#!/usr/bin/env python3
"""Per-event values of the fi101_s013 boots, one row per (model, PMU set, event), measured RUNs only.

  python3 host/analysis/fi101_events.py <evidence root> <out long.csv> <out wide.csv> <set ids, e.g. 1 or 2,3,4,5,6,7>

Long: model, set, ev_type, name, in_trm110, n, median, min, max, verdict (closed set as Stage 0 S0-6).
Wide: one row per model, one column per (set, event) median.
"""
import csv, json, pathlib, statistics, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
NAMES = dict((i, n) for i, n in json.load(open(REPO / "docs/reference/driver_events_171.json")))
TRM = {e["id"] if isinstance(e, dict) else e[0] for e in json.load(open(REPO / "docs/reference/trm_events_110.json"))}


def verdict(vals, ovf):
    if ovf:
        return "OVERFLOW"
    if all(v > 0 for v in vals):
        return "COUNTED_NONZERO"
    if all(v == 0 for v in vals):
        return "COUNTED_ZERO"
    return "INCONSISTENT"


def main(root, long_out, wide_out, sets, warmup=2):
    want = {int(s) for s in sets.split(",")}
    rows, wide = [], {}
    for folder in sorted(pathlib.Path(root).glob("*/*/")):
        if not (folder / "runs.csv").exists():
            continue
        acc = {}
        for r in csv.DictReader(open(folder / "runs.csv")):
            s, rep, e = int(r["set_id"]), int(r["rep"]), int(r["ev_type"])
            if s in want and rep > warmup and r["event_value"] not in ("", "None"):
                a = acc.setdefault((s, e), {"v": [], "ovf": False})
                a["v"].append(int(r["event_value"])); a["ovf"] |= r["event_overflow"] == "True"
        for (s, e), a in sorted(acc.items()):
            v = a["v"]
            rows.append(dict(model=folder.name, set=s, ev_type=e, name=NAMES.get(e, "?"), in_trm110=e in TRM, n=len(v),
                             median=statistics.median(v), min=min(v), max=max(v), verdict=verdict(v, a["ovf"])))
            wide.setdefault(folder.name, {})[f"s{s}_{e}_{NAMES.get(e, '?')}"] = statistics.median(v)
    with open(long_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    cols = sorted({c for d in wide.values() for c in d}, key=lambda c: (int(c.split("_")[0][1:]), int(c.split("_")[1])))
    with open(wide_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model"] + cols, lineterminator="\n"); w.writeheader()
        for m, d in wide.items():
            w.writerow({"model": m, **d})
    print(len(rows), "rows,", len(wide), "models")


if __name__ == "__main__":
    main(*sys.argv[1:5])
