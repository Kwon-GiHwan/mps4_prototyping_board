"""Raw PMU diagnostic exchange shared by the V9–V13 experiment runners.

Payload parsing and archive state belong to the versioned runners. Keep the
frozen transport's module identity so callers catch its original exceptions.
"""

from __future__ import annotations

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_pmu_qual as rq
from runner_proto import (
    CMD_GET_PMU_DIAG_RESULT,
    CMD_PMU_DIAG_COMPLETE,
    CMD_RUN_PMU_DIAG,
    NACK,
    Nack,
    ProtocolError,
    RunSequenceError,
    build_frame,
)


def read_diag_result(link: rq.PmuQualLink, timeout: float) -> bytes:
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
        "no GET_PMU_DIAG_RESULT response carrying sequence %d within %.1fs"
        % (seq, timeout))



def run_diag_raw(link: rq.PmuQualLink, timeout: float) -> bytes:
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
            raise RunSequenceError(
                "frame 0x%02X arrived before the ACK" % frame.command)
        link.late_frames += 1

    if not acked:
        raise RunSequenceError("no ACK for CMD_RUN_PMU_DIAG within %.1fs" % timeout)
    if raw is None:
        raise RunSequenceError(
            "no PMU_DIAG_COMPLETE carrying sequence %d within %.1fs"
            % (seq, timeout))

    while True:
        try:
            frame = link.read_frame(rq.DRAIN_SECONDS)
        except ProtocolError:
            break
        if frame.sequence != seq:
            link.late_frames += 1
            continue
        if frame.command == CMD_PMU_DIAG_COMPLETE:
            raise RunSequenceError(
                "duplicate PMU_DIAG_COMPLETE for seq=%d" % seq)
        if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
            raise RunSequenceError(
                "duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
        link.late_frames += 1
    return raw
