#!/usr/bin/env python3
"""Stage 6B-E2D (evidence/stage6b/stage6be2d/contract.md): G12 Conv placement x EXT read latency. Validity reuses the
Stage 6B-B / E2B checks (image, TA read-back, placement identity per condition from the manifest).

  python3 stage6be2d.py manifest <workloads dir> <l1000 image.sha256>
  python3 stage6be2d.py boot-check <run root> <workloads dir> <key>          # rc 1 -> the session stops
  python3 stage6be2d.py repro-gate <run root> <workloads dir> <boot 375 wfe dir>
  python3 stage6be2d.py judge <l500 run root> <l1000 run root> <workloads dir> <boot 375 wfe dir> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage4 as S4  # noqa: E402
import stage4k as K  # noqa: E402
import stage6bb as BB  # noqa: E402
import stage6be2b as E2B  # noqa: E402

MANIFEST = "e2d_manifest.json"
H1UC = 20736
MODEL_TOL = 0.15
NOISE_FLOOR = 0.01
VELA = {"W1-P0": (100310, 200622), "W1-P1": (53052, 83142), "W0-P0": (107812, 215624)}   # E2C facts (L500, L1000)
PE_VELA = {500: 47258, 1000: 117480}
INTERACTION_VELA = 70222
CELLS = ("W0-P0", "W0-P1", "W1-P0", "W1-P1")
ORDER = [("REF", 500, 440), ("W0-P0", 500, 441), ("W0-P1", 500, 442), ("W1-P0", 500, 443), ("W1-P1", 500, 444),
         ("W1-P1", 1000, 445), ("W1-P0", 1000, 446), ("W0-P1", 1000, 447), ("W0-P0", 1000, 448)]
DRWL = {"REF": "s4c2_conv_cin48", "W0-P0": "e2d_w0p0", "W0-P1": "e2d_w0p1", "W1-P0": "e2d_w1p0", "W1-P1": "e2d_w1p1"}
STOP = ("CONFIG_MISMATCH", "UNMEASURED")


def key(cell: str, lat: int) -> str:
    return "REF" if cell == "REF" else f"{cell}-L{lat}"


# ---- pure rules -------------------------------------------------------------------------------------------------------
def tol(base: float, ranges: list[float]) -> float:
    return max(NOISE_FLOOR * base, sum(ranges))


def placement_effect(pe: dict, tols: dict, usable: bool) -> str:
    """pe, tols: {500: .., 1000: ..}."""
    if not usable:
        return "NOT_IDENTIFIABLE"
    big = [abs(pe[L]) > tols[L] for L in (500, 1000)]
    same_sign = (pe[500] > 0) == (pe[1000] > 0)
    return "PLACEMENT_EFFECT_OBSERVED" if all(big) and same_sign else "PLACEMENT_EFFECT_NOT_RESOLVED"


def within(board: float, vela: float, t: float) -> bool:
    return abs(board - vela) <= MODEL_TOL * abs(vela) + t


def fidelity(pe: dict, tols: dict, evaluable: dict) -> str:
    ok = {L: within(pe[L], PE_VELA[L], tols[L]) for L in (500, 1000) if evaluable.get(L)}
    if not ok:
        return "NOT_COMPARABLE"
    if not all(ok.values()):
        return "PLACEMENT_RESPONSE_DISCREPANCY"
    return "PLACEMENT_RESPONSE_CONSISTENT" if len(ok) == 2 else "FIDELITY_PARTIAL"


def validity(gate: dict, res: dict, mac_ok: dict) -> str:
    if gate.get("verdict") != "PASS" or any(r["status"] in STOP for r in res.values()):
        return "MEASUREMENT_INVALID"
    if all(r["status"] == "VALID" for r in res.values()) and all(mac_ok.values()):
        return "VALID"
    return "PARTIAL_VALID"


def mechanism() -> str:
    return "MECHANISM_UNRESOLVED"     # contract §5: no measurement here separates DMA overlap from AO/WD backpressure


# ---- board results ----------------------------------------------------------------------------------------------------
def config_result(root: pathlib.Path, wl: pathlib.Path, k: str) -> dict:
    m = json.loads((wl / MANIFEST).read_text())[k]
    cfg = m["config"]
    folder = root / "conds" / cfg / "wfe"
    base = dict(key=k, config=cfg)
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    ident = BB.identity_of(folder, wl, cfg, m, str(wl / m["caps_ref"]))
    env = E2B.environment(folder, m, ident)
    if env:
        return dict(base, status="CONFIG_MISMATCH", reasons=env)
    s = K.summary_of(folder, m["n_mac"])
    met = BB.rates(m, s["metrics"])
    if not BB.output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][x] for x in BB.IDENT_OUTPUT):
        return dict(base, status="INVALID_OUTPUT", reasons=["board output != reference"])
    p = BB.pmu(folder, s["runs"], m["n_mac"])
    if p:
        return dict(base, status="INVALID_PMU", reasons=p)
    st = BB.stability(s)
    res = dict(base, metrics=met, pass_b={c: s["metrics"].get(f"B_{c}") for c in S4.PASS_B}, output_sha256=s["output_sha256"])
    return dict(res, status="UNSTABLE", reasons=st) if st else dict(res, status="VALID", reasons=[])


def repro_gate(root: str, wl: str, ref: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    r = config_result(rootp, wlp, "REF")
    if r["status"] != "VALID":
        return dict(verdict="FAIL", why=r["status"], reasons=r["reasons"])
    m = json.loads((wlp / MANIFEST).read_text())["REF"]
    folder = rootp / "conds" / m["config"] / "wfe"
    same = {x["workload_sha256"] for x in BB.rows_of(pathlib.Path(ref))} == {x["workload_sha256"] for x in BB.rows_of(folder)}
    rep = K.reproduce(K.summary_of(folder, m["n_mac"]), K.summary_of(pathlib.Path(ref), m["n_mac"]))
    return dict(verdict="PASS" if rep["ok"] and same else "FAIL", same_binary=same, reproduce=rep)


def boot_check(root: str, wl: str, k: str) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), k)
    return dict(key=k, status=r["status"], reasons=r["reasons"], stop=r["status"] in STOP)


def effects(res: dict, w: str, usable: bool) -> dict:
    b = lambda c, L: res[key(c, L)]["metrics"]["npu_active"]
    r = lambda c, L: res[key(c, L)]["metrics"]["npu_active_range"]
    p0, p1 = f"{w}-P0", f"{w}-P1"
    if not usable:
        return dict(usable=False)
    pe = {L: b(p0, L) - b(p1, L) for L in (500, 1000)}
    t_pe = {L: tol(b(p1, L), [r(p0, L), r(p1, L)]) for L in (500, 1000)}
    le = {c: b(c, 1000) - b(c, 500) for c in (p0, p1)}
    t_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in (p0, p1)}
    inter = le[p0] - le[p1]
    t_i = tol(b(p1, 500), [r(c, L) for c in (p0, p1) for L in (500, 1000)])
    return dict(usable=True, pe=pe, tol_pe=t_pe, le=le, tol_le=t_le, ratio={c: b(c, 1000) / b(c, 500) for c in (p0, p1)},
                interaction=inter, tol_interaction=t_i, cls=placement_effect(pe, t_pe, True))


def judge(root500: str, root1000: str, wl: str, ref: str, out: str) -> dict:
    wlp = pathlib.Path(wl)
    man = json.loads((wlp / MANIFEST).read_text())
    roots = {k: pathlib.Path(root1000 if man[k]["latency"] == 1000 else root500) for k in man}
    has_ref = (roots["REF"] / "conds" / man["REF"]["config"] / "wfe" / "runs.csv").exists()
    gate = repro_gate(str(roots["REF"]), wl, ref) if has_ref else dict(verdict="FAIL", why="UNMEASURED")
    res = {k: config_result(roots[k], wlp, k) for k in man}
    mac_ok = {k: r["metrics"]["mac_active"] == H1UC for k, r in res.items() if k != "REF" and r["status"] == "VALID"}
    ok = lambda c: all(res[key(c, L)]["status"] == "VALID" and mac_ok.get(key(c, L)) for L in (500, 1000))
    eff = {w: effects(res, w, ok(f"{w}-P0") and ok(f"{w}-P1")) for w in ("W1", "W0")}
    w1 = eff["W1"]
    evaluable = {L: all(res[key(c, L)]["status"] == "VALID" and mac_ok.get(key(c, L)) for c in ("W1-P0", "W1-P1")) for L in (500, 1000)}
    if w1["usable"]:
        pe, tp = w1["pe"], w1["tol_pe"]
    else:
        b = lambda c, L: res[key(c, L)]["metrics"]["npu_active"]
        r = lambda c, L: res[key(c, L)]["metrics"]["npu_active_range"]
        pe = {L: b("W1-P0", L) - b("W1-P1", L) for L in (500, 1000) if evaluable[L]}
        tp = {L: tol(b("W1-P1", L), [r("W1-P0", L), r("W1-P1", L)]) for L in (500, 1000) if evaluable[L]}
    fid = fidelity(pe, tp, evaluable)
    vela_rows = {}
    for c, (v5, v10) in VELA.items():
        for L, v in ((500, v5), (1000, v10)):
            rr = res[key(c, L)]
            if rr["status"] == "VALID":
                bb = rr["metrics"]["npu_active"]
                vela_rows[key(c, L)] = dict(vela=v, board=bb, abs_err=bb - v, rel_err=(bb - v) / v, board_over_vela=bb / v)
    report = {}
    if w1["usable"]:
        report = dict(le_vs_vela={c: dict(board=w1["le"][c], vela=VELA[c][1] - VELA[c][0],
                                           within=within(w1["le"][c], VELA[c][1] - VELA[c][0], w1["tol_le"][c])) for c in ("W1-P0", "W1-P1")},
                      interaction_vs_vela=dict(board=w1["interaction"], vela=INTERACTION_VELA,
                                               within=within(w1["interaction"], INTERACTION_VELA, w1["tol_interaction"])),
                      pe_vs_vela={L: dict(board=w1["pe"][L], vela=PE_VELA[L], within=within(w1["pe"][L], PE_VELA[L], w1["tol_pe"][L])) for L in (500, 1000)})
    summary = dict(contract="evidence/stage6b/stage6be2d/contract.md", ta="TA profile 1; EXT RLATENCY 500 (70090f1) / 1000 (L1000 image)",
                   reference_gate=gate, results=res, mac_equals_h1uc=mac_ok, effects=eff, vela=vela_rows, vela_report=report,
                   verdicts=dict(measurement_validity=validity(gate, res, mac_ok), placement_effect=eff["W1"].get("cls", "NOT_IDENTIFIABLE"),
                                 placement_effect_w0_aux=eff["W0"].get("cls", "NOT_IDENTIFIABLE"), vela_fidelity=fid, mechanism=mechanism()),
                   internal_conv="INTERNAL_CONV_NOT_OBSERVED",
                   limits=["one boot per condition", "drift checked once by REF; reverse order does not remove it",
                           "W1 placement moves the Conv IFM/OFM and the two ADDs' paths together; physical memory, AXI port and TA change together",
                           "W0-P1 has no comparable Vela estimate", "W0 vs W1 is not a wrapper-only effect (NHWC vs NHCWB16)"])
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2d_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- manifest -----------------------------------------------------------------------------------------------------------
def manifest(wl: str, l1000_sha: str) -> dict:
    wlp = pathlib.Path(wl)
    img = dict(reversed(line.split()) for line in pathlib.Path(l1000_sha).read_text().splitlines())
    image_l1000 = dict(boot_sha256=img["boot.bin"], bram_sha256=img["bram.bin"], ddr_sha256=img["ddr.bin"], images_txt_sha256=img["images.txt"])
    k4 = json.loads((wlp / "s4c2_conv_cin48.compile.json").read_text())
    out = {}
    for cell, lat, boot in ORDER:
        cfg = DRWL[cell]
        m = dict(kind="reference", n_mac=k4["n_mac"], cin=48, internal_conv="CONV_OUTPUT_OBSERVED") if cell == "REF" else \
            dict(kind="A2" if cell.startswith("W1") else "A0", n_mac=19501056, cin=276, internal_conv="INTERNAL_CONV_NOT_OBSERVED")
        out[key(cell, lat)] = dict(m, cell=cell, config=cfg, boot=boot, latency=lat, drwl_sha256=BB.sha(wlp / f"{cfg}.drwl"),
                                   image=E2B.IMAGE_L500 if lat == 500 else image_l1000, ta_ext_rlatency=lat,
                                   caps_ref="caps_l500.json" if lat == 500 else "caps_l1000.json")
    (wlp / MANIFEST).write_text(json.dumps(out, indent=1, sort_keys=True))
    return out


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "manifest":
        manifest(*a[:2]); return 0
    if cmd == "boot-check":
        r = boot_check(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "repro-gate":
        r = repro_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge":
        r = judge(*a[:5]); print(json.dumps({k: r[k] for k in ("verdicts", "effects", "vela", "vela_report", "mac_equals_h1uc")}, indent=1, default=str)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
