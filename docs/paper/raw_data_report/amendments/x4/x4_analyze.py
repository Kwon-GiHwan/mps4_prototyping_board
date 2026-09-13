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
    """Campaign D is evaluated like A (has its own base arms). C and E are descriptive: their arms are
    attached to the A/B base of the same cell for the gates, and summarised separately."""
    g = {}
    for r in records:
        if "measurement" not in r:
            continue
        camp = {"C": "A", "E": "B"}.get(r["campaign"], r["campaign"])
        g.setdefault((camp, r["cell_id"]), {}).setdefault(r["arm"], []).append(r)
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
    if campaign in ("A", "D"):
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


BASE_LAT = {"256": 250, "512": 500, "1024": 500, "2048": 500}
PAIRS = {"A": ("256", "512"), "D": ("1024", "2048")}


def latency_only(levels):
    """Only arms that vary EXT latency alone (excludes the campaign-C full-profile arms)."""
    return {a: v for a, v in levels.items() if set(v["defines"]) <= {"EXT_RLATENCY", "EXT_WLATENCY"}}


def direction_flip(results, campaign="A"):
    """Does the lower->higher MAC direction of a workload change at any common latency level?"""
    out = {}
    lo, hi = PAIRS[campaign]
    by = {(r["cell_id"].split("__")[0], r["cell_id"].rsplit("-", 1)[1]): r for r in results if r["campaign"] == campaign and r["outcome"] != "NOT_EVALUABLE"}
    for wl in {k[0] for k in by}:
        a, b = by.get((wl, lo)), by.get((wl, hi))
        if not (a and b):
            continue
        base_dir = (b["base_total"] > a["base_total"]) - (b["base_total"] < a["base_total"])
        flips = []
        for arm, la in latency_only(a["levels"]).items():
            f = la["defines"]["EXT_RLATENCY"] / BASE_LAT[lo]
            lb = next((v for v in latency_only(b["levels"]).values() if v["defines"]["EXT_RLATENCY"] / BASE_LAT[hi] == f), None)
            if lb:
                d = (lb["total"] > la["total"]) - (lb["total"] < la["total"])
                flips.append({"factor": f, "total_lo": la["total"], "total_hi": lb["total"], "direction": d, "flipped": d != base_dir})
        out[wl] = {"pair": (lo, hi), "base_direction": base_dir, "levels": flips, "any_flip": any(x["flipped"] for x in flips)}
    return out


def profile_swap_table(results):
    """Campaign C: 2x2 of artifact x full TA profile for RNNoise 256/512 (descriptive only)."""
    r256 = next((r for r in results if r["cell_id"].endswith("u85-256") and "rnnoise" in r["cell_id"] and r["campaign"] == "A"), None)
    r512 = next((r for r in results if r["cell_id"].endswith("u85-512") and "rnnoise" in r["cell_id"] and r["campaign"] == "A"), None)
    if not (r256 and r512) or "levels" not in r256 or "levels" not in r512:
        return None
    return {"artifact_256": {"low_profile(base)": r256["base_total"], "mid_profile_full": r256["levels"].get("ta_mid_full", {}).get("total")},
            "artifact_512": {"mid_profile(base)": r512["base_total"], "low_profile_full": r512["levels"].get("ta_low_full", {}).get("total")}}


def u55_2x2(results):
    """Campaign B+E: RNNoise U55 256, bandwidth cap x EXT latency (descriptive only)."""
    r = next((r for r in results if r["campaign"] == "B" and "levels" in r), None)
    if not r:
        return None
    def tot(bw, lat):
        for v in r["levels"].values():
            d = v["defines"]
            if d.get("EXT_BWCAP") == bw and d.get("EXT_RLATENCY", 64) == lat:
                return v["total"]
    return {"bwcap50_lat64(base)": tot(50, 64), "bwcap200_lat64": tot(200, 64), "bwcap50_lat16": tot(50, 16), "bwcap200_lat16": tot(200, 16)}


def main(path=HERE / "results.jsonl"):
    recs = [json.loads(l) for l in open(path)]
    frozen = frozen_counters(); results = []
    for (camp, cid), arms in sorted(group(recs).items()):
        results.append(evaluate_cell(camp, cid, arms, frozen))
    flips = {c: direction_flip(results, c) for c in ("A", "D")}
    for r in results:
        if r["campaign"] in flips and r["outcome"] == "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE":
            wl = r["cell_id"].split("__")[0]
            if flips[r["campaign"]].get(wl, {}).get("any_flip"):
                r["outcome"] = "MEMORY_SERVICE_SENSITIVE"; r["sensitive_by"] = "direction_flip"
    json.dump({"cells": results, "direction_flip": flips, "campaign_C_profile_swap": profile_swap_table(results),
               "campaign_E_u55_2x2": u55_2x2(results)}, open(HERE / "x4_results.json", "w"), indent=1)
    for r in results:
        print(r["campaign"], r["cell_id"], r["outcome"], r.get("rule", ""), r.get("A5_PREDICTION", ""))
        for arm, v in sorted(r.get("levels", {}).items(), key=lambda kv: list(kv[1]["defines"].values())):
            print("   %-18s total=%-9d ratio=%.3f" % (arm, v["total"], v["ratio_to_base"]))
    for c, fl in flips.items():
        for wl, f in fl.items():
            print("direction", c, wl, f["pair"], "base", f["base_direction"], "any_flip", f["any_flip"], [(x["factor"], x["direction"]) for x in f["levels"]])
    print("campaign C", profile_swap_table(results)); print("campaign E", u55_2x2(results))


if __name__ == "__main__":
    sys.exit(main())
