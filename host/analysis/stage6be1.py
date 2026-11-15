#!/usr/bin/env python3
"""Stage 6B-E1 (evidence/stage6b/stage6be1/contract.md): candidate eligibility, category selection and frozen predictions
from the container's static facts, and the H1-UC verdict on the board results. The hypotheses are stage6br's (5c801f7),
imported unchanged; the board checks are stage6bb's config_result / repro_gate, imported unchanged.

  stage6be1.py select  <grid.json> <out dir>
  stage6be1.py predict <build.json> <selection.json> <workloads dir>        (manifest + predictions.json)
  stage6be1.py judge   <root> <workloads dir> <reference folder> <caps ref> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6bb as BB  # noqa: E402
import stage6br as R  # noqa: E402

REPO = R.REPO
FIRST_BOOT = 421
COMPETITORS = {**{k: f for k, f in R.MAC_HYP.items() if k != "H1-UC"}, **R.ABLATIONS}
NO_MIN32 = "H1-UC without the 32 minimum"
NO_SPATIAL = "H1-UC without spatial ublock padding"
WHOLE_COUT = "H1-UC with whole Cout instead of per-kernel slices"
CATEGORIES = ("E1-A", "E1-B", "E1-C", "E1-D")
N_SELECT = 6


# ---- candidates ---------------------------------------------------------------------------------------------------------
def parse(name: str) -> tuple[int, int, int, int]:
    _, c, hw, o = name.split("_")
    h, w = hw[1:].split("w")
    return int(c[1:]), int(h), int(w), int(o[1:])


def existing_shapes() -> set[tuple[int, int, int, int]]:
    """(H, W, Cin, Cout) of every officially measured or Revision A candidate 1x1 shape."""
    # The Stage 6B-B shapes are the Revision A candidates plus the Stage 4K Cin 48 reference (test_stage6be1 checks it).
    s = {(24, 24, c, 96) for c in (15, 16, 32, 40, 48, 56, 64, 128)}
    ra = json.loads((REPO / "evidence/stage6b/revision_a/revision_a_manifest.json").read_text())
    for c in ra["candidates"]:
        i, o = c["tensors"]["ifm"]["shape"], c["tensors"]["ofm"]["shape"]
        s.add((o[1], o[2], i[3], o[3]))
    return s


def case_of(name: str, f: dict) -> dict | None:
    """The stage6br case dict of a compiled candidate (None when the facts do not give one Conv with its kernels)."""
    convs = [r for r in f.get("rows", []) if r["npu_op"] == "Conv2D"]
    if len(convs) != 1 or not f.get("kernels") or any(k is None for k in f["kernels"]):
        return None
    cin, h, w, cout = parse(name)
    c = convs[0]
    return dict(case=name, status="VALID", cin=cin, cout=cout, ofm=[h, w, cout], ublock=R.hwc(c["ofm_ublock"]),
                ifm_block_depth=R.hwc(c["ifm_block"])[2], ofm_block=c["ofm_block"], ifm_block=c["ifm_block"],
                traversal=c["traversal"], kernels=[k["ofm"] for k in f["kernels"]], n_mac=h * w * cin * cout,
                memory=f"{c['ifm_memory']}/{c['ofm_memory']}")


def eligible(name: str, f: dict, existing: set) -> tuple[bool, list[str]]:
    why = []
    if f.get("error") or f.get("n_ethosu_ops") != 1:
        why.append("not one ethos-u op")
    rows = f.get("rows", [])
    if any(r["cpu"] == "1" for r in rows):
        why.append("cpu op")
    npu = [r["npu_op"] for r in rows if r["cpu"] == "0"]
    if npu != ["Conv2D", "Relu6"] or any(r["cms_offsets"] for r in rows if r["npu_op"] == "Relu6"):
        why.append(f"npu rows {npu}")
    c = case_of(name, f)
    if c is None:
        return False, why + ["no single Conv with kernels"]
    if c["traversal"] != "DepthFirst":
        why.append(f"traversal {c['traversal']}")
    if next(r for r in rows if r["npu_op"] == "Conv2D")["kernel"] != "1x1":
        why.append("kernel")
    cin, h, w, cout = parse(name)
    if (h, w, cin, cout) in existing:
        why.append("duplicates a measured shape")
    if n_split(c) == 0:
        why.append("H1-UC equals every competitor")
    return not why, why


def n_split(c: dict) -> int:
    return sum(f(c) != R.h1_uc(c) for f in COMPETITORS.values())


def categories(c: dict) -> list[str]:
    out = []
    # Contract E1-A "0 < r < 32 and H1-UC != no-min-32": the prediction difference implies 0 < r <= 16 (a remainder of 17-31
    # or >= 32 costs the same with or without the minimum). E1-B "edge not on the ublock and H1-UC != no-spatial-padding":
    # the difference implies the edge. Only the implying term is coded; test_stage6be1 pins both implications.
    if COMPETITORS[NO_MIN32](c) != R.h1_uc(c):
        out.append("E1-A")
    if COMPETITORS[NO_SPATIAL](c) != R.h1_uc(c):
        out.append("E1-B")
    if c["ublock"][2] == 16:
        out.append("E1-C")
    if len(c["kernels"]) >= 2 and COMPETITORS[WHOLE_COUT](c) != R.h1_uc(c):
        out.append("E1-D")
    return out


def rank_key(c: dict):
    return (-n_split(c), 0 if R.DPU_HYP["D-PW"](c) != R.DPU_HYP["D-U16"](c) else 1, c["n_mac"], c["case"])


def select(cases: list[dict], packs=lambda name: True) -> dict:
    """Contract §3: one per category in E1-A..D order (rank key, skipping taken and unpackable), then two more from all."""
    order = sorted(cases, key=rank_key)
    taken, picks, missing = [], {}, []
    for cat in CATEGORIES:
        pick = next((c for c in order if cat in categories(c) and c["case"] not in taken and packs(c["case"])), None)
        if pick is None:
            missing.append(cat); continue
        taken.append(pick["case"]); picks[pick["case"]] = cat
    for c in order:
        if len(taken) >= N_SELECT:
            break
        if c["case"] in taken or not packs(c["case"]):
            continue
        if any((c["cin"], c["cout"]) == (x["cin"], x["cout"]) for x in cases if x["case"] in taken):
            continue
        taken.append(c["case"]); picks[c["case"]] = "extra"
    status = "OK" if not missing and len(taken) == N_SELECT else "NEEDS_REVISION"
    return dict(status=status, selected=taken, role=picks, missing_categories=missing)


def predictions(c: dict) -> dict:
    mac = {k: f(c) for k, f in {"H1-UC": R.h1_uc, **COMPETITORS}.items()}
    dpu = {k: f(c) for k, f in R.DPU_HYP.items()}
    return dict(n_mac=c["n_mac"], kernels=c["kernels"], n_kernels=len(c["kernels"]), traversal=c["traversal"],
                ofm_block=c["ofm_block"], ifm_block=c["ifm_block"], ublock=c["ublock"],
                ublocks=R.ublocks(c["kernels"], c["ublock"]), cin_chunks=R.chunks(c["cin"], c["ifm_block_depth"]),
                categories=categories(c), mac=mac, dpu=dpu, h1_uc_rate=c["n_mac"] / mac["H1-UC"],
                differs_from_h1_uc=sorted(k for k, v in mac.items() if v != mac["H1-UC"]),
                dpu_pw_vs_u16_split=dpu["D-PW"] != dpu["D-U16"])


# ---- verdict -------------------------------------------------------------------------------------------------------------
def classify(r: dict) -> str:
    if r["status"] == "VALID":
        return "PRIMARY_VALID"
    if r["status"] == "UNSTABLE" and len(set(r.get("mac_active_runs") or [None, 0])) == 1 and \
            len(set(r.get("mac_dpu_active_runs") or [None, 0])) == 1:
        return "MAC_ONLY_DIAGNOSTIC"
    return "INVALID_OR_UNRESOLVED"


def shape_result(r: dict, pred: dict) -> dict:
    cls = classify(r)
    out = dict(config=r["config"], status=r["status"], reasons=r.get("reasons", []), cls=cls)
    if cls == "INVALID_OR_UNRESOLVED":
        return out
    mac = (r.get("mac_active_runs") or [None])[0]
    dpu = (r.get("mac_dpu_active_runs") or [None])[0]
    p = pred["mac"]["H1-UC"]
    out.update(measured_mac=mac, measured_dpu=dpu, predicted_mac=p, residual=mac - p, rel_residual=(mac - p) / p,
               h1_uc_match=mac == p, measured_rate=pred["n_mac"] / mac, predicted_rate=pred["n_mac"] / p,
               competitors={k: dict(pred=v, match=mac == v, distinguishing=v != p) for k, v in pred["mac"].items() if k != "H1-UC"},
               dpu={k: dict(pred=v, match=dpu == v) for k, v in pred["dpu"].items()},
               dpu_pw_vs_u16_split=pred["dpu_pw_vs_u16_split"])
    return out


def verdict(gate: dict, shapes: list[dict]) -> str:
    primary = [s for s in shapes if s["cls"] == "PRIMARY_VALID"]
    if gate.get("verdict") == "PASS" and any(not s["h1_uc_match"] for s in primary):
        return "H1_UC_CONTRADICTED"
    if gate.get("verdict") == "PASS" and len(primary) == N_SELECT and all(s["h1_uc_match"] for s in primary):
        return "PROSPECTIVE_SUPPORT"
    return "INSUFFICIENT_EVIDENCE"


def dpu_verdict(shapes: list[dict]) -> str:
    split = [s for s in shapes if s["cls"] == "PRIMARY_VALID" and s["dpu_pw_vs_u16_split"]]
    if not split:
        return "INSUFFICIENT_EVIDENCE"
    return "D-PW_CONSISTENT" if all(s["dpu"]["D-PW"]["match"] for s in split) else "D-PW_CONTRADICTED"


# ---- commands -----------------------------------------------------------------------------------------------------------
def cmd_select(grid_p: str, out: str) -> dict:
    grid = json.loads(pathlib.Path(grid_p).read_text())
    ex = existing_shapes()
    table, cases = [], []
    for name, f in sorted(grid.items()):
        ok, why = eligible(name, f, ex)
        c = case_of(name, f)
        row = dict(name=name, eligible=ok, why="; ".join(why))
        if c:
            row.update(traversal=c["traversal"], ublock="x".join(map(str, c["ublock"])), ifm_block=c["ifm_block"],
                       ofm_block=c["ofm_block"], n_kernels=len(c["kernels"]), n_split=n_split(c),
                       categories=" ".join(categories(c)), h1_uc=R.h1_uc(c), n_mac=c["n_mac"])
        table.append(row)
        if ok:
            cases.append(c)
    sel = select(cases)
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    R.S.write_csv(o / "candidates.csv", table)
    (o / "selection.json").write_text(json.dumps(dict(sel, n_grid=len(grid), n_eligible=len(cases),
                                                      ranking=[c["case"] for c in sorted(cases, key=rank_key)][:40]), indent=1))
    return sel


def cmd_predict(build_p: str, sel_p: str, wl: str) -> dict:
    """Manifest in stage6bb's format (reference + six E1 configs) and the frozen predictions."""
    build = json.loads(pathlib.Path(build_p).read_text())
    sel = json.loads(pathlib.Path(sel_p).read_text())
    wlp = pathlib.Path(wl)
    man6 = json.loads((REPO / "evidence/stage6b/stage6bb/workloads/stage6bb_manifest.json").read_text())
    man = {BB.REF: dict(man6[BB.REF], boot=FIRST_BOOT)}
    ident = {BB.REF: json.loads((REPO / "evidence/stage6b/stage6bb/workloads/expected_identity.json").read_text())[BB.REF]}
    preds = {}
    for i, name in enumerate(sel["selected"], 1):
        b = build[name]
        c = case_of(name, b)
        preds[name] = dict(predictions(c), role=sel["role"][name], drwl_sha256=b["drwl_sha256"], golden_sha256=b["golden_sha256"],
                           vela_sha256=b["vela_sha256"], cms_sha256=b["cms_sha256"], deterministic=b["deterministic"])
        n_base = 3 + b["n_in"] + b["n_out"]
        man[name] = dict(order=i, boot=FIRST_BOOT + i, kind="E1", group=name, drwl_sha256=b["drwl_sha256"],
                         golden_sha256=b["golden_sha256"], n_mac=c["n_mac"], cin=c["cin"], cout=c["cout"],
                         ifm_hwc=f"{c['ofm'][0]}x{c['ofm'][1]}x{c['cin']}", ofm_hwc="x".join(map(str, c["ofm"])),
                         ofm_block=c["ofm_block"], ifm_block=c["ifm_block"], ofm_ublock="x".join(map(str, c["ublock"])),
                         traversal=c["traversal"], n_base=n_base, placement=b["placement"],
                         internal_conv="CONV_OUTPUT_OBSERVED", output_check="output.bin = golden (BUILTIN_REF)",
                         vela=dict(status="NOT_COMPARABLE", why="E1 measures MAC_ACTIVE only (Vela fidelity is E2)"))
        ident[name] = dict(custom_op_inputs=n_base, custom_op_outputs=b["n_out"], n_base=n_base, placement=b["placement"],
                           drwl_sha256=b["drwl_sha256"])
    (wlp / BB.MANIFEST).write_text(json.dumps(man, indent=1))
    (wlp / "expected_identity.json").write_text(json.dumps(ident, indent=1))
    (wlp / "predictions.json").write_text(json.dumps(preds, indent=1))
    return preds


def cmd_judge(root: str, wl: str, ref: str, caps: str, out: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    preds = json.loads((wlp / "predictions.json").read_text())
    gate = BB.repro_gate(root, wl, ref, caps) if (rootp / "conds" / BB.REF / "wfe" / "runs.csv").exists() \
        else dict(verdict="FAIL", why="UNMEASURED")
    shapes = [shape_result(BB.config_result(rootp, wlp, n, caps), preds[n]) for n in preds]
    summary = dict(contract="evidence/stage6b/stage6be1/contract.md", reference_gate=gate, shapes=shapes,
                   verdict=verdict(gate, shapes), dpu_verdict=dpu_verdict(shapes),
                   counts={k: sum(s["cls"] == k for s in shapes) for k in ("PRIMARY_VALID", "MAC_ONLY_DIAGNOSTIC", "INVALID_OR_UNRESOLVED")})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be1_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    r = dict(select=lambda: cmd_select(*a[:2]), predict=lambda: cmd_predict(*a[:3]),
             judge=lambda: cmd_judge(*a[:5]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:4000])
