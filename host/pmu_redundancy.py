"""POST_HOC_DESCRIPTIVE: which PMU counters duplicate other counters, over every valid campaign.

Each event is read in its own run (8 counters per set), so events are compared as values
*across runs*. Hence:
  - exact relations only between deterministic events (all repeats equal in that boot);
  - stalls and cycles vary run to run, so they are compared as repeat ranges (± TOL), only for
    name-family hypotheses (aggregate vs ports, cycle-like counters). An open approximate
    search matches coincidences (hundreds of spurious sums), so it is not used.
A relation must hold in every boot where all its members were measured (COUNTED_*), and is
reported with the boots where all members were nonzero (its support).

    python3 host/pmu_redundancy.py evidence > out.md
"""
from __future__ import annotations

import csv
import itertools
import json
import re
import sys
from pathlib import Path

BOOTS = {
    "pmu_events/boot9": "1x1 conv, SRAM port",
    "pmu_events_c/boot12": "1x1 conv, EXT/DRAM",
    "pmu_events_c/boot13": "kws, all EXT",
    "pmu_events_c/boot18": "mobilenet, split ports (48 ids)",
    "pmu_events_c/boot19": "mobilenet, split ports",
    "pmu_events_c/boot20": "mobilenet, split ports, AXI limit (19 ids)",
    "pmu_events_c/boot21": "ad_medium (FWD), all EXT (39 ids)",
    "pmu_events_c/boot22": "MatMul, all EXT (39 ids)",
    "pmu_events_c/boot23": "kws, all EXT, AXI limit (20 ids)",
}
MEASURED = {"COUNTED_NONZERO", "COUNTED_ZERO"}
TOL = 0.02
PORT = re.compile(r"^(sram|ext)([0-3])_(.+)$")


def load(root: Path):
    data: dict[int, dict[str, tuple[float, bool]]] = {}
    names: dict[int, str] = {}
    trm: dict[int, bool] = {}
    for boot in BOOTS:
        for r in csv.DictReader(open(root / boot / "per_event.csv")):
            ev = int(r["ev_type"])
            names[ev], trm[ev] = r["name"], r["in_trm110"] == "True"
            if r["verdict"] in MEASURED:
                vals = json.loads(r["values"])
                data.setdefault(ev, {})[boot] = (sum(vals) / len(vals), len(set(vals)) == 1, min(vals), max(vals))
    return data, names, trm


def holds(data, members, pred, exact) -> list[str] | None:
    """Boots supporting the relation, or None if any boot contradicts it or none supports it.
    pred gets one (mean, deterministic, min, max) tuple per member."""
    support = []
    for boot in BOOTS:
        if not all(boot in data.get(m, {}) for m in members):
            continue
        rows = [data[m][boot] for m in members]
        if all(r[0] == 0 for r in rows):
            continue
        if exact and not all(r[1] for r in rows):
            return None
        if not pred(rows):
            return None
        if all(r[0] > 0 for r in rows):
            support.append(boot)
    return support or None


def within_noise(a: tuple, parts: list[tuple]) -> bool:
    """a's repeat range, widened by TOL, meets the range of sum(parts): equal within run-to-run noise."""
    lo, hi = sum(p[2] for p in parts), sum(p[3] for p in parts)
    return a[2] * (1 - TOL) <= hi and lo <= a[3] * (1 + TOL)


def classes(evs, pairs):
    parent = {e: e for e in evs}

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in pairs:
        parent[root(b)] = root(a)
    groups: dict[int, list[int]] = {}
    for e in evs:
        groups.setdefault(root(e), []).append(e)
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: g[0])


def find(data, names):
    evs = sorted(e for e in data if any(v[0] > 0 for v in data[e].values()))
    exact_pairs = [(a, b) for a, b in itertools.combinations(evs, 2)
                   if holds(data, (a, b), lambda v: v[0][0] == v[1][0], True)]
    exact_cls = classes(evs, exact_pairs)
    rep = {e: g[0] for g in exact_cls for e in g}
    reps = sorted({rep.get(e, e) for e in evs})

    exact_sums = []
    for a in reps:
        for b, c in itertools.combinations([e for e in reps if e != a], 2):
            s = holds(data, (a, b, c), lambda v: v[0][0] == v[1][0] + v[2][0], True)
            if s:
                exact_sums.append((a, b, c, s))

    # Approximate, name-family only: aggregate vs port0 + port1, and cycle-like equalities.
    by_name = {names[e]: e for e in evs}
    approx_sums = []
    for e in evs:
        m = PORT.match(names[e])
        if not m or m.group(2) != "0":
            continue
        agg, p1 = by_name.get(f"{m.group(1)}_{m.group(3)}"), by_name.get(f"{m.group(1)}1_{m.group(3)}")
        if agg is None or p1 is None or any(agg == x[0] for x in exact_sums):
            continue
        s = holds(data, (agg, e, p1), lambda v: within_noise(v[0], v[1:]), False)
        approx_sums.append((agg, e, p1, s))

    cycle_like = [e for e in evs if names[e] == "cycle" or names[e].endswith("enabled_cycles")]
    cyc_pairs = [(a, b) for a, b in itertools.combinations(cycle_like, 2)
                 if holds(data, (a, b), lambda v: within_noise(v[0], v[1:]), False)]
    return evs, exact_cls, exact_sums, approx_sums, classes(cycle_like, cyc_pairs)


def main(root: str) -> None:
    data, names, trm = load(Path(root))
    evs, exact_cls, exact_sums, approx_sums, cyc_cls = find(data, names)
    n = lambda e: f"`{names[e]}`({e}{'' if trm[e] else ', drv'})"
    sup = lambda s: ", ".join(b.split("/")[1] for b in s)

    out = ["# PMU counter redundancy (POST_HOC_DESCRIPTIVE)", "",
           "Boots: " + "; ".join(f"{b.split('/')[1]} = {w}" for b, w in BOOTS.items()) + ".",
           f"`drv` = driver-only (TRM Reserved). Approximate relations: repeat min–max ranges meet after widening by {TOL:.0%}.", "",
           f"Events nonzero in at least one boot: **{len(evs)}** of 171.", "",
           "## A. Exact equality (deterministic counts)", ""]
    for g in exact_cls:
        s = holds(data, g, lambda v: len({x[0] for x in v}) == 1, True)
        out.append(f"- {' = '.join(n(e) for e in g)} — support: {sup(s)}")
    out += ["", "## B. Exact sums a = b + c (one member per class A)", ""]
    for a, b, c, s in exact_sums:
        out.append(f"- {n(a)} = {n(b)} + {n(c)} — support: {sup(s)}")
    out += ["", f"## C. Aggregate ≈ port0 + port1 (repeat ranges meet, widened by {TOL:.0%})", ""]
    for a, b, c, s in approx_sums:
        verdict = f"holds — support: {sup(s)}" if s else "**does not hold** in some boot"
        out.append(f"- {n(a)} ≈ {n(b)} + {n(c)} — {verdict}")
    out += ["", f"## D. Cycle-like counters equal within repeat ranges ± {TOL:.0%}", ""]
    for g in cyc_cls:
        out.append(f"- {' ≈ '.join(n(e) for e in g)}")

    redundant = {e for g in exact_cls for e in g[1:]}
    redundant |= {a for a, _, _, _ in exact_sums}
    redundant |= {a for a, _, _, s in approx_sums if s}
    redundant |= {e for g in cyc_cls for e in g[1:]}
    out += ["", "## Count", "",
            f"- nonzero in at least one boot: {len(evs)}",
            f"- expressible by the relations above (A–D): {len(redundant)}",
            f"- **left: {len(evs) - len(redundant)}**", "",
            "\"Left\" is an upper bound on independent information, not a count of independent counters: only",
            "pairwise equality and two-term sums are searched, and an equality seen on these workloads may",
            "be a property of the workloads (e.g. even load across ports) rather than of the counters."]
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
