"""stage4p.py rules on synthetic A/B condition folders (run_driver_events.py's layout) around the real Stage 4 conv_base
workload, compile metadata and CPU reference. Expected values are the contract's numbers, written out here."""
import copy, csv, json, sys, tempfile, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis")); sys.path.insert(0, str(REPO / "host" / "lib"))
import drwl
import stage4p as P

W = REPO / "evidence" / "stage4" / "workloads"
A_BLOB = (W / "s4_conv_base.drwl").read_bytes()
META = json.loads((W / "s4_conv_base.drwl.json").read_text())
CMS = (W / "s4_conv_base.drwl.cms.bin").read_bytes()
REF = (W / "s4_conv_base.drwl.tflite_ofm.bin").read_bytes()
PASS_A = [35, 48, 51, 53, 55, 64, 80, 81]
PASS_B = [35, 128, 130, 132, 135, 384, 386, 391]
REGIONCFG_MATCH = 1 << 6
REQUIRED = 0x1F

# Stage 4 conv_base pass medians (TA profile 1, image 83398c7) and the B the plan predicts (§6: IFM 576 beats x 2 kernels,
# OFM 3,456 beats moved from EXT to SRAM)
A_EV = {1: {35: 21207, 48: 2304, 51: 1152, 53: 0, 55: 5347, 64: 3540, 80: 1052, 81: 6993},
        2: {35: 21139, 128: 304, 130: 2016, 132: 16, 135: 252, 384: 171, 386: 1437, 391: 3456}}
B_EV = copy.deepcopy(A_EV)
B_EV[1][35] = B_EV[2][35] = 15000
B_EV[2].update({130: 2016 + 1152, 135: 252 + 3456, 386: 1437 - 1152, 391: 0})
JITTER = [0, 0, 3, 7]                     # added to NPU_ACTIVE per measured RUN (range 7)
CAPS = dict(fast_base=0x31000000, fast_size=0x60000, axi_sram=0x20F0B, axi_ext=0x21F3F, mem_attr0=0, mem_attr1=0,
            mem_attr2=4, mem_attr3=4, ta_sram_version=0x1117, ta_ext_version=0x1117,
            **{f"ta_{p}_{n}": i for p in ("sram", "ext") for i, n in enumerate(P.record_v2.TA11)})


def record(which, **over):
    arena = (0x700015C0, 0x310615C0)[which]
    r = dict(schema=4, placement=which, arena_base=arena, base1=arena, base_size1=0xFC00,
             regioncfg_irq=(0x15F, 0x153)[which], qconfig_irq=3, n_base=5, model_base=0x70000000, model_len=5568,
             arena_len=0x200000, base0=0x700003B0, base2=0x31000000, base_size0=0xFC0, base_size2=0xFC0,
             ofm_mismatch=0, ofm_max_diff=0)
    r.update(over)
    return r


def write(folder, placement, ev, out=REF, rec=None, flags=REQUIRED | REGIONCFG_MATCH, caps=None, valid=True):
    folder.mkdir(parents=True)
    raw, rows = [{"ping": {}}], []
    for set_id, codes in ((1, PASS_A), (2, PASS_B)):
        for rep, j in enumerate([0] + JITTER, start=1):
            raw.append(dict(set_id=set_id, rep=rep, valid_flags=flags, record=record(placement, **(rec or {})),
                            output_crc32=zlib.crc32(out), output_len=len(out)))
            for c in codes:
                rows.append(dict(set_id=set_id, rep=rep, ev_type=c, event_value=ev[set_id][c] + (j if c == 35 else 0),
                                 run_valid=str(valid)))
    (folder / "raw_runs.json").write_text(json.dumps(raw))
    with open(folder / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (folder / "output.bin").write_bytes(out)
    (folder.parent / "capabilities.json").write_text(json.dumps(caps or CAPS))


def run(a=None, b=None, b_blob=None):
    """a, b: keyword overrides for write()."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        a, b = dict(a or {}), dict(b or {})
        write(d / "A" / "wfe", 0, a.pop("ev", A_EV), **a)
        write(d / "B" / "wfe", 1, b.pop("ev", B_EV), **b)
        (d / "a.drwl").write_bytes(A_BLOB)
        (d / "b.drwl").write_bytes(b_blob if b_blob is not None else P.make_b(A_BLOB))
        (d / "cms.bin").write_bytes(CMS)
        return P.analyse(d / "A" / "wfe", d / "B" / "wfe", W, d / "out", d / "a.drwl", d / "b.drwl", d / "cms.bin")


def ev_with(base, changes):
    e = copy.deepcopy(base)
    for (p, c), v in changes.items():
        e[p][c] = v
    return e


class GateB(unittest.TestCase):
    def test_real_workloads(self):
        r = P.gate_b(A_BLOB, P.make_b(A_BLOB), META, CMS)
        self.assertEqual((r["verdict"], r["differing_bytes"]), ("PASS", [28]))
        self.assertEqual(r["model_sha256"], META["vela_sha256"])

    def test_failures(self):
        b = P.make_b(A_BLOB)
        h = drwl.parse(b)
        x = bytearray(b); x[h["model_off"] + 100] ^= 1                                     # a model byte
        y = bytearray(b); o, n = h["inputs"][0]; y[o] ^= 1                                  # an IFM byte
        cases = {"only_word_7_differs": bytes(x), "sections_equal": bytes(y), "placements": A_BLOB}
        for check, blob in cases.items():
            r = P.gate_b(A_BLOB, blob, META, CMS)
            self.assertEqual(r["verdict"], "FAIL", check)
            self.assertFalse(r["checks"][check], check)
        r = P.gate_b(b, b, META, CMS)                                                       # A must be Stage 4's blob
        self.assertFalse(r["checks"]["a_is_stage4_blob"])
        self.assertFalse(P.gate_b(A_BLOB, b, META, CMS[:-16] + b"\0" * 16)["checks"]["cms_sha256"])
        with self.assertRaises(ValueError):
            P.make_b(b)                                                                     # B is not an A

    def test_cli_writes_b(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").write_bytes(A_BLOB)
            self.assertEqual(P.main(["make-b", str(d / "a"), str(d / "b")]), 0)
            self.assertEqual(drwl.parse((d / "b").read_bytes())["placement"], 1)
            self.assertEqual(P.main(["gate-b", str(d / "a"), str(d / "b"), str(W / "s4_conv_base.drwl.json"),
                                     str(W / "s4_conv_base.drwl.cms.bin")]), 0)


class Verdicts(unittest.TestCase):
    def test_interpreted_b_lower(self):
        r = run()
        self.assertEqual((r["outcome"], r["stops"]), ("INTERPRETED", []))
        self.assertEqual((r["cost"]["verdict"], r["compute"]["verdict"], r["traffic"]["verdict"], r["p1"]["verdict"]),
                         ("B_LOWER", "COMPUTE_SAME", "TRAFFIC_CONSISTENT", "PASS"))
        self.assertEqual(r["cost"]["per_pass"][1]["tol"], max(0.01 * 21208.5, 7))     # median of +0 +0 +3 +7
        self.assertEqual(r["ta_profile"], 1)
        self.assertEqual(r["auxiliary"]["pass2_391"]["verdict"], "CHANGED")
        self.assertEqual(r["auxiliary"]["pass1_64"]["verdict"], "NOT_RESOLVED")

    def test_cost_rule(self):
        cases = {"B_HIGHER": {(1, 35): 25000, (2, 35): 25000},
                 "UNRESOLVED": {(1, 35): 21207 + 200, (2, 35): 15000},        # pass A inside 1 % (212)
                 "UNRESOLVED ": {(1, 35): 25000, (2, 35): 15000}}             # opposite signs
        for want, ch in cases.items():
            self.assertEqual(run(b=dict(ev=ev_with(B_EV, ch)))["cost"]["verdict"], want.strip(), want)
        self.assertEqual(run(b=dict(ev=ev_with(B_EV, {(1, 35): 21207 - 213, (2, 35): 21139 - 212})))["cost"]["verdict"],
                         "B_LOWER")                                           # both just outside 1 %

    def test_compute_rule(self):
        self.assertEqual(run(b=dict(ev=ev_with(B_EV, {(1, 48): 2305})))["compute"]["verdict"], "COMPUTE_CHANGED")
        self.assertEqual(run(b=dict(ev=ev_with(B_EV, {(1, 51): 1151})))["compute"]["verdict"], "COMPUTE_CHANGED")

    def assert_stop(self, r, text):
        self.assertEqual(r["outcome"], "NOT_INTERPRETED", text)
        self.assertNotIn("cost", r)
        self.assertTrue(any(text in s for s in r["stops"]), (text, r["stops"]))

    def test_placement_stops(self):
        for over, text in ((dict(placement=0), "placement B: run 0: placement"),
                           (dict(arena_base=0x700015C0, base1=0x700015C0), "arena_base"),
                           (dict(regioncfg_irq=0x15F), "regioncfg_irq"), (dict(qconfig_irq=2), "qconfig_irq"),
                           (dict(schema=3), "schema"), (dict(base1=0x310615D0), "base1"),
                           (dict(base_size1=0xFC10), "base_size1"), (dict(base2=0x31060000), "A/B differ: record base2"),
                           (dict(model_len=5584), "model_len")):
            self.assert_stop(run(b=dict(rec=over)), text)
        self.assert_stop(run(b=dict(flags=REQUIRED)), "REGIONCFG_MATCH")
        self.assert_stop(run(a=dict(rec=dict(arena_base=0x710015C0, base1=0x710015C0))), "placement A")
        self.assert_stop(run(b=dict(caps=dict(CAPS, ta_ext_rlatency=99))), "capabilities ta_ext_rlatency")
        self.assert_stop(run(b=dict(caps=dict(CAPS, mem_attr0=4))), "capabilities mem_attr0")

    def test_output_and_gate_c_stops(self):
        bad = bytearray(REF); bad[0] ^= 1
        self.assert_stop(run(b=dict(out=bytes(bad), rec=dict(ofm_mismatch=1, ofm_max_diff=1))), "gate C B")
        self.assert_stop(run(b=dict(out=bytes(bad), rec=dict(ofm_mismatch=1, ofm_max_diff=1))), "output CRC")
        self.assert_stop(run(b=dict(valid=False)), "gate C B")
        self.assert_stop(run(b_blob=A_BLOB), "gate B")

    def test_p1_stops(self):
        for ch, text in (({(1, 48): 2305}, "pass 1 event 48"), ({(1, 51): 1153}, "pass 1 event 51"),
                         ({(2, 391): 3457}, "pass 2 event 391"), ({(2, 128): 305}, "pass 2 event 128"),
                         ({(1, 35): 21207 + 368}, "NPU_ACTIVE")):
            ev = ev_with(A_EV, ch)
            self.assert_stop(run(a=dict(ev=ev), b=dict(ev=ev_with(B_EV, {k: v for k, v in ch.items()
                                                                          if k[1] in (48, 51)}))), text)
        r = run(a=dict(ev=ev_with(A_EV, {(1, 35): 21207 + 365})))                  # median +366.5 <= Stage 4 range 367
        self.assertEqual(r["p1"]["verdict"], "PASS")

    def test_traffic_stops(self):
        for ch in ({(2, 391): 3456}, {(2, 386): 1437}, {(2, 130): 2016}, {(2, 135): 252}, {(2, 391): 4000}):
            r = run(b=dict(ev=ev_with(B_EV, ch)))
            self.assert_stop(r, "traffic: TRAFFIC_INCONSISTENT")


if __name__ == "__main__":
    unittest.main()
