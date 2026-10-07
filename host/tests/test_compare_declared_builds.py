"""Unit tests for the declared-artifact build comparator.

The comparator is the tool that decides whether two independent builds of the
same variant produced the same evidence. It is therefore held to the shape of
the question rather than to a diff: a manifest *declares* a set of logical
artifacts with their digests, and the comparator answers whether both sides
declare the same set, whether every declared artifact is present, and whether
the bytes on disk are the ones the manifest claims. A manifest that leaks the
absolute build root or a timestamp is rejected outright -- two builds under
different roots would otherwise differ for a reason that says nothing about
determinism.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
COMPARATOR = REPO / "host" / "compare_declared_builds.py"
MANIFEST_NAME = "pmu_completion_visibility_v14_manifest.json"
VARIANTS = ("Q", "QS", "SQ")


def _digest(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _artifact(payload: bytes) -> dict:
    return {"sha256": _digest(payload), "bytes": len(payload)}


def _write_side(root: pathlib.Path, contents: dict, extra_manifest=None) -> None:
    """Lay out one build root: ``<root>/<variant>/`` per variant."""

    for variant in VARIANTS:
        directory = root / variant
        directory.mkdir(parents=True, exist_ok=True)
        declared = {}
        for name, payload in contents.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            declared[name] = _artifact(payload)
        manifest = {
            "variant": variant,
            "schema_version": 14,
            "build_id": "0x34314950",
            "frozen_input_sha256": {"runner": "a" * 64, "vendor": "b" * 64},
            "declared_artifacts": declared,
        }
        if extra_manifest is not None:
            manifest.update(extra_manifest(variant, directory))
        (directory / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


BASE = {
    "APP.BIN": b"app-bytes",
    "VECTORS.BIN": b"vectors-bytes",
    "DDR.BIN": b"ddr-bytes",
    "runner.elf": b"elf-bytes",
    "runner.map": b"map-bytes",
    "runner.nm": b"nm-bytes",
    "runner.objdump": b"objdump-bytes",
    "runner.dwarf.txt": b"dwarf-bytes",
    # The V14 manifest legitimately declares nested generated sources, so the
    # happy path has to carry one: separators are ordinary, traversal is not.
    "generated/Selftest_pmu_diag/runner_pmu_diag_main.c": b"generated-runner",
    "generated/Drivers/u85_driver/u85.c": b"generated-vendor",
}


class ComparatorContract(unittest.TestCase):
    def run_comparator(self, left, right, report):
        return subprocess.run(
            [
                sys.executable,
                str(COMPARATOR),
                "--left",
                str(left),
                "--right",
                str(right),
                "--variants",
                ",".join(VARIANTS),
                "--manifest-name",
                MANIFEST_NAME,
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
        )

    def compare(self, mutate_right=None, extra_manifest=None):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "BUILD_A", root / "BUILD_B"
            _write_side(left, BASE, extra_manifest)
            _write_side(right, BASE, extra_manifest)
            if mutate_right is not None:
                mutate_right(right)
            report = root / "report.json"
            result = self.run_comparator(left, right, report)
            payload = json.loads(report.read_text()) if report.exists() else None
            return result, payload

    def test_identical_builds_compare_clean(self):
        result, report = self.compare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(sorted(report["variants"]), sorted(VARIANTS))

    # ------------------------------------------------------------------
    # One tree wearing two names
    #
    # Every symlink shape below was already refused, and all four of these were
    # accepted: the comparator would report ``mismatches=[]`` and exit zero for
    # a comparison that never had two builds in it. That is the exact shape of
    # a determinism claim that was never tested, produced by the tool the whole
    # contract's determinism evidence comes from.
    # ------------------------------------------------------------------

    def test_the_same_root_on_both_sides_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left = root / "BUILD_A"
            _write_side(left, BASE)
            result = self.run_comparator(left, left, root / "report.json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("same directory", result.stderr)

    def test_a_path_alias_of_one_root_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left = root / "BUILD_A"
            _write_side(left, BASE)
            for alias in (left / ".", left / "Q" / ".."):
                result = self.run_comparator(left, alias, root / "report.json")
                self.assertEqual(result.returncode, 2, "%s: %s" % (alias, result.stdout))
                self.assertIn("same directory", result.stderr)

    def test_a_root_nested_inside_the_other_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left = root / "BUILD_A"
            inner = left / "inner"
            _write_side(left, BASE)
            _write_side(inner, BASE)
            result = self.run_comparator(left, inner, root / "report.json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("nested", result.stderr)

    def test_hardlinked_artifacts_are_not_two_builds(self):
        # A hardlink carries no marker a path check can see: the file is one
        # inode under two names, and it agrees with itself forever.
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "BUILD_A", root / "BUILD_B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            linked = right / "Q" / "APP.BIN"
            linked.unlink()
            os.link(left / "Q" / "APP.BIN", linked)
            report = root / "report.json"
            result = self.run_comparator(left, right, report)
            payload = json.loads(report.read_text())
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any(m["kind"] == "alias" and m["artifact"] == "APP.BIN" for m in payload["mismatches"]),
            payload["mismatches"],
        )

    def test_a_hardlinked_manifest_is_not_two_builds(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "BUILD_A", root / "BUILD_B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            linked = right / "QS" / MANIFEST_NAME
            linked.unlink()
            os.link(left / "QS" / MANIFEST_NAME, linked)
            report = root / "report.json"
            result = self.run_comparator(left, right, report)
            payload = json.loads(report.read_text())
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any(m["kind"] == "alias" for m in payload["mismatches"]), payload["mismatches"]
        )

    def test_two_independent_trees_are_still_ordinary(self):
        # The other half of the same rule: refusing aliases must not refuse the
        # thing the comparison exists to accept.
        result, report = self.compare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["mismatches"], [])

    def test_missing_declared_artifact_is_a_mismatch(self):
        def drop(right):
            (right / "Q" / "APP.BIN").unlink()

        result, report = self.compare(drop)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(m["kind"] == "missing" for m in report["mismatches"]))

    def test_byte_different_artifact_is_a_mismatch(self):
        def flip(right):
            (right / "QS" / "DDR.BIN").write_bytes(b"ddr-bytes-different")

        result, report = self.compare(flip)
        self.assertNotEqual(result.returncode, 0)
        kinds = {m["kind"] for m in report["mismatches"]}
        self.assertTrue({"digest", "declared"} & kinds, report["mismatches"])

    def test_substituted_declaration_is_a_mismatch(self):
        def substitute(right):
            path = right / "SQ" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["declared_artifacts"]["runner.elf"]["sha256"] = "0" * 64
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        result, report = self.compare(substitute)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report["mismatches"])

    def test_extra_declared_artifact_is_a_mismatch(self):
        def add(right):
            path = right / "Q" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            (right / "Q" / "EXTRA.BIN").write_bytes(b"extra")
            manifest["declared_artifacts"]["EXTRA.BIN"] = _artifact(b"extra")
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        result, report = self.compare(add)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(m["kind"] == "extra" for m in report["mismatches"]))

    def test_absolute_path_leakage_is_rejected(self):
        def leak(variant, directory):
            return {"build_root": str(directory)}

        result, report = self.compare(extra_manifest=leak)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(m["kind"] == "leakage" for m in report["mismatches"]))

    def test_timestamp_leakage_is_rejected(self):
        def leak(variant, directory):
            return {"built_at": "2026-08-15T12:00:00Z"}

        result, report = self.compare(extra_manifest=leak)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(m["kind"] == "leakage" for m in report["mismatches"]))

    def test_missing_manifest_is_a_mismatch_not_a_traceback(self):
        def drop_manifest(right):
            (right / "Q" / MANIFEST_NAME).unlink()

        result, report = self.compare(drop_manifest)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(any(m["kind"] == "manifest" for m in report["mismatches"]))

    # --- artifact names: nesting is ordinary, escaping the root is not -------

    def _declare(self, right, variant, name, entry):
        path = right / variant / MANIFEST_NAME
        manifest = json.loads(path.read_text())
        manifest["declared_artifacts"][name] = entry
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    def assert_rejected(self, mutate, kind=None):
        result, report = self.compare(mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(report["mismatches"], report)
        if kind is not None:
            self.assertTrue(
                any(m["kind"] == kind for m in report["mismatches"]),
                report["mismatches"],
            )

    def test_nested_relative_artifact_paths_are_ordinary(self):
        nested = [name for name in BASE if "/" in name]
        self.assertTrue(nested, "the positive contract needs a nested artifact to exercise")

        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "BUILD_A", root / "BUILD_B"
            _write_side(left, BASE)
            _write_side(right, BASE)

            # The nested artifacts really are declared and really are on disk at
            # the nested path, on both sides -- otherwise this would pass by
            # never testing nesting at all.
            for side in (left, right):
                manifest = json.loads((side / "Q" / MANIFEST_NAME).read_text())
                for name in nested:
                    self.assertIn(name, manifest["declared_artifacts"])
                    self.assertTrue((side / "Q" / name).is_file(), name)
                    self.assertEqual(
                        manifest["declared_artifacts"][name]["sha256"], _digest(BASE[name])
                    )

            report = root / "report.json"
            result = self.run_comparator(left, right, report)
            payload = json.loads(report.read_text())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(payload["mismatches"], [])

    def test_absolute_artifact_name_is_rejected(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "/etc/passwd", _artifact(b"x")),
            "artifact-path",
        )

    def test_parent_traversal_artifact_name_is_rejected(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "../QS/APP.BIN", _artifact(b"x")),
            "artifact-path",
        )

    def test_dot_and_empty_components_are_rejected(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "./APP.BIN", _artifact(b"x")),
            "artifact-path",
        )
        self.assert_rejected(
            lambda right: self._declare(right, "QS", "generated//u85.c", _artifact(b"x")),
            "artifact-path",
        )

    def test_symlinked_declared_artifact_is_rejected(self):
        def link(right):
            outside = right.parent / "outside.bin"
            outside.write_bytes(b"app-bytes")
            target = right / "Q" / "APP.BIN"
            target.unlink()
            target.symlink_to(outside)

        self.assert_rejected(link, "artifact-path")

    def test_empty_declared_artifacts_is_refused(self):
        def empty(right):
            path = right / "Q" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["declared_artifacts"] = {}
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        self.assert_rejected(empty, "manifest")

    def test_empty_declared_artifacts_on_both_sides_is_refused(self):
        """Two empty manifests agree on everything and prove nothing."""

        def empty(variant, directory):
            return {"declared_artifacts": {}}

        result, report = self.compare(extra_manifest=empty)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(any(m["kind"] == "manifest" for m in report["mismatches"]))

    # --- symlinked variant directories --------------------------------------

    def _symlink_variant(self, side, variant, target):
        import shutil

        directory = side / variant
        shutil.rmtree(directory)
        directory.symlink_to(target, target_is_directory=True)

    def test_variant_directory_symlinked_to_a_shared_tree_is_refused(self):
        """One tree behind two names compares clean while proving nothing."""

        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            shared = root / "SHARED"
            shared.mkdir()
            import shutil

            shutil.copytree(left / "Q", shared / "Q")
            self._symlink_variant(left, "Q", shared / "Q")
            self._symlink_variant(right, "Q", shared / "Q")
            report = root / "r.json"
            result = self.run_comparator(left, right, report)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            payload = json.loads(report.read_text())
            self.assertTrue(any(m["kind"] == "variant" for m in payload["mismatches"]))

    def test_variant_directory_symlinked_outside_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            outside = root / "ELSEWHERE"
            import shutil

            shutil.copytree(right / "QS", outside)
            self._symlink_variant(right, "QS", outside)
            report = root / "r.json"
            result = self.run_comparator(left, right, report)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            payload = json.loads(report.read_text())
            self.assertTrue(any(m["kind"] == "variant" for m in payload["mismatches"]))

    def test_symlinked_build_root_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            real, right = root / "REAL", root / "B"
            _write_side(real, BASE)
            _write_side(right, BASE)
            left = root / "A"
            left.symlink_to(real, target_is_directory=True)
            report = root / "r.json"
            result = self.run_comparator(left, right, report)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            payload = json.loads(report.read_text())
            self.assertTrue(any(m["kind"] == "variant" for m in payload["mismatches"]))

    def test_physical_variant_directories_are_accepted(self):
        """The positive control: honest directories with nonempty nested artifacts."""

        result, report = self.compare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["mismatches"], [])
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            for side in (left, right):
                for variant in VARIANTS:
                    self.assertFalse((side / variant).is_symlink())
                    self.assertTrue((side / variant).is_dir())
                manifest = json.loads((side / "Q" / MANIFEST_NAME).read_text())
                self.assertTrue(manifest["declared_artifacts"])

    # --- variant arguments ---------------------------------------------------

    def test_variant_outside_the_contract_set_is_a_caller_error(self):
        """Refused while reading the arguments, before anything is compared."""

        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            result = subprocess.run(
                [
                    sys.executable, str(COMPARATOR),
                    "--left", str(left), "--right", str(right),
                    "--variants", "Q,ZZ",
                    "--manifest-name", MANIFEST_NAME,
                    "--report", str(root / "r.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("ZZ", result.stderr)

    def test_absent_contract_variant_directory_is_a_reported_mismatch(self):
        def drop_variant(right):
            import shutil

            shutil.rmtree(right / "SQ")

        result, report = self.compare(drop_variant)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(any(m["kind"] == "variant" for m in report["mismatches"]))

    def test_variant_outside_the_contract_set_is_refused_even_when_populated(self):
        """A populated ZZ tree must not pass merely by existing on both sides."""

        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            # Give ZZ a complete, self-consistent tree on both sides: absence is
            # not what makes it wrong, being outside the contract set is.
            for side in (left, right):
                directory = side / "ZZ"
                directory.mkdir(parents=True, exist_ok=True)
                declared = {}
                for name, payload in BASE.items():
                    target = directory / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    declared[name] = _artifact(payload)
                (directory / MANIFEST_NAME).write_text(
                    json.dumps(
                        {
                            "variant": "ZZ",
                            "schema_version": 14,
                            "build_id": "0x34314950",
                            "frozen_input_sha256": {"runner": "a" * 64, "vendor": "b" * 64},
                            "declared_artifacts": declared,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
            result = subprocess.run(
                [
                    sys.executable, str(COMPARATOR),
                    "--left", str(left), "--right", str(right),
                    "--variants", "Q,ZZ",
                    "--manifest-name", MANIFEST_NAME,
                    "--report", str(root / "r.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_manifest_name_must_be_a_safe_basename(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            for unsafe in (
                "/etc/passwd",
                "../" + MANIFEST_NAME,
                "sub/" + MANIFEST_NAME,
                ".",
                "",
            ):
                result = subprocess.run(
                    [
                        sys.executable, str(COMPARATOR),
                        "--left", str(left), "--right", str(right),
                        "--variants", "Q",
                        "--manifest-name", unsafe,
                        "--report", str(root / "r.json"),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0, unsafe)
                self.assertNotIn("Traceback", result.stderr)

    def test_symlinked_manifest_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            outside = root / "outside_manifest.json"
            outside.write_text((right / "Q" / MANIFEST_NAME).read_text())
            target = right / "Q" / MANIFEST_NAME
            target.unlink()
            target.symlink_to(outside)
            report = root / "r.json"
            result = self.run_comparator(left, right, report)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            payload = json.loads(report.read_text())
            self.assertTrue(any(m["kind"] == "manifest" for m in payload["mismatches"]))

    def test_duplicate_and_empty_variants_are_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            left, right = root / "A", root / "B"
            _write_side(left, BASE)
            _write_side(right, BASE)
            for spec in ("Q,Q", "", " , "):
                result = subprocess.run(
                    [
                        sys.executable, str(COMPARATOR),
                        "--left", str(left), "--right", str(right),
                        "--variants", spec,
                        "--manifest-name", MANIFEST_NAME,
                        "--report", str(root / "r.json"),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0, spec)
                self.assertNotIn("Traceback", result.stderr)

    # --- malformed declarations ---------------------------------------------

    def test_non_dict_artifact_entry_is_a_mismatch(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "APP.BIN", "just-a-string"),
            "declaration",
        )

    def test_missing_sha256_is_a_mismatch(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "APP.BIN", {"bytes": 9}),
            "declaration",
        )

    def test_non_hex_sha256_is_a_mismatch(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "APP.BIN", {"sha256": "zz" * 32, "bytes": 9}),
            "declaration",
        )

    def test_missing_bytes_is_a_mismatch(self):
        self.assert_rejected(
            lambda right: self._declare(right, "Q", "APP.BIN", {"sha256": _digest(b"app-bytes")}),
            "declaration",
        )

    def test_non_integer_bytes_is_a_mismatch(self):
        for bad in ("9", 9.0, None, [9]):
            self.assert_rejected(
                lambda right, value=bad: self._declare(
                    right, "Q", "APP.BIN", {"sha256": _digest(b"app-bytes"), "bytes": value}
                ),
                "declaration",
            )

    def test_boolean_bytes_is_not_an_integer(self):
        self.assert_rejected(
            lambda right: self._declare(
                right, "Q", "APP.BIN", {"sha256": _digest(b"app-bytes"), "bytes": True}
            ),
            "declaration",
        )

    def test_negative_bytes_is_a_mismatch(self):
        self.assert_rejected(
            lambda right: self._declare(
                right, "Q", "APP.BIN", {"sha256": _digest(b"app-bytes"), "bytes": -1}
            ),
            "declaration",
        )

    def test_bytes_must_equal_the_on_disk_size(self):
        self.assert_rejected(
            lambda right: self._declare(
                right, "Q", "APP.BIN", {"sha256": _digest(b"app-bytes"), "bytes": 4096}
            ),
            "declared",
        )

    def test_bytes_drift_between_sides_is_a_mismatch(self):
        def drift(right):
            path = right / "QS" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            # Same digest on both sides, a byte count that disagrees: the
            # declaration must not be believed just because the hash matches.
            manifest["declared_artifacts"]["DDR.BIN"]["bytes"] = 1234
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        result, report = self.compare(drift)
        self.assertNotEqual(result.returncode, 0)
        kinds = {m["kind"] for m in report["mismatches"]}
        self.assertTrue({"declared", "size"} & kinds, report["mismatches"])

    # --- manifest identity ---------------------------------------------------

    def test_manifest_variant_must_match_the_requested_variant(self):
        def relabel(right):
            path = right / "Q" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["variant"] = "SQ"
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        self.assert_rejected(relabel, "identity")

    def test_manifest_schema_version_must_be_fourteen(self):
        def bump(right):
            path = right / "QS" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["schema_version"] = 13
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        self.assert_rejected(bump, "identity")

    def test_reproducible_metadata_is_compared_between_sides(self):
        def drift(right):
            path = right / "SQ" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["frozen_input_sha256"] = {"runner": "c" * 64, "vendor": "d" * 64}
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        self.assert_rejected(drift, "metadata")

    def test_build_id_drift_between_sides_is_a_mismatch(self):
        def drift(right):
            path = right / "Q" / MANIFEST_NAME
            manifest = json.loads(path.read_text())
            manifest["build_id"] = "0xDEADBEEF"
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        self.assert_rejected(drift, "metadata")

    def test_cli_requires_every_declared_option(self):
        help_text = subprocess.run(
            [sys.executable, str(COMPARATOR), "--help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for option in ("--left", "--right", "--variants", "--manifest-name", "--report"):
            self.assertIn(option, help_text)


if __name__ == "__main__":
    unittest.main()
