"""Step-by-step verification of the harness transfer path."""

import os

from mcc_harness import SD_MOUNT, STAGING, Harness, MccConsole, SdCard, _sudo

PW = os.environ["MPS4_SUDO_PW"]
PATTERN = b"STEPCHECK1234567"  # 16 bytes

h = Harness(PW)

print("step 1: stage file on SD via SdCard.put", flush=True)
with SdCard(h.mcc, PW) as sd:
    sd.put("STEP_W.BIN", PATTERN)
    listing = _sudo("ls -l %s/STEP_W.BIN; xxd %s/STEP_W.BIN" % (SD_MOUNT, SD_MOUNT), PW)
    print("   on-SD check while still mounted:", flush=True)
    for line in listing.strip().split("\n"):
        if "password" not in line:
            print("     %s" % line, flush=True)

print("\nstep 2: WRITE_AXI", flush=True)
out = h.mcc.command('WRITE_AXI "\\STEP_W.BIN" %s' % STAGING.text(), wait=6.0)
for line in out.replace("\r", "").split("\n"):
    if line.strip():
        print("     %s" % line.strip(), flush=True)

print("\nstep 3: READ_AXI", flush=True)
end = STAGING.plus(len(PATTERN))
out = h.mcc.command('READ_AXI "\\STEP_R.BIN" %s %s' % (STAGING.text(), end.text()), wait=6.0)
for line in out.replace("\r", "").split("\n"):
    if line.strip():
        print("     %s" % line.strip(), flush=True)

print("\nstep 4: retrieve readback from SD", flush=True)
with SdCard(h.mcc, PW) as sd:
    dump = _sudo("ls -l %s/STEP_R.BIN; xxd %s/STEP_R.BIN" % (SD_MOUNT, SD_MOUNT), PW)
    for line in dump.strip().split("\n"):
        if "password" not in line:
            print("     %s" % line, flush=True)
    got = sd.get("STEP_R.BIN")
    sd.remove("STEP_W.BIN", "STEP_R.BIN")

print("\nresult: sent=%r" % PATTERN, flush=True)
print("        got =%r" % got, flush=True)
print("        %s" % ("IDENTICAL" if got == PATTERN else "DIFFERENT"), flush=True)
h.close()
