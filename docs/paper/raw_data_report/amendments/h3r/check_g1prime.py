"""G1' -- non-shape identity between each derived model and its base (plan A8, GO section 2.3). TensorFlow venv:

    ~/.venvs/h3r-tf/bin/python check_g1prime.py            # writes h3r_manifest.json + model_manifest.csv
    ~/.venvs/h3r-tf/bin/python -m unittest check_g1prime   # fixtures: each rule trips on its own mutation

Field-level comparison of the final INT8 flatbuffers. Must be identical: weight buffer sha256, bias buffer sha256,
all quantisation records (every scale, every zero-point, quantized_dimension) of IFM/weights/bias/OFM, operator
code/version/options/connectivity, tensor count/types/names/buffers, weight and bias shapes, channel count, metadata
buffers. Allowed to differ: IFM/OFM shape (must equal [1,H,W,128]) and the file digest (re-serialisation).
Every refusal carries a rule id; a model passes only if no rule trips.
"""
import copy, csv, hashlib, json, os, sys, tempfile, unittest

from tensorflow.lite.tools import flatbuffer_utils as fu

HERE = os.path.dirname(os.path.abspath(__file__))
C = 128
IFM, W, B, OFM = 0, 2, 1, 3     # tensor indices in the H3 single-op models (weights are input 1, bias input 2 of the op)
RULE_WEIGHTS = "RULE_G1P_WEIGHTS"
RULE_BIAS = "RULE_G1P_BIAS"
RULE_QUANT = "RULE_G1P_QUANT"
RULE_OPERATOR = "RULE_G1P_OPERATOR"
RULE_STRUCTURE = "RULE_G1P_STRUCTURE"
RULE_SHAPE = "RULE_G1P_SHAPE"
RULES = (RULE_WEIGHTS, RULE_BIAS, RULE_QUANT, RULE_OPERATOR, RULE_STRUCTURE, RULE_SHAPE)
OPTION_FIELDS = ("padding", "strideW", "strideH", "fusedActivationFunction", "dilationWFactor", "dilationHFactor", "depthMultiplier", "quantizedBiasType")


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def refusal_rule(exc):
    return getattr(exc, "rule", None)


def bdata(model, index):
    d = model.buffers[index].data
    return bytes(d) if d is not None else b""


def buf_sha(model, tensor):
    return hashlib.sha256(bdata(model, tensor.buffer)).hexdigest()


def quant(t):
    q = t.quantization
    if q is None:
        return None
    return {"scale": [float(x) for x in (q.scale if q.scale is not None else [])],
            "zero_point": [int(x) for x in (q.zeroPoint if q.zeroPoint is not None else [])],
            "quantized_dimension": int(q.quantizedDimension)}


def options(op):
    o = op.builtinOptions
    return None if o is None else {k: int(getattr(o, k)) for k in OPTION_FIELDS if hasattr(o, k)}


def describe(model):
    """Non-shape description of a single-op model + the IFM/OFM shapes (kept apart)."""
    sg = model.subgraphs[0]
    d = {"n_subgraphs": len(model.subgraphs), "n_tensors": len(sg.tensors), "n_ops": len(sg.operators),
         "inputs": [int(x) for x in sg.inputs], "outputs": [int(x) for x in sg.outputs],
         "opcodes": [(int(c.builtinCode), int(c.deprecatedBuiltinCode), int(c.version)) for c in model.operatorCodes],
         "tensors": [{"name": bytes(t.name), "type": int(t.type), "buffer_sha": buf_sha(model, t), "quant": quant(t),
                      "shape": [int(x) for x in t.shape], "shape_signature": None if t.shapeSignature is None else [int(x) for x in t.shapeSignature]}
                     for t in sg.tensors],
         "ops": [{"opcode": int(o.opcodeIndex), "inputs": [int(x) for x in o.inputs], "outputs": [int(x) for x in o.outputs],
                  "options_type": int(o.builtinOptionsType), "options": options(o)} for o in sg.operators],
         "metadata": [(bytes(m.name), hashlib.sha256(bdata(model, m.buffer)).hexdigest()) for m in (model.metadata or [])]}
    return d


def check(base, derived, h, w):
    """Raise Refusal(rule) on the first violated field group; return the comparison record on success."""
    b, d = describe(base), describe(derived)
    if (b["n_subgraphs"], b["n_tensors"], b["n_ops"]) != (d["n_subgraphs"], d["n_tensors"], d["n_ops"]):
        raise Refusal(RULE_STRUCTURE, "tensor/op counts differ: %s vs %s" % ((b["n_subgraphs"], b["n_tensors"], b["n_ops"]), (d["n_subgraphs"], d["n_tensors"], d["n_ops"])))
    if b["inputs"] != d["inputs"] or b["outputs"] != d["outputs"] or b["metadata"] != d["metadata"]:
        raise Refusal(RULE_STRUCTURE, "subgraph inputs/outputs/metadata differ")
    for i, (bt, dt) in enumerate(zip(b["tensors"], d["tensors"])):
        if bt["name"] != dt["name"] or bt["type"] != dt["type"]:
            raise Refusal(RULE_STRUCTURE, "tensor %d name/type differ" % i)
        if i not in (IFM, OFM) and (bt["shape"] != dt["shape"] or bt["shape_signature"] != dt["shape_signature"]):
            raise Refusal(RULE_STRUCTURE, "tensor %d (non-IFM/OFM) shape differs: %s vs %s" % (i, bt["shape"], dt["shape"]))
    if b["tensors"][W]["buffer_sha"] != d["tensors"][W]["buffer_sha"]:
        raise Refusal(RULE_WEIGHTS, "weight buffer differs")
    if b["tensors"][B]["buffer_sha"] != d["tensors"][B]["buffer_sha"]:
        raise Refusal(RULE_BIAS, "bias buffer differs")
    for i in (IFM, W, B, OFM):
        if b["tensors"][i]["quant"] != d["tensors"][i]["quant"]:
            raise Refusal(RULE_QUANT, "quantisation record of tensor %d differs" % i)
    if b["opcodes"] != d["opcodes"] or b["ops"] != d["ops"]:
        raise Refusal(RULE_OPERATOR, "operator code/version/options/connectivity differ: %s vs %s" % ((b["opcodes"], b["ops"]), (d["opcodes"], d["ops"])))
    for i in (IFM, OFM):
        if d["tensors"][i]["shape"] != [1, h, w, C]:
            raise Refusal(RULE_SHAPE, "tensor %d shape %s != [1,%d,%d,%d]" % (i, d["tensors"][i]["shape"], h, w, C))
        if d["tensors"][i]["shape_signature"] not in (None, [1, h, w, C]):
            raise Refusal(RULE_SHAPE, "tensor %d shape_signature %s" % (i, d["tensors"][i]["shape_signature"]))
    if b["tensors"][W]["shape"][-1] != C and b["tensors"][W]["shape"][0] != C:
        raise Refusal(RULE_STRUCTURE, "channel count")
    return {"weights_sha256": d["tensors"][W]["buffer_sha"], "bias_sha256": d["tensors"][B]["buffer_sha"],
            "weight_shape": d["tensors"][W]["shape"], "weight_bytes": len(bdata(derived, derived.subgraphs[0].tensors[W].buffer)),
            "ifm_q": d["tensors"][IFM]["quant"], "ofm_q": d["tensors"][OFM]["quant"],
            "w_q_channels": len(d["tensors"][W]["quant"]["scale"]), "w_q_dim": d["tensors"][W]["quant"]["quantized_dimension"],
            "b_q_channels": len(d["tensors"][B]["quant"]["scale"]), "b_q_dim": d["tensors"][B]["quant"]["quantized_dimension"],
            "opcode": d["opcodes"][0], "options": d["ops"][0]["options"], "ifm_shape": d["tensors"][IFM]["shape"], "ofm_shape": d["tensors"][OFM]["shape"]}


def padding_note(op, h, w):
    if op == "conv1x1":
        return "no padding (1x1)"
    k = 3
    rows_full_pad = 2 if h == 1 else 0; cols_full_pad = 2 if w == 1 else 0
    border = h * w - max(h - 2, 0) * max(w - 2, 0)
    return "SAME 3x3: pad 1 each side; %d of %d OFM positions touch padding (%.0f%%)%s" % (
        border, h * w, 100.0 * border / (h * w),
        "; H=1: the top and bottom kernel rows read padding only" if rows_full_pad else ("; W=1: the left and right kernel columns read padding only" if cols_full_pad else ""))


def main():
    derived = json.load(open(os.path.join(HERE, "derived_models.json")))
    rows = []
    for r in derived:
        base = fu.read_model(os.path.join(HERE, "base_models", r["base_model"] + ".tflite"))
        d = fu.read_model(os.path.join(HERE, "models", r["model"] + ".tflite"))
        rec = dict(r)
        try:
            rec.update(check(base, d, r["H"], r["W"])); rec["g1prime_pass"] = True; rec["g1prime_rule"] = None
        except Refusal as e:
            rec["g1prime_pass"] = False; rec["g1prime_rule"] = e.rule; rec["g1prime_msg"] = str(e)
        rec["padding_note"] = padding_note(r["op"], r["H"], r["W"])
        rows.append(rec)
    json.dump(rows, open(os.path.join(HERE, "h3r_manifest.json"), "w"), indent=1)
    cols = ["model", "op", "H", "W", "C", "area", "base_model", "base_sha256", "sha256", "bytes", "identical_to_base_file",
            "weights_sha256", "bias_sha256", "weight_bytes", "w_q_channels", "w_q_dim", "b_q_channels", "b_q_dim", "opcode", "options",
            "ifm_q", "ofm_q", "ifm_shape", "ofm_shape", "g1prime_pass", "g1prime_rule", "padding_note"]
    with open(os.path.join(HERE, "model_manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
    n_ok = sum(1 for r in rows if r["g1prime_pass"])
    per_op = {}
    for r in rows:
        per_op.setdefault(r["op"], set()).add((r.get("weights_sha256"), r.get("bias_sha256"), json.dumps(r.get("ifm_q")), json.dumps(r.get("ofm_q"))))
    print("G1' pass %d/%d; distinct (weights, bias, ifm_q, ofm_q) per op: %s" % (n_ok, len(rows), {k: len(v) for k, v in per_op.items()}))
    for r in rows:
        if not r["g1prime_pass"]:
            print("FAIL", r["model"], r["g1prime_rule"], r["g1prime_msg"])
    return 0 if n_ok == len(rows) else 1


# ---------------------------------------------------------------- fixtures: every rule must trip on its own mutation
class G1PrimeRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fu.read_model(os.path.join(HERE, "base_models", "h3_conv3x3_6x6_c128.tflite"))

    def derived(self, h=2, w=18):
        m = copy.deepcopy(self.base)
        for ti in (IFM, OFM):
            m.subgraphs[0].tensors[ti].shape = [1, h, w, C]
        return m

    def rule(self, m, h=2, w=18):
        try:
            check(self.base, m, h, w); return None
        except Refusal as e:
            return e.rule

    def test_shape_only_derivative_passes(self):
        self.assertEqual(self.rule(self.derived()), None)
        self.assertEqual(self.rule(copy.deepcopy(self.base), 6, 6), None)

    def test_weights(self):
        m = self.derived(); d = bytearray(m.buffers[m.subgraphs[0].tensors[W].buffer].data); d[100] ^= 1
        m.buffers[m.subgraphs[0].tensors[W].buffer].data = bytes(d)
        self.assertEqual(self.rule(m), RULE_WEIGHTS)

    def test_bias(self):
        m = self.derived(); d = bytearray(m.buffers[m.subgraphs[0].tensors[B].buffer].data); d[3] ^= 1
        m.buffers[m.subgraphs[0].tensors[B].buffer].data = bytes(d)
        self.assertEqual(self.rule(m), RULE_BIAS)

    def test_quant(self):
        m = self.derived(); m.subgraphs[0].tensors[OFM].quantization.zeroPoint = [2]
        self.assertEqual(self.rule(m), RULE_QUANT)
        m = self.derived(); m.subgraphs[0].tensors[IFM].quantization.scale = [0.01]
        self.assertEqual(self.rule(m), RULE_QUANT)
        m = self.derived(); s = list(m.subgraphs[0].tensors[W].quantization.scale); s[5] = s[5] * 1.01; m.subgraphs[0].tensors[W].quantization.scale = s
        self.assertEqual(self.rule(m), RULE_QUANT)
        m = self.derived(); m.subgraphs[0].tensors[B].quantization.quantizedDimension = 1
        self.assertEqual(self.rule(m), RULE_QUANT)

    def test_operator(self):
        m = self.derived(); m.subgraphs[0].operators[0].builtinOptions.strideW = 2
        self.assertEqual(self.rule(m), RULE_OPERATOR)
        m = self.derived(); m.subgraphs[0].operators[0].builtinOptions.padding = 1
        self.assertEqual(self.rule(m), RULE_OPERATOR)
        m = self.derived(); m.operatorCodes[0].version = 2
        self.assertEqual(self.rule(m), RULE_OPERATOR)
        m = self.derived(); m.subgraphs[0].operators[0].inputs = [0, 1, 2]
        self.assertEqual(self.rule(m), RULE_OPERATOR)

    def test_structure(self):
        m = self.derived(); m.subgraphs[0].tensors[W].shape = [128, 3, 3, 64]
        self.assertEqual(self.rule(m), RULE_STRUCTURE)
        m = self.derived(); m.subgraphs[0].tensors[IFM].type = 3
        self.assertEqual(self.rule(m), RULE_STRUCTURE)
        m = self.derived(); m.subgraphs[0].tensors.append(copy.deepcopy(m.subgraphs[0].tensors[OFM]))
        self.assertEqual(self.rule(m), RULE_STRUCTURE)
        m = self.derived(); m.metadata = []
        self.assertEqual(self.rule(m), RULE_STRUCTURE)

    def test_shape(self):
        self.assertEqual(self.rule(self.derived(2, 18), 3, 12), RULE_SHAPE)      # wrong target shape
        m = self.derived(); m.subgraphs[0].tensors[OFM].shape = [1, 6, 6, C]
        self.assertEqual(self.rule(m), RULE_SHAPE)                                # only IFM changed
        m = self.derived(); m.subgraphs[0].tensors[IFM].shapeSignature = [1, -1, -1, C]
        self.assertEqual(self.rule(m), RULE_SHAPE)

    def test_roundtrip_through_file(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "m.tflite"); fu.write_model(self.derived(), p)
        self.assertEqual(self.rule(fu.read_model(p)), None)

    def test_rules_tuple_complete(self):
        tripped = set()
        for name in ("test_weights", "test_bias", "test_quant", "test_operator", "test_structure", "test_shape"):
            getattr(self, name)()
        muts = []
        m = self.derived(); d = bytearray(m.buffers[m.subgraphs[0].tensors[W].buffer].data); d[0] ^= 1; m.buffers[m.subgraphs[0].tensors[W].buffer].data = bytes(d); muts.append(m)
        m = self.derived(); d = bytearray(m.buffers[m.subgraphs[0].tensors[B].buffer].data); d[0] ^= 1; m.buffers[m.subgraphs[0].tensors[B].buffer].data = bytes(d); muts.append(m)
        m = self.derived(); m.subgraphs[0].tensors[OFM].quantization.zeroPoint = [9]; muts.append(m)
        m = self.derived(); m.subgraphs[0].operators[0].builtinOptions.strideH = 2; muts.append(m)
        m = self.derived(); m.subgraphs[0].tensors[IFM].type = 3; muts.append(m)
        m = self.derived(); m.subgraphs[0].tensors[OFM].shape = [1, 3, 12, C]; muts.append(m)
        for m in muts:
            tripped.add(self.rule(m))
        self.assertEqual(tripped, set(RULES))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.argv = sys.argv[:1]; unittest.main()
    else:
        sys.exit(main())
