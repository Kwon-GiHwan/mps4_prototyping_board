"""PMU ABI host-side unit tests. No board required.

The payload is 106 words / 424 bytes, NOT the 103 discussed earlier: three
fields were added afterwards (two cumulative MMIO counters and the PMCR
readback). total_payload_words is the authority and 106 is never hardcoded
into the parser.
"""

import struct
import sys
import zlib

import runner_proto as rp

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


BASE = rp.RME_KNOWN_FIELDS_V1
SLOTS = rp.NPU_PMU_ABI_EVENT_SLOTS


def build(total_words=rp.RME_PMU_TOTAL_WORDS, declared=None, pmu=None,
          seq=11, flags=rp.RUN_VALID_REQUIRED_MASK, rc=0):
    body = [0] * (total_words - rp.RME_HEADER_WORDS_V1)
    if pmu:
        for idx, val in pmu.items():
            body[BASE + idx] = val
    head = struct.pack("<8I", rp.RME_MAGIC, rp.RME_ABI_VERSION,
                       total_words if declared is None else declared,
                       rp.RME_HEADER_WORDS_V1, seq, flags, rc, 0)
    p = bytearray(head + b"".join(struct.pack("<I", w) for w in body))
    crc = zlib.crc32(bytes(p[16:28]) + bytes(p[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", p, 28, crc)
    return bytes(p)


# field indices inside the PMU block
I_MODE_APPLIED = 2
I_VALID_MASK = 13
I_OVF_MASK = 14
I_CODES = 15
I_VALUES = 23
I_CYC_LO = 31
I_CYC_HI = 32
I_CYC_VALID = 33

print("=== size and CRC ===")
p = build()
check("payload is total_payload_words x 4", len(p) == rp.RME_PMU_TOTAL_WORDS * 4, "%d words, %d bytes" % (rp.RME_PMU_TOTAL_WORDS, len(p)))
m = rp.parse_measurement_payload(p)
check("parses, PMU block present", m.pmu is not None,
      "trailing=%d" % m.trailing_words)

declared = struct.unpack_from("<I", p, 28)[0]
tampered = bytearray(p)
struct.pack_into("<I", tampered, 28, 0xA5A5A5A5)
check("changing ONLY word 7 leaves the computed CRC unchanged",
      rp.measurement_payload_crc(bytes(tampered), rp.RME_PMU_TOTAL_WORDS) == declared)

tampered = bytearray(p)
tampered[-1] ^= 0xFF
check("changing the last word changes the computed CRC",
      rp.measurement_payload_crc(bytes(tampered), rp.RME_PMU_TOTAL_WORDS) != declared)

check("contiguous payload[16:] must NOT match",
      (zlib.crc32(p[16:]) & 0xFFFFFFFF) != declared)

print("\n=== length contract ===")
for d in (rp.RME_PMU_TOTAL_WORDS - 1, rp.RME_PMU_TOTAL_WORDS + 1):
    try:
        rp.parse_measurement_payload(build(declared=d))
        check("declared %d vs 424 bytes rejected" % d, False, "accepted")
    except rp.ProtocolError as e:
        check("declared %d vs 424 bytes rejected" % d, True, str(e)[:38])

try:
    rp.parse_measurement_payload(build(declared=rp.RME_MAX_WORDS + 10_000))
    check("absurd word count rejected before parsing", False, "accepted")
except rp.ProtocolError as e:
    check("absurd word count rejected before parsing", True, str(e)[:38])

print("\n=== absence is not zero ===")
m55 = rp.parse_measurement_payload(build(total_words=rp.RME_MIN_WORDS_V1))
check("MEASURE_SEQ 55-word payload still parses", m55.pmu is None,
      "pmu is None, not a block of zeros")

print("\n=== validity beats value ===")
pmu = {I_VALID_MASK: 0b00000101, I_OVF_MASK: 0b00000100}
for n in range(SLOTS):
    pmu[I_CODES + n] = 0        # code 0 is a REAL event code, not "empty"
    pmu[I_VALUES + n] = 1000 + n
d = rp.parse_measurement_payload(build(pmu=pmu)).pmu
check("invalid slots decode to None", d["event_values"][1] is None
      and d["event_values"][3] is None)
check("valid slot with code 0 is kept", d["event_codes"][0] == 0
      and d["event_values"][0] == 1000)
check("overflow reported only for valid slots",
      d["event_overflow"][2] is True and d["event_overflow"][1] is None)

print("\n=== 48-bit cycle counter ===")
pmu = {I_CYC_LO: 0xFFFFFFFF, I_CYC_HI: 0xFFFF, I_CYC_VALID: 1}
d = rp.parse_measurement_payload(build(pmu=pmu)).pmu
check("wire order is lo then hi, masked to 48 bits",
      d["npu_pmu_window_cycles"] == (1 << 48) - 1,
      "0x%012X" % d["npu_pmu_window_cycles"])

pmu = {I_CYC_LO: 0x1234, I_CYC_HI: 0xDEAD0000, I_CYC_VALID: 1}
d = rp.parse_measurement_payload(build(pmu=pmu)).pmu
check("bits above 48 are discarded",
      d["npu_pmu_window_cycles"] == 0x1234, "0x%X" % d["npu_pmu_window_cycles"])

pmu = {I_CYC_LO: 12345, I_CYC_HI: 0, I_CYC_VALID: 0}
d = rp.parse_measurement_payload(build(pmu=pmu)).pmu
check("cycle_valid=0 yields None even with a non-zero raw value",
      d["npu_pmu_window_cycles"] is None and d["npu_pmu_window_cycles_raw"] == 12345)

print("\n=== OFF is distinguishable from a measurement of zero ===")
d = rp.parse_measurement_payload(build(pmu={I_MODE_APPLIED: rp.INSTRUMENTATION_OFF})).pmu
check("OFF: cycles None, sample_valid 0",
      d["npu_pmu_window_cycles"] is None and d["pmu_sample_valid"] == 0)

print("\n=== SUMMARY ===")
print("passed: %d   failed: %d" % (passed, failed))
sys.exit(1 if failed else 0)
