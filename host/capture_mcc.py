import argparse
import time
import serial
import sys

def main():
    parser = argparse.ArgumentParser(description="Capture MCC serial output")
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with serial.Serial(
        port=args.port,
        baudrate=115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.5,
        write_timeout=1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as ser:
        ser.reset_input_buffer()
        start = time.monotonic()
        total = 0

        print(f"Listening on {args.port} for {args.duration}s ...")
        print("Perform PBON operation NOW.")

        with open(args.output, "wb") as f:
            while time.monotonic() - start < args.duration:
                chunk = ser.read(4096)
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    ts = time.monotonic() - start
                    print(f"  [{ts:6.1f}s] +{len(chunk)} bytes (total {total})")
                    sys.stdout.flush()

        print(f"\nDone. {total} bytes captured -> {args.output}")
        if total > 0:
            with open(args.output, "rb") as f:
                data = f.read()
            print(f"Preview (first 500 bytes): {data[:500]!r}")
            try:
                print(f"As text: {data[:500].decode(errors=replace)}")
            except Exception:
                pass

if __name__ == "__main__":
    main()
