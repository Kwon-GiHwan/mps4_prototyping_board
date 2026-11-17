#!/usr/bin/env python3
"""Stage 6E-X3 workloads (kws, ad; B0..B4) from the driver_m7 DRWLs (docs/plan/stage6ex3_directive_chatgpt.txt,
amendment A). B0 = the m7 bytes unchanged (pmu_flags 0). B1..B4 = one serialised stream (KERNEL_WAIT n=0 + PMU_MASK at
every kernel boundary, host/lib/cms.serial_mask) that differs between B1..B4 only in the PMU_MASK enable bits, put into
the model by redirecting the ethos-u op's COP1 buffer (host/lib/tflite_cop1.py), pmu_flags 1 (PMCR.mask_en).

  python3 stage6ex3_workloads.py <m7 DRWL dir> <out dir>
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import cms  # noqa: E402
import drwl  # noqa: E402
import tflite_cop1  # noqa: E402

MODELS = ("kws_micronet_m", "ad_medium_int8")
OP_MAP = REPO / "results/fi101_stage2_groups/vela_op_map"
LEVELS = REPO / "results/fi101_stage6d/operator_levels.csv"
# contract: G_0 = TFLite op 0; G_V = TFLite ops at 6D EXACT_VALIDATED (DF1x1); G_R = every other kernel op
EXPECTED = {"kws_micronet_m": {"G_0": [0, 1], "G_V": [3, 5, 7]},
            "ad_medium_int8": {"G_0": [0, 1], "G_V": [3, 5, 7, 9]}}
CONDS = ("B0", "B1", "B2", "B3", "B4")
COND_GROUP = {"B2": "G_V", "B3": "G_0", "B4": "G_R"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def groups(model: str) -> dict[str, list[int]]:
    """Stream kernel-op indices per group: op map source_id − 1 = TFLite op index; levels from 6D."""
    rows = list(csv.DictReader((OP_MAP / f"{model}.op_map.csv").open()))
    lv = {int(r["op"]): r["level"] for r in csv.DictReader(LEVELS.open()) if r["model"] == model}
    g0 = [int(r["index"]) for r in rows if int(r["source_id"]) - 1 == 0]
    gv = [int(r["index"]) for r in rows if lv.get(int(r["source_id"]) - 1) == "EXACT_VALIDATED"]
    gr = [int(r["index"]) for r in rows if int(r["index"]) not in g0 + gv]
    return {"G_0": g0, "G_V": gv, "G_R": gr}


def bits_for(cond: str, g: dict, n: int) -> list[int]:
    if cond == "B1":
        return [1] * n
    members = set(g[COND_GROUP[cond]])
    return [1 if i in members else 0 for i in range(n)]


def build(src: pathlib.Path, out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    man = {}
    for m in MODELS:
        blob = (src / f"{m}.drwl").read_bytes()
        h = drwl.parse(blob)
        model = blob[h["model_off"]:h["model_off"] + h["model_len"]]
        cop = tflite_cop1.cop1(model)
        orig = _cms_of(cop)
        n = len(cms.kernel_offsets(orig))
        g = groups(m)
        if {k: g[k] for k in ("G_0", "G_V")} != EXPECTED[m]:
            raise SystemExit(f"{m}: groups {g} differ from the contract")
        if sorted(g["G_0"] + g["G_V"] + g["G_R"]) != list(range(n)):
            raise SystemExit(f"{m}: groups do not partition {n} kernel ops")
        ifms = [blob[o:o + ln] for o, ln in h["inputs"]]
        golds = [blob[o:o + ln] for o, ln in h["outputs"]]
        for c in CONDS:
            if c == "B0":
                wl, stream, bits, flags = blob, orig, None, 0
            else:
                bits = bits_for(c, g, n)
                stream = cms.serial_mask(orig, bits)
                flags = drwl.PMU_MASK_EN
                new_model = tflite_cop1.with_cop1(model, tflite_cop1.cop1_with_cms(cop, stream))
                wl = drwl.pack(new_model, ifms, golds, placement=h["placement"], pmu_flags=flags)
            key = f"x3_{m.split('_')[0]}_{c}"
            (out / f"{key}.drwl").write_bytes(wl)
            (out / f"{key}.cms.bin").write_bytes(stream)
            man[key] = dict(model=m, cond=c, drwl_sha256=sha(wl), cms_sha256=sha(stream), cms_len=len(stream),
                            stripped_cms_sha256=sha(cms.strip_serial(stream)), orig_cms_sha256=sha(orig),
                            kernel_ops=len(cms.kernel_offsets(stream)), bits=bits, pmu_flags=flags,
                            placement=h["placement"], source_drwl_sha256=sha(blob), groups=g)
    (out / "x3_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def _cms_of(cop: bytes) -> bytes:
    """Command stream from a COP1 payload (inverse of tflite_cop1.cop1_with_cms for one COMMAND_STREAM)."""
    import struct
    words = struct.unpack(f"<{len(cop) // 4}I", cop)
    i = 1
    while i < len(words):
        w = words[i]
        cmd = w & 0xFF
        if cmd == tflite_cop1.DA_OPTIMIZER_CONFIG:
            i += 3
        elif cmd == tflite_cop1.DA_COMMAND_STREAM:
            n = ((w >> 8) & 0xFF) << 16 | (w >> 16)
            return cop[(i + 1) * 4:(i + 1 + n) * 4]
        elif cmd == tflite_cop1.DA_NOP:
            i += 1
        else:
            raise ValueError(f"driver action {cmd}")
    raise ValueError("no COMMAND_STREAM")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    for k, v in build(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])).items():
        print(k, v["drwl_sha256"][:8], v["cms_len"], v["kernel_ops"], v["bits"])
