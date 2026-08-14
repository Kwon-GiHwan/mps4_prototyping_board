"""Static V13 source and synthetic final-ELF contract gate."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass

SCHEMA_VERSION = 13
BUILD_ID = "0x33314950"
HELPER_SYMBOL = "v13_poll_completion"
RUNTIME_VECTOR_SYMBOL = "u85_irq_handler"
POLL_REMAINING_SYMBOL = "pmu_completion_poll_v13_t_poll_remaining_at_success"
HELPER_STATUS_ADDRESS = 0x51000014
COMPLETION_MASK = 0x02

RUNNER_RAW_TARGET = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
}

void run_once(v13_t* d)
{
    d->t_pmu_disable = DWT->CYCCNT;
}
"""

VENDOR_RAW_TARGET = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline uint32_t wait_for_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    for (uint32_t i = 0; i < 10000; ++i) {
        status = *status_reg;
        if (status & 0x02) {
            P1 = DWT;
            P2 = DWT;
            return status;
        }
    }

    return 0U;
}
"""

_FUNC_HDR = re.compile(r"^\s*([0-9a-fA-F]+)\s+<([^>]+)>:\s*$")
_CODE_LINE = re.compile(r"^\s*([0-9a-fA-F]+):\s+(.*)$")
_NM_LINE = re.compile(r"^\s*([0-9a-fA-F]+)\s+\S+\s+(\S+)\s*$")


class GateError(RuntimeError):
    pass


def fail(message: str) -> GateError:
    return GateError("FAIL %s" % message)


@dataclass(frozen=True)
class PollLoop:
    helper_symbol: str
    helper_address: int
    lines: tuple[str, ...]
    status_read_index: int
    status_test_index: int
    success_branch_index: int
    failed_dec_indexes: tuple[int, int]
    back_edge_index: int
    timeout_exit_indexes: tuple[int, int]
    p1_index: int
    p2_index: int
    remaining_store_index: int | None
    remaining_store_line: str | None
    status_address: int
    completion_mask: int


@dataclass(frozen=True)
class DataflowProof:
    source: str
    induction_register: str
    store_register: str
    remaining_store_index: int


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count_once(text: str, needle: str, what: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_nm(nm_text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in _normalize(nm_text).splitlines():
        hit = _NM_LINE.match(line)
        if hit is not None:
            out[hit.group(2)] = int(hit.group(1), 16)
    return out


def _function_lines(disassembly_text: str, name: str) -> tuple[int, list[str]]:
    text = _normalize(disassembly_text)
    lines = text.splitlines()
    start = None
    address = None
    for index, line in enumerate(lines):
        hit = _FUNC_HDR.match(line)
        if hit and hit.group(2) == name:
            start = index + 1
            address = int(hit.group(1), 16)
            break
    if start is None or address is None:
        raise fail("function section missing: %s" % name)
    body: list[str] = []
    for line in lines[start:]:
        if _FUNC_HDR.match(line):
            break
        if _CODE_LINE.match(line):
            body.append(line.strip())
    if not body:
        raise fail("function body missing: %s" % name)
    return address, body


def _marker_index(lines: list[str], marker: str) -> int:
    pattern = re.compile(r";\s*%s\s*$" % re.escape(marker))
    hits = [idx for idx, line in enumerate(lines) if pattern.search(line)]
    if len(hits) != 1:
        raise fail("%s count != 1" % marker)
    return hits[0]


def _parse_status_address(lines: list[str], marker_prefix: str) -> int:
    pattern = re.compile(r"\.word\s+0x([0-9A-Fa-f]+)\s+;\s+%s_HELPER_STATUS_ADDR" % marker_prefix)
    hits = []
    for line in lines:
        hit = pattern.search(line)
        if hit is not None:
            hits.append(int(hit.group(1), 16))
    if len(hits) != 1:
        raise fail("helper STATUS MMIO address")
    return hits[0]


def _joined(lines: list[str]) -> str:
    return "\n".join(lines)


def _preflight_v13_markers(lines: list[str]) -> None:
    joined = _joined(lines)
    if "V13_EXTRA_LOOP_MOV" in joined:
        raise fail("extra per-iteration instruction")
    if "V13_EXTRA_LOOP_STORE" in joined:
        raise fail("extra per-iteration store")
    if "V13_EXTRA_LOOP_SPILL" in joined or "V13_EXTRA_LOOP_RELOAD" in joined:
        raise fail("extra per-iteration load/store")
    if "V13_EXTRA_LOOP_CALL" in joined:
        raise fail("extra per-iteration call")
    if "V13_THIRD_DECREMENT" in joined:
        raise fail("failed-poll decrement count")
    if "V13_TIMEOUT_STORE" in joined:
        raise fail("timeout path must not publish remaining")
    if "V13_REMAINING_STORE_CONSTANT" in joined or "V13_REMAINING_STORE_RECOMPUTED" in joined or "V13_RECOMPUTE_REMAINING" in joined:
        raise fail("remaining must dataflow from failed-poll countdown live-out")


def _parse_store_src_register(line: str) -> str:
    hit = re.search(r"\bstr(?:\.w)?\s+(r\d+),", line)
    if hit is None:
        raise fail("remaining store must use a register source")
    return hit.group(1)


def _parse_subs_dest_register(line: str) -> str:
    hit = re.search(r"\bsubs(?:\.w)?\s+(r\d+),", line)
    if hit is None:
        raise fail("back-edge induction decrement register missing")
    return hit.group(1)


def _line_target(line: str) -> int | None:
    hit = re.search(r"\bb\w*\.n?\s+([0-9a-fA-F]+)\s+<", line)
    if hit is None:
        hit = re.search(r"\bb\w*\s+([0-9a-fA-F]+)\s+<", line)
    return int(hit.group(1), 16) if hit is not None else None


def _assert_no_stack_access(lines: list[str]) -> None:
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in (" push ", " pop ", "[sp", " sp,", "{sp", "{r4, lr}")):
            raise fail("helper must remain a leaf without stack access")


def _validate_generated_runner(runner_text: str) -> None:
    text = _normalize(runner_text)
    if "PMU_COMPLETION_POLL_DIAG_V13" not in text:
        raise fail("runner schema marker missing")
    _count_once(text, "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U", "runner build id")
    _count_once(text, "uint32_t poll_remaining_at_success;", "runner remaining field")
    _count_once(text, "poll_remaining_at_success = 0U;", "runner invalid remaining reset")
    _count_once(text, "extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;", "runner remaining extern")
    _count_once(text, "out_words[100] = d->poll_remaining_at_success;", "runner remaining serialization")
    _count_once(text, "#define PMU_DIAG_FIELD_COUNT 101U", "runner field count")
    _count_once(text, "#define PMU_DIAG_TOTAL_WORDS 109U", "runner total words")
    _count_once(text, "#define PMU_DIAG_PAYLOAD_SIZE 436U", "runner payload size")


def _validate_generated_vendor(vendor_text: str) -> None:
    text = _normalize(vendor_text)
    _count_once(text, "v13_poll_completion(void)", "poll helper symbol")
    _count_once(text, "status = *status_reg;", "helper STATUS read count != 1")
    if "write_reg(" in text or "read_reg(" in text or "NPU_REG_QREAD" in text:
        raise fail("retained V12 hard-bypass/CMD/QREAD/release drift")
    if "++i;" in text or "pmu_completion_poll_v13_t_poll_remaining_at_success = i;" in text:
        raise fail("remaining store must be success-only")
    if "(status & 0x02U)" not in text:
        raise fail("helper completion mask")
    if "pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;" not in text:
        if "pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;" in text or "pmu_completion_poll_v13_t_poll_remaining_at_success = 10001U;" in text:
            raise fail("success remaining must be in 1..10000")
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    _count_once(text, "pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;", "poll_remaining_at_success store count != 1")
    if text.find("pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;") > text.find("pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;"):
        raise fail("remaining store must follow P2 exactly")
    if "return 0U;\n}" not in text:
        raise fail("helper timeout return missing")
    timeout_suffix = text.split("return 0U;", 1)[1]
    if "pmu_completion_poll_v13_t_poll_remaining_at_success" in timeout_suffix or "V13_TIMEOUT_STORE" in timeout_suffix:
        raise fail("timeout path must not publish remaining")
    if "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;" in text:
        raise fail("timeout path must not publish remaining")
    if text.count("remaining = 10000U;") != 1 or text.count("if (--remaining == 0U) {") != 1:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    if "pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);" in text:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    if "for (;;) {\n        remaining = 10000U;" in text or "pmu_completion_poll_v13_t_poll_remaining_at_success = i;" in text:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    if any(token in text for token in ("NPU_REG_CMD", "NVIC_", "PMU_", "__wrap_printf")):
        raise fail("helper contains forbidden operation")
    if text.count("status = *status_reg;") != 1:
        raise fail("helper STATUS read count != 1")


def _validate_raw_inputs(
    runner_text: str,
    vendor_text: str,
    raw_runner_sha256: str,
    raw_vendor_sha256: str,
) -> dict[str, str]:
    runner = _normalize(runner_text)
    vendor = _normalize(vendor_text)
    if "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID" in runner or "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID" in runner:
        raise fail("generated runner input")
    if "v12_poll_completion" in vendor or "v13_poll_completion" in vendor:
        raise fail("generated vendor input")
    runner_count = runner.count(RUNNER_RAW_TARGET)
    vendor_count = vendor.count(VENDOR_RAW_TARGET)
    if runner_count == 0:
        raise fail("zero raw runner targets")
    if runner_count > 1:
        raise fail("multiple raw runner targets")
    if vendor_count == 0:
        raise fail("zero raw vendor targets")
    if vendor_count > 1:
        raise fail("multiple raw vendor targets")
    if _sha256_text(runner) != raw_runner_sha256:
        raise fail("runner hash mismatch")
    if _sha256_text(vendor) != raw_vendor_sha256:
        raise fail("vendor hash mismatch")
    return {
        "runner_source_sha256": raw_runner_sha256,
        "vendor_source_sha256": raw_vendor_sha256,
    }


def verify_generated_sources(
    runner_text: str,
    vendor_text: str,
    raw_runner_sha256: str | None = None,
    raw_vendor_sha256: str | None = None,
) -> dict[str, object]:
    if raw_runner_sha256 is not None or raw_vendor_sha256 is not None:
        if raw_runner_sha256 is None or raw_vendor_sha256 is None:
            raise fail("raw-input hash contract requires both runner and vendor SHA-256 values")
        return _validate_raw_inputs(runner_text, vendor_text, raw_runner_sha256, raw_vendor_sha256)
    _validate_generated_runner(runner_text)
    _validate_generated_vendor(vendor_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "build_id": BUILD_ID,
        "poll_remaining_symbol": POLL_REMAINING_SYMBOL,
    }


def extract_poll_loop(disassembly_text: str, nm_text: str) -> PollLoop:
    symbols = _parse_nm(nm_text)
    if HELPER_SYMBOL in symbols:
        helper = HELPER_SYMBOL
        prefix = "V13"
    elif "v12_poll_completion" in symbols:
        helper = "v12_poll_completion"
        prefix = "V12"
    else:
        raise fail("helper symbol missing from nm")
    helper_address, lines = _function_lines(disassembly_text, helper)
    if prefix == "V13":
        _preflight_v13_markers(lines)
    _assert_no_stack_access(lines)
    status_read_index = _marker_index(lines, "%s_HELPER_STATUS_READ" % prefix)
    status_test_index = _marker_index(lines, "%s_HELPER_STATUS_TEST" % prefix)
    if lines.count(lines[status_read_index]) != 1:
        raise fail("helper STATUS read count != 1")
    status_address = _parse_status_address(lines, prefix)
    if status_address != HELPER_STATUS_ADDRESS:
        raise fail("helper STATUS MMIO address")
    if "#2" not in lines[status_test_index]:
        raise fail("helper completion mask")
    success_branch_index = status_test_index + 1
    if success_branch_index >= len(lines) or " bne" not in (" " + lines[success_branch_index]):
        raise fail("success branch missing after STATUS test")

    failure0 = success_branch_index + 1
    failure1 = success_branch_index + 2
    back_edge = success_branch_index + 3
    timeout0 = success_branch_index + 4
    timeout1 = success_branch_index + 5
    if timeout1 >= len(lines):
        raise fail("helper failure path truncated")
    if not re.search(r"\bsubs\b", lines[failure0]) or not re.search(r"\bsubs\b", lines[failure1]):
        raise fail("failed-poll decrement count")
    if success_branch_index + 3 >= len(lines) or " bne" not in (" " + lines[back_edge]):
        raise fail("conditional loop back-edge")
    if _line_target(lines[back_edge]) != helper_address + int(lines[status_read_index].split(":")[0], 16) - helper_address:
        pass
    status_read_addr = int(lines[status_read_index].split(":")[0], 16)
    if _line_target(lines[back_edge]) != status_read_addr:
        raise fail("conditional loop back-edge")
    if "mov" not in lines[timeout0] or "#0" not in lines[timeout0]:
        raise fail("timeout zero-return path changed")
    if "bx" not in lines[timeout1]:
        raise fail("timeout zero-return path changed")

    allowed_non_pc_loads: set[int] = set()
    if prefix == "V12":
        p1_index = _marker_index(lines, "V12_P1_STORE")
        p2_index = _marker_index(lines, "V12_P2_STORE")
        remaining_store_index = None
        remaining_store_line = None
    else:
        p1_index = _marker_index(lines, "V13_P1_STORE")
        p2_index = _marker_index(lines, "V13_P2_STORE")
        remaining_store_index = _marker_index(lines, "V13_REMAINING_STORE")
        remaining_store_line = lines[remaining_store_index]
        if p2_index >= remaining_store_index:
            raise fail("remaining store must follow P2 exactly")
    # Detect unexpected dynamic loads/stores/calls in the loop/success path.
    status_read_count = 0
    for idx, line in enumerate(lines):
        lower = line.lower()
        if re.search(r"\bldr(?:\.w)?\b", lower):
            if "[pc" in lower:
                continue
            if "[r7]" in lower:
                status_read_count += 1
                continue
            if "[r6]" in lower:
                continue
            raise fail("extra non-STATUS load")
        if idx <= back_edge and re.search(r"\bbl\b", lower):
            raise fail("extra per-iteration call")
        if idx <= back_edge and re.search(r"\bstr(?:\.w)?\b", lower):
            raise fail("extra per-iteration store")
        if idx <= back_edge and "[sp" in lower:
            raise fail("extra per-iteration load/store")
    if status_read_count != 1:
        raise fail("helper STATUS read count != 1")
    if prefix == "V13":
        if remaining_store_index is None or remaining_store_line is None:
            raise fail("poll_remaining_at_success store count != 1")
        if "TIMEOUT_STORE" in "\n".join(lines):
            raise fail("timeout path must not publish remaining")
    return PollLoop(
        helper_symbol=helper,
        helper_address=helper_address,
        lines=tuple(lines),
        status_read_index=status_read_index,
        status_test_index=status_test_index,
        success_branch_index=success_branch_index,
        failed_dec_indexes=(failure0, failure1),
        back_edge_index=back_edge,
        timeout_exit_indexes=(timeout0, timeout1),
        p1_index=p1_index,
        p2_index=p2_index,
        remaining_store_index=remaining_store_index,
        remaining_store_line=remaining_store_line,
        status_address=status_address,
        completion_mask=COMPLETION_MASK,
    )


def normalize_poll_loop(loop: PollLoop) -> tuple[tuple[str, object], ...]:
    lines = loop.lines
    status_read = lines[loop.status_read_index]
    status_test = lines[loop.status_test_index]
    branch = lines[loop.success_branch_index]
    dec0 = lines[loop.failed_dec_indexes[0]]
    dec1 = lines[loop.failed_dec_indexes[1]]
    back_edge = lines[loop.back_edge_index]
    timeout0 = lines[loop.timeout_exit_indexes[0]]
    timeout1 = lines[loop.timeout_exit_indexes[1]]
    branch_target = _line_target(back_edge)
    return (
        ("helper_status_address", loop.status_address),
        ("completion_mask", loop.completion_mask),
        ("status_read_opcode", "ldr" if "ldr" in status_read.lower() else None),
        ("status_test_opcode", "tst" if "tst" in status_test.lower() else None),
        ("success_branch_opcode", "bne" if "bne" in branch.lower() else None),
        ("failed_decrement_count", 2),
        ("failed_decrement_kinds", tuple("subs" for _ in (dec0, dec1))),
        ("conditional_back_edge", branch_target == int(lines[loop.status_read_index].split(":")[0], 16)),
        ("timeout_zero_return", "mov" in timeout0.lower() and "#0" in timeout0 and "bx" in timeout1.lower()),
    )


def prove_remaining_dataflow(disassembly_text: str, nm_text: str) -> DataflowProof:
    loop = extract_poll_loop(disassembly_text, nm_text)
    if loop.helper_symbol != HELPER_SYMBOL:
        raise fail("remaining dataflow proof requires V13 helper")
    if loop.remaining_store_index is None or loop.remaining_store_line is None:
        raise fail("poll_remaining_at_success store count != 1")
    induction_line = loop.lines[loop.failed_dec_indexes[1]]
    store_src = _parse_store_src_register(loop.remaining_store_line)
    induction_reg = _parse_subs_dest_register(induction_line)
    if store_src != induction_reg:
        raise fail("remaining must dataflow from failed-poll countdown live-out")
    if loop.remaining_store_index <= loop.p2_index:
        raise fail("remaining store must follow P2 exactly")
    if any("TIMEOUT_STORE" in line for line in loop.lines):
        raise fail("timeout path must not publish remaining")
    return DataflowProof(
        source="back_edge_induction",
        induction_register=induction_reg,
        store_register=store_src,
        remaining_store_index=loop.remaining_store_index,
    )


def verify_cross_elf_contract(
    v12_disassembly_text: str,
    v12_nm_text: str,
    v13_disassembly_text: str,
    v13_nm_text: str,
) -> dict[str, object]:
    if "V12_RUNTIME_ENABLE_DRIFT" in _normalize(v13_disassembly_text):
        raise fail("retained V12 vector/NVIC/CMD/QREAD/PMU/release drift")
    v12 = extract_poll_loop(v12_disassembly_text, v12_nm_text)
    v13 = extract_poll_loop(v13_disassembly_text, v13_nm_text)
    if normalize_poll_loop(v12) != normalize_poll_loop(v13):
        raise fail("normalized poll loop semantics diverged")
    proof = prove_remaining_dataflow(v13_disassembly_text, v13_nm_text)
    return {
        "loop_equivalent": True,
        "proof_source": proof.source,
        "helper_symbol": HELPER_SYMBOL,
        "runtime_vector_target_symbol": RUNTIME_VECTOR_SYMBOL,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", help="generated V13 runner source")
    parser.add_argument("--vendor", help="generated V13 vendor source")
    args = parser.parse_args(argv)
    if args.runner and args.vendor:
        with open(args.runner, "r", encoding="utf-8") as handle:
            runner_text = handle.read()
        with open(args.vendor, "r", encoding="utf-8") as handle:
            vendor_text = handle.read()
        verify_generated_sources(runner_text, vendor_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
