"""stage4c2b.py: hypothesis values, the per-config verdict, and the reference gate on synthetic folders."""
import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import stage4c2b as P
from test_stage4c1 import write
from test_stage4c2 import add_mac

WL = REPO / "evidence/stage4c2b/workloads"


class Rules(unittest.TestCase):
    def test_hypotheses(self):
        self.assertEqual(P.hypotheses(24 * 24 * 96 * 40, 40), dict(H1=2880, H2=4608, H3=5760, H4=3456))
        self.assertEqual(P.hypotheses(24 * 24 * 96 * 48, 48), dict(H1=3456, H2=4608, H3=6912, H4=3456))
        self.assertEqual(P.hypotheses(24 * 24 * 96 * 33, 33)["H4"], 24 * 24 * 96 * 48 / 768)

    def test_verdict(self):
        h = dict(H1=2880, H2=4608, H3=5760, H4=3456)
        self.assertEqual(P.verdict([2880] * 4, True, True, h), "MATCH:H1")
        self.assertEqual(P.verdict([3456] * 4, True, True, dict(h, H1=3456)), "MATCH:H1+H4")
        self.assertEqual(P.verdict([3000] * 4, True, True, h), "NONE_MATCHED")
        self.assertEqual(P.verdict([2880, 2880, 2880, 2881], True, True, h), "MEASUREMENT_UNSTABLE")
        self.assertEqual(P.verdict([2880] * 4, False, True, h), "INVALID")
        self.assertEqual(P.verdict([2880] * 4, True, False, h), "INVALID")

    def test_predictions_from_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            r = P.predict(str(WL), d)
            self.assertTrue(all(r["s4c2_conv_cin40"]["distinct"].values()))
            self.assertFalse(r["s4c2_conv_cin48"]["distinct"]["H1"])
            self.assertEqual(r["s4c2_conv_cin40"]["static"]["traversal"], "DepthFirst")


def comp(wl, name):
    src = json.loads((WL / f"{name}.compile.json").read_text())
    src.update(ofm_shape=[1, 1, 1, 4], quant=dict(ofm_scale=0.1, zero_points=0, ifm_scale=1, weight_scale=1),
               activation="NONE")
    wl.mkdir(exist_ok=True)
    (wl / f"{name}.compile.json").write_text(json.dumps(src))
    (wl / f"{name}.drwl.tflite_ofm.bin").write_bytes(b"\x01\x02\x03\x04")


class Judge(unittest.TestCase):
    def run_it(self, d, mac40, ref_mac=4608, ref_out=b"\x01\x02\x03\x04"):
        root, c2, wl = d / "root", d / "c2", d / "wl"
        macs = {"s4c2_conv_cin40": (mac40, mac40), "s4c2_conv_cin48": (3456, 3456), "s4c2_conv_cin64": (ref_mac, ref_mac)}
        for c, (m, dp) in macs.items():
            add_mac(write(root, c, [600] * 4, [1000] * 4, 0x70000010), m, dp)
            comp(wl, c)
        add_mac(write(c2, "s4c2_conv_cin64", [600] * 4, [1000] * 4, 0x70000010, out=ref_out), 4608, 4608)
        pred = P.predict(str(WL), str(d / "p"))
        return P.judge(str(root), str(wl), str(c2), str(d / "p" / "predictions.json"), str(d / "out"))

    def test_match_and_reference(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_it(pathlib.Path(d), 2880)
            self.assertTrue(r["reference"]["ok"])
            self.assertEqual(r["configs"]["s4c2_conv_cin40"]["verdict"], "MATCH:H1")
            self.assertEqual(r["configs"]["s4c2_conv_cin48"]["verdict"], "MATCH:H1+H4")
        with tempfile.TemporaryDirectory() as d:
            r = self.run_it(pathlib.Path(d), 2880, ref_mac=4600)
            self.assertFalse(r["reference"]["ok"])
            self.assertEqual(r["configs"]["s4c2_conv_cin40"]["verdict"], "NOT_JUDGED (REFERENCE_MISMATCH)")
        with tempfile.TemporaryDirectory() as d:
            r = self.run_it(pathlib.Path(d), 2880, ref_out=b"\x01\x02\x03\x05")
            self.assertFalse(r["reference"]["ok"])
        with tempfile.TemporaryDirectory() as d:          # MAC 4,600 now, the old reference's MAC not constant
            d = pathlib.Path(d)
            r = self.run_it(d, 2880)
            f = d / "root" / "conds" / "s4c2_conv_cin64" / "wfe"
            rows = list(csv.DictReader(open(f / "runs.csv")))
            for x in rows:
                if x["ev_type"] == "48":
                    x["event_value"] = 4600
            with open(f / "runs.csv", "w", newline="") as g:
                w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            g2 = d / "c2" / "conds" / "s4c2_conv_cin64" / "wfe"
            rows = list(csv.DictReader(open(g2 / "runs.csv")))
            for x in rows:
                if x["ev_type"] == "48":
                    x["event_value"] = 4600 + int(x["rep"])
            with open(g2 / "runs.csv", "w", newline="") as g:
                w = csv.DictWriter(g, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            r = P.judge(str(d / "root"), str(d / "wl"), str(d / "c2"), str(d / "p" / "predictions.json"), str(d / "o2"))
            self.assertFalse(r["reference"]["ok"])


if __name__ == "__main__":
    unittest.main()
