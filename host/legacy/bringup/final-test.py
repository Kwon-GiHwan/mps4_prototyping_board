"""FI101 AN 109762 section 9.1 recovery procedure.

Captures all four serial ports from before the reboot, and issues REBOOT on the
MCC console through the same handle that captures Serial Port 0, so the port is
never opened twice.
"""

import os
import threading
import time

import serial

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"
LOG_DIR = "/home/gihwan/mps4/boot-capture-logs/official-ti3-final"
CAPTURE_SECONDS = 120

LABELS = {
    0: "if00_SerialPort0_MCC",
    1: "if01_SerialPort1_FPGA_UART0_Selftest",
    2: "if02_SerialPort2_FPGA_UART1",
    3: "if03_SerialPort3_FPGA_UART2",
}

os.makedirs(LOG_DIR, exist_ok=True)

captured = {i: b"" for i in range(4)}
timeline = {i: [] for i in range(4)}
stop = threading.Event()
start_time = None


def ts():
    return time.strftime("%H:%M:%S")


def open_port(idx):
    return serial.Serial(
        BASE + "%d-port0" % idx,
        115200,
        timeout=1,
        write_timeout=2,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )


def reader(idx, ser):
    while not stop.is_set():
        try:
            data = ser.read(256)
        except Exception as e:
            print("[%s] %s read error: %s" % (ts(), LABELS[idx], e), flush=True)
            return
        if data:
            captured[idx] += data
            elapsed = time.time() - start_time
            timeline[idx].append("[%8.3fs] %s" % (elapsed, repr(data)))
            print("[%s] if0%d: %s" % (ts(), idx, repr(data[:110])), flush=True)


print("=== FI101 AN 109762 OFFICIAL CONFIG: UARTMODE 0 / TOTALIMAGES 3 (with DDR.BIN) ===", flush=True)
print("Config untouched (UARTMODE 0, official SHA-256 match)", flush=True)
print("115200 8N1, no flow control | capture %ds" % CAPTURE_SECONDS, flush=True)
print("", flush=True)

ports = {}
for i in range(4):
    try:
        ports[i] = open_port(i)
        ports[i].reset_input_buffer()
        print("[%s] %s OPEN" % (ts(), LABELS[i]), flush=True)
    except Exception as e:
        print("[%s] %s OPEN FAILED: %s" % (ts(), LABELS[i], e), flush=True)

if 0 not in ports:
    raise SystemExit("Serial Port 0 (MCC) unavailable - aborting")

mcc = ports[0]

# Confirm the MCC prompt before doing anything. Serial Port 0 uses CR.
print("", flush=True)
print("[%s] Probing MCC prompt..." % ts(), flush=True)
mcc.write(b"\r")
mcc.flush()
time.sleep(1.5)
probe = mcc.read(4096)
print("[%s] probe response: %s" % (ts(), repr(probe) if probe else "NONE"), flush=True)

if not probe or b"Cmd>" not in probe:
    print("[%s] ABORT: no Cmd> prompt. Board may not be in Standby." % ts(), flush=True)
    for p in ports.values():
        p.close()
    raise SystemExit(1)

print("[%s] Cmd> confirmed." % ts(), flush=True)

# Start capture on every port, then issue REBOOT through the same MCC handle.
start_time = time.time()
threads = []
for i, ser in ports.items():
    t = threading.Thread(target=reader, args=(i, ser), daemon=True)
    threads.append(t)
    t.start()

time.sleep(0.5)
print("", flush=True)
print("[%s] === Sending REBOOT ===" % ts(), flush=True)
mcc.write(b"REBOOT\r")
mcc.flush()

deadline = start_time + CAPTURE_SECONDS
while time.time() < deadline:
    time.sleep(2)

stop.set()
for t in threads:
    t.join(timeout=3)
for p in ports.values():
    p.close()

print("", flush=True)
print("=== SUMMARY ===", flush=True)
for i in range(4):
    size = len(captured[i])
    print("%s: %s" % (LABELS[i], "%d bytes" % size if size else "SILENT"), flush=True)

selftest = captured.get(1, b"")
print("", flush=True)
if b"Selftest>" in selftest:
    print("RESULT: Selftest> prompt FOUND on if01", flush=True)
elif selftest:
    print("RESULT: if01 produced %d bytes but no Selftest> prompt" % len(selftest), flush=True)
else:
    print("RESULT: if01 SILENT - no Selftest output", flush=True)

for i in range(4):
    with open(os.path.join(LOG_DIR, "%s.raw" % LABELS[i]), "wb") as f:
        f.write(captured[i])
    with open(os.path.join(LOG_DIR, "%s.timeline" % LABELS[i]), "w") as f:
        f.write("\n".join(timeline[i]))
print("\nLogs: %s/" % LOG_DIR, flush=True)
