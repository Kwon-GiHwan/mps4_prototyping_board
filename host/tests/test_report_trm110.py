import json, re, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import report_trm110 as R


class T(unittest.TestCase):
    def test_regenerates_110_rows_matching_trm_and_raw(self):
        trm, vals = R.build()
        text = R.OUT.read_text()
        rows = [l for l in text.split("\n") if re.match(r"^\| \d+ \| `[a-z0-9_]+` \|", l)]
        self.assertEqual(len(rows), 110)
        ids = [int(l.split("|")[1]) for l in rows]
        self.assertEqual(sorted(ids), sorted(v for v, _, _ in trm)); self.assertEqual(len(set(ids)), 110)
        # every value cell equals the raw record (spot-check all rows, rep 1..3)
        raw = [r for r in json.loads((R.B / "raw_runs.json").read_text()) if "pmu" in r]
        for l in rows:
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            ev = int(c[0]); reps = [int(c[4]), int(c[5]), int(c[6])]
            got = []
            for rep in (1, 2, 3):
                x = next(x for x in raw if x["rep"] == rep and ev in x["pmu"]["event_codes"])
                got.append(x["pmu"]["event_values"][x["pmu"]["event_codes"].index(ev)])
            self.assertEqual(reps, got, f"ev {ev}")

    def test_no_interpretation_words(self):
        text = R.OUT.read_text()
        for bad in ("faster", "slower", "efficien", "bottleneck", "병목", "성능이 ", "utilization"):
            self.assertNotIn(bad, text)


if __name__ == "__main__":
    unittest.main()
