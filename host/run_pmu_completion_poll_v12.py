"""Collect one PMU_COMPLETION_POLL_DIAG_V12 sample and bind it to its manifest."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time

try:
    import host.run_pmu_qual as rq
    from host.runner_proto import (
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
    from host.runner_proto_pmu_completion_poll_v12 import (
        PMU_COMPLETION_POLL_V12_BUILD_ID,
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
        target_fields,
        verify_manifest_identity,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
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
    from runner_proto_pmu_completion_poll_v12 import (
        PMU_COMPLETION_POLL_V12_BUILD_ID,
        classify_pmu_completion_poll_v12_payload,
        parse_pmu_completion_poll_v12_payload,
        target_fields,
        verify_manifest_identity,
    )

PORT_DEFAULT = rq.PORT_DEFAULT


class CampaignAbort(RuntimeError):
    """A timeout or identity failure that requires a fresh boot."""


@dataclass
class CampaignState:
    blocked_boot_index: int | None = None
    next_boot_index: int | None = None
    current_boot_index: int | None = None
    next_run_sequence: int = 1

    def validate(self, host_boot_index: int, run_sequence: int | None = None) -> None:
        if host_boot_index <= 0:
            raise CampaignAbort("host_boot_index must be a positive integer")
        if self.blocked_boot_index is not None and host_boot_index <= self.blocked_boot_index:
            raise CampaignAbort(
                "fresh boot required after boot %d; boot %d is refused"
                % (self.blocked_boot_index, host_boot_index)
            )
        if self.next_boot_index is not None and host_boot_index < self.next_boot_index:
            raise CampaignAbort(
                "host_boot_index %d regressed below required fresh boot %d"
                % (host_boot_index, self.next_boot_index)
            )
        if self.current_boot_index is None or host_boot_index != self.current_boot_index:
            self.current_boot_index = host_boot_index
            self.next_run_sequence = 1
        if run_sequence is not None and run_sequence != self.next_run_sequence:
            raise CampaignAbort(
                "boot %d run_sequence %d != expected %d"
                % (host_boot_index, run_sequence, self.next_run_sequence)
            )

    def note_success(self, host_boot_index: int, run_sequence: int) -> None:
        self.validate(host_boot_index, run_sequence)
        self.next_run_sequence = run_sequence + 1

    def note_timeout(self, host_boot_index: int, run_sequence: int) -> None:
        self.validate(host_boot_index, run_sequence)
        self.blocked_boot_index = host_boot_index
        self.next_boot_index = host_boot_index + 1
        self.current_boot_index = None
        self.next_run_sequence = 1


def read_manifest(path: str) -> tuple[dict, bytes]:
    doc, blob = rq.read_manifest_document(path)
    verify_manifest_identity(doc, path)
    return doc, blob


def verify_record_identity(res, manifest: dict) -> None:
    if res.build_id != PMU_COMPLETION_POLL_V12_BUILD_ID:
        raise SystemExit(
            "FAIL target build_id 0x%08X is not the V12 identity 0x%08X"
            % (res.build_id, PMU_COMPLETION_POLL_V12_BUILD_ID)
        )
    if res.qualification_mode != PMU_QUAL_MODES["Q1"]:
        raise SystemExit(
            "FAIL target qualification_mode=%d is not Q1" % res.qualification_mode
        )
    if res.diag_case != 1 or res.nc_control_id != 0:
        raise SystemExit(
            "FAIL target identity diag_case=%d nc_control_id=%d is not V12 normal case-A"
            % (res.diag_case, res.nc_control_id)
        )
    expected_lr = manifest["expected_return_address"]
    if res.hook_callsite_lr_observed != expected_lr:
        raise SystemExit(
            "FAIL observed LR 0x%08X but manifest expects 0x%08X"
            % (res.hook_callsite_lr_observed, expected_lr)
        )


def _canonical_manifest_bytes(manifest: dict, manifest_blob: bytes | None) -> bytes:
    if manifest_blob is None:
        return (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8")
    try:
        decoded = json.loads(manifest_blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CampaignAbort("manifest_blob is not valid JSON: %s" % exc)
    if decoded != manifest:
        raise CampaignAbort("manifest_blob does not decode to the supplied manifest")
    return manifest_blob


def _raw_payload_bytes(raw) -> bytes:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, dict):
        payload_hex = raw.get("payload_hex")
        if not isinstance(payload_hex, str):
            raise ValueError("raw payload dict has no payload_hex")
        return bytes.fromhex(payload_hex)
    raise TypeError("unsupported raw payload type %r" % (type(raw).__name__,))


def _raw_meta(raw: bytes, reread: bytes) -> dict:
    return {
        "payload_hex": raw.hex(),
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "reread_payload_hex": reread.hex(),
        "reread_payload_sha256": hashlib.sha256(reread).hexdigest(),
        "reread_matches_run_payload": reread == raw,
    }


def _raw_reread_identity_ok(raw_doc: dict) -> bool:
    return (
        raw_doc.get("reread_matches_run_payload") is True
        and raw_doc.get("payload_hex") == raw_doc.get("reread_payload_hex")
        and raw_doc.get("payload_sha256") == raw_doc.get("reread_payload_sha256")
    )


def _read_v12_result(link: rq.PmuQualLink, timeout: float) -> bytes:
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


def collect_pmu_completion_poll_v12(
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

    res = parse_pmu_completion_poll_v12_payload(raw)
    link.last_pmu_diag_raw = raw
    reread = _read_v12_result(link, get_timeout)
    if not reread:
        raise RunSequenceError("GET_PMU_DIAG_RESULT returned an empty payload")
    if reread != raw:
        raise RunSequenceError("GET_PMU_DIAG_RESULT reread differs from COMPLETE payload")
    parse_pmu_completion_poll_v12_payload(reread)
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
    manifest_path: str | None,
) -> dict:
    derived = classify_pmu_completion_poll_v12_payload(res, manifest)
    return {
        "variant": "PMU_COMPLETION_POLL_DIAG_V12",
        "host": {
            "host_boot_index": host_boot_index,
            "manifest_path": manifest_path,
            "manifest_sha256": hashlib.sha256(manifest_blob).hexdigest(),
            "manifest_text": manifest_blob.decode("utf-8"),
            "artifact_sha256": dict(artifacts),
        },
        "manifest": manifest,
        "target": target_fields(res),
        "derived": derived if derived["valid"] else None,
        "raw": _raw_meta(raw, reread),
    }


def collect_one(
    link=None,
    *,
    raw=None,
    manifest=None,
    manifest_blob: bytes | None = None,
    manifest_path: str | None = None,
    artifact_sha256: dict | None = None,
    out_path=None,
    host_boot_index=1,
    timeout: float = 60.0,
    get_timeout: float = 10.0,
    campaign_state: CampaignState | None = None,
):
    if manifest is None:
        raise TypeError("collect_one requires an attested manifest")
    if host_boot_index <= 0:
        raise CampaignAbort("host_boot_index must be a positive integer")
    verify_manifest_identity(manifest, manifest_path or "<manifest>")
    manifest_blob = _canonical_manifest_bytes(manifest, manifest_blob)
    artifacts = dict(artifact_sha256 or manifest.get("artifact_sha256") or {})
    if artifacts != manifest["artifact_sha256"]:
        raise CampaignAbort("artifact identity mismatch before collection")
    if out_path is not None and Path(out_path).exists():
        raise CampaignAbort("refusing to overwrite existing archive %s" % out_path)

    run_sequence_hint = None
    if isinstance(raw, dict):
        payload_hint = _raw_payload_bytes(raw)
        run_sequence_hint = parse_pmu_completion_poll_v12_payload(payload_hint).run_sequence
    if campaign_state is not None:
        campaign_state.validate(host_boot_index, run_sequence_hint)

    if raw is None:
        if link is None:
            raise TypeError("collect_one requires either link or raw payload")
        res, payload, reread = collect_pmu_completion_poll_v12(
            link, timeout=timeout, get_timeout=get_timeout
        )
        reread_protocol_ok = True
    else:
        payload = _raw_payload_bytes(raw)
        reread = payload
        if isinstance(raw, dict):
            reread = bytes.fromhex(raw.get("reread_payload_hex", payload.hex()))
        res = parse_pmu_completion_poll_v12_payload(payload)
        try:
            parse_pmu_completion_poll_v12_payload(reread)
            reread_protocol_ok = True
        except ProtocolError:
            reread_protocol_ok = False

    verify_record_identity(res, manifest)
    record = build_record(
        manifest=manifest,
        manifest_blob=manifest_blob,
        artifacts=artifacts,
        res=res,
        raw=payload,
        reread=reread,
        host_boot_index=host_boot_index,
        manifest_path=manifest_path,
    )
    derived = classify_pmu_completion_poll_v12_payload(res, manifest)
    raw_identity_ok = _raw_reread_identity_ok(record["raw"]) and reread_protocol_ok
    outcome = {
        "valid": bool(derived["valid"]) and raw_identity_ok,
        "campaign_abort": bool(derived["campaign_abort"]) or not raw_identity_ok,
        "fresh_boot_required": bool(derived["fresh_boot_required"]) or not raw_identity_ok,
        "archive_write": False,
        "derived": record["derived"],
        "record": record,
        "raw_reread_identity_ok": raw_identity_ok,
    }
    if campaign_state is not None:
        if derived["timeout"] or not raw_identity_ok:
            campaign_state.note_timeout(host_boot_index, res.run_sequence)
        else:
            campaign_state.note_success(host_boot_index, res.run_sequence)
    if not outcome["valid"]:
        record["derived"] = None
        outcome["derived"] = None
        return outcome
    if out_path is not None:
        out = Path(out_path)
        with out.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        outcome["archive_write"] = True
    return outcome


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
        outcome = collect_one(
            link,
            manifest=manifest,
            manifest_blob=manifest_blob,
            manifest_path=args.manifest,
            artifact_sha256=artifacts,
            out_path=args.out,
            host_boot_index=args.host_boot_index,
        )
    finally:
        link.close()

    if not outcome["valid"]:
        raise SystemExit("FAIL invalid V12 sample must not be archived")


if __name__ == "__main__":
    main()
