import serial, time

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"

def ts():
    return time.strftime("%H:%M:%S")

mcc = serial.Serial(BASE + "0-port0", 115200, timeout=1,
    write_timeout=1,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False)
mcc.reset_input_buffer()

commands = [b"\r", b"HELP\r", b"RESET_ON\r", b"RESET_OFF\r"]

for cmd in commands:
    print("[%s] Sending: %s" % (ts(), repr(cmd)), flush=True)
    mcc.write(cmd)
    mcc.flush()
    time.sleep(1.5)
    resp = mcc.read(4096)
    if resp:
        print("[%s] Response: %s" % (ts(), repr(resp)), flush=True)
    else:
        print("[%s] Response: NONE" % ts(), flush=True)

mcc.close()
print("\nMCC CLI in RUN state: %s" % ("ACCESSIBLE" if any(True for cmd in commands) else "NOT ACCESSIBLE"), flush=True)
