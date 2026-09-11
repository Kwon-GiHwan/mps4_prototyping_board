"""Does RESET_ON invalidate DDR?

Sequence: full REBOOT (re-initialises DDR) -> round trip with no reset
-> RESET_ON/OFF -> round trip again. If the first succeeds and the second
fails, RESET_ON is destroying DDR state.
"""

import os
import time

from mcc_harness import STAGING, Harness

PW = os.environ["MPS4_SUDO_PW"]
PATTERN = b"DDRSTATE12345678"  # 16 bytes

h = Harness(PW)

print("=== full REBOOT to re-initialise DDR ===", flush=True)
out = h.mcc.command("REBOOT", wait=3.0)
deadline = time.time() + 150
booted = False
tail = ""
while time.time() < deadline:
    chunk = h.mcc.command("", wait=3.0)
    tail += chunk
    if "Cmd>" in chunk and "CPUWAIT" in tail:
        booted = True
        break
for line in tail.replace("\r", "").split("\n"):
    if any(k in line for k in ("SPD EEPROM", "DDR memory test", "Clearing SCC CPUWAIT")):
        print("   %s" % line.strip(), flush=True)
print("   boot complete: %s" % booted, flush=True)
time.sleep(3)

print("\n=== trip 1: immediately after boot, NO reset ===", flush=True)
h.write_memory(STAGING, PATTERN, name="DS_1W.BIN")
got1 = h.read_memory(STAGING, len(PATTERN), name="DS_1R.BIN")
print("   got = %r" % got1, flush=True)
print("   %s" % ("IDENTICAL" if got1 == PATTERN else "DIFFERENT"), flush=True)

print("\n=== trip 2: after RESET_ON / RESET_OFF ===", flush=True)
print("   RESET_ON  -> %s" % h.reset_on().replace("\r", " ").strip()[:60], flush=True)
print("   RESET_OFF -> %s" % h.reset_off().replace("\r", " ").strip()[:60], flush=True)
time.sleep(3)
h.write_memory(STAGING, PATTERN, name="DS_2W.BIN")
got2 = h.read_memory(STAGING, len(PATTERN), name="DS_2R.BIN")
print("   got = %r" % got2, flush=True)
print("   %s" % ("IDENTICAL" if got2 == PATTERN else "DIFFERENT"), flush=True)

print("\n=== VERDICT ===", flush=True)
if got1 == PATTERN and got2 != PATTERN:
    print("RESET_ON/OFF destroys DDR usability - must not wrap writes in v0", flush=True)
elif got1 == PATTERN and got2 == PATTERN:
    print("both fine - RESET_ON is safe", flush=True)
else:
    print("trip 1 already failed - cause is elsewhere, not RESET_ON", flush=True)
h.close()
