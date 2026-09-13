"""Gate tests for A6. Run from repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.test_a6_model_structure
Fixtures are synthetic; every rule must trip at its own id and every outcome must be reachable."""
import importlib.util, tempfile, unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("a6", Path(__file__).with_name("a6_model_structure.py"))
a6 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(a6)

PER_LAYER = """Original Operator,NNG Operator,Target,Staging Usage,Peak% (Staging),Op Cycles,Network% (cycles),NPU,SRAM AC,DRAM AC,OnFlash AC,OffFlash AC,MAC Count,Network% (MAC),Util% (MAC),Name
Conv2D,Conv2D,NPU,1,1,10,1,10,0,0,0,0,300,0,0,a
DepthwiseConv2D,DepthwiseConv2D,NPU,1,1,10,1,10,0,0,0,0,100,0,0,b
Softmax,Softmax,CPU,1,1,10,1,10,0,0,0,0,999,0,0,c
"""
SCHEDULE = """Performance for NPU Graph x
\t0: Operation Conv2D  - OFM 1, 32, 32, 16
\t\tKernel: size=3,3 stride=1,1
\t\tOperator Config = OFM Block=[1, 8, 8, 16], IFM Block=[1, 10, 10, 8], OFM UBlock=[1, 4, 8] Traversal=DepthFirst, AccType=Acc32
\t\tOFM Stripe   = [1, 32, 32, 16]
\t1: Operation MemoryCopy  - OFM 1, 1, 1, 42
\t\tOperator Config = OFM Block=[1, 1, 2, 48], IFM Block=[1, 1, 2, 48], Traversal=DepthFirst, AccType=SHRAM_Acc32
"""


def series(shares, effs):
    return [{"dw_mac_share": s, "mean_incremental_efficiency": e} for s, e in zip(shares, effs)]


def ops(n_improve, n_regress, size_improve=1000, size_regress=100):
    rows = [{"op_identity": f"Conv2D|10x10x{size_improve // 100}|1x1|0", "direction": "IMPROVE"} for _ in range(n_improve)]
    rows += [{"op_identity": f"Add|10x10x{max(size_regress // 100, 1)}|1x1|0", "direction": "REGRESS"} for _ in range(n_regress)]
    return rows


class Extraction(unittest.TestCase):
    def test_per_layer_counts_npu_ops_only(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(PER_LAYER); p = f.name
        s = a6.per_layer_structure(p)
        self.assertEqual((s["npu_op_count"], s["dwconv_op_count"], s["total_mac"]), (2, 1, 400))
        self.assertAlmostEqual(s["dwconv_mac_share"], 0.25)

    def test_schedule_parse(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(SCHEDULE); p = f.name
        o = a6.schedule_ops(p)
        self.assertEqual(len(o), 2)
        self.assertEqual((o[0]["type"], o[0]["ofm"], o[0]["ublock"]), ("Conv2D", [1, 32, 32, 16], [1, 4, 8]))
        self.assertEqual((o[1]["type"], o[1]["ublock"]), ("MemoryCopy", None))


class H4(unittest.TestCase):
    def test_matches_when_more_depthwise_means_lower_efficiency(self):
        v = a6.h4_verdict(series([0.0, 0.1, 0.2, 0.3, 0.4], [0.9, 0.8, 0.7, 0.6, 0.5]))
        self.assertEqual(v["outcome"], "DW_SHARE_ORDER_MATCHES"); self.assertAlmostEqual(v["rho"], -1.0)

    def test_no_relation(self):
        v = a6.h4_verdict(series([0.0, 0.1, 0.2, 0.3, 0.4], [0.5, 0.9, 0.6, 0.8, 0.7]))
        self.assertEqual(v["outcome"], "NO_ORDER_RELATION")

    def test_too_few_series_trips_rule(self):
        v = a6.h4_verdict(series([0.0, 0.1, 0.2], [0.9, 0.8, 0.7]))
        self.assertEqual((v["outcome"], v["rule"]), ("NOT_EVALUABLE", a6.RULE_TOO_FEW))

    def test_no_variation_trips_rule(self):
        v = a6.h4_verdict(series([0.2] * 5, [0.9, 0.8, 0.7, 0.6, 0.5]))
        self.assertEqual((v["outcome"], v["rule"]), ("NOT_EVALUABLE", a6.RULE_NO_VARIATION))


class H5(unittest.TestCase):
    def test_concentrated(self):
        self.assertEqual(a6.h5_verdict(ops(6, 6, 1000, 100))["outcome"], "SMALL_FM_CONCENTRATED")

    def test_not_concentrated(self):
        self.assertEqual(a6.h5_verdict(ops(6, 6, 1000, 900))["outcome"], "NOT_CONCENTRATED")

    def test_too_few_trips_rule(self):
        v = a6.h5_verdict(ops(6, 2))
        self.assertEqual((v["outcome"], v["rule"]), ("NOT_EVALUABLE", a6.RULE_TOO_FEW))

    def test_unparsed_shape_trips_rule(self):
        rows = ops(6, 6); rows[0]["op_identity"] = "Conv2D|weird|1x1|0"
        v = a6.h5_verdict(rows)
        self.assertEqual((v["outcome"], v["rule"]), ("NOT_EVALUABLE", a6.RULE_SHAPE_UNPARSED))


class Closure(unittest.TestCase):
    def test_every_rule_and_outcome_reachable(self):
        tripped = {a6.h4_verdict(series([0.0] * 3, [0.1] * 3))["rule"], a6.h4_verdict(series([0.2] * 5, [0.9, 0.8, 0.7, 0.6, 0.5]))["rule"]}
        bad = ops(6, 6); bad[0]["op_identity"] = "x"
        tripped.add(a6.h5_verdict(bad)["rule"])
        self.assertEqual(tripped, set(a6.RULES))
        seen4 = {a6.h4_verdict(s)["outcome"] for s in (series([0, .1, .2, .3, .4], [.9, .8, .7, .6, .5]),
                                                       series([0, .1, .2, .3, .4], [.5, .9, .6, .8, .7]), series([0], [0]))}
        self.assertEqual(seen4, set(a6.H4_OUTCOMES))
        seen5 = {a6.h5_verdict(o)["outcome"] for o in (ops(6, 6, 1000, 100), ops(6, 6, 1000, 900), ops(6, 1))}
        self.assertEqual(seen5, set(a6.H5_OUTCOMES))


if __name__ == "__main__":
    unittest.main()
