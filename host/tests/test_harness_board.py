"""Board acceptance tests for MCC transport harness v0.

Every DDR write is an offline load: RESET_ON -> write -> readback -> compare
-> RESET_OFF. Live writes while the CPU runs are not attempted.
"""

import os
import random
import sys
import time
import zlib

from mcc_harness import STAGING, Harness, LarAddress

PW = os.environ["MPS4_SUDO_PW"]

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        print("  PASS  %-38s %s" % (name, detail), flush=True)
        passed += 1
    else:
        print("  FAIL  %-38s %s" % (name, detail), flush=True)
        failed += 1


h = Harness(PW)

print("=== establishing known-good DDR state (full REBOOT) ===", flush=True)
ddr_ok = h.reboot()
check("DDR initialised by boot", ddr_ok, "'DDR memory test ... PASSED' seen")

print("\n=== PING ===", flush=True)
p = h.ping()
print("  harness            : %s" % p.harness_version, flush=True)
print("  MCC responsive     : %s" % p.mcc_responsive, flush=True)
print("  Selftest responsive: %s" % p.selftest_responsive, flush=True)
print("  staging LAR        : %s (%d MiB)" % (p.staging_lar, p.staging_size // (1 << 20)), flush=True)
check("MCC console reachable", p.mcc_responsive)
check("Selftest CLI reachable", p.selftest_responsive)

print("\n=== 4 KiB round trip (fixed-seed PRNG) ===", flush=True)
rng = random.Random(0xF1101)
payload = bytes(rng.randrange(256) for _ in range(4096))
print("  source CRC32: 0x%08X" % (zlib.crc32(payload) & 0xFFFFFFFF), flush=True)
t0 = time.time()
r = h.round_trip(STAGING, payload)
dt = time.time() - t0
print("  readback CRC32: 0x%08X   (%.1fs)" % (r.readback_crc32, dt), flush=True)
check("4 KiB byte-for-byte identical", r.identical)
check("4 KiB CRC32 match", r.source_crc32 == r.readback_crc32,
      "0x%08X vs 0x%08X" % (r.source_crc32, r.readback_crc32))

print("\n=== assorted lengths ===", flush=True)
for length in (1, 3, 4, 15, 16, 17):
    blob = bytes((i * 7 + length) & 0xFF for i in range(length))
    try:
        res = h.round_trip(STAGING, blob)
        check("%2d bytes" % length, res.identical and res.source_crc32 == res.readback_crc32,
              "crc 0x%08X" % res.readback_crc32)
    except Exception as exc:
        check("%2d bytes" % length, False, "%s: %s" % (type(exc).__name__, exc))

print("\n=== host policy rejects out-of-window write ===", flush=True)
try:
    h.write_memory(LarAddress(1, STAGING.offset - 1), b"x")
    check("below-base write rejected", False, "accepted")
except ValueError as exc:
    check("below-base write rejected", True, str(exc)[:40])

h.close()
print("\n=== SUMMARY ===", flush=True)
print("passed: %d   failed: %d" % (passed, failed), flush=True)
sys.exit(1 if failed else 0)
