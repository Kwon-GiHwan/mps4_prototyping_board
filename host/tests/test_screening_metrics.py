import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import screening_metrics as S

GOOD = {35: 1000, 48: 800, 386: 300, 391: 100, 387: 50, 392: 20, 393: 10, 396: 2000}


def write(root, name, reps=35, invalid=(), values=GOOD, window=4000, n_mac=1024 * 500, overflow=False):
    (root / "workloads").mkdir(exist_ok=True)
    json.dump(dict(n_mac=n_mac, op_counts={"CONV_2D": 1},
                   vela=dict(cycles_total=1100.0, cycles_npu=900.0, nn_macs=float(n_mac))),
              open(root / "workloads" / f"{name}.meta.json", "w"))
    (root / name).mkdir()
    with open(root / name / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rep", "ev_type", "event_value", "event_overflow", "run_valid", "window_cycles"])
        w.writeheader()
        for rep in range(1, reps + 1):
            for ev, v in values.items():
                w.writerow(dict(rep=rep, ev_type=ev, event_value=v, event_overflow=overflow,
                                run_valid=rep not in invalid, window_cycles=window))


class Outcome(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def test_screened_and_metrics(self):
        write(self.root, "w")
        r = S.workload(self.root, "w")
        self.assertEqual(r["outcome"], "SCREENED")
        self.assertEqual(r["valid_measured"], 30)                      # 5 warm-up RUNs dropped
        s = r["summary"]
        self.assertAlmostEqual(s["npu_active_ratio"]["median"], 0.25)
        self.assertAlmostEqual(s["peak_mac_efficiency"]["median"], 0.5)  # 1024*500 / (1024*1000)
        self.assertAlmostEqual(s["mac_active_ratio"]["median"], 0.8)
        self.assertAlmostEqual(s["ext_beats_per_mac"]["median"], 400 / (1024 * 500))
        self.assertAlmostEqual(s["ext_read_req_stall_ratio"]["median"], 50 / 2000)
        self.assertAlmostEqual(r["m7"]["vela_signed_error"], 0.1)

    def test_warmup_failures_do_not_count(self):
        write(self.root, "w", invalid=(1, 2, 3))
        self.assertEqual(S.workload(self.root, "w")["outcome"], "SCREENED")

    def test_fewer_than_30_valid_is_unproven(self):
        write(self.root, "w", invalid=(6,))
        self.assertEqual(S.workload(self.root, "w")["outcome"], "UNPROVEN")

    def test_consistency_fail_is_unproven(self):
        write(self.root, "w", values={**GOOD, 48: 1500})          # mac_active > npu_active
        r = S.workload(self.root, "w")
        self.assertEqual(r["outcome"], "UNPROVEN")
        self.assertIn("mac_active>npu_active", next(iter(r["consistency_fails"].values())))

    def test_stall_above_enabled_is_unproven(self):
        write(self.root, "w", values={**GOOD, 387: 2500})
        self.assertEqual(S.workload(self.root, "w")["outcome"], "UNPROVEN")

    def test_window_below_npu_active_is_unproven(self):
        write(self.root, "w", window=900)
        self.assertEqual(S.workload(self.root, "w")["outcome"], "UNPROVEN")

    def test_overflow_is_unproven(self):
        write(self.root, "w", overflow=True)
        self.assertEqual(S.workload(self.root, "w")["outcome"], "UNPROVEN")

    def test_no_valid_run_is_not_executable(self):
        write(self.root, "w", invalid=tuple(range(1, 36)))
        self.assertEqual(S.workload(self.root, "w")["outcome"], "NOT_EXECUTABLE")

    def test_missing_campaign_is_not_executable(self):
        json.dump(dict(n_mac=1, op_counts={}, vela=dict(cycles_total=1.0, cycles_npu=1.0, nn_macs=1.0)),
                  open(self.root / "x.json", "w"))
        (self.root / "workloads").mkdir(); (self.root / "x.json").rename(self.root / "workloads" / "w.meta.json")
        self.assertEqual(S.workload(self.root, "w")["outcome"], "NOT_EXECUTABLE")

    def test_outcomes_closed_set(self):
        write(self.root, "w")
        self.assertIn(S.workload(self.root, "w")["outcome"], S.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
