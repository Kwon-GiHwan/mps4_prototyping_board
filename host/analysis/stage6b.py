#!/usr/bin/env python3
"""Stage 6B (evidence/stage6b/rules.md, fixed at b9f3824 before any compile): 1x1 DepthFirst Conv of the seven MLEK models
-> execution groups -> compile candidates -> static match classes -> representative selection -> coverage opportunity.
Board-free. The container side (host/container/stage6b_models.py) compiles the candidates; this module only reads its
<cfg>.s6b.json records.

  python3 stage6b.py candidates <out.json>             Phase 1-2: groups and the per-model top-5 candidates
  python3 stage6b.py run <compiled dir> <out dir>      Phase 3-4: classify, select, coverage, CSVs + summary.json
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = REPO / "results" / "fi101_stage4" / "stage4_operator_inventory.csv"
DTYPES = REPO / "results" / "fi101_stage6" / "tflite_dtypes.json"
S6_ESTIMATES = REPO / "results" / "fi101_stage6" / "model_activity_estimates.csv"
S6_APPLICABILITY = REPO / "results" / "fi101_stage6" / "unit_model_applicability.csv"
MODELS = ("ad_medium_int8", "kws_micronet_m", "mobilenet_v2_1.0_224_INT8", "rnnoise_INT8", "vww4_128_128_INT8",
          "wav2letter_pruned_int8", "yolo-fastest_192_face_v4")
GROUP_KEY = ("npu_op", "kernel", "stride", "padding", "npu_ifm_hwc", "npu_ofm_hwc", "ifm_block", "ofm_block", "ofm_ublock",
             "traversal", "ifm_memory", "ofm_memory", "ifm_format", "ofm_format", "cascade", "tflite_activation")
SHAPE = ("npu_ifm_hwc", "npu_ofm_hwc", "kernel", "stride", "padding", "mac_count")
EXEC = ("traversal", "ifm_block", "ofm_block", "ofm_ublock")
PLACE = ("ifm_memory", "ofm_memory", "ifm_format", "ofm_format", "cascade")
WEIGHT = ("weight_bytes", "staging_usage", "tflite_activation")
TOP_N = 5
MAX_SELECT = 10
MEASURED_CIN = (40, 128)
LIMITS = dict(fast_size=0x60000, arena_size=0x200000, model_region=32 << 20)
RANK = {"EXACT_STATIC_MATCH": 0, "PARTIAL_STATIC_MATCH": 1, "NOT_REPRODUCIBLE": 2}


def load(path=INVENTORY) -> list[dict]:
    return list(csv.DictReader(open(path)))


def model_macs(rows: list[dict]) -> dict:
    tot = collections.Counter()
    for r in rows:
        if r["cpu"] == "0":
            tot[r["model"]] += int(r["mac_count"] or 0)
    return dict(tot)


def int8_out(r: dict, dt: dict) -> bool:
    ops = dt.get(r["model"], {}).get("ops", {})
    return ops.get(r["tflite_op_index"], {}).get("outputs") == ["INT8"]


def targets(rows: list[dict], dt: dict) -> list[dict]:
    return [r for r in rows if r["cpu"] == "0" and r["npu_op"] == "Conv2D" and r["kernel"] == "1x1"
            and r["traversal"] == "DepthFirst" and int(r["mac_count"] or 0) > 0 and int8_out(r, dt)]


def gkey(r: dict) -> tuple:
    return tuple(r[k] for k in GROUP_KEY)


def groups(tg: list[dict]) -> list[dict]:
    """One dict per execution group, ids G01.. in order of first appearance after sorting by key (deterministic)."""
    by = collections.defaultdict(list)
    for r in tg:
        by[gkey(r)].append(r)
    out = []
    for i, k in enumerate(sorted(by)):
        mem = by[k]
        rep = sorted(mem, key=lambda r: (-int(r["mac_count"]), r["model"], int(r["scheduled_id"])))[0]
        wb = [int(r["weight_bytes"] or 0) for r in mem]
        out.append(dict(group=f"G{i + 1:02d}", key=dict(zip(GROUP_KEY, k)), members=mem, rep=rep,
                        weight_bytes_min=min(wb), weight_bytes_max=max(wb),
                        macs={m: sum(int(r["mac_count"]) for r in mem if r["model"] == m) for m in {r["model"] for r in mem}}))
    return out


def candidates(gs: list[dict], tot: dict) -> list[dict]:
    """Per model top-N groups by in-model MAC share (tie: smallest scheduled_id of the group in that model); de-duplicated."""
    chosen, per_model = {}, {}
    for m in MODELS:
        mine = [g for g in gs if m in g["macs"]]
        mine.sort(key=lambda g: (-g["macs"][m], min(int(r["scheduled_id"]) for r in g["members"] if r["model"] == m)))
        per_model[m] = [g["group"] for g in mine[:TOP_N]]
        for g in mine[:TOP_N]:
            chosen[g["group"]] = g
    return [chosen[k] for k in sorted(chosen)], per_model


def cfg_name(g: dict) -> str:
    return f"s6b_{g['group'].lower()}"


def candidate_manifest(gs, per_model, tot) -> dict:
    return dict(rules="evidence/stage6b/rules.md", per_model_top=per_model, model_macs=tot,
                candidates=[dict(group=g["group"], config=cfg_name(g), key=g["key"], n_members=len(g["members"]),
                                 rep=dict(model=g["rep"]["model"], scheduled_id=g["rep"]["scheduled_id"],
                                          tflite_op_index=g["rep"]["tflite_op_index"],
                                          weight_bytes=g["rep"]["weight_bytes"], mac_count=g["rep"]["mac_count"],
                                          staging_usage=g["rep"]["staging_usage"]),
                                 weight_bytes_range=[g["weight_bytes_min"], g["weight_bytes_max"]],
                                 macs=g["macs"]) for g in gs])


# ---- Phase 3: static match ------------------------------------------------------------------------------------------
def form_class(rep: dict, form: dict | None) -> dict:
    """rep = the original inventory row; form = the compiled record of one form (conv row + feasibility) or None."""
    if not form:
        return dict(cls="NOT_REPRODUCIBLE", diffs=["not compiled"])
    feas = [k for k, ok in form.get("feasible", {}).items() if not ok]
    row = form.get("conv_row") or {}
    shape = [k for k in SHAPE if str(row.get(k, "")) != str(rep[k])]
    if feas or shape or not row:
        return dict(cls="NOT_REPRODUCIBLE", diffs=feas + shape + ([] if row else ["no conv row"]))
    diffs = [k for k in EXEC + PLACE + WEIGHT if str(row.get(k, "")) != str(rep[k])]
    return dict(cls="PARTIAL_STATIC_MATCH" if diffs else "EXACT_STATIC_MATCH", diffs=diffs)


def classify(rep: dict, rec: dict | None) -> dict:
    forms = {f: form_class(rep, (rec or {}).get("forms", {}).get(f)) for f in ("F_PLAIN", "F_CTX")}
    best = min(forms, key=lambda f: (RANK[forms[f]["cls"]], f != "F_PLAIN"))
    return dict(forms=forms, form=best, cls=forms[best]["cls"])


# ---- Phase 2 (selection) and Phase 4 -----------------------------------------------------------------------------
def score(g: dict, tot: dict) -> float:
    return sum(v / tot[m] for m, v in g["macs"].items())


def cin_of(g: dict) -> int:
    return int(g["key"]["npu_ifm_hwc"].split("x")[2])


def tie_key(g: dict, tot: dict, all_mac: int) -> tuple:
    return (-score(g, tot), -len(g["macs"]), -sum(g["macs"].values()) / all_mac,
            0 if MEASURED_CIN[0] <= cin_of(g) <= MEASURED_CIN[1] else 1, g["rep"]["model"], int(g["rep"]["scheduled_id"]))


def select(cands: list[dict], cls: dict, tot: dict) -> list[dict]:
    """cls: group -> classify() result. Returns [(group, reason)] in selection order, at most MAX_SELECT."""
    elig = [g for g in cands if cls[g["group"]]["cls"] == "EXACT_STATIC_MATCH"]
    all_mac = sum(tot.values())
    out, picked = [], set()
    for m in MODELS:
        if len(out) >= MAX_SELECT:
            break
        if any(m in g["macs"] for g in elig if g["group"] in picked):
            continue
        mine = sorted((g for g in elig if m in g["macs"] and g["group"] not in picked),
                      key=lambda g: (-g["macs"][m] / tot[m],) + tie_key(g, tot, all_mac))
        if mine:
            out.append(dict(group=mine[0]["group"], reason=f"model_floor:{m}")); picked.add(mine[0]["group"])
    for g in sorted(elig, key=lambda g: tie_key(g, tot, all_mac)):
        if len(out) >= MAX_SELECT:
            break
        if g["group"] not in picked:
            out.append(dict(group=g["group"], reason="score")); picked.add(g["group"])
    return out


def s6_mac_coverage(path=S6_ESTIMATES) -> dict:
    out = {}
    for r in csv.DictReader(open(path)):
        if r.get("axis") == "mac":
            out[r["model"]] = float(r["calibrated_coverage"])
    return out


def s6_calibrated_ids(path=S6_APPLICABILITY) -> set:
    return {(r["model"], r["scheduled_id"]) for r in csv.DictReader(open(path))
            if r.get("mac_tier") in ("T0", "T1_INTERP")}


def coverage(rows, tg, gs, cands, cls, sel, tot, s6cov, calibrated) -> list[dict]:
    gmap = {g["group"]: g for g in gs}
    cset = {g["group"] for g in cands}
    sset = {s["group"] for s in sel}
    out = []
    for m in MODELS:
        t = tot.get(m, 0) or 1
        mine = [r for r in tg if r["model"] == m]
        share = lambda rs: sum(int(r["mac_count"]) for r in rs) / t
        of = {g: [r for r in gmap[g]["members"] if r["model"] == m] for g in gmap}
        by_cls = collections.Counter()
        for g in cset:
            by_cls[cls[g]["cls"]] += share(of[g])
        sel_rows = [r for g in sset for r in of[g]]
        new = [r for r in sel_rows if (m, r["scheduled_id"]) not in calibrated]
        covered = {(m, r["scheduled_id"]) for r in sel_rows} | {x for x in calibrated if x[0] == m}
        rest = sorted((r for r in rows if r["model"] == m and r["cpu"] == "0" and int(r["mac_count"] or 0) > 0
                       and (m, r["scheduled_id"]) not in covered), key=lambda r: -int(r["mac_count"]))
        top = collections.Counter()
        for r in rest:
            top[f"{r['npu_op']} {r['kernel']} {r['traversal']} Cin{r['cin']}"] += int(r["mac_count"]) / t
        out.append(dict(model=m, stage6_mac_coverage=s6cov.get(m), depthfirst_1x1_share=share(mine),
                        candidate_share=sum(by_cls.values()), candidate_exact_share=by_cls["EXACT_STATIC_MATCH"],
                        candidate_partial_share=by_cls["PARTIAL_STATIC_MATCH"],
                        candidate_not_reproducible_share=by_cls["NOT_REPRODUCIBLE"],
                        selected_share=share(sel_rows),
                        projected_upper_bound=(s6cov.get(m) or 0) + share(new),
                        remaining_top3="; ".join(f"{k} {v:.1%}" for k, v in top.most_common(3))))
    return out


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def run(compiled: pathlib.Path, out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, dt = load(), json.loads(DTYPES.read_text())
    tot, tg = model_macs(rows), targets(load(), dt)
    gs = groups(tg)
    cands, per_model = candidates(gs, tot)
    recs = {g["group"]: (json.loads(p.read_text()) if (p := compiled / f"{cfg_name(g)}.s6b.json").exists() else None)
            for g in cands}
    cls = {g["group"]: classify(g["rep"], recs[g["group"]]) for g in cands}
    sel = select(cands, cls, tot)
    cov = coverage(rows, tg, gs, cands, cls, sel, tot, s6_mac_coverage(), s6_calibrated_ids())
    write_csv(out / "depthfirst_operator_inventory.csv",
              [dict(group=next(g["group"] for g in gs if r in g["members"]), model_share=int(r["mac_count"]) / tot[r["model"]],
                    **{k: r[k] for k in ("model", "scheduled_id", "tflite_op_index", "tflite_op", "tflite_inputs",
                                         "tflite_outputs", "npu_ifm_hwc", "npu_ofm_hwc", "cin", "cout", "stride", "padding",
                                         "kernel", "mac_count", "traversal", "ifm_block", "ofm_block", "ofm_ublock",
                                         "weight_bytes", "staging_usage", "tflite_activation", "ifm_memory", "ofm_memory",
                                         "ifm_format", "ofm_format", "cascade", "cms_offsets", "vela_npu_cycles",
                                         "vela_mac_cycles")}) for r in tg])
    write_csv(out / "depthfirst_execution_groups.csv",
              [dict(group=g["group"], candidate=g["group"] in {c["group"] for c in cands}, n_members=len(g["members"]),
                    models=" ".join(sorted(g["macs"])), score=score(g, tot),
                    weight_bytes_min=g["weight_bytes_min"], weight_bytes_max=g["weight_bytes_max"],
                    rep=f"{g['rep']['model']}#{g['rep']['scheduled_id']}", **g["key"],
                    **{f"share_{m}": g["macs"].get(m, 0) / tot[m] for m in MODELS if tot.get(m)}) for g in gs])
    sel_ids = {s["group"]: s["reason"] for s in sel}
    write_csv(out / "static_mapping_comparison.csv",
              [dict(group=g["group"], config=cfg_name(g), form=f, cls=cls[g["group"]]["forms"][f]["cls"],
                    diffs=" ".join(cls[g["group"]]["forms"][f]["diffs"]),
                    **{f"orig_{k}": g["rep"][k] for k in SHAPE + EXEC + PLACE + WEIGHT},
                    **{f"ind_{k}": ((recs[g["group"]] or {}).get("forms", {}).get(f, {}).get("conv_row") or {}).get(k, "")
                       for k in SHAPE + EXEC + PLACE + WEIGHT},
                    orig_vela_npu_cycles=g["rep"]["vela_npu_cycles"],
                    ind_vela_npu_cycles=((recs[g["group"]] or {}).get("forms", {}).get(f, {}).get("conv_row") or {})
                    .get("vela_npu_cycles", ""))
               for g in cands for f in ("F_PLAIN", "F_CTX")])
    write_csv(out / "representative_selection.csv",
              [dict(group=g["group"], config=cfg_name(g), cls=cls[g["group"]]["cls"], form=cls[g["group"]]["form"],
                    score=score(g, tot), n_models=len(g["macs"]), cin=cin_of(g), selected=g["group"] in sel_ids,
                    reason=sel_ids.get(g["group"], "" if cls[g["group"]]["cls"] == "EXACT_STATIC_MATCH"
                                       else "not eligible: " + cls[g["group"]]["cls"]),
                    order=[s["group"] for s in sel].index(g["group"]) + 1 if g["group"] in sel_ids else "")
               for g in sorted(cands, key=lambda g: tie_key(g, tot, sum(tot.values())))])
    write_csv(out / "coverage_opportunity.csv", cov)
    summary = dict(rules="evidence/stage6b/rules.md", n_targets=len(tg), n_groups=len(gs), n_candidates=len(cands),
                   per_model_top=per_model, classes=collections.Counter(c["cls"] for c in cls.values()),
                   selected=sel, coverage=cov)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list) -> None:
    if argv[0] == "candidates":
        rows, dt = load(), json.loads(DTYPES.read_text())
        tot = model_macs(rows)
        gs = groups(targets(rows, dt))
        cands, per_model = candidates(gs, tot)
        pathlib.Path(argv[1]).write_text(json.dumps(candidate_manifest(cands, per_model, tot), indent=1))
        print(len(gs), "groups,", len(cands), "candidates")
    elif argv[0] == "run":
        s = run(pathlib.Path(argv[1]), pathlib.Path(argv[2]))
        print(json.dumps({k: s[k] for k in ("n_targets", "n_groups", "n_candidates", "classes", "selected")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
