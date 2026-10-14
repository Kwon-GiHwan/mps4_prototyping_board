#!/usr/bin/env python3
"""Stage 2A component attribution (evidence/stage2a/contract.md): gate every RUN, derive metrics A-I, check Stage 1
reproduction, compare with conv3x3 and give every hypothesis a status from the closed set.

  python3 host/analysis/stage2a.py <campaign dir holding <workload>/{runs.csv,summary.json}> <out dir>

Writes per_run.csv, summary.csv, summary.json and tables.md into <out dir>. Hypotheses are judged only when all three
operators are VALID and REPRODUCED (contract §10); otherwise they are reported as not interpreted.
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import results
from baseline_gate import PROFILE, gate
from stage1 import M_CONFIGURED, stage1_checks, stats

REPO = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO / "evidence" / "stage2a" / "manifest.json"
STAGE1_SUMMARY = REPO / "evidence" / "stage1" / "summary.json"
IDS = REPO / "config" / "stage2a_ids.txt"
REF = "conv3x3"
OPERATORS = ("dw3x3", "pw1x1")
STAGE1_REF = {"conv3x3": "conv3x3@a2", "dw3x3": "dw3x3", "pw1x1": "pw1x1@a2"}   # boots 72, 69, 73
RAW = ("npu_active", "mac_active", "mac_dpu_active", "mac_stalled_by_w_or_acc", "mac_stalled_by_ib", "ao_active",
       "wd_active", "wd_stalled")
DRIVER_DERIVED = ("mac_stalled_by_w_or_acc", "mac_stalled_by_ib")
DERIVED = ("mac_active_ratio", "dpu_active_ratio", "dpu_given_mac_active", "ao_active_ratio", "wd_active_ratio",
           "wd_stalled_ratio", "mac_ib_stall_ratio", "mac_w_or_acc_stall_ratio", "mac_active_cycle_efficiency")
STAGE1_SHOWN = ("peak_mac_efficiency", "mac_active_cycle_efficiency", "sram_beats_per_mac", "ext_beats_per_mac")
# MAC-inactivity hypotheses: id -> (counter metric, semantics source); H3 (event 33) is not measured
INACTIVITY = {"H1": ("wd_stalled_ratio", "TRM"), "H2": ("mac_ib_stall_ratio", "driver"),
              "H3b": ("mac_w_or_acc_stall_ratio", "driver"), "H4": ("ao_active_ratio", "TRM")}
STALLS = ("wd_stalled_ratio", "mac_ib_stall_ratio", "mac_w_or_acc_stall_ratio")


def derive(run: dict, n_mac: int) -> dict:
    a, m = run["npu_active"], run["mac_active"]
    return {"mac_active_ratio": m / a, "dpu_active_ratio": run["mac_dpu_active"] / a,
            "dpu_given_mac_active": run["mac_dpu_active"] / m if m else None,
            "ao_active_ratio": run["ao_active"] / a, "wd_active_ratio": run["wd_active"] / a,
            "wd_stalled_ratio": run["wd_stalled"] / a, "mac_ib_stall_ratio": run["mac_stalled_by_ib"] / a,
            "mac_w_or_acc_stall_ratio": run["mac_stalled_by_w_or_acc"] / a,
            "mac_active_cycle_efficiency": n_mac / (M_CONFIGURED * m) if m else None}


def diagnostics(run: dict) -> dict:
    """S1-S3 (contract §4): recorded, never used for validity."""
    a, m, ib, wa = run["npu_active"], run["mac_active"], run["mac_stalled_by_ib"], run["mac_stalled_by_w_or_acc"]
    return {"S1_mac_plus_ib_le_npu": m + ib <= a, "S2_mac_plus_ib_plus_wacc_le_npu": m + ib + wa <= a,
            "S3_dpu_le_npu": run["mac_dpu_active"] <= a}


def analyse(root: pathlib.Path, man: dict, prof: dict, ids: list[int]) -> tuple[list[dict], dict]:
    per_run, summary = [], {}
    for name, w in man.items():
        g = gate(root / name, prof, w, ids, stage1_checks)
        runs = results.load_runs(root / name / "runs.csv") if (root / name / "runs.csv").exists() else []
        boot_ok = g["gate"] == "BASELINE_PASS"
        rows = []
        for r in runs:
            failed = g.get("failed_runs", {}).get(r["rep"], [])
            complete = all(r.get(k) is not None for k in RAW) and r["npu_active"]
            row = dict(experiment_id="stage2a", profile_id=prof["name"], workload=name, run_id=r["rep"],
                       warmup_or_measured="warmup" if r["rep"] <= results.WARMUP else "measured",
                       input_sha256=w["golden"]["input_sha256"], golden_sha256=w["golden"]["ofm_sha256"],
                       blob_sha256=w["blob_sha256"], command_stream_sha256=w["cms_sha256"], n_mac=w["n_mac"],
                       pmccntr=r["window_cycles"], **{k: r.get(k) for k in RAW},
                       output_valid="R3_output" not in failed, knobs_honoured=r["run_rc"] != 0x7D,
                       overflow=bool(r["overflow"]), consistency_valid=not ({"R5_active", "R6s_mac_le_npu"} & set(failed)),
                       run_valid=boot_ok and not failed, failed_checks=";".join(failed))
            row.update(derive(r, w["n_mac"]) if complete else {k: None for k in DERIVED})
            row.update(diagnostics(r) if complete else {})
            rows.append(row)
        per_run += rows
        entry = {"workload": name, "n_mac": w["n_mac"], "gate": g["gate"], "failed_boot": g.get("failed_boot"),
                 "failed_runs": g.get("failed_runs"), "status": "VALID" if boot_ok else "UNRESOLVED"}
        if "numerical_difference_diagnostic" in w:   # reported only, never used for pass/fail
            entry["numerical_difference_diagnostic"] = w["numerical_difference_diagnostic"]
        if boot_ok:
            measured = [p for p in rows if p["warmup_or_measured"] == "measured"]
            entry["metrics"] = {k: stats([p[k] for p in measured]) for k in RAW + ("pmccntr",) + DERIVED
                                if all(p[k] is not None for p in measured)}
            entry["diagnostic_violations"] = {k: sum(not p[k] for p in measured) for k in diagnostics(measured[0])}
        summary[name] = entry
    return per_run, summary


def reproduction(metrics: dict, ref: dict) -> dict:
    """Contract §5: MAC_ACTIVE equal to the deterministic reference in every measured RUN; NPU_ACTIVE median inside
    the reference's measured [min, max]."""
    mac, npu = metrics["mac_active"], metrics["npu_active"]
    ok_mac = ref["mac_active"]["deterministic"] and mac["min"] == mac["max"] == ref["mac_active"]["median"]
    ok_npu = ref["npu_active"]["min"] <= npu["median"] <= ref["npu_active"]["max"]
    return {"result": "REPRODUCED" if ok_mac and ok_npu else "NOT_REPRODUCED", "mac_active_equal": ok_mac,
            "npu_active_median_in_range": ok_npu, "npu_active_median": npu["median"],
            "ref_npu_active_range": [ref["npu_active"]["min"], ref["npu_active"]["max"]],
            "mac_active": [mac["min"], mac["max"]], "ref_mac_active": ref["mac_active"]["median"]}


def separation(op: dict, ref: dict) -> str:
    """Contract §7: run-to-run separation of two metric distributions."""
    if op["min"] > ref["max"]:
        return "HIGHER"
    if op["max"] < ref["min"]:
        return "LOWER"
    return "OVERLAP"


def inactivity_status(op: dict, ref: dict, metric: str, source: str) -> dict:
    """H1, H2, H3b, H4 for one operator (contract §8)."""
    sep = separation(op[metric], ref[metric])
    excess = op[metric]["median"] - ref[metric]["median"]
    gap = ref["mac_active_ratio"]["median"] - op["mac_active_ratio"]["median"]
    if separation(op["mac_active_ratio"], ref["mac_active_ratio"]) != "LOWER":
        status = "UNRESOLVED"
    elif sep == "HIGHER":
        covers = excess >= gap
        status = {("TRM", True): "SUPPORTED", ("TRM", False): "PARTIAL_SUPPORT",
                  ("driver", True): "PARTIAL_SUPPORT", ("driver", False): "CORRELATED_ONLY"}[(source, covers)]
    elif sep == "OVERLAP" and excess > 0:
        status = "UNRESOLVED"
    else:
        status = "REFUTED"
    return {"status": status, "counter": metric, "source": source, "separation": sep, "median_excess": excess,
            "excess_inactive_share": gap}


def efficiency_status(op: dict, ref: dict) -> dict:
    """H5 and H6 for one operator (contract §8)."""
    low = separation(op["mac_active_cycle_efficiency"], ref["mac_active_cycle_efficiency"]) == "LOWER"
    c = separation(op["dpu_given_mac_active"], ref["dpu_given_mac_active"])
    stalls_higher = [s for s in STALLS if separation(op[s], ref[s]) == "HIGHER"]
    if not low:
        h5 = h6 = "REFUTED"
    else:
        h5 = "REFUTED" if c == "LOWER" else ("UNRESOLVED" if stalls_higher else "SUPPORTED")
        h6 = {"LOWER": "SUPPORTED", "HIGHER": "REFUTED", "OVERLAP": "UNRESOLVED"}[c]
    detail = {"active_cycle_efficiency_lower": low, "dpu_given_mac_active": c, "stalls_higher": stalls_higher}
    return {"H5": dict(status=h5, **detail), "H6": dict(status=h6, **detail)}


ROUTES = {"H1": ({"SUPPORTED", "PARTIAL_SUPPORT"}, "Stage 3: weight-stream supply"),
          "H2": ({"PARTIAL_SUPPORT", "CORRELATED_ONLY"}, "Stage 3: IFM supply, confirm with a TRM event"),
          "H3b": ({"PARTIAL_SUPPORT", "CORRELATED_ONLY"}, "Stage 3: split 52 into 53/54 with weight-supply counters"),
          "H4": ({"SUPPORTED", "PARTIAL_SUPPORT"}, "Stage 3: output/write side"),
          "H5": ({"SUPPORTED"}, "Stage 4: shape sweep"),
          "H6": ({"SUPPORTED"}, "Stage 4: shape sweep (DPU occupancy vs channels)")}


def hypotheses(summary: dict) -> dict:
    ref = summary[REF]["metrics"]
    out = {}
    for name in OPERATORS:
        op = summary[name]["metrics"]
        h = {k: inactivity_status(op, ref, m, src) for k, (m, src) in INACTIVITY.items()}
        h["H3"] = {"status": "UNRESOLVED", "counter": "event 33 (not measured)"}
        h.update(efficiency_status(op, ref))
        no_component = not any(h[k]["status"] in ("SUPPORTED", "PARTIAL_SUPPORT") for k in INACTIVITY)
        routes = [why for k, (hit, why) in ROUTES.items() if h[k]["status"] in hit]
        if no_component:
            routes.append("Stage 3: SRAM/EXT request stall, outstanding, AXI latency (pattern 6)")
        out[name] = {"hypotheses": h, "component_evidence_for_low_mac_activity": not no_component, "routes": routes}
    return out


def comparisons(summary: dict) -> dict:
    pairs = (("dw3x3", "conv3x3"), ("pw1x1", "conv3x3"), ("dw3x3", "pw1x1"))
    out = {}
    for a, b in pairs:
        ma, mb = summary[a]["metrics"], summary[b]["metrics"]
        out[f"{a}_vs_{b}"] = {k: {"ratio_of_medians": (ma[k]["median"] / mb[k]["median"]) if mb[k]["median"] else None,
                                  "separation": separation(ma[k], mb[k])} for k in RAW + DERIVED}
    return out


TABLE = (("NPU cycles", "npu_active", "{:,.0f}"), ("MAC active ratio", "mac_active_ratio", "{:.1%}"),
         ("DPU active ratio", "dpu_active_ratio", "{:.1%}"), ("DPU / MAC-active", "dpu_given_mac_active", "{:.3f}"),
         ("AO active ratio", "ao_active_ratio", "{:.1%}"), ("WD active ratio", "wd_active_ratio", "{:.1%}"),
         ("WD stalled ratio", "wd_stalled_ratio", "{:.1%}"), ("IB stall ratio †", "mac_ib_stall_ratio", "{:.1%}"),
         ("W/ACC stall ratio †", "mac_w_or_acc_stall_ratio", "{:.1%}"))


def table(summary: dict) -> str:
    head = "| operator | " + " | ".join(c for c, _, _ in TABLE) + " | CV(NPU active) |"
    lines = [head, "|" + " --- |" * (len(TABLE) + 2)]
    for name, e in summary.items():
        if e["status"] != "VALID":
            lines.append(f"| {name} | {e['gate']} |" + " |" * len(TABLE))
            continue
        m = e["metrics"]
        lines.append(f"| {name} | " + " | ".join(f.format(m[k]["median"]) for _, k, f in TABLE)
                     + f" | {m['npu_active']['cv']:.2%} |")
    return "\n".join(lines) + "\n\n† driver-derived event (contract §2)\n"


def main() -> int:
    root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    prof = json.loads(PROFILE.read_text())
    ids = sorted(int(x) for x in IDS.read_text().split())
    per_run, summary = analyse(root, json.loads(MANIFEST.read_text())["workloads"], prof, ids)
    s1 = json.loads(STAGE1_SUMMARY.read_text())["workloads"]
    for name, e in summary.items():
        ref = s1[STAGE1_REF[name]]
        e["stage1_reference"] = {"entry": STAGE1_REF[name], "dataset": ref["dataset"],
                                 **{k: ref["metrics"][k]["median"] for k in STAGE1_SHOWN}}
        if e["status"] == "VALID":
            e["reproduction"] = reproduction(e["metrics"], ref["metrics"])
    ok = all(e["status"] == "VALID" and e["reproduction"]["result"] == "REPRODUCED" for e in summary.values())
    doc = {"ta_state": prof["ta_state"], "event_ids": {results.event_name(i): i for i in ids},
           "driver_derived": list(DRIVER_DERIVED), "workloads": summary,
           "comparisons": comparisons(summary) if ok else "not computed: an operator is not VALID or not REPRODUCED",
           "hypotheses": hypotheses(summary) if ok else "not interpreted (contract §10)"}
    with open(out / "per_run.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_run[0].keys())); w.writeheader(); w.writerows(per_run)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["workload", "status", "metric", "n", "median", "mean", "std", "cv", "min", "max", "deterministic"])
        for name, e in summary.items():
            for k, s in e.get("metrics", {}).items():
                w.writerow([name, e["status"], k] + [s[c] for c in ("n", "median", "mean", "std", "cv", "min", "max",
                                                                    "deterministic")])
    (out / "summary.json").write_text(json.dumps(doc, indent=1, default=str))
    (out / "tables.md").write_text(table(summary))
    print(table(summary))
    for name, e in summary.items():
        print(name, e["gate"], e.get("reproduction", {}).get("result"), e.get("diagnostic_violations"))
    if ok:
        for name, h in doc["hypotheses"].items():
            print(name, {k: v["status"] for k, v in h["hypotheses"].items()}, h["routes"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
