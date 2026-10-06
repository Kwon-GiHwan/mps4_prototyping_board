import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import pmu_events_parse as E


def rec(codes, values=None, **over):
    n = len(codes); values = values or [1] * n
    pmu = dict(npu_pmu_cycle_valid=1, cycle_progress_observed=1, instrumentation_mode_applied=2, applied_event_count=n,
               event_valid_mask=(1 << n) - 1, event_codes=list(codes) + [None] * (8 - n),
               event_values=list(values) + [None] * (8 - n), npu_pmu_window_cycles=1000)
    pmu.update({k: v for k, v in over.items() if k in pmu})
    r = dict(run_rc=0, required_flags_ok=True, pmu=pmu, seam_fired=1, golden_ok=True)
    r.update({k: v for k, v in over.items() if k in r})
    return r


class Sets(unittest.TestCase):
    def test_22_sets_cover_171_once(self):
        s = E.event_sets(); self.assertEqual(len(s), 22)
        flat = [c for _, cs in s for c in cs]
        self.assertEqual(len(flat), 171); self.assertEqual(len(set(flat)), 171)
        self.assertEqual(len(s[-1][1]), 3); self.assertEqual(s[0][0], 1)


class Validity(unittest.TestCase):
    def test_green(self): self.assertEqual(E.run_validity(rec([17, 35]), [17, 35]), (True, []))
    def test_each_term_reachable(self):
        c = [17, 35]; tripped = set()
        for term, r in {
            "rc_zero": rec(c, run_rc=3), "required_flags_ok": rec(c, required_flags_ok=False),
            "cycle_valid": rec(c, npu_pmu_cycle_valid=0), "cycle_progress": rec(c, cycle_progress_observed=0),
            "seam_fired": rec(c, seam_fired=0), "golden_ok": rec(c, golden_ok=False), "mode_applied_2": rec(c, instrumentation_mode_applied=1),
            "applied_count": rec(c, applied_event_count=1), "valid_mask_full": rec(c, event_valid_mask=1),
            "codes_echo": rec([17, 36]),
        }.items():
            ok, failed = E.run_validity(r, c); self.assertFalse(ok); self.assertIn(term, failed); tripped.add(term)
        self.assertEqual(tripped, set(E.VALIDITY_TERMS))


class Verdicts(unittest.TestCase):
    def test_closed_set(self):
        self.assertEqual(E.verdict([5, 6, 7]), "COUNTED_NONZERO")
        self.assertEqual(E.verdict([0, 0, 0]), "COUNTED_ZERO")
        self.assertEqual(E.verdict([0, 3, 0]), "INCONSISTENT")
        self.assertEqual(E.verdict([1, None, 1]), "NOT_OBSERVED")
        self.assertEqual(set(E.VERDICTS), {"COUNTED_NONZERO", "COUNTED_ZERO", "INCONSISTENT", "NOT_OBSERVED"})


class Consistency(unittest.TestCase):
    def test_three_states(self):
        rows = [dict(ev_type=17, event_value=1000, window_cycles=1005), dict(ev_type=35, event_value=900, window_cycles=1005)]
        self.assertEqual(E.consistency(rows), {"CYCLE_EVENT_VS_PMCCNTR": "PASS", "NPU_ACTIVE_LE_CYCLE": "PASS"})
        rows = [dict(ev_type=17, event_value=500, window_cycles=1000), dict(ev_type=35, event_value=2000, window_cycles=1000)]
        self.assertEqual(E.consistency(rows), {"CYCLE_EVENT_VS_PMCCNTR": "FAIL", "NPU_ACTIVE_LE_CYCLE": "FAIL"})
        self.assertEqual(E.consistency([]), {"CYCLE_EVENT_VS_PMCCNTR": "UNPROVEN", "NPU_ACTIVE_LE_CYCLE": "UNPROVEN"})


class Coverage(unittest.TestCase):
    def test_partial_refused(self):
        with self.assertRaises(E.Refusal) as cm: E.check_coverage({17: 1})
        self.assertEqual(E.refusal_rule(cm.exception), "RULE_SET_COVERAGE")
        E.check_coverage({k: 1 for k in E.driver_ids()})


if __name__ == "__main__":
    unittest.main()
