"""H3-R analysis -- contract: docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md A8 (manager GO:
docs/superpowers/plans/2026-09-15-h3r-verification-GO.md). Thresholds and outcome sets are copied from there and
must not be edited after data exists.

Reads h3r/results.jsonl (copied from the server) and h3r/h3r_manifest.json (G1' result per model).
Gates per arm / cell / model, every refusal carries a rule id. Judgements are computed twice, once on NPU TOTAL
(primary, links to H3) and once on NPU ACTIVE (preregistered parallel); disagreement is tagged METRIC_DEPENDENT.
Writes h3r_results.json. No prose is generated here.
"""
import hashlib, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
H13 = HERE.parent / "h13"

RULE_RUN = "RULE_H3R_RUN"                          # 3 SUCCESS runs, required counters present (None is not a value)
RULE_REPS_DIFFER = "RULE_H3R_REPS_DIFFER"          # counter vectors identical across the 3 reps
RULE_TA_CONFIG = "RULE_H3R_TA_CONFIG"              # header == request (16), CMakeCache read-back present and == request, equalized applied == across MACs
RULE_ARTIFACT = "RULE_H3R_ARTIFACT"                # G1: same model x MAC -> identical Vela artifact / cc body across TA arms
RULE_G1PRIME = "RULE_H3R_G1PRIME"                  # G1': derived model non-shape fields == base model (from check_g1prime)
RULE_OUTPUT_MISMATCH = "RULE_H3R_OUTPUT_MISMATCH"  # same model: output bytes identical across MAC and TA arms
RULE_PRESERVATION = "RULE_H3R_PRESERVATION"        # existing H13 evidence digests unchanged
RULES = (RULE_RUN, RULE_REPS_DIFFER, RULE_TA_CONFIG, RULE_ARTIFACT, RULE_G1PRIME, RULE_OUTPUT_MISMATCH, RULE_PRESERVATION)

REPS = 3
REQUIRED = ("npu_total_cycles", "npu_active_cycles", "npu_idle_cycles",
            "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats")
TA_KEYS = tuple("%s_%s" % (s, k) for s in ("SRAM", "EXT")
                for k in ("MAXR", "MAXW", "MAXRW", "RLATENCY", "WLATENCY", "PULSE_ON", "PULSE_OFF", "BWCAP"))
# driver register masks: core-platform drivers/timing_adapter/src/timing_adapter.c (ta_set_*: reg = val & MASK)
TA_MASK = {"MAXR": 0x3F, "MAXW": 0x3F, "MAXRW": 0x3F, "RLATENCY": 0xFFF, "WLATENCY": 0xFFF,
           "PULSE_ON": 0xFFFF, "PULSE_OFF": 0xFFFF, "BWCAP": 0xFFFF}
CONDS = ("base", "equalized", "bridge_legacy_relaxed")
OPS = ("conv1x1", "conv3x3", "dw3x3")
METRICS = {"TOTAL": "npu_total_cycles", "ACTIVE": "npu_active_cycles"}
SHAPE_T, MSI_FACTOR, TYPE_T = 0.10, 0.5, 0.10   # plan A8 / section 7, fixed before measurement; judged on the 4-decimal values that are reported

# existing evidence that H3-R must leave untouched (sha256 at the A8 commit)
PRESERVED = {
    "h13/results.jsonl": "d880c79e06dd1059ef91d8424efabefe6fa46ca3760598853affe0f04a3d3480",
    "h13/h13_results.json": "ec4319a7288ec50fdece3cebe9b462f54c40aebf0c8eff1958d9baa1c193eed1",
    "h13/h3_manifest.json": "80ece83337ab97bad8c4ae976045356b815797a7f906cc3ff53695dfc7414c05",
    "h13/h3_blocks.csv": "910d47b49cd5f0d756e5c439a5a6ec9323c3fb3035a0d3b4e451278f86f92e2e",
}


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def refusal_rule(exc):
    return getattr(exc, "rule", None)


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def applied(values):
    """The 16 managed register values after the driver masks (requested/header value -> applied value)."""
    return {k: (v & TA_MASK[k.split("_", 1)[1]]) for k, v in values.items() if k in TA_KEYS}


def applied_all(header):
    """Every field the generated header carries, masked where the driver masks it.

    The generated timing_adapter_settings.h holds more than the 16 values the campaign sets (PERFCTRL, PERFCNT,
    MODE, HISTBIN, HISTCNT per side). equalized requires the two MACs to agree on ALL of them, not only on the 16,
    so an unmanaged field that happens to differ per MAC cannot hide inside a passing gate."""
    out = {}
    for k, v in header.items():
        suffix = k.split("_", 1)[1] if "_" in k else k
        out[k] = (v & TA_MASK[suffix]) if suffix in TA_MASK else v
    return out


def group(records):
    g = {}
    for r in records:
        if "measurement" not in r:
            continue
        a = g.setdefault((r["cell_id"], r["arm"]), {"runs": [], "defines": r["defines"], "artifact": r["artifact"],
                                                    "verify": None, "header": r.get("ta_header") or {},
                                                    "header_ok": r.get("header_matches_request"), "cache": r.get("ta_cache")})
        a["runs"].append(r)
        if r.get("verify"):
            a["verify"] = r["verify"]
    return g


def vec(m):
    return tuple(m.get(k) for k in REQUIRED)


def gate_arm(key, a):
    """RUN, REPS, TA header/cache for one arm. Returns the (single) counter dict."""
    if len(a["runs"]) < REPS or any(r["status"] != "SUCCESS" for r in a["runs"]):
        raise Refusal(RULE_RUN, "%s/%s: %d runs, statuses %s" % (key[0], key[1], len(a["runs"]), [r["status"] for r in a["runs"]]))
    for r in a["runs"]:
        missing = [k for k in REQUIRED if r["measurement"].get(k) is None]
        if missing:
            raise Refusal(RULE_RUN, "%s/%s rep %s: required counters missing %s" % (key[0], key[1], r.get("rep"), missing))
    if len({vec(r["measurement"]) for r in a["runs"]}) != 1:
        raise Refusal(RULE_REPS_DIFFER, "%s/%s: %s" % (key[0], key[1], [vec(r["measurement"]) for r in a["runs"]]))
    req = a["defines"]
    if not a["header_ok"] or any(a["header"].get(k) != req.get(k) for k in TA_KEYS):
        raise Refusal(RULE_TA_CONFIG, "%s/%s: generated header != request" % key)
    if not a["cache"] or any(a["cache"].get(k) != req.get(k) for k in TA_KEYS):
        raise Refusal(RULE_TA_CONFIG, "%s/%s: CMakeCache read-back absent or != request" % key)
    return a["runs"][0]["measurement"]


def parse_output_dump(txt):
    i = txt.find("output tensors post inference")
    if i < 0:
        return None, None
    j = txt.find("Profile for Inference", i)
    data = [int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", txt[i:j if j > 0 else None])]
    k = txt.find("Model OUTPUT tensors:")
    expected = None
    if k >= 0:
        end = txt.find("Activation buffer", k)
        expected = sum(int(x) for x in re.findall(r"tensor occupies (\d+) bytes", txt[k:end if end > 0 else None]))
    return data, expected


def output_bytes(v, verify_dir):
    p = v.get("uart_file")
    local = verify_dir / Path(p).name if p else None
    if local is None or not local.exists():
        return v["dump_sha256"]
    data, expected = parse_output_dump(open(local, errors="replace").read())
    if data is None or not data or (expected is not None and len(data) != expected):
        return "INCOMPLETE_DUMP"
    return data


def mac_of(cell):
    return int(cell.split("ethos-u85-")[1].split("_")[0])


def model_of(cell):
    return cell.split("__")[0]


def analyze(records, manifest, verify_dir=None, preserved=None):
    """manifest: list of {model, op, H, W, g1prime_pass}. preserved: {relpath: sha256 observed} or None to compute."""
    verify_dir = verify_dir if verify_dir is not None else HERE / "verify"
    meta = {m["model"]: m for m in manifest}
    g = group(records)
    gates = {"arms": {}, "cells": {}, "models": {}}
    ok = {}                                   # (cell, arm) -> measurement
    for key, a in g.items():
        try:
            ok[key] = gate_arm(key, a); gates["arms"]["%s|%s" % key] = "PASS"
        except Refusal as e:
            gates["arms"]["%s|%s" % key] = {"refused": e.rule, "msg": str(e)}
    # G1 per cell: identical Vela artifact and cc body across passing arms
    by_cell = {}
    for (cell, arm) in ok:
        by_cell.setdefault(cell, []).append(arm)
    for cell, arms in by_cell.items():
        shas = {(g[(cell, a)]["artifact"]["vela_sha256"], g[(cell, a)]["artifact"]["cc_body_sha256"]) for a in arms}
        if len(shas) > 1:
            gates["cells"][cell] = {"refused": RULE_ARTIFACT, "msg": "%s: %d distinct vela/cc artifacts across arms %s" % (cell, len(shas), sorted(arms))}
            for a in arms:
                ok.pop((cell, a), None)
        else:
            gates["cells"][cell] = "PASS"
    # per model: G1', output identity across all passing arms of both MACs, equalized applied-value identity
    by_model = {}
    for (cell, arm) in ok:
        by_model.setdefault(model_of(cell), []).append((cell, arm))
    for model, keys in sorted(by_model.items()):
        notes = []
        try:
            m = meta.get(model)
            if m is None or m.get("g1prime_pass") is not True:
                raise Refusal(RULE_G1PRIME, "%s: G1' not passed in manifest (%s)" % (model, None if m is None else m.get("g1prime_pass")))
            dumps = {}
            for key in keys:
                v = g[key].get("verify") or {}
                if v.get("status") == "SUCCESS" and v.get("dump_sha256"):
                    dumps[key] = output_bytes(v, verify_dir)
                    if v.get("measurement") != g[key]["runs"][0]["measurement"]:
                        notes.append({"arm": "%s|%s" % key, "note": "INSTRUMENTATION_DEVIATION"})
                else:
                    raise Refusal(RULE_OUTPUT_MISMATCH, "%s/%s: no verify dump (%s)" % (key[0], key[1], {k: v.get(k) for k in ("build_ok", "status", "stage")}))
            bad = [k for k, d in dumps.items() if d == "INCOMPLETE_DUMP"]
            if bad:
                raise Refusal(RULE_OUTPUT_MISMATCH, "%s: incomplete output dump in %s" % (model, ["%s|%s" % k for k in bad]))
            if len({str(d) for d in dumps.values()}) > 1:
                raise Refusal(RULE_OUTPUT_MISMATCH, "%s: output dumps differ across %s" % (model, sorted("%s|%s" % k for k in dumps)))
            eq = {mac_of(c): applied_all(g[(c, a)]["header"]) for (c, a) in keys if a == "equalized"}
            if len(eq) == 2 and eq[256] != eq[512]:
                diff = sorted(k for k in set(eq[256]) | set(eq[512]) if eq[256].get(k) != eq[512].get(k))
                raise Refusal(RULE_TA_CONFIG, "%s: equalized applied values differ across MACs: %s" % (model, diff))
            if len(eq) == 2:
                gates.setdefault("equalized_applied", {})[model] = {"fields_compared": len(eq[256]), "identical": True}
            gates["models"][model] = {"status": "PASS", "arms": sorted("%s|%s" % k for k in keys), "notes": notes}
        except Refusal as e:
            gates["models"][model] = {"refused": e.rule, "msg": str(e), "notes": notes}
            for key in keys:
                ok.pop(key, None)
    # preservation gate (existing evidence unchanged)
    pres = preserved if preserved is not None else {k: hashlib.sha256(open(HERE.parent / k, "rb").read()).hexdigest() for k in PRESERVED}
    changed = sorted(k for k, v in PRESERVED.items() if pres.get(k) != v)
    gates["preservation"] = {"refused": RULE_PRESERVATION, "changed": changed} if changed else "PASS"
    if changed:
        raise Refusal(RULE_PRESERVATION, "existing evidence changed: %s" % changed)
    cyc = {}                                  # (model, cond, mac) -> measurement
    for (cell, arm), m in ok.items():
        cyc[(model_of(cell), arm, mac_of(cell))] = m
    ta = {"%s|%s" % k: {"request": {t: a["defines"].get(t) for t in TA_KEYS}, "header": {t: a["header"].get(t) for t in TA_KEYS},
                        "applied": applied(a["header"])} for k, a in g.items()}
    out = {"gates": gates, "ta_matrix": ta,
           "cycles": {"%s|%s|%d" % k: v for k, v in cyc.items()}, "judged": {}}
    for name, key in METRICS.items():
        out["judged"][name] = judge(cyc, meta, key)
    out["judgements"] = compare_metrics(out["judged"])
    out["bridge"] = bridge(cyc, meta)
    return out


def med(xs):
    xs = sorted(xs); n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def judge(cyc, meta, key):
    """Plan section 7 formulas on one counter: r = C512/C256, spread = max r - min r per (op, cond)."""
    r = {}
    for (model, cond, mac), m in cyc.items():
        if mac == 256 and (model, cond, 512) in cyc:
            r[(model, cond)] = cyc[(model, cond, 512)][key] / float(m[key])
    spread, outcomes, values = {}, [], {}
    for op in OPS:
        for cond in CONDS:
            xs = [v for (mo, co), v in r.items() if co == cond and meta[mo]["op"] == op]
            if len(xs) >= 2:
                spread[(op, cond)] = {"spread": round(max(xs) - min(xs), 4), "median": round(med(xs), 4), "n": len(xs),
                                      "max": round(max(xs), 4), "min": round(min(xs), 4)}
                jid = "SHAPE_EFFECT:%s:%s" % (op, cond)
                values[jid] = {"value": spread[(op, cond)]["spread"], "holds": spread[(op, cond)]["spread"] >= SHAPE_T}
    for op in OPS:
        b, e = spread.get((op, "base")), spread.get((op, "equalized"))
        if b and e:
            values["MEMORY_SHAPE_INTERACTION:%s" % op] = {"value": [b["spread"], e["spread"]],
                                                          "holds": e["spread"] < MSI_FACTOR * b["spread"]}   # base spread 0 can never be halved (spread >= 0)
    for cond in ("base", "equalized"):
        ms = [spread.get((op, cond), {}).get("median") for op in OPS]
        if all(m is not None for m in ms):
            values["TYPE_DEPENDENT:%s" % cond] = {"value": ms, "holds": round(max(ms) - min(ms), 4) >= TYPE_T}
    outcomes = sorted(j for j, v in values.items() if v["holds"])
    return {"ratios": {"%s|%s" % k: round(v, 4) for k, v in r.items()}, "spread": {"%s|%s" % k: v for k, v in spread.items()},
            "values": values, "outcomes": outcomes}


def compare_metrics(judged):
    rows = []
    ids = sorted(set(judged["TOTAL"]["values"]) | set(judged["ACTIVE"]["values"]))
    for j in ids:
        t, a = judged["TOTAL"]["values"].get(j), judged["ACTIVE"]["values"].get(j)
        if t is None or a is None:
            label = "NOT_EVALUABLE"
        elif t["holds"] == a["holds"]:
            label = "HOLDS_BOTH" if t["holds"] else "FAILS_BOTH"
        else:
            label = "METRIC_DEPENDENT"
        rows.append({"judgement": j, "TOTAL_value": None if t is None else t["value"], "TOTAL_holds": None if t is None else t["holds"],
                     "ACTIVE_value": None if a is None else a["value"], "ACTIVE_holds": None if a is None else a["holds"], "label": label})
    return rows


def bridge(cyc, meta):
    """DW bridge control (descriptive, no thresholds): bridge_legacy_relaxed vs equalized per shape, both MACs, both metrics."""
    out = {}
    for model, m in meta.items():
        if m["op"] != "dw3x3":
            continue
        row = {}
        for cond in ("bridge_legacy_relaxed", "equalized"):
            for mac in (256, 512):
                mm = cyc.get((model, cond, mac))
                if mm:
                    row["%s|%d" % (cond, mac)] = {k: mm[k] for k in REQUIRED}
            if (model, cond, 256) in cyc and (model, cond, 512) in cyc:
                for name, key in METRICS.items():
                    row["r_%s|%s" % (name, cond)] = round(cyc[(model, cond, 512)][key] / float(cyc[(model, cond, 256)][key]), 4)
        for name in METRICS:
            a, b = row.get("r_%s|bridge_legacy_relaxed" % name), row.get("r_%s|equalized" % name)
            if a is not None and b is not None:
                row["delta_r_%s" % name] = round(b - a, 4)
        out[model] = row
    return out


def main():
    res = analyze(load(HERE / "results.jsonl"), json.load(open(HERE / "h3r_manifest.json")))
    json.dump(res, open(HERE / "h3r_results.json", "w"), indent=1, default=str)
    for k, v in res["gates"]["arms"].items():
        if v != "PASS":
            print("REFUSED arm", k, v["refused"])
    for k, v in res["gates"]["cells"].items():
        if v != "PASS":
            print("REFUSED cell", k, v["refused"])
    for k, v in res["gates"]["models"].items():
        if v.get("refused"):
            print("REFUSED model", k, v["refused"], v["msg"][:120])
    print("preservation", res["gates"]["preservation"])
    for name in METRICS:
        print(name, res["judged"][name]["outcomes"])
    for row in res["judgements"]:
        print("%-42s TOTAL=%-18s ACTIVE=%-18s %s" % (row["judgement"], row["TOTAL_value"], row["ACTIVE_value"], row["label"]))


if __name__ == "__main__":
    main()
