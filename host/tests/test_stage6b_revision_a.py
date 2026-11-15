"""stage6b_revision_a.py: per-form checks, EXACT_A (the unchanged Stage 6B definition), BOARD_ELIGIBLE, form preference,
selection on BOARD_ELIGIBLE, coverage values and the verdict of evidence/stage6b/revision_a/revision_a_contract.md, on
synthetic records. Expected values typed here."""
import copy, pathlib, sys, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6b_revision_a as R


def row(**kw):
    r = dict(model="kws_micronet_m", scheduled_id="10", tflite_op_index="0", cpu="0", npu_op="Conv2D", kernel="1x1",
             stride="1x1", padding="t0b0l0r0", npu_ifm_hwc="8x8x64", npu_ofm_hwc="8x8x96", ifm_block="8x8x64",
             ofm_block="8x8x96", ofm_ublock="2x2x32", traversal="DepthFirst", ifm_memory="Sram", ofm_memory="Sram",
             ifm_format="NHCWB16", ofm_format="NHCWB16", cascade="0", tflite_activation="RELU6", mac_count="393216",
             weight_bytes="7000", staging_usage="9000", cin="64", cout="96", fused_names="1", name="conv_out")
    r.update(kw)
    return r


T = lambda sha=None, scale=(0.5,), zp=(-3,): dict(shape=[1, 8, 8, 64], type=9, scale=list(scale), zp=list(zp), qdim=0, sha256=sha)
TENSORS = dict(ifm=T(), w=T("w1", (0.1, 0.2)), b=T("b1", (0.05, 0.1), (0, 0)), ofm=T(scale=(0.7,), zp=(5,)))
KERN = dict(ifm_depth_m1=63, ifm_precision=1, ofm_width_m1=7, ofm_height_m1=7, ofm_depth_m1=95, ofm_precision=1,
            blk_width_m1=7, blk_height_m1=7, blk_depth_m1=95, acc_format=0, ifm_width0_m1=7, ifm_height0_m1=7,
            kernel_width_m1=0, kernel_height_m1=0, kernel_stride=0, ifm_stride_x=16, ifm_stride_y=128, ifm_stride_c=1024,
            ofm_stride_x=16, ofm_stride_y=128, ofm_stride_c=1024, weight_length=7000, weight1_length=0, weight2_length=0,
            weight3_length=0, ifm_region=2, ofm_region=2, weight_region=0, ifm_base0=0, ofm_base0=4096, dma_len=7000,
            dma_before=[7000], offset=100, kind="CONV")
MAN = dict(group="G01", tensors=TENSORS, inventory_vela_sha256="abcd")
ORIG = dict(vela_sha256="abcd" + "0" * 60, n_ethosu_ops=1, conv_kernels=[dict(KERN)])


def form(label="A2", **kw):
    r = row(name=R.CONV_OUT_NAME[label])
    f = dict(conv_row=r, feasible=dict(single_conv=True, no_cpu=True, packed=True, reference=True, fast_size=True,
                                       arena_size=True, model_region=True),
             npu_ops=list(R.EXPECTED_OPS[label]), cpu_rows=[], graph_conv=copy.deepcopy(TENSORS),
             reference=dict(n=6144, ref_sha256="r"), golden_sha256="r",
             refcheck=dict(final_sha256_equals_ref=True, numpy_vs_ref_max_abs=1, conv_out_informative=0.9,
                           final_informative=0.9, final_vs_conv_out_max_abs=1),
             model_sha256="m", vela_sha256="v", drwl_sha256="d", manifest_sha256="j", cms_sha256="c",
             conv_kernels=[dict(KERN, ifm_base0=64, ofm_base0=8192, dma_before=[], dma_len=3)],
             ta_profile=1, placement=0, n_base=5)
    f["second"] = {k: copy.deepcopy(f[k]) for k in ("model_sha256", "vela_sha256", "drwl_sha256", "manifest_sha256",
                                                    "cms_sha256", "conv_row", "conv_kernels")}
    f.update(kw)
    return f


def rec(**forms):
    return dict(original=copy.deepcopy(ORIG), forms={f: forms.get(f, form(f)) for f in R.FORMS})


def jf(label="A2", rep=None, man=MAN, r=None, **kw):
    r = r or dict(original=copy.deepcopy(ORIG), forms={label: form(label, **kw)})
    return R.judge_form(label, rep or row(), man, r)


class Checks(unittest.TestCase):
    def test_good_form_is_eligible(self):
        j = jf()
        self.assertEqual(j["cls"], "EXACT_A")
        self.assertEqual({k: c["status"] for k, c in j["checks"].items()}, {k: "PASS" for k in R.CHECKS})
        self.assertTrue(j["board_eligible"])

    def test_exact_a_is_the_stage6b_definition(self):
        self.assertEqual(jf(conv_row=row(ofm_memory="Dram"))["cls"], "PARTIAL_A")
        self.assertEqual(jf(conv_row=row(staging_usage="1"))["cls"], "PARTIAL_A")
        self.assertEqual(jf(conv_row=row(mac_count="1"))["cls"], "NOT_REPRODUCIBLE_A")
        self.assertFalse(jf(conv_row=row(ofm_memory="Dram"))["board_eligible"])

    def test_params(self):
        g = copy.deepcopy(TENSORS); g["w"]["sha256"] = "w2"
        self.assertEqual(jf(graph_conv=g)["checks"]["params"]["status"], "FAIL")
        g = copy.deepcopy(TENSORS); g["ofm"]["scale"] = [1.4]
        self.assertEqual(jf(graph_conv=g)["checks"]["params"]["diffs"], {"ofm": ["scale"]})
        g = copy.deepcopy(TENSORS); g["b"]["zp"] = [1, 0]
        self.assertFalse(jf(graph_conv=g)["board_eligible"])
        g = copy.deepcopy(TENSORS); g["ifm"]["type"] = 7
        self.assertEqual(jf(graph_conv=g)["checks"]["params"]["status"], "FAIL")

    def test_reference(self):
        base = form()["refcheck"]
        for k, v in (("numpy_vs_ref_max_abs", 2), ("conv_out_informative", 0.09), ("final_informative", 0.05),
                     ("final_vs_conv_out_max_abs", 2), ("final_sha256_equals_ref", False)):
            j = jf(refcheck=dict(base, **{k: v}))
            self.assertEqual(j["checks"]["reference"]["status"], "FAIL", k)
            self.assertFalse(j["board_eligible"], k)
        self.assertEqual(jf(refcheck=dict(base, conv_out_informative=0.10))["checks"]["reference"]["status"], "PASS")
        self.assertEqual(jf(golden_sha256="other")["checks"]["reference"]["status"], "FAIL")
        # the self-ADD identity applies to A2 only: A1's final output is ADD(conv_out, c)
        self.assertEqual(jf("A1", refcheck=dict(base, final_vs_conv_out_max_abs=128))["checks"]["reference"]["status"], "PASS")

    def test_repeat(self):
        for k in ("model_sha256", "vela_sha256", "drwl_sha256", "manifest_sha256", "cms_sha256"):
            f = form(); f["second"][k] = "x"
            self.assertEqual(jf(r=dict(original=ORIG, forms=dict(A2=f)))["checks"]["repeat"]["diffs"], [k])
        f = form(); f["second"]["conv_row"] = row(ofm_block="4x8x96")
        j = jf(r=dict(original=ORIG, forms=dict(A2=f)))
        self.assertEqual(j["checks"]["repeat"]["status"], "FAIL")
        self.assertEqual(j["second_cls"], "PARTIAL_A")
        f = form(); f["second"]["conv_kernels"] = [dict(KERN, weight_length=1)]
        self.assertFalse(jf(r=dict(original=ORIG, forms=dict(A2=f)))["board_eligible"])

    def test_fusion(self):
        self.assertEqual(jf(npu_ops=["Conv2D", "Add"])["checks"]["fusion"]["status"], "FAIL")
        self.assertEqual(jf(npu_ops=["Add", "Conv2D"])["checks"]["fusion"]["status"], "FAIL")       # wrapper removed
        self.assertEqual(jf(cpu_rows=["ADD"])["checks"]["fusion"]["status"], "FAIL")
        f = form(); f["conv_row"] = row(fused_names="2"); f["second"]["conv_row"] = f["conv_row"]
        self.assertEqual(jf(r=dict(original=ORIG, forms=dict(A2=f)))["checks"]["fusion"]["status"], "FAIL")
        f = form(); f["conv_row"] = row(name="ofm"); f["second"]["conv_row"] = f["conv_row"]
        self.assertEqual(jf(r=dict(original=ORIG, forms=dict(A2=f)))["checks"]["fusion"]["status"], "FAIL")
        self.assertEqual(jf("A0")["checks"]["fusion"]["status"], "PASS")

    def test_registers(self):
        ks = lambda **kw: [dict(KERN, **kw)]
        f = lambda **kw: dict(conv_kernels=ks(**kw), second=dict(form()["second"], conv_kernels=ks(**kw)))
        self.assertEqual(jf(**f(weight_length=6000))["checks"]["registers"]["diffs"], ["weight_length"])
        self.assertEqual(jf(**f(blk_depth_m1=63))["checks"]["registers"]["status"], "FAIL")
        self.assertEqual(jf(**f(ofm_region=1))["checks"]["registers"]["diffs"], ["ofm_region"])
        self.assertEqual(jf(**f(ifm_stride_y=256))["checks"]["registers"]["status"], "FAIL")
        # addresses and DMA prefetch context are not compared
        self.assertEqual(jf(**f(ifm_base0=1, ofm_base0=2, dma_before=[1, 2], dma_len=9))["checks"]["registers"]["status"],
                         "PASS")
        two = [dict(KERN), dict(KERN)]
        self.assertTrue(jf(conv_kernels=two, second=dict(form()["second"], conv_kernels=two))["checks"]["registers"]
                        ["diffs"][0].startswith("n_kernels"))

    def test_registers_not_verified_blocks(self):
        r = rec(); r["original"]["vela_sha256"] = "ffff" + "0" * 60
        j = R.judge_form("A2", row(), MAN, r)
        self.assertEqual(j["checks"]["registers"]["status"], "NOT_VERIFIED")
        self.assertFalse(j["board_eligible"])
        r = rec(); r["original"]["conv_kernels"] = [None]
        self.assertEqual(R.judge_form("A2", row(), MAN, r)["checks"]["registers"]["status"], "NOT_VERIFIED")
        r = rec(); r["original"]["n_ethosu_ops"] = 2
        self.assertEqual(R.judge_form("A2", row(), MAN, r)["checks"]["registers"]["status"], "NOT_VERIFIED")

    def test_package(self):
        self.assertEqual(jf(ta_profile=2)["checks"]["package"]["status"], "FAIL")
        self.assertEqual(jf(placement=1)["checks"]["package"]["status"], "FAIL")
        self.assertEqual(jf(n_base=9)["checks"]["package"]["status"], "FAIL")
        self.assertEqual(jf(n_base=8)["checks"]["package"]["status"], "PASS")
        f = form(); f["feasible"]["arena_size"] = False
        j = jf(r=dict(original=ORIG, forms=dict(A2=f)))
        self.assertEqual(j["checks"]["package"]["diffs"], ["arena_size"])
        self.assertFalse(j["board_eligible"])

    def test_missing_form(self):
        j = R.judge_form("A2", row(), MAN, dict(original=ORIG, forms={}))
        self.assertEqual(j["cls"], "NOT_REPRODUCIBLE_A")
        self.assertFalse(j["board_eligible"])


class Candidate(unittest.TestCase):
    def test_form_preference(self):
        c = R.judge_candidate(row(), MAN, rec())
        self.assertEqual((c["form"], c["board_form"]), ("A0", "A0"))
        a0 = form("A0", conv_row=row(name="ofm", ofm_memory="Dram"))
        a0["second"]["conv_row"] = a0["conv_row"]
        c = R.judge_candidate(row(), MAN, rec(A0=a0))
        self.assertEqual((c["cls"], c["form"], c["board_form"]), ("EXACT_A", "A1", "A1"))
        a1 = form("A1", ta_profile=2)                                 # EXACT_A but not eligible
        c = R.judge_candidate(row(), MAN, rec(A0=a0, A1=a1))
        self.assertEqual((c["form"], c["board_form"]), ("A1", "A2"))

    def test_none_eligible(self):
        bad = {f: form(f, placement=1) for f in R.FORMS}
        c = R.judge_candidate(row(), MAN, rec(**bad))
        self.assertEqual((c["cls"], c["board_eligible"], c["board_form"]), ("EXACT_A", False, None))


def g(name, macs, model="kws_micronet_m", sid="1", cin=64):
    return dict(group=name, macs=macs, rep=dict(model=model, scheduled_id=sid), key=dict(npu_ifm_hwc=f"8x8x{cin}"))


class Selection(unittest.TestCase):
    def test_board_eligible_only(self):
        tot = {"kws_micronet_m": 1000}
        cands = [g("A", {"kws_micronet_m": 500}), g("B", {"kws_micronet_m": 400})]
        judged = dict(A=dict(cls="EXACT_A", board_eligible=False), B=dict(cls="EXACT_A", board_eligible=True))
        self.assertEqual([s["group"] for s in R.select(cands, judged, tot)], ["B"])


def grp(name, rows):
    return dict(group=name, members=rows, macs={})


class Coverage(unittest.TestCase):
    def test_values_and_status(self):
        r1 = row(scheduled_id="1", mac_count="300")
        r2 = row(scheduled_id="2", mac_count="200")
        r3 = row(model="ad_medium_int8", scheduled_id="5", mac_count="50")
        gs = [grp("G1", [r1]), grp("G2", [r2]), grp("G3", [r3])]
        judged = dict(G1=dict(cls="EXACT_A", board_eligible=True), G2=dict(cls="EXACT_A", board_eligible=False),
                      G3=dict(cls="PARTIAL_A", board_eligible=False))
        tot = {"kws_micronet_m": 1000, "ad_medium_int8": 100, "rnnoise_INT8": 10}
        cov = R.coverage([r1, r2, r3], [r1, r2, r3], gs, gs, judged, [dict(group="G1")], tot,
                         {"kws_micronet_m": 0.1, "ad_medium_int8": 0.2}, {("kws_micronet_m", "9")})
        k = next(c for c in cov if c["model"] == "kws_micronet_m")
        self.assertEqual((k["n_mac_model"], k["n_mac_depthfirst_1x1"], k["n_mac_candidates"], k["n_mac_exact_a"],
                          k["n_mac_board_eligible"], k["n_mac_selected"]), (1000, 500, 500, 500, 300, 300))
        self.assertAlmostEqual(k["static_reproduction_coverage"], 0.5)
        self.assertAlmostEqual(k["selected_measurement_coverage"], 0.3)
        self.assertAlmostEqual(k["validated_hw_coverage"], 0.1)                  # unchanged by a static stage
        self.assertAlmostEqual(k["projected_after_board_upper_bound"], 0.4)
        self.assertEqual(k["status"], "ELIGIBLE")
        a = next(c for c in cov if c["model"] == "ad_medium_int8")
        self.assertEqual((a["status"], a["n_mac_exact_a"], a["n_mac_selected"]), ("NO_ELIGIBLE", 0, 0))
        self.assertEqual(next(c for c in cov if c["model"] == "rnnoise_INT8")["status"], "NOT_APPLICABLE")

    def test_calibrated_not_recounted(self):
        r1 = row(scheduled_id="1", mac_count="300")
        gs = [grp("G1", [r1])]
        cov = R.coverage([r1], [r1], gs, gs, dict(G1=dict(cls="EXACT_A", board_eligible=True)), [dict(group="G1")],
                         {"kws_micronet_m": 1000}, {"kws_micronet_m": 0.3}, {("kws_micronet_m", "1")})
        self.assertAlmostEqual(next(c for c in cov if c["model"] == "kws_micronet_m")["projected_after_board_upper_bound"], 0.3)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.man = dict(n=1, candidates=[dict(group="G01", model_sha256="s", tensors=TENSORS)])
        self.cands = [dict(group="G01")]
        self.rec = dict(source=dict(model_sha256="s", tensors=copy.deepcopy(TENSORS)),
                        forms={f: form(f, drwl_sha256=f"d{f}") for f in R.FORMS})
        self.s6b = dict(G01=dict(forms=dict(F_PLAIN=dict(drwl_sha256="dA0"), F_CTX=dict(drwl_sha256="dA1"))))

    def test_clean(self):
        self.assertEqual(R.provenance(self.man, self.cands, dict(G01=self.rec), self.s6b), [])

    def test_errors(self):
        self.assertTrue(R.provenance(self.man, self.cands, {}, self.s6b))
        self.assertTrue(R.provenance(self.man, [dict(group="G01"), dict(group="G02")], dict(G01=self.rec), self.s6b))
        r = copy.deepcopy(self.rec); r["source"]["model_sha256"] = "t"
        self.assertTrue(R.provenance(self.man, self.cands, dict(G01=r), self.s6b))
        r = copy.deepcopy(self.rec); r["source"]["tensors"]["w"]["sha256"] = "x"
        self.assertTrue(R.provenance(self.man, self.cands, dict(G01=r), self.s6b))
        r = copy.deepcopy(self.rec); r["forms"]["A1"]["drwl_sha256"] = "new"
        self.assertEqual(R.provenance(self.man, self.cands, dict(G01=r), self.s6b), ["G01: A1 bytes differ from Stage 6B F_CTX"])
        r = copy.deepcopy(self.rec); del r["forms"]["A2"]
        self.assertTrue(R.provenance(self.man, self.cands, dict(G01=r), self.s6b))


class Verdict(unittest.TestCase):
    J = dict(G14=dict(board_eligible=True), G09=dict(board_eligible=True))
    SEL = [dict(group="G09"), dict(group="G14")]

    def test_ready(self):
        v = R.verdict([], self.J, self.SEL, self.SEL, True)
        self.assertEqual((v["verdict"], v["new_board_eligible"]), ("READY_FOR_BOARD_REVIEW", ["G09"]))

    def test_needs_revision(self):
        self.assertEqual(R.verdict([], dict(G14=dict(board_eligible=True)), [dict(group="G14")], [dict(group="G14")],
                                   True)["verdict"], "NEEDS_REVISION")
        self.assertEqual(R.verdict([], self.J, self.SEL, self.SEL[:1], True)["verdict"], "NEEDS_REVISION")
        self.assertEqual(R.verdict([], self.J, self.SEL, self.SEL, False)["verdict"], "NEEDS_REVISION")

    def test_invalid(self):
        self.assertEqual(R.verdict(["x"], self.J, self.SEL, self.SEL, True)["verdict"], "INVALID")

    def test_second_compile_selection(self):
        judged = dict(A=dict(forms={f: dict(board_eligible=f == "A2", second_cls="PARTIAL_A") for f in R.FORMS}))
        self.assertEqual(R.second_judged(judged), dict(A=dict(board_eligible=False)))
        judged["A"]["forms"]["A2"]["second_cls"] = "EXACT_A"
        self.assertEqual(R.second_judged(judged), dict(A=dict(board_eligible=True)))


if __name__ == "__main__":
    unittest.main()
