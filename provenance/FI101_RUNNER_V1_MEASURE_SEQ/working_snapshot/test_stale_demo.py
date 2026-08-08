"""Same-boot stale-output demonstration.

The one remaining deployment blocker: prove that after a successful RUN, a
RUN whose NPU execution is skipped cannot return the previous run's CRC.
Everything happens in ONE boot session -- no reboot between the good and the
bad run, because a reboot would clear the hazard being tested.

Requires the TEST_HOOKS image (CMD_TEST_SKIP_NEXT_NPU present).
"""

import os
import struct
import sys
import time
import zlib

from runner_proto import (
    CMD_GET_RESULT,
    ERR_RESULT_NOT_VALID,
    PROTO_MEASURE_V2,
    RUN_VALID_REQUIRED_MASK,
    Nack,
    ProtocolError,
    RunnerLink,
    build_frame,
    parse_measurement_payload,
)

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
CMD_TEST_SKIP_NEXT_NPU = 0x7E
ERR_LENGTH = 0x0003

RESULT_BASE = int(os.environ.get("RESULT_BASE", "0x90020cc0"), 16)
RESULT_LEN = int(os.environ.get("RESULT_LEN", "0x100"), 16)
GOLDEN = 0x27084C4C

passed = 0
failed = 0
log = []


def check(name, ok, detail=""):
    global passed, failed
    stamp = time.strftime("%H:%M:%S")
    line = "  [%s] %-4s %-46s %s" % (stamp, "PASS" if ok else "FAIL", name, detail)
    print(line, flush=True)
    log.append(line)
    if ok:
        passed += 1
    else:
        failed += 1


link = RunnerLink(PORT, protocol=PROTO_MEASURE_V2)

print("=== phase 1: a normal RUN must produce the golden CRC ===", flush=True)
link.reset_runner()
blob = b"\x00" * 64
link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
link.load_model_chunk(0, blob)
link.load_model_end()
link.load_input(b"")

rc = link.run()
# The sequence GET_RESULT wants is the firmware's run counter from the
# RUN_COMPLETE header, not the protocol frame counter -- different namespaces.
seq_good = link.last_measurement.run_sequence
check("normal RUN completed", rc == 0, "rc=%d seq=%d" % (rc, seq_good))

_, _, _, crc_good = link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=seq_good)
check("golden CRC produced", crc_good == GOLDEN, "0x%08X" % crc_good)

if failed:
    print("\n### phase 1 failed - the hazard cannot be demonstrated ###", flush=True)
    link.close()
    sys.exit(1)

print("\n=== phase 2: arm skip-next, then RUN again in the SAME boot ===", flush=True)
try:
    f = link.request(CMD_TEST_SKIP_NEXT_NPU)
    check("CMD_TEST_SKIP_NEXT_NPU accepted (test image)", True, "cmd=0x%02X" % f.command)
except Nack as exc:
    check("CMD_TEST_SKIP_NEXT_NPU accepted (test image)", False,
          "%s -- is this the TEST_HOOKS image?" % exc)
    link.close()
    sys.exit(1)

link.load_input(b"")
try:
    rc_bad = link.run()
    seq_bad = link.last_measurement.run_sequence
    flags_bad = link.last_measurement.valid_flags
except Exception as exc:
    rc_bad, seq_bad, flags_bad = -1, seq_good + 1, 0
    print("     run() raised: %r" % exc, flush=True)
check("skipped RUN reports failure", rc_bad != 0, "rc=0x%08X seq=%d" % (rc_bad & 0xFFFFFFFF, seq_bad))
check("required valid_flags NOT satisfied", (flags_bad & RUN_VALID_REQUIRED_MASK) != RUN_VALID_REQUIRED_MASK, "flags=0x%02X" % flags_bad)
check("skipped RUN sequence advanced", seq_bad != seq_good, "%d -> %d" % (seq_good, seq_bad))

print("\n=== phase 3: the stale hazard itself ===", flush=True)
try:
    _, _, _, crc_bad = link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=seq_bad)
    check("GET_RESULT(N+1) refused", False,
          "returned 0x%08X -- STALE LEAK" % crc_bad)
    check("golden CRC not reused", crc_bad != GOLDEN, "0x%08X" % crc_bad)
except Nack as exc:
    check("GET_RESULT(N+1) refused with RESULT_NOT_VALID",
          exc.code == ERR_RESULT_NOT_VALID, "code=0x%04X" % exc.code)
    check("golden CRC NOT reused after skip", True, "no payload returned at all")

print("\n=== phase 4: stale sequence and short form ===", flush=True)
try:
    link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=seq_good)
    check("GET_RESULT(old N) refused", False, "accepted a superseded sequence")
except Nack as exc:
    check("GET_RESULT(old N) refused", exc.code == ERR_RESULT_NOT_VALID,
          "code=0x%04X" % exc.code)

link._seq = (link._seq + 1) & 0xFFFFFFFF
link.send_raw(build_frame(CMD_GET_RESULT, link._seq,
                          struct.pack("<II", RESULT_BASE, RESULT_LEN)))
try:
    fr = link.read_frame(5.0)
    if fr.command == 0xFF:
        check("8-byte GET_RESULT rejected with ERR_LENGTH", fr.flags == ERR_LENGTH,
              "code=0x%04X" % fr.flags)
    else:
        check("8-byte GET_RESULT rejected with ERR_LENGTH", False,
              "got cmd 0x%02X instead of a NACK" % fr.command)
except ProtocolError as exc:
    check("8-byte GET_RESULT rejected with ERR_LENGTH", False, str(exc))

print("\n=== SUMMARY ===", flush=True)
print("passed: %d   failed: %d" % (passed, failed), flush=True)
print("\nsequences: good=%d  skipped=%d  (no reboot between them)" % (seq_good, seq_bad), flush=True)
link.close()
sys.exit(1 if failed else 0)
