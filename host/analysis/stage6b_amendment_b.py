#!/usr/bin/env python3
"""Stage 6B Revision A Amendment B judge (evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md).
POSTHOC_AMENDMENT: the Revision A judge with its `fusion` check replaced by the B-1 gate; every other gate, the selection
and the coverage arithmetic are the Revision A / Stage 6B functions, unchanged. ADDITIONAL_VALIDATION: the B-2b input
fixture, judged and reported apart.

  python3 stage6b_amendment_b.py run <compiled dir> <fusion facts.json> <fixture.json|-> <out dir>
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6b as S  # noqa: E402
import stage6b_revision_a as RA  # noqa: E402

REPO = S.REPO
BOARD_CONTRACT = REPO / "evidence" / "stage6b" / "revision_a" / "amendment_b" / "amendment_b_board_contract.md"
PRESERVED, CHANGED, UNVERIFIED = "ORIGINAL_ACTIVATION_PRESERVED", "EXECUTION_CHANGED", "FUSION_UNVERIFIED"
ACT_OP = {"RELU": "Relu", "RELU6": "Relu6"}
ACT_OPS = ("Relu", "Relu6", "ReluN1To1", "Clip", "Sigmoid", "Tanh", "LeakyRelu", "HardSwish")
ACT_REGS = ("activation", "activation_min", "activation_max", "ofm_zero_point", "ofm_scale")
WRAP = {"A0": ([], []), "A1": (["Add"], ["Add"]), "A2": (["Add"], ["Add"])}
SATURATION_DIFFS = {"conv_out saturated", "final output saturated"}
FIXTURE_GROUPS = ("G09", "G11", "G12", "G14", "G23", "G25", "G28", "G40", "G41", "G52", "G53", "G56", "G57")
UNRESOLVED = "VALIDATION_UNRESOLVED"


# ---- B-1 fusion gate ---------------------------------------------------------------------------------------------------
def act_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("npu_op") in ACT_OPS]


def is_dead(r: dict) -> bool:
    """A logical row that issues no kernel instruction and no MAC or cycle estimate."""
    return not str(r.get("cms_offsets") or "").strip() and str(r.get("mac_count")) == "0" and str(r.get("vela_op_cycles")) == "0"


def expected_rows(label: str, oacts: list[str]) -> tuple[list[str], list[int]]:
    """The wrapper's rows around the Conv and exactly the original Conv's activation rows."""
    pre, post = WRAP[label]
    conv = ["Conv2D"] + list(oacts)
    idx = [0] * len(pre) + [len(pre)] * len(conv) + [len(pre) + 1] * len(post)
    return pre + conv + post, idx


def expected_kernels(label: str, n_conv: int) -> list[str]:
    pre, post = WRAP[label]
    return ["ELEMENTWISE"] * len(pre) + ["CONV"] * n_conv + ["ELEMENTWISE"] * len(post)


def fusion_gate(label: str, man: dict, inv_rows: list[dict], rec: dict, facts: dict | None) -> dict:
    """B-1: ORIGINAL_ACTIVATION_PRESERVED / EXECUTION_CHANGED / FUSION_UNVERIFIED with the failing conditions."""
    form = (rec.get("forms") or {}).get(label) or {}
    orig, ff = (facts or {}).get("original") or {}, ((facts or {}).get("forms") or {}).get(label)
    missing = []
    if not orig.get("vela_sha256", "").startswith(man["inventory_vela_sha256"]) or orig.get("n_ethosu_ops") != 1:
        missing.append("original compile not the inventory compile")
    if not orig.get("conv_act") or any(k is None for k in orig["conv_act"]):
        missing.append("original activation registers")
    if not ff or not ff.get("conv_act") or any(k is None for k in ff["conv_act"]):
        missing.append("form activation registers")
    if ff and ff.get("cms_sha256") != form.get("cms_sha256"):
        missing.append("stream digest != record")
    if not form.get("rows") or not inv_rows:
        missing.append("logical rows")
    if missing:
        return dict(status=RA.FAIL, cls=UNVERIFIED, diffs=missing)
    act, diffs = man["activation"], []
    # F1 the original Conv had exactly this activation
    oacts = [r["npu_op"] for r in act_rows(inv_rows)]
    if oacts != ([ACT_OP[act]] if act in ACT_OP else []):
        diffs.append(f"F1 original activation rows {oacts} vs {act}")
    # F2 same activation kind and parameters
    row = form.get("conv_row") or {}
    oconv = next((r for r in inv_rows if r.get("npu_op") == "Conv2D"), {})
    if row.get("tflite_activation") != oconv.get("tflite_activation"):
        diffs.append("F2 tflite_activation")
    if len(ff["conv_act"]) != len(orig["conv_act"]):
        diffs.append("F2 kernel count")
    else:
        bad = sorted({k for a, b in zip(orig["conv_act"], ff["conv_act"]) for k in ACT_REGS if a.get(k) != b.get(k)})
        diffs += [f"F2 {k}" for k in bad]
    # F3 Conv execution settings
    d = RA.reg_diffs((rec.get("original") or {}).get("conv_kernels"), form.get("conv_kernels"), RA.REG_CONFIG + RA.REG_REGION)
    if d is None:
        return dict(status=RA.FAIL, cls=UNVERIFIED, diffs=["original conv kernels"])
    diffs += [f"F3 {k}" for k in d]
    # F4 no kernel from the activation, kernel structure as the wrapper's
    if not all(is_dead(r) for r in act_rows(inv_rows) + act_rows(form["rows"])):
        diffs.append("F4 activation row issues work")
    if ff["kernel_types"] != expected_kernels(label, len(orig["conv_act"])):
        diffs.append(f"F4 kernels {ff['kernel_types']}")
    # F6 logical structure
    ops, idx = expected_rows(label, oacts)
    if form.get("npu_ops") != ops or [int(r["tflite_op_index"]) for r in form["rows"]] != idx:
        diffs.append(f"F6 rows {form.get('npu_ops')}")
    if form.get("cpu_rows"):
        diffs.append("F6 cpu ops")
    if any(str(r.get("fused_names")) != "1" for r in form["rows"]):
        diffs.append("F6 fused names")
    if row.get("name") != RA.CONV_OUT_NAME[label]:
        diffs.append("F6 conv output tensor")
    return dict(status=RA.FAIL if diffs else RA.PASS, cls=CHANGED if diffs else PRESERVED, diffs=diffs)


# ---- B-2b additional validation -----------------------------------------------------------------------------------------
def fixture_gate(fx: dict | None) -> dict:
    if not fx or fx.get("missing") or "input_digest_ok" not in fx:
        return dict(status=UNRESOLVED, diffs=["no fixture facts"])
    if not fx["input_digest_ok"]:
        return dict(status=UNRESOLVED, diffs=["V1 input digest"])
    if fx.get("x_shape") != fx.get("conv_ifm_shape"):
        return dict(status=UNRESOLVED, diffs=["V1 input shape"])
    need = ("conv_in_equals_x", "conv_out_vs_model_mismatch", "numpy_vs_ref_max_abs", "final_vs_conv_out_max_abs",
            "conv_out_informative", "final_informative", "pack_rc")
    if any(fx.get(k) is None for k in need):
        return dict(status=UNRESOLVED, diffs=["fixture facts incomplete"])
    d = []
    if not fx["conv_in_equals_x"]:
        d.append("V2 conv input != x")
    if fx["conv_out_vs_model_mismatch"] != 0:
        d.append("V3 conv_out != model conv output")
    if fx["numpy_vs_ref_max_abs"] > RA.NUMPY_MAX_ABS:
        d.append("V4 independent conv")
    if fx["final_vs_conv_out_max_abs"] > RA.SELF_ADD_MAX_ABS:
        d.append("V5 self-ADD")
    if fx["conv_out_informative"] < RA.INFORMATIVE_MIN:
        d.append("V6 conv_out saturated")
    if fx["final_informative"] < RA.INFORMATIVE_MIN:
        d.append("V6 final saturated")
    if fx["pack_rc"] != 0 or not fx.get("vela_equals_record") or not fx.get("cms_equals_record"):
        d.append("V7 repacked compile differs")
    return dict(status=RA.FAIL if d else RA.PASS, diffs=d)


# ---- judgement -----------------------------------------------------------------------------------------------------------
def judge_form(label: str, rep: dict, man: dict, inv_rows: list[dict], rec: dict, facts: dict | None) -> dict:
    j = RA.judge_form(label, rep, man, rec)
    if not (rec.get("forms") or {}).get(label):
        return dict(j, fusion_cls=UNVERIFIED)
    fg = fusion_gate(label, man, inv_rows, rec, facts)
    checks = dict(j["checks"], fusion=dict(status=fg["status"], diffs=fg["diffs"]))
    ok = j["cls"] == "EXACT_A" and all(c["status"] == RA.PASS for c in checks.values())
    return dict(j, checks=checks, board_eligible=ok, fusion_cls=fg["cls"])


def saturation_only(fj: dict) -> bool:
    """Every gate passes except the reference gate, and that one only by the saturation diffs."""
    ref = fj["checks"]["reference"]
    others = all(c["status"] == RA.PASS for k, c in fj["checks"].items() if k != "reference")
    return fj["cls"] == "EXACT_A" and others and ref["status"] == RA.FAIL and set(ref["diffs"]) <= SATURATION_DIFFS


def judge_candidate(rep: dict, man: dict, inv_rows: list[dict], rec: dict | None, facts: dict | None,
                    fx: dict | None) -> dict:
    forms = {f: judge_form(f, rep, man, inv_rows, rec or {}, facts) for f in RA.FORMS}
    best = min(RA.FORMS, key=lambda f: (RA.RANK[forms[f]["cls"]], RA.FORMS.index(f)))
    board = next((f for f in RA.FORMS if forms[f]["board_eligible"]), None)
    fg = fixture_gate(fx) if man["group"] in FIXTURE_GROUPS else None
    extra = board is None and fg is not None and fg["status"] == RA.PASS and saturation_only(forms["A2"])
    return dict(forms=forms, form=best, cls=forms[best]["cls"], board_form=board, board_eligible=board is not None,
                fixture=fg, board_eligible_with_additional=board is not None or extra)


def fact_provenance(man: dict, recs: dict, facts: dict) -> list[str]:
    """A fusion fact that does not describe the judged stream makes the run INVALID."""
    err = []
    for c in man["candidates"]:
        f = facts.get(c["group"])
        if f is None:
            err.append(f"{c['group']}: no fusion facts"); continue
        for label in RA.FORMS:
            ff, form = (f.get("forms") or {}).get(label), ((recs.get(c["group"]) or {}).get("forms") or {}).get(label) or {}
            if ff and ff.get("cms_sha256") != form.get("cms_sha256"):
                err.append(f"{c['group']} {label}: fusion facts from another stream")
    return err


def inventory_rows(rows: list[dict], man_c: dict) -> list[dict]:
    return [r for r in rows if r["model"] == man_c["model"] and r["tflite_op_index"] == str(man_c["tflite_op_index"])
            and r["vela_sha256"].startswith(man_c["inventory_vela_sha256"])]


def vela_estimates(rec: dict | None) -> dict:
    out = {}
    for f in RA.FORMS:
        form = ((rec or {}).get("forms") or {}).get(f) or {}
        cr = form.get("conv_row") or {}
        num = lambda v: int(v) if str(v).strip().lstrip("-").isdigit() else None
        out[f] = dict(conv_op_cycles=num(cr.get("vela_op_cycles")), conv_npu_cycles=num(cr.get("vela_npu_cycles")),
                      conv_mac_cycles=num(cr.get("vela_mac_cycles")), conv_ao_cycles=num(cr.get("vela_ao_cycles")),
                      conv_cmd_cycles=num(cr.get("vela_cmd_cycles")),
                      graph_op_cycles_sum=sum(num(r.get("vela_op_cycles")) or 0 for r in form.get("rows") or []),
                      rows=[(r.get("npu_op"), num(r.get("vela_op_cycles"))) for r in form.get("rows") or []])
    return out


def run(compiled: pathlib.Path, facts_p: pathlib.Path, fixture_p: str, out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, dt = S.load(), json.loads(S.DTYPES.read_text())
    tot, tg = S.model_macs(rows), S.targets(rows, dt)
    gs = S.groups(tg)
    cands, _ = S.candidates(gs, tot)
    man = json.loads(RA.MANIFEST.read_text())
    mby = {c["group"]: c for c in man["candidates"]}
    recs = {g["group"]: RA.load_json(compiled / f"{S.cfg_name(g)}.ra.json") for g in cands}
    recs = {k: v for k, v in recs.items() if v is not None}
    s6b = {g["group"]: RA.load_json(RA.S6B_COMPILED / f"{S.cfg_name(g)}.s6b.json") for g in cands}
    facts = json.loads(facts_p.read_text())
    fixture = json.loads(pathlib.Path(fixture_p).read_text()) if fixture_p != "-" else {}
    prov = RA.provenance(man, cands, recs, s6b) + fact_provenance(man, recs, facts)
    judged = {g["group"]: judge_candidate(g["rep"], mby[g["group"]], inventory_rows(rows, mby[g["group"]]),
                                          recs.get(g["group"]), facts.get(g["group"]), fixture.get(g["group"]))
              for g in cands}
    sel = RA.select(cands, judged, tot)
    sel2 = S.select(cands, RA.eligibility(RA.second_judged(judged)), tot)
    with_extra = {g: dict(board_eligible=j["board_eligible_with_additional"]) for g, j in judged.items()}
    sel_extra = S.select(cands, RA.eligibility(with_extra), tot)
    cov = RA.coverage(rows, tg, gs, cands, judged, sel, tot, S.s6_mac_coverage(), S.s6_calibrated_ids())
    v = RA.verdict(prov, judged, sel, sel2, BOARD_CONTRACT.exists())
    sel_ids = {s["group"]: i + 1 for i, s in enumerate(sel)}
    res_rows = []
    for g in cands:
        j = judged[g["group"]]
        r = dict(group=g["group"], rep=f"{g['rep']['model']}#{g['rep']['scheduled_id']}", models=" ".join(sorted(g["macs"])),
                 activation=mby[g["group"]]["activation"], mac_count=g["rep"]["mac_count"], cls=j["cls"],
                 best_form=j["form"], board_eligible=j["board_eligible"], board_form=j["board_form"] or "",
                 fixture=(j["fixture"] or {}).get("status", ""),
                 fixture_diffs=" ".join((j["fixture"] or {}).get("diffs", [])),
                 board_eligible_with_additional=j["board_eligible_with_additional"],
                 selected=g["group"] in sel_ids, order=sel_ids.get(g["group"], ""))
        for f in RA.FORMS:
            fj = j["forms"][f]
            r[f"{f}_cls"], r[f"{f}_fusion_cls"] = fj["cls"], fj.get("fusion_cls", "")
            r[f"{f}_board_eligible"] = fj["board_eligible"]
            for k in RA.CHECKS:
                r[f"{f}_{k}"] = fj["checks"][k]["status"]
                r[f"{f}_{k}_diffs"] = json.dumps(fj["checks"][k]["diffs"]) if fj["checks"][k]["diffs"] else ""
        res_rows.append(r)
    S.write_csv(out / "amendment_b_results.csv", res_rows)
    S.write_csv(out / "amendment_b_coverage.csv", cov)
    summary = dict(
        label="POSTHOC_AMENDMENT", contract="evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md",
        n_candidates=len(cands), classes=dict(collections.Counter(j["cls"] for j in judged.values())),
        fusion_by_form={f: dict(collections.Counter(j["forms"][f].get("fusion_cls") for j in judged.values())) for f in RA.FORMS},
        fusion_a2_exact={g: j["forms"]["A2"].get("fusion_cls") for g, j in sorted(judged.items()) if j["forms"]["A2"]["cls"] == "EXACT_A"},
        board_eligible=sorted(g for g, j in judged.items() if j["board_eligible"]),
        board_eligible_by_form={f: sorted(g for g, j in judged.items() if j["forms"][f]["board_eligible"]) for f in RA.FORMS},
        selected=sel, selected_second_compile=sel2, provenance_errors=prov, verdict=v, coverage=cov,
        additional_validation=dict(label="ADDITIONAL_VALIDATION (MLEK input fixture, B-2b)",
                                   fixture={g: j["fixture"] for g, j in sorted(judged.items()) if j["fixture"]},
                                   board_eligible_with_additional=sorted(g for g, j in judged.items()
                                                                         if j["board_eligible_with_additional"]),
                                   selection_scenario=sel_extra),
        vela_estimates={g: vela_estimates(recs.get(g)) for g in sorted(judged)})
    (out / "amendment_b_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list) -> None:
    if argv[0] == "run":
        s = run(pathlib.Path(argv[1]), pathlib.Path(argv[2]), argv[3], pathlib.Path(argv[4]))
        print(json.dumps({k: s[k] for k in ("classes", "fusion_a2_exact", "board_eligible", "verdict")}, indent=1))
        print(json.dumps({k: s["additional_validation"][k] for k in ("board_eligible_with_additional",)}, indent=1))
        print("selected", [x["group"] for x in s["selected"]])


if __name__ == "__main__":
    main(sys.argv[1:])
