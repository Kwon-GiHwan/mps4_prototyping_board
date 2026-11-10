"""stage5.py rules on synthetic folders (DRWLs, campaign folders, the 5-0 record and the earlier measurements)."""
import csv, json, sys, tempfile, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "lib"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import drwl
import stage5 as P
from test_stage4c1 import write
from test_stage4c2 import add_mac

GOLD = b"\x01\x02\x03\x04"


def setup(d, out=None, earlier_mac=250, na_b_variant=1100, model_out=None, variant_macs=1000):
    """Every workload/variant: a DRWL with GOLD, RUNs with NPU_ACTIVE 1000 (base) / 1100 (variants, pass A)."""
    wl, root, c50 = d / "wl", d / "root", {}
    wl.mkdir()
    earlier = {}
    for w, (kind, variants) in P.WORKLOADS.items():
        c50[w] = {}
        for v in variants:
            name = f"{w}_{v}"
            sha = f"{name}-sha"
            (wl / f"{name}.drwl").write_bytes(drwl.pack(b"MODEL", [b"\x00" * 8], [GOLD]))
            (wl / f"{name}.drwl.json").write_text(json.dumps(dict(vela_sha256=sha)))
            c50[w][v] = dict(nn_macs=1000 if v == "base" else variant_macs, compute_sig=f"sig-{v}", kernels=2, cycles_npu=500, vela_sha256=sha,
                             sram_used_kib=8.0, fast_size=100, arena_size=200, **{"class": "BASE" if v == "base" else "SCHEDULE_CHANGED"})
            o = (out or {}).get(name, GOLD)
            na = [1000] * 4 if v == "base" else [1100] * 4
            f = write(root, name, [600] * 4, na, 0x70000010, out=o)
            if o != GOLD:                                   # the firmware counted the same difference
                raw = json.loads((f / "raw_runs.json").read_text())
                for x in raw[1:]:
                    x["record"].update(ofm_mismatch=1, ofm_max_diff=abs(o[0] - GOLD[0]))
                (f / "raw_runs.json").write_text(json.dumps(raw))
            if v != "base":
                rows = list(csv.DictReader(open(f / "runs.csv")))
                for r in rows:
                    if r["set_id"] == "2" and r["ev_type"] == "35":
                        r["event_value"] = na_b_variant
                with open(f / "runs.csv", "w", newline="") as g:
                    wr = csv.DictWriter(g, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
            add_mac(f, 250, 250)
        e = d / "earlier" / w
        ef = write(e, "x", [600] * 4, [1000] * 4, 0x70000010)
        add_mac(ef, earlier_mac, 250)
        earlier[w] = (ef, 1)
    (d / "c50.json").write_text(json.dumps(c50))
    return root, wl, earlier


class Stage5(unittest.TestCase):
    def run_it(self, effective=None, **kw):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        root, wl, earlier = setup(d, **kw)
        old, old_eff = dict(P.EARLIER), dict(P.EFFECTIVE)
        P.EARLIER.update(earlier)
        P.EFFECTIVE.clear(); P.EFFECTIVE.update(effective or {})
        try:
            return P.main(str(root), str(wl), str(d / "c50.json"), str(d / "out"))
        finally:
            P.EARLIER.clear(); P.EARLIER.update(old)
            P.EFFECTIVE.clear(); P.EFFECTIVE.update(old_eff)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_and_pairs(self):
        r = self.run_it()
        self.assertTrue(all(x["ok"] for x in r["base_check"].values()))
        p = r["pairs"]["kws_micronet_m_base->kws_micronet_m_cache0"]
        self.assertEqual((p["verdict"], p["class_5_0"], p["same_output_as_base"]),
                         ("NOT_PROPORTIONAL_TO_MAC", "SCHEDULE_CHANGED", True))
        self.assertEqual(p["mac_dpu_exact"], {"mac_active": (250, 250), "mac_dpu_active": (250, 250)})

    def test_effective_macs_are_the_base_definition(self):
        # Vela counts 10 % more MACs for the variant; NPU_ACTIVE +10 % must still be judged against unchanged MACs
        r = self.run_it(variant_macs=1100)
        p = r["pairs"]["kws_micronet_m_base->kws_micronet_m_cache0"]
        self.assertEqual(p["verdict"], "NOT_PROPORTIONAL_TO_MAC")
        self.assertEqual(p["pass_a"]["mac_change_pct"], 0.0)
        self.assertEqual(p["vela_macs"], (1000, 1100))

    def test_effective_macs_from_the_project_definition(self):
        # a model with a project N_MAC (2000) uses it for base and variant; an isolated operator without one
        # falls back to its base compile's count (1000); Vela's own counts stay in vela_macs
        r = self.run_it(variant_macs=1100, effective={"kws_micronet_m": 2000})
        kws = r["configs"]["kws_micronet_m_base"]["metrics"]
        self.assertEqual(kws["macs_per_npu_active"], 2.0)                       # 2000 MACs / NPU_ACTIVE 1000
        self.assertEqual(r["configs"]["kws_micronet_m_cache0"]["metrics"]["macs_per_npu_active"], 2000 / 1100)
        self.assertEqual(r["configs"]["s4_dw_base_base"]["metrics"]["macs_per_npu_active"], 1.0)
        self.assertEqual(r["pairs"]["kws_micronet_m_base->kws_micronet_m_cache0"]["vela_macs"], (1000, 1100))

    def test_opposite_directions(self):
        r = self.run_it(na_b_variant=900)
        self.assertEqual(r["pairs"]["s4_dw_base_base->s4_dw_base_cache0"]["verdict"], "UNRESOLVED")

    def test_baseline_mismatch(self):
        r = self.run_it(earlier_mac=251)
        self.assertFalse(r["base_check"]["ad_medium_int8"]["ok"])
        self.assertEqual(r["pairs"]["ad_medium_int8_base->ad_medium_int8_cache64k"]["verdict"], "NOT_INTERPRETED")

    def test_model_exact_only_op_tolerance(self):
        one = b"\x02\x02\x03\x04"                            # +1 LSB at element 0
        r = self.run_it(out={"kws_micronet_m_cache0": one, "s4_conv_base_cache0": one})
        self.assertEqual(r["configs"]["kws_micronet_m_cache0"]["output"]["verdict"], "FAIL")
        self.assertEqual(r["configs"]["kws_micronet_m_cache0"]["verdict"], "INVALID")
        self.assertEqual(r["pairs"]["kws_micronet_m_base->kws_micronet_m_cache0"]["verdict"], "EXCLUDED")
        self.assertEqual(r["configs"]["s4_conv_base_cache0"]["output"]["verdict"], "PASS_TOLERANCE")
        self.assertFalse(r["pairs"]["s4_conv_base_base->s4_conv_base_cache0"]["same_output_as_base"])

    def test_not_executable(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        root, wl, earlier = setup(d)
        import shutil
        shutil.rmtree(root / "conds" / "ad_medium_int8_cache0")
        old = dict(P.EARLIER); P.EARLIER.update(earlier)
        try:
            r = P.main(str(root), str(wl), str(d / "c50.json"), str(d / "out"))
        finally:
            P.EARLIER.clear(); P.EARLIER.update(old)
        self.assertEqual(r["configs"]["ad_medium_int8_cache0"]["verdict"], "NOT_EXECUTABLE")
        self.assertEqual(r["pairs"]["ad_medium_int8_base->ad_medium_int8_cache0"]["verdict"], "EXCLUDED")

    def test_refused_after_warmup_and_crc(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        root, wl, earlier = setup(d)
        f = root / "conds" / "ad_medium_int8_cache0" / "wfe"          # only the warm-up RUN completed
        rows = [r for r in csv.DictReader(open(f / "runs.csv")) if r["rep"] == "1"]
        with open(f / "runs.csv", "w", newline="") as g:
            wr = csv.DictWriter(g, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
        raw = json.loads((f / "raw_runs.json").read_text())
        (f / "raw_runs.json").write_text(json.dumps([raw[0]] + [x for x in raw[1:] if x["rep"] == 1]))
        g2 = root / "conds" / "kws_micronet_m_cache64k" / "wfe"       # one RUN's output CRC differs
        raw = json.loads((g2 / "raw_runs.json").read_text())
        raw[3]["output_crc32"] ^= 1
        (g2 / "raw_runs.json").write_text(json.dumps(raw))
        old = dict(P.EARLIER); P.EARLIER.update(earlier)
        try:
            r = P.main(str(root), str(wl), str(d / "c50.json"), str(d / "out"))
        finally:
            P.EARLIER.clear(); P.EARLIER.update(old)
        self.assertEqual(r["configs"]["ad_medium_int8_cache0"]["verdict"], "NOT_EXECUTABLE")
        self.assertEqual(r["configs"]["kws_micronet_m_cache64k"]["output"]["verdict"], "INVALID")


class Plans(unittest.TestCase):
    def test_5_2_configs(self):
        w, e = P.PLANS["5-2"]
        self.assertEqual({k: v[1] for k, v in w.items()}, {"kws_micronet_m": ("base", "size"),
                                                           "ad_medium_int8": ("base", "size"),
                                                           "s4c2_conv_cin64": ("base", "size")})
        self.assertEqual(set(e), set(w))
        self.assertEqual(P.PLANS["5-1"][0], P.WORKLOADS)


if __name__ == "__main__":
    unittest.main()
