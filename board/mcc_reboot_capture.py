"""Issue MCC REBOOT and record everything the MCC console prints for --secs."""
import serial, sys, time
P="/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
out=sys.argv[1]; secs=float(sys.argv[2]) if len(sys.argv)>2 else 90.0
s=serial.Serial(P,115200,timeout=0.5)
s.reset_input_buffer(); s.write(b"REBOOT\r"); s.flush()
t0=time.time(); buf=bytearray()
while time.time()-t0 < secs:
    c=s.read(4096)
    if c: buf+=c
s.close(); open(out,"wb").write(bytes(buf))
print(f"mcc boot log: {len(buf)} bytes -> {out}")
