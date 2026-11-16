"""stage6m.py (evidence/stage6m/contract.md): mapping, computability, categories A/B/C/D, H1-UC factors, model metrics,
bound, excess share, verdict and the P level, on synthetic facts. Expected values typed here (hand-computed)."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6m as M  # noqa: E402

DOM = dict(n=6, cin=(100, 200), hw=(29, 37), cout=(96, 176), ublock={(2, 2, 32), (2, 4, 16)}, ifm_depth={64},
           memory={("Dram", "Dram")}, stride={"1x1"}, kernel={"1x1"}, traversal={"DepthFirst"})


def row(idx, cin, h, w, cout, ub="2x2x32", mem=("Sram", "Sram"), npu_op="Conv2D", kernel="1x1", trav="DepthFirst",
        offsets="100", sid=None, name=None, act="RELU6", cycles="10", mac=None, cpu="0", op="CONV_2D"):
    return dict(model="m", tflite_op_index=str(idx), tflite_op=op, npu_op=npu_op, cpu=cpu, vela_npu_cycles=cycles,
                mac_count=str(h * w * cout * cin if mac is None else mac), name=name or f"t{idx}",
                scheduled_id=sid or str(100 + idx), kernel=kernel, stride="1x1", traversal=trav, cin=str(cin),
                cout=str(cout), npu_ofm_hwc=f"{h}x{w}x{cout}", ifm_block="8x8x64", ofm_block="8x8x96", ofm_ublock=ub,
                ifm_memory=mem[0], ofm_memory=mem[1], cascade="0", tflite_activation=act, vela_mac_cycles="100",
                vela_op_cycles="120", cms_offsets=offsets, vela_sha256="abc")


def kern(off, h, w, d, cin, kind="CONV", kw=0):
    return dict(offset=off, kind=kind, ofm_height_m1=h - 1, ofm_width_m1=w - 1, ofm_depth_m1=d - 1, ifm_depth_m1=cin - 1,
                kernel_width_m1=kw, kernel_height_m1=0)


def case(cin, kernels, ub=(2, 2, 32), ofm=None):
    oh, ow = ofm or kernels[0][:2]
    return dict(cin=cin, cout=sum(k[2] for k in kernels), ofm=[oh, ow, sum(k[2] for k in kernels)], ublock=list(ub),
                ifm_block_depth=64, ofm_block="8x8x96", ifm_block="8x8x64", kernels=[list(k) for k in kernels])


class Factors(unittest.TestCase):
    def test_768_case(self):
        # 8x8, Cout 16 + 80, Cin 64: U = 16 + 48 = 64, U0 = 48, C = 8 -> H1-UC 512, ideal 384, eff 0.75
        f = M.factors(case(64, [(8, 8, 16), (8, 8, 80)]), 8 * 8 * 96 * 64)
        self.assertEqual(f["h1uc"], 512)
        self.assertEqual(f["ideal"], 384)
        self.assertAlmostEqual(f["eff"], 0.75)
        self.assertAlmostEqual(f["F_U"], 4 / 3)
        self.assertAlmostEqual(f["F_sp"], 1.0)
        self.assertAlmostEqual(f["F_cout"], 4 / 3)
        self.assertAlmostEqual(f["F_cin"], 1.0)
        self.assertTrue(f["factor_check"])
        self.assertEqual(f["h1uc_no_cout_pad"], 384)

    def test_spatial_and_cin(self):
        # 7x7x96, Cin 72 (64 + 8): U = 4*4*3 = 48, U0 = 36.75, C = 8 + 4 = 12, C0 = 9 -> 576
        f = M.factors(case(72, [(7, 7, 96)]), 7 * 7 * 96 * 72)
        self.assertEqual(f["h1uc"], 576)
        self.assertAlmostEqual(f["ideal"], 330.75)
        self.assertAlmostEqual(f["F_sp"], 48 / 36.75)
        self.assertAlmostEqual(f["F_cout"], 1.0)
        self.assertAlmostEqual(f["F_cin"], 12 / 9)
        self.assertAlmostEqual(f["interaction"], 1.0)
        self.assertEqual(f["h1uc_no_spatial"], 441)
        self.assertEqual(f["h1uc_no_cin_pad"], 432)
        self.assertAlmostEqual(f["loss"], 576 - 330.75)


class Computable(unittest.TestCase):
    def test_ok_and_reasons(self):
        r = row(0, 64, 8, 8, 96)
        ks = [kern(100, 8, 8, 16, 64), kern(200, 8, 8, 80, 64)]
        n = 8 * 8 * 96 * 64
        self.assertEqual(M.computable(r, ks, n, True), [])
        self.assertIn("model integrity", M.computable(r, ks, n, False))
        self.assertIn("kernel missing at a cms offset", M.computable(r, [None], n, True))
        self.assertIn("kernel not CONV 1x1", M.computable(r, [kern(100, 8, 8, 96, 64, kind="DEPTHWISE")], n, True))
        self.assertIn("kernel not CONV 1x1", M.computable(r, [kern(100, 8, 8, 96, 64, kw=2)], n, True))
        self.assertIn("kernel IFM depth != Cin", M.computable(r, [kern(100, 8, 8, 96, 32)], n, True))
        self.assertIn("kernels do not cover the OFM", M.computable(r, [kern(100, 8, 8, 80, 64)], n, True))
        self.assertIn("TFLite N_MAC != OFM x Cin", M.computable(r, [kern(100, 8, 8, 96, 64)], n + 1, True))
        r2 = row(0, 64, 8, 8, 96, ub="1x2x32")
        self.assertIn("ublock volume != 128", M.computable(r2, [kern(100, 8, 8, 96, 64)], n, True))


class Categories(unittest.TestCase):
    def meas(self, r, ks, group="G99"):
        c = M.case_of(r, ks)
        return dict(sig=M.E1R.exec_sig(c), memory=(r["ifm_memory"], r["ofm_memory"]), stride=r["stride"],
                    activation=r["tflite_activation"], group=group)

    def test_a_needs_every_term(self):
        r = row(0, 140, 25, 5, 140)
        ks = [kern(100, 25, 5, 140, 140)]
        meas = {"VALID": [self.meas(r, ks, "G25")]}
        c = M.case_of(r, ks)
        self.assertEqual(M.classify(c, r, False, meas, DOM)[:2], (M.A, "G25"))
        self.assertNotEqual(M.classify(c, r, True, meas, DOM)[0], M.A)                       # LUT fused
        r_dram = dict(r, ofm_memory="Dram")
        self.assertNotEqual(M.classify(M.case_of(r_dram, ks), r_dram, False, meas, DOM)[0], M.A)
        r_act = dict(r, tflite_activation="NONE")
        self.assertNotEqual(M.classify(M.case_of(r_act, ks), r_act, False, meas, DOM)[0], M.A)
        r_st = dict(r, stride="2x2")
        self.assertNotEqual(M.classify(M.case_of(r_st, ks), r_st, False, meas, DOM)[0], M.A)
        self.assertEqual(M.classify(c, r, False, {"UNSTABLE": [self.meas(r, ks, "G53")]}, DOM)[3], "G53")
        self.assertEqual(M.classify(c, r, False, {"UNSTABLE": [self.meas(r, ks, "G53")]}, DOM)[0], M.C)

    def test_same_cin_cout_is_not_same_config(self):
        r = row(0, 140, 25, 5, 140)
        meas = {"VALID": [self.meas(r, [kern(100, 25, 5, 140, 140)], "G25")]}
        split = [kern(100, 25, 5, 16, 140), kern(200, 25, 5, 124, 140)]                    # same Cin/Cout, other kernels
        self.assertNotEqual(M.classify(M.case_of(r, split), r, False, meas, DOM)[0], M.A)

    def test_b_box(self):
        r = row(0, 136, 33, 33, 96, mem=("Dram", "Dram"))
        ks = [kern(100, 33, 33, 16, 136), kern(200, 33, 33, 80, 136)]
        c = M.case_of(r, ks)
        self.assertEqual(M.classify(c, r, False, {}, DOM)[0], M.B)
        bad = dict(cin=row(0, 96, 33, 33, 96, mem=("Dram", "Dram")), ofm_h=row(0, 136, 28, 33, 96, mem=("Dram", "Dram")),
                   ofm_w=row(0, 136, 33, 38, 96, mem=("Dram", "Dram")), cout=row(0, 136, 33, 33, 64, mem=("Dram", "Dram")),
                   ublock=row(0, 136, 33, 33, 96, ub="1x4x32", mem=("Dram", "Dram")), memory=row(0, 136, 33, 33, 96),
                   traversal=row(0, 136, 33, 33, 96, trav="PartKernel", mem=("Dram", "Dram")))
        for dim, rr in bad.items():
            with self.subTest(dim):
                oh, ow, co = M.hwc(rr["npu_ofm_hwc"])
                cc = M.case_of(rr, [kern(100, oh, ow, co, int(rr["cin"]))])
                cat, _, fails, _ = M.classify(cc, rr, False, {}, DOM)
                self.assertEqual(cat, M.C)
                self.assertIn(dim, fails)
        self.assertIn("no_lut", M.classify(c, r, True, {}, DOM)[2])
        stripe = M.case_of(r, [kern(100, 17, 33, 96, 136), kern(200, 16, 33, 96, 136)])
        self.assertIn("full_spatial", M.classify(stripe, r, False, {}, DOM)[2])
        self.assertFalse(M.domain_flags(dict(c, ifm_block_depth=32), r, False, DOM)["ifm_depth"])
        self.assertFalse(M.domain_flags(c, dict(r, stride="2x2"), False, DOM)["stride"])
        self.assertFalse(M.domain_flags(c, dict(r, kernel="3x3"), False, DOM)["kernel"])

    def test_e1r_domain_from_files(self):
        d = M.e1r_domain()
        self.assertEqual((d["n"], d["cin"], d["hw"], d["cout"]), (6, (100, 200), (29, 37), (96, 176)))
        self.assertEqual(d["ublock"], {(2, 2, 32), (2, 4, 16)})
        self.assertEqual((d["ifm_depth"], d["memory"], d["stride"]), ({64}, {("Dram", "Dram")}, {"1x1"}))
        self.assertEqual((d["kernel"], d["traversal"]), ({"1x1"}, {"DepthFirst"}))

    def test_domain_only_valid_matching_shapes(self):
        def shape(cin, hw, cout, ub, mem="Dram"):
            n = f"e1r_c{cin}_h{hw}w{hw}_o{cout}"
            p = {n: dict(ublock=list(ub), ifm_block="2x38x64")}
            b = {n: dict(rows=[dict(npu_op="Conv2D", ifm_memory=mem, ofm_memory=mem, stride="1x1", kernel="1x1",
                                    traversal="DepthFirst")])}
            return n, p, b
        n1, p1, b1 = shape(100, 30, 96, (2, 2, 32))
        n2, p2, b2 = shape(300, 50, 512, (1, 4, 32), mem="Sram")
        n3, p3, b3 = shape(120, 31, 100, (2, 4, 16))
        shapes = [dict(config=n1, cls="PRIMARY_VALID", h1_uc_match=True), dict(config=n2, cls="MAC_ONLY_DIAGNOSTIC", h1_uc_match=True),
                  dict(config=n3, cls="PRIMARY_VALID", h1_uc_match=False)]
        d = M.domain_of({**p1, **p2, **p3}, {**b1, **b2, **b3}, shapes)
        self.assertEqual((d["n"], d["cin"], d["hw"], d["cout"]), (1, (100, 100), (30, 30), (96, 96)))
        self.assertEqual((d["ublock"], d["memory"]), ({(2, 2, 32)}, {("Dram", "Dram")}))

    def test_measured_groups_from_files(self):
        m = M.measured_configs()
        self.assertEqual(sorted(x["group"] for x in m["VALID"]), ["G09", "G11", "G12", "G25", "G40", "G52", "G57"])
        self.assertEqual(sorted(x["group"] for x in m["UNSTABLE"]), ["G28", "G53", "G56"])


class Operators(unittest.TestCase):
    def setUp(self):
        self.rows = [row(0, 64, 8, 8, 96, offsets="100 200", name="c0"),
                     dict(row(1, 64, 8, 8, 96, npu_op="LUT", cycles="0", mac=0, name="c0", op="LEAKY_RELU")),
                     row(2, 32, 8, 8, 32, npu_op="Depthwise", kernel="3x3", offsets="300"),
                     row(3, 64, 4, 4, 64, offsets="400", sid="7"), row(3, 64, 4, 4, 64, offsets="500", sid="8"),
                     row(4, 1, 1, 1, 1, cpu="1", npu_op="FullyConnected"),
                     row(2, 32, 8, 8, 32, npu_op="LUT", cycles="0", mac=0, name="other", op="LOGISTIC")]
        self.meta = dict(ops=[dict(op="CONV_2D", n_mac=8 * 8 * 96 * 64), dict(op="LEAKY_RELU", n_mac=None),
                              dict(op="DEPTHWISE_CONV_2D", n_mac=8 * 8 * 32 * 9), dict(op="CONV_2D", n_mac=4 * 4 * 64 * 64),
                              dict(op="FULLY_CONNECTED", n_mac=10)])
        self.dt = {"m": {"ops": {str(i): {"outputs": ["INT8"]} for i in range(5)}}}
        self.kf = dict(n_ethosu_ops=1, kernels=[[kern(100, 8, 8, 16, 64), kern(200, 8, 8, 80, 64)]])

    def ops(self, kf=None, ok=True):
        return M.operators("m", self.rows, self.meta, self.dt, self.kf if kf is None else kf, ok, {}, DOM)

    def test_rows(self):
        o = self.ops()
        self.assertEqual(len(o), 5)                                                         # one row per TFLite op
        self.assertEqual([x["exec_on"] for x in o], ["NPU", "CPU_OR_REMOVED", "NPU", "AMBIGUOUS_SPLIT", "CPU_OR_REMOVED"])
        c0 = o[0]
        self.assertTrue(c0["is_target"])
        self.assertTrue(c0["lut_fused"])
        self.assertEqual(c0["fused_ops"], "LEAKY_RELU")
        self.assertEqual(c0["n_kernels"], 2)
        self.assertEqual(c0["h1uc"], 512)                                                   # two kernels, N_MAC once
        self.assertEqual(c0["n_mac_tflite"], 393216)
        self.assertEqual(c0["category"], M.C)
        self.assertEqual(o[2]["category"], M.D)
        self.assertFalse(o[2]["is_target"])
        self.assertEqual(o[3]["category"], M.D)
        self.assertFalse(o[3]["is_target"])                                                 # ambiguous split: no target

    def test_multi_stream_not_computable(self):
        o = self.ops(kf=dict(n_ethosu_ops=2, kernels=self.kf["kernels"] * 2))
        self.assertEqual(o[0]["category"], M.D)
        self.assertIn("kernel missing", o[0]["reason"])
        self.assertIn("model integrity", self.ops(ok=False)[0]["reason"])


def op(n, cat="", h1=None, target=True, sched=1):
    o = dict(n_mac_tflite=n, n_sched=sched, is_target=target, category=cat or M.D)
    if h1 is not None:
        o.update(h1uc=h1, loss=h1 - n / 1024, h1uc_no_spatial=h1, h1uc_no_cout_pad=h1, h1uc_no_cin_pad=h1)
    return o


class Metrics(unittest.TestCase):
    def test_values(self):
        ops = [op(102400, M.A, 125), op(51200, M.B, 60), op(20480, M.C, 40), op(10240, target=False),
               op(5120, target=False, sched=0), dict(n_mac_tflite=None, n_sched=1, is_target=False, category=M.D)]
        m = M.model_metrics(ops, 400.0, 1000.0)
        self.assertEqual(m["n_model"], 189440)
        self.assertEqual(m["n_npu"], 184320)                                                # CPU MAC op out
        self.assertAlmostEqual(m["coverage_A"], 102400 / 189440)
        self.assertAlmostEqual(m["coverage_AB"], 153600 / 189440)
        self.assertAlmostEqual(m["coverage_ABC"], 174080 / 189440)
        self.assertAlmostEqual(m["share_1x1df"], 174080 / 189440)
        self.assertAlmostEqual(m["eff_set_AB"], 153600 / (1024 * 185))
        self.assertAlmostEqual(m["eff_meas"], 184320 / (1024 * 400))
        # bound AB: 400 - 185 - (20480 + 10240)/1024 = 185
        self.assertAlmostEqual(m["bound_AB"], 185)
        # excess: 400 - 180 = 220; AB loss = (125 - 100) + (60 - 50) = 35
        self.assertAlmostEqual(m["excess_meas"], 220)
        self.assertAlmostEqual(m["excess_share_AB"], 35 / 220)
        self.assertAlmostEqual(m["excess_share_ABC"], 55 / 220)
        self.assertAlmostEqual(m["bound_ABC"], 400 - 225 - 10)
        self.assertEqual(m["n_ops"], {M.A: 1, M.B: 1, M.C: 1, M.D: 0})

    def test_bound_can_go_negative(self):
        m = M.model_metrics([op(102400, M.A, 300), op(102400, target=False)], 350.0, 1000.0)
        self.assertAlmostEqual(m["bound_AB"], 350 - 300 - 100)


def mm(cov_ab=0.6, eff_set=0.7, eff_meas=0.6, excess=0.2, bound=10.0, cov_abc=0.9, n_ab=1, share=0.9):
    return dict(coverage_AB=cov_ab, coverage_ABC=cov_abc, eff_set_AB=eff_set, eff_meas=eff_meas, excess_share_AB=excess,
                bound_AB=bound, n_ops={M.A: n_ab, M.B: 0, M.C: 0, M.D: 0}, share_1x1df=share)


class Verdict(unittest.TestCase):
    def go(self, kws=None, ad=None, ok=True, others=None, s6=None):
        models = {"kws_micronet_m": kws or mm(eff_set=0.6, eff_meas=0.3), "ad_medium_int8": ad or mm(eff_set=0.9, eff_meas=0.6)}
        models.update(others or {})
        integ = {m: dict(ok=ok) for m in models}
        return M.verdict(integ, models, s6 or {m: 0.0 for m in models})

    def test_partial(self):
        self.assertEqual(self.go()["verdict"], "EXPLANATORY_SUPPORT_PARTIAL")

    def test_v1(self):
        self.assertEqual(self.go(ok=False)["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_each_v_blocks_partial(self):
        cases = dict(V2=dict(others={"x": mm(bound=-1.0)}),
                     V3=dict(kws=mm(cov_ab=0.49, eff_set=0.6, eff_meas=0.3)),
                     V4=dict(kws=mm(eff_set=0.95, eff_meas=0.3)),
                     V4m=dict(kws=mm(eff_set=0.6, eff_meas=0.7)),
                     V5=dict(kws=mm(eff_set=0.6, eff_meas=0.3, excess=0.09), ad=mm(eff_set=0.9, eff_meas=0.6, excess=0.05)))
        for k, kw in cases.items():
            with self.subTest(k):
                v = self.go(**kw)
                self.assertEqual(v["verdict"], "COVERAGE_EXPANDED_NOT_EXPLAINED")
                self.assertIn(k[:2], v["failed"])

    def test_v5_one_of_pair_enough(self):
        self.assertEqual(self.go(kws=mm(eff_set=0.6, eff_meas=0.3, excess=0.0))["verdict"], "EXPLANATORY_SUPPORT_PARTIAL")

    def test_bound_ignored_without_ab(self):
        v = self.go(others={"x": mm(bound=-1.0, n_ab=0)})
        self.assertEqual(v["verdict"], "EXPLANATORY_SUPPORT_PARTIAL")

    def test_not_expanded(self):
        v = self.go(kws=mm(cov_ab=0.1, eff_set=0.6, eff_meas=0.3, cov_abc=0.5), ad=mm(eff_set=0.9, eff_meas=0.6, cov_abc=0.5),
                    s6={"kws_micronet_m": 0.5, "ad_medium_int8": 0.6})
        self.assertEqual(v["verdict"], "INSUFFICIENT_EVIDENCE")


class PLevel(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(M.p_level("ao", mm()), "NOT_APPLICABLE_TO_H1UC")
        self.assertEqual(M.p_level("mac", mm(share=0.0)), "NOT_APPLICABLE_TO_H1UC")
        self.assertEqual(M.p_level("mac+wd", mm()), "PARTIAL_MAC_COST")
        self.assertEqual(M.p_level("mac", mm(bound=-1.0)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(M.p_level("mac", mm(cov_ab=0.4)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(M.p_level("mac", mm(excess=0.09)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(M.p_level("mac", mm(excess=None)), "INSUFFICIENT_EVIDENCE")


class Integrity(unittest.TestCase):
    def test_terms(self):
        f = {"m": dict(vela_sha256="v", cms_sha256=["c"], model_sha256="s")}
        m7 = dict(vela_sha256="v" * 16 + "x", cms_sha256="c", model_sha256="s")
        f["m"]["vela_sha256"] = m7["vela_sha256"]
        self.assertTrue(M.integrity("m", f, m7, dict(model_sha256="s"), {"v" * 16})["ok"])
        self.assertFalse(M.integrity("m", f, m7, dict(model_sha256="t"), {"v" * 16})["ok"])
        self.assertFalse(M.integrity("m", f, m7, dict(model_sha256="s"), {"w" * 16})["ok"])
        self.assertFalse(M.integrity("m", f, dict(m7, cms_sha256="d"), dict(model_sha256="s"), {"v" * 16})["ok"])
        self.assertFalse(M.integrity("m", f, dict(m7, vela_sha256="z"), dict(model_sha256="s"), {"z"})["ok"])
        self.assertFalse(M.integrity("x", f, m7, dict(model_sha256="s"), {"v" * 16})["ok"])


if __name__ == "__main__":
    unittest.main()
