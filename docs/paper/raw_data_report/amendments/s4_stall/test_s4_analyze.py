"""Gate tests for the S4 analysis. Run from repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.s4_stall.test_s4_analyze"""
import copy, importlib.util, unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("s4", Path(__file__).with_name("s4_analyze.py"))
s4 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(s4)

ART = {"vela_sha256": "v", "frozen_vela_sha256": "v", "cc_body_sha256": "c", "frozen_cc_body_sha256": "c", "axf_sha256": "a", "frozen_axf_sha256": "b"}


def run(total=1000, w=100, ib=50, ob=50, active=600, g2=True, status="SUCCESS", pass_id="A", idle=10, ovs=0):
    s4 = ({"MAC_ACTIVE": active, "MAC_STALLED_BY_W": w, "MAC_STALLED_BY_IB": ib, "OVS": ovs} if pass_id == "A"
          else {"MAC_ACTIVE": active, "AO_STALLED_BY_OB": ob, "NPU_IDLE": idle, "OVS": ovs})
    return {"cell_id": "cell", "pass": pass_id, "status": status,
            "stock_counters": {"npu_total_cycles": total, "npu_active_cycles": 990, "npu_idle_cycles": 10},
            "G2_stock_counters_match": {"npu_total_cycles": g2, "npu_active_cycles": True}, "s4_counters": s4, "artifact": ART}


def cell(w=100, ib=50, ob=50, active=600, g2=True, active_b=None):
    return {"A": [run(w=w, ib=ib, active=active, g2=g2)] * 3,
            "B": [run(ob=ob, active=active if active_b is None else active_b, g2=g2, pass_id="B")] * 3}


class Outcomes(unittest.TestCase):
    def test_raw_preserved_without_summing(self):
        r = s4.evaluate_cell("cell", cell(w=200, ib=100, ob=50))
        self.assertEqual(r["outcome"], "RAW_PRESERVED")
        self.assertNotIn("stall_sum", r); self.assertNotIn("stall_share_upper_bound", r)
        self.assertEqual(r["counters"]["MAC_STALLED_BY_W"], 200)
        self.assertAlmostEqual(r["per_event_ratio_to_total_descriptive"]["AO_STALLED_BY_OB"], 0.05)

    def test_overflow_trips_g6(self):
        c = cell(); c["B"] = [run(pass_id="B", ovs=0x40)] * 3
        r = s4.evaluate_cell("cell", c)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G6))
        c = cell(); c["A"] = [run(ovs=0x01)] * 3   # overflow on a stock counter bit is not S4's
        self.assertEqual(s4.evaluate_cell("cell", c)["outcome"], "RAW_PRESERVED")

    def test_semantics_flag_always_present(self):
        self.assertEqual(s4.evaluate_cell("cell", cell())["semantics"], "SEMANTICS_UNVERIFIED")


class Refusals(unittest.TestCase):
    def test_g2(self):
        r = s4.evaluate_cell("cell", cell(g2=False))
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G2))

    def test_g3(self):
        c = cell(); c["A"] = [run(), run(w=101), run()]
        r = s4.evaluate_cell("cell", c)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G3))

    def test_g1(self):
        c = cell(); rr = run(); rr["artifact"] = dict(ART, vela_sha256="x"); c["A"] = [rr] * 3
        r = s4.evaluate_cell("cell", c)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G1))

    def test_missing_counter_and_missing_pass(self):
        c = cell(); rr = run(); rr["s4_counters"]["MAC_STALLED_BY_W"] = None; c["A"] = [rr] * 3
        r = s4.evaluate_cell("cell", c)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_MISSING))
        r = s4.evaluate_cell("cell", {"A": cell()["A"]})
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_MISSING))

    def test_g5_passes_disagree(self):
        r = s4.evaluate_cell("cell", cell(active=600, active_b=601))
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", s4.RULE_G5))

    def test_every_rule_and_outcome_reachable(self):
        c = cell(); c["A"] = [run(), run(w=1), run()]
        rules = {s4.evaluate_cell("c", cell(g2=False))["rule"], s4.evaluate_cell("c", c)["rule"], s4.evaluate_cell("c", cell(active_b=1))["rule"]}
        c = cell(); rr = run(); rr["artifact"] = dict(ART, cc_body_sha256="x"); c["A"] = [rr] * 3; rules.add(s4.evaluate_cell("c", c)["rule"])
        c = cell(); rr = run(pass_id="B"); rr["s4_counters"]["AO_STALLED_BY_OB"] = None; c["B"] = [rr] * 3; rules.add(s4.evaluate_cell("c", c)["rule"])
        c = cell(); c["A"] = [run(ovs=0x20)] * 3; rules.add(s4.evaluate_cell("c", c)["rule"])
        self.assertEqual(rules, set(s4.RULES))
        outs = {s4.evaluate_cell("c", cell())["outcome"], s4.evaluate_cell("c", cell(g2=False))["outcome"]}
        self.assertEqual(outs, set(s4.OUTCOMES))


if __name__ == "__main__":
    unittest.main()
