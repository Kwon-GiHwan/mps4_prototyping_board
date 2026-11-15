#!/usr/bin/env python3
"""Stage 6B Revision A judge (evidence/stage6b/revision_a/revision_a_contract.md, committed before any A2 compile).
Reads the container records <cfg>.ra.json (host/container/stage6b_revision_a_models.py); every pass/fail rule is here.
The Stage 6B rules (stage6b.py, b9f3824) are reused unchanged: the EXACT/PARTIAL/NOT definition (form_class), the
selection (select) and the coverage arithmetic. Original Stage 6B results are not read back into or rewritten.

  python3 stage6b_revision_a.py run <compiled dir> <out dir>
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6b as S  # noqa: E402

REPO = S.REPO
MANIFEST = REPO / "evidence" / "stage6b" / "revision_a" / "revision_a_manifest.json"
S6B_COMPILED = REPO / "evidence" / "stage6b" / "compiled"
BOARD_CONTRACT = REPO / "evidence" / "stage6b" / "revision_a" / "revision_a_board_contract.md"
FORMS = ("A0", "A1", "A2")                                   # order = tie preference (least wrapper first)
S6B_FORM = {"A0": "F_PLAIN", "A1": "F_CTX"}                  # forms whose bytes must equal Stage 6B 0c4bf4c
CLS = {"EXACT_STATIC_MATCH": "EXACT_A", "PARTIAL_STATIC_MATCH": "PARTIAL_A", "NOT_REPRODUCIBLE": "NOT_REPRODUCIBLE_A"}
RANK = {"EXACT_A": 0, "PARTIAL_A": 1, "NOT_REPRODUCIBLE_A": 2}
EXPECTED_OPS = {"A0": ["Conv2D"], "A1": ["Add", "Conv2D", "Add"], "A2": ["Add", "Conv2D", "Add"]}
CONV_OUT_NAME = {"A0": "ofm", "A1": "conv_out", "A2": "conv_out"}
# Conv kernel registers compared one kernel instruction (stripe) at a time. Not compared: base addresses (placement
# inside a region), the last DMA length register and the DMAs issued since the previous kernel (prefetch context).
REG_CONFIG = ("ifm_depth_m1", "ifm_precision", "ofm_width_m1", "ofm_height_m1", "ofm_depth_m1", "ofm_precision",
              "blk_width_m1", "blk_height_m1", "blk_depth_m1", "acc_format", "ifm_width0_m1", "ifm_height0_m1",
              "kernel_width_m1", "kernel_height_m1", "kernel_stride", "ifm_stride_x", "ifm_stride_y", "ifm_stride_c",
              "ofm_stride_x", "ofm_stride_y", "ofm_stride_c", "weight_length", "weight1_length", "weight2_length",
              "weight3_length")
REG_REGION = ("ifm_region", "ofm_region", "weight_region")
REG_NOT_COMPARED = ("ifm_base0", "ofm_base0", "dma_len", "dma_before", "offset", "kind")
NUMPY_MAX_ABS = 1            # independent float64 requantisation vs TFLite fixed point: rounding only
INFORMATIVE_MIN = 0.10       # share of elements strictly inside the clamp range (can reveal a wrong result)
SELF_ADD_MAX_ABS = 1         # A2 final = requant(2 * conv_out, 2 * scale): conv_out within rounding
TA_PROFILE = 1
PLACEMENT_DDR = 0
N_BASE_MAX = 8
PASS, FAIL, NV = "PASS", "FAIL", "NOT_VERIFIED"


# ---- per-form checks ---------------------------------------------------------------------------------------------------
def exact_a(rep: dict, form: dict | None) -> dict:
    c = S.form_class(rep, form)
    return dict(cls=CLS[c["cls"]], diffs=c["diffs"])


def tensor_eq(a: dict | None, b: dict | None, keys=("shape", "type", "scale", "zp", "qdim", "sha256")) -> list[str]:
    if not a or not b:
        return ["missing"]
    return [k for k in keys if a.get(k) != b.get(k)]


def check_params(src_tensors: dict, form: dict) -> dict:
    """The generated graph's Conv tensors are the source tensors (weights/bias bytes, scales, zero points, dtypes, shapes).
    IFM/OFM carry no data; their quantisation and shape must still match (the A1/A2 Conv IFM/OFM are intermediates)."""
    g = form.get("graph_conv") or {}
    d = {k: tensor_eq(src_tensors.get(k), g.get(k), ("shape", "type", "scale", "zp", "qdim") + (("sha256",) if k in ("w", "b") else ()))
         for k in ("ifm", "w", "b", "ofm")}
    bad = {k: v for k, v in d.items() if v}
    return dict(status=FAIL if bad else PASS, diffs=bad)


def check_reference(label: str, form: dict) -> dict:
    r = form.get("refcheck") or {}
    if not r:
        return dict(status=FAIL, diffs=["no reference facts"])
    diffs = []
    if not form.get("feasible", {}).get("reference") or not r.get("final_sha256_equals_ref"):
        diffs.append("reference output")
    if form.get("golden_sha256") != (form.get("reference") or {}).get("ref_sha256"):
        diffs.append("golden != BUILTIN_REF output")
    if r.get("numpy_vs_ref_max_abs") is None or r["numpy_vs_ref_max_abs"] > NUMPY_MAX_ABS:
        diffs.append("independent conv vs reference")
    if r.get("conv_out_informative", 0) < INFORMATIVE_MIN:
        diffs.append("conv_out saturated")
    if r.get("final_informative", 0) < INFORMATIVE_MIN:
        diffs.append("final output saturated")
    if label == "A2" and (r.get("final_vs_conv_out_max_abs") is None or r["final_vs_conv_out_max_abs"] > SELF_ADD_MAX_ABS):
        diffs.append("self-ADD output != conv_out")
    return dict(status=FAIL if diffs else PASS, diffs=diffs)


def check_repeat(form: dict) -> dict:
    sec = form.get("second") or {}
    keys = ("model_sha256", "vela_sha256", "drwl_sha256", "manifest_sha256", "cms_sha256", "conv_row", "conv_kernels")
    diffs = [k for k in keys if form.get(k) is None or form.get(k) != sec.get(k)]
    return dict(status=FAIL if diffs else PASS, diffs=diffs)


def check_fusion(label: str, form: dict) -> dict:
    row = form.get("conv_row") or {}
    diffs = []
    if form.get("npu_ops") != EXPECTED_OPS[label]:
        diffs.append(f"scheduled ops {form.get('npu_ops')}")
    if form.get("cpu_rows"):
        diffs.append("cpu ops")
    if str(row.get("fused_names")) != "1":
        diffs.append("conv fused")
    if row.get("name") != CONV_OUT_NAME[label]:
        diffs.append("conv output tensor")
    return dict(status=FAIL if diffs else PASS, diffs=diffs)


def reg_diffs(orig: list | None, mine: list | None, keys: tuple) -> list[str] | None:
    """None = cannot be compared (NOT_VERIFIED); [] = equal; otherwise the differing registers."""
    if orig is None or any(k is None for k in orig):
        return None
    if mine is None or any(k is None for k in mine):
        return ["no kernels"]
    if len(orig) != len(mine):
        return [f"n_kernels {len(orig)} != {len(mine)}"]
    return sorted({k for a, b in zip(orig, mine) for k in keys if a.get(k) != b.get(k)})


def check_registers(original: dict, inv_vela: str, form: dict) -> dict:
    if not original or not original.get("vela_sha256", "").startswith(inv_vela) or original.get("n_ethosu_ops") != 1:
        return dict(status=NV, diffs=["original compile not the Stage 4 inventory compile"])
    d = reg_diffs(original.get("conv_kernels"), form.get("conv_kernels"), REG_CONFIG + REG_REGION)
    if d is None:
        return dict(status=NV, diffs=["original kernels missing"])
    return dict(status=FAIL if d else PASS, diffs=d)


def check_package(form: dict) -> dict:
    diffs = [k for k, ok in form.get("feasible", {}).items() if not ok]
    if not form.get("feasible"):
        diffs.append("no feasibility")
    if form.get("ta_profile") != TA_PROFILE:
        diffs.append(f"ta_profile {form.get('ta_profile')}")
    if form.get("placement") != PLACEMENT_DDR:
        diffs.append(f"placement {form.get('placement')}")
    if not isinstance(form.get("n_base"), int) or not 1 <= form["n_base"] <= N_BASE_MAX:
        diffs.append(f"n_base {form.get('n_base')}")
    return dict(status=FAIL if diffs else PASS, diffs=diffs)


CHECKS = ("params", "reference", "repeat", "fusion", "registers", "package")


def judge_form(label: str, rep: dict, man: dict, rec: dict) -> dict:
    form = (rec.get("forms") or {}).get(label)
    ex = exact_a(rep, form)
    if not form:
        return dict(cls=ex["cls"], diffs=ex["diffs"], checks={k: dict(status=FAIL, diffs=["no record"]) for k in CHECKS},
                    board_eligible=False, second_cls=ex["cls"])
    checks = dict(params=check_params(man["tensors"], form), reference=check_reference(label, form),
                  repeat=check_repeat(form), fusion=check_fusion(label, form),
                  registers=check_registers(rec.get("original"), man["inventory_vela_sha256"], form),
                  package=check_package(form))
    second = dict(form, conv_row=(form.get("second") or {}).get("conv_row"))
    sec_cls = exact_a(rep, second)["cls"]
    ok = ex["cls"] == "EXACT_A" and all(c["status"] == PASS for c in checks.values())
    return dict(cls=ex["cls"], diffs=ex["diffs"], checks=checks, board_eligible=ok, second_cls=sec_cls)


def judge_candidate(rep: dict, man: dict, rec: dict | None) -> dict:
    forms = {f: judge_form(f, rep, man, rec or {}) for f in FORMS}
    best = min(FORMS, key=lambda f: (RANK[forms[f]["cls"]], FORMS.index(f)))
    board = next((f for f in FORMS if forms[f]["board_eligible"]), None)
    return dict(forms=forms, form=best, cls=forms[best]["cls"], board_form=board, board_eligible=board is not None)


# ---- provenance (INVALID) ---------------------------------------------------------------------------------------------
def provenance(man: dict, cands: list[dict], recs: dict, s6b: dict) -> list[str]:
    """Errors that make the whole Revision A run INVALID."""
    err = []
    if man.get("n") != len(cands) or sorted(c["group"] for c in man["candidates"]) != sorted(g["group"] for g in cands):
        err.append("candidate set differs from the fixed 26")
    for c in man["candidates"]:
        rec = recs.get(c["group"])
        if rec is None:
            err.append(f"{c['group']}: no record"); continue
        if rec.get("source", {}).get("model_sha256") != c["model_sha256"]:
            err.append(f"{c['group']}: source model sha256")
        if any(tensor_eq(c["tensors"][k], rec.get("source", {}).get("tensors", {}).get(k)) for k in ("ifm", "w", "b", "ofm")):
            err.append(f"{c['group']}: source tensors")
        for f in FORMS:
            if f not in (rec.get("forms") or {}):
                err.append(f"{c['group']}: form {f} missing")
        for f, old in S6B_FORM.items():
            prev = ((s6b.get(c["group"]) or {}).get("forms") or {}).get(old, {}).get("drwl_sha256")
            now = ((rec.get("forms") or {}).get(f) or {}).get("drwl_sha256")
            if prev is None or prev != now:
                err.append(f"{c['group']}: {f} bytes differ from Stage 6B {old}")
    return err


# ---- selection, coverage, verdict ------------------------------------------------------------------------------------
def eligibility(judged: dict) -> dict:
    """Stage 6B select() takes 'EXACT_STATIC_MATCH' as eligible; Revision A eligibility is BOARD_ELIGIBLE (contract §6)."""
    return {g: dict(cls="EXACT_STATIC_MATCH" if j["board_eligible"] else "NOT_ELIGIBLE") for g, j in judged.items()}


def select(cands: list[dict], judged: dict, tot: dict) -> list[dict]:
    return S.select(cands, eligibility(judged), tot)


def second_judged(judged: dict) -> dict:
    """The classification from the second compile: same checks, class from the second conv row."""
    out = {}
    for g, j in judged.items():
        be = next((f for f in FORMS if j["forms"][f]["board_eligible"] and j["forms"][f]["second_cls"] == "EXACT_A"), None)
        out[g] = dict(board_eligible=be is not None)
    return out


def coverage(rows, tg, gs, cands, judged, sel, tot, s6cov, calibrated) -> list[dict]:
    gmap = {g["group"]: g for g in gs}
    cset = {g["group"] for g in cands}
    exact = {g for g in cset if judged[g]["cls"] == "EXACT_A"}
    elig = {g for g in cset if judged[g]["board_eligible"]}
    sset = {s["group"] for s in sel}
    out = []
    for m in S.MODELS:
        t = tot.get(m, 0)
        own = lambda grp: [r for g in grp for r in gmap[g]["members"] if r["model"] == m]
        mac = lambda rs: sum(int(r["mac_count"]) for r in rs)
        df = [r for r in tg if r["model"] == m]
        sel_rows = own(sset)
        new = [r for r in sel_rows if (m, r["scheduled_id"]) not in calibrated]
        status = ("NOT_APPLICABLE" if not df else "NO_CANDIDATE" if not own(cset) else
                  "NO_ELIGIBLE" if not own(elig) else "ELIGIBLE")
        share = lambda x: x / t if t else 0.0
        out.append(dict(model=m, status=status, n_mac_model=t, n_mac_depthfirst_1x1=mac(df), n_mac_candidates=mac(own(cset)),
                        n_mac_exact_a=mac(own(exact)), n_mac_board_eligible=mac(own(elig)), n_mac_selected=mac(sel_rows),
                        static_reproduction_coverage=share(mac(own(exact))),
                        board_eligible_coverage=share(mac(own(elig))),
                        selected_measurement_coverage=share(mac(sel_rows)),
                        validated_hw_coverage=s6cov.get(m),
                        projected_after_board_upper_bound=(s6cov.get(m) or 0) + share(mac(new))))
    return out


def verdict(prov_err: list, judged: dict, sel: list, sel2: list, board_contract: bool) -> dict:
    if prov_err:
        return dict(verdict="INVALID", reasons=prov_err)
    reasons = []
    new = sorted(g for g, j in judged.items() if j["board_eligible"] and g != "G14")
    if not new:
        reasons.append("no BOARD_ELIGIBLE shape besides G14")
    if [s["group"] for s in sel] != [s["group"] for s in sel2]:
        reasons.append("selection differs between the two compiles")
    if not sel:
        reasons.append("nothing selected")
    if not board_contract:
        reasons.append("board contract not written")
    return dict(verdict="NEEDS_REVISION" if reasons else "READY_FOR_BOARD_REVIEW", reasons=reasons, new_board_eligible=new)


# ---- run -----------------------------------------------------------------------------------------------------------
def load_json(p: pathlib.Path):
    return json.loads(p.read_text()) if p.exists() else None


def run(compiled: pathlib.Path, out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, dt = S.load(), json.loads(S.DTYPES.read_text())
    tot, tg = S.model_macs(rows), S.targets(rows, dt)
    gs = S.groups(tg)
    cands, _ = S.candidates(gs, tot)
    man = json.loads(MANIFEST.read_text())
    mby = {c["group"]: c for c in man["candidates"]}
    recs = {g["group"]: load_json(compiled / f"{S.cfg_name(g)}.ra.json") for g in cands}
    recs = {k: v for k, v in recs.items() if v is not None}
    s6b = {g["group"]: load_json(S6B_COMPILED / f"{S.cfg_name(g)}.s6b.json") for g in cands}
    prov = provenance(man, cands, recs, s6b)
    judged = {g["group"]: judge_candidate(g["rep"], mby[g["group"]], recs.get(g["group"])) for g in cands}
    sel = select(cands, judged, tot)
    sel2 = S.select(cands, eligibility(second_judged(judged)), tot)
    cov = coverage(rows, tg, gs, cands, judged, sel, tot, S.s6_mac_coverage(), S.s6_calibrated_ids())
    v = verdict(prov, judged, sel, sel2, BOARD_CONTRACT.exists())
    sel_ids = {s["group"]: (i + 1, s["reason"]) for i, s in enumerate(sel)}
    res_rows = []
    for g in cands:
        j = judged[g["group"]]
        r = dict(group=g["group"], config=S.cfg_name(g), rep=f"{g['rep']['model']}#{g['rep']['scheduled_id']}",
                 tflite_op_index=g["rep"]["tflite_op_index"], mac_count=g["rep"]["mac_count"],
                 models=" ".join(sorted(g["macs"])), score=S.score(g, tot), cls=j["cls"], best_form=j["form"],
                 board_eligible=j["board_eligible"], board_form=j["board_form"] or "",
                 selected=g["group"] in sel_ids, order=sel_ids.get(g["group"], ("", ""))[0],
                 reason=sel_ids.get(g["group"], ("", ""))[1])
        for f in FORMS:
            fj = j["forms"][f]
            r[f"{f}_cls"] = fj["cls"]
            r[f"{f}_diffs"] = " ".join(fj["diffs"])
            r[f"{f}_board_eligible"] = fj["board_eligible"]
            for k in CHECKS:
                r[f"{f}_{k}"] = fj["checks"][k]["status"]
                r[f"{f}_{k}_diffs"] = json.dumps(fj["checks"][k]["diffs"]) if fj["checks"][k]["diffs"] else ""
        res_rows.append(r)
    S.write_csv(out / "revision_a_results.csv", res_rows)
    S.write_csv(out / "revision_a_coverage.csv", cov)
    summary = dict(contract="evidence/stage6b/revision_a/revision_a_contract.md", n_candidates=len(cands),
                   classes=dict(collections.Counter(j["cls"] for j in judged.values())),
                   classes_by_form={f: dict(collections.Counter(j["forms"][f]["cls"] for j in judged.values())) for f in FORMS},
                   board_eligible=sorted(g for g, j in judged.items() if j["board_eligible"]),
                   board_eligible_by_form={f: sorted(g for g, j in judged.items() if j["forms"][f]["board_eligible"])
                                           for f in FORMS},
                   selected=sel, selected_second_compile=sel2, provenance_errors=prov, verdict=v, coverage=cov)
    (out / "revision_a_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list) -> None:
    if argv[0] == "run":
        s = run(pathlib.Path(argv[1]), pathlib.Path(argv[2]))
        print(json.dumps({k: s[k] for k in ("classes", "board_eligible", "selected", "verdict")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
