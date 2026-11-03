import sys, unittest, pathlib, tempfile
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2_groups as G


def runs(rows, valid=True, s=1, npu=1000):
    """rows: [{event: value}, ...] -> RUNs of set s."""
    return {(s, i + 3): dict(ev=dict(r), valid=valid, infer=npu) for i, r in enumerate(rows)}


def same(ev, n=3, **kw):
    return runs([ev] * n, **kw)


TOTAL = runs([{35: 1000, 48: 600}, {35: 1010, 48: 600}, {35: 990, 48: 600}])     # 35 width 2 %, 48 fixed


class Partition(unittest.TestCase):
    def test_holds_and_leaks(self):
        g = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 300, 48: 100}))
        self.assertEqual(G.partition(g, TOTAL)[0], "PARTITION_HOLDS")
        g2 = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 318, 48: 100}))    # 35: +1.8 % < 2 %
        self.assertEqual(G.partition(g2, TOTAL)[0], "PARTITION_HOLDS")
        g3 = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 325, 48: 100}))    # 35: +2.5 %
        self.assertEqual(G.partition(g3, TOTAL)[0], "PARTITION_LEAKS")
        g4 = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 300, 48: 107}))    # 48: +1.2 % > floor 1 %
        self.assertEqual(G.partition(g4, TOTAL)[0], "PARTITION_LEAKS")
        g5 = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 300, 48: 105}))    # 48: +0.8 %
        self.assertEqual(G.partition(g5, TOTAL)[0], "PARTITION_HOLDS")

    def test_npu_cycles_not_summed_and_noisy_not_judged(self):
        g = dict(CONV=same({35: 700, 48: 500}, npu=5000), DEPTHWISE=same({35: 300, 48: 100}, npu=5000))
        self.assertEqual(G.partition(g, TOTAL)[0], "PARTITION_HOLDS")
        noisy = runs([{35: 1000, 48: 600, 53: 100}, {35: 1000, 48: 600, 53: 110}])        # 53 width 9.5 %
        g = dict(CONV=same({35: 700, 48: 500, 53: 10}), DEPTHWISE=same({35: 300, 48: 100, 53: 10}))
        v, rows = G.partition(g, noisy)
        self.assertEqual(v, "PARTITION_HOLDS")
        self.assertFalse(rows[(1, 53)][2])
        self.assertFalse(rows[(1, 53)][3])
        edge = runs([{35: 1000, 53: 95}, {35: 1000, 53: 100}, {35: 1000, 53: 100}])         # width exactly 5 %: judged
        g = dict(CONV=same({35: 700, 53: 60}), DEPTHWISE=same({35: 300, 53: 60}))
        self.assertEqual(G.partition(g, edge)[0], "PARTITION_LEAKS")

    def test_zero_total(self):
        t = same({35: 1000, 51: 0})
        self.assertEqual(G.partition(dict(A=same({35: 600, 51: 0}), B=same({35: 400, 51: 0})), t)[0], "PARTITION_HOLDS")
        self.assertEqual(G.partition(dict(A=same({35: 600, 51: 1}), B=same({35: 400, 51: 0})), t)[0], "PARTITION_LEAKS")

    def test_unproven(self):
        g = dict(CONV=same({35: 700, 48: 500}), DEPTHWISE=same({35: 300, 48: 100}))
        self.assertEqual(G.partition(g, {})[0], "UNPROVEN")
        self.assertEqual(G.partition({}, TOTAL)[0], "UNPROVEN")
        self.assertEqual(G.partition(dict(g, CONV=same({35: 700, 48: 500}, valid=False)), TOTAL)[0], "UNPROVEN")
        self.assertEqual(G.partition(dict(g, CONV=same({35: 700})), TOTAL)[0], "UNPROVEN")           # event missing
        self.assertEqual(G.partition(g, same({}))[0], "UNPROVEN")                                   # nothing to judge

    def test_of_set(self):
        r = runs([{35: 1}]) | runs([{35: 2}, {35: 3}], s=2)
        self.assertEqual(sorted(G.of_set(r, 2)), [(2, 3), (2, 4)])

    def test_width(self):
        self.assertAlmostEqual(G.width([990, 1000, 1010]), 0.02)
        self.assertEqual(G.width([0, 0]), 0.0)
        self.assertEqual(G.width([0, 0, 3]), float("inf"))


class Hypotheses(unittest.TestCase):
    def test_ratio(self):
        r = runs([{35: 100, 48: 50}, {35: 200, 48: 60}, {35: 0, 48: 1}]) | runs([{35: 100, 48: 99}], s=2)
        self.assertEqual(G.ratio(r, 1, 48), 0.4)          # median of 0.5, 0.3; the npu_active 0 RUN is skipped
        self.assertIsNone(G.ratio(same({35: 0, 48: 5}), 1, 48))

    def test_h1(self):
        c, d = same({35: 100, 48: 60}), same({35: 100, 48: 20})
        self.assertEqual(G.h1(dict(CONV=c, DEPTHWISE=d), 1), "DW_LOWER")
        self.assertEqual(G.h1(dict(CONV=d, DEPTHWISE=c), 1), "DW_NOT_LOWER")
        self.assertEqual(G.h1(dict(CONV=c, DEPTHWISE=c), 1), "DW_NOT_LOWER")
        self.assertEqual(G.h1(dict(CONV=c), 1), "NOT_APPLICABLE")
        self.assertEqual(G.h1(dict(DEPTHWISE=d), 1), "NOT_APPLICABLE")
        self.assertEqual(G.h1(dict(CONV=c, DEPTHWISE=same({35: 0, 48: 5})), 1), "UNPROVEN")

    def test_h2(self):
        g = dict(CONV=same({35: 600}), DEPTHWISE=same({35: 400}))      # DW time share 0.4
        self.assertEqual(G.h2(g, 1, 0.2), ("DW_COSTLY", 2.0))
        v, q = G.h2(g, 1, 0.21)
        self.assertEqual(v, "DW_NOT_COSTLY"); self.assertAlmostEqual(q, 0.4 / 0.21)
        self.assertEqual(G.h2(dict(CONV=same({35: 600})), 1, 0.2), ("NOT_APPLICABLE", None))
        self.assertEqual(G.h2(g, 1, None), ("NOT_APPLICABLE", None))
        self.assertEqual(G.h2(dict(CONV=same({35: 0}), DEPTHWISE=same({35: 0})), 1, 0.2), ("UNPROVEN", None))

    def test_gate_and_overall(self):
        self.assertEqual(G.gated("DW_LOWER", "PARTITION_HOLDS"), "DW_LOWER")
        self.assertEqual(G.gated("DW_LOWER", "PARTITION_LEAKS"), "UNPROVEN")
        self.assertEqual(G.overall(["DW_LOWER", "NOT_APPLICABLE", "DW_LOWER"]), "DW_LOWER")
        self.assertEqual(G.overall(["DW_LOWER", "DW_NOT_LOWER"]), "MIXED")
        self.assertEqual(G.overall(["DW_LOWER", "UNPROVEN"]), "UNPROVEN")
        self.assertEqual(G.overall(["NOT_APPLICABLE"]), "UNPROVEN")

    def test_dw_mac_share(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("model,index,op,macs\na,0,Conv2D,300\na,1,DepthwiseConv2D,100\nb,0,Conv2D,5\nc,0,Conv2D,0\n")
        self.assertEqual(G.dw_mac_share(f.name), {"a": 0.25, "b": 0.0})


if __name__ == "__main__":
    unittest.main()
