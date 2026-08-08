"""Runtime gate for runner v1. Stops at the first failure.

Functional verification only -- latency, PMU and stall numbers from this build
are NOT usable as performance data, because the legacy printf in
u85_Convolution.c runs inside the measured window.
"""

import os
import random
import struct
import sys
import time
import zlib

from runner_proto import (
    CMD_GET_RESULT,
    CMD_LOAD_MODEL_CHUNK,
    CMD_RUN,
    MAGIC,
    HEADER,
    Nack,
    ProtocolError,
    RunnerLink,
    STATE_NAMES,
    build_frame,
)

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"

# From THIS build's map, supplied by the caller -- never hardcoded in firmware.
RESULT_BASE = int(os.environ.get("RESULT_BASE", "0x90020cc0"), 16)
RESULT_LEN = int(os.environ.get("RESULT_LEN", "0x100"), 16)
EXPECT_CRC = 0x27084C4C

gate = 0
failed = False


def check(name, ok, detail=""):
    global gate, failed
    gate += 1
    status = "PASS" if ok else "FAIL"
    print("  [%2d] %-4s %-40s %s" % (gate, status, name, detail), flush=True)
    if not ok:
        failed = True
    return ok


def stop_if_failed():
    if failed:
        print("\n### GATE FAILED - STOPPING (per first-failure rule) ###", flush=True)
        link.close()
        sys.exit(1)


link = RunnerLink(PORT, protocol=os.environ.get("PROTO", "functional-v1"))


def result_of(last_run):
    """measure-v2 mandates the 12-byte GET_RESULT; v1 has no sequence to pass."""
    if link.protocol == "measure-v2":
        return link.get_result(RESULT_BASE, RESULT_LEN,
                               run_sequence=last_run.run_sequence)
    return link.get_result(RESULT_BASE, RESULT_LEN)


print("=== gate 1: runner responds ===", flush=True)
alive = False
for _ in range(5):
    try:
        c = link.ping()
        alive = True
        break
    except (ProtocolError, Nack):
        time.sleep(1)
check("runner answers PING", alive, "state=%s" % (STATE_NAMES.get(c.state) if alive else "-"))
stop_if_failed()

print("\n=== gate 2: PING x100 ===", flush=True)
ok = 0
for _ in range(100):
    try:
        link.ping()
        ok += 1
    except Exception:
        pass
check("100 consecutive PINGs", ok == 100, "%d/100" % ok)
stop_if_failed()

print("\n=== gates 3-6: malformed frame rejection ===", flush=True)
before = link.ping()

bad = struct.pack(HEADER, 0xDEADBEEF, 1, 0x01, 0, 999, 0) + b"\x00\x00\x00\x00"
link.send_raw(bad)
time.sleep(0.5)
after = link.ping()
check("bad MAGIC ignored (no response)", after.bad_magic > before.bad_magic,
      "bad_magic %d -> %d" % (before.bad_magic, after.bad_magic))

body = struct.pack(HEADER, MAGIC, 99, 0x01, 0, 1001, 0)
link.send_raw(body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF))
try:
    link.read_frame(3.0)
    got_ver = True
except ProtocolError:
    got_ver = False
after2 = link.ping()
check("bad VERSION rejected", after2.bad_version > after.bad_version,
      "bad_version %d -> %d" % (after.bad_version, after2.bad_version))

body = struct.pack(HEADER, MAGIC, 1, 0x01, 0, 1002, 0xFFFF)
link.send_raw(body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF))
time.sleep(0.5)
after3 = link.ping()
check("over-length rejected without waiting", after3.length_error > after2.length_error,
      "length_error %d -> %d" % (after2.length_error, after3.length_error))

body = struct.pack(HEADER, MAGIC, 1, 0x01, 0, 1003, 0)
link.send_raw(body + struct.pack("<I", 0x12345678))
time.sleep(0.5)
after4 = link.ping()
check("bad CRC rejected", after4.bad_crc > after3.bad_crc,
      "bad_crc %d -> %d" % (after3.bad_crc, after4.bad_crc))
stop_if_failed()

print("\n=== gate 8: state violation ===", flush=True)
try:
    link.request(CMD_RUN)
    check("RUN rejected while IDLE", False, "accepted")
except Nack as exc:
    check("RUN rejected while IDLE", exc.code == 5, str(exc))
stop_if_failed()

print("\n=== gates 9-10: model transfer ===", flush=True)
rng = random.Random(0xF1101)
blob = bytes(rng.randrange(256) for _ in range(4096))
blob_crc = zlib.crc32(blob) & 0xFFFFFFFF
total, staging_base, staging_max = link.load_model_begin(len(blob), blob_crc)
print("     staging_base=0x%08X staging_max=0x%X (from firmware)" % (staging_base, staging_max), flush=True)

small_ok = True
for length in (1, 3, 4, 15, 16, 17):
    piece = blob[:length]
    try:
        link.load_model_chunk(0, piece)
    except Exception as exc:
        small_ok = False
        print("     %d-byte chunk failed: %s" % (length, exc), flush=True)
check("1/3/4/15/16/17-byte chunks accepted", small_ok)

CHUNK = 1024
for off in range(0, len(blob), CHUNK):
    link.load_model_chunk(off, blob[off:off + CHUNK])
computed, expected, tot = link.load_model_end()
check("4 KiB transfer, whole-blob CRC matches", computed == expected == blob_crc,
      "computed 0x%08X expected 0x%08X" % (computed, expected))
stop_if_failed()

print("\n=== gate 11: staging boundary rejection ===", flush=True)
link.load_model_begin(16, 0)
try:
    link.load_model_chunk(staging_max, b"\x00" * 16)
    check("write at staging limit rejected", False, "accepted")
except Nack as exc:
    check("write at staging limit rejected", exc.code == 6, str(exc))
stop_if_failed()

print("\n=== gates 12-15: fixed inference ===", flush=True)
link.reset_runner()
blob2 = b"\x00" * 64
link.load_model_begin(len(blob2), zlib.crc32(blob2) & 0xFFFFFFFF)
link.load_model_chunk(0, blob2)
link.load_model_end()
link.load_input(b"")
rc = link.run()
check("RUN executed", rc == 0, "rc=%d" % rc)
r_rc, r_base, r_len, r_crc = result_of(link.last_measurement)
check("GET_RESULT returned %d bytes" % RESULT_LEN, r_len == RESULT_LEN,
      "base=0x%08X len=0x%X" % (r_base, r_len))
check("output CRC32 == 0x27084C4C", r_crc == EXPECT_CRC, "got 0x%08X" % r_crc)
stop_if_failed()

print("\n=== gates 16-17: RESET_RUNNER then re-run, no reboot ===", flush=True)
link.reset_runner()
st = link.ping()
check("state is IDLE after RESET_RUNNER", st.state == 1, STATE_NAMES.get(st.state, st.state))
link.load_model_begin(len(blob2), zlib.crc32(blob2) & 0xFFFFFFFF)
link.load_model_chunk(0, blob2)
link.load_model_end()
link.load_input(b"")
rc2 = link.run()
_, _, _, crc2 = result_of(link.last_measurement)
check("re-run reproduces CRC without reboot", rc2 == 0 and crc2 == EXPECT_CRC,
      "rc=%d crc=0x%08X" % (rc2, crc2))

final = link.ping()
print("\n=== firmware counters ===", flush=True)
print("  rx_bytes=%d tx_bytes=%d rx_overrun=%d" % (final.rx_bytes, final.tx_bytes, final.rx_overrun), flush=True)
print("  bad_magic=%d bad_version=%d bad_crc=%d length_err=%d seq_err=%d resync=%d"
      % (final.bad_magic, final.bad_version, final.bad_crc,
         final.length_error, final.sequence_error, final.parser_resync), flush=True)
print("  host-side resyncs=%d, legacy text lines captured=%d"
      % (link.resyncs, len(link.text_log)), flush=True)
for line in link.text_log[:5]:
    print("     legacy: %s" % line, flush=True)

print("\n=== RESULT ===", flush=True)
print("ALL GATES PASSED" if not failed else "FAILED", flush=True)
link.close()
sys.exit(1 if failed else 0)
