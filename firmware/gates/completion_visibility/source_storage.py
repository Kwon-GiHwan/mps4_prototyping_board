"""Successor completion-visibility checker: source storage."""

from __future__ import annotations

import collections
import functools
import re

from .constants import (
    APPENDIX_FIELDS,
    APPENDIX_PRODUCERS,
    APPENDIX_WORDS,
    BODY_WORDS,
    BUILD_ID,
    CONVERGE_SYMBOL,
    MAILBOX_PUBLISH_SYMBOL,
    MAILBOX_RESET_SYMBOL,
    MAILBOX_SYMBOL,
    MAILBOX_VALID,
    MEASURED_CALL,
    OBSERVATION_FIELDS,
    OBSERVATION_PRODUCERS,
    OBSERVATION_PUBLISH_SYMBOL,
    OBSERVATION_TYPE,
    PAYLOAD_BYTES,
    PRIMARY_SYMBOL,
    RECORD_SYMBOL,
    RUNNER_STOCK_FUNCTION_POINTERS,
    SCHEMA_VERSION,
    TOTAL_WORDS,
    U32_INVALID,
    UNRESOLVED_INITIALIZER,
    UNRESOLVED_ROLE,
    VARIANTS,
    _ALIAS_BUDGET_FACTOR,
    _ALIAS_BUDGET_FLOOR,
    _ASSIGNMENT_BOUNDARY,
    _CALLABLE_END,
    _CAST_RE,
    _CONVERGENCE_TUPLE,
    _C_TOKEN_RE,
    _DECLARATOR_TAIL_RE,
    _EXPRESSION_KEYWORDS,
    _FAILURE_TUPLE,
    _FIRST_TUPLE_FIELDS,
    _FROZEN_INDEX_RE,
    _FUNCTION_POINTER_DECLARATOR_RE,
    _IDENTIFIER_RE,
    _INDEX_RE,
    _INLINE_SPACE,
    _MAILBOX_DECL_RE,
    _MEMBER_ACCESS_RE,
    _NAME_CHARACTER_RE,
    _NON_CALL_KEYWORDS,
    _OBSERVATION_DECL_RE,
    _OPERAND_END_CHARACTERS,
    _POINTER_OBJECT_CALL_REFUSAL,
    _POSTFIX_OPERAND_RE,
    _RECORD_FIELD_RE,
    _SERIALIZE_RE,
    _TYPEDEF_DECLARATION_RE,
    _TYPEDEF_RE,
    _TYPE_NAME_TOKEN_RE,
)

from .errors import (
    fail,
)

from .c_lexical import (
    _matching_brace,
    code_contains,
    code_find,
    function_text,
    names_identifier,
    parse_define_values,
)

from .c_addresses import (
    _binding_dependents,
    _bindings,
    _bracket_pairs,
    _evaluate_constant,
    _is_declaration,
    _is_declarator_star,
    _seeded_bindings,
    _split_top_level,
    _strip_address_of,
    _token_before,
    assignment_statements,
    blank_directives,
    compound_assignment_lvalues,
    compound_assignment_targets,
    enclosing_function,
    function_spans,
    mailbox_alias_words,
    obs_aliases,
    resolve_mailbox_word,
)


def _mbox_macro(field: str) -> str:
    return "V14_MBOX_" + field.upper()


def _word(field: str) -> int:
    return APPENDIX_FIELDS.index(field)


def _mailbox_words_stored(
    block: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[object, str], ...]:
    """``(word, value)`` for every mailbox store in ``block``, in source order."""

    return tuple((word, value) for word, _token, value, _start in mailbox_stores(block, defines, known))


def _publication_words(
    block: str, defines: dict[str, int], known: dict[str, object], what: str
) -> dict[object, str]:
    """The one value each appendix word receives in a publication helper.

    A helper that writes the same word twice is refused rather than reduced to
    whichever store the reader happens to look at: a second store is exactly how
    a tuple the first store invalidated comes back as evidence.
    """

    resolved: dict[object, str] = {}
    for word, _token, value, _start in mailbox_stores(block, defines, known):
        if word == UNRESOLVED_ROLE:
            raise fail("%s stores into the mailbox at an offset this gate cannot resolve" % what)
        if word in resolved:
            raise fail("%s publishes appendix word %s from more than one store" % (what, word))
        resolved[word] = value
    return resolved


def mailbox_stores(
    block: str, defines: dict[str, int], known: dict[str, object] | None = None
) -> tuple[tuple[object, str, str, int], ...]:
    """``(word, index_token, value, start)`` for every store into the mailbox.

    The lvalue is resolved rather than pattern-matched, so the subscript, the
    reversed subscript C also accepts, a dereference of pointer arithmetic and
    an alias of the array all arrive at the same word. ``index_token`` is the
    text between the brackets when -- and only when -- the store is written in
    the frozen ``symbol[macro]`` spelling, so the *spelling* stays judged
    separately from the *word* the callers below need.
    """

    resolved = mailbox_alias_words(block, defines) if known is None else known
    stores: list[tuple[object, str, str, int]] = []
    for start, lvalue, rvalue in assignment_statements(block):
        if _is_declaration(lvalue):
            continue
        word = resolve_mailbox_word(lvalue, defines, resolved)
        if word is None:
            continue
        frozen = _FROZEN_INDEX_RE.match(lvalue)
        index_token = frozen.group(1) if frozen else re.sub(r"\s+", " ", lvalue.strip())
        stores.append((word, index_token, rvalue.strip(), start))
    return tuple(stores)


def require_mailbox_provenance(text: str, defines: dict[str, int], what: str) -> dict[str, object]:
    """Resolve the mailbox aliases of ``text``, refusing the ones nothing can pin.

    A name whose displacement from the array is unknown, and a name the source
    re-points with ``+=`` or ``++``, are both names no word rule covers. They
    are refused here rather than resolved to whichever word they happened to
    start at.

    A read-modify-write on an addressed *word* is refused for a different
    reason. Every publication rule in this file is written over the one value a
    word receives, so ``mailbox[V14_MBOX_VARIANT_ID] += 2U`` after the frozen
    variant-id store leaves the gate reporting the store it proved and the
    image publishing a different number -- exactly the mis-attributed frame
    ``verify_variant_identity`` exists to prevent, and the same for the magic
    that declares the other 33 words real. The mailbox is write-once per word,
    so an operator that also reads it back is refused whatever spelling reaches
    the word.
    """

    aliases = mailbox_alias_words(text, defines)
    unresolved = sorted(name for name, word in aliases.items() if word == UNRESOLVED_ROLE)
    if unresolved:
        raise fail(
            "%s binds a mailbox alias this gate cannot resolve to one appendix word: %s"
            % (what, ", ".join(unresolved))
        )
    stepped = compound_assignment_targets(text, (MAILBOX_SYMBOL,) + tuple(sorted(aliases)))
    if stepped:
        raise fail(
            "%s re-points mailbox storage through a compound assignment or an increment: %s"
            % (what, ", ".join(stepped))
        )
    for start, lvalue in compound_assignment_lvalues(text):
        if resolve_mailbox_word(lvalue, defines, aliases) is None:
            continue
        raise fail(
            "%s mutates a published mailbox word through a read-modify-write at offset %d: %s"
            % (what, start, re.sub(r"\s+", " ", lvalue.strip())[:40])
        )
    return aliases


def require_no_record_read_modify_write(masked: str, what: str) -> None:
    """Refuse a read-modify-write on an observation record, in any function.

    The record is what the primary loop freezes and the publication helpers
    copy into the appendix, so a ``obs->result |= 1U`` between the freeze and
    the copy rewrites a published field without ever appearing as a second
    store. Each function resolves its own aliases, because ``obs`` is a
    parameter and a second name for it is local to the body that binds it.
    """

    for name, start, stop in function_spans(masked):
        body = masked[start:stop]
        names = ("obs",) + obs_aliases(body)
        for offset, lvalue in compound_assignment_lvalues(body):
            if not any(names_identifier(lvalue, alias) for alias in names):
                continue
            raise fail(
                "%s mutates a frozen observation field through a read-modify-write in %s: %s"
                % (what, name or "<file scope>", re.sub(r"\s+", " ", lvalue.strip())[:40])
            )


def address_of_operands(text: str) -> tuple[tuple[int, str], ...]:
    """``(site, operand)`` for every *unary* ``&`` in ``text``.

    Unary is decided the way ``_strip_address_of`` decides it -- nothing that
    can end an operand precedes it -- so ``base & mask`` is left alone and
    ``&d.variant_id`` is not.
    """

    found: list[tuple[int, str]] = []
    previous = ""
    for index, character in enumerate(text):
        if character in _INLINE_SPACE:
            continue
        if character == "&" and not (
            previous
            and (previous in _OPERAND_END_CHARACTERS or _NAME_CHARACTER_RE.match(previous))
        ):
            match = _POSTFIX_OPERAND_RE.match(text, index + 1)
            if match is not None:
                found.append((index, match.group(0).strip()))
            previous = "&"
            continue
        previous = character
    return tuple(found)


def enclosing_calls(text: str, offsets: frozenset) -> dict[int, str]:
    """The innermost callee whose argument list encloses each wanted offset.

    Walked once with an explicit stack rather than by matching each call's
    parenthesis on demand: an unterminated ``(`` makes every on-demand match
    rescan to the end of the text, which is the quadratic ``_bracket_pairs``
    already exists to avoid.
    """

    enclosing: dict[int, str] = {}
    stack: list[str] = []
    for index, character in enumerate(text):
        if character == "(":
            _start, name = _token_before(text, index)
            stack.append("" if name in _NON_CALL_KEYWORDS else name)
        elif character == ")":
            if stack:
                stack.pop()
        elif index in offsets and stack:
            enclosing[index] = stack[-1]
    return enclosing


def _member_base_follows(text: str, index: int) -> bool:
    """Whether the name ending at ``index`` is the base of a member access."""

    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    if text[cursor : cursor + 2] == "->":
        return True
    return text[cursor : cursor + 1] == "." and text[cursor + 1 : cursor + 2] != "."


def _is_whole_rvalue(text: str, start: int, stop: int) -> bool:
    """Whether ``text[start:stop]`` is the entire right-hand side of a copy."""

    cursor = start - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if text[cursor : cursor + 1] != "=" or text[cursor - 1 : cursor] in _ASSIGNMENT_BOUNDARY:
        return False
    cursor = stop
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    return text[cursor : cursor + 1] == ";"


def require_record_storage_closed(runner_masked: str, window: tuple[int, int]) -> None:
    """Bound every way the serialized record's storage can be reached.

    ``verify_runner_contract`` proves the 34 appendix fields are written exactly
    once, inside the magic branch, from the word the wire order gives them. It
    proves that over *lvalues it can resolve to the record*, and ``_record_member``
    only resolves an lvalue whose last token follows a ``.`` or a ``->``. A write
    that names no member is therefore neither proven nor refused, and three of
    them reach the same storage:

        { uint32_t *pf = &d.variant_id; *pf = 3U; }
        memset(&d.variant_id, 0, 34U * 4U);
        { uint32_t z = 3U; memcpy(&d.variant_id, &z, sizeof z); }

    Each one rewrites a published field while the manifest still reports the 34
    proven copies. They are answered here the way ``verify_hard_bypass_contract``
    answers ``&irq_triggered`` -- by refusing the *address*, which is the one
    token all three share:

    * the address of an appendix field is refused wherever it is taken, because
      the design never takes one and a pointer to a field is a write to that
      field this gate cannot see; and
    * inside the window the write-once proof covers -- from the end of the
      magic branch to the end of the function that owns the record -- the record
      and its aliases may only be the base of a member access or the whole
      right-hand side of a copy, so ``memset(&d, ...)``, a cast of the record to
      a byte pointer, and handing it to any call are all refused.

    Outside that window the record is not yet the transport: it is zeroed and
    its frozen v7/v8 snapshot fields are filled by address, which is why the
    second rule is bounded to the window and the first one is not.
    """

    aliases = frozenset(record_aliases(runner_masked))
    names = aliases | {RECORD_SYMBOL}
    appendix = frozenset(APPENDIX_FIELDS)
    for site, operand in address_of_operands(runner_masked):
        field = _record_field_target(operand, aliases)
        if field in appendix:
            raise fail(
                "the runner takes the address of the appendix field %s at offset %d: a write "
                "through it is a write the record's write-once proof cannot see" % (field, site)
            )
    start, stop = window
    for match in _IDENTIFIER_RE.finditer(runner_masked, start, stop):
        if match.group(0) not in names:
            continue
        if _member_base_follows(runner_masked, match.end()):
            continue
        if _is_whole_rvalue(runner_masked, match.start(), match.end()):
            continue
        raise fail(
            "the runner reaches the serialized record as whole storage at offset %d, after the "
            "magic-gated appendix copy: %s is neither a member access nor a copy of the record"
            % (match.start(), match.group(0))
        )


def _observation_value_key(value: str, defines: dict[str, int]) -> str:
    """What a stored value *is*, over every spelling that produces it.

    A value that folds to a constant is compared as that constant, so
    ``V14_PRIMARY_OBSERVED``, ``(V14_PRIMARY_OBSERVED)`` and
    ``V14_PRIMARY_OBSERVED + 0U`` are one value here -- the same reading
    ``is_magic_value`` already gives the mailbox magic. What does not fold is a
    local or a register read, and those are compared as the tokens they are.
    """

    folded = _evaluate_constant(value, defines)
    if folded is not None:
        return "0x%08X" % (folded & 0xFFFFFFFF)
    return re.sub(r"\s+", " ", value.strip())


def _observation_text(published: dict[str, tuple[str, ...]]) -> str:
    return (
        ", ".join(
            "%s=[%s]" % (field, ", ".join(values))
            for field, values in sorted(published.items())
        )
        or "no store"
    )

def _observation_field_target(lvalue: str, names: frozenset) -> str | None:
    """The observation field ``lvalue`` designates, or ``None`` for other storage."""

    member = _record_member(lvalue)
    if member is None:
        return None
    head, field = member
    base = _INDEX_RE.sub(" ", _strip_address_of(_CAST_RE.sub(" ", head)))
    mentioned = set(_IDENTIFIER_RE.findall(base))
    if not mentioned or mentioned - names:
        return None
    return field


def observation_record_names(vendor_masked: str) -> frozenset:
    """Every name declared as an observation record or a pointer to one."""

    return frozenset(_OBSERVATION_DECL_RE.findall(vendor_masked))


def verify_observation_contract(
    vendor_masked: str, variant: str, defines: dict[str, int]
) -> None:
    """Refuse an observation record written anywhere the design does not write it.

    The mailbox half of this proof is ``require_authorized_appendix_producers``.
    This is the same proof one hop upstream, and it is made the same way: the
    sites and counts are a contract table, an lvalue that names an observation
    field through a base this gate cannot bind is refused rather than passed
    over, and the record's address is bounded so a write that names no field at
    all -- an alias, a field pointer, a ``memcpy`` -- cannot reach the storage
    behind the table's back.
    """

    declared = observation_record_names(vendor_masked)
    if not declared:
        raise fail("the vendor translation unit declares no %s record" % OBSERVATION_TYPE)
    fields = frozenset(OBSERVATION_FIELDS)
    authorized = OBSERVATION_PRODUCERS[variant]
    for owner, start, stop in function_spans(vendor_masked):
        body = vendor_masked[start:stop]
        names = declared | frozenset(obs_aliases(body))
        published: dict[str, list[str]] = {}
        for site, lvalue, rvalue in assignment_statements(body):
            if _is_declaration(lvalue):
                continue
            member = _record_member(lvalue)
            if member is None or member[1] not in fields:
                continue
            field = _observation_field_target(lvalue, names)
            if field is None:
                raise fail(
                    "%s writes the observation field %s through an lvalue this gate cannot bind "
                    "to an observation record at offset %d: %s"
                    % (
                        owner or "<file scope>",
                        member[1],
                        start + site,
                        re.sub(r"\s+", " ", lvalue.strip())[:40],
                    )
                )
            published.setdefault(field, []).append(
                _observation_value_key(rvalue, defines)
            )
        observed = {field: tuple(sorted(values)) for field, values in published.items()}
        expected = {
            field: tuple(sorted(_observation_value_key(value, defines) for value in values))
            for field, values in authorized.get(owner, {}).items()
        }
        if observed != expected:
            raise fail(
                "the observation record is not published by its authorized producers in %s: "
                "found %s, expected %s"
                % (owner or "<file scope>", _observation_text(observed), _observation_text(expected))
            )

    consumers = frozenset((PRIMARY_SYMBOL[variant], CONVERGE_SYMBOL, OBSERVATION_PUBLISH_SYMBOL))
    for site, operand in address_of_operands(vendor_masked):
        field = _observation_field_target(operand, declared)
        if field in fields:
            raise fail(
                "the vendor translation unit takes the address of the observation field %s at "
                "offset %d: a write through it is a write the producer table cannot see"
                % (field, site)
            )
    # What is left is the record taken *whole*. It is the argument of the three
    # helpers the design gives it and nothing else: bound to a second name, cast,
    # or handed to any other call, it is storage this gate stops being able to
    # account for.
    exempt = set()
    for match in _OBSERVATION_DECL_RE.finditer(vendor_masked):
        exempt.update(range(match.start(1), match.end(1)))
    wanted = {
        match.start(): match
        for match in _IDENTIFIER_RE.finditer(vendor_masked)
        if match.group(0) in declared
        and match.start() not in exempt
        and not _member_base_follows(vendor_masked, match.end())
    }
    enclosing = enclosing_calls(vendor_masked, frozenset(wanted))
    for offset, match in sorted(wanted.items()):
        if enclosing.get(offset) in consumers:
            continue
        raise fail(
            "the vendor translation unit reaches an observation record as whole storage at "
            "offset %d: %s is neither a member access nor an argument of %s"
            % (offset, match.group(0), ", ".join(sorted(consumers)))
        )


def is_magic_value(value: str, defines: dict[str, int]) -> bool:
    """Whether a stored value *is* the 0x5631344D magic, over every spelling.

    The magic is what tells a reader the other 33 words are real, so what
    matters is the number the compiler stores and not the text that produces it.
    ``V14_MAILBOX_VALID + 0U``, ``(V14_MAILBOX_VALID)`` and ``0x5631344DU | 0U``
    all store it, and a count keyed on the bare macro or the bare literal misses
    each of them -- which leaves the "published from more than one site"
    rejection unreachable and lets a second, earlier, unearned magic hand the
    runner a valid-looking frame full of reset sentinels.

    The evaluator this file already trusts for CMD values and NVIC addresses is
    the one that answers here. The two text cases are kept as the fast path.
    """

    token = value.strip()
    if token in defines:
        return defines[token] == MAILBOX_VALID
    try:
        return int(token.rstrip("uU"), 0) == MAILBOX_VALID
    except ValueError:
        pass
    folded = _evaluate_constant(token, defines)
    return folded is not None and (folded & 0xFFFFFFFF) == MAILBOX_VALID


def _resolved_mailbox_stores(
    vendor_masked: str, defines: dict[str, int], known: dict[str, object] | None = None
) -> tuple[tuple[object, str, str, str], ...]:
    """``(word, index_token, value, owner)`` for every mailbox store, aliases included."""

    spans = function_spans(vendor_masked)
    return tuple(
        (word, index_token, value, enclosing_function(spans, start))
        for word, index_token, value, start in mailbox_stores(vendor_masked, defines, known)
    )


def verify_variant_identity(
    vendor_masked: str, defines: dict[str, int], variant: str
) -> dict[str, object]:
    """Bind ``V14_VARIANT_ID`` to the selected variant and to appendix word 0.

    Word 0 is the only thing a decoder has to tell a Q frame from an SQ one, so
    a frame that publishes the wrong id, no id, or an id that never reaches
    word 0 is a frame whose every other field is attributed to the wrong
    experiment. The publication is required in the frozen spelling: an alias
    store is not refused because it would fail, but because nothing here can
    prove it is the same array.
    """

    expected = VARIANTS[variant]
    if defines.get("V14_VARIANT_ID") != expected:
        raise fail(
            "variant id define is not the selected variant: V14_VARIANT_ID is %s, expected %d"
            % (
                "undefined" if "V14_VARIANT_ID" not in defines else str(defines["V14_VARIANT_ID"]),
                expected,
            )
        )

    aliases = require_mailbox_provenance(vendor_masked, defines, "the vendor translation unit")
    stores = _resolved_mailbox_stores(vendor_masked, defines, aliases)
    word_zero = [store for store in stores if store[0] == 0]
    misplaced = [store for store in stores if store[0] != 0 and store[2] == "V14_VARIANT_ID"]
    if len(word_zero) != 1:
        raise fail(
            "variant id is not published to mailbox word 0: %d stores address word 0"
            % len(word_zero)
        )
    word, index_token, value, _owner = word_zero[0]
    if value != "V14_VARIANT_ID":
        raise fail("mailbox word 0 does not publish V14_VARIANT_ID: it stores %s" % value)
    if misplaced:
        raise fail(
            "variant id is published to appendix word %s rather than word 0" % (misplaced[0][0],)
        )

    direct = re.search(
        r"(?<![A-Za-z0-9_])%s\s*\[\s*%s\s*\]\s*=\s*V14_VARIANT_ID\s*;"
        % (re.escape(MAILBOX_SYMBOL), re.escape(_mbox_macro("variant_id"))),
        vendor_masked,
    )
    if direct is None:
        raise fail(
            "variant id is published through a mailbox alias or a raw index rather than "
            "%s[%s]" % (MAILBOX_SYMBOL, _mbox_macro("variant_id"))
        )
    return {
        "variant_id_word": 0,
        "variant_id_publication": "%s[%s] = V14_VARIANT_ID"
        % (MAILBOX_SYMBOL, _mbox_macro("variant_id")),
        "variant_id_define": defines["V14_VARIANT_ID"],
    }


def verify_mailbox_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the exact 34-word mailbox, its reset, and its magic-last publication."""

    declarations = _MAILBOX_DECL_RE.findall(vendor_masked)
    if declarations != [str(APPENDIX_WORDS)]:
        raise fail("mailbox storage is not a 34-word array: found %s" % (declarations or ["no declaration"]))

    for index, field in enumerate(APPENDIX_FIELDS):
        macro = _mbox_macro(field)
        if defines.get(macro) != index:
            raise fail(
                "appendix offset table does not match the schema-14 wire order: %s is %r, expected %d"
                % (macro, defines.get(macro), index)
            )
    if defines.get("V14_APPENDIX_WORDS") != APPENDIX_WORDS:
        raise fail("appendix offset table does not match the schema-14 wire order: V14_APPENDIX_WORDS drifted")
    if defines.get("V14_MAILBOX_VALID") != MAILBOX_VALID:
        raise fail("mailbox magic is not 0x5631344D")
    if defines.get("V14_U32_INVALID") != U32_INVALID:
        raise fail("invalid sentinel is not 0xFFFFFFFF")

    aliases = require_mailbox_provenance(vendor_masked, defines, "the vendor translation unit")
    require_no_record_read_modify_write(vendor_masked, "the vendor translation unit")

    valid_word = APPENDIX_FIELDS.index("mailbox_valid")
    reset = function_text(vendor_masked, MAILBOX_RESET_SYMBOL, "mailbox reset entry")
    if not names_identifier(reset, "V14_U32_INVALID") or not names_identifier(
        reset, "V14_APPENDIX_WORDS"
    ):
        raise fail("mailbox reset does not invalidate every appendix field")
    reset_stores = _mailbox_words_stored(reset, defines, aliases)
    if (valid_word, "0U") not in reset_stores:
        raise fail("mailbox reset does not zero mailbox_valid")
    if reset_stores[-1] != (valid_word, "0U"):
        raise fail("mailbox reset does not zero mailbox_valid last")
    if not code_contains(reset, "__DSB()"):
        raise fail("mailbox reset does not issue a DSB")

    publish = function_text(vendor_masked, MAILBOX_PUBLISH_SYMBOL, "mailbox publication entry")
    publish_stores = mailbox_stores(publish, defines, aliases)
    if len(publish_stores) != 1 or publish_stores[0][0] != valid_word or not is_magic_value(
        publish_stores[0][2], defines
    ):
        raise fail(
            "mailbox magic is not the final appendix store: publication stores %s"
            % ([(store[0], store[2]) for store in publish_stores],)
        )
    if not code_contains(publish[publish_stores[0][3] :], "__DSB()"):
        raise fail("mailbox publication does not issue a DSB")

    # The magic is what tells a reader the other 33 words are real, so it is
    # counted by *value* over every spelling a store can take: the frozen macro
    # or the bare 0x5631344D, the frozen symbol or an alias of it, the offset
    # macro or its numeric 33. Counting the macro text alone leaves three ways
    # to publish a second, earlier, unearned magic.
    resolved_stores = _resolved_mailbox_stores(vendor_masked, defines, aliases)
    magic_stores = [store for store in resolved_stores if is_magic_value(store[2], defines)]
    if len(magic_stores) != 1:
        raise fail(
            "mailbox_valid is published from more than one site: %d stores" % len(magic_stores)
        )
    word, index_token, value, owner = magic_stores[0]
    if word != valid_word:
        raise fail("mailbox magic is not stored at appendix word 33: it lands on word %s" % word)
    if owner != MAILBOX_PUBLISH_SYMBOL:
        raise fail(
            "mailbox magic is published outside %s: stored in %s"
            % (MAILBOX_PUBLISH_SYMBOL, owner or "<file scope>")
        )
    if (index_token, value) != (_mbox_macro("mailbox_valid"), "V14_MAILBOX_VALID"):
        raise fail(
            "mailbox magic is published through an alias or a raw index rather than "
            "%s[%s] = V14_MAILBOX_VALID" % (MAILBOX_SYMBOL, _mbox_macro("mailbox_valid"))
        )

    failure = function_text(vendor_masked, "v14_publish_failure", "failure publication")
    failure_stores = _publication_words(failure, defines, aliases, "the failure publication")
    for field in _CONVERGENCE_TUPLE:
        if failure_stores.get(_word(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a failure" % field)
    for field in _FIRST_TUPLE_FIELDS:
        if _word(field) in failure_stores:
            raise fail("convergence failure discards the retained first-observation tuple: %s" % field)

    success = function_text(vendor_masked, "v14_publish_success", "success publication")
    success_stores = _publication_words(success, defines, aliases, "the success publication")
    for field in _FAILURE_TUPLE:
        if success_stores.get(_word(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a success" % field)
    if success_stores.get(_word("failure_phase")) != "V14_PHASE_NONE":
        raise fail("success and failure tuples are both published as valid: failure_phase is not NONE")

    cleanup = function_text(vendor_masked, "v14_publish_cleanup_failure", "cleanup publication")
    cleanup_stores = _publication_words(cleanup, defines, aliases, "the cleanup publication")
    if cleanup_stores.get(_word("failure_phase")) != "V14_PHASE_CLEANUP":
        raise fail("cleanup invariant is not recorded as failure_phase=CLEANUP")
    for field in _CONVERGENCE_TUPLE:
        if _word(field) in cleanup_stores:
            raise fail("cleanup invariant discards the convergence tuple: %s" % field)

    first_words = {_word(field) for field in _FIRST_TUPLE_FIELDS}
    for word, index_token, _value, owner in resolved_stores:
        if word not in first_words:
            continue
        if owner != "v14_publish_primary":
            raise fail(
                "first-observation STATUS fields are synthesized from convergence values: %s stored in %s"
                % (index_token, owner or "<file scope>")
            )

    return {
        "mailbox_symbol": MAILBOX_SYMBOL,
        "mailbox_words": APPENDIX_WORDS,
        "mailbox_reset_entry": MAILBOX_RESET_SYMBOL,
        "mailbox_magic_store_index": APPENDIX_FIELDS.index("mailbox_valid"),
        "mailbox_magic": "0x%08X" % MAILBOX_VALID,
        "failure_publication_invalidates": list(_CONVERGENCE_TUPLE),
        "success_publication_invalidates": list(_FAILURE_TUPLE),
        "cleanup_publication_retains": list(_CONVERGENCE_TUPLE),
    }


def require_every_appendix_word_produced(vendor_masked: str, defines: dict[str, int]) -> int:
    """Refuse a frame whose appendix carries a word nothing ever stores.

    A word no store reaches carries the reset sentinel into the published frame,
    and every other rule in this file is written over the stores that *do*
    exist -- so deleting a publication, commenting it out, or splicing a comment
    over it leaves this gate with nothing to object to and a decoder with
    0xFFFFFFFF where the contract promised an observation. Fail-silent is still
    a false manifest: the appendix table is published as the frame's contents,
    so every word in it has to have a producer.

    This runs after every other contract, so a source that breaks a *specific*
    rule is still named by that rule. Reaching here means the store is simply
    absent, which no other rule is written to see. The reset is excluded because
    it writes the sentinel rather than an observation.
    """

    aliases = mailbox_alias_words(vendor_masked, defines)
    produced = {
        word
        for word, _token, _value, owner in _resolved_mailbox_stores(vendor_masked, defines, aliases)
        if owner != MAILBOX_RESET_SYMBOL and isinstance(word, int)
    }
    missing = [index for index in range(APPENDIX_WORDS) if index not in produced]
    if missing:
        raise fail(
            "appendix word %d (%s) has no store outside the mailbox reset: it can only carry the "
            "invalid sentinel" % (missing[0], APPENDIX_FIELDS[missing[0]])
        )
    return len(produced)


def _producer_text(producers: dict[str, int]) -> str:
    return ", ".join("%s x%d" % (owner, count) for owner, count in sorted(producers.items()))


def require_authorized_appendix_producers(
    vendor_masked: str, defines: dict[str, int]
) -> int:
    """Refuse an appendix word written anywhere the design does not write it.

    ``require_every_appendix_word_produced`` answers "does this word have a
    producer at all", which is the fail-silent direction. This answers "are its
    producers the ones the design gives it", which is the fail-*open* one: a word
    can carry every proof this file makes about it and still be overwritten by a
    second store one line later.

    The mailbox reset is excluded because it writes the sentinel to every word
    rather than an observation. A store this gate cannot pin to a word is refused
    outright: the reset's loop-indexed sentinel store is the only one the frozen
    sources carry, and it is the reset's.
    """

    aliases = mailbox_alias_words(vendor_masked, defines)
    observed: dict[object, dict[str, int]] = {}
    for word, _token, _value, owner in _resolved_mailbox_stores(
        vendor_masked, defines, aliases
    ):
        if owner == MAILBOX_RESET_SYMBOL:
            continue
        counts = observed.setdefault(word, {})
        counts[owner] = counts.get(owner, 0) + 1
    for word, counts in sorted(observed.items(), key=repr):
        if isinstance(word, int) and 0 <= word < APPENDIX_WORDS:
            continue
        raise fail(
            "the vendor translation unit stores outside the 34-word appendix at word %s: %s"
            % (word, _producer_text(counts))
        )
    for index in range(APPENDIX_WORDS):
        authorized = dict(APPENDIX_PRODUCERS[index])
        found = observed.get(index, {})
        if found != authorized:
            raise fail(
                "appendix word %d (%s) is not published by its authorized producers: found "
                "%s, expected %s"
                % (
                    index,
                    APPENDIX_FIELDS[index],
                    _producer_text(found) or "no store outside the mailbox reset",
                    _producer_text(authorized),
                )
            )
    return sum(sum(counts.values()) for counts in observed.values())


def _record_member(lvalue: str) -> tuple[str, str] | None:
    """``(base, field)`` for the last member access an lvalue makes, or ``None``.

    ``d.variant_id``, ``(&d)->variant_id``, ``alias->variant_id`` and
    ``array[0]->variant_id`` all designate one field of one record, and a rule
    written over the ``d.<field>`` spelling holds for exactly the first of them.
    Read as a bounded scan back from the end rather than as a backtracking
    pattern, because an lvalue is a whole statement's worth of text here and a
    non-greedy head would try every split point in it.
    """

    tail = lvalue.rstrip()
    stop = len(tail)
    cursor = stop
    while cursor > 0 and _NAME_CHARACTER_RE.match(tail[cursor - 1]):
        cursor -= 1
    field = tail[cursor:stop]
    if not field or field[0].isdigit():
        return None
    head = tail[:cursor].rstrip()
    if head.endswith("->"):
        return head[:-2], field
    if head.endswith(".") and not head.endswith(".."):
        return head[:-1], field
    return None


@functools.lru_cache(maxsize=4)
def record_aliases(runner_masked: str) -> tuple[str, ...]:
    """Every name transitively bound to the address of the serialized record.

    A name is an alias when its binding takes the record's address, or when it
    copies a name that already is one. ``last_pmu_diag = d`` is neither -- it is
    a copy of the *value*, and writing through it reaches other storage -- so it
    is not one here either.
    """

    bindings = _bindings(runner_masked)
    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    aliases: set[str] = set()
    pending = collections.deque(_seeded_bindings(bindings, dependents, RECORD_SYMBOL))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving a record alias did not settle within %d steps: the source binds "
                "more aliases than this gate walks" % budget
            )
        name, expr = bindings[index]
        if name == RECORD_SYMBOL or name in aliases:
            continue
        # An initializer this gate could not flatten may take the record's
        # address, so the name it binds is an alias here rather than a name the
        # write-once proof below is free to ignore.
        if expr != UNRESOLVED_INITIALIZER:
            if _MEMBER_ACCESS_RE.search(expr) is not None:
                continue
            stripped = _CAST_RE.sub(" ", expr)
            mentioned = set(_IDENTIFIER_RE.findall(stripped))
            takes_address = "&" in stripped and RECORD_SYMBOL in mentioned
            if not (takes_address or mentioned & aliases):
                continue
        aliases.add(name)
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return tuple(sorted(aliases))


def _record_field_target(lvalue: str, aliases: frozenset) -> str | None:
    """The record field ``lvalue`` designates, or ``None`` when it names another.

    The base is reduced the way every other lvalue in this file is reduced -- the
    casts, the address-of and the subscripts come off -- so what is left is the
    names it reaches. It designates the record exactly when those names are the
    record and its aliases and nothing else.
    """

    member = _record_member(lvalue)
    if member is None:
        return None
    head, field = member
    base = _INDEX_RE.sub(" ", _strip_address_of(_CAST_RE.sub(" ", head)))
    names = set(_IDENTIFIER_RE.findall(base))
    if not names or names - {RECORD_SYMBOL} - aliases:
        return None
    return field


def runner_appendix_copies(
    runner_masked: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[int, str, object], ...]:
    """``(start, field, word)`` for every ``d.<field> = <a mailbox word>`` copy.

    The right-hand side is resolved to the storage it reads rather than matched
    as ``symbol[``, so a copy spelled with pointer arithmetic, a reversed
    subscript or an alias is seen exactly where a subscript one is -- which is
    what makes "the 34 are copied only inside the magic branch" a proof rather
    than a claim about one spelling.

    The resolved *word* is carried out with the field, because the transport is
    a mapping and not a count. Thirty-four copies that all read word 0, or read
    the appendix backwards, are thirty-four copies -- and every field but one
    then carries a value the vendor never published there.
    """

    return tuple(
        (start, field, word)
        for start, field, word in runner_record_stores(runner_masked, defines, known)
        if word is not None
    )


def runner_record_stores(
    runner_masked: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[int, str, object], ...]:
    """``(start, field, word)`` for every ``d.<field> = ...``; ``word`` may be ``None``.

    ``runner_appendix_copies`` keeps only the stores that *read* the mailbox,
    which is what proves the transport. It is not what bounds it: a store whose
    rvalue is a constant, another record field, or anything else this gate does
    not resolve to a word is invisible to a rvalue-keyed walk, so
    ``d.variant_id = 3U`` after the proven copy rewrites a published field and
    the frame still serializes under a manifest that says the 34 words came from
    the mailbox. Every store to the record is recovered here so the caller can
    hold the appendix fields closed between the copy and ``put32``.
    """

    aliases = frozenset(record_aliases(runner_masked))
    found: list[tuple[int, str, object]] = []
    for start, lvalue, rvalue in assignment_statements(runner_masked):
        if _is_declaration(lvalue):
            continue
        field = _record_field_target(lvalue, aliases)
        if field is None:
            continue
        found.append((start, field, resolve_mailbox_word(rvalue, defines, known)))
    return tuple(found)


def require_bindable_record_writes(runner_masked: str) -> None:
    """Refuse a write to an appendix-named field this gate cannot bind to the record.

    ``runner_record_stores`` resolves the lvalues that *do* designate the record.
    This names the ones that do not: a field the appendix owns, written through a
    base nothing here resolves, is either a second name for the record that this
    walk cannot follow or a different object carrying the same field name. Both
    are outside what the write-once proof below covers, so both are refused
    rather than passed over.
    """

    aliases = frozenset(record_aliases(runner_masked))
    appendix = frozenset(APPENDIX_FIELDS)
    lvalues = [(start, lvalue) for start, lvalue, _rvalue in assignment_statements(runner_masked)]
    lvalues.extend(compound_assignment_lvalues(runner_masked))
    for start, lvalue in lvalues:
        if _is_declaration(lvalue):
            continue
        member = _record_member(lvalue)
        if member is None or member[1] not in appendix:
            continue
        if _record_field_target(lvalue, aliases) is None:
            raise fail(
                "the runner writes the appendix field %s through an lvalue this gate cannot "
                "bind to the serialized record at offset %d: %s"
                % (member[1], start, re.sub(r"\s+", " ", lvalue.strip())[:40])
            )


def _contiguous_appendix_run(names: list[str]) -> bool:
    """True when the 34 appendix names form one ordered, non-repeating run.

    The runner keeps its frozen v8 fields around the appendix, so the contract
    is that the appendix words sit together in wire order -- not that they are
    the only fields present.
    """

    if any(names.count(field) != 1 for field in APPENDIX_FIELDS):
        return False
    start = names.index(APPENDIX_FIELDS[0])
    return tuple(names[start : start + APPENDIX_WORDS]) == APPENDIX_FIELDS


def verify_runner_contract(runner_masked: str) -> dict[str, object]:
    """Prove the runner declares schema 14 and copies the mailbox fail-closed."""

    # The runner keeps the frozen v7/v8 branches alongside the V14 one, so a
    # name carries several values here; membership, not the last value, is the
    # question.
    declared = parse_define_values(runner_masked)
    defines = {name: seen[-1] for name, seen in declared.items()}
    if SCHEMA_VERSION not in declared.get("PMU_DIAG_SCHEMA_VERSION", ()):
        raise fail("runner does not declare schema 14")
    if declared.get("PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID") != [BUILD_ID]:
        raise fail("runner does not declare build id 0x34314950")
    for assertion, reason in (
        ("PMU_DIAG_FIELD_COUNT == %dU" % BODY_WORDS, "runner does not statically assert 119 body words"),
        ("PMU_DIAG_TOTAL_WORDS == %dU" % TOTAL_WORDS, "runner does not statically assert 127 frame words"),
        ("PMU_DIAG_PAYLOAD_SIZE == %dU" % PAYLOAD_BYTES, "runner does not statically assert 508 payload bytes"),
        ("PMU_DIAG_SCHEMA_VERSION == %dU" % SCHEMA_VERSION, "runner does not declare schema 14"),
    ):
        if not code_contains(runner_masked, assertion):
            raise fail(reason)

    record_end = code_find(runner_masked, "} pmu_diag_record_t;")
    record_start = runner_masked.rfind("typedef struct", 0, record_end) if record_end >= 0 else -1
    if record_start < 0:
        raise fail("runner record does not carry the 34 appendix fields in wire order: no record found")
    if not _contiguous_appendix_run(_RECORD_FIELD_RE.findall(runner_masked[record_start:record_end])):
        raise fail("runner record does not carry the 34 appendix fields in wire order")

    if not _contiguous_appendix_run(_SERIALIZE_RE.findall(runner_masked)):
        raise fail("runner serialization order does not match the appendix table")

    reset_site = code_find(runner_masked, MAILBOX_RESET_SYMBOL + "();")
    driver_site = code_find(runner_masked[reset_site:], MEASURED_CALL) if reset_site >= 0 else -1
    if reset_site < 0 or driver_site < 0:
        raise fail("runner does not reset the mailbox before the measured call")

    magic_guard = re.search(
        r"if\s*\(\s*%s\s*\[\s*%d\s*\]\s*!=\s*V14_MAILBOX_VALID\s*\)"
        % (re.escape(MAILBOX_SYMBOL), APPENDIX_FIELDS.index("mailbox_valid")),
        runner_masked,
    )
    if magic_guard is None:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    tail_after_guard = code_find(runner_masked[magic_guard.end() :], "else")
    else_site = -1 if tail_after_guard < 0 else magic_guard.end() + tail_after_guard
    if else_site < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    open_index = runner_masked.find("{", else_site)
    if open_index < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    close_index = _matching_brace(runner_masked, open_index, "runner magic else branch")
    aliases = require_mailbox_provenance(runner_masked, defines, "the runner translation unit")
    require_bindable_record_writes(runner_masked)
    record_stores = runner_record_stores(runner_masked, defines, aliases)
    all_copies = tuple(
        (start, field, word) for start, field, word in record_stores if word is not None
    )
    inside = tuple(
        (field, word) for start, field, word in all_copies if open_index <= start < close_index
    )
    copies = tuple(field for field, _word in inside)
    if copies != APPENDIX_FIELDS:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")

    # A count is not a mapping. Thirty-four copies in field order still serialize
    # the wrong frame if every one of them reads word 0, if they read the
    # appendix backwards, or if one reads a word outside the array -- and a word
    # whose index this gate cannot evaluate is a word nothing here can check at
    # all. Each field is therefore bound to the appendix word the wire order
    # gives it, which is the transport half of the same proof the vendor side
    # already carries.
    for index, (field, word) in enumerate(inside):
        if word == UNRESOLVED_ROLE:
            raise fail(
                "runner copies %s from a mailbox offset this gate cannot resolve to one "
                "appendix word" % field
            )
        if not isinstance(word, int) or not 0 <= word < APPENDIX_WORDS:
            raise fail(
                "runner copies %s from outside the 34-word appendix: word %s" % (field, word)
            )
        if word != index:
            raise fail(
                "runner appendix copy does not read the word its field is published in: "
                "%s reads word %s, expected word %d" % (field, word, index)
            )

    # Dominance is not "the valid branch copies all 34"; it is "the 34 are
    # copied *only* there". A copy before the guard runs whatever the magic
    # says, and a copy in the invalid branch publishes reset sentinels -- or
    # stale words from a previous run -- as if they were evidence.
    stray = [
        (start, field)
        for start, field, _word in all_copies
        if not open_index <= start < close_index
    ]
    if stray:
        raise fail(
            "runner copies the appendix outside the mailbox-magic branch: %s copied at %d"
            % (stray[0][1], stray[0][0])
        )

    # Proving where the 34 words come *from* does not prove what is serialized.
    # Between the copy and ``put32`` the record is ordinary memory, and
    # ``d.variant_id = 3U``, ``d.first_qread |= 0x80000000U`` or a two-field swap
    # each rewrite a published field without ever reading the mailbox -- so the
    # rvalue-keyed walk above never sees them and the frame goes out with the
    # manifest still asserting ``runner_appendix_source_words == range(34)``.
    # The appendix half of the record is therefore write-once: exactly the 34
    # proven copies, and nothing after them.
    appendix_fields = frozenset(APPENDIX_FIELDS)
    outside = [
        (start, field)
        for start, field, _word in record_stores
        if field in appendix_fields and not open_index <= start < close_index
    ]
    if outside:
        raise fail(
            "runner rewrites a copied appendix field outside the mailbox-magic branch: "
            "%s assigned at %d" % (outside[0][1], outside[0][0])
        )
    # Write-once means once, and the walk above only counts where a store sits.
    # A store is credited as a *copy* by its rvalue resolving to a mailbox word,
    # so a second store to an already-copied field whose rvalue is a constant is
    # not a copy at all -- it is invisible to ``all_copies``, it is inside the
    # branch so ``outside`` never looks at it, and ``d.variant_id = 0U`` written
    # one line under the proven copy rewrites a published field with every proof
    # above satisfied. Every store to an appendix field is therefore required to
    # be one of the 34 that read the word the wire order gives it.
    forged = [
        (start, field)
        for start, field, word in record_stores
        if field in appendix_fields and word is None
    ]
    if forged:
        raise fail(
            "runner writes the copied appendix field %s from something that is not its mailbox "
            "word at offset %d" % (forged[0][1], forged[0][0])
        )
    # An increment writes the field without ever spelling ``d.<field> =``, and
    # it can be written prefix or postfix, so the lvalue is resolved to the
    # storage it designates rather than matched against one shape.
    record_names = frozenset(record_aliases(runner_masked))
    for offset, lvalue in compound_assignment_lvalues(runner_masked):
        field = _record_field_target(lvalue, record_names)
        if field in appendix_fields:
            raise fail(
                "runner rewrites a copied appendix field through a read-modify-write: "
                "%s at offset %d" % (field, offset)
            )

    # Everything above reads an *lvalue*, so everything above is answered by a
    # write that names no member: a field pointer, a ``memset``, a ``memcpy``.
    # This bounds the storage those lvalues designate instead, and it runs last
    # so a source that breaks one of the named rules is still named by it. The
    # window ends with the function that owns the record: past that the record
    # has been copied out by value and is no longer this proof's subject.
    owning_stop = next(
        (
            stop
            for _name, start, stop in function_spans(runner_masked)
            if start <= close_index < stop
        ),
        len(runner_masked),
    )
    require_record_storage_closed(runner_masked, (close_index, owning_stop))
    # The vendor-only indirect-call exemption ends at the function that owns the
    # record: the stock runner's file-scope ``irq_handler_t`` is not an attack,
    # and a function pointer declared inside the diagnostic is.
    owning_start = next(
        (
            start
            for _name, start, stop in function_spans(runner_masked)
            if start <= close_index < stop
        ),
        0,
    )
    require_runner_diagnostic_closed(runner_masked, (owning_start, owning_stop))

    return {
        "runner_serialized_words": TOTAL_WORDS,
        "runner_payload_bytes": PAYLOAD_BYTES,
        # The verifier's own observation: every appendix copy it found sits
        # inside the magic ``else`` branch, and none sits outside it.
        "runner_copy_dominated_by_magic": len(copies) == len(all_copies) and not stray,
        "runner_appendix_copies": len(copies),
        # The mailbox word each copy was resolved to, in the order the copies
        # appear. It is the verifier's own reading of the transport, not a
        # restatement of the wire order it was checked against.
        "runner_appendix_source_words": [word for _field, word in inside],
    }


def _direct_call_sites(masked: str, name: str) -> tuple[int, ...]:
    """Every offset where ``name`` is used as a callee rather than declared."""

    found: list[int] = []
    pattern = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])\s*\(" % re.escape(name))
    for match in pattern.finditer(blank_directives(masked)):
        cursor = match.start() - 1
        while cursor >= 0 and masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(masked[cursor]) or masked[cursor] == "*"
        ):
            continue
        found.append(match.start())
    return tuple(found)


# ---------------------------------------------------------------------------
# The runner's diagnostic function
#
# ``require_no_function_pointer``/``require_no_indirect_call`` are vendor-only,
# because the stock runner declares an ``irq_handler_t`` of its own at file
# scope. That exemption reached the serialized record: a function pointer
# declared *inside* the diagnostic function rewrote all 34 words after every
# copy and dominance rule was satisfied, and the copy-out parameter escaped the
# ``&d`` closure because the write went through ``out`` rather than through the
# record. The exemption is narrowed to file scope here, and the copy-out pointer
# is closed the way the record already is.
# ---------------------------------------------------------------------------


def _parameter_names(masked: str, body_start: int) -> tuple[tuple[str, bool], ...]:
    """``(name, is_pointer)`` for each parameter of the function opening at ``body_start``."""

    head = masked[: max(body_start - 1, 0)]
    close = head.rfind(")")
    if close < 0:
        return ()
    _close_of, opens = _bracket_pairs(head[: close + 1])
    open_index = opens.get(close)
    if open_index is None:
        return ()
    found: list[tuple[str, bool]] = []
    for declarator in head[open_index + 1 : close].split(","):
        names = _IDENTIFIER_RE.findall(declarator)
        if not names:
            continue
        found.append((names[-1], "*" in declarator))
    return tuple(found)


def require_record_copy_out_closed(
    runner_masked: str, span: tuple[int, int], parameters: frozenset
) -> None:
    """Refuse the record copy-out pointer reaching anything but its own store."""

    start, stop = span
    for match in _IDENTIFIER_RE.finditer(runner_masked, start, stop):
        if match.group(0) not in parameters:
            continue
        cursor = match.start() - 1
        while cursor >= 0 and runner_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if runner_masked[cursor : cursor + 1] == "*" and not _is_declarator_star(
            runner_masked, cursor
        ):
            continue
        raise fail(
            "the runner hands the record copy-out pointer %s to something other than the copy "
            "the design writes, at offset %d: a write through it rewrites every word the "
            "record's copy, dominance and address rules proved"
            % (match.group(0), match.start())
        )


def require_runner_diagnostic_closed(runner_masked: str, span: tuple[int, int]) -> None:
    """Hold the record-owning function to the vendor's indirect-call standard."""

    start, stop = span
    body = runner_masked[start:stop]
    require_no_function_pointer(body, "the runner diagnostic function")
    require_no_indirect_call(body, "the runner diagnostic function")
    # No exemption inside this window: the stock vector slot is chained to from
    # the ISR wrapper, not from the function that owns the serialized record, and
    # a call through any pointer object here rewrites words the copy, dominance
    # and address rules just proved.
    require_no_call_through_pointer_object(
        runner_masked,
        RUNNER_STOCK_FUNCTION_POINTERS,
        "the runner diagnostic function",
        window=span,
    )
    pointers = frozenset(
        name for name, is_pointer in _parameter_names(runner_masked, start) if is_pointer
    )
    if pointers:
        require_record_copy_out_closed(runner_masked, span, pointers)


def _introduced_by_typedef(masked: str, start: int) -> bool:
    """Whether the declarator beginning at ``start`` belongs to a ``typedef``."""

    head = masked.rfind(";", 0, start)
    brace = max(masked.rfind("{", 0, start), masked.rfind("}", 0, start))
    return _TYPEDEF_RE.search(masked, max(head, brace) + 1, start) is not None


def require_no_function_pointer(
    masked: str, what: str, exempt: frozenset = frozenset()
) -> None:
    """Refuse a function-pointer declarator anywhere in ``masked``.

    ``exempt`` names the *typedefs* the stock file may introduce. A declarator
    that carries an exempt name without a ``typedef`` in front of it is an
    object, not a type, and is refused like any other.
    """

    match = next(
        (
            found
            for found in _FUNCTION_POINTER_DECLARATOR_RE.finditer(masked)
            if not (
                found.group(1) in exempt
                and _introduced_by_typedef(masked, found.start())
            )
        ),
        None,
    )
    if match is not None:
        raise fail(
            "%s declares a function pointer at offset %d: %s -- a call through it carries "
            "any effect past the per-iteration, submit-counting and register-confinement "
            "rules, and this gate cannot resolve its target"
            % (what, match.start(), " ".join(match.group(0).split()))
        )


def function_pointer_type_names(masked: str, seeds: frozenset) -> frozenset:
    """``seeds`` and every typedef alias that resolves to one of them."""

    declarations = tuple(
        match.group(1) for match in _TYPEDEF_DECLARATION_RE.finditer(masked)
    )
    known = set(seeds)
    budget = len(declarations) + 1
    for _pass in range(budget):
        grown = False
        for body in declarations:
            # One ``typedef`` declares as many names as it has declarators:
            # ``typedef irq_handler_t v14_a_t, v14_b_t;`` gives the exempt type
            # two aliases, and reading only the last identifier lost the first.
            # The declarators are therefore split the same way an object
            # declaration's are, and every one of them enters the closure.
            parts = _split_top_level(body, ",")
            base = _IDENTIFIER_RE.findall(parts[0]) if parts else []
            if len(base) < 2 or not set(base[:-1]) & known:
                continue
            # A typedef that merely *mentions* a known type inside a
            # function-pointer declarator is not an alias of it.
            if _FUNCTION_POINTER_DECLARATOR_RE.search(body) is not None:
                continue
            for part in parts:
                match = _DECLARATOR_TAIL_RE.search(part.strip())
                if match is None or match.group(1) in known:
                    continue
                known.add(match.group(1))
                grown = True
        if not grown:
            break
    return frozenset(known)


def _is_cast_of(masked: str, start: int, stop: int) -> bool:
    """Whether the type name spanning ``start``..``stop`` is a cast operator."""

    before = start - 1
    while before >= 0 and masked[before] in _INLINE_SPACE:
        before -= 1
    after = stop
    while after < len(masked) and masked[after] in _INLINE_SPACE:
        after += 1
    return masked[before : before + 1] == "(" and masked[after : after + 1] == ")"


def _declaration_end(text: str, start: int) -> int:
    """Where the declaration beginning at ``start`` ends.

    ``_statement_end`` stops at ``;``/``{``/``}`` at bracket depth zero, which is
    the wrong end for a *parameter*: the declaration sits inside a parameter
    list, so the first ``)`` closes a bracket this scan never opened and the walk
    ran on past the whole function -- missing the parameter's own name and
    sweeping in identifiers from unrelated statements. A closer with nothing to
    match is therefore an end too.
    """

    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            if depth == 0:
                return index
            depth -= 1
        elif depth == 0 and character in ";{}":
            return index
    return len(text)


def declaration_declarators(text: str, start: int) -> tuple[str, ...]:
    """Every declarator name in the declaration whose type name begins at ``start``."""

    body = text[start : _declaration_end(text, start)]
    found: list[str] = []
    for part in _split_top_level(body, ","):
        # An initialiser is not a declarator. ``= 0`` after the name would
        # otherwise make the last identifier of the initialiser the object.
        head = _split_top_level(part, "=")[0]
        match = _DECLARATOR_TAIL_RE.search(head.strip())
        if match is not None:
            found.append(match.group(1))
    return tuple(found)


def function_pointer_objects(masked: str, types: frozenset) -> tuple[str, ...]:
    """Every identifier declared with one of the exempt function-pointer types.

    ``types`` is widened to the alias closure first, so a typedef that renames
    the exempt type does not hide its objects from the call rule.
    """

    scan = blank_directives(masked)
    types = function_pointer_type_names(masked, types)
    found: list[str] = []
    for type_name in sorted(types):
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(type_name)
        )
        for match in pattern.finditer(scan):
            if _introduced_by_typedef(masked, match.start()):
                continue
            if _is_cast_of(scan, match.start(), match.end()):
                # ``(irq_handler_t)0`` names the type as an operator, not as the
                # head of a declaration; reading declarators out of the
                # expression behind it would invent objects the source has none
                # of.
                continue
            found.extend(declaration_declarators(scan, match.end()))
    return tuple(sorted(set(found) - {type_name for type_name in types}))


def require_no_call_through_pointer_object(
    masked: str,
    types: frozenset,
    what: str,
    exempt: frozenset = frozenset(),
    window: tuple[int, int] | None = None,
) -> None:
    """Refuse a call whose callee is an object of a function-pointer type.

    ``exempt`` names the stock slots the frozen host file calls through.
    ``window`` bounds the scan to one span, and an exemption does not apply
    inside one -- the record-owning function is held to the stricter rule.
    """

    objects = function_pointer_objects(masked, types)
    if not objects:
        return
    scan = blank_directives(masked)
    start, stop = window if window is not None else (0, len(scan))
    for name in objects:
        if window is None and name in exempt:
            continue
        for site in _direct_call_sites(scan, name):
            if start <= site < stop:
                raise fail(_POINTER_OBJECT_CALL_REFUSAL % (what, site, name))


def _is_type_only_group(masked: str, open_index: int, close_index: int) -> bool:
    """Whether ``(...)`` encloses a type name and nothing else."""

    tokens = _C_TOKEN_RE.findall(masked[open_index + 1 : close_index])
    if not tokens:
        return False
    return all(
        token == "*" or _TYPE_NAME_TOKEN_RE.match(token) is not None for token in tokens
    )


def _closes_cast_chain(masked: str, close_index: int, opens: dict[int, int]) -> bool:
    """Whether the ``)`` at ``close_index`` ends a run of casts rather than an operand.

    ``_is_cast_parenthesis`` answers this for a single group, and answers it
    wrongly for the chain the vendor sources actually write::

        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD)

    because the ``(uintptr_t)`` group is preceded by the ``)`` of another cast,
    which that helper reads as "an operand ended here". Casts chain, so the walk
    chains too: every group stepped over must enclose a type name only, and the
    leftmost one must be preceded by something that cannot end an operand.
    """

    cursor = close_index
    while cursor >= 0 and masked[cursor] == ")":
        open_index = opens.get(cursor)
        if open_index is None or not _is_type_only_group(masked, open_index, cursor):
            return False
        cursor = open_index - 1
        while cursor >= 0 and masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor < 0:
            return True
        if masked[cursor] == ")":
            continue
        if _NAME_CHARACTER_RE.match(masked[cursor]):
            # An identifier before a cast ends an operand only if it *is* one. A
            # keyword that introduces an expression is not a value, so
            # ``return (uint32_t)(uintptr_t)p`` is a chain of casts and not a
            # call through whatever ``return`` produced.
            return _token_before(masked, cursor + 1)[1] in _EXPRESSION_KEYWORDS
        return masked[cursor] not in _OPERAND_END_CHARACTERS
    return False


def require_no_indirect_call(masked: str, what: str) -> None:
    """Refuse a postfix call whose callee is an expression rather than a name.

    A ``(`` whose preceding token is ``)`` or ``]`` is a call through whatever
    that expression produced -- unless what closed is a cast, in which case the
    ``(`` opens the cast's operand rather than an argument list.
    """

    # Directives are blanked first: a function-like macro's replacement list is
    # not a call site, and ``require_no_statement_macro`` is what judges it.
    scan = blank_directives(masked)
    _close_of, opens = _bracket_pairs(scan)
    # A function-pointer *declarator* closes with ``)`` and is followed by its
    # parameter list, so the ``(`` that opens that list is not a call site. The
    # declarator itself is judged by ``require_no_function_pointer``; reading it
    # as a call here would refuse the stock ``typedef void (*irq_handler_t)(void)``
    # for being a declaration.
    declarator_parameters = frozenset(
        match.end() - 1 for match in _FUNCTION_POINTER_DECLARATOR_RE.finditer(scan)
    )
    for index, character in enumerate(scan):
        if character != "(":
            continue
        if index in declarator_parameters:
            continue
        cursor = index - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor < 0 or scan[cursor] not in _CALLABLE_END:
            continue
        if scan[cursor] == ")" and _closes_cast_chain(scan, cursor, opens):
            continue
        raise fail(
            "%s calls through a function pointer at offset %d: the callee is an expression "
            "rather than a name, so no counting, ordering or per-iteration rule in this file "
            "sees the effect it carries" % (what, index)
        )
