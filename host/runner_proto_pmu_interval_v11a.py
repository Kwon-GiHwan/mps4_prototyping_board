"""Schema-v11 PMU interval characterization protocol helpers.

This is a separate host path on purpose. Earlier parsers must continue to
reject a v11a payload.
"""

from __future__ import annotations

import re
import struct
from dataclasses import asdict, dataclass

import runner_proto as v8

PMU_INTERVAL_ENTRY_DIAG_V11A_NAME = "PMU_INTERVAL_ENTRY_DIAG_V11A"
PMU_INTERVAL_ENTRY_DIAG_V11A_MAGIC = v8.PMU_QUAL_MAGIC
PMU_INTERVAL_ENTRY_DIAG_V11A_SCHEMA_VERSION = 11
PMU_INTERVAL_ENTRY_DIAG_V11A_HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS
PMU_INTERVAL_ENTRY_DIAG_V11A_BASE_FIELDS = v8.PMU_QUAL_KNOWN_FIELDS
PMU_INTERVAL_ENTRY_DIAG_V11A_EXTRA_FIELDS = 7
PMU_INTERVAL_ENTRY_DIAG_V11A_KNOWN_FIELDS = (
    PMU_INTERVAL_ENTRY_DIAG_V11A_BASE_FIELDS
    + PMU_INTERVAL_ENTRY_DIAG_V11A_EXTRA_FIELDS
)
PMU_INTERVAL_ENTRY_DIAG_V11A_TOTAL_WORDS = (
    PMU_INTERVAL_ENTRY_DIAG_V11A_HEADER_WORDS
    + PMU_INTERVAL_ENTRY_DIAG_V11A_KNOWN_FIELDS
)
PMU_INTERVAL_ENTRY_DIAG_V11A_PAYLOAD_SIZE = (
    PMU_INTERVAL_ENTRY_DIAG_V11A_TOTAL_WORDS * 4
)
PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID = 0x41314950  # ASCII "PI1A", little-endian.
PMU_INTERVAL_V11A_EXPECTED_PMU_MMIO_READS = 58
PMU_INTERVAL_V11A_EXPECTED_PMU_MMIO_WRITES = 8
PMU_INTERVAL_V11A_EXPECTED_HOOK_PMU_MMIO_READS = 16
PMU_INTERVAL_V11A_EXPECTED_HOOK_PMU_MMIO_WRITES = 1
PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256 = (
    "713c1f50cd30e3397db4f715895ec9f4b74f88f6f4e5bd1040a43f7d4f0e5f67"
)
PMU_INTERVAL_V11A_FROZEN_ARTIFACT_SHA256 = {
    "APP.BIN": "92e81e5ac51ed56c89eb3cc447ef421334142ec9a2a941990995025d546b00b9",
    "VECTORS.BIN": "1b86143c1bf9ba06263ffe1744b41f57b79f5d50f9db67bd9fc0eac33b67c81f",
    "DDR.BIN": "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
}
PMU_INTERVAL_V11A_FROZEN_BUILD_EVIDENCE_SHA256 = {
    "runner_pmu_interval_v11a.elf": "28d93dfe113cff6fb86595411d4c5d4a1dbb1d0f77c4f5b8159777084ff57c93",
    "runner_pmu_interval_v11a.map": "c112826b4d1fa8ba6b7a04df98ba99b1b7e1d65d70d0cdb0f36f442c70fe95f4",
    "generated_runner.c": "f426b6e5c1a7ae5b1d6a78efdf39c02dbebfe0fef6effc5b314b6f3503314d55",
    "generated_vendor_u85.c": "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf",
}
PMU_INTERVAL_REQUIRED_MANIFEST_KEYS = (
    "variant",
    "schema_version",
    "build_id",
    "qualification_mode",
    "expected_return_address",
    "characterization_only",
    "not_a_performance_baseline",
    "not_a_latency_measurement",
    "busy_poll_interval_only",
    "d23_split_only",
    "post_t3_handoff_out_of_scope",
    "verify_output_stays_enabled",
    "generated_private_driver_diagnostic_only",
    "production_end_only_frozen",
    "mlek_performance_not_started",
    "j0_first_veneer_probe_only",
    "v11a_perturbed_window_only",
    "artifact_sha256",
    "build_evidence_sha256",
)
PMU_INTERVAL_ANALYZER_PROHIBITED_CLAIMS = (
    "latency",
    "T_npu",
    "performance",
    "Gate7",
    "MLEK",
    "Production",
)


@dataclass(frozen=True)
class PmuIntervalDiagV11AResult:
    base: v8.PmuQualResult
    header_words: int
    body_words: int
    t_submit_before_cmd: int
    t_submit_after_cmd: int
    t_vector_probe: int
    t_isr_entry: int
    t_irq_status_seen: int
    i0_hit_count: int
    t3_hit_count: int
    trailing_words: int

    def __getattr__(self, name):
        if name == "base":
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "base"), name)

    def checkpoints(self) -> dict[str, int]:
        return {
            "T0": self.t_call_enter,
            "T1": self.t_submit_before_cmd,
            "T2": self.t_submit_after_cmd,
            "J0": self.t_vector_probe,
            "I0": self.t_isr_entry,
            "T3": self.t_irq_status_seen,
            "T4": self.hook_entry_timestamp,
            "T5": self.t_call_return,
        }


def target_fields(res: PmuIntervalDiagV11AResult) -> dict:
    doc = asdict(res.base)
    doc.update(
        {
            "t_submit_before_cmd": res.t_submit_before_cmd,
            "t_submit_after_cmd": res.t_submit_after_cmd,
            "t_vector_probe": res.t_vector_probe,
            "t_isr_entry": res.t_isr_entry,
            "t_irq_status_seen": res.t_irq_status_seen,
            "i0_hit_count": res.i0_hit_count,
            "t3_hit_count": res.t3_hit_count,
            "v11a_trailing_words": res.trailing_words,
        }
    )
    return doc


def _manifest_build_id(doc: dict) -> int | None:
    value = doc.get("build_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def parse_pmu_interval_diag_v11a_payload(payload: bytes) -> PmuIntervalDiagV11AResult:
    if len(payload) < PMU_INTERVAL_ENTRY_DIAG_V11A_HEADER_WORDS * 4:
        raise v8.ProtocolError("v11a payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_INTERVAL_ENTRY_DIAG_V11A_MAGIC:
        raise v8.ProtocolError(
            "bad PMU_INTERVAL_ENTRY_DIAG_V11A magic 0x%08X" % magic
        )
    if version != PMU_INTERVAL_ENTRY_DIAG_V11A_SCHEMA_VERSION:
        raise v8.ProtocolError(
            "unsupported PMU_INTERVAL_ENTRY_DIAG_V11A schema version %d" % version
        )
    if header_words != PMU_INTERVAL_ENTRY_DIAG_V11A_HEADER_WORDS:
        raise v8.ProtocolError(
            "unexpected PMU_INTERVAL_ENTRY_DIAG_V11A header_words %d" % header_words
        )
    if total_words != PMU_INTERVAL_ENTRY_DIAG_V11A_TOTAL_WORDS:
        raise v8.ProtocolError(
            "total_payload_words %d does not equal the v11a contract %d"
            % (total_words, PMU_INTERVAL_ENTRY_DIAG_V11A_TOTAL_WORDS)
        )
    if total_words * 4 != len(payload):
        raise v8.ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload))
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise v8.ProtocolError("PMU_INTERVAL_ENTRY_DIAG_V11A payload CRC mismatch")

    body = struct.unpack_from(
        "<%dI" % (total_words - header_words), payload, header_words * 4
    )
    scalars = v8.PMU_QUAL_BASE_FIELDS + v8.PMU_QUAL_HOOK_FIELDS
    snaps = []
    for n in range(v8.PMU_QUAL_SNAPSHOT_COUNT):
        base = scalars + n * v8.PMU_QUAL_SNAPSHOT_WORDS
        snaps.append(v8.PmuDiagSnapshot(*body[base:base + v8.PMU_QUAL_SNAPSHOT_WORDS]))

    extra_base = v8.PMU_QUAL_KNOWN_FIELDS
    res = v8.PmuQualResult(
        *body[:v8.PMU_QUAL_BASE_FIELDS],
        *body[v8.PMU_QUAL_BASE_FIELDS:scalars],
        pre=snaps[0],
        internal_pre_release=snaps[1],
        internal_post_disable=snaps[2],
        after_return=snaps[3],
        trailing_words=len(body) - PMU_INTERVAL_ENTRY_DIAG_V11A_KNOWN_FIELDS,
    )
    if (seq, flags, rc) != (res.run_sequence, res.valid_flags, res.run_rc):
        raise v8.ProtocolError(
            "PMU_INTERVAL_ENTRY_DIAG_V11A header/body disagree on seq/flags/rc"
        )
    if res.schema_version != version:
        raise v8.ProtocolError(
            "PMU_INTERVAL_ENTRY_DIAG_V11A body schema_version %d != header %d"
            % (res.schema_version, version)
        )
    if (
        res.power_seam_id,
        res.power_rehold_performed,
        res.rehold_guard_cycles,
    ) != (v8.PMU_QUAL_POWER_SEAM_ID, 0, 0):
        raise v8.ProtocolError(
            "PMU_INTERVAL_ENTRY_DIAG_V11A retained seam slots are %d/%d/%d, "
            "expected %d/0/0"
            % (
                res.power_seam_id,
                res.power_rehold_performed,
                res.rehold_guard_cycles,
                v8.PMU_QUAL_POWER_SEAM_ID,
            )
        )

    return PmuIntervalDiagV11AResult(
        base=res,
        header_words=header_words,
        body_words=total_words - header_words,
        t_submit_before_cmd=body[extra_base],
        t_submit_after_cmd=body[extra_base + 1],
        t_vector_probe=body[extra_base + 2],
        t_isr_entry=body[extra_base + 3],
        t_irq_status_seen=body[extra_base + 4],
        i0_hit_count=body[extra_base + 5],
        t3_hit_count=body[extra_base + 6],
        trailing_words=len(body) - PMU_INTERVAL_ENTRY_DIAG_V11A_KNOWN_FIELDS,
    )


def verify_manifest_identity(doc: dict, where: str) -> None:
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    for key in PMU_INTERVAL_REQUIRED_MANIFEST_KEYS:
        if doc.get(key) is None:
            raise SystemExit("FAIL %s: manifest has no %s" % (where, key))
    if doc["schema_version"] != PMU_INTERVAL_ENTRY_DIAG_V11A_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d"
            % (where, doc["schema_version"], PMU_INTERVAL_ENTRY_DIAG_V11A_SCHEMA_VERSION)
        )
    if doc["variant"] != PMU_INTERVAL_ENTRY_DIAG_V11A_NAME:
        raise SystemExit(
            "FAIL %s: manifest variant=%r, expected %s"
            % (where, doc["variant"], PMU_INTERVAL_ENTRY_DIAG_V11A_NAME)
        )
    if doc["qualification_mode"] != "Q1":
        raise SystemExit(
            "FAIL %s: manifest qualification_mode=%r, expected Q1"
            % (where, doc["qualification_mode"])
        )
    if _manifest_build_id(doc) != PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID:
        raise SystemExit(
            "FAIL %s: manifest build_id %r is not the v11a identity 0x%08X"
            % (where, doc.get("build_id"), PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID)
        )
    for key in (
        "characterization_only",
        "not_a_performance_baseline",
        "not_a_latency_measurement",
        "busy_poll_interval_only",
        "d23_split_only",
        "post_t3_handoff_out_of_scope",
        "verify_output_stays_enabled",
        "generated_private_driver_diagnostic_only",
        "production_end_only_frozen",
        "mlek_performance_not_started",
        "j0_first_veneer_probe_only",
        "v11a_perturbed_window_only",
    ):
        if doc.get(key) is not True:
            raise SystemExit(
                "FAIL %s: manifest %s=%r, expected true" % (where, key, doc.get(key))
            )
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise SystemExit("FAIL %s: artifact_sha256 is not an object" % where)
    for name in ("APP.BIN", "VECTORS.BIN", "DDR.BIN"):
        digest = artifacts.get(name)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SystemExit(
                "FAIL %s: artifact_sha256[%s] is not a lowercase SHA-256"
                % (where, name)
            )
    if artifacts != PMU_INTERVAL_V11A_FROZEN_ARTIFACT_SHA256:
        raise SystemExit(
            "FAIL %s: artifact_sha256 does not match the frozen V11-A image" % where
        )
    build_evidence = doc.get("build_evidence_sha256")
    if not isinstance(build_evidence, dict):
        raise SystemExit("FAIL %s: build_evidence_sha256 is not an object" % where)
    for name in PMU_INTERVAL_V11A_FROZEN_BUILD_EVIDENCE_SHA256:
        digest = build_evidence.get(name)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SystemExit(
                "FAIL %s: build_evidence_sha256[%s] is not a lowercase SHA-256"
                % (where, name)
            )
    if build_evidence != PMU_INTERVAL_V11A_FROZEN_BUILD_EVIDENCE_SHA256:
        raise SystemExit(
            "FAIL %s: build_evidence_sha256 does not match the frozen V11-A build"
            % where
        )


def classify_pmu_interval_diag_v11a(
    res: PmuIntervalDiagV11AResult, expected_manifest: dict
) -> dict:
    expected_build_id = _manifest_build_id(expected_manifest)
    expected_lr = expected_manifest.get("expected_return_address")
    v8_manifest = dict(expected_manifest)
    v8_manifest["schema_version"] = v8.PMU_QUAL_SCHEMA_VERSION
    v8_manifest["build_id"] = "0x%08X" % res.build_id
    v8_derived = v8.classify_pmu_qual(res.base, v8_manifest)
    inherited_terms = dict(v8_derived["terms"])
    for key in ("manifest_schema_matches", "manifest_build_id_matches", "build_id_is_hprintf"):
        inherited_terms.pop(key, None)
    terms = {"v8_%s" % key: value for key, value in inherited_terms.items()}
    terms.update(
        {
            "manifest_schema_matches": (
                expected_manifest.get("schema_version")
                == PMU_INTERVAL_ENTRY_DIAG_V11A_SCHEMA_VERSION
            ),
            "manifest_mode_matches": expected_manifest.get("qualification_mode") == "Q1",
            "manifest_build_id_matches": (
                expected_build_id is not None and res.build_id == expected_build_id
            ),
            "build_id_is_v11a": res.build_id == PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID,
            "is_normal_build": res.nc_control_id == 0,
            "is_case_a": res.diag_case == 1,
            "hook_callsite_lr_matches_manifest": (
                isinstance(expected_lr, int)
                and res.hook_callsite_lr_observed == expected_lr
            ),
            "hook_fired_once": res.hook_fired_count == 1,
            "hook_detected_once": res.hook_detected_count == 1,
            "hook_snapshot_valid": res.hook_snapshot_valid == 1,
            "golden_window_ok": bool(
                res.golden_window_base == v8.PMU_DIAG_GOLDEN_WINDOW_BASE
                and res.golden_window_len == v8.PMU_DIAG_GOLDEN_WINDOW_LEN
                and res.golden_window_crc == v8.GOLDEN_WINDOW_CRC
            ),
            "run_rc_ok": res.run_rc == 0,
            "required_flags_ok": (
                (res.valid_flags & v8.RUN_VALID_REQUIRED_MASK)
                == v8.RUN_VALID_REQUIRED_MASK
            ),
            "timestamp_source_valid": res.ts_source_valid == 1,
            "retained_power_seam_exact": (
                res.power_seam_id == v8.PMU_QUAL_POWER_SEAM_ID
                and res.power_rehold_performed == 0
                and res.rehold_guard_cycles == 0
            ),
            "window_mmio_reads_exact": (
                res.pmu_mmio_read_count_delta
                == PMU_INTERVAL_V11A_EXPECTED_PMU_MMIO_READS
            ),
            "window_mmio_writes_exact": (
                res.pmu_mmio_write_count_delta
                == PMU_INTERVAL_V11A_EXPECTED_PMU_MMIO_WRITES
            ),
            "hook_mmio_reads_exact": (
                res.hook_pmu_mmio_read_count
                == PMU_INTERVAL_V11A_EXPECTED_HOOK_PMU_MMIO_READS
            ),
            "hook_mmio_writes_exact": (
                res.hook_pmu_mmio_write_count
                == PMU_INTERVAL_V11A_EXPECTED_HOOK_PMU_MMIO_WRITES
            ),
            "t0_nonzero": res.t_call_enter != 0,
            "t1_nonzero": res.t_submit_before_cmd != 0,
            "t2_nonzero": res.t_submit_after_cmd != 0,
            "j0_nonzero": res.t_vector_probe != 0,
            "i0_nonzero": res.t_isr_entry != 0,
            "t3_nonzero": res.t_irq_status_seen != 0,
            "i0_hit_once": res.i0_hit_count == 1,
            "t3_hit_once": res.t3_hit_count == 1,
            "t4_nonzero": res.hook_entry_timestamp != 0,
            "t5_nonzero": res.t_call_return != 0,
        }
    )
    checkpoints = res.checkpoints()
    timeline = ["T0", "T1", "T2", "J0", "I0", "T3", "T4", "T5"]
    deltas = {}
    for i, left in enumerate(timeline):
        for right in timeline[i + 1:]:
            deltas["D%s%s" % (left[1], right[1])] = (
                checkpoints[right] - checkpoints[left]
            ) & 0xFFFFFFFF
    a0 = (res.t_vector_probe - res.t_submit_after_cmd) & 0xFFFFFFFF
    a1 = (res.t_isr_entry - res.t_vector_probe) & 0xFFFFFFFF
    a2 = (res.t_irq_status_seen - res.t_isr_entry) & 0xFFFFFFFF
    d23 = (res.t_irq_status_seen - res.t_submit_after_cmd) & 0xFFFFFFFF
    deltas.update({"A0": a0, "A1": a1, "A2": a2, "D23": d23})
    positive_half_range = {}
    for name in ("D01", "D12", "A0", "A1", "A2", "D34", "D45", "D23"):
        value = deltas[name]
        positive_half_range[name] = 0 < value < 0x80000000
    terms["checkpoint_order_u32"] = all(
        positive_half_range[name] for name in ("D01", "D12", "D23", "D34", "D45")
    )
    terms["a0_nonzero_u32"] = positive_half_range["A0"]
    terms["a1_nonzero_u32"] = positive_half_range["A1"]
    terms["a2_nonzero_u32"] = positive_half_range["A2"]
    terms["d23_split_consistent_u32"] = ((a0 + a1 + a2) & 0xFFFFFFFF) == d23
    valid = all(terms.values())

    return {
        "terms": terms,
        "invalid_reasons": sorted(k for k, ok in terms.items() if not ok),
        "checkpoints": checkpoints,
        "deltas_u32": deltas,
        "positive_half_range": positive_half_range,
        "characterization_only": True,
        "busy_poll_interval_only": True,
        "d23_split_only": True,
        "post_t3_handoff_out_of_scope": True,
        "not_a_latency_measurement": True,
        "not_a_performance_baseline": True,
        "generated_private_driver_diagnostic_only": True,
        "j0_first_veneer_probe_only": True,
        "j0_label": "first_veneer_probe",
        "a0_label": "submit_after_cmd_to_first_veneer_probe",
        "a1_label": "first_veneer_probe_to_isr_entry",
        "a2_label": "isr_entry_to_status_completion_observation",
        "t2_t3_label": "d23_split_interval",
        "t0_t1_label": "call_entry_to_pre_submit_setup",
        "t1_t2_label": "npu_cmd_read_modify_submit",
        "t3_t4_label": "completion_seen_to_pre_release_driver_path",
        "t4_t5_label": "hook_to_return_including_verify_output",
        "v11a_perturbed_window_cycles": (
            v8_derived["raw_delta_diagnostic"] if valid else None
        ),
        "not_comparable_to_v10_window": True,
        "not_comparable_to_v9_window": True,
        "valid": valid,
    }
