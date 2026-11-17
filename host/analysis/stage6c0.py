#!/usr/bin/env python3
"""Stage 6C-0 (evidence/stage6c0/contract.md): board-free integration of every existing Unit / AXI / Vela measurement
and the Stage 6C operator-family selection. Reads committed result files only; never fills a missing value.

  python3 stage6c0.py specs <specs.json>                      candidate shapes for the container compile check
  python3 stage6c0.py run <out dir> <compile_facts.json>      every output of the stage
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
R = REPO / "results"
SOURCES = dict(
    models_driver=R / "fi101_stage4wd/mlek_wd.json", models_vela=R / "fi101_stage6b/stage6be2a/reference_models.csv",
    models_nmac=R / "fi101_stage6m/model_metrics.csv", stage1=R / "fi101_stage1/stage1.csv", stage3=R / "fi101_stage3/stage3.csv",
    stage4=R / "fi101_stage4/stage4_summary.csv", stage4c2=R / "fi101_stage4c2/stage4c2_table.csv",
    stage4k=R / "fi101_stage4k/stage4k_table.csv", stage4k_static=R / "fi101_stage4k/stage4k_static.csv",
    stage4ao=R / "fi101_stage4ao/summary.json", stage4aoe=R / "fi101_stage4aoe/summary.json",
    stage4wd=R / "fi101_stage4wd/summary.json", placement=R / "stage4_placement/stage4p_summary.json",
    e2a=R / "fi101_stage6b/stage6be2a/vela_board_table.csv", e2d=R / "fi101_stage6b/stage6be2ea/trackB/e2d_table.csv",
    e2eb=R / "fi101_stage6b/stage6be2eb/stage6be2eb_summary.json", e2ed=R / "fi101_stage6b/stage6be2ed/stage6be2ed_summary.json",
    families=R / "fi101_stage6m/mac_family_breakdown.csv", ops=R / "fi101_stage6m/operator_mapping.csv",
    inventory=R / "fi101_stage4/stage4_operator_inventory.csv")
FIELDS = ("key", "source", "stage", "item", "level", "family", "runner", "image", "ta", "latency", "placement", "n_mac",
          "npu_active", "npu_range", "mac_active", "mac_dpu_active", "ao_active", "wd_active", "wd_stalled",
          "sram_rd_bytes", "sram_wr_bytes", "ext_rd_bytes", "ext_wr_bytes", "ext_rd_trans", "traversal", "ofm_block",
          "ofm_ublock", "kernels", "vela_compute", "vela_sram_ac", "vela_dram_ac", "vela_total", "vela_npu", "status")
TOL = 0.01
LOW_EVIDENCE_MAX = 2
IMPORTANCE_MIN = 0.10
MAX_BOOTS = 9
MEASURED_SHAPES = {"F1": 2, "F2": 1, "F3": 1, "F4": 0, "F5": 0}          # contract §5 C1 (driver runner)
MEASURED_KEYS = {"F1": {("PartKernel", "1x1", True)}, "F2": {("Depthwise", "3x3", True)}, "F3": {("DepthFirst", "1x1", True)},
                 "F4": set(), "F5": set()}                                    # (traversal, kernel, Cin % 16 == 0)
CONTROL = {"F1": ("cin16", "cout2"), "F2": ("c16", "k5"), "F3": ("cin16", "cout2"), "F4": None, "F5": None}
PRIORITY = ("F1", "F2", "F3", "F4", "F5")
LIMITS = dict(fast_size=0x60000, arena_size=0x200000, model_region=32 << 20)


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _csv(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def row(**kw) -> dict:
    r = {k: None for k in FIELDS}
    r.update(kw)
    r["key"] = f"{r['stage']}:{r['item']}" + (f":L{r['latency']}" if r.get("latency") not in (None, 500) else "")
    return r


def beats(x):
    v = _f(x)
    return None if v is None else v * 16


def family_of_config(name: str) -> str:
    n = name.lower()
    if "conv3x3" in n:
        return "conv3x3 PartKernel"
    if "dw" in n:
        return "dw3x3"
    if "fc" in n:
        return "fc"
    if "conv" in n or n.startswith(("g", "e1r", "e2d", "e2eb", "s4c2")):
        return "conv1x1"
    return "elementwise"


# ---- Phase 0: integration ---------------------------------------------------------------------------------------------
def passes_row(m: dict, **kw) -> dict:
    """A row from pass A / B medians named A_<code> / B_<code> (Stage 4 layout)."""
    g = lambda k: _f(m.get(k))
    return row(npu_active=g("A_35"), npu_range=g("A_35_range"), mac_active=g("A_48"), mac_dpu_active=g("A_51"),
               ao_active=g("A_64"), wd_active=g("A_80"), wd_stalled=g("A_81"), sram_rd_bytes=beats(m.get("B_130")),
               sram_wr_bytes=beats(m.get("B_135")), ext_rd_bytes=beats(m.get("B_386")), ext_wr_bytes=beats(m.get("B_391")),
               ext_rd_trans=g("B_384"), **kw)



def load_models() -> list[dict]:
    vela = {r["model"]: r for r in _csv(SOURCES["models_vela"])}
    nmac = {r["model"]: r for r in _csv(SOURCES["models_nmac"])}
    out = []
    for d in json.loads(SOURCES["models_driver"].read_text()):
        m = d["model"]; v = vela.get(m, {})
        out.append(row(source="stage4wd/mlek_wd.json + stage6be2a/reference_models.csv", stage="driver_m7", item=m,
                       level="model", family="model", runner="driver", image="65cf963", ta=1, latency=500, placement="mlek",
                       n_mac=_f(nmac.get(m, {}).get("n_model")), npu_active=_f(d["npu_active"]), mac_active=_f(d["mac_active"]),
                       ao_active=_f(d["ao_active"]), wd_active=_f(d["wd_active"]), wd_stalled=_f(d["wd_stalled"]),
                       vela_total=_f(v.get("vela_total")), vela_npu=_f(v.get("vela_npu")), status="VALID"))
    for r in _csv(SOURCES["stage1"]):
        a = _f(r["active"])
        x = lambda k: None if a is None or _f(r[k]) is None else _f(r[k]) * a
        out.append(row(source="fi101_stage1/stage1.csv", stage="stage1", item=r["model"], level="model", family="model",
                       runner="legacy", image="2bb04bfa", ta=1, latency=500, placement="mlek", n_mac=_f(r["n_mac"]),
                       npu_active=a, mac_active=x("mac_active_ratio"), mac_dpu_active=x("dpu_active_ratio"),
                       ao_active=x("ao_active_ratio"), wd_active=x("wd_active_ratio"), wd_stalled=x("wd_stalled_ratio"),
                       vela_npu=_f(r["vela_cycles_npu"]), status=r["status"]))
    return out


def load_operators() -> list[dict]:
    out = []
    for r in _csv(SOURCES["stage4"]):
        out.append(row(source="fi101_stage4/stage4_summary.csv", stage="stage4", item=r["config"], level="operator",
                       family=family_of_config(r["config"]), runner="driver", image="83398c7", ta=1, latency=500, placement="ddr",
                       n_mac=_f(r["macs"]), npu_active=_f(r["A_35"]), npu_range=_f(r["A_35_range"]), mac_active=_f(r["A_48"]),
                       mac_dpu_active=_f(r["A_51"]), ao_active=_f(r["A_64"]), wd_active=_f(r["A_80"]), wd_stalled=_f(r["A_81"]),
                       sram_rd_bytes=beats(r["B_130"]), sram_wr_bytes=beats(r["B_135"]), ext_rd_bytes=beats(r["B_386"]),
                       ext_wr_bytes=beats(r["B_391"]), ext_rd_trans=_f(r["B_384"]), ofm_block=r["ofm_block"],
                       ofm_ublock=r["ofm_ublock"], kernels=r["kernels"], vela_npu=_f(r["vela_npu_cycles"]), status=r["gate_c"]))
    for r in _csv(SOURCES["stage4c2"]):
        out.append(row(source="fi101_stage4c2/stage4c2_table.csv", stage="stage4c2", item=r["config"], level="operator",
                       family="conv1x1", runner="driver", image="83398c7", ta=1, latency=500, placement="ddr", n_mac=_f(r["macs"]),
                       npu_active=_f(r["npu_active_a"]), npu_range=_f(r["npu_active_range_a"]), mac_active=_f(r["mac_active"]),
                       mac_dpu_active=_f(r["mac_dpu_active"]), ao_active=_f(r["ao_active"]), wd_active=_f(r["wd_active"]),
                       wd_stalled=_f(r["wd_stalled"]), sram_rd_bytes=beats(r["sram_rd_beats"]), sram_wr_bytes=beats(r["sram_wr_beats"]),
                       ext_rd_bytes=beats(r["ext_rd_beats"]), ext_wr_bytes=beats(r["ext_wr_beats"]), ext_rd_trans=_f(r["ext_rd_trans"]),
                       traversal=r["kernels_traversal"], ofm_block=r["block_ublock"], status=r["verdict"]))
    st = {r["config"]: r for r in _csv(SOURCES["stage4k_static"])}
    for r in _csv(SOURCES["stage4k"]):
        s = st.get(r["config"], {})
        out.append(row(source="fi101_stage4k/stage4k_table.csv + stage4k_static.csv", stage="stage4k", item=r["config"],
                       level="operator", family=f"conv{r['kernel']}x{r['kernel']} {r['traversal']}", runner="driver",
                       image="70090f1", ta=1, latency=500, placement="ddr", n_mac=_f(r["macs_nominal"]), npu_active=_f(r["npu_active"]),
                       npu_range=_f(r["npu_active_range"]), mac_active=_f(r["mac_active"]), mac_dpu_active=_f(r["mac_dpu_active"]),
                       ao_active=_f(r["ao_active"]), wd_active=_f(r["wd_active"]), wd_stalled=_f(r["wd_stalled"]),
                       sram_rd_bytes=beats(r["b130"]), sram_wr_bytes=beats(r["b135"]), ext_rd_bytes=beats(r["b386"]),
                       ext_wr_bytes=beats(r["b391"]), ext_rd_trans=_f(r["b384"]), traversal=r["traversal"], ofm_block=r["ofm_block"],
                       ofm_ublock=r["ofm_ublock"], kernels=s.get("n_kernels"), vela_npu=_f(s.get("vela_npu_cycles")),
                       vela_total=_f(s.get("vela_op_cycles")), status=r["verdict"]))
    for c, r in json.loads(SOURCES["stage4ao"].read_text())["configs"].items():
        out.append(passes_row(r.get("metrics") or {}, source="fi101_stage4ao/summary.json", stage="stage4ao", item=c,
                              level="operator", family="conv1x1 PartKernel", runner="driver", image="70090f1", ta=1, latency=500,
                              placement="ddr", status=r.get("verdict")))
    pl = json.loads(SOURCES["placement"].read_text())
    for side, place in (("a", "ddr"), ("b", "sram")):
        ev = {}
        for k, v in pl["compute"]["per_event"].items():
            ev[f"A_{k}"] = v[side]
        for k, v in pl["auxiliary"].items():
            ps, code = k.split("_")
            ev[f"{'A' if ps == 'pass1' else 'B'}_{code}"] = v[side]
        for k, v in pl["traffic"]["per_event"].items():
            ev[f"B_{k}"] = v[side]
        ev["A_35"] = pl["cost"]["per_pass"]["1"][side]
        out.append(passes_row(ev, source="stage4_placement/stage4p_summary.json", stage="stage4p", item=f"conv_base_{place}",
                              level="operator", family="conv1x1 PartKernel", runner="driver", image="70090f1", ta=1, latency=500,
                              placement=place, status=pl["outcome"] if isinstance(pl.get("outcome"), str) else "VALID"))
    for c, r in json.loads(SOURCES["stage4aoe"].read_text())["configs"].items():
        out.append(passes_row(r.get("metrics") or {}, source="fi101_stage4aoe/summary.json", stage="stage4aoe", item=c,
                              level="operator", family="elementwise", runner="driver", image="70090f1", ta=1, latency=500,
                              placement="ddr", status=r.get("verdict")))
    for c, r in json.loads(SOURCES["stage4wd"].read_text())["configs"].items():   # erratum: 4WD's own boots 402-409
        out.append(passes_row(r.get("metrics") or {}, source="fi101_stage4wd/summary.json", stage="stage4wd", item=c,
                              level="operator", family="conv1x1 PartKernel", runner="driver", image="70090f1", ta=1, latency=500,
                              placement="ddr", status=r.get("verdict")))
    return out


def load_graphs() -> list[dict]:
    out = []
    for r in _csv(SOURCES["e2a"]):
        out.append(row(source="fi101_stage6b/stage6be2a/vela_board_table.csv", stage=f"e2a_{r['group']}", item=r["shape"],
                       level="graph" if r["group"].startswith("A") else "operator",
                       family="A2 wrapper 1x1 DepthFirst" if r["group"].startswith("A") else "conv1x1 DepthFirst",
                       runner="driver", image=r["image"], ta=int(_f(r["ta_profile"]) or 0) or None, latency=500, placement="ddr",
                       npu_active=_f(r["board_npu_active"]), mac_active=_f(r["board_mac_active"]), ao_active=_f(r["board_ao_active"]),
                       wd_active=_f(r["board_wd_active"]), wd_stalled=_f(r["board_wd_stalled"]),
                       sram_rd_bytes=_f(r["board_sram_read_bytes"]), sram_wr_bytes=_f(r["board_sram_write_bytes"]),
                       ext_rd_bytes=_f(r["board_ext_read_bytes"]), ext_wr_bytes=_f(r["board_ext_write_bytes"]),
                       vela_compute=_f(r["vela_compute"]), vela_sram_ac=_f(r["vela_sram_ac"]), vela_dram_ac=_f(r["vela_dram_ac"]),
                       vela_total=_f(r["vela_total"]), status=r["status"]))
    for r in _csv(SOURCES["e2d"]):
        out.append(row(source="fi101_stage6b/stage6be2ea/trackB/e2d_table.csv", stage="e2d", item=r["cell"], level="graph",
                       family="A2 wrapper" if r["cell"].startswith("W1") else "conv1x1 DepthFirst", runner="driver", image=r["image"],
                       ta=1, latency=int(r["latency"]), placement=r["io_path"], npu_active=_f(r["npu"]), npu_range=_f(r["npu_range"]),
                       mac_active=_f(r["mac"]), mac_dpu_active=_f(r["dpu"]), ao_active=_f(r["ao"]), wd_active=_f(r["wd"]),
                       wd_stalled=_f(r["wd_stalled"]), sram_rd_bytes=beats(r["sram_rd_beats"]), sram_wr_bytes=beats(r["sram_wr_beats"]),
                       ext_rd_bytes=beats(r["ext_rd_beats"]), ext_wr_bytes=beats(r["ext_wr_beats"]), ext_rd_trans=_f(r["ext_rd_trans"]),
                       kernels=r["kernels"], vela_compute=_f(r["vela_npu"]), vela_sram_ac=_f(r["vela_sram"]),
                       vela_dram_ac=_f(r["vela_dram"]), vela_total=_f(r["vela_total"]), status="VALID"))
    for stage, src, img in (("e2eb", "e2eb", "70090f1/L1000"), ("e2ed", "e2ed", "14077be")):
        s = json.loads(SOURCES[src].read_text())
        for k, r in s["results"].items():
            if k == "REF" or r.get("status") != "VALID":
                continue
            m, t = r["metrics"], r["traffic"]
            cell, L = k.rsplit("-L", 1)
            out.append(row(source=f"{SOURCES[src].relative_to(REPO)}", stage=stage, item=cell, level="graph", family="A2 wrapper",
                           runner="driver", image=img, ta=1, latency=int(L), placement=cell, npu_active=m["npu_active"],
                           npu_range=m["npu_active_range"], mac_active=m["mac_active"], mac_dpu_active=m["mac_dpu_active"],
                           ao_active=m["ao_active"], wd_active=m["wd_active"], wd_stalled=m["wd_stalled"],
                           sram_rd_bytes=t["sram_rd_beats"] * 16, sram_wr_bytes=t["sram_wr_beats"] * 16,
                           ext_rd_bytes=t["ext_rd_beats"] * 16, ext_wr_bytes=t["ext_wr_beats"] * 16, ext_rd_trans=t["ext_rd_trans"],
                           vela_total=({500: 53052, 1000: 83142}[int(L)] if cell == "B0" else None), status="VALID"))
    return out


def integrate() -> list[dict]:
    return load_models() + load_operators() + load_graphs()


# ---- Phase 2: controlled pairs ----------------------------------------------------------------------------------------
PAIRS = [  # (id, key a, key b, variable)
    ("s4 conv Cin 16->15", "stage4:conv_base", "stage4:conv_cin15", "shape"),
    ("s4 conv Cout 96->95", "stage4:conv_base", "stage4:conv_cout95", "shape"),
    ("s4 dw C 144->143", "stage4:dw_base", "stage4:dw_c143", "shape"),
    ("s4 fc in 96->95", "stage4:fc_base", "stage4:fc_in95", "shape"),
    ("s4 fc out 288->287", "stage4:fc_base", "stage4:fc_out287", "shape"),
    ("4c2 Cin 16->32", "stage4c2:s4_conv_base", "stage4c2:s4c2_conv_cin32", "shape"),
    ("4c2 Cin 32->64", "stage4c2:s4c2_conv_cin32", "stage4c2:s4c2_conv_cin64", "shape"),
    ("4c2 Cin 64->128", "stage4c2:s4c2_conv_cin64", "stage4c2:s4c2_conv_cin128", "shape"),
    ("4k Cin16 1x1->3x3", "stage4k:s4_conv_base", "stage4k:s4k_conv3x3_cin16", "kernel"),
    ("4k Cin32 1x1->3x3", "stage4k:s4c2_conv_cin32", "stage4k:s4k_conv3x3_cin32", "kernel"),
    ("4k Cin48 1x1->3x3", "stage4k:s4c2_conv_cin48", "stage4k:s4k_conv3x3_cin48", "kernel"),
    ("4k Cin64 1x1->3x3", "stage4k:s4c2_conv_cin64", "stage4k:s4k_conv3x3_cin64", "kernel"),
    ("4ao OFM H24->H72", "stage4ao:s4ao_conv1x1_h24", "stage4ao:s4ao_conv1x1_h72", "shape"),
    ("4p placement DDR->SRAM", "stage4p:conv_base_ddr", "stage4p:conv_base_sram", "placement"),
    ("e2d W1 placement L500", "e2d:W1-P0", "e2d:W1-P1", "placement"),
    ("e2d W1-P1 latency", "e2d:W1-P1", "e2d:W1-P1:L1000", "latency"),
    ("e2d W0 placement L500", "e2d:W0-P0", "e2d:W0-P1", "placement"),
    ("e2eb IO placement L500", "e2eb:B0", "e2eb:B3", "placement"),
    ("e2eb IO placement L1000", "e2eb:B0:L1000", "e2eb:B3:L1000", "placement"),
    ("e2ed weight placement L500", "e2ed:B3", "e2ed:B3w", "placement"),
    ("e2ed weight placement L1000", "e2ed:B3:L1000", "e2ed:B3w:L1000", "placement"),
]


def _rel(a, b):
    return None if a in (None, 0) or b is None else (b - a) / a


def tags(a: dict, b: dict, variable: str) -> dict:
    """contract §3. Missing values never create a tag."""
    t = []
    d_mac = _rel(a["mac_active"], b["mac_active"])
    d_dpu = _rel(a["mac_dpu_active"], b["mac_dpu_active"])
    if (d_mac is not None and abs(d_mac) > TOL) or (d_dpu is not None and abs(d_dpu) > TOL):
        t.append("COMPUTE_COST_CHANGE")
    tot = lambda r, ks: None if any(r[k] is None for k in ks) else sum(r[k] for k in ks)
    rd = _rel(tot(a, ("sram_rd_bytes", "ext_rd_bytes")), tot(b, ("sram_rd_bytes", "ext_rd_bytes")))
    wr = _rel(tot(a, ("sram_wr_bytes", "ext_wr_bytes")), tot(b, ("sram_wr_bytes", "ext_wr_bytes")))
    tr = _rel(a["ext_rd_trans"], b["ext_rd_trans"])
    if any(x is not None and abs(x) > TOL for x in (rd, wr, tr)):
        t.append("DATA_TRANSFER_CHANGE")
    if variable in ("placement", "latency", "sram_budget"):
        t.append("MEMORY_SERVICE_CONDITION_CHANGE")
    if any(a[k] is not None and b[k] is not None and str(a[k]) != str(b[k]) for k in ("traversal", "ofm_block", "ofm_ublock", "kernels")):
        t.append("COMPILER_MAPPING_CHANGE")
    d_npu = None if a["npu_active"] is None or b["npu_active"] is None else b["npu_active"] - a["npu_active"]
    tol_npu = None if d_npu is None else max(TOL * a["npu_active"], (a["npu_range"] or 0) + (b["npu_range"] or 0))
    sig = d_npu is not None and abs(d_npu) > tol_npu
    if sig and d_mac is not None and abs(d_mac) <= TOL:
        t.append("PIPELINE_DEPENDENCY_CANDIDATE")
    if sig and not t:
        t.append("CAUSE_UNRESOLVED")
    return dict(tags=t, d_npu=d_npu, tol_npu=tol_npu, npu_significant=sig, d_mac=d_mac, d_dpu=d_dpu, d_read=rd, d_write=wr,
                d_ext_trans=tr)


def compare(rows: list[dict]) -> list[dict]:
    by = {r["key"]: r for r in rows}
    out = []
    for pid, ka, kb, var in PAIRS:
        a, b = by.get(ka), by.get(kb)
        if a is None or b is None:
            out.append(dict(pair=pid, a=ka, b=kb, variable=var, missing=[k for k, x in ((ka, a), (kb, b)) if x is None]))
            continue
        same_group = all(a[k] == b[k] for k in ("runner", "image", "ta")) or var in ("latency",)
        out.append(dict(pair=pid, a=ka, b=kb, variable=var, same_condition_group=same_group, npu_a=a["npu_active"],
                        npu_b=b["npu_active"], **tags(a, b, var)))
    return out


# ---- Phase 3: Vela fidelity -----------------------------------------------------------------------------------------
def direction(err: float) -> str:
    return "WITHIN_10PCT" if abs(err) <= 0.10 else ("UNDER_PREDICTS" if err > 0 else "OVER_PREDICTS")


def vela_table(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        for basis in ("vela_total", "vela_npu"):
            v = r[basis]
            if v and r["npu_active"]:
                err = (r["npu_active"] - v) / v
                out.append(dict(key=r["key"], stage=r["stage"], level=r["level"], family=r["family"], runner=r["runner"],
                                image=r["image"], latency=r["latency"], basis=basis, vela=v, board=r["npu_active"],
                                board_over_vela=r["npu_active"] / v, error=err, direction=direction(err)))
                break
    return out


# ---- Phase 4: selection -----------------------------------------------------------------------------------------------
def family_of_op(r: dict) -> str | None:
    op, k, trav, cin = r.get("npu_op") or "", r.get("kernel") or "", r.get("traversal") or "", _f(r.get("cin"))
    if op == "Conv2D" and k == "1x1" and trav == "PartKernel":
        return "F1"
    if op == "DepthwiseConv2D":
        return "F2"
    if op == "FullyConnected":
        return "F3"
    if op == "Conv2D" and k.startswith("1x") and int(k.split("x")[1]) >= 7:
        return "F4"
    if op == "Conv2D" and cin is not None and cin < 16 and k != "1x1":
        return "F5"
    return None


def family_shares(ops: list[dict]) -> dict:
    tot, fam = {}, {}
    for r in ops:
        n = _f(r.get("n_mac_tflite")) or 0
        tot[r["model"]] = tot.get(r["model"], 0) + n
        f = family_of_op(r)
        if f:
            fam.setdefault(f, {}).setdefault(r["model"], 0)
            fam[f][r["model"]] += n
    return {f: {m: v / tot[m] for m, v in d.items() if tot[m]} for f, d in fam.items()}


def representative(ops: list[dict], f: str, shares: dict) -> dict | None:
    if f not in shares or not shares[f]:
        return None
    model = max(sorted(shares[f]), key=lambda m: shares[f][m])
    cand = [r for r in ops if r["model"] == model and family_of_op(r) == f]
    return max(cand, key=lambda r: (_f(r.get("n_mac_tflite")) or 0, -int(r["tflite_op_index"])))


def control_variant(f: str, rep: dict) -> str | None:
    c = CONTROL[f]
    if c is None:
        return None
    cin = int(_f(rep["cin"]))
    return c[0] if cin % 16 else c[1]


def select_static(ops: list[dict]) -> dict:
    shares = family_shares(ops)
    res = {}
    for f in PRIORITY:
        rep = representative(ops, f, shares)
        mx = max(shares.get(f, {}).values() or [0])
        c1 = MEASURED_SHAPES[f] <= LOW_EVIDENCE_MAX
        c2 = mx >= IMPORTANCE_MIN
        c3 = rep is not None and (rep["traversal"], rep["kernel"], int(_f(rep["cin"])) % 16 == 0) not in MEASURED_KEYS[f]
        res[f] = dict(max_share=mx, shares=shares.get(f, {}), c1_low_evidence=c1, c2_importance=c2, c3_new=c3,
                      rep=None if rep is None else {k: rep[k] for k in ("model", "tflite_op_index", "kernel", "stride", "traversal",
                                                                          "cin", "cout", "npu_ofm_hwc", "ofm_block", "ofm_ublock",
                                                                          "n_mac_tflite")},
                      control=None if rep is None else control_variant(f, rep))
    return res


def specs(sel: dict) -> list[dict]:
    out = []
    for f in PRIORITY:
        s = sel[f]
        if not (s["c1_low_evidence"] and s["c2_importance"] and s["c3_new"]) or s["rep"] is None:
            continue
        base = dict(model=s["rep"]["model"], op_index=int(s["rep"]["tflite_op_index"]))
        out.append(dict(base, name=f"s6c_{f.lower()}_rep", family=f, variant=None))
        if s["control"]:
            out.append(dict(base, name=f"s6c_{f.lower()}_{s['control']}", family=f, variant=s["control"]))
    return out


def npu_row(fact: dict) -> dict | None:
    rows = fact.get("npu_rows") or []
    return rows[0] if len(rows) == 1 else None


def compile_checks(fact: dict, rep: dict | None) -> dict:
    """C4 for the representative (MAPPING_SAME with the in-model op), C5 for every shape."""
    r = npu_row(fact)
    c5 = dict(single_npu_op=r is not None, no_cpu=not fact.get("cpu_rows"), packed=fact.get("pack_rc") == 0,
              vela_values=r is not None and all(r.get(k) not in (None, "") for k in ("vela_op_cycles", "vela_npu_cycles", "sram_ac", "dram_ac")),
              fast_size=fact.get("pack_rc") == 0 and fact.get("fast_size", 1 << 30) <= LIMITS["fast_size"],
              arena_size=fact.get("pack_rc") == 0 and fact.get("arena_size", 1 << 30) <= LIMITS["arena_size"],
              model_region=fact.get("pack_rc") == 0 and fact.get("model_len", 1 << 30) + fact.get("arena_size", 0) <= LIMITS["model_region"])
    mapping = None
    if r is not None and rep is not None:
        mapping = "MAPPING_SAME" if all(str(r.get(k)) == str(rep.get(k)) for k in ("traversal", "ofm_block", "ofm_ublock")) \
            else "COMPILER_MAPPING_CHANGE"
    return dict(c5=c5, c5_ok=all(c5.values()), mapping=mapping)


def select_final(sel: dict, facts: list[dict]) -> dict:
    by = {x["name"]: x for x in facts}
    chosen, shapes = [], []
    for f in PRIORITY:
        s = sel[f]
        s["selected"] = False
        if not (s["c1_low_evidence"] and s["c2_importance"] and s["c3_new"]) or s["rep"] is None:
            continue
        rep_fact = by.get(f"s6c_{f.lower()}_rep", {})
        chk = compile_checks(rep_fact, s["rep"])
        s["rep_check"] = chk
        s["c4_controllable"] = chk["mapping"] == "MAPPING_SAME"
        s["c5_analyzable"] = chk["c5_ok"]
        if s["control"]:
            cf = by.get(f"s6c_{f.lower()}_{s['control']}", {})
            cc = compile_checks(cf, None)
            r0, r1 = npu_row(rep_fact), npu_row(cf)
            cc["traversal_same"] = r0 is not None and r1 is not None and r0.get("traversal") == r1.get("traversal")
            cc["mapping_vs_rep"] = None if r0 is None or r1 is None else (
                "MAPPING_SAME" if all(r0.get(k) == r1.get(k) for k in ("traversal", "ofm_block", "ofm_ublock")) else "COMPILER_MAPPING_CHANGE")
            s["control_check"] = cc
        if s["c4_controllable"] and s["c5_analyzable"]:
            s["selected"] = True
            chosen.append(f)
            shapes.append(f"s6c_{f.lower()}_rep")
            if s["control"] and s["control_check"]["c5_ok"]:
                shapes.append(f"s6c_{f.lower()}_{s['control']}")
    # budget: REF + shapes <= MAX_BOOTS; drop from the end of PRIORITY
    dropped = []
    while 1 + len(shapes) > MAX_BOOTS and chosen:
        f = chosen.pop()
        dropped.append(f)
        shapes = [x for x in shapes if not x.startswith(f"s6c_{f.lower()}_")]
    return dict(families=sel, selected=chosen, dropped_for_budget=dropped, shapes=shapes, boots=1 + len(shapes))


# ---- Phase 1: unit inventory (documented sources) --------------------------------------------------------------------
UNIT_INVENTORY = {
    "MAC/DPU": dict(
        secured=["1x1 DepthFirst: H1-UC MAC_ACTIVE PROSPECTIVE_SUPPORT (6B-B, E1-R, E2D/E2E; 768 not a cap: G09 1024)",
                 "1x1 PartKernel Cin 16/32: 384 MAC/MAC-active cycle, DPU/MAC 0.5 (4C-2, 4K)",
                 "3x3 PartKernel Cin 16-64: 768 nominal (4K), PROPORTIONAL_TO_CIN",
                 "DW 3x3 C144: 128 MAC/MAC-active cycle (Stage 4); C rounded up to 16 (4C-1)",
                 "FC 96->288: 256 MAC/MAC-active cycle, MAC/NPU 1.15 % (Stage 4)"],
        missing=["1x1 PartKernel at Cin < 16 and large spatial", "DW at C < 16, 5x5, other resolutions",
                 "FC beyond one shape (out 287 not reproduced, RUN ranges 7-9 %)", "1D large-kernel PartKernel (wav2letter)",
                 "first Conv Cin 1 (kws 10x4)"],
        issues=[]),
    "AO": dict(
        secured=["Conv INT8 output ~15.6 elem/AO cycle (4AO), DW ~15.85", "ADD/MUL N/16, ADD->MUL 2N/16 (4AO-E)",
                 "model AO/NPU: yolo 46 %, vww4 27 % (Stage 1)"],
        missing=["LUT / TANH / LOGISTIC (compiled only)", "activation NONE vs RELU (INCONCLUSIVE)"],
        issues=["AO-1: ABS N/32 unexplained"]),
    "WD": dict(
        secured=["WD_ACTIVE follows spatial OFM blocks (BLOCK_LIKE, 4WD)", "not proportional to encoded bytes (CONSTANT)",
                 "WD_STALLED moves with memory condition (placement, EXT latency: E2D, E2E-B/D)"],
        missing=["WD vs other units' backpressure separation", "FC weight-decode rate"],
        issues=["WD-1: FC 34.7-42 encoded B/WD cycle > documented 32", "WD-2"]),
    "DMA/AXI": dict(
        secured=["SRAM/EXT read/write beats, transactions per model (Stage 3) and per isolated / A2 config",
                 "per-port EXT0/EXT1 beats/trans (640/642/656/658) VERIFIED", "387 ext_rd_tran_req_stalled VERIFIED",
                 "channel-filtered read traffic (rd_weights/ifm/mem2mem, Stage 3 legacy)",
                 "graph IO vs weight path EXT latency sensitivity (E2E-B/D)"],
        missing=["physical port bandwidth limit under FI101 clocks (no AXI utilisation computed)",
                 "axi_latency 160-166 (TRM only)", "outstanding-limit stall 398 INCONSISTENT",
                 "PMCAXI_CHAN in the driver runner (not implemented)"],
        issues=["B3w slower at L500 (E2E-D, unresolved)"]),
}


def unit_inventory_md() -> str:
    lines = ["# Unit별 확보·미확보 지표 (Stage 6C-0, 근거: results 인벤토리)", "",
             "AXI 이용률: 포트 물리 한도와 클럭 조건이 검증되지 않아 계산하지 않는다 (`AXI_UTILIZATION_NOT_COMPUTED`). "
             "바이트 ÷ NPU_ACTIVE는 관측 평균 처리율(B/cycle)이다.", ""]
    for u, d in UNIT_INVENTORY.items():
        lines += [f"## {u}", "", "확보:"] + [f"- {x}" for x in d["secured"]] + ["", "미확보:"] + [f"- {x}" for x in d["missing"]]
        if d["issues"]:
            lines += ["", "Open issue:"] + [f"- {x}" for x in d["issues"]]
        lines.append("")
    return "\n".join(lines)


# ---- run -----------------------------------------------------------------------------------------------------------------
def write_csv(p: pathlib.Path, rows: list[dict], fields=None):
    fields = fields or sorted({k for r in rows for k in r})
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def run(out: str, facts_path: str) -> dict:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    rows = integrate()
    write_csv(o / "integrated.csv", rows, FIELDS)
    cmp = compare(rows)
    write_csv(o / "comparisons.csv", cmp)
    vt = vela_table(rows)
    write_csv(o / "vela_fidelity.csv", vt)
    (o / "unit_inventory.md").write_text(unit_inventory_md())
    sel = select_static(_csv(SOURCES["ops"]))
    facts = json.loads(pathlib.Path(facts_path).read_text())
    fin = select_final(sel, facts)
    (o / "selection.json").write_text(json.dumps(fin, indent=1, sort_keys=True, default=str))
    summary = dict(contract="evidence/stage6c0/contract.md", rows=len(rows), pairs=len(cmp), vela_rows=len(vt),
                   selected=fin["selected"], shapes=fin["shapes"], boots=fin["boots"])
    (o / "stage6c0_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "specs":
        sp = specs(select_static(_csv(SOURCES["ops"])))
        pathlib.Path(sys.argv[2]).write_text(json.dumps(sp, indent=1))
        print(json.dumps(sp, indent=1))
    elif cmd == "run":
        print(json.dumps(run(sys.argv[2], sys.argv[3]), indent=1))
    else:
        raise SystemExit(__doc__)
