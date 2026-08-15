"""Schema-v13 PMU completion-poll count diagnostic protocol helpers."""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import asdict, dataclass

try:
    from host import runner_proto as v8
    from host import runner_proto_pmu_completion_poll_v12 as v12
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8
    import runner_proto_pmu_completion_poll_v12 as v12

PMU_COMPLETION_POLL_COUNT_V13_NAME = "PMU_COMPLETION_POLL_COUNT_DIAG_V13"
PMU_COMPLETION_POLL_COUNT_V13_MAGIC = v8.PMU_QUAL_MAGIC
PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION = 13
PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS
PMU_COMPLETION_POLL_COUNT_V13_BASE_FIELDS = v8.PMU_QUAL_KNOWN_FIELDS
PMU_COMPLETION_POLL_COUNT_V13_EXTRA_FIELDS = 16
PMU_COMPLETION_POLL_COUNT_V13_BODY_WORDS = (
    PMU_COMPLETION_POLL_COUNT_V13_BASE_FIELDS
    + PMU_COMPLETION_POLL_COUNT_V13_EXTRA_FIELDS
)
PMU_COMPLETION_POLL_COUNT_V13_TOTAL_WORDS = (
    PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS
    + PMU_COMPLETION_POLL_COUNT_V13_BODY_WORDS
)
PMU_COMPLETION_POLL_COUNT_V13_PAYLOAD_SIZE = (
    PMU_COMPLETION_POLL_COUNT_V13_TOTAL_WORDS * 4
)
PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID = 0x33314950
PMU_COMPLETION_POLL_COUNT_V13_POLL_SUCCESS = (
    v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS
)
PMU_COMPLETION_POLL_COUNT_V13_POLL_TIMEOUT = (
    v12.PMU_COMPLETION_POLL_V12_POLL_TIMEOUT
)
PMU_COMPLETION_POLL_COUNT_V13_STATUS_COMPLETE_MASK = (
    v12.PMU_COMPLETION_POLL_V12_STATUS_COMPLETE_MASK
)
PMU_COMPLETION_POLL_COUNT_V13_POLL_REMAINING_INVALID = 0
PMU_COMPLETION_POLL_COUNT_V13_MIN_REMAINING = 1
PMU_COMPLETION_POLL_COUNT_V13_MAX_REMAINING = 10000
PMU_COMPLETION_POLL_COUNT_V13_WIRE_WORD_INDEX = 100
PMU_COMPLETION_POLL_COUNT_V13_REMAINING_OFFSET_BYTES = 400
PMU_COMPLETION_POLL_COUNT_V13_REQUIRED_ARTIFACT_KEYS = (
    "app_bin",
    "authoritative_v12_elf",
    "authoritative_v12_nm",
    "authoritative_v12_objdump",
    "cross_elf_evidence",
    "ddr_bin",
    "elf",
    "interface_header",
    "map",
    "preprocessed_runner",
    "regs_header",
    "retained_v12_base_pmu_evidence",
    "retained_v12_executable_evidence",
    "runner_generated",
    "runner_record_wire_evidence",
    "v13_dwarf",
    "v13_nm",
    "v13_objdump",
    "vectors_bin",
    "vendor_generated",
    "vendor_object",
)
PMU_COMPLETION_POLL_COUNT_V13_REQUIRED_BUILD_EVIDENCE_KEYS = (
    "authoritative_v12_elf",
    "authoritative_v12_nm",
    "authoritative_v12_objdump",
    "cross_elf_evidence",
    "interface_header",
    "preprocessed_runner",
    "regs_header",
    "retained_v12_base_pmu_evidence",
    "retained_v12_executable_evidence",
    "runner_record_wire_evidence",
    "v13_dwarf",
    "v13_nm",
    "v13_objdump",
    "vendor_object",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^0x[0-9a-fA-F]{8}$")

ProtocolError = v8.ProtocolError
u32 = v12.u32


@dataclass(frozen=True)
class PmuCompletionPollCountV13Result:
    v12_result: v12.PmuCompletionPollV12Result
    poll_remaining_at_success: int

    def __getattr__(self, name):
        if name == "v12_result":
            raise AttributeError(name)
        if name == "schema_version":
            return PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION
        if name == "build_id":
            return PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID
        if name == "body_words":
            return PMU_COMPLETION_POLL_COUNT_V13_BODY_WORDS
        if name == "trailing_words":
            return 0
        return getattr(object.__getattribute__(self, "v12_result"), name)

    def _asdict(self) -> dict:
        return target_fields(self)


def target_fields(res: PmuCompletionPollCountV13Result) -> dict:
    doc = asdict(res.v12_result.base)
    doc.update(
        {
            "schema_version": PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION,
            "build_id": PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID,
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
            "poll_remaining_at_success": res.poll_remaining_at_success,
            "v13_trailing_words": res.trailing_words,
        }
    )
    return doc


def _hex_digest(doc: dict, key: str, where: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise SystemExit("FAIL %s: %s=%r is not a lowercase SHA-256" % (where, key, value))
    return value


def _hex_u32(doc: dict, key: str, where: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or HEX32.fullmatch(value) is None:
        raise SystemExit("FAIL %s: %s=%r is not 0xXXXXXXXX" % (where, key, value))
    return value


def _manifest_build_id(doc: dict) -> int | None:
    value = doc.get("build_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def _require_exact_digest_map(doc: dict, key: str, keys: tuple[str, ...], where: str) -> dict:
    value = doc.get(key)
    if not isinstance(value, dict):
        raise SystemExit("FAIL %s: %s is not an object" % (where, key))
    if tuple(sorted(value)) != tuple(sorted(keys)):
        raise SystemExit("FAIL %s: %s keys %r, expected %r" % (where, key, sorted(value), list(keys)))
    for name in keys:
        digest = value.get(name)
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise SystemExit(
                "FAIL %s: %s[%s]=%r is not a lowercase SHA-256"
                % (where, key, name, digest)
            )
    return value


def verify_manifest_identity(doc: dict, where: str) -> None:
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    if doc.get("variant") != PMU_COMPLETION_POLL_COUNT_V13_NAME:
        raise SystemExit(
            "FAIL %s: manifest variant=%r, expected %s"
            % (where, doc.get("variant"), PMU_COMPLETION_POLL_COUNT_V13_NAME)
        )
    if doc.get("schema_version") != PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d"
            % (where, doc.get("schema_version"), PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION)
        )
    if _manifest_build_id(doc) != PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID:
        raise SystemExit(
            "FAIL %s: manifest build_id %r is not the V13 identity 0x%08X"
            % (where, doc.get("build_id"), PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID)
        )
    artifacts = _require_exact_digest_map(
        doc, "artifact_sha256", PMU_COMPLETION_POLL_COUNT_V13_REQUIRED_ARTIFACT_KEYS, where
    )
    build_evidence = _require_exact_digest_map(
        doc,
        "build_evidence_sha256",
        PMU_COMPLETION_POLL_COUNT_V13_REQUIRED_BUILD_EVIDENCE_KEYS,
        where,
    )
    for key in (
        "artifact_bundle_sha256",
        "manifest_sha256",
        "parser_sha256",
        "cross_elf_evidence_sha256",
        "retained_v12_base_pmu_evidence_sha256",
        "retained_v12_executable_evidence_sha256",
        "runner_record_wire_evidence_sha256",
        "runner_source_sha256",
        "vendor_source_sha256",
        "authoritative_v12_elf_sha256",
    ):
        _hex_digest(doc, key, where)
    if doc["authoritative_v12_elf_sha256"] != artifacts["authoritative_v12_elf"]:
        raise SystemExit("FAIL %s: authoritative_v12_elf_sha256 does not bind artifact_sha256" % where)
    if doc["authoritative_v12_elf_sha256"] != build_evidence["authoritative_v12_elf"]:
        raise SystemExit("FAIL %s: authoritative_v12_elf_sha256 does not bind build_evidence_sha256" % where)
    nested_specs = (
        ("cross_elf_evidence", "cross_elf_evidence_sha256"),
        ("retained_v12_base_pmu_evidence", "retained_v12_base_pmu_evidence_sha256"),
        ("retained_v12_executable_evidence", "retained_v12_executable_evidence_sha256"),
        ("runner_record_wire_evidence", "runner_record_wire_evidence_sha256"),
    )
    for object_key, digest_key in nested_specs:
        nested = doc.get(object_key)
        if not isinstance(nested, dict):
            raise SystemExit("FAIL %s: %s is not an object" % (where, object_key))
        digest = doc[digest_key]
        if artifacts.get(object_key) != digest:
            raise SystemExit("FAIL %s: artifact_sha256[%s] != %s" % (where, object_key, digest_key))
        if build_evidence.get(object_key) != digest:
            raise SystemExit("FAIL %s: build_evidence_sha256[%s] != %s" % (where, object_key, digest_key))

    executable = doc["retained_v12_executable_evidence"]
    if executable.get("variant") not in (None, PMU_COMPLETION_POLL_COUNT_V13_NAME):
        raise SystemExit("FAIL %s: retained_v12_executable_evidence.variant drift" % where)
    if executable.get("schema_version") != PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION:
        raise SystemExit("FAIL %s: retained_v12_executable_evidence.schema_version drift" % where)
    if _manifest_build_id(executable) != PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID:
        raise SystemExit("FAIL %s: retained_v12_executable_evidence.build_id drift" % where)
    for key in (
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
    ):
        _hex_u32(executable, key, where)
    if executable.get("runtime_vector_target_symbol") != "u85_irq_handler":
        raise SystemExit("FAIL %s: runtime_vector_target_symbol drift" % where)
    if executable.get("helper_symbol") != "v13_poll_completion":
        raise SystemExit("FAIL %s: helper_symbol drift" % where)
    if executable.get("helper_completion_mask_value") != "0x00000002":
        raise SystemExit("FAIL %s: helper_completion_mask_value drift" % where)
    if executable.get("helper_status_register_address") != "0x50004004":
        raise SystemExit("FAIL %s: helper_status_register_address drift" % where)
    for key in (
        "runtime_vector_target_exact",
        "helper_call_target_exact",
        "helper_one_direct_callsite",
        "history_mask_from_success_status",
        "retained_v12_cmd_qread_ordering_exact",
        "retained_v12_hprintf_seam_exact",
        "retained_v12_nvic_hard_bypass_exact",
        "retained_v12_p0_p1_p2_exact",
        "retained_v12_status_history_provenance_exact",
        "retained_v12_stock_vector_exact",
        "retained_v12_terminal_release_exact",
        "status_success_dataflow_exact",
        "success_cmd2_count_2",
        "timeout_cmd2_count_1",
        "nvic_enable_replaced",
        "irq_triggered_true_reachable_false",
    ):
        if executable.get(key) is not True:
            raise SystemExit("FAIL %s: retained_v12_executable_evidence.%s=%r, expected true" % (where, key, executable.get(key)))

    base_pmu = doc["retained_v12_base_pmu_evidence"]
    if base_pmu.get("variant") != PMU_COMPLETION_POLL_COUNT_V13_NAME:
        raise SystemExit("FAIL %s: retained_v12_base_pmu_evidence.variant drift" % where)
    for key in (
        "golden_window_link_symbols_exact",
        "retained_v12_compiler_contract_exact",
        "retained_v12_hprintf_callsite_exact",
        "retained_v12_no_pmccntr_cfg_write",
        "retained_v12_pmu_hook_order_exact",
        "retained_v12_target_object_relocation_exact",
    ):
        if base_pmu.get(key) is not True:
            raise SystemExit("FAIL %s: retained_v12_base_pmu_evidence.%s=%r, expected true" % (where, key, base_pmu.get(key)))
    result = base_pmu.get("base_pmu_result")
    if not isinstance(result, dict) or result.get("qualification_mode") != "Q1":
        raise SystemExit("FAIL %s: retained_v12_base_pmu_evidence.base_pmu_result.qualification_mode drift" % where)
    if not isinstance(result.get("expected_return_address"), int):
        raise SystemExit("FAIL %s: retained_v12_base_pmu_evidence.base_pmu_result.expected_return_address missing" % where)

    wire = doc["runner_record_wire_evidence"]
    if wire.get("variant") != PMU_COMPLETION_POLL_COUNT_V13_NAME:
        raise SystemExit("FAIL %s: runner_record_wire_evidence.variant drift" % where)
    if wire.get("evidence_source") != "arm_elf":
        raise SystemExit("FAIL %s: runner_record_wire_evidence.evidence_source drift" % where)
    if wire.get("dwarf_required") is not True:
        raise SystemExit("FAIL %s: runner_record_wire_evidence.dwarf_required must be true" % where)
    if wire.get("poll_remaining_field_offset_bytes") != PMU_COMPLETION_POLL_COUNT_V13_REMAINING_OFFSET_BYTES:
        raise SystemExit("FAIL %s: runner_record_wire_evidence.poll_remaining_field_offset_bytes drift" % where)
    if wire.get("wire_word_index") != PMU_COMPLETION_POLL_COUNT_V13_WIRE_WORD_INDEX:
        raise SystemExit("FAIL %s: runner_record_wire_evidence.wire_word_index drift" % where)

    cross_elf = doc["cross_elf_evidence"]
    if cross_elf.get("variant") != PMU_COMPLETION_POLL_COUNT_V13_NAME:
        raise SystemExit("FAIL %s: cross_elf_evidence.variant drift" % where)
    for key in (
        "helper_leaf_no_stack_access",
        "remaining_from_back_edge_induction",
        "remaining_store_after_p2_exactly_once",
        "remaining_store_timeout_unreachable",
        "synchronized_induction_pair",
        "v12_v13_poll_loop_semantically_equivalent",
        "v13_extra_per_iteration_instruction_count_zero",
    ):
        if cross_elf.get(key) is not True:
            raise SystemExit("FAIL %s: cross_elf_evidence.%s=%r, expected true" % (where, key, cross_elf.get(key)))


def _v12_manifest_view(doc: dict) -> dict:
    executable = doc["retained_v12_executable_evidence"]
    base_pmu = doc["retained_v12_base_pmu_evidence"]
    result = base_pmu["base_pmu_result"]
    return {
        "variant": v12.PMU_COMPLETION_POLL_V12_NAME,
        "schema_version": v12.PMU_COMPLETION_POLL_V12_SCHEMA_VERSION,
        "build_id": "0x%08X" % v12.PMU_COMPLETION_POLL_V12_BUILD_ID,
        "qualification_mode": "Q1",
        "expected_return_address": result["expected_return_address"],
        "evidence_source": "arm_elf",
        "characterization_only": True,
        "not_a_performance_baseline": True,
        "not_a_latency_measurement": True,
        "generated_private_driver_diagnostic_only": True,
        "production_end_only_frozen": True,
        "diagnostic_only": True,
        "not_numerically_comparable_to_v11a": True,
        "not_latency": True,
        "not_t_npu": True,
        "not_production": True,
        "not_mlek": True,
        "artifact_sha256": {
            "APP.BIN": doc["artifact_sha256"]["app_bin"],
            "VECTORS.BIN": doc["artifact_sha256"]["vectors_bin"],
            "DDR.BIN": doc["artifact_sha256"]["ddr_bin"],
        },
        "build_evidence_sha256": {
            "runner_pmu_completion_poll_v12.elf": doc["build_evidence_sha256"]["authoritative_v12_elf"],
            "runner_pmu_completion_poll_v12.map": doc["artifact_sha256"]["map"],
            "generated_runner.c": doc["artifact_sha256"]["runner_generated"],
            "generated_vendor_u85.c": doc["artifact_sha256"]["vendor_generated"],
            "checker_disassembly.txt": doc["artifact_sha256"]["authoritative_v12_objdump"],
            "checker_nm.txt": doc["artifact_sha256"]["authoritative_v12_nm"],
        },
        "helper_symbol": "v12_poll_completion",
        "runtime_vector_target_symbol": executable["runtime_vector_target_symbol"],
        "runtime_vector_target_address": executable["runtime_vector_target_address"],
        "wait_call_address": executable["wait_call_address"],
        "hprintf_callsite_address": executable["hprintf_callsite_address"],
        "helper_status_read_address": executable["helper_status_read_address"],
        "helper_status_test_address": executable["helper_status_test_address"],
        "poll_helper_p0_address": executable["poll_helper_p0_address"],
        "poll_helper_p1_address": executable["poll_helper_p1_address"],
        "poll_helper_p2_address": executable["poll_helper_p2_address"],
        "success_cmd2_1_store_address": executable["success_cmd2_1_store_address"],
        "success_qread_load_address": executable["success_qread_load_address"],
        "success_cmd2_2_store_address": executable["success_cmd2_2_store_address"],
        "timeout_qread_load_address": executable["timeout_qread_load_address"],
        "timeout_cmd2_store_address": executable["timeout_cmd2_store_address"],
        "cmd0_store_address": executable["cmd0_store_address"],
        "terminal_cmd0c_store_address": executable["terminal_cmd0c_store_address"],
    }


def _v12_payload_view(payload: bytes) -> bytes:
    v12_payload = bytearray(payload)
    struct.pack_into("<I", v12_payload, 4, v12.PMU_COMPLETION_POLL_V12_SCHEMA_VERSION)
    struct.pack_into("<I", v12_payload, 8, v12.PMU_COMPLETION_POLL_V12_TOTAL_WORDS)
    struct.pack_into("<I", v12_payload, PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS * 4, v12.PMU_COMPLETION_POLL_V12_SCHEMA_VERSION)
    struct.pack_into("<I", v12_payload, (PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS + 1) * 4, v12.PMU_COMPLETION_POLL_V12_BUILD_ID)
    del v12_payload[-4:]
    v12_crc = zlib.crc32(bytes(v12_payload[16:28]) + bytes(v12_payload[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", v12_payload, 28, v12_crc)
    return bytes(v12_payload)


def parse_pmu_completion_poll_count_v13_payload(payload: bytes) -> PmuCompletionPollCountV13Result:
    if len(payload) < PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS * 4:
        raise ProtocolError("v13 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_COMPLETION_POLL_COUNT_V13_MAGIC:
        raise ProtocolError("bad PMU_COMPLETION_POLL_COUNT_V13 magic 0x%08X" % magic)
    if version != PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION:
        raise ProtocolError("unsupported PMU_COMPLETION_POLL_COUNT_V13 schema version %d" % version)
    if header_words != PMU_COMPLETION_POLL_COUNT_V13_HEADER_WORDS:
        raise ProtocolError("unexpected PMU_COMPLETION_POLL_COUNT_V13 header_words %d" % header_words)
    if total_words != PMU_COMPLETION_POLL_COUNT_V13_TOTAL_WORDS:
        raise ProtocolError(
            "total_payload_words %d does not equal the v13 contract %d"
            % (total_words, PMU_COMPLETION_POLL_COUNT_V13_TOTAL_WORDS)
        )
    if total_words * 4 != len(payload):
        raise ProtocolError("declared %d bytes, frame carried %d" % (total_words * 4, len(payload)))
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("PMU_COMPLETION_POLL_COUNT_V13 payload CRC mismatch")
    body = struct.unpack_from("<%dI" % (total_words - header_words), payload, header_words * 4)
    if body[0] != version:
        raise ProtocolError(
            "PMU_COMPLETION_POLL_COUNT_V13 body schema_version %d != header %d"
            % (body[0], version)
        )
    if body[1] != PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID:
        raise ProtocolError(
            "PMU_COMPLETION_POLL_COUNT_V13 body build_id 0x%08X != V13 identity 0x%08X"
            % (body[1], PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID)
        )
    v12_result = v12.parse_pmu_completion_poll_v12_payload(_v12_payload_view(payload))
    if (seq, flags, rc) != (
        v12_result.run_sequence,
        v12_result.valid_flags,
        v12_result.run_rc,
    ):
        raise ProtocolError("PMU_COMPLETION_POLL_COUNT_V13 header/body disagree on seq/flags/rc")
    return PmuCompletionPollCountV13Result(
        v12_result=v12_result,
        poll_remaining_at_success=body[v8.PMU_QUAL_KNOWN_FIELDS + 15],
    )


def classify_pmu_completion_poll_count_v13_payload(
    res: PmuCompletionPollCountV13Result, expected_manifest: dict
) -> dict:
    verify_manifest_identity(expected_manifest, "<manifest>")
    retained_v12 = v12.classify_pmu_completion_poll_v12_payload(
        res.v12_result, _v12_manifest_view(expected_manifest)
    )
    terms = {"retained_v12_%s" % key: value for key, value in retained_v12["terms"].items()}
    success = res.poll_result == PMU_COMPLETION_POLL_COUNT_V13_POLL_SUCCESS
    timeout = res.poll_result == PMU_COMPLETION_POLL_COUNT_V13_POLL_TIMEOUT
    remaining = res.poll_remaining_at_success
    poll_cycles = u32(res.t_status_completion_seen - res.t_poll_entry) if success else None
    remaining_valid = (
        PMU_COMPLETION_POLL_COUNT_V13_MIN_REMAINING
        <= remaining
        <= PMU_COMPLETION_POLL_COUNT_V13_MAX_REMAINING
    )
    iterations = 10001 - remaining if remaining_valid else None
    terms.update(
        {
            "manifest_variant_matches": expected_manifest.get("variant") == PMU_COMPLETION_POLL_COUNT_V13_NAME,
            "manifest_schema_matches": expected_manifest.get("schema_version") == PMU_COMPLETION_POLL_COUNT_V13_SCHEMA_VERSION,
            "manifest_build_id_matches": _manifest_build_id(expected_manifest) == PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID,
            "build_id_is_v13": res.build_id == PMU_COMPLETION_POLL_COUNT_V13_BUILD_ID,
            "poll_result_known": success or timeout,
        }
    )
    if success:
        terms.update(
            {
                "remaining_nonzero_on_success": remaining != PMU_COMPLETION_POLL_COUNT_V13_POLL_REMAINING_INVALID,
                "remaining_in_range_on_success": remaining_valid,
                "iterations_derived_in_range": iterations is not None and 1 <= iterations <= 10000,
                "poll_observation_cycles_positive_half_range": 0 < poll_cycles < 0x80000000,
            }
        )
    else:
        terms.update(
            {
                "remaining_invalid_on_timeout": remaining == PMU_COMPLETION_POLL_COUNT_V13_POLL_REMAINING_INVALID,
            }
        )
    valid = all(terms.values()) and success
    derived = None
    if valid:
        derived = dict(retained_v12["derived"])
        derived.update(
            {
                "poll_remaining_at_success": remaining,
                "poll_iterations": iterations,
                "poll_observation_cycles": poll_cycles,
                "average_cycles_per_observed_poll": poll_cycles / iterations,
            }
        )
    return {
        "terms": terms,
        "invalid_reasons": sorted(key for key, ok in terms.items() if not ok),
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
        "retained_v12": retained_v12,
        "vector_identity": retained_v12["vector_identity"],
        "deltas_u32": dict(retained_v12["deltas_u32"]),
        "valid": valid,
    }
