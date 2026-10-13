"""Functional check of the 27 derived models with the TF Lite interpreter (plan A8, GO section 2.4). TF venv:

    ~/.venvs/h3r-tf/bin/python func_check.py

Per op type one common input vector: numpy.random.default_rng(20260915).integers(-128, 128, 4608, int8), reshaped
to [1,H,W,128] for each shape (input bytes and their sha256 are recorded). Checks load, invoke, output shape ==
[1,H,W,128]. The 6x6 derivative must reproduce the base model's output byte for byte (self check). Different
shapes are NOT required to agree. This does not replace the NPU output gate (verify build on the server).
Writes func_check.json.
"""
import hashlib, json, os

import numpy as np
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
C, AREA, SEED = 128, 36, 20260915


def run(path, x):
    it = tf.lite.Interpreter(model_path=path); it.allocate_tensors()
    i, o = it.get_input_details()[0], it.get_output_details()[0]
    assert i["dtype"] == np.int8 and o["dtype"] == np.int8, (i["dtype"], o["dtype"])
    it.set_tensor(i["index"], x); it.invoke()
    return it.get_tensor(o["index"]).copy(), [int(v) for v in i["shape"]], [int(v) for v in o["shape"]]


def main():
    man = json.load(open(os.path.join(HERE, "h3r_manifest.json")))
    vec = np.random.default_rng(SEED).integers(-128, 128, AREA * C, dtype=np.int8)
    common = {"seed": SEED, "bytes": AREA * C, "sha256": hashlib.sha256(vec.tobytes()).hexdigest(),
              "policy": "one int8 vector per op type (identical across the three op types), reshaped to [1,H,W,128] in row-major order"}
    out = {"input": common, "models": []}
    base_out = {}
    for m in man:
        x = vec.reshape(1, m["H"], m["W"], C)
        y, ishape, oshape = run(os.path.join(HERE, "models", m["model"] + ".tflite"), x)
        rec = {"model": m["model"], "op": m["op"], "H": m["H"], "W": m["W"], "input_shape": ishape, "output_shape": oshape,
               "output_shape_ok": oshape == [1, m["H"], m["W"], C], "output_bytes": int(y.nbytes),
               "output_sha256": hashlib.sha256(y.tobytes()).hexdigest(), "invoke_ok": True}
        if (m["H"], m["W"]) == (6, 6):
            yb, _, _ = run(os.path.join(HERE, "base_models", m["base_model"] + ".tflite"), x)
            rec["identical_to_base_output"] = bool(np.array_equal(y, yb)); base_out[m["op"]] = rec["identical_to_base_output"]
        out["models"].append(rec)
        print("%-24s in=%s out=%s ok=%s sha=%s %s" % (m["model"], ishape, oshape, rec["output_shape_ok"], rec["output_sha256"][:10],
                                                    "base_identical=%s" % rec.get("identical_to_base_output") if "identical_to_base_output" in rec else ""))
    out["all_shapes_ok"] = all(r["output_shape_ok"] for r in out["models"])
    out["six_by_six_identical_to_base"] = base_out
    json.dump(out, open(os.path.join(HERE, "func_check.json"), "w"), indent=1)
    print("all_shapes_ok", out["all_shapes_ok"], "6x6==base", base_out)


if __name__ == "__main__":
    main()
