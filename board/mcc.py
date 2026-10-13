import serial, sys, time
P="/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
s=serial.Serial(P,115200,timeout=1,write_timeout=2)
def cmd(line, wait):
    s.reset_input_buffer(); s.write(line.encode()+b"\r"); s.flush(); time.sleep(wait)
    return s.read(200000).decode("ascii",errors="replace")
line=sys.argv[1]; wait=float(sys.argv[2]) if len(sys.argv)>2 else 3.0
print(cmd(line, wait)); s.close()
