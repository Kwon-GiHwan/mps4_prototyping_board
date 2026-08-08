"""Raw UART RX smoke test.

Exercises the polling RX path with GetLine() and the Selftest CLI parser out
of the picture entirely. Runs the same 4-byte exchange slowly and as a burst,
then reads the firmware's own counters so byte loss is measured rather than
inferred.
"""

import sys
import time

import serial

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"

PING_REQ = bytes([0x55, 0xAA, 0x01, 0xFE])
PING_RESP = bytes([0xAA, 0x55, 0x01, 0xFE])
STAT_REQ = bytes([0x55, 0xAA, 0x02, 0xFD])
STAT_RESP = bytes([0xAA, 0x55, 0x02, 0xFD])

ROUNDS = 100

ser = serial.Serial(
    PORT, 115200, timeout=0.5, write_timeout=2,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False,
)


def banner(limit=20.0):
    end = time.time() + limit
    buf = b""
    while time.time() < end:
        buf += ser.read(256)
        if b"RAWRX READY" in buf:
            return True
    return False


def exchange(gap):
    """Send the ping, return (ok, raw_response)."""
    ser.reset_input_buffer()
    for byte in PING_REQ:
        ser.write(bytes([byte]))
        ser.flush()
        if gap:
            time.sleep(gap)
    deadline = time.time() + 1.0
    got = b""
    while time.time() < deadline and len(got) < 4:
        got += ser.read(4 - len(got))
    return got == PING_RESP, got


def stats():
    ser.reset_input_buffer()
    ser.write(STAT_REQ)
    ser.flush()
    time.sleep(0.5)
    raw = ser.read(64)
    if len(raw) < 8 or raw[:4] != STAT_RESP:
        return None
    rx = (raw[4] << 8) | raw[5]
    over = (raw[6] << 8) | raw[7]
    return rx, over


# The banner is emitted at CPU start, before this script can open the port,
# so treat it as advisory and probe with an actual ping instead.
print("=== liveness probe ===", flush=True)
alive, first = exchange(0.005)
print("ping -> %s%s" % (first.hex() or "(nothing)", "  OK" if alive else "  MISMATCH"), flush=True)
if not alive:
    print("FAIL: raw RX firmware not responding to ping", flush=True)
    ser.close()
    sys.exit(1)

results = {}
for label, gap in (("slow (5ms/byte)", 0.005), ("burst (0ms)", 0.0)):
    ok_count = 0
    bad = []
    for i in range(ROUNDS):
        ok, got = exchange(gap)
        if ok:
            ok_count += 1
        elif len(bad) < 3:
            bad.append((i, got.hex()))
    results[label] = (ok_count, bad)
    print("\n%-18s %3d/%d correct responses" % (label, ok_count, ROUNDS), flush=True)
    for idx, hexs in bad:
        print("    round %d -> %s" % (idx, hexs or "(nothing)"), flush=True)

st = stats()
print("\n=== firmware counters ===", flush=True)
if st is None:
    print("stats command did not answer", flush=True)
else:
    rx, over = st
    print("bytes received (mod 65536): %d" % rx, flush=True)
    print("RX overruns (STATE.RXOR)  : %d" % over, flush=True)

print("\n=== VERDICT ===", flush=True)
slow_ok = results["slow (5ms/byte)"][0]
burst_ok = results["burst (0ms)"][0]
if slow_ok == ROUNDS and burst_ok == ROUNDS:
    print("RAW RX PASS - polling receive is sound at both pacings", flush=True)
    print("=> the CLI regression is isolated to GetLine/parser layer", flush=True)
elif slow_ok == ROUNDS and burst_ok < ROUNDS:
    print("RAW RX PARTIAL - slow ok, burst loses bytes", flush=True)
    print("=> hardware/driver RX cannot keep up; fix UART layer before runner", flush=True)
else:
    print("RAW RX FAIL - loss even when paced", flush=True)
    print("=> stop runner work; UART driver/clock/init needs fixing", flush=True)

ser.close()
