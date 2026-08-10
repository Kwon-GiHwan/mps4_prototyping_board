"""Schema-v10 PMU interval characterization protocol helpers.

This is a separate host path on purpose. `runner_proto.py` keeps the v8 ABI
and must continue to reject a v10 payload.
"""

from __future__ import annotations

import struct
import re
from dataclasses import asdict, dataclass

import runner_proto as v8

PMU_INTERVAL_FINE_DIAG_V10_NAME = "PMU_INTERVAL_FINE_DIAG_V10"
PMU_INTERVAL_FINE_DIAG_V10_MAGIC = v8.PMU_QUAL_MAGIC
PMU_INTERVAL_FINE_DIAG_V10_SCHEMA_VERSION = 10
PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS
PMU_INTERVAL_FINE_DIAG_V10_BASE_FIELDS = v8.PMU_QUAL_KNOWN_FIELDS
PMU_INTERVAL_FINE_DIAG_V10_EXTRA_FIELDS = 6
PMU_INTERVAL_FINE_DIAG_V10_KNOWN_FIELDS = (
    PMU_INTERVAL_FINE_DIAG_V10_BASE_FIELDS + PMU_INTERVAL_FINE_DIAG_V10_EXTRA_FIELDS
)
PMU_INTERVAL_FINE_DIAG_V10_TOTAL_WORDS = (
    PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS + PMU_INTERVAL_FINE_DIAG_V10_KNOWN_FIELDS
)
PMU_INTERVAL_FINE_DIAG_V10_PAYLOAD_SIZE = PMU_INTERVAL_FINE_DIAG_V10_TOTAL_WORDS * 4
PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID = 0x30314950  # ASCII "PI10", little-endian.
PMU_INTERVAL_V10_EXPECTED_PMU_MMIO_READS = 58
PMU_INTERVAL_V10_EXPECTED_PMU_MMIO_WRITES = 8
PMU_INTERVAL_V10_EXPECTED_HOOK_PMU_MMIO_READS = 16
PMU_INTERVAL_V10_EXPECTED_HOOK_PMU_MMIO_WRITES = 1
PMU_INTERVAL_V10_FROZEN_MANIFEST_SHA256 = (
    "1a0eb13c6dbc7181bd85544307d6c643efdfe5e1352b95aa1234eed6c2518792"
)
PMU_INTERVAL_V10_FROZEN_ARTIFACT_SHA256 = {
    "APP.BIN": "92e81e5ac51ed56c89eb3cc447ef421334142ec9a2a941990995025d546b00b9",
    "VECTORS.BIN": "1b86143c1bf9ba06263ffe1744b41f57b79f5d50f9db67bd9fc0eac33b67c81f",
    "DDR.BIN": "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
}
PMU_INTERVAL_V10_FROZEN_BUILD_EVIDENCE_SHA256 = {
    "runner_pmu_interval_v10.elf": "6f99df6a35da87be8dca41af7dbe7e16a3c1af84796ac1e159273b3051469dac",
    "runner_pmu_interval_v10.map": "32eea379e1d416f3e89f8143b974f54f4dc8df3f35b6fcddac354e4e33de035d",
    "generated_runner.c": "6e10eb040c4950f9264f8354f709dd8ddf8ec326e86c99e2a47ff5aa0f43b0f2",
    "generated_vendor_u85.c": "0b760c09a0bad6d9728d5fe2667a933c49e4fbe019e749b0152ae58ef6ea4570",
    "generated_vendor_u85.o": "1e3ee6a43a5a6f912ee86d88874f5d0bf8206c96297bf49c12a14b2b3e86edbd",
    "preprocessed_runner.i": "5efa2f53eebfadef88d100965e2972588091361226d0a2c32da30bc2fa02b089",
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
class PmuIntervalDiagV10Result:
    base: v8.PmuQualResult
    t_submit_before_cmd: int
    t_submit_after_cmd: int
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
            "I0": self.t_isr_entry,
            "T3": self.t_irq_status_seen,
            "T4": self.hook_entry_timestamp,
            "T5": self.t_call_return,
        }


def target_fields(res: PmuIntervalDiagV10Result) -> dict:
    doc = asdict(res.base)
    doc.update({
        "t_submit_before_cmd": res.t_submit_before_cmd,
        "t_submit_after_cmd": res.t_submit_after_cmd,
        "t_isr_entry": res.t_isr_entry,
        "t_irq_status_seen": res.t_irq_status_seen,
        "i0_hit_count": res.i0_hit_count,
        "t3_hit_count": res.t3_hit_count,
        "v10_trailing_words": res.trailing_words,
    })
    return doc


def _manifest_build_id(doc: dict) -> int | None:
    value = doc.get("build_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def parse_pmu_interval_diag_v10_payload(payload: bytes) -> PmuIntervalDiagV10Result:
    if len(payload) < PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS * 4:
        raise v8.ProtocolError("v10 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_INTERVAL_FINE_DIAG_V10_MAGIC:
        raise v8.ProtocolError("bad PMU_INTERVAL_FINE_DIAG_V10 magic 0x%08X" % magic)
    if version != PMU_INTERVAL_FINE_DIAG_V10_SCHEMA_VERSION:
        raise v8.ProtocolError(
            "unsupported PMU_INTERVAL_FINE_DIAG_V10 schema version %d" % version
        )
    if header_words != PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS:
        raise v8.ProtocolError(
            "unexpected PMU_INTERVAL_FINE_DIAG_V10 header_words %d" % header_words
        )
    if total_words != PMU_INTERVAL_FINE_DIAG_V10_TOTAL_WORDS:
        raise v8.ProtocolError(
            "total_payload_words %d does not equal the v10 contract %d"
            % (total_words, PMU_INTERVAL_FINE_DIAG_V10_TOTAL_WORDS)
        )
    if total_words * 4 != len(payload):
        raise v8.ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload))
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise v8.ProtocolError("PMU_INTERVAL_FINE_DIAG_V10 payload CRC mismatch")

    body = struct.unpack_from("<%dI" % (total_words - header_words), payload, header_words * 4)
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
        trailing_words=len(body) - PMU_INTERVAL_FINE_DIAG_V10_KNOWN_FIELDS,
    )
    if (seq, flags, rc) != (res.run_sequence, res.valid_flags, res.run_rc):
        raise v8.ProtocolError(
            "PMU_INTERVAL_FINE_DIAG_V10 header/body disagree on seq/flags/rc"
        )
    if res.schema_version != version:
        raise v8.ProtocolError(
            "PMU_INTERVAL_FINE_DIAG_V10 body schema_version %d != header %d"
            % (res.schema_version, version)
        )
    if (res.power_seam_id, res.power_rehold_performed, res.rehold_guard_cycles) \
            != (v8.PMU_QUAL_POWER_SEAM_ID, 0, 0):
        raise v8.ProtocolError(
            "PMU_INTERVAL_FINE_DIAG_V10 retained seam slots are %d/%d/%d, "
            "expected %d/0/0"
            % (res.power_seam_id, res.power_rehold_performed,
               res.rehold_guard_cycles, v8.PMU_QUAL_POWER_SEAM_ID)
        )

    return PmuIntervalDiagV10Result(
        base=res,
        t_submit_before_cmd=body[extra_base],
        t_submit_after_cmd=body[extra_base + 1],
        t_isr_entry=body[extra_base + 2],
        t_irq_status_seen=body[extra_base + 3],
        i0_hit_count=body[extra_base + 4],
        t3_hit_count=body[extra_base + 5],
        trailing_words=len(body) - PMU_INTERVAL_FINE_DIAG_V10_KNOWN_FIELDS,
    )


def verify_manifest_identity(doc: dict, where: str) -> None:
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    for key in PMU_INTERVAL_REQUIRED_MANIFEST_KEYS:
        if doc.get(key) is None:
            raise SystemExit("FAIL %s: manifest has no %s" % (where, key))
    if doc["schema_version"] != PMU_INTERVAL_FINE_DIAG_V10_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d"
            % (where, doc["schema_version"], PMU_INTERVAL_FINE_DIAG_V10_SCHEMA_VERSION)
        )
    if doc["variant"] != PMU_INTERVAL_FINE_DIAG_V10_NAME:
        raise SystemExit(
            "FAIL %s: manifest variant=%r, expected %s"
            % (where, doc["variant"], PMU_INTERVAL_FINE_DIAG_V10_NAME)
        )
    if doc["qualification_mode"] != "Q1":
        raise SystemExit(
            "FAIL %s: manifest qualification_mode=%r, expected Q1"
            % (where, doc["qualification_mode"])
        )
    if _manifest_build_id(doc) != PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID:
        raise SystemExit(
            "FAIL %s: manifest build_id %r is not the v10 identity 0x%08X"
            % (where, doc.get("build_id"), PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID)
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
    ):
        if doc.get(key) is not True:
            raise SystemExit("FAIL %s: manifest %s=%r, expected true" % (where, key, doc.get(key)))
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise SystemExit("FAIL %s: artifact_sha256 is not an object" % where)
    for name in ("APP.BIN", "VECTORS.BIN", "DDR.BIN"):
        digest = artifacts.get(name)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SystemExit(
                "FAIL %s: artifact_sha256[%s] is not a lowercase SHA-256"
                % (where, name))
    if artifacts != PMU_INTERVAL_V10_FROZEN_ARTIFACT_SHA256:
        raise SystemExit(
            "FAIL %s: artifact_sha256 does not match the frozen V10 image" % where)
    build_evidence = doc.get("build_evidence_sha256")
    if not isinstance(build_evidence, dict):
        raise SystemExit("FAIL %s: build_evidence_sha256 is not an object" % where)
    for name in PMU_INTERVAL_V10_FROZEN_BUILD_EVIDENCE_SHA256:
        digest = build_evidence.get(name)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SystemExit(
                "FAIL %s: build_evidence_sha256[%s] is not a lowercase SHA-256"
                % (where, name))
    if build_evidence != PMU_INTERVAL_V10_FROZEN_BUILD_EVIDENCE_SHA256:
        raise SystemExit(
            "FAIL %s: build_evidence_sha256 does not match the frozen V10 build"
            % where)


def classify_pmu_interval_diag_v10(
    res: PmuIntervalDiagV10Result, expected_manifest: dict
) -> dict:
    expected_build_id = _manifest_build_id(expected_manifest)
    expected_lr = expected_manifest.get("expected_return_address")
    v8_manifest = dict(expected_manifest)
    v8_manifest["schema_version"] = v8.PMU_QUAL_SCHEMA_VERSION
    v8_manifest["build_id"] = "0x%08X" % res.build_id
    v8_derived = v8.classify_pmu_qual(res.base, v8_manifest)
    inherited_terms = dict(v8_derived["terms"])
    # These three v8 identity terms are intentionally replaced below. Keeping
    # the synthesized v8 manifest checks would make them vacuously true.
    for key in ("manifest_schema_matches", "manifest_build_id_matches",
                "build_id_is_hprintf"):
        inherited_terms.pop(key, None)
    terms = {"v8_%s" % key: value for key, value in inherited_terms.items()}
    terms.update({
        "manifest_schema_matches": (
            expected_manifest.get("schema_version") == PMU_INTERVAL_FINE_DIAG_V10_SCHEMA_VERSION
        ),
        "manifest_mode_matches": expected_manifest.get("qualification_mode") == "Q1",
        "manifest_build_id_matches": (
            expected_build_id is not None and res.build_id == expected_build_id
        ),
        "build_id_is_v10": res.build_id == PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID,
        "is_normal_build": res.nc_control_id == 0,
        "is_case_a": res.diag_case == 1,
        "hook_callsite_lr_matches_manifest": (
            isinstance(expected_lr, int) and res.hook_callsite_lr_observed == expected_lr
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
            (res.valid_flags & v8.RUN_VALID_REQUIRED_MASK) == v8.RUN_VALID_REQUIRED_MASK
        ),
        "timestamp_source_valid": res.ts_source_valid == 1,
        "retained_power_seam_exact": (
            res.power_seam_id == v8.PMU_QUAL_POWER_SEAM_ID
            and res.power_rehold_performed == 0
            and res.rehold_guard_cycles == 0
        ),
        "window_mmio_reads_exact": (
            res.pmu_mmio_read_count_delta
            == PMU_INTERVAL_V10_EXPECTED_PMU_MMIO_READS
        ),
        "window_mmio_writes_exact": (
            res.pmu_mmio_write_count_delta
            == PMU_INTERVAL_V10_EXPECTED_PMU_MMIO_WRITES
        ),
        "hook_mmio_reads_exact": (
            res.hook_pmu_mmio_read_count
            == PMU_INTERVAL_V10_EXPECTED_HOOK_PMU_MMIO_READS
        ),
        "hook_mmio_writes_exact": (
            res.hook_pmu_mmio_write_count
            == PMU_INTERVAL_V10_EXPECTED_HOOK_PMU_MMIO_WRITES
        ),
        "t0_nonzero": res.t_call_enter != 0,
        "t1_nonzero": res.t_submit_before_cmd != 0,
        "t2_nonzero": res.t_submit_after_cmd != 0,
        "i0_nonzero": res.t_isr_entry != 0,
        "t3_nonzero": res.t_irq_status_seen != 0,
        "i0_hit_once": res.i0_hit_count == 1,
        "t3_hit_once": res.t3_hit_count == 1,
        "t4_nonzero": res.hook_entry_timestamp != 0,
        "t5_nonzero": res.t_call_return != 0,
    })
    checkpoints = res.checkpoints()
    timeline = ["T0", "T1", "T2", "T3", "T4", "T5"]
    deltas = {}
    for i, left in enumerate(timeline):
        for right in timeline[i + 1:]:
            deltas["D%s%s" % (left[1], right[1])] = (
                checkpoints[right] - checkpoints[left]
            ) & 0xFFFFFFFF
    e0 = (res.t_isr_entry - res.t_submit_after_cmd) & 0xFFFFFFFF
    e1 = (res.t_irq_status_seen - res.t_isr_entry) & 0xFFFFFFFF
    d23 = (res.t_irq_status_seen - res.t_submit_after_cmd) & 0xFFFFFFFF
    deltas.update({"E0": e0, "E1": e1})
    adjacent = [deltas[name] for name in ("D01", "D12", "D23", "D34", "D45")]
    terms["checkpoint_order_u32"] = all(0 < value < 0x80000000 for value in adjacent)
    terms["e0_nonzero_u32"] = 0 < e0 < 0x80000000
    terms["e1_nonzero_u32"] = 0 < e1 < 0x80000000
    terms["d23_split_consistent_u32"] = ((e0 + e1) & 0xFFFFFFFF) == d23
    valid = all(terms.values())

    return {
        "terms": terms,
        "invalid_reasons": sorted(k for k, ok in terms.items() if not ok),
        "checkpoints": checkpoints,
        "deltas_u32": deltas,
        "characterization_only": True,
        "busy_poll_interval_only": True,
        "d23_split_only": True,
        "post_t3_handoff_out_of_scope": True,
        "not_a_latency_measurement": True,
        "t2_i0_label": "submit_to_isr_entry_including_npu_irq_and_exception_entry",
        "i0_t3_label": "isr_entry_to_status_completion_observation",
        "t2_t3_label": "d23_split_interval",
        "t0_t1_label": "call_entry_to_pre_submit_setup",
        "t1_t2_label": "npu_cmd_read_modify_submit",
        "t3_t4_label": "completion_seen_to_pre_release_driver_path",
        "t4_t5_label": "hook_to_return_including_verify_output",
        # The added timestamp probes perturb this image. Keep its PMU window
        # under a V10-only name so it cannot be silently compared with v8/CFG.
        "v10_perturbed_window_cycles": (
            v8_derived["raw_delta_diagnostic"] if valid else None),
        "not_comparable_to_v8_cfg_window": True,
        "not_comparable_to_v9_window": True,
        "valid": valid,
    }
