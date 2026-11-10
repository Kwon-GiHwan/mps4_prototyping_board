"""DRWL driver-runner workload (docs/plan/driver_runner_plan.md J8): the Vela output file as it is, the IFMs to put into
the model's input tensors and the golden OFMs to compare its output tensors with, both in the model's graph order (the
order TFLM's GetInputTensor / GetOutputTensor use, which is MLEK's order).

The driver runner declares the same layout independently (firmware/driver_runner/use_case/pmu_runner/src/workload.h);
host/tests/test_driver_runner_contract.py requires the two to agree. Neither imports the other.

Little-endian u32 words:
  words 0..15  header (HEADER_FIELDS)
  words 16..   IO table: per input (data_off, len), then per output (golden_off, len)
  then the model, every IFM, every golden, each 16-byte aligned
"""
from __future__ import annotations

import struct

MAGIC = 0x4C575244   # 'DRWL'
VERSION = 1
HEADER_WORDS = 16
IO_WORD = HEADER_WORDS
IO_MAX = 8           # per side: up to 8 inputs and up to 8 outputs (rnnoise has 4 and 5)
ALIGN = 16
HEADER_FIELDS = ("magic", "version", "total_len", "model_off", "model_len", "n_in", "n_out")


def align(n: int, a: int = ALIGN) -> int:
    return (n + a - 1) // a * a


def pack(model: bytes, ifms: list[bytes], goldens: list[bytes]) -> bytes:
    if not model or not ifms or not goldens:
        raise ValueError("a model, at least one IFM and one golden are needed")
    if len(ifms) > IO_MAX or len(goldens) > IO_MAX:
        raise ValueError(f"{len(ifms)} IFMs / {len(goldens)} OFMs: at most {IO_MAX} each")
    off = align(4 * (HEADER_WORDS + 2 * (len(ifms) + len(goldens))))
    places = []
    for b in [model] + ifms + goldens:
        places.append(off)
        off = align(off + len(b))
    blob = bytearray(off)
    fields = dict(magic=MAGIC, version=VERSION, total_len=off, model_off=places[0], model_len=len(model),
                  n_in=len(ifms), n_out=len(goldens))
    struct.pack_into(f"<{len(HEADER_FIELDS)}I", blob, 0, *(fields[f] for f in HEADER_FIELDS))
    table = [w for p, b in zip(places[1:], ifms + goldens) for w in (p, len(b))]
    struct.pack_into(f"<{len(table)}I", blob, 4 * IO_WORD, *table)
    for p, b in zip(places, [model] + ifms + goldens):
        blob[p:p + len(b)] = b
    return bytes(blob)


def parse(blob: bytes) -> dict:
    """Header fields, 'inputs' and 'outputs' as (offset, len); refuses what the runner refuses."""
    if len(blob) < 4 * HEADER_WORDS:
        raise ValueError("shorter than the DRWL header")
    h = dict(zip(HEADER_FIELDS, struct.unpack_from(f"<{len(HEADER_FIELDS)}I", blob, 0)))
    if h["magic"] != MAGIC or h["version"] != VERSION:
        raise ValueError(f"not a DRWL v{VERSION} blob")
    if h["total_len"] != len(blob):
        raise ValueError(f"total_len {h['total_len']} != {len(blob)} bytes")
    n = h["n_in"] + h["n_out"]
    if not 1 <= h["n_in"] <= IO_MAX or not 1 <= h["n_out"] <= IO_MAX:
        raise ValueError(f"{h['n_in']} inputs / {h['n_out']} outputs")
    t = struct.unpack_from(f"<{2 * n}I", blob, 4 * IO_WORD)
    ents = [(h["model_off"], h["model_len"])] + [(t[2 * i], t[2 * i + 1]) for i in range(n)]
    for o, ln in ents:
        if o % ALIGN or ln == 0 or o + ln > len(blob) or o < 4 * (HEADER_WORDS + 2 * n):
            raise ValueError(f"section ({o}, {ln}) misplaced")
    h["inputs"], h["outputs"] = ents[1:1 + h["n_in"]], ents[1 + h["n_in"]:]
    return h
