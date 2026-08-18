"""The V14 verdict, and everything it refuses to say.

The analyzer's job is mostly refusal. It is handed nine cells of ten runs and
asked what the campaign showed, and almost every interesting answer -- a
latency, a comparison between variants, a claim that two registers changed at
the same instant -- is one the design forbids. What it may conclude is narrow
and the rows below are all of it.
"""

import unittest

from host import analyze_pmu_completion_visibility_v14 as analyzer


ORDERS = (("Q", "QS", "SQ"), ("QS", "SQ", "Q"), ("SQ", "Q", "QS"))
RUNS = 10


def cell(round_index, position, variant, category=None, *, boot=None, runs=RUNS,
         first_run=1, attempt=1, p0=100, p1=None, excursion=False):
    """One matrix cell, built the way the collector hands one over."""

    boot_id = boot or "boot-%d-%d" % (round_index, position)
    samples = []
    for offset in range(runs):
        run_id = first_run + offset
        cycles = (p1 if p1 is not None else p0 + 66)
        if excursion and offset >= runs - 2:
            cycles += 26 * (offset - runs + 3)
        samples.append(
            {
                "run_id": run_id,
                "boot_id": boot_id,
                "sample_valid": True,
                "category": category,
                "q_observation_cycles": cycles,
                "first_q_done": 1 if category in ("Q_FIRST", "SAME_ITERATION") else 0,
                "first_cmd_end_reached": 1 if category in ("S5_FIRST", "SAME_ITERATION") else 0,
                "convergence_iterations": 3,
                "convergence_timeout": 0,
            }
        )
    return {
        "round": round_index,
        "position": position,
        "variant": variant,
        "attempt": attempt,
        "boot_id": boot_id,
        "samples": samples,
    }


def campaign(qs_category, sq_category, *, q_excursion=True, q_floor=100, dual_excursion=True):
    """A balanced nine-cell campaign with the two dual verdicts asked for."""

    cells = []
    for round_index, order in enumerate(ORDERS, start=1):
        for position, variant in enumerate(order, start=1):
            if variant == "Q":
                cells.append(cell(round_index, position, "Q", None,
                                  p0=q_floor, excursion=q_excursion))
            else:
                category = qs_category if variant == "QS" else sq_category
                cells.append(cell(round_index, position, variant, category,
                                  excursion=dual_excursion))
    return {"identity": {"image_sha256": "b" * 64}, "cells": cells}


class AnalyzerRedTests(unittest.TestCase):
    # --- the five rows -----------------------------------------------------
    def test_order_reversal_concludes_read_order_bias(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "S5_FIRST"))
        self.assertEqual(verdict["conclusion"], analyzer.READ_ORDER_BIAS_DOMINATES)

    def test_q_first_in_both_dual_variants_requires_the_control(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "Q_FIRST"))
        self.assertEqual(verdict["conclusion"], analyzer.CONTROL_REQUIRED)

    def test_s5_first_in_both_dual_variants_requires_the_control(self):
        verdict = analyzer.analyze(campaign("S5_FIRST", "S5_FIRST"))
        self.assertEqual(verdict["conclusion"], analyzer.CONTROL_REQUIRED)

    def test_same_iteration_in_both_resolves_no_gap(self):
        verdict = analyzer.analyze(campaign("SAME_ITERATION", "SAME_ITERATION"))
        self.assertEqual(verdict["conclusion"], analyzer.NO_GAP_RESOLVED)

    def test_a_mixed_campaign_is_unresolved(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        # One QS cell disagrees with the other two: nothing stable to conclude.
        for entry in data["cells"]:
            if entry["variant"] == "QS" and entry["round"] == 2:
                for sample in entry["samples"]:
                    sample["category"] = "SAME_ITERATION"
                    sample["first_cmd_end_reached"] = 1
                break
        self.assertEqual(analyzer.analyze(data)["conclusion"], analyzer.UNRESOLVED)

    # --- what it must never say -------------------------------------------
    def test_the_verdict_never_carries_a_latency_or_a_comparison(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "S5_FIRST"))
        text = repr(verdict).lower()
        for forbidden in ("latency", "t_npu", "speedup", "faster", "slower"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertTrue(verdict["not_performance_metric"])
        self.assertTrue(verdict["not_comparable_to_v13"])
        self.assertTrue(verdict["perturbed_by_convergence_tail"])
        self.assertFalse(verdict["cross_variant_cycle_comparison"])
        self.assertFalse(verdict["physical_simultaneity_claimed"])

    # --- floor reproduction -------------------------------------------------
    def test_a_floor_needs_the_same_minimum_in_all_three_q_boots(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "S5_FIRST"))
        self.assertEqual(verdict["q_floor"]["status"], analyzer.REPRODUCED)
        data = campaign("Q_FIRST", "S5_FIRST")
        for entry in data["cells"]:
            if entry["variant"] == "Q" and entry["round"] == 3:
                for sample in entry["samples"]:
                    sample["q_observation_cycles"] += 1
                break
        self.assertEqual(
            analyzer.analyze(data)["q_floor"]["status"], analyzer.NOT_REPRODUCED
        )

    def test_excursion_structure_needs_values_above_the_floor_in_two_boots(self):
        flat = campaign("Q_FIRST", "S5_FIRST", q_excursion=False)
        self.assertEqual(analyzer.analyze(flat)["q_floor"]["excursion"], analyzer.NOT_REPRODUCED)

    def test_a_qualitative_disagreement_between_q_and_the_dual_variants_forces_the_control(self):
        # Q reproduces, the dual variants do not.
        data = campaign("Q_FIRST", "S5_FIRST", dual_excursion=False)
        self.assertEqual(analyzer.analyze(data)["conclusion"], analyzer.CONTROL_REQUIRED)
        # And the other direction.
        data = campaign("Q_FIRST", "S5_FIRST", q_excursion=False)
        self.assertEqual(analyzer.analyze(data)["conclusion"], analyzer.CONTROL_REQUIRED)

    def test_historical_v13_never_satisfies_the_control(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "Q_FIRST"))
        self.assertIn("S5", verdict["control_required"])
        self.assertIn("V13", verdict["control_required"])

    # --- campaign shape -----------------------------------------------------
    def test_a_short_cell_is_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"][0]["samples"] = data["cells"][0]["samples"][:-1]
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_run_ids_that_are_not_exactly_one_to_ten_are_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"][0]["samples"][0]["run_id"] = 11
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_two_boot_ids_inside_one_cell_are_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"][0]["samples"][5]["boot_id"] = "another-boot"
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_an_unbalanced_matrix_is_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"] = data["cells"][:-1]
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_a_duplicate_cell_is_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"][1] = dict(data["cells"][0])
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_an_invalid_sample_anywhere_is_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        data["cells"][4]["samples"][2]["sample_valid"] = False
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_a_q_cell_that_carries_a_category_is_refused(self):
        data = campaign("Q_FIRST", "S5_FIRST")
        for entry in data["cells"]:
            if entry["variant"] == "Q":
                for sample in entry["samples"]:
                    sample["category"] = "Q_FIRST"
                break
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(data)

    def test_per_boot_counts_are_reported_without_promotion(self):
        verdict = analyzer.analyze(campaign("Q_FIRST", "S5_FIRST"))
        self.assertEqual(len(verdict["per_boot_categories"]), 6)
        for entry in verdict["per_boot_categories"].values():
            self.assertEqual(sum(entry.values()), RUNS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


def campaign_with_structure(q_values, dual_values, qs="Q_FIRST", sq="S5_FIRST", q_boots=None):
    """A balanced campaign with per-boot cycle values chosen by the caller."""

    cells = []
    q_index = 0
    for round_index, order in enumerate(ORDERS, start=1):
        for position, variant in enumerate(order, start=1):
            boot = "b-%d-%d" % (round_index, position)
            if variant == "Q":
                if q_boots is not None:
                    boot = q_boots[q_index]
                values = q_values[q_index]
                q_index += 1
                entry = cell(round_index, position, "Q", None, boot=boot)
            else:
                values = dual_values[(round_index - 1)]
                entry = cell(round_index, position, variant,
                             qs if variant == "QS" else sq, boot=boot)
            for offset, sample in enumerate(entry["samples"]):
                sample["q_observation_cycles"] = values[offset % len(values)]
            cells.append(entry)
    return {"identity": {"image_sha256": "b" * 64}, "cells": cells}


class AnalyzerStructureTests(unittest.TestCase):
    """The two ways a verdict could be published that the design forbids."""

    def test_a_floor_disagreement_forces_the_control_in_both_directions(self):
        # Q reproduces its floor, QS does not. Excursion is NOT_REPRODUCED on
        # both, so comparing excursion alone sees no disagreement at all.
        forward = campaign_with_structure(
            q_values=[[100, 166], [100, 100], [100, 100]],
            dual_values=[[100, 100], [200, 200], [300, 300]],
        )
        verdict = analyzer.analyze(forward)
        self.assertEqual(verdict["q_floor"]["status"], analyzer.REPRODUCED)
        self.assertEqual(verdict["dual_structure"]["QS"]["status"], analyzer.NOT_REPRODUCED)
        self.assertEqual(verdict["conclusion"], analyzer.CONTROL_REQUIRED)

        mirrored = campaign_with_structure(
            q_values=[[100, 100], [200, 200], [300, 300]],
            dual_values=[[100, 166], [100, 100], [100, 100]],
        )
        self.assertEqual(analyzer.analyze(mirrored)["conclusion"], analyzer.CONTROL_REQUIRED)

    def test_three_q_cells_on_one_boot_are_not_three_boots(self):
        pooled = campaign_with_structure(
            q_values=[[100, 166], [100, 166], [100, 166]],
            dual_values=[[100, 166], [100, 166], [100, 166]],
            q_boots=["THE-SAME-BOOT", "THE-SAME-BOOT", "THE-SAME-BOOT"],
        )
        with self.assertRaises(analyzer.AnalysisError):
            analyzer.analyze(pooled)

    def test_a_campaign_whose_cells_are_all_distinct_boots_is_accepted(self):
        fine = campaign_with_structure(
            q_values=[[100, 166], [100, 166], [100, 166]],
            dual_values=[[100, 166], [100, 166], [100, 166]],
        )
        self.assertEqual(analyzer.analyze(fine)["conclusion"], analyzer.READ_ORDER_BIAS_DOMINATES)
