"""Offline regression for the package CLI and frozen transport boundary."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from host.experiments.completion_visibility import runner


REPO = Path(__file__).resolve().parents[3]


class RunnerBoundary(unittest.TestCase):
    def test_transport_timeout_uses_the_caught_exception_class(self):
        self.assertIs(runner.ProtocolError, runner.rq.ProtocolError)
        self.assertIs(runner.Nack, runner.rq.Nack)
        link = mock.Mock()
        link.next_sequence.return_value = 1
        link.read_frame.side_effect = runner.rq.ProtocolError("fixture timeout")
        with self.assertRaisesRegex(runner.RunSequenceError, "no ACK"):
            runner.collect_one(link)

    def test_ack_completion_and_independent_reread_keep_their_sequences(self):
        link = mock.Mock()
        link.next_sequence.side_effect = [1, 2]
        link.read_frame.side_effect = [
            SimpleNamespace(command=runner.CMD_RUN_PMU_DIAG | 0x80, sequence=1),
            SimpleNamespace(command=runner.CMD_PMU_DIAG_COMPLETE, sequence=1, payload=b"frame"),
            SimpleNamespace(command=runner.CMD_GET_PMU_DIAG_RESULT | 0x80, sequence=2, payload=b"frame"),
        ]
        self.assertEqual(runner.collect_one(link), (b"frame", b"frame"))
        self.assertEqual(link.send_raw.call_args_list, [
            mock.call(runner.build_frame(runner.CMD_RUN_PMU_DIAG, 1)),
            mock.call(runner.build_frame(runner.CMD_GET_PMU_DIAG_RESULT, 2)),
        ])

    def test_new_cli_paths_show_help_without_hardware_access(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            for name in ("runner", "protocol"):
                path = REPO / "host" / "experiments" / "completion_visibility" / f"{name}.py"
                for command, cwd in (
                    ([sys.executable, "-B", str(path), "--help"], directory),
                    ([sys.executable, "-B", "-m", f"host.experiments.completion_visibility.{name}", "--help"], REPO),
                ):
                    with self.subTest(command=command):
                        result = subprocess.run(
                            command, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=30,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
