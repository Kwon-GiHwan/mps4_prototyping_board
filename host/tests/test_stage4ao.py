"""stage4ao.py: AO metrics and models, the Phase A re-analysis of the archived Stage 4K RUNs, the static
comparability / Phase C selection rules on the compiled workloads, and the board judgement on synthetic results.
Expected numbers are typed here (recomputed independently from runs.csv), never read back from the module."""
import copy, json, pathlib, shutil, struct, sys, tempfile, unittest
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "lib"))
import stage4ao as A

WL = REPO / "evidence/stage4ao/workloads"
WL4K = REPO / "evidence/stage4k/workloads"
K4 = REPO / "evidence/stage4k/raw/evsweep_s4k_run"
H = {h: f"s4ao_conv1x1_h{h}" for h in (12, 24, 36, 42, 48, 54, 72)}


class Definitions(unittest.TestCase):
    def test_ao_metrics(self):
        m = A.ao_metrics(3540.5, 55296)
        self.assertEqual(m["ao_ideal_cycles"], 3456)
        self.assertEqual(m["ao_cycle_residual"], 84.5)
        self.assertAlmostEqual(m["ao_observed_throughput"], 55296 / 3540.5)
        self.assertAlmostEqual(m["ao_relative_throughput"], 55296 / 3540.5 / 16)
        self.assertNotIn("ao_cycle_residual", A.ao_metrics(None, 100))

    def test_c16_and_tol(self):
        self.assertEqual(A.c16(24, 24, 97), 24 * 24 * 112)
        self.assertEqual(A.c16(56, 56, 144), 56 * 56 * 144)
        self.assertEqual(A.tol(1000), 25)
        self.assertEqual(A.tol(5000), 50)

    def test_models(self):
        m = A.models(110592, 30, 16, 79.5, 7680.0)
        self.assertEqual(m, dict(M1=6912, M2=6991.5, M3=6912 + 79.5 * 30 / 16, M4=7680.0))

    def test_slope(self):
        b, a = A.slope([1, 2, 3], [12, 14, 16])
        self.assertAlmostEqual(b, 2); self.assertAlmostEqual(a, 10)

    def test_spearman(self):
        self.assertAlmostEqual(A.spearman([1, 2, 3], [3, 2, 1]), -1)
        self.assertAlmostEqual(A.spearman([1, 2, 3], [10, 20, 30]), 1)


class PhaseA(unittest.TestCase):
    """The archived RUNs: medians recomputed by hand from runs.csv (measured RUNs 2-5 of pass A)."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.r = A.phase_a(cls.d)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_table(self):
        t = {r["config"]: r for r in self.r["table"]}
        self.assertEqual(len(t), 10)
        self.assertEqual(t["s4_conv_base"]["ao_active"], 3540.5)
        self.assertEqual(t["s4k_conv3x3_cin40"]["ao_active"], 3484.5)
        self.assertEqual(t["s4k_conv3x3_cin48"]["ao_range"], 50)
        self.assertEqual(t["s4k_conv3x3_cin64"]["mac_active"], 41472)
        self.assertEqual({r["ext_wr_beats"] for r in t.values()}, {3456})
        self.assertEqual(self.r["descriptive"]["ao_spread"], 78)

    def test_calibration(self):
        c = self.r["calibration"]
        self.assertEqual(c["ao_active"], dict(stage4=3540, stage4c1=3534, stage4c2=3533.5, placement_a=3535.5,
                                              stage4k=3540.5))
        self.assertEqual(c["c0"], 79.5)

    def test_other_ofm(self):
        o = {(r["config"], r["folder"].split("/raw")[0]): r for r in self.r["other_ofm_post_hoc"]}
        cout97 = o[("s4c_conv_cout97", "evidence/stage4c1")]
        self.assertEqual(cout97["ao_active"], 4127.5)
        self.assertEqual(cout97["c16"]["ao_cycle_residual"], 4127.5 - 24 * 24 * 112 / 16)
        self.assertEqual(o[("s4_dw_base", "evidence/stage4")]["ao_active"], 28491)
        self.assertEqual({r["label"] for r in o.values()}, {"POST_HOC_DESCRIPTIVE"})


class Static(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.s = A.static(str(WL), cls.d)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_base_is_ref(self):
        self.assertEqual(self.s["base_equals_ref"], dict(cms=True, cpu_ofm=True))

    def test_base_differs(self):
        d = pathlib.Path(tempfile.mkdtemp())
        try:
            wl = d / "wl"
            shutil.copytree(WL, wl)
            ofm = bytearray((wl / f"{A.REF_H}.drwl.tflite_ofm.bin").read_bytes()); ofm[0] ^= 1
            (wl / f"{A.REF_H}.drwl.tflite_ofm.bin").write_bytes(bytes(ofm))
            self.assertEqual(A.static(str(wl), str(d / "o"))["base_equals_ref"], dict(cms=True, cpu_ofm=False))
        finally:
            shutil.rmtree(d)

    def test_phase_b(self):
        self.assertEqual(self.s["phase_b_original"]["verdict"], "NEEDS_REVISION")
        self.assertEqual(self.s["phase_b_original"]["comparable"], [H[24], H[36]])
        self.assertEqual(self.s["phase_b_original"]["differing"][H[12]]["ofm_block"], "8x24x32")
        self.assertEqual(self.s["phase_b_original"]["differing"][H[48]]["ofm_block"], "10x8x96")
        self.assertEqual(self.s["phase_b_revision"]["verdict"], "COMPARABLE")
        self.assertEqual(len(self.s["phase_b_revision"]["comparable"]), 5)
        c = self.s["configs"]
        self.assertEqual((c[H[24]]["ofm_blocks"], c[H[72]]["ofm_blocks"]), (16, 48))
        self.assertEqual(c[H[72]]["n_ofm"], 72 * 24 * 96)

    def test_phase_c(self):
        self.assertTrue(self.s["phase_c"]["s4ao_act_none"]["selected"])
        self.assertEqual(self.s["phase_c"]["s4ao_act_none"]["diff"]["ops"], [294, 295])
        self.assertEqual(self.s["phase_c"]["s4ao_act_relu"]["diff"]["ops"], [295])

    def test_comparable_rules(self):
        st = copy.deepcopy(self.s["configs"])
        st[H[36]]["gate_b"] = False
        self.assertEqual(A.comparable(st, [H[24], H[36], H[54]])["verdict"], "NEEDS_REVISION")
        st = copy.deepcopy(self.s["configs"])
        self.assertEqual(A.comparable(st, [H[24], H[36], H[54]])["verdict"], "COMPARABLE")
        st[H[54]]["signature"]["ofm_slices"] = [32, 64]
        self.assertEqual(A.comparable(st, [H[24], H[36], H[54]])["verdict"], "NEEDS_REVISION")

    def test_phase_c_rules(self):
        base = copy.deepcopy(self.s["configs"])
        for field, val in (("gate_b", False), ("weight_lengths", [1, 2]), ("signature", {"ofm_block": "x"})):
            st = copy.deepcopy(base)
            st["s4ao_act_none"][field] = val
            self.assertFalse(A.phase_c_select(WL, st)["s4ao_act_none"]["selected"], field)

    def test_phase_c_extra_op(self):
        d = pathlib.Path(tempfile.mkdtemp())
        try:
            for f in (f"{A.REF_H}.drwl.cms.bin", "s4ao_act_relu.drwl.cms.bin"):
                shutil.copy(WL / f, d / f)
            s = bytearray((WL / "s4ao_act_none.drwl.cms.bin").read_bytes())
            import cms
            off = next(o for o, w, c, op in cms.instructions(bytes(s)) if c == 1)    # first cmd1 payload
            s[off + 4] ^= 1
            (d / "s4ao_act_none.drwl.cms.bin").write_bytes(bytes(s))
            r = A.phase_c_select(d, self.s["configs"])
            self.assertFalse(r["s4ao_act_none"]["selected"])
            self.assertTrue(r["s4ao_act_relu"]["selected"])
        finally:
            shutil.rmtree(d)


def w0(op, param):
    return struct.pack("<I", (param << 16) | op)


def w1(op, payload):
    return struct.pack("<II", (1 << 14) | op, payload)


class StreamDiff(unittest.TestCase):
    def test_aligned(self):
        a = w0(294, 0) + w1(36, 5) + w0(2, 0)
        b = w0(294, 7) + w1(36, 5) + w0(2, 0)
        d = A.stream_diff(a, b)
        self.assertTrue(d["aligned"]); self.assertEqual(d["ops"], [294])
        self.assertEqual(A.stream_diff(a, a)["ops"], [])
        self.assertEqual(A.stream_diff(a, w0(294, 0) + w1(36, 6) + w0(2, 0))["ops"], [36])

    def test_unaligned(self):
        a = w0(294, 0) + w0(2, 0)
        self.assertFalse(A.stream_diff(a, w0(295, 0) + w0(2, 0))["aligned"])
        self.assertFalse(A.stream_diff(a, a + w0(2, 0))["aligned"])


def res_of(ao, n_ofm, verdict="VALID", ao_range=10, a35=20000, b35=20000, r35=100):
    return dict(verdict=verdict, n_ofm=n_ofm, metrics={"A_64": ao, "A_64_range": ao_range, "A_35": a35, "B_35": b35,
                                                       "A_35_range": r35, "B_35_range": r35},
                stability=A.stability({"A_64": ao, "A_64_range": ao_range, "A_35": a35, "B_35": b35,
                                       "A_35_range": r35, "B_35_range": r35}))


SW = [H[24], H[36], H[54], H[72]]
N = {H[24]: 55296, H[36]: 82944, H[54]: 124416, H[72]: 165888}


class Judgement(unittest.TestCase):
    def res(self, rate=16, c=80, **kw):
        return {k: res_of(n / rate + c, n, **kw.get(k, {})) for k, n in N.items()}

    def test_stability(self):
        self.assertTrue(A.stability({"A_64": 3500, "A_64_range": 70, "A_35": 1, "B_35": 1})["ok"])
        self.assertFalse(A.stability({"A_64": 3500, "A_64_range": 71, "A_35": 1, "B_35": 1})["ao_range_ok"])
        self.assertTrue(A.stability({"A_64": 1000, "A_64_range": 50, "A_35": 1, "B_35": 1})["ao_range_ok"])
        self.assertFalse(A.stability({"A_64": 1000, "A_64_range": 51, "A_35": 1, "B_35": 1})["ao_range_ok"])
        m = {"A_64": 1000, "A_64_range": 0, "A_35": 20000, "B_35": 21000, "A_35_range": 10, "B_35_range": 10}
        self.assertTrue(A.stability(m)["pass_ab_ok"])
        self.assertFalse(A.stability(dict(m, B_35=21001))["pass_ab_ok"])
        self.assertTrue(A.stability(dict(m, B_35=23000, A_35_range=2000, B_35_range=1000))["pass_ab_ok"])

    def test_rate(self):
        self.assertEqual(A.rate_verdict(self.res(), SW, SW)["verdict"], "RATE_CONSISTENT")
        r = A.rate_verdict(self.res(), SW, SW)
        self.assertAlmostEqual(r["slope"], 1); self.assertAlmostEqual(r["intercept"], 80)
        self.assertEqual(A.rate_verdict(self.res(rate=14), SW, SW)["verdict"], "RATE_NOT_CONSISTENT")
        self.assertEqual(A.rate_verdict(self.res(rate=16 / 1.019), SW, SW)["verdict"], "RATE_CONSISTENT")
        self.assertEqual(A.rate_verdict(self.res(rate=16 / 1.021), SW, SW)["verdict"], "RATE_NOT_CONSISTENT")
        self.assertEqual(A.rate_verdict(self.res(rate=16 / 0.979), SW, SW)["verdict"], "RATE_NOT_CONSISTENT")

    def test_rate_gates(self):
        bad = {H[24]: dict(verdict="INVALID"), H[36]: dict(verdict="INVALID")}
        self.assertEqual(A.rate_verdict(self.res(**bad), SW, SW)["verdict"], "INVALID")
        self.assertEqual(A.rate_verdict(self.res(**{H[24]: dict(verdict="INVALID")}), SW, SW)["verdict"],
                         "RATE_CONSISTENT")
        self.assertEqual(A.rate_verdict(self.res(**{H[36]: dict(ao_range=500)}), SW, SW)["verdict"],
                         "MEASUREMENT_UNSTABLE")
        self.assertEqual(A.rate_verdict(self.res(), SW, [H[24], H[36]])["verdict"], "SCHEDULE_CONFOUNDED")

    def test_act(self):
        r = {A.REF_H: res_of(3540, 55296), "a": res_of(3570, 55296), "b": res_of(3580, 55296),
             "c": res_of(3540, 55296, verdict="INVALID"), "d": res_of(3540, 55296, ao_range=400)}
        self.assertEqual(A.act_verdict(r, "a")["verdict"], "RATE_CONSISTENT")
        self.assertEqual(A.act_verdict(r, "b")["verdict"], "RATE_NOT_CONSISTENT")
        self.assertEqual(A.act_verdict(r, "c")["verdict"], "INVALID")
        self.assertEqual(A.act_verdict(r, "d")["verdict"], "MEASUREMENT_UNSTABLE")

    def test_models_verdict(self):
        def r(**within):
            return {c: dict(models={m: dict(within=within.get(m, True) if c == H[72] else True)
                                    for m in ("M1", "M2", "M3", "M4")}) for c in SW}
        self.assertEqual(A.models_verdict(r(), SW)["verdict"], "BOTH_CONSISTENT")
        self.assertEqual(A.models_verdict(r(M3=False), SW)["verdict"], "M2_ONLY")
        self.assertEqual(A.models_verdict(r(M2=False), SW)["verdict"], "M3_ONLY")
        self.assertEqual(A.models_verdict(r(M2=False, M3=False), SW)["verdict"], "NEITHER")
        self.assertEqual(A.models_verdict(r(M1=False), SW)["per_model"]["M1"], "NOT_CONSISTENT")
        self.assertEqual(A.models_verdict(r(), SW[:2])["verdict"], "NOT_JUDGED")

    def test_base_vs_ref(self):
        r = {A.BASE: res_of(3540, 55296), A.REF_H: res_of(3570, 55296)}
        self.assertEqual(A.base_vs_ref(r)["verdict"], "SAME_WITHIN_TOL")
        r[A.REF_H] = res_of(3580, 55296)
        self.assertEqual(A.base_vs_ref(r)["verdict"], "DIFFERENT")
        r[A.BASE] = res_of(3540, 55296, verdict="INVALID")
        self.assertEqual(A.base_vs_ref(r)["verdict"], "NOT_JUDGED")

    def test_model_check(self):
        m = A.model_check(3540.5, dict(M1=3456, M2=3535.5))
        self.assertFalse(m["M1"]["within"]); self.assertTrue(m["M2"]["within"])
        self.assertEqual(m["M1"]["error"], 84.5)


class Board(unittest.TestCase):
    """config_result / repro_gate on the archived Stage 4K campaign (boot 369 = the same blob as boot 1 here)."""
    def test_config_result_valid(self):
        r = A.config_result(K4, WL4K, A.BASE)
        self.assertEqual(r["verdict"], "VALID"); self.assertEqual(r["output"], "PASS_EXACT")
        self.assertEqual(r["metrics"]["A_64"], 3540.5)
        self.assertEqual(A.config_result(K4, WL4K, "nope")["verdict"], "NOT_MEASURED")

    def test_config_result_invalid(self):
        with mock.patch.object(A.S4, "output_check", return_value=dict(verdict="PASS_TOLERANCE")):
            self.assertEqual(A.config_result(K4, WL4K, A.BASE)["verdict"], "INVALID")
        with mock.patch.object(A.K, "identity", return_value=dict(ok=False)):
            self.assertEqual(A.config_result(K4, WL4K, A.BASE)["verdict"], "INVALID")
        d = pathlib.Path(tempfile.mkdtemp())          # same model_len, other DRWL: only workload_sha256 catches it
        try:
            shutil.copytree(WL4K, d / "wl")
            shutil.copy(WL / "s4ao_conv1x1_h24.drwl", d / "wl" / f"{A.BASE}.drwl")
            r = A.config_result(K4, d / "wl", A.BASE)
            self.assertFalse(r["workload_sha256_ok"]); self.assertEqual(r["verdict"], "INVALID")
        finally:
            shutil.rmtree(d)
        real = A.K.summary_of

        def three_runs(folder, n):
            s = real(folder, n)
            s["runs"] = {1: s["runs"][1][:3], 2: s["runs"][2]}
            return s
        with mock.patch.object(A.K, "summary_of", side_effect=three_runs):
            self.assertEqual(A.config_result(K4, WL4K, A.BASE)["verdict"], "INVALID")

    def test_workload_rows(self):
        d = pathlib.Path(tempfile.mkdtemp())
        try:
            shutil.copytree(K4 / "conds" / A.BASE / "wfe", d / "wfe")
            drwl = WL4K / f"{A.BASE}.drwl"
            self.assertTrue(A.workload_ok(d / "wfe", drwl))
            t = (d / "wfe" / "runs.csv").read_text().splitlines()
            t[-1] = t[-1].replace("2681c566729ce568f4041df6a69d1b5c5c558d2172bb76b6d75ad64ca2b4f267", "0" * 64)
            (d / "wfe" / "runs.csv").write_text("\n".join(t) + "\n")
            self.assertFalse(A.workload_ok(d / "wfe", drwl))                  # one row of another blob
        finally:
            shutil.rmtree(d)

    def test_repro_gate(self):
        self.assertEqual(A.repro_gate(str(K4), str(WL4K))["verdict"], "PASS")
        d = pathlib.Path(tempfile.mkdtemp())                        # the board's staged copy of boot 369
        try:
            shutil.copytree(K4 / "conds" / A.BASE, d / "ref")
            self.assertEqual(A.repro_gate(str(K4), str(WL4K), str(d / "ref" / "wfe"))["verdict"], "PASS")
        finally:
            shutil.rmtree(d)
        b330 = REPO / "evidence/stage4/raw/conds/s4_conv_base/wfe"     # image 83398c7: other capabilities
        self.assertEqual(A.repro_gate(str(K4), str(WL4K), str(b330))["verdict"], "FAIL")
        with mock.patch.object(A.K, "reproduce", return_value=dict(ok=False)):
            self.assertEqual(A.repro_gate(str(K4), str(WL4K))["verdict"], "FAIL")
        real = A.config_result

        def far(root, wl, cfg, *x):
            r = real(root, wl, cfg, *x)
            r["metrics"] = dict(r["metrics"], A_64=r["metrics"]["A_64"] + 40)
            return r
        with mock.patch.object(A, "config_result", side_effect=far):
            self.assertEqual(A.repro_gate(str(K4), str(WL4K))["verdict"], "FAIL")
        with mock.patch.object(A, "config_result", return_value=dict(verdict="INVALID")):
            self.assertEqual(A.repro_gate(str(K4), str(WL4K))["verdict"], "FAIL")

    def test_boot_check(self):
        self.assertEqual(A.boot_check(str(K4), str(WL4K), A.BASE)["verdict"], "PASS")
        with mock.patch.object(A, "config_result", return_value=dict(gate_c="FAIL")):
            self.assertEqual(A.boot_check(str(K4), str(WL4K), A.BASE)["verdict"], "FAIL")

    def test_judge(self):
        d = tempfile.mkdtemp()
        try:
            pred = A.predict(str(WL), d)
            fake = {c: dict(res_of(n / 16 + 80, n), gate_c="PASS") for c, n in N.items()}
            fake["s4ao_act_none"] = dict(res_of(3540, 55296), gate_c="PASS")
            fake[A.BASE] = dict(res_of(3540.5, 55296), gate_c="PASS")
            with mock.patch.object(A, "config_result", side_effect=lambda root, wl, c, *x: copy.deepcopy(fake[c])), \
                    mock.patch.object(A, "repro_gate", return_value=dict(verdict="PASS")):
                s = A.judge("x", str(WL), str(pathlib.Path(d) / "predictions.json"), d, ",".join(SW), "s4ao_act_none")
            self.assertEqual(s["rq1"]["verdict"], "RATE_CONSISTENT")
            self.assertEqual(s["rq3"]["s4ao_act_none"]["verdict"], "RATE_CONSISTENT")
            m72 = s["configs"][H[72]]["models"]                 # AO 10448: M2 10447.5 in, M3 10606.5 out (tol 106)
            self.assertTrue(m72["M2"]["within"]); self.assertFalse(m72["M3"]["within"])
            self.assertEqual(s["rq2"]["verdict"], "M2_ONLY")
            self.assertEqual(s["base_vs_h24"]["verdict"], "SAME_WITHIN_TOL")
            with mock.patch.object(A, "config_result", side_effect=lambda root, wl, c, *x: copy.deepcopy(fake[c])), \
                    mock.patch.object(A, "repro_gate", return_value=dict(verdict="FAIL")):
                s = A.judge("x", str(WL), str(pathlib.Path(d) / "predictions.json"), d, ",".join(SW))
            self.assertTrue(s["rq1"]["verdict"].startswith("NOT_INTERPRETED"))
            self.assertEqual(s["rq2"]["verdict"], "NOT_JUDGED")
            self.assertEqual(pred["c0"], 79.5)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
