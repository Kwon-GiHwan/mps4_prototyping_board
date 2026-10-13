#!/usr/bin/env python3
"""Stage-0 per-run gate and MLEK verification outcome (docs/specs/mlek-baseline.md sections 2-3).

  python3 host/baseline_gate.py <campaign dir holding <workload>/{runs.csv,summary.json}> [--manifest M] [--out OUTCOME.json]

Gate per workload: BASELINE_PASS / BASELINE_FAIL / UNPROVEN / INVALID (amendment 1: the blob's IFM or golden is not
the manifest's, so the output comparison means nothing). Outcome per workload and overall:
MLEK_EQUIVALENT / MLEK_DIFFERENT / UNRESOLVED.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pmwl
import reference
import results
from pack_vela_workload import from_profile

REPO = pathlib.Path(__file__).resolve().parents[1]
PROFILE = REPO / "config" / "mlek_baseline.json"
MANIFEST = REPO / "config" / "mlek_baseline.manifest.json"
ACTIVE_TOL = 0.01      # |npu_active - MLEK| / MLEK
CYCLE_TOL = 0.01       # |cycle - window| / window
BEATS = (("sram_rd_beats", "SRAM_RD_DATA_BEAT_RECEIVED"), ("sram_wr_beats", "SRAM_WR_DATA_BEAT_WRITTEN"),
         ("ext_rd_beats", "EXT_RD_DATA_BEAT_RECEIVED"), ("ext_wr_beats", "EXT_WR_DATA_BEAT_WRITTEN"))


def boot_checks(summ: dict, prof: dict, man: dict, ids: list[int]) -> list[str]:
    """B1-B3: failed check names for one boot's summary.json."""
    kargs, _ = from_profile(prof, prof["vela"]["version"])
    want_knobs = [f"0x{w:08x}" for w in pmwl.knobs(**kargs)]
    prov = summ.get("provenance", {})
    failed = []
    if any(prov.get(k) != v for k, v in prof["image"].items()):
        failed.append("B1_image")
    if (summ.get("blob_sha256") != man["blob_sha256"] or summ.get("cms_sha256") != man["cms_sha256"]
            or summ.get("blob_knobs") != want_knobs):
        failed.append("B2_blob")
    if (summ.get("requested_ids") != ids or not str(summ.get("coverage", "")).startswith("COMPLETE")
            or summ.get("refusal") is not None or summ.get("runs") != prof["repeats"]):
        failed.append("B3_set")
    return failed


def run_checks(run: dict) -> list[str]:
    """R1-R6: failed check names for one RUN (results.load_runs dict)."""
    a, w, c = run.get("npu_active"), run.get("window_cycles"), run.get("cycle")
    checks = {
        "R1_valid": run["valid"],
        "R2_rc": run["run_rc"] == 0,
        "R3_output": run["vendor_rc"] == 0 and run["ofm_mismatch"] == 0,
        "R4_overflow": not run["overflow"],
        "R5_active": a is not None and w is not None and 0 < a <= w,
        "R6_cycle": c is not None and bool(w) and abs(c - w) / w <= CYCLE_TOL,
    }
    return [k for k, ok in checks.items() if not ok]


def gate(wdir: pathlib.Path, prof: dict, man: dict, ids: list[int]) -> dict:
    if not (wdir / "summary.json").exists() or not (wdir / "runs.csv").exists():
        return {"gate": "UNPROVEN", "why": "missing summary.json or runs.csv"}
    summ = json.loads((wdir / "summary.json").read_text())
    gold = man.get("golden")
    if gold and (summ.get("ifm_sha256") != gold["input_sha256"] or summ.get("golden_sha256") != gold["ofm_sha256"]):
        return {"gate": "INVALID", "why": "B4: blob IFM or golden differs from the manifest's"}
    runs = results.load_runs(wdir / "runs.csv")
    failed_boot = boot_checks(summ, prof, man, ids)
    failed_runs = {r["rep"]: f for r in runs if (f := run_checks(r))}
    ok = not failed_boot and not failed_runs and len(runs) == prof["repeats"]
    return {"gate": "BASELINE_PASS" if ok else "BASELINE_FAIL", "failed_boot": failed_boot,
            "failed_runs": failed_runs, "runs": len(runs)}


def outcome(g: dict, runs: list[dict], mlek: dict) -> dict:
    if g["gate"] != "BASELINE_PASS":
        return {"outcome": "UNRESOLVED"}
    m = results.measured_valid(runs)
    med = {k: statistics.median(r[k] for r in m) for k in ["npu_active"] + [ours for ours, _ in BEATS]}
    beats_equal = all(med[ours] == mlek[theirs] for ours, theirs in BEATS)
    delta = (med["npu_active"] - mlek["ACTIVE_median"]) / mlek["ACTIVE_median"]
    eq = beats_equal and abs(delta) <= ACTIVE_TOL
    return {"outcome": "MLEK_EQUIVALENT" if eq else "MLEK_DIFFERENT", "measured": len(m), "medians": med,
            "mlek_active_median": mlek["ACTIVE_median"], "active_delta": delta, "beats_equal": beats_equal}


def overall(per: list[str]) -> str:
    if not per or "UNRESOLVED" in per:
        return "UNRESOLVED"
    return "MLEK_DIFFERENT" if "MLEK_DIFFERENT" in per else "MLEK_EQUIVALENT"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--out"); ap.add_argument("--manifest", default=str(MANIFEST))
    a = ap.parse_args()
    prof = json.loads(PROFILE.read_text())
    mpath = pathlib.Path(a.manifest)
    man = json.loads(mpath.read_text())["workloads"] if mpath.exists() else {}
    ids = sorted(int(x) for x in (REPO / prof["pmu_ids_file"]).read_text().split())
    res = {}
    for name in sorted(man):   # every workload of the manifest; a missing directory is UNPROVEN
        wdir = pathlib.Path(a.root) / name
        g = gate(wdir, prof, man[name], ids)
        runs = results.load_runs(wdir / "runs.csv") if g["gate"] != "UNPROVEN" else []
        mlek = dict(reference.mlek_b1(name), ACTIVE_median=reference.mlek_active()[name])
        res[name] = {**g, **outcome(g, runs, mlek)}
        if "numerical_difference_diagnostic" in man[name]:   # reported only, never used for pass/fail
            res[name]["numerical_difference_diagnostic"] = man[name]["numerical_difference_diagnostic"]
    res = {"ta_state": prof["ta_state"], "manifest": mpath.name, "workloads": res, "overall": overall([w["outcome"] for w in res.values()])}
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(text)
    print(text)
    return 0 if res["overall"] == "MLEK_EQUIVALENT" else 1


if __name__ == "__main__":
    sys.exit(main())
