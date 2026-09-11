"""Archive byte checks must reject at the same boundary after extraction."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from host.experiments.interval import archive


class ArchiveBytes(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.json"
        self.payload = b"recorded frame"
        self.manifest = {"build_id": "fixture"}
        self.manifest_text = json.dumps(self.manifest)
        self.digest = hashlib.sha256(self.manifest_text.encode()).hexdigest()
        payload_digest = hashlib.sha256(self.payload).hexdigest()
        self.document = {
            "variant": "PMU_INTERVAL_DIAG_V9",
            "host": {"manifest_text": self.manifest_text, "manifest_sha256": self.digest},
            "manifest": self.manifest,
            "raw": {
                "payload_hex": self.payload.hex(), "payload_sha256": payload_digest,
                "reread_payload_hex": self.payload.hex(), "reread_payload_sha256": payload_digest,
                "reread_matches_run_payload": True,
            },
        }

    def read(self, document, expected_digest=None, label="V9"):
        self.path.write_text(json.dumps(document))
        return archive.read_archive(
            str(self.path), expected_variant="PMU_INTERVAL_DIAG_V9",
            expected_manifest_sha256=self.digest if expected_digest is None else expected_digest,
            frozen_label=label,
        )

    def assert_refused(self, document, message):
        with self.assertRaises(SystemExit) as caught:
            self.read(document)
        self.assertEqual(str(caught.exception), f"FAIL {self.path}: {message}")

    def test_returns_original_document_payload_and_manifest(self):
        self.assertEqual(
            self.read(self.document), (self.document, self.payload, self.manifest)
        )

    def test_variant_is_checked_before_missing_raw_data(self):
        self.assert_refused({"variant": "wrong"}, "not a PMU_INTERVAL_DIAG_V9 archive")

    def test_missing_or_nonstring_hex_is_rejected_by_its_own_check(self):
        for key in ("payload_hex", "reread_payload_hex"):
            for value in (None, 7):
                with self.subTest(key=key, value=value):
                    doc = copy.deepcopy(self.document)
                    doc["raw"][key] = value
                    self.assert_refused(doc, f"{key} missing or not a string")

    def test_malformed_hex_is_reported_without_leaking_valueerror(self):
        for key in ("payload_hex", "reread_payload_hex"):
            with self.subTest(key=key):
                doc = copy.deepcopy(self.document)
                doc["raw"][key] = "not hex"
                with self.assertRaises(SystemExit) as caught:
                    self.read(doc)
                self.assertTrue(str(caught.exception).startswith(f"FAIL {self.path}: {key} is malformed hex:"))

    def test_payload_and_reread_hashes_are_checked_independently(self):
        for key in ("payload_sha256", "reread_payload_sha256"):
            with self.subTest(key=key):
                doc = copy.deepcopy(self.document)
                doc["raw"][key] = "0" * 64
                self.assert_refused(doc, f"{key} mismatch")

    def test_reread_must_match_even_when_its_digest_is_valid(self):
        doc = copy.deepcopy(self.document)
        doc["raw"]["reread_payload_hex"] = b"another frame".hex()
        doc["raw"]["reread_payload_sha256"] = hashlib.sha256(b"another frame").hexdigest()
        self.assert_refused(doc, "archived reread does not prove equality")

    def test_reread_equality_flag_must_be_true_not_merely_truthy(self):
        for flag in (False, 1, "true", None):
            with self.subTest(flag=flag):
                doc = copy.deepcopy(self.document)
                doc["raw"]["reread_matches_run_payload"] = flag
                self.assert_refused(doc, "archived reread does not prove equality")

    def test_manifest_text_is_required(self):
        doc = copy.deepcopy(self.document)
        del doc["host"]["manifest_text"]
        self.assert_refused(doc, "manifest_text missing")

    def test_manifest_digest_is_checked_before_the_frozen_identity(self):
        doc = copy.deepcopy(self.document)
        doc["host"]["manifest_sha256"] = "0" * 64
        self.assert_refused(doc, "manifest_sha256 mismatch")

    def test_frozen_mismatch_keeps_the_version_label(self):
        for label in ("V9", "V10", "V11-A"):
            with self.subTest(label=label), self.assertRaises(SystemExit) as caught:
                self.read(self.document, "other", label)
            self.assertEqual(
                str(caught.exception),
                f"FAIL {self.path}: manifest SHA-256 {self.digest} does not match frozen {label} other",
            )

    def test_invalid_json_is_rejected_after_its_matching_digest(self):
        doc = copy.deepcopy(self.document)
        doc["host"]["manifest_text"] = "{"
        digest = hashlib.sha256(b"{").hexdigest()
        doc["host"]["manifest_sha256"] = digest
        with self.assertRaises(SystemExit) as caught:
            self.read(doc, digest)
        self.assertTrue(str(caught.exception).startswith(f"FAIL {self.path}: manifest_text is invalid JSON:"))

    def test_manifest_object_must_match_its_recorded_bytes(self):
        doc = copy.deepcopy(self.document)
        doc["manifest"]["build_id"] = "different"
        self.assert_refused(doc, "manifest bytes disagree with manifest object")


if __name__ == "__main__":
    unittest.main()
