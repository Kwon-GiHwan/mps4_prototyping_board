#!/usr/bin/env python3
"""Stage 2B-2: activity and stalls per operator-type group, gated with NPU_OP_PMU_MASK (evidence/s2_groups/contract.md).

  python3 host/analysis/s2_groups.py <root> <ids file> <vela per-op csv> <out dir>

<root>/<arm>/<model>: arm `m_all` (mask on for the whole stream) and one arm `g_<TYPE>` per kernel-op type present in
the model (CONV, DEPTHWISE, POOL, ELEMENTWISE, RESIZE: only that type's ops counted). Sets from <ids file>, npu_active
(35) in every set. Vela per-op csv: results/fi101_stage1/vela_block_fill_per_op.csv (MACs per Vela operator).
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import fi101_s013 as S  # noqa: E402

WARMUP = 2
FLOOR, NOISY_MIN = 0.01, 0.05
NPU_ACTIVE, MAC_ACTIVE = 35, 48
COSTLY = 2.0                      # time share / MAC share at or above which the depthwise group is "costly"
VELA_DW = "DepthwiseConv2D"


def valid(runs):
    return bool(runs) and all(r["valid"] for r in runs.values())


def keyed(runs):
    """{(set, event): [values over RUNs]} plus {(set, 'npu'): NPU cycles}."""
    out = {}
    for (s, _), r in runs.items():
        for e, v in r["ev"].items():
            if v is not None:
                out.setdefault((s, e), []).append(v)
        if r["infer"] is not None:
            out.setdefault((s, "npu"), []).append(r["infer"])
    return out


def width(xs):
    m = S.med(xs)
    if m == 0:
        return 0.0 if max(xs) == 0 else float("inf")
    return (max(xs) - min(xs)) / m


def partition(groups, total):
    """Per event key (NPU cycles excluded): sum of the groups' medians = the whole stream's median within max(1 %, the
    whole's own RUN width); keys with width > 5 % are not judged. -> (verdict, {key: (sum, total, judged, ok)})."""
    if not valid(total) or not groups or not all(valid(g) for g in groups.values()):
        return "UNPROVEN", {}
    t = keyed(total)
    gk = {g: keyed(r) for g, r in groups.items()}
    rows = {}
    for k, xs in t.items():
        if k[1] == "npu":
            continue
        if not all(k in g for g in gk.values()):
            return "UNPROVEN", {}
        w, tm = width(xs), S.med(xs)
        sm = sum(S.med(g[k]) for g in gk.values())
        judged = w <= NOISY_MIN
        tol = max(FLOOR, w)
        ok = (sm == 0) if tm == 0 else abs(sm - tm) <= tol * tm
        rows[k] = (sm, tm, judged, ok)
    if not rows:
        return "UNPROVEN", {}
    return ("PARTITION_HOLDS" if all(ok for _, _, j, ok in rows.values() if j) else "PARTITION_LEAKS"), rows


def ratio(runs, s, e):
    """Median over RUNs of event e / npu_active in the same RUN of set s; None if npu_active is 0 in every RUN."""
    xs = [r["ev"][e] / r["ev"][NPU_ACTIVE] for (ss, _), r in runs.items()
          if ss == s and r["ev"].get(NPU_ACTIVE) and r["ev"].get(e) is not None]
    return S.med(xs)


def npu_active(runs, s):
    return S.med([r["ev"][NPU_ACTIVE] for (ss, _), r in runs.items() if ss == s and NPU_ACTIVE in r["ev"]])


def h1(groups, set_a):
    """Depthwise group's MAC-active share of its NPU-active cycles is below the CONV group's."""
    if "DEPTHWISE" not in groups or "CONV" not in groups:
        return "NOT_APPLICABLE"
    d, c = ratio(groups["DEPTHWISE"], set_a, MAC_ACTIVE), ratio(groups["CONV"], set_a, MAC_ACTIVE)
    if d is None or c is None:
        return "UNPROVEN"
    return "DW_LOWER" if d < c else "DW_NOT_LOWER"


def h2(groups, set_a, mac_share):
    """Depthwise group's share of NPU-active cycles over its share of Vela MACs; COSTLY at >= 2."""
    if "DEPTHWISE" not in groups or not mac_share:
        return "NOT_APPLICABLE", None
    tot = sum(npu_active(g, set_a) or 0 for g in groups.values())
    if not tot:
        return "UNPROVEN", None
    q = (npu_active(groups["DEPTHWISE"], set_a) or 0) / tot / mac_share
    return ("DW_COSTLY" if q >= COSTLY else "DW_NOT_COSTLY"), q


def overall(vs):
    vs = [v for v in vs if v != "NOT_APPLICABLE"]
    if not vs or "UNPROVEN" in vs:
        return "UNPROVEN"
    return vs[0] if len(set(vs)) == 1 else "MIXED"


def gated(verdict, part):
    return verdict if part == "PARTITION_HOLDS" else "UNPROVEN"


def dw_mac_share(vela_csv):
    """{model: depthwise MACs / all MACs} from the Vela per-operator table."""
    tot, dw = {}, {}
    with open(vela_csv) as f:
        for r in csv.DictReader(f):
            m, macs = r["model"], int(r["macs"])
            tot[m] = tot.get(m, 0) + macs
            dw[m] = dw.get(m, 0) + (macs if r["op"] == VELA_DW else 0)
    return {m: dw[m] / tot[m] for m in tot if tot[m]}


def load(d):
    return S.load_runs(d, WARMUP) if (d / "runs.csv").exists() else {}


def main(root, ids, vela_csv, out):
    import pmu_events_parse as E
    root, out = pathlib.Path(root), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _, sets = E.parse_ids_text(pathlib.Path(ids).read_text())
    sets = {i + 1: s for i, s in enumerate(sets)}
    set_a = next(s for s, evs in sets.items() if MAC_ACTIVE in evs)
    share = dw_mac_share(vela_csv)
    res, part_rows, grp_rows = {}, [], []
    for d in sorted((root / "m_all").glob("*")):
        m = d.name
        total = load(d)
        groups = {p.name[2:]: load(p / m) for p in sorted(root.glob("g_*")) if (p / m).is_dir()}
        pv, rows = partition(groups, total)
        v1 = gated(h1(groups, set_a), pv)
        v2, q = h2(groups, set_a, share.get(m))
        res[m] = dict(partition=pv, h1=v1, h2=gated(v2, pv), dw_time_over_mac_share=q, groups=sorted(groups))
        for (s, e), (sm, tm, j, ok) in rows.items():
            part_rows.append(dict(model=m, set=s, event=e, sum_groups=sm, m_all=tm, judged=j, ok=ok))
        for g, r in [("m_all", total)] + sorted(groups.items()):
            for s, evs in sets.items():
                row = dict(model=m, group=g, set=s, npu_active=npu_active(r, s),
                           npu_cycles=S.med([x["infer"] for (ss, _), x in r.items() if ss == s]))
                row.update({f"ev{e}_per_active": ratio(r, s, e) for e in evs if e != NPU_ACTIVE})
                grp_rows.append(row)
    summary = dict(h1=overall([x["h1"] for x in res.values()]), h2=overall([x["h2"] for x in res.values()]),
                   partition=overall([x["partition"] for x in res.values()]), models=res)
    for name, rs in (("partition", part_rows), ("groups", grp_rows)):
        if rs:
            keys = list(dict.fromkeys(k for r in rs for k in r))
            with open(out / f"{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rs)
    json.dump(summary, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
