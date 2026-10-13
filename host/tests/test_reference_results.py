import csv, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import reference, results


class Reference(unittest.TestCase):
    def test_event_lists(self):
        d, t = reference.driver_ids(), reference.trm_ids()
        self.assertEqual((len(d), len(t)), (171, 110))
        self.assertTrue(t <= set(d))                                  # TRM-described ids are driver ids
        self.assertEqual((d[35], d[48]), ("npu_active", "mac_active"))

    def test_mlek_reference_is_the_b1_b3_median(self):
        self.assertEqual(reference.mlek_active(), {"kws_micronet_m": 91_431, "ad_medium_int8": 145_976,
                                                   "mobilenet_v2_1.0_224_INT8": 1_448_049})


class Results(unittest.TestCase):
    def write(self, rows):
        p = pathlib.Path(tempfile.mkdtemp()) / "runs.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["rep", "ev_type", "event_value", "event_overflow", "run_valid", "window_cycles"])
            w.writeheader(); w.writerows(rows)
        return p

    def test_load_runs_names_events_and_keeps_invalid(self):
        p = self.write([dict(rep=2, ev_type=35, event_value=10, event_overflow=0, run_valid=True, window_cycles=50),
                        dict(rep=2, ev_type=999, event_value=3, event_overflow=1, run_valid=True, window_cycles=50),
                        dict(rep=1, ev_type=35, event_value="", event_overflow=0, run_valid=False, window_cycles="")])
        runs = results.load_runs(p)
        self.assertEqual([r["rep"] for r in runs], [1, 2])            # sorted by rep
        self.assertEqual((runs[1]["npu_active"], runs[1]["ev999"], runs[1]["overflow"]), (10, 3, True))
        self.assertEqual((runs[0]["npu_active"], runs[0]["valid"], runs[0]["window_cycles"]), (None, False, None))

    def test_measured_valid_drops_warmup_and_invalid(self):
        runs = [dict(rep=r, valid=(r != 7)) for r in range(1, 11)]
        self.assertEqual([r["rep"] for r in results.measured_valid(runs)], [6, 8, 9, 10])


if __name__ == "__main__":
    unittest.main()
