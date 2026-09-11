"""V15 package imports must share classes and patch targets in a fresh process."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
V15_MODULES = (
    "analysis", "canonical_elf", "collector", "comparison_mode", "contract",
    "deployment", "inheritance", "normalize", "preflight", "protocol",
)


class V15Imports(unittest.TestCase):
    def test_vocabulary_guard_rejects_mutations_in_source_and_tests(self):
        from host.experiments.s5_only import contract
        from host.tests.s5_only.test_contract import ForbiddenVocabulary

        read_text = Path.read_text
        guard = ForbiddenVocabulary(
            "test_no_forbidden_name_appears_in_any_other_v15_module"
        )
        for relative in (
            "host/experiments/s5_only/analysis.py",
            "host/tests/s5_only/test_analysis.py",
        ):
            target = REPO / relative

            def mutated_text(path, *args, **kwargs):
                text = read_text(path, *args, **kwargs)
                if path == target:
                    text += "\n" + contract.FORBIDDEN_FIELD_NAMES[0]
                return text

            with (
                self.subTest(path=relative),
                mock.patch.object(Path, "read_text", mutated_text),
                self.assertRaisesRegex(AssertionError, target.name),
            ):
                guard.test_no_forbidden_name_appears_in_any_other_v15_module()

    def test_package_dependencies_share_identity_and_patch_targets(self):
        code = """
from unittest import mock
from host.experiments.s5_only import normalize as normalizer
from host.experiments.s5_only import collector as collector
from host.experiments.s5_only import deployment as deployment
from host.experiments.s5_only import protocol as wire
from host import runner_proto as base
assert normalizer.deployment is deployment
assert normalizer.wire is wire
assert collector.normalizer is normalizer
assert collector.deployment is deployment
assert wire.ProtocolError is base.ProtocolError
with mock.patch.object(wire, 'parse_frame', return_value='patched'):
    assert normalizer.wire.parse_frame(b'') == 'patched'
try:
    raise normalizer.wire.ProtocolError('fixture')
except base.ProtocolError:
    pass
import importlib
import pathlib
import sys
for path in pathlib.Path('host/experiments/s5_only').glob('*.py'):
    importlib.import_module('host.experiments.s5_only.' + path.stem)
assert not any(name.endswith('_pmu_completion_s5_only_control') for name in sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=REPO,
            env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_direct_scripts_work_outside_repo_without_pythonpath(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            for name in V15_MODULES:
                path = REPO / "host" / "experiments" / "s5_only" / f"{name}.py"
                with self.subTest(script=path.name):
                    result = subprocess.run(
                        [sys.executable, "-B", str(path)],
                        cwd=directory,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
