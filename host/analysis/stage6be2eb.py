#!/usr/bin/env python3
"""Stage 6B-E2E-B (evidence/stage6b/stage6be2eb/contract.md): G12 A2 graph-IO placement (B0 DRAM / B3 on-chip SRAM)
x EXT read latency (500 / 1000). Validity reuses the Stage 6B-B / E2B checks and the shared identity with the frozen
manifest's expected placement (maintenance 6614ce8); this stage adds the memory layout check and the traffic rules.

  python3 stage6be2eb.py workloads <E2D workloads dir> <out dir>
  python3 stage6be2eb.py manifest <workloads dir> <l1000 image.sha256>
  python3 stage6be2eb.py boot-check <run root> <workloads dir> <key>          # rc 1 -> the session stops
  python3 stage6be2eb.py repro-gate <run root> <workloads dir> <boot 375 wfe dir>
  python3 stage6be2eb.py judge <l500 run root> <l1000 run root> <workloads dir> <boot 375 wfe dir> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4k as K  # noqa: E402
import stage6bb as BB  # noqa: E402
import stage6be2b as E2B  # noqa: E402

MANIFEST = "e2eb_manifest.json"
H1UC = 20736
NOISE_FLOOR = 0.01
EXT_TOL = 0.01                                   # contract §5: B3 EXT read within 1 % of the static expectation
ORDER = [("REF", 500, 458), ("B0", 500, 459), ("B3", 500, 460), ("B3", 1000, 461), ("B0", 1000, 462)]
PLACEMENT = {"REF": 0, "B0": 0, "B3": 1}         # frozen expected placement
DRWL = {"REF": "s4c2_conv_cin48", "B0": "e2d_w1p1", "B3": "e2eb_b3"}
B0_SHA = "928296b1c235f1b22ce69d29900561d937818ffa655e1ec335e90ee3b1992c5f"   # E2D W1-P1 / E2B / 6B-B DRWL
# static EXT read expectation in 16-byte beats (contract §4): weights 174,752 + scales 5,760 + A2 command stream 628
B3_EXT_READ_BYTES = 174752 + 5760 + 628
EXT_READ_EXPECTED = {"B0": 27066.0, "B3": B3_EXT_READ_BYTES / 16}
VELA_B0 = {500: 53052, 1000: 83142}              # E2C facts, A2 Dedicated_Sram; B3: NO_COMPARABLE_VELA_ESTIMATE
E2D_B0 = {500: (99233.5, 1476), 1000: (158505.0, 2601)}   # E2D Amendment A W1-P1 (boots 453 / 454): median, range
SRAM_BASE, SRAM_LIMIT = 0x31000000, 0x31400000
SRAM_ALIGN = 0x10000
STOP = ("CONFIG_MISMATCH", "UNMEASURED")
CELLS = ("B0", "B3")


def key(cell: str, lat: int) -> str:
    return "REF" if cell == "REF" else f"{cell}-L{lat}"


# ---- pure rules -------------------------------------------------------------------------------------------------------
def tol(base: float, ranges: list[float]) -> float:
    return max(NOISE_FLOOR * base, sum(ranges))


def expected_arena(placement: int, model_base: int, model_len: int, fast_base: int, fast_size: int) -> int:
    """Where the runner puts region 1 (placement.h): DDR = model_base + model_len rounded up to 16 bytes as
    drwl_arena_after does; SRAM = (fast end rounded up to 64 KiB) + (DDR arena - model_base)."""
    ddr = model_base + ((model_len + 15) & ~15)
    if placement == 0:
        return ddr
    start = (fast_base + fast_size + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)
    return start + (ddr - model_base)


def layout(records: list[dict], caps: dict, placement: int, n_in: int, n_out: int) -> dict:
    """contract §3 memory layout, every RUN: region 1 (graph IO arena) where the placement puts it and inside its
    memory, the fast scratch (region 2) inside the driver's fast memory, region 1 disjoint from both, the weights
    (region 0) inside the model in DDR, every graph input/output base inside region 1."""
    fb, fs = caps.get("fast_base"), caps.get("fast_size")
    mb, lim, alen = caps.get("model_base"), caps.get("ddr_limit"), caps.get("arena_len")
    if not records or None in (fb, fs, mb, lim, alen):
        return dict(ok=False, checks=dict(records_and_caps=False))
    io = [3 + i for i in range(n_in + n_out)]

    def one(r):
        b = lambda i: r.get(f"base{i}", 0)
        s = lambda i: r.get(f"base_size{i}", 0)
        a = expected_arena(placement, mb, r.get("model_len", 0), fb, fs)
        mem = (SRAM_BASE, SRAM_LIMIT) if placement == 1 else (mb, lim)
        return dict(arena_where=r.get("arena_base") == a and b(1) == a,
                    arena_inside=mem[0] <= b(1) and b(1) + alen <= mem[1] and s(1) <= alen,
                    fast_inside=fb <= b(2) and b(2) + s(2) <= fb + fs,
                    fast_disjoint=(b(2) + s(2) <= b(1) or b(1) + alen <= b(2)) and (fb + fs <= b(1) or b(1) + alen <= fb),
                    weights_ddr=mb <= b(0) and b(0) + s(0) <= mb + r.get("model_len", 0),
                    io_in_arena=all(b(1) <= b(i) and b(i) + s(i) <= b(1) + s(1) for i in io))
    per = [one(r) for r in records]
    checks = {k: all(p[k] for p in per) for k in per[0]}
    return dict(ok=all(checks.values()), checks=checks)


def io_placement(pe: dict, tols: dict, usable: bool) -> str:
    if not usable:
        return "NOT_IDENTIFIABLE"
    big = [abs(pe[L]) > tols[L] for L in (500, 1000)]
    same_sign = (pe[500] > 0) == (pe[1000] > 0)
    return "IO_PLACEMENT_EFFECT_OBSERVED" if all(big) and same_sign else "IO_PLACEMENT_EFFECT_NOT_RESOLVED"


def sensitivity(inter: float, t: float, usable: bool) -> str:
    if not usable:
        return "INSUFFICIENT_EVIDENCE"
    return "IO_SENSITIVITY_REDUCED" if inter > t else "IO_SENSITIVITY_NOT_REDUCED"


def residual_response(le: float, t: float, usable: bool) -> str:
    """H-REMAIN, descriptive (no attribution): B3's own latency effect against its tolerance."""
    if not usable:
        return "NOT_EVALUABLE"
    return "RESIDUAL_RESPONSE_OBSERVED" if abs(le) > t else "RESIDUAL_RESPONSE_NOT_OBSERVED"


def ext_within(beats: float, expected: float) -> bool:
    return abs(beats - expected) <= EXT_TOL * expected


def residual_path(b3: dict, b0_ext_read: float) -> str:
    """b3: {L: dict(ext_rd_beats, ext_wr_beats)} for the VALID B3 cells only."""
    if not b3 or any(v["ext_wr_beats"] != 0 or v["ext_rd_beats"] >= b0_ext_read for v in b3.values()):
        return "EXT_PATH_UNRESOLVED"
    if len(b3) == 2 and all(ext_within(v["ext_rd_beats"], EXT_READ_EXPECTED["B3"]) for v in b3.values()):
        return "WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED"
    return "EXT_PATH_PARTIAL"


def validity(gate: dict, res: dict, mac_ok: dict) -> str:
    if gate.get("verdict") != "PASS" or any(r["status"] in STOP for r in res.values()):
        return "MEASUREMENT_INVALID"
    if all(r["status"] == "VALID" for r in res.values()) and all(mac_ok.values()):
        return "VALID"
    return "PARTIAL_VALID"


def mechanism() -> str:
    return "MECHANISM_UNRESOLVED"     # contract §6: no measurement here separates DMA overlap, WD supply and AO backpressure


# ---- board results ----------------------------------------------------------------------------------------------------
def traffic(m: dict) -> dict:
    pb = m.get("pass_b", {})
    return dict(sram_rd_beats=pb.get(130), sram_rd_trans=pb.get(128), sram_wr_beats=pb.get(135), sram_wr_trans=pb.get(132),
                ext_rd_beats=pb.get(386), ext_rd_trans=pb.get(384), ext_wr_beats=pb.get(391))


def config_result(root: pathlib.Path, wl: pathlib.Path, k: str) -> dict:
    import drwl
    m = json.loads((wl / MANIFEST).read_text())[k]
    cfg = m["config"]
    folder = root / "conds" / cfg / "wfe"
    base = dict(key=k, config=cfg)
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    ident = BB.identity_of(folder, wl, cfg, m, str(wl / m["caps_ref"]))      # shared identity, manifest placement
    env = E2B.environment(folder, m, ident)
    caps_p = folder.parent / "capabilities.json"
    caps = json.loads(caps_p.read_text()) if caps_p.exists() else {}
    h = drwl.parse((wl / f"{cfg}.drwl").read_bytes())
    recs = [x["record"] for x in json.loads((folder / "raw_runs.json").read_text())[1:]]
    lay = layout(recs, caps, m["placement"], h["n_in"], h["n_out"])
    env += [f"layout {c}" for c, v in lay["checks"].items() if not v]
    if env:
        return dict(base, status="CONFIG_MISMATCH", reasons=env, layout=lay)
    s = K.summary_of(folder, m["n_mac"])
    met = BB.rates(m, s["metrics"])
    if not BB.output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][x] for x in BB.IDENT_OUTPUT):
        return dict(base, status="INVALID_OUTPUT", reasons=["board output != reference"])
    p = BB.pmu(folder, s["runs"], m["n_mac"])
    if p:
        return dict(base, status="INVALID_PMU", reasons=p)
    st = BB.stability(s)
    res = dict(base, metrics=met, traffic=traffic(met), layout=lay, arena_base=recs[0].get("arena_base"),
               output_sha256=s["output_sha256"])
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


def effects(res: dict, usable: bool) -> dict:
    if not usable:
        return dict(usable=False)
    b = lambda c, L: res[key(c, L)]["metrics"]["npu_active"]
    r = lambda c, L: res[key(c, L)]["metrics"]["npu_active_range"]
    pe = {L: b("B0", L) - b("B3", L) for L in (500, 1000)}
    t_pe = {L: tol(b("B3", L), [r("B0", L), r("B3", L)]) for L in (500, 1000)}
    le = {c: b(c, 1000) - b(c, 500) for c in CELLS}
    t_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in CELLS}
    inter = le["B0"] - le["B3"]
    t_i = tol(b("B3", 500), [r(c, L) for c in CELLS for L in (500, 1000)])
    return dict(usable=True, pe=pe, tol_pe=t_pe, le=le, tol_le=t_le, interaction=inter, tol_interaction=t_i,
                le_share_removed=inter / le["B0"] if le["B0"] else None,
                ratio={c: b(c, 1000) / b(c, 500) for c in CELLS})


ACTIVITY = ("npu_active", "mac_active", "mac_dpu_active", "ao_active", "wd_active", "wd_stalled")


def activity(res: dict) -> dict:
    """§9.4 descriptive: per latency, B0 and B3 unit activity and traffic, and B3 - B0."""
    out = {}
    for L in (500, 1000):
        a, b = res[key("B0", L)], res[key("B3", L)]
        if a["status"] != "VALID" or b["status"] != "VALID":
            continue
        va = {**{x: a["metrics"][x] for x in ACTIVITY}, **a["traffic"]}
        vb = {**{x: b["metrics"][x] for x in ACTIVITY}, **b["traffic"]}
        out[L] = dict(B0=va, B3=vb, delta={x: (vb[x] - va[x]) if None not in (va[x], vb[x]) else None for x in va},
                      read_total=dict(B0=va["sram_rd_beats"] + va["ext_rd_beats"], B3=vb["sram_rd_beats"] + vb["ext_rd_beats"]),
                      write_total=dict(B0=va["sram_wr_beats"] + va["ext_wr_beats"], B3=vb["sram_wr_beats"] + vb["ext_wr_beats"]))
    return out


def judge(root500: str, root1000: str, wl: str, ref: str, out: str) -> dict:
    wlp = pathlib.Path(wl)
    man = json.loads((wlp / MANIFEST).read_text())
    roots = {k: pathlib.Path(root1000 if man[k]["latency"] == 1000 else root500) for k in man}
    has_ref = (roots["REF"] / "conds" / man["REF"]["config"] / "wfe" / "runs.csv").exists()
    gate = repro_gate(str(roots["REF"]), wl, ref) if has_ref else dict(verdict="FAIL", why="UNMEASURED")
    res = {k: config_result(roots[k], wlp, k) for k in man}
    mac_ok = {k: r["metrics"]["mac_active"] == H1UC for k, r in res.items() if k != "REF" and r["status"] == "VALID"}
    good = lambda k: res[k]["status"] == "VALID" and mac_ok.get(k, False)
    usable = all(good(key(c, L)) for c in CELLS for L in (500, 1000))
    eff = effects(res, usable)
    ext = {c: {L: dict(res[key(c, L)]["traffic"], expected_ext_rd=EXT_READ_EXPECTED[c],
                       within=ext_within(res[key(c, L)]["traffic"]["ext_rd_beats"], EXT_READ_EXPECTED[c]))
               for L in (500, 1000) if good(key(c, L))} for c in CELLS}
    b0_rd = max([v["ext_rd_beats"] for v in ext["B0"].values()] or [EXT_READ_EXPECTED["B0"]])
    b3 = {L: v for L, v in ext["B3"].items()}
    vela = {L: dict(vela=VELA_B0[L], board=res[key("B0", L)]["metrics"]["npu_active"],
                    board_over_vela=res[key("B0", L)]["metrics"]["npu_active"] / VELA_B0[L]) for L in (500, 1000) if good(key("B0", L))}
    e2d = {L: dict(e2d=E2D_B0[L][0], now=res[key("B0", L)]["metrics"]["npu_active"],
                   within=abs(res[key("B0", L)]["metrics"]["npu_active"] - E2D_B0[L][0])
                   <= tol(E2D_B0[L][0], [E2D_B0[L][1], res[key("B0", L)]["metrics"]["npu_active_range"]]))
           for L in (500, 1000) if good(key("B0", L))}
    summary = dict(contract="evidence/stage6b/stage6be2eb/contract.md",
                   ta="TA profile 1; EXT RLATENCY 500 (image 70090f1) / 1000 (L1000 image, bram fd478e2d)",
                   reference_gate=gate, results=res, mac_equals_h1uc=mac_ok, effects=eff, ext_traffic=ext,
                   activity=activity(res), vela_b0=vela, b0_vs_e2d=e2d,
                   vela_le_b0=dict(vela=VELA_B0[1000] - VELA_B0[500], board=eff["le"]["B0"] if usable else None),
                   verdicts=dict(measurement_validity=validity(gate, res, mac_ok),
                                 graph_io_placement=io_placement(eff.get("pe"), eff.get("tol_pe"), usable),
                                 latency_sensitivity=sensitivity(eff.get("interaction"), eff.get("tol_interaction"), usable),
                                 residual_ext_path=residual_path(b3, b0_rd),
                                 residual_latency_response=residual_response(eff["le"]["B3"] if usable else 0,
                                                                             eff["tol_le"]["B3"] if usable else 0, usable),
                                 pipeline_mechanism=mechanism()),
                   b3_vela="NO_COMPARABLE_VELA_ESTIMATE",
                   limits=["one boot per condition; no boot repetition",
                           "graph input and output move together (B1/B2 UNAVAILABLE)",
                           "weight supply and command-stream fetch stay on EXT in both; not separable here",
                           "physical memory, AXI port and TA (SRAM vs EXT) change together with the placement",
                           "drift checked once by REF; L500 B0->B3, L1000 B3->B0 does not remove it"])
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2eb_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- workloads and manifest ----------------------------------------------------------------------------------------------
def workloads(e2d_wl: str, out: str) -> dict:
    """B0 = E2D e2d_w1p1 unchanged; B3 = the same DRWL with header word 7 = 1 (drwl.with_placement); REF = s4c2_conv_cin48.
    Companion files are copied byte for byte; expected_identity.json gets the three configs."""
    import drwl
    src, o = pathlib.Path(e2d_wl), pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for f in ["s4c2_conv_cin48.compile.json", "s4c2_conv_cin48.drwl", "s4c2_conv_cin48.drwl.tflite_ofm.bin",
              "caps_l500.json", "caps_l1000.json"] + [f"e2d_w1p1{x}" for x in
                                                      (".drwl", ".drwl.cms.bin", ".drwl.json", ".drwl.tflite_ofm.bin", ".ifm.bin", ".ref_ofm.bin")]:
        shutil.copyfile(src / f, o / f)
    b0 = (o / "e2d_w1p1.drwl").read_bytes()
    if BB.sha(o / "e2d_w1p1.drwl") != B0_SHA:
        raise SystemExit("B0 DRWL is not 928296b1")
    (o / "e2eb_b3.drwl").write_bytes(drwl.with_placement(b0, 1))
    for x in (".drwl.cms.bin", ".drwl.tflite_ofm.bin", ".ifm.bin", ".ref_ofm.bin"):
        shutil.copyfile(o / f"e2d_w1p1{x}", o / f"e2eb_b3{x}")
    e2d = json.loads((src / "expected_identity.json").read_text())
    ei = {c: e2d[c] for c in ("s4c2_conv_cin48", "e2d_w1p1")}
    ei["e2eb_b3"] = dict(e2d["e2d_w1p1"], drwl_sha256=BB.sha(o / "e2eb_b3.drwl"), placement=1)
    (o / "expected_identity.json").write_text(json.dumps(ei, indent=1, sort_keys=True))
    return {c: v["drwl_sha256"] for c, v in ei.items()}


def manifest(wl: str, l1000_sha: str) -> dict:
    import drwl
    wlp = pathlib.Path(wl)
    img = dict(reversed(line.split()) for line in pathlib.Path(l1000_sha).read_text().splitlines())
    image_l1000 = dict(boot_sha256=img["boot.bin"], bram_sha256=img["bram.bin"], ddr_sha256=img["ddr.bin"], images_txt_sha256=img["images.txt"])
    k4 = json.loads((wlp / "s4c2_conv_cin48.compile.json").read_text())
    caps = json.loads((wlp / "caps_l500.json").read_text())
    out = {}
    for cell, lat, boot in ORDER:
        cfg = DRWL[cell]
        m = dict(kind="reference", n_mac=k4["n_mac"], cin=48, internal_conv="CONV_OUTPUT_OBSERVED") if cell == "REF" else \
            dict(kind="A2", n_mac=19501056, cin=276, internal_conv="INTERNAL_CONV_NOT_OBSERVED")
        h = drwl.parse((wlp / f"{cfg}.drwl").read_bytes())
        if h["placement"] != PLACEMENT[cell]:
            raise SystemExit(f"{cfg}: DRWL placement {h['placement']} != frozen {PLACEMENT[cell]}")
        out[key(cell, lat)] = dict(m, cell=cell, config=cfg, boot=boot, latency=lat, placement=PLACEMENT[cell],
                                   drwl_sha256=BB.sha(wlp / f"{cfg}.drwl"),
                                   arena_base=expected_arena(PLACEMENT[cell], caps["model_base"], h["model_len"],
                                                             caps["fast_base"], caps["fast_size"]),
                                   image=E2B.IMAGE_L500 if lat == 500 else image_l1000, ta_ext_rlatency=lat,
                                   caps_ref="caps_l500.json" if lat == 500 else "caps_l1000.json")
    (wlp / MANIFEST).write_text(json.dumps(out, indent=1, sort_keys=True))
    return out


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "workloads":
        print(json.dumps(workloads(*a[:2]), indent=1)); return 0
    if cmd == "manifest":
        manifest(*a[:2]); return 0
    if cmd == "boot-check":
        r = boot_check(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "repro-gate":
        r = repro_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge":
        r = judge(*a[:5])
        print(json.dumps({k: r[k] for k in ("verdicts", "effects", "ext_traffic", "vela_b0", "b0_vs_e2d", "mac_equals_h1uc")},
                         indent=1, default=str)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
