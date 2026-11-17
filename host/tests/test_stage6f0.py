"""Stage 6F-0 judge (contract evidence/stage6f0/contract.md). Expected values are hand-written fixtures."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6f0 as F  # noqa: E402


def op(level, p="", p_ext="", n=100, opi=0, model="m"):
    return dict(model=model, op=str(opi), family="DW", n_mac=str(n), level=level, p=str(p), p_ext=str(p_ext))


class GroupStatus(unittest.TestCase):
    def test_prediction_config_only_1pct(self):
        rows = [op("CONFIGURATION_MATCHED", 1000)]
        self.assertEqual(F.group_status(rows, 1010)[0], "PREDICTION_AGREES")
        self.assertEqual(F.group_status(rows, 1011)[0], "PREDICTION_DISAGREES")
        self.assertEqual(F.group_status(rows, 989.9)[0], "PREDICTION_DISAGREES")

    def test_prediction_rule_5pct(self):
        rows = [op("EXACT_VALIDATED", 600), op("CLASS_SUPPORTED", 400)]
        self.assertEqual(F.group_status(rows, 1050), ("PREDICTION_AGREES", 1000.0))
        self.assertEqual(F.group_status(rows, 1051)[0], "PREDICTION_DISAGREES")
        mixed = [op("CONFIGURATION_MATCHED", 600), op("EXACT_VALIDATED", 400)]
        self.assertEqual(F.group_status(mixed, 1040)[0], "PREDICTION_AGREES")     # 5 %, not 1 %

    def test_extrapolation_band(self):
        rows = [op("CLASS_SUPPORTED", 500), op("EXTRAPOLATED", "", 350)]           # sum 850
        self.assertEqual(F.group_status(rows, 1000), ("EXTRAPOLATION_CONSISTENT", 850.0))
        self.assertEqual(F.group_status(rows, 1001)[0], "EXTRAPOLATION_REFUTED")  # 850 < 0.85*1001
        self.assertEqual(F.group_status([op("EXTRAPOLATED", "", 1050)], 1000)[0], "EXTRAPOLATION_CONSISTENT")
        self.assertEqual(F.group_status([op("EXTRAPOLATED", "", 1051)], 1000)[0], "EXTRAPOLATION_REFUTED")
        self.assertEqual(F.group_status([op("EXTRAPOLATED", "", 36864)], 16128)[0], "EXTRAPOLATION_REFUTED")

    def test_not_testable(self):
        rows = [op("EXTRAPOLATED", "", 300), op("INVALID_OR_UNSTABLE")]
        self.assertEqual(F.group_status(rows, 1000), ("NOT_TESTABLE", 300.0))


class Level(unittest.TestCase):
    def setUp(self):
        self.g = {"kws_micronet_m": {"G_0": dict(ops=[0], status="EXTRAPOLATION_REFUTED"),
                                     "G_V": dict(ops=[2, 4], status="PREDICTION_AGREES"),
                                     "G_R": dict(ops=[1, 3], status="EXTRAPOLATION_REFUTED")}}

    def lv(self, level, opi, model="kws_micronet_m"):
        return F.level_6f(op(level, opi=opi, model=model), self.g)[0]

    def test_levels(self):
        self.assertEqual(self.lv("EXACT_VALIDATED", 2), "DIRECT_IN_MODEL")
        self.assertEqual(self.lv("EXACT_VALIDATED", 2, "rnnoise_INT8"), "DIRECT_ISOLATED")
        self.assertEqual(self.lv("CONFIGURATION_MATCHED", 9, "rnnoise_INT8"), "CONFIGURATION")
        self.assertEqual(self.lv("CLASS_SUPPORTED", 3), "CLASS")                  # multi-op group: no change
        self.assertEqual(self.lv("EXTRAPOLATED", 0), "REFUTED")                   # single-op group refuted
        self.assertEqual(self.lv("EXTRAPOLATED", 1), "EXTRAPOLATED")              # multi-op group refuted
        self.g["ad_medium_int8"] = {"G_0": dict(ops=[0], status="EXTRAPOLATION_CONSISTENT")}
        self.assertEqual(self.lv("EXTRAPOLATED", 0, "ad_medium_int8"), "EXTRAPOLATED")   # single-op, consistent
        self.assertEqual(self.lv("EXTRAPOLATED", 5, "rnnoise_INT8"), "EXTRAPOLATED")
        self.assertEqual(self.lv("INVALID_OR_UNSTABLE", 3), "UNSUPPORTED_OR_UNSTABLE")
        self.assertEqual(self.lv("UNSUPPORTED", 3, "rnnoise_INT8"), "UNSUPPORTED_OR_UNSTABLE")

    def test_group_of(self):
        self.assertEqual(F.group_of("ad_medium_int8", 8), "G_V")
        self.assertEqual(F.group_of("kws_micronet_m", 8), "G_R")
        self.assertEqual(F.group_of("kws_micronet_m", 0), "G_0")
        self.assertIsNone(F.group_of("vww4_128_128_INT8", 0))


def r6f(level, n, p=None, p_ext=None):
    return dict(level_6f=level, n_mac=n, p=p, p_ext=p_ext)


class Coverage(unittest.TestCase):
    def test_metrics(self):
        rows = [r6f("DIRECT_IN_MODEL", 40, 400.0), r6f("CLASS", 10, 50.0), r6f("EXTRAPOLATED", 20, None, 70.0),
                r6f("REFUTED", 20, None, 300.0), r6f("UNSUPPORTED_OR_UNSTABLE", 10)]
        g = {"G_V": dict(mac=400.0, status="PREDICTION_AGREES"), "G_0": dict(mac=150.0, status="EXTRAPOLATION_REFUTED"),
             "G_R": dict(mac=450.0, status="NOT_TESTABLE")}
        cv = F.coverage(rows, 100, 1000.0, g, True)
        self.assertAlmostEqual(cv["c"], 0.5)
        self.assertEqual((cv["P"], cv["P_ext_6d"], cv["P_ext_6f"]), (450.0, 820.0, 520.0))
        self.assertAlmostEqual(cv["V"], 0.4)
        self.assertEqual(cv["D"], 1.0)
        self.assertAlmostEqual(cv["extrap_dependence"], 0.4)
        self.assertEqual(F.coverage(rows, 100, 1000.0, g, False)["D"], 0.0)
        self.assertEqual(F.coverage(rows, 100, 1000.0, None, False)["V"], 0.0)

    def test_compute_6f(self):
        self.assertEqual(F.compute_6f(dict(D=1.0, V=0.90), "QUANTITATIVELY_EXPLAINED"), "PROSPECTIVELY_EXPLAINED")
        self.assertEqual(F.compute_6f(dict(D=1.0, V=0.89), "QUANTITATIVELY_EXPLAINED"), "DECOMPOSED_PARTIALLY_PREDICTED")
        self.assertEqual(F.compute_6f(dict(D=1.0, V=0.95), "NOT_EXPLAINED"), "DECOMPOSED_PARTIALLY_PREDICTED")
        self.assertEqual(F.compute_6f(dict(D=0.0, V=0.0), "PARTIALLY_EXPLAINED"), "PARTIALLY_EXPLAINED")
        self.assertEqual(F.compute_6f(dict(D=0.99, V=0.95), "QUANTITATIVELY_EXPLAINED"), "QUANTITATIVELY_EXPLAINED")

    def test_runtime_fidelity(self):
        self.assertEqual(F.runtime_6f(True, 1.0, 2.0), "SERIAL_DECOMPOSITION_ONLY")
        self.assertEqual(F.runtime_6f(False, 1.0, 2.0), "LOWER_BOUND_ONLY")
        self.assertEqual(F.runtime_6f(None, 1.0, 2.0), "LOWER_BOUND_ONLY")
        self.assertEqual(F.runtime_6f(None, None, 2.0), "NOT_EXPLAINED")
        self.assertEqual(F.fidelity_6f(True, 0.0, 0.0), "GROUP_DIRECTION_MEASURED")
        self.assertEqual(F.fidelity_6f(False, 0.05, 0.05), "FAMILY_DIRECTION_ONLY")
        self.assertEqual(F.fidelity_6f(False, 0.05, 0.049), "NO_EVIDENCE")


class Vela(unittest.TestCase):
    def test_cls(self):
        self.assertEqual(F.vela_cls(850, 1000, 10), "OVER")
        self.assertEqual(F.vela_cls(1150, 1000, 10), "UNDER")
        self.assertEqual(F.vela_cls(1000, 1000, 10), "AGREE")
        self.assertEqual(F.vela_cls(910, 1000, 10), "INSUFFICIENT_EVIDENCE")     # |910-900| <= 10
        self.assertEqual(F.vela_cls(911, 1000, 10), "AGREE")
        self.assertEqual(F.vela_cls(940, 1000, 10), "AGREE")
        self.assertEqual(F.vela_cls(1090, 1000, 10), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(F.vela_cls(889, 1000, 10), "OVER")

    def test_terms(self):
        inv = [dict(model="kws_micronet_m", tflite_op_index="0", vela_op_cycles="100", vela_npu_cycles="100"),
               dict(model="kws_micronet_m", tflite_op_index="1", vela_op_cycles="300", vela_npu_cycles="50"),
               dict(model="kws_micronet_m", tflite_op_index="1", vela_op_cycles="", vela_npu_cycles="")]
        t = F.vela_terms(inv, {("kws_micronet_m", 0): "PK", ("kws_micronet_m", 1): "DW"})["kws_micronet_m"]
        self.assertEqual((t["cycles_total"], t["cycles_npu"]), (400.0, 150.0))
        self.assertAlmostEqual(t["mem_dominated_share"], 0.75)
        self.assertEqual(t["families"]["DW"], dict(share=0.75, mem_share_within=1.0))
        self.assertEqual(t["families"]["PK"], dict(share=0.25, mem_share_within=0.0))


class Recommend(unittest.TestCase):
    def test_fixed_table(self):
        r = F.recommend()
        self.assertEqual(r["recommendation"], "X_LAT")
        t = {x["name"]: x for x in r["table"]}
        self.assertEqual((t["X_LAT"]["score"], t["X_FIRST"]["score"], t["X3_5M"]["score"]), (9, 8, 7))
        self.assertEqual([x["name"] for x in r["table"] if x["eligible"]], ["X_LAT", "X_FIRST", "X_DW"])

    def test_rules(self):
        saved = F.CANDIDATES
        try:
            F.CANDIDATES = (("A", "YYYYYYYYYY", 13, False), ("B", "YYYYYYYYNN", 6, False), ("C", "YYYYYYYYNN", 4, False))
            self.assertEqual(F.recommend()["recommendation"], "C")       # A over budget; B/C tie -> fewer boots
            F.CANDIDATES = (("B", "YYYYYYYYNN", 6, False), ("C", "YYYYYYYYNN", 6, False))
            self.assertEqual(F.recommend()["recommendation"], "B")       # full tie -> table order
            F.CANDIDATES = (("A", "YYYYYYYYYY", 4, True), ("B", "YYYNYYYYYY", 4, False), ("C", "YYYYNYYYYY", 4, False),
                            ("D", "YYYYYNYYYY", 4, False))
            self.assertIsNone(F.recommend()["recommendation"])          # excluded, d/e/f each N
            F.CANDIDATES = (("A", "YYYYYYYYYY", 12, False),)
            self.assertEqual(F.recommend()["recommendation"], "A")       # boundary 12 eligible
        finally:
            F.CANDIDATES = saved


class Serial(unittest.TestCase):
    def test_ratios(self):
        def stats(npu, mac):
            return {"1": {e: [v, 0] for e, v in {"35": npu, "48": mac, "51": 1, "64": 1, "80": 1, "81": 1}.items()},
                    "2": {e: [1, 0] for e in ("130", "135", "386")},
                    "3": {e: [1, 0] for e in ("387", "640", "642", "656", "658")}}
        x3 = {"results": {"x3_kws_B0": {"stats": stats(100.0, 50)}, "x3_kws_B1": {"stats": stats(120.0, 50)},
                          "x3_ad_B0": {"stats": stats(200.0, 80)}, "x3_ad_B1": {"stats": stats(210.0, 81)}},
              "hypotheses": {"h_p": {"kws_micronet_m": {"35": {"tol": 5, "holds": True}},
                                     "ad_medium_int8": {"35": {"tol": 5, "holds": False}}}}}
        g = {"kws_micronet_m": {"G_0": {"npu": 40.0}, "G_V": {"npu": 40.0}, "G_R": {"npu": 45.0}},
             "ad_medium_int8": {"G_0": {"npu": 100.0}, "G_V": {"npu": 100.0}, "G_R": {"npu": 10.0}}}
        s = F.serial(x3, g)
        k = s["kws_micronet_m"]
        self.assertEqual(k["group_sum"], 125.0)
        self.assertAlmostEqual(k["ratios"]["(serial-orig)/orig"], 0.2)
        self.assertAlmostEqual(k["ratios"]["(S-orig)/S"], 0.2)
        self.assertAlmostEqual(k["ratios"]["(S-orig)/orig"], 0.25)
        self.assertAlmostEqual(k["ratios"]["(S-serial)/serial"], 5 / 120)
        self.assertTrue(k["schedule_invariant_mac"] and k["partition_holds"])
        self.assertFalse(s["ad_medium_int8"]["schedule_invariant_mac"] or s["ad_medium_int8"]["partition_holds"])


if __name__ == "__main__":
    unittest.main()
