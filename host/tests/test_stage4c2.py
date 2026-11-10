"""stage4c2.py: the static kernel table on the real Stage 4C-2 artifacts, and the judge rules on synthetic folders."""
import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import stage4c2 as P
from test_stage4c1 import write

WL = REPO / "evidence/stage4c2/workloads"


class Static(unittest.TestCase):
    def test_kernels(self):
        s = P.static_one(WL, "s4c2_conv_cin128")
        self.assertEqual([(k["ofm_slice"], k["ifm_depth"], k["ofm_ublocks"], k["ifm_depth_steps"]) for k in s["kernels"]],
                         [(16, 128, 144, 2), (80, 128, 432, 2)])
        self.assertEqual((s["ofm_ublocks"], s["ublock_x_steps"], s["traversal"]), (576, 1152, "DepthFirst"))
        b = P.static_one(WL, "s4_conv_base")
        self.assertEqual((b["ofm_ublocks"], b["ublock_x_steps"]), (576, 576))
        self.assertEqual(P.static_one(WL, "s4c2_conv_cin32")["ublock_x_steps"], 1152)
        self.assertEqual(b["schedule"] == P.static_one(WL, "s4c2_conv_cin32")["schedule"], True)
        self.assertNotEqual(b["schedule"], s["schedule"])
        self.assertEqual(b["schedule"][-1], (16, 80))                       # kernel OFM slices are part of it


def comp(wl, name, macs):
    src = json.loads((WL / f"{name}.compile.json").read_text())
    src.update(n_mac=macs, ofm_shape=[1, 1, 1, 4], quant=dict(ofm_scale=0.1, zero_points=0, ifm_scale=1, weight_scale=1),
               activation="NONE")
    wl.mkdir(exist_ok=True)
    (wl / f"{name}.compile.json").write_text(json.dumps(src))
    (wl / f"{name}.drwl.tflite_ofm.bin").write_bytes(b"\x01\x02\x03\x04")
    (wl / f"{name}.drwl.cms.bin").write_bytes((WL / f"{name}.drwl.cms.bin").read_bytes())


def add_mac(folder, mac, dpu):
    rows = list(csv.DictReader(open(folder / "runs.csv")))
    extra = []
    for r in rows:
        if r["set_id"] == "1" and r["ev_type"] == "35":
            extra += [dict(r, ev_type=48, event_value=mac), dict(r, ev_type=51, event_value=dpu)]
    with open(folder / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows + extra)


class Judge(unittest.TestCase):
    def campaign(self, d, na_b, na_c, base_out=b"\x01\x02\x03\x04"):
        root, s4, wl = d / "root", d / "s4", d / "wl"
        na = {"s4_conv_base": ([1000] * 4, 1000), "s4c2_conv_cin32": ([1500] * 4, na_b),
              "s4c2_conv_cin64": (na_c, 2500), "s4c2_conv_cin128": ([4000] * 4, 4000)}
        macs = {"s4_conv_base": 1000, "s4c2_conv_cin32": 2000, "s4c2_conv_cin64": 4000, "s4c2_conv_cin128": 8000}
        for c, (a, b) in na.items():
            f = write(root, c, [600] * 4, a, 0x70000010)
            rows = list(csv.DictReader(open(f / "runs.csv")))
            for r in rows:
                if r["set_id"] == "2" and r["ev_type"] == "35":
                    r["event_value"] = b
            with open(f / "runs.csv", "w", newline="") as g:
                w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            add_mac(f, macs[c] // 4, macs[c] // 8)
            comp(wl, c, macs[c])
        f = write(s4, "s4_conv_base", [600] * 4, [1000] * 4, 0x70000010, out=base_out)
        add_mac(f, 250, 125)
        return P.judge(str(root), str(wl), str(s4), str(d / "out"))

    def test_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), 1500, [2500] * 4)
            self.assertTrue(r["baseline"]["ok"])
            p = r["pairs"]["s4_conv_base->s4c2_conv_cin32"]
            self.assertEqual((p["verdict"], p["schedule"]), ("NOT_PROPORTIONAL_TO_MAC", "SAME_SCHEDULE"))
            self.assertEqual((p["mac_ratio"], p["mac_active_ratio"]), (2.0, 2.0))
            self.assertEqual(r["pairs"]["s4c2_conv_cin32->s4c2_conv_cin64"]["schedule"], "SCHEDULE_CHANGED")
            ub = r["static"]["s4_conv_base"]["ofm_ublocks"]                    # 4 here: the fixture's 1x1 OFM
            self.assertEqual(ub, 4)
            self.assertEqual(r["configs"]["s4_conv_base"]["mac_active_per_ublock"], 250 / ub)
            st = r["static"]["s4c2_conv_cin32"]                                # 2 IFM depth steps
            self.assertEqual(st["ublock_x_steps"], 2 * st["ofm_ublocks"])
            self.assertEqual(r["configs"]["s4c2_conv_cin32"]["mac_active_per_ublock"], 500 / st["ofm_ublocks"])
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), 900, [2500] * 4)                 # pass B the other way
            self.assertEqual(r["pairs"]["s4_conv_base->s4c2_conv_cin32"]["verdict"], "UNRESOLVED")
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), 1500, [2500] * 4, base_out=b"\x01\x02\x03\x05")
            self.assertFalse(r["baseline"]["ok"])
            self.assertEqual(r["pairs"]["s4c2_conv_cin64->s4c2_conv_cin128"]["verdict"], "NOT_INTERPRETED")

    def test_invalid_config_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            r = self.campaign(d, 1500, [2500] * 4)
            self.assertEqual(r["configs"]["s4c2_conv_cin64"]["verdict"], "VALID")
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            root = d / "root"
            r0 = self.campaign(d, 1500, [2500] * 4)
            (root / "conds" / "s4c2_conv_cin64" / "wfe" / "output.bin").write_bytes(b"\x09\x02\x03\x04")
            r = P.judge(str(root), str(d / "wl"), str(d / "s4"), str(d / "out2"))
            self.assertEqual(r["configs"]["s4c2_conv_cin64"]["verdict"], "INVALID")
            self.assertEqual(r["pairs"]["s4c2_conv_cin32->s4c2_conv_cin64"]["verdict"], "EXCLUDED")
            self.assertTrue(r0)
        with tempfile.TemporaryDirectory() as d:                                 # an output FAIL the firmware agrees with
            d = pathlib.Path(d)
            self.campaign(d, 1500, [2500] * 4)
            f = d / "root" / "conds" / "s4c2_conv_cin64" / "wfe"
            (f / "output.bin").write_bytes(b"\x09\x02\x03\x04")
            raw = json.loads((f / "raw_runs.json").read_text())
            import zlib
            for x in raw[1:]:
                x["record"].update(ofm_mismatch=1, ofm_max_diff=8); x["output_crc32"] = zlib.crc32(b"\x09\x02\x03\x04")
            (f / "raw_runs.json").write_text(json.dumps(raw))
            r = P.judge(str(d / "root"), str(d / "wl"), str(d / "s4"), str(d / "out3"))
            self.assertEqual((r["configs"]["s4c2_conv_cin64"]["output"]["verdict"],
                              r["configs"]["s4c2_conv_cin64"]["verdict"]), ("FAIL", "INVALID"))


if __name__ == "__main__":
    unittest.main()
