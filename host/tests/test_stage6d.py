"""Stage 6D judge tests. Expected values are hand-written (board measurements, contract boundaries)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6d as D  # noqa: E402


def op(model="m", idx=1, tfop="CONV_2D", k="1x1", s="1x1", tr="DepthFirst", cin=16, cout=16, ofm="8x8x16",
       n=1000, ex="NPU", cat="NOT_APPLICABLE"):
    return dict(model=model, tflite_op_index=str(idx), tflite_op=tfop, kernel=k, stride=s, traversal=tr, cin=str(cin),
                cout=str(cout), npu_ofm_hwc=ofm, n_mac_tflite=str(n), exec_on=ex, category=cat, vela_op_cycles="1")


class Family(unittest.TestCase):
    def test_families(self):
        self.assertEqual(D.family(op()), "DF1x1")
        self.assertEqual(D.family(op(tr="PartKernel")), "PK1x1")
        self.assertEqual(D.family(op(k="3x3", tr="PartKernel", cin=1)), "PK3x3")
        self.assertEqual(D.family(op(k="1x7", tr="PartKernel")), "PK1D")
        self.assertEqual(D.family(op(k="3x3", tr="DepthFirst", cin=32)), "OTHER_CONV")
        self.assertEqual(D.family(op(k="1x5", tr="PartKernel")), "OTHER_CONV")
        self.assertEqual(D.family(op(k="10x4", tr="PartKernel", cin=1)), "FIRST_CONV")
        self.assertEqual(D.family(op(k="10x4", tr="PartKernel", cin=16)), "OTHER_CONV")
        self.assertEqual(D.family(op(tfop="DEPTHWISE_CONV_2D", k="3x3", tr="Depthwise")), "DW")
        self.assertEqual(D.family(op(tfop="FULLY_CONNECTED")), "FC")
        self.assertEqual(D.family(op(ex="CPU_OR_REMOVED")), "CPU_OR_SPLIT")
        self.assertEqual(D.family(op(ex="AMBIGUOUS_SPLIT")), "CPU_OR_SPLIT")
        self.assertEqual(D.family(op(n=0)), "AO_ELEMENTWISE")


class Rules(unittest.TestCase):
    def dw(self, c, hw="96x96", k="3x3", s="1x1"):
        return op(tfop="DEPTHWISE_CONV_2D", k=k, s=s, tr="Depthwise", cin=c, cout=c, ofm=f"{hw}x{c}")

    def test_dw_board_values(self):
        self.assertEqual(D.rule(self.dw(8), "DW"), (10368.0, True))        # 6C F2 rep
        self.assertEqual(D.rule(self.dw(16), "DW"), (10368.0, True))       # 6C F2 ctl
        self.assertEqual(D.rule(self.dw(144, "56x56"), "DW"), (31752.0, True))   # Stage 4 dw_base
        self.assertEqual(D.rule(self.dw(143, "56x56"), "DW"), (31752.0, True))   # Stage 4 dw_c143

    def test_dw_range(self):
        self.assertFalse(D.rule(self.dw(7), "DW")[1])
        self.assertTrue(D.rule(self.dw(145), "DW")[1])
        self.assertFalse(D.rule(self.dw(146), "DW")[1])
        self.assertFalse(D.rule(self.dw(16, s="2x2"), "DW")[1])
        p, ok = D.rule(self.dw(16, k="5x5"), "DW")
        self.assertFalse(ok)
        self.assertEqual(p, 96 * 96 * 16 * 25 / 128)

    def test_fc(self):
        fc = lambda ci, co, o="1x1": op(tfop="FULLY_CONNECTED", cin=ci, cout=co, ofm=f"{o}x{co}")  # noqa: E731
        self.assertEqual(D.rule(fc(96, 288), "FC"), (108.0, True))        # Stage 4 fc_base
        self.assertEqual(D.rule(fc(95, 288), "FC"), (108.0, True))
        self.assertEqual(D.rule(fc(96, 287), "FC"), (108.0, True))
        self.assertEqual(D.rule(fc(114, 288), "FC"), (144.0, False))      # 6C F3 value, out of range
        self.assertFalse(D.rule(fc(97, 288), "FC")[1])
        self.assertFalse(D.rule(fc(96, 289), "FC")[1])
        self.assertFalse(D.rule(fc(94, 288), "FC")[1])
        self.assertFalse(D.rule(fc(96, 286), "FC")[1])
        self.assertEqual(D.rule(fc(96, 288, "2x1"), "FC"), (216.0, False))

    def test_pk3(self):
        pk = lambda ci, co=32, s="1x1": op(k="3x3", tr="PartKernel", s=s, cin=ci, cout=co,  # noqa: E731
                                            ofm=f"48x36x{co}")
        self.assertEqual(D.rule(pk(16), "PK3x3"), (7962624 / 768, True))   # 4K cin16: 10368
        self.assertEqual(D.rule(pk(16), "PK3x3")[0], 10368.0)
        self.assertEqual(D.rule(pk(32), "PK3x3")[0], 20736.0)               # 4K cin32
        self.assertFalse(D.rule(pk(1), "PK3x3")[1])
        self.assertFalse(D.rule(pk(15), "PK3x3")[1])
        self.assertTrue(D.rule(pk(64), "PK3x3")[1])
        self.assertFalse(D.rule(pk(65), "PK3x3")[1])
        self.assertFalse(D.rule(pk(16, s="2x2"), "PK3x3")[1])
        self.assertFalse(D.rule(pk(16, co=24), "PK3x3")[1])
        self.assertEqual(D.rule(pk(3), "PK3x3")[0], 48 * 36 * 16 * 32 * 9 / 768)

    def test_no_rule(self):
        self.assertEqual(D.rule(op(tr="PartKernel"), "PK1x1"), (None, False))


class Level(unittest.TestCase):
    def lv(self, r, h1=None, exact=None):
        return D.level(r, D.family(r), h1 or {}, exact or {})

    def test_order(self):
        h_ok = {("m", 1): dict(h1uc="500", measured_unstable_match="")}
        h_bad = {("m", 1): dict(h1uc="500", measured_unstable_match="G28")}
        self.assertEqual(self.lv(op(cat="BOARD_MEASURED"), h_ok), ("EXACT_VALIDATED", 500.0, None))
        self.assertEqual(self.lv(op(cat="BOARD_MEASURED"), h_bad)[0], "INVALID_OR_UNSTABLE")
        self.assertEqual(self.lv(op(cat="EXTRAPOLATED_PREDICTION"), h_ok), ("EXTRAPOLATED", None, 500.0))
        dw = op(tfop="DEPTHWISE_CONV_2D", k="3x3", tr="Depthwise", cin=8, cout=8, ofm="96x96x8")
        self.assertEqual(self.lv(dw), ("CLASS_SUPPORTED", 10368.0, None))
        self.assertEqual(self.lv(dw, exact={("m", 1): 777.0}), ("CONFIGURATION_MATCHED", 777.0, None))
        self.assertEqual(self.lv(op(tr="PartKernel")), ("EXTRAPOLATED", None, None))
        self.assertEqual(self.lv(op(k="1x5", tr="PartKernel")), ("UNSUPPORTED", None, None))
        dw2 = op(tfop="DEPTHWISE_CONV_2D", k="3x3", s="2x2", tr="Depthwise", cin=16, cout=16, ofm="4x4x16")
        self.assertEqual(self.lv(dw2), ("EXTRAPOLATED", None, 4 * 4 * 16 * 9 / 128))

    def test_f3_unstable(self):
        fc = op(model="rnnoise_INT8", idx=46, tfop="FULLY_CONNECTED", cin=96, cout=288, ofm="1x1x288")
        self.assertEqual(self.lv(fc)[0], "INVALID_OR_UNSTABLE")
        fc0 = op(model="rnnoise_INT8", idx=0, tfop="FULLY_CONNECTED", cin=96, cout=288, ofm="1x1x288")
        self.assertEqual(self.lv(fc0)[0], "CLASS_SUPPORTED")

    def test_exact_keys(self):
        self.assertEqual(D.EXACT[("yolo-fastest_192_face_v4", 9)], "s6c_f1_rep")
        self.assertEqual(D.EXACT[("yolo-fastest_192_face_v4", 3)], "s6c_f2_rep")
        self.assertEqual(D.EXACT[("wav2letter_pruned_int8", 17)], "s6c_f4_rep")
        self.assertEqual(D.EXACT[("kws_micronet_m", 0)], "s6c_f5_rep")
        self.assertEqual(len(D.EXACT), 4)


class Coverage(unittest.TestCase):
    def rows(self):
        return [dict(level="EXACT_VALIDATED", n_mac=500, p=40.0, p_ext=None, family="DF1x1"),
                dict(level="CLASS_SUPPORTED", n_mac=200, p=10.0, p_ext=None, family="DW"),
                dict(level="EXTRAPOLATED", n_mac=200, p=None, p_ext=7.0, family="PK1x1"),
                dict(level="EXTRAPOLATED", n_mac=50, p=None, p_ext=None, family="PK1D"),
                dict(level="CPU_OR_SPLIT", n_mac=50, p=None, p_ext=None, family="CPU_OR_SPLIT"),
                dict(level="AO_ELEMENTWISE", n_mac=0, p=None, p_ext=None, family="AO_ELEMENTWISE")]

    def test_coverage(self):
        c = D.coverage(self.rows())
        self.assertEqual(c["n_model"], 1000)
        self.assertAlmostEqual(c["c"], 0.7)
        self.assertEqual(c["P"], 50.0)
        self.assertEqual(c["P_ext"], 57.0)
        self.assertAlmostEqual(c["share"]["EXTRAPOLATED"], 0.25)
        self.assertAlmostEqual(c["count_share"]["EXTRAPOLATED"], 0.4)
        self.assertAlmostEqual(c["count_share"]["AO_ELEMENTWISE"], 0.2)
        self.assertTrue(c["any_evidence"])

    def test_extrapolated_is_evidence(self):
        c = D.coverage([dict(level="EXTRAPOLATED", n_mac=10, p=None, p_ext=None, family="PK1x1")])
        self.assertTrue(c["any_evidence"])

    def test_no_evidence(self):
        c = D.coverage([dict(level="UNSUPPORTED", n_mac=10, p=None, p_ext=None, family="OTHER_CONV")])
        self.assertFalse(c["any_evidence"])


class Verdict(unittest.TestCase):
    def test_bounds(self):
        V = D.compute_verdict
        self.assertEqual(V(0.90, 85.0, 100.0, True), "QUANTITATIVELY_EXPLAINED")
        self.assertEqual(V(0.90, 105.0, 100.0, True), "QUANTITATIVELY_EXPLAINED")
        self.assertEqual(V(0.89, 95.0, 100.0, True), "PARTIALLY_EXPLAINED")
        self.assertEqual(V(0.90, 84.9, 100.0, True), "NOT_EXPLAINED")
        self.assertEqual(V(0.95, 105.1, 100.0, True), "NOT_EXPLAINED")
        self.assertEqual(V(0.30, 105.1, 100.0, True), "NOT_EXPLAINED")
        self.assertEqual(V(0.50, 10.0, 100.0, True), "PARTIALLY_EXPLAINED")
        self.assertEqual(V(0.49, 10.0, 100.0, True), "QUALITATIVE_SUPPORT_ONLY")
        self.assertEqual(V(0.49, 10.0, 100.0, False), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(V(0.95, 95.0, None, True), "INSUFFICIENT_EVIDENCE")


class Vela(unittest.TestCase):
    def test_cancel(self):
        r = [dict(family="DW", n_mac=10), dict(family="PK1x1", n_mac=10), dict(family="DF1x1", n_mac=80)]
        self.assertEqual(D.cancellation(r, 100)["verdict"], "CANCELLATION_POSSIBLE")
        r = [dict(family="DW", n_mac=9), dict(family="FC", n_mac=50), dict(family="DF1x1", n_mac=41)]
        x = D.cancellation(r, 100)
        self.assertEqual(x["verdict"], "NO_CANCELLATION_INDICATED")
        self.assertAlmostEqual(x["under_share"], 0.5)
        self.assertAlmostEqual(x["mixed_share"], 0.41)
        r = [dict(family="PK1D", n_mac=10), dict(family="FIRST_CONV", n_mac=10)]
        self.assertEqual(D.cancellation(r, 100)["verdict"], "CANCELLATION_POSSIBLE")

    def test_class(self):
        self.assertEqual(D.vela_class(0.89), "OVERESTIMATION")
        self.assertEqual(D.vela_class(0.9), "ESTIMATE_AGREEMENT")
        self.assertEqual(D.vela_class(1.1), "ESTIMATE_AGREEMENT")
        self.assertEqual(D.vela_class(1.11), "UNDERESTIMATION")


class Recommend(unittest.TestCase):
    def test_pick(self):
        rows = {"a": [dict(family="PK1x1", level="EXTRAPOLATED", n_mac=30), dict(family="DF1x1", level="EXACT_VALIDATED",
                                                                                 n_mac=70)],
                "b": [dict(family="FC", level="INVALID_OR_UNSTABLE", n_mac=90), dict(family="DW", level="UNSUPPORTED",
                                                                                     n_mac=10)],
                "c": [dict(family="PK1x1", level="EXTRAPOLATED", n_mac=20), dict(family="DF1x1", level="EXACT_VALIDATED",
                                                                                 n_mac=80)]}
        r = D.recommend(rows)
        imp = {t["gap"]: t["impact"] for t in r["table"]}
        self.assertAlmostEqual(imp["G_FC"], 0.9)
        self.assertAlmostEqual(imp["G_PK1X1"], 0.3)
        self.assertAlmostEqual(imp["G_DW_VELA"], 0.1)
        self.assertEqual(imp["G_DF_EXT"], 0.0)
        self.assertEqual(r["recommendation"], "G_PK1X1")   # G_FC not discriminating

    def test_tie_first(self):
        rows = {"a": [dict(family="DW", level="EXTRAPOLATED", n_mac=50), dict(family="PK1D", level="EXTRAPOLATED",
                                                                               n_mac=50)]}
        self.assertEqual(D.recommend(rows)["recommendation"], "G_DW_VELA")

    def test_fixed_table(self):
        t = {g: (f, c, d, k) for g, f, c, d, k in D.GAPS}
        self.assertEqual(t["G_FC"][2], False)
        self.assertEqual(t["G_DF_EXT"][3], 9)
        self.assertEqual(t["G_FIRST"][0], ("FIRST_CONV", "PK3x3"))
        self.assertEqual(D.MAX_COST, 9)
        self.assertEqual(len(D.GAPS), 8)

    def test_cost_limit(self):
        orig = D.GAPS
        try:
            D.GAPS = (("X", ("DW",), True, True, 10), ("Y", ("FC",), True, True, 9))
            rows = {"a": [dict(family="DW", level="EXTRAPOLATED", n_mac=90), dict(family="FC", level="EXTRAPOLATED",
                                                                                   n_mac=10)]}
            self.assertEqual(D.recommend(rows)["recommendation"], "Y")
            D.GAPS = (("X", ("DW",), False, True, 1), ("Y", ("FC",), True, True, 9))
            self.assertEqual(D.recommend(rows)["recommendation"], "Y")
        finally:
            D.GAPS = orig


if __name__ == "__main__":
    unittest.main()
