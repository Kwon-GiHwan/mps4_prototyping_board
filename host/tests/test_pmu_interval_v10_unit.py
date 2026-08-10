import hashlib
import json
import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import analyze_pmu_interval_v10 as az
import run_pmu_interval_v10 as rv10
import runner_proto as v8
import runner_proto_pmu_interval_v10 as v10

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-56s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


GLOBAL = 1 << v8.PMU_PMCR_CNT_EN_BIT
ARMED = 1 << v8.PMU_PMCNTEN_CYCLE_BIT
LR = 0x3100078C


def snap(cfg=0, cyc=0, armed=True, glob=True, stable=1, ovs=0):
    return (GLOBAL if glob else 0, ARMED if armed else 0, cfg, cyc & 0xFFFFFFFF,
            (cyc >> 32) & 0xFFFF, stable, 0, ovs)


def manifest(**over):
    doc = {
        "variant": "PMU_INTERVAL_FINE_DIAG_V10",
        "schema_version": 10,
        "build_id": "0x%08X" % v10.PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID,
        "qualification_mode": "Q1",
        "expected_return_address": LR,
        "characterization_only": True,
        "not_a_performance_baseline": True,
        "not_a_latency_measurement": True,
        "busy_poll_interval_only": True,
        "d23_split_only": True,
        "post_t3_handoff_out_of_scope": True,
        "verify_output_stays_enabled": True,
        "generated_private_driver_diagnostic_only": True,
        "production_end_only_frozen": True,
        "mlek_performance_not_started": True,
        "artifact_sha256": dict(v10.PMU_INTERVAL_V10_FROZEN_ARTIFACT_SHA256),
        "build_evidence_sha256": dict(
            v10.PMU_INTERVAL_V10_FROZEN_BUILD_EVIDENCE_SHA256),
    }
    doc.update(over)
    return doc


def build(**over):
    pre = over.pop("pre", snap(cyc=1000))
    internal = over.pop("internal", snap(cyc=4300))
    post_disable = over.pop("post_disable", snap(cyc=4300, glob=False))
    after_return = over.pop("after_return", snap(cyc=0, armed=False, glob=False))
    prefix = [
        10,
        v10.PMU_INTERVAL_FINE_DIAG_V10_BUILD_ID,
        1, 0, 7,
        0, 0, 0,
        0, v8.RUN_VALID_REQUIRED_MASK,
        0x1111, 0x2222, 0x3333,
        1, 100, 900, 700,
        0, 58, 8,
        v8.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
        v8.PMU_DIAG_POWER_GUARD_CYCLES, 0xC, 0, 0,
        v8.PMU_DIAG_RESET_GUARD_CYCLES, 0x4000, 0x4001, 1,
        v8.PMU_DIAG_STABILITY_SAMPLES, 1,
        0xC, v8.PMU_QUAL_POWER_SEAM_ID, 0, 0, 0xC, 0,
        v8.PMU_DIAG_GOLDEN_WINDOW_BASE, v8.PMU_DIAG_GOLDEN_WINDOW_LEN,
        v8.GOLDEN_WINDOW_CRC,
    ]
    hook = [1, 1, 1, 1, 1, 1, LR, 800, 850, 0, 0, 16, 1]
    extra = [200, 300, 420, 500, 1, 1]
    for idx, value in over.items():
        mapping = {
            "build_id": 1,
            "diag_case": 2,
            "nc_control_id": 3,
            "run_sequence": 4,
            "valid_flags": 9,
            "t_call_enter": 14,
            "t_call_return": 15,
            "npu_cmd_after_return": 31,
            "power_rehold_performed": 33,
            "rehold_guard_cycles": 34,
            "ts_source_valid": 13,
            "pmu_mmio_read_count_delta": 18,
            "pmu_mmio_write_count_delta": 19,
            "hook_detected_count": ("hook", 3),
            "hook_fired_count": ("hook", 4),
            "hook_callsite_lr_observed": ("hook", 6),
            "hook_entry_timestamp": ("hook", 7),
            "hook_pmu_mmio_read_count": ("hook", 11),
            "hook_pmu_mmio_write_count": ("hook", 12),
            "t_submit_before_cmd": ("extra", 0),
            "t_submit_after_cmd": ("extra", 1),
            "t_isr_entry": ("extra", 2),
            "t_irq_status_seen": ("extra", 3),
            "i0_hit_count": ("extra", 4),
            "t3_hit_count": ("extra", 5),
            "golden_window_crc": 39,
            "run_rc": 8,
        }
        slot = mapping[idx]
        if isinstance(slot, tuple):
            if slot[0] == "hook":
                hook[slot[1]] = value
            else:
                extra[slot[1]] = value
        else:
            prefix[slot] = value
    body = prefix + hook + list(pre) + list(internal) + list(post_disable) + list(after_return) + extra
    total = v10.PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS + len(body)
    head = struct.pack("<8I", v10.PMU_INTERVAL_FINE_DIAG_V10_MAGIC, 10, total,
                       v10.PMU_INTERVAL_FINE_DIAG_V10_HEADER_WORDS, prefix[4], prefix[9], prefix[8], 0)
    payload = bytearray(head + b"".join(struct.pack("<I", w) for w in body))
    struct.pack_into("<I", payload, 28,
                     zlib.crc32(bytes(payload[16:28]) + bytes(payload[32:])) & 0xFFFFFFFF)
    return bytes(payload)


def archive_doc(raw, man=None, host_boot_index=1):
    man = manifest() if man is None else man
    parsed = v10.parse_pmu_interval_diag_v10_payload(raw)
    return {
        "variant": "PMU_INTERVAL_FINE_DIAG_V10",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_path": "manifest.json",
            "manifest_text": json.dumps(man, sort_keys=True),
            "manifest_sha256": hashlib.sha256(
                json.dumps(man, sort_keys=True).encode()
            ).hexdigest(),
            "artifact_sha256": man["artifact_sha256"],
        },
        "manifest": json.loads(json.dumps(man, sort_keys=True)),
        "target": v10.target_fields(parsed),
        "derived": v10.classify_pmu_interval_diag_v10(parsed, man),
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_payload_hex": raw.hex(),
            "reread_payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }


def write_doc(root, name, doc):
    path = os.path.join(root, name)
    with open(path, "w") as handle:
        json.dump(doc, handle, sort_keys=True)
    return path


def campaign_payload(boot, repeat, primary_window):
    t0 = 100 + boot * 1000 + repeat * 10
    d01 = 10
    d12 = 20
    d34 = 40
    d23 = primary_window - (d01 + d12 + d34)
    e1 = 8
    e0 = d23 - e1
    d45 = 50
    return build(
        pre=snap(cyc=1000),
        internal=snap(cyc=1000 + primary_window),
        post_disable=snap(cyc=1000 + primary_window, glob=False),
        run_sequence=repeat,
        t_call_enter=t0,
        t_submit_before_cmd=t0 + d01,
        t_submit_after_cmd=t0 + d01 + d12,
        t_isr_entry=t0 + d01 + d12 + e0,
        t_irq_status_seen=t0 + d01 + d12 + d23,
        hook_entry_timestamp=t0 + primary_window,
        t_call_return=t0 + primary_window + d45,
    )


def campaign_paths(root, *, per_boot_primary=None, mutate=None):
    paths = []
    per_boot_primary = per_boot_primary or {
        1: [100] * 10,
        2: [100] * 5 + [130] * 5,
        3: [100] * 5 + [160] * 5,
    }
    for boot in (1, 2, 3):
        for repeat in range(1, 11):
            raw = campaign_payload(boot, repeat, per_boot_primary[boot][repeat - 1])
            doc = archive_doc(raw, host_boot_index=boot)
            if mutate is not None:
                doc = mutate(doc, boot, repeat)
            paths.append(write_doc(root, "boot%d_repeat%02d.json" % (boot, repeat), doc))
    return paths


print("=== ABI ===")
p = build()
res = v10.parse_pmu_interval_diag_v10_payload(p)
check("v10 payload size is 396 bytes", len(p) == v10.PMU_INTERVAL_FINE_DIAG_V10_PAYLOAD_SIZE)
check("v10 parser decodes extra checkpoints",
      (res.t_submit_before_cmd, res.t_submit_after_cmd, res.t_isr_entry,
       res.t_irq_status_seen, res.i0_hit_count, res.t3_hit_count)
      == (200, 300, 420, 500, 1, 1))
try:
    v8.parse_pmu_qual_payload(p)
    check("v8 parser rejects v10 payload", False)
except v8.ProtocolError:
    check("v8 parser rejects v10 payload", True)

bad = bytearray(p)
bad[40] ^= 0x01
try:
    v10.parse_pmu_interval_diag_v10_payload(bytes(bad))
    check("CRC mismatch rejected", False)
except v8.ProtocolError:
    check("CRC mismatch rejected", True)

print("=== classification ===")
cls = v10.classify_pmu_interval_diag_v10(res, manifest())
check("valid sample classifies", cls["valid"], "reasons=%s" % cls["invalid_reasons"])
check("D23 is split into E0+E1 with delta32 consistency",
      cls["deltas_u32"]["D23"] == 200
      and cls["deltas_u32"]["E0"] == 120
      and cls["deltas_u32"]["E1"] == 80
      and cls["terms"]["d23_split_consistent_u32"])
check("characterization labels present",
      cls["busy_poll_interval_only"] and cls["d23_split_only"]
      and cls["post_t3_handoff_out_of_scope"] and cls["not_a_latency_measurement"])
check("all coarse interval labels present",
      cls["t0_t1_label"] == "call_entry_to_pre_submit_setup"
      and cls["t3_t4_label"] == "completion_seen_to_pre_release_driver_path")
check("V10 window has a non-comparable V10-only name",
      cls["v10_perturbed_window_cycles"] is not None
      and cls["not_comparable_to_v8_cfg_window"] is True
      and cls["not_comparable_to_v9_window"] is True
      and "npu_pmu_window_cycles" not in cls)

try:
    v10.verify_manifest_identity(manifest(production_end_only_frozen=False), "test")
    check("Production-unfrozen manifest rejected", False)
except SystemExit:
    check("Production-unfrozen manifest rejected", True)

try:
    v10.verify_manifest_identity(manifest(artifact_sha256={}), "test")
    check("empty artifact provenance rejected", False)
except SystemExit:
    check("empty artifact provenance rejected", True)

cls = v10.classify_pmu_interval_diag_v10(
    v10.parse_pmu_interval_diag_v10_payload(build(t_submit_after_cmd=430)),
    manifest(),
)
check("non-monotonic checkpoints fail closed",
      (not cls["valid"]) and "e0_nonzero_u32" in cls["invalid_reasons"])

cls = v10.classify_pmu_interval_diag_v10(
    v10.parse_pmu_interval_diag_v10_payload(build(t_irq_status_seen=0)),
    manifest(),
)
check("zero checkpoint fails closed",
      (not cls["valid"]) and "t3_nonzero" in cls["invalid_reasons"])

for label, override, reason in (
    ("I0 multiple hits", {"i0_hit_count": 2}, "i0_hit_once"),
    ("T3 multiple hits", {"t3_hit_count": 2}, "t3_hit_once"),
    ("I0 missing", {"t_isr_entry": 0}, "i0_nonzero"),
):
    cls = v10.classify_pmu_interval_diag_v10(
        v10.parse_pmu_interval_diag_v10_payload(build(**override)), manifest())
    check(label + " fails closed",
          (not cls["valid"]) and reason in cls["invalid_reasons"])

for label, override, reason in (
    ("timestamp source invalid", {"ts_source_valid": 0}, "timestamp_source_valid"),
    ("window MMIO count drift", {"pmu_mmio_read_count_delta": 59},
     "window_mmio_reads_exact"),
    ("hook MMIO count drift", {"hook_pmu_mmio_read_count": 17},
     "hook_mmio_reads_exact"),
):
    cls = v10.classify_pmu_interval_diag_v10(
        v10.parse_pmu_interval_diag_v10_payload(build(**override)), manifest())
    check(label + " fails closed",
          (not cls["valid"]) and reason in cls["invalid_reasons"])

try:
    v10.parse_pmu_interval_diag_v10_payload(build(power_rehold_performed=1))
    check("retained rehold slot rejected by parser", False)
except v8.ProtocolError:
    check("retained rehold slot rejected by parser", True)

cls = v10.classify_pmu_interval_diag_v10(
    v10.parse_pmu_interval_diag_v10_payload(build(build_id=0xDEADBEEF)),
    manifest(),
)
check("wrong build id fails closed",
      (not cls["valid"]) and "build_id_is_v10" in cls["invalid_reasons"])

cls = v10.classify_pmu_interval_diag_v10(
    v10.parse_pmu_interval_diag_v10_payload(build(hook_callsite_lr_observed=LR + 4)),
    manifest(),
)
check("wrong callsite fails closed",
      (not cls["valid"]) and "hook_callsite_lr_matches_manifest" in cls["invalid_reasons"])

cls = v10.classify_pmu_interval_diag_v10(
    v10.parse_pmu_interval_diag_v10_payload(build(golden_window_crc=0xDEAD)),
    manifest(),
)
check("golden failure fails closed",
      (not cls["valid"]) and "golden_window_ok" in cls["invalid_reasons"])

print("=== transport ===")


def frame_command(blob):
    return struct.unpack_from(v8.HEADER, blob)[2:5:2]


class FakeLink:
    def __init__(self, run_frames, get_frames):
        self._seq = 40
        self.run_frames = run_frames
        self.get_frames = get_frames
        self.queue = []
        self.late_frames = 0

    def next_sequence(self):
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    def send_raw(self, blob):
        cmd, seq = frame_command(blob)
        frames = self.run_frames(seq) if cmd == v8.CMD_RUN_PMU_DIAG else self.get_frames(seq)
        self.queue.extend(frames)

    def read_frame(self, _timeout):
        if not self.queue:
            raise v8.ProtocolError("scripted timeout")
        return self.queue.pop(0)


def ack(seq):
    return v8.Frame(1, v8.CMD_RUN_PMU_DIAG | 0x80, 0, seq, b"")


def complete(seq, payload):
    return v8.Frame(1, v8.CMD_PMU_DIAG_COMPLETE, 0, seq, payload)


def reread(seq, payload):
    return v8.Frame(1, v8.CMD_GET_PMU_DIAG_RESULT | 0x80, 0, seq, payload)


def fake_link(payload, run=None, get=None):
    return FakeLink(
        run or (lambda seq: [ack(seq), complete(seq, payload)]),
        get or (lambda seq: [reread(seq, payload)]),
    )


res, raw, reread_raw = rv10.collect_pmu_interval_v10(fake_link(p), timeout=0.01, get_timeout=0.01)
check("ACK/COMPLETE/GET exchange accepts byte-identical v10", raw == reread_raw == p)

for label, link in (
    ("no ACK rejected", fake_link(p, run=lambda seq: [])),
    ("ACK without COMPLETE rejected", fake_link(p, run=lambda seq: [ack(seq)])),
    ("COMPLETE-before-ACK rejected",
     fake_link(p, run=lambda seq: [complete(seq, p)])),
    ("duplicate ACK rejected",
     fake_link(p, run=lambda seq: [ack(seq), ack(seq)])),
    ("duplicate COMPLETE rejected",
     fake_link(p, run=lambda seq: [ack(seq), complete(seq, p), complete(seq, p)])),
    ("reread mismatch rejected",
     fake_link(p, get=lambda seq: [reread(seq, build(t_irq_status_seen=501))])),
):
    try:
        rv10.collect_pmu_interval_v10(link, timeout=0.01, get_timeout=0.01)
        check(label, False)
    except (v8.ProtocolError, v8.RunSequenceError):
        check(label, True)

stale = v8.Frame(1, v8.CMD_PMU_DIAG_COMPLETE, 0, 3, b"stale")
link = fake_link(p, run=lambda seq: [stale, ack(seq), complete(seq, p)])
_, raw, _ = rv10.collect_pmu_interval_v10(link, timeout=0.01, get_timeout=0.01)
check("stale prior-sequence frame skipped", raw == p and link.late_frames == 1)

try:
    rv10.verify_record_identity(
        v10.parse_pmu_interval_diag_v10_payload(build(diag_case=2)), manifest())
    check("wrong V10 case identity rejected before archive", False)
except SystemExit:
    check("wrong V10 case identity rejected before archive", True)

print("=== analyzer ===")
TEST_MANIFEST_SHA256 = hashlib.sha256(
    json.dumps(manifest(), sort_keys=True).encode()).hexdigest()
with tempfile.TemporaryDirectory() as td:
    raw = build()
    doc = archive_doc(raw)
    path = os.path.join(td, "sample.json")
    with open(path, "w") as handle:
        json.dump(doc, handle, sort_keys=True)
    _, loaded = az.load(path, TEST_MANIFEST_SHA256)
    check("analyzer reloads and re-derives sample", loaded["variant"] == "PMU_INTERVAL_FINE_DIAG_V10")

    try:
        az.load(path)
        check("analyzer rejects a self-consistent but non-frozen manifest", False)
    except SystemExit:
        check("analyzer rejects a self-consistent but non-frozen manifest", True)

    malformed = json.loads(json.dumps(doc))
    malformed["raw"]["payload_hex"] = "not-hex"
    malformed_path = os.path.join(td, "malformed.json")
    with open(malformed_path, "w") as handle:
        json.dump(malformed, handle, sort_keys=True)
    try:
        az.load(malformed_path, TEST_MANIFEST_SHA256)
        check("analyzer rejects malformed raw hex without traceback", False)
    except SystemExit:
        check("analyzer rejects malformed raw hex without traceback", True)

    doc["derived"]["deltas_u32"]["D23"] = 999
    with open(path, "w") as handle:
        json.dump(doc, handle, sort_keys=True)
    try:
        az.load(path, TEST_MANIFEST_SHA256)
        check("analyzer rejects derived delta mismatch", False)
    except SystemExit:
        check("analyzer rejects derived delta mismatch", True)

print("=== campaign analyzer ===")
with tempfile.TemporaryDirectory() as td:
    report = az.summarize_campaign(campaign_paths(td), TEST_MANIFEST_SHA256)
    check("campaign has exactly 30 samples", report["sample_count"] == 30)
    check("campaign has 3 boots", report["boot_count"] == 3)
    check("per-boot run_sequence is 1..10",
          report["per_boot_run_sequences"] == {
              "1": list(range(1, 11)),
              "2": list(range(1, 11)),
              "3": list(range(1, 11)),
          })
    check("campaign is explicitly non-performance",
          report["characterization_only"] and report["not_latency"]
          and report["not_performance"] and report["not_production"]
          and report["not_mlek"])
    check("observed floor is the primary-window minimum",
          report["floor_excursion"]["primary_window"] == az.PRIMARY_WINDOW
          and report["floor_excursion"]["observed_floor"] == 100)
    check("floor/excursion split counts are correct",
          report["floor_excursion"]["floor_sample_count"] == 20
          and report["floor_excursion"]["excursion_sample_count"] == 10)
    check("earliest excursion interval localizes to E0",
          report["floor_excursion"]["earliest_interval_counts"] == {"E0": 10})
    stats = report["v10_perturbed_window_stats"]
    check("overall V10 window stats are derived",
          stats["min"] == 100 and stats["max"] == 160 and stats["median"] == 100.0
          and stats["q1_inclusive"] == 100.0 and stats["q3_inclusive"] == 130.0
          and stats["iqr_inclusive"] == 30.0)
    check("per-boot E0 stats are split correctly",
          report["per_boot_delta_stats"]["1"]["E0"]["min"] == 22
          and report["per_boot_delta_stats"]["2"]["E0"]["max"] == 52
          and report["per_boot_delta_stats"]["3"]["E0"]["max"] == 82)
    check("constant interval CV collapses to zero",
          report["delta_stats"]["E1"]["cv"] == 0.0)

with tempfile.TemporaryDirectory() as td:
    try:
        az.summarize_campaign(campaign_paths(td)[:-1], TEST_MANIFEST_SHA256)
        check("29-sample campaign rejected", False)
    except SystemExit:
        check("29-sample campaign rejected", True)

with tempfile.TemporaryDirectory() as td:
    def mutate_boot_reuse(doc, boot, repeat):
        if boot == 3:
            doc["host"]["host_boot_index"] = 2
        return doc
    try:
        az.summarize_campaign(campaign_paths(td, mutate=mutate_boot_reuse), TEST_MANIFEST_SHA256)
        check("boot reuse rejected", False)
    except SystemExit:
        check("boot reuse rejected", True)

with tempfile.TemporaryDirectory() as td:
    def mutate_gap(doc, boot, repeat):
        if boot == 2 and repeat == 7:
            return archive_doc(build(run_sequence=9), host_boot_index=boot)
        return doc
    try:
        az.summarize_campaign(campaign_paths(td, mutate=mutate_gap), TEST_MANIFEST_SHA256)
        check("sequence gap rejected", False)
    except SystemExit:
        check("sequence gap rejected", True)

with tempfile.TemporaryDirectory() as td:
    def mutate_invalid(doc, boot, repeat):
        if boot == 1 and repeat == 3:
            return archive_doc(build(run_sequence=repeat, golden_window_crc=0xDEAD),
                               host_boot_index=boot)
        return doc
    try:
        az.summarize_campaign(campaign_paths(td, mutate=mutate_invalid), TEST_MANIFEST_SHA256)
        check("invalid sample rejected", False)
    except SystemExit:
        check("invalid sample rejected", True)

with tempfile.TemporaryDirectory() as td:
    def mutate_manifest(doc, boot, repeat):
        if boot == 3 and repeat == 10:
            return archive_doc(campaign_payload(boot, repeat, 160),
                               man=manifest(expected_return_address=LR + 4),
                               host_boot_index=boot)
        return doc
    try:
        az.summarize_campaign(campaign_paths(td, mutate=mutate_manifest), TEST_MANIFEST_SHA256)
        check("manifest mismatch rejected", False)
    except SystemExit:
        check("manifest mismatch rejected", True)

with tempfile.TemporaryDirectory() as td:
    report = az.summarize_campaign(
        campaign_paths(td, per_boot_primary={
            1: [100] * 10,
            2: [100] * 10,
            3: [100] * 10,
        }), TEST_MANIFEST_SHA256
    )
    check("no-excursion campaign stays unresolved",
          report["floor_excursion"]["status"] == "unresolved_no_excursion")

print()
print("passed=%d failed=%d" % (passed, failed))
raise SystemExit(1 if failed else 0)
