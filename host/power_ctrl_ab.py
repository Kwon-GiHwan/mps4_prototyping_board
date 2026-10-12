"""POWER_CTRL A/B outcome (contract 2026-10-12-u85-power-ctrl-ab-contract.md).

Reads two screening_metrics roots (control = POWER_CTRL vendor 2, treatment = POWER_CTRL 0, same new image)
plus each workload's runs.csv for the invariants.

    python3 host/power_ctrl_ab.py evidence/u85_power_ctrl/ctrl evidence/u85_power_ctrl/treat
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

WORKLOADS = ("kws_micronet_m", "ad_medium_int8", "mobilenet_v2_1.0_224_INT8")
MLEK_ACTIVE = {"kws_micronet_m": 91_431, "ad_medium_int8": 145_976, "mobilenet_v2_1.0_224_INT8": 1_448_049}
SCREENING2 = {"kws_micronet_m": 334_714, "ad_medium_int8": 951_418, "mobilenet_v2_1.0_224_INT8": 10_121_486}
WARMUP = 5
INVARIANT_TOL = 0.001          # mac_active and EXT beats may move by at most 0.1 %
NEUTRAL_TOL = 0.05             # control vs screening 2
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


def main(ctrl_root: str, treat_root: str) -> None:
    summ = lambda root: {r["name"]: r for r in json.load(open(Path(root) / "screening_summary.json"))}
    sc, st = summ(ctrl_root), summ(treat_root)
    per = {}
    print("| workload | outcome | control npu_active | treatment npu_active | MLEK | gap closure | "
          "control / screening 2 | non-MAC control → treatment |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for n in WORKLOADS:
        if n not in sc or n not in st or not (Path(ctrl_root) / n / "runs.csv").exists() \
                or not (Path(treat_root) / n / "runs.csv").exists():
            per[n] = "UNRESOLVED"
            print(f"| {n} | UNRESOLVED | N/A | N/A | {MLEK_ACTIVE[n]:,} | N/A | N/A | N/A |")
            continue
        mc, mt = medians(Path(ctrl_root) / n / "runs.csv"), medians(Path(treat_root) / n / "runs.csv")
        per[n] = outcome(sc[n]["outcome"] == "SCREENED", st[n]["outcome"] == "SCREENED", mc, mt, MLEK_ACTIVE[n])
        neutral = mc["35"] / SCREENING2[n]
        print(f"| {n} | {per[n]} | {mc['35']:,.0f} | {mt['35']:,.0f} | {MLEK_ACTIVE[n]:,} | "
              f"{closure(mc['35'], mt['35'], MLEK_ACTIVE[n]):.3f} | {neutral:.3f}"
              f"{'' if abs(neutral - 1) <= NEUTRAL_TOL else ' (IMAGE_CHANGED)'} | "
              f"{mc['35'] - mc['48']:,.0f} → {mt['35'] - mt['48']:,.0f} |")
    print(f"\nOverall: **{overall(per)}**")


if __name__ == "__main__":
    main(*sys.argv[1:3])
