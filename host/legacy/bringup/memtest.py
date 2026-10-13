"""Run Selftest test 7 (MEMORY_TEST) alone, capturing Serial Port 0 and 1.

MEMORY_TEST is destructive over the whole DDR window and mem_test_finish()
ends in while(1), so this is a one-shot run: the CLI does not return.
Serial Port 1 uses LF as its line ending per AN 109762 section 6.
"""

import os
import threading
import time

import serial

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"
LOG_DIR = "/home/gihwan/mps4/boot-capture-logs/gcc-memtest7"
MAX_SECONDS = 900

os.makedirs(LOG_DIR, exist_ok=True)

captured = {0: b"", 1: b""}
timeline = {0: [], 1: []}
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
            timeline[idx].append("[%8.3fs] %s" % (time.time() - start_time, repr(data)))
            text = data.decode("ascii", errors="replace")
            for line in text.replace("\r", "").split("\n"):
                if line.strip():
                    print("[%s] if0%d| %s" % (ts(), idx, line), flush=True)


ports = {i: open_port(i) for i in (0, 1)}
for ser in ports.values():
    ser.reset_input_buffer()
print("[%s] if00 (MCC) and if01 (Selftest) OPEN" % ts(), flush=True)

threads = []
for i, ser in ports.items():
    t = threading.Thread(target=reader, args=(i, ser), daemon=True)
    threads.append(t)
    t.start()

sel = ports[1]

# Validate the input path with a harmless command first. Serial Port 1 uses LF.
print("\n[%s] === sending '-help' to validate input path ===" % ts(), flush=True)
sel.write(b"-help\n")
sel.flush()
time.sleep(4)

if not captured[1]:
    print("[%s] WARNING: no echo from Selftest CLI" % ts(), flush=True)
else:
    print("[%s] input path OK (%d bytes)" % (ts(), len(captured[1])), flush=True)

print("\n[%s] === sending '7' (MEMORY_TEST) ===" % ts(), flush=True)
print("[%s] destructive over 0x60000000-0xDFFFFFFF, one-shot" % ts(), flush=True)
mark = len(captured[1])
sel.write(b"7\n")
sel.flush()

# Run until the test announces completion or the cap is reached.
deadline = start_time + MAX_SECONDS
finished = False
while time.time() < deadline:
    time.sleep(2)
    if b"Please reboot the board." in captured[1]:
        finished = True
        print("\n[%s] test reported completion" % ts(), flush=True)
        time.sleep(2)
        break

stop.set()
for t in threads:
    t.join(timeout=3)
for ser in ports.values():
    ser.close()

body = captured[1][mark:]
print("\n=== SUMMARY ===", flush=True)
print("if00 (MCC):      %d bytes" % len(captured[0]), flush=True)
print("if01 (Selftest): %d bytes total, %d bytes after '7'" % (len(captured[1]), len(body)), flush=True)
print("completed:       %s" % ("YES" if finished else "NO - hit %ds cap" % MAX_SECONDS), flush=True)

if b"Memory test: PASSED" in captured[1]:
    print("RESULT: PASSED", flush=True)
elif b"Memory test: FAILED" in captured[1]:
    print("RESULT: FAILED", flush=True)
else:
    print("RESULT: no verdict line - test did not finish", flush=True)

banks = [l for l in body.decode("ascii", errors="replace").replace("\r", "").split("\n") if "Bank:" in l or "Memory Test:" in l]
if banks:
    print("\n--- bank progress ---", flush=True)
    for line in banks:
        print("  " + line.strip(), flush=True)

for i in (0, 1):
    with open(os.path.join(LOG_DIR, "if0%d.raw" % i), "wb") as f:
        f.write(captured[i])
    with open(os.path.join(LOG_DIR, "if0%d.timeline" % i), "w") as f:
        f.write("\n".join(timeline[i]))
print("\nLogs: %s/" % LOG_DIR, flush=True)
