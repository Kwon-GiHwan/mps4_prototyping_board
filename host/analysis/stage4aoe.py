#!/usr/bin/env python3
"""Stage 4AO-E (docs/plan/stage4aoe_characterization_plan.md, contract draft evidence/stage4aoe/contract_draft.md): AO
activity of Elementwise (ADD / MUL / ABS), chaining-buffer (Conv->ADD, ADD->MUL) and LUT (Conv->TANH / LOGISTIC)
paths. TA profile 1, driver runner image 70090f1, DDR/EXT, Vela 5.0.0 (MLEK options). Board-free: static, predict.
config-result / boot-check / judge are for a board run under a frozen contract and are exercised here by tests only.

  python3 host/analysis/stage4aoe.py static <workloads dir> <out dir>
  python3 host/analysis/stage4aoe.py predict <workloads dir> <out dir>
  python3 host/analysis/stage4aoe.py boot-check <campaign root> <workloads dir> <config> [<reference capabilities.json>]
  python3 host/analysis/stage4aoe.py repro-gate <campaign root> <workloads dir> <boot-380 wfe copy> [<capabilities>]
  python3 host/analysis/stage4aoe.py judge <campaign root> <workloads dir> <predictions.json> <out dir> [<caps>]

Official rates (Arm Ethos-U85 TRM 102685 issue 05 §4.2, NUM_SU 16 on U85-1024): AB->OB_8, AB->CB_8/16, CB_8/16->CB_8/16
and CB_8/16->OB_8 all run at 1 element per SU per cycle = 16 elements/cycle; 32-bit CB or 16/32-bit OB paths are slower
(Tables 4-11 / 4-12) and are not covered here. "AO pass" = one kernel instruction's AO traversal (a CONV kernel: AB ->
OB or CB; an ELEMENTWISE kernel: IFM/CB -> OB or CB); logical AO elements = the sum over kernels of OFM h*w*depth.
Rates are element-count-to-cycle ratios, not SU occupancy.
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4ao as AO  # noqa: E402
import stage4k as K  # noqa: E402

TRM_RATE = 16                    # elements/cycle, 8-bit paths (TRM Tables 4-11 / 4-12)
CONV_RATE = 15.605               # Stage 4AO RQ1 observed rate (boots 380-383, slope 1.0253), INT8 Conv AB->OB
CHAINED = 2                      # activation_storage CHAINED (ethosu85_interface.h)
GROUP_A = ["s4aoe_add_h24", "s4aoe_add_h72", "s4aoe_mul_h24", "s4aoe_mul_h72", "s4aoe_abs_h24", "s4aoe_abs_h72"]
GROUP_B = ["s4aoe_conv_add_h24", "s4aoe_add_mul_h24"]
GROUP_C = ["s4aoe_tanh_h24", "s4aoe_logistic_h24"]
ALL = GROUP_A + GROUP_B + GROUP_C
PAIRS = {"add": ("s4aoe_add_h24", "s4aoe_add_h72"), "mul": ("s4aoe_mul_h24", "s4aoe_mul_h72"),
         "abs": ("s4aoe_abs_h24", "s4aoe_abs_h72")}
RATE_TOL = 0.01                  # rate class band: +-1 % around 16 or around 15.605 (the two bands do not overlap)
PROP_TOL = 0.02                  # AO(H72) / AO(H24) within 2 % of 3 -> PROPORTIONAL
AO_RANGE_ABS, AO_RANGE_REL = 50, 0.02
AB_REL = 0.05
# Amendment A1 (evidence/stage4aoe/contract_a1.md): REGIONCFG per the firmware's rule (placement.h / placement.c),
# with n_base expected from the DRWL, not from the RUN record. Values typed from the firmware header.
REGION0, REGION1_DDR, REGION1_SRAM, REGION2_7 = 3, 3, 0, 1
QCONFIG = 3
REGIONCFG_MATCH = 1 << 6          # record.h REC_REGIONCFG_MATCH
MANIFEST = "expected_identity.json"


def precision_bits(word: int | None) -> int | None:
    """OFM/IFM precision word (cmd0 param): activation_precision field -> bits (0 = 8, 1 = 16, 2 = 32, 3 = 64)."""
    return None if word is None else 8 << ((word >> 1) & 3)


def passes(aoe: dict) -> list[dict]:
    """One AO pass per kernel instruction: source (AB / IFM / CB), destination (OB / CB), output bits, elements."""
    out = []
    for k, g in zip(aoe["kernels"], aoe["geometry"]):
        src = "AB" if k["kind"] in ("CONV", "DEPTHWISE", "POOL") else ("CB" if k["ifm_storage"] == CHAINED else "IFM")
        dst = "CB" if k["ofm_storage"] == CHAINED else "OB"
        out.append(dict(kind=k["kind"], src=src, dst=dst, ofm_bits=precision_bits(k["ofm_precision"]),
                        lut=bool((k["activation"] or 0) & 0x1F), elements=g["h"] * g["w"] * g["c"]))
    return out


def trm_rate(p: dict) -> float | None:
    """Official elements/cycle of one pass, only for the 8-bit paths TRM Tables 4-11 / 4-12 give as 1 per SU."""
    return TRM_RATE if p["ofm_bits"] == 8 else None


def exactness(aoe: dict) -> str:
    """EXACT_EITHER: tflite default and BUILTIN_REF kernels agree byte for byte (the golden is unambiguous);
    REF_ONLY: they differ (PASS_EXACT is defined only once the owner fixes which CPU reference is the golden)."""
    return "EXACT_EITHER" if aoe["reference"]["opt_vs_ref"] == 0 else "REF_ONLY"


def select(aoe: dict, ps: list[dict]) -> dict:
    """Closed rule (fixed before the board): SELECTED if Vela leaves no CPU op, packing succeeded, every pass is an
    8-bit path with an official rate, and the golden is unambiguous; NEEDS_GOLDEN_RULE if only the last fails;
    EXCLUDED otherwise (reasons listed)."""
    why = [r for r, bad in (("cpu_fallback", bool(aoe["cpu_fallback"])), ("pack_failed", aoe["pack_rc"] != 0),
                            ("path_not_covered", any(trm_rate(p) is None for p in ps))) if bad]
    if why:
        return dict(verdict="EXCLUDED", why=why)
    if exactness(aoe) != "EXACT_EITHER":
        return dict(verdict="NEEDS_GOLDEN_RULE", why=["default and BUILTIN_REF kernels differ"])
    return dict(verdict="SELECTED", why=[])


def static_one(wl: pathlib.Path, cfg: str) -> dict:
    import cms_regs
    aoe = json.loads((wl / f"{cfg}.aoe.json").read_text())
    ks = cms_regs.kernels((wl / f"{cfg}.drwl.cms.bin").read_bytes())
    aoe["geometry"] = [dict(h=k["ofm_height_m1"] + 1, w=k["ofm_width_m1"] + 1, c=k["ofm_depth_m1"] + 1,
                            blk=[k["blk_height_m1"] + 1, k["blk_width_m1"] + 1, k["blk_depth_m1"] + 1],
                            dma=k["dma_before"]) for k in ks]
    ps = passes(aoe)
    logical = sum(p["elements"] for p in ps)
    return dict(config=cfg, group=aoe["group"], h=aoe["h"], n_ofm=aoe["n_ofm"], n_ifm=aoe["n_ifm"], passes=ps,
                n_passes=len(ps), logical_elements=logical, chained=any(p["dst"] == "CB" for p in ps),
                lut=any(p["lut"] for p in ps), geometry=aoe["geometry"], exactness=exactness(aoe),
                reference=aoe["reference"], selection=select(aoe, ps), kernel_kinds=aoe["kernel_kinds"],
                scheduled=aoe["scheduled"], vela_ao_cycles=sum(float(p["ao_cycles"] or 0) for p in aoe["perf_main"]),
                memories=aoe["perf_debug"], drwl_sha256=aoe.get("drwl_sha256"), golden_sha256=aoe.get("golden_sha256"),
                tflite_ofm_sha256=aoe.get("tflite_ofm_sha256"), arena_size=aoe.get("arena_size"),
                fast_size=aoe.get("fast_size"))


def static(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {c: static_one(wl, c) for c in ALL}
    o.mkdir(parents=True, exist_ok=True)
    (o / "static.json").write_text(json.dumps(res, indent=1, default=str))
    cols = ["config", "group", "n_ofm", "n_ifm", "n_passes", "logical_elements", "chained", "lut", "exactness",
            "vela_ao_cycles", "drwl_sha256"]
    with open(o / "stage4aoe_static.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + ["selection", "opt_vs_ref"], lineterminator="\n")
        w.writeheader()
        for c, r in res.items():
            w.writerow(dict({k: r[k] for k in cols}, selection=r["selection"]["verdict"],
                            opt_vs_ref=r["reference"]["opt_vs_ref"]))
    return res


def predict(wl: str, out: str) -> dict:
    st = {c: static_one(pathlib.Path(wl), c) for c in ALL}
    res = {c: dict(n_ofm=r["n_ofm"], logical_elements=r["logical_elements"], n_passes=r["n_passes"],
                   P_TRM=r["logical_elements"] / TRM_RATE, P_CONV=r["logical_elements"] / CONV_RATE,
                   P_VELA=r["vela_ao_cycles"]) for c, r in st.items()}
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    doc = dict(trm_rate=TRM_RATE, conv_rate=CONV_RATE, rate_tol=RATE_TOL, prop_tol=PROP_TOL, configs=res)
    (o / "predictions.json").write_text(json.dumps(doc, indent=1))
    return doc


# ---- board judgement (frozen contract only) -----------------------------------------------------------------------
def rate_class(rate: float) -> str:
    """Observed logical elements / AO_ACTIVE against the two references: NOMINAL_16 (within 1 % of 16), CONV_LIKE
    (within 1 % of the Conv AB->OB rate 15.605), BELOW_CONV, BETWEEN (between the bands) or ABOVE_NOMINAL."""
    if abs(rate / TRM_RATE - 1) <= RATE_TOL:
        return "NOMINAL_16"
    if abs(rate / CONV_RATE - 1) <= RATE_TOL:
        return "CONV_LIKE"
    if rate > TRM_RATE:
        return "ABOVE_NOMINAL"
    return "BELOW_CONV" if rate < CONV_RATE else "BETWEEN"


def stability(m: dict) -> bool:
    ao, r, a, b = m.get("A_64"), m.get("A_64_range"), m.get("A_35"), m.get("B_35")
    if None in (ao, r, a, b):
        return False
    return r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao) and \
        abs(b - a) <= max(AB_REL * a, (m.get("A_35_range") or 0) + (m.get("B_35_range") or 0))


def output_exact(folder: pathlib.Path, golden: bytes, runs: dict) -> bool:
    """output.bin = the DRWL's golden byte for byte, and every RUN reported a match with zero mismatches."""
    p = folder / "output.bin"
    if not p.exists() or p.read_bytes() != golden:
        return False
    with open(folder / "runs.csv") as f:
        rows = list(csv.DictReader(f))
    return bool(rows) and all(r["output_match"] == "1" and r["ofm_mismatch_count"] == "0" for r in rows)


def placement_regioncfg(n_base: int, placement: int) -> int:
    """firmware placement_regioncfg: 2 bits per region for the first min(n_base, 8) regions."""
    sel = lambda i: REGION0 if i == 0 else (REGION1_SRAM if placement == 1 else REGION1_DDR) if i == 1 else REGION2_7
    return sum(sel(i) << (2 * i) for i in range(min(n_base, 8)))


def expected_identity(wl: pathlib.Path, cfg: str) -> dict:
    """n_base from two derivations that never look at a RUN: the manifest (the Vela model's ethos-u custom op:
    inputs - 1 + outputs, made in the container) and the DRWL header (3 + graph inputs + graph outputs: command
    stream, flash, scratch, fast scratch). They must agree; the placement is the DRWL's word 7."""
    import drwl
    h = drwl.parse((wl / f"{cfg}.drwl").read_bytes())
    man = json.loads((wl / MANIFEST).read_text()).get(cfg, {})
    from_header = min(3 + h["n_in"] + h["n_out"], 8)
    agree = man.get("n_base") == from_header and man.get("placement") == h["placement"]
    return dict(n_base=from_header if agree else None, from_manifest=man.get("n_base"), from_header=from_header,
                placement=h["placement"], agree=agree,
                regioncfg=placement_regioncfg(from_header, h["placement"]) if agree else None)


def identity_a1(folder: pathlib.Path, wl: pathlib.Path, cfg: str, caps_ref: str | None = None) -> dict:
    """K.identity without its fixed REGIONCFG constant, plus, for every RUN (warm-up included): n_base = the expected
    n_base, regioncfg_irq = placement_regioncfg(expected n_base, DRWL placement), qconfig_irq = 3, placement = the
    DRWL's, and the firmware's REGIONCFG_MATCH flag set."""
    k = K.identity(folder, wl, cfg, caps_ref)
    checks = {n: v for n, v in k["checks"].items() if n != "regioncfg"}
    exp = expected_identity(wl, cfg)
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    recs = [(x["record"], x.get("valid_flags", 0)) for x in raw]
    checks.update(expected_agree=exp["agree"],
                  n_base=bool(recs) and exp["agree"] and all(r.get("n_base") == exp["n_base"] for r, _ in recs),
                  regioncfg=bool(recs) and exp["agree"] and all(r.get("regioncfg_irq") == exp["regioncfg"] for r, _ in recs),
                  qconfig=bool(recs) and all(r.get("qconfig_irq") == QCONFIG for r, _ in recs),
                  drwl_placement=bool(recs) and all(r.get("placement") == exp["placement"] for r, _ in recs),
                  regioncfg_match_flag=bool(recs) and all(f & REGIONCFG_MATCH for _, f in recs))
    return dict(ok=all(checks.values()), checks=checks, expected=exp, caps_diff=k.get("caps_diff"))


def config_result(root: pathlib.Path, wl: pathlib.Path, cfg: str, caps_ref: str | None = None) -> dict:
    folder = root / "conds" / cfg / "wfe"
    if not (folder / "raw_runs.json").exists():
        return dict(config=cfg, verdict="NOT_MEASURED")
    s = K.summary_of(folder, 1)
    runs_ok = sorted(s["runs"]) == [1, 2] and all(len(rs) == 4 and all(r["valid"] for r in rs) for rs in s["runs"].values())
    ident = identity_a1(folder, wl, cfg, caps_ref)
    wl_ok = AO.workload_ok(folder, wl / f"{cfg}.drwl")
    out_ok = output_exact(folder, (wl / f"{cfg}.ref_ofm.bin").read_bytes(), s["runs"])
    ok = runs_ok and ident["ok"] and wl_ok and out_ok
    return dict(config=cfg, verdict="VALID" if ok else "INVALID", gate_c="PASS" if ok else "FAIL", metrics=s["metrics"],
                runs_valid=runs_ok, identity=ident, workload_sha256_ok=wl_ok, output_exact=out_ok,
                stable=stability(s["metrics"]))


def rate_verdict(r: dict, logical: int) -> dict:
    if r.get("verdict") != "VALID":
        return dict(verdict="INVALID" if r.get("verdict") == "INVALID" else "NOT_MEASURED")
    if not r["stable"]:
        return dict(verdict="MEASUREMENT_UNSTABLE")
    rate = logical / r["metrics"]["A_64"]
    return dict(verdict=rate_class(rate), rate=rate, rel_to_16=rate / TRM_RATE, rel_to_conv=rate / CONV_RATE)


def prop_verdict(a: dict, b: dict) -> dict:
    """RQ1 per operator: AO(H72) / AO(H24) against 3 (= the element ratio); both must be VALID and stable."""
    if a.get("verdict") != "VALID" or b.get("verdict") != "VALID":
        return dict(verdict="INVALID")
    if not (a["stable"] and b["stable"]):
        return dict(verdict="MEASUREMENT_UNSTABLE")
    ratio = b["metrics"]["A_64"] / a["metrics"]["A_64"]
    slope = (b["metrics"]["A_64"] - a["metrics"]["A_64"]) / (2 * 24 * 24 * 96 / TRM_RATE)   # vs ideal cycle step
    return dict(verdict="PROPORTIONAL" if abs(ratio / 3 - 1) <= PROP_TOL else "NOT_PROPORTIONAL", ratio=ratio,
                slope_vs_ideal=slope, intercept=a["metrics"]["A_64"] - slope * 24 * 24 * 96 / TRM_RATE)


REPRO_CFG = "s4ao_conv1x1_h24"   # boot 1: the Stage 4AO H24 blob, against its boot 380 (same image)


def repro_gate(root: str, wl: str, ref: str, caps_ref: str | None = None) -> dict:
    """Boot 1: Stage 4AO's H24 DRWL (validity by stage4ao.config_result: identity, workload sha256, PASS_EXACT) and
    K.reproduce against the boot-380 wfe folder (MAC, DPU, output sha256, constant counters, NPU_ACTIVE), plus
    AO_ACTIVE within stage4ao.tol of boot 380. Fail -> the session stops."""
    r = AO.config_result(pathlib.Path(root), pathlib.Path(wl), REPRO_CFG, caps_ref)
    if r["verdict"] != "VALID":
        return dict(verdict="FAIL", why=r["verdict"])
    now = K.summary_of(pathlib.Path(root) / "conds" / REPRO_CFG / "wfe", 1)
    rs = K.summary_of(pathlib.Path(ref), 1)
    rep = K.reproduce(now, rs)
    ao, ao_ref = now["metrics"]["A_64"], rs["metrics"]["A_64"]
    ao_ok = abs(ao - ao_ref) <= AO.tol(ao_ref)
    return dict(verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep, ao=ao, ao_ref=ao_ref, ao_ok=ao_ok)


def boot_check(root: str, wl: str, cfg: str, caps_ref: str | None = None) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), cfg, caps_ref)
    return dict(config=cfg, verdict="PASS" if r.get("gate_c") == "PASS" else "FAIL", output_exact=r.get("output_exact"),
                workload_sha256_ok=r.get("workload_sha256_ok"), runs_valid=r.get("runs_valid"),
                identity=r.get("identity"))


def judge(root: str, wl: str, pred_path: str, out: str, caps_ref: str | None = None) -> dict:
    root, wlp = pathlib.Path(root), pathlib.Path(wl)
    pred = json.loads(pathlib.Path(pred_path).read_text())["configs"]
    res = {c: config_result(root, wlp, c, caps_ref) for c in ALL}
    rates = {c: rate_verdict(res[c], pred[c]["logical_elements"]) for c in ALL}
    props = {op: prop_verdict(res[a], res[b]) for op, (a, b) in PAIRS.items()}
    summary = dict(rates=rates, proportional=props,
                   configs={c: {k: v for k, v in r.items() if k != "identity"} for c, r in res.items()})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd in ("boot-check", "repro-gate"):
        r = boot_check(*a[:4]) if cmd == "boot-check" else repro_gate(*a[:4])
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    r = dict(static=lambda: static(*a[:2]), predict=lambda: predict(*a[:2]), judge=lambda: judge(*a[:5]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
