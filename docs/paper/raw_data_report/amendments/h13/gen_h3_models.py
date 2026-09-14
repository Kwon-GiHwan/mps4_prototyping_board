"""H3 synthetic shape models (plan section 7). Run locally in the TensorFlow venv:

    tfenv/bin/python gen_h3_models.py <out_dir>

Produces <out_dir>/models/h3_<op>_<H>x<W>_c128.tflite (full-integer INT8), <out_dir>/manifest.json and
<out_dir>/synthetic_cells.json for h13_sweep.py (S3). Weights are one fixed array per op type, shared by
every shape of that type; the representative dataset is fixed-seed uniform noise, so only H x W changes.
"""
import hashlib, json, os, sys

import numpy as np
import tensorflow as tf

C = 128
SHAPES = {36: [(1, 36), (36, 1), (2, 18), (18, 2), (3, 12), (12, 3), (4, 9), (9, 4), (6, 6)],
          64: [(1, 64), (2, 32), (4, 16), (8, 8)],
          256: [(1, 256), (4, 64), (8, 32), (16, 16)]}
OPS = {"conv1x1": ("conv", 1), "conv3x3": ("conv", 3), "dw3x3": ("dw", 3)}
FVP = "/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320"
SYSCFG = {256: "Ethos_U85_SYS_DRAM_Low", 512: "Ethos_U85_SYS_DRAM_Mid_512"}
RELAXED = {"EXT_RLATENCY": 0, "EXT_WLATENCY": 0, "EXT_BWCAP": 0, "SRAM_RLATENCY": 0, "SRAM_WLATENCY": 0}


def weights_for(op, rng):
    kind, k = OPS[op]
    if kind == "conv":
        return [rng.uniform(-0.5, 0.5, (k, k, C, C)).astype(np.float32), rng.uniform(-0.1, 0.1, (C,)).astype(np.float32)]
    return [rng.uniform(-0.5, 0.5, (k, k, C, 1)).astype(np.float32), rng.uniform(-0.1, 0.1, (C,)).astype(np.float32)]


def build(op, h, w, weights):
    kind, k = OPS[op]
    inp = tf.keras.Input(shape=(h, w, C), batch_size=1, name="ifm")
    layer = (tf.keras.layers.Conv2D(C, k, padding="same", name="op") if kind == "conv"
             else tf.keras.layers.DepthwiseConv2D(k, padding="same", name="op"))
    m = tf.keras.Model(inp, layer(inp)); m.get_layer("op").set_weights(weights); return m


def to_int8(model, h, w, seed):
    rng = np.random.default_rng(seed)
    def rep():
        for _ in range(8):
            yield [rng.uniform(-1.0, 1.0, (1, h, w, C)).astype(np.float32)]
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]; conv.representative_dataset = rep
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8; conv.inference_output_type = tf.int8
    return conv.convert()


def quant_info(blob):
    it = tf.lite.Interpreter(model_content=blob)
    i, o = it.get_input_details()[0], it.get_output_details()[0]
    return {"input_shape": [int(x) for x in i["shape"]], "input_scale": float(i["quantization"][0]), "input_zp": int(i["quantization"][1]),
            "output_shape": [int(x) for x in o["shape"]], "output_scale": float(o["quantization"][0]), "output_zp": int(o["quantization"][1])}


def main(out):
    mdir = os.path.join(out, "models"); os.makedirs(mdir, exist_ok=True)
    rng = np.random.default_rng(20260914)
    wts = {op: weights_for(op, rng) for op in OPS}
    manifest, cells = [], []
    for op in OPS:
        wsha = hashlib.sha256(b"".join(a.tobytes() for a in wts[op])).hexdigest()
        for area, shapes in SHAPES.items():
            for h, w in shapes:
                name = "h3_%s_%dx%d_c%d" % (op, h, w, C)
                blob = to_int8(build(op, h, w, wts[op]), h, w, seed=1000 + h * 1000 + w)
                path = os.path.join(mdir, name + ".tflite"); open(path, "wb").write(blob)
                q = quant_info(blob)
                manifest.append(dict(model=name, op=op, H=h, W=w, C=C, area=area, bytes=len(blob),
                                     sha256=hashlib.sha256(blob).hexdigest(), weights_sha256=wsha, **q))
                for mac in (256, 512):
                    arms = [["base", {}]]
                    if area == 36:
                        arms.append(["relaxed", RELAXED])
                    cells.append(cell(name, mac, SYSCFG[mac], "", arms))
                    if op == "conv1x1" and area == 36 and mac == 256:
                        cells.append(cell(name, mac, SYSCFG[512], "__syscfgMid", [["base", {}]]))
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    json.dump(cells, open(os.path.join(out, "synthetic_cells.json"), "w"), indent=1)
    print("models", len(manifest), "cells", len(cells), "arms", sum(len(c["arms"]) for c in cells))


def cell(name, mac, syscfg, suffix, arms):
    return {"cell_id": "%s__SSE-320__ethos-u85-%d%s" % (name, mac, suffix), "model": name,
            "model_path": "/tmp/h13/models/%s.tflite" % name, "platform": "SSE-320", "npu": "ethos-u85",
            "mac_config": mac, "accelerator_config": "ethos-u85-%d" % mac, "system_config": syscfg,
            "memory_mode": "Dedicated_Sram", "target_platform": "mps4", "target_subsystem": "sse-320",
            "fvp": FVP, "verbose": True, "experiment": "H3", "arms": arms}


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
