"""Run the frozen V14 fixtures against the separately identified successor.

The original fixture module is read without changing it. Three narrowly scoped
AST adaptations redirect its source inspections and alias instrumentation to
the actual implementation modules; the efficacy trace is explicitly multi-file.
"""

import ast
import inspect
import pathlib
import re
import subprocess
import sys
import unittest


FIRMWARE = pathlib.Path(__file__).resolve().parents[2]
DIAG = FIRMWARE / "Selftest_pmu_diag"
sys.path.insert(0, str(FIRMWARE))
sys.path.insert(0, str(DIAG))

import test_check_pmu_completion_visibility_v14 as fixtures  # noqa: E402
from gates import completion_visibility as successor  # noqa: E402


class GateView:
    """Expose frozen fixture internals without widening the production API."""

    def __getattr__(self, name):
        if hasattr(successor, name):
            return getattr(successor, name)
        for module in successor.IMPLEMENTATION_MODULES:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)


gate = GateView()


def implementation_sources():
    sources = {}
    for module in gate.IMPLEMENTATION_MODULES:
        path = pathlib.Path(module.__file__).resolve()
        if path in sources:
            raise AssertionError("duplicate implementation module: %s" % path)
        source = path.read_text(encoding="utf-8")
        if not source.strip():
            raise AssertionError("empty implementation module: %s" % path)
        sources[path] = source
    if len(sources) < 2:
        raise AssertionError("successor efficacy requires multiple implementation files")
    package = pathlib.Path(successor.__file__).resolve().parent
    expected = {
        path.resolve() for path in package.glob("*.py")
        if path.name not in {"__init__.py", "__main__.py", "identity.py"}
    }
    if set(sources) != expected:
        raise AssertionError("implementation source inventory is incomplete")
    return sources


def implementation_source():
    return "\n".join(implementation_sources().values())


def adapt_fixture(function, kind):
    """Change only the known frozen-suite coupling, failing on fixture drift."""
    tree = ast.parse(inspect.getsource(function))
    changes = 0

    class Adapt(ast.NodeTransformer):
        def visit_Assign(self, node):
            nonlocal changes
            if kind == "claim_source" and len(node.targets) == 1 and isinstance(
                node.targets[0], ast.Name
            ) and node.targets[0].id == "source":
                changes += 1
                return ast.copy_location(
                    ast.parse("source = _successor_source()").body[0], node
                )
            return self.generic_visit(node)

        def visit_With(self, node):
            nonlocal changes
            if kind == "manifest_source" and any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "open"
                and item.context_expr.args
                and isinstance(item.context_expr.args[0], ast.Name)
                and item.context_expr.args[0].id == "CHECKER_PATH"
                for item in node.items
            ):
                changes += 1
                return ast.copy_location(
                    ast.parse("source = _successor_source()").body[0], node
                )
            return self.generic_visit(node)

        def visit_Attribute(self, node):
            nonlocal changes
            if kind == "alias_owner" and isinstance(node.ctx, ast.Store) and (
                isinstance(node.value, ast.Name)
                and node.value.id == "gate"
                and node.attr == "resolve_address_role"
            ):
                changes += 1
                node.value = ast.copy_location(
                    ast.Name(id="_alias_owner", ctx=ast.Load()), node.value
                )
            return self.generic_visit(node)

        def visit_Return(self, node):
            nonlocal changes
            if kind == "alias_owner" and isinstance(node.value, ast.Tuple) and (
                ast.unparse(node.value.elts[0]) == "calls[0]"
            ):
                changes += 1
                assertion = ast.parse(
                    "assert calls[0] > 0, 'alias instrumentation did not run'"
                ).body[0]
                return [ast.copy_location(assertion, node), node]
            return self.generic_visit(node)

    tree = Adapt().visit(tree)
    expected = 3 if kind == "alias_owner" else 1
    if changes != expected:
        raise AssertionError(
            "%s adaptation changed %d sites, expected %d" % (kind, changes, expected)
        )
    ast.fix_missing_locations(tree)
    namespace = fixtures.__dict__
    namespace["_successor_source"] = implementation_source
    namespace["_alias_owner"] = sys.modules[gate.pointer_roles.__module__]
    exec(compile(tree, inspect.getsourcefile(function), "exec"), namespace)


def run_gate_efficacy_suite(successor, patcher):
    """Apply the original seven efficacy claims over every implementation file."""
    records = []
    raise_sites = {}
    for path, source in implementation_sources().items():
        lines = source.splitlines()
        tree = ast.parse(source)
        functions = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        records.append((path, lines, tree, functions))
        for index, line in enumerate(lines):
            hit = re.search(r"raise fail_rule\((RULE_[A-Z0-9_]+)?", line)
            if hit is None:
                continue
            rule = hit.group(1)
            if rule is None and index + 1 < len(lines):
                following = lines[index + 1].strip().rstrip(",")
                rule = following if following.startswith("RULE_") else None
            if rule is not None:
                raise_sites.setdefault(rule, []).append((path, index + 1))

    def enclosing(path, lineno):
        functions = next(record[3] for record in records if record[0] == path)
        holders = [f for f in functions if f.lineno <= lineno <= f.end_lineno]
        if not holders:
            return None
        return min(holders, key=lambda f: f.end_lineno - f.lineno).name

    def owners(detector, rule):
        if detector == "several":
            return {enclosing(path, line) for path, line in raise_sites.get(rule, [])}
        return {detector}

    executed = set()
    targets = {str(record[0]): record[0] for record in records}
    # The frozen fixtures add a path containing ".." to sys.path. CPython
    # retains that spelling in co_filename even though our inventory resolves it.
    for module in successor.IMPLEMENTATION_MODULES:
        targets[module.__file__] = pathlib.Path(module.__file__).resolve()

    def tracer(frame, event, arg):
        path = targets.get(frame.f_code.co_filename)
        if path is None:
            return None
        if event == "line":
            executed.add((path, frame.f_lineno))
        return tracer

    generated = []
    runner_stock = fixtures.load_real_runner_stock()
    vendor_stock = fixtures.load_real_vendor_stock()
    for variant in fixtures.VARIANTS:
        runner, _ = patcher.patch_runner(runner_stock, variant)
        vendor, _ = patcher.patch_vendor(vendor_stock, variant)
        generated.append((variant, runner, vendor))
    previous_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        for variant in fixtures.VARIANTS:
            successor.verify_linked_image(
                fixtures.linked_image(variant), fixtures.linked_nm(variant), variant,
                dwarf_text=fixtures.linked_dwarf() if variant == "Q" else None,
            )
        successor.verify_read_order_equivalence(
            fixtures.linked_image("QS"), fixtures.linked_image("SQ")
        )
        successor.verify_common_tail_is_shared(
            {name: fixtures.linked_image(name) for name in fixtures.VARIANTS}
        )
        for variant, runner, vendor in generated:
            successor.verify_generated_sources(runner, vendor, variant)
    finally:
        sys.settrace(previous_trace)

    fixtures.check(
        "the efficacy trace executed this gate", len(executed) > 1000, len(executed)
    )
    unapplied = []
    for _claim, detector, rule in successor.CLAIM_MATRIX:
        owned = owners(detector, rule)
        reached = any(
            (path, line) in executed
            for path, _lines, _tree, functions in records
            for function in functions if function.name in owned
            for line in range(function.lineno, function.end_lineno + 1)
        )
        if not reached:
            unapplied.append((rule, sorted(owner for owner in owned if owner)))
    fixtures.check(
        "every load-bearing claim's detector runs against the real artifacts",
        not unapplied,
        unapplied[:3],
    )
    counted = {}
    for path, lines, tree, _functions in records:
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)) and (
                (path, node.lineno) in executed and (path, node.body[0].lineno) not in executed
            ):
                key = (
                    enclosing(path, node.lineno),
                    " ".join(lines[node.lineno - 1].split()),
                )
                counted[key] = counted.get(key, 0) + 1
    measured = {(name, head, count) for (name, head), count in counted.items()}
    declared = set(successor.VACUOUS_ON_REAL_ARTIFACTS)
    fixtures.check(
        "no loop examines nothing on the real artifacts without being declared",
        measured <= declared,
        sorted(measured - declared)[:3],
    )
    fixtures.check(
        "every declared vacuous loop is still vacuous, and still there",
        declared <= measured,
        sorted(declared - measured)[:3],
    )
    measured_count = sum(key[2] for key in measured)
    declared_count = sum(key[2] for key in declared)
    fixtures.check(
        "the number of loops that examine nothing has not moved",
        measured_count == declared_count == 18,
        (measured_count, declared_count),
    )
    incomplete = [
        key for key, entry in successor.VACUOUS_ON_REAL_ARTIFACTS.items()
        if not all(
            entry.get(field)
            for field in ("proves", "scope", "why_vacuous", "evidence_instead")
        )
    ]
    fixtures.check(
        "every declared vacuity says what proves its claim instead",
        not incomplete,
        [key[0] for key in incomplete][:3],
    )
    vacuous_headers = {(key[0], key[1]) for key in measured}
    resting = []
    for _claim, detector, rule in successor.CLAIM_MATRIX:
        owned = owners(detector, rule)
        loops = [
            (path, lines, node) for path, lines, tree, _functions in records
            for node in ast.walk(tree)
            if isinstance(node, (ast.For, ast.While))
            and enclosing(path, node.lineno) in owned
        ]
        entered = [
            node for path, lines, node in loops
            if (enclosing(path, node.lineno), " ".join(lines[node.lineno - 1].split()))
            not in vacuous_headers
            and (path, node.body[0].lineno) in executed
        ]
        if loops and not entered:
            resting.append(rule)
    fixtures.check(
        "no load-bearing claim rests only on a path that examined nothing",
        not resting,
        resting[:3],
    )


def main():
    fixtures.CHECKER_PATH = str(FIRMWARE / "gates/completion_visibility/__main__.py")
    adapt_fixture(fixtures.run_claim_matrix_suite, "claim_source")
    adapt_fixture(fixtures.run_manifest_evidence_suite, "manifest_source")
    adapt_fixture(fixtures._check_alias_resolution_is_bounded, "alias_owner")
    fixtures._appendix_fields = lambda: gate.APPENDIX_FIELDS
    # Reuse the exact frozen invocation order. Only its two module imports and
    # efficacy function differ; all fixture calls and the 1241-count guard stay.
    fixtures.run_gate_efficacy_suite = run_gate_efficacy_suite
    source_tree = ast.parse(pathlib.Path(fixtures.__file__).read_text())
    main_blocks = [
        node for node in source_tree.body
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "__name__ == '__main__'"
    ]
    if len(main_blocks) != 1:
        raise AssertionError("the frozen fixture entry point changed")
    body = main_blocks[0].body
    gate_imports = 0

    class UseSuccessor(ast.NodeTransformer):
        def visit_Import(self, node):
            nonlocal gate_imports
            if any(
                alias.name == "check_pmu_completion_visibility_v14"
                for alias in node.names
            ):
                gate_imports += 1
                return ast.copy_location(
                    ast.parse("gate = _successor_gate").body[0], node
                )
            return node

    entry = UseSuccessor().visit(ast.Module(body=body, type_ignores=[]))
    if gate_imports != 1:
        raise AssertionError("the frozen gate import changed")
    ast.fix_missing_locations(entry)
    fixtures._successor_gate = gate
    exec(compile(entry, fixtures.__file__, "exec"), fixtures.__dict__)


class DirectSuiteExecution(unittest.TestCase):
    def test_every_frozen_fixture_runs_against_the_successor(self):
        result = subprocess.run(
            [sys.executable, "-u", str(pathlib.Path(__file__).resolve())],
            capture_output=True,
            text=True,
            timeout=600,
        )
        tail = result.stdout[-5000:] + result.stderr[-2000:]
        self.assertEqual(result.returncode, 0, tail)
        self.assertIn("passed=1241 failed=0", result.stdout, tail)


if __name__ == "__main__":
    main()
