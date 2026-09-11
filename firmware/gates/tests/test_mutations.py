"""Prove targeted rule fixtures fail when a modular detector is disabled."""

import ast
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

from firmware.gates.tests.test_completion_visibility import fixtures, gate, successor


def refusing_rule(call):
    try:
        call()
    except Exception as exc:
        return gate.refusal_rule(exc)
    return None


def disabled_rule_functions(rule):
    """Compile temporary replacements; never change implementation files."""
    replacements = {}
    for module in gate.IMPLEMENTATION_MODULES:
        tree = ast.parse(Path(module.__file__).read_text())
        for function in tree.body:
            if not isinstance(function, ast.FunctionDef):
                continue
            removed = 0

            class Disable(ast.NodeTransformer):
                def visit_Raise(self, node):
                    nonlocal removed
                    call = node.exc
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == 'fail_rule'
                        and call.args
                        and isinstance(call.args[0], ast.Name)
                        and call.args[0].id == rule
                    ):
                        removed += 1
                        return ast.copy_location(ast.Pass(), node)
                    return self.generic_visit(node)

            function = Disable().visit(function)
            if not removed:
                continue
            rewritten = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
            namespace = {}
            exec(compile(rewritten, module.__file__, 'exec'), module.__dict__, namespace)
            replacements[getattr(module, function.name)] = namespace[function.name]
    return replacements


class RuleMutationTests(unittest.TestCase):
    def test_targeted_refusals_detect_disabled_rules(self):
        negatives = fixtures.targeted_negatives(gate)
        tested = set()
        for rule, call in negatives.items():
            with self.subTest(rule=rule):
                self.assertEqual(refusing_rule(call), rule, 'baseline negative did not reach its rule')
                replacements = disabled_rule_functions(rule)
                self.assertTrue(replacements, 'no detector mutation generated')
                with ExitStack() as stack:
                    # Update owners and explicit imported aliases together.
                    for module in (*gate.IMPLEMENTATION_MODULES, successor):
                        for name, value in vars(module).copy().items():
                            if callable(value) and value in replacements:
                                stack.enter_context(patch.object(module, name, replacements[value]))
                    self.assertNotEqual(refusing_rule(call), rule, 'disabled detector survived its fixture')
                tested.add(rule)
        self.assertEqual(tested, {rule for _, _, rule in gate.CLAIM_MATRIX})


if __name__ == '__main__':
    unittest.main()
