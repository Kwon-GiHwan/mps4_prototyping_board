"""Static metadata for a screening workload: per-op MACs from the original tflite, and Vela's prediction.

Runs in the benchmark-runner container (needs `tflite` and `vela`). Uses the packer's (MLEK) Vela options.
MAC = one multiply-accumulate. Only CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, BATCH_MATMUL carry
MACs; every other op is listed with n_mac = None (not applicable, not zero).

    python3 screening_workload_meta.py MODEL.tflite OUT.json   (pack_vela_workload.py beside it)
"""
import csv, glob, hashlib, json, subprocess, sys, tempfile
import numpy as np
import tflite
from tflite.BuiltinOperator import BuiltinOperator as B
from pack_vela_workload import VELA_OPTIONS

OPNAME = {v: k for k, v in vars(B).items() if not k.startswith("_")}


def shape(t):
    return [int(t.Shape(i)) for i in range(t.ShapeLength())]


def op_macs(code, ins, outs):
    """ins/outs: lists of shapes. Returns MACs or None for non-MAC ops."""
    if code == B.CONV_2D:            # filter [Cout, Kh, Kw, Cin/groups]; OFM [N, Ho, Wo, Cout]
        n, ho, wo, cout = outs[0]; _, kh, kw, cin_g = ins[1]
        return n * ho * wo * cout * kh * kw * cin_g
    if code == B.DEPTHWISE_CONV_2D:  # filter [1, Kh, Kw, Cout]
        n, ho, wo, cout = outs[0]; _, kh, kw, _ = ins[1]
        return n * ho * wo * cout * kh * kw
    if code == B.FULLY_CONNECTED:    # weights [Cout, Cin]; batch = OFM rows
        cout, cin = ins[1]
        return int(np.prod(outs[0][:-1])) * cin * cout
    if code == B.BATCH_MATMUL:       # [..., M, K] x [..., K, N] (adj flags folded into shapes below)
        return int(np.prod(outs[0])) * ins[0][-1]
    return None


def analyse(path):
    m = tflite.Model.GetRootAsModel(open(path, "rb").read(), 0); sg = m.Subgraphs(0)
    ops = []
    for i in range(sg.OperatorsLength()):
        op = sg.Operators(i); oc = m.OperatorCodes(op.OpcodeIndex())
        code = max(oc.BuiltinCode(), oc.DeprecatedBuiltinCode())
        ins = [shape(sg.Tensors(op.Inputs(k))) for k in range(op.InputsLength()) if op.Inputs(k) >= 0]
        outs = [shape(sg.Tensors(op.Outputs(k))) for k in range(op.OutputsLength())]
        ops.append(dict(op=OPNAME.get(code, str(code)), inputs=ins, outputs=outs, n_mac=op_macs(code, ins, outs)))
    return ops


def vela_summary(path, vela):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", path, *vela, "--output-dir", d], check=True, capture_output=True)
        row = next(csv.DictReader(open(glob.glob(d + "/*_summary_*.csv")[0])))
    keep = ("core_clock", "nn_macs", "cycles_npu", "cycles_sram_access", "cycles_dram_access", "cycles_total")
    return {k: float(row[k]) for k in keep}


def main(model, out):
    vela = VELA_OPTIONS
    ops = analyse(model)
    macs = [o["n_mac"] for o in ops if o["n_mac"] is not None]
    meta = dict(model=model, model_sha256=hashlib.sha256(open(model, "rb").read()).hexdigest(),
                vela_options=vela, ops=ops, op_counts={o: sum(1 for x in ops if x["op"] == o) for o in {x["op"] for x in ops}},
                n_mac=sum(macs), n_mac_ops=len(macs), non_mac_ops=len(ops) - len(macs), vela=vela_summary(model, vela))
    meta["n_mac_vs_vela_nn_macs"] = meta["n_mac"] / meta["vela"]["nn_macs"] if meta["vela"]["nn_macs"] else None
    json.dump(meta, open(out, "w"), indent=1)
    print(json.dumps({k: meta[k] for k in ("n_mac", "n_mac_ops", "non_mac_ops", "op_counts", "vela", "n_mac_vs_vela_nn_macs")}))


if __name__ == "__main__":
    main(*sys.argv[1:3])
