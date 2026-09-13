"""S4 analysis -- contract in plan 2026-09-14 section 11. Reads results.jsonl (copied from the server).

Per cell:
  gates   G1 artifact identity (vela sha, cc body sha == frozen; the AXF differs by design)
          G2 stock counters (total, active, SRAM/EXT beats) exactly equal the R1 values
          G3 the REPS runs are vector-identical (stock + S4 counters)
  metric  stall_share = (MAC_STALLED_BY_W + MAC_STALLED_BY_IB + AO_STALLED_BY_OB) / total   (upper bound: events may overlap)
          mac_active_share = MAC_ACTIVE / total
  outcome MEMORY_WAIT_DOMINANT (>= 0.30) | MEMORY_WAIT_PRESENT (0.05 .. 0.30) | MEMORY_WAIT_NEGLIGIBLE (< 0.05) | NOT_EVALUABLE
Every result carries semantics = SEMANTICS_UNVERIFIED until the Arm TRM definitions are confirmed.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE_G2 = "RULE_S4_STOCK_COUNTERS_DIFFER"
RULE_G3 = "RULE_S4_REPS_DIFFER"
RULE_G1 = "RULE_S4_ARTIFACT"
RULE_MISSING = "RULE_S4_COUNTER_MISSING"
RULES = (RULE_G1, RULE_G2, RULE_G3, RULE_MISSING)
OUTCOMES = ("MEMORY_WAIT_DOMINANT", "MEMORY_WAIT_PRESENT", "MEMORY_WAIT_NEGLIGIBLE", "NOT_EVALUABLE")
STALL = ("MAC_STALLED_BY_W", "MAC_STALLED_BY_IB", "AO_STALLED_BY_OB")


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def classify(share):
    if share >= 0.30:
        return "MEMORY_WAIT_DOMINANT"
    if share >= 0.05:
        return "MEMORY_WAIT_PRESENT"
    return "MEMORY_WAIT_NEGLIGIBLE"


def evaluate_cell(cell_id, runs):
    try:
        if any(r["status"] != "SUCCESS" for r in runs):
            raise Refusal(RULE_G3, "a run did not succeed")
        vecs = {json.dumps([r["stock_counters"], r["s4_counters"]], sort_keys=True) for r in runs}
        if len(vecs) != 1:
            raise Refusal(RULE_G3, "runs differ")
        r0 = runs[0]; a = r0["artifact"]
        if a["vela_sha256"] != a["frozen_vela_sha256"] or a["cc_body_sha256"] != a["frozen_cc_body_sha256"]:
            raise Refusal(RULE_G1, "artifact differs from frozen")
        if not r0["G2_stock_counters_match"] or not all(r0["G2_stock_counters_match"].values()):
            raise Refusal(RULE_G2, "stock counters differ from R1: %s" % r0["G2_stock_counters_match"])
        s4 = r0["s4_counters"]
        if any(s4.get(k) is None for k in STALL + ("MAC_ACTIVE",)):
            raise Refusal(RULE_MISSING, "S4 counter missing: %s" % s4)
        total = r0["stock_counters"]["npu_total_cycles"]
        stall = sum(s4[k] for k in STALL)
    except Refusal as e:
        return {"cell_id": cell_id, "outcome": "NOT_EVALUABLE", "rule": e.rule, "detail": str(e), "semantics": "SEMANTICS_UNVERIFIED"}
    share = stall / total
    return {"cell_id": cell_id, "outcome": classify(share), "rule": "", "total": total, "stall_sum": stall,
            "stall_share_upper_bound": round(share, 4), "mac_active_share": round(s4["MAC_ACTIVE"] / total, 4),
            "counters": s4, "semantics": "SEMANTICS_UNVERIFIED"}


def main(path=HERE / "results.jsonl"):
    recs = [json.loads(l) for l in open(path)]
    by = {}
    for r in recs:
        if "stock_counters" in r:
            by.setdefault(r["cell_id"], []).append(r)
    results = [evaluate_cell(c, runs) for c, runs in sorted(by.items())]
    json.dump(results, open(HERE / "s4_results.json", "w"), indent=1)
    for r in results:
        print(r["cell_id"], r["outcome"], r.get("rule", ""), "stall_share<=", r.get("stall_share_upper_bound"),
              "mac_active", r.get("mac_active_share"), r.get("counters", ""))


if __name__ == "__main__":
    sys.exit(main())
