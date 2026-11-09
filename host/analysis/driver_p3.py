#!/usr/bin/env python3
"""Driver runner Phase 3 first validation (evidence/driver_p3/contract.md). TA profile 1 (MLEK's own TA set-up).

  python3 host/analysis/driver_p3.py <driver root> <legacy root> <out dir>

<driver root>/wfe/<model>/: run_driver_events.py output (runs.csv, capabilities.json); sets: BASE = (35 17), A, B.
<legacy root>/<model>/: the legacy runner on the same seed-1 input (Stage 0 ctl, passes A-G).

  D1 platform   capabilities: both TAs' registers = MLEK sys_dram_mid except TA_EXT MAXR (recorded: E2), AXI_SRAM
                0x20F0B, AXI_EXT 0x21F3F, MEM_ATTR 0/0/4/4, POWER_CTRL 0       -> PLATFORM_AS_MLEK / PLATFORM_DIFFERS
  D2 execution  every RUN valid (record_v2.validity) and OFM mismatch 0       -> EXEC_OK / EXEC_INVALID
  D3 window     every RUN: one arm, one IRQ, stable cycle read, NPU_EXECUTION >= NPU_ACTIVE > 0  -> WINDOW_OK / _INVALID
  D4 repeat     mac_active and the four beat counters identical in every measured RUN            -> STABLE / UNSTABLE
  D5 legacy     same input: mac_active and the four beats equal the legacy runner's exactly, NPU_ACTIVE within the
                2B-0b tolerance of the legacy RUN width                      -> REPRODUCES_LEGACY / DIFFERS_FROM_LEGACY
  D6 PMU load   NPU_ACTIVE, NPU_EXECUTION and HOST_END_TO_END of sets A and B within the 2B-0b tolerance of set BASE
                (BASE's RUN width, at least 1 %), OFM the same              -> PMU_INERT / PMU_EFFECTIVE
Any missing piece -> UNPROVEN for that check. No check is inferred from another.
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402
import s2_mask_confirm as M  # noqa: E402

WARMUP = 2
ACTIVE, MAC = 35, 48
BEATS = (130, 135, 386, 391)
BASE_SET, SET_A, SET_B = 1, 2, 3
TA_EXPECTED = {   # MLEK ta_config_u85_sys_dram_mid (host/lib/pmwl.py TA_PROFILES[1]); EXT maxr judged apart
    "ta_sram_": dict(maxr=8, maxw=8, maxrw=0, rlatency=32, wlatency=32, pulse_on=3999, pulse_off=1, bwcap=4000, mode=1,
                     histbin=0),
    "ta_ext_": dict(maxw=32, maxrw=0, rlatency=500, wlatency=250, pulse_on=4000, pulse_off=1000, bwcap=3750, mode=1,
                    histbin=0)}
NPU_EXPECTED = dict(axi_sram=0x20F0B, axi_ext=0x21F3F, mem_attr0=0, mem_attr1=0, mem_attr2=4, mem_attr3=4, power_ctrl=0)
UP = "UNPROVEN"


def platform(caps: dict | None) -> tuple[str, dict]:
    if not caps:
        return UP, dict(reason="no capabilities")
    off = [f"{p}{k}" for p, regs in TA_EXPECTED.items() for k, v in regs.items() if caps[f"{p}{k}"] != v]
    off += [k for k, v in NPU_EXPECTED.items() if caps[k] != v]
    ext_maxr = caps["ta_ext_maxr"]
    det = dict(outside=off, ta_ext_maxr=ext_maxr, e2={0: "E2_SAME", 64: "E2_DIFFERS"}.get(ext_maxr, "E2_OTHER"),
               cfg_sram_cap=f"0x{caps['cfg_sram_cap']:08x}", cfg_ext_cap=f"0x{caps['cfg_ext_cap']:08x}",
               power_requests_idle=caps["power_requests"])
    return ("PLATFORM_AS_MLEK" if not off else "PLATFORM_DIFFERS"), det


def rows(folder: pathlib.Path) -> list[dict]:
    with (folder / "runs.csv").open() as f:
        return [r for r in csv.DictReader(f) if int(r["rep"]) > WARMUP]


def execution(rs: list[dict]) -> str:
    if not rs:
        return UP
    ok = all(r["run_valid"] == "True" and r["ofm_mismatch_count"] == "0" for r in rs)
    return "EXEC_OK" if ok else "EXEC_INVALID"


def window(raw: list[dict]) -> str:
    runs = [x for x in raw if "record" in x and x["rep"] > WARMUP]
    if not runs:
        return UP
    for x in runs:
        f = x["record"]
        codes = [f[f"event_code{i}"] for i in range(f["event_count"])]
        if ACTIVE not in codes:
            return UP
        active = f[f"ev_irq{codes.index(ACTIVE)}"]
        execution_cycles = f["ccnt_irq_lo"] | f["ccnt_irq_hi"] << 32
        if f["arm_count"] != 1 or f["irq_count"] != 1 or not 0 < active <= execution_cycles:
            return "WINDOW_INVALID"
    return "WINDOW_OK"


def values(runs: dict, ev: int) -> list[int]:
    return [r["ev"][ev] for r in runs.values() if r["ev"].get(ev) is not None]


def repeat(runs: dict) -> str:
    sets = [values(runs, e) for e in (MAC,) + BEATS]
    if any(not s for s in sets):
        return UP
    return "STABLE" if all(len(set(s)) == 1 for s in sets) else "UNSTABLE"


def legacy(runs: dict, ref: dict) -> tuple[str, dict]:
    if not runs or not ref:
        return UP, {}
    off = []
    for e in (MAC,) + BEATS:
        a, b = values(runs, e), values(ref, e)
        if not a or not b:
            return UP, dict(reason=f"event {e} missing")
        if set(a) != set(b) or len(set(a)) != 1:
            off.append(e)
    a, b = values(runs, ACTIVE), values(ref, ACTIVE)
    w = M.width(b)
    if not M.close(S.med(a), S.med(b), M.tol_pass(w)):
        off.append(ACTIVE)
    det = dict(outside=off, npu_active_driver=S.med(a), npu_active_legacy=S.med(b),
               npu_active_diff_pct=(S.med(a) - S.med(b)) / S.med(b) * 100)
    return ("REPRODUCES_LEGACY" if not off else "DIFFERS_FROM_LEGACY"), det


def pmu_load(rs: list[dict]) -> tuple[str, dict]:
    by = {}
    for r in rs:
        if r["slot"] == "0":
            by.setdefault(int(r["set_id"]), []).append(r)
    if not all(s in by for s in (BASE_SET, SET_A, SET_B)):
        return UP, dict(reason="a set is missing")
    keys = ("infer_npu_cycles", "host_end_to_end_cycles")
    det, off = {}, []
    base_active = [int(r["event_value"]) for r in by[BASE_SET]]
    for s in (SET_A, SET_B):
        for k in keys:
            ref = [int(r[k]) for r in by[BASE_SET]]
            if not M.close(statistics.median(int(r[k]) for r in by[s]), statistics.median(ref),
                           max(M.FLOOR, M.width(ref))):
                off.append(f"set{s}:{k}")
        act = [int(r["event_value"]) for r in by[s]]
        if not M.close(statistics.median(act), statistics.median(base_active), max(M.FLOOR, M.width(base_active))):
            off.append(f"set{s}:npu_active")
        if {r["ofm_mismatch_count"] for r in by[s]} != {r["ofm_mismatch_count"] for r in by[BASE_SET]}:
            off.append(f"set{s}:ofm")
    det["outside"] = off
    return ("PMU_INERT" if not off else "PMU_EFFECTIVE"), det


def main(root: str, legacy_root: str, out: str) -> dict:
    res = {}
    for d in sorted((pathlib.Path(root) / "wfe").iterdir()):
        if not (d / "runs.csv").exists():
            continue
        caps = json.loads((d / "capabilities.json").read_text()) if (d / "capabilities.json").exists() else None
        rs, raw = rows(d), json.loads((d / "raw_runs.json").read_text())
        runs = S.load_runs(d, WARMUP)
        ref_dir = pathlib.Path(legacy_root) / d.name
        ref = S.load_runs(ref_dir, WARMUP) if (ref_dir / "runs.csv").exists() else {}
        res[d.name] = dict(zip(("D1", "D1_detail"), platform(caps))) | {"D2": execution(rs), "D3": window(raw),
                                                                         "D4": repeat(runs)} \
            | dict(zip(("D5", "D5_detail"), legacy(runs, ref))) | dict(zip(("D6", "D6_detail"), pmu_load(rs)))
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), indent=1))
