#!/usr/bin/env python3
"""Stage 6G-X_LAT — group-level EXT read latency sensitivity vs Vela (contract evidence/stage6gxlat/contract.md).

Per-boot checks are Stage 6E-X3's (host/analysis/stage6ex3.py) with this stage's image, boot and TA latency.

  stage6gxlat.py boot-check <roots> <wl dir> <caps L500 json> <key> <L>
  stage6gxlat.py judge <roots> <wl dir> <caps L500 json> <vela dir> <out dir>
<roots> = "x3b=<X3 run root holding kws B0/B1>,x3c=<X3 amendment C run root>,l250=<run root>,l1000=<run root>"
"""
from __future__ import annotations

import contextlib
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6ex3 as X  # noqa: E402

MODELS = ("kws_micronet_m", "ad_medium_int8")
GROUP_KEY = {"G_V": "B2", "G_0": "B3", "G_R": "B4"}
LAT_NEW = (250, 1000)
BOOTS = {("x3_kws_B2", 250): 505, ("x3_kws_B2", 1000): 506, ("x3_kws_B3", 1000): 507, ("x3_kws_B3", 250): 508,
         ("x3_kws_B4", 250): 509, ("x3_kws_B4", 1000): 510, ("x3_ad_B2", 1000): 511, ("x3_ad_B2", 250): 512,
         ("x3_ad_B3", 250): 513, ("x3_ad_B3", 1000): 514, ("x3_ad_B4", 1000): 515, ("x3_ad_B4", 250): 516}
IMAGES = {  # container builds of f0baf8c with -DEXT_RLATENCY (evidence/stage6gxlat/image_L*/image/image.sha256)
    250: dict(boot_sha256=X.IMAGE["boot_sha256"],
              bram_sha256="4f5f54aa2e5d49054769bd25897d6c3dcb55149510e0de4a3faea43fc2991d15", ddr_sha256=X.IMAGE["ddr_sha256"],
              images_txt_sha256=X.IMAGE["images_txt_sha256"]),
    1000: dict(boot_sha256=X.IMAGE["boot_sha256"],
               bram_sha256="7004c53022901a0cc9d9b46e53cf2066bdb0b666ec1856b203d6b3e8fc775e47", ddr_sha256=X.IMAGE["ddr_sha256"],
               images_txt_sha256=X.IMAGE["images_txt_sha256"]),
}
INV_TOL = 0.01                 # compute invariance and traffic comparability (X3 EV_TOL)
MAG_TOL = 0.15                 # E2B primary: |dB - dV| <= 0.15 |dV| + tol
IDENT = 0.5                    # E2B identifiability: tol > 0.5 max(|dV|, |dB|) -> INSUFFICIENT
REL_FLOOR = 0.01               # tol floor, fraction of the larger median
DRAM_SHARE = 0.5               # H-L2: a group is DRAM-dominated if >= half its L500 Op Cycles are DRAM-bound
MECH_SHARE = 0.5               # pipeline: an observed stall delta >= half the NPU delta, same sign
MECH_EVENTS = (81, 55, 387)    # WD_STALLED, MAC_STALLED_BY_IB, EXT read address handshake stall
TRAFFIC = (130, 135, 386, 391)


# ---- per-boot check (X3 functions, this stage's identity) --------------------------------------------------------
@contextlib.contextmanager
def x3_identity(key: str, lat: int):
    saved = (X.IMAGE, X.BOOT, X.EXT_RLATENCY, X.KEY_ROOT)
    try:
        X.IMAGE = IMAGES[lat]
        X.BOOT = {key: BOOTS[(key, lat)]}
        X.EXT_RLATENCY = lat
        X.KEY_ROOT = {"x3_kws_B0": "x3b", "x3_ad_B0": "x3c", key: f"l{lat}"}
        yield
    finally:
        X.IMAGE, X.BOOT, X.EXT_RLATENCY, X.KEY_ROOT = saved


def caps_for(caps500: dict, lat: int) -> dict:
    return dict(caps500, ta_ext_rlatency=lat)


def check(roots: dict, wl: pathlib.Path, caps500: dict, key: str, lat: int) -> dict:
    with x3_identity(key, lat):
        return X.config_result(roots, wl, None, caps_for(caps500, lat), key)


def check_l500(roots: dict, wl: pathlib.Path, caps500: dict, key: str) -> dict:
    """The X3 group boots (497-499, 502-504) with X3's own identity."""
    return X.config_result({"b": roots["x3b"], "c": roots["x3c"]}, wl, None, caps500, key)


# ---- Vela per latency -------------------------------------------------------------------------------------------
def vela_comparable(vj: dict, model: str, lat: int) -> bool:
    e = vj["models"][model]
    return e[f"L{lat}"]["cms_sha256"] == e["base"]["cms_sha256"] and e["L500"]["cms_sha256"] == e["base"]["cms_sha256"]


def vela_group(rows: list[dict], ops: list[int]) -> dict:
    sel = [rows[i] for i in ops]
    term = lambda r: max(("NPU", "SRAM AC", "DRAM AC"), key=lambda t: float(r[t]))
    oc = sum(float(r["Op Cycles"]) for r in sel)
    return dict(op_cycles=oc, npu=sum(float(r["NPU"]) for r in sel), sram=sum(float(r["SRAM AC"]) for r in sel),
                dram=sum(float(r["DRAM AC"]) for r in sel), bound=[term(r) for r in sel],
                dram_bound_share=(sum(float(r["Op Cycles"]) for r in sel if term(r) == "DRAM AC") / oc) if oc else 0.0)


def per_layer(vela_dir: pathlib.Path, model: str, lat: int) -> list[dict]:
    with (vela_dir / model / f"L{lat}" / f"{model}_per-layer.csv").open(newline="") as f:
        return [r for r in csv.DictReader(f) if float(r["Op Cycles"]) > 0]


# ---- comparison rules ---------------------------------------------------------------------------------------------
def tol_of(cap: float, ra: float, rb: float, ba: float, bb: float) -> float:
    return max(cap, ra + rb, REL_FLOOR * max(ba, bb))


def response(db: float, tol: float) -> str:
    return "SENSITIVE" if abs(db) > tol else "NOT_DETECTABLY_SENSITIVE"


def fidelity(db: float, dv: float, tol: float) -> str:
    if tol > IDENT * max(abs(dv), abs(db)):
        return "INSUFFICIENT_EVIDENCE"
    if abs(db - dv) <= MAG_TOL * abs(dv) + tol:
        return "DIRECTION_AND_MAGNITUDE_CONSISTENT"
    if abs(db) > tol and abs(dv) > tol and (db > 0) == (dv > 0):
        return "DIRECTION_ONLY_CONSISTENT"
    return "INCONSISTENT"


def overall_fidelity(per_group: list[str]) -> str:
    t = [v for v in per_group if v != "INSUFFICIENT_EVIDENCE"]
    if not t:
        return "INSUFFICIENT_EVIDENCE"
    if "INCONSISTENT" in t:
        return "INCONSISTENT"
    if all(v == "DIRECTION_AND_MAGNITUDE_CONSISTENT" for v in t):
        return "DIRECTION_AND_MAGNITUDE_CONSISTENT"
    return "DIRECTION_ONLY_CONSISTENT"


def invariant(vals: dict, ref: float) -> bool:
    return all(v is not None and abs(v - ref) <= INV_TOL * ref for v in vals.values())


def mechanism(sensitive: list[dict]) -> str:
    """sensitive: [{'db': NPU delta, 'ev': {code: delta}}] for SENSITIVE groups (250 -> 1000 or the primary segment)."""
    if not sensitive:
        return "MECHANISM_UNRESOLVED"
    ok = all(any(e.get(c) is not None and (e[c] > 0) == (g["db"] > 0) and abs(e[c]) >= MECH_SHARE * abs(g["db"])
                 for c in MECH_EVENTS for e in (g["ev"],)) for g in sensitive)
    return "PARTIALLY_SUPPORTED" if ok else "MECHANISM_UNRESOLVED"


def h_l2(groups: list[dict]) -> str:
    """groups: [{'dram_share': L500 Vela DRAM-bound share, 'rel': dB / B250}] — every DRAM-dominated group responds more
    (relative) than every other group."""
    d = [g["rel"] for g in groups if g["dram_share"] >= DRAM_SHARE]
    n = [g["rel"] for g in groups if g["dram_share"] < DRAM_SHARE]
    if not d or not n:
        return "INSUFFICIENT_EVIDENCE"
    return "SUPPORTED" if min(d) > max(n) else "REFUTED"


def measurement(statuses: list[str]) -> str:
    if any(s in X.STOP for s in statuses) or not any(s == "VALID" for s in statuses):
        return "MEASUREMENT_INVALID"
    return "VALID" if all(s == "VALID" for s in statuses) else "PARTIAL_VALID"


# ---- judge ---------------------------------------------------------------------------------------------------------
def med(r: dict, s: int, c: int):
    return X.val(r, s, c)


def judge(roots: dict, wl: pathlib.Path, caps500: dict, vela_dir: pathlib.Path) -> dict:
    vj = json.loads((vela_dir / "xlat_vela.json").read_text())
    man = json.loads((wl / X.MANIFEST).read_text())
    res = {f"{k}@L{lat}": check(roots, wl, caps500, k, lat) for (k, lat) in BOOTS}
    l500 = {k: check_l500(roots, wl, caps500, k) for k in {k for k, _ in BOOTS}}
    groups, fids, sens, l2 = {}, [], [], []
    inv_all = []
    for m in MODELS:
        tfl = X.tflite_groups(man[X.key(m, "B0")])
        rows = {lat: per_layer(vela_dir, m, lat) for lat in (250, 500, 1000)}
        cap = X.GROUP_CAP[m]
        for g, c in GROUP_KEY.items():
            k = X.key(m, c)
            by = {250: res[f"{k}@L250"], 500: l500[k], 1000: res[f"{k}@L1000"]}
            ok = {lat: r["status"] == "VALID" for lat, r in by.items()}
            b = {lat: med(r, 1, 35) if ok[lat] else (None, None) for lat, r in by.items()}
            vg = {lat: vela_group(rows[lat], tfl[g]) for lat in rows}
            comp = {lat: vela_comparable(vj, m, lat) for lat in (250, 1000)}
            seg = (250, 1000) if comp[250] and comp[1000] else (250, 500) if comp[250] else None
            e = dict(key=k, ops_tflite=tfl[g], status={f"L{lat}": by[lat]["status"] for lat in by},
                     npu={f"L{lat}": b[lat][0] for lat in b}, npu_range={f"L{lat}": b[lat][1] for lat in b},
                     vela={f"L{lat}": vg[lat] for lat in vg}, vela_comparable={f"L{lat}": comp[lat] for lat in comp},
                     segment=list(seg) if seg else None)
            macs = {lat: med(by[lat], 1, 48)[0] if ok[lat] else None for lat in by}
            dpus = {lat: med(by[lat], 1, 51)[0] if ok[lat] else None for lat in by}
            if all(ok.values()):
                inv = invariant(macs, macs[500]) and invariant(dpus, dpus[500])
                e["compute_invariant"] = inv
                inv_all.append(inv)
                e["traffic_comparable"] = all(invariant({lat: med(by[lat], 2, t)[0] for lat in by},
                                                         med(by[500], 2, t)[0]) for t in TRAFFIC if med(by[500], 2, t)[0])
                ev = {lat: {cc: med(by[lat], s, cc)[0] for s, cs in X.SETS.items() for cc in cs} for lat in by}
                e["events"] = {f"L{lat}": ev[lat] for lat in ev}
                tol = tol_of(cap, b[250][1], b[1000][1], b[250][0], b[1000][0])
                db = b[1000][0] - b[250][0]
                e.update(delta_B=db, tol_250_1000=tol, response=response(db, tol) if inv else "CONFOUNDED",
                         slope_250_500=(b[500][0] - b[250][0]) / 250, slope_500_1000=(b[1000][0] - b[500][0]) / 500)
                if inv:
                    lo, hi = seg if seg else (250, 1000)
                    st = tol_of(cap, b[lo][1], b[hi][1], b[lo][0], b[hi][0])
                    dbs, dvs = b[hi][0] - b[lo][0], vg[hi]["op_cycles"] - vg[lo]["op_cycles"]
                    f = fidelity(dbs, dvs, st) if seg else "INSUFFICIENT_EVIDENCE"
                    e.update(delta_B_segment=dbs, delta_V_segment=dvs if seg else None, tol_segment=st,
                             prediction_error_delta=(dbs - dvs) if seg else None, fidelity=f)
                    fids.append(f)
                    if e["response"] == "SENSITIVE":
                        sens.append(dict(db=db, ev={cc: ev[1000][cc] - ev[250][cc] for cc in MECH_EVENTS}))
                    l2.append(dict(dram_share=vg[500]["dram_bound_share"], rel=db / b[250][0]))
            else:
                e.update(response="INSUFFICIENT_EVIDENCE", fidelity="INSUFFICIENT_EVIDENCE")
                fids.append("INSUFFICIENT_EVIDENCE")
            e["delta_V"] = {"250_500": vg[500]["op_cycles"] - vg[250]["op_cycles"],
                            "500_1000": vg[1000]["op_cycles"] - vg[500]["op_cycles"],
                            "250_1000": vg[1000]["op_cycles"] - vg[250]["op_cycles"]}
            groups[f"{m}:{g}"] = e
    resp = [g["response"] for g in groups.values()]
    verdicts = dict(
        measurement=measurement([r["status"] for r in res.values()]),
        compute_invariance="INSUFFICIENT_EVIDENCE" if not inv_all else ("SUPPORTED" if all(inv_all) else "REFUTED"),
        latency_response={k: g["response"] for k, g in groups.items()},
        latency_response_overall="SENSITIVE" if "SENSITIVE" in resp else (
            "NOT_DETECTABLY_SENSITIVE" if "NOT_DETECTABLY_SENSITIVE" in resp else "INSUFFICIENT_EVIDENCE"),
        vela_term_fidelity=overall_fidelity(fids),
        h_l2_term_dominance=h_l2(l2),
        pipeline_mechanism=mechanism(sens))
    return dict(contract="evidence/stage6gxlat/contract.md", boots={f"{k}@L{lat}": n for (k, lat), n in BOOTS.items()},
                results=res, l500=l500, groups=groups, verdicts=verdicts)


def parse_roots(s: str) -> dict:
    return dict(x.split("=", 1) for x in s.split(","))


def main(argv: list) -> int:
    if len(argv) >= 7 and argv[1] == "boot-check":
        roots, wl, caps = parse_roots(argv[2]), pathlib.Path(argv[3]), json.loads(pathlib.Path(argv[4]).read_text())
        r = check(roots, wl, caps, argv[5], int(argv[6]))
        print(json.dumps(dict(key=argv[5], lat=int(argv[6]), status=r["status"], reasons=r["reasons"]), indent=1))
        return 0 if r["status"] == "VALID" else 1
    if len(argv) == 7 and argv[1] == "judge":
        roots, wl, caps = parse_roots(argv[2]), pathlib.Path(argv[3]), json.loads(pathlib.Path(argv[4]).read_text())
        s = judge(roots, wl, caps, pathlib.Path(argv[5]))
        out = pathlib.Path(argv[6])
        out.mkdir(parents=True, exist_ok=True)
        (out / "stage6gxlat_summary.json").write_text(json.dumps(s, indent=1, sort_keys=True, default=str) + "\n")
        print(json.dumps(s["verdicts"]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
