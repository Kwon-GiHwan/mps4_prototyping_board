#!/usr/bin/env python3
"""Stage 6E-0 — static identifiability of model-level cost attribution (contract evidence/stage6e0/contract.md).

  python3 stage6e0.py judge <out dir>
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RES = REPO / "results"
S6D = RES / "fi101_stage6d/stage6d_summary.json"
LEVELS6D = RES / "fi101_stage6d/operator_levels.csv"
OPS = RES / "fi101_stage6m/operator_mapping.csv"
STAGE1 = RES / "fi101_stage1/stage1.csv"
STAGE3 = RES / "fi101_stage3/stage3.csv"

PRED_LEVELS = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED")
HI, LO, COV_ALL = 1.05, 0.95, 0.95
CRITERIA = tuple(f"c{i}" for i in range(1, 11))
# contract §3 — per-op time attribution obtained by each existing instrument (all: none)
INSTRUMENTS = (
    ("NPU_OP_PMU_MASK (2B-0b)", "fi101_stage2_mask", False),
    ("group mask windows (2B-2)", "fi101_stage2_groups", False),
    ("3a window pilot (2B-3)", "fi101_stage2b3/pilot", False),
    ("QREAD trace", "qread_pilot, qread_op_pilot", False),
    ("PMCLUT overlap (2A-F2)", "fi101_stage2_probe", False),
)
Y, N = True, False
# contract §5 — fixed assessment: name, c1..c10, vela_condition_match, boots
CANDIDATES = (
    ("X1_G_DF_EXT", (N, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 9),
    ("X2_PREFIX_STOP", (Y, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 10),
    ("X3_SERIAL_MASK", (Y, Y, Y, Y, Y, Y, Y, Y, Y, Y), Y, 10),
    ("X4_QREAD_FINE", (Y, Y, N, N, Y, N, N, Y, Y, Y), N, 4),
    ("X5_AD_REST_ISOLATED", (N, Y, Y, Y, Y, Y, Y, N, N, Y), N, 4),
)
IMPLEMENTATION = {  # contract §5, selected-candidate items (X3)
    "X3_SERIAL_MASK": (("cms insert / PMU_MASK", "EXISTS"), ("KERNEL_WAIT encoding", "NEW_BOUNDED"),
                       ("COP1 extract", "EXISTS"), ("COP1 replace + tflite reserialize", "NEW_BOUNDED"),
                       ("DRWL pack, identity", "EXISTS"), ("runner firmware unchanged", "EXISTS"),
                       ("PMU_MASK / KERNEL_WAIT(0) on driver runner", "NEEDS_BOARD_PRECHECK"),
                       ("judge and contract", "NEW_BOUNDED")),
}
PRECHECK_IN_FIRST_BOOT = {"X3_SERIAL_MASK": True}


def read_csv(p: pathlib.Path) -> list[dict]:
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- §2 compute attribution ------------------------------------------------------------------------------------
def predicted_share(rows: list[dict]) -> float:
    mac = [r for r in rows if r["level"] not in ("CPU_OR_SPLIT", "AO_ELEMENTWISE")]
    n = sum(int(r["n_mac"]) for r in rows)
    has = sum(int(r["n_mac"]) for r in mac if r["level"] in PRED_LEVELS or fnum(r["p_ext"]) is not None)
    return has / n if n else 0.0


def compute_attribution(v6d: str, p_v: float, p_all: float, m: float, share_pred: float) -> str:
    if v6d == "QUANTITATIVELY_EXPLAINED":
        return "EXPLAINED_WITH_EXISTING_DATA"
    if v6d == "PARTIALLY_EXPLAINED" or (p_v <= HI * m and p_all >= LO * m and share_pred >= COV_ALL):
        return "PARTIALLY_EXPLAINED"
    return "NOT_IDENTIFIABLE"


# ---- §5 candidates ---------------------------------------------------------------------------------------------
def select(cands=CANDIDATES) -> dict:
    eligible = [c for c in cands if all(c[1])]
    if eligible:
        pick = min(eligible, key=lambda c: c[3])          # min keeps table order on ties
    else:
        pick = max(cands, key=lambda c: sum(c[1]))
    return dict(name=pick[0], eligible=bool(eligible), criteria=dict(zip(CRITERIA, pick[1])),
                vela_condition_match=pick[2], boots=pick[3])


def next_experiment(sel: dict, cands=CANDIDATES, impl=IMPLEMENTATION, pre=PRECHECK_IN_FIRST_BOOT) -> str:
    states = [s for _, s in impl.get(sel["name"], ())]
    if not any(c[1][3] for c in cands):
        return "INSUFFICIENT_IDENTIFIABILITY"
    if (sel["eligible"] and "UNKNOWN_FEASIBILITY" not in states
            and ("NEEDS_BOARD_PRECHECK" not in states or pre.get(sel["name"], False))):
        return "READY_FOR_BOARD_REVIEW"
    return "STATIC_DESIGN_INCOMPLETE"


# ---- §3 / §4 ----------------------------------------------------------------------------------------------------
def execution_cost(sel: dict, instruments=INSTRUMENTS) -> str:
    if any(ok for _, _, ok in instruments):
        return "MEASURABLE_WITH_EXISTING_INSTRUMENTATION"
    c = sel["criteria"]
    if c["c3"] and c["c4"] and c["c7"]:
        return "REQUIRES_CONTROLLED_EXPERIMENT"
    return "NOT_IDENTIFIABLE"


def vela_fidelity(sel: dict, all_classified: bool) -> str:
    if sel["criteria"]["c6"] and sel["vela_condition_match"]:
        return "TESTABLE_MECHANISM_IDENTIFIED"
    if all_classified:
        return "DISCREPANCY_CHARACTERIZED"
    return "CAUSE_UNRESOLVED"


def vela_terms(ops: list[dict]) -> dict:
    """Descriptive: Vela per-op cost composition for the NPU MAC ops of one model."""
    rows = [o for o in ops if o["exec_on"] == "NPU" and fnum(o["vela_op_cycles"]) is not None]
    op = sum(float(o["vela_op_cycles"]) for o in rows)
    mac = sum(fnum(o["vela_mac_cycles"]) or 0.0 for o in rows)
    non_mac = sum(float(o["vela_op_cycles"]) for o in rows if float(o["vela_op_cycles"]) > (fnum(o["vela_mac_cycles"]) or 0.0))
    return dict(sum_op_cycles=op, sum_mac_cycles=mac, non_mac_bound_share=non_mac / op if op else None, n_ops=len(rows))


# ---- judge ------------------------------------------------------------------------------------------------------
def judge() -> tuple[dict, list[dict], list[dict]]:
    s6d = json.loads(S6D.read_text())
    lv = read_csv(LEVELS6D)
    ops = read_csv(OPS)
    s1 = {r["model"]: r for r in read_csv(STAGE1)}
    s3 = {r["model"]: r for r in read_csv(STAGE3)}
    sel = select()
    models, table = {}, []
    for m, v in s6d["models"].items():
        rows = [r for r in lv if r["model"] == m]
        c = v["coverage"]
        mac, npu, vela = v["mac_active"], v["npu_active"], v["npu_active"] / v["vela"]["board_over_vela"]
        sp = predicted_share(rows)
        ca = compute_attribution(v["compute_verdict"], c["P"], c["P_ext"], mac, sp)
        row = dict(model=m, npu_active=npu, mac_active=mac, P_v=c["P"], P_all=c["P_ext"], R_c=mac - c["P"],
                   R_c_over_M=(mac - c["P"]) / mac, R_c_all=mac - c["P_ext"], predicted_nmac_share=sp,
                   execution_cost_residual="NOT_COMPUTED", vela_npu_cycles=vela, E_v=npu - vela,
                   board_over_vela=npu / vela, mac_over_npu=v["unit"]["mac_over_npu"], ao_over_npu=v["unit"]["ao_over_npu"],
                   wd_over_npu=v["unit"]["wd_over_npu"], legacy_dpu_over_mac=s1[m]["dpu_over_mac"],
                   legacy_wd_stalled_ratio=s1[m]["wd_stalled_ratio"], legacy_sram_bytes=s3[m]["sram_bytes"],
                   legacy_ext_bytes=s3[m]["ext_bytes"], legacy_ext_rd_req_stall=s3[m]["ext_rd_req_stall"],
                   legacy_ext_rd_port_imbalance=s3[m]["ext_rd_port_imbalance"], compute_attribution=ca)
        table.append(row)
        models[m] = dict(compute_attribution=ca, vela_terms=vela_terms([o for o in ops if o["model"] == m]))
    om = {(o["model"], o["tflite_op_index"]): o for o in ops}
    ad = []
    for r in lv:
        if r["model"] != "ad_medium_int8" or r["level"] == "CPU_OR_SPLIT":
            continue
        o = om[(r["model"], r["op"])]
        ad.append(dict(op=int(r["op"]), family=r["family"], level=r["level"], n_mac=int(r["n_mac"]), p=r["p"],
                       p_ext=r["p_ext"], kernel=r["kernel"], stride=r["stride"], cin=r["cin"], cout=r["cout"], ofm=r["ofm"],
                       vela_op_cycles=o["vela_op_cycles"], vela_mac_cycles=o["vela_mac_cycles"]))
    ad_row = next(t for t in table if t["model"] == "ad_medium_int8")
    rest = [a for a in ad if a["level"] not in PRED_LEVELS and a["level"] != "AO_ELEMENTWISE"]
    ad_diag = dict(R_c=ad_row["R_c"], candidate_ops=[a["op"] for a in rest],
                   candidate_p_ext_sum=sum(fnum(a["p_ext"]) or 0.0 for a in rest),
                   candidate_without_p_ext=[a["op"] for a in rest if fnum(a["p_ext"]) is None])
    all_classified = all(v["vela"]["cls"] for v in s6d["models"].values())
    summary = dict(
        contract="evidence/stage6e0/contract.md", stage6d=s6d["contract"], models=models, ad_residual=ad_diag,
        instruments=[dict(name=a, source=b, per_op_time=c) for a, b, c in INSTRUMENTS],
        candidates=[dict(name=n, criteria=dict(zip(CRITERIA, c)), met=sum(c), vela_condition_match=v, boots=b)
                    for n, c, v, b in CANDIDATES],
        selected=sel, implementation=[dict(item=i, state=s) for i, s in IMPLEMENTATION.get(sel["name"], ())],
        verdicts=dict(execution_cost=execution_cost(sel), vela_fidelity=vela_fidelity(sel, all_classified),
                      next_experiment=next_experiment(sel)))
    return summary, table, sorted(ad, key=lambda a: a["op"])


def write_csv(p: pathlib.Path, rows: list[dict]) -> None:
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "judge":
        print(__doc__)
        return 2
    out = pathlib.Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    s, t, ad = judge()
    (out / "stage6e0_summary.json").write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    write_csv(out / "model_differences.csv", t)
    write_csv(out / "ad_operators.csv", ad)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
