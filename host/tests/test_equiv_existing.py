import csv, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import equiv_existing as E


class Compare(unittest.TestCase):
    def test_exact_and_ranges(self):
        c = E.compare([10, 10, 10], [10, 10])
        self.assertEqual((c["exact"], c["runner_median_in_mlek_range"], c["diff_pct"]), (1, 1, 0.0))
        c = E.compare([100, 102, 104], [99, 99, 110])
        self.assertEqual((c["exact"], c["runner_median_in_mlek_range"], c["ranges_overlap"]), (0, 0, 1))
        self.assertAlmostEqual(c["diff_pct"], -2.941176, places=5)
        self.assertEqual(E.compare([10, 10, 10], [10, 11])["exact"], 0)
        c = E.compare([100, 102, 104], [105, 106])
        self.assertEqual((c["runner_median_in_mlek_range"], c["ranges_overlap"]), (0, 0))
        self.assertEqual(E.compare([100, 102, 104], [102])["runner_median_in_mlek_range"], 1)
        self.assertEqual(E.compare([100, 102, 104], [104, 104])["runner_median_in_mlek_range"], 1)

    def test_runner_values_keep_only_valid_known_events(self):
        rows = [dict(rep=3, ev_type=35, event_value=5, run_valid="True", app_sha256="d0cd4775ab"),
                dict(rep=2, ev_type=35, event_value=6, run_valid="True", app_sha256="d0cd4775ab"),   # warm-up
                dict(rep=3, ev_type=35, event_value=9, run_valid="False", app_sha256="d0cd4775ab"),
                dict(rep=3, ev_type=48, event_value=7, run_valid="True", app_sha256="d0cd4775ab"),
                dict(rep=3, ev_type=130, event_value="", run_valid="True", app_sha256="d0cd4775ab")]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "runs.csv"
            with p.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            vals, image = E.runner_values(p, 2)
        self.assertEqual((vals, image), ({"ACTIVE": [5]}, "d0cd4775"))


if __name__ == "__main__":
    unittest.main()
