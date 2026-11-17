"""Stage 6B-E2E-D rules (evidence/stage6b/stage6be2ed/contract.md). Expected values typed by hand.

Board fixtures: E2E-B boots 458 (REF), 460 / 461 (B3), judged under this stage's manifest with the old image digests and
boot numbers mapped back. B3w has no board data before the session; its fixture is the B3 folder rewritten to the B3w
identity (DRWL digest, placement 2, REGIONCFG 0x550, BASEP0 = the SRAM copy) and, where a test needs it, to B3w traffic
or NPU_ACTIVE values. It tests the judge only.
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
import stage6be2ed as E  # noqa: E402

WL = REPO / "evidence/stage6b/stage6be2ed/workloads"
EB_WL = REPO / "evidence/stage6b/stage6be2eb/workloads"
RAW = REPO / "evidence/stage6b/stage6be2eb/raw"
R500, R1000 = RAW / "evsweep_s6be2eb_run_l500", RAW / "evsweep_s6be2eb_run_l1000"
REF375 = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"
B3W_SHA = "51ff7a4a540dc1fdb2a6dad72cbca2286e855bfd53961cb4a5dad4e4ce197918"
COPY = 0x31280420


def rows_of(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def write_rows(p, rows):
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def set_event(folder, code, value=None, scale=None):
    p = folder / "runs.csv"
    rows = rows_of(p)
    for r in rows:
        if r["ev_type"] == str(code):
            v = value if value is not None else float(r["event_value"]) * scale
            r["event_value"] = r["ev_post_value"] = str(int(v))
    write_rows(p, rows)


def make_b3w(root: pathlib.Path, src_root: pathlib.Path, boot: int) -> pathlib.Path:
    src, dst = src_root / "conds/e2eb_b3", root / "conds/e2ed_b3w"
    shutil.copytree(src, dst)
    f = dst / "wfe/raw_runs.json"
    runs = json.loads(f.read_text())
    for x in runs[1:]:
        r = x["record"]
        r["placement"], r["regioncfg_irq"], r["base0"] = 2, 0x550, COPY
    f.write_text(json.dumps(runs))
    p = dst / "wfe/runs.csv"
    rows = rows_of(p)
    for r in rows:
        r["workload_sha256"], r["host_boot_index"] = B3W_SHA, str(boot)
    write_rows(p, rows)
    return dst / "wfe"


class Constants(unittest.TestCase):
    def test_frozen(self):
        self.assertEqual(E.ORDER, [("REF", 500, 463), ("B3", 500, 464), ("B3w", 500, 465), ("B3w", 1000, 466), ("B3", 1000, 467)])
        self.assertEqual(E.PLACEMENT, {"REF": 0, "B3": 1, "B3w": 2})
        self.assertEqual((E.LOW, E.HIGH, E.SHIFT_TOL, E.NOISE_FLOOR), (0.25, 0.75, 0.01, 0.01))
        self.assertEqual(E.EXT_RD_B3W, (39, 64))
        self.assertEqual(E.WEIGHT_SCALE_BEATS, 11282.0)
        self.assertEqual(E.B3_EB, {500: (60320.0, 1197), 1000: (72526.5, 1189)})
        self.assertEqual(E.B3_EB_TRAFFIC["ext_rd_beats"], 11322.0)

    def test_manifest(self):
        m = json.loads((WL / E.MANIFEST).read_text())
        self.assertEqual({k: (v["boot"], v["config"], v["placement"], v["latency"]) for k, v in m.items()},
                         {"REF": (463, "s4c2_conv_cin48", 0, 500), "B3-L500": (464, "e2eb_b3", 1, 500),
                          "B3w-L500": (465, "e2ed_b3w", 2, 500), "B3w-L1000": (466, "e2ed_b3w", 2, 1000),
                          "B3-L1000": (467, "e2eb_b3", 1, 1000)})
        self.assertEqual(m["B3w-L500"]["drwl_sha256"], B3W_SHA)
        self.assertEqual((m["B3w-L500"]["weights_at"], m["B3-L500"]["weights_at"]), (COPY, None))
        self.assertEqual(m["B3w-L500"]["image"]["bram_sha256"][:8], "ec0e8c3b")
        self.assertEqual(m["B3w-L1000"]["image"]["bram_sha256"][:8], "ca7d2e49")
        self.assertEqual(m["B3w-L1000"]["image"]["boot_sha256"][:8], "751a1bf2")
        self.assertEqual(m["REF"]["image"]["ddr_sha256"][:8], "374708ff")

    def test_b3w_is_b3_with_word7(self):
        a, b = (WL / "e2eb_b3.drwl").read_bytes(), (WL / "e2ed_b3w.drwl").read_bytes()
        self.assertEqual([(i, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]], [(28, 1, 2)])


class Pure(unittest.TestCase):
    def test_weight_dst(self):
        self.assertEqual(E.weight_dst(0x31076770, 0x200000, 0x31400000, 0x70000420, 0x16090), COPY)
        self.assertEqual(E.weight_dst(0x31070000, 0x200000, 0x31400000, 0x70000420, 0x10), 0x31270420)
        self.assertEqual(E.weight_dst(0x31076770, 0x200000, 0x31400000, 0x70000420, 0x17FBE0), COPY)
        self.assertEqual(E.weight_dst(0x31076770, 0x200000, 0x31400000, 0x70000420, 0x17FBE1), 0)
        self.assertEqual(E.weight_dst(0x31076770, 0x200000, 0x31400000, 0, 0x10), 0)

    def test_remap_ok(self):
        good = dict(ext_rd_beats=40.0, ext_wr_beats=0.0, sram_rd_beats=40832.0 + 11282)
        r = E.remap_ok(good, 40832.0, 52154.0)
        self.assertTrue(r["ok"], r)
        for k, v, c in (("ext_rd_beats", 38.0, "ext_rd"), ("ext_rd_beats", 65.0, "ext_rd"), ("ext_wr_beats", 1.0, "ext_wr"),
                        ("sram_rd_beats", 40832.0 + 11282 * 0.98, "sram_shift")):
            self.assertFalse(E.remap_ok(dict(good, **{k: v}), 40832.0, 52154.0)["checks"][c], k)
        self.assertTrue(E.remap_ok(dict(good, ext_rd_beats=39.0), 40832.0, 52154.0)["checks"]["ext_rd"])
        self.assertTrue(E.remap_ok(dict(good, ext_rd_beats=64.0), 40832.0, 52154.0)["checks"]["ext_rd"])
        self.assertTrue(E.remap_ok(dict(good, sram_rd_beats=40832.0 + 11282 * 1.0099), 40832.0, 52154.0)["checks"]["sram_shift"])
        self.assertFalse(E.remap_ok(good, 40832.0, 52154.0 * 1.02)["checks"]["read_total"])

    def test_remap_validity(self):
        ok, bad = dict(ok=True), dict(ok=False)
        self.assertEqual(E.remap_validity({500: ok, 1000: ok}), "WEIGHT_SCALE_REMAP_CONFIRMED")
        self.assertEqual(E.remap_validity({500: ok, 1000: None}), "REMAP_PARTIAL")
        self.assertEqual(E.remap_validity({500: bad, 1000: ok}), "REMAP_PARTIAL")
        self.assertEqual(E.remap_validity({500: bad, 1000: None}), "REMAP_INVALID")

    def test_b3_reproduced(self):
        t = dict(E.B3_EB_TRAFFIC)
        self.assertTrue(E.b3_reproduced(60320 + 1197 + 300, 300, t, 500)["ok"])     # within range sum
        self.assertFalse(E.b3_reproduced(60320 + 1197 + 301, 300, t, 500)["ok"])
        self.assertTrue(E.b3_reproduced(72526.5 - 1000, 10, t, 1000)["ok"])          # 1 % floor 725 < 1189 + 10
        self.assertFalse(E.b3_reproduced(60320, 0, dict(t, ext_rd_beats=11323.0), 500)["ok"])
        self.assertEqual(E.equivalence({500: dict(ok=True), 1000: dict(ok=True)}), "B3_REPRODUCED")
        self.assertEqual(E.equivalence({500: dict(ok=True), 1000: None}), "B3_PARTIAL")
        self.assertEqual(E.equivalence({500: dict(ok=False), 1000: None}), "B3_NOT_REPRODUCED")

    def test_residual(self):
        R = lambda *a: E.residual(*a, True)["verdict"]
        self.assertEqual(R(12000, 2000, 1000, 500), "WEIGHT_PATH_DOMINANT_RESPONSE")
        self.assertEqual(R(12000, 2000, 3000, 500), "WEIGHT_PATH_DOMINANT_RESPONSE")     # ratio 0.25 exactly
        self.assertEqual(R(12000, 2000, 3001, 500), "MIXED_RESPONSE")
        self.assertEqual(R(12000, 2000, 11000, 500), "RESIDUAL_NON_WEIGHT_RESPONSE")
        self.assertEqual(R(12000, 2000, 9000, 500), "RESIDUAL_NON_WEIGHT_RESPONSE")      # ratio 0.75 exactly
        self.assertEqual(R(12000, 2000, 8999, 500), "MIXED_RESPONSE")
        self.assertEqual(R(12000, 2000, 12206, 2386), "RESIDUAL_NON_WEIGHT_RESPONSE")    # E2E-B noise, ratio ~1
        self.assertEqual(R(3000, 2000, 500, 1500), "INSUFFICIENT_EVIDENCE")              # removal 2500 <= 3500
        self.assertEqual(R(3000, 2000, 500, 499), "WEIGHT_PATH_DOMINANT_RESPONSE")       # removal 2500 > 2499
        self.assertEqual(R(12000, 2000, 9500, 9500), "INSUFFICIENT_EVIDENCE")            # remaining not > tol
        self.assertEqual(R(12000, 9000, 6000, 500), "INSUFFICIENT_EVIDENCE")             # mixed, removal 6000 <= 9500
        self.assertEqual(R(12000, 2000, 6000, 6000), "INSUFFICIENT_EVIDENCE")            # mixed, remaining 6000 <= 6000
        self.assertEqual(R(2000, 2000, 0, 500), "INSUFFICIENT_EVIDENCE")                 # B3 has no response
        self.assertEqual(E.residual(12000, 2000, 1000, 500, False)["verdict"], "INSUFFICIENT_EVIDENCE")
        r = E.residual(12000, 2000, 6000, 500, True)
        self.assertEqual((r["verdict"], r["ratio"], r["low"], r["high"]), ("MIXED_RESPONSE", 0.5, 5500 / 14000, 6500 / 10000))

    def test_validity_mechanism(self):
        g = dict(verdict="PASS")
        r = {k: dict(status="VALID") for k in ("REF", "B3-L500")}
        self.assertEqual(E.validity(g, r, {"B3-L500": True}), "VALID")
        self.assertEqual(E.validity(g, r, {"B3-L500": False}), "PARTIAL_VALID")
        self.assertEqual(E.validity(g, dict(r, **{"B3-L500": dict(status="INVALID_OUTPUT")}), {}), "PARTIAL_VALID")
        self.assertEqual(E.validity(g, dict(r, **{"B3-L500": dict(status="UNMEASURED")}), {}), "MEASUREMENT_INVALID")
        self.assertEqual(E.validity(dict(verdict="FAIL"), r, {}), "MEASUREMENT_INVALID")
        self.assertEqual(E.mechanism(), "MECHANISM_UNRESOLVED")


def caps(folder):
    return json.loads((folder.parent / "capabilities.json").read_text())


def recs(folder):
    return [x["record"] for x in json.loads((folder / "raw_runs.json").read_text())[1:]]


class Layout(unittest.TestCase):
    B3 = R500 / "conds/e2eb_b3/wfe"

    def w(self, change=None, at=COPY):
        r = [dict(x, base0=COPY) for x in recs(self.B3)]
        for x in r:
            (change or (lambda _: None))(x)
        return E.layout(r, caps(self.B3), 2, 2, 1, at)

    def test_b3_real(self):
        l = E.layout(recs(self.B3), caps(self.B3), 1, 2, 1, None)
        self.assertTrue(l["ok"], l)
        self.assertTrue(l["checks"]["weights_ddr"])

    def test_b3w(self):
        self.assertTrue(self.w()["ok"])
        self.assertFalse(self.w(at=COPY + 16)["checks"]["weights_where"])
        self.assertFalse(self.w(at=None)["checks"]["weights_where"])

    def test_weights_not_moved(self):                      # a B3 record (weights in DDR) under the B3w expectation
        l = E.layout(recs(self.B3), caps(self.B3), 2, 2, 1, COPY)
        self.assertFalse(l["checks"]["weights_where"])
        self.assertFalse(l["checks"]["weights_inside"])

    def test_weights_overlap_arena(self):
        def ch(x):
            x["base0"] = 0x31200000
        c = self.w(ch, at=0x31200000)["checks"]
        self.assertFalse(c["weights_disjoint"])
        self.assertTrue(c["weights_inside"])

    def test_weights_overlap_fast(self):
        def ch(x):
            x["base0"] = 0x31010000
        self.assertFalse(self.w(ch, at=0x31010000)["checks"]["weights_disjoint"])

    def test_weights_past_sram(self):
        def ch(x):
            x["base0"] = 0x313F0000
        self.assertFalse(self.w(ch, at=0x313F0000)["checks"]["weights_inside"])

    def test_b3_weights_in_sram(self):                     # placement 1 must keep region 0 in the DDR model
        r = [dict(x, base0=COPY) for x in recs(self.B3)]
        self.assertFalse(E.layout(r, caps(self.B3), 1, 2, 1, None)["checks"]["weights_ddr"])

    def test_arena_checks_kept(self):
        r = [dict(x, arena_base=0x31010000, base1=0x31010000, base0=COPY) for x in recs(self.B3)]
        c = E.layout(r, caps(self.B3), 2, 2, 1, COPY)["checks"]
        self.assertFalse(c["arena_where"])
        self.assertFalse(c["fast_disjoint"])
        self.assertFalse(E.layout([], caps(self.B3), 2, 2, 1, COPY)["ok"])


class Board(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        shutil.copytree(WL, self.d / "wl")
        m = json.loads((WL / E.MANIFEST).read_text())
        eb = json.loads((EB_WL / "e2eb_manifest.json").read_text())
        for k, boot in (("REF", 458), ("B3-L500", 460), ("B3-L1000", 461), ("B3w-L500", 465), ("B3w-L1000", 466)):
            m[k]["boot"] = boot
            m[k]["image"] = eb["B3-L1000" if k.endswith("1000") else "B3-L500"]["image"]   # the old images (fixture)
        self.m = m
        self.write()
        self.r5, self.r10 = self.d / "r500", self.d / "r1000"
        shutil.copytree(R500, self.r5)
        shutil.copytree(R1000, self.r10)
        self.w5 = make_b3w(self.r5, R500, 465)
        self.w10 = make_b3w(self.r10, R1000, 466)

    def write(self):
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(self.m))

    def cr(self, k):
        return E.config_result(self.r10 if k.endswith("1000") else self.r5, self.d / "wl", k)

    def remap_traffic(self):
        for f in (self.w5, self.w10):
            set_event(f, 386, 40)                  # EXT read beats: command stream only
            set_event(f, 384, 3)
            set_event(f, 130, 40832 + 11282)       # SRAM read beats: + weights and scale

    def judge(self):
        return E.judge(str(self.r5), str(self.r10), str(self.d / "wl"), str(REF375), str(self.d / "out"))

    def test_valid(self):
        for k in ("REF", "B3-L500", "B3-L1000", "B3w-L500", "B3w-L1000"):
            r = self.cr(k)
            self.assertEqual((k, r["status"]), (k, "VALID"), r.get("reasons"))

    def test_wrong_remap_address(self):
        self.m["B3w-L500"]["weights_at"] = COPY + 0x10000
        self.write()
        r = self.cr("B3w-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertIn("layout weights_where", r["reasons"])

    def test_remap_fell_back(self):              # the firmware fell back to placement 1: base0 DDR, REGIONCFG 0x553, no flag
        f = self.w5 / "raw_runs.json"
        runs = json.loads(f.read_text())
        for x in runs[1:]:
            x["record"]["regioncfg_irq"], x["record"]["base0"] = 0x553, 0x70000420
            x["valid_flags"] = x.get("valid_flags", 0) & ~(1 << 6)
        f.write_text(json.dumps(runs))
        r = self.cr("B3w-L500")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertTrue({"identity regioncfg", "layout weights_where"} <= set(r["reasons"]), r["reasons"])

    def test_wrong_placement(self):
        self.m["B3w-L500"]["placement"] = 1
        self.write()
        self.assertIn("identity placement", self.cr("B3w-L500")["reasons"])

    def test_wrong_digest(self):
        self.m["B3w-L500"]["drwl_sha256"] = "0" * 64
        self.write()
        self.assertIn("workload sha256", self.cr("B3w-L500")["reasons"])

    def test_wrong_ta(self):
        self.m["B3w-L1000"]["ta_ext_rlatency"] = 500
        self.write()
        self.assertIn("TA EXT RLATENCY read-back", self.cr("B3w-L1000")["reasons"])

    def test_wrong_image(self):
        self.m["B3-L500"]["image"] = json.loads((WL / E.MANIFEST).read_text())["B3-L500"]["image"]   # the new image
        self.write()
        self.assertIn("image bram_sha256", self.cr("B3-L500")["reasons"])

    def test_command_moved(self):              # QCONFIG changed (command stream port) -> identity qconfig
        f = self.w5 / "raw_runs.json"
        runs = json.loads(f.read_text())
        for x in runs[1:]:
            x["record"]["qconfig_irq"] = 0
        f.write_text(json.dumps(runs))
        self.assertIn("identity qconfig", self.cr("B3w-L500")["reasons"])

    def test_output_error(self):
        p = self.d / "wl/e2ed_b3w.ref_ofm.bin"
        b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
        self.assertEqual(self.cr("B3w-L500")["status"], "INVALID_OUTPUT")

    def test_unmeasured_stops(self):
        shutil.rmtree(self.r5 / "conds/e2ed_b3w")
        self.assertTrue(E.boot_check(str(self.r5), str(self.d / "wl"), "B3w-L500")["stop"])

    def test_b3_gate(self):
        self.assertEqual(E.b3_gate(str(self.r5), str(self.d / "wl"), 500)["verdict"], "PASS")
        set_event(self.r5 / "conds/e2eb_b3/wfe", 35, scale=1.1)
        self.assertEqual(E.b3_gate(str(self.r5), str(self.d / "wl"), 500)["verdict"], "FAIL")

    def test_b3_gate_mac(self):
        set_event(self.r5 / "conds/e2eb_b3/wfe", 48, 20737)
        self.assertEqual(E.b3_gate(str(self.r5), str(self.d / "wl"), 500)["verdict"], "FAIL")

    def test_repro_gate(self):
        self.assertEqual(E.repro_gate(str(self.r5), str(self.d / "wl"), str(REF375))["verdict"], "PASS")
        g = E.repro_gate(str(self.r5), str(self.d / "wl"), str(self.r5 / "conds/e2eb_b3/wfe"))
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", False))
        ref = self.d / "ref375"
        shutil.copytree(REF375, ref)
        set_event(ref, 35, scale=1.2)
        g = E.repro_gate(str(self.r5), str(self.d / "wl"), str(ref))
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", True))

    def test_b3_gate_traffic(self):
        set_event(self.r5 / "conds/e2eb_b3/wfe", 386, 11323)
        self.assertEqual(E.b3_gate(str(self.r5), str(self.d / "wl"), 500)["verdict"], "FAIL")

    def test_judge_fixture_unremapped(self):     # B3w fixture with B3 traffic: remap not shown -> no residual class
        s = self.judge()
        v = s["verdicts"]
        self.assertEqual((v["measurement_validity"], v["b3_equivalence"], v["remap_validity"]),
                         ("VALID", "B3_REPRODUCED", "REMAP_INVALID"))
        self.assertEqual(v["residual_latency"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(v["pipeline_mechanism"], "MECHANISM_UNRESOLVED")

    def test_judge_weight_dominant(self):
        self.remap_traffic()
        set_event(self.w10, 35, 60500)          # B3w L1000 NPU_ACTIVE ~ its L500 value: LE(B3w) ~ 0
        set_event(self.w5, 35, 60000)
        s = self.judge()
        self.assertEqual(s["verdicts"]["remap_validity"], "WEIGHT_SCALE_REMAP_CONFIRMED")
        self.assertEqual(s["verdicts"]["residual_latency"], "WEIGHT_PATH_DOMINANT_RESPONSE", s["residual"])
        self.assertEqual(s["effects"]["le"]["B3w"], 500.0)
        self.assertEqual(s["effects"]["tol_le"]["B3"], 1197 + 1189)                    # E2E-B B3 ranges

    def test_judge_non_weight(self):
        self.remap_traffic()                   # NPU unchanged: LE(B3w) = LE(B3)
        s = self.judge()
        self.assertEqual(s["verdicts"]["residual_latency"], "RESIDUAL_NON_WEIGHT_RESPONSE", s["residual"])

    def test_judge_b3_not_reproduced(self):
        self.remap_traffic()
        set_event(self.r10 / "conds/e2eb_b3/wfe", 35, scale=1.2)
        s = self.judge()
        self.assertEqual(s["verdicts"]["b3_equivalence"], "B3_PARTIAL")
        self.assertEqual(s["verdicts"]["residual_latency"], "INSUFFICIENT_EVIDENCE")

    def test_judge_mac(self):
        self.remap_traffic()
        set_event(self.w5, 48, 20737)
        s = self.judge()
        self.assertEqual(s["verdicts"]["remap_validity"], "REMAP_PARTIAL")
        self.assertEqual(s["verdicts"]["measurement_validity"], "PARTIAL_VALID")
        self.assertEqual(s["verdicts"]["residual_latency"], "INSUFFICIENT_EVIDENCE")

    def test_judge_ref_gate(self):
        shutil.rmtree(self.r5 / "conds/s4c2_conv_cin48")
        self.assertEqual(self.judge()["verdicts"]["measurement_validity"], "MEASUREMENT_INVALID")


if __name__ == "__main__":
    unittest.main()
