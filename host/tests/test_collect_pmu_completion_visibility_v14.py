"""The campaign collector's state machine, exercised without a board.

Everything here is filesystem and bookkeeping. The board's part -- opening a
port, sending a command, reading a frame -- is injected, so what is tested is
the part that decides whether a run counts, and that part is the one that can
quietly turn nine good runs and one bad one into a ten-run cell.
"""

import os
import tempfile
import unittest

from host import collect_pmu_completion_visibility_v14 as collector


IDENTITY = {
    "source_sha256": "a" * 64,
    "image_sha256": "b" * 64,
    "classifier_sha256": "c" * 64,
    "manifest_sha256": "d" * 64,
    "contract_sha256": "e" * 64,
}
RUNS_PER_CELL = 10


def sample(run_id, boot_id="boot-1", valid=True):
    return {"run_id": run_id, "boot_id": boot_id, "sample_valid": valid,
            "payload_sha256": "%064x" % run_id}


class CollectorRedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.campaign = collector.Campaign(self.root, IDENTITY)

    def tearDown(self):
        self._tmp.cleanup()

    def cell(self, round_index=1, position=1, variant="Q"):
        return self.campaign.cell(round_index, position, variant)

    # --- layout ------------------------------------------------------------
    def test_the_cell_root_is_the_one_the_plan_fixes(self):
        cell = self.cell(2, 3, "SQ")
        self.assertTrue(
            cell.attempt_path(1).endswith(os.path.join("cells", "2-3-SQ", "attempt-1")),
            cell.attempt_path(1),
        )

    def test_a_variant_outside_the_matrix_is_a_caller_error(self):
        with self.assertRaises(collector.CollectorError):
            self.campaign.cell(1, 1, "ZZ")

    # --- the happy cell ----------------------------------------------------
    def test_ten_contiguous_runs_on_one_boot_complete_a_cell(self):
        cell = self.cell()
        for run_id in range(1, RUNS_PER_CELL + 1):
            cell.record(sample(run_id))
        self.assertTrue(cell.complete)
        self.assertEqual(len(cell.samples), RUNS_PER_CELL)

    def test_a_cell_is_not_complete_early(self):
        cell = self.cell()
        for run_id in range(1, RUNS_PER_CELL):
            cell.record(sample(run_id))
        self.assertFalse(cell.complete)

    def test_an_eleventh_run_is_refused(self):
        cell = self.cell()
        for run_id in range(1, RUNS_PER_CELL + 1):
            cell.record(sample(run_id))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(RUNS_PER_CELL + 1))

    # --- run identity ------------------------------------------------------
    def test_run_numbering_starts_at_one(self):
        with self.assertRaises(collector.CollectorError):
            self.cell().record(sample(0))

    def test_a_gap_in_the_run_sequence_is_refused(self):
        cell = self.cell()
        cell.record(sample(1))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(3))

    def test_a_repeated_run_number_is_refused(self):
        cell = self.cell()
        cell.record(sample(1))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(1))

    def test_a_boot_id_change_mid_cell_is_refused(self):
        cell = self.cell()
        cell.record(sample(1))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(2, boot_id="boot-2"))

    def test_an_invalid_sample_is_refused_rather_than_counted(self):
        cell = self.cell()
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(1, valid=False))

    # --- failure handling --------------------------------------------------
    def test_a_failure_quarantines_the_whole_attempt(self):
        for failed_at in (1, 9):
            campaign = collector.Campaign(tempfile.mkdtemp(dir=self.root), IDENTITY)
            cell = campaign.cell(1, 1, "Q")
            for run_id in range(1, failed_at):
                cell.record(sample(run_id))
            cell.fail("uart holder lost")
            self.assertEqual(cell.samples, [])
            quarantined = campaign.quarantined()
            self.assertEqual(len(quarantined), 1)
            self.assertTrue(os.path.isdir(quarantined[0]))
            self.assertFalse(campaign.formal_samples())

    def test_a_failure_stops_the_campaign_until_disposed(self):
        cell = self.cell()
        cell.record(sample(1))
        cell.fail("convergence timeout")
        self.assertTrue(self.campaign.stopped)
        with self.assertRaises(collector.CollectorError):
            self.campaign.cell(1, 2, "QS")

    def test_a_retry_needs_a_disposition_and_a_fresh_attempt(self):
        cell = self.cell()
        cell.record(sample(1))
        cell.fail("fault bits")
        with self.assertRaises(collector.CollectorError):
            self.campaign.cell(1, 1, "Q")
        self.campaign.dispose("root cause closed, board restored", board_restored=True)
        retry = self.campaign.cell(1, 1, "Q")
        self.assertTrue(retry.attempt_path(retry.attempt).endswith("attempt-2"))
        retry.record(sample(1, boot_id="boot-2"))
        self.assertEqual(len(retry.samples), 1)

    def test_a_disposition_without_a_board_restore_is_refused(self):
        cell = self.cell()
        cell.record(sample(1))
        cell.fail("fault bits")
        with self.assertRaises(collector.CollectorError):
            self.campaign.dispose("looks fine", board_restored=False)

    def test_a_retry_restarts_at_run_one(self):
        cell = self.cell()
        cell.record(sample(1))
        cell.record(sample(2))
        cell.fail("stop")
        self.campaign.dispose("closed", board_restored=True)
        retry = self.campaign.cell(1, 1, "Q")
        with self.assertRaises(collector.CollectorError):
            retry.record(sample(3, boot_id="boot-2"))

    # --- campaign identity -------------------------------------------------
    def test_changing_any_identity_input_restarts_the_campaign(self):
        cell = self.cell()
        for run_id in range(1, RUNS_PER_CELL + 1):
            cell.record(sample(run_id))
        for key in IDENTITY:
            changed = dict(IDENTITY, **{key: "f" * 64})
            with self.assertRaises(collector.CollectorError):
                collector.Campaign(self.root, changed)

    def test_reopening_with_the_same_identity_keeps_completed_cells(self):
        cell = self.cell()
        for run_id in range(1, RUNS_PER_CELL + 1):
            cell.record(sample(run_id))
        reopened = collector.Campaign(self.root, IDENTITY)
        self.assertEqual(len(reopened.completed_cells()), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class CollectorFailClosedTests(unittest.TestCase):
    """The rules the module's own docstring promised and did not keep.

    Every one of these was demonstrated against the shipped collector during
    review: it raised on a bad run and then let the caller carry on as if the
    run had never been offered.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.campaign = collector.Campaign(self._tmp.name, IDENTITY)

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_invalid_run_ends_the_attempt_rather_than_being_re_offered(self):
        cell = self.campaign.cell(1, 1, "Q")
        for run_id in range(1, 5):
            cell.record(sample(run_id))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(5, valid=False))
        # The cell is over. Offering run 5 again is offering it to a dead cell.
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(5))
        self.assertTrue(self.campaign.stopped)
        self.assertEqual(len(self.campaign.quarantined()), 1)
        self.assertEqual(cell.samples, [])
        self.assertFalse(cell.complete)

    def test_a_boot_change_ends_the_attempt_the_same_way(self):
        cell = self.campaign.cell(1, 1, "Q")
        cell.record(sample(1))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(2, boot_id="boot-2"))
        self.assertTrue(self.campaign.stopped)
        self.assertEqual(len(self.campaign.quarantined()), 1)

    def test_a_run_out_of_sequence_ends_the_attempt(self):
        cell = self.campaign.cell(1, 1, "Q")
        cell.record(sample(1))
        with self.assertRaises(collector.CollectorError):
            cell.record(sample(3))
        self.assertTrue(self.campaign.stopped)

    def test_a_sample_from_another_variant_is_refused(self):
        cell = self.campaign.cell(1, 1, "Q")
        with self.assertRaises(collector.CollectorError):
            cell.record(dict(sample(1), variant="SQ"))
        self.assertTrue(self.campaign.stopped)

    def test_a_cell_is_not_retried_without_a_failure_and_a_disposition(self):
        first = self.campaign.cell(1, 1, "Q")
        first.record(sample(1))
        # Asking for the same cell again, with no failure recorded, is the
        # retry-until-clean move. It is refused.
        with self.assertRaises(collector.CollectorError):
            self.campaign.cell(1, 1, "Q")

    def test_a_completed_cell_cannot_be_reopened(self):
        cell = self.campaign.cell(1, 1, "Q")
        for run_id in range(1, RUNS_PER_CELL + 1):
            cell.record(sample(run_id))
        with self.assertRaises(collector.CollectorError):
            self.campaign.cell(1, 1, "Q")

    def test_quarantine_moves_the_attempt_out_of_the_cell_tree(self):
        cell = self.campaign.cell(1, 1, "Q")
        path = cell.attempt_path(cell.attempt)
        cell.record(sample(1))
        self.assertTrue(os.path.isdir(path))
        cell.fail("something")
        self.assertFalse(os.path.exists(path), "the failed attempt is still in cells/")


class CollectorFrameIngestTests(unittest.TestCase):
    """The collector decides validity from the frame, not from the caller.

    Until this existed, `record()` took `sample_valid` from whoever called it
    and the phase classifier had no caller anywhere in the tree. A campaign
    could therefore be assembled entirely out of assertions.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.campaign = collector.Campaign(self._tmp.name, IDENTITY)
        self.cell = self.campaign.cell(1, 1, "Q")

    def tearDown(self):
        self._tmp.cleanup()

    def frame(self, **kw):
        from host.tests import test_pmu_completion_visibility_v14 as frames
        return frames.build_frame(**kw)

    def test_a_frame_is_parsed_classified_and_recorded(self):
        sample = self.cell.record_frame(self.frame(variant="Q", seq=1), boot_id="boot-1")
        self.assertEqual(sample["run_id"], 1)
        self.assertEqual(sample["variant"], "Q")
        self.assertTrue(sample["sample_valid"])
        self.assertEqual(sample["payload_sha256"], collector.payload_digest(self.frame(variant="Q", seq=1)))
        self.assertEqual(len(self.cell.samples), 1)

    def test_the_caller_cannot_assert_validity(self):
        # A frame whose primary stage failed is not valid however it is offered.
        from host.tests import test_pmu_completion_visibility_v14 as frames
        bad = frames.failure_appendix("Q", 3, 7, primary=2)
        with self.assertRaises(collector.CollectorError):
            self.cell.record_frame(self.frame(variant="Q", appendix=bad, seq=1), boot_id="boot-1")
        self.assertTrue(self.campaign.stopped)

    def test_a_frame_the_parser_refuses_ends_the_attempt(self):
        with self.assertRaises(collector.CollectorError):
            self.cell.record_frame(b"\x00" * 508, boot_id="boot-1")
        self.assertTrue(self.campaign.stopped)

    def test_a_frame_whose_variant_is_not_the_cell_s_ends_the_attempt(self):
        with self.assertRaises(collector.CollectorError):
            self.cell.record_frame(self.frame(variant="SQ", seq=1), boot_id="boot-1")
        self.assertTrue(self.campaign.stopped)

    def test_a_reread_that_differs_from_the_first_read_ends_the_attempt(self):
        first = self.frame(variant="Q", seq=1)
        other = self.frame(variant="Q", seq=2)
        with self.assertRaises(collector.CollectorError):
            self.cell.record_frame(first, boot_id="boot-1", reread=other)
        self.assertTrue(self.campaign.stopped)

    def test_a_matching_reread_is_accepted(self):
        frame = self.frame(variant="Q", seq=1)
        sample = self.cell.record_frame(frame, boot_id="boot-1", reread=frame)
        self.assertTrue(sample["reread_matched"])

    def test_the_run_sequence_comes_from_the_frame(self):
        self.cell.record_frame(self.frame(variant="Q", seq=1), boot_id="boot-1")
        # The firmware's own run_sequence restarted; that is a boot boundary
        # inside a cell however the caller numbers its runs.
        with self.assertRaises(collector.CollectorError):
            self.cell.record_frame(self.frame(variant="Q", seq=1), boot_id="boot-1")
        self.assertTrue(self.campaign.stopped)


class EndToEndRejectionTests(unittest.TestCase):
    """Detection has to reach refusal, and refusal has to reach the campaign.

    The classifier could notice a problem and still return a sample the
    collector accepted: every test asserted `problems` was non-empty and none
    asserted `sample_valid` was then False, so the link between the two was
    untested in both directions. This walks the whole path for one mutation at
    a time -- raw frame, parse, classify, validity, collector, cell, campaign.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.campaign = collector.Campaign(self._tmp.name, IDENTITY)

    def tearDown(self):
        self._tmp.cleanup()

    def mutations(self):
        from host.tests import test_pmu_completion_visibility_v14 as frames
        return (
            ("pre-submit running", frames.mutate_pre_submit_running),
            ("stale interrupt", frames.mutate_pre_submit_stale_irq),
            ("stale cmd_end", frames.mutate_pre_submit_stale_cmd_end),
            ("pre-program fault", frames.mutate_pre_program_fault),
            ("reset in the first tuple", frames.mutate_first_tuple_reset),
            ("convergence without cmd_end", frames.mutate_convergence_not_converged),
            ("short convergence cursor", frames.mutate_convergence_qread_short),
            ("interrupt enabled", frames.mutate_nvic_enabled),
            ("observed nothing", frames.mutate_first_tuple_observed_nothing),
        )

    def test_every_contract_violation_is_refused_all_the_way_to_the_campaign(self):
        from host.tests import test_pmu_completion_visibility_v14 as frames
        from host import runner_proto_pmu_completion_visibility_v14 as proto

        for label, mutate in self.mutations():
            with self.subTest(label):
                campaign = collector.Campaign(
                    tempfile.mkdtemp(dir=self._tmp.name), IDENTITY
                )
                cell = campaign.cell(1, 1, "QS")
                # Four good runs first, so the refusal has something to discard.
                for run_id in range(1, 5):
                    cell.record_frame(
                        frames.build_frame("QS", seq=run_id), boot_id="boot-1"
                    )
                self.assertEqual(len(cell.samples), 4)

                payload = frames.build_frame(
                    "QS", mutate(frames.canonical_appendix("QS")), seq=5
                )
                # The parser accepts it: this is a well-formed V14 frame.
                result = proto.parse_payload(payload)
                document = proto.classify_payload(result)
                # The classifier notices...
                self.assertTrue(document["problems"], "%s: nothing detected" % label)
                # ...and refuses...
                self.assertFalse(document["sample_valid"], "%s: detected, not refused" % label)
                # ...and the refusal reaches the campaign.
                with self.assertRaises(collector.CollectorError):
                    cell.record_frame(payload, boot_id="boot-1")
                self.assertEqual(cell.samples, [], label)
                self.assertFalse(cell.complete, label)
                self.assertTrue(campaign.stopped, label)
                self.assertEqual(len(campaign.quarantined()), 1, label)
                self.assertEqual(campaign.completed_cells(), [], label)

    def test_a_detected_problem_always_invalidates_the_sample(self):
        # The link C28 showed was untested, asserted directly: there is no
        # frame the classifier complains about and still calls a sample.
        from host.tests import test_pmu_completion_visibility_v14 as frames
        from host import runner_proto_pmu_completion_visibility_v14 as proto

        for label, mutate in self.mutations():
            document = proto.classify_payload(
                proto.parse_payload(
                    frames.build_frame("QS", mutate(frames.canonical_appendix("QS")))
                )
            )
            self.assertEqual(
                bool(document["problems"]), not document["sample_valid"], label
            )

    def test_the_collector_cannot_be_handed_a_verdict(self):
        # record_frame takes bytes. There is no argument through which a caller
        # can assert that a bad frame was fine.
        import inspect

        signature = inspect.signature(collector.Cell.record_frame)
        self.assertEqual(
            [name for name in signature.parameters if name != "self"],
            ["payload", "boot_id", "reread"],
        )
