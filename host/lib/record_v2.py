"""Driver runner record v2 (RUN_COMPLETE) and capabilities (GET_CAPABILITIES), docs/plan/driver_runner_plan.md 2.3.

The firmware declares the same field lists independently (firmware/driver_runner/use_case/pmu_runner/include/record.h,
caps.h); host/tests/test_driver_runner_contract.py parses those X-macro lists and requires them to equal these.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import runner_proto

MAGIC = 0x32454D52        # 'RME2'
ABI_VERSION = 2
HEADER_WORDS = 8
SCHEMA = 4                # 3: trace_words .. trace_id (checked trace modes); 4: regioncfg_irq .. placement
CAPS_MAGIC = 0x31435244   # 'DRC1'


def _eight(prefix: str) -> list[str]:
    return [f"{prefix}{i}" for i in range(8)]


FIELDS_V3 = (["schema", "build_id", "instr_mode", "event_set_id", "event_count"] + _eight("event_code")
          + ["config_seq", "wait_mode", "pmccntr_cfg", "dcache_on", "invoke_ok", "job_result", "irq_count",
             "arm_count", "power_requests", "status_at_irq", "qread_at_irq", "qsize", "pmcr_at_arm", "cnten_at_arm",
             "ccnt_irq_lo", "ccnt_irq_hi"] + _eight("ev_irq")
          + ["ovf_irq", "ccnt_post_lo", "ccnt_post_hi"] + _eight("ev_post")
          + ["ovf_post", "dwt_invoke", "dwt_arm", "dwt_irq", "dwt_return", "ofm_mismatch", "ofm_max_diff", "ofm_first",
             "model_base", "model_len", "arena_base", "arena_len", "n_base"] + _eight("base") + _eight("base_size")
          + ["samples", "sample_dropped", "trace_config", "trace_words_per_sample", "trace_polls", "trace_hook_calls",
             "trace_words", "trace_rejected", "trace_unaccepted", "trace_id"])
FIELDS = FIELDS_V3 + ["regioncfg_irq", "qconfig_irq", "placement"]
SCHEMA_FIELDS = {3: FIELDS_V3, 4: FIELDS}   # schema 3: images before the placement fields (83398c7 and earlier)

TA11 = ("maxr", "maxw", "maxrw", "rlatency", "wlatency", "pulse_on", "pulse_off", "bwcap", "perfctrl", "mode",
        "histbin")
CAPS_FIELDS = (["magic", "schema", "build_id", "record_fields", "driver_version", "npu_id", "npu_config",
                "power_requests", "pmcr", "scb_ccr", "fast_base", "fast_size", "model_base", "ddr_limit",
                "staging_base", "staging_size", "arena_len", "load_status", "ta_sram_version", "ta_ext_version"]
               + [f"ta_sram_{n}" for n in TA11] + [f"ta_ext_{n}" for n in TA11]
               + ["cfg_sram_cap", "cfg_ext_cap", "axi_sram", "axi_ext", "mem_attr0", "mem_attr1", "mem_attr2",
                  "mem_attr3", "power_ctrl", "regioncfg", "qconfig"])

# valid_flags (record.h)
COMPLETED, INVOKE_OK, ONE_ARM, ONE_IRQ, NO_OVERFLOW, OUTPUT_MATCH, REGIONCFG_MATCH = (1 << i for i in range(7))
REQUIRED = COMPLETED | INVOKE_OK | ONE_ARM | ONE_IRQ | NO_OVERFLOW
U32 = 1 << 32


@dataclass(frozen=True)
class Record:
    run_sequence: int
    valid_flags: int
    run_rc: int
    f: dict

    def events(self) -> list[tuple[int, int]]:
        """(event code, value at the IRQ) of the armed slots."""
        return [(self.f[f"event_code{i}"], self.f[f"ev_irq{i}"]) for i in range(self.f["event_count"])]

    def npu_execution_cycles(self) -> int:
        """PMCCNTR from the arm (right before the NPU start) to the completion IRQ's entry."""
        return self.f["ccnt_irq_lo"] | self.f["ccnt_irq_hi"] << 32

    def npu_execution_dwt(self) -> int:
        return (self.f["dwt_irq"] - self.f["dwt_arm"]) % U32

    def host_end_to_end(self) -> int:
        return (self.f["dwt_return"] - self.f["dwt_invoke"]) % U32


def parse(payload: bytes) -> Record:
    """Validates header, size and CRC (the v1 rule), then names every field. Schema 3 (no placement fields) and 4."""
    if len(payload) < 4 * HEADER_WORDS:
        raise runner_proto.ProtocolError("record v2 shorter than its header")
    magic, ver, total, hw, seq, flags, rc, crc = struct.unpack_from("<8I", payload)
    if magic != MAGIC or ver != ABI_VERSION or hw != HEADER_WORDS:
        raise runner_proto.ProtocolError(f"not a v2 record (magic 0x{magic:08x}, version {ver}, header {hw})")
    known = {HEADER_WORDS + len(v): s for s, v in SCHEMA_FIELDS.items()}
    if total not in known or len(payload) != 4 * total:
        raise runner_proto.ProtocolError(f"record v2 of {total} words / {len(payload)} bytes, "
                                         f"this host knows {sorted(known)} words")
    if runner_proto.measurement_payload_crc(payload, total) != crc:
        raise runner_proto.ProtocolError("record v2 CRC mismatch")
    names = SCHEMA_FIELDS[known[total]]
    f = dict(zip(names, struct.unpack_from(f"<{len(names)}I", payload, 4 * HEADER_WORDS)))
    if f["schema"] != known[total]:
        raise runner_proto.ProtocolError(f"record schema {f['schema']} in a {total}-word record")
    return Record(seq, flags, rc, f)


def parse_capabilities(payload: bytes) -> dict:
    if len(payload) != 4 * len(CAPS_FIELDS):
        raise runner_proto.ProtocolError(f"capabilities of {len(payload)} bytes, expected {4 * len(CAPS_FIELDS)}")
    c = dict(zip(CAPS_FIELDS, struct.unpack(f"<{len(CAPS_FIELDS)}I", payload)))
    if c["magic"] != CAPS_MAGIC:
        raise runner_proto.ProtocolError(f"capabilities magic 0x{c['magic']:08x}")
    return c


def validity(r: Record, codes: list[int]) -> tuple[bool, list[str]]:
    """Measurement validity of one RUN (the driver runner's counterpart of pmu_events_parse.run_validity): every
    required flag, the driver's job result OK, the armed codes echo the request. Output equality is reported apart
    (ofm_mismatch), as in the legacy 'model' mode. Schema 4 adds: REGIONCFG/QCONFIG read at the IRQ equal the
    workload's placement (regioncfg_match)."""
    failed = [name for name, bit in (("completed", COMPLETED), ("invoke_ok", INVOKE_OK), ("one_arm", ONE_ARM),
                                     ("one_irq", ONE_IRQ), ("no_overflow", NO_OVERFLOW)) if not r.valid_flags & bit]
    if r.f["schema"] >= 4 and not r.valid_flags & REGIONCFG_MATCH:
        failed.append("regioncfg_match")
    if r.f["job_result"] != 0:
        failed.append("job_result")
    if [c for c, _ in r.events()] != list(codes):
        failed.append("codes_echo")
    if r.run_rc != 0:
        failed.append("run_rc")
    return not failed, failed
