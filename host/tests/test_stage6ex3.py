"""Stage 6E-X3 judge tests on synthetic run trees. Expected values are hand-written from the contract."""
import csv
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "lib"))
import drwl  # noqa: E402
import record_v2  # noqa: E402
import stage6ex3 as X  # noqa: E402

WL = REPO / "evidence/stage6ex3/workloads"
VELA = REPO / "evidence/stage6ex3/vela"
OK_FLAGS = record_v2.REQUIRED | record_v2.OUTPUT_MATCH | record_v2.REGIONCFG_MATCH
CAPS = {"magic": 1, "schema": 5, "record_fields": 92, "npu_config": 0x2000201A, "ta_ext_rlatency": 500,
        "ta_sram_rlatency": 32, "ta_ext_maxr": 8}
KWS = dict(npu=91000, mac=56450, dpu=49495)


def ev(npu, mac, dpu, extra=None):
    """Event values for all three passes."""
    e = {35: npu, 48: mac, 51: dpu, 53: 0, 55: 0, 64: 17825, 80: 11415, 81: 64094, 128: 3337, 130: 22664, 132: 3170,
         135: 17760, 384: 1607, 386: 15815, 391: 1, 131: 777, 142: 5, 387: 17579, 640: 754, 642: 7832, 656: 853, 658: 7983}
    e.update(extra or {})
    return e


def record(codes, e, flags_pmu, mlen, **over):
    r = dict(schema=5, placement=0, model_len=mlen, pmu_flags=flags_pmu,
             pmcr_after_arm=0x4001 | (0x8 if flags_pmu else 0), irq_count=1, job_result=0, ofm_mismatch=0,
             event_count=len(codes))
    for i, c in enumerate(codes):
        r[f"event_code{i}"], r[f"ev_irq{i}"] = c, e[c]
    r.update(over)
    return r


def write_boot(root, k, e, crc=7, crc_fn=None, per_run=None, rows_over=None, caps=None, rec_over=None, flags=OK_FLAGS, sets=X.SETS):
    m = json.loads((WL / X.MANIFEST).read_text())[k]
    model_len = drwl.parse((WL / f"{k}.drwl").read_bytes())["model_len"]
    folder = root / "conds" / k / "wfe"
    folder.mkdir(parents=True, exist_ok=True)
    raw = [dict(ping=1)]
    for s, codes in sets.items():
        for rep in range(1, X.REPS + 1):
            ee = dict(e)
            if per_run:
                ee.update(per_run(s, rep) or {})
            raw.append(dict(set_id=s, rep=rep, run_sequence=len(raw), valid_flags=flags, run_rc=0,
                            record=record(codes, ee, m["pmu_flags"], model_len, **(rec_over or {})),
                            output_crc32=crc_fn(s, rep) if crc_fn else crc, output_len=12))
    (folder / "raw_runs.json").write_text(json.dumps(raw))
    row = dict(workload_sha256=m["drwl_sha256"], host_boot_index=str(X.BOOT[k]), condition="wfe", **X.IMAGE)
    row.update(rows_over or {})
    with (folder / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    (folder.parent / "capabilities.json").write_text(json.dumps(caps or CAPS))


def write_m7(root, model, npu, mac, dpu, warm=None, spread=0, vary=None):
    """m7 layout: set 1 = BASE (35 17; NPU_ACTIVE differs from pass A on purpose), set 2 = pass A, 3 = pass B, 4/7/8 hold
    pass C's events; reps 1-2 warm-up (values from `warm` if given)."""
    raw = [dict(ping=1)]
    sets = {1: [35, 17], 2: X.PASS_A, 3: X.PASS_B, 4: [35, 131, 142, 387], 7: [35, 642, 658], 8: [35, 640, 656]}
    for s, codes in sets.items():
        for rep in range(1, 11):
            e = ev(npu + (2000 if s == 1 else 0) + (spread // 2 if rep == 3 else -spread // 2 if rep == 4 else 0), mac, dpu,
                   {17: 1})
            if rep <= 2 and warm:
                e.update(warm)
            if vary and rep in (3, 4):
                e.update({c: d + (1 if rep == 3 else -1) for c, d in vary.items()})
            raw.append(dict(set_id=s, rep=rep, record=dict(event_count=len(codes), **{f"event_code{i}": c for i, c in enumerate(codes)},
                                                          **{f"ev_irq{i}": e[c] for i, c in enumerate(codes)})))
    (root / model).mkdir(parents=True, exist_ok=True)
    (root / model / "raw_runs.json").write_text(json.dumps(raw))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root, self.m7 = self.tmp / "run", self.tmp / "m7"
        write_m7(self.m7, "kws_micronet_m", KWS["npu"], KWS["mac"], KWS["dpu"])
        write_m7(self.m7, "ad_medium_int8", 146000, 93672, 93672)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def res(self, k):
        return X.config_result(self.root, WL, self.m7, CAPS, k)


class Validity(Base):
    def test_valid(self):
        write_boot(self.root, "x3_kws_B0", ev(**KWS))
        r = self.res("x3_kws_B0")
        self.assertEqual((r["status"], r["reasons"]), ("VALID", []))
        self.assertEqual(X.val(r, 1, 35), (91000.0, 0.0))

    def test_unmeasured(self):
        self.assertEqual(self.res("x3_kws_B0")["status"], "UNMEASURED")

    def test_config_mismatch_terms(self):
        cases = [dict(rows_over=dict(workload_sha256="x")), dict(rows_over=dict(bram_sha256="x")),
                 dict(rows_over=dict(host_boot_index="476")), dict(rows_over=dict(condition="busy")),
                 dict(caps=dict(CAPS, ta_ext_rlatency=1000)), dict(caps=dict(CAPS, ta_sram_rlatency=33)),
                 dict(caps=dict(CAPS, schema=4)), dict(caps=dict(CAPS, npu_config=0x2000201B)),
                 dict(rec_over=dict(schema=4)), dict(rec_over=dict(placement=1)), dict(rec_over=dict(pmu_flags=1)),
                 dict(rec_over=dict(pmcr_after_arm=0x4009)), dict(rec_over=dict(irq_count=2)),
                 dict(rec_over=dict(model_len=1))]
        for c in cases:
            shutil.rmtree(self.root, ignore_errors=True)
            write_boot(self.root, "x3_kws_B0", ev(**KWS), **c)
            self.assertEqual(self.res("x3_kws_B0")["status"], "CONFIG_MISMATCH", c)

    def test_serial_mask_en_required(self):
        write_boot(self.root, "x3_kws_B0", ev(**KWS))
        write_boot(self.root, "x3_kws_B1", ev(**KWS), rec_over=dict(pmcr_after_arm=0x4001))
        self.assertEqual(self.res("x3_kws_B1")["status"], "CONFIG_MISMATCH")

    def test_output(self):
        write_boot(self.root, "x3_kws_B0", ev(**KWS), rec_over=dict(ofm_mismatch=3))
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_OUTPUT")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), flags=OK_FLAGS & ~record_v2.OUTPUT_MATCH)
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_OUTPUT")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), crc=7)
        write_boot(self.root, "x3_kws_B1", ev(**KWS), crc=8)                  # serial output != original
        self.assertEqual(self.res("x3_kws_B1")["status"], "INVALID_OUTPUT")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B1", ev(**KWS), crc=7)                  # no B0 to compare with
        self.assertEqual(self.res("x3_kws_B1")["status"], "INVALID_OUTPUT")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), crc=None)
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_OUTPUT")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), crc_fn=lambda s, r: 7 if r < 5 else 9)
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_OUTPUT")

    def test_pmu(self):
        write_boot(self.root, "x3_kws_B0", ev(**KWS), flags=OK_FLAGS & ~record_v2.NO_OVERFLOW)
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_PMU")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), sets={1: X.PASS_A, 2: X.PASS_B})
        self.assertEqual(self.res("x3_kws_B0")["status"], "INVALID_PMU")

    def test_unstable(self):
        write_boot(self.root, "x3_kws_B0", ev(**KWS), per_run=lambda s, r: {48: 56451} if s == 1 and r == 3 else None)
        self.assertEqual(self.res("x3_kws_B0")["status"], "UNSTABLE")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), per_run=lambda s, r: {35: 96000} if s == 2 else None)
        self.assertEqual(self.res("x3_kws_B0")["status"], "UNSTABLE")
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), per_run=lambda s, r: {35: 96000} if s == 1 and r == 2 else None)
        r = self.res("x3_kws_B0")
        self.assertEqual(r["status"], "UNSTABLE")
        self.assertIn("NPU_ACTIVE pass A range", r["reasons"])
        shutil.rmtree(self.root)                                              # warm-up RUN is not judged
        write_boot(self.root, "x3_kws_B0", ev(**KWS), per_run=lambda s, r: {35: 99000, 48: 1} if r == 1 else None)
        self.assertEqual(self.res("x3_kws_B0")["status"], "VALID")


class Gates(Base):
    def test_g1(self):                                                         # amendment B rule
        write_m7(self.m7, "kws_micronet_m", KWS["npu"], KWS["mac"], KWS["dpu"], spread=2000)
        ref = X.m7_ref(self.m7, "kws_micronet_m")
        self.assertEqual((ref["events"][35], ref["npu_range_cap"]), ((91000.0, 2000.0), 2000.0))
        spread = lambda s, r: {35: 91000 + (750 if r == 2 else -750 if r == 3 else 0)} if s == 1 else None  # noqa: E731
        g = lambda npu, sp=spread, extra=None: self.g1_of(ev(npu, KWS["mac"], KWS["dpu"], extra), sp, ref, npu)  # noqa: E731
        self.assertEqual(g(91000)["npu"]["tolerance"], 3500.0)                    # range_m7 2000 + range_B0 1500
        for npu, want in ((94500, "PASS"), (87500, "PASS"), (94501, "FAIL"), (87499, "FAIL")):
            self.assertEqual(g(npu)["verdict"], want, npu)
        flat = lambda s, r: None  # noqa: E731
        self.assertEqual(g(93000, flat)["npu"]["tolerance"], 2000.0)            # max(1 % = 910, 2000 + 0)
        big = lambda s, r: {35: 91000 + (1001 if r == 2 else -1000 if r == 3 else 0)} if s == 1 else None  # noqa: E731
        r = g(91000, big)
        self.assertEqual(r["verdict"], "FAIL")                                    # range 2001 > m7 cap 2000
        self.assertIn("range", " ".join(r["reasons"]))
        for c, v, want in ((48, KWS["mac"] + 1, "FAIL"), (51, KWS["dpu"] - 1, "FAIL"), (642, 7833, "FAIL"),
                           (130, 22665, "FAIL"), (391, 2, "FAIL"), (656, 852, "FAIL"), (387, 17579 + 175, "PASS"),
                           (64, 17825 + 179, "FAIL"), (64, 17825 + 178, "PASS"), (142, 5, "PASS"), (142, 6, "FAIL")):
            self.assertEqual(g(91000, flat, {c: v})["verdict"], want, (c, v))
        port = lambda s, r: {642: 7833} if s == 3 and r == 4 else None  # noqa: E731
        self.assertEqual(g(91000, port)["verdict"], "FAIL")                       # a deterministic counter varying
        shutil.rmtree(self.root, ignore_errors=True)
        write_boot(self.root, "x3_kws_B0", ev(**KWS), rec_over=dict(ofm_mismatch=1))
        self.assertEqual(X.g1(self.res("x3_kws_B0"), ref)["verdict"], "FAIL")
        write_m7(self.m7, "kws_micronet_m", KWS["npu"], KWS["mac"], KWS["dpu"], warm={642: 9000, 35: 99000})
        ref = X.m7_ref(self.m7, "kws_micronet_m")                             # m7 warm-up RUNs are not reference
        self.assertEqual((ref["events"][642], ref["events"][35], ref["npu_range_cap"]), ((7832.0, 0.0), (91000.0, 0.0), 0.0))
        self.assertEqual(g(91000, flat)["verdict"], "PASS")
        write_m7(self.m7, "kws_micronet_m", KWS["npu"], KWS["mac"], KWS["dpu"], vary={642: 7832})
        ref = X.m7_ref(self.m7, "kws_micronet_m")                             # reference itself not deterministic
        self.assertEqual(ref["events"][642], (7832.0, 2.0))
        self.assertEqual(g(91000, flat)["verdict"], "FAIL")

    def g1_of(self, e, per_run, ref, npu):
        shutil.rmtree(self.root, ignore_errors=True)
        write_boot(self.root, "x3_kws_B0", e, per_run=(lambda s, r: {35: npu - 91000 + per_run(s, r)[35]} if per_run(s, r) and 35 in per_run(s, r) else per_run(s, r)))
        return X.g1(self.res("x3_kws_B0"), ref)

    def kws_serial(self, b2, b3, b4, b1=(95000, 56450)):
        write_boot(self.root, "x3_kws_B0", ev(**KWS))
        for k, (n, m) in (("x3_kws_B1", b1), ("x3_kws_B2", b2), ("x3_kws_B3", b3), ("x3_kws_B4", b4)):
            write_boot(self.root, k, ev(n, m, m))
        return {X.key("kws_micronet_m", c): self.res(X.key("kws_micronet_m", c)) for c in ("B0", "B1", "B2", "B3", "B4")}

    def test_gm_pass(self):
        res = self.kws_serial((20000, 11700), (30000, 26090), (45000, 18660))
        g = X.gm(res, "kws_micronet_m")
        self.assertEqual(g["verdict"], "PASS", g)

    def test_gm_failures(self):
        for b2, b3, b4, why in (((90250, 11700), (30000, 26090), (45000, 18660), "m2 0.95"),
                                ((20000, 11700), (30000, 26090), (46000, 18660), "m3 npu"),
                                ((20000, 11700), (30000, 26090), (45000, 19260), "m3 mac"),
                                ((20000, 11800), (30000, 26352), (45000, 18298), "m4 op0 +1.0 %"),
                                ((0, 0), (30000, 26090), (65000, 30360), "m2 zero window")):
            shutil.rmtree(self.root, ignore_errors=True)
            res = self.kws_serial(b2, b3, b4)
            self.assertEqual(X.gm(res, "kws_micronet_m")["verdict"], "FAIL", why)

    def test_gm_inert_mask_fails(self):                                        # the 14077be failure mode
        shutil.rmtree(self.root, ignore_errors=True)
        res = self.kws_serial((95000, 56450), (95000, 56450), (95000, 56450))
        g = X.gm(res, "kws_micronet_m")
        self.assertEqual(g["verdict"], "FAIL")
        self.assertFalse(g["m2"]["holds"])


class Hypotheses(unittest.TestCase):
    def r(self, npu, mac, rng=0.0, status="VALID"):
        return dict(status=status, stats={1: {"35": (float(npu), rng), "48": (float(mac), 0.0)}})

    def test_h_s(self):
        res = {"x3_kws_B0": self.r(91000, 56450), "x3_kws_B1": self.r(95000, 57014)}
        self.assertEqual(X.h_s(res, "kws_micronet_m"), "SUPPORTED")
        res["x3_kws_B1"] = self.r(95000, 57015)
        self.assertEqual(X.h_s(res, "kws_micronet_m"), "REFUTED")

    def test_h_k(self):
        res = {"x3_kws_B3": self.r(1, 26350), "x3_kws_B2": self.r(1, 12285)}
        self.assertEqual((X.h_k(res)["G_0"], X.h_k(res)["G_V"]), ("SUPPORTED", "SUPPORTED"))
        res = {"x3_kws_B3": self.r(1, 26352), "x3_kws_B2": self.r(1, 12286)}
        self.assertEqual((X.h_k(res)["G_0"], X.h_k(res)["G_V"]), ("REFUTED", "REFUTED"))

    def test_h_a(self):
        f = lambda v, ok=True: X.h_a({"x3_ad_B2": self.r(1, v)}, ok)["verdict"]  # noqa: E731
        self.assertEqual(f(63504), "H_A1_SUPPORTED")
        self.assertEqual(f(57456), "H_A1_SUPPORTED")
        self.assertEqual(f(63505), "H_A2_SUPPORTED")
        self.assertEqual(f(57455), "NEITHER")
        self.assertEqual(f(60480, False), "INSUFFICIENT_EVIDENCE")

    def test_h_o(self):
        res = {"x3_kws_B0": self.r(100000, 1, 300), "x3_kws_B1": self.r(101000, 1, 300)}
        self.assertEqual(X.h_o(res, "kws_micronet_m")["verdict"], "NO_SIGNIFICANT_EFFECT")
        res["x3_kws_B1"] = self.r(101001, 1, 300)
        self.assertEqual(X.h_o(res, "kws_micronet_m")["verdict"], "SCHEDULE_EFFECT_OBSERVED")
        res = {"x3_kws_B0": self.r(100000, 1, 900), "x3_kws_B1": self.r(101500, 1, 700)}
        self.assertEqual(X.h_o(res, "kws_micronet_m")["verdict"], "NO_SIGNIFICANT_EFFECT")
        res["x3_kws_B1"] = self.r(150000, 1, 0, "UNSTABLE")
        self.assertEqual(X.h_o(res, "kws_micronet_m")["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_vela(self):
        self.assertEqual((X.vela_cls(0.89), X.vela_cls(0.9), X.vela_cls(1.1), X.vela_cls(1.11)),
                         ("OVER", "AGREE", "AGREE", "UNDER"))
        g = X.vela_groups(VELA, "kws_micronet_m", {"G_0": [0], "G_V": [2, 4, 6], "G_R": [1, 3, 5, 7, 8, 9, 10, 11, 12]})
        self.assertEqual(g["groups"]["G_0"]["op_cycles"], 23261.0)               # per-layer row 0
        self.assertEqual(g["groups"]["G_V"]["op_cycles"], 3 * 7812.0)
        self.assertEqual(g["groups"]["G_0"]["bound"], ["NPU"])
        self.assertEqual(sum(x["op_cycles"] for x in g["groups"].values()), 102248.0)   # = cycles_total
        self.assertEqual((g["cycles_total"], g["cycles_npu"]), (102248.0, 86324.0))

    def test_tflite_groups(self):
        m = json.loads((WL / X.MANIFEST).read_text())
        self.assertEqual(X.tflite_groups(m["x3_kws_B0"]), {"G_0": [0], "G_V": [2, 4, 6], "G_R": [1, 3, 5, 7, 8, 9, 10, 11, 12]})
        self.assertEqual(X.tflite_groups(m["x3_ad_B0"])["G_V"], [2, 4, 6, 8])


GOOD = {"x3_kws_B0": (91000, 56450), "x3_kws_B1": (95000, 56450), "x3_kws_B2": (20000, 11700),
        "x3_kws_B3": (30000, 26090), "x3_kws_B4": (45000, 18660),
        "x3_ad_B0": (146000, 93672), "x3_ad_B1": (150000, 93672), "x3_ad_B2": (60000, 60480),
        "x3_ad_B3": (40000, 20000), "x3_ad_B4": (50000, 13192)}


class Judge(Base):
    def run_all(self, vals):
        for k, (n, m) in vals.items():
            write_boot(self.root, k, ev(n, m, KWS["dpu"] if k == "x3_kws_B0" else m))
        return X.judge(self.root, WL, self.m7, CAPS, VELA)

    def test_good(self):
        s = self.run_all(GOOD)
        self.assertEqual(s["verdicts"], dict(measurement="VALID", baseline_reproducibility=dict(kws_micronet_m="REPRODUCED", ad_medium_int8="REPRODUCED"),
                                             pmu_mask_functionality="FUNCTIONAL", group_attribution="VALIDATED",
                                             compute_explanation="RESIDUAL_REDUCED", serialization="SCHEDULE_EFFECT_OBSERVED",
                                             vela_fidelity="GROUP_DISCREPANCY_REMAINS"))
        self.assertEqual(s["hypotheses"]["h_a"]["verdict"], "H_A1_SUPPORTED")
        self.assertEqual(s["vela"]["kws_micronet_m"]["groups"]["G_V"]["cls"], "OVER")      # 20000 / 23436

    def test_residual_unchanged(self):
        v = dict(GOOD, x3_ad_B2=(60000, 70000), x3_ad_B4=(50000, 3672))
        s = self.run_all(v)
        self.assertEqual((s["verdicts"]["group_attribution"], s["verdicts"]["compute_explanation"]),
                         ("VALIDATED", "RESIDUAL_UNCHANGED"))

    def test_partial(self):
        v = dict(GOOD, x3_kws_B2=(20000, 13000), x3_kws_B4=(45000, 17360))    # kws G_V off h1uc by 11 %
        s = self.run_all(v)
        self.assertEqual(s["verdicts"]["group_attribution"], "PARTIALLY_VALIDATED")
        v = dict(GOOD, x3_ad_B4=(60000, 13192))                               # ad partition fails
        shutil.rmtree(self.root)
        self.assertEqual(self.run_all(v)["verdicts"]["group_attribution"], "PARTIALLY_VALIDATED")

    def test_invalid(self):
        v = dict(GOOD, x3_kws_B3=(30000, 27000), x3_kws_B4=(45000, 17750))   # op0 window != isolated F5
        s = self.run_all(v)
        self.assertEqual(s["verdicts"], dict(measurement="MEASUREMENT_INVALID", baseline_reproducibility=dict(kws_micronet_m="REPRODUCED", ad_medium_int8="REPRODUCED"),
                                             pmu_mask_functionality="FUNCTIONAL", group_attribution="INVALID",
                                             compute_explanation="INSUFFICIENT_EVIDENCE",
                                             serialization="SCHEDULE_EFFECT_OBSERVED", vela_fidelity="INSUFFICIENT_EVIDENCE"))

    def test_improved_and_no_effect(self):
        v = dict(GOOD, x3_kws_B1=(102248, 56450), x3_kws_B2=(23436, 11700), x3_kws_B3=(23261, 26090),
                 x3_kws_B4=(55551, 18660), x3_ad_B1=(148328, 93672), x3_ad_B2=(71857, 60480), x3_ad_B3=(21874, 20000),
                 x3_ad_B4=(54597, 13192))
        s = self.run_all(v)
        self.assertEqual(s["verdicts"]["vela_fidelity"], "GROUP_FIDELITY_IMPROVED")
        v2 = dict(GOOD, x3_kws_B1=(91000, 56450), x3_kws_B4=(41000, 18660), x3_ad_B1=(146000, 93672),
                  x3_ad_B4=(46000, 13192))
        shutil.rmtree(self.root)
        s = self.run_all(v2)
        self.assertEqual(s["verdicts"]["serialization"], "NO_SIGNIFICANT_EFFECT")
        self.assertEqual(s["verdicts"]["vela_fidelity"], "GROUP_DISCREPANCY_REMAINS")   # not closer than original

    def test_serial_mixed_insufficient(self):
        v = dict(GOOD, x3_kws_B1=(91000, 56450), x3_kws_B4=(41000, 18660))
        for k, (n, m) in v.items():
            write_boot(self.root, k, ev(n, m, KWS["dpu"] if k == "x3_kws_B0" else m),
                       per_run=(lambda s, r: {35: 160000} if s == 2 else None) if k == "x3_ad_B1" else None)
        s = X.judge(self.root, WL, self.m7, CAPS, VELA)
        self.assertEqual((s["hypotheses"]["h_o"]["kws_micronet_m"]["verdict"], s["hypotheses"]["h_o"]["ad_medium_int8"]["verdict"]),
                         ("NO_SIGNIFICANT_EFFECT", "INSUFFICIENT_EVIDENCE"))
        self.assertEqual(s["verdicts"]["serialization"], "INSUFFICIENT_EVIDENCE")

    def test_groups_agree_but_not_closer(self):
        write_m7(self.m7, "kws_micronet_m", 100000, KWS["mac"], KWS["dpu"])
        f = 1.0465                                                            # serial 4.65 % over Vela total
        v = dict(GOOD, x3_kws_B0=(100000, 56450), x3_kws_B1=(round(102248 * f), 56450),
                 x3_kws_B2=(round(23436 * f), 11700), x3_kws_B3=(round(23261 * f), 26090),
                 x3_kws_B4=(round(102248 * f) - round(23436 * f) - round(23261 * f), 18660),
                 x3_ad_B1=(148328, 93672), x3_ad_B2=(71857, 60480), x3_ad_B3=(21874, 20000), x3_ad_B4=(54597, 13192))
        s = self.run_all(v)
        self.assertTrue(all(g["cls"] == "AGREE" for m in s["vela"].values() for g in m["groups"].values()))
        self.assertEqual(s["verdicts"]["group_attribution"], "VALIDATED")
        self.assertEqual(s["verdicts"]["vela_fidelity"], "GROUP_DISCREPANCY_REMAINS")   # kws: 0.978 -> 1.0465

    def test_partial_valid_and_g1(self):
        for k, (n, m) in GOOD.items():
            write_boot(self.root, k, ev(n, m, KWS["dpu"] if k == "x3_kws_B0" else m),
                       per_run=(lambda s, r: {35: 98000} if s == 2 else None) if k == "x3_ad_B3" else None)
        s = X.judge(self.root, WL, self.m7, CAPS, VELA)
        self.assertEqual(s["results"]["x3_ad_B3"]["status"], "UNSTABLE")
        self.assertEqual(s["verdicts"]["measurement"], "MEASUREMENT_INVALID")   # GS: a serial boot not VALID
        shutil.rmtree(self.root)
        s = self.run_all(dict(GOOD, x3_ad_B0=(150000, 93672)))                  # ad B0 not reproduced
        self.assertEqual(s["gates"]["ad_medium_int8"]["g1"]["verdict"], "FAIL")
        self.assertEqual(s["verdicts"]["baseline_reproducibility"],
                         dict(kws_micronet_m="REPRODUCED", ad_medium_int8="NOT_REPRODUCED"))
        self.assertEqual(s["verdicts"]["measurement"], "MEASUREMENT_INVALID")

    def test_mask_functionality(self):
        inert = dict(GOOD, x3_kws_B2=(95000, 56450), x3_kws_B3=(95000, 56450), x3_kws_B4=(95000, 56450))
        s = self.run_all(inert)
        self.assertEqual((s["verdicts"]["pmu_mask_functionality"], s["verdicts"]["group_attribution"]),
                         ("NOT_FUNCTIONAL", "INVALID"))
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS))
        s = X.judge(self.root, WL, self.m7, CAPS, VELA)
        self.assertEqual(s["verdicts"]["pmu_mask_functionality"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(s["verdicts"]["baseline_reproducibility"],
                         dict(kws_micronet_m="REPRODUCED", ad_medium_int8="INSUFFICIENT_EVIDENCE"))
        shutil.rmtree(self.root)                                              # only M2 broken (an empty window)
        s = self.run_all(dict(GOOD, x3_kws_B2=(0, 0), x3_kws_B4=(65000, 30360)))
        self.assertEqual(s["gates"]["kws_micronet_m"]["gm"]["m3"][35]["holds"], True)
        self.assertEqual(s["verdicts"]["pmu_mask_functionality"], "NOT_FUNCTIONAL")
        shutil.rmtree(self.root)                                              # only M3 broken -> not functional
        s = self.run_all(dict(GOOD, x3_kws_B4=(50000, 18660)))
        self.assertEqual(s["verdicts"]["pmu_mask_functionality"], "NOT_FUNCTIONAL")

    def test_cli_rc(self):
        cp = self.tmp / "caps.json"
        cp.write_text(json.dumps(CAPS))
        a = lambda *x: X.main(["x", x[0], str(self.root), str(WL), str(self.m7), str(cp), *x[1:]])  # noqa: E731
        write_boot(self.root, "x3_kws_B0", ev(**KWS), per_run=lambda s, r: {35: 96000} if s == 2 else None)
        self.assertEqual(a("boot-check", "x3_kws_B0"), 0)                      # UNSTABLE B0: G1 decides
        self.assertEqual(a("gate-g1", "kws_micronet_m"), 1)
        shutil.rmtree(self.root)
        write_boot(self.root, "x3_kws_B0", ev(**KWS))
        self.assertEqual((a("boot-check", "x3_kws_B0"), a("gate-g1", "kws_micronet_m")), (0, 0))
        write_boot(self.root, "x3_kws_B1", ev(95000, 56450, 56450), per_run=lambda s, r: {35: 99900} if s == 2 else None)
        self.assertEqual(a("boot-check", "x3_kws_B1"), 1)                      # serial boot must be VALID
        self.assertEqual(a("boot-check", "x3_kws_B2"), 1)                      # UNMEASURED
        shutil.rmtree(self.root)
        for k in ("x3_kws_B0", "x3_kws_B1", "x3_kws_B2", "x3_kws_B3", "x3_kws_B4"):
            write_boot(self.root, k, ev(GOOD[k][0], GOOD[k][1], GOOD[k][1]))
        self.assertEqual(a("gate-gm", "kws_micronet_m"), 0)
        write_boot(self.root, "x3_kws_B3", ev(95000, 56450, 56450))
        self.assertEqual(a("gate-gm", "kws_micronet_m"), 1)


class Constants(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(X.PASS_C, [35, 131, 142, 387, 640, 642, 656, 658])
        self.assertEqual(list(X.BOOT.values()), list(range(487, 497)))
        self.assertEqual(X.DETERMINISTIC, (48, 51, 128, 130, 132, 135, 384, 386, 391, 640, 642, 656, 658))
        self.assertEqual((X.NPU_TOL, X.EV_TOL, X.M2_MAX, X.F5_MAC, X.F5_TOL), (0.01, 0.01, 0.95, 26090.0, 0.01))
        self.assertEqual((X.H1UC_KWS, X.H1UC_AD, X.H1UC_TOL, X.VELA_LO, X.VELA_HI), (11700.0, 60480.0, 0.05, 0.9, 1.1))
        self.assertEqual(X.IMAGE["bram_sha256"][:8], "9b1844a3")
        self.assertEqual((X.SCHEMA, X.RECORD_FIELDS, X.EXT_RLATENCY, X.MASK_EN), (5, 92, 500, 0x8))


if __name__ == "__main__":
    unittest.main()
