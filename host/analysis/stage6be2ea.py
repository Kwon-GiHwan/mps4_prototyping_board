#!/usr/bin/env python3
"""Stage 6B-E2E-A (evidence/stage6b/stage6be2ea/contract.md). Track A: does stage4k.identity's fixed `placement == 0`
term touch any archived judgement? Track B: E2D recomputation, A2 graph-IO candidates, the W0-P0 Vela over-prediction.

  python3 stage6be2ea.py track-a <out dir>
  python3 stage6be2ea.py track-b <facts dir> <out dir>
"""
from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
REPO = pathlib.Path(__file__).resolve().parents[2]

# ---- Track A ------------------------------------------------------------------------------------------------------------
# experiment directory -> (judge module, does the judge call stage4k.identity for every config?)
IDENTITY_JUDGES = {
    "evidence/stage4k": ("stage4k.config_result", True),
    "evidence/stage4ao": ("stage4ao (K.identity)", True),
    "evidence/stage4aoe": ("stage4aoe.identity_a1 -> K.identity", True),
    "evidence/stage4wd": ("stage4wd -> stage4aoe.config_result -> identity_a1", True),
    "evidence/stage6b/stage6bb": ("stage6bb.identity_of", True),
    "evidence/stage6b/stage6be1": ("stage6be1 -> stage6bb.identity_of", True),
    "evidence/stage6b/stage6be1r": ("stage6be1r -> stage6bb.identity_of", True),
    "evidence/stage6b/stage6be2b": ("stage6be2b -> stage6bb.identity_of", True),
    "evidence/stage6b/stage6be2d/raw": ("stage6be2d (3ca60a7, original) -> stage6bb.identity_of", True),
    "evidence/stage6b/stage6be2d/raw_a": ("stage6be2d Amendment A (placement_identity replaces the term)", False),
    "evidence/stage4_placement": ("stage4p (own placement check)", False),
}
SETTLED = {"evidence/stage6b/stage6be2d/raw": dict(rejudged=True, remeasured=True)}   # Amendment A: rejudge + boots 449-457


def experiment_of(rel: str) -> str:
    for k in IDENTITY_JUDGES:                      # keys end at a directory; matched with the trailing "/"
        if rel.startswith(k + "/") or rel == k:
            return k
    return "/".join(rel.split("/")[:2])


def classify(uses_identity: bool, placements: set, has_field: bool, settled: dict | None) -> str:
    """contract A2."""
    if not uses_identity:
        return "UNAFFECTED"
    if not has_field:
        return "UNRESOLVED"
    if placements <= {0}:
        return "UNAFFECTED"
    s = settled or {}
    if not s.get("remeasured"):
        return "REMEASUREMENT_REQUIRED"
    if not s.get("rejudged"):
        return "REJUDGE_REQUIRED"
    return "JUDGE_FALSE_REJECTION"


def overall(classes: list[str]) -> str:
    if "REMEASUREMENT_REQUIRED" in classes:
        return "HISTORICAL_REMEASUREMENT_REQUIRED"
    if "REJUDGE_REQUIRED" in classes:
        return "HISTORICAL_REJUDGE_REQUIRED"
    if "UNRESOLVED" in classes:
        return "HISTORICAL_IMPACT_UNRESOLVED"
    return "NO_HISTORICAL_IMPACT"


def scan(root: pathlib.Path) -> list[dict]:
    rows = []
    for p in sorted(root.glob("**/raw_runs.json")):
        rel = str(p.relative_to(REPO))
        try:
            raw = json.loads(p.read_text())[1:]
        except (ValueError, IndexError):
            rows.append(dict(file=rel, experiment=experiment_of(rel), n=0, placements=[], has_field=False, parse_error=True))
            continue
        recs = [x.get("record") or {} for x in raw if isinstance(x, dict)]
        has = bool(recs) and all("placement" in r for r in recs)
        rows.append(dict(file=rel, experiment=experiment_of(rel), n=len(recs), has_field=has,
                         placements=sorted({r.get("placement") for r in recs if "placement" in r})))
    return rows


def track_a(out: str) -> dict:
    import stage6be2d as D
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    rows = scan(REPO / "evidence")
    import csv
    with open(o / "raw_scan.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["experiment", "file", "n", "has_field", "placements"], lineterminator="\n", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    exps = {}
    for r in rows:
        e = exps.setdefault(r["experiment"], dict(placements=set(), has_field=True, files=0, runs=0))
        e["placements"] |= set(r["placements"]); e["has_field"] &= r["has_field"]; e["files"] += 1; e["runs"] += r["n"]
    table = []
    for e, v in sorted(exps.items()):
        judge, uses = IDENTITY_JUDGES.get(e, ("no stage4k.identity path", False))
        table.append(dict(experiment=e, judge=judge, uses_identity=uses, files=v["files"], runs=v["runs"],
                          placements=sorted(x for x in v["placements"] if x is not None), placement_field=v["has_field"],
                          cls=classify(uses, v["placements"], v["has_field"], SETTLED.get(e))))
    # E2D original session re-judged with the corrected judge (Amendment A), a separate artefact
    wl = REPO / "evidence/stage6b/stage6be2d/workloads"
    import shutil, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp()); shutil.copytree(wl, tmp / "wl")
    m = json.loads((wl / D.MANIFEST).read_text())
    m["REF"]["boot"], m["W0-P0-L500"]["boot"], m["W0-P1-L500"]["boot"] = 440, 441, 442
    (tmp / "wl" / D.MANIFEST).write_text(json.dumps(m))
    raw = REPO / "evidence/stage6b/stage6be2d/raw/evsweep_s6be2d_run_l500"
    rej = {k: D.config_result(raw, tmp / "wl", k)["status"] for k in ("REF", "W0-P0-L500", "W0-P1-L500")}
    gate = D.repro_gate(str(raw), str(tmp / "wl"), str(REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"))["verdict"]
    shutil.rmtree(tmp)
    summary = dict(contract="evidence/stage6b/stage6be2ea/contract.md (Track A)", experiments=table,
                   e2d_original_rejudge=dict(judge="stage6be2d Amendment A (347712c) placement_identity", boots=[440, 441, 442],
                                             status=rej, reference_gate=gate, original_verdict_kept="MEASUREMENT_INVALID"),
                   verdict=overall([t["cls"] for t in table]))
    (o / "trackA_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- Track B pure rules ---------------------------------------------------------------------------------------------------
def c1(board_bytes: dict, npu: dict, vela_bw: dict) -> str:
    """{lat: ...}; board EXT read bytes per NPU cycle vs Vela's Dram IFM channel bandwidth."""
    above = [board_bytes[L] / npu[L] > vela_bw[L] for L in (500, 1000)]
    if all(above):
        return "SUPPORTED"
    if not any(above):
        return "CONTRADICTED"
    return "UNRESOLVED"


def c2(inflated: float, actual: float, board_burst: float, vela_burst: float) -> str:
    f = inflated / actual if actual else math.inf
    if f >= 1.3 and board_burst > vela_burst:
        return "SUPPORTED"
    if f < 1.1:
        return "CONTRADICTED"
    return "UNRESOLVED"


def c3(vela_actual: float, board: float) -> str:
    return "SUPPORTED" if 0.8 <= board / vela_actual <= 1.25 else "CONTRADICTED"


def cause(c1_: str, c2_: str) -> str:
    if c1_ == "SUPPORTED" and c2_ == "SUPPORTED":
        return "SUPPORTED"
    if c1_ == "CONTRADICTED":
        return "CONTRADICTED"
    return "UNRESOLVED"


def track_b_verdict(i1: bool, io_only: bool, sram_fits: bool, reference: bool) -> str:
    if not i1:
        return "INVALID"
    if io_only and sram_fits and reference:
        return "READY_FOR_BOARD_REVIEW"
    if io_only:
        return "PARTIAL_IDENTIFIABILITY"
    return "NOT_IDENTIFIABLE"


def sram_arena(sram_free: int, model_base: int, ddr_arena: int, arena_len: int, limit: int = 0x31400000) -> int:
    """firmware placement.c placement_sram_arena: 0 if it does not fit."""
    mask = 0x10000 - 1
    start = (sram_free + mask) & ~mask
    if model_base & mask or ddr_arena < model_base:
        return 0
    a = start + (ddr_arena - model_base)
    return a if a <= limit and arena_len <= limit - a else 0


# ---- Track B run ------------------------------------------------------------------------------------------------------------
E2D_SUM = REPO / "results/fi101_stage6b/stage6be2d/stage6be2d_summary.json"
E2D_RAW = REPO / "evidence/stage6b/stage6be2d/raw_a"
E2D_WL = REPO / "evidence/stage6b/stage6be2d/workloads"
E2C_FACTS = REPO / "evidence/stage6b/stage6be2c/facts/configs.json"
REF375 = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"
FAST_END = 0x31000000 + 0x60000          # driver fast memory (cache_arena) end, the runner's sram_free
EXT_REGIONCFG = 3                        # REGIONCFG field value on the EXT port (placement.h: DDR = 3, SRAM = 0/1)


def regions_on_ext(n_base: int, placement: int) -> set:
    import stage4aoe as AOE
    r = AOE.placement_regioncfg(n_base, placement)
    return {i for i in range(n_base) if (r >> (2 * i)) & 3 == EXT_REGIONCFG}


def recompute_e2d(tmp: pathlib.Path) -> bool:
    import stage6be2d as D
    D.judge(str(E2D_RAW / "evsweep_s6be2d_a_run_l500"), str(E2D_RAW / "evsweep_s6be2d_a_run_l1000"), str(E2D_WL), str(REF375), str(tmp))
    return (tmp / "stage6be2d_summary.json").read_bytes() == E2D_SUM.read_bytes()


def e2d_table() -> list[dict]:
    s = json.loads(E2D_SUM.read_text())
    e2c = json.loads(E2C_FACTS.read_text())["candidates"]
    src = {"W0-P0": "W0-P0", "W0-P1": None, "W1-P0": "W1-P0-c0", "W1-P1": "W1-P1"}
    io = {"W0-P0": "IFM/OFM = graph IO, DDR (region 1)", "W0-P1": "IFM/OFM = graph IO, on-chip SRAM (region 1, placement 1)",
          "W1-P0": "graph IO DDR (region 1), intermediates DDR (region 1)", "W1-P1": "graph IO DDR (region 1), intermediates SRAM (fast, region 2)"}
    rows = []
    for k, r in s["results"].items():
        if k == "REF":
            continue
        cell, lat = k.rsplit("-L", 1)
        m, b = r["metrics"], r["pass_b"]
        f = e2c[src[cell]]["L500" if lat == "500" else "L1000"] if src[cell] else None
        rows.append(dict(key=k, cell=cell, latency=int(lat), npu=m["npu_active"], npu_range=m["npu_active_range"], mac=m["mac_active"],
                         dpu=m["mac_dpu_active"], ao=m["ao_active"], wd=m["wd_active"], wd_stalled=m["wd_stalled"],
                         sram_rd_beats=b["130"], sram_rd_trans=b["128"], sram_wr_beats=b["135"], sram_wr_trans=b["132"],
                         ext_rd_beats=b["386"], ext_rd_trans=b["384"], ext_wr_beats=b["391"],
                         vela_npu=int(f["summary"]["cycles_npu"]) if f else None, vela_sram=int(f["summary"]["cycles_sram_access"]) if f else None,
                         vela_dram=int(f["summary"]["cycles_dram_access"]) if f else None, vela_total=int(f["summary"]["cycles_total"]) if f else None,
                         kernels=len(f["kernels"]) if f else 1, io_path=io[cell], ta_profile=1,
                         image="70090f1" if lat == "500" else "L1000"))
    return rows


def b2(F: dict) -> dict:
    import stage6be2c as C2
    raw = E2D_RAW / "evsweep_s6be2d_a_run_l500/conds/e2d_w1p1/wfe/raw_runs.json"
    rec = json.loads(raw.read_text())[1]["record"]
    n_base = rec["n_base"]
    ext0, ext1 = regions_on_ext(n_base, 0), regions_on_ext(n_base, 1)
    e2c = json.loads(E2C_FACTS.read_text())["candidates"]["W1-P1"]["L500"]
    used = {}
    for k in e2c["kernels"]:
        for n in ("NPU_SET_IFM_REGION", "NPU_SET_IFM2_REGION", "NPU_SET_OFM_REGION", "NPU_SET_WEIGHT_REGION", "NPU_SET_SCALE_REGION"):
            if n in k["regs"]:
                used.setdefault(n.split("_SET_")[1].replace("_REGION", ""), set()).add(k["regs"][n])
    tensors_on_ext_b3 = {t: sorted(v & ext1) for t, v in used.items() if v & ext1}
    weight_only = set(tensors_on_ext_b3) <= {"WEIGHT", "SCALE"}
    arena = sram_arena(FAST_END, rec["model_base"], rec["arena_base"], rec["arena_len"])
    base, est = F["a2io"]["A2-base"]["L500"], F["a2io"]["B3-est-Shared_Sram"]
    c = C2.compare(base, est["L500"]) if est["L500"].get("ok") else None
    est_ok = bool(c and c["same_n_conv"] and c["weights_equal"] and c["same_ops"] and not set(c["diff"]) - {"ADDRESS"})
    vela_b3 = None
    if est_ok and C2.estimator_only(est["L500"], est["L1000"]):
        vela_b3 = {L: int(est[f"L{L}"]["summary"]["cycles_total"]) for L in (500, 1000)}
    sep = F["a2io"]["B12-separate-io"]["L500"]
    return dict(b0="e2d_w1p1 (928296b1), placement 0", b3="same DRWL, header word 7 = 1", same_command_stream=True,
                io_placement_only=True, n_base=n_base, regions_on_ext_placement0=sorted(ext0), regions_on_ext_placement1=sorted(ext1),
                tensor_regions={t: sorted(v) for t, v in used.items()}, tensors_on_ext_b3=tensors_on_ext_b3,
                weight_only_ext_path=weight_only, sram_arena=hex(arena) if arena else 0, sram_fits=bool(arena),
                reference="b9341e6f (BUILTIN_REF, same golden as B0)",
                b3_vela=dict(source="A2 --memory-mode Shared_Sram", usable=est_ok, diff=c["diff"] if c else None,
                             n_conv=c["n_conv"] if c else None, totals=vela_b3,
                             label="NO_COMPARABLE_VELA_ESTIMATE" if vela_b3 is None else "ESTIMATE"),
                b1_b2=dict(status="UNAVAILABLE", why=(sep.get("stderr_tail") or "").strip().splitlines()[-1] if not sep.get("ok") else "compiled"),
                w0p1_board_evidence=None)


def b3(F: dict, table: list[dict]) -> dict:
    import stage6be2a as A
    a0 = F["a0"]["base"]
    conv = [r for r in a0["db"]["perf_debug"] if r.get("ifm_memory") == "Dram" and r.get("DramFeatureMap_read")][0]
    num = lambda v: float(v or 0)
    fm, wt, sc = num(conv["DramFeatureMap_read"]), num(conv["DramWeights_read"]), num(conv["DramScales_read"])
    eff = num(conv["Dram_read_efficiency"])
    inflated = fm + wt + sc
    actual = inflated * eff
    main = [m for m in a0["db"]["perf_debug_main"] if m.get("id") == conv["id"]][0]
    vela_burst = int(main["ifm_block_c"]) * 8 // 8
    bw = {L: A.channel_bw(dict(A.VELA["Dram"], read_latency=L), "IFM") for L in (500, 1000)}
    w0 = {r["latency"]: r for r in table if r["cell"] == "W0-P0"}
    board_bytes = {L: w0[L]["ext_rd_beats"] * 16 for L in (500, 1000)}
    npu = {L: w0[L]["npu"] for L in (500, 1000)}
    burst = {L: w0[L]["ext_rd_beats"] / w0[L]["ext_rd_trans"] * 16 for L in (500, 1000)}
    r1, r2, r3 = c1(board_bytes, npu, bw), c2(inflated, actual, min(burst.values()), vela_burst), c3(actual, board_bytes[500])
    perf = [r for r in a0["db"]["perf"] if r["operator"] == "Conv2D"][0]
    c4 = dict(total=int(perf["op_cycles"]), npu=int(perf["npu_cycles"]), dram_ac=int(perf["Dram_ac"]),
              dram_dominates=int(perf["op_cycles"]) == int(perf["Dram_ac"]) > 2 * int(perf["npu_cycles"]))
    # POST_HOC_DESCRIPTIVE (computed after the rules): the IFM read at Vela's channel rate without the burst inflation
    fm_actual = fm - inflated * (1 - eff)
    post = {L: dict(fm_actual_over_bw=fm_actual / bw[L], board=npu[L], ratio=npu[L] / (fm_actual / bw[L]),
                    board_ifm_rate_if_weights_as_vela=(board_bytes[L] - (wt + sc)) / npu[L], vela_bw=bw[L]) for L in (500, 1000)}
    w0p1 = {r["latency"]: r for r in table if r["cell"] == "W0-P1"}
    return dict(vela=dict(fm_read_inflated=fm, weights_read=wt, scales_read=sc, read_efficiency=eff, inflated_total=inflated,
                          actual_total=actual, fm_actual=fm_actual, ifm_block_depth=int(main["ifm_block_c"]), assumed_burst=vela_burst,
                          channel_bw=bw, fm_ac=int(num(conv["DramFeatureMap_ac"]))),
                board=dict(ext_read_bytes=board_bytes, npu=npu, mean_burst=burst, rate=({L: board_bytes[L] / npu[L] for L in (500, 1000)})),
                C1=r1, C2=r2, C3=r3, C4=c4, overprediction_cause=cause(r1, r2),
                post_hoc_descriptive=post,
                w0p1_ext_reads=dict(board_bytes={L: w0p1[L]["ext_rd_beats"] * 16 for L in (500, 1000)},
                                    vela_weights_scales_actual=wt + sc, note="W0-P1 EXT write 0: graph IO on SRAM; EXT read = weights + scales + command stream"))


def sensitivity(F: dict, table: list[dict]) -> list[dict]:
    import stage6be2a as A
    base = F["a0"]["base"]
    b0 = float(base["summary"]["cycles_total"])
    w0 = {r["latency"]: r["npu"] for r in table if r["cell"] == "W0-P0"}
    out = []
    for name, ch in F["variants"].items():
        if name == "base":
            continue
        v = F["a0"][name]
        cls = A.sensitivity_class(base, v)
        row = dict(variant=name, parameter=ch["parameter"], value=ch["value"], cls=cls, label="POSTHOC_SENSITIVITY")
        if cls == "ESTIMATOR_ONLY_COMPARABLE":
            t = float(v["summary"]["cycles_total"])
            row.update(vela_total=t, ratio_to_base=t / b0, board_l500=w0[500], board_over_vela=w0[500] / t)
        out.append(row)
    return out


def track_b(facts: str, out: str) -> dict:
    import csv
    import shutil
    import tempfile
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    F = json.loads((pathlib.Path(facts) / "vela.json").read_text())
    tmp = pathlib.Path(tempfile.mkdtemp())
    i1 = recompute_e2d(tmp)
    shutil.rmtree(tmp)
    table = e2d_table()
    with open(o / "e2d_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]), lineterminator="\n"); w.writeheader(); w.writerows(table)
    io = b2(F)
    ana = b3(F, table)
    io["w0p1_board_evidence"] = ana["w0p1_ext_reads"]
    sens = sensitivity(F, table)
    with open(o / "w0p0_sensitivity.csv", "w", newline="") as f:
        keys = []
        for r in sens:
            keys += [k for k in r if k not in keys]
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(sens)
    summary = dict(contract="evidence/stage6b/stage6be2ea/contract.md (Track B)", i1_e2d_recompute_identical=i1, b2=io, b3=ana,
                   verdict=track_b_verdict(i1, io["io_placement_only"], io["sram_fits"], True),
                   overprediction_cause=ana["overprediction_cause"])
    (o / "trackB_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    if sys.argv[1] == "track-a":
        s = track_a(sys.argv[2]); print(json.dumps(dict(verdict=s["verdict"], rejudge=s["e2d_original_rejudge"],
                                                         experiments=[(t["experiment"], t["uses_identity"], t["placements"], t["cls"]) for t in s["experiments"]]), indent=1))
    elif sys.argv[1] == "track-b":
        s = track_b(sys.argv[2], sys.argv[3]); print(json.dumps({k: s[k] for k in ("i1_e2d_recompute_identical", "b2", "b3", "verdict")}, indent=1, default=str))
