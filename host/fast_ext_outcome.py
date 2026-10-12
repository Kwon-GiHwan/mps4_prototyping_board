"""Outcome for the fast-scratch-on-EXT run (contract 2026-10-12-u85-fast-scratch-ext-contract.md).

    python3 host/fast_ext_outcome.py evidence/u85_fast_ext     (after screening_metrics.py on that root)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# name: (MLEK ACTIVE median B1-B3, screening-2 npu_active median, MLEK EXT rd, EXT wr, SRAM rd, SRAM wr)
REF = {
    "kws_micronet_m": (91_431, 334_714, 15_815, 1, 22_664, 17_760),
    "ad_medium_int8": (145_976, 951_418, 44_084, 1, 70_538, 41_888),
    "mobilenet_v2_1.0_224_INT8": (1_448_049, 10_121_486, 301_217, 47_887, 672_948, 401_443),
}
OUTCOMES = ("FAST_PATH_EXPLAINS", "FAST_PATH_PARTIAL", "FAST_PATH_NOT_CAUSE", "UNPROVEN")


def outcome(screen_outcome: str, r: float, mlek: float, s2: float) -> str:
    if screen_outcome != "SCREENED":
        return "UNPROVEN"
    if r <= 1.25 * mlek:
        return "FAST_PATH_EXPLAINS"
    if r >= 0.8 * s2:
        return "FAST_PATH_NOT_CAUSE"
    return "FAST_PATH_PARTIAL"


def main(root: str) -> None:
    rows = {r["name"]: r for r in json.load(open(Path(root) / "screening_summary.json"))}
    print("| workload | outcome | npu_active R | R / MLEK | R / screening 2 | EXT rd / expected | EXT wr / expected |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for name, (m, s2, erd, ewr, srd, swr) in REF.items():
        row = rows.get(name)
        if row is None or row["outcome"] == "NOT_EXECUTABLE":
            print(f"| {name} | UNPROVEN | N/A | N/A | N/A | N/A | N/A |")
            continue
        r = row["summary"]["npu_active"]["median"]
        n_mac = row["n_mac"]
        rd = row["summary"]["ext_rd_beats_per_mac"]["median"] * n_mac
        wr = row["summary"]["ext_wr_beats_per_mac"]["median"] * n_mac
        print(f"| {name} | {outcome(row['outcome'], r, m, s2)} | {r:,.0f} | {r / m:.2f} | {r / s2:.2f} | "
              f"{rd / (erd + srd):.3f} | {wr / (ewr + swr):.3f} |")


if __name__ == "__main__":
    main(sys.argv[1])
