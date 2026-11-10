#!/usr/bin/env python3
"""AD SRAM-budget static comparison (owner request 2026-11-11, after Stage 5-1): ad_medium_int8 at 384 KiB (base),
64 KiB and 0, from the measured DRWLs only. POST_HOC_DESCRIPTIVE; no board run; nothing here is a measured time.

  python3 host/analysis/ad64k_static.py <out dir>

Inputs (all in the repo):
  evidence/stage5/workloads/ad_medium_int8_{base,cache64k,cache0}.drwl(.json)   the measured workloads
  evidence/ad64k_static/vela_map/<config>/ad_medium_int8.*                       vela_op_map.py with the same options
The Vela file inside the measured DRWL must equal the op-map compile (sha256) and the DRWL record; the command stream
(saved by the op-map compile) must equal the DRWL record's cms_sha256; and the debug-db kernel offsets must equal the stream's, else the config is refused. Per kernel: the source TFLite
operator (debug db), Vela's high-level command (OFM/IFM area, cascaded/buffered), and the registers (block, ublock,
regions, weight-stream lengths, DMA started before it). Region 0/1 = DRAM over EXT (read-only constants / arena),
region 2 = fast scratch in SRAM (driver runner Dedicated_Sram build).
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import cms_regs  # noqa: E402
import drwl  # noqa: E402

CONFIGS = ("base", "cache64k", "cache0")
WL = REPO / "evidence/stage5/workloads"
MAP = REPO / "evidence/ad64k_static/vela_map"
REGION = {0: "DRAM(const)", 1: "DRAM(arena)", 2: "SRAM(fast)"}
# NPU_SET_ACC_FORMAT parameter (= instruction word >> 16; core driver ethosu85_interface.h npu_set_acc_format_t):
# acc_format [1:0], acc_input [5:4], acc_output [6], microblock [10:8] in the enum order below
MICROBLOCK = ("U1X1", "U1X2", "U1X4", "U2X2", "U2X4", "U4X4")


def acc(param: int) -> tuple[str, int]:
    """(microblock name, acc_input) of an ACC_FORMAT parameter."""
    mb = (param >> 8) & 7
    return (MICROBLOCK[mb] if mb < len(MICROBLOCK) else f"?{mb}"), (param >> 4) & 3
AREA = re.compile(r"(OFM|IFM) area \[([\d, -]+)\]|(?:^|, )(IFM) \[([\d, -]+)\]")
HL_KERNEL = re.compile(r"^\d+ (\S+) OFM area \[([^\]]*)\], IFM \[([^\]]*)\](.*)$")
HL_DMA = re.compile(r"^\d+ DMA src: (\S+), address: (\S+), dest: (\S+), address: (\S+),.* length: (\d+)")
sha = lambda b: hashlib.sha256(b).hexdigest()


def area(text: str) -> tuple[int, int, int, int, int, int]:
    """'0, 2, 0, 0 - 1, 4, 32, 192' -> (h0, w0, c0, h1, w1, c1) (exclusive ends, batch dropped)."""
    lo, hi = (list(map(int, s.split(","))) for s in text.split(" - "))
    return lo[1], lo[2], lo[3], hi[1], hi[2], hi[3]


def volume(a) -> int:
    return (a[3] - a[0]) * (a[4] - a[1]) * (a[5] - a[2])


def hl_commands(log: str) -> list[dict]:
    """Kernel commands of Vela's high-level command stream, in order, with the DMAs issued just before each."""
    out, dmas = [], []
    for line in log.split("High level command stream:", 1)[1].splitlines():
        m = HL_DMA.match(line)
        if m:
            dmas.append(dict(src=m.group(1), dst=m.group(3), length=int(m.group(5))))
            continue
        m = HL_KERNEL.match(line)
        if m:
            tail = m.group(4)
            out.append(dict(op=m.group(1), ofm=area(m.group(2)), ifm=area(m.group(3)), dmas=dmas,
                            cascaded="cascaded" in tail, buffered="buffered" in tail))
            dmas = []
    return out


HL_OP = re.compile(r"^(\d+) (\S+) .*OFM UBlock=\[(\d+), (\d+), (\d+)\]")


def hl_ublocks(log: str) -> list[tuple[str, tuple[int, int, int]]]:
    """(operator, OFM ublock h, w, c) of each high-level NPU operation, in order."""
    text = log.split("High level NPU operations:", 1)[1].split("High level command stream:", 1)[0]
    return [(m.group(2), tuple(map(int, m.group(3, 4, 5)))) for m in (HL_OP.match(l) for l in text.splitlines()) if m]


def ublocks(ofm, ub) -> int:
    """OFM ublocks a kernel covers: ceil(H/ub_h) * ceil(W/ub_w) * ceil(C/ub_c) of its OFM area."""
    h, w, c = ofm[3] - ofm[0], ofm[4] - ofm[1], ofm[5] - ofm[2]
    return -(-h // ub[0]) * -(-w // ub[1]) * -(-c // ub[2])


def kernels(cfg: str) -> list[dict]:
    name = f"ad_medium_int8_{cfg}"
    meta = json.loads((WL / f"{name}.drwl.json").read_text())
    d = MAP / cfg
    stream = (d / "ad_medium_int8.cms.bin").read_bytes()
    blob = (WL / f"{name}.drwl").read_bytes()
    h = drwl.parse(blob)
    vela = sha(blob[h["model_off"]:h["model_off"] + h["model_len"]])
    checks = (("DRWL record cms_sha256", sha(stream), meta["cms_sha256"]),
              ("op-map cms.sha256", sha(stream), (d / "ad_medium_int8.cms.sha256").read_text().strip()),
              ("Vela file in the measured DRWL vs op-map compile", vela, (d / "ad_medium_int8.vela.sha256").read_text().strip()),
              ("Vela file in the measured DRWL vs DRWL record", vela, meta["vela_sha256"]))
    for what, a, b in checks:
        if a != b:
            raise SystemExit(f"{cfg}: {what} differ")
    rows = list(csv.DictReader(open(d / "ad_medium_int8.op_map.csv")))
    regs = cms_regs.kernels(stream)
    log = (d / "ad_medium_int8.hlcs.txt").read_text()
    hl = hl_commands(log)
    ops = hl_ublocks(log)
    order = list(dict.fromkeys(r["optimised_id"] for r in rows))   # optimised ops in stream order
    if len(order) != len(ops):
        raise SystemExit(f"{cfg}: {len(ops)} high-level NPU operations for {len(order)} optimised ops")
    ub_of = dict(zip(order, ops))
    if [int(r["offset"]) for r in rows] != [k["offset"] for k in regs] or len(hl) != len(regs):
        raise SystemExit(f"{cfg}: op map / high-level commands / registers do not line up")
    out = []
    for i, (r, k, c) in enumerate(zip(rows, regs, hl)):
        if c["op"] != r["optimised_op"]:
            raise SystemExit(f"{cfg}: kernel {i} high-level op {c['op']} != debug db {r['optimised_op']}")
        # a POOL kernel reads no weights; its weight registers still hold the previous kernel's values
        wl = 0 if k["kind"] == "POOL" else sum(k[f] or 0 for f in ("weight_length", "weight1_length",
                                                                   "weight2_length", "weight3_length"))
        ub, acc_in = acc(k["acc_format"])
        op_name, ub_dims = ub_of[r["optimised_id"]]
        if op_name != r["optimised_op"]:
            raise SystemExit(f"{cfg}: kernel {i} NPU operation {op_name} != debug db {r['optimised_op']}")
        if ub != f"U{ub_dims[0]}X{ub_dims[1]}":   # register microblock vs Vela's ublock (two independent sources)
            raise SystemExit(f"{cfg}: kernel {i} register microblock {ub} != Vela ublock {ub_dims}")
        out.append(dict(config=cfg, index=i, offset=k["offset"], source_id=int(r["source_id"]), source_op=r["source_op"],
                        kind=k["kind"], ofm_rows=f"{c['ofm'][0]}-{c['ofm'][3]}", ofm_ch=f"{c['ofm'][2]}-{c['ofm'][5]}",
                        ofm_elems=volume(c["ofm"]), ifm_elems=volume(c["ifm"]), cascaded=c["cascaded"],
                        buffered=c["buffered"],
                        block=f"{k['blk_height_m1'] + 1}x{k['blk_width_m1'] + 1}x{k['blk_depth_m1'] + 1}",
                        microblock=ub, ofm_ublock="x".join(map(str, ub_dims)), ofm_ublocks=ublocks(c["ofm"], ub_dims),
                        acc_input=acc_in, kernel=f"{(k['kernel_height_m1'] or 0) + 1}x{(k['kernel_width_m1'] or 0) + 1}",
                        ifm_region=REGION.get(k["ifm_region"], k["ifm_region"]),
                        ofm_region=REGION.get(k["ofm_region"], k["ofm_region"]),
                        weight_region=REGION.get(k["weight_region"], k["weight_region"]) if wl else "",
                        weight_stream_bytes=wl, dma_bytes=sum(x or 0 for x in k["dma_before"]),
                        hl_dma_bytes=sum(x["length"] for x in c["dmas"])))
        if out[-1]["dma_bytes"] != out[-1]["hl_dma_bytes"]:
            raise SystemExit(f"{cfg}: kernel {i} register DMA != high-level DMA")
    return out


def per_source(rows: list[dict]) -> list[dict]:
    out = []
    for cfg in CONFIGS:
        for sid in sorted({r["source_id"] for r in rows if r["config"] == cfg}):
            g = [r for r in rows if r["config"] == cfg and r["source_id"] == sid]
            j = lambda f: "/".join(sorted({str(r[f]) for r in g}))
            out.append(dict(config=cfg, source_id=sid, source_op=g[0]["source_op"], kernels=len(g),
                            ofm_rows_per_kernel=j("ofm_rows") if len(g) <= 3 else f"{len(g)} stripes",
                            cascaded=any(r["cascaded"] for r in g), block=j("block"), microblock=j("microblock"),
                            ofm_ublock=j("ofm_ublock"), ofm_ublocks=sum(r["ofm_ublocks"] for r in g),
                            acc_input=j("acc_input"),
                            kernel=j("kernel"), ifm_region=j("ifm_region"), ofm_region=j("ofm_region"),
                            weight_region=j("weight_region"), ofm_elems=sum(r["ofm_elems"] for r in g),
                            ifm_elems=sum(r["ifm_elems"] for r in g),
                            weight_stream_bytes=sum(r["weight_stream_bytes"] for r in g),
                            dma_bytes=sum(r["dma_bytes"] for r in g)))
    return out


def write(path: pathlib.Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)


def main(out: str) -> list[dict]:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    rows = [r for cfg in CONFIGS for r in kernels(cfg)]
    src = per_source(rows)
    write(o / "per_kernel.csv", rows)
    write(o / "per_source_op.csv", src)
    return src


if __name__ == "__main__":
    for r in main(sys.argv[1]):
        print(r)
