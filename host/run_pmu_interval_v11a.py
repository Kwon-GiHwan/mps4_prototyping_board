"""Collect one PMU_INTERVAL_ENTRY_DIAG_V11A sample and bind it to its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import run_pmu_qual as rq
from runner_proto import (
    CMD_GET_PMU_DIAG_RESULT,
    CMD_PMU_DIAG_COMPLETE,
    CMD_RUN_PMU_DIAG,
    NACK,
    Nack,
    PMU_QUAL_MODES,
    ProtocolError,
    RunSequenceError,
    build_frame,
)
from runner_proto_pmu_interval_v11a import (
    PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID,
    PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256,
    classify_pmu_interval_diag_v11a,
    parse_pmu_interval_diag_v11a_payload,
    target_fields,
    verify_manifest_identity,
)

PORT_DEFAULT = rq.PORT_DEFAULT


def read_manifest(path: str) -> tuple[dict, bytes]:
    doc, blob = rq.read_manifest_document(path)
    digest = hashlib.sha256(blob).hexdigest()
    if digest != PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256:
        raise SystemExit(
            "FAIL %s: manifest SHA-256 %s does not match frozen V11-A %s"
            % (path, digest, PMU_INTERVAL_V11A_FROZEN_MANIFEST_SHA256)
        )
    verify_manifest_identity(doc, path)
    return doc, blob


def verify_record_identity(res, manifest: dict) -> None:
    if res.build_id != PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID:
        raise SystemExit(
            "FAIL target build_id 0x%08X is not the v11a identity 0x%08X"
            % (res.build_id, PMU_INTERVAL_ENTRY_DIAG_V11A_BUILD_ID)
        )
    if res.qualification_mode != PMU_QUAL_MODES["Q1"]:
        raise SystemExit(
            "FAIL target qualification_mode=%d is not Q1" % res.qualification_mode
        )
    if res.diag_case != 1 or res.nc_control_id != 0:
        raise SystemExit(
            "FAIL target identity diag_case=%d nc_control_id=%d is not V11-A normal case-A"
            % (res.diag_case, res.nc_control_id)
        )
    expected_lr = manifest["expected_return_address"]
    if res.hook_callsite_lr_observed != expected_lr:
        raise SystemExit(
            "FAIL observed LR 0x%08X but manifest expects 0x%08X"
            % (res.hook_callsite_lr_observed, expected_lr)
        )


def _read_v11a_result(link: rq.PmuQualLink, timeout: float) -> bytes:
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
                "unexpected response 0x%02X to GET_PMU_DIAG_RESULT" % frame.command
            )
        return bytes(frame.payload)
    raise RunSequenceError(
        "no GET_PMU_DIAG_RESULT response carrying sequence %d within %.1fs"
        % (seq, timeout)
    )


def collect_pmu_interval_v11a(
    link: rq.PmuQualLink, timeout: float = 60.0, get_timeout: float = 10.0
):
    link.last_pmu_diag_raw = None
    link.last_pmu_diag_reread_raw = None
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
                raise RunSequenceError("duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
            acked = True
            continue
        if frame.command == CMD_PMU_DIAG_COMPLETE:
            if not acked:
                raise RunSequenceError("PMU_DIAG_COMPLETE arrived before the ACK")
            raw = bytes(frame.payload)
            break
        if not acked:
            raise RunSequenceError("frame 0x%02X arrived before the ACK" % frame.command)
        link.late_frames += 1

    if not acked:
        raise RunSequenceError("no ACK for CMD_RUN_PMU_DIAG within %.1fs" % timeout)
    if raw is None:
        raise RunSequenceError(
            "no PMU_DIAG_COMPLETE carrying sequence %d within %.1fs" % (seq, timeout)
        )

    while True:
        try:
            frame = link.read_frame(rq.DRAIN_SECONDS)
        except ProtocolError:
            break
        if frame.sequence != seq:
            link.late_frames += 1
            continue
        if frame.command == CMD_PMU_DIAG_COMPLETE:
            raise RunSequenceError("duplicate PMU_DIAG_COMPLETE for seq=%d" % seq)
        if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
            raise RunSequenceError("duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
        link.late_frames += 1

    res = parse_pmu_interval_diag_v11a_payload(raw)
    link.last_pmu_diag_raw = raw
    reread = _read_v11a_result(link, get_timeout)
    if not reread:
        raise RunSequenceError("GET_PMU_DIAG_RESULT returned an empty payload")
    if reread != raw:
        raise RunSequenceError("GET_PMU_DIAG_RESULT reread differs from COMPLETE payload")
    parse_pmu_interval_diag_v11a_payload(reread)
    link.last_pmu_diag_reread_raw = reread
    return res, raw, reread


def build_record(
    manifest: dict,
    manifest_blob: bytes,
    artifacts: dict,
    res,
    raw: bytes,
    reread: bytes,
    host_boot_index: int,
    manifest_path: str,
) -> dict:
    derived = classify_pmu_interval_diag_v11a(res, manifest)
    return {
        "variant": "PMU_INTERVAL_ENTRY_DIAG_V11A",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_path": manifest_path,
            "manifest_sha256": hashlib.sha256(manifest_blob).hexdigest(),
            "manifest_text": manifest_blob.decode("utf-8"),
            "artifact_sha256": dict(artifacts),
        },
        "manifest": manifest,
        "target": target_fields(res),
        "derived": derived,
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_payload_hex": reread.hex(),
            "reread_payload_sha256": hashlib.sha256(reread).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bins-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host-boot-index", required=True, type=int)
    ap.add_argument("--port", default=PORT_DEFAULT)
    args = ap.parse_args()

    if args.host_boot_index <= 0:
        raise SystemExit("FAIL --host-boot-index must be a positive fresh-boot index")
    if os.path.exists(args.out):
        raise SystemExit("FAIL refusing to overwrite existing sample %s" % args.out)

    manifest, manifest_blob = read_manifest(args.manifest)
    artifacts = rq.verify_local_bins(manifest, args.bins_dir)
    link = rq.PmuQualLink(args.port)
    try:
        link.ping()
        rq.prime(link)
        res, raw, reread = collect_pmu_interval_v11a(link)
    finally:
        link.close()

    verify_record_identity(res, manifest)
    doc = build_record(
        manifest=manifest,
        manifest_blob=manifest_blob,
        artifacts=artifacts,
        res=res,
        raw=raw,
        reread=reread,
        host_boot_index=args.host_boot_index,
        manifest_path=args.manifest,
    )
    with open(args.out, "x") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True)
        handle.write("\n")
    if not doc["derived"]["valid"]:
        raise SystemExit("FAIL invalid V11-A sample archived without a V11-A window value")


if __name__ == "__main__":
    main()
