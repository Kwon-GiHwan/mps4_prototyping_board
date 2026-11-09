#!/usr/bin/env python3
"""Equivalence C (docs/plan/equivalence_plan.md §8.1 M1-M4, §9): runner vs MLEK on the same input, the same Vela
output and TA profile 1. Judged per (model, metric); missing data is UNPROVEN, never assumed equal.

  python3 host/analysis/equiv_c.py <mlek root> <runner root> <out dir>

<mlek root>/<model>/stock/B<n>/app_uart.raw and events/B<n>/app_uart.raw: stock MLEK and the instrumented build, one
inference per boot (mlek_counters.py). <runner root>/<model>/: run_pmu_events.py output of the blob whose IFM and
golden are the MLEK dump (amendment-2 entry accepted), sets A and B, 10 RUNs, 2 warm-up.

  M1 output   every measured RUN valid with OFM mismatch 0 against the MLEK golden -> EQUIVALENT; a mismatch ->
              NOT_EQUIVALENT; no runner data -> UNPROVEN
  M2 beats    every stock boot and every runner RUN the same value, and equal -> EQUIVALENT; else NOT_EQUIVALENT
  M3 ACTIVE   |runner median - MLEK median| <= max(MLEK boot range, runner measured-RUN range) -> EQUIVALENT
  M4 events   (MAC_ACTIVE, MAC_DPU_ACTIVE, AO_ACTIVE) the M3 rule against the instrumented build, only if that build
              leaves the stock counters unchanged on this input (its beats = stock exactly, its ACTIVE within the M3
              rule against stock) -> else UNPROVEN (instrumented build disturbs or is missing)
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mlek_counters as MC  # noqa: E402

WARMUP = 2
BEATS = ("SRAM_RD_DATA_BEAT_RECEIVED", "SRAM_WR_DATA_BEAT_WRITTEN", "EXT_RD_DATA_BEAT_RECEIVED",
         "EXT_WR_DATA_BEAT_WRITTEN")
UNITS = ("MAC_ACTIVE", "MAC_DPU_ACTIVE", "AO_ACTIVE")
EQ, NE, UP = "EQUIVALENT", "NOT_EQUIVALENT", "UNPROVEN"


def mlek_boots(d: pathlib.Path) -> list[dict[str, int]]:
    out = []
    for f in sorted(d.glob("B*/app_uart.raw")):
        out.append(MC.counters(f.read_bytes().decode("ascii", "replace").replace("\r", "")))
    return out


def runner_rows(d: pathlib.Path) -> list[dict]:
    with (d / "runs.csv").open() as f:
        return [r for r in csv.DictReader(f) if int(r["rep"]) > WARMUP]


def runner_values(rows: list[dict], name: str) -> list[int]:
    ev = MC.EVENT_ID[name]
    return [int(r["event_value"]) for r in rows
            if int(r["ev_type"]) == ev and r["run_valid"] == "True" and r["event_value"] not in ("", "None")]


def exact(a: list[int], b: list[int]) -> str:
    if not a or not b:
        return UP
    return EQ if len(set(a)) == 1 and set(a) == set(b) else NE


def jitter(a: list[int], b: list[int]) -> str:
    """The M3 rule: medians within the larger of the two ranges."""
    if not a or not b:
        return UP
    tol = max(max(a) - min(a), max(b) - min(b))
    return EQ if abs(statistics.median(a) - statistics.median(b)) <= tol else NE


def output(rows: list[dict]) -> str:
    if not rows:
        return UP
    if any(r["run_valid"] != "True" for r in rows):
        return UP
    return EQ if all(r["ofm_mismatch_count"] == "0" for r in rows) else NE


def model(stock: list[dict], events: list[dict], rows: list[dict]) -> dict:
    col = lambda boots, k: [b[k] for b in boots if k in b]
    res = {"M1_output": output(rows)}
    for k in BEATS:
        res[f"M2_{k}"] = exact(col(stock, k), runner_values(rows, k))
    res["M3_ACTIVE"] = jitter(col(stock, "ACTIVE"), runner_values(rows, "ACTIVE"))
    inert = all(exact(col(events, k), col(stock, k)) == EQ for k in BEATS) \
        and jitter(col(events, "ACTIVE"), col(stock, "ACTIVE")) == EQ
    res["instrumented_build_inert"] = inert
    for k in UNITS:
        res[f"M4_{k}"] = jitter(col(events, k), runner_values(rows, k)) if inert else UP
    return res


def main(mlek_root: str, runner_root: str, out: str) -> dict:
    res = {}
    for d in sorted(pathlib.Path(mlek_root).iterdir()):
        if not d.is_dir():
            continue
        r = pathlib.Path(runner_root) / d.name
        rows = runner_rows(r) if (r / "runs.csv").exists() else []
        res[d.name] = model(mlek_boots(d / "stock"), mlek_boots(d / "events"), rows)
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), indent=1))
