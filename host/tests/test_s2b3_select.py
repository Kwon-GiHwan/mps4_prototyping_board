import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2b3_select as X


class Select(unittest.TestCase):
    def test_largest_contrast(self):
        self.assertEqual(X.select([2000, 40000, 5000, 900000, 100000, 0])[:2], (3, 4))   # 9.0 beats 8.0

    def test_ratio_is_inclusive_and_needs_both_neighbours(self):
        self.assertEqual(X.select([1000, 4000, 1000])[:2], (1, 2))           # exactly 4x
        self.assertIsNone(X.select([1000, 3999, 0]))
        self.assertIsNone(X.select([0, 5000, 1300]))                         # next neighbour too big
        self.assertIsNone(X.select([10 ** 9, 0, 0]))                         # first op has no predecessor
        self.assertIsNone(X.select([0, 0, 10 ** 9]))                         # last op has no successor
        self.assertIsNone(X.select([0, 0, 0]))                               # zero MACs is not a reference

    def test_floor_and_ties(self):
        a, b, c = X.select([0, 4096, 0, 0, 4096, 0])
        self.assertEqual((a, b, c), (1, 2, 4.0))                             # tie -> earlier op; 4096 / FLOOR
        self.assertEqual(X.select([0, 4096, 0, 0, 8192, 0])[:2], (4, 5))     # contrast 8 > 4
        self.assertEqual(X.select([500, 8000, 0, 100, 8000, 0])[:2], (1, 2))  # both / 1024 -> tie -> earlier
        self.assertEqual(X.select([2048, 8192, 0, 0, 8192 * 4, 8192])[:2], (4, 5))  # 4 = 4: more MACs wins


if __name__ == "__main__":
    unittest.main()
