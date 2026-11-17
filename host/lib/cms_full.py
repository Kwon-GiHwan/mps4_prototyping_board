"""Full Ethos-U85 register state at every kernel instruction of a command stream (Stage 6B-E2C). Register names come from
docs/reference/u85_cmd_opcodes.json (Vela 5.0.0 ethos_u85_interface.hpp enums cmd0_opcode / cmd1_opcode); cmd0 values
are the 16-bit parameter, cmd1 values the 48-bit (parameter << 32 | payload) like cms_regs."""
from __future__ import annotations

import json
import pathlib
import re

import cms

TABLE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reference" / "u85_cmd_opcodes.json"
_T = json.loads(TABLE.read_text())
CMD0 = {int(k): v for k, v in _T["cmd0_opcode"].items()}
CMD1 = {int(k): v for k, v in _T["cmd1_opcode"].items()}

ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\d*|.*_REGION|DMA0_SRC|DMA0_DST)$")
LAYOUT = re.compile(r"^NPU_SET_(IFM2?_STRIDE_[XYC]|OFM_STRIDE_[XYC]|IFM2?_PRECISION|OFM_PRECISION)$")
DEPENDENCY = {"NPU_SET_BLOCKDEP"}


def category(name: str) -> str:
    if ADDRESS.match(name):
        return "ADDRESS"
    if LAYOUT.match(name):
        return "LAYOUT"
    if name in DEPENDENCY:
        return "DEPENDENCY"
    return "COMPUTE"


def kernels(stream: bytes) -> list[dict]:
    """[{"kind": .., "offset": .., "regs": {name: value}, "dma": [{name: value} at each DMA_START before it]}]."""
    reg, dmas, out = {}, [], []
    for off, word, ctrl, op in cms.instructions(stream):
        if ctrl == 1:
            reg[CMD1.get(op, f"CMD1_{op}")] = (word >> 16) << 32 | int.from_bytes(stream[off + 4:off + 8], "little")
        elif op == 16:                                   # NPU_OP_DMA_START
            dmas.append({k: v for k, v in reg.items() if "DMA0" in k})
        elif op in cms.KERNEL_OPS:
            out.append(dict(kind=cms.KERNEL_OPS[op], offset=off, regs=dict(reg), dma=dmas))
            dmas = []
        elif CMD0.get(op, "").startswith("NPU_SET_"):
            reg[CMD0[op]] = word >> 16
    return out


def diff(a: dict, b: dict) -> dict:
    """{category: [register names that differ]} between two register dicts (a missing register counts as a difference)."""
    out = {}
    for n in sorted(set(a) | set(b)):
        if a.get(n) != b.get(n):
            out.setdefault(category(n), []).append(n)
    return out
