#!/usr/bin/env python3
"""Study: the 1x1 Conv example from the Ethos-U85 architecture notes, compiled by Vela into a C header.

Runs in the benchmark-runner container (vela, tflite, flatbuffers, numpy, tflite_runtime).

  python3 make_conv1x1_study.py <out_dir>
    -> <out_dir>/conv1x1.tflite, vela/ (Vela output + verbose log), conv1x1_data.h

The example (notes section 4): IFM 1x4x4x4, 1x1 conv, stride 1, no padding, OFM 1x4x4x2, bias 0, zero point 0.
Position (0,0) = [2,3,1,4], (0,1) = [5,0,2,1]; filters [1,2,3,1] and [-1,1,2,0] -> accumulators [15,3] at (0,0).
Every scale is 1.0, so the rescale in AO is the identity and the OFM equals the accumulators byte for byte.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import flatbuffers
import numpy as np
from tflite.ActivationFunctionType import ActivationFunctionType
from tflite.BuiltinOperator import BuiltinOperator
from tflite.BuiltinOptions import BuiltinOptions
from tflite.Padding import Padding
from tflite.TensorType import TensorType

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_op_model import (Conv2DOptions, Model, Operator, OperatorCode, SubGraph,  # noqa: E402
                           _buffer, _quant, _tensor, _vec)
from pack_vela_workload import VELA_OPTIONS, inspect_vela  # noqa: E402

WEIGHTS = np.array([[1, 2, 3, 1], [-1, 1, 2, 0]], dtype=np.int8).reshape(2, 1, 1, 4)  # [Cout, kH, kW, Cin]
VERBOSE = ["--verbose-high-level-command-stream", "--verbose-register-command-stream",
           "--verbose-allocation", "--verbose-weights", "--verbose-performance"]


def ifm() -> np.ndarray:
    """The two positions from the notes, the other 14 small values so every accumulator fits int8."""
    x = np.array([((h * 4 + w) * 3 + c) % 7 - 3 for h in range(4) for w in range(4) for c in range(4)],
                 dtype=np.int8).reshape(1, 4, 4, 4)
    x[0, 0, 0] = [2, 3, 1, 4]
    x[0, 0, 1] = [5, 0, 2, 1]
    return x


def accumulators(x: np.ndarray) -> np.ndarray:
    return np.einsum("nhwc,oc->nhwo", x.astype(np.int32), WEIGHTS.reshape(2, 4).astype(np.int32))


def build_model() -> bytes:
    b = flatbuffers.Builder(1 << 12)
    bufs = [_buffer(b, None), _buffer(b, None), _buffer(b, WEIGHTS.tobytes()),
            _buffer(b, np.zeros(2, dtype="<i4").tobytes()), _buffer(b, None)]
    tensors = [
        _tensor(b, "ifm", (1, 4, 4, 4), TensorType.INT8, 1, _quant(b, [1.0], [0])),
        _tensor(b, "weights", WEIGHTS.shape, TensorType.INT8, 2, _quant(b, [1.0, 1.0], [0, 0], 0)),
        _tensor(b, "bias", (2,), TensorType.INT32, 3, _quant(b, [1.0, 1.0], [0, 0])),
        _tensor(b, "ofm", (1, 4, 4, 2), TensorType.INT8, 4, _quant(b, [1.0], [0])),
    ]
    Conv2DOptions.Conv2DOptionsStart(b)
    Conv2DOptions.Conv2DOptionsAddPadding(b, Padding.VALID)
    Conv2DOptions.Conv2DOptionsAddStrideH(b, 1); Conv2DOptions.Conv2DOptionsAddStrideW(b, 1)
    Conv2DOptions.Conv2DOptionsAddDilationHFactor(b, 1); Conv2DOptions.Conv2DOptionsAddDilationWFactor(b, 1)
    Conv2DOptions.Conv2DOptionsAddFusedActivationFunction(b, ActivationFunctionType.NONE)
    opts = Conv2DOptions.Conv2DOptionsEnd(b)
    ins = _vec(b, Operator.OperatorStartInputsVector, [0, 1, 2], b.PrependInt32)
    outs = _vec(b, Operator.OperatorStartOutputsVector, [3], b.PrependInt32)
    Operator.OperatorStart(b)
    Operator.OperatorAddOpcodeIndex(b, 0); Operator.OperatorAddInputs(b, ins); Operator.OperatorAddOutputs(b, outs)
    Operator.OperatorAddBuiltinOptionsType(b, BuiltinOptions.Conv2DOptions); Operator.OperatorAddBuiltinOptions(b, opts)
    operator = Operator.OperatorEnd(b)

    tvec = _vec(b, SubGraph.SubGraphStartTensorsVector, tensors, b.PrependUOffsetTRelative)
    sin = _vec(b, SubGraph.SubGraphStartInputsVector, [0], b.PrependInt32)
    sout = _vec(b, SubGraph.SubGraphStartOutputsVector, [3], b.PrependInt32)
    ovec = _vec(b, SubGraph.SubGraphStartOperatorsVector, [operator], b.PrependUOffsetTRelative)
    nm = b.CreateString("conv1x1")
    SubGraph.SubGraphStart(b)
    SubGraph.SubGraphAddTensors(b, tvec); SubGraph.SubGraphAddInputs(b, sin); SubGraph.SubGraphAddOutputs(b, sout)
    SubGraph.SubGraphAddOperators(b, ovec); SubGraph.SubGraphAddName(b, nm)
    sg = SubGraph.SubGraphEnd(b)

    OperatorCode.OperatorCodeStart(b)
    OperatorCode.OperatorCodeAddBuiltinCode(b, BuiltinOperator.CONV_2D)
    OperatorCode.OperatorCodeAddDeprecatedBuiltinCode(b, BuiltinOperator.CONV_2D)
    OperatorCode.OperatorCodeAddVersion(b, 1)
    oc = OperatorCode.OperatorCodeEnd(b)

    codes = _vec(b, Model.ModelStartOperatorCodesVector, [oc], b.PrependUOffsetTRelative)
    sgs = _vec(b, Model.ModelStartSubgraphsVector, [sg], b.PrependUOffsetTRelative)
    bvec = _vec(b, Model.ModelStartBuffersVector, bufs, b.PrependUOffsetTRelative)
    desc = b.CreateString("study 1x1 conv example")
    Model.ModelStart(b)
    Model.ModelAddVersion(b, 3); Model.ModelAddOperatorCodes(b, codes); Model.ModelAddSubgraphs(b, sgs)
    Model.ModelAddDescription(b, desc); Model.ModelAddBuffers(b, bvec)
    b.Finish(Model.ModelEnd(b), file_identifier=b"TFL3")
    return bytes(b.Output())


def tflite_reference(model: pathlib.Path, x: np.ndarray) -> np.ndarray:
    from tflite_runtime.interpreter import Interpreter
    it = Interpreter(model_path=str(model)); it.allocate_tensors()
    it.set_tensor(it.get_input_details()[0]["index"], x); it.invoke()
    return it.get_tensor(it.get_output_details()[0]["index"])


def c_bytes(name: str, data: bytes, section: str) -> str:
    rows = [", ".join(f"0x{v:02x}" for v in data[i:i + 16]) for i in range(0, len(data), 16)]
    body = ",\n    ".join(rows) if rows else "0"
    return (f'__attribute__((section("{section}"), aligned(16)))\n'
            f"static const uint8_t {name}[{max(len(data), 1)}] = {{\n    {body}\n}};\n")


def header(info: dict, x: np.ndarray, ofm: np.ndarray, acc: np.ndarray) -> str:
    cms = info["cms"]
    words = np.frombuffer(cms, dtype="<u4")
    cms_rows = [", ".join(f"0x{w:08x}" for w in words[i:i + 6]) for i in range(0, len(words), 6)]
    return "\n".join([
        "/* Generated by host/container/make_conv1x1_study.py -- do not edit. */",
        "#ifndef CONV1X1_DATA_H", "#define CONV1X1_DATA_H", "#include <stdint.h>", "",
        f"#define CONV1X1_CMS_BYTES   {len(cms)}U      /* command stream -> QBASE/QSIZE (CC)        */",
        f"#define CONV1X1_CONST_BYTES {len(info['const'])}U      /* weights+bias/scale stream -> BASEP0 (WD, AO) */",
        f"#define CONV1X1_ARENA_BYTES {info['arena_size']}U      /* scratch arena -> BASEP1 (IFM and OFM live here) */",
        f"#define CONV1X1_FAST_BYTES  {info['fast_size']}U      /* fast scratch -> BASEP2                  */",
        f"#define CONV1X1_IFM_OFFSET  {info['ifm_off']}U      /* IFM offset inside the arena            */",
        f"#define CONV1X1_IFM_BYTES   {info['ifm_len']}U",
        f"#define CONV1X1_OFM_OFFSET  {info['ofm_off']}U      /* OFM offset inside the arena            */",
        f"#define CONV1X1_OFM_BYTES   {info['ofm_len']}U", "",
        '__attribute__((section("sec_command_stream"), aligned(16)))',
        f"static const uint32_t conv1x1_cms[{len(words)}] = {{\n    " + ",\n    ".join(cms_rows) + "\n};",
        c_bytes("conv1x1_const", info["const"], "sec_weight_data"),
        "/* IFM, NHWC: 16 positions x 4 input channels */",
        c_bytes("conv1x1_ifm", x.tobytes(), "sec_input_data"),
        "/* expected OFM (TFLite reference == numpy accumulators, every scale 1.0), NHWC: 16 positions x 2 */",
        "static const int8_t conv1x1_expected_ofm[32] = {\n    "
        + ", ".join(str(int(v)) for v in ofm.reshape(-1)) + "\n};",
        f"/* numpy accumulators before AO, same layout; max |acc| = {int(np.abs(acc).max())} */",
        "static const int32_t conv1x1_expected_acc[32] = {\n    "
        + ", ".join(str(int(v)) for v in acc.reshape(-1)) + "\n};", "",
        "#endif", ""])


def main() -> int:
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    model = out / "conv1x1.tflite"; model.write_bytes(build_model())
    x = ifm(); acc = accumulators(x)
    if np.abs(acc).max() > 127:
        raise SystemExit(f"accumulator {np.abs(acc).max()} does not fit int8 with scale 1.0")
    ofm = tflite_reference(model, x)
    if not np.array_equal(ofm.astype(np.int32), acc):
        raise SystemExit("TFLite OFM != numpy accumulators: the identity-rescale assumption is wrong")

    vdir = out / "vela"
    log = subprocess.run(["vela", str(model), *VELA_OPTIONS, *VERBOSE, "--output-dir", str(vdir)],
                         check=True, capture_output=True, text=True)
    (vdir / "vela_verbose.txt").write_text(log.stdout + log.stderr)
    info = inspect_vela(str(vdir / "conv1x1_vela.tflite"))
    if info["ifm_len"] != x.size or info["ofm_len"] != ofm.size:
        raise SystemExit(f"Vela IFM/OFM sizes {info['ifm_len']}/{info['ofm_len']} != {x.size}/{ofm.size}")

    (out / "conv1x1_data.h").write_text(header(info, x, ofm, acc))
    print(f"(0,0) acc = {acc[0, 0, 0].tolist()}, (0,1) acc = {acc[0, 0, 1].tolist()}")
    print(f"cms {len(info['cms'])} B, const {len(info['const'])} B, arena {info['arena_size']} B, "
          f"fast {info['fast_size']} B, ifm@{info['ifm_off']}, ofm@{info['ofm_off']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
