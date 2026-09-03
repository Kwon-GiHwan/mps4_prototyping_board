"""The coverage matrix is data, so it is checked rather than believed.

A table that names a rule which no longer exists, or a test that was renamed, is
worse than no table: it reports coverage that has quietly gone away. So every
reference in it is resolved against the tree -- firmware rules against the
checker's own claim matrix, host functions against their modules, test names
against the test modules that should hold them.

The other half is authority. Each requirement names exactly one layer whose
answer is the answer, and the same layer may not appear as a corroborator of a
claim it decides: that is the ambiguity the table exists to remove.
"""

import ast
import importlib
import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))
sys.path.insert(0, str(REPO / "firmware" / "Selftest_pmu_diag"))

import requirements_pmu_completion_visibility_v14 as matrix  # noqa: E402


TEST_DIRECTORIES = (
    REPO / "host" / "tests",
    REPO / "firmware" / "Selftest_pmu_diag",
)


def _test_names(module_name):
    """Every callable defined at any level in a test module, by name."""

    for directory in TEST_DIRECTORIES:
        path = directory / ("%s.py" % module_name)
        if path.is_file():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return None


def _firmware_checker():
    return importlib.import_module("check_pmu_completion_visibility_v14")


class MatrixResolves(unittest.TestCase):
    def test_every_firmware_rule_exists_and_is_claim_matrix_bound(self):
        # Being in the claim matrix is what makes a rule worth citing here: that
        # membership is what guarantees it has a targeted negative which fails at
        # that rule, and that its detector runs against the real images.
        gate = _firmware_checker()
        bound = {rule for _claim, _detector, rule in gate.CLAIM_MATRIX}
        named = {rule for requirement in matrix.REQUIREMENTS for rule in requirement["rules"]}
        self.assertTrue(named, "the matrix cites no firmware rule at all")
        for rule in sorted(named):
            self.assertTrue(hasattr(gate, rule), rule)
            self.assertIn(rule, bound, "%s is not in the claim matrix" % rule)

    def test_every_claim_matrix_rule_is_carried_by_some_requirement(self):
        # The other direction: a load-bearing rule the requirements table forgot
        # is coverage nobody is accounting for.
        gate = _firmware_checker()
        bound = {rule for _claim, _detector, rule in gate.CLAIM_MATRIX}
        named = {rule for requirement in matrix.REQUIREMENTS for rule in requirement["rules"]}
        self.assertEqual(sorted(bound - named), [], "rules no requirement carries")

    def test_every_named_function_exists(self):
        for requirement in matrix.REQUIREMENTS:
            for reference in requirement["functions"]:
                module_name, _, attribute = reference.partition(":")
                target = importlib.import_module(module_name)
                # A dotted attribute is a method: the decision can live on a
                # class as easily as on a function, and naming the class is more
                # honest than pointing at the module and hoping.
                for part in attribute.split("."):
                    self.assertTrue(
                        hasattr(target, part), "%s: %s" % (requirement["id"], reference)
                    )
                    target = getattr(target, part)

    def test_every_named_test_exists(self):
        for requirement in matrix.REQUIREMENTS:
            for reference in requirement["tests"]:
                module_name, _, test_name = reference.partition(":")
                names = _test_names(module_name)
                self.assertIsNotNone(names, "%s: no module %s" % (requirement["id"], module_name))
                self.assertIn(test_name, names, "%s: %s" % (requirement["id"], reference))


class AuthorityIsUnambiguous(unittest.TestCase):
    def test_every_requirement_names_one_known_layer(self):
        for requirement in matrix.REQUIREMENTS:
            self.assertIn(requirement["authority"], matrix.LAYERS, requirement["id"])

    def test_no_layer_both_decides_and_corroborates_the_same_claim(self):
        for requirement in matrix.REQUIREMENTS:
            self.assertNotIn(
                requirement["authority"], requirement["corroborated_by"], requirement["id"]
            )

    def test_identifiers_are_unique(self):
        identifiers = [requirement["id"] for requirement in matrix.REQUIREMENTS]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_every_requirement_carries_evidence(self):
        for requirement in matrix.REQUIREMENTS:
            self.assertTrue(
                requirement["rules"] or requirement["tests"],
                "%s cites nothing that could fail" % requirement["id"],
            )

    def test_every_layer_that_decides_anything_is_represented(self):
        # A layer that decides nothing is either redundant or forgotten, and both
        # are worth noticing rather than leaving implicit.
        deciding = {requirement["authority"] for requirement in matrix.REQUIREMENTS}
        self.assertEqual(sorted(deciding), sorted(matrix.LAYERS))


class ExitCriteria(unittest.TestCase):
    def test_the_step_seven_numbers_are_what_the_table_reports(self):
        summary = matrix.summary()
        self.assertEqual(summary["untested"], [])
        self.assertEqual(summary["ambiguous_authority"], [])
        self.assertEqual(summary["qualified"], summary["load_bearing"])

    def test_every_elf_authority_requirement_reaches_the_real_images(self):
        # An ELF claim that has never been applied to the built image is a claim
        # about a fixture.
        for requirement in matrix.REQUIREMENTS:
            if requirement["authority"] == matrix.ELF:
                self.assertTrue(requirement["real_artifact"], requirement["id"])


if __name__ == "__main__":
    unittest.main()
