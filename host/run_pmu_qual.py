"""Collect ONE schema-v8 PMU_QUAL sample and bind it to the build that made it.

One invocation == one mode on one fresh boot. Like run_pmu_diag.py this script
never touches MCC power or reboot paths -- deploy the Q0 or Q1 image, REBOOT,
then run this.

  python3 run_pmu_qual.py --mode Q1 --host-boot-index 2 \
      --bins-dir /path/to/build_pmu_qual_q1 \
      --manifest /path/to/build_pmu_qual_q1/pmu_qual_manifest.json \
      --out results/qual_q1_boot2.json

Three rules shape this file:

  - Everything provable before the port opens IS proved before the port opens.
    The manifest must be the one check_pmu_qual.py emitted for THIS mode, with
    its callsite attestation intact, and the three BIN files in --bins-dir must
    hash exactly to the artifacts that manifest describes. A JSON on disk
    asserting a build nobody verified is worse than no JSON at all.

  - The v8 transport is LOCAL. RunnerLink.run_pmu_diag()/get_pmu_diag_result()
    parse with parse_pmu_diag_payload(), which correctly refuses a schema-v8
    record, so they are never called here. The exchange below reuses the same
    0x60/0x61/0x62 framing with the v8 parser and keeps the v7 methods
    untouched and still refusing v8.

  - One sample is TWO independent reads: the unsolicited PMU_DIAG_COMPLETE and
    a separate GET re-read of the latch. Both raw hex strings and both digests
    are archived, and the two must be byte-equal -- a latch still serving an
    older run cannot then be mistaken for this one.

Q0 and Q1 are separate links, so their callsites MAY land at different numeric
addresses. Whether they do is a property of a particular pair of builds, not a
guarantee either way -- today's images happen to link the target callsite at
the same address. Either outcome is fine here because an observed LR is only
ever compared with the manifest of its OWN mode: equality across modes is
never required, and inequality is never a failure.
"""

import argparse
import hashlib
import json
import os
import re
import time
import zlib

from runner_proto import (CMD_GET_PMU_DIAG_RESULT, CMD_PMU_DIAG_COMPLETE,
                          CMD_RUN_PMU_DIAG, NACK, Nack, PMU_QUAL_BUILD_IDS,
                          PMU_QUAL_MODES, PMU_QUAL_SCHEMA_VERSION,
                          ProtocolError, RunSequenceError, RunnerLink,
                          build_frame, classify_pmu_qual,
                          parse_pmu_qual_payload)

PORT_DEFAULT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"

# The deployed artifacts, named as check_pmu_qual.py keys them inside
# manifest["artifact_sha256"].
BIN_FILES = ("APP.BIN", "VECTORS.BIN", "DDR.BIN")

# The gate's identity terms, restated here so a manifest that lost one is
# rejected by the host as well. These are not re-derivations of the gate's
# work -- they are the values a reviewer reads off the procedure.
CALLER_SYMBOL = "test_u85"
TARGET_RELOC_SYMBOL = "printf"
CALL_RELOC = re.compile(r"^R_ARM_\w*CALL$")
RELEASE_IMMEDIATE_VALUE = 0xC   # the vendor's terminal CMD write
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Manifest keys the host uses, compares or archives as callsite provenance. A
# manifest missing any of them was not produced by the ELF gate, and a sample
# collected against it could not be re-derived by a reviewer.
MANIFEST_REQUIRED = (
    "caller_symbol",
    "callsite_disassembly_sha256",
    "expected_return_address",
    "release_store_address",
    "release_immediate_value",
    "target_call_address",
    "stop_store_address",
    "object_target_relocation_symbol",
    "object_target_relocation_type",
    "vendor_source_sha256",
    "vendor_object_sha256",
    "test_cpm",
)

# Q1 carries the hook's attested operation order: EVERY address the gate
# emits, in the order it emits them, plus the digest over that order. A subset
# would let a manifest lose a term the gate proved and still be accepted here.
# Q0 has no hook AT ALL by contract, so all of these must be absent rather
# than present-and-zero.
Q1_HOOK_REQUIRED = (
    "hook_order_sha256",
    "hook_address",
    "hook_wrapper_call_address",
    "hook_internal_pre_release_cycle_read_address",
    "hook_pre_release_pmcr_address",
    "hook_pre_release_pmcntenset_address",
    "hook_pre_release_pmccntr_cfg_address",
    "hook_pre_release_pmovsset_address",
    "hook_pmu_disable_address",
    "hook_dsb_address",
    "hook_pmcr_readback_address",
    "hook_internal_post_disable_capture_address",
    "hook_snapshot_valid_latch_address",
    "hook_return_address",
)

# How long to keep listening after a COMPLETE for a second one carrying the
# same sequence. A duplicate latch is cheap to look for now and impossible to
# notice later.
DRAIN_SECONDS = 0.5


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_build_id(doc: dict) -> int | None:
    """JSON has no unsigned 32-bit type, so the gate writes build_id as a hex
    string. Anything unparseable yields None, which equals no build id."""
    value = doc.get("build_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def _is_address(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def verify_manifest_identity(doc: dict, mode: str, where: str) -> None:
    """The manifest must be the one this mode's ELF gate emitted, with its
    callsite attestation whole.

    Used by the collector on the file and by the analyzer on the archived
    copy, so the two can never drift apart.
    """
    if not isinstance(doc, dict):
        raise SystemExit("FAIL %s: manifest is not a JSON object" % where)
    if doc.get("schema_version") != PMU_QUAL_SCHEMA_VERSION:
        raise SystemExit(
            "FAIL %s: manifest schema_version=%r, expected %d -- this is not a "
            "schema-v8 qualification manifest"
            % (where, doc.get("schema_version"), PMU_QUAL_SCHEMA_VERSION))
    if doc.get("qualification_mode") != mode:
        raise SystemExit(
            "FAIL %s: manifest describes mode %r but %s was requested -- each "
            "mode is a separate link with its own manifest"
            % (where, doc.get("qualification_mode"), mode))
    want_build = PMU_QUAL_BUILD_IDS[mode]
    if manifest_build_id(doc) != want_build:
        raise SystemExit(
            "FAIL %s: manifest build_id %r does not decode to the %s identity "
            "0x%08X" % (where, doc.get("build_id"), mode, want_build))

    for key in MANIFEST_REQUIRED:
        if doc.get(key) is None:
            raise SystemExit(
                "FAIL %s: manifest has no %s -- the callsite attestation is "
                "incomplete" % (where, key))
    for key in ("expected_return_address", "release_store_address",
                "target_call_address", "stop_store_address"):
        if not _is_address(doc[key]):
            raise SystemExit(
                "FAIL %s: manifest %s=%r is not numeric; the host compares "
                "these to raw record fields" % (where, key, doc[key]))
    for key in ("callsite_disassembly_sha256", "vendor_source_sha256",
                "vendor_object_sha256"):
        if not HEX64.match(str(doc[key])):
            raise SystemExit("FAIL %s: manifest %s=%r is not a SHA-256"
                             % (where, key, doc[key]))

    if doc["caller_symbol"] != CALLER_SYMBOL:
        raise SystemExit(
            "FAIL %s: manifest attests caller %r, but the qualification "
            "callsite lives in <%s>"
            % (where, doc["caller_symbol"], CALLER_SYMBOL))
    if doc["object_target_relocation_symbol"] != TARGET_RELOC_SYMBOL:
        raise SystemExit(
            "FAIL %s: the target call relocates against %r, expected %r -- a "
            "call lowered to something else is not the attested callsite"
            % (where, doc["object_target_relocation_symbol"],
               TARGET_RELOC_SYMBOL))
    if not CALL_RELOC.match(str(doc["object_target_relocation_type"])):
        raise SystemExit(
            "FAIL %s: the target relocation is %r, expected an R_ARM_*_CALL"
            % (where, doc["object_target_relocation_type"]))
    if doc["release_immediate_value"] != RELEASE_IMMEDIATE_VALUE:
        raise SystemExit(
            "FAIL %s: manifest release immediate is %r, expected %d (the "
            "vendor's terminal CMD write)"
            % (where, doc["release_immediate_value"], RELEASE_IMMEDIATE_VALUE))
    if doc["test_cpm"] != 1:
        raise SystemExit(
            "FAIL %s: manifest reports test_cpm=%r; the qualification images "
            "require TEST_CPM=1" % (where, doc["test_cpm"]))

    hook_keys = sorted(k for k in doc if k.startswith("hook_"))
    if mode == "Q1":
        for key in Q1_HOOK_REQUIRED:
            if doc.get(key) is None:
                raise SystemExit(
                    "FAIL %s: Q1 manifest has no %s -- the hook's operation "
                    "order was not attested" % (where, key))
            if key.endswith("_address") and not _is_address(doc[key]):
                raise SystemExit(
                    "FAIL %s: Q1 manifest %s=%r is not numeric"
                    % (where, key, doc[key]))
        if not HEX64.match(str(doc["hook_order_sha256"])):
            raise SystemExit(
                "FAIL %s: Q1 manifest hook_order_sha256=%r is not a SHA-256"
                % (where, doc["hook_order_sha256"]))
    elif hook_keys:
        raise SystemExit(
            "FAIL %s: the Q0 baseline carries hook evidence (%s) -- Q0 must "
            "have no hook at all" % (where, ", ".join(hook_keys)))


def read_manifest(path: str, mode: str) -> tuple[dict, bytes]:
    """Read the manifest ONCE and return both the parsed document and the
    exact bytes it was parsed from.

    One read, not two: re-opening the file at archive time would leave a
    window in which the reference the sample was collected against is not the
    reference the sample gets archived with.
    """
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError as exc:
        raise SystemExit("FAIL cannot read manifest %s: %s" % (path, exc))
    try:
        doc = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit("FAIL manifest %s is not valid JSON text: %s"
                         % (path, exc))
    verify_manifest_identity(doc, mode, path)
    return doc, blob


def load_manifest(path: str, mode: str) -> dict:
    """read_manifest() for callers that only need the parsed document."""
    return read_manifest(path, mode)[0]


def verify_local_bins(doc: dict, bins_dir: str) -> dict:
    """Prove the files about to be trusted as "what was deployed" are the ones
    the manifest describes, by full hash. Returns the observed digests."""
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise SystemExit("FAIL manifest carries no artifact_sha256 block")
    observed = {}
    for name in BIN_FILES:
        want = artifacts.get(name)
        if not want:
            raise SystemExit(
                "FAIL manifest carries no %s hash -- deployment provenance "
                "incomplete" % name)
        path = os.path.join(bins_dir, name)
        try:
            got = sha256_file(path)
        except OSError as exc:
            raise SystemExit("FAIL cannot hash %s: %s" % (path, exc))
        if got != want:
            raise SystemExit(
                "FAIL %s\n  manifest %s\n  local    %s\n  the deployed "
                "artifact is not the one this manifest attests"
                % (path, want, got))
        observed[name] = got
    return observed


class PmuQualLink(RunnerLink):
    """RunnerLink plus the one seam the schema-v8 transport needs.

    The inherited v7 helpers are left exactly as they are and keep refusing v8
    payloads; nothing here overrides them. Only the request sequence counter is
    exposed, so the v8 exchange can be driven with the same framing without
    reaching into private state from module scope.
    """

    def next_sequence(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq


def _read_v8_result(link, timeout: float) -> bytes:
    """The GET re-read: its own request, its own sequence, its own response."""
    seq = link.next_sequence()
    link.send_raw(build_frame(CMD_GET_PMU_DIAG_RESULT, seq))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            frame = link.read_frame(min(5.0, max(0.5, deadline - time.time())))
        except ProtocolError:
            break
        if frame.sequence != seq:
            link.late_frames += 1
            continue
        if frame.command == NACK:
            raise Nack(frame.flags, frame.payload[0], frame.payload[1])
        if frame.command != (CMD_GET_PMU_DIAG_RESULT | 0x80):
            raise ProtocolError(
                "unexpected response 0x%02X to GET_PMU_DIAG_RESULT"
                % frame.command)
        return bytes(frame.payload)
    raise RunSequenceError(
        "no GET_PMU_DIAG_RESULT response carrying sequence %d within %.1fs -- "
        "the re-read is half of the evidence, so there is no sample without it"
        % (seq, timeout))


def collect_pmu_qual(link, timeout: float = 60.0, get_timeout: float = 10.0):
    """One schema-v8 sample: the unsolicited COMPLETE plus an independent GET.

    Same discipline the v7 collector enforces, restated over the v8 parser:
    ACK before COMPLETE, no duplicate of either, and a completion carrying an
    earlier exchange's sequence is a straggler -- counted, never adopted.
    """
    # A failed run must not leave the PREVIOUS run's bytes lying around as
    # presentable evidence -- cleared before anything is sent.
    link.last_pmu_qual_raw = None
    link.last_pmu_qual_reread_raw = None

    seq = link.next_sequence()
    link.send_raw(build_frame(CMD_RUN_PMU_DIAG, seq))

    acked = False
    raw = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            frame = link.read_frame(min(5.0, max(0.5, deadline - time.time())))
        except ProtocolError:
            break
        if frame.sequence != seq:
            link.late_frames += 1
            continue
        if frame.command == NACK:
            raise Nack(frame.flags, frame.payload[0], frame.payload[1])
        if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
            if acked:
                raise RunSequenceError(
                    "duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
            acked = True
            continue
        if frame.command == CMD_PMU_DIAG_COMPLETE:
            if not acked:
                raise RunSequenceError(
                    "PMU_DIAG_COMPLETE arrived before the ACK")
            raw = bytes(frame.payload)
            break
        if not acked:
            raise RunSequenceError(
                "frame 0x%02X arrived before the ACK" % frame.command)
        link.late_frames += 1

    if not acked:
        raise RunSequenceError(
            "no ACK for CMD_RUN_PMU_DIAG within %.1fs" % timeout)
    if raw is None:
        raise RunSequenceError(
            "no PMU_DIAG_COMPLETE carrying sequence %d within %.1fs -- a "
            "completion from an earlier run is never adopted" % (seq, timeout))

    # Bounded look for a second latch on this same sequence. Two completions
    # can carry different bytes, and whichever arrived first would otherwise
    # become "the" evidence by accident.
    while True:
        try:
            frame = link.read_frame(DRAIN_SECONDS)
        except ProtocolError:
            break
        if frame.sequence != seq:
            link.late_frames += 1
            continue
        if frame.command == CMD_PMU_DIAG_COMPLETE:
            raise RunSequenceError(
                "duplicate PMU_DIAG_COMPLETE for seq=%d -- the target latched "
                "twice and this sample is not attributable to one run" % seq)
        if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
            raise RunSequenceError(
                "duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
        link.late_frames += 1

    res = parse_pmu_qual_payload(raw)
    link.last_pmu_qual_raw = raw

    reread_raw = _read_v8_result(link, get_timeout)
    if not reread_raw:
        raise RunSequenceError(
            "GET_PMU_DIAG_RESULT returned an empty payload -- the re-read is "
            "half of the evidence, so there is no sample without it")
    if reread_raw != raw:
        raise RunSequenceError(
            "GET_PMU_DIAG_RESULT bytes differ from the PMU_DIAG_COMPLETE "
            "payload -- latch bug or a stale result being re-served, do not "
            "analyse")
    parse_pmu_qual_payload(reread_raw)  # decoded on its own, never assumed
    link.last_pmu_qual_reread_raw = reread_raw
    return res, raw, reread_raw


def verify_record_identity(res, doc: dict, mode: str) -> None:
    """The record the target returned must be the image this invocation
    claims. Checked BEFORE anything is written."""
    want_mode = PMU_QUAL_MODES[mode]
    if res.qualification_mode != want_mode:
        raise SystemExit(
            "FAIL deployed %s (mode %d) but the target reports "
            "qualification_mode=%d -- wrong image on the SD, result NOT written"
            % (mode, want_mode, res.qualification_mode))
    want_build = manifest_build_id(doc)
    if res.build_id != want_build:
        raise SystemExit(
            "FAIL %s expects build_id 0x%08X but the target reports 0x%08X -- "
            "wrong artifact, result NOT written"
            % (mode, want_build, res.build_id))
    if res.nc_control_id != 0:
        raise SystemExit(
            "FAIL target reports nc_control_id=%d: negative-control images "
            "must never feed the qualification dataset" % res.nc_control_id)
    expected_lr = doc["expected_return_address"]
    if res.hook_callsite_lr_observed != expected_lr:
        raise SystemExit(
            "FAIL %s observed callsite LR 0x%08X but its own manifest expects "
            "0x%08X -- the hook did not fire at the attested callsite, result "
            "NOT written (the other mode's address is never the reference)"
            % (mode, res.hook_callsite_lr_observed, expected_lr))


def build_record(mode: str, host_boot_index: int, bins_dir: str, doc: dict,
                 manifest_path: str, manifest_blob: bytes,
                 artifact_sha256: dict, res, raw: bytes,
                 reread_raw: bytes) -> dict:
    """The archive.

    Keys are split the way the contract splits them: the host knows what it
    deployed, the target reports what it observed. The manifest is carried
    BOTH as the exact bytes preflight read and as the parsed document, so the
    analyzer re-derives the parse instead of inheriting this run's copy of it.
    """
    return {
        "host": {
            "mode": mode,
            "host_boot_index": host_boot_index,
            "bins_dir": bins_dir,
            "artifact_sha256": dict(artifact_sha256),
            "manifest_path": manifest_path,
            "manifest_sha256": hashlib.sha256(manifest_blob).hexdigest(),
            # The exact bytes the gate wrote. The parsed copy below is a
            # convenience; THIS is the evidence, and the analyzer re-parses it.
            "manifest_text": manifest_blob.decode("utf-8"),
        },
        "manifest": doc,
        "target": {
            "schema_version": res.schema_version,
            "build_id": "0x%08X" % res.build_id,
            "qualification_mode": res.qualification_mode,
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
            "pmcr_readback_after_disable": "0x%08X" % res.pmcr_readback_after_disable,
            "pmu_mmio_read_count_delta": res.pmu_mmio_read_count_delta,
            "pmu_mmio_write_count_delta": res.pmu_mmio_write_count_delta,
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
            "npu_cmd_after_return": "0x%08X" % res.npu_cmd_after_return,
            "power_seam_id": res.power_seam_id,
            "power_rehold_performed": res.power_rehold_performed,
            "rehold_guard_cycles": res.rehold_guard_cycles,
            "npu_cmd_after_seam": "0x%08X" % res.npu_cmd_after_seam,
            "npu_status_after_seam": "0x%08X" % res.npu_status_after_seam,
            "golden_window_base": "0x%08X" % res.golden_window_base,
            "golden_window_len": "0x%X" % res.golden_window_len,
            "golden_window_crc": "0x%08X" % res.golden_window_crc,
            "hook_armed": res.hook_armed,
            "hook_arm_consumed": res.hook_arm_consumed,
            "hook_detected_count": res.hook_detected_count,
            "hook_fired_count": res.hook_fired_count,
            "hook_snapshot_valid": res.hook_snapshot_valid,
            "hook_callsite_lr_observed": "0x%08X" % res.hook_callsite_lr_observed,
            "hook_entry_timestamp": res.hook_entry_timestamp,
            "hook_exit_timestamp": res.hook_exit_timestamp,
            "npu_cmd_at_hook": "0x%08X" % res.npu_cmd_at_hook,
            "pmcr_disable_readback_at_hook": "0x%08X" % res.pmcr_disable_readback_at_hook,
            "hook_pmu_mmio_read_count": res.hook_pmu_mmio_read_count,
            "hook_pmu_mmio_write_count": res.hook_pmu_mmio_write_count,
            "trailing_words": res.trailing_words,
            "snapshots": {
                name: dict(vars(snap)) for name, snap in
                (("pre", res.pre),
                 ("internal_pre_release", res.internal_pre_release),
                 ("internal_post_disable", res.internal_post_disable),
                 ("after_return", res.after_return))
            },
        },
        "derived": classify_pmu_qual(res, doc),
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


def prime(link) -> None:
    """Walk the state machine to INPUT_READY exactly as run_pmu_diag.py does:
    a dummy blob and an empty input. The qualification run executes the fixed
    compiled-in inference regardless of the staged bytes."""
    link.reset_runner()
    blob = b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("Q0", "Q1"),
                    help="Q0 = detect-only baseline, Q1 = H-PRINTF candidate")
    ap.add_argument("--bins-dir", required=True,
                    help="build dir holding the APP/VECTORS/DDR.BIN actually deployed")
    ap.add_argument("--manifest", required=True,
                    help="check_pmu_qual.py manifest for THIS mode")
    ap.add_argument("--host-boot-index", required=True, type=int,
                    help="host-side boot counter; bump on EVERY reboot")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", default=PORT_DEFAULT)
    a = ap.parse_args()

    # Nothing after this point can rescue a wrong image, so all of it happens
    # before the port is opened.
    doc, manifest_blob = read_manifest(a.manifest, a.mode)
    artifacts = verify_local_bins(doc, a.bins_dir)

    link = PmuQualLink(a.port)
    try:
        link.ping()
        prime(link)
        res, raw, reread_raw = collect_pmu_qual(link)
    finally:
        link.close()

    verify_record_identity(res, doc, a.mode)
    record = build_record(a.mode, a.host_boot_index, a.bins_dir, doc,
                          a.manifest, manifest_blob, artifacts, res, raw,
                          reread_raw)

    with open(a.out, "w") as f:
        json.dump(record, f, indent=2)

    derived = record["derived"]
    print("wrote %s" % a.out)
    print("  %s boot=%d seq=%d build=0x%08X"
          % (a.mode, a.host_boot_index, res.run_sequence, res.build_id))
    print("  callsite LR observed 0x%08X == %s manifest 0x%08X"
          % (res.hook_callsite_lr_observed, a.mode,
             doc["expected_return_address"]))
    print("  hook: armed=%d consumed=%d detected=%d fired=%d snapshot_valid=%d"
          % (res.hook_armed, res.hook_arm_consumed, res.hook_detected_count,
             res.hook_fired_count, res.hook_snapshot_valid))
    print("  raw delta (diagnostic): %d" % derived["raw_delta_diagnostic"])
    if derived["valid"]:
        print("  npu_pmu_window_cycles: %d" % derived["npu_pmu_window_cycles"])
    else:
        print("  npu_pmu_window_cycles: INVALID")
        for reason in derived["invalid_reasons"]:
            print("    FAIL %s" % reason)
        if a.mode == "Q0":
            print("  (Q0 is the detect-only baseline: it is invalid as a "
                  "measurement BY DESIGN and never becomes one)")


if __name__ == "__main__":
    main()
