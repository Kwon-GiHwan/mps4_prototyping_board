#!/usr/bin/env python3
"""Stage 6B-R (results/fi101_stage6b/stage6br/analysis_contract.md): board-free POSTHOC_EXPLANATORY analysis of the MAC
counters and the Vela error. Reads committed evidence only; writes the CSVs of the analysis.

  python3 stage6br.py run <out dir>
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6b as S  # noqa: E402

REPO = S.REPO
K4 = REPO / "results" / "fi101_stage4k"
C2 = REPO / "results" / "fi101_stage4c2"
BB = REPO / "results" / "fi101_stage6b" / "stage6bb"
RA = REPO / "evidence" / "stage6b" / "revision_a" / "compiled"
WL = REPO / "evidence" / "stage6b" / "stage6bb" / "workloads"
RAW = REPO / "evidence" / "stage6b" / "stage6bb" / "raw" / "evsweep_s6bb_run" / "conds"
VELA = REPO / "results" / "fi101_stage6b" / "stage6br" / "facts" / "vela_summary_full.json"
STAGE4_1X1 = {"s4_conv_base": K4, "s4c2_conv_cin32": K4, "s4c2_conv_cin40": K4, "s4c2_conv_cin48": K4,
              "s4c2_conv_cin64": K4, "s4c2_conv_cin128": C2}
BEAT = 16


def up(x: int, m: int) -> int:
    return math.ceil(x / m) * m


def hwc(s: str) -> list[int]:
    return [int(v) for v in s.split("x")]


# ---- cases ---------------------------------------------------------------------------------------------------------------
def read_csv(p: pathlib.Path) -> list[dict]:
    with open(p) as f:
        return list(csv.DictReader(f))


def stage4_cases() -> list[dict]:
    out = []
    t4 = {r["config"]: r for r in read_csv(K4 / "stage4k_table.csv")}
    t2 = {r["config"]: r for r in read_csv(C2 / "stage4c2_table.csv")}
    for cfg, d in STAGE4_1X1.items():
        st = json.loads((d / "static.json").read_text())[cfg]
        row = (t4 if d == K4 else t2)[cfg]
        ok = row["output"] == "PASS_EXACT" and (row.get("gate_c") == "PASS" if d == K4 else row["verdict"] == "VALID")
        status = "VALID" if ok else "INVALID"
        out.append(dict(case=f"stage4:{cfg}", source="Stage4K" if d == K4 else "Stage4C2", status=status, cin=st["cin"], cout=96,
                        ofm=[24, 24, 96], ublock=hwc(st["ofm_ublock"]), ifm_block_depth=hwc(st["ifm_block"])[2],
                        ofm_block=st["ofm_block"], traversal=st["traversal"],
                        kernels=[[24, 24, k["ofm_slice"]] for k in st["kernels"]], n_mac=24 * 24 * 96 * st["cin"],
                        mac=float(row["mac_active"]), dpu=float(row["mac_dpu_active"]), memory="UNKNOWN (not in the Stage 4K static record)"))
    return out


def stage6bb_cases() -> list[dict]:
    out = []
    man = json.loads((WL / "stage6bb_manifest.json").read_text())
    sh = {r["config"]: r for r in read_csv(BB / "shapes.csv")}
    for cfg, m in man.items():
        r = sh[cfg]
        if m["kind"] == "reference":
            st = json.loads((K4 / "static.json").read_text())["s4c2_conv_cin48"]
            kernels = [[24, 24, k["ofm_slice"]] for k in st["kernels"]]
        else:
            ks = json.loads((RA / f"s6b_{m['group'].lower()}.ra.json").read_text())["forms"]["A2"]["conv_kernels"]
            kernels = [[k["ofm_height_m1"] + 1, k["ofm_width_m1"] + 1, k["ofm_depth_m1"] + 1] for k in ks]
        out.append(dict(case=f"6bb:{m['group']}", source="Stage6B-B", status=r["status"], cin=m["cin"], cout=m["cout"],
                        ofm=hwc(m["ofm_hwc"]), ublock=hwc(m["ofm_ublock"]), ifm_block_depth=hwc(m["ifm_block"])[2],
                        ofm_block=m["ofm_block"], traversal=m["traversal"], kernels=kernels, n_mac=m["n_mac"],
                        mac=float(r["mac_active"]), dpu=float(r["mac_dpu_active"]),
                        memory=f"{m.get('ifm_memory', 'UNKNOWN')}/{m.get('ofm_memory', 'UNKNOWN')}"))
    return out


# ---- MAC hypotheses (POSTHOC_EXPLANATORY) ----------------------------------------------------------------------------------
def ublocks(kernels: list, ub: list, pad_spatial: bool = True) -> float:
    f = (lambda a, b: math.ceil(a / b)) if pad_spatial else (lambda a, b: a / b)
    return sum(f(h, ub[0]) * f(w, ub[1]) * math.ceil(d / ub[2]) for h, w, d in kernels)


def chunks(cin: int, depth: int) -> list[int]:
    return [depth] * (cin // depth) + ([cin % depth] if cin % depth else [])


def mac_chunk(x: int, min32: bool = True) -> float:
    return max(32 if min32 else 0, up(x, 16)) / 8


def mac_per_ublock(cin: int, depth: int, chunked: bool = True, min32: bool = True) -> float:
    return sum(mac_chunk(x, min32) for x in (chunks(cin, depth) if chunked else [cin]))


def h1_uc(c: dict, pad_spatial=True, per_kernel=True, chunked=True, min32=True) -> float:
    ks = c["kernels"] if per_kernel else [[c["ofm"][0], c["ofm"][1], c["cout"]]]
    return ublocks(ks, c["ublock"], pad_spatial) * mac_per_ublock(c["cin"], c["ifm_block_depth"], chunked, min32)


MAC_HYP = {
    "H1-G": lambda c: up(c["ofm"][0], c["ublock"][0]) * up(c["ofm"][1], c["ublock"][1]) * up(c["cin"], 32) * up(c["cout"], 16) / 1024,
    "H1-C16": lambda c: c["ofm"][0] * c["ofm"][1] * up(c["cin"], 16) * up(c["cout"], 16) / 1024,
    "H1-U8": lambda c: ublocks(c["kernels"], c["ublock"]) * math.ceil(c["cin"] / 8),
    "H1-U16": lambda c: ublocks(c["kernels"], c["ublock"]) * up(c["cin"], 16) / 8,
    "H1-UC": h1_uc,
}
ABLATIONS = {
    "H1-UC without spatial ublock padding": lambda c: h1_uc(c, pad_spatial=False),
    "H1-UC with whole Cout instead of per-kernel slices": lambda c: h1_uc(c, per_kernel=False),
    "H1-UC without IFM-depth chunks": lambda c: h1_uc(c, chunked=False),
    "H1-UC without the 32 minimum": lambda c: h1_uc(c, min32=False),
}


def dpu_chunk_pw(x: int) -> float:
    return up(x, 8) / 8 if x <= 8 else up(x, 16) / 8


DPU_HYP = {
    "D-U16": lambda c: ublocks(c["kernels"], c["ublock"]) * sum(up(x, 16) / 8 for x in chunks(c["cin"], c["ifm_block_depth"])),
    "D-U8": lambda c: ublocks(c["kernels"], c["ublock"]) * sum(up(x, 8) / 8 for x in chunks(c["cin"], c["ifm_block_depth"])),
    "D-PW": lambda c: ublocks(c["kernels"], c["ublock"]) * sum(dpu_chunk_pw(x) for x in chunks(c["cin"], c["ifm_block_depth"])),
}


def ratio_dr(c: dict) -> float:
    """The instruction's D-R: DPU/MAC = ceil8(Cin) / ceil32(Cin)."""
    return up(c["cin"], 8) / up(c["cin"], 32)


def verdict(cases: list[dict], pred, key: str, competitors: list | None = None) -> dict:
    official = [c for c in cases if c["status"] == "VALID"]
    miss = [c["case"] for c in official if pred(c) != c[key]]
    # cases that separate this hypothesis from its closest competitor (the one it differs from least often)
    split = min((sum(p(c) != pred(c) for c in official) for p in competitors), default=0) if competitors else 0
    if miss:
        v = "CONTRADICTED"
    elif competitors is not None and split <= 1:
        v = "INSUFFICIENT_EVIDENCE"
    else:
        v = "CONSISTENT_WITH_OBSERVATIONS"
    expl = [c for c in cases if c["status"] != "VALID"]
    return dict(verdict=v, n_official=len(official), n_exact=len(official) - len(miss), not_exact=miss,
                cases_splitting_competitors=split,
                exploratory_exact=sum(pred(c) == c[key] for c in expl), exploratory_total=len(expl))


def mac_rows(cases: list[dict]) -> list[dict]:
    rows = []
    for c in cases:
        r = dict(case=c["case"], source=c["source"], status=c["status"], label="EXPLORATORY" if c["status"] != "VALID" else "OFFICIAL",
                 cin=c["cin"], cout=c["cout"], ofm="x".join(map(str, c["ofm"])), ofm_block=c["ofm_block"],
                 ublock="x".join(map(str, c["ublock"])), ifm_block_depth=c["ifm_block_depth"], traversal=c["traversal"],
                 kernels=" + ".join("x".join(map(str, k)) for k in c["kernels"]), n_kernels=len(c["kernels"]),
                 memory=c["memory"], n_mac=c["n_mac"], ofm_ublocks=ublocks(c["kernels"], c["ublock"]),
                 cin_chunks="+".join(map(str, chunks(c["cin"], c["ifm_block_depth"]))),
                 mac_per_ublock_measured=c["mac"] / ublocks(c["kernels"], c["ublock"]),
                 dpu_per_ublock_measured=c["dpu"] / ublocks(c["kernels"], c["ublock"]),
                 padded_mac_uc=h1_uc(c) * 1024, mac_active=c["mac"], mac_dpu_active=c["dpu"],
                 n_mac_per_mac_active=c["n_mac"] / c["mac"], dpu_over_mac=c["dpu"] / c["mac"], dr_ratio=ratio_dr(c))
        for k, f in {**MAC_HYP, **ABLATIONS}.items():
            r[f"pred[{k}]"] = f(c)
            r[f"resid[{k}]"] = c["mac"] - f(c)
        for k, f in DPU_HYP.items():
            r[f"pred_dpu[{k}]"] = f(c)
        rows.append(r)
    return rows


# ---- Vela ------------------------------------------------------------------------------------------------------------------
def vela_rows() -> tuple[list[dict], dict]:
    vs = json.loads(VELA.read_text())
    sh = {r["config"]: r for r in read_csv(BB / "shapes.csv")}
    man = json.loads((WL / "stage6bb_manifest.json").read_text())
    rows, checks = [], dict(op_is_max=[], total_is_sum=[])
    for cfg, m in man.items():
        if m["kind"] != "A2":
            continue
        g, r, s = m["group"], sh[cfg], vs[m["group"]]["summary"]
        rec = json.loads((RA / f"s6b_{g.lower()}.ra.json").read_text())["forms"]["A2"]
        num = lambda v: int(v) if str(v).strip().lstrip("-").isdigit() else 0
        for row in rec["rows"]:
            if row.get("cms_offsets"):
                checks["op_is_max"].append(num(row["vela_op_cycles"]) == max(num(row["vela_npu_cycles"]), num(row["sram_ac"]), num(row["dram_ac"])))
        total = int(s["cycles_total"])
        checks["total_is_sum"].append(total == sum(num(x["vela_op_cycles"]) for x in rec["rows"]))
        valid = r["status"] == "VALID"
        npu = float(r["npu_active"]) if valid else None
        b = lambda k: float(r[k]) * BEAT if r.get(k) not in ("", None) else None
        rows.append(dict(
            group=g, status=r["status"], label="MEASURED+STATIC" if valid else "NOT_COMPARABLE (UNSTABLE)",
            vela_sha_equals_measured=vs[g]["vela_sha256"] == m["vela_sha256"],
            vela_cycles_total=total, vela_cycles_npu=int(s["cycles_npu"]), vela_cycles_sram_access=int(s["cycles_sram_access"]),
            vela_cycles_dram_access=int(s["cycles_dram_access"]), board_npu_active=npu,
            error_pct=(npu - total) / total * 100 if valid else None, abs_error_pct=abs(npu - total) / total * 100 if valid else None,
            npu_over_vela_npu=npu / int(s["cycles_npu"]) if valid else None,
            vela_sram_read_bytes=int(s["sram_feature_map_read_bytes"]) + int(s["sram_weight_read_bytes"]),
            vela_sram_write_bytes=int(s["sram_feature_map_write_bytes"]) + int(s["sram_weight_write_bytes"]),
            vela_dram_read_bytes=int(s["dram_feature_map_read_bytes"]) + int(s["dram_weight_read_bytes"]),
            vela_dram_write_bytes=int(s["dram_feature_map_write_bytes"]) + int(s["dram_weight_write_bytes"]),
            vela_dram_weight_read_bytes=int(s["dram_weight_read_bytes"]), weight_bytes=m["weight_bytes"],
            board_sram_read_bytes=b("passB_130"), board_sram_write_bytes=b("passB_135"),
            board_ext_read_bytes=b("passB_386"), board_ext_write_bytes=b("passB_391"),
            mac_active=float(r["mac_active"]), mac_activity=float(r["mac_activity"]) if r["mac_activity"] else None,
            macs_per_mac_active=float(r["macs_per_mac_active"]) if r["macs_per_mac_active"] else None,
            wd_stalled=float(r["wd_stalled"]) if r["wd_stalled"] else None, ao_active=float(r["ao_active"]) if r["ao_active"] else None))
    return rows, {k: dict(n=len(v), all_true=all(v)) for k, v in checks.items()}


def ranks(v: list) -> list[float]:
    """Average ranks (ties share the mean of their positions)."""
    order = sorted(v)
    return [sum(i + 1 for i, a in enumerate(order) if a == x) / order.count(x) for x in v]


def spearman(x: list, y: list) -> float | None:
    """Pearson correlation of the average ranks; None when either side is constant."""
    a, b = ranks(x), ranks(y)
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa, sb = sum((p - ma) ** 2 for p in a), sum((q - mb) ** 2 for q in b)
    if not sa or not sb:
        return None
    return sum((p - ma) * (q - mb) for p, q in zip(a, b)) / math.sqrt(sa * sb)


# ---- UNSTABLE diagnostics ---------------------------------------------------------------------------------------------------
def run_rows() -> list[dict]:
    out = []
    man = json.loads((WL / "stage6bb_manifest.json").read_text())
    sh = {r["config"]: r["status"] for r in read_csv(BB / "shapes.csv")}
    for cfg in man:
        runs = {}
        for r in read_csv(RAW / cfg / "wfe" / "runs.csv"):
            k = (int(r["set_id"]), int(r["rep"]))
            runs.setdefault(k, dict(config=cfg, group=man[cfg]["group"], status=sh[cfg], set_id=k[0], rep=k[1],
                                    warmup=k[1] == 1, window_cycles=int(r["window_cycles"])))[f"ev{r['ev_type']}"] = int(r["event_value"])
        out += [runs[k] for k in sorted(runs)]
    return out


def unstable_summary(rr: list[dict]) -> list[dict]:
    out = []
    for cfg in dict.fromkeys(r["config"] for r in rr):
        rs = [r for r in rr if r["config"] == cfg and not r["warmup"]]
        a = [r for r in rs if r["set_id"] == 1]
        b = [r for r in rs if r["set_id"] == 2]
        med = statistics.median(r["ev35"] for r in a)
        rng = lambda xs, k: max(x[k] for x in xs) - min(x[k] for x in xs)
        corr = lambda xs, k: spearman([x["ev35"] for x in xs], [x[k] for x in xs])
        out.append(dict(config=cfg, group=rs[0]["group"], status=rs[0]["status"],
                        npu_a_runs=" ".join(str(r["ev35"]) for r in a), npu_b_runs=" ".join(str(r["ev35"]) for r in b),
                        npu_a_median=med, npu_a_range=rng(a, "ev35"), npu_a_range_pct=rng(a, "ev35") / med * 100,
                        npu_b_range=rng(b, "ev35"), mac_range=rng(a, "ev48"), dpu_range=rng(a, "ev51"),
                        ao_range=rng(a, "ev64"), wd_range=rng(a, "ev80"), wd_stalled_range=rng(a, "ev81"),
                        ext_rd_beat_range=rng(b, "ev386"), ext_rd_trans_range=rng(b, "ev384"), sram_rd_beat_range=rng(b, "ev130"),
                        ext_wr_beat_range=rng(b, "ev391"),
                        rho_npu_wd_stalled_A=corr(a, "ev81"), rho_npu_ao_A=corr(a, "ev64"), rho_npu_wd_A=corr(a, "ev80"),
                        rho_npu_ext_rd_trans_B=corr(b, "ev384"),
                        window_minus_npu_A=statistics.median(r["window_cycles"] - r["ev35"] for r in a)))
    return out


def run(out: str) -> dict:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    cases = stage4_cases() + stage6bb_cases()
    S.write_csv(o / "mac_padding_analysis.csv", mac_rows(cases))
    every_mac = {**MAC_HYP, **ABLATIONS}
    ver = {k: verdict(cases, f, "mac", [g for j, g in every_mac.items() if j != k]) for k, f in every_mac.items()}
    dver = {k: verdict(cases, f, "dpu", [g for j, g in DPU_HYP.items() if j != k]) for k, f in DPU_HYP.items()}
    dver["D-R (DPU/MAC ratio)"] = verdict([dict(c, dpu_over_mac=c["dpu"] / c["mac"]) for c in cases], ratio_dr, "dpu_over_mac")
    vr, vchecks = vela_rows()
    S.write_csv(o / "vela_fidelity_analysis.csv", vr)
    valid = [r for r in vr if r["status"] == "VALID"]
    desc = {k: spearman([r["error_pct"] for r in valid], [r[k] for r in valid])
            for k in ("macs_per_mac_active", "mac_activity", "vela_cycles_total", "wd_stalled", "ao_active", "vela_cycles_dram_access")}
    rr = run_rows()
    S.write_csv(o / "unstable_runs.csv", rr)
    S.write_csv(o / "unstable_summary.csv", unstable_summary(rr))
    summary = dict(label="POSTHOC_EXPLANATORY", mac_hypotheses=ver, dpu_hypotheses=dver, vela_cost_model_checks=vchecks,
                   vela_error=dict(n=len(valid), min=min(r["error_pct"] for r in valid), max=max(r["error_pct"] for r in valid),
                                   median=statistics.median(r["error_pct"] for r in valid)),
                   vela_error_spearman_descriptive=desc)
    (o / "stage6br_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    if sys.argv[1] == "run":
        print(json.dumps(run(sys.argv[2]), indent=1))
