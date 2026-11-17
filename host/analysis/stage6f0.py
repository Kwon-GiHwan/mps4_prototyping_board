#!/usr/bin/env python3
"""Stage 6F-0 — seven-model compute reconstruction, runtime explainability, Vela fidelity (board-free).
Contract: evidence/stage6f0/contract.md.

  python3 stage6f0.py judge <out dir>
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6d as D  # noqa: E402

REPO = D.REPO
RES = REPO / "results"
OPS6D = RES / "fi101_stage6d/operator_levels.csv"
SUM6D = RES / "fi101_stage6d/stage6d_summary.json"
S6 = RES / "fi101_stage6/summary.json"
WHOLE = RES / "fi101_stage6/whole_model_comparison.csv"
INV = RES / "fi101_stage4/stage4_operator_inventory.csv"
X3 = RES / "fi101_stage6ex3/stage6ex3_summary.json"

MODELS = D.MODELS
PRED_6D = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED")
X3_GROUPS = {"kws_micronet_m": {"G_0": (0,), "G_V": (2, 4, 6)}, "ad_medium_int8": {"G_0": (0,), "G_V": (2, 4, 6, 8)}}
X3_COND = {"G_V": "B2", "G_0": "B3", "G_R": "B4"}
TOL_EXACT, TOL_RULE = 0.01, 0.05                 # X3 H-K
LO, HI = D.LO, D.HI                              # 6D band 0.85 / 1.05
V_FULL = 0.90
VELA_LO, VELA_HI = 0.9, 1.1
COVERED = ("DIRECT_IN_MODEL", "DIRECT_ISOLATED", "CONFIGURATION", "CLASS")
EXTRAP = ("EXTRAPOLATED", "REFUTED")
LEVELS_6F = COVERED + EXTRAP + ("UNSUPPORTED_OR_UNSTABLE",)
CRITERIA = "abcdefghij"
CANDIDATES = (  # name, Y/N for a..j, boots, excluded by the directive — contract §7
    ("X_LAT", "YYYYYYYNYY", 12, False),
    ("X_FIRST", "YYYYYYNNYY", 6, False),
    ("X_DW", "YYYYYYNNYY", 6, False),
    ("G_DF_EXT", "NYNNYYNNNY", 9, False),
    ("X3_5M", "NYYNYYYYNY", 25, False),
    ("X_BARRIER", "YNNYYYYNNN", 4, True),
)
MAX_BOOTS = 12


def fnum(s: str) -> float | None:
    return float(s) if s not in ("", None) else None


# ---- §1 X3 groups -------------------------------------------------------------------------------------------------
def group_of(model: str, op: int) -> str | None:
    if model not in X3_GROUPS:
        return None
    return next((g for g, ops in X3_GROUPS[model].items() if op in ops), "G_R")


def group_status(rows: list[dict], measured: float) -> tuple[str, float | None]:
    """rows: the group's MAC operators (6D rows). Returns (status, predicted sum)."""
    if all(r["level"] in PRED_6D for r in rows):
        p = sum(fnum(r["p"]) for r in rows)
        tol = TOL_EXACT if all(r["level"] == "CONFIGURATION_MATCHED" for r in rows) else TOL_RULE
        return ("PREDICTION_AGREES" if abs(measured - p) <= tol * p else "PREDICTION_DISAGREES"), p
    vals = [fnum(r["p"]) if fnum(r["p"]) is not None else fnum(r["p_ext"]) for r in rows]
    if any(v is None for v in vals):
        part = sum(v for v in vals if v is not None)
        return "NOT_TESTABLE", part
    p = sum(vals)
    return ("EXTRAPOLATION_CONSISTENT" if LO * measured <= p <= HI * measured else "EXTRAPOLATION_REFUTED"), p


def x3_groups(ops: list[dict], x3: dict) -> dict:
    out = {}
    for m in X3_GROUPS:
        mac_ops = [r for r in ops if r["model"] == m and int(r["n_mac"]) > 0]
        res = {}
        for g, cond in X3_COND.items():
            rows = [r for r in mac_ops if group_of(m, int(r["op"])) == g]
            k = f"x3_{m.split('_')[0]}_{cond}"
            mac = x3["results"][k]["stats"]["1"]["48"][0]
            st, p = group_status(rows, mac)
            res[g] = dict(ops=[int(r["op"]) for r in rows], mac=mac, npu=x3["results"][k]["window_npu"]["median"],
                          npu_range=x3["results"][k]["window_npu"]["range"], status=st, predicted=p,
                          p_over_m=(p / mac if p is not None else None))
        out[m] = res
    return out


# ---- §2 operator level -----------------------------------------------------------------------------------------
def level_6f(r: dict, groups: dict) -> tuple[str, str | None, str | None]:
    g = group_of(r["model"], int(r["op"]))
    gi = groups.get(r["model"], {}).get(g) if g else None
    st = gi["status"] if gi else None
    lv = r["level"]
    if st == "PREDICTION_AGREES":
        return "DIRECT_IN_MODEL", g, st
    if lv == "EXACT_VALIDATED":
        return "DIRECT_ISOLATED", g, st
    if lv == "CONFIGURATION_MATCHED":
        return "CONFIGURATION", g, st
    if lv == "CLASS_SUPPORTED":
        return "CLASS", g, st
    if lv == "EXTRAPOLATED":
        alone = gi is not None and gi["ops"] == [int(r["op"])]
        return ("REFUTED" if alone and st == "EXTRAPOLATION_REFUTED" else "EXTRAPOLATED"), g, st
    return "UNSUPPORTED_OR_UNSTABLE", g, st


def levels(ops: list[dict], groups: dict) -> list[dict]:
    out = []
    for r in ops:
        if r["level"] in ("CPU_OR_SPLIT", "AO_ELEMENTWISE"):
            continue
        lv, g, st = level_6f(r, groups)
        out.append(dict(model=r["model"], op=int(r["op"]), family=r["family"], n_mac=int(r["n_mac"]), level_6d=r["level"],
                        level_6f=lv, group=g or "", group_status=st or "", p=fnum(r["p"]), p_ext=fnum(r["p_ext"])))
    return out


# ---- §3/§4 model --------------------------------------------------------------------------------------------------
def coverage(rows: list[dict], n_model: int, m: float, groups: dict | None, partition_exact: bool) -> dict:
    sh = {lv: sum(r["n_mac"] for r in rows if r["level_6f"] == lv) / n_model for lv in LEVELS_6F}
    cov = [r for r in rows if r["level_6f"] in COVERED]
    p = sum(r["p"] for r in cov)
    ext = sum(r["p_ext"] or 0.0 for r in rows if r["level_6f"] == "EXTRAPOLATED")
    ref = sum(r["p_ext"] or 0.0 for r in rows if r["level_6f"] == "REFUTED")
    v = sum(gi["mac"] for gi in groups.values() if gi["status"] == "PREDICTION_AGREES") / m if groups else 0.0
    d = sum(gi["mac"] for gi in groups.values()) / m if groups and partition_exact else 0.0
    return dict(share=sh, c=sum(sh[lv] for lv in COVERED), P=p, P_over_M=p / m, V=v, D=d,
                extrap_dependence=sh["EXTRAPOLATED"] + sh["REFUTED"], P_ext_6d=p + ext + ref, P_ext_6f=p + ext,
                any_evidence=any(r["level_6f"] in COVERED + ("EXTRAPOLATED",) for r in rows))


def compute_6f(cv: dict, prospective: str) -> str:
    if cv["D"] == 1.0:
        if cv["V"] >= V_FULL and prospective == "QUANTITATIVELY_EXPLAINED":
            return "PROSPECTIVELY_EXPLAINED"
        return "DECOMPOSED_PARTIALLY_PREDICTED"
    return prospective


def runtime_6f(serial_partition_holds: bool | None, mac: float | None, npu: float | None) -> str:
    if serial_partition_holds:
        return "SERIAL_DECOMPOSITION_ONLY"
    if mac and npu:
        return "LOWER_BOUND_ONLY"
    return "NOT_EXPLAINED"


def fidelity_6f(has_groups: bool, over: float, under: float) -> str:
    if has_groups:
        return "GROUP_DIRECTION_MEASURED"
    if over + under >= D.CANCEL_MIN:
        return "FAMILY_DIRECTION_ONLY"
    return "NO_EVIDENCE"


# ---- §5 Vela ------------------------------------------------------------------------------------------------------
def vela_cls(npu: float, total: float, rng: float) -> str:
    if any(abs(npu - b * total) <= rng for b in (VELA_LO, VELA_HI)):
        return "INSUFFICIENT_EVIDENCE"
    r = npu / total
    return "OVER" if r < VELA_LO else "UNDER" if r > VELA_HI else "AGREE"


def vela_terms(inv: list[dict], fam_of: dict) -> dict:
    """Per model: cycles_npu, cycles_total, memory-dominated share and per-family shares (contract §5)."""
    out = {}
    for m in sorted({r["model"] for r in inv}):
        rows = [r for r in inv if r["model"] == m and r["vela_op_cycles"]]
        tot = sum(float(r["vela_op_cycles"]) for r in rows)
        npu = sum(float(r["vela_npu_cycles"]) for r in rows if r["vela_npu_cycles"])
        mem = [r for r in rows if float(r["vela_op_cycles"]) > float(r["vela_npu_cycles"] or 0)]
        fam = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            f = fam_of.get((m, int(r["tflite_op_index"])), "OTHER") if r["tflite_op_index"] not in ("", None) else "OTHER"
            fam[f][0] += float(r["vela_op_cycles"])
            if r in mem:
                fam[f][1] += float(r["vela_op_cycles"])
        out[m] = dict(cycles_total=tot, cycles_npu=npu, mem_dominated_share=sum(float(r["vela_op_cycles"]) for r in mem) / tot,
                      families={f: dict(share=a / tot, mem_share_within=(b / a if a else 0.0)) for f, (a, b) in sorted(fam.items())})
    return out


# ---- §6 original vs serial ----------------------------------------------------------------------------------------
SERIAL_EVENTS = {"35": "npu_active", "48": "mac", "51": "dpu", "64": "ao", "80": "wd", "81": "wd_stalled",
                 "130": "sram_rd", "135": "sram_wr", "386": "ext_rd", "387": "axi_387",
                 "640": "ev640", "642": "ev642", "656": "ev656", "658": "ev658"}
EVENT_SET = {"35": "1", "48": "1", "51": "1", "64": "1", "80": "1", "81": "1", "130": "2", "135": "2", "386": "2",
             "387": "3", "640": "3", "642": "3", "656": "3", "658": "3"}


def serial(x3: dict, groups: dict) -> dict:
    out = {}
    for m in X3_GROUPS:
        tag = m.split("_")[0]
        b0, b1 = x3["results"][f"x3_{tag}_B0"]["stats"], x3["results"][f"x3_{tag}_B1"]["stats"]
        ev = {name: dict(orig=b0[EVENT_SET[e]][e][0], serial=b1[EVENT_SET[e]][e][0]) for e, name in SERIAL_EVENTS.items()}
        for v in ev.values():
            v["delta"] = v["serial"] - v["orig"]
        o, s = ev["npu_active"]["orig"], ev["npu_active"]["serial"]
        gs = sum(g["npu"] for g in groups[m].values())
        hp = x3["hypotheses"]["h_p"][m]["35"]
        out[m] = dict(events=ev, group_sum=gs,
                      ratios={"(serial-orig)/orig": (s - o) / o, "(S-orig)/S": (gs - o) / gs,
                              "(S-orig)/orig": (gs - o) / o, "(S-serial)/serial": (gs - s) / s},
                      partition_tol=hp["tol"], partition_holds=hp["holds"], schedule_invariant_mac=ev["mac"]["delta"] == 0)
    return out


# ---- §7 recommendation ----------------------------------------------------------------------------------------------
def recommend() -> dict:
    table = []
    for name, yn, boots, excluded in CANDIDATES:
        c = dict(zip(CRITERIA, (x == "Y" for x in yn)))
        elig = c["d"] and c["e"] and c["f"] and boots <= MAX_BOOTS and not excluded
        table.append(dict(name=name, criteria=c, score=sum(c.values()), boots=boots, excluded=excluded, eligible=elig))
    el = [t for t in table if t["eligible"]]
    pick = min(el, key=lambda t: (-t["score"], t["boots"], table.index(t))) if el else None
    return dict(table=table, recommendation=pick["name"] if pick else None)


# ---- judge ---------------------------------------------------------------------------------------------------------
def load() -> dict:
    return dict(ops=D.read_csv(OPS6D), s6d=json.loads(SUM6D.read_text()), s6=json.loads(S6.read_text())["models"],
                whole={r["model"]: r for r in D.read_csv(WHOLE) if r["axis"] == "mac"}, inv=D.read_csv(INV),
                x3=json.loads(X3.read_text()))


def judge(d: dict) -> dict:
    groups = x3_groups(d["ops"], d["x3"])
    rows = levels(d["ops"], groups)
    fam_of = {(r["model"], int(r["op"])): r["family"] for r in d["ops"]}
    vt = vela_terms(d["inv"], fam_of)
    ser = serial(d["x3"], groups)
    models = {}
    for m in MODELS:
        b, m6d = d["s6"][m]["baseline"], d["s6d"]["models"][m]
        mac, npu, rng = b["mac_active"], b["npu_active"], b["npu_active_range"]
        if vt[m]["cycles_npu"] != float(d["whole"][m]["vela_npu_cycles"]):
            raise SystemExit(f"{m}: inventory cycles_npu {vt[m]['cycles_npu']} != whole_model_comparison")
        mr = [r for r in rows if r["model"] == m]
        n_model = m6d["coverage"]["n_model"]
        g = groups.get(m)
        cv = coverage(mr, n_model, mac, g, d["x3"]["mac_partition_exact"].get(m, False) if g else False)
        prosp = D.compute_verdict(cv["c"], cv["P"], mac, cv["any_evidence"])
        tot = vt[m]["cycles_total"]
        canc = m6d["vela"]
        models[m] = dict(
            coverage=cv, mac_active=mac, npu_active=npu, npu_range=rng, prospective_6d=prosp,
            reproduces_6d=prosp == m6d["compute_verdict"], compute_6d=m6d["compute_verdict"],
            compute_6f=compute_6f(cv, prosp), groups=g,
            runtime_6f=runtime_6f(ser[m]["partition_holds"] if m in ser else None, mac, npu),
            runtime_bounds=dict(mac_over_npu=mac / npu, unit_max_over_npu=max(mac, b["ao_active"], b["wd_active"]) / npu),
            unit={k: b[k] for k in ("mac_active", "mac_dpu_active", "ao_active", "wd_active", "wd_stalled", "sram_rd",
                                    "sram_wr", "ext_rd", "ext_wr")},
            unit_over_npu={k: b[k] / npu for k in ("mac_active", "mac_dpu_active", "ao_active", "wd_active", "wd_stalled")},
            axi_legacy=m6d["axi"],
            vela=dict(cycles_npu=vt[m]["cycles_npu"], cycles_total=tot, board_over_total=npu / tot,
                      board_over_npu=npu / vt[m]["cycles_npu"], abs_error=npu - tot, rel_error=(npu - tot) / tot,
                      cls_total=vela_cls(npu, tot, rng), cls_npu_historical=m6d["vela"]["cls"],
                      mem_dominated_share=vt[m]["mem_dominated_share"], families=vt[m]["families"],
                      over_share=canc["over_share"], under_share=canc["under_share"], cancellation=canc["verdict"],
                      x3_groups=d["x3"]["vela"].get(m, {}).get("groups")),
            fidelity_6f=fidelity_6f(m in d["x3"]["vela"], canc["over_share"], canc["under_share"]),
        )
    return dict(contract="evidence/stage6f0/contract.md", x3_ta=d["x3"]["ta"], groups=groups, serial=ser,
                models=models, recommendation=recommend(), rows=rows)


def write(res: dict, out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = res.pop("rows")
    with (out / "operator_levels_6f.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (out / "stage6f0_summary.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "judge":
        print(__doc__)
        return 2
    write(judge(load()), pathlib.Path(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
