"""Static source and cross-ELF gate for PMU_COMPLETION_POLL_COUNT_DIAG_V13.

The gate proves two independent properties:

1. the generated V13 sources publish ``poll_remaining_at_success`` exactly once,
   on the success path only, immediately after P2, from the loop induction
   variable; and
2. the final V13 poll loop is structurally the V12 poll loop plus that single
   post-P2 store, with the stored value flowing out of the register that the
   failed-poll conditional back edge decrements.

Property 2 is derived from the instruction stream itself (basic-block edges,
register definitions and uses), not from disassembly comments or fixed
addresses, so a relabelled or relocated build is accepted while an extra
per-iteration effect is not.

Scope: this module gates generated sources and the helper poll loop of the two
final ELFs. The retained V12 executable proofs that need whole-image artifacts
(stock vector table, NVIC hard-bypass, path-sensitive CMD/QREAD, PMU, H-PRINTF,
golden output, terminal release) stay in ``check_pmu_completion_poll_v12`` and
are re-run against the V13 image by the V13 build graph; the only retained-V12
proof enforced here is that the V13 image reintroduces no NVIC enable/vector
call site.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from check_pmu_completion_poll_v12 import (
    _function_section,
    count_once,
    fail,
    parse_functions,
)

SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
VARIANT = "PMU_COMPLETION_POLL_COUNT_DIAG_V13"
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
STATUS_ADDRESS = 0x51000014
DWT_CYCCNT_ADDRESS = 0xE0001004
COMPLETION_MASK = 0x02
POLL_LIMIT = 10000
NPU_MMIO_BASE = 0x51000000
NPU_MMIO_LIMIT = 0x51001000
SRAM_BASE = 0x20000000
SRAM_LIMIT = 0x30000000

_RAW_RUNNER_ANCHOR = "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;"
_RAW_VENDOR_ANCHOR = "static int test_commands( const u85_eTest eTest,"
_RAW_RUNNER_GENERATED_MARKER = "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID"
_RAW_VENDOR_GENERATED_MARKER = "v12_poll_completion(void)"

_REMAINING_SYMBOL = "pmu_completion_poll_v13_t_poll_remaining_at_success"
_P1_STATEMENT = "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;"
_P2_STATEMENT = "pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;"
_LOOP_HEADER = "for (uint32_t i = 0U; i < %dU; ++i) {" % POLL_LIMIT
_SUCCESS_GUARD = "if ((status & 0x%02XU) != 0U) {" % COMPLETION_MASK
_STATUS_READ_STATEMENT = "status = *status_reg;"
_REMAINING_RHS = "%dU - i" % POLL_LIMIT

_HEX_WORD_RE = re.compile(r"\.word\s+0x([0-9A-Fa-f]+)")
_ENCODING_RE = re.compile(r"^(?:[0-9a-f]{8}|[0-9a-f]{4}(?:\s+[0-9a-f]{4})*)\s+(?=[a-z.])")
_BRANCH_TARGET_RE = re.compile(r"\b([0-9a-fA-F]+)\s+<")
_LOAD_RE = re.compile(r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+(r\d+),\s*\[([a-z0-9]+)")
_PC_LOAD_RE = re.compile(r"^ldr(?:\.w)?\s+(r\d+),\s*\[pc\b")
_STORE_RE = re.compile(r"^str(?:b|h)?(?:\.w)?\s+(r\d+),\s*\[([a-z0-9]+)")
_DECREMENT_RE = re.compile(r"^subs(?:\.w)?\s+(r\d+),\s*#1$")
_TEST_RE = re.compile(r"^tst(?:\.w)?\s+(r\d+),\s*#(\d+)$")
_DEST_RE = re.compile(r"^[a-z][a-z0-9.]*\s+(r\d+)\b")
_CALL_TO_RE = r"\bbl(?:x)?(?:\.w)?\s+[0-9a-fA-F]+\s+<%s>"

_WRITING_MNEMONICS = frozenset(
    (
        "mov", "movs", "movw", "movt", "mvn", "mvns", "neg", "negs",
        "add", "adds", "adc", "adcs", "sub", "subs", "sbc", "sbcs", "rsb", "rsbs",
        "and", "ands", "orr", "orrs", "orn", "eor", "eors", "bic", "bics",
        "lsl", "lsls", "lsr", "lsrs", "asr", "asrs", "ror", "rors",
        "mul", "muls", "mla", "mls", "udiv", "sdiv", "umull", "smull",
        "ldr", "ldrb", "ldrh", "ldrsb", "ldrsh",
        "uxtb", "uxth", "sxtb", "sxth", "rev", "rev16", "clz", "ubfx", "sbfx",
    )
)
_STACK_MNEMONICS = frozenset(("push", "pop", "stm", "stmdb", "ldm", "ldmia"))
_CALL_MNEMONICS = frozenset(("bl", "blx"))
_COND_BRANCH_MNEMONICS = frozenset(
    (
        "bne", "beq", "bcs", "bhs", "bcc", "blo", "bmi", "bpl", "bvs", "bvc",
        "bhi", "bls", "bge", "blt", "bgt", "ble", "cbz", "cbnz",
    )
)
_V12_RUNTIME_DRIFT_CALLEES = ("NVIC_EnableIRQ", "NVIC_SetVector", "NVIC_ClearPendingIRQ")


@dataclass(frozen=True)
class _Insn:
    """One helper instruction with the objdump encoding column removed."""

    addr: int
    mnemonic: str
    text: str
    target: int | None
    is_cond_branch: bool
    is_return: bool


@dataclass(frozen=True)
class PollLoop:
    variant: str
    helper_name: str
    helper_addr: int
    status_addr: int
    mask: int
    status_base_reg: str
    status_value_reg: str
    status_read_count: int
    failed_path_decrement_regs: tuple[str, ...]
    failed_path_decrement_count: int
    back_edge_target: int
    conditional_back_edge_count: int
    success_edge_count: int
    timeout_edge_count: int
    extra_per_iteration_instruction_count: int
    has_stack_access: bool
    has_extra_non_status_load: bool
    has_forbidden_loop_effect: bool


@dataclass(frozen=True)
class RemainingDataflowProof:
    source: str
    induction_register: str
    remaining_store_after_p2_exactly_once: bool
    remaining_store_timeout_unreachable: bool
    remaining_from_back_edge_induction: bool
    helper_leaf_no_stack_access: bool


@dataclass(frozen=True)
class _HelperAnalysis:
    variant: str
    helper_name: str
    helper_addr: int
    code: tuple[_Insn, ...]
    literal_words: tuple[int, ...]
    status_index: int
    test_index: int
    success_branch_index: int
    success_index: int
    back_edge_index: int
    loop_head_addr: int
    status_base_reg: str
    status_value_reg: str
    mask: int
    decrement_regs: tuple[str, ...]
    loop_body: tuple[_Insn, ...]
    timeout_block: tuple[_Insn, ...]
    has_stack_access: bool
    has_extra_non_status_load: bool


# --------------------------------------------------------------------------
# generated-source gate
# --------------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _count_raw_inputs(text: str, anchor: str, generated_marker: str, kind: str) -> None:
    if generated_marker in text:
        raise fail("generated %s input" % kind)
    count = text.count(anchor)
    if count == 0:
        raise fail("zero raw %s targets" % kind)
    if count != 1:
        raise fail("multiple raw %s targets" % kind)


def _matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise fail("canonical V13 helper shape missing")


def _extract_vendor_helper(vendor_text: str) -> str:
    starts = (
        "__attribute__((noinline))\nstatic uint32_t v13_poll_completion(void)",
        "uint32_t __attribute__((noinline)) v13_poll_completion(void)",
        "static uint32_t v13_poll_completion(void)",
    )
    start = -1
    for candidate in starts:
        start = vendor_text.find(candidate)
        if start >= 0:
            break
    if start < 0:
        raise fail("poll helper signature not found")
    end = vendor_text.find("static int test_commands(", start)
    if end < 0:
        end = len(vendor_text)
    return vendor_text[start:end]


def _verify_runner_source(runner_text: str) -> None:
    if "PMU_COMPLETION_POLL_DIAG_V13" not in runner_text:
        raise fail("runner schema marker missing")
    if "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x%08XU" % BUILD_ID not in runner_text:
        raise fail("runner build id missing")
    count_once(runner_text, "extern volatile uint32_t %s;" % _REMAINING_SYMBOL, "runner remaining extern")
    count_once(runner_text, "uint32_t poll_remaining_at_success;", "runner remaining field")
    count_once(runner_text, "poll_remaining_at_success = 0U;", "runner remaining reset")
    for needle, what in (
        ("PMU_DIAG_FIELD_COUNT 101U", "runner field count"),
        ("PMU_DIAG_TOTAL_WORDS 109U", "runner total words"),
        ("PMU_DIAG_PAYLOAD_SIZE 436U", "runner payload size"),
    ):
        if needle not in runner_text and needle.replace(" ", " == ") not in runner_text:
            raise fail("%s missing" % what)
    if (
        "put32(&c, d->poll_remaining_at_success);" not in runner_text
        and "out_words[100] = d->poll_remaining_at_success;" not in runner_text
    ):
        raise fail("runner remaining serialization missing")


def _verify_vendor_helper_source(helper: str) -> None:
    if helper.count("*status_reg") != 1 or helper.count(_STATUS_READ_STATEMENT) != 1:
        raise fail("helper STATUS read count != 1")
    if helper.count(_SUCCESS_GUARD) != 1:
        raise fail("helper completion mask")
    if (
        "write_reg(NPU_REG_CMD" in helper
        or "read_reg(NPU_REG_QREAD)" in helper
        or "0x0000000C" in helper
    ):
        raise fail("retained V12 hard-bypass/CMD/QREAD/release drift")
    if re.findall(r"NPU_REG_[A-Z0-9_]+", helper) != ["NPU_REG_STATUS"]:
        raise fail("helper contains forbidden operation")
    if helper.count("U85_BASE_ADDRESS") != 1:
        raise fail("helper contains forbidden operation")

    if helper.count(_LOOP_HEADER) != 1:
        raise fail("canonical V13 helper shape missing")
    loop_open = helper.index("{", helper.index(_LOOP_HEADER))
    loop_end = _matching_brace(helper, loop_open)
    guard_start = helper.find(_SUCCESS_GUARD, loop_open)
    if not loop_open < guard_start < loop_end:
        raise fail("canonical V13 helper shape missing")
    guard_open = helper.index("{", guard_start)
    guard_end = _matching_brace(helper, guard_open)

    assignments = [
        (hit.start(), hit.group(1).strip())
        for hit in re.finditer(r"%s\s*=\s*([^;]+);" % re.escape(_REMAINING_SYMBOL), helper)
    ]
    references = len(re.findall(re.escape(_REMAINING_SYMBOL), helper))
    if references != len(assignments):
        raise fail("remaining store must be success-only")
    if any(position > loop_end for position, _ in assignments):
        raise fail("timeout path must not publish remaining")
    if any(not guard_open < position < guard_end for position, _ in assignments):
        raise fail("remaining store must be success-only")
    if len(assignments) != 1:
        raise fail("poll_remaining_at_success store count != 1")

    remaining_position, remaining_rhs = assignments[0]
    if remaining_rhs != _REMAINING_RHS:
        literal = re.fullmatch(r"(\d+)U?", remaining_rhs)
        if literal is not None and not 1 <= int(literal.group(1)) <= POLL_LIMIT:
            raise fail("success remaining must be in 1..%d" % POLL_LIMIT)
        raise fail("remaining must be derived from the loop induction variable")

    p1_position = helper.find(_P1_STATEMENT, guard_open)
    p2_position = helper.find(_P2_STATEMENT, guard_open)
    if not guard_open < p1_position < p2_position < remaining_position < guard_end:
        raise fail("remaining store must follow P2 exactly")
    if helper.find("return status;", remaining_position) > guard_end:
        raise fail("canonical V13 helper shape missing")

    if helper[loop_open + 1:guard_start].strip() != _STATUS_READ_STATEMENT:
        raise fail("extra per-iteration source statement")
    if helper[guard_end + 1:loop_end].strip():
        raise fail("extra per-iteration source statement")
    if "return 0U;" not in helper[loop_end:]:
        raise fail("canonical V13 helper shape missing")


def verify_generated_sources(
    runner_text: str,
    vendor_text: str,
    *,
    raw_runner_sha256: str | None = None,
    raw_vendor_sha256: str | None = None,
) -> dict[str, object]:
    """Gate the generated V13 runner/vendor sources.

    When raw SHA-256 pins are supplied the arguments are treated as the frozen
    *raw* generator inputs and only the frozen-input contract is enforced.
    """
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    raw_validation_requested = raw_runner_sha256 is not None or raw_vendor_sha256 is not None
    if raw_runner_sha256 is not None:
        _count_raw_inputs(runner_text, _RAW_RUNNER_ANCHOR, _RAW_RUNNER_GENERATED_MARKER, "runner")
        if _sha256_text(runner_text) != raw_runner_sha256:
            raise fail("runner hash mismatch")
    if raw_vendor_sha256 is not None:
        _count_raw_inputs(vendor_text, _RAW_VENDOR_ANCHOR, _RAW_VENDOR_GENERATED_MARKER, "vendor")
        if _sha256_text(vendor_text) != raw_vendor_sha256:
            raise fail("vendor hash mismatch")
    if not raw_validation_requested:
        _verify_runner_source(runner_text)
        _verify_vendor_helper_source(_extract_vendor_helper(vendor_text))

    return {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "poll_remaining_symbol": _REMAINING_SYMBOL,
    }


# --------------------------------------------------------------------------
# final-ELF gate
# --------------------------------------------------------------------------


def _helper_name_from_nm(nm_text: str) -> str:
    names = re.findall(r"^[0-9A-Fa-f]+\s+[Tt]\s+([A-Za-z0-9_]+)$", nm_text, re.M)
    for candidate in ("v12_poll_completion", "v13_poll_completion"):
        if names.count(candidate) == 1:
            return candidate
    raise fail("poll helper symbol in nm: expected 1 text symbol, found 0")


def _symbol_addr_from_nm(nm_text: str, symbol: str) -> int:
    match = re.search(r"^([0-9A-Fa-f]+)\s+[Tt]\s+%s$" % re.escape(symbol), nm_text, re.M)
    if match is None:
        raise fail("missing symbol in nm: %s" % symbol)
    return int(match.group(1), 16)


def _split_code_and_literals(raw_insns) -> tuple[tuple[_Insn, ...], tuple[int, ...]]:
    """Normalize objdump rows into instructions plus the helper literal pool.

    The V12 parser keeps the raw encoding column in ``text``; strip it here so
    mnemonic classification does not depend on the objdump invocation flags.
    """
    code: list[_Insn] = []
    words: list[int] = []
    for raw in raw_insns:
        body = _ENCODING_RE.sub("", raw.text).strip()
        if body.startswith(".word"):
            hit = _HEX_WORD_RE.search(body)
            if hit is None:
                raise fail("helper literal pool word unreadable")
            words.append(int(hit.group(1), 16))
            continue
        if not body or body.startswith("."):
            continue
        mnemonic = body.split()[0].lower().split(".")[0]
        target_hit = _BRANCH_TARGET_RE.search(body)
        code.append(
            _Insn(
                addr=raw.addr,
                mnemonic=mnemonic,
                text=body,
                target=int(target_hit.group(1), 16) if target_hit else None,
                is_cond_branch=mnemonic in _COND_BRANCH_MNEMONICS,
                is_return=(mnemonic == "bx" and body.rstrip().endswith("lr"))
                or (mnemonic == "pop" and "pc" in body),
            )
        )
    return tuple(code), tuple(words)


def _defined_register(insn: _Insn) -> str | None:
    if insn.mnemonic not in _WRITING_MNEMONICS:
        return None
    if _STORE_RE.match(insn.text):
        return None
    hit = _DEST_RE.match(insn.text)
    return hit.group(1) if hit else None


def _is_stack_access(insn: _Insn) -> bool:
    return "[sp" in insn.text or insn.mnemonic in _STACK_MNEMONICS


def _is_call(insn: _Insn) -> bool:
    return insn.mnemonic in _CALL_MNEMONICS


def _check_literal_pool(words: tuple[int, ...]) -> None:
    npu_words = [word for word in words if NPU_MMIO_BASE <= word < NPU_MMIO_LIMIT]
    if npu_words != [STATUS_ADDRESS]:
        raise fail("helper STATUS MMIO address")
    for word in words:
        if word in (STATUS_ADDRESS, DWT_CYCCNT_ADDRESS):
            continue
        if SRAM_BASE <= word < SRAM_LIMIT:
            continue
        raise fail("helper references unexpected MMIO literal 0x%08X" % word)


def _check_loop_body(loop_body: tuple[_Insn, ...]) -> tuple[str, ...]:
    for insn in loop_body:
        if _is_call(insn):
            raise fail("extra per-iteration call")
    for insn in loop_body:
        if _is_stack_access(insn):
            raise fail("extra per-iteration load/store")
    for insn in loop_body:
        if _STORE_RE.match(insn.text):
            raise fail("extra per-iteration store")
        if _LOAD_RE.match(insn.text):
            raise fail("extra per-iteration load/store")
    decrements = tuple(
        hit.group(1) for hit in (_DECREMENT_RE.match(insn.text) for insn in loop_body) if hit
    )
    if len(decrements) != 2:
        raise fail("failed-poll decrement count")
    if len(loop_body) != len(decrements):
        raise fail("extra per-iteration instruction")
    return decrements


def _analyze_helper(disassembly_text: str, nm_text: str) -> _HelperAnalysis:
    helper_name = _helper_name_from_nm(nm_text)
    helper_addr = _symbol_addr_from_nm(nm_text, helper_name)
    functions = parse_functions(disassembly_text)
    insns = functions.get(helper_name)
    if insns is None:
        raise fail("helper function in disassembly: expected 1 match, found 0")
    if insns[0].addr != helper_addr:
        raise fail("helper symbol/address mismatch")
    _function_section(disassembly_text, helper_name)

    code, literal_words = _split_code_and_literals(insns)
    if not code:
        raise fail("helper disassembly empty")
    _check_literal_pool(literal_words)

    pointer_regs = {
        hit.group(1)
        for hit in (_PC_LOAD_RE.match(insn.text) for insn in code)
        if hit is not None
    }

    tests = [(index, _TEST_RE.match(insn.text)) for index, insn in enumerate(code)]
    tests = [(index, hit) for index, hit in tests if hit is not None]
    if len(tests) != 1:
        raise fail("helper completion mask: expected 1 completion test, found %d" % len(tests))
    test_index, test_hit = tests[0]
    status_value_reg = test_hit.group(1)
    mask = int(test_hit.group(2))
    if mask != COMPLETION_MASK:
        raise fail("helper completion mask")

    status_index = -1
    for index in range(test_index - 1, -1, -1):
        hit = _LOAD_RE.match(code[index].text)
        if hit and hit.group(1) == status_value_reg and hit.group(2) != "pc":
            status_index = index
            break
    if status_index < 0:
        raise fail("helper STATUS read shape missing")
    status_base_reg = _LOAD_RE.match(code[status_index].text).group(2)
    if status_base_reg not in pointer_regs:
        raise fail("helper STATUS pointer is not literal-pool resolved")
    status_reads = [
        insn
        for insn in code
        if (hit := _LOAD_RE.match(insn.text)) is not None and hit.group(2) == status_base_reg
    ]
    if len(status_reads) != 1:
        raise fail("helper STATUS read count != 1")
    loop_head_addr = code[status_index].addr

    success_branch_index = test_index + 1
    if success_branch_index >= len(code):
        raise fail("success branch missing")
    success_branch = code[success_branch_index]
    if not success_branch.is_cond_branch or success_branch.target is None:
        raise fail("success branch missing")
    success_addr = success_branch.target
    success_index = next((index for index, insn in enumerate(code) if insn.addr == success_addr), -1)
    if success_index <= success_branch_index:
        raise fail("success branch target missing")

    back_edges = [
        index
        for index, insn in enumerate(code)
        if insn.is_cond_branch and insn.target == loop_head_addr
    ]
    if len(back_edges) != 1:
        raise fail("conditional loop back-edge")
    back_edge_index = back_edges[0]
    if not success_branch_index < back_edge_index < success_index:
        raise fail("conditional loop back-edge")

    loop_body = code[success_branch_index + 1:back_edge_index]
    decrement_regs = _check_loop_body(loop_body)

    timeout_block = code[back_edge_index + 1:success_index]
    for insn in timeout_block:
        if _STORE_RE.match(insn.text):
            raise fail("timeout path must not publish remaining")
    if not any(insn.is_return for insn in timeout_block):
        raise fail("timeout exit edge missing")

    has_extra_non_status_load = False
    for insn in code:
        hit = _LOAD_RE.match(insn.text)
        if hit is None or hit.group(2) == "pc":
            continue
        if hit.group(2) not in pointer_regs:
            has_extra_non_status_load = True
            break

    return _HelperAnalysis(
        variant="v12" if helper_name.startswith("v12_") else "v13",
        helper_name=helper_name,
        helper_addr=helper_addr,
        code=code,
        literal_words=literal_words,
        status_index=status_index,
        test_index=test_index,
        success_branch_index=success_branch_index,
        success_index=success_index,
        back_edge_index=back_edge_index,
        loop_head_addr=loop_head_addr,
        status_base_reg=status_base_reg,
        status_value_reg=status_value_reg,
        mask=mask,
        decrement_regs=decrement_regs,
        loop_body=loop_body,
        timeout_block=timeout_block,
        has_stack_access=any(_is_stack_access(insn) for insn in code),
        has_extra_non_status_load=has_extra_non_status_load,
    )


def extract_poll_loop(disassembly_text: str, nm_text: str) -> PollLoop:
    analysis = _analyze_helper(disassembly_text, nm_text)
    return PollLoop(
        variant=analysis.variant,
        helper_name=analysis.helper_name,
        helper_addr=analysis.helper_addr,
        status_addr=STATUS_ADDRESS,
        mask=analysis.mask,
        status_base_reg=analysis.status_base_reg,
        status_value_reg=analysis.status_value_reg,
        status_read_count=1,
        failed_path_decrement_regs=analysis.decrement_regs,
        failed_path_decrement_count=len(analysis.decrement_regs),
        back_edge_target=analysis.loop_head_addr,
        conditional_back_edge_count=1,
        success_edge_count=1,
        timeout_edge_count=1,
        extra_per_iteration_instruction_count=len(analysis.loop_body) - len(analysis.decrement_regs),
        has_stack_access=analysis.has_stack_access,
        has_extra_non_status_load=analysis.has_extra_non_status_load,
        has_forbidden_loop_effect=any(
            _is_call(insn) or _is_stack_access(insn) or _STORE_RE.match(insn.text)
            for insn in analysis.loop_body
        ),
    )


def normalize_poll_loop(loop: PollLoop) -> tuple[tuple[str, int], ...]:
    """Register names, addresses and literal-pool layout are normalized away."""
    return (
        ("status_reads_per_iteration", loop.status_read_count),
        ("mask", loop.mask),
        ("failed_path_decrements", loop.failed_path_decrement_count),
        ("conditional_back_edges", loop.conditional_back_edge_count),
        ("success_edges", loop.success_edge_count),
        ("timeout_edges", loop.timeout_edge_count),
        ("extra_per_iteration_instruction_count", loop.extra_per_iteration_instruction_count),
    )


def _success_block(analysis: _HelperAnalysis) -> tuple[_Insn, ...]:
    for index in range(analysis.success_index, len(analysis.code)):
        if analysis.code[index].is_return:
            return analysis.code[analysis.success_index:index + 1]
    raise fail("success path return missing")


def _classify_success_stores(block: tuple[_Insn, ...]) -> tuple[list[int], list[tuple[int, str]]]:
    """Split success-path stores into memory-derived (P1/P2) and live-in stores."""
    memory_derived: set[str] = set()
    cyccnt_store_offsets: list[int] = []
    live_in_stores: list[tuple[int, str]] = []
    for offset, insn in enumerate(block):
        store = _STORE_RE.match(insn.text)
        if store is not None:
            if store.group(1) in memory_derived:
                cyccnt_store_offsets.append(offset)
            else:
                live_in_stores.append((offset, store.group(1)))
            continue
        dest = _defined_register(insn)
        if dest is None:
            continue
        load = _LOAD_RE.match(insn.text)
        if load is not None and load.group(2) != "pc":
            memory_derived.add(dest)
        else:
            memory_derived.discard(dest)
    return cyccnt_store_offsets, live_in_stores


def prove_remaining_dataflow(disassembly_text: str, nm_text: str) -> RemainingDataflowProof:
    analysis = _analyze_helper(disassembly_text, nm_text)
    if analysis.variant != "v13":
        raise fail("remaining dataflow proof requires V13 helper")

    block = _success_block(analysis)
    cyccnt_store_offsets, live_in_stores = _classify_success_stores(block)
    if len(cyccnt_store_offsets) != 2:
        raise fail("success path P1/P2 cycle-count store count != 2")
    if len(live_in_stores) != 1:
        raise fail("remaining store after P2 count != 1")
    remaining_offset, remaining_reg = live_in_stores[0]
    if remaining_offset < max(cyccnt_store_offsets):
        raise fail("remaining store must follow P2 exactly")

    induction_reg = analysis.decrement_regs[-1]
    if remaining_reg != induction_reg:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    for insn in block[:remaining_offset]:
        if _defined_register(insn) == remaining_reg:
            raise fail("remaining must dataflow from failed-poll countdown live-out")

    if analysis.has_stack_access:
        raise fail("helper must remain a leaf without stack access")
    if analysis.has_extra_non_status_load:
        raise fail("extra non-STATUS load")

    return RemainingDataflowProof(
        source="back_edge_induction",
        induction_register=induction_reg,
        remaining_store_after_p2_exactly_once=True,
        remaining_store_timeout_unreachable=True,
        remaining_from_back_edge_induction=True,
        helper_leaf_no_stack_access=True,
    )


def _check_retained_v12_runtime(disassembly_text: str) -> None:
    for callee in _V12_RUNTIME_DRIFT_CALLEES:
        if re.search(_CALL_TO_RE % re.escape(callee), disassembly_text):
            raise fail("retained V12 vector/NVIC/CMD/QREAD/PMU/release drift")


def verify_cross_elf_contract(
    v12_disassembly_text: str,
    v12_nm_text: str,
    v13_disassembly_text: str,
    v13_nm_text: str,
) -> dict[str, object]:
    v12_loop = extract_poll_loop(v12_disassembly_text, v12_nm_text)
    v13_loop = extract_poll_loop(v13_disassembly_text, v13_nm_text)
    if v12_loop.variant != "v12" or v13_loop.variant != "v13":
        raise fail("cross-ELF gate requires one V12 and one V13 helper")
    if normalize_poll_loop(v12_loop) != normalize_poll_loop(v13_loop):
        raise fail("V12/V13 normalized poll loop mismatch")
    if v13_loop.extra_per_iteration_instruction_count != 0 or v13_loop.has_forbidden_loop_effect:
        raise fail("extra per-iteration instruction")
    proof = prove_remaining_dataflow(v13_disassembly_text, v13_nm_text)
    _check_retained_v12_runtime(v13_disassembly_text)
    return {
        "variant": VARIANT,
        "v12_v13_poll_loop_semantically_equivalent": True,
        "v13_extra_per_iteration_instruction_count_zero": True,
        "remaining_store_after_p2_exactly_once": proof.remaining_store_after_p2_exactly_once,
        "remaining_from_back_edge_induction": proof.remaining_from_back_edge_induction,
        "remaining_store_timeout_unreachable": proof.remaining_store_timeout_unreachable,
        "helper_leaf_no_stack_access": proof.helper_leaf_no_stack_access,
        "remaining_induction_register": proof.induction_register,
        "loop_equivalent": True,
    }
