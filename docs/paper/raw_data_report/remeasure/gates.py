"""Evaluate gates G1-G5 of REMEASURE_CONTRACT.md over R1_RAW.json.

The gates were frozen before the data existed. Each is evaluated as a closed
predicate over 35 cells; a gate is PASS only at 35/35. G1-G4 failing means the
recovered memory counters must NOT be attached to the frozen cells: they would
describe a different build or a nondeterministic one.

Emits R1_GATE_REPORT.md, R1_MEMORY_COUNTERS.csv and R1_RESULTS.json.
"""
import csv, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
FROZEN = os.path.join(REPO, "docs", "paper", "analysis", "canonical_cells.csv")
RAW = os.path.join(HERE, "R1_RAW.json")
N = 35

MEM = ("SRAM_RD_DATA_BEAT_RECEIVED", "SRAM_WR_DATA_BEAT_WRITTEN",
       "EXT_RD_DATA_BEAT_RECEIVED", "EXT_WR_DATA_BEAT_WRITTEN")


def frozen_rows():
    with open(FROZEN) as fh:
        return {r["cell_id"]: r for r in csv.DictReader(fh)
                if r["npu"] == "ethos-u85"}


def counters(rep):
    return ((rep or {}).get("pmu") or {}).get("counters", {})


def evaluate(results, frozen):
    per, g = {}, {}

    def cellwise(name, fn):
        ok = {c["cell_id"]: bool(fn(c)) for c in results}
        per[name] = ok
        g[name] = {"passed": sum(ok.values()), "of": len(ok), "expected": N,
                   "verdict": "PASS" if sum(ok.values()) == N == len(ok) else "FAIL",
                   "failing_cells": sorted(k for k, v in ok.items() if not v)}

    cellwise("G1_artifact_reproduction",
             lambda c: c.get("build_ok") and not c.get("reproduction_gate_failed")
                       and all(c.get("reproduction_gate", {}).values()))

    def g2(c):
        f = frozen.get(c["cell_id"])
        v = counters(c["reps"][0] if c["reps"] else None).get("TOTAL")
        return f and v is not None and str(v) == f["canonical_cycles"]
    cellwise("G2_total_cycles_match_frozen", g2)

    def g3(c):
        f = frozen.get(c["cell_id"])
        v = counters(c["reps"][0] if c["reps"] else None).get("ACTIVE")
        return f and v is not None and str(v) == f["npu_active_cycles"]
    cellwise("G3_active_cycles_match_frozen", g3)

    def g4(c):
        if len(c.get("reps", [])) != 2:
            return False
        a, b = counters(c["reps"][0]), counters(c["reps"][1])
        return bool(a) and a == b and all(
            c["reps"][i]["status"] == "SUCCESS" for i in (0, 1))
    cellwise("G4_repetition_identical", g4)

    def g5(c):
        a = counters(c["reps"][0] if c["reps"] else None)
        return all(a.get(k) is not None for k in MEM)
    cellwise("G5_memory_counters_present", g5)

    return g, per


def main():
    results = json.load(open(RAW))
    frozen = frozen_rows()
    gates, per = evaluate(results, frozen)
    overall = "PASS" if all(v["verdict"] == "PASS" for v in gates.values()) else "FAIL"

    rows = []
    for c in sorted(results, key=lambda r: r["seq"]):
        a = counters(c["reps"][0] if c["reps"] else None)
        rows.append({
            "cell_id": c["cell_id"], "workload": c["model"],
            "platform": c["platform"], "mac_config": c["mac_config"],
            "memory_mode": c["memory_mode"],
            "sram_rd_beats": a.get("SRAM_RD_DATA_BEAT_RECEIVED", ""),
            "sram_wr_beats": a.get("SRAM_WR_DATA_BEAT_WRITTEN", ""),
            "ext_rd_beats": a.get("EXT_RD_DATA_BEAT_RECEIVED", ""),
            "ext_wr_beats": a.get("EXT_WR_DATA_BEAT_WRITTEN", ""),
            "npu_total_cycles": a.get("TOTAL", ""),
            "npu_active_cycles": a.get("ACTIVE", ""),
            "npu_idle_cycles": a.get("IDLE", ""),
            "counter_family": ((c["reps"][0] if c["reps"] else {}).get("pmu") or {}).get("generation", ""),
            "source": "REMEASUREMENT_R1",
        })
    csv_path = os.path.join(HERE, "R1_MEMORY_COUNTERS.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    json.dump({"gates": gates, "per_cell": per, "overall": overall,
               "cells_evaluated": len(results), "expected_cells": N},
              open(os.path.join(HERE, "R1_RESULTS.json"), "w"), indent=1)

    L = ["# R1 gate report", "",
         "Gates were frozen in `REMEASURE_CONTRACT.md` before this data existed.",
         "A gate is PASS only at %d/%d." % (N, N), "",
         "| gate | passed | verdict |", "| --- | ---: | --- |"]
    for k, v in gates.items():
        L.append("| `%s` | %d/%d | **%s** |" % (k, v["passed"], v["of"], v["verdict"]))
    L += ["", "```", "R1_GATES: %s" % overall, "```", ""]
    for k, v in gates.items():
        if v["failing_cells"]:
            L += ["**%s failing cells:**" % k, ""] + \
                 ["- `%s`" % c for c in v["failing_cells"]] + [""]
    if overall == "PASS":
        L += ["All five gates hold. The rebuild is byte-identical to the frozen",
              "anchor (G1); the cycle counters this run observes are the frozen",
              "values themselves (G2, G3), which is what licenses attaching the",
              "recovered memory counters to those same cells; the two repetitions",
              "agree exactly (G4); and all four U85 memory counters are present on",
              "every cell (G5).", "",
              "The loss was in the reader, not the measurement: `stage1.py` matched",
              "`AXI0_*`/`AXI1_*`, which the U85 runner never emits. The same UART",
              "block re-read with a parser that discovers the emitted set yields",
              "`SRAM_*`/`EXT_*` on all 35 cells.", ""]
    else:
        L += ["At least one gate failed. Per the contract, the recovered memory",
              "counters are NOT attached to the frozen cells.", ""]
    open(os.path.join(HERE, "R1_GATE_REPORT.md"), "w").write("\n".join(L))

    print("R1_GATES: %s" % overall)
    for k, v in gates.items():
        print("  %-34s %2d/%-2d %s" % (k, v["passed"], v["of"], v["verdict"]))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
