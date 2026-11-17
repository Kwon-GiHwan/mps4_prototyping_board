"""Shared identity: expected placement (maintenance 2026-11-17, Stage 6B-E2E-B Phase 0).

stage4k.identity / stage4aoe.identity_a1 take the expected placement as an argument (default 0, the only value before
this change); stage6bb.identity_of passes the frozen manifest's. Fixtures: E2D's original session, boot 441 (W0-P0,
placement 0, REGIONCFG 0x15F) and boot 442 (W0-P1, placement 1, REGIONCFG 0x153). Expected values typed by hand.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis"), str(REPO / "host/lib")]
import stage4k as K  # noqa: E402
import stage4aoe as AOE  # noqa: E402
import stage6bb as BB  # noqa: E402

RAW = REPO / "evidence/stage6b/stage6be2d/raw/evsweep_s6be2d_run_l500/conds"
WL = REPO / "evidence/stage6b/stage6be2d/workloads"
CAPS = str(WL / "caps_l500.json")
DRAM, SRAM = RAW / "e2d_w0p0/wfe", RAW / "e2d_w0p1/wfe"
MAINT = REPO / "evidence/maint/identity_placement"


def k(folder, cfg, *exp):
    return K.identity(folder, WL, cfg, CAPS, *exp)


class ExpectedObserved(unittest.TestCase):
    def test_dram_dram(self):
        r = k(DRAM, "e2d_w0p0", 0)
        self.assertTrue(r["checks"]["placement"] and r["checks"]["regioncfg"] and r["ok"])

    def test_sram_sram(self):
        r = k(SRAM, "e2d_w0p1", 1)
        self.assertTrue(r["checks"]["placement"] and r["checks"]["regioncfg"] and r["ok"])

    def test_dram_expected_sram_observed(self):
        r = k(SRAM, "e2d_w0p1", 0)
        self.assertFalse(r["checks"]["placement"])
        self.assertFalse(r["checks"]["regioncfg"])          # 0x153 seen, 0x15F expected
        self.assertFalse(r["ok"])

    def test_sram_expected_dram_observed(self):
        r = k(DRAM, "e2d_w0p0", 1)
        self.assertFalse(r["checks"]["placement"])
        self.assertFalse(r["checks"]["regioncfg"])
        self.assertFalse(r["ok"])

    def test_unknown_placement(self):
        self.assertFalse(k(SRAM, "e2d_w0p1", 2)["checks"]["regioncfg"])

    def test_one_run_off(self):
        d = pathlib.Path(tempfile.mkdtemp()) / "wfe"
        shutil.copytree(SRAM, d)
        runs = json.loads((d / "raw_runs.json").read_text())
        runs[-1]["record"]["placement"] = 0
        (d / "raw_runs.json").write_text(json.dumps(runs))
        self.assertFalse(k(d, "e2d_w0p1", 1)["checks"]["placement"])


class RegionCfg(unittest.TestCase):
    def test_wrong_regioncfg(self):
        d = pathlib.Path(tempfile.mkdtemp()) / "wfe"
        shutil.copytree(SRAM, d)
        runs = json.loads((d / "raw_runs.json").read_text())
        for x in runs[1:]:
            x["record"]["regioncfg_irq"] = 0x15F
        (d / "raw_runs.json").write_text(json.dumps(runs))
        r = k(d, "e2d_w0p1", 1)
        self.assertTrue(r["checks"]["placement"])
        self.assertFalse(r["checks"]["regioncfg"])
        self.assertFalse(r["ok"])


class Defaults(unittest.TestCase):
    """Backward compatibility: no argument = expected placement 0, the behaviour every historical judge used."""
    def test_k_default(self):
        self.assertEqual(k(SRAM, "e2d_w0p1"), k(SRAM, "e2d_w0p1", 0))
        self.assertEqual(k(DRAM, "e2d_w0p0"), k(DRAM, "e2d_w0p0", 0))
        self.assertFalse(k(SRAM, "e2d_w0p1")["checks"]["placement"])

    def test_a1_default_and_pass_through(self):
        a0 = AOE.identity_a1(SRAM, WL, "e2d_w0p1", CAPS)
        self.assertFalse(a0["checks"]["placement"])
        self.assertTrue(a0["checks"]["drwl_placement"])     # RUN = DRWL header placement 1
        a1 = AOE.identity_a1(SRAM, WL, "e2d_w0p1", CAPS, 1)
        self.assertTrue(a1["checks"]["placement"] and a1["checks"]["regioncfg"] and a1["ok"])
        self.assertFalse(AOE.identity_a1(DRAM, WL, "e2d_w0p0", CAPS, 1)["checks"]["placement"])


class ManifestDriven(unittest.TestCase):
    """identity_of takes the expectation from the frozen manifest, never from a RUN."""
    def man(self, name, key):
        return json.loads((WL / name).read_text())[key]

    def test_boot442_rejudge(self):
        m = self.man("e2d_manifest_a.json", "W0-P1-L500")
        self.assertEqual(m["placement"], 1)
        self.assertTrue(BB.identity_of(SRAM, WL, "e2d_w0p1", m, str(WL / m["caps_ref"]))["ok"])

    def test_original_manifest_unchanged(self):
        m = self.man("e2d_manifest.json", "W0-P1-L500")      # frozen before Amendment A: no placement field
        self.assertNotIn("placement", m)
        r = BB.identity_of(SRAM, WL, "e2d_w0p1", m, str(WL / m["caps_ref"]))
        self.assertFalse(r["ok"])
        self.assertEqual([c for c, v in r["checks"].items() if not v], ["placement"])

    def test_manifest_dram_vs_sram_records(self):
        m = dict(self.man("e2d_manifest_a.json", "W0-P1-L500"), placement=0)
        r = BB.identity_of(SRAM, WL, "e2d_w0p1", m, str(WL / m["caps_ref"]))
        self.assertFalse(r["checks"]["placement"])

    def test_reference_kind(self):
        m = dict(self.man("e2d_manifest_a.json", "REF"), placement=1)  # a reference expecting SRAM: its RUNs are DRAM
        folder = RAW / m["config"] / "wfe"
        self.assertFalse(BB.identity_of(folder, WL, m["config"], m, str(WL / m["caps_ref"]))["checks"]["placement"])

    def test_digest(self):
        m = dict(self.man("e2d_manifest_a.json", "W0-P1-L500"), boot=442)
        ident = BB.identity_of(SRAM, WL, "e2d_w0p1", m, str(WL / m["caps_ref"]))
        self.assertNotIn("workload sha256", BB.environment(SRAM, WL, "e2d_w0p1", m, str(WL / m["caps_ref"]), ident))
        bad = dict(m, drwl_sha256="0" * 64)
        self.assertIn("workload sha256", BB.environment(SRAM, WL, "e2d_w0p1", bad, str(WL / m["caps_ref"]), ident))


class AllCallPaths(unittest.TestCase):
    """Every identity-path folder, judged with the current code, against the committed before-change results: only
    the three W0-P1 placement terms under a placement-1 manifest entry may change (False -> True)."""
    def test_regression(self):
        d = pathlib.Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, str(MAINT / "regression.py"), str(REPO), str(REPO), str(d / "after.json")],
                       check=True, capture_output=True)
        p = subprocess.run([sys.executable, str(MAINT / "compare.py"), str(MAINT / "before.json"), str(d / "after.json"),
                            str(d / "cmp.json")], capture_output=True)
        c = json.loads((d / "cmp.json").read_text())
        self.assertEqual(p.returncode, 0)
        self.assertEqual((c["verdict"], c["folders"], c["same"], len(c["expected_changes"]), c["unexpected"]),
                         ("REGRESSION_PASS", 76, 152, 3, []))


class CompareGate(unittest.TestCase):
    """compare.py itself: an unexpected difference must give REGRESSION_FAIL (exit 1)."""
    def run_cmp(self, after: dict) -> tuple[int, dict]:
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "a.json").write_text(json.dumps(after))
        p = subprocess.run([sys.executable, str(MAINT / "compare.py"), str(MAINT / "before.json"), str(d / "a.json"),
                            str(d / "c.json")], capture_output=True)
        return p.returncode, json.loads((d / "c.json").read_text())

    def mutate(self, fn_filter, change):
        a = json.loads((MAINT / "before.json").read_text())
        f, fn = next((f, fn) for f, v in sorted(a["folders"].items()) for fn in sorted(v) if fn_filter(f, fn, v[fn]))
        change(a["folders"][f][fn])
        return a

    def test_identical_passes(self):
        rc, c = self.run_cmp(json.loads((MAINT / "before.json").read_text()))
        self.assertEqual((rc, c["verdict"], c["expected_changes"]), (0, "REGRESSION_PASS", []))

    def test_other_term_flip_fails(self):
        def ch(r):
            r["checks"]["schema"] = not r["checks"]["schema"]
        a = self.mutate(lambda f, fn, r: fn == "k_identity" and "checks" in r, ch)
        self.assertEqual(self.run_cmp(a)[0], 1)

    def test_k_placement_flip_fails(self):        # only manifest-driven identity_of may flip; K's default must not
        def ch(r):
            r["checks"]["placement"] = not r["checks"]["placement"]
        a = self.mutate(lambda f, fn, r: fn == "k_identity" and "checks" in r, ch)
        self.assertEqual(self.run_cmp(a)[0], 1)

    def test_k_default_false_to_true_fails(self):  # the default path (expected 0) must never start passing placement 1
        def ch(r):
            r["checks"]["placement"] = True
        a = self.mutate(lambda f, fn, r: fn == "k_identity" and r.get("checks", {}).get("placement") is False, ch)
        self.assertEqual(self.run_cmp(a)[0], 1)

    def test_placement_true_to_false_fails(self):
        def ch(r):
            r["checks"]["placement"] = False
        a = self.mutate(lambda f, fn, r: fn.startswith("identity_of[") and r.get("checks", {}).get("placement"), ch)
        self.assertEqual(self.run_cmp(a)[0], 1)

    def test_other_field_fails(self):            # the expected placement flip plus any other difference -> FAIL
        def ch(r):
            r["checks"]["placement"], r["caps_diff"] = True, {"x": [1, 2]}
        a = self.mutate(lambda f, fn, r: fn.startswith("identity_of[") and r.get("checks", {}).get("placement") is False, ch)
        self.assertEqual(self.run_cmp(a)[0], 1)

    def test_expected_flip_alone_passes(self):
        def ch(r):
            r["checks"]["placement"], r["ok"] = True, True
        a = self.mutate(lambda f, fn, r: fn.startswith("identity_of[") and r.get("checks", {}).get("placement") is False
                        and [c for c, v in r["checks"].items() if not v] == ["placement"], ch)
        rc, c = self.run_cmp(a)
        self.assertEqual((rc, len(c["expected_changes"])), (0, 1))

    def test_folder_set_fails(self):
        a = json.loads((MAINT / "before.json").read_text())
        a["folders"].pop(sorted(a["folders"])[0])
        self.assertEqual(self.run_cmp(a)[0], 1)


if __name__ == "__main__":
    unittest.main()
