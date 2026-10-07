"""Keep the extraction behavior-preserving while the successor is qualified."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from firmware.gates import completion_visibility as gate


FIRMWARE = Path(__file__).resolve().parents[2]
FROZEN = FIRMWARE / 'Selftest_pmu_diag/check_pmu_completion_visibility_v14.py'


def definitions(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        result[name.id] = node
    return result


class ExtractionTests(unittest.TestCase):
    def test_all_frozen_definitions_preserve_their_ast(self):
        original = definitions(FROZEN.read_text())
        extracted = {}
        for module in gate.IMPLEMENTATION_MODULES:
            for name, node in definitions(Path(module.__file__).read_text()).items():
                self.assertNotIn(name, extracted, 'duplicate owner: ' + name)
                extracted[name] = node
        self.assertEqual(set(original), set(extracted))
        self.assertEqual(len(original), 586)
        # Only the frozen-dependency loader and output provenance change.
        for name in original.keys() - {'_elf_front_end', '_write_manifest'}:
            with self.subTest(name=name):
                self.assertEqual(ast.dump(original[name]), ast.dump(extracted[name]))

    def test_implementation_imports_form_an_acyclic_graph(self):
        modules = {module.__name__.rsplit('.', 1)[-1]: module for module in gate.IMPLEMENTATION_MODULES}
        graph = {}
        for name, module in modules.items():
            graph[name] = {
                node.module for node in ast.parse(Path(module.__file__).read_text()).body
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module in modules
            }
        done = set()
        def visit(name, active):
            self.assertNotIn(name, active, 'circular implementation import')
            if name in done:
                return
            for dependency in graph[name]:
                visit(dependency, active | {name})
            done.add(name)
        for name in graph:
            visit(name, set())

    def test_direct_cli_from_outside_repository(self):
        with tempfile.TemporaryDirectory() as cwd:
            completed = subprocess.run(
                [sys.executable, '-B', str(Path(gate.__file__).with_name('__main__.py')), '--help'],
                cwd=cwd, capture_output=True, text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('--allow-fixture', completed.stdout)

    def test_cli_records_identity_without_changing_the_fixture_verdict(self):
        from firmware.gates import identity
        from firmware.gates.tests.test_completion_visibility import fixtures

        runner = fixtures.canonical_runner('Q')
        vendor = fixtures.canonical_vendor('Q')
        with tempfile.TemporaryDirectory() as cwd:
            root = Path(cwd)
            (root / 'runner.c').write_text(runner)
            (root / 'vendor.c').write_text(vendor)
            output = root / 'manifest.json'
            completed = subprocess.run([
                sys.executable, '-B', '-m', 'firmware.gates.completion_visibility',
                '--allow-fixture', '--variant', 'Q',
                '--runner-generated', str(root / 'runner.c'),
                '--vendor-generated', str(root / 'vendor.c'),
                '--fixture-manifest-out', str(output),
            ], cwd=FIRMWARE.parent, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            document = json.loads(output.read_text())
        record = document.pop('checker_identity')
        self.assertEqual(record, identity.capture_identity())
        self.assertEqual(record['qualification_status'], 'UNQUALIFIED_SUCCESSOR')
        expected = gate.verify_generated_sources(runner, vendor, 'Q')
        self.assertEqual(document, json.loads(json.dumps(expected)))

    def test_module_cli(self):
        completed = subprocess.run(
            [sys.executable, '-B', '-m', 'firmware.gates.completion_visibility', '--help'],
            cwd=FIRMWARE.parent, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('--real-elf', completed.stdout)


if __name__ == '__main__':
    unittest.main()
