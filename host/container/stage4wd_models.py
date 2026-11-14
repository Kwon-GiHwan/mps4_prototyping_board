#!/usr/bin/env python3
"""Stage 4WD (docs/plan/stage4wd_characterization_plan.md): weight-decoder candidates. Runs in the benchmark-runner
container. Imports make_op_model / stage4ao_models / stage4_compile; edits none of them and rebuilds nothing of theirs.

  python3 stage4wd_models.py <out dir> scan          Vela block choice for the 1x1 base rule at H = 18..36, W = 24
  python3 stage4wd_models.py <out dir>               Experiment A (weight values) and B (partial blocks) candidates:
                                                     stage4_compile.check (Gate B, DRWL), CPU references (default vs
                                                     BUILTIN_REF), <cfg>.wd.json

Experiment A — weight values only: the 24x24 1x1 Conv of Stage 4AO (IFM, bias, OFM scale and RELU6 of s4_conv_base,
  SAME) with the weights replaced: 'sparse75' / 'sparse90' (the base weights with 75 % / 90 % set to 0 by a WD_SEED
  mask), 'small' (uniform [-3, 3] from WD_SEED). Reference 'dense' = s4ao_conv1x1_h24. Same shape, so the same Vela
  schedule is expected; the encoded stream length is what should change.
Experiment B — blocks against elements: the base tensors at H = 23, 32, 34 (with s4ao_conv1x1_h24 / _h36): Vela keeps
  the 6x12x96 block at all five; partial block rows give equal block counts at different N. IFM rows:
  stage4ao_models.base_tensors (AO_SEED extension).
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

WD_SEED = 20261117
A_VARIANTS = {"s4wd_w_sparse75": "sparse75", "s4wd_w_sparse90": "sparse90", "s4wd_w_small": "small"}
# 'dense' = Stage 4AO's s4ao_conv1x1_h24 (same tensors), reused byte for byte as the A and B reference
B_H = (23, 32, 34)      # with Stage 4AO's H24 / H36: block 6x12x96 at all five (wd_block_scan.json); spatial blocks
                        # 8 (H23, H24) and 12 (H32, H34, H36) at different N
B_VARIANTS = {f"s4wd_h{h}": h for h in B_H}


def weights(kind: str, wt: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(WD_SEED)
    if kind == "dense":
        return wt.copy()
    if kind == "small":
        return rng.integers(-3, 4, size=wt.shape, dtype=np.int8)
    keep = rng.random(wt.shape) >= {"sparse75": 0.75, "sparse90": 0.90}[kind]
    return np.where(keep, wt, 0).astype(np.int8)


def derive(name: str) -> tuple[bytes, dict, bytes]:
    h = B_VARIANTS.get(name, 24)
    x, wt, bias, s_out = AO.base_tensors(h)
    w = weights(A_VARIANTS.get(name, "dense"), wt)
    spec = AO.conv_spec(h, "RELU6")
    acc_max = int(np.abs(M.accumulators(spec, x, w, bias)).max())
    model, meta = M.serialize(name, spec, w, bias, s_out, acc_max)
    meta.update(base="s4_conv_base", wd_seed=WD_SEED, weight_kind=A_VARIANTS.get(name, "dense"),
                weight_zero_share=float((w == 0).mean()), ofm_scale_from="s4_conv_base")
    return model, meta, x.tobytes()


def references(model_path: str, ifm: bytes, shape) -> dict:
    from tflite_runtime.interpreter import Interpreter, OpResolverType
    outs = {}
    for tag, kw in (("opt", {}), ("ref", dict(experimental_op_resolver_type=OpResolverType.BUILTIN_REF))):
        it = Interpreter(model_path=model_path, **kw); it.allocate_tensors()
        d = it.get_input_details()[0]
        it.set_tensor(d["index"], np.frombuffer(ifm, np.int8).reshape(d["shape"])); it.invoke()
        outs[tag] = it.get_tensor(it.get_output_details()[0]["index"]).tobytes()
    a, b = np.frombuffer(outs["opt"], np.int8), np.frombuffer(outs["ref"], np.int8)
    return dict(opt_vs_ref=int((a != b).sum()), opt_sha256=hashlib.sha256(outs["opt"]).hexdigest(),
                ref_sha256=hashlib.sha256(outs["ref"]).hexdigest())


def scan(o: pathlib.Path) -> list:
    from pack_vela_workload import VELA_OPTIONS
    from stage4_inventory import tables
    rows = []
    for h in range(18, 37):
        x, wt, bias, s_out = AO.base_tensors(h)
        model, _ = M.serialize(f"scan_h{h}", AO.conv_spec(h, "RELU6"), wt, bias, s_out, 0)
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "m.tflite"; p.write_bytes(model)
            subprocess.run(["vela", str(p), *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"], check=True,
                           capture_output=True)
            t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
        mq = t["perf_debug_main"][0]
        hwc = lambda pre: "x".join(mq.get(f"{pre}_{a}", "") for a in "hwc")
        rows.append(dict(h=h, w=24, n_ofm=h * 24 * 96, ofm_block=hwc("ofm_block"), ifm_block=hwc("ifm_block"),
                         traversal=mq.get("traversal"), vela_npu_cycles=t["perf"][0]["npu_cycles"]))
        print(rows[-1], flush=True)
    (o / "wd_block_scan.json").write_text(json.dumps(rows, indent=1))
    return rows


def main(argv: list) -> None:
    o = pathlib.Path(argv[0]); o.mkdir(parents=True, exist_ok=True)
    if argv[1:2] == ["scan"]:
        scan(o)
        return
    import stage4_compile as SC
    for name in [*A_VARIANTS, *B_VARIANTS]:
        model, meta, ifm = derive(name)
        r = SC.check(name, o, built=(model, meta, ifm), kind="conv")
        ref = references(str(o / f"{name}.tflite"), ifm, meta["input_shape"])
        (o / f"{name}.wd.json").write_text(json.dumps(dict(config=name, reference=ref, weight_kind=meta["weight_kind"],
                                                           weight_zero_share=meta["weight_zero_share"]), indent=1))
        print(name, "GATE_B", r["gate_b"], r["ofm_block"], r["traversal"], r["n_kernels"], "weight_bytes",
              r["weight_bytes"], "zero", round(meta["weight_zero_share"], 3), "opt_vs_ref", ref["opt_vs_ref"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
