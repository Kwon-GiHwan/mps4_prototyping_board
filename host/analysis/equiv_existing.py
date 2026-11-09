#!/usr/bin/env python3
"""Runner vs MLEK equivalence (E1-E5 plan, docs/plan/equivalence_plan.md): what existing data already shows. TA
profile 1 on both sides. POST_HOC_DESCRIPTIVE: no new rule is applied here; the plan preregisters the criteria.

  python3 host/analysis/equiv_existing.py <out dir> <name>=<runner boot dir>:<warm-up RUNs> ...

MLEK side: docs/reference/mlek_board_reference.json (stock MLEK on FI101, one inference per boot, B1-B3, ethosu_profiler
counters: ACTIVE and four beat counters; kws, ad, mobilenet only). Runner side: every valid measured RUN (rep >
warm-up, as each dataset's own rule) of each given boot dir (<dir>/<model>/runs.csv), all event sets pooled per event
id. Per (model, runner dataset, metric): runner median, min, max and n, MLEK B1-B3 values, the difference of the medians, and whether the runner median lies inside the MLEK
range. IDLE / TOTAL are not compared: the two PMU windows differ (E4).
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
REF = REPO / "docs" / "reference" / "mlek_board_reference.json"
METRICS = {35: "ACTIVE", 130: "SRAM_RD_DATA_BEAT_RECEIVED", 135: "SRAM_WR_DATA_BEAT_WRITTEN",
           386: "EXT_RD_DATA_BEAT_RECEIVED", 391: "EXT_WR_DATA_BEAT_WRITTEN"}
BOOTS = ("B1", "B2", "B3")


def runner_values(runs_csv: pathlib.Path, warmup: int) -> tuple[dict[str, list[int]], str]:
    """Valid measured values per MLEK metric name, and the image (APP sha256 prefix)."""
    out: dict[str, list[int]] = {}
    image = ""
    with runs_csv.open() as f:
        for r in csv.DictReader(f):
            image = r.get("app_sha256", "")[:8]
            ev = int(r["ev_type"])
            if (ev in METRICS and int(r["rep"]) > warmup and r["run_valid"] == "True"
                    and r["event_value"] not in ("", "None")):
                out.setdefault(METRICS[ev], []).append(int(r["event_value"]))
    return out, image


def compare(mlek: list[int], runner: list[int]) -> dict:
    med_r, med_m = statistics.median(runner), statistics.median(mlek)
    return dict(runner_median=med_r, runner_min=min(runner), runner_max=max(runner), runner_n=len(runner),
                mlek=" ".join(map(str, mlek)), mlek_median=med_m,
                diff_pct=(med_r - med_m) / med_m * 100 if med_m else None,
                exact=int(min(runner) == max(runner) == min(mlek) == max(mlek)),
                runner_median_in_mlek_range=int(min(mlek) <= med_r <= max(mlek)),
                ranges_overlap=int(min(runner) <= max(mlek) and min(mlek) <= max(runner)))


def main(out: str, *datasets: str) -> list[dict]:
    ref = json.loads(REF.read_text())["workloads"]
    rows = []
    for spec in datasets:
        name, rest = spec.split("=", 1)
        root, warmup = rest.rsplit(":", 1)
        for model, m in ref.items():
            p = pathlib.Path(root) / model / "runs.csv"
            if not p.exists():
                continue
            vals, image = runner_values(p, int(warmup))
            for metric, xs in vals.items():
                rows.append(dict(model=model, dataset=name, image=image, warmup=int(warmup), metric=metric,
                                 **compare([m[b][metric] for b in BOOTS], xs)))
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    with (o / "existing_equivalence.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    for r in main(*sys.argv[1:]):
        print(r["model"][:9], r["dataset"], r["image"], r["metric"][:12], r["runner_median"], r["mlek"],
              f"{r['diff_pct']:+.2f}%", "exact" if r["exact"] else ("in-range" if r["runner_median_in_mlek_range"]
                                                                    else "out-of-range"))
