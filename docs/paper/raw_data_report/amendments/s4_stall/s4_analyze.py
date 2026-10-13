"""S4 analysis -- contract in plan 2026-09-14 section 11. Reads results.jsonl (copied from the server).

Two passes per cell (plan section 11, corrected): A = MAC_ACTIVE, MAC_STALLED_BY_W, MAC_STALLED_BY_IB;
B = MAC_ACTIVE, AO_STALLED_BY_OB, NPU_IDLE.
Per cell:
  gates   G1 artifact identity (vela sha, cc body sha == frozen; the AXF differs by design)
          G2 stock counters (total, active, SRAM/EXT beats) exactly equal the R1 values, in both passes
          G3 the REPS runs of each pass are vector-identical (stock + S4 counters)
          G5 MAC_ACTIVE identical across the two passes
  outcome RAW_PRESERVED | NOT_EVALUABLE      (manager reviews 2-3: while the event semantics are unverified the
          stall events are NOT summed, NO ratio to TOTAL is produced (different window), and only the
          per-event raw counts are preserved)
          G6 overflow status word must be 0 for the S4 counters.
          G7 UART_NON_S4_EQ: the UART of passes A and B, with the "NPU S4 " lines removed, must be byte-identical
             to the UART of the unpatched clean pass (same cell, same repetition). This is a log-identity check;
             it is NOT an output-tensor equivalence check (manager review 4). Every result therefore carries
             output_tensor_equivalence = NOT_TESTED and event_semantics = SEMANTICS_UNVERIFIED.
Purpose (manager review 4): exploratory raw-value collection of PMU events whose semantics are unverified.
No summing, no utilisation, no bottleneck attribution.
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
RULE_G7 = "RULE_S4_UART_NON_S4_EQ_FAILED"
RULES = (RULE_G1, RULE_G2, RULE_G3, RULE_MISSING, RULE_G5, RULE_G6, RULE_G7)
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


def strip_s4(txt):
    return "\n".join(l for l in txt.split("\n") if not l.startswith("NPU S4 "))


def uart_of(run):
    p = run.get("uart_file")
    if p and Path(p).exists():
        return Path(p).read_text()
    local = HERE / "uart" / Path(p).name if p else None
    return local.read_text() if local and local.exists() else run.get("uart_text")


def check_clean_identity(runs_by_pass):
    clean = runs_by_pass["clean"]
    for pid in ("A", "B"):
        for rc, rp in zip(clean, runs_by_pass[pid]):
            uc, up = uart_of(rc), uart_of(rp)
            if uc is None or up is None:
                raise Refusal(RULE_G7, "pass %s: UART text unavailable" % pid)
            if strip_s4(up) != uc:
                raise Refusal(RULE_G7, "pass %s rep %s: UART differs from clean beyond the S4 lines" % (pid, rp.get("rep")))


def evaluate_cell(cell_id, runs_by_pass):
    """runs_by_pass: {"clean": [runs], "A": [runs], "B": [runs]}"""
    try:
        if set(runs_by_pass) != {"clean", "A", "B"}:
            raise Refusal(RULE_MISSING, "passes present: %s" % sorted(runs_by_pass))
        if any(r["status"] != "SUCCESS" for r in runs_by_pass["clean"]):
            raise Refusal(RULE_G3, "clean: a run did not succeed")
        ra = check_pass(runs_by_pass["A"], "A"); rb = check_pass(runs_by_pass["B"], "B")
        check_clean_identity(runs_by_pass)
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
        return {"cell_id": cell_id, "outcome": "NOT_EVALUABLE", "rule": e.rule, "detail": str(e),
                "output_tensor_equivalence": "NOT_TESTED", "event_semantics": "SEMANTICS_UNVERIFIED", "semantics": "SEMANTICS_UNVERIFIED"}
    hal_idle = ra["stock_counters"].get("npu_idle_cycles")
    return {"cell_id": cell_id, "outcome": "RAW_PRESERVED", "rule": "", "total_stock_window": total,
            "npu_idle_event": s4["NPU_IDLE"], "derived_idle_stock": hal_idle, "counters": s4,
            "window": "S4: enabled before HAL begin, disabled after HAL end (wider than stock TOTAL)",
            "G7": "UART_NON_S4_EQ", "output_tensor_equivalence": "NOT_TESTED", "event_semantics": "SEMANTICS_UNVERIFIED",
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
        print(r["cell_id"], r["outcome"], r.get("rule", ""), r.get("detail", ""), r.get("counters", ""))


if __name__ == "__main__":
    sys.exit(main())
