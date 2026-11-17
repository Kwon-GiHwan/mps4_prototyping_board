"""Stage 6B-E2E-A rules (evidence/stage6b/stage6be2ea/contract.md) and a characterisation test of the shared
stage4k.identity placement term (A4: it is not changed; this pins its current behaviour). Expected values by hand."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage6be2ea as E  # noqa: E402


class TrackA(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(E.classify(False, {1}, True, None), "UNAFFECTED")
        self.assertEqual(E.classify(True, {0}, True, None), "UNAFFECTED")
        self.assertEqual(E.classify(True, set(), True, None), "UNAFFECTED")
        self.assertEqual(E.classify(True, {0}, False, None), "UNRESOLVED")
        self.assertEqual(E.classify(True, {0, 1}, True, None), "REMEASUREMENT_REQUIRED")
        self.assertEqual(E.classify(True, {1}, True, dict(remeasured=True)), "REJUDGE_REQUIRED")
        self.assertEqual(E.classify(True, {1}, True, dict(remeasured=True, rejudged=True)), "JUDGE_FALSE_REJECTION")

    def test_overall(self):
        self.assertEqual(E.overall(["UNAFFECTED", "JUDGE_FALSE_REJECTION"]), "NO_HISTORICAL_IMPACT")
        self.assertEqual(E.overall(["UNAFFECTED", "UNRESOLVED"]), "HISTORICAL_IMPACT_UNRESOLVED")
        self.assertEqual(E.overall(["UNRESOLVED", "REJUDGE_REQUIRED"]), "HISTORICAL_REJUDGE_REQUIRED")
        self.assertEqual(E.overall(["REJUDGE_REQUIRED", "REMEASUREMENT_REQUIRED"]), "HISTORICAL_REMEASUREMENT_REQUIRED")

    def test_experiment_of(self):
        self.assertEqual(E.experiment_of("evidence/stage6b/stage6be2d/raw_a/x/raw_runs.json"), "evidence/stage6b/stage6be2d/raw_a")
        self.assertEqual(E.experiment_of("evidence/stage6b/stage6be2d/raw/x/raw_runs.json"), "evidence/stage6b/stage6be2d/raw")
        self.assertEqual(E.experiment_of("evidence/stage6b/stage6be1r/raw/x.json"), "evidence/stage6b/stage6be1r")
        self.assertEqual(E.experiment_of("evidence/stage4aoe/raw_a1/x.json"), "evidence/stage4aoe")
        self.assertEqual(E.experiment_of("evidence/stage5/raw/x.json"), "evidence/stage5")
        self.assertEqual(E.experiment_of("evidence/stage4k_extra/raw/x.json"), "evidence/stage4k_extra")    # not stage4k

    def test_scan_missing_field(self):
        d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d, True)
        (d / "a").mkdir()
        (d / "a" / "raw_runs.json").write_text(json.dumps([{}, {"record": {"placement": 0}}, {"record": {}}]))
        orig = E.REPO
        try:
            E.REPO = d
            r = E.scan(d)
        finally:
            E.REPO = orig
        self.assertEqual((r[0]["has_field"], r[0]["placements"], r[0]["n"]), (False, [0], 2))

    def test_scan(self):
        rows = E.scan(E.REPO / "evidence" / "stage6b" / "stage6be2d" / "raw")
        w0p1 = [r for r in rows if "e2d_w0p1" in r["file"]]
        self.assertEqual((w0p1[0]["placements"], w0p1[0]["n"], w0p1[0]["has_field"]), ([1], 10, True))


class SharedIdentityCharacterisation(unittest.TestCase):
    """stage4k.identity keeps `placement == 0` (A4: unchanged); boot 442 (placement 1) fails only that term."""
    def test_boot442(self):
        import stage4k as K
        raw = E.REPO / "evidence/stage6b/stage6be2d/raw/evsweep_s6be2d_run_l500/conds"
        wl = E.REPO / "evidence/stage6b/stage6be2d/workloads"
        i1 = K.identity(raw / "e2d_w0p1" / "wfe", wl, "e2d_w0p1", str(wl / "caps_l500.json"))
        self.assertFalse(i1["checks"]["placement"])
        i0 = K.identity(raw / "e2d_w0p0" / "wfe", wl, "e2d_w0p0", str(wl / "caps_l500.json"))
        self.assertTrue(i0["checks"]["placement"])


class TrackB(unittest.TestCase):
    def test_c1(self):
        bw = {500: 6.5536, 1000: 3.2768}
        self.assertEqual(E.c1({500: 477824, 1000: 477824}, {500: 55467, 1000: 102616}, bw), "SUPPORTED")   # 8.61, 4.66
        self.assertEqual(E.c1({500: 300000, 1000: 300000}, {500: 55467, 1000: 102616}, bw), "CONTRADICTED")  # 5.41, 2.92
        self.assertEqual(E.c1({500: 477824, 1000: 300000}, {500: 55467, 1000: 102616}, bw), "UNRESOLVED")

    def test_c2(self):
        self.assertEqual(E.c2(706560, 353280, 79.3, 64), "SUPPORTED")
        self.assertEqual(E.c2(706560, 353280, 60, 64), "UNRESOLVED")
        self.assertEqual(E.c2(380000, 353280, 79.3, 64), "CONTRADICTED")    # 1.076
        self.assertEqual(E.c2(400000, 353280, 79.3, 64), "UNRESOLVED")      # 1.13
        self.assertEqual(E.c2(459264, 353280, 79.3, 64), "SUPPORTED")       # exactly 1.3

    def test_c3(self):
        self.assertEqual(E.c3(440000, 477824), "SUPPORTED")
        self.assertEqual(E.c3(353280, 477824), "CONTRADICTED")              # 1.353
        self.assertEqual(E.c3(400000, 320000), "SUPPORTED")                 # 0.8
        self.assertEqual(E.c3(400000, 319999), "CONTRADICTED")

    def test_cause(self):
        self.assertEqual(E.cause("SUPPORTED", "SUPPORTED"), "SUPPORTED")
        self.assertEqual(E.cause("SUPPORTED", "UNRESOLVED"), "UNRESOLVED")
        self.assertEqual(E.cause("CONTRADICTED", "SUPPORTED"), "CONTRADICTED")
        self.assertEqual(E.cause("UNRESOLVED", "CONTRADICTED"), "UNRESOLVED")

    def test_verdict(self):
        self.assertEqual(E.track_b_verdict(True, True, True, True), "READY_FOR_BOARD_REVIEW")
        self.assertEqual(E.track_b_verdict(True, True, False, True), "PARTIAL_IDENTIFIABILITY")
        self.assertEqual(E.track_b_verdict(True, True, True, False), "PARTIAL_IDENTIFIABILITY")
        self.assertEqual(E.track_b_verdict(True, False, True, True), "NOT_IDENTIFIABLE")
        self.assertEqual(E.track_b_verdict(False, True, True, True), "INVALID")

    def test_sram_arena(self):
        # boot 442: fast end 0x31060000, model 0x70000000, DDR arena 0x700165F0 -> SRAM arena 0x310765F0 (2 MiB fits)
        self.assertEqual(E.sram_arena(0x31060000, 0x70000000, 0x700165F0, 0x200000), 0x310765F0)
        self.assertEqual(E.sram_arena(0x31060001, 0x70000000, 0x700165F0, 0x200000), 0x310865F0)   # 64 KiB rounding
        self.assertEqual(E.sram_arena(0x31060000, 0x70000000, 0x70216000, 0x200000), 0)           # past the limit
        self.assertEqual(E.sram_arena(0x31060000, 0x70000100, 0x700165F0, 0x200000), 0)           # unaligned model
        self.assertEqual(E.sram_arena(0x31060000, 0x70000000, 0x6FFFFFFF, 0x10), 0)               # arena below model


if __name__ == "__main__":
    unittest.main()
