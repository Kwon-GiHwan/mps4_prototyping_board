"""H3-R shape-only derivatives (plan A8, GO section 2). Run in the TensorFlow venv:

    ~/.venvs/h3r-tf/bin/python gen_h3r_models.py

For each op type the H3 6x6 INT8 model (base_models/h3_<op>_6x6_c128.tflite, sha256 checked against
h13/h3_manifest.json) is read as a flatbuffer and ONLY the IFM (tensor 0) and OFM (tensor 3) `shape` fields are
set to [1, H, W, 128] before re-serialisation. Weight/bias buffers, quantisation records, operator code/version/
options, tensor names/types, metadata buffers are not touched. No re-calibration, no re-quantisation.
Writes models/h3r_<op>_<H>x<W>_c128.tflite and derived_models.json (file digests + the fields that were changed).
"""
import copy, hashlib, json, os

from tensorflow.lite.tools import flatbuffer_utils as fu

HERE = os.path.dirname(os.path.abspath(__file__))
C = 128
SHAPES = [(1, 36), (2, 18), (3, 12), (4, 9), (6, 6), (9, 4), (12, 3), (18, 2), (36, 1)]
OPS = ("conv1x1", "conv3x3", "dw3x3")
IFM, OFM = 0, 3


def base_sha(op):
    for m in json.load(open(os.path.join(HERE, "..", "h13", "h3_manifest.json"))):
        if m["model"] == "h3_%s_6x6_c128" % op:
            return m["sha256"]
    raise SystemExit("no H3 base entry for %s" % op)


def derive(model, h, w):
    new = copy.deepcopy(model)
    sg = new.subgraphs[0]
    assert list(sg.inputs) == [IFM] and list(sg.outputs) == [OFM], (sg.inputs, sg.outputs)
    for ti in (IFM, OFM):
        t = sg.tensors[ti]
        assert list(t.shape) == [1, 6, 6, C], list(t.shape)
        assert t.shapeSignature is None, "base model carries a shape_signature; extend the derivation"
        t.shape = [1, h, w, C]
    return new


def main():
    mdir = os.path.join(HERE, "models"); os.makedirs(mdir, exist_ok=True)
    out = []
    for op in OPS:
        src = os.path.join(HERE, "base_models", "h3_%s_6x6_c128.tflite" % op)
        blob = open(src, "rb").read(); sha = hashlib.sha256(blob).hexdigest()
        assert sha == base_sha(op), ("base model digest != h13/h3_manifest.json", op, sha)
        model = fu.read_model(src)
        for h, w in SHAPES:
            name = "h3r_%s_%dx%d_c128" % (op, h, w)
            path = os.path.join(mdir, name + ".tflite")
            fu.write_model(derive(model, h, w), path)
            dblob = open(path, "rb").read()
            out.append({"model": name, "op": op, "H": h, "W": w, "C": C, "area": h * w, "base_model": "h3_%s_6x6_c128" % op,
                        "base_sha256": sha, "bytes": len(dblob), "sha256": hashlib.sha256(dblob).hexdigest(),
                        "changed_fields": ["subgraphs[0].tensors[%d].shape" % IFM, "subgraphs[0].tensors[%d].shape" % OFM],
                        "identical_to_base_file": dblob == blob})
    json.dump(out, open(os.path.join(HERE, "derived_models.json"), "w"), indent=1)
    for r in out:
        print(r["model"], r["bytes"], r["sha256"][:12], "identical_to_base_file" if r["identical_to_base_file"] else "")


if __name__ == "__main__":
    main()
