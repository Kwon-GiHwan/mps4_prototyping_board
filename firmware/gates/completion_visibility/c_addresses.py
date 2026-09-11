"""Successor completion-visibility checker: c addresses."""

from __future__ import annotations

import collections
import re

from .constants import (
    MAILBOX_SYMBOL,
    NPU_BASE_SYMBOLS,
    UNRESOLVED_INITIALIZER,
    UNRESOLVED_ROLE,
    _ACCESSOR_SYMBOL_RE,
    _ALIAS_BUDGET_FACTOR,
    _ALIAS_BUDGET_FLOOR,
    _ASSIGNMENT_BOUNDARY,
    _ASSIGNMENT_OPERATOR_RE,
    _BRACKET_OPENERS,
    _CALLABLE_END,
    _CALL_RE,
    _CAST_RE,
    _CMD_VALUE_RE,
    _COMPOUND_LVALUE_RE,
    _C_TOKEN_RE,
    _DECLARATOR_INITIALIZER_RE,
    _DECLARATOR_TYPES,
    _DEREF_RE,
    _DESIGNATOR_RE,
    _DIRECTIVE_LINE_RE,
    _EVAL_MAGNITUDE_LIMIT,
    _EVAL_SHIFT_LIMIT,
    _EVAL_TOKEN_RE,
    _IDENTIFIER_RE,
    _INDEX_RE,
    _INITIALIZER_BUDGET_FACTOR,
    _INITIALIZER_BUDGET_FLOOR,
    _INLINE_SPACE,
    _MACRO_CRITICAL_MEMBER_RE,
    _MACRO_CRITICAL_NAME_RE,
    _MACRO_DEFINITION_RE,
    _MACRO_STORE_RE,
    _MAX_INITIALIZER_ELEMENTS,
    _MEMBER_ACCESS_RE,
    _NAME_CHARACTER_RE,
    _NON_CALL_KEYWORDS,
    _NOT_AN_ADDRESS_RE,
    _NPU_REG_DEFINE_RE,
    _NPU_REG_NAME_RE,
    _OPERAND_END_CHARACTERS,
    _POINTER_CAST_RE,
    _POINTER_WORD_BYTES,
    _RAW_REGISTER_PREFIX_RE,
    _RAW_REGISTER_RE,
    _STATEMENT_SCAN_FACTOR,
    _STATEMENT_SCAN_FLOOR,
    _STEPPED_NAME_RE,
    _STEP_RE,
    _STORE_RE,
    _TOKEN_PASTE_RE,
    _TYPE_NAME_TOKEN_RE,
    _UNARY_DEREF_RE,
    _UNCLASSIFIED_MACRO_KIND,
)

from .errors import (
    fail,
)

from .c_lexical import (
    _blank_span,
    _matching_brace,
    code_contains,
    code_positions,
    directive_view,
    names_identifier,
)


def _c_divide(left: int, right: int) -> int:
    """``left / right`` with C's truncation toward zero."""

    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def _c_modulo(left: int, right: int) -> int:
    """``left % right`` as C defines it from the truncated quotient."""

    return left - _c_divide(left, right) * right


def _evaluate_constant(
    expr: str, defines: dict[str, int], zero_names: tuple[str, ...] = ()
) -> int | None:
    """The integer ``expr`` denotes, or ``None`` when any part of it is unknown.

    ``zero_names`` are the symbols the caller wants treated as the origin, so
    the same evaluator answers "what constant is this" and "how far past that
    pointer is this".
    """

    tokens = _EVAL_TOKEN_RE.findall(expr)
    cursor = [0]

    def peek() -> str | None:
        return tokens[cursor[0]] if cursor[0] < len(tokens) else None

    def primary() -> int | None:
        token = peek()
        if token is None:
            return None
        cursor[0] += 1
        if token == "(":
            value = bit_or()
            if peek() != ")":
                return None
            cursor[0] += 1
            return value
        if token in ("+", "-", "~"):
            value = primary()
            if value is None:
                return None
            if token == "+":
                return value
            return -value if token == "-" else ~value
        if token[0].isdigit():
            try:
                return int(token.rstrip("uUlL"), 0)
            except ValueError:
                return None
        if not (token[0].isalpha() or token[0] == "_"):
            return None
        if token in zero_names:
            return 0
        return defines.get(token)

    def binary(next_level, operators) -> int | None:
        value = next_level()
        while value is not None and peek() in operators:
            operator = tokens[cursor[0]]
            cursor[0] += 1
            right = next_level()
            if right is None:
                return None
            if operator == "+":
                value += right
            elif operator == "-":
                value -= right
            elif operator == "*":
                value *= right
            elif operator in ("/", "%"):
                if right == 0:
                    return None
                # C99 6.5.5p6 truncates the quotient toward zero and defines the
                # remainder from it, so ``(0-3)/2`` is -1 and ``(0-4)%3`` is -1.
                # Python floors instead, which answers -2 and 2 -- a different
                # number, and for ``write_reg(NPU_REG_CMD, ...)`` a different
                # bit 0. An evaluator that folds a submit into a non-submit is
                # a rule the arithmetic walks around, so the C answer is the one
                # computed here.
                value = _c_divide(value, right) if operator == "/" else _c_modulo(value, right)
            elif operator == "<<":
                if not 0 <= right <= _EVAL_SHIFT_LIMIT:
                    return None
                value <<= right
            elif operator == ">>":
                if right < 0:
                    return None
                value >>= right
            elif operator == "&":
                value &= right
            elif operator == "^":
                value ^= right
            else:
                value |= right
            if abs(value) > _EVAL_MAGNITUDE_LIMIT:
                return None
        return value

    def term() -> int | None:
        return binary(primary, ("*", "/", "%"))

    def additive() -> int | None:
        return binary(term, ("+", "-"))

    def shift() -> int | None:
        return binary(additive, ("<<", ">>"))

    # The bitwise levels sit below the shifts in C's precedence, and each is its
    # own level: ``a | b & c`` is ``a | (b & c)``. Folding them is not a
    # convenience -- an address written ``0x48000014U | 0U`` designates exactly
    # one register, and an evaluator that stops at ``|`` reports the whole
    # expression as "not an address" and hands every MMIO rule below a load it
    # never sees.
    def bit_and() -> int | None:
        return binary(shift, ("&",))

    def bit_xor() -> int | None:
        return binary(bit_and, ("^",))

    def bit_or() -> int | None:
        return binary(bit_xor, ("|",))

    value = bit_or()
    return value if cursor[0] == len(tokens) else None


def npu_register_offsets(defines: dict[str, int]) -> dict[int, str]:
    """The source's own ``NPU_REG_*`` offset table, keyed by byte offset.

    An offset two register names share is not a name, so it is dropped rather
    than resolved to whichever one sorts first.
    """

    seen: dict[int, set[str]] = {}
    for name, value in defines.items():
        match = _NPU_REG_DEFINE_RE.match(name)
        if match is not None:
            seen.setdefault(value, set()).add(match.group(1))
    return {offset: sorted(names)[0] for offset, names in seen.items() if len(names) == 1}


def _role_at_offset(offset: int, defines: dict[str, int]) -> str:
    return npu_register_offsets(defines).get(offset, UNRESOLVED_ROLE)


def _has_unary_deref(expr: str) -> bool:
    return _UNARY_DEREF_RE.search(expr) is not None


def _strip_address_of(expr: str) -> str:
    """Drop every *unary* ``&`` and keep every bitwise one.

    ``expr.replace("&", " ")`` drops address-of, and it also destroys ``&`` as
    an operator -- so ``0x50004004U & V14_ADDR_MASK`` reaches the evaluator as
    two adjacent tokens, folds to ``None``, and the address the compiler builds
    from it is reported as "not an address at all". The evaluator has folded
    ``&`` all along; only this rewrite kept it from ever seeing one.

    An ``&`` is unary exactly when nothing that can end an operand precedes it,
    which is what separates ``&mailbox[3]`` from ``base & mask``.
    """

    out = list(expr)
    previous = ""
    for index, character in enumerate(expr):
        if character in _INLINE_SPACE:
            continue
        if character == "&" and not (
            previous
            and (previous in _OPERAND_END_CHARACTERS or _NAME_CHARACTER_RE.match(previous))
        ):
            out[index] = " "
            previous = "&"
            continue
        previous = character
    return "".join(out)


def _flatten_address(expr: str) -> str:
    """Drop casts and address-of, and turn an index into an additive offset."""

    stripped = _CAST_RE.sub(" ", expr)
    flattened = _INDEX_RE.sub(
        lambda match: "+((%s)*%d)" % (match.group(1).strip() or "0", _POINTER_WORD_BYTES),
        stripped,
    )
    return _strip_address_of(flattened)


def resolve_address_role(expr: str, defines: dict[str, int], known: dict[str, str]) -> str | None:
    """The register an address expression designates.

    ``None`` means the expression is not an NPU address at all;
    ``UNRESOLVED_ROLE`` means it provably is one and this gate cannot say which
    register, which is the fail-closed answer rather than a silent pass.
    """

    # An initializer the declarator walk could not flatten binds the name to
    # *something*, and this gate cannot say what. That is ``UNRESOLVED`` -- the
    # answer the callers refuse -- and never ``None``, which would make every
    # dereference of the name an access to nothing at all.
    if expr == UNRESOLVED_INITIALIZER:
        return UNRESOLVED_ROLE
    # The deref test runs over the cast-stripped text, because a cast's closing
    # parenthesis is not an operator: ``(int)*p`` reads the word ``p`` points at
    # exactly as ``*p`` does, and reading it as an address instead leaves the
    # leading ``*`` in the evaluator's hands, which answers ``UNRESOLVED`` and
    # refuses an ordinary value binding. The load itself is not lost -- the
    # ``*`` is its own access site in ``access_expressions``.
    if _has_unary_deref(expr) or _has_unary_deref(_CAST_RE.sub(" ", expr)):
        return None
    if _NOT_AN_ADDRESS_RE.search(expr) is not None:
        # A predicate or a selection is not an address, and reading one as an
        # address would make every ordinary comparison an unresolvable NPU
        # pointer. But a *pointer cast* over one says the operator meant it as
        # an address -- ``(volatile uint32_t *)(c ? A : B)`` reaches a register
        # this gate cannot name, which is refused rather than ignored.
        return UNRESOLVED_ROLE if _POINTER_CAST_RE.search(expr) is not None else None
    flat = _flatten_address(expr)
    # A call *returns* a register value; it does not name the register's
    # address, so ``x = read_reg(NPU_REG_STATUS)`` binds a word, not a pointer.
    if _CALL_RE.search(flat) is not None:
        return None
    registers = sorted(set(_NPU_REG_NAME_RE.findall(flat)))
    if len(registers) > 1:
        return UNRESOLVED_ROLE
    if len(registers) == 1:
        return registers[0]

    pointers = sorted({name for name in _IDENTIFIER_RE.findall(flat) if name in known})
    if pointers:
        if len(pointers) > 1:
            return UNRESOLVED_ROLE
        inherited = known[pointers[0]]
        displacement = _evaluate_constant(flat, defines, (pointers[0],))
        if displacement == 0:
            return inherited
        if displacement is None or inherited == UNRESOLVED_ROLE:
            return UNRESOLVED_ROLE
        anchor = defines.get("NPU_REG_" + inherited)
        if anchor is None:
            return UNRESOLVED_ROLE
        return _role_at_offset(anchor + displacement, defines)

    bases = [name for name in NPU_BASE_SYMBOLS if names_identifier(flat, name)]
    if bases:
        offset = _evaluate_constant(flat, defines, (bases[0],))
        return UNRESOLVED_ROLE if offset is None else _role_at_offset(offset, defines)

    # What is left is an absolute address: a constant reached through a pointer
    # cast. Nothing in it names a register, so whether it can be pinned depends
    # entirely on the translation unit's own map.
    if _POINTER_CAST_RE.search(expr) is None:
        return None
    value = _evaluate_constant(flat, defines)
    if value is None:
        # The pointer cast is the operator saying "this is an address". "This
        # gate cannot fold it" is then not evidence that it is not one -- it is
        # evidence that nothing here can say *which* one, which is
        # ``UNRESOLVED`` and is refused. Reporting it as "not an address" is
        # what lets an operator walk around every MMIO rule below by choosing an
        # operator the evaluator does not implement, or by hiding a foldable
        # address behind an identifier: ``0x50004004U & V14_U32_INVALID`` is the
        # STATUS register to the compiler.
        #
        # A leftover identifier does not earn an exemption here. Every shape
        # this gate *can* name -- an ``NPU_REG_*`` offset, a bound pointer, a
        # base symbol -- was resolved above, so reaching this line with an
        # identifier still in hand means the register genuinely cannot be named.
        return UNRESOLVED_ROLE
    # An address is an unsigned machine word. ``~0xB7FFFFEBU`` is 0x48000014 to
    # the compiler and a negative integer to an evaluator that folds without
    # width, so the fold is normalised before it is compared against the window.
    value &= 0xFFFFFFFF
    table = npu_register_offsets(defines)
    base = defines.get(NPU_BASE_SYMBOLS[0])
    if base is None or not table:
        # The source pins no register map at all, so this gate cannot say which
        # word -- or even which peripheral -- the address reaches. Ignoring it
        # would let every ordering, counting and isolation rule below be walked
        # around by writing the number instead of the name, so it is refused.
        # Resolving it from an assumed map is the one thing this gate must not
        # do: an offset table it invented is not the source's.
        return UNRESOLVED_ROLE
    if not base <= value <= base + max(table):
        return None
    return table.get(value - base, UNRESOLVED_ROLE)


def _binding_dependents(
    bindings: tuple[tuple[str, str], ...]
) -> tuple[dict[str, list[int]], int]:
    """``name -> binding indices mentioning it``, and the total edge count."""

    dependents: dict[str, list[int]] = {}
    edges = 0
    for index, (_name, expr) in enumerate(bindings):
        for token in set(_IDENTIFIER_RE.findall(expr)):
            dependents.setdefault(token, []).append(index)
            edges += 1
    return dependents, edges


def _alias_fixpoint(bindings, resolve, collapse, what: str) -> dict[str, object]:
    """The least fixpoint of ``resolve`` over ``bindings``, on a bounded worklist.

    ``resolve(expr, known)`` answers what a binding's right-hand side designates
    given what is known so far, or ``None`` when it designates nothing here.
    ``collapse`` reduces the set of answers a name accumulated to the one value
    every rule downstream reads -- a name that resolved two ways is the
    fail-closed ``UNRESOLVED``.
    """

    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    observed: dict[str, set[object]] = {}
    known: dict[str, object] = {}
    pending = collections.deque(range(len(bindings)))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving %s did not settle within %d steps: the source binds more aliases than "
                "this gate walks" % (what, budget)
            )
        name, expr = bindings[index]
        answer = resolve(expr, known)
        if answer is None:
            continue
        seen = observed.setdefault(name, set())
        if answer in seen:
            continue
        seen.add(answer)
        collapsed = collapse(seen)
        if name in known and known[name] == collapsed:
            continue
        known[name] = collapsed
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return known


def file_scope_text(masked: str) -> str:
    """``masked`` with every top-level function body blanked, offsets preserved.

    What is left is the declarations a function inherits rather than binds. A
    per-function pointer walk that cannot see them reports a dereference of a
    file-scope register pointer as an access to nothing at all, which is how a
    running-QSIZE read moved out of the function that performs it.
    """

    out = list(masked)
    for _name, start, stop in function_spans(masked):
        # A function body's ``{`` follows its parameter list; a brace
        # initializer's follows an ``=``. Only the first is a body, and blanking
        # the second would delete the very declaration this view exists to keep.
        head = masked[: start - 1].rstrip()
        if head.endswith(")"):
            _blank_span(out, masked, start, stop)
    return "".join(out)


def pointer_roles(body: str, defines: dict[str, int], scope: str = "") -> dict[str, str]:
    """Every name in ``body`` bound to an NPU register, transitively.

    ``scope`` is the enclosing declaration text -- the translation unit's file
    scope -- whose bindings the body inherits. It is resolved in the same
    fixpoint rather than beside it, so a file-scope pointer copied into a local
    one is the same pointer here too.

    A pointer copied from a bound pointer is the same pointer, and a chain of
    such copies is still that pointer, so the bindings are re-scanned until
    nothing new resolves. A name bound twice to two different registers is
    ``UNRESOLVED``: nothing here can say which binding a later dereference
    reaches.

    ``p += 4`` and ``++p`` re-point a bound pointer at another register without
    ever writing ``p = expr``, so the binding walk above cannot see them and
    would keep crediting the original register for every later dereference --
    which is worse than not seeing the load, because the load then *satisfies*
    a read-order rule while reading somewhere else. A stepped name is therefore
    ``UNRESOLVED`` here, and refused by ``require_resolved_pointers``.
    """

    bindings = _bindings(scope) + _bindings(body)
    resolved = _alias_fixpoint(
        bindings,
        lambda expr, known: resolve_address_role(expr, defines, known),
        lambda roles: sorted(roles)[0] if len(roles) == 1 else UNRESOLVED_ROLE,
        "an NPU-region pointer",
    )
    for name in compound_assignment_targets(scope + body, tuple(sorted(resolved))):
        resolved[name] = UNRESOLVED_ROLE
    return resolved


def unresolved_pointers(roles: dict[str, str]) -> tuple[str, ...]:
    return tuple(sorted(name for name, role in roles.items() if role == UNRESOLVED_ROLE))


def require_resolved_pointers(roles: dict[str, str], what: str) -> None:
    unresolved = unresolved_pointers(roles)
    if unresolved:
        raise fail(
            "%s binds an NPU-region pointer this gate cannot resolve to one register: %s"
            % (what, ", ".join(unresolved))
        )


def macro_definitions(masked: str) -> tuple[tuple[str, str, str], ...]:
    """``(name, parameter list, replacement list)`` for every ``#define``.

    Read over ``directive_view`` so a definition split across physical lines is
    the one logical line the compiler sees.
    """

    return tuple(
        (match.group(1), match.group(2) or "", match.group(3))
        for match in _MACRO_DEFINITION_RE.finditer(directive_view(masked))
    )


def mmio_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list carries an MMIO access.

    ``#define REG32(a) (*(volatile uint32_t *)(a))`` turns an MMIO access into
    what reads here as an ordinary call, so the address never reaches
    ``resolve_address_role`` and the access is counted as nothing. This gate
    does not preprocess, so it cannot say which register such a call names --
    which makes it exactly the unresolved access every rule in this file
    refuses rather than ignores.

    An object-like macro is the same construct without a parameter list, and its
    invocation site carries no parentheses at all: ``#define POKE
    write_reg(NPU_REG_CMD, 1U)`` invoked as ``POKE;`` is a submit write that no
    call, effect or CMD-value rule here can see. A replacement list that names a
    register this gate counts is therefore refused on the same terms, whichever
    of the two forms carries it.
    """

    return tuple(sorted(mmio_macro_kinds(masked)))


def mmio_macro_kinds(masked: str) -> dict[str, str]:
    """Every MMIO-carrying macro, mapped to what its replacement list carries.

    ``"designation"`` is a register *name* the confinement scan would otherwise
    never see; ``"accessor"`` is the vendor accessor under another name;
    ``"dereference"`` is an unexpanded MMIO access. The three are reported
    separately because they are refused for different reasons.
    """

    found: dict[str, str] = {}
    for name, _parameters, body in macro_definitions(masked):
        if _RAW_REGISTER_PREFIX_RE.search(body) is not None:
            found[name] = "designation"
        elif _ACCESSOR_SYMBOL_RE.search(body) is not None:
            found[name] = "accessor"
        elif _POINTER_CAST_RE.search(body) is not None and _DEREF_RE.search(body) is not None:
            found[name] = "dereference"
    return found


def require_no_token_paste(masked: str, what: str) -> None:
    """Refuse a macro replacement list that builds an identifier by pasting."""

    for name, _parameters, body in macro_definitions(masked):
        if _TOKEN_PASTE_RE.search(body) is None:
            continue
        if _RAW_REGISTER_PREFIX_RE.search(body) is not None:
            # ``#define SEL(x) NPU_REG_##x`` is a paste too, and it is already a
            # refusal by the rule that owns register designations. Leaving it to
            # that rule keeps a source named by the most specific thing wrong
            # with it rather than by the operator it happens to use.
            continue
        raise fail(
            "%s builds an identifier this gate cannot compute: the macro %s pastes tokens in "
            "its replacement list, and a name produced during translation is one no call, "
            "reachability or designation rule in this file can read"
            % (what, name)
        )


def mmio_macro_table(masked: str) -> tuple[tuple[str, ...], dict[str, str]]:
    """``(names, kinds)`` for every MMIO-carrying macro, resolved together.

    Returned as a pair so a caller cannot pass the names of one walk with the
    kinds of another -- or, as happened before, the names with no kinds at all,
    which reported every refusal under whichever construct the default named.
    """

    kinds = mmio_macro_kinds(masked)
    return tuple(sorted(kinds)), kinds


def require_no_macro_mmio(
    text: str, macros: tuple[str, ...], what: str, kinds: dict[str, str] | None = None
) -> None:
    """Refuse an MMIO access made through a macro this gate cannot expand.

    The invocation is looked for as a *name* rather than as ``name(``, because
    an object-like macro is invoked by naming it and a rule that insists on the
    parenthesis sees only half of the construct.
    """

    for name in macros:
        if names_identifier(text, name):
            raise fail(
                "%s reaches an NPU-region address this gate cannot resolve to one register: "
                "the macro %s expands to an unexpanded MMIO %s"
                % (what, name, (kinds or {}).get(name, _UNCLASSIFIED_MACRO_KIND))
            )


def require_resolved_dereferences(
    text: str, defines: dict[str, int], roles: dict[str, str], what: str
) -> None:
    """Refuse an MMIO dereference this gate cannot pin to one register.

    ``require_resolved_pointers`` covers an address that is *bound to a name*.
    This covers the one that is not: an absolute address dereferenced where it
    stands. Its role reaches every rule below as ``UNRESOLVED``, and a rule that
    merely fails to recognise it is a rule the number walks around -- so the
    access is named here rather than counted as nothing.
    """

    for site, role, is_write in dereference_sites(text, defines, roles):
        if role == UNRESOLVED_ROLE:
            raise fail(
                "%s reaches an NPU-region address this gate cannot resolve to one register: "
                "%s at offset %d" % (what, "write" if is_write else "read", site)
            )


def _alternation(names: tuple[str, ...]) -> str:
    return "|".join(re.escape(name) for name in names)


def _statement_end(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            return index
    return len(text)


def blank_directives(text: str) -> str:
    """Blank every preprocessor directive line, preserving each byte offset.

    A directive is not a statement and carries no terminator, so a scan that
    breaks statements on ``;``/``{``/``}`` alone folds the directive line into
    the *next* statement's lvalue: ``#line 1`` above ``d.variant_id = ...``
    makes the lvalue ``#line 1 d.variant_id``, which no ``^``-anchored lvalue
    rule matches. The store then exists for the compiler and not for the gate.
    Blanking the line in place removes it from the statement stream while
    leaving every offset -- which the load-provenance and dominance rules
    compare against -- exactly where it was.
    """

    return _DIRECTIVE_LINE_RE.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), text
    )


def _statement_scan_budget(text: str) -> int:
    return _STATEMENT_SCAN_FACTOR * len(text) + _STATEMENT_SCAN_FLOOR


def _refuse_statement_scan(walked: int, budget: int) -> None:
    raise fail(
        "recovering the statements of this source did not settle within %d walked characters "
        "(reached %d): it writes more assignments into one statement than this gate walks"
        % (budget, walked)
    )


def assignment_statements(text: str) -> tuple[tuple[int, str, str], ...]:
    """``(start, lvalue, rvalue)`` for every simple assignment in ``text``."""

    scan = blank_directives(text)
    budget = _statement_scan_budget(scan)
    walked = 0
    found: list[tuple[int, str, str]] = []
    depth = 0
    start = 0
    for index, character in enumerate(scan):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            start = index + 1
        elif (
            depth == 0
            and character == "="
            and scan[index + 1 : index + 2] != "="
            and scan[index - 1 : index] not in _ASSIGNMENT_BOUNDARY
        ):
            stop = _statement_end(scan, index + 1)
            walked += stop - start
            if walked > budget:
                _refuse_statement_scan(walked, budget)
            found.append((start, scan[start:index], scan[index + 1 : stop]))
    return tuple(found)


def compound_assignment_lvalues(text: str) -> tuple[tuple[int, str], ...]:
    """``(start, lvalue)`` for every read-modify-write statement in ``text``.

    A compound assignment and an increment are stores that no ``name = expr``
    walk sees, and the lvalue they write is an expression rather than a name:
    ``mailbox[V14_MBOX_VARIANT_ID] += 2U`` and ``0[mailbox]++`` both mutate an
    appendix word after its canonical store, and a rule that only knows the
    bare array name never looks at either. The whole lvalue is recovered here
    so the caller can resolve *which storage* it designates.
    """

    scan = blank_directives(text)
    budget = _statement_scan_budget(scan)
    walked = 0
    found: list[tuple[int, str]] = []
    depth = 0
    start = 0
    index = 0
    length = len(scan)
    while index < length:
        character = scan[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            start = index + 1
        elif depth == 0:
            # Each recovered lvalue is one walk of its own statement, so the
            # same budget bounds the same quadratic ``assignment_statements``
            # is bounded against.
            compound = _COMPOUND_LVALUE_RE.match(scan, index)
            if compound is not None and scan[compound.end() : compound.end() + 1] != "=":
                walked += index - start
                if walked > budget:
                    _refuse_statement_scan(walked, budget)
                found.append((start, scan[start:index]))
                index = compound.end()
                continue
            step = _STEP_RE.match(scan, index)
            if step is not None:
                before = scan[start:index].strip()
                after = _expression_after(scan, step.end())
                walked += (index - start) + len(after)
                if walked > budget:
                    _refuse_statement_scan(walked, budget)
                found.append((start, before if before else after))
                index = step.end()
                continue
        index += 1
    return tuple(found)


def compound_assignment_targets(text: str, names: tuple[str, ...]) -> tuple[str, ...]:
    """Every name in ``names`` that ``text`` compound-assigns or increments.

    ``p += 1`` and ``++p`` re-point a pointer without ever writing a plain
    assignment, so a provenance walk built on ``name = expr`` cannot see them.
    Naming them here is what keeps that walk honest.
    """

    if not names:
        return ()
    # Driven by the *operator*, not by an alternation of every candidate name.
    # A pattern rebuilt from n names and matched against the whole text costs
    # O(n x len(text)), so a source that binds thousands of pointers pays a full
    # rescan per name -- the quadratic this walk is bounded against. One pass
    # collects every stepped name; the set membership does the filtering.
    wanted = frozenset(names)
    found = {
        name
        for match in _STEPPED_NAME_RE.finditer(text)
        for name in (match.group(1) or match.group(2) or match.group(3),)
        if name in wanted
    }
    return tuple(sorted(found))


def statement_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list carries a store rather than a value."""

    return tuple(
        sorted(
            {
                name
                for name, _parameters, body in macro_definitions(masked)
                if _MACRO_STORE_RE.search(body) is not None
            }
        )
    )


def require_no_statement_macro(masked: str, what: str) -> None:
    """Refuse a source that hides a store inside a macro replacement list.

    ``blank_directives`` removes the ``#define`` line from the statement stream
    -- it has to, or the directive folds into the next statement's lvalue -- and
    the invocation site is then only ``NAME;``, which names no storage at all.
    So ``#define POKE mailbox[V14_MBOX_VARIANT_ID] = 7U`` is a store that exists
    for the compiler and for no rule in this file: not for
    ``assignment_statements``, not for ``mailbox_stores``, not for the
    ``irq_triggered`` site walk, and not for the runner's record closure.

    This gate does not expand macros, which is stated in every manifest, so it
    cannot model where such a body lands. The fail-closed answer is to refuse the
    definition rather than to analyse a translation unit whose stores it cannot
    see; the frozen sources define no such macro, so the refusal costs the
    contract nothing.
    """

    names = statement_macro_names(masked)
    if names:
        raise fail(
            "%s defines %s with a statement in its replacement list: this gate does not "
            "expand macros, so a store written there is a store no rule here can see"
            % (what, names[0])
        )


def critical_lvalue_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list names storage the contract tables own."""

    return tuple(
        sorted(
            {
                name
                for name, _parameters, body in macro_definitions(masked)
                if _MACRO_CRITICAL_NAME_RE.search(body) is not None
                or _MACRO_CRITICAL_MEMBER_RE.search(body) is not None
            }
        )
    )


def _opens_compound_literal(text: str, brace: int, open_of: dict[int, int]) -> bool:
    """Whether the ``{`` at ``brace`` is a compound literal's, not a block's."""

    cursor = brace - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0 or text[cursor] != ")":
        return False
    open_index = open_of.get(cursor)
    if open_index is None:
        return False
    tokens = _C_TOKEN_RE.findall(text[open_index + 1 : cursor])
    if not any(token in _DECLARATOR_TYPES for token in tokens):
        return False
    # What separates the parentheses of a compound literal's type name from a
    # function definition's parameter list, or an ``if``'s condition, is what
    # sits in front of them: a callee name or a keyword, or the ``)``/``]`` of
    # something already callable. A unary ``&`` is not one of those -- nothing
    # is called through it -- so the operand-end set ``_strip_address_of`` uses
    # is deliberately not the set here: ``*&(volatile uint32_t *const){ addr }``
    # is a compound literal, and reading its ``&`` as an operand end is what let
    # one through.
    cursor = open_index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return False
    return not (_NAME_CHARACTER_RE.match(text[cursor]) or text[cursor] in _CALLABLE_END)


def require_no_compound_literal(masked: str, what: str) -> None:
    """Refuse an initializer this gate cannot attribute to any declared name."""

    _close_of, open_of = _bracket_pairs(masked)
    for index, character in enumerate(masked):
        if character == "{" and _opens_compound_literal(masked, index, open_of):
            raise fail(
                "%s writes a compound literal at offset %d: it initializes storage this gate "
                "cannot bind to any name, so an access through it is an access no rule here sees"
                % (what, index)
            )


def require_no_critical_lvalue_macro(masked: str, what: str) -> None:
    """Refuse a macro that spells the mailbox, an appendix word or a record field."""

    names = critical_lvalue_macro_names(masked)
    if names:
        raise fail(
            "%s defines %s with contract storage in its replacement list: this gate does not "
            "expand macros, so a store written through it is a store no rule here can see"
            % (what, names[0])
        )


def _split_initializer(text: str) -> tuple[str, ...]:
    """Split an initializer body on the commas that separate its clauses.

    ``_split_top_level`` counts parentheses and brackets only, which is right
    for an argument list and wrong here: the comma between two *nested* brace
    groups sits at paren depth zero, so a nested initializer would be cut in
    half rather than descended into.
    """

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        if depth == 0 and character == ",":
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(character)
    parts.append("".join(buffer))
    return tuple(parts)


def _initializer_elements(text: str, open_index: int) -> tuple[str, ...]:
    """The leaf clauses of the brace list at ``open_index``, nesting flattened.

    A brace group is descended into rather than treated as one clause, so
    ``{{ A }}`` and ``{ { A } }`` bind exactly what ``{ A }`` binds. A clause
    this walk cannot reduce to a brace-free expression -- an unterminated group,
    or one still carrying a brace after its designator comes off -- is
    ``UNRESOLVED_INITIALIZER`` rather than nothing, because a name left unbound
    is a name every access through it resolves to "not an address at all".
    """

    depth = 0
    close = -1
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                close = index
                break
    if close < 0:
        return (UNRESOLVED_INITIALIZER,)
    budget = _INITIALIZER_BUDGET_FACTOR * (close - open_index) + _INITIALIZER_BUDGET_FLOOR
    elements: list[str] = []
    pending = [text[open_index + 1 : close]]
    read = 0
    while pending:
        body = pending.pop()
        read += len(body)
        if read > budget or len(elements) > _MAX_INITIALIZER_ELEMENTS:
            return (UNRESOLVED_INITIALIZER,)
        for clause in _split_initializer(body):
            item = _DESIGNATOR_RE.sub("", clause).strip()
            if not item:
                continue
            if item.startswith("{") and item.endswith("}"):
                pending.append(item[1:-1])
                continue
            elements.append(UNRESOLVED_INITIALIZER if "{" in item or "}" in item else item)
    if len(elements) > _MAX_INITIALIZER_ELEMENTS:
        return (UNRESOLVED_INITIALIZER,)
    return tuple(elements)


def _declarator_bindings(text: str) -> tuple[tuple[str, str], ...]:
    """``(name, element)`` for every array declarator initialized with a brace list."""

    found: list[tuple[str, str]] = []
    for match in _DECLARATOR_INITIALIZER_RE.finditer(text):
        for element in _initializer_elements(text, match.end()):
            found.append((match.group(1), element))
    return tuple(found)


def _clause_expression(text: str, start: int) -> str:
    """The expression at ``start``, up to the comma or semicolon that ends it."""

    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and character in ",;":
            break
        index += 1
    return text[start:index]


def _assignment_bindings(text: str) -> tuple[tuple[str, str], ...]:
    """``(name, expr)`` for every ``name = expr`` clause, declarator lists split."""

    found: list[tuple[str, str]] = []
    for match in _ASSIGNMENT_OPERATOR_RE.finditer(text):
        operator = match.end() - 1
        if text[operator - 1 : operator] in _ASSIGNMENT_BOUNDARY:
            continue
        expression = _clause_expression(text, match.end()).strip()
        if expression:
            found.append((match.group(1), expression))
    return tuple(found)


def _is_declaration(lvalue: str) -> bool:
    match = re.match(r"\s*([A-Za-z_]\w*)", lvalue)
    return match is not None and match.group(1) in _DECLARATOR_TYPES


def _strip_leading_derefs(expr: str) -> tuple[int, str]:
    stripped = expr.strip()
    count = 0
    while stripped.startswith("*"):
        count += 1
        stripped = stripped[1:].lstrip()
    return count, stripped


def _flatten_word_address(expr: str) -> str:
    """Drop casts and address-of, and turn an index into a *word* offset.

    ``_flatten_address`` answers the same question in bytes, because an MMIO
    pointer displaces by four per step. The mailbox is addressed by appendix
    word, so the same walk counts in words here.
    """

    stripped = _CAST_RE.sub(" ", expr)
    flattened = _INDEX_RE.sub(
        lambda match: "+(%s)" % (match.group(1).strip() or "0"), stripped
    )
    return _strip_address_of(flattened)


def resolve_mailbox_word(expr: str, defines: dict[str, int], known: dict[str, object]) -> object:
    """The appendix word an expression designates, over every spelling.

    ``None`` means the expression does not reach the mailbox at all;
    ``UNRESOLVED_ROLE`` means it provably does and this gate cannot say which
    word, which is the fail-closed answer rather than a silent pass.
    """

    # Same asymmetry as ``resolve_address_role``: an initializer this gate could
    # not flatten may well name the mailbox, so it is refused rather than
    # dropped.
    if expr == UNRESOLVED_INITIALIZER:
        return UNRESOLVED_ROLE
    derefs, addressed = _strip_leading_derefs(expr)
    flat = _flatten_word_address(addressed)
    if _CALL_RE.search(flat) is not None:
        return None
    names = sorted(
        {
            name
            for name in _IDENTIFIER_RE.findall(flat)
            if name == MAILBOX_SYMBOL or name in known
        }
    )
    if not names:
        return None
    if len(names) > 1 or derefs > 1:
        return UNRESOLVED_ROLE
    base = names[0]
    inherited = 0 if base == MAILBOX_SYMBOL else known[base]
    step = _evaluate_constant(flat, defines, (base,))
    if inherited == UNRESOLVED_ROLE or step is None:
        return UNRESOLVED_ROLE
    return inherited + step


def _expression_after(text: str, start: int) -> str:
    """The expression beginning at ``start``, up to its statement terminator."""

    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if character in ";,":
                break
            if character == "=" and text[index + 1 : index + 2] != "=":
                break
        index += 1
    return text[start:index]


def _token_before(text: str, index: int) -> tuple[int, str]:
    """``(start, token)`` for the name token ending just before ``index``.

    Written as a bounded backward scan rather than ``text[:index].rstrip()`` and
    a ``$``-anchored search. Both of those are linear in the *whole* prefix, and
    a source with many declarator stars then costs one full prefix scan each --
    quadratic in exactly the input the size bound was supposed to cover.
    """

    cursor = index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    stop = cursor + 1
    while cursor >= 0 and _NAME_CHARACTER_RE.match(text[cursor]):
        cursor -= 1
    return cursor + 1, text[cursor + 1 : stop]


def _token_after(text: str, index: int) -> str:
    """The name token beginning just after ``index``."""

    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    start = cursor
    while cursor < len(text) and _NAME_CHARACTER_RE.match(text[cursor]):
        cursor += 1
    return text[start:cursor]


def _next_non_space(text: str, index: int) -> str:
    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    return text[cursor : cursor + 2]


def _is_declarator_star(text: str, star_index: int) -> bool:
    if _token_before(text, star_index)[1] in _DECLARATOR_TYPES:
        return True
    return _token_after(text, star_index + 1) in _DECLARATOR_TYPES


def _is_cast_parenthesis(text: str, open_index: int, close_index: int) -> bool:
    """Whether ``text[open_index:close_index]`` is a cast rather than an operand.

    A cast's ``)`` and a call's ``)`` are the same character, which is why a rule
    that reads "the previous character is ``)``" as "an operand ended here"
    resolves ``(bool *)&flag`` the same way it resolves ``f() & flag`` -- and
    resolves it in the fail-open direction, because the first one takes an
    address and the second one reads a value.

    The two are separable without a symbol table. A cast encloses a type name and
    nothing else -- identifiers and ``*``, no literal, no operator, no comma --
    and nothing that can end an operand may precede its ``(``, or the parentheses
    are a call's argument list or a subscripted expression instead. A
    parenthesised single identifier is ambiguous in C itself; it is read here as a
    cast, which is the direction that refuses rather than credits.
    """

    tokens = _C_TOKEN_RE.findall(text[open_index + 1 : close_index])
    if not tokens:
        return False
    for token in tokens:
        if token != "*" and _TYPE_NAME_TOKEN_RE.match(token) is None:
            return False
    cursor = open_index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return True
    return not (
        _NAME_CHARACTER_RE.match(text[cursor]) or text[cursor] in _OPERAND_END_CHARACTERS
    )


def _bracket_pairs(text: str) -> tuple[dict[int, int], dict[int, int]]:
    """``(close_of_open, open_of_close)`` for every matched bracket, in one pass.

    Matching each bracket on demand means rescanning from it to the end of the
    text, and an unterminated ``[`` makes that rescan reach the end every time --
    so a source made of nothing but openers costs one full scan per opener. The
    same shape ``_mask_one_pass`` already guards against for ``/*``, answered the
    same way: walk the text once and remember the answers.
    """

    close_of: dict[int, int] = {}
    open_of: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    for index, character in enumerate(text):
        if character in "([":
            stack.append((character, index))
        elif character in ")]":
            if stack and stack[-1][0] == _BRACKET_OPENERS[character]:
                _opener, start = stack.pop()
                close_of[start] = index
                open_of[index] = start
    return close_of, open_of


def _subscript_expression(
    text: str, bracket: int, pairs: tuple[dict[int, int], dict[int, int]]
) -> tuple[int, str, int] | None:
    """``(start, expression, stop)`` for the subscript opening at ``bracket``.

    The base is the postfix expression the ``[`` binds to -- a name, an integer
    literal, or a parenthesised expression -- so ``p[0]``, ``0[p]`` and
    ``(base + 1)[0]`` are each recovered whole and handed to the same resolver a
    ``*`` access is handed.
    """

    close_of, open_of = pairs
    close = close_of.get(bracket)
    if close is None:
        return None
    cursor = bracket - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return None
    if text[cursor] in ")]":
        start = open_of.get(cursor)
        if start is None:
            return None
    else:
        start, token = _token_before(text, cursor + 1)
        if not token:
            return None
    return start, text[start : close + 1], close + 1


def _is_declarator_subscript(text: str, base_start: int) -> bool:
    """Whether the name at ``base_start`` is being *declared* as an array.

    ``volatile uint32_t *const regs[1] = { ... }`` gives the array its extent;
    it does not read one of its elements. Counting the declarator's brackets as
    an access invents a load at ``regs + 1`` that the image never performs --
    and once the name is bound to a register, that invented load resolves to
    whatever sits one word past it, which is a rejection with the wrong name.
    """

    cursor = base_start - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return False
    if text[cursor] == "*":
        return _is_declarator_star(text, cursor)
    return _token_before(text, cursor + 1)[1] in _DECLARATOR_TYPES


def _assigns_at(text: str, stop: int) -> bool:
    """Whether an assignment operator, not a comparison, follows ``stop``."""

    tail = _next_non_space(text, stop)
    return tail.startswith("=") and not tail.startswith("==")


def access_expressions(text: str) -> tuple[tuple[int, str, bool], ...]:
    """``(offset, address expression, is_write)`` for every MMIO-shaped access.

    C spells one load two ways. ``*p`` and ``p[0]`` are the same access --
    6.5.2.1 *defines* ``E1[E2]`` as ``(*((E1)+(E2)))`` -- and the subscript is
    commutative, so ``0[p]`` is that load too. Enumerating only the ``*``
    spelling leaves the others invisible to every ordering, counting and
    provenance rule below, which is worse than not seeing the access: a read
    spelled ``status_reg[0]`` satisfies no read-order rule *and* trips none, so
    the manifest keeps asserting a read order the built image does not have.

    The address expression is handed back rather than a role, because the NVIC
    isolation rule folds these same expressions against a different window than
    the NPU register map.
    """

    found: list[tuple[int, str, bool]] = []
    for match in _DEREF_RE.finditer(text):
        if _is_declarator_star(text, match.start()):
            continue
        expression = _expression_after(text, match.end())
        stop = match.end() + len(expression)
        found.append((match.start(), expression, _assigns_at(text, stop)))
    pairs = _bracket_pairs(text)
    for index, character in enumerate(text):
        if character != "[":
            continue
        recovered = _subscript_expression(text, index, pairs)
        if recovered is None:
            continue
        start, expression, stop = recovered
        if _is_declarator_subscript(text, start):
            continue
        # A ``*`` in front of the base already entered this access above, and
        # counting it twice would turn one load into two.
        cursor = start - 1
        while cursor >= 0 and text[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and text[cursor] == "*" and not _is_declarator_star(text, cursor):
            continue
        found.append((start, expression, _assigns_at(text, stop)))
    return tuple(sorted(found))


def dereference_sites(
    text: str, defines: dict[str, int], roles: dict[str, str]
) -> tuple[tuple[int, str, bool], ...]:
    """``(offset, role, is_write)`` for every MMIO access in ``text``."""

    found: list[tuple[int, str, bool]] = []
    for site, expression, is_write in access_expressions(text):
        role = resolve_address_role(expression, defines, roles)
        if role is None:
            continue
        found.append((site, role, is_write))
    return tuple(found)


def register_access_sites(
    text: str,
    register: str,
    defines: dict[str, int],
    roles: dict[str, str] | None = None,
    write: bool = False,
) -> tuple[int, ...]:
    """Every offset in ``text`` that reads or writes ``register``, any spelling."""

    if roles is None:
        roles = pointer_roles(text, defines)
    verb = "write_reg" if write else "read_reg"
    sites = set(
        code_positions(text, "%s(NPU_REG_%s" % (verb, register), open_end=(register == "QBASE"))
    )
    for site, role, is_write in dereference_sites(text, defines, roles):
        if role == register and is_write == write:
            sites.add(site)
    return tuple(sorted(sites))


def cmd_write_values(
    text: str, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[tuple[int, int | None], ...]:
    """``(offset, value)`` for every CMD write; ``value`` is ``None`` when opaque.

    The value is the OR of every constant term, because that is what decides
    whether a write starts the NPU (bit 0), and a term this gate cannot read is
    reported as opaque rather than assumed harmless.
    """

    if roles is None:
        roles = pointer_roles(text, defines)
    found: list[tuple[int, int | None]] = []
    for match in _CMD_VALUE_RE.finditer(text):
        found.append((match.start(), _or_terms(match.group(1), defines)))
    for site, role, is_write in dereference_sites(text, defines, roles):
        if role != "CMD" or not is_write:
            continue
        tail = text[site:]
        assignment = re.search(r"=(?!=)([^;]*);", tail)
        found.append((site, _or_terms(assignment.group(1), defines) if assignment else None))
    return tuple(sorted(found))


def _or_terms(value: str, defines: dict[str, int]) -> int | None:
    resolved = 0
    for term in _split_top_level(value, "|"):
        part = _evaluate_constant(term, defines)
        if part is None:
            return None
        resolved |= part
    return resolved


def submit_write_sites(
    text: str, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[int, ...]:
    """Every CMD write that starts the NPU, whatever spelling sets bit 0."""

    return tuple(
        site for site, value in cmd_write_values(text, defines, roles) if value is None or value & 1
    )


def cmd_write_sites_with_value(
    text: str, wanted: int, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[int, ...]:
    return tuple(site for site, value in cmd_write_values(text, defines, roles) if value == wanted)


def _bindings(text: str) -> tuple[tuple[str, str], ...]:
    """Every ``name = expr`` and every array declarator element in ``text``.

    Both forms hand a name an address, and a walk that knows only the first one
    resolves a dereference of the second to nothing rather than to a register.
    """

    return _assignment_bindings(text) + _declarator_bindings(text)


def _is_pointer_binding(expr: str) -> bool:
    """Whether ``expr`` hands over the storage itself rather than a word of it.

    ``p = mb`` and ``p = &mb[3]`` name the array; ``v = mb[3]`` names the value
    in one of its words, and calling that an alias would make every reader of a
    mailbox word a second name for the mailbox.
    """

    if "&" in expr:
        return True
    return "[" not in expr and not _has_unary_deref(expr)


def _seeded_bindings(
    bindings: tuple[tuple[str, str], ...], dependents: dict[str, list[int]], root: str
) -> list[int]:
    """The binding indices an alias walk from ``root`` has to start at.

    The bindings that mention ``root``, plus every binding whose initializer the
    declarator walk could not flatten. The second half is what keeps the walk
    honest: such a binding may name ``root`` and this gate cannot see that it
    does, and a name it never examines is a second name for the storage that no
    rule downstream covers.
    """

    seeds = list(dependents.get(root, ()))
    seen = set(seeds)
    for index, (_name, expr) in enumerate(bindings):
        if expr == UNRESOLVED_INITIALIZER and index not in seen:
            seeds.append(index)
            seen.add(index)
    return seeds


def obs_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the observation record pointer, transitively."""

    bindings = _bindings(text)
    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    names = {"obs"}
    pending = collections.deque(_seeded_bindings(bindings, dependents, "obs"))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving an observation-record alias did not settle within %d steps: the "
                "source binds more aliases than this gate walks" % budget
            )
        name, expr = bindings[index]
        if name in names:
            continue
        # An initializer this gate could not flatten may name the record, so the
        # name it binds is treated as a second name for it rather than as
        # something the walk is free to ignore.
        if expr != UNRESOLVED_INITIALIZER:
            if _MEMBER_ACCESS_RE.search(expr) is not None:
                continue
            stripped = _strip_address_of(_CAST_RE.sub(" ", expr))
            if not any(token in names for token in _IDENTIFIER_RE.findall(stripped)):
                continue
        names.add(name)
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return tuple(sorted(names - {"obs"}))


def mailbox_alias_words(text: str, defines: dict[str, int]) -> dict[str, object]:
    """Every name bound to the mailbox array, with the word it starts at.

    ``UNRESOLVED_ROLE`` is a displacement nothing here can evaluate -- a name
    bound twice, or bound past the array by arithmetic this gate cannot read.
    That is the fail-closed answer: a second name whose origin is unknown is a
    name no word rule covers.
    """

    def resolve(expr: str, known: dict[str, object]) -> object:
        if not _is_pointer_binding(expr):
            return None
        return resolve_mailbox_word(expr, defines, known)

    resolved = _alias_fixpoint(
        _bindings(text),
        resolve,
        lambda words: sorted(words, key=repr)[0] if len(words) == 1 else UNRESOLVED_ROLE,
        "a mailbox alias",
    )
    return {name: word for name, word in resolved.items() if name != MAILBOX_SYMBOL}


def mailbox_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the failure mailbox array."""

    return tuple(sorted(mailbox_alias_words(text, {})))


def store_pattern(text: str) -> re.Pattern[str]:
    """A store recogniser that also sees ``text``'s obs and mailbox aliases."""

    names = ("obs",) + obs_aliases(text) + (MAILBOX_SYMBOL,) + mailbox_aliases(text)
    return re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % _alternation(names))


def function_spans(masked: str) -> tuple[tuple[str, int, int], ...]:
    """Return ``(name, body_start, body_stop)`` for every top-level brace block."""

    spans: list[tuple[str, int, int]] = []
    index = 0
    declarator_start = 0
    while index < len(masked):
        character = masked[index]
        if character == "{":
            head = masked[declarator_start:index]
            names = _CALL_RE.findall(head)
            close = _matching_brace(masked, index, "top-level block")
            spans.append((names[-1] if names else "", index + 1, close))
            index = close + 1
            declarator_start = index
            continue
        if character == ";":
            declarator_start = index + 1
        index += 1
    return tuple(spans)


def enclosing_block_start(text: str, position: int) -> int:
    """The offset just inside the innermost ``{`` still open at ``position``."""

    stack: list[int] = []
    for index in range(min(position, len(text))):
        character = text[index]
        if character == "{":
            stack.append(index + 1)
        elif character == "}" and stack:
            stack.pop()
    return stack[-1] if stack else 0


def enclosing_function(spans: tuple[tuple[str, int, int], ...], position: int) -> str:
    for name, start, stop in spans:
        if start <= position < stop:
            return name
    return ""


def split_block(block: str) -> tuple[tuple[str, str, str], ...]:
    """Split a compound statement into ``(kind, head, body)`` items."""

    items: list[tuple[str, str, str]] = []
    buffer: list[str] = []
    paren = 0
    index = 0
    while index < len(block):
        character = block[index]
        if character == "(":
            paren += 1
        elif character == ")":
            paren -= 1
        if paren == 0 and character == ";":
            items.append(("stmt", "".join(buffer).strip(), ""))
            buffer = []
            index += 1
            continue
        if paren == 0 and character == "{":
            close = _matching_brace(block, index, "nested block")
            items.append(("block", "".join(buffer).strip(), block[index + 1 : close]))
            buffer = []
            index = close + 1
            continue
        buffer.append(character)
        index += 1
    trailing = "".join(buffer).strip()
    if trailing:
        items.append(("stmt", trailing, ""))
    return tuple(items)


def statement_effects(
    statement: str,
    roles: dict[str, str],
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> tuple[str, ...]:
    effects: list[str] = []
    resolved = defines if defines is not None else {}
    for _site, role, _is_write in dereference_sites(statement, resolved, roles):
        effects.append("qsize" if role == "QSIZE" else "load:%s" % role)
    already_loaded = {effect.split(":", 1)[1] for effect in effects if effect.startswith("load:")}
    for register in _RAW_REGISTER_RE.findall(statement):
        if register == "QSIZE":
            if "qsize" not in effects:
                effects.append("qsize")
        elif register not in already_loaded:
            effects.append("load:%s" % register)
            already_loaded.add(register)
    if code_contains(statement, "DWT->CYCCNT"):
        effects.append("timestamp")
    if store_re.search(statement):
        effects.append("store")
    for callee in _CALL_RE.findall(statement):
        if callee not in _NON_CALL_KEYWORDS and callee not in roles:
            effects.append("call:%s" % callee)
    return tuple(effects)


def extract_loop(body: str, what: str) -> tuple[str, str, int, int]:
    """Return ``(loop_head, loop_body, body_start, body_stop)`` of the single ``for``."""

    heads = [match for match in re.finditer(r"(?<![A-Za-z0-9_])for\s*\(", body)]
    if len(heads) != 1:
        raise fail("%s: expected exactly one loop, found %d" % (what, len(heads)))
    match = heads[0]
    depth = 0
    index = match.end() - 1
    while index < len(body):
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    head = body[match.end() : index]
    tail = body[index + 1 :]
    stripped = tail.lstrip()
    if not stripped.startswith("{"):
        raise fail("%s: loop body is not a compound statement" % what)
    open_index = index + 1 + (len(tail) - len(stripped))
    close_index = _matching_brace(body, open_index, what)
    return head, body[open_index + 1 : close_index], open_index + 1, close_index


def _split_top_level(text: str, separator: str) -> tuple[str, ...]:
    """Split ``text`` on ``separator`` at paren depth zero."""

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for character in text:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and character == separator:
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(character)
    parts.append("".join(buffer))
    return tuple(parts)
