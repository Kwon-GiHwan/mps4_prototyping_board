import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s0_3_ta as T


def run(npu=1000, cpu=1200, active=990, valid=True):
    return dict(ev={35: active}, ovf=set(), valid=valid, window=5000, infer=npu, infer_cpu=cpu, sys=None, host_s=None)


def runs(*rs):
    return {(1, i + 3): r for i, r in enumerate(rs)}


P1 = runs(run(), run(cpu=1210))                      # frac 0.20 / 0.21 -> median 0.205


class ModelVerdict(unittest.TestCase):
    def test_removes(self):
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1005), run(cpu=1010))), "TA_REMOVES_GAP")

    def test_one_run_out_of_band_is_not_removed(self):
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1005), run(cpu=1011))), "TA_REDUCES_GAP")

    def test_reduces_boundary(self):
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1102), run(cpu=1103))), "TA_REDUCES_GAP")  # 0.1025
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1104), run(cpu=1104))), "TA_NO_EFFECT")    # 0.104 > 0.1025

    def test_no_effect(self):
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1200), run(cpu=1200))), "TA_NO_EFFECT")

    def test_small_gap_model_is_descriptive(self):
        self.assertIsNone(T.model_verdict(runs(run(cpu=1049), run(cpu=1049)), runs(run(cpu=1300))))
        self.assertEqual(T.model_verdict(runs(run(cpu=1050), run(cpu=1050)), runs(run(cpu=1300))), "TA_NO_EFFECT")

    def test_unproven(self):
        ok = runs(run(cpu=1005))
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=1005, valid=False))), "UNPROVEN")
        self.assertEqual(T.model_verdict(runs(run(valid=False)), ok), "UNPROVEN")
        self.assertEqual(T.model_verdict(P1, {}), "UNPROVEN")
        self.assertEqual(T.model_verdict(P1, runs(run(cpu=None))), "UNPROVEN")


class Drift(unittest.TestCase):
    REF = runs(run(active=990), run(active=1000))

    def test_ok_and_each_failure(self):
        self.assertEqual(T.drift(runs(run(cpu=1215, active=995)), self.REF), "DRIFT_OK")       # frac 0.215 vs 0.20
        self.assertEqual(T.drift(runs(run(cpu=1225, active=995)), self.REF), "DRIFT")          # 0.225: > 10 %
        self.assertEqual(T.drift(runs(run(cpu=1175, active=995)), self.REF), "DRIFT")          # 0.175: > 10 % below
        self.assertEqual(T.drift(runs(run(active=1010)), self.REF), "DRIFT")                   # active > 1005
        self.assertEqual(T.drift(runs(run(active=980)), self.REF), "DRIFT")                    # active < 985.05
        self.assertEqual(T.drift({}, self.REF), "UNPROVEN")
        self.assertEqual(T.drift(runs(run(valid=False)), self.REF), "UNPROVEN")


class Overall(unittest.TestCase):
    def test_cases(self):
        R, D, N = "TA_REMOVES_GAP", "TA_REDUCES_GAP", "TA_NO_EFFECT"
        self.assertEqual(T.overall([R, R, None, R], "DRIFT_OK"), "TA_EXPLAINS")
        self.assertEqual(T.overall([N, N, None], "DRIFT_OK"), "TA_NOT_EXPLAINS")
        self.assertEqual(T.overall([R, D], "DRIFT_OK"), "MIXED")
        self.assertEqual(T.overall([R, N], "DRIFT_OK"), "MIXED")
        self.assertEqual(T.overall([D, D], "DRIFT_OK"), "MIXED")
        self.assertEqual(T.overall([D, N], "DRIFT_OK"), "MIXED")
        self.assertEqual(T.overall([R, R], "DRIFT"), "UNPROVEN")
        self.assertEqual(T.overall([R, "UNPROVEN"], "DRIFT_OK"), "UNPROVEN")
        self.assertEqual(T.overall([None], "DRIFT_OK"), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
