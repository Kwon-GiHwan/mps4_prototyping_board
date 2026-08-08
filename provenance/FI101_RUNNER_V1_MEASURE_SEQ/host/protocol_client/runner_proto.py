"""Host side of the FI101 runner v1 wire protocol.

The target shares one UART between this binary protocol and legacy printf
output from the Selftest test code, so the receive path never assumes the next
byte starts a header: it searches for the magic, validates the candidate, and
on failure advances by exactly one byte rather than discarding the buffer.
Text found outside frames is kept as a diagnostic log rather than thrown away.
"""

from __future__ import annotations

import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import Optional

MAGIC = 0x3152554E
MAGIC_BYTES = struct.pack("<I", MAGIC)
VERSION = 1
HEADER = "<IBBHII"
HEADER_LEN = struct.calcsize(HEADER)
MAX_PAYLOAD = 4096

CMD_PING = 0x01
CMD_GET_STATE = 0x02
CMD_LOAD_MODEL_BEGIN = 0x10
CMD_LOAD_MODEL_CHUNK = 0x11
CMD_LOAD_MODEL_END = 0x12
CMD_LOAD_INPUT = 0x20
CMD_RUN = 0x30
CMD_RUN_COMPLETE = 0x31  # unsolicited, measure-v2 only
CMD_GET_RESULT = 0x40
CMD_RESET_RUNNER = 0x50

NACK = 0xFF

# Wire protocol variants. Selected explicitly -- never sniffed -- because
# guessing would make a run's provenance ambiguous.
#   functional-v1: CMD_RUN returns a single ACK carrying rc.
#   measure-v2:    CMD_RUN is ACKed BEFORE the measured window opens, then an
#                  unsolicited RUN_COMPLETE (0x31) arrives when it closes.
PROTO_FUNCTIONAL_V1 = "functional-v1"
PROTO_MEASURE_V2 = "measure-v2"
PROTOCOLS = (PROTO_FUNCTIONAL_V1, PROTO_MEASURE_V2)

# --- RUN_COMPLETE measurement ABI ----------------------------------------

RME_MAGIC = 0x524D4531  # "RME1"
RME_ABI_VERSION = 1
RME_HEADER_WORDS_V1 = 8
RME_KNOWN_FIELDS_V1 = 47
RME_MIN_WORDS_V1 = RME_HEADER_WORDS_V1 + RME_KNOWN_FIELDS_V1
RME_MAX_WORDS = MAX_PAYLOAD // 4

RUN_VALID_RUN_COMPLETED = 0x01
RUN_VALID_RUN_RC_OK = 0x02
RUN_VALID_OUTPUT_CHANGED = 0x04
RUN_VALID_COARSE_WINDOW = 0x08
# Computed over the WHOLE .sec_noinit. This is NOT the golden judgement --
# that is the host comparing GET_RESULT(0x90020cc0, 0x100) against 0x27084C4C.
RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH = 0x10

RUN_VALID_REQUIRED_MASK = (
    RUN_VALID_RUN_COMPLETED | RUN_VALID_RUN_RC_OK
    | RUN_VALID_OUTPUT_CHANGED | RUN_VALID_COARSE_WINDOW
)

ERR_RESULT_NOT_VALID = 0x000B


def measurement_payload_crc(payload: bytes, total_words: int) -> int:
    """CRC over the measurement payload.

    The range is deliberately non-contiguous: it covers word 4 (run_sequence)
    through the final word, but skips word 7, which holds the CRC itself.
    Computing it over a contiguous payload[16:] yields a different value, so
    this is isolated in one named function rather than inlined at call sites.
    """
    total_bytes = total_words * 4
    if len(payload) != total_bytes:
        raise ProtocolError(
            "payload length mismatch: declared=%d actual=%d" % (total_bytes, len(payload))
        )
    if total_bytes < RME_HEADER_WORDS_V1 * 4:
        raise ProtocolError("payload shorter than the v1 header")
    return zlib.crc32(payload[16:28] + payload[32:total_bytes]) & 0xFFFFFFFF


@dataclass(frozen=True)
class Measurement:
    run_sequence: int
    valid_flags: int
    run_rc: int
    fields: tuple
    trailing_words: int  # present but not understood by this host version

    def required_flags_ok(self) -> bool:
        return (self.valid_flags & RUN_VALID_REQUIRED_MASK) == RUN_VALID_REQUIRED_MASK


def parse_measurement_payload(payload: bytes) -> Measurement:
    """Validate and decode a RUN_COMPLETE payload.

    Size is taken from the frame, never hardcoded: a later firmware may append
    fields, so anything past the 47 words this host knows is counted and
    skipped rather than treated as an error.
    """
    if len(payload) < RME_HEADER_WORDS_V1 * 4:
        raise ProtocolError("payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != RME_MAGIC:
        raise ProtocolError("bad measurement magic 0x%08X" % magic)
    if version != RME_ABI_VERSION:
        raise ProtocolError("unsupported measurement ABI version %d" % version)
    if header_words != RME_HEADER_WORDS_V1:
        raise ProtocolError("unexpected header_words %d" % header_words)
    if total_words < RME_MIN_WORDS_V1:
        raise ProtocolError(
            "total_payload_words %d below the v1 minimum %d" % (total_words, RME_MIN_WORDS_V1)
        )
    if total_words > RME_MAX_WORDS:
        raise ProtocolError("total_payload_words %d exceeds the protocol cap" % total_words)
    if total_words * 4 != len(payload):
        raise ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload))
        )
    if measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("measurement payload CRC mismatch")

    body = struct.unpack_from("<%dI" % (total_words - header_words), payload, header_words * 4)
    return Measurement(
        run_sequence=seq,
        valid_flags=flags,
        run_rc=rc,
        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
    )

ERROR_NAMES = {
    1: "BAD_VERSION", 2: "BAD_COMMAND", 3: "LENGTH", 4: "BAD_CRC", 5: "STATE",
    6: "RANGE", 7: "CHUNK_MISMATCH", 8: "MODEL_CRC", 9: "PAYLOAD_FORMAT",
}

STATE_NAMES = {
    0: "BOOT", 1: "IDLE", 2: "MODEL_LOADING", 3: "MODEL_READY",
    4: "INPUT_READY", 5: "RUNNING", 6: "RESULT_READY",
}


class ProtocolError(Exception):
    pass


class RunSequenceError(ProtocolError):
    """CMD_RUN frames did not arrive in the order the selected variant requires."""


class Nack(Exception):
    def __init__(self, code: int, orig_cmd: int, state: int) -> None:
        self.code = code
        self.orig_cmd = orig_cmd
        self.state = state
        super().__init__(
            "NACK %s (cmd 0x%02X, state %s)"
            % (ERROR_NAMES.get(code, str(code)), orig_cmd, STATE_NAMES.get(state, state))
        )


@dataclass
class Frame:
    version: int
    command: int
    flags: int
    sequence: int
    payload: bytes


@dataclass
class Counters:
    state: int = 0
    version: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_overrun: int = 0
    bad_magic: int = 0
    bad_version: int = 0
    bad_crc: int = 0
    length_error: int = 0
    sequence_error: int = 0
    parser_resync: int = 0


def build_frame(command: int, sequence: int, payload: bytes = b"", flags: int = 0) -> bytes:
    header = struct.pack(HEADER, MAGIC, VERSION, command, flags, sequence, len(payload))
    body = header + payload
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


class RunnerLink:
    def __init__(self, port: str, baud: int = 115200,
                 protocol: str = PROTO_FUNCTIONAL_V1) -> None:
        import serial

        if protocol not in PROTOCOLS:
            raise ValueError("protocol must be one of %s" % (PROTOCOLS,))
        self.protocol = protocol
        self.late_frames = 0
        self.last_measurement = None
        self._ser = serial.Serial(
            port, baud, timeout=0.2, write_timeout=3,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )
        self._buf = bytearray()
        self._seq = 0
        self.text_log: list[str] = []
        self.resyncs = 0

    def close(self) -> None:
        self._ser.close()

    # -- receive path ------------------------------------------------------

    def _harvest_text(self, upto: int) -> None:
        """Stash non-frame bytes as diagnostic text instead of dropping them."""
        if upto <= 0:
            return
        chunk = bytes(self._buf[:upto])
        text = chunk.decode("ascii", errors="replace").replace("\r", "")
        for line in text.split("\n"):
            if line.strip():
                self.text_log.append(line.strip())

    def _try_parse(self) -> Optional[Frame]:
        while True:
            idx = self._buf.find(MAGIC_BYTES)
            if idx < 0:
                # Keep the last 3 bytes: a magic may straddle the boundary.
                keep = 3
                if len(self._buf) > keep:
                    self._harvest_text(len(self._buf) - keep)
                    del self._buf[: len(self._buf) - keep]
                return None
            if idx:
                self._harvest_text(idx)
                del self._buf[:idx]
            if len(self._buf) < HEADER_LEN:
                return None
            magic, ver, cmd, flags, seq, plen = struct.unpack(HEADER, self._buf[:HEADER_LEN])
            if plen > MAX_PAYLOAD:
                # Bogus candidate: step one byte and keep looking.
                self.resyncs += 1
                self._harvest_text(1)
                del self._buf[:1]
                continue
            total = HEADER_LEN + plen + 4
            if len(self._buf) < total:
                return None
            payload = bytes(self._buf[HEADER_LEN:HEADER_LEN + plen])
            (crc,) = struct.unpack("<I", self._buf[HEADER_LEN + plen:total])
            if crc != (zlib.crc32(self._buf[:HEADER_LEN + plen]) & 0xFFFFFFFF):
                self.resyncs += 1
                self._harvest_text(1)
                del self._buf[:1]
                continue
            del self._buf[:total]
            return Frame(ver, cmd, flags, seq, payload)

    def read_frame(self, timeout: float = 5.0) -> Frame:
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = self._try_parse()
            if frame is not None:
                return frame
            chunk = self._ser.read(1024)
            if chunk:
                self._buf.extend(chunk)
        raise ProtocolError("timed out waiting for a frame")

    # -- request/response --------------------------------------------------

    def send_raw(self, blob: bytes) -> None:
        self._ser.write(blob)
        self._ser.flush()

    def request(self, command: int, payload: bytes = b"", timeout: float = 5.0) -> Frame:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        seq = self._seq
        self.send_raw(build_frame(command, seq, payload))
        while True:
            frame = self.read_frame(timeout)
            if frame.sequence != seq:
                continue  # stale response from an earlier exchange
            if frame.command == NACK:
                orig, state = frame.payload[0], frame.payload[1]
                raise Nack(frame.flags, orig, state)
            if frame.command != (command | 0x80):
                raise ProtocolError(
                    "unexpected response 0x%02X for command 0x%02X" % (frame.command, command)
                )
            return frame

    # -- commands ----------------------------------------------------------

    def ping(self) -> Counters:
        f = self.request(CMD_PING)
        vals = struct.unpack("<BBHIIIIIIIII", f.payload[:40])
        return Counters(
            state=vals[0], version=vals[1], rx_bytes=vals[3], tx_bytes=vals[4],
            rx_overrun=vals[5], bad_magic=vals[6], bad_version=vals[7],
            bad_crc=vals[8], length_error=vals[9], sequence_error=vals[10],
            parser_resync=vals[11],
        )

    def load_model_begin(self, total_len: int, total_crc: int) -> tuple[int, int, int]:
        f = self.request(CMD_LOAD_MODEL_BEGIN, struct.pack("<II", total_len, total_crc))
        return struct.unpack("<III", f.payload[:12])  # total, staging_base, staging_max

    def load_model_chunk(self, offset: int, data: bytes) -> tuple[int, int, int]:
        f = self.request(CMD_LOAD_MODEL_CHUNK, struct.pack("<I", offset) + data)
        return struct.unpack("<III", f.payload[:12])

    def load_model_end(self) -> tuple[int, int, int]:
        f = self.request(CMD_LOAD_MODEL_END, timeout=10.0)
        return struct.unpack("<III", f.payload[:12])  # computed, expected, total

    def load_input(self, data: bytes = b"") -> int:
        f = self.request(CMD_LOAD_INPUT, data)
        return struct.unpack("<I", f.payload[:4])[0]

    def run(self, timeout: float = 30.0) -> int:
        """Execute the fixed inference.

        functional-v1: a single ACK carries rc.
        measure-v2:    ACK arrives BEFORE the measured window opens, then an
                       unsolicited RUN_COMPLETE (0x31) closes it. The frame
                       order is checked rather than assumed, so a firmware /
                       host protocol mismatch surfaces as a clear error instead
                       of a timeout.
        """
        if self.protocol == PROTO_FUNCTIONAL_V1:
            f = self.request(CMD_RUN, timeout=timeout)
            return struct.unpack("<i", f.payload[:4])[0]

        self._seq = (self._seq + 1) & 0xFFFFFFFF
        seq = self._seq
        self.send_raw(build_frame(CMD_RUN, seq))

        acked = False
        completed = False
        rc = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                frame = self.read_frame(min(5.0, max(0.5, deadline - time.time())))
            except ProtocolError:
                break

            if frame.sequence != seq and frame.command != CMD_RUN_COMPLETE:
                # A straggler from an earlier exchange; count it, do not act on it.
                self.late_frames += 1
                continue

            if frame.command == NACK:
                raise Nack(frame.flags, frame.payload[0], frame.payload[1])

            if frame.command == (CMD_RUN | 0x80):
                if acked:
                    raise RunSequenceError("duplicate ACK for CMD_RUN seq=%d" % seq)
                acked = True
                continue

            if frame.command == CMD_RUN_COMPLETE:
                if not acked:
                    raise RunSequenceError("RUN_COMPLETE arrived before the ACK")
                if completed:
                    raise RunSequenceError("duplicate RUN_COMPLETE")
                completed = True
                # rc and the run sequence live in the ABI header, not at offset
                # 0 -- word 0 is the magic. The run sequence here is the
                # firmware's own run counter and is the value GET_RESULT wants;
                # the protocol frame sequence is a different namespace.
                self.last_measurement = parse_measurement_payload(frame.payload)
                rc = self.last_measurement.run_rc
                break

            # Any other frame before the ACK means the board opened the window
            # without acknowledging -- a real protocol violation, not a straggler.
            if not acked:
                raise RunSequenceError(
                    "result frame 0x%02X arrived before the ACK" % frame.command
                )
            self.late_frames += 1

        if not acked:
            raise RunSequenceError("no ACK for CMD_RUN within %.1fs" % timeout)
        if not completed:
            raise RunSequenceError("no RUN_COMPLETE within %.1fs (ACK was seen)" % timeout)
        return 0 if rc is None else rc

    def get_result(self, base: int, length: int,
                   run_sequence: int | None = None) -> tuple[int, int, int, int]:
        """Fetch the result CRC over [base, base+length).

        measure-v2 requires the 12-byte form: without the sequence there is no
        guarantee the result belongs to the run just executed, which is exactly
        the stale-output hazard this build exists to close. The 8-byte form is
        therefore refused here rather than being sent and rejected on target.
        """
        if self.protocol == PROTO_MEASURE_V2:
            if run_sequence is None:
                raise ProtocolError(
                    "measure-v2 GET_RESULT requires run_sequence (12-byte form)"
                )
            payload = struct.pack("<III", base, length, run_sequence)
        else:
            payload = struct.pack("<II", base, length)
        f = self.request(CMD_GET_RESULT, payload, timeout=10.0)
        return struct.unpack("<iIII", f.payload[:16])  # rc, base, len, crc32

    def reset_runner(self) -> None:
        self.request(CMD_RESET_RUNNER)
