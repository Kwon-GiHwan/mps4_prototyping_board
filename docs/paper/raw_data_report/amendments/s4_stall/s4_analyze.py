"""S4 analysis -- contract in plan 2026-09-14 section 11. Reads results.jsonl (copied from the server).

Two passes per cell (plan section 11, corrected): A = MAC_ACTIVE, MAC_STALLED_BY_W, MAC_STALLED_BY_IB;
B = MAC_ACTIVE, AO_STALLED_BY_OB, NPU_IDLE.
Per cell:
  gates   G1 artifact identity (vela sha, cc body sha == frozen; the AXF differs by design)
          G2 stock counters (total, active, SRAM/EXT beats) exactly equal the R1 values, in both passes
          G3 the REPS runs of each pass are vector-identical (stock + S4 counters)
          G5 MAC_ACTIVE identical across the two passes
  outcome RAW_PRESERVED | NOT_EVALUABLE      (manager review 2: while the event semantics are unverified the
          stall events are NOT summed and no share-based verdict is produced; per-event raw counts and
          per-event ratios to TOTAL are recorded as descriptive values only)
          G6 overflow status word must be 0 for the S4 counters.
Every result carries semantics = SEMANTICS_UNVERIFIED until the Arm TRM definitions are confirmed.
The S4 window (enable before HAL begin .. disable after HAL end) is wider than the stock TOTAL window
and is never equated with it; derived_idle (TOTAL - ACTIVE) and the NPU_IDLE event are kept apart.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE_G2 = "RULE_S4_STOCK_COUNTERS_DIFFER"
RULE_G3 = "RULE_S4_REPS_DIFFER"
RULE_G1 = "RULE_S4_ARTIFACT"
RULE_MISSING = "RULE_S4_COUNTER_MISSING"
RULE_G5 = "RULE_S4_PASSES_DISAGREE"
RULE_G6 = "RULE_S4_OVERFLOW"
RULES = (RULE_G1, RULE_G2, RULE_G3, RULE_MISSING, RULE_G5, RULE_G6)
OUTCOMES = ("RAW_PRESERVED", "NOT_EVALUABLE")
STALL = ("MAC_STALLED_BY_W", "MAC_STALLED_BY_IB", "AO_STALLED_BY_OB")


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


PASS_EVENTS = {"A": ("MAC_ACTIVE", "MAC_STALLED_BY_W", "MAC_STALLED_BY_IB"), "B": ("MAC_ACTIVE", "AO_STALLED_BY_OB", "NPU_IDLE")}


def check_pass(runs, pass_id):
    if any(r["status"] != "SUCCESS" for r in runs):
        raise Refusal(RULE_G3, "pass %s: a run did not succeed" % pass_id)
    vecs = {json.dumps([r["stock_counters"], r["s4_counters"]], sort_keys=True) for r in runs}
    if len(vecs) != 1:
        raise Refusal(RULE_G3, "pass %s: runs differ" % pass_id)
    r0 = runs[0]; a = r0["artifact"]
    if a["vela_sha256"] != a["frozen_vela_sha256"] or a["cc_body_sha256"] != a["frozen_cc_body_sha256"]:
        raise Refusal(RULE_G1, "pass %s: artifact differs from frozen" % pass_id)
    if not r0["G2_stock_counters_match"] or not all(r0["G2_stock_counters_match"].values()):
        raise Refusal(RULE_G2, "pass %s: stock counters differ from R1: %s" % (pass_id, r0["G2_stock_counters_match"]))
    s4 = r0["s4_counters"]
    if any(s4.get(k) is None for k in PASS_EVENTS[pass_id]):
        raise Refusal(RULE_MISSING, "pass %s: S4 counter missing: %s" % (pass_id, s4))
    return r0


def evaluate_cell(cell_id, runs_by_pass):
    """runs_by_pass: {"A": [runs], "B": [runs]}"""
    try:
        if set(runs_by_pass) != {"A", "B"}:
            raise Refusal(RULE_MISSING, "passes present: %s" % sorted(runs_by_pass))
        ra = check_pass(runs_by_pass["A"], "A"); rb = check_pass(runs_by_pass["B"], "B")
        if ra["s4_counters"]["MAC_ACTIVE"] != rb["s4_counters"]["MAC_ACTIVE"]:
            raise Refusal(RULE_G5, "MAC_ACTIVE differs across passes: %s vs %s" % (ra["s4_counters"]["MAC_ACTIVE"], rb["s4_counters"]["MAC_ACTIVE"]))
        for r, pid in ((ra, "A"), (rb, "B")):
            ovs = r["s4_counters"].get("OVS")
            if ovs is None or (ovs & 0xE0):  # bits 5-7 = event counters 5-7
                raise Refusal(RULE_G6, "pass %s: overflow status %s" % (pid, ovs))
        total = ra["stock_counters"]["npu_total_cycles"]
        s4 = {"MAC_ACTIVE": ra["s4_counters"]["MAC_ACTIVE"], "MAC_STALLED_BY_W": ra["s4_counters"]["MAC_STALLED_BY_W"],
              "MAC_STALLED_BY_IB": ra["s4_counters"]["MAC_STALLED_BY_IB"], "AO_STALLED_BY_OB": rb["s4_counters"]["AO_STALLED_BY_OB"],
              "NPU_IDLE": rb["s4_counters"]["NPU_IDLE"]}
    except Refusal as e:
        return {"cell_id": cell_id, "outcome": "NOT_EVALUABLE", "rule": e.rule, "detail": str(e), "semantics": "SEMANTICS_UNVERIFIED"}
    hal_idle = ra["stock_counters"].get("npu_idle_cycles")
    return {"cell_id": cell_id, "outcome": "RAW_PRESERVED", "rule": "", "total_stock_window": total,
            "per_event_ratio_to_total_descriptive": {k: round(v / total, 4) for k, v in s4.items()},
            "npu_idle_event": s4["NPU_IDLE"], "derived_idle_stock": hal_idle, "counters": s4,
            "window": "S4: enabled before HAL begin, disabled after HAL end (wider than stock TOTAL)",
            "semantics": "SEMANTICS_UNVERIFIED"}


def main(path=HERE / "results.jsonl"):
    recs = [json.loads(l) for l in open(path)]
    by = {}
    for r in recs:
        if "stock_counters" in r:
            by.setdefault(r["cell_id"], {}).setdefault(r.get("pass", "A"), []).append(r)
    results = [evaluate_cell(c, runs) for c, runs in sorted(by.items())]
    json.dump(results, open(HERE / "s4_results.json", "w"), indent=1)
    for r in results:
        print(r["cell_id"], r["outcome"], r.get("rule", ""), r.get("counters", ""), r.get("per_event_ratio_to_total_descriptive", ""))


if __name__ == "__main__":
    sys.exit(main())
