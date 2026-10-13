"""One-variable A/B outcome against MLEK's board NPU ACTIVE (rule frozen in docs/specs/timing-adapter-ab.md).

Reads two screening_metrics roots (control, treatment: same image, same command stream, one knob differs) plus
each workload's runs.csv for the invariants, and MLEK's board reference from docs/reference/mlek_board_reference.json.

    python3 host/ab_outcome.py <control root> <treatment root>
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "reference" / "mlek_board_reference.json"
WARMUP = 5
INVARIANT_TOL = 0.001          # mac_active and EXT beats may move by at most 0.1 %
OUTCOMES = ("SUPPORTED", "PARTIAL_CONTRIBUTOR", "REFUTED", "UNRESOLVED")


def medians(runs_csv: Path) -> dict:
    """Median over measured RUNs (rep > WARMUP, valid) of npu_active, mac_active, EXT rd/wr beats."""
    vals: dict[str, list[int]] = {"35": [], "48": [], "386": [], "391": []}
    for r in csv.DictReader(open(runs_csv)):
        if int(r["rep"]) > WARMUP and r["run_valid"] == "True" and r["ev_type"] in vals:
            vals[r["ev_type"]].append(int(r["event_value"]))
    return {k: statistics.median(v) if v else None for k, v in vals.items()}


def closure(c: float, t: float, m: float) -> float:
    """Share of the control-to-MLEK gap removed by the treatment."""
    return (c - t) / (c - m)


def outcome(screened_c: bool, screened_t: bool, mc: dict, mt: dict, m: float) -> str:
    if not (screened_c and screened_t):
        return "UNRESOLVED"
    for ev in ("48", "386", "391"):
        if mc[ev] is None or mt[ev] is None or abs(mt[ev] - mc[ev]) > INVARIANT_TOL * max(mc[ev], 1):
            return "UNRESOLVED"   # the work or the traffic changed: not a one-variable comparison
    if mc["35"] <= m:
        return "UNRESOLVED"       # no gap to close
    g = closure(mc["35"], mt["35"], m)
    if g >= 0.8:
        return "SUPPORTED"
    if g >= 0.2:
        return "PARTIAL_CONTRIBUTOR"
    return "REFUTED"


def overall(per: dict) -> str:
    """kws is primary, ad_medium replicates; mobilenet is reported but does not decide."""
    k, a = per.get("kws_micronet_m"), per.get("ad_medium_int8")
    if k == a and k in ("SUPPORTED", "PARTIAL_CONTRIBUTOR", "REFUTED"):
        return k
    return "UNRESOLVED"


def mlek_active() -> dict:
    """MLEK board NPU ACTIVE, median of B1-B3, per workload."""
    return {n: w["ACTIVE_median"] for n, w in json.load(open(REFERENCE))["workloads"].items()}


def main(ctrl_root: str, treat_root: str) -> None:
    summ = lambda root: {r["name"]: r for r in json.load(open(Path(root) / "screening_summary.json"))}
    sc, st = summ(ctrl_root), summ(treat_root)
    ref = mlek_active()
    per = {}
    print("| workload | outcome | control npu_active | treatment npu_active | MLEK | gap closure | "
          "non-MAC control → treatment |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for n in ref:
        if n not in sc or n not in st or not (Path(ctrl_root) / n / "runs.csv").exists() \
                or not (Path(treat_root) / n / "runs.csv").exists():
            per[n] = "UNRESOLVED"
            print(f"| {n} | UNRESOLVED | N/A | N/A | {ref[n]:,} | N/A | N/A |")
            continue
        mc, mt = medians(Path(ctrl_root) / n / "runs.csv"), medians(Path(treat_root) / n / "runs.csv")
        per[n] = outcome(sc[n]["outcome"] == "SCREENED", st[n]["outcome"] == "SCREENED", mc, mt, ref[n])
        print(f"| {n} | {per[n]} | {mc['35']:,.0f} | {mt['35']:,.0f} | {ref[n]:,} | "
              f"{closure(mc['35'], mt['35'], ref[n]):.3f} | "
              f"{mc['35'] - mc['48']:,.0f} → {mt['35'] - mt['48']:,.0f} |")
    print(f"\nOverall: **{overall(per)}**")


if __name__ == "__main__":
    main(*sys.argv[1:3])
