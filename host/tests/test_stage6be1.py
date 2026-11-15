"""stage6be1.py (evidence/stage6b/stage6be1/contract.md): eligibility, categories, the selection rule, the frozen
predictions and the H1-UC / DPU verdicts, on synthetic facts. Expected values typed here."""
import pathlib, sys, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6be1 as E


def facts(cin, h, w, cout, ublock="2x2x32", ifm_block="8x8x64", kernels=None, trav="DepthFirst", npu=("Conv2D", "Relu6"),
          cpu="0", n_ops=1, kernel="1x1"):
    rows = [dict(npu_op=npu[0], cpu=cpu, cms_offsets="100", traversal=trav, ofm_block="8x8x64", ifm_block=ifm_block,
                 ofm_ublock=ublock, kernel=kernel, ifm_memory="Dram", ofm_memory="Dram")]
    rows += [dict(npu_op=n, cpu="0", cms_offsets="", traversal="", ofm_block="xx", ifm_block="xx", ofm_ublock="xx", kernel="1x1",
                  ifm_memory="Dram", ofm_memory="Dram") for n in npu[1:]]
    ks = kernels or [[h, w, cout]]
    return dict(n_ethosu_ops=n_ops, rows=rows, kernels=[dict(ofm=k, ifm_depth=cin, offset=100, kind="CONV") for k in ks])


NAME = lambda cin, h, w, cout: f"e1_c{cin}_h{h}w{w}_o{cout}"


def case(cin, h, w, cout, **kw):
    return E.case_of(NAME(cin, h, w, cout), facts(cin, h, w, cout, **kw))


class Eligibility(unittest.TestCase):
    def test_good(self):
        ok, why = E.eligible(NAME(72, 8, 8, 96), facts(72, 8, 8, 96), set())
        self.assertTrue(ok, why)

    def test_rejections(self):
        cases = dict(partkernel=dict(trav="PartKernel"), two_ops=dict(n_ops=2), cpu=dict(cpu="1"),
                     extra_row=dict(npu=("Conv2D", "Relu6", "Add")), kernel=dict(kernel="3x3"))
        for k, kw in cases.items():
            with self.subTest(k):
                self.assertFalse(E.eligible(NAME(72, 8, 8, 96), facts(72, 8, 8, 96, **kw), set())[0])
        self.assertFalse(E.eligible(NAME(72, 8, 8, 96), facts(72, 8, 8, 96), {(8, 8, 72, 96)})[0])

    def test_extra_cpu_row(self):
        f = facts(72, 8, 8, 96)
        f["rows"].append(dict(npu_op="", cpu="1", cms_offsets="", traversal="", ofm_block="", ifm_block="", ofm_ublock="",
                              kernel="", ifm_memory="", ofm_memory=""))
        self.assertFalse(E.eligible(NAME(72, 8, 8, 96), f, set())[0])

    def test_stage6bb_shapes_are_covered(self):
        import json
        ex = E.existing_shapes()
        man = json.loads((REPO / "evidence/stage6b/stage6bb/workloads/stage6bb_manifest.json").read_text())
        for m in man.values():
            oh, ow, _ = E.R.hwc(m["ofm_hwc"])
            self.assertIn((oh, ow, m["cin"], m["cout"]), ex)
        for c in (16, 32, 64, 128):
            self.assertIn((24, 24, c, 96), ex)

    def test_no_split_is_ineligible(self):
        # Cin 64, 8x8, Cout 96 one kernel 2x2x32: every hypothesis gives 16*3*8 = 384
        c = case(64, 8, 8, 96)
        self.assertEqual(E.n_split(c), 0)
        self.assertFalse(E.eligible(NAME(64, 8, 8, 96), facts(64, 8, 8, 96), set())[0])

    def test_existing_shapes_include_the_measured_ones(self):
        ex = E.existing_shapes()
        self.assertIn((24, 24, 48, 96), ex)
        self.assertIn((16, 16, 276, 276), ex)                 # G12
        self.assertIn((14, 14, 64, 384), ex)                  # G09


class Categories(unittest.TestCase):
    def test_a_b_c_d(self):
        self.assertIn("E1-A", E.categories(case(72, 8, 8, 96)))            # 64 + 8: min 32 binds
        self.assertNotIn("E1-A", E.categories(case(100, 8, 8, 96)))        # 64 + 36
        self.assertNotIn("E1-A", E.categories(case(88, 8, 8, 96)))         # 64 + 24: 24 -> 32 with or without the minimum
        for cin in (66, 72, 80, 88, 100, 120, 136):                         # implication: difference -> 0 < r <= 16
            c = case(cin, 8, 8, 96)
            self.assertEqual("E1-A" in E.categories(c), 0 < cin % 64 <= 16, cin)
        for h in (7, 8, 13, 14):                                             # implication: difference <-> edge off the ublock
            self.assertEqual("E1-B" in E.categories(case(72, h, h, 96)), h % 2 == 1, h)
        self.assertNotIn("E1-C", E.categories(case(72, 8, 8, 96, ublock="2x2x8")))
        self.assertIn("E1-B", E.categories(case(72, 7, 7, 96)))            # 7 not a multiple of 2
        self.assertNotIn("E1-B", E.categories(case(72, 8, 8, 96)))
        self.assertIn("E1-C", E.categories(case(72, 8, 8, 96, ublock="2x4x16")))
        self.assertIn("E1-D", E.categories(case(72, 8, 8, 96, kernels=[[8, 8, 16], [8, 8, 80]])))
        self.assertNotIn("E1-D", E.categories(case(72, 8, 8, 96, kernels=[[8, 8, 64], [8, 8, 32]])))  # same padding both ways


class Selection(unittest.TestCase):
    def test_one_per_category_then_extras(self):
        pool = [case(72, 8, 8, 96), case(80, 7, 7, 80), case(88, 8, 8, 112, ublock="2x4x16"),
                case(40, 8, 8, 96, kernels=[[8, 8, 16], [8, 8, 80]]), case(100, 9, 9, 48), case(136, 13, 13, 176),
                case(72, 14, 14, 96)]
        s = E.select(pool)
        self.assertEqual(s["status"], "OK")
        self.assertEqual(len(s["selected"]), 6)
        self.assertEqual(sorted(v for v in s["role"].values() if v != "extra"), ["E1-A", "E1-B", "E1-C", "E1-D"])
        same = [(c["cin"], c["cout"]) for c in pool if c["case"] in s["selected"]]
        self.assertEqual(len(same), len(set(same)))           # no repeated (Cin, Cout)

    def test_missing_category_needs_revision(self):
        pool = [case(72, 8, 8, 96), case(80, 7, 7, 80), case(100, 9, 9, 48), case(136, 13, 13, 176),
                case(88, 14, 14, 112), case(200, 9, 9, 80), case(40, 7, 7, 48)]
        s = E.select(pool)
        self.assertEqual(s["status"], "NEEDS_REVISION")
        self.assertIn("E1-C", s["missing_categories"])

    def test_unpackable_skipped(self):
        pool = [case(72, 8, 8, 96), case(72, 9, 9, 96)]
        first = E.select(pool)["role"]
        a = next(n for n, r in first.items() if r == "E1-A")
        again = E.select(pool, packs=lambda n: n != a)["role"]
        self.assertNotIn(a, again)

    def test_rank_key(self):
        hi, lo = case(72, 7, 7, 96), case(64, 7, 7, 96)
        self.assertGreater(E.n_split(hi), E.n_split(lo))
        self.assertLess(E.rank_key(hi), E.rank_key(lo))


class Predictions(unittest.TestCase):
    def test_values(self):
        p = E.predictions(case(72, 7, 7, 96))
        self.assertEqual(p["ublocks"], 4 * 4 * 3)
        self.assertEqual(p["mac"]["H1-UC"], 48 * (8 + 4))
        self.assertEqual(p["mac"][E.NO_MIN32], 48 * (8 + 2))      # chunk 8 -> 16 without the minimum
        self.assertEqual(p["dpu"]["D-PW"], 48 * (8 + 1))
        self.assertEqual(p["dpu"]["D-U16"], 48 * (8 + 2))
        self.assertTrue(p["dpu_pw_vs_u16_split"])
        self.assertIn(E.NO_SPATIAL, p["differs_from_h1_uc"])


class Frozen(unittest.TestCase):
    """The committed predictions recomputed by hand from the committed compile facts, and the 6B-R regression set."""
    def test_hand_computed_h1_uc(self):
        import json
        p = json.loads((REPO / "evidence/stage6b/stage6be1/workloads/predictions.json").read_text())
        # 13x13, Cout 96 split 16 + 80, ublock 2x2x32: 7*7*1 + 7*7*3 = 196 ublocks; Cin 72 = 64 + 8 -> 8 + max(32,16)/8 = 12
        self.assertEqual(p["e1_c72_h13w13_o96"]["mac"]["H1-UC"], 196 * 12)
        self.assertEqual(p["e1_c136_h13w13_o96"]["mac"]["H1-UC"], 196 * (8 + 8 + 4))
        self.assertEqual(p["e1_c200_h13w13_o96"]["mac"]["H1-UC"], 196 * (8 * 3 + 4))
        self.assertEqual(p["e1_c80_h13w13_o96"]["mac"]["H1-UC"], 196 * (8 + 4))
        # 7x7x48, ublock 2x4x16: 4*2*3 = 24 ublocks; Cin 72 -> 12
        self.assertEqual(p["e1_c72_h7w7_o48"]["mac"]["H1-UC"], 24 * 12)
        # 7x7x112, ublock 1x4x32: 7*2*4 = 56 ublocks; Cin 72 -> 12
        self.assertEqual(p["e1_c72_h7w7_o112"]["mac"]["H1-UC"], 56 * 12)

    def test_regression_14_of_14(self):
        cases = [c for c in E.R.stage4_cases() + E.R.stage6bb_cases() if c["status"] == "VALID"]
        self.assertEqual(len(cases), 14)
        self.assertTrue(all(E.R.h1_uc(c) == c["mac"] for c in cases))


PRED = E.predictions(case(72, 7, 7, 96))


def run(status="VALID", mac=576, dpu=432, runs=4):
    return dict(config="x", status=status, reasons=[], mac_active_runs=[mac] * runs, mac_dpu_active_runs=[dpu] * runs)


class Verdict(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(E.classify(run()), "PRIMARY_VALID")
        self.assertEqual(E.classify(run(status="UNSTABLE")), "MAC_ONLY_DIAGNOSTIC")
        self.assertEqual(E.classify(dict(run(status="UNSTABLE"), mac_active_runs=[576, 576, 577, 576])), "INVALID_OR_UNRESOLVED")
        self.assertEqual(E.classify(dict(run(status="UNSTABLE"), mac_dpu_active_runs=[1, 2, 1, 1])), "INVALID_OR_UNRESOLVED")
        self.assertEqual(E.classify(run(status="INVALID_OUTPUT")), "INVALID_OR_UNRESOLVED")

    def test_shape_result(self):
        s = E.shape_result(run(), PRED)
        self.assertTrue(s["h1_uc_match"])
        self.assertEqual(s["residual"], 0)
        self.assertFalse(s["competitors"][E.NO_MIN32]["match"])
        self.assertTrue(s["competitors"][E.NO_MIN32]["distinguishing"])
        self.assertTrue(s["dpu"]["D-PW"]["match"])
        self.assertFalse(E.shape_result(run(mac=577), PRED)["h1_uc_match"])

    def test_verdicts(self):
        ok = dict(verdict="PASS")
        good = [E.shape_result(run(), PRED) for _ in range(6)]
        self.assertEqual(E.verdict(ok, good), "PROSPECTIVE_SUPPORT")
        bad = good[:5] + [E.shape_result(run(mac=600), PRED)]
        self.assertEqual(E.verdict(ok, bad), "H1_UC_CONTRADICTED")
        fewer = good[:5] + [E.shape_result(run(status="UNSTABLE"), PRED)]
        self.assertEqual(E.verdict(ok, fewer), "INSUFFICIENT_EVIDENCE")
        diag_miss = good[:5] + [E.shape_result(run(status="UNSTABLE", mac=600), PRED)]
        self.assertEqual(E.verdict(ok, diag_miss), "INSUFFICIENT_EVIDENCE")       # diagnostic never contradicts
        self.assertEqual(E.verdict(dict(verdict="FAIL"), good), "INSUFFICIENT_EVIDENCE")

    def test_dpu_verdict(self):
        self.assertEqual(E.dpu_verdict([E.shape_result(run(), PRED)]), "D-PW_CONSISTENT")
        self.assertEqual(E.dpu_verdict([E.shape_result(run(dpu=480), PRED)]), "D-PW_CONTRADICTED")
        no_split = E.predictions(case(100, 8, 8, 96))
        self.assertEqual(E.dpu_verdict([E.shape_result(run(mac=no_split["mac"]["H1-UC"]), no_split)]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.dpu_verdict([E.shape_result(run(status="UNSTABLE"), PRED)]), "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
