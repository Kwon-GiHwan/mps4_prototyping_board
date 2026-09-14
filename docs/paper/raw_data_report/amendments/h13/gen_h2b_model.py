"""H2-B representative-layer model (plan section 5). Run locally in the TensorFlow venv:

    tfenv/bin/python gen_h2b_model.py <wav2letter_pruned_int8.tflite> <out_dir>

Wav2Letter's two largest Conv2D layers (16 MB and 4 MB of weights) cannot be placed in SRAM on Corstone-320,
so the representative layer is the 7-tap 250->250 Conv2D of the middle stack (op 15, 437,500 weight bytes),
which fits the 2 MB arena under Sram_Only. Weights and bias are dequantised from the original per-channel
INT8 tensors and re-quantised by the converter; the byte-level difference to the original is recorded in the
manifest (the original encoded weights are not reproduced exactly -- schedule/command-stream differences are
therefore compared from the Vela dumps, per the plan).
"""
import hashlib, json, os, sys

import numpy as np
import tensorflow as tf

OP_INDEX = 15
FVP = "/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320"
SYSCFG = {256: "Ethos_U85_SYS_DRAM_Low", 512: "Ethos_U85_SYS_DRAM_Mid_512"}


def extract(path):
    it = tf.lite.Interpreter(model_path=path); it.allocate_tensors()
    td = {t["index"]: t for t in it.get_tensor_details()}
    op = [o for o in it._get_ops_details() if o["index"] == OP_INDEX][0]
    assert op["op_name"] == "CONV_2D", op
    wi, bi, ii, oi = op["inputs"][1], op["inputs"][2], op["inputs"][0], op["outputs"][0]
    w = it.get_tensor(wi).astype(np.int32); b = it.get_tensor(bi).astype(np.int64)
    wq, bq = td[wi]["quantization_parameters"], td[bi]["quantization_parameters"]
    ws, wz = wq["scales"], wq["zero_points"]
    wf = (w - wz[:, None, None, None]) * ws[:, None, None, None]          # [O, kh, kw, I] -> float
    bf = b * bq["scales"]
    return {"w": np.transpose(wf, (1, 2, 3, 0)).astype(np.float32), "b": bf.astype(np.float32),
            "in_shape": td[ii]["shape"].tolist(), "out_shape": td[oi]["shape"].tolist(),
            "in_q": td[ii]["quantization"], "out_q": td[oi]["quantization"],
            "w_int8_sha256": hashlib.sha256(it.get_tensor(wi).tobytes()).hexdigest(), "w_shape": w.shape}


def build(layer):
    h, wd, c = layer["in_shape"][1:]
    kh, kw = layer["w"].shape[:2]; o = layer["w"].shape[3]
    inp = tf.keras.Input(shape=(h, wd, c), batch_size=1, name="ifm")
    conv = tf.keras.layers.Conv2D(o, (kh, kw), padding="same", name="op")
    m = tf.keras.Model(inp, conv(inp)); m.get_layer("op").set_weights([layer["w"], layer["b"]]); return m


def to_int8(model, shape, in_q):
    rng = np.random.default_rng(7)
    scale, zp = in_q
    def rep():
        for _ in range(8):   # spans the original input's int8 range
            yield [((rng.integers(-128, 128, (1,) + tuple(shape[1:])) - zp) * scale).astype(np.float32)]
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]; conv.representative_dataset = rep
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8; conv.inference_output_type = tf.int8
    return conv.convert()


def main(src, out):
    os.makedirs(os.path.join(out, "models"), exist_ok=True)
    L = extract(src); name = "h2b_w2l_conv7_250"
    blob = to_int8(build(L), L["in_shape"], L["in_q"])
    open(os.path.join(out, "models", name + ".tflite"), "wb").write(blob)
    it = tf.lite.Interpreter(model_content=blob); it.allocate_tensors()
    wq = [t for t in it.get_tensor_details() if len(t["shape"]) == 4 and t["shape"][0] == L["w"].shape[3] and t["dtype"] == np.int8]
    man = {"model": name, "source_op_index": OP_INDEX, "in_shape": L["in_shape"], "out_shape": L["out_shape"],
           "kernel": [int(x) for x in L["w"].shape], "orig_w_int8_sha256": L["w_int8_sha256"],
           "orig_in_q": [float(L["in_q"][0]), int(L["in_q"][1])], "orig_out_q": [float(L["out_q"][0]), int(L["out_q"][1])],
           "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
           "requant_w_int8_sha256": hashlib.sha256(it.get_tensor(wq[0]["index"]).tobytes()).hexdigest() if wq else None,
           "requant_w_max_abs_diff": int(np.max(np.abs(it.get_tensor(wq[0]["index"]).astype(np.int32) - np.transpose(
               np.round(L["w"] / np.array([s for s in wq[0]["quantization_parameters"]["scales"]])[None, None, None, :]), (3, 0, 1, 2)).astype(np.int32)))) if wq else None}
    cells = []
    for mac in (512, 256):
        for mode, tag in (("Dedicated_Sram", "Dedicated"), ("Sram_Only", "SramOnly")):
            cells.append({"cell_id": "%s__SSE-320__ethos-u85-%d__%s" % (name, mac, tag), "model": name,
                          "model_path": "/tmp/h13/models/%s.tflite" % name, "platform": "SSE-320", "npu": "ethos-u85",
                          "mac_config": mac, "accelerator_config": "ethos-u85-%d" % mac, "system_config": SYSCFG[mac],
                          "memory_mode": mode, "target_platform": "mps4", "target_subsystem": "sse-320", "fvp": FVP,
                          "verbose": True, "experiment": "H2B", "arms": [["base", {}]]})
    json.dump(man, open(os.path.join(out, "h2b_manifest.json"), "w"), indent=1)
    json.dump(cells, open(os.path.join(out, "h2b_cells.json"), "w"), indent=1)
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
