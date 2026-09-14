"""H13 analysis -- contract: docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md (metrics, thresholds,
outcome sets and the H1-C predictions are copied from there verbatim and must not be edited after data exists).

Reads h13/results.jsonl (copied from the server). Gates G1-G6 per arm/cell; every refusal carries a rule id.
Outputs h13_results.json (per experiment) and prints a summary. No prose is generated here.
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "x4"))
from x4_analyze import frozen_counters  # noqa: E402  (frozen R1/canonical counters for the existing cells)

RULE_ARTIFACT = "RULE_H13_ARTIFACT"
RULE_BASE_MISMATCH = "RULE_H13_BASE_MISMATCH"
RULE_REPS_DIFFER = "RULE_H13_REPS_DIFFER"
RULE_TA_HEADER = "RULE_H13_TA_HEADER"
RULE_RUN = "RULE_H13_RUN"
RULE_OUTPUT_MISMATCH = "RULE_H13_OUTPUT_MISMATCH"
RULES = (RULE_ARTIFACT, RULE_BASE_MISMATCH, RULE_REPS_DIFFER, RULE_TA_HEADER, RULE_RUN, RULE_OUTPUT_MISMATCH)

KEYS = ("npu_total_cycles", "npu_active_cycles", "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats",
        "axi0_rd_beats", "axi0_wr_beats", "axi1_rd_beats")
REPS = 3
# H1-C(a) predictions fixed in the plan (section 3a) before measurement
PRED = {256: {"M1": (52757, 89229), "M2": (49086, 89086)}, 512: {"M1": (45415, 77943), "M2": (43086, 78086)},
        1024: {"M1": (40529, 72372), "M2": (38586, 72086)}, 2048: {"M1": (43586, 78086), "M2": (42086, 78086)}}
TOL_M1, TOL_M2 = 0.05, 0.02
WORD = {"ethos-u55": 8, "ethos-u65": 16, "ethos-u85": 16}


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def refusal_rule(exc):
    return getattr(exc, "rule", None)


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def group(records):
    """(cell_id, arm) -> {exp, runs, verify, defines, is_base, artifact}"""
    g = {}
    for r in records:
        if "measurement" not in r:
            continue
        a = g.setdefault((r["cell_id"], r["arm"]), {"exp": r["experiment"], "runs": [], "defines": r["defines"],
                                                    "is_base": r["is_base"], "artifact": r["artifact"], "verify": None,
                                                    "header_ok": r.get("header_matches_request")})
        a["runs"].append(r)
        if r.get("verify"):
            a["verify"] = r["verify"]
    return g


def vec(m):
    return tuple(m.get(k) for k in KEYS)


def gate_arm(key, a):
    """G5, G3, G4, G1 for one arm. Returns the (single) counter dict."""
    if len(a["runs"]) < REPS or any(r["status"] != "SUCCESS" for r in a["runs"]):
        raise Refusal(RULE_RUN, "%s/%s: %d runs, statuses %s" % (key[0], key[1], len(a["runs"]), [r["status"] for r in a["runs"]]))
    vs = {vec(r["measurement"]) for r in a["runs"]}
    if len(vs) != 1:
        raise Refusal(RULE_REPS_DIFFER, "%s/%s: %s" % (key[0], key[1], vs))
    if not a["header_ok"]:
        raise Refusal(RULE_TA_HEADER, "%s/%s: generated header != request" % key)
    art = a["artifact"]
    if art.get("frozen_vela_sha256") and (art["vela_sha256"] != art["frozen_vela_sha256"] or art["cc_body_sha256"] != art["frozen_cc_body_sha256"]):
        raise Refusal(RULE_ARTIFACT, "%s/%s: vela/cc-body sha != frozen" % key)
    return a["runs"][0]["measurement"]


def gate_cell(cell, arms, frozen):
    """G2 (base reproduces frozen counters), G1 for synthetic cells (identical artifact across arms),
    G6 (verify dumps identical across arms). Returns {arm: counters} for the arms that passed, plus notes."""
    ok, notes = {}, []
    for (cid, arm), a in arms.items():
        try:
            ok[arm] = gate_arm((cid, arm), a)
        except Refusal as e:
            notes.append({"arm": arm, "rule": e.rule, "msg": str(e)})
    base = [arm for (cid, arm), a in arms.items() if a["is_base"] and arm in ok]
    if cell in frozen:
        if not base:
            raise Refusal(RULE_BASE_MISMATCH, "%s: no passing base arm" % cell)
        exp = frozen[cell]
        got = ok[base[0]]
        if any(got.get(k) != v for k, v in exp.items()):
            raise Refusal(RULE_BASE_MISMATCH, "%s: base %s != frozen %s" % (cell, got, exp))
    else:
        shas = {a["artifact"]["vela_sha256"] for (cid, arm), a in arms.items() if arm in ok}
        if len(shas) > 1:
            raise Refusal(RULE_ARTIFACT, "%s: synthetic cell has %d distinct vela artifacts" % (cell, len(shas)))
    dumps = {}
    for (cid, arm), a in arms.items():
        v = a.get("verify") or {}
        if arm in ok and v.get("status") == "SUCCESS" and v.get("dump_sha256"):
            dumps[arm] = v["dump_sha256"]
            if v.get("measurement") != a["runs"][0]["measurement"]:
                notes.append({"arm": arm, "note": "INSTRUMENTATION_DEVIATION", "verify_pmu": v.get("measurement")})
        elif arm in ok:
            notes.append({"arm": arm, "note": "OUTPUT_NOT_VERIFIED", "verify": {k: v.get(k) for k in ("build_ok", "status", "stage")}})
    if len(set(dumps.values())) > 1:
        raise Refusal(RULE_OUTPUT_MISMATCH, "%s: output dumps differ across arms %s" % (cell, dumps))
    return ok, notes, dumps


def by_cell(g):
    cells = {}
    for (cid, arm), a in g.items():
        cells.setdefault(cid, {})[(cid, arm)] = a
    return cells


def mac_of(cell):
    return int(cell.split("ethos-u")[1].split("-")[1].split("_")[0])


def npu_of(cell):
    return "ethos-u" + cell.split("ethos-u")[1][:2]


def tot(c, arm):
    return c[arm]["npu_total_cycles"]


# ---------------------------------------------------------------- experiments
def h1a(cells_ok):
    out = {}
    for cell, c in cells_ok.items():
        if not cell.startswith("rnnoise") or not {"r0_w250", "r1000_w250", "r500_w0", "r500_w500", "r500_w250"} <= set(c):
            continue
        k_r = (tot(c, "r1000_w250") - tot(c, "r0_w250")) / 1000.0
        k_w = (tot(c, "r500_w500") - tot(c, "r500_w0")) / 500.0
        if k_w <= 0.2 * k_r:
            o = "READ_DOMINANT"
        elif k_r <= 0.2 * k_w:
            o = "WRITE_DOMINANT"
        else:
            o = "MIXED"
        pred00 = tot(c, "r0_w250") - (tot(c, "r500_w250") - tot(c, "r500_w0"))
        add = None
        if "r0_w0" in c:
            add = "ADDITIVE" if abs(pred00 - tot(c, "r0_w0")) <= 0.05 * tot(c, "r0_w0") else "NON_ADDITIVE"
        out[mac_of(cell)] = {"k_r": round(k_r, 3), "k_w": round(k_w, 3), "outcome": o, "additivity": add,
                             "C00_pred": pred00, "C00_obs": c.get("r0_w0", {}).get("npu_total_cycles"),
                             "read_sweep": {r: c["r%d_w250" % r]["npu_total_cycles"] for r in (0, 125, 250, 500, 1000) if "r%d_w250" % r in c},
                             "write_sweep": {w: c["r500_w%d" % w]["npu_total_cycles"] for w in (0, 125, 250, 500) if "r500_w%d" % w in c}}
    if len(out) >= 2:
        ks = [v["k_r"] for v in out.values()]
        out["cross_mac"] = "SENSITIVITY_SIMILAR_ACROSS_MAC" if max(ks) / min(ks) <= 1.15 else "SENSITIVITY_DIFFERS_ACROSS_MAC"
    return out


def h1b(cells_ok):
    out = {}
    for cell, c in cells_ok.items():
        if not cell.startswith("rnnoise"):
            continue
        mac = mac_of(cell); wb = 125 if mac == 256 else 250
        s = {}
        for m in (1, 4, 16, 63, 64, 0):
            a, b = "maxr%d_r250_w%d" % (m, wb), "maxr%d_r1000_w%d" % (m, wb)
            if a in c and b in c:
                s[m] = (tot(c, b) - tot(c, a)) / 750.0
        if not s or 1 not in s:
            continue
        order = [m for m in (1, 4, 16, 63, 0) if m in s]
        vals = [s[m] for m in order]
        mono = all(x >= y for x, y in zip(vals, vals[1:]))
        top = s.get(63, s.get(0))
        if mono and top <= 0.8 * s[1]:
            o = "CONCURRENCY_REDUCES_SENSITIVITY"
        elif all(abs(v - s[1]) <= 0.05 * s[1] for v in s.values()):
            o = "CONCURRENCY_NO_EFFECT_IN_RANGE"
        else:
            o = "PARTIAL_OR_NON_MONOTONE"
        m64 = None
        if 64 in s and 0 in s:
            same = all(tot(c, "maxr64_r%d_w%d" % (r, wb)) == tot(c, "maxr0_r%d_w%d" % (r, wb)) for r in (250, 1000))
            m64 = "MAXR64_IS_UNLIMITED" if same else "MAXR64_DISTINCT"
        note = "NPU_OUTSTANDING_LIMIT_LE_4_SUSPECTED" if (4 in s and 16 in s and s[4] == s[16] and s[1] != s[4]) else None
        out[mac] = {"s": {m: round(v, 3) for m, v in s.items()}, "outcome": o, "maxr64": m64, "note": note,
                    "cycles": {arm: c[arm]["npu_total_cycles"] for arm in c if arm.startswith("maxr")}}
    return out


def h1c_a(cells_ok):
    out = {}
    for cell, c in cells_ok.items():
        if not cell.startswith("rnnoise") or not {"r375_w187", "r750_w375"} <= set(c):
            continue
        mac = mac_of(cell); obs = (tot(c, "r375_w187"), tot(c, "r750_w375"))
        m1 = all(abs(o - p) <= TOL_M1 * p for o, p in zip(obs, PRED[mac]["M1"]))
        m2 = all(abs(o - p) <= TOL_M2 * p for o, p in zip(obs, PRED[mac]["M2"]))
        out[mac] = {"observed": obs, "M1_pred": PRED[mac]["M1"], "M2_pred": PRED[mac]["M2"], "M1_pass": m1, "M2_pass": m2,
                    "outcome": "LINEAR_ADEQUATE" if m1 else ("PIECEWISE_ADEQUATE" if m2 else "NEITHER_MODEL_PREDICTS")}
    return out


def h1c_b(cells_ok):
    out = {}
    for cell, c in cells_ok.items():
        if not (cell.startswith("kws") or cell.startswith("ad_")) or "u85" not in cell or not {"r0_w250", "r1000_w250"} <= set(c):
            continue
        rho = tot(c, "r1000_w250") / float(tot(c, "r0_w250"))
        out[cell] = {"rho": round(rho, 4), "k_r": round((tot(c, "r1000_w250") - tot(c, "r0_w250")) / 1000.0, 3),
                     "outcome": "LATENCY_SENSITIVE" if rho >= 1.10 else "ROBUST_IN_RANGE",
                     "read_sweep": {r: c["r%d_w250" % r]["npu_total_cycles"] for r in (0, 250, 500, 1000) if "r%d_w250" % r in c}}
    if out:
        os_ = {v["outcome"] for v in out.values()}
        out["generalisation"] = ("GENERALISES_TO_KWS_AD" if os_ == {"LATENCY_SENSITIVE"} else
                                 "RNNOISE_SPECIFIC" if os_ == {"ROBUST_IN_RANGE"} else "PARTIAL")
    return out


def h2a(cells_ok, defines_of):
    out = {}
    for cell, c in cells_ok.items():
        if not cell.startswith("wav2letter"):
            continue
        mac = mac_of(cell); caps = (1875, 3750, 7500, 0) if mac == 512 else (1172, 2344, 4688, 0)
        base_lat = (500, 250) if mac == 512 else (250, 125)
        def arm(cap, lat):
            return "bw%d_r%d_w%d" % (cap, lat[0], lat[1])
        rows = {}
        for lat in (base_lat, (0, 0)):
            for cap in caps:
                a = arm(cap, lat)
                if a in c:
                    m = c[a]; d = defines_of[(cell, a)]
                    nominal = (cap * 16.0 / (d["EXT_PULSE_ON"] + d["EXT_PULSE_OFF"])) if cap else None
                    achieved = (m["ext_rd_beats"] + m["ext_wr_beats"]) * 16.0 / m["npu_total_cycles"]
                    rows[a] = {"cycles": m["npu_total_cycles"], "ext_beats": m["ext_rd_beats"] + m["ext_wr_beats"],
                               "achieved_B_per_cyc": round(achieved, 4), "nominal_cap_B_per_cyc": round(nominal, 4) if nominal else None}
        b = rows.get(arm(caps[1], base_lat))
        if not b:
            continue
        C1 = b["cycles"]; relaxed = [rows[arm(cp, base_lat)]["cycles"] for cp in (caps[2], caps[3]) if arm(cp, base_lat) in rows]
        lowered = rows.get(arm(caps[0], base_lat), {}).get("cycles")
        within = all(abs(rows[arm(cp, base_lat)]["cycles"] - C1) <= 0.05 * C1 for cp in caps if arm(cp, base_lat) in rows)
        binding = b["achieved_B_per_cyc"] >= 0.9 * b["nominal_cap_B_per_cyc"]
        if relaxed and min(relaxed) <= 0.90 * C1:
            o = "EXT_CAP_CONSTRAINED"
        elif within and not binding:
            o = "EXT_CAP_NOT_BINDING_IN_RANGE"
        elif within and binding:
            o = "CAP_RAISE_INEFFECTIVE_NOT_EVIDENCE"
        elif lowered and lowered >= 1.10 * C1:
            o = "CAP_LOWERING_SLOWS_ONLY"
        else:
            o = "MIXED_BELOW_THRESHOLDS"
        inter = None
        a2, a1, z2, z1 = arm(caps[2], base_lat), arm(caps[1], base_lat), arm(caps[2], (0, 0)), arm(caps[1], (0, 0))
        if all(x in rows for x in (a2, a1, z2, z1)):
            eff_base = 1 - rows[a2]["cycles"] / float(rows[a1]["cycles"]); eff_zero = 1 - rows[z2]["cycles"] / float(rows[z1]["cycles"])
            inter = "LATENCY_CAP_INTERACTION" if abs(eff_base - eff_zero) >= 0.05 else "NO_INTERACTION_DETECTED"
        out[mac] = {"rows": rows, "outcome": o, "interaction": inter}
    return out


def sramcap(cells_ok):
    out = {}
    for cell, c in cells_ok.items():
        if "sbw4000" not in c:
            continue
        w = WORD[npu_of(cell)]
        def sram_rate(m):
            beats = (m.get("sram_rd_beats") or m.get("axi0_rd_beats") or 0) + (m.get("sram_wr_beats") or m.get("axi0_wr_beats") or 0)
            return round(beats * w / float(m["npu_total_cycles"]), 4)
        rows = {a: {"cycles": c[a]["npu_total_cycles"], "sram_B_per_cyc": sram_rate(c[a])} for a in c if a.startswith("sbw")}
        C1 = rows["sbw4000"]["cycles"]
        raised = [rows[a]["cycles"] for a in ("sbw8000", "sbw0") if a in rows]
        if raised and min(raised) <= 0.90 * C1:
            o = "SRAM_CAP_CONSTRAINED_AT_DEFAULT"
        elif "sbw2000" in rows and rows["sbw2000"]["cycles"] >= 1.10 * C1:
            o = "SRAM_CAP_LOWERING_SLOWS"
        else:
            o = "SRAM_CAP_NOT_BINDING_IN_RANGE"
        out[cell] = {"rows": rows, "outcome": o}
    return out


def h3(cells_ok, manifest):
    """r = C_512 / C_256 per model per condition; outcomes per plan section 7."""
    meta = {m["model"]: m for m in manifest}
    r = {}  # (model, condition) -> ratio
    cyc = {}
    for cell, c in cells_ok.items():
        if not cell.startswith("h3_"):
            continue
        model = cell.split("__")[0]; mac = mac_of(cell); ctrl = cell.endswith("__syscfgMid")
        for arm, m in c.items():
            cond = ("syscfgMid" if ctrl else arm)
            cyc[(model, cond, mac)] = m["npu_total_cycles"]
    for (model, cond, mac), v in cyc.items():
        if mac == 256 and (model, cond, 512) in cyc:
            r[(model, cond)] = cyc[(model, cond, 512)] / float(v)
        if mac == 256 and cond == "syscfgMid" and (model, "base", 512) in cyc:      # 512 already uses Mid_512
            r[(model, "syscfgMid")] = cyc[(model, "base", 512)] / float(v)
    def med(xs):
        xs = sorted(xs); n = len(xs)
        return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)
    out = {"ratios": {"%s|%s" % k: round(v, 4) for k, v in r.items()}, "cycles": {"%s|%s|%d" % k: v for k, v in cyc.items()}}
    outcomes = []
    spread = {}
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        for area in (36, 64, 256):
            for cond in ("base", "relaxed"):
                xs = [v for (mo, co), v in r.items() if co == cond and meta[mo]["op"] == op and meta[mo]["area"] == area]
                if len(xs) >= 2:
                    spread[(op, area, cond)] = (round(max(xs) - min(xs), 4), round(med(xs), 4), len(xs))
                    if cond == "base" and max(xs) - min(xs) >= 0.10:
                        outcomes.append("SHAPE_EFFECT:%s:%d" % (op, area))
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        meds = [spread.get((op, a, "base"), (None, None, 0))[1] for a in (36, 64, 256)]
        if all(m is not None for m in meds) and meds[0] > meds[1] > meds[2] and meds[2] <= meds[0] - 0.10:
            outcomes.append("AREA_EFFECT:%s" % op)
    m36 = [spread.get((op, 36, "base"), (None, None, 0))[1] for op in ("conv1x1", "conv3x3", "dw3x3")]
    if all(m is not None for m in m36) and max(m36) - min(m36) >= 0.10:
        outcomes.append("TYPE_DEPENDENT")
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        b, rl = spread.get((op, 36, "base")), spread.get((op, 36, "relaxed"))
        if b and rl and b[0] > 0 and rl[0] < 0.5 * b[0]:
            outcomes.append("MEMORY_SHAPE_INTERACTION:%s" % op)
    out["spread"] = {"%s|%d|%s" % k: v for k, v in spread.items()}
    out["outcomes"] = outcomes
    return out


def analyze(records, manifest=None, frozen=None):
    frozen = frozen if frozen is not None else frozen_counters()
    g = group(records); cells = by_cell(g)
    cells_ok, gates, dumps = {}, {}, {}
    for cell, arms in cells.items():
        try:
            ok, notes, d = gate_cell(cell, arms, frozen)
            cells_ok[cell] = ok; gates[cell] = {"passed": sorted(ok), "notes": notes}; dumps[cell] = d
        except Refusal as e:
            gates[cell] = {"passed": [], "refused": e.rule, "msg": str(e)}
    defines_of = {k: a["defines"] for k, a in g.items()}
    return {"gates": gates, "H1A": h1a(cells_ok), "H1B": h1b(cells_ok), "H1Ca": h1c_a(cells_ok), "H1Cb": h1c_b(cells_ok),
            "H2A": h2a(cells_ok, defines_of), "SRAMCAP": sramcap(cells_ok), "H3": h3(cells_ok, manifest or [])}


def main():
    path = HERE / "results.jsonl"
    man = HERE / "h3_manifest.json"
    res = analyze(load(path), json.load(open(man)) if man.exists() else [])
    json.dump(res, open(HERE / "h13_results.json", "w"), indent=1, default=str)
    for cell, gt in res["gates"].items():
        if gt.get("refused"):
            print("REFUSED", cell, gt["refused"])
        for n in gt.get("notes", []):
            if n.get("rule") or n.get("note") == "INSTRUMENTATION_DEVIATION":
                print("NOTE", cell, n)
    for k in ("H1A", "H1B", "H1Ca", "H1Cb", "H2A", "SRAMCAP"):
        for cell, v in res[k].items():
            print(k, cell, v.get("outcome", v) if isinstance(v, dict) else v)
    print("H3", res["H3"]["outcomes"])


if __name__ == "__main__":
    main()
