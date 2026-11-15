"""stage6br.py (results/fi101_stage6b/stage6br/analysis_contract.md): the counting formulas, the hypothesis verdict rule and
the rank correlation. Expected values are typed here from hand arithmetic, not read back from the module."""
import pathlib, sys, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6br as R

STAGE4_CIN48 = dict(case="a", status="VALID", cin=48, cout=96, ofm=[24, 24, 96], ublock=[2, 2, 32], ifm_block_depth=64,
                    kernels=[[24, 24, 16], [24, 24, 80]], mac=3456.0, dpu=3456.0)
G25 = dict(case="g25", status="VALID", cin=140, cout=140, ofm=[25, 5, 140], ublock=[2, 2, 32], ifm_block_depth=64,
           kernels=[[25, 5, 140]], mac=3900.0, dpu=3510.0)
G57 = dict(case="g57", status="VALID", cin=68, cout=288, ofm=[8, 8, 288], ublock=[2, 2, 32], ifm_block_depth=64,
           kernels=[[8, 8, 288]], mac=1728.0, dpu=1296.0)
G40 = dict(case="g40", status="VALID", cin=160, cout=960, ofm=[7, 7, 960], ublock=[1, 4, 32], ifm_block_depth=64,
           kernels=[[7, 7, 960]], mac=8400.0, dpu=8400.0)
PK16 = dict(case="pk", status="VALID", cin=16, cout=96, ofm=[24, 24, 96], ublock=[2, 2, 32], ifm_block_depth=16,
            kernels=[[24, 24, 16], [24, 24, 80]], mac=2304.0, dpu=1152.0)


class Counting(unittest.TestCase):
    def test_ublocks(self):
        self.assertEqual(R.ublocks(STAGE4_CIN48["kernels"], [2, 2, 32]), 144 * 1 + 144 * 3)      # 16 -> 1, 80 -> 3 deep
        self.assertEqual(R.ublocks(G25["kernels"], [2, 2, 32]), 13 * 3 * 5)                      # 25 -> 13, 5 -> 3
        self.assertEqual(R.ublocks(G40["kernels"], [1, 4, 32]), 7 * 2 * 30)
        self.assertEqual(R.ublocks(G25["kernels"], [2, 2, 32], pad_spatial=False), 12.5 * 2.5 * 5)

    def test_chunks(self):
        self.assertEqual(R.chunks(276, 64), [64, 64, 64, 64, 20])
        self.assertEqual(R.chunks(68, 64), [64, 4])
        self.assertEqual(R.chunks(48, 64), [48])
        self.assertEqual(R.chunks(32, 16), [16, 16])

    def test_chunk_costs(self):
        self.assertEqual([R.mac_chunk(x) for x in (4, 12, 20, 32, 40, 44, 48, 64)], [4, 4, 4, 4, 6, 6, 6, 8])
        self.assertEqual([R.mac_chunk(x, min32=False) for x in (4, 20, 40)], [2, 4, 6])
        self.assertEqual([R.dpu_chunk_pw(x) for x in (4, 12, 20, 40, 64)], [1, 2, 4, 6, 8])

    def test_h1_uc_values(self):
        self.assertEqual(R.h1_uc(STAGE4_CIN48), 576 * 6)
        self.assertEqual(R.h1_uc(G25), 195 * (8 + 8 + 4))
        self.assertEqual(R.h1_uc(G57), 144 * (8 + 4))
        self.assertEqual(R.h1_uc(G40), 420 * 20)
        self.assertEqual(R.h1_uc(PK16), 576 * 4)

    def test_other_hypotheses(self):
        self.assertEqual(R.MAC_HYP["H1-G"](G25), 26 * 6 * 160 * 144 / 1024)
        self.assertEqual(R.MAC_HYP["H1-U8"](G57), 144 * 9)
        self.assertEqual(R.DPU_HYP["D-PW"](G57), 144 * (8 + 1))
        self.assertEqual(R.DPU_HYP["D-U16"](G57), 144 * (8 + 2))
        self.assertAlmostEqual(R.ratio_dr(G25), 144 / 160)
        self.assertAlmostEqual(R.ratio_dr(G57), 72 / 96)

    def test_ablation_whole_cout(self):
        self.assertEqual(R.h1_uc(STAGE4_CIN48, per_kernel=False), 144 * 3 * 6)


class Verdict(unittest.TestCase):
    def test_rules(self):
        cases = [dict(c) for c in (STAGE4_CIN48, G25, G57, G40)]
        self.assertEqual(R.verdict(cases, R.h1_uc, "mac")["verdict"], "CONSISTENT_WITH_OBSERVATIONS")
        bad = cases + [dict(G57, case="x", mac=1729.0)]
        v = R.verdict(bad, R.h1_uc, "mac")
        self.assertEqual((v["verdict"], v["not_exact"]), ("CONTRADICTED", ["x"]))

    def test_unstable_is_not_official(self):
        cases = [dict(STAGE4_CIN48), dict(G57, status="UNSTABLE", mac=1.0)]
        v = R.verdict(cases, R.h1_uc, "mac")
        self.assertEqual((v["verdict"], v["n_official"], v["exploratory_exact"]), ("CONSISTENT_WITH_OBSERVATIONS", 1, 0))

    def test_insufficient_when_closest_competitor_splits_once(self):
        cases = [dict(STAGE4_CIN48), dict(G57)]
        same_but_one = lambda c: R.h1_uc(c) + (1 if c["case"] == "g57" else 0)
        self.assertEqual(R.verdict(cases, R.h1_uc, "mac", [same_but_one])["verdict"], "INSUFFICIENT_EVIDENCE")
        two_apart = lambda c: R.h1_uc(c) + 1
        self.assertEqual(R.verdict(cases, R.h1_uc, "mac", [two_apart])["verdict"], "CONSISTENT_WITH_OBSERVATIONS")


class Rank(unittest.TestCase):
    def test_spearman(self):
        self.assertAlmostEqual(R.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(R.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertEqual(R.ranks([5, 1, 5, 2]), [3.5, 1.0, 3.5, 2.0])
        self.assertIsNone(R.spearman([1, 2, 3], [7, 7, 7]))
        r = R.spearman([1, 2, 3, 4], [1, 1, 2, 2])
        self.assertTrue(-1 <= r <= 1)
        self.assertAlmostEqual(r, 0.894427191, places=6)


if __name__ == "__main__":
    unittest.main()
