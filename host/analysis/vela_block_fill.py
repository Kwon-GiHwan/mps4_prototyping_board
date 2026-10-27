#!/usr/bin/env python3
"""POST_HOC_DESCRIPTIVE: how much of Vela's chosen OFM blocks and ublocks a model's operators actually fill.

  python3 host/analysis/vela_block_fill.py <dir with <model>.verbose.txt> <out.csv> [<per-operator out.csv>]

Per operator (from `vela --verbose-schedule`): fill = OFM elements / (blocks x block elements), blocks = per-axis
ceil(OFM / block) over H, W, C; same for the ublock. Model value = MAC-weighted mean over operators with MACs > 0.
Compile-time choices only; nothing here is observed on hardware.
"""
import csv, math, pathlib, re, sys

OP = re.compile(r"^\t\d+: Operation (\S+)\s+- OFM ([\d, ]+)$")
CFG = re.compile(r"OFM Block=\[([\d, ]+)\].*OFM UBlock=\[([\d, ]+)\]")
PERF = re.compile(r"Estimated Perf: Macs=(\d+) Cycles=(\d+)")


def hwc(nums):
    v = [int(x) for x in nums.split(",")]
    return v[-3:] if len(v) >= 3 else [1] * (3 - len(v)) + v


def fill(ofm, blk):
    used = 1
    for o, b in zip(ofm, blk):
        used *= math.ceil(o / b) * b
    return math.prod(ofm) / used


def parse(text):
    ops, cur = [], None
    for line in text.splitlines():
        m = OP.match(line)
        if m:
            cur = dict(op=m.group(1), ofm=hwc(m.group(2))); ops.append(cur); continue
        if cur is None:
            continue
        m = CFG.search(line)
        if m:
            cur["block"], cur["ublock"] = hwc(m.group(1)), hwc(m.group(2))
        m = PERF.search(line)
        if m:
            cur["macs"], cur["cycles"] = int(m.group(1)), int(m.group(2))
    return [o for o in ops if "block" in o and o.get("macs")]


def model_fill(ops):
    w = sum(o["macs"] for o in ops)
    return (sum(fill(o["ofm"], o["block"]) * o["macs"] for o in ops) / w,
            sum(fill(o["ofm"], o["ublock"]) * o["macs"] for o in ops) / w, len(ops), w)


def main(src, out, per_op=None):
    rows, oprows = [], []
    for f in sorted(pathlib.Path(src).glob("*.verbose.txt")):
        ops = parse(f.read_text())
        name = f.name.replace(".verbose.txt", "")
        for i, o in enumerate(ops):
            oprows.append(dict(model=name, index=i, op=o["op"], ofm_hwc="x".join(map(str, o["ofm"])),
                               block_hwc="x".join(map(str, o["block"])), ublock_hwc="x".join(map(str, o["ublock"])),
                               macs=o["macs"], vela_cycles=o["cycles"], block_fill=fill(o["ofm"], o["block"]),
                               ublock_fill=fill(o["ofm"], o["ublock"])))
        b, u, n, macs = model_fill(ops)
        rows.append(dict(model=f.name.replace(".verbose.txt", ""), ops_with_macs=n, vela_macs=macs,
                         block_fill_mac_weighted=b, ublock_fill_mac_weighted=u))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    if per_op:
        with open(per_op, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(oprows[0]), lineterminator="\n"); w.writeheader(); w.writerows(oprows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main(*sys.argv[1:4])
