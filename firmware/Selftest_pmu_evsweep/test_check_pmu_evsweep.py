"""Mutation tests for check_pmu_evsweep: every rule must be reachable and RED."""
import sys, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_pmu_evsweep as g

GOOD_OBJ = """
 8000100:  f24f 3080   movw r0, #0x5380
 8000104:  f2c5 0000   movt r0, #0x5000
 8000200:  .word 0x50005380
 8000204:  .word 0x45565357
"""
GOOD_NM = """
08000000 T main
08000400 t cell
08000500 T serial_print
"""
BID = 0x45565357


class T(unittest.TestCase):
    def test_green(self):
        self.assertTrue(g.check(GOOD_OBJ, GOOD_NM, BID))

    def _red(self, obj, nm, bid, rule):
        with self.assertRaises(g.GateFail) as cm:
            g.check(obj, nm, bid)
        self.assertEqual(cm.exception.rule, rule)

    def test_no_pmevtyper_store(self):
        self._red(GOOD_OBJ.replace("50005380", "50005300"), GOOD_NM, BID, "RULE_PMEVTYPER0_TARGET")

    def test_inference_linked(self):
        self._red(GOOD_OBJ, GOOD_NM + "08000600 T apU85Conv_TEST\n", BID, "RULE_NO_INFERENCE")

    def test_wrong_build_id(self):
        self._red(GOOD_OBJ, GOOD_NM, 0x504D5543, "RULE_BUILD_ID")

    def test_no_main(self):
        self._red(GOOD_OBJ, GOOD_NM.replace("T main", "T notmain"), BID, "RULE_MAIN_PRESENT")

    def test_every_rule_has_a_fixture(self):
        tripped = set()
        for obj, nm, bid in (
            (GOOD_OBJ.replace("50005380", "50005300"), GOOD_NM, BID),
            (GOOD_OBJ, GOOD_NM + "08000600 T apU85Conv_TEST\n", BID),
            (GOOD_OBJ, GOOD_NM, 0x504D5543),
            (GOOD_OBJ, GOOD_NM.replace("T main", "T notmain"), BID),
        ):
            try: g.check(obj, nm, bid)
            except g.GateFail as e: tripped.add(e.rule)
        self.assertEqual(tripped, set(g.RULES))


if __name__ == "__main__":
    unittest.main()
