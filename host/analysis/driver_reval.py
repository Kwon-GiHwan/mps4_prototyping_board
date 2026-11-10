#!/usr/bin/env python3
"""Phase 7: Stage 1 / 2A / 3 metrics re-evaluated against the driver runner (evidence/driver_m7/contract.md, rules R1-R5).

  python3 host/analysis/driver_reval.py <stage raw> <bridge raw> <driver raw> <driver same-input raw> <results> <out>

<stage raw>/<cond>/<model>/   legacy runner, the Stage 1/2A/3 boots 94-100 (evidence/fi101_s013/raw)
<bridge raw>/<model>/         legacy runner on MLEK's input (equivalence C-d; sets A, B)
<driver raw>/<model>/         driver runner on MLEK's input (driver_m7; sets BASE, A-G)
<driver same-input raw>/<model>/  driver runner on the stage's own input (driver_p3: kws, ad; sets BASE, A, B)
<results>                     the published tables: fi101_stage1/stage1.csv, fi101_stage3/{stage3,unit_stalls}.csv,
                              fi101_stage2a/stage2a_models.csv
The stage value is the published number; the driver value comes from the same fi101_s013 functions on driver data.
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402

WARMUP = 2
FLOOR = 0.01
A = 35
SAME_INPUT_STAGE = {"mobilenet_v2_1.0_224_INT8"}      # boot 99 ran MLEK's input (amendment 1): driver_m7 has the same IFM
SAME_INPUT_DRIVER = {"kws_micronet_m", "ad_medium_int8"}   # driver_p3 ran the stage's seed-1 IFM
BRIDGE_EVENTS = {35, 48, 51, 53, 55, 64, 80, 81, 128, 130, 132, 135, 384, 386, 391}   # sets A and B of C-d
REVALIDATED, RETAINED, COND, REMEASURE, INVALID, UP = ("REVALIDATED", "RETAINED", "CONDITION_SPECIFIC",
                                                         "REMEASURE_REQUIRED", "INVALID", "UNPROVEN")


def _r(num, den, scale=1.0):
    return lambda ev, c: ev[num] / (scale * ev[den]) if num in ev and den in ev and ev[den] else None


def _sum(*evs, k=S.BEAT_BYTES):
    return lambda ev, c: sum(ev[e] for e in evs) * k if all(e in ev for e in evs) else None


def _imb(p, q):
    return lambda ev, c: abs(ev[p] - ev[q]) / (ev[p] + ev[q]) if p in ev and q in ev and ev[p] + ev[q] else None


# key -> (class, events, per-RUN value). DET: fixed by the command stream (exact); JITTER: timing (tolerance);
# WINDOW: the runner's own window definition; POLLUTED: includes CPU staging; STATIC: compile-time, not measured.
STALLS = {"mac_stalled_by_w": 53, "mac_stalled_by_ib": 55, "mac_stalled_by_w_or_acc": 52, "mac_stalled_by_acc": 54,
          "ao_stalled_by_bs_or_ob": 67, "ao_stalled_by_ob": 69, "ao_stalled_by_ab_or_cb": 70, "ao_stalled_by_cb": 72,
          "wd_stalled_by_wd_buf": 83, "cc_stalled_on_blockdep": 33}
P = S.PORTS
METRICS = {
    "stage1": {
        "infer_cycles": ("WINDOW", (), None), "active_over_infer": ("WINDOW", (), None),
        "runner_window": ("POLLUTED", (), None),
        "active": ("JITTER", (A,), lambda ev, c: ev.get(A)),
        "mac_active_ratio": ("JITTER", (48, A), _r(48, A)), "dpu_active_ratio": ("JITTER", (51, A), _r(51, A)),
        "dpu_over_mac": ("DET", (51, 48), _r(51, 48)), "ao_active_ratio": ("JITTER", (64, A), _r(64, A)),
        "wd_active_ratio": ("JITTER", (80, A), _r(80, A)), "wd_stalled_ratio": ("JITTER", (81, A), _r(81, A)),
        "n_mac": ("STATIC", (), None), "vela_cycles_npu": ("STATIC", (), None),
        "mac_per_cycle": ("JITTER", (A,), lambda ev, c: c["n_mac"] / ev[A] if ev.get(A) else None),
        "peak_mac_eff": ("JITTER", (A,), lambda ev, c: c["n_mac"] / (1024 * ev[A]) if ev.get(A) else None),
        "mac_active_cycle_eff": ("DET", (48,), lambda ev, c: c["n_mac"] / (1024 * ev[48]) if ev.get(48) else None),
        "active_over_vela": ("JITTER", (A,), lambda ev, c: ev[A] / c["vela_cycles_npu"] if ev.get(A) else None),
    },
    "stage3": {
        "sram_bytes": ("DET", (130, 135), _sum(130, 135)), "ext_bytes": ("DET", (386, 391), _sum(386, 391)),
        "total_bytes": ("DET", (130, 135, 386, 391), _sum(130, 135, 386, 391)),
        "bytes_per_mac": ("DET", (130, 135, 386, 391),
                          lambda ev, c: (lambda b: b / c["n_mac"] if b is not None else None)(
                              _sum(130, 135, 386, 391)(ev, c))),
        "sram_bw_bytes_per_cycle": ("JITTER", (130, 135, A),
                                    lambda ev, c: _sum(130, 135)(ev, c) / ev[A] if all(e in ev for e in (130, 135, A)) else None),
        "ext_bw_bytes_per_cycle": ("JITTER", (386, 391, A),
                                   lambda ev, c: _sum(386, 391)(ev, c) / ev[A] if all(e in ev for e in (386, 391, A)) else None),
        "sram_rd_burst": ("DET", (130, 128), _r(130, 128)), "ext_rd_burst": ("DET", (386, 384), _r(386, 384)),
        "sram_rd_req_stall": ("JITTER", (131, A), _r(131, A, 2)), "ext_rd_req_stall": ("JITTER", (387, A), _r(387, A, 2)),
        "sram_wr_beat_stall": ("JITTER", (137, A), _r(137, A, 2)), "ext_wr_beat_stall": ("JITTER", (393, A), _r(393, A, 2)),
        "sram_rd_limit": ("JITTER", (142, A), _r(142, A, 2)), "sram_wr_limit": ("JITTER", (143, A), _r(143, A, 2)),
        "ext_rd_limit": ("JITTER", (398, A), _r(398, A, 2)), "ext_wr_limit": ("JITTER", (399, A), _r(399, A, 2)),
        "sram_rd_port_imbalance": ("DET", (P["sram0_rd"], P["sram1_rd"]), _imb(P["sram0_rd"], P["sram1_rd"])),
        "ext_rd_port_imbalance": ("DET", (P["ext0_rd"], P["ext1_rd"]), _imb(P["ext0_rd"], P["ext1_rd"])),
        "sram_wr_port_imbalance": ("DET", (P["sram0_wr"], P["sram1_wr"]), _imb(P["sram0_wr"], P["sram1_wr"])),
        "ext_wr_port_imbalance": ("DET", (P["ext0_wr"], P["ext1_wr"]), _imb(P["ext0_wr"], P["ext1_wr"])),
        "vela_sram_bytes": ("STATIC", (), None), "vela_dram_bytes": ("STATIC", (), None),
        **{f"{k}_bytes": ("DET", (e,), _sum(e)) for k, e in P.items()},
    },
    "unit_stalls": {k: ("JITTER", (e, A), _r(e, A)) for k, e in STALLS.items()},
}
STAGE2A = {"mac_active": "mac_active_ratio", "dpu_over_mac": "dpu_over_mac", "ao_active": "ao_active_ratio",
           "wd_active": "wd_active_ratio", "wd_stalled": "wd_stalled_ratio"}   # the rest: same key as unit_stalls
TABLES = {"stage1": "fi101_stage1/stage1.csv", "stage3": "fi101_stage3/stage3.csv",
          "unit_stalls": "fi101_stage3/unit_stalls.csv"}


def num(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return v                  # a verdict string (COUNTED_ZERO, INCONSISTENT, ...)


def computed(runs: dict, stage: str, const: dict) -> dict:
    """The published functions on any dataset: {key: value or verdict string}."""
    vela = dict(cycles_npu=const["vela_cycles_npu"], sram_total_bytes=const.get("vela_sram_bytes"),
                dram_total_bytes=const.get("vela_dram_bytes"))
    if stage == "stage1":
        return S.stage1(runs, const["n_mac"], vela)
    if stage == "stage3":
        return S.stage3(runs, const["n_mac"], vela)
    return S.unit_stalls(runs)


def per_run(runs: dict, fn, const: dict) -> list[float]:
    """The metric RUN by RUN (all events of one RUN, i.e. one set), for the tolerance."""
    return [v for v in (fn(r["ev"], const) for r in runs.values()) if v is not None]


def agree(cls: str, x, ref, xs: list[float], refs: list[float]) -> bool | None:
    """DET: equal. JITTER: within max(1 % of ref, either dataset's RUN range). Verdict strings must be equal."""
    if x in (None, "NOT_OBSERVED") or ref in (None, "NOT_OBSERVED"):   # missing data is never a difference
        return None
    if isinstance(x, str) or isinstance(ref, str):
        return x == ref
    if cls == "DET":
        return abs(x - ref) <= 1e-9 * max(1.0, abs(ref))
    width = lambda vs: max(vs) - min(vs) if vs else 0.0
    return abs(x - ref) <= max(FLOOR * abs(ref), width(xs), width(refs))


def verdict(cls: str, cross_input: bool, path: bool | None, inp: bool | None, direct: bool | None) -> tuple[str, str]:
    """R1-R4 of the contract."""
    if cls == "STATIC":
        return RETAINED, "compile-time quantity, not measured"
    if cls == "POLLUTED":
        return INVALID, "window includes the CPU staging copies (P1)"
    if cls == "WINDOW":
        return COND, "defined by the legacy runner's own seam window"
    if not cross_input:
        if path is None:
            return UP, "no driver value"
        return (REVALIDATED, "same input, driver agrees") if path else (COND, "same input, execution path changes it")
    if path is not None:      # bridged: driver vs legacy on MLEK's input, legacy seed-1 vs legacy MLEK input
        if not path:
            return COND, "same input (MLEK's), execution path changes it"
        if inp is None:
            return UP, "no bridge value"
        return (REVALIDATED, "bridged: path and input both agree") if inp else (COND, "path agrees, input changes it")
    if direct is None:
        return UP, "no driver value"
    return (RETAINED, "agrees across input and path (not separable)") if direct else \
        (REMEASURE, "differs across input and path (not separable)")


def table(results: pathlib.Path, rel: str) -> dict[str, dict]:
    with (results / rel).open() as f:
        return {r["model"]: r for r in csv.DictReader(f)}


def load(root: pathlib.Path, m: str) -> dict:
    hits = [d for d in (root / m, *root.glob(f"*/{m}")) if (d / "runs.csv").exists()]
    return S.load_runs(hits[0], WARMUP) if hits else {}


def model_rows(m: str, roots: dict, tabs: dict) -> list[dict]:
    stage_runs, bridge, drv, drv_same = (load(roots[k], m) for k in ("stage", "bridge", "driver", "same"))
    const = {k: num(tabs["stage1"][m][k]) for k in ("n_mac", "vela_cycles_npu")}
    const.update({k: num(tabs["stage3"][m][k]) for k in ("vela_sram_bytes", "vela_dram_bytes")})
    out = []
    for stage, metrics in METRICS.items():
        pub = tabs[stage][m]
        vals = {k: computed(d, stage, const) if d else {} for k, d in
                (("driver", drv), ("same", drv_same), ("bridge", bridge))}
        for key, (cls, evs, fn) in metrics.items():
            ref = num(pub.get(key))
            refs = per_run(stage_runs, fn, const) if fn else []
            if cls == "DET" and len(set(refs)) > 1:     # R2: declared fixed, but it moves RUN to RUN in the stage data
                cls = "JITTER"
            path = inp = direct = None
            same_ds = drv if m in SAME_INPUT_STAGE else drv_same if m in SAME_INPUT_DRIVER else {}
            same_vals = vals["driver"] if m in SAME_INPUT_STAGE else vals["same"] if m in SAME_INPUT_DRIVER else {}
            in_same = fn and same_ds and all(any(e in r["ev"] for r in same_ds.values()) for e in evs)
            cross = not in_same
            dv = None
            if fn and in_same:
                dv = same_vals.get(key)
                path = agree(cls, dv, ref, per_run(same_ds, fn, const), refs)
            elif fn and set(evs) <= BRIDGE_EVENTS and bridge:
                dv, bv = vals["driver"].get(key), vals["bridge"].get(key)
                bs = per_run(bridge, fn, const)
                path = agree(cls, dv, bv, per_run(drv, fn, const), bs) if drv else None
                inp = agree(cls, ref, bv, refs, bs)
            elif fn and drv:
                dv = vals["driver"].get(key)
                direct = agree(cls, dv, ref, per_run(drv, fn, const), refs)
            v, why = verdict(cls, cross, path, inp, direct)
            out.append(dict(stage=stage, model=m, metric=key, cls=cls, stage_value=ref, driver_value=dv,
                            input_basis="-" if not fn else "SAME_INPUT" if not cross else
                            "BRIDGED" if path is not None else "CROSS_INPUT",
                            verdict=v, reason=why))
    by_key = {r["metric"]: r for r in out if r["stage"] in ("stage1", "unit_stalls")}
    for k in tabs["stage2a"].get(m, {}):
        if k in ("model", "measured_runs"):
            continue
        src = by_key.get(STAGE2A.get(k, k))
        if src:
            out.append(dict(src, stage="stage2a", metric=k, reason=f"same value as {src['stage']} {src['metric']}"))
    beats = [r["verdict"] for r in out if r["stage"] == "stage3" and r["metric"] in ("sram_bytes", "ext_bytes")]
    ok = len(beats) == 2 and all(v == REVALIDATED for v in beats)
    out.append(dict(stage="stage3_channels", model=m, metric="channel_shares", cls="DET", stage_value=None,
                    driver_value=None, input_basis="-", verdict=RETAINED if ok else REMEASURE,
                    reason="unfiltered beats revalidated" if ok else "unfiltered beats not revalidated"))
    return out


def main(stage_raw: str, bridge_raw: str, driver_raw: str, same_raw: str, results: str, out: str) -> dict:
    res = pathlib.Path(results)
    tabs = {k: table(res, v) for k, v in TABLES.items()}
    tabs["stage2a"] = table(res, "fi101_stage2a/stage2a_models.csv")
    roots = dict(stage=pathlib.Path(stage_raw), bridge=pathlib.Path(bridge_raw), driver=pathlib.Path(driver_raw),
                 same=pathlib.Path(same_raw))
    rows = [r for m in sorted(tabs["stage1"]) for r in model_rows(m, roots, tabs)]
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    with (o / "reval.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    counts: dict = {}
    for r in rows:
        c = counts.setdefault(r["stage"], {}); c[r["verdict"]] = c.get(r["verdict"], 0) + 1
    (o / "summary.json").write_text(json.dumps(counts, indent=1))
    return counts


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:7]), indent=1))
