import serial, time
BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"

def probe(idx, cmd, ending):
    try:
        s = serial.Serial(BASE + "%d-port0" % idx, 115200, timeout=1, write_timeout=2,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
        s.reset_input_buffer()
        s.write(cmd + ending); s.flush(); time.sleep(2)
        out = s.read(8192)
        s.close()
        return out
    except Exception as e:
        return b"ERROR: " + str(e).encode()

print("if00 (MCC, CR):     ", repr(probe(0, b"", b"\r"))[:200])
print("if01 (Selftest, LF):", repr(probe(1, b"", b"\n"))[:300])
