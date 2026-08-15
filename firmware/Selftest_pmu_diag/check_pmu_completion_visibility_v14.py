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
brace matching, loop bodies are flattened into every reachable statement at
every nesting depth, and each statement is classified into a semantic effect (an
MMIO load of a bound register pointer, a timestamp read, a store, a call, a
control branch). Gates are then expressed over the ordered effect sequence and
over the branch topology, so reformatting the generated source cannot change a
verdict while inserting a per-iteration effect anywhere in the loop can. A guard
inside a loop is not assumed to run on the exiting iteration -- no condition
proves that -- so it earns its exemption only by carrying nothing beyond the
canonical result publication and its timestamp and by ending its iteration in a
structurally proven ``break`` or ``return``.

Two limitations are load-bearing and are published in every manifest rather
than left to be discovered. The frozen raw vendor translation unit is not
tracked in this repository, so the vendor half of this contract runs against a
stock fixture and is **not** proven against the frozen ``u85.c``. And the
cleanup H-PRINTF seam is proven here only as the frozen ``V12_HPRINTF_SEAM``
source anchor; the ``__wrap_printf`` callsite it maps to is an ELF contract that
belongs to the later qualification chunk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

# The frozen V12/V13 qualified H-PRINTF seam. ``V12_HPRINTF_SEAM`` is the marker
# name ``check_pmu_completion_poll_v12.MANIFEST_MARKER_KEYS`` maps to
# ``hprintf_callsite_address``, which that gate proves is the address of the one
# ``__wrap_printf`` call between CMD=0 and the terminal CMD=0xC. Anchoring the
# generated source on that marker is what makes the seam the qualified callsite
# rather than whichever vendor printf happens to sit in the release window.
HPRINTF_SEAM_MARKER_NAME = "V12_HPRINTF_SEAM"
HPRINTF_SEAM_MARKER = "/* %s */" % HPRINTF_SEAM_MARKER_NAME
HPRINTF_WRAP_SYMBOL = "__wrap_printf"

# Stated in every manifest so no reader has to infer what this chunk did not do.
RESIDUAL_LIMITATIONS = (
    "vendor_raw_source_absent: the frozen u85.c is not tracked here, so the vendor "
    "half runs against a stock fixture and is not proven against the frozen "
    "translation unit",
    "hprintf_callsite_not_elf_bound: the cleanup seam is proven as the frozen "
    "V12_HPRINTF_SEAM source anchor only; binding it to the qualified "
    "__wrap_printf callsite address is an ELF contract",
    "no_elf_disassembly_or_dwarf_evidence: every verdict here is source-structural",
    "test_cpm_branch_not_preprocessed: the H-PRINTF seam and the terminal CMD=0xC are proven "
    "inside the #if(TEST_CPM==1) branch of a source that defines TEST_CPM to 1; this gate does "
    "not preprocess or compile, so whether the built image kept that branch is a "
    "build-configuration fact belonging to the later qualification chunk",
)

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
    """Blank comments and literals while preserving every byte offset.

    The scan is the single left-to-right pass the frozen V13 gate already uses,
    because the construct that opens first is the construct that wins. Masking
    each kind with its own sweep does not hold that rule: a ``/*`` written
    *inside* a string literal opens a block comment for the sweep that runs
    first, and everything up to the next ``*/`` -- real executable code
    included -- is blanked before the string sweep ever gets to see that the
    ``/*`` was only text. One pass cannot be talked into that, because reaching
    the ``/`` means the enclosing string was already recognised and skipped.

    Each construct is recognised by a pattern that must close: an unterminated
    block comment or literal simply does not match, and its opening character
    is then left as ordinary code. That is the fail-closed direction -- the
    scan may look at something that is really comment text, but it can never be
    talked out of looking at real code by an unbalanced quote.
    """

    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "/" and index + 1 < length and text[index + 1] in "/*":
            pattern = _LINE_COMMENT_RE if text[index + 1] == "/" else _BLOCK_COMMENT_RE
        elif character == '"':
            pattern = _STRING_LITERAL_RE
        elif character == "'":
            pattern = _CHAR_LITERAL_RE
        else:
            index += 1
            continue
        match = pattern.match(text, index)
        if match is None:
            index += 1
            continue
        _blank_span(out, text, index, match.end())
        index = match.end()
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


def parse_define_values(masked: str) -> dict[str, list[int]]:
    """Return every integer value each object-like macro is given, in order.

    A macro this contract owns -- anything in the ``V14_`` namespace -- has to
    parse. Dropping a malformed one and reporting the macro as *undefined*
    names the wrong defect, and a reader chasing "is not defined" against a
    source that plainly defines it learns nothing. Macros outside the namespace
    are the vendor's and are skipped when they are not integers.
    """

    values: dict[str, list[int]] = {}
    for match in _DEFINE_RE.finditer(masked):
        name = match.group(1)
        raw = match.group(2).rstrip("uU")
        try:
            parsed = int(raw, 0)
        except ValueError:
            if name.startswith("V14_"):
                raise fail(
                    "malformed numeric define: %s is %r, which is not an integer literal"
                    % (name, match.group(2))
                )
            continue
        values.setdefault(name, []).append(parsed)
    return values


def parse_defines(masked: str) -> dict[str, int]:
    """Return the integer-valued object-like macros of a translation unit."""

    return {name: seen[-1] for name, seen in parse_define_values(masked).items()}


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

    # The gate is anchored on whichever function actually programs the queue,
    # rather than on a function name, so the proof holds wherever the vendor
    # keeps its programming.
    spans = function_spans(vendor_masked)
    programming_sites = positions(vendor_masked, _QBASE_WRITE) + positions(vendor_masked, _QSIZE_WRITE)
    if not programming_sites:
        raise fail("pre-program STATUS gate does not dominate QBASE/QSIZE: no queue programming found")
    owners = {enclosing_function(spans, site) for site in programming_sites}
    if len(owners) != 1:
        raise fail("queue programming is split across %d functions: %s" % (len(owners), sorted(owners)))
    setup_start, setup_stop = function_span(vendor_masked, sorted(owners)[0], "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]

    pre_program_reads = positions(setup, _STATUS_READ)
    queue_accesses = positions(setup, _QBASE_WRITE) + positions(setup, _QSIZE_WRITE)
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

    # The design forbids a running transition *between* the gate and the
    # programming writes, not a CMD write anywhere in the setup function, so
    # the window is exactly that span.
    gate_to_programming = setup[pre_program_reads[0] : min(queue_accesses)]
    if _CMD_WRITE in gate_to_programming:
        raise fail(
            "state-transitioning CMD write between the pre-program gate and queue programming"
        )

    qsize_writes = positions(setup, _QSIZE_WRITE)
    if not qsize_writes:
        raise fail(
            "queue programming does not write QSIZE: the setup function programs QBASE only"
        )
    final_qsize_write = max(qsize_writes)
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

    # Only the window up to submit belongs to the pre-run gate; STATUS reads
    # after submit are the tail's business and are judged by the cleanup gate.
    status_loads = tuple(site for site in positions(command, _STATUS_READ) if site < submits[0])
    if len(status_loads) != 1:
        raise fail(
            "post-program STATUS load is not distinct from the pre-program load: %d loads"
            % len(status_loads)
        )

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
_STORE_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_])obs\s*->|(?<![A-Za-z0-9_])%s\s*\[)" % re.escape(MAILBOX_SYMBOL)
)

# A register touched through its raw address expression is the same observable
# as one touched through a bound pointer; only the spelling differs. Naming the
# register is what makes it an access, so ``NPU_REG_STATUS`` written inline
# counts exactly as ``*status_reg`` does.
_RAW_REGISTER_RE = re.compile(r"NPU_REG_([A-Z][A-Z0-9_]*)")

# An alias is a second name for the same storage. ``obs_alias->result`` writes
# the observation record and ``mb[33]`` writes the mailbox, so a rule that only
# recognises the declared spelling is a rule an alias walks around.
_OBS_ALIAS_RE = re.compile(r"([A-Za-z_]\w*)\s*=\s*obs\s*;")
_MAILBOX_ALIAS_RE = re.compile(
    r"([A-Za-z_]\w*)\s*=\s*%s(?![A-Za-z0-9_\[])" % re.escape(MAILBOX_SYMBOL)
)


def obs_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the observation record pointer."""

    return tuple(sorted({name for name in _OBS_ALIAS_RE.findall(text) if name != "obs"}))


def mailbox_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the failure mailbox array."""

    return tuple(
        sorted({name for name in _MAILBOX_ALIAS_RE.findall(text) if name != MAILBOX_SYMBOL})
    )


def _alternation(names: tuple[str, ...]) -> str:
    return "|".join(re.escape(name) for name in names)


def store_pattern(text: str) -> re.Pattern[str]:
    """A store recogniser that also sees ``text``'s obs and mailbox aliases."""

    arrows = ("obs",) + obs_aliases(text)
    arrays = (MAILBOX_SYMBOL,) + mailbox_aliases(text)
    return re.compile(
        r"(?:(?<![A-Za-z0-9_])(?:%s)\s*->|(?<![A-Za-z0-9_])(?:%s)\s*\[)"
        % (_alternation(arrows), _alternation(arrays))
    )


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


def statement_effects(
    statement: str, roles: dict[str, str], store_re: re.Pattern[str] = _STORE_RE
) -> tuple[str, ...]:
    effects: list[str] = []
    for name, role in roles.items():
        if re.search(r"\*\s*%s(?![A-Za-z0-9_])" % re.escape(name), statement):
            effects.append("load:%s" % role)
    if "NPU_REG_QSIZE" in statement:
        effects.append("qsize")
    already_loaded = {effect.split(":", 1)[1] for effect in effects if effect.startswith("load:")}
    for register in _RAW_REGISTER_RE.findall(statement):
        if register != "QSIZE" and register not in already_loaded:
            effects.append("load:%s" % register)
    if "DWT->CYCCNT" in statement:
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


_GUARD_HEAD_RE = re.compile(r"^(?:else\s+if\b|if\b|else\b)")

# The loop head runs on every iteration exactly as the body does. An MMIO load
# in the increment, a mailbox store in the initialiser or a call in the
# condition is a per-iteration effect that happens to be written outside the
# braces, so the head is held to the same rule the body is: the only thing it
# may compute is the register-local induction arithmetic.
_INDUCTION_ALLOWED = frozenset(
    ("uint32_t", "int32_t", "uintptr_t", "unsigned", "int", "V14_ITERATION_BOUND")
)
_INDUCTION_DECL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:uint32_t|int32_t|unsigned|int)\s+([A-Za-z_]\w*)"
)

# A second loop is a second polling site, whatever keyword opens it, and a
# ``goto`` or a label is a back-edge the brace structure does not show. The
# bounded ``for`` this contract proves is only a bound if it is the only way
# round.
_EXTRA_LOOP_RE = re.compile(r"(?<![A-Za-z0-9_])(while|do)(?![A-Za-z0-9_])")
_GOTO_RE = re.compile(r"(?<![A-Za-z0-9_])goto(?![A-Za-z0-9_])")
_CONTINUE_RE = re.compile(r"(?<![A-Za-z0-9_])continue(?![A-Za-z0-9_])")
_LABEL_RE = re.compile(r"^([A-Za-z_]\w*)\s*:(?!:)")
_LABEL_KEYWORDS = frozenset(("case", "default"))


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


def verify_loop_header(
    head: str, roles: dict[str, str], what: str, store_re: re.Pattern[str] = _STORE_RE
) -> None:
    """Reject a ``for`` head that carries anything but induction arithmetic."""

    clauses = _split_top_level(head, ";")
    if len(clauses) != 3:
        raise fail("%s: loop head is not a three-clause bounded for" % what)
    induction = set(_INDUCTION_DECL_RE.findall(clauses[0]))
    for clause in clauses:
        effects = statement_effects(clause, roles, store_re)
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


def _label_statements(block: str) -> tuple[str, ...]:
    """Every statement in ``block``, at any depth, that opens with a label."""

    found: list[str] = []
    for kind, headline, nested in split_block(block):
        match = _LABEL_RE.match(headline.strip())
        if match is not None and match.group(1) not in _LABEL_KEYWORDS:
            found.append(match.group(1))
        if kind == "block":
            found.extend(_label_statements(nested))
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


# A guard body may publish the frozen result tuple and its first-observation
# timestamp. Anything else it carries -- a call above all -- is an effect the
# guard cannot own, whatever its condition turns out to be.
_CANONICAL_GUARD_EFFECTS = frozenset(("store", "timestamp"))
_CARRIED_EFFECT_PREFIXES = ("store", "timestamp", "call:")
_TERMINATOR_RE = re.compile(r"^(?:break|return)(?![A-Za-z0-9_])")
_BACK_EDGE_RE = re.compile(r"(?<![A-Za-z0-9_])(continue|goto)(?![A-Za-z0-9_])")


def subtree_effects(
    body: str, roles: dict[str, str], store_re: re.Pattern[str] = _STORE_RE
) -> tuple[str, ...]:
    """Return every effect carried anywhere inside ``body``, at any depth.

    ``split_block`` keeps a braceless ``if`` inside its own statement text, so
    scanning both the statement text and every nested block reaches an effect
    however it is written.
    """

    effects: list[str] = []
    for kind, headline, nested in split_block(body):
        effects.extend(statement_effects(headline, roles, store_re))
        if kind == "block":
            effects.extend(subtree_effects(nested, roles, store_re))
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
        for effect in subtree_effects(body, roles, store_re)
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


def _duplicate_roles(read_order: list[str]) -> list[str]:
    return sorted({role for role in read_order if read_order.count(role) > 1})


def _guard_kind(condition: str) -> str:
    if "V14_STATUS_RESET" in condition:
        return "reset"
    if "V14_STATUS_FAULT_MASK" in condition:
        return "fault"
    if "qsize_expected" in condition:
        return "completion"
    return "other"


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
    reset = [c for c, b in guards if "V14_STATUS_RESET" in c and "V14_PRIMARY_RESET" in b]
    fault = [c for c, b in guards if "V14_STATUS_FAULT_MASK" in c and "V14_PRIMARY_FAULT" in b]
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
    roles = pointer_roles(body)
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in a primary loop: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "primary loop")
    if "V14_ITERATION_BOUND" not in head:
        raise fail("primary loop bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "primary helper")
    verify_loop_header(head, roles, "primary loop", store_re)

    items = flatten_loop(loop_body, "primary loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    expected = ["QREAD"] if variant == "Q" else EXPECTED_PRIMARY_ORDER[variant]
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re)
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
        verify_guard_publication(head, guard_body, roles, "primary loop", store_re)
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

    guards = [
        (_guard_kind(head), head)
        for depth, kind, head, _ in items
        if depth == 0 and kind == "guard" and head.startswith("if")
    ]

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
        "q_timeout_classification": classification,
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
    install_sites = positions(vendor_masked, install)
    if len(install_sites) != 1:
        raise fail("runtime vector is not the exact stock u85_irq_handler")

    spans = function_spans(vendor_masked)
    setup_start, setup_stop = function_span(
        vendor_masked, enclosing_function(spans, install_sites[0]), "runtime setup function"
    )
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


# ---------------------------------------------------------------------------
# Common convergence tail
# ---------------------------------------------------------------------------

_PREDICATE_TERMS = (
    "qread == qsize_expected",
    "status & V14_STATUS_CMD_END",
    "status & V14_STATUS_IRQ_RAISED",
    "status & V14_STATUS_STATE",
)
_PREDICATE_IDENTIFIERS = frozenset(("qread", "status", "qsize_expected"))
# The lookbehind keeps the ``U`` of a ``0U`` literal from reading as a name.
_IDENTIFIER_RE = re.compile(r"(?<![0-9A-Za-z_])[A-Za-z_]\w*")


def verify_convergence_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the one shared bounded convergence tail."""

    try:
        body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    except GateError:
        raise fail("common convergence helper %s is missing" % CONVERGE_SYMBOL)

    roles = pointer_roles(body)
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in the convergence tail: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "convergence loop")
    if "V14_ITERATION_BOUND" not in head:
        raise fail("convergence bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "convergence helper")
    verify_loop_header(head, roles, "convergence loop", store_re)

    items = flatten_loop(loop_body, "convergence loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re)
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
        verify_guard_publication(head, guard_body, roles, "convergence loop", store_re)
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
        ("success" if "V14_CONVERGENCE_SUCCESS" in body else _guard_kind(head), head, body)
        for depth, kind, head, body in items
        if depth == 0 and kind == "guard" and head.startswith("if")
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

    if store_re.search(body[:loop_start]):
        raise fail("convergence evidence store occurs before the loop")

    return {
        "convergence_helper": CONVERGE_SYMBOL,
        "convergence_read_order": ["QREAD", "STATUS"],
        "convergence_bound": ITERATION_BOUND,
        "convergence_predicate_terms": list(_PREDICATE_TERMS),
    }


# ---------------------------------------------------------------------------
# Failure mailbox and success cleanup
# ---------------------------------------------------------------------------

_MAILBOX_DECL_RE = re.compile(r"volatile\s+uint32_t\s+%s\s*\[\s*(\d+)\s*\]" % re.escape(MAILBOX_SYMBOL))
_MAILBOX_STORE_RE = re.compile(r"%s\s*\[\s*([A-Za-z0-9_]+)\s*\]\s*=\s*([^;]+);" % re.escape(MAILBOX_SYMBOL))

_CONVERGENCE_TUPLE = ("convergence_final_qread", "convergence_final_status")
_FAILURE_TUPLE = ("failure_qread", "failure_status")
_FIRST_TUPLE_FIELDS = (
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
)


def _mbox_macro(field: str) -> str:
    return "V14_MBOX_" + field.upper()


def _mailbox_stores(block: str) -> tuple[tuple[str, str], ...]:
    return tuple((match.group(1), match.group(2).strip()) for match in _MAILBOX_STORE_RE.finditer(block))


def mailbox_store_pattern(aliases: tuple[str, ...]) -> re.Pattern[str]:
    """A mailbox-store recogniser that also sees the array's aliases."""

    return re.compile(
        r"(?<![A-Za-z0-9_])(?:%s)\s*\[\s*([A-Za-z0-9_]+)\s*\]\s*=\s*([^;]+);"
        % _alternation((MAILBOX_SYMBOL,) + aliases)
    )


def resolve_word(index_token: str, defines: dict[str, int]) -> int | None:
    """The appendix word an index expression names, or ``None`` if it is not one.

    An offset written as the frozen macro and the same offset written as its
    numeric value address the same word. A rule that only recognises the macro
    is a rule a bare ``[33]`` walks around, so both spellings resolve here and
    the *spelling* is judged separately from the *word*.
    """

    if index_token in defines:
        return defines[index_token]
    try:
        return int(index_token.rstrip("uU"), 0)
    except ValueError:
        return None


def is_magic_value(value: str, defines: dict[str, int]) -> bool:
    """Whether a stored value is the 0x5631344D magic, macro or literal."""

    token = value.strip()
    if token in defines:
        return defines[token] == MAILBOX_VALID
    try:
        return int(token.rstrip("uU"), 0) == MAILBOX_VALID
    except ValueError:
        return False


def _resolved_mailbox_stores(
    vendor_masked: str, defines: dict[str, int]
) -> tuple[tuple[int | None, str, str, str], ...]:
    """``(word, index_token, value, owner)`` for every mailbox store, aliases included."""

    spans = function_spans(vendor_masked)
    pattern = mailbox_store_pattern(mailbox_aliases(vendor_masked))
    stores = []
    for match in pattern.finditer(vendor_masked):
        index_token = match.group(1)
        stores.append(
            (
                resolve_word(index_token, defines),
                index_token,
                match.group(2).strip(),
                enclosing_function(spans, match.start()),
            )
        )
    return tuple(stores)


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

    stores = _resolved_mailbox_stores(vendor_masked, defines)
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

    reset = function_text(vendor_masked, MAILBOX_RESET_SYMBOL, "mailbox reset entry")
    if "V14_U32_INVALID" not in reset or "V14_APPENDIX_WORDS" not in reset:
        raise fail("mailbox reset does not invalidate every appendix field")
    reset_stores = _mailbox_stores(reset)
    if ("V14_MBOX_MAILBOX_VALID", "0U") not in reset_stores:
        raise fail("mailbox reset does not zero mailbox_valid")
    if reset_stores[-1] != ("V14_MBOX_MAILBOX_VALID", "0U"):
        raise fail("mailbox reset does not zero mailbox_valid last")
    if "__DSB()" not in reset:
        raise fail("mailbox reset does not issue a DSB")

    publish = function_text(vendor_masked, MAILBOX_PUBLISH_SYMBOL, "mailbox publication entry")
    publish_stores = _mailbox_stores(publish)
    if publish_stores != (("V14_MBOX_MAILBOX_VALID", "V14_MAILBOX_VALID"),):
        raise fail("mailbox magic is not the final appendix store: publication stores %s" % (publish_stores,))
    magic_match = _MAILBOX_STORE_RE.search(publish)
    if "__DSB()" not in publish[magic_match.end() :]:
        raise fail("mailbox publication does not issue a DSB")

    # The magic is what tells a reader the other 33 words are real, so it is
    # counted by *value* over every spelling a store can take: the frozen macro
    # or the bare 0x5631344D, the frozen symbol or an alias of it, the offset
    # macro or its numeric 33. Counting the macro text alone leaves three ways
    # to publish a second, earlier, unearned magic.
    magic_stores = [
        store
        for store in _resolved_mailbox_stores(vendor_masked, defines)
        if is_magic_value(store[2], defines)
    ]
    if len(magic_stores) != 1:
        raise fail(
            "mailbox_valid is published from more than one site: %d stores" % len(magic_stores)
        )
    word, index_token, value, owner = magic_stores[0]
    if word != APPENDIX_FIELDS.index("mailbox_valid"):
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
    failure_stores = dict(_mailbox_stores(failure))
    for field in _CONVERGENCE_TUPLE:
        if failure_stores.get(_mbox_macro(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a failure" % field)
    for field in _FIRST_TUPLE_FIELDS:
        if _mbox_macro(field) in failure_stores:
            raise fail("convergence failure discards the retained first-observation tuple: %s" % field)

    success = function_text(vendor_masked, "v14_publish_success", "success publication")
    success_stores = dict(_mailbox_stores(success))
    for field in _FAILURE_TUPLE:
        if success_stores.get(_mbox_macro(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a success" % field)
    if success_stores.get(_mbox_macro("failure_phase")) != "V14_PHASE_NONE":
        raise fail("success and failure tuples are both published as valid: failure_phase is not NONE")

    cleanup = function_text(vendor_masked, "v14_publish_cleanup_failure", "cleanup publication")
    cleanup_stores = dict(_mailbox_stores(cleanup))
    if cleanup_stores.get(_mbox_macro("failure_phase")) != "V14_PHASE_CLEANUP":
        raise fail("cleanup invariant is not recorded as failure_phase=CLEANUP")
    for field in _CONVERGENCE_TUPLE:
        if _mbox_macro(field) in cleanup_stores:
            raise fail("cleanup invariant discards the convergence tuple: %s" % field)

    first_words = {APPENDIX_FIELDS.index(field) for field in _FIRST_TUPLE_FIELDS}
    for word, index_token, _value, owner in _resolved_mailbox_stores(vendor_masked, defines):
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


SUCCESS_CLEANUP_ORDER = (
    "CMD2",
    "QREAD",
    "CMD2",
    "QREAD_VERIFY",
    "NVIC",
    "CMD0",
    "H-PRINTF",
    "CMD0xC",
)


def _hprintf_seam_site(cleanup: str, cleanup_raw: str, cmd0: int, terminal: int) -> int:
    """Return the offset of the one qualified H-PRINTF callsite in the window.

    ``mask_c_lexical`` preserves byte offsets, so the marker can be located in
    the raw text and compared against callsites found in the masked text. The
    marker is what makes this the qualified seam: a bare vendor printf in the
    release window is a debug print, not the ``__wrap_printf`` callsite the
    frozen V12 gate qualified.
    """

    markers = [site for site in positions(cleanup_raw, HPRINTF_SEAM_MARKER) if cmd0 < site < terminal]
    callsites = [site for site in positions(cleanup, "printf(") if cmd0 < site < terminal]
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
    between = cleanup_raw[markers[0] + len(HPRINTF_SEAM_MARKER) : callsites[0]]
    if markers[0] > callsites[0] or between.strip():
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: the seam marker does not anchor it"
            % HPRINTF_SEAM_MARKER_NAME
        )
    return callsites[0]


_TEST_CPM_IF_RE = re.compile(r"#[ \t]*if[ \t]*\(?[ \t]*TEST_CPM[ \t]*==[ \t]*1[ \t]*\)?")
_TEST_CPM_ENDIF_RE = re.compile(r"(?m)^[ \t]*#[ \t]*endif")


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

    primary_call = command.find(PRIMARY_SYMBOL[variant] + "(")
    if primary_call < 0:
        raise fail("command path does not call the variant primary helper")
    tail = command[primary_call + len(PRIMARY_SYMBOL[variant]) :]
    if "v14_primary_" in tail:
        raise fail("variant-specific block between the primary freeze and the common cleanup")

    for site in positions(command, "v14_publish_failure("):
        window_end = command.find("return", site)
        if window_end < 0:
            raise fail("failure path does not return after publication")
        window = command[site:window_end]
        if _CMD_WRITE in window:
            raise fail("failure path clears NPU state before serialization")
        if "printf(" in window:
            raise fail("failure path enters the H-PRINTF seam")

    history = re.search(r"irq_history_mask\s*=\s*([^;]+);", command)
    if history is None or "converged.status" not in history.group(1):
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")
    converge_call = command.find(CONVERGE_SYMBOL + "(")
    if converge_call < 0:
        raise fail("command path does not call the common convergence helper")
    if _STATUS_READ in command[converge_call:]:
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")

    cleanup = command[history.start() :]
    cleanup_raw = command_raw[history.start() :]
    markers: list[tuple[int, str]] = []
    for site in positions(cleanup, "write_reg(NPU_REG_CMD, 0x00000002)"):
        markers.append((site, "CMD2"))
    for site in positions(cleanup, "read_reg(NPU_REG_QREAD)"):
        markers.append((site, "QREAD"))
    for site in positions(cleanup, "read_val == u32CmdQueueSize"):
        markers.append((site, "QREAD_VERIFY"))
    for site in positions(cleanup, "NVIC_ClearPendingIRQ("):
        markers.append((site, "NVIC"))
    cmd0 = positions(cleanup, "write_reg(NPU_REG_CMD, 0x00000000)")
    for site in cmd0:
        markers.append((site, "CMD0"))
    terminal = positions(cleanup, "write_reg(NPU_REG_CMD, 0x0000000C)")
    for site in terminal:
        markers.append((site, "CMD0xC"))
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
        "success_cleanup_order": list(SUCCESS_CLEANUP_ORDER),
        "failure_paths_clear_npu": False,
        "failure_paths_enter_hprintf": False,
        "hprintf_seam_marker": HPRINTF_SEAM_MARKER_NAME,
        "hprintf_seam_wrap_symbol": HPRINTF_WRAP_SYMBOL,
        "hprintf_callsite_elf_qualified": False,
        "cleanup_terminal_conditional_on": "TEST_CPM==1",
        "cleanup_terminal_branch_compiled_proof": False,
    }


# ---------------------------------------------------------------------------
# Runner wire contract
# ---------------------------------------------------------------------------

_RECORD_FIELD_RE = re.compile(r"uint32_t\s+([A-Za-z_]\w*)\s*;")
_SERIALIZE_RE = re.compile(r"put32\s*\(\s*&c\s*,\s*d\s*->\s*([A-Za-z_]\w*)\s*\)")
def runner_copy_pattern(aliases: tuple[str, ...]) -> re.Pattern[str]:
    """An appendix-copy recogniser that also sees the mailbox array's aliases."""

    return re.compile(
        r"d\.([A-Za-z_]\w*)\s*=\s*(?:%s)\s*\[" % _alternation((MAILBOX_SYMBOL,) + aliases)
    )


MEASURED_CALL = "run_fixed_inference()"


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
        if assertion not in runner_masked:
            raise fail(reason)

    record_end = runner_masked.find("} pmu_diag_record_t;")
    record_start = runner_masked.rfind("typedef struct", 0, record_end) if record_end >= 0 else -1
    if record_start < 0:
        raise fail("runner record does not carry the 34 appendix fields in wire order: no record found")
    if not _contiguous_appendix_run(_RECORD_FIELD_RE.findall(runner_masked[record_start:record_end])):
        raise fail("runner record does not carry the 34 appendix fields in wire order")

    if not _contiguous_appendix_run(_SERIALIZE_RE.findall(runner_masked)):
        raise fail("runner serialization order does not match the appendix table")

    reset_site = runner_masked.find(MAILBOX_RESET_SYMBOL + "();")
    driver_site = runner_masked.find(MEASURED_CALL, reset_site) if reset_site >= 0 else -1
    if reset_site < 0 or driver_site < 0:
        raise fail("runner does not reset the mailbox before the measured call")

    magic_guard = re.search(
        r"if\s*\(\s*%s\s*\[\s*%d\s*\]\s*!=\s*V14_MAILBOX_VALID\s*\)"
        % (re.escape(MAILBOX_SYMBOL), APPENDIX_FIELDS.index("mailbox_valid")),
        runner_masked,
    )
    if magic_guard is None:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    else_site = runner_masked.find("else", magic_guard.end())
    if else_site < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    open_index = runner_masked.find("{", else_site)
    if open_index < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    close_index = _matching_brace(runner_masked, open_index, "runner magic else branch")
    copy_re = runner_copy_pattern(mailbox_aliases(runner_masked))
    copies = tuple(match.group(1) for match in copy_re.finditer(runner_masked[open_index:close_index]))
    if copies != APPENDIX_FIELDS:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")

    # Dominance is not "the valid branch copies all 34"; it is "the 34 are
    # copied *only* there". A copy before the guard runs whatever the magic
    # says, and a copy in the invalid branch publishes reset sentinels -- or
    # stale words from a previous run -- as if they were evidence.
    stray = [
        match
        for match in copy_re.finditer(runner_masked)
        if not open_index <= match.start() < close_index
    ]
    if stray:
        raise fail(
            "runner copies the appendix outside the mailbox-magic branch: %s copied at %d"
            % (stray[0].group(1), stray[0].start())
        )

    return {
        "runner_serialized_words": TOTAL_WORDS,
        "runner_payload_bytes": PAYLOAD_BYTES,
        "runner_copy_dominated_by_magic": True,
        "runner_appendix_copies": len(copies),
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
    """Write the manifest, reporting a bad path as a named rejection.

    A bare relative filename is a legitimate output path and needs no directory
    handling at all; a path whose directory does not exist is an operator
    mistake. Either way the caller gets a ``FAIL`` line, because a traceback on
    stderr is not a verdict a gate is allowed to emit.
    """

    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError as exc:
        raise fail("fixture manifest is not writable at %r (%s)" % (path, exc))


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
        _write_manifest(args.fixture_manifest_out, doc)
    except GateError as exc:
        print("FAIL %s" % exc)
        return 1

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
    convergence = verify_convergence_contract(vendor_masked, defines)
    mailbox = verify_mailbox_contract(vendor_masked, defines)
    identity = verify_variant_identity(vendor_masked, defines, variant)
    cleanup = verify_cleanup_contract(vendor_masked, vendor_text, variant, defines)
    runner = verify_runner_contract(mask_c_lexical(runner_text))
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
        # The frozen u85.c is not tracked in this repository. The vendor half of
        # this contract therefore runs against a stock fixture, and saying so is
        # part of the verdict rather than a footnote to it.
        "vendor_raw_source_verified": False,
        "residual_limitations": list(RESIDUAL_LIMITATIONS),
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
        "common_convergence_source_sha256": normalized_digest(converge_body),
        "common_tail_source_sha256": normalized_digest(command[tail_start:]),
    }
    for section in (pre_run, primary, hard_bypass, convergence, mailbox, identity, cleanup, runner):
        doc.update(section)
    return doc


if __name__ == "__main__":
    sys.exit(main())
