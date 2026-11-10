"""stage4c1.py: the decoder and the prediction on Stage 4's artifacts (known measurements, never an input), and the
verdict rules on synthetic campaign folders."""
import csv, json, sys, tempfile, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage4c1 as P
sys.path.insert(0, str(REPO / "host" / "lib"))

S4W = REPO / "evidence/stage4/workloads"


class Predict(unittest.TestCase):
    def test_decoder_on_stage4_streams(self):
        ks = P.kernels((S4W / "s4_conv_cout95.drwl.cms.bin").read_bytes())
        self.assertEqual([(k["kind"], k["ofm_depth_m1"] + 1, k["ofm_stride_x"], k["ofm_stride_y"], k["ofm_base0"])
                          for k in ks], [("CONV", 16, 95, 2280, 0), ("CONV", 79, 95, 2280, 16)])
        self.assertEqual(ks[1]["dma_before"], [2992])                          # Vela verbose: DMA0_LEN 0xbb0
        ks = P.kernels((S4W / "s4_dw_c143.drwl.cms.bin").read_bytes())
        self.assertEqual([(k["ifm_depth_m1"] + 1, k["ifm_stride_x"], k["ifm_base0"]) for k in ks],
                         [(16, 143, 0x6D7C0), (127, 143, 0x6D7D0)])
        self.assertEqual(ks[0]["blk_height_m1"] + 1, 26)

    def test_reproduces_stage4_without_records(self):
        # artifacts only; the Stage 4 board records (arena 0x700015b0 / 0x700012a0; event 391 6,660 / 54,488) are the check
        for cfg, arena, beats in (("s4_conv_cout95", 0x700015B0, 6660), ("s4_dw_c143", 0x700012A0, 54488),
                                  ("s4_conv_base", 0x700015C0, 3456), ("s4_dw_base", 0x700012B0, 28224)):
            p = P.predict_one(S4W, cfg)
            self.assertEqual((int(p["arena"], 16), p["predicted_write_beats"]["A"]), (arena, beats), cfg)
            self.assertTrue(p["dense_nhwc"])
        self.assertTrue(P.predict_one(S4W, "s4_dw_c143")["discriminating"])
        self.assertFalse(P.predict_one(S4W, "s4_dw_base")["discriminating"])

    def test_not_dense_is_not_comparable(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            for f in S4W.glob("s4_conv_cout95.*"):
                shutil.copy(f, d / f.name)
            c = json.loads((d / "s4_conv_cout95.compile.json").read_text())
            c["ofm_shape"] = [1, 24, 24, 96]                                    # the stream's stride is 95
            (d / "s4_conv_cout95.compile.json").write_text(json.dumps(c))
            p = P.predict_one(d, "s4_conv_cout95")
            self.assertEqual((p["dense_nhwc"], p["not_comparable"]), (False, True))
            c["ofm_shape"] = [1, 24, 24, 95]
            (d / "s4_conv_cout95.compile.json").write_text(json.dumps(c))
            import cms, hashlib                                                  # only the pixel stride differs
            st = bytearray((d / "s4_conv_cout95.drwl.cms.bin").read_bytes())
            for off, word, ctrl, op in cms.instructions(bytes(st)):
                if ctrl == 1 and op == 0x14:
                    st[off + 4:off + 8] = (96).to_bytes(4, "little")
            (d / "s4_conv_cout95.drwl.cms.bin").write_bytes(bytes(st))
            m = json.loads((d / "s4_conv_cout95.drwl.json").read_text())
            m["cms_sha256"] = hashlib.sha256(bytes(st)).hexdigest()
            (d / "s4_conv_cout95.drwl.json").write_text(json.dumps(m))
            self.assertFalse(P.predict_one(d, "s4_conv_cout95")["dense_nhwc"])
            for f in S4W.glob("s4_conv_cout95.drwl*"):
                shutil.copy(f, d / f.name)
            c["ofm_memory"] = "Sram"
            (d / "s4_conv_cout95.compile.json").write_text(json.dumps(c))
            self.assertTrue(P.predict_one(d, "s4_conv_cout95")["not_comparable"])

    def test_arena_rule(self):
        self.assertEqual(P.arena(5568), 0x700015C0)
        self.assertEqual(P.arena(5569), 0x700015D0)


def write(root, name, beats, n_active, base1, out=b"\x01\x02\x03\x04", valid=True, macs=1000, block="6x12x96"):
    d = root / "conds" / name / "wfe"
    d.mkdir(parents=True)
    raw, rows = [{"ping": {}}], []
    for set_id, codes in ((1, [35, 48]), (2, [35, 391])):
        for rep in range(1, 6):
            na = n_active[rep - 2] if rep > 1 else n_active[0]
            raw.append(dict(set_id=set_id, rep=rep, record=dict(ofm_mismatch=0, ofm_max_diff=0, base1=base1),
                            output_crc32=zlib.crc32(out), output_len=len(out)))
            for c in codes:
                v = na if c == 35 else (beats[rep - 2] if rep > 1 else beats[0]) if c == 391 else 500
                rows.append(dict(set_id=set_id, rep=rep, ev_type=c, event_value=v, run_valid=str(valid)))
    (d / "raw_runs.json").write_text(json.dumps(raw))
    with open(d / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (d / "output.bin").write_bytes(out)
    return d


def comp(wl, name, macs, block="6x12x96"):
    wl.mkdir(exist_ok=True)
    (wl / f"{name}.drwl.tflite_ofm.bin").write_bytes(b"\x01\x02\x03\x04")
    (wl / f"{name}.compile.json").write_text(json.dumps(dict(
        n_mac=macs, ofm_shape=[1, 1, 1, 4], quant=dict(ofm_scale=0.1, zero_points=0, ifm_scale=1, weight_scale=1),
        activation="NONE", vela_npu_cycles=1000, ofm_block=block, ofm_ublock="2x2x32", n_kernels=2)))


PRED = dict(arena="0x70000010", predicted_write_beats=dict(A=600, B=400, C=450, D=380), discriminating=True,
            not_comparable=False)


class Judge(unittest.TestCase):
    def one(self, beats, base1=0x70000010, pred=PRED, **kw):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            folder = write(d, "x", beats, [1000] * 4, base1, **kw)
            comp(d / "wl", "x", 1000)
            return P.judge_one(folder, d / "wl", "x", pred)["verdict"]

    def test_verdicts(self):
        self.assertEqual(self.one([600] * 4), "PREDICTION_MATCH")
        self.assertEqual(self.one([601] * 4), "PREDICTION_MISMATCH")
        self.assertEqual(self.one([600, 600, 601, 600]), "MEASUREMENT_UNSTABLE")
        self.assertEqual(self.one([600] * 4, base1=0x70000020), "INVALID")              # address not as predicted
        self.assertEqual(self.one([600] * 4, valid=False), "INVALID")
        self.assertEqual(self.one([600] * 4, out=b"\x09\x02\x03\x04"), "INVALID")        # output FAIL
        self.assertEqual(self.one([600] * 4, pred=dict(PRED, not_comparable=True)), "NOT_COMPARABLE")
        self.assertEqual(self.one([400] * 4), "PREDICTION_MISMATCH")                     # = rule B, still a mismatch

    def campaign(self, d, variant_na_a, variant_na_b, base_beats_now=600):
        root, s4, wl = d / "root", d / "s4", d / "wl"
        preds = {}
        for c in P.CONFIGS:
            base = c.startswith("s4_")
            na = [1000] * 4
            if not base:
                na = variant_na_a
            f = write(root, c, [600] * 4 if not base else [base_beats_now] * 4, na, 0x70000010)
            if not base:   # pass B NPU_ACTIVE of the variant
                rows = list(csv.DictReader(open(f / "runs.csv")))
                for r in rows:
                    if r["set_id"] == "2" and r["ev_type"] == "35":
                        r["event_value"] = variant_na_b
                with open(f / "runs.csv", "w", newline="") as g:
                    w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            comp(wl, c, 1000)
            preds[c] = PRED
            if base:
                write(s4, c, [600] * 4, [1000] * 4, 0x70000010)
        (d / "pred.json").write_text(json.dumps(preds))
        return P.judge(str(root), str(wl), str(d / "pred.json"), str(s4), str(d / "out"))

    def test_pairs_and_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), [1100] * 4, 1100)
            self.assertTrue(r["baseline_ok"])
            self.assertEqual(r["pairs"]["s4_conv_base->s4c_conv_cout94"]["verdict"], "NOT_PROPORTIONAL_TO_MAC")
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), [1100] * 4, 900)                          # pass B goes the other way
            self.assertEqual(r["pairs"]["s4_conv_base->s4c_conv_cout94"]["verdict"], "UNRESOLVED")
        with tempfile.TemporaryDirectory() as d:
            r = self.campaign(pathlib.Path(d), [1100] * 4, 1100, base_beats_now=601)    # a constant counter moved
            self.assertFalse(r["baseline_ok"])
            self.assertEqual(r["pairs"]["s4_dw_base->s4c_dw_c145"]["verdict"], "NOT_INTERPRETED")


if __name__ == "__main__":
    unittest.main()
