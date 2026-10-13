#!/bin/sh
# After restore.sh: REBOOT (card still presented, unmounted) -> boot markers -> PING the restored
# runner -> USB_OFF (only now: after the reboot, with nothing mounted) -> confirm the card is gone.
set -eu
cd /home/gihwan/evsweep
EV=/home/gihwan/evsweep/evidence/postflight; mkdir -p "$EV"
findmnt | grep -q sdb && { echo "FAIL: card is mounted -- not rebooting, not USB_OFF"; exit 1; }
python3 mcc_reboot_capture.py "$EV/mcc_boot.log" 150
strings "$EV/mcc_boot.log" | grep -E "Image loaded|DDR memory test|CPUWAIT"
strings "$EV/mcc_boot.log" | grep -q "Clearing SCC CPUWAIT" || { echo "FAIL: CPUWAIT not released"; exit 1; }
sleep 3
python3 - <<'PY' | tee "$EV/ping.txt"
import sys; sys.path.insert(0, "/home/gihwan/evsweep/host/lib")
from runner_proto import RunnerLink, PROTOCOLS
P = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
for proto in PROTOCOLS:
    l = RunnerLink(P, protocol=proto)
    try:
        c = l.ping(); print(f"[{proto}] PING -> {c}"); break
    except Exception as e:
        print(f"[{proto}] no: {type(e).__name__}")
    finally:
        l.close()
PY
python3 mcc.py USB_OFF 4 | tail -2
sleep 3
ls /dev/sdb1 2>/dev/null && { echo "WARN: /dev/sdb1 still present after USB_OFF"; exit 2; } || echo "POSTFLIGHT DONE: card withdrawn, board on restored image"
