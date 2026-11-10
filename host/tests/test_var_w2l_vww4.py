import csv, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import var_w2l_vww4 as V

BEATS = dict(SRAM_RD_DATA_BEAT_RECEIVED=463085, SRAM_WR_DATA_BEAT_WRITTEN=40950, EXT_RD_DATA_BEAT_RECEIVED=1836882,
             EXT_WR_DATA_BEAT_WRITTEN=19045)


def uart(active, beats=BEATS, ta=2, end=True):
    lines = ["INFO - Configured TA_SRAM"] * ta + ["Profile for Inference:", f"INFO - NPU ACTIVE: {active} cycles"]
    lines += [f"INFO - NPU {k}: {v} beats" for k, v in beats.items()] + ["INFO - NPU TOTAL: 1 cycles", "done"]
    return "\r\n".join(lines + (["program terminating"] if end else [])) + "\r\n"


def runs(d, actives):
    d.mkdir(parents=True, exist_ok=True)
    rows = [dict(set_id=1, rep=i + 1, ev_type=35, event_value=a, run_valid="True", window_cycles=1, infer_npu_cycles=1,
                 infer_cpu_cycles=1, infer_sys_ticks="", host_run_s="", event_overflow="False")
            for i, a in enumerate(actives)]
    with (d / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


class Shift(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(V.shift([10, 11, 12, 13], [5, 6, 7, 8], 4), "SHIFT_REPRODUCED")
        self.assertEqual(V.shift([5, 6, 7, 8], [10, 11, 12, 13], 4), "SHIFT_REVERSED")
        self.assertEqual(V.shift([10, 14, 12, 13], [11, 13, 12, 15], 4), "NO_SHIFT")
        self.assertEqual(V.shift([10, 14, 12, 13], [11, 13, 12, 9], 4), "NO_SHIFT")      # lower but overlapping
        self.assertEqual(V.shift([10, 11, 12, 13], [5, 6, 7, 8], 5), "UNPROVEN")       # a boot missing
        self.assertEqual(V.shift([100, 100, 100, 120], [119, 140, 140, 140], 4), "UNPROVEN")   # overlap, medians apart

    def test_capture_validity(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.raw"
            p.write_bytes(uart(5).encode()); self.assertEqual(V.capture(p)["ACTIVE"], 5)
            p.write_bytes(uart(5, ta=1).encode()); self.assertIsNone(V.capture(p))
            p.write_bytes(uart(5, end=False).encode()); self.assertIsNone(V.capture(p))
            self.assertIsNone(V.capture(pathlib.Path(t) / "missing.raw"))


class Parts(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.m = pathlib.Path(self.t.name) / "main"
        self.d = pathlib.Path(self.t.name) / "drv"

    def tearDown(self):
        self.t.cleanup()

    def mlek(self, model, variant, actives):
        for i, a in enumerate(actives, 1):
            p = self.m / f"evidence/equiv_c/raw_bc/{model}/{variant}/B{i}/app_uart.raw"
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(uart(a).encode())

    def test_w_part(self):
        self.mlek(V.W2L, "stock", [4132211, 4133890, 4133959]); self.mlek(V.W2L, "events", [4130708, 4131099, 4131728])
        vals = dict(W1_stock=4133000, W2_events=4130000, W3_events=4130500, W4_stock=4133500, W5_events=4131000,
                    W6_stock=4132500, W7_stock=4134000, W8_events=4130800)
        for k, a in vals.items():
            p = self.d / "evidence/var_w2l_vww4/raw" / k / "app_uart.raw"
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(uart(a).encode())
        w = V.w_part(self.m, self.d)
        self.assertEqual((w["W1"], w["W2"]), ("SHIFT_REPRODUCED", "BEATS_FIXED"))
        p = self.d / "evidence/var_w2l_vww4/raw/W8_events/app_uart.raw"
        p.write_bytes(uart(4130800, beats=dict(BEATS, EXT_WR_DATA_BEAT_WRITTEN=19046)).encode())
        self.assertEqual(V.w_part(self.m, self.d)["W2"], "BEATS_DIFFER")
        p.unlink()
        self.assertEqual(V.w_part(self.m, self.d)["W1"], "UNPROVEN")

    def test_v_part(self):
        self.mlek(V.VWW4, "stock", [233394, 234749, 232761]); self.mlek(V.VWW4, "events", [232991, 236774, 233762])
        for r, base in zip(V.DRIVER_VWW4, (233000, 234000, 235000)):
            runs(self.d / r / V.VWW4, [base + 900, base + 800] + [base + k for k in (-100, 0, 100)])
        v = V.v_part(self.m, self.d)
        self.assertEqual(v["V2"], "DRIVER_WITHIN_MLEK_RANGE")
        self.assertEqual(v["V1_V4_descriptive"]["driver_first_run"], [233900, 234900, 235900])
        runs(self.d / V.DRIVER_VWW4[2] / V.VWW4, [1, 1, 240000, 240000, 240000])
        self.assertEqual(V.v_part(self.m, self.d)["V2"], "DRIVER_OUTSIDE_MLEK_RANGE")
        (self.d / V.DRIVER_VWW4[1] / V.VWW4 / "runs.csv").unlink()
        self.assertEqual(V.v_part(self.m, self.d)["V2"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
