"""Read interval archive bytes before version-specific semantic validation.

Checks preserve the original rejection order and messages. A returned manifest
has matching recorded bytes and digest; callers must still validate its fields,
artifact identities, decoded target and derived values.
"""

from __future__ import annotations

import hashlib
import json


def _decode_hex(raw_meta: dict, key: str, path: str) -> bytes:
    value = raw_meta.get(key)
    if not isinstance(value, str):
        raise SystemExit("FAIL %s: %s missing or not a string" % (path, key))
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise SystemExit("FAIL %s: %s is malformed hex: %s" % (path, key, exc))


def read_archive(
    path: str,
    *,
    expected_variant: str,
    expected_manifest_sha256: str,
    frozen_label: str,
) -> tuple[dict, bytes, dict]:
    with open(path) as handle:
        doc = json.load(handle)
    if doc.get("variant") != expected_variant:
        raise SystemExit("FAIL %s: not a %s archive" % (path, expected_variant))
    host = doc.get("host") or {}
    raw_meta = doc.get("raw") or {}
    raw = _decode_hex(raw_meta, "payload_hex", path)
    reread = _decode_hex(raw_meta, "reread_payload_hex", path)
    if hashlib.sha256(raw).hexdigest() != raw_meta.get("payload_sha256"):
        raise SystemExit("FAIL %s: payload_sha256 mismatch" % path)
    if hashlib.sha256(reread).hexdigest() != raw_meta.get("reread_payload_sha256"):
        raise SystemExit("FAIL %s: reread_payload_sha256 mismatch" % path)
    if reread != raw or raw_meta.get("reread_matches_run_payload") is not True:
        raise SystemExit("FAIL %s: archived reread does not prove equality" % path)
    manifest_text = host.get("manifest_text")
    if not isinstance(manifest_text, str):
        raise SystemExit("FAIL %s: manifest_text missing" % path)
    observed_manifest_sha256 = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    if observed_manifest_sha256 != host.get("manifest_sha256"):
        raise SystemExit("FAIL %s: manifest_sha256 mismatch" % path)
    if observed_manifest_sha256 != expected_manifest_sha256:
        raise SystemExit(
            "FAIL %s: manifest SHA-256 %s does not match frozen %s %s"
            % (path, observed_manifest_sha256, frozen_label, expected_manifest_sha256))
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise SystemExit("FAIL %s: manifest_text is invalid JSON: %s" % (path, exc))
    if doc.get("manifest") != manifest:
        raise SystemExit("FAIL %s: manifest bytes disagree with manifest object" % path)
    return doc, raw, manifest
