"""Run ONE PMU_DIAG case on an already-booted board and archive the raw result.

One invocation == one case on one fresh boot. The A/B/C protocol demands an
independent full REBOOT per case, so this script deliberately does NOT touch
MCC power or reboot paths -- deploy the case image, REBOOT, then run this.

  python3 run_pmu_diag.py --case B --host-boot-index 2 \
      --bins-dir /path/to/build_pmu_diag_b --out results/diag_b.json

Keys are split exactly as the contract splits them:
  host-attached : host_boot_index, app/vectors/ddr BIN SHA-256 (the host
                  knows what it deployed; the target reporting a firmware
                  hash would be self-referential)
  target-returned: build_id, diag_case, nc_control_id, run_sequence and the
                  raw snapshots

The analysis rule is enforced AT COLLECTION: derived.usable_diagnostic_delta
is null unless progress was observed, and no key of this file is ever named
as a performance metric -- a DIAG delta contains extra MMIO reads by design.
"""

import argparse
import hashlib
import json
import zlib

from runner_proto import (PMU_DIAG_BUILD_IDS, PMU_DIAG_SEAM_BUILD_IDS,
                          PMU_DIAG_SEAM_IDS, RunnerLink, classify_pmu_diag,
                          pmu_diag_b_proof, pmu_diag_seam_post_held,
                          pmu_diag_seam_row_ok)

PORT_DEFAULT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
CASE_IDS = {"A": 1, "B": 2, "C": 3}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def prime(link):
    """Walk the state machine to INPUT_READY, the same way the board gates
    do: a dummy model blob and an empty input. The diag run executes the
    fixed compiled-in inference regardless of the staged bytes."""
    link.reset_runner()
    blob = b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=("A", "B", "C"),
                    help="legacy CFG experiment selector")
    ap.add_argument("--seam", choices=("S1", "S2", "S3"),
                    help="v7 power-seam selector; implies case B")
    ap.add_argument("--host-boot-index", required=True, type=int,
                    help="host-side boot counter; bump on EVERY reboot")
    ap.add_argument("--bins-dir", required=True,
                    help="build dir holding the APP/VECTORS/DDR.BIN actually deployed")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", default=PORT_DEFAULT)
    a = ap.parse_args()
    if bool(a.case) == bool(a.seam):
        raise SystemExit("give exactly one of --case (legacy CFG experiment) "
                         "or --seam (v7 power-seam experiment)")

    host_meta = {
        "host_boot_index": a.host_boot_index,
        "deployed_case": "B" if a.seam else a.case,
        "deployed_seam": a.seam,
        "app_bin_sha256": sha256_file("%s/APP.BIN" % a.bins_dir),
        "vectors_bin_sha256": sha256_file("%s/VECTORS.BIN" % a.bins_dir),
        "ddr_bin_sha256": sha256_file("%s/DDR.BIN" % a.bins_dir),
    }

    link = RunnerLink(a.port)
    try:
        link.ping()
        prime(link)
        res = link.run_pmu_diag()
        link.get_pmu_diag_result()
        # EXACT byte equality between the unsolicited completion payload and
        # the re-read latch -- stronger than field equality, and it makes the
        # archived canonical payload cover both.
        if link.last_pmu_diag_reread_raw != link.last_pmu_diag_raw:
            raise SystemExit("FAIL GET_PMU_DIAG_RESULT bytes differ from the "
                             "PMU_DIAG_COMPLETE payload -- latch bug, do not analyse")
        raw = link.last_pmu_diag_raw
    finally:
        link.close()

    # Identity is checked BEFORE anything is written: a mismatch means the SD
    # carries a different image than the one this invocation claims, and a
    # JSON on disk asserting the wrong seam is worse than no JSON at all.
    want_case = "B" if a.seam else a.case
    if res.diag_case != CASE_IDS[want_case]:
        raise SystemExit(
            "FAIL deployed %s but the target reports diag_case=%d -- "
            "wrong image on the SD, result NOT written"
            % (a.seam or a.case, res.diag_case))
    if res.nc_control_id != 0:
        raise SystemExit(
            "FAIL target reports nc_control_id=%d: negative-control images "
            "must never feed the experiment dataset" % res.nc_control_id)
    want_build = (PMU_DIAG_SEAM_BUILD_IDS[a.seam] if a.seam
                  else PMU_DIAG_BUILD_IDS[a.case])
    if res.build_id != want_build:
        raise SystemExit(
            "FAIL deployed %s expects build_id 0x%08X but the target reports "
            "0x%08X -- wrong artifact, result NOT written"
            % (a.seam or a.case, want_build, res.build_id))
    if a.seam and res.power_seam_id != PMU_DIAG_SEAM_IDS[a.seam]:
        raise SystemExit(
            "FAIL requested seam %s (id %d) but the target reports "
            "power_seam_id=%d -- wrong artifact, result NOT written"
            % (a.seam, PMU_DIAG_SEAM_IDS[a.seam], res.power_seam_id))

    derived = classify_pmu_diag(res)
    b_ok, b_checks = pmu_diag_b_proof(res)
    if a.seam:
        seam_ok, seam_checks = pmu_diag_seam_row_ok(res, a.seam)
    record = {
        "host": host_meta,
        "target": {
            "schema_version": res.schema_version,
            "build_id": "0x%08X" % res.build_id,
            "diag_case": res.diag_case,
            "nc_control_id": res.nc_control_id,
            "run_sequence": res.run_sequence,
            "cfg_write_performed": res.cfg_write_performed,
            "cfg_write_value": "0x%08X" % res.cfg_write_value,
            "cfg_readback_after_write": "0x%08X" % res.cfg_readback_after_write,
            "run_rc": res.run_rc,
            "valid_flags": "0x%02X" % res.valid_flags,
            "poison_crc": "0x%08X" % res.poison_crc,
            "output_crc": "0x%08X" % res.output_crc,
            "result_region_crc": "0x%08X" % res.result_region_crc,
            "ts_source_valid": res.ts_source_valid,
            "t_call_enter": res.t_call_enter,
            "t_call_return": res.t_call_return,
            "t_pmu_disable": res.t_pmu_disable,
            "start_sequence_id": res.start_sequence_id,
            "power_guard_cycles": res.power_guard_cycles,
            "npu_cmd_before_power_request": "0x%08X" % res.npu_cmd_before_power_request,
            "npu_cmd_after_power_request": "0x%08X" % res.npu_cmd_after_power_request,
            "npu_status_after_power_request": "0x%08X" % res.npu_status_after_power_request,
            "reset_guard_cycles": res.reset_guard_cycles,
            "pmcr_after_reset_guard": "0x%08X" % res.pmcr_after_reset_guard,
            "pmcr_after_program": "0x%08X" % res.pmcr_after_program,
            "armed_after_program": res.armed_after_program,
            "program_stability_reads": res.program_stability_reads,
            "program_stable": res.program_stable,
            "npu_cmd_after_power_release": "0x%08X" % res.npu_cmd_after_power_release,
            "golden_window_base": "0x%08X" % res.golden_window_base,
            "golden_window_len": "0x%X" % res.golden_window_len,
            "golden_window_crc": "0x%08X" % res.golden_window_crc,
            "pmcr_readback_after_disable": "0x%08X" % res.pmcr_readback_after_disable,
            "pmu_mmio_read_count_delta": res.pmu_mmio_read_count_delta,
            "pmu_mmio_write_count_delta": res.pmu_mmio_write_count_delta,
            "power_seam_id": res.power_seam_id,
            "power_rehold_performed": res.power_rehold_performed,
            "rehold_guard_cycles": res.rehold_guard_cycles,
            "npu_cmd_after_seam": "0x%08X" % res.npu_cmd_after_seam,
            "npu_status_after_seam": "0x%08X" % res.npu_status_after_seam,
            "snapshots": {
                name: vars(snap) for name, snap in
                (("pre", res.pre), ("post", res.post),
                 ("post_disable", res.post_disable))
            },
        },
        "derived": derived,
        "b_proof": {"pass": b_ok, "checks": b_checks} if a.case == "B" else None,
        "seam_row": ({"row_ok": seam_ok, "checks": seam_checks,
                      "post_held": pmu_diag_seam_post_held(res)}
                     if a.seam else None),
        # The canonical evidence: the exact wire payload. Everything above is
        # derivable from it; the analyzer re-parses and re-verifies its CRC
        # rather than trusting this file's parsed copies.
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }

    with open(a.out, "w") as f:
        json.dump(record, f, indent=2)
    print("wrote %s" % a.out)
    print("  %s boot=%d seq=%d" % (a.seam or ("case=%s" % a.case),
                                   a.host_boot_index, res.run_sequence))
    print("  raw delta (diagnostic): %d" % derived["raw_delta_diagnostic"])
    print("  progress_observed:      %s" % derived["progress_observed"])
    print("  usable_diagnostic_delta: %s" % derived["usable_diagnostic_delta"])
    if a.seam:
        print("  seam row: %s | post_held=%s"
              % ("ok" if seam_ok else "FAIL", pmu_diag_seam_post_held(res)))
        for k, v in seam_checks.items():
            if not v:
                print("    FAIL %s" % k)
    if a.case == "B":
        print("  B proof: %s" % ("PASS" if b_ok else "FAIL"))
        for k, v in b_checks.items():
            print("    %-28s %s" % (k, "ok" if v else "FAIL"))


if __name__ == "__main__":
    main()
