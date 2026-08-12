"""Static gate for PMU_COMPLETION_POLL_DIAG_V12 generated sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

BUILD_ID = 0x32314950
SCHEMA_VERSION = 12
VARIANT = "PMU_COMPLETION_POLL_DIAG_V12"

EXPECTED_DYNAMIC_ADDRESS_KEYS = (
    "helper_address",
    "runtime_vector_target_address",
    "wait_call_target_address",
    "wait_result_branch_block_address",
    "success_entry_block_address",
    "timeout_entry_block_address",
    "merge_block_address",
)

EXPECTED_MANIFEST_KEYS = (
    "runtime_vector_install_site_address",
    "runtime_disable_site_address",
    "runtime_clear_pending_site_address",
    "runtime_enable_read_address",
    "runtime_pending_read_address",
    "runtime_active_read_address",
    "runtime_irq_triggered_read_address",
    "helper_status_read_address",
    "helper_status_test_address",
    "poll_helper_p0_address",
    "poll_helper_p1_address",
    "poll_helper_p2_address",
    "submit_read_address",
    "submit_write_address",
    "submit_t2_address",
    "wait_call_address",
    "wait_result_store_address",
    "success_history_mask_store_address",
    "success_cmd2_1_store_address",
    "success_qread_load_address",
    "success_cmd2_2_store_address",
    "timeout_report_address",
    "timeout_qread_load_address",
    "timeout_cmd2_store_address",
    "cmd0_store_address",
    "hprintf_callsite_address",
    "terminal_cmd0c_store_address",
    "final_pending_before_clear_address",
    "final_pending_after_clear_address",
    "final_active_after_cleanup_address",
    "final_irq_triggered_after_cleanup_address",
    "irq_status_read_address",
    "irq_trigger_test_address",
    "irq_history_mask_store_address",
    "irq_cmd2_store_address",
)

EXPECTED_BOOLEAN_KEYS = (
    "helper_one_direct_callsite",
    "helper_call_target_exact",
    "status_success_dataflow_exact",
    "history_mask_from_success_status",
    "success_cmd2_count_2",
    "timeout_cmd2_count_1",
    "nvic_enable_replaced",
    "irq_triggered_true_reachable_false",
    "runtime_vector_target_exact",
    "result_paths_distinct",
)

HEX32_RE = re.compile(r"^0x[0-9A-Fa-f]{4,8}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_MANIFEST_EXACT = {
    "variant": VARIANT,
    "schema_version": SCHEMA_VERSION,
    "build_id": "0x32314950",
    "qualification_mode": "Q1",
    "evidence_source": "arm_elf",
    "characterization_only": True,
    "not_a_performance_baseline": True,
    "not_a_latency_measurement": True,
    "generated_private_driver_diagnostic_only": True,
    "production_end_only_frozen": True,
    "diagnostic_only": True,
    "not_numerically_comparable_to_v11a": True,
    "not_latency": True,
    "not_t_npu": True,
    "not_production": True,
    "not_mlek": True,
    "runner_source_sha256": "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b",
    "vendor_source_sha256": "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf",
    "helper_symbol": "v12_poll_completion",
    "runtime_vector_target_symbol": "u85_irq_handler",
    "helper_status_register_address": "0x50004004",
    "helper_completion_mask_value": "0x00000002",
    "success_cmd2_write_value": "0x00000002",
    "timeout_cmd2_write_value": "0x00000002",
    "qread_verify_mask_value": "0x0000000F",
    "qread_verify_expected_value": "0x00000003",
    "runtime_vector_api_symbol": "NVIC_SetVector",
    "nvic_disable_symbol": "NVIC_DisableIRQ",
    "nvic_clear_pending_symbol": "NVIC_ClearPendingIRQ",
    "nvic_get_vector_symbol": "NVIC_GetVector",
    "nvic_get_enable_symbol": "NVIC_GetEnableIRQ",
    "nvic_get_pending_symbol": "NVIC_GetPendingIRQ",
    "nvic_get_active_symbol": "NVIC_GetActive",
}
MANIFEST_MARKER_KEYS = {
    "V12_RUNTIME_VECTOR_INSTALL": "runtime_vector_install_site_address",
    "V12_RUNTIME_DISABLE": "runtime_disable_site_address",
    "V12_RUNTIME_CLEAR_PENDING": "runtime_clear_pending_site_address",
    "V12_RUNTIME_ENABLE_READ": "runtime_enable_read_address",
    "V12_RUNTIME_PENDING_READ": "runtime_pending_read_address",
    "V12_RUNTIME_ACTIVE_READ": "runtime_active_read_address",
    "V12_RUNTIME_IRQ_TRIGGERED_READ": "runtime_irq_triggered_read_address",
    "V12_HELPER_STATUS_READ": "helper_status_read_address",
    "V12_HELPER_STATUS_TEST": "helper_status_test_address",
    "V12_P0": "poll_helper_p0_address",
    "V12_P1": "poll_helper_p1_address",
    "V12_P2": "poll_helper_p2_address",
    "V12_SUBMIT_READ": "submit_read_address",
    "V12_SUBMIT_WRITE": "submit_write_address",
    "V12_SUBMIT_T2": "submit_t2_address",
    "V12_WAIT_CALL": "wait_call_address",
    "V12_WAIT_RESULT_STORE": "wait_result_store_address",
    "V12_SUCCESS_HISTORY_STORE": "success_history_mask_store_address",
    "V12_SUCCESS_CMD2_1": "success_cmd2_1_store_address",
    "V12_SUCCESS_QREAD_READ": "success_qread_load_address",
    "V12_SUCCESS_CMD2_2": "success_cmd2_2_store_address",
    "V12_TIMEOUT_REPORT": "timeout_report_address",
    "V12_TIMEOUT_QREAD_READ": "timeout_qread_load_address",
    "V12_TIMEOUT_CMD2": "timeout_cmd2_store_address",
    "V12_CMD0": "cmd0_store_address",
    "V12_HPRINTF_SEAM": "hprintf_callsite_address",
    "V12_CMD0C": "terminal_cmd0c_store_address",
    "V12_FINAL_PENDING_BEFORE_CLEAR": "final_pending_before_clear_address",
    "V12_FINAL_PENDING_AFTER_CLEAR": "final_pending_after_clear_address",
    "V12_FINAL_ACTIVE_AFTER_CLEAR": "final_active_after_cleanup_address",
    "V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR": "final_irq_triggered_after_cleanup_address",
    "V12_ISR_STATUS_READ": "irq_status_read_address",
    "V12_ISR_TRIGGER_TEST": "irq_trigger_test_address",
    "V12_ISR_HISTORY_STORE": "irq_history_mask_store_address",
    "V12_ISR_CMD2": "irq_cmd2_store_address",
}

_FUNC_HDR = re.compile(r"^\s*([0-9a-fA-F]+)\s+<([^>]+)>:\s*$")
_LINE = re.compile(r"^\s*([0-9a-fA-F]+):\s*(.*)$")
_INLINE_MARKER = re.compile(r";\s*([A-Za-z0-9_]+)\s*$")
_TARGET = re.compile(r"\b([0-9a-fA-F]+)\s+<")


class GateError(RuntimeError):
    pass


def fail(message: str) -> GateError:
    return GateError("FAIL %s" % message)


def count_once(text: str, needle: str, what: str) -> int:
    count = text.count(needle)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return count


def _first_of(text: str, needles: tuple[str, ...], what: str) -> tuple[str, int]:
    for needle in needles:
        pos = text.find(needle)
        if pos >= 0:
            return needle, pos
    raise fail("%s not found" % what)


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _section(text: str, start: str, end: str) -> str:
    left = text.find(start)
    right = text.find(end, left)
    if left < 0 or right < 0 or not (left < right):
        raise fail("section %s -> %s not found" % (start, end))
    return text[left:right]


def _commands_section(vendor_text: str) -> str:
    start = vendor_text.find("void test_commands(void)")
    if start < 0:
        start = vendor_text.find("static int test_commands(")
    if start < 0:
        raise fail("test_commands entry not found")
    open_brace = vendor_text.find("{", start)
    if open_brace < 0:
        raise fail("test_commands opening brace not found")
    depth = 0
    for index in range(open_brace, len(vendor_text)):
        ch = vendor_text[index]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return vendor_text[start:index + 1]
    raise fail("test_commands closing brace not found")


def _function_section(disassembly_text: str, name: str) -> str:
    pattern = re.compile(
        r"(?ms)^[0-9a-fA-F]+\s+<%s>:\s*$\n(.*?)(?=^[0-9a-fA-F]+\s+<|\Z)" % re.escape(name)
    )
    hit = pattern.search(disassembly_text)
    if hit is None:
        raise fail("function section missing: %s" % name)
    return hit.group(1)


def _code_line_after_marker(section_text: str, marker: str) -> str:
    lines = section_text.splitlines()
    for index, line in enumerate(lines):
        if ("; %s" % marker) in line:
            for nxt in lines[index + 1:]:
                if re.match(r"^\s*[0-9a-fA-F]+:\s+", nxt):
                    return nxt.strip()
            break
    raise fail("disassembly code line missing after marker: %s" % marker)


def _function_code_lines(section_text: str) -> list[str]:
    return [
        line.strip()
        for line in section_text.splitlines()
        if re.match(r"^\s*[0-9a-fA-F]+:\s+", line)
    ]


def _parse_nm_symbols(nm_text: str) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for raw in nm_text.splitlines():
        parts = raw.split()
        if len(parts) == 3 and re.fullmatch(r"[0-9A-Fa-f]+", parts[0]):
            symbols[parts[2]] = int(parts[0], 16)
    return symbols


def _hex32(value: int) -> str:
    return "0x%08X" % value


def _same_hex32(lhs, rhs) -> bool:
    return (
        isinstance(lhs, str)
        and isinstance(rhs, str)
        and HEX32_RE.fullmatch(lhs) is not None
        and HEX32_RE.fullmatch(rhs) is not None
        and int(lhs, 16) == int(rhs, 16)
    )


@dataclass(frozen=True)
class AsmInsn:
    addr: int
    mnemonic: str
    text: str
    marker: str | None
    target: int | None
    kind: str


@dataclass(frozen=True)
class BasicBlock:
    start: int
    end: int
    insns: tuple[AsmInsn, ...]

    @property
    def terminator(self) -> AsmInsn:
        return self.insns[-1]


def _base_mnemonic(text: str) -> str:
    head = text.split()[0] if text.split() else ""
    return head.split(".")[0].lower()


def parse_functions(disassembly_text: str) -> dict[str, tuple[AsmInsn, ...]]:
    funcs: dict[str, list[AsmInsn]] = {}
    current: str | None = None
    pending_marker: str | None = None
    for raw in disassembly_text.splitlines():
        hdr = _FUNC_HDR.match(raw)
        if hdr:
            current = hdr.group(2)
            funcs[current] = []
            pending_marker = None
            continue
        line = _LINE.match(raw)
        if line is None or current is None:
            continue
        addr = int(line.group(1), 16)
        body = line.group(2).strip()
        if not body:
            continue
        marker_hit = _INLINE_MARKER.search(body)
        inline_marker = marker_hit.group(1) if marker_hit else None
        code = body[:marker_hit.start()].rstrip() if marker_hit else body
        if code.startswith(";"):
            pending_marker = inline_marker or code[1:].strip()
            continue
        marker = inline_marker or pending_marker
        pending_marker = None
        mnemonic = _base_mnemonic(code)
        target_hit = _TARGET.search(code)
        target = int(target_hit.group(1), 16) if target_hit else None
        if mnemonic == "b":
            kind = "branch_uncond"
        elif mnemonic in ("beq", "bne", "cbz", "cbnz"):
            kind = "branch_cond"
        elif mnemonic == "bl":
            kind = "call_direct"
        elif mnemonic == "blx":
            kind = "call_indirect"
        elif mnemonic == "bx" and code.endswith("lr"):
            kind = "return"
        elif mnemonic.startswith("it"):
            kind = "it"
        else:
            kind = "other"
        funcs[current].append(AsmInsn(addr=addr, mnemonic=mnemonic, text=code, marker=marker, target=target, kind=kind))
    if not funcs:
        raise fail("no disassembly functions parsed")
    return {name: tuple(insns) for name, insns in funcs.items()}


def split_basic_blocks(insns: tuple[AsmInsn, ...]) -> dict[int, BasicBlock]:
    if not insns:
        raise fail("split_basic_blocks requires non-empty instructions")
    starts = {insns[0].addr}
    all_addrs = {ins.addr for ins in insns}
    for index, ins in enumerate(insns):
        if ins.kind == "call_indirect":
            raise fail("indirect helper branch present")
        if ins.kind == "it":
            raise fail("IT-predicated CMD store")
        if ins.kind in ("branch_uncond", "branch_cond"):
            if ins.target is None:
                raise fail("unresolved direct branch at 0x%08x" % ins.addr)
            if ins.target not in all_addrs:
                raise fail("branch target 0x%08x outside function" % ins.target)
            starts.add(ins.target)
            if index + 1 >= len(insns):
                if ins.kind == "branch_cond":
                    raise fail("conditional branch at 0x%08x lacks fallthrough" % ins.addr)
            else:
                starts.add(insns[index + 1].addr)
        elif ins.kind == "return" and index + 1 < len(insns):
            starts.add(insns[index + 1].addr)
    ordered = sorted(starts)
    blocks: dict[int, BasicBlock] = {}
    for pos, start in enumerate(ordered):
        limit = ordered[pos + 1] if pos + 1 < len(ordered) else None
        block_insns = tuple(ins for ins in insns if ins.addr >= start and (limit is None or ins.addr < limit))
        if not block_insns:
            raise fail("empty basic block at 0x%08x" % start)
        blocks[start] = BasicBlock(start=start, end=block_insns[-1].addr, insns=block_insns)
    return blocks


def build_direct_edges(blocks: dict[int, BasicBlock]) -> dict[int, tuple[int, ...]]:
    starts = sorted(blocks)
    edges: dict[int, tuple[int, ...]] = {}
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        term = blocks[start].terminator
        if any(ins.marker == "V12_CMD0C" for ins in blocks[start].insns):
            edges[start] = ()
            continue
        if term.kind == "branch_uncond":
            if term.target not in blocks:
                raise fail("branch target 0x%08x is not a block start" % (term.target or 0))
            edges[start] = (term.target,)
        elif term.kind == "branch_cond":
            if next_start is None:
                raise fail("conditional block at 0x%08x lacks fallthrough block" % start)
            if term.target not in blocks:
                raise fail("conditional target 0x%08x is not a block start" % (term.target or 0))
            edges[start] = (term.target, next_start)
        elif term.kind == "return":
            edges[start] = ()
        else:
            edges[start] = (next_start,) if next_start is not None else ()
    return edges


def reachable_blocks(entry: int, edges: dict[int, tuple[int, ...]], allowed_back_edges: set[tuple[int, int]] | None = None) -> set[int]:
    allowed = allowed_back_edges or set()
    seen: set[int] = set()
    active: set[int] = set()

    def dfs(node: int) -> None:
        if node not in edges:
            raise fail("reachable block 0x%08x missing edge definition" % node)
        if node in active:
            raise fail("unexpected control-flow cycle re-enters 0x%08x" % node)
        if node in seen:
            return
        active.add(node)
        seen.add(node)
        if len(seen) > len(edges):
            raise fail("reachable_blocks exceeded block bound")
        for succ in edges[node]:
            if succ is None:
                continue
            if succ not in edges:
                raise fail("edge 0x%08x -> 0x%08x leaves graph" % (node, succ))
            if succ in active and (node, succ) not in allowed:
                raise fail("unexpected control-flow cycle 0x%08x -> 0x%08x" % (node, succ))
            if succ in active and (node, succ) in allowed:
                continue
            dfs(succ)
        active.remove(node)

    dfs(entry)
    return seen


def enumerate_result_paths(callsite, result_branch, merge, *, blocks, edges):
    del callsite
    branch_block = result_branch if isinstance(result_branch, BasicBlock) else blocks[result_branch]
    merge_block = merge if isinstance(merge, BasicBlock) else blocks[merge]
    succs = edges.get(branch_block.start, ())
    if len(succs) != 2:
        raise fail("result branch does not split into exactly two successors")
    if succs[0] == succs[1]:
        raise fail("result branch successors are not distinct")
    succ_a, succ_b = succs
    if any(ins.marker == "V12_SUCCESS_HISTORY_STORE" for ins in blocks[succ_a].insns):
        success_entry, timeout_entry = succ_a, succ_b
    elif any(ins.marker == "V12_SUCCESS_HISTORY_STORE" for ins in blocks[succ_b].insns):
        success_entry, timeout_entry = succ_b, succ_a
    else:
        raise fail("result branch successors do not expose distinct success block")

    def walk(start: int) -> set[int]:
        todo = [start]
        seen: set[int] = set()
        while todo:
            node = todo.pop()
            if node in seen:
                continue
            seen.add(node)
            if node == merge_block.start:
                continue
            todo.extend(edges.get(node, ()))
        return seen

    success_reach = walk(success_entry)
    timeout_reach = walk(timeout_entry)
    commons = sorted((success_reach & timeout_reach) | {merge_block.start})
    if commons[0] != merge_block.start:
        raise fail("success/timeout merge occurs before path-local QREAD verify")
    branch_marker = next(
        ins.addr for ins in branch_block.insns if ins.marker == "V12_WAIT_RESULT_STORE"
    )
    return {
        "branch_block": branch_marker,
        "success_entry": success_entry,
        "timeout_entry": timeout_entry,
        "merge_block": merge_block.start,
    }


def _block_for_marker(blocks: dict[int, BasicBlock], marker: str) -> BasicBlock:
    for block in blocks.values():
        for ins in block.insns:
            if ins.marker == marker:
                return block
    raise fail("marker %s is not attached to any basic block" % marker)


def _marker_addr(disassembly_text: str, marker: str) -> int:
    pattern = re.compile(r"^\s*([0-9a-fA-F]+):.*;\s*%s\s*$" % re.escape(marker), re.M)
    hit = pattern.search(disassembly_text)
    if hit is None:
        raise fail("disassembly marker missing: %s" % marker)
    return int(hit.group(1), 16)


def _marker_line_index(disassembly_text: str, marker: str) -> int:
    needle = "; %s" % marker
    for index, line in enumerate(disassembly_text.splitlines()):
        if needle in line:
            return index
    raise fail("disassembly marker missing: %s" % marker)


def _propagate_aliases(lines: list[str], aliases: set[str]) -> set[str]:
    current = set(aliases)
    mov_matchers = (
        re.compile(r"\bmov(?:s|\.w)?\s+(r\d+),\s+(r\d+)\b"),
        re.compile(r"\borr(?:s|\.w)?\s+(r\d+),\s+(r\d+),\s*#0\b"),
    )
    mov_imm_match = re.compile(r"\bmov(?:s|\.w)?\s+(r\d+),\s*#")
    clobber_match = re.compile(r"\b(?:ldr|ldrb|ldrh|add|adds|sub|subs|and|ands|eor|orr|bic|lsl|lsls|lsr|lsrs)(?:\.w)?\s+(r\d+),")
    for line in lines:
        handled = False
        for matcher in mov_matchers:
            hit = matcher.search(line)
            if hit is None:
                continue
            dst, src = hit.groups()
            if src in current:
                current.add(dst)
            elif dst in current:
                current.remove(dst)
            handled = True
            break
        if handled:
            continue
        mov_imm = mov_imm_match.search(line)
        if mov_imm is not None:
            dst = mov_imm.group(1)
            if dst in current:
                current.remove(dst)
            continue
        clobber = clobber_match.search(line)
        if clobber is not None:
            dst = clobber.group(1)
            if dst in current:
                current.remove(dst)
    return current


def _validate_helper(vendor_text: str) -> None:
    helper_start, _ = _first_of(
        vendor_text,
        (
            "uint32_t __attribute__((noinline)) v12_poll_completion(void)",
            "__attribute__((noinline))\nstatic uint32_t v12_poll_completion(void)",
            "static uint32_t v12_poll_completion(void)",
        ),
        "poll helper signature",
    )
    end_positions = [
        vendor_text.find(needle, vendor_text.find(helper_start))
        for needle in ("void test_u85(void)", "int test_u85(", "static int test_commands(")
    ]
    end_positions = [pos for pos in end_positions if pos >= 0]
    if not end_positions:
        raise fail("helper trailing function not found")
    helper = vendor_text[vendor_text.find(helper_start):min(end_positions)]
    count_once(helper, "v12_poll_completion(void)", "poll helper symbol")
    count_once(helper, "status = *status_reg;", "helper status load")
    count_once(helper, "if ((status & 0x02U) != 0U) {", "helper completion mask")
    count_once(helper, "pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;", "helper P0")
    count_once(helper, "pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;", "helper P1")
    count_once(helper, "pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;", "helper P2")
    count_once(helper, "return status;", "helper success return")
    count_once(helper, "return 0U;", "helper timeout return")
    count_once(helper, "for (uint32_t i = 0U; i < 10000U; ++i) {", "helper bounded poll loop")
    for forbidden in (
        "write_reg(",
        "read_reg(",
        "NVIC_",
        "printf(",
        "pmu_interval_v11a_",
        "pmu_interval_v10_",
        "pmu_qual_",
        "__asm",
        "dsb",
        "isb",
        "0x20000000U",
    ):
        if forbidden in helper:
            raise fail("helper contains forbidden operation %r" % forbidden)
    order = [
        "pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;",
        "status = *status_reg;",
        "if ((status & 0x02U) != 0U) {",
        "pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;",
        "pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;",
        "return status;",
    ]
    positions = [helper.find(needle) for needle in order]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise fail("helper ordering violated")


def _validate_runtime_path(vendor_text: str) -> None:
    if "v11a_u85_irq_entry_veneer" in vendor_text:
        raise fail("runtime vector still reaches V11 veneer")
    count_once(vendor_text, "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);", "runtime vector target")
    if "0xE000E100U" in vendor_text:
        raise fail("direct NVIC ISER enable write remains reachable")
    if "NVIC_EnableIRQ(NPU0_IRQn)" in vendor_text:
        raise fail("NVIC enable path remains reachable")
    if "pmu_interval_v11a_" in vendor_text:
        raise fail("V11 marker remains reachable in V12 source")
    runtime_start, _ = _first_of(vendor_text, ("void test_u85(void)", "int test_u85("), "runtime test_u85")
    start_index = vendor_text.find(runtime_start)
    end_positions = [
        vendor_text.find(needle, start_index + len(runtime_start))
        for needle in ("void test_commands(void)", "static int test_commands(")
    ]
    end_positions = [pos for pos in end_positions if pos >= 0]
    runtime = vendor_text[start_index:min(end_positions)] if end_positions else vendor_text[start_index:]
    order = [
        "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
        "irq_triggered = false;",
        "NVIC_DisableIRQ(NPU0_IRQn);",
        "NVIC_ClearPendingIRQ(NPU0_IRQn);",
        "pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);",
        "pmu_completion_poll_v12_t_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);",
        "pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);",
        "pmu_completion_poll_v12_t_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);",
        "pmu_completion_poll_v12_t_irq_triggered_before_submit = irq_triggered ? 1U : 0U;",
    ]
    positions = [runtime.find(needle) for needle in order]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise fail("runtime hard-bypass ordering violated")
    if "irq_triggered = true;" in runtime:
        raise fail("unexpected reachable irq_triggered=true count")


def _validate_success_timeout_paths(vendor_text: str) -> None:
    commands = _commands_section(vendor_text)
    if "else if ((status_at_success & 0x02U) != 0U)" in commands:
        raise fail("timeout path reaches success CFG")
    if "((void(*)(uint32_t, uint32_t))" in commands or "__asm volatile(\"itt" in commands:
        raise fail("indirect or IT-predicated CMD store")
    count_once(commands, "status_at_success = v12_poll_completion();", "wait helper call")
    _, poll_result_pos = _first_of(
        commands,
        (
            "pmu_completion_poll_v12_t_poll_result = (status_at_success & 0x02U) ? V12_POLL_SUCCESS : V12_POLL_TIMEOUT;",
            "pmu_completion_poll_v12_t_poll_result =\n\t      V12_POLL_TIMEOUT - ((status_at_success & 0x02U) >> 1);",
            "pmu_completion_poll_v12_t_poll_result =\n      V12_POLL_TIMEOUT - ((status_at_success & 0x02U) >> 1);",
        ),
        "poll result store",
    )
    success_head = "if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {"
    success_start = commands.find(success_head, poll_result_pos)
    if success_start < 0:
        raise fail("success poll_result branch missing")
    merge_start = commands.find("v12_common_cleanup:", success_start)
    if merge_start < 0:
        raise fail("common cleanup label missing")
    else_pos = commands.find("} else {", success_start)
    if else_pos >= 0 and else_pos < merge_start:
        success = commands[success_start:else_pos]
        timeout = commands[else_pos:merge_start]
    else:
        goto_pos = commands.find("goto v12_common_cleanup;", success_start)
        if goto_pos < 0:
            raise fail("success path does not terminate before cleanup merge")
        success = commands[success_start:goto_pos + len("goto v12_common_cleanup;")]
        timeout = commands[goto_pos + len("goto v12_common_cleanup;"):merge_start]
    if success.count("write_reg(NPU_REG_CMD, 0x00000002);") != 2:
        raise fail("success path CMD=2 count != 2")
    if timeout.count("write_reg(NPU_REG_CMD, 0x00000002);") != 1:
        raise fail("timeout path CMD=2 count != 1")
    success_head_pos = success.find("if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {")
    status_store_pos = success.find("pmu_completion_poll_v12_t_poll_status_at_success = status_at_success;")
    history_store_any = success.find("irq_history_mask =")
    if history_store_any >= 0 and not _has_any(
        success,
        (
            "irq_history_mask = status_at_success >> 16;",
            "irq_history_mask = (uint16_t)(status_at_success >> 16);",
        ),
    ):
        raise fail("history mask lost single-source status dataflow")
    history_store_pos = _first_of(
        success,
        (
            "irq_history_mask = status_at_success >> 16;",
            "irq_history_mask = (uint16_t)(status_at_success >> 16);",
        ),
        "success history mask store",
    )[1]
    first_cmd2_pos = success.find("write_reg(NPU_REG_CMD, 0x00000002);")
    qread_pos = success.find("read_val = read_reg(NPU_REG_QREAD);")
    second_cmd2_pos = success.find("write_reg(NPU_REG_CMD, 0x00000002);", first_cmd2_pos + 1)
    if min(success_head_pos, status_store_pos, history_store_pos, first_cmd2_pos, qread_pos, second_cmd2_pos) < 0:
        raise fail("success path ordering violated")
    if not (
        success_head_pos < first_cmd2_pos
        and status_store_pos < first_cmd2_pos
        and history_store_pos < first_cmd2_pos
        and first_cmd2_pos < qread_pos < second_cmd2_pos
    ):
        raise fail("success path ordering violated")
    timeout_order = [
        "irq_never_triggered = true;",
        "read_reg(NPU_REG_STATUS)",
        "read_val = read_reg(NPU_REG_QREAD);",
        "write_reg(NPU_REG_CMD, 0x00000002);",
    ]
    timeout_positions = [timeout.find(needle) for needle in timeout_order]
    if any(pos < 0 for pos in timeout_positions) or timeout_positions != sorted(timeout_positions):
        raise fail("timeout path ordering violated")
    if "status_at_success = read_reg(NPU_REG_STATUS);" in commands:
        raise fail("status_at_success comes from a reread")
    if "irq_history_mask = 0xABCDU;" in commands:
        raise fail("history mask lost single-source status dataflow")
    if "irq_history_mask =" in success and not _has_any(
        success,
        (
            "irq_history_mask = status_at_success >> 16;",
            "irq_history_mask = (uint16_t)(status_at_success >> 16);",
        ),
    ):
        raise fail("history mask lost single-source status dataflow")
    synthetic_success_verify = re.search(
        r"if\s*\(\(read_val\s*&\s*0x0FU\)\s*==\s*0x03U\)\s*\{\s*pmu_completion_poll_v12_t_success_qread_verified\s*=\s*1U;\s*\}",
        success,
        re.S,
    )
    real_success_verify = (
        "if(read_val == u32CmdQueueSize)" in success
        and "ERROR: Read mismatch at address: NPU_REG_QREAD" in success
        and "ret_code = 1;" in success
    )
    if not (synthetic_success_verify or real_success_verify):
        raise fail("success qread verify body missing")
    if not (
        ("pmu_completion_poll_v12_t_timeout_qread_verified = 1U;" in timeout)
        or ("if(read_val == u32CmdQueueSize)" in timeout)
    ):
        raise fail("timeout qread verify body missing")
    if "irq_triggered = true;" in commands:
        raise fail("measured path reintroduces irq_triggered=true")
    cleanup_order = [
        ("v12_common_cleanup:",),
        (
            "pmu_completion_poll_v12_t_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);",
            "/* V12_FINAL_PENDING_BEFORE_CLEAR */",
        ),
        (
            "pmu_completion_poll_v12_t_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);",
            "/* V12_FINAL_PENDING_AFTER_CLEAR */",
        ),
        (
            "pmu_completion_poll_v12_t_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);",
            "/* V12_FINAL_ACTIVE_AFTER_CLEAR */",
        ),
        (
            "pmu_completion_poll_v12_t_irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;",
            "/* V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR */",
        ),
        (
            "write_reg(NPU_REG_CMD, 0x00000000);",
            "/* V12_CMD0 */",
        ),
        (
            "printf(\"Testing CPM signals\\n\");",
            "/* V12_HPRINTF_SEAM */",
            "printf(\"V12: completed\\n\");",
        ),
        (
            "write_reg(NPU_REG_CMD, 0x0000000C);",
            "write_reg(NPU_REG_CMD, 0x0000000CU);",
            "/* V12_CMD0C */",
        ),
    ]
    cleanup_positions = []
    for choices in cleanup_order:
        _, pos = _first_of(commands, choices, "cleanup ordering token")
        cleanup_positions.append(pos)
    if cleanup_positions != sorted(cleanup_positions):
        raise fail("cleanup ordering violated")


def verify_generated_sources(runner_text: str, vendor_text: str) -> dict:
    counts = {}
    if "PMU_COMPLETION_POLL_DIAG_V12" not in runner_text:
        raise fail("runner schema marker missing")
    count_once(runner_text, "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U", "runner build id")
    if all(
        needle not in runner_text
        for needle in (
            "pmu_completion_poll_v12_t_poll_result",
            "uint32_t poll_result;",
            "d->poll_result",
        )
    ):
        raise fail("runner V12 poll_result field missing")
    if ("PMU_QUAL_SCHEMA_V12" not in runner_text) and ("PMU_COMPLETION_POLL_DIAG_V12" not in runner_text):
        raise fail("runner V12 cleanup field missing")
    counts["PMU_COMPLETION_POLL_V12_HELPER"] = count_once(
        vendor_text,
        "v12_poll_completion(void)",
        "poll helper symbol",
    )
    _validate_helper(vendor_text)
    _validate_runtime_path(vendor_text)
    _validate_success_timeout_paths(vendor_text)
    if not _has_any(vendor_text, ("void u85_irq_handler(void)", "void u85_irq_handler()")):
        raise fail("stock handler missing")
    if not _has_any(vendor_text, ("/* V12_ISR_STATUS_READ */", "status_register = read_reg(NPU_REG_STATUS);")):
        raise fail("ISR status read marker: expected 1 match, found 0")
    if not _has_any(vendor_text, ("/* V12_ISR_TRIGGER_TEST */", "if ((status_register & 0x02))", "if ((status_register & 0x02U))")):
        raise fail("ISR trigger test marker: expected 1 match, found 0")
    if not _has_any(vendor_text, ("/* V12_ISR_HISTORY_STORE */", "irq_history_mask = status_register >> 16;", "irq_history_mask = (uint16_t)(status_register >> 16);")):
        raise fail("ISR history marker: expected 1 match, found 0")
    if not _has_any(vendor_text, ("/* V12_ISR_CMD2 */", "write_reg(NPU_REG_CMD, 0x00000002);", "write_reg(NPU_REG_CMD, 2);")):
        raise fail("ISR cmd2 marker: expected 1 match, found 0")
    return counts


def verify_callsite_trace(runner_text: str, vendor_text: str, disassembly_text: str, nm_text: str) -> dict:
    if "pmu_interval_v11a_" in disassembly_text or "v11a_u85_irq_entry_veneer" in disassembly_text:
        raise fail("V11 marker remains reachable")
    count_once(nm_text, " T v12_poll_completion", "helper symbol in nm")
    count_once(nm_text, " T u85_irq_handler", "stock handler symbol in nm")
    count_once(disassembly_text, "<v12_poll_completion>:", "helper function in disassembly")
    count_once(disassembly_text, "<test_commands>:", "caller function in disassembly")

    funcs = parse_functions(disassembly_text)
    nm_symbols = _parse_nm_symbols(nm_text)
    for symbol in (
        "NVIC_SetVector",
        "NVIC_DisableIRQ",
        "NVIC_ClearPendingIRQ",
        "NVIC_GetVector",
        "NVIC_GetEnableIRQ",
        "NVIC_GetPendingIRQ",
        "NVIC_GetActive",
        "u85_irq_handler",
    ):
        if symbol not in nm_symbols:
            raise fail("missing symbol in nm: %s" % symbol)
    helper_insns = funcs.get("v12_poll_completion")
    caller_insns = funcs.get("test_commands")
    runtime_insns = funcs.get("test_u85")
    if helper_insns is None:
        raise fail("helper function in disassembly: expected 1 match, found 0")
    if caller_insns is None:
        raise fail("caller function <test_commands> missing from disassembly")
    if runtime_insns is None:
        raise fail("runtime function <test_u85> missing from disassembly")
    helper_addr = nm_symbols.get("v12_poll_completion")
    if helper_addr != helper_insns[0].addr:
        raise fail("helper symbol/address mismatch")
    stock_handler_addr = nm_symbols["u85_irq_handler"]

    helper_blocks = split_basic_blocks(helper_insns)
    helper_edges = build_direct_edges(helper_blocks)
    helper_entry = min(helper_blocks)
    p0_addr = _marker_addr(disassembly_text, "V12_P0")
    p1_addr = _marker_addr(disassembly_text, "V12_P1")
    p2_addr = _marker_addr(disassembly_text, "V12_P2")
    p1_line = _marker_line_index(disassembly_text, "V12_P1")
    p2_line = _marker_line_index(disassembly_text, "V12_P2")
    if not (p0_addr < p1_addr < p2_addr) or not (p1_line < p2_line):
        raise fail("P1/P2 modular-order identity violated")
    status_read_block = _block_for_marker(helper_blocks, "V12_HELPER_STATUS_READ")
    status_test_block = _block_for_marker(helper_blocks, "V12_HELPER_STATUS_TEST")
    p1_block = _block_for_marker(helper_blocks, "V12_P1")
    p2_block = _block_for_marker(helper_blocks, "V12_P2")
    if helper_edges.get(p2_block.start, ()) != ():
        raise fail("unexpected post-P1 cycle")
    helper_seen = reachable_blocks(helper_entry, helper_edges, {(status_test_block.start, status_read_block.start)})
    if helper_seen != set(helper_blocks):
        raise fail("helper reachability does not cover all helper blocks")
    if helper_edges.get(status_test_block.start) != (status_read_block.start, p1_block.start):
        raise fail("helper completion loop shape violated")

    caller_blocks = split_basic_blocks(caller_insns)
    caller_edges = build_direct_edges(caller_blocks)
    runtime_blocks = split_basic_blocks(runtime_insns)
    runtime_edges = build_direct_edges(runtime_blocks)
    wait_call = _block_for_marker(caller_blocks, "V12_WAIT_CALL")
    result_branch = _block_for_marker(caller_blocks, "V12_WAIT_RESULT_STORE")
    merge = _block_for_marker(caller_blocks, "V12_FINAL_PENDING_BEFORE_CLEAR")
    paths = enumerate_result_paths(wait_call, result_branch, merge, blocks=caller_blocks, edges=caller_edges)
    reachable_blocks(
        min(caller_blocks),
        caller_edges,
        {(paths["timeout_entry"], paths["merge_block"])},
    )
    reachable_blocks(min(runtime_blocks), runtime_edges)

    if "blx\tr3" in disassembly_text:
        raise fail("indirect helper branch present")
    helper_calls = [ins for ins in wait_call.insns if ins.kind == "call_direct"]
    helper_call_count = len(helper_calls)
    if helper_call_count != 1:
        raise fail("helper direct callsite count != 1")
    if helper_calls[0].target != helper_addr:
        raise fail("helper direct call target mismatch")
    runtime_text = _function_section(disassembly_text, "test_u85")
    reachable_text = "\n".join((runtime_text, _function_section(disassembly_text, "v12_poll_completion"), _function_section(disassembly_text, "test_commands")))
    if "NVIC_EnableIRQ" in reachable_text:
        raise fail("NVIC enable path remains reachable")
    if "0xE000E100" in reachable_text or "e000e100" in reachable_text.lower():
        raise fail("direct NVIC ISER enable write remains reachable")
    runtime_vector_value_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_VECTOR_VALUE")
    runtime_vector_install_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_VECTOR_INSTALL")
    runtime_disable_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_DISABLE")
    runtime_clear_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_CLEAR_PENDING")
    runtime_vector_load_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_VECTOR_LOAD")
    runtime_enable_read_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_ENABLE_READ")
    runtime_pending_read_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_PENDING_READ")
    runtime_active_read_line = _code_line_after_marker(runtime_text, "V12_RUNTIME_ACTIVE_READ")
    if "<u85_irq_handler>" not in runtime_vector_value_line or ("%04x" % stock_handler_addr) not in runtime_vector_value_line.lower():
        raise fail("runtime vector target mismatch")
    if "<NVIC_SetVector>" not in runtime_vector_install_line or _marker_addr(disassembly_text, "V12_RUNTIME_VECTOR_VALUE") >= _marker_addr(disassembly_text, "V12_RUNTIME_VECTOR_INSTALL"):
        raise fail("runtime vector install proof missing")
    if "<NVIC_DisableIRQ>" not in runtime_disable_line:
        raise fail("runtime disable proof missing")
    if "<NVIC_ClearPendingIRQ>" not in runtime_clear_line:
        raise fail("runtime clear-pending proof missing")
    if "<NVIC_GetVector>" not in runtime_vector_load_line:
        raise fail("runtime GetVector proof missing")
    if "<NVIC_GetEnableIRQ>" not in runtime_enable_read_line:
        raise fail("runtime GetEnable proof missing")
    if "<NVIC_GetPendingIRQ>" not in runtime_pending_read_line:
        raise fail("runtime GetPending proof missing")
    if "<NVIC_GetActive>" not in runtime_active_read_line:
        raise fail("runtime GetActive proof missing")
    if _marker_addr(disassembly_text, "V12_P0") >= _marker_addr(disassembly_text, "V12_HELPER_STATUS_READ"):
        raise fail("P0 must precede helper status read")
    if _marker_addr(disassembly_text, "V12_HELPER_STATUS_READ") >= _marker_addr(disassembly_text, "V12_HELPER_STATUS_TEST"):
        raise fail("helper status read/test ordering violated")
    if _marker_addr(disassembly_text, "V12_HELPER_STATUS_TEST") >= _marker_addr(disassembly_text, "V12_P1"):
        raise fail("P1 must occur after completion test")
    if _marker_addr(disassembly_text, "V12_SUCCESS_CMD2_1") >= _marker_addr(disassembly_text, "V12_SUCCESS_QREAD_READ"):
        raise fail("success CMD2 #1 must precede QREAD")
    if _marker_addr(disassembly_text, "V12_SUCCESS_QREAD_READ") >= _marker_addr(disassembly_text, "V12_SUCCESS_CMD2_2"):
        raise fail("success CMD2 #2 must follow QREAD")
    if _marker_addr(disassembly_text, "V12_FINAL_PENDING_BEFORE_CLEAR") >= _marker_addr(disassembly_text, "V12_CMD0"):
        raise fail("cleanup must precede CMD0")
    if _marker_addr(disassembly_text, "V12_FINAL_PENDING_BEFORE_CLEAR") >= _marker_addr(disassembly_text, "V12_FINAL_PENDING_AFTER_CLEAR"):
        raise fail("final pending clear ordering violated")
    if _marker_addr(disassembly_text, "V12_CMD0") >= _marker_addr(disassembly_text, "V12_HPRINTF_SEAM"):
        raise fail("CMD0/HPRINTF ordering violated")
    if _marker_addr(disassembly_text, "V12_HPRINTF_SEAM") >= _marker_addr(disassembly_text, "V12_CMD0C"):
        raise fail("HPRINTF/CMD0xC ordering violated")

    helper_text = _function_section(disassembly_text, "v12_poll_completion")
    caller_text = _function_section(disassembly_text, "test_commands")
    final_pending_after_line = _code_line_after_marker(caller_text, "V12_FINAL_PENDING_AFTER_CLEAR")
    if "<NVIC_ClearPendingIRQ>" not in final_pending_after_line:
        raise fail("final clear-pending proof missing")
    helper_status_line = _code_line_after_marker(helper_text, "V12_HELPER_STATUS_READ")
    helper_test_line = _code_line_after_marker(helper_text, "V12_HELPER_STATUS_TEST")
    result_store_line = _code_line_after_marker(caller_text, "V12_WAIT_RESULT_STORE")
    success_history_line = _code_line_after_marker(caller_text, "V12_SUCCESS_HISTORY_STORE")
    status_store_match = re.search(r"\bstr(?:\.w)?\s+(r\d+),", success_history_line)
    helper_load_match = re.search(r"\bldr(?:\.w)?\s+(r\d+),.*0x50004004", helper_status_line)
    helper_test_match = re.search(r"\btst(?:\.w)?\s+(r\d+),\s*#2", helper_test_line)
    shift_match = re.search(r"\blsrs(?:\.w)?\s+(r\d+),\s+(r\d+),\s*#16", caller_text)
    if not all((helper_load_match, helper_test_match, status_store_match, shift_match)):
        raise fail("status success dataflow proof missing")
    helper_reg = helper_load_match.group(1)
    if helper_test_match.group(1) != helper_reg:
        raise fail("status success dataflow violated")
    helper_lines = _function_code_lines(helper_text)
    helper_load_index = next((i for i, line in enumerate(helper_lines) if "0x50004004" in line), -1)
    helper_return_index = next((i for i, line in enumerate(helper_lines) if re.search(r"\bbx\s+lr\b", line)), -1)
    caller_lines = _function_code_lines(caller_text)
    result_store_index = next((i for i, line in enumerate(caller_lines) if "; V12_WAIT_RESULT_STORE" in line), -1)
    history_index = next((i for i, line in enumerate(caller_lines) if re.search(r"\blsrs(?:\.w)?\s+(r\d+),\s+(r\d+),\s*#16", line)), -1)
    if min(helper_load_index, helper_return_index, result_store_index, history_index) < 0:
        raise fail("status success dataflow proof missing")
    helper_aliases = _propagate_aliases(helper_lines[helper_load_index + 1:helper_return_index], {helper_reg})
    if "r0" not in helper_aliases:
        raise fail("status success dataflow violated")
    result_aliases = _propagate_aliases(caller_lines[result_store_index:history_index], {"r0"})
    shift_src = shift_match.group(2)
    if shift_src not in result_aliases:
        raise fail("status success dataflow violated")
    if status_store_match.group(1) not in result_aliases:
        raise fail("status success dataflow violated")
    if "0x50004004" in caller_text:
        raise fail("status success dataflow violated")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "build_id": _hex32(BUILD_ID),
        "runner_source_sha256": EXPECTED_MANIFEST_EXACT["runner_source_sha256"],
        "vendor_source_sha256": EXPECTED_MANIFEST_EXACT["vendor_source_sha256"],
        "helper_symbol": "v12_poll_completion",
        "helper_address": _hex32(helper_addr),
        "runtime_vector_target_symbol": "u85_irq_handler",
        "runtime_vector_target_address": _hex32(stock_handler_addr),
        "wait_call_target_address": _hex32(helper_calls[0].target),
        "wait_result_branch_block_address": _hex32(paths["branch_block"]),
        "success_entry_block_address": _hex32(paths["success_entry"]),
        "timeout_entry_block_address": _hex32(paths["timeout_entry"]),
        "merge_block_address": _hex32(paths["merge_block"]),
        "helper_status_register_address": "0x50004004",
        "helper_completion_mask_value": "0x00000002",
        "success_cmd2_write_value": "0x00000002",
        "timeout_cmd2_write_value": "0x00000002",
        "qread_verify_mask_value": "0x0000000F",
        "qread_verify_expected_value": "0x00000003",
        "runtime_vector_api_symbol": "NVIC_SetVector",
        "nvic_disable_symbol": "NVIC_DisableIRQ",
        "nvic_clear_pending_symbol": "NVIC_ClearPendingIRQ",
        "nvic_get_vector_symbol": "NVIC_GetVector",
        "nvic_get_enable_symbol": "NVIC_GetEnableIRQ",
        "nvic_get_pending_symbol": "NVIC_GetPendingIRQ",
        "nvic_get_active_symbol": "NVIC_GetActive",
        "helper_one_direct_callsite": True,
        "helper_call_target_exact": True,
        "status_success_dataflow_exact": True,
        "history_mask_from_success_status": True,
        "success_cmd2_count_2": True,
        "timeout_cmd2_count_1": True,
        "nvic_enable_replaced": True,
        "irq_triggered_true_reachable_false": True,
        "runtime_vector_target_exact": True,
        "result_paths_distinct": True,
        "result_paths": paths,
    }
    for marker, key in MANIFEST_MARKER_KEYS.items():
        evidence[key] = _hex32(_marker_addr(disassembly_text, marker))
    return evidence


def validate_artifact_against_evidence(manifest_json: str, evidence: dict) -> dict:
    doc = validate_artifact_contract(manifest_json)
    for key, expected in evidence.items():
        if key == "result_paths":
            continue
        actual = doc.get(key)
        if key in doc and actual != expected and not _same_hex32(actual, expected):
            raise fail("%s mismatch" % key)
    return doc


def validate_artifact_contract(
    manifest_json: str,
    evidence: dict | None = None,
    *,
    allow_synthetic: bool = False,
) -> dict:
    doc = json.loads(manifest_json)
    evidence_source = doc.get("evidence_source")
    if evidence_source not in ("arm_elf", "synthetic_fixture"):
        raise fail("evidence_source mismatch")
    if evidence_source == "synthetic_fixture" and not allow_synthetic:
        raise fail("synthetic evidence rejected without explicit allow_synthetic")
    for key, expected in EXPECTED_MANIFEST_EXACT.items():
        if key == "evidence_source":
            if evidence_source == "arm_elf" and doc.get(key) != expected:
                raise fail("%s mismatch" % key)
            if evidence_source == "synthetic_fixture" and doc.get(key) != "synthetic_fixture":
                raise fail("%s mismatch" % key)
            continue
        if doc.get(key) != expected:
            raise fail("%s mismatch" % key)
    for key in ("runner_source_sha256", "vendor_source_sha256", "manifest_sha256", "artifact_bundle_sha256", "parser_sha256"):
        value = doc.get(key)
        if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
            raise fail("%s malformed" % key)
    if not isinstance(doc.get("expected_return_address"), int) or doc["expected_return_address"] <= 0:
        raise fail("expected_return_address malformed")
    if doc["expected_return_address"] != int(doc["hprintf_callsite_address"], 16) + 4:
        raise fail("expected_return_address mismatch")
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise fail("artifact_sha256 malformed")
    for key in ("APP.BIN", "VECTORS.BIN", "DDR.BIN"):
        value = artifacts.get(key)
        if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
            raise fail("artifact_sha256 malformed: %s" % key)
    build_evidence = doc.get("build_evidence_sha256")
    if not isinstance(build_evidence, dict):
        raise fail("build_evidence_sha256 malformed")
    required_build_evidence = {
        "generated_runner.c",
        "generated_vendor_u85.c",
        "runner_pmu_completion_poll_v12.map",
        "checker_disassembly.txt",
        "checker_nm.txt",
    }
    if evidence_source == "arm_elf":
        required_build_evidence.add("runner_pmu_completion_poll_v12.elf")
    for key in required_build_evidence:
        value = build_evidence.get(key)
        if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
            raise fail("build_evidence_sha256 malformed: %s" % key)
    for key in EXPECTED_DYNAMIC_ADDRESS_KEYS:
        value = doc.get(key)
        if not isinstance(value, str) or HEX32_RE.fullmatch(value) is None:
            raise fail("manifest key missing or not address-like: %s" % key)
    for key in EXPECTED_MANIFEST_KEYS:
        value = doc.get(key)
        if not isinstance(value, str) or HEX32_RE.fullmatch(value) is None:
            raise fail("manifest key missing or not address-like: %s" % key)
    for key in EXPECTED_BOOLEAN_KEYS:
        if doc.get(key) is not True:
            raise fail("manifest boolean missing or false: %s" % key)
    if evidence is not None:
        for key in tuple(EXPECTED_MANIFEST_EXACT.keys()) + EXPECTED_DYNAMIC_ADDRESS_KEYS + EXPECTED_MANIFEST_KEYS + EXPECTED_BOOLEAN_KEYS:
            actual = doc.get(key)
            expected = evidence[key] if key in evidence else None
            if key in evidence and actual != expected and not _same_hex32(actual, expected):
                raise fail("%s mismatch" % key)
    return doc


def _sha256_path(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _artifact_bundle_sha256(artifact_hashes: dict[str, str]) -> str:
    payload = "".join(f"{name}:{artifact_hashes[name]}\n" for name in sorted(artifact_hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parser_sha256() -> str:
    return _sha256_path(__file__)


def manifest_document(
    *,
    evidence: dict,
    artifacts: dict[str, str],
    build_evidence: dict[str, str],
    runner_sha: str,
    vendor_sha: str,
    evidence_source: str,
) -> dict:
    doc = dict(evidence)
    doc.update(
        {
            "variant": VARIANT,
            "schema_version": SCHEMA_VERSION,
            "build_id": "0x%08X" % BUILD_ID,
            "qualification_mode": "Q1",
            "expected_return_address": int(evidence["hprintf_callsite_address"], 16) + 4,
            "characterization_only": True,
            "not_a_performance_baseline": True,
            "not_a_latency_measurement": True,
            "generated_private_driver_diagnostic_only": True,
            "production_end_only_frozen": True,
            "diagnostic_only": True,
            "not_numerically_comparable_to_v11a": True,
            "not_latency": True,
            "not_t_npu": True,
            "not_production": True,
            "not_mlek": True,
            "evidence_source": evidence_source,
            "runner_source_sha256": runner_sha,
            "vendor_source_sha256": vendor_sha,
            "artifact_sha256": dict(artifacts),
            "build_evidence_sha256": dict(build_evidence),
        }
    )
    return doc


def build_manifest_document(
    evidence: dict,
    artifact_hashes: dict[str, str],
    *,
    evidence_source: str,
    build_evidence: dict[str, str],
) -> dict:
    artifact_doc = {name: artifact_hashes[name] for name in ("APP.BIN", "VECTORS.BIN", "DDR.BIN")}
    doc = manifest_document(
        evidence=evidence,
        artifacts=artifact_doc,
        build_evidence=build_evidence,
        runner_sha=EXPECTED_MANIFEST_EXACT["runner_source_sha256"],
        vendor_sha=EXPECTED_MANIFEST_EXACT["vendor_source_sha256"],
        evidence_source=evidence_source,
    )
    doc["artifact_bundle_sha256"] = _artifact_bundle_sha256(artifact_hashes)
    doc["parser_sha256"] = _parser_sha256()
    manifest_seed = dict(doc)
    manifest_seed["manifest_sha256"] = "0" * 64
    manifest_json = json.dumps(manifest_seed, indent=2, sort_keys=True)
    doc["manifest_sha256"] = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    return doc


def _load_trace_inputs(paths: argparse.Namespace) -> tuple[str, str, dict[str, str], dict[str, str], str]:
    synthetic_requested = any(
        getattr(paths, name) is not None for name in ("disassembly_text", "nm_text")
    )
    real_requested = any(
        getattr(paths, name) is not None for name in ("elf", "objdump", "nm", "readelf")
    )
    if synthetic_requested and real_requested:
        raise fail("synthetic evidence inputs and real ELF tool inputs are mutually exclusive")
    if not synthetic_requested and not real_requested:
        raise fail("either synthetic evidence inputs or real ELF tool inputs are required")

    common_artifacts = {
        "APP.BIN": paths.app_bin,
        "VECTORS.BIN": paths.vectors_bin,
        "DDR.BIN": paths.ddr_bin,
        "map": paths.map,
    }

    if synthetic_requested:
        if not paths.allow_synthetic_evidence:
            raise fail("synthetic evidence requires --allow-synthetic-evidence")
        missing = [
            name
            for name in ("disassembly_text", "nm_text", "map", "app_bin", "vectors_bin", "ddr_bin")
            if getattr(paths, name) is None
        ]
        if missing:
            raise fail("missing synthetic evidence input(s): %s" % ", ".join(missing))
        disassembly_text = _read_text(paths.disassembly_text)
        nm_text = _read_text(paths.nm_text)
        artifact_hashes = {label: _sha256_path(path) for label, path in common_artifacts.items()}
        build_evidence = {
            "runner_pmu_completion_poll_v12.map": artifact_hashes["map"],
            "checker_disassembly.txt": _sha256_path(paths.disassembly_text),
            "checker_nm.txt": _sha256_path(paths.nm_text),
        }
        return disassembly_text, nm_text, artifact_hashes, build_evidence, "synthetic_fixture"

    missing = [
        name
        for name in ("elf", "objdump", "nm", "readelf", "map", "app_bin", "vectors_bin", "ddr_bin")
        if getattr(paths, name) is None
    ]
    if missing:
        raise fail("missing real ELF input(s): %s" % ", ".join(missing))
    readelf_header = subprocess.run(
        [paths.readelf, "-h", paths.elf],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "Executable" not in readelf_header and "EXEC" not in readelf_header:
        raise fail("%s is not an executable ELF" % paths.elf)
    disassembly_text = subprocess.run(
        [paths.objdump, "-d", paths.elf],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    nm_text = subprocess.run(
        [paths.nm, paths.elf],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    artifact_hashes = {label: _sha256_path(path) for label, path in common_artifacts.items()}
    artifact_hashes["elf"] = _sha256_path(paths.elf)
    build_evidence = {
        "runner_pmu_completion_poll_v12.elf": artifact_hashes["elf"],
        "runner_pmu_completion_poll_v12.map": artifact_hashes["map"],
        "checker_disassembly.txt": _sha256_text(disassembly_text),
        "checker_nm.txt": _sha256_text(nm_text),
    }
    return disassembly_text, nm_text, artifact_hashes, build_evidence, "arm_elf"


def verify(paths: argparse.Namespace) -> dict:
    if paths.manifest_out is None:
        raise fail("--manifest-out is required")
    if int(paths.build_id, 16) != BUILD_ID:
        raise fail("build_id %s is not 0x%08X" % (paths.build_id, BUILD_ID))
    runner_text = _read_text(paths.runner_generated)
    vendor_text = _read_text(paths.vendor_generated)
    runner_generated_sha = _sha256_text(runner_text)
    vendor_generated_sha = _sha256_text(vendor_text)
    verify_generated_sources(runner_text, vendor_text)
    disassembly_text, nm_text, artifact_hashes, build_evidence, evidence_source = _load_trace_inputs(paths)
    build_evidence["generated_runner.c"] = runner_generated_sha
    build_evidence["generated_vendor_u85.c"] = vendor_generated_sha
    evidence = verify_callsite_trace(runner_text, vendor_text, disassembly_text, nm_text)
    doc = build_manifest_document(
        evidence,
        artifact_hashes,
        evidence_source=evidence_source,
        build_evidence=build_evidence,
    )
    validate_artifact_contract(
        json.dumps(doc, sort_keys=True),
        evidence,
        allow_synthetic=(evidence_source == "synthetic_fixture"),
    )
    return doc


def _write_manifest_atomic(path: str, doc: dict) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=directory,
        prefix=".pmu_completion_poll_v12.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_path = handle.name
    os.replace(temp_path, path)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--runner-generated", required=True)
    ap.add_argument("--vendor-generated", required=True)
    ap.add_argument("--manifest-out", required=True)
    ap.add_argument("--disassembly-text")
    ap.add_argument("--nm-text")
    ap.add_argument("--allow-synthetic-evidence", action="store_true")
    ap.add_argument("--elf")
    ap.add_argument("--map")
    ap.add_argument("--app-bin")
    ap.add_argument("--vectors-bin")
    ap.add_argument("--ddr-bin")
    ap.add_argument("--objdump")
    ap.add_argument("--nm")
    ap.add_argument("--readelf")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    doc = verify(args)
    _write_manifest_atomic(args.manifest_out, doc)
    print(json.dumps(doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
