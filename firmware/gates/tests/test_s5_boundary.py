"""Compare downstream S5 predicates against the frozen V15 implementation."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from firmware.gates import identity, s5_boundary
from firmware.gates.completion_visibility.errors import GateError as SuccessorGateError


FROZEN = identity.FIRMWARE / "Selftest_pmu_diag"


def load_reference(filename):
    name = "_s5_reference_" + Path(filename).stem
    spec = importlib.util.spec_from_file_location(name, FROZEN / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class S5BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = load_reference("check_s5_only_boundary_image.py")
        cls.v14 = load_reference("check_pmu_completion_visibility_v14.py")
        cls.objdump = (FROZEN / "fixtures/v15_probe/S5.objdump").read_text()
        cls.nm = (FROZEN / "fixtures/v15_probe/S5.nm").read_text()

    def compare(self, text):
        v12, v13 = identity.load_frozen_helpers()
        with patch.object(self.original, "_helpers", return_value=self.v14), patch.object(
            self.v14, "_elf_front_end", return_value=(v12.parse_functions, v13._split_code_and_literals)
        ):
            try:
                original = self.original.verify_s5_only_boundary_image(text)
            except (self.original.GateError, self.v14.GateError) as expected:
                with self.assertRaises((s5_boundary.GateError, SuccessorGateError)) as actual:
                    s5_boundary.verify_s5_only_boundary_image(text, expected_identity=identity.capture_identity())
                self.assertEqual(str(actual.exception), str(expected))
                return False
        successor = s5_boundary.verify_s5_only_boundary_image(text, expected_identity=identity.capture_identity())
        original.pop("helper_dependencies")
        record = successor.pop("successor_identity")
        self.assertEqual(record["qualification_status"], "UNQUALIFIED_SUCCESSOR")
        self.assertEqual(successor, original)
        return True

    def test_fixture_matches_frozen_detector(self):
        self.assertIn("v15_primary_s5", self.nm)
        self.assertTrue(self.compare(self.objdump))

    def test_input_mutations_preserve_refusals(self):
        changes = (
            ("tst.w\tr2, #32", "tst.w\tr2, #8"),
            ("ldr\tr2, [r1, #4]", "ldr\tr2, [r1, #24]"),
            ("ldr\tr2, [r1, #4]", "ldr\tr2, [r1, #28]"),
            ("<v15_primary_s5>:", "<removed_primary>:"),
            ("mov.w\tr3, #4294967295", "ldr\tr2, [r1, #4]"),
        )
        # Restrict replacements to this helper rather than unrelated functions.
        start = self.objdump.index("310024c0 <v15_primary_s5>:")
        end = self.objdump.index("31002534 <v15_converge>:", start)
        original = self.objdump[start:end]
        for before, after in changes:
            with self.subTest(before=before, after=after):
                self.assertIn(before, original)
                mutated = self.objdump[:start] + original.replace(before, after, 1) + self.objdump[end:]
                self.assertFalse(self.compare(mutated))

    def test_identity_checked_before_image_analysis(self):
        with patch.object(s5_boundary, "primary_phase_evidence") as analyze:
            with self.assertRaisesRegex(s5_boundary.GateError, "RULE_V15_HELPER_IDENTITY"):
                s5_boundary.verify_s5_only_boundary_image("not an image", expected_identity={})
            analyze.assert_not_called()
        with self.assertRaises(TypeError):
            s5_boundary.verify_s5_only_boundary_image(self.objdump)


if __name__ == "__main__":
    unittest.main()
