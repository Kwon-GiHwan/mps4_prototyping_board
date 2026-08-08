"""Fresh REBOOT via the MCC console. No SD access, so no password needed."""
import time
from mcc_harness import MccConsole

mcc = MccConsole()
mcc.command("REBOOT", wait=3.0)
seen = ""
deadline = time.time() + 150.0
while time.time() < deadline:
    seen += mcc.command("", wait=3.0)
    if "Clearing SCC CPUWAIT" in seen and "Cmd>" in seen:
        time.sleep(3)
        break
print("DDR self-test PASSED:", "DDR memory test at 0x70000000: PASSED" in seen)
print("CPUWAIT cleared    :", "Clearing SCC CPUWAIT" in seen)
mcc.close()
