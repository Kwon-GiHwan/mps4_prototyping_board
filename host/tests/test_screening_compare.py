import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import screening_compare as C  # noqa: E402


def entry(outcome, **medians):
    return {"outcome": outcome, "summary": {m: ({"median": medians[m]} if m in medians else {}) for m in C.METRICS}}


class RatioRow(unittest.TestCase):
    def test_ratio_is_new_over_old(self):
        row = C.ratio_row(entry("SCREENED", npu_active=200), entry("SCREENED", npu_active=100))
        self.assertEqual(row["npu_active"], 0.5)

    def test_not_screened_gives_none_everywhere(self):
        for old, new in (("UNPROVEN", "SCREENED"), ("SCREENED", "NOT_EXECUTABLE")):
            row = C.ratio_row(entry(old, npu_active=1), entry(new, npu_active=1))
            self.assertTrue(all(v is None for v in row.values()), (old, new))

    def test_zero_or_missing_old_median_gives_none(self):
        self.assertIsNone(C.ratio_row(entry("SCREENED", npu_active=0), entry("SCREENED", npu_active=5))["npu_active"])
        self.assertIsNone(C.ratio_row(entry("SCREENED"), entry("SCREENED", npu_active=5))["npu_active"])

    def test_zero_new_median_is_a_ratio_not_none(self):
        self.assertEqual(C.ratio_row(entry("SCREENED", ext_write_req_stall_ratio=0.1),
                                     entry("SCREENED", ext_write_req_stall_ratio=0.0))["ext_write_req_stall_ratio"], 0.0)


class CmsChanged(unittest.TestCase):
    def test_compares_vela_output_digest(self):
        self.assertFalse(C.cms_changed({"vela_sha256": "a"}, {"vela_sha256": "a"}))
        self.assertTrue(C.cms_changed({"vela_sha256": "a"}, {"vela_sha256": "b"}))


if __name__ == "__main__":
    unittest.main()
