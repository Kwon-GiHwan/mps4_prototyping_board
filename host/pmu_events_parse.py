"""Tier B: event sets, per-run validity, per-event verdicts, consistency checks, refusals.
Pure functions. Contract: docs/superpowers/specs/2026-09-23-pmu-events-tier-b-contract.md (+ amendment 1).
"""
import json, pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
INSTRUMENTATION_EVENTS = 2
BUILD_ID_PMEV = 0x504D4556
SLOTS = 8
REPEATS = 3
VERDICTS = ("COUNTED_NONZERO", "COUNTED_ZERO", "INCONSISTENT", "NOT_OBSERVED")
RULES = ("RULE_PING", "RULE_CAPABILITY", "RULE_MODE_NACK", "RULE_RUN_TRANSPORT",
         "RULE_RECORD_SCHEMA", "RULE_CODES_ECHO", "RULE_SET_COVERAGE")
VALIDITY_TERMS = ("rc_zero", "required_flags_ok", "cycle_valid", "mode_applied_2",
                  "applied_count", "valid_mask_full", "codes_echo")


class Refusal(Exception):
    def __init__(self, rule, msg):
        assert rule in RULES; super().__init__(f"{rule}: {msg}"); self.rule = rule


def fail_rule(rule, msg): return Refusal(rule, msg)
def refusal_rule(exc): return exc.rule


def driver_ids():
    d = json.loads((REPO / "docs/ethos_u85_pmu_sources/driver_events_171.json").read_text())
    return {int(v): n for v, n in d}


def trm_ids():
    return {int(v) for v, _, _ in json.loads((REPO / "docs/ethos_u85_pmu_sources/trm_events_110.json").read_text())}


def event_sets():
    """22 sets: (set_id, [codes]) over the 171 driver ids ascending; last set has 3."""
    ids = sorted(driver_ids())
    return [(i + 1, ids[i * SLOTS:(i + 1) * SLOTS]) for i in range((len(ids) + SLOTS - 1) // SLOTS)]


def run_validity(rec, codes):
    """rec: dict with run_rc, required_flags_ok, pmu(dict). Returns (valid, failed_terms)."""
    p = rec["pmu"]; n = len(codes)
    terms = {
        "rc_zero": rec["run_rc"] == 0,
        "required_flags_ok": bool(rec["required_flags_ok"]),
        "cycle_valid": p["npu_pmu_cycle_valid"] == 1,
        "mode_applied_2": p["instrumentation_mode_applied"] == INSTRUMENTATION_EVENTS,
        "applied_count": p["applied_event_count"] == n,
        "valid_mask_full": p["event_valid_mask"] == (1 << n) - 1,
        "codes_echo": all(p["event_codes"][i] == codes[i] for i in range(n)),
    }
    failed = [k for k in VALIDITY_TERMS if not terms[k]]
    return (not failed), failed


def verdict(values):
    """values: list of per-repeat event_value or None (invalid run)."""
    ok = [v for v in values if v is not None]
    if len(ok) < REPEATS: return "NOT_OBSERVED"
    if all(v > 0 for v in ok): return "COUNTED_NONZERO"
    if all(v == 0 for v in ok): return "COUNTED_ZERO"
    return "INCONSISTENT"


def consistency(rows):
    """rows: per-run dicts with ev_type, event_value, window_cycles (None if invalid)."""
    out = {"CYCLE_EVENT_VS_PMCCNTR": [], "NPU_ACTIVE_LE_CYCLE": []}
    for r in rows:
        if r["event_value"] is None or r["window_cycles"] is None: continue
        if r["ev_type"] == 17:
            w = r["window_cycles"]
            out["CYCLE_EVENT_VS_PMCCNTR"].append("PASS" if w and abs(r["event_value"] - w) / w <= 0.01 else "FAIL")
        if r["ev_type"] == 35:
            out["NPU_ACTIVE_LE_CYCLE"].append("PASS" if r["event_value"] <= r["window_cycles"] else "FAIL")
    return {k: ("UNPROVEN" if not v else ("PASS" if all(x == "PASS" for x in v) else "FAIL")) for k, v in out.items()}


def check_coverage(rows_by_ev):
    got = set(rows_by_ev); want = set(driver_ids())
    if got != want:
        raise fail_rule("RULE_SET_COVERAGE", f"covered {len(got)}/{len(want)}")
