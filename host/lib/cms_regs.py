"""Register state of an Ethos-U85 command stream at every kernel instruction (decoded from the stream bytes the board
runs). Shared by the Stage 4C/5 analyses and the container compile checks; register numbers from the core driver's
ethosu85_interface.h (cmd0 = 16-bit parameter, cmd1 = 32/48-bit payload)."""
from __future__ import annotations

import cms

C0 = dict(ifm_depth_m1=0x104, ifm_precision=0x105, ifm_region=0x10F, ofm_width_m1=0x111, ofm_height_m1=0x112,
          ofm_depth_m1=0x113, ofm_precision=0x114, blk_width_m1=0x115, blk_height_m1=0x116, blk_depth_m1=0x117,
          ofm_region=0x11F, acc_format=0x124, ifm_width0_m1=0x10A, ifm_height0_m1=0x10B,
          kernel_width_m1=0x120, kernel_height_m1=0x121, kernel_stride=0x122, weight_region=0x128)
C1 = dict(ifm_base0=0x00, ifm_stride_x=0x04, ifm_stride_y=0x05, ifm_stride_c=0x06, ofm_base0=0x10, ofm_stride_x=0x14,
          ofm_stride_y=0x15, ofm_stride_c=0x16, weight_length=0x21, weight1_length=0x91, weight2_length=0x93,
          weight3_length=0x95, dma_len=0x32)
OP_DMA_START = 0x10


def kernels(stream: bytes) -> list[dict]:
    """Register state at every kernel instruction, plus the DMA lengths started before it."""
    reg0, reg1, dmas, out = {}, {}, [], []
    for off, word, ctrl, op in cms.instructions(stream):
        if ctrl == 1:
            reg1[op] = (word >> 16) << 32 | int.from_bytes(stream[off + 4:off + 8], "little")
        elif op == OP_DMA_START:
            dmas.append(reg1.get(C1["dma_len"]))
        elif op in cms.KERNEL_OPS:
            k = {n: reg0.get(v) for n, v in C0.items()}
            k.update({n: reg1.get(v) for n, v in C1.items()})
            k.update(kind=cms.KERNEL_OPS[op], offset=off, dma_before=list(dmas))
            out.append(k)
            dmas = []
        else:
            reg0[op] = word >> 16
    return out
