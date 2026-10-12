import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fast_ext_outcome as F  # noqa: E402


class Outcome(unittest.TestCase):
    def test_explains_at_and_below_bound(self):
        self.assertEqual(F.outcome("SCREENED", 125, 100, 1000), "FAST_PATH_EXPLAINS")
        self.assertEqual(F.outcome("SCREENED", 90, 100, 1000), "FAST_PATH_EXPLAINS")

    def test_partial_between_bounds(self):
        self.assertEqual(F.outcome("SCREENED", 126, 100, 1000), "FAST_PATH_PARTIAL")
        self.assertEqual(F.outcome("SCREENED", 799, 100, 1000), "FAST_PATH_PARTIAL")

    def test_not_cause_at_and_above_bound(self):
        self.assertEqual(F.outcome("SCREENED", 800, 100, 1000), "FAST_PATH_NOT_CAUSE")
        self.assertEqual(F.outcome("SCREENED", 1200, 100, 1000), "FAST_PATH_NOT_CAUSE")

    def test_not_screened_is_unproven(self):
        for o in ("UNPROVEN", "NOT_EXECUTABLE"):
            self.assertEqual(F.outcome(o, 90, 100, 1000), "UNPROVEN")

    def test_outcomes_closed_set(self):
        got = {F.outcome(o, r, 100, 1000) for o in ("SCREENED", "UNPROVEN") for r in (90, 500, 900)}
        self.assertEqual(got, set(F.OUTCOMES))


if __name__ == "__main__":
    unittest.main()
