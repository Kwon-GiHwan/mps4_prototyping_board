#!/usr/bin/env python3
"""POST_HOC_DESCRIPTIVE for the QREAD pilot (boots 325-326, TA profile 1): the owner's five questions, answered from the
raw traces after the contract verdicts (all TRACE_INVALID) were fixed. Nothing here changes a verdict or corrects data.

Two post-hoc views, each named in the output:
  as_recorded  every stored sample
  usable       a RUN only if, after dropping its first sample when that sample still shows the previous RUN's stream end
               (QREAD = stream length before the new job reset it), the integrity checks pass; RUNs with any other
               problem (QREAD read outside the stream, counters decreasing) are counted, not repaired.

  python3 results/qread_pilot/describe.py   (from the repo root) -> results/qread_pilot/describe.json
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host" / "lib"), str(REPO / "host" / "analysis")]
import qread_timeline as T  # noqa: E402
import qread_trace as Q  # noqa: E402

RAW = REPO / "evidence/qread_pilot/raw/conds"
MODELS = ("rnnoise_INT8", "yolo-fastest_192_face_v4")
CONDS = ("t06", "t10", "t14", "p10")
WARMUP = 1


def traces(model: str, cond: str):
    d = RAW / model / cond
    for r in json.loads((d / "raw_runs.json").read_text())[1:]:
        if r["rep"] <= WARMUP:
            continue
        b = (d / "traces" / f"set{r['set_id']}_rep{r['rep']}.bin").read_bytes()
        yield r, Q.parse([int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)],
                         Q.header_from_record(r["record"]))


def usable(t: Q.Trace, cms_len: int) -> tuple[Q.Trace | None, list[str]]:
    s = t.samples[1:] if t.samples and t.samples[0].qread_before == cms_len else t.samples
    u = Q.Trace(t.config, s, t.dropped, t.polls - (len(t.samples) - len(s)), t.hook_calls)
    p = Q.integrity(u, cms_len)
    return (u if not p else None), p


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def per_run(t: Q.Trace, cm: T.CommandMap, record: dict) -> dict:
    bs = T.brackets(t, cm)
    widths = [T.Q.elapsed(b.lo, b.hi) for b in bs if b.lo is not None and b.hi is not None]
    firsts = [b.first_past for b in bs]
    groups = [firsts.count(f) for f in sorted(set(f for f in firsts if f is not None))]
    gaps = [Q.elapsed(a.t_before, b.t_before) for a, b in zip(t.samples, t.samples[1:])]
    cost = [Q.elapsed(s.t_before, s.t_after) for s in t.samples]
    distinct = sorted({s.qread_after for s in t.samples})
    stops = [o for o in distinct if 0 < o < cm.cms_len]
    out = dict(resolved_ratio=T.resolved_ratio(bs), kernels=len(cm.kernels), samples=len(t.samples),
               distinct_qread=len(distinct), kernels_per_first_sight_max=max(groups, default=0),
               kernels_per_first_sight_median=med(groups),
               bracket_cycles_median=med(widths), bracket_cycles_max=max(widths, default=None),
               sample_gap_median=med(gaps), read_cycles_median=med(cost), read_cycles_max=max(cost, default=None),
               polls=t.polls, hook_calls=t.hook_calls,
               qread_stops_on_kernel_instruction=sum(o in {k.offset for k in cm.kernels} for o in stops),
               qread_stops_right_after_kernel=sum(o - 4 in {k.offset for k in cm.kernels} for o in stops),
               qread_stops=len(stops))
    if t.config.mode == Q.MODE_QREAD_PMU:
        codes = [record[f"event_code{i}"] for i in range(len(t.samples[0].events))]
        mac = codes.index(48) if 48 in codes else None
        stalled = moving = 0
        mac_in_stall = mac_total = 0
        for a, b in zip(t.samples, t.samples[1:]):
            dm = b.events[mac] - a.events[mac] if mac is not None else 0
            mac_total += dm
            if b.qread_after == a.qread_after:
                stalled += 1
                mac_in_stall += dm
            else:
                moving += 1
        out.update(intervals_qread_stalled=stalled, intervals_qread_moved=moving,
                   mac_active_share_while_qread_stalled=(mac_in_stall / mac_total) if mac_total else None)
    return out


def main() -> dict:
    res = {}
    for m in MODELS:
        cm = T.CommandMap.from_stream((REPO / f"evidence/qread_pilot/workloads/{m}.drwl.cms.bin").read_bytes())
        for c in CONDS:
            rows, problems, first_stale = [], {}, 0
            for r, t in traces(m, c):
                first_stale += t.samples[0].qread_before == cm.cms_len
                u, p = usable(t, cm.cms_len)
                if u is None:
                    for x in p:
                        problems[x] = problems.get(x, 0) + 1
                    continue
                rows.append(per_run(u, cm, r["record"]))
            keys = rows[0].keys() if rows else []
            res[f"{m}/{c}"] = dict(measured_runs=4, first_sample_shows_previous_end=first_stale,
                                   usable_runs=len(rows), problems_in_other_runs=problems,
                                   **{k: med([x[k] for x in rows]) for k in keys})
    (REPO / "results/qread_pilot/describe.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
