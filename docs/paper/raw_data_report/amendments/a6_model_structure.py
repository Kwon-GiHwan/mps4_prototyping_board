"""A6 -- model structure recollected from the Vela verbose re-compile (POST_HOC_DESCRIPTIVE).

Contract (plan 2026-09-14 section 2), fixed before any value was computed:

H4  DWConv / output-channel mismatch.
    Per TA-ON series (platform, npu, workload) with >= 2 executable MAC points:
      dw_mac_share      = MAC count of DepthwiseConv2D ops / MAC count of all NPU ops
                          (per-layer CSV of the series' smallest executable MAC config)
      mean_efficiency   = mean incremental_efficiency over the series' evaluable transitions
    Spearman rho between dw_mac_share and mean_efficiency over the series:
      DW_SHARE_ORDER_MATCHES   rho <= -0.7 (more depthwise -> lower efficiency)
      NO_ORDER_RELATION        otherwise
      NOT_EVALUABLE            fewer than 5 series, or all dw_mac_share equal

H5  Small feature map / tile parallelism.
    U85 256->512 separable ops of the frozen binding (U85_256_512_DIFFERENTIAL, binding_pair
    B-frozen, separable == 1). ofm_size = H*W*C parsed from op_identity "Type|HxWxC|...".
      SMALL_FM_CONCENTRATED    median ofm_size(REGRESS) <= 0.5 * median ofm_size(IMPROVE)
      NOT_CONCENTRATED         otherwise
      NOT_EVALUABLE            fewer than 5 ops in either group, or a shape fails to parse

Structural inputs (per cell): dwconv_op_count, dwconv_mac_share, npu_op_count, total_mac
from the per-layer CSV; per-op OFM shape, block config and ublock from the schedule dump.
"""
import csv, re, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VV = HERE / "vela_verbose" / "cells"
TABLES = ROOT / "docs/paper/raw_data_report/tables"
DIFF = ROOT / "docs/paper/raw_data_report/source_data/3_4_limits/U85_256_512_DIFFERENTIAL.csv"

RULE_SHAPE_UNPARSED = "RULE_A6_SHAPE_UNPARSED"
RULE_TOO_FEW = "RULE_A6_TOO_FEW"
RULE_NO_VARIATION = "RULE_A6_NO_VARIATION"
RULES = (RULE_SHAPE_UNPARSED, RULE_TOO_FEW, RULE_NO_VARIATION)
H4_OUTCOMES = ("DW_SHARE_ORDER_MATCHES", "NO_ORDER_RELATION", "NOT_EVALUABLE")
H5_OUTCOMES = ("SMALL_FM_CONCENTRATED", "NOT_CONCENTRATED", "NOT_EVALUABLE")

OP_RE = re.compile(r"^\s*(\d+): Operation (\S+)\s+- OFM ([\d, ]+)$")
CFG_RE = re.compile(r"OFM Block=\[([\d, ]+)\], IFM Block=\[([\d, ]+)\](?:, OFM UBlock=\[([\d, ]+)\])?")


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


# ---------- structural extraction ----------

def per_layer_structure(csv_path):
    """dwconv_op_count, dwconv_mac_share, npu_op_count, total_mac from a Vela per-layer CSV."""
    ops = [r for r in csv.DictReader(open(csv_path)) if r["Target"] == "NPU"]
    total = sum(int(float(r["MAC Count"])) for r in ops)
    dw = [r for r in ops if r["Original Operator"] == "DepthwiseConv2D"]
    dw_mac = sum(int(float(r["MAC Count"])) for r in dw)
    return {"npu_op_count": len(ops), "dwconv_op_count": len(dw), "total_mac": total,
            "dwconv_mac_share": (dw_mac / total) if total else None}


def schedule_ops(stdout_path):
    """Ops from a --verbose-schedule dump: index, type, ofm shape, ofm block, ifm block, ublock."""
    ops, cur = [], None
    for line in open(stdout_path, errors="replace"):
        m = OP_RE.match(line)
        if m:
            cur = {"index": int(m.group(1)), "type": m.group(2),
                   "ofm": [int(x) for x in m.group(3).split(",")], "ofm_block": None, "ifm_block": None, "ublock": None}
            ops.append(cur); continue
        c = CFG_RE.search(line)
        if c and cur is not None:
            cur["ofm_block"] = [int(x) for x in c.group(1).split(",")]
            cur["ifm_block"] = [int(x) for x in c.group(2).split(",")]
            cur["ublock"] = [int(x) for x in c.group(3).split(",")] if c.group(3) else None
    return ops


def structure_table(out_path):
    rows = []
    for d in sorted(VV.iterdir()):
        csvs = list(d.glob("*_per-layer.csv"))
        if not csvs:
            continue
        s = per_layer_structure(csvs[0]); ops = schedule_ops(d / "vela_stdout.txt")
        rows.append({"cell_id": d.name, **s, "schedule_ops": len(ops),
                     "ublock_set": ";".join(sorted({str(o["ublock"]) for o in ops if o["ublock"]}))})
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return rows


# ---------- H4 ----------

def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys); n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    if den == 0:
        raise Refusal(RULE_NO_VARIATION, "no variation in one variable")
    return num / den


def h4_series(structure_by_cell, transitions_path=TABLES / "3_3_scaling_transitions.csv"):
    """One row per TA-ON series: dw_mac_share (smallest executable MAC) and mean incremental efficiency."""
    series = {}
    for t in csv.DictReader(open(transitions_path)):
        if t["transition_status"] not in ("IMPROVED", "PLATEAU", "REVERSED"):
            continue
        if t["platform"] not in ("SSE-300", "SSE-320"):
            continue  # TA ON only
        key = (t["platform"], t["npu"], t["workload"])
        series.setdefault(key, {"effs": [], "macs": set()})
        series[key]["effs"].append(float(t["incremental_efficiency"]))
        series[key]["macs"].update({int(t["mac_prev"]), int(t["mac_next"])})
    out = []
    for (plat, npu, wl), v in sorted(series.items()):
        cell = f"{wl}__{plat}__{npu}-{min(v['macs'])}"
        s = structure_by_cell.get(cell)
        if s is None or s["dwconv_mac_share"] is None:
            continue
        out.append({"platform": plat, "npu": npu, "workload": wl, "min_mac": min(v["macs"]), "n_transitions": len(v["effs"]),
                    "dw_mac_share": float(s["dwconv_mac_share"]), "mean_incremental_efficiency": sum(v["effs"]) / len(v["effs"])})
    return out


def h4_verdict(series_rows):
    try:
        if len(series_rows) < 5:
            raise Refusal(RULE_TOO_FEW, f"{len(series_rows)} series")
        rho = spearman([r["dw_mac_share"] for r in series_rows], [r["mean_incremental_efficiency"] for r in series_rows])
    except Refusal as e:
        return {"outcome": "NOT_EVALUABLE", "rule": e.rule, "rho": None, "n": len(series_rows)}
    return {"outcome": "DW_SHARE_ORDER_MATCHES" if rho <= -0.7 else "NO_ORDER_RELATION", "rule": "", "rho": round(rho, 4), "n": len(series_rows)}


# ---------- H5 ----------

def ofm_size(op_identity):
    parts = op_identity.split("|")
    if len(parts) < 2 or not re.fullmatch(r"\d+x\d+x\d+", parts[1]):
        raise Refusal(RULE_SHAPE_UNPARSED, op_identity)
    h, w, c = (int(x) for x in parts[1].split("x"))
    return h * w * c


def h5_rows(diff_path=DIFF, binding="B-frozen"):
    rows = []
    for r in csv.DictReader(open(diff_path)):
        if r["binding_pair"] != binding or r["separable"] != "1":
            continue
        rows.append({"workload": r["workload"], "op_type": r["op_type"], "op_identity": r["op_identity"],
                     "direction": r["observed_direction"], "cycles_256": r["cycles_256"], "cycles_512": r["cycles_512"]})
    return rows


def h5_verdict(rows):
    try:
        sizes = {"IMPROVE": [], "REGRESS": [], "SAME": []}
        for r in rows:
            sizes.setdefault(r["direction"], []).append(ofm_size(r["op_identity"]))
        if len(sizes["IMPROVE"]) < 5 or len(sizes["REGRESS"]) < 5:
            raise Refusal(RULE_TOO_FEW, f"improve={len(sizes['IMPROVE'])} regress={len(sizes['REGRESS'])}")
    except Refusal as e:
        return {"outcome": "NOT_EVALUABLE", "rule": e.rule}
    mi, mr = statistics.median(sizes["IMPROVE"]), statistics.median(sizes["REGRESS"])
    return {"outcome": "SMALL_FM_CONCENTRATED" if mr <= 0.5 * mi else "NOT_CONCENTRATED", "rule": "",
            "median_ofm_improve": mi, "median_ofm_regress": mr,
            "median_ofm_same": statistics.median(sizes["SAME"]) if sizes["SAME"] else None,
            "n_improve": len(sizes["IMPROVE"]), "n_regress": len(sizes["REGRESS"]), "n_same": len(sizes["SAME"])}


def main():
    rows = structure_table(HERE / "a6_model_structure.csv")
    by_cell = {r["cell_id"]: r for r in rows}
    s4 = h4_series(by_cell)
    with open(HERE / "a6_h4_series.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(s4[0].keys())); w.writeheader(); w.writerows(s4)
    v4 = h4_verdict(s4); v5 = h5_verdict(h5_rows())
    print("structure cells", len(rows)); print("H4", v4); print("H5", v5)
    for r in sorted(s4, key=lambda r: -r["dw_mac_share"]):
        print(f"  {r['platform']:8s} {r['npu']:9s} {r['workload']:28s} dw_share {r['dw_mac_share']:.3f}  mean_eff {r['mean_incremental_efficiency']:.3f}  n={r['n_transitions']}")


if __name__ == "__main__":
    sys.exit(main())
