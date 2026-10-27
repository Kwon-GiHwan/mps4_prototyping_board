#!/usr/bin/env python3
"""FI101 Stage 0 checks and Stage 1 / Stage 3 model-level metrics (evidence/fi101_s013/contract.md).

  python3 host/analysis/fi101_s013.py <evidence root> <out dir> [--profile config/fi101_s013.json]

Input: one `<cond>/<model>/` folder per boot (runs.csv, raw_runs.json from host/board/run_pmu_events.py).
Every ratio pairs two events of the same RUN (same PMU set); the anchor `npu_active` (35) is in every set.
"""
import argparse, csv, json, pathlib, statistics, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
ACTIVE, MAC, DPU, AO, WD, WD_ST = 35, 48, 51, 64, 80, 81
BEATS = {"sram_rd": 130, "sram_wr": 135, "ext_rd": 386, "ext_wr": 391}
PORTS = {"sram0_rd": 514, "sram1_rd": 530, "ext0_rd": 642, "ext1_rd": 658,
         "sram0_wr": 519, "sram1_wr": 535, "ext0_wr": 647, "ext1_wr": 663}
BEAT_BYTES = 16                       # 128-bit AXI ports (TRM, AXI ports per configuration)
REFERENCE = {  # same blob on image 38ce118c (S0-4)
    "kws_micronet_m": "evidence/x1_mlek_models/raw_a2/ctl/kws_micronet_m",
    "ad_medium_int8": "evidence/x1_mlek_models/raw_a2/ctl/ad_medium_int8",
    "mobilenet_v2_1.0_224_INT8": "evidence/x1_mlek_models/raw_a2/ctl/mobilenet_v2_1.0_224_INT8",
    "vww4_128_128_INT8": "evidence/x1_mlek_models/raw_a2/x1/vww4_128_128_INT8",
    "rnnoise_INT8": "evidence/x1_mlek_models/raw_a2/x1/rnnoise_INT8",
    "yolo-fastest_192_face_v4": "evidence/x1_mlek_models/raw_a2/x1/yolo-fastest_192_face_v4",
    "wav2letter_pruned_int8": "evidence/x1_mlek_models/raw_a4/x1/wav2letter_pruned_int8",
}
MANIFESTS = ("evidence/stage1/workload_manifest/manifest.json", "evidence/x1_mlek_models/manifest.x1.json")


def load_runs(folder, warmup):
    """{(set_id, rep): {"ev": {id: value}, "valid": bool, "window": int, ...}} for measured RUNs only."""
    runs = {}
    for r in csv.DictReader(open(folder / "runs.csv")):
        k = (int(r["set_id"]), int(r["rep"]))
        if k[1] <= warmup:
            continue
        d = runs.setdefault(k, {"ev": {}, "ovf": set(), "valid": r["run_valid"] == "True",
                                "window": int(r["window_cycles"]),
                                "infer": _int(r.get("infer_npu_cycles")), "infer_cpu": _int(r.get("infer_cpu_cycles")),
                                "sys": _int(r.get("infer_sys_ticks")), "host_s": _float(r.get("host_run_s"))})
        d["ev"][int(r["ev_type"])] = _int(r["event_value"])
        if r["event_overflow"] == "True":
            d["ovf"].add(int(r["ev_type"]))
    raw = folder / "raw_runs.json"
    if raw.exists():
        for x in json.load(open(raw)):
            k = (x.get("set_id"), x.get("rep"))
            if k in runs:
                runs[k].update(start_fired=x.get("start_seam_fired"), cntcr=x.get("sys_cntcr"))
    return runs


def _int(v):
    return int(v) if v not in (None, "", "None") else None


def _float(v):
    return float(v) if v not in (None, "", "None") else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def values(runs, ev):
    return [r["ev"][ev] for r in runs.values() if ev in r["ev"] and r["ev"][ev] is not None]


def ratio(runs, num, den, scale=1.0):
    """Median over RUNs that carry both events of num/(scale*den)."""
    return med([r["ev"][num] / (scale * r["ev"][den]) for r in runs.values()
                if num in r["ev"] and den in r["ev"] and r["ev"][den]])


# ---------------- Stage 0 ----------------
def verdict(vals, overflow):
    if overflow:
        return "OVERFLOW"
    if not vals:
        return "NOT_OBSERVED"
    if all(v > 0 for v in vals):
        return "COUNTED_NONZERO"
    if all(v == 0 for v in vals):
        return "COUNTED_ZERO"
    return "INCONSISTENT"


def stage0(runs, ref_runs):
    rs = list(runs.values())
    pf = lambda ok: "PASS" if ok else "FAIL"
    s = {}
    s["S0-1"] = pf(rs and all(r["valid"] and r.get("start_fired") == 1 for r in rs))
    order = [r["ev"][ACTIVE] <= r["infer"] <= r["window"] for r in rs if r["infer"] is not None and ACTIVE in r["ev"]]
    s["S0-2"] = pf(order and len(order) == len(rs) and all(order))
    clk = [r["infer"] / r["infer_cpu"] for r in rs if r["infer"] and r["infer_cpu"]]
    s["S0-3"] = pf(clk and len(clk) == len(rs) and all(0.99 <= c <= 1.01 for c in clk))
    if ref_runs is None:
        s["S0-4"] = "UNPROVEN"
    else:
        same = all(set(values(runs, e)) == set(values(ref_runs, e)) and values(runs, e)
                   for e in (MAC, *BEATS.values()))
        ra = values(ref_runs, ACTIVE)
        m = med(values(runs, ACTIVE))
        s["S0-4"] = pf(same and ra and min(ra) * 0.995 <= m <= max(ra) * 1.005)
    a = values(runs, ACTIVE)
    s["S0-5"] = pf(a and (max(a) - min(a)) / med(a) <= 0.02)
    return s


# ---------------- Stage 1 / 3 ----------------
def stage1(runs, n_mac, vela):
    a, inf = med(values(runs, ACTIVE)), med([r["infer"] for r in runs.values()])
    out = dict(infer_cycles=inf, active=a, active_over_infer=med([r["ev"][ACTIVE] / r["infer"] for r in runs.values()
                                                                 if r["infer"] and ACTIVE in r["ev"]]),
               runner_window=med([r["window"] for r in runs.values()]),
               mac_active_ratio=ratio(runs, MAC, ACTIVE), dpu_active_ratio=ratio(runs, DPU, ACTIVE),
               dpu_over_mac=ratio(runs, DPU, MAC), ao_active_ratio=ratio(runs, AO, ACTIVE),
               wd_active_ratio=ratio(runs, WD, ACTIVE), wd_stalled_ratio=ratio(runs, WD_ST, ACTIVE))
    mac = med(values(runs, MAC))
    out.update(n_mac=n_mac, mac_per_cycle=n_mac / a, peak_mac_eff=n_mac / (1024 * a),
               mac_active_cycle_eff=n_mac / (1024 * mac) if mac else None,
               vela_cycles_npu=vela.get("cycles_npu"), active_over_vela=a / vela["cycles_npu"] if vela.get("cycles_npu") else None)
    return out


def stage3(runs, n_mac, vela):
    a = med(values(runs, ACTIVE))
    by = {k: med(values(runs, e)) * BEAT_BYTES if values(runs, e) else None for k, e in {**BEATS, **PORTS}.items()}
    sram = (by["sram_rd"] or 0) + (by["sram_wr"] or 0); ext = (by["ext_rd"] or 0) + (by["ext_wr"] or 0)
    imb = lambda x, y: abs(x - y) / (x + y) if x is not None and y is not None and (x + y) else None
    out = dict(sram_bytes=sram, ext_bytes=ext, total_bytes=sram + ext, bytes_per_mac=(sram + ext) / n_mac,
               sram_bw_bytes_per_cycle=sram / a, ext_bw_bytes_per_cycle=ext / a,
               sram_rd_burst=ratio(runs, 130, 128), ext_rd_burst=ratio(runs, 386, 384),
               sram_rd_req_stall=ratio(runs, 131, ACTIVE, 2), ext_rd_req_stall=ratio(runs, 387, ACTIVE, 2),
               sram_wr_beat_stall=ratio(runs, 137, ACTIVE, 2), ext_wr_beat_stall=ratio(runs, 393, ACTIVE, 2),
               sram_rd_limit=ratio(runs, 142, ACTIVE, 2), sram_wr_limit=ratio(runs, 143, ACTIVE, 2),
               ext_rd_limit=ratio(runs, 398, ACTIVE, 2), ext_wr_limit=ratio(runs, 399, ACTIVE, 2),
               sram_rd_port_imbalance=imb(by["sram0_rd"], by["sram1_rd"]),
               ext_rd_port_imbalance=imb(by["ext0_rd"], by["ext1_rd"]),
               sram_wr_port_imbalance=imb(by["sram0_wr"], by["sram1_wr"]),
               ext_wr_port_imbalance=imb(by["ext0_wr"], by["ext1_wr"]),
               vela_sram_bytes=vela.get("sram_total_bytes"), vela_dram_bytes=vela.get("dram_total_bytes"))
    out.update({f"{k}_bytes": v for k, v in by.items() if k in PORTS})
    return out


def unit_stalls(runs):
    ids = {"mac_stalled_by_w": 53, "mac_stalled_by_ib": 55, "mac_stalled_by_w_or_acc": 52, "mac_stalled_by_acc": 54,
           "ao_stalled_by_bs_or_ob": 67, "ao_stalled_by_ob": 69, "ao_stalled_by_ab_or_cb": 70, "ao_stalled_by_cb": 72,
           "wd_stalled_by_wd_buf": 83, "cc_stalled_on_blockdep": 33}
    return {k: ratio(runs, e, ACTIVE) for k, e in ids.items()}


def descriptive_s0(runs):
    rs = list(runs.values())
    cyc = med([r["ev"][17] / r["window"] for r in rs if 17 in r["ev"]])
    idle = med([(r["ev"][32] + r["ev"][ACTIVE]) / r["window"] for r in rs if 32 in r["ev"]])
    en = med([r["ev"][140] / (2 * r["window"]) for r in rs if 140 in r["ev"]])
    cntcr = {r.get("cntcr") for r in rs}
    sysr = med([r["infer_cpu"] / r["sys"] for r in rs if r["sys"]]) if cntcr == {1} or (cntcr and all(c and c & 1 for c in cntcr)) else None
    host = med([r["host_s"] * 50e6 / r["window"] for r in rs if r["host_s"]])
    return dict(cycle_over_window=cyc, idle_plus_active_over_window=idle, sram_enabled_over_2window=en,
                sys_cntcr=sorted(c for c in cntcr if c is not None), cpu_cycles_per_sys_tick=sysr,
                host_s_x_50MHz_over_window=host)


CHAN_EVENTS = (128, 130, 132, 135, 384, 386, 391)


def channel_check(base_runs, chan_runs):
    """Amendment 2 rule. base: the model's unfiltered boot (Pass B is set 2); chan: {channel: runs of its boot}.
    CHANNEL_FILTER_WORKS needs every channel's median <= the unfiltered median for each event, at least one below,
    and npu_active / mac_active of the channel boots inside the base boot's range (S0-4 widening)."""
    base_b = {k: v for k, v in base_runs.items() if k[0] == 2}
    unf = {e: med(values(base_b, e)) for e in CHAN_EVENTS}
    rows, ok_le, any_below = [], True, False
    a_lo, a_hi = min(values(base_runs, ACTIVE)) * 0.995, max(values(base_runs, ACTIVE)) * 1.005
    exec_same = True
    for ch, runs in chan_runs.items():
        if not runs or not all(r["valid"] for r in runs.values()):
            exec_same = False
            continue
        m = med(values(runs, ACTIVE))
        exec_same &= a_lo <= m <= a_hi
        for e in CHAN_EVENTS:
            v = med(values(runs, e))
            if v is None or unf[e] is None:
                ok_le = False
                continue
            ok_le &= v <= unf[e]
            any_below |= v < unf[e]
            rows.append(dict(channel=ch, ev_type=e, channel_median=v, unfiltered_median=unf[e],
                             share=(v / unf[e]) if unf[e] else None))
    verdict = "CHANNEL_FILTER_WORKS" if (chan_runs and ok_le and any_below and exec_same) else "CHANNEL_FILTER_UNPROVEN"
    return verdict, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("out")
    ap.add_argument("--profile", default=str(REPO / "config/fi101_s013.json"))
    ap.add_argument("--channels", help="amendment 2/3: per-channel root (<channel>/<model>/); writes channels.csv")
    ap.add_argument("--stage1-only", action="store_true",
                    help="amendment 1: Stage 1 rows for every model, labelled PROVISIONAL (Stage 0 pending)")
    a = ap.parse_args()
    prof = json.load(open(a.profile)); warm = prof["warmup"]
    n_mac = {}
    for f in MANIFESTS:
        for k, v in json.load(open(REPO / f))["workloads"].items():
            if isinstance(v, dict) and v.get("n_mac"):
                n_mac[k] = v["n_mac"]
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    tables = {"stage0": [], "stage0_descriptive": [], "event_validity": [], "stage1": [], "stage3": [], "unit_stalls": []}
    for folder in sorted(pathlib.Path(a.root).glob("*/*/")):
        if not (folder / "runs.csv").exists():
            continue
        m = folder.name; runs = load_runs(folder, warm)
        ref = REPO / REFERENCE[m] if m in REFERENCE else None
        ref_runs = load_runs(ref, warm) if ref and (ref / "runs.csv").exists() else None
        vela = {}
        vf = REPO / "evidence/fi101_s013/vela" / f"{m}_summary.csv"
        if vf.exists():
            row = next(csv.DictReader(open(vf)))
            vela = {k: float(row[k]) for k in ("cycles_npu", "sram_total_bytes", "dram_total_bytes")}
        s0 = stage0(runs, ref_runs)
        tables["stage0"].append(dict(model=m, measured_runs=len(runs), **s0))
        tables["stage0_descriptive"].append(dict(model=m, **descriptive_s0(runs)))
        evs = sorted({e for r in runs.values() for e in r["ev"]})
        for e in evs:
            tables["event_validity"].append(dict(model=m, ev_type=e, verdict=verdict(values(runs, e),
                                                 any(e in r["ovf"] for r in runs.values())),
                                                 median=med(values(runs, e))))
        ok = all(s0[k] == "PASS" for k in ("S0-1", "S0-2", "S0-4"))
        status = "VALID" if ok else "UNRESOLVED (s013)"
        if a.stage1_only:
            tables["stage1"].append(dict(model=m, status="PROVISIONAL (Stage 0 pending)", measured_runs=len(runs),
                                         **stage1(runs, n_mac[m], vela)))
        elif ok:
            tables["stage1"].append(dict(model=m, **stage1(runs, n_mac[m], vela)))
            tables["stage3"].append(dict(model=m, **stage3(runs, n_mac[m], vela)))
            tables["unit_stalls"].append(dict(model=m, **unit_stalls(runs)))
        tables["stage0"][-1]["status"] = status
    if a.channels:
        chroot = pathlib.Path(a.channels); crow, cver = [], []
        for base in sorted(pathlib.Path(a.root).glob("*/*/")):
            m = base.name
            chans = {d.parent.name: load_runs(d, warm) for d in sorted(chroot.glob(f"*/{m}/")) if (d / "finished_utc").exists()}
            if not chans:
                continue
            v, rows = channel_check(load_runs(base, warm), chans)
            cver.append(dict(model=m, channels=",".join(sorted(chans)), verdict=v))
            crow += [dict(model=m, verdict=v, **r) for r in rows]
        tables = {"channel_verdicts": cver, "channels": crow}
    elif a.stage1_only:
        tables = {"stage1": tables["stage1"]}
    for name, rows in tables.items():
        if rows:
            with open(out / f"{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    json.dump(tables, open(out / "summary.json", "w"), indent=1, default=str)
    for r in tables.get("stage0", tables.get("stage1", tables.get("channel_verdicts", []))):
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
