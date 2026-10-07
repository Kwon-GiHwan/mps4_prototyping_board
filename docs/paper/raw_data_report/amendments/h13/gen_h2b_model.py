"""H2-B representative-layer model (plan section 5, manager directive 2026-09-14: preserve weights, bias,
quantisation parameters and stride/padding exactly; verify the input/output correspondence with the original).

    tfenv/bin/python gen_h2b_model.py <wav2letter_pruned_int8.tflite> <out_dir>

The layer is op 15 of Wav2Letter (7-tap 250->250 Conv2D, 437,500 weight bytes). It is cut out of the original
flatbuffer verbatim: operator options, the four tensors (IFM, weights, bias, OFM) with their quantisation
records and the weight/bias buffers are copied unchanged, so nothing is re-quantised. The extracted model is
then checked against the original by running the full original model, capturing tensor 38 (the op's IFM)
and tensor 39 (its OFM), feeding tensor 38 to the extracted model and requiring a byte-identical OFM.
"""
import copy, hashlib, json, os, sys

import numpy as np
import tensorflow as tf
from tensorflow.lite.tools import flatbuffer_utils as fu

OP_INDEX = 15
FVP = "/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320"
SYSCFG = {256: "Ethos_U85_SYS_DRAM_Low", 512: "Ethos_U85_SYS_DRAM_Mid_512"}
MODES = (("Shared_Sram", "Shared"), ("Sram_Only", "SramOnly"), ("Dedicated_Sram", "Dedicated"))


def slice_op(src):
    m = fu.read_model(src); sg = m.subgraphs[0]; op = sg.operators[OP_INDEX]
    new = copy.deepcopy(m)
    new.operatorCodes = [copy.deepcopy(m.operatorCodes[op.opcodeIndex])]
    tids = list(op.inputs) + list(op.outputs)
    new.buffers = [copy.deepcopy(m.buffers[0])]
    tensors = []
    for k, ti in enumerate(tids):
        t = copy.deepcopy(sg.tensors[ti])
        if k in (1, 2):                       # weights, bias: keep the constant buffers verbatim
            new.buffers.append(copy.deepcopy(m.buffers[t.buffer])); t.buffer = len(new.buffers) - 1
        else:                                 # IFM / OFM: activation tensors, empty buffer
            t.buffer = 0
        tensors.append(t)
    nsg = copy.deepcopy(sg); nsg.tensors = tensors; nsg.inputs = [0]; nsg.outputs = [3]
    nop = copy.deepcopy(op); nop.opcodeIndex = 0; nop.inputs = [0, 1, 2]; nop.outputs = [3]
    nsg.operators = [nop]; nsg.name = b"h2b_w2l_conv7_250"
    new.subgraphs = [nsg]
    if new.signatureDefs:
        new.signatureDefs = []
    return m, new, tids


def correspondence(src, blob, tids):
    """Run the original end-to-end, capture the op's IFM/OFM, replay the IFM through the extracted model."""
    full = tf.lite.Interpreter(model_path=src, experimental_preserve_all_tensors=True); full.allocate_tensors()
    rng = np.random.default_rng(3)
    inp = full.get_input_details()[0]
    full.set_tensor(inp["index"], rng.integers(-128, 128, inp["shape"], dtype=np.int8)); full.invoke()
    ifm, ofm = full.get_tensor(tids[0]).copy(), full.get_tensor(tids[3]).copy()
    ext = tf.lite.Interpreter(model_content=blob); ext.allocate_tensors()
    ext.set_tensor(ext.get_input_details()[0]["index"], ifm); ext.invoke()
    got = ext.get_tensor(ext.get_output_details()[0]["index"])
    return bool(np.array_equal(got, ofm)), int(np.max(np.abs(got.astype(np.int32) - ofm.astype(np.int32))))


def main(src, out):
    os.makedirs(os.path.join(out, "models"), exist_ok=True)
    name = "h2b_w2l_conv7_250"
    m, new, tids = slice_op(src)
    path = os.path.join(out, "models", name + ".tflite"); fu.write_model(new, path)
    blob = open(path, "rb").read()
    same, maxdiff = correspondence(src, blob, tids)
    sg = m.subgraphs[0]; op = sg.operators[OP_INDEX]; o = op.builtinOptions
    w, b = sg.tensors[tids[1]], sg.tensors[tids[2]]
    man = {"model": name, "source_op_index": OP_INDEX, "source_tensors": [int(x) for x in tids],
           "opcode": int(m.operatorCodes[op.opcodeIndex].builtinCode), "options": {k: int(getattr(o, k)) for k in
           ("padding", "strideH", "strideW", "dilationHFactor", "dilationWFactor", "fusedActivationFunction")},
           "ifm_shape": [int(x) for x in sg.tensors[tids[0]].shape], "ofm_shape": [int(x) for x in sg.tensors[tids[3]].shape],
           "weight_shape": [int(x) for x in w.shape], "weight_bytes": len(m.buffers[w.buffer].data),
           "weight_sha256": hashlib.sha256(bytes(m.buffers[w.buffer].data)).hexdigest(),
           "bias_sha256": hashlib.sha256(bytes(m.buffers[b.buffer].data)).hexdigest(),
           "ifm_q": [float(sg.tensors[tids[0]].quantization.scale[0]), int(sg.tensors[tids[0]].quantization.zeroPoint[0])],
           "ofm_q": [float(sg.tensors[tids[3]].quantization.scale[0]), int(sg.tensors[tids[3]].quantization.zeroPoint[0])],
           "weight_q_channels": len(w.quantization.scale), "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
           "ofm_identical_to_original": same, "ofm_max_abs_diff": maxdiff}
    cells = []
    for mac in (512, 256):
        for mode, tag in MODES:
            cells.append({"cell_id": "%s__SSE-320__ethos-u85-%d__%s" % (name, mac, tag), "model": name,
                          "model_path": "/tmp/h13/models/%s.tflite" % name, "platform": "SSE-320", "npu": "ethos-u85",
                          "mac_config": mac, "accelerator_config": "ethos-u85-%d" % mac, "system_config": SYSCFG[mac],
                          "memory_mode": mode, "target_platform": "mps4", "target_subsystem": "sse-320", "fvp": FVP,
                          "verbose": True, "experiment": "H2B", "arms": [["base", {}]]})
    json.dump(man, open(os.path.join(out, "h2b_manifest.json"), "w"), indent=1)
    json.dump(cells, open(os.path.join(out, "h2b_cells.json"), "w"), indent=1)
    print(json.dumps(man, indent=1))
    if not same:
        sys.exit("OFM mismatch -- extraction is not faithful")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
