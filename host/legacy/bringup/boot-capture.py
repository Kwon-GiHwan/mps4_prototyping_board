import serial, time, threading, os, sys

LOG_DIR = '/home/gihwan/mps4/boot-capture-logs'
os.makedirs(LOG_DIR, exist_ok=True)

BASE = '/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0'
LABELS = {0: 'MCC', 1: 'FPGA_UART0_Selftest', 2: 'FPGA_UART1', 3: 'FPGA_UART2'}
DURATION = 120

def capture_port(idx):
    port_path = f'{BASE}{idx}-port0'
    label = LABELS[idx]
    log_file = os.path.join(LOG_DIR, f'if0{idx}_{label}.log')
    ts_file = os.path.join(LOG_DIR, f'if0{idx}_{label}_ts.log')
    
    try:
        ser = serial.Serial(
            port_path, 115200, timeout=1,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False
        )
        ser.reset_input_buffer()
        print(f'[{time.strftime("%H:%M:%S")}] if0{idx} ({label}) OPEN - listening...', flush=True)
    except Exception as e:
        print(f'[{time.strftime("%H:%M:%S")}] if0{idx} ({label}) OPEN FAILED: {e}', flush=True)
        return

    start = time.time()
    total_bytes = 0
    
    with open(log_file, 'wb') as raw, open(ts_file, 'w') as ts:
        while time.time() - start < DURATION:
            data = ser.read(256)
            if data:
                now = time.time()
                elapsed = now - start
                total_bytes += len(data)
                raw.write(data)
                raw.flush()
                ts.write(f'[{elapsed:7.3f}s] {len(data)} bytes: {repr(data)}\n')
                ts.flush()
                printable = data.decode('ascii', errors='replace').rstrip()
                print(f'[{time.strftime("%H:%M:%S")}] if0{idx}: {repr(data[:80])}', flush=True)
    
    ser.close()
    print(f'[{time.strftime("%H:%M:%S")}] if0{idx} ({label}) DONE - {total_bytes} bytes total', flush=True)

print(f'=== Boot Capture Start: {time.strftime("%Y-%m-%d %H:%M:%S")} ===', flush=True)
print(f'Duration: {DURATION}s | Settings: 115200 8N1 no-flow-control', flush=True)
print(f'Logs: {LOG_DIR}/', flush=True)
print(f'>>> Press PBON short NOW to boot <<<', flush=True)
print(flush=True)

threads = []
for i in range(4):
    t = threading.Thread(target=capture_port, args=(i,), daemon=True)
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print(f'\n=== Boot Capture End: {time.strftime("%Y-%m-%d %H:%M:%S")} ===', flush=True)

# Summary
print('\n=== SUMMARY ===', flush=True)
for i in range(4):
    label = LABELS[i]
    log_file = os.path.join(LOG_DIR, f'if0{i}_{label}.log')
    size = os.path.getsize(log_file) if os.path.exists(log_file) else 0
    status = f'{size} bytes' if size > 0 else 'SILENT (0 bytes)'
    print(f'if0{i} ({label}): {status}', flush=True)
