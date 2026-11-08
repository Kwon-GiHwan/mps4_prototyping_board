#!/usr/bin/env python3
"""Stage 2B-3 Phase 3a: choose the reference op A and the comparison op B of a model, by the same rule for all seven
models, from compile-time data only (per-op MACs of the command stream = Vela's counts; results/fi101_stage2b3/
timeline/). No PMU data is used (owner 2026-11-08: not the misattributed 2B-2 results).

  python3 host/analysis/s2b3_select.py <timeline dir>

A: a kernel op with both stream neighbours, MACs > 0 and at least RATIO times the MACs of each neighbour; among those
the largest contrast = MACs / max(neighbour MACs, FLOOR) (FLOOR = one cycle of the 1024-MAC array, so a zero-MAC
neighbour does not make every contrast infinite); ties -> more MACs, then the earlier op. B: the op right after A
(where a late window would put A's work). No A -> NOT_AVAILABLE (the rule is not relaxed).
"""
import csv, pathlib, sys

RATIO, FLOOR = 4, 1024


def select(macs):
    """-> (a, b, contrast) or None."""
    keys = []
    for i in range(1, len(macs) - 1):
        nb = max(macs[i - 1], macs[i + 1])
        if macs[i] > 0 and macs[i] >= RATIO * nb:
            keys.append((macs[i] / max(nb, FLOOR), macs[i], -i))
    if not keys:
        return None
    contrast, _, neg_a = max(keys)
    return -neg_a, -neg_a + 1, contrast


def main(timeline_dir):
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["model", "A", "B", "contrast", "A_type", "A_op", "A_macs", "prev_macs", "B_type", "B_op", "B_macs"])
    for p in sorted(pathlib.Path(timeline_dir).glob("*.csv")):
        ops = list(csv.DictReader(open(p)))
        s = select([int(r["macs"]) for r in ops])
        if s is None:
            w.writerow([p.stem, "NOT_AVAILABLE"]); continue
        a, b, c = s
        w.writerow([p.stem, a, b, f"{c:.1f}", ops[a]["type"], ops[a]["optimised_op"], ops[a]["macs"],
                    ops[a - 1]["macs"], ops[b]["type"], ops[b]["optimised_op"], ops[b]["macs"]])


if __name__ == "__main__":
    main(sys.argv[1])
