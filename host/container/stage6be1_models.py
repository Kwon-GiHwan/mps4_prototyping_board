#!/usr/bin/env python3
"""Stage 6B-E1 (evidence/stage6b/stage6be1/contract.md): 1x1 Conv candidates of the fixed grid, compiled with the MLEK
Vela options; facts only (every selection / pass-fail rule is in host/analysis/stage6be1.py).

  stage6be1_models.py grid  <out.json>                      static facts of all 200 grid candidates (Vela only)
  stage6be1_models.py build <out dir> <name>...             two independent builds per name: tflite, golden, DRWL
"""
from __future__ import annotations

import glob
import hashlib
import itertools
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
import make_op_model as M  # noqa: E402
import stage4aoe_models as AOE  # noqa: E402
import stage6b_models as B  # noqa: E402

E1_SEED = 20261116
CINS = (24, 40, 72, 80, 88, 100, 136, 200)
HWS = ((7, 7), (8, 8), (9, 9), (13, 13), (14, 14))
COUTS = (48, 80, 96, 112, 176)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def name_of(cin: int, h: int, w: int, cout: int) -> str:
    return f"e1_c{cin}_h{h}w{w}_o{cout}"


def parse(name: str) -> tuple[int, int, int, int]:
    _, c, hw, o = name.split("_")
    h, w = hw[1:].split("w")
    return int(c[1:]), int(h), int(w), int(o[1:])


def tensors(cin: int, h: int, w: int, cout: int):
    spec = dict(kind="conv", ifm=(1, h, w, cin), cout=cout, k=1, padding="VALID", act="RELU6")
    rng = np.random.default_rng(E1_SEED)
    wt = rng.integers(-127, 128, size=(cout, 1, 1, cin), dtype=np.int8)
    bias = rng.integers(-1024, 1025, size=(cout,), dtype=np.int32)
    x = np.random.default_rng(E1_SEED).integers(-128, 128, size=(1, h, w, cin), dtype=np.int8)
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    return spec, wt, bias, x, acc_max * M.S_IN * M.S_W / 127, acc_max


def model(name: str) -> tuple[bytes, np.ndarray]:
    spec, wt, bias, x, s_out, acc_max = tensors(*parse(name))
    blob, _ = M.serialize(name, spec, wt, bias, s_out, acc_max)
    return blob, x


def vela_facts(mp: pathlib.Path) -> dict:
    """Vela output digest, ethos-u op count, Conv kernel registers at the debug-DB Conv row's command offsets."""
    import tflite
    import cms_regs
    from pack_vela_workload import VELA_OPTIONS, extract_cms
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", str(mp), *VELA_OPTIONS, "--output-dir", d], check=True, capture_output=True)
        blob = open(glob.glob(os.path.join(d, "*_vela.tflite"))[0], "rb").read()
    m = tflite.Model.GetRootAsModel(blob, 0); g = m.Subgraphs(0)
    eu = [g.Operators(k) for k in range(g.OperatorsLength())
          if (m.OperatorCodes(g.Operators(k).OpcodeIndex()).CustomCode() or b"").startswith(b"ethos-u")]
    stream = extract_cms(m.Buffers(g.Tensors(eu[0].Inputs(0)).Buffer()).DataAsNumpy().tobytes()) if len(eu) == 1 else b""
    rows = B.inventory_rows(mp)
    convs = [r for r in rows if r.get("npu_op") == "Conv2D"]
    ks = {k["offset"]: k for k in cms_regs.kernels(stream)} if stream else {}
    offs = [int(x) for x in convs[0]["cms_offsets"].split()] if len(convs) == 1 else []
    kern = [ks.get(o) for o in offs]
    return dict(vela_sha256=sha(blob), n_ethosu_ops=len(eu), cms_sha256=sha(stream),
                rows=[{k: r[k] for k in ("npu_op", "tflite_op", "cms_offsets", "mac_count", "vela_op_cycles", "cpu",
                                         "traversal", "ofm_block", "ifm_block", "ofm_ublock", "kernel", "stride",
                                         "npu_ifm_hwc", "npu_ofm_hwc", "ifm_memory", "ofm_memory", "fused_names",
                                         "vela_mac_cycles", "vela_npu_cycles")} for r in rows],
                kernels=[None if k is None else dict(ofm=[k["ofm_height_m1"] + 1, k["ofm_width_m1"] + 1, k["ofm_depth_m1"] + 1],
                                                     ifm_depth=k["ifm_depth_m1"] + 1, offset=k["offset"],
                                                     kind=k["kind"]) for k in kern],
                kernel_kinds=[k["kind"] for k in cms_regs.kernels(stream)] if stream else [])


def grid(out: str) -> None:
    res = {}
    with tempfile.TemporaryDirectory() as d:
        for cin, (h, w), cout in itertools.product(CINS, HWS, COUTS):
            name = name_of(cin, h, w, cout)
            blob, _ = model(name)
            mp = pathlib.Path(d) / f"{name}.tflite"; mp.write_bytes(blob)
            try:
                res[name] = dict(model_sha256=sha(blob), **vela_facts(mp))
            except Exception as e:                    # recorded, never dropped silently
                res[name] = dict(model_sha256=sha(blob), error=repr(e))
            r = res[name]
            print(name, r.get("n_ethosu_ops"), [x["traversal"] for x in r.get("rows", []) if x["npu_op"] == "Conv2D"],
                  len(r.get("kernels", [])), flush=True)
    pathlib.Path(out).write_text(json.dumps(res, indent=1))


def build_one(name: str, o: pathlib.Path) -> dict:
    import drwl
    blob, x = model(name)
    mp = o / f"{name}.tflite"; mp.write_bytes(blob)
    (o / f"{name}.ifm.bin").write_bytes(x.tobytes())
    ref = b"".join(AOE.run(str(mp), [x], True))
    opt = b"".join(AOE.run(str(mp), [x], False))
    (o / f"{name}.ref_ofm.bin").write_bytes(ref)
    p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(mp), "--profile", str(B.PROFILE),
                        "--format", "drwl", "--out", str(o / f"{name}.drwl"), "--ifm", str(o / f"{name}.ifm.bin"),
                        "--golden", str(o / f"{name}.ref_ofm.bin")], capture_output=True, text=True)
    res = dict(name=name, model_sha256=sha(blob), ifm_sha256=sha(x.tobytes()), ref_sha256=sha(ref),
               reference=AOE.compare(opt, ref), pack_rc=p.returncode, pack_log_tail=(p.stdout + p.stderr).strip().splitlines()[-3:],
               **vela_facts(mp))
    if p.returncode == 0:
        meta = json.loads((o / f"{name}.drwl.json").read_text())
        h = drwl.parse((o / f"{name}.drwl").read_bytes())
        res.update(drwl_sha256=meta["blob_sha256"], golden_sha256=meta["golden_sha256"], drwl_vela_sha256=meta["vela_sha256"],
                   drwl_cms_sha256=sha((o / f"{name}.drwl.cms.bin").read_bytes()), fast_size=meta["fast_size"],
                   arena_size=meta["arena_size"], model_len=h["model_len"], placement=h["placement"], n_in=h["n_in"],
                   n_out=h["n_out"], ta_profile=meta.get("ta_profile"),
                   fits=meta["fast_size"] <= B.LIMITS["fast_size"] and meta["arena_size"] <= B.LIMITS["arena_size"]
                   and h["model_len"] + meta["arena_size"] <= B.LIMITS["model_region"])
    return res


def build(out: str, names: list[str]) -> None:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    res = {}
    for name in names:
        first = build_one(name, o)
        with tempfile.TemporaryDirectory() as d:
            second = build_one(name, pathlib.Path(d))
        keys = ("model_sha256", "ifm_sha256", "ref_sha256", "vela_sha256", "cms_sha256", "drwl_sha256", "rows", "kernels")
        res[name] = dict(first, second={k: second.get(k) for k in keys},
                         deterministic=all(first.get(k) == second.get(k) for k in keys))
        print(name, first.get("pack_rc"), first.get("fits"), res[name]["deterministic"], first.get("drwl_sha256", "")[:12], flush=True)
    (o / "build.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "grid":
        grid(sys.argv[2])
    elif sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3:])
    else:
        raise SystemExit(__doc__)
