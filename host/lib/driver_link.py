"""Host link to the driver runner (firmware/driver_runner): the legacy wire protocol of runner_proto.RunnerLink, with
record v2 in RUN_COMPLETE and the driver runner's own requests."""
from __future__ import annotations

import struct

import record_v2
import runner_proto

CMD_GET_CAPABILITIES = 0x03
CMD_SET_RUN_OPTIONS = 0x06
CMD_GET_TRACE = 0x41
WAIT_WFE, WAIT_BUSY, WAIT_TRACE = 0, 1, 2
TRACE_OFF = 0xFFFFFFFF
TRACE_GET_MAX_WORDS = 1000


class DriverLink(runner_proto.RunnerLink):
    def __init__(self, port: str, baud: int = 115200) -> None:
        super().__init__(port, baud, protocol=runner_proto.PROTO_MEASURE_V2)

    def _decode(self, payload: bytes) -> record_v2.Record:
        return record_v2.parse(payload)

    def capabilities(self) -> dict:
        return record_v2.parse_capabilities(self.request(CMD_GET_CAPABILITIES).payload)

    def set_run_options(self, wait_mode: int = WAIT_WFE, pmccntr_cfg: int = 0,
                        trace_word: int = TRACE_OFF) -> tuple[int, int, int]:
        """trace_word: a qread_trace.TraceConfig word with WAIT_TRACE, TRACE_OFF otherwise (the runner refuses a mix)."""
        f = self.request(CMD_SET_RUN_OPTIONS, struct.pack("<III", wait_mode, pmccntr_cfg, trace_word))
        return struct.unpack_from("<III", f.payload)

    def get_trace(self, n_words: int) -> list[int]:
        """The last RUN's trace buffer (n_words = samples x words per sample from its record)."""
        out: list[int] = []
        while len(out) < n_words:
            f = self.request(CMD_GET_TRACE, struct.pack("<II", len(out), min(TRACE_GET_MAX_WORDS, n_words - len(out))))
            got = list(struct.unpack_from(f"<{len(f.payload) // 4}I", f.payload))
            if not got:
                raise runner_proto.ProtocolError(f"GET_TRACE stopped at word {len(out)} of {n_words}")
            out += got
        return out
