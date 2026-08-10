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
CMD_SET_INSTRUMENTATION_MODE = 0x05
CMD_RUN_PMU_DIAG = 0x60         # RUNNER_V1_PMU_DIAG image only
CMD_GET_PMU_DIAG_RESULT = 0x61  # RUNNER_V1_PMU_DIAG image only
CMD_PMU_DIAG_COMPLETE = 0x62    # unsolicited, diag analogue of 0x31

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

# The PMU candidate appends 51 fields. Both images declare abi_version 1, so
# the field count -- never the version -- decides what can be decoded. A
# MEASURE_SEQ payload (55 words) stays fully parseable; its PMU block is absent
# and is reported as None, never as zeros.
RME_PMU_FIELDS_V1 = 55
RME_PMU_TOTAL_WORDS = RME_HEADER_WORDS_V1 + RME_KNOWN_FIELDS_V1 + RME_PMU_FIELDS_V1

INSTRUMENTATION_OFF = 0
INSTRUMENTATION_END_ONLY = 1
COMPLETION_WAIT_MODE_BUSY_POLL = 1
NPU_PMU_CYCLE_WIDTH_BITS = 48
NPU_PMU_ABI_EVENT_SLOTS = 8

_PMU_SCALARS_A = [
    "record_schema_version", "instrumentation_mode_requested",
    "instrumentation_mode_applied", "event_set_id", "configuration_sequence",
    "npu_pmu_present", "pmu_probe_performed", "hw_event_counter_count",
    "expected_hw_event_counter_count", "abi_event_slot_count",
    "effective_event_slot_count", "requested_event_count",
    "applied_event_count", "event_valid_mask", "event_overflow_mask",
]
_PMU_SCALARS_B = [
    "npu_pmu_window_cycles_lo", "npu_pmu_window_cycles_hi",
    "npu_pmu_cycle_valid", "npu_pmu_cycle_overflow",
    "npu_pmu_cycle_read_retry_count", "pmu_sample_valid",
    "completion_wait_mode", "t_pmu_enable", "t_inference_call_enter",
    "t_inference_call_return", "t_pmu_disable", "t_pmu_programming",
    "cpu_call_window_cycles", "cpu_return_to_pmu_disable_cycles",
    "t_result_processing", "pmu_mmio_read_count_total",
    "pmu_mmio_write_count_total", "pmu_mmio_read_count_delta",
    "pmu_mmio_write_count_delta", "pmcr_at_disable",
    # Independent evidence. "read cleanly" is not "was armed" is not "was
    # globally enabled" is not "actually counted" -- milestone 1 shipped a
    # build where the first was true and the rest were not.
    "cycle_counter_armed", "cycle_global_enable_verified",
    "cycle_read_stable", "cycle_progress_observed",
]


def decode_pmu_block(words):
    """Decode the 51 appended PMU fields.

    Two rules that must not be relaxed:
      - an event slot is judged ONLY by event_valid_mask. Code 0 can be a real
        event, so an invalid slot yields None, not 0.
      - npu_pmu_window_cycles is None unless cycle_valid is set. The name stays
        "window": the snapshot is taken after the inference call returns, not
        in the completion ISR, so it is not NPU execution time.
    """
    if len(words) < RME_PMU_FIELDS_V1:
        raise ProtocolError("PMU block shorter than %d fields" % RME_PMU_FIELDS_V1)
    out, i = {}, 0
    for name in _PMU_SCALARS_A:
        out[name] = words[i]
        i += 1
    codes = list(words[i:i + NPU_PMU_ABI_EVENT_SLOTS]); i += NPU_PMU_ABI_EVENT_SLOTS
    values = list(words[i:i + NPU_PMU_ABI_EVENT_SLOTS]); i += NPU_PMU_ABI_EVENT_SLOTS
    for name in _PMU_SCALARS_B:
        out[name] = words[i]
        i += 1

    mask = out["event_valid_mask"]
    ovf = out["event_overflow_mask"]
    out["event_codes"] = [codes[n] if (mask >> n) & 1 else None
                          for n in range(NPU_PMU_ABI_EVENT_SLOTS)]
    out["event_values"] = [values[n] if (mask >> n) & 1 else None
                           for n in range(NPU_PMU_ABI_EVENT_SLOTS)]
    out["event_overflow"] = [bool((ovf >> n) & 1) if (mask >> n) & 1 else None
                             for n in range(NPU_PMU_ABI_EVENT_SLOTS)]

    raw = out["npu_pmu_window_cycles_lo"] | ((out["npu_pmu_window_cycles_hi"] & 0xFFFF) << 32)
    raw &= (1 << NPU_PMU_CYCLE_WIDTH_BITS) - 1
    out["npu_pmu_window_cycles_raw"] = raw
    out["npu_pmu_window_cycles"] = raw if out["npu_pmu_cycle_valid"] else None
    return out

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
ERR_UNSUPPORTED = 0x000C


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
    pmu: dict | None = None

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
    m = Measurement(
        run_sequence=seq,
        valid_flags=flags,
        run_rc=rc,
        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
        # Absent, not zero: an image without the PMU block must stay
        # distinguishable from one that measured zeros.
        pmu=(decode_pmu_block(body[RME_KNOWN_FIELDS_V1:])
             if total_words >= RME_PMU_TOTAL_WORDS else None),
    )
    return m

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

    def set_instrumentation_mode(self, mode: int, event_codes=(),
                                 event_set_id: int = 0):
        """Set mode and event configuration. Returns (requested, applied,
        applied_count, configuration_sequence).

        The firmware refuses rather than clamps, so a NACK here means the
        request was rejected outright and the previous configuration stands.
        """
        codes = list(event_codes)
        if len(codes) > NPU_PMU_ABI_EVENT_SLOTS:
            raise ProtocolError("at most %d event codes" % NPU_PMU_ABI_EVENT_SLOTS)
        payload = struct.pack("<III", mode, event_set_id, len(codes))
        payload += b"".join(struct.pack("<I", c) for c in codes)
        payload += b"\x00" * (4 * (NPU_PMU_ABI_EVENT_SLOTS - len(codes)))
        f = self.request(CMD_SET_INSTRUMENTATION_MODE, payload)
        return struct.unpack("<IIII", f.payload[:16])

    def reset_runner(self) -> None:
        self.request(CMD_RESET_RUNNER)

    def run_pmu_diag(self, timeout: float = 60.0) -> "PmuDiagResult":
        """RUNNER_V1_PMU_DIAG image only: execute the fixed inference under
        the diag PMU sequence.

        The ACK arrives BEFORE the window opens, then an unsolicited
        CMD_PMU_DIAG_COMPLETE (0x62) closes it -- the same discipline run()
        enforces for measure-v2, checked rather than assumed.
        """
        # A failed run must not leave the PREVIOUS run's bytes lying around as
        # presentable evidence -- cleared before anything is sent.
        self.last_pmu_diag_raw = None
        self.last_pmu_diag_reread_raw = None

        self._seq = (self._seq + 1) & 0xFFFFFFFF
        seq = self._seq
        self.send_raw(build_frame(CMD_RUN_PMU_DIAG, seq))

        acked = False
        result = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                frame = self.read_frame(min(5.0, max(0.5, deadline - time.time())))
            except ProtocolError:
                break

            # The DIAG firmware sends CMD_PMU_DIAG_COMPLETE with the REQUEST
            # sequence, so a mismatched completion is a straggler from an
            # earlier exchange -- counted and dropped, never adopted. This is
            # deliberately stricter than run()'s RUN_COMPLETE handling.
            if frame.sequence != seq:
                self.late_frames += 1
                continue

            if frame.command == NACK:
                raise Nack(frame.flags, frame.payload[0], frame.payload[1])

            if frame.command == (CMD_RUN_PMU_DIAG | 0x80):
                if acked:
                    raise RunSequenceError(
                        "duplicate ACK for CMD_RUN_PMU_DIAG seq=%d" % seq)
                acked = True
                continue

            if frame.command == CMD_PMU_DIAG_COMPLETE:
                if not acked:
                    raise RunSequenceError("PMU_DIAG_COMPLETE arrived before the ACK")
                if result is not None:
                    raise RunSequenceError("duplicate PMU_DIAG_COMPLETE")
                # The EXACT bytes are evidence: the collector archives them so
                # any later analysis can re-verify the payload CRC itself
                # instead of trusting parsed fields.
                self.last_pmu_diag_raw = bytes(frame.payload)
                result = parse_pmu_diag_payload(frame.payload)
                break

            if not acked:
                raise RunSequenceError(
                    "frame 0x%02X arrived before the ACK" % frame.command)
            self.late_frames += 1

        if not acked:
            raise RunSequenceError("no ACK for CMD_RUN_PMU_DIAG within %.1fs" % timeout)
        if result is None:
            raise RunSequenceError(
                "no PMU_DIAG_COMPLETE within %.1fs (ACK was seen)" % timeout)
        return result

    def get_pmu_diag_result(self) -> "PmuDiagResult":
        f = self.request(CMD_GET_PMU_DIAG_RESULT, timeout=10.0)
        self.last_pmu_diag_reread_raw = bytes(f.payload)
        return parse_pmu_diag_payload(f.payload)


# ---------------------------------------------------------------------------
# PMU_DIAG (RUNNER_V1_PMU_DIAG diagnostic image)
#
# A SEPARATE ABI from the measurement payload, on purpose: the production
# schema gains no fields for a temporary diagnostic. Same 8-word header shape
# and the same two-slice CRC rule as RUN_COMPLETE, so measurement_payload_crc
# is reused unchanged.
# ---------------------------------------------------------------------------

PMU_DIAG_MAGIC = 0x31474450  # "PDG1"
# v7 splits the three interventions v6 bundled. All seam images carry the same
# case-B cycle config, so power_seam_id is the only variable. v1-v6 payloads
# are invalid evidence for this experiment and are refused outright.
PMU_DIAG_SCHEMA_VERSION = 7
PMU_DIAG_HEADER_WORDS = 8
PMU_DIAG_SNAPSHOT_WORDS = 8
PMU_DIAG_KNOWN_FIELDS_V7 = 40 + 3 * PMU_DIAG_SNAPSHOT_WORDS  # 64
PMU_DIAG_TOTAL_WORDS_V7 = PMU_DIAG_HEADER_WORDS + PMU_DIAG_KNOWN_FIELDS_V7
PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM = 4
PMU_DIAG_POWER_GUARD_CYCLES = 65536
PMU_DIAG_RESET_GUARD_CYCLES = 65536
PMU_DIAG_REHOLD_GUARD_CYCLES = 65536
PMU_DIAG_STABILITY_SAMPLES = 8

# Power-seam identity. S1/S2 link the reference vendor driver (its terminal
# CMD=0xC lands inside test_u85()); S3 is the v6 configuration re-measured
# under v7 instrumentation and is the known-good control.
PMU_DIAG_SEAM_IDS = {"S1": 1, "S2": 2, "S3": 3}
# ASCII "PDS1".."PDS3" little-endian; must match Makefile.pmu_diag.
PMU_DIAG_SEAM_BUILD_IDS = {"S1": 0x31534450, "S2": 0x32534450,
                           "S3": 0x33534450}

PMU_CYCLE_MASK48 = (1 << 48) - 1

# Known-position pins, the same status as the firmware's _Static_assert on
# 0x11: cross-checks against the machine-extracted vendor header, never the
# source of truth. The firmware refuses to build if these move.
PMU_PMCNTEN_CYCLE_BIT = 31
PMU_PMOVS_CYCLE_OVF_BIT = 31
PMU_PMCR_CNT_EN_BIT = 0

# The semantic golden judgement: CRC32 over EXACTLY the 256-byte test-19
# output window, the same computation the production host makes via
# GET_RESULT(0x90020CC0, 0x100). Board-verified boot-invariant on
# 2026-08-08 (recovered window CRC == 0x27084C4C while the whole-region CRC
# varied with residual scratch). The whole-region result_region_crc is
# CORROBORATION ONLY and is never a validity condition.
GOLDEN_WINDOW_CRC = 0x27084C4C
PMU_DIAG_GOLDEN_WINDOW_BASE = 0x90020CC0
PMU_DIAG_GOLDEN_WINDOW_LEN = 0x100

# Target build identity -- ONE mapping for every host-side check. ASCII
# "PDGA"/"PDGB"/"PDGC" as little-endian words; must match Makefile.pmu_diag.
# The NC control builds carry "PDN1".."PDN4" ids and nc_control_id 1..4 and
# are rejected from the A/B/C dataset by the nc gates, not listed here.
PMU_DIAG_BUILD_IDS = {"A": 0x41474450, "B": 0x42474450, "C": 0x43474450}


@dataclass(frozen=True)
class PmuDiagSnapshot:
    pmcr: int
    pmcntenset: int
    pmccntr_cfg: int
    cycle_lo: int
    cycle_hi: int
    cycle_read_stable: int
    cycle_read_retries: int
    pmovsset: int

    @property
    def cycle48(self) -> int:
        return (self.cycle_lo | ((self.cycle_hi & 0xFFFF) << 32)) & PMU_CYCLE_MASK48

    @property
    def cycle_overflow(self) -> bool:
        return bool((self.pmovsset >> PMU_PMOVS_CYCLE_OVF_BIT) & 1)

    @property
    def armed(self) -> bool:
        return bool((self.pmcntenset >> PMU_PMCNTEN_CYCLE_BIT) & 1)

    @property
    def global_enable(self) -> bool:
        return bool((self.pmcr >> PMU_PMCR_CNT_EN_BIT) & 1)


@dataclass(frozen=True)
class PmuDiagResult:
    schema_version: int
    build_id: int
    diag_case: int      # 1=A 2=B 3=C
    nc_control_id: int  # 0=normal, 1..4 negative control
    run_sequence: int
    cfg_write_performed: int
    cfg_write_value: int
    cfg_readback_after_write: int
    run_rc: int
    valid_flags: int
    poison_crc: int
    output_crc: int
    result_region_crc: int
    ts_source_valid: int
    t_call_enter: int
    t_call_return: int
    t_pmu_disable: int
    pmcr_readback_after_disable: int
    pmu_mmio_read_count_delta: int
    pmu_mmio_write_count_delta: int
    start_sequence_id: int
    power_guard_cycles: int
    npu_cmd_before_power_request: int
    npu_cmd_after_power_request: int
    npu_status_after_power_request: int
    reset_guard_cycles: int
    pmcr_after_reset_guard: int
    pmcr_after_program: int
    armed_after_program: int
    program_stability_reads: int
    program_stable: int
    npu_cmd_after_power_release: int
    power_seam_id: int          # 1=S1 2=S2 3=S3
    power_rehold_performed: int
    rehold_guard_cycles: int
    npu_cmd_after_seam: int
    npu_status_after_seam: int
    golden_window_base: int
    golden_window_len: int
    golden_window_crc: int
    pre: PmuDiagSnapshot
    post: PmuDiagSnapshot
    post_disable: PmuDiagSnapshot
    trailing_words: int  # present but not understood by this host version


def pmu_diag_delta48(pre_cycles: int, post_cycles: int) -> int:
    """48-bit modular progress. NEVER post > pre: a wrap would then read as
    no progress. Overflow handling is the caller's job -- see classify."""
    return (post_cycles - pre_cycles) & PMU_CYCLE_MASK48


def parse_pmu_diag_payload(payload: bytes) -> PmuDiagResult:
    if len(payload) < PMU_DIAG_HEADER_WORDS * 4:
        raise ProtocolError("diag payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_DIAG_MAGIC:
        raise ProtocolError("bad PMU_DIAG magic 0x%08X" % magic)
    if version != PMU_DIAG_SCHEMA_VERSION:
        raise ProtocolError(
            "unsupported PMU_DIAG schema version %d (v1-v6 are invalid "
            "evidence for the seam experiment and must not be re-fed)"
            % version)
    if header_words != PMU_DIAG_HEADER_WORDS:
        raise ProtocolError("unexpected PMU_DIAG header_words %d" % header_words)
    if total_words < PMU_DIAG_TOTAL_WORDS_V7:
        raise ProtocolError(
            "total_payload_words %d below the v7 minimum %d"
            % (total_words, PMU_DIAG_TOTAL_WORDS_V7))
    if total_words * 4 != len(payload):
        raise ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload)))
    if measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("PMU_DIAG payload CRC mismatch")

    body = struct.unpack_from("<%dI" % (total_words - header_words),
                              payload, header_words * 4)
    snaps = []
    for base in (40, 48, 56):
        snaps.append(PmuDiagSnapshot(*body[base:base + PMU_DIAG_SNAPSHOT_WORDS]))
    res = PmuDiagResult(
        *body[:40],
        pre=snaps[0], post=snaps[1], post_disable=snaps[2],
        trailing_words=len(body) - PMU_DIAG_KNOWN_FIELDS_V7,
    )
    # The header duplicates three body fields; a disagreement means the
    # payload was assembled wrong, not that one of them wins.
    if (seq, flags, rc) != (res.run_sequence, res.valid_flags, res.run_rc):
        raise ProtocolError("PMU_DIAG header/body disagree on seq/flags/rc")
    if res.schema_version != version:
        raise ProtocolError("PMU_DIAG body schema_version %d != header %d"
                            % (res.schema_version, version))
    if res.diag_case not in (1, 2, 3):
        raise ProtocolError("PMU_DIAG diag_case %d out of range" % res.diag_case)
    if res.nc_control_id not in (0, 1, 2, 3, 4):
        raise ProtocolError("PMU_DIAG nc_control_id %d out of range"
                            % res.nc_control_id)
    if res.power_seam_id not in (1, 2, 3):
        raise ProtocolError("PMU_DIAG power_seam_id %d out of range"
                            % res.power_seam_id)
    # Only S2 re-holds. A record claiming otherwise describes an image whose
    # seam identity and behaviour disagree, which is never interpretable.
    expect_rehold = 1 if res.power_seam_id == 2 else 0
    if res.power_rehold_performed != expect_rehold:
        raise ProtocolError(
            "PMU_DIAG seam %d reports power_rehold_performed=%d (expected %d)"
            % (res.power_seam_id, res.power_rehold_performed, expect_rehold))
    return res


def classify_pmu_diag(res: PmuDiagResult) -> dict:
    """Derive the contract's validity flags from OBSERVED registers only.

    NO_EVENT == 0 (firmware _Static_assert), so a zero PMCCNTR_CFG means
    "configured never to start" whether or not a write ever happened -- that
    is exactly how the CFG-write-omitted and START=NO_EVENT defect classes
    both land on cfg_programmed=0.
    """
    pre, post = res.pre, res.post
    overflow = pre.cycle_overflow or post.cycle_overflow
    stable = bool(pre.cycle_read_stable and post.cycle_read_stable)
    armed = pre.armed and post.armed
    global_enable = pre.global_enable and post.global_enable
    raw_delta = pmu_diag_delta48(pre.cycle48, post.cycle48)
    # A modulo-positive delta is not progress if the PMU state disappeared.
    # When power/reset clears the counter, (0 - pre) mod 2^48 looks huge even
    # though the post snapshot proves the counter was reset, not advanced.
    progress_observed = bool(armed and global_enable and stable
                             and not overflow and raw_delta > 0)
    cfg_programmed = bool(pre.pmccntr_cfg != 0
                          and post.pmccntr_cfg == pre.pmccntr_cfg)
    cycle_read_valid = bool(armed and global_enable and stable and not overflow)
    return {
        "cfg_programmed": cfg_programmed,
        # A DIFFERENT fact from cfg_programmed: the write/readback PATH
        # worked. Case C is the positive control for exactly this -- it
        # writes a (zero) config and must read it back, so its
        # cfg_write_path_ok is True while cfg_programmed stays False.
        "cfg_write_path_ok": bool(
            res.cfg_write_performed == 1
            and res.cfg_readback_after_write == res.cfg_write_value),
        "cycle_counter_armed": armed,
        "cycle_global_enable": global_enable,
        "cycle_read_stable": stable,
        "cycle_overflow": overflow,
        "raw_delta_diagnostic": raw_delta,
        # Collection-stage enforcement of the analysis rule: a DIAG delta is
        # never a performance metric (extra MMIO reads sit inside it), and a
        # delta without observed progress is not even usable diagnostically.
        "usable_diagnostic_delta": raw_delta if progress_observed else None,
        "progress_observed": progress_observed,
        "cycle_read_valid": cycle_read_valid,
        # v6 sequence boundary evidence. Boot6 showed the v5 programming was
        # attempted while the NPU requested clock/power shutdown. Hold power,
        # guard, reset/guard/program, prove persistence, then release power.
        "start_sequence_ok": (
            res.start_sequence_id == PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM),
        "power_hold_ok": bool(
            res.power_guard_cycles == PMU_DIAG_POWER_GUARD_CYCLES
            and (res.npu_cmd_after_power_request & 0xC) == 0
            and (res.npu_status_after_power_request & 0x8) == 0),
        # Every seam leaves the board in the same terminal state. S2 and S3
        # restore it with a runner write (S2 cancelled the driver's release
        # with its re-hold, S3's private driver never issued one); S1 only
        # reads back what the reference driver already did. The readback is
        # therefore uniform, and WHO wrote it is a static-gate question.
        "power_release_restored": (
            (res.npu_cmd_after_power_release & 0xC) == 0xC),
        # Seam identity and its re-hold shape, as observed.
        "seam_rehold_consistent": (
            res.power_rehold_performed == (1 if res.power_seam_id == 2 else 0)),
        # RUNTIME proof that the seam did what its identity claims, read at
        # the one moment that distinguishes the three images. S1 never
        # re-holds, so by this point the reference driver's terminal release
        # must already be visible; S2 and S3 must still be holding power,
        # S2 because it just re-held and S3 because its private driver never
        # released. Without this the record could claim a seam it did not
        # actually perform.
        "seam_runtime_cmd_ok": (
            (res.npu_cmd_after_seam & 0xC) == 0xC if res.power_seam_id == 1
            else (res.npu_cmd_after_seam & 0xC) == 0),
        # S1 is sampled while the shutdown transition is in flight, so its
        # status bit has no settled meaning and is deliberately NOT gated.
        "seam_runtime_status_ok": (
            True if res.power_seam_id == 1
            else (res.npu_status_after_seam & 0x8) == 0),
        "rehold_guard_ok": (
            res.rehold_guard_cycles == PMU_DIAG_REHOLD_GUARD_CYCLES
            if res.power_seam_id == 2 else res.rehold_guard_cycles == 0),
        "reset_guard_complete": (
            res.reset_guard_cycles == PMU_DIAG_RESET_GUARD_CYCLES),
        "global_after_program": bool(
            (res.pmcr_after_program >> PMU_PMCR_CNT_EN_BIT) & 1),
        "armed_after_program": res.armed_after_program == 1,
        "program_stable": bool(
            res.program_stable == 1
            and res.program_stability_reads == PMU_DIAG_STABILITY_SAMPLES),
        "measurement_usable": bool(cycle_read_valid and progress_observed
                                   and cfg_programmed
                                   and res.start_sequence_id
                                       == PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM
                                   and res.power_guard_cycles
                                       == PMU_DIAG_POWER_GUARD_CYCLES
                                   and (res.npu_cmd_after_power_request & 0xC) == 0
                                   and (res.npu_status_after_power_request & 0x8) == 0
                                   and (res.npu_cmd_after_power_release & 0xC) == 0xC
                                   and res.power_rehold_performed
                                       == (1 if res.power_seam_id == 2 else 0)
                                   and res.reset_guard_cycles
                                       == PMU_DIAG_RESET_GUARD_CYCLES
                                   and res.armed_after_program == 1
                                   and res.program_stable == 1
                                   and res.program_stability_reads
                                       == PMU_DIAG_STABILITY_SAMPLES
                                   and ((res.pmcr_after_program
                                         >> PMU_PMCR_CNT_EN_BIT) & 1)),
        # THE semantic golden gate: the exact 256-byte window, with the
        # base/len contract re-checked. result_region_crc is corroboration
        # display only and is deliberately absent from every validity term.
        "golden_window_ok": bool(
            res.golden_window_base == PMU_DIAG_GOLDEN_WINDOW_BASE
            and res.golden_window_len == PMU_DIAG_GOLDEN_WINDOW_LEN
            and res.golden_window_crc == GOLDEN_WINDOW_CRC),
        "run_rc_ok": res.run_rc == 0,
        "required_flags_ok": (res.valid_flags & RUN_VALID_REQUIRED_MASK)
                             == RUN_VALID_REQUIRED_MASK,
    }


def pmu_diag_b_proof(res: PmuDiagResult) -> tuple[bool, dict]:
    """Case B's pass evidence -- every condition must hold SIMULTANEOUSLY.

    delta > 0 alone proves nothing: the claim is that counter progress
    changed while the individual enable and the global enable were HELD and
    only the start-event configuration differed. The golden check is the
    EXACT 256-byte window CRC (golden_window_crc == 0x27084C4C with the
    base/len contract intact); the whole-region result_region_crc is
    corroboration display only and gates nothing here.
    """
    cls = classify_pmu_diag(res)
    checks = {
        "is_case_b": res.diag_case == 2,
        "is_normal_build": res.nc_control_id == 0,
        # Artifact-level identity, not just the record's own claim: the B
        # image the contract describes is the one Makefile.pmu_diag stamps
        # as "PDGB".
        "build_id_is_pdgb": res.build_id == PMU_DIAG_BUILD_IDS["B"],
        "cfg_write_performed": res.cfg_write_performed == 1,
        "cfg_written_nonzero": res.cfg_write_value != 0,
        "cfg_readback_matches_write": cls["cfg_write_path_ok"],
        "cfg_pre_equals_written": res.pre.pmccntr_cfg == res.cfg_write_value,
        "cfg_post_unchanged": res.post.pmccntr_cfg == res.pre.pmccntr_cfg,
        "armed_pre_and_post": cls["cycle_counter_armed"],
        "global_enable_pre_and_post": cls["cycle_global_enable"],
        "cycle_read_stable": cls["cycle_read_stable"],
        "no_overflow": not cls["cycle_overflow"],
        "delta_positive": cls["progress_observed"],
        "start_sequence_ok": cls["start_sequence_ok"],
        "power_hold_ok": cls["power_hold_ok"],
        "power_release_restored": cls["power_release_restored"],
        "reset_guard_complete": cls["reset_guard_complete"],
        "global_after_program": cls["global_after_program"],
        "armed_after_program": cls["armed_after_program"],
        "program_stable": cls["program_stable"],
        "run_rc_ok": cls["run_rc_ok"],
        "inference_valid_flags": cls["required_flags_ok"],
        "golden_window_crc": cls["golden_window_ok"],
    }
    return all(checks.values()), checks


def pmu_diag_verdict(res_a: PmuDiagResult, res_b: PmuDiagResult,
                     res_c: PmuDiagResult) -> tuple[str, dict]:
    """Apply the root-cause table to OBSERVED results.

    Nothing is assumed: A and C are judged from their own snapshots, never
    coded as zero. An unstable or overflowed sample invalidates the row
    rather than feeding the table.
    """
    ca = classify_pmu_diag(res_a)
    cb = classify_pmu_diag(res_b)
    cc = classify_pmu_diag(res_c)
    detail = {"A": ca, "B": cb, "C": cc}

    # Identity and validity gates FIRST: every case must be the expected
    # normal build, its inference must have succeeded and reproduced the
    # exact golden window CRC, and its sample must be readable. A row that fails
    # any of these feeds nothing -- it gets re-run, not interpreted.
    for name, res, cls, want_case in (("A", res_a, ca, 1), ("B", res_b, cb, 2),
                                      ("C", res_c, cc, 3)):
        if res.diag_case != want_case or res.nc_control_id != 0:
            return ("invalid-sample: case %s carries diag_case=%d "
                    "nc_control_id=%d -- wrong image, re-run"
                    % (name, res.diag_case, res.nc_control_id)), detail
        if not (cls["start_sequence_ok"] and cls["power_hold_ok"]
                and cls["reset_guard_complete"] and cls["program_stable"]
                and cls["power_release_restored"]):
            return ("invalid-sample: case %s did not report the required "
                    "power-hold/guard/program/stable/release PMU sequence -- "
                    "wrong image or invalid power boundary, re-run"
                    % name), detail
        if not (cls["run_rc_ok"] and cls["required_flags_ok"]
                and cls["golden_window_ok"]):
            return ("invalid-sample: case %s inference is not clean "
                    "(rc/flags/exact golden window CRC) -- re-run before "
                    "judging" % name), detail
        if not cls["cycle_read_stable"] or cls["cycle_overflow"]:
            return ("invalid-sample: case %s is unstable or overflowed -- "
                    "re-run before judging" % name), detail

    # The single-variable claim needs the COMMON enables held in the CONTEXT
    # rows: an A or C that lost arm or global enable is not a clean "CFG
    # differs, everything else equal" comparison partner. B is deliberately
    # NOT gated here -- losing arm/global in the call is one of the outcomes
    # the table exists to diagnose, and it is separated below.
    for name, cls in (("A", ca), ("C", cc)):
        if not (cls["global_after_program"]
                and cls["armed_after_program"]
                and cls["cycle_counter_armed"]
                and cls["cycle_global_enable"]):
            return ("invalid-sample: case %s did not hold the cycle arm and "
                    "global enable after programming and across pre/post "
                    "snapshots -- not a valid comparison row, re-run"
                    % name), detail
    # Case-contract identity: A must never have written CFG; C must have
    # written a zero config through a WORKING write/readback path.
    if res_a.cfg_write_performed != 0:
        return ("invalid-sample: case A reports cfg_write_performed=1 -- "
                "violates the A contract, wrong image or build"), detail
    if not (res_c.cfg_write_performed == 1 and res_c.cfg_write_value == 0
            and cc["cfg_write_path_ok"]):
        return ("invalid-sample: case C is not a valid explicit-zero write "
                "control (write/readback path or value wrong)"), detail
    # Cross-case drift corroboration: the SAME fixed inference must leave the
    # SAME output bytes in every case. This supplements the exact golden
    # window (which each case already passed above) -- it never replaces it,
    # and the whole-region CRC is deliberately NOT compared here: it varies
    # with residual scratch and proved it on the 2026-08-08 boot1/2 runs.
    if not (res_a.output_crc == res_b.output_crc == res_c.output_crc):
        return ("invalid-sample: output_crc disagrees across A/B/C "
                "(A=0x%08X B=0x%08X C=0x%08X) -- inference outputs differ, "
                "re-run" % (res_a.output_crc, res_b.output_crc,
                            res_c.output_crc)), detail

    a_zero = ca["raw_delta_diagnostic"] == 0
    c_zero = cc["raw_delta_diagnostic"] == 0
    b_full_proof, _ = pmu_diag_b_proof(res_b)
    b_pos = cb["progress_observed"]

    if a_zero != c_zero:
        return ("A-and-C-differ: explicit zero write has a distinct effect -- "
                "investigate further"), detail
    if a_zero and c_zero and b_full_proof:
        return "cfg-missing-root-cause: PMCCNTR_CFG programming was the missing wiring", detail
    if a_zero and c_zero and b_pos:
        # Progress alone is NOT the B proof: some held-state or CRC condition
        # failed, so the comparison is not the clean single-variable one.
        return ("inconclusive: B shows progress but fails the full B proof -- "
                "inspect pmu_diag_b_proof(res_b) before claiming a root cause"), detail
    if not a_zero and not c_zero and b_full_proof:
        return ("cfg-not-required: A/B/C all show cycle progress while power "
                "is held; PMCCNTR_CFG programming was not the missing wiring"), detail
    if not b_pos:
        # FIRST: were the preconditions ever established? A pre-call state
        # that never held CFG/arm/global is a programming failure, not an
        # in-call loss, and "all held" would be a false statement about it.
        missing = []
        if not (res_b.cfg_write_value != 0
                and res_b.pre.pmccntr_cfg == res_b.cfg_write_value):
            missing.append("cfg")
        if not res_b.pre.armed:
            missing.append("arm")
        if not res_b.pre.global_enable:
            missing.append("global")
        if missing:
            return ("b-precondition-not-established: pre-call %s never held "
                    "-- fix the programming path before interpreting the "
                    "no-progress result" % "+".join(missing)), detail
        # Established pre-call, so a change IS an in-call loss.
        if res_b.post.pmccntr_cfg != res_b.pre.pmccntr_cfg:
            return "cfg-lost-in-call: in-call reset clears PMCCNTR_CFG", detail
        if not res_b.post.armed:
            return "arm-lost-in-call: in-call reset clears the PMCNTEN cycle bit", detail
        if not res_b.post.global_enable:
            return "global-enable-lost: reset/power path clears PMCR.cnt_en", detail
        return ("b-no-progress-all-held: CFG, arm and global enable held pre "
                "AND post -- re-examine PMU clock / CYCLE event semantics / "
                "reset order"), detail
    return "inconclusive: pattern matches no table row -- record and escalate", detail


# ---------------------------------------------------------------------------
# v7 power-seam experiment (S1/S2/S3)
#
# Every seam image carries the SAME case-B cycle configuration, so PMCCNTR_CFG
# is held constant and only the power seam varies. The question is narrow and
# so are the answers: which of v6's three bundled interventions the production
# END_ONLY candidate actually needs.
# ---------------------------------------------------------------------------

def pmu_diag_seam_post_held(res: PmuDiagResult) -> bool:
    """Did the programmed state survive the inference AND did the counter
    move? This is the single predicate the seam rows are compared on."""
    cls = classify_pmu_diag(res)
    return bool(res.post.armed and res.post.global_enable
                and res.post.pmccntr_cfg == res.pre.pmccntr_cfg
                and res.pre.pmccntr_cfg != 0
                and cls["progress_observed"])


def pmu_diag_seam_row_ok(res: PmuDiagResult, seam: str) -> tuple[bool, dict]:
    """Identity and validity gates every seam row must clear before its post
    state means anything. Deliberately excludes the post-state predicate --
    a row can be perfectly valid and still show the loss we are measuring."""
    cls = classify_pmu_diag(res)
    checks = {
        "seam_id": res.power_seam_id == PMU_DIAG_SEAM_IDS[seam],
        "build_id": res.build_id == PMU_DIAG_SEAM_BUILD_IDS[seam],
        "case_is_b": res.diag_case == 2,
        "is_normal_build": res.nc_control_id == 0,
        "seam_rehold_consistent": cls["seam_rehold_consistent"],
        "rehold_guard_ok": cls["rehold_guard_ok"],
        "seam_runtime_cmd_ok": cls["seam_runtime_cmd_ok"],
        "seam_runtime_status_ok": cls["seam_runtime_status_ok"],
        "start_sequence_ok": cls["start_sequence_ok"],
        "power_hold_ok": cls["power_hold_ok"],
        "power_release_restored": cls["power_release_restored"],
        "reset_guard_complete": cls["reset_guard_complete"],
        "global_after_program": cls["global_after_program"],
        "armed_after_program": cls["armed_after_program"],
        "program_stable": cls["program_stable"],
        # The ACTUAL pre-inference state, read from the pre snapshot. The
        # *_after_program fields above are a different fact: they describe
        # the moment programming finished, and the stability loop runs
        # before the snapshot. If the state decayed between them, only these
        # three catch it -- and without them a loss that happened BEFORE the
        # inference would be misread as the terminal release's fault.
        "pre_armed": res.pre.armed,
        "pre_global_enable": res.pre.global_enable,
        "cfg_programmed_pre": res.pre.pmccntr_cfg == res.cfg_write_value,
        "cfg_write_path_ok": cls["cfg_write_path_ok"],
        "cycle_read_stable": cls["cycle_read_stable"],
        "no_overflow": not cls["cycle_overflow"],
        "run_rc_ok": cls["run_rc_ok"],
        "inference_valid_flags": cls["required_flags_ok"],
        "golden_window_crc": cls["golden_window_ok"],
    }
    return all(checks.values()), checks


def pmu_diag_seam_verdict(res_s1: PmuDiagResult, res_s2: PmuDiagResult,
                          res_s3: PmuDiagResult) -> tuple[str, dict]:
    """Apply the seam table to OBSERVED rows, conservatively.

    The one thing this function must never do is turn a single passing S2 run
    into a production decision. S2 matching S3 shows the re-hold is worth
    repeating, not that it is qualified: n=1 establishes nothing about
    stability, and the production candidate is a different image again.
    """
    rows = {"S1": (res_s1, "S1"), "S2": (res_s2, "S2"), "S3": (res_s3, "S3")}
    detail = {}
    for name, (res, seam) in rows.items():
        ok, checks = pmu_diag_seam_row_ok(res, seam)
        detail[name] = {
            "row_ok": ok,
            "checks": checks,
            "post_held": pmu_diag_seam_post_held(res),
            "classify": classify_pmu_diag(res),
        }

    for name in ("S1", "S2", "S3"):
        if not detail[name]["row_ok"]:
            failed = [k for k, v in detail[name]["checks"].items() if not v]
            return ("invalid-sample: %s failed %s -- re-run before judging"
                    % (name, ", ".join(failed))), detail

    # Cross-seam drift corroboration. Each row already passed the exact
    # 256-byte golden window on its own; this ADDS the requirement that the
    # same fixed inference left the same output bytes in all three, which is
    # what makes them comparable. The whole-region CRC is deliberately not
    # compared -- it varies with residual scratch and proved it on boot1/2.
    if not (res_s1.output_crc == res_s2.output_crc == res_s3.output_crc):
        return ("invalid-sample: output_crc disagrees across the seams "
                "(S1=0x%08X S2=0x%08X S3=0x%08X) -- the rows are not "
                "comparable, re-run"
                % (res_s1.output_crc, res_s2.output_crc,
                   res_s3.output_crc)), detail

    # The control anchors the whole comparison. Without it, S1/S2 outcomes
    # cannot be attributed to their seams at all.
    if not detail["S3"]["post_held"]:
        return ("control-failed: S3 (the v6 known-good configuration) did not "
                "hold its post state -- re-establish the control before "
                "interpreting S1 or S2"), detail

    s1_held = detail["S1"]["post_held"]
    s2_held = detail["S2"]["post_held"]

    if s1_held and s2_held:
        return ("terminal-release-harmless: S1 held its post state without any "
                "re-hold, so the reference driver's terminal release did not "
                "cost us the evidence in this run -- the pre-hold alone is the "
                "candidate minimal seam, pending repetition"), detail
    if not s1_held and s2_held:
        return ("rehold workaround viable-for-repeat: S1 lost its post state "
                "and S2 recovered it with a post-return re-hold on the "
                "reference driver. This is NOT a production GO -- one passing "
                "run is not stability evidence and the END_ONLY candidate is a "
                "different image; repeat across independent boots first"), detail
    if not s1_held and not s2_held:
        return ("internal-pre-release-seam-required: neither S1 nor S2 held "
                "the post state, so a re-hold after the driver returns is too "
                "late -- the seam must sit inside the inference path before "
                "the driver's terminal release"), detail
    return ("inconclusive: S1 held but S2 did not, which no seam hypothesis "
            "predicts -- record and escalate"), detail


# ---------------------------------------------------------------------------
# PMU_QUAL (schema v8, H-PRINTF qualification images Q0/Q1)
#
# A SEPARATE parser and classifier from v7, not an extension of it. v7 answered
# "where is the counter state lost"; v8 asks "is this one sample a publishable
# performance value". Those need different, stricter rules, so nothing above is
# modified and nothing above is called for a validity decision: v7's
# (pre, post) pair, cfg_programmed, cfg_write_path_ok, progress_observed and
# seam_post_held are all deliberately absent from everything below.
#
# The wire record keeps the diag magic and the 8-word header; the SCHEMA
# VERSION is what separates the two ABIs, which is why parse_pmu_diag_payload
# refuses a v8 payload and parse_pmu_qual_payload refuses a v7 one.
# ---------------------------------------------------------------------------

PMU_QUAL_MAGIC = PMU_DIAG_MAGIC
PMU_QUAL_SCHEMA_VERSION = 8
PMU_QUAL_HEADER_WORDS = 8
PMU_QUAL_BASE_FIELDS = 40       # the v7 prefix, retained slot-for-slot
PMU_QUAL_HOOK_FIELDS = 13       # appended by v8
PMU_QUAL_SNAPSHOT_WORDS = 8
PMU_QUAL_SNAPSHOT_COUNT = 4     # pre, internal_pre_release, internal_post_disable, after_return
PMU_QUAL_KNOWN_FIELDS = (PMU_QUAL_BASE_FIELDS + PMU_QUAL_HOOK_FIELDS
                         + PMU_QUAL_SNAPSHOT_COUNT * PMU_QUAL_SNAPSHOT_WORDS)  # 85
PMU_QUAL_TOTAL_WORDS = PMU_QUAL_HEADER_WORDS + PMU_QUAL_KNOWN_FIELDS           # 93
PMU_QUAL_PAYLOAD_SIZE = PMU_QUAL_TOTAL_WORDS * 4                              # 372

PMU_QUAL_MODES = {"Q0": 0, "Q1": 1}
# ASCII "PQB0"/"PQH1" little-endian; must match Makefile.pmu_qual. Q0 is the
# hook-disabled baseline and is invalid as a performance sample BY DESIGN.
PMU_QUAL_BUILD_IDS = {"Q0": 0x30425150, "Q1": 0x31485150}
# v8 runs no seam experiment. The three seam slots are retained for layout
# compatibility and pinned, so a seam image can never be read as a v8 record.
PMU_QUAL_POWER_SEAM_ID = 4

# Vendor CMD bits 3:2. Held == 0 at the hook (the release has not happened
# yet); restored == 0xC after test_u85() returns.
PMU_QUAL_NPU_CMD_RELEASE_MASK = 0xC


@dataclass(frozen=True)
class PmuQualResult:
    """One schema-v8 record.

    The first 40 fields keep the v7 prefix slots. Two of them change MEANING
    in v8 and are named for what they now carry:
      - npu_cmd_after_return reuses the v7 npu_cmd_after_power_release slot;
      - npu_cmd_after_seam / npu_status_after_seam are after-return
        corroboration, not seam telemetry.
    """
    schema_version: int
    build_id: int
    diag_case: int
    nc_control_id: int
    run_sequence: int
    cfg_write_performed: int
    cfg_write_value: int
    cfg_readback_after_write: int
    run_rc: int
    valid_flags: int
    poison_crc: int
    output_crc: int
    result_region_crc: int
    ts_source_valid: int
    t_call_enter: int
    t_call_return: int
    t_pmu_disable: int
    pmcr_readback_after_disable: int
    pmu_mmio_read_count_delta: int
    pmu_mmio_write_count_delta: int
    start_sequence_id: int
    power_guard_cycles: int
    npu_cmd_before_power_request: int
    npu_cmd_after_power_request: int
    npu_status_after_power_request: int
    reset_guard_cycles: int
    pmcr_after_reset_guard: int
    pmcr_after_program: int
    armed_after_program: int
    program_stability_reads: int
    program_stable: int
    npu_cmd_after_return: int
    power_seam_id: int
    power_rehold_performed: int
    rehold_guard_cycles: int
    npu_cmd_after_seam: int
    npu_status_after_seam: int
    golden_window_base: int
    golden_window_len: int
    golden_window_crc: int
    # --- the 13 appended hook words, in wire order ---
    qualification_mode: int
    hook_armed: int
    hook_arm_consumed: int
    hook_detected_count: int
    hook_fired_count: int
    hook_snapshot_valid: int
    hook_callsite_lr_observed: int
    hook_entry_timestamp: int
    hook_exit_timestamp: int
    npu_cmd_at_hook: int
    pmcr_disable_readback_at_hook: int
    hook_pmu_mmio_read_count: int
    hook_pmu_mmio_write_count: int
    # --- four snapshots; only the first two are authoritative ---
    pre: PmuDiagSnapshot
    internal_pre_release: PmuDiagSnapshot
    internal_post_disable: PmuDiagSnapshot
    after_return: PmuDiagSnapshot
    trailing_words: int  # present but not understood by this host version


def parse_pmu_qual_payload(payload: bytes) -> PmuQualResult:
    """Validate and decode a schema-v8 qualification payload.

    Schema v1-v7 are refused outright: they were collected to localize a
    fault, not to publish a number, and re-feeding one here would launder
    diagnostic evidence into a performance claim.
    """
    if len(payload) < PMU_QUAL_HEADER_WORDS * 4:
        raise ProtocolError("qual payload too short for the ABI header")
    magic, version, total_words, header_words, seq, flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != PMU_QUAL_MAGIC:
        raise ProtocolError("bad PMU_QUAL magic 0x%08X" % magic)
    if version != PMU_QUAL_SCHEMA_VERSION:
        raise ProtocolError(
            "unsupported PMU_QUAL schema version %d (only v8 records are "
            "qualification evidence)" % version)
    if header_words != PMU_QUAL_HEADER_WORDS:
        raise ProtocolError("unexpected PMU_QUAL header_words %d" % header_words)
    if total_words < PMU_QUAL_TOTAL_WORDS:
        raise ProtocolError(
            "total_payload_words %d below the v8 minimum %d"
            % (total_words, PMU_QUAL_TOTAL_WORDS))
    if total_words * 4 != len(payload):
        raise ProtocolError(
            "declared %d bytes, frame carried %d" % (total_words * 4, len(payload)))
    if measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("PMU_QUAL payload CRC mismatch")

    body = struct.unpack_from("<%dI" % (total_words - header_words),
                              payload, header_words * 4)
    scalars = PMU_QUAL_BASE_FIELDS + PMU_QUAL_HOOK_FIELDS
    snaps = []
    for n in range(PMU_QUAL_SNAPSHOT_COUNT):
        base = scalars + n * PMU_QUAL_SNAPSHOT_WORDS
        snaps.append(PmuDiagSnapshot(*body[base:base + PMU_QUAL_SNAPSHOT_WORDS]))
    res = PmuQualResult(
        *body[:scalars],
        pre=snaps[0], internal_pre_release=snaps[1],
        internal_post_disable=snaps[2], after_return=snaps[3],
        trailing_words=len(body) - PMU_QUAL_KNOWN_FIELDS,
    )
    if (seq, flags, rc) != (res.run_sequence, res.valid_flags, res.run_rc):
        raise ProtocolError("PMU_QUAL header/body disagree on seq/flags/rc")
    if res.schema_version != version:
        raise ProtocolError("PMU_QUAL body schema_version %d != header %d"
                            % (res.schema_version, version))
    if res.qualification_mode not in PMU_QUAL_MODES.values():
        raise ProtocolError("PMU_QUAL qualification_mode %d out of range"
                            % res.qualification_mode)
    if res.diag_case not in (1, 2, 3):
        raise ProtocolError("PMU_QUAL diag_case %d out of range" % res.diag_case)
    if res.nc_control_id not in (0, 1, 2, 3, 4):
        raise ProtocolError("PMU_QUAL nc_control_id %d out of range"
                            % res.nc_control_id)
    # The retained seam slots must describe the v8 shape exactly. A record that
    # still claims a seam identity or a re-hold is a v7 image mislabelled, and
    # its power boundary means something else entirely.
    if (res.power_seam_id, res.power_rehold_performed, res.rehold_guard_cycles) \
            != (PMU_QUAL_POWER_SEAM_ID, 0, 0):
        raise ProtocolError(
            "PMU_QUAL retained seam slots are seam_id=%d rehold=%d guard=%d "
            "(expected %d/0/0)"
            % (res.power_seam_id, res.power_rehold_performed,
               res.rehold_guard_cycles, PMU_QUAL_POWER_SEAM_ID))
    return res


def _qual_manifest_build_id(expected_manifest: dict) -> int | None:
    """The manifest is JSON, so build_id arrives as a hex string. Anything
    unparseable yields None, which can never equal an observed build id."""
    value = expected_manifest.get("build_id")
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def classify_pmu_qual(res: PmuQualResult, expected_manifest: dict) -> dict:
    """Fail-closed v8 validity. Every term must hold for a value to exist.

    Three rules this function exists to enforce:

      - the authoritative state pair is (pre, internal_pre_release) ONLY. The
        vendor release wipes the PMU bank, so after_return is expected to read
        as zeros and is excluded from every term below; internal_post_disable
        is corroboration for the single in-hook disable write.
      - the no-CFG contract is positive evidence, not an absence: v8 writes no
        PMCCNTR_CFG, so cfg_write_performed and BOTH authoritative CFG reads
        must be zero. A record that programmed a config is a different image.
      - the expected callsite address comes from the build manifest, never
        from firmware and never from a default. The manifest is a required
        argument so a caller cannot accidentally self-approve a sample.

    The only performance field is npu_pmu_window_cycles. It is a counter
    window, not T_npu and not a latency, and it is None whenever anything
    failed.
    """
    pre, internal = res.pre, res.internal_pre_release
    raw_delta = pmu_diag_delta48(pre.cycle48, internal.cycle48)
    # A counter cleared by the power/reset path reads as (0 - pre) mod 2^48,
    # which is enormous and positive. Only the pair can tell that apart from
    # real progress, and only by the shape.
    reset_to_zero = bool(pre.cycle48 != 0 and internal.cycle48 == 0)

    expected_mode = PMU_QUAL_MODES.get(expected_manifest.get("qualification_mode"))
    expected_build_id = _qual_manifest_build_id(expected_manifest)
    expected_lr = expected_manifest.get("expected_return_address")

    terms = {
        # Identity: the record, the image and the manifest must agree, and the
        # image must be the H-PRINTF candidate rather than the baseline.
        "manifest_schema_matches": (
            expected_manifest.get("schema_version") == PMU_QUAL_SCHEMA_VERSION),
        "manifest_mode_matches": (
            expected_mode is not None and res.qualification_mode == expected_mode),
        "manifest_build_id_matches": (
            expected_build_id is not None and res.build_id == expected_build_id),
        "mode_is_hprintf": res.qualification_mode == PMU_QUAL_MODES["Q1"],
        "build_id_is_hprintf": res.build_id == PMU_QUAL_BUILD_IDS["Q1"],
        "is_normal_build": res.nc_control_id == 0,
        # Q0 and Q1 are contractually case-A images: they write no PMCCNTR_CFG
        # at all. A record claiming case B or C describes a DIFFERENT image
        # whose cycle configuration was programmed, so the no-CFG terms below
        # would be judging the wrong contract. Kept as a validity term rather
        # than a parser refusal so a mislabelled record still archives.
        "is_case_a": res.diag_case == 1,

        # The hook fired exactly once, at the attested callsite, while the NPU
        # power request was still held. Zero times and twice both fail.
        "hook_armed": res.hook_armed == 1,
        "hook_arm_consumed": res.hook_arm_consumed == 1,
        "hook_detected_once": res.hook_detected_count == 1,
        "hook_fired_once": res.hook_fired_count == 1,
        "hook_snapshot_valid": res.hook_snapshot_valid == 1,
        "hook_callsite_lr_matches_manifest": (
            isinstance(expected_lr, int)
            and res.hook_callsite_lr_observed == expected_lr),
        # EXACTLY zero, not merely free of the release bits. At the hook the
        # vendor driver has not yet issued its terminal CMD, so any set bit --
        # release or otherwise -- means the register was in a state this
        # sample cannot account for. The masked form is correct only for the
        # after-return term below, where 0xC is the value being looked for.
        "npu_power_held_at_hook": res.npu_cmd_at_hook == 0,

        # The hook's PMU accesses happen INSIDE the measurement window, so the
        # hook-local counts are a SUBSET of the whole-window deltas and
        # equality is the legitimate boundary (a window whose only PMU traffic
        # was the hook's own). A window total below its own subset means the
        # two counters were not counting the same accesses, which makes the
        # contamination evidence meaningless in either direction. Exact
        # cross-run count invariance is the later analyzer's job, not a
        # single-sample term.
        "hook_mmio_reads_within_window": (
            res.pmu_mmio_read_count_delta >= res.hook_pmu_mmio_read_count),
        "hook_mmio_writes_within_window": (
            res.pmu_mmio_write_count_delta >= res.hook_pmu_mmio_write_count),

        # Start boundary, unchanged in meaning from v6/v7 and re-derived here
        # rather than borrowed, so a v7 classifier change can never silently
        # move a v8 validity line.
        "start_sequence_ok": (
            res.start_sequence_id == PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM),
        "power_hold_ok": bool(
            res.power_guard_cycles == PMU_DIAG_POWER_GUARD_CYCLES
            and (res.npu_cmd_after_power_request & 0xC) == 0
            and (res.npu_status_after_power_request & 0x8) == 0),
        "reset_guard_complete": (
            res.reset_guard_cycles == PMU_DIAG_RESET_GUARD_CYCLES),
        "armed_after_program": res.armed_after_program == 1,
        "global_after_program": bool(
            (res.pmcr_after_program >> PMU_PMCR_CNT_EN_BIT) & 1),
        "program_stable": bool(
            res.program_stable == 1
            and res.program_stability_reads == PMU_DIAG_STABILITY_SAMPLES),

        # The no-CFG contract, on both authoritative reads.
        "cfg_no_write": res.cfg_write_performed == 0,
        "cfg_pre_zero": pre.pmccntr_cfg == 0,
        "cfg_internal_zero": internal.pmccntr_cfg == 0,

        # Both authoritative snapshots, judged separately so the failure names
        # which end of the window lost the state.
        "pre_armed": pre.armed,
        "pre_global_enable": pre.global_enable,
        "pre_read_stable": bool(pre.cycle_read_stable),
        "internal_armed": internal.armed,
        "internal_global_enable": internal.global_enable,
        "internal_read_stable": bool(internal.cycle_read_stable),
        "no_overflow": not (pre.cycle_overflow or internal.cycle_overflow),

        "positive_delta": bool(raw_delta > 0 and not reset_to_zero),

        # The single in-hook disable write was acknowledged: PMCR.cnt_en reads
        # back clear. After the return the runner only reads, so this is the
        # one place the disable can be proven.
        "pmu_disable_acknowledged": not (
            (res.pmcr_disable_readback_at_hook >> PMU_PMCR_CNT_EN_BIT) & 1),
        # The vendor driver reached its own terminal release after the hook, so
        # the hook did not displace or skip it.
        "vendor_release_after_return": (
            (res.npu_cmd_after_return & PMU_QUAL_NPU_CMD_RELEASE_MASK)
            == PMU_QUAL_NPU_CMD_RELEASE_MASK),

        # The inference itself. result_region_crc is corroboration display only
        # and is deliberately absent from every term here, as in v7.
        "golden_window_ok": bool(
            res.golden_window_base == PMU_DIAG_GOLDEN_WINDOW_BASE
            and res.golden_window_len == PMU_DIAG_GOLDEN_WINDOW_LEN
            and res.golden_window_crc == GOLDEN_WINDOW_CRC),
        "run_rc_ok": res.run_rc == 0,
        "required_flags_ok": (res.valid_flags & RUN_VALID_REQUIRED_MASK)
                             == RUN_VALID_REQUIRED_MASK,
    }
    valid = all(terms.values())
    return {
        "terms": terms,
        "invalid_reasons": sorted(k for k, v in terms.items() if not v),
        "raw_delta_diagnostic": raw_delta,
        "reset_to_zero": reset_to_zero,
        "npu_pmu_window_cycles": raw_delta if valid else None,
        "valid": valid,
    }


# ---------------------------------------------------------------------------
# PMU_CFG (schema-v8 wire layout, CFG A/B/C characterization images)
# ---------------------------------------------------------------------------
#
# CHARACTERIZATION ONLY. Not latency, not T_npu, not a performance baseline,
# not a Production GO, not Gate 7, not MLEK data. The +514 identity observed in
# the Gate 1 fixed-image Q1 campaign is NOT generalized to these images.
#
# These images reuse the schema-v8 payload and the Q1 H-PRINTF seam unchanged;
# only the PMCCNTR_CFG action varies. They therefore carry their OWN build ids
# and are never accepted by the Q0/Q1 qualification verdict.

PMU_CFG_CASES = ("A", "B", "C")
PMU_CFG_CASE_IDS = {"A": 1, "B": 2, "C": 3}          # matches PMU_DIAG_CASE_ID
PMU_CFG_BUILD_IDS = {                                 # matches Makefile.pmu_cfg
    "A": 0x31414350,   # ASCII "PCA1"
    "B": 0x31424350,   # ASCII "PCB1"
    "C": 0x31434350,   # ASCII "PCC1"
}

# The EXACT term names classify_pmu_cfg removes from, and adds to, the common
# Q1 rule set. A unit test asserts this symmetric difference mechanically, so a
# future edit to classify_pmu_qual cannot silently diverge the two classifiers.
PMU_CFG_SUBSTITUTED_OUT = frozenset({
    "build_id_is_hprintf",   # the CFG images are not the Q1 fixed build
    "is_case_a",             # the case is the variable, not a constant
    "cfg_no_write",          # replaced by a per-case write-count contract
    "cfg_pre_zero",          # replaced by a per-case expected final value
    "cfg_internal_zero",     # replaced by a per-case expected final value
})
PMU_CFG_SUBSTITUTED_IN = frozenset({
    "substitution_contract_intact",
    "cfg_manifest_case_coherent",
    "build_id_matches_case",
    "diag_case_matches_case",
    "cfg_write_count_ok",
    "cfg_write_value_ok",
    "cfg_readback_ok",
    "cfg_pre_matches_case",
    "cfg_internal_matches_case",
})

# What each case IS, held here and not taken from any manifest. The manifest
# declares the same numbers, but a manifest is evidence ABOUT a build, never a
# licence to redefine what A/B/C mean: an "A" that declares one write, a "B"
# that declares a zero value or a "C" that declares a non-zero one describe a
# case that does not exist, and the record they would otherwise accept is not
# interpretable. The declared numbers are therefore compared with these, and
# these -- never the declared ones -- are what the record is judged against.
PMU_CFG_INTRINSIC_WRITE_COUNT = {"A": 0, "B": 1, "C": 1}


def pmu_cfg_manifest_case(expected_manifest: dict) -> str | None:
    case = expected_manifest.get("cfg_case")
    return case if case in PMU_CFG_CASES else None


def _pmu_cfg_hex(raw) -> int | None:
    """Manifest values are JSON hex strings. Unparseable yields None, which can
    never equal an observed register value."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    try:
        return int(str(raw), 16)
    except (TypeError, ValueError):
        return None


def pmu_cfg_case_contract(expected_manifest: dict) -> dict:
    """The intrinsic contract of the manifest's case, and whether the manifest
    agrees with it.

    ``manifest_coherent`` is False for any manifest that is not a possible
    description of its own case, so a semantically impossible document can
    never make a record valid -- not even one whose registers happen to match
    what that document asked for.

    The one thing that legitimately comes FROM the manifest is case B's
    generated value: its exact encoding is a property of the build and is
    attested by the ELF gate. The host can only require that it exists, parses
    and is non-zero -- a zero there would be case C wearing case B's name.
    """
    case = pmu_cfg_manifest_case(expected_manifest)
    contract = {
        "case": case,
        "write_count": None,
        "written_value": None,
        "final_value": None,
        "declared_write_count": expected_manifest.get("cfg_expected_write_count"),
        "manifest_coherent": False,
    }
    if case is None:
        return contract

    want_count = PMU_CFG_INTRINSIC_WRITE_COUNT[case]
    contract["write_count"] = want_count
    raw = expected_manifest.get("cfg_expected_value")
    parsed = None if raw is None else _pmu_cfg_hex(raw)

    if case == "A":
        # Nothing is written, so there is no value to declare. A declared one
        # describes a write this case does not perform.
        value_ok = raw is None
        contract["final_value"] = 0
    elif case == "B":
        value_ok = parsed is not None and parsed != 0
        contract["written_value"] = parsed if value_ok else None
        contract["final_value"] = contract["written_value"]
    else:  # C: an explicit zero is the whole point of the case
        value_ok = parsed == 0
        contract["written_value"] = 0 if value_ok else None
        contract["final_value"] = 0 if value_ok else None

    contract["manifest_coherent"] = bool(
        value_ok
        and contract["declared_write_count"] == want_count
        and expected_manifest.get("cfg_case_id") == PMU_CFG_CASE_IDS[case])
    return contract


def pmu_cfg_expected_final_value(expected_manifest: dict) -> int | None:
    """The PMCCNTR_CFG value the register must END at for this case.

    Case A never writes and case C writes an explicit zero, so both end at 0.
    Case B ends at its own attested generated value. None whenever the
    manifest is not a coherent description of its case.
    """
    contract = pmu_cfg_case_contract(expected_manifest)
    return contract["final_value"] if contract["manifest_coherent"] else None


def classify_pmu_cfg(res: PmuQualResult, expected_manifest: dict) -> dict:
    """Case-aware verdict for a CFG A/B/C characterization record.

    The COMMON validity rules are not restated here: classify_pmu_qual() is
    called to compute them, and only the five terms in
    PMU_CFG_SUBSTITUTED_OUT are removed and replaced by the nine in
    PMU_CFG_SUBSTITUTED_IN. Everything else -- hook contract, LR against this
    case's own manifest, power-held, MMIO subset, start boundary, snapshot
    state, overflow, positive delta, disable acknowledgement, vendor release,
    golden window, run rc and required flags -- is inherited from the same
    code the qualification gate uses.

    npu_pmu_window_cycles is published only when EVERY term holds, and keeps
    exactly that name. after_return remains corroboration only.
    """
    base = classify_pmu_qual(res, expected_manifest)
    terms = dict(base["terms"])
    # A base term that is not there was not removed, and its replacement would
    # then be judging a rule nobody stated. Absence is a substitution this
    # classifier no longer describes, so it fails the sample rather than
    # silently narrowing the contract -- which is what pop(name, None) did.
    missing_base_terms = sorted(PMU_CFG_SUBSTITUTED_OUT - set(terms))
    for name in PMU_CFG_SUBSTITUTED_OUT & set(terms):
        del terms[name]

    contract = pmu_cfg_case_contract(expected_manifest)
    case = contract["case"]
    want_count = contract["write_count"]
    want_final = contract["final_value"]
    # Case A writes nothing, so the recorded value must stay zero; B and C must
    # have written exactly the value their own case requires.
    want_written = 0 if case == "A" else contract["written_value"]

    terms["substitution_contract_intact"] = not missing_base_terms
    # An impossible manifest cannot be repaired by a matching record.
    terms["cfg_manifest_case_coherent"] = contract["manifest_coherent"]
    terms["build_id_matches_case"] = (
        case is not None and res.build_id == PMU_CFG_BUILD_IDS[case])
    terms["diag_case_matches_case"] = (
        case is not None and res.diag_case == PMU_CFG_CASE_IDS[case])
    # Judged against the INTRINSIC count for the case, never the declared one.
    terms["cfg_write_count_ok"] = (
        want_count is not None and res.cfg_write_performed == want_count)
    terms["cfg_write_value_ok"] = (
        want_written is not None and res.cfg_write_value == want_written)
    terms["cfg_readback_ok"] = (
        want_written is not None
        and res.cfg_readback_after_write == want_written)
    terms["cfg_pre_matches_case"] = (
        want_final is not None and res.pre.pmccntr_cfg == want_final)
    terms["cfg_internal_matches_case"] = (
        want_final is not None
        and res.internal_pre_release.pmccntr_cfg == want_final)

    valid = all(terms.values())
    return {
        "characterization_only": True,
        "not_a_performance_baseline": True,
        "cfg_case": case,
        "cfg_expected_write_count": want_count,
        "cfg_manifest_declared_write_count": contract["declared_write_count"],
        "cfg_expected_write_value": contract["written_value"],
        "cfg_expected_final_value": want_final,
        "substitution_missing_base_terms": missing_base_terms,
        "terms": terms,
        "invalid_reasons": sorted(k for k, v in terms.items() if not v),
        "raw_delta_diagnostic": base["raw_delta_diagnostic"],
        "reset_to_zero": base["reset_to_zero"],
        "npu_pmu_window_cycles": base["raw_delta_diagnostic"] if valid else None,
        "valid": valid,
        # STATUS at the hook instant is NOT recorded by this image. The two
        # surrounding observations are archived instead and this limitation is
        # declared rather than papered over.
        "status_bracket": {
            "npu_status_after_power_request": res.npu_status_after_power_request,
            "npu_status_after_seam": res.npu_status_after_seam,
            "limitation": "no npu_status_at_hook field exists in schema v8; "
                          "hook-instant STATUS is bracketed, not observed",
        },
    }
