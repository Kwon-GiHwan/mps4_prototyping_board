#!/usr/bin/env python3
"""Stage 6B-E2C (evidence/stage6b/stage6be2c/contract.md §1-2): facts only. Compiles the fixed candidate list of G12
configurations at EXT read latency 500 (MLEK ini) and 1000 (one line changed, as E2A), and records per compile: Vela /
command stream / constant digests, IO, arena and fast sizes, the operator list, the debug-DB perf rows, the full register
state at every kernel (cms_full) and the sha256 of each kernel's weight and scale streams. Also the CPU checks: A2's
intermediate Conv input, A0 run on it, and the outputs against the committed references.

  stage6be2c_configs.py <A0 tflite> <A2 tflite> <A2 ifm.bin (a|b)> <A2 ref_ofm.bin> <out.json>
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
import cms_full  # noqa: E402
from pack_vela_workload import MLEK_INI, inspect_vela  # noqa: E402
from stage6be2a_vela import BASE_SECTION, compile_one, variant_inis  # noqa: E402

# contract §1: the fixed candidate list (cell, form, extra Vela options); W1-P0 candidates in this order
CANDIDATES = [("W0-P0", "A0", []), ("W1-P1", "A2", []), ("W0-P1-est", "A0", ["--memory-mode", "Shared_Sram"]),
              ("W1-P0-c0", "A2", ["--arena-cache-size", "0"]), ("W1-P0-c16384", "A2", ["--arena-cache-size", "16384"]),
              ("W1-P0-c65536", "A2", ["--arena-cache-size", "65536"])]
LATENCY_VARIANT = "E2A_Dram_read_latency_1000"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def compile_with(tfl: str, ini: str, sysname: str, extra: list[str]) -> dict:
    """stage6be2a_vela.compile_one with extra options; --memory-mode replaces the packer's value."""
    import pack_vela_workload as P
    saved = list(P.VELA_OPTIONS)
    opts = list(saved)
    if "--memory-mode" in extra:
        opts[opts.index("--memory-mode") + 1] = extra[extra.index("--memory-mode") + 1]
        extra = [x for i, x in enumerate(extra) if x != "--memory-mode" and (i == 0 or extra[i - 1] != "--memory-mode")]
    import stage6be2a_vela as V
    V.VELA_OPTIONS[:] = opts + extra
    try:
        return compile_one(tfl, ini, sysname, True), opts + extra
    finally:
        V.VELA_OPTIONS[:] = saved


def streams(vela_tflite: bytes, kernels: list[dict], const: bytes) -> list[dict]:
    out = []
    for k in kernels:
        r, s = k["regs"], {}
        for w in ("WEIGHT", "WEIGHT1", "WEIGHT2", "WEIGHT3", "SCALE"):
            base, ln = r.get(f"NPU_SET_{w}_BASE"), r.get(f"NPU_SET_{w}_LENGTH")
            if ln:
                region = r.get("NPU_SET_SCALE_REGION" if w == "SCALE" else "NPU_SET_WEIGHT_REGION")
                s[w] = dict(region=region, base=base, length=ln,
                            const_sha256=sha(const[base:base + ln]) if region == 0 and base + ln <= len(const) else None)
        out.append(s)
    return out


def facts_of(tfl: str, ini_text: str, sysname: str, extra: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as d:
        c, opts = compile_with(tfl, ini_text, sysname, extra)
        if not c.get("ok"):
            return dict(ok=False, options=opts, why=c.get("why"), stderr_tail=c.get("stderr_tail"))
    # re-run once more to get the Vela file for the stream decode (compile_one does not return bytes)
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        ini_p = MLEK_INI
        o = list(opts)
        if sysname != BASE_SECTION:
            ini_p = os.path.join(d, "e2c.ini"); pathlib.Path(ini_p).write_text(ini_text)
            o[o.index("--config") + 1] = ini_p; o[o.index("--system-config") + 1] = sysname
        subprocess.run(["vela", tfl, *o, "--output-dir", d], check=True, capture_output=True)
        vt = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        blob = open(vt, "rb").read()
        info = inspect_vela(vt)
    ks = cms_full.kernels(info["cms"])
    keep = ("id", "operator", "op_cycles", "npu_cycles", "Sram_ac", "Dram_ac")
    dbg_keep = ("id", "ifm_memory", "ofm_memory", "ifm_format", "ofm_format")
    return dict(ok=True, options=opts, vela_sha256=sha(blob), vela_equals_first_compile=sha(blob) == c["vela_sha256"],
                cms_sha256=sha(info["cms"]), const_sha256=sha(info["const"]), arena_size=info["arena_size"],
                fast_size=info["fast_size"], inputs=info["inputs"], outputs=info["outputs"], summary=c["summary"],
                perf=[{k: r.get(k) for k in keep} for r in c["db"]["perf"]],
                perf_debug=[{k: r.get(k) for k in dbg_keep} for r in c["db"]["perf_debug"]],
                main=c["db"]["perf_debug_main"], kernels=ks, streams=streams(blob, ks, info["const"]))


def cpu_checks(a0: str, a2: str, ifm_bin: str, ref_bin: str) -> dict:
    import numpy as np
    from tflite_runtime.interpreter import Interpreter
    raw = pathlib.Path(ifm_bin).read_bytes()
    half = len(raw) // 2
    it = Interpreter(model_path=a2, experimental_preserve_all_tensors=True); it.allocate_tensors()
    ins = {d["name"]: d for d in it.get_input_details()}
    for n, part in (("a", raw[:half]), ("b", raw[half:])):
        it.set_tensor(ins[n]["index"], np.frombuffer(part, dtype=np.int8).reshape(ins[n]["shape"]))
    it.invoke()
    tens = {t["name"]: t["index"] for t in it.get_tensor_details()}
    conv_in, conv_out = it.get_tensor(tens["ifm"]).tobytes(), it.get_tensor(tens["conv_out"]).tobytes()
    a2_out = it.get_tensor(it.get_output_details()[0]["index"]).tobytes()
    i0 = Interpreter(model_path=a0); i0.allocate_tensors()
    d0 = i0.get_input_details()[0]
    i0.set_tensor(d0["index"], np.frombuffer(conv_in, dtype=np.int8).reshape(d0["shape"])); i0.invoke()
    a0_out = i0.get_tensor(i0.get_output_details()[0]["index"]).tobytes()
    wsha = lambda p: {t["name"]: sha(Interpreter(model_path=p).get_tensor(t["index"]).tobytes())
                      for t in Interpreter(model_path=p).get_tensor_details() if t["name"] in ("weights", "bias")}
    return dict(a2_conv_input_sha256=sha(conv_in), a2_conv_out_sha256=sha(conv_out), a0_out_on_a2_conv_input_sha256=sha(a0_out),
                a0_out_equals_a2_conv_out=a0_out == conv_out, a2_out_equals_ref=a2_out == pathlib.Path(ref_bin).read_bytes(),
                a2_out_sha256=sha(a2_out), conv_in_len=len(conv_in), weights_a0=wsha(a0), weights_a2=wsha(a2),
                conv_input_bytes_hex_sha=sha(conv_in))


def main(a0: str, a2: str, ifm_bin: str, ref_bin: str, out: str) -> None:
    ini = pathlib.Path(MLEK_INI).read_text()
    lat = variant_inis(ini)[LATENCY_VARIANT][0]
    form = {"A0": a0, "A2": a2}
    res = dict(sources={k: dict(path=v, sha256=sha(pathlib.Path(v).read_bytes())) for k, v in form.items()},
               mlek_ini_sha256=sha(ini.encode()), candidates={})
    for cell, f, extra in CANDIDATES:
        res["candidates"][cell] = dict(form=f, extra=extra, L500=facts_of(form[f], ini, BASE_SECTION, extra),
                                       L1000=facts_of(form[f], lat, LATENCY_VARIANT, extra))
        print(cell, res["candidates"][cell]["L500"].get("ok"), res["candidates"][cell]["L1000"].get("ok"), flush=True)
    res["cpu"] = cpu_checks(a0, a2, ifm_bin, ref_bin)
    pathlib.Path(out).write_text(json.dumps(res, indent=1, sort_keys=True, default=str))
    print(out, sha(pathlib.Path(out).read_bytes()))


if __name__ == "__main__":
    main(*sys.argv[1:6])
