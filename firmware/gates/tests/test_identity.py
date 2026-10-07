"""Successor identities reject missing and changed implementation inputs."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from firmware.gates import identity


class IdentityTests(unittest.TestCase):
    def test_complete_identity_and_unqualified_status(self):
        record = identity.capture_identity()
        actual_python = {
            p.relative_to(identity.FIRMWARE).as_posix()
            for p in (identity.FIRMWARE / "gates").rglob("*.py")
            if "tests" not in p.parts
        }
        self.assertEqual(actual_python, {p for p in record["files"] if p.startswith("gates/")})
        self.assertEqual(record["qualification_status"], "UNQUALIFIED_SUCCESSOR")
        self.assertEqual(identity.verify_identity(record), record)

    def test_each_dependency_is_required_and_byte_sensitive(self):
        record = identity.capture_identity()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in record["files"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(identity.FIRMWARE / name, path)
            self.assertEqual(identity.verify_identity(record, firmware_root=root), record)
            for name in record["files"]:
                with self.subTest(name=name):
                    path = root / name
                    original = path.read_bytes()
                    path.unlink()
                    with self.assertRaises(identity.IdentityError):
                        identity.verify_identity(record, firmware_root=root)
                    path.write_bytes(original + b"\n# altered\n")
                    with self.assertRaises(identity.IdentityError):
                        identity.verify_identity(record, firmware_root=root)
                    if name.startswith("Selftest_pmu_diag/"):
                        with self.assertRaises(identity.IdentityError):
                            identity.capture_identity(firmware_root=root)
                    path.write_bytes(original)

    def test_record_tampering_is_rejected(self):
        record = identity.capture_identity()
        cases = []
        for field in record:
            changed = deepcopy(record)
            changed.pop(field)
            cases.append(changed)
        changed = deepcopy(record)
        changed["files"].pop(next(iter(changed["files"])))
        cases.append(changed)
        changed = deepcopy(record)
        changed["qualification_status"] = "QUALIFIED"
        cases.append(changed)
        for changed in cases:
            with self.subTest(record=changed.keys()):
                with self.assertRaises(identity.IdentityError):
                    identity.verify_identity(changed)

    def test_loader_restores_import_state(self):
        search_path = sys.path[:]
        sentinel = object()
        with patch.dict(sys.modules, {"check_pmu_qual": sentinel}):
            v12, v13 = identity.load_frozen_helpers()
            self.assertIs(sys.modules["check_pmu_qual"], sentinel)
            self.assertEqual(Path(v12.__file__).name, "check_pmu_completion_poll_v12.py")
            self.assertEqual(Path(v13.__file__).name, "check_pmu_completion_poll_count_v13.py")
            self.assertIs(identity.load_frozen_helpers()[0], v12)
        self.assertEqual(sys.path, search_path)


if __name__ == "__main__":
    unittest.main()
