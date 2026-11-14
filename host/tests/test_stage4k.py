"""stage4k.py: MAC definitions, hypotheses, static facts of the compiled configs, the Phase 1 recomputation of the
existing 1x1 data, and the judge (reproduction gate, verdicts, RQ rules) on synthetic campaigns."""
import csv, json, math, pathlib, shutil, sys, tempfile, unittest
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import stage4k as P
from test_stage4c1 import write
from test_stage4c2 import add_mac

WL = REPO / "evidence/stage4k/workloads"
# MAC_ACTIVE of the existing 1x1 data (owner's table, results/fi101_stage4c2 and 4c2b READMEs), typed here on purpose
# pass-A NPU_ACTIVE near the archived medians (32: 25,622.5; 40: 22,454.5; 48: 22,331; 64: 24,182.5 / 24,554)
K1_NPU = {32: 25600, 40: 22450, 48: 22330, 64: 24300}
K1_MAC = {16: (2304, 1152), 32: (4608, 2304), 40: (3456, 3456), 48: (3456, 3456), 64: (4608, 4608)}


class Definitions(unittest.TestCase):
    def test_macs(self):
        self.assertEqual(P.macs(1, 16), dict(nominal=884736, valid=884736, c16=884736))
        self.assertEqual(P.macs(3, 16)["nominal"], 24 * 24 * 96 * 9 * 16)
        self.assertEqual(P.macs(3, 16)["valid"], 70 * 70 * 96 * 16)       # 24x24 SAME 3x3: 70 in-bound taps per axis
        self.assertEqual(P.macs(3, 40)["c16"], 24 * 24 * 96 * 9 * 48)

    def test_hypotheses(self):
        h = P.hypotheses(3, 40)
        self.assertEqual(h["R384_nominal"], 51840)
        self.assertEqual(h["R384_c16"], 62208)
        self.assertEqual(h["R768_valid"], 24500)
        self.assertEqual(h["R768_valid_c16"], 29400)
        self.assertEqual(len(set(h.values())), 8)                             # Cin 40 separates all eight

    def test_verdict(self):
        h = P.hypotheses(3, 16)
        self.assertEqual(P.verdict([20736] * 4, True, True, h), "MATCH:R384_nominal+R384_c16")
        self.assertEqual(P.verdict([12345] * 4, True, True, h), "NONE_MATCHED")
        self.assertEqual(P.verdict([20736, 20736, 20736, 20737], True, True, h), "MEASUREMENT_UNSTABLE")
        self.assertEqual(P.verdict([20736] * 4, False, True, h), "INVALID")
        self.assertEqual(P.verdict([20736] * 4, True, False, h), "INVALID")
        self.assertEqual(P.verdict([20736] * 3, True, True, h), "INVALID")


class Static(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        cls.s = P.static(str(WL), cls.d.name)

    @classmethod
    def tearDownClass(cls):
        cls.d.cleanup()

    def test_schedule_switches(self):
        self.assertEqual(self.s["switches_k1"], ["32->40"])
        self.assertEqual(self.s["switches_k3"], [])
        self.assertEqual({self.s[P.K3[c]]["traversal"] for c in P.CINS}, {"PartKernel"})

    def test_controls(self):
        self.assertTrue(all(v["cms"] and v["cpu_ofm"] for v in self.s["k1_same_control"].values()))
        self.assertTrue(all(self.s["same_ifm_per_cin"].values()))

    def test_structure(self):
        x = self.s[P.K3[40]]
        self.assertEqual(x["kernel_hw"], [[3, 3]])
        self.assertEqual([k["ifm_depth_steps"] for k in x["kernels"]], [3, 3])
        self.assertAlmostEqual(x["block_fill"], 0.8)
        self.assertAlmostEqual(x["ublock_fill"], 0.75)
        self.assertEqual(self.s[P.K1[16]]["kernel_hw"], [[1, 1]])


class Prior(unittest.TestCase):
    def test_phase1_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = P.prior(d)
        for cin, (mac, dpu) in K1_MAC.items():
            rows = [v for k, v in p.items() if k.startswith(P.K1[cin] + "@")]
            self.assertTrue(rows)
            for r in rows:
                self.assertEqual(set(r["mac_active"]), {mac})
                self.assertEqual(set(r["mac_dpu_active"]), {dpu})
                self.assertEqual(r["macs_per_mac_active"], 24 * 24 * 96 * cin / mac)


def write_cfg(root, cfg, mac, npu, beats=3456, out=None, unstable=False, valid=True, dpu=None):
    out = out if out is not None else (WL / f"{cfg}.drwl.tflite_ofm.bin").read_bytes()
    f = write(root, cfg, [beats] * 4, [npu] * 4, 0x70000010, out=out, valid=valid)
    mac = int(mac)
    add_mac(f, mac, int(dpu if dpu is not None else mac))
    if unstable:
        rows = list(csv.DictReader(open(f / "runs.csv")))
        for r in rows:
            if r["ev_type"] == "48" and r["set_id"] == "1" and r["rep"] == "5" and r["event_value"] == str(mac):
                r["event_value"] = mac + 1
        with open(f / "runs.csv", "w", newline="") as g:
            w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return f


class Judge(unittest.TestCase):
    def campaign(self, d, mac3, base_mac=2304, base_npu=21000, npu3=None, unstable=None, base_out=None, k1_npu=None,
                 npu3_b=None):
        root = d / "root"
        for cin in P.CINS:
            mac = base_mac if cin == 16 else K1_MAC[cin][0]
            write_cfg(root, P.K1[cin], mac, base_npu if cin == 16 else (k1_npu or {}).get(cin, K1_NPU[cin]),
                      out=base_out if cin == 16 else None, dpu=K1_MAC[cin][1])
            f = write_cfg(root, P.K3[cin], mac3[cin], (npu3 or {}).get(cin, 40000), unstable=unstable == cin)
            if npu3_b and cin in npu3_b:                                # pass B NPU_ACTIVE set apart from pass A
                rows = list(csv.DictReader(open(f / "runs.csv")))
                for x in rows:
                    if x["set_id"] == "2" and x["ev_type"] == "35":
                        x["event_value"] = npu3_b[cin]
                with open(f / "runs.csv", "w", newline="") as g:
                    w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        P.predict(str(WL), str(d / "p"))
        return P.judge(str(root), str(WL), str(d / "p" / "predictions.json"), str(d / "out"))

    def test_rate_384_ceil16(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), mac3)
        self.assertEqual(r["repro_gate"]["verdict"], "PASS")
        self.assertEqual(r["configs"][P.K3[40]]["verdict"], "MATCH:R384_c16")
        self.assertEqual(r["rq"]["rq2"]["k3"]["verdict"], "CONSISTENT_WITH_CEIL16")
        self.assertTrue(r["rq"]["rq2"]["k3"]["step_40_48_equal"])
        self.assertEqual(r["rq"]["rq1"][16]["verdict"], "SAME_RATE")
        self.assertEqual(r["rq"]["rq1"][16]["comparability"], "SAME_TRAVERSAL_BLOCKS_DIFFER")
        self.assertEqual(r["rq"]["rq1"][48]["comparability"], "TRAVERSAL_DIFFERS")
        self.assertEqual(r["rq"]["rq1"][48]["verdict"], "RATE_3X3_LOWER")
        self.assertEqual(r["reproduction"][P.K1[40]]["verdict"], "REPRODUCED")
        row = next(x for x in r["table"] if x["config"] == P.K3[16])
        self.assertEqual(row["macs_per_mac_active"], 384)
        self.assertAlmostEqual(row["peak_rel_mac_active"], 384 / 1024)
        self.assertAlmostEqual(row["valid_macs_per_mac_active"], 384 * 4900 / 5184)

    def test_proportional_and_neither(self):
        mac3 = {c: P.hypotheses(3, c)["R768_nominal"] for c in P.CINS}
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), mac3)
        self.assertEqual(r["rq"]["rq2"]["k3"]["verdict"], "PROPORTIONAL_TO_CIN")
        self.assertEqual(r["rq"]["rq1"][16]["verdict"], "RATE_3X3_HIGHER")
        self.assertEqual(r["rq"]["rq2"]["k1"]["verdict"], "NEITHER")       # the 1x1 set spans two schedules
        mac3 = {**mac3, 40: 30000}
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), mac3)
        self.assertEqual(r["configs"][P.K3[40]]["verdict"], "NONE_MATCHED")
        self.assertEqual(r["rq"]["rq2"]["k3"]["verdict"], "NEITHER")

    def test_unstable_not_judged(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), mac3, unstable=40)
        self.assertEqual(r["configs"][P.K3[40]]["verdict"], "MEASUREMENT_UNSTABLE")
        self.assertEqual(r["rq"]["rq2"]["k3"]["verdict"], "NOT_JUDGED")
        self.assertEqual(r["rq"]["rq1"][40]["verdict"], "NOT_JUDGED")

    def test_repro_gate(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        for kw in (dict(base_mac=2305), dict(base_npu=23000), dict(base_out=bytes(55296))):
            with tempfile.TemporaryDirectory() as d:
                r = self.campaign(pathlib.Path(d), mac3, **kw)
            self.assertEqual(r["repro_gate"]["verdict"], "FAIL", kw)
            self.assertTrue(r["configs"][P.K3[16]]["verdict"].startswith("NOT_INTERPRETED"), kw)
            self.assertEqual(r["rq"]["rq2"]["k3"]["verdict"], "NOT_INTERPRETED", kw)
        with tempfile.TemporaryDirectory() as d:                      # cli exit code follows the verdict
            d = pathlib.Path(d)
            self.campaign(d, mac3, base_mac=2305)
            self.assertEqual(P.main(["repro-gate", str(d / "root"), str(WL)]), 1)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            self.campaign(d, mac3)
            self.assertEqual(P.main(["repro-gate", str(d / "root"), str(WL)]), 0)

    def test_boot_check(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            self.campaign(d, mac3)
            self.assertEqual(P.main(["boot-check", str(d / "root"), str(WL), P.K3[40]]), 0)
            self.assertEqual(P.main(["boot-check", str(d / "empty"), str(WL), P.K3[16]]), 1)    # not measured
            write_cfg(d / "bad", P.K3[16], 20736, 40000, valid=False)
            self.assertEqual(P.boot_check(str(d / "bad"), str(WL), P.K3[16])["verdict"], "FAIL")
            write_cfg(d / "out", P.K3[16], 20736, 40000, out=bytes(55296))
            self.assertEqual(P.boot_check(str(d / "out"), str(WL), P.K3[16])["verdict"], "FAIL")

    def test_repro_other_1x1(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        with tempfile.TemporaryDirectory() as d:          # Cin 40 NPU_ACTIVE far from 4C-2b boot 348 (22,454.5)
            r = self.campaign(pathlib.Path(d), mac3, k1_npu={40: 30000})
        self.assertEqual(r["reproduction"][P.K1[40]]["verdict"], "REPRO_MISMATCH")
        self.assertEqual(r["reproduction"][P.K1[48]]["verdict"], "REPRODUCED")
        self.assertEqual(r["repro_gate"]["verdict"], "PASS")

    def test_pairs(self):
        mac3 = {c: P.hypotheses(3, c)["R384_c16"] for c in P.CINS}
        npu3 = {16: 40000, 32: 80000, 40: 40100, 48: 50000, 64: 60000}
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), mac3, npu3=npu3)
        cp = r["rq"]["rq4"]["cin_pairs"]
        self.assertEqual(cp[f"{P.K3[16]}->{P.K3[32]}"]["verdict"], "CONSISTENT_WITH_MAC_CHANGE")
        self.assertEqual(cp[f"{P.K3[32]}->{P.K3[40]}"]["verdict"], "NOT_PROPORTIONAL_TO_MAC")
        self.assertEqual(cp[f"{P.K3[40]}->{P.K3[48]}"]["verdict"], "NOT_PROPORTIONAL_TO_MAC")
        with tempfile.TemporaryDirectory() as d:          # pass B moves the other way at 16 -> 32
            r2 = self.campaign(pathlib.Path(d), mac3, npu3=npu3, npu3_b={16: 40000, 32: 30000})
        self.assertEqual(r2["rq"]["rq4"]["cin_pairs"][f"{P.K3[16]}->{P.K3[32]}"]["verdict"], "UNRESOLVED")
        self.assertTrue(r2["rq"]["rq4"]["cin_pairs"][f"{P.K3[16]}->{P.K3[32]}"]["directions_opposite"])
        kp = r["rq"]["rq4"]["kernel_pairs"][f"{P.K1[16]}->{P.K3[16]}"]
        self.assertAlmostEqual(kp["mac_ratio"], 9.0)
        self.assertAlmostEqual(kp["mac_active_ratio"], 9.0)


def summ(mac=2304, dpu=1152, out="aa", npu=21000.0, rng=100, const=None):
    runs = {1: [dict(ev=dict(const or {}))] * 2}
    return dict(runs=runs, mac_active=[mac] * 4, mac_dpu_active=[dpu] * 4, output_sha256=out,
                metrics=dict(A_35=npu, A_35_range=rng))


class Reproduce(unittest.TestCase):
    def test_each_check(self):
        ref = summ(const={64: 5})
        self.assertTrue(P.reproduce(summ(const={64: 5}), ref)["ok"])
        for kw, key in ((dict(mac=2305), "mac"), (dict(dpu=1153), "dpu"), (dict(out="bb"), "output"),
                        (dict(out=None), "output"), (dict(const={64: 6}), "constant_counters"),
                        (dict(npu=21300.0), "npu_active")):
            r = P.reproduce(summ(**dict(dict(const={64: 5}), **kw)), ref)
            self.assertFalse(r["ok"], kw)
            self.assertEqual([k for k, v in r["checks"].items() if not v], [key], kw)
        self.assertTrue(P.reproduce(summ(npu=21200.0), summ())["ok"])            # inside 1 % of 21,000

    def test_gate_requires_exact_output(self):
        rep = dict(ok=True, checks={}, differing_constant_counters={}, npu_active=(1, 1), tolerance=1, compared=1)
        for out, want in (("PASS_EXACT", "PASS"), ("PASS_TOLERANCE", "FAIL")):
            cr = dict(verdict="MATCH:x", output=dict(verdict=out))
            with mock.patch.object(P, "config_result", return_value=cr), \
                    mock.patch.object(P, "reproduce", return_value=rep), mock.patch.object(P, "gate_ref"):
                self.assertEqual(P.repro_gate("x", "y")["verdict"], want)


class StaticControls(unittest.TestCase):
    def test_control_and_mac_assertion(self):
        with tempfile.TemporaryDirectory() as d:
            wl = pathlib.Path(d) / "wl"
            shutil.copytree(WL, wl)
            f = wl / f"{P.K1_SAME[40]}.drwl.cms.bin"
            b = bytearray(f.read_bytes()); b[-1] ^= 1; f.write_bytes(bytes(b))
            s = P.static(str(wl), str(pathlib.Path(d) / "o"))
            self.assertFalse(s["k1_same_control"][40]["cms"])
            self.assertTrue(s["k1_same_control"][48]["cms"])
            c = wl / f"{P.K3[16]}.compile.json"
            x = json.loads(c.read_text()); x["n_mac"] += 1; c.write_text(json.dumps(x))
            with self.assertRaises(AssertionError):
                P.predict(str(wl), str(pathlib.Path(d) / "p"))


if __name__ == "__main__":
    unittest.main()
