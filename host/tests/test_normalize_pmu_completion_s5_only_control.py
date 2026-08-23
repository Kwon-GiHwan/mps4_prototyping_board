"""The step where three provenances meet, and are kept apart while they do.

parse_frame knows the wire. This is what happens next, and the reason it is a
separate call is that comparison_mode and build_id are not on the wire: taking
them from a context makes that visible, whereas a parser that filled them in
would produce a record where a field that was never measured looks like one that
was.

So the tests below are mostly about provenance rather than arithmetic. A wire
field must move unchanged from the frame; a static field must come from the
context and follow it when it changes; a derived field must change when the
words it is derived from change, and must refuse when those words disagree with
each other.
"""

import pathlib
import struct
import sys
import unittest
from unittest import mock


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deploy  # noqa: E402
import normalize_pmu_completion_s5_only_control as normalizer  # noqa: E402
import runner_proto as v8  # noqa: E402
import runner_proto_pmu_completion_s5_only_control as wire  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_deployment_pmu_completion_s5_only_control import chain_of, open_cell  # noqa: E402


def appendix(**overrides):
    values = dict.fromkeys(wire.APPENDIX_FIELDS, 0)
    values["variant_id"] = 1
    values["qsize_expected"] = wire.QSIZE_EXPECTED
    values["t_submit_after_cmd"] = 1000
    values["t_primary_entry"] = 1100
    values["t_first_observation"] = 1732
    values["primary_iterations"] = 7
    values["primary_result"] = wire.PRIMARY_OBSERVED
    values["convergence_result"] = wire.CONVERGENCE_SUCCESS
    values["first_status"] = wire.STATUS_CMD_END
    values["first_cmd_end_reached"] = 1
    values["mailbox_valid"] = wire.MAILBOX_VALID
    values.update(overrides)
    return values


def parsed(**overrides):
    values = appendix(**overrides)
    body = [0x2000 + n for n in range(wire.BASE_WORDS)]
    body += [values[name] for name in wire.APPENDIX_FIELDS]
    header = [v8.PMU_DIAG_MAGIC, wire.SCHEMA_VERSION, 0, wire.HEADER_WORDS, 3, 0, 0, 0]
    payload = bytearray(struct.pack("<%dI" % (len(header) + len(body)), *header, *body))
    struct.pack_into("<I", payload, 8, len(payload) // 4)
    struct.pack_into(
        "<I", payload, 28, v8.measurement_payload_crc(bytes(payload), len(payload) // 4)
    )
    return wire.parse_frame(bytes(payload))


def context(**kwargs):
    return open_cell(*chain_of(**kwargs))


class TheRecordIsExactlyTheContractedFields(unittest.TestCase):
    def test_every_record_field_is_present_and_nothing_else_is(self):
        record = normalizer.normalize(parsed(), context())
        self.assertEqual(set(record.fields), set(contract.RECORD_FIELDS))

    def test_every_field_reports_the_origin_the_contract_gives_it(self):
        record = normalizer.normalize(parsed(), context())
        for name in contract.RECORD_FIELDS:
            self.assertIn(record.origin_of(name), contract.FIELD_ORIGINS, name)


class TheRecordShapeIsEnforcedNotAssumed(unittest.TestCase):
    def test_a_record_short_of_a_field_is_refused(self):
        # Without this the completeness check is a branch nothing reaches:
        # deleting it left every test green.
        short = dict(normalizer._derive(parsed()))
        short.pop("cleanup_result")
        with mock.patch.object(normalizer, "_derive", return_value=short):
            with self.assertRaises(normalizer.NormalizeError) as caught:
                normalizer.normalize(parsed(), context())
        self.assertEqual(
            normalizer.refusal_rule(caught.exception),
            normalizer.RULE_RECORD_FIELD_MISSING,
        )
        self.assertIn("cleanup_result", "%s" % caught.exception)

    def test_a_record_carrying_a_field_the_contract_does_not_name_is_refused(self):
        extra = dict(normalizer._derive(parsed()))
        extra["t_npu_completion"] = 1
        with mock.patch.object(normalizer, "_derive", return_value=extra):
            with self.assertRaises(normalizer.NormalizeError) as caught:
                normalizer.normalize(parsed(), context())
        self.assertEqual(
            normalizer.refusal_rule(caught.exception),
            normalizer.RULE_RECORD_FIELD_MISSING,
        )


class WireFieldsTravelUnchanged(unittest.TestCase):
    def test_a_wire_appendix_field_is_the_word_the_device_sent(self):
        frame = parsed(primary_iterations=41, convergence_iterations=9)
        record = normalizer.normalize(frame, context())
        self.assertEqual(record.fields["primary_iterations"], 41)
        self.assertEqual(record.fields["convergence_iterations"], 9)
        self.assertEqual(
            record.origin_of("primary_iterations"), contract.WIRE_APPENDIX
        )

    def test_the_header_fields_come_from_the_header(self):
        record = normalizer.normalize(parsed(), context())
        # Amendment 4: the wire schema is 14. 15 is the qualification
        # generation and never appears in a frame.
        self.assertEqual(record.fields["schema_version"], wire.SCHEMA_VERSION)
        self.assertEqual(record.fields["schema_version"], 14)
        self.assertEqual(record.fields["run_sequence"], 3)
        self.assertEqual(record.origin_of("run_sequence"), contract.WIRE_HEADER)

    def test_mailbox_magic_is_the_wires_mailbox_valid_word(self):
        # The alias relationship, asserted rather than assumed: same value, no
        # transform, and the legacy V14M marker is not an identity.
        record = normalizer.normalize(parsed(), context())
        self.assertEqual(record.fields["mailbox_magic"], wire.MAILBOX_VALID)
        self.assertEqual(record.origin_of("mailbox_magic"), contract.WIRE_APPENDIX)

    def test_the_frame_does_not_establish_which_experiment_produced_it(self):
        # Amendment 4, learned from a live frame. The wire schema is 14, the
        # mailbox marker is "V14M", the geometry and appendix are V14's. A V15
        # frame is shaped exactly like a V14 frame, so nothing in it says which
        # experiment ran. Amendment 2 claimed schema_version did; it does not.
        record = normalizer.normalize(parsed(), context())
        self.assertEqual(record.fields["mailbox_magic"], 0x5631344D)
        self.assertEqual(record.fields["schema_version"], 14)
        self.assertFalse(contract.FRAME_ESTABLISHES_EXPERIMENT_IDENTITY)
        self.assertEqual(contract.EXPERIMENT_IDENTITY_AUTHORITY, "VerifiedCellContext")

    def test_experiment_identity_comes_from_the_context_instead(self):
        # build_id is not in the frame either; it reaches the record from the
        # cell context, which is where experiment identity now lives.
        record = normalizer.normalize(parsed(), context())
        self.assertEqual(record.fields["build_id"], contract.BUILD_ID)
        self.assertEqual(record.origin_of("build_id"), contract.STATIC_IMAGE_EVIDENCE)
        self.assertNotIn("build_id", wire.ParsedFrame.__dataclass_fields__)


class StaticFieldsComeFromTheContext(unittest.TestCase):
    def test_comparison_mode_is_taken_from_the_cell_context(self):
        record = normalizer.normalize(parsed(), context())
        self.assertEqual(record.comparison_mode, contract.Q_S5_EQUIVALENT)
        self.assertEqual(
            record.origin_of("comparison_mode"), contract.STATIC_IMAGE_EVIDENCE
        )

    def test_the_mode_follows_the_context_rather_than_the_frame(self):
        # Same bytes, different licensed deployment, different mode. If the mode
        # were coming from the frame this could not happen.
        fallback = context(
            equivalence={
                "mode": contract.S5_WITHIN_VARIANT_ONLY,
                "status": "FALLBACK_WITHIN_VARIANT",
            }
        )
        frame = parsed()
        self.assertEqual(
            normalizer.normalize(frame, context()).comparison_mode,
            contract.Q_S5_EQUIVALENT,
        )
        self.assertEqual(
            normalizer.normalize(frame, fallback).comparison_mode,
            contract.S5_WITHIN_VARIANT_ONLY,
        )

    def test_normalising_without_a_context_is_refused(self):
        with self.assertRaises(normalizer.NormalizeError) as caught:
            normalizer.normalize(parsed(), {"comparison_mode": contract.Q_S5_EQUIVALENT})
        self.assertEqual(
            normalizer.refusal_rule(caught.exception), normalizer.RULE_CONTEXT_REQUIRED
        )

    def test_a_dict_dressed_as_a_context_is_refused(self):
        class Pretend:
            comparison_mode = contract.Q_S5_EQUIVALENT
            boot_id = "b1"
            candidate_identity = "x" * 64

        with self.assertRaises(normalizer.NormalizeError):
            normalizer.normalize(parsed(), Pretend())


class DerivedFieldsAreComputedAndCrossChecked(unittest.TestCase):
    def test_the_interval_is_the_difference_of_two_wire_stamps(self):
        record = normalizer.normalize(
            parsed(t_submit_after_cmd=1000, t_first_observation=1732), context()
        )
        self.assertEqual(record.fields["submit_to_s5_observed_cycles"], 732)
        self.assertEqual(
            record.origin_of("submit_to_s5_observed_cycles"), contract.DERIVED_FROM_WIRE
        )

    def test_a_negative_interval_is_refused(self):
        with self.assertRaises(normalizer.NormalizeError) as caught:
            normalizer.normalize(
                parsed(t_submit_after_cmd=2000, t_first_observation=1000), context()
            )
        self.assertEqual(
            normalizer.refusal_rule(caught.exception), normalizer.RULE_TIMESTAMPS_UNORDERED
        )

    def test_a_status_word_disagreeing_with_the_firmwares_own_reading_is_refused(self):
        # The device said two things. Preferring one would be choosing which of
        # its statements to believe.
        with self.assertRaises(normalizer.NormalizeError) as caught:
            normalizer.normalize(
                parsed(first_status=wire.STATUS_CMD_END, first_cmd_end_reached=0), context()
            )
        self.assertEqual(
            normalizer.refusal_rule(caught.exception),
            normalizer.RULE_STATUS_SELF_CONTRADICTION,
        )

    def test_an_irq_bit_disagreeing_with_the_firmwares_reading_is_refused(self):
        with self.assertRaises(normalizer.NormalizeError) as caught:
            normalizer.normalize(
                parsed(
                    first_status=wire.STATUS_CMD_END | wire.STATUS_IRQ_RAISED,
                    first_cmd_end_reached=1,
                    first_irq_raised=0,
                ),
                context(),
            )
        self.assertEqual(
            normalizer.refusal_rule(caught.exception),
            normalizer.RULE_STATUS_SELF_CONTRADICTION,
        )

    def test_cleanup_fails_when_an_interrupt_survives_it(self):
        record = normalizer.normalize(parsed(nvic_active_after_cleanup=1), context())
        self.assertEqual(record.fields["cleanup_result"], normalizer.CLEANUP_FAIL)


class ClassificationNamesWhyASampleDoesNotCount(unittest.TestCase):
    def test_a_healthy_run_is_a_valid_sample(self):
        sample = normalizer.classify(normalizer.normalize(parsed(), context()))
        self.assertTrue(sample["sample_valid"])
        self.assertEqual(sample["invalid_reasons"], ())
        self.assertEqual(sample["submit_to_s5_observed_cycles"], 732)
        self.assertEqual(sample["boot_id"], "b1")

    def test_a_primary_timeout_is_invalid_and_says_so(self):
        sample = normalizer.classify(
            normalizer.normalize(parsed(primary_result=wire.PRIMARY_TIMEOUT), context())
        )
        self.assertFalse(sample["sample_valid"])
        self.assertIn(normalizer.INVALID_PRIMARY_FAILED, sample["invalid_reasons"])

    def test_fault_bits_invalidate_the_sample(self):
        sample = normalizer.classify(
            normalizer.normalize(
                parsed(first_status=wire.STATUS_CMD_END | 0x004), context()
            )
        )
        self.assertFalse(sample["sample_valid"])
        self.assertIn(normalizer.INVALID_FAULT_BITS, sample["invalid_reasons"])

    def test_a_broken_cleanup_invariant_invalidates_the_sample(self):
        sample = normalizer.classify(
            normalizer.normalize(parsed(irq_triggered_after_cleanup=1), context())
        )
        self.assertFalse(sample["sample_valid"])
        self.assertIn(normalizer.INVALID_CLEANUP_FAILED, sample["invalid_reasons"])

    def test_every_invalid_reason_is_reachable(self):
        cases = (
            (dict(primary_result=wire.PRIMARY_TIMEOUT), normalizer.INVALID_PRIMARY_FAILED),
            (dict(first_status=0, first_cmd_end_reached=0),
             normalizer.INVALID_CMD_END_NOT_OBSERVED),
            (dict(first_status=wire.STATUS_CMD_END | 0x100),
             normalizer.INVALID_FAULT_BITS),
            (dict(convergence_result=wire.CONVERGENCE_TIMEOUT), normalizer.INVALID_CONVERGENCE_FAILED),
            (dict(nvic_pending_after_final_clear=1), normalizer.INVALID_CLEANUP_FAILED),
            (dict(failure_phase=2), normalizer.INVALID_FAILURE_RECORDED),
        )
        seen = set()
        for overrides, expected in cases:
            sample = normalizer.classify(
                normalizer.normalize(parsed(**overrides), context())
            )
            self.assertIn(expected, sample["invalid_reasons"], overrides)
            seen.add(expected)
        self.assertEqual(len(seen), len(cases))

    def test_the_poll_count_rides_along_and_is_not_admitted(self):
        sample = normalizer.classify(
            normalizer.normalize(parsed(primary_iterations=41), context())
        )
        self.assertEqual(sample["poll_count"], 41)
        self.assertEqual(sample["poll_count_admission"], contract.POLL_COUNT_NOT_ADMITTED)

    def test_the_sample_carries_the_candidate_it_came_from(self):
        cell = context()
        sample = normalizer.classify(normalizer.normalize(parsed(), cell))
        self.assertEqual(sample["candidate_identity"], cell.candidate_identity)


if __name__ == "__main__":
    unittest.main()


class TheChainRunsFromBytesToAVerdict(unittest.TestCase):
    """parse -> normalize -> classify -> analyze, over synthetic frames.

    Not the end-to-end requalification, which waits on the collector issuing a
    context from a real deployment. What it shows is that the four stages agree
    about the shape they hand each other, which is where a pipeline usually
    breaks first.
    """

    def _campaign(self, per_boot):
        import analyze_pmu_completion_s5_only_control as analyzer

        boots = []
        for boot_index, cycles in enumerate(per_boot, start=1):
            cell = context()
            samples = []
            for run, value in enumerate(cycles, start=1):
                frame = parsed(
                    t_submit_after_cmd=1000, t_first_observation=1000 + value
                )
                samples.append(normalizer.classify(normalizer.normalize(frame, cell)))
            boots.append({"boot_id": "b%d" % boot_index, "samples": samples})
        return analyzer, {
            "comparison_mode": contract.Q_S5_EQUIVALENT,
            "boots": boots,
        }

    def test_a_reproduced_floor_with_excursions_reaches_s1(self):
        analyzer, campaign = self._campaign(
            [
                [732, 732, 900, 1400, 2200, 732, 3100, 980, 732, 4400],
                [732, 810, 732, 2600, 732, 1750, 732, 5200, 990, 732],
                [732, 732, 1220, 732, 3300, 732, 870, 4100, 732, 1500],
            ]
        )
        self.assertEqual(analyzer.analyze(campaign)["outcome"], "S1")

    def test_a_floor_with_no_excursion_reaches_s2(self):
        analyzer, campaign = self._campaign([[732] * 10] * 3)
        self.assertEqual(analyzer.analyze(campaign)["outcome"], "S2")

    def test_invalid_samples_do_not_enter_the_distribution(self):
        cell = context()
        good = normalizer.classify(
            normalizer.normalize(parsed(t_first_observation=1732), cell)
        )
        bad = normalizer.classify(
            normalizer.normalize(parsed(t_first_observation=1100, primary_result=wire.PRIMARY_TIMEOUT), cell)
        )
        self.assertTrue(good["sample_valid"])
        self.assertFalse(bad["sample_valid"])
        # The invalid one is the smaller interval. Counting it would move the
        # floor, which is why validity is decided before the distribution.
        self.assertLess(
            bad["submit_to_s5_observed_cycles"], good["submit_to_s5_observed_cycles"]
        )
