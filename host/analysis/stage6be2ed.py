#!/usr/bin/env python3
"""Stage 6B-E2E-D (evidence/stage6b/stage6be2ed/contract.md): B3 (graph IO SRAM, weights/scale EXT) vs B3w (the same
with region 0 read from an on-chip SRAM copy, runner placement 2) x EXT read latency 500 / 1000, on the new runner
images (14077be). Validity reuses the Stage 6B-B / E2B checks and the shared identity with the manifest placement.

  python3 stage6be2ed.py workloads <E2E-B workloads dir> <out dir>
  python3 stage6be2ed.py manifest <workloads dir> <l500 image dir> <l1000 image dir>
  python3 stage6be2ed.py boot-check <run root> <workloads dir> <key>          # rc 1 -> the session stops
  python3 stage6be2ed.py repro-gate <run root> <workloads dir> <boot 375 wfe dir>
  python3 stage6be2ed.py b3-gate <run root> <workloads dir> <latency>       # rc 1 -> B3 not reproduced, stop
  python3 stage6be2ed.py judge <l500 run root> <l1000 run root> <workloads dir> <boot 375 wfe dir> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4k as K  # noqa: E402
import stage6bb as BB  # noqa: E402
import stage6be2b as E2B  # noqa: E402
import stage6be2eb as EB  # noqa: E402

MANIFEST = "e2ed_manifest.json"
H1UC = 20736
NOISE_FLOOR = 0.01
ORDER = [("REF", 500, 463), ("B3", 500, 464), ("B3w", 500, 465), ("B3w", 1000, 466), ("B3", 1000, 467)]
PLACEMENT = {"REF": 0, "B3": 1, "B3w": 2}
DRWL = {"REF": "s4c2_conv_cin48", "B3": "e2eb_b3", "B3w": "e2ed_b3w"}
CELLS = ("B3", "B3w")
B3_SHA = "7b2cedd5d42dcf28547f35d0a049a9bfe5c3395eec40f33fd70592e125a13125"
# E2E-B B3 (boots 460 / 461, TA profile 1, old image 70090f1 / L1000): NPU_ACTIVE median, range; traffic (exact)
B3_EB = {500: (60320.0, 1197), 1000: (72526.5, 1189)}
B3_EB_TRAFFIC = dict(sram_rd_beats=40832.0, sram_rd_trans=11192.0, sram_wr_beats=17088.0, sram_wr_trans=5388.0,
                     ext_rd_beats=11322.0, ext_rd_trans=793.0, ext_wr_beats=0.0)
# region 0 of the A2 DRWL as the board recorded it in E2E-B (B3, every RUN): base 0x70000420, 0x16090 bytes
WEIGHTS_SRC, WEIGHTS_LEN = 0x70000420, 0x16090
WEIGHT_SCALE_BEATS = (174752 + 5760) / 16           # region 0 traffic Vela counts (weights + scale), E2E-C
EXT_RD_B3W = (39, 64)                               # command stream 628 B = 39.25 beats; up to 1 KiB for fetch rounding
SHIFT_TOL = 0.01
LOW, HIGH = 0.25, 0.75
SRAM_BASE, SRAM_LIMIT, SRAM_ALIGN, ARENA_LEN = 0x31000000, 0x31400000, 0x10000, 0x200000
STOP = ("CONFIG_MISMATCH", "UNMEASURED")


def key(cell: str, lat: int) -> str:
    return "REF" if cell == "REF" else f"{cell}-L{lat}"


# ---- pure rules -------------------------------------------------------------------------------------------------------
def tol(base: float, ranges: list[float]) -> float:
    return max(NOISE_FLOOR * base, sum(ranges))


def weight_dst(arena: int, arena_len: int, sram_limit: int, src: int, length: int) -> int:
    """Mirror of firmware placement_weight_dst (placement.c), written from its description, tested against fixed values."""
    end = arena + arena_len
    if src == 0 or length == 0:
        return 0
    start = (end + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)
    dst = start + (src & (SRAM_ALIGN - 1))
    return dst if dst + length <= sram_limit else 0


def layout(records: list[dict], caps: dict, placement: int, n_in: int, n_out: int, weights_at: int | None) -> dict:
    """E2E-B layout (graph IO arena, fast scratch, IO bases) plus region 0: placement 2 -> BASEP0 = the frozen copy
    address, inside the SRAM window, disjoint from the arena and the fast memory; else inside the DDR model."""
    fb, fs = caps.get("fast_base"), caps.get("fast_size")
    mb, lim, alen = caps.get("model_base"), caps.get("ddr_limit"), caps.get("arena_len")
    if not records or None in (fb, fs, mb, lim, alen):
        return dict(ok=False, checks=dict(records_and_caps=False))
    io = [3 + i for i in range(n_in + n_out)]

    def one(r):
        b = lambda i: r.get(f"base{i}", 0)
        s = lambda i: r.get(f"base_size{i}", 0)
        a = EB.expected_arena(min(placement, 1), mb, r.get("model_len", 0), fb, fs)
        mem = (SRAM_BASE, SRAM_LIMIT) if placement >= 1 else (mb, lim)
        c = dict(arena_where=r.get("arena_base") == a and b(1) == a,
                 arena_inside=mem[0] <= b(1) and b(1) + alen <= mem[1] and s(1) <= alen,
                 fast_inside=fb <= b(2) and b(2) + s(2) <= fb + fs,
                 fast_disjoint=(b(2) + s(2) <= b(1) or b(1) + alen <= b(2)) and (fb + fs <= b(1) or b(1) + alen <= fb),
                 io_in_arena=all(b(1) <= b(i) and b(i) + s(i) <= b(1) + s(1) for i in io))
        if placement == 2:
            c.update(weights_where=b(0) == weights_at and weights_at is not None,
                     weights_inside=SRAM_BASE <= b(0) and b(0) + s(0) <= SRAM_LIMIT,
                     weights_disjoint=(b(0) + s(0) <= b(1) or b(1) + alen <= b(0)) and (b(0) + s(0) <= fb or fb + fs <= b(0)))
        else:
            c.update(weights_ddr=mb <= b(0) and b(0) + s(0) <= mb + r.get("model_len", 0))
        return c
    per = [one(r) for r in records]
    checks = {k: all(p[k] for p in per) for k in per[0]}
    return dict(ok=all(checks.values()), checks=checks)


def remap_ok(b3w: dict, b3_sram_rd: float, b3_read_total: float) -> dict:
    """One latency: b3w = traffic of a VALID, MAC-equal B3w cell; b3_* = the same-latency B3 (or E2E-B) values."""
    c = dict(ext_rd=EXT_RD_B3W[0] <= b3w["ext_rd_beats"] <= EXT_RD_B3W[1],
             ext_wr=b3w["ext_wr_beats"] == 0,
             sram_shift=abs((b3w["sram_rd_beats"] - b3_sram_rd) - WEIGHT_SCALE_BEATS) <= SHIFT_TOL * WEIGHT_SCALE_BEATS,
             read_total=abs(b3w["sram_rd_beats"] + b3w["ext_rd_beats"] - b3_read_total) <= SHIFT_TOL * b3_read_total)
    return dict(ok=all(c.values()), checks=c)


def remap_validity(per_latency: dict) -> str:
    """per_latency: {L: remap_ok result or None (cell not VALID / MAC mismatch)}."""
    ok = [L for L, r in per_latency.items() if r and r["ok"]]
    if len(ok) == 2:
        return "WEIGHT_SCALE_REMAP_CONFIRMED"
    return "REMAP_PARTIAL" if ok else "REMAP_INVALID"


def b3_reproduced(npu: float, rng: float, traffic: dict, L: int) -> dict:
    eb, r_eb = B3_EB[L]
    c = dict(npu=abs(npu - eb) <= tol(eb, [r_eb, rng]),
             traffic={k: traffic.get(k) for k in B3_EB_TRAFFIC} == B3_EB_TRAFFIC)
    return dict(ok=all(c.values()), checks=c)


def equivalence(per_latency: dict) -> str:
    ok = [L for L, r in per_latency.items() if r and r["ok"]]
    return "B3_REPRODUCED" if len(ok) == 2 else ("B3_PARTIAL" if ok else "B3_NOT_REPRODUCED")


def residual(le3: float, t3: float, le3w: float, t3w: float, usable: bool) -> dict:
    """Residual_Ratio = LE_B3w / LE_B3 (point value) picks the class; the difference behind the class must exceed its
    tolerance: removal LE_B3 - LE_B3w > t3 + t3w (dominant, mixed), remaining LE_B3w > t3w (non-weight, mixed).
    The ratio's noise interval is reported, not used (with E2E-B's ranges it is about +-0.4 wide)."""
    if not usable or le3 <= t3:
        return dict(verdict="INSUFFICIENT_EVIDENCE", ratio=None, low=None, high=None)
    ratio = le3w / le3
    low = (le3w - t3w) / (le3 + t3)
    high = (le3w + t3w) / (le3 - t3)
    removed, remains = le3 - le3w > t3 + t3w, le3w > t3w
    if ratio <= LOW and removed:
        v = "WEIGHT_PATH_DOMINANT_RESPONSE"
    elif ratio >= HIGH and remains:
        v = "RESIDUAL_NON_WEIGHT_RESPONSE"
    elif LOW < ratio < HIGH and removed and remains:
        v = "MIXED_RESPONSE"
    else:
        v = "INSUFFICIENT_EVIDENCE"
    return dict(verdict=v, ratio=ratio, low=low, high=high, removal_significant=removed, remaining_significant=remains)


def validity(gate: dict, res: dict, mac_ok: dict) -> str:
    if gate.get("verdict") != "PASS" or any(r["status"] in STOP for r in res.values()):
        return "MEASUREMENT_INVALID"
    if all(r["status"] == "VALID" for r in res.values()) and all(mac_ok.values()):
        return "VALID"
    return "PARTIAL_VALID"


def mechanism() -> str:
    return "MECHANISM_UNRESOLVED"     # contract §7: no counter here attributes cycles to WD, AO, DMA or command fetch


# ---- board results ----------------------------------------------------------------------------------------------------
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
    lay = layout(recs, caps, m["placement"], h["n_in"], h["n_out"], m.get("weights_at"))
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
    res = dict(base, metrics=met, traffic=EB.traffic(met), layout=lay, base0=recs[0].get("base0"),
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


def b3_gate(root: str, wl: str, L: int) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), key("B3", int(L)))
    if r["status"] != "VALID" or r["metrics"]["mac_active"] != H1UC:
        return dict(verdict="FAIL", why=r["status"])
    rep = b3_reproduced(r["metrics"]["npu_active"], r["metrics"]["npu_active_range"], r["traffic"], int(L))
    return dict(verdict="PASS" if rep["ok"] else "FAIL", reproduce=rep)


ACTIVITY = ("npu_active", "mac_active", "mac_dpu_active", "ao_active", "wd_active", "wd_stalled")


def activity(res: dict) -> dict:
    out = {}
    for L in (500, 1000):
        a, b = res[key("B3", L)], res[key("B3w", L)]
        if a["status"] != "VALID" or b["status"] != "VALID":
            continue
        va = {**{x: a["metrics"][x] for x in ACTIVITY}, **a["traffic"]}
        vb = {**{x: b["metrics"][x] for x in ACTIVITY}, **b["traffic"]}
        out[L] = dict(B3=va, B3w=vb, delta={x: vb[x] - va[x] for x in va if None not in (va[x], vb[x])})
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
    m = lambda c, L: res[key(c, L)]["metrics"]
    t = lambda c, L: res[key(c, L)]["traffic"]
    eq = {L: (b3_reproduced(m("B3", L)["npu_active"], m("B3", L)["npu_active_range"], t("B3", L), L)
              if good(key("B3", L)) else None) for L in (500, 1000)}
    rm = {}
    for L in (500, 1000):
        if not good(key("B3w", L)):
            rm[L] = None
            continue
        ref3 = t("B3", L) if good(key("B3", L)) else B3_EB_TRAFFIC
        rm[L] = remap_ok(t("B3w", L), ref3["sram_rd_beats"], ref3["sram_rd_beats"] + ref3["ext_rd_beats"])
    equiv, remap = equivalence(eq), remap_validity(rm)
    usable = all(good(key(c, L)) for c in CELLS for L in (500, 1000))
    eff = dict(usable=usable)
    if usable:
        b = lambda c, L: m(c, L)["npu_active"]
        r = lambda c, L: m(c, L)["npu_active_range"]
        le = {c: b(c, 1000) - b(c, 500) for c in CELLS}
        t_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in CELLS}
        wpe = {L: b("B3", L) - b("B3w", L) for L in (500, 1000)}
        t_wpe = {L: tol(b("B3w", L), [r("B3", L), r("B3w", L)]) for L in (500, 1000)}
        eff.update(le=le, tol_le=t_le, weight_placement_effect=wpe, tol_wpe=t_wpe,
                   weight_path_removal_effect=le["B3"] - le["B3w"],
                   command_path_response="RESIDUAL_RESPONSE_OBSERVED" if abs(le["B3w"]) > t_le["B3w"]
                   else "RESIDUAL_RESPONSE_NOT_OBSERVED")
    res_ok = usable and equiv == "B3_REPRODUCED" and remap == "WEIGHT_SCALE_REMAP_CONFIRMED"
    rs = residual(eff["le"]["B3"], eff["tol_le"]["B3"], eff["le"]["B3w"], eff["tol_le"]["B3w"], res_ok) if usable \
        else residual(0, 0, 0, 0, False)
    summary = dict(contract="evidence/stage6b/stage6be2ed/contract.md",
                   ta="TA profile 1; EXT RLATENCY 500 / 1000; new runner images (14077be): L500 bram ec0e8c3b, L1000 bram ca7d2e49",
                   scope="NPU-internal execution time (NPU_ACTIVE); CPU staging and the weight copy are outside the measured window",
                   reference_gate=gate, results=res, mac_equals_h1uc=mac_ok, b3_equivalence=dict(per_latency=eq, verdict=equiv),
                   remap=dict(per_latency=rm, verdict=remap), effects=eff, residual=rs, activity=activity(res),
                   b3w_vela="NO_COMPARABLE_VELA_ESTIMATE",
                   verdicts=dict(measurement_validity=validity(gate, res, mac_ok), remap_validity=remap,
                                 b3_equivalence=equiv, residual_latency=rs["verdict"], pipeline_mechanism=mechanism()),
                   limits=["one boot per condition", "weights and scale/bias move together (region 0)",
                           "B3w reads region 0 through the SRAM port and TA_SRAM: port, TA and memory change together",
                           "the residual ratio is a change of latency sensitivity, not a WD stall share",
                           "drift checked once by REF"])
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2ed_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- workloads and manifest ----------------------------------------------------------------------------------------------
def workloads(eb_wl: str, out: str) -> dict:
    import drwl
    src, o = pathlib.Path(eb_wl), pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for f in ["s4c2_conv_cin48.compile.json", "s4c2_conv_cin48.drwl", "s4c2_conv_cin48.drwl.tflite_ofm.bin",
              "caps_l500.json", "caps_l1000.json"] + [f"e2eb_b3{x}" for x in
                                                      (".drwl", ".drwl.cms.bin", ".drwl.tflite_ofm.bin", ".ifm.bin", ".ref_ofm.bin")]:
        shutil.copyfile(src / f, o / f)
    if BB.sha(o / "e2eb_b3.drwl") != B3_SHA:
        raise SystemExit("B3 DRWL is not 7b2cedd5")
    (o / "e2ed_b3w.drwl").write_bytes(drwl.with_placement((o / "e2eb_b3.drwl").read_bytes(), 2))
    for x in (".drwl.cms.bin", ".drwl.tflite_ofm.bin", ".ifm.bin", ".ref_ofm.bin"):
        shutil.copyfile(o / f"e2eb_b3{x}", o / f"e2ed_b3w{x}")
    e = json.loads((src / "expected_identity.json").read_text())
    ei = {c: e[c] for c in ("s4c2_conv_cin48", "e2eb_b3")}
    ei["e2ed_b3w"] = dict(e["e2eb_b3"], drwl_sha256=BB.sha(o / "e2ed_b3w.drwl"), placement=2)
    (o / "expected_identity.json").write_text(json.dumps(ei, indent=1, sort_keys=True))
    return {c: v["drwl_sha256"] for c, v in ei.items()}


def image_of(d: str) -> dict:
    img = dict(reversed(line.split()) for line in (pathlib.Path(d) / "image.sha256").read_text().splitlines())
    return dict(boot_sha256=img["boot.bin"], bram_sha256=img["bram.bin"], ddr_sha256=img["ddr.bin"], images_txt_sha256=img["images.txt"])


def manifest(wl: str, img500: str, img1000: str) -> dict:
    import drwl
    wlp = pathlib.Path(wl)
    k4 = json.loads((wlp / "s4c2_conv_cin48.compile.json").read_text())
    caps = json.loads((wlp / "caps_l500.json").read_text())
    images = {500: image_of(img500), 1000: image_of(img1000)}
    out = {}
    for cell, lat, boot in ORDER:
        cfg = DRWL[cell]
        mm = dict(kind="reference", n_mac=k4["n_mac"], cin=48, internal_conv="CONV_OUTPUT_OBSERVED") if cell == "REF" else \
            dict(kind="A2", n_mac=19501056, cin=276, internal_conv="INTERNAL_CONV_NOT_OBSERVED")
        h = drwl.parse((wlp / f"{cfg}.drwl").read_bytes())
        if h["placement"] != PLACEMENT[cell]:
            raise SystemExit(f"{cfg}: DRWL placement {h['placement']} != frozen {PLACEMENT[cell]}")
        arena = EB.expected_arena(min(PLACEMENT[cell], 1), caps["model_base"], h["model_len"], caps["fast_base"], caps["fast_size"])
        wat = weight_dst(arena, ARENA_LEN, SRAM_LIMIT, WEIGHTS_SRC, WEIGHTS_LEN) if PLACEMENT[cell] == 2 else None
        out[key(cell, lat)] = dict(mm, cell=cell, config=cfg, boot=boot, latency=lat, placement=PLACEMENT[cell],
                                   drwl_sha256=BB.sha(wlp / f"{cfg}.drwl"), arena_base=arena, weights_at=wat,
                                   image=images[lat], ta_ext_rlatency=lat,
                                   caps_ref="caps_l500.json" if lat == 500 else "caps_l1000.json")
    (wlp / MANIFEST).write_text(json.dumps(out, indent=1, sort_keys=True))
    return out


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "workloads":
        print(json.dumps(workloads(*a[:2]), indent=1)); return 0
    if cmd == "manifest":
        manifest(*a[:3]); return 0
    if cmd == "boot-check":
        r = boot_check(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "repro-gate":
        r = repro_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "b3-gate":
        r = b3_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge":
        r = judge(*a[:5])
        print(json.dumps({k: r[k] for k in ("verdicts", "effects", "residual", "remap", "b3_equivalence")}, indent=1,
                         default=str)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
