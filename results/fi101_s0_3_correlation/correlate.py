#!/usr/bin/env python3
"""POST_HOC_DESCRIPTIVE: what does the S0-3 gap (CPU DWT span - NPU PMCCNTR span, same seams) go with, across the
seven models? Inputs are the committed fi101_s013 tables (boots 94-128, TA profile 1); nothing new is measured.

  python3 results/fi101_s0_3_correlation/correlate.py      (from the repo root; writes features.csv, correlation.csv)
"""
import csv, pathlib, re

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent


def rows(p):
    return {r["model"]: r for r in csv.DictReader(open(REPO / p))}


def features():
    d = rows("results/fi101_stage0/s0_3_s0_5_detail.csv")
    s1 = rows("results/fi101_stage1/stage1.csv")
    s3 = rows("results/fi101_stage3/stage3.csv")
    us = rows("results/fi101_stage3/unit_stalls.csv")
    w = rows("results/fi101_stage3/events_pass_B_to_G_wide.csv")
    ch = {(r["model"], r["channel"], int(r["ev_type"])): float(r["channel_median"])
          for r in csv.DictReader(open(REPO / "results/fi101_stage3_channels/channels.csv"))}
    out = {}
    for m in d:
        verbose = (REPO / f"evidence/fi101_s013/vela/verbose/{m}.verbose.txt").read_text()
        out[m] = dict(
            gap=float(d[m]["cpu_minus_npu"]), gap_frac=float(d[m]["cpu_minus_npu"]) / float(d[m]["infer_npu_cycles"]),
            infer_npu=float(d[m]["infer_npu_cycles"]), active=float(s1[m]["active"]),
            vela_ops=len(re.findall(r"^\t\d+: Operation", verbose, re.M)),
            sram_rd_beats=float(w[m]["s2_130_sram_rd_data_beat_received"]),
            sram_wr_beats=float(w[m]["s2_135_sram_wr_data_beat_written"]),
            sram_rd_trans=float(w[m]["s2_128_sram_rd_trans_accepted"]),
            sram_wr_trans=float(w[m]["s2_132_sram_wr_trans_accepted"]),
            ext_rd_beats=float(w[m]["s2_386_ext_rd_data_beat_received"]),
            ext_wr_beats=float(w[m]["s2_391_ext_wr_data_beat_written"]),
            ext_rd_trans=float(w[m]["s2_384_ext_rd_trans_accepted"]),
            dma_ext_rd_beats=ch[(m, "rd_mem2mem", 386)],
            mac_active_ratio=float(s1[m]["mac_active_ratio"]), active_over_vela=float(s1[m]["active_over_vela"]),
            cc_blockdep=float(us[m]["cc_stalled_on_blockdep"]), mac_stalled_by_ib=float(us[m]["mac_stalled_by_ib"]),
            ext_rd_req_stall=float(s3[m]["ext_rd_req_stall"]), sram_rd_req_stall=float(s3[m]["sram_rd_req_stall"]))
    return out


def rank(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    for k, i in enumerate(order):
        r[i] = float(k)
    return r


def pearson(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else None


def correlations(f, models):
    out = []
    for k in [k for k in next(iter(f.values())) if k not in ("gap", "gap_frac")]:
        x = [f[m][k] for m in models]
        row = dict(feature=k)
        for t in ("gap", "gap_frac"):
            y = [f[m][t] for m in models]
            row[f"spearman_{t}"] = pearson(rank(x), rank(y))
            row[f"pearson_{t}"] = pearson(x, y)
        out.append(row)
    return out


def write(name, rs):
    with open(OUT / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rs[0]), lineterminator="\n"); w.writeheader(); w.writerows(rs)


def main():
    f = features()
    models = sorted(f, key=lambda m: f[m]["gap"])
    write("features.csv", [dict(model=m, **f[m]) for m in models])
    corr = correlations(f, models)
    no_mob = [m for m in models if not m.startswith("mobilenet")]
    for r, r2 in zip(corr, correlations(f, no_mob)):
        r["spearman_gap_without_mobilenet"], r["pearson_gap_without_mobilenet"] = r2["spearman_gap"], r2["pearson_gap"]
    write("correlation.csv", corr)
    for r in sorted(corr, key=lambda r: -abs(r["spearman_gap"] or 0)):
        print(f"{r['feature']:18s} " + " ".join(f"{k}={v:+.2f}" for k, v in r.items() if k != "feature" and v is not None))


if __name__ == "__main__":
    main()
