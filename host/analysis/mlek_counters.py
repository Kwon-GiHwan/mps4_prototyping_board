#!/usr/bin/env python3
"""MLEK profiler counters from an app-UART capture: the "INFO - NPU <name>: <value> <unit>" lines after
"Profile for Inference:". Names as MLEK prints them; the stock build prints ACTIVE, four beat counters, IDLE and TOTAL,
the instrumented build (host/container/mlek_profiler_events.py) also MAC_ACTIVE, MAC_DPU_ACTIVE and AO_ACTIVE.

  python3 host/analysis/mlek_counters.py <app_uart.raw>   -> JSON {name: value}
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

MARK = "Profile for Inference:"
LINE = re.compile(r"^INFO - NPU (?:ETHOSU_PMU_)?([A-Z0-9_ ]+): (\d+) (cycles|beats)\s*$")
# MLEK print name -> the runner's driver event id (docs/reference/driver_events_171.json); IDLE/TOTAL have none.
EVENT_ID = {"ACTIVE": 35, "SRAM_RD_DATA_BEAT_RECEIVED": 130, "SRAM_WR_DATA_BEAT_WRITTEN": 135,
            "EXT_RD_DATA_BEAT_RECEIVED": 386, "EXT_WR_DATA_BEAT_WRITTEN": 391, "MAC_ACTIVE": 48,
            "MAC_DPU_ACTIVE": 51, "AO_ACTIVE": 64}


def counters(text: str) -> dict[str, int]:
    """Counters of the one profiled inference (CR removed). Refuses a capture with no profile or two profiles."""
    if text.count(MARK) != 1:
        raise ValueError(f"{text.count(MARK)} '{MARK}' blocks, need 1")
    out: dict[str, int] = {}
    for ln in text.split(MARK, 1)[1].splitlines()[1:]:
        m = LINE.match(ln.strip())
        if not m:
            if out:
                break
            continue
        name = m.group(1).strip()
        if name in out:
            raise ValueError(f"counter {name} printed twice")
        out[name] = int(m.group(2))
    if "ACTIVE" not in out:
        raise ValueError("no NPU ACTIVE line in the profile")
    return out


if __name__ == "__main__":
    t = pathlib.Path(sys.argv[1]).read_bytes().decode("ascii", "replace").replace("\r", "")
    print(json.dumps(counters(t), indent=1))
