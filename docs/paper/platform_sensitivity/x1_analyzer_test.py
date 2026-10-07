#!/usr/bin/env python3
"""Mutation / rejection tests for the X1 analyzer.

Every rejection rule named in the frozen contract must be provably able to
fire, and the metric arithmetic must reproduce the paper's frozen definitions.
"""
import copy
import unittest

import x1_analyzer as X


def cell(w, npu, mac, plat, cyc, sha="A" * 8):
    return {"workload": w, "npu": npu, "mac": mac, "platform": plat,
            "ta_state": X.TA[plat], "vela_artifact_sha256": sha,
            "axf_sha256": "f" * 8, "cycles": cyc, "runs_exact_equal": True}


def u65_set():
    """Two workloads x 2 MACs x 3 platforms, artifact-identical."""
    out = []
    base = {("w1", 256): 1000, ("w1", 512): 600,
            ("w2", 256): 4000, ("w2", 512): 2500}
    for plat, k in (("SSE-300", 1.0), ("SSE-310", 0.5), ("SSE-315", 0.5)):
        for (w, m), v in base.items():
            out.append(cell(w, "ethos-u65", m, plat, int(v * k),
                            sha="art-%s-%d" % (w, m)))
    return out


class TestGates(unittest.TestCase):
    def test_valid_set_passes(self):
        self.assertTrue(X.validate(u65_set()))

    def test_wrong_platform_label_rejects(self):
        c = u65_set(); c[0]["platform"] = "SSE-999"
        with self.assertRaises(X.Reject): X.validate(c)

    def test_wrong_ta_classification_rejects(self):
        c = u65_set(); c[0]["ta_state"] = "TA_OFF"   # SSE-300 is TA_ON
        with self.assertRaises(X.Reject): X.validate(c)

    def test_artifact_hash_mismatch_rejects(self):
        c = u65_set()
        for x in c:
            if x["platform"] == "SSE-315" and x["workload"] == "w1" and x["mac"] == 256:
                x["vela_artifact_sha256"] = "DIFFERENT"
        with self.assertRaises(X.Reject): X.validate(c)

    def test_missing_mac_point_rejects(self):
        c = [x for x in u65_set()
             if not (x["platform"] == "SSE-310" and x["mac"] == 512
                     and x["workload"] == "w1")]
        with self.assertRaises(X.Reject): X.validate(c)

    def test_non_exact_repetition_rejects(self):
        c = u65_set(); c[0]["runs_exact_equal"] = False
        with self.assertRaises(X.Reject): X.validate(c)

    def test_wav2letter_low_mac_u55_rejects(self):
        c = [cell("wav2letter_pruned_int8", "ethos-u55", 32, "SSE-300", 10),
             cell("wav2letter_pruned_int8", "ethos-u55", 32, "SSE-310", 10)]
        with self.assertRaises(X.Reject): X.validate(c)

    def test_workload_pair_mismatch_rejects(self):
        c = u65_set()
        for x in c:
            if x["platform"] == "SSE-315" and x["workload"] == "w2":
                x["workload"] = "w3"
        pp = X.per_platform(c)
        with self.assertRaises(X.Reject):
            X.compare(pp, "ethos-u65", "SSE-310", "SSE-315", "A")

    def test_missing_platform_rejects(self):
        c = [x for x in u65_set() if x["platform"] != "SSE-315"]
        pp = X.per_platform(c)
        with self.assertRaises(X.Reject):
            X.compare(pp, "ethos-u65", "SSE-310", "SSE-315", "A")


class TestNoForbiddenAggregation(unittest.TestCase):
    def test_classes_are_reported_separately(self):
        """CLASS A and CLASS B must never be pooled into one statistic."""
        c = u65_set()
        pp = X.per_platform(c)
        a = X.compare(pp, "ethos-u65", "SSE-310", "SSE-315", "A")
        b = X.compare(pp, "ethos-u65", "SSE-300", "SSE-310", "B")
        self.assertEqual(a["class"], "A")
        self.assertEqual(b["class"], "B")
        self.assertNotEqual((a["platform_A"], a["platform_B"]),
                            (b["platform_A"], b["platform_B"]))

    def test_no_cross_platform_ratio_or_score_emitted(self):
        c = u65_set()
        pp = X.per_platform(c)
        r = X.compare(pp, "ethos-u65", "SSE-300", "SSE-310", "B")
        import re
        flat = repr(r).lower()
        # word-boundary matching: 'saturation' legitimately contains 'ratio'
        for banned in (r"\bratio\b", r"\bpercent\b", r"\bfaster\b",
                       r"\bslower\b", r"robustness_score", r"speedup_vs",
                       r"cycle_error", r"cross_platform_geomean"):
            self.assertIsNone(re.search(banned, flat),
                              "forbidden term %s present" % banned)
        # raw cycles never appear in a cross-platform comparison record
        self.assertNotIn("cycles", r)

    def test_normalization_is_within_platform_only(self):
        c = u65_set()
        pp = X.per_platform(c)
        n300 = pp[("SSE-300", "ethos-u65")]["normalized"][256]
        n310 = pp[("SSE-310", "ethos-u65")]["normalized"][256]
        # a uniform platform scale factor must cancel inside each platform
        self.assertEqual(sorted(n300.values()), sorted(n310.values()))


class TestFrozenMetricDefinitions(unittest.TestCase):
    def test_adjacent_and_cumulative_efficiency(self):
        c = [cell("w", "ethos-u65", 256, "SSE-300", 1000),
             cell("w", "ethos-u65", 512, "SSE-300", 600)]
        pp = X.per_platform(c)
        r = pp[("SSE-300", "ethos-u65")]
        self.assertAlmostEqual(r["adjacent"]["w"][512], (1000/600)/2, places=6)
        self.assertAlmostEqual(r["cumulative"]["w"][512], (1000/600)/2, places=6)

    def test_class_thresholds(self):
        self.assertEqual(X.cls(0.80), "STRONG")
        self.assertEqual(X.cls(0.75), "STRONG")
        self.assertEqual(X.cls(0.60), "PARTIAL")
        self.assertEqual(X.cls(0.50), "PARTIAL")
        self.assertEqual(X.cls(0.49), "WEAK_OR_SATURATED")

    def test_saturation_rule(self):
        c = [cell("w", "ethos-u65", 256, "SSE-300", 1000),
             cell("w", "ethos-u65", 512, "SSE-300", 900)]   # adjacent ~0.55 -> none
        pp = X.per_platform(c)
        self.assertEqual(pp[("SSE-300", "ethos-u65")]["saturation"]["w"],
                         "NONE_OBSERVED")
        c2 = [cell("w", "ethos-u65", 256, "SSE-300", 1000),
              cell("w", "ethos-u65", 512, "SSE-300", 990)]  # adjacent ~0.505.. -> none
        c3 = [cell("w", "ethos-u65", 256, "SSE-300", 1000),
              cell("w", "ethos-u65", 512, "SSE-300", 1100)]  # adjacent < 0.5 -> 512
        pp3 = X.per_platform(c3)
        self.assertEqual(pp3[("SSE-300", "ethos-u65")]["saturation"]["w"], 512)

    def test_spearman_identical_and_reversed(self):
        self.assertAlmostEqual(X.spearman([1, 2, 3], [1, 2, 3]), 1.0, places=9)
        self.assertAlmostEqual(X.spearman([1, 2, 3], [3, 2, 1]), -1.0, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=1)
