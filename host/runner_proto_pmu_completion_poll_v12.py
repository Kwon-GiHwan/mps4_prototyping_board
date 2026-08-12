"""Schema-v12 PMU completion-poll diagnostic protocol helpers.

Diagnostic-only host path for the V12 hard-bypass image. The schema extends
the schema-v8 qualification wire layout with a 15-word polling appendix and
keeps earlier parsers intentionally rejecting it.
"""

from __future__ import annotations

import re
import struct
from dataclasses import asdict, dataclass

try:
    from host import runner_proto as v8
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8

PMU_COMPLETION_POLL_V12_NAME = "PMU_COMPLETION_POLL_DIAG_V12"
PMU_COMPLETION_POLL_V12_MAGIC = v8.PMU_QUAL_MAGIC
PMU_COMPLETION_POLL_V12_SCHEMA_VERSION = 12
PMU_COMPLETION_POLL_V12_HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS
PMU_COMPLETION_POLL_V12_BASE_FIELDS = v8.PMU_QUAL_KNOWN_FIELDS
PMU_COMPLETION_POLL_V12_EXTRA_FIELDS = 15
PMU_COMPLETION_POLL_V12_BODY_WORDS = (
    PMU_COMPLETION_POLL_V12_BASE_FIELDS + PMU_COMPLETION_POLL_V12_EXTRA_FIELDS
)
PMU_COMPLETION_POLL_V12_TOTAL_WORDS = (
    PMU_COMPLETION_POLL_V12_HEADER_WORDS + PMU_COMPLETION_POLL_V12_BODY_WORDS
)
PMU_COMPLETION_POLL_V12_PAYLOAD_SIZE = PMU_COMPLETION_POLL_V12_TOTAL_WORDS * 4
PMU_COMPLETION_POLL_V12_BUILD_ID = 0x32314950  # ASCII "PI12", little-endian.
PMU_COMPLETION_POLL_V12_POLL_SUCCESS = 1
PMU_COMPLETION_POLL_V12_POLL_TIMEOUT = 2
PMU_COMPLETION_POLL_V12_STATUS_COMPLETE_MASK = 0x02
PMU_COMPLETION_POLL_V12_REQUIRED_MANIFEST_KEYS = (
    "variant",
    "schema_version",
    "build_id",
    "qualification_mode",
    "expected_return_address",
    "evidence_source",
    "artifact_sha256",
    "build_evidence_sha256",
)
PMU_COMPLETION_POLL_V12_REQUIRED_MANIFEST_BOOLEANS = (
    "characterization_only",
    "not_a_performance_baseline",
    "not_a_latency_measurement",
    "generated_private_driver_diagnostic_only",
    "production_end_only_frozen",
    "diagnostic_only",
    "not_numerically_comparable_to_v11a",
    "not_latency",
    "not_t_npu",
    "not_production",
    "not_mlek",
)
PMU_COMPLETION_POLL_V12_REQUIRED_ARTIFACT_KEYS = (
    "APP.BIN",
    "VECTORS.BIN",
    "DDR.BIN",
)
PMU_COMPLETION_POLL_V12_REQUIRED_BUILD_EVIDENCE_KEYS = (
    "runner_pmu_completion_poll_v12.elf",
    "runner_pmu_completion_poll_v12.map",
    "generated_runner.c",
    "generated_vendor_u85.c",
    "checker_disassembly.txt",
    "checker_nm.txt",
)
PMU_COMPLETION_POLL_V12_REQUIRED_BINDING_KEYS = (
    "expected_return_address",
    "runtime_vector_target_address",
    "wait_call_address",
    "hprintf_callsite_address",
    "helper_status_read_address",
    "helper_status_test_address",
    "poll_helper_p0_address",
    "poll_helper_p1_address",
    "poll_helper_p2_address",
    "success_cmd2_1_store_address",
    "success_qread_load_address",
    "success_cmd2_2_store_address",
    "timeout_qread_load_address",
    "timeout_cmd2_store_address",
    "cmd0_store_address",
    "terminal_cmd0c_store_address",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^0x[0-9a-fA-F]{8}$")

ProtocolError = v8.ProtocolError


def u32(value: int) -> int:
    return int(value) & 0xFFFFFFFF


@dataclass(frozen=True)
class PmuCompletionPollV12Result:
    base: v8.PmuQualResult
    header_words: int
    body_words: int
    t_submit_after_cmd: int
    t_poll_entry: int
    t_status_completion_seen: int
    t_poll_exit: int
    poll_result: int
    status_at_success: int
    installed_vector: int
    nvic_enabled_before_submit: int
    nvic_pending_after_initial_clear: int
    nvic_active_before_submit: int
    irq_triggered_before_submit: int
    nvic_pending_before_final_clear: int
    nvic_pending_after_final_clear: int
    nvic_active_after_cleanup: int
    irq_triggered_after_cleanup: int
    trailing_words: int

    def __getattr__(self, name):
        if name == "base":
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "base"), name)

    def _asdict(self) -> dict:
        return target_fields(self)


def target_fields(res: PmuCompletionPollV12Result) -> dict:
    doc = asdict(res.base)
    doc.update(
        {
            "header_words": res.header_words,
            "body_words": res.body_words,
            "t_submit_after_cmd": res.t_submit_after_cmd,
            "t_poll_entry": res.t_poll_entry,
            "t_status_completion_seen": res.t_status_completion_seen,
            "t_poll_exit": res.t_poll_exit,
            "poll_result": res.poll_result,
            "status_at_success": res.status_at_success,
            "installed_vector": res.installed_vector,
            "nvic_enabled_before_submit": res.nvic_enabled_before_submit,
            "nvic_pending_after_initial_clear": res.nvic_pending_after_initial_clear,
            "nvic_active_before_submit": res.nvic_active_before_submit,
            "irq_triggered_before_submit": res.irq_triggered_before_submit,
            "nvic_pending_before_final_clear": res.nvic_pending_before_final_clear,
            "nvic_pending_after_final_clear": res.nvic_pending_after_final_clear,
            "nvic_active_after_cleanup": res.nvic_active_after_cleanup,
            "irq_triggered_after_cleanup": res.irq_triggered_after_cleanup,
            "v12_trailing_words": res.trailing_words,
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


def verify_manifest_identity(doc: dict, where: str) -> None:
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    for key in PMU_COMPLETION_POLL_V12_REQUIRED_MANIFEST_KEYS:
        if doc.get(key) is None:
            raise SystemExit("FAIL %s: manifest has no %s" % (where, key))
    if doc.get("variant") != PMU_COMPLETION_POLL_V12_NAME:
        raise SystemExit(
            "FAIL %s: manifest variant=%r, expected %s"
            % (where, doc.get("variant"), PMU_COMPLETION_POLL_V12_NAME)
        )
    if doc.get("schema_version") != PMU_COMPLETION_POLL_V12_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d"
            % (where, doc.get("schema_version"), PMU_COMPLETION_POLL_V12_SCHEMA_VERSION)
        )
    if doc.get("qualification_mode") != "Q1":
        raise SystemExit(
            "FAIL %s: manifest qualification_mode=%r, expected Q1"
            % (where, doc.get("qualification_mode"))
        )
    if doc.get("evidence_source") != "arm_elf":
        raise SystemExit(
            "FAIL %s: manifest evidence_source=%r, expected arm_elf"
            % (where, doc.get("evidence_source"))
        )
    if _manifest_build_id(doc) != PMU_COMPLETION_POLL_V12_BUILD_ID:
        raise SystemExit(
            "FAIL %s: manifest build_id %r is not the V12 identity 0x%08X"
            % (where, doc.get("build_id"), PMU_COMPLETION_POLL_V12_BUILD_ID)
        )
    for key in PMU_COMPLETION_POLL_V12_REQUIRED_MANIFEST_BOOLEANS:
        if doc.get(key) is not True:
            raise SystemExit(
                "FAIL %s: manifest %s=%r, expected true" % (where, key, doc.get(key))
            )
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise SystemExit("FAIL %s: artifact_sha256 is not an object" % where)
    if tuple(sorted(artifacts)) != tuple(sorted(PMU_COMPLETION_POLL_V12_REQUIRED_ARTIFACT_KEYS)):
        raise SystemExit(
            "FAIL %s: artifact_sha256 keys %r, expected %r"
            % (
                where,
                sorted(artifacts),
                list(PMU_COMPLETION_POLL_V12_REQUIRED_ARTIFACT_KEYS),
            )
        )
    for name in PMU_COMPLETION_POLL_V12_REQUIRED_ARTIFACT_KEYS:
        digest = artifacts.get(name)
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise SystemExit(
                "FAIL %s: artifact_sha256[%s]=%r is not a lowercase SHA-256"
                % (where, name, digest)
            )
    build_evidence = doc.get("build_evidence_sha256")
    if not isinstance(build_evidence, dict):
        raise SystemExit("FAIL %s: build_evidence_sha256 is not an object" % where)
    for name in PMU_COMPLETION_POLL_V12_REQUIRED_BUILD_EVIDENCE_KEYS:
        digest = build_evidence.get(name)
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise SystemExit(
                "FAIL %s: build_evidence_sha256[%s]=%r is not a lowercase SHA-256"
                % (where, name, digest)
            )
    if doc.get("helper_symbol") != "v12_poll_completion":
        raise SystemExit(
            "FAIL %s: helper_symbol=%r, expected v12_poll_completion"
            % (where, doc.get("helper_symbol"))
        )
    if doc.get("runtime_vector_target_symbol") != "u85_irq_handler":
        raise SystemExit(
            "FAIL %s: runtime_vector_target_symbol=%r, expected u85_irq_handler"
            % (where, doc.get("runtime_vector_target_symbol"))
        )
    for key in PMU_COMPLETION_POLL_V12_REQUIRED_BINDING_KEYS:
        value = doc.get(key)
        if key == "expected_return_address":
            if not isinstance(value, int) or isinstance(value, bool):
                raise SystemExit(
                    "FAIL %s: %s=%r is not numeric" % (where, key, value)
                )
            continue
        if not isinstance(value, str) or HEX32.fullmatch(value) is None:
            raise SystemExit(
                "FAIL %s: %s=%r is not 0xXXXXXXXX" % (where, key, value)
            )
    if doc["expected_return_address"] != int(doc["hprintf_callsite_address"], 16) + 4:
        raise SystemExit(
            "FAIL %s: expected_return_address=%r does not equal hprintf_callsite_address+4"
            % (where, doc["expected_return_address"])
        )


def parse_pmu_completion_poll_v12_payload(payload: bytes) -> PmuCompletionPollV12Result:
    if len(payload) < PMU_COMPLETION_POLL_V12_HEADER_WORDS * 4:
        raise ProtocolError("v12 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_COMPLETION_POLL_V12_MAGIC:
        raise ProtocolError("bad PMU_COMPLETION_POLL_V12 magic 0x%08X" % magic)
    if version != PMU_COMPLETION_POLL_V12_SCHEMA_VERSION:
        raise ProtocolError(
            "unsupported PMU_COMPLETION_POLL_V12 schema version %d" % version
        )
    if header_words != PMU_COMPLETION_POLL_V12_HEADER_WORDS:
        raise ProtocolError(
            "unexpected PMU_COMPLETION_POLL_V12 header_words %d" % header_words
        )
    if total_words != PMU_COMPLETION_POLL_V12_TOTAL_WORDS:
        raise ProtocolError(
            "total_payload_words %d does not equal the v12 contract %d"
            % (total_words, PMU_COMPLETION_POLL_V12_TOTAL_WORDS)
        )
    if total_words * 4 != len(payload):
        raise ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload))
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("PMU_COMPLETION_POLL_V12 payload CRC mismatch")

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
        trailing_words=len(body) - PMU_COMPLETION_POLL_V12_BODY_WORDS,
    )
    if (seq, flags, rc) != (res.run_sequence, res.valid_flags, res.run_rc):
        raise ProtocolError(
            "PMU_COMPLETION_POLL_V12 header/body disagree on seq/flags/rc"
        )
    if res.schema_version != version:
        raise ProtocolError(
            "PMU_COMPLETION_POLL_V12 body schema_version %d != header %d"
            % (res.schema_version, version)
        )
    if (
        res.power_seam_id,
        res.power_rehold_performed,
        res.rehold_guard_cycles,
    ) != (v8.PMU_QUAL_POWER_SEAM_ID, 0, 0):
        raise ProtocolError(
            "PMU_COMPLETION_POLL_V12 retained seam slots are %d/%d/%d, expected %d/0/0"
            % (
                res.power_seam_id,
                res.power_rehold_performed,
                res.rehold_guard_cycles,
                v8.PMU_QUAL_POWER_SEAM_ID,
            )
        )
    return PmuCompletionPollV12Result(
        base=res,
        header_words=header_words,
        body_words=total_words - header_words,
        t_submit_after_cmd=body[extra_base],
        t_poll_entry=body[extra_base + 1],
        t_status_completion_seen=body[extra_base + 2],
        t_poll_exit=body[extra_base + 3],
        poll_result=body[extra_base + 4],
        status_at_success=body[extra_base + 5],
        installed_vector=body[extra_base + 6],
        nvic_enabled_before_submit=body[extra_base + 7],
        nvic_pending_after_initial_clear=body[extra_base + 8],
        nvic_active_before_submit=body[extra_base + 9],
        irq_triggered_before_submit=body[extra_base + 10],
        nvic_pending_before_final_clear=body[extra_base + 11],
        nvic_pending_after_final_clear=body[extra_base + 12],
        nvic_active_after_cleanup=body[extra_base + 13],
        irq_triggered_after_cleanup=body[extra_base + 14],
        trailing_words=len(body) - PMU_COMPLETION_POLL_V12_BODY_WORDS,
    )


def classify_pmu_completion_poll_v12_payload(
    res: PmuCompletionPollV12Result, expected_manifest: dict
) -> dict:
    expected_build_id = _manifest_build_id(expected_manifest)
    expected_lr = expected_manifest.get("expected_return_address")
    runtime_vector_target = expected_manifest.get("runtime_vector_target_address")
    runtime_vector_target_int = None
    try:
        if isinstance(runtime_vector_target, str):
            runtime_vector_target_int = int(runtime_vector_target, 16)
    except ValueError:
        runtime_vector_target_int = None

    # Reuse the retained v8 sample-validity terms without laundering the V12
    # manifest identity. The inherited classifier sees the retained Q1 shape,
    # while V12-specific manifest identity is checked separately against the
    # unmodified producer manifest by verify_manifest_identity() and by the
    # V12-specific terms below.
    v8_manifest = dict(expected_manifest)
    v8_manifest["schema_version"] = v8.PMU_QUAL_SCHEMA_VERSION
    v8_manifest["build_id"] = "0x%08X" % v8.PMU_QUAL_BUILD_IDS["Q1"]
    v8_derived = v8.classify_pmu_qual(res.base, v8_manifest)
    inherited_terms = dict(v8_derived["terms"])
    for key in ("manifest_schema_matches", "manifest_build_id_matches", "build_id_is_hprintf"):
        inherited_terms.pop(key, None)
    terms = {"v8_%s" % key: value for key, value in inherited_terms.items()}

    d0 = u32(res.t_poll_entry - res.t_submit_after_cmd)
    d1 = u32(res.t_status_completion_seen - res.t_poll_entry)
    d2 = u32(res.t_poll_exit - res.t_status_completion_seen)
    submit_to_observed = u32(res.t_status_completion_seen - res.t_submit_after_cmd)
    p2_from_submit = u32(res.t_poll_exit - res.t_submit_after_cmd)
    success = res.poll_result == PMU_COMPLETION_POLL_V12_POLL_SUCCESS
    timeout = res.poll_result == PMU_COMPLETION_POLL_V12_POLL_TIMEOUT

    terms.update(
        {
            "manifest_schema_matches": (
                expected_manifest.get("schema_version")
                == PMU_COMPLETION_POLL_V12_SCHEMA_VERSION
            ),
            "manifest_mode_matches": expected_manifest.get("qualification_mode") == "Q1",
            "manifest_build_id_matches": (
                expected_build_id is not None and res.build_id == expected_build_id
            ),
            "build_id_is_v12": res.build_id == PMU_COMPLETION_POLL_V12_BUILD_ID,
            "hook_callsite_lr_matches_manifest": (
                isinstance(expected_lr, int)
                and res.hook_callsite_lr_observed == expected_lr
            ),
            "runtime_vector_matches_manifest": (
                runtime_vector_target_int is not None
                and res.installed_vector == runtime_vector_target_int
            ),
            "nvic_disabled_before_submit": res.nvic_enabled_before_submit == 0,
            "nvic_pending_cleared_before_submit": (
                res.nvic_pending_after_initial_clear == 0
            ),
            "nvic_inactive_before_submit": res.nvic_active_before_submit == 0,
            "irq_flag_false_before_submit": res.irq_triggered_before_submit == 0,
            "pending_before_final_clear_u32": isinstance(
                res.nvic_pending_before_final_clear, int
            ),
            "nvic_pending_cleared_after_cleanup": (
                res.nvic_pending_after_final_clear == 0
            ),
            "nvic_inactive_after_cleanup": res.nvic_active_after_cleanup == 0,
            "irq_flag_false_after_cleanup": res.irq_triggered_after_cleanup == 0,
            "poll_result_known": success or timeout,
            "p0_nonzero": res.t_poll_entry != 0,
        }
    )

    positive_half_range = {
        "d0": 0 < d0 < 0x80000000,
        "d1": 0 < d1 < 0x80000000,
        "d2": 0 < d2 < 0x80000000,
    }
    if success:
        terms.update(
            {
                "p1_nonzero": res.t_status_completion_seen != 0,
                "p2_nonzero": res.t_poll_exit != 0,
                "status_success_bit_set": (
                    (res.status_at_success & PMU_COMPLETION_POLL_V12_STATUS_COMPLETE_MASK)
                    == PMU_COMPLETION_POLL_V12_STATUS_COMPLETE_MASK
                ),
                "positive_half_range_d0": positive_half_range["d0"],
                "positive_half_range_d1": positive_half_range["d1"],
                "positive_half_range_d2": positive_half_range["d2"],
                "submit_to_observed_identity": u32(d0 + d1) == submit_to_observed,
                "submit_to_exit_identity": u32(d0 + d1 + d2) == p2_from_submit,
            }
        )
    else:
        terms.update(
            {
                "p1_zero_on_timeout": timeout and res.t_status_completion_seen == 0,
                "p2_zero_on_timeout": timeout and res.t_poll_exit == 0,
                "status_zero_on_timeout": timeout and res.status_at_success == 0,
            }
        )

    valid = all(terms.values()) and success
    derived = None
    if valid:
        derived = {
            "d0": d0,
            "d1": d1,
            "d2": d2,
            "submit_to_status_completion_observed_cycles": submit_to_observed,
            "submit_to_poll_exit_cycles": p2_from_submit,
        }

    return {
        "terms": terms,
        "invalid_reasons": sorted(k for k, ok in terms.items() if not ok),
        "timeout": timeout,
        "campaign_abort": timeout,
        "fresh_boot_required": timeout,
        "archive_write": bool(valid),
        "characterization_only": True,
        "not_a_latency_measurement": True,
        "not_a_performance_baseline": True,
        "generated_private_driver_diagnostic_only": True,
        "diagnostic_only": True,
        "derived": derived,
        "deltas_u32": {"d0": d0, "d1": d1, "d2": d2},
        "valid": valid,
    }
