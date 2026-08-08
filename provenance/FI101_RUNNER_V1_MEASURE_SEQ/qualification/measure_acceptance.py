"""Final acceptance for the MEASURE image.

Runs the promotion criteria in order: the nine gates (no result before the
first run, the test-only hook is genuinely absent at runtime, one ABI smoke
run), then ten consecutive runs each checked independently, then a reuse
check after RESET_RUNNER.

Error codes are asserted per state, never as "either code passes":

  IDLE          + GET_RESULT          -> exactly STATE(0x0005)
  RESULT_READY  + invalid result      -> exactly RESULT_NOT_VALID(0x000B)

GET_RESULT is only accepted in RESULT_READY, so from IDLE the state gate
legitimately fires first and STATE is the specified code. RESULT_NOT_VALID
belongs to the different case of an allowed state holding an invalid result,
which only the TEST_HOOKS image can produce -- see test_stale_demo.py. This
file must never accept 0x000B for the IDLE case, nor 0x0005 for the other.
"""

import os
import struct
import sys
import time
import zlib

from runner_proto import (
    CMD_GET_RESULT,
    NACK,
    PROTO_MEASURE_V2,
    RME_MAGIC,
    Nack,
    ProtocolError,
    RunnerLink,
    build_frame,
)

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
CMD_TEST_SKIP_NEXT_NPU = 0x7E
RESULT_BASE = int(os.environ.get("RESULT_BASE", "0x90020cc0"), 16)
RESULT_LEN = int(os.environ.get("RESULT_LEN", "0x100"), 16)
GOLDEN = 0x27084C4C
RUNS = 10

ERR_STATE = 0x0005
STATE_IDLE = 1
# send_nack() emits a fixed 4-byte body {request_command, runner_state, 0, 0}
# for every error code. A result region would be 16 bytes (rc, base, len, crc),
# so a 4-byte body is positive evidence that no region was read or returned.
NACK_PAYLOAD_LEN = 4
RESULT_PAYLOAD_LEN = 16

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-48s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    if ok:
        passed += 1
    else:
        failed += 1


def prime(link):
    """Bring the runner to INPUT_READY without touching the NPU."""
    link.reset_runner()
    blob = b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")


link = RunnerLink(PORT, protocol=PROTO_MEASURE_V2)

print("=== gate 1: GET_RESULT from IDLE -> exactly STATE(0x0005) ===", flush=True)
# Sent raw rather than through get_result() so the rejection frame itself can be
# inspected: Nack carries only the code, not the payload we must prove is empty.
st_before = link.ping()
link._seq = (link._seq + 1) & 0xFFFFFFFF
seq = link._seq
link.send_raw(build_frame(CMD_GET_RESULT, seq,
                          struct.pack("<III", RESULT_BASE, RESULT_LEN, 1)))
sub = []
try:
    fr = link.read_frame(5.0)
    sub.append(("frame is a NACK, not a result", fr.command == NACK,
                "cmd=0x%02X" % fr.command))
    sub.append(("code is exactly STATE(0x0005)", fr.flags == ERR_STATE,
                "code=0x%04X" % fr.flags))
    sub.append(("body is the 4-byte NACK form", len(fr.payload) == NACK_PAYLOAD_LEN,
                "payload=%dB (result would be %dB)"
                % (len(fr.payload), RESULT_PAYLOAD_LEN)))
    sub.append(("NACK reserved bytes are zero",
                len(fr.payload) == 4 and fr.payload[2] == 0 and fr.payload[3] == 0,
                "%r" % (bytes(fr.payload[2:4]),)))
    sub.append(("NACK echoes GET_RESULT as the request",
                len(fr.payload) >= 1 and fr.payload[0] == CMD_GET_RESULT,
                "orig=0x%02X" % (fr.payload[0] if fr.payload else -1)))
    sub.append(("NACK reports state IDLE", len(fr.payload) >= 2 and fr.payload[1] == STATE_IDLE,
                "state=%d" % (fr.payload[1] if len(fr.payload) >= 2 else -1)))
except ProtocolError as exc:
    sub.append(("frame is a NACK, not a result", False, str(exc)))
st_after = link.ping()
sub.append(("state stayed IDLE across the rejection",
            st_before.state == STATE_IDLE and st_after.state == STATE_IDLE,
            "%d -> %d" % (st_before.state, st_after.state)))
sub.append(("PING still answers afterwards", True, "state=%d" % st_after.state))
for n, ok, d in sub:
    print("       %-4s %-44s %s" % ("ok" if ok else "NO", n, d), flush=True)
check("IDLE GET_RESULT refused with STATE(0x0005)", all(s[1] for s in sub),
      "%d/%d sub-conditions" % (sum(1 for s in sub if s[1]), len(sub)))

print("\n=== gates 2-3: the test-only hook is absent at runtime ===", flush=True)
acked = False
try:
    f = link.request(CMD_TEST_SKIP_NEXT_NPU, timeout=4.0)
    acked = True
    check("0x7E did NOT get an ACK", False, "ACKed with 0x%02X -- STOP, wrong image" % f.command)
except Nack as exc:
    check("0x7E rejected with an explicit NACK", True,
          "code=0x%04X (%s)" % (exc.code, exc))
except ProtocolError:
    check("0x7E rejected with an explicit NACK", False,
          "only timed out -- absence shown, protocol handling not")

if acked:
    print("\n### the final image answers the test hook. Deployment must stop. ###", flush=True)
    link.close()
    sys.exit(1)

try:
    c = link.ping()
    check("PING still works after the rejection", True, "state=%d" % c.state)
except Exception as exc:
    check("PING still works after the rejection", False, repr(exc))

print("\n=== gates 4-9: single-RUN ABI smoke ===", flush=True)
prime(link)
before = link.late_frames
rc = link.run()
m = link.last_measurement
check("RUN rc == 0", rc == 0, "rc=%d" % rc)
check("measurement magic is RME1", True, "0x%08X" % RME_MAGIC)
check("required valid_flags satisfied", m.required_flags_ok(), "flags=0x%02X" % m.valid_flags)
check("host knows all 47 fields, no unparsed tail", m.trailing_words == 0,
      "trailing=%d" % m.trailing_words)
_, gb, gl, crc = link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=m.run_sequence)
check("golden CRC", crc == GOLDEN, "0x%08X at 0x%08X+0x%X" % (crc, gb, gl))
check("no late frames", link.late_frames == before, "late=%d" % link.late_frames)

print("\n--- gates: %d/%d ---" % (passed, passed + failed), flush=True)
if failed:
    print("\n### gates failed - not proceeding to the 10-run series ###", flush=True)
    link.close()
    sys.exit(1)

print("\n=== ten consecutive RUNs, each checked independently ===", flush=True)
prev_seq = m.run_sequence
seqs, crcs, bad = [], [], []
for i in range(RUNS):
    late_before = link.late_frames
    c_before = link.ping()
    prime(link)
    rc = link.run()
    mm = link.last_measurement
    _, _, _, c = link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=mm.run_sequence)
    c_after = link.ping()
    seqs.append(mm.run_sequence)
    crcs.append(c)
    d_ovr = c_after.rx_overrun - c_before.rx_overrun
    d_crc = c_after.bad_crc - c_before.bad_crc
    d_rsy = c_after.parser_resync - c_before.parser_resync
    d_seq = c_after.sequence_error - c_before.sequence_error
    problems = []
    if mm.run_sequence != prev_seq + 1:
        problems.append("seq %d -> %d" % (prev_seq, mm.run_sequence))
    if rc != 0:
        problems.append("rc=%d" % rc)
    if not mm.required_flags_ok():
        problems.append("flags=0x%02X" % mm.valid_flags)
    if mm.trailing_words != 0:
        problems.append("trailing=%d" % mm.trailing_words)
    if c != GOLDEN:
        problems.append("crc=0x%08X" % c)
    if link.late_frames != late_before:
        problems.append("late+%d" % (link.late_frames - late_before))
    for nm, d in (("rx_overrun", d_ovr), ("bad_crc", d_crc),
                  ("parser_resync", d_rsy), ("sequence_error", d_seq)):
        if d != 0:
            problems.append("%s+%d" % (nm, d))
    print("    run %2d: seq=%-3d rc=%d flags=0x%02X crc=0x%08X "
          "d[ovr=%d crc=%d rsy=%d seq=%d] %s"
          % (i + 1, mm.run_sequence, rc, mm.valid_flags, c,
             d_ovr, d_crc, d_rsy, d_seq,
             "OK" if not problems else "  <-- " + ", ".join(problems)), flush=True)
    if problems:
        bad.append((i + 1, problems))
    prev_seq = mm.run_sequence

check("10/10 runs clean", not bad, "%d problem run(s)" % len(bad))
check("sequences strictly +1", seqs == list(range(seqs[0], seqs[0] + RUNS)),
      "%d..%d" % (seqs[0], seqs[-1]))
check("golden CRC on every run", set(crcs) == {GOLDEN}, "distinct=%d" % len(set(crcs)))
check("late_frames == 0 overall", link.late_frames == 0, "late=%d" % link.late_frames)

print("\n=== reuse after RESET_RUNNER ===", flush=True)
link.reset_runner()
st = link.ping()
check("RESET_RUNNER returns to IDLE", st.state == STATE_IDLE, "state=%d" % st.state)
prime(link)
rc = link.run()
mr = link.last_measurement
_, _, _, cr = link.get_result(RESULT_BASE, RESULT_LEN, run_sequence=mr.run_sequence)
check("RUN after reset succeeds", rc == 0 and mr.required_flags_ok(),
      "rc=%d flags=0x%02X seq=%d" % (rc, mr.valid_flags, mr.run_sequence))
check("GET_RESULT after reset is golden", cr == GOLDEN, "0x%08X" % cr)

print("\n=== SUMMARY ===", flush=True)
print("passed: %d   failed: %d" % (passed, failed), flush=True)
link.close()
sys.exit(1 if failed else 0)
