import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2_probe as P


def run(ev, valid=True, npu=1000):
    return dict(ev=dict(ev), ovf=set(), valid=valid, window=5000, infer=npu, infer_cpu=npu, sys=None, host_s=None)


SETS = {1: [48, 55, 35], 2: [64, 67, 35]}


def lut_runs(pairs, valid=True):
    """pairs: {set_id: [(slot0 composite, slot1 raw), ...]} -> runs keyed (set_id, rep)."""
    out = {}
    for s, vals in pairs.items():
        for i, (c, raw) in enumerate(vals):
            e0, e1, e2 = SETS[s]
            out[(s, i + 3)] = run({e0: c, e1: raw, e2: 1000}, valid)
    return out


class Identity(unittest.TestCase):
    def test_exact_close_fail(self):
        self.assertEqual(P.identity(lut_runs({1: [(50, 50), (60, 60)], 2: [(7, 7)]}), SETS), "LUT_IDENTITY_EXACT")
        self.assertEqual(P.identity(lut_runs({1: [(1000, 1001)], 2: [(7, 7)]}), SETS), "LUT_IDENTITY_CLOSE")
        self.assertEqual(P.identity(lut_runs({1: [(1000, 1002)], 2: [(7, 7)]}), SETS), "LUT_FAILS")      # 0.2 %
        self.assertEqual(P.identity(lut_runs({1: [(0, 0)], 2: [(7, 7)]}), SETS), "UNPROVEN")           # zero raw
        self.assertEqual(P.identity(lut_runs({1: [(5, 5)]}, valid=False), SETS), "UNPROVEN")
        self.assertEqual(P.identity({}, SETS), "UNPROVEN")


class Overlap(unittest.TestCase):
    def test_classes(self):
        f = lambda c, raw: P.overlap(lut_runs({1: [(c, raw), (c, raw)]}), SETS)[1]
        self.assertEqual(f(90, 100), ("STALL_WHILE_ACTIVE", 0.9))
        self.assertEqual(f(89, 100)[0], "PARTLY_WHILE_ACTIVE")
        self.assertEqual(f(11, 100)[0], "PARTLY_WHILE_ACTIVE")
        self.assertEqual(f(10, 100), ("STALL_WHILE_IDLE", 0.1))
        self.assertEqual(f(0, 0), ("COUNTED_ZERO", None))
        self.assertEqual(P.overlap(lut_runs({1: [(5, 5)]}, valid=False), SETS)[1], ("UNPROVEN", None))

    def test_lut_gate(self):
        o = P.overlap(lut_runs({1: [(90, 100)]}), SETS)
        self.assertEqual(P.gated(o, "LUT_FAILS")[1][0], "UNPROVEN")
        self.assertEqual(P.gated(o, "LUT_IDENTITY_CLOSE")[1][0], "STALL_WHILE_ACTIVE")


A = [35, 48, 51]


def mask_runs(vals, valid=True, npu=1000):
    return {(1, i + 3): run(dict(zip(A, v)), valid, npu) for i, v in enumerate(vals)}


CTL = mask_runs([(1000, 600, 500), (1000, 600, 500)])


class Mask(unittest.TestCase):
    def test_passthrough(self):
        self.assertEqual(P.passthrough(mask_runs([(1009, 605, 504)]), CTL), True)          # ≤ 1 %
        self.assertEqual(P.passthrough(mask_runs([(1011, 600, 500)]), CTL), False)
        self.assertEqual(P.passthrough(mask_runs([(1000, 600, 510)]), CTL), False)              # any one event
        self.assertEqual(P.passthrough(mask_runs([(1000, 600, 500)], npu=1011), CTL), False)    # NPU cycles too
        self.assertEqual(P.passthrough(mask_runs([(1000, 600, 500)], npu=1010), CTL), True)
        self.assertIsNone(P.passthrough(mask_runs([(1000, 600, 500)], valid=False), CTL))

    def test_additive(self):
        allr = mask_runs([(1000, 600, 500)])
        self.assertTrue(P.additive(mask_runs([(400, 250, 200)]), mask_runs([(605, 350, 300)]), allr))   # 1005: 0.5 %
        # PMCCNTR is not part of the sum (it may run regardless of the mask)
        self.assertTrue(P.additive(mask_runs([(400, 250, 200)], npu=1000), mask_runs([(600, 350, 300)], npu=1000),
                                   mask_runs([(1000, 600, 500)], npu=1000)))
        self.assertFalse(P.additive(mask_runs([(400, 250, 200)]), mask_runs([(620, 350, 300)]), allr))  # 2 %
        self.assertFalse(P.additive(mask_runs([(400, 250, 200)]), mask_runs([(600, 350, 320)]), allr))  # 51: 4 %
        self.assertIsNone(P.additive(mask_runs([(400, 250, 200)], valid=False), mask_runs([(600, 350, 300)]), allr))

    def test_default_state(self):
        self.assertEqual(P.default_state(mask_runs([(0, 0, 0)]), CTL), "MASK_DEFAULT_OFF")
        self.assertEqual(P.default_state(mask_runs([(1000, 600, 500)]), CTL), "MASK_DEFAULT_ON")
        self.assertEqual(P.default_state(mask_runs([(500, 300, 250)]), CTL), "MASK_DEFAULT_OTHER")
        self.assertEqual(P.default_state({}, CTL), "UNPROVEN")

    def test_model_and_overall(self):
        self.assertEqual(P.mask_verdict(True, True), "MASK_WORKS")
        self.assertEqual(P.mask_verdict(True, False), "MASK_NOT_ADDITIVE")
        self.assertEqual(P.mask_verdict(False, True), "MASK_DISTURBS")
        self.assertEqual(P.mask_verdict(None, True), "UNPROVEN")
        self.assertEqual(P.mask_verdict(True, None), "UNPROVEN")
        self.assertEqual(P.mask_overall(["MASK_WORKS", "MASK_WORKS"]), "MASK_WORKS")
        self.assertEqual(P.mask_overall(["MASK_WORKS", "MASK_NOT_ADDITIVE"]), "MASK_NOT_ADDITIVE")
        self.assertEqual(P.mask_overall(["MASK_DISTURBS", "MASK_NOT_ADDITIVE"]), "MASK_DISTURBS")
        self.assertEqual(P.mask_overall(["MASK_WORKS", "UNPROVEN"]), "UNPROVEN")
        self.assertEqual(P.mask_overall([]), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
