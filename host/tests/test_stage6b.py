"""stage6b.py: target filter, execution groups, per-model top-5 candidates, static match classes, the selection rule and
the coverage opportunity of evidence/stage6b/rules.md, on synthetic rows and on the archived Stage 6 inventory.
Expected values typed here."""
import pathlib, sys, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6b as S


def row(**kw):
    r = dict(model="kws_micronet_m", scheduled_id="10", tflite_op_index="0", cpu="0", npu_op="Conv2D", kernel="1x1",
             stride="1x1", padding="t0b0l0r0", npu_ifm_hwc="8x8x64", npu_ofm_hwc="8x8x96", ifm_block="8x8x64",
             ofm_block="8x8x96", ofm_ublock="2x2x32", traversal="DepthFirst", ifm_memory="Sram", ofm_memory="Sram",
             ifm_format="NHCWB16", ofm_format="NHCWB16", cascade="0", tflite_activation="RELU6", mac_count="393216",
             weight_bytes="7000", staging_usage="9000", cin="64", cout="96")
    r.update(kw)
    return r


DT = {"kws_micronet_m": {"ops": {"0": {"outputs": ["INT8"]}, "1": {"outputs": ["INT16"]}}},
      "ad_medium_int8": {"ops": {"0": {"outputs": ["INT8"]}}}}


def form(**kw):
    conv = {k: v for k, v in row().items()}
    conv.update(kw)
    return dict(conv_row=conv, feasible=dict(single_conv=True, packed=True, repeat_identical=True))


class Targets(unittest.TestCase):
    def test_filter(self):
        rs = [row(), row(traversal="PartKernel"), row(kernel="3x3"), row(cpu="1"), row(mac_count="0"),
              row(tflite_op_index="1"), row(npu_op="DepthwiseConv2D")]
        self.assertEqual(len(S.targets(rs, DT)), 1)

    def test_groups_and_rep(self):
        rs = [row(scheduled_id="10", mac_count="100", weight_bytes="7000"),
              row(scheduled_id="20", mac_count="300", weight_bytes="7100"),          # same key, larger MAC -> rep
              row(scheduled_id="30", ofm_block="4x8x96")]                           # block differs -> own group
        gs = S.groups(rs)
        self.assertEqual(len(gs), 2)
        g = next(g for g in gs if len(g["members"]) == 2)
        self.assertEqual(g["rep"]["scheduled_id"], "20")
        self.assertEqual((g["weight_bytes_min"], g["weight_bytes_max"]), (7000, 7100))
        self.assertEqual(g["macs"], {"kws_micronet_m": 400})

    def test_top5(self):
        rs = [row(scheduled_id=str(i), npu_ifm_hwc=f"8x8x{16 * (i + 1)}", mac_count=str(1000 - i)) for i in range(7)]
        cands, per = S.candidates(S.groups(rs), {"kws_micronet_m": 10000})
        self.assertEqual(len(cands), 5)
        self.assertEqual(per["rnnoise_INT8"], [])
        kept = {g["rep"]["scheduled_id"] for g in cands}
        self.assertEqual(kept, {"0", "1", "2", "3", "4"})


class Classes(unittest.TestCase):
    def test_form(self):
        rep = row()
        self.assertEqual(S.form_class(rep, form())["cls"], "EXACT_STATIC_MATCH")
        self.assertEqual(S.form_class(rep, form(ofm_block="4x8x96"))["cls"], "PARTIAL_STATIC_MATCH")
        self.assertEqual(S.form_class(rep, form(ofm_memory="Dram"))["diffs"], ["ofm_memory"])
        self.assertEqual(S.form_class(rep, form(weight_bytes="7016"))["cls"], "PARTIAL_STATIC_MATCH")
        self.assertEqual(S.form_class(rep, form(staging_usage="1"))["cls"], "PARTIAL_STATIC_MATCH")
        self.assertEqual(S.form_class(rep, form(cascade="5"))["cls"], "PARTIAL_STATIC_MATCH")
        self.assertEqual(S.form_class(rep, form(mac_count="1"))["cls"], "NOT_REPRODUCIBLE")
        self.assertEqual(S.form_class(rep, form(npu_ifm_hwc="8x8x48"))["cls"], "NOT_REPRODUCIBLE")
        bad = form(); bad["feasible"]["packed"] = False
        self.assertEqual(S.form_class(rep, bad)["cls"], "NOT_REPRODUCIBLE")
        rep2 = form(); rep2["feasible"]["repeat_identical"] = False
        self.assertEqual(S.form_class(rep, rep2)["cls"], "NOT_REPRODUCIBLE")
        self.assertEqual(S.form_class(rep, None)["cls"], "NOT_REPRODUCIBLE")
        self.assertEqual(S.form_class(rep, dict(conv_row=None, feasible={}))["cls"], "NOT_REPRODUCIBLE")

    def test_best_form(self):
        rep = row()
        c = S.classify(rep, dict(forms=dict(F_PLAIN=form(ifm_memory="Dram"), F_CTX=form())))
        self.assertEqual((c["cls"], c["form"]), ("EXACT_STATIC_MATCH", "F_CTX"))
        c = S.classify(rep, dict(forms=dict(F_PLAIN=form(), F_CTX=form())))
        self.assertEqual(c["form"], "F_PLAIN")                                    # tie -> no ADD contamination
        c = S.classify(rep, dict(forms=dict(F_PLAIN=form(ifm_memory="Dram"), F_CTX=form(mac_count="1"))))
        self.assertEqual((c["cls"], c["form"]), ("PARTIAL_STATIC_MATCH", "F_PLAIN"))


def g(name, macs, model="kws_micronet_m", sid="1", cin=64):
    return dict(group=name, macs=macs, rep=dict(model=model, scheduled_id=sid), key=dict(npu_ifm_hwc=f"8x8x{cin}"))


class Selection(unittest.TestCase):
    TOT = {"kws_micronet_m": 1000, "ad_medium_int8": 100}

    def test_floor_then_score(self):
        cands = [g("A", {"kws_micronet_m": 500}), g("B", {"kws_micronet_m": 400}), g("C", {"ad_medium_int8": 10}, "ad_medium_int8")]
        cls = {k: dict(cls="EXACT_STATIC_MATCH") for k in "ABC"}
        sel = S.select(cands, cls, self.TOT)
        self.assertEqual([s["group"] for s in sel], ["C", "A", "B"])            # ad before kws by model name
        self.assertEqual(sel[0]["reason"], "model_floor:ad_medium_int8")
        self.assertEqual(sel[2]["reason"], "score")

    def test_normalised_score(self):
        # D: 30 % of kws's MAC vs E: 40 % of ad's MAC (absolute 300 vs 40): E ranks first among score picks
        cands = [g("A", {"kws_micronet_m": 500}), g("D", {"kws_micronet_m": 300}), g("F", {"ad_medium_int8": 50}, "ad_medium_int8"),
                 g("E", {"ad_medium_int8": 40}, "ad_medium_int8")]
        sel = S.select(cands, {k: dict(cls="EXACT_STATIC_MATCH") for k in "ADEF"}, self.TOT)
        self.assertEqual([s["group"] for s in sel], ["F", "A", "E", "D"])

    def test_partial_not_eligible_and_cap(self):
        cands = [g(f"X{i:02d}", {"kws_micronet_m": 100 - i}, sid=str(i)) for i in range(12)] + [g("P", {"kws_micronet_m": 999})]
        cls = {c["group"]: dict(cls="EXACT_STATIC_MATCH") for c in cands}
        cls["P"] = dict(cls="PARTIAL_STATIC_MATCH")
        sel = S.select(cands, cls, self.TOT)
        self.assertEqual(len(sel), 10)
        self.assertNotIn("P", [s["group"] for s in sel])
        self.assertEqual(sel[0]["group"], "X00")

    def test_ties(self):
        tot = {"kws_micronet_m": 1000}
        a, b = g("A", {"kws_micronet_m": 100}, sid="5", cin=200), g("B", {"kws_micronet_m": 100}, sid="9", cin=64)
        c = g("C", {"kws_micronet_m": 900}, sid="1")
        sel = S.select([a, b, c], {k: dict(cls="EXACT_STATIC_MATCH") for k in "ABC"}, tot)
        self.assertEqual([s["group"] for s in sel], ["C", "B", "A"])            # Cin in [40, 128] wins the tie
        a2 = g("A", {"kws_micronet_m": 100}, sid="5", cin=64)
        sel = S.select([b, a2, c], {k: dict(cls="EXACT_STATIC_MATCH") for k in "ABC"}, tot)
        self.assertEqual([s["group"] for s in sel], ["C", "A", "B"])            # then scheduled_id

    def test_no_eligible(self):
        self.assertEqual(S.select([g("A", {"kws_micronet_m": 1})], {"A": dict(cls="NOT_REPRODUCIBLE")}, self.TOT), [])


class Coverage(unittest.TestCase):
    def test_upper_bound_no_double_count(self):
        r1, r2 = row(scheduled_id="1", mac_count="300"), row(scheduled_id="2", mac_count="200", ofm_block="4x8x96")
        other = row(scheduled_id="3", traversal="PartKernel", mac_count="500", kernel="3x3")
        gs = S.groups([r1, r2])
        cls = {x["group"]: dict(cls="EXACT_STATIC_MATCH" if x["rep"]["scheduled_id"] == "1" else "PARTIAL_STATIC_MATCH")
               for x in gs}
        sel = [dict(group=next(x["group"] for x in gs if x["rep"]["scheduled_id"] == "1"))]
        tot = {"kws_micronet_m": 1000}
        cov = S.coverage([r1, r2, other], [r1, r2], gs, gs, cls, sel, tot, {"kws_micronet_m": 0.1}, set())
        k = next(c for c in cov if c["model"] == "kws_micronet_m")
        self.assertAlmostEqual(k["depthfirst_1x1_share"], 0.5)
        self.assertAlmostEqual(k["candidate_exact_share"], 0.3)
        self.assertAlmostEqual(k["candidate_partial_share"], 0.2)
        self.assertAlmostEqual(k["selected_share"], 0.3)
        self.assertAlmostEqual(k["projected_upper_bound"], 0.4)
        self.assertTrue(k["remaining_top3"].startswith("Conv2D 3x3 PartKernel Cin64 50.0%"))
        cov = S.coverage([r1, r2, other], [r1, r2], gs, gs, cls, sel, tot, {"kws_micronet_m": 0.1}, {("kws_micronet_m", "1")})
        k = next(c for c in cov if c["model"] == "kws_micronet_m")
        self.assertAlmostEqual(k["projected_upper_bound"], 0.1)                  # already calibrated: not counted again


class Archived(unittest.TestCase):
    def test_inventory(self):
        import json
        rows = S.load()
        tg = S.targets(rows, json.loads(S.DTYPES.read_text()))
        self.assertEqual(len(tg), 93)
        gs = S.groups(tg)
        self.assertEqual(len(gs), 57)
        cands, per = S.candidates(gs, S.model_macs(rows))
        self.assertEqual(len(cands), 26)
        self.assertEqual(per["rnnoise_INT8"], [])
        self.assertEqual(len(per["kws_micronet_m"]), 4)
        self.assertEqual(len(per["wav2letter_pruned_int8"]), 2)
        self.assertEqual(sum(len(g["members"]) for g in gs), 93)


if __name__ == "__main__":
    unittest.main()
