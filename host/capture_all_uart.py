import time, serial, threading, os, sys

BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B"
PORTS = {
    "MCC_if00": f"{BASE}-if00-port0",
    "FPGA_UART0_if01": f"{BASE}-if01-port0",
    "FPGA_UART1_if02": f"{BASE}-if02-port0",
    "FPGA_UART2_if03": f"{BASE}-if03-port0",
}
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 120
OUTDIR = os.path.expanduser("~/mps4/logs")
os.makedirs(OUTDIR, exist_ok=True)

def capture(name, dev_path):
    outfile = os.path.join(OUTDIR, f"boot-{name}.log")
    total = 0
    start = time.monotonic()

    with open(outfile, "wb") as f:
        while time.monotonic() - start < DURATION:
            try:
                ser = serial.Serial(
                    port=dev_path, baudrate=115200,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE, timeout=0.5,
                    xonxoff=False, rtscts=False, dsrdtr=False,
                )
                while time.monotonic() - start < DURATION:
                    chunk = ser.read(4096)
                    if chunk:
                        ts = time.monotonic() - start
                        f.write(f"[{ts:07.2f}] ".encode() + chunk + b"\n")
                        f.flush()
                        total += len(chunk)
                        print(f"  {name} [{ts:6.1f}s] +{len(chunk)}B (total {total})", flush=True)
                ser.close()
            except (serial.SerialException, OSError) as e:
                elapsed = time.monotonic() - start
                msg = f"  {name} [{elapsed:6.1f}s] PORT ERROR: {e} — retrying in 2s\n"
                print(msg, end="", flush=True)
                f.write(f"[{elapsed:07.2f}] ERROR: {e}\n".encode())
                time.sleep(2)

    print(f"  {name}: DONE — {total} bytes -> {outfile}", flush=True)

print(f"Capturing {len(PORTS)} ports for {DURATION}s ...")
print(">>> Press PBON NOW <<<")
print()

threads = []
for name, path in PORTS.items():
    t = threading.Thread(target=capture, args=(name, path), daemon=True)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print("\n=== SUMMARY ===")
for name in PORTS:
    path = os.path.join(OUTDIR, f"boot-{name}.log")
    size = os.path.getsize(path) if os.path.exists(path) else 0
    print(f"  {name}: {size} bytes")
    if size > 0:
        with open(path, "rb") as f:
            data = f.read()
        text = data.decode(errors="replace")
        # Show first 2000 chars
        print(text[:2000])
        if len(text) > 2000:
            print(f"  ... ({len(text) - 2000} more chars)")
        print()
