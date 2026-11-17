#!/usr/bin/env python3
"""Stage 6B-E2E-A Track B (evidence/stage6b/stage6be2ea/contract.md B2, B3): Vela facts only.

  a0     the A0 (W0-P0) compile and the 26 E2A one-variable variants, full debug DB (stage6be2a_vela.compile_one)
  a2io   A2 with --memory-mode Shared_Sram (B3 estimator candidate) and with --separate-io-regions (B1/B2 candidate),
         latency 500 and 1000, E2C facts (registers, streams, memories)

  stage6be2ea_vela.py <A0 tflite> <A2 tflite> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
from pack_vela_workload import MLEK_INI  # noqa: E402
import stage6be2a_vela as V  # noqa: E402
import stage6be2c_configs as C  # noqa: E402

A2_CANDIDATES = [("A2-base", []), ("B3-est-Shared_Sram", ["--memory-mode", "Shared_Sram"]),
                 ("B12-separate-io", ["--separate-io-regions"])]


def main(a0: str, a2: str, out: str) -> None:
    ini = pathlib.Path(MLEK_INI).read_text()
    inis = V.variant_inis(ini)
    res = dict(sources={p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in (a0, a2)},
               variants={n: ch for n, (_, ch) in inis.items()}, a0={}, a2io={})
    for name, (text, _) in inis.items():
        res["a0"][name] = V.compile_one(a0, text, V.BASE_SECTION if name == "base" else name, True)
    lat = inis[C.LATENCY_VARIANT][0]
    for cid, extra in A2_CANDIDATES:
        res["a2io"][cid] = dict(extra=extra, L500=C.facts_of(a2, ini, V.BASE_SECTION, extra),
                                L1000=C.facts_of(a2, lat, C.LATENCY_VARIANT, extra))
        print(cid, res["a2io"][cid]["L500"].get("ok"), flush=True)
    pathlib.Path(out).write_text(json.dumps(res, indent=1, sort_keys=True, default=str))
    print(out, hashlib.sha256(pathlib.Path(out).read_bytes()).hexdigest())


if __name__ == "__main__":
    main(*sys.argv[1:4])
