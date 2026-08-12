"""Analyze PMU completion-poll V12 archives.

Diagnostic-only analyzer. It never labels the observed values as latency,
T_npu, production evidence, or MLEK data.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import statistics

try:
    from host.runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
        verify_manifest_identity,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    from runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
        verify_manifest_identity,
    )

CAMPAIGN_BOOT_COUNT = 3
CAMPAIGN_SAMPLES_PER_BOOT = 10
CAMPAIGN_TOTAL_SAMPLES = CAMPAIGN_BOOT_COUNT * CAMPAIGN_SAMPLES_PER_BOOT


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
    if doc.get("variant") != "PMU_COMPLETION_POLL_DIAG_V12":
        raise ValueError("%s is not a PMU_COMPLETION_POLL_DIAG_V12 archive" % path)
    raw_meta = doc.get("raw") or {}
    payload = _decode_hex(raw_meta, "payload_hex", path)
    reread = _decode_hex(raw_meta, "reread_payload_hex", path)
    if hashlib.sha256(payload).hexdigest() != raw_meta.get("payload_sha256"):
        raise ValueError("%s payload_sha256 mismatch" % path)
    if hashlib.sha256(reread).hexdigest() != raw_meta.get("reread_payload_sha256"):
        raise ValueError("%s reread_payload_sha256 mismatch" % path)
    if reread != payload or raw_meta.get("reread_matches_run_payload") is not True:
        raise ValueError("%s archived reread does not prove equality" % path)
    manifest = doc.get("manifest") or json.loads(doc["host"]["manifest_text"])
    host_meta = doc.get("host") or {}
    manifest_text = host_meta.get("manifest_text")
    manifest_sha256 = host_meta.get("manifest_sha256")
    if isinstance(manifest_text, str):
        canonical = json.dumps(manifest, sort_keys=True)
        if manifest_text != canonical:
            raise ValueError("%s host manifest_text mismatch" % path)
        if manifest_sha256 != hashlib.sha256(canonical.encode()).hexdigest():
            raise ValueError("%s host manifest_sha256 mismatch" % path)
    host_artifact_sha256 = host_meta.get("artifact_sha256")
    if host_artifact_sha256 is not None:
        if host_artifact_sha256 != manifest.get("artifact_sha256"):
            raise ValueError("%s host artifact_sha256 mismatch" % path)
    try:
        verify_manifest_identity(manifest, path)
    except SystemExit as exc:
        raise ValueError(str(exc)) from None
    parsed = parse_pmu_completion_poll_v12_payload(payload)
    derived = classify_pmu_completion_poll_v12_payload(parsed, manifest)
    return {
        "path": path,
        "host_boot_index": host_meta.get("host_boot_index"),
        "manifest": manifest,
        "manifest_identity": json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        "parsed": parsed,
        "derived": derived,
    }


def _shape_errors(rows: list[dict]) -> list[str]:
    errors = []
    if len(rows) != CAMPAIGN_TOTAL_SAMPLES:
        errors.append("sample_count != %d" % CAMPAIGN_TOTAL_SAMPLES)
    if any(
        not isinstance(row["host_boot_index"], int)
        or isinstance(row["host_boot_index"], bool)
        or row["host_boot_index"] <= 0
        for row in rows
    ):
        errors.append("host_boot_index must be a positive integer")
        return errors
    boots = sorted({row["host_boot_index"] for row in rows})
    if len(boots) != CAMPAIGN_BOOT_COUNT or any(boot is None for boot in boots):
        errors.append("boot_count != %d" % CAMPAIGN_BOOT_COUNT)
        return errors
    for boot in boots:
        sequences = sorted(
            row["parsed"].run_sequence for row in rows if row["host_boot_index"] == boot
        )
        if len(sequences) != CAMPAIGN_SAMPLES_PER_BOOT:
            errors.append(
                "boot %s sample_count != %d" % (boot, CAMPAIGN_SAMPLES_PER_BOOT)
            )
            continue
        if sequences != list(range(1, CAMPAIGN_SAMPLES_PER_BOOT + 1)):
            errors.append(
                "boot %s run_sequence != 1..%d"
                % (boot, CAMPAIGN_SAMPLES_PER_BOOT)
            )
    return errors


def _identity_errors(rows: list[dict]) -> list[str]:
    errors = []
    if len({row["manifest_identity"] for row in rows}) != 1:
        errors.append("manifest_identity drift")
    return errors


def _mode_summary(values: list[int]) -> list[dict]:
    counts = Counter(values)
    if not counts:
        return []
    top = max(counts.values())
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items())
        if count == top
    ]


def analyze_3x10(paths: list[str]) -> dict:
    rows = [_load(path) for path in sorted(paths)]
    sample_count = len(rows)
    invalid_rows = [row for row in rows if not row["derived"]["valid"]]
    shape_errors = _shape_errors(rows)
    identity_errors = _identity_errors(rows)
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
        "campaign_valid": not invalid_rows and not shape_errors and not identity_errors,
        "invalid_sample_count": len(invalid_rows),
        "fresh_boot_required": any(row["derived"]["fresh_boot_required"] for row in rows),
        "campaign_abort": any(row["derived"]["campaign_abort"] for row in rows),
    }
    if invalid_rows:
        raise ValueError(
            "campaign contains invalid sample(s): %s"
            % ", ".join(row["path"] for row in invalid_rows)
        )
    if shape_errors:
        raise ValueError("; ".join(shape_errors))
    if identity_errors:
        raise ValueError("; ".join(identity_errors))

    boots = sorted({row["host_boot_index"] for row in rows})
    values = [
        row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
        for row in rows
    ]
    per_boot_median = {
        str(boot): _median(
            [
                row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
                for row in rows
                if row["host_boot_index"] == boot
            ]
        )
        for boot in boots
    }
    within_boot_cv = {
        str(boot): _cv(
            [
                row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
                for row in rows
                if row["host_boot_index"] == boot
            ]
        )
        for boot in boots
    }
    result.update(
        {
            "boot_count": len(boots),
            "boots": boots,
            "per_boot_run_count": {
                str(boot): sum(1 for row in rows if row["host_boot_index"] == boot)
                for boot in boots
            },
            "submit_to_status_completion_observed_cycles": _stats(values),
            "per_boot_median": per_boot_median,
            "within_boot_cv": within_boot_cv,
            "between_boot_spread": max(per_boot_median.values()) - min(per_boot_median.values()),
            "mode_frequencies": {str(value): count for value, count in sorted(Counter(values).items())},
            "modes": _mode_summary(values),
            "hard_floor": min(values),
            "hard_floor_count": sum(1 for value in values if value == min(values)),
            "excursion_count": sum(1 for value in values if value > min(values)),
        }
    )
    return result
