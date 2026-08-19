#!/usr/bin/env python3
"""Drive one V14 cell: deploy a variant, boot it, and take ten samples.

This is transport and sequencing only. It decides nothing: whether a frame is a
V14 record is the parser's answer, whether it is a sample is the classifier's,
and whether a cell is a cell is the collector's. Each of those was qualified
before any board was touched, and this script exists so that none of them has to
be re-implemented on the day the board runs.

The per-cell path is the one the plan fixes and does not vary by variant:

    verify source hashes -> mount/write gate -> deploy -> destination hashes
    -> unmount -> USB_OFF and /dev/sdb absent -> root-inclusive UART gate
    -> fresh full boot -> DDR/CPUWAIT -> protocol identity, IDLE, errors zero
    -> ten sequential runs

Every one of those is a gate. A cell that skipped any of them is not a cell, and
this script stops rather than continuing without one -- including at the boundary
the plan calls out, where the UART holder check and the transition after it must
not have anything in between.

Nothing here writes to the SD except `deploy`, and `deploy` refuses to run unless
the card was mounted through the bounded path the procedure defines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_pmu_qual as rq  # noqa: E402
import runner_proto_pmu_completion_visibility_v14 as v14  # noqa: E402
from runner_proto import (  # noqa: E402
    CMD_GET_PMU_DIAG_RESULT,
    CMD_PMU_DIAG_COMPLETE,
    CMD_RUN_PMU_DIAG,
    NACK,
    Nack,
    ProtocolError,
    RunSequenceError,
    build_frame,
)

MCC_PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
RUNNER_PORT = rq.PORT_DEFAULT
ARTIFACTS = ("APP.BIN", "VECTORS.BIN", "DDR.BIN")
PROTOCOL_COUNTERS = (
    "rx_overrun",
    "bad_magic",
    "bad_version",
    "bad_crc",
    "length_error",
    "sequence_error",
    "parser_resync",
)
IDLE_STATE = 1


class CellAbort(RuntimeError):
    """A gate this cell cannot pass. The cell is not a cell; nothing is salvaged."""


# --- board transport ------------------------------------------------------


def mcc(command: str, wait: float = 3.0) -> str:
    import serial

    port = serial.Serial(MCC_PORT, 115200, timeout=1, write_timeout=2)
    try:
        port.reset_input_buffer()
        port.write(command.encode() + b"\r")
        port.flush()
        time.sleep(wait)
        return port.read(65536).decode("ascii", errors="replace")
    finally:
        port.close()


def sh(*argv, stdin: str | None = None):
    return subprocess.run(argv, capture_output=True, text=True, input=stdin)


def sdb_present() -> bool:
    return os.path.exists("/dev/sdb")


def uart_holders_zero(password: str) -> bool:
    """Root-inclusive. A check that cannot see root proves nothing about root."""

    probe = sh(
        "sudo", "-S", "-p", "", "lsof",
        "/dev/sdb", "/dev/sdb1",
        "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3",
        stdin=password + "\n",
    )
    return not probe.stdout.strip()


def reboot_and_gate() -> tuple[bool, bool]:
    """Full boot. Returns (ddr_passed, cpuwait_cleared) as the MCC reported them."""

    mcc("REBOOT", wait=3.0)
    seen = ""
    deadline = time.time() + 150.0
    while time.time() < deadline:
        seen += mcc("", wait=3.0)
        if "Clearing SCC CPUWAIT" in seen and "Cmd>" in seen:
            time.sleep(3)
            break
    return (
        "DDR memory test at 0x70000000: PASSED" in seen,
        "Clearing SCC CPUWAIT" in seen,
    )


# --- deployment -----------------------------------------------------------


def deploy(variant_dir: str, password: str) -> dict:
    """Write one variant's three artifacts, and prove what landed on the card.

    The source hashes are taken before the card is mounted and the destination
    hashes after the copy, from the card itself. Equality of the two is the only
    thing that makes the deployment a fact rather than an intention.
    """

    source = {}
    for name in ARTIFACTS:
        path = os.path.join(variant_dir, name)
        source[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()

    mcc("USB_ON", wait=4.0)
    for _ in range(20):
        if os.path.exists("/dev/sdb1"):
            break
        time.sleep(0.5)
    if not os.path.exists("/dev/sdb1"):
        mcc("USB_OFF", wait=3.0)
        raise CellAbort("USB_ON did not present /dev/sdb1")

    identity = sh("lsblk", "-n", "-o", "FSTYPE,LABEL", "/dev/sdb1").stdout.split()
    transport = sh("lsblk", "-n", "-o", "TRAN", "/dev/sdb").stdout.split()
    if identity[:2] != ["vfat", "M1SDP"] or "usb" not in transport:
        mcc("USB_OFF", wait=3.0)
        raise CellAbort("the block device is not the board's card: %r" % (identity + transport))

    mountpoint = sh("mktemp", "-d", "/tmp/pmu_v14_sd.XXXXXXXX").stdout.strip()
    mounted = False
    destination = {}
    try:
        sh(
            "sudo", "-S", "-p", "", "mount", "-t", "vfat", "/dev/sdb1", mountpoint,
            "-o", "uid=%d,gid=%d,umask=022" % (os.getuid(), os.getgid()),
            stdin=password + "\n",
        )
        mounted = bool(sh("findmnt", "-rn", "-S", "/dev/sdb1").stdout.strip())
        if not mounted:
            raise CellAbort("the bounded mount did not take")
        for name in ARTIFACTS:
            target = os.path.join(mountpoint, "SOFTWARE", name)
            with open(os.path.join(variant_dir, name), "rb") as handle:
                payload = handle.read()
            with open(target, "wb") as handle:
                handle.write(payload)
        sh("sync")
        for name in ARTIFACTS:
            target = os.path.join(mountpoint, "SOFTWARE", name)
            destination[name] = hashlib.sha256(open(target, "rb").read()).hexdigest()
    finally:
        if mounted:
            sh("sync")
            sh("sudo", "-S", "-p", "", "umount", mountpoint, stdin=password + "\n")
            if sh("findmnt", "-rn", "-S", "/dev/sdb1").stdout.strip():
                # The one thing the procedure calls its most dangerous action.
                raise CellAbort("the card is still mounted: USB_OFF was not issued")
        sh("rmdir", mountpoint)
        mcc("USB_OFF", wait=3.0)
        time.sleep(2)

    if sdb_present():
        raise CellAbort("/dev/sdb survived USB_OFF")
    if destination != source:
        raise CellAbort("what landed on the card is not what was sent: %r" % destination)
    return {"source": source, "destination": destination}


# --- one run --------------------------------------------------------------


def collect_one(link, timeout: float = 60.0, get_timeout: float = 10.0):
    """One measured run, returned as the bytes it arrived in and its re-read.

    Nothing is interpreted here. The frame is handed to the collector, which
    asks the parser and the classifier and decides whether the run counts.
    """

    sequence = link.next_sequence()
    link.send_raw(build_frame(CMD_RUN_PMU_DIAG, sequence))

    acked = False
    raw = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            frame = link.read_frame(min(5.0, max(0.5, deadline - time.time())))
        except ProtocolError:
            break
        if frame.sequence != sequence:
            link.late_frames += 1
            continue
        if frame.command == NACK:
            raise Nack(frame.flags, frame.payload[0], frame.payload[1])
        if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
            if acked:
                raise RunSequenceError("duplicate ACK for CMD_RUN_PMU_DIAG")
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
        raise RunSequenceError("no PMU_DIAG_COMPLETE within %.1fs" % timeout)

    # The re-read is its own request with its own sequence, so a frame that
    # merely repeated would not satisfy it.
    sequence = link.next_sequence()
    link.send_raw(build_frame(CMD_GET_PMU_DIAG_RESULT, sequence))
    reread = None
    deadline = time.time() + get_timeout
    while time.time() < deadline:
        try:
            frame = link.read_frame(min(5.0, max(0.5, deadline - time.time())))
        except ProtocolError:
            break
        if frame.sequence != sequence:
            link.late_frames += 1
            continue
        if frame.command == NACK:
            raise Nack(frame.flags, frame.payload[0], frame.payload[1])
        if frame.command != (CMD_GET_PMU_DIAG_RESULT | 0x80):
            raise ProtocolError("unexpected 0x%02X to GET_PMU_DIAG_RESULT" % frame.command)
        reread = bytes(frame.payload)
        break
    if reread is None:
        raise RunSequenceError("no GET_PMU_DIAG_RESULT within %.1fs" % get_timeout)
    return raw, reread


# --- one cell -------------------------------------------------------------


def run_cell(variant, variant_dir, password, runs=10):
    """Deploy, boot, gate, and take ten runs. Returns the cell's evidence."""

    evidence = {"variant": variant, "gates": {}}

    evidence["gates"]["deploy"] = deploy(variant_dir, password)

    # The plan calls this a TOCTOU boundary: the holder check and the transition
    # after it must have nothing in between.
    if not uart_holders_zero(password):
        raise CellAbort("a UART or block-device holder appeared before the boot")
    evidence["gates"]["uart_holders_zero"] = True

    ddr, cpuwait = reboot_and_gate()
    evidence["gates"]["ddr_selftest_passed"] = ddr
    evidence["gates"]["cpuwait_cleared"] = cpuwait
    if not (ddr and cpuwait):
        raise CellAbort("the deployed image did not pass DDR/CPUWAIT")

    link = rq.PmuQualLink(RUNNER_PORT)
    try:
        counters = link.ping()
        evidence["gates"]["ping"] = {
            "state": counters.state,
            **{name: getattr(counters, name) for name in PROTOCOL_COUNTERS},
        }
        if counters.state != IDLE_STATE:
            raise CellAbort("the runner answered from state %d, not IDLE" % counters.state)
        if any(getattr(counters, name) for name in PROTOCOL_COUNTERS):
            raise CellAbort("a protocol counter is not zero before the first run")

        boot_id = "%s-%d" % (variant, int(time.time()))
        frames = []
        for index in range(runs):
            raw, reread = collect_one(link)
            frames.append({"index": index, "raw": raw.hex(), "reread": reread.hex()})
        evidence["boot_id"] = boot_id
        evidence["frames"] = frames
    finally:
        link.close()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one V14 cell against the board.")
    parser.add_argument("--variant", required=True, choices=("Q", "QS", "SQ"))
    parser.add_argument("--variant-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("the bounded mount needs the operator credential on stdin", file=sys.stderr)
        return 2
    try:
        evidence = run_cell(args.variant, args.variant_dir, password, args.runs)
    except (CellAbort, ProtocolError, Nack, OSError) as exc:
        print("CELL ABORT %s: %s" % (args.variant, exc), file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, indent=2, sort_keys=True)
    print("CELL OK %s runs=%d boot=%s" % (args.variant, len(evidence["frames"]), evidence["boot_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
