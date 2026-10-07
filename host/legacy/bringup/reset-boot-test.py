import serial, time, threading, os

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"
LOG_DIR = "/home/gihwan/mps4/boot-capture-logs/uartmode2"
os.makedirs(LOG_DIR, exist_ok=True)

LABELS = {0: "if00", 1: "if01", 2: "if02", 3: "if03"}
capture_data = {i: b"" for i in range(4)}
capture_logs = {i: [] for i in range(4)}
stop_event = threading.Event()


def ts():
    return time.strftime("%H:%M:%S")


def capture_port(idx):
    port_path = BASE + "%d-port0" % idx
    label = LABELS[idx]
    try:
        ser = serial.Serial(
            port_path, 115200, timeout=1,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )
        ser.reset_input_buffer()
        print("[%s] %s OPEN" % (ts(), label), flush=True)
    except Exception as e:
        print("[%s] %s OPEN FAILED: %s" % (ts(), label, e), flush=True)
        return

    while not stop_event.is_set():
        data = ser.read(256)
        if data:
            elapsed = time.time() - start_time
            capture_data[idx] += data
            entry = "[%7.3fs] %s: %s" % (elapsed, label, repr(data[:120]))
            capture_logs[idx].append(entry)
            print("[%s] %s: %s" % (ts(), label, repr(data[:120])), flush=True)
    ser.close()


# Phase 1: start all captures
print("=== UARTMODE 2 Boot + RESET Test ===", flush=True)
print(">>> Press PBON short NOW to boot <<<", flush=True)
print("", flush=True)

start_time = time.time()
threads = []
for i in range(4):
    t = threading.Thread(target=capture_port, args=(i,), daemon=True)
    threads.append(t)
    t.start()

# Phase 2: wait for MCC boot to complete (look for image loading on any port)
print("[%s] Waiting up to 90s for MCC boot log..." % ts(), flush=True)
boot_detected = False
boot_deadline = time.time() + 90

while time.time() < boot_deadline:
    time.sleep(2)
    for i in range(4):
        if b"Image loaded" in capture_data[i] or b"FPGA configuration complete" in capture_data[i]:
            boot_detected = True
            break
    if boot_detected:
        break

if not boot_detected:
    print("[%s] WARNING: MCC boot log not detected after 90s" % ts(), flush=True)
    print("[%s] Proceeding anyway..." % ts(), flush=True)
else:
    print("[%s] MCC boot detected. Waiting 10s for CPU init..." % ts(), flush=True)
    time.sleep(10)

# Phase 3: probe MCC CLI on if00 and if01
print("", flush=True)
print("[%s] === Probing MCC CLI ===" % ts(), flush=True)
mcc_port = None

for probe_idx in [0, 1]:
    port_path = BASE + "%d-port0" % probe_idx
    label = LABELS[probe_idx]
    try:
        probe = serial.Serial(
            port_path, 115200, timeout=1,
            write_timeout=1, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )
        probe.reset_input_buffer()
        probe.write(b"\r")
        probe.flush()
        time.sleep(1)
        resp = probe.read(4096)
        print("[%s] %s CR probe: %s" % (ts(), label, repr(resp) if resp else "NONE"), flush=True)

        if resp and b"Cmd>" in resp:
            print("[%s] MCC CLI found on %s!" % (ts(), label), flush=True)
            mcc_port = probe
            mcc_port_idx = probe_idx
            break

        probe.write(b"HELP\r")
        probe.flush()
        time.sleep(1)
        resp2 = probe.read(4096)
        print("[%s] %s HELP probe: %s" % (ts(), label, repr(resp2[:200]) if resp2 else "NONE"), flush=True)

        if resp2 and (b"Cmd>" in resp2 or b"HELP" in resp2):
            print("[%s] MCC CLI found on %s!" % (ts(), label), flush=True)
            mcc_port = probe
            mcc_port_idx = probe_idx
            break

        probe.close()
    except Exception as e:
        print("[%s] %s probe error: %s" % (ts(), label, e), flush=True)

if mcc_port is None:
    print("[%s] MCC CLI NOT found on if00 or if01 in RUN state" % ts(), flush=True)
    print("[%s] RESET_ON/RESET_OFF cannot be performed" % ts(), flush=True)
else:
    # Phase 4: RESET_ON -> RESET_OFF
    print("", flush=True)
    print("[%s] === Sending RESET_ON ===" % ts(), flush=True)
    mcc_port.write(b"RESET_ON\r")
    mcc_port.flush()
    time.sleep(1)
    resp_on = mcc_port.read(4096)
    print("[%s] RESET_ON response: %s" % (ts(), repr(resp_on) if resp_on else "NONE"), flush=True)

    print("[%s] === Sending RESET_OFF ===" % ts(), flush=True)
    mcc_port.write(b"RESET_OFF\r")
    mcc_port.flush()
    time.sleep(1)
    resp_off = mcc_port.read(4096)
    print("[%s] RESET_OFF response: %s" % (ts(), repr(resp_off) if resp_off else "NONE"), flush=True)

    # Phase 5: wait 30s for Selftest output
    print("[%s] Waiting 30s for Selftest output..." % ts(), flush=True)
    time.sleep(30)
    mcc_port.close()

# Stop captures
stop_event.set()
for t in threads:
    t.join(timeout=3)

# Summary
print("", flush=True)
print("=== SUMMARY ===", flush=True)
for i in range(4):
    size = len(capture_data[i])
    status = "%d bytes" % size if size > 0 else "SILENT"
    print("%s: %s" % (LABELS[i], status), flush=True)

# Save logs
for i in range(4):
    with open(os.path.join(LOG_DIR, "%s_raw.log" % LABELS[i]), "wb") as f:
        f.write(capture_data[i])
    with open(os.path.join(LOG_DIR, "%s_ts.log" % LABELS[i]), "w") as f:
        f.write("\n".join(capture_logs[i]))
print("\nLogs saved to %s/" % LOG_DIR, flush=True)
