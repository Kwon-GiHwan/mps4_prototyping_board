#!/usr/bin/env python3
"""Stage 2B operator-aware QREAD pilot (contract evidence/qread_op_pilot/contract.md): yolo-fastest_192_face_v4, kernel
ops 99 (Conv2D) and 100 (Resize) of the original command stream, driver runner, TA profile 1, 1 warm-up + 4 measured
RUNs per condition and set. Conditions (run_driver_events.py --conditions, one folder each):

  base   WAIT_WFE, no trace                       sets 1-3   P1 baseline
  q06    WAIT_TRACE checked QREAD-only, poll 2^6  sets 1-3   P1, P2
  pbase  WAIT_WFE, no trace                       set 4      P3 baseline (second boot, only after P2 observed)
  p06    WAIT_TRACE checked QREAD+PMU, poll 2^6   set 4      P3

  python3 host/analysis/qread_op_pilot.py p12 <model dir> <cms.bin> <npu_id> <out> [warm-up]
  python3 host/analysis/qread_op_pilot.py p3  <model dir> <cms.bin> <npu_id> <out> <p12 summary.json> [warm-up]

Rules (fixed before the data):
  RUN       TRACE_INVALID if the RUN is not valid, its output differs from the golden, or the trace fails a check
            (qread_checked.problems); else TRACE_RECOVERED if any read was rejected and re-read; else TRACE_VALID
  P1        TRACE_INVALID if any measured q06 RUN is; else TRACE_PERTURBED if, in any set, the median NPU_ACTIVE (35)
            differs from base's by more than 1 %; else TRACE_RECOVERED if any RUN is; else TRACE_VALID
  P2        only when P1 is TRACE_VALID or TRACE_RECOVERED. Kernel op k at byte o_k is passed when QREAD > o_k.
            Bracket of k: lo = the last job sample with QREAD-before <= o_k, hi = the first with QREAD-after > o_k;
            observed when both exist and both of those QREAD reads were accepted at the first read (a recovered value
            never decides a boundary). Separated when some first-read QREAD r of the job has o_99 < r <= o_100.
            BOUNDARY_OBSERVED if every measured RUN observes both and separates them, else TRACE_VALID_COARSE
  P3        only when P2 is BOUNDARY_OBSERVED. p06 RUNs by the RUN rule (counters included); P1's perturbation rule
            against pbase; P2's boundary rule on p06; resolution kept when the median bracket width of each op is at
            most 2x q06's. PMU_ASSOCIATED if p06 has no INVALID RUN, is not perturbed, observes and separates both
            boundaries in every measured RUN and keeps the resolution; else the failing term is reported and the
            PMU values are not used
None of these is an operator start/end time or an attribution of counts to an operator.
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms  # noqa: E402
import cms_timeline  # noqa: E402
import qread_checked as C  # noqa: E402
import qread_trace as Q  # noqa: E402

OPS = (99, 100)
NPU_ACTIVE = 35
FLOOR = 0.01
RESOLUTION_FACTOR = 2
PERTURBED, OBSERVED, COARSE = "TRACE_PERTURBED", "BOUNDARY_OBSERVED", "TRACE_VALID_COARSE"
ASSOCIATED, NOT_RUN, UP = "PMU_ASSOCIATED", "NOT_RUN", "UNPROVEN"


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def load_runs(folder: pathlib.Path, warmup: int) -> dict:
    """{(set, rep): {"ev": {code: value}, "valid": bool, "output": bool}}, measured RUNs only."""
    out = {}
    with open(folder / "runs.csv") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        k = (int(r["set_id"]), int(r["rep"]))
        if k[1] <= warmup:
            continue
        d = out.setdefault(k, {"ev": {}, "valid": r["run_valid"] == "True",
                               "output": r["output_match"] == "1" and r["ofm_mismatch_count"] == "0"})
        d["ev"][int(r["ev_type"])] = int(r["event_value"]) if r["event_value"] not in ("", "None") else None
    return out


def load_traces(folder: pathlib.Path, warmup: int) -> dict:
    out = {}
    for x in json.loads((folder / "raw_runs.json").read_text()):
        if "record" not in x or x["rep"] <= warmup:
            continue
        b = (folder / "traces" / f"set{x['set_id']}_rep{x['rep']}.bin").read_bytes()
        words = [int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)]
        out[(x["set_id"], x["rep"])] = C.parse(words, Q.header_from_record(x["record"]), x["record"]["event_count"])
    return out


def perturbation(cond: dict, base: dict) -> tuple[str, dict]:
    """Per set: median NPU_ACTIVE of cond vs base; PERTURBED if any |diff| > 1 %, UNPROVEN if a set lacks data."""
    det, verdict = {}, "UNPERTURBED"
    for s in sorted({k[0] for k in cond}):
        a = [r["ev"].get(NPU_ACTIVE) for k, r in cond.items() if k[0] == s]
        b = [r["ev"].get(NPU_ACTIVE) for k, r in base.items() if k[0] == s]
        ma, mb = med(a), med(b)
        if ma is None or not mb:
            return UP, det
        det[s] = dict(median=ma, base_median=mb, diff_pct=(ma / mb - 1) * 100)
        if abs(ma - mb) > FLOOR * mb:
            verdict = PERTURBED
    return (verdict if det else UP), det


def run_class(t: C.Trace | None, run: dict, cms_len: int, npu_id: int) -> tuple[str, list[str]]:
    if t is None:
        return C.INVALID, ["no_trace"]
    cls, why = C.trace_class(t, cms_len, npu_id)
    extra = ([] if run["valid"] else ["run_not_valid"]) + ([] if run["output"] else ["output_mismatch"])
    return (C.INVALID, why + extra) if extra else (cls, why)


def condition_verdict(classes: list[str], pert: str) -> str:
    if not classes or pert == UP:
        return UP
    if C.INVALID in classes:
        return C.INVALID
    if pert == PERTURBED:
        return PERTURBED
    return C.RECOVERED if C.RECOVERED in classes else C.VALID


def kernel_offsets(stream: bytes) -> dict:
    return {r["index"]: r["offset"] for r in cms_timeline.timeline(stream) if r["index"] in OPS}


def bracket(job: tuple, o: int) -> dict:
    lo = [i for i, s in enumerate(job) if s.qread_before.value <= o]
    hi = [i for i, s in enumerate(job) if s.qread_after.value > o]
    if not lo or not hi:
        return dict(observed=False, why="not_bracketed")
    a, b = job[lo[-1]], job[hi[0]]
    ok = a.qread_before.first_ok and b.qread_after.first_ok
    return dict(observed=ok, why="" if ok else "recovered_endpoint", lo=a.t_before, hi=b.t_after,
                width=Q.elapsed(a.t_before, b.t_after), lo_index=lo[-1], hi_index=hi[0])


def separated(job: tuple, o99: int, o100: int) -> bool:
    return any(o99 < sl.value <= o100 for s in job for sl in (s.qread_before, s.qread_after) if sl.first_ok)


def boundaries(traces: dict, offs: dict) -> tuple[bool, dict]:
    per = {}
    for k, t in traces.items():
        job = t.job()
        b = {op: bracket(job, offs[op]) for op in OPS}
        per[f"set{k[0]}_rep{k[1]}"] = dict(brackets=b, separated=separated(job, offs[99], offs[100]))
    ok = bool(per) and all(all(v["brackets"][op]["observed"] for op in OPS) and v["separated"] for v in per.values())
    return ok, per


def describe(traces: dict, stream: bytes) -> dict:
    """POST_HOC_DESCRIPTIVE answers to P1's questions (not verdicts)."""
    ins = [o for o, *_ in cms.instructions(stream)]
    zero_status, skipped, cost, rejects = [], [], [], []
    for k, t in traces.items():
        job = t.job()
        zero_status += [s.status.value & 1 for s in job if s.qread_after.value == 0]
        q = [s.qread_after.value for s in job]
        skipped += [sum(a <= o < b for o in ins) for a, b in zip(q, q[1:])]
        cost += [Q.elapsed(s.t_before, s.t_after) for s in job]
        rejects += [dict(r, run=f"set{k[0]}_rep{k[1]}") for r in C.rejected_attempts(t)]
    return dict(samples_with_qread_0=len(zero_status), of_them_status_running=sum(zero_status),
                commands_completed_between_samples=dict(median=med(skipped), max=max(skipped, default=None),
                                                        zero=sum(x == 0 for x in skipped), n=len(skipped)),
                read_cycles=dict(median=med(cost), max=max(cost, default=None)), rejected_attempts=rejects)


def traffic(cond: dict, base: dict) -> dict:
    """Median of every event in both conditions, per set (POST_HOC_DESCRIPTIVE)."""
    out = {}
    for s in sorted({k[0] for k in cond}):
        codes = {c for k, r in cond.items() if k[0] == s for c in r["ev"]}
        for c in sorted(codes):
            a = med([r["ev"].get(c) for k, r in cond.items() if k[0] == s])
            b = med([r["ev"].get(c) for k, r in base.items() if k[0] == s])
            out[f"set{s}_ev{c}"] = dict(median=a, base_median=b, diff_pct=(a / b - 1) * 100 if a is not None and b else None)
    return out


def judge(root: pathlib.Path, cond: str, base: str, stream: bytes, npu_id: int, warmup: int) -> dict:
    runs, ref = load_runs(root / cond, warmup), load_runs(root / base, warmup)
    traces = load_traces(root / cond, warmup)
    classes = {f"set{k[0]}_rep{k[1]}": run_class(traces.get(k), r, len(stream), npu_id) for k, r in runs.items()}
    pert, pdet = perturbation(runs, ref)
    v = condition_verdict([c for c, _ in classes.values()], pert)
    return dict(verdict=v, perturbation=pert, perturbation_detail=pdet, run_classes=classes, traces=traces,
                runs=runs, base=ref)


def p12(model_dir: str, cms_path: str, npu_id: int, out: str, warmup: int = 1) -> dict:
    root, o, stream = pathlib.Path(model_dir), pathlib.Path(out), pathlib.Path(cms_path).read_bytes()
    j = judge(root, "q06", "base", stream, npu_id, warmup)
    offs = kernel_offsets(stream)
    res = dict(P1=j["verdict"], P1_perturbation=j["perturbation_detail"], P1_runs=j["run_classes"],
               kernel_offsets=offs, P1_descriptive=dict(describe(j["traces"], stream),
                                                        traffic=traffic(j["runs"], j["base"])))
    if j["verdict"] in (C.VALID, C.RECOVERED):
        ok, per = boundaries(j["traces"], offs)
        res.update(P2=OBSERVED if ok else COARSE, P2_runs=per)
    else:
        res.update(P2=NOT_RUN)
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def intervals(t: C.Trace, lo: int, hi: int) -> list[dict]:
    """Δt and Δcounters between consecutive job samples lo .. hi (POST_HOC_DESCRIPTIVE); an interval whose counter or
    QREAD reads were not all first-read is flagged, never used as a value."""
    job, out = t.job(), []
    for a, b in zip(job[lo:hi], job[lo + 1:hi + 1]):
        first = all(sl.first_ok for s in (a, b) for sl in s.slots)
        out.append(dict(q_from=a.qread_after.value, q_to=b.qread_after.value, dt=Q.elapsed(a.t_before, b.t_before),
                        first_read=first,
                        d_events=[y.value - x.value for x, y in zip(a.events, b.events)] if first else None))
    return out


def p3(model_dir: str, cms_path: str, npu_id: int, out: str, p12_summary: str, warmup: int = 1) -> dict:
    root, o, stream = pathlib.Path(model_dir), pathlib.Path(out), pathlib.Path(cms_path).read_bytes()
    prev = json.loads(pathlib.Path(p12_summary).read_text())
    if prev.get("P2") != OBSERVED:
        res = dict(P3=NOT_RUN, why=f"P2 = {prev.get('P2')}")
    else:
        j = judge(root, "p06", "pbase", stream, npu_id, warmup)
        offs = kernel_offsets(stream)
        ok, per = boundaries(j["traces"], offs) if j["verdict"] in (C.VALID, C.RECOVERED) else (False, {})
        width = {op: med([v["brackets"][op].get("width") for v in per.values()]) for op in OPS}
        width_q06 = {op: med([v["brackets"][str(op)].get("width") for v in prev["P2_runs"].values()]) for op in OPS}
        kept = all(width[op] is not None and width_q06[op] and width[op] <= RESOLUTION_FACTOR * width_q06[op]
                   for op in OPS)
        terms = dict(trace=j["verdict"], boundaries=ok, resolution_kept=kept)
        res = dict(P3=ASSOCIATED if j["verdict"] in (C.VALID, C.RECOVERED) and ok and kept else "NOT_ASSOCIATED",
                   terms=terms, perturbation=j["perturbation_detail"], runs=j["run_classes"], bracket_width=width,
                   bracket_width_q06=width_q06, P3_runs=per)
        if res["P3"] == ASSOCIATED:
            res["intervals"] = {k: intervals(t, per[k]["brackets"][99]["lo_index"], per[k]["brackets"][100]["hi_index"])
                                for k, t in ((f"set{a}_rep{b}", t) for (a, b), t in j["traces"].items())}
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "p12":
        print(json.dumps(p12(a[1], a[2], int(a[3], 0), a[4], *(int(x) for x in a[5:6])), indent=1, default=str))
    else:
        print(json.dumps(p3(a[1], a[2], int(a[3], 0), a[4], a[5], *(int(x) for x in a[6:7])), indent=1, default=str))
