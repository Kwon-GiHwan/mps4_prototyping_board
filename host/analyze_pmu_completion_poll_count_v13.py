"""Analyze PMU completion-poll count V13 archives.

Diagnostic-only analyzer. It never labels the observed values as latency,
T_npu, performance, production evidence, or MLEK data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import statistics

try:
    from host.runner_proto_pmu_completion_poll_count_v13 import (
        classify_pmu_completion_poll_count_v13_payload,
        parse_pmu_completion_poll_count_v13_payload,
        target_fields,
        verify_manifest_identity,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    from runner_proto_pmu_completion_poll_count_v13 import (
        classify_pmu_completion_poll_count_v13_payload,
        parse_pmu_completion_poll_count_v13_payload,
        target_fields,
        verify_manifest_identity,
    )

CAMPAIGN_BOOT_COUNT = 3
CAMPAIGN_SAMPLES_PER_BOOT = 10
CAMPAIGN_TOTAL_SAMPLES = CAMPAIGN_BOOT_COUNT * CAMPAIGN_SAMPLES_PER_BOOT
OUTPUT_LABELS = [
    "DIAGNOSTIC ONLY",
    "NOT LATENCY",
    "NOT T_npu",
    "NOT PERFORMANCE",
    "NOT PRODUCTION",
    "NOT MLEK",
]


def _decode_hex(raw_meta: dict, key: str, path: str) -> bytes:
    value = raw_meta.get(key)
    if not isinstance(value, str):
        raise ValueError("%s missing %s" % (path, key))
    return bytes.fromhex(value)


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _inclusive_quartiles(values: list[float]) -> tuple[float, float]:
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


def _mad(values: list[float]) -> float:
    med = statistics.median(values)
    return float(statistics.median([abs(v - med) for v in values]))


def _cv(values: list[float]) -> float | None:
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    if len(values) == 1:
        return 0.0
    return float(statistics.stdev(values) / mean)


def _stats(values: list[float]) -> dict:
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


def average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for pos in range(index, end):
            ranks[ordered[pos][0]] = rank
        index = end
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    if den_x == 0 or den_y == 0:
        return None
    return num / math.sqrt(den_x * den_y)


def _variance(values: list[float]) -> float:
    mean = statistics.fmean(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _covariance(xs: list[float], ys: list[float]) -> float:
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / len(xs)


def _mode_summary(values: list[int]) -> list[dict]:
    counts = Counter(values)
    top = max(counts.values())
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items())
        if count == top
    ]


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    if doc.get("variant") != "PMU_COMPLETION_POLL_COUNT_DIAG_V13":
        raise ValueError("%s is not a PMU_COMPLETION_POLL_COUNT_DIAG_V13 archive" % path)

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

    parsed = parse_pmu_completion_poll_count_v13_payload(payload)
    derived = classify_pmu_completion_poll_count_v13_payload(parsed, manifest)
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
    raw_boots = [row["host_boot_index"] for row in rows]
    if any(
        not isinstance(boot, int) or isinstance(boot, bool) or boot <= 0
        for boot in raw_boots
    ):
        errors.append("host_boot_index must be a positive integer")
        return errors
    boots = sorted(set(raw_boots))
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


def _fit_summary(
    iterations: list[int], poll_cycles: list[int]
) -> tuple[float | None, dict | None]:
    if _variance(iterations) == 0:
        return None, None
    rho = pearson(average_ranks(iterations), average_ranks(poll_cycles))
    beta = _covariance(iterations, poll_cycles) / _variance(iterations)
    alpha = statistics.fmean(poll_cycles) - (beta * statistics.fmean(iterations))
    return rho, {"alpha": alpha, "beta": beta}


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

    rows = sorted(rows, key=lambda row: (row["host_boot_index"], row["parsed"].run_sequence))
    boots = sorted({row["host_boot_index"] for row in rows})
    iterations = [row["derived"]["derived"]["poll_iterations"] for row in rows]
    poll_cycles = [row["derived"]["derived"]["poll_observation_cycles"] for row in rows]
    observed_cycles = [
        row["derived"]["derived"]["submit_to_status_completion_observed_cycles"]
        for row in rows
    ]
    ratios = [
        row["derived"]["derived"]["average_cycles_per_observed_poll"]
        for row in rows
    ]
    rho, ols_fit = _fit_summary(iterations, poll_cycles)

    residuals = []
    for row, iteration, cycle, observed, ratio in zip(
        rows, iterations, poll_cycles, observed_cycles, ratios
    ):
        residual = None
        if ols_fit is not None:
            residual = cycle - (ols_fit["alpha"] + (ols_fit["beta"] * iteration))
        residuals.append(
            {
                "host_boot_index": row["host_boot_index"],
                "run_sequence": row["parsed"].run_sequence,
                "poll_remaining_at_success": row["parsed"].poll_remaining_at_success,
                "poll_iterations": iteration,
                "poll_observation_cycles": cycle,
                "submit_to_status_completion_observed_cycles": observed,
                "average_cycles_per_observed_poll": ratio,
                "residual": residual,
            }
        )

    per_boot_residual_summary = {}
    for boot in boots:
        boot_residuals = [
            item["residual"] for item in residuals if item["host_boot_index"] == boot
        ]
        if any(value is None for value in boot_residuals):
            per_boot_residual_summary[str(boot)] = None
            continue
        residual_values = [float(value) for value in boot_residuals]
        per_boot_residual_summary[str(boot)] = {
            "count": len(residual_values),
            "min": min(residual_values),
            "max": max(residual_values),
            "mean": statistics.fmean(residual_values),
            "median": _median(residual_values),
            "rmse": math.sqrt(
                sum(value * value for value in residual_values) / len(residual_values)
            ),
        }

    hard_floor = min(poll_cycles)
    hard_floor_rows = [item for item in residuals if item["poll_observation_cycles"] == hard_floor]
    excursion_rows = [item for item in residuals if item["poll_observation_cycles"] > hard_floor]

    return {
        "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
        "labels": list(OUTPUT_LABELS),
        "diagnostic_only": True,
        "not_latency": True,
        "not_t_npu": True,
        "not_performance": True,
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
        "poll_iterations": _stats(iterations),
        "poll_observation_cycles": _stats(poll_cycles),
        "submit_to_status_completion_observed_cycles": _stats(observed_cycles),
        "average_cycles_per_observed_poll": _stats(ratios),
        "spearman_rho_iterations_vs_poll_observation_cycles": rho,
        "ols_fit_iterations_to_poll_observation_cycles": ols_fit,
        "residuals": residuals,
        "per_boot_residual_summary": per_boot_residual_summary,
        "per_boot_median_poll_observation_cycles": {
            str(boot): _median(
                [
                    row["derived"]["derived"]["poll_observation_cycles"]
                    for row in rows
                    if row["host_boot_index"] == boot
                ]
            )
            for boot in boots
        },
        "hard_floor": hard_floor,
        "hard_floor_count": len(hard_floor_rows),
        "hard_floor_distribution": {
            str(boot): sum(1 for item in hard_floor_rows if item["host_boot_index"] == boot)
            for boot in boots
        },
        "excursion_count": len(excursion_rows),
        "excursion_distribution": {
            str(boot): sum(1 for item in excursion_rows if item["host_boot_index"] == boot)
            for boot in boots
        },
        "mode_frequencies": {
            str(value): count for value, count in sorted(Counter(poll_cycles).items())
        },
        "modes": _mode_summary(poll_cycles),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", help="exactly 30 accepted V13 sample archives")
    args = parser.parse_args()
    print(json.dumps(analyze_3x10(args.archives), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
