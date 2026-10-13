"""Open the app UART first, then REBOOT via MCC; record the app UART until the post-inference tensor dump is
complete (marker seen, then QUIET seconds of silence) or SECS elapse.
Usage: python3 mlek_app_capture.py <out.raw> <mcc_boot.log> [secs]"""
import serial, subprocess, sys, time, pathlib
APP = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
MARK, QUIET = b"output tensors post inference", 15.0
out, mcc_log = sys.argv[1], sys.argv[2]; secs = float(sys.argv[3]) if len(sys.argv) > 3 else 1200.0
s = serial.Serial(APP, 115200, timeout=0.5); s.reset_input_buffer()
t_open = time.time()
reboot = subprocess.Popen([sys.executable, str(pathlib.Path(__file__).with_name("mcc_reboot_capture.py")), mcc_log, "150"])
t_reboot = time.time(); assert t_open < t_reboot
buf = bytearray(); t0 = time.time(); last = t0
while time.time() - t0 < secs:
    c = s.read(65536)
    if c:
        buf += c; last = time.time()
    elif MARK in buf and time.time() - last > QUIET:
        break
s.close(); reboot.wait(); open(out, "wb").write(bytes(buf))
print(f"app uart: {len(buf)} bytes -> {out}; marker {'seen' if MARK in buf else 'NOT seen'}; listener opened before REBOOT")
sys.exit(0 if MARK in buf else 1)
