"""RUN_FIXED acceptance: Selftest PASS and output-region CRC must both be stable.

The two verdicts are deliberately separate. PASS is the Selftest's own
comparison against its expected output. output_crc32 is an independent host
check computed from the DDR output region read back over READ_AXI.
Output address and length come from Debug/selftest.map:
    0x900203c0  0x00000100  .bss.sec_output_data  u85_Convolution.o
"""

import os
import zlib

from mcc_harness import CONV_OUTPUT_LEN, Harness, LarAddress

# The output-region address MUST come from the map of the build under test.
# official armclang: 0x900203c0 (output_data placed before scratch_buffer)
# GCC:               0x90020cc0 (scatter-declared order: scratch first)
CONV_OUTPUT = LarAddress(port=1, offset=int(os.environ.get("CONV_OUT", "0x900203c0"), 16))

PW = os.environ["MPS4_SUDO_PW"]
REPEATS = 5

h = Harness(PW)

print("=== RUN_FIXED: test 19 (U85_CONV_TEST) x %d ===" % REPEATS, flush=True)
print("output region: LAR 0x%012X  len %d" % (CONV_OUTPUT.encode(), CONV_OUTPUT_LEN), flush=True)
print(flush=True)

results = []
for i in range(REPEATS):
    out = h.run_fixed(19)
    verdict = "PASS" if "U85_CONV_TEST : test result : PASS" in out else "FAIL/UNKNOWN"
    blob = h.read_memory(CONV_OUTPUT, CONV_OUTPUT_LEN, name="CONVOUT.BIN")
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    nonzero = sum(1 for b in blob if b)
    results.append((verdict, crc))
    print("  run %d: selftest=%-12s output_crc32=0x%08X  nonzero=%d/%d"
          % (i + 1, verdict, crc, nonzero, CONV_OUTPUT_LEN), flush=True)

verdicts = {v for v, _ in results}
crcs = {c for _, c in results}

print("\n=== SUMMARY ===", flush=True)
print("selftest verdicts : %s" % (", ".join(sorted(verdicts))), flush=True)
print("distinct CRC32    : %d (%s)" % (len(crcs), ", ".join("0x%08X" % c for c in sorted(crcs))), flush=True)

ok = verdicts == {"PASS"} and len(crcs) == 1
print("\nRESULT: %s" % ("STABLE - PASS and CRC identical across runs" if ok
                        else "UNSTABLE - investigate"), flush=True)
h.close()
