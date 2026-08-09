"""Re-derive the A/B/C root-cause verdict from three collected JSON files.

Each file comes from run_pmu_diag.py on an INDEPENDENT reboot. Nothing here
trusts the parsed copies inside the JSON: the canonical raw payload is
re-parsed and its two-slice CRC re-verified, so this analysis reproduces the
verdict from the wire bytes alone.

  python3 analyze_pmu_diag.py \
      --a results/pmu_diag_A_boot1.json \
      --b results/pmu_diag_B_boot2.json \
      --c results/pmu_diag_C_boot3.json

Output order follows the reporting contract: the raw A/B/C snapshot table
first, then the verdict, then (only when a root cause is claimed) the full
B-proof check list.
"""

import argparse
import hashlib
import json

from runner_proto import (PMU_DIAG_BUILD_IDS, PMU_DIAG_SEAM_BUILD_IDS,
                          PMU_DIAG_SEAM_IDS, classify_pmu_diag,
                          parse_pmu_diag_payload, pmu_diag_b_proof,
                          pmu_diag_seam_post_held, pmu_diag_seam_verdict,
                          pmu_diag_verdict)

CASE_IDS = {"A": 1, "B": 2, "C": 3}
BIN_KEYS = ("app_bin_sha256", "vectors_bin_sha256", "ddr_bin_sha256")


def load(path, want_case, expected_build_id=None, build_label=None):
    with open(path) as f:
        doc = json.load(f)
    host = doc.get("host") or {}
    raw_meta = doc.get("raw") or {}
    if "payload_hex" not in raw_meta:
        raise SystemExit("FAIL %s: no raw payload archived -- re-collect, "
                         "parsed fields alone are not evidence" % path)
    raw = bytes.fromhex(raw_meta["payload_hex"])
    if hashlib.sha256(raw).hexdigest() != raw_meta.get("payload_sha256"):
        raise SystemExit("FAIL %s: raw payload does not match its recorded "
                         "SHA-256" % path)
    if raw_meta.get("reread_matches_run_payload") is not True:
        raise SystemExit("FAIL %s: collector did not (or could not) prove the "
                         "GET_PMU_DIAG_RESULT re-read matched the completion "
                         "payload -- re-collect" % path)
    res = parse_pmu_diag_payload(raw)  # re-verifies magic/schema/lengths/CRC
    if expected_build_id is None:
        expected_build_id = PMU_DIAG_BUILD_IDS[want_case]
    if build_label is None:
        build_label = "case %s" % want_case
    if res.build_id != expected_build_id:
        raise SystemExit("FAIL %s: %s expects build_id 0x%08X but the "
                         "payload carries 0x%08X -- wrong artifact"
                         % (path, build_label, expected_build_id, res.build_id))
    if host.get("deployed_case") != want_case:
        raise SystemExit("FAIL %s: host deployed_case=%r but this file was "
                         "given as case %s" % (path, host.get("deployed_case"),
                                               want_case))
    if res.diag_case != CASE_IDS[want_case]:
        raise SystemExit("FAIL %s: target diag_case=%d does not match "
                         "deployed case %s" % (path, res.diag_case, want_case))
    if res.nc_control_id != 0:
        raise SystemExit("FAIL %s: negative-control record (nc=%d) can never "
                         "feed the A/B/C dataset" % (path, res.nc_control_id))
    for key in BIN_KEYS:
        if not host.get(key):
            raise SystemExit("FAIL %s: missing %s -- deployment provenance "
                             "incomplete" % (path, key))
    if "host_boot_index" not in host:
        raise SystemExit("FAIL %s: missing host_boot_index" % path)
    return res, host


def snapshot_row(snap):
    return ("cfg=0x%08X armed=%d glob=%d cyc=%d stable=%d ovf=%d"
            % (snap.pmccntr_cfg, int(snap.armed), int(snap.global_enable),
               snap.cycle48, snap.cycle_read_stable, int(snap.cycle_overflow)))


def load_seam(path, want_seam):
    """Same evidence discipline as load(), with the seam identity added: the
    file's own claim, the host's deployment record and the target's reported
    seam must all agree before a row is admitted."""
    res, host = load(path, "B", PMU_DIAG_SEAM_BUILD_IDS[want_seam],
                     "seam %s" % want_seam)
    if host.get("deployed_seam") != want_seam:
        raise SystemExit("FAIL %s: host deployed_seam=%r but this file was "
                         "given as %s" % (path, host.get("deployed_seam"),
                                          want_seam))
    if res.power_seam_id != PMU_DIAG_SEAM_IDS[want_seam]:
        raise SystemExit("FAIL %s: target power_seam_id=%d does not match "
                         "deployed seam %s" % (path, res.power_seam_id,
                                               want_seam))
    if res.build_id != PMU_DIAG_SEAM_BUILD_IDS[want_seam]:
        raise SystemExit("FAIL %s: seam %s expects build_id 0x%08X but the "
                         "payload carries 0x%08X -- wrong artifact"
                         % (path, want_seam,
                            PMU_DIAG_SEAM_BUILD_IDS[want_seam], res.build_id))
    return res, host


def seam_main(a):
    loaded, hosts = {}, {}
    for seam, path in (("S1", a.s1), ("S2", a.s2), ("S3", a.s3)):
        loaded[seam], hosts[seam] = load_seam(path, seam)

    boots = [hosts[s]["host_boot_index"] for s in ("S1", "S2", "S3")]
    if len(set(boots)) != 3:
        raise SystemExit("FAIL host_boot_index values %r are not distinct -- "
                         "S1/S2/S3 must come from independent reboots" % boots)

    print("=== S1/S2/S3 raw snapshot table (CFG held constant at case B) ===")
    for seam in ("S1", "S2", "S3"):
        res = loaded[seam]
        cls = classify_pmu_diag(res)
        print("%s  boot=%d  build=0x%08X  seq=%d  rc=%d"
              % (seam, hosts[seam]["host_boot_index"], res.build_id,
                 res.run_sequence, res.run_rc))
        print("  cfg_write: performed=%d value=0x%08X readback=0x%08X"
              % (res.cfg_write_performed, res.cfg_write_value,
                 res.cfg_readback_after_write))
        print("  power: entry cmd=0x%08X -> hold 0x%08X status=0x%08X | "
              "rehold=%d guard=%d | after-seam cmd=0x%08X status=0x%08X | "
              "runner release=0x%08X"
              % (res.npu_cmd_before_power_request,
                 res.npu_cmd_after_power_request,
                 res.npu_status_after_power_request,
                 res.power_rehold_performed, res.rehold_guard_cycles,
                 res.npu_cmd_after_seam, res.npu_status_after_seam,
                 res.npu_cmd_after_power_release))
        print("  PMU boundary: pmcr_after_guard=0x%08X pmcr_after_program=0x%08X "
              "arm_after_program=%d stability=%d/%d"
              % (res.pmcr_after_reset_guard, res.pmcr_after_program,
                 res.armed_after_program, res.program_stable,
                 res.program_stability_reads))
        print("  golden window [0x%08X +0x%X] crc=0x%08X -> %s | "
              "region_crc=0x%08X (corroboration only, never a gate)"
              % (res.golden_window_base, res.golden_window_len,
                 res.golden_window_crc,
                 "GOLDEN" if cls["golden_window_ok"] else "MISMATCH",
                 res.result_region_crc))
        for name, snap in (("pre", res.pre), ("post", res.post),
                           ("post_disable", res.post_disable)):
            print("  %-12s %s" % (name, snapshot_row(snap)))
        print("  raw_delta=%d progress=%s post_held=%s"
              % (cls["raw_delta_diagnostic"], cls["progress_observed"],
                 pmu_diag_seam_post_held(res)))

    verdict, detail = pmu_diag_seam_verdict(loaded["S1"], loaded["S2"],
                                            loaded["S3"])
    print()
    print("=== seam verdict ===")
    print(verdict)
    print()
    print("NOTE the diagnostic delta is not a performance metric: extra MMIO "
          "reads sit inside the measured window by design.")
    for seam in ("S1", "S2", "S3"):
        failed = [k for k, v in detail[seam]["checks"].items() if not v]
        if failed:
            print("  %s failed checks: %s" % (seam, ", ".join(failed)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--c")
    ap.add_argument("--s1")
    ap.add_argument("--s2")
    ap.add_argument("--s3")
    a = ap.parse_args()

    seam_given = all((a.s1, a.s2, a.s3))
    case_given = all((a.a, a.b, a.c))
    if seam_given == case_given:
        raise SystemExit("give either --a/--b/--c (CFG experiment) or "
                         "--s1/--s2/--s3 (power-seam experiment)")
    if seam_given:
        seam_main(a)
        return

    loaded = {}
    hosts = {}
    for case, path in (("A", a.a), ("B", a.b), ("C", a.c)):
        loaded[case], hosts[case] = load(path, case)

    boots = [hosts[c]["host_boot_index"] for c in ("A", "B", "C")]
    if len(set(boots)) != 3:
        raise SystemExit("FAIL host_boot_index values %r are not distinct -- "
                         "A/B/C must come from independent reboots" % boots)
    if boots != sorted(boots):
        print("NOTE host_boot_index %r is not monotonic in A,B,C order -- "
              "legal, but confirm the reboot log agrees" % boots)

    print("=== A/B/C raw snapshot table ===")
    for case in ("A", "B", "C"):
        res = loaded[case]
        cls = classify_pmu_diag(res)
        print("case %s  boot=%d  build=0x%08X  seq=%d  rc=%d"
              % (case, hosts[case]["host_boot_index"], res.build_id,
                 res.run_sequence, res.run_rc))
        print("  cfg_write: performed=%d value=0x%08X readback=0x%08X"
              % (res.cfg_write_performed, res.cfg_write_value,
                 res.cfg_readback_after_write))
        print("  power boundary: cmd 0x%08X -> 0x%08X status=0x%08X "
              "guard=%d release=0x%08X"
              % (res.npu_cmd_before_power_request,
                 res.npu_cmd_after_power_request,
                 res.npu_status_after_power_request,
                 res.power_guard_cycles, res.npu_cmd_after_power_release))
        print("  PMU boundary: seq=%d guard_cycles=%d "
              "pmcr_after_guard=0x%08X pmcr_after_program=0x%08X "
              "arm_after_program=%d stability=%d/%d"
              % (res.start_sequence_id, res.reset_guard_cycles,
                 res.pmcr_after_reset_guard, res.pmcr_after_program,
                 res.armed_after_program, res.program_stable,
                 res.program_stability_reads))
        print("  golden window [0x%08X +0x%X] crc=0x%08X -> %s | "
              "region_crc=0x%08X (corroboration only, never a gate)"
              % (res.golden_window_base, res.golden_window_len,
                 res.golden_window_crc,
                 "GOLDEN" if cls["golden_window_ok"] else "MISMATCH",
                 res.result_region_crc))
        for name, snap in (("pre", res.pre), ("post", res.post),
                           ("post_disable", res.post_disable)):
            print("  %-12s %s" % (name, snapshot_row(snap)))
        print("  raw_delta=%d progress=%s usable_diagnostic_delta=%s"
              % (cls["raw_delta_diagnostic"], cls["progress_observed"],
                 cls["usable_diagnostic_delta"]))

    verdict, _detail = pmu_diag_verdict(loaded["A"], loaded["B"], loaded["C"])
    print()
    print("=== verdict ===")
    print(verdict)

    if verdict.startswith("cfg-missing-root-cause"):
        ok, checks = pmu_diag_b_proof(loaded["B"])
        print()
        print("=== full B proof (required for the root-cause claim) ===")
        for k, v in checks.items():
            print("  %-28s %s" % (k, "ok" if v else "FAIL"))
        assert ok, "verdict claimed root cause but the B proof does not hold"


if __name__ == "__main__":
    main()
