"""Known-value and boundary checks for interval report statistics."""

import math
import statistics
import unittest

from host.experiments.interval.stats import series_stats


class IntervalStatistics(unittest.TestCase):
    def test_odd_samples_include_the_median_in_both_quartile_halves(self):
        result = series_stats([9, 1, 3, 2, 4])
        self.assertAlmostEqual(result.pop("cv"), math.sqrt(9.7) / 3.8)
        self.assertEqual(result, {
            "count": 5, "min": 1, "max": 9, "median": 3.0, "mad": 1.0,
            "q1_inclusive": 2.0, "q3_inclusive": 4.0, "iqr_inclusive": 2.0,
        })

    def test_even_samples_use_separate_halves_and_sample_deviation(self):
        result = series_stats([8, 1, 2, 3])
        self.assertAlmostEqual(result.pop("cv"), math.sqrt(29 / 3) / 3.5)
        self.assertEqual(result, {
            "count": 4, "min": 1, "max": 8, "median": 2.5, "mad": 1.0,
            "q1_inclusive": 1.5, "q3_inclusive": 5.5, "iqr_inclusive": 4.0,
        })

    def test_single_sample_has_no_spread_and_zero_mean_has_no_cv(self):
        for value, cv in ((7, 0.0), (0, None)):
            with self.subTest(value=value):
                self.assertEqual(series_stats([value]), {
                    "count": 1, "min": value, "max": value,
                    "median": float(value), "mad": 0.0,
                    "q1_inclusive": float(value), "q3_inclusive": float(value),
                    "iqr_inclusive": 0.0, "cv": cv,
                })
        self.assertIsNone(series_stats([-1, 1])["cv"])

    def test_constant_samples_keep_zero_spread(self):
        result = series_stats([12] * 30)
        self.assertEqual(result["count"], 30)
        for key in ("mad", "iqr_inclusive", "cv"):
            self.assertEqual(result[key], 0.0, key)

    def test_empty_input_is_still_rejected(self):
        with self.assertRaises(statistics.StatisticsError):
            series_stats([])

    def test_input_order_and_contents_are_not_mutated(self):
        values = [8, 1, 2, 3]
        series_stats(values)
        self.assertEqual(values, [8, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
