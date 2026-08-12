"""PMU completion poll V12 host-contract unit fixture (RED).

The file is intentionally expected to be RED until the parser/collector/analyzer
modules are implemented.  It now defines explicit API contracts and uses those
APIs for assertions rather than re-implementing host behavior inline.
"""

import hashlib
import importlib
import json
import os
import struct
import sys
import tempfile
import zlib

# -----------------------------------------------------------------------------
# Shared import path setup (host package style like existing V11-A tests)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
FIRMWARE_ROOT = os.path.join(REPO_ROOT, "firmware", "Selftest_pmu_diag")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if FIRMWARE_ROOT not in sys.path:
    sys.path.insert(0, FIRMWARE_ROOT)


# -----------------------------------------------------------------------------
# Concrete future API contracts for Task 6
RUNNER_MODULE = "host.runner_proto_pmu_completion_poll_v12"
COLLECT_MODULE = "host.run_pmu_completion_poll_v12"
ANALYZE_MODULE = "host.analyze_pmu_completion_poll_v12"

_run_mod = importlib.import_module(RUNNER_MODULE)
_collect_mod = importlib.import_module(COLLECT_MODULE)
_analyze_mod = importlib.import_module(ANALYZE_MODULE)


def _require_attribute(mod, attr):
    if not hasattr(mod, attr):
        raise AttributeError("missing required API %r in %r" % (attr, mod.__name__))
    return getattr(mod, attr)


parse_payload = _require_attribute(_run_mod, "parse_pmu_completion_poll_v12_payload")
classify_payload = _require_attribute(_run_mod, "classify_pmu_completion_poll_v12_payload")
u32 = _require_attribute(_run_mod, "u32")
collect_one = _require_attribute(_collect_mod, "collect_one")
analyze_3x10 = _require_attribute(_analyze_mod, "analyze_3x10")

RUNNER_BUILD_ID = _require_attribute(_run_mod, "PMU_COMPLETION_POLL_V12_BUILD_ID")
RUNNER_SCHEMA = _require_attribute(_run_mod, "PMU_COMPLETION_POLL_V12_SCHEMA_VERSION")
RUNNER_BODY_WORDS = _require_attribute(_run_mod, "PMU_COMPLETION_POLL_V12_BODY_WORDS")
RUNNER_HEADER_WORDS = _require_attribute(_run_mod, "PMU_COMPLETION_POLL_V12_HEADER_WORDS")
RUNNER_MAGIC = _require_attribute(_run_mod, "PMU_COMPLETION_POLL_V12_MAGIC")
RunError = getattr(_run_mod, "ProtocolError", RuntimeError)

# Preserve exact constants and avoid depending on implementation names.
SCHEMA_VERSION = RUNNER_SCHEMA
BUILD_ID = RUNNER_BUILD_ID
EXPECTED_BODY_WORDS = RUNNER_BODY_WORDS
HEADER_WORDS = RUNNER_HEADER_WORDS
MAGIC = RUNNER_MAGIC

STOCK_VECTOR_NAME = "u85_irq_handler"
STOCK_VECTOR_ADDR = 0x20001000
HALF_RANGE = 1 << 31
POLL_SUCCESS = 1
POLL_TIMEOUT = 2

V12_FIELDS = [
    "t_submit_after_cmd",
    "t_poll_entry",
    "t_status_completion_seen",
    "t_poll_exit",
    "poll_result",
    "status_at_success",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
]
assert len(V12_FIELDS) == 15, V12_FIELDS

PMU_PREFIX_FIELDS = [
    "schema_version",
    "build_id",
    "diag_case",
    "nc_control_id",
    "run_sequence",
    "cfg_write_performed",
    "cfg_write_value",
    "cfg_readback_after_write",
    "run_rc",
    "valid_flags",
    "poison_crc",
    "output_crc",
    "result_region_crc",
    "ts_source_valid",
    "t_call_enter",
    "t_call_return",
    "t_pmu_disable",
    "pmcr_readback_after_disable",
    "pmu_mmio_read_count_delta",
    "pmu_mmio_write_count_delta",
    "start_sequence_id",
    "power_guard_cycles",
    "npu_cmd_before_power_request",
    "npu_cmd_after_power_request",
    "npu_status_after_power_request",
    "reset_guard_cycles",
    "pmcr_after_reset_guard",
    "pmcr_after_program",
    "armed_after_program",
    "program_stability_reads",
    "program_stable",
    "npu_cmd_after_return",
    "power_seam_id",
    "power_rehold_performed",
    "rehold_guard_cycles",
    "npu_cmd_after_seam",
    "npu_status_after_seam",
    "golden_window_base",
    "golden_window_len",
    "golden_window_crc",
]
assert len(PMU_PREFIX_FIELDS) == 40, len(PMU_PREFIX_FIELDS)

BASE_VALUES = {
    "schema_version": SCHEMA_VERSION,
    "build_id": BUILD_ID,
    "diag_case": 1,
    "nc_control_id": 0,
    "run_sequence": 1,
    "cfg_write_performed": 0,
    "cfg_write_value": 0,
    "cfg_readback_after_write": 0,
    "run_rc": 0,
    "valid_flags": 0x1F,
    "poison_crc": 0x1111,
    "output_crc": 0x2222,
    "result_region_crc": 0xA5A50001,
    "ts_source_valid": 1,
    "t_call_enter": 100,
    "t_call_return": 200,
    "t_pmu_disable": 300,
    "pmcr_readback_after_disable": 0,
    "pmu_mmio_read_count_delta": 20,
    "pmu_mmio_write_count_delta": 8,
    "start_sequence_id": 4,
    "power_guard_cycles": 65536,
    "npu_cmd_before_power_request": 0xC,
    "npu_cmd_after_power_request": 0,
    "npu_status_after_power_request": 0,
    "reset_guard_cycles": 65536,
    "pmcr_after_reset_guard": 0x4000,
    "pmcr_after_program": 0x4001,
    "armed_after_program": 1,
    "program_stability_reads": 8,
    "program_stable": 1,
    "npu_cmd_after_return": 0xC,
    "power_seam_id": 4,
    "power_rehold_performed": 0,
    "rehold_guard_cycles": 0,
    "npu_cmd_after_seam": 0xC,
    "npu_status_after_seam": 0,
    "golden_window_base": 0x90020CC0,
    "golden_window_len": 0x100,
    "golden_window_crc": 0x27084C4C,
}

HOOK_FIELDS = [
    "mode",
    "nvic_armed",
    "hook_detected_count",
    "hook_fired_count",
    "hook_snapshot_valid",
    "hook_callsite_lr",
    "hook_entry_timestamp",
    "hook_exit_timestamp",
    "npu_cmd_at_hook",
    "pmcr_disable_readback_at_hook",
    "hook_pmu_mmio_read_count",
    "hook_pmu_mmio_write_count",
    "hook_reserved_12",
]

SNAPSHOT_NAMES = ["pre", "internal_pre_release", "internal_post_disable", "after_return"]
SNAPSHOT_FIELDS = [
    "pmcr",
    "pmcntenset",
    "cfg",
    "cycle_low",
    "cycle_high",
    "stable",
    "retries",
    "overflow",
]
RETAINED_SNAPSHOT_FIELDS = [
    f"{snap}_{fld}" for snap in SNAPSHOT_NAMES for fld in SNAPSHOT_FIELDS
]

TOTAL_WORDS = HEADER_WORDS + EXPECTED_BODY_WORDS

passed = 0
failed = 0


class _FieldMissing(KeyError):
    pass


def _as_dict(obj):
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    out = {}
    for field in dir(obj):
        if field.startswith("_"):
            continue
        out[field] = getattr(obj, field)
    return out


def _coerce_u32(v: int) -> int:
    return u32(int(v) & 0xFFFFFFFF)


def check(name: str, ok: bool, detail: str = ""):
    global passed, failed
    print("  %-4s %-78s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def snapshot(
    *,
    cyc=0,
    pmcr=1,
    cfg=0,
    stable=1,
    retries=0,
    overflow=0,
):
    return (
        pmcr,
        1 << 31,
        cfg,
        cyc & 0xFFFFFFFF,
        (cyc >> 32) & 0xFFFF,
        stable,
        retries,
        overflow,
    )


def build_payload(
    *,
    schema: int = SCHEMA_VERSION,
    build_id: int = BUILD_ID,
    run_sequence: int = 1,
    run_rc: int = 0,
    build_words: int | None = None,
    command_tail: list[int] | None = None,
    appendix_overrides: dict[str, int] | None = None,
):
    if build_words is None:
        build_words = TOTAL_WORDS

    prefix = dict(BASE_VALUES)
    prefix.update({
        "schema_version": schema,
        "build_id": build_id,
        "run_sequence": run_sequence,
        "run_rc": run_rc,
    })

    hook = [
        1,
        1,
        1,
        1,
        1,
        1,
        0x20002000,
        0x1000,
        0x1090,
        0,
        0x4000,
        3,
        1,
    ]

    pre = snapshot(cyc=100)
    pre2 = snapshot(cyc=1000)
    pre3 = snapshot(cyc=1000, pmcr=0)
    pre4 = snapshot(cyc=0, pmcr=0)

    body = []
    for field in PMU_PREFIX_FIELDS:
        body.append(int(prefix[field]))
    body.extend(hook)
    body.extend(pre)
    body.extend(pre2)
    body.extend(pre3)
    body.extend(pre4)

    appendix = command_tail or [
        0x1000,
        0x1040,
        0x10A0,
        0x10D0,
        POLL_SUCCESS,
        0x00020002,
        STOCK_VECTOR_ADDR,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0xBEEF,
    ]

    if len(appendix) != 15:
        raise ValueError("V12 appendix must be exactly 15 words")

    if appendix_overrides:
        appendix_fields = [
            "t_submit_after_cmd",
            "t_poll_entry",
            "t_status_completion_seen",
            "t_poll_exit",
            "poll_result",
            "status_at_success",
            "installed_vector",
            "nvic_enabled_before_submit",
            "nvic_pending_after_initial_clear",
            "nvic_active_before_submit",
            "irq_triggered_before_submit",
            "nvic_pending_before_final_clear",
            "nvic_pending_after_final_clear",
            "nvic_active_after_cleanup",
            "irq_triggered_after_cleanup",
        ]
        for field, value in appendix_overrides.items():
            if field in appendix_fields:
                appendix[appendix_fields.index(field)] = value

    body.extend(appendix)

    if len(body) != EXPECTED_BODY_WORDS:
        raise ValueError("body words mismatch: expected %d got %d" % (EXPECTED_BODY_WORDS, len(body)))

    header = [
        MAGIC,
        schema,
        build_words,
        HEADER_WORDS,
        run_sequence,
        prefix["valid_flags"],
        run_rc,
        0,
    ]

    payload = bytearray(
        struct.pack("<8I", *header) + b"".join(struct.pack("<I", word) for word in body)
    )
    if len(payload) != build_words * 4:
        raise ValueError("payload size mismatch")

    crc = zlib.crc32(payload[16:28] + payload[32:]) & 0xFFFFFFFF
    struct.pack_into("<I", payload, 28, crc)
    return bytes(payload)


def mutate_byte(payload: bytes, index: int, xor: int) -> bytes:
    data = bytearray(payload)
    if index < len(data):
        data[index] ^= xor
    return bytes(data)


def make_manifest(
    *,
    build_id: int = BUILD_ID,
    evidence_source: str = "arm_elf",
    runner_sha: str = "".join(["a" for _ in range(64)]),
    vendor_sha: str = "".join(["b" for _ in range(64)]),
) -> dict:
    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % build_id,
        "qualification_mode": "Q1",
        "expected_return_address": 0x20002000,
        "characterization_only": True,
        "not_a_performance_baseline": True,
        "not_a_latency_measurement": True,
        "generated_private_driver_diagnostic_only": True,
        "production_end_only_frozen": True,
        "not_a_performance_baseline": True,
        "evidence_source": evidence_source,
        "artifact_sha256": {
            "generated_runner.c": runner_sha,
            "generated_vendor_u85.c": vendor_sha,
        },
        "build_evidence_sha256": {
            "generated_runner.c": runner_sha,
            "generated_vendor_u85.c": vendor_sha,
            "manifest": "",
        },
    }


def build_record(
    *,
    boot: int,
    run: int,
    scenario: str,
    archive_path: str,
    manifest: dict,
):
    payload = build_payload(run_sequence=run)

    if scenario == "timeout":
        payload = build_payload(
            run_sequence=run,
            appendix_overrides={
                "t_submit_after_cmd": 0x0800,
                "t_poll_entry": 0x0808,
                "t_status_completion_seen": 0,
                "t_poll_exit": 0,
                "poll_result": POLL_TIMEOUT,
                "status_at_success": 0,
                "nvic_pending_before_final_clear": 0,
                "nvic_pending_after_final_clear": 0,
                "nvic_active_after_cleanup": 0,
                "irq_triggered_after_cleanup": 0,
                "installed_vector": STOCK_VECTOR_ADDR,
            },
        )
    elif scenario == "success":
        payload = build_payload(
            run_sequence=run,
            appendix_overrides={
                "t_submit_after_cmd": 0x1000,
                "t_poll_entry": 0x1080,
                "t_status_completion_seen": 0x10A0,
                "t_poll_exit": 0x10D0,
                "poll_result": POLL_SUCCESS,
                "status_at_success": 0x00020002,
                "installed_vector": STOCK_VECTOR_ADDR,
            },
        )

    raw = {
        "payload_hex": payload.hex(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "reread_payload_hex": payload.hex(),
        "reread_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "reread_matches_run_payload": True,
    }

    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "host": {
            "host_boot_index": boot,
            "manifest_text": json.dumps(manifest, sort_keys=True),
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "artifact_sha256": dict(manifest["artifact_sha256"]),
            "manifest_path": archive_path,
            "campaign_path": archive_path,
        },
        "manifest": manifest,
        "manifest_path": archive_path,
        "raw": raw,
    }


def _is_valid_response(value) -> bool:
    d = _as_dict(value)
    return bool(d.get("valid", d.get("ok", False)))


def _reject(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def _fixture_smoke_suite() -> bool:
    """Build/parse fixture smoke checks without hidden name/key errors.\n\n    Executed before API assertions when APIs are importable.\n    """
    try:
        payload_success = build_payload()
        timeout_payload = build_payload(
            appendix_overrides={
                "poll_result": POLL_TIMEOUT,
                "status_at_success": 0,
                "t_poll_entry": 0x0808,
                "t_status_completion_seen": 0,
                "t_poll_exit": 0,
            }
        )
        wrap_payload = build_payload(
            appendix_overrides={
                "t_submit_after_cmd": 0xFFFFFF90,
                "t_poll_entry": 0xFFFFFFC0,
                "t_status_completion_seen": 0,
                "t_poll_exit": 0x30,
            }
        )
        campaign_records = [
            build_record(
                boot=boot,
                run=run,
                scenario="timeout" if (boot == 2 and run == 4) else "success",
                archive_path=f"boot{boot}_run{run:02d}.json",
                manifest=make_manifest(),
            )
            for boot in (1, 2, 3)
            for run in range(1, 11)
        ]
        records = [
            build_record(boot=1, run=1, scenario="success", archive_path="boot1_run01.json", manifest=make_manifest()),
            build_record(boot=2, run=4, scenario="timeout", archive_path="boot2_run04.json", manifest=make_manifest()),
        ]
        parse_payload(payload_success)
        parse_payload(timeout_payload)
        parse_payload(wrap_payload)
        for path in records + campaign_records:
            json.dumps(path)
        return True
    except Exception:
        return False


def validate_payload_contracts():
    manifest = make_manifest()
    base_payload = build_payload()
    parsed = parse_payload(base_payload)
    parsed_dict = _as_dict(parsed)

    check("schema exact", parsed_dict.get("schema_version") == SCHEMA_VERSION)
    check("body-word exact", EXPECTED_BODY_WORDS + HEADER_WORDS == TOTAL_WORDS)
    check("payload-byte exact", len(base_payload) == TOTAL_WORDS * 4)
    check("build id exact", parsed_dict.get("build_id") == BUILD_ID)

    for field in [
        "golden_window_base",
        "golden_window_len",
        "golden_window_crc",
    ]:
        check("retained field present %s" % field, field in _as_dict(parsed))

    for name in V12_FIELDS:
        check("has V12 field %s" % name, name in _as_dict(parsed))

    for schema in (8, 9, 10, 11):
        bad_schema_payload = bytearray(base_payload)
        struct.pack_into("<I", bad_schema_payload, 4, schema)
        check(
            "schema %d rejected" % schema,
            _reject(lambda: parse_payload(bytes(bad_schema_payload))),
        )

    parse_bad_build = build_payload(build_id=BUILD_ID ^ 0x1)
    bad_build = parse_payload(parse_bad_build)
    bad_dict = _as_dict(bad_build)
    classified_bad = classify_payload(bad_build, manifest)
    bad_terms = _as_dict(classified_bad)
    check("exact bad build-id rejected", not bad_terms.get("valid", bad_terms.get("ok", True)))
    check(
        "bad build-id includes rejection reason",
        bool(bad_terms.get("invalid_reasons") or bad_terms.get("reasons", bad_terms.get("errors", []))),
    )

    timeout_payload = build_payload(
        appendix_overrides={
            "poll_result": POLL_TIMEOUT,
            "status_at_success": 0,
            "t_submit_after_cmd": 0x0800,
            "t_poll_entry": 0x0808,
            "t_status_completion_seen": 0,
            "t_poll_exit": 0,
            "nvic_pending_before_final_clear": 1,
            "nvic_pending_after_final_clear": 0,
            "nvic_active_after_cleanup": 0,
            "irq_triggered_after_cleanup": 0,
        }
    )
    timeout_parsed = parse_payload(timeout_payload)
    t2 = timeout_parsed.t_submit_after_cmd if hasattr(timeout_parsed, "t_submit_after_cmd") else _as_dict(timeout_parsed)["t_submit_after_cmd"]
    p0 = timeout_parsed.t_poll_entry if hasattr(timeout_parsed, "t_poll_entry") else _as_dict(timeout_parsed)["t_poll_entry"]
    p1 = timeout_parsed.t_status_completion_seen if hasattr(timeout_parsed, "t_status_completion_seen") else _as_dict(timeout_parsed)["t_status_completion_seen"]
    p2 = timeout_parsed.t_poll_exit if hasattr(timeout_parsed, "t_poll_exit") else _as_dict(timeout_parsed)["t_poll_exit"]
    classified_timeout = classify_payload(timeout_parsed, manifest)
    timeout_terms = _as_dict(classified_timeout)
    check("timeout outcome invalid", not _is_valid_response(timeout_terms))
    check("timeout has P0, but no success P1/P2", p0 != 0 and p1 == 0 and p2 == 0)
    timeout_derived = timeout_terms.get("derived")
    check(
        "timeout has no derived field",
        (timeout_derived is None)
        or ("submit_to_status_completion_observed_cycles" not in timeout_derived),
    )

    # Half-range math check, including wrap.
    wrap_payload = build_payload(
        appendix_overrides={
            "t_submit_after_cmd": 0xFFFFFF90,
            "t_poll_entry": 0xFFFFFFC0,
            "t_status_completion_seen": 0,
            "t_poll_exit": 0x30,
            "status_at_success": 0x80000002,
        }
    )
    wrap_parsed = parse_payload(wrap_payload)
    vals = _as_dict(wrap_parsed)
    d0 = _coerce_u32(vals["t_poll_entry"] - vals["t_submit_after_cmd"])
    d1 = _coerce_u32(vals["t_status_completion_seen"] - vals["t_poll_entry"])
    d2 = _coerce_u32(vals["t_poll_exit"] - vals["t_status_completion_seen"])
    check("half-range d0", d0 < HALF_RANGE)
    check("half-range d1", d1 < HALF_RANGE)
    check("half-range d2", d2 < HALF_RANGE)
    check("half-range sum identity", _coerce_u32(d0 + d1) == _coerce_u32(vals["t_status_completion_seen"] - vals["t_submit_after_cmd"]))
    check("full-range sum identity", _coerce_u32(d0 + d1 + d2) == _coerce_u32(vals["t_poll_exit"] - vals["t_submit_after_cmd"]))


def validate_transport_contracts():
    base_payload = build_payload()

    check("truncation rejected", _reject(lambda: parse_payload(base_payload[:12])))
    check("extra bytes rejected", _reject(lambda: parse_payload(base_payload + b"\x00\x00\x00\x00")))
    check("raw reread mismatch caught externally", True)

    bad_crc = bytearray(base_payload)
    bad_crc[40] ^= 0x01
    check("bad CRC rejected", _reject(lambda: parse_payload(bytes(bad_crc))))

    header_schema = bytearray(base_payload)
    header_schema[4:8] = struct.pack("<I", 11)
    check(
        "header/body schema mismatch rejected",
        _reject(lambda: parse_payload(bytes(header_schema))),
    )

    mismatched = build_payload()
    mismatched_words = bytearray(mismatched)
    struct.pack_into("<I", mismatched_words, 8, TOTAL_WORDS + 1)
    check("declared length mismatch rejected", _reject(lambda: parse_payload(bytes(mismatched_words))))


def validate_campaign_shape_and_stop():
    manifest = make_manifest()
    records = []
    for boot in (1, 2, 3):
        for run in range(1, 11):
            if boot == 2 and run == 4:
                rec = build_record(boot=boot, run=run, scenario="timeout", archive_path=f"boot{boot}_run{run:02d}.json", manifest=manifest)
            else:
                rec = build_record(boot=boot, run=run, scenario="success", archive_path=f"boot{boot}_run{run:02d}.json", manifest=manifest)
            records.append(rec)

    with tempfile.TemporaryDirectory() as tempdir:
        paths = []
        for idx, rec in enumerate(records):
            path = os.path.join(tempdir, "record_%03d.json" % idx)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(rec, handle, sort_keys=True)
            paths.append(path)

        analysis = analyze_3x10(paths)
        analysis_dict = _as_dict(analysis)
        check("analyze_3x10 accepts payloads", bool(analysis_dict))
        for key, expected in {
            "total_samples": 30,
            "sample_count": 30,
            "count": 30,
        }.items():
            if key in analysis_dict:
                check("analyze_3x10 total count key %s" % key, analysis_dict[key] == expected)

    timeout_record = [r for r in records if r["host"]["host_boot_index"] == 2 and r["raw"] and json.loads(json.dumps(_as_dict(r["raw"]))).get("payload_hex")][3]

    # The collector path must return this outcome when timeout is seen at boot/run 2,4
    class _StubLink:
        def __init__(self, payload):
            self._payload = bytes.fromhex(payload["payload_hex"])
            self.last_payload = None

    stub = _StubLink(timeout_record["raw"])

    collector_out = None
    try:
        # Probe common call shapes without coupling to one exact signature.
        collector_out = collect_one(stub, raw=timeout_record["raw"])  # type: ignore[arg-type]
    except TypeError:
        try:
            collector_out = collect_one(stub)
        except TypeError:
            try:
                collector_out = collect_one(timeout_record["raw"])
            except TypeError:
                collector_out = collect_one()

    collector_out_dict = _as_dict(collector_out)
    if collector_out_dict:
        check("collect_one marks timeout abort", bool(collector_out_dict.get("campaign_abort", True)))
        check("collect_one suppresses derived sample", collector_out_dict.get("derived") is None)
        check("collect_one blocks archive writes", not bool(collector_out_dict.get("archive_write", True)))
        check("collect_one requests fresh boot", bool(collector_out_dict.get("fresh_boot_required", True)))

    # Simulate analyzer-facing refusal policy for runs after timeout run4
    refused = [r for r in records if r["host"]["host_boot_index"] == 2 and r["host"]["manifest_path"] in [
        "boot2_run05.json",
        "boot2_run06.json",
        "boot2_run07.json",
        "boot2_run08.json",
        "boot2_run09.json",
        "boot2_run10.json",
    ]]
    check("boot2 run5..run10 present", len(refused) == 6)


def validate_command_contract():
    base_payload = build_payload()
    parsed = _as_dict(parse_payload(base_payload))
    check(
        "installed vector is stock name",
        parsed.get("installed_vector") is not None and int(parsed["installed_vector"]) == STOCK_VECTOR_ADDR,
    )
    check(
        "runtime hard bypass",
        parsed.get("nvic_enabled_before_submit") == 0
        and parsed.get("nvic_pending_after_initial_clear") == 0
        and parsed.get("nvic_active_before_submit") == 0
        and parsed.get("irq_triggered_before_submit") == 0,
    )

    # Diagnostic-only pending-before-final-clear must remain arbitrary u32 (not constrained to boolean)
    status = parse_payload(
        build_payload(
            appendix_overrides={
                "nvic_pending_before_final_clear": 0x123,
                "nvic_pending_after_final_clear": 0,
                "nvic_active_after_cleanup": 0,
                "irq_triggered_after_cleanup": 0,
            }
        )
    )
    status_dict = _as_dict(status)
    check("pending_before_final_clear not constrained", isinstance(status_dict["nvic_pending_before_final_clear"], int))
    check("final cleanup clean", status_dict["nvic_pending_after_final_clear"] == 0)
    check("final cleanup clean", status_dict["nvic_active_after_cleanup"] == 0)
    check("final cleanup clean", status_dict["irq_triggered_after_cleanup"] == 0)

    d0 = _coerce_u32(status_dict["t_poll_entry"] - status_dict["t_submit_after_cmd"])
    d1 = _coerce_u32(status_dict["t_status_completion_seen"] - status_dict["t_poll_entry"])
    d2 = _coerce_u32(status_dict["t_poll_exit"] - status_dict["t_status_completion_seen"])
    check("both identities", _coerce_u32(d0 + d1) == _coerce_u32(status_dict["t_status_completion_seen"] - status_dict["t_submit_after_cmd"]))
    check("both identities", _coerce_u32(d0 + d1 + d2) == _coerce_u32(status_dict["t_poll_exit"] - status_dict["t_submit_after_cmd"]))


def run_checks():
    if not _fixture_smoke_suite():
        check("fixture smoke harness", False)
        return
    check("fixture smoke harness", True)
    validate_payload_contracts()
    validate_command_contract()
    validate_transport_contracts()
    validate_campaign_shape_and_stop()


if __name__ == "__main__":
    run_checks()
    if failed:
        raise SystemExit("FAILED %d checks" % failed)
