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
    if mnemonic in ("mov", "movs"):
        ops = [part.strip() for part in ins.operands.split(",")]
        if len(ops) >= 2 and q._REG.fullmatch(ops[1]):
            return _resolve_register_value(fn, pos, ops[1], pool)
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


def _local_literal_pool(fn):
    return {ins.addr: ins.value for ins in fn.insns if ins.kind == "word"}


def _prove_dwt_load_for_store(fn, store_index, pool, label):
    store = fn.insns[store_index]
    found = q.defining_insn(fn, store_index, store.src)
    if found is None:
        raise fail("%s store source has no reaching definition" % label)
    load_index, _ = found
    address = _load_address(fn, load_index, pool)
    if address != DWT_CYCCNT:
        raise fail("%s source is not one direct DWT->CYCCNT load" % label)
    if any(ins.kind == "call" for ins in fn.insns[load_index + 1:store_index]):
        raise fail("%s calls a helper between timestamp load and store" % label)
    return fn.insns[load_index].addr


def _materialize_address(fn, start_index, pool, expected, label):
    ins = fn.insns[start_index]
    if ins.kind == "ldr_lit":
        local_pool = _local_literal_pool(fn)
        if ins.literal_addr not in local_pool:
            raise fail("%s literal materialization is not from the veneer-local pool" % label)
        if local_pool[ins.literal_addr] != expected:
            raise fail("%s literal materialization resolves to the wrong address" % label)
        return start_index + 1, ins.dest
    if ins.kind == "mov_imm":
        reg = ins.dest
        next_index = start_index + 1
        if next_index < len(fn.insns):
            next_ins = fn.insns[next_index]
            if next_ins.dest == reg and next_ins.mnemonic.split(".")[0] == "movt":
                next_index += 1
        value = _resolve_register_value(fn, next_index, reg, pool)
        if value != expected:
            raise fail("%s immediate materialization resolves to the wrong address" % label)
        return next_index, reg
    raise fail("%s does not start with a permitted address materialization" % label)


def _regs_used(ins):
    return set(re.findall(r"\b(?:r1[0-5]|r[0-9]|sp|lr|pc)\b", ins.operands))


def _run(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout


def manifest_document(base_doc: dict, artifacts: dict, runner_sha: str, vendor_sha: str,
                      patch_counts: dict) -> dict:
    doc = dict(base_doc)
    doc.update(
        {
            "schema_version": SCHEMA_VERSION,
            "build_id": "0x%08X" % BUILD_ID,
            "variant": VARIANT,
            "characterization_only": True,
            "not_a_performance_baseline": True,
            "not_a_latency_measurement": True,
            "busy_poll_interval_only": True,
            "d23_split_only": True,
            "post_t3_handoff_out_of_scope": True,
            "verify_output_stays_enabled": True,
            "generated_private_driver_diagnostic_only": True,
            "production_end_only_frozen": True,
            "mlek_performance_not_started": True,
            "first_veneer_probe_only": True,
            "perturbed_window_only": True,
            "non_comparable_to_production_or_latency": True,
            "generated_runner_sha256": runner_sha,
            "generated_vendor_sha256": vendor_sha,
            "generated_patch_counts": patch_counts,
            "artifact_sha256": dict(artifacts),
        }
    )
    return doc


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
    for idx, ins in enumerate(test_u85.insns[vector_store_index + 1:], start=vector_store_index + 1):
        if ins.addr >= submit_store_addr or ins.kind != "store" or ins.offset != VECTOR_SLOT_OFFSET:
            continue
        address = _vector_slot_store_address(test_u85, idx, pool)
        if address is None:
            raise fail("runtime vector overwrite candidate base is unresolved")
        if address == SCB_VTOR + VECTOR_SLOT_OFFSET:
            raise fail("runtime vector target is later overwritten")

    exec_insns = [ins for ins in veneer.insns if ins.mnemonic not in q.DATA_DIRECTIVES]
    if not (5 <= len(exec_insns) <= 7):
        raise fail("veneer has %d executable instructions, expected 5-7" % len(exec_insns))
    allowed_regs = {"r0", "r1", "pc"}
    forbidden_prefixes = ("push", "pop", "bl", "blx", "cps", "dsb", "isb", "mrs", "msr")
    for ins in exec_insns:
        mnemonic = ins.mnemonic.split(".")[0]
        if mnemonic in forbidden_prefixes:
            raise fail("veneer uses forbidden instruction %s" % ins.mnemonic)
        if ins.dest == "lr" or ins.base == "sp" or ins.dest == "sp":
            raise fail("veneer touches LR/SP")
        used = _regs_used(ins)
        if not used.issubset(allowed_regs | {"sp", "lr"}):
            raise fail("veneer uses disallowed scratch registers")
        if "sp" in used or "lr" in used:
            raise fail("veneer touches LR/SP")
        if ins.kind == "call":
            raise fail("veneer contains a call")

    exec_indexes = [veneer.insns.index(ins) for ins in exec_insns]
    cursor, dwt_reg = _materialize_address(veneer, exec_indexes[0], pool, DWT_CYCCNT, "veneer DWT address")
    if cursor >= len(veneer.insns):
        raise fail("veneer ends before the DWT CYCCNT read")
    dwt_load_ins = veneer.insns[cursor]
    memop = q._MEMOP.search(dwt_load_ins.operands)
    if (_load_address(veneer, cursor, pool) != DWT_CYCCNT
            or dwt_load_ins.dest != "r1"
            or memop is None
            or memop.group(1) != dwt_reg):
        raise fail("veneer does not perform the required DWT CYCCNT read into r1")
    cursor += 1
    cursor, j0_reg = _materialize_address(veneer, cursor, pool, j0_symbol, "veneer J0 slot")
    if cursor >= len(veneer.insns):
        raise fail("veneer ends before the J0 store")
    fourth_index = cursor
    fourth = veneer.insns[fourth_index]
    if fourth.kind != "store" or fourth.src != "r1" or fourth.base != j0_reg or _vector_slot_store_address(veneer, fourth_index, pool) != j0_symbol:
        raise fail("veneer does not store J0 exactly once to the J0 slot")
    j0_load = _prove_dwt_load_for_store(veneer, fourth_index, pool, "J0")
    cursor += 1
    if cursor >= len(veneer.insns):
        raise fail("veneer ends before the stock-handler branch")
    fifth = veneer.insns[cursor]
    branch_target = q._CALL_TARGET.search(fifth.operands)
    if fifth.mnemonic.split(".")[0] != "b" or branch_target is None:
        raise fail("veneer tail transfer is not an unconditional branch")
    if branch_target.group(1) != "u85_irq_handler":
        raise fail("veneer does not branch directly to the stock handler")
    cursor += 1
    if cursor != exec_indexes[-1] + 1:
        raise fail("veneer contains extra executable effects")
    for ins in exec_insns:
        mnemonic = ins.mnemonic.split(".")[0]
        if mnemonic.startswith("b") and ins is not fifth:
            raise fail("veneer contains an extra branch")
        if ins.kind == "store" and ins.addr != fourth.addr:
            raise fail("veneer has an extra store")
    if sum(1 for idx, _ in enumerate(veneer.insns) if _load_address(veneer, idx, pool) == DWT_CYCCNT) != 1:
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
    i0_store_index = next(n for n, ins in enumerate(irq.insns) if ins.addr == i0_store)
    t3_store_index = next(n for n, ins in enumerate(irq.insns) if ins.addr == t3_store)
    i0_load = _prove_dwt_load_for_store(irq, i0_store_index, pool, "I0")
    t3_load = _prove_dwt_load_for_store(irq, t3_store_index, pool, "T3")
    return {
        "vector_slot_store": vector_store.addr,
        "vector_value": vector_value,
        "veneer_address": veneer_addr,
        "stock_handler_address": symbols["u85_irq_handler"],
        "j0_dwt_load_address": j0_load,
        "j0_store_address": fourth.addr,
        "i0_dwt_load_address": i0_load,
        "i0_store_address": i0_store,
        "t3_dwt_load_address": t3_load,
        "t3_store_address": t3_store,
        "npu_status_read_address": status_read,
        "npu_cmd_irq_clear_store_address": cmd2_store,
    }


def verify(paths: argparse.Namespace) -> dict:
    if int(paths.build_id, 16) != BUILD_ID:
        raise fail("build_id %s is not 0x%08X" % (paths.build_id, BUILD_ID))
    if _sha256(paths.vendor_src) != FROZEN_VENDOR_SHA256:
        raise fail("vendor hash mismatch")
    with open(paths.runner_generated) as handle:
        runner_text = handle.read()
    with open(paths.vendor_generated) as handle:
        vendor_text = handle.read()
    source_counts = verify_generated_sources(runner_text, vendor_text)
    header = _run([paths.readelf, "-h", paths.elf])
    if "Executable" not in header and "EXEC" not in header:
        raise fail("%s is not an executable ELF" % paths.elf)
    disassembly = _run([paths.objdump, "-d", paths.elf])
    nm_text = _run([paths.nm, paths.elf])
    try:
        result = q.evaluate(
            mode="Q1",
            disassembly_text=disassembly,
            nm_text=nm_text,
            strings_text=_run([paths.objdump, "-s", paths.elf]),
            relocation_text=_run([paths.objdump, "-r", paths.vendor_object]),
            object_disassembly_text=_run([
                paths.objdump, "-drz", "--section=" + q.OBJECT_TEXT_SECTION,
                paths.vendor_object,
            ]),
            object_sections_text=_run([paths.objdump, "-s", paths.vendor_object]),
            vendor_source_text=vendor_text,
            interface_header_text=open(paths.interface_header, newline=None).read(),
            compiler_flags=paths.cflags,
            preprocessed_text=open(paths.preprocessed, newline=None).read(),
            cfg_header_text=open(paths.regs_header, newline=None).read(),
        )
    except q.GateError as exc:
        raise fail("base H-PRINTF gate: %s" % exc)
    elf = verify_final_elf(disassembly, nm_text)
    base_doc = q.manifest_document(
        result=result,
        build_id=BUILD_ID,
        vendor_source_sha256=hashlib.sha256(vendor_text.encode()).hexdigest(),
        vendor_object_sha256=_sha256(paths.vendor_object),
        compiler_flags=paths.cflags,
        artifacts={
            "APP.BIN": _sha256(paths.app_bin),
            "VECTORS.BIN": _sha256(paths.vectors_bin),
            "DDR.BIN": _sha256(paths.ddr_bin),
            "elf": _sha256(paths.elf),
            "map": _sha256(paths.map),
        },
    )
    base_doc["source_counts"] = source_counts
    base_doc["elf"] = elf
    doc = manifest_document(
        base_doc=base_doc,
        artifacts={
            "APP.BIN": _sha256(paths.app_bin),
            "VECTORS.BIN": _sha256(paths.vectors_bin),
            "DDR.BIN": _sha256(paths.ddr_bin),
        },
        runner_sha=hashlib.sha256(runner_text.encode()).hexdigest(),
        vendor_sha=hashlib.sha256(vendor_text.encode()).hexdigest(),
        patch_counts=source_counts,
    )
    doc["frozen_vendor_source_sha256"] = FROZEN_VENDOR_SHA256
    doc["build_evidence_sha256"] = {
        "runner_pmu_interval_v11a.elf": _sha256(paths.elf),
        "runner_pmu_interval_v11a.map": _sha256(paths.map),
        "generated_runner.c": hashlib.sha256(runner_text.encode()).hexdigest(),
        "generated_vendor_u85.c": hashlib.sha256(vendor_text.encode()).hexdigest(),
        "generated_vendor_u85.o": _sha256(paths.vendor_object),
        "preprocessed_runner.i": _sha256(paths.preprocessed),
    }
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--vendor-src", required=True)
    ap.add_argument("--interface-header", required=True)
    ap.add_argument("--vendor-object", required=True)
    ap.add_argument("--regs-header", required=True)
    ap.add_argument("--preprocessed", required=True)
    ap.add_argument("--runner-generated", required=True)
    ap.add_argument("--vendor-generated", required=True)
    ap.add_argument("--elf", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--app-bin", required=True)
    ap.add_argument("--vectors-bin", required=True)
    ap.add_argument("--ddr-bin", required=True)
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--nm", required=True)
    ap.add_argument("--readelf", required=True)
    ap.add_argument("--cflags", required=True)
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
