"""Source and fixture contract gate for PMU_COMPLETION_VISIBILITY_DIAG_V14.

Scope, stated first so nothing here is read for more than it is: this module
gates **generated C sources** for the Q/QS/SQ schema-14 diagnostic images. It
proves the identity constants, the pre-run stopped-state/QSIZE contract, the
per-variant primary observation loops, the one common convergence tail, the
34-word failure mailbox, and the retained V12/V13 IRQ hard-bypass and success
cleanup ordering -- all over comment- and literal-masked source text.

What it does **not** do: it does not read an ELF, a disassembly, DWARF, or a
map file, so it cannot prove what the compiler actually lowered. Source
inspection is supporting evidence only; the final-ELF qualification gates named
in the design are a separate, later contract and are not implemented here. A
build that satisfies this module is UNIT-QUALIFIED and nothing more.

The analyzer is structural rather than textual. Function bodies are resolved by
brace matching, loop bodies are split into statements, and each statement is
classified into a semantic effect (an MMIO load of a bound register pointer, a
timestamp read, a store, a call, a control branch). Gates are then expressed
over the ordered effect sequence and over the branch topology, so reformatting
the generated source cannot change a verdict while inserting a per-iteration
effect can.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA_VERSION = 14
BUILD_ID = 0x34314950
VARIANT_FAMILY = "PMU_COMPLETION_VISIBILITY_DIAG_V14"

HEADER_WORDS = 8
BASE_WORDS = 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS
PAYLOAD_BYTES = TOTAL_WORDS * 4

QSIZE_EXPECTED = 0x110
MAILBOX_VALID = 0x5631344D
U32_INVALID = 0xFFFFFFFF
ITERATION_BOUND = 10000

VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"

APPENDIX_FIELDS = (
    "variant_id",
    "qsize_expected",
    "pre_program_status",
    "pre_submit_status",
    "t_submit_after_cmd",
    "t_primary_entry",
    "t_first_observation",
    "primary_result",
    "primary_iterations",
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
    "convergence_result",
    "convergence_iterations",
    "convergence_final_qread",
    "convergence_final_status",
    "convergence_timeout",
    "failure_phase",
    "failure_reason",
    "failure_qread",
    "failure_status",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
    "mailbox_valid",
)

PRIMARY_RESULT = {"NOT_RUN": 0, "OBSERVED": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
CONVERGENCE_RESULT = {"NOT_RUN": 0, "SUCCESS": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
FAILURE_PHASE = {
    "NONE": 0,
    "PRE_PROGRAM": 1,
    "PRE_SUBMIT": 2,
    "PRIMARY": 3,
    "CONVERGENCE": 4,
    "CLEANUP": 5,
}
FAILURE_REASON = {
    "NONE": 0,
    "STATE_RUNNING": 1,
    "RESET_IN_PROGRESS": 2,
    "HARDWARE_FAULT": 3,
    "STALE_IRQ": 4,
    "STALE_CMD_END": 5,
    "QSIZE_MISMATCH": 6,
    "PRIMARY_TIMEOUT": 7,
    "CONVERGENCE_TIMEOUT": 8,
    "CLEANUP_INVARIANT": 9,
}
VENDOR_RETURN = {
    "SUCCESS": 0,
    "PRE_PROGRAM_FAILURE": 1,
    "PRE_SUBMIT_FAILURE": 2,
    "PRIMARY_TIMEOUT": 3,
    "RESET_IN_PROGRESS": 4,
    "HARDWARE_FAULT": 5,
    "CONVERGENCE_TIMEOUT": 6,
    "CLEANUP_INVARIANT": 7,
}

STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_BUS = 0x004
STATUS_RESET = 0x008
STATUS_CMD_PARSE = 0x010
STATUS_CMD_END = 0x020
STATUS_ECC = 0x100
STATUS_BRANCH = 0x200
STATUS_FAULT_MASK = STATUS_BUS | STATUS_CMD_PARSE | STATUS_ECC | STATUS_BRANCH

MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"
MAILBOX_RESET_SYMBOL = "v14_mailbox_reset"
MAILBOX_PUBLISH_SYMBOL = "v14_mailbox_publish"
CONVERGE_SYMBOL = "v14_converge"
PRIMARY_SYMBOL = {"Q": "v14_primary_q", "QS": "v14_primary_qs", "SQ": "v14_primary_sq"}


class GateError(Exception):
    """A stable, named contract rejection."""


def fail(message: str) -> GateError:
    return GateError(message)


def identity_matches(
    *,
    schema_version: int,
    build_id: int,
    appendix_words: int,
    qsize_expected: int,
    mailbox_valid: int,
) -> bool:
    """Report whether a candidate identity tuple is the frozen V14 one."""

    return (
        schema_version == SCHEMA_VERSION
        and build_id == BUILD_ID
        and appendix_words == APPENDIX_WORDS
        and qsize_expected == QSIZE_EXPECTED
        and mailbox_valid == MAILBOX_VALID
    )


# ---------------------------------------------------------------------------
# Lexical masking and structural extraction
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//(?:\\[ \t]*\n|[^\n])*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL_RE = re.compile(r'"(?:\\[\s\S]|[^"\\\n])*"')
_CHAR_LITERAL_RE = re.compile(r"'(?:\\[\s\S]|[^'\\\n])+'")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _blank_span(out: list[str], text: str, start: int, stop: int) -> None:
    for index in range(start, stop):
        out[index] = "\n" if text[index] == "\n" else " "


def mask_c_lexical(text: str) -> str:
    """Blank comments and literals while preserving every byte offset."""

    out = list(text)
    for pattern in (_BLOCK_COMMENT_RE, _LINE_COMMENT_RE, _STRING_LITERAL_RE, _CHAR_LITERAL_RE):
        for match in pattern.finditer("".join(out)):
            _blank_span(out, text, match.start(), match.end())
    return "".join(out)


def _matching_brace(text: str, open_index: int, what: str) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise fail("%s: unbalanced braces" % what)


def extract_function_body(masked: str, name: str, what: str) -> tuple[int, int]:
    """Return the ``(start, stop)`` span of ``name``'s body, braces excluded."""

    definitions = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])%s\s*\(" % re.escape(name), masked):
        close = masked.find(")", match.end() - 1)
        if close < 0:
            continue
        tail = masked[close + 1 :]
        stripped = tail.lstrip()
        if not stripped.startswith("{"):
            continue
        open_index = close + 1 + (len(tail) - len(stripped))
        definitions.append((open_index, _matching_brace(masked, open_index, what)))
    if len(definitions) != 1:
        raise fail("%s: expected exactly one definition, found %d" % (what, len(definitions)))
    open_index, close_index = definitions[0]
    return open_index + 1, close_index


def function_text(masked: str, name: str, what: str) -> str:
    start, stop = extract_function_body(masked, name, what)
    return masked[start:stop]


def normalized_digest(text: str) -> str:
    """Digest of ``text`` after collapsing all whitespace runs to one space."""

    return _sha256_text(re.sub(r"\s+", " ", text).strip())


_DEFINE_RE = re.compile(r"(?m)^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]+(\S+)[ \t]*$")


def parse_defines(masked: str) -> dict[str, int]:
    """Return the integer-valued object-like macros of a translation unit."""

    values: dict[str, int] = {}
    for match in _DEFINE_RE.finditer(masked):
        raw = match.group(2).rstrip("uU")
        try:
            values[match.group(1)] = int(raw, 0)
        except ValueError:
            continue
    return values


def require_define(defines: dict[str, int], name: str, expected: int, what: str) -> None:
    if name not in defines:
        raise fail("%s: %s is not defined" % (what, name))
    if defines[name] != expected:
        raise fail("%s: %s is 0x%X, expected 0x%X" % (what, name, defines[name], expected))


def positions(text: str, needle: str) -> tuple[int, ...]:
    found = []
    start = text.find(needle)
    while start >= 0:
        found.append(start)
        start = text.find(needle, start + 1)
    return tuple(found)


def function_span(masked: str, name: str, what: str) -> tuple[int, int]:
    return extract_function_body(masked, name, what)


_QSIZE_READ = "read_reg(NPU_REG_QSIZE)"
_STATUS_READ = "read_reg(NPU_REG_STATUS)"
_QBASE_WRITE = "write_reg(NPU_REG_QBASE"
_QSIZE_WRITE = "write_reg(NPU_REG_QSIZE"
_CMD_WRITE = "write_reg(NPU_REG_CMD"
_SUBMIT_WRITE = "write_reg(NPU_REG_CMD, read_val | 0x00000001)"

_PRE_SUBMIT_GATES = (
    ("V14_STATUS_STATE", "stopped"),
    ("V14_STATUS_IRQ_RAISED", "stale irq_raised"),
    ("V14_STATUS_RESET", "reset_status"),
    ("V14_STATUS_CMD_END", "stale cmd_end_reached"),
    ("V14_STATUS_FAULT_MASK", "vendor fault"),
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
        if subject in condition:
            found.append((condition, block[open_index + 1 : close_index]))
    return tuple(found)


def verify_pre_run_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the stopped-state gate, the single QSIZE snapshot and fail-closed submit."""

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

    setup_start, setup_stop = function_span(vendor_masked, "test_u85", "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]

    pre_program_reads = positions(setup, _STATUS_READ)
    queue_accesses = positions(setup, _QBASE_WRITE) + positions(setup, _QSIZE_WRITE)
    if not queue_accesses:
        raise fail("pre-program STATUS gate does not dominate QBASE/QSIZE: no queue programming found")
    if len(pre_program_reads) != 1 or pre_program_reads[0] > min(queue_accesses):
        raise fail(
            "pre-program STATUS gate does not dominate QBASE/QSIZE: %d gate loads, first queue access at %d"
            % (len(pre_program_reads), min(queue_accesses))
        )

    for mask, label in (
        ("V14_STATUS_STATE", "stopped"),
        ("V14_STATUS_RESET", "reset_status"),
        ("V14_STATUS_FAULT_MASK", "vendor fault"),
    ):
        guards = [c for c, _ in _guard_blocks(setup, "pre_program_status") if mask in c]
        if len(guards) != 1:
            raise fail("pre-program gate omits stopped/reset/fault: %s check is missing" % label)

    if positions(setup, _CMD_WRITE):
        raise fail(
            "state-transitioning CMD write between the pre-program gate and queue programming"
        )

    final_qsize_write = max(positions(setup, _QSIZE_WRITE))
    for site in positions(setup, _QSIZE_READ):
        if site < final_qsize_write:
            raise fail("qsize snapshot precedes the final QSIZE programming write")

    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]

    qsize_loads = positions(command, _QSIZE_READ)
    if len(qsize_loads) == 0:
        raise fail("qsize_expected snapshot is missing between final programming and submit")
    if len(qsize_loads) != 1:
        raise fail("QSIZE is loaded more than once: %d loads in the command path" % len(qsize_loads))

    submits = positions(command, _SUBMIT_WRITE)
    if len(submits) != 1:
        raise fail("command path does not carry exactly one NPU submit write")
    if qsize_loads[0] > submits[0]:
        raise fail("running QSIZE reachable: the QSIZE load follows the submit write")

    status_loads = positions(command, _STATUS_READ)
    if len(status_loads) != 1:
        raise fail(
            "post-program STATUS load is not distinct from the pre-program load: %d loads"
            % len(status_loads)
        )
    if status_loads[0] > submits[0]:
        raise fail("post-program STATUS gate follows the submit write")

    qsize_compare = _guard_blocks(command, "qsize_expected")
    if not any("V14_QSIZE_EXPECTED" in condition for condition, _ in qsize_compare):
        raise fail("qsize_expected is not manifest 0x110: no compare against V14_QSIZE_EXPECTED")

    pre_submit_guards = _guard_blocks(command, "pre_submit_status")
    for mask, label in _PRE_SUBMIT_GATES:
        if not any(mask in condition for condition, _ in pre_submit_guards):
            raise fail("post-program stale/reset/fault gate is incomplete: %s check is missing" % label)

    for condition, body in tuple(qsize_compare) + pre_submit_guards:
        if "return" not in body:
            raise fail("pre-run failure reaches submit: guard (%s) does not return" % condition.strip()[:40])

    return {
        "pre_program_status_loads": len(pre_program_reads),
        "post_program_status_loads": len(status_loads),
        "qsize_loads": len(qsize_loads),
        "qsize_expected": "0x%08X" % QSIZE_EXPECTED,
        "running_qsize_loads": 0,
    }


# ---------------------------------------------------------------------------
# Statement-level effect model
# ---------------------------------------------------------------------------

_POINTER_BINDING_RE = re.compile(r"\*\s*const\s+([A-Za-z_]\w*)\s*=[^;]*?(NPU_REG_[A-Z_]+)")
_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*\(")
_NON_CALL_KEYWORDS = frozenset(
    ("if", "for", "while", "switch", "return", "sizeof", "uint32_t", "int32_t", "volatile", "uintptr_t")
)
_STORE_RE = re.compile(r"(?:obs\s*->|%s\s*\[)" % re.escape(MAILBOX_SYMBOL))


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


def pointer_roles(body: str) -> dict[str, str]:
    roles: dict[str, str] = {}
    for name, register in _POINTER_BINDING_RE.findall(body):
        roles[name] = register.replace("NPU_REG_", "")
    return roles


def statement_effects(statement: str, roles: dict[str, str]) -> tuple[str, ...]:
    effects: list[str] = []
    for name, role in roles.items():
        if re.search(r"\*\s*%s(?![A-Za-z0-9_])" % re.escape(name), statement):
            effects.append("load:%s" % role)
    if "NPU_REG_QSIZE" in statement:
        effects.append("qsize")
    if "DWT->CYCCNT" in statement:
        effects.append("timestamp")
    if _STORE_RE.search(statement):
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


def _all_loads(block: str, roles: dict[str, str]) -> list[str]:
    """Every MMIO load in ``block``, in source order, regardless of nesting."""

    found: list[tuple[int, str]] = []
    for name, role in roles.items():
        for match in re.finditer(r"\*\s*%s(?![A-Za-z0-9_])" % re.escape(name), block):
            found.append((match.start(), role))
    return [role for _, role in sorted(found)]


def _guard_kind(condition: str) -> str:
    if "V14_STATUS_RESET" in condition:
        return "reset"
    if "V14_STATUS_FAULT_MASK" in condition:
        return "fault"
    if "qsize_expected" in condition:
        return "completion"
    return "other"


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
    roles = pointer_roles(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in a primary loop: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "primary loop")
    if "V14_ITERATION_BOUND" not in head:
        raise fail("primary loop bound is not 10000: loop head does not use V14_ITERATION_BOUND")

    items = split_block(loop_body)
    read_order: list[str] = []
    expected = ["QREAD"] if variant == "Q" else EXPECTED_PRIMARY_ORDER[variant]
    for kind, headline, nested in items:
        if kind == "block":
            break
        effects = statement_effects(headline, roles)
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in a primary loop")
        if any(effect in ("timestamp", "store") or effect.startswith("call:") for effect in effects):
            raise fail(
                "primary loop carries a per-iteration store/call/timestamp: %s" % headline.strip()[:50]
            )
        for effect in effects:
            if effect.startswith("load:"):
                read_order.append(effect.split(":", 1)[1])
    if read_order != expected:
        if variant == "Q" and "STATUS" in read_order:
            raise fail("Q primary loop reads STATUS")
        # A read that exists in the loop but only downstream of a branch is a
        # short-circuit exit, not a missing read: the two cases need different
        # names because they need different fixes.
        if read_order == expected[: len(read_order)] and _all_loads(loop_body, roles)[: len(expected)] == expected:
            raise fail("primary predicate is evaluated before both reads")
        raise fail(
            "%s primary read order is not %s: observed %s"
            % (variant, " then ".join(expected), read_order or ["nothing"])
        )

    guards: list[tuple[str, str]] = []
    for kind, headline, nested in items:
        if kind != "block":
            continue
        if not headline.startswith("if"):
            continue
        effects = statement_effects(nested, roles)
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in a primary loop")
            if effect.startswith("load:"):
                raise fail("primary success tuple is re-read rather than frozen")
        guards.append((_guard_kind(headline), headline))

    kinds = [kind for kind, _ in guards]
    if "completion" not in kinds:
        raise fail("primary loop has no completion predicate")
    if variant == "Q":
        if "STATUS" in "".join(condition for _, condition in guards):
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
        if "V14_STATUS_CMD_END" not in completion:
            raise fail("primary completion predicate does not use cmd_end_reached bit5")
        if "V14_STATUS_IRQ_RAISED" in completion:
            raise fail("irq_raised bit1 is used as a primary exit predicate")

    # Everything before the loop and everything after it is outside authoritative
    # timing; only Q may touch STATUS there, and only once.
    outside = body[:loop_start] + body[loop_stop:]
    diagnostic_loads = len(
        re.findall(
            r"\*\s*(?:%s)(?![A-Za-z0-9_])"
            % "|".join(re.escape(name) for name, role in roles.items() if role == "STATUS"),
            outside,
        )
    )
    if variant == "Q":
        if diagnostic_loads != 1:
            raise fail(
                "Q timeout diagnostic STATUS read is missing or duplicated: %d loads" % diagnostic_loads
            )
    elif diagnostic_loads != 0:
        raise fail("%s primary helper reads STATUS outside its loop: %d loads" % (variant, diagnostic_loads))

    after_loop = body[loop_stop:]
    if "DWT->CYCCNT" in after_loop:
        raise fail("%s timeout path publishes a first-observation timestamp" % variant)
    if CONVERGE_SYMBOL in body:
        raise fail("%s timeout path reaches the convergence tail" % variant)

    fault_bits = [bit for bit in (1 << shift for shift in range(32)) if defines["V14_STATUS_FAULT_MASK"] & bit]
    return {
        "primary_helper": wanted,
        "primary_read_order": expected,
        "primary_bound": ITERATION_BOUND,
        "valid_iteration_range": [1, ITERATION_BOUND],
        "fault_bits_gated": fault_bits,
        "reset_bit_gated": defines["V14_STATUS_RESET"],
        "q_timeout_diagnostic_status_loads": diagnostic_loads,
        "first_observation_categories": [] if variant == "Q" else ["Q_FIRST", "S5_FIRST", "SAME_ITERATION"],
    }


EXPECTED_PRIMARY_ORDER = {"Q": ["QREAD"], "QS": ["QREAD", "STATUS"], "SQ": ["STATUS", "QREAD"]}

STOCK_VECTOR_SYMBOL = "u85_irq_handler"
HARD_BYPASS_PROBE_ORDER = (
    "NVIC_DisableIRQ",
    "NVIC_ClearPendingIRQ",
    "NVIC_GetVector",
    "NVIC_GetEnableIRQ",
    "NVIC_GetPendingIRQ",
    "NVIC_GetActive",
)


def verify_hard_bypass_contract(vendor_masked: str) -> dict[str, object]:
    """Prove the retained V12/V13 stock vector and NVIC hard bypass."""

    install = "NVIC_SetVector(NPU0_IRQn, (uint32_t)&%s)" % STOCK_VECTOR_SYMBOL
    if len(positions(vendor_masked, install)) != 1:
        raise fail("runtime vector is not the exact stock u85_irq_handler")

    setup_start, setup_stop = function_span(vendor_masked, "test_u85", "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]
    observed = []
    for probe in HARD_BYPASS_PROBE_ORDER:
        site = setup.find(probe + "(")
        if site >= 0:
            observed.append((site, probe))
    ordering = [probe for _, probe in sorted(observed)]
    if ordering != list(HARD_BYPASS_PROBE_ORDER):
        raise fail("NVIC hard-bypass probe ordering drifted: observed %s" % ordering)

    if positions(vendor_masked, "NVIC_EnableIRQ("):
        raise fail("reachable NVIC_EnableIRQ")
    if re.search(r"NVIC\s*->\s*ISER", vendor_masked):
        raise fail("direct NVIC ISER enable write is reachable")

    spans = function_spans(vendor_masked)
    sites = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])irq_triggered\s*=\s*true", vendor_masked):
        sites.append(enclosing_function(spans, match.start()))
    if sorted(set(sites)) != [STOCK_VECTOR_SYMBOL]:
        raise fail("irq_triggered can become true on a measured path: sites %s" % sorted(set(sites)))
    if not re.search(r"(?<![A-Za-z0-9_])irq_triggered\s*=\s*false", setup):
        raise fail("NVIC hard-bypass probe ordering drifted: irq_triggered is not cleared before the probes")

    return {
        "installed_vector_symbol": STOCK_VECTOR_SYMBOL,
        "hard_bypass_probe_order": list(HARD_BYPASS_PROBE_ORDER),
        "irq_triggered_publication_sites": sorted(set(sites)),
        "reachable_nvic_enable_sites": 0,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_pmu_completion_visibility_v14.py",
        description="Source and fixture contract gate for %s." % VARIANT_FAMILY,
    )
    parser.add_argument(
        "--allow-fixture",
        action="store_true",
        help="acknowledge that the inputs are generated/fixture sources, not board evidence",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANTS),
        help="variant under test: Q, QS or SQ",
    )
    parser.add_argument("--runner-generated", help="path to the generated runner translation unit")
    parser.add_argument("--vendor-generated", help="path to the generated vendor translation unit")
    parser.add_argument("--fixture-manifest-out", help="path the fixture manifest is written to")
    return parser


def _read_text(path: str, what: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _normalize_newlines(handle.read())
    except OSError as exc:
        raise fail("%s: unreadable (%s)" % (what, exc))


def _write_manifest(path: str, doc: dict[str, object]) -> None:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.allow_fixture:
        print("FAIL fixture mode requires --allow-fixture; synthetic evidence is refused by default")
        return 2
    missing = [
        name
        for name, value in (
            ("--variant", args.variant),
            ("--runner-generated", args.runner_generated),
            ("--vendor-generated", args.vendor_generated),
            ("--fixture-manifest-out", args.fixture_manifest_out),
        )
        if value in (None, "")
    ]
    if missing:
        print("FAIL fixture mode requires %s" % ", ".join(missing))
        return 2

    try:
        runner_text = _read_text(args.runner_generated, "generated runner")
        vendor_text = _read_text(args.vendor_generated, "generated vendor")
        doc = verify_generated_sources(runner_text, vendor_text, args.variant)
    except GateError as exc:
        print("FAIL %s" % exc)
        return 1

    _write_manifest(args.fixture_manifest_out, doc)
    print("FIXTURE PASS %s variant=%s" % (VARIANT_FAMILY, args.variant))
    return 0


def verify_generated_sources(runner_text: str, vendor_text: str, variant: str) -> dict[str, object]:
    """Verify a generated Q/QS/SQ source pair and return its fixture manifest."""

    if variant not in VARIANTS:
        raise fail("unknown variant %r" % variant)
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    vendor_masked = mask_c_lexical(vendor_text)
    defines = parse_defines(vendor_masked)

    pre_run = verify_pre_run_contract(vendor_masked, defines)
    primary = verify_primary_contract(vendor_masked, variant, defines)
    hard_bypass = verify_hard_bypass_contract(vendor_masked)
    converge_body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    tail_start = command.find("v14_publish_primary(")
    if tail_start < 0:
        raise fail("common tail does not start at the shared primary publication")

    doc: dict[str, object] = {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "qualification": "UNIT-QUALIFIED",
        "proof_scope": "generated_source_and_fixture_only",
        "real_elf_qualified": False,
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
        "common_convergence_source_sha256": normalized_digest(converge_body),
        "common_tail_source_sha256": normalized_digest(command[tail_start:]),
    }
    doc.update(pre_run)
    doc.update(primary)
    doc.update(hard_bypass)
    return doc


if __name__ == "__main__":
    sys.exit(main())
