"""Successor completion-visibility checker: source cleanup."""

from __future__ import annotations

import re

from .constants import (
    CONVERGE_SYMBOL,
    HPRINTF_SEAM_MARKER,
    HPRINTF_SEAM_MARKER_NAME,
    HPRINTF_WRAP_SYMBOL,
    PRIMARY_SYMBOL,
    SUCCESS_CLEANUP_ORDER,
    _CLEANUP_CMD_TOKENS,
    _TEST_CPM_ENDIF_RE,
    _TEST_CPM_IF_RE,
)

from .errors import (
    fail,
)

from .c_lexical import (
    code_contains,
    code_find,
    code_pattern,
    code_positions,
    function_span,
)

from .c_addresses import (
    cmd_write_values,
    enclosing_block_start,
    file_scope_text,
    mmio_macro_table,
    pointer_roles,
    register_access_sites,
    require_no_macro_mmio,
    require_resolved_dereferences,
    require_resolved_pointers,
    submit_write_sites,
)


def _cmd_value_text(value: int | None) -> str:
    return "opaque" if value is None else "0x%08X" % value


def _hprintf_seam_site(cleanup: str, cleanup_raw: str, cmd0: int, terminal: int) -> int:
    """Return the offset of the one qualified H-PRINTF callsite in the window.

    ``mask_c_lexical`` preserves byte offsets, so the marker can be located in
    the raw text and compared against callsites found in the masked text. The
    marker is what makes this the qualified seam: a bare vendor printf in the
    release window is a debug print, not the ``__wrap_printf`` callsite the
    frozen V12 gate qualified.
    """

    marker_spans = [
        (match.start(), match.end())
        for match in code_pattern(HPRINTF_SEAM_MARKER).finditer(cleanup_raw)
        if cmd0 < match.start() < terminal
    ]
    markers = [start for start, _stop in marker_spans]
    callsites = [site for site in code_positions(cleanup, "printf(") if cmd0 < site < terminal]
    if len(markers) != 1:
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: %d seam markers in the release window"
            % (HPRINTF_SEAM_MARKER_NAME, len(markers))
        )
    if len(callsites) != 1:
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: %d printf callsites in the release window"
            % (HPRINTF_SEAM_MARKER_NAME, len(callsites))
        )
    between = cleanup_raw[marker_spans[0][1] : callsites[0]]
    if markers[0] > callsites[0] or between.strip():
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: the seam marker does not anchor it"
            % HPRINTF_SEAM_MARKER_NAME
        )
    return callsites[0]


def _test_cpm_region(cleanup: str) -> tuple[int, int]:
    """The ``#if(TEST_CPM==1)`` span the terminal cleanup writes live in.

    The seam and the terminal ``CMD=0xC`` are inside a preprocessor branch, and
    this gate reads source rather than a translation unit. What it can prove is
    that the branch is the ``TEST_CPM==1`` one and that ``TEST_CPM`` is defined
    to 1 in the same source; what it cannot prove is that the build actually
    compiled it, which is why the manifest publishes that as a limitation
    rather than implying the writes are unconditionally reachable.
    """

    opens = [match.end() for match in _TEST_CPM_IF_RE.finditer(cleanup)]
    if len(opens) != 1:
        raise fail(
            "cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): %d guards"
            % len(opens)
        )
    close = _TEST_CPM_ENDIF_RE.search(cleanup, opens[0])
    if close is None:
        raise fail("cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): no #endif")
    return opens[0], close.start()


def verify_cleanup_contract(
    vendor_masked: str, vendor_text: str, variant: str, defines: dict[str, int]
) -> dict[str, object]:
    """Prove failure isolation, history provenance and the stock success tail."""

    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    command_raw = vendor_text[command_start:command_stop]

    scope = file_scope_text(vendor_masked)
    command_roles = pointer_roles(command, defines, scope)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, *mmio_macro_table(vendor_masked)[:1], "the command function",
                          mmio_macro_table(vendor_masked)[1])

    primary_call = code_find(command, PRIMARY_SYMBOL[variant] + "(")
    if primary_call < 0:
        raise fail("command path does not call the variant primary helper")
    tail = command[primary_call + len(PRIMARY_SYMBOL[variant]) :]
    if re.search(r"(?<![A-Za-z0-9_])v14_primary_", tail) is not None:
        raise fail("variant-specific block between the primary freeze and the common cleanup")

    command_cmd_writes = tuple(site for site, _value in cmd_write_values(command, defines, command_roles))
    command_prints = code_positions(command, "printf(")
    failure_clears: list[int] = []
    failure_prints: list[int] = []
    for site in code_positions(command, "v14_publish_failure("):
        window_end = code_find(command[site:], "return")
        if window_end < 0:
            raise fail("failure path does not return after publication")
        window_stop = site + window_end
        # The failure path is the branch that decided the failure, not the two
        # statements that report it. A CMD clear written immediately *before*
        # the publication clears the NPU exactly as one written after it does,
        # and a window that opens at the publication call never looks there --
        # so the window opens where the branch does.
        window_start = enclosing_block_start(command, site)
        failure_clears.extend(
            offset for offset in command_cmd_writes if window_start <= offset < window_stop
        )
        failure_prints.extend(
            offset for offset in command_prints if window_start <= offset < window_stop
        )
    if failure_clears:
        raise fail("failure path clears NPU state before serialization")
    if failure_prints:
        raise fail("failure path enters the H-PRINTF seam")

    history = re.search(r"irq_history_mask\s*=\s*([^;]+);", command)
    if history is None or not code_contains(history.group(1), "converged.status"):
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")
    converge_call = code_find(command, CONVERGE_SYMBOL + "(")
    if converge_call < 0:
        raise fail("command path does not call the common convergence helper")
    if any(
        site >= converge_call
        for site in register_access_sites(command, "STATUS", defines, command_roles)
    ):
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")

    # Between the submit write and the point the cleanup ordering starts walking,
    # the only rule that ever applied was "exactly one write sets bit 0". A
    # ``write_reg(NPU_REG_CMD, 0)`` immediately after the submit satisfies it and
    # stops the queue, so every timestamp, iteration count and first-observation
    # word published afterwards describes a run that was not running. The window
    # is closed here rather than by widening the ordering walk, because the walk
    # is a proof about the release tail and this is a proof about the measurement.
    submits = submit_write_sites(command, defines, command_roles)
    if len(submits) != 1:
        raise fail(
            "command path does not carry exactly one NPU submit write: %d submit writes"
            % len(submits)
        )
    intruding = tuple(
        site for site in command_cmd_writes if submits[0] < site < history.start()
    )
    if intruding:
        raise fail(
            "a CMD write falls between the submit write and the convergence tail: %d writes, "
            "first at offset %d -- the queue every measured word reports on is transitioned "
            "while it is being measured" % (len(intruding), intruding[0])
        )

    cleanup = command[history.start() :]
    cleanup_raw = command_raw[history.start() :]
    cleanup_roles = pointer_roles(cleanup, defines, scope)
    # The cleanup tail is judged by what each CMD write *does*, so a second
    # ISR-equivalent written as ``2`` rather than ``0x00000002`` is the same
    # marker and lands in the same ordering.
    cleanup_cmd_writes = cmd_write_values(cleanup, defines, cleanup_roles)
    markers: list[tuple[int, str]] = []
    for site, value in cleanup_cmd_writes:
        markers.append((site, _CLEANUP_CMD_TOKENS.get(value, "CMD=%s" % _cmd_value_text(value))))
    for site in register_access_sites(cleanup, "QREAD", defines, cleanup_roles):
        markers.append((site, "QREAD"))
    for site in code_positions(cleanup, "read_val == u32CmdQueueSize"):
        markers.append((site, "QREAD_VERIFY"))
    for site in code_positions(cleanup, "NVIC_ClearPendingIRQ("):
        markers.append((site, "NVIC"))
    cmd0 = tuple(site for site, value in cleanup_cmd_writes if value == 0x0)
    terminal = tuple(site for site, value in cleanup_cmd_writes if value == 0xC)
    seam_site = -1
    if cmd0 and terminal:
        seam_site = _hprintf_seam_site(cleanup, cleanup_raw, cmd0[0], terminal[0])
        markers.append((seam_site, "H-PRINTF"))
    observed = tuple(token for _, token in sorted(markers))
    if observed != SUCCESS_CLEANUP_ORDER:
        raise fail("success cleanup ordering drifted: observed %s" % (list(observed),))

    region_start, region_stop = _test_cpm_region(cleanup_raw)
    if not region_start < seam_site < terminal[0] < region_stop:
        raise fail(
            "cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): the seam and the "
            "terminal CMD=0xC are not both inside it"
        )
    if defines.get("TEST_CPM") != 1:
        raise fail(
            "cleanup terminal sequence is compiled out: TEST_CPM is %s, not 1"
            % ("undefined" if "TEST_CPM" not in defines else defines["TEST_CPM"])
        )

    return {
        "success_cleanup_order": list(observed),
        "failure_paths_clear_npu": bool(failure_clears),
        "failure_paths_enter_hprintf": bool(failure_prints),
        "hprintf_seam_marker": HPRINTF_SEAM_MARKER_NAME,
        "hprintf_seam_wrap_symbol": HPRINTF_WRAP_SYMBOL,
        "hprintf_callsite_elf_qualified": False,
        "cleanup_terminal_conditional_on": "TEST_CPM==1",
        "cleanup_terminal_branch_compiled_proof": False,
    }
