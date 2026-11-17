"""Stage 6B-E2E-B rules (evidence/stage6b/stage6be2eb/contract.md). Expected values typed by hand.

Board fixtures: E2D Amendment A boots 449 (REF), 453 / 454 (W1-P1 = B0) and 451 (W0-P1, a real placement-1 layout).
B3 has no board data before the session; its fixture is boot 453's folder rewritten to the B3 identity (DRWL digest,
placement 1, REGIONCFG 0x553, region 1 and the graph-IO bases moved to the SRAM arena). It tests the judge only.
"""
import csv
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis"), str(REPO / "host/lib")]
import stage6be2eb as E  # noqa: E402

WL = REPO / "evidence/stage6b/stage6be2eb/workloads"
RAW = REPO / "evidence/stage6b/stage6be2d/raw_a"
R500, R1000 = RAW / "evsweep_s6be2d_a_run_l500", RAW / "evsweep_s6be2d_a_run_l1000"
REF375 = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"
B3_SHA = "7b2cedd5d42dcf28547f35d0a049a9bfe5c3395eec40f33fd70592e125a13125"
SHIFT = 0x31076770 - 0x70016770


def res(npu, rng, mac=20736, status="VALID", ext_rd=27066.0, ext_wr=7872.0):
    return dict(status=status, reasons=[], traffic=dict(ext_rd_beats=ext_rd, ext_wr_beats=ext_wr),
                metrics=dict(npu_active=npu, npu_active_range=rng, mac_active=mac))


class Constants(unittest.TestCase):
    def test_frozen(self):
        self.assertEqual(E.ORDER, [("REF", 500, 458), ("B0", 500, 459), ("B3", 500, 460), ("B3", 1000, 461), ("B0", 1000, 462)])
        self.assertEqual(E.PLACEMENT, {"REF": 0, "B0": 0, "B3": 1})
        self.assertEqual(E.EXT_READ_EXPECTED["B3"], 11321.25)
        self.assertEqual(E.EXT_READ_EXPECTED["B0"], 27066.0)
        self.assertEqual(E.VELA_B0, {500: 53052, 1000: 83142})
        self.assertEqual(E.H1UC, 20736)
        self.assertEqual((E.EXT_TOL, E.NOISE_FLOOR), (0.01, 0.01))

    def test_manifest(self):
        m = json.loads((WL / E.MANIFEST).read_text())
        self.assertEqual({k: (v["boot"], v["config"], v["placement"], v["latency"]) for k, v in m.items()},
                         {"REF": (458, "s4c2_conv_cin48", 0, 500), "B0-L500": (459, "e2d_w1p1", 0, 500),
                          "B3-L500": (460, "e2eb_b3", 1, 500), "B3-L1000": (461, "e2eb_b3", 1, 1000),
                          "B0-L1000": (462, "e2d_w1p1", 0, 1000)})
        self.assertEqual(m["B0-L500"]["drwl_sha256"], "928296b1c235f1b22ce69d29900561d937818ffa655e1ec335e90ee3b1992c5f")
        self.assertEqual(m["B3-L500"]["drwl_sha256"], B3_SHA)
        self.assertEqual((m["B0-L500"]["arena_base"], m["B3-L500"]["arena_base"]), (0x70016770, 0x31076770))
        self.assertEqual(m["B3-L1000"]["image"]["bram_sha256"][:8], "fd478e2d")
        self.assertEqual(m["B3-L500"]["image"]["bram_sha256"][:8], "c80e77df")

    def test_b3_is_b0_with_word7(self):
        a, b = (WL / "e2d_w1p1.drwl").read_bytes(), (WL / "e2eb_b3.drwl").read_bytes()
        self.assertEqual(len(a), len(b))
        self.assertEqual([(i, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]], [(28, 0, 1)])


class Rules(unittest.TestCase):
    def test_tol(self):
        self.assertEqual(E.tol(100000, [300, 400]), 1000)
        self.assertEqual(E.tol(100000, [800, 400]), 1200)

    def test_io_placement(self):
        t = {500: 1000, 1000: 1000}
        self.assertEqual(E.io_placement({500: 1001, 1000: 5000}, t, True), "IO_PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.io_placement({500: -1001, 1000: -5000}, t, True), "IO_PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.io_placement({500: 1000, 1000: 5000}, t, True), "IO_PLACEMENT_EFFECT_NOT_RESOLVED")
        self.assertEqual(E.io_placement({500: 1001, 1000: -5000}, t, True), "IO_PLACEMENT_EFFECT_NOT_RESOLVED")
        self.assertEqual(E.io_placement({500: 9e9, 1000: 9e9}, t, False), "NOT_IDENTIFIABLE")

    def test_sensitivity(self):
        self.assertEqual(E.sensitivity(1001, 1000, True), "IO_SENSITIVITY_REDUCED")
        self.assertEqual(E.sensitivity(1000, 1000, True), "IO_SENSITIVITY_NOT_REDUCED")
        self.assertEqual(E.sensitivity(-5000, 1000, True), "IO_SENSITIVITY_NOT_REDUCED")
        self.assertEqual(E.sensitivity(9e9, 1000, False), "INSUFFICIENT_EVIDENCE")

    def test_residual_response(self):
        self.assertEqual(E.residual_response(1001, 1000, True), "RESIDUAL_RESPONSE_OBSERVED")
        self.assertEqual(E.residual_response(-1001, 1000, True), "RESIDUAL_RESPONSE_OBSERVED")
        self.assertEqual(E.residual_response(1000, 1000, True), "RESIDUAL_RESPONSE_NOT_OBSERVED")
        self.assertEqual(E.residual_response(9e9, 1, False), "NOT_EVALUABLE")

    def test_ext_within(self):
        x = 11321.25
        self.assertTrue(E.ext_within(x * 1.01, x))
        self.assertTrue(E.ext_within(x * 0.99, x))
        self.assertFalse(E.ext_within(x * 1.0101, x))
        self.assertFalse(E.ext_within(x * 0.9899, x))

    def test_residual_path(self):
        ok = dict(ext_rd_beats=11322.0, ext_wr_beats=0.0)
        self.assertEqual(E.residual_path({500: ok, 1000: ok}, 27066), "WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED")
        self.assertEqual(E.residual_path({500: ok}, 27066), "EXT_PATH_PARTIAL")                 # one latency only
        off = dict(ext_rd_beats=12000.0, ext_wr_beats=0.0)                                      # 6 % above
        self.assertEqual(E.residual_path({500: ok, 1000: off}, 27066), "EXT_PATH_PARTIAL")
        self.assertEqual(E.residual_path({500: ok, 1000: dict(ok, ext_wr_beats=1.0)}, 27066), "EXT_PATH_UNRESOLVED")
        self.assertEqual(E.residual_path({500: ok, 1000: dict(ok, ext_rd_beats=27066.0)}, 27066), "EXT_PATH_UNRESOLVED")
        self.assertEqual(E.residual_path({}, 27066), "EXT_PATH_UNRESOLVED")

    def test_validity(self):
        g = dict(verdict="PASS")
        r = {k: dict(status="VALID") for k in ("REF", "B0-L500", "B3-L500")}
        self.assertEqual(E.validity(g, r, {"B0-L500": True, "B3-L500": True}), "VALID")
        self.assertEqual(E.validity(g, r, {"B0-L500": True, "B3-L500": False}), "PARTIAL_VALID")
        self.assertEqual(E.validity(g, dict(r, **{"B3-L500": dict(status="UNSTABLE")}), {}), "PARTIAL_VALID")
        for s in ("CONFIG_MISMATCH", "UNMEASURED"):
            self.assertEqual(E.validity(g, dict(r, **{"B3-L500": dict(status=s)}), {}), "MEASUREMENT_INVALID")
        self.assertEqual(E.validity(dict(verdict="FAIL"), r, {}), "MEASUREMENT_INVALID")

    def test_mechanism(self):
        self.assertEqual(E.mechanism(), "MECHANISM_UNRESOLVED")

    def test_effects(self):
        r = {"B0-L500": res(100000, 1000), "B0-L1000": res(160000, 2000),
             "B3-L500": res(80000, 500), "B3-L1000": res(110000, 700)}
        e = E.effects(r, True)
        self.assertEqual(e["pe"], {500: 20000, 1000: 50000})
        self.assertEqual(e["tol_pe"], {500: 1500, 1000: 2700})
        self.assertEqual(e["le"], {"B0": 60000, "B3": 30000})
        self.assertEqual(e["tol_le"], {"B0": 3000, "B3": 1200})
        self.assertEqual((e["interaction"], e["tol_interaction"]), (30000, 4200))
        self.assertEqual(e["le_share_removed"], 0.5)
        self.assertEqual(E.effects(r, False), dict(usable=False))

    def test_expected_arena(self):
        self.assertEqual(E.expected_arena(0, 0x70000000, 0x16770, 0x31000000, 0x60000), 0x70016770)
        self.assertEqual(E.expected_arena(1, 0x70000000, 0x16770, 0x31000000, 0x60000), 0x31076770)
        self.assertEqual(E.expected_arena(0, 0x70000000, 0x16771, 0x31000000, 0x60000), 0x70016780)
        self.assertEqual(E.expected_arena(1, 0x70000000, 0x16770, 0x31000000, 0x60001), 0x31086770)


def caps(folder):
    return json.loads((folder.parent / "capabilities.json").read_text())


def recs(folder):
    return [x["record"] for x in json.loads((folder / "raw_runs.json").read_text())[1:]]


class Layout(unittest.TestCase):
    B0 = R500 / "conds/e2d_w1p1/wfe"
    W0P1 = R500 / "conds/e2d_w0p1/wfe"

    def test_real_layouts(self):
        self.assertTrue(E.layout(recs(self.B0), caps(self.B0), 0, 2, 1)["ok"])
        self.assertTrue(E.layout(recs(self.W0P1), caps(self.W0P1), 1, 1, 1)["ok"])

    def test_wrong_placement_layout(self):
        self.assertFalse(E.layout(recs(self.B0), caps(self.B0), 1, 2, 1)["checks"]["arena_where"])
        self.assertFalse(E.layout(recs(self.W0P1), caps(self.W0P1), 0, 1, 1)["checks"]["arena_inside"])

    def mod(self, folder, placement, n_in, change):
        r = [dict(x) for x in recs(folder)]
        for x in r:
            change(x)
        return E.layout(r, caps(folder), placement, n_in, 1)["checks"]

    def test_arena_overlaps_fast(self):          # SRAM conflict: region 1 placed inside the driver's fast memory
        def ch(x):
            x["arena_base"] = x["base1"] = 0x31010000
        c = self.mod(self.W0P1, 1, 1, ch)
        self.assertFalse(c["fast_disjoint"])
        self.assertFalse(c["arena_where"])

    def test_fast_disjoint_alone(self):
        def ch(x):
            x["base2"], x["base_size2"] = 0x310765f0, 0x1000   # fast scratch inside region 1
        c = self.mod(self.W0P1, 1, 1, ch)
        self.assertFalse(c["fast_disjoint"])
        self.assertFalse(c["fast_inside"])

    def test_fast_disjoint_only(self):           # fast scratch still inside fast memory, region 1 moved over it
        caps_ = dict(caps(self.W0P1), fast_size=0x200000)
        r = [dict(x, base2=0x31070000, base_size2=0x10000) for x in recs(self.W0P1)]
        c = E.layout(r, caps_, 1, 1, 1)["checks"]
        self.assertTrue(c["fast_inside"])
        self.assertFalse(c["fast_disjoint"])

    def test_arena_past_sram(self):
        def ch(x):
            x["arena_base"] = x["base1"] = 0x31300000
        c = self.mod(self.W0P1, 1, 1, ch)
        self.assertFalse(c["arena_inside"])

    def test_io_outside_arena(self):
        def ch(x):
            x["base3"] = 0x70000000
        self.assertFalse(self.mod(self.B0, 0, 2, ch)["io_in_arena"])

    def test_weights_not_ddr(self):
        def ch(x):
            x["base0"] = 0x31100000
        self.assertFalse(self.mod(self.B0, 0, 2, ch)["weights_ddr"])

    def test_region1_bigger_than_arena(self):
        def ch(x):
            x["base_size1"] = 0x200001
        self.assertFalse(self.mod(self.B0, 0, 2, ch)["arena_inside"])

    def test_empty(self):
        self.assertFalse(E.layout([], caps(self.B0), 0, 2, 1)["ok"])
        self.assertFalse(E.layout(recs(self.B0), {}, 0, 2, 1)["ok"])


def read_rows(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def make_b3(root: pathlib.Path, src_root: pathlib.Path, boot: int):
    """Boot 453/454's B0 folder rewritten to the B3 identity (judge fixture, not data)."""
    src, dst = src_root / "conds/e2d_w1p1", root / "conds/e2eb_b3"
    shutil.copytree(src, dst)
    f = dst / "wfe/raw_runs.json"
    runs = json.loads(f.read_text())
    for x in runs[1:]:
        r = x["record"]
        r["placement"], r["regioncfg_irq"] = 1, 0x553
        for k in ("arena_base", "base1", "base3", "base4", "base5"):
            r[k] = r[k] + SHIFT
    f.write_text(json.dumps(runs))
    p = dst / "wfe/runs.csv"
    rows = read_rows(p)
    for r in rows:
        r["workload_sha256"], r["host_boot_index"] = B3_SHA, str(boot)
    with open(p, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return dst / "wfe"


class Board(unittest.TestCase):
    """config_result on E2D boots under this stage's manifest (boot numbers mapped), plus the B3 fixture."""
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        shutil.copytree(WL, self.d / "wl")
        m = json.loads((WL / E.MANIFEST).read_text())
        m["REF"]["boot"], m["B0-L500"]["boot"], m["B0-L1000"]["boot"] = 449, 453, 454
        self.m = m
        self.write()
        self.r5, self.r10 = self.d / "r500", self.d / "r1000"
        shutil.copytree(R500, self.r5)
        shutil.copytree(R1000, self.r10)
        make_b3(self.r5, R500, 460)
        make_b3(self.r10, R1000, 461)

    def write(self):
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(self.m))

    def cr(self, k):
        return E.config_result(self.r10 if k.endswith("1000") else self.r5, self.d / "wl", k)

    def test_valid(self):
        for k in ("REF", "B0-L500", "B0-L1000", "B3-L500", "B3-L1000"):
            r = self.cr(k)
            self.assertEqual((k, r["status"]), (k, "VALID"), r.get("reasons"))
        self.assertTrue(self.cr("B3-L500")["layout"]["ok"])

    def test_shared_identity_runs(self):       # the shared identity (not a stage overlay) decides the placement term
        import stage6bb as BB
        f = self.r5 / "conds/e2eb_b3/wfe"
        m = self.m["B3-L500"]
        i = BB.identity_of(f, self.d / "wl", "e2eb_b3", m, str(self.d / "wl" / m["caps_ref"]))
        self.assertTrue(i["ok"])
        self.assertFalse(BB.identity_of(f, self.d / "wl", "e2eb_b3", dict(m, placement=0), str(self.d / "wl" / m["caps_ref"]))["ok"])

    def test_wrong_placement(self):
        self.m["B3-L500"]["placement"] = 0
        self.write()
        r = self.cr("B3-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("identity placement", r["reasons"])

    def test_b0_records_under_b3(self):        # a B0 RUN (placement 0) where B3 is expected
        self.m["B3-L500"].update(config="e2d_w1p1", drwl_sha256=self.m["B0-L500"]["drwl_sha256"], boot=453)
        self.write()
        r = self.cr("B3-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertTrue({"identity placement", "layout arena_where"} <= set(r["reasons"]))

    def rewrite(self, change, root=None, cfg="e2eb_b3"):
        f = (root or self.r5) / f"conds/{cfg}/wfe/raw_runs.json"
        runs = json.loads(f.read_text())
        for x in runs[1:]:
            change(x["record"])
        f.write_text(json.dumps(runs))

    def test_wrong_regioncfg(self):
        def ch(r):
            r["regioncfg_irq"] = 0x55F
        self.rewrite(ch)
        r = self.cr("B3-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("identity regioncfg", r["reasons"])

    def test_wrong_digest(self):
        self.m["B3-L500"]["drwl_sha256"] = "0" * 64
        self.write()
        self.assertIn("workload sha256", self.cr("B3-L500")["reasons"])

    def test_wrong_ta(self):
        self.m["B3-L500"]["ta_ext_rlatency"] = 1000
        self.write()
        r = self.cr("B3-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("TA EXT RLATENCY read-back", r["reasons"])

    def test_wrong_image(self):
        self.m["B3-L1000"]["image"] = self.m["B3-L500"]["image"]
        self.write()
        self.assertIn("image bram_sha256", self.cr("B3-L1000")["reasons"])

    def test_sram_conflict(self):
        def ch(r):
            r["arena_base"] = r["base1"] = 0x31010000
        self.rewrite(ch)
        r = self.cr("B3-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("layout fast_disjoint", r["reasons"])

    def test_output_mismatch(self):
        p = self.d / "wl/e2eb_b3.ref_ofm.bin"
        b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
        self.assertEqual(self.cr("B3-L500")["status"], "INVALID_OUTPUT")

    def test_pmu_missing(self):
        f = self.r5 / "conds/e2eb_b3/wfe/raw_runs.json"
        runs = json.loads(f.read_text())
        f.write_text(json.dumps(runs[:-1]))
        self.assertIn(self.cr("B3-L500")["status"], ("CONFIG_MISMATCH", "INVALID_PMU"))
        self.assertNotEqual(self.cr("B3-L500")["status"], "VALID")

    def test_unmeasured(self):
        shutil.rmtree(self.r5 / "conds/e2eb_b3")
        self.assertEqual(self.cr("B3-L500")["status"], "UNMEASURED")
        self.assertTrue(E.boot_check(str(self.r5), str(self.d / "wl"), "B3-L500")["stop"])

    def test_unstable(self):
        p = self.r5 / "conds/e2eb_b3/wfe/runs.csv"
        rows = read_rows(p)
        npu = [r for r in rows if r["name"] == "npu_active" and r["ev_type"] == "35"]
        target = npu[2]                                  # a measured pass-A RUN (rows are per slot per RUN)
        for r in rows:
            if r is target:
                r["event_value"] = r["ev_post_value"] = str(int(float(r["event_value"]) * 1.2))
        with open(p, "w", newline="") as fo:
            w = csv.DictWriter(fo, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        self.assertIn(self.cr("B3-L500")["status"], ("UNSTABLE", "INVALID_PMU"))

    def test_judge(self):
        s = E.judge(str(self.r5), str(self.r10), str(self.d / "wl"), str(REF375), str(self.d / "out"))
        v = s["verdicts"]
        self.assertEqual(v["measurement_validity"], "VALID")
        # the fixture is B0's data under B3's identity: no placement effect, no interaction, EXT unchanged
        self.assertEqual(v["graph_io_placement"], "IO_PLACEMENT_EFFECT_NOT_RESOLVED")
        self.assertEqual(v["latency_sensitivity"], "IO_SENSITIVITY_NOT_REDUCED")
        self.assertEqual(v["residual_ext_path"], "EXT_PATH_UNRESOLVED")
        self.assertEqual(v["residual_latency_response"], "RESIDUAL_RESPONSE_OBSERVED")
        self.assertEqual(v["pipeline_mechanism"], "MECHANISM_UNRESOLVED")
        self.assertEqual(s["b0_vs_e2d"][500]["within"], True)
        self.assertEqual(s["effects"]["pe"], {500: 0.0, 1000: 0.0})

    def test_judge_stop(self):
        shutil.rmtree(self.r10 / "conds/e2eb_b3")
        s = E.judge(str(self.r5), str(self.r10), str(self.d / "wl"), str(REF375), str(self.d / "out"))
        self.assertEqual(s["verdicts"]["measurement_validity"], "MEASUREMENT_INVALID")
        self.assertEqual(s["verdicts"]["graph_io_placement"], "NOT_IDENTIFIABLE")
        self.assertEqual(s["verdicts"]["latency_sensitivity"], "INSUFFICIENT_EVIDENCE")

    def test_mac_mismatch(self):
        p = self.r5 / "conds/e2eb_b3/wfe/runs.csv"
        rows = read_rows(p)
        for r in rows:
            if r["name"] == "mac_active":
                r["event_value"] = r["ev_post_value"] = "20737"
        with open(p, "w", newline="") as fo:
            w = csv.DictWriter(fo, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        s = E.judge(str(self.r5), str(self.r10), str(self.d / "wl"), str(REF375), str(self.d / "out"))
        self.assertEqual(s["mac_equals_h1uc"]["B3-L500"], False)
        self.assertEqual(s["verdicts"]["measurement_validity"], "PARTIAL_VALID")
        self.assertEqual(s["verdicts"]["graph_io_placement"], "NOT_IDENTIFIABLE")

    def test_repro_gate_fail(self):
        shutil.rmtree(self.r5 / "conds/s4c2_conv_cin48")
        s = E.judge(str(self.r5), str(self.r10), str(self.d / "wl"), str(REF375), str(self.d / "out"))
        self.assertEqual(s["reference_gate"]["verdict"], "FAIL")
        self.assertEqual(s["verdicts"]["measurement_validity"], "MEASUREMENT_INVALID")


    def test_repro_gate_ref_invalid(self):    # REF measured but its output differs -> gate FAIL before reproduce
        p = self.d / "wl/s4c2_conv_cin48.drwl.tflite_ofm.bin"
        b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
        g = E.repro_gate(str(self.r5), str(self.d / "wl"), str(REF375))
        self.assertEqual((g["verdict"], g.get("why")), ("FAIL", "INVALID_OUTPUT"))

    def test_repro_gate_other_binary(self):
        g = E.repro_gate(str(self.r5), str(self.d / "wl"), str(self.r5 / "conds/e2d_w1p1/wfe"))
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", False))

    def test_repro_gate_not_reproduced(self):  # same binary, boot-375 copy with NPU_ACTIVE 20 % higher
        ref = self.d / "ref375"
        shutil.copytree(REF375, ref)
        rows = read_rows(ref / "runs.csv")
        for r in rows:
            if r["name"] == "npu_active":
                r["event_value"] = r["ev_post_value"] = str(int(float(r["event_value"]) * 1.2))
        with open(ref / "runs.csv", "w", newline="") as fo:
            w = csv.DictWriter(fo, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        g = E.repro_gate(str(self.r5), str(self.d / "wl"), str(ref))
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", True))
        self.assertTrue(E.repro_gate(str(self.r5), str(self.d / "wl"), str(REF375))["verdict"] == "PASS")


if __name__ == "__main__":
    unittest.main()
