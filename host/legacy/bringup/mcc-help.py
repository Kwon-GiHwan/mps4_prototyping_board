import serial, time
BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
ser = serial.Serial(BASE, 115200, timeout=1, write_timeout=2,
    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
ser.reset_input_buffer()
ser.write(b"\r"); ser.flush(); time.sleep(1); ser.read(4096)
ser.write(b"HELP\r"); ser.flush(); time.sleep(3)
out = ser.read(16384)
print(out.decode("ascii", errors="replace"))
ser.close()
