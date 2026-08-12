"""PMU completion-poll V12 host-contract unit fixture."""

import hashlib
import json
import os
import struct
import sys
import tempfile
import zlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
FIRMWARE_ROOT = os.path.join(REPO_ROOT, "firmware", "Selftest_pmu_diag")
HOST_ROOT = os.path.join(REPO_ROOT, "host")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if HOST_ROOT not in sys.path:
    sys.path.insert(0, HOST_ROOT)
if FIRMWARE_ROOT not in sys.path:
    sys.path.insert(0, FIRMWARE_ROOT)

import host.analyze_pmu_completion_poll_v12 as az
import host.run_pmu_completion_poll_v12 as rv12
import host.runner_proto as v8
import host.runner_proto_pmu_completion_poll_v12 as v12

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-68s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def rejects(name, fn):
    try:
        fn()
        check(name, False, "accepted")
    except BaseException as exc:
        check(name, True, str(exc)[:80])


def snap(cfg=0, cyc=0, armed=True, glob=True, stable=1, ovs=0):
    global_en = 1 << v8.PMU_PMCR_CNT_EN_BIT
    armed_bit = 1 << v8.PMU_PMCNTEN_CYCLE_BIT
    return (
        global_en if glob else 0,
        armed_bit if armed else 0,
        cfg,
        cyc & 0xFFFFFFFF,
        (cyc >> 32) & 0xFFFF,
        stable,
        0,
        ovs,
    )


def hex64(ch):
    return ch * 64


def manifest(**over):
    doc = {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "schema_version": 12,
        "build_id": "0x%08X" % v12.PMU_COMPLETION_POLL_V12_BUILD_ID,
        "qualification_mode": "Q1",
        "expected_return_address": 0x3100078C,
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
            "APP.BIN": hex64("a"),
            "VECTORS.BIN": hex64("b"),
            "DDR.BIN": hex64("c"),
        },
        "build_evidence_sha256": {
            "runner_pmu_completion_poll_v12.elf": hex64("d"),
            "runner_pmu_completion_poll_v12.map": hex64("e"),
            "generated_runner.c": hex64("f"),
            "generated_vendor_u85.c": hex64("0"),
            "checker_disassembly.txt": hex64("1"),
            "checker_nm.txt": hex64("2"),
        },
        "helper_symbol": "v12_poll_completion",
        "runtime_vector_target_symbol": "u85_irq_handler",
        "runtime_vector_target_address": "0x20001000",
        "wait_call_address": "0x00001200",
        "hprintf_callsite_address": "0x31000788",
        "helper_status_read_address": "0x0000100c",
        "helper_status_test_address": "0x00001010",
        "poll_helper_p0_address": "0x00001004",
        "poll_helper_p1_address": "0x00001014",
        "poll_helper_p2_address": "0x00001018",
        "success_cmd2_1_store_address": "0x00001234",
        "success_qread_load_address": "0x00001238",
        "success_cmd2_2_store_address": "0x0000123c",
        "timeout_qread_load_address": "0x00001274",
        "timeout_cmd2_store_address": "0x00001278",
        "cmd0_store_address": "0x00001290",
        "terminal_cmd0c_store_address": "0x000012a0",
    }
    doc.update(over)
    return doc


def build_payload(
    *,
    run_sequence=1,
    poll_result=v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS,
    appendix_overrides=None,
    build_id=v12.PMU_COMPLETION_POLL_V12_BUILD_ID,
    schema=12,
):
    pre = snap(cyc=1000)
    internal = snap(cyc=1160)
    post_disable = snap(cyc=1160, glob=False)
    after_return = snap(cyc=0, armed=False, glob=False)
    prefix = [
        schema,
        build_id,
        1, 0, run_sequence,
        0, 0, 0,
        0, v8.RUN_VALID_REQUIRED_MASK,
        0x1111, 0x2222, 0x3333,
        1, 100, 300, 240,
        0, 58, 8,
        v8.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
        v8.PMU_DIAG_POWER_GUARD_CYCLES, 0xC, 0, 0,
        v8.PMU_DIAG_RESET_GUARD_CYCLES, 0x4000, 0x4001, 1,
        v8.PMU_DIAG_STABILITY_SAMPLES, 1,
        0xC, v8.PMU_QUAL_POWER_SEAM_ID, 0, 0, 0xC, 0,
        v8.PMU_DIAG_GOLDEN_WINDOW_BASE, v8.PMU_DIAG_GOLDEN_WINDOW_LEN,
        v8.GOLDEN_WINDOW_CRC,
    ]
    hook = [1, 1, 1, 1, 1, 1, 0x3100078C, 0x1000, 0x1090, 0, 0, 3, 1]
    appendix = [
        0x1000,
        0x1080,
        0x10A0 if poll_result == v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS else 0,
        0x10D0 if poll_result == v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS else 0,
        poll_result,
        0x00020002 if poll_result == v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS else 0,
        int(manifest()["runtime_vector_target_address"], 16),
        0,
        0,
        0,
        0,
        1 if poll_result == v12.PMU_COMPLETION_POLL_V12_POLL_TIMEOUT else 0,
        0,
        0,
        0,
    ]
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
        for key, value in appendix_overrides.items():
            appendix[appendix_fields.index(key)] = value
    body = prefix + hook + list(pre) + list(internal) + list(post_disable) + list(after_return) + appendix
    total = v12.PMU_COMPLETION_POLL_V12_TOTAL_WORDS
    assert len(body) == v12.PMU_COMPLETION_POLL_V12_BODY_WORDS, len(body)
    payload = bytearray(
        struct.pack(
            "<8I",
            v12.PMU_COMPLETION_POLL_V12_MAGIC,
            schema,
            total,
            v12.PMU_COMPLETION_POLL_V12_HEADER_WORDS,
            run_sequence,
            prefix[9],
            prefix[8],
            0,
        )
        + b"".join(struct.pack("<I", word) for word in body)
    )
    crc = zlib.crc32(bytes(payload[16:28]) + bytes(payload[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", payload, 28, crc)
    return bytes(payload)


def archive_doc(raw, *, man=None, host_boot_index=1):
    man = manifest() if man is None else man
    parsed = v12.parse_pmu_completion_poll_v12_payload(raw)
    blob = (json.dumps(man, sort_keys=True) + "\n").encode("utf-8")
    derived = v12.classify_pmu_completion_poll_v12_payload(parsed, man)
    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_path": "manifest.json",
            "manifest_text": blob.decode("utf-8"),
            "manifest_sha256": hashlib.sha256(blob).hexdigest(),
            "artifact_sha256": dict(man["artifact_sha256"]),
        },
        "manifest": json.loads(blob.decode("utf-8")),
        "target": v12.target_fields(parsed),
        "derived": derived if derived["valid"] else None,
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_payload_hex": raw.hex(),
            "reread_payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }


class Frame:
    def __init__(self, command, sequence, payload=b"", flags=0):
        self.version = 1
        self.command = command
        self.flags = flags
        self.sequence = sequence
        self.payload = payload


def ack(seq):
    return Frame(v8.CMD_RUN_PMU_DIAG | 0x80, seq, b"\x00\x00\x00\x00")


def complete(payload, seq):
    return Frame(v8.CMD_PMU_DIAG_COMPLETE, seq, payload)


def reread_reply(payload, seq):
    return Frame(v8.CMD_GET_PMU_DIAG_RESULT | 0x80, seq, payload)


class FakeLink:
    def __init__(self, run_frames, get_frames):
        self._seq = 40
        self._run_frames = run_frames
        self._get_frames = get_frames
        self.queue = []
        self.sent = []
        self.late_frames = 0
        self.last_pmu_diag_raw = None
        self.last_pmu_diag_reread_raw = None

    def next_sequence(self):
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    def send_raw(self, blob):
        _, _, cmd, _, seq, _ = struct.unpack(v8.HEADER, blob[: struct.calcsize(v8.HEADER)])
        self.sent.append((cmd, seq))
        frames = self._run_frames(seq) if cmd == v8.CMD_RUN_PMU_DIAG else self._get_frames(seq)
        self.queue.extend(frames)

    def read_frame(self, timeout=5.0):
        if not self.queue:
            raise v8.ProtocolError("timed out waiting for a frame")
        return self.queue.pop(0)


def write_doc(root, name, doc):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, sort_keys=True)
    return path


def campaign_paths(root, *, mutate=None):
    paths = []
    for boot in (1, 2, 3):
        for run in range(1, 11):
            raw = build_payload(run_sequence=run)
            doc = archive_doc(raw, host_boot_index=boot)
            if mutate is not None:
                doc = mutate(doc, boot, run)
            paths.append(write_doc(root, "boot%d_run%02d.json" % (boot, run), doc))
    return paths


def test_schema_and_manifest():
    raw = build_payload()
    parsed = v12.parse_pmu_completion_poll_v12_payload(raw)
    check("schema exact", parsed.schema_version == 12)
    check("body words exact", v12.PMU_COMPLETION_POLL_V12_BODY_WORDS == 100)
    check("payload size exact", len(raw) == v12.PMU_COMPLETION_POLL_V12_PAYLOAD_SIZE)
    for schema in (8, 9, 10, 11):
        bad = bytearray(raw)
        struct.pack_into("<I", bad, 4, schema)
        rejects("schema %d rejected" % schema, lambda payload=bytes(bad): v12.parse_pmu_completion_poll_v12_payload(payload))
    rejects("collect_one requires attested manifest", lambda: rv12.collect_one(raw=raw))
    rejects(
        "manifest runtime vector target key required",
        lambda: v12.verify_manifest_identity(
            dict(manifest(), runtime_vector_target_symbol=None), "fixture"
        ),
    )
    rejects(
        "manifest artifact dict exact APP/VECTORS/DDR",
        lambda: v12.verify_manifest_identity(
            dict(manifest(), artifact_sha256={"APP.BIN": hex64("a")}), "fixture"
        ),
    )
    rejects(
        "manifest diagnostic_only required",
        lambda: v12.verify_manifest_identity(
            dict(manifest(), diagnostic_only=False), "fixture"
        ),
    )
    relocated = manifest(
        runtime_vector_target_address="0x20001234",
        expected_return_address=0x3100078C,
    )
    relocated_raw = build_payload(
        appendix_overrides={"installed_vector": int(relocated["runtime_vector_target_address"], 16)}
    )
    relocated_parsed = v12.parse_pmu_completion_poll_v12_payload(relocated_raw)
    relocated_derived = v12.classify_pmu_completion_poll_v12_payload(relocated_parsed, relocated)
    check("relocated stock vector address accepted", relocated_derived["valid"] is True)
    stale_derived = v12.classify_pmu_completion_poll_v12_payload(
        relocated_parsed, manifest()
    )
    check(
        "stale hardcoded vector address rejected",
        "runtime_vector_matches_manifest" in stale_derived["invalid_reasons"],
    )


def test_collect_raw_and_timeout():
    man = manifest()
    raw = build_payload()
    with tempfile.TemporaryDirectory() as tempdir:
        out = os.path.join(tempdir, "ok.json")
        res = rv12.collect_one(raw=raw, manifest=man, out_path=out, host_boot_index=1)
        check("collect_one valid success", res["valid"] is True and res["archive_write"] is True)
        check("collect_one wrote archive", os.path.exists(out))

        mismatch_out = os.path.join(tempdir, "mismatch.json")
        reread = bytearray(raw)
        reread[80] ^= 0x01
        mismatch_raw = {
            "payload_hex": raw.hex(),
            "reread_payload_hex": bytes(reread).hex(),
        }
        mismatch = rv12.collect_one(
            raw=mismatch_raw, manifest=man, out_path=mismatch_out, host_boot_index=1
        )
        check("raw reread mismatch aborts", mismatch["campaign_abort"] is True)
        check("raw reread mismatch writes nothing", not os.path.exists(mismatch_out))

        artifact_bad_out = os.path.join(tempdir, "artifact_bad.json")
        rejects(
            "artifact digest mismatch rejects before write",
            lambda: rv12.collect_one(
                raw=raw,
                manifest=man,
                artifact_sha256=dict(man["artifact_sha256"], **{"APP.BIN": hex64("0")}),
                out_path=artifact_bad_out,
                host_boot_index=1,
            ),
        )
        check("artifact digest mismatch opens no output", not os.path.exists(artifact_bad_out))

        manifest_blob_bad_out = os.path.join(tempdir, "manifest_blob_bad.json")
        rejects(
            "manifest_blob mismatch rejects before write",
            lambda: rv12.collect_one(
                raw=raw,
                manifest=man,
                manifest_blob=(json.dumps(dict(man, helper_symbol="wrong"), sort_keys=True) + "\n").encode("utf-8"),
                out_path=manifest_blob_bad_out,
                host_boot_index=1,
            ),
        )
        check("manifest_blob mismatch opens no output", not os.path.exists(manifest_blob_bad_out))

        timeout_raw = build_payload(poll_result=v12.PMU_COMPLETION_POLL_V12_POLL_TIMEOUT)
        timeout_out = os.path.join(tempdir, "timeout.json")
        timeout = rv12.collect_one(
            raw=timeout_raw, manifest=man, out_path=timeout_out, host_boot_index=2
        )
        check("timeout aborts campaign", timeout["campaign_abort"] is True)
        check("timeout requires fresh boot", timeout["fresh_boot_required"] is True)
        check("timeout writes nothing", not os.path.exists(timeout_out))


def test_transport_contract():
    payload = build_payload()
    link = FakeLink(
        lambda seq: [ack(seq), complete(payload, seq)],
        lambda seq: [reread_reply(payload, seq)],
    )
    res, raw, reread = rv12.collect_pmu_completion_poll_v12(link)
    check("ACK/COMPLETE/GET exchange accepted", raw == payload and reread == payload)
    check("transport parsed exact run", res.run_sequence == 1)
    rejects(
        "no ACK rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [], lambda seq: [])
        ),
    )
    rejects(
        "ACK without COMPLETE rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq)], lambda seq: [])
        ),
    )
    rejects(
        "COMPLETE before ACK rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [complete(payload, seq), ack(seq)], lambda seq: [reread_reply(payload, seq)])
        ),
    )
    rejects(
        "duplicate ACK rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq), ack(seq), complete(payload, seq)], lambda seq: [reread_reply(payload, seq)])
        ),
    )
    rejects(
        "duplicate COMPLETE rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq), complete(payload, seq), complete(payload, seq)], lambda seq: [reread_reply(payload, seq)])
        ),
    )
    rejects(
        "GET reread mismatch rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq), complete(payload, seq)], lambda seq: [reread_reply(build_payload(run_sequence=1, appendix_overrides={"t_poll_exit": 0x10E0}), seq)])
        ),
    )
    rejects(
        "GET empty rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq), complete(payload, seq)], lambda seq: [reread_reply(b"", seq)])
        ),
    )
    rejects(
        "GET wrong command rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(lambda seq: [ack(seq), complete(payload, seq)], lambda seq: [Frame(v8.CMD_PING | 0x80, seq, payload)])
        ),
    )
    stale_seq = FakeLink(
        lambda seq: [ack(seq), Frame(v8.CMD_PMU_DIAG_COMPLETE, seq - 1, b"stale"), complete(payload, seq)],
        lambda seq: [Frame(v8.CMD_GET_PMU_DIAG_RESULT | 0x80, seq - 1, b"late"), reread_reply(payload, seq)],
    )
    _, raw2, reread2 = rv12.collect_pmu_completion_poll_v12(stale_seq)
    check("stale sequence frames skipped", raw2 == payload and reread2 == payload and stale_seq.late_frames == 2)
    rejects(
        "NACK rejected",
        lambda: rv12.collect_pmu_completion_poll_v12(
            FakeLink(
                lambda seq: [Frame(v8.NACK, seq, bytes([0x60, 2]), flags=3)],
                lambda seq: [],
            )
        ),
    )


def test_campaign_state_stop_gate():
    state = rv12.CampaignState()
    man = manifest()
    for run in (1, 2, 3):
        out = rv12.collect_one(
            raw=build_payload(run_sequence=run),
            manifest=man,
            host_boot_index=2,
            campaign_state=state,
        )
        check("boot2 run%d success before timeout" % run, out["valid"] is True)
    timeout = rv12.collect_one(
        raw=build_payload(
            run_sequence=4,
            poll_result=v12.PMU_COMPLETION_POLL_V12_POLL_TIMEOUT,
        ),
        manifest=man,
        host_boot_index=2,
        campaign_state=state,
    )
    check("boot2 run4 timeout recorded", timeout["fresh_boot_required"] is True)
    rejects(
        "boot2 run5 refused after timeout",
        lambda: rv12.collect_one(
            raw=build_payload(run_sequence=5),
            manifest=man,
            host_boot_index=2,
            campaign_state=state,
        ),
    )
    out = rv12.collect_one(
        raw=build_payload(run_sequence=1),
        manifest=man,
        host_boot_index=3,
        campaign_state=state,
    )
    check("fresh boot 3 resumes at run1", out["valid"] is True)


def test_analyzer_contract():
    with tempfile.TemporaryDirectory() as tempdir:
        paths = campaign_paths(tempdir)
        analysis = az.analyze_3x10(paths)
        check("analyze_3x10 marks campaign valid", analysis["campaign_valid"] is True)
        check("analyze_3x10 exact 3x10", analysis["sample_count"] == 30 and analysis["boot_count"] == 3)
        check("analyze_3x10 exact labels", analysis["labels"] == az.OUTPUT_LABELS)

        drift_target = json.loads(open(paths[0], encoding="utf-8").read())
        drift_target["target"]["t_poll_exit"] += 4
        drift_target_path = write_doc(tempdir, "drift_target.json", drift_target)
        rejects("analyzer rejects target drift", lambda: az.load(drift_target_path))

        drift_derived = json.loads(open(paths[1], encoding="utf-8").read())
        drift_derived["derived"]["derived"]["submit_to_status_completion_observed_cycles"] += 1
        drift_derived_path = write_doc(tempdir, "drift_derived.json", drift_derived)
        rejects("analyzer rejects derived drift", lambda: az.load(drift_derived_path))

        drift_manifest = json.loads(open(paths[2], encoding="utf-8").read())
        drift_manifest["host"]["artifact_sha256"]["APP.BIN"] = hex64("0")
        drift_manifest_path = write_doc(tempdir, "drift_manifest.json", drift_manifest)
        rejects("analyzer rejects host/manifest artifact mismatch", lambda: az.load(drift_manifest_path))

        timeout_paths = campaign_paths(
            tempdir,
            mutate=lambda doc, boot, run: archive_doc(
                build_payload(
                    run_sequence=run,
                    poll_result=(
                        v12.PMU_COMPLETION_POLL_V12_POLL_TIMEOUT
                        if boot == 2 and run == 4
                        else v12.PMU_COMPLETION_POLL_V12_POLL_SUCCESS
                    ),
                ),
                host_boot_index=boot,
            ),
        )
        rejects("analyze_3x10 rejects timeout campaign", lambda: az.analyze_3x10(timeout_paths))


def test_pretransport_fail_closed():
    class GuardLink:
        def __init__(self):
            self.touched = False

        def send_raw(self, blob):
            self.touched = True
            raise AssertionError("transport must not start")

    man = manifest()
    raw = build_payload()
    link = GuardLink()
    rejects(
        "invalid manifest blocks transport open",
        lambda: rv12.collect_one(
            link=link,
            raw=raw,
            manifest=dict(man, diagnostic_only=False),
            host_boot_index=1,
        ),
    )
    check("invalid manifest kept transport closed", link.touched is False)
    link = GuardLink()
    rejects(
        "artifact mismatch blocks transport open",
        lambda: rv12.collect_one(
            link=link,
            raw=raw,
            manifest=man,
            artifact_sha256=dict(man["artifact_sha256"], **{"APP.BIN": hex64("0")}),
            host_boot_index=1,
        ),
    )
    check("artifact mismatch kept transport closed", link.touched is False)


def run_checks():
    test_schema_and_manifest()
    test_collect_raw_and_timeout()
    test_transport_contract()
    test_campaign_state_stop_gate()
    test_analyzer_contract()
    test_pretransport_fail_closed()


if __name__ == "__main__":
    run_checks()
    if failed:
        raise SystemExit("FAILED %d checks" % failed)
