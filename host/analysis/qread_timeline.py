#!/usr/bin/env python3
"""Command completion progress timeline from a driver-runner QREAD trace (docs/plan/driver_profiling_design.md;
ported from feat/stage2b4-qread 65d3f8b, docs/plan/stage2b4_qread_plan.md there; the analysis is unchanged, only the
input is the driver runner's). TA profile 1.

  python3 host/analysis/qread_timeline.py <model.drwl.cms.bin> <boot dir> <out dir>

<model.drwl.cms.bin> = the command stream the packer writes beside a DRWL (its sha256 = the DRWL meta cms_sha256).
<boot dir> = one run_driver_events.py output with traces/set<S>_rep<R>.bin and raw_runs.json. Per RUN: progress.csv
(one row per stored sample), brackets.csv (per kernel op: when QREAD was seen passing its kernel instruction),
deltas.csv (per consecutive sample pair: Δt, ΔQREAD, Δevent), and summary.json.

QREAD is the completion position: commands before QBASE+QREAD are complete (TRM). Kernel op k (a one-word cmd0 at
byte offset o_k) is marked complete once QREAD > o_k. A bracket (lo, hi] bounds the time QREAD passed o_k:
lo = t_before of the last sample that read QREAD <= o_k, hi = t_after of the first sample that read QREAD > o_k.
It bounds when completion became visible; the op itself may have finished earlier (an earlier incomplete command
holds QREAD back) and its start time is not observable. None of this attributes PMU counts to an op.
"""
from __future__ import annotations

import bisect
import csv
import json
import pathlib
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms_timeline  # noqa: E402
import qread_trace as Q  # noqa: E402

# Proposed observation bounds (plan §8); the board contract freezes them before any trace data exists.
RESOLVED_LOW, RESOLVED_HIGH = 0.10, 0.90
VERDICTS = ("TRACE_INVALID", "TRACE_PERTURBED", "TRACE_UNOBSERVABLE", "TRACE_COARSE", "TRACE_VALID", "UNPROVEN")


@dataclass(frozen=True)
class Kernel:
    index: int
    offset: int
    type: str
    macs: int


class CommandMap:
    """Kernel ops of one command stream, by the byte offset of their kernel instruction."""

    def __init__(self, kernels: list[Kernel], cms_len: int) -> None:
        self.kernels = kernels
        self.cms_len = cms_len
        self._offsets = [k.offset for k in kernels]

    @classmethod
    def from_stream(cls, stream: bytes) -> CommandMap:
        rows = cms_timeline.timeline(stream)
        return cls([Kernel(r["index"], r["offset"], r["type"], r["macs"]) for r in rows], len(stream))

    def completed(self, qread: int) -> int:
        """Kernel ops marked complete at this QREAD (their instruction lies before it)."""
        return bisect.bisect_left(self._offsets, qread)


@dataclass(frozen=True)
class Bracket:
    kernel: int
    lo: int | None     # t_before of the last sample still before the op's instruction
    hi: int | None     # t_after of the first sample past it
    first_past: int | None   # index of that sample


def progress(trace: Q.Trace, cmap: CommandMap) -> list[dict]:
    t0 = trace.samples[0].t_before if trace.samples else 0
    rows, done = [], 0
    for i, s in enumerate(trace.samples):
        now = cmap.completed(s.qread_after)
        rows.append(dict(sample=i, t_before=Q.elapsed(t0, s.t_before), t_after=Q.elapsed(t0, s.t_after),
                         qread=s.qread_after, moved_during_read=int(s.qread_before != s.qread_after),
                         kernels_complete=now, newly_complete=now - done, status=f"0x{s.status:08x}"))
        done = now
    return rows


def brackets(trace: Q.Trace, cmap: CommandMap) -> list[Bracket]:
    out = []
    for k in cmap.kernels:
        before = [s.t_before for s in trace.samples if s.qread_before <= k.offset]
        past = [i for i, s in enumerate(trace.samples) if s.qread_after > k.offset]
        first = past[0] if past else None
        out.append(Bracket(k.index, before[-1] if before else None,
                           trace.samples[first].t_after if first is not None else None, first))
    return out


def resolved_ratio(bs: list[Bracket]) -> float:
    """Share of kernel ops whose completion was first seen alone: bounded on both sides and by a sample that no
    neighbouring op shares."""
    if not bs:
        return 0.0
    firsts = [b.first_past for b in bs]
    ok = 0
    for i, b in enumerate(bs):
        alone = all(firsts[j] != b.first_past for j in (i - 1, i + 1) if 0 <= j < len(bs))
        ok += b.lo is not None and b.hi is not None and alone
    return ok / len(bs)


def deltas(trace: Q.Trace, cmap: CommandMap, codes: list[int | None]) -> list[dict]:
    """codes: the event code of each slot in sample order; None (slot not valid in the record, e.g. overflowed) keeps
    its place and is labelled by slot, so later columns never shift."""
    rows = []
    for i, (a, b) in enumerate(zip(trace.samples, trace.samples[1:])):
        row = dict(sample=i + 1, dt=Q.elapsed(a.t_before, b.t_before), dqread=b.qread_after - a.qread_after,
                   kernels_complete=cmap.completed(b.qread_after), qread_stalled=int(b.qread_after == a.qread_after))
        for slot, (code, x, y) in enumerate(zip(codes, a.events, b.events)):
            row[f"d_ev{code}" if code is not None else f"d_slot{slot}"] = y - x
        rows.append(row)
    return rows


def verdict(problems: list[str], perturbed: bool | None, ratio: float,
            low: float = RESOLVED_LOW, high: float = RESOLVED_HIGH) -> str:
    """Priority INVALID > PERTURBED > UNOBSERVABLE > COARSE > VALID. perturbed None (not judged against the
    BASELINE arm yet) leaves a consistent trace UNPROVEN. TRACE_VALID is not exact attribution."""
    if problems:
        return "TRACE_INVALID"
    if perturbed is None:
        return "UNPROVEN"
    if perturbed:
        return "TRACE_PERTURBED"
    if ratio < low:
        return "TRACE_UNOBSERVABLE"
    if ratio < high:
        return "TRACE_COARSE"
    return "TRACE_VALID"


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def analyse_run(trace: Q.Trace, cmap: CommandMap, codes: list[int], out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    bs = brackets(trace, cmap)
    write_csv(out / "progress.csv", progress(trace, cmap))
    write_csv(out / "brackets.csv", [dict(kernel=b.kernel, offset=k.offset, type=k.type, macs=k.macs, lo=b.lo,
                                          hi=b.hi, first_past=b.first_past)
                                     for b, k in zip(bs, cmap.kernels)])
    write_csv(out / "deltas.csv", deltas(trace, cmap, codes))
    problems = Q.integrity(trace, cmap.cms_len)
    ratio = resolved_ratio(bs)
    cost = [Q.elapsed(s.t_before, s.t_after) for s in trace.samples]
    return dict(samples=len(trace.samples), polls=trace.polls, hook_calls=trace.hook_calls, dropped=trace.dropped,
                problems=problems, resolved_ratio=ratio, verdict_before_baseline=verdict(problems, None, ratio),
                read_cycles_max=max(cost, default=None), read_cycles_min=min(cost, default=None),
                distinct_qread=len({s.qread_after for s in trace.samples}), kernels=len(cmap.kernels))


def slot_codes(record: dict, n: int) -> list[int | None]:
    """The event code of each traced slot; an overflowed slot keeps its place as None."""
    return [None if record["ovf_irq"] >> i & 1 else record[f"event_code{i}"] for i in range(n)]


def main(cms_path: str, boot: str, out: str) -> dict:
    cmap = CommandMap.from_stream(pathlib.Path(cms_path).read_bytes())
    boot_dir, out_dir = pathlib.Path(boot), pathlib.Path(out)
    summary = {}
    for r in json.loads((boot_dir / "raw_runs.json").read_text()):
        if "record" not in r:
            continue
        name = f"set{r['set_id']}_rep{r['rep']}"
        header = Q.header_from_record(r["record"])
        tf = boot_dir / "traces" / f"{name}.bin"
        if header["trace_config"] == Q.OFF or not tf.exists():
            summary[name] = dict(verdict="TRACE_INVALID", problems=["no_trace"])
            continue
        raw = tf.read_bytes()
        words = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]
        try:
            trace = Q.parse(words, header)
        except ValueError as e:
            summary[name] = dict(verdict="TRACE_INVALID", problems=[f"unparsable: {e}"])
            continue
        n = header["trace_words_per_sample"] - Q.BASE_SAMPLE_WORDS
        summary[name] = analyse_run(trace, cmap, slot_codes(r["record"], n), out_dir / name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), indent=1))
