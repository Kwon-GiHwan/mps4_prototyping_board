"""Reading a campaign's runs.csv (one row per event per RUN, written by run_pmu_events.py)."""
from __future__ import annotations

import csv
from pathlib import Path

WARMUP, MEASURED = 5, 30   # RUNs 1..WARMUP are warm-up; analyses need MEASURED valid RUNs after them
EVENTS = {35: "npu_active", 48: "mac_active", 386: "ext_rd_beats", 391: "ext_wr_beats",
          387: "ext_rd_req_stall", 392: "ext_wr_req_stall", 393: "ext_wr_data_stall", 396: "ext_enabled"}


def event_name(ev: int) -> str:
    return EVENTS.get(ev, f"ev{ev}")


def load_runs(path: Path) -> list[dict]:
    """One dict per RUN, by rep: rep, valid, overflow, window_cycles and every event by name (None if invalid)."""
    runs: dict[int, dict] = {}
    for r in csv.DictReader(open(path)):
        rep = int(r["rep"])
        run = runs.setdefault(rep, {"rep": rep, "valid": r["run_valid"] == "True", "overflow": False,
                                    "window_cycles": int(r["window_cycles"]) if r["window_cycles"] else None})
        run["overflow"] |= r["event_overflow"] not in ("0", "False", "")
        run[event_name(int(r["ev_type"]))] = int(r["event_value"]) if r["event_value"] not in ("", "None") else None
    return [runs[k] for k in sorted(runs)]


def measured_valid(runs: list[dict]) -> list[dict]:
    """The RUNs an analysis may use: after the warm-up, and valid."""
    return [r for r in runs if r["rep"] > WARMUP and r["valid"]]
