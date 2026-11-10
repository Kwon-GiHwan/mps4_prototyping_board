"""QREAD trace of the driver runner (docs/plan/driver_profiling_design.md §2): trace word, buffer layout, parsing and
integrity checks. Ported from `feat/stage2b4-qread` 65d3f8b (the legacy runner's 2B-4 layout, unchanged); what was tied
to the legacy runner (PMWL knob word 31, record trailing fields) is replaced by SET_RUN_OPTIONS word 2 and the named
record v2 fields.

The firmware declares the same layout independently (firmware/driver_runner/use_case/pmu_runner/include/trace.h);
host/tests/test_driver_runner_contract.py asserts the two agree. Neither imports the other.

Trace word: bits 3:0 mode (1 QREAD_ONLY, 2 QREAD_PMU), bits 11:8 poll interval 2^n CPU cycles, bits 19:16 store policy
(0 = every poll; n >= 1 = only when QREAD changed or 2^n cycles since the last stored sample); OFF = 0xFFFFFFFF.
Sample (u32 words): t_before, qread_before, status, event_0 .. event_{N-1}, qread_after, t_after; t = DWT CYCCNT,
N = 0 in QREAD_ONLY, the RUN's event count in QREAD_PMU. The last sample is taken after the completion IRQ.
QREAD is the command completion position (TRM), not an operator start or end time.
"""
from __future__ import annotations

from dataclasses import dataclass

OFF = 0xFFFFFFFF
MODE_QREAD_ONLY, MODE_QREAD_PMU = 1, 2
MODE_QREAD_CHECKED, MODE_QREAD_PMU_CHECKED = 3, 4
CHECKED_MODES = (MODE_QREAD_CHECKED, MODE_QREAD_PMU_CHECKED)
MODE_MASK, INTERVAL_SHIFT, STORE_SHIFT, FIELD_MASK = 0xF, 8, 16, 0xF
CONFIG_MASK = MODE_MASK | FIELD_MASK << INTERVAL_SHIFT | FIELD_MASK << STORE_SHIFT
BASE_SAMPLE_WORDS = 5          # t_before, qread_before, status, qread_after, t_after
BUFFER_WORDS = 32768           # firmware static buffer
GET_TRACE_MAX_WORDS = 1000     # words per GET_TRACE reply
CMD_GET_TRACE = 0x41
# record v2 field -> trace header key
RECORD_FIELDS = {"trace_config": "trace_config", "trace_words_per_sample": "trace_words_per_sample",
                 "samples": "trace_samples", "sample_dropped": "trace_dropped", "trace_polls": "trace_polls",
                 "trace_hook_calls": "trace_hook_calls"}
# checked modes (record schema 3)
CHECKED_RECORD_FIELDS = {"trace_words": "trace_words", "trace_rejected": "trace_rejected",
                         "trace_unaccepted": "trace_unaccepted", "trace_id": "trace_id"}
CHECKED_MAGIC = 0x5A
CHECK_SEED = 0xA5A5A5A5
MAX_ATTEMPTS = 3
NPU_OFF_ID, NPU_OFF_STATUS, NPU_OFF_QREAD, NPU_OFF_QSIZE = 0x00, 0x04, 0x18, 0x20
NPU_REG_PMEVCNTR_BASE = 0x1300
U32 = 1 << 32


@dataclass(frozen=True)
class TraceConfig:
    mode: int
    interval_log2: int = 0
    store_log2: int = 0

    def __post_init__(self) -> None:
        if self.mode not in (MODE_QREAD_ONLY, MODE_QREAD_PMU) + CHECKED_MODES:
            raise ValueError(f"trace mode {self.mode}: 1 (QREAD_ONLY), 2 (QREAD_PMU), 3/4 (the same, checked)")
        for name in ("interval_log2", "store_log2"):
            if not 0 <= getattr(self, name) <= FIELD_MASK:
                raise ValueError(f"{name} {getattr(self, name)} outside 0..{FIELD_MASK}")

    def word(self) -> int:
        return self.mode | self.interval_log2 << INTERVAL_SHIFT | self.store_log2 << STORE_SHIFT

    def words_per_sample(self, n_events: int) -> int:
        """Legacy modes: the fixed sample size; checked modes: the nominal one (every slot accepted at once)."""
        if self.mode in CHECKED_MODES:
            return 4 + (3 + (n_events if self.mode == MODE_QREAD_PMU_CHECKED else 0)) * 3
        return BASE_SAMPLE_WORDS + (n_events if self.mode == MODE_QREAD_PMU else 0)


def config_from_word(word: int) -> TraceConfig | None:
    """Trace word -> TraceConfig, None for OFF. Refuses what the firmware refuses."""
    if word == OFF:
        return None
    if word & ~CONFIG_MASK:
        raise ValueError(f"trace word 0x{word:08x} sets reserved bits")
    return TraceConfig(word & MODE_MASK, word >> INTERVAL_SHIFT & FIELD_MASK, word >> STORE_SHIFT & FIELD_MASK)


@dataclass(frozen=True)
class Sample:
    t_before: int
    qread_before: int
    status: int
    events: tuple[int, ...]
    qread_after: int
    t_after: int


@dataclass(frozen=True)
class Trace:
    config: TraceConfig
    samples: tuple[Sample, ...]
    dropped: int
    polls: int
    hook_calls: int


def header_from_record(fields: dict) -> dict:
    """The trace header of one RUN from its record v2 fields (record_v2.Record.f); schema 3 adds the checked fields."""
    names = dict(RECORD_FIELDS, **{k: v for k, v in CHECKED_RECORD_FIELDS.items() if k in fields})
    return {key: fields[name] for name, key in names.items()}


def n_words(header: dict) -> int:
    """Buffer words to fetch with GET_TRACE for this RUN."""
    cfg = config_from_word(header["trace_config"])
    if cfg is not None and cfg.mode in CHECKED_MODES:
        return header["trace_words"]
    return header["trace_words_per_sample"] * header["trace_samples"]


def parse(words, header: dict) -> Trace:
    """Trace buffer words (GET_TRACE) + the record's trace header -> Trace. Refuses a layout that does not add up."""
    cfg = config_from_word(header["trace_config"])
    if cfg is None:
        raise ValueError("trace was off for this RUN")
    wps, n = header["trace_words_per_sample"], header["trace_samples"]
    if wps < BASE_SAMPLE_WORDS or (cfg.mode == MODE_QREAD_ONLY and wps != BASE_SAMPLE_WORDS):
        raise ValueError(f"{wps} words per sample for mode {cfg.mode}")
    if len(words) != wps * n:
        raise ValueError(f"{len(words)} trace words for {n} samples of {wps}")
    ne = wps - BASE_SAMPLE_WORDS
    samples = tuple(Sample(w[0], w[1], w[2], tuple(w[3:3 + ne]), w[3 + ne], w[4 + ne])
                    for w in (words[i * wps:(i + 1) * wps] for i in range(n)))
    return Trace(cfg, samples, header["trace_dropped"], header["trace_polls"], header["trace_hook_calls"])


def elapsed(t0: int, t: int) -> int:
    """DWT CYCCNT difference modulo 2^32 (the counter wraps; a gap is assumed < 2^31 cycles)."""
    return (t - t0) % U32


def integrity(trace: Trace, cms_len: int) -> list[str]:
    """Every failed consistency check, by name; empty = consistent. Unlike the legacy runner's check, zero wait-loop
    calls is not a failure here: an NPU that finishes before the driver starts waiting leaves only the final sample."""
    out = []
    s = trace.samples
    if not s:
        out.append("no_samples")
    if trace.dropped:
        out.append("buffer_overflow")
    if len(s) + trace.dropped > trace.polls:
        out.append("more_samples_than_polls")
    if trace.polls > trace.hook_calls + 1:   # every poll is a hook call, plus the one final sample after the IRQ
        out.append("more_polls_than_hook_calls")
    if s and s[-1].qread_after != cms_len:   # the final sample is taken after the completion IRQ
        out.append("final_qread_not_stream_end")
    t = [x for p in s for x in (p.t_before, p.t_after)]
    if any(elapsed(a, b) >= U32 // 2 for a, b in zip(t, t[1:])):
        out.append("time_not_monotonic")
    q = [x for p in s for x in (p.qread_before, p.qread_after)]
    if any(b < a for a, b in zip(q, q[1:])):
        out.append("qread_decreasing")
    if any(x > cms_len or x % 4 for x in q):
        out.append("qread_outside_stream")
    for a, b in zip(s, s[1:]):
        if any(y < x for x, y in zip(a.events, b.events)):
            out.append("event_counter_decreasing")
            break
    return out
