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
