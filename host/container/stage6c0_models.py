#!/usr/bin/env python3
"""Stage 6C-0 (evidence/stage6c0/contract.md §5): compile facts for the Stage 6C candidate shapes. Each shape is one
operator rebuilt from the original MLEK tflite's own tensors and options (CONV_2D / DEPTHWISE_CONV_2D / FULLY_CONNECTED:
weights, bias, quantization, stride, padding, dilation, depth multiplier, fused activation), optionally with one variable
changed (Cin / C rounded up to 16, Cout x2, depthwise kernel 3x3 -> 5x5; added weights from a fixed seed). Facts only:
every rule is in host/analysis/stage6c0.py. Runs in the benchmark-runner container.

  python3 stage6c0_models.py <out dir> <specs.json>      specs: [{name, model, op_index, variant}], variant one of
                                                          null | "cin16" | "c16" | "cout2" | "k5"
Per shape: <name>.tflite, .ifm.bin, .ref_ofm.bin (BUILTIN_REF), .drwl (pack_vela_workload, MLEK options) and a row in
<out dir>/compile_facts.json: the scheduled NPU rows (stage4_inventory format), CPU rows, pack result and sizes.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import flatbuffers
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
import make_op_model as M  # noqa: E402
import stage4ao_models as AO  # noqa: E402
import stage4aoe_models as AOE  # noqa: E402

(Conv2DOptions, DepthwiseConv2DOptions, FullyConnectedOptions) = (importlib.import_module("tflite." + n) for n in (
    "Conv2DOptions", "DepthwiseConv2DOptions", "FullyConnectedOptions"))
from tflite.BuiltinOptions import BuiltinOptions as BO  # noqa: E402

MLEK = pathlib.Path("/opt/arm/ml-embedded-evaluation-kit/resources_downloaded")
SOURCES = {"kws_micronet_m": "kws", "ad_medium_int8": "ad", "mobilenet_v2_1.0_224_INT8": "img_class",
           "vww4_128_128_INT8": "vww", "rnnoise_INT8": "noise_reduction", "yolo-fastest_192_face_v4": "object_detection",
           "wav2letter_pruned_int8": "asr"}
KINDS = {3: "conv", 4: "dw", 9: "fc"}
PROFILE = HERE.parents[1] / "config" / "fi101_s013.json"
SEED = 20261118
LIMITS = dict(fast_size=0x60000, arena_size=0x200000, model_region=32 << 20)


def source_op(model: str, op_index: int) -> dict:
    import tflite
    path = MLEK / SOURCES[model] / f"{model}.tflite"
    raw = path.read_bytes()
    m = tflite.Model.GetRootAsModel(raw, 0)
    g = m.Subgraphs(0)
    op = g.Operators(op_index)
    code = m.OperatorCodes(op.OpcodeIndex())
    builtin = max(code.BuiltinCode(), code.DeprecatedBuiltinCode())
    kind = KINDS[builtin]
    bo = op.BuiltinOptions()
    if kind == "conv":
        o = Conv2DOptions.Conv2DOptions(); o.Init(bo.Bytes, bo.Pos)
        opts = dict(padding=o.Padding(), stride=(o.StrideH(), o.StrideW()), dilation=(o.DilationHFactor(), o.DilationWFactor()),
                    act=o.FusedActivationFunction())
    elif kind == "dw":
        o = DepthwiseConv2DOptions.DepthwiseConv2DOptions(); o.Init(bo.Bytes, bo.Pos)
        opts = dict(padding=o.Padding(), stride=(o.StrideH(), o.StrideW()), dilation=(o.DilationHFactor(), o.DilationWFactor()),
                    mult=o.DepthMultiplier(), act=o.FusedActivationFunction())
    else:
        o = FullyConnectedOptions.FullyConnectedOptions(); o.Init(bo.Bytes, bo.Pos)
        opts = dict(act=o.FusedActivationFunction(), keep=o.KeepNumDims())

    def tensor(i):
        if i < 0:
            return None
        t = g.Tensors(i)
        q = t.Quantization()
        buf = m.Buffers(t.Buffer()).DataAsNumpy()
        return dict(shape=tuple(int(t.Shape(k)) for k in range(t.ShapeLength())), type=t.Type(),
                    scale=[float(x) for x in q.ScaleAsNumpy()] if q and q.ScaleLength() else [1.0],
                    zp=[int(x) for x in q.ZeroPointAsNumpy()] if q and q.ZeroPointLength() else [0],
                    qdim=q.QuantizedDimension() if q else 0, data=None if isinstance(buf, int) else buf.tobytes())
    ins = [tensor(op.Inputs(k)) for k in range(op.InputsLength())]
    return dict(model=model, op_index=op_index, kind=kind, version=code.Version(),
                model_sha256=hashlib.sha256(raw).hexdigest(), ifm=ins[0], w=ins[1], b=ins[2] if len(ins) > 2 else None,
                ofm=tensor(op.Outputs(0)), opts=opts)


def _np(t, dtype):
    return np.frombuffer(t["data"], dtype=dtype).reshape(t["shape"]).copy()


def _ext_scale(scale, n):
    return (scale + [scale[-1]] * n)[:max(n, len(scale))] if len(scale) > 1 else scale


def _ext_q(t: dict, n: int) -> dict:
    """Per-channel quantization extended to n channels (scale and zero point together; erratum 2026-11-18: the first
    version extended the scales only and TFLite refused the DW c16 model)."""
    return dict(t, scale=_ext_scale(t["scale"], n), zp=_ext_scale(t["zp"], n))


def _dup_q(t: dict) -> dict:
    return dict(t, scale=t["scale"] * 2 if len(t["scale"]) > 1 else t["scale"], zp=t["zp"] * 2 if len(t["zp"]) > 1 else t["zp"])


def variant(src: dict, v: str | None) -> dict:
    """One variable changed; the source tensors otherwise byte for byte. Returns a new dict."""
    if v is None:
        return src
    rng = np.random.default_rng(SEED)
    s = {k: (dict(x) if isinstance(x, dict) else x) for k, x in src.items()}
    w = _np(src["w"], np.int8)
    b = _np(src["b"], np.int32) if src["b"] and src["b"]["data"] else None
    ifm, ofm = list(src["ifm"]["shape"]), list(src["ofm"]["shape"])
    if v == "cin16" and src["kind"] in ("conv", "fc"):
        cin = ifm[-1]; new = -(-cin // 16) * 16
        pad = rng.integers(-127, 128, size=w.shape[:-1] + (new - cin,), dtype=np.int8)
        w = np.concatenate([w, pad], axis=-1); ifm[-1] = new
    elif v == "cout2" and src["kind"] in ("conv", "fc"):
        w = np.concatenate([w, w], axis=0); ofm[-1] *= 2
        b = np.concatenate([b, b]) if b is not None else None
        s["w"] = _dup_q(src["w"])
        if s["b"]:
            s["b"] = _dup_q(src["b"])
    elif v == "c16" and src["kind"] == "dw":
        c = w.shape[-1]; new = -(-c // 16) * 16
        w = np.concatenate([w, rng.integers(-127, 128, size=w.shape[:-1] + (new - c,), dtype=np.int8)], axis=-1)
        b = np.concatenate([b, rng.integers(-1024, 1025, size=new - c, dtype=np.int32)]) if b is not None else None
        ifm[-1] = new; ofm[-1] = new
        s["w"] = _ext_q(src["w"], new)
        if s["b"]:
            s["b"] = _ext_q(src["b"], new)
    elif v == "k5" and src["kind"] == "dw":
        w = rng.integers(-127, 128, size=(w.shape[0], 5, 5, w.shape[3]), dtype=np.int8)
    else:
        raise ValueError(f"variant {v} not defined for {src['kind']}")
    s["w"] = dict(s["w"], shape=tuple(w.shape), data=w.tobytes())
    if b is not None:
        s["b"] = dict(s["b"], shape=tuple(b.shape), data=b.tobytes())
    s["ifm"] = dict(s["ifm"], shape=tuple(ifm))
    s["ofm"] = dict(s["ofm"], shape=tuple(ofm))
    return s


def _options(b, src):
    k, o = src["kind"], src["opts"]
    if k == "conv":
        C = Conv2DOptions
        C.Conv2DOptionsStart(b); C.Conv2DOptionsAddPadding(b, o["padding"])
        C.Conv2DOptionsAddStrideH(b, o["stride"][0]); C.Conv2DOptionsAddStrideW(b, o["stride"][1])
        C.Conv2DOptionsAddDilationHFactor(b, o["dilation"][0]); C.Conv2DOptionsAddDilationWFactor(b, o["dilation"][1])
        C.Conv2DOptionsAddFusedActivationFunction(b, o["act"])
        return BO.Conv2DOptions, C.Conv2DOptionsEnd(b), 3
    if k == "dw":
        D = DepthwiseConv2DOptions
        D.DepthwiseConv2DOptionsStart(b); D.DepthwiseConv2DOptionsAddPadding(b, o["padding"])
        D.DepthwiseConv2DOptionsAddStrideH(b, o["stride"][0]); D.DepthwiseConv2DOptionsAddStrideW(b, o["stride"][1])
        D.DepthwiseConv2DOptionsAddDilationHFactor(b, o["dilation"][0]); D.DepthwiseConv2DOptionsAddDilationWFactor(b, o["dilation"][1])
        D.DepthwiseConv2DOptionsAddDepthMultiplier(b, o["mult"]); D.DepthwiseConv2DOptionsAddFusedActivationFunction(b, o["act"])
        return BO.DepthwiseConv2DOptions, D.DepthwiseConv2DOptionsEnd(b), 4
    F = FullyConnectedOptions
    F.FullyConnectedOptionsStart(b); F.FullyConnectedOptionsAddFusedActivationFunction(b, o["act"])
    F.FullyConnectedOptionsAddKeepNumDims(b, o["keep"])
    return BO.FullyConnectedOptions, F.FullyConnectedOptionsEnd(b), 9


def model_bytes(name: str, src: dict) -> bytes:
    """One operator: inputs (ifm, weights, bias), output ofm; the source opcode version."""
    b = flatbuffers.Builder(1 << 22)
    ts = [("ifm", src["ifm"], None), ("weights", src["w"], src["w"]["data"])]
    if src["b"]:
        ts.append(("bias", src["b"], src["b"]["data"]))
    ts.append(("ofm", src["ofm"], None))
    bufs = [M._buffer(b, None)] + [M._buffer(b, d) for _, _, d in ts]
    tens = [M._tensor(b, n, t["shape"], t["type"], i + 1, M._quant(b, t["scale"], t["zp"], t.get("qdim", 0)))
            for i, (n, t, _) in enumerate(ts)]
    otype, opts, code = _options(b, src)
    n_in = len(ts) - 1
    ins = AO._vec(b, M.Operator.OperatorStartInputsVector, list(range(n_in)), b.PrependInt32)
    outs = AO._vec(b, M.Operator.OperatorStartOutputsVector, [n_in], b.PrependInt32)
    M.Operator.OperatorStart(b)
    M.Operator.OperatorAddOpcodeIndex(b, 0); M.Operator.OperatorAddInputs(b, ins); M.Operator.OperatorAddOutputs(b, outs)
    M.Operator.OperatorAddBuiltinOptionsType(b, otype); M.Operator.OperatorAddBuiltinOptions(b, opts)
    op = M.Operator.OperatorEnd(b)
    t_vec = AO._vec(b, M.SubGraph.SubGraphStartTensorsVector, tens, b.PrependUOffsetTRelative)
    i_vec = AO._vec(b, M.SubGraph.SubGraphStartInputsVector, [0], b.PrependInt32)
    o_vec = AO._vec(b, M.SubGraph.SubGraphStartOutputsVector, [n_in], b.PrependInt32)
    ops = AO._vec(b, M.SubGraph.SubGraphStartOperatorsVector, [op], b.PrependUOffsetTRelative)
    gname = b.CreateString(name)
    M.SubGraph.SubGraphStart(b)
    M.SubGraph.SubGraphAddTensors(b, t_vec); M.SubGraph.SubGraphAddInputs(b, i_vec); M.SubGraph.SubGraphAddOutputs(b, o_vec)
    M.SubGraph.SubGraphAddOperators(b, ops); M.SubGraph.SubGraphAddName(b, gname)
    sg = M.SubGraph.SubGraphEnd(b)
    M.OperatorCode.OperatorCodeStart(b)
    M.OperatorCode.OperatorCodeAddDeprecatedBuiltinCode(b, code); M.OperatorCode.OperatorCodeAddBuiltinCode(b, code)
    M.OperatorCode.OperatorCodeAddVersion(b, src["version"])
    oc = M.OperatorCode.OperatorCodeEnd(b)
    sgs = AO._vec(b, M.Model.ModelStartSubgraphsVector, [sg], b.PrependUOffsetTRelative)
    ocs = AO._vec(b, M.Model.ModelStartOperatorCodesVector, [oc], b.PrependUOffsetTRelative)
    bvec = AO._vec(b, M.Model.ModelStartBuffersVector, bufs, b.PrependUOffsetTRelative)
    desc = b.CreateString("stage6c0")
    M.Model.ModelStart(b)
    M.Model.ModelAddVersion(b, 3); M.Model.ModelAddOperatorCodes(b, ocs); M.Model.ModelAddSubgraphs(b, sgs)
    M.Model.ModelAddDescription(b, desc); M.Model.ModelAddBuffers(b, bvec)
    b.Finish(M.Model.ModelEnd(b), file_identifier=b"TFL3")
    return bytes(b.Output())


def inventory_rows(model_path: pathlib.Path) -> list[dict]:
    import stage4_inventory as INV
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "inv.csv")
        INV.main(out, str(model_path))
        with open(out) as f:
            return list(csv.DictReader(f))


def one(spec: dict, o: pathlib.Path) -> dict:
    import drwl
    name = spec["name"]
    src = variant(source_op(spec["model"], spec["op_index"]), spec.get("variant"))
    mp = o / f"{name}.tflite"
    mp.write_bytes(model_bytes(name, src))
    rng = np.random.default_rng(SEED)
    x = rng.integers(-128, 128, size=src["ifm"]["shape"], dtype=np.int8)
    (o / f"{name}.ifm.bin").write_bytes(x.tobytes())
    res = dict(spec, kind=src["kind"], source_sha256=src["model_sha256"], ifm=list(src["ifm"]["shape"]),
               ofm=list(src["ofm"]["shape"]), weights=list(src["w"]["shape"]), opts={k: list(v) if isinstance(v, tuple) else v
                                                                                     for k, v in src["opts"].items()},
               model_sha256=hashlib.sha256(mp.read_bytes()).hexdigest())
    try:
        ref = b"".join(AOE.run(str(mp), [x], True))
        (o / f"{name}.ref_ofm.bin").write_bytes(ref)
        res["reference_len"] = len(ref)
    except Exception as e:                     # recorded, not hidden
        res["reference_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return res
    rows = inventory_rows(mp)
    res["rows"] = rows
    res["npu_rows"] = [r for r in rows if r.get("cpu") == "0" and r.get("npu_op") in ("Conv2D", "DepthwiseConv2D", "FullyConnected")]
    res["cpu_rows"] = [r["tflite_op"] for r in rows if r.get("cpu") == "1"]
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile", str(PROFILE),
                        "--format", "drwl", "--out", str(o / f"{name}.drwl"), "--ifm", str(o / f"{name}.ifm.bin"),
                        "--golden", str(o / f"{name}.ref_ofm.bin")], capture_output=True, text=True)
    res["pack_rc"] = p.returncode
    res["pack_log_tail"] = (p.stdout + p.stderr).strip().splitlines()[-3:]
    if p.returncode == 0:
        meta = json.loads((o / f"{name}.drwl.json").read_text())
        h = drwl.parse((o / f"{name}.drwl").read_bytes())
        res.update(drwl_sha256=meta["blob_sha256"], vela_sha256=meta["vela_sha256"], arena_size=meta["arena_size"],
                   fast_size=meta["fast_size"], model_len=h["model_len"], cms_len=meta["cms_len"], limits=LIMITS)
    return res


def main(out: str, specs_path: str) -> None:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    specs = json.loads(pathlib.Path(specs_path).read_text())
    facts = []
    for sp in specs:
        try:
            facts.append(one(sp, o))
        except Exception as e:
            facts.append(dict(sp, error=f"{type(e).__name__}: {str(e)[:300]}"))
        print(sp["name"], "ok" if "error" not in facts[-1] else facts[-1]["error"], flush=True)
    (o / "compile_facts.json").write_text(json.dumps(facts, indent=1, sort_keys=True, default=str))
    print(o / "compile_facts.json", hashlib.sha256((o / "compile_facts.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main(*sys.argv[1:3])
