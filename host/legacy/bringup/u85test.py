"""Run a single Selftest test by number, capturing Serial Port 0 and 1.

Usage: u85test.py <test_number> <label> [timeout_seconds]

Only tests whose sections are proven to live outside external DDR should be
run while the DDR subsystem is unusable. Returns to the CLI on completion,
unlike MEMORY_TEST.
"""

import os
import sys
import threading
import time

import serial

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"

TEST_NUM = sys.argv[1]
LABEL = sys.argv[2]
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 120

LOG_DIR = "/home/gihwan/mps4/boot-capture-logs/u85-test%s" % TEST_NUM
os.makedirs(LOG_DIR, exist_ok=True)

captured = {0: b"", 1: b""}
stop = threading.Event()
start_time = time.time()


def ts():
    return time.strftime("%H:%M:%S")


def open_port(idx):
    return serial.Serial(
        BASE + "%d-port0" % idx, 115200, timeout=1, write_timeout=2,
        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False, rtscts=False, dsrdtr=False,
    )


def reader(idx, ser):
    while not stop.is_set():
        try:
            data = ser.read(256)
        except Exception as e:
            print("[%s] if0%d read error: %s" % (ts(), idx, e), flush=True)
            return
        if data:
            captured[idx] += data
            for line in data.decode("ascii", errors="replace").replace("\r", "").split("\n"):
                if line.strip():
                    print("[%s] if0%d| %s" % (ts(), idx, line), flush=True)


ports = {i: open_port(i) for i in (0, 1)}
for ser in ports.values():
    ser.reset_input_buffer()
print("[%s] if00 and if01 OPEN" % ts(), flush=True)

threads = []
for i, ser in ports.items():
    t = threading.Thread(target=reader, args=(i, ser), daemon=True)
    threads.append(t)
    t.start()

sel = ports[1]
time.sleep(1)

print("\n[%s] === running test %s : %s ===" % (ts(), TEST_NUM, LABEL), flush=True)
mark = len(captured[1])
sent_at = time.time()
# The GCC build drops back-to-back UART bytes, so pace the digits.
for _ch in TEST_NUM.encode():
    sel.write(bytes([_ch]))
    sel.flush()
    time.sleep(0.15)
sel.write(b"\n")
sel.flush()

# The CLI reprints "Selftest>" once the test returns.
finished = False
deadline = sent_at + LIMIT
while time.time() < deadline:
    time.sleep(1)
    tail = captured[1][mark:]
    if b"Selftest>" in tail:
        finished = True
        time.sleep(2)
        break

elapsed = time.time() - sent_at
stop.set()
for t in threads:
    t.join(timeout=3)
for ser in ports.values():
    ser.close()

body = captured[1][mark:].decode("ascii", errors="replace").replace("\r", "")

print("\n=== SUMMARY: test %s (%s) ===" % (TEST_NUM, LABEL), flush=True)
print("elapsed:   %.1fs" % elapsed, flush=True)
print("returned:  %s" % ("YES - CLI prompt came back" if finished else "NO - hung, hit %ds limit" % LIMIT), flush=True)
print("if00 MCC:  %d bytes" % len(captured[0]), flush=True)
print("if01:      %d bytes after command" % len(captured[1][mark:]), flush=True)

low = body.lower()
if "pass" in low and "fail" not in low.replace("total fail", ""):
    verdict = "PASS indicated"
elif "fail" in low.replace("total fail :    0", ""):
    verdict = "FAIL indicated"
else:
    verdict = "no explicit verdict"
print("verdict:   %s" % verdict, flush=True)

with open(os.path.join(LOG_DIR, "if01.raw"), "wb") as f:
    f.write(captured[1])
with open(os.path.join(LOG_DIR, "if00.raw"), "wb") as f:
    f.write(captured[0])
print("\nLogs: %s/" % LOG_DIR, flush=True)
