"""R1 -- recover the U85 whole-model memory counters that stage1's parser dropped.

stage1.py hardcoded AXI0_*/AXI1_* counter names. The U85 runner emits
SRAM_*/EXT_* instead, so those fields recorded None on all 35 U85 cells and the
raw UART was discarded with the workspace. The values were never wrong; they
were never read.

This harness does not re-implement stage1. It IMPORTS it, so the build, the
artifact-reproduction gate and the FVP invocation are the same code, not code
"modelled on" it. Two things differ, both deliberate:

  1. the retained UART is parsed with pmuparse.parse_profile(), which discovers
     the emitted counter set instead of assuming a generation's names;
  2. the UART file is written outside the workspace and kept, so the same loss
     cannot recur.

Cells, build arguments and expected artifact hashes come from the frozen
anchor.json. Nothing frozen is written. Output goes to OUTDIR only.
"""
import json, os, shutil, sys, time

sys.path.insert(0, "/tmp/xqbin")
import stage1, pmuparse

ANCHOR = "/tmp/xqbin/anchor.json"
OUTDIR = "/tmp/r1out"
UARTD  = os.path.join(OUTDIR, "uart")
REPS   = 2
FREE_GATE = 1 << 30


def u85_cells():
    cells = [c for c in json.load(open(ANCHOR))["canonical_order"]
             if c["npu"] == "ethos-u85"]
    if len(cells) != 35:
        raise SystemExit("expected 35 U85 cells in the anchor, found %d" % len(cells))
    return cells


def measure(cell, axf, tag):
    """One FVP run. UART is kept; the counter set is discovered, not assumed."""
    uart = os.path.join(UARTD, "%s.%s.uart.txt" % (cell["cell_id"], tag))
    log  = os.path.join(UARTD, "%s.%s.fvp.log" % (cell["cell_id"], tag))
    r = stage1.run_once(cell, axf, uart, log)
    rec = {"tag": tag, "status": r["status"],
           "inference_count_line": r["inference_count_line"],
           "wall_clock_s": r["wall_clock_s"],
           "survivors_after_cleanup": r["survivors_after_cleanup"],
           "stage1_parser": {k: r[k] for k in
                             ("npu_total_cycles", "npu_active_cycles", "npu_idle_cycles",
                              "axi0_rd_beats", "axi0_wr_beats", "axi1_rd_beats")},
           "uart_path": uart, "uart_sha256": stage1.sha256(uart)}
    try:
        p = pmuparse.parse_profile(open(uart, errors="replace").read())
    except pmuparse.PmuParseError as e:
        rec["pmu"] = None
        rec["pmu_parse_error"] = str(e)
        return rec
    rec["pmu"] = {
        "event_set": p["event_set"],
        "generation": pmuparse.classify_generation(p),
        "total_identity_holds": pmuparse.total_identity_holds(p),
        "counters": {k: v["value"] for k, v in p["events"].items()},
        "emitted_names": {k: v["emitted_name"] for k, v in p["events"].items()},
        "units": {k: v["unit"] for k, v in p["events"].items()},
    }
    return rec


def main():
    anchor = json.load(open(ANCHOR))
    os.makedirs(UARTD, exist_ok=True)
    dest = os.path.join(OUTDIR, "R1_RAW.json")
    results = json.load(open(dest)) if os.path.exists(dest) else []
    done = {r["cell_id"] for r in results}

    for i, cell in enumerate(u85_cells(), 1):
        if cell["cell_id"] in done:
            continue
        if stage1.free_bytes() < FREE_GATE:
            print("FREE_SPACE_GATE at %s" % cell["cell_id"], flush=True)
            return 2
        t0 = time.monotonic()
        print("[%2d/35] %s" % (i, cell["cell_id"]), flush=True)

        b = stage1.build(cell, anchor)
        rec = {"seq": cell["seq"], "cell_id": cell["cell_id"],
               "model": cell["model"], "platform": cell["platform"],
               "mac_config": cell["mac_config"],
               "system_config": cell["system_config"],
               "memory_mode": cell["memory_mode"],
               "npu_config_id": cell["npu_config_id"], "fvp": cell["fvp"]}
        if not b.get("ok"):
            rec["build_ok"] = False
            rec["build_stage"] = b.get("stage")
            rec["build_log"] = b.get("log", "")
            rec["reps"] = []
            results.append(rec)
            shutil.rmtree(b.get("ws", "/nonexistent"), ignore_errors=True)
            json.dump(results, open(dest, "w"), indent=1)
            continue

        checks, bad = stage1.gate(cell, b)
        rec["build_ok"] = True
        rec["reproduction_gate"] = checks            # G1
        rec["reproduction_gate_failed"] = bad
        rec["artifact_identity"] = {
            "model_sha256": cell["model_sha256"],
            "vela_sha256": b["vela_sha256"],
            "generated_cc_body_sha256": b["cc_body_sha256"],
            "axf_sha256": b["axf_sha256"]}
        rec["timing_adapter_cache"] = b["timing_adapter_cache"]
        rec["embedded_build_stamp"] = b["embedded_build_stamp"]
        rec["frozen_expected"] = {
            "vela_sha256": cell["formal_vela_sha256"],
            "generated_cc_body_sha256": cell["FORMAL_GENERATED_CC_BODY_SHA256"],
            "axf_sha256": cell["FORMAL_REFERENCE_AXF_SHA256"]}

        rec["reps"] = [measure(cell, b["axf"], "R%d" % r) for r in range(1, REPS + 1)]
        for m in rec["reps"]:
            c = (m.get("pmu") or {}).get("counters", {})
            print("    %s %-8s TOTAL=%-10s SRAM_RD=%-10s EXT_RD=%-10s %s"
                  % (m["tag"], m["status"], c.get("TOTAL"), c.get("SRAM_RD_DATA_BEAT_RECEIVED"),
                     c.get("EXT_RD_DATA_BEAT_RECEIVED"),
                     (m.get("pmu") or {}).get("generation")), flush=True)

        rec["elapsed_s"] = round(time.monotonic() - t0, 1)
        results.append(rec)
        shutil.rmtree(b["ws"], ignore_errors=True)
        json.dump(results, open(dest, "w"), indent=1)

    print("R1_COMPLETE %d cells" % len(results), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
