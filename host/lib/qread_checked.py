"""Checked QREAD trace (trace modes 3 and 4; Stage 2B operator-aware pilot, evidence/qread_op_pilot/contract.md):
parsing of the variable-length samples and the per-RUN trace class. Layout constants live in qread_trace.py; the
firmware declares them independently (trace.h) and host/tests/test_driver_runner_contract.py checks both.

Every register read of a checked sample is a pair (ID read, value read); a slot holds 1-3 such attempts, the first read
and at most two re-reads, and is accepted when the firmware found the last attempt plausible. Every attempt is kept, so
a rejected value is never lost and never replaced: `value` is the last attempt, `recovered` marks a slot accepted only
after a re-read.

Trace class of one RUN (the contract's P1 terms):
  TRACE_INVALID    a check failed: checksum, layout, an unaccepted slot, ID mismatch, an accepted QREAD out of the
                   stream / misaligned / decreasing, a counter decreasing, final QREAD != stream end, QSIZE != stream
                   length, buffer overflow, record counts that do not add up
  TRACE_RECOVERED  no failure, but at least one attempt was rejected and its slot accepted on a re-read
  TRACE_VALID      no failure and no rejected attempt
"""
from __future__ import annotations

from dataclasses import dataclass

import qread_trace as Q

VALID, RECOVERED, INVALID = "TRACE_VALID", "TRACE_RECOVERED", "TRACE_INVALID"


@dataclass(frozen=True)
class Slot:
    offset: int
    attempts: tuple[tuple[int, int], ...]   # (ID read, value read) in read order
    accepted: bool

    @property
    def value(self) -> int:
        return self.attempts[-1][1]

    @property
    def first_ok(self) -> bool:
        """Accepted at the first read."""
        return self.accepted and len(self.attempts) == 1


@dataclass(frozen=True)
class Sample:
    job: bool
    final: bool
    start: bool
    t_before: int
    t_after: int
    slots: tuple[Slot, ...]
    checksum_ok: bool

    def _q(self) -> tuple[Slot, ...]:
        return tuple(s for s in self.slots if s.offset == Q.NPU_OFF_QREAD)

    @property
    def qread_before(self) -> Slot:
        return self._q()[0]

    @property
    def qread_after(self) -> Slot:
        return self._q()[-1]

    @property
    def status(self) -> Slot:
        return next(s for s in self.slots if s.offset == Q.NPU_OFF_STATUS)

    @property
    def events(self) -> tuple[Slot, ...]:
        return tuple(s for s in self.slots if s.offset >= Q.NPU_REG_PMEVCNTR_BASE)

    @property
    def rejected(self) -> int:
        return sum(len(s.attempts) - s.accepted for s in self.slots)


@dataclass(frozen=True)
class Trace:
    config: Q.TraceConfig
    samples: tuple[Sample, ...]
    header: dict
    layout_errors: tuple[str, ...]          # what parse() found that does not add up (not raised: it is data)

    def job(self) -> tuple[Sample, ...]:
        """The measurement window: samples of the inference semaphore's wait, after the start (QSIZE) sample."""
        return tuple(s for s in self.samples if s.job and not s.start)

    def qsize(self) -> int | None:
        st = [s for s in self.samples if s.start]
        return st[0].slots[0].value if st and st[0].slots and st[0].slots[0].accepted else None


def expected_offsets(sample_start: bool, n_events: int) -> list[int]:
    if sample_start:
        return [Q.NPU_OFF_QSIZE]
    return ([Q.NPU_OFF_QREAD, Q.NPU_OFF_STATUS] + [Q.NPU_REG_PMEVCNTR_BASE + 4 * i for i in range(n_events)]
            + [Q.NPU_OFF_QREAD])


def parse(words: list[int], header: dict, n_events: int) -> Trace:
    """Buffer words of a checked-mode RUN -> Trace. A sample that does not parse ends the parse with a layout error."""
    cfg = Q.config_from_word(header["trace_config"])
    if cfg is None or cfg.mode not in Q.CHECKED_MODES:
        raise ValueError("not a checked-mode trace")
    ne = n_events if cfg.mode == Q.MODE_QREAD_PMU_CHECKED else 0
    out, errors, i = [], [], 0
    while i < len(words):
        h = words[i]
        if h >> 24 != Q.CHECKED_MAGIC:
            errors.append(f"bad_header_at_{i}")
            break
        n_slots, n_att = h >> 8 & 0xFF, h & 0xFF
        start = bool(h >> 21 & 1)
        j, slots = i + 2, []
        try:
            for _ in range(n_slots):
                d = words[j]
                a = d >> 16 & 0xF
                if not 1 <= a <= Q.MAX_ATTEMPTS:
                    raise IndexError
                pairs = tuple((words[j + 1 + 2 * k], words[j + 2 + 2 * k]) for k in range(a))
                slots.append(Slot(d & 0xFFFF, pairs, bool(d >> 20 & 1)))
                j += 1 + 2 * a
            t_after, check = words[j], words[j + 1]
        except IndexError:
            errors.append(f"truncated_sample_at_{i}")
            break
        x = Q.CHECK_SEED
        for w in words[i:j + 1]:
            x ^= w
        if sum(len(s.attempts) for s in slots) != n_att:
            errors.append(f"attempt_count_at_{i}")
        if [s.offset for s in slots] != expected_offsets(start, ne):
            errors.append(f"slot_layout_at_{i}")
        out.append(Sample(bool(h >> 23 & 1), bool(h >> 22 & 1), start, words[i + 1], t_after, tuple(slots), x == check))
        i = j + 2
    return Trace(cfg, tuple(out), dict(header), tuple(errors))


def problems(t: Trace, cms_len: int, npu_id: int) -> list[str]:
    """Every failed check of the trace (TRACE_INVALID causes), by name."""
    out = list(t.layout_errors)
    h, s, job = t.header, t.samples, t.job()
    if any(not x.checksum_ok for x in s):
        out.append("checksum")
    if h["trace_dropped"]:
        out.append("buffer_overflow")
    if h["trace_samples"] != len(s):
        out.append("sample_count")
    if h["trace_rejected"] != sum(x.rejected for x in s):
        out.append("rejected_count")
    if h["trace_unaccepted"] != 0 or any(not sl.accepted for x in s for sl in x.slots):
        out.append("unaccepted_read")
    if h["trace_id"] != npu_id:
        out.append("id_not_npu_id")
    if sum(x.start for x in s) != 1:
        out.append("start_sample_count")
    if t.qsize() != cms_len:
        out.append("qsize_not_stream_length")
    if not job:
        out.append("no_job_samples")
    else:
        if not job[-1].final or job[-1].qread_after.value != cms_len:
            out.append("final_qread_not_stream_end")
        q = [sl.value for x in job for sl in (x.qread_before, x.qread_after)]
        if any(b < a for a, b in zip(q, q[1:])):
            out.append("qread_decreasing")
        if any(v > cms_len or v % 4 for v in q):
            out.append("qread_outside_stream")
        for a, b in zip(job, job[1:]):
            if any(y.value < x.value for x, y in zip(a.events, b.events)):
                out.append("event_counter_decreasing")
                break
    tt = [v for x in s for v in (x.t_before, x.t_after)]
    if any(Q.elapsed(a, b) >= Q.U32 // 2 for a, b in zip(tt, tt[1:])):
        out.append("time_not_monotonic")
    if len(s) > h["trace_polls"] + 1:          # every sample is a poll, plus the job's start sample
        out.append("more_samples_than_polls")
    return out


def trace_class(t: Trace, cms_len: int, npu_id: int) -> tuple[str, list[str]]:
    p = problems(t, cms_len, npu_id)
    if p:
        return INVALID, p
    return (RECOVERED if any(x.rejected for x in t.samples) else VALID), []


def rejected_attempts(t: Trace) -> list[dict]:
    """Every rejected attempt with its context: which slot, the value, and whether it equals the read right before it
    (the ID read of the same attempt) or the previous slot's last value — the reappearance of an earlier read."""
    out = []
    for i, x in enumerate(t.samples):
        prev_val = None
        for k, sl in enumerate(x.slots):
            for a, (idr, v) in enumerate(sl.attempts):
                if a == len(sl.attempts) - 1 and sl.accepted:
                    continue
                out.append(dict(sample=i, job=x.job, slot=k, offset=sl.offset, attempt=a, id_read=idr, value=v,
                                value_is_id=v == t.header["trace_id"], id_read_ok=idr == t.header["trace_id"],
                                id_read_is_prev_value=prev_val is not None and idr == prev_val,
                                accepted_later=sl.accepted))
            prev_val = sl.value
    return out
