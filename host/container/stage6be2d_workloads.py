#!/usr/bin/env python3
"""Stage 6B-E2D (evidence/stage6b/stage6be2d/contract.md §2): the four G12 board workloads, facts only.

  e2d_w1p1  A2 (MLEK options)                         a|b = 6B-B s6bb_g12 inputs, golden = A2 BUILTIN_REF output
  e2d_w1p0  A2 + --arena-cache-size=0                 same inputs and golden
  e2d_w0p0  A0 (MLEK options)                         IFM = A2's Conv input (CPU, first ADD), golden = A0 BUILTIN_REF output
  e2d_w0p1  e2d_w0p0 with DRWL header word 7 = 1 (drwl.with_placement): every other byte the same

  stage6be2d_workloads.py <A0 tflite> <A2 tflite> <A2 ifm.bin (a|b)> <out dir (new)>
Writes the DRWLs (+ .json meta, .cms.bin), <cfg>.ifm.bin, <cfg>.ref_ofm.bin, <cfg>.drwl.tflite_ofm.bin, expected_identity.json
and build.json (digests, CPU checks).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
import drwl  # noqa: E402
import stage4aoe_models as AOE  # noqa: E402
import stage6b_models as B  # noqa: E402

PACKS = {"e2d_w1p1": ("A2", []), "e2d_w1p0": ("A2", ["--vela-option=--arena-cache-size=0"]), "e2d_w0p0": ("A0", [])}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def conv_input(a2: str, ab: bytes) -> tuple[bytes, bytes]:
    from tflite_runtime.interpreter import Interpreter
    it = Interpreter(model_path=a2, experimental_preserve_all_tensors=True); it.allocate_tensors()
    ins = {d["name"]: d for d in it.get_input_details()}
    h = len(ab) // 2
    for n, part in (("a", ab[:h]), ("b", ab[h:])):
        it.set_tensor(ins[n]["index"], np.frombuffer(part, np.int8).reshape(ins[n]["shape"]))
    it.invoke()
    t = {x["name"]: x["index"] for x in it.get_tensor_details()}
    return it.get_tensor(t["ifm"]).tobytes(), it.get_tensor(t["conv_out"]).tobytes()


def main(a0: str, a2: str, ab_p: str, out: str) -> None:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=False)
    ab = pathlib.Path(ab_p).read_bytes()
    cin, conv_out = conv_input(a2, ab)
    model = {"A0": a0, "A2": a2}
    xs = {"A2": [np.frombuffer(ab[:len(ab) // 2], np.int8), np.frombuffer(ab[len(ab) // 2:], np.int8)],
          "A0": [np.frombuffer(cin, np.int8)]}
    refs = {f: b"".join(AOE.run(model[f], xs[f], True)) for f in model}
    opts = {f: b"".join(AOE.run(model[f], xs[f], False)) for f in model}
    build = dict(sources={f: dict(path=p, sha256=sha(pathlib.Path(p).read_bytes())) for f, p in model.items()},
                 a2_inputs_sha256=sha(ab), conv_input_sha256=sha(cin), conv_out_cpu_sha256=sha(conv_out),
                 a0_ref_equals_a2_conv_out=refs["A0"] == conv_out, a0_ref_vs_opt=AOE.compare(opts["A0"], refs["A0"]),
                 a2_ref_vs_opt=AOE.compare(opts["A2"], refs["A2"]), profile=str(B.PROFILE), configs={})
    for cfg, (form, extra) in PACKS.items():
        ifm = ab if form == "A2" else cin
        (o / f"{cfg}.ifm.bin").write_bytes(ifm)
        (o / f"{cfg}.ref_ofm.bin").write_bytes(refs[form])
        p = subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", model[form], "--profile", str(B.PROFILE),
                            "--format", "drwl", "--out", str(o / f"{cfg}.drwl"), "--ifm", str(o / f"{cfg}.ifm.bin"),
                            "--golden", str(o / f"{cfg}.ref_ofm.bin"), *extra], capture_output=True, text=True)
        if p.returncode != 0:
            build["configs"][cfg] = dict(pack_rc=p.returncode, log=(p.stdout + p.stderr)[-1500:]); continue
        (o / f"{cfg}.drwl.tflite_ofm.bin").write_bytes(opts[form])
        build["configs"][cfg] = dict(form=form, extra=extra, pack_rc=0)
    w = o / "e2d_w0p0.drwl"
    if w.exists():
        b1 = drwl.with_placement(w.read_bytes(), 1)
        (o / "e2d_w0p1.drwl").write_bytes(b1)
        for suf in (".ifm.bin", ".ref_ofm.bin", ".drwl.tflite_ofm.bin", ".drwl.cms.bin"):
            (o / f"e2d_w0p1{suf}").write_bytes((o / f"e2d_w0p0{suf}").read_bytes())
        build["configs"]["e2d_w0p1"] = dict(form="A0", extra=["drwl.with_placement(1)"], pack_rc=0)
    for cfg in build["configs"]:
        d = o / f"{cfg}.drwl"
        if d.exists():
            blob = d.read_bytes(); h = drwl.parse(blob)
            meta = json.loads((o / f"e2d_w0p0.drwl.json" if cfg == "e2d_w0p1" else o / f"{cfg}.drwl.json").read_text())
            build["configs"][cfg].update(drwl_sha256=sha(blob), placement=h["placement"], model_len=h["model_len"],
                                         n_in=h["n_in"], n_out=h["n_out"], vela_sha256=meta["vela_sha256"],
                                         cms_sha256=sha((o / f"{cfg}.drwl.cms.bin").read_bytes()), arena_size=meta["arena_size"],
                                         fast_size=meta["fast_size"], ifm_off=meta.get("ifm_off"), ofm_off=meta.get("ofm_off"),
                                         inputs=meta.get("inputs") or meta.get("ifms"), outputs=meta.get("outputs") or meta.get("ofms"),
                                         golden_sha256=sha((o / f"{cfg}.ref_ofm.bin").read_bytes()),
                                         ifm_sha256=sha((o / f"{cfg}.ifm.bin").read_bytes()))
    ident = AOE.identity_manifest(o, [str(o / f"{c}.drwl") for c in build["configs"] if (o / f"{c}.drwl").exists()])
    (o / "expected_identity.json").write_text(json.dumps(ident, indent=1, sort_keys=True))
    build["expected_identity"] = ident
    (o / "build.json").write_text(json.dumps(build, indent=1, sort_keys=True, default=str))
    print(json.dumps({c: {k: v for k, v in x.items() if k in ("drwl_sha256", "placement", "vela_sha256", "cms_sha256", "pack_rc")}
                      for c, x in build["configs"].items()}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
