"""Re-derive the schema-v8 qualification verdict from collected JSON files.

Each file comes from run_pmu_qual.py on an INDEPENDENT reboot. Nothing here
trusts the parsed copies inside the JSON: the archived raw payload is
re-parsed and its CRC re-verified, the archived manifest BYTES are re-hashed
and re-parsed, and the record is re-bound to that manifest -- so the report is
reproduced from the wire bytes and the build attestation alone.

  python3 analyze_pmu_qual.py --q1 results/qual_q1_boot2.json
  python3 analyze_pmu_qual.py --q0 results/qual_q0_boot1.json \
                              --q1 results/qual_q1_boot2.json

With both files the report adds a Q0/Q1 functional-equivalence section. That
section compares LOGICAL shape -- the same caller, the same address-normalized
callsite, the same vendor object, the same functional outputs -- and each
mode's observed LR against ITS OWN manifest. Q0 and Q1 are separate links, so
their numeric callsite addresses MAY differ; whether they do is a property of
a given pair of builds and not a guarantee either way. Cross-mode numeric LR
equality is therefore never a term: it is neither required nor forbidden.

The only number this report will ever print as a measurement is
npu_pmu_window_cycles, and only when every validity term holds. It is a
counter window over the vendor call, nothing more: Q0 and the v7 DIAG deltas
are diagnostic evidence and are never promoted to performance here.
"""

import argparse
import hashlib
import json

from run_pmu_qual import (BIN_FILES, verify_manifest_identity,
                          verify_record_identity)
from runner_proto import (GOLDEN_WINDOW_CRC, PMU_DIAG_GOLDEN_WINDOW_BASE,
                          PMU_DIAG_GOLDEN_WINDOW_LEN, PMU_QUAL_MODES,
                          RUN_VALID_REQUIRED_MASK, classify_pmu_qual,
                          parse_pmu_qual_payload)


def _raw_payload(path: str, raw_meta: dict, key: str, digest_key: str) -> bytes:
    if key not in raw_meta:
        raise SystemExit(
            "FAIL %s: no %s archived -- re-collect, parsed fields alone are "
            "not evidence" % (path, key))
    try:
        blob = bytes.fromhex(raw_meta[key])
    except (TypeError, ValueError) as exc:
        # A hand-edited or truncated archive must fail closed with a verdict,
        # not with a traceback that reads like a tool bug.
        raise SystemExit("FAIL %s: %s is not a hex payload: %s"
                         % (path, key, exc))
    if hashlib.sha256(blob).hexdigest() != raw_meta.get(digest_key):
        raise SystemExit("FAIL %s: %s does not match its recorded %s"
                         % (path, key, digest_key))
    return blob


def load(path: str, want_mode: str):
    """Admit one collected file, or refuse it. Returns (result, document)."""
    with open(path) as f:
        doc = json.load(f)
    host = doc.get("host") or {}
    raw_meta = doc.get("raw") or {}

    if host.get("mode") != want_mode:
        raise SystemExit("FAIL %s: collected in mode %r but given as %s"
                         % (path, host.get("mode"), want_mode))
    if "host_boot_index" not in host:
        raise SystemExit("FAIL %s: missing host_boot_index" % path)

    # Both halves of the sample, each proven against its own digest, then
    # proven equal. A single boolean in the file would be the collector
    # marking its own homework.
    raw = _raw_payload(path, raw_meta, "payload_hex", "payload_sha256")
    reread = _raw_payload(path, raw_meta, "reread_payload_hex",
                          "reread_payload_sha256")
    if raw != reread:
        raise SystemExit(
            "FAIL %s: the archived GET re-read differs from the archived "
            "COMPLETE payload -- the two halves of the sample disagree" % path)
    if raw_meta.get("reread_matches_run_payload") is not True:
        raise SystemExit(
            "FAIL %s: the collector did not (or could not) prove the "
            "GET_PMU_DIAG_RESULT re-read matched the completion payload -- "
            "re-collect" % path)

    res = parse_pmu_qual_payload(raw)  # re-verifies magic/schema/length/CRC

    # The manifest is re-derived from its archived BYTES: re-hashed, re-parsed,
    # and required to agree with the parsed copy the collector stored.
    text = host.get("manifest_text")
    if not isinstance(text, str):
        raise SystemExit(
            "FAIL %s: no manifest bytes archived -- the callsite attestation "
            "cannot be re-derived" % path)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != host.get("manifest_sha256"):
        raise SystemExit("FAIL %s: archived manifest bytes do not match their "
                         "recorded SHA-256" % path)
    try:
        manifest = json.loads(text)
    except ValueError as exc:
        raise SystemExit("FAIL %s: archived manifest bytes are not JSON: %s"
                         % (path, exc))
    if doc.get("manifest") != manifest:
        raise SystemExit(
            "FAIL %s: the archived manifest document disagrees with the "
            "manifest bytes it claims to be a parse of" % path)
    doc["manifest"] = manifest

    verify_manifest_identity(manifest, want_mode, path)
    verify_record_identity(res, manifest, want_mode)

    artifacts = manifest.get("artifact_sha256") or {}
    deployed = host.get("artifact_sha256") or {}
    for name in BIN_FILES:
        if not deployed.get(name):
            raise SystemExit("FAIL %s: missing deployed %s hash -- deployment "
                             "provenance incomplete" % (path, name))
        if deployed[name] != artifacts.get(name):
            raise SystemExit(
                "FAIL %s: deployed %s %s is not the manifest's %s"
                % (path, name, deployed[name], artifacts.get(name)))
    return res, doc


def snapshot_row(snap) -> str:
    return ("cfg=0x%08X armed=%d glob=%d cyc=%d stable=%d retries=%d ovf=%d"
            % (snap.pmccntr_cfg, int(snap.armed), int(snap.global_enable),
               snap.cycle48, snap.cycle_read_stable, snap.cycle_read_retries,
               int(snap.cycle_overflow)))


def report(label: str, res, doc: dict) -> None:
    manifest = doc["manifest"]
    host = doc["host"]
    cls = classify_pmu_qual(res, manifest)

    print("=== %s identity and callsite attestation ===" % label)
    print("  mode=%s build=0x%08X boot=%d run_sequence=%d rc=%d flags=0x%02X"
          % (label, res.build_id, host["host_boot_index"], res.run_sequence,
             res.run_rc, res.valid_flags))
    print("  manifest %s" % host["manifest_path"])
    print("    sha256              %s" % host["manifest_sha256"])
    print("    caller_symbol       %s" % manifest["caller_symbol"])
    print("    stop store          0x%08X" % manifest["stop_store_address"])
    print("    target call         0x%08X" % manifest["target_call_address"])
    print("    expected_return_address 0x%08X"
          % manifest["expected_return_address"])
    print("    release store       0x%08X (immediate #%d)"
          % (manifest["release_store_address"],
             manifest["release_immediate_value"]))
    print("    callsite_disassembly_sha256 %s"
          % manifest["callsite_disassembly_sha256"])
    print("    target relocation   %s against %r"
          % (manifest["object_target_relocation_type"],
             manifest["object_target_relocation_symbol"]))
    print("    vendor source/object %s / %s"
          % (manifest["vendor_source_sha256"][:16],
             manifest["vendor_object_sha256"][:16]))
    if "hook_order_sha256" in manifest:
        print("    hook_order_sha256   %s" % manifest["hook_order_sha256"])
    print("  observed callsite LR 0x%08X -> %s (compared only with the %s "
          "manifest)"
          % (res.hook_callsite_lr_observed,
             "MATCH" if res.hook_callsite_lr_observed
             == manifest["expected_return_address"] else "MISMATCH", label))
    for name in BIN_FILES:
        print("  deployed %-11s %s" % (name, host["artifact_sha256"][name]))

    print("=== %s start boundary ===" % label)
    print("  start_sequence_id=%d power_guard_cycles=%d reset_guard_cycles=%d"
          % (res.start_sequence_id, res.power_guard_cycles,
             res.reset_guard_cycles))
    print("  power: entry cmd=0x%08X -> hold cmd=0x%08X status=0x%08X"
          % (res.npu_cmd_before_power_request,
             res.npu_cmd_after_power_request,
             res.npu_status_after_power_request))
    print("  PMU program: pmcr_after_guard=0x%08X pmcr_after_program=0x%08X "
          "armed_after_program=%d stability=%d/%d"
          % (res.pmcr_after_reset_guard, res.pmcr_after_program,
             res.armed_after_program, res.program_stable,
             res.program_stability_reads))
    print("  cfg_write: performed=%d value=0x%08X readback=0x%08X "
          "(v8 writes none by contract)"
          % (res.cfg_write_performed, res.cfg_write_value,
             res.cfg_readback_after_write))

    print("=== %s raw PMU snapshots ===" % label)
    print("  (only pre and internal_pre_release are authoritative; the vendor "
          "release wipes the bank, so after_return reads zeroed by design)")
    for name, snap in (("pre", res.pre),
                       ("internal_pre_release", res.internal_pre_release),
                       ("internal_post_disable", res.internal_post_disable),
                       ("after_return", res.after_return)):
        print("  %-22s %s" % (name, snapshot_row(snap)))

    print("=== %s hook evidence ===" % label)
    print("  hook_armed=%d hook_arm_consumed=%d hook_detected_count=%d "
          "hook_fired_count=%d hook_snapshot_valid=%d"
          % (res.hook_armed, res.hook_arm_consumed, res.hook_detected_count,
             res.hook_fired_count, res.hook_snapshot_valid))
    print("  hook_callsite_lr_observed=0x%08X npu_cmd_at_hook=0x%08X "
          "pmcr_disable_readback_at_hook=0x%08X"
          % (res.hook_callsite_lr_observed, res.npu_cmd_at_hook,
             res.pmcr_disable_readback_at_hook))
    print("  hook_entry_timestamp=%d hook_exit_timestamp=%d "
          "t_call_enter=%d t_call_return=%d t_pmu_disable=%d ts_valid=%d"
          % (res.hook_entry_timestamp, res.hook_exit_timestamp,
             res.t_call_enter, res.t_call_return, res.t_pmu_disable,
             res.ts_source_valid))
    print("  hook_pmu_mmio_read_count=%d hook_pmu_mmio_write_count=%d "
          "(window totals %d / %d, hook counts are a subset)"
          % (res.hook_pmu_mmio_read_count, res.hook_pmu_mmio_write_count,
             res.pmu_mmio_read_count_delta, res.pmu_mmio_write_count_delta))
    print("  npu_cmd_after_return=0x%08X (vendor terminal release) "
          "corroboration cmd=0x%08X status=0x%08X"
          % (res.npu_cmd_after_return, res.npu_cmd_after_seam,
             res.npu_status_after_seam))

    print("=== %s inference outputs ===" % label)
    print("  golden window [0x%08X +0x%X] crc=0x%08X -> %s"
          % (res.golden_window_base, res.golden_window_len,
             res.golden_window_crc,
             "GOLDEN" if cls["terms"]["golden_window_ok"] else "MISMATCH"))
    print("  expected      [0x%08X +0x%X] crc=0x%08X"
          % (PMU_DIAG_GOLDEN_WINDOW_BASE, PMU_DIAG_GOLDEN_WINDOW_LEN,
             GOLDEN_WINDOW_CRC))
    print("  output_crc=0x%08X poison_crc=0x%08X result_region_crc=0x%08X "
          "(region crc is corroboration only, never a gate)"
          % (res.output_crc, res.poison_crc, res.result_region_crc))

    print("=== %s verdict ===" % label)
    print("  raw_delta_diagnostic=%d reset_to_zero=%s"
          % (cls["raw_delta_diagnostic"], cls["reset_to_zero"]))
    if cls["valid"]:
        print("  npu_pmu_window_cycles: %d" % cls["npu_pmu_window_cycles"])
        print("  (a PMU cycle-counter window over the vendor call under the "
              "attested callsite -- not a wall-clock figure and not a "
              "production baseline)")
    else:
        print("  npu_pmu_window_cycles: INVALID")
        for reason in cls["invalid_reasons"]:
            print("    FAIL %s" % reason)
        if res.qualification_mode == PMU_QUAL_MODES["Q0"]:
            print("  (Q0 is the detect-only baseline: invalid as a measurement "
                  "BY DESIGN, and its raw delta is never promoted to one)")


def functional_equivalence(q0, q1):
    """Do the two images differ ONLY in the hook, and did they do the same
    functional work?

    Every term is either logical shape (same caller, same address-normalized
    callsite, same vendor object) or a functional output. The two modes are
    separate links, so their numeric callsite addresses MAY differ -- today's
    pair happens to land on the same one. Each observed LR is therefore
    checked against its OWN manifest, and no term compares the two numbers
    with each other in either direction.
    """
    r0, d0 = q0
    r1, d1 = q1
    m0, m1 = d0["manifest"], d1["manifest"]

    checks = {
        "same_caller_symbol": m0["caller_symbol"] == m1["caller_symbol"],
        "same_vendor_source": (m0["vendor_source_sha256"]
                               == m1["vendor_source_sha256"]),
        "same_vendor_object": (m0["vendor_object_sha256"]
                               == m1["vendor_object_sha256"]),
        "same_test_cpm": m0["test_cpm"] == m1["test_cpm"],
        # Address-normalized: this is the whole reason the two links can be
        # compared at all.
        "same_normalized_callsite_shape": (
            m0["callsite_disassembly_sha256"]
            == m1["callsite_disassembly_sha256"]),
        "same_release_immediate": (m0["release_immediate_value"]
                                   == m1["release_immediate_value"]),
        # Caller/release ORDER, per mode, from that mode's own addresses.
        "q0_release_follows_return": (m0["release_store_address"]
                                      > m0["expected_return_address"]),
        "q1_release_follows_return": (m1["release_store_address"]
                                      > m1["expected_return_address"]),
        "q0_lr_matches_own_manifest": (r0.hook_callsite_lr_observed
                                       == m0["expected_return_address"]),
        "q1_lr_matches_own_manifest": (r1.hook_callsite_lr_observed
                                       == m1["expected_return_address"]),

        # Same image family, same experiment shape.
        "both_case_a": r0.diag_case == 1 and r1.diag_case == 1,
        "both_normal_build": r0.nc_control_id == 0 and r1.nc_control_id == 0,
        "both_no_cfg_write": (r0.cfg_write_performed == 0
                              and r1.cfg_write_performed == 0),
        "both_start_boundary": (r0.start_sequence_id == r1.start_sequence_id
                                and r0.power_guard_cycles == r1.power_guard_cycles
                                and r0.reset_guard_cycles == r1.reset_guard_cycles),

        # The detector behaved identically; only the side effect differs.
        "both_detected_once": (r0.hook_detected_count == 1
                               and r1.hook_detected_count == 1),
        "both_armed_and_consumed": (r0.hook_armed == 1 and r1.hook_armed == 1
                                    and r0.hook_arm_consumed == 1
                                    and r1.hook_arm_consumed == 1),
        "q0_never_fired": (r0.hook_fired_count == 0
                           and r0.hook_snapshot_valid == 0),
        "q1_fired_once": (r1.hook_fired_count == 1
                          and r1.hook_snapshot_valid == 1),

        # Functional outputs: the hook must not have changed what ran.
        "same_golden_window": (
            (r0.golden_window_base, r0.golden_window_len, r0.golden_window_crc)
            == (r1.golden_window_base, r1.golden_window_len,
                r1.golden_window_crc)),
        "golden_window_is_the_pinned_one": (
            r1.golden_window_base == PMU_DIAG_GOLDEN_WINDOW_BASE
            and r1.golden_window_len == PMU_DIAG_GOLDEN_WINDOW_LEN
            and r1.golden_window_crc == GOLDEN_WINDOW_CRC),
        "same_output_crc": r0.output_crc == r1.output_crc,
        "both_run_rc_ok": r0.run_rc == 0 and r1.run_rc == 0,
        "both_required_flags_ok": (
            (r0.valid_flags & RUN_VALID_REQUIRED_MASK) == RUN_VALID_REQUIRED_MASK
            and (r1.valid_flags & RUN_VALID_REQUIRED_MASK)
            == RUN_VALID_REQUIRED_MASK),
        "both_released_after_return": (
            (r0.npu_cmd_after_return & 0xC) == 0xC
            and (r1.npu_cmd_after_return & 0xC) == 0xC),

        "independent_boots": (d0["host"]["host_boot_index"]
                              != d1["host"]["host_boot_index"]),
    }
    return all(checks.values()), checks


def report_equivalence(q0, q1) -> None:
    r0, d0 = q0
    r1, d1 = q1
    ok, checks = functional_equivalence(q0, q1)
    print("=== Q0/Q1 functional equivalence ===")
    print("  Q0 callsite 0x%08X  Q1 callsite 0x%08X  (%s)"
          % (r0.hook_callsite_lr_observed, r1.hook_callsite_lr_observed,
             "equal in this pair" if r0.hook_callsite_lr_observed
             == r1.hook_callsite_lr_observed else "different in this pair"))
    print("  the two modes are separate links, so these numeric addresses MAY "
          "differ; equality is never required and never forbidden, and each "
          "is compared only with its own manifest")
    print("  boots: Q0=%d Q1=%d"
          % (d0["host"]["host_boot_index"], d1["host"]["host_boot_index"]))
    for name in sorted(checks):
        print("  %-34s %s" % (name, "ok" if checks[name] else "FAIL"))
    print("  equivalence: %s" % ("PASS" if ok else "FAIL"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--q0", help="collected Q0 baseline JSON")
    ap.add_argument("--q1", help="collected Q1 H-PRINTF JSON")
    a = ap.parse_args()
    if not a.q0 and not a.q1:
        raise SystemExit("give --q0, --q1, or both")

    loaded = {}
    for mode, path in (("Q0", a.q0), ("Q1", a.q1)):
        if path:
            loaded[mode] = load(path, mode)
            report(mode, *loaded[mode])
            print()

    if len(loaded) == 2:
        report_equivalence(loaded["Q0"], loaded["Q1"])
        print()

    print("QUALIFICATION ONLY -- no production go, no performance baseline.")


if __name__ == "__main__":
    main()
