#!/usr/bin/env python3
"""Single-operator INT8 tflite models for Stage 1B, written directly as flatbuffers (no TensorFlow needed).

Runs in the benchmark-runner container (needs `tflite`, `flatbuffers`, `numpy`).

  python3 make_op_model.py <op> <out_dir>        op: one of OPS -> <out_dir>/<op>.tflite and <op>.json

Quantization (fixed, documented in evidence/stage1/contract.md):
- IFM int8, scale 1/128, zero point 0. The packer's seed-1 IFM covers the full int8 range.
- Weights int8 uniform in [-127, 127] from WEIGHT_SEED, symmetric, scale 1/128. Per-channel (all channels equal) for
  CONV_2D (dimension 0) and DEPTHWISE_CONV_2D (dimension 3); per-tensor for FULLY_CONNECTED.
- Bias int32 uniform in [-1024, 1024], scale = IFM scale x weight scale.
- OFM int8, zero point 0, scale = max |accumulator| x IFM scale x weight scale / 127, where the accumulators are
  computed here in numpy for the packer's seed-1 IFM, so the output spans the int8 range without saturating.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import importlib

import flatbuffers
import numpy as np
from tflite.ActivationFunctionType import ActivationFunctionType
from tflite.BuiltinOperator import BuiltinOperator
from tflite.BuiltinOptions import BuiltinOptions
from tflite.Padding import Padding
from tflite.TensorType import TensorType

# the generated flatbuffer modules (the `tflite` package re-exports their classes under the same names)
(Buffer, Conv2DOptions, DepthwiseConv2DOptions, FullyConnectedOptions, Model, Operator, OperatorCode,
 QuantizationParameters, SubGraph, Tensor) = (importlib.import_module("tflite." + n) for n in (
    "Buffer", "Conv2DOptions", "DepthwiseConv2DOptions", "FullyConnectedOptions", "Model", "Operator", "OperatorCode",
    "QuantizationParameters", "SubGraph", "Tensor"))

WEIGHT_SEED = 20261014
IFM_SEED = 1                 # = config/mlek_baseline.json "seed"; the packer draws the IFM the same way
S_IN, S_W = 1.0 / 128, 1.0 / 128
OPS = {
    "conv3x3": dict(kind="conv", ifm=(1, 56, 56, 64), cout=64, k=3),
    "dw3x3": dict(kind="dw", ifm=(1, 56, 56, 128), k=3),
    "pw1x1": dict(kind="conv", ifm=(1, 56, 56, 64), cout=128, k=1),
    "fc1024": dict(kind="fc", ifm=(1, 1024), cout=1024),
}


def geometry(spec: dict) -> dict:
    """Shapes and N_MAC by the Stage 1 formulas (stride 1, SAME padding, so spatial size is kept)."""
    if spec["kind"] == "fc":
        cin, cout = spec["ifm"][1], spec["cout"]
        return dict(ofm=(1, cout), kernel=None, stride=None, padding=None, groups=1, weights=(cout, cin),
                    n_mac=cout * cin)
    n, h, w, cin = spec["ifm"]; k = spec["k"]
    if spec["kind"] == "dw":
        return dict(ofm=(n, h, w, cin), kernel=(k, k), stride=(1, 1), padding="SAME", groups=cin,
                    weights=(1, k, k, cin), n_mac=h * w * cin * k * k)
    cout = spec["cout"]
    return dict(ofm=(n, h, w, cout), kernel=(k, k), stride=(1, 1), padding="SAME", groups=1,
                weights=(cout, k, k, cin), n_mac=h * w * cout * k * k * cin)


def accumulators(spec: dict, x: np.ndarray, wt: np.ndarray, bias: np.ndarray) -> np.ndarray:
    x = x.astype(np.int64); wt = wt.astype(np.int64)
    if spec["kind"] == "fc":
        return x @ wt.T + bias
    k = spec["k"]; p = k // 2
    xp = np.pad(x, ((0, 0), (p, p), (p, p), (0, 0)))
    _, h, w, _ = x.shape
    patches = np.stack([xp[:, i:i + h, j:j + w, :] for i in range(k) for j in range(k)], axis=3)  # n,h,w,k*k,cin
    if spec["kind"] == "dw":
        return np.einsum("nhwpc,pc->nhwc", patches, wt.reshape(k * k, -1)) + bias
    return np.einsum("nhwpc,opc->nhwo", patches, wt.reshape(wt.shape[0], k * k, -1)) + bias


def _vec(b, start, items, put):
    start(b, len(items))
    for v in reversed(items):
        put(v)
    return b.EndVector()


def _quant(b, scales, zps, dim=0):
    sc = _vec(b, QuantizationParameters.QuantizationParametersStartScaleVector, list(scales), b.PrependFloat32)
    zp = _vec(b, QuantizationParameters.QuantizationParametersStartZeroPointVector, list(zps), b.PrependInt64)
    QuantizationParameters.QuantizationParametersStart(b)
    QuantizationParameters.QuantizationParametersAddScale(b, sc)
    QuantizationParameters.QuantizationParametersAddZeroPoint(b, zp)
    QuantizationParameters.QuantizationParametersAddQuantizedDimension(b, dim)
    return QuantizationParameters.QuantizationParametersEnd(b)


def _tensor(b, name, shape, ttype, buf, quant):
    nm = b.CreateString(name)
    sh = _vec(b, Tensor.TensorStartShapeVector, list(shape), b.PrependInt32)
    Tensor.TensorStart(b)
    Tensor.TensorAddShape(b, sh); Tensor.TensorAddType(b, ttype); Tensor.TensorAddBuffer(b, buf)
    Tensor.TensorAddName(b, nm); Tensor.TensorAddQuantization(b, quant)
    return Tensor.TensorEnd(b)


def _buffer(b, data: bytes | None):
    vec = b.CreateByteVector(data) if data else None
    Buffer.BufferStart(b)
    if data:
        Buffer.BufferAddData(b, vec)
    return Buffer.BufferEnd(b)


def build(op: str) -> tuple[bytes, dict]:
    spec = OPS[op]; g = geometry(spec)
    rng = np.random.default_rng(WEIGHT_SEED)
    wt = rng.integers(-127, 128, size=g["weights"], dtype=np.int8)
    cout = g["ofm"][-1]
    bias = rng.integers(-1024, 1025, size=(cout,), dtype=np.int32)
    x = np.random.default_rng(IFM_SEED).integers(-128, 128, size=spec["ifm"], dtype=np.int8)
    acc = accumulators(spec, x, wt, bias)
    s_out = float(np.abs(acc).max()) * S_IN * S_W / 127

    b = flatbuffers.Builder(1 << 20)
    bufs = [_buffer(b, None), _buffer(b, None), _buffer(b, wt.tobytes()), _buffer(b, bias.astype("<i4").tobytes()),
            _buffer(b, None)]
    per_ch = spec["kind"] != "fc"
    wdim = 3 if spec["kind"] == "dw" else 0
    tensors = [
        _tensor(b, "ifm", spec["ifm"], TensorType.INT8, 1, _quant(b, [S_IN], [0])),
        _tensor(b, "weights", g["weights"], TensorType.INT8, 2,
                _quant(b, [S_W] * (cout if per_ch else 1), [0] * (cout if per_ch else 1), wdim)),
        _tensor(b, "bias", (cout,), TensorType.INT32, 3,
                _quant(b, [S_IN * S_W] * (cout if per_ch else 1), [0] * (cout if per_ch else 1))),
        _tensor(b, "ofm", g["ofm"], TensorType.INT8, 4, _quant(b, [s_out], [0])),
    ]
    if spec["kind"] == "conv":
        code, otype = BuiltinOperator.CONV_2D, BuiltinOptions.Conv2DOptions
        Conv2DOptions.Conv2DOptionsStart(b)
        Conv2DOptions.Conv2DOptionsAddPadding(b, Padding.SAME)
        Conv2DOptions.Conv2DOptionsAddStrideH(b, 1); Conv2DOptions.Conv2DOptionsAddStrideW(b, 1)
        Conv2DOptions.Conv2DOptionsAddDilationHFactor(b, 1); Conv2DOptions.Conv2DOptionsAddDilationWFactor(b, 1)
        Conv2DOptions.Conv2DOptionsAddFusedActivationFunction(b, ActivationFunctionType.NONE)
        opts = Conv2DOptions.Conv2DOptionsEnd(b)
    elif spec["kind"] == "dw":
        code, otype = BuiltinOperator.DEPTHWISE_CONV_2D, BuiltinOptions.DepthwiseConv2DOptions
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsStart(b)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddPadding(b, Padding.SAME)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddStrideH(b, 1)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddStrideW(b, 1)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddDepthMultiplier(b, 1)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddDilationHFactor(b, 1)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddDilationWFactor(b, 1)
        DepthwiseConv2DOptions.DepthwiseConv2DOptionsAddFusedActivationFunction(b, ActivationFunctionType.NONE)
        opts = DepthwiseConv2DOptions.DepthwiseConv2DOptionsEnd(b)
    else:
        code, otype = BuiltinOperator.FULLY_CONNECTED, BuiltinOptions.FullyConnectedOptions
        FullyConnectedOptions.FullyConnectedOptionsStart(b)
        FullyConnectedOptions.FullyConnectedOptionsAddFusedActivationFunction(b, ActivationFunctionType.NONE)
        opts = FullyConnectedOptions.FullyConnectedOptionsEnd(b)
    ins = _vec(b, Operator.OperatorStartInputsVector, [0, 1, 2], b.PrependInt32)
    outs = _vec(b, Operator.OperatorStartOutputsVector, [3], b.PrependInt32)
    Operator.OperatorStart(b)
    Operator.OperatorAddOpcodeIndex(b, 0); Operator.OperatorAddInputs(b, ins); Operator.OperatorAddOutputs(b, outs)
    Operator.OperatorAddBuiltinOptionsType(b, otype); Operator.OperatorAddBuiltinOptions(b, opts)
    operator = Operator.OperatorEnd(b)

    tvec = _vec(b, SubGraph.SubGraphStartTensorsVector, tensors, b.PrependUOffsetTRelative)
    sin = _vec(b, SubGraph.SubGraphStartInputsVector, [0], b.PrependInt32)
    sout = _vec(b, SubGraph.SubGraphStartOutputsVector, [3], b.PrependInt32)
    ovec = _vec(b, SubGraph.SubGraphStartOperatorsVector, [operator], b.PrependUOffsetTRelative)
    nm = b.CreateString(op)
    SubGraph.SubGraphStart(b)
    SubGraph.SubGraphAddTensors(b, tvec); SubGraph.SubGraphAddInputs(b, sin); SubGraph.SubGraphAddOutputs(b, sout)
    SubGraph.SubGraphAddOperators(b, ovec); SubGraph.SubGraphAddName(b, nm)
    sg = SubGraph.SubGraphEnd(b)

    OperatorCode.OperatorCodeStart(b)
    OperatorCode.OperatorCodeAddBuiltinCode(b, code); OperatorCode.OperatorCodeAddDeprecatedBuiltinCode(b, code)
    OperatorCode.OperatorCodeAddVersion(b, 1)
    oc = OperatorCode.OperatorCodeEnd(b)

    codes = _vec(b, Model.ModelStartOperatorCodesVector, [oc], b.PrependUOffsetTRelative)
    sgs = _vec(b, Model.ModelStartSubgraphsVector, [sg], b.PrependUOffsetTRelative)
    bvec = _vec(b, Model.ModelStartBuffersVector, bufs, b.PrependUOffsetTRelative)
    desc = b.CreateString("stage1 isolated operator " + op)
    Model.ModelStart(b)
    Model.ModelAddVersion(b, 3); Model.ModelAddOperatorCodes(b, codes); Model.ModelAddSubgraphs(b, sgs)
    Model.ModelAddDescription(b, desc); Model.ModelAddBuffers(b, bvec)
    b.Finish(Model.ModelEnd(b), file_identifier=b"TFL3")
    model = bytes(b.Output())

    meta = dict(op=op, operator_type={"conv": "CONV_2D", "dw": "DEPTHWISE_CONV_2D", "fc": "FULLY_CONNECTED"}[spec["kind"]],
                input_shape=list(spec["ifm"]), output_shape=list(g["ofm"]), kernel_shape=g["kernel"] and list(g["kernel"]),
                weight_shape=list(g["weights"]), stride=g["stride"] and list(g["stride"]), padding=g["padding"],
                groups=g["groups"], n_mac=g["n_mac"], weight_seed=WEIGHT_SEED, ifm_seed=IFM_SEED,
                quant=dict(ifm_scale=S_IN, weight_scale=S_W, ofm_scale=s_out, zero_points=0),
                acc_abs_max=int(np.abs(acc).max()), model_sha256=hashlib.sha256(model).hexdigest())
    return model, meta


def main() -> int:
    op, out = sys.argv[1], pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    model, meta = build(op)
    (out / f"{op}.tflite").write_bytes(model)
    (out / f"{op}.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
