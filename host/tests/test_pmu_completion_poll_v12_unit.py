"""PMU completion poll V12 host-contract unit fixture (RED).

This module is a standalone stdlib-only contract harness.  All internal
assertions are intended to pass; after they run it imports an absent V12 host
module so the test file itself still REDs until module ownership is added.
"""

import hashlib
import struct
import zlib

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = ""):
    global passed, failed
    print("  %-4s %-70s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


class ProtocolError(RuntimeError):
    pass


SCHEMA_VERSION = 12
BUILD_ID = 0x32314950
MAGIC = 0x4B4D5A5A
HEADER_WORDS = 8
TOTAL_WORDS = 108
BODY_WORDS = 100
PAYLOAD_SIZE = 432
PREFIX_WORDS = 40
HOOK_WORDS = 13
SNAPSHOT_WORDS = 8
SNAPSHOT_COUNT = 4
HALF_RANGE = 1 << 31
POLL_SUCCESS = 1
POLL_TIMEOUT = 2
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
STOCK_VECTOR_NAME = "u85_irq_handler"
STOCK_VECTOR_ADDR = 0x20001000

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
assert len(V12_FIELDS) == 15, len(V12_FIELDS)


PREFIX_FIELDS = [
    "prefix_00",
    "prefix_01",
    "prefix_02",
    "prefix_03",
    "prefix_04",
    "prefix_05",
    "prefix_06",
    "prefix_07",
    "prefix_08",
    "prefix_09",
    "prefix_10",
    "prefix_11",
    "prefix_12",
    "prefix_13",
    "prefix_14",
    "prefix_15",
    "prefix_16",
    "prefix_17",
    "prefix_18",
    "prefix_19",
    "prefix_20",
    "prefix_21",
    "prefix_22",
    "prefix_23",
    "prefix_24",
    "prefix_25",
    "prefix_26",
    "prefix_27",
    "prefix_28",
    "prefix_29",
    "prefix_30",
    "prefix_31",
    "prefix_32",
    "prefix_33",
    "pmu_golden_window_base",
    "pmu_golden_window_len",
    "pmu_golden_window_crc",
    "prefix_34",
    "prefix_35",
    "prefix_36",
    "prefix_37",
    "prefix_38",
    "prefix_39",
]

PREFIX_FIELDS[0] = "schema_version"
PREFIX_FIELDS[1] = "build_id"
PREFIX_FIELDS[2] = "diag_case"
PREFIX_FIELDS[3] = "nc_control_id"
PREFIX_FIELDS[4] = "run_sequence"
PREFIX_FIELDS[5] = "cfg_written"
PREFIX_FIELDS[6] = "cfg_value"
PREFIX_FIELDS[7] = "cfg_readback"
PREFIX_FIELDS[8] = "run_return_code"
PREFIX_FIELDS[9] = "valid_flags"
PREFIX_FIELDS[10] = "ts_source_valid"
PREFIX_FIELDS[11] = "mmio_reads"
PREFIX_FIELDS[12] = "mmio_writes"
PREFIX_FIELDS[13] = "power_sequence_id"
PREFIX_FIELDS[14] = "power_guard_cycles"
PREFIX_FIELDS[15] = "cmd_after_submit"
PREFIX_FIELDS[16] = "status_after_submit"
PREFIX_FIELDS[17] = "reset_guard_cycles"
PREFIX_FIELDS[18] = "pmcr_guard"
PREFIX_FIELDS[19] = "pmcr_program"
PREFIX_FIELDS[20] = "arm_program"
PREFIX_FIELDS[21] = "stability_samples"
PREFIX_FIELDS[22] = "program_stable"
PREFIX_FIELDS[23] = "cmd_after_return"
PREFIX_FIELDS[24] = "status_after_return"
PREFIX_FIELDS[25] = "power_seam_id"
PREFIX_FIELDS[26] = "power_rehold_performed"
PREFIX_FIELDS[27] = "rehold_guard_cycles"
PREFIX_FIELDS[28] = "cmd_after_rehold"
PREFIX_FIELDS[29] = "status_after_rehold"
PREFIX_FIELDS[30] = "reserved_30"
PREFIX_FIELDS[31] = "reserved_31"
PREFIX_FIELDS[32] = "reserved_32"
PREFIX_FIELDS[33] = "pmu_golden_window_base"
PREFIX_FIELDS[34] = "pmu_golden_window_len"
PREFIX_FIELDS[35] = "pmu_golden_window_crc"
PREFIX_FIELDS[36] = "retained_36"
PREFIX_FIELDS[37] = "retained_37"
PREFIX_FIELDS[38] = "retained_38"
PREFIX_FIELDS[39] = "retained_39"

PREFIX_FIELDS = PREFIX_FIELDS[:PREFIX_WORDS]
assert len(PREFIX_FIELDS) == PREFIX_WORDS, len(PREFIX_FIELDS)

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

HOOK_FIELDS = HOOK_FIELDS[:HOOK_WORDS]
assert len(PREFIX_FIELDS) == PREFIX_WORDS, len(PREFIX_FIELDS)
assert len(HOOK_FIELDS) == HOOK_WORDS, len(HOOK_FIELDS)

SNAPSHOT_NAMES = [
    "pre",
    "internal_pre_release",
    "internal_post_disable",
    "after_return",
]
SNAPSHOT_WORD_NAMES = [
    "pmcr",
    "pmcntenset",
    "cfg",
    "cycle_low",
    "cycle_high",
    "stable",
    "retries",
    "overflow",
]

RETAINED_SNAPSHOT_WORDS = []
for snapshot_name in SNAPSHOT_NAMES:
    for word_name in SNAPSHOT_WORD_NAMES:
        RETAINED_SNAPSHOT_WORDS.append(f"{snapshot_name}_{word_name}")

assert len(RETAINED_SNAPSHOT_WORDS) == SNAPSHOT_WORDS * SNAPSHOT_COUNT
RETAINED_FIELD_COUNT = PREFIX_WORDS + HOOK_WORDS + len(RETAINED_SNAPSHOT_WORDS)
assert RETAINED_FIELD_COUNT == 85, RETAINED_FIELD_COUNT


def u32(value: int) -> int:
    return value & 0xFFFFFFFF


def delta32(ending: int, start: int) -> int:
    return u32(ending - start)


def snapshot(cyc: int, pmcr: int = 1, cfg: int = 0, stable: int = 1, retries: int = 0, overflow: int = 0):
    return (pmcr, 1 << 31, cfg, cyc & 0xFFFFFFFF, (cyc >> 32) & 0xFFFF, stable, retries, overflow)


def mutate_byte(payload: bytes, index: int, xor: int) -> bytes:
    data = bytearray(payload)
    if index < len(data):
        data[index] ^= xor
    return bytes(data)


def build_payload(
    *,
    schema: int = SCHEMA_VERSION,
    build_id: int = BUILD_ID,
    total_words: int = TOTAL_WORDS,
    run_sequence: int = 1,
    prefix_overrides: dict[str, int] | None = None,
    appendix: list[int] | None = None,
):
    if prefix_overrides is None:
        prefix_overrides = {}

    prefix = [0] * PREFIX_WORDS
    prefix[0] = schema
    prefix[1] = build_id
    prefix[2] = 1
    prefix[3] = 0
    prefix[4] = run_sequence
    prefix[5] = 1
    prefix[6] = 0
    prefix[7] = 0
    prefix[8] = 0
    prefix[9] = 0x1F
    prefix[10] = 0x1111
    prefix[11] = 0
    prefix[12] = 0
    prefix[13] = 1
    prefix[14] = 100
    prefix[15] = 200
    prefix[16] = 20
    prefix[17] = 0x4000
    prefix[18] = 0x4001
    prefix[19] = 1
    prefix[20] = 1
    prefix[21] = 1
    prefix[22] = 0xC
    prefix[23] = 0
    prefix[24] = 4
    prefix[25] = 0
    prefix[26] = 0
    prefix[27] = 0
    prefix[28] = 0
    prefix[29] = 0
    prefix[30] = 0
    prefix[31] = 0
    prefix[32] = 0
    prefix[33] = 0
    prefix[34] = 0x20000000
    prefix[35] = 0x4000
    prefix[36] = 0xABCD1234
    prefix[37] = 0
    prefix[38] = 0
    prefix[39] = 0

    for field, value in prefix_overrides.items():
        if field not in PREFIX_FIELDS:
            raise ProtocolError("unknown prefix field: %s" % field)
        prefix[all(PREFIX_FIELDS.index(field) for _ in [0])]
        prefix[PREFIX_FIELDS.index(field)] = value

    hook = [
        1,
        1,
        1,
        1,
        1,
        0x2000AAAA,
        100,
        1000,
        0,
        0x4000,
        6,
        1,
        0,
    ]

    pre = snapshot(100)
    pre2 = snapshot(1000)
    pre3 = snapshot(1000, pmcr=0)
    pre4 = snapshot(0, pmcr=0)

    body = (
        list(prefix)
        + list(hook)
        + list(pre)
        + list(pre2)
        + list(pre3)
        + list(pre4)
    )

    if appendix is None:
        appendix = [
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
            0xDEAD,
        ]

    if len(appendix) != 15:
        raise ProtocolError("v12 appendix must have 15 words, got %d" % len(appendix))
    body.extend(appendix)
    if len(body) != BODY_WORDS:
        raise ProtocolError("body length mismatch: expected %d got %d" % (BODY_WORDS, len(body)))

    header = [
        MAGIC,
        SCHEMA_VERSION,
        total_words,
        HEADER_WORDS,
        run_sequence,
        1,
        0,
        0,
    ]

    payload = bytearray(struct.pack("<8I", *header) + b"".join(struct.pack("<I", word) for word in body))
    struct.pack_into(
        "<I",
        payload,
        28,
        zlib.crc32(payload[16:28] + payload[32:]) & 0xFFFFFFFF,
    )
    if len(payload) != PAYLOAD_SIZE:
        raise ProtocolError("payload size mismatch")
    return bytes(payload)


def parse_payload(payload: bytes) -> dict:
    if len(payload) % 4 != 0:
        raise ProtocolError("payload not word-aligned")
    if len(payload) < HEADER_WORDS * 4:
        raise ProtocolError("truncated header")

    words = list(struct.unpack(f"<{len(payload) // 4}I", payload))
    header = words[:HEADER_WORDS]
    magic, schema, total_words, header_words, seq, valid_flags, run_return_code, crc = header

    if schema != SCHEMA_VERSION:
        raise ProtocolError("header schema mismatch: %d" % schema)
    if header_words != HEADER_WORDS:
        raise ProtocolError("header words mismatch")
    if total_words != len(words):
        raise ProtocolError("declared/actual word length mismatch")
    if total_words < TOTAL_WORDS:
        raise ProtocolError("declared length too short")
    if total_words > len(words):
        raise ProtocolError("declared length exceeds received payload")

    body_words = words[HEADER_WORDS:]
    if len(body_words) != BODY_WORDS:
        raise ProtocolError("body length mismatch")

    if body_words[0] != SCHEMA_VERSION:
        raise ProtocolError("wire body schema mismatch")

    build_id = body_words[1]
    retained = {}
    for idx, name in enumerate(PREFIX_FIELDS):
        retained[name] = body_words[idx]
    for idx, name in enumerate(HOOK_FIELDS):
        retained[name] = body_words[PREFIX_WORDS + idx]

    snap_base = PREFIX_WORDS + HOOK_WORDS
    for snap_idx, snap_name in enumerate(SNAPSHOT_NAMES):
        start = snap_base + snap_idx * SNAPSHOT_WORDS
        for word_idx, word_name in enumerate(SNAPSHOT_WORD_NAMES):
            retained[f"{snap_name}_{word_name}"] = body_words[start + word_idx]

    v12_words = body_words[85:100]
    v12 = {}
    for index, name in enumerate(V12_FIELDS):
        v12[name] = v12_words[index]

    return {
        "magic": magic,
        "schema": schema,
        "total_words": total_words,
        "header_words": header_words,
        "run_sequence": seq,
        "valid_flags": valid_flags,
        "run_return_code": run_return_code,
        "crc": crc,
        "payload_words": words,
        "body_words": body_words,
        "build_id": build_id,
        "retained": retained,
        "v12": v12,
    }


def parse_with_crc(payload: bytes) -> dict:
    parsed = parse_payload(payload)
    expected = zlib.crc32(payload[16:28] + payload[32:]) & 0xFFFFFFFF
    if expected != parsed["crc"]:
        raise ProtocolError("crc mismatch")
    return parsed


def command_contract(sequence: list[str], success: bool) -> bool:
    if success:
        expected = [
            "CMD_WRITE_SUBMIT",
            "POLL_ENTRY",
            "HELPER_STATUS_READ",
            "POLL_P1",
            "POLL_P2",
            "CMD2#1",
            "QREAD",
            "CMD2#2",
            "QREAD_VERIFY",
            "FINAL_PENDING_BEFORE_CLEAR",
            "NVIC_CLEAR_PENDING",
            "FINAL_PENDING_AFTER_CLEAR",
            "FINAL_ACTIVE_AFTER_CLEANUP",
            "FINAL_IRQ_TRIGGERED_AFTER_CLEANUP",
            "CMD0",
            "HPRINTF",
            "CMD0C",
        ]
    else:
        expected = [
            "CMD_WRITE_SUBMIT",
            "POLL_ENTRY",
            "HELPER_TIMEOUT_REPORT",
            "HELPER_TIMEOUT_QREAD",
            "CMD2_TIMEOUT",
            "FINAL_PENDING_BEFORE_CLEAR",
            "NVIC_CLEAR_PENDING",
            "FINAL_PENDING_AFTER_CLEAR",
            "FINAL_ACTIVE_AFTER_CLEANUP",
            "FINAL_IRQ_TRIGGERED_AFTER_CLEANUP",
            "CMD0",
            "HPRINTF",
            "CMD0C",
        ]

    if sequence != expected:
        return False

    cmd2_count = sequence.count("CMD2#1") + sequence.count("CMD2#2") + sequence.count("CMD2_TIMEOUT")
    if success:
        if cmd2_count != 2:
            return False
    else:
        if cmd2_count != 1:
            return False
    return True


def validate_command(doc: dict):
    sequence = doc["command_sequence"]
    success = doc["poll_result"] == POLL_SUCCESS
    check("exact command contract length", command_contract(sequence, success))

    if success:
        check("no NVIC enable path", "NVIC_EnableIRQ" not in sequence and "ISER_SET" not in sequence)
        check("success ordering CMD2#1 < QREAD < CMD2#2",
              sequence.index("CMD2#1") < sequence.index("QREAD") < sequence.index("CMD2#2"))
        check("cleanup tail order",
              sequence.index("FINAL_PENDING_BEFORE_CLEAR") < sequence.index("NVIC_CLEAR_PENDING") < sequence.index("FINAL_PENDING_AFTER_CLEAR")
              < sequence.index("FINAL_ACTIVE_AFTER_CLEANUP") < sequence.index("FINAL_IRQ_TRIGGERED_AFTER_CLEANUP")
              < sequence.index("CMD0") < sequence.index("HPRINTF") < sequence.index("CMD0C"))
    else:
        check("timeout cleanup still reaches CMD0 and CMD0C",
              sequence.index("CMD0") < sequence.index("HPRINTF") < sequence.index("CMD0C"))
        check("timeout path has no success command count",
              sequence.count("CMD2#1") + sequence.count("CMD2#2") == 0)


def validate_host_terms(record: dict):
    success = record["poll_result"] == POLL_SUCCESS
    t2 = record["timing"]["t_submit_after_cmd"]
    p0 = record["timing"]["t_poll_entry"]
    p1 = record["timing"]["t_status_completion_seen"]
    p2 = record["timing"]["t_poll_exit"]
    status = record["status_at_success"]

    d0 = delta32(p0, t2)
    d1 = delta32(p1, p0)
    d2 = delta32(p2, p1)

    check("runtime vector is stock symbol", record["installed_vector_symbol"] == STOCK_VECTOR_NAME)
    check("runtime installed vector address preserved", record["installed_vector"] == STOCK_VECTOR_ADDR)
    check("runtime hard-bypass NVIC state is clean", 
          record["nvic_enabled_before_submit"] == 0
          and record["nvic_pending_after_initial_clear"] == 0
          and record["nvic_active_before_submit"] == 0
          and record["irq_triggered_before_submit"] == 0)

    if success:
        check("poll_result success path is 1", record["poll_result"] == POLL_SUCCESS)
        check("status success bit set", status & 0x2 == 0x2)
        check("poll helper emits P1/P2", p1 != 0 and p2 != 0)
        check("u32 half-range d0", d0 < HALF_RANGE)
        check("u32 half-range d1", d1 < HALF_RANGE)
        check("u32 half-range d2", d2 < HALF_RANGE)
        check("d0+d1 == delta(T2->P1)", u32(d0 + d1) == delta32(p1, t2))
        check("d0+d1+d2 == delta(T2->P2)", u32(d0 + d1 + d2) == delta32(p2, t2))
        check("both identities true",
              u32(d0 + d1) == delta32(p1, t2)
              and u32(d0 + d1 + d2) == delta32(p2, t2))
        check("status-derived irq mask", doc_irq_mask(record) == (status >> 16) & 0xFFFF)
        check("both cleanup sentinels exist",
              record["nvic_pending_before_final_clear"] in (0, 1)
              and record["nvic_pending_after_final_clear"] in (0, 1)
              and record["nvic_active_after_cleanup"] in (0, 1)
              and record["irq_triggered_after_cleanup"] in (0, 1))
        check("write path has CMD0 and CMD0xC", record["command_sequence"].count("CMD0") == 1 and record["command_sequence"].count("CMD0C") == 1)
    else:
        check("success-only fields invalid on timeout/invalid", p1 == 0 and p2 == 0 and status == 0)
        check("non-success no-derived", record["derived"] is None)
        check("non-success writes blocked", not record["archive_write"])


def doc_irq_mask(record: dict) -> int:
    status = record["status_at_success"]
    if record["poll_result"] != POLL_SUCCESS:
        return 0
    return (status >> 16) & 0xFFFF


def make_manifest(evidence_source: str = "arm_elf") -> dict:
    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "qualification_mode": "Q1",
        "expected_return_address": 0x12345678,
        "artifact_sha256": {
            "generated_runner.c": RUNNER_SHA256,
            "generated_vendor_u85.c": VENDOR_SHA256,
        },
        "build_evidence_sha256": {
            "generated_runner.c": RUNNER_SHA256,
            "generated_vendor_u85.c": VENDOR_SHA256,
            "manifest": "",
        },
        "evidence_source": evidence_source,
    }


def make_raw(payload: bytes) -> dict:
    return {
        "payload_hex": payload.hex(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "reread_payload_hex": payload.hex(),
        "reread_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "reread_matches_run_payload": True,
    }


def make_record(boot: int, run: int, scenario: str = "success") -> dict:
    if scenario == "success":
        t2 = 0x1000
        p0 = 0x1080
        p1 = 0x10A0
        p2 = 0x1110
        poll_result = POLL_SUCCESS
        status = 0x00020002
        archive_write = True
    elif scenario == "half_wrap":
        t2 = 0xFFFFFF90
        p0 = u32(t2 + 0x30)
        p1 = u32(p0 + 0x50)
        p2 = u32(p1 + 0x60)
        poll_result = POLL_SUCCESS
        status = 0x80000002
        archive_write = True
    elif scenario in ("timeout", "invalid"):
        t2 = 0x0800
        p0 = 0x0808
        p1 = 0
        p2 = 0
        poll_result = POLL_TIMEOUT
        status = 0
        archive_write = False
    else:
        t2 = 0x1000
        p0 = 0x1080
        p1 = 0
        p2 = 0
        poll_result = 0
        status = 0
        archive_write = False

    payload = build_payload(
        run_sequence=run,
        prefix_overrides={
            "build_id": BUILD_ID,
            "run_sequence": run,
        },
        appendix=[
            t2,
            p0,
            p1,
            p2,
            poll_result,
            status,
            STOCK_VECTOR_ADDR,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
    )

    command_sequence = [
        "CMD_WRITE_SUBMIT",
        "POLL_ENTRY",
        "HELPER_STATUS_READ" if scenario in ("success", "half_wrap") else "HELPER_TIMEOUT_REPORT",
        "POLL_P1" if scenario in ("success", "half_wrap") else "HELPER_TIMEOUT_QREAD",
        "POLL_P2" if scenario in ("success", "half_wrap") else "CMD2_TIMEOUT",
        "CMD2#1" if scenario in ("success", "half_wrap") else "POLL_TIMEOUT_NOP",
        "QREAD" if scenario in ("success", "half_wrap") else "POLL_TIMEOUT_NOP",
        "CMD2#2" if scenario in ("success", "half_wrap") else "POLL_TIMEOUT_NOP",
        "QREAD_VERIFY" if scenario in ("success", "half_wrap") else "POLL_TIMEOUT_NOP",
        "FINAL_PENDING_BEFORE_CLEAR",
        "NVIC_CLEAR_PENDING",
        "FINAL_PENDING_AFTER_CLEAR",
        "FINAL_ACTIVE_AFTER_CLEANUP",
        "FINAL_IRQ_TRIGGERED_AFTER_CLEANUP",
        "CMD0",
        "HPRINTF",
        "CMD0C",
    ]
    if scenario in ("timeout", "invalid"):
        command_sequence = [
            "CMD_WRITE_SUBMIT",
            "POLL_ENTRY",
            "HELPER_TIMEOUT_REPORT",
            "HELPER_TIMEOUT_QREAD",
            "CMD2_TIMEOUT",
            "FINAL_PENDING_BEFORE_CLEAR",
            "NVIC_CLEAR_PENDING",
            "FINAL_PENDING_AFTER_CLEAR",
            "FINAL_ACTIVE_AFTER_CLEANUP",
            "FINAL_IRQ_TRIGGERED_AFTER_CLEANUP",
            "CMD0",
            "HPRINTF",
            "CMD0C",
        ]

    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "host": {
            "host_boot_index": boot,
            "manifest_path": "manifest.json",
            "manifest_text": str(make_manifest()),
            "manifest_sha256": hashlib.sha256(str(make_manifest()).encode()).hexdigest(),
            "artifact_sha256": make_manifest()["artifact_sha256"],
        },
        "manifest": make_manifest(),
        "raw": make_raw(payload),
        "timing": {
            "t_submit_after_cmd": t2,
            "t_poll_entry": p0,
            "t_status_completion_seen": p1,
            "t_poll_exit": p2,
        },
        "poll_result": poll_result,
        "status_at_success": status,
        "installed_vector": STOCK_VECTOR_ADDR,
        "installed_vector_symbol": STOCK_VECTOR_NAME,
        "nvic_enabled_before_submit": 0,
        "nvic_pending_after_initial_clear": 0,
        "nvic_active_before_submit": 0,
        "irq_triggered_before_submit": 0,
        "nvic_pending_before_final_clear": 0,
        "nvic_pending_after_final_clear": 0,
        "nvic_active_after_cleanup": 0,
        "irq_triggered_after_cleanup": 0,
        "command_sequence": command_sequence,
        "derived": None if not status else {"irq_history_mask": doc_irq_mask({"poll_result": poll_result, "status_at_success": status})},
        "fresh_boot_required": False,
        "campaign_abort": False,
        "archive_write": archive_write,
    }


def validate_manifest(manifest: dict):
    check("manifest schema version is 12", manifest["schema_version"] == SCHEMA_VERSION)
    check("manifest build id exact", int(manifest["build_id"], 16) == BUILD_ID)
    check("manifest evidence_source is arm_elf", manifest["evidence_source"] == "arm_elf")
    check("manifest runner hash", manifest["artifact_sha256"]["generated_runner.c"] == RUNNER_SHA256)
    check("manifest vendor hash", manifest["artifact_sha256"]["generated_vendor_u85.c"] == VENDOR_SHA256)


def validate_transport(base: bytes):
    check("transport truncated rejected", _reject(lambda: parse_payload(base[:3])))
    check("transport extra words rejected", _reject(lambda: parse_payload(base + b"\x00\x00\x00\x00")))
    check("header/body schema mismatch rejected", _reject(lambda: parse_payload(base[:4] + struct.pack("<I", 11) + base[8:])))
    check("bad declared length rejected", _reject(lambda: parse_with_crc(bytearray(base[:-4]) + b"\x00\x00\x00\x00")))
    bad_crc = bytearray(base)
    bad_crc[40] ^= 0x01
    check("bad CRC rejected", _reject(lambda: parse_with_crc(bytes(bad_crc))))

    mutated = base + b"\x00"
    bad_raw = make_raw(base)
    bad_raw["reread_payload_hex"] = mutated.hex()
    bad_raw["reread_payload_sha256"] = hashlib.sha256(mutated).hexdigest()
    bad_raw["reread_matches_run_payload"] = False
    check("raw reread mismatch visible", bad_raw["reread_matches_run_payload"] is False)

    doc = make_record(1, 1, scenario="success")
    doc["command_sequence"] = doc["command_sequence"] + ["EXTRA_CMD"]
    check("extra command token fails contract", command_contract(doc["command_sequence"], True) is False)


def _reject(fn) -> bool:
    try:
        fn()
        return False
    except ProtocolError:
        return True


def validate_campaigns():
    records = []
    for boot in (1, 2, 3):
        for run in range(1, 11):
            if boot == 2 and run == 4:
                r = make_record(boot, run, scenario="timeout")
                r["campaign_abort"] = True
                r["fresh_boot_required"] = True
            elif boot == 2 and run >= 5:
                r = make_record(boot, run, scenario="invalid")
                r["skip_write"] = True
                r["campaign_abort"] = True
                r["archive_write"] = False
            else:
                r = make_record(boot, run, scenario="success")
                r["archive_write"] = True
            r["host"]["run_sequence"] = run
            records.append(r)

    check("campaign shape 3x10", len(records) == 30)
    by_boot = {}
    for r in records:
        by_boot[r["host"]["host_boot_index"]] = by_boot.get(r["host"]["host_boot_index"], 0) + 1
    check("boot1 has 10 entries", by_boot.get(1) == 10)
    check("boot2 has 10 entries", by_boot.get(2) == 10)
    check("boot3 has 10 entries", by_boot.get(3) == 10)

    timeout = next(r for r in records if r["host"]["host_boot_index"] == 2 and r["host"]["run_sequence"] == 4)
    check("boot2 run4 is timeout", timeout["poll_result"] == POLL_TIMEOUT)
    check("boot2 run4 has no derived", timeout["derived"] is None)
    check("boot2 run4 requires fresh boot", timeout["fresh_boot_required"])
    check("boot2 run4 no archive", not timeout["archive_write"])

    for run in range(5, 11):
        skipped = next(r for r in records if r["host"]["host_boot_index"] == 2 and r["host"]["run_sequence"] == run)
        check("boot2 run%d skipped after timeout" % run, skipped.get("skip_write") and not skipped["archive_write"])

    for record in records:
        validate_command(record)
        validate_host_terms(record)


def validate_payload_invariants(base: bytes):
    parsed = parse_payload(base)
    check("schema header is 12", parsed["schema"] == SCHEMA_VERSION)
    check("body schema is 12", parsed["payload_words"][8] == SCHEMA_VERSION)
    check("total words exact", parsed["total_words"] == TOTAL_WORDS)
    check("payload bytes exact", len(base) == PAYLOAD_SIZE)
    check("retained field count exact", len(parsed["retained"]) == RETAINED_FIELD_COUNT)
    check("retained includes PMU golden", "pmu_golden_window_base" in parsed["retained"] and "pmu_golden_window_len" in parsed["retained"] and "pmu_golden_window_crc" in parsed["retained"])
    check("all 15 V12 fields", len(parsed["v12"]) == 15)

    for field in V12_FIELDS:
        check("v12 field present %s" % field, field in parsed["v12"])

    check("build id exact", parsed["build_id"] == BUILD_ID)
    check("v8 rejected", _reject(lambda: parse_payload(base[:4] + struct.pack("<I", 8) + base[8:])))
    check("v9 rejected", _reject(lambda: parse_payload(base[:4] + struct.pack("<I", 9) + base[8:])))
    check("v10 rejected", _reject(lambda: parse_payload(base[:4] + struct.pack("<I", 10) + base[8:])))
    check("v11 rejected", _reject(lambda: parse_payload(base[:4] + struct.pack("<I", 11) + base[8:])))


def run_checks():
    print("=== PMU completion poll V12 host contract (Task 5 RED) ===")

    base = build_payload()

    validate_payload_invariants(base)
    parse_doc = parse_with_crc(base)
    for doc in (make_record(1, 1, "success"), make_record(1, 2, "half_wrap"), make_record(2, 4, "timeout")):
        check("manifest producer-consumer includes arm_elf", doc["manifest"]["evidence_source"] == "arm_elf")
        validate_manifest(doc["manifest"])
        check("manifest and doc build ids match", doc["manifest"]["build_id"] == "0x%08X" % parse_doc["build_id"])

    # direct payload->host roundtrip checks
    for parsed in [parse_payload(base), parse_with_crc(base)]:
        check("wire/manifest build-id consistency", parsed["build_id"] == int("0x%08X" % parsed["build_id"], 16))

    validate_transport(base)
    validate_campaigns()
    validate_host_terms(make_record(1, 1, "success"))
    validate_host_terms(make_record(1, 1, "half_wrap"))

    # mutation utility checks
    mutated = mutate_byte(base, 16, 0x01)
    check("mutation path is effective", mutated != base)
    no_mutation = mutate_byte(base, 16, 0)
    check("no-op mutation leaves payload unchanged", no_mutation == base)


if __name__ == "__main__":
    run_checks()
    import importlib
    importlib.import_module("host.runner_proto_pmu_completion_poll_v12")
