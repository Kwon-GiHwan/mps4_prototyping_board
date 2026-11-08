#!/usr/bin/env python3
"""Stage 2B-3 Phase 1: one row per kernel operation of an Ethos-U85 command stream, from the register state the
stream sets (static; no board data). POST_HOC_DESCRIPTIVE.
`sparse` = 1 if NPU_SET_WEIGHT_FORMAT selects 2:4 weight sparsity (bit 4 of the parameter) for a CONV/DEPTHWISE op:
TRM 102685 Table 7 doubles the 1024 MACs/cycle of convolutions with sparsity.

  python3 host/analysis/cms_timeline.py <out dir> <op_map dir> <model.pmwl>...

Per row: position, type, BLOCKDEP, the synchronisation commands parsed since the previous kernel op (DMA_START,
DMA_WAIT k, KERNEL_WAIT n), OFM/kernel/IFM shape, MACs from the registers, and the data dependency on earlier ops
(ifm_src / ifm2_src = the last earlier op whose OFM byte range overlaps the IFM / IFM2 range in the same region;
dep_prev = 1 if that is op i-1). MACs as Vela counts them: CONV OFM x kernel x IFM depth, DEPTHWISE and POOL
OFM x kernel, others 0. The 2B-2 mask window of op i is
[after op i-1's kernel instruction, after op i's kernel instruction) (`cms.gate_ops`); it is not a column.
Opcodes and fields: ethos-u-core-driver `ethosu85_interface.h` (cmd0 value = word bits 31:16; cmd1 value =
bits 31:16 << 32 | second word).
"""
import csv, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms  # noqa: E402
import pmwl  # noqa: E402

DMA_START, DMA_WAIT, KERNEL_WAIT, BLOCKDEP, WEIGHT_FORMAT = 16, 17, 18, 303, 302
IFM_DEPTH_M1, IFM_HEIGHT0_M1, IFM_REGION = 260, 267, 271
OFM_WIDTH_M1, OFM_HEIGHT_M1, OFM_DEPTH_M1, OFM_REGION = 273, 274, 275, 287
KERNEL_WIDTH_M1, KERNEL_HEIGHT_M1, IFM2_HEIGHT0_M1, IFM2_REGION = 288, 289, 395, 399
IFM_BASE0, IFM_STRIDE_Y, OFM_BASE0, OFM_STRIDE_Y, IFM2_BASE0, IFM2_STRIDE_Y = 0, 5, 16, 21, 128, 133


def span(reg0, reg1, base, stride_y, height_m1, region):
    """(region, start, end) of a feature map's bytes, or None if a register was never set."""
    if base not in reg1 or stride_y not in reg1 or height_m1 not in reg0 or region not in reg0:
        return None
    return reg0[region], reg1[base], reg1[base] + reg1[stride_y] * (reg0[height_m1] + 1)


def overlaps(a, b):
    return a is not None and b is not None and a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def macs(kind, reg):
    out = (reg[OFM_HEIGHT_M1] + 1) * (reg[OFM_WIDTH_M1] + 1) * (reg[OFM_DEPTH_M1] + 1)
    k = (reg.get(KERNEL_HEIGHT_M1, 0) + 1) * (reg.get(KERNEL_WIDTH_M1, 0) + 1)
    if kind == "CONV":
        return out * k * (reg.get(IFM_DEPTH_M1, 0) + 1)
    if kind in ("DEPTHWISE", "POOL"):
        return out * k
    return 0


def timeline(stream):
    reg0, reg1, sync, rows, ofms = {}, {}, [], [], []
    for off, word, ctrl, op in cms.instructions(stream):
        if ctrl == 1:
            reg1[op] = (word >> 16) << 32 | struct.unpack_from("<I", stream, off + 4)[0]
            continue
        val = word >> 16
        if op in (DMA_START, DMA_WAIT, KERNEL_WAIT):
            sync.append({DMA_START: "DMA_START", DMA_WAIT: f"DMA_WAIT k={val & 3}",
                         KERNEL_WAIT: f"KERNEL_WAIT n={val & 1}"}[op])
        elif op in cms.KERNEL_OPS:
            kind = cms.KERNEL_OPS[op]
            ifm = span(reg0, reg1, IFM_BASE0, IFM_STRIDE_Y, IFM_HEIGHT0_M1, IFM_REGION)
            ifm2 = (span(reg0, reg1, IFM2_BASE0, IFM2_STRIDE_Y, IFM2_HEIGHT0_M1, IFM2_REGION)
                    if kind == "ELEMENTWISE" else None)
            ofm = span(reg0, reg1, OFM_BASE0, OFM_STRIDE_Y, OFM_HEIGHT_M1, OFM_REGION)
            src = [max((j for j, o in enumerate(ofms) if overlaps(fm, o)), default=None) for fm in (ifm, ifm2)]
            i = len(rows)
            rows.append(dict(
                index=i, offset=off, type=kind, blockdep=reg0.get(BLOCKDEP, 0) & 7, sync_before=" ".join(sync),
                ofm_hwc=f"{reg0[OFM_HEIGHT_M1] + 1}x{reg0[OFM_WIDTH_M1] + 1}x{reg0[OFM_DEPTH_M1] + 1}",
                kernel_hw=f"{reg0.get(KERNEL_HEIGHT_M1, 0) + 1}x{reg0.get(KERNEL_WIDTH_M1, 0) + 1}",
                ifm_depth=reg0.get(IFM_DEPTH_M1, 0) + 1, macs=macs(kind, reg0),
                sparse=int(kind in ("CONV", "DEPTHWISE") and reg0.get(WEIGHT_FORMAT, 0) >> 4 & 1),
                ifm_src="" if src[0] is None else src[0], ifm2_src="" if src[1] is None else src[1],
                dep_prev=int(i - 1 in src)))
            ofms.append(ofm)
            sync = []
        else:
            reg0[op] = val
    return rows


def main(out, op_map_dir, *blobs):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    for p in map(pathlib.Path, blobs):
        b = p.read_bytes(); h = pmwl.parse_header(b)
        rows = timeline(b[h["cms_off"]:h["cms_off"] + h["cms_len"]])
        name = p.name.rsplit(".", 2)[0]
        with open(pathlib.Path(op_map_dir) / f"{name}.op_map.csv") as f:
            om = list(csv.DictReader(f))
        if [r["stream_op"] for r in om] != [r["type"] for r in rows]:
            raise SystemExit(f"{name}: op_map stream types differ from the blob's command stream")
        rows = [dict(r, optimised_id=m["optimised_id"], optimised_op=m["optimised_op"], source_op=m["source_op"])
                for r, m in zip(rows, om)]
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
        print(name, len(rows), "kernel ops", sum(r["macs"] for r in rows), "MACs")


if __name__ == "__main__":
    main(*sys.argv[1:])
