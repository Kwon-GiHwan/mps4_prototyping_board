"""Pure functions: event sets, per-run validity, per-event verdicts, consistency checks, refusals with rule ids."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reference import driver_ids
INSTRUMENTATION_EVENTS = 2
BUILD_ID_PMEV = 0x504D4556
SLOTS = 8
REPEATS = 3
VERDICTS = ("COUNTED_NONZERO", "COUNTED_ZERO", "INCONSISTENT", "NOT_OBSERVED")
RULES = ("RULE_PING", "RULE_CAPABILITY", "RULE_MODE_NACK", "RULE_RUN_TRANSPORT",
         "RULE_RECORD_SCHEMA", "RULE_CODES_ECHO", "RULE_SET_COVERAGE")
VALIDITY_TERMS = ("rc_zero", "required_flags_ok", "cycle_valid", "cycle_progress", "seam_fired",
                  "mode_applied_2", "applied_count", "valid_mask_full", "codes_echo")


class Refusal(Exception):
    def __init__(self, rule, msg):
        assert rule in RULES; super().__init__(f"{rule}: {msg}"); self.rule = rule


def fail_rule(rule, msg): return Refusal(rule, msg)
def refusal_rule(exc): return exc.rule


def event_sets(ids=None):
    """Sets of 8 over the requested driver ids ascending (default: all 171 -> 22 sets, last has 3)."""
    known = driver_ids()
    if ids is None:
        ids = known
    unknown = sorted(set(ids) - set(known))
    if unknown:
        raise ValueError(f"not driver event ids: {unknown}")
    ids = sorted(set(ids))
    return [(i + 1, ids[i * SLOTS:(i + 1) * SLOTS]) for i in range((len(ids) + SLOTS - 1) // SLOTS)]


STATUS_CMD_END = 1 << 5
STATUS_FAULTS = (1 << 2) | (1 << 4) | (1 << 8) | (1 << 9)   # bus_status, cmd_parse_error, ecc_fault, branch_fault
FLAGS_COMPLETED = 0xD                                     # COMPLETED | OUTPUT_CHANGED | COARSE_WINDOW
KNOB_NOT_HONOURED = 0x7D                                  # runner rc when a knob read-back failed
MODEL_TERMS = ("vendor_rc_completed", "flags_completed", "stream_completed", "knobs_honoured")


def run_validity(rec, codes, mode="exact"):
    """rec: dict with run_rc, required_flags_ok, pmu(dict). Returns (valid, failed_terms).
    mode 'model' (step-2 amendment 2): completion replaces exact correctness."""
    p = rec["pmu"]; n = len(codes)
    if mode == "model":
        st = rec.get("seam_npu_status")
        completion = {
            "vendor_rc_completed": rec.get("vendor_rc") in (0, 2),
            "flags_completed": (rec.get("valid_flags", 0) & FLAGS_COMPLETED) == FLAGS_COMPLETED,
            "stream_completed": (st is not None and (st & STATUS_CMD_END) and not (st & STATUS_FAULTS)
                                 and rec.get("seam_npu_qread") == rec.get("cms_len")),
            "knobs_honoured": rec["run_rc"] != KNOB_NOT_HONOURED,   # mlek-baseline.md section 2
        }
    terms = {
        "rc_zero": rec["run_rc"] == 0,
        "required_flags_ok": bool(rec["required_flags_ok"]),
        "cycle_valid": p["npu_pmu_cycle_valid"] == 1,
        "cycle_progress": p.get("cycle_progress_observed", 0) == 1,   # amendment 6: a 0 window carries no count
        "seam_fired": rec.get("seam_fired") == 1,                       # amendment 7: read at the CPM seam, exactly once
        "mode_applied_2": p["instrumentation_mode_applied"] == INSTRUMENTATION_EVENTS,
        "applied_count": p["applied_event_count"] == n,
        "valid_mask_full": p["event_valid_mask"] == (1 << n) - 1,
        "codes_echo": all(p["event_codes"][i] == codes[i] for i in range(n)),
    }
    if mode == "model":
        for k in ("rc_zero", "required_flags_ok"):
            terms.pop(k)
        terms.update(completion)
    failed = [k for k in terms if not terms[k]]
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


def check_coverage(rows_by_ev, expected=None):
    got = set(rows_by_ev); want = set(driver_ids() if expected is None else expected)
    if got != want:
        raise fail_rule("RULE_SET_COVERAGE", f"covered {len(got)}/{len(want)}")
