"""Analyze PMU completion-poll V12 archives.

Diagnostic-only analyzer. It never labels the observed values as latency,
T_npu, production evidence, or MLEK data.
"""

from __future__ import annotations

import hashlib
import json
import statistics

try:
    from host.runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    from runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
    )


def _decode_hex(raw_meta: dict, key: str, path: str) -> bytes:
    value = raw_meta.get(key)
    if not isinstance(value, str):
        raise ValueError("%s missing %s" % (path, key))
    return bytes.fromhex(value)


def _median(values: list[int]) -> float:
    return float(statistics.median(values))


def _inclusive_quartiles(values: list[int]) -> tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        one = float(ordered[0])
        return one, one
    mid = n // 2
    if n % 2:
        lower = ordered[: mid + 1]
        upper = ordered[mid:]
    else:
        lower = ordered[:mid]
        upper = ordered[mid:]
    return float(statistics.median(lower)), float(statistics.median(upper))


def _mad(values: list[int]) -> float:
    med = statistics.median(values)
    return float(statistics.median([abs(v - med) for v in values]))


def _cv(values: list[int]) -> float | None:
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    if len(values) == 1:
        return 0.0
    return float(statistics.stdev(values) / mean)


def _stats(values: list[int]) -> dict:
    q1, q3 = _inclusive_quartiles(values)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "median": _median(values),
        "mad": _mad(values),
        "q1_inclusive": q1,
        "q3_inclusive": q3,
        "iqr_inclusive": q3 - q1,
        "cv": _cv(values),
    }


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    raw_meta = doc.get("raw") or {}
    payload = _decode_hex(raw_meta, "payload_hex", path)
    reread = _decode_hex(raw_meta, "reread_payload_hex", path)
    if hashlib.sha256(payload).hexdigest() != raw_meta.get("payload_sha256"):
        raise ValueError("%s payload_sha256 mismatch" % path)
    if hashlib.sha256(reread).hexdigest() != raw_meta.get("reread_payload_sha256"):
        raise ValueError("%s reread_payload_sha256 mismatch" % path)
    manifest = doc.get("manifest") or json.loads(doc["host"]["manifest_text"])
    parsed = parse_pmu_completion_poll_v12_payload(payload)
    derived = classify_pmu_completion_poll_v12_payload(parsed, manifest)
    return {
        "path": path,
        "host_boot_index": doc.get("host", {}).get("host_boot_index"),
        "manifest": manifest,
        "parsed": parsed,
        "derived": derived,
    }


def analyze_3x10(paths: list[str]) -> dict:
    rows = [_load(path) for path in sorted(paths)]
    sample_count = len(rows)
    invalid_rows = [row for row in rows if not row["derived"]["valid"]]
    result = {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "diagnostic_only": True,
        "not_numerically_comparable_to_v11a": True,
        "not_latency": True,
        "not_t_npu": True,
        "not_production": True,
        "not_mlek": True,
        "sample_count": sample_count,
        "total_samples": sample_count,
        "count": sample_count,
        "campaign_valid": not invalid_rows,
        "invalid_sample_count": len(invalid_rows),
        "fresh_boot_required": any(row["derived"]["fresh_boot_required"] for row in rows),
        "campaign_abort": any(row["derived"]["campaign_abort"] for row in rows),
    }
    if invalid_rows:
        result["invalid_paths"] = [row["path"] for row in invalid_rows]
        return result

    boots = sorted({row["host_boot_index"] for row in rows})
    values = [
        row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
        for row in rows
    ]
    result.update(
        {
            "boot_count": len(boots),
            "boots": boots,
            "submit_to_status_completion_observed_cycles": _stats(values),
            "per_boot_median": {
                str(boot): _median(
                    [
                        row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
                        for row in rows
                        if row["host_boot_index"] == boot
                    ]
                )
                for boot in boots
            },
            "hard_floor": min(values),
            "hard_floor_count": sum(1 for value in values if value == min(values)),
            "excursion_count": sum(1 for value in values if value > min(values)),
        }
    )
    return result
