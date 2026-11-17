"""Stage 6B-E2D rules (evidence/stage6b/stage6be2d/contract.md). Expected values typed by hand."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6be2d as E  # noqa: E402


def res(npu, rng, mac=20736, status="VALID"):
    return dict(status=status, reasons=[], metrics=dict(npu_active=npu, npu_active_range=rng, mac_active=mac))


class PlacementIdentity(unittest.TestCase):
    """Amendment A: placement = the frozen manifest's expected placement (and the DRWL's), every other term unchanged."""
    def ident(self, exp_drwl):
        return dict(checks=dict(placement=False, regioncfg=True, n_base=True), expected=dict(placement=exp_drwl))

    def test_cases(self):
        rec = lambda p: [dict(placement=p)] * 10
        self.assertTrue(E.placement_identity(self.ident(0), rec(0), 0)["checks"]["placement"])         # DRAM / DRAM
        self.assertTrue(E.placement_identity(self.ident(1), rec(1), 1)["checks"]["placement"])         # SRAM / SRAM
        self.assertFalse(E.placement_identity(self.ident(0), rec(1), 0)["checks"]["placement"])        # DRAM expected, SRAM seen
        self.assertFalse(E.placement_identity(self.ident(1), rec(0), 1)["checks"]["placement"])        # SRAM expected, DRAM seen
        self.assertFalse(E.placement_identity(self.ident(1), rec(1)[:9] + [dict(placement=0)], 1)["checks"]["placement"])
        self.assertFalse(E.placement_identity(self.ident(1), [], 1)["checks"]["placement"])
        self.assertFalse(E.placement_identity(self.ident(0), rec(1), 1)["checks"]["placement_manifest_equals_drwl"])
        kept = E.placement_identity(dict(checks=dict(placement=True, regioncfg=False), expected=dict(placement=1)), rec(1), 1)
        self.assertFalse(kept["checks"]["regioncfg"])                                                  # other terms untouched


class Regression(unittest.TestCase):
    """Boots 440-442 (original session, kept unchanged) judged with the corrected code and a manifest copy whose boot
    numbers are 440-442: W0-P1 must now be VALID; swapping the expected placement must give CONFIG_MISMATCH."""
    RAW = pathlib.Path(__file__).resolve().parents[2] / "evidence/stage6b/stage6be2d/raw/evsweep_s6be2d_run_l500"
    WL = pathlib.Path(__file__).resolve().parents[2] / "evidence/stage6b/stage6be2d/workloads"

    def setUp(self):
        import json, shutil, tempfile
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        shutil.copytree(self.WL, self.d / "wl")
        m = json.loads((self.WL / E.MANIFEST).read_text())
        m["REF"]["boot"], m["W0-P0-L500"]["boot"], m["W0-P1-L500"]["boot"] = 440, 441, 442
        self.m = m
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(m))

    def test_boot442(self):
        import json
        self.assertEqual(E.config_result(self.RAW, self.d / "wl", "W0-P1-L500")["status"], "VALID")
        self.assertEqual(E.config_result(self.RAW, self.d / "wl", "W0-P0-L500")["status"], "VALID")
        self.assertEqual(E.config_result(self.RAW, self.d / "wl", "REF")["status"], "VALID")
        self.m["W0-P1-L500"]["placement"] = 0
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(self.m))
        r = E.config_result(self.RAW, self.d / "wl", "W0-P1-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("identity placement", r["reasons"])
        # the stage overlay is still wired in (since 6614ce8 the shared path checks the placement too; only the overlay
        # names a manifest / DRWL header disagreement)
        self.assertIn("identity placement_manifest_equals_drwl", r["reasons"])

    def test_wrong_regioncfg_and_digest(self):
        import json
        m = dict(self.m)
        m["W0-P0-L500"] = dict(m["W0-P0-L500"], config="e2d_w0p1", drwl_sha256=m["W0-P1-L500"]["drwl_sha256"], boot=441)
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(m))
        r = E.config_result(self.RAW, self.d / "wl", "W0-P0-L500")      # boot 442's folder under a DRAM expectation
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertTrue({"identity placement", "boot index"} <= set(r["reasons"]))
        m["W0-P1-L500"] = dict(self.m["W0-P1-L500"], drwl_sha256="0" * 64)
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(m))
        self.assertIn("workload sha256", E.config_result(self.RAW, self.d / "wl", "W0-P1-L500")["reasons"])


class RegionCfg(Regression):
    def test_wrong_regioncfg(self):
        import json, shutil
        raw = self.d / "raw"
        shutil.copytree(self.RAW, raw)
        f = raw / "conds/e2d_w0p1/wfe/raw_runs.json"
        runs = json.loads(f.read_text())
        for x in runs[1:]:
            x["record"]["regioncfg_irq"] = 0x15F          # the DDR value, while placement 1 expects 0x153
        f.write_text(json.dumps(runs))
        r = E.config_result(raw, self.d / "wl", "W0-P1-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("identity regioncfg", r["reasons"])


class Rules(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(E.PE_VELA, {500: 100310 - 53052, 1000: 200622 - 83142})
        self.assertEqual(E.INTERACTION_VELA, (200622 - 100310) - (83142 - 53052))
        self.assertEqual(E.H1UC, 20736)
        self.assertEqual([b for _, _, b in E.ORDER], list(range(449, 458)))       # Amendment A
        self.assertEqual(E.PLACEMENT, {"REF": 0, "W0-P0": 0, "W0-P1": 1, "W1-P0": 0, "W1-P1": 0})
        self.assertEqual([(c, L) for c, L, _ in E.ORDER][1:5], [("W0-P0", 500), ("W0-P1", 500), ("W1-P0", 500), ("W1-P1", 500)])
        self.assertEqual([(c, L) for c, L, _ in E.ORDER][5:], [("W1-P1", 1000), ("W1-P0", 1000), ("W0-P1", 1000), ("W0-P0", 1000)])

    def test_tol(self):
        self.assertEqual(E.tol(100000, [300, 400]), 1000)
        self.assertEqual(E.tol(100000, [700, 600]), 1300)

    def test_placement_effect(self):
        t = {500: 1000, 1000: 1000}
        self.assertEqual(E.placement_effect({500: 5000, 1000: 9000}, t, True), "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.placement_effect({500: -5000, 1000: -9000}, t, True), "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.placement_effect({500: 5000, 1000: -9000}, t, True), "PLACEMENT_EFFECT_NOT_RESOLVED")
        self.assertEqual(E.placement_effect({500: 1000, 1000: 9000}, t, True), "PLACEMENT_EFFECT_NOT_RESOLVED")   # = tol
        self.assertEqual(E.placement_effect({500: 5000, 1000: 9000}, t, False), "NOT_IDENTIFIABLE")

    def test_within(self):
        self.assertTrue(E.within(53000, 47258, 1000))      # 5742 <= 7088.7 + 1000
        self.assertFalse(E.within(56400, 47258, 1000))     # 9142 > 8088.7
        self.assertTrue(E.within(55300, 47258, 1000))      # 8042 <= 8088.7

    def test_fidelity(self):
        t = {500: 1000, 1000: 1000}
        ok = {500: 47258, 1000: 117480}
        self.assertEqual(E.fidelity(ok, t, {500: True, 1000: True}), "PLACEMENT_RESPONSE_CONSISTENT")
        self.assertEqual(E.fidelity({500: 47258, 1000: 50000}, t, {500: True, 1000: True}), "PLACEMENT_RESPONSE_DISCREPANCY")
        self.assertEqual(E.fidelity(ok, t, {500: True, 1000: False}), "FIDELITY_PARTIAL")
        self.assertEqual(E.fidelity({500: 0, 1000: 117480}, t, {500: True, 1000: False}), "PLACEMENT_RESPONSE_DISCREPANCY")
        self.assertEqual(E.fidelity(ok, t, {}), "NOT_COMPARABLE")

    def test_validity(self):
        p = dict(verdict="PASS")
        good = {k: dict(status="VALID") for k in ("REF", "a", "b")}
        self.assertEqual(E.validity(p, good, {"a": True, "b": True}), "VALID")
        self.assertEqual(E.validity(p, good, {"a": True, "b": False}), "PARTIAL_VALID")
        for s in ("UNSTABLE", "INVALID_OUTPUT", "INVALID_PMU"):
            self.assertEqual(E.validity(p, dict(good, a=dict(status=s)), {"b": True}), "PARTIAL_VALID", s)
        for s in ("CONFIG_MISMATCH", "UNMEASURED"):
            self.assertEqual(E.validity(p, dict(good, a=dict(status=s)), {"b": True}), "MEASUREMENT_INVALID", s)
        self.assertEqual(E.validity(dict(verdict="FAIL"), good, {"a": True}), "MEASUREMENT_INVALID")

    def test_mechanism(self):
        self.assertEqual(E.mechanism(), "MECHANISM_UNRESOLVED")

    def test_effects(self):
        r = {"W1-P0-L500": res(150000, 500), "W1-P1-L500": res(100000, 400), "W1-P0-L1000": res(260000, 600), "W1-P1-L1000": res(160000, 300)}
        e = E.effects(r, "W1", True)
        self.assertEqual(e["pe"], {500: 50000, 1000: 100000})
        self.assertEqual(e["tol_pe"], {500: 1000, 1000: 1600})          # max(1000, 900), max(1600, 900)
        self.assertEqual(e["le"], {"W1-P0": 110000, "W1-P1": 60000})
        self.assertEqual(e["tol_le"], {"W1-P0": 1500, "W1-P1": 1000})    # max(1500, 1100), max(1000, 700)
        self.assertEqual((e["interaction"], e["tol_interaction"]), (50000, 1800))   # max(1000, 1800)
        self.assertAlmostEqual(e["ratio"]["W1-P0"], 260000 / 150000)
        self.assertEqual(e["cls"], "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.effects(r, "W1", False), dict(usable=False))

    def test_key(self):
        self.assertEqual(E.key("REF", 500), "REF")
        self.assertEqual(E.key("W1-P0", 1000), "W1-P0-L1000")


if __name__ == "__main__":
    unittest.main()
