"""Measurement-ABI unit tests. No board required.

Every negative case is exercised deliberately, including the one that is
easiest to get wrong: the CRC range skips word 7, so a contiguous CRC over
payload[16:] must NOT validate.
"""

import struct
import sys
import zlib

import runner_proto as rp

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        print("  PASS  %-50s %s" % (name, detail))
        passed += 1
    else:
        print("  FAIL  %-50s %s" % (name, detail))
        failed += 1


def build_payload(total_words=rp.RME_MIN_WORDS_V1, version=rp.RME_ABI_VERSION,
                  header_words=rp.RME_HEADER_WORDS_V1, magic=rp.RME_MAGIC,
                  seq=7, flags=rp.RUN_VALID_REQUIRED_MASK, rc=0,
                  declared_total=None):
    """Well-formed payload unless a parameter is deliberately corrupted."""
    declared = total_words if declared_total is None else declared_total
    body = bytes()
    for i in range(total_words - header_words):
        body += struct.pack("<I", 0x1000 + i)
    head = struct.pack("<8I", magic, version, declared, header_words, seq, flags, rc, 0)
    payload = bytearray(head + body)
    crc = zlib.crc32(bytes(payload[16:28]) + bytes(payload[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", payload, 28, crc)
    return bytes(payload)


print("=== happy path ===")
p = build_payload()
try:
    m = rp.parse_measurement_payload(p)
    check("55-word payload parses", len(p) == 220 and m.run_sequence == 7,
          "%d bytes, seq=%d, trailing=%d" % (len(p), m.run_sequence, m.trailing_words))
    check("required flag mask satisfied", m.required_flags_ok(),
          "flags=0x%02X" % m.valid_flags)
except Exception as exc:
    check("55-word payload parses", False, repr(exc))

print("\n=== the CRC range really is non-contiguous ===")
contig = zlib.crc32(p[16:]) & 0xFFFFFFFF
declared = struct.unpack_from("<I", p, 28)[0]
check("contiguous payload[16:] gives a DIFFERENT value", contig != declared,
      "contig=0x%08X declared=0x%08X" % (contig, declared))
check("named helper reproduces the declared CRC",
      rp.measurement_payload_crc(p, rp.RME_MIN_WORDS_V1) == declared)

print("\n=== negative controls ===")


def expect_reject(name, payload, total_words=None):
    try:
        rp.parse_measurement_payload(payload)
        check(name, False, "accepted")
    except rp.ProtocolError as exc:
        check(name, True, str(exc)[:46])
    except Exception as exc:
        check(name, False, "wrong exception %s" % type(exc).__name__)


expect_reject("bad magic rejected", build_payload(magic=0xDEADBEEF))
expect_reject("unknown ABI version rejected", build_payload(version=99))
expect_reject("unexpected header_words rejected", build_payload(header_words=6))
expect_reject("total below v1 minimum rejected",
              build_payload(total_words=rp.RME_MIN_WORDS_V1 - 1))
expect_reject("declared longer than actual rejected",
              build_payload(declared_total=rp.RME_MIN_WORDS_V1 + 4))
expect_reject("declared shorter than actual rejected",
              build_payload(declared_total=rp.RME_MIN_WORDS_V1 - 4))
expect_reject("total beyond protocol cap rejected",
              build_payload(declared_total=rp.RME_MAX_WORDS + 1))

tampered = bytearray(build_payload())
struct.pack_into("<I", tampered, 28, 0x12345678)
expect_reject("tampered CRC field rejected", bytes(tampered))

tampered = bytearray(build_payload())
tampered[-1] ^= 0xFF
expect_reject("tampered trailing byte rejected", bytes(tampered))

tampered = bytearray(build_payload())
struct.pack_into("<I", tampered, 16, 0xFFFFFFFF)  # run_sequence is inside the CRC range
expect_reject("tampered run_sequence rejected", bytes(tampered))

print("\n=== forward compatibility: extra trailing fields ===")
p2 = build_payload(total_words=rp.RME_MIN_WORDS_V1 + 3)
try:
    m2 = rp.parse_measurement_payload(p2)
    check("longer payload accepted, extras counted",
          m2.trailing_words == 3 and len(m2.fields) == rp.RME_KNOWN_FIELDS_V1,
          "trailing=%d known=%d" % (m2.trailing_words, len(m2.fields)))
    check("CRC covers the appended words too",
          rp.measurement_payload_crc(p2, rp.RME_MIN_WORDS_V1 + 3)
          == struct.unpack_from("<I", p2, 28)[0])
except Exception as exc:
    check("longer payload accepted, extras counted", False, repr(exc))

print("\n=== measure-v2 requires the 12-byte GET_RESULT form ===")
link = rp.RunnerLink.__new__(rp.RunnerLink)
link.protocol = rp.PROTO_MEASURE_V2
try:
    link.get_result(0x90020CC0, 0x100)
    check("8-byte form refused in measure-v2", False, "accepted")
except rp.ProtocolError as exc:
    check("8-byte form refused in measure-v2", True, str(exc)[:46])

print("\n=== flag naming guards against golden misuse ===")
check("FULL_OUTPUT flag not in required mask",
      not (rp.RUN_VALID_REQUIRED_MASK & rp.RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH),
      "required=0x%02X" % rp.RUN_VALID_REQUIRED_MASK)

print("\n=== SUMMARY ===")
print("passed: %d   failed: %d" % (passed, failed))
sys.exit(1 if failed else 0)
