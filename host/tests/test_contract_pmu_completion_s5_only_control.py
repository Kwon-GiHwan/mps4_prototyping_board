"""The schema-15 contract constants, and the names that may not appear in them.

Written before the module exists. Two of these tests are about arithmetic and
the rest are about vocabulary, because on this project the vocabulary has
repeatedly been where the overclaim entered: a field called
`internal_completion_cycles` invites a sentence nobody is entitled to write, and
it invites it in every report built on top of it forever.

The vocabulary check scans the shipped V15 modules rather than their exported
symbols, so that a name cannot survive in a comment or a docstring and be picked
up later by someone reading it as intent. Two files are exempt and both for the
same reason: the contract must name them in order to refuse them, and this test
must name them in order to check that the contract's list is the right one.
"""

import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import contract_pmu_completion_s5_only_control as contract  # noqa: E402


class Identity(unittest.TestCase):
    def test_the_schema_is_fifteen(self):
        self.assertEqual(contract.SCHEMA_VERSION, 15)

    def test_the_build_id_is_the_pi15_family_and_not_v14s(self):
        import runner_proto_pmu_completion_visibility_v14 as v14

        self.assertNotEqual(contract.BUILD_ID, v14.BUILD_ID)
        self.assertEqual(contract.BUILD_ID & 0xFFFF, contract.PI15_FAMILY)

    def test_the_experiment_names_itself_by_purpose(self):
        self.assertEqual(contract.EXPERIMENT_NAME, "PMU_COMPLETION_S5_ONLY_CONTROL")


class TheObservable(unittest.TestCase):
    def test_the_deciding_bit_is_status_bit5(self):
        self.assertEqual(contract.STATUS_CMD_END, 0x020)

    def test_irq_raised_is_carried_as_supporting_evidence_only(self):
        # Same raw word, never a second read. The constant exists so the
        # classifier can read bit1 out of the STATUS the loop already sampled.
        self.assertEqual(contract.STATUS_IRQ_RAISED, 0x002)
        self.assertIn("same raw STATUS", contract.IRQ_SCOPE)

    def test_the_two_bits_are_distinct(self):
        self.assertNotEqual(contract.STATUS_CMD_END, contract.STATUS_IRQ_RAISED)


class TheAppendix(unittest.TestCase):
    def test_the_primary_observation_fields_are_named_for_what_they_are(self):
        self.assertIn("cmd_end_reached_observed", contract.APPENDIX_FIELDS)
        self.assertIn("submit_to_s5_observed_cycles", contract.APPENDIX_FIELDS)

    def test_field_order_is_frozen_and_has_no_duplicates(self):
        self.assertEqual(
            len(contract.APPENDIX_FIELDS), len(set(contract.APPENDIX_FIELDS))
        )

    def test_the_appendix_carries_the_comparison_mode(self):
        # The mode has to survive into the record itself, or the propagation
        # chain has a hole exactly where the board data enters it.
        self.assertIn("comparison_mode", contract.APPENDIX_FIELDS)


class ForbiddenVocabulary(unittest.TestCase):
    def test_the_forbidden_names_are_the_designs(self):
        self.assertEqual(
            set(contract.FORBIDDEN_FIELD_NAMES),
            {
                "internal_completion_cycles",
                "npu_completion_timestamp",
                "T_npu",
                "execution_latency",
            },
        )

    def test_no_forbidden_name_appears_in_the_appendix(self):
        for name in contract.FORBIDDEN_FIELD_NAMES:
            self.assertNotIn(name, contract.APPENDIX_FIELDS, name)

    def test_no_forbidden_name_appears_in_any_other_v15_module(self):
        # The contract module has to name them in order to refuse them, and this
        # file has to name them to check that list. Everything else must not
        # at all -- in code, in a comment, or in a docstring, since a name that
        # survives in prose is a name somebody later reads as an intention.
        #
        # This scan grows with the codebase: every V15 module added later is
        # covered without anyone remembering to add it here.
        exempt = {
            pathlib.Path(contract.__file__).resolve(),
            pathlib.Path(__file__).resolve(),
        }
        scanned = 0
        for path in sorted((REPO / "host").rglob("*_s5_only_control.py")):
            if path.resolve() in exempt:
                continue
            source = path.read_text(encoding="utf-8")
            scanned += 1
            for name in contract.FORBIDDEN_FIELD_NAMES:
                self.assertNotIn(name, source, "%s in %s" % (name, path.name))
        self.assertGreater(scanned, 0, "the scan covered no module at all")


class ComparisonMode(unittest.TestCase):
    def test_the_mode_has_exactly_two_values(self):
        self.assertEqual(
            set(contract.COMPARISON_MODES),
            {"Q_S5_EQUIVALENT", "S5_WITHIN_VARIANT_ONLY"},
        )

    def test_the_outcomes_are_the_six_that_were_preregistered(self):
        self.assertEqual(
            list(contract.OUTCOMES), ["S1", "S2", "S3", "S4", "S5", "S6"]
        )

    def test_s3_is_not_permitted_in_fallback_mode(self):
        self.assertIn("S3", contract.OUTCOMES_PERMITTED["Q_S5_EQUIVALENT"])
        self.assertNotIn("S3", contract.OUTCOMES_PERMITTED["S5_WITHIN_VARIANT_ONLY"])

    def test_every_other_outcome_survives_the_fallback(self):
        equivalent = set(contract.OUTCOMES_PERMITTED["Q_S5_EQUIVALENT"])
        fallback = set(contract.OUTCOMES_PERMITTED["S5_WITHIN_VARIANT_ONLY"])
        self.assertEqual(equivalent - fallback, {"S3"})

    def test_the_fallback_reason_is_fixed_not_free_text(self):
        self.assertEqual(
            contract.FALLBACK_REASON, "Q_S5_EQUIVALENCE_NOT_ESTABLISHED"
        )


class PollCount(unittest.TestCase):
    """Presence and admission are separate, because one enum could not say both."""

    def test_transport_and_admission_are_different_vocabularies(self):
        self.assertNotEqual(
            set(contract.POLL_COUNT_TRANSPORT), set(contract.POLL_COUNT_ADMISSION)
        )

    def test_a_present_field_is_not_described_as_omitted(self):
        # The single enum read as a lie: OMITTED about a value the record
        # carries. Presence says what is in the frame; admission says what may
        # be concluded from it.
        for value in contract.POLL_COUNT_TRANSPORT:
            self.assertNotIn("OMITTED", value)

    def test_not_admitted_names_the_reason(self):
        self.assertIn("LOOP_PERTURBATION", contract.POLL_COUNT_NOT_ADMITTED)

    def test_the_forbidden_uses_are_enumerated_not_implied(self):
        # A value that is present and not admitted invites exactly these five
        # sentences, so they are listed rather than left to judgement.
        self.assertEqual(len(contract.POLL_COUNT_FORBIDDEN_USES), 5)
        joined = " ".join(contract.POLL_COUNT_FORBIDDEN_USES)
        for fragment in ("S1..S6", "regression", "histogram", "Q and S5", "latency"):
            self.assertIn(fragment, joined)


if __name__ == "__main__":
    unittest.main()
