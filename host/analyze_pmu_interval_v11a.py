"""Re-derive PMU_INTERVAL_ENTRY_DIAG_V11A archives.

Supports both:
  - one archived sample
  - one 30-sample campaign: exactly 3 distinct boots x 10 valid runs each

CHARACTERIZATION ONLY. Nothing emitted here is latency, T_npu, performance,
Production evidence, or MLEK data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics

from runner_proto_pmu_interval_v11a import (
    PMU_INTERVAL_ANALYZER_PROHIBITED_CLAIMS,
    PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256,
    classify_pmu_interval_diag_v11a,
    parse_pmu_interval_diag_v11a_payload,
    target_fields,
    verify_manifest_identity,
)

CAMPAIGN_BOOT_COUNT = 3
CAMPAIGN_SAMPLES_PER_BOOT = 10
CAMPAIGN_TOTAL_SAMPLES = CAMPAIGN_BOOT_COUNT * CAMPAIGN_SAMPLES_PER_BOOT
REPORT_INTERVALS = ("A0", "A1", "A2", "D23")
LOCALIZATION_INTERVALS = ("A0", "A1", "A2")
PRIMARY_WINDOW = "v11a_perturbed_window_cycles"


def _decode_hex(raw_meta: dict, key: str, path: str) -> bytes:
    value = raw_meta.get(key)
    if not isinstance(value, str):
        raise SystemExit("FAIL %s: %s missing or not a string" % (path, key))
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise SystemExit("FAIL %s: %s is malformed hex: %s" % (path, key, exc))


def load(
    path: str,
    expected_manifest_sha256: str = PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256,
) -> tuple[object, dict]:
    with open(path) as handle:
        doc = json.load(handle)
    if doc.get("variant") != "PMU_INTERVAL_ENTRY_DIAG_V11A":
        raise SystemExit("FAIL %s: not a PMU_INTERVAL_ENTRY_DIAG_V11A archive" % path)
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
            "FAIL %s: manifest SHA-256 %s does not match frozen V11-A %s"
            % (path, observed_manifest_sha256, expected_manifest_sha256)
        )
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise SystemExit("FAIL %s: manifest_text is invalid JSON: %s" % (path, exc))
    if doc.get("manifest") != manifest:
        raise SystemExit("FAIL %s: manifest bytes disagree with manifest object" % path)
    verify_manifest_identity(manifest, path)
    if host.get("artifact_sha256") != manifest.get("artifact_sha256"):
        raise SystemExit("FAIL %s: archived artifact hashes disagree with manifest" % path)
    res = parse_pmu_interval_diag_v11a_payload(raw)
    derived = classify_pmu_interval_diag_v11a(res, manifest)
    if doc.get("target") != target_fields(res):
        raise SystemExit("FAIL %s: archived target disagrees with raw payload" % path)
    if doc.get("derived") != derived:
        raise SystemExit("FAIL %s: archived derived block disagrees with re-derivation" % path)
    return res, doc


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


def _series_stats(values: list[int]) -> dict:
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


def _campaign_rows(paths: list[str], expected_manifest_sha256: str) -> list[dict]:
    rows = []
    for path in sorted(paths):
        res, doc = load(path, expected_manifest_sha256)
        derived = classify_pmu_interval_diag_v11a(res, doc["manifest"])
        if not derived["valid"]:
            raise SystemExit("FAIL %s: campaign sample is invalid" % path)
        boot = doc.get("host", {}).get("host_boot_index")
        if not isinstance(boot, int) or isinstance(boot, bool) or boot <= 0:
            raise SystemExit("FAIL %s: host_boot_index must be a positive integer" % path)
        rows.append(
            {
                "path": path,
                "boot": boot,
                "run_sequence": res.run_sequence,
                "manifest": doc["manifest"],
                "target": doc["target"],
                "derived": derived,
            }
        )
    return rows


def summarize_campaign(
    paths: list[str],
    expected_manifest_sha256: str = PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256,
) -> dict:
    rows = _campaign_rows(paths, expected_manifest_sha256)
    if len(rows) != CAMPAIGN_TOTAL_SAMPLES:
        raise SystemExit(
            "FAIL campaign has %d samples, expected exactly %d"
            % (len(rows), CAMPAIGN_TOTAL_SAMPLES)
        )

    boots = sorted({row["boot"] for row in rows})
    if len(boots) != CAMPAIGN_BOOT_COUNT:
        raise SystemExit(
            "FAIL campaign has %d distinct boots, expected %d"
            % (len(boots), CAMPAIGN_BOOT_COUNT)
        )

    first_manifest = json.dumps(rows[0]["manifest"], sort_keys=True)
    first_artifacts = json.dumps(rows[0]["manifest"]["artifact_sha256"], sort_keys=True)
    first_lr = rows[0]["manifest"]["expected_return_address"]
    first_build = rows[0]["manifest"]["build_id"]
    boot_rows = {}
    for boot in boots:
        boot_rows[boot] = sorted(
            [row for row in rows if row["boot"] == boot],
            key=lambda row: row["run_sequence"],
        )
        if len(boot_rows[boot]) != CAMPAIGN_SAMPLES_PER_BOOT:
            raise SystemExit(
                "FAIL boot %d has %d samples, expected %d"
                % (boot, len(boot_rows[boot]), CAMPAIGN_SAMPLES_PER_BOOT)
            )
        want_seq = list(range(1, CAMPAIGN_SAMPLES_PER_BOOT + 1))
        got_seq = [row["run_sequence"] for row in boot_rows[boot]]
        if got_seq != want_seq:
            raise SystemExit(
                "FAIL boot %d run_sequence %s, expected %s" % (boot, got_seq, want_seq)
            )
        for row in boot_rows[boot]:
            if json.dumps(row["manifest"], sort_keys=True) != first_manifest:
                raise SystemExit(
                    "FAIL %s: manifest differs from the frozen campaign identity"
                    % row["path"]
                )
            if json.dumps(row["manifest"]["artifact_sha256"], sort_keys=True) != first_artifacts:
                raise SystemExit(
                    "FAIL %s: artifact hashes differ from the frozen campaign identity"
                    % row["path"]
                )
            if row["manifest"]["expected_return_address"] != first_lr:
                raise SystemExit(
                    "FAIL %s: expected_return_address differs from the frozen campaign identity"
                    % row["path"]
                )

    for row in rows[1:]:
        if row["manifest"]["build_id"] != first_build:
            raise SystemExit("FAIL %s: build_id differs inside the campaign" % row["path"])
        if any(name not in row["derived"]["deltas_u32"] for name in REPORT_INTERVALS):
            raise SystemExit("FAIL %s: adjacent interval keys are incomplete" % row["path"])

    overall = {
        name: _series_stats([row["derived"]["deltas_u32"][name] for row in rows])
        for name in REPORT_INTERVALS
    }
    per_boot = {
        str(boot): {
            name: _series_stats([row["derived"]["deltas_u32"][name] for row in boot_rows[boot]])
            for name in REPORT_INTERVALS
        }
        for boot in boots
    }

    window_values = [row["derived"][PRIMARY_WINDOW] for row in rows]
    if any(value is None for value in window_values):
        raise SystemExit("FAIL campaign contains an unpublished V11-A window value")
    floor_value = min(window_values)
    floor_rows = [row for row in rows if row["derived"][PRIMARY_WINDOW] == floor_value]
    excursion_rows = [row for row in rows if row["derived"][PRIMARY_WINDOW] > floor_value]
    floor_ranges = {
        name: (
            min(row["derived"]["deltas_u32"][name] for row in floor_rows),
            max(row["derived"]["deltas_u32"][name] for row in floor_rows),
        )
        for name in LOCALIZATION_INTERVALS
    }
    earliest_counts = {name: 0 for name in LOCALIZATION_INTERVALS}
    unresolved = []
    for row in excursion_rows:
        earliest = None
        for name in LOCALIZATION_INTERVALS:
            value = row["derived"]["deltas_u32"][name]
            low, high = floor_ranges[name]
            if value < low or value > high:
                earliest = name
                earliest_counts[name] += 1
                break
        if earliest is None:
            unresolved.append(os.path.basename(row["path"]))

    if len(floor_rows) < 2:
        floor_excursion = {
            "primary_window": PRIMARY_WINDOW,
            "observed_floor": floor_value,
            "floor_sample_count": len(floor_rows),
            "excursion_sample_count": len(excursion_rows),
            "status": "unresolved_floor_group_shortage",
            "earliest_interval_counts": earliest_counts,
            "unresolved_samples": unresolved,
        }
    elif not excursion_rows:
        floor_excursion = {
            "primary_window": PRIMARY_WINDOW,
            "observed_floor": floor_value,
            "floor_sample_count": len(floor_rows),
            "excursion_sample_count": 0,
            "status": "unresolved_no_excursion",
            "earliest_interval_counts": earliest_counts,
            "unresolved_samples": [],
        }
    else:
        floor_excursion = {
            "primary_window": PRIMARY_WINDOW,
            "observed_floor": floor_value,
            "floor_sample_count": len(floor_rows),
            "excursion_sample_count": len(excursion_rows),
            "status": (
                "resolved" if len(unresolved) == 0 else "unresolved_excursion_within_floor_ranges"
            ),
            "earliest_interval_counts": {
                name: count for name, count in earliest_counts.items() if count
            },
            "unresolved_samples": unresolved,
        }

    return {
        "variant": "PMU_INTERVAL_ENTRY_DIAG_V11A",
        "characterization_only": True,
        "not_latency": True,
        "not_performance": True,
        "not_production": True,
        "not_mlek": True,
        "sample_count": len(rows),
        "boot_count": len(boots),
        "build_id": first_build,
        "expected_return_address": first_lr,
        "boots": boots,
        "per_boot_run_sequences": {
            str(boot): [row["run_sequence"] for row in boot_rows[boot]] for boot in boots
        },
        "delta_stats": overall,
        "v11a_perturbed_window_stats": _series_stats(window_values),
        "per_boot_delta_stats": per_boot,
        "floor_excursion": floor_excursion,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="+")
    args = ap.parse_args()
    print("characterization_only: true")
    print("prohibited_claims: %s" % ", ".join(PMU_INTERVAL_ANALYZER_PROHIBITED_CLAIMS))
    print("not_latency_or_performance_or_production_or_mlek: true")
    if len(args.path) == 1:
        res, doc = load(args.path[0])
        derived = classify_pmu_interval_diag_v11a(res, doc["manifest"])
        print("variant: PMU_INTERVAL_ENTRY_DIAG_V11A")
        print("build_id: 0x%08X" % res.build_id)
        print("checkpoints: %s" % json.dumps(derived["checkpoints"], sort_keys=True))
        print("deltas_u32: %s" % json.dumps(derived["deltas_u32"], sort_keys=True))
        print("j0_label: %s" % derived["j0_label"])
        print("a0_label: %s" % derived["a0_label"])
        print("a1_label: %s" % derived["a1_label"])
        print("a2_label: %s" % derived["a2_label"])
        print("t4_t5_label: %s" % derived["t4_t5_label"])
        print("valid: %s" % ("true" if derived["valid"] else "false"))
        return 0 if derived["valid"] else 1

    report = summarize_campaign(args.path)
    print("variant: PMU_INTERVAL_ENTRY_DIAG_V11A")
    print("campaign_sample_count: %d" % report["sample_count"])
    print("campaign_boot_count: %d" % report["boot_count"])
    print("boots: %s" % json.dumps(report["boots"]))
    print(
        "primary_window_floor_excursion: %s"
        % json.dumps(report["floor_excursion"], sort_keys=True)
    )
    print("delta_stats: %s" % json.dumps(report["delta_stats"], sort_keys=True))
    print("per_boot_delta_stats: %s" % json.dumps(report["per_boot_delta_stats"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
