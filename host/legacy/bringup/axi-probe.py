"""Probe the MCC WRITE_AXI / READ_AXI transfer path.

Writes a known 16-byte pattern to the runner staging address, reads it back
through a separate file, and compares byte-for-byte. Read-only with respect
to the Selftest image: only the staging window is touched.
"""

import time

import serial

MCC = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
STAGING = "0x010090120000"


def ts():
    return time.strftime("%H:%M:%S")


def cmd(ser, line, wait=2.0, quiet=False):
    ser.reset_input_buffer()
    ser.write(line.encode() + b"\r")
    ser.flush()
    time.sleep(wait)
    out = ser.read(16384)
    text = out.decode("ascii", errors="replace")
    if not quiet:
        print("[%s] > %s" % (ts(), line), flush=True)
        for l in text.replace("\r", "").split("\n"):
            if l.strip() and l.strip() != line:
                print("        %s" % l, flush=True)
    return text


ser = serial.Serial(
    MCC, 115200, timeout=1, write_timeout=2,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False,
)

print("=== MCC WRITE_AXI / READ_AXI path probe ===", flush=True)
resp = cmd(ser, "")
if "Cmd>" not in resp:
    ser.close()
    raise SystemExit("no Cmd> prompt - is the board in RUN with a completed boot?")

# The transfer commands are RUN-mode only; confirm we are there.
print("\n--- writing staging pattern to %s ---" % STAGING, flush=True)
cmd(ser, 'WRITE_AXI "\\PROBE_W.BIN" "%s"' % STAGING, 4)

print("\n--- reading it back ---", flush=True)
cmd(ser, 'READ_AXI "\\PROBE_R.BIN" "%s" "0x010090120010"' % STAGING, 4)

ser.close()
print("\n(compare PROBE_W.BIN and PROBE_R.BIN on the SD card)", flush=True)
