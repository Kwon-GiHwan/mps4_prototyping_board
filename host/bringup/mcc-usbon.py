import serial, time

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"

def ts():
    return time.strftime("%H:%M:%S")

mcc = serial.Serial(BASE + "0-port0", 115200, timeout=2,
    write_timeout=1,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False, rtscts=False, dsrdtr=False)
mcc.reset_input_buffer()

# Send CR to get prompt
mcc.write(b"\r")
mcc.flush()
time.sleep(1)
resp = mcc.read(4096)
print("[%s] CR response: %s" % (ts(), repr(resp) if resp else "NONE"), flush=True)

# Send USB_ON
mcc.write(b"USB_ON\r")
mcc.flush()
time.sleep(3)
resp2 = mcc.read(4096)
print("[%s] USB_ON response: %s" % (ts(), repr(resp2) if resp2 else "NONE"), flush=True)

mcc.close()
