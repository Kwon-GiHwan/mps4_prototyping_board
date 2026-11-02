import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s0_3_clk as K

C1, C2, D = 0x1313, 0x1201, 0x1313


def run(npu=1000, cpu=1200, active=990, sram=0, ext=0, sel=C1, valid=True):
    return dict(ev={35: active}, ovf=set(), valid=valid, window=5000, infer=npu, infer_cpu=cpu, sys=None, host_s=None,
                ta_sel=sel, ta_sram=sram, ta_ext=ext)


def runs(*rs):
    return {(1, i + 3): r for i, r in enumerate(rs)}


REF = runs(run(active=990), run(active=1000))           # s013 profile 1: frac 0.20, active 990..1000
CAL = runs(run(sram=1200, sel=C2), run(sram=1200, sel=C2))   # root clock = CPU clock (k = 1)


class Usable(unittest.TestCase):
    def test_select_must_match_the_arm(self):
        self.assertTrue(K.usable(runs(run()), "c1"))
        self.assertFalse(K.usable(runs(run(sel=C2)), "c1"))
        self.assertTrue(K.usable(runs(run(sel=C2)), "c2"))
        self.assertFalse(K.usable(runs(run(sram=None)), "c1"))
        self.assertFalse(K.usable(runs(run(ext=None)), "c1"))
        self.assertFalse(K.usable(runs(run(valid=False)), "c1"))
        self.assertFalse(K.usable({}, "c1"))


class Drift(unittest.TestCase):
    def test_gap_model_relative_and_active_band(self):
        self.assertEqual(K.drift(runs(run(cpu=1215, active=995)), REF, "c1"), "DRIFT_OK")   # frac 0.215
        self.assertEqual(K.drift(runs(run(cpu=1225, active=995)), REF, "c1"), "DRIFT")      # 0.225 > +10 %
        self.assertEqual(K.drift(runs(run(active=1006)), REF, "c1"), "DRIFT")               # > 1005
        self.assertEqual(K.drift(runs(run(active=985)), REF, "c1"), "DRIFT")                # < 985.05
        self.assertEqual(K.drift(runs(run(sel=C2)), REF, "c1"), "UNPROVEN")

    def test_small_gap_model_absolute(self):
        ref = runs(run(cpu=1000), run(cpu=1000))                                            # frac 0
        self.assertEqual(K.drift(runs(run(cpu=1005)), ref, "c1"), "DRIFT_OK")               # 0.005
        self.assertEqual(K.drift(runs(run(cpu=1006)), ref, "c1"), "DRIFT")


class ClockScale(unittest.TestCase):
    def test_root_cycles_per_cpu_cycle(self):
        self.assertEqual(K.clock_scale(CAL), 1.0)
        self.assertEqual(K.clock_scale(runs(run(cpu=1000, sram=2000, sel=C2))), 2.0)
        self.assertIsNone(K.clock_scale(runs(run(sel=C1))))


class Counted(unittest.TestCase):
    def test_bands(self):
        c1 = lambda off: runs(run(sram=off, ext=0), run(sram=off, ext=0))                   # gap 200 CPU cycles
        self.assertEqual(K.counted(c1(200), CAL), "CLOCK_STOP_MATCHES")
        self.assertEqual(K.counted(c1(180), CAL), "CLOCK_STOP_MATCHES")                     # 0.90
        self.assertEqual(K.counted(c1(220), CAL), "CLOCK_STOP_MATCHES")                     # 1.10
        self.assertEqual(K.counted(c1(221), CAL), "CLOCK_STOP_EXCEEDS")
        self.assertEqual(K.counted(c1(179), CAL), "CLOCK_STOP_PARTIAL")
        self.assertEqual(K.counted(c1(20), CAL), "CLOCK_STOP_PARTIAL")                      # 0.10
        self.assertEqual(K.counted(c1(19), CAL), "CLOCK_STOP_ABSENT")

    def test_larger_adapter_and_scale(self):
        self.assertEqual(K.counted(runs(run(sram=0, ext=200)), CAL), "CLOCK_STOP_MATCHES")
        cal2 = runs(run(sram=2400, sel=C2))                                                  # k = 2
        self.assertEqual(K.counted(runs(run(sram=400)), cal2), "CLOCK_STOP_MATCHES")
        self.assertEqual(K.counted(runs(run(sram=200)), cal2), "CLOCK_STOP_PARTIAL")

    def test_unproven(self):
        self.assertEqual(K.counted(runs(run(sram=200)), {}), "UNPROVEN")
        self.assertEqual(K.counted(runs(run(sram=200, valid=False)), CAL), "UNPROVEN")


class Mode0(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(K.mode0(REF, runs(run(cpu=1010, sel=D), run(cpu=1005, sel=D))), "MODE0_REMOVES_GAP")
        self.assertEqual(K.mode0(REF, runs(run(cpu=1011, sel=D), run(cpu=1005, sel=D))), "MODE0_REDUCES_GAP")
        self.assertEqual(K.mode0(REF, runs(run(cpu=1100, sel=D))), "MODE0_REDUCES_GAP")    # 0.10 = 0.5 x 0.20
        self.assertEqual(K.mode0(REF, runs(run(cpu=1101, sel=D))), "MODE0_NO_EFFECT")
        self.assertEqual(K.mode0(REF, runs(run(cpu=1000, valid=False))), "UNPROVEN")
        self.assertEqual(K.mode0(REF, runs(run(cpu=1005, sel=C2))), "UNPROVEN")              # wrong counter select


class Overall(unittest.TestCase):
    def test_cases(self):
        M, X, P, A = "CLOCK_STOP_MATCHES", "CLOCK_STOP_EXCEEDS", "CLOCK_STOP_PARTIAL", "CLOCK_STOP_ABSENT"
        R, Dd, N = "MODE0_REMOVES_GAP", "MODE0_REDUCES_GAP", "MODE0_NO_EFFECT"
        self.assertEqual(K.overall([(M, R), (M, R)]), "CAUSE_CONFIRMED")
        self.assertEqual(K.overall([(A, N), (A, N)]), "CAUSE_REJECTED")
        for mixed in ([(M, R), (M, Dd)], [(M, R), (P, R)], [(X, R), (M, R)], [(M, N), (M, N)], [(A, R), (A, R)],
                      [(A, N), (A, Dd)]):
            self.assertEqual(K.overall(mixed), "MIXED", mixed)
        self.assertEqual(K.overall([(M, R), ("UNPROVEN", R)]), "UNPROVEN")
        self.assertEqual(K.overall([(M, R), (M, "UNPROVEN")]), "UNPROVEN")
        self.assertEqual(K.overall([]), "UNPROVEN")


class ModelVerdicts(unittest.TestCase):
    def test_drift_makes_the_model_unproven(self):
        c1 = runs(run(sram=200), run(sram=200)); d = runs(run(cpu=1005, sel=D))
        self.assertEqual(K.model_verdicts(REF, c1, CAL, d), ("CLOCK_STOP_MATCHES", "MODE0_REMOVES_GAP", "DRIFT_OK"))
        bad = runs(run(sram=200, active=1010))
        self.assertEqual(K.model_verdicts(REF, bad, CAL, d)[:2], ("UNPROVEN", "UNPROVEN"))
        cal_bad = runs(run(sram=1200, sel=C2, active=1010))
        self.assertEqual(K.model_verdicts(REF, c1, cal_bad, d)[:2], ("UNPROVEN", "UNPROVEN"))

    def test_small_gap_model_is_descriptive(self):
        ref = runs(run(cpu=1040), run(cpu=1040))                                            # frac 0.04 < 0.05
        c1 = runs(run(cpu=1040, sram=40)); cal = runs(run(cpu=1040, sram=1040, sel=C2))
        self.assertEqual(K.model_verdicts(ref, c1, cal, runs(run(cpu=1040, sel=D)))[:2], (None, None))
        ref = runs(run(cpu=1045), run(cpu=1045))                                            # 0.045: still below 0.05
        c1 = runs(run(cpu=1045, sram=45)); cal = runs(run(cpu=1045, sram=1045, sel=C2))
        self.assertEqual(K.model_verdicts(ref, c1, cal, runs(run(cpu=1045, sel=D)))[:2], (None, None))


if __name__ == "__main__":
    unittest.main()
