#!/usr/bin/env python3
"""Mobilenet output verification: parse MLEK's VERIFY_TEST_OUTPUT UART dump, compare OFMs byte by byte.

  python3 host/ofm_compare.py dump <app_uart.raw> <out dir>      -> ifm.bin, mlek_ofm.bin
  python3 host/ofm_compare.py cmp <a.bin> <b.bin> [labels a b]   -> JSON: count, positions, values, signed diff, max
Bytes are compared as int8 (the model's output type); signed difference = a - b.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

IFM_MARK = "input tensors populated"
OFM_MARK = "output tensors post inference"
HEX = re.compile(r"0x([0-9a-f]{2}),")


def section(text: str, mark: str) -> bytes:
    """The hex dump that follows the first `mark` line: lines of `0x.., ` values (the board's UART drops the
    source's leading tab) up to the first other non-empty line."""
    lines = text.split(mark, 1)[1].splitlines()[1:]
    out = bytearray()
    for ln in lines:
        if ln.lstrip("\t").startswith("0x"):
            out += bytes(int(h, 16) for h in HEX.findall(ln))
        elif ln.strip():
            if out:
                break
    return bytes(out)


def int8(b: int) -> int:
    return b - 256 if b > 127 else b


def compare(a: bytes, b: bytes) -> dict:
    if len(a) != len(b):
        raise ValueError(f"length {len(a)} != {len(b)}")
    pos = [i for i in range(len(a)) if a[i] != b[i]]
    diff = [int8(a[i]) - int8(b[i]) for i in pos]
    return {"length": len(a), "mismatch_count": len(pos), "positions": pos,
            "a_values": [int8(a[i]) for i in pos], "b_values": [int8(b[i]) for i in pos],
            "signed_diff_a_minus_b": diff, "max_abs_diff": max((abs(d) for d in diff), default=0)}


def main() -> int:
    if sys.argv[1] == "dump":
        text = pathlib.Path(sys.argv[2]).read_bytes().decode("ascii", "replace").replace("\r", "")
        out = pathlib.Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
        ifm, ofm = section(text, IFM_MARK), section(text, OFM_MARK)
        (out / "ifm.bin").write_bytes(ifm); (out / "mlek_ofm.bin").write_bytes(ofm)
        print(json.dumps({"ifm_bytes": len(ifm), "ofm_bytes": len(ofm)}))
        return 0
    a, b = pathlib.Path(sys.argv[2]).read_bytes(), pathlib.Path(sys.argv[3]).read_bytes()
    r = compare(a, b)
    if len(sys.argv) > 5:
        r = {"a": sys.argv[4], "b": sys.argv[5], **r}
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
