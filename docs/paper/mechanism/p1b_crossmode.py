#!/usr/bin/env python3
"""P1-B cross-memory group table (frozen plan 7eb51df; written before the
new profiled data is examined).

Per workload: ONE common attribution partition across all six profiled
cells (3 modes x 2 MACs) — union-find joins source ops that share a
service window in ANY cell — then the per-group 256→512 delta under each
mode, raw values only. Gates: source-table equality across all six cells;
every per-cell decode gate of pd_analyzer applies. No aggregate metric.

Cell inputs are directories shaped like the P0-E view:
  <root>/<workload>__<mode>__<mac>/ {debug.xml, launches.json,
                                     instr.meta.json, prof.run1.json}
"""
import csv
import json
import os
import sys
from collections import defaultdict

import pd_analyzer as A

MODES = ["Sram_Only", "Shared_Sram", "Dedicated_Sram"]
MACS = [256, 512]


def load(root, workload, mode, mac):
    d = os.path.join(root, "%s__%s__%d" % (workload, mode, mac))
    meta = json.load(open(os.path.join(d, "instr.meta.json")))
    queue, optimised, source = A.parse_db(os.path.join(d, "debug.xml"))
    launches = json.load(open(os.path.join(d, "launches.json")))
    if meta["irq_count"] != len(launches):
        raise A.Reject("irq/launch mismatch %s %s %d" % (workload, mode, mac))
    by_off = dict(queue)
    lmap = []
    for off, kind in launches:
        if kind == "KERNEL_WAIT":
            lmap.append(A.SYNC_SID)
        elif off in by_off:
            lmap.append(optimised[by_off[off]]["source_id"])
        else:
            raise A.Reject("offset %d missing from queue" % off)
    prof = json.load(open(os.path.join(d, "prof.run1.json")))
    cell = {"launch_map": lmap, "source": source, "prof": prof}
    agg, units = A.per_source(cell)
    return source, units


def main(root, out_dir):
    rows = []
    for workload in ("rnnoise_INT8", "vww4_128_128_INT8"):
        cells = {}
        src0 = None
        for mode in MODES:
            for mac in MACS:
                source, units = load(root, workload, mode, mac)
                if src0 is None:
                    src0 = source
                elif source != src0:
                    raise A.Reject("source-table mismatch %s %s@%d"
                                   % (workload, mode, mac))
                cells[(mode, mac)] = units
        # common partition across ALL six cells
        sids = set(src0)
        parent = {s: s for s in sids | {A.SYNC_SID}}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for units in cells.values():
            for u in units:
                ms = u["source_ids"]
                for m in ms[1:]:
                    ra, rb = find(ms[0]), find(m)
                    if ra != rb:
                        parent[rb] = ra
        groups = defaultdict(set)
        for s in sids:
            groups[find(s)].add(s)

        def gsum(units):
            g = defaultdict(int)
            for u in units:
                g[find(u["source_ids"][0])] += int(u["ccnt"])
            return g

        sums = {k: gsum(v) for k, v in cells.items()}
        for k in sums:
            if set(sums[k]) - set(groups):
                raise A.Reject("group cover anomaly %s %s" % (workload, k))
        for root_id in groups:
            members = sorted(groups[root_id])
            types = sorted({src0[m]["operator"] for m in members if m != A.SYNC_SID})
            row = {"workload": workload, "group_root": root_id,
                   "n_ops": len(members),
                   "member_source_ids": " ".join(map(str, members)),
                   "member_types": " ".join(types)}
            for mode, tag in (("Sram_Only", "SO"), ("Shared_Sram", "SH"),
                              ("Dedicated_Sram", "DS")):
                a = sums[(mode, 256)].get(root_id, 0)
                b = sums[(mode, 512)].get(root_id, 0)
                row["%s_256" % tag] = a
                row["%s_512" % tag] = b
                row["%s_delta" % tag] = b - a
                row["%s_dir" % tag] = ("REGRESS" if b > a else
                                       "IMPROVE" if b < a else "SAME")
            rows.append(row)
    rows.sort(key=lambda r: (r["workload"], -abs(r["DS_delta"])))
    out = os.path.join(out_dir, "U85_P1B_CROSSMODE_GROUPS.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("groups:", len(rows), "->", out)


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
    except A.Reject as e:
        print("REJECT:", e)
        sys.exit(2)
