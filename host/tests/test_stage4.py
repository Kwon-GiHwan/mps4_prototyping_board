"""stage4.py rules on synthetic campaign folders (written here from the board script's file layout)."""
import csv, json, sys, tempfile, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage4 as S

CFGS = ("conv_base", "conv_cin15", "conv_cout95", "dw_base", "dw_c143", "fc_base", "fc_in95", "fc_out287")
MACS = dict(conv_base=1000, conv_cin15=900, conv_cout95=990, dw_base=500, dw_c143=496, fc_base=100, fc_in95=99,
            fc_out287=99)


def write_cfg(root, comp, name, npu_active, ref, npu=None, valid=True, crc_bad=False, fw=None, traffic=None,
              block="6x12x96", act="RELU6"):
    """npu_active: list of 4 measured values (the warm-up RUN gets the first one too)."""
    npu = ref if npu is None else npu
    d = root / "conds" / f"s4_{name}" / "wfe"
    d.mkdir(parents=True)
    diffs = [abs((a - 256 if a > 127 else a) - (b - 256 if b > 127 else b)) for a, b in zip(npu, ref)]
    mism, mx = fw if fw is not None else (sum(x != 0 for x in diffs), max(diffs))
    raw, rows = [{"ping": {}}], []
    for set_id, codes in ((1, S.PASS_A), (2, S.PASS_B)):
        for rep, na in enumerate([npu_active[0]] + list(npu_active), start=1):
            crc = zlib.crc32(npu) ^ (1 if crc_bad and rep == 3 else 0)
            raw.append(dict(set_id=set_id, rep=rep, record=dict(ofm_mismatch=mism, ofm_max_diff=mx),
                            output_crc32=crc, output_len=len(npu)))
            for c in codes:
                v = na if c == 35 else (traffic or {}).get(c, 1000) if set_id == 2 else na // 2
                rows.append(dict(set_id=set_id, rep=rep, ev_type=c, event_value=v,
                                 run_valid=str(valid or rep != 2)))
    (d / "raw_runs.json").write_text(json.dumps(raw))
    with open(d / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (d / "output.bin").write_bytes(npu)
    comp.mkdir(exist_ok=True)
    (comp / f"s4_{name}.drwl.tflite_ofm.bin").write_bytes(ref)
    (comp / f"s4_{name}.compile.json").write_text(json.dumps(dict(
        n_mac=MACS[name], ofm_shape=[1, 2, len(ref) // 2], quant=dict(ofm_scale=0.1, zero_points=0, ifm_scale=1,
                                                                      weight_scale=1),
        activation=act, gate_b=True, vela_npu_cycles=1000, ofm_block=block, ofm_ublock="2x2x32", n_kernels=2)))


REF = bytes([0, 1, 2, 3, 250, 60, 7, 8])


def build(d, **over):
    root, comp = d / "root", d / "comp"
    base = dict(conv_base=[1000] * 4, conv_cin15=[900] * 4, conv_cout95=[1000] * 4, dw_base=[500] * 4,
                dw_c143=[500] * 4, fc_base=[100] * 4, fc_in95=[100] * 4, fc_out287=[100] * 4)
    for c in CFGS:
        kw = over.get(c, {})
        write_cfg(root, comp, c, kw.pop("npu_active", base[c]), REF, **kw)
    return S.main(str(root), str(comp), str(d / "out"))


class Output(unittest.TestCase):
    def check(self, npu, **kw):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            res = build(d, conv_base=dict(npu=npu, **kw))
            return res["configs"]["conv_base"]

    def test_exact_tolerance_fail(self):
        self.assertEqual(self.check(REF)["output"]["verdict"], "PASS_EXACT")
        one = bytes([1, 1, 2, 3, 251, 60, 7, 8])                                # +1 at 0 and at -6
        c = self.check(one)
        self.assertEqual(c["output"]["verdict"], "PASS_TOLERANCE")
        self.assertEqual((c["output"]["mismatch_count"], c["output"]["diff_1lsb_count"], c["output"]["max_abs_diff"]),
                         (2, 2, 1))
        self.assertEqual(c["gate_c"], "PASS")
        two = bytes([2, 1, 2, 3, 250, 60, 7, 8])
        c = self.check(two)
        self.assertEqual((c["output"]["verdict"], c["gate_c"]), ("FAIL", "FAIL"))
        self.assertEqual((c["output"]["diff_gt_1lsb_count"], c["output"]["diff_1lsb_count"]), (1, 0))
        self.assertEqual(self.check(bytes([0, 1, 2, 3, 6, 60, 7, 8]))["output"]["verdict"], "FAIL")   # -6 vs 6: int8

    def test_invalid(self):
        self.assertEqual(self.check(REF[:-1])["output"]["verdict"], "INVALID")                      # length
        self.assertEqual(self.check(REF, crc_bad=True)["output"]["verdict"], "INVALID")             # RUNs differ
        self.assertEqual(self.check(REF, fw=(1, 1))["output"]["verdict"], "INVALID")                # firmware count

    def test_saturation_and_channels(self):
        o = self.check(bytes([1, 1, 2, 3, 250, 60, 8, 8]))["output"]                 # cap = round(6 / 0.1) = 60
        self.assertEqual((o["relu6_cap"], o["npu_at_relu6_cap"], o["channels_with_mismatch"], o["channels"]),
                         (60, 1, 2, 4))
        self.assertEqual(o["top_channel_share"], 0.5)

    def test_invalid_run_fails_gate(self):
        self.assertEqual(self.check(REF, valid=False)["gate_c"], "FAIL")


class Pairs(unittest.TestCase):
    def test_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            res = build(pathlib.Path(d), conv_cout95=dict(npu_active=[1100] * 4, block="14x18x32"),
                        dw_c143=dict(npu_active=[505, 505, 505, 505]),
                        fc_in95=dict(npu_active=[99] * 4, traffic={128: 2000}))
            p = res["pairs"]
            self.assertEqual(p["conv_base->conv_cin15"]["verdict"], "CONSISTENT_WITH_MAC_CHANGE")   # -10 % = MACs
            self.assertEqual(p["conv_base->conv_cout95"]["verdict"], "NOT_PROPORTIONAL_TO_MAC")
            self.assertTrue(p["conv_base->conv_cout95"]["schedule_changed"])
            self.assertFalse(p["conv_base->conv_cin15"]["schedule_changed"])
            self.assertEqual(p["dw_base->dw_c143"]["verdict"], "UNRESOLVED")                        # +1 % = floor
            self.assertEqual(p["fc_base->fc_in95"]["verdict"], "UNRESOLVED")
            self.assertTrue(p["fc_base->fc_in95"]["traffic_changed"])
            self.assertFalse(p["fc_base->fc_out287"]["traffic_changed"])

    def test_floor_is_one_percent(self):
        with tempfile.TemporaryDirectory() as d:
            res = build(pathlib.Path(d), dw_c143=dict(npu_active=[508] * 4))                     # +1.6 %
            self.assertEqual(res["pairs"]["dw_base->dw_c143"]["verdict"], "NOT_PROPORTIONAL_TO_MAC")

    def test_range_widens_tolerance(self):
        with tempfile.TemporaryDirectory() as d:
            res = build(pathlib.Path(d), conv_cin15=dict(npu_active=[800, 900, 900, 950]))
            self.assertEqual(res["pairs"]["conv_base->conv_cin15"]["verdict"], "UNRESOLVED")      # range 150

    def test_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            res = build(pathlib.Path(d), dw_c143=dict(npu=bytes([9]) + REF[1:]))
            self.assertEqual(res["pairs"]["dw_base->dw_c143"]["verdict"], "EXCLUDED")


if __name__ == "__main__":
    unittest.main()
