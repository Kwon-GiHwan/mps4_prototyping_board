import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2b3_existing as X


class Lag(unittest.TestCase):
    MACS = [100, 20, 3000, 0]

    def test_lagged(self):
        self.assertEqual(X.lagged(self.MACS, {2}, 0), 3000)
        self.assertEqual(X.lagged(self.MACS, {2}, 1), 20)            # window of op 2 holds op 1's work
        self.assertEqual(X.lagged(self.MACS, {2}, 2), 100)
        self.assertEqual(X.lagged(self.MACS, {0}, 1), 0)             # nothing before op 0
        self.assertEqual(X.lagged(self.MACS, {0, 1, 2, 3}, 1), 3120) # op 3's work falls past the last window

    def test_efficiency(self):
        self.assertEqual(X.efficiency(2048, 4), 0.5)
        self.assertEqual(X.efficiency(4096, 2), 2.0)
        self.assertIsNone(X.efficiency(0, 0))
        self.assertEqual(X.efficiency(5, 0), float("inf"))
        self.assertIsNone(X.efficiency(0, None))

    def test_min_cycles(self):
        op = lambda t, m, sp=0: dict(type=t, macs=str(m), sparse=str(sp))
        self.assertEqual(X.min_cycles(op("CONV", 4096)), 4.0)
        self.assertEqual(X.min_cycles(op("CONV", 4096, 1)), 2.0)               # 2:4 sparsity doubles the peak
        self.assertEqual(X.min_cycles(op("DEPTHWISE", 4096)), 32.0)            # 128 MACs/cycle
        self.assertEqual(X.min_cycles(op("DEPTHWISE", 4096, 1)), 32.0)         # sparsity: convolutions only
        self.assertEqual(X.min_cycles(op("POOL", 4096)), 0)

    def test_windows(self):
        w = X.windows(["CONV", "CONV", "DEPTHWISE", "POOL", "CONV"])
        self.assertEqual(w["g_CONV"], {0, 1, 4})
        self.assertEqual(w["g_DEPTHWISE"], {2})
        self.assertEqual(w["m_all"], {0, 1, 2, 3, 4})
        self.assertEqual((w["m_a"], w["m_b"]), ({0, 1}, {2, 3, 4}))  # 2B-0b split: cms.gate(0, n // 2)


if __name__ == "__main__":
    unittest.main()
