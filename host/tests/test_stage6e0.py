"""Stage 6E-0 judge tests. Expected values are hand-written from the contract tables."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6e0 as E  # noqa: E402

Y, N = True, False
ALL = (Y,) * 10


class Compute(unittest.TestCase):
    def test_rules(self):
        V = E.compute_attribution
        self.assertEqual(V("QUANTITATIVELY_EXPLAINED", 0, 0, 100, 0), "EXPLAINED_WITH_EXISTING_DATA")
        self.assertEqual(V("PARTIALLY_EXPLAINED", 10, 10, 100, 0.1), "PARTIALLY_EXPLAINED")
        self.assertEqual(V("NOT_EXPLAINED", 64.6, 120.4, 100, 0.98), "PARTIALLY_EXPLAINED")   # bracket
        self.assertEqual(V("NOT_EXPLAINED", 105, 95, 100, 0.95), "PARTIALLY_EXPLAINED")       # edges inclusive
        self.assertEqual(V("NOT_EXPLAINED", 105.1, 120, 100, 0.98), "NOT_IDENTIFIABLE")
        self.assertEqual(V("NOT_EXPLAINED", 60, 94.9, 100, 0.98), "NOT_IDENTIFIABLE")
        self.assertEqual(V("NOT_EXPLAINED", 60, 120, 100, 0.949), "NOT_IDENTIFIABLE")
        self.assertEqual(V("QUALITATIVE_SUPPORT_ONLY", 10, 50, 100, 0.99), "NOT_IDENTIFIABLE")

    def test_predicted_share(self):
        rows = [dict(level="EXACT_VALIDATED", n_mac="50", p_ext=""),
                dict(level="EXTRAPOLATED", n_mac="20", p_ext="7.0"),
                dict(level="EXTRAPOLATED", n_mac="10", p_ext=""),
                dict(level="INVALID_OR_UNSTABLE", n_mac="10", p_ext=""),
                dict(level="CPU_OR_SPLIT", n_mac="10", p_ext="3")]
        self.assertAlmostEqual(E.predicted_share(rows), 0.7)


class Candidates(unittest.TestCase):
    def test_fixed_table(self):
        c = {n: (cr, v, b) for n, cr, v, b in E.CANDIDATES}
        self.assertEqual(c["X3_SERIAL_MASK"], (ALL, Y, 10))
        self.assertEqual(c["X1_G_DF_EXT"][0][0], N)
        self.assertEqual(c["X1_G_DF_EXT"][0][7], N)
        self.assertEqual(c["X2_PREFIX_STOP"][0][7], N)
        self.assertEqual(c["X4_QREAD_FINE"][0][3], N)
        self.assertEqual(c["X5_AD_REST_ISOLATED"][0][8], N)
        self.assertEqual(len(E.CANDIDATES), 5)
        self.assertFalse(any(ok for _, _, ok in E.INSTRUMENTS))
        self.assertEqual(len(E.INSTRUMENTS), 5)

    def test_select_eligible_min_boots(self):
        cands = (("A", ALL, N, 12), ("B", ALL, Y, 10), ("C", (N,) + ALL[1:], Y, 2))
        s = E.select(cands)
        self.assertEqual((s["name"], s["eligible"], s["boots"]), ("B", True, 10))
        cands = (("A", ALL, N, 10), ("B", ALL, Y, 10))
        self.assertEqual(E.select(cands)["name"], "A")

    def test_select_none_eligible(self):
        cands = (("A", (Y, N) + ALL[2:], N, 1), ("B", (Y, N, N) + ALL[3:], N, 1))
        s = E.select(cands)
        self.assertEqual((s["name"], s["eligible"]), ("A", False))

    def test_selected_is_x3(self):
        self.assertEqual(E.select()["name"], "X3_SERIAL_MASK")


class Verdicts(unittest.TestCase):
    def sel(self, name="X", eligible=True, c=ALL, v=Y):
        return dict(name=name, eligible=eligible, criteria=dict(zip(E.CRITERIA, c)), vela_condition_match=v, boots=1)

    def test_next(self):
        cands = (("X", ALL, Y, 1),)
        ok = {"X": (("a", "EXISTS"), ("b", "NEEDS_BOARD_PRECHECK"))}
        self.assertEqual(E.next_experiment(self.sel(), cands, ok, {"X": True}), "READY_FOR_BOARD_REVIEW")
        self.assertEqual(E.next_experiment(self.sel(), cands, ok, {"X": False}), "STATIC_DESIGN_INCOMPLETE")
        unk = {"X": (("a", "UNKNOWN_FEASIBILITY"),)}
        self.assertEqual(E.next_experiment(self.sel(), cands, unk, {"X": True}), "STATIC_DESIGN_INCOMPLETE")
        self.assertEqual(E.next_experiment(self.sel(eligible=False), cands, ok, {"X": True}), "STATIC_DESIGN_INCOMPLETE")
        no4 = (("X", (Y, Y, Y, N) + ALL[4:], Y, 1),)
        self.assertEqual(E.next_experiment(self.sel(eligible=False), no4, ok, {"X": True}), "INSUFFICIENT_IDENTIFIABILITY")
        self.assertEqual(E.next_experiment(self.sel(), cands, {"X": (("a", "EXISTS"),)}, {}), "READY_FOR_BOARD_REVIEW")

    def test_execution(self):
        self.assertEqual(E.execution_cost(self.sel()), "REQUIRES_CONTROLLED_EXPERIMENT")
        self.assertEqual(E.execution_cost(self.sel(), (("a", "s", True),)), "MEASURABLE_WITH_EXISTING_INSTRUMENTATION")
        for i in (2, 3, 6):
            c = list(ALL)
            c[i] = N
            self.assertEqual(E.execution_cost(self.sel(c=tuple(c))), "NOT_IDENTIFIABLE")

    def test_vela(self):
        self.assertEqual(E.vela_fidelity(self.sel(), True), "TESTABLE_MECHANISM_IDENTIFIED")
        self.assertEqual(E.vela_fidelity(self.sel(v=N), True), "DISCREPANCY_CHARACTERIZED")
        c = list(ALL)
        c[5] = N
        self.assertEqual(E.vela_fidelity(self.sel(c=tuple(c)), True), "DISCREPANCY_CHARACTERIZED")
        self.assertEqual(E.vela_fidelity(self.sel(v=N), False), "CAUSE_UNRESOLVED")

    def test_vela_terms(self):
        ops = [dict(exec_on="NPU", vela_op_cycles="100", vela_mac_cycles="100"),
               dict(exec_on="NPU", vela_op_cycles="300", vela_mac_cycles="50"),
               dict(exec_on="NPU", vela_op_cycles="", vela_mac_cycles=""),
               dict(exec_on="CPU_OR_REMOVED", vela_op_cycles="999", vela_mac_cycles="1")]
        t = E.vela_terms(ops)
        self.assertEqual((t["sum_op_cycles"], t["sum_mac_cycles"], t["n_ops"]), (400.0, 150.0, 2))
        self.assertAlmostEqual(t["non_mac_bound_share"], 0.75)

    def test_implementation_fixed(self):
        st = dict(E.IMPLEMENTATION["X3_SERIAL_MASK"])
        self.assertEqual(st["PMU_MASK / KERNEL_WAIT(0) on driver runner"], "NEEDS_BOARD_PRECHECK")
        self.assertEqual(st["COP1 replace + tflite reserialize"], "NEW_BOUNDED")
        self.assertNotIn("UNKNOWN_FEASIBILITY", st.values())
        self.assertTrue(E.PRECHECK_IN_FIRST_BOOT["X3_SERIAL_MASK"])


if __name__ == "__main__":
    unittest.main()
