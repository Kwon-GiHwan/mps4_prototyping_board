"""Static gate for PMU_INTERVAL_DIAG_V9 generated sources and final layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess

import check_pmu_qual as q

BUILD_ID = 0x39564950
SCHEMA_VERSION = 9
VARIANT = "PMU_INTERVAL_DIAG_V9"
RUNNER_APPEND_MARKERS = (
    "d.t_submit_before_cmd",
    "d.t_submit_after_cmd",
    "d.t_irq_status_seen",
)
VENDOR_MARKERS = (
    "PMU_INTERVAL_V9_T1",
    "PMU_INTERVAL_V9_T2",
    "PMU_INTERVAL_V9_T3",
)
FROZEN_VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
CHECKPOINT_SYMBOLS = {
    # -O1 inlines test_commands() into test_u85(); the final-ELF owner is
    # pinned here rather than inferred from source-level function names.
    "pmu_interval_v9_t_submit_before_cmd": "test_u85",
    "pmu_interval_v9_t_submit_after_cmd": "test_u85",
    "pmu_interval_v9_t_irq_status_seen": "u85_irq_handler",
}
DWT_CYCCNT = 0xE0001004
NPU_CMD = 0x50004008
T0_STACK_OFFSET = 96
T5_STACK_OFFSET = 100


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
    t1 = vendor_text.index("PMU_INTERVAL_V9_T1")
    t2 = vendor_text.index("PMU_INTERVAL_V9_T2")
    submit_hit = re.search(
        r"write_reg\s*\(\s*NPU_REG_CMD\s*,\s*read_val\s*\|\s*0x0*1\s*\)\s*;",
        vendor_text[t1:t2])
    submit = t1 + submit_hit.start() if submit_hit is not None else -1
    wait_call = vendor_text.find("wait_for_irq();", t2)
    if submit < 0 or wait_call < 0 or not (t1 < submit < t2 < wait_call):
        raise fail("T1→submit-store→T2→wait order violated")
    t3 = vendor_text.index("PMU_INTERVAL_V9_T3")
    status_read = vendor_text.rfind("read_reg(NPU_REG_STATUS", 0, t3)
    completion_if = vendor_text.rfind("if ((status_register & 0x02)){", 0, t3)
    irq_flag = vendor_text.find("irq_triggered = true", t3)
    if (status_read < 0 or completion_if < 0 or irq_flag < 0
            or not (status_read < completion_if < t3 < irq_flag)):
        raise fail("ISR status-read→completion-if→T3→flag order violated")
    for marker in VENDOR_MARKERS:
        start = vendor_text.index(marker)
        lines = vendor_text[start:].splitlines()
        joined = "\n".join(lines[:2])
        if "printf" in joined:
            raise fail("%s carries forbidden logging" % marker)
        if "read_reg(" in joined or "write_reg(" in joined:
            raise fail("%s injects forbidden MMIO" % marker)
    for field in ("t_submit_before_cmd", "t_submit_after_cmd", "t_irq_status_seen"):
        if runner_text.count("put32(&c, d->%s);" % field) != 1:
            raise fail("runner serializer append for %s missing or duplicated" % field)
    for field in ("t_call_enter", "t_call_return"):
        count_once(
            runner_text, "put32(&c, d->%s);" % field,
            "runner serializer for %s" % field)
        count_once(
            runner_text, "d.%s = read_timestamp();" % field,
            "runner assignment for %s" % field)
    t0_source = runner_text.index("d.t_call_enter = read_timestamp();")
    call_source = runner_text.find("rc = run_fixed_inference();", t0_source)
    t5_source = runner_text.find("d.t_call_return = read_timestamp();", call_source)
    if call_source < 0 or t5_source < 0 or not (t0_source < call_source < t5_source):
        raise fail("runner T0→run_fixed_inference→T5 source order violated")
    if len(re.findall(r"^\s*#\s*define\s+BUSY_SLEEP\s*$", vendor_text, re.M)) != 1:
        raise fail("BUSY_SLEEP busy-poll mode is not defined exactly once")
    if len(re.findall(r"^\s*#\s*define\s+VERIFY_OUTPUT\s+1\s*$", vendor_text, re.M)) != 1:
        raise fail("VERIFY_OUTPUT=1 is not preserved")
    return counts


def _load_address(fn, index, pool):
    """Resolve the address read by a plain register-indirect LDR."""
    ins = fn.insns[index]
    if not ins.mnemonic.split(".")[0].startswith("ldr"):
        return None
    hit = q._MEMOP.search(ins.operands)
    if hit is None:
        return None
    base = q.resolve_register(fn, index, hit.group(1), pool)
    if base is None:
        return None
    offset = q._int(hit.group(2)) if hit.group(2) else 0
    return base + offset


def _prove_dwt_load_for_store(fn, store_index, pool, label):
    store = fn.insns[store_index]
    found = q.defining_insn(fn, store_index, store.src)
    if found is None:
        raise fail("%s store source has no reaching definition" % label)
    load_index, load = found
    address = _load_address(fn, load_index, pool)
    if address != DWT_CYCCNT:
        raise fail("%s source is not one direct DWT->CYCCNT load" % label)
    if any(ins.kind == "call" for ins in fn.insns[load_index + 1:store_index]):
        raise fail("%s calls a helper between timestamp load and store" % label)
    return load.addr


def _timestamp_pairs(fn, start, stop, pool):
    """Direct DWT load followed by its first reaching store within a window."""
    pairs = []
    for n in range(start, stop):
        ins = fn.insns[n]
        if _load_address(fn, n, pool) != DWT_CYCCNT or ins.dest is None:
            continue
        for m in range(n + 1, stop):
            candidate = fn.insns[m]
            if candidate.kind == "call":
                break
            if candidate.dest == ins.dest:
                break
            if candidate.kind == "store" and candidate.src == ins.dest:
                pairs.append((ins.addr, candidate.addr,
                              candidate.base, candidate.offset))
                break
    return pairs


def verify_checkpoint_stores(disassembly_text: str, nm_text: str) -> dict:
    funcs = q.parse_disassembly(disassembly_text).functions
    pool = q.literal_pool(funcs)
    symbols = q.parse_nm(nm_text)
    evidence = {}
    for symbol, function in CHECKPOINT_SYMBOLS.items():
        address = symbols.get(symbol)
        if address is None:
            raise fail("final ELF has no <%s> symbol" % symbol)
        fn = funcs.get(function)
        if fn is None:
            raise fail("final ELF has no <%s> function" % function)
        stores = [ins.addr for n, ins in enumerate(fn.insns)
                  if ins.kind == "store" and q.store_address(fn, n, pool) == address]
        if len(stores) != 1:
            raise fail("<%s> stores to <%s> %d times, expected exactly 1"
                       % (function, symbol, len(stores)))
        load_address = _prove_dwt_load_for_store(
            fn, next(n for n, ins in enumerate(fn.insns) if ins.addr == stores[0]),
            pool, symbol)
        evidence["%s_dwt_load_address" % symbol] = load_address
        evidence["%s_store_address" % symbol] = stores[0]
    if not (evidence["pmu_interval_v9_t_submit_before_cmd_store_address"]
            < evidence["pmu_interval_v9_t_submit_after_cmd_store_address"]):
        raise fail("final ELF T1/T2 store order is reversed")
    test_u85 = funcs["test_u85"]
    t1_store = evidence["pmu_interval_v9_t_submit_before_cmd_store_address"]
    t2_store = evidence["pmu_interval_v9_t_submit_after_cmd_store_address"]
    submit_stores = [ins.addr for n, ins in enumerate(test_u85.insns)
                     if t1_store < ins.addr < t2_store
                     and ins.kind == "store"
                     and q.store_address(test_u85, n, pool) == NPU_CMD]
    if len(submit_stores) != 1:
        raise fail("final ELF has %d NPU CMD submit stores between T1 and T2, expected 1"
                   % len(submit_stores))
    evidence["npu_cmd_submit_store_address"] = submit_stores[0]

    dispatch = funcs.get("dispatch")
    if dispatch is None:
        raise fail("final ELF has no <dispatch> function for T0/T5 attestation")
    calls = [n for n, ins in enumerate(dispatch.insns)
             if ins.kind == "call" and ins.callee == "run_fixed_inference"]
    if len(calls) != 1:
        raise fail("<dispatch> calls <run_fixed_inference> %d times, expected 1"
                   % len(calls))
    call_index = calls[0]
    pre_pairs = _timestamp_pairs(dispatch, max(0, call_index - 16), call_index, pool)
    post_pairs = _timestamp_pairs(
        dispatch, call_index + 1, min(len(dispatch.insns), call_index + 7), pool)
    if len(pre_pairs) != 1:
        raise fail("T0 final-ELF window has %d direct DWT-load/store pairs, expected 1"
                   % len(pre_pairs))
    if len(post_pairs) != 1:
        raise fail("T5 final-ELF window has %d direct DWT-load/store pairs, expected 1"
                   % len(post_pairs))
    if pre_pairs[0][2:] != ("sp", T0_STACK_OFFSET):
        raise fail("T0 timestamp is not stored to the attested record stack slot sp+%d"
                   % T0_STACK_OFFSET)
    if post_pairs[0][2:] != ("sp", T5_STACK_OFFSET):
        raise fail("T5 timestamp is not stored to the attested record stack slot sp+%d"
                   % T5_STACK_OFFSET)
    evidence.update({
        "t0_dwt_load_address": pre_pairs[0][0],
        "t0_store_address": pre_pairs[0][1],
        "t0_record_stack_offset": pre_pairs[0][3],
        "run_fixed_inference_call_address": dispatch.insns[call_index].addr,
        "t5_dwt_load_address": post_pairs[0][0],
        "t5_store_address": post_pairs[0][1],
        "t5_record_stack_offset": post_pairs[0][3],
    })
    return evidence


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
            "verify_output_stays_enabled": True,
            "generated_private_driver_diagnostic_only": True,
            "production_end_only_frozen": True,
            "mlek_performance_not_started": True,
            "generated_runner_sha256": runner_sha,
            "generated_vendor_sha256": vendor_sha,
            "generated_patch_counts": patch_counts,
            "artifact_sha256": dict(artifacts),
        }
    )
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", required=True)
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--vendor-source", required=True)
    ap.add_argument("--interface-header", required=True)
    ap.add_argument("--vendor-object", required=True)
    ap.add_argument("--regs-header", required=True)
    ap.add_argument("--preprocessed", required=True)
    ap.add_argument("--elf", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--app-bin", required=True)
    ap.add_argument("--vectors-bin", required=True)
    ap.add_argument("--ddr-bin", required=True)
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--nm", required=True)
    ap.add_argument("--readelf", required=True)
    ap.add_argument("--cflags", required=True)
    ap.add_argument("--manifest-out", required=True)
    args = ap.parse_args()

    if int(args.build_id, 16) != BUILD_ID:
        raise fail("build_id %s is not 0x%08X" % (args.build_id, BUILD_ID))
    with open(args.runner) as handle:
        runner_text = handle.read()
    with open(args.vendor) as handle:
        vendor_text = handle.read()
    patch_counts = verify_generated_sources(runner_text, vendor_text)
    if _sha256(args.vendor_source) != FROZEN_VENDOR_SHA256:
        raise fail("frozen vendor source hash mismatch")

    def run(argv):
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout

    header = run([args.readelf, "-h", args.elf])
    if "Executable" not in header and "EXEC" not in header:
        raise fail("%s is not an executable ELF" % args.elf)
    disassembly = run([args.objdump, "-d", args.elf])
    nm_text = run([args.nm, args.elf])
    try:
        result = q.evaluate(
            mode="Q1",
            disassembly_text=disassembly,
            nm_text=nm_text,
            strings_text=run([args.objdump, "-s", args.elf]),
            relocation_text=run([args.objdump, "-r", args.vendor_object]),
            object_disassembly_text=run([
                args.objdump, "-drz", "--section=" + q.OBJECT_TEXT_SECTION,
                args.vendor_object]),
            object_sections_text=run([args.objdump, "-s", args.vendor_object]),
            vendor_source_text=vendor_text,
            interface_header_text=open(args.interface_header, newline=None).read(),
            compiler_flags=args.cflags,
            preprocessed_text=open(args.preprocessed, newline=None).read(),
            cfg_header_text=open(args.regs_header, newline=None).read(),
        )
    except q.GateError as exc:
        raise fail("base H-PRINTF gate: %s" % exc)
    checkpoint_evidence = verify_checkpoint_stores(disassembly, nm_text)
    base_doc = q.manifest_document(
        result=result,
        build_id=BUILD_ID,
        vendor_source_sha256=hashlib.sha256(vendor_text.encode()).hexdigest(),
        vendor_object_sha256=_sha256(args.vendor_object),
        compiler_flags=args.cflags,
        artifacts={
            "APP.BIN": _sha256(args.app_bin),
            "VECTORS.BIN": _sha256(args.vectors_bin),
            "DDR.BIN": _sha256(args.ddr_bin),
            "elf": _sha256(args.elf),
            "map": _sha256(args.map),
        },
    )
    base_doc.update(checkpoint_evidence)
    doc = manifest_document(
        base_doc=base_doc,
        artifacts={
            "APP.BIN": _sha256(args.app_bin),
            "VECTORS.BIN": _sha256(args.vectors_bin),
            "DDR.BIN": _sha256(args.ddr_bin),
        },
        runner_sha=hashlib.sha256(runner_text.encode()).hexdigest(),
        vendor_sha=hashlib.sha256(vendor_text.encode()).hexdigest(),
        patch_counts=patch_counts,
    )
    doc["frozen_vendor_source_sha256"] = FROZEN_VENDOR_SHA256
    doc["build_evidence_sha256"] = {
        "runner_pmu_interval_v9.elf": _sha256(args.elf),
        "runner_pmu_interval_v9.map": _sha256(args.map),
        "generated_runner.c": hashlib.sha256(runner_text.encode()).hexdigest(),
        "generated_vendor_u85.c": hashlib.sha256(vendor_text.encode()).hexdigest(),
        "generated_vendor_u85.o": _sha256(args.vendor_object),
        "preprocessed_runner.i": _sha256(args.preprocessed),
    }
    with open(args.manifest_out, "w") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
