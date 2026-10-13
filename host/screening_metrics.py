"""Ethos-U85 first-pass screening metrics (contract 2026-10-12-u85-screening-contract.md).

Reads each workload's campaign (runs.csv: one row per event per RUN) and its static metadata
(N_MAC, Vela prediction), drops the warm-up RUNs, and writes per-run metrics, per-workload
summaries and the fingerprint table.

    python3 host/screening_metrics.py evidence/u85_screening
      expects  <root>/workloads/<name>.meta.json  and  <root>/<name>/runs.csv
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

WORKLOADS = ("kws_micronet_m", "mobilenet_v2_1.0_224_INT8", "ad_medium_int8", "conv3x3_56x56x64", "matmul_xxT")
EVENTS = {35: "npu_active", 48: "mac_active", 386: "ext_rd_beats", 391: "ext_wr_beats",
          387: "ext_rd_req_stall", 392: "ext_wr_req_stall", 393: "ext_wr_data_stall", 396: "ext_enabled"}
WARMUP, MEASURED = 5, 30
MACS_PER_CYCLE = 1024          # configured_MAC_count (contract: Vela convention, not TRM-verified)
OUTCOMES = ("SCREENED", "UNPROVEN", "NOT_EXECUTABLE")
METRICS = ("npu_active", "window_cycles", "npu_active_ratio", "peak_mac_efficiency",
           "mac_active_cycle_efficiency", "mac_active_ratio", "ext_beats_per_mac", "ext_rd_beats_per_mac",
           "ext_wr_beats_per_mac", "ext_read_req_stall_ratio", "ext_write_req_stall_ratio",
           "ext_write_data_stall_ratio")


def load_runs(path: Path) -> list[dict]:
    """One dict per RUN: rep, valid, overflow, window_cycles and the 8 counters."""
    runs: dict[int, dict] = {}
    for r in csv.DictReader(open(path)):
        rep = int(r["rep"])
        run = runs.setdefault(rep, {"rep": rep, "valid": r["run_valid"] == "True", "overflow": False,
                                    "window_cycles": int(r["window_cycles"]) if r["window_cycles"] else None})
        run["overflow"] |= r["event_overflow"] not in ("0", "False", "")
        ev = int(r["ev_type"])
        run[EVENTS[ev]] = int(r["event_value"]) if r["event_value"] not in ("", "None") else None
    return [runs[k] for k in sorted(runs)]


def ratio(a, b):
    return a / b if a is not None and b else None


def derive(run: dict, n_mac: int) -> dict:
    d = dict(run)
    d["npu_active_ratio"] = ratio(run["npu_active"], run["window_cycles"])
    d["peak_mac_efficiency"] = ratio(n_mac, MACS_PER_CYCLE * run["npu_active"])
    d["mac_active_cycle_efficiency"] = ratio(n_mac, MACS_PER_CYCLE * run["mac_active"]) if run["mac_active"] else None
    d["mac_active_ratio"] = ratio(run["mac_active"], run["npu_active"])
    d["ext_beats_per_mac"] = ratio(run["ext_rd_beats"] + run["ext_wr_beats"], n_mac)
    d["ext_rd_beats_per_mac"] = ratio(run["ext_rd_beats"], n_mac)
    d["ext_wr_beats_per_mac"] = ratio(run["ext_wr_beats"], n_mac)
    d["ext_read_req_stall_ratio"] = ratio(run["ext_rd_req_stall"], run["ext_enabled"])
    d["ext_write_req_stall_ratio"] = ratio(run["ext_wr_req_stall"], run["ext_enabled"])
    d["ext_write_data_stall_ratio"] = ratio(run["ext_wr_data_stall"], run["ext_enabled"])
    return d


def consistency(run: dict) -> list[str]:
    fails = []
    if run["overflow"]:
        fails.append("overflow")
    if run["npu_active"] > run["window_cycles"]:
        fails.append("npu_active>window")
    if run["mac_active"] > run["npu_active"]:
        fails.append("mac_active>npu_active")
    for k in ("ext_rd_req_stall", "ext_wr_req_stall", "ext_wr_data_stall"):
        if run[k] > run["ext_enabled"]:
            fails.append(f"{k}>ext_enabled")
    return fails


def stats(values: list[float]) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {}
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return dict(median=statistics.median(vals), mean=mean, std=std, cv=(std / mean if mean else None),
                min=min(vals), max=max(vals), n=len(vals))


def workload(root: Path, name: str) -> dict:
    meta = json.load(open(root / "workloads" / f"{name}.meta.json"))
    runs_csv = root / name / "runs.csv"
    if not runs_csv.exists():
        return dict(name=name, outcome="NOT_EXECUTABLE", reason="no runs.csv")
    runs = load_runs(runs_csv)
    measured = [r for r in runs if r["rep"] > WARMUP]
    valid = [derive(r, meta["n_mac"]) for r in measured if r["valid"]]
    fails = {r["rep"]: consistency(r) for r in valid if consistency(r)}
    if not valid:
        outcome = "NOT_EXECUTABLE"
    elif len(valid) < MEASURED or fails:
        outcome = "UNPROVEN"
    else:
        outcome = "SCREENED"
    summary = {m: stats([r[m] for r in valid]) for m in METRICS}
    med = summary["npu_active"].get("median")
    vela = meta["vela"]
    m7 = {}
    if med:
        m7 = dict(vela_cycles_total=vela["cycles_total"], vela_cycles_npu=vela["cycles_npu"],
                  vela_signed_error=(vela["cycles_total"] - med) / med,
                  vela_absolute_error=abs(vela["cycles_total"] - med) / med,
                  vela_npu_signed_error=(vela["cycles_npu"] - med) / med)
    return dict(name=name, outcome=outcome, runs_total=len(runs), measured=len(measured), valid_measured=len(valid),
                consistency_fails=fails, n_mac=meta["n_mac"], vela_nn_macs=vela["nn_macs"],
                op_counts=meta["op_counts"], summary=summary, m7=m7, per_run=valid)


def fmt(v, kind="f"):
    if v is None:
        return "N/A"
    return f"{v:,.0f}" if kind == "i" else (f"{v:.1%}" if kind == "%" else f"{v:.4f}")


def fingerprint(results: list[dict]) -> str:
    rows = [("M1 npu_active (cycles)", "npu_active", "i"), ("    window (PMCCNTR, incl. staging)", "window_cycles", "i"),
            ("M2 npu_active / window", "npu_active_ratio", "%"), ("M3 peak MAC efficiency", "peak_mac_efficiency", "%"),
            ("    MAC active-cycle efficiency", "mac_active_cycle_efficiency", "%"),
            ("M4 MAC active ratio", "mac_active_ratio", "%"), ("M5 EXT beats / MAC", "ext_beats_per_mac", "f"),
            ("    read beats / MAC", "ext_rd_beats_per_mac", "f"), ("    write beats / MAC", "ext_wr_beats_per_mac", "f"),
            ("M6 EXT read-req stall", "ext_read_req_stall_ratio", "%"),
            ("    EXT write-req stall", "ext_write_req_stall_ratio", "%"),
            ("    EXT write-data stall", "ext_write_data_stall_ratio", "%")]
    head = "| metric (median of 30) | " + " | ".join(r["name"] for r in results) + " |"
    out = [head, "|" + " --- |" * (len(results) + 1),
           "| outcome | " + " | ".join(r["outcome"] for r in results) + " |"]
    for label, key, kind in rows:
        out.append(f"| {label} | " + " | ".join(fmt(r.get("summary", {}).get(key, {}).get("median"), kind) for r in results) + " |")
    out.append("| M7 Vela signed error (cycles_total vs npu_active) | "
               + " | ".join(fmt(r.get("m7", {}).get("vela_signed_error"), "%") for r in results) + " |")
    out.append("| CV of npu_active | " + " | ".join(fmt(r.get("summary", {}).get("npu_active", {}).get("cv"), "%") for r in results) + " |")
    return "\n".join(out)


def main(root: str) -> None:
    root_p = Path(root)
    results = [workload(root_p, n) for n in WORKLOADS]
    with open(root_p / "screening_per_run.csv", "w", newline="") as f:
        rows = [dict(workload=r["name"], **{k: v for k, v in run.items()}) for r in results for run in r.get("per_run", [])]
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump([{k: v for k, v in r.items() if k != "per_run"} for r in results],
              open(root_p / "screening_summary.json", "w"), indent=1)
    print(fingerprint(results))


if __name__ == "__main__":
    main(sys.argv[1])
