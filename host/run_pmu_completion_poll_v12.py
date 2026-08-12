"""Collect one PMU completion-poll V12 sample.

The board-facing transport is not implemented in this local workspace yet.
This module still provides the fail-closed one-sample contract used by the
host unit suite: parse first, classify before any destination write, and abort
the campaign on timeout without persisting an invalid sample.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from host.runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        default_manifest,
        parse_pmu_completion_poll_v12_payload,
        target_fields,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    from runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        default_manifest,
        parse_pmu_completion_poll_v12_payload,
        target_fields,
    )


def _raw_payload_bytes(raw) -> bytes:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, dict):
        payload_hex = raw.get("payload_hex")
        if not isinstance(payload_hex, str):
            raise ValueError("raw payload dict has no payload_hex")
        return bytes.fromhex(payload_hex)
    raise TypeError("unsupported raw payload type %r" % (type(raw).__name__,))


def _raw_meta(payload: bytes, raw) -> dict:
    reread_hex = payload.hex()
    reread_sha = hashlib.sha256(payload).hexdigest()
    if isinstance(raw, dict):
        reread_hex = raw.get("reread_payload_hex", reread_hex)
        reread_sha = raw.get("reread_payload_sha256", reread_sha)
    return {
        "payload_hex": payload.hex(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "reread_payload_hex": reread_hex,
        "reread_payload_sha256": reread_sha,
        "reread_matches_run_payload": (
            isinstance(raw, dict)
            and raw.get("reread_matches_run_payload") is True
            and raw.get("reread_payload_hex") == payload.hex()
        )
        or not isinstance(raw, dict),
    }


def collect_one(link=None, *, raw=None, manifest=None, out_path=None, host_boot_index=1):
    if raw is None:
        if link is not None and hasattr(link, "last_payload"):
            raw = getattr(link, "last_payload")
        elif link is not None and isinstance(link, dict):
            raw = link
        else:
            raise TypeError("collect_one requires raw payload bytes or payload metadata")

    payload = _raw_payload_bytes(raw)
    manifest_doc = default_manifest() if manifest is None else manifest
    parsed = parse_pmu_completion_poll_v12_payload(payload)
    derived = classify_pmu_completion_poll_v12_payload(parsed, manifest_doc)
    raw_doc = _raw_meta(payload, raw)
    record = {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_text": json.dumps(manifest_doc, sort_keys=True),
            "manifest_sha256": hashlib.sha256(
                json.dumps(manifest_doc, sort_keys=True).encode()
            ).hexdigest(),
            "artifact_sha256": dict(manifest_doc.get("artifact_sha256", {})),
            "manifest_path": None,
        },
        "manifest": manifest_doc,
        "target": target_fields(parsed),
        "derived": derived if derived["valid"] else None,
        "raw": raw_doc,
    }
    outcome = {
        "valid": bool(derived["valid"]),
        "campaign_abort": bool(derived["campaign_abort"]),
        "fresh_boot_required": bool(derived["fresh_boot_required"]),
        "archive_write": False,
        "derived": record["derived"],
        "record": record,
    }
    if not derived["valid"]:
        return outcome
    if out_path is not None:
        out = Path(out_path)
        with out.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        outcome["archive_write"] = True
    return outcome
