"""Reading a campaign's runs.csv (one row per event per RUN, written by run_pmu_events.py)."""
from __future__ import annotations

import csv
from pathlib import Path

WARMUP, MEASURED = 5, 30   # RUNs 1..WARMUP are warm-up; analyses need MEASURED valid RUNs after them
EVENTS = {17: "cycle", 32: "npu_idle", 35: "npu_active", 48: "mac_active", 130: "sram_rd_beats", 135: "sram_wr_beats",
          140: "sram_enabled", 386: "ext_rd_beats", 391: "ext_wr_beats",
          387: "ext_rd_req_stall", 392: "ext_wr_req_stall", 393: "ext_wr_data_stall", 396: "ext_enabled"}


def event_name(ev: int) -> str:
    return EVENTS.get(ev, f"ev{ev}")


def _int(text):
    return int(text) if text not in (None, "", "None") else None


def load_runs(path: Path) -> list[dict]:
    """One dict per RUN, by rep: rep, valid, overflow, window_cycles, run_rc, vendor_rc, ofm_mismatch (None when
    the column is absent) and every event by name (None if invalid)."""
    runs: dict[int, dict] = {}
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        rep = int(r["rep"])
        run = runs.setdefault(rep, {"rep": rep, "valid": r["run_valid"] == "True", "overflow": False,
                                    "window_cycles": int(r["window_cycles"]) if r["window_cycles"] else None,
                                    **{k: _int(r.get(c)) for k, c in (("run_rc", "run_rc"), ("vendor_rc", "vendor_rc"),
                                                                     ("ofm_mismatch", "ofm_mismatch_count"))}})
        run["overflow"] |= r["event_overflow"] not in ("0", "False", "")
        run[event_name(int(r["ev_type"]))] = int(r["event_value"]) if r["event_value"] not in ("", "None") else None
    return [runs[k] for k in sorted(runs)]


def measured_valid(runs: list[dict]) -> list[dict]:
    """The RUNs an analysis may use: after the warm-up, and valid."""
    return [r for r in runs if r["rep"] > WARMUP and r["valid"]]
