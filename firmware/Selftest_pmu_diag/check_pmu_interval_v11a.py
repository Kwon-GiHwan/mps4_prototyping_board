"""Static gate for PMU_INTERVAL_ENTRY_DIAG_V11A generated sources and final layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess

import check_pmu_qual as q

BUILD_ID = 0x41314950
SCHEMA_VERSION = 11
VARIANT = "PMU_INTERVAL_ENTRY_DIAG_V11A"
RUNNER_APPEND_MARKERS = (
    "d.t_submit_before_cmd",
    "d.t_submit_after_cmd",
    "d.t_vector_probe",
    "d.t_irq_handler_entry",
    "d.t_irq_status_seen",
    "d.i0_hit_count",
    "d.t3_hit_count",
)
VENDOR_MARKERS = (
    "PMU_INTERVAL_V10_T1",
    "PMU_INTERVAL_V10_T2",
    "PMU_INTERVAL_V10_I0",
    "PMU_INTERVAL_V10_T3",
)
FROZEN_VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
DWT_CYCCNT = 0xE0001004
SCB_VTOR = 0xE000ED08
NPU_CMD = 0x50004008
NPU_STATUS = 0x50004004
VECTOR_SLOT_OFFSET = 128


class GateError(SystemExit):
    pass


def fail(message: str) -> GateError:
    return GateError("FAIL %s" % message)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def count_once(text: str, needle: str, what: str) -> int:
    count = text.count(needle)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return count


def verify_generated_sources(runner_text: str, vendor_text: str) -> dict:
    counts = {}
    for needle in RUNNER_APPEND_MARKERS:
        counts[needle] = count_once(runner_text, needle, needle)
    for needle in VENDOR_MARKERS:
        counts[needle] = count_once(vendor_text, needle, needle)
    counts["runtime_vector_install"] = count_once(
        vendor_text,
        "NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);",
        "runtime vector install",
    )
    count_once(vendor_text, "extern void v11a_u85_irq_entry_veneer(void);", "veneer extern")
    count_once(vendor_text, "volatile uint32_t pmu_interval_v11a_t_vector_probe;", "J0 storage")
    if "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);" in vendor_text:
        raise fail("stock handler remains a runtime vector target")
    t1 = vendor_text.index("PMU_INTERVAL_V10_T1")
    t2 = vendor_text.index("PMU_INTERVAL_V10_T2")
    submit_hit = re.search(
        r"write_reg\s*\(\s*NPU_REG_CMD\s*,\s*read_val\s*\|\s*0x0*1\s*\)\s*;",
        vendor_text[t1:t2],
    )
    submit = t1 + submit_hit.start() if submit_hit is not None else -1
    wait_call = vendor_text.find("wait_for_irq();", t2)
    if submit < 0 or wait_call < 0 or not (t1 < submit < t2 < wait_call):
        raise fail("T1→submit-store→T2→wait order violated")
    i0 = vendor_text.index("PMU_INTERVAL_V10_I0")
    t3 = vendor_text.index("PMU_INTERVAL_V10_T3")
    status_read = vendor_text.find("read_reg(NPU_REG_STATUS", i0, t3)
    completion_if = vendor_text.rfind("if ((status_register & 0x02)){", 0, t3)
    irq_flag = vendor_text.find("irq_triggered = true", t3)
    cmd2 = vendor_text.find("write_reg(NPU_REG_CMD, 2);", irq_flag)
    i0_count = vendor_text.find("pmu_interval_v10_i0_hit_count++;", cmd2)
    t3_count = vendor_text.find("pmu_interval_v10_t3_hit_count++;", t3)
    if (status_read < 0 or completion_if < 0 or irq_flag < 0 or cmd2 < 0
            or i0_count < 0 or t3_count < 0
            or not (i0 < status_read < completion_if < t3 < t3_count < irq_flag < cmd2 < i0_count)):
        raise fail("ISR I0→status→completion→T3→flag→CMD2→count order violated")
    for marker in VENDOR_MARKERS:
        start = vendor_text.index(marker)
        lines = vendor_text[start:].splitlines()
        joined = "\n".join(lines[:2])
        if "printf" in joined:
            raise fail("%s carries forbidden logging" % marker)
        if "read_reg(" in joined or "write_reg(" in joined:
            raise fail("%s injects forbidden MMIO" % marker)
    for field in ("t_submit_before_cmd", "t_submit_after_cmd", "t_vector_probe",
                  "t_irq_handler_entry", "t_irq_status_seen", "i0_hit_count", "t3_hit_count"):
        count_once(runner_text, "put32(&c, d->%s);" % field, "runner serializer for %s" % field)
    return counts


def _load_address(fn, index, pool):
    ins = fn.insns[index]
    if not ins.mnemonic.split(".")[0].startswith("ldr"):
        return None
    hit = q._MEMOP.search(ins.operands)
    if hit is None:
        return None
    base = _resolve_register_value(fn, index, hit.group(1), pool)
    if base is None:
        return None
    offset = q._int(hit.group(2)) if hit.group(2) else 0
    return base + offset


def _resolve_register_value(fn, index, reg, pool):
    value = q.resolve_register(fn, index, reg, pool)
    if value is not None:
        return value
    found = q.defining_insn(fn, index, reg)
    if found is None:
        return None
    pos, ins = found
    mnemonic = ins.mnemonic.split(".")[0]
    if mnemonic.startswith("ldr") and q._MEMOP.search(ins.operands):
        return _load_address(fn, pos, pool)
    if mnemonic == "movt":
        low = _resolve_register_value(fn, pos, reg, pool)
        if low is None:
            return None
        imm = q._IMM.search(ins.operands)
        if imm is None:
            return None
        return (low & 0xFFFF) | (q._int(imm.group(1)) << 16)
    return None


def _find_function(funcs, name):
    fn = funcs.get(name)
    if fn is None:
        raise fail("final ELF has no <%s>" % name)
    return fn


def _literal_value(fn, index, pool, reg):
    value = _resolve_register_value(fn, index, reg, pool)
    if value is None:
        raise fail("%s at 0x%x is not backed by a proven literal/immediate" % (reg, fn.insns[index].addr))
    return value


def _vector_slot_store_address(fn, index, pool):
    ins = fn.insns[index]
    base = _resolve_register_value(fn, index, ins.base, pool)
    return None if base is None else base + ins.offset


def verify_final_elf(disassembly_text: str, nm_text: str) -> dict:
    funcs = q.parse_disassembly(disassembly_text).functions
    pool = q.literal_pool(funcs)
    symbols = q.parse_nm(nm_text)
    test_u85 = _find_function(funcs, "test_u85")
    veneer = _find_function(funcs, "v11a_u85_irq_entry_veneer")
    irq = _find_function(funcs, "u85_irq_handler")
    j0_symbol = symbols.get("pmu_interval_v11a_t_vector_probe")
    if j0_symbol is None:
        raise fail("final ELF has no <pmu_interval_v11a_t_vector_probe> symbol")

    vector_store_index = None
    vector_store = None
    for idx, ins in enumerate(test_u85.insns):
        if ins.kind == "store" and ins.offset == VECTOR_SLOT_OFFSET:
            vector_store_index = idx
            vector_store = ins
            break
    if vector_store is None:
        raise fail("test_u85 has no VTOR-slot store")
    base_found = q.defining_insn(test_u85, vector_store_index, vector_store.base)
    if base_found is None:
        raise fail("VTOR-slot store base has no reaching definition")
    base_index, _ = base_found
    if _load_address(test_u85, base_index, pool) != SCB_VTOR:
        raise fail("runtime vector store is not based on SCB->VTOR")
    vector_value = _literal_value(test_u85, vector_store_index, pool, vector_store.src)
    if (vector_value & 1) != 1:
        raise fail("runtime vector target is not a Thumb entry")
    veneer_addr = symbols.get("v11a_u85_irq_entry_veneer")
    if veneer_addr is None:
        raise fail("final ELF has no <v11a_u85_irq_entry_veneer> symbol")
    if (vector_value & ~1) != veneer_addr:
        raise fail("runtime vector target does not resolve to the veneer")
    submit_store_addr = None
    for idx, ins in enumerate(test_u85.insns):
        if (ins.kind == "store"
                and _vector_slot_store_address(test_u85, idx, pool) == NPU_CMD):
            submit_store_addr = ins.addr
            break
    if submit_store_addr is None:
        raise fail("test_u85 has no submit-path NPU CMD store")
    if any(ins.kind == "store"
           and _vector_slot_store_address(test_u85, idx, pool) == SCB_VTOR + VECTOR_SLOT_OFFSET
           for idx, ins in enumerate(test_u85.insns[vector_store_index + 1:], start=vector_store_index + 1)
           if ins.addr < submit_store_addr):
        raise fail("runtime vector target is later overwritten")

    exec_insns = [ins for ins in veneer.insns if ins.mnemonic not in q.DATA_DIRECTIVES]
    if len(exec_insns) != 5:
        raise fail("veneer has %d executable instructions, expected 5" % len(exec_insns))
    first, second, third, fourth, fifth = exec_insns
    if first.kind != "ldr_lit" or pool.get(first.literal_addr) != DWT_CYCCNT:
        raise fail("veneer first instruction is not a DWT literal load")
    if _load_address(veneer, 1, pool) != DWT_CYCCNT:
        raise fail("veneer second instruction is not a DWT CYCCNT read")
    if third.kind != "ldr_lit" or pool.get(third.literal_addr) != j0_symbol:
        raise fail("veneer third instruction does not materialize the J0 slot")
    if fourth.kind != "store" or _vector_slot_store_address(veneer, veneer.insns.index(fourth), pool) != j0_symbol:
        raise fail("veneer does not store J0 exactly once to the J0 slot")
    branch_target = q._CALL_TARGET.search(fifth.operands)
    if fifth.mnemonic.split(".")[0] != "b" or branch_target is None:
        raise fail("veneer tail transfer is not an unconditional branch")
    if branch_target.group(1) != "u85_irq_handler":
        raise fail("veneer does not branch directly to the stock handler")
    forbidden_prefixes = ("push", "pop", "bl", "blx", "cps", "dsb", "isb", "mrs", "msr")
    for ins in exec_insns:
        mnemonic = ins.mnemonic.split(".")[0]
        if mnemonic in forbidden_prefixes:
            raise fail("veneer uses forbidden instruction %s" % ins.mnemonic)
        if ins.dest == "lr" or ins.base == "sp" or ins.dest == "sp":
            raise fail("veneer touches LR/SP")
        if mnemonic.startswith("b") and ins is not fifth:
            raise fail("veneer contains an extra branch")
        if ins.kind == "store" and ins.addr != fourth.addr:
            raise fail("veneer has an extra store")
        if ins.kind == "call":
            raise fail("veneer contains a call")
    if sum(1 for ins in exec_insns if ins.kind == "ldr_lit") != 2:
        raise fail("veneer has more than two literal materializations")
    if sum(1 for idx, ins in enumerate(veneer.insns) if _load_address(veneer, idx, pool) == DWT_CYCCNT) != 1:
        raise fail("veneer does not have exactly one DWT CYCCNT load")

    i0_symbol = symbols.get("pmu_interval_v10_t_irq_handler_entry")
    t3_symbol = symbols.get("pmu_interval_v10_t_irq_status_seen")
    if i0_symbol is None or t3_symbol is None:
        raise fail("final ELF lacks I0/T3 symbols")
    i0_store = None
    t3_store = None
    status_read = None
    flag_symbol = symbols.get("irq_triggered")
    if flag_symbol is None:
        raise fail("final ELF lacks irq_triggered")
    flag_store = None
    cmd2_store = None
    for idx, ins in enumerate(irq.insns):
        if ins.kind == "store":
            address = _vector_slot_store_address(irq, idx, pool)
            if address == i0_symbol:
                i0_store = ins.addr
            elif address == t3_symbol:
                t3_store = ins.addr
            elif address == flag_symbol:
                flag_store = ins.addr
            elif address == NPU_CMD and _resolve_register_value(irq, idx, ins.src, pool) == 2:
                cmd2_store = ins.addr
        if _load_address(irq, idx, pool) == NPU_STATUS:
            status_read = ins.addr
    if None in (i0_store, t3_store, status_read, flag_store, cmd2_store):
        raise fail("stock handler ordering evidence is incomplete")
    if [i0_store, status_read, t3_store, flag_store, cmd2_store] != sorted([i0_store, status_read, t3_store, flag_store, cmd2_store]):
        raise fail("stock handler I0→STATUS→T3→flag→CMD2 order violated")
    return {
        "vector_slot_store": vector_store.addr,
        "vector_value": vector_value,
        "veneer_address": veneer_addr,
        "stock_handler_address": symbols["u85_irq_handler"],
        "j0_store_address": fourth.addr,
        "i0_store_address": i0_store,
        "t3_store_address": t3_store,
        "npu_status_read_address": status_read,
        "npu_cmd_irq_clear_store_address": cmd2_store,
    }


def verify(paths: argparse.Namespace) -> dict:
    if _sha256(paths.vendor_src) != FROZEN_VENDOR_SHA256:
        raise fail("vendor hash mismatch")
    with open(paths.runner_generated) as handle:
        runner_text = handle.read()
    with open(paths.vendor_generated) as handle:
        vendor_text = handle.read()
    source_counts = verify_generated_sources(runner_text, vendor_text)
    with open(paths.final_disassembly) as handle:
        disassembly = handle.read()
    with open(paths.final_nm) as handle:
        nm_text = handle.read()
    try:
        q.evaluate(
            mode="Q1",
            disassembly_text=disassembly,
            nm_text=nm_text,
            strings_text=disassembly,
            relocation_text="",
            object_disassembly_text="Disassembly of section .text:\n",
            object_sections_text="Contents of section .rodata:\n",
            vendor_source_text=vendor_text,
            interface_header_text="",
            compiler_flags="",
            preprocessed_text="",
            cfg_header_text="",
        )
    except q.GateError as exc:
        raise fail("base H-PRINTF gate: %s" % exc)
    elf = verify_final_elf(disassembly, nm_text)
    return {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": BUILD_ID,
        "source_counts": source_counts,
        "elf": elf,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor-src", required=True)
    ap.add_argument("--runner-generated", required=True)
    ap.add_argument("--vendor-generated", required=True)
    ap.add_argument("--final-disassembly", required=True)
    ap.add_argument("--final-nm", required=True)
    ap.add_argument("--manifest-out")
    args = ap.parse_args()
    result = verify(args)
    if args.manifest_out:
        os.makedirs(os.path.dirname(args.manifest_out), exist_ok=True)
        with open(args.manifest_out, "w") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
