"""Collection is opened against a verified deployment, or it does not open.

The collector treats the cell context as a capability that was established
elsewhere. These tests are mostly about what it refuses: collecting with no
context, swapping candidates mid-cell, runs arriving out of order, a boot
changing underneath a cell, and an invalid run being offered again.

That last one is the shape that matters. A refusal that only raises lets a
caller retry until the cell fills, which turns nine good runs and one bad one
into a ten-run cell. So an unacceptable run ends the attempt, and the test
checks the attempt stays dead afterwards rather than just that a call raised.
"""

import pathlib
import struct
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import collect_pmu_completion_s5_only_control as collector  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deploy  # noqa: E402
import runner_proto as v8  # noqa: E402
import runner_proto_pmu_completion_s5_only_control as wire  # noqa: E402

from test_deployment_pmu_completion_s5_only_control import chain_of, open_cell  # noqa: E402


def frame(run_id, cycles=732, **overrides):
    values = dict.fromkeys(wire.APPENDIX_FIELDS, 0)
    values["variant_id"] = 1
    values["qsize_expected"] = wire.QSIZE_EXPECTED
    values["t_submit_after_cmd"] = 1000
    values["t_first_observation"] = 1000 + cycles
    values["t_primary_entry"] = 1100
    values["primary_iterations"] = 7
    values["primary_result"] = wire.PRIMARY_OBSERVED
    values["convergence_result"] = wire.CONVERGENCE_SUCCESS
    values["first_status"] = wire.STATUS_CMD_END
    values["first_cmd_end_reached"] = 1
    values["mailbox_valid"] = wire.MAILBOX_VALID
    values.update(overrides)

    body = [0x2000 + n for n in range(wire.BASE_WORDS)]
    body += [values[name] for name in wire.APPENDIX_FIELDS]
    header = [v8.PMU_DIAG_MAGIC, wire.SCHEMA_VERSION, 0, wire.HEADER_WORDS, run_id, 0, 0, 0]
    payload = bytearray(struct.pack("<%dI" % (len(header) + len(body)), *header, *body))
    struct.pack_into("<I", payload, 8, len(payload) // 4)
    struct.pack_into(
        "<I", payload, 28, v8.measurement_payload_crc(bytes(payload), len(payload) // 4)
    )
    return bytes(payload)


def context(boot_id="b1", **kwargs):
    return open_cell(*chain_of(**kwargs), boot_id=boot_id)


def fill(cell, count=collector.RUNS_PER_CELL, cycles=None):
    for run in range(1, count + 1):
        cell.record(frame(run, cycles=732 if cycles is None else cycles[run - 1]))
    return cell


class ACellNeedsAVerifiedDeployment(unittest.TestCase):
    def test_opening_a_cell_without_a_context_is_refused(self):
        with self.assertRaises(collector.CollectorError) as caught:
            collector.Cell(None)
        self.assertEqual(
            collector.refusal_rule(caught.exception), collector.RULE_CONTEXT_REQUIRED
        )

    def test_a_dict_that_looks_like_a_context_is_refused(self):
        with self.assertRaises(collector.CollectorError):
            collector.Cell({"comparison_mode": contract.Q_S5_EQUIVALENT, "boot_id": "b1"})

    def test_a_cell_opens_against_a_verified_deployment(self):
        cell = collector.Cell(context())
        self.assertFalse(cell.complete)
        self.assertEqual(cell.context.comparison_mode, contract.Q_S5_EQUIVALENT)


class TenRunsMakeACell(unittest.TestCase):
    def test_ten_runs_complete_the_cell(self):
        cell = fill(collector.Cell(context()))
        self.assertTrue(cell.complete)
        self.assertEqual(len(cell.samples), 10)
        self.assertEqual(cell.bundle()["run_sequence"], tuple(range(1, 11)))

    def test_an_eleventh_run_is_refused(self):
        cell = fill(collector.Cell(context()))
        with self.assertRaises(collector.CollectorError) as caught:
            cell.record(frame(11))
        self.assertEqual(
            collector.refusal_rule(caught.exception), collector.RULE_CELL_ALREADY_COMPLETE
        )

    def test_a_short_cell_produces_no_bundle(self):
        cell = fill(collector.Cell(context()), count=9)
        with self.assertRaises(collector.CollectorError) as caught:
            cell.bundle()
        self.assertEqual(
            collector.refusal_rule(caught.exception), collector.RULE_CELL_INCOMPLETE
        )

    def test_runs_out_of_order_end_the_attempt(self):
        cell = collector.Cell(context())
        cell.record(frame(1))
        with self.assertRaises(collector.CollectorError) as caught:
            cell.record(frame(3))
        self.assertEqual(
            collector.refusal_rule(caught.exception), collector.RULE_RUN_OUT_OF_ORDER
        )


class AnUnacceptableRunEndsTheAttempt(unittest.TestCase):
    def test_an_invalid_run_ends_the_attempt(self):
        cell = collector.Cell(context())
        fill(cell, count=4)
        with self.assertRaises(collector.CollectorError) as caught:
            cell.record(frame(5, primary_result=wire.PRIMARY_TIMEOUT))
        self.assertEqual(
            collector.refusal_rule(caught.exception),
            collector.RULE_INVALID_SAMPLE_ENDS_ATTEMPT,
        )

    def test_the_attempt_stays_dead_and_cannot_be_filled_by_retrying(self):
        # The point of ending rather than raising: catching the error and
        # offering the run again must not produce a ten-run cell.
        cell = collector.Cell(context())
        fill(cell, count=4)
        try:
            cell.record(frame(5, primary_result=wire.PRIMARY_TIMEOUT))
        except collector.CollectorError:
            pass
        for attempt in range(6):
            with self.assertRaises(collector.CollectorError) as caught:
                cell.record(frame(5))
            self.assertEqual(
                collector.refusal_rule(caught.exception), collector.RULE_ATTEMPT_IS_OVER
            )
        self.assertFalse(cell.complete)
        self.assertEqual(len(cell.samples), 4)


class OneCellIsOneBootAndOneCandidate(unittest.TestCase):
    def test_a_boot_changing_mid_cell_ends_the_attempt(self):
        # boot_id reaches a sample from the cell's context, so a different boot
        # is a different context and is caught as one. There is no separate boot
        # comparison in the collector because it would compare a value with
        # itself and could never fire.
        cell = collector.Cell(context(boot_id="b1"))
        fill(cell, count=3)
        with self.assertRaises(collector.CollectorError) as caught:
            cell.record(frame(4), context=context(boot_id="b2"))
        self.assertEqual(
            collector.refusal_rule(caught.exception),
            collector.RULE_CONTEXT_CHANGED_MID_CELL,
        )
        self.assertIsNotNone(cell.dead)

    def test_swapping_candidate_mid_cell_fails_the_whole_cell(self):
        cell = collector.Cell(context())
        fill(cell, count=5)
        # A different ELF is a different candidate: same artifacts deployed,
        # different evidence chain, different candidate_identity.
        other = context(equivalence={"elf": "e7" * 32})
        self.assertNotEqual(
            other.candidate_identity, cell.context.candidate_identity
        )
        with self.assertRaises(collector.CollectorError) as caught:
            cell.record(frame(6), context=other)
        self.assertEqual(
            collector.refusal_rule(caught.exception),
            collector.RULE_CONTEXT_CHANGED_MID_CELL,
        )
        self.assertIsNotNone(cell.dead)
        self.assertFalse(cell.complete)


class TheCampaignHoldsOneMode(unittest.TestCase):
    def test_three_boots_make_a_campaign(self):
        campaign = collector.Campaign()
        for boot in range(3):
            fill(campaign.open_cell(context()))
        bundle = campaign.bundle()
        self.assertTrue(bundle["complete"])
        self.assertEqual(bundle["boots_collected"], 3)
        self.assertEqual(bundle["comparison_mode"], contract.Q_S5_EQUIVALENT)

    def test_two_boots_is_not_a_complete_campaign(self):
        campaign = collector.Campaign()
        for boot in range(2):
            fill(campaign.open_cell(context()))
        self.assertFalse(campaign.bundle()["complete"])

    def test_a_cell_in_another_mode_is_refused(self):
        campaign = collector.Campaign()
        fill(campaign.open_cell(context()))
        fallback = context(
            equivalence={"mode": contract.S5_WITHIN_VARIANT_ONLY,
                         "status": "FALLBACK_WITHIN_VARIANT"}
        )
        with self.assertRaises(collector.CollectorError) as caught:
            campaign.open_cell(fallback)
        self.assertEqual(
            collector.refusal_rule(caught.exception),
            collector.RULE_MODE_CHANGED_MID_CAMPAIGN,
        )


class TheBundleCarriesItsProvenance(unittest.TestCase):
    def test_the_bundle_names_the_deployment_it_came_from(self):
        cell = fill(collector.Cell(context()))
        bundle = cell.bundle()
        self.assertEqual(len(bundle["raw_frame_sha256"]), 10)
        self.assertEqual(len(set(bundle["raw_frame_sha256"])), 10)
        for key in ("app_sha256", "vectors_sha256", "ddr_sha256", "analysis_elf_sha256",
                    "manifest_sha256", "static_evidence_sha256",
                    "equivalence_evidence_sha256", "v14_q_reference_identity"):
            self.assertTrue(bundle["deployment"][key], key)

    def test_the_bundle_feeds_the_analyzer(self):
        import analyze_pmu_completion_s5_only_control as analyzer

        campaign = collector.Campaign()
        per_boot = [
            [732, 732, 900, 1400, 2200, 732, 3100, 980, 732, 4400],
            [732, 810, 732, 2600, 732, 1750, 732, 5200, 990, 732],
            [732, 732, 1220, 732, 3300, 732, 870, 4100, 732, 1500],
        ]
        for cycles in per_boot:
            fill(campaign.open_cell(context()), cycles=cycles)
        self.assertEqual(analyzer.analyze(campaign.bundle())["outcome"], "S1")


class TheCollectorDoesNotReadjudicate(unittest.TestCase):
    def test_the_collector_touches_only_the_context_type_from_deployment(self):
        # The boundary the design depends on: when the V14 Q reference pin
        # lands, nothing in the collector changes. Checked structurally rather
        # than by searching the text, which would also match the prose above
        # explaining the boundary.
        import ast

        tree = ast.parse(
            (REPO / "host" / "collect_pmu_completion_s5_only_control.py").read_text()
        )
        used = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "deployment"
        }
        self.assertEqual(used, {"VerifiedCellContext"})

    def test_the_mode_is_read_from_the_context_and_never_decided(self):
        fallback = context(
            equivalence={"mode": contract.S5_WITHIN_VARIANT_ONLY,
                         "status": "FALLBACK_WITHIN_VARIANT"}
        )
        self.assertEqual(
            fill(collector.Cell(fallback)).bundle()["comparison_mode"],
            contract.S5_WITHIN_VARIANT_ONLY,
        )


class TheReconstructionClosedTheBridge(unittest.TestCase):
    def test_the_reconstruction_matched_the_deployed_artifact_set(self):
        self.assertEqual(
            deploy.V14_Q_RECONSTRUCTION_ATTEMPT_RESULT,
            deploy.RECONSTRUCTION_APP_SET_MATCHED,
        )

    def test_the_raw_ab_claim_is_scoped_to_one_build_path(self):
        # The original claim was unconditional and wrong: raw ELF digests move
        # with the build directory, so A == B only holds at a fixed path.
        self.assertEqual(deploy.V14_Q_RAW_ELF_SAME_PATH_AB, "IDENTICAL")
        self.assertIn("PATH_INDEPENDENT", deploy.V14_Q_ANALYSIS_ELF_STABILITY)
        self.assertEqual(
            deploy.V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET, "REPRODUCED_BYTE_EXACT"
        )

    def test_both_provenance_bridges_are_resolved_and_kept_separate(self):
        # Amendment 3 split one bridge into two: the runtime identity bridge and
        # the analysis identity bridge are established by different evidence.
        self.assertEqual(deploy.Q_S5_EXECUTABLE_COMPARISON, "PASS")
        self.assertIn("RESOLVED", deploy.Q_S5_RUNTIME_IDENTITY_BRIDGE)
        self.assertIn("RESOLVED", deploy.Q_S5_ANALYSIS_IDENTITY_BRIDGE)
        self.assertNotEqual(
            deploy.Q_S5_RUNTIME_IDENTITY_BRIDGE, deploy.Q_S5_ANALYSIS_IDENTITY_BRIDGE
        )


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_collector_declares(self):
        def out_of_order():
            cell = collector.Cell(context())
            cell.record(frame(1))
            cell.record(frame(3))

        def invalid_run():
            cell = collector.Cell(context())
            cell.record(frame(1, primary_result=wire.PRIMARY_TIMEOUT))

        def attempt_over():
            cell = collector.Cell(context())
            try:
                cell.record(frame(1, primary_result=wire.PRIMARY_TIMEOUT))
            except collector.CollectorError:
                pass
            cell.record(frame(1))

        def context_changed():
            cell = collector.Cell(context())
            cell.record(frame(1))
            cell.record(frame(2), context=context())

        def overfull():
            fill(collector.Cell(context())).record(frame(11))

        def incomplete():
            fill(collector.Cell(context()), count=2).bundle()

        def mode_changed():
            campaign = collector.Campaign()
            campaign.open_cell(context())
            campaign.open_cell(
                context(equivalence={"mode": contract.S5_WITHIN_VARIANT_ONLY,
                                     "status": "FALLBACK_WITHIN_VARIANT"})
            )

        attempts = (
            lambda: collector.Cell(None),
            context_changed,
            out_of_order,
            invalid_run,
            overfull,
            incomplete,
            attempt_over,
            mode_changed,
        )
        tripped = set()
        for attempt in attempts:
            try:
                attempt()
            except collector.CollectorError as exc:
                tripped.add(collector.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(collector, name) for name in collector.RULES})


if __name__ == "__main__":
    unittest.main()
