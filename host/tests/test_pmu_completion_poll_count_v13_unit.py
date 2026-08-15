"""PMU completion-poll count V13 host-contract unit fixture."""

import hashlib
import json
import math
import os
import struct
import sys
import tempfile
import zlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
HOST_ROOT = os.path.join(REPO_ROOT, "host")
CANONICAL_MANIFEST_PATH = "/tmp/pmu_completion_poll_count_v13_manifest.json"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if HOST_ROOT not in sys.path:
    sys.path.insert(0, HOST_ROOT)

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
        check(name, True, str(exc)[:120])


def require_v13_modules():
    import host.analyze_pmu_completion_poll_count_v13 as az
    import host.run_pmu_completion_poll_count_v13 as rv13
    import host.runner_proto_pmu_completion_poll_count_v13 as v13

    return az, rv13, v13


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


def fallback_manifest():
    return {
        "artifact_bundle_sha256": hex64("0"),
        "artifact_sha256": {
            "app_bin": hex64("1"),
            "authoritative_v12_elf": "cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401",
            "authoritative_v12_nm": hex64("2"),
            "authoritative_v12_objdump": hex64("3"),
            "cross_elf_evidence": hex64("4"),
            "ddr_bin": hex64("5"),
            "elf": hex64("6"),
            "interface_header": hex64("7"),
            "map": hex64("8"),
            "preprocessed_runner": hex64("9"),
            "regs_header": hex64("a"),
            "retained_v12_base_pmu_evidence": hex64("b"),
            "retained_v12_executable_evidence": hex64("c"),
            "runner_generated": hex64("d"),
            "runner_record_wire_evidence": hex64("e"),
            "v13_dwarf": hex64("f"),
            "v13_nm": hex64("0"),
            "v13_objdump": hex64("1"),
            "vectors_bin": hex64("2"),
            "vendor_generated": hex64("3"),
            "vendor_object": hex64("4"),
        },
        "authoritative_v12_elf_sha256": "cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401",
        "build_evidence_sha256": {
            "authoritative_v12_elf": "cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401",
            "authoritative_v12_nm": hex64("5"),
            "authoritative_v12_objdump": hex64("6"),
            "cross_elf_evidence": hex64("7"),
            "interface_header": hex64("8"),
            "preprocessed_runner": hex64("9"),
            "regs_header": hex64("a"),
            "retained_v12_base_pmu_evidence": hex64("b"),
            "retained_v12_executable_evidence": hex64("c"),
            "runner_record_wire_evidence": hex64("d"),
            "v13_dwarf": hex64("e"),
            "v13_nm": hex64("f"),
            "v13_objdump": hex64("0"),
            "vendor_object": hex64("1"),
        },
        "build_id": "0x33314950",
        "cross_elf_evidence": {
            "helper_leaf_no_stack_access": True,
            "remaining_back_edge_induction_register": "r3",
            "remaining_from_back_edge_induction": True,
            "remaining_publication_register": "r2",
            "remaining_store_after_p2_exactly_once": True,
            "remaining_store_timeout_unreachable": True,
            "synchronized_induction_pair": True,
            "v12_v13_poll_loop_equivalence_scope": "per_iteration_loop_region",
            "v12_v13_poll_loop_semantically_equivalent": True,
            "v13_extra_per_iteration_instruction_count_zero": True,
            "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
        },
        "cross_elf_evidence_proof_scope": "per_iteration_loop_region",
        "cross_elf_evidence_sha256": hex64("2"),
        "manifest_sha256": hex64("3"),
        "parser_sha256": hex64("4"),
        "retained_v12_base_pmu_evidence": {
            "base_pmu_result": {
                "expected_return_address": 0x3100078C,
                "qualification_mode": "Q1",
                "release_immediate_address": 0x3100078C,
                "ok": True,
            },
            "golden_window_base": "0x90020CC0",
            "golden_window_len": "0x00000100",
            "golden_window_link_symbols_exact": True,
            "performance_qualified": False,
            "retained_v12_base_pmu_limitations": "fixture",
            "retained_v12_base_pmu_proof_scope": "fixture",
            "retained_v12_compiler_contract_exact": True,
            "retained_v12_hprintf_callsite_exact": True,
            "retained_v12_no_pmccntr_cfg_write": True,
            "retained_v12_pmu_hook_order_exact": True,
            "retained_v12_target_object_relocation_exact": True,
            "runtime_golden_output_qualified": False,
            "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
        },
        "retained_v12_base_pmu_evidence_sha256": hex64("5"),
        "retained_v12_base_pmu_limitations": "fixture",
        "retained_v12_base_pmu_proof_scope": "fixture",
        "retained_v12_executable_evidence": {
            "build_id": "0x33314950",
            "cmd0_store_address": "0x31002544",
            "helper_address": "0x31002368",
            "helper_call_target_exact": True,
            "helper_completion_mask_value": "0x00000002",
            "helper_one_direct_callsite": True,
            "helper_status_read_address": "0x31002378",
            "helper_status_register_address": "0x50004004",
            "helper_status_test_address": "0x3100237A",
            "helper_symbol": "v13_poll_completion",
            "history_mask_from_success_status": True,
            "hprintf_callsite_address": "0x31002548",
            "irq_triggered_true_reachable_false": True,
            "nvic_enable_replaced": True,
            "poll_helper_p0_address": "0x3100236E",
            "poll_helper_p1_address": "0x31002392",
            "poll_helper_p2_address": "0x3100239A",
            "retained_v12_cmd_qread_ordering_exact": True,
            "retained_v12_executable_limitations": "fixture",
            "retained_v12_executable_proof_scope": "fixture",
            "retained_v12_hprintf_seam_exact": True,
            "retained_v12_nvic_hard_bypass_exact": True,
            "retained_v12_p0_p1_p2_exact": True,
            "retained_v12_status_history_provenance_exact": True,
            "retained_v12_stock_vector_exact": True,
            "retained_v12_terminal_release_exact": True,
            "runtime_golden_output_qualified": False,
            "runtime_vector_target_address": "0x310023BC",
            "runtime_vector_target_exact": True,
            "runtime_vector_target_symbol": "u85_irq_handler",
            "schema_version": 13,
            "status_success_dataflow_exact": True,
            "success_cmd2_count_2": True,
            "success_cmd2_write_value": "0x00000002",
            "success_cmd2_1_store_address": "0x31002560",
            "success_qread_load_address": "0x31002562",
            "success_cmd2_2_store_address": "0x31002564",
            "terminal_cmd0c_store_address": "0x3100254E",
            "timeout_cmd2_count_1": True,
            "timeout_cmd2_store_address": "0x310024F8",
            "timeout_cmd2_write_value": "0x00000002",
            "timeout_qread_load_address": "0x310024F4",
            "wait_call_address": "0x310024CE",
            "wait_call_target_address": "0x31002368",
        },
        "retained_v12_executable_evidence_sha256": hex64("6"),
        "retained_v12_executable_limitations": "fixture",
        "retained_v12_executable_proof_scope": "fixture",
        "runner_record_wire_evidence": {
            "build_pmu_diag_payload_address": "0x31000B0C",
            "dispatch_address": "0x31001010",
            "dispatch_local_d_copy_source_offset_bytes": 48,
            "dispatch_resp_offset_bytes": 452,
            "dwarf_producer": "GNU C11 fixture",
            "dwarf_required": True,
            "evidence_source": "arm_elf",
            "handle_run_pmu_diag_local_d_fbreg": -1056,
            "handle_run_pmu_diag_resp_fbreg": -652,
            "last_pmu_diag_address": "0x3100514C",
            "memcpy_size_bytes": 404,
            "poll_remaining_field_offset_bytes": 400,
            "runner_record_wire_limitations": "fixture",
            "runner_record_wire_proof_scope": "linked_image_dwarf_exact_locations",
            "runner_record_wire_scope_statement": "fixture",
            "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
            "wire_word_index": 100,
        },
        "runner_record_wire_evidence_sha256": hex64("7"),
        "runner_record_wire_limitations": "fixture",
        "runner_record_wire_proof_scope": "linked_image_dwarf_exact_locations",
        "runner_record_wire_scope_statement": "fixture",
        "runner_source_sha256": hex64("8"),
        "schema_version": 13,
        "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
        "vendor_source_sha256": hex64("9"),
    }


def manifest():
    if os.path.exists(CANONICAL_MANIFEST_PATH):
        with open(CANONICAL_MANIFEST_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    return fallback_manifest()


def build_payload(
    *,
    run_sequence=1,
    poll_result=1,
    remaining=10000,
    build_id=0x33314950,
    schema=13,
    appendix_overrides=None,
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
        0x10A0 if poll_result == 1 else 0,
        0x10AB if poll_result == 1 else 0,
        poll_result,
        0x00020002 if poll_result == 1 else 0,
        int(manifest()["retained_v12_executable_evidence"]["runtime_vector_target_address"], 16) | 1,
        0,
        0,
        0,
        0,
        1 if poll_result == 2 else 0,
        0,
        0,
        0,
        remaining if poll_result == 1 else 0,
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
            "poll_remaining_at_success",
        ]
        for key, value in appendix_overrides.items():
            appendix[appendix_fields.index(key)] = value
    body = prefix + hook + list(pre) + list(internal) + list(post_disable) + list(after_return) + appendix
    total_words = 109
    header_words = v12.PMU_COMPLETION_POLL_V12_HEADER_WORDS
    assert len(body) == total_words - header_words, len(body)
    payload = bytearray(
        struct.pack(
            "<8I",
            v12.PMU_COMPLETION_POLL_V12_MAGIC,
            schema,
            total_words,
            header_words,
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
    _, _, v13 = require_v13_modules()
    man = manifest() if man is None else man
    parsed = v13.parse_pmu_completion_poll_count_v13_payload(raw)
    blob = (json.dumps(man, sort_keys=True) + "\n").encode("utf-8")
    derived = v13.classify_pmu_completion_poll_count_v13_payload(parsed, man)
    return {
        "variant": "PMU_COMPLETION_POLL_COUNT_DIAG_V13",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_path": "manifest.json",
            "manifest_text": blob.decode("utf-8"),
            "manifest_sha256": hashlib.sha256(blob).hexdigest(),
            "artifact_sha256": dict(man["artifact_sha256"]),
        },
        "manifest": json.loads(blob.decode("utf-8")),
        "target": v13.target_fields(parsed),
        "derived": derived if derived["valid"] else None,
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
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, sort_keys=True)
    return path


def average_ranks(values):
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


def pearson(xs, ys):
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    if den_x == 0 or den_y == 0:
        return None
    return num / math.sqrt(den_x * den_y)


def test_schema_and_manifest_contract():
    _, _, v13 = require_v13_modules()
    man = manifest()
    raw = build_payload()
    parsed = v13.parse_pmu_completion_poll_count_v13_payload(raw)
    check("schema exact", parsed.schema_version == 13)
    check("body words exact", v13.PMU_COMPLETION_POLL_COUNT_V13_BODY_WORDS == 101)
    check("payload size exact", len(raw) == 436 == v13.PMU_COMPLETION_POLL_COUNT_V13_PAYLOAD_SIZE)
    check("manifest exact variant", man["variant"] == "PMU_COMPLETION_POLL_COUNT_DIAG_V13")
    check("manifest exact build", man["build_id"] == "0x33314950")
    check("manifest omits flat qualification_mode", "qualification_mode" not in man)
    v13.verify_manifest_identity(man, "fixture")
    if os.path.exists(CANONICAL_MANIFEST_PATH):
        with open(CANONICAL_MANIFEST_PATH, encoding="utf-8") as handle:
            canonical = json.load(handle)
        v13.verify_manifest_identity(canonical, CANONICAL_MANIFEST_PATH)
        check("canonical manifest variant", canonical["variant"] == man["variant"])
    for schema in (8, 9, 10, 11, 12):
        bad = bytearray(raw)
        struct.pack_into("<I", bad, 4, schema)
        rejects(
            "schema %d rejected" % schema,
            lambda payload=bytes(bad): v13.parse_pmu_completion_poll_count_v13_payload(payload),
        )
    rejects(
        "v8 parser rejects v13 payload",
        lambda: v8.parse_pmu_qual_payload(raw),
    )
    rejects(
        "v12 parser rejects v13 payload",
        lambda: v12.parse_pmu_completion_poll_v12_payload(raw),
    )


def test_success_and_timeout_derivation():
    _, rv13, v13 = require_v13_modules()
    man = manifest()
    success = v13.classify_pmu_completion_poll_count_v13_payload(
        v13.parse_pmu_completion_poll_count_v13_payload(build_payload(remaining=10000)),
        man,
    )
    check("first observed poll remaining boundary", success["derived"]["poll_remaining_at_success"] == 10000)
    check("first observed poll iterations boundary", success["derived"]["poll_iterations"] == 1)
    check("first observed poll ratio boundary", success["derived"]["average_cycles_per_observed_poll"] == 32.0)
    final = v13.classify_pmu_completion_poll_count_v13_payload(
        v13.parse_pmu_completion_poll_count_v13_payload(build_payload(remaining=1)),
        man,
    )
    check("10000th poll remaining boundary", final["derived"]["poll_remaining_at_success"] == 1)
    check("10000th poll iterations boundary", final["derived"]["poll_iterations"] == 10000)
    check(
        "submit-to-observed remains authoritative",
        final["derived"]["submit_to_status_completion_observed_cycles"]
        == ((0x10A0 - 0x1000) & 0xFFFFFFFF),
    )
    timeout = v13.classify_pmu_completion_poll_count_v13_payload(
        v13.parse_pmu_completion_poll_count_v13_payload(build_payload(poll_result=2)),
        man,
    )
    check("timeout invalid", timeout["valid"] is False)
    check("timeout archive_write false", timeout["archive_write"] is False)
    check("timeout fresh boot required", timeout["fresh_boot_required"] is True)
    check(
        "timeout emits no remaining/iterations/poll cycle/ratio",
        timeout["derived"] is None,
    )
    with tempfile.TemporaryDirectory() as tempdir:
        out = os.path.join(tempdir, "timeout.json")
        collected = rv13.collect_one(
            raw=build_payload(poll_result=2),
            manifest=man,
            out_path=out,
            host_boot_index=4,
            campaign_state=rv13.CampaignState(),
        )
        check("timeout archive suppressed before write", collected["archive_write"] is False and not os.path.exists(out))


def test_collector_campaign_stop_and_identity():
    _, rv13, _ = require_v13_modules()
    man = manifest()
    state = rv13.CampaignState()
    with tempfile.TemporaryDirectory() as tempdir:
        valid_path = os.path.join(tempdir, "ok.json")
        valid = rv13.collect_one(
            raw=build_payload(run_sequence=1, remaining=9998),
            manifest=man,
            out_path=valid_path,
            host_boot_index=9,
            campaign_state=state,
        )
        check("collector writes valid success", valid["valid"] is True and valid["archive_write"] is True)
        check("collector preserved manifest hashes", valid["record"]["host"]["artifact_sha256"] == man["artifact_sha256"])
        bad_path = os.path.join(tempdir, "bad.json")
        mismatch = rv13.collect_one(
            raw={
                "payload_hex": build_payload(run_sequence=2, remaining=9997).hex(),
                "reread_payload_hex": build_payload(run_sequence=2, remaining=9996).hex(),
            },
            manifest=man,
            out_path=bad_path,
            host_boot_index=9,
            campaign_state=state,
        )
        check("collector aborts on reread mismatch", mismatch["campaign_abort"] is True)
        check("collector never writes invalid record", mismatch["archive_write"] is False and not os.path.exists(bad_path))
        timeout = rv13.collect_one(
            raw=build_payload(run_sequence=3, poll_result=2),
            manifest=man,
            host_boot_index=9,
            campaign_state=state,
        )
        check("timeout blocks rest of boot", timeout["fresh_boot_required"] is True)
        rejects(
            "same boot refused after timeout",
            lambda: rv13.collect_one(
                raw=build_payload(run_sequence=4, remaining=9994),
                manifest=man,
                host_boot_index=9,
                campaign_state=state,
            ),
        )
        resumed = rv13.collect_one(
            raw=build_payload(run_sequence=1, remaining=9999),
            manifest=man,
            host_boot_index=10,
            campaign_state=state,
        )
        check("fresh boot resumes at run1", resumed["valid"] is True)


def test_analyzer_contract():
    az, _, _ = require_v13_modules()
    man = manifest()
    with tempfile.TemporaryDirectory() as tempdir:
        expected_iterations = []
        expected_cycles = []
        paths = []
        for boot in (1, 2, 3):
            for run in range(1, 11):
                remaining = 10000 - ((run - 1) % 4)
                iterations = 10001 - remaining
                poll_cycles = 20 + (iterations * 5) + ((boot - 1) * 2)
                raw = build_payload(
                    run_sequence=run,
                    remaining=remaining,
                    appendix_overrides={
                        "t_poll_entry": 0x1080,
                        "t_status_completion_seen": 0x1080 + poll_cycles,
                        "t_poll_exit": 0x1080 + poll_cycles + 11,
                    },
                )
                expected_iterations.append(iterations)
                expected_cycles.append(poll_cycles)
                paths.append(
                    write_doc(
                        tempdir,
                        "boot%d_run%02d.json" % (boot, run),
                        archive_doc(raw, man=man, host_boot_index=boot),
                    )
                )
        analysis = az.analyze_3x10(paths)
        ranks_i = average_ranks(expected_iterations)
        ranks_c = average_ranks(expected_cycles)
        expected_rho = pearson(ranks_i, ranks_c)
        mean_i = sum(expected_iterations) / len(expected_iterations)
        mean_c = sum(expected_cycles) / len(expected_cycles)
        var_i = sum((value - mean_i) ** 2 for value in expected_iterations) / len(expected_iterations)
        cov_ic = sum(
            (it - mean_i) * (cy - mean_c)
            for it, cy in zip(expected_iterations, expected_cycles)
        ) / len(expected_iterations)
        beta = cov_ic / var_i
        alpha = mean_c - beta * mean_i
        first_residual = expected_cycles[0] - (alpha + beta * expected_iterations[0])
        check("analyzer exact 3x10", analysis["sample_count"] == 30 and analysis["boot_count"] == 3)
        check("analyzer labels remain diagnostic only", analysis["labels"] == az.OUTPUT_LABELS)
        check("analyzer Spearman uses average ranks", abs(analysis["spearman_rho_iterations_vs_poll_observation_cycles"] - expected_rho) < 1e-12)
        check("analyzer OLS alpha", abs(analysis["ols_fit_iterations_to_poll_observation_cycles"]["alpha"] - alpha) < 1e-12)
        check("analyzer OLS beta", abs(analysis["ols_fit_iterations_to_poll_observation_cycles"]["beta"] - beta) < 1e-12)
        check(
            "analyzer residuals per sample",
            abs(analysis["residuals"][0]["residual"] - first_residual) < 1e-12,
        )
        check(
            "analyzer per-boot residual summaries",
            sorted(analysis["per_boot_residual_summary"]) == ["1", "2", "3"],
        )
        check(
            "analyzer floor/excursion counts",
            analysis["hard_floor_count"] + analysis["excursion_count"] == 30,
        )
        constant_paths = []
        for boot in (1, 2, 3):
            for run in range(1, 11):
                raw = build_payload(
                    run_sequence=run,
                    remaining=9998,
                    appendix_overrides={
                        "t_poll_entry": 0x1080,
                        "t_status_completion_seen": 0x1090 + boot,
                        "t_poll_exit": 0x109B + boot,
                    },
                )
                constant_paths.append(
                    write_doc(
                        tempdir,
                        "constant_boot%d_run%02d.json" % (boot, run),
                        archive_doc(raw, man=man, host_boot_index=boot),
                    )
                )
        constant = az.analyze_3x10(constant_paths)
        check(
            "zero iteration variance returns None",
            constant["spearman_rho_iterations_vs_poll_observation_cycles"] is None
            and constant["ols_fit_iterations_to_poll_observation_cycles"] is None,
        )


def main():
    test_schema_and_manifest_contract()
    test_success_and_timeout_derivation()
    test_collector_campaign_stop_and_identity()
    test_analyzer_contract()
    print("\nPassed %d / %d tests" % (passed, passed + failed))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
