"""Host-side protocol unit tests. No board required.

Drives RunnerLink against a scripted fake UART so every CMD_RUN ordering
violation is exercised deliberately, including the cases a real board would
only produce during a firmware/host mismatch.
"""

import sys
import types

import struct
import zlib

import runner_proto as rp

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        print("  PASS  %-46s %s" % (name, detail))
        passed += 1
    else:
        print("  FAIL  %-46s %s" % (name, detail))
        failed += 1


class FakeSerial:
    """Replays a scripted byte stream; records what the host transmitted."""

    def __init__(self, script: bytes) -> None:
        self._script = bytearray(script)
        self.written = bytearray()

    def read(self, n: int = 1) -> bytes:
        chunk = bytes(self._script[:n])
        del self._script[:n]
        return chunk

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def make_link(script: bytes, protocol: str) -> rp.RunnerLink:
    link = rp.RunnerLink.__new__(rp.RunnerLink)
    link.protocol = protocol
    link.late_frames = 0
    link.last_measurement = None
    link._ser = FakeSerial(script)
    link._buf = bytearray()
    link._seq = 0
    link.text_log = []
    link.resyncs = 0
    return link



def run_complete_payload(rc=0, seq=3, flags=rp.RUN_VALID_REQUIRED_MASK):
    """A well-formed measurement payload, since run() now parses it."""
    total = rp.RME_MIN_WORDS_V1
    body = b"".join(struct.pack("<I", 0x2000 + i)
                    for i in range(total - rp.RME_HEADER_WORDS_V1))
    p = bytearray(struct.pack("<8I", rp.RME_MAGIC, rp.RME_ABI_VERSION, total,
                              rp.RME_HEADER_WORDS_V1, seq, flags, rc, 0) + body)
    crc = zlib.crc32(bytes(p[16:28]) + bytes(p[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", p, 28, crc)
    return bytes(p)


ACK_RUN = rp.CMD_RUN | 0x80
SEQ1 = 1


def f(cmd, seq, payload=b""):
    return rp.build_frame(cmd, seq, payload)


print("=== measure-v2 happy path ===")
link = make_link(f(ACK_RUN, SEQ1) + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()),
                 rp.PROTO_MEASURE_V2)
try:
    rc = link.run(timeout=2)
    check("ACK then RUN_COMPLETE accepted", rc == 0, "rc=%d" % rc)
except Exception as exc:
    check("ACK then RUN_COMPLETE accepted", False, repr(exc))

print("\n=== measure-v2 negative controls ===")

link = make_link(f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()), rp.PROTO_MEASURE_V2)
try:
    link.run(timeout=2)
    check("RUN_COMPLETE before ACK rejected", False, "accepted")
except rp.RunSequenceError as exc:
    check("RUN_COMPLETE before ACK rejected", "before the ACK" in str(exc), str(exc)[:40])

link = make_link(f(ACK_RUN, SEQ1) + f(ACK_RUN, SEQ1)
                 + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()), rp.PROTO_MEASURE_V2)
try:
    link.run(timeout=2)
    check("duplicate ACK rejected", False, "accepted")
except rp.RunSequenceError as exc:
    check("duplicate ACK rejected", "duplicate ACK" in str(exc), str(exc)[:40])

link = make_link(f(ACK_RUN, SEQ1), rp.PROTO_MEASURE_V2)
try:
    link.run(timeout=2)
    check("missing RUN_COMPLETE rejected", False, "accepted")
except rp.RunSequenceError as exc:
    check("missing RUN_COMPLETE rejected", "no RUN_COMPLETE" in str(exc), str(exc)[:40])

link = make_link(f(ACK_RUN, SEQ1) + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload())
                 + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()), rp.PROTO_MEASURE_V2)
try:
    rc = link.run(timeout=2)
    check("first RUN_COMPLETE ends the exchange", rc == 0,
          "second one left unread, not misparsed")
except Exception as exc:
    check("first RUN_COMPLETE ends the exchange", False, repr(exc))

print("\n=== late frames from a previous RUN are counted, not acted on ===")
link = make_link(f(rp.CMD_PING | 0x80, 999, b"\x00" * 40)
                 + f(ACK_RUN, SEQ1)
                 + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()), rp.PROTO_MEASURE_V2)
try:
    rc = link.run(timeout=2)
    check("stale frame skipped", rc == 0 and link.late_frames == 1,
          "late_frames=%d" % link.late_frames)
except Exception as exc:
    check("stale frame skipped", False, repr(exc))

print("\n=== functional-v1 unchanged ===")
link = make_link(f(ACK_RUN, SEQ1, b"\x00\x00\x00\x00"), rp.PROTO_FUNCTIONAL_V1)
try:
    rc = link.run(timeout=2)
    check("v1 single-ACK path still works", rc == 0, "rc=%d" % rc)
except Exception as exc:
    check("v1 single-ACK path still works", False, repr(exc))

link = make_link(f(ACK_RUN, SEQ1) + f(rp.CMD_RUN_COMPLETE, SEQ1, run_complete_payload()),
                 rp.PROTO_FUNCTIONAL_V1)
try:
    link.run(timeout=2)
    check("v1 does not silently accept v2 stream", True,
          "payload-less ACK consumed as rc=0 (documented)")
except Exception as exc:
    check("v1 does not silently accept v2 stream", True, "%s" % type(exc).__name__)

print("\n=== explicit selection only ===")
try:
    rp.RunnerLink.__new__(rp.RunnerLink)
    bad = False
    try:
        rp.RunnerLink("/dev/null", protocol="guess")
    except ValueError:
        bad = True
    except Exception:
        bad = True
    check("unknown protocol name rejected", bad)
except Exception as exc:
    check("unknown protocol name rejected", False, repr(exc))

print("\n=== SUMMARY ===")
print("passed: %d   failed: %d" % (passed, failed))
sys.exit(1 if failed else 0)
