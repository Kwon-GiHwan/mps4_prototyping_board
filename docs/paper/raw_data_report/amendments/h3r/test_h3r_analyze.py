"""Fixtures for every gate rule and every preregistered outcome of h3r_analyze. Run from the repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.h3r.test_h3r_analyze
Mutation check (per CLAUDE.md): neuter a comparison in h3r_analyze.py, this file must go RED (mutation_log.md)."""
import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h3r_analyze as A  # noqa: E402

CELL = "h3r_%s_%dx%d_c128__SSE-320__ethos-u85-%d"
LOW = {"SRAM_MAXR": 8, "SRAM_MAXW": 8, "SRAM_MAXRW": 0, "SRAM_RLATENCY": 16, "SRAM_WLATENCY": 16, "SRAM_PULSE_ON": 3999,
       "SRAM_PULSE_OFF": 1, "SRAM_BWCAP": 4000, "EXT_MAXR": 24, "EXT_MAXW": 12, "EXT_MAXRW": 0, "EXT_RLATENCY": 250,
       "EXT_WLATENCY": 125, "EXT_PULSE_ON": 4000, "EXT_PULSE_OFF": 1000, "EXT_BWCAP": 2344}
MID = dict(LOW, SRAM_RLATENCY=32, SRAM_WLATENCY=32, EXT_MAXR=64, EXT_MAXW=32, EXT_RLATENCY=500, EXT_WLATENCY=250, EXT_BWCAP=3750)
EQ = dict(LOW, SRAM_RLATENCY=0, SRAM_WLATENCY=0, EXT_MAXR=0, EXT_MAXW=0, EXT_RLATENCY=0, EXT_WLATENCY=0, EXT_BWCAP=0)
PROFILE = {256: LOW, 512: MID}
OK_PRES = dict(A.PRESERVED)
SHAPES = [(1, 36), (2, 18), (3, 12), (4, 9), (6, 6), (9, 4), (12, 3), (18, 2), (36, 1)]


def manifest(ops=A.OPS, shapes=SHAPES, g1=True):
    return [{"model": "h3r_%s_%dx%d_c128" % (op, h, w), "op": op, "H": h, "W": w, "g1prime_pass": g1} for op in ops for h, w in shapes]


def meas(total, active=None, **kw):
    m = {"npu_total_cycles": total, "npu_active_cycles": total - 500 if active is None else active, "npu_idle_cycles": 500,
         "sram_rd_beats": 10, "sram_wr_beats": 11, "ext_rd_beats": 12, "ext_wr_beats": 13}
    m.update(kw); return m


def recs(op, h, w, mac, arm, total, active=None, defines=None, header=None, cache=None, status="SUCCESS", reps=3, header_ok=None,
         vela="v-%s-%d" % ("x", 0), verify_sha="dump", verify_status="SUCCESS", verify_file=None, verify_m=None, **kw):
    cell = CELL % (op, h, w, mac)
    defines = defines if defines is not None else (dict(PROFILE[mac]) if arm == "base" else dict(EQ))
    header = header if header is not None else dict(defines)
    art = {"vela_sha256": vela, "cc_body_sha256": "c-" + vela, "axf_sha256": "a"}
    out = []
    for rep in range(1, reps + 1):
        r = {"experiment": "H3R", "cell_id": cell, "arm": arm, "defines": defines, "ta_header": header, "ta_cache": cache,
             "header_matches_request": all(header.get(k) == v for k, v in defines.items()) if header_ok is None else header_ok,
             "rep": rep, "status": status, "measurement": meas(total, active, **kw), "artifact": art}
        if rep == 1:
            r["verify"] = {"build_ok": True, "status": verify_status, "dump_sha256": verify_sha, "uart_file": verify_file,
                           "measurement": verify_m or meas(total, active, **kw)}
        out.append(r)
    return out


def pair(op, h, w, arm, c256, c512, a256=None, a512=None, **kw):
    return recs(op, h, w, 256, arm, c256, a256, vela="v256", **kw) + recs(op, h, w, 512, arm, c512, a512, vela="v512", **kw)


def one_model(op="conv1x1", h=6, w=6, **kw):
    return pair(op, h, w, "base", 6068, 7068, **kw) + pair(op, h, w, "equalized", 4068, 3068, **kw)


def run(records, man=None, preserved=OK_PRES, verify_dir=None):
    return A.analyze(records, man if man is not None else manifest(), verify_dir=verify_dir or Path(tempfile.mkdtemp()), preserved=preserved)


class Gates(unittest.TestCase):
    def arm_rule(self, res, op, h, w, mac, arm):
        v = res["gates"]["arms"]["%s|%s" % (CELL % (op, h, w, mac), arm)]
        return None if v == "PASS" else v["refused"]

    def model_rule(self, res, model):
        return res["gates"]["models"][model].get("refused")

    def test_clean_passes(self):
        res = run(one_model())
        self.assertEqual(set(res["gates"]["arms"].values()), {"PASS"})
        self.assertEqual(self.model_rule(res, "h3r_conv1x1_6x6_c128"), None)
        self.assertEqual(res["gates"]["preservation"], "PASS")

    def test_run_status(self):
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, status="FAILURE_TIMEOUT", vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_RUN)

    def test_run_missing_counter_is_not_a_value(self):
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, ext_rd_beats=None, vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_RUN)

    def test_run_fewer_reps(self):
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, reps=2, vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_RUN)

    def test_reps_differ(self):
        rs = one_model(); rs[2]["measurement"]["npu_total_cycles"] = 6069
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 6, 6, 256, "base"), A.RULE_REPS_DIFFER)
        rs = one_model(); rs[1]["measurement"]["sram_rd_beats"] = 99
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 6, 6, 256, "base"), A.RULE_REPS_DIFFER)

    def test_ta_header_mismatch(self):
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, header=dict(LOW, EXT_MAXR=23), vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_TA_CONFIG)
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, header_ok=False, vela="v256")   # harness flag alone
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_TA_CONFIG)

    def test_ta_cache_mismatch(self):
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, cache=dict(LOW, SRAM_BWCAP=1), vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), A.RULE_TA_CONFIG)
        rs = one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, cache=dict(LOW), vela="v256")
        self.assertEqual(self.arm_rule(run(rs), "conv1x1", 1, 36, 256, "base"), None)

    def test_equalized_applied_must_match_across_macs(self):
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068) + recs("conv1x1", 6, 6, 256, "equalized", 4068, vela="v256") \
            + recs("conv1x1", 6, 6, 512, "equalized", 3068, defines=dict(EQ, EXT_MAXW=32), vela="v512")
        self.assertEqual(self.model_rule(run(rs), "h3r_conv1x1_6x6_c128"), A.RULE_TA_CONFIG)

    def test_applied_mask_64_is_0(self):
        self.assertEqual(A.applied({"EXT_MAXR": 64, "EXT_MAXW": 32, "EXT_RLATENCY": 500})["EXT_MAXR"], 0)
        self.assertEqual(A.applied({"EXT_MAXR": 63})["EXT_MAXR"], 63)
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068) + recs("conv1x1", 6, 6, 256, "equalized", 4068, vela="v256") \
            + recs("conv1x1", 6, 6, 512, "equalized", 3068, defines=dict(EQ, EXT_MAXR=64), vela="v512")   # 64 -> applied 0 == 0
        self.assertEqual(self.model_rule(run(rs), "h3r_conv1x1_6x6_c128"), None)

    def test_artifact_identity_within_cell(self):
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068) + recs("conv1x1", 6, 6, 256, "equalized", 4068, vela="v256-other") \
            + recs("conv1x1", 6, 6, 512, "equalized", 3068, vela="v512")
        res = run(rs)
        self.assertEqual(res["gates"]["cells"][CELL % ("conv1x1", 6, 6, 256)]["refused"], A.RULE_ARTIFACT)
        self.assertNotIn("h3r_conv1x1_6x6_c128|base|256", res["cycles"])

    def test_g1prime(self):
        self.assertEqual(self.model_rule(run(one_model(), manifest(g1=False)), "h3r_conv1x1_6x6_c128"), A.RULE_G1PRIME)
        self.assertEqual(self.model_rule(run(one_model(), manifest(g1=None)), "h3r_conv1x1_6x6_c128"), A.RULE_G1PRIME)

    def test_output_mismatch_across_mac(self):
        rs = recs("conv1x1", 6, 6, 256, "base", 6068, vela="v256", verify_sha="d1") + recs("conv1x1", 6, 6, 512, "base", 7068, vela="v512", verify_sha="d2")
        self.assertEqual(self.model_rule(run(rs), "h3r_conv1x1_6x6_c128"), A.RULE_OUTPUT_MISMATCH)

    def test_output_mismatch_across_ta(self):
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068) + pair("conv1x1", 6, 6, "equalized", 4068, 3068, verify_sha="other")
        self.assertEqual(self.model_rule(run(rs), "h3r_conv1x1_6x6_c128"), A.RULE_OUTPUT_MISMATCH)

    def test_output_not_verified_is_refused(self):
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068) + pair("conv1x1", 6, 6, "equalized", 4068, 3068, verify_status="FAILURE_TIMEOUT")
        self.assertEqual(self.model_rule(run(rs), "h3r_conv1x1_6x6_c128"), A.RULE_OUTPUT_MISMATCH)

    def test_output_bytes_compared_from_uart(self):
        d = Path(tempfile.mkdtemp())
        def uart(name, hexes, complete=True):
            n = len(hexes) if complete else len(hexes) + 1
            (d / name).write_text("Model OUTPUT tensors:\n tensor occupies %d bytes\nActivation buffer\n"
                                  "output tensors post inference\n%s\nProfile for Inference\n" % (n, " ".join("0x%02x" % x for x in hexes)))
            return str(d / name)
        a = uart("a.txt", [1, 2, 3]); b = uart("b.txt", [1, 2, 3]); c = uart("c.txt", [1, 2, 4]); inc = uart("i.txt", [1, 2, 3], complete=False)
        rs = recs("conv1x1", 6, 6, 256, "base", 6068, vela="v256", verify_sha="s1", verify_file=a) + recs("conv1x1", 6, 6, 512, "base", 7068, vela="v512", verify_sha="s2", verify_file=b)
        self.assertEqual(self.model_rule(run(rs, verify_dir=d), "h3r_conv1x1_6x6_c128"), None)   # same bytes, different digest strings: bytes win
        rs = recs("conv1x1", 6, 6, 256, "base", 6068, vela="v256", verify_sha="s", verify_file=a) + recs("conv1x1", 6, 6, 512, "base", 7068, vela="v512", verify_sha="s", verify_file=c)
        self.assertEqual(self.model_rule(run(rs, verify_dir=d), "h3r_conv1x1_6x6_c128"), A.RULE_OUTPUT_MISMATCH)
        rs = recs("conv1x1", 6, 6, 256, "base", 6068, vela="v256", verify_sha="s", verify_file=a) + recs("conv1x1", 6, 6, 512, "base", 7068, vela="v512", verify_sha="s", verify_file=inc)
        res = run(rs, verify_dir=d)
        self.assertEqual(self.model_rule(res, "h3r_conv1x1_6x6_c128"), A.RULE_OUTPUT_MISMATCH); self.assertIn("incomplete", res["gates"]["models"]["h3r_conv1x1_6x6_c128"]["msg"])

    def test_instrumentation_note(self):
        rs = pair("conv1x1", 6, 6, "base", 6068, 7068, verify_m=meas(6069))
        self.assertEqual(run(rs)["gates"]["models"]["h3r_conv1x1_6x6_c128"]["notes"][0]["note"], "INSTRUMENTATION_DEVIATION")

    def test_preservation(self):
        bad = dict(OK_PRES); bad["h13/results.jsonl"] = "0" * 64
        with self.assertRaises(A.Refusal) as cm:
            run(one_model(), preserved=bad)
        self.assertEqual(A.refusal_rule(cm.exception), A.RULE_PRESERVATION)

    def test_rules_tuple_complete(self):
        tripped = set()
        for rs, man in ((one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, status="FAILURE", vela="v256"), None),
                        (one_model() + recs("conv1x1", 1, 36, 256, "base", 6068, header=dict(LOW, EXT_MAXR=23), vela="v256"), None),
                        (one_model(), manifest(g1=False)),
                        (pair("conv1x1", 6, 6, "base", 6068, 7068, verify_sha="x") + pair("conv1x1", 6, 6, "equalized", 4068, 3068, verify_sha="y"), None),
                        (pair("conv1x1", 6, 6, "base", 6068, 7068) + recs("conv1x1", 6, 6, 256, "equalized", 4068, vela="v256-2") + recs("conv1x1", 6, 6, 512, "equalized", 3068, vela="v512"), None)):
            res = run(rs, man)
            for v in res["gates"]["arms"].values():
                if v != "PASS": tripped.add(v["refused"])
            for v in res["gates"]["cells"].values():
                if v != "PASS": tripped.add(v["refused"])
            for v in res["gates"]["models"].values():
                if v.get("refused"): tripped.add(v["refused"])
        rs = one_model(); rs[2]["measurement"]["npu_total_cycles"] = 1
        tripped.add(self.arm_rule(run(rs), "conv1x1", 6, 6, 256, "base"))
        try:
            run(one_model(), preserved={})
        except A.Refusal as e:
            tripped.add(A.refusal_rule(e))
        self.assertEqual(tripped, set(A.RULES))


def grid(op, cond, r_by_shape, c256=10000, metric_active=None):
    """records for one op x cond with prescribed r per shape (TOTAL); ACTIVE r via metric_active (default same)."""
    rs = []
    for (h, w), r in r_by_shape.items():
        ra = r if metric_active is None else metric_active[(h, w)]
        rs += pair(op, h, w, cond, c256, int(round(c256 * r)), a256=c256 - 500, a512=int(round((c256 - 500) * ra)))
    return rs


def flat(r, h=None, w=None, r_hw=None):
    d = {s: r for s in SHAPES}
    if h is not None:
        d[(h, w)] = r_hw
    return d


class Judgements(unittest.TestCase):
    def values(self, rs, metric="TOTAL"):
        return run(rs)["judged"][metric]["values"]

    def test_ratio_and_spread(self):
        rs = grid("conv1x1", "base", flat(1.0, 36, 1, 0.7))
        v = run(rs)["judged"]["TOTAL"]
        self.assertEqual(v["ratios"]["h3r_conv1x1_36x1_c128|base"], 0.7)
        self.assertEqual(v["spread"]["conv1x1|base"]["spread"], 0.3); self.assertEqual(v["spread"]["conv1x1|base"]["n"], 9)

    def test_shape_effect_threshold(self):
        self.assertTrue(self.values(grid("conv1x1", "base", flat(1.0, 36, 1, 0.9)))["SHAPE_EFFECT:conv1x1:base"]["holds"])
        self.assertFalse(self.values(grid("conv1x1", "base", flat(1.0, 36, 1, 0.91)))["SHAPE_EFFECT:conv1x1:base"]["holds"])
        self.assertTrue(self.values(grid("dw3x3", "bridge_legacy_relaxed", flat(0.67, 36, 1, 0.5)))["SHAPE_EFFECT:dw3x3:bridge_legacy_relaxed"]["holds"])

    def test_memory_shape_interaction(self):
        b = grid("conv3x3", "base", flat(0.94, 36, 1, 0.58))          # spread 0.36
        self.assertTrue(self.values(b + grid("conv3x3", "equalized", flat(0.56, 36, 1, 0.39)))["MEMORY_SHAPE_INTERACTION:conv3x3"]["holds"])   # 0.17 < 0.18
        self.assertFalse(self.values(b + grid("conv3x3", "equalized", flat(0.56, 36, 1, 0.38)))["MEMORY_SHAPE_INTERACTION:conv3x3"]["holds"])  # 0.18 not < 0.18
        z = grid("dw3x3", "base", flat(1.0)) + grid("dw3x3", "equalized", flat(1.0))
        self.assertFalse(self.values(z)["MEMORY_SHAPE_INTERACTION:dw3x3"]["holds"])                          # base spread 0 -> cannot halve

    def test_type_dependent(self):
        rs = grid("conv1x1", "base", flat(1.165)) + grid("conv3x3", "base", flat(0.936)) + grid("dw3x3", "base", flat(1.0))
        v = self.values(rs)["TYPE_DEPENDENT:base"]; self.assertTrue(v["holds"]); self.assertEqual(v["value"], [1.165, 0.936, 1.0])
        rs = grid("conv1x1", "base", flat(1.0)) + grid("conv3x3", "base", flat(0.95)) + grid("dw3x3", "base", flat(1.0))
        self.assertFalse(self.values(rs)["TYPE_DEPENDENT:base"]["holds"])
        rs = grid("conv1x1", "base", flat(1.10)) + grid("conv3x3", "base", flat(1.0)) + grid("dw3x3", "base", flat(1.0))   # boundary 0.10
        self.assertTrue(self.values(rs)["TYPE_DEPENDENT:base"]["holds"])
        rs = grid("conv1x1", "equalized", flat(0.75)) + grid("conv3x3", "equalized", flat(0.56)) + grid("dw3x3", "equalized", flat(0.67))
        self.assertTrue(self.values(rs)["TYPE_DEPENDENT:equalized"]["holds"]); self.assertNotIn("TYPE_DEPENDENT:base", self.values(rs))

    def test_metric_dependent(self):
        rs = grid("conv1x1", "base", flat(1.0, 36, 1, 0.85), metric_active=flat(1.0, 36, 1, 0.95))
        res = run(rs)
        row = [r for r in res["judgements"] if r["judgement"] == "SHAPE_EFFECT:conv1x1:base"][0]
        self.assertTrue(row["TOTAL_holds"]); self.assertFalse(row["ACTIVE_holds"]); self.assertEqual(row["label"], "METRIC_DEPENDENT")
        rs = grid("conv1x1", "base", flat(1.0, 36, 1, 0.85))
        self.assertEqual([r["label"] for r in run(rs)["judgements"]], ["HOLDS_BOTH"])
        self.assertEqual([r["label"] for r in run(grid("conv1x1", "base", flat(1.0)))["judgements"]], ["FAILS_BOTH"])
        self.assertIn("SHAPE_EFFECT:conv1x1:base", res["judged"]["TOTAL"]["outcomes"]); self.assertNotIn("SHAPE_EFFECT:conv1x1:base", res["judged"]["ACTIVE"]["outcomes"])

    def test_bridge_descriptive(self):
        rs = pair("dw3x3", 6, 6, "bridge_legacy_relaxed", 3068, 2068, a256=2790, a512=1500) + pair("dw3x3", 6, 6, "equalized", 3068, 3068, a256=2790, a512=2790)
        b = run(rs)["bridge"]["h3r_dw3x3_6x6_c128"]
        self.assertAlmostEqual(b["r_TOTAL|bridge_legacy_relaxed"], 0.6741, 4); self.assertEqual(b["r_TOTAL|equalized"], 1.0)
        self.assertAlmostEqual(b["delta_r_TOTAL"], 0.3259, 4); self.assertAlmostEqual(b["delta_r_ACTIVE"], 1 - 1500 / 2790.0, 4)
        self.assertEqual(b["bridge_legacy_relaxed|512"]["npu_total_cycles"], 2068)

    def test_refused_arm_excluded_from_ratios(self):
        rs = grid("conv1x1", "base", flat(1.0)); rs[2]["measurement"]["npu_total_cycles"] = 1   # 1x36 256 rep3 differs
        v = run(rs)["judged"]["TOTAL"]
        self.assertNotIn("h3r_conv1x1_1x36_c128|base", v["ratios"]); self.assertEqual(v["spread"]["conv1x1|base"]["n"], 8)


if __name__ == "__main__":
    unittest.main()
