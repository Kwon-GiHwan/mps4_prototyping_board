#!/usr/bin/env python3
"""Stage 6D — seven-model hardware/compiler reassessment, board-free (contract evidence/stage6d/contract.md).

  python3 stage6d.py judge <out dir>
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RES = REPO / "results"
OPS = RES / "fi101_stage6m/operator_mapping.csv"
H1UC = RES / "fi101_stage6m/h1uc_operators.csv"
COV6M = RES / "fi101_stage6m/coverage_comparison.csv"
SUM6M = RES / "fi101_stage6m/stage6m_summary.json"
WHOLE = RES / "fi101_stage6/whole_model_comparison.csv"
STAGE1 = RES / "fi101_stage1/stage1.csv"
STAGE3 = RES / "fi101_stage3/stage3.csv"
SUM6C = RES / "fi101_stage6c/stage6c_summary.json"

MODELS = ("kws_micronet_m", "ad_medium_int8", "mobilenet_v2_1.0_224_INT8", "vww4_128_128_INT8", "rnnoise_INT8",
          "yolo-fastest_192_face_v4", "wav2letter_pruned_int8")
LEVELS = ("INVALID_OR_UNSTABLE", "EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED", "EXTRAPOLATED",
          "UNSUPPORTED")
PREDICTED = LEVELS[1:4]
GAP_LEVELS = ("INVALID_OR_UNSTABLE", "EXTRAPOLATED", "UNSUPPORTED")
# (model, tflite op index) -> 6C shape whose measured MAC_ACTIVE is R_EXACT
EXACT = {("yolo-fastest_192_face_v4", 9): "s6c_f1_rep", ("yolo-fastest_192_face_v4", 3): "s6c_f2_rep",
         ("wav2letter_pruned_int8", 17): "s6c_f4_rep", ("kws_micronet_m", 0): "s6c_f5_rep"}
UNSTABLE_OPS = {("rnnoise_INT8", 46)}  # F3, Stage 6C UNSTABLE
COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.50
VELA_DIR = {"PK1x1": "UNDER", "DW": "OVER", "PK1D": "OVER", "FIRST_CONV": "UNDER", "FC": "UNDER",
            "DF1x1": "MIXED", "PK3x3": "MIXED"}
CANCEL_MIN = 0.10
GAPS = (  # name, families, controllable, discriminating, cost (boots) — contract §6
    ("G_PK1X1", ("PK1x1",), True, True, 6),
    ("G_DF_EXT", ("DF1x1",), True, True, 9),
    ("G_FC", ("FC",), True, False, 4),
    ("G_DW_VELA", ("DW",), True, True, 6),
    ("G_PK1D", ("PK1D",), True, True, 3),
    ("G_FIRST", ("FIRST_CONV", "PK3x3"), True, True, 4),
    ("G_AO1", (), True, True, 4),
    ("G_WD", (), True, True, 4),
)
MAX_COST = 9


def read_csv(p: pathlib.Path) -> list[dict]:
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def dims(s: str) -> list[int]:
    return [int(x) for x in s.split("x")]


def up16(n: int) -> int:
    return math.ceil(n / 16) * 16


# ---- §1 family ---------------------------------------------------------------------------------------------------
def family(r: dict) -> str:
    if r["exec_on"] != "NPU":
        return "CPU_OR_SPLIT"
    if not r["n_mac_tflite"] or int(r["n_mac_tflite"]) == 0:
        return "AO_ELEMENTWISE"
    op, k, tr = r["tflite_op"], r["kernel"], r["traversal"]
    if op == "DEPTHWISE_CONV_2D":
        return "DW"
    if op == "FULLY_CONNECTED":
        return "FC"
    if op == "CONV_2D":
        kh, kw = dims(k)
        if k == "1x1":
            return "DF1x1" if tr == "DepthFirst" else "PK1x1"
        if k == "3x3" and tr == "PartKernel":
            return "PK3x3"
        if kh == 1 and kw >= 7 and tr == "PartKernel":
            return "PK1D"
        if int(r["cin"]) < 16:
            return "FIRST_CONV"
    return "OTHER_CONV"


# ---- §2 rules: (prediction, in validated range) -------------------------------------------------------------------
def rule(r: dict, fam: str) -> tuple[float | None, bool]:
    ho, wo, _ = dims(r["npu_ofm_hwc"])
    cin, cout, k, s = int(r["cin"]), int(r["cout"]), dims(r["kernel"]), r["stride"]
    if fam == "DW":
        p = ho * wo * up16(cout) * k[0] * k[1] / 128
        return p, k == [3, 3] and s == "1x1" and 8 <= cout <= 145
    if fam == "FC":
        p = ho * wo * up16(cin) * up16(cout) / 256
        return p, ho * wo == 1 and 95 <= cin <= 96 and 287 <= cout <= 288
    if fam == "PK3x3":
        p = ho * wo * up16(cin) * cout * 9 / 768
        return p, s == "1x1" and 16 <= cin <= 64 and cout % 16 == 0
    return None, False


# ---- §3 level ----------------------------------------------------------------------------------------------------
def level(r: dict, fam: str, h1: dict, exact: dict) -> tuple[str, float | None, float | None]:
    """Return (level, P for levels 2-4, P_ext for extrapolated)."""
    key = (r["model"], int(r["tflite_op_index"]))
    hr = h1.get(key)
    if key in UNSTABLE_OPS or (hr and hr["measured_unstable_match"]):
        return LEVELS[0], None, None
    if r["category"] == "BOARD_MEASURED":
        return LEVELS[1], float(hr["h1uc"]), None
    if key in exact:
        return LEVELS[2], exact[key], None
    p, ok = rule(r, fam)
    if ok:
        return LEVELS[3], p, None
    if fam == "DF1x1" and hr and hr["h1uc"]:
        return LEVELS[4], None, float(hr["h1uc"])
    if fam in ("DW", "FC", "PK3x3", "PK1x1", "PK1D", "FIRST_CONV", "DF1x1"):
        return LEVELS[4], None, p
    return LEVELS[5], None, None


def classify(ops: list[dict], h1: dict, exact: dict) -> list[dict]:
    out = []
    for r in ops:
        fam = family(r)
        row = dict(model=r["model"], op=int(r["tflite_op_index"]), tflite_op=r["tflite_op"], family=fam,
                   kernel=r["kernel"], stride=r["stride"], traversal=r["traversal"], cin=r["cin"], cout=r["cout"],
                   ofm=r["npu_ofm_hwc"], n_mac=int(r["n_mac_tflite"] or 0), vela_op_cycles=r["vela_op_cycles"])
        if fam in ("CPU_OR_SPLIT", "AO_ELEMENTWISE"):
            row.update(level=fam, p=None, p_ext=None)
        else:
            lv, p, pe = level(r, fam, h1, exact)
            row.update(level=lv, p=p, p_ext=pe)
        out.append(row)
    return out


# ---- §4 model verdict --------------------------------------------------------------------------------------------
def coverage(rows: list[dict]) -> dict:
    n_model = sum(r["n_mac"] for r in rows)
    mac_ops = [r for r in rows if r["level"] not in ("CPU_OR_SPLIT", "AO_ELEMENTWISE")]
    npu_ops = [r for r in rows if r["level"] != "CPU_OR_SPLIT"]
    share = {lv: (sum(r["n_mac"] for r in mac_ops if r["level"] == lv) / n_model if n_model else 0.0) for lv in LEVELS}
    count = {lv: (sum(r["level"] == lv for r in npu_ops) / len(npu_ops) if npu_ops else 0.0)
             for lv in LEVELS + ("AO_ELEMENTWISE",)}
    cov = [r for r in mac_ops if r["level"] in PREDICTED]
    c = sum(r["n_mac"] for r in cov) / n_model if n_model else 0.0
    p = sum(r["p"] for r in cov)
    p_ext = p + sum(r["p_ext"] for r in mac_ops if r["level"] == "EXTRAPOLATED" and r["p_ext"] is not None)
    return dict(n_model=n_model, share=share, count_share=count, c=c, P=p, P_ext=p_ext,
                any_evidence=any(r["level"] in LEVELS[1:5] for r in mac_ops))


def compute_verdict(c: float, p: float, m: float | None, any_evidence: bool) -> str:
    if not m:
        return "INSUFFICIENT_EVIDENCE"
    if c >= COV_FULL and LO * m <= p <= HI * m:
        return "QUANTITATIVELY_EXPLAINED"
    if p > HI * m or (c >= COV_FULL and p < LO * m):
        return "NOT_EXPLAINED"
    if COV_PART <= c < COV_FULL:
        return "PARTIALLY_EXPLAINED"
    if c < COV_PART and any_evidence:
        return "QUALITATIVE_SUPPORT_ONLY"
    return "INSUFFICIENT_EVIDENCE"


# ---- §5 vela direction / cancellation ----------------------------------------------------------------------------
def cancellation(rows: list[dict], n_model: int) -> dict:
    def sh(d):
        return sum(r["n_mac"] for r in rows if VELA_DIR.get(r["family"]) == d) / n_model if n_model else 0.0
    over, under = sh("OVER"), sh("UNDER")
    return dict(over_share=over, under_share=under, mixed_share=sh("MIXED"),
                verdict="CANCELLATION_POSSIBLE" if over >= CANCEL_MIN and under >= CANCEL_MIN
                else "NO_CANCELLATION_INDICATED")


def vela_class(ratio: float) -> str:
    return "OVERESTIMATION" if ratio < 0.9 else "UNDERESTIMATION" if ratio > 1.1 else "ESTIMATE_AGREEMENT"


# ---- §6 recommendation -------------------------------------------------------------------------------------------
def gap_impact(rows_by_model: dict, fams: tuple) -> float:
    best = 0.0
    for rows in rows_by_model.values():
        n = sum(r["n_mac"] for r in rows)
        s = sum(r["n_mac"] for r in rows if r["family"] in fams and r["level"] in GAP_LEVELS)
        best = max(best, s / n if n else 0.0)
    return best


def recommend(rows_by_model: dict) -> dict:
    table = [dict(gap=g, families=list(f), controllable=c, discriminating=d, cost=k,
                  impact=gap_impact(rows_by_model, f)) for g, f, c, d, k in GAPS]
    elig = [t for t in table if t["controllable"] and t["discriminating"] and t["cost"] <= MAX_COST]
    pick = max(elig, key=lambda t: t["impact"]) if elig else None   # max() keeps the first on ties
    return dict(table=table, recommendation=pick["gap"] if pick else None)


# ---- judge -------------------------------------------------------------------------------------------------------
def load() -> dict:
    ops = read_csv(OPS)
    h1 = {(r["model"], int(r["tflite_op_index"])): r for r in read_csv(H1UC)}
    s6c = json.loads(SUM6C.read_text())
    exact = {}
    for key, shape in EXACT.items():
        if s6c["results"][shape]["status"] == "VALID":
            exact[key] = float(s6c["results"][shape]["metrics"]["mac_active"])
    whole = {}
    for r in read_csv(WHOLE):
        whole.setdefault(r["model"], {})[r["axis"]] = r
    return dict(ops=ops, h1=h1, exact=exact, whole=whole, s1={r["model"]: r for r in read_csv(STAGE1)},
                s3={r["model"]: r for r in read_csv(STAGE3)}, cov6m={r["model"]: r for r in read_csv(COV6M)},
                v6m=json.loads(SUM6M.read_text())["verdict"])


def judge(d: dict) -> dict:
    rows = classify(d["ops"], d["h1"], d["exact"])
    by_model = {m: [r for r in rows if r["model"] == m] for m in MODELS}
    models = {}
    for m in MODELS:
        w = d["whole"][m]
        mac, npu, vela = float(w["mac"]["measured"]), float(w["mac"]["npu_active"]), float(w["mac"]["vela_npu_cycles"])
        cv = coverage(by_model[m])
        s1, s3, c6 = d["s1"].get(m, {}), d["s3"].get(m, {}), d["cov6m"][m]
        models[m] = dict(
            coverage=cv, mac_active=mac, npu_active=npu,
            compute_verdict=compute_verdict(cv["c"], cv["P"], mac, cv["any_evidence"]),
            p_over_m=cv["P"] / mac, p_ext_over_m=cv["P_ext"] / mac,
            runtime_verdict="NOT_EXPLAINED",
            runtime_reason="no validated model-level NPU_ACTIVE predictor (isolated graph IO in DDR, overlap unmeasured)",
            unit=dict(mac_over_npu=mac / npu, ao_over_npu=float(w["ao"]["measured"]) / npu,
                      wd_over_npu=float(w["wd"]["measured"]) / npu,
                      eff_tflite=cv["n_model"] / (1024 * mac),
                      legacy_dpu_over_mac=s1.get("dpu_over_mac"), legacy_wd_stalled_ratio=s1.get("wd_stalled_ratio")),
            axi={k: s3.get(k) for k in ("sram_bytes", "ext_bytes", "bytes_per_mac", "sram_rd_burst", "ext_rd_burst",
                                        "sram_rd_req_stall", "ext_rd_req_stall", "ext_rd_port_imbalance",
                                        "vela_sram_bytes", "vela_dram_bytes")},
            vela=dict(board_over_vela=npu / vela, cls=vela_class(npu / vela), **cancellation(by_model[m], cv["n_model"])),
            stage6m=dict(evidence_supported=float(c6["evidence_supported"]), static_structural=float(c6["static_structural"])),
        )
    return dict(contract="evidence/stage6d/contract.md", stage6m_verdict=d["v6m"]["verdict"], exact_ops=
                {f"{k[0]}:{k[1]}": v for k, v in sorted(d["exact"].items())}, models=models,
                recommendation=recommend(by_model), rows=rows)


def write(res: dict, out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = res.pop("rows")
    with (out / "operator_levels.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (out / "stage6d_summary.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "judge":
        print(__doc__)
        return 2
    write(judge(load()), pathlib.Path(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
