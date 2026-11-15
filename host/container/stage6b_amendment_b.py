#!/usr/bin/env python3
"""Stage 6B Revision A Amendment B facts (evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md). Facts only;
every pass/fail rule lives in host/analysis/stage6b_amendment_b.py. Reads the Revision A compile directory, never writes
into it.

  stage6b_amendment_b.py fusion   <compile dir> <manifest.json> <out.json>
  stage6b_amendment_b.py diagnose <compile dir> <manifest.json> <out.json> <group>...
  stage6b_amendment_b.py fixture  <compile dir> <manifest.json> <equiv_c dir> <out dir> <group>...
  stage6b_amendment_b.py vela     <compile dir> <manifest.json> <out.json> <group>...   (A2 network estimate, Vela summary)
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import stage6b_models as B  # noqa: E402
import stage6b_revision_a_models as RA  # noqa: E402
import cms  # noqa: E402

ACT_C0 = dict(activation=293, activation_min=294, activation_max=295, ofm_zero_point=280)
ACT_C1 = dict(ofm_scale=36)
FORM_FILE = {"A0": "f_plain", "A1": "f_ctx", "A2": "f_ctx_self"}
# MLEK's own input, equivalence C manifest (refactor/firmware-modules 0f329a5): workloads.<model>.golden.input_sha256
MLEK_INPUT_SHA256 = {
    "kws_micronet_m": "236ea3d63f20b5953f20d9fcf542fe7c0cc56777a02233f575daa84ade0d393a",
    "ad_medium_int8": "89ce99eb736e413e302d18227b4eaa23530b3f9d1524a5210b813851e759165b",
    "mobilenet_v2_1.0_224_INT8": "be4e01717eced208f5e6ae99120a754290c1dcc6ae7b9d367e6eac6c265d3232",
    "vww4_128_128_INT8": "906d4afbc9d3853e8088ebc9041652ab30fa80dbc502624477b751357e783395",
    "wav2letter_pruned_int8": "dc8d69e0cf5cc4890ad4017c210ecce3e2d65271658a0d72db38dd842b4cd83f",
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def act_regs(stream: bytes) -> list[dict]:
    """Kernel type and activation/output-scaling registers at every kernel instruction."""
    reg0, reg1, out = {}, {}, []
    for off, word, ctrl, op in cms.instructions(stream):
        if ctrl == 1:
            reg1[op] = (word >> 16) << 32 | int.from_bytes(stream[off + 4:off + 8], "little")
        elif op in cms.KERNEL_OPS:
            k = {n: reg0.get(v) for n, v in ACT_C0.items()}
            k.update({n: reg1.get(v) for n, v in ACT_C1.items()})
            out.append(dict(k, kind=cms.KERNEL_OPS[op], offset=off))
        else:
            reg0[op] = word >> 16
    return out


def at(regs: list[dict], offsets: list[int]) -> list[dict | None]:
    by = {r["offset"]: r for r in regs}
    return [by.get(o) for o in offsets]


def fusion(cdir: pathlib.Path, man: dict, out: pathlib.Path) -> None:
    cache, res = {}, {}
    for c in man["candidates"]:
        rec = json.loads((cdir / f"{c['config']}.ra.json").read_text())
        RA.original(c["model"], c["cms_offsets"], cache)
        o = cache[c["model"]]
        r = dict(original=dict(vela_sha256=o["vela_sha256"], n_ethosu_ops=o["n_ethosu_ops"],
                               conv_act=at(act_regs(o["stream"]), c["cms_offsets"]) if o["stream"] is not None else None),
                 forms={})
        for label, f in FORM_FILE.items():
            p = cdir / f"{c['config']}_{f}.drwl.cms.bin"
            if not p.exists():
                r["forms"][label] = None
                continue
            stream = p.read_bytes()
            regs = act_regs(stream)
            row = (rec["forms"][label] or {}).get("conv_row") or {}
            offs = [int(x) for x in str(row.get("cms_offsets", "")).split()]
            r["forms"][label] = dict(cms_sha256=sha(stream), kernel_types=[k["kind"] for k in regs],
                                     conv_act=at(regs, offs))
        res[c["group"]] = r
        print(c["group"], "original", r["original"]["vela_sha256"][:16],
              {k: (v or {}).get("kernel_types") for k, v in r["forms"].items()}, flush=True)
    out.write_text(json.dumps(res, indent=1))


def clamp_hist(a: np.ndarray, lo: int, hi: int) -> dict:
    a = a.astype(np.int64).reshape(-1)
    return dict(n=int(a.size), at_lo=int((a == lo).sum()), at_hi=int((a == hi).sum()),
                inside=int(((a > lo) & (a < hi)).sum()), below_lo=int((a < lo).sum()), above_hi=int((a > hi).sum()),
                min=int(a.min()), max=int(a.max()), inside_share=float(((a > lo) & (a < hi)).mean()))


def preclamp(x: np.ndarray, src: dict) -> np.ndarray:
    """RA.numpy_conv1x1 without the final clip (same int64 accumulate and float64 requantisation)."""
    i, w, b, o = src["ifm"], src["w"], src["b"], src["ofm"]
    wt = np.frombuffer(w["data"], np.int8).reshape(w["shape"][0], -1).astype(np.int64)
    wzp = np.array(w["zp"] if len(w["zp"]) == wt.shape[0] else w["zp"] * wt.shape[0], np.int64)
    bias = np.frombuffer(b["data"], {2: np.int32, 9: np.int8, 7: np.int16, 4: np.int64}.get(b["type"], np.int32)).astype(np.int64)
    xi = x.reshape(-1, x.shape[-1]).astype(np.int64) - i["zp"][0]
    acc = xi @ (wt - wzp[:, None]).T + bias
    ws = np.array(w["scale"] if len(w["scale"]) == wt.shape[0] else w["scale"] * wt.shape[0], np.float64)
    return np.round(acc * (i["scale"][0] * ws / o["scale"][0])) + o["zp"][0]


def inputs_of(cdir: pathlib.Path, name: str, shapes: list) -> list[np.ndarray]:
    raw = (cdir / f"{name}.ifm.bin").read_bytes()
    xs, k = [], 0
    for s in shapes:
        n = int(np.prod(s))
        xs.append(np.frombuffer(raw[k:k + n], np.int8).reshape(s)); k += n
    assert k == len(raw), (name, k, len(raw))
    return xs


def quant(t: dict) -> dict:
    return dict(scale=t["scale"], zp=t["zp"])


def diagnose(cdir: pathlib.Path, man: dict, out: pathlib.Path, groups: list[str]) -> None:
    res = {}
    for c in man["candidates"]:
        if c["group"] not in groups:
            continue
        src = B.source_conv(c["model"], c["tflite_op_index"])
        rec = json.loads((cdir / f"{c['config']}.ra.json").read_text())
        lo, hi = RA.act_range(src)
        r = dict(model=c["model"], op_index=c["tflite_op_index"], activation=B.ACTS[src["activation"]],
                 act_range=[lo, hi], quant=dict(conv_ifm=quant(src["ifm"]), conv_ofm=quant(src["ofm"])), forms={})
        for label, form in RA.FORMS.items():
            name = f"{c['config']}_{form.lower()}"
            ts, ops, shapes = RA.tensors(src, form)
            xs = inputs_of(cdir, name, shapes)
            rt = RA.ref_tensors(str(cdir / f"{name}.tflite"), xs)
            pre = preclamp(rt["conv_in"], src)
            co, fin = rt["conv_out"], rt["final"]
            rc = rec["forms"][label]["refcheck"]
            r["forms"][label] = dict(
                tensors=dict(share_conv_out=("conv_out" if label != "A0" else "ofm") + " (BUILTIN_REF, after fused activation)",
                             share_final="ofm (graph output)"),
                quant=dict(graph_inputs=[quant(ts[k]) for k in range(len(shapes))], final=quant(ts[-1])),
                graph_inputs=[clamp_hist(x, -128, 127) for x in xs],
                conv_in=clamp_hist(rt["conv_in"], -128, 127),
                conv_out=clamp_hist(co, lo, hi), final=clamp_hist(fin, -128, 127),
                preclamp=dict(n=int(pre.size), below_lo=int((pre < lo).sum()), above_hi=int((pre > hi).sum()),
                              inside=int(((pre > lo) & (pre < hi)).sum()), p01=float(np.percentile(pre, 1)),
                              p50=float(np.percentile(pre, 50)), p99=float(np.percentile(pre, 99))),
                recomputed_equals_record=dict(
                    conv_out=float(((co > lo) & (co < hi)).mean()) == rc["conv_out_informative"],
                    final=float(((fin > -128) & (fin < 127)).mean()) == rc["final_informative"]),
                record=dict(conv_out_informative=rc["conv_out_informative"], final_informative=rc["final_informative"]))
        res[c["group"]] = r
        print(c["group"], {k: round(v["conv_out"]["inside_share"], 4) for k, v in r["forms"].items()}, flush=True)
    out.write_text(json.dumps(res, indent=1))


def model_conv_tensors(model: str, op_index: int, x: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Input and output of the model's own Conv on MLEK's input (BUILTIN_REF, all tensors preserved)."""
    import tflite
    from tflite_runtime.interpreter import Interpreter, OpResolverType
    path = B.MLEK / B.SOURCES[model] / f"{model}.tflite"
    m = tflite.Model.GetRootAsModel(path.read_bytes(), 0)
    op = m.Subgraphs(0).Operators(op_index)
    it = Interpreter(model_path=str(path), experimental_op_resolver_type=OpResolverType.BUILTIN_REF,
                     experimental_preserve_all_tensors=True)
    it.allocate_tensors()
    ins = it.get_input_details()
    assert len(ins) == 1, (model, len(ins))
    it.set_tensor(ins[0]["index"], np.frombuffer(x, ins[0]["dtype"]).reshape(ins[0]["shape"]))
    it.invoke()
    return it.get_tensor(op.Inputs(0)).copy(), it.get_tensor(op.Outputs(0)).copy()


def fixture(cdir: pathlib.Path, man: dict, eqc: pathlib.Path, o: pathlib.Path, groups: list[str]) -> None:
    import drwl  # noqa: F401  (packer dependency check)
    o.mkdir(parents=True, exist_ok=True)
    res = {}
    for c in man["candidates"]:
        if c["group"] not in groups:
            continue
        r = dict(model=c["model"], op_index=c["tflite_op_index"], form="A2")
        res[c["group"]] = r
        p = eqc / c["model"] / "ifm.bin"
        r["input_file"] = str(p)
        if not p.exists():
            r["missing"] = "input file"; continue
        raw = p.read_bytes()
        r["input_sha256"] = sha(raw)
        r["input_digest_ok"] = r["input_sha256"] == MLEK_INPUT_SHA256.get(c["model"])
        if not r["input_digest_ok"]:
            continue
        src = B.source_conv(c["model"], c["tflite_op_index"])
        x, y_model = model_conv_tensors(c["model"], c["tflite_op_index"], raw)
        r["x_shape"], r["conv_ifm_shape"] = list(x.shape), list(src["ifm"]["shape"])
        if tuple(x.shape) != tuple(src["ifm"]["shape"]):
            continue
        rec = json.loads((cdir / f"{c['config']}.ra.json").read_text())["forms"]["A2"]
        name = f"{c['config']}_f_ctx_self"
        mp = cdir / f"{name}.tflite"
        xs = [x.astype(np.int8), np.full(x.shape, src["ifm"]["zp"][0], np.int8)]
        rt = RA.ref_tensors(str(mp), xs)
        lo, hi = RA.act_range(src)
        co, fin = rt["conv_out"].astype(np.int64), rt["final"].astype(np.int64)
        npc = RA.numpy_conv1x1(rt["conv_in"], src)
        ref = rt["final"].astype(np.int8).tobytes()
        (o / f"{name}.mlek.ifm.bin").write_bytes(b"".join(v.tobytes() for v in xs))
        (o / f"{name}.mlek.ref_ofm.bin").write_bytes(ref)
        pk = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile",
                             str(B.PROFILE), "--format", "drwl", "--out", str(o / f"{name}.mlek.drwl"), "--ifm",
                             str(o / f"{name}.mlek.ifm.bin"), "--golden", str(o / f"{name}.mlek.ref_ofm.bin")],
                            capture_output=True, text=True)
        r.update(
            ifm_zero_point=src["ifm"]["zp"][0], act_range=[lo, hi],
            conv_in_equals_x=bool(np.array_equal(rt["conv_in"].reshape(-1), x.reshape(-1))),
            conv_out_vs_model_mismatch=int((co.reshape(-1) != y_model.astype(np.int64).reshape(-1)).sum()),
            numpy_vs_ref_max_abs=int(np.abs(npc - co.reshape(npc.shape)).max()),
            final_vs_conv_out_max_abs=int(np.abs(fin.reshape(-1) - co.reshape(-1)).max()),
            conv_out=clamp_hist(co, lo, hi), final=clamp_hist(fin, -128, 127), x=clamp_hist(x, -128, 127),
            conv_out_informative=float(((co > lo) & (co < hi)).mean()),
            final_informative=float(((fin > -128) & (fin < 127)).mean()),
            ref_ofm_sha256=sha(ref), pack_rc=pk.returncode, pack_log_tail=(pk.stdout + pk.stderr).strip().splitlines()[-3:])
        if pk.returncode == 0:
            meta = json.loads((o / f"{name}.mlek.drwl.json").read_text())
            stream = (o / f"{name}.mlek.drwl.cms.bin").read_bytes()
            r.update(vela_sha256=meta["vela_sha256"], cms_sha256=sha(stream), drwl_sha256=meta["blob_sha256"],
                     golden_sha256=meta["golden_sha256"], vela_equals_record=meta["vela_sha256"] == rec.get("vela_sha256"),
                     cms_equals_record=sha(stream) == rec.get("cms_sha256"))
        print(c["group"], round(r["conv_out_informative"], 4), round(r["final_informative"], 4),
              r["conv_out_vs_model_mismatch"], r.get("cms_equals_record"), flush=True)
    (o / "fixture.json").write_text(json.dumps(res, indent=1))


def vela_total(cdir: pathlib.Path, man: dict, out: pathlib.Path, groups: list[str]) -> None:
    """Vela's own performance summary of the A2 compile (same tflite, same options); its output must be the record's."""
    import csv
    import glob
    from pack_vela_workload import VELA_OPTIONS
    res = {}
    for c in man["candidates"]:
        if c["group"] not in groups:
            continue
        name = f"{c['config']}_f_ctx_self"
        rec = json.loads((cdir / f"{c['config']}.ra.json").read_text())["forms"]["A2"]
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["vela", str(cdir / f"{name}.tflite"), *VELA_OPTIONS, "--output-dir", d], check=True,
                           capture_output=True)
            blob = open(glob.glob(os.path.join(d, "*_vela.tflite"))[0], "rb").read()
            row = next(csv.DictReader(open(glob.glob(os.path.join(d, "*_summary_*.csv"))[0])))
        res[c["group"]] = dict(vela_sha256=sha(blob), vela_equals_record=sha(blob) == rec.get("vela_sha256"),
                               summary={k: row[k] for k in row if "cycles" in k or k in ("inference_time", "core_clock",
                                                                                          "system_config", "passes_after_fusing")})
        print(c["group"], res[c["group"]]["vela_equals_record"], res[c["group"]]["summary"], flush=True)
    out.write_text(json.dumps(res, indent=1))


def main(argv: list) -> None:
    man = json.loads(pathlib.Path(argv[2]).read_text())
    if argv[0] == "fusion":
        fusion(pathlib.Path(argv[1]), man, pathlib.Path(argv[3]))
    elif argv[0] == "diagnose":
        diagnose(pathlib.Path(argv[1]), man, pathlib.Path(argv[3]), argv[4:])
    elif argv[0] == "vela":
        vela_total(pathlib.Path(argv[1]), man, pathlib.Path(argv[3]), argv[4:])
    elif argv[0] == "fixture":
        fixture(pathlib.Path(argv[1]), man, pathlib.Path(argv[3]), pathlib.Path(argv[4]), argv[5:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
