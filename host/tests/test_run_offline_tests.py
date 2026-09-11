"""Verify the baseline runner's process boundary and failure reporting."""

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from host import run_offline_tests as runner


class OfflineRunnerTests(unittest.TestCase):
    def test_child_failure_is_reported_and_later_script_still_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tests = root / "host" / "tests"
            tests.mkdir(parents=True)
            (root / "host" / "__init__.py").touch()
            (tests / "__init__.py").touch()
            (tests / "failing.py").write_text(
                "import unittest\n"
                "class Failure(unittest.TestCase):\n"
                "    def test_failure(self):\n"
                "        self.fail('intentional runner regression fixture')\n"
            )
            (tests / "later.py").write_text(
                "import os\nfrom pathlib import Path\n"
                "assert Path.cwd() == Path(__file__).resolve().parents[2]\n"
                "assert os.environ['PYTHONPATH'] == str(Path.cwd() / 'host')\n"
                "Path('cache-used.txt').write_text(os.environ['PYTHONPYCACHEPREFIX'])\n"
            )
            output = io.StringIO()
            with (
                mock.patch.object(runner, "REPO_ROOT", root),
                mock.patch.object(runner, "UNITTEST_MODULES", ("host.tests.failing",)),
                mock.patch.object(runner, "SCRIPT_TESTS", ("host/tests/later.py",)),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(runner.main(), 1)
            self.assertIn("FAIL host.tests.failing: exit 1", output.getvalue())
            self.assertIn("PASS host/tests/later.py: exit 0", output.getvalue())
            self.assertIn("1 passed, 1 failed", output.getvalue())
            cache = Path((root / "cache-used.txt").read_text())
            self.assertFalse(cache.exists())

    def test_timeout_and_start_failure_do_not_hide_later_results(self):
        output = io.StringIO()
        with (
            mock.patch.object(runner, "UNITTEST_MODULES", ()),
            mock.patch.object(runner, "SCRIPT_TESTS", ("slow", "missing", "ok")),
            mock.patch.object(
                runner.subprocess,
                "run",
                side_effect=[
                    subprocess.TimeoutExpired(["python"], 90),
                    OSError("fixture launch failure"),
                    subprocess.CompletedProcess(["python"], 0),
                ],
            ) as run,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(runner.main(), 1)
        self.assertEqual(run.call_count, 3)
        self.assertIn("FAIL slow: timeout", output.getvalue())
        self.assertIn("FAIL missing: could not start", output.getvalue())
        self.assertIn("PASS ok: exit 0", output.getvalue())
        self.assertIn("1 passed, 2 failed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
