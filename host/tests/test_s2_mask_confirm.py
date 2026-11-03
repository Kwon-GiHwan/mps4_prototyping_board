import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2_mask_confirm as C

A = (35, 48)                      # 35 jittery (npu_active-like), 48 fixed by the command stream (mac_active-like)


def run(v35, v48, npu, valid=True):
    return dict(ev={35: v35, 48: v48}, valid=valid, infer=npu)


def runs(rows, valid=True):
    return [run(*r, valid=valid) for r in rows]


# control: 35 spans 980..1000 (width 2 %), 48 fixed at 500, NPU cycles 2000..2040 (width 2 %)
CTL = runs([(980, 500, 2000), (990, 500, 2020), (1000, 500, 2040)])
CTL2 = runs([(985, 500, 2005), (995, 500, 2025), (990, 500, 2030)])


def arms(**kw):
    a = dict(ctl=CTL, ctl2=CTL2, m_all=runs([(990, 500, 2020)]),
             m_a=runs([(400, 200, 900)]), m_b=runs([(590, 300, 900)]))
    a.update(kw)
    return a


class Width(unittest.TestCase):
    def test_width_and_class(self):
        self.assertAlmostEqual(C.width([980, 990, 1000]), 20 / 990)
        self.assertEqual(C.width([0, 0]), 0.0)
        self.assertEqual(C.width([0, 0, 5]), float("inf"))
        self.assertIsNone(C.width([]))
        self.assertEqual(C.klass(0.001), "DETERMINISTIC")
        self.assertEqual(C.klass(0.0011), "JITTERY")
        self.assertEqual(C.klass(0.05), "JITTERY")
        self.assertEqual(C.klass(0.0501), "NOISY")
        self.assertEqual(C.klass(None), "MISSING")

    def test_tolerance(self):
        self.assertEqual(C.tol_pass(0.0), 0.001)
        self.assertEqual(C.tol_pass(0.005), 0.01)          # floor 1 %
        self.assertEqual(C.tol_pass(0.03), 0.03)


class Verdict(unittest.TestCase):
    def test_works(self):
        self.assertEqual(C.model_verdict(arms())[0], "MASK_WORKS")

    def test_jittery_event_may_move_within_the_control_width(self):
        # 35: ctl median 990, m_all 1008 = +1.8 % < width 2.04 % -> still passthrough (the old 1 % band would fail)
        self.assertEqual(C.model_verdict(arms(m_all=runs([(1008, 500, 2020)]), m_b=runs([(608, 300, 900)])))[0],
                         "MASK_WORKS")
        self.assertEqual(C.model_verdict(arms(m_all=runs([(1012, 500, 2020)]), m_b=runs([(612, 300, 900)])))[0],
                         "MASK_DISTURBS")                  # +2.2 % > width

    def test_fixed_event_must_stay_fixed(self):
        self.assertEqual(C.model_verdict(arms(m_all=runs([(990, 501, 2020)]), m_b=runs([(590, 301, 900)])))[0],
                         "MASK_DISTURBS")                  # 0.2 % on a deterministic event
        self.assertEqual(C.model_verdict(arms(m_all=runs([(990, 500, 2070)])))[0], "MASK_DISTURBS")   # NPU +2.5 %

    def test_additive(self):
        self.assertEqual(C.model_verdict(arms(m_b=runs([(590, 304, 900)])))[0], "MASK_WORKS")       # 48: 0.8 %
        self.assertEqual(C.model_verdict(arms(m_b=runs([(590, 306, 900)])))[0], "MASK_NOT_ADDITIVE")  # 1.2 %
        self.assertEqual(C.model_verdict(arms(m_b=runs([(615, 300, 900)])))[0], "MASK_NOT_ADDITIVE")  # 35: 2.5 %
        # NPU cycles are not part of the sum
        self.assertEqual(C.model_verdict(arms(m_b=runs([(590, 300, 5000)])))[0], "MASK_WORKS")

    def test_aa_gate(self):
        for bad in (runs([(980, 501, 2000), (990, 501, 2020)]),       # control boot 2 moves a fixed event 0.2 %
                    runs([(1015, 500, 2020)]),                        # a jittery one beyond boot 1's width (+2.5 %)
                    runs([(990, 500, 2080)])):                        # NPU cycles +3 %
            v, d = C.model_verdict(arms(ctl2=bad))
            self.assertEqual(v, "UNPROVEN")
            self.assertFalse(d["aa"])
        self.assertTrue(C.model_verdict(arms(ctl2=runs([(1008, 500, 2050)])))[1]["aa"])   # within 2 %

    def test_noisy_event_not_judged_but_npu_must_be(self):
        noisy = dict(ctl=runs([(800, 500, 2000), (1000, 500, 2020)]), ctl2=runs([(1000, 500, 2010)]))
        v, d = C.model_verdict(arms(m_all=runs([(1100, 500, 2010)]), m_b=runs([(700, 300, 900)]), **noisy))
        self.assertEqual(v, "MASK_WORKS")
        self.assertEqual(d["noisy"], [35])
        npu_noisy = dict(ctl=runs([(990, 500, 2000), (990, 500, 2200)]), ctl2=runs([(990, 500, 2100)]))
        self.assertEqual(C.model_verdict(arms(**npu_noisy))[1]["reason"], "NPU cycles missing or too noisy")
        self.assertEqual(C.model_verdict(arms(**npu_noisy))[0], "UNPROVEN")

    def test_zero_event(self):
        z = lambda rows: [dict(r, ev={**r["ev"], 51: 0}) for r in rows]
        a = {k: z(v) for k, v in arms().items()}
        self.assertEqual(C.model_verdict(a)[0], "MASK_WORKS")
        a["m_all"] = [dict(r, ev={**r["ev"], 51: 1}) for r in a["m_all"]]
        self.assertEqual(C.model_verdict(a)[0], "MASK_DISTURBS")

    def test_missing_or_invalid(self):
        self.assertEqual(C.model_verdict(arms(m_a=[]))[0], "UNPROVEN")
        self.assertEqual(C.model_verdict(arms(m_all=runs([(990, 500, 2020)], valid=False)))[0], "UNPROVEN")
        no48 = [dict(r, ev={35: r["ev"][35]}) for r in CTL]
        self.assertEqual(C.model_verdict(arms(ctl=no48, ctl2=no48))[0], "MASK_WORKS")  # event absent everywhere
        for a in ("ctl2", "m_all", "m_a", "m_b"):                                   # event missing in one arm
            v, d = C.model_verdict(arms(**{a: [dict(r, ev={35: r["ev"][35]}) for r in arms()[a]]}))
            self.assertEqual((v, d["reason"]), ("UNPROVEN", "an event of the control missing in another arm"))
        nonpu = [dict(r, infer=None) for r in CTL]
        self.assertEqual(C.model_verdict(arms(ctl=nonpu))[1]["reason"], "NPU cycles missing or too noisy")

    def test_overall(self):
        self.assertEqual(C.overall(["MASK_WORKS"] * 7), "MASK_WORKS")
        self.assertEqual(C.overall(["MASK_WORKS", "MASK_NOT_ADDITIVE"]), "MASK_NOT_ADDITIVE")
        self.assertEqual(C.overall(["MASK_NOT_ADDITIVE", "MASK_DISTURBS"]), "MASK_DISTURBS")
        self.assertEqual(C.overall(["MASK_DISTURBS", "UNPROVEN"]), "UNPROVEN")
        self.assertEqual(C.overall([]), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
