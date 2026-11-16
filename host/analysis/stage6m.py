#!/usr/bin/env python3
"""Stage 6-M (evidence/stage6m/contract.md): board-free model-level reassessment of H1-UC. Maps every TFLite operator of
the seven MLEK models to its Vela execution, classifies each 1x1 DepthFirst Conv (A BOARD_MEASURED / B
VALIDATED_DOMAIN_PREDICTION / C EXTRAPOLATED_PREDICTION / D NOT_APPLICABLE), computes the unchanged H1-UC per kernel, the
model metrics on original TFLite N_MAC, the bound check, the excess share, the verdict, the P1-P7 level and the E2 link.

Unchanged imports: stage6br (h1_uc, ublocks, chunks, mac_chunk, stage6bb_cases; 5c801f7), stage6be1r (exec_sig),
stage6be1 (parse), stage6b (targets), stage6 (fused).

  python3 stage6m.py run <kernels.json> <out dir>
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6 as S6  # noqa: E402
import stage6b as S  # noqa: E402
import stage6be1 as E  # noqa: E402
import stage6be1r as E1R  # noqa: E402
import stage6br as R  # noqa: E402

REPO = R.REPO
MODELS = ("kws_micronet_m", "ad_medium_int8", "mobilenet_v2_1.0_224_INT8", "vww4_128_128_INT8", "rnnoise_INT8",
          "yolo-fastest_192_face_v4", "wav2letter_pruned_int8")
META = {m: REPO / ("evidence/stage1/workload_manifest/meta" if m in MODELS[:3] else "evidence/x1_mlek_models") / f"{m}.meta.json"
        for m in MODELS}
INVENTORY = REPO / "results/fi101_stage4/stage4_operator_inventory.csv"
DTYPES = REPO / "results/fi101_stage6/tflite_dtypes.json"
M7_WL = REPO / "evidence/driver_m7/workloads"
S6_WHOLE = REPO / "results/fi101_stage6/whole_model_comparison.csv"
S6_MATRIX = REPO / "results/fi101_stage6/anomaly_attribution_matrix.csv"
BB_DIR = REPO / "results/fi101_stage6b/stage6bb"
BB_MAN = REPO / "evidence/stage6b/stage6bb/workloads/stage6bb_manifest.json"
RA = REPO / "evidence/stage6b/revision_a/compiled"
BR_VELA = REPO / "results/fi101_stage6b/stage6br/vela_fidelity_analysis.csv"
E1R_WL = REPO / "evidence/stage6b/stage6be1r/workloads"
E1R_SUM = REPO / "results/fi101_stage6b/stage6be1r/stage6be1r_summary.json"

A, B, C, D = "BOARD_MEASURED", "VALIDATED_DOMAIN_PREDICTION", "EXTRAPOLATED_PREDICTION", "NOT_APPLICABLE"
UBLOCK_VOLUME = 128
MIN_EVIDENCE_COVERAGE = 0.50     # V3, P level
MIN_EXCESS_SHARE = 0.10          # V5, P level
PAIR = ("kws_micronet_m", "ad_medium_int8")


def hwc(s: str) -> list[int]:
    return [int(v) for v in s.split("x")]


def read_csv(p: pathlib.Path) -> list[dict]:
    with open(p) as f:
        return list(csv.DictReader(f))


# ---- Phase 1: mapping ------------------------------------------------------------------------------------------------
def integrity(model: str, facts: dict, m7: dict, meta: dict, inv_sha16: set) -> dict:
    """Contract §2.1 (V1 per model)."""
    f = facts.get(model) or {}
    checks = dict(vela_sha256=f.get("vela_sha256") == m7.get("vela_sha256"),
                  cms_sha256=f.get("cms_sha256") == [m7.get("cms_sha256")],
                  model_sha256=f.get("model_sha256") == m7.get("model_sha256") == meta.get("model_sha256"),
                  inventory=inv_sha16 == {(m7.get("vela_sha256") or "")[:16]})
    return dict(checks, ok=all(checks.values()))


def executions(rows: list[dict], idx: int) -> list[dict]:
    """Contract §2.3: the non-fused, non-CPU scheduled ops of one TFLite operator."""
    return [r for r in rows if r["tflite_op_index"] == str(idx) and r["npu_op"] and r["cpu"] == "0" and not S6.fused(r)]


def fused_ops(conv: dict, rows: list[dict]) -> list[dict]:
    """Contract §2.5: zero-cycle rows of the same model carrying the Conv's name."""
    return [r for r in rows if r is not conv and r["name"] == conv["name"] and S6.fused(r)]


def kernels_of(r: dict, kfacts: list[dict] | None) -> list[dict | None]:
    by = {k["offset"]: k for k in (kfacts or [])}
    return [by.get(int(o)) for o in r["cms_offsets"].split()]


def case_of(r: dict, ks: list[dict]) -> dict:
    oh, ow, cout = hwc(r["npu_ofm_hwc"])
    return dict(cin=int(r["cin"]), cout=cout, ofm=[oh, ow, cout], ublock=hwc(r["ofm_ublock"]),
                ifm_block_depth=hwc(r["ifm_block"])[2], ofm_block=r["ofm_block"], ifm_block=r["ifm_block"],
                kernels=[[k["ofm_height_m1"] + 1, k["ofm_width_m1"] + 1, k["ofm_depth_m1"] + 1] for k in ks])


def computable(r: dict, ks: list, n_tfl, ok_model: bool) -> list[str]:
    """Contract §3 computability; returns the reasons it fails (empty = computable)."""
    why = []
    if not ok_model:
        why.append("model integrity")
    if not ks or any(k is None for k in ks):
        return why + ["kernel missing at a cms offset"]
    if any(k["kind"] != "CONV" or k["kernel_width_m1"] != 0 or k["kernel_height_m1"] != 0 for k in ks):
        why.append("kernel not CONV 1x1")
    if any(k["ifm_depth_m1"] + 1 != int(r["cin"]) for k in ks):
        why.append("kernel IFM depth != Cin")
    c = case_of(r, ks)
    oh, ow, cout = c["ofm"]
    if sum(h * w * d for h, w, d in c["kernels"]) != oh * ow * cout:
        why.append("kernels do not cover the OFM")
    if n_tfl != oh * ow * cout * c["cin"]:
        why.append("TFLite N_MAC != OFM x Cin")
    if math.prod(c["ublock"]) != UBLOCK_VOLUME:
        why.append("ublock volume != 128")
    return why


# ---- Phase 2: evidence -----------------------------------------------------------------------------------------------
def config(c: dict, row: dict) -> dict:
    return dict(sig=E1R.exec_sig(c), memory=(row["ifm_memory"], row["ofm_memory"]), stride=row["stride"],
                activation=row["tflite_activation"])


def measured_configs() -> dict[str, list[dict]]:
    """6B-B A2 Conv configurations by status (VALID / UNSTABLE), from the Revision A compiled A2 facts."""
    man = json.loads(BB_MAN.read_text())
    status = {r["config"]: r["status"] for r in read_csv(BB_DIR / "shapes.csv")}
    out: dict[str, list[dict]] = {}
    for cfg, m in sorted(man.items()):
        if m["kind"] != "A2":
            continue
        a2 = json.loads((RA / f"s6b_{m['group'].lower()}.ra.json").read_text())["forms"]["A2"]
        c = case_of(a2["conv_row"], a2["conv_kernels"])
        out.setdefault(status[cfg], []).append(dict(config(c, a2["conv_row"]), group=m["group"]))
    return out


def e1r_domain() -> dict:
    """Contract §3 B: the box spanned by the six E1-R shapes (all PRIMARY_VALID with an exact H1-UC match)."""
    return domain_of(json.loads((E1R_WL / "predictions.json").read_text()), json.loads((E1R_WL / "build.json").read_text()),
                     json.loads(E1R_SUM.read_text())["shapes"])


def domain_of(preds: dict, build: dict, shapes: list[dict]) -> dict:
    ok = {s["config"] for s in shapes if s["cls"] == "PRIMARY_VALID" and s["h1_uc_match"]}
    dims = []
    for name in sorted(ok):
        cin, h, w, cout = E.parse(name)
        conv = [x for x in build[name]["rows"] if x["npu_op"] == "Conv2D"][0]
        dims.append(dict(cin=cin, h=h, w=w, cout=cout, ublock=tuple(preds[name]["ublock"]),
                         ifm_depth=hwc(preds[name]["ifm_block"])[2], memory=(conv["ifm_memory"], conv["ofm_memory"]),
                         stride=conv["stride"], kernel=conv["kernel"], traversal=conv["traversal"]))
    rng = lambda k: (min(d[k] for d in dims), max(d[k] for d in dims))  # noqa: E731
    return dict(n=len(dims), cin=rng("cin"), hw=(min(rng("h")[0], rng("w")[0]), max(rng("h")[1], rng("w")[1])),
                cout=rng("cout"), ublock={d["ublock"] for d in dims}, ifm_depth={d["ifm_depth"] for d in dims},
                memory={d["memory"] for d in dims}, stride={d["stride"] for d in dims},
                kernel={d["kernel"] for d in dims}, traversal={d["traversal"] for d in dims})


def domain_flags(c: dict, r: dict, lut: bool, dom: dict) -> dict:
    inside = lambda v, b: b[0] <= v <= b[1]  # noqa: E731
    oh, ow, cout = c["ofm"]
    return dict(traversal=r["traversal"] in dom["traversal"], kernel=r["kernel"] in dom["kernel"],
                stride=r["stride"] in dom["stride"], ublock=tuple(c["ublock"]) in dom["ublock"],
                ifm_depth=c["ifm_block_depth"] in dom["ifm_depth"], cin=inside(c["cin"], dom["cin"]),
                ofm_h=inside(oh, dom["hw"]), ofm_w=inside(ow, dom["hw"]), cout=inside(cout, dom["cout"]),
                full_spatial=all((h, w) == (oh, ow) for h, w, _ in c["kernels"]),
                memory=(r["ifm_memory"], r["ofm_memory"]) in dom["memory"], no_lut=not lut)


def classify(c: dict, r: dict, lut: bool, meas: dict, dom: dict) -> tuple[str, str, list[str], str]:
    """Contract §3 order A > B > C for a computable target. Returns (category, measured group, failed B dims, unstable group)."""
    mine = config(c, r)
    same = lambda m: m["sig"] == mine["sig"] and m["memory"] == mine["memory"] and m["stride"] == mine["stride"] \
        and m["activation"] == mine["activation"]  # noqa: E731
    hit = next((m["group"] for m in meas.get("VALID", []) if same(m)), "")
    unstable = next((m["group"] for m in meas.get("UNSTABLE", []) if same(m)), "")
    fails = [k for k, v in domain_flags(c, r, lut, dom).items() if not v]
    if hit and not lut:
        return A, hit, fails, unstable
    return (B if not fails else C), "", fails, unstable


# ---- Phase 3: costs --------------------------------------------------------------------------------------------------
def factors(c: dict, n: int) -> dict:
    """Contract §4: H1-UC (unchanged) and its multiplicative factors."""
    uh, uw, ud = c["ublock"]
    u = R.ublocks(c["kernels"], c["ublock"])
    u0 = sum(h * w * d for h, w, d in c["kernels"]) / UBLOCK_VOLUME
    u_sp = sum(math.ceil(h / uh) * math.ceil(w / uw) * d / ud for h, w, d in c["kernels"])
    u_co = sum(h / uh * (w / uw) * math.ceil(d / ud) for h, w, d in c["kernels"])
    cc = sum(R.mac_chunk(x) for x in R.chunks(c["cin"], c["ifm_block_depth"]))
    h1 = R.h1_uc(c)
    f = dict(h1uc=h1, ideal=n / 1024, eff=n / 1024 / h1, loss=h1 - n / 1024, F_U=u / u0, F_sp=u_sp / u0, F_cout=u_co / u0,
             F_cin=cc / (c["cin"] / 8))
    f["interaction"] = f["F_U"] / (f["F_sp"] * f["F_cout"])
    f["factor_check"] = math.isclose(1 / f["eff"], f["F_U"] * f["F_cin"], rel_tol=1e-9)
    f["h1uc_no_spatial"] = R.h1_uc(c, pad_spatial=False)
    f["h1uc_no_cout_pad"] = u_sp * cc
    f["h1uc_no_cin_pad"] = u * c["cin"] / 8
    return f


def operators(model: str, rows: list[dict], meta: dict, dt: dict, kf: dict | None, ok: bool, meas: dict, dom: dict) -> list[dict]:
    """One row per TFLite operator (contract §2.2), with the category and the H1-UC facts of the targets."""
    targets = {id(r) for r in S.targets(rows, dt)}
    out = []
    for i, op in enumerate(meta["ops"]):
        ex = executions(rows, i)
        row = dict(model=model, tflite_op_index=i, tflite_op=op["op"], n_mac_tflite=op["n_mac"], n_sched=len(ex),
                   exec_on="NPU" if len(ex) == 1 else ("CPU_OR_REMOVED" if not ex else "AMBIGUOUS_SPLIT"),
                   is_target=False, category=D, reason="")
        if len(ex) == 1:
            r = ex[0]
            fz = fused_ops(r, rows)
            row.update(scheduled_id=r["scheduled_id"], npu_op=r["npu_op"], kernel=r["kernel"], stride=r["stride"],
                       traversal=r["traversal"], cin=r["cin"], cout=r["cout"], npu_ofm_hwc=r["npu_ofm_hwc"],
                       ifm_block=r["ifm_block"], ofm_block=r["ofm_block"], ofm_ublock=r["ofm_ublock"],
                       ifm_memory=r["ifm_memory"], ofm_memory=r["ofm_memory"], cascade=r["cascade"],
                       tflite_activation=r["tflite_activation"], fused_ops=";".join(x["tflite_op"] for x in fz),
                       lut_fused=any(x["npu_op"] == "LUT" for x in fz), vela_mac_count=r["mac_count"],
                       vela_mac_cycles=r["vela_mac_cycles"], vela_op_cycles=r["vela_op_cycles"], cms_offsets=r["cms_offsets"])
            row["is_target"] = id(r) in targets
        if not row["is_target"]:
            row["reason"] = "not a 1x1 DepthFirst Conv" if len(ex) == 1 else row["exec_on"]
            out.append(row)
            continue
        ks = kernels_of(r, kf["kernels"][0] if kf and kf.get("n_ethosu_ops") == 1 else None)
        why = computable(r, ks, op["n_mac"], ok)
        if why:
            row["reason"] = "; ".join(why)
            out.append(row)
            continue
        c = case_of(r, ks)
        cat, grp, fails, unst = classify(c, r, row["lut_fused"], meas, dom)
        row.update(category=cat, measured_group=grp, b_failed_dims=" ".join(fails), measured_unstable_match=unst,
                   kernels=json.dumps(c["kernels"]), n_kernels=len(c["kernels"]),
                   spatial_stripe=not all((h, w) == tuple(c["ofm"][:2]) for h, w, _ in c["kernels"]),
                   cin_chunks=" ".join(map(str, R.chunks(c["cin"], c["ifm_block_depth"]))), **factors(c, op["n_mac"]))
        vm = float(r["vela_mac_cycles"] or 0)
        row["h1uc_over_vela_mac_cycles"] = row["h1uc"] / vm if vm else None
        out.append(row)
    return out


# ---- model metrics, bound, excess, verdict ---------------------------------------------------------------------------
SETS = {"ABC": (A, B, C), "AB": (A, B), "A": (A,)}


def model_metrics(ops: list[dict], mac_meas: float, npu_meas: float) -> dict:
    """Contract §5."""
    mac_ops = [o for o in ops if o["n_mac_tflite"] is not None]
    n_model = sum(o["n_mac_tflite"] for o in mac_ops)
    npu_mac = [o for o in mac_ops if o["n_sched"] >= 1]
    n_npu = sum(o["n_mac_tflite"] for o in npu_mac)
    tg = [o for o in mac_ops if o["is_target"]]
    m = dict(n_model=n_model, n_npu=n_npu, n_cpu_mac=n_model - n_npu, mac_active_meas=mac_meas, npu_active_meas=npu_meas,
             eff_meas=n_npu / (1024 * mac_meas) if mac_meas else None, mac_over_npu=mac_meas / npu_meas if npu_meas else None,
             share_1x1df=sum(o["n_mac_tflite"] for o in tg) / n_model if n_model else 0.0,
             n_ops={k: sum(o["category"] == k for o in tg) for k in (A, B, C, D)})
    excess = mac_meas - n_npu / 1024
    for key, cats in SETS.items():
        s = [o for o in npu_mac if o["category"] in cats and o["is_target"]]
        rest = [o for o in npu_mac if not (o["category"] in cats and o["is_target"])]
        h1 = sum(o["h1uc"] for o in s)
        n_s = sum(o["n_mac_tflite"] for o in s)
        m[f"coverage_{key}"] = n_s / n_model if n_model else 0.0
        m[f"h1uc_{key}"] = h1
        m[f"eff_set_{key}"] = n_s / (1024 * h1) if h1 else None
        m[f"bound_{key}"] = mac_meas - h1 - sum(o["n_mac_tflite"] for o in rest) / 1024
        m[f"excess_share_{key}"] = sum(o["loss"] for o in s) / excess if s and excess > 0 else None
        m[f"h1uc_over_mac_meas_{key}"] = h1 / mac_meas if mac_meas else None
        for f in ("h1uc_no_spatial", "h1uc_no_cout_pad", "h1uc_no_cin_pad"):
            m[f"{f}_{key}"] = sum(o[f] for o in s)
    m["excess_meas"] = excess
    return m


def verdict(integ: dict, mm: dict, s6_cov: dict) -> dict:
    """Contract §7."""
    v = dict(V1=all(x["ok"] for x in integ.values()))
    viol = [m for m, x in mm.items() if x["n_ops"][A] + x["n_ops"][B] > 0 and x["bound_AB"] < 0]
    v["V2"] = not viol
    k, a = (mm[p] for p in PAIR)
    v["V3"] = all(x["coverage_AB"] >= MIN_EVIDENCE_COVERAGE for x in (k, a))
    v["V4"] = bool(k["eff_set_AB"] and a["eff_set_AB"] and a["eff_set_AB"] > k["eff_set_AB"]
                   and a["eff_meas"] > k["eff_meas"])
    v["V5"] = any((x["excess_share_AB"] or 0) >= MIN_EXCESS_SHARE for x in (k, a))
    expanded = [m for m, x in mm.items() if x["coverage_ABC"] > s6_cov.get(m, 0.0)]
    if not v["V1"]:
        out = "INSUFFICIENT_EVIDENCE"
    elif all(v.values()):
        out = "EXPLANATORY_SUPPORT_PARTIAL"
    elif expanded:
        out = "COVERAGE_EXPANDED_NOT_EXPLAINED"
    else:
        out = "INSUFFICIENT_EVIDENCE"
    return dict(verdict=out, checks=v, failed=[x for x, ok in v.items() if not ok], bound_violation=viol,
                coverage_expanded=expanded, h1uc_single_op_verdict="PROSPECTIVE_SUPPORT (E1-R, unchanged)")


def p_level(axes: str, x: dict) -> str:
    """Contract §8."""
    if "mac" not in axes.split("+") or x["share_1x1df"] == 0:
        return "NOT_APPLICABLE_TO_H1UC"
    if x["bound_AB"] >= 0 and x["coverage_AB"] >= MIN_EVIDENCE_COVERAGE and (x["excess_share_AB"] or 0) >= MIN_EXCESS_SHARE:
        return "PARTIAL_MAC_COST"
    return "INSUFFICIENT_EVIDENCE"


# ---- E2 link (descriptive) -------------------------------------------------------------------------------------------
def e2_rows() -> list[dict]:
    out = []
    vela = {r["group"]: r for r in read_csv(BR_VELA)}
    shapes = {r["config"]: r for r in read_csv(BB_DIR / "shapes.csv")}
    man = json.loads(BB_MAN.read_text())
    for c in R.stage6bb_cases():
        if c["status"] != "VALID":
            continue
        g = c["case"].split(":")[1]
        cfg = next(k for k, m in man.items() if m["group"] == g)
        conv = {}
        if man[cfg]["kind"] == "A2":
            conv = json.loads((RA / f"s6b_{g.lower()}.ra.json").read_text())["forms"]["A2"]["conv_row"]
        v = vela.get(g, {})
        out.append(dict(source="Stage6B-B", shape=g, ta_profile=1, image="70090f1", h1uc=R.h1_uc(c), mac_active=c["mac"],
                        vela_conv_mac_cycles=conv.get("vela_mac_cycles", ""), vela_conv_op_cycles=conv.get("vela_op_cycles", ""),
                        vela_graph_cycles_total=v.get("vela_cycles_total", ""), vela_graph_label="Vela summary cycles_total" if v else "",
                        npu_active=shapes[cfg]["npu_active"], graph="A2 (ADD, Conv, ADD)" if conv else "Conv alone (Stage 4K reference)"))
    preds = json.loads((E1R_WL / "predictions.json").read_text())
    build = json.loads((E1R_WL / "build.json").read_text())
    for s in json.loads(E1R_SUM.read_text())["shapes"]:
        conv = [x for x in build[s["config"]]["rows"] if x["npu_op"] == "Conv2D"][0]
        out.append(dict(source="Stage6B-E1-R", shape=s["config"], ta_profile=1, image="70090f1", h1uc=s["predicted_mac"],
                        mac_active=s["measured_mac"], vela_conv_mac_cycles=conv["vela_mac_cycles"],
                        vela_conv_op_cycles=conv["vela_op_cycles"], vela_graph_cycles_total=preds[s["config"]]["vela_cycles"],
                        vela_graph_label="Vela sum of op cycles", npu_active=s["npu"]["a_median"], graph="Conv alone"))
    return out


# ---- run -------------------------------------------------------------------------------------------------------------
def write_csv(p: pathlib.Path, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in keys})


def run(kernels_p: str, out: str) -> dict:
    facts = json.loads(pathlib.Path(kernels_p).read_text())
    inv = read_csv(INVENTORY)
    dt = json.loads(DTYPES.read_text())
    whole = {(r["model"], r["axis"]): r for r in read_csv(S6_WHOLE)}
    s6_cov = {m: float(whole[(m, "mac")]["coverage"]) for m in MODELS}
    meas, dom = measured_configs(), e1r_domain()
    ops, integ, mm = [], {}, {}
    for m in MODELS:
        rows = [r for r in inv if r["model"] == m]
        meta = json.loads(META[m].read_text())
        m7 = json.loads((M7_WL / f"{m}.drwl.json").read_text())
        integ[m] = integrity(m, facts, m7, meta, {r["vela_sha256"] for r in rows})
        mo = operators(m, rows, meta, dt, facts.get(m), integ[m]["ok"], meas, dom)
        ops += mo
        mm[m] = model_metrics(mo, float(whole[(m, "mac")]["measured"]), float(whole[(m, "mac")]["npu_active"]))
    v = verdict(integ, mm, s6_cov)
    bb_cov = {r["model"]: float(r["validly_measured_shape_coverage"]) for r in read_csv(BB_DIR / "coverage.csv")}
    cov = [dict(model=m, static_structural=mm[m]["coverage_ABC"], evidence_supported=mm[m]["coverage_AB"],
                direct_model_shape=mm[m]["coverage_A"], share_1x1df=mm[m]["share_1x1df"],
                stage6_mac_calibrated_vela=s6_cov[m], stage6bb_validly_measured_vela=bb_cov.get(m, 0.0),
                model_level_explanation_excess_share_AB=mm[m]["excess_share_AB"], bound_AB=mm[m]["bound_AB"]) for m in MODELS]
    pp = [dict(r, h1uc_mac_level=p_level(r["axes"], mm[r["model"]]), share_1x1df=mm[r["model"]]["share_1x1df"],
               coverage_AB=mm[r["model"]]["coverage_AB"], excess_share_AB=mm[r["model"]]["excess_share_AB"],
               bound_AB=mm[r["model"]]["bound_AB"]) for r in read_csv(S6_MATRIX)]
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    write_csv(o / "operator_mapping.csv", [{k: x[k] for k in x if k not in FACTOR_KEYS} for x in ops])
    write_csv(o / "h1uc_operators.csv", [x for x in ops if x["is_target"]])
    write_csv(o / "model_metrics.csv", [dict(model=m, **{k: (json.dumps(v_) if isinstance(v_, dict) else v_)
                                                         for k, v_ in mm[m].items()}) for m in MODELS])
    write_csv(o / "coverage_comparison.csv", cov)
    write_csv(o / "p1_p7.csv", pp)
    write_csv(o / "e2_link.csv", e2_rows())
    summary = dict(contract="evidence/stage6m/contract.md",
                   kernels_sha256=hashlib.sha256(pathlib.Path(kernels_p).read_bytes()).hexdigest(), integrity=integ, e1r_domain={k: sorted(map(str, v)) if isinstance(v, set)
                   else v for k, v in dom.items()}, measured_groups={k: [x["group"] for x in v_] for k, v_ in meas.items()},
                   models=mm, verdict=v)
    (o / "stage6m_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str))
    return summary


FACTOR_KEYS = ("kernels", "h1uc", "ideal", "eff", "loss", "F_U", "F_sp", "F_cout", "F_cin", "interaction", "factor_check",
               "h1uc_no_spatial", "h1uc_no_cout_pad", "h1uc_no_cin_pad", "h1uc_over_vela_mac_cycles", "cin_chunks")


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    assert cmd == "run", cmd
    s = run(*a[:2])
    print(json.dumps(dict(verdict=s["verdict"], integrity={m: x["ok"] for m, x in s["integrity"].items()}), indent=1))
