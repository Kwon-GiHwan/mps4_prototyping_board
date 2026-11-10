#!/usr/bin/env python3
"""QREAD pilot on the driver runner (docs/plan/driver_profiling_design.md §4 P1-P3; contract evidence/qread_pilot/).
TA profile 1. One boot per model, every condition in that boot (run_driver_events.py --conditions):

  wfe     WAIT_WFE,  sets BASE, A, B      (P0: driver_p3.py on this folder, warm-up 1, reference = driver m7)
  busy    WAIT_BUSY, set BASE             (P1 against wfe)
  t06/t10/t14  WAIT_TRACE QREAD_ONLY, poll 2^6 / 2^10 / 2^14 cycles, set BASE   (P2 against busy)
  p10     WAIT_TRACE QREAD_PMU,  poll 2^10, set A                                (P3)

  python3 host/analysis/qread_pilot.py <boot root>/<model> <model.drwl.cms.bin> <out dir> [warm-up RUNs, default 1]

Rules (fixed in the contract before the data):
  P1  wfe vs busy, NPU_ACTIVE and NPU_EXECUTION medians: |diff| > tol -> EFFECTIVE, else UNRESOLVED (a difference
      inside the spread is never claimed; config/driver_r5.json). tol = max(1 % of the reference median, either RUN range)
  P2  per trace condition: perturbation = the P1 rule against busy (EFFECTIVE -> TRACE_PERTURBED); every RUN through
      qread_timeline (integrity, resolved ratio); the condition takes its worst RUN's verdict
      (TRACE_INVALID > TRACE_PERTURBED > TRACE_UNOBSERVABLE > TRACE_COARSE > TRACE_VALID). TRACE_VALID is a timeline
      verdict, never an attribution.
  P3  p10: the P2 verdict, and EVENTS_AT_END = the last sample's counters equal the IRQ read in every RUN (the
      counters stopped with the NPU) / EVENTS_MOVED_AFTER_IRQ; UNPROVEN without data.
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import fi101_s013 as S  # noqa: E402
import qread_timeline as T  # noqa: E402
import qread_trace as Q  # noqa: E402

FLOOR = 0.01
TRACE_CONDS = ("t06", "t10", "t14", "p10")
ORDER = ("TRACE_INVALID", "TRACE_PERTURBED", "TRACE_UNOBSERVABLE", "TRACE_COARSE", "TRACE_VALID", "UNPROVEN")
UP = "UNPROVEN"


def metric(runs: dict, key: str) -> list[int]:
    return [r["infer"] if key == "exec" else r["ev"].get(35) for r in runs.values()
            if (r["infer"] if key == "exec" else r["ev"].get(35)) is not None]


def compare(a: list[int], ref: list[int]) -> tuple[str, dict]:
    """The P1 rule: EFFECTIVE beyond the spread, UNRESOLVED inside it."""
    if not a or not ref:
        return UP, {}
    m, mr = statistics.median(a), statistics.median(ref)
    tol = max(FLOOR * mr, max(a) - min(a), max(ref) - min(ref))
    return ("EFFECTIVE" if abs(m - mr) > tol else "UNRESOLVED"), dict(median=m, ref_median=mr,
                                                                       diff_pct=(m / mr - 1) * 100, tol=tol)


def wait_effect(cond: dict, ref: dict) -> tuple[str, dict]:
    """P1 over NPU_ACTIVE and NPU_EXECUTION: EFFECTIVE if either is, UNPROVEN if either is missing."""
    out = {k: compare(metric(cond, k), metric(ref, k)) for k in ("active", "exec")}
    v = [x[0] for x in out.values()]
    verdict = UP if UP in v else "EFFECTIVE" if "EFFECTIVE" in v else "UNRESOLVED"
    return verdict, {k: x[1] for k, x in out.items()}


def worst(verdicts: list[str]) -> str:
    return min(verdicts, key=ORDER.index) if verdicts else UP


def events_at_end(folder: pathlib.Path, warmup: int) -> str:
    raw = json.loads((folder / "raw_runs.json").read_text())
    ok = []
    for r in raw:
        if "record" not in r or r["rep"] <= warmup:
            continue
        tf = folder / "traces" / f"set{r['set_id']}_rep{r['rep']}.bin"
        if not tf.exists():
            return UP
        b = tf.read_bytes()
        t = Q.parse([int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)],
                    Q.header_from_record(r["record"]))
        if not t.samples:
            return UP
        ok.append(list(t.samples[-1].events) == [r["record"][f"ev_irq{i}"] for i in range(len(t.samples[-1].events))])
    return UP if not ok else "EVENTS_AT_END" if all(ok) else "EVENTS_MOVED_AFTER_IRQ"


def trace_condition(folder: pathlib.Path, cms: str, busy: dict, warmup: int, out: pathlib.Path) -> dict:
    runs = S.load_runs(folder, warmup)
    pert, pdet = wait_effect(runs, busy)
    summ = T.main(cms, str(folder), str(out))
    measured = {k: v for k, v in summ.items() if int(k.split("_rep")[1]) > warmup}
    per_run = []
    for v in measured.values():
        if "verdict" in v:                                   # no or unparsable trace
            per_run.append(v["verdict"])
        else:
            per_run.append(T.verdict(v["problems"], None if pert == UP else pert == "EFFECTIVE", v["resolved_ratio"]))
    return dict(perturbation=pert, perturbation_detail=pdet, verdict=worst(per_run), run_verdicts=per_run,
                resolved_ratio=[v.get("resolved_ratio") for v in measured.values()],
                samples=[v.get("samples") for v in measured.values()],
                read_cycles_max=[v.get("read_cycles_max") for v in measured.values()])


def main(model_dir: str, cms: str, out: str, warmup: int = 1) -> dict:
    root, o = pathlib.Path(model_dir), pathlib.Path(out)
    load = lambda c: S.load_runs(root / c, warmup) if (root / c / "runs.csv").exists() else {}
    wfe, busy = load("wfe"), load("busy")
    p1, p1d = wait_effect(busy, wfe)
    res = dict(P1=p1, P1_detail=p1d)
    for c in TRACE_CONDS:
        res[c] = trace_condition(root / c, cms, busy, warmup, o / c) if (root / c / "runs.csv").exists() \
            else dict(verdict=UP)
    res["P3_events"] = events_at_end(root / "p10", warmup) if (root / "p10" / "raw_runs.json").exists() else UP
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4], *(int(x) for x in sys.argv[4:5])), indent=1, default=str))
