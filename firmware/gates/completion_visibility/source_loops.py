"""Successor completion-visibility checker: source loops."""

from __future__ import annotations

import re

from .constants import (
    CONVERGENCE_PREDICATE,
    CONVERGE_SYMBOL,
    EXPECTED_PRIMARY_ORDER,
    HARD_BYPASS_PROBE_ORDER,
    ITERATION_BOUND,
    NVIC_ISER_BASE,
    NVIC_ISER_BYTES,
    PRIMARY_COMPLETION_PREDICATE,
    PRIMARY_SYMBOL,
    QSIZE_EXPECTED,
    RULE_PRE_PROGRAM_GATE_SHAPE,
    STATUS_CMD_END,
    STATUS_FAULT_MASK,
    STATUS_IRQ_RAISED,
    STATUS_RESET,
    STATUS_STATE,
    STOCK_VECTOR_SYMBOL,
    _BACK_EDGE_RE,
    _CANONICAL_GUARD_EFFECTS,
    _CARRIED_EFFECT_PREFIXES,
    _CONTINUE_RE,
    _C_TOKEN_RE,
    _EXTRA_LOOP_RE,
    _FAULT_PREDICATE,
    _FIRST_OBSERVATION_CATEGORY,
    _GOTO_RE,
    _GUARD_HEAD_RE,
    _IDENTIFIER_RE,
    _INDUCTION_ALLOWED,
    _INDUCTION_DECL_RE,
    _INLINE_SPACE,
    _IRQ_TRIGGERED_CLEARED,
    _LABEL_KEYWORDS,
    _LABEL_RE,
    _MAX_NESTING_DEPTH,
    _OPERAND_END_CHARACTERS,
    _POINTER_CAST_RE,
    _PREDICATE_IDENTIFIERS,
    _PREDICATE_TERMS,
    _PRE_SUBMIT_GATES,
    _QBASE_WRITE,
    _QSIZE_WRITE,
    _QUEUE_PROGRAMMING_ROLES,
    _RESET_PREDICATE,
    _STATUS_BOOLEAN_NAMES,
    _STORE_RE,
    _TERMINATOR_RE,
)

from .errors import (
    GateError,
    fail,
    fail_rule,
)

from .c_lexical import (
    _matching_brace,
    code_contains,
    code_find,
    code_positions,
    extract_function_body,
    function_span,
    function_text,
    names_identifier,
    parse_defines,
    require_define,
)

from .c_addresses import (
    _bindings,
    _bracket_pairs,
    _evaluate_constant,
    _flatten_address,
    _is_cast_parenthesis,
    _split_top_level,
    _statement_end,
    _token_before,
    access_expressions,
    assignment_statements,
    cmd_write_values,
    compound_assignment_targets,
    dereference_sites,
    enclosing_function,
    extract_loop,
    file_scope_text,
    function_spans,
    mmio_macro_table,
    pointer_roles,
    register_access_sites,
    require_no_macro_mmio,
    require_resolved_dereferences,
    require_resolved_pointers,
    split_block,
    statement_effects,
    store_pattern,
    submit_write_sites,
)


def _guard_blocks(block: str, subject: str) -> tuple[tuple[str, str], ...]:
    """Return ``(condition, body)`` for every ``if`` whose condition names ``subject``."""

    found = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])if\s*\(", block):
        depth = 0
        index = match.end() - 1
        while index < len(block):
            if block[index] == "(":
                depth += 1
            elif block[index] == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        condition = block[match.end() : index]
        tail = block[index + 1 :]
        stripped = tail.lstrip()
        if not stripped.startswith("{"):
            continue
        open_index = index + 1 + (len(tail) - len(stripped))
        close_index = _matching_brace(block, open_index, "guard body")
        if names_identifier(condition, subject):
            found.append((condition, block[open_index + 1 : close_index]))
    return tuple(found)


def require_load_provenance(
    body: str, name: str, load_sites: tuple[int, ...], register: str, what: str
) -> None:
    """Prove ``name`` holds the value the counted ``register`` load produced.

    Counting the loads and grepping the guards for the mask macros proves the
    two exist; it does not prove they are connected. ``pre_program_status = 0U``
    beside a discarded ``read_reg(NPU_REG_STATUS)`` satisfies both counts and
    turns a mandatory fail-closed gate into a comparison against a constant that
    always passes. So the assignment that produced the guarded value has to
    *be* one of the loads the gate counted, and nothing may overwrite it after.

    "Nothing may overwrite it" is a claim about the *storage*, not about the
    spelling of an lvalue. ``*(&pre_submit_status) = 0U`` writes the same word
    as ``pre_submit_status = 0U`` and matches no name-shaped pattern, so a rule
    written over the pattern lets the clearing store back in and every gate
    below it compares against zero. Two things therefore have to hold: every
    assignment whose lvalue mentions the name is written in the plain form this
    walk can order, and the name's address is never taken at all -- because a
    pointer to it is a second lvalue this intraprocedural walk cannot follow.
    """

    stepped = compound_assignment_targets(body, (name,))
    if stepped:
        raise fail(
            "%s: %s is compound-assigned rather than bound to the %s load it is gated on"
            % (what, name, register)
        )
    plain = re.compile(r"^\s*(?:[A-Za-z_]\w*\s+)*\*?\s*%s\s*$" % re.escape(name))
    for _start, lvalue, _rvalue in assignment_statements(body):
        if names_identifier(lvalue, name) and plain.match(lvalue) is None:
            raise fail(
                "%s: %s is written through an lvalue this gate cannot bind to its storage: %s"
                % (what, name, re.sub(r"\s+", " ", lvalue.strip())[:40])
            )
    if re.search(r"&\s*%s(?![A-Za-z0-9_])" % re.escape(name), body) is not None:
        raise fail(
            "%s: the address of %s is taken, so the %s load its guards are credited for can be "
            "overwritten through an alias this gate cannot follow" % (what, name, register)
        )
    assignments = [
        (start, _statement_end(body, start), rvalue)
        for start, lvalue, rvalue in assignment_statements(body)
        if plain.match(lvalue)
    ]
    if not assignments:
        raise fail("%s: %s is never assigned the %s load" % (what, name, register))
    loading = [
        assignment
        for assignment in assignments
        if any(assignment[0] <= site < assignment[1] for site in load_sites)
    ]
    if len(loading) != 1:
        raise fail(
            "%s: %s is not bound to the %s load this gate counted: %d of its %d assignments "
            "read the register" % (what, name, register, len(loading), len(assignments))
        )
    if any(start > loading[0][0] for start, _stop, _rvalue in assignments):
        raise fail(
            "%s: %s is reassigned after the %s load its guards are credited for"
            % (what, name, register)
        )


def queue_programming_sites(
    vendor_masked: str,
    defines: dict[str, int],
    scope: str,
    spans: tuple[tuple[str, int, int], ...],
) -> tuple[int, ...]:
    """Every site that programs the queue, whatever spelling reaches it.

    The frozen sources program the queue through ``write_reg``, and a scan for
    that call is what the single-owner rule was built on. A write through a
    bound pointer reaches the same register and carries no call for that scan to
    find, so a declarator was all it took to reprogram QSIZE in the cleanup tail
    while the gate still proved "queue programming lives in one function" about
    the call sites alone. The resolved write dereferences are therefore collected
    here beside the calls, per function, so a site is a site whichever spelling
    performs it.
    """

    sites = set(code_positions(vendor_masked, _QBASE_WRITE, open_end=True))
    sites.update(code_positions(vendor_masked, _QSIZE_WRITE))
    for _name, start, stop in spans:
        body = vendor_masked[start:stop]
        roles = pointer_roles(body, defines, scope)
        for site, role, is_write in dereference_sites(body, defines, roles):
            if is_write and role.startswith(_QUEUE_PROGRAMMING_ROLES):
                sites.add(start + site)
    return tuple(sorted(sites))


def _pre_program_gate_function(vendor_masked: str, spans) -> str:
    """The one function that carries the pre-program gate.

    The gate is found by the object it binds rather than by a function name, so
    it holds wherever the vendor keeps it -- and requiring exactly one owner is
    what keeps a second gate from being introduced somewhere the guards below
    are never applied to it.
    """

    owners = sorted(
        {
            name
            for name, start, stop in spans
            if code_positions(vendor_masked[start:stop], "pre_program_status")
        }
    )
    if not owners:
        raise fail("pre-program gate is missing: no function binds pre_program_status")
    if len(owners) != 1:
        raise fail("pre-program gate is split across %d functions: %s" % (len(owners), owners))
    return owners[0]


def verify_pre_run_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the stopped-state gate, the single QSIZE snapshot and fail-closed submit.

    Everything proved here is a property of the source text: which objects exist,
    how many loads there are, which guards consume them, and that each guard
    returns. Ordering and dominance are deliberately *not* proved here. They are
    control-flow properties, this module reads characters, and a rule that reads
    character order as execution order is wrong in exactly the case that matters
    -- mutually exclusive branches, and gates that sit in a caller. Those claims
    are bound on the linked image instead, and the keys returned below are named
    so that none of them can be read as a dominance proof.
    """

    if defines.get("V14_QSIZE_EXPECTED") != QSIZE_EXPECTED:
        raise fail(
            "qsize_expected is not manifest 0x110: V14_QSIZE_EXPECTED is %s"
            % ("undefined" if "V14_QSIZE_EXPECTED" not in defines else "0x%X" % defines["V14_QSIZE_EXPECTED"])
        )
    require_define(defines, "V14_STATUS_STATE", STATUS_STATE, "status mask contract")
    require_define(defines, "V14_STATUS_IRQ_RAISED", STATUS_IRQ_RAISED, "status mask contract")
    require_define(defines, "V14_STATUS_RESET", STATUS_RESET, "status mask contract")
    require_define(defines, "V14_STATUS_CMD_END", STATUS_CMD_END, "status mask contract")
    require_define(defines, "V14_STATUS_FAULT_MASK", STATUS_FAULT_MASK, "status mask contract")

    # The gate is anchored on whichever function actually programs the queue,
    # rather than on a function name, so the proof holds wherever the vendor
    # keeps its programming.
    mmio_macros, mmio_kinds = mmio_macro_table(vendor_masked)
    scope = file_scope_text(vendor_masked)
    spans = function_spans(vendor_masked)
    programming_sites = queue_programming_sites(vendor_masked, defines, scope, spans)
    if not programming_sites:
        raise fail("pre-program STATUS gate does not dominate QBASE/QSIZE: no queue programming found")
    owners = {enclosing_function(spans, site) for site in programming_sites}
    if len(owners) != 1:
        raise fail("queue programming is split across %d functions: %s" % (len(owners), sorted(owners)))
    programming_name = sorted(owners)[0]
    setup_start, setup_stop = function_span(vendor_masked, programming_name, "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]
    setup_roles = pointer_roles(setup, defines, scope)
    require_resolved_pointers(setup_roles, "queue setup function")
    require_resolved_dereferences(setup, defines, setup_roles, "the queue setup function")
    require_no_macro_mmio(setup, mmio_macros, "the queue setup function", mmio_kinds)

    # The gate is where ``pre_program_status`` is, which need not be the function
    # that programs the queue -- in the real vendor it is the caller. Anchoring
    # it on the programming function instead was a rule that only its own
    # fixtures could satisfy: it found the *post*-program load, called it the
    # gate, and reported the gate as late.
    gate_name = _pre_program_gate_function(vendor_masked, spans)
    gate_start, gate_stop = function_span(vendor_masked, gate_name, "pre-program gate function")
    gate = vendor_masked[gate_start:gate_stop]
    gate_roles = pointer_roles(gate, defines, scope)
    require_resolved_pointers(gate_roles, "pre-program gate function")
    require_resolved_dereferences(gate, defines, gate_roles, "the pre-program gate function")
    require_no_macro_mmio(gate, mmio_macros, "the pre-program gate function", mmio_kinds)

    pre_program_reads = register_access_sites(gate, "STATUS", defines, gate_roles)
    if len(pre_program_reads) != 1:
        raise fail_rule(
            RULE_PRE_PROGRAM_GATE_SHAPE,

            "pre-program gate does not read STATUS exactly once: %d loads in %s"
            % (len(pre_program_reads), gate_name)
        )

    # Whether the gate *dominates* the programming writes is a control-flow
    # property. Text order cannot decide it -- two sites in mutually exclusive
    # branches have an order here and no order at run time, which is how the
    # vendor's eU85_TEST0 pin-toggle writes to QBASE_LSB came to be read as
    # queue programming. What text can decide is that the gate and the
    # programming are connected at all, so that is what is claimed here; the
    # dominance proof itself is bound on the linked image.
    if gate_name != programming_name and not code_positions(gate, programming_name + "("):
        raise fail(
            "pre-program gate and queue programming are unconnected: %s neither programs the queue nor calls %s"
            % (gate_name, programming_name)
        )

    for mask, label in (
        ("V14_STATUS_STATE", "stopped"),
        ("V14_STATUS_RESET", "reset_status"),
        ("V14_STATUS_FAULT_MASK", "vendor fault"),
    ):
        guards = [c for c, _ in _guard_blocks(gate, "pre_program_status") if names_identifier(c, mask)]
        if len(guards) != 1:
            raise fail("pre-program gate omits stopped/reset/fault: %s check is missing" % label)

    require_load_provenance(
        gate, "pre_program_status", pre_program_reads, "STATUS", "pre-program gate"
    )

    # The design forbids a running transition between the gate and the
    # programming writes. That window is a control-flow span, and once the gate
    # and the programming can live in different functions the span is not a
    # range of characters in one of them. What is decidable here is the part of
    # the window inside the gate function: nothing may transition the state
    # after the gate load and before the function hands control on. The rest of
    # the window is bound on the linked image.
    after_gate = tuple(
        site
        for site, _value in cmd_write_values(gate, defines, gate_roles)
        if site > pre_program_reads[0]
    )
    if after_gate:
        raise fail(
            "state-transitioning CMD write after the pre-program gate in %s" % gate_name
        )

    qsize_writes = [
        site
        for site, role, is_write in dereference_sites(setup, defines, setup_roles)
        if is_write and role == "QSIZE"
    ] + list(code_positions(setup, _QSIZE_WRITE))
    if not qsize_writes:
        raise fail(
            "queue programming does not write QSIZE: the setup function programs QBASE only"
        )
    final_qsize_write = max(qsize_writes)
    for site in register_access_sites(setup, "QSIZE", defines, setup_roles):
        if site < final_qsize_write:
            raise fail("qsize snapshot precedes the final QSIZE programming write")

    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    command_roles = pointer_roles(command, defines, scope)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, mmio_macros, "the command function", mmio_kinds)

    qsize_loads = register_access_sites(command, "QSIZE", defines, command_roles)
    if len(qsize_loads) == 0:
        raise fail("qsize_expected snapshot is missing between final programming and submit")
    if len(qsize_loads) != 1:
        raise fail("QSIZE is loaded more than once: %d loads in the command path" % len(qsize_loads))

    # A submit is a CMD write that sets bit 0, whichever spelling sets it, so a
    # second start written as ``1`` rather than ``0x00000001`` -- or through a
    # raw CMD pointer -- is counted here rather than walked around.
    submits = submit_write_sites(command, defines, command_roles)
    if len(submits) != 1:
        raise fail(
            "command path does not carry exactly one NPU submit write: %d submit writes"
            % len(submits)
        )
    running_qsize_loads = tuple(site for site in qsize_loads if site > submits[0])
    if running_qsize_loads:
        raise fail("running QSIZE reachable: the QSIZE load follows the submit write")
    # This comparison is over ``test_commands`` only, which is what the manifest
    # key below is named for. The claim that no QSIZE access is reachable from the
    # running window at all is a different proof and belongs to
    # ``require_register_confinement``, which scans the whole translation unit.

    # Only the window up to submit belongs to the pre-run gate; STATUS reads
    # after submit are the tail's business and are judged by the cleanup gate.
    status_loads = tuple(
        site
        for site in register_access_sites(command, "STATUS", defines, command_roles)
        if site < submits[0]
    )
    if len(status_loads) != 1:
        raise fail(
            "post-program STATUS load is not distinct from the pre-program load: %d loads"
            % len(status_loads)
        )

    qsize_compare = _guard_blocks(command, "qsize_expected")
    if not any(names_identifier(condition, "V14_QSIZE_EXPECTED") for condition, _ in qsize_compare):
        raise fail("qsize_expected is not manifest 0x110: no compare against V14_QSIZE_EXPECTED")

    pre_submit_guards = _guard_blocks(command, "pre_submit_status")
    for mask, label in _PRE_SUBMIT_GATES:
        if not any(names_identifier(condition, mask) for condition, _ in pre_submit_guards):
            raise fail("post-program stale/reset/fault gate is incomplete: %s check is missing" % label)

    for condition, body in tuple(qsize_compare) + pre_submit_guards:
        if not names_identifier(body, "return"):
            raise fail("pre-run failure reaches submit: guard (%s) does not return" % condition.strip()[:40])

    # Both post-program gates are credited for a load; prove each consumes the
    # one this gate counted rather than a constant beside a discarded read.
    require_load_provenance(
        command, "pre_submit_status", status_loads, "STATUS", "post-program gate"
    )
    require_load_provenance(
        command, "qsize_expected", qsize_loads, "QSIZE", "qsize_expected snapshot"
    )

    return {
        "pre_program_status_loads": len(pre_program_reads),
        "post_program_status_loads": len(status_loads),
        "qsize_loads": len(qsize_loads),
        "qsize_expected": "0x%08X" % QSIZE_EXPECTED,
        # Named for the scope it is actually taken over. The whole-unit claim is
        # ``vendor_register_designations_confined``.
        "running_qsize_loads_in_test_commands": len(running_qsize_loads),
        # Where the two halves of the pre-run contract were found, so a reader
        # can see whether they were in one function or two without rerunning
        # anything.
        "pre_program_gate_function": gate_name,
        "queue_programming_function": programming_name,
        # What this gate did and did not prove, in the manifest rather than in a
        # comment, because a consumer reads the manifest.
        "pre_run_source_scope": "shape_only_no_control_flow",
        "pre_run_dominance_deferred_to": (
            "linked-image proof: pre-program gate dominates every QBASE/QSIZE write, "
            "and no state transition occurs between them"
        ),
    }


def verify_loop_header(
    head: str,
    roles: dict[str, str],
    what: str,
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> None:
    """Reject a ``for`` head that carries anything but induction arithmetic."""

    clauses = _split_top_level(head, ";")
    if len(clauses) != 3:
        raise fail("%s: loop head is not a three-clause bounded for" % what)
    induction = set(_INDUCTION_DECL_RE.findall(clauses[0]))
    for clause in clauses:
        effects = statement_effects(clause, roles, store_re, defines)
        if effects:
            raise fail(
                "%s head carries a per-iteration effect: (%s) carries %s"
                % (what, re.sub(r"\s+", " ", head.strip())[:60], ", ".join(sorted(set(effects))))
            )
        for identifier in _IDENTIFIER_RE.findall(clause):
            if identifier in induction or identifier in _INDUCTION_ALLOWED:
                continue
            raise fail(
                "%s head observes %s outside the induction variable: (%s)"
                % (what, identifier, re.sub(r"\s+", " ", head.strip())[:60])
            )


def _label_statements(block: str, depth: int = 0) -> tuple[str, ...]:
    """Every statement in ``block``, at any depth, that opens with a label."""

    if depth > _MAX_NESTING_DEPTH:
        raise fail(
            "block nesting is deeper than the %d levels this gate walks" % _MAX_NESTING_DEPTH
        )
    found: list[str] = []
    for kind, headline, nested in split_block(block):
        match = _LABEL_RE.match(headline.strip())
        if match is not None and match.group(1) not in _LABEL_KEYWORDS:
            found.append(match.group(1))
        if kind == "block":
            found.extend(_label_statements(nested, depth + 1))
    return tuple(found)


def verify_single_bounded_loop(body: str, what: str) -> None:
    """Reject any polling construct other than the one bounded ``for``.

    ``extract_loop`` already refuses a second ``for``, braceless or not. This
    adds the constructs brace matching does not see as loops at all: a ``while``
    or ``do`` anywhere in the helper -- before the bounded loop, after it, or
    nested inside it -- and a ``goto``/label pair, which can both re-enter the
    loop and jump *into* the middle of a guard whose exemption was granted on
    the assumption that its condition is the only way in.
    """

    extra = _EXTRA_LOOP_RE.search(body)
    if extra is not None:
        raise fail(
            "%s: an unbounded %s polling loop is reachable beside the bounded for"
            % (what, extra.group(1))
        )
    if _GOTO_RE.search(body) is not None:
        raise fail("%s: a goto back-edge is reachable beside the bounded for" % what)
    labels = _label_statements(body)
    if labels:
        raise fail(
            "%s: label %s makes the loop or a guard body multi-entry" % (what, labels[0])
        )


def verify_no_loop_back_edge(loop_body: str, what: str) -> None:
    """Reject a ``continue`` path back to the loop head.

    ``verify_guard_publication`` already refuses one inside an effect-carrying
    guard, where it is the mechanism that turns a published tuple into a
    per-iteration store. This refuses the rest of them: the canonical loop
    leaves by ``break`` or ``return`` and by nothing else, so a ``continue``
    anywhere in it is a control path the ordered-effect model does not describe.
    """

    if _CONTINUE_RE.search(loop_body) is not None:
        raise fail("%s: a continue statement reaches the loop back-edge" % what)


def flatten_loop(block: str, what: str) -> tuple[tuple[int, str, str, str], ...]:
    """Return every reachable item of a loop body as ``(depth, kind, head, body)``.

    ``depth`` 0 is the loop body itself, so a depth-0 item runs on every
    iteration and a deeper one only on the iteration that takes its branch. The
    walk recurses, so no statement can hide behind an earlier guard, and every
    nested block has to be an ``if``/``else`` guard -- a bare block or a nested
    loop would let a per-iteration effect masquerade as a guard body.
    """

    items: list[tuple[int, str, str, str]] = []

    def walk(text: str, depth: int) -> None:
        if depth > _MAX_NESTING_DEPTH:
            raise fail(
                "%s: guard nesting is deeper than the %d levels this gate walks"
                % (what, _MAX_NESTING_DEPTH)
            )
        for kind, headline, nested in split_block(text):
            if kind == "stmt":
                items.append((depth, "stmt", headline, ""))
                continue
            head = headline.strip()
            if _GUARD_HEAD_RE.match(head) is None:
                raise fail("%s: nested block %r is not an if/else guard" % (what, head[:40] or "{}"))
            items.append((depth, "guard", head, nested))
            walk(nested, depth + 1)

    walk(block, 0)
    return tuple(items)


def subtree_effects(
    body: str,
    roles: dict[str, str],
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
    depth: int = 0,
) -> tuple[str, ...]:
    """Return every effect carried anywhere inside ``body``, at any depth.

    ``split_block`` keeps a braceless ``if`` inside its own statement text, so
    scanning both the statement text and every nested block reaches an effect
    however it is written.
    """

    if depth > _MAX_NESTING_DEPTH:
        raise fail(
            "block nesting is deeper than the %d levels this gate walks" % _MAX_NESTING_DEPTH
        )
    effects: list[str] = []
    for kind, headline, nested in split_block(body):
        effects.extend(statement_effects(headline, roles, store_re, defines))
        if kind == "block":
            effects.extend(subtree_effects(nested, roles, store_re, defines, depth + 1))
    return tuple(effects)


def terminates_iteration(body: str) -> bool:
    """True when control cannot fall off the end of ``body`` into the back-edge.

    The proof is structural: the last statement of the body is a ``break`` or a
    ``return``, so every path that runs to the end of the guard leaves the loop
    rather than starting another iteration.
    """

    items = split_block(body)
    if not items:
        return False
    kind, headline, _ = items[-1]
    return kind == "stmt" and _TERMINATOR_RE.match(headline.strip()) is not None


def verify_guard_publication(
    head: str,
    body: str,
    roles: dict[str, str],
    what: str,
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> None:
    """Reject a loop guard body that carries an effect it cannot own.

    A guard body runs only on the iteration that takes its branch -- but that
    says nothing about *how many* iterations there are. An always-true guard,
    or one whose body simply falls through to the back-edge, runs its body on
    every iteration and so carries a per-iteration store, call or timestamp
    exactly as a depth-0 statement would. The exemption therefore has to be
    earned rather than assumed: the effects the body carries must be the
    canonical result publication and its timestamp, and the iteration must end
    in a ``break`` or a ``return`` before any path can reach the back-edge.
    """

    carried = tuple(
        effect
        for effect in subtree_effects(body, roles, store_re, defines)
        if effect.startswith(_CARRIED_EFFECT_PREFIXES)
    )
    if not carried:
        return
    condition = re.sub(r"\s+", " ", head.strip())[:60]
    foreign = sorted({effect for effect in carried if effect not in _CANONICAL_GUARD_EFFECTS})
    if foreign:
        raise fail(
            "%s guard body carries a non-publication effect: (%s) carries %s"
            % (what, condition, ", ".join(foreign))
        )
    back_edge = _BACK_EDGE_RE.search(body)
    if back_edge is not None:
        raise fail(
            "%s guard body carries a per-iteration effect: (%s) reaches the loop back-edge "
            "through %s" % (what, condition, back_edge.group(1))
        )
    if not terminates_iteration(body):
        raise fail(
            "%s guard body carries a per-iteration effect: (%s) does not end the iteration "
            "with a break or a return" % (what, condition)
        )


def _peel_parens(text: str) -> str:
    """Strip parentheses that wrap the whole expression."""

    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        depth = 0
        for index, character in enumerate(stripped):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    break
        if index != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
    return stripped


def _split_logical(text: str, operator: str) -> tuple[str, ...]:
    """Split ``text`` on ``&&`` or ``||`` at paren depth zero."""

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and text[index : index + 2] == operator:
            parts.append("".join(buffer))
            buffer = []
            index += 2
            continue
        buffer.append(character)
        index += 1
    parts.append("".join(buffer))
    return tuple(parts)


def logical_structure(condition: str) -> tuple[str, tuple[str, ...]]:
    """``(connective, terms)`` at the outermost level of ``condition``.

    ``&&`` binds tighter than ``||``, so a top-level ``||`` is the connective
    even when conjunctions sit under it. A leaf comes back as ``("", (leaf,))``.
    """

    peeled = _peel_parens(condition)
    disjuncts = _split_logical(peeled, "||")
    if len(disjuncts) > 1:
        return "||", disjuncts
    conjuncts = _split_logical(peeled, "&&")
    if len(conjuncts) > 1:
        return "&&", conjuncts
    return "", (peeled,)


def guard_condition(head: str, what: str) -> str:
    """The text inside a guard head's parentheses."""

    open_index = head.find("(")
    if open_index < 0:
        raise fail("%s: guard head carries no condition: %s" % (what, head.strip()[:40]))
    depth = 0
    for index in range(open_index, len(head)):
        if head[index] == "(":
            depth += 1
        elif head[index] == ")":
            depth -= 1
            if depth == 0:
                return head[open_index + 1 : index]
    raise fail("%s: guard head has unbalanced parentheses" % what)


def _split_comparison(text: str) -> tuple[str, str, str] | None:
    depth = 0
    for index, character in enumerate(text):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in "!=" and text[index + 1 : index + 2] == "=":
            if character == "=" and text[index - 1 : index] in ("=", "!", "<", ">"):
                continue
            return text[:index], text[index : index + 2], text[index + 2 :]
    return None


def classify_predicate_leaf(leaf: str, defines: dict[str, int]) -> tuple[object, ...] | None:
    """The named boolean a leaf computes, bound to the value that drives it.

    ``None`` means the leaf is not one of the same-iteration observations this
    contract knows, which every caller refuses rather than ignores: a term
    nothing here can name is a term no exit rule covers.
    """

    parts = _split_comparison(_peel_parens(leaf))
    if parts is None:
        return None
    left, operator, right = parts
    left_tokens = tuple(_C_TOKEN_RE.findall(_peel_parens(left)))
    if left_tokens == ("qread",):
        if tuple(_C_TOKEN_RE.findall(_peel_parens(right))) != ("qsize_expected",):
            return None
        return ("q_done", operator)
    if len(left_tokens) != 3 or left_tokens[0] != "status" or left_tokens[1] != "&":
        return None
    mask = defines.get(left_tokens[2])
    value = _evaluate_constant(right, defines)
    if mask is None or value is None or mask not in _STATUS_BOOLEAN_NAMES:
        return None
    return (_STATUS_BOOLEAN_NAMES[mask], operator, value)


def verify_predicate_shape(
    condition: str,
    connective: str,
    required: tuple[tuple[object, ...], ...],
    defines: dict[str, int],
    what: str,
) -> tuple[tuple[object, ...], ...]:
    """Prove ``condition`` joins exactly ``required`` with exactly ``connective``."""

    observed_connective, terms = logical_structure(condition)
    if observed_connective != connective:
        raise fail(
            "%s does not join its terms with %s: it uses %s"
            % (
                what,
                connective or "a single term",
                observed_connective or "a single term",
            )
        )
    classified: list[tuple[object, ...]] = []
    for term in terms:
        if logical_structure(term)[0]:
            raise fail("%s carries a nested boolean term: %s" % (what, term.strip()[:40]))
        leaf = classify_predicate_leaf(term, defines)
        if leaf is None:
            raise fail(
                "%s carries a term this gate cannot bind to an observed value: %s"
                % (what, term.strip()[:40])
            )
        classified.append(leaf)
    if sorted(classified, key=repr) != sorted(required, key=repr):
        raise fail(
            "%s is not the frozen tuple of observations: it decides on %s"
            % (what, sorted(classified, key=repr))
        )
    return tuple(classified)


def _duplicate_roles(read_order: list[str]) -> list[str]:
    return sorted({role for role in read_order if read_order.count(role) > 1})


def _guard_kind(condition: str) -> str:
    if names_identifier(condition, "V14_STATUS_RESET"):
        return "reset"
    if names_identifier(condition, "V14_STATUS_FAULT_MASK"):
        return "fault"
    if names_identifier(condition, "qsize_expected"):
        return "completion"
    return "other"


def _publishing_guards(
    items: tuple[tuple[int, str, str, str], ...],
    roles: dict[str, str],
    store_re: re.Pattern[str],
    defines: dict[str, int],
) -> tuple[tuple[str, str], ...]:
    """Every depth-0 guard of a loop whose subtree stores anything."""

    return tuple(
        (head, body)
        for depth, kind, head, body in items
        if depth == 0
        and kind == "guard"
        and "store" in subtree_effects(body, roles, store_re, defines)
    )


def verify_publishing_guards(
    guards: tuple[tuple[str, str], ...],
    required: dict[str, tuple[str, str, tuple[tuple[object, ...], ...]]],
    defines: dict[str, int],
    what: str,
    kinds: tuple[str, ...] | None = None,
) -> None:
    """Prove every publishing guard is a known kind joined exactly as its kind is.

    ``guards[kinds.index("completion")]`` checks one guard. It says nothing
    about the guard beside it, and a loop may carry as many as it likes: an
    extra ``if (i > 5U)`` that publishes the frozen success tuple exits on an
    iteration count, and a reset guard rewritten as
    ``((status & RESET) != 0U) || (i > 5U)`` keeps its classification while
    deciding on something else entirely. Both publish evidence about a
    measurement the source does not make, so every publishing guard earns its
    exit here rather than the first one of each name.
    """

    seen: list[str] = []
    for index, (head, _body) in enumerate(guards):
        condition = head.strip()
        if _GUARD_HEAD_RE.match(condition) is None or "(" not in condition:
            raise fail(
                "%s publishes from a guard with no condition this gate can bind: %s"
                % (what, condition[:40] or "else")
            )
        kind = kinds[index] if kinds is not None else _guard_kind(guard_condition(head, what))
        if kind not in required:
            raise fail(
                "%s publishes from a guard whose condition is not a contract predicate: %s"
                % (what, re.sub(r"\s+", " ", condition)[:60])
            )
        label, connective, terms = required[kind]
        verify_predicate_shape(guard_condition(head, what), connective, terms, defines, label)
        seen.append(kind)
    missing = sorted(set(required) - set(seen))
    if missing:
        raise fail("%s has no %s predicate" % (what, missing[0]))
    duplicated = sorted({kind for kind in seen if seen.count(kind) > 1})
    if duplicated:
        raise fail(
            "%s publishes from more than one %s guard: %d"
            % (what, duplicated[0], seen.count(duplicated[0]))
        )


def _q_timeout_classification(
    after_loop: str, roles: dict[str, str], defines: dict[str, int]
) -> list[str]:
    """Prove the one post-timeout STATUS load classifies reset and every fault bit.

    Q's loop never reads STATUS, so the timeout tail's single diagnostic load is
    the only evidence there is about *why* the queue never drained. It has to
    separate reset from a hardware fault, and it has to test the whole pinned
    0x314 mask rather than a subset, or a fault bit silently reports as a plain
    timeout.
    """

    status_pointers = [name for name, role in roles.items() if role == "STATUS"]
    if not status_pointers:
        raise fail("Q timeout diagnostic STATUS read is missing or duplicated: 0 named loads")
    targets = re.findall(
        r"([A-Za-z_]\w*)\s*=\s*\*\s*(?:%s)(?![A-Za-z0-9_])"
        % "|".join(re.escape(name) for name in status_pointers),
        after_loop,
    )
    if len(targets) != 1:
        raise fail(
            "Q timeout diagnostic STATUS read is missing or duplicated: %d named loads" % len(targets)
        )

    guards = _guard_blocks(after_loop, targets[0])
    # One guard that tests both the reset bit and the fault mask cannot report
    # which of the two it found, so it is a contract rejection with a name --
    # not an ordering question, and never a traceback out of ``index``.
    if any(
        names_identifier(condition, "V14_STATUS_RESET")
        and names_identifier(condition, "V14_STATUS_FAULT_MASK")
        for condition, _body in guards
    ):
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "one guard tests both the reset bit and the fault mask"
        )
    reset = [
        c
        for c, b in guards
        if names_identifier(c, "V14_STATUS_RESET") and names_identifier(b, "V14_PRIMARY_RESET")
    ]
    fault = [
        c
        for c, b in guards
        if names_identifier(c, "V14_STATUS_FAULT_MASK") and names_identifier(b, "V14_PRIMARY_FAULT")
    ]
    if len(reset) != 1:
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: %d guards"
            % len(reset)
        )
    if len(fault) != 1:
        raise fail(
            "Q timeout diagnostic does not classify every 0x%03X fault bit from the diagnostic "
            "STATUS load: %d guards test the pinned mask" % (defines["V14_STATUS_FAULT_MASK"], len(fault))
        )
    kinds = [_guard_kind(condition) for condition, _ in guards]
    if "reset" not in kinds or "fault" not in kinds:
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "the reset and fault tests are not two separate guards"
        )
    if kinds.index("reset") > kinds.index("fault"):
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "the fault test comes first"
        )
    return ["reset:0x%03X" % defines["V14_STATUS_RESET"]] + [
        "fault:0x%03X" % bit
        for bit in (1 << shift for shift in range(32))
        if defines["V14_STATUS_FAULT_MASK"] & bit
    ]


def verify_primary_contract(
    vendor_masked: str, variant: str, defines: dict[str, int]
) -> dict[str, object]:
    """Prove the per-variant primary observation loop."""

    if defines.get("V14_ITERATION_BOUND") != ITERATION_BOUND:
        raise fail("primary loop bound is not 10000: V14_ITERATION_BOUND is %r" % defines.get("V14_ITERATION_BOUND"))

    defined = []
    for name in PRIMARY_SYMBOL.values():
        try:
            extract_function_body(vendor_masked, name, name)
        except GateError:
            continue
        defined.append(name)
    wanted = PRIMARY_SYMBOL[variant]
    if wanted not in defined:
        raise fail("primary helper %s is missing" % wanted)
    for name in defined:
        if name != wanted:
            raise fail("inactive primary helper is reachable: %s" % name)

    body = function_text(vendor_masked, wanted, "primary helper")
    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
    require_resolved_pointers(roles, "primary helper")
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in a primary loop: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "primary loop")
    if not names_identifier(head, "V14_ITERATION_BOUND"):
        raise fail("primary loop bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "primary helper")
    verify_loop_header(head, roles, "primary loop", store_re, defines)
    # After the loop-shape rules, so each keeps its own rejection: what is left
    # for this to name is an address written where it stands, which the ordered
    # effect sequence below would otherwise carry as an unnamed load.
    require_resolved_dereferences(body, defines, roles, "the primary helper")
    require_no_macro_mmio(body, *mmio_macro_table(vendor_masked)[:1], "the primary helper",
                          mmio_macro_table(vendor_masked)[1])

    items = flatten_loop(loop_body, "primary loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    expected = ["QREAD"] if variant == "Q" else EXPECTED_PRIMARY_ORDER[variant]
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re, defines)
        if depth:
            # A guard body that has earned its exemption publishes the frozen
            # success tuple, so a store or a timestamp here is that tuple rather
            # than a per-iteration effect. A reload is still forbidden: it would
            # unfreeze the tuple.
            for effect in effects:
                if effect == "qsize":
                    raise fail("QSIZE access reachable in a primary loop")
                if effect.startswith("load:"):
                    raise fail("primary success tuple is re-read rather than frozen")
            continue
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in a primary loop")
        if any(effect in ("timestamp", "store") or effect.startswith("call:") for effect in effects):
            raise fail(
                "primary loop carries a per-iteration store/call/timestamp: %s" % head.strip()[:50]
            )
        for effect in effects:
            if effect.startswith("load:"):
                role = effect.split(":", 1)[1]
                read_order.append(role)
                if branched:
                    loads_after_branch.append(role)
        if kind == "guard":
            guard_bodies.append((head, guard_body))
            branched = True

    # The exemption the depth check above grants is only sound for a guard that
    # provably ends its iteration. Prove it rather than assume it -- after the
    # per-statement rules above, so each keeps its own rejection.
    for head, guard_body in guard_bodies:
        verify_guard_publication(head, guard_body, roles, "primary loop", store_re, defines)
    verify_no_loop_back_edge(loop_body, "primary loop")

    if variant == "Q" and "STATUS" in read_order:
        raise fail("Q primary loop reads STATUS")
    duplicates = _duplicate_roles(read_order)
    if duplicates:
        raise fail(
            "primary loop reloads %s: the exit predicate must come from one load per register"
            % ", ".join(duplicates)
        )
    # A read that exists in the loop but only downstream of a branch is a
    # short-circuit exit, not a missing read: the two cases need different names
    # because they need different fixes.
    if loads_after_branch and read_order == expected:
        raise fail("primary predicate is evaluated before both reads")
    if read_order != expected:
        raise fail(
            "%s primary read order is not %s: observed %s"
            % (variant, " then ".join(expected), read_order or ["nothing"])
        )

    # ``else if`` is a depth-0 guard exactly as ``if`` is, and a filter that
    # only knows the one spelling leaves the other unclassified -- which is to
    # say unchecked, by every ordering and predicate rule below.
    guards = [
        (_guard_kind(head), head)
        for depth, kind, head, _ in items
        if depth == 0 and kind == "guard" and _GUARD_HEAD_RE.match(head) and "(" in head
    ]

    kinds = [kind for kind, _ in guards]
    if "completion" not in kinds:
        raise fail("primary loop has no completion predicate")
    if variant == "Q":
        # The substring ``STATUS`` also names ``V14_STATUS_*`` and
        # ``NPU_REG_STATUS``; it does not name the local ``status`` that holds a
        # STATUS load, which is the one spelling the rule most needs to see.
        if any(
            names_identifier(condition, "status")
            or re.search(r"(?<![A-Za-z0-9_])(?:V14_STATUS_|NPU_REG_STATUS)", condition)
            for _, condition in guards
        ):
            raise fail("Q primary loop reads STATUS")
    else:
        for required in ("reset", "fault"):
            if required not in kinds:
                raise fail(
                    "reset/fault check does not dominate the primary completion predicate: %s guard is missing"
                    % required
                )
            if kinds.index(required) > kinds.index("completion"):
                raise fail(
                    "reset/fault check does not dominate the primary completion predicate: %s guard follows it"
                    % required
                )
        completion = guards[kinds.index("completion")][1]
        if not names_identifier(completion, "V14_STATUS_CMD_END"):
            raise fail("primary completion predicate does not use cmd_end_reached bit5")
        if names_identifier(completion, "V14_STATUS_IRQ_RAISED"):
            raise fail("irq_raised bit1 is used as a primary exit predicate")

    # Which terms the exit tests is not what it decides. ``q_done && s_done``
    # names the same two observations as ``q_done || s_done`` and can only ever
    # report SAME_ITERATION, so the connective is proven rather than assumed --
    # and the categories the manifest publishes are read off that proof.
    completion_condition = guard_condition(guards[kinds.index("completion")][1], "primary loop")
    if variant == "Q":
        completion_terms = verify_predicate_shape(
            completion_condition, "", (("q_done", "=="),), defines,
            "the Q primary completion predicate",
        )
    else:
        completion_terms = verify_predicate_shape(
            completion_condition, "||", PRIMARY_COMPLETION_PREDICATE, defines,
            "the primary completion predicate",
        )
    # Every guard that publishes earns its exit, not just the first one named
    # ``completion``. Without this an extra guard -- before the real one, after
    # it, or spelled ``else if`` -- writes the frozen OBSERVED tuple on an
    # arbitrary condition, and a reset guard rewritten as
    # ``((status & RESET) != 0U) || (i > 5U)`` keeps its classification while
    # deciding on an iteration count. The manifest would then report
    # first-observation evidence about a measurement the source never made.
    if variant == "Q":
        required_guards = {
            "completion": ("the Q primary completion predicate", "", (("q_done", "=="),)),
        }
    else:
        required_guards = {
            "reset": ("the primary reset predicate", "", _RESET_PREDICATE),
            "fault": ("the primary fault predicate", "", _FAULT_PREDICATE),
            "completion": (
                "the primary completion predicate",
                "||",
                PRIMARY_COMPLETION_PREDICATE,
            ),
        }
    publishing = _publishing_guards(items, roles, store_re, defines)
    verify_publishing_guards(publishing, required_guards, defines, "primary loop")
    observed_publishers = [
        head
        for head, guard_body in publishing
        if names_identifier(guard_body, "V14_PRIMARY_OBSERVED")
    ]
    if len(observed_publishers) != 1 or _guard_kind(
        guard_condition(observed_publishers[0], "primary loop")
    ) != "completion":
        raise fail(
            "V14_PRIMARY_OBSERVED is published from a guard that is not the completion "
            "predicate: %d publishing guards write it" % len(observed_publishers)
        )

    categories: list[str] = []
    if len(completion_terms) > 1:
        categories = sorted(_FIRST_OBSERVATION_CATEGORY[name] for name, *_rest in completion_terms)
        categories.append("SAME_ITERATION")

    # Everything before the loop and everything after it is outside authoritative
    # timing; only Q may touch STATUS there, and only once.
    after_loop = body[loop_stop:]
    outside = body[:loop_start] + after_loop
    diagnostic_loads = len(
        re.findall(
            r"\*\s*(?:%s)(?![A-Za-z0-9_])"
            % "|".join(re.escape(name) for name, role in roles.items() if role == "STATUS"),
            outside,
        )
    )
    classification: list[str] = []
    if variant == "Q":
        if diagnostic_loads != 1:
            raise fail(
                "Q timeout diagnostic STATUS read is missing or duplicated: %d loads" % diagnostic_loads
            )
        classification = _q_timeout_classification(after_loop, roles, defines)
    elif diagnostic_loads != 0:
        raise fail("%s primary helper reads STATUS outside its loop: %d loads" % (variant, diagnostic_loads))

    if code_contains(after_loop, "DWT->CYCCNT"):
        raise fail("%s timeout path publishes a first-observation timestamp" % variant)
    if names_identifier(body, CONVERGE_SYMBOL):
        raise fail("%s timeout path reaches the convergence tail" % variant)

    fault_bits = [bit for bit in (1 << shift for shift in range(32)) if defines["V14_STATUS_FAULT_MASK"] & bit]
    return {
        "primary_helper": wanted,
        "primary_read_order": expected,
        "primary_bound": ITERATION_BOUND,
        "valid_iteration_range": [1, ITERATION_BOUND],
        "fault_bits_gated": fault_bits,
        "reset_bit_gated": defines["V14_STATUS_RESET"],
        "q_timeout_classification": classification,
        "q_timeout_diagnostic_status_loads": diagnostic_loads,
        "first_observation_categories": categories,
        "primary_completion_predicate_connective": logical_structure(completion_condition)[0],
        "primary_completion_predicate_terms": [list(term) for term in completion_terms],
    }


def verify_hard_bypass_contract(vendor_masked: str) -> dict[str, object]:
    """Prove the retained V12/V13 stock vector and NVIC hard bypass."""

    install = "NVIC_SetVector(NPU0_IRQn, (uint32_t)&%s)" % STOCK_VECTOR_SYMBOL
    install_sites = code_positions(vendor_masked, install)
    if len(install_sites) != 1:
        raise fail("runtime vector is not the exact stock u85_irq_handler")

    spans = function_spans(vendor_masked)
    setup_start, setup_stop = function_span(
        vendor_masked, enclosing_function(spans, install_sites[0]), "runtime setup function"
    )
    setup = vendor_masked[setup_start:setup_stop]
    observed = []
    for probe in HARD_BYPASS_PROBE_ORDER:
        site = code_find(setup, probe + "(")
        if site >= 0:
            observed.append((site, probe))
    ordering = [probe for _, probe in sorted(observed)]
    if ordering != list(HARD_BYPASS_PROBE_ORDER):
        raise fail("NVIC hard-bypass probe ordering drifted: observed %s" % ordering)

    enable_sites = code_positions(vendor_masked, "NVIC_EnableIRQ(") + code_positions(
        vendor_masked, "__NVIC_EnableIRQ("
    )
    if enable_sites:
        raise fail("reachable NVIC_EnableIRQ")
    # ``NVIC->ISER[0] = 1UL`` and ``((NVIC_Type *)0xE000E100UL)->ISER[0] = 1UL``
    # enable the same interrupt; only the spelling of the base differs. The NPU
    # registers get full address provenance, so the NVIC gets the same
    # treatment: the register name is refused as a token, and so is the address
    # written as a number.
    if names_identifier(vendor_masked, "ISER"):
        raise fail("direct NVIC ISER enable write is reachable")
    for match in re.finditer(r"(?<![A-Za-z0-9_.])(0[xX][0-9A-Fa-f]+|\d+)[uUlL]*", vendor_masked):
        try:
            literal = int(match.group(1), 0)
        except ValueError:  # pragma: no cover - the pattern only matches literals
            continue
        if NVIC_ISER_BASE <= literal < NVIC_ISER_BASE + NVIC_ISER_BYTES:
            raise fail("direct NVIC ISER enable write is reachable")
    # A literal scan only refuses the address written as *one* number.
    # ``V14_NVIC_LO + 0x100U`` reaches the same register and contains no literal
    # in the window, so every access expression in the file is folded against it
    # here. This runs file-wide on purpose: ``require_resolved_dereferences``
    # covers four functions, and a helper called from ``test_commands`` is
    # neither of them -- which is exactly where the computed address went.
    defines = parse_defines(vendor_masked)
    # An address *bound* in a declarator never appears as an access expression:
    # ``*const iser[1] = { (volatile uint32_t *)(0xE000E000UL + 0x100UL) }`` puts
    # the cast in the initializer and leaves the write spelled ``*iser[0]``,
    # which carries no cast for this fold to recognise. The bindings are folded
    # here for the same reason the accesses are -- the register is reached
    # either way, and only the spelling differs.
    candidates = [
        (site, expression) for site, expression, _is_write in access_expressions(vendor_masked)
    ]
    # Both binding forms, through the same walk every other rule reads them
    # with, so a nested-brace or comma-separated declarator is folded here too.
    # A binding carries the name it bound rather than an offset, because the
    # walk resolves a declarator to its elements and an element has no single
    # site the way an access expression does.
    for name, expression in _bindings(vendor_masked):
        candidates.append(("the binding of %s" % name, expression))
    for site, expression in candidates:
        if _POINTER_CAST_RE.search(expression) is None:
            continue
        value = _evaluate_constant(_flatten_address(expression), defines)
        if value is None:
            continue
        if NVIC_ISER_BASE <= (value & 0xFFFFFFFF) < NVIC_ISER_BASE + NVIC_ISER_BYTES:
            raise fail(
                "direct NVIC ISER enable write is reachable: computed address at %s"
                % (site if isinstance(site, str) else "offset %d" % site)
            )

    # ``irq_triggered = 1`` sets the same flag ``irq_triggered = true`` does. The
    # rule is about the value the flag can take on a measured path, so it is the
    # assigned value that decides, not the spelling of the constant -- and a
    # compound assignment sets it without ever writing a plain one.
    stepped = compound_assignment_targets(vendor_masked, ("irq_triggered",))
    if stepped:
        raise fail("irq_triggered can become true on a measured path: sites ['<compound assignment>']")
    # ``*trig_alias = true`` sets the flag without ever spelling its name on the
    # left of an ``=``, so the site walk below never sees it and the manifest
    # keeps publishing the handler as the only writer. The values this file
    # gates already refuse address-taking through ``require_load_provenance``;
    # the flag gets the same treatment. The stock handler assigns it directly
    # and needs no pointer to it, so refusing every ``&irq_triggered`` costs the
    # contract nothing and closes the alias for good.
    _open_of = _bracket_pairs(vendor_masked)[1]
    for match in re.finditer(r"&\s*(?:\(\s*)*irq_triggered(?![A-Za-z0-9_])", vendor_masked):
        # ``mask & irq_triggered`` reads the flag; only address-of aliases it.
        previous = _token_before(vendor_masked, match.start())[1]
        cursor = match.start() - 1
        while cursor >= 0 and vendor_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if previous:
            continue
        if cursor >= 0 and vendor_masked[cursor] in _OPERAND_END_CHARACTERS:
            # A cast's closing parenthesis is not the end of an operand, so
            # ``(bool *)&irq_triggered`` takes the address the same way a bare
            # ``&irq_triggered`` does. Reading the two alike is what let the
            # alias be bound and the flag set through it, with the manifest still
            # publishing the stock handler as the flag's only writer.
            opening = _open_of.get(cursor) if vendor_masked[cursor] == ")" else None
            if opening is None or not _is_cast_parenthesis(vendor_masked, opening, cursor):
                continue
        raise fail(
            "irq_triggered can become true on a measured path: sites ['<address taken at offset %d>']"
            % match.start()
        )
    sites = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])irq_triggered\s*=(?!=)([^;]*);", vendor_masked):
        if match.group(1).strip() in _IRQ_TRIGGERED_CLEARED:
            continue
        sites.append(enclosing_function(spans, match.start()))
    if sorted(set(sites)) != [STOCK_VECTOR_SYMBOL]:
        raise fail("irq_triggered can become true on a measured path: sites %s" % sorted(set(sites)))
    if not re.search(
        r"(?<![A-Za-z0-9_])irq_triggered\s*=(?!=)\s*(?:false|0[uU]?)\s*;", setup
    ):
        raise fail("NVIC hard-bypass probe ordering drifted: irq_triggered is not cleared before the probes")

    return {
        "installed_vector_symbol": STOCK_VECTOR_SYMBOL,
        "hard_bypass_probe_order": list(HARD_BYPASS_PROBE_ORDER),
        "irq_triggered_publication_sites": sorted(set(sites)),
        "reachable_nvic_enable_sites": len(enable_sites),
    }


def verify_convergence_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the one shared bounded convergence tail."""

    try:
        body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    except GateError:
        raise fail("common convergence helper %s is missing" % CONVERGE_SYMBOL)

    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
    require_resolved_pointers(roles, "convergence helper")
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in the convergence tail: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "convergence loop")
    if not names_identifier(head, "V14_ITERATION_BOUND"):
        raise fail("convergence bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "convergence helper")
    verify_loop_header(head, roles, "convergence loop", store_re, defines)
    require_resolved_dereferences(body, defines, roles, "the convergence helper")
    require_no_macro_mmio(body, *mmio_macro_table(vendor_masked)[:1], "the convergence helper",
                          mmio_macro_table(vendor_masked)[1])

    items = flatten_loop(loop_body, "convergence loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re, defines)
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in the convergence tail")
            if effect == "store":
                raise fail("convergence evidence store occurs inside the loop")
        if depth:
            for effect in effects:
                if effect.startswith("load:"):
                    raise fail("convergence predicate is satisfied by a reread rather than the loop tuple")
            continue
        for effect in effects:
            if effect == "timestamp" or effect.startswith("call:"):
                raise fail(
                    "convergence loop carries a per-iteration store/call/timestamp: %s"
                    % head.strip()[:50]
                )
            if effect.startswith("load:"):
                role = effect.split(":", 1)[1]
                read_order.append(role)
                if branched:
                    loads_after_branch.append(role)
        if kind == "guard":
            guard_bodies.append((head, guard_body))
            branched = True

    # Same proof obligation as the primary loop: a guard only escapes the
    # per-iteration rule if it provably ends the iteration.
    for head, guard_body in guard_bodies:
        verify_guard_publication(head, guard_body, roles, "convergence loop", store_re, defines)
    verify_no_loop_back_edge(loop_body, "convergence loop")

    duplicates = _duplicate_roles(read_order)
    if duplicates:
        raise fail(
            "convergence loop reloads %s: the same-iteration tuple must come from one load per register"
            % ", ".join(duplicates)
        )
    if loads_after_branch and read_order == ["QREAD", "STATUS"]:
        raise fail("convergence predicate is evaluated before both reads")
    if read_order != ["QREAD", "STATUS"]:
        raise fail("convergence read order is not QREAD then STATUS: observed %s" % (read_order or ["nothing"]))

    guards = [
        ("success" if names_identifier(body, "V14_CONVERGENCE_SUCCESS") else _guard_kind(head), head, body)
        for depth, kind, head, body in items
        if depth == 0 and kind == "guard" and _GUARD_HEAD_RE.match(head) and "(" in head
    ]

    kinds = [role for role, _, _ in guards]
    if "success" not in kinds:
        raise fail("convergence loop has no success predicate")
    success_index = kinds.index("success")
    for required in ("reset", "fault"):
        if required not in kinds:
            raise fail("convergence fault/reset check is delayed: %s guard is missing" % required)
        if kinds.index(required) > success_index:
            raise fail("convergence fault/reset check is delayed: %s guard follows the success predicate" % required)

    predicate = guards[success_index][1]
    for identifier in _IDENTIFIER_RE.findall(predicate):
        if identifier in _PREDICATE_IDENTIFIERS or identifier.startswith("V14_") or identifier == "if":
            continue
        raise fail(
            "convergence predicate accumulates across iterations: %s is not part of the same-iteration tuple"
            % identifier
        )
    flattened = re.sub(r"\s+", " ", predicate)
    for term in _PREDICATE_TERMS:
        if term not in flattened:
            raise fail("convergence predicate omits a required term: %s" % term)

    # Naming the four terms is not deciding on them. Written with ``||`` the
    # same four succeed on ``(status & STATE) == 0`` alone -- with the queue
    # undrained, bit5 clear and bit1 clear -- which is the one thing "one
    # same-iteration tuple" was meant to rule out. So the connective is parsed,
    # and each term is bound to the value its comparison lands on.
    predicate_condition = guard_condition(predicate, "convergence loop")
    predicate_terms = verify_predicate_shape(
        predicate_condition,
        "&&",
        CONVERGENCE_PREDICATE,
        defines,
        "the convergence success predicate",
    )

    # Every depth-0 guard of the tail decides an outcome, so each one is held to
    # the predicate its kind is. Without this a second guard that also sets
    # ``V14_CONVERGENCE_SUCCESS`` is classified ``success``, sorts behind the
    # real one, and is never predicate-checked at all -- so it can succeed on
    # anything at all while the manifest publishes the real predicate.
    verify_publishing_guards(
        tuple((head, guard_body) for _kind, head, guard_body in guards),
        {
            "reset": ("the convergence reset predicate", "", _RESET_PREDICATE),
            "fault": ("the convergence fault predicate", "", _FAULT_PREDICATE),
            "success": ("the convergence success predicate", "&&", CONVERGENCE_PREDICATE),
        },
        defines,
        "convergence loop",
        tuple(kind for kind, _head, _guard_body in guards),
    )

    if store_re.search(body[:loop_start]):
        raise fail("convergence evidence store occurs before the loop")

    return {
        "convergence_helper": CONVERGE_SYMBOL,
        "convergence_read_order": ["QREAD", "STATUS"],
        "convergence_bound": ITERATION_BOUND,
        "convergence_predicate_terms": list(_PREDICATE_TERMS),
        "convergence_predicate_connective": logical_structure(predicate_condition)[0],
        "convergence_predicate_bindings": [list(term) for term in predicate_terms],
    }
