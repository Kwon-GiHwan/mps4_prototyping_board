import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "board"))
import run_pmu_events as R


class Stage0Window(unittest.TestCase):
    """The inference window is computed from the start seam, not from the runner window (PMCCNTR)."""
    def test_older_record_has_no_window(self):
        w = R.stage0_window({"npu_pmu_window_cycles": 1000}, [1, 0, 0, 0, 0, 0, 0] + [None] * 15)
        self.assertIsNone(w["infer_npu_cycles"]); self.assertIsNone(w["start_seam_fired"])

    def test_window_differences(self):
        # trailing: 7 old words, then fired, start_lo, start_hi, start_dwt, end_dwt, start_sys, end_sys, cntcr
        tr = [1, 0, 0, 0, 0, 0, 0, 1, 0xFFFFFFF0, 0, 4_000_000_000, 100, 7, 12, 1] + [None] * 15
        w = R.stage0_window({"npu_pmu_window_cycles": (1 << 32) + 0x20}, tr)
        self.assertEqual(w["infer_npu_cycles"], 0x30)                     # 64-bit start, carries across lo/hi
        self.assertEqual(w["infer_cpu_cycles"], (100 - 4_000_000_000) & 0xFFFFFFFF)   # DWT wraps
        self.assertEqual(w["infer_sys_ticks"], 5)
        self.assertEqual((w["start_seam_fired"], w["sys_cntcr"]), (1, 1))

    def test_start_high_word_counts(self):
        tr = [1, 0, 0, 0, 0, 0, 0, 1, 0x10, 1, 0, 0, 0, 0, 1] + [None] * 15
        w = R.stage0_window({"npu_pmu_window_cycles": (2 << 32) + 0x20}, tr)
        self.assertEqual(w["infer_npu_cycles"], (1 << 32) + 0x10)


if __name__ == "__main__":
    unittest.main()
