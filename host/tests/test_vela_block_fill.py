import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import vela_block_fill as V

TXT = """Schedule: 'x'
\t0: Operation Conv2D  - OFM 1, 49, 10, 140
\t\tOperator Config = OFM Block=[1, 24, 10, 32], IFM Block=[1, 32, 16, 16], OFM UBlock=[2, 2, 32] Traversal=PartKernel
\t\tEstimated Perf: Macs=300 Cycles=10
\t1: Operation DepthwiseConv2D  - OFM 1, 4, 4, 32
\t\tOperator Config = OFM Block=[4, 4, 32], IFM Block=[1, 4, 4, 32], OFM UBlock=[2, 4, 16] Traversal=Depthwise
\t\tEstimated Perf: Macs=100 Cycles=5
\t2: Operation Reshape  - OFM 1, 4, 4, 32
"""


class T(unittest.TestCase):
    def test_fill(self):
        self.assertEqual(V.fill([49, 10, 140], [24, 10, 32]), 49 * 10 * 140 / (72 * 10 * 160))
        self.assertEqual(V.fill([4, 4, 32], [4, 4, 32]), 1.0)

    def test_parse_and_weight(self):
        ops = V.parse(TXT)
        self.assertEqual([o["op"] for o in ops], ["Conv2D", "DepthwiseConv2D"])   # no MACs -> not counted
        b, u, n, w = V.model_fill(ops)
        self.assertEqual((n, w), (2, 400))
        self.assertAlmostEqual(b, (V.fill([49, 10, 140], [24, 10, 32]) * 300 + 1.0 * 100) / 400)


if __name__ == "__main__":
    unittest.main()
