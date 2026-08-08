"""Host-policy acceptance tests for MCC transport harness v0.

These exercise the address/range checks only -- no board access. They verify
what the *host script* rejects; the MCC itself performs no such protection.
"""

import sys

from mcc_harness import (
    LAR_PORT_DDR,
    LAR_PORT_QSPI,
    STAGING,
    STAGING_LIMIT,
    STAGING_SIZE,
    LarAddress,
    check_staging,
    checked_end,
)

passed = 0
failed = 0


def expect_ok(name, fn):
    global passed, failed
    try:
        result = fn()
        print("  PASS  %-42s -> %s" % (name, result))
        passed += 1
    except Exception as exc:
        print("  FAIL  %-42s -> unexpected %s: %s" % (name, type(exc).__name__, exc))
        failed += 1


def expect_reject(name, fn, exc_types):
    global passed, failed
    try:
        result = fn()
        print("  FAIL  %-42s -> accepted (0x%x), should reject" % (name, result))
        failed += 1
    except exc_types as exc:
        print("  PASS  %-42s -> rejected (%s)" % (name, type(exc).__name__))
        passed += 1
    except Exception as exc:
        print("  FAIL  %-42s -> wrong exception %s: %s" % (name, type(exc).__name__, exc))
        failed += 1


print("=== LAR address encoding ===")
expect_ok("port 1 + 0x90120000 encodes", lambda: "0x%012X" % STAGING.encode())
assert STAGING.encode() == 0x0100_9012_0000, "encoding contract broken"
print("        (asserted == 0x010090120000)")
expect_reject("port 256 rejected", lambda: LarAddress(256, 0).encode(), ValueError)
expect_reject("negative port rejected", lambda: LarAddress(-1, 0).encode(), ValueError)
expect_reject("offset >= 2^40 rejected", lambda: LarAddress(1, 1 << 40).encode(), ValueError)

print("\n=== staging window policy (base=0x%x limit=0x%x) ===" % (STAGING.offset, STAGING_LIMIT))
expect_ok("16 bytes at base", lambda: check_staging(STAGING, 16))
expect_ok("full window", lambda: check_staging(STAGING, STAGING_SIZE))
expect_reject("QSPI port 0 rejected", lambda: check_staging(LarAddress(LAR_PORT_QSPI, STAGING.offset), 16), ValueError)
expect_reject("SBROM port 2 rejected", lambda: check_staging(LarAddress(2, STAGING.offset), 16), ValueError)
expect_reject("base-1 rejected", lambda: check_staging(STAGING.plus(-1), 1), ValueError)
expect_reject("1 byte at limit rejected", lambda: check_staging(LarAddress(LAR_PORT_DDR, STAGING_LIMIT), 1), ValueError)
expect_reject("1 byte past limit rejected", lambda: check_staging(STAGING, STAGING_SIZE + 1), ValueError)
expect_reject("length 0 rejected", lambda: check_staging(STAGING, 0), ValueError)
expect_reject("negative length rejected", lambda: check_staging(STAGING, -16), ValueError)

print("\n=== address-field bounds ===")
# Python integers are arbitrary precision, so C-style wraparound cannot occur.
# The meaningful bound is the 40-bit LAR offset field, which read_memory
# enforces by passing limit = 1 << 40 to checked_end.
expect_reject("end past 40-bit LAR field rejected", lambda: checked_end((1 << 40) - 8, 64, 1 << 40), ValueError)
expect_reject("encoding an out-of-field end rejected", lambda: LarAddress(1, 1 << 40).encode(), ValueError)
expect_ok("end just inside LAR field", lambda: "0x%x" % checked_end((1 << 40) - 16, 16, 1 << 40))

print("\n=== exclusive end contract ===")
expect_ok("end is exclusive (base+len)", lambda: "0x%x" % checked_end(0x9012_0000, 16, 1 << 40))
assert checked_end(0x9012_0000, 16, 1 << 40) == 0x9012_0010, "end must be base+length"
print("        (asserted 0x90120000 + 16 == 0x90120010)")

print("\n=== SUMMARY ===")
print("passed: %d   failed: %d" % (passed, failed))
sys.exit(1 if failed else 0)
