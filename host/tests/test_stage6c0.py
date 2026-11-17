"""Stage 6C-0 rules (evidence/stage6c0/contract.md). Expected values typed by hand."""
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis")]
import stage6c0 as C  # noqa: E402


def r(**kw):
    x = {k: None for k in C.FIELDS}
    x.update(kw)
    return x


class Constants(unittest.TestCase):
    def test_frozen(self):
        self.assertEqual((C.TOL, C.LOW_EVIDENCE_MAX, C.IMPORTANCE_MIN, C.MAX_BOOTS), (0.01, 2, 0.10, 9))
        self.assertEqual(C.MEASURED_SHAPES, {"F1": 2, "F2": 1, "F3": 1, "F4": 0, "F5": 0})
        self.assertEqual(C.PRIORITY, ("F1", "F2", "F3", "F4", "F5"))
        self.assertEqual(C.CONTROL["F1"], ("cin16", "cout2"))
        self.assertEqual(C.CONTROL["F2"], ("c16", "k5"))
        self.assertIsNone(C.CONTROL["F4"])


class Tags(unittest.TestCase):
    A = dict(mac_active=1000.0, mac_dpu_active=500.0, npu_active=10000.0, npu_range=50.0, sram_rd_bytes=100.0, ext_rd_bytes=100.0,
             sram_wr_bytes=50.0, ext_wr_bytes=50.0, ext_rd_trans=10.0, traversal="PartKernel", ofm_block="8x8x16")

    def t(self, var="shape", **b):
        return C.tags(r(**self.A), r(**dict(self.A, **b)), var)

    def test_none(self):
        self.assertEqual(self.t()["tags"], [])

    def test_compute(self):
        self.assertIn("COMPUTE_COST_CHANGE", self.t(mac_active=1011.0)["tags"])
        self.assertNotIn("COMPUTE_COST_CHANGE", self.t(mac_active=1010.0)["tags"])
        self.assertIn("COMPUTE_COST_CHANGE", self.t(mac_dpu_active=506.0)["tags"])

    def test_transfer(self):
        self.assertIn("DATA_TRANSFER_CHANGE", self.t(ext_rd_bytes=103.0)["tags"])      # read total +1.5 %
        self.assertNotIn("DATA_TRANSFER_CHANGE", self.t(ext_rd_bytes=102.0)["tags"])   # +1 %
        self.assertIn("DATA_TRANSFER_CHANGE", self.t(sram_wr_bytes=52.0)["tags"])
        self.assertIn("DATA_TRANSFER_CHANGE", self.t(ext_rd_trans=11.0)["tags"])
        self.assertNotIn("DATA_TRANSFER_CHANGE", self.t(ext_rd_bytes=None)["tags"])    # missing never tags

    def test_memory_condition(self):
        for v in ("placement", "latency", "sram_budget"):
            self.assertIn("MEMORY_SERVICE_CONDITION_CHANGE", self.t(var=v)["tags"])
        self.assertNotIn("MEMORY_SERVICE_CONDITION_CHANGE", self.t(var="kernel")["tags"])

    def test_mapping(self):
        self.assertIn("COMPILER_MAPPING_CHANGE", self.t(traversal="DepthFirst")["tags"])
        self.assertIn("COMPILER_MAPPING_CHANGE", self.t(ofm_block="8x16x16")["tags"])
        self.assertNotIn("COMPILER_MAPPING_CHANGE", self.t(ofm_block=None)["tags"])

    def test_pipeline_and_unresolved(self):
        x = self.t(npu_active=10101.0, npu_range=50.0)               # +101 > max(100, 100)
        self.assertEqual(x["tags"], ["PIPELINE_DEPENDENCY_CANDIDATE"])
        self.assertTrue(x["npu_significant"])
        self.assertEqual(self.t(npu_active=10100.0)["tags"], [])      # = tol
        y = self.t(npu_active=12000.0, mac_active=None)                # MAC unknown -> no pipeline tag
        self.assertEqual(y["tags"], ["CAUSE_UNRESOLVED"])
        z = self.t(npu_active=12000.0, mac_active=1500.0)
        self.assertEqual(z["tags"], ["COMPUTE_COST_CHANGE"])
        self.assertEqual(self.t(npu_active=10140.0, npu_range=100.0)["tags"], [])   # ranges 150 > 140


class Vela(unittest.TestCase):
    def test_direction(self):
        self.assertEqual(C.direction(0.10), "WITHIN_10PCT")
        self.assertEqual(C.direction(-0.10), "WITHIN_10PCT")
        self.assertEqual(C.direction(0.11), "UNDER_PREDICTS")
        self.assertEqual(C.direction(-0.11), "OVER_PREDICTS")

    def test_table(self):
        t = C.vela_table([r(key="a", npu_active=200.0, vela_total=100.0, vela_npu=50.0), r(key="b", npu_active=90.0, vela_npu=100.0),
                          r(key="c", npu_active=90.0)])
        self.assertEqual([(x["key"], x["basis"], x["error"]) for x in t], [("a", "vela_total", 1.0), ("b", "vela_npu", -0.1)])


def op(model, idx, npu_op, kernel, trav, cin, cout, n):
    return dict(model=model, tflite_op_index=str(idx), npu_op=npu_op, kernel=kernel, traversal=trav, cin=str(cin), cout=str(cout),
                n_mac_tflite=str(n), stride="1x1", npu_ofm_hwc="8x8x8", ofm_block="8x8x8", ofm_ublock="2x2x8")


class Selection(unittest.TestCase):
    OPS = [op("m1", 0, "Conv2D", "1x1", "PartKernel", 4, 24, 300), op("m1", 1, "Conv2D", "1x1", "PartKernel", 8, 8, 100),
           op("m1", 2, "Conv2D", "1x1", "DepthFirst", 64, 64, 600), op("m2", 0, "DepthwiseConv2D", "3x3", "Depthwise", 8, 8, 50),
           op("m2", 1, "Conv2D", "1x1", "DepthFirst", 64, 64, 950), op("m3", 0, "FullyConnected", "1x1", "DepthFirst", 96, 288, 100),
           op("m4", 0, "Conv2D", "1x32", "PartKernel", 250, 2000, 900), op("m4", 1, "Conv2D", "1x5", "PartKernel", 250, 250, 100),
           op("m5", 0, "Conv2D", "10x4", "PartKernel", 1, 140, 200), op("m5", 1, "Conv2D", "3x3", "PartKernel", 16, 16, 800)]

    def test_family(self):
        fam = [C.family_of_op(o) for o in self.OPS]
        self.assertEqual(fam, ["F1", "F1", None, "F2", None, "F3", "F4", None, "F5", None])

    def test_shares_and_rep(self):
        s = C.family_shares(self.OPS)
        self.assertEqual(s["F1"], {"m1": 0.4})
        self.assertEqual(s["F2"], {"m2": 0.05})
        self.assertEqual(s["F3"], {"m3": 1.0})
        self.assertEqual(s["F5"], {"m5": 0.2})
        self.assertEqual(C.representative(self.OPS, "F1", s)["tflite_op_index"], "0")
        self.assertIsNone(C.representative(self.OPS, "F9", s))

    def test_control(self):
        self.assertEqual(C.control_variant("F1", dict(cin="4")), "cin16")
        self.assertEqual(C.control_variant("F1", dict(cin="32")), "cout2")
        self.assertEqual(C.control_variant("F2", dict(cin="8")), "c16")
        self.assertEqual(C.control_variant("F2", dict(cin="144")), "k5")
        self.assertIsNone(C.control_variant("F4", dict(cin="250")))

    def test_static(self):
        s = C.select_static(self.OPS)
        self.assertTrue(s["F1"]["c1_low_evidence"] and s["F1"]["c2_importance"] and s["F1"]["c3_new"])
        self.assertFalse(s["F2"]["c2_importance"])                       # 0.05 < 0.10
        self.assertFalse(s["F3"]["c3_new"])                              # (DepthFirst, 1x1, Cin 96 % 16 == 0) already measured
        self.assertEqual([x["name"] for x in C.specs(s)], ["s6c_f1_rep", "s6c_f1_cin16", "s6c_f4_rep", "s6c_f5_rep"])

    def fact(self, name, ok=True, trav="PartKernel", blk="8x8x8", ub="2x2x8", fast=0x100, arena=0x1000, mlen=0x1000, cpu=()):
        row = dict(traversal=trav, ofm_block=blk, ofm_ublock=ub, vela_op_cycles="1", vela_npu_cycles="1", sram_ac="1", dram_ac="1")
        return dict(name=name, npu_rows=[row] if ok else [], cpu_rows=list(cpu), pack_rc=0, fast_size=fast, arena_size=arena,
                    model_len=mlen)

    def test_compile_checks(self):
        rep = dict(traversal="PartKernel", ofm_block="8x8x8", ofm_ublock="2x2x8")
        self.assertEqual(C.compile_checks(self.fact("x"), rep)["mapping"], "MAPPING_SAME")
        self.assertEqual(C.compile_checks(self.fact("x", blk="8x16x8"), rep)["mapping"], "COMPILER_MAPPING_CHANGE")
        self.assertTrue(C.compile_checks(self.fact("x"), rep)["c5_ok"])
        for kw in (dict(ok=False), dict(cpu=("ADD",)), dict(fast=0x60001), dict(arena=0x200001), dict(mlen=(32 << 20))):
            self.assertFalse(C.compile_checks(self.fact("x", **kw), rep)["c5_ok"], kw)
        self.assertTrue(C.compile_checks(self.fact("x", fast=0x60000, arena=0x200000), rep)["c5_ok"])
        bad = dict(self.fact("x"), pack_rc=1)
        self.assertFalse(C.compile_checks(bad, rep)["c5_ok"])
        nov = self.fact("x"); nov["npu_rows"][0]["dram_ac"] = ""
        self.assertFalse(C.compile_checks(nov, rep)["c5_ok"])

    def test_final(self):
        s = C.select_static(self.OPS)
        facts = [self.fact("s6c_f1_rep"), self.fact("s6c_f1_cin16", trav="DepthFirst"), self.fact("s6c_f4_rep", ok=False),
                 self.fact("s6c_f5_rep")]
        f = C.select_final(s, facts)
        self.assertEqual(f["selected"], ["F1", "F5"])
        self.assertEqual(f["shapes"], ["s6c_f1_rep", "s6c_f1_cin16", "s6c_f5_rep"])
        self.assertEqual(f["boots"], 4)
        self.assertEqual(s["F1"]["control_check"]["mapping_vs_rep"], "COMPILER_MAPPING_CHANGE")
        self.assertFalse(s["F1"]["control_check"]["traversal_same"])

    def test_rep_model_is_largest_share(self):
        ops = self.OPS + [op("m6", 0, "Conv2D", "1x1", "PartKernel", 4, 24, 100), op("m6", 1, "Conv2D", "1x1", "DepthFirst", 64, 64, 900)]
        s = C.family_shares(ops)
        self.assertEqual(s["F1"], {"m1": 0.4, "m6": 0.1})
        self.assertEqual(C.representative(ops, "F1", s)["model"], "m1")

    def test_c1(self):
        orig = dict(C.MEASURED_SHAPES)
        try:
            C.MEASURED_SHAPES["F1"] = 3
            self.assertFalse(C.select_static(self.OPS)["F1"]["c1_low_evidence"])
            C.MEASURED_SHAPES["F1"] = 2
            self.assertTrue(C.select_static(self.OPS)["F1"]["c1_low_evidence"])
        finally:
            C.MEASURED_SHAPES.clear(); C.MEASURED_SHAPES.update(orig)

    def test_c5_items(self):
        rep = dict(traversal="PartKernel", ofm_block="8x8x8", ofm_ublock="2x2x8")
        two = self.fact("x"); two["npu_rows"] = two["npu_rows"] * 2
        self.assertFalse(C.compile_checks(two, rep)["c5"]["single_npu_op"])
        self.assertFalse(C.compile_checks(dict(self.fact("x"), pack_rc=1), rep)["c5"]["packed"])

    def test_final_gates(self):
        s = C.select_static(self.OPS)
        f = C.select_final(s, [self.fact("s6c_f1_rep", blk="8x16x8"), self.fact("s6c_f1_cin16"), self.fact("s6c_f5_rep", fast=0x60001)])
        self.assertEqual(f["selected"], [])                               # F1: mapping change (C4); F5: C5 fails
        s = C.select_static(self.OPS)
        f = C.select_final(s, [self.fact("s6c_f1_rep"), self.fact("s6c_f1_cin16", arena=0x200001)])
        self.assertEqual((f["selected"], f["shapes"]), (["F1"], ["s6c_f1_rep"]))   # control fails C5 -> not scheduled

    def test_budget(self):
        orig = C.MAX_BOOTS
        try:
            C.MAX_BOOTS = 3
            s = C.select_static(self.OPS)
            f = C.select_final(s, [self.fact("s6c_f1_rep"), self.fact("s6c_f1_cin16"), self.fact("s6c_f5_rep")])
            self.assertEqual((f["selected"], f["dropped_for_budget"], f["boots"]), (["F1"], ["F5"], 3))
        finally:
            C.MAX_BOOTS = orig


class Loaders(unittest.TestCase):
    """Values read back from committed result files (checked by hand against those files)."""
    def test_integrate(self):
        rows = C.integrate()
        by = {x["key"]: x for x in rows}
        self.assertEqual(by["driver_m7:kws_micronet_m"]["npu_active"], 91540.0)
        self.assertEqual(by["driver_m7:kws_micronet_m"]["vela_total"], 102248.0)
        self.assertEqual(by["stage4:conv_base"]["mac_active"] is not None, True)
        self.assertEqual(by["stage4p:conv_base_ddr"]["npu_active"], 21086.5)
        self.assertEqual(by["stage4p:conv_base_sram"]["npu_active"], 10355.5)
        self.assertEqual(by["e2ed:B3w"]["ext_rd_bytes"], 40 * 16)
        self.assertEqual(by["e2eb:B0:L1000"]["npu_active"], 159122.5)
        self.assertEqual(by["e2d:W1-P1"]["npu_active"], 99233.5)
        self.assertEqual(len(by), len(rows))                              # keys unique

    def test_pairs_resolve(self):
        cmp = C.compare(C.integrate())
        self.assertEqual([c["pair"] for c in cmp if c.get("missing")], [])
        pl = next(c for c in cmp if c["pair"] == "4p placement DDR->SRAM")
        self.assertIn("MEMORY_SERVICE_CONDITION_CHANGE", pl["tags"])
        self.assertEqual(len(cmp), len(C.PAIRS))
        e = next(c for c in cmp if c["pair"] == "e2ed weight placement L500")
        self.assertIn("MEMORY_SERVICE_CONDITION_CHANGE", e["tags"])

    def test_run_writes(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "facts.json"
            f.write_text("[]")
            s = C.run(d, str(f))
            self.assertEqual(s["selected"], [])
            for n in ("integrated.csv", "comparisons.csv", "vela_fidelity.csv", "unit_inventory.md", "selection.json"):
                self.assertTrue((pathlib.Path(d) / n).exists(), n)


if __name__ == "__main__":
    unittest.main()
