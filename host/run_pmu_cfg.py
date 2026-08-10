"""Collect ONE 10-repeat PMU_CFG characterization block from ONE fresh boot.

CHARACTERIZATION ONLY. Nothing this script writes is latency, T_npu, a
performance baseline, a Production GO, Gate 7, or MLEK data, and the +514
identity observed in the Gate 1 fixed-image Q1 campaign is NOT generalized to
these images. The only performance-shaped number archived is
npu_pmu_window_cycles, which is a counter window for ONE case of ONE build.

One invocation == one (case, round, position) cell of the balanced campaign,
== one fresh MCU boot, == ten consecutive runs on that boot. Like
run_pmu_qual.py this script never touches MCC power or reboot paths: deploy the
CFG image for this case, REBOOT, then run this ONCE.

  python3 run_pmu_cfg.py --case B --round 1 --position 2 --host-boot-index 5 \
      --bins-dir /path/to/build_pmu_cfg_b \
      --manifest /path/to/build_pmu_cfg_b/pmu_cfg_manifest.json \
      --out-dir results/cfg_r1_p2_B

Four rules shape this file:

  - Everything provable before the port opens IS proved before the port opens:
    the schedule cell, the manifest identity (schema v8, Q1 structure, this
    case's PCA1/PCB1/PCC1 build id, case id, write contract, callsite and hook
    attestation) and the SHA-256 of all three deployed BIN files. A JSON on
    disk asserting a build nobody verified is worse than no JSON at all.

  - The transport is not reimplemented. run_pmu_qual.collect_pmu_qual() is the
    proven schema-v8 exchange -- ACK, unsolicited COMPLETE, no duplicates, and
    an independent GET re-read that must be byte-equal -- and it is reused
    here unchanged rather than restated.

  - The ten repeats come from ONE boot. Between repeats only the RUNNER
    PROTOCOL state is reset and re-primed (CMD_RESET_RUNNER plus the dummy
    load); the MCU is never rebooted and no power path is touched. The target's
    own run_sequence must therefore read exactly 1, 2, ... 10: a first record
    that is not 1 means the boot was not fresh, and a gap means a run was lost
    or a latch was re-served.

  - A sample is archived the moment it exists, before the next repeat starts.
    A crash at repeat 7 must leave repeats 1-6 on disk, not nothing.

The two failure kinds are deliberately NOT the same:

  - identity, CRC, re-read or sequence failure -> nothing is written for that
    repeat. Those records cannot be attributed to this cell at all, and a file
    on disk claiming otherwise would be the misleading artifact.
  - case-aware VALIDITY failure -> that sample IS archived, with
    npu_pmu_window_cycles null and its failing terms named, and the block stops
    before the next repeat with a non-zero exit. The evidence of the failure is
    the point; what must not happen is the block continuing as if it had ten
    good samples.

Aggregating the 90 samples of a full campaign is a separate analyzer's job and
is deliberately absent here.
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass

import run_pmu_qual as rq
from runner_proto import (PMU_CFG_BUILD_IDS, PMU_CFG_CASE_IDS, PMU_CFG_CASES,
                          PMU_QUAL_MODES, PMU_QUAL_SCHEMA_VERSION,
                          classify_pmu_cfg, pmu_cfg_case_contract)

# Ten consecutive runs per boot. Not a sample-size claim: it is what one boot
# is allowed to contribute before the next cell needs its own boot.
REPEATS = 10

# The CFG images are Q1 H-PRINTF images in every structural respect -- same
# callsite, same hook, same seam -- so their manifests carry the Q1 mode and
# are held to the Q1 hook rules. Only the build identity and the one
# PMCCNTR_CFG action differ.
CFG_STRUCTURAL_MODE = "Q1"

# The balanced design: every case appears once per round and once in every
# position across the three rounds, so a position effect (warm-up, drift,
# whatever it turns out to be) cannot be confounded with a case effect.
POSITION_SCHEDULE = {
    1: ("A", "B", "C"),
    2: ("B", "C", "A"),
    3: ("C", "A", "B"),
}
ROUNDS = tuple(sorted(POSITION_SCHEDULE))
POSITIONS = (1, 2, 3)

# Manifest keys the CFG gate adds on top of the qualification manifest. Absence
# is refused rather than defaulted: a manifest without them was not emitted by
# check_pmu_cfg.py and does not describe a case.
CFG_MANIFEST_REQUIRED = (
    "cfg_case",
    "cfg_case_id",
    "cfg_expected_write_count",
    "characterization_only",
    "not_a_performance_baseline",
)


@dataclass(frozen=True)
class CampaignPlan:
    """Everything proved before the port opens, carried to the archive."""
    case: str
    round_index: int
    position: int
    host_boot_index: int
    bins_dir: str
    manifest_path: str
    manifest_doc: dict
    manifest_blob: bytes
    artifact_sha256: dict


def verify_schedule(case: str, round_index: int, position: int) -> None:
    """The cell must be one the balanced design actually contains."""
    if case not in PMU_CFG_CASES:
        raise SystemExit("FAIL unknown case %r, expected one of %s"
                         % (case, ", ".join(PMU_CFG_CASES)))
    if round_index not in POSITION_SCHEDULE:
        raise SystemExit("FAIL round %r is not one of %s"
                         % (round_index, ", ".join(str(r) for r in ROUNDS)))
    if position not in POSITIONS:
        raise SystemExit("FAIL position %r is not one of %s"
                         % (position, ", ".join(str(p) for p in POSITIONS)))
    want = POSITION_SCHEDULE[round_index][position - 1]
    if want != case:
        raise SystemExit(
            "FAIL round %d position %d is case %s, not %s -- the balanced "
            "design is R1 %s / R2 %s / R3 %s, and running a cell out of order "
            "destroys the property that makes position and case separable"
            % (round_index, position, want, case,
               "/".join(POSITION_SCHEDULE[1]), "/".join(POSITION_SCHEDULE[2]),
               "/".join(POSITION_SCHEDULE[3])))


def verify_cfg_manifest_identity(doc: dict, case: str, where: str) -> None:
    """The manifest must be the one check_pmu_cfg.py emitted for THIS case.

    The callsite and hook half is delegated to run_pmu_qual, by the same code
    the qualification collector uses, so the CFG images are held to the Q1
    structural attestation rather than to a weaker copy of it.
    """
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    if doc.get("schema_version") != PMU_QUAL_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d -- this is not a "
            "schema-v8 manifest"
            % (where, doc.get("schema_version"), PMU_QUAL_SCHEMA_VERSION))
    if doc.get("qualification_mode") != CFG_STRUCTURAL_MODE:
        raise SystemExit(
            "FAIL %s: manifest describes mode %r, but the CFG images are %s "
            "H-PRINTF images structurally"
            % (where, doc.get("qualification_mode"), CFG_STRUCTURAL_MODE))
    for key in CFG_MANIFEST_REQUIRED:
        if doc.get(key) is None:
            raise SystemExit(
                "FAIL %s: manifest has no %s -- this is a qualification "
                "manifest, not a CFG characterization manifest" % (where, key))
    for key in ("characterization_only", "not_a_performance_baseline"):
        if doc[key] is not True:
            raise SystemExit(
                "FAIL %s: manifest %s=%r; a CFG manifest must declare the "
                "scope limit it was built under" % (where, key, doc[key]))
    if doc.get("cfg_case") != case:
        raise SystemExit(
            "FAIL %s: manifest describes case %r but case %s was requested -- "
            "each case is a separate build with its own manifest"
            % (where, doc.get("cfg_case"), case))

    want_build = PMU_CFG_BUILD_IDS[case]
    if rq.manifest_build_id(doc) != want_build:
        raise SystemExit(
            "FAIL %s: manifest build_id %r does not decode to the case %s "
            "identity 0x%08X" % (where, doc.get("build_id"), case, want_build))

    # The case contract itself: an "A" that declares a write, a "B" that
    # declares a zero value or a "C" that declares a non-zero one is not a
    # description of any case that exists.
    contract = pmu_cfg_case_contract(doc)
    if not contract["manifest_coherent"]:
        raise SystemExit(
            "FAIL %s: manifest is not a possible description of case %s -- "
            "cfg_case_id=%r cfg_expected_write_count=%r cfg_expected_value=%r "
            "(case %s requires case_id %d, exactly %d write(s), and %s)"
            % (where, case, doc.get("cfg_case_id"),
               doc.get("cfg_expected_write_count"),
               doc.get("cfg_expected_value"), case, PMU_CFG_CASE_IDS[case],
               contract["write_count"],
               {"A": "no declared value at all",
                "B": "a non-zero generated value",
                "C": "an explicit zero"}[case]))

    rq.verify_manifest_callsite(doc, CFG_STRUCTURAL_MODE, where)


def read_cfg_manifest(path: str, case: str) -> tuple[dict, bytes]:
    """Read the manifest ONCE: the parsed document and the exact bytes.

    One read, not two -- re-opening at archive time would leave a window in
    which the reference the block was collected against is not the reference
    the block gets archived with.
    """
    doc, blob = rq.read_manifest_document(path)
    verify_cfg_manifest_identity(doc, case, path)
    return doc, blob


def preflight(case: str, round_index: int, position: int, host_boot_index: int,
              bins_dir: str, manifest_path: str) -> CampaignPlan:
    """Everything that can be proved without a serial port, proved."""
    verify_schedule(case, round_index, position)
    if isinstance(host_boot_index, bool) or host_boot_index <= 0:
        raise SystemExit("FAIL host_boot_index must be a positive integer, got %r"
                         % host_boot_index)
    doc, blob = read_cfg_manifest(manifest_path, case)
    artifacts = rq.verify_local_bins(doc, bins_dir)
    return CampaignPlan(
        case=case, round_index=round_index, position=position,
        host_boot_index=host_boot_index, bins_dir=bins_dir,
        manifest_path=manifest_path, manifest_doc=doc, manifest_blob=blob,
        artifact_sha256=artifacts)


def verify_cfg_record_identity(res, plan: CampaignPlan, repeat: int) -> None:
    """The record must be this case's image, at this cell, at this repeat.

    Checked BEFORE anything is written: a record that fails here cannot be
    attributed to this cell at all, so no file is produced for it.
    """
    if res.qualification_mode != PMU_QUAL_MODES[CFG_STRUCTURAL_MODE]:
        raise SystemExit(
            "FAIL repeat %d: target reports qualification_mode=%d, expected %d "
            "(%s) -- wrong image on the SD, result NOT written"
            % (repeat, res.qualification_mode,
               PMU_QUAL_MODES[CFG_STRUCTURAL_MODE], CFG_STRUCTURAL_MODE))
    want_build = PMU_CFG_BUILD_IDS[plan.case]
    if res.build_id != want_build:
        raise SystemExit(
            "FAIL repeat %d: case %s expects build_id 0x%08X but the target "
            "reports 0x%08X -- wrong artifact, result NOT written"
            % (repeat, plan.case, want_build, res.build_id))
    want_case_id = PMU_CFG_CASE_IDS[plan.case]
    if res.diag_case != want_case_id:
        raise SystemExit(
            "FAIL repeat %d: case %s expects diag_case %d but the target "
            "reports %d -- wrong case image, result NOT written"
            % (repeat, plan.case, want_case_id, res.diag_case))
    if res.nc_control_id != 0:
        raise SystemExit(
            "FAIL repeat %d: target reports nc_control_id=%d; negative-control "
            "images must never feed the characterization dataset"
            % (repeat, res.nc_control_id))
    expected_lr = plan.manifest_doc["expected_return_address"]
    if res.hook_callsite_lr_observed != expected_lr:
        raise SystemExit(
            "FAIL repeat %d: observed callsite LR 0x%08X but case %s's own "
            "manifest expects 0x%08X -- the hook did not fire at the attested "
            "callsite, result NOT written (another case's address is never the "
            "reference)"
            % (repeat, res.hook_callsite_lr_observed, plan.case, expected_lr))
    if res.run_sequence != repeat:
        raise SystemExit(
            "FAIL repeat %d: target reports run_sequence=%d, expected %d -- the "
            "block is %d consecutive runs numbered 1..%d on ONE fresh boot, so "
            "a first record that is not 1 means the boot was not fresh and a "
            "gap means a run was lost or a latch re-served; result NOT written"
            % (repeat, res.run_sequence, repeat, REPEATS, REPEATS))


def repeat_filename(plan: CampaignPlan, repeat: int) -> str:
    return ("cfg_%s_round%d_pos%d_boot%d_repeat%02d.json"
            % (plan.case, plan.round_index, plan.position, plan.host_boot_index,
               repeat))


def build_cfg_record(plan: CampaignPlan, repeat: int, res, raw: bytes,
                     reread_raw: bytes) -> dict:
    """One archived repeat.

    Keys are split the way the contract splits them: the campaign says which
    cell this is, the host says what it deployed, the target says what it
    observed, and `derived` is the case-aware verdict. The manifest is carried
    BOTH as the exact bytes preflight read and as the parsed document, so the
    analyzer re-derives the parse instead of inheriting this run's copy of it.
    """
    return {
        "campaign": {
            "experiment": "pmu_cfg_characterization",
            "characterization_only": True,
            "not_a_performance_baseline": True,
            "cfg_case": plan.case,
            "cfg_case_id": PMU_CFG_CASE_IDS[plan.case],
            "round": plan.round_index,
            "position": plan.position,
            "position_schedule": {str(r): list(POSITION_SCHEDULE[r])
                                  for r in ROUNDS},
            "repeat_index": repeat,
            "repeat_total": REPEATS,
            "host_boot_index": plan.host_boot_index,
            "boot_policy": (
                "all %d repeats come from ONE fresh MCU boot; between repeats "
                "only the runner protocol state is reset and re-primed, the "
                "MCU is never rebooted and no power path is touched"
                % REPEATS),
        },
        "host": {
            "structural_mode": CFG_STRUCTURAL_MODE,
            "bins_dir": plan.bins_dir,
            "artifact_sha256": dict(plan.artifact_sha256),
            "manifest_path": plan.manifest_path,
            "manifest_sha256": hashlib.sha256(plan.manifest_blob).hexdigest(),
            # The exact bytes the gate wrote. The parsed copy below is a
            # convenience; THIS is the evidence, and the analyzer re-parses it.
            "manifest_text": plan.manifest_blob.decode("utf-8"),
        },
        "manifest": plan.manifest_doc,
        "target": rq.target_fields(res),
        "derived": classify_pmu_cfg(res, plan.manifest_doc),
        # The canonical evidence: BOTH exact wire payloads, each with its own
        # digest. Everything above is derivable from them, and the analyzer
        # re-parses rather than trusting any parsed copy in this file.
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_payload_hex": reread_raw.hex(),
            "reread_payload_sha256": hashlib.sha256(reread_raw).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }


def archive_repeat(plan: CampaignPlan, out_dir: str, repeat: int, res,
                   raw: bytes, reread_raw: bytes) -> tuple[str, dict]:
    """Write one repeat to disk immediately, before the next one starts."""
    record = build_cfg_record(plan, repeat, res, raw, reread_raw)
    path = os.path.join(out_dir, repeat_filename(plan, repeat))
    # Evidence is append-only. A repeated invocation for the same cell must
    # fail instead of silently replacing a sample that was already observed.
    with open(path, "x") as handle:
        json.dump(record, handle, indent=2)
    return path, record


def prepare_output_directory(out_dir: str) -> None:
    """Create one empty cell directory, refusing any pre-existing evidence."""
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise SystemExit("FAIL cannot create output directory %s: %s"
                         % (out_dir, exc))
    if not os.path.isdir(out_dir):
        raise SystemExit("FAIL output path is not a directory: %s" % out_dir)
    try:
        entries = os.listdir(out_dir)
    except OSError as exc:
        raise SystemExit("FAIL cannot inspect output directory %s: %s"
                         % (out_dir, exc))
    if entries:
        raise SystemExit(
            "FAIL output directory %s is not empty; characterization evidence "
            "is never overwritten (%s)" % (out_dir, ", ".join(sorted(entries))))


def collect_campaign(link, plan: CampaignPlan, out_dir: str) -> int:
    """The ten repeats. Returns the process exit code."""
    for repeat in range(1, REPEATS + 1):
        # Runner protocol state ONLY: the state machine is walked back to
        # INPUT_READY exactly as run_pmu_qual does. The boot is not touched,
        # which is what keeps run_sequence counting 1..10 across the block.
        rq.prime(link)
        res, raw, reread_raw = rq.collect_pmu_qual(link)
        verify_cfg_record_identity(res, plan, repeat)
        path, record = archive_repeat(plan, out_dir, repeat, res, raw,
                                      reread_raw)
        derived = record["derived"]
        print("wrote %s" % path)
        print("  case %s round %d position %d boot %d repeat %d/%d seq=%d"
              % (plan.case, plan.round_index, plan.position,
                 plan.host_boot_index, repeat, REPEATS, res.run_sequence))
        print("  cfg: write_performed=%d value=0x%08X readback=0x%08X"
              % (res.cfg_write_performed, res.cfg_write_value,
                 res.cfg_readback_after_write))
        print("  raw delta (diagnostic): %d" % derived["raw_delta_diagnostic"])
        if not derived["valid"]:
            print("  npu_pmu_window_cycles: INVALID (archived as null)")
            for reason in derived["invalid_reasons"]:
                print("    FAIL %s" % reason)
            print("  STOPPING after repeat %d of %d: an invalid sample is "
                  "archived as evidence, never continued past"
                  % (repeat, REPEATS))
            return 1
        print("  npu_pmu_window_cycles: %d (characterization only)"
              % derived["npu_pmu_window_cycles"])
    print("collected %d/%d valid repeats for case %s (round %d, position %d, "
          "boot %d)" % (REPEATS, REPEATS, plan.case, plan.round_index,
                        plan.position, plan.host_boot_index))
    return 0


def main(argv=None, open_link=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=PMU_CFG_CASES,
                    help="CFG characterization case deployed on the SD")
    ap.add_argument("--round", required=True, type=int, dest="round_index",
                    help="campaign round 1..3")
    ap.add_argument("--position", required=True, type=int,
                    help="position within the round, 1..3")
    ap.add_argument("--host-boot-index", required=True, type=int,
                    help="host-side boot counter; bump on EVERY reboot")
    ap.add_argument("--bins-dir", required=True,
                    help="build dir holding the APP/VECTORS/DDR.BIN actually deployed")
    ap.add_argument("--manifest", required=True,
                    help="check_pmu_cfg.py manifest for THIS case")
    ap.add_argument("--out-dir", required=True,
                    help="directory the repeat01..repeat%02d JSON files go in"
                         % REPEATS)
    ap.add_argument("--port", default=rq.PORT_DEFAULT)
    a = ap.parse_args(argv)

    # Nothing after this point can rescue a wrong cell, a wrong manifest or a
    # wrong image, so all of it happens before the port is opened.
    plan = preflight(a.case, a.round_index, a.position, a.host_boot_index,
                     a.bins_dir, a.manifest)
    prepare_output_directory(a.out_dir)

    opener = open_link or rq.PmuQualLink
    link = opener(a.port)
    try:
        link.ping()
        return collect_campaign(link, plan, a.out_dir)
    finally:
        link.close()


if __name__ == "__main__":
    raise SystemExit(main())
