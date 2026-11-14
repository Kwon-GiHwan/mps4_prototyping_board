#!/usr/bin/env python3
"""Stage 4AO (docs/plan/stage4ao_characterization_plan.md, contract draft evidence/stage4ao/contract_draft.md): AO
(activation output) activity of the 1x1 Conv against the OFM element count. TA profile 1, driver runner image 70090f1
(DDR/EXT placement), Vela 5.0.0 with MLEK's options. Board-free parts: phase-a, static, predict. judge / repro-gate /
boot-check are for a board run under a frozen contract and are exercised here only by tests.

  python3 host/analysis/stage4ao.py phase-a <out dir>                    Stage 4K AO re-analysis from the raw RUNs
  python3 host/analysis/stage4ao.py static <workloads dir> <out dir>     Phase B/C/D compile facts, comparability
  python3 host/analysis/stage4ao.py predict <workloads dir> <out dir>    M1-M4 per Phase B / C config
  python3 host/analysis/stage4ao.py repro-gate <campaign root> <workloads dir> [<boot-369 wfe copy>]
  python3 host/analysis/stage4ao.py boot-check <campaign root> <workloads dir> <config> [<reference capabilities.json>]
  python3 host/analysis/stage4ao.py judge <campaign root> <workloads dir> <predictions.json> <out dir> <sweep,configs>
                                          [<act,configs> [<boot-369 wfe copy>]]
M3 block count (fixed before the board): sum over the kernel instructions of ceil(H / block_h) * ceil(W / block_w) *
ceil(kernel OFM slice depth / block_c), from the compiled command stream (cms_regs.kernels) and Vela's OFM block.

Official basis (Arm Ethos-U85 TRM 102685 issue 05, §4.2 Table 4-11): U85-1024 has NUM_SU = 16; AB->OB with an 8-bit
OFM runs at 1 element per SU per cycle = 16 elements/cycle (16-bit OFM: 1/2, DMA-limited). "AO_Relative_Throughput"
below is N_OFM / AO_ACTIVE / 16, a count-to-cycle ratio, not a measured SU occupancy or lane utilisation.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4k as K  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
SU_RATE = 16                     # TRM 102685-05 Table 4-11: NUM_SU 16 x 1 element/SU/cycle (AB -> OB_8)
K4_ROOT = REPO / "evidence/stage4k/raw/evsweep_s4k_run"
BASE = "s4_conv_base"            # Stage 4K boot 1 blob (VALID 1x1; byte-identical command stream to s4ao_conv1x1_h24)
REF_H = "s4ao_conv1x1_h24"       # Phase B/C reference (SAME 1x1 at 24x24, RELU6)
ORIGINAL = ["s4ao_conv1x1_h12", "s4ao_conv1x1_h24", "s4ao_conv1x1_h36", "s4ao_conv1x1_h48"]
REVISION = ["s4ao_conv1x1_h42", "s4ao_conv1x1_h54", "s4ao_conv1x1_h72"]
ACTS = ["s4ao_act_none", "s4ao_act_relu"]
PROBES = ["s4ao_lut_tanh", "s4ao_lut_logistic", "s4ao_conv_int16", "s4ao_ew_add", "s4ao_ew_mul", "s4ao_ew_abs",
          "s4ao_ew_leaky", "s4ao_chain_conv_add", "s4ao_chain_add_mul"]
# Overhead calibration (fixed before any Stage 4AO board data): the AO_ACTIVE medians of the s4_conv_base blob on TA
# profile 1 at boots 330, 338, 344 (image 83398c7), 367 and 369 (image 70090f1), recomputed from raw by phase-a.
CAL_BOOTS = [("stage4", "evidence/stage4/raw", BASE), ("stage4c1", "evidence/stage4c1/raw", BASE),
             ("stage4c2", "evidence/stage4c2/raw", BASE),
             ("placement_a", "evidence/stage4_placement/raw/evsweep_s4p_run_a", "s4p_conv_base_ddr"),
             ("stage4k", "evidence/stage4k/raw/evsweep_s4k_run", BASE)]
# Tolerances (fixed before the board; basis in the contract draft §7)
T_ABS, T_REL = 25, 0.01          # per-config model agreement: |AO - pred| <= max(25, 1 % of pred)
SLOPE_TOL = 0.02                 # rate: |slope of AO on N_OFM/16 - 1| <= 2 %
AO_RANGE_ABS, AO_RANGE_REL = 50, 0.02     # pass-A AO RUN range above max(50, 2 % of median) -> unstable
AB_REL = 0.05                    # pass A/B NPU_ACTIVE medians differ by more than max(5 %, rangeA + rangeB) -> unstable
ALLOWED_C_DIFF = {294, 295}      # Phase C selection: only NPU_SET_ACTIVATION_MIN / _MAX may differ from the reference
OPNAMES = {293: "ACTIVATION", 294: "ACTIVATION_MIN", 295: "ACTIVATION_MAX", 280: "OFM_ZERO_POINT", 36: "OFM_SCALE"}
# other existing TA-profile-1 data with a different OFM size (post-hoc, descriptive only): config -> OFM (H, W, C)
OTHER_OFM = {"s4_conv_cin15": (24, 24, 96), "s4_conv_cout95": (24, 24, 95), "s4c_conv_cout94": (24, 24, 94),
             "s4c_conv_cout97": (24, 24, 97), "s4c2_conv_cin128": (24, 24, 96), "s4_dw_base": (56, 56, 144),
             "s4_dw_c143": (56, 56, 143), "s4c_dw_c142": (56, 56, 142), "s4c_dw_c145": (56, 56, 145),
             "s4_fc_base": (1, 1, 288), "s4_fc_in95": (1, 1, 288), "s4_fc_out287": (1, 1, 287)}


def ao_metrics(ao: float | None, n_ofm: int) -> dict:
    ideal = n_ofm / SU_RATE
    if not ao:
        return dict(n_ofm=n_ofm, ao_ideal_cycles=ideal)
    return dict(n_ofm=n_ofm, ao_ideal_cycles=ideal, ao_observed_throughput=n_ofm / ao, ao_cycle_residual=ao - ideal,
                ao_relative_throughput=n_ofm / ao / SU_RATE)


def c16(h: int, w: int, c: int) -> int:
    return h * w * math.ceil(c / 16) * 16


def tol(pred: float) -> float:
    return max(T_ABS, T_REL * pred)


# ---- Phase A ------------------------------------------------------------------------------------------------------
def summary(folder: pathlib.Path) -> dict:
    s = K.summary_of(folder, 1)
    return s["metrics"]


def phase_a(out: str) -> dict:
    st = json.loads((REPO / "results/fi101_stage4k/static.json").read_text())
    rows = []
    for cfg in K.ORDER:
        m = summary(K4_ROOT / "conds" / cfg / "wfe")
        n = 24 * 24 * 96
        rows.append(dict(config=cfg, kernel=K.CONFIGS[cfg][0], cin=K.CONFIGS[cfg][1], ofm_dtype="int8",
                         activation="RELU6", ofm_block=st[cfg]["ofm_block"], ofm_ublock=st[cfg]["ofm_ublock"],
                         traversal=st[cfg]["traversal"], vela_ao_cycles=float(st[cfg]["vela_ao_cycles"]),
                         ao_active=m["A_64"], ao_range=m["A_64_range"], mac_active=m["A_48"], mac_dpu_active=m["A_51"],
                         npu_active=m["A_35"], ao_over_npu_active=m["A_64"] / m["A_35"],
                         ext_wr_beats=m["B_391"], ofm_dma_bytes_at_16B_per_beat=m["B_391"] * 16,
                         **ao_metrics(m["A_64"], n)))
    ao = [r["ao_active"] for r in rows]
    mac = [r["mac_active"] for r in rows]
    cal = calibration()
    res = dict(table=rows, descriptive=dict(
        ao_min=min(ao), ao_max=max(ao), ao_spread=max(ao) - min(ao), ao_spread_rel=(max(ao) - min(ao)) / min(ao),
        mac_active_ratio_max_min=max(mac) / min(mac), max_ao_run_range=max(r["ao_range"] for r in rows),
        spearman_ao_mac_active=spearman(ao, mac),
        note="all ten configs share one OFM shape (24x24x96): proportionality to N_OFM is not tested by these data"),
        calibration=cal, other_ofm_post_hoc=other_ofm())
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "phase_a.json").write_text(json.dumps(res, indent=1))
    with open(o / "phase_a_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return res


def spearman(a: list, b: list) -> float:
    rank = lambda xs: [sorted(xs).index(x) + (xs.count(x) - 1) / 2 for x in xs]
    ra, rb = rank(a), rank(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return num / math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))


def calibration() -> dict:
    """C0 = median over CAL_BOOTS of (AO_ACTIVE median - 55296/16): the constant overhead M2 uses."""
    per = {}
    for tag, root, cfg in CAL_BOOTS:
        per[tag] = summary(REPO / root / "conds" / cfg / "wfe")["A_64"]
    c0 = statistics.median(v - 55296 / SU_RATE for v in per.values())
    return dict(ao_active=per, c0=c0)


def other_ofm() -> list:
    """Every other existing TA-profile-1 RUN folder with a different OFM size (Stage 4 / 4C-1 / 4C-2), POST_HOC."""
    out = []
    for cfg, (h, w, c) in OTHER_OFM.items():
        for f in sorted(glob.glob(str(REPO / "evidence" / "stage4*" / "raw" / "**" / "conds" / cfg / "wfe"),
                                  recursive=True)):
            m = summary(pathlib.Path(f))
            out.append(dict(config=cfg, folder=str(pathlib.Path(f).relative_to(REPO)), ofm=[h, w, c],
                            ao_active=m["A_64"], ao_range=m["A_64_range"], exact=ao_metrics(m["A_64"], h * w * c),
                            c16=ao_metrics(m["A_64"], c16(h, w, c)), label="POST_HOC_DESCRIPTIVE"))
    return out


# ---- static -------------------------------------------------------------------------------------------------------
def instructions(stream: bytes) -> list[tuple]:
    import cms
    return [(c, op, w >> 16, int.from_bytes(stream[o + 4:o + 8], "little") if c == 1 else None)
            for o, w, c, op in cms.instructions(stream)]


def stream_diff(a: bytes, b: bytes) -> dict:
    x, y = instructions(a), instructions(b)
    if len(x) != len(y) or any(p[:2] != q[:2] for p, q in zip(x, y)):
        return dict(aligned=False, ops=None)
    d = [(i, p[1], p[2:], q[2:]) for i, (p, q) in enumerate(zip(x, y)) if p != q]
    return dict(aligned=True, ops=sorted({op for _, op, _, _ in d}),
                changes=[dict(index=i, op=OPNAMES.get(op, op), ref=list(p), cfg=list(q)) for i, op, p, q in d])


def conv_static(wl: pathlib.Path, cfg: str) -> dict:
    import cms_regs
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    ks = cms_regs.kernels((wl / f"{cfg}.drwl.cms.bin").read_bytes())
    ofm = comp["ofm_shape"][1:]
    bh, bw, bc = (int(v) for v in comp["ofm_block"].split("x"))
    slices = [k["ofm_depth_m1"] + 1 for k in ks]
    blocks = sum(math.ceil(ofm[0] / bh) * math.ceil(ofm[1] / bw) * math.ceil(s / bc) for s in slices)
    sig = dict(traversal=comp["traversal"], ofm_block=comp["ofm_block"], ifm_block=comp["ifm_block"],
               ofm_ublock=comp["ofm_ublock"], n_kernels=comp["n_kernels"], ofm_slices=slices,
               ofm_precision=sorted({k["ofm_precision"] for k in ks}))
    return dict(config=cfg, gate_b=comp["gate_b"], ofm_shape=ofm, n_ofm=math.prod(ofm), signature=sig,
                ofm_blocks=blocks, weight_bytes=int(comp["weight_bytes"]), weight_lengths=[k["weight_length"] for k in ks],
                dma_lengths=[k["dma_before"] for k in ks], vela_ao_cycles=float(comp["vela_ao_cycles"]),
                vela_npu_cycles=float(comp["vela_npu_cycles"]), vela_mac_cycles=float(comp["vela_mac_cycles"]),
                sram_ac=comp.get("sram_ac"), dram_ac=comp.get("dram_ac"), staging_usage=comp.get("staging_usage"),
                ifm_memory=comp.get("ifm_memory"), ofm_memory=comp.get("ofm_memory"), activation=comp["activation"],
                drwl_sha256=comp["drwl_sha256"], model_sha256=comp["model_sha256"], cms_sha256=comp["cms_sha256"],
                cpu_ofm_sha256=comp["cpu_ofm_sha256"], arena_size=comp["arena_size"])


def comparable(st: dict, cfgs: list) -> dict:
    """Comparable = the reference's signature (traversal, OFM/IFM block, ublock, kernel count and OFM slices, OFM
    precision). Verdict: COMPARABLE if >= 3 configs (the reference included) share it, else NEEDS_REVISION."""
    ref = st[REF_H]["signature"]
    same = [c for c in cfgs if st[c]["signature"] == ref and st[c]["gate_b"]]
    return dict(verdict="COMPARABLE" if len(same) >= 3 else "NEEDS_REVISION", comparable=same,
                differing={c: {k: v for k, v in st[c]["signature"].items() if v != ref[k]} for c in cfgs if c not in same})


def phase_c_select(wl: pathlib.Path, st: dict) -> dict:
    ref = (wl / f"{REF_H}.drwl.cms.bin").read_bytes()
    out = {}
    for c in ACTS:
        d = stream_diff(ref, (wl / f"{c}.drwl.cms.bin").read_bytes())
        ok = st[c]["gate_b"] and st[c]["signature"] == st[REF_H]["signature"] and d["aligned"] \
            and set(d["ops"]) <= ALLOWED_C_DIFF and st[c]["weight_lengths"] == st[REF_H]["weight_lengths"]
        out[c] = dict(selected=ok, diff=d)
    return out


def static(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    st = {c: conv_static(wl, c) for c in [BASE, *ORIGINAL, *REVISION, *ACTS]}
    same = lambda a, b: (wl / a).read_bytes() == (wl / b).read_bytes()
    res = dict(configs=st,
               base_equals_ref=dict(cms=same(f"{BASE}.drwl.cms.bin", f"{REF_H}.drwl.cms.bin"),
                                    cpu_ofm=same(f"{BASE}.drwl.tflite_ofm.bin", f"{REF_H}.drwl.tflite_ofm.bin")),
               phase_b_original=comparable(st, ORIGINAL),
               phase_b_revision=comparable(st, [REF_H, "s4ao_conv1x1_h36", *REVISION]),
               phase_c=phase_c_select(wl, st),
               phase_d={p: json.loads((wl / f"{p}.static.json").read_text()) for p in PROBES})
    o.mkdir(parents=True, exist_ok=True)
    (o / "static.json").write_text(json.dumps(res, indent=1, default=str))
    cols = ["config", "n_ofm", "ofm_blocks", "weight_bytes", "vela_ao_cycles", "vela_npu_cycles", "vela_mac_cycles",
            "activation", "drwl_sha256"]
    with open(o / "stage4ao_static.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + list(st[REF_H]["signature"]), lineterminator="\n")
        w.writeheader()
        for c, r in st.items():
            w.writerow(dict({k: r[k] for k in cols}, **r["signature"]))
    return res


# ---- predictions --------------------------------------------------------------------------------------------------
def models(n_ofm: int, blocks: int, ref_blocks: int, c0: float, vela_ao: float) -> dict:
    return dict(M1=n_ofm / SU_RATE, M2=n_ofm / SU_RATE + c0, M3=n_ofm / SU_RATE + c0 * blocks / ref_blocks, M4=vela_ao)


def predict(wl: str, out: str) -> dict:
    wl = pathlib.Path(wl)
    c0 = calibration()["c0"]
    st = {c: conv_static(wl, c) for c in [*ORIGINAL, *REVISION, *ACTS]}
    ref_blocks = st[REF_H]["ofm_blocks"]
    res = dict(c0=c0, su_rate=SU_RATE, tolerance=dict(t_abs=T_ABS, t_rel=T_REL, slope=SLOPE_TOL),
               configs={c: dict(n_ofm=r["n_ofm"], ofm_blocks=r["ofm_blocks"],
                                models=models(r["n_ofm"], r["ofm_blocks"], ref_blocks, c0, r["vela_ao_cycles"]),
                                tol=tol(r["n_ofm"] / SU_RATE + c0)) for c, r in st.items()})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "predictions.json").write_text(json.dumps(res, indent=1))
    return res


# ---- board judgement (frozen contract only) -----------------------------------------------------------------------
def config_result(root: pathlib.Path, wl: pathlib.Path, cfg: str, caps_ref: str | None = None) -> dict:
    """Validity: both passes with 4 measured valid RUNs, K.identity (model, placement 0, REGIONCFG, one IRQ, one CRC,
    output length, capabilities) and an output byte-identical to the CPU reference (PASS_EXACT)."""
    folder = root / "conds" / cfg / "wfe"
    if not (folder / "raw_runs.json").exists():
        return dict(config=cfg, verdict="NOT_MEASURED")
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    s = K.summary_of(folder, comp["n_mac"])
    oc = S4.output_check(folder, comp, (wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), s["runs"])
    ident = K.identity(folder, wl, cfg, caps_ref)
    runs_ok = sorted(s["runs"]) == [1, 2] and all(len(rs) == 4 and all(r["valid"] for r in rs)
                                                  for rs in s["runs"].values())
    m = s["metrics"]
    wl_ok = workload_ok(folder, wl / f"{cfg}.drwl")
    ok = runs_ok and ident["ok"] and wl_ok and oc["verdict"] == "PASS_EXACT"
    return dict(config=cfg, gate_c="PASS" if ok else "FAIL", verdict="VALID" if ok else "INVALID", metrics=m,
                output=oc["verdict"], identity=ident, workload_sha256_ok=wl_ok, runs_valid=runs_ok,
                stability=stability(m))


def workload_ok(folder: pathlib.Path, drwl_path: pathlib.Path) -> bool:
    """Every runs.csv row names this DRWL (workload_sha256 = its sha256). All Stage 4AO configs share model_len
    5568, so K.identity's model-length check alone cannot tell them apart."""
    import hashlib
    want = hashlib.sha256(drwl_path.read_bytes()).hexdigest()
    with open(folder / "runs.csv") as f:
        got = {r["workload_sha256"] for r in csv.DictReader(f)}
    return got == {want}


def stability(m: dict) -> dict:
    ao, r = m.get("A_64"), m.get("A_64_range")
    a, b = m.get("A_35"), m.get("B_35")
    ao_ok = ao is not None and r is not None and r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao)
    ab_ok = a is not None and b is not None and \
        abs(b - a) <= max(AB_REL * a, (m.get("A_35_range") or 0) + (m.get("B_35_range") or 0))
    return dict(ok=ao_ok and ab_ok, ao_range_ok=ao_ok, pass_ab_ok=ab_ok)


def model_check(ao: float, pred: dict) -> dict:
    return {k: dict(pred=v, error=ao - v, within=abs(ao - v) <= tol(v)) for k, v in pred.items()}


def slope(xs: list, ys: list) -> tuple[float, float]:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return b, my - b * mx


def rate_verdict(res: dict, sweep: list, comparable_set: list) -> dict:
    """RQ1 (closed set): INVALID if fewer than 3 sweep configs are valid; MEASUREMENT_UNSTABLE if any valid one is
    unstable; SCHEDULE_CONFOUNDED if fewer than 3 valid configs are statically comparable; else the slope of AO_ACTIVE
    on N_OFM/16 over the comparable valid configs: RATE_CONSISTENT if |slope - 1| <= SLOPE_TOL else
    RATE_NOT_CONSISTENT."""
    valid = [c for c in sweep if res[c].get("verdict") == "VALID"]
    if len(valid) < 3:
        return dict(verdict="INVALID", valid=valid)
    if not all(res[c]["stability"]["ok"] for c in valid):
        return dict(verdict="MEASUREMENT_UNSTABLE", unstable=[c for c in valid if not res[c]["stability"]["ok"]])
    use = [c for c in valid if c in comparable_set]
    if len(use) < 3:
        return dict(verdict="SCHEDULE_CONFOUNDED", comparable_valid=use)
    xs = [res[c]["n_ofm"] / SU_RATE for c in use]
    ys = [res[c]["metrics"]["A_64"] for c in use]
    b, a = slope(xs, ys)
    return dict(verdict="RATE_CONSISTENT" if abs(b - 1) <= SLOPE_TOL else "RATE_NOT_CONSISTENT", configs=use,
                slope=b, intercept=a, observed_rate=SU_RATE / b)


def act_verdict(res: dict, cfg: str) -> dict:
    """Phase C pair against the RELU6 reference: same AO rate if |AO - AO_ref| <= tol(AO_ref)."""
    r, ref = res.get(cfg, {}), res.get(REF_H, {})
    if r.get("verdict") != "VALID" or ref.get("verdict") != "VALID":
        return dict(verdict="INVALID")
    if not (r["stability"]["ok"] and ref["stability"]["ok"]):
        return dict(verdict="MEASUREMENT_UNSTABLE")
    d = r["metrics"]["A_64"] - ref["metrics"]["A_64"]
    return dict(verdict="RATE_CONSISTENT" if abs(d) <= tol(ref["metrics"]["A_64"]) else "RATE_NOT_CONSISTENT",
                ao_diff=d, tol=tol(ref["metrics"]["A_64"]))


def models_verdict(res: dict, use: list) -> dict:
    """H2 (closed set), over the valid comparable sweep configs rate_verdict used: a model is CONSISTENT if every
    one of them is within tol. M2 / M3 together: BOTH_CONSISTENT, M2_ONLY, M3_ONLY, NEITHER."""
    if len(use) < 3:
        return dict(verdict="NOT_JUDGED", configs=use)
    per = {m: all(res[c]["models"][m]["within"] for c in use) for m in ("M1", "M2", "M3", "M4")}
    both = {(True, True): "BOTH_CONSISTENT", (True, False): "M2_ONLY", (False, True): "M3_ONLY",
            (False, False): "NEITHER"}[(per["M2"], per["M3"])]
    return dict(verdict=both, per_model={m: "CONSISTENT" if v else "NOT_CONSISTENT" for m, v in per.items()},
                configs=use)


def base_vs_ref(res: dict) -> dict:
    """s4_conv_base (VALID) and s4ao_conv1x1_h24 (SAME): the same command stream, so a repeated measurement of one
    execution, never a second sweep sample. Descriptive: AO difference against tol."""
    a, b = res.get(BASE, {}), res.get(REF_H, {})
    if a.get("verdict") != "VALID" or b.get("verdict") != "VALID":
        return dict(verdict="NOT_JUDGED")
    d = b["metrics"]["A_64"] - a["metrics"]["A_64"]
    return dict(verdict="SAME_WITHIN_TOL" if abs(d) <= tol(a["metrics"]["A_64"]) else "DIFFERENT", ao_diff=d,
                npu_diff=b["metrics"]["A_35"] - a["metrics"]["A_35"])


def repro_gate(root: str, wl: str, ref: str | None = None) -> dict:
    """Boot 1 = s4_conv_base (the Stage 4K blob) against Stage 4K boot 369 (same image): K.reproduce (MAC, DPU,
    output, constant counters, NPU_ACTIVE) and AO_ACTIVE within tol. ref: a copy of the boot-369 wfe folder (its
    parent holds capabilities.json), as staged on the board."""
    caps = str(pathlib.Path(ref).parent / "capabilities.json") if ref else None
    r = config_result(pathlib.Path(root), pathlib.Path(wl), BASE, caps)
    if r["verdict"] != "VALID":
        return dict(verdict="FAIL", why=r["verdict"])
    folder = pathlib.Path(ref) if ref else K4_ROOT / "conds" / BASE / "wfe"
    rs = K.summary_of(folder, K.macs(1, 16)["nominal"])
    k = K.summary_of(pathlib.Path(root) / "conds" / BASE / "wfe", K.macs(1, 16)["nominal"])
    rep = K.reproduce(k, rs)
    ao, ao_ref = r["metrics"]["A_64"], rs["metrics"]["A_64"]
    ao_ok = abs(ao - ao_ref) <= tol(ao_ref)
    return dict(verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep, ao=ao, ao_ref=ao_ref, ao_ok=ao_ok)


def boot_check(root: str, wl: str, cfg: str, caps_ref: str | None = None) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), cfg, caps_ref)
    return dict(config=cfg, verdict="PASS" if r.get("gate_c") == "PASS" else "FAIL", output=r.get("output"),
                identity=r.get("identity"), runs_valid=r.get("runs_valid"))


def judge(root: str, wl: str, pred_path: str, out: str, sweep: str, acts: str = "", ref: str | None = None) -> dict:
    root, wlp = pathlib.Path(root), pathlib.Path(wl)
    pred = json.loads(pathlib.Path(pred_path).read_text())
    sw = sweep.split(","); ac = [a for a in acts.split(",") if a]
    caps = str(pathlib.Path(ref).parent / "capabilities.json") if ref else None
    res = {c: config_result(root, wlp, c, caps) for c in [*sw, *ac]}
    base = config_result(root, wlp, BASE, caps)
    for c, r in res.items():
        r["n_ofm"] = pred["configs"][c]["n_ofm"]
        if r.get("verdict") == "VALID":
            r["models"] = model_check(r["metrics"]["A_64"], pred["configs"][c]["models"])
            r["ao"] = ao_metrics(r["metrics"]["A_64"], r["n_ofm"])
    st = {c: conv_static(wlp, c) for c in sw}
    gate = repro_gate(str(root), wl, ref)
    cmp_set = comparable({**st, REF_H: conv_static(wlp, REF_H)}, sw)["comparable"]
    rq1 = rate_verdict(res, sw, cmp_set) if gate["verdict"] == "PASS" else dict(verdict="NOT_INTERPRETED (REPRO_GATE)")
    rq2 = models_verdict(res, rq1.get("configs", [])) if rq1["verdict"].startswith("RATE_") \
        else dict(verdict="NOT_JUDGED")
    rq3 = {a: act_verdict(res, a) if gate["verdict"] == "PASS" else dict(verdict="NOT_INTERPRETED") for a in ac}
    summary = dict(repro_gate=gate, rq1=rq1, rq2=rq2, rq3=rq3, base_vs_h24=base_vs_ref({**res, BASE: base}),
                   configs={c: {k: v for k, v in r.items() if k != "identity"} for c, r in res.items()})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd in ("repro-gate", "boot-check"):
        r = repro_gate(*a[:3]) if cmd == "repro-gate" else boot_check(*a[:4])
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    r = dict(**{"phase-a": lambda: phase_a(a[0])}, static=lambda: static(*a[:2]), predict=lambda: predict(*a[:2]),
             judge=lambda: judge(*a[:7]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
