"""Read-only probe of SCC CFG_REG0 through the MCC DEBUG console.

Control group: the board has completed a verbose-mode boot that printed
"Clearing SCC CPUWAIT", so CFG_REG0 bit[1] is expected to read 0.
No write commands are issued.
"""

import time

import serial

MCC = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"

# LAR port 1 reaches the high-latency peripheral window that holds the SCC.
READS = [
    ("CFG_REG0 secure     0x5930_0000", "0X010059300000"),
    ("CFG_REG0 non-secure 0x4930_0000", "0X010049300000"),
    ("SCC_AID             0x5930_0FF8", "0X010059300FF8"),
    ("SCC_ID              0x5930_0FFC", "0X010059300FFC"),
]


def ts():
    return time.strftime("%H:%M:%S")


def send(ser, line, wait=1.5):
    ser.write(line.encode() + b"\r")
    ser.flush()
    time.sleep(wait)
    return ser.read(8192)


ser = serial.Serial(
    MCC, 115200, timeout=1, write_timeout=2,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False,
)
ser.reset_input_buffer()

print("[%s] probing prompt..." % ts(), flush=True)
resp = send(ser, "")
print("[%s] %s" % (ts(), repr(resp) if resp else "NONE"), flush=True)

if not resp or b"Cmd>" not in resp:
    ser.close()
    raise SystemExit("No Cmd> prompt - aborting")

print("\n[%s] entering DEBUG mode..." % ts(), flush=True)
resp = send(ser, "DEBUG", 2)
print("[%s] %s" % (ts(), repr(resp) if resp else "NONE"), flush=True)

if b"Debug>" not in (resp or b""):
    print("[%s] DEBUG prompt not seen - trying reads anyway" % ts(), flush=True)

print("", flush=True)
for name, addr in READS:
    out = send(ser, "R " + addr, 2)
    text = out.decode("ascii", errors="replace").replace("\r", "").strip() if out else "NO RESPONSE"
    print("[%s] %s" % (ts(), name), flush=True)
    print("        R %s -> %s" % (addr, text), flush=True)

print("\n[%s] leaving DEBUG mode..." % ts(), flush=True)
resp = send(ser, "EXIT", 2)
print("[%s] %s" % (ts(), repr(resp) if resp else "NONE"), flush=True)

ser.close()
