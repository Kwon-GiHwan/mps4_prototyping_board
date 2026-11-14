"""stage4wd.py: weight facts from the compiled streams, the archived-RUN inventory (SRAM re-read rule), the MLEK WD
table, and the Experiment A / B / SRAM verdicts (closed sets) on synthetic values. Expected numbers are typed here."""
import copy, json, pathlib, shutil, sys, tempfile, unittest
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "lib"))
import stage4wd as W

WL = REPO / "evidence/stage4wd/workloads"
AO_WL = REPO / "evidence/stage4ao/workloads"


def st_of():
    s = {c: W.static_of(WL if (WL / f"{c}.compile.json").exists() else AO_WL, c) for c in set(W.EXP_A + W.EXP_B)}
    return s


class Static(unittest.TestCase):
    def test_base(self):
        s = W.static_of(AO_WL, "s4ao_conv1x1_h24")
        self.assertEqual((s["encoded_bytes"], s["staged_bytes"], s["spatial_blocks"], s["blocks"]), (2752, 4032, 8, 16))
        self.assertEqual(s["encoded_per_kernel"], [704, 2048]); self.assertEqual(s["weight_format"], [0])
        self.assertEqual(s["raw_weight_bytes"], 96 * 16)

    def test_depth_slices(self):
        s = W.static_of(REPO / "evidence/stage4k/workloads", "s4k_conv3x3_cin16")      # block 24x10x32, slices > 32
        self.assertEqual((s["spatial_blocks"], s["blocks"]), (3, 12))

    def test_checks(self):
        res = {c: dict(W.static_of(WL if (WL / f"{c}.compile.json").exists() else AO_WL, c), reference=None)
               for c in set(W.EXP_A + W.EXP_B)}
        self.assertTrue(W.checks(res)["a_same_schedule"])
        bad = copy.deepcopy(res); bad["s4wd_w_small"]["blocks"] = 99
        self.assertFalse(W.checks(bad)["a_same_schedule"])
        bad = copy.deepcopy(res); bad["s4wd_h32"]["encoded_bytes"] = 1
        self.assertFalse(W.checks(bad)["b_same_block"])
        bad = copy.deepcopy(res); bad["s4wd_h32"]["reference"] = dict(opt_vs_ref=3)
        self.assertFalse(W.checks(bad)["golden_unambiguous"])

    def test_candidates(self):
        s = st_of()
        self.assertEqual([s[c]["encoded_bytes"] for c in W.EXP_A], [2752, 1536, 1168, 640])
        self.assertEqual([s[c]["staged_bytes"] for c in W.EXP_A], [4032, 2816, 2448, 1920])
        self.assertEqual([s[c]["spatial_blocks"] for c in W.EXP_B], [8, 8, 12, 12, 12])
        self.assertEqual([s[c]["n_ofm"] for c in W.EXP_B], [52992, 55296, 73728, 78336, 82944])
        d = tempfile.mkdtemp()
        try:
            r = W.static(str(WL), d)["_checks"]
            self.assertTrue(r["a_same_schedule"] and r["a_encoded_distinct"] and r["b_same_block"] and r["golden_unambiguous"])
            self.assertEqual(r["b_block_groups"], [16, 24])
        finally:
            shutil.rmtree(d)


class Inventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.rows = W.inventory(cls.d)
        cls.mlek = W.mlek_wd(cls.d)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_rule(self):
        staged = [r for r in self.rows if r["placement"] == "ddr" and r["staged_bytes"] > 0]
        self.assertEqual(len(staged), 35)
        self.assertTrue(all(r["sram_rd_is_spatial_x_staged"] for r in staged))
        h72 = next(r for r in self.rows if r["config"] == "s4ao_conv1x1_h72")
        self.assertEqual((h72["wd_active"], h72["sram_rd"], h72["spatial_blocks"]), (2993.5, 6048, 24))
        sram = next(r for r in self.rows if r["config"] == "s4p_conv_base_sram")
        self.assertEqual((sram["wd_active"], sram["wd_stalled"]), (1048, 2414))
        self.assertFalse(any(r["config"] == "s4ao_act_none" for r in self.rows))   # refused boot: no metrics
        self.assertEqual(len(self.rows), 39)
        r = dict(placement="ddr", staged_bytes=4032, spatial_blocks=8, sram_rd=2016, sram_wr=252)
        self.assertTrue(W.sram_rule(r))
        self.assertFalse(W.sram_rule(dict(r, sram_rd=2017)))
        self.assertFalse(W.sram_rule(dict(r, sram_wr=253)))
        self.assertFalse(W.sram_rule(dict(r, placement="sram")))
        self.assertFalse(W.sram_rule(dict(r, staged_bytes=0, sram_rd=0, sram_wr=0)))

    def test_mlek(self):
        m = {r["model"]: r for r in self.mlek}
        self.assertEqual(len(m), 7)
        self.assertEqual(m["wav2letter_pruned_int8"]["wd_active"], 1133549)
        self.assertEqual(m["rnnoise_INT8"]["mac_active"], 548)

    def test_predict(self):
        shutil.copy(REPO / "results/fi101_stage4wd/static.json", pathlib.Path(self.d) / "static.json")
        p = W.predict(self.d)
        self.assertAlmostEqual(p["fit_blocks"]["slope"], (2993.5 - 1052) / 32, delta=3)
        self.assertGreater(p["exp_b"]["s4wd_h32"]["by_blocks"] - p["exp_b"]["s4wd_h32"]["by_n"], 100)


class Helpers(unittest.TestCase):
    def tearDown(self):
        W.RNG.clear()

    def test_linfit(self):
        f = W.linfit([1, 2, 3], [5, 7, 9])
        self.assertAlmostEqual(f["slope"], 2); self.assertAlmostEqual(f["intercept"], 3); self.assertAlmostEqual(f["r2"], 1)

    def test_same(self):
        self.assertTrue(W.same(1000, 1020)); self.assertFalse(W.same(1000, 1030))
        self.assertTrue(W.same(3000, 3055)); self.assertFalse(W.same(3000, 3070))       # 2 % of the mean
        self.assertTrue(W.same(1000, 1080, 40, 40)); self.assertFalse(W.same(1000, 1081, 40, 40))
        self.assertTrue(W.same(100, 125)); self.assertFalse(W.same(100, 126))            # the 25-cycle floor


B_BLOCKS = {"s4wd_h23": 1050, "s4ao_conv1x1_h24": 1052, "s4wd_h32": 1555, "s4wd_h34": 1550, "s4ao_conv1x1_h36": 1560}
B_N = {"s4wd_h23": 1010, "s4ao_conv1x1_h24": 1060, "s4wd_h32": 1390, "s4wd_h34": 1470, "s4ao_conv1x1_h36": 1555}


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.st = st_of()

    def tearDown(self):
        W.RNG.clear()

    def test_b(self):
        self.assertEqual(W.verdict_b(B_BLOCKS, self.st)["verdict"], "BLOCK_LIKE")
        self.assertEqual(W.verdict_b(B_N, self.st)["verdict"], "N_LIKE")
        flat = {c: 1200 for c in W.EXP_B}
        self.assertEqual(W.verdict_b(flat, self.st)["verdict"], "NEITHER")             # no step between groups
        self.assertEqual(W.verdict_b(dict(B_BLOCKS, s4wd_h32=None), self.st)["verdict"], "INCOMPLETE")
        W.RNG.update({c: 60 for c in W.EXP_B})                                         # wide ranges absorb N's steps
        self.assertNotEqual(W.verdict_b(B_N, self.st)["verdict"], "N_LIKE")

    def test_a(self):
        enc = {c: 1052 * self.st[c]["encoded_bytes"] / 2752 for c in W.EXP_A}
        stg = {c: 1052 * self.st[c]["staged_bytes"] / 4032 for c in W.EXP_A}
        self.assertEqual(W.verdict_a(enc, self.st)["verdict"], "ENCODED_PROPORTIONAL")
        self.assertEqual(W.verdict_a(stg, self.st)["verdict"], "STAGED_PROPORTIONAL")
        self.assertEqual(W.verdict_a({c: 1052 for c in W.EXP_A}, self.st)["verdict"], "CONSTANT")
        mono = {"s4ao_conv1x1_h24": 1052, "s4wd_w_small": 950, "s4wd_w_sparse75": 900, "s4wd_w_sparse90": 850}
        self.assertEqual(W.verdict_a(mono, self.st)["verdict"], "MONOTONE")
        other = dict(mono, s4wd_w_sparse90=990)
        self.assertEqual(W.verdict_a(other, self.st)["verdict"], "OTHER")
        self.assertEqual(W.verdict_a(dict(enc, s4wd_w_small=None), self.st)["verdict"], "INCOMPLETE")

    def test_sram(self):
        good = {c: self.st[c]["spatial_blocks"] * self.st[c]["staged_bytes"] / 16 for c in set(W.EXP_A + W.EXP_B)}
        self.assertEqual(W.verdict_sram(good, self.st)["verdict"], "HOLDS")
        self.assertEqual(good["s4wd_w_sparse90"], 960)
        self.assertEqual(W.verdict_sram(dict(good, s4wd_h32=good["s4wd_h32"] + 1), self.st)["verdict"], "FAILS")
        self.assertEqual(W.verdict_sram(dict(good, s4wd_h32=None), self.st)["verdict"], "INCOMPLETE")

    def test_judge(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copy(REPO / "results/fi101_stage4wd/static.json", pathlib.Path(d) / "static.json")
            vals = dict(B_BLOCKS, **{c: 1052 * self.st[c]["encoded_bytes"] / 2752 for c in W.EXP_A if c != "s4ao_conv1x1_h24"})
            def fake(root, wl, c, *x):
                return dict(verdict="VALID", stable=True, metrics={"A_80": vals[c], "A_80_range": 0,
                            "B_130": self.st[c]["spatial_blocks"] * self.st[c]["staged_bytes"] / 16})
            with mock.patch.object(W.AOE, "config_result", side_effect=fake):
                s = W.judge("x", str(WL), "unused", d)
            self.assertEqual((s["exp_b"]["verdict"], s["exp_a"]["verdict"], s["sram_rule"]["verdict"]),
                             ("BLOCK_LIKE", "ENCODED_PROPORTIONAL", "HOLDS"))
            bad = lambda r, w, c, *x: dict(fake(r, w, c), verdict="INVALID")
            with mock.patch.object(W.AOE, "config_result", side_effect=bad):
                s = W.judge("x", str(WL), "unused", d)
            self.assertEqual(s["exp_b"]["verdict"], "INCOMPLETE")
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
