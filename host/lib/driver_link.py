"""Host link to the driver runner (firmware/driver_runner): the legacy wire protocol of runner_proto.RunnerLink, with
record v2 in RUN_COMPLETE and the driver runner's own requests."""
from __future__ import annotations

import struct

import record_v2
import runner_proto

CMD_GET_CAPABILITIES = 0x03
CMD_SET_RUN_OPTIONS = 0x06
WAIT_WFE, WAIT_BUSY = 0, 1


class DriverLink(runner_proto.RunnerLink):
    def __init__(self, port: str, baud: int = 115200) -> None:
        super().__init__(port, baud, protocol=runner_proto.PROTO_MEASURE_V2)

    def _decode(self, payload: bytes) -> record_v2.Record:
        return record_v2.parse(payload)

    def capabilities(self) -> dict:
        return record_v2.parse_capabilities(self.request(CMD_GET_CAPABILITIES).payload)

    def set_run_options(self, wait_mode: int = WAIT_WFE, pmccntr_cfg: int = 0) -> tuple[int, int]:
        f = self.request(CMD_SET_RUN_OPTIONS, struct.pack("<III", wait_mode, pmccntr_cfg, 0))
        return struct.unpack_from("<II", f.payload)
