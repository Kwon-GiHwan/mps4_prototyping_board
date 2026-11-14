#!/usr/bin/env python3
"""Stage 4AO-E (docs/plan/stage4aoe_characterization_plan.md): Elementwise, chaining-buffer and LUT workloads for the AO
study, plus the CPU-reference check behind the Stage 4AO act_none 1-LSB mismatch. Runs in the benchmark-runner
container. Imports stage4ao_models / make_op_model; edits neither and rebuilds nothing of theirs.

  python3 stage4aoe_models.py <out dir>                 Group A/B/C builds: <cfg>.tflite, .ifm.bin, .ref_ofm.bin, .drwl
                                                        (golden = TFLite reference kernels), <cfg>.aoe.json
  python3 stage4aoe_models.py <out dir> rounding <Stage 4AO workloads dir>   act_none diagnosis -> rounding.json
  python3 stage4aoe_models.py <out dir> identity <drwl>...   amendment A1: expected n_base per DRWL -> expected_identity.json
  python3 stage4aoe_models.py <out dir> refcheck <dir>...   for every <cfg>.drwl.json in the dirs: tflite_runtime default
                                                        (optimized) kernels vs BUILTIN_REF on the same IFMs -> refcheck.json

Inputs: every IFM is drawn once at H = 72 from AOE_SEED (graph-input order, one generator) and cut to H, so the H24 IFMs
are the first 24 rows of the H72 ones. The Conv parts reuse s4_conv_base's IFM, weights, bias and OFM scale
(stage4ao_models.base_tensors). Quantization (fixed): IFMs scale 1/128 zp 0; ADD OFM 2/128, MUL 1/128, ABS 1/128;
TANH OFM 1/128 zp 0, LOGISTIC 1/256 zp -128 (TFLite's fixed int8 ranges).
"""
from __future__ import annotations

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
import make_op_model as M  # noqa: E402
import stage4ao_models as AO  # noqa: E402
from stage4ao_models import graph, i8  # noqa: E402

AOE_SEED = 20261116
H_MAX, W, C = 72, 24, 96
PROFILE = HERE.parents[1] / "config" / "fi101_s013.json"
# name -> (group, H, description)
CONFIGS = {
    "s4aoe_add_h24": ("A", 24, "INT8 ADD, two IFMs"), "s4aoe_add_h72": ("A", 72, "INT8 ADD, two IFMs"),
    "s4aoe_mul_h24": ("A", 24, "INT8 MUL, two IFMs"), "s4aoe_mul_h72": ("A", 72, "INT8 MUL, two IFMs"),
    "s4aoe_abs_h24": ("A", 24, "INT8 ABS, one IFM"), "s4aoe_abs_h72": ("A", 72, "INT8 ABS, one IFM"),
    "s4aoe_conv_add_h24": ("B", 24, "Conv 1x1 (s4_conv_base tensors, no fused act) -> ADD residual"),
    "s4aoe_add_mul_h24": ("B", 24, "ADD -> MUL, three IFMs"),
    "s4aoe_tanh_h24": ("C", 24, "Conv 1x1 (no fused act) -> TANH"),
    "s4aoe_logistic_h24": ("C", 24, "Conv 1x1 (no fused act) -> LOGISTIC"),
}


def ifms(n: int, h: int) -> list[np.ndarray]:
    rng = np.random.default_rng(AOE_SEED)
    return [rng.integers(-128, 128, size=(1, H_MAX, W, C), dtype=np.int8)[:, :h].copy() for _ in range(n)]


def build(name: str) -> tuple[bytes, list[np.ndarray]]:
    """(tflite bytes, IFMs in graph-input order)."""
    _, h, _ = CONFIGS[name]
    ofm = (1, h, W, C)
    kind = name.split("_")[1]
    if kind in ("add", "mul") and not name.startswith("s4aoe_add_mul"):
        s_o = 2 / 128 if kind == "add" else 1 / 128
        m = graph(name, [i8("a", ofm, 1 / 128), i8("b", ofm, 1 / 128), i8("ofm", ofm, s_o)],
                  [dict(kind=kind, ins=[0, 1], outs=[2])])
        return m, ifms(2, h)
    if kind == "abs":
        return graph(name, [i8("a", ofm, 1 / 128), i8("ofm", ofm, 1 / 128)], [dict(kind="abs", ins=[0], outs=[1])]), ifms(1, h)
    if name == "s4aoe_add_mul_h24":
        m = graph(name, [i8("a", ofm, 1 / 128), i8("b", ofm, 1 / 128), i8("t", ofm, 2 / 128), i8("c", ofm, 1 / 128),
                         i8("ofm", ofm, 2 / 128)],
                  [dict(kind="add", ins=[0, 1], outs=[2]), dict(kind="mul", ins=[2, 3], outs=[4])])
        return m, ifms(3, h)
    x, wt, bias, s_out = AO.base_tensors(24)
    conv = dict(kind="conv", arg="NONE", ins=[0, 1, 2], outs=[3])
    if name == "s4aoe_conv_add_h24":
        m = graph(name, AO.conv_tensors(i8("res", ofm, 1 / 128), wt, bias, s_out) + [i8("ofm", ofm, 2 / 128)],
                  [conv, dict(kind="add", ins=[3, 4], outs=[5])])
        return m, [x, ifms(1, h)[0]]
    act, out = ("tanh", i8("ofm", ofm, 1 / 128)) if name == "s4aoe_tanh_h24" else ("logistic", i8("ofm", ofm, 1 / 256, -128))
    return graph(name, AO.conv_tensors(out, wt, bias, s_out), [conv, dict(kind=act, ins=[3], outs=[4])]), [x]


def run(model: str, xs: list[np.ndarray], ref: bool) -> list[bytes]:
    """OFM bytes of the original model on these IFMs (graph-input order): default kernels or BUILTIN_REF."""
    from tflite_runtime.interpreter import Interpreter, OpResolverType
    kw = dict(experimental_op_resolver_type=OpResolverType.BUILTIN_REF) if ref else {}
    it = Interpreter(model_path=model, **kw); it.allocate_tensors()
    for d, x in zip(it.get_input_details(), xs):
        it.set_tensor(d["index"], x.reshape(d["shape"]).astype(d["dtype"]))
    it.invoke()
    return [it.get_tensor(d["index"]).tobytes() for d in it.get_output_details()]


def compare(opt: bytes, ref: bytes, dtype=np.int8) -> dict:
    a, b = np.frombuffer(opt, dtype).astype(np.int64), np.frombuffer(ref, dtype).astype(np.int64)
    d = a != b
    return dict(n=int(a.size), opt_vs_ref=int(d.sum()), max_abs=int(np.abs(a - b).max()) if a.size else 0,
                ref_negative=int((b < 0).sum()), ref_min=int(b.min()), ref_max=int(b.max()),
                opt_sha256=hashlib.sha256(opt).hexdigest(), ref_sha256=hashlib.sha256(ref).hexdigest())


def vela_facts(model: pathlib.Path) -> dict:
    import cms
    from pack_vela_workload import VELA_OPTIONS, inspect_vela
    from stage4_inventory import tables, tflite_ops
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", str(model), *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"], check=True,
                       capture_output=True)
        t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
        out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        vops = tflite_ops(out)
        stream = inspect_vela(out)["cms"]
    return dict(vela_ops=[x[1] for x in vops], cpu_fallback=[x[1] for x in vops if not x[1].startswith("CUSTOM:ethos-u")],
                scheduled=[dict(operator=p["operator"], npu_cycles=p["npu_cycles"], mac_count=p["mac_count"])
                           for p in t["perf"]],
                perf_main=[{k: p.get(k) for k in ("id", "mac_cycles", "ao_cycles", "cmd_cycles", "ofm_block_h", "ofm_block_w",
                                                   "ofm_block_c", "ifm_block_h", "ifm_block_w", "ifm_block_c",
                                                   "ofm_ublock_h", "ofm_ublock_w", "ofm_ublock_c", "traversal")}
                           for p in t["perf_debug_main"]],
                perf_debug=[{k: p.get(k) for k in ("id", "ifm_memory", "ifm2_memory", "ofm_memory", "ifm_format",
                                                    "ofm_format", "weight_total_bytes", "cascade")} for p in t["perf_debug"]],
                kernels=AO.storage_of(stream), kernel_kinds=cms.kernel_types(stream), cms_len=len(stream),
                cms_sha256=hashlib.sha256(stream).hexdigest())


def make(name: str, o: pathlib.Path) -> dict:
    group, h, desc = CONFIGS[name]
    model, xs = build(name)
    mp = o / f"{name}.tflite"; mp.write_bytes(model)
    (o / f"{name}.ifm.bin").write_bytes(b"".join(x.tobytes() for x in xs))
    opt, ref = b"".join(run(str(mp), xs, False)), b"".join(run(str(mp), xs, True))
    (o / f"{name}.ref_ofm.bin").write_bytes(ref)
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile", str(PROFILE),
                        "--format", "drwl", "--out", str(o / f"{name}.drwl"), "--ifm", str(o / f"{name}.ifm.bin"),
                        "--golden", str(o / f"{name}.ref_ofm.bin")], capture_output=True, text=True)
    res = dict(config=name, group=group, h=h, description=desc, n_ofm=h * W * C, n_ifm=len(xs), aoe_seed=AOE_SEED,
               model_sha256=hashlib.sha256(model).hexdigest(), reference=compare(opt, ref), pack_rc=p.returncode,
               pack_log_tail=(p.stdout + p.stderr).strip().splitlines()[-4:], **vela_facts(mp))
    if p.returncode == 0:
        meta = json.loads((o / f"{name}.drwl.json").read_text())
        res.update(drwl_sha256=meta["blob_sha256"], golden_sha256=meta["golden_sha256"],
                   tflite_ofm_sha256=meta["tflite_ofm_sha256"], arena_size=meta["arena_size"], fast_size=meta["fast_size"])
    (o / f"{name}.aoe.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def refcheck(out: pathlib.Path, dirs: list[str]) -> list:
    """Existing DRWLs: the same IFMs (the --ifm file, or the packer's seeded draw) through default and BUILTIN_REF."""
    from pack_vela_workload import reference
    rows = []
    for d in dirs:
        for js in sorted(glob.glob(os.path.join(d, "*.drwl.json"))):
            meta = json.loads(open(js).read())
            model = meta["model"]
            if not os.path.exists(model):
                model = os.path.join(d, os.path.basename(model))
            if meta.get("ifm_file"):
                from tflite_runtime.interpreter import Interpreter
                it = Interpreter(model_path=model); it.allocate_tensors()
                raw, xs, off = open(meta["ifm_file"] if os.path.exists(meta["ifm_file"]) else
                                    os.path.join(d, os.path.basename(meta["ifm_file"])), "rb").read(), [], 0
                for dd in it.get_input_details():
                    n = int(np.prod(dd["shape"])) * np.dtype(dd["dtype"]).itemsize
                    xs.append(np.frombuffer(raw[off:off + n], dd["dtype"]).reshape(dd["shape"])); off += n
            else:
                xb, _ = reference(model, meta["seed"])
                from tflite_runtime.interpreter import Interpreter
                it = Interpreter(model_path=model); it.allocate_tensors()
                xs = [np.frombuffer(b, dd["dtype"]).reshape(dd["shape"]) for b, dd in zip(xb, it.get_input_details())]
            opt, ref = b"".join(run(model, xs, False)), b"".join(run(model, xs, True))
            dt = np.int16 if "int16" in os.path.basename(js) else np.int8
            r = compare(opt, ref, dt)
            rows.append(dict(dir=d, config=os.path.basename(js)[:-len(".drwl.json")], golden_sha256=meta["golden_sha256"],
                             golden_is_opt=meta["golden_sha256"] == r["opt_sha256"],
                             golden_is_ref=meta["golden_sha256"] == r["ref_sha256"], **r))
            print(rows[-1]["config"], r["opt_vs_ref"], r["max_abs"], flush=True)
    (out / "refcheck.json").write_text(json.dumps(rows, indent=1))
    return rows


def rounded_shift_right(acc: np.ndarray, shift: int, mode: str, dbl_rnd: int) -> np.ndarray:
    """TRM 102685-05 §3.6 rounded_shift_right, vectorised (modes used here: double_symmetric, natural, symmetric)."""
    R = 1 << (shift - 1)
    D = (1 << (30 - dbl_rnd)) if shift > 31 - dbl_rnd else 0
    R = {"double_symmetric": np.where(acc >= 0, R + D, R - D), "natural": np.full_like(acc, R),
         "symmetric": np.where(acc >= 0, R, R - 1)}[mode]
    return (acc + R) >> shift


def rounding(o: pathlib.Path, wl: str) -> dict:
    """Stage 4AO act_none diagnosis without the board: the Conv accumulators of the 24x24 Phase B/C tensors, the
    NPU's OFM rescale emulated from the TRM pseudo-code with the stream's NPU_SET_OFM_SCALE (decoded), against the
    packed golden (tflite default kernels) and BUILTIN_REF, for NONE / RELU / RELU6 clipping."""
    import cms
    x, wt, bias, _ = AO.base_tensors(24)
    acc = M.accumulators(AO.conv_spec(24, "NONE"), x, wt, bias).astype(np.int64)
    res = {}
    for cfg, lo_hi in (("s4ao_act_none", (-128, 127)), ("s4ao_act_relu", (0, 127)), ("s4ao_conv1x1_h24", (0, 120))):
        s = open(os.path.join(wl, f"{cfg}.drwl.cms.bin"), "rb").read()
        (off, word), = [(o_, w) for o_, w, c, op in cms.instructions(s) if c == 1 and op == 36]
        p = word >> 16
        shift, dbl, mode_id, scale = p & 63, (p >> 6) & 31, (p >> 13) & 7, int.from_bytes(s[off + 4:off + 8], "little")
        golden = np.frombuffer(open(os.path.join(wl, f"{cfg}.drwl.tflite_ofm.bin"), "rb").read(), np.int8).astype(np.int64)
        model = os.path.join(wl, f"{cfg}.tflite")
        ref = np.frombuffer(run(model, [x], True)[0], np.int8).astype(np.int64)
        row = dict(ofm_scale=dict(scale=scale, shift=shift, dbl_rnd=dbl, round_mode=mode_id), clip=lo_hi,
                   golden_vs_ref=int((golden != ref).sum()))
        for mode in ("double_symmetric", "natural", "symmetric"):
            npu = np.clip(rounded_shift_right(acc * scale, shift, mode, dbl), *lo_hi).reshape(-1)
            d = npu != golden
            row[mode] = dict(vs_golden=int(d.sum()), vs_ref=int((npu != ref).sum()),
                             npu_minus_golden=sorted({int(v) for v in (npu - golden)[d]}))
        res[cfg] = row
    (o / "rounding.json").write_text(json.dumps(res, indent=1))
    return res


def identity_manifest(o: pathlib.Path, drwls: list[str]) -> dict:
    """Amendment A1: the expected number of driver base addresses per DRWL, from the Vela model inside it (TFLM
    ethos_u/ethosu.cc: num_base_addr = custom-op inputs - 1 (the command stream) + outputs, at most 8), and the DRWL's
    placement word. -> expected_identity.json (REGIONCFG is computed from these on the analysis side)."""
    import drwl
    import tflite
    res = {}
    for p in drwls:
        blob = open(p, "rb").read()
        h = drwl.parse(blob)
        m = tflite.Model.GetRootAsModel(blob[h["model_off"]:h["model_off"] + h["model_len"]], 0)
        sg = m.Subgraphs(0)
        ops = [sg.Operators(i) for i in range(sg.OperatorsLength())]
        code = lambda op: m.OperatorCodes(op.OpcodeIndex()).CustomCode()
        eu = [op for op in ops if (code(op) or b"").startswith(b"ethos-u")]
        assert len(eu) == 1, f"{p}: {len(eu)} ethos-u custom ops"
        n_in, n_out = eu[0].InputsLength(), eu[0].OutputsLength()
        res[os.path.basename(p)[:-len(".drwl")]] = dict(custom_op_inputs=n_in, custom_op_outputs=n_out,
                                                       n_base=min(n_in - 1 + n_out, 8), placement=h["placement"],
                                                       drwl_sha256=hashlib.sha256(blob).hexdigest())
    (o / "expected_identity.json").write_text(json.dumps(res, indent=1))
    return res


def main(argv: list) -> None:
    o = pathlib.Path(argv[0]); o.mkdir(parents=True, exist_ok=True)
    if argv[1:2] == ["identity"]:
        print(json.dumps(identity_manifest(o, argv[2:]), indent=1))
        return
    if argv[1:2] == ["refcheck"]:
        refcheck(o, argv[2:])
        return
    if argv[1:2] == ["rounding"]:
        print(json.dumps(rounding(o, argv[2]), indent=1))
        return
    for name in CONFIGS:
        r = make(name, o)
        print(name, r["kernel_kinds"], "fallback", r["cpu_fallback"], "opt_vs_ref", r["reference"]["opt_vs_ref"],
              "pack", r["pack_rc"], [(p["ao_cycles"], p["ofm_block_h"], p["ofm_block_w"], p["ofm_block_c"]) for p in r["perf_main"]],
              flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
