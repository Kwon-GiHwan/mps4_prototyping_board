"""The inheritance matrix is a design input, so it is checked like one.

A claim with no class does not enter implementation. That rule is worth nothing
unless something enforces it, so this asserts the properties the matrix has to
have before any V15 code is written: every V14 rule appears exactly once, every
class is one of the four, every NOT_APPLICABLE carries a reason, every
REQUALIFIED carries a proof, and every NEW claim names the detector that will
have to exist.

The last one is deliberately a forward reference. The detector does not exist
yet; naming it here is what makes its absence visible later, when a second test
in the implementation chunks will require it to resolve.
"""

import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))
sys.path.insert(0, str(REPO / "firmware" / "Selftest_pmu_diag"))

import inheritance_pmu_completion_s5_only_control as matrix  # noqa: E402


def _v14_rules():
    import check_pmu_completion_visibility_v14 as gate

    return {rule for _claim, _detector, rule in gate.CLAIM_MATRIX}


class EveryClaimIsClassified(unittest.TestCase):
    def test_every_v14_rule_appears_exactly_once(self):
        listed = [row["claim"] for row in matrix.INHERITED_RULES]
        self.assertEqual(len(listed), len(set(listed)), "a rule is listed twice")
        self.assertEqual(set(listed), _v14_rules())

    def test_every_class_is_one_of_the_four(self):
        for row in matrix.ALL_ROWS:
            self.assertIn(row["class"], matrix.CLASSES, row["claim"])

    def test_no_row_carries_more_than_one_class(self):
        # The dict shape makes this structural rather than checkable by
        # inspection, so it is asserted: exactly one class key, never a list.
        for row in matrix.ALL_ROWS:
            self.assertIsInstance(row["class"], str, row["claim"])


class EachClassCarriesWhatItOwes(unittest.TestCase):
    def test_not_applicable_rows_say_why(self):
        # A rule dropped without a reason is indistinguishable from a rule
        # forgotten, and the second is how coverage disappears quietly.
        for row in matrix.ALL_ROWS:
            if row["class"] == matrix.NOT_APPLICABLE:
                self.assertTrue(row["reason"], row["claim"])

    def test_requalified_rows_name_their_proof(self):
        for row in matrix.ALL_ROWS:
            if row["class"] == matrix.REQUALIFIED_FOR_V15:
                self.assertTrue(row["proof"], row["claim"])

    def test_pinned_rows_name_what_pins_them(self):
        for row in matrix.ALL_ROWS:
            if row["class"] == matrix.UNCHANGED_AND_HASH_PINNED:
                self.assertTrue(row["proof"], row["claim"])

    def test_new_claims_name_a_detector(self):
        for row in matrix.ALL_ROWS:
            if row["class"] == matrix.NEW_V15_CLAIM:
                self.assertTrue(row["detector"], row["claim"])

    def test_no_row_is_both_pinned_and_requalified_in_substance(self):
        # A pinned object that also claims to be re-proved is one of the two
        # answers dressed as both; the class is supposed to be a decision.
        for row in matrix.ALL_ROWS:
            if row["class"] == matrix.UNCHANGED_AND_HASH_PINNED:
                self.assertIsNone(row["detector"], row["claim"])


class TheConceptsThatDoNotSurvive(unittest.TestCase):
    def test_the_two_cross_variant_rules_are_not_applicable(self):
        # These are the only two V14 rules whose subject is a *set* of variants.
        # V15 has one, so keeping them alive would mean feeding them an input
        # that does not exist -- a gate answering a question nobody asked.
        dropped = {
            row["claim"]
            for row in matrix.INHERITED_RULES
            if row["class"] == matrix.NOT_APPLICABLE
        }
        self.assertEqual(
            dropped, {"RULE_TAIL_SHARED", "RULE_READ_ORDER_EQUIVALENCE"}
        )

    def test_nothing_else_was_quietly_dropped(self):
        requalified = sum(
            1 for row in matrix.INHERITED_RULES if row["class"] == matrix.REQUALIFIED_FOR_V15
        )
        self.assertEqual(requalified + 2, len(_v14_rules()))


class EveryRequalifiedRuleHasSomewhereToBeProved(unittest.TestCase):
    """"Inherited" is not a place, so each carried rule names one."""

    def test_every_requalified_rule_has_an_application_entry(self):
        requalified = {
            row["claim"]
            for row in matrix.INHERITED_RULES
            if row["class"] == matrix.REQUALIFIED_FOR_V15
        }
        self.assertEqual(set(matrix.APPLICATION), requalified)

    def test_no_application_entry_is_for_a_rule_that_was_dropped(self):
        dropped = {
            row["claim"]
            for row in matrix.INHERITED_RULES
            if row["class"] == matrix.NOT_APPLICABLE
        }
        self.assertFalse(set(matrix.APPLICATION) & dropped)

    def test_every_entry_names_a_layer_a_task_and_a_status(self):
        for rule, entry in matrix.APPLICATION.items():
            layer, task, status = entry
            self.assertTrue(layer, rule)
            self.assertTrue(task.startswith("Task "), rule)
            self.assertIn(status, matrix.STATUSES, rule)

    def test_nothing_claims_to_be_requalified_before_a_v15_artifact_exists(self):
        # There is no V15 source and no V15 image yet, so every carried rule is
        # NOT_YET_APPLIED. This test is what stops the table drifting into
        # optimism ahead of the evidence -- and it will fail, correctly, the day
        # a status is advanced without the artifact to justify it.
        for rule, (_layer, _task, status) in matrix.APPLICATION.items():
            self.assertEqual(status, matrix.NOT_YET_APPLIED, rule)

    def test_the_source_layer_never_claims_the_final_word(self):
        # A source-layer entry may reach SOURCE_CONTRACT_REQUALIFIED and no
        # further: the compiler has not been asked yet, and calling that
        # QUALIFIED would retire the claim early.
        self.assertNotIn("QUALIFIED", matrix.STATUSES)
        self.assertIn(matrix.SOURCE_REQUALIFIED, matrix.STATUSES)
        self.assertNotEqual(matrix.SOURCE_REQUALIFIED, matrix.ELF_REQUALIFIED)

    def test_the_layers_are_the_ones_this_experiment_has(self):
        # A rule assigned to a layer V15 does not build would be an application
        # entry that can never be satisfied.
        layers = {layer for layer, _task, _status in matrix.APPLICATION.values()}
        self.assertTrue(layers <= {"source/generator", "linked ELF"}, layers)

    def test_almost_all_of_the_inheritance_lands_on_the_image(self):
        # Recorded because it corrects the plan: only one carried rule is decided
        # on the source, and calling the rest "the source contract" overstated
        # what exists at that layer.
        by_layer = {}
        for layer, _task, _status in matrix.APPLICATION.values():
            by_layer[layer] = by_layer.get(layer, 0) + 1
        self.assertEqual(by_layer["source/generator"], 1)
        self.assertEqual(by_layer["linked ELF"], 33)


class TheReferenceIsUnambiguous(unittest.TestCase):
    def test_the_v14_reference_names_both_anchors(self):
        for key in ("preboard_anchor", "board_evidence_anchor", "campaign_protocol"):
            self.assertTrue(matrix.V14_REFERENCE[key], key)

    def test_the_reference_artifacts_are_named_not_described(self):
        for key in ("q_reference_artifacts", "q_reference_image"):
            self.assertIn("FINAL8_A/Q", matrix.V14_REFERENCE[key])


class TheNewClaimsCoverTheDesign(unittest.TestCase):
    def test_every_design_gate_has_a_row(self):
        # The design named these; a new claim missing here would be one nobody
        # scheduled a detector for.
        detectors = {row["detector"] for row in matrix.NEW_CLAIMS}
        for required in (
            "verify_single_register_equivalence",
            "verify_s5_only_boundary_image",
            "verify_post_freeze_equivalence",
            "verify_comparison_mode_propagation",
            "verify_poll_count_admission",
        ):
            self.assertIn(required, detectors)


if __name__ == "__main__":
    unittest.main()
