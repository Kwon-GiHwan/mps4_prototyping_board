"""stage4aoe.py: AO pass decoding, TRM rates, golden exactness, the selection rule on the compiled workloads, the
prediction table, and the board judgement (rate classes, proportionality, validity) on synthetic and archived data.
Expected numbers are typed here, never read back from the module."""
import copy, csv, json, pathlib, shutil, sys, tempfile, unittest
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "lib"))
import stage4aoe as E

WL = REPO / "evidence/stage4aoe/workloads"
AO_RAW = REPO / "evidence/stage4ao/raw"
AO_WL = REPO / "evidence/stage4ao/workloads"


class Decode(unittest.TestCase):
    def test_precision_bits(self):
        self.assertEqual(E.precision_bits(257), 8)        # elementwise OFM (signed, global scale)
        self.assertEqual(E.precision_bits(32833), 8)      # chained Conv OFM
        self.assertEqual(E.precision_bits(3), 16)         # INT16 Conv OFM
        self.assertEqual(E.precision_bits(5), 32)
        self.assertIsNone(E.precision_bits(None))

    def test_passes(self):
        aoe = dict(kernels=[dict(kind="CONV", ifm_storage=0, ofm_storage=2, ofm_precision=32833, activation=0),
                            dict(kind="ELEMENTWISE", ifm_storage=2, ofm_storage=0, ofm_precision=257, activation=4),
                            dict(kind="ELEMENTWISE", ifm_storage=0, ofm_storage=0, ofm_precision=3, activation=None)],
                   geometry=[dict(h=2, w=3, c=4), dict(h=2, w=3, c=4), dict(h=1, w=1, c=5)])
        p = E.passes(aoe)
        self.assertEqual([(x["src"], x["dst"], x["ofm_bits"], x["lut"], x["elements"]) for x in p],
                         [("AB", "CB", 8, False, 24), ("CB", "OB", 8, True, 24), ("IFM", "OB", 16, False, 5)])
        self.assertEqual([E.trm_rate(x) for x in p], [16, 16, None])


def aoe_of(**kw):
    base = dict(cpu_fallback=[], pack_rc=0, reference=dict(opt_vs_ref=0))
    return dict(base, **kw)


class Selection(unittest.TestCase):
    P8 = [dict(ofm_bits=8)]

    def test_rules(self):
        self.assertEqual(E.select(aoe_of(), self.P8)["verdict"], "SELECTED")
        self.assertEqual(E.select(aoe_of(reference=dict(opt_vs_ref=3)), self.P8)["verdict"], "NEEDS_GOLDEN_RULE")
        self.assertEqual(E.select(aoe_of(cpu_fallback=["TANH"]), self.P8)["why"], ["cpu_fallback"])
        self.assertEqual(E.select(aoe_of(pack_rc=1), self.P8)["why"], ["pack_failed"])
        self.assertEqual(E.select(aoe_of(), [dict(ofm_bits=16)])["why"], ["path_not_covered"])
        self.assertEqual(E.select(aoe_of(pack_rc=1, reference=dict(opt_vs_ref=3)), self.P8)["verdict"], "EXCLUDED")


class Static(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.s = E.static(str(WL), cls.d)
        cls.p = E.predict(str(WL), cls.d)["configs"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_selection(self):
        sel = {c: r["selection"]["verdict"] for c, r in self.s.items()}
        self.assertEqual({sel[c] for c in E.GROUP_A}, {"SELECTED"})
        self.assertEqual(sel["s4aoe_add_mul_h24"], "SELECTED")
        for c in ("s4aoe_conv_add_h24", "s4aoe_tanh_h24", "s4aoe_logistic_h24"):
            self.assertEqual(sel[c], "NEEDS_GOLDEN_RULE")
        self.assertEqual(self.s["s4aoe_conv_add_h24"]["reference"]["opt_vs_ref"], 48)

    def test_paths(self):
        s = self.s
        self.assertEqual(s["s4aoe_add_h72"]["logical_elements"], 72 * 24 * 96)
        self.assertEqual(s["s4aoe_add_mul_h24"]["logical_elements"], 2 * 55296)
        self.assertEqual([(p["src"], p["dst"]) for p in s["s4aoe_add_mul_h24"]["passes"]], [("IFM", "CB"), ("CB", "OB")])
        self.assertEqual([p["elements"] for p in s["s4aoe_conv_add_h24"]["passes"]], [9216, 9216, 46080, 46080])
        self.assertTrue(s["s4aoe_tanh_h24"]["lut"]); self.assertFalse(s["s4aoe_tanh_h24"]["chained"])
        self.assertTrue(s["s4aoe_conv_add_h24"]["chained"])
        self.assertEqual(s["s4aoe_abs_h24"]["n_ifm"], 1); self.assertEqual(s["s4aoe_mul_h24"]["n_ifm"], 2)

    def test_predict(self):
        self.assertEqual(self.p["s4aoe_add_h24"]["P_TRM"], 3456)
        self.assertAlmostEqual(self.p["s4aoe_add_h24"]["P_CONV"], 55296 / 15.605)
        self.assertEqual(self.p["s4aoe_add_mul_h24"]["P_TRM"], 6912)
        self.assertEqual(self.p["s4aoe_tanh_h24"]["P_VELA"], 4224)


class Rates(unittest.TestCase):
    def test_rate_class(self):
        self.assertEqual(E.rate_class(16.0), "NOMINAL_16")
        self.assertEqual(E.rate_class(15.85), "NOMINAL_16")          # inside 1 % below 16
        self.assertEqual(E.rate_class(16.15), "NOMINAL_16")
        self.assertEqual(E.rate_class(16.2), "ABOVE_NOMINAL")
        self.assertEqual(E.rate_class(15.605), "CONV_LIKE")
        self.assertEqual(E.rate_class(15.75), "CONV_LIKE")
        self.assertEqual(E.rate_class(15.83), "BETWEEN")
        self.assertEqual(E.rate_class(15.44), "BELOW_CONV")

    def test_stability(self):
        m = {"A_64": 3500, "A_64_range": 70, "A_35": 10000, "B_35": 10500, "A_35_range": 0, "B_35_range": 0}
        self.assertTrue(E.stability(m))
        self.assertFalse(E.stability(dict(m, A_64_range=71)))
        self.assertTrue(E.stability(dict(m, A_64=1000, A_64_range=50)))
        self.assertFalse(E.stability(dict(m, A_64=1000, A_64_range=51)))
        self.assertFalse(E.stability(dict(m, B_35=10501)))
        self.assertTrue(E.stability(dict(m, B_35=12000, A_35_range=1000, B_35_range=1000)))
        self.assertFalse(E.stability(dict(m, A_64=None)))


def res(ao, verdict="VALID", stable=True):
    return dict(verdict=verdict, stable=stable, metrics={"A_64": ao})


class Verdicts(unittest.TestCase):
    def test_rate_verdict(self):
        self.assertEqual(E.rate_verdict(res(3456), 55296)["verdict"], "NOMINAL_16")
        self.assertEqual(E.rate_verdict(res(3543.5), 55296)["verdict"], "CONV_LIKE")
        self.assertEqual(E.rate_verdict(res(3456, verdict="INVALID"), 55296)["verdict"], "INVALID")
        self.assertEqual(E.rate_verdict(dict(verdict="NOT_MEASURED"), 55296)["verdict"], "NOT_MEASURED")
        self.assertEqual(E.rate_verdict(res(3456, stable=False), 55296)["verdict"], "MEASUREMENT_UNSTABLE")
        self.assertAlmostEqual(E.rate_verdict(res(6912), 110592)["rate"], 16)

    def test_prop(self):
        self.assertEqual(E.prop_verdict(res(3500), res(10500))["verdict"], "PROPORTIONAL")
        self.assertEqual(E.prop_verdict(res(3500), res(10709))["verdict"], "PROPORTIONAL")     # just inside +2 %
        self.assertEqual(E.prop_verdict(res(3500), res(10711))["verdict"], "NOT_PROPORTIONAL")
        self.assertEqual(E.prop_verdict(res(3500), res(10289))["verdict"], "NOT_PROPORTIONAL")
        r = E.prop_verdict(res(3456 + 80), res(10368 + 80))
        self.assertAlmostEqual(r["slope_vs_ideal"], 1); self.assertAlmostEqual(r["intercept"], 80)
        self.assertEqual(E.prop_verdict(res(3500, verdict="INVALID"), res(10500))["verdict"], "INVALID")
        self.assertEqual(E.prop_verdict(res(3500), res(10500, stable=False))["verdict"], "MEASUREMENT_UNSTABLE")


class Board(unittest.TestCase):
    """config_result on the archived Stage 4AO boot 380 (H24, golden = the tflite output it carries)."""
    CFG = "s4ao_conv1x1_h24"

    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp()); self.wl = self.d / "wl"; self.wl.mkdir()
        for suf in (".drwl", ".drwl.tflite_ofm.bin"):
            shutil.copy(AO_WL / f"{self.CFG}{suf}", self.wl / f"{self.CFG}{suf}")
        shutil.copy(AO_WL / f"{self.CFG}.drwl.tflite_ofm.bin", self.wl / f"{self.CFG}.ref_ofm.bin")
        self.root = AO_RAW / "evsweep_s4ao_run"; self.caps = str(AO_RAW / "evsweep_s4ao/ref/capabilities.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_valid(self):
        r = E.config_result(self.root, self.wl, self.CFG, self.caps)
        self.assertEqual(r["verdict"], "VALID"); self.assertTrue(r["stable"])
        self.assertEqual(r["metrics"]["A_64"], 3534)
        self.assertEqual(E.boot_check(str(self.root), str(self.wl), self.CFG, self.caps)["verdict"], "PASS")
        self.assertEqual(E.config_result(self.root, self.wl, "nope", self.caps)["verdict"], "NOT_MEASURED")

    def test_golden_byte(self):
        g = bytearray((self.wl / f"{self.CFG}.ref_ofm.bin").read_bytes()); g[100] ^= 1
        (self.wl / f"{self.CFG}.ref_ofm.bin").write_bytes(bytes(g))
        r = E.config_result(self.root, self.wl, self.CFG, self.caps)
        self.assertFalse(r["output_exact"]); self.assertEqual(r["verdict"], "INVALID")
        self.assertEqual(E.boot_check(str(self.root), str(self.wl), self.CFG, self.caps)["verdict"], "FAIL")

    def test_other_gates(self):
        with mock.patch.object(E.K, "identity", return_value=dict(ok=False)):
            self.assertEqual(E.config_result(self.root, self.wl, self.CFG, self.caps)["verdict"], "INVALID")
        with mock.patch.object(E.AO, "workload_ok", return_value=False):
            self.assertEqual(E.config_result(self.root, self.wl, self.CFG, self.caps)["verdict"], "INVALID")
        real = E.K.summary_of

        def three(folder, n):
            s = real(folder, n); s["runs"] = {1: s["runs"][1][:3], 2: s["runs"][2]}; return s
        with mock.patch.object(E.K, "summary_of", side_effect=three):
            self.assertEqual(E.config_result(self.root, self.wl, self.CFG, self.caps)["verdict"], "INVALID")

    def test_output_rows(self):
        f = self.d / "wfe"; shutil.copytree(self.root / "conds" / self.CFG / "wfe", f)
        g = (self.wl / f"{self.CFG}.ref_ofm.bin").read_bytes()
        self.assertTrue(E.output_exact(f, g, {}))
        rows = list(csv.DictReader(open(f / "runs.csv")))
        rows[-1]["ofm_mismatch_count"] = "1"
        with open(f / "runs.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        self.assertFalse(E.output_exact(f, g, {}))
        (f / "output.bin").unlink()
        self.assertFalse(E.output_exact(f, g, {}))

    def test_repro_gate(self):
        root = AO_RAW / "evsweep_s4ao_run"; ref = root / "conds" / E.REPRO_CFG / "wfe"
        self.assertEqual(E.repro_gate(str(root), str(AO_WL), str(ref), self.caps)["verdict"], "PASS")
        with mock.patch.object(E.K, "reproduce", return_value=dict(ok=False)):
            self.assertEqual(E.repro_gate(str(root), str(AO_WL), str(ref), self.caps)["verdict"], "FAIL")
        with mock.patch.object(E.AO, "config_result", return_value=dict(verdict="INVALID")):
            self.assertEqual(E.repro_gate(str(root), str(AO_WL), str(ref), self.caps)["verdict"], "FAIL")
        real = E.K.summary_of
        calls = []
        def shifted(folder, n):
            s = real(folder, n); calls.append(folder)
            if len(calls) == 2:                     # 1 = config_result, 2 = the campaign summary, 3 = the reference
                s["metrics"] = dict(s["metrics"], A_64=s["metrics"]["A_64"] + 40)
            return s
        with mock.patch.object(E.K, "summary_of", side_effect=shifted), \
                mock.patch.object(E.K, "reproduce", return_value=dict(ok=True)):
            self.assertEqual(E.repro_gate(str(root), str(AO_WL), str(ref), self.caps)["verdict"], "FAIL")

    def test_judge(self):
        d = tempfile.mkdtemp()
        try:
            pred = E.predict(str(WL), d)
            n = {c: v["logical_elements"] for c, v in pred["configs"].items()}
            fake = {c: dict(res(n[c] / 16), stable=True) for c in E.ALL}
            fake["s4aoe_abs_h72"] = dict(res(n["s4aoe_abs_h72"] / 15.605), stable=True)
            with mock.patch.object(E, "config_result", side_effect=lambda r, w, c, *x: copy.deepcopy(fake[c])):
                s = E.judge("x", str(WL), str(pathlib.Path(d) / "predictions.json"), d)
            self.assertEqual(s["rates"]["s4aoe_add_h24"]["verdict"], "NOMINAL_16")
            self.assertEqual(s["rates"]["s4aoe_add_mul_h24"]["verdict"], "NOMINAL_16")   # 2N logical elements
            self.assertEqual(s["rates"]["s4aoe_abs_h72"]["verdict"], "CONV_LIKE")
            self.assertEqual(s["proportional"]["add"]["verdict"], "PROPORTIONAL")
            self.assertEqual(s["proportional"]["abs"]["verdict"], "NOT_PROPORTIONAL")
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
