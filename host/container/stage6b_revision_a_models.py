#!/usr/bin/env python3
"""Stage 6B Revision A (evidence/stage6b/revision_a/revision_a_contract.md): the 26 fixed candidates in three forms,
compiled twice, with the raw facts the judge (host/analysis/stage6b_revision_a.py) needs. Runs in the benchmark-runner
container. Imports stage6b_models / stage4ao_models / stage4aoe_models / stage4_inventory / cms_regs; edits none of them.

  python3 stage6b_revision_a_models.py manifest <out.json> <candidates.json> <inventory.csv>   source fixation (Phase 0)
  python3 stage6b_revision_a_models.py compile <out dir> <manifest.json> [group ...]           A0/A1/A2 x 2 (Phase 1)

A0 = F_PLAIN   CONV_2D alone                              (same bytes as Stage 6B 0c4bf4c)
A1 = F_CTX     ADD(a, b) -> CONV_2D -> ADD(conv_out, c)   (same bytes as Stage 6B 0c4bf4c)
A2 = F_CTX_SELF ADD(a, b) -> CONV_2D -> ADD(conv_out, conv_out); final scale 2 x conv_out scale, zero point of conv_out
This module records facts only; every pass/fail rule lives in the judge.
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
import stage6b_models as B  # noqa: E402

FORMS = {"A0": "F_PLAIN", "A1": "F_CTX", "A2": "F_CTX_SELF"}
META_PATH_KEYS = ("model", "ifm_file", "golden_file")     # absolute paths in the packer meta; differ per output dir


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tensor_facts(x: dict) -> dict:
    return dict(shape=list(x["shape"]), type=int(x["type"]), scale=list(x["scale"]), zp=list(x["zp"]), qdim=int(x["qdim"]),
                sha256=None if x.get("data") is None else sha(x["data"]))


# ---- Phase 0: source fixation ---------------------------------------------------------------------------------------
def manifest(out: str, cands_path: str, inv_path: str) -> dict:
    inv = {(r["model"], r["scheduled_id"]): r for r in csv.DictReader(open(inv_path))}
    cj = json.loads(pathlib.Path(cands_path).read_text())
    res = []
    for c in cj["candidates"]:
        rep = inv[(c["rep"]["model"], c["rep"]["scheduled_id"])]
        src = B.source_conv(rep["model"], int(rep["tflite_op_index"]))
        res.append(dict(group=c["group"], config=c["config"], model=rep["model"], scheduled_id=rep["scheduled_id"],
                        tflite_op_index=int(rep["tflite_op_index"]), mac_count=int(rep["mac_count"]),
                        cms_offsets=[int(o) for o in rep["cms_offsets"].split()], inventory_vela_sha256=rep["vela_sha256"],
                        model_sha256=src["model_sha256"], stride=list(src["stride"]), dilation=list(src["dilation"]),
                        activation=B.ACTS.get(src["activation"], str(src["activation"])),
                        padding="SAME" if src["padding"] == 0 else "VALID",
                        tensors={k: tensor_facts(src[k]) for k in ("ifm", "w", "b", "ofm")}, macs=c["macs"]))
    doc = dict(contract="evidence/stage6b/revision_a/revision_a_contract.md", candidates_json=cands_path,
               candidates_sha256=sha(pathlib.Path(cands_path).read_bytes()), n=len(res), candidates=res)
    pathlib.Path(out).write_text(json.dumps(doc, indent=1))
    return doc


# ---- Phase 1: compile ------------------------------------------------------------------------------------------------
def tensors(src: dict, form: str):
    if form != "F_CTX_SELF":
        return B.tensors(src, form)
    i, w, b, o = src["ifm"], src["w"], src["b"], src["ofm"]
    t = lambda name, x, data=None: dict(name=name, shape=x["shape"], type=x["type"], data=data, scale=x["scale"], zp=x["zp"],
                                        qdim=x["qdim"])
    ts = [t("a", i), t("b", i), t("ifm", i), t("weights", w, w["data"]), t("bias", b, b["data"]), t("conv_out", o),
          t("ofm", dict(o, scale=[2 * o["scale"][0]]))]
    ops = [dict(kind="add", ins=[0, 1], outs=[2]), dict(kind="conv", arg=B.ACTS[src["activation"]], ins=[2, 3, 4], outs=[5]),
           dict(kind="add", ins=[5, 5], outs=[6])]
    return ts, ops, [i["shape"], i["shape"]]


def graph_conv_tensors(model: bytes) -> dict:
    """The CONV_2D tensors of the generated (pre-Vela) graph, read back from its bytes."""
    import tflite
    m = tflite.Model.GetRootAsModel(model, 0)
    g = m.Subgraphs(0)
    convs = [g.Operators(k) for k in range(g.OperatorsLength())
             if max(m.OperatorCodes(g.Operators(k).OpcodeIndex()).BuiltinCode(),
                    m.OperatorCodes(g.Operators(k).OpcodeIndex()).DeprecatedBuiltinCode()) == 3]
    assert len(convs) == 1

    def tensor(i):
        t = g.Tensors(i)
        q = t.Quantization()
        buf = m.Buffers(t.Buffer()).DataAsNumpy()
        return dict(name=t.Name().decode(), shape=[int(t.Shape(k)) for k in range(t.ShapeLength())], type=int(t.Type()),
                    scale=[float(x) for x in q.ScaleAsNumpy()], zp=[int(x) for x in q.ZeroPointAsNumpy()],
                    qdim=int(q.QuantizedDimension()), sha256=None if isinstance(buf, int) else sha(buf.tobytes()))
    op = convs[0]
    return dict(ifm=tensor(op.Inputs(0)), w=tensor(op.Inputs(1)), b=tensor(op.Inputs(2)), ofm=tensor(op.Outputs(0)))


def ref_tensors(model_path: str, xs: list) -> dict:
    """BUILTIN_REF run with every tensor preserved: graph outputs, the Conv input and the Conv output."""
    from tflite_runtime.interpreter import Interpreter, OpResolverType
    it = Interpreter(model_path=model_path, experimental_op_resolver_type=OpResolverType.BUILTIN_REF,
                     experimental_preserve_all_tensors=True)
    it.allocate_tensors()
    for d, x in zip(it.get_input_details(), xs):
        it.set_tensor(d["index"], x.reshape(d["shape"]).astype(d["dtype"]))
    it.invoke()
    by = {d["name"]: d["index"] for d in it.get_tensor_details()}
    out_name = "ofm"
    conv_out = "conv_out" if "conv_out" in by else out_name
    return dict(final=it.get_tensor(by[out_name]).copy(), conv_in=it.get_tensor(by["ifm"]).copy(),
                conv_out=it.get_tensor(by[conv_out]).copy())


def numpy_conv1x1(x: np.ndarray, src: dict) -> np.ndarray:
    """Independent 1x1 Conv (stride 1) from the source tensors: int64 accumulate, float64 requantisation, clamp."""
    i, w, b, o = src["ifm"], src["w"], src["b"], src["ofm"]
    wt = np.frombuffer(w["data"], np.int8).reshape(w["shape"][0], -1).astype(np.int64)        # Cout x Cin
    wzp = np.array(w["zp"] if len(w["zp"]) == wt.shape[0] else w["zp"] * wt.shape[0], np.int64)
    bias = np.frombuffer(b["data"], {2: np.int32, 9: np.int8, 7: np.int16, 4: np.int64}.get(b["type"], np.int32)).astype(np.int64)
    xi = x.reshape(-1, x.shape[-1]).astype(np.int64) - i["zp"][0]
    acc = xi @ (wt - wzp[:, None]).T + bias
    ws = np.array(w["scale"] if len(w["scale"]) == wt.shape[0] else w["scale"] * wt.shape[0], np.float64)
    q = np.round(acc * (i["scale"][0] * ws / o["scale"][0])) + o["zp"][0]
    lo, hi = act_range(src)
    return np.clip(q, lo, hi).astype(np.int64).reshape(x.shape[:-1] + (wt.shape[0],))


def act_range(src: dict) -> tuple[int, int]:
    s, z = src["ofm"]["scale"][0], src["ofm"]["zp"][0]
    act = B.ACTS[src["activation"]]
    lo = z if act in ("RELU", "RELU6") else -128
    hi = z + int(round(6 / s)) if act == "RELU6" else 127
    return max(lo, -128), min(hi, 127)


def kernels_at(stream: bytes, offsets: list[int]) -> list[dict]:
    import cms_regs
    ks = {k["offset"]: k for k in cms_regs.kernels(stream)}
    return [ks.get(o) for o in offsets]


def original(model: str, offsets: list[int], cache: dict) -> dict:
    """Recompile the original MLEK model (MLEK Vela options) and read the Conv's kernel register states."""
    if model not in cache:
        from pack_vela_workload import VELA_OPTIONS, extract_cms
        import tflite
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["vela", str(B.MLEK / B.SOURCES[model] / f"{model}.tflite"), *VELA_OPTIONS, "--output-dir", d],
                           check=True, capture_output=True)
            blob = open(glob.glob(os.path.join(d, "*_vela.tflite"))[0], "rb").read()
        m = tflite.Model.GetRootAsModel(blob, 0); g = m.Subgraphs(0)
        eu = [g.Operators(k) for k in range(g.OperatorsLength())
              if (m.OperatorCodes(g.Operators(k).OpcodeIndex()).CustomCode() or b"").startswith(b"ethos-u")]
        stream = extract_cms(m.Buffers(g.Tensors(eu[0].Inputs(0)).Buffer()).DataAsNumpy().tobytes()) if len(eu) == 1 else None
        cache[model] = dict(vela_sha256=sha(blob), n_ethosu_ops=len(eu), stream=stream)
    c = cache[model]
    return dict(vela_sha256=c["vela_sha256"], n_ethosu_ops=c["n_ethosu_ops"],
                conv_kernels=kernels_at(c["stream"], offsets) if c["stream"] is not None else None)


def build(cfg: str, src: dict, form: str, o: pathlib.Path) -> dict:
    """stage6b_models.build for F_PLAIN / F_CTX (identical steps and names, so A0/A1 bytes equal 0c4bf4c), plus A2 and
    the Revision A facts."""
    import drwl
    ts, ops, shapes = tensors(src, form)
    model = AO.graph(f"{cfg}_{form}", ts, ops)
    rng = np.random.default_rng(B.S6B_SEED)
    xs = [rng.integers(-128, 128, size=s, dtype=np.int8) for s in shapes]
    name = f"{cfg}_{form.lower()}"
    mp = o / f"{name}.tflite"; mp.write_bytes(model)
    (o / f"{name}.ifm.bin").write_bytes(b"".join(x.tobytes() for x in xs))
    opt, ref = b"".join(AOE.run(str(mp), xs, False)), b"".join(AOE.run(str(mp), xs, True))
    (o / f"{name}.ref_ofm.bin").write_bytes(ref)
    rows = B.inventory_rows(mp)
    convs = [r for r in rows if r.get("npu_op") == "Conv2D"]
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile", str(B.PROFILE),
                        "--format", "drwl", "--out", str(o / f"{name}.drwl"), "--ifm", str(o / f"{name}.ifm.bin"),
                        "--golden", str(o / f"{name}.ref_ofm.bin")], capture_output=True, text=True)
    res = dict(config=name, form=form, model_sha256=sha(model), reference=AOE.compare(opt, ref), rows=rows,
               conv_row=convs[0] if len(convs) == 1 else None, n_conv_rows=len(convs),
               cpu_rows=[r["tflite_op"] for r in rows if r.get("cpu") == "1"],
               npu_ops=[r["npu_op"] for r in rows if r.get("cpu") == "0" and r.get("npu_op")], pack_rc=p.returncode,
               pack_log_tail=(p.stdout + p.stderr).strip().splitlines()[-4:], graph_conv=graph_conv_tensors(model))
    if p.returncode == 0:
        meta = json.loads((o / f"{name}.drwl.json").read_text())
        blob = (o / f"{name}.drwl").read_bytes()
        h = drwl.parse(blob)
        stream = (o / f"{name}.drwl.cms.bin").read_bytes()
        with tempfile.TemporaryDirectory() as d:
            ident = AOE.identity_manifest(pathlib.Path(d), [str(o / f"{name}.drwl")])[name]
        res.update(drwl_sha256=meta["blob_sha256"], vela_sha256=meta["vela_sha256"], golden_sha256=meta["golden_sha256"],
                   arena_size=meta["arena_size"], fast_size=meta["fast_size"], model_len=h["model_len"],
                   cms_len=meta["cms_len"], ta_profile=meta.get("ta_profile"), placement=h["placement"],
                   n_base=ident["n_base"], cms_sha256=sha(stream),
                   manifest_sha256=sha(json.dumps({k: v for k, v in meta.items() if k not in META_PATH_KEYS},
                                                  sort_keys=True).encode()),
                   conv_kernels=kernels_at(stream, [int(x) for x in convs[0]["cms_offsets"].split()]) if len(convs) == 1
                   else None)
    res["feasible"] = dict(
        single_conv=len(convs) == 1, no_cpu=not res["cpu_rows"], packed=p.returncode == 0,
        reference=res["reference"]["n"] > 0,
        fast_size=p.returncode == 0 and res["fast_size"] <= B.LIMITS["fast_size"],
        arena_size=p.returncode == 0 and res["arena_size"] <= B.LIMITS["arena_size"],
        model_region=p.returncode == 0 and res["model_len"] + res["arena_size"] <= B.LIMITS["model_region"])
    rt = ref_tensors(str(mp), xs)
    lo, hi = act_range(src)
    co, fin = rt["conv_out"].astype(np.int64), rt["final"].astype(np.int64)
    npc = numpy_conv1x1(rt["conv_in"], src)
    res["refcheck"] = dict(
        final_sha256_equals_ref=sha(rt["final"].tobytes()) == res["reference"]["ref_sha256"],
        numpy_vs_ref_mismatch=int((npc != co.reshape(npc.shape)).sum()),
        numpy_vs_ref_max_abs=int(np.abs(npc - co.reshape(npc.shape)).max()), n_conv_out=int(co.size),
        act_range=[lo, hi], conv_out_informative=float(((co > lo) & (co < hi)).mean()),
        final_informative=float(((fin > -128) & (fin < 127)).mean()),
        final_vs_conv_out_max_abs=int(np.abs(fin.reshape(-1) - co.reshape(-1)).max()) if fin.size == co.size else None,
        conv_out_distinct=int(np.unique(co).size))
    return res


REPEAT_KEYS = ("model_sha256", "vela_sha256", "drwl_sha256", "manifest_sha256", "cms_sha256", "conv_row", "conv_kernels")


def make(c: dict, o: pathlib.Path, cache: dict) -> dict:
    src = B.source_conv(c["model"], c["tflite_op_index"])
    assert src["stride"] == (1, 1) and src["dilation"] == (1, 1), (c["config"], src["stride"], src["dilation"])
    forms = {}
    for label, form in FORMS.items():
        r1 = build(c["config"], src, form, o)
        with tempfile.TemporaryDirectory() as d:
            r2 = build(c["config"], src, form, pathlib.Path(d))
        r1["second"] = {k: r2.get(k) for k in REPEAT_KEYS}
        forms[label] = r1
    rec = dict(config=c["config"], group=c["group"], source=dict(model=src["model"], op_index=src["op_index"],
                                                                  model_sha256=src["model_sha256"],
                                                                  tensors={k: tensor_facts(src[k]) for k in ("ifm", "w", "b", "ofm")}),
               original=original(c["model"], c["cms_offsets"], cache), s6b_seed=B.S6B_SEED, forms=forms)
    (o / f"{c['config']}.ra.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def main(argv: list) -> None:
    if argv[0] == "manifest":
        d = manifest(*argv[1:4])
        print(d["n"], "candidates fixed")
        return
    o = pathlib.Path(argv[1]); o.mkdir(parents=True, exist_ok=True)
    cands = json.loads(pathlib.Path(argv[2]).read_text())["candidates"]
    only = set(argv[3:])
    cache = {}
    for c in cands:
        if only and c["group"] not in only:
            continue
        rec = make(c, o, cache)
        for label, r in rec["forms"].items():
            row = r["conv_row"] or {}
            print(c["config"], label, {k: v for k, v in r["feasible"].items() if not v} or "feasible", row.get("ofm_block"),
                  row.get("ifm_memory"), row.get("ofm_memory"), row.get("staging_usage"), "np_vs_ref",
                  r["refcheck"]["numpy_vs_ref_max_abs"], "drwl", (r.get("drwl_sha256") or "")[:12], flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
