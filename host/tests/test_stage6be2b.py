"""Stage 6B-E2B rules (evidence/stage6b/stage6be2b/contract.md). Expected values typed by hand."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6be2b as E  # noqa: E402


def res(npu, rng, status="VALID"):
    return dict(status=status, metrics=dict(npu_active=npu, npu_active_range=rng))


class Rules(unittest.TestCase):
    def test_tolerance(self):
        self.assertEqual(E.tolerance(100000, 300, 400), 1000)      # 1 % floor
        self.assertEqual(E.tolerance(100000, 700, 600), 1300)      # range sum

    def test_primary(self):
        self.assertEqual(E.primary(30000, 30090, 1000), "CONSISTENT")
        self.assertEqual(E.primary(34600, 30090, 1000), "CONSISTENT")     # 4510 <= 4513.5 + 1000
        self.assertEqual(E.primary(35700, 30090, 1000), "DISCREPANT")     # 5610 > 5513.5
        self.assertEqual(E.primary(35000, 30090, 1000), "CONSISTENT")     # 4910: above 4513.5, inside + tol
        self.assertEqual(E.primary(0, 30090, 1000), "DISCREPANT")         # no response on the board
        self.assertEqual(E.primary(30000, 30090, 15100), "INSUFFICIENT")  # 15100 > 15045
        self.assertEqual(E.primary(30000, 30090, 15000), "CONSISTENT")

    def test_secondary(self):
        self.assertEqual(E.secondary(1.60, 1.5672, 1000, 100000), "CONSISTENT")   # 0.0328 <= 0.0851 + 0.01
        self.assertEqual(E.secondary(1.70, 1.5672, 1000, 100000), "DISCREPANT")   # 0.1328 > 0.0951
        self.assertEqual(E.secondary(1.66, 1.5672, 1000, 100000), "CONSISTENT")   # 0.0928: inside only with tol/B500

    def test_history(self):
        self.assertEqual(E.history(100500, 200, 100000, 200), "REPRODUCED")   # 500 <= 1000
        self.assertEqual(E.history(101200, 200, 100000, 200), "DIFFERENT")
        self.assertEqual(E.history(101200, 1500, 100000, 0), "REPRODUCED")    # ranges 1500 >= 1200

    def test_auxiliary(self):
        b = {130: 1000, 135: 1000, 386: 1000, 391: 1000}
        m5 = dict(mac=20736, dpu=100, beats=b)
        self.assertEqual(E.auxiliary(m5, dict(m5), 5000, 1000)["cls"], "MEMORY_SERVICE_RESPONSE")
        self.assertEqual(E.auxiliary(m5, dict(m5, beats={**b, 386: 1010}), 5000, 1000)["cls"], "MEMORY_SERVICE_RESPONSE")
        self.assertIn("beats", E.auxiliary(m5, dict(m5, beats={**b, 386: 1011}), 5000, 1000)["cls"])
        self.assertIn("MAC_ACTIVE", E.auxiliary(m5, dict(m5, mac=20737), 5000, 1000)["cls"])
        self.assertIn("MAC_DPU_ACTIVE", E.auxiliary(m5, dict(m5, dpu=101), 5000, 1000)["cls"])
        self.assertIn("NPU_ACTIVE", E.auxiliary(m5, dict(m5), 1000, 1000)["cls"])

    def test_workload(self):
        w = E.workload(res(100000, 300), res(130000, 400), dict(v500=53052, v1000=83142))
        self.assertEqual((w["d_board"], w["d_vela"], w["tol"], w["primary"]), (30000, 30090, 1000, "CONSISTENT"))
        self.assertAlmostEqual(w["slope_board"], 60.0)
        self.assertAlmostEqual(w["r_board"], 1.3)
        self.assertEqual(w["secondary"], "DISCREPANT")                    # 1.3 vs 1.567
        self.assertAlmostEqual(w["abs_err_500"], (100000 - 53052) / 53052)
        self.assertAlmostEqual(w["abs_err_1000"], (130000 - 83142) / 83142)
        self.assertEqual(E.workload(res(1, 1, "UNSTABLE"), res(1, 1), {})["primary"], "INSUFFICIENT")
        self.assertEqual(E.workload(res(1, 1), res(1, 1, "INVALID_PMU"), {})["primary"], "NOT_EVALUABLE")

    def test_verdict(self):
        ok = {k: dict(status="VALID") for k in E.KEYS}
        c, d, i = dict(primary="CONSISTENT"), dict(primary="DISCREPANT"), dict(primary="INSUFFICIENT")
        p = dict(verdict="PASS")
        self.assertEqual(E.verdict(p, ok, dict(G12=c, CONV=c)), "SENSITIVITY_CONSISTENT")
        self.assertEqual(E.verdict(p, ok, dict(G12=c, CONV=d)), "SENSITIVITY_DISCREPANCY_OBSERVED")
        self.assertEqual(E.verdict(p, ok, dict(G12=i, CONV=d)), "SENSITIVITY_DISCREPANCY_OBSERVED")
        self.assertEqual(E.verdict(p, ok, dict(G12=i, CONV=c)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.verdict(p, ok, dict(G12=dict(primary="NOT_EVALUABLE"), CONV=c)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.verdict(dict(verdict="FAIL"), ok, dict(G12=c, CONV=c)), "MEASUREMENT_INVALID")
        for s in ("CONFIG_MISMATCH", "UNMEASURED", "INVALID_OUTPUT", "INVALID_PMU"):
            self.assertEqual(E.verdict(p, dict(ok, **{"G12-L1000": dict(status=s)}), dict(G12=c, CONV=c)), "MEASUREMENT_INVALID", s)
        self.assertEqual(E.verdict(p, dict(ok, **{"G12-L1000": dict(status="UNSTABLE")}), dict(G12=i, CONV=c)), "INSUFFICIENT_EVIDENCE")


class BootCheck(unittest.TestCase):
    def test_stop(self):
        orig = E.config_result
        try:
            for st, stop in (("CONFIG_MISMATCH", True), ("UNMEASURED", True), ("UNSTABLE", False), ("VALID", False), ("INVALID_PMU", False)):
                E.config_result = lambda root, wl, key, st=st: dict(status=st, reasons=[])
                self.assertEqual(E.boot_check("r", "w", "G12-L1000")["stop"], stop, st)
        finally:
            E.config_result = orig


class Environment(unittest.TestCase):
    """environment() on a synthetic RUN table (rows_of and capabilities replaced)."""
    M = dict(drwl_sha256="d", image=dict(boot_sha256="b1"), boot=438, ta_ext_rlatency=1000)
    ROW = dict(workload_sha256="d", boot_sha256="b1", fpga_image="FI101_x", host_boot_index="438", condition="wfe")

    def run_env(self, row=None, caps=None, ident=None):
        import json, tempfile
        d = pathlib.Path(tempfile.mkdtemp()); f = d / "wfe"; f.mkdir()
        (d / "capabilities.json").write_text(json.dumps(caps if caps is not None else dict(npu_config=0x2000251A, ta_ext_rlatency=1000)))
        orig = E.BB.rows_of
        E.BB.rows_of = lambda folder: [row or self.ROW]
        try:
            return E.environment(f, self.M, ident or dict(checks=dict(capabilities=True)))
        finally:
            E.BB.rows_of = orig

    def test_ok(self):
        self.assertEqual(self.run_env(), [])

    def test_each_term(self):
        self.assertIn("workload sha256", self.run_env(row=dict(self.ROW, workload_sha256="x")))
        self.assertIn("image boot_sha256", self.run_env(row=dict(self.ROW, boot_sha256="x")))
        self.assertIn("fpga image", self.run_env(row=dict(self.ROW, fpga_image="X")))
        self.assertIn("boot index", self.run_env(row=dict(self.ROW, host_boot_index="437")))
        self.assertIn("condition", self.run_env(row=dict(self.ROW, condition="busy")))
        self.assertIn("NPU MAC count", self.run_env(caps=dict(npu_config=0x20002519, ta_ext_rlatency=1000)))
        self.assertIn("TA EXT RLATENCY read-back", self.run_env(caps=dict(npu_config=0x2000251A, ta_ext_rlatency=500)))
        self.assertIn("identity capabilities", self.run_env(ident=dict(checks=dict(capabilities=False))))
        self.assertEqual(self.run_env(ident=dict(checks=dict(runs=False, one_crc=False))), [])   # PMU / output terms elsewhere


if __name__ == "__main__":
    unittest.main()
