#!/usr/bin/env python3
"""FI101 Stage 2A (model level): pipeline activity and stalls of the seven MLEK models, from the fi101_s013 boots
94-100 (TA profile 1, PMU sets A, D, E; 8 measured RUNs per set). No new board data.

  python3 results/fi101_stage2a/stage2a_models.py

Ratios: preregistered in evidence/fi101_s013/contract.md (stage 1 / "2-pre"), each within one RUN (npu_active is in
every set); an event that is not COUNTED_NONZERO gives its verdict instead of a number. Consistency checks and the
Stage 2B candidates are POST_HOC_DESCRIPTIVE.
"""
import csv, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import fi101_s013 as S  # noqa: E402

RAW = REPO / "evidence" / "fi101_s013" / "raw"
A = S.ACTIVE
# (column, numerator, denominator); TRM-documented events first, then Reserved IDs (meaning inferred)
INDICATORS = [
    ("mac_active", 48, A), ("dpu_over_mac", 51, 48), ("ao_active", 64, A), ("wd_active", 80, A),
    ("wd_stalled", 81, A),
    ("mac_stalled_by_ib", 55, A), ("mac_stalled_by_w_or_acc", 52, A), ("mac_stalled_by_w", 53, A),
    ("mac_stalled_by_acc", 54, A), ("ao_stalled_by_bs_or_ob", 67, A), ("ao_stalled_by_ob", 69, A),
    ("ao_stalled_by_ab_or_cb", 70, A), ("ao_stalled_by_cb", 72, A), ("wd_stalled_by_wd_buf", 83, A),
    ("cc_stalled_on_blockdep", 33, A),
]
TRM_DOCUMENTED = {35, 48, 51, 64, 80, 81}


def num(x):
    return x if isinstance(x, float) else None


def checks(runs, row):
    """Semantic consistency of the inferred stall events (descriptive)."""
    same_run = [r["ev"][48] + r["ev"][55] <= r["ev"][A] for r in runs.values()
                if {48, 55, A} <= set(r["ev"]) and None not in (r["ev"][48], r["ev"][55], r["ev"][A])]
    g = lambda k: num(row[k]) or 0.0
    return {
        "mac_active+mac_stalled_by_ib<=npu_active (RUNs)": f"{sum(same_run)}/{len(same_run)}",
        "dpu<=mac": num(row["dpu_over_mac"]) is not None and row["dpu_over_mac"] <= 1.0,
        "max(w,acc)<=w_or_acc<=w+acc": max(g("mac_stalled_by_w"), g("mac_stalled_by_acc")) - 0.005
                                       <= g("mac_stalled_by_w_or_acc")
                                       <= g("mac_stalled_by_w") + g("mac_stalled_by_acc") + 0.005,
        "ob<=bs_or_ob": g("ao_stalled_by_ob") <= g("ao_stalled_by_bs_or_ob") + 0.005,
        "cb<=ab_or_cb": g("ao_stalled_by_cb") <= g("ao_stalled_by_ab_or_cb") + 0.005,
        "wd_buf<=wd_stalled": g("wd_stalled_by_wd_buf") <= g("wd_stalled") + 0.005,
    }


def main():
    rows, chk = [], []
    for d in sorted(RAW.glob("*/*")):
        runs = S.load_runs(d, 2)
        if not runs:
            continue
        row = dict(model=d.name, measured_runs=len([k for k in runs if k[0] == 1]),
                   **{c: S.ratio(runs, n, den) for c, n, den in INDICATORS})
        rows.append(row)
        chk.append(dict(model=d.name, **checks(runs, row)))
    for name, rs in (("stage2a_models", rows), ("consistency", chk)):
        with open(HERE / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n"); w.writeheader(); w.writerows(rs)
    for r in rows:
        print(r["model"][:14].ljust(14), " ".join(f"{v:.3f}" if isinstance(v, float) else str(v)[:9]
                                                  for k, v in r.items() if k not in ("model", "measured_runs")))
    for c in chk:
        print(c)


if __name__ == "__main__":
    main()
