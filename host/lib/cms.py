"""Ethos-U85 command stream (Vela output) in a PMWL blob: instruction boundaries, kernel operations, NPU_OP_PMU_MASK
insertion and repacking (Stage 2B-0 / 2B group gating).

Encoding (core-driver ethosu85_interface.h): 32-bit words; opcode bits 9:0, control bits 15:14 (0 = cmd0, one word,
parameter in 31:16; 1 = cmd1, a second payload word follows). NPU_OP_PMU_MASK = cmd0 opcode 19, enable bit 16; it
gates counting only when PMCR.mask_en = 1 (PMWL knob word 30).
"""
from __future__ import annotations

import struct

import pmwl

KERNEL_OPS = {2: "CONV", 3: "DEPTHWISE", 5: "POOL", 6: "ELEMENTWISE", 7: "RESIZE"}
OP_STOP, OP_PMU_MASK = 0, 19


def instructions(stream: bytes) -> list[tuple[int, int, int, int]]:
    """(byte offset, first word, control, opcode) per instruction."""
    out, i = [], 0
    while i < len(stream):
        word = struct.unpack_from("<I", stream, i)[0]
        ctrl, op = (word >> 14) & 3, word & 0x3FF
        size = 8 if ctrl == 1 else 4
        if i + size > len(stream):
            raise ValueError(f"instruction at {i} runs past the end of the command stream")
        out.append((i, word, ctrl, op))
        i += size
    return out


def kernel_offsets(stream: bytes) -> list[int]:
    return [o for o, _, c, op in instructions(stream) if c == 0 and op in KERNEL_OPS]


def boundaries(stream: bytes) -> list[int]:
    """Insertion points: 0 (before kernel op 0's setup), then right after each kernel op instruction."""
    return [0] + [o + 4 for o in kernel_offsets(stream)]


def pmu_mask(enable: int) -> int:
    return OP_PMU_MASK | (enable & 1) << 16


def insert(stream: bytes, at: dict[int, list[int]]) -> bytes:
    """Insert words before the instructions at the given byte offsets (instruction boundaries before the STOP)."""
    ins = instructions(stream)
    valid = {o for o, *_ in ins}
    stop_at = max(o for o, _, c, op in ins if c == 0 and op == OP_STOP)
    for off in at:
        if off not in valid or off > stop_at:
            raise ValueError(f"offset {off} is not an instruction boundary before the STOP")
    out, prev = bytearray(), 0
    for off in sorted(at):
        out += stream[prev:off] + struct.pack(f"<{len(at[off])}I", *at[off])
        prev = off
    return bytes(out + stream[prev:])


def gate(stream: bytes, first: int, end: int) -> bytes:
    """Count only kernel ops first..end-1 (as parsed): disable at the start, enable before op `first`'s setup, disable
    after op end-1. Ops already in flight across a boundary are not separated (BLOCKDEP overlap)."""
    b = boundaries(stream)
    if not 0 <= first < end <= len(b) - 1:
        raise ValueError(f"ops {first}..{end - 1}: stream has {len(b) - 1} kernel ops")
    at = {b[first]: [pmu_mask(1)], b[end]: [pmu_mask(0)]}
    if first > 0:
        at[0] = [pmu_mask(0)]
    return insert(stream, at)


def with_cms(blob: bytes, stream: bytes) -> bytes:
    """The same blob (knobs, const, IFMs, goldens, arena layout) repacked around another command stream."""
    h = pmwl.parse_header(blob)
    data = lambda off, n: blob[off:off + n]
    info = dict(cms=stream, const=data(h["const_off"], h["const_len"]), arena_size=h["arena_size"],
                fast_size=h["fast_size"])
    ins = [(e["arena_off"], e["len"]) for e in h["inputs"]]
    outs = [(e["arena_off"], e["len"]) for e in h["outputs"]]
    ifms = [data(e["data_off"], e["len"]) for e in h["inputs"]]
    golds = [data(e["golden_off"], e["len"]) for e in h["outputs"]]
    if h["version"] == 4:
        return pmwl.pack(dict(info, inputs=ins, outputs=outs), ifms, golds, h["knobs"])
    info.update(ifm_off=ins[0][0], ifm_len=ins[0][1], ofm_off=outs[0][0], ofm_len=outs[0][1])
    return pmwl.pack(info, ifms[0], golds[0], h["knobs"])
