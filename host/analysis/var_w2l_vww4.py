#!/usr/bin/env python3
"""Owner item 2 (evidence/var_w2l_vww4/contract.md): the wav2letter instrumented-build shift (W) and vww4's boot-to-boot
NPU_ACTIVE spread (V). TA profile 1 everywhere.

  python3 host/analysis/var_w2l_vww4.py <main repo> <driver repo> <out dir>

Datasets are fixed below (= the contract's list); a missing or invalid one makes its outcome UNPROVEN.
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import equiv_c as EC  # noqa: E402
import fi101_s013 as S  # noqa: E402
import mlek_counters as MC  # noqa: E402

W2L, VWW4 = "wav2letter_pruned_int8", "vww4_128_128_INT8"
BEATS = EC.BEATS
W_ORDER = ("W1_stock", "W2_events", "W3_events", "W4_stock", "W5_events", "W6_stock", "W7_stock", "W8_events")
DRIVER_VWW4 = ("evidence/driver_m7/raw/wfe", "evidence/driver_m7/raw_r2/wfe", "evidence/driver_m7/raw_r3/wfe")
LEGACY_VWW4_SEED1 = ("evidence/fi101_s013/raw/x1", "evidence/s2_mask/raw/ctl", "evidence/s2_mask/raw/ctl2",
                     "evidence/s2b3_pilot/raw_a1/ctl", "evidence/s2b3_pilot/raw_a1/ctl2")   # boots 97, 192, 196, 281, 287
LEGACY_VWW4_MLEK_INPUT = "evidence/equiv_c/raw_cd_a1/cd"                                 # boot 306
UP = "UNPROVEN"


def capture(path: pathlib.Path) -> dict | None:
    """MLEK counters of a valid capture (one profile, both TA lines, program end), else None."""
    if not path.exists():
        return None
    t = path.read_bytes().decode("ascii", "replace").replace("\r", "")
    if t.count("Configured TA") != 2 or "program terminating" not in t:
        return None
    try:
        return MC.counters(t)
    except ValueError:
        return None


def rng(xs):
    return max(xs) - min(xs)


def shift(stock: list[int], events: list[int], n: int) -> str:
    """W1 on the interleaved boots: complete separation in either direction, the M3 rule, or UNPROVEN."""
    if len(stock) != n or len(events) != n:
        return UP
    if max(events) < min(stock):
        return "SHIFT_REPRODUCED"
    if min(events) > max(stock):
        return "SHIFT_REVERSED"
    if abs(statistics.median(events) - statistics.median(stock)) <= max(rng(events), rng(stock)):
        return "NO_SHIFT"
    return UP


def w_part(main: pathlib.Path, drv: pathlib.Path) -> dict:
    old = {v: [capture(p) for p in sorted((main / f"evidence/equiv_c/raw_bc/{W2L}/{v}").glob("B*/app_uart.raw"))]
           for v in ("stock", "events")}
    new = {k: capture(drv / "evidence/var_w2l_vww4/raw" / k / "app_uart.raw") for k in W_ORDER}
    act = lambda caps: [c["ACTIVE"] for c in caps if c]
    ns = [new[k] for k in W_ORDER if k.endswith("stock")]
    ne = [new[k] for k in W_ORDER if k.endswith("events")]
    ref_beats = {k: old["stock"][0][k] for k in BEATS} if old["stock"] and old["stock"][0] else None
    caps = [c for c in new.values() if c]
    beats = UP if not ref_beats or len(caps) != len(W_ORDER) else \
        "BEATS_FIXED" if all(all(c[k] == ref_beats[k] for k in BEATS) for c in caps) else "BEATS_DIFFER"
    res = dict(W1=shift(act(ns), act(ne), 4), W2=beats,
               new_stock_active=act(ns), new_events_active=act(ne),
               old_stock_active=act(old["stock"]), old_events_active=act(old["events"]))
    pooled_s, pooled_e = [c for c in old["stock"] + ns if c], [c for c in old["events"] + ne if c]
    sup = {}
    for name, root in (("legacy_cd", main / "evidence/equiv_c/raw_cd/cd"), ("driver_m7", drv / DRIVER_VWW4[0])):
        rows = EC.runner_rows(root / W2L) if (root / W2L / "runs.csv").exists() else []
        sup[name] = EC.model(pooled_s, pooled_e, rows)
    res["W3_supplementary_M4_all_boots"] = sup
    return res


def first_runs(folder: pathlib.Path) -> list[int]:
    """V5: NPU_ACTIVE of the first RUN after boot (set 1, rep 1; a warm-up RUN) - MLEK runs one inference per boot."""
    if not (folder / "runs.csv").exists():
        return []
    with (folder / "runs.csv").open() as f:
        return [int(r["event_value"]) for r in csv.DictReader(f)
                if r["set_id"] == "1" and r["rep"] == "1" and r["ev_type"] == "35" and r["event_value"] not in ("", "None")]


def boot_median(folder: pathlib.Path) -> tuple[float, int] | None:
    if not (folder / "runs.csv").exists():
        return None
    a = S.values(S.load_runs(folder, 2), 35)
    return (statistics.median(a), rng(a)) if a else None


def v_part(main: pathlib.Path, drv: pathlib.Path) -> dict:
    mlek = [c["ACTIVE"] for v in ("stock", "events")
            for c in (capture(p) for p in sorted((main / f"evidence/equiv_c/raw_bc/{VWW4}/{v}").glob("B*/app_uart.raw")))
            if c]
    stock = [c["ACTIVE"] for c in (capture(p) for p in
                                   sorted((main / f"evidence/equiv_c/raw_bc/{VWW4}/stock").glob("B*/app_uart.raw"))) if c]
    drivers = [boot_median(drv / r / VWW4) for r in DRIVER_VWW4]
    legacy1 = [boot_median(main / r / VWW4) for r in LEGACY_VWW4_SEED1]
    legacy_cd = boot_median(main / LEGACY_VWW4_MLEK_INPUT / VWW4)
    lo, hi = (min(mlek), max(mlek)) if len(mlek) == 6 else (None, None)
    inside = lambda x: lo <= x <= hi
    dv = [d[0] for d in drivers if d]
    res = dict(
        V2=UP if lo is None or len(dv) != 3 else
        "DRIVER_WITHIN_MLEK_RANGE" if all(inside(x) for x in dv) else "DRIVER_OUTSIDE_MLEK_RANGE",
        V3_post_hoc=UP if lo is None or not legacy_cd else   # computable before the contract: descriptive only
        "LEGACY_WITHIN_MLEK_RANGE" if inside(legacy_cd[0]) else "LEGACY_OUTSIDE_MLEK_RANGE")
    desc = lambda meds, within: dict(boot_medians=meds, between_boot_range=rng(meds) if meds else None,
                                     within_boot_ranges=within)
    res["V1_V4_descriptive"] = dict(
        mlek_boots=desc(mlek, None), mlek_stock_only=desc(stock, None),
        driver=desc(dv, [d[1] for d in drivers if d]),
        legacy_seed1=desc([d[0] for d in legacy1 if d], [d[1] for d in legacy1 if d]),
        legacy_mlek_input=dict(median=legacy_cd[0], within_boot_range=legacy_cd[1]) if legacy_cd else None,
        driver_first_run=[x for r in DRIVER_VWW4 for x in first_runs(drv / r / VWW4)],
        driver_minus_mlek_pct=(statistics.median(dv) / statistics.median(mlek) - 1) * 100 if dv and mlek else None,
        legacy_mlek_input_minus_mlek_pct=(legacy_cd[0] / statistics.median(mlek) - 1) * 100 if legacy_cd and mlek else None)
    return res


def main(main_repo: str, driver_repo: str, out: str) -> dict:
    m, d = pathlib.Path(main_repo), pathlib.Path(driver_repo)
    res = dict(W=w_part(m, d), V=v_part(m, d))
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), indent=1))
