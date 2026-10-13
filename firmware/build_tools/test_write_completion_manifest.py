"""Exercise both real manifest recipes with synthetic build artifacts."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


FIRMWARE = Path(__file__).resolve().parents[1]
WRITER = FIRMWARE / 'build_tools/write_completion_manifest.py'


class ManifestRecipeTests(unittest.TestCase):
    def make_fixture(self, root, suffix, variant):
        text = (FIRMWARE / ('Makefile.pmu_completion_' + suffix)).read_text()
        rule = text[text.index('$(MANIFEST):'):text.index('\n# BUILD is caller-supplied')]
        names = (
            'TARGET BUILD_ID GEN GEN_RUNNER GEN_VENDOR PREPROCESSED V14_NM '
            'V14_OBJDUMP V14_DWARF SOURCE_FIXTURE_EVIDENCE MAILBOX_WIRE_EVIDENCE '
            'RETAINED_BASE_PMU_EVIDENCE FROZEN_INPUT_EVIDENCE LINKED_IMAGE_EVIDENCE MANIFEST'
        ).split()
        definitions = [re.search(r'^' + name + r' := (.+)$', text, re.M).group(0) for name in names]
        resolved = {'BUILD': str(root), 'V14_VARIANT': variant, 'V15_VARIANT': variant}
        for _ in names:
            for definition in definitions:
                name, value = definition.split(' := ', 1)
                resolved[name] = re.sub(r'\$\((\w+)\)', lambda m: resolved.get(m[1], m[0]), value)
        artifacts = ['APP.BIN', 'VECTORS.BIN', 'DDR.BIN']
        artifacts += [Path(resolved['TARGET'] + ext).name for ext in ('.elf', '.map')]
        artifacts += [Path(resolved[name]).name for name in names if name in (
            'PREPROCESSED', 'V14_NM', 'V14_OBJDUMP', 'V14_DWARF',
            'SOURCE_FIXTURE_EVIDENCE', 'MAILBOX_WIRE_EVIDENCE',
            'RETAINED_BASE_PMU_EVIDENCE', 'FROZEN_INPUT_EVIDENCE', 'LINKED_IMAGE_EVIDENCE',
        )]
        artifacts += ['generated/Selftest_pmu_diag/runner_pmu_diag_main.c', 'generated/Drivers/u85_driver/u85.c']
        for name in artifacts:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture ' + name + '\n').encode())
        frozen = Path(resolved['FROZEN_INPUT_EVIDENCE'])
        frozen.write_text(json.dumps({'frozen_inputs': {'runner.c': 'a' * 64}}))
        makefile = root / 'fixture.mk'
        makefile.write_text('\n'.join([
            'BUILD := ' + str(root), 'V14_VARIANT := ' + variant,
            'V15_VARIANT := ' + variant, 'GATE :=', 'MANIFEST_WRITER := ' + str(WRITER),
            *definitions, rule,
        ]))
        return makefile, Path(resolved['MANIFEST']), artifacts, resolved

    def test_both_recipes_and_writer_dependency(self):
        variants = [('visibility_v14', name) for name in ('Q', 'QS', 'SQ')]
        variants.append(('s5_only_control', 'S5'))
        for suffix, variant in variants:
            with self.subTest(suffix=suffix, variant=variant), tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch)
                makefile, output, artifacts, resolved = self.make_fixture(root, suffix, variant)
                command = ['make', '-f', str(makefile), str(output)]
                done = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                document = json.loads(output.read_bytes())
                self.assertEqual(document['variant'], variant)
                self.assertEqual(document['build_id'], resolved['BUILD_ID'])
                self.assertEqual(document['schema_version'], 14)
                self.assertEqual(document['canonical_json'], 'v14-canonical-json-v1')
                self.assertEqual(document['frozen_input_sha256'], {'runner.c': 'a' * 64})
                self.assertEqual(set(document['declared_artifacts']), set(artifacts))
                for name, entry in document['declared_artifacts'].items():
                    payload = (root / name).read_bytes()
                    self.assertEqual(entry, {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
                digest = document.pop('manifest_self_hash')
                canonical = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
                self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())
                current = subprocess.run(command + ['-q'], capture_output=True)
                self.assertEqual(current.returncode, 0)
                stale = subprocess.run(command + ['-q', '-W', str(WRITER)], capture_output=True)
                self.assertEqual(stale.returncode, 1)

    def test_missing_artifact_does_not_write_manifest(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            output = root / 'manifest.json'
            done = subprocess.run([
                sys.executable, str(WRITER), '--build', str(root), '--variant', 'Q',
                '--build-id', 'example', '--frozen-evidence', str(root / 'frozen.json'),
                '--output', str(output), 'missing.bin',
            ], capture_output=True, text=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn('declared artifact missing', done.stderr)
            self.assertFalse(output.exists())

    def test_build_path_backticks_are_literal(self):
        for suffix, variant in [('visibility_v14', 'Q'), ('s5_only_control', 'S5')]:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch)
                build = root / '`>marker`'
                makefile, output, _, _ = self.make_fixture(build, suffix, variant)
                done = subprocess.run(
                    ['make', '-f', str(makefile), str(output)],
                    capture_output=True, text=True, cwd=root,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue(output.is_file())
                self.assertFalse((root / 'marker').exists())


if __name__ == '__main__':
    unittest.main()
