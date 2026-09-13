"""X4 analysis -- contract in plan 2026-09-14 section 10. Reads results.jsonl (copied from the server).

Per (campaign, cell):
  gates   G1 artifact identity (vela sha, cc body sha == frozen)
          G2 base arm reproduces the frozen counters exactly (total, active, beats)
          G3 the REPS runs of every arm are vector-identical
          G4 the generated TA header carries the requested values
  outcome A: MEMORY_SERVICE_SENSITIVE | ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE | NOT_EVALUABLE
          B: BANDWIDTH_SENSITIVE | BANDWIDTH_INSENSITIVE | NOT_EVALUABLE  (+ A5_PREDICTION MET|NOT_MET)
Sensitivity = any level moves total cycles by >= 10 % of the base, or (campaign A) flips the
256->512 direction of the cell's workload.
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
R1 = ROOT / "docs/paper/raw_data_report/source_data/3_2_inference_time/R1_MEMORY_COUNTERS.csv"
CANON = ROOT / "docs/paper/raw_data_report/source_data/3_1_methodology/canonical_cells.csv"

RULE_BASE_MISMATCH = "RULE_X4_BASE_MISMATCH"
RULE_REPS_DIFFER = "RULE_X4_REPS_DIFFER"
RULE_TA_HEADER = "RULE_X4_TA_HEADER"
RULE_ARTIFACT = "RULE_X4_ARTIFACT"
RULES = (RULE_BASE_MISMATCH, RULE_REPS_DIFFER, RULE_TA_HEADER, RULE_ARTIFACT)
THRESH = 0.10
KEYS = ("npu_total_cycles", "npu_active_cycles", "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats",
        "axi0_rd_beats", "axi0_wr_beats", "axi1_rd_beats")


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def frozen_counters():
    exp = {}
    for r in csv.DictReader(open(R1)):
        exp.setdefault(r["cell_id"], {k: int(r[k]) for k in ("npu_total_cycles", "npu_active_cycles", "sram_rd_beats",
                                                             "sram_wr_beats", "ext_rd_beats", "ext_wr_beats")})
    for r in csv.DictReader(open(CANON)):
        if r["npu"] != "ethos-u85":
            exp[r["cell_id"]] = {"npu_total_cycles": int(r["canonical_cycles"]), "npu_active_cycles": int(r["npu_active_cycles"]),
                                 "axi0_rd_beats": int(r["axi0_rd_beats"]), "axi0_wr_beats": int(r["axi0_wr_beats"]),
                                 "axi1_rd_beats": int(r["axi1_rd_beats"])}
    return exp


def group(records):
    g = {}
    for r in records:
        if "measurement" not in r:
            continue
        g.setdefault((r["campaign"], r["cell_id"]), {}).setdefault(r["arm"], []).append(r)
    return g


def check_arm(runs, defines_expected=None):
    """G3 + G4 + G1 for one arm; returns the (identical) measurement vector."""
    vecs = [tuple(r["measurement"].get(k) for k in KEYS) for r in runs]
    if any(r["status"] != "SUCCESS" for r in runs) or len(set(vecs)) != 1:
        raise Refusal(RULE_REPS_DIFFER, "runs differ or failed: %s" % [r["status"] for r in runs])
    r0 = runs[0]
    for k, v in r0["defines"].items():
        if r0["ta_header"].get(k) != v:
            raise Refusal(RULE_TA_HEADER, "%s requested %s, header %s" % (k, v, r0["ta_header"].get(k)))
    a = r0["artifact"]
    if a["vela_sha256"] != a["frozen_vela_sha256"] or a["cc_body_sha256"] != a["frozen_cc_body_sha256"]:
        raise Refusal(RULE_ARTIFACT, "artifact differs from frozen")
    return r0["measurement"]


def evaluate_cell(campaign, cell_id, arms, frozen):
    try:
        base_arm = next(a for a, runs in arms.items() if runs[0]["is_base"])
        base = check_arm(arms[base_arm])
        exp = frozen.get(cell_id, {})
        bad = [k for k in exp if base.get(k) != exp[k]]
        if bad:
            raise Refusal(RULE_BASE_MISMATCH, "base differs from frozen on %s" % bad)
        levels = {}
        for arm, runs in arms.items():
            m = check_arm(runs)
            levels[arm] = {"total": m["npu_total_cycles"], "ratio_to_base": round(m["npu_total_cycles"] / base["npu_total_cycles"], 4),
                           "defines": runs[0]["defines"]}
    except Refusal as e:
        return {"campaign": campaign, "cell_id": cell_id, "outcome": "NOT_EVALUABLE", "rule": e.rule, "detail": str(e)}
    moved = any(abs(v["ratio_to_base"] - 1) >= THRESH for v in levels.values())
    if campaign == "A":
        outcome = "MEMORY_SERVICE_SENSITIVE" if moved else "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE"
    else:
        outcome = "BANDWIDTH_SENSITIVE" if moved else "BANDWIDTH_INSENSITIVE"
    res = {"campaign": campaign, "cell_id": cell_id, "outcome": outcome, "rule": "", "base_total": base["npu_total_cycles"],
           "levels": levels}
    if campaign == "B":
        r25 = next((v["ratio_to_base"] for v in levels.values() if v["defines"].get("EXT_BWCAP") == 25), None)
        r100 = next((v["ratio_to_base"] for v in levels.values() if v["defines"].get("EXT_BWCAP") == 100), None)
        res["A5_PREDICTION"] = "MET" if (r25 is not None and r25 >= 1.8 and r100 is not None and r100 <= 0.6) else "NOT_MET"
        res["A5_prediction_inputs"] = {"bwcap25_ratio": r25, "bwcap100_ratio": r100}
    return res


def direction_flip(results):
    """Campaign A extra: does the 256->512 direction of a workload change at any latency level?"""
    out = {}
    by = {(r["cell_id"].split("__")[0], r["cell_id"].rsplit("-", 1)[1]): r for r in results if r["campaign"] == "A" and r["outcome"] != "NOT_EVALUABLE"}
    for wl in {k[0] for k in by}:
        a, b = by.get((wl, "256")), by.get((wl, "512"))
        if not (a and b):
            continue
        base_dir = (b["base_total"] > a["base_total"]) - (b["base_total"] < a["base_total"])
        flips = []
        for arm, la in a["levels"].items():
            f = la["defines"]["EXT_RLATENCY"] / (250 if "256" in a["cell_id"] else 500)
            lb = next((v for v in b["levels"].values() if v["defines"]["EXT_RLATENCY"] / 500 == f), None)
            if lb:
                d = (lb["total"] > la["total"]) - (lb["total"] < la["total"])
                flips.append({"factor": f, "total_256": la["total"], "total_512": lb["total"], "direction": d, "flipped": d != base_dir})
        out[wl] = {"base_direction": base_dir, "levels": flips, "any_flip": any(x["flipped"] for x in flips)}
    return out


def main(path=HERE / "results.jsonl"):
    recs = [json.loads(l) for l in open(path)]
    frozen = frozen_counters(); results = []
    for (camp, cid), arms in sorted(group(recs).items()):
        results.append(evaluate_cell(camp, cid, arms, frozen))
    flips = direction_flip(results)
    for r in results:
        if r["campaign"] == "A" and r["outcome"] == "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE":
            wl = r["cell_id"].split("__")[0]
            if flips.get(wl, {}).get("any_flip"):
                r["outcome"] = "MEMORY_SERVICE_SENSITIVE"; r["sensitive_by"] = "direction_flip"
    json.dump({"cells": results, "direction_256_512": flips}, open(HERE / "x4_results.json", "w"), indent=1)
    for r in results:
        print(r["campaign"], r["cell_id"], r["outcome"], r.get("rule", ""), r.get("A5_PREDICTION", ""))
        for arm, v in sorted(r.get("levels", {}).items(), key=lambda kv: list(kv[1]["defines"].values())):
            print("   %-18s total=%-9d ratio=%.3f" % (arm, v["total"], v["ratio_to_base"]))
    for wl, f in flips.items():
        print("direction", wl, "base", f["base_direction"], "any_flip", f["any_flip"], [(x["factor"], x["direction"]) for x in f["levels"]])


if __name__ == "__main__":
    sys.exit(main())
