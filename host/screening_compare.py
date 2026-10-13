"""Screening 2 (MLEK-Vela-aligned) vs screening 1: per-workload median ratios (contract 2026-10-12-u85-screening-mlek-contract.md).

Descriptive only: ratios of medians, no thresholds. A ratio is reported only when both sides are SCREENED.

    python3 host/screening_compare.py evidence/u85_screening evidence/u85_screening_mlek
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

METRICS = ("npu_active", "peak_mac_efficiency", "mac_active_ratio", "ext_beats_per_mac",
           "ext_read_req_stall_ratio", "ext_write_req_stall_ratio", "ext_write_data_stall_ratio")


def cms_changed(old_meta: dict, new_meta: dict) -> bool:
    return old_meta["vela_sha256"] != new_meta["vela_sha256"]


def ratio_row(old: dict, new: dict) -> dict:
    """old/new: one screening_summary.json entry each."""
    if old["outcome"] != "SCREENED" or new["outcome"] != "SCREENED":
        return {m: None for m in METRICS}
    row = {}
    for m in METRICS:
        a, b = old["summary"][m].get("median"), new["summary"][m].get("median")
        row[m] = b / a if a and b is not None else None
    return row


def main(old_root: str, new_root: str) -> None:
    old = {r["name"]: r for r in json.load(open(Path(old_root) / "screening_summary.json"))}
    new = {r["name"]: r for r in json.load(open(Path(new_root) / "screening_summary.json"))}
    out = ["| workload | cms changed | outcome 1 → 2 | " + " | ".join(f"{m} (2/1)" for m in METRICS) + " |",
           "|" + " --- |" * (len(METRICS) + 3)]
    for name in new:
        pm = lambda root: json.load(open(Path(root) / "workloads" / f"{name}.pmwl.json"))
        row = ratio_row(old[name], new[name])
        cells = ["N/A" if row[m] is None else f"{row[m]:.3f}" for m in METRICS]
        out.append(f"| {name} | {cms_changed(pm(old_root), pm(new_root))} | {old[name]['outcome']} → "
                   f"{new[name]['outcome']} | " + " | ".join(cells) + " |")
    print("\n".join(out))


if __name__ == "__main__":
    main(*sys.argv[1:3])
