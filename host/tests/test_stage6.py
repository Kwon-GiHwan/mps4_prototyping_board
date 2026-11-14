"""stage6.py: applicability tiers (T0/T1/T2/U) on synthetic rows, coverage, the comparison and verdict rules of
evidence/stage6/rules.md, and the full run on the archived inventory and driver_m7 data. Expected values typed here."""
import json, pathlib, shutil, sys, tempfile, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6 as S


def row(**kw):
    r = dict(model="m", scheduled_id="1", tflite_op_index="0", tflite_op="CONV_2D", npu_op="Conv2D", kernel="1x1",
             stride="1x1", cin="16", cout="96", traversal="PartKernel", ofm_block="6x12x96", npu_ofm_hwc="24x24x96",
             mac_count="884736", vela_npu_cycles="100", vela_mac_cycles="50", vela_ao_cycles="40", weight_bytes="2752",
             ofm_format="NHWC", cpu="0", ifm_memory="Dram", ofm_memory="Dram")
    r.update(kw)
    return r


DT = {"m": {"ops": {"0": {"inputs": ["INT8"], "outputs": ["INT8"]}, "1": {"inputs": ["INT8"], "outputs": ["INT16"]}}}}


class Tiers(unittest.TestCase):
    def test_mac(self):
        self.assertEqual(S.mac_tier(row()), ("T0", 384))
        self.assertEqual(S.mac_tier(row(cin="24", ofm_block="8x8x96")), ("T1_INTERP", 384))       # inside [16, 32], 384 constant
        self.assertEqual(S.mac_tier(row(cin="64")), ("T1_EXTRAP", None))                          # outside the range
        self.assertEqual(S.mac_tier(row(traversal="DepthFirst", cin="56", ofm_block="8x8x96")), ("T1_EXTRAP", None))  # 640/768 not constant
        self.assertEqual(S.mac_tier(row(traversal="DepthFirst", cin="48")), ("T0", 768))
        self.assertEqual(S.mac_tier(row(kernel="3x3", cin="40", ofm_block="9x9x32")), ("T1_INTERP", 768))
        self.assertEqual(S.mac_tier(row(kernel="10x4")), ("T2", None))
        self.assertEqual(S.mac_tier(row(npu_op="Add", mac_count="0")), ("U", None))
        self.assertEqual(S.mac_tier(row(npu_op="MemoryCopy")), ("U", None))
        self.assertEqual(S.mac_tier(row(mac_count="0")), ("U", None))                            # a 0-MAC Conv row

    def test_ao(self):
        self.assertEqual(S.ao_tier(row(), DT), ("T1_INTERP", 15.60))
        self.assertEqual(S.ao_tier(row(tflite_op_index="1"), DT), ("U", None))                   # not INT8 out
        self.assertEqual(S.ao_tier(row(npu_op="DepthwiseConv2D"), DT), ("T2", None))
        self.assertEqual(S.ao_tier(row(npu_op="Add"), DT), ("T1_INTERP", 16.0))
        self.assertEqual(S.ao_tier(row(npu_op="Add", ofm_format="NHCWB16"), DT), ("U", None))   # chaining not decidable
        self.assertEqual(S.ao_tier(row(vela_npu_cycles="0", mac_count="0"), DT), ("U", None))   # fused
        self.assertEqual(S.ao_tier(row(cpu="1"), DT), ("U", None))

    def test_geometry(self):
        self.assertEqual(S.ao_elements(row(npu_ofm_hwc="24x24x97")), 24 * 24 * 112)
        self.assertEqual(S.spatial_blocks(row(npu_ofm_hwc="24x24x96", ofm_block="6x12x96")), 8)
        self.assertEqual(S.spatial_blocks(row(ofm_block="xx")), 0)
        self.assertEqual(S.wd_tier(row()), "T0"); self.assertEqual(S.wd_tier(row(cin="32")), "PROXY")
        self.assertEqual(S.wd_tier(row(weight_bytes="0")), "U")


class Rules(unittest.TestCase):
    def test_compare(self):
        e = dict(calibrated_coverage=0.85, calibrated_estimate=1080)
        self.assertEqual(S.compare(e, 1000)["status"], "CONSISTENT")
        self.assertEqual(S.compare(dict(e, calibrated_estimate=1101), 1000)["status"], "NOT_CONSISTENT")
        self.assertEqual(S.compare(dict(e, calibrated_coverage=0.79), 1000)["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(S.compare(e, None)["status"], "BASELINE_NOT_COMPARABLE")

    def test_verdict(self):
        self.assertEqual(S.verdict(False, [0.9], ["CONSISTENT"], False), "BASELINE_NOT_COMPARABLE")
        self.assertEqual(S.verdict(True, [0.9, 0.4], ["CONSISTENT", "CONSISTENT"], False), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(S.verdict(True, [0.9], ["CONSISTENT"], True), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(S.verdict(True, [0.9], ["CONSISTENT"], False), "SUPPORTED_WITHIN_SCOPE")
        self.assertEqual(S.verdict(True, [0.9], ["NOT_CONSISTENT"], False), "NOT_SUPPORTED")
        self.assertEqual(S.verdict(True, [0.6], ["INSUFFICIENT_EVIDENCE"], False), "PARTIALLY_SUPPORTED")

    def test_shares_and_estimate(self):
        ops = S.classify([row(), row(scheduled_id="2", cin="64"), row(scheduled_id="3", npu_op="Add", mac_count="0",
                                                                      weight_bytes="0"),
                          row(scheduled_id="4", cin="24", ofm_block="8x8x96")], DT)          # T0, T1_EXTRAP, -, T1_INTERP
        e = S.estimate(ops)
        self.assertAlmostEqual(e["mac"]["calibrated_coverage"], 2 / 3)
        self.assertAlmostEqual(e["mac"]["calibrated_estimate"], 2 * 884736 / 384)
        n = 24 * 24 * 96
        self.assertAlmostEqual(e["ao"]["calibrated_estimate"], 3 * n / 15.60 + n / 16)
        self.assertAlmostEqual(e["wd"]["calibrated_estimate"], 60.6 * 2 * 8 + 96.7)
        self.assertEqual(e["wd"]["proxy_total"], (8 + 8 + 9) * 2752)                       # 8x8x96 block: 3 x 3


class Baseline(unittest.TestCase):
    def test_invalid_run(self):
        from unittest import mock
        d = pathlib.Path(tempfile.mkdtemp())
        try:
            m = "kws_micronet_m"
            shutil.copytree(S.M7_RAW / m, d / m)
            import csv
            rows = list(csv.DictReader(open(d / m / "runs.csv")))
            rows[0]["run_valid"] = "False"
            with open(d / m / "runs.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            self.assertTrue(S.baseline(m)["checks"]["all_valid"])
            with mock.patch.object(S, "M7_RAW", d):
                self.assertFalse(S.baseline(m)["checks"]["all_valid"])
        finally:
            shutil.rmtree(d)


class Run(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.s = S.run(cls.d)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_all_models(self):
        self.assertEqual(sorted(self.s["models"]), sorted(S.MODELS))
        for m, d in self.s["models"].items():
            self.assertTrue(d["baseline"]["ok"], m)
        self.assertEqual(self.s["models"]["wav2letter_pruned_int8"]["baseline"]["wd_active"], 1133549)
        self.assertEqual(sum(d["n_ops"] for d in self.s["models"].values()), 591)
        for f in ("model_operator_inventory.csv", "vela_kernel_mapping.csv", "unit_model_applicability.csv",
                  "model_activity_estimates.csv", "whole_model_comparison.csv", "anomaly_attribution_matrix.csv"):
            self.assertTrue((pathlib.Path(self.d) / f).exists(), f)

    def test_no_numbers_for_unsupported(self):
        ops = S.classify(__import__("csv").DictReader(open(S.INVENTORY)), json.loads(S.DTYPES.read_text()))
        self.assertTrue(all(o["mac_rate"] is None for o in ops if o["mac_tier"] in ("T1_EXTRAP", "T2", "U")))
        self.assertTrue(all(o["ao_rate"] is None for o in ops if o["ao_tier"] in ("T2", "U")))

    def test_matrix(self):
        self.assertEqual(len(self.s["matrix"]), 1 + 2 + 2 + 1 + 1 + 1 + 7)
        w2l = self.s["models"]["wav2letter_pruned_int8"]["comparison"]["ao"]
        self.assertEqual(w2l["status"], "CONSISTENT")


if __name__ == "__main__":
    unittest.main()
