import serial, time

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"

mcc = serial.Serial(BASE + "0-port0", 115200, timeout=2,
    write_timeout=1, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
mcc.reset_input_buffer()

mcc.write(b"USB_OFF\r")
mcc.flush()
time.sleep(2)
resp = mcc.read(4096)
print("USB_OFF response: %s" % (repr(resp) if resp else "NONE"))
mcc.close()
