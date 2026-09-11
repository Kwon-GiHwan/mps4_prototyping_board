"""Successor completion-visibility checker: source confinement."""

from __future__ import annotations


from .constants import (
    APPENDIX_FIELDS,
    APPENDIX_WORDS,
    COMMAND_SYMBOL,
    COMMAND_V14_RETURN_CODES,
    CONVERGENCE_ASSIGNMENTS,
    CONVERGENCE_CLASSIFIER,
    CONVERGENCE_DECLARATIONS,
    CONVERGE_SYMBOL,
    FROZEN_ACCESSOR_BODIES,
    ISR_CMD_CLEAR_VALUE,
    ISR_STATUS_LOADS,
    ISR_SYMBOL,
    MAILBOX_RESET_SYMBOL,
    MAILBOX_SYMBOL,
    MEASURED_LOCALS,
    NAME_UNCONFINED_REGISTERS,
    PRIMARY_SYMBOL,
    QREAD_LOADS_PER_OWNER,
    RUNNER_TRANSPORT_ASSIGNMENTS,
    STOCK_REGISTER_OWNERS,
    STOCK_STATUS_HELPERS,
    TRANSPORT_CLEARED,
    TRANSPORT_INVALID_VALUE,
    TRANSPORT_VALID_SYMBOL,
    UNRESOLVED_ROLE,
    WAIT_FOR_IRQ_SYMBOL,
    _ACCESSOR_CALL_RE,
    _ACCESSOR_REFUSAL,
    _CLEANUP_EPILOGUE_RE,
    _CONTROL_TRANSFER_RE,
    _C_TOKEN_RE,
    _FROZEN_ENTRY_STEP,
    _IDENTIFIER_RE,
    _IF_HEAD_OPEN_RE,
    _INLINE_SPACE,
    _LOOP_OR_SWITCH_KEYWORDS,
    _MAILBOX_MAGIC_GUARD_RE,
    _NAME_CHARACTER_RE,
    _PLAIN_DESIGNATION_RE,
    _PLAIN_LOCAL_LVALUE_RE,
    _PUBLICATION_SYMBOL_RE,
    _QREAD_WRITE_REFUSAL,
    _RAW_REGISTER_RE,
    _REGISTER_REFUSALS,
    _RETURN_STATEMENT_RE,
    _RET_CODE_STEP_RE,
    _UNMODELLED_ROLE_REFUSAL,
    _V14_RETURN_CONSTANTS,
    _WAIT_FOR_IRQ_REFUSAL,
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
    normalized_digest,
    parse_define_values,
)

from .c_addresses import (
    _bracket_pairs,
    _evaluate_constant,
    _is_declaration,
    _role_at_offset,
    _split_top_level,
    _token_before,
    assignment_statements,
    blank_directives,
    cmd_write_values,
    compound_assignment_targets,
    dereference_sites,
    enclosing_block_start,
    enclosing_function,
    file_scope_text,
    function_spans,
    macro_definitions,
    mailbox_alias_words,
    pointer_roles,
    register_access_sites,
    require_resolved_dereferences,
    require_resolved_pointers,
)

from .source_loops import (
    _guard_blocks,
    _pre_program_gate_function,
)

from .source_storage import (
    _direct_call_sites,
    _resolved_mailbox_stores,
)

from .source_cleanup import (
    _cmd_value_text,
)


def _require_modelled_role(
    role: str, authorized: dict[str, frozenset], what: str, site: int
) -> frozenset:
    """The owner set for ``role``, or a refusal when the contract models none."""

    allowed = authorized.get(role)
    if allowed is None:
        allowed = STOCK_REGISTER_OWNERS.get(role)
    if allowed is None:
        raise fail(_UNMODELLED_ROLE_REFUSAL % (what, role, site))
    return allowed


def _register_authorized_owners(
    vendor_masked: str, setup_name: str, variant: str
) -> dict[str, frozenset]:
    """The functions the design lets name each NPU register.

    ``setup_name`` is resolved rather than named, the way
    ``verify_pre_run_contract`` resolves it, so the confinement holds wherever
    the vendor keeps its queue programming. The pre-program gate is resolved the
    same way and for the same reason: it reads STATUS, and it does not have to
    live in the function that programs the queue -- in the frozen vendor it does
    not.
    """

    primary = PRIMARY_SYMBOL[variant]
    gate_name = _pre_program_gate_function(vendor_masked, function_spans(vendor_masked))
    return {
        "QSIZE": frozenset((setup_name, COMMAND_SYMBOL)),
        "QBASE": frozenset((setup_name,)),
        # Plus the frozen stock vendor's own STATUS helpers -- see
        # STOCK_STATUS_HELPERS. They are authorised for STATUS only: a QSIZE or
        # CMD access relocated into one of them is still refused.
        "STATUS": frozenset(
            (setup_name, gate_name, COMMAND_SYMBOL, ISR_SYMBOL, primary, CONVERGE_SYMBOL)
        )
        | STOCK_STATUS_HELPERS,
        "CMD": frozenset((COMMAND_SYMBOL, ISR_SYMBOL)),
        # QREAD used to be *absent* from this table, on the ground that a bound
        # QREAD pointer is not evidence the way a QSIZE or CMD one is -- it is
        # the register the design polls, its ordering is proven inside the two
        # measured loops, and the frozen contract permits a file-scope binding
        # this table would otherwise refuse.
        #
        # Absence was read by every walk below as permission, and
        # permission-by-absence is indistinguishable from "a role nothing
        # models": one added ``#define NPU_REG_DOORBELL 0x000U`` produced a role
        # with no owner set, and each walk skipped the second submit it named.
        # Writing that permission down as an owner-unconstrained answer fixed
        # the confusion and kept the hole: "its ordering is proven inside the
        # measured loops" is an argument about the loops, not a licence for
        # QREAD MMIO anywhere in the unit, and an extra load in a publisher or
        # in the ISR is running-path MMIO no read-order rule judged.
        #
        # So QREAD is owned like every other register. The design polls it in
        # the active primary helper and the convergence helper, and reads it
        # back once in the command function's cleanup; those three are the whole
        # set the canonical and generated sources *load* it from.
        #
        # This row is read by the two **access** walks only. The name scan skips
        # it, because a QREAD designation is not necessarily a load: the frozen
        # contract binds a QREAD pointer, and a binding names the register
        # without reaching it. Confining the name would refuse that binding;
        # confining the access is what the ground about the measured loops
        # actually supports. Writes are refused by their own rules.
        "QREAD": frozenset((primary, CONVERGE_SYMBOL, COMMAND_SYMBOL)),
    }


def require_register_confinement(
    vendor_masked: str, setup_name: str, variant: str
) -> int:
    """Refuse an NPU register named anywhere the design does not name it.

    Directives are blanked first, so the ``#define NPU_REG_QSIZE`` that gives the
    register its offset is not itself an access. Every remaining spelling counts:
    the vendor accessor's argument, a raw pointer built from
    ``U85_BASE_ADDRESS + NPU_REG_QSIZE``, and a name at file scope with no
    enclosing function at all.

    Returns the number of authorised designations it walked, so the manifest can
    publish the verifier's own count rather than a constant.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    spans = function_spans(vendor_masked)
    scanned = blank_directives(vendor_masked)
    walked = 0
    for match in _RAW_REGISTER_RE.finditer(scanned):
        register = match.group(1)
        owner = enclosing_function(spans, match.start())
        if register in NAME_UNCONFINED_REGISTERS:
            # A designation that may be a *binding* rather than an access. This
            # walk reads names, so confining it here would refuse the frozen
            # contract's own QREAD pointer; the two access walks below own the
            # question of where a load may happen, and they hold it to the same
            # table every other register is held to.
            _require_modelled_role(register, authorized, _span_label(owner), match.start())
            walked += 1
            continue
        allowed = _require_modelled_role(
            register, authorized, _span_label(owner), match.start()
        )
        if owner in allowed:
            walked += 1
            continue
        raise fail(
            _REGISTER_REFUSALS[register]
            % (owner or "file scope", match.start())
        )
    return walked


# ---------------------------------------------------------------------------
# Whole-unit MMIO confinement
#
# The scan above reads a register *name*, so it is a scan every spelling that
# carries no name walks around:
#
#     *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 1U;
#     *(volatile uint32_t *)0x50004000U = 1U;
#
# Both are a second submit. The gate already owns the resolver that names them
# -- ``resolve_address_role``, reached through ``require_resolved_dereferences``
# -- but that resolver ran only inside the functions the design names, and a
# helper the design does not name was scanned by neither rule. The resolver is
# therefore run over *every* function span and over file scope, so an NPU-region
# address this gate cannot pin to one register is refused wherever it is
# written, and a resolved one is held to the same owner table as its name.
#
# That is what makes ``register_confinement_scope: vendor_translation_unit`` a
# statement about the translation unit rather than about the tokens that happen
# to spell a register.
# ---------------------------------------------------------------------------


def _span_label(name: str) -> str:
    return "the vendor function %s" % name if name else "the vendor unit at file scope"


def require_whole_unit_mmio_confinement(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an NPU-region access this gate cannot name, or names out of place.

    Returns the number of resolved, authorised accesses it walked, so the
    manifest publishes the verifier's own whole-unit count.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    scope = file_scope_text(vendor_masked)
    walked = 0
    for name, start, stop in function_spans(vendor_masked):
        body = vendor_masked[start:stop]
        what = _span_label(name)
        if FROZEN_ACCESSOR_BODIES.get(name) == normalized_digest(body):
            continue
        roles = pointer_roles(body, defines, scope)
        require_resolved_pointers(roles, what)
        require_resolved_dereferences(body, defines, roles, what)
        for site, role, is_write in dereference_sites(body, defines, roles):
            if role == "QREAD" and is_write:
                raise fail(_QREAD_WRITE_REFUSAL % (what, start + site))
            allowed = _require_modelled_role(role, authorized, what, start + site)
            if name in allowed:
                walked += 1
                continue
            raise fail(_REGISTER_REFUSALS[role] % (name or "file scope", start + site))
    return walked


def _takes_address_at(text: str, site: int) -> bool:
    """Whether the access at ``site`` is an address-of rather than a load.

    ``&base[NPU_REG_QREAD / 4]`` is a subscript this gate enumerates as an
    access, and it is a *binding*: it reaches no word. Counting it as a load
    would make the design's own pointer bindings look like extra MMIO.
    """

    cursor = site - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    return text[cursor : cursor + 1] == "&" and text[cursor - 1 : cursor] != "&"


def qread_access_counts(
    vendor_masked: str, defines: dict[str, int]
) -> dict[str, int]:
    """``owner -> number of QREAD accesses``, over both spellings."""

    scope = file_scope_text(vendor_masked)
    spans = function_spans(vendor_masked)
    counts: dict[str, int] = {}
    for name, start, stop in spans:
        body = vendor_masked[start:stop]
        roles = pointer_roles(body, defines, scope)
        loads = sum(
            1
            for site, role, _write in dereference_sites(body, defines, roles)
            if role == "QREAD" and not _takes_address_at(body, site)
        )
        if loads:
            counts[name] = counts.get(name, 0) + loads
    for site, _verb, role in accessor_designations(vendor_masked, defines):
        if role != "QREAD":
            continue
        owner = enclosing_function(spans, site)
        counts[owner] = counts.get(owner, 0) + 1
    return counts


def require_qread_load_budget(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an authorised owner that loads QREAD more often than the design does."""

    allowed = _register_authorized_owners(vendor_masked, setup_name, variant)["QREAD"]
    counts = qread_access_counts(vendor_masked, defines)
    for owner in sorted(counts):
        if owner not in allowed:
            # Where it may be loaded at all is the confinement walks' question;
            # this rule only bounds the owners they authorise.
            continue
        if counts[owner] != QREAD_LOADS_PER_OWNER:
            raise fail(
                "%s loads QREAD more times than the design loads it: %d accesses where the "
                "design makes %d, and a load outside the loop that measures it is running-path "
                "MMIO no read-order rule in this file judged"
                % (_span_label(owner), counts[owner], QREAD_LOADS_PER_OWNER)
            )
    return sum(counts.get(owner, 0) for owner in allowed)


def require_no_qread_write(vendor_masked: str) -> None:
    """Refuse the accessor spelling of a QREAD write anywhere in the unit."""

    scan = blank_directives(vendor_masked)
    site = code_find(scan, "write_reg(NPU_REG_QREAD")
    if site >= 0:
        raise fail(_QREAD_WRITE_REFUSAL % ("the vendor translation unit", site))


def _accessor_offset_role(argument: str, defines: dict[str, int]) -> str:
    """The register an accessor's offset argument designates."""

    designation = _PLAIN_DESIGNATION_RE.match(argument)
    if designation is not None:
        return designation.group(1)
    value = _evaluate_constant(argument, defines)
    if value is None:
        return UNRESOLVED_ROLE
    return _role_at_offset(value, defines)


def accessor_designations(
    vendor_masked: str, defines: dict[str, int]
) -> tuple[tuple[int, str, str], ...]:
    """``(site, verb, role)`` for every vendor-accessor *call* in the unit.

    A declaration is separated from a call the way ``_publication_symbol_sites``
    separates them: a declarator is introduced by its return type, and nothing
    but a type name or a ``*`` can sit directly in front of one.
    """

    scan = blank_directives(vendor_masked)
    close_of, _open_of = _bracket_pairs(scan)
    found: list[tuple[int, str, str]] = []
    for match in _ACCESSOR_CALL_RE.finditer(scan):
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(scan[cursor]) or scan[cursor] == "*"
        ):
            continue
        open_index = match.end() - 1
        close_index = close_of.get(open_index)
        if close_index is None:
            found.append((match.start(), match.group(1), UNRESOLVED_ROLE))
            continue
        arguments = _split_top_level(scan[open_index + 1 : close_index], ",")
        found.append(
            (
                match.start(),
                match.group(1),
                _accessor_offset_role(arguments[0] if arguments else "", defines),
            )
        )
    return tuple(found)


def require_accessor_designations_confined(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an accessor call this gate cannot pin to one authorised register.

    Returns the number of resolved, authorised accessor calls it walked, so the
    manifest publishes the verifier's own count of the third spelling too.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    spans = function_spans(vendor_masked)
    walked = 0
    for site, verb, role in accessor_designations(vendor_masked, defines):
        owner = enclosing_function(spans, site)
        if role == UNRESOLVED_ROLE:
            raise fail(_ACCESSOR_REFUSAL % (verb, _span_label(owner), site))
        if role == "QREAD" and verb == "write_reg":
            raise fail(_QREAD_WRITE_REFUSAL % (_span_label(owner), site))
        allowed = _require_modelled_role(role, authorized, _span_label(owner), site)
        if owner not in allowed:
            raise fail(_REGISTER_REFUSALS[role] % (owner or "file scope", site))
        walked += 1
    return walked


def require_isr_register_values(vendor_masked: str, defines: dict[str, int]) -> None:
    """Pin what the interrupt handler writes to CMD and how often it reads STATUS."""

    body = function_text(vendor_masked, ISR_SYMBOL, "interrupt handler")
    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
    for site, value in cmd_write_values(body, defines, roles):
        if value != ISR_CMD_CLEAR_VALUE:
            raise fail(
                "the interrupt handler writes CMD with a value the design does not give it: "
                "%s at offset %d, and the only CMD write this contract makes from interrupt "
                "context is the 0x%X completion clear"
                % (_cmd_value_text(value), site, ISR_CMD_CLEAR_VALUE)
            )
    loads = register_access_sites(body, "STATUS", defines, roles)
    if len(loads) != ISR_STATUS_LOADS:
        raise fail(
            "the interrupt handler loads STATUS %d times: the design loads it %d, and a further "
            "load is one no dominance or read-order rule in this file judged"
            % (len(loads), ISR_STATUS_LOADS)
        )


def require_wait_for_irq_unreachable(vendor_masked: str) -> None:
    """Refuse a ``wait_for_irq`` this gate cannot prove is unreached.

    ``_direct_call_sites`` answers "is it called *here*", which is an answer
    about the token stream after ``blank_directives`` -- so a macro expanding to
    the call is a call after preprocessing and no call site before it, and the
    address of the symbol is a reachability with no call site at all. The
    exemption rests on the helper being unreached, so the proof is written the
    same way: the symbol may appear as its own declarator and nowhere else.
    """

    # The direct call first, so the spelling the design's own fixtures name is
    # reported by the rule that names it rather than by the wider one below.
    sites = _direct_call_sites(vendor_masked, WAIT_FOR_IRQ_SYMBOL)
    if sites:
        raise fail(
            "wait_for_irq is called at offset %d: the STATUS designation this gate authorises "
            "inside it is authorised on the ground that the command path never calls it, and a "
            "call makes that a running-path STATUS load no dominance or read-order rule judged"
            % sites[0]
        )
    scan = blank_directives(vendor_masked)
    for match in _IDENTIFIER_RE.finditer(scan):
        if match.group(0) != WAIT_FOR_IRQ_SYMBOL:
            continue
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        introduced_by_a_type = cursor >= 0 and (
            _NAME_CHARACTER_RE.match(scan[cursor]) or scan[cursor] == "*"
        )
        cursor = match.end()
        while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:
            cursor += 1
        if introduced_by_a_type and scan[cursor : cursor + 1] == "(":
            # A definition or a prototype: a return type in front of it, a
            # parameter list behind it. Neither reaches the helper.
            continue
        raise fail(_WAIT_FOR_IRQ_REFUSAL % ("at offset %d" % match.start()))
    # And the half the scan above cannot see at all. A replacement list naming
    # the helper is a call site this gate never expands, whichever of the two
    # macro forms carries it and whether it spells the parentheses or leaves
    # them to the invocation.
    for name, _parameters, body in macro_definitions(vendor_masked):
        if names_identifier(body, WAIT_FOR_IRQ_SYMBOL):
            raise fail(_WAIT_FOR_IRQ_REFUSAL % ("in the replacement list of %s" % name))


def require_measured_locals_not_stepped(body: str, what: str) -> None:
    """Refuse a read-modify-write on a local the publication reads."""

    stepped = compound_assignment_targets(body, MEASURED_LOCALS)
    if stepped:
        raise fail(
            "%s: %s is stepped by a read-modify-write, so the value it publishes is not the one "
            "the measured load produced" % (what, ", ".join(stepped))
        )


def require_convergence_declarations(converge_body: str, defines: dict[str, int]) -> None:
    """Pin the convergence helper's terminal tuple and count what may rewrite it."""

    wanted_names = frozenset(name for name, _expected in CONVERGENCE_DECLARATIONS)
    declared: dict[str, list[str]] = {}
    assigned: dict[str, int] = {}
    for _start, lvalue, rvalue in assignment_statements(converge_body):
        # The bare local only. ``obs->result`` writes the observation record,
        # which ``verify_observation_contract`` owns, and counting it here would
        # credit the helper with a write to a name it never touched.
        match = _PLAIN_LOCAL_LVALUE_RE.match(lvalue)
        if match is None or match.group(1) not in wanted_names:
            continue
        name = match.group(1)
        if _is_declaration(lvalue):
            declared.setdefault(name, []).append(rvalue)
        else:
            assigned[name] = assigned.get(name, 0) + 1
    for name, expected in CONVERGENCE_DECLARATIONS:
        found = declared.get(name, [])
        wanted = _evaluate_constant(expected, defines)
        if len(found) != 1 or _evaluate_constant(found[0], defines) != wanted:
            raise fail(
                "the convergence helper does not carry its terminal category in its declaration: "
                "%s is declared %s, and the design declares it %s -- a loop that runs to the "
                "bound without matching publishes whatever the declaration left there"
                % (
                    name,
                    ", ".join(_normalized_expression(item) for item in found) or "nowhere",
                    expected,
                )
            )
    for name, count in CONVERGENCE_ASSIGNMENTS:
        found_count = assigned.get(name, 0)
        if found_count != count:
            raise fail(
                "the convergence helper assigns %s %d times outside its declaration: the design "
                "assigns it %d, and a further assignment reaches the publication without passing "
                "the guard that would justify it" % (name, found_count, count)
            )


# ---------------------------------------------------------------------------
# Appendix storage closure
#
# ``require_authorized_appendix_producers`` proves the producer set over lvalue
# stores it can resolve to a word. A write that names no word reaches the same
# storage and is neither proven nor refused by it:
#
#     memcpy((void *)&mailbox[33], &m, 4U);   /* the validity magic, forged */
#     memset((void *)mailbox, 0, 4U * 34U);   /* every measured word, scrubbed */
#     v14_sink(&mailbox[9]);                  /* the address, handed away */
#
# The runner's serialized record and the observation record are already closed
# this way (``require_record_storage_closed``, ``verify_observation_contract``).
# The mailbox is the one transport object that was not, so it gets the same two
# rules: its address is never taken, and it is never reached except as a
# subscript.
# ---------------------------------------------------------------------------


def require_mailbox_storage_closed(masked: str, defines: dict[str, int], what: str) -> None:
    """Refuse the appendix reached as whole storage or by an escaped address."""

    aliases = frozenset(mailbox_alias_words(masked, defines))
    names = aliases | {MAILBOX_SYMBOL}
    scan = blank_directives(masked)
    for match in _IDENTIFIER_RE.finditer(scan):
        if match.group(0) not in names:
            continue
        # The address first, because ``&mailbox[33]`` is also a subscript and the
        # subscript rule below would wave it through. ``address_of_operands``
        # cannot answer this one: the vendor writes ``(void *)&mailbox[33]``, and
        # a ``)`` immediately before the ``&`` reads there as "an operand ended",
        # so the unary address is classified as a bitwise and. Looking left from
        # the *name* has no such ambiguity -- nothing but a unary ``&`` puts an
        # ampersand directly in front of an identifier.
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if scan[cursor : cursor + 1] == "&" and scan[cursor - 1 : cursor] != "&":
            raise fail(
                "%s takes the address of appendix word %s at offset %d: a write through it is "
                "a write the producer table cannot see, and the magic it can reach declares "
                "the other 33 words real"
                % (what, scan[match.start() : match.start() + 60].split(";")[0][:40], cursor)
            )
        cursor = match.end()
        while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:
            cursor += 1
        if scan[cursor : cursor + 1] == "[":
            continue
        raise fail(
            "%s reaches the appendix as whole storage at offset %d: %s is not a subscript, so "
            "a library call or a cast can rewrite every word the producer table proved"
            % (what, match.start(), match.group(0))
        )


# ---------------------------------------------------------------------------
# Appendix value provenance
#
# ``APPENDIX_PRODUCERS`` answers "which function wrote this word, and how many
# times". It never reads the value, so a store that satisfies every site and
# count rule can publish a number the diagnostic never measured:
#
#     mailbox[V14_MBOX_PRIMARY_RESULT] = V14_PRIMARY_OBSERVED;   /* was obs->result */
#
# That republishes a timed-out run as an observed one with the producer table
# fully satisfied -- the exact defect the observation-record table was added to
# close, one statement further down. The table below closes it at the mailbox:
# each word carries the producers the design gives it *and the expression each of
# them writes*, compared over the C token sequence so formatting is free and
# spelling is not.
# ---------------------------------------------------------------------------


def _normalized_expression(text: str) -> str:
    """``text`` as its C token sequence, so whitespace and line breaks are free."""

    return " ".join(_C_TOKEN_RE.findall(text))


APPENDIX_VALUES: dict[int, tuple[tuple[str, str], ...]] = {
    0: (("test_u85", "V14_VARIANT_ID"),),
    1: (("test_commands", "qsize_expected"),),
    2: (("test_u85", "pre_program_status"),),
    3: (("test_commands", "pre_submit_status"),),
    4: (("test_commands", "DWT -> CYCCNT"),),
    5: (("test_commands", "DWT -> CYCCNT"),),
    6: (("v14_publish_primary", "obs -> t_first"),),
    7: (("v14_publish_primary", "obs -> result"),),
    8: (("v14_publish_primary", "obs -> iterations"),),
    9: (
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "obs -> qread"),
    ),
    10: (
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "obs -> status"),
    ),
    11: (
        ("v14_publish_primary", "( obs -> qread = = qsize_expected ) ? 1U : 0U"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    12: (
        (
            "v14_publish_primary",
            "( ( obs -> status & V14_STATUS_CMD_END ) ! = 0U ) ? 1U : 0U",
        ),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    13: (
        (
            "v14_publish_primary",
            "( ( obs -> status & V14_STATUS_IRQ_RAISED ) ! = 0U ) ? 1U : 0U",
        ),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    14: (
        ("v14_publish_primary", "( obs -> status & V14_STATUS_STATE )"),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    15: (("test_commands", "converged . result"),),
    16: (("test_commands", "converged . iterations"),),
    17: (
        ("test_commands", "converged . qread"),
        ("v14_publish_failure", "V14_U32_INVALID"),
    ),
    18: (
        ("test_commands", "converged . status"),
        ("v14_publish_failure", "V14_U32_INVALID"),
    ),
    19: (
        (
            "test_commands",
            "( converged . result = = V14_CONVERGENCE_TIMEOUT ) ? 1U : 0U",
        ),
    ),
    20: (
        ("v14_publish_cleanup_failure", "V14_PHASE_CLEANUP"),
        ("v14_publish_failure", "phase"),
        ("v14_publish_success", "V14_PHASE_NONE"),
    ),
    21: (
        ("v14_publish_cleanup_failure", "V14_REASON_CLEANUP_INVARIANT"),
        ("v14_publish_failure", "reason"),
        ("v14_publish_success", "V14_REASON_NONE"),
    ),
    22: (
        ("v14_publish_cleanup_failure", "qread"),
        ("v14_publish_failure", "qread"),
        ("v14_publish_success", "V14_U32_INVALID"),
    ),
    23: (
        ("v14_publish_cleanup_failure", "status"),
        ("v14_publish_failure", "status"),
        ("v14_publish_success", "V14_U32_INVALID"),
    ),
    24: (("test_u85", "NVIC_GetVector ( NPU0_IRQn )"),),
    25: (("test_u85", "NVIC_GetEnableIRQ ( NPU0_IRQn )"),),
    26: (("test_u85", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    27: (("test_u85", "NVIC_GetActive ( NPU0_IRQn )"),),
    28: (("test_u85", "irq_triggered ? 1U : 0U"),),
    29: (("test_commands", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    30: (("test_commands", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    31: (("test_commands", "NVIC_GetActive ( NPU0_IRQn )"),),
    32: (("test_commands", "irq_triggered ? 1U : 0U"),),
    33: (("v14_mailbox_publish", "V14_MAILBOX_VALID"),),
}


def _value_text(pairs: tuple[tuple[str, str], ...]) -> str:
    return ", ".join("%s <- %s" % (owner, value) for owner, value in pairs)


def require_appendix_value_provenance(
    vendor_masked: str, defines: dict[str, int]
) -> int:
    """Refuse an appendix word published from a value the design does not give it."""

    aliases = mailbox_alias_words(vendor_masked, defines)
    observed: dict[object, list[tuple[str, str]]] = {}
    for word, _token, value, owner in _resolved_mailbox_stores(
        vendor_masked, defines, aliases
    ):
        if owner == MAILBOX_RESET_SYMBOL:
            continue
        observed.setdefault(word, []).append((owner, _normalized_expression(value)))
    for index in range(APPENDIX_WORDS):
        expected = APPENDIX_VALUES[index]
        found = tuple(sorted(observed.get(index, ())))
        if found != tuple(sorted(expected)):
            raise fail(
                "appendix word %d (%s) is not published from the value the design gives it: "
                "found %s, expected %s"
                % (
                    index,
                    APPENDIX_FIELDS[index],
                    _value_text(found) or "no store outside the mailbox reset",
                    _value_text(tuple(sorted(expected))),
                )
            )
    return sum(len(pairs) for pairs in observed.values())


def _publication_call_sites(vendor_masked: str) -> tuple[tuple[int, str, str], ...]:
    """``(site, callee, arguments)`` for every publication *call* statement.

    The argument list is bounded by the matching parenthesis rather than by a
    ``[^;]*`` run, because such a run walks straight out of a definition's
    parameter list and into the first ``);`` inside its body -- which is how the
    definition of ``v14_publish_failure`` reads as a call to itself. A call is
    then separated from a definition by what follows the ``)``: a ``;`` ends a
    statement, a ``{`` opens a body.

    A forward declaration ends in ``;`` exactly as a call statement does, so the
    two are separated by what *precedes* the name instead: a prototype is
    introduced by its return type, and nothing but a type name or a ``*`` can sit
    directly in front of a declarator. A call statement is preceded by ``;``,
    ``{``, ``}`` or the ``)`` of the branch that reaches it.
    """

    return tuple(
        (site, callee, arguments)
        for site, callee, arguments, is_call in _publication_symbol_sites(vendor_masked)
        if is_call
    )


def _publication_symbol_sites(
    vendor_masked: str,
) -> tuple[tuple[int, str, str, bool], ...]:
    """``(site, callee, arguments, is_call_statement)`` for every publication symbol.

    A symbol that is neither a definition nor a prototype but whose ``)`` is not
    followed by ``;`` is reported here with ``is_call_statement`` false rather
    than dropped, because dropping it is what let a live publication call hide
    behind one pair of parentheses:

        (void)(v14_publish_failure(V14_PHASE_NONE, V14_REASON_NONE, ...));

    That overwrites every verdict the run reached with a clean tuple, republishes
    the magic, and leaves ``publication_calls_with_proven_arguments`` at the
    number the design's own call sites produce.
    """

    close_of, _open_of = _bracket_pairs(vendor_masked)
    found: list[tuple[int, str, str, bool]] = []
    for match in _PUBLICATION_SYMBOL_RE.finditer(vendor_masked):
        cursor = match.start() - 1
        while cursor >= 0 and vendor_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(vendor_masked[cursor]) or vendor_masked[cursor] == "*"
        ):
            continue
        cursor = match.end()
        while cursor < len(vendor_masked) and vendor_masked[cursor] in _INLINE_SPACE:
            cursor += 1
        if vendor_masked[cursor : cursor + 1] != "(":
            # The symbol reached without a parameter list at all -- its address,
            # or a bare mention. It publishes nothing on its own and it hands
            # the publisher somewhere no argument rule below can follow.
            found.append((match.start(), match.group(1), "", False))
            continue
        open_index = cursor
        close_index = close_of.get(open_index)
        if close_index is None:
            found.append((match.start(), match.group(1), "", False))
            continue
        cursor = close_index + 1
        while cursor < len(vendor_masked) and vendor_masked[cursor] in _INLINE_SPACE:
            cursor += 1
        found.append(
            (
                match.start(),
                match.group(1),
                vendor_masked[open_index + 1 : close_index],
                vendor_masked[cursor : cursor + 1] == ";",
            )
        )
    return tuple(found)

PUBLICATION_CALLS: dict[str, tuple[tuple[str, str], ...]] = {
    "test_u85": (
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_STATE_RUNNING , V14_U32_INVALID , V14_U32_INVALID",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_STATE_RUNNING , V14_U32_INVALID , pre_program_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_RESET_IN_PROGRESS , V14_U32_INVALID , pre_program_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_HARDWARE_FAULT , V14_U32_INVALID , pre_program_status",
        ),
    ),
    "test_commands": (
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_QSIZE_MISMATCH , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STATE_RUNNING , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_RESET_IN_PROGRESS , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_HARDWARE_FAULT , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STALE_IRQ , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STALE_CMD_END , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_RESET_IN_PROGRESS , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_HARDWARE_FAULT , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_PRIMARY_TIMEOUT , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_RESET_IN_PROGRESS , converged . qread , converged . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_HARDWARE_FAULT , converged . qread , converged . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_CONVERGENCE_TIMEOUT , converged . qread , converged . status",
        ),
        ("v14_publish_cleanup_failure", "( uint32_t ) read_val , converged . status"),
        ("v14_publish_success", ""),
    ),
}


def require_publication_call_provenance(vendor_masked: str) -> int:
    """Refuse a publication call whose argument tuple is not the design's."""

    # A symbol that is not a definition, not a prototype and not a call
    # *statement* is a live publication this table never reads, so it is refused
    # here rather than skipped by the walk that builds the table.
    for site, callee, _arguments, is_call in _publication_symbol_sites(vendor_masked):
        if not is_call:
            raise fail(
                "a publication symbol appears outside a proven call site: %s at offset %d is "
                "neither a definition nor a call statement, so the tuple it publishes is one no "
                "argument rule in this file reads" % (callee, site)
            )
    spans = function_spans(vendor_masked)
    observed: dict[str, list[tuple[str, str]]] = {}
    for site, callee, arguments in _publication_call_sites(vendor_masked):
        owner = enclosing_function(spans, site)
        observed.setdefault(owner, []).append(
            (callee, _normalized_expression(arguments))
        )
    for owner in sorted(set(observed) | set(PUBLICATION_CALLS)):
        expected = tuple(sorted(PUBLICATION_CALLS.get(owner, ())))
        found = tuple(sorted(observed.get(owner, ())))
        if found != expected:
            missing = [pair for pair in expected if pair not in found]
            extra = [pair for pair in found if pair not in expected]
            raise fail(
                "a publication call does not carry the argument tuple the design gives it in "
                "%s: missing %s, unexpected %s"
                % (
                    owner or "file scope",
                    _value_text(tuple(missing)) or "none",
                    _value_text(tuple(extra)) or "none",
                )
            )
    return sum(len(calls) for calls in observed.values())


def require_cleanup_epilogue(command: str) -> None:
    """Prove the cleanup branch publishes its own tuple and lands its own code."""

    match = _CLEANUP_EPILOGUE_RE.search(command)
    if match is None:
        raise fail(
            "the cleanup epilogue is not the design's ret_code branch: the failure and success "
            "tails are not two arms of one if/else on ret_code"
        )
    for arm, publisher, code, label in (
        (match.group(1), "v14_publish_cleanup_failure", "V14_RET_CLEANUP_INVARIANT", "failure"),
        (match.group(2), "v14_publish_success", "V14_RET_SUCCESS", "success"),
    ):
        if not code_contains(arm, publisher + "("):
            raise fail(
                "a publication call does not carry the argument tuple the design gives it in "
                "the cleanup %s arm: %s is not the publisher it calls" % (label, publisher)
            )
        if not code_contains(arm, "ret_code = " + code):
            raise fail(
                "the cleanup-failure branch does not land its own return code: the %s arm does "
                "not assign %s" % (label, code)
            )
        # Presence is not exclusivity. A second store to the same name walks
        # straight past the check above, and only the last one decides what the
        # host is told -- so the mailbox says CLEANUP_INVARIANT while the vendor
        # returns SUCCESS, which is the disagreement this rule exists to refuse.
        writes = [
            lvalue
            for _start, lvalue, _rvalue in assignment_statements(arm)
            if names_identifier(lvalue, "ret_code")
        ]
        if len(writes) != 1:
            raise fail(
                "the cleanup %s arm assigns ret_code more than once: %d assignments reach the "
                "vendor return code, and only the last one decides what the host is told"
                % (label, len(writes))
            )
        if compound_assignment_targets(arm, ("ret_code",)):
            raise fail(
                "the cleanup %s arm assigns ret_code more than once: a read-modify-write reaches "
                "the vendor return code after the assignment this rule proved" % label
            )
    require_v14_return_codes_settled(command, "command", COMMAND_V14_RETURN_CODES)


# Exclusivity *within* each epilogue arm is only a proof while the arms are the
# last word. The epilogue is not the end of the function and the command
# function is not the end of the call chain, so a store one statement further
# down -- in either frame -- overwrites whichever arm ran with every rule above
# satisfied: ``ret_code &= 0;`` republishes a detected cleanup invariant as
# V14_RET_SUCCESS while the mailbox still carries the failure tuple. The return
# code is therefore settled over each whole function that owns one: the design's
# assignments, and never a read-modify-write.
def _return_code_writes(body: str):
    return [
        (start, rvalue)
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, "ret_code")
    ]


def require_return_code_settled(body: str, what: str, expected: int) -> None:
    """Refuse a return code rewritten after the branch that decided it."""

    if compound_assignment_targets(body, ("ret_code",)):
        raise fail(
            "the %s function reaches ret_code through a read-modify-write: the value the vendor "
            "returns is then not the one the branch that detected the outcome assigned, and the "
            "mailbox tuple and the return code stop agreeing" % what
        )
    writes = _return_code_writes(body)
    if len(writes) != expected:
        raise fail(
            "the %s function assigns ret_code %d times: the design assigns it %d, and a further "
            "assignment reaches the vendor return code after the branch that decided it"
            % (what, len(writes), expected)
        )


def require_entry_return_code_frozen(body: str, what: str) -> None:
    """Hold the entry frame's return code to the frozen vendor's own handling.

    The entry frame is the vendor's, not the design's: it rewrites ret_code after
    the command function has returned, and refusing that refuses the frozen file.
    What must still be refused is a store the frozen vendor does not make, because
    that is how a forged verdict gets one frame further out -- ``ret_code &= 0``
    to mask a failure to success, or a V14 verdict assigned where no V14 branch
    decided one.
    """

    steps = [hit.group(0).replace(" ", "") for hit in _RET_CODE_STEP_RE.finditer(body)]
    foreign = [step for step in steps if step != _FROZEN_ENTRY_STEP]
    if foreign:
        raise fail(
            "the %s function reaches ret_code through a read-modify-write the frozen vendor does "
            "not make (%s): the value returned is then not the one the branch that detected the "
            "outcome assigned" % (what, foreign[0])
        )
    for _start, rvalue in _return_code_writes(body):
        named = [c for c in _V14_RETURN_CONSTANTS if names_identifier(rvalue, c)]
        if named:
            raise fail(
                "the %s function assigns %s: no V14 branch decides a verdict in this frame, so a "
                "store of one forges the command function's" % (what, named[0])
            )


def require_v14_return_codes_settled(body: str, what: str, codes) -> None:
    """Refuse a V14 verdict written more than once, or through a read-modify-write.

    This is the part of "the return code is settled" that reading characters can
    decide. The rest of it -- that no later store overwrites the arm that ran --
    is an ordering claim over a function the frozen vendor also writes to on
    branches of its own, and it is bound on the linked image instead.
    """

    if compound_assignment_targets(body, ("ret_code",)):
        raise fail(
            "the %s function reaches ret_code through a read-modify-write: the value the vendor "
            "returns is then not the one the branch that detected the outcome assigned, and the "
            "mailbox tuple and the return code stop agreeing" % what
        )
    writes = _return_code_writes(body)
    for code in codes:
        carrying = [rvalue for _start, rvalue in writes if names_identifier(rvalue, code)]
        if len(carrying) != 1:
            raise fail(
                "the %s function assigns %s %d times: the design assigns it once, in the epilogue "
                "arm that decided it" % (what, code, len(carrying))
            )
    # A V14 verdict the design does not own has no arm behind it.
    for _start, rvalue in writes:
        named = [c for c in _V14_RETURN_CONSTANTS if names_identifier(rvalue, c)]
        if named and not any(c in codes for c in named):
            raise fail(
                "the %s function assigns %s, which is not one of the design's epilogue verdicts: %s"
                % (what, named[0], ", ".join(codes))
            )

# A *bag* of return expressions pins which codes appear and never which guard
# produced which, so any permutation among the arms is accepted: the reset arm
# returns HARDWARE_FAULT and the fault arm returns RESET_IN_PROGRESS with the
# multiset unchanged. The design gives those two separate failure classes and
# fixes their priority -- reset checked before fault -- and the host's
# disposition keys off the class.
#
# So the table is an ordered sequence of ``(guard condition, return
# expression)`` pairs, compared position by position over the C token sequence.
# Order is the priority, the pairing is the binding, and a permutation changes
# both. The fall-through returns carry an empty condition: they are reached when
# no guard in their block matched, which is a position in the sequence rather
# than a predicate.
RETURN_BINDINGS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "test_commands": (
        ((
            "qsize_expected ! = V14_QSIZE_EXPECTED",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_STATE ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_RESET ) ! = 0U",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "( pre_submit_status & V14_STATUS_FAULT_MASK ) ! = 0U",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "( pre_submit_status & V14_STATUS_IRQ_RAISED ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_CMD_END ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
            "primary . result = = V14_PRIMARY_RESET",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
            "primary . result = = V14_PRIMARY_FAULT",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
        ), "V14_RET_PRIMARY_TIMEOUT"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
            "converged . result = = V14_CONVERGENCE_RESET",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
            "converged . result = = V14_CONVERGENCE_FAULT",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
        ), "V14_RET_CONVERGENCE_TIMEOUT"),
        ((), "ret_code"),
    ),
    "test_u85": (
        ((
            "( pmu_completion_visibility_v14_mailbox [ V14_MBOX_INSTALLED_VECTOR ] ! = ( uint32_t ) & u85_irq_handler ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_ENABLED_BEFORE_SUBMIT ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT ] ! = 0U )",
        ), "V14_RET_PRE_PROGRAM_FAILURE"),
        ((
            "( pre_program_status & V14_STATUS_STATE ) ! = 0U",
        ), "V14_RET_PRE_PROGRAM_FAILURE"),
        ((
            "( pre_program_status & V14_STATUS_RESET ) ! = 0U",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "( pre_program_status & V14_STATUS_FAULT_MASK ) ! = 0U",
        ), "V14_RET_HARDWARE_FAULT"),
        ((), "ret_code"),
    ),
}


def _enclosing_guards(
    body: str, position: int, defines: dict[str, int]
) -> tuple[str, ...]:
    """Every ``if`` condition whose block encloses ``position``, outermost first.

    Reading only the *innermost* guard records a pair that an extra enclosing
    guard leaves byte-identical while changing which arm runs first. Wrapping
    the reset arm in ``if ((status & FAULT_MASK) == 0U)`` inverts a priority the
    design fixes -- a status carrying both bits returns HARDWARE_FAULT where the
    design returns RESET_IN_PROGRESS -- so the whole chain is the binding, and
    its depth is part of it.

    A guard this gate can fold to a non-zero constant is not a branch: ``if
    (1)`` selects nothing and reorders nothing, so it is dropped from the chain
    rather than recorded as a level. The walk continues outward past it, so a
    real guard wrapped in a vacuous one is still seen. Only a condition that
    folds -- the same evaluator the value tables use -- earns that; one this
    gate cannot read stays in the chain, which is the fail-closed answer.
    """

    found: list[str] = []
    cursor = position
    budget = len(body)
    for _step in range(budget):
        start = enclosing_block_start(body, cursor)
        if start <= 0:
            break
        head = body[: start - 1]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            break
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None:
            break
        # A block that opens on something other than the guard it follows -- an
        # ``else`` arm, a loop body -- has other text between the ``)`` and the
        # ``{``, and reading its condition as this return's guard would bind the
        # wrong predicate. Only an immediately-following block is the guard's own.
        if head[close + 1 :].strip():
            break
        condition = head[opener.end() : close]
        folded = _evaluate_constant(condition, defines)
        if folded is None or folded == 0:
            found.append(_normalized_expression(condition))
        cursor = opener.start()
    return tuple(reversed(found))


def return_bindings(
    body: str, defines: dict[str, int]
) -> tuple[tuple[tuple[str, ...], str], ...]:
    """``(guard chain, return expression)`` for every return, in source order."""

    return tuple(
        (
            _enclosing_guards(body, match.start(), defines),
            _normalized_expression(match.group(1)),
        )
        for match in _RETURN_STATEMENT_RE.finditer(body)
    )


def _binding_text(pairs: tuple[tuple[tuple[str, ...], str], ...], index: int) -> str:
    if index >= len(pairs):
        return "nothing"
    chain, expression = pairs[index]
    return "%s -> %s" % (" && ".join(chain) or "the fall-through", expression)


def require_return_expression_provenance(
    body: str, name: str, what: str, defines: dict[str, int]
) -> int:
    """Refuse a function whose guards do not return the codes the design binds them to."""

    expected = RETURN_BINDINGS[name]
    found = return_bindings(body, defines)
    if found != expected:
        index = next(
            (
                position
                for position in range(max(len(expected), len(found)))
                if position >= len(found)
                or position >= len(expected)
                or found[position] != expected[position]
            ),
            0,
        )
        raise fail(
            "the %s function does not return the value the design returns: at return %d it "
            "carries %s, and the design binds %s -- the failure class the host is handed is "
            "decided by the guard that detected it, so the codes are not permutable among the "
            "arms"
            % (what, index, _binding_text(found, index), _binding_text(expected, index))
        )
    return len(found)


def require_convergence_classification(converge_body: str) -> None:
    """Prove each convergence category is bound to the condition that decides it."""

    guards = _guard_blocks(converge_body, "status")
    for mask, expected in CONVERGENCE_CLASSIFIER:
        matching = [body for condition, body in guards if names_identifier(condition, mask)]
        if len(matching) != 1:
            raise fail(
                "the convergence classifier does not bind %s to one guard: %d guards name %s"
                % (expected, len(matching), mask)
            )
        if not code_contains(matching[0], "result = " + expected):
            raise fail(
                "the convergence classifier does not bind %s to its own condition: the %s "
                "guard lands a different category" % (expected, mask)
            )
    success = [
        body
        for condition, body in _guard_blocks(converge_body, "qsize_expected")
        if names_identifier(condition, "V14_STATUS_CMD_END")
    ]
    if len(success) != 1:
        raise fail(
            "the convergence classifier does not bind V14_CONVERGENCE_SUCCESS to one guard: "
            "%d completion guards" % len(success)
        )
    if not code_contains(success[0], "result = V14_CONVERGENCE_SUCCESS"):
        raise fail(
            "the convergence classifier does not bind V14_CONVERGENCE_SUCCESS to its own "
            "condition: the completion guard lands a different category"
        )
    if not code_contains(success[0], "iterations = i"):
        raise fail(
            "the convergence classifier does not bind the iteration count to the loop "
            "induction variable: iterations is not set from i"
        )


def require_convergence_same_iteration(loop_body: str) -> None:
    """Prove the published convergence tuple is the one this iteration read."""

    for name in ("qread", "status"):
        writes = [
            lvalue
            for _start, lvalue, _rvalue in assignment_statements(loop_body)
            if names_identifier(lvalue, name) and not _is_declaration(lvalue)
        ]
        if len(writes) != 1:
            raise fail(
                "the convergence tuple is not the one the loop's own iteration read: %s is "
                "assigned %d times in the loop body, so a value from an earlier iteration can "
                "reach the publication" % (name, len(writes))
            )


def _opens_loop_or_switch(body: str, open_index: int) -> bool:
    """Whether the block opening at ``open_index`` is a loop or ``switch`` body.

    The head is read by matching its parenthesis rather than by a pattern, because
    a ``for`` header carries its own semicolons and any expression the source
    likes -- a regex bounded on ``;`` misses exactly the loop this has to see.
    """

    head = body[:open_index].rstrip()
    if head.endswith("do"):
        return _token_before(head, len(head))[1] == "do"
    if not head.endswith(")"):
        return False
    open_paren = _bracket_pairs(head)[1].get(len(head) - 1)
    if open_paren is None:
        return False
    return _token_before(head, open_paren)[1] in _LOOP_OR_SWITCH_KEYWORDS


def _enclosing_blocks(body: str, position: int) -> tuple[tuple[int, int], ...]:
    """``(open brace, just-inside offset)`` for each block enclosing ``position``."""

    stack: list[tuple[int, int]] = []
    for index in range(min(position, len(body))):
        character = body[index]
        if character == "{":
            stack.append((index, index + 1))
        elif character == "}" and stack:
            stack.pop()
    return tuple(reversed(stack))


def _is_unreachable_here(body: str, position: int, defines: dict[str, int]) -> bool:
    """Whether some block enclosing ``position`` is an ``if`` that folds to zero."""

    for open_index, _inside in _enclosing_blocks(body, position):
        head = body[:open_index]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            continue
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None or head[close + 1 :].strip():
            continue
        if _evaluate_constant(head[opener.end() : close], defines) == 0:
            return True
    return False


def _transfer_stays_inside(body: str, offset: int, position: int) -> bool:
    """Whether a ``break``/``continue`` at ``offset`` is spent before ``position``.

    A loop that runs to completion ahead of the store cannot skip it, so its own
    ``break`` is not a bypass. One whose block still encloses the store is.
    """

    for open_index, _inside in _enclosing_blocks(body, offset):
        if not _opens_loop_or_switch(body, open_index):
            continue
        return _matching_brace(body, open_index, "loop body") < position
    return False


def _reaches_without_transfer(
    body: str, position: int, defines: dict[str, int]
) -> bool:
    """Whether no reachable control transfer precedes ``position`` in ``body``.

    Checking the blocks that *enclose* the store leaves every statement *before*
    it unexamined, and an early exit there skips an otherwise-unguarded clear
    while every enclosing block stays trivially acceptable -- ordinary
    warning-clean C, no dead code. Every transfer in the prefix therefore has to
    be discharged: one this gate can prove unreachable, or a ``break``/
    ``continue`` whose loop is over before the store. Anything else, including a
    ``goto`` whose label this gate does not resolve, is a bypass.
    """

    prefix = blank_directives(body[:position])
    for match in _CONTROL_TRANSFER_RE.finditer(prefix):
        if _is_unreachable_here(body, match.start(), defines):
            continue
        if match.group(1) in ("break", "continue") and _transfer_stays_inside(
            body, match.start(), position
        ):
            continue
        return False
    return True


def _executes_unconditionally(body: str, position: int, defines: dict[str, int]) -> bool:
    """Whether the statement at ``position`` runs on every path through ``body``.

    Proving the clearing store *exists* is not proving it *happens*: wrapping it
    in ``if (0)`` leaves a store that folds to zero and never executes, so the
    flag is never cleared and the run window carries whatever the last one left.
    A store is on the must-execute path when every block enclosing it is an
    ``if`` whose condition folds to a non-zero constant -- a guard that selects
    nothing -- and it is not on that path when a block is an ``else`` arm, a
    loop, or an ``if`` this gate cannot fold.

    The enclosing blocks are only half of it: a transfer that *precedes* the
    store skips it without touching any of them, so the prefix is walked too.
    """

    if not _reaches_without_transfer(body, position, defines):
        return False
    cursor = position
    for _step in range(len(body)):
        start = enclosing_block_start(body, cursor)
        if start <= 0:
            return True
        head = body[: start - 1]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            return False
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None or head[close + 1 :].strip():
            # An ``else`` arm or a loop body: text sits between the guard's
            # ``)`` and this block's ``{``, so the block is not the guard's own.
            return False
        folded = _evaluate_constant(head[opener.end() : close], defines)
        if folded is None or folded == 0:
            return False
        cursor = opener.start()
    return False


def _mailbox_magic_branch(runner_masked: str) -> tuple[int, int]:
    """The span of the mailbox-magic ``if``/``else``, arms included.

    Everything inside it is the polarity rule's to judge; everything outside it
    settles the flag before the run and is judged by the lifetime rule.
    """

    match = _MAILBOX_MAGIC_GUARD_RE.search(runner_masked)
    if match is None:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    open_index = runner_masked.find("{", match.end())
    if open_index < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    close_index = _matching_brace(runner_masked, open_index, "runner magic guard")
    tail = code_find(runner_masked[close_index:], "else")
    if tail < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    else_open = runner_masked.find("{", close_index + tail)
    if else_open < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    return open_index, _matching_brace(runner_masked, else_open, "runner magic else") + 1


def require_transport_reset_polarity(runner_masked: str) -> None:
    """Prove the runner's reset clears the transport flag rather than asserting it.

    The reset function is *resolved* rather than named -- it is whichever
    function calls ``v14_mailbox_reset()``, the way ``verify_pre_run_contract``
    resolves the queue setup owner. The host runner this contract is generated
    into keeps its own name for that routine, so a rule written against one
    spelling proves nothing about the file it actually runs on.

    The store is then read as a value, folded the way ``APPENDIX_VALUES`` and
    ``RETURN_EXPRESSIONS`` fold theirs, so a spelling this gate cannot fold is
    refused rather than admitted for containing the right prefix.
    """

    site = code_find(runner_masked, MAILBOX_RESET_SYMBOL + "();")
    if site < 0:
        raise fail("runner does not reset the mailbox before the measured call")
    spans = function_spans(runner_masked)
    owner = enclosing_function(spans, site)
    body_start, body_stop = next(
        (
            (start, stop)
            for name, start, stop in spans
            if name == owner and start <= site < stop
        ),
        (0, len(runner_masked)),
    )
    body = runner_masked[body_start:body_stop]
    defines = {
        name: seen[-1] for name, seen in parse_define_values(runner_masked).items()
    }
    branch_start, branch_stop = _mailbox_magic_branch(runner_masked)
    # "The first store after the reset call" is a statement about *where the
    # call is*, and the call can move. Hoisting ``v14_mailbox_reset()`` into the
    # record owner makes the magic branch's own ``= 0U`` the first store after
    # it, so that reading passes while the function that actually re-arms the
    # run asserts the flag. Three things are therefore required of the re-arm,
    # narrowest first, so a source is named by the most specific thing wrong
    # with it: the store that accompanies the call clears the flag; that store
    # is in the same function as the call; and no store anywhere outside the
    # mailbox-magic branch leaves the flag asserted.
    reset_offset = site - body_start
    stores = [
        rvalue
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL) and start >= reset_offset
    ]
    landed = [_evaluate_constant(rvalue, defines) for rvalue in stores]
    if not stores or landed[0] != TRANSPORT_CLEARED:
        raise fail(
            "the runner reset does not clear the transport flag: %s re-arms the run without "
            "storing %s to %s -- it stores %s, so a mailbox that never published is reported "
            "to the host as a valid transport for every window before the magic branch "
            "settles it"
            % (
                owner or "file scope",
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
                ", ".join(_normalized_expression(rvalue) for rvalue in stores)
                or "nothing",
            )
        )
    cleared_here = [
        start
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
        and not branch_start <= body_start + start < branch_stop
        and _evaluate_constant(rvalue, defines) == TRANSPORT_CLEARED
    ]
    # A store the contract needs to *happen* is not proven by one that merely
    # *exists*. ``if (0) { pmu_diag_v14_transport_valid = 0U; }`` satisfies the
    # value and the ownership and clears nothing.
    if cleared_here and not any(
        _executes_unconditionally(body, start, defines) for start in cleared_here
    ):
        raise fail(
            "the runner does not clear the transport flag on every path: %s stores %s to %s "
            "only under a guard this gate cannot discharge, so a run whose vendor never "
            "published carries whatever the previous run left in %s"
            % (
                owner or "file scope",
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
                TRANSPORT_VALID_SYMBOL,
            )
        )
    if not cleared_here:
        raise fail(
            "the runner resets the mailbox in a function that does not clear the transport "
            "flag: %s calls %s without storing %s to %s, so the re-arm and the reset are two "
            "different windows and the flag outlives the run they belong to"
            % (
                owner or "file scope",
                MAILBOX_RESET_SYMBOL,
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
            )
        )
    for start, lvalue, rvalue in assignment_statements(runner_masked):
        if not names_identifier(lvalue, TRANSPORT_VALID_SYMBOL):
            continue
        if branch_start <= start < branch_stop:
            continue
        if _evaluate_constant(rvalue, defines) != TRANSPORT_CLEARED:
            raise fail(
                "the runner asserts the transport flag outside the mailbox-magic branch: the "
                "store at offset %d lands %s rather than %s, so a mailbox that never published "
                "is reported to the host as a valid transport for the whole run window before "
                "the branch settles it"
                % (start, _normalized_expression(rvalue), TRANSPORT_INVALID_VALUE)
            )


def require_transport_validity_polarity(runner_masked: str) -> None:
    """Prove the invalid-magic arm clears the transport flag rather than setting it."""

    guards = [
        body
        for condition, body in _guard_blocks(runner_masked, MAILBOX_SYMBOL)
        if names_identifier(condition, "V14_MAILBOX_VALID")
    ]
    if len(guards) != 1:
        raise fail(
            "the runner does not gate its copy on one mailbox-magic comparison: %d guards "
            "name V14_MAILBOX_VALID" % len(guards)
        )
    if not code_contains(guards[0], TRANSPORT_VALID_SYMBOL + " = 0U"):
        raise fail(
            "the runner sets transport_valid on an invalid mailbox magic: the arm taken when "
            "word 33 is not the magic does not clear %s, so a run that never published is "
            "reported to the host as a valid transport" % TRANSPORT_VALID_SYMBOL
        )
    # And clearing it is only a proof while nothing sets it again: the check
    # above asks whether the store appears, never whether it is the last one.
    writes = [
        lvalue
        for _start, lvalue, _rvalue in assignment_statements(guards[0])
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
    ]
    if len(writes) != 1 or compound_assignment_targets(guards[0], (TRANSPORT_VALID_SYMBOL,)):
        raise fail(
            "the invalid-magic arm assigns %s more than once: %d assignments reach the transport "
            "flag, and a run that never published is reported to the host as a valid transport by "
            "whichever one lands last" % (TRANSPORT_VALID_SYMBOL, len(writes))
        )
    # And the arm is only the last word while nothing outside it writes the flag
    # either. A store *after* the branch reports the transport as valid whichever
    # arm ran, with the polarity rule above fully satisfied, so the flag is
    # settled over the whole runner rather than inside one arm of it.
    if compound_assignment_targets(runner_masked, (TRANSPORT_VALID_SYMBOL,)):
        raise fail(
            "the runner reaches %s through a read-modify-write: the flag the host reads is then "
            "not the one the mailbox-magic branch assigned, and a run that never published is "
            "reported as a valid transport" % TRANSPORT_VALID_SYMBOL
        )
    unit_writes = [
        lvalue
        for _start, lvalue, _rvalue in assignment_statements(runner_masked)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
    ]
    if len(unit_writes) != RUNNER_TRANSPORT_ASSIGNMENTS:
        raise fail(
            "the runner assigns %s %d times: the design assigns it %d, and a further assignment "
            "reaches the transport flag after the mailbox-magic branch that decided it"
            % (TRANSPORT_VALID_SYMBOL, len(unit_writes), RUNNER_TRANSPORT_ASSIGNMENTS)
        )
