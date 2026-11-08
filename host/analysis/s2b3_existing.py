#!/usr/bin/env python3
"""Stage 2B-3 Phase 2: the 2B-2 group data and the 2B-0b half-stream data re-read against per-op MACs from the
command stream (results/fi101_stage2b3/timeline/). POST_HOC_DESCRIPTIVE; no new board data. TA profile 1.

  python3 host/analysis/s2b3_existing.py <2B-2 raw root> <2B-0b raw root> <timeline dir> <out dir>

MAC efficiency of a window = MACs assigned to it / (1024 x its median mac_active), set A. Lag hypothesis d: the
window of kernel op i (from after op i-1's kernel instruction to after op i's) counts the MAC work of op i-d, so a
window set W is assigned Σ MACs of ops j with j + d in W (ops whose j + d falls past the last op are assigned to no
window). d = 0 is how 2B-2 read the groups. An efficiency above 1 rules out that d for that window set.
"""
import csv, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402
import s2_groups as G  # noqa: E402

MACS_PER_CYCLE = 1024
PEAK = {"CONV": 1024, "DEPTHWISE": 128}
LAGS = (0, 1, 2, 3)


def lagged(macs, window, d):
    return sum(m for j, m in enumerate(macs) if j + d in window)


def min_cycles(op):
    """Fewest MAC-active cycles the op's MACs need at the TRM peak; 0 for ops without a peak."""
    peak = PEAK.get(op["type"])
    if peak is None:
        return 0
    return int(op["macs"]) / (peak * (2 if op["type"] == "CONV" and int(op["sparse"]) else 1))


def efficiency(assigned, mac_active):
    if not mac_active:
        return None if assigned == 0 else float("inf")
    return assigned / (MACS_PER_CYCLE * mac_active)


def medians(runs, s):
    """{event: median over valid measured RUNs of set s}, or {} if any RUN is invalid."""
    r = G.of_set(runs, s)
    if not G.valid(r):
        return {}
    return {e: S.med(xs) for (_, e), xs in G.keyed(r).items() if e != "npu"}


def windows(types):
    n = len(types)
    out = {f"g_{t}": {i for i, x in enumerate(types) if x == t} for t in sorted(set(types))}
    return {"m_all": set(range(n)), **out, "m_a": set(range(n // 2)), "m_b": set(range(n // 2, n))}


def main(groups_root, mask_root, timeline_dir, out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    eff_rows, share_rows = [], []
    for tl in sorted(pathlib.Path(timeline_dir).glob("*.csv")):
        m = tl.stem
        ops = list(csv.DictReader(open(tl)))
        macs, types = [int(r["macs"]) for r in ops], [r["type"] for r in ops]
        need = [min_cycles(r) for r in ops]
        arms = {a: (pathlib.Path(groups_root) / a / m) for a in windows(types) if a.startswith(("g_", "m_all"))}
        arms.update({f"s2mask_{a}": pathlib.Path(mask_root) / a / m for a in ("m_all", "m_a", "m_b")})
        win = windows(types)
        total = {s: medians(G.load(arms["m_all"]), s) for s in (1, 2, 3)}
        for arm, d in arms.items():
            runs = G.load(d)
            w = win[arm.replace("s2mask_", "")]
            a = medians(runs, 1)
            row = dict(model=m, arm=arm, ops=len(w), npu_active=a.get(G.NPU_ACTIVE), mac_active=a.get(G.MAC_ACTIVE),
                       macs_d0=lagged(macs, w, 0))
            for lag in LAGS:
                row[f"eff_d{lag}"] = efficiency(lagged(macs, w, lag), a.get(G.MAC_ACTIVE))
            for lag in LAGS:
                ma = a.get(G.MAC_ACTIVE)
                row[f"bound_d{lag}"] = efficiency(lagged(need, w, lag) * MACS_PER_CYCLE, ma)
            eff_rows.append(row)
            if arm.startswith("g_"):
                for s in (1, 2, 3):
                    for e, v in medians(runs, s).items():
                        t = total[s].get(e)
                        share_rows.append(dict(model=m, group=arm[2:], set=s, event=e, group_median=v, m_all=t,
                                               share=v / t if t else None))
    for name, rs in (("efficiency_lag", eff_rows), ("event_share", share_rows)):
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n"); w.writeheader(); w.writerows(rs)


if __name__ == "__main__":
    main(*sys.argv[1:5])
