import serial, time, threading

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"
LOG_DIR = "/home/gihwan/mps4/boot-capture-logs"

results = {"if01": b""}

def ts():
    return time.strftime("%H:%M:%S")

def capture_if01():
    port = BASE + "1-port0"
    ser = serial.Serial(port, 115200, timeout=1,
        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False, rtscts=False, dsrdtr=False)
    ser.reset_input_buffer()
    print("[%s] if01 (Selftest) OPEN - listening..." % ts(), flush=True)
    start = time.time()
    while time.time() - start < 30:
        data = ser.read(256)
        if data:
            results["if01"] += data
            print("[%s] if01: %s" % (ts(), repr(data[:200])), flush=True)
    ser.close()

t = threading.Thread(target=capture_if01, daemon=True)
t.start()
time.sleep(1)

mcc = serial.Serial(BASE + "0-port0", 115200, timeout=0.5,
    write_timeout=1,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False)
mcc.reset_input_buffer()
print("[%s] if00 (MCC) OPEN" % ts(), flush=True)

print("[%s] Sending RESET_ON..." % ts(), flush=True)
mcc.write(b"RESET_ON\r")
mcc.flush()
time.sleep(2)
resp1 = mcc.read(4096)
r1_str = repr(resp1) if resp1 else "NO RESPONSE"
print("[%s] if00 after RESET_ON: %s" % (ts(), r1_str), flush=True)

print("[%s] Sending RESET_OFF..." % ts(), flush=True)
mcc.write(b"RESET_OFF\r")
mcc.flush()
time.sleep(10)
resp2 = mcc.read(4096)
r2_str = repr(resp2) if resp2 else "NO RESPONSE"
print("[%s] if00 after RESET_OFF: %s" % (ts(), r2_str), flush=True)

time.sleep(5)
resp3 = mcc.read(4096)
if resp3:
    print("[%s] if00 additional: %s" % (ts(), repr(resp3)), flush=True)

mcc.close()
t.join(timeout=5)

print("\n=== SUMMARY ===", flush=True)
print("if00 RESET_ON response: %s" % r1_str, flush=True)
print("if00 RESET_OFF response: %s" % r2_str, flush=True)
print("if01 Selftest total: %d bytes" % len(results["if01"]), flush=True)
if results["if01"]:
    print("if01 data: %s" % repr(results["if01"][:500]), flush=True)
else:
    print("if01 Selftest: SILENT", flush=True)

with open(LOG_DIR + "/reset_test_if00.log", "w") as f:
    f.write("RESET_ON: %s\n" % repr(resp1))
    f.write("RESET_OFF: %s\n" % repr(resp2))
    if resp3:
        f.write("Additional: %s\n" % repr(resp3))
with open(LOG_DIR + "/reset_test_if01.log", "wb") as f:
    f.write(results["if01"])
