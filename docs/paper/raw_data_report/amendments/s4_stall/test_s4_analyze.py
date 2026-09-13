"""Gate tests for the S4 analysis. Run from repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.s4_stall.test_s4_analyze"""
import copy, importlib.util, unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("s4", Path(__file__).with_name("s4_analyze.py"))
s4 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(s4)

ART = {"vela_sha256": "v", "frozen_vela_sha256": "v", "cc_body_sha256": "c", "frozen_cc_body_sha256": "c", "axf_sha256": "a", "frozen_axf_sha256": "b"}


def run(total=1000, w=100, ib=50, ob=50, active=600, g2=True, status="SUCCESS"):
    return {"cell_id": "cell", "status": status, "stock_counters": {"npu_total_cycles": total, "npu_active_cycles": 990},
            "G2_stock_counters_match": {"npu_total_cycles": g2, "npu_active_cycles": True},
            "s4_counters": {"MAC_ACTIVE": active, "MAC_STALLED_BY_W": w, "MAC_STALLED_BY_IB": ib, "AO_STALLED_BY_OB": ob},
            "artifact": ART}


class Outcomes(unittest.TestCase):
    def test_dominant_present_negligible(self):
        self.assertEqual(s4.evaluate_cell("cell", [run(w=200, ib=100, ob=50)] * 3)["outcome"], "MEMORY_WAIT_DOMINANT")   # 0.35
        self.assertEqual(s4.evaluate_cell("cell", [run(w=50, ib=30, ob=20)] * 3)["outcome"], "MEMORY_WAIT_PRESENT")      # 0.10
        self.assertEqual(s4.evaluate_cell("cell", [run(w=10, ib=10, ob=10)] * 3)["outcome"], "MEMORY_WAIT_NEGLIGIBLE")   # 0.03

    def test_semantics_flag_always_present(self):
        self.assertEqual(s4.evaluate_cell("cell", [run()] * 3)["semantics"], "SEMANTICS_UNVERIFIED")


class Refusals(unittest.TestCase):
    def test_g2(self):
        r = s4.evaluate_cell("cell", [run(g2=False)] * 3)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G2))

    def test_g3(self):
        r = s4.evaluate_cell("cell", [run(), run(w=101), run()])
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G3))

    def test_g1(self):
        rr = run(); rr["artifact"] = dict(ART, vela_sha256="x")
        r = s4.evaluate_cell("cell", [rr] * 3)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G1))

    def test_missing_counter(self):
        rr = run(); rr["s4_counters"]["MAC_STALLED_BY_W"] = None
        r = s4.evaluate_cell("cell", [rr] * 3)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_MISSING))

    def test_every_rule_and_outcome_reachable(self):
        rules = {s4.evaluate_cell("c", [run(g2=False)] * 3)["rule"], s4.evaluate_cell("c", [run(), run(w=1), run()])["rule"]}
        rr = run(); rr["artifact"] = dict(ART, cc_body_sha256="x"); rules.add(s4.evaluate_cell("c", [rr] * 3)["rule"])
        rr = run(); rr["s4_counters"]["AO_STALLED_BY_OB"] = None; rules.add(s4.evaluate_cell("c", [rr] * 3)["rule"])
        self.assertEqual(rules, set(s4.RULES))
        outs = {s4.evaluate_cell("c", [run(w=200, ib=100, ob=50)] * 3)["outcome"], s4.evaluate_cell("c", [run(w=50, ib=30, ob=20)] * 3)["outcome"],
                s4.evaluate_cell("c", [run(w=10, ib=10, ob=10)] * 3)["outcome"], s4.evaluate_cell("c", [run(g2=False)] * 3)["outcome"]}
        self.assertEqual(outs, set(s4.OUTCOMES))


if __name__ == "__main__":
    unittest.main()
