"""Offline checks for V9-V13 package and frozen transport boundaries."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
VERSIONS = (
    "interval.v9", "interval.v10", "interval.v11a",
    "completion_poll.v12", "completion_poll.v13",
)


class VersionedExperiments(unittest.TestCase):
    def test_versions_share_the_frozen_transport_exceptions(self):
        code = """
import importlib
import sys
from unittest import mock
versions = (
    ('interval.v9', 'collect_pmu_interval_v9'),
    ('interval.v10', 'collect_pmu_interval_v10'),
    ('interval.v11a', 'collect_pmu_interval_v11a'),
    ('completion_poll.v12', 'collect_pmu_completion_poll_v12'),
    ('completion_poll.v13', 'collect_pmu_completion_poll_count_v13'),
)
for version, collect in versions:
    package = 'host.experiments.' + version
    runner = importlib.import_module(package + '.runner')
    protocol = importlib.import_module(package + '.protocol')
    importlib.import_module(package + '.analysis')
    assert runner.ProtocolError is protocol.v8.ProtocolError
    assert runner.ProtocolError is runner.rq.ProtocolError
    link = mock.Mock()
    link.next_sequence.return_value = 1
    link.read_frame.side_effect = runner.rq.ProtocolError('fixture timeout')
    try:
        getattr(runner, collect)(link)
    except runner.RunSequenceError as exc:
        assert 'no ACK' in str(exc), str(exc)
    else:
        raise AssertionError('timeout was accepted')
from host.experiments.completion_poll.v13 import protocol as v13
from host.experiments.completion_poll.v12 import protocol as v12
assert v13.v12 is v12
assert 'serial' not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=REPO,
            env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_help_works_as_module_and_external_direct_script(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            for version in VERSIONS:
                # V12 analysis is a library; it has no CLI.
                roles = ("runner",) if version == "completion_poll.v12" else ("runner", "analysis")
                for role in roles:
                    module = f"host.experiments.{version}.{role}"
                    path = REPO.joinpath(*module.split(".")).with_suffix(".py")
                    for args, cwd in (([str(path)], directory), (["-m", module], REPO)):
                        with self.subTest(module=module, args=args):
                            result = subprocess.run(
                                [sys.executable, "-B", *args, "--help"],
                                cwd=cwd, env=env, capture_output=True,
                                text=True, timeout=30,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
