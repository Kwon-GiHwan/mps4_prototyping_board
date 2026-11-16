#!/usr/bin/env python3
"""Stage 6B-E1-R (evidence/stage6b/stage6be1r/contract.md): the revised eligibility, rank and selection, the frozen
predictions, and the verdict. Unchanged imports: stage6br (hypotheses, 5c801f7), stage6be1 (categories, classify,
shape_result, verdict, 3a83175), stage6bb (config_result, repro_gate, 0a99697). New here: the cycle floor, the memory
check, the rank key, the execution-config de-dup, the DPU extra slot, the build conditions, the D-PW verdict over D-U16
and D-U8, and the descriptive NPU_ACTIVE table.

  stage6be1r.py select  <grid.json> <builds.json|-> <out dir>
  stage6be1r.py predict <build.json> <selection.json> <compiler.json> <workloads dir>
  stage6be1r.py judge   <root> <workloads dir> <reference folder> <caps ref> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6bb as BB  # noqa: E402
import stage6be1 as E  # noqa: E402
import stage6br as R  # noqa: E402

REPO = R.REPO
FIRST_BOOT = 428
MIN_VELA_CYCLES = 50_000
N_SELECT = E.N_SELECT
CATEGORIES = E.CATEGORIES
COMPETITORS = E.COMPETITORS
E1_PREDICTIONS = REPO / "evidence/stage6b/stage6be1/workloads/predictions.json"


def existing_shapes() -> set[tuple[int, int, int, int]]:
    """E1 contract §2.3 set plus the six E1 shapes (contract §2.7)."""
    e1 = {(h, w, cin, cout) for cin, h, w, cout in map(E.parse, json.loads(E1_PREDICTIONS.read_text()))}
    return E.existing_shapes() | e1


def vela_cycles(f: dict) -> int:
    return sum(int(r["vela_op_cycles"] or 0) for r in f.get("rows", []))


def eligible(name: str, f: dict, existing: set) -> tuple[bool, list[str]]:
    """Contract §2: E1 §2 terms (1, 5, 7) plus Dram/Dram (2) and the Vela cycle floor (4)."""
    ok, why = E.eligible(name, f, existing)
    conv = [r for r in f.get("rows", []) if r["npu_op"] == "Conv2D"]
    if conv and (conv[0]["ifm_memory"], conv[0]["ofm_memory"]) != ("Dram", "Dram"):
        why.append(f"memory {conv[0]['ifm_memory']}/{conv[0]['ofm_memory']}")
    if vela_cycles(f) < MIN_VELA_CYCLES:
        why.append(f"Vela cycles {vela_cycles(f)} < {MIN_VELA_CYCLES}")
    return not why, why


def case_of(name: str, f: dict) -> dict | None:
    c = E.case_of(name, f)
    return None if c is None else dict(c, vela_cycles=vela_cycles(f))


def min_gap(c: dict) -> float:
    h = R.h1_uc(c)
    return min((abs(f(c) - h) for f in COMPETITORS.values() if f(c) != h), default=0)


def exec_sig(c: dict) -> tuple:
    """Everything H1-UC reads: per-kernel OFM sizes, ublock, blocks, and the per-chunk H1-UC cost of the Cin chunks."""
    costs = tuple(R.mac_chunk(x) for x in R.chunks(c["cin"], c["ifm_block_depth"]))
    return (json.dumps(c["kernels"]), tuple(c["ublock"]), c["ofm_block"], c["ifm_block"], costs)


def rank_key(c: dict):
    return (-E.n_split(c), -min_gap(c), -c["vela_cycles"], c["case"])


def dpu_pw_vs(c: dict, other: str) -> bool:
    return R.DPU_HYP["D-PW"](c) != R.DPU_HYP[other](c)


def build_ok(name: str, b: dict) -> tuple[bool, list[str]]:
    """Contract §2.6 and §2.8 from a stage6be1_models build record."""
    cin, h, w, cout = E.parse(name)
    why = []
    if b.get("pack_rc") != 0 or not b.get("fits"):
        why.append("pack or limits")
    if not b.get("deterministic"):
        why.append("not deterministic")
    if not b.get("golden_sha256") or b.get("golden_sha256") != b.get("ref_sha256"):
        why.append("golden != reference output")
    if (b.get("reference") or {}).get("n") != h * w * cout:
        why.append("reference length")
    return not why, why


def select(cases: list[dict], built: dict[str, bool]) -> dict:
    """Contract §3. built: name -> build passed; a name not in it is assumed buildable and listed in need_build."""
    order = sorted(cases, key=rank_key)
    usable = lambda c: built.get(c["case"], True)  # noqa: E731
    taken: list[dict] = []
    roles: dict[str, str] = {}
    missing = []

    def free(c, extra=False):
        return usable(c) and all(c["case"] != t["case"] and exec_sig(c) != exec_sig(t) for t in taken) and \
            not (extra and any((c["cin"], c["cout"]) == (t["cin"], t["cout"]) for t in taken))

    def take(c, role):
        taken.append(c); roles[c["case"]] = role

    for cat in CATEGORIES:
        pick = next((c for c in order if cat in E.categories(c) and free(c)), None)
        if pick is None:
            missing.append(cat)
        else:
            take(pick, cat)
    pick = next((c for c in order if dpu_pw_vs(c, "D-U8") and free(c, True)), None) or \
        next((c for c in order if free(c, True)), None)
    if pick:
        take(pick, "extra-DPU" if dpu_pw_vs(pick, "D-U8") else "extra")
    pick = next((c for c in order if free(c, True)), None)
    if pick:
        take(pick, "extra")
    names = [c["case"] for c in taken]
    status = "OK" if not missing and len(names) == N_SELECT else "NEEDS_REVISION"
    return dict(status=status, selected=names, role=roles, missing_categories=missing,
                need_build=[n for n in names if n not in built])


def predictions(c: dict) -> dict:
    p = E.predictions(c)
    return dict(p, vela_cycles=c["vela_cycles"], n_split=E.n_split(c), min_gap=min_gap(c),
                dpu_pw_vs_u8_split=p["dpu"]["D-PW"] != p["dpu"]["D-U8"], exec_sig=list(map(str, exec_sig(c))))


def dpu_verdict(shapes: list[dict]) -> str:
    """Contract §7: D-PW against D-U16 and D-U8 on Primary Valid shapes where they differ."""
    pv = [s for s in shapes if s["cls"] == "PRIMARY_VALID"]
    split = {k: [s for s in pv if s["dpu"]["D-PW"]["pred"] != s["dpu"][k]["pred"]] for k in ("D-U16", "D-U8")}
    if any(not s["dpu"]["D-PW"]["match"] for v in split.values() for s in v):
        return "D-PW_CONTRADICTED"
    return "D-PW_CONSISTENT" if all(split.values()) else "INSUFFICIENT_EVIDENCE"


def npu_table(r: dict) -> dict:
    """Descriptive (contract §7, not a verdict input): NPU_ACTIVE per pass, range, absolute range."""
    m = r.get("metrics") or {}
    a, ra = m.get("A_35"), m.get("A_35_range")
    return dict(a_median=a, a_range=ra, a_range_pct=None if not a or ra is None else 100 * ra / a,
                b_median=m.get("B_35"), b_range=m.get("B_35_range"))


# ---- commands -----------------------------------------------------------------------------------------------------------
def cmd_select(grid_p: str, builds_p: str, out: str) -> dict:
    grid = json.loads(pathlib.Path(grid_p).read_text())
    builds = {} if builds_p == "-" else json.loads(pathlib.Path(builds_p).read_text())
    built = {n: build_ok(n, b)[0] for n, b in builds.items()}
    ex = existing_shapes()
    table, cases = [], []
    for name, f in sorted(grid.items()):
        ok, why = eligible(name, f, ex)
        c = case_of(name, f)
        row = dict(name=name, eligible=ok, why="; ".join(why), vela_cycles=vela_cycles(f))
        if c:
            row.update(traversal=c["traversal"], ublock="x".join(map(str, c["ublock"])), ifm_block=c["ifm_block"],
                       ofm_block=c["ofm_block"], n_kernels=len(c["kernels"]), n_split=E.n_split(c), min_gap=min_gap(c),
                       categories=" ".join(E.categories(c)), h1_uc=R.h1_uc(c), n_mac=c["n_mac"],
                       dpu_pw_vs_u8=dpu_pw_vs(c, "D-U8"))
        if name in builds:
            row.update(build_ok=built[name], build_why="; ".join(build_ok(name, builds[name])[1]))
        table.append(row)
        if ok:
            cases.append(c)
    sel = select(cases, built)
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    R.S.write_csv(o / "candidates.csv", table)
    per_cat = {k: sum(k in E.categories(c) for c in cases) for k in CATEGORIES}
    (o / "selection.json").write_text(json.dumps(dict(
        sel, n_grid=len(grid), n_eligible=len(cases), eligible_per_category=per_cat, builds_tried=sorted(builds),
        builds_failed=sorted(n for n, v in built.items() if not v),
        ranking=[c["case"] for c in sorted(cases, key=rank_key)][:40]), indent=1))
    return sel


def cmd_predict(build_p: str, sel_p: str, compiler_p: str, wl: str) -> dict:
    """E1's manifest/identity/predictions writer (boots from FIRST_BOOT), then the E1-R prediction fields."""
    E.FIRST_BOOT = FIRST_BOOT
    E.cmd_predict(build_p, sel_p, wl)
    build = json.loads(pathlib.Path(build_p).read_text())
    comp = json.loads(pathlib.Path(compiler_p).read_text())
    wlp = pathlib.Path(wl)
    preds = json.loads((wlp / "predictions.json").read_text())
    for name in preds:
        preds[name].update(predictions(case_of(name, build[name])), model_sha256=build[name]["model_sha256"],
                           compiler=dict(vela_version=comp["vela_version"], package_digest=comp["package_digest"]))
    (wlp / "predictions.json").write_text(json.dumps(preds, indent=1))
    return preds


def cmd_judge(root: str, wl: str, ref: str, caps: str, out: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    preds = json.loads((wlp / "predictions.json").read_text())
    gate = BB.repro_gate(root, wl, ref, caps) if (rootp / "conds" / BB.REF / "wfe" / "runs.csv").exists() \
        else dict(verdict="FAIL", why="UNMEASURED")
    raw = {n: BB.config_result(rootp, wlp, n, caps) for n in [BB.REF, *preds]}
    shapes = [dict(E.shape_result(raw[n], preds[n]), npu=npu_table(raw[n])) for n in preds]
    summary = dict(contract="evidence/stage6b/stage6be1r/contract.md", ta_profile=1, image="70090f1",
                   reference_gate=gate, reference_npu=npu_table(raw[BB.REF]), shapes=shapes,
                   verdict=E.verdict(gate, shapes), dpu_verdict=dpu_verdict(shapes),
                   counts={k: sum(s["cls"] == k for s in shapes) for k in ("PRIMARY_VALID", "MAC_ONLY_DIAGNOSTIC", "INVALID_OR_UNRESOLVED")})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be1r_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    r = dict(select=lambda: cmd_select(*a[:3]), predict=lambda: cmd_predict(*a[:4]),
             judge=lambda: cmd_judge(*a[:5]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:4000])
