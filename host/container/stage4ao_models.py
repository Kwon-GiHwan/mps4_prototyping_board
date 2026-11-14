#!/usr/bin/env python3
"""Stage 4AO (docs/plan/stage4ao_characterization_plan.md): workloads for the AO (activation output) study. Runs in the
benchmark-runner container. Nothing here changes a Stage 4/4C/4K build: make_op_model and stage4c_models are imported,
not edited, and the base tensors are re-derived from them.

  python3 stage4ao_models.py <out dir>          Phase B sweep + Phase C activations (compile-checked and packed,
                                                stage4_compile.check) and Phase D static probes (<name>.static.json)

Phase B (board candidates): 1x1 Conv, Cin 16, Cout 96, stride 1, SAME, RELU6, INT8, IFM H x 24 for H = 12/24/36/48.
  Weights, bias and the OFM scale are s4_conv_base's. IFM rows: the base IFM (seed 1, 24 rows); H < 24 keeps the first
  H rows, H > 24 appends rows drawn once from AO_SEED (made at H = 72, then cut), so every config shares its rows with
  every larger one.
Phase C (board candidates only if the selection rule in the contract draft passes): the 24 x 24 config with the fused
  activation NONE / RELU (RELU6 = the Phase B 24 x 24 config). Same tensors, same OFM scale.
Phase D (static only, never measured under this plan): LUT activations after the Conv (TANH, LOGISTIC), INT16 (16x8)
  Conv, INT8 ADD / MUL / ABS / LEAKY_RELU at the same OFM shape (1, 24, 24, 96), and two chains (Conv -> ADD,
  ADD -> MUL) to see whether Vela uses the chaining buffer.
"""
from __future__ import annotations

import glob
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
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib")); sys.path.insert(0, str(HERE.parents[0] / "analysis"))
import make_op_model as M  # noqa: E402
from stage4c_models import fit  # noqa: E402
from tflite.ActivationFunctionType import ActivationFunctionType as AF  # noqa: E402
from tflite.BuiltinOperator import BuiltinOperator as OP  # noqa: E402
from tflite.BuiltinOptions import BuiltinOptions as BO  # noqa: E402
from tflite.Padding import Padding  # noqa: E402
from tflite.TensorType import TensorType as TT  # noqa: E402

(AddOptions, MulOptions, LeakyReluOptions, Conv2DOptions) = (importlib.import_module("tflite." + n) for n in (
    "AddOptions", "MulOptions", "LeakyReluOptions", "Conv2DOptions"))

AO_SEED = 20261115
H_MAX, W, CIN, COUT = 72, 24, 16, 96
SWEEP = {f"s4ao_conv1x1_h{h}": h for h in (12, 24, 36, 48)}
# owner-review revision set (NOT a measurement target until approved): the H that keep the 24 x 24 block (block_scan)
REVISION = {f"s4ao_conv1x1_h{h}": h for h in (42, 54, 72)}
ACTS = {"s4ao_act_none": "NONE", "s4ao_act_relu": "RELU"}     # RELU6 = s4ao_conv1x1_h24
ACT_REF = "s4ao_conv1x1_h24"
AFS = {"NONE": AF.NONE, "RELU": AF.RELU, "RELU6": AF.RELU6}


def base_tensors(h: int):
    """IFM (1, h, 24, 16), weights, bias, OFM scale of the Phase B rule."""
    x, wt, bias, s_out, _ = M.arrays("s4_conv_base")
    x = np.take(fit(x, H_MAX, 1, np.random.default_rng(AO_SEED), -128, 128), range(h), axis=1)
    return x, wt, bias, s_out


def conv_spec(h: int, act: str) -> dict:
    return dict(kind="conv", ifm=(1, h, W, CIN), cout=COUT, k=1, padding="SAME", act=act)


def derive_conv(name: str) -> tuple[bytes, dict, bytes]:
    h, act = ({**SWEEP, **REVISION}[name], "RELU6") if name in {**SWEEP, **REVISION} else (24, ACTS[name])
    x, wt, bias, s_out = base_tensors(h)
    spec = conv_spec(h, act)
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    if act == "RELU" and "RELU" not in M.ACT:         # make_op_model knows NONE / RELU6; RELU added for this run only
        M.ACT["RELU"] = AF.RELU
    model, meta = M.serialize(name, spec, wt, bias, s_out, acc_max)
    meta.update(base="s4_conv_base", ao_seed=AO_SEED, ofm_scale_from="s4_conv_base", ifm_rows="base 24 rows, cut or "
                "extended from AO_SEED", acc_abs_max_note="of this config; the OFM scale is the base's")
    return model, meta, x.tobytes()


# ---- Phase D: a small multi-operator flatbuffer writer (static probes only) -------------------------------------------
def _vec(b, start, items, put):
    start(b, len(items))
    for v in reversed(items):
        put(v)
    return b.EndVector()


def _opts(b, kind: str, arg):
    if kind == "conv":
        Conv2DOptions.Conv2DOptionsStart(b)
        Conv2DOptions.Conv2DOptionsAddPadding(b, Padding.SAME)
        Conv2DOptions.Conv2DOptionsAddStrideH(b, 1); Conv2DOptions.Conv2DOptionsAddStrideW(b, 1)
        Conv2DOptions.Conv2DOptionsAddDilationHFactor(b, 1); Conv2DOptions.Conv2DOptionsAddDilationWFactor(b, 1)
        Conv2DOptions.Conv2DOptionsAddFusedActivationFunction(b, AFS[arg])
        return BO.Conv2DOptions, Conv2DOptions.Conv2DOptionsEnd(b)
    if kind == "add":
        AddOptions.AddOptionsStart(b); AddOptions.AddOptionsAddFusedActivationFunction(b, AF.NONE)
        return BO.AddOptions, AddOptions.AddOptionsEnd(b)
    if kind == "mul":
        MulOptions.MulOptionsStart(b); MulOptions.MulOptionsAddFusedActivationFunction(b, AF.NONE)
        return BO.MulOptions, MulOptions.MulOptionsEnd(b)
    if kind == "leaky":
        LeakyReluOptions.LeakyReluOptionsStart(b); LeakyReluOptions.LeakyReluOptionsAddAlpha(b, arg)
        return BO.LeakyReluOptions, LeakyReluOptions.LeakyReluOptionsEnd(b)
    return None, None


CODES = dict(conv=(OP.CONV_2D, 1), conv16=(OP.CONV_2D, 4), add=(OP.ADD, 2), mul=(OP.MUL, 2), tanh=(OP.TANH, 2),
             logistic=(OP.LOGISTIC, 2), abs=(OP.ABS, 2), leaky=(OP.LEAKY_RELU, 2))


def graph(name: str, tensors: list[dict], ops: list[dict]) -> bytes:
    """tensors: dict(name, shape, type, data (bytes|None), scale [..], zp [..], qdim); ops: dict(kind, arg, ins, outs).
    Graph inputs = tensors without data that no op produces; outputs = the last op's outputs."""
    b = flatbuffers.Builder(1 << 20)
    bufs = [M._buffer(b, None)] + [M._buffer(b, t.get("data")) for t in tensors]
    tens = []
    for i, t in enumerate(tensors):
        q = M._quant(b, t["scale"], t["zp"], t.get("qdim", 0))
        tens.append(M._tensor(b, t["name"], t["shape"], t["type"], i + 1, q))
    kinds = sorted({o["kind"] for o in ops}, key=list(CODES).index)
    operators = []
    for o in ops:
        otype, opts = _opts(b, o["kind"], o.get("arg"))
        ins = _vec(b, M.Operator.OperatorStartInputsVector, o["ins"], b.PrependInt32)
        outs = _vec(b, M.Operator.OperatorStartOutputsVector, o["outs"], b.PrependInt32)
        M.Operator.OperatorStart(b)
        M.Operator.OperatorAddOpcodeIndex(b, kinds.index(o["kind"]))
        M.Operator.OperatorAddInputs(b, ins); M.Operator.OperatorAddOutputs(b, outs)
        if otype is not None:
            M.Operator.OperatorAddBuiltinOptionsType(b, otype); M.Operator.OperatorAddBuiltinOptions(b, opts)
        operators.append(M.Operator.OperatorEnd(b))
    produced = {i for o in ops for i in o["outs"]}
    g_in = [i for i, t in enumerate(tensors) if t.get("data") is None and i not in produced]
    g_out = ops[-1]["outs"]
    tvec = _vec(b, M.SubGraph.SubGraphStartTensorsVector, tens, b.PrependUOffsetTRelative)
    sin = _vec(b, M.SubGraph.SubGraphStartInputsVector, g_in, b.PrependInt32)
    sout = _vec(b, M.SubGraph.SubGraphStartOutputsVector, g_out, b.PrependInt32)
    ovec = _vec(b, M.SubGraph.SubGraphStartOperatorsVector, operators, b.PrependUOffsetTRelative)
    nm = b.CreateString(name)
    M.SubGraph.SubGraphStart(b)
    M.SubGraph.SubGraphAddTensors(b, tvec); M.SubGraph.SubGraphAddInputs(b, sin); M.SubGraph.SubGraphAddOutputs(b, sout)
    M.SubGraph.SubGraphAddOperators(b, ovec); M.SubGraph.SubGraphAddName(b, nm)
    sg = M.SubGraph.SubGraphEnd(b)
    codes = []
    for k in kinds:
        code, ver = CODES[k]
        M.OperatorCode.OperatorCodeStart(b)
        M.OperatorCode.OperatorCodeAddBuiltinCode(b, code)
        M.OperatorCode.OperatorCodeAddDeprecatedBuiltinCode(b, min(code, 127))
        M.OperatorCode.OperatorCodeAddVersion(b, ver)
        codes.append(M.OperatorCode.OperatorCodeEnd(b))
    cvec = _vec(b, M.Model.ModelStartOperatorCodesVector, codes, b.PrependUOffsetTRelative)
    sgs = _vec(b, M.Model.ModelStartSubgraphsVector, [sg], b.PrependUOffsetTRelative)
    bvec = _vec(b, M.Model.ModelStartBuffersVector, bufs, b.PrependUOffsetTRelative)
    desc = b.CreateString("stage4ao static probe " + name)
    M.Model.ModelStart(b)
    M.Model.ModelAddVersion(b, 3); M.Model.ModelAddOperatorCodes(b, cvec); M.Model.ModelAddSubgraphs(b, sgs)
    M.Model.ModelAddDescription(b, desc); M.Model.ModelAddBuffers(b, bvec)
    b.Finish(M.Model.ModelEnd(b), file_identifier=b"TFL3")
    return bytes(b.Output())


def i8(name, shape, scale, zp=0):
    return dict(name=name, shape=shape, type=TT.INT8, scale=[scale], zp=[zp])


def conv_tensors(act_out: dict, wt, bias, s_out):
    return [i8("ifm", (1, 24, W, CIN), M.S_IN),
            dict(name="weights", shape=wt.shape, type=TT.INT8, data=wt.tobytes(), scale=[M.S_W] * COUT, zp=[0] * COUT),
            dict(name="bias", shape=(COUT,), type=TT.INT32, data=bias.astype("<i4").tobytes(),
                 scale=[M.S_IN * M.S_W] * COUT, zp=[0] * COUT),
            i8("conv_out", (1, 24, W, COUT), s_out), act_out]


OFM = (1, 24, W, COUT)


def probes() -> dict:
    """name -> (model bytes, description). Phase D only."""
    _, wt, bias, s_out = base_tensors(24)
    out = {}
    conv = dict(kind="conv", arg="NONE", ins=[0, 1, 2], outs=[3])
    out["s4ao_lut_tanh"] = (graph("s4ao_lut_tanh", conv_tensors(i8("ofm", OFM, 1 / 128), wt, bias, s_out),
                                  [conv, dict(kind="tanh", ins=[3], outs=[4])]), "Conv 1x1 (no fused act) -> TANH")
    out["s4ao_lut_logistic"] = (graph("s4ao_lut_logistic", conv_tensors(i8("ofm", OFM, 1 / 256, -128), wt, bias, s_out),
                                      [conv, dict(kind="logistic", ins=[3], outs=[4])]), "Conv 1x1 -> LOGISTIC")
    t16 = [dict(name="ifm", shape=(1, 24, W, CIN), type=TT.INT16, scale=[M.S_IN / 256], zp=[0]),
           dict(name="weights", shape=wt.shape, type=TT.INT8, data=wt.tobytes(), scale=[M.S_W] * COUT, zp=[0] * COUT),
           dict(name="bias", shape=(COUT,), type=TT.INT64, data=(bias.astype(np.int64) * 256).astype("<i8").tobytes(),
                scale=[M.S_IN / 256 * M.S_W] * COUT, zp=[0] * COUT),
           dict(name="ofm", shape=OFM, type=TT.INT16, scale=[s_out / 256], zp=[0])]
    out["s4ao_conv_int16"] = (graph("s4ao_conv_int16", t16, [dict(kind="conv16", arg="RELU6", ins=[0, 1, 2], outs=[3])]),
                              "Conv 1x1 16x8 (IFM/OFM int16, weights int8, bias int64), RELU6")
    for k, s_o in (("add", 2 / 128), ("mul", 1 / 128)):
        out[f"s4ao_ew_{k}"] = (graph(f"s4ao_ew_{k}", [i8("a", OFM, 1 / 128), i8("b", OFM, 1 / 128), i8("ofm", OFM, s_o)],
                                     [dict(kind=k, ins=[0, 1], outs=[2])]), f"INT8 {k.upper()} (1,24,24,96) x 2")
    out["s4ao_ew_abs"] = (graph("s4ao_ew_abs", [i8("a", OFM, 1 / 128), i8("ofm", OFM, 1 / 128)],
                                [dict(kind="abs", ins=[0], outs=[1])]), "INT8 ABS (1,24,24,96)")
    out["s4ao_ew_leaky"] = (graph("s4ao_ew_leaky", [i8("a", OFM, 1 / 128), i8("ofm", OFM, 1 / 128)],
                                  [dict(kind="leaky", arg=0.125, ins=[0], outs=[1])]), "INT8 LEAKY_RELU alpha 0.125")
    out["s4ao_chain_conv_add"] = (graph("s4ao_chain_conv_add", conv_tensors(i8("res", OFM, 1 / 128), wt, bias, s_out)
                                        + [i8("ofm", OFM, 2 / 128)],
                                        [conv, dict(kind="add", ins=[3, 4], outs=[5])]), "Conv 1x1 -> ADD residual")
    out["s4ao_chain_add_mul"] = (graph("s4ao_chain_add_mul", [i8("a", OFM, 1 / 128), i8("b", OFM, 1 / 128),
                                                              i8("t", OFM, 2 / 128), i8("c", OFM, 1 / 128),
                                                              i8("ofm", OFM, 2 / 128)],
                                       [dict(kind="add", ins=[0, 1], outs=[2]), dict(kind="mul", ins=[2, 3], outs=[4])]),
                                 "ADD -> MUL (three external IFMs)")
    return out


def storage_of(stream: bytes) -> list[dict]:
    """Per kernel instruction: kind and the IFM / IFM2 / OFM storage fields (activation_storage, 2 = CHAINED) and the
    precision words, decoded from the stream (ethosu85_interface.h: storage = bits [31:30] = param bits [15:14])."""
    import cms
    reg0, out = {}, []
    for off, word, ctrl, op in cms.instructions(stream):
        if ctrl == 1:
            continue
        if op in cms.KERNEL_OPS:
            st = lambda r: None if reg0.get(r) is None else reg0[r] >> 14
            out.append(dict(kind=cms.KERNEL_OPS[op], ifm_storage=st(0x105), ifm2_storage=st(389), ofm_storage=st(0x114),
                            ifm_precision=reg0.get(0x105), ofm_precision=reg0.get(0x114), activation=reg0.get(293)))
        else:
            reg0[op] = word >> 16
    return out


def static_probe(name: str, model: bytes, desc: str, o: pathlib.Path) -> dict:
    """Vela placement (CPU fallback = any operator left that is not the Ethos-U custom op), the scheduled operations,
    kernel kinds and storage fields, and whether the DRWL packer accepts it (feasibility for the runner, not a run)."""
    import cms
    from pack_vela_workload import VELA_OPTIONS, inspect_vela
    from stage4_inventory import tables, tflite_ops
    (o / f"{name}.tflite").write_bytes(model)
    res = dict(config=name, description=desc, model_sha256=hashlib.sha256(model).hexdigest())
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["vela", str(o / f"{name}.tflite"), *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"],
                           capture_output=True, text=True)
        res["vela_rc"] = r.returncode
        res["vela_log_tail"] = (r.stdout + r.stderr).strip().splitlines()[-12:]
        if r.returncode == 0:
            t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
            vela_out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
            vops = tflite_ops(vela_out)
            stream = inspect_vela(vela_out)["cms"]
            res.update(vela_ops=[x[1] for x in vops],
                       cpu_fallback=[x[1] for x in vops if not x[1].startswith("CUSTOM:ethos-u")],
                       scheduled=[dict(operator=p["operator"], npu_cycles=p["npu_cycles"], mac_count=p["mac_count"])
                                  for p in t["perf"]],
                       perf_main=[{k: p.get(k) for k in ("id", "mac_cycles", "ao_cycles", "cmd_cycles", "ofm_block_h",
                                                          "ofm_block_w", "ofm_block_c", "traversal")}
                                  for p in t["perf_debug_main"]],
                       kernels=storage_of(stream), kernel_kinds=cms.kernel_types(stream), cms_len=len(stream))
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(o / f"{name}.tflite"),
                        "--profile", str(HERE.parents[1] / "config" / "fi101_s013.json"), "--format", "drwl",
                        "--out", str(o / f"{name}.drwl")], capture_output=True, text=True)
    res["pack_rc"] = p.returncode
    res["pack_log_tail"] = (p.stdout + p.stderr).strip().splitlines()[-6:]
    (o / f"{name}.static.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(out: str) -> None:
    import stage4_compile as SC
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    r = SC.check("s4_conv_base", o)                    # the Stage 4K repro anchor, rebuilt for a byte comparison
    print("s4_conv_base", "GATE_B", r["gate_b"], r["drwl_sha256"][:12], flush=True)
    for name in [*SWEEP, *ACTS, *REVISION]:
        model, meta, ifm = derive_conv(name)
        r = SC.check(name, o, built=(model, meta, ifm), kind="conv")
        print(name, "GATE_B", r["gate_b"], r["checks"], meta["output_shape"], r["ofm_block"], r["ifm_block"],
              r["ofm_ublock"], r["traversal"], r["n_kernels"], r["vela_ao_cycles"], r["vela_npu_cycles"], flush=True)
    for name, (model, desc) in probes().items():
        r = static_probe(name, model, desc, o)
        print(name, "vela_rc", r["vela_rc"], "fallback", r.get("cpu_fallback"), r.get("kernel_kinds"),
              "pack_rc", r["pack_rc"], flush=True)


def scan(out: str) -> None:
    """Compile-only reference for the owner (not a candidate list): Vela's block choice for the Phase B rule at
    H = 6..72 (step 6) with W = 24, and at H = 24 with W = 6..72 (step 6). Vela only; nothing is packed."""
    from pack_vela_workload import VELA_OPTIONS
    from stage4_inventory import tables
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    rows = []
    for h, w in [(h, 24) for h in range(6, 73, 6)] + [(24, w) for w in range(6, 73, 6) if w != 24]:
        _, wt, bias, s_out = base_tensors(24)
        spec = dict(conv_spec(h, "RELU6"), ifm=(1, h, w, CIN))
        model, _ = M.serialize(f"scan_h{h}_w{w}", spec, wt, bias, s_out, 0)
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "m.tflite"; p.write_bytes(model)
            subprocess.run(["vela", str(p), *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"], check=True,
                           capture_output=True)
            t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
        mq = t["perf_debug_main"][0]
        hwc = lambda pre: "x".join(mq.get(f"{pre}_{a}", "") for a in "hwc")
        rows.append(dict(h=h, w=w, n_ofm=h * w * COUT, ofm_block=hwc("ofm_block"), ifm_block=hwc("ifm_block"),
                         ofm_ublock=hwc("ofm_ublock"), traversal=mq.get("traversal"), vela_ao_cycles=mq.get("ao_cycles"),
                         vela_npu_cycles=t["perf"][0]["npu_cycles"]))
        print(rows[-1], flush=True)
    (o / "block_scan.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    {"scan": scan}.get((sys.argv[2:] or [""])[0], main)(sys.argv[1])
