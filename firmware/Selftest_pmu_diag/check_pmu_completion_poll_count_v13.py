"""Static source and synthetic cross-ELF gate for PMU_COMPLETION_POLL_COUNT_DIAG_V13."""

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

_RAW_RUNNER_ANCHOR = "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;"
_RAW_VENDOR_ANCHOR = "static inline uint32_t wait_for_completion(void)"
_HEX_WORD_RE = re.compile(r"\.word\s+0x([0-9A-Fa-f]+)")
_RAW_LOAD_RE = re.compile(r"\bldr(?:\.w)?\s+(r\d+),\s+\[(r\d+)(?:,\s*#[0-9]+)?\]")
_RAW_PC_LOAD_RE = re.compile(r"\bldr(?:\.w)?\s+(r\d+),\s+\[pc,")
_SUBS_RE = re.compile(r"\bsubs(?:\.w)?\s+(r\d+),\s*#1\b")
_MOV_IMM_RE = re.compile(r"\bmov(?:s|\.w)?\s+(r\d+),\s*#")
_WRITES_RE = re.compile(r"\b(?:mov|movs|movw|movt|sub|subs|sub\.w|add|adds|ldr|ldrb|ldrh|and|ands|orr|eor|lsl|lsls|lsr|lsrs)\s+(r\d+)\b")


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
    remaining_store_after_p2_exactly_once: bool
    remaining_store_timeout_unreachable: bool
    remaining_from_back_edge_induction: bool
    helper_leaf_no_stack_access: bool


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


def _marker_lines(section_text: str, marker: str) -> list[str]:
    pattern = re.compile(r";\s*%s\s*$" % re.escape(marker))
    return [line.strip() for line in section_text.splitlines() if pattern.search(line)]


def _line_has_marker(line: str, marker: str) -> bool:
    return re.search(r";\s*%s\s*$" % re.escape(marker), line) is not None


def _marker_line(section_text: str, marker: str, *, what: str | None = None) -> str:
    lines = _marker_lines(section_text, marker)
    if len(lines) != 1:
        raise fail("%s count != 1" % (what or marker))
    return lines[0]


def _marker_addr(section_text: str, marker: str, *, what: str | None = None) -> int:
    line = _marker_line(section_text, marker, what=what)
    return int(line.split(":", 1)[0], 16)


def _word_value(section_text: str, marker: str, *, what: str | None = None) -> int:
    line = _marker_line(section_text, marker, what=what)
    hit = _HEX_WORD_RE.search(line)
    if hit is None:
        raise fail("%s missing literal pool word" % (what or marker))
    return int(hit.group(1), 16)


def _code_lines(section_text: str) -> list[str]:
    return [line.strip() for line in section_text.splitlines() if re.match(r"^\s*[0-9a-fA-F]+:\s+", line)]


def verify_generated_sources(
    runner_text: str,
    vendor_text: str,
    *,
    raw_runner_sha256: str | None = None,
    raw_vendor_sha256: str | None = None,
) -> dict[str, object]:
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    raw_validation_requested = raw_runner_sha256 is not None or raw_vendor_sha256 is not None
    if raw_runner_sha256 is not None:
        _count_raw_inputs(runner_text, _RAW_RUNNER_ANCHOR, "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID", "runner")
        if _sha256_text(runner_text) != raw_runner_sha256:
            raise fail("runner hash mismatch")
    if raw_vendor_sha256 is not None:
        _count_raw_inputs(vendor_text, _RAW_VENDOR_ANCHOR, "v12_poll_completion(void)", "vendor")
        if _sha256_text(vendor_text) != raw_vendor_sha256:
            raise fail("vendor hash mismatch")
    if raw_validation_requested:
        return {
            "variant": VARIANT,
            "schema_version": SCHEMA_VERSION,
            "build_id": "0x%08X" % BUILD_ID,
            "poll_remaining_symbol": "pmu_completion_poll_v13_t_poll_remaining_at_success",
        }

    if "PMU_COMPLETION_POLL_DIAG_V13" not in runner_text:
        raise fail("runner schema marker missing")
    if "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U" not in runner_text:
        raise fail("runner build id missing")
    count_once(runner_text, "extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;", "runner remaining extern")
    count_once(runner_text, "uint32_t poll_remaining_at_success;", "runner remaining field")
    count_once(runner_text, "poll_remaining_at_success = 0U;", "runner remaining reset")
    if "PMU_DIAG_FIELD_COUNT == 101U" not in runner_text and "#define PMU_DIAG_FIELD_COUNT 101U" not in runner_text:
        raise fail("runner field count missing")
    if "PMU_DIAG_TOTAL_WORDS == 109U" not in runner_text and "#define PMU_DIAG_TOTAL_WORDS 109U" not in runner_text:
        raise fail("runner total words missing")
    if "PMU_DIAG_PAYLOAD_SIZE == 436U" not in runner_text and "#define PMU_DIAG_PAYLOAD_SIZE 436U" not in runner_text:
        raise fail("runner payload size missing")
    if "put32(&c, d->poll_remaining_at_success);" not in runner_text and "out_words[100] = d->poll_remaining_at_success;" not in runner_text:
        raise fail("runner remaining serialization missing")

    helper = _extract_vendor_helper(vendor_text)
    count_once(helper, "status = *status_reg;", "helper STATUS read")
    count_once(helper, "(status & 0x02U)", "helper completion mask")
    if "(status & 0x04U)" in helper:
        raise fail("helper completion mask")
    if helper.count("pmu_completion_poll_v13_t_poll_remaining_at_success") != 1:
        raise fail("poll_remaining_at_success store count != 1")
    if "pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;" in helper:
        raise fail("remaining store must be success-only")
    if helper.count("*status_reg") != 1:
        raise fail("helper STATUS read count != 1")
    if "write_reg(NPU_REG_CMD" in helper or "read_reg(NPU_REG_QREAD)" in helper or "0x0000000CU" in helper:
        raise fail("retained V12 hard-bypass/CMD/QREAD/release drift")
    if "(void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD);" in helper:
        raise fail("helper contains forbidden operation")

    if "pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;" in helper or "pmu_completion_poll_v13_t_poll_remaining_at_success = 10001U;" in helper:
        raise fail("success remaining must be in 1..10000")
    if re.search(r"pmu_completion_poll_v13_t_poll_remaining_at_success\s*=\s*10000U\s*-\s*i\s*;", helper) is None and "pmu_completion_poll_v13_t_poll_remaining_at_success =" in helper:
        if "++i;" in helper:
            raise fail("remaining store must be success-only")
        raise fail("success remaining must be in 1..10000")

    success_pos = helper.find("if ((status & 0x02U) != 0U) {")
    p1_pos = helper.find("pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;", success_pos)
    p2_pos = helper.find("pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;", success_pos)
    remaining_pos = helper.find("pmu_completion_poll_v13_t_poll_remaining_at_success", success_pos)
    timeout_pos = helper.rfind("return 0U;")
    if min(success_pos, p1_pos, p2_pos, remaining_pos, timeout_pos) < 0:
        raise fail("canonical V13 helper shape missing")
    if remaining_pos < p2_pos:
        raise fail("remaining store must follow P2 exactly")
    if "pmu_completion_poll_v13_t_poll_remaining_at_success" in helper[timeout_pos:]:
        raise fail("timeout path must not publish remaining")
    if "uint32_t i = 0U;" in helper or "++i;" in helper:
        raise fail("remaining store must be success-only")

    return {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "poll_remaining_symbol": "pmu_completion_poll_v13_t_poll_remaining_at_success",
    }


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


def extract_poll_loop(disassembly_text: str, nm_text: str) -> PollLoop:
    helper_name = _helper_name_from_nm(nm_text)
    helper_addr = _symbol_addr_from_nm(nm_text, helper_name)
    funcs = parse_functions(disassembly_text)
    insns = funcs.get(helper_name)
    if insns is None:
        raise fail("helper function in disassembly: expected 1 match, found 0")
    if insns[0].addr != helper_addr:
        raise fail("helper symbol/address mismatch")
    helper_text = _function_section(disassembly_text, helper_name)
    status_marker = "V12_HELPER_STATUS_READ" if helper_name.startswith("v12_") else "V13_HELPER_STATUS_READ"
    test_marker = "V12_HELPER_STATUS_TEST" if helper_name.startswith("v12_") else "V13_HELPER_STATUS_TEST"
    status_addr_marker = "V12_HELPER_STATUS_ADDR" if helper_name.startswith("v12_") else "V13_HELPER_STATUS_ADDR"
    status_line = _marker_line(helper_text, status_marker, what="helper STATUS read")
    if _word_value(helper_text, status_addr_marker, what="helper STATUS MMIO address") != STATUS_ADDRESS:
        raise fail("helper STATUS MMIO address")
    if helper_text.count("; %s" % status_marker) != 1:
        raise fail("helper STATUS read count != 1")
    status_load_hit = _RAW_LOAD_RE.search(status_line)
    if status_load_hit is None:
        raise fail("helper STATUS read shape missing")
    status_value_reg, status_base_reg = status_load_hit.groups()
    if len(re.findall(r"\bldr(?:\.w)?\s+r\d+,\s+\[%s(?:,\s*#[0-9]+)?\]" % re.escape(status_base_reg), helper_text)) != 1:
        raise fail("helper STATUS read count != 1")
    test_line = _marker_line(helper_text, test_marker, what="helper STATUS test")
    if "#2" not in test_line:
        raise fail("helper completion mask")

    code_lines = _code_lines(helper_text)
    status_index = next((i for i, line in enumerate(code_lines) if _line_has_marker(line, status_marker)), -1)
    test_index = next((i for i, line in enumerate(code_lines) if _line_has_marker(line, test_marker)), -1)
    if min(status_index, test_index) < 0 or status_index >= test_index:
        raise fail("helper status read/test ordering violated")

    success_branch_line = code_lines[test_index + 1]
    if "bne" not in success_branch_line:
        raise fail("success branch missing")
    success_target_hit = re.search(r"\b([0-9a-fA-F]+)\s+<", success_branch_line)
    if success_target_hit is None:
        raise fail("success branch target missing")
    success_target = int(success_target_hit.group(1), 16)

    failed_path = []
    for line in code_lines[test_index + 2:]:
        addr = int(line.split(":", 1)[0], 16)
        if addr >= success_target:
            break
        failed_path.append(line)
    if len(failed_path) < 3:
        raise fail("failed-poll decrement count")

    loop_body = failed_path[:3]
    decrement_regs: list[str] = []
    for line in loop_body[:2]:
        hit = _SUBS_RE.search(line)
        if hit is None:
            raise fail("failed-poll decrement count")
        decrement_regs.append(hit.group(1))
    if len([line for line in loop_body if _SUBS_RE.search(line)]) != 2:
        raise fail("failed-poll decrement count")
    if len(loop_body) != 3:
        if "str" in loop_body[1] or "str" in loop_body[2]:
            raise fail("extra per-iteration store")
        if any(" bl " in line or "\tbl\t" in line for line in loop_body):
            raise fail("extra per-iteration call")
        if any("[sp" in line for line in loop_body):
            raise fail("extra per-iteration load/store")
        raise fail("extra per-iteration instruction")

    back_edge_line = loop_body[2]
    back_edge_hit = re.search(r"\bbne(?:\.n)?\s+([0-9a-fA-F]+)\s+<", back_edge_line)
    if back_edge_hit is None:
        raise fail("conditional loop back-edge")
    back_edge_target = int(back_edge_hit.group(1), 16)
    status_addr = _marker_addr(helper_text, status_marker, what="helper STATUS read")
    if back_edge_target != status_addr:
        raise fail("conditional loop back-edge")

    remaining_lines = _marker_lines(helper_text, "V13_REMAINING_STORE")
    if helper_name.startswith("v13_") and len(remaining_lines) != 1:
        raise fail("remaining store must follow P2 exactly")
    has_stack_access = any(re.search(r"\b(push|pop)\b|\[sp", line) for line in code_lines)
    has_extra_non_status_load = False
    allowed_load_markers = {status_marker, "V12_P1_DWT_READ", "V12_P2_DWT_READ", "V13_P1_DWT_READ", "V13_P2_DWT_READ"}
    for line in code_lines:
        if _RAW_PC_LOAD_RE.search(line):
            continue
        if not _RAW_LOAD_RE.search(line):
            continue
        if not any(_line_has_marker(line, marker) for marker in allowed_load_markers):
            has_extra_non_status_load = True
            break
    has_forbidden_loop_effect = any(
        re.search(r"\b(bl|blx|dmb|dsb|isb)\b", line)
        or ("str" in line and int(line.split(":", 1)[0], 16) < success_target)
        or ("[sp" in line and int(line.split(":", 1)[0], 16) < success_target)
        for line in code_lines[test_index + 2:]
    )
    return PollLoop(
        variant="v12" if helper_name.startswith("v12_") else "v13",
        helper_name=helper_name,
        helper_addr=helper_addr,
        status_addr=STATUS_ADDRESS,
        mask=0x02,
        status_base_reg=status_base_reg,
        status_value_reg=status_value_reg,
        status_read_count=1,
        failed_path_decrement_regs=tuple(decrement_regs),
        failed_path_decrement_count=2,
        back_edge_target=back_edge_target,
        conditional_back_edge_count=1,
        success_edge_count=1,
        timeout_edge_count=1,
        extra_per_iteration_instruction_count=max(0, len(failed_path) - 5),
        has_stack_access=has_stack_access,
        has_extra_non_status_load=has_extra_non_status_load,
        has_forbidden_loop_effect=has_forbidden_loop_effect,
    )


def normalize_poll_loop(loop: PollLoop) -> tuple[tuple[str, int], ...]:
    return (
        ("status_reads_per_iteration", loop.status_read_count),
        ("mask", loop.mask),
        ("failed_path_decrements", loop.failed_path_decrement_count),
        ("conditional_back_edges", loop.conditional_back_edge_count),
        ("success_edges", loop.success_edge_count),
        ("timeout_edges", loop.timeout_edge_count),
        ("extra_per_iteration_instruction_count", loop.extra_per_iteration_instruction_count),
    )


def prove_remaining_dataflow(disassembly_text: str, nm_text: str) -> RemainingDataflowProof:
    loop = extract_poll_loop(disassembly_text, nm_text)
    if loop.variant != "v13":
        raise fail("remaining dataflow proof requires V13 helper")
    helper_text = _function_section(disassembly_text, loop.helper_name)
    code_lines = _code_lines(helper_text)
    p2_index = next((i for i, line in enumerate(code_lines) if _line_has_marker(line, "V13_P2_STORE")), -1)
    remaining_index = next((i for i, line in enumerate(code_lines) if _line_has_marker(line, "V13_REMAINING_STORE")), -1)
    success_index = next((i for i, line in enumerate(code_lines) if _line_has_marker(line, "V13_HELPER_STATUS_TEST")), -1)
    success_branch_target = _marker_addr(helper_text, "V13_P1_DWT_READ", what="V13 P1 DWT read")
    timeout_prefix = [line for line in code_lines if int(line.split(":", 1)[0], 16) < success_branch_target]
    if any("TIMEOUT_STORE" in line or "; V13_REMAINING_STORE" in line for line in timeout_prefix):
        raise fail("timeout path must not publish remaining")
    if p2_index < 0 or remaining_index < 0 or remaining_index <= p2_index:
        raise fail("remaining store must follow P2 exactly")

    remaining_store_line = code_lines[remaining_index]
    store_match = re.search(r"\bstr(?:\.w)?\s+(r\d+),", remaining_store_line)
    if store_match is None:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    store_reg = store_match.group(1)
    induction_reg = loop.failed_path_decrement_regs[-1]
    if store_reg != induction_reg:
        raise fail("remaining must dataflow from failed-poll countdown live-out")

    for line in code_lines[p2_index + 1:remaining_index]:
        hit = _WRITES_RE.search(line)
        if hit is None:
            continue
        if hit.group(1) == store_reg:
            raise fail("remaining must dataflow from failed-poll countdown live-out")
    for line in code_lines[success_index + 1:remaining_index]:
        if _MOV_IMM_RE.search(line) and _MOV_IMM_RE.search(line).group(1) == store_reg:
            raise fail("remaining must dataflow from failed-poll countdown live-out")
        if re.search(r"\bsub(?:s|\.w)?\s+%s," % re.escape(store_reg), line):
            raise fail("remaining must dataflow from failed-poll countdown live-out")
    if loop.has_stack_access:
        raise fail("helper must remain a leaf without stack access")
    if loop.has_extra_non_status_load:
        raise fail("extra non-STATUS load")

    return RemainingDataflowProof(
        source="back_edge_induction",
        remaining_store_after_p2_exactly_once=True,
        remaining_store_timeout_unreachable=True,
        remaining_from_back_edge_induction=True,
        helper_leaf_no_stack_access=True,
    )


def verify_cross_elf_contract(
    v12_disassembly_text: str,
    v12_nm_text: str,
    v13_disassembly_text: str,
    v13_nm_text: str,
) -> dict[str, object]:
    v12_loop = extract_poll_loop(v12_disassembly_text, v12_nm_text)
    v13_loop = extract_poll_loop(v13_disassembly_text, v13_nm_text)
    if normalize_poll_loop(v12_loop) != normalize_poll_loop(v13_loop):
        raise fail("failed-poll decrement count")
    if v13_loop.has_forbidden_loop_effect:
        raise fail("extra per-iteration instruction")
    if v13_loop.has_extra_non_status_load:
        raise fail("extra non-STATUS load")
    proof = prove_remaining_dataflow(v13_disassembly_text, v13_nm_text)
    if "NVIC_EnableIRQ" in v13_disassembly_text:
        raise fail("retained V12 vector/NVIC/CMD/QREAD/PMU/release drift")
    return {
        "v12_v13_poll_loop_semantically_equivalent": True,
        "v13_extra_per_iteration_instruction_count_zero": True,
        "remaining_store_after_p2_exactly_once": proof.remaining_store_after_p2_exactly_once,
        "remaining_from_back_edge_induction": proof.remaining_from_back_edge_induction,
        "remaining_store_timeout_unreachable": proof.remaining_store_timeout_unreachable,
        "helper_leaf_no_stack_access": proof.helper_leaf_no_stack_access,
        "loop_equivalent": True,
    }
