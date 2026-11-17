#!/usr/bin/env python3
"""Stage 6E-X3 judge (contract evidence/stage6ex3/contract.md + amendment B evidence/stage6ex3/amendment_b.md): kws/ad,
B0 original, B1 serialised, B2-B4 group windows; amendment C (evidence/stage6ex3/amendment_c.md): kws B0/B1 = boots
487/488 of the amendment B run (root "b"), the rest = boots 497-504 (root "c"); boots 477 and 489 stay judged by their
own rules (result_g1.md, result_b.md).

  <roots> = b=<amendment B run root>,c=<amendment C run root>   (or one path holding every key)
  python3 stage6ex3.py boot-check <roots> <workloads> <m7 root> <caps ref> <key>     rc 1 = stop
  python3 stage6ex3.py gate-g1    <roots> <workloads> <m7 root> <caps ref> <model>   rc 1 = stop
  python3 stage6ex3.py gate-gm    <roots> <workloads> <m7 root> <caps ref> <model>   rc 1 = stop (kws)
  python3 stage6ex3.py judge      <roots> <workloads> <m7 root> <caps ref> <vela dir> <out dir>
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import statistics
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import drwl  # noqa: E402
import record_v2  # noqa: E402

MANIFEST = "x3_manifest.json"
PASS_A = [35, 48, 51, 53, 55, 64, 80, 81]
PASS_B = [35, 128, 130, 132, 135, 384, 386, 391]
PASS_C = [35, 131, 142, 387, 640, 642, 656, 658]
SETS = {1: PASS_A, 2: PASS_B, 3: PASS_C}
REPS = 5                      # 1 warm-up + 4 measured per set
IMAGE = dict(boot_sha256="3b4af743c13aa25f4335a30b739f196187ed023ea9f3f1d3a372a851b9c630c3",
             bram_sha256="9b1844a3fde3443779d341f890cd2d106ab92e593020f8e336fbc5f991dd740f",
             ddr_sha256="374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb",
             images_txt_sha256="af688281435a73dda3b2247845149817ecc7a9bbdff5a3ccd2e4dfa52875423f")
BOOT = {"x3_kws_B0": 487, "x3_kws_B1": 488, "x3_kws_B2": 497, "x3_kws_B3": 498, "x3_kws_B4": 499,
        "x3_ad_B0": 500, "x3_ad_B1": 501, "x3_ad_B2": 502, "x3_ad_B3": 503, "x3_ad_B4": 504}
KEY_ROOT = {k: "b" if k in ("x3_kws_B0", "x3_kws_B1") else "c" for k in BOOT}
GROUP_COND = ("B2", "B3", "B4")
GROUP_CAP = {"kws_micronet_m": 2423.0, "ad_medium_int8": 2596.0}   # amendment C: largest m7 per-set NPU_ACTIVE range
# amendment B: counters that must equal m7 exactly in G1 (MAC, DPU, SRAM/EXT beats and transactions, per-port EXT)
DETERMINISTIC = (48, 51, 128, 130, 132, 135, 384, 386, 391, 640, 642, 656, 658)
MODEL_KEY = {"kws_micronet_m": "kws", "ad_medium_int8": "ad"}
SCHEMA, RECORD_FIELDS, LOG2_MACS, EXT_RLATENCY = 5, 92, 10, 500
MASK_EN = 0x8
NPU_TOL = 0.01                # G1 NPU_ACTIVE
EV_TOL = 0.01                 # G1 other events, H-S, H-P, M3
UNSTABLE_REL = 0.05
M2_MAX = 0.95
F5_MAC, F5_TOL = 26090.0, 0.01        # 6C F5 (kws op0 isolated), M4 / H-K G_0
H1UC_KWS, H1UC_AD, H1UC_TOL = 11700.0, 60480.0, 0.05
VELA_LO, VELA_HI = 0.9, 1.1
STOP = ("UNMEASURED", "CONFIG_MISMATCH", "INVALID_OUTPUT")


def root_of(roots, k: str) -> pathlib.Path:
    return pathlib.Path(roots[KEY_ROOT[k]]) if isinstance(roots, dict) else pathlib.Path(roots)


def key(model: str, cond: str) -> str:
    return f"x3_{MODEL_KEY[model]}_{cond}"


def med_range(vals: list) -> tuple:
    if not vals:
        return None, None
    return float(statistics.median(vals)), float(max(vals) - min(vals))


def events_of(rec: dict) -> dict:
    return {rec[f"event_code{i}"]: rec[f"ev_irq{i}"] for i in range(rec["event_count"])}


# ---- per boot ----------------------------------------------------------------------------------------------------
def load(folder: pathlib.Path) -> dict:
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    with (folder / "runs.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    cp = folder.parent / "capabilities.json"
    return dict(raw=raw, rows=rows, caps=json.loads(cp.read_text()) if cp.exists() else {})


def stats(raw: list, measured_from: int = 2) -> dict:
    """{set: {code: (median, range)}} over measured RUNs (rep >= measured_from)."""
    out = {}
    for s, codes in SETS.items():
        rs = [events_of(x["record"]) for x in raw if x["set_id"] == s and x["rep"] >= measured_from]
        out[s] = {c: med_range([r[c] for r in rs if c in r]) for c in codes}
    return out


def m7_ref(m7_root: pathlib.Path, model: str) -> dict:
    """Per event (median, range) over the m7 measured RUNs (2 warm-up of 10), any m7 set holding the event; output CRC."""
    raw = json.loads((m7_root / model / "raw_runs.json").read_text())[1:]
    ev = {}
    for x in raw:
        if x["rep"] <= 2:
            continue
        for c, v in events_of(x["record"]).items():
            ev.setdefault((x["set_id"], c), []).append(v)
    pa = {c: med_range(v) for (s, c), v in ev.items() if s == 2}           # m7 set 2 = pass A
    any_set = {}
    for (s, c), v in sorted(ev.items()):
        any_set.setdefault(c, v)
    ref = {c: med_range(v) for c, v in any_set.items()}
    ref[35] = pa[35]                                                         # NPU_ACTIVE: pass A against pass A
    cap = max(max(v) - min(v) for (s, c), v in ev.items() if c == 35)       # largest m7 per-set NPU_ACTIVE range
    return dict(events=ref, npu_range_cap=float(cap))


def identity(d: dict, m: dict, k: str, caps_ref: dict, model_len: int) -> list[str]:
    bad, rows, recs, caps = [], d["rows"], [x["record"] for x in d["raw"]], d["caps"]
    if not rows:
        return ["no RUN rows"]
    if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:
        bad.append("workload sha256")
    for f, v in IMAGE.items():
        if {r[f] for r in rows} != {v}:
            bad.append(f"image {f}")
    if {r["host_boot_index"] for r in rows} != {str(BOOT[k])}:
        bad.append("boot index")
    if {r["condition"] for r in rows} != {"wfe"}:
        bad.append("condition")
    ta = {x: v for x, v in caps.items() if x.startswith("ta_")}
    if not ta or ta != {x: v for x, v in caps_ref.items() if x.startswith("ta_")}:
        bad.append("TA registers")
    if caps.get("ta_ext_rlatency") != EXT_RLATENCY:
        bad.append("TA EXT RLATENCY")
    if (caps.get("npu_config", 0) & 0xF) != LOG2_MACS:
        bad.append("NPU MAC count")
    if caps.get("schema") != SCHEMA or caps.get("record_fields") != RECORD_FIELDS:
        bad.append("record schema (capabilities)")
    checks = dict(schema=all(r.get("schema") == SCHEMA for r in recs),
                  placement=all(r.get("placement") == 0 for r in recs),
                  model_len=bool(recs) and all(r.get("model_len") == model_len for r in recs),
                  pmu_flags=all(r.get("pmu_flags") == m["pmu_flags"] for r in recs),
                  mask_en=all(bool(r.get("pmcr_after_arm", 0) & MASK_EN) == bool(m["pmu_flags"]) for r in recs),
                  irq=all(r.get("irq_count") == 1 for r in recs))
    return bad + [f"record {c}" for c, ok in checks.items() if not ok]


def output_bad(d: dict, crc_ref) -> list[str]:
    """Every RUN equals the DRWL golden (the m7 golden; OUTPUT_MATCH, ofm_mismatch 0), one output CRC; for B1-B4 that CRC
    equals this run's B0 CRC (crc_ref; None = B0 itself, "MISSING" = B0 not available)."""
    bad = []
    if not all(x["record"].get("ofm_mismatch") == 0 and x["valid_flags"] & record_v2.OUTPUT_MATCH for x in d["raw"]):
        bad.append("output != golden")
    crcs = {x.get("output_crc32") for x in d["raw"]}
    if len(crcs) != 1 or None in crcs:
        bad.append("output CRC missing or differs between RUNs")
    elif crc_ref is not None and crcs != {crc_ref}:
        bad.append("output CRC != B0 (original)")
    return bad


def b0_crc(root, model: str):
    p = root_of(root, key(model, "B0")) / "conds" / key(model, "B0") / "wfe" / "raw_runs.json"
    if not p.exists():
        return "MISSING"
    crcs = {x.get("output_crc32") for x in json.loads(p.read_text())[1:]}
    return crcs.pop() if len(crcs) == 1 and None not in crcs else "MISSING"


def pmu_bad(d: dict) -> list[str]:
    bad = []
    raw = d["raw"]
    if len(raw) != len(SETS) * REPS or sorted((x["set_id"], x["rep"]) for x in raw) != \
            [(s, r) for s in SETS for r in range(1, REPS + 1)]:
        bad.append("RUN layout (3 passes x (1 warm-up + 4))")
    for x in raw:
        codes = SETS.get(x["set_id"], [])
        ok, why = record_v2.validity(record_v2.Record(x["run_sequence"], x["valid_flags"], x["run_rc"], x["record"]),
                                     codes)
        if not ok:
            bad.append(f"set {x['set_id']} RUN invalid: {' '.join(why)}")
        if sorted(events_of(x["record"])) != sorted(codes):
            bad.append(f"set {x['set_id']} counters missing or wrong pass")
    return sorted(set(bad))


def unstable(st: dict, raw: list, cap: float | None = None) -> list[str]:
    """cap: amendment C group windows (B2-B4) — pass A NPU_ACTIVE range limit max(5 %, cap) instead of 5 %."""
    bad = []
    for c in (48, 51):
        vals = {events_of(x["record"]).get(c) for x in raw if x["set_id"] == 1 and x["rep"] >= 2}
        if len(vals) != 1:
            bad.append(f"event {c} differs between RUNs")
    a, ra = st[1][35]
    for s in (2, 3):
        x, rx = st[s][35]
        if a is None or x is None or abs(x - a) > max(UNSTABLE_REL * a, ra + rx):
            bad.append(f"NPU_ACTIVE pass A vs pass {'B' if s == 2 else 'C'}")
    if a and ra > (max(UNSTABLE_REL * a, cap) if cap is not None else UNSTABLE_REL * a):
        bad.append("NPU_ACTIVE pass A range")
    return bad


def config_result(root, wl: pathlib.Path, m7: pathlib.Path, caps_ref: dict, k: str) -> dict:
    m = json.loads((wl / MANIFEST).read_text())[k]
    folder = root_of(root, k) / "conds" / k / "wfe"
    base = dict(key=k, model=m["model"], cond=m["cond"])
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    d = load(folder)
    model_len = drwl.parse((wl / f"{k}.drwl").read_bytes())["model_len"]
    ident = identity(d, m, k, caps_ref, model_len)
    if ident:
        return dict(base, status="CONFIG_MISMATCH", reasons=ident)
    ob = output_bad(d, None if m["cond"] == "B0" else b0_crc(root, m["model"]))
    if ob:
        return dict(base, status="INVALID_OUTPUT", reasons=ob)
    pb = pmu_bad(d)
    if pb:
        return dict(base, status="INVALID_PMU", reasons=pb)
    st = stats(d["raw"])
    res = dict(base, stats={s: {str(c): v for c, v in e.items()} for s, e in st.items()})
    cap = GROUP_CAP[m["model"]] if m["cond"] in GROUP_COND else None
    if cap is not None:
        a = [events_of(x["record"])[35] for x in d["raw"] if x["set_id"] == 1 and x["rep"] >= 2]
        med = st[1][35][0]
        lim = max(UNSTABLE_REL * med, cap)
        res["window_npu"] = dict(median=med, min=min(a), max=max(a), range=max(a) - min(a),
                                 rel_range=(max(a) - min(a)) / med if med else None, gs_limit=lim,
                                 rel_limit=lim / med if med else None)
    u = unstable(st, d["raw"], cap)
    return dict(res, status="UNSTABLE" if u else "VALID", reasons=u)


def val(r: dict, s: int, c: int):
    return (r.get("stats") or {}).get(s, {}).get(str(c), (None, None))


# ---- gates -------------------------------------------------------------------------------------------------------
def g1(b0: dict, ref: dict) -> dict:
    """Original reproduction of one model's B0 against m7 (amendment B): NPU_ACTIVE within max(1 % of m7,
    range_m7 + range_B0) with range_B0 <= the largest m7 per-set range; deterministic counters exactly equal (every
    measured RUN, m7 range 0); the other counters within max(1 %, range sum)."""
    if b0["status"] != "VALID":
        return dict(verdict="FAIL", why=f"B0 {b0['status']}", reasons=b0["reasons"])
    bad = []
    npu, rb = val(b0, 1, 35)
    rn, rm = ref["events"][35]
    tol = max(NPU_TOL * rn, rm + rb) if rn is not None and rb is not None else None
    if npu is None or rn is None or abs(npu - rn) > tol:
        bad.append(f"NPU_ACTIVE {npu} vs m7 {rn} (tolerance {tol})")
    if rb is None or rb > ref["npu_range_cap"]:
        bad.append(f"NPU_ACTIVE range {rb} > m7 largest set range {ref['npu_range_cap']}")
    for s, codes in SETS.items():
        for c in codes:
            if c == 35 or c not in ref["events"]:
                continue
            v, rv = val(b0, s, c)
            mv, rmv = ref["events"][c]
            if c in DETERMINISTIC:
                if v is None or v != mv or rv != 0 or rmv != 0:
                    bad.append(f"deterministic event {c} {v} (range {rv}) vs m7 {mv} (range {rmv})")
            elif v is None or abs(v - mv) > max(EV_TOL * mv, rmv + rv):
                bad.append(f"event {c} {v} vs m7 {mv}")
    return dict(verdict="FAIL" if bad else "PASS", reasons=bad,
                npu=dict(b0=npu, m7=rn, delta=None if npu is None or rn is None else npu - rn, tolerance=tol,
                         range_b0=rb, range_m7=rm, range_cap=ref["npu_range_cap"]))


def partition(res: dict, model: str, code: int) -> dict:
    whole = res[key(model, "B1")]
    parts = [res[key(model, c)] for c in ("B2", "B3", "B4")]
    w, rw = val(whole, 1, code)
    vs = [val(p, 1, code) for p in parts]
    if w is None or any(v is None for v, _ in vs):
        return dict(holds=False, why="missing")
    s = sum(v for v, _ in vs)
    tol = max(EV_TOL * w, rw + sum(r for _, r in vs))
    return dict(holds=abs(s - w) <= tol, whole=w, sum=s, tol=tol)


def m2(res: dict, model: str) -> dict:
    w, _ = val(res[key(model, "B1")], 1, 35)
    out = {}
    for c in ("B2", "B3", "B4"):
        v, _ = val(res[key(model, c)], 1, 35)
        out[c] = w is not None and v is not None and 0 < v < M2_MAX * w
    return dict(holds=all(out.values()), each=out)


def gm(res: dict, model: str) -> dict:
    need = [key(model, c) for c in ("B1", "B2", "B3", "B4")]
    if any(res[k]["status"] not in ("VALID", "UNSTABLE") for k in need):
        return dict(verdict="FAIL", why="serial boots not measured validly")
    r2 = m2(res, model)
    r3 = {c: partition(res, model, c) for c in (35, 48)}
    mac0, _ = val(res[key(model, "B3")], 1, 48)
    r4 = model != "kws_micronet_m" or (mac0 is not None and abs(mac0 - F5_MAC) <= F5_TOL * F5_MAC)
    ok = r2["holds"] and all(x["holds"] for x in r3.values()) and r4
    return dict(verdict="PASS" if ok else "FAIL", m2=r2, m3=r3, m4=r4, mac_g0=mac0)


# ---- hypotheses and verdicts ---------------------------------------------------------------------------------------
def h_s(res, model):
    a, _ = val(res[key(model, "B0")], 1, 48)
    b, _ = val(res[key(model, "B1")], 1, 48)
    if a is None or b is None:
        return "INSUFFICIENT_EVIDENCE"
    return "SUPPORTED" if abs(b - a) <= EV_TOL * a else "REFUTED"


def h_k(res):
    g0, _ = val(res[key("kws_micronet_m", "B3")], 1, 48)
    gv, _ = val(res[key("kws_micronet_m", "B2")], 1, 48)
    f = lambda v, ref, t: "INSUFFICIENT_EVIDENCE" if v is None else ("SUPPORTED" if abs(v - ref) <= t * ref else "REFUTED")
    return dict(G_0=f(g0, F5_MAC, F5_TOL), G_V=f(gv, H1UC_KWS, H1UC_TOL), mac_g0=g0, mac_gv=gv)


def h_a(res, attribution_ok: bool):
    gv, _ = val(res[key("ad_medium_int8", "B2")], 1, 48)
    if not attribution_ok or gv is None:
        return dict(verdict="INSUFFICIENT_EVIDENCE", mac_gv=gv)
    if gv > (1 + H1UC_TOL) * H1UC_AD:
        v = "H_A2_SUPPORTED"
    elif gv < (1 - H1UC_TOL) * H1UC_AD:
        v = "NEITHER"
    else:
        v = "H_A1_SUPPORTED"
    return dict(verdict=v, mac_gv=gv)


def h_o(res, model):
    b0, b1 = res[key(model, "B0")], res[key(model, "B1")]
    if b0["status"] != "VALID" or b1["status"] != "VALID":
        return dict(verdict="INSUFFICIENT_EVIDENCE")
    a, ra = val(b0, 1, 35)
    b, rb = val(b1, 1, 35)
    d = b - a
    tol = max(EV_TOL * a, ra + rb)
    return dict(verdict="SCHEDULE_EFFECT_OBSERVED" if abs(d) > tol else "NO_SIGNIFICANT_EFFECT", delta=d, tol=tol)


def vela_cls(r: float) -> str:
    return "OVER" if r < VELA_LO else "UNDER" if r > VELA_HI else "AGREE"


def vela_cls_noise(npu: float, rng: float, vela: float) -> str:
    """Amendment C: a class boundary (0.9 or 1.1 x Vela) within the measured range of the median -> undecidable."""
    if rng > 0 and any(abs(npu - b * vela) <= rng for b in (VELA_LO, VELA_HI)):
        return "INSUFFICIENT_EVIDENCE"
    return vela_cls(npu / vela)


def vela_groups(vela_dir: pathlib.Path, model: str, groups_tfl: dict) -> dict:
    """Group sums of Vela per-layer terms; rows with Op Cycles > 0 in TFLite order."""
    with (vela_dir / f"out_{model}" / f"{model}_per-layer.csv").open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if float(r["Op Cycles"]) > 0]
    with (vela_dir / f"out_{model}" / f"{model}_summary_Ethos_U85_SYS_DRAM_Mid_1024.csv").open(newline="") as f:
        summ = next(csv.DictReader(f))
    out = {}
    for g, ops in groups_tfl.items():
        sel = [rows[i] for i in ops]
        term = lambda r: max(("NPU", "SRAM AC", "DRAM AC"), key=lambda t: float(r[t]))
        out[g] = dict(op_cycles=sum(float(r["Op Cycles"]) for r in sel), npu=sum(float(r["NPU"]) for r in sel),
                      sram=sum(float(r["SRAM AC"]) for r in sel), dram=sum(float(r["DRAM AC"]) for r in sel),
                      bound=[term(r) for r in sel])
    return dict(groups=out, cycles_total=float(summ["cycles_total"]), cycles_npu=float(summ["cycles_npu"]))


def tflite_groups(m: dict) -> dict:
    """Stream ops -> TFLite op indices via the op map (source_id - 1), per group."""
    with (REPO / "results/fi101_stage2_groups/vela_op_map" / f"{m['model']}.op_map.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    src = {int(r["index"]): int(r["source_id"]) - 1 for r in rows}
    return {g: sorted({src[i] for i in ops}) for g, ops in m["groups"].items()}


def judge(root, wl, m7, caps_ref, vela_dir) -> dict:
    wl, m7, vela_dir = map(pathlib.Path, (wl, m7, vela_dir))
    man = json.loads((wl / MANIFEST).read_text())
    res = {k: config_result(root, wl, m7, caps_ref, k) for k in BOOT}
    models = ("kws_micronet_m", "ad_medium_int8")
    gates = {m: dict(g1=g1(res[key(m, "B0")], m7_ref(m7, m)), gm=gm(res, m)) for m in models}
    gs = {k: res[k]["status"] == "VALID" for k in BOOT if not k.endswith("B0")}
    kws_gm = gates["kws_micronet_m"]["gm"]["verdict"] == "PASS"
    ad_gm = gates["ad_medium_int8"]["gm"]
    ad_ok = ad_gm.get("m2", {}).get("holds", False) and all(x["holds"] for x in ad_gm.get("m3", {}).values()) \
        if "m3" in ad_gm else False
    hk = h_k(res)
    if kws_gm and hk["G_V"] == "SUPPORTED" and ad_ok:
        attribution = "VALIDATED"
    elif kws_gm:
        attribution = "PARTIALLY_VALIDATED"
    else:
        attribution = "INVALID"
    att_ok = attribution in ("VALIDATED", "PARTIALLY_VALIDATED")
    ha = h_a(res, att_ok)
    compute = "INSUFFICIENT_EVIDENCE" if not att_ok else (
        "RESIDUAL_REDUCED" if ha["verdict"] == "H_A1_SUPPORTED" else "RESIDUAL_UNCHANGED")
    ho = {m: h_o(res, m) for m in models}
    vs = [v["verdict"] for v in ho.values()]
    serial = "SCHEDULE_EFFECT_OBSERVED" if "SCHEDULE_EFFECT_OBSERVED" in vs else (
        "NO_SIGNIFICANT_EFFECT" if all(v == "NO_SIGNIFICANT_EFFECT" for v in vs) else "INSUFFICIENT_EVIDENCE")
    vela = {}
    for m in models:
        vg = vela_groups(vela_dir, m, tflite_groups(man[key(m, "B0")]))
        g_ratio = {}
        for g, c in (("G_V", "B2"), ("G_0", "B3"), ("G_R", "B4")):
            npu, rng = val(res[key(m, c)], 1, 35)
            v = vg["groups"][g]["op_cycles"]
            r = npu / v if npu else None
            g_ratio[g] = dict(ratio=r, cls=vela_cls_noise(npu, rng, v) if r else None, npu=npu, npu_range=rng, vela=v)
        n0, _ = val(res[key(m, "B0")], 1, 35)
        n1, _ = val(res[key(m, "B1")], 1, 35)
        vela[m] = dict(vela=vg, groups=g_ratio, official_denominator="cycles_total (sum of per-layer Op Cycles)",
                       orig_over_total=n0 / vg["cycles_total"] if n0 else None,
                       serial_over_total=n1 / vg["cycles_total"] if n1 else None,
                       orig_over_npu_term=n0 / vg["cycles_npu"] if n0 else None,
                       serial_over_npu_term=n1 / vg["cycles_npu"] if n1 else None)
    if not att_ok or any(g["cls"] in (None, "INSUFFICIENT_EVIDENCE") for v in vela.values() for g in v["groups"].values()):
        vf = "INSUFFICIENT_EVIDENCE"
    else:
        closer = all(v["orig_over_total"] and v["serial_over_total"] and
                     abs(math.log(v["serial_over_total"])) < abs(math.log(v["orig_over_total"])) for v in vela.values())
        agree = all(g["cls"] == "AGREE" for v in vela.values() for g in v["groups"].values())
        vf = "GROUP_FIDELITY_IMPROVED" if closer and agree else "GROUP_DISCREPANCY_REMAINS"
    gates_ok = all(g["g1"]["verdict"] == "PASS" for g in gates.values()) and all(gs.values()) and kws_gm
    sts = [r["status"] for r in res.values()]
    if not gates_ok or any(s in STOP for s in sts):
        meas = "MEASUREMENT_INVALID"
    elif all(s == "VALID" for s in sts):
        meas = "VALID"
    else:
        meas = "PARTIAL_VALID"
    repro = {m: "INSUFFICIENT_EVIDENCE" if res[key(m, "B0")]["status"] == "UNMEASURED" else
             ("REPRODUCED" if gates[m]["g1"]["verdict"] == "PASS" else "NOT_REPRODUCED") for m in models}
    kg = gates["kws_micronet_m"]["gm"]
    mask = "INSUFFICIENT_EVIDENCE" if "m2" not in kg else ("FUNCTIONAL" if kg["m2"]["holds"] else "NOT_FUNCTIONAL")
    part = {}
    for m in models:
        g = gates[m]["gm"]
        part[m] = "INSUFFICIENT_EVIDENCE" if "m3" not in g else (
            "CONSISTENT" if all(x["holds"] for x in g["m3"].values()) else "INCONSISTENT")
    ind = "INSUFFICIENT_EVIDENCE" if "INSUFFICIENT_EVIDENCE" in (hk["G_0"], hk["G_V"]) else (
        "AGREES" if hk["G_0"] == hk["G_V"] == "SUPPORTED" else "DISAGREES")
    exact = []
    for m in models:
        w, _ = val(res[key(m, "B1")], 1, 48)
        ps = [val(res[key(m, c)], 1, 48)[0] for c in GROUP_COND]
        exact.append(None if w is None or None in ps else sum(ps) == w)
    temporal = "INSUFFICIENT_EVIDENCE" if ind == "INSUFFICIENT_EVIDENCE" or None in exact else (
        "VALIDATED_FOR_KERNEL_UNITS" if ind == "AGREES" and all(exact) else "NOT_VALIDATED")
    return dict(contract="evidence/stage6ex3/contract.md + amendment_b.md",
                ta="TA profile 1; EXT RLATENCY 500; image f0baf8c (bram 9b1844a3), placement 0",
                results=res, gates=gates, gs=gs,
                hypotheses=dict(h_s={m: h_s(res, m) for m in models},
                                h_p={m: {c: partition(res, m, c) for c in (35, 48, 51, 64, 80)} for m in models},
                                h_k=hk, h_a=ha, h_o=ho),
                vela=vela,
                mac_partition_exact=dict(zip(models, exact)),
                verdicts=dict(measurement=meas, baseline_reproducibility=repro, pmu_mask_functionality=mask,
                              group_partition_consistency=part, independent_reference_agreement=ind,
                              temporal_attribution_validity=temporal, group_attribution=attribution,
                              compute_explanation=compute, serialization=serial, vela_fidelity=vf))


def main(argv: list) -> int:
    if len(argv) < 7:
        print(__doc__)
        return 2
    root = dict(x.split("=", 1) for x in argv[2].split(",")) if "=" in argv[2] else pathlib.Path(argv[2])
    cmd, wl, m7, caps_ref = argv[1], pathlib.Path(argv[3]), pathlib.Path(argv[4]), json.loads(pathlib.Path(argv[5]).read_text())
    if cmd == "boot-check":
        r = config_result(root, wl, m7, caps_ref, argv[6])
        print(json.dumps(dict(key=argv[6], status=r["status"], reasons=r["reasons"]), indent=1))
        return 1 if r["status"] in STOP or (not argv[6].endswith("B0") and r["status"] != "VALID") else 0
    if cmd == "gate-g1":
        model = argv[6]
        r = g1(config_result(root, wl, m7, caps_ref, key(model, "B0")), m7_ref(m7, model))
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    if cmd == "gate-gm":
        model = argv[6]
        res = {key(model, c): config_result(root, wl, m7, caps_ref, key(model, c)) for c in ("B1", "B2", "B3", "B4")}
        r = gm(res, model)
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge" and len(argv) == 8:
        out = pathlib.Path(argv[7])
        out.mkdir(parents=True, exist_ok=True)
        s = judge(root, wl, m7, caps_ref, argv[6])
        (out / "stage6ex3_summary.json").write_text(json.dumps(s, indent=1, sort_keys=True, default=str) + "\n")
        print(json.dumps(s["verdicts"]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
