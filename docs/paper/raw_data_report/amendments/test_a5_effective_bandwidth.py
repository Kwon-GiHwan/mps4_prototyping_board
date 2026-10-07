"""Gate tests for A5. Run from repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.test_a5_effective_bandwidth
Every refusal must trip its own rule; every outcome in the closed set must be reachable."""
import copy, unittest
from pathlib import Path

import importlib.util
_spec = importlib.util.spec_from_file_location("a5", Path(__file__).with_name("a5_effective_bandwidth.py"))
a5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(a5)

TA = {"ta_config": "t", "bytes_per_word": "16",
      "sram_bwcap": "4000", "sram_pulse_on": "3999", "sram_pulse_off": "1",
      "ext_bwcap": "2344", "ext_pulse_on": "4000", "ext_pulse_off": "1000"}
CELL = {"npu": "ethos-u85", "mac": 256, "cycles": 10000,
        "sram_rd": "1000", "sram_wr": "1000", "ext_rd": "500", "ext_wr": "10"}


class Caps(unittest.TestCase):
    def test_cap_matches_vela_reference(self):
        self.assertAlmostEqual(a5.cap_bytes_per_cycle(TA, "sram"), 16.0)      # 1 word/cycle
        self.assertAlmostEqual(a5.cap_bytes_per_cycle(TA, "ext"), 7.5008, places=3)  # 3.75 GB/s @ 500 MHz


class Outcomes(unittest.TestCase):
    def test_ruled_out(self):
        r = a5.evaluate(CELL, TA)
        self.assertEqual(r["sram"]["outcome"], "SATURATION_RULED_OUT")   # 2000*16/10000 = 3.2 B/cyc of 16
        self.assertEqual(r["ext"]["outcome"], "SATURATION_RULED_OUT")    # 510*16/10000 = 0.816 of 7.5

    def test_near_and_at_limit(self):
        c = dict(CELL, sram_rd="4000", sram_wr="3000")                    # 7000*16/10000 = 11.2 -> 0.70
        self.assertEqual(a5.evaluate(c, TA)["sram"]["outcome"], "NEAR_LIMIT")
        c = dict(CELL, sram_rd="6000", sram_wr="3500")                    # 9500*16/10000 = 15.2 -> 0.95
        self.assertEqual(a5.evaluate(c, TA)["sram"]["outcome"], "AT_LIMIT")

    def test_lower_bound_without_writes(self):
        c = dict(CELL, npu="ethos-u65", mac=256, ext_wr=None)
        self.assertEqual(a5.evaluate(c, TA)["ext"]["outcome"], "LOWER_BOUND_ONLY")
        c = dict(c, ext_rd="4500")                                       # 4500*16/10000 = 7.2 -> 0.96 on a lower bound
        self.assertEqual(a5.evaluate(c, TA)["ext"]["outcome"], "AT_LIMIT")

    def test_structurally_zero_writes_count_as_complete(self):
        c = dict(CELL, npu="ethos-u55", mac=32, ext_wr=None, ext_wr_structurally_zero=True)
        self.assertEqual(a5.evaluate(c, TA)["ext"]["outcome"], "SATURATION_RULED_OUT")


class Refusals(unittest.TestCase):
    def test_cap_zero_trips_its_own_rule(self):
        ta = dict(TA, ext_bwcap="0")
        r = a5.evaluate(CELL, ta)["ext"]
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", a5.RULE_CAP_ZERO))

    def test_missing_cycles_trips_input_rule(self):
        r = a5.evaluate(dict(CELL, cycles=None), TA)
        self.assertEqual((r["sram"]["outcome"], r["sram"]["rule"]), ("NOT_EVALUABLE", a5.RULE_INPUT_MISSING))

    def test_missing_ta_field_trips_input_rule(self):
        ta = copy.deepcopy(TA); del ta["sram_bwcap"]
        r = a5.evaluate(CELL, ta)["sram"]
        self.assertEqual((r["outcome"], r["rule"]), ("NOT_EVALUABLE", a5.RULE_INPUT_MISSING))

    def test_every_rule_and_outcome_is_reachable(self):
        tripped, seen = set(), set()
        for cell, ta in ((CELL, dict(TA, ext_bwcap="0")), (dict(CELL, cycles=None), TA)):
            for g in a5.evaluate(cell, ta).values():
                if g["rule"]: tripped.add(g["rule"])
        self.assertEqual(tripped, set(a5.RULES))
        for cell in (CELL, dict(CELL, sram_rd="4000", sram_wr="3000"), dict(CELL, sram_rd="6000", sram_wr="3500"),
                     dict(CELL, npu="ethos-u65", ext_wr=None), dict(CELL, cycles=None)):
            for g in a5.evaluate(cell, TA).values():
                seen.add(g["outcome"])
        self.assertEqual(seen, set(a5.OUTCOMES))


if __name__ == "__main__":
    unittest.main()
