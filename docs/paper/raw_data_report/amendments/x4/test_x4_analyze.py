"""Gate tests for the X4 analysis. Run from repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.x4.test_x4_analyze"""
import copy, importlib.util, unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("x4", Path(__file__).with_name("x4_analyze.py"))
x4 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(x4)

ART = {"vela_sha256": "v", "frozen_vela_sha256": "v", "cc_body_sha256": "c", "frozen_cc_body_sha256": "c"}
FROZEN = {"cell": {"npu_total_cycles": 1000, "npu_active_cycles": 990, "ext_rd_beats": 10}}


def run(arm, defines, total, is_base=False, status="SUCCESS", header=None):
    return {"campaign": "A", "cell_id": "cell", "arm": arm, "defines": defines, "is_base": is_base, "status": status,
            "measurement": {"npu_total_cycles": total, "npu_active_cycles": 990, "ext_rd_beats": 10},
            "ta_header": header if header is not None else dict(defines), "artifact": ART}


def arms_a(totals):  # totals for factors 1.0(base), 0.0, 2.0
    lat = {"base": 250, "zero": 0, "double": 500}
    return {name: [run(name, {"EXT_RLATENCY": lat[name], "EXT_WLATENCY": lat[name] // 2}, t, is_base=(name == "base")) for _ in range(3)]
            for name, t in totals.items()}


def arms_b(totals):  # keyed by bwcap
    return {"bw%d" % bw: [run("bw%d" % bw, {"EXT_BWCAP": bw}, t, is_base=(bw == 50)) for _ in range(3)] for bw, t in totals.items()}


class Outcomes(unittest.TestCase):
    def test_sensitive_when_a_level_moves_ten_percent(self):
        r = x4.evaluate_cell("A", "cell", arms_a({"base": 1000, "zero": 850, "double": 1000}), FROZEN)
        self.assertEqual(r["outcome"], "MEMORY_SERVICE_SENSITIVE")

    def test_robust_when_all_levels_within_ten_percent(self):
        r = x4.evaluate_cell("A", "cell", arms_a({"base": 1000, "zero": 950, "double": 1050}), FROZEN)
        self.assertEqual(r["outcome"], "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE")

    def test_campaign_b_prediction(self):
        r = x4.evaluate_cell("B", "cell", arms_b({50: 1000, 25: 1900, 100: 550}), FROZEN)
        self.assertEqual((r["outcome"], r["A5_PREDICTION"]), ("BANDWIDTH_SENSITIVE", "MET"))
        r = x4.evaluate_cell("B", "cell", arms_b({50: 1000, 25: 1300, 100: 800}), FROZEN)
        self.assertEqual((r["outcome"], r["A5_PREDICTION"]), ("BANDWIDTH_SENSITIVE", "NOT_MET"))
        r = x4.evaluate_cell("B", "cell", arms_b({50: 1000, 25: 1050, 100: 960}), FROZEN)
        self.assertEqual(r["outcome"], "BANDWIDTH_INSENSITIVE")


class Refusals(unittest.TestCase):
    def test_base_mismatch(self):
        r = x4.evaluate_cell("A", "cell", arms_a({"base": 1001, "zero": 850, "double": 1000}), FROZEN)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", x4.RULE_BASE_MISMATCH))

    def test_reps_differ(self):
        a = arms_a({"base": 1000, "zero": 850, "double": 1000}); a["zero"][1]["measurement"]["npu_total_cycles"] = 851
        r = x4.evaluate_cell("A", "cell", a, FROZEN)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", x4.RULE_REPS_DIFFER))

    def test_ta_header_not_applied(self):
        a = arms_a({"base": 1000, "zero": 850, "double": 1000})
        for rr in a["zero"]: rr["ta_header"] = {"EXT_RLATENCY": 250, "EXT_WLATENCY": 125}
        r = x4.evaluate_cell("A", "cell", a, FROZEN)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", x4.RULE_TA_HEADER))

    def test_artifact_differs(self):
        a = arms_a({"base": 1000, "zero": 850, "double": 1000})
        for rr in a["double"]: rr["artifact"] = dict(ART, vela_sha256="x")
        r = x4.evaluate_cell("A", "cell", a, FROZEN)
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", x4.RULE_ARTIFACT))

    def test_every_rule_reachable(self):
        seen = set()
        a = arms_a({"base": 1001, "zero": 850, "double": 1000}); seen.add(x4.evaluate_cell("A", "cell", a, FROZEN)["rule"])
        a = arms_a({"base": 1000, "zero": 850, "double": 1000}); a["zero"][1]["status"] = "FAILURE"; seen.add(x4.evaluate_cell("A", "cell", a, FROZEN)["rule"])
        a = arms_a({"base": 1000, "zero": 850, "double": 1000}); a["zero"][0]["ta_header"] = {}; seen.add(x4.evaluate_cell("A", "cell", a, FROZEN)["rule"])
        a = arms_a({"base": 1000, "zero": 850, "double": 1000}); a["double"][0]["artifact"] = dict(ART, cc_body_sha256="x"); seen.add(x4.evaluate_cell("A", "cell", a, FROZEN)["rule"])
        self.assertEqual(seen, set(x4.RULES))


class DirectionFlip(unittest.TestCase):
    def test_flip_detected(self):
        a256 = {"campaign": "A", "cell_id": "w__P__ethos-u85-256", "outcome": "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE", "base_total": 100,
                "levels": {"b": {"total": 100, "defines": {"EXT_RLATENCY": 250}}, "z": {"total": 100, "defines": {"EXT_RLATENCY": 0}}}}
        a512 = {"campaign": "A", "cell_id": "w__P__ethos-u85-512", "outcome": "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE", "base_total": 120,
                "levels": {"b": {"total": 120, "defines": {"EXT_RLATENCY": 500}}, "z": {"total": 90, "defines": {"EXT_RLATENCY": 0}}}}
        f = x4.direction_flip([a256, a512])
        self.assertEqual((f["w"]["base_direction"], f["w"]["any_flip"]), (1, True))

    def test_full_profile_arms_are_excluded_from_flip_pairing(self):
        a256 = {"campaign": "A", "cell_id": "w__P__ethos-u85-256", "outcome": "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE", "base_total": 100,
                "levels": {"b": {"total": 100, "defines": {"EXT_RLATENCY": 250}}, "c": {"total": 300, "defines": {"EXT_RLATENCY": 500, "EXT_BWCAP": 3750}}}}
        a512 = {"campaign": "A", "cell_id": "w__P__ethos-u85-512", "outcome": "ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE", "base_total": 120,
                "levels": {"b": {"total": 120, "defines": {"EXT_RLATENCY": 500}}, "z": {"total": 90, "defines": {"EXT_RLATENCY": 1000}}}}
        f = x4.direction_flip([a256, a512])
        self.assertEqual([x["factor"] for x in f["w"]["levels"]], [1.0])


if __name__ == "__main__":
    unittest.main()
