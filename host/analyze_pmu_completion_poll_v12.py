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
        target_fields,
        verify_manifest_identity,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    from runner_proto_pmu_completion_poll_v12 import (
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
        target_fields,
        verify_manifest_identity,
    )

CAMPAIGN_BOOT_COUNT = 3
CAMPAIGN_SAMPLES_PER_BOOT = 10
CAMPAIGN_TOTAL_SAMPLES = CAMPAIGN_BOOT_COUNT * CAMPAIGN_SAMPLES_PER_BOOT
OUTPUT_LABELS = [
    "DIAGNOSTIC ONLY",
    "NOT NUMERICALLY COMPARABLE TO V11-A",
    "NOT LATENCY",
    "NOT T_npu",
    "NOT PRODUCTION",
    "NOT MLEK",
]


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


def load(path: str) -> dict:
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

    host = doc.get("host") or {}
    manifest_text = host.get("manifest_text")
    if not isinstance(manifest_text, str):
        raise ValueError("%s host manifest_text missing" % path)
    manifest_sha = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    if manifest_sha != host.get("manifest_sha256"):
        raise ValueError("%s host manifest_sha256 mismatch" % path)
    manifest = json.loads(manifest_text)
    if doc.get("manifest") != manifest:
        raise ValueError("%s manifest object differs from manifest_text" % path)
    verify_manifest_identity(manifest, path)
    if host.get("artifact_sha256") != manifest.get("artifact_sha256"):
        raise ValueError("%s host artifact_sha256 mismatch" % path)

    parsed = parse_pmu_completion_poll_v12_payload(payload)
    derived = classify_pmu_completion_poll_v12_payload(parsed, manifest)
    if doc.get("target") != target_fields(parsed):
        raise ValueError("%s archived target disagrees with raw payload" % path)
    if doc.get("derived") != (derived if derived["valid"] else None):
        raise ValueError("%s archived derived block disagrees with re-derivation" % path)

    return {
        "path": path,
        "host_boot_index": host.get("host_boot_index"),
        "manifest": manifest,
        "manifest_identity": manifest_text,
        "artifact_identity": json.dumps(manifest["artifact_sha256"], sort_keys=True),
        "parsed": parsed,
        "derived": derived,
    }


def _shape_errors(rows: list[dict]) -> list[str]:
    errors = []
    if len(rows) != CAMPAIGN_TOTAL_SAMPLES:
        errors.append("sample_count != %d" % CAMPAIGN_TOTAL_SAMPLES)
    boots = sorted({row["host_boot_index"] for row in rows})
    if any(not isinstance(boot, int) or isinstance(boot, bool) or boot <= 0 for boot in boots):
        errors.append("host_boot_index must be a positive integer")
        return errors
    if len(boots) != CAMPAIGN_BOOT_COUNT:
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
                "boot %s run_sequence != 1..%d" % (boot, CAMPAIGN_SAMPLES_PER_BOOT)
            )
    return errors


def _mode_summary(values: list[int]) -> list[dict]:
    counts = Counter(values)
    top = max(counts.values())
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items())
        if count == top
    ]


def analyze_3x10(paths: list[str]) -> dict:
    rows = [load(path) for path in sorted(paths)]
    invalid_rows = [row for row in rows if not row["derived"]["valid"]]
    if invalid_rows:
        raise ValueError(
            "campaign contains invalid sample(s): %s"
            % ", ".join(row["path"] for row in invalid_rows)
        )
    shape_errors = _shape_errors(rows)
    if shape_errors:
        raise ValueError("; ".join(shape_errors))
    if len({row["manifest_identity"] for row in rows}) != 1:
        raise ValueError("manifest_identity drift")
    if len({row["artifact_identity"] for row in rows}) != 1:
        raise ValueError("artifact_identity drift")

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
    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "labels": list(OUTPUT_LABELS),
        "diagnostic_only": True,
        "not_numerically_comparable_to_v11a": True,
        "not_latency": True,
        "not_t_npu": True,
        "not_production": True,
        "not_mlek": True,
        "campaign_valid": True,
        "sample_count": len(rows),
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
