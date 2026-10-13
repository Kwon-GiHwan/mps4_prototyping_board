"""Reference data kept in docs/reference/: PMU event lists and MLEK's board NPU ACTIVE."""
from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
REF = REPO / "docs" / "reference"


def driver_ids() -> dict[int, str]:
    """All 171 event ids of the U85 driver header, id -> name."""
    return {int(v): n for v, n in json.loads((REF / "driver_events_171.json").read_text())}


def trm_ids() -> set[int]:
    """The 110 event ids the TRM describes."""
    return {int(v) for v, _, _ in json.loads((REF / "trm_events_110.json").read_text())}


def mlek_active() -> dict[str, int]:
    """MLEK board NPU ACTIVE, median of boots B1-B3, per workload (TA: MLEK profile)."""
    return {n: w["ACTIVE_median"] for n, w in json.loads((REF / "mlek_board_reference.json").read_text())["workloads"].items()}


def mlek_b1(workload: str) -> dict[str, int]:
    """MLEK board B1 counters of one workload by MLEK name (ACTIVE, SRAM_/EXT_ beats, IDLE, TOTAL)."""
    return json.loads((REF / "mlek_board_reference.json").read_text())["workloads"][workload]["B1"]
