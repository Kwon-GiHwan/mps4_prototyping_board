#!/usr/bin/env python3
"""Stage 1 screening analysis (evidence/stage1/contract.md): gate every RUN, derive M1-M11, aggregate, fingerprint.

  python3 host/analysis/stage1.py <campaign dir holding <workload>/{runs.csv,summary.json}> <out dir>
      [--add <label> <campaign dir> <manifest>]... [--profile config/mlek_r10.json]

--add analyses a further dataset (amendment 2: `--add a2 <root> manifest.a2.json`) into the same outputs; its rows
carry dataset=<label> and its summary entries are keyed <workload>@<label>. Dataset `s1` is unchanged by it.

Writes per_run.csv, summary.csv, summary.json, fingerprint_table.md into <out dir>. Every RUN is written, valid or
not; aggregates use the 30 measured RUNs of a workload whose gate is BASELINE_PASS, otherwise the workload is
UNRESOLVED and has no aggregate. RUN count, warm-up and image come from the profile (default mlek_baseline:
35 RUNs, 5 warm-up; mlek_r10: 10 RUNs, 2 warm-up).
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import results
from baseline_gate import PROFILE, gate, run_checks

REPO = pathlib.Path(__file__).resolve().parents[2]
STAGE1 = REPO / "evidence" / "stage1"
MANIFEST = STAGE1 / "workload_manifest" / "manifest.json"
IDS = REPO / "config" / "stage1_ids.txt"
M_CONFIGURED = 1024
RAW = ("npu_active", "mac_active", "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats",
       "sram_enabled", "ext_enabled")
DERIVED = ("mac_throughput", "peak_mac_efficiency", "mac_active_ratio", "mac_active_cycle_efficiency",
           "decomposition_residual", "sram_beats_per_mac", "ext_beats_per_mac", "sram_beats_per_npu_cycle",
           "ext_beats_per_npu_cycle", "sram_enabled_per_npu_cycle", "ext_enabled_per_npu_cycle")


def stage1_checks(run: dict) -> list[str]:
    """R1-R5 of stage 0, and R6s (mac_active <= npu_active) in place of R6: the 8 slots hold no `cycle` event."""
    failed = [k for k in run_checks(run) if k != "R6_cycle"]
    a, m = run.get("npu_active"), run.get("mac_active")
    if not (a is not None and m is not None and m <= a):
        failed.append("R6s_mac_le_npu")
    return failed


def derive(run: dict, n_mac: int | None) -> dict:
    """M1-M11 for one RUN. MAC metrics are None when n_mac is None (not a MAC workload)."""
    a, m = run["npu_active"], run["mac_active"]
    sram = run["sram_rd_beats"] + run["sram_wr_beats"]
    ext = run["ext_rd_beats"] + run["ext_wr_beats"]
    d = {"sram_beats_per_npu_cycle": sram / a, "ext_beats_per_npu_cycle": ext / a,
         "sram_enabled_per_npu_cycle": run["sram_enabled"] / a, "ext_enabled_per_npu_cycle": run["ext_enabled"] / a,
         "sram_total_beats": sram, "ext_total_beats": ext}
    if n_mac:
        peak = n_mac / (M_CONFIGURED * a)
        ratio = m / a
        aeff = n_mac / (M_CONFIGURED * m) if m else None
        d.update(mac_throughput=n_mac / a, peak_mac_efficiency=peak, mac_active_ratio=ratio,
                 mac_active_cycle_efficiency=aeff,
                 decomposition_residual=(peak - ratio * aeff) if aeff is not None else None,
                 sram_beats_per_mac=sram / n_mac, ext_beats_per_mac=ext / n_mac)
    else:
        d.update({k: None for k in ("mac_throughput", "peak_mac_efficiency", "mac_active_cycle_efficiency",
                                    "decomposition_residual", "sram_beats_per_mac", "ext_beats_per_mac")})
        d["mac_active_ratio"] = m / a
    return d


def stats(values: list[float]) -> dict:
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"n": len(values), "median": statistics.median(values), "mean": mean, "std": sd,
            "cv": (sd / mean) if mean else None, "min": min(values), "max": max(values),
            "deterministic": min(values) == max(values)}


def analyse(root: pathlib.Path, man: dict, prof: dict, ids: list[int], dataset: str = "s1") -> tuple[list[dict], dict]:
    per_run, summary = [], {}
    for name, w in man.items():
        key = name if dataset == "s1" else f"{name}@{dataset}"
        g = gate(root / name, prof, w, ids, stage1_checks)
        runs = results.load_runs(root / name / "runs.csv") if (root / name / "runs.csv").exists() else []
        boot_ok = g["gate"] == "BASELINE_PASS"
        for r in runs:
            failed = g.get("failed_runs", {}).get(r["rep"], [])
            complete = all(r.get(k) is not None for k in RAW) and r["npu_active"]
            row = dict(experiment_id="stage1", dataset=dataset, profile_id=prof["name"], workload=name, workload_class=w["class"],
                       operator=w.get("operator_type", ""), shape=w.get("shape", ""), run_id=r["rep"],
                       warmup_or_measured="warmup" if r["rep"] <= prof["warmup"] else "measured",
                       input_sha256=w["golden"]["input_sha256"], blob_sha256=w["blob_sha256"],
                       command_stream_sha256=w["cms_sha256"], configured_mac_count=M_CONFIGURED, n_mac=w["n_mac"],
                       pmccntr=r["window_cycles"], **{k: r.get(k) for k in RAW},
                       output_valid="R3_output" not in failed, knobs_honoured=r["run_rc"] != 0x7D,
                       overflow=bool(r["overflow"]), consistency_valid=not ({"R5_active", "R6s_mac_le_npu"} & set(failed)),
                       run_valid=boot_ok and not failed, failed_checks=";".join(failed))
            row.update(derive(r, w["n_mac"]) if complete else {k: None for k in DERIVED})
            per_run.append(row)
        entry = {"workload": name, "dataset": dataset, "golden_source": w["golden"]["source"],
                 "class": w["class"], "n_mac": w["n_mac"], "gate": g["gate"], "failed_boot": g.get("failed_boot"),
                 "failed_runs": g.get("failed_runs"), "status": "VALID" if boot_ok else "UNRESOLVED"}
        if "numerical_difference_diagnostic" in w:   # reported only, never used for pass/fail
            entry["numerical_difference_diagnostic"] = w["numerical_difference_diagnostic"]
        if boot_ok:
            measured = [p for p in per_run if p["workload"] == name and p["warmup_or_measured"] == "measured"]
            entry["metrics"] = {k: stats([p[k] for p in measured]) for k in RAW + ("pmccntr",) + DERIVED
                                if all(p[k] is not None for p in measured)}
        summary[key] = entry
    return per_run, summary


FINGERPRINT = (("N_MAC", lambda e, n: f"{n:,}" if n else "N/A"),
               ("NPU cycles", lambda e, w: f"{e['npu_active']['median']:,.0f}"),
               ("MAC/cycle", lambda e, w: _f(e, "mac_throughput", "{:.1f}")),
               ("peak MAC eff.", lambda e, w: _f(e, "peak_mac_efficiency", "{:.1%}")),
               ("MAC active ratio", lambda e, w: _f(e, "mac_active_ratio", "{:.1%}")),
               ("MAC active-cycle eff.", lambda e, w: _f(e, "mac_active_cycle_efficiency", "{:.1%}")),
               ("SRAM beat/MAC", lambda e, w: _f(e, "sram_beats_per_mac", "{:.4f}")),
               ("EXT beat/MAC", lambda e, w: _f(e, "ext_beats_per_mac", "{:.4f}")),
               ("SRAM beat/NPU cycle", lambda e, w: _f(e, "sram_beats_per_npu_cycle", "{:.3f}")),
               ("EXT beat/NPU cycle", lambda e, w: _f(e, "ext_beats_per_npu_cycle", "{:.3f}")),
               ("CV(NPU active)", lambda e, w: f"{e['npu_active']['cv']:.2%}"))


def _f(e: dict, k: str, fmt: str) -> str:
    return fmt.format(e[k]["median"]) if k in e else "N/A"


def fingerprint(summary: dict) -> str:
    head = "| workload | class | " + " | ".join(c for c, _ in FINGERPRINT) + " |"
    lines = [head, "| " + " | ".join(["---"] * (len(FINGERPRINT) + 2)) + " |"]
    for name, e in summary.items():
        cells = ([fn(e["metrics"], e["n_mac"]) for _, fn in FINGERPRINT] if e["status"] == "VALID"
                 else [e["gate"]] + [""] * (len(FINGERPRINT) - 1))
        lines.append(f"| {name} | {e['class']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("out")
    ap.add_argument("--add", nargs=3, action="append", default=[], metavar=("LABEL", "ROOT", "MANIFEST"))
    ap.add_argument("--profile", default=str(PROFILE), help="measurement profile (RUN count, warm-up, image); "
                    "default config/mlek_baseline.json")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prof = json.loads(pathlib.Path(a.profile).read_text())
    ids = sorted(int(x) for x in IDS.read_text().split())
    per_run, summary = analyse(pathlib.Path(a.root), json.loads(MANIFEST.read_text())["workloads"], prof, ids)
    for label, root, mpath in a.add:
        rows, summ = analyse(pathlib.Path(root), json.loads(pathlib.Path(mpath).read_text())["workloads"], prof, ids,
                             label)
        per_run += rows; summary.update(summ)
    with open(out / "per_run.csv", "w", newline="") as f:
        cols = list(per_run[0].keys()) if per_run else []
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(per_run)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["workload", "class", "status", "metric", "n", "median", "mean", "std", "cv",
                                       "min", "max", "deterministic"])
        for name, e in summary.items():
            for k, s in e.get("metrics", {}).items():
                w.writerow([name, e["class"], e["status"], k] + [s[c] for c in ("n", "median", "mean", "std", "cv",
                                                                                 "min", "max", "deterministic")])
    (out / "summary.json").write_text(json.dumps({"ta_state": prof["ta_state"], "workloads": summary}, indent=1,
                                                 default=str))
    (out / "fingerprint_table.md").write_text(fingerprint(summary))
    print(fingerprint(summary))
    return 0 if all(e["status"] == "VALID" for e in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
