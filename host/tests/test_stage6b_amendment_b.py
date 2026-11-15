"""stage6b_amendment_b.py: the B-1 fusion gate (ORIGINAL_ACTIVATION_PRESERVED / EXECUTION_CHANGED / FUSION_UNVERIFIED),
the B-2b fixture gate and the separate BOARD_ELIGIBLE_WITH_ADDITIONAL_VALIDATION field of
evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md, on synthetic records. Expected values typed here."""
import copy, pathlib, sys, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import stage6b_amendment_b as A
import test_stage6b_revision_a as T

ACT = dict(activation=1, activation_min=0, activation_max=255, ofm_zero_point=128, ofm_scale=12345)
MAN = dict(T.MAN, activation="RELU6", model="kws_micronet_m", tflite_op_index=5)
DEAD = dict(cms_offsets="", mac_count="0", vela_op_cycles="0")


def inv(act="Relu6"):
    rows = [T.row(tflite_op_index="5", cms_offsets="100", vela_op_cycles="500")]
    return rows + ([T.row(npu_op=act, tflite_op_index="5", **DEAD)] if act else [])


def frows(act="Relu6"):
    add = lambda i: T.row(npu_op="Add", tflite_op_index=str(i), cms_offsets="10", mac_count="0", vela_op_cycles="50",
                          tflite_activation="", name="x")
    conv = [T.row(tflite_op_index="1", cms_offsets="100")] + ([T.row(npu_op=act, tflite_op_index="1", **DEAD)] if act else [])
    return [add(0)] + conv + [add(2)]


def bform(act="Relu6", **kw):
    rows = frows(act)
    f = T.form("A2", rows=rows, npu_ops=[r["npu_op"] for r in rows])
    f.update(kw)
    return f


def facts(orig_act=None, form_act=None, kinds=None, sha="c"):
    return dict(original=dict(vela_sha256="abcd" + "0" * 60, n_ethosu_ops=1, conv_act=[dict(orig_act or ACT)]),
                forms=dict(A2=dict(cms_sha256=sha, kernel_types=kinds or ["ELEMENTWISE", "CONV", "ELEMENTWISE"],
                                   conv_act=[dict(form_act or ACT)])))


def rec(form=None):
    return dict(original=copy.deepcopy(T.ORIG), forms=dict(A2=form or bform()))


def gate(man=MAN, inv_rows=None, form=None, f=None):
    return A.fusion_gate("A2", man, inv() if inv_rows is None else inv_rows, rec(form), facts() if f is None else f)


class Fusion(unittest.TestCase):
    def test_original_activation_preserved_passes(self):
        g = gate()
        self.assertEqual((g["cls"], g["status"], g["diffs"]), ("ORIGINAL_ACTIVATION_PRESERVED", "PASS", []))
        j = A.judge_form("A2", T.row(), MAN, inv(), rec(), facts())
        self.assertTrue(j["board_eligible"])
        self.assertEqual(j["fusion_cls"], "ORIGINAL_ACTIVATION_PRESERVED")

    def test_original_contract_check_still_fails_the_same_record(self):
        self.assertEqual(T.R.judge_form("A2", T.row(), MAN, rec())["checks"]["fusion"]["status"], "FAIL")

    def test_no_activation_source_without_row_is_preserved(self):
        g = gate(man=dict(MAN, activation="NONE"), inv_rows=inv(None), form=bform(None))
        self.assertEqual(g["cls"], "ORIGINAL_ACTIVATION_PRESERVED")

    def test_activation_added_where_the_source_had_none(self):
        self.assertEqual(gate(man=dict(MAN, activation="NONE"), inv_rows=inv(None))["cls"], "EXECUTION_CHANGED")

    def test_manifest_and_inventory_disagree(self):
        g = gate(inv_rows=inv(None), form=bform(None))                         # manifest RELU6, no activation row
        self.assertEqual(g["cls"], "EXECUTION_CHANGED")
        self.assertTrue(any(d.startswith("F1") for d in g["diffs"]))
        g = gate(man=dict(MAN, activation="NONE"))                               # manifest NONE, rows have Relu6
        self.assertEqual(g["cls"], "EXECUTION_CHANGED")

    def test_activation_kind_changed(self):
        self.assertEqual(gate(form=bform("Relu"))["cls"], "EXECUTION_CHANGED")
        self.assertEqual(gate(f=facts(form_act=dict(ACT, activation=2)))["cls"], "EXECUTION_CHANGED")

    def test_activation_parameters_changed(self):
        for k in ("activation_min", "activation_max", "ofm_zero_point", "ofm_scale"):
            with self.subTest(k):
                self.assertEqual(gate(f=facts(form_act=dict(ACT, **{k: 7})))["cls"], "EXECUTION_CHANGED")

    def test_conv_tflite_activation_changed(self):
        f = bform()
        f["conv_row"] = dict(f["conv_row"], tflite_activation="RELU")
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_extra_kernel_instruction(self):
        g = gate(f=facts(kinds=["ELEMENTWISE", "CONV", "ELEMENTWISE", "ELEMENTWISE"]))
        self.assertEqual(g["cls"], "EXECUTION_CHANGED")
        self.assertEqual(gate(f=facts(kinds=["ELEMENTWISE", "CONV", "CONV", "ELEMENTWISE"]))["cls"], "EXECUTION_CHANGED")

    def test_activation_row_that_issues_work(self):
        f = bform()
        f["rows"][2] = dict(f["rows"][2], cms_offsets="300")
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")
        bad_inv = inv()
        bad_inv[1] = dict(bad_inv[1], vela_op_cycles="40")
        self.assertEqual(gate(inv_rows=bad_inv)["cls"], "EXECUTION_CHANGED")

    def test_conv_register_mismatch(self):
        f = bform(conv_kernels=[dict(T.KERN, blk_depth_m1=31)])
        f["second"]["conv_kernels"] = copy.deepcopy(f["conv_kernels"])
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_unexpected_extra_operator(self):
        f = bform()
        f["rows"].insert(3, T.row(npu_op="Mul", tflite_op_index="1", **DEAD))
        f["npu_ops"] = [r["npu_op"] for r in f["rows"]]
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_activation_row_of_another_op(self):
        f = bform()
        f["rows"][2] = dict(f["rows"][2], tflite_op_index="2")
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_wrapper_row_fused(self):
        f = bform()
        f["rows"][0] = dict(f["rows"][0], fused_names="2")
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_cpu_rows_and_output_tensor(self):
        self.assertEqual(gate(form=bform(cpu_rows=["ADD"]))["cls"], "EXECUTION_CHANGED")
        f = bform()
        f["conv_row"] = dict(f["conv_row"], name="ofm")
        self.assertEqual(gate(form=f)["cls"], "EXECUTION_CHANGED")

    def test_unverified_when_facts_missing(self):
        cases = dict(orig_regs=facts(), form_regs=facts(), orig_compile=facts())
        cases["orig_regs"]["original"]["conv_act"] = [None]
        cases["form_regs"]["forms"]["A2"]["conv_act"] = [None]
        cases["orig_compile"]["original"]["vela_sha256"] = "ffff"
        for k, f in cases.items():
            with self.subTest(k):
                g = gate(f=f)
                self.assertEqual((g["cls"], g["status"]), ("FUSION_UNVERIFIED", "FAIL"))
        self.assertEqual(gate(f=facts(sha="other"))["cls"], "FUSION_UNVERIFIED")
        self.assertEqual(gate(inv_rows=[])["cls"], "FUSION_UNVERIFIED")
        self.assertFalse(A.judge_form("A2", T.row(), MAN, inv(), rec(), facts(sha="other"))["board_eligible"])

    def test_other_gates_still_required(self):
        f = bform(refcheck=dict(T.form()["refcheck"], conv_out_informative=0.05))
        j = A.judge_form("A2", T.row(), MAN, inv(), rec(f), facts())
        self.assertEqual(j["fusion_cls"], "ORIGINAL_ACTIVATION_PRESERVED")
        self.assertFalse(j["board_eligible"])


GOOD_FX = dict(input_digest_ok=True, x_shape=[1, 8, 8, 64], conv_ifm_shape=[1, 8, 8, 64], conv_in_equals_x=True,
               conv_out_vs_model_mismatch=0, numpy_vs_ref_max_abs=1, final_vs_conv_out_max_abs=1, conv_out_informative=0.3,
               final_informative=0.3, pack_rc=0, vela_equals_record=True, cms_equals_record=True)


class Fixture(unittest.TestCase):
    def test_good_fixture_passes(self):
        self.assertEqual(A.fixture_gate(dict(GOOD_FX)), dict(status="PASS", diffs=[]))

    def test_each_rule_fails(self):
        for k, v in dict(conv_in_equals_x=False, conv_out_vs_model_mismatch=1, numpy_vs_ref_max_abs=2,
                         final_vs_conv_out_max_abs=2, conv_out_informative=0.0999, final_informative=0.0999, pack_rc=1,
                         vela_equals_record=False, cms_equals_record=False).items():
            with self.subTest(k):
                self.assertEqual(A.fixture_gate(dict(GOOD_FX, **{k: v}))["status"], "FAIL")

    def test_threshold_is_the_original_ten_percent(self):
        self.assertEqual(A.fixture_gate(dict(GOOD_FX, conv_out_informative=0.10, final_informative=0.10))["status"], "PASS")

    def test_unresolved(self):
        self.assertEqual(A.fixture_gate(None)["status"], "VALIDATION_UNRESOLVED")
        self.assertEqual(A.fixture_gate(dict(missing="input file"))["status"], "VALIDATION_UNRESOLVED")
        self.assertEqual(A.fixture_gate(dict(GOOD_FX, input_digest_ok=False))["status"], "VALIDATION_UNRESOLVED")
        self.assertEqual(A.fixture_gate(dict(GOOD_FX, x_shape=[1, 4, 4, 64]))["status"], "VALIDATION_UNRESOLVED")
        self.assertEqual(A.fixture_gate(dict(GOOD_FX, conv_in_equals_x=None))["status"], "VALIDATION_UNRESOLVED")


def cand(form=None, group="G14", fx=GOOD_FX):
    r = dict(original=copy.deepcopy(T.ORIG), forms={"A0": T.form("A0"), "A1": None, "A2": form or bform()})
    r["forms"]["A0"]["conv_row"] = dict(r["forms"]["A0"]["conv_row"], kernel="3x3")       # A0 shape differs: not eligible
    return A.judge_candidate(T.row(), dict(MAN, group=group), inv(), r, facts(), dict(fx) if fx else None)


SAT = dict(T.form()["refcheck"], conv_out_informative=0.05, final_informative=0.05)


class Additional(unittest.TestCase):
    def test_saturation_only_with_fixture_pass_is_reported_apart(self):
        c = cand(bform(refcheck=SAT))
        self.assertFalse(c["board_eligible"])
        self.assertTrue(c["board_eligible_with_additional"])
        self.assertEqual(c["fixture"]["status"], "PASS")

    def test_fixture_fail_keeps_it_out(self):
        self.assertFalse(cand(bform(refcheck=SAT), fx=dict(GOOD_FX, final_informative=0.05))["board_eligible_with_additional"])

    def test_no_fixture_outside_the_fixed_groups(self):
        c = cand(bform(refcheck=SAT), group="G01")
        self.assertIsNone(c["fixture"])
        self.assertFalse(c["board_eligible_with_additional"])

    def test_other_reference_failure_is_not_saturation_only(self):
        f = bform(refcheck=dict(SAT, numpy_vs_ref_max_abs=3))
        self.assertFalse(cand(f)["board_eligible_with_additional"])

    def test_other_gate_failure_is_not_saturation_only(self):
        f = bform(refcheck=SAT, ta_profile=2)
        self.assertFalse(cand(f)["board_eligible_with_additional"])
        g = bform(refcheck=SAT)
        g["rows"][2] = dict(g["rows"][2], cms_offsets="300")
        self.assertFalse(cand(g)["board_eligible_with_additional"])

    def test_partial_is_not_promoted(self):
        f = bform(refcheck=SAT)
        f["conv_row"] = dict(f["conv_row"], staging_usage="1")
        f["second"]["conv_row"] = copy.deepcopy(f["conv_row"])
        c = cand(f)
        self.assertEqual(c["forms"]["A2"]["cls"], "PARTIAL_A")
        self.assertFalse(c["board_eligible_with_additional"])

    def test_eligible_candidate_counts_in_both(self):
        c = cand()
        self.assertTrue(c["board_eligible"] and c["board_eligible_with_additional"])


class Provenance(unittest.TestCase):
    def test_fact_from_another_stream_is_invalid(self):
        man = dict(candidates=[dict(group="G14")])
        recs = dict(G14=dict(forms=dict(A0=None, A1=None, A2=dict(cms_sha256="c"))))
        self.assertEqual(A.fact_provenance(man, recs, dict(G14=facts())), [])
        self.assertEqual(len(A.fact_provenance(man, recs, dict(G14=facts(sha="z")))), 1)
        self.assertEqual(len(A.fact_provenance(man, recs, {})), 1)


class Estimates(unittest.TestCase):
    def test_conv_and_graph_scope(self):
        r = dict(forms=dict(A0=None, A1=None, A2=bform()))
        r["forms"]["A2"]["conv_row"] = dict(r["forms"]["A2"]["conv_row"], vela_op_cycles="500", vela_mac_cycles="300")
        e = A.vela_estimates(r)["A2"]
        self.assertEqual((e["conv_op_cycles"], e["conv_mac_cycles"], e["graph_op_cycles_sum"]), (500, 300, 100))


if __name__ == "__main__":
    unittest.main()
