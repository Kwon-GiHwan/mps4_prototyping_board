#!/usr/bin/env python3
"""Stage 6B (evidence/stage6b/rules.md §4): rebuild each candidate 1x1 DepthFirst Conv from the original MLEK model's own
tensors (weights, bias, per-channel scales, IFM/OFM quantization, fused activation) in two forms, compile them with Vela
(MLEK options) and record the scheduled Conv row in the Stage 4 inventory format. Runs in the benchmark-runner container.
Imports make_op_model / stage4ao_models / stage4aoe_models / stage4_inventory; edits none of them.

  python3 stage6b_models.py <out dir> <candidates.json>                      both forms, twice (repeat check)
  python3 stage6b_models.py <out dir> identity <drwl>...                     A1 expected_identity.json (selected only)

F_PLAIN  CONV_2D alone (IFM graph input, OFM graph output).
F_CTX    ADD(a, b) -> CONV_2D -> ADD(conv out, c): the Conv IFM and OFM become intermediate tensors.
Golden = BUILTIN_REF output (opt vs ref recorded). IFMs from S6B_SEED, full int8 range, graph-input order.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib")); sys.path.insert(0, str(HERE.parents[0] / "analysis"))
import stage4ao_models as AO  # noqa: E402
import stage4aoe_models as AOE  # noqa: E402

S6B_SEED = 20261118
MLEK = pathlib.Path("/opt/arm/ml-embedded-evaluation-kit/resources_downloaded")
SOURCES = {"kws_micronet_m": "kws", "ad_medium_int8": "ad", "mobilenet_v2_1.0_224_INT8": "img_class",
           "vww4_128_128_INT8": "vww", "rnnoise_INT8": "noise_reduction", "yolo-fastest_192_face_v4": "object_detection",
           "wav2letter_pruned_int8": "asr"}
PROFILE = HERE.parents[1] / "config" / "fi101_s013.json"
ACTS = {0: "NONE", 1: "RELU", 3: "RELU6"}
LIMITS = dict(fast_size=0x60000, arena_size=0x200000, model_region=32 << 20)


def source_conv(model: str, op_index: int) -> dict:
    """The original CONV_2D's tensors and options, read from the MLEK tflite."""
    import tflite
    path = MLEK / SOURCES[model] / f"{model}.tflite"
    m = tflite.Model.GetRootAsModel(path.read_bytes(), 0)
    g = m.Subgraphs(0)
    op = g.Operators(op_index)
    code = m.OperatorCodes(op.OpcodeIndex())
    assert max(code.BuiltinCode(), code.DeprecatedBuiltinCode()) == 3, f"{model}#{op_index} is not CONV_2D"
    o = tflite.Conv2DOptions(); bo = op.BuiltinOptions(); o.Init(bo.Bytes, bo.Pos)

    def tensor(i):
        t = g.Tensors(i)
        q = t.Quantization()
        buf = m.Buffers(t.Buffer()).DataAsNumpy()
        return dict(shape=tuple(int(t.Shape(k)) for k in range(t.ShapeLength())), type=t.Type(),
                    scale=[float(x) for x in q.ScaleAsNumpy()], zp=[int(x) for x in q.ZeroPointAsNumpy()],
                    qdim=q.QuantizedDimension(), data=None if isinstance(buf, int) else buf.tobytes())
    ifm, w, b = (tensor(op.Inputs(k)) for k in range(3))
    ofm = tensor(op.Outputs(0))
    return dict(model=model, op_index=op_index, model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                ifm=ifm, w=w, b=b, ofm=ofm, stride=(o.StrideH(), o.StrideW()), padding=o.Padding(),
                dilation=(o.DilationHFactor(), o.DilationWFactor()), activation=o.FusedActivationFunction())


def tensors(src: dict, form: str) -> tuple[list, list, list]:
    """(tensors, ops, graph input shapes) for AO.graph; the Conv uses the source tensors byte for byte."""
    i, w, b, o = src["ifm"], src["w"], src["b"], src["ofm"]
    t = lambda name, x, data=None: dict(name=name, shape=x["shape"], type=x["type"], data=data, scale=x["scale"], zp=x["zp"],
                                        qdim=x["qdim"])
    conv_t = [t("weights", w, w["data"]), t("bias", b, b["data"])]
    act = ACTS[src["activation"]]
    if form == "F_PLAIN":
        ts = [t("ifm", i)] + conv_t + [t("ofm", o)]
        return ts, [dict(kind="conv", arg=act, ins=[0, 1, 2], outs=[3])], [i["shape"]]
    ofm2 = dict(o, scale=[2 * o["scale"][0]])
    ts = [t("a", i), t("b", i), t("ifm", i)] + conv_t + [t("conv_out", o), t("c", o), t("ofm", ofm2)]
    ops = [dict(kind="add", ins=[0, 1], outs=[2]), dict(kind="conv", arg=act, ins=[2, 3, 4], outs=[5]),
           dict(kind="add", ins=[5, 6], outs=[7])]
    return ts, ops, [i["shape"], i["shape"], o["shape"]]


def inventory_rows(model_path: pathlib.Path) -> list[dict]:
    import stage4_inventory as INV
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "inv.csv")
        INV.main(out, str(model_path))
        return list(csv.DictReader(open(out)))


def build(cfg: str, src: dict, form: str, o: pathlib.Path) -> dict:
    import drwl
    ts, ops, shapes = tensors(src, form)
    model = AO.graph(f"{cfg}_{form}", ts, ops)
    rng = np.random.default_rng(S6B_SEED)
    xs = [rng.integers(-128, 128, size=s, dtype=np.int8) for s in shapes]
    name = f"{cfg}_{form.lower()}"
    mp = o / f"{name}.tflite"; mp.write_bytes(model)
    (o / f"{name}.ifm.bin").write_bytes(b"".join(x.tobytes() for x in xs))
    opt, ref = b"".join(AOE.run(str(mp), xs, False)), b"".join(AOE.run(str(mp), xs, True))
    (o / f"{name}.ref_ofm.bin").write_bytes(ref)
    rows = inventory_rows(mp)
    convs = [r for r in rows if r.get("npu_op") == "Conv2D"]
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile", str(PROFILE),
                        "--format", "drwl", "--out", str(o / f"{name}.drwl"), "--ifm", str(o / f"{name}.ifm.bin"),
                        "--golden", str(o / f"{name}.ref_ofm.bin")], capture_output=True, text=True)
    res = dict(config=name, form=form, model_sha256=hashlib.sha256(model).hexdigest(), reference=AOE.compare(opt, ref),
               rows=rows, conv_row=convs[0] if len(convs) == 1 else None, n_conv_rows=len(convs),
               cpu_rows=[r["tflite_op"] for r in rows if r.get("cpu") == "1"], pack_rc=p.returncode,
               pack_log_tail=(p.stdout + p.stderr).strip().splitlines()[-4:])
    if p.returncode == 0:
        meta = json.loads((o / f"{name}.drwl.json").read_text())
        blob = (o / f"{name}.drwl").read_bytes()
        h = drwl.parse(blob)
        res.update(drwl_sha256=meta["blob_sha256"], vela_sha256=meta["vela_sha256"], golden_sha256=meta["golden_sha256"],
                   arena_size=meta["arena_size"], fast_size=meta["fast_size"], model_len=h["model_len"],
                   cms_len=meta["cms_len"])
    res["feasible"] = dict(
        single_conv=len(convs) == 1, no_cpu=not res["cpu_rows"], packed=p.returncode == 0,
        reference=res["reference"]["n"] > 0,
        fast_size=p.returncode == 0 and res["fast_size"] <= LIMITS["fast_size"],
        arena_size=p.returncode == 0 and res["arena_size"] <= LIMITS["arena_size"],
        model_region=p.returncode == 0 and res["model_len"] + res["arena_size"] <= LIMITS["model_region"])
    return res


def make(c: dict, o: pathlib.Path) -> dict:
    src = source_conv(c["rep"]["model"], int(c["rep"]["tflite_op_index"]))
    assert src["stride"] == (1, 1) and src["dilation"] == (1, 1), (c["config"], src["stride"], src["dilation"])
    assert src["activation"] in ACTS, (c["config"], src["activation"])
    forms = {}
    for form in ("F_PLAIN", "F_CTX"):
        r1 = build(c["config"], src, form, o)
        with tempfile.TemporaryDirectory() as d:
            r2 = build(c["config"], src, form, pathlib.Path(d))
        same = all(r1.get(k) == r2.get(k) for k in ("model_sha256", "vela_sha256", "drwl_sha256"))
        r1["feasible"]["repeat_identical"] = same and r1.get("drwl_sha256") is not None
        forms[form] = r1
    rec = dict(config=c["config"], group=c["group"], source=dict(model=src["model"], op_index=src["op_index"],
                                                                  model_sha256=src["model_sha256"],
                                                                  padding="SAME" if src["padding"] == 0 else "VALID",
                                                                  activation=ACTS[src["activation"]],
                                                                  ifm_quant=[src["ifm"]["scale"], src["ifm"]["zp"]],
                                                                  ofm_quant=[src["ofm"]["scale"], src["ofm"]["zp"]],
                                                                  weight_shape=src["w"]["shape"]),
               s6b_seed=S6B_SEED, forms=forms)
    (o / f"{c['config']}.s6b.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def main(argv: list) -> None:
    o = pathlib.Path(argv[0]); o.mkdir(parents=True, exist_ok=True)
    if argv[1:2] == ["identity"]:
        print(json.dumps(AOE.identity_manifest(o, argv[2:]), indent=1))
        return
    for c in json.loads(pathlib.Path(argv[1]).read_text())["candidates"]:
        rec = make(c, o)
        for f, r in rec["forms"].items():
            row = r["conv_row"] or {}
            print(c["config"], f, {k: v for k, v in r["feasible"].items() if not v} or "feasible",
                  row.get("ofm_block"), row.get("ifm_block"), row.get("ofm_ublock"), row.get("traversal"),
                  row.get("ifm_memory"), row.get("ofm_memory"), row.get("ifm_format"), row.get("ofm_format"),
                  row.get("weight_bytes"), "/", c["rep"]["weight_bytes"], row.get("staging_usage"), "/",
                  c["rep"]["staging_usage"], "opt_vs_ref", r["reference"]["opt_vs_ref"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
