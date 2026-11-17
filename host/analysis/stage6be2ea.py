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


if __name__ == "__main__":
    if sys.argv[1] == "track-a":
        s = track_a(sys.argv[2]); print(json.dumps(dict(verdict=s["verdict"], rejudge=s["e2d_original_rejudge"],
                                                         experiments=[(t["experiment"], t["uses_identity"], t["placements"], t["cls"]) for t in s["experiments"]]), indent=1))
