#!/usr/bin/env python3
"""Stage 4C-1 (evidence/stage4c1/contract.md): channel variants derived from the Stage 4 base operators, so that every
channel the variant shares with its base has the same input, weights, bias and quantization. Runs in the
benchmark-runner container.

  python3 stage4c_models.py <out dir>      -> <name>.tflite, <name>.json, <name>.ifm.bin per variant

Derivation (owner 2026-11-10): a smaller variant drops the last channels; a larger one appends channels drawn from
EXTRA_SEED (weights, bias and, for DWConv, the IFM channel) with the module's ranges; the OFM scale is the base's (no
per-shape calibration); per-channel weight scales are the module's constant, so the base channels keep theirs.
The IFM is written out and packed with --ifm, so the CPU reference runs on exactly this input.
"""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import make_op_model as M  # noqa: E402

EXTRA_SEED = 20261110
VARIANTS = {   # name: (base op in make_op_model.OPS, channels)
    "s4c_conv_cout94": ("s4_conv_base", 94), "s4c_conv_cout97": ("s4_conv_base", 97),
    "s4c_dw_c142": ("s4_dw_base", 142), "s4c_dw_c145": ("s4_dw_base", 145),
}
# Stage 4C-2 (evidence/stage4c2/contract.md): Conv input channels. The 1x1 Conv base's IFM and weights are extended once
# to CIN_MAX input channels from CIN_SEED (base channels first, unchanged) and every config takes the first Cin of them,
# so channels shared by two configs carry the same values; bias and the OFM scale are the base's (Cout stays 96).
CIN_SEED, CIN_MAX = 20261111, 128
CIN_VARIANTS = {"s4c2_conv_cin16": 16, "s4c2_conv_cin32": 32, "s4c2_conv_cin64": 64, "s4c2_conv_cin128": 128,
                # compile-only sweep (owner 2026-11-11): where Vela's schedule changes between Cin 32 and 64
                "s4c2_conv_cin40": 40, "s4c2_conv_cin48": 48, "s4c2_conv_cin56": 56}


def fit(a: np.ndarray, n: int, axis: int, rng, lo: int, hi: int) -> np.ndarray:
    """a cut to n along axis, or extended with rng draws in [lo, hi)."""
    if n <= a.shape[axis]:
        return np.take(a, range(n), axis=axis)
    shape = list(a.shape); shape[axis] = n - a.shape[axis]
    return np.concatenate([a, rng.integers(lo, hi, size=shape, dtype=a.dtype)], axis=axis)


def derive(name: str) -> tuple[bytes, dict, bytes]:
    base, n = VARIANTS[name]
    spec0 = M.OPS[base]
    x, wt, bias, s_out, _ = M.arrays(base)
    rng = np.random.default_rng(EXTRA_SEED)
    if spec0["kind"] == "conv":                       # Cout: weights (cout, 1, 1, cin), bias (cout,)
        spec = dict(spec0, cout=n)
        wt = fit(wt, n, 0, rng, -127, 128)
        bias = fit(bias, n, 0, rng, -1024, 1025)
    else:                                             # DWConv: IFM (1, h, w, c), weights (1, k, k, c), bias (c,)
        spec = dict(spec0, ifm=spec0["ifm"][:3] + (n,))
        x = fit(x, n, 3, rng, -128, 128)
        wt = fit(wt, n, 3, rng, -127, 128)
        bias = fit(bias, n, 0, rng, -1024, 1025)
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    model, meta = M.serialize(name, spec, wt, bias, s_out, acc_max)
    meta.update(base=base, extra_seed=EXTRA_SEED, ofm_scale_from=base,
                acc_abs_max_note="of this variant; the OFM scale is the base's, so values beyond it saturate")
    return model, meta, x.tobytes()


def derive_cin(name: str) -> tuple[bytes, dict, bytes]:
    cin = CIN_VARIANTS[name]
    spec0 = M.OPS["s4_conv_base"]
    x, wt, bias, s_out, _ = M.arrays("s4_conv_base")   # IFM (1, 24, 24, 16), weights (96, 1, 1, 16)
    rng = np.random.default_rng(CIN_SEED)
    x = np.take(fit(x, CIN_MAX, 3, rng, -128, 128), range(cin), axis=3)
    wt = np.take(fit(wt, CIN_MAX, 3, rng, -127, 128), range(cin), axis=3)
    spec = dict(spec0, ifm=spec0["ifm"][:3] + (cin,))
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    model, meta = M.serialize(name, spec, wt, bias, s_out, acc_max)
    meta.update(base="s4_conv_base", cin_seed=CIN_SEED, cin_max=CIN_MAX, ofm_scale_from="s4_conv_base",
                acc_abs_max_note="of this config; the OFM scale is the base's, so values beyond it saturate")
    return model, meta, x.tobytes()


# Stage 4K (docs/plan/stage4k_conv_kernel_plan.md): 3x3 Conv (24x24, Cout 96, stride 1, SAME, RELU6) at the 4C-2 Cin
# values. Same IFM bytes as the 1x1 config of that Cin (first Cin channels of the CIN_SEED extension); weights
# (96, 3, 3, Cin): centre tap = the 1x1 weights of that Cin, the 8 other taps drawn once at Cin 128 from K3_SEED and cut
# to Cin; bias and OFM scale = the base's (as every 4C-2 config), so all ten configs share one OFM quantization.
K3_SEED = 20261114
K3_VARIANTS = {f"s4k_conv3x3_cin{c}": c for c in (16, 32, 40, 48, 64)}
# compile-only control: the 1x1 configs written with SAME padding (the 1x1 data use VALID; for 1x1 they are the same op)
K1_SAME_VARIANTS = {f"s4k_conv1x1same_cin{c}": c for c in (16, 32, 40, 48, 64)}


def cin_arrays(cin: int):
    """IFM (1, 24, 24, cin) and 1x1 weights (96, 1, 1, cin) of the 4C-2 rule; bias and OFM scale of s4_conv_base."""
    x, wt, bias, s_out, _ = M.arrays("s4_conv_base")
    rng = np.random.default_rng(CIN_SEED)
    x = np.take(fit(x, CIN_MAX, 3, rng, -128, 128), range(cin), axis=3)
    wt = np.take(fit(wt, CIN_MAX, 3, rng, -127, 128), range(cin), axis=3)
    return x, wt, bias, s_out


def k3_weights(wt1: np.ndarray) -> np.ndarray:
    """(96, 3, 3, cin) with the 1x1 weights at the centre tap and K3_SEED draws (made at Cin 128, cut) elsewhere."""
    cout, cin = wt1.shape[0], wt1.shape[3]
    w = np.random.default_rng(K3_SEED).integers(-127, 128, size=(cout, 3, 3, CIN_MAX), dtype=np.int8)[..., :cin].copy()
    w[:, 1, 1, :] = wt1[:, 0, 0, :]
    return w


def k3_spec(cin: int) -> dict:
    return dict(M.OPS["s4_conv_base"], ifm=(1, 24, 24, cin), k=3, padding="SAME")


def derive_k3(name: str) -> tuple[bytes, dict, bytes]:
    cin = K3_VARIANTS[name]
    x, wt1, bias, s_out = cin_arrays(cin)
    wt, spec = k3_weights(wt1), k3_spec(cin)
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    model, meta = M.serialize(name, spec, wt, bias, s_out, acc_max)
    meta.update(base="s4_conv_base", cin_seed=CIN_SEED, cin_max=CIN_MAX, k3_seed=K3_SEED, ofm_scale_from="s4_conv_base",
                acc_abs_max_note="of this config; the OFM scale is the base's, so values beyond it saturate")
    return model, meta, x.tobytes()


def derive_k1_same(name: str) -> tuple[bytes, dict, bytes]:
    cin = K1_SAME_VARIANTS[name]
    x, wt, bias, s_out = cin_arrays(cin)
    spec = dict(M.OPS["s4_conv_base"], ifm=(1, 24, 24, cin), padding="SAME")
    acc_max = int(np.abs(M.accumulators(spec, x, wt, bias)).max())
    model, meta = M.serialize(name, spec, wt, bias, s_out, acc_max)
    meta.update(base="s4_conv_base", cin_seed=CIN_SEED, cin_max=CIN_MAX, ofm_scale_from="s4_conv_base",
                note="compile-only control: same tensors as the 1x1 VALID config of this Cin, padding SAME")
    return model, meta, x.tobytes()


def main_k3(out):
    """Stage 4K: the 1x1 configs (s4_conv_base, 4C-2 builds) rebuilt for a byte check, the 3x3 configs and the 1x1 SAME
    control, all compile-checked by stage4_compile.check (Gate B, DRWL with --ifm)."""
    import stage4_compile as SC
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    r = SC.check("s4_conv_base", o)
    print("s4_conv_base", "GATE_B", r["gate_b"], r["drwl_sha256"][:12], flush=True)
    for name in ("s4c2_conv_cin32", "s4c2_conv_cin40", "s4c2_conv_cin48", "s4c2_conv_cin64"):
        model, meta, ifm = derive_cin(name)
        r = SC.check(name, o, built=(model, meta, ifm), kind="conv")
        print(name, "GATE_B", r["gate_b"], r["drwl_sha256"][:12], flush=True)
    for table, fn in ((K3_VARIANTS, derive_k3), (K1_SAME_VARIANTS, derive_k1_same)):
        for name in table:
            model, meta, ifm = fn(name)
            r = SC.check(name, o, built=(model, meta, ifm), kind="conv")
            print(name, "GATE_B", r["gate_b"], r["checks"], meta["n_mac"], r["ofm_block"], r["ifm_block"],
                  r["ofm_ublock"], r["traversal"], r["n_kernels"], r["vela_npu_cycles"], flush=True)


def main_cin(out):
    """Stage 4C-2: the four Cin configs compile-checked like the 4C-1 variants (Gate B, DRWL with --ifm)."""
    import stage4_compile as SC
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    r = SC.check("s4_conv_base", o)
    print("s4_conv_base", "GATE_B", r["gate_b"], r["drwl_sha256"][:12])
    for name in CIN_VARIANTS:
        model, meta, ifm = derive_cin(name)
        r = SC.check(name, o, built=(model, meta, ifm), kind="conv")
        print(name, "GATE_B", r["gate_b"], r["checks"], meta["input_shape"], meta["n_mac"], r["ofm_block"],
              r["ifm_block"], r["ofm_ublock"], r["traversal"], r["n_kernels"], r["vela_npu_cycles"], flush=True)


def main(out):
    """Builds the variants and compile-checks them with stage4_compile.check (Gate B, DRWL with --ifm); the two bases
    are rebuilt the Stage 4 way into the same folder for a byte comparison with evidence/stage4/workloads."""
    import stage4_compile as SC
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    for base in ("s4_conv_base", "s4_dw_base"):
        r = SC.check(base, o)
        print(base, "GATE_B", r["gate_b"], r["drwl_sha256"][:12])
    for name in VARIANTS:
        model, meta, ifm = derive(name)
        r = SC.check(name, o, built=(model, meta, ifm), kind=M.OPS[VARIANTS[name][0]]["kind"])
        print(name, "GATE_B", r["gate_b"], r["checks"], meta["input_shape"], meta["output_shape"], meta["n_mac"],
              r["ofm_block"], r["ofm_ublock"], r["n_kernels"], r["vela_npu_cycles"], flush=True)


if __name__ == "__main__":
    {"cin": main_cin, "k3": main_k3}.get((sys.argv[2:] or [""])[0], main)(sys.argv[1])
