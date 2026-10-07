"""Build the H13_HANDOFF package (copies + correspondence tables only; no new measurement, no judgement change).

    python3 make_handoff.py <out_dir>

Layout: INDEX.md, MANIFEST.csv, reports/, results/, analysis/, evidence/. Every copied file keeps its original
name; MANIFEST.csv records source path, last commit touching it, and SHA-256. Derived tables are generated from
results.jsonl / h13_results.json / Vela dumps in this directory and are marked DERIVED in the manifest.
"""
import csv, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
AM = HERE.parent
OUT = Path(sys.argv[1]).resolve()
KEYS = ("npu_total_cycles", "npu_active_cycles", "npu_idle_cycles", "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats",
        "axi0_rd_beats", "axi0_wr_beats", "axi1_rd_beats")
TA = ("EXT_RLATENCY", "EXT_WLATENCY", "EXT_MAXR", "EXT_MAXW", "EXT_MAXRW", "EXT_PULSE_ON", "EXT_PULSE_OFF", "EXT_BWCAP",
      "SRAM_RLATENCY", "SRAM_WLATENCY", "SRAM_MAXR", "SRAM_MAXW", "SRAM_MAXRW", "SRAM_PULSE_ON", "SRAM_PULSE_OFF", "SRAM_BWCAP")
manifest = []


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def commit_of(p):
    try:
        return subprocess.run(["git", "log", "-1", "--format=%h", "--", str(p)], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "untracked"
    except Exception:
        return "?"


def put(src, dest_dir, kind="COPY", note=""):
    src = Path(src); d = OUT / dest_dir; d.mkdir(parents=True, exist_ok=True)
    dst = d / src.name
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        for f in sorted(dst.rglob("*")):
            if f.is_file():
                manifest.append({"handoff_path": str(f.relative_to(OUT)), "source": str((src / f.relative_to(dst)).relative_to(ROOT)) if str(src).startswith(str(ROOT)) else str(src), "kind": kind, "commit": commit_of(src), "sha256": sha(f), "note": note})
    else:
        shutil.copy2(src, dst)
        manifest.append({"handoff_path": str(dst.relative_to(OUT)), "source": str(src.relative_to(ROOT)) if str(src).startswith(str(ROOT)) else str(src), "kind": kind, "commit": commit_of(src), "sha256": sha(dst), "note": note})
    return dst


def write_csv(rel, rows, note=""):
    p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("");
    else:
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    manifest.append({"handoff_path": rel, "source": "DERIVED from results.jsonl / h13_results.json / vela dumps", "kind": "DERIVED", "commit": commit_of(HERE / "results.jsonl"), "sha256": sha(p), "note": note})


# ---------------------------------------------------------------- 1. reports / analysis (copies)
for f in ("H13_RESULTS.md", "README.md" if False else None, ):
    pass
put(HERE / "H13_RESULTS.md", "reports")
put(ROOT / "docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md", "reports")
put(ROOT / "docs/superpowers/plans/2026-09-14-h1-h3-verification-GO.md", "reports")
put(AM / "manager_review_20260914_v7_directive.md", "reports")
put(AM / "manager_log.md", "reports")
put(AM / "A10_revised_hypotheses.md", "reports")
put(AM / "A8_x4_timing_adapter_sweep.md", "reports", note="X4 (pre-H13) latency sweep")
put(AM / "A5_effective_bandwidth.md", "reports")
put(AM / "A6_model_structure.md", "reports")
put(AM / "A9_s4_closure.md", "reports")
put(AM / "README.md", "reports")
for f in ("h13_analyze.py", "test_h13_analyze.py", "h13_sweep.py", "h3_blocks.py", "gen_h3_models.py", "gen_h2b_model.py", "h13_quantum.py", "collect.sh"):
    put(HERE / f, "analysis")
put(AM / "x4/x4_analyze.py", "analysis", note="frozen-counter reference used by h13_analyze (G2)")
for f in ("h13_results.json", "h3_blocks.csv", "h3_manifest.json", "h2b_manifest.json", "ta_parameters.csv", "results.jsonl", "results_cachecheck.jsonl", "quantum.jsonl"):
    put(HERE / f, "results", note="raw per-run records" if f.endswith("jsonl") else "")
put(HERE / "h3_synthetic_cells.json", "results", note="synthetic cell definitions incl. arms")
for f in ("vela_fvp_trend_agreement.csv", "vela_matrix.csv", "canonical_cells.csv"):
    put(ROOT / "docs/paper/raw_data_report/source_data/4_1_estimation_accuracy" / f, "results/vela_fvp_existing", note="pre-existing Vela-FVP comparison (real models only)")
put(ROOT / "docs/paper/raw_data_report/source_data/4_2_error_sources/U85_256_512_DIFFERENTIAL.csv", "results/vela_fvp_existing", note="pre-existing")

# ---------------------------------------------------------------- 2. per-run table
recs = [json.loads(l) for l in open(HERE / "results.jsonl") if l.strip()]
runs = []
for r in recs:
    m = r.get("measurement") or {}
    d = r.get("defines", {})
    row = {"experiment": r.get("experiment"), "cell_id": r["cell_id"], "arm": r["arm"], "rep": r.get("rep"), "status": r.get("status"),
           "is_base": r.get("is_base"), "profile": r.get("profile")}
    row.update({k: m.get(k) for k in KEYS})
    row.update({k: d.get(k) for k in TA})
    a = r.get("artifact", {})
    row.update({"vela_sha256": a.get("vela_sha256"), "vela_equals_frozen": (a.get("vela_sha256") == a.get("frozen_vela_sha256")) if a.get("frozen_vela_sha256") else "n/a",
                "axf_sha256": a.get("axf_sha256"), "axf_equals_frozen": (a.get("axf_sha256") == a.get("frozen_axf_sha256")) if a.get("frozen_axf_sha256") else "n/a",
                "header_matches_request": r.get("header_matches_request"), "uart_file": Path(r["uart_file"]).name if r.get("uart_file") else None})
    v = r.get("verify")
    if v:
        row.update({"verify_status": v.get("status"), "verify_pmu_equals_stock": (v.get("measurement") == m) if v.get("measurement") else None, "verify_uart": Path(v["uart_file"]).name if v.get("uart_file") else None})
    if str(r.get("status", "")).startswith("BUILD_FAILED"):
        row["build_fail_log_tail"] = (r.get("log") or "")[-300:].replace("\n", " | ")
    runs.append(row)
write_csv("results/runs_all.csv", runs, note="every stock run (3 reps per arm) with the 16 applied TA values and gate facts")

# ---------------------------------------------------------------- 3. H3 table + judgements (TOTAL vs ACTIVE)
res = json.load(open(HERE / "h13_results.json"))
meta = {m["model"]: m for m in json.load(open(HERE / "h3_manifest.json"))}
blocks = {(r["model"], r["cond"], int(r["mac"])): r for r in csv.DictReader(open(HERE / "h3_blocks.csv"))}
per = {}
for r in recs:
    if r["cell_id"].startswith("h3_") and "measurement" in r:
        model = r["cell_id"].split("__")[0]; mac = int(r["cell_id"].split("ethos-u85-")[1].split("_")[0])
        cond = "syscfgMid" if r["cell_id"].endswith("__syscfgMid") else r["arm"]
        per.setdefault((model, cond, mac), []).append(r)


def vela_layer(model, cond, mac, suffix):
    d = HERE / "vela" / ("%s__SSE-320__ethos-u85-%d%s__%s" % (model, mac, "__syscfgMid" if cond == "syscfgMid" else "", "base" if cond == "syscfgMid" else cond))
    for f in d.glob("*per-layer.csv"):
        rows = list(csv.DictReader(open(f)))
        if rows:
            return rows[0], d
    return {}, d


h3rows = []
for (model, cond, mac), rs in sorted(per.items()):
    m = meta[model]; r0 = rs[0]; d = r0["defines"]; b = blocks.get((model, cond, mac), {})
    lay, vdir = vela_layer(model, cond, mac, "")
    k = 1 if m["op"] == "conv1x1" else 3
    row = {"model": model, "op": m["op"], "kernel": "%dx%d" % (k, k), "stride": 1, "padding": "same", "IFM_HWC": "%dx%dx%d" % (m["H"], m["W"], m["C"]),
           "OFM_HWC": "%dx%dx%d" % (m["H"], m["W"], m["C"]), "area": m["area"], "model_sha256": m["sha256"], "weights_sha256": m["weights_sha256"],
           "mac": mac, "cond": cond, "vela_system_config": "Ethos_U85_SYS_DRAM_Mid_512" if (cond == "syscfgMid" or mac == 512) else "Ethos_U85_SYS_DRAM_Low",
           "vela_mac_count": lay.get("MAC Count"), "vela_est_cycles": lay.get("Op Cycles"), "vela_util_pct": lay.get("Util% (MAC)"),
           "ofm_block_HWC": b.get("ofm_block_HWC"), "ifm_block": b.get("ifm_block"), "ublock_HWC": b.get("ublock_HWC"), "traversal": b.get("traversal"),
           "H_mod_blockH": b.get("H_mod_bH"), "W_mod_blockW": b.get("W_mod_bW"), "n_blocks": b.get("n_blocks"), "vela_artifact_sha256": r0["artifact"]["vela_sha256"],
           "EXT_RLATENCY": d["EXT_RLATENCY"], "EXT_WLATENCY": d["EXT_WLATENCY"], "EXT_BWCAP": d["EXT_BWCAP"], "EXT_MAXR_requested": d["EXT_MAXR"],
           "EXT_MAXR_applied": 0 if d["EXT_MAXR"] >= 64 else d["EXT_MAXR"], "SRAM_RLATENCY": d["SRAM_RLATENCY"], "SRAM_WLATENCY": d["SRAM_WLATENCY"],
           "EXT_PULSE": "%d/%d" % (d["EXT_PULSE_ON"], d["EXT_PULSE_OFF"])}
    for i, rr in enumerate(sorted(rs, key=lambda x: x["rep"])[:3], 1):
        mm = rr["measurement"]
        row["TOTAL_rep%d" % i] = mm["npu_total_cycles"]; row["ACTIVE_rep%d" % i] = mm["npu_active_cycles"]; row["IDLE_rep%d" % i] = mm["npu_idle_cycles"]
    mm = rs[0]["measurement"]
    row.update({"sram_rd_beats": mm["sram_rd_beats"], "sram_wr_beats": mm["sram_wr_beats"], "ext_rd_beats": mm["ext_rd_beats"], "ext_wr_beats": mm["ext_wr_beats"],
                "reps_identical": len({tuple(x["measurement"].get(k) for k in KEYS) for x in rs}) == 1,
                "verify_output_sha256": (rs[0].get("verify") or {}).get("dump_sha256")})
    h3rows.append(row)
# TA equality across MACs per (model, cond)
by_mc = {}
for row in h3rows:
    by_mc.setdefault((row["model"], row["cond"]), {})[row["mac"]] = row
for (model, cond), d in by_mc.items():
    if 256 in d and 512 in d:
        a, b = d[256], d[512]
        same = all(a[k] == b[k] for k in ("EXT_RLATENCY", "EXT_WLATENCY", "EXT_BWCAP", "SRAM_RLATENCY", "SRAM_WLATENCY", "EXT_PULSE"))
        maxr_same = a["EXT_MAXR_applied"] == b["EXT_MAXR_applied"]
        rt = b["TOTAL_rep1"] / a["TOTAL_rep1"]; ra = b["ACTIVE_rep1"] / a["ACTIVE_rep1"]
        for x in (a, b):
            x["ta_latency_bwcap_same_across_mac"] = same; x["ta_maxr_same_across_mac"] = maxr_same
            x["r_total_512_over_256"] = round(rt, 4); x["r_active_512_over_256"] = round(ra, 4)
            x["reversal_total"] = rt > 1.0; x["reversal_active"] = ra > 1.0
            x["scaling_efficiency_total"] = round(1.0 / (2 * rt), 4); x["scaling_efficiency_active"] = round(1.0 / (2 * ra), 4)
write_csv("results/h3_models_conditions_metrics.csv", h3rows,
          note="51 models x MAC x condition; r = C512/C256 (same model, same condition); scaling_efficiency = 1/(2r); EXT_MAXR_applied = requested & 0x3F")


def med(xs):
    xs = sorted(xs); n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def judge(metric):
    r = {}
    for (model, cond), d in by_mc.items():
        if 256 in d and 512 in d:
            r[(model, cond)] = d[256]["r_total_512_over_256"] if metric == "TOTAL" else d[256]["r_active_512_over_256"]
    spread, out = {}, []
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        for area in (36, 64, 256):
            for cond in ("base", "relaxed"):
                xs = [v for (mo, co), v in r.items() if co == cond and meta[mo]["op"] == op and meta[mo]["area"] == area]
                if len(xs) >= 2:
                    spread[(op, area, cond)] = (max(xs) - min(xs), med(xs), len(xs))
    for (op, area, cond), (sp, md, n) in spread.items():
        if cond == "base":
            out.append({"metric": metric, "group": "%s|%d|base" % (op, area), "test": "SHAPE_EFFECT", "rule": "max(r)-min(r) >= 0.10 within same area & op", "value": round(sp, 4), "n": n, "median_r": round(md, 4), "holds": sp >= 0.10})
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        meds = [spread.get((op, a, "base"), (None, None, 0))[1] for a in (36, 64, 256)]
        if all(x is not None for x in meds):
            out.append({"metric": metric, "group": op, "test": "AREA_EFFECT", "rule": "median r decreases 36>64>256 and r(256) <= r(36)-0.10", "value": "%.3f/%.3f/%.3f" % tuple(meds), "n": 3, "median_r": "", "holds": meds[0] > meds[1] > meds[2] and meds[2] <= meds[0] - 0.10})
    m36 = [spread.get((op, 36, "base"), (None, None, 0))[1] for op in ("conv1x1", "conv3x3", "dw3x3")]
    if all(x is not None for x in m36):
        out.append({"metric": metric, "group": "area36 conv1x1/conv3x3/dw3x3", "test": "TYPE_DEPENDENT", "rule": "max-min of the three area-36 medians >= 0.10", "value": round(max(m36) - min(m36), 4), "n": 3, "median_r": "%.3f/%.3f/%.3f" % tuple(m36), "holds": max(m36) - min(m36) >= 0.10})
    for op in ("conv1x1", "conv3x3", "dw3x3"):
        b, rl = spread.get((op, 36, "base")), spread.get((op, 36, "relaxed"))
        if b and rl:
            out.append({"metric": metric, "group": op + "|36", "test": "MEMORY_SHAPE_INTERACTION", "rule": "relaxed spread < 0.5 x base spread", "value": "base %.3f -> relaxed %.3f" % (b[0], rl[0]), "n": b[2], "median_r": "base %.3f -> relaxed %.3f" % (b[1], rl[1]), "holds": b[0] > 0 and rl[0] < 0.5 * b[0]})
    return out


jt, ja = judge("TOTAL"), judge("ACTIVE")
jrows = []
for a, b in zip(jt, ja):
    assert a["group"] == b["group"] and a["test"] == b["test"]
    jrows.append({"group": a["group"], "test": a["test"], "rule": a["rule"], "TOTAL_value": a["value"], "TOTAL_median_r": a["median_r"], "TOTAL_holds (preregistered)": a["holds"],
                  "ACTIVE_value": b["value"], "ACTIVE_median_r": b["median_r"], "ACTIVE_holds (post hoc)": b["holds"], "agree": a["holds"] == b["holds"]})
write_csv("results/h3_judgements_total_vs_active.csv", jrows, note="preregistered TOTAL-based outcomes vs post-hoc ACTIVE recomputation with identical rules")

cases = []
for (model, cond), d in sorted(by_mc.items()):
    if 256 not in d or 512 not in d:
        continue
    a, b = d[256], d[512]; op = meta[model]["op"]; area = meta[model]["area"]
    tag = []
    if op == "conv1x1" and area == 36 and cond == "base":
        tag.append("A: conv1x1 area36 base -- reversal" if a["reversal_total"] else "A': conv1x1 area36 base -- no reversal")
    if op == "conv1x1" and area == 36 and cond == "relaxed":
        tag.append("B: same model under relaxed TA (reversal gone: %s)" % ("yes" if not a["reversal_total"] else "no"))
    if op == "conv3x3" and area == 36:
        tag.append("C: conv3x3 area36 %s (shape spread base 0.355 -> relaxed 0.049)" % cond)
    if op == "dw3x3" and area == 36:
        tag.append("D: dw3x3 area36 %s (shape spread base 0.000 -> relaxed 0.492)" % cond)
    if op == "dw3x3" and area == 64 and cond == "base":
        tag.append("E: dw3x3 area64 -- SHAPE_EFFECT holds on TOTAL (0.110) not on ACTIVE (0.029)")
    if tag:
        cases.append({"case": " ; ".join(tag), "model": model, "cond": cond, "TOTAL_256": a["TOTAL_rep1"], "TOTAL_512": b["TOTAL_rep1"], "r_total": a["r_total_512_over_256"],
                      "ACTIVE_256": a["ACTIVE_rep1"], "ACTIVE_512": b["ACTIVE_rep1"], "r_active": a["r_active_512_over_256"],
                      "block_256": a["ofm_block_HWC"], "block_512": b["ofm_block_HWC"], "ublock_256": a["ublock_HWC"], "ublock_512": b["ublock_HWC"],
                      "EXT_RLATENCY_256/512": "%s/%s" % (a["EXT_RLATENCY"], b["EXT_RLATENCY"]), "EXT_MAXR_applied_256/512": "%s/%s" % (a["EXT_MAXR_applied"], b["EXT_MAXR_applied"])})
write_csv("results/h3_flagged_cases.csv", cases, note="cases requested in the handoff spec (A reversal, B relaxed, C conv3x3 shape, D dw3x3 shape, E TOTAL/ACTIVE disagreement)")

# ---------------------------------------------------------------- 4. H2-B-X
h2 = []
for r in recs:
    if r.get("experiment") == "H2BX" and "measurement" in r:
        cell = r["cell_id"]; mac = int(cell.split("ethos-u85-")[1].split("__")[0]); mode = cell.rsplit("__", 1)[1]
        vd = HERE / "vela" / (cell + "__base")
        txt = (vd / "vela_verbose.txt").read_text(errors="replace") if (vd / "vela_verbose.txt").exists() else ""
        alloc = re.findall(r"Allocation, memory (\w+), usage mask: ([\w|]+)\n.*?\nAllocation Peak Tensor Size: (\d+) bytes", txt, re.S)
        ro = re.search(r"read-only NPU tensors:.*?Allocation Peak Tensor Size: (\d+) bytes", txt, re.S)
        cfg = re.search(r"OFM Block=\[([\d, ]+)\], IFM Block=\[([\d, ]+)\], OFM UBlock=\[([\d, ]+)\] Traversal=(\w+)", txt)
        enc = re.search(r"Encoded Weights = (\d+) bytes", txt)
        summ = {}
        for f in vd.glob("*summary*.csv"):
            rows = list(csv.DictReader(open(f)))
            if rows:
                summ = rows[0]
        m = r["measurement"]
        h2.append({"cell_id": cell, "mac": mac, "memory_mode": summ.get("memory_mode", mode), "rep": r["rep"], "TOTAL": m["npu_total_cycles"], "ACTIVE": m["npu_active_cycles"], "IDLE": m["npu_idle_cycles"],
                   "sram_rd_beats": m["sram_rd_beats"], "sram_wr_beats": m["sram_wr_beats"], "ext_rd_beats": m["ext_rd_beats"], "ext_wr_beats": m["ext_wr_beats"],
                   "vela_weights_storage_area": summ.get("weights_storage_area"), "vela_feature_map_storage_area": summ.get("feature_map_storage_area"), "vela_arena_cache_size_KiB": summ.get("arena_cache_size"),
                   "vela_allocations": " ; ".join("%s:%s:%s B" % a for a in alloc), "vela_readonly_peak_bytes": ro.group(1) if ro else None, "encoded_weights_bytes": enc.group(1) if enc else None,
                   "ofm_block": cfg.group(1) if cfg else None, "ifm_block": cfg.group(2) if cfg else None, "ublock": cfg.group(3) if cfg else None, "traversal": cfg.group(4) if cfg else None,
                   "vela_artifact_sha256": r["artifact"]["vela_sha256"], "verify_output_sha256": (r.get("verify") or {}).get("dump_sha256"), "EXT_RLATENCY": r["defines"]["EXT_RLATENCY"], "EXT_MAXR_requested": r["defines"]["EXT_MAXR"]})
shared = {(x["mac"]): x["TOTAL"] for x in h2 if x["memory_mode"] == "Shared_Sram" and x["rep"] == 1}
for x in h2:
    x["pct_vs_Shared_same_mac"] = round(100.0 * (x["TOTAL"] / shared[x["mac"]] - 1), 2) if x["mac"] in shared else None
write_csv("results/h2bx_placement_schedule_measurements.csv", h2, note="per rep; pct = (TOTAL/TOTAL_Shared - 1)*100 within the same MAC; allocations parsed from --verbose-allocation")

# ---------------------------------------------------------------- 5. H1 / H2-A / SRAM / DIAG per-arm tables
def arm_rows(pred):
    seen, out = set(), []
    for r in recs:
        if "measurement" not in r or not pred(r) or (r["cell_id"], r["arm"]) in seen:
            continue
        seen.add((r["cell_id"], r["arm"]))
        reps = [x for x in recs if x["cell_id"] == r["cell_id"] and x["arm"] == r["arm"] and "measurement" in x]
        d = r["defines"]; m = r["measurement"]
        row = {"experiment": r["experiment"], "cell_id": r["cell_id"], "arm": r["arm"], "memory_mode": "Dedicated_Sram" if "u85" in r["cell_id"] else ("Shared_Sram" if "u55" in r["cell_id"] else "Dedicated_Sram"),
               "vela_artifact_sha256": r["artifact"]["vela_sha256"], "vela_equals_frozen": r["artifact"]["vela_sha256"] == r["artifact"].get("frozen_vela_sha256"), "is_base": r["is_base"], "profile": r["profile"],
               "n_reps": len(reps), "reps_identical": len({tuple(x["measurement"].get(k) for k in KEYS) for x in reps}) == 1,
               "TOTAL": m["npu_total_cycles"], "ACTIVE": m["npu_active_cycles"], "IDLE": m["npu_idle_cycles"]}
        row.update({k: m.get(k) for k in ("sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats", "axi0_rd_beats", "axi0_wr_beats", "axi1_rd_beats")})
        row.update({k: d[k] for k in TA}); row["EXT_MAXR_applied"] = 0 if d["EXT_MAXR"] >= 64 else d["EXT_MAXR"]
        row["verify_output_sha256"] = (r.get("verify") or {}).get("dump_sha256")
        out.append(row)
    return out
write_csv("results/h1_arms_rnnoise.csv", arm_rows(lambda r: r["experiment"] in ("H1A", "H1B", "H1Ca")), note="H1-A read/write sweeps, H1-B MAXR, H1-C(a) 375/750, A3 zero-latency MAXR")
write_csv("results/h1cb_arms_kws_ad.csv", arm_rows(lambda r: r["experiment"] == "H1Cb"))
write_csv("results/h2a_arms_wav2letter.csv", arm_rows(lambda r: r["experiment"] == "H2A"))
write_csv("results/sramcap_arms.csv", arm_rows(lambda r: r["experiment"] == "SRAMCAP"))
diag = arm_rows(lambda r: r["experiment"] == "DIAG")
for r in recs:
    if r.get("experiment") == "DIAG" and r.get("status") == "FAILURE_TIMEOUT":
        diag.append({"experiment": "DIAG", "cell_id": r["cell_id"], "arm": r["arm"], "n_reps": 1, "TOTAL": None, "status": "FAILURE_TIMEOUT (3600 s)", **{k: r["defines"][k] for k in TA}})
write_csv("results/diag_arms.csv", diag, note="A5 diagnostic arms incl. the four EXT_PULSE_OFF=0 timeouts")
q = [json.loads(l) for l in open(HERE / "quantum.jsonl")]
write_csv("results/diag_quantum.csv", [{"quantum": x["quantum"], "rep": x["rep"], "TOTAL": x["measurement"]["npu_total_cycles"], "ACTIVE": x["measurement"]["npu_active_cycles"], "IDLE": x["measurement"]["npu_idle_cycles"], "axf_equals_frozen": x["axf_equals_frozen"], "fvp_cmd": x["fvp_cmd"]} for x in q])
# grid check over all runs
grid = {}
for r in recs:
    if "measurement" in r and r["measurement"].get("npu_total_cycles"):
        fam = r["cell_id"].split("__")[0]; grid.setdefault(fam, set()).add(r["measurement"]["npu_total_cycles"] % 1000)
write_csv("results/diag_total_mod1000_by_model.csv", [{"model_family": k, "TOTAL_mod_1000_residues": ";".join(str(x) for x in sorted(v)), "n_distinct": len(v)} for k, v in sorted(grid.items())], note="residue of TOTAL modulo 1000 over every stock run")

# preregistered-formula summary (from h13_results.json)
form = []
for mac, v in res["H1A"].items():
    if mac == "cross_mac":
        form.append({"experiment": "H1A", "unit": "all MAC", "quantity": "cross-MAC", "formula": "max(k_r)/min(k_r) <= 1.15 -> SIMILAR", "value": v}); continue
    form.append({"experiment": "H1A", "unit": mac, "quantity": "k_r", "formula": "[C(R=1000,W=250) - C(R=0,W=250)] / 1000", "value": v["k_r"], "outcome": v["outcome"]})
    form.append({"experiment": "H1A", "unit": mac, "quantity": "k_w", "formula": "[C(R=500,W=500) - C(R=500,W=0)] / 500", "value": v["k_w"], "outcome": "READ_DOMINANT if k_w <= 0.2 k_r"})
    form.append({"experiment": "H1A", "unit": mac, "quantity": "additivity", "formula": "pred C(0,0) = C(0,250) - [C(500,250) - C(500,0)]; |pred - obs| <= 5% obs", "value": "pred %s obs %s" % (v["C00_pred"], v["C00_obs"]), "outcome": v["additivity"]})
for mac, v in res["H1B"].items():
    form.append({"experiment": "H1B", "unit": mac, "quantity": "s(MAXR)", "formula": "[C(R=1000) - C(R=250)] / 750 per MAXR; REDUCES if monotone non-increasing and s(63|0) <= 0.8 s(1)", "value": json.dumps(v["s"]), "outcome": v["outcome"] + " ; " + str(v["maxr64"])})
for mac, v in res["H1Ca"].items():
    form.append({"experiment": "H1Ca", "unit": mac, "quantity": "375/750 prediction", "formula": "M1 = linear fit on X4 {0,250,500,1000} +-5%; M2 = piecewise interpolation +-2%; both L must pass", "value": "obs %s M1 %s M2 %s" % (v["observed"], v["M1_pred"], v["M2_pred"]), "outcome": v["outcome"]})
for cell, v in res["H1Cb"].items():
    if cell == "generalisation":
        form.append({"experiment": "H1Cb", "unit": "KWS+AD", "quantity": "generalisation", "formula": "all 4 LATENCY_SENSITIVE -> GENERALISES", "value": v}); continue
    form.append({"experiment": "H1Cb", "unit": cell, "quantity": "rho", "formula": "C(R=1000)/C(R=0) >= 1.10 -> LATENCY_SENSITIVE", "value": v["rho"], "outcome": v["outcome"]})
for mac, v in res["H2A"].items():
    form.append({"experiment": "H2A", "unit": mac, "quantity": "cap effect", "formula": "CONSTRAINED if C(2x|0) <= 0.90 C(1x) at base latency; NOT_BINDING if all within 5% and achieved < 0.9 nominal; nominal = BWCAP*16/(pulse_on+pulse_off)", "value": json.dumps({k: x["cycles"] for k, x in v["rows"].items()}), "outcome": v["outcome"] + " ; " + str(v["interaction"])})
for cell, v in res["SRAMCAP"].items():
    form.append({"experiment": "SRAMCAP", "unit": cell, "quantity": "cap effect", "formula": "LOWERING_SLOWS if C(2000) >= 1.10 C(4000); CONSTRAINED if C(8000|0) <= 0.90 C(4000)", "value": json.dumps({k: x["cycles"] for k, x in v["rows"].items()}), "outcome": v["outcome"]})
write_csv("results/judgement_formulas_and_values.csv", form, note="formulas as preregistered in the plan; values from h13_results.json")

# ---------------------------------------------------------------- 6. evidence
put(HERE / "vela", "evidence", note="Vela --verbose-schedule/--verbose-performance dumps for every synthetic and H2-B-X cell (per arm)")
put(HERE / "verify_build", "evidence", note="verify-build patch (guarded blocks only), originals and digests")
ev = OUT / "evidence" / "uart_representative"; ev.mkdir(parents=True, exist_ok=True)
want = ["rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125__R1.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__r0_w0__R1.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__maxr1_r250_w125__R1.txt",
        "rnnoise_INT8__SSE-320__ethos-u85-512__r500_w250__R1.txt", "kws_micronet_m__SSE-320__ethos-u85-256__r250_w125__R1.txt",
        "h3_conv1x1_1x36_c128__SSE-320__ethos-u85-256__base__R1.txt", "h3_conv1x1_1x36_c128__SSE-320__ethos-u85-512__base__R1.txt",
        "h3_conv1x1_1x36_c128__SSE-320__ethos-u85-256__relaxed__R1.txt", "h3_conv1x1_1x36_c128__SSE-320__ethos-u85-512__relaxed__R1.txt",
        "h3_conv1x1_36x1_c128__SSE-320__ethos-u85-256__base__R1.txt", "h3_dw3x3_1x36_c128__SSE-320__ethos-u85-512__base__R1.txt",
        "rnnoise_INT8__SSE-320__ethos-u85-256__r137_w125__R1.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125_eon2000_eoff500__R1.txt",
        "rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125_soff0__R1.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125_eoff0__R1.txt",
        "rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125_eoff0_soff0__R1.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__r0_w0_eoff0_soff0__R1.txt",
        "kws_micronet_m__SSE-320__ethos-u85-256__r250_w125_eoff0__R1.txt", "wav2letter_pruned_int8__SSE-320__ethos-u85-512__bw3750_r500_w250__R1.txt",
        "wav2letter_pruned_int8__SSE-320__ethos-u85-512__bw0_r500_w250__R1.txt"]
want += ["h2b_w2l_conv7_250__SSE-320__ethos-u85-%d__%s__base__R1.txt" % (m, md) for m in (512, 256) for md in ("Shared", "SramOnly", "Dedicated")]
for f in want:
    p = HERE / "uart" / f
    if p.exists():
        put(p, "evidence/uart_representative", note="stock-build UART")
vv = OUT / "evidence" / "verify_dumps"; vv.mkdir(exist_ok=True)
for f in ["rnnoise_INT8__SSE-320__ethos-u85-256__r250_w125.txt", "rnnoise_INT8__SSE-320__ethos-u85-256__r0_w0.txt"] + ["h2b_w2l_conv7_250__SSE-320__ethos-u85-%d__%s__base.txt" % (m, md) for m in (512, 256) for md in ("Shared", "SramOnly", "Dedicated")]:
    p = HERE / "verify" / f
    if p.exists():
        put(p, "evidence/verify_dumps", note="verify-build UART with input/output tensor hex dump")
ex = Path("/tmp/timing_adapter_excerpt.txt")
if ex.exists():
    dst = OUT / "evidence" / "timing_adapter_driver_excerpt.txt"; shutil.copy2(ex, dst)
    manifest.append({"handoff_path": "evidence/timing_adapter_driver_excerpt.txt", "source": "server: /opt/arm/ml-embedded-evaluation-kit/dependencies/core-platform/drivers/timing_adapter/{src/timing_adapter.c lines 1-110, include/timing_adapter.h lines 40-70}, ta_config_u85_sys_dram_mid.cmake EXT_MAXR/MAXW; MLEK commit b2c0bb2, core-platform commit 02d0290", "kind": "COPY(excerpt)", "commit": "n/a", "sha256": sha(dst), "note": "TA_MAXR_MASK 0x3F and ta_set_maxr(): 64 & 0x3F = 0"})
for f in ("run_S1.log", "run_S1b.log", "run_S2.log", "run_S3.log", "run_S3d.log", "run_S4.log", "run_S4c.log", "run_S5.log", "run_S5c.log", "run_cachecheck.log"):
    if (HERE / f).exists():
        put(HERE / f, "evidence/run_logs")

# ---------------------------------------------------------------- 7. INDEX + MANIFEST
head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
n_ok = sum(1 for r in recs if r.get("status") == "SUCCESS")
index = f"""# H13_HANDOFF — H13 검증 캠페인 전달 자료 (생성 기준 커밋 {head}, 2026-09-15)

복사·대응표 작성만 수행. 새 측정·빌드·판정 기준 변경 없음. 논문 PDF와의 비교 없음. 원본 파일은 수정하지 않았다.

## 기준 커밋과 최신 결과 파일
- 결과 보고서: `reports/H13_RESULTS.md` (섹션 0–8; §8a 요인표, §8b 가설별 답)
- 계획서(사전 판정 기준·375/750 예측값 고정, amendment A1–A7, 종료 기록): `reports/2026-09-14-h1-h3-verification-plan.md`
- GO 전문: `reports/2026-09-14-h1-h3-verification-GO.md` · 매니저 지시·교환: `reports/manager_review_20260914_v7_directive.md`, `reports/manager_log.md`
- 판정에 실제 사용한 분석기: `analysis/h13_analyze.py` (fixtures `analysis/test_h13_analyze.py`), 출력 `results/h13_results.json`
- 원시 레코드: `results/results.jsonl` (모든 stock 실행, 검증 빌드 블록 포함), `results/runs_all.csv` (평탄화)
- 파일별 경로·커밋·SHA-256: `MANIFEST.csv` (kind = COPY / COPY(excerpt) / DERIVED)

## 각 실험의 실행 범위와 완료 상태 (stock 실행 SUCCESS {n_ok}건)
| 단계 | 실험 | 범위 | 상태 |
|---|---|---|---|
| S1 | H1-A 읽기/쓰기 분리 · H1-B MAXR · H1-C(a) 375/750 · H1-C(b) KWS/AD · A3 지연0×MAXR | RNNoise U85 256/512/1024/2048, KWS·AD U85 256/512, 90 arm | 완료, 게이트 전부 통과 |
| S2 | H2-A EXT BWCAP×지연 · SRAM BWCAP | Wav2Letter U85 512/256 16 arm · KWS/AD U55-256·U65-512 16 arm | 완료 |
| S3 | H3 합성 형상 | 51 모델 × 256/512 × base(+relaxed 면적 36, +syscfgMid 1×1 면적 36), 165 arm | 완료 (33 arm은 GitHub 504로 1회 재실행, A6) |
| S4 | H2-B(원계획) / H2-B-X(탐색) | 대표 레이어 × 3 memory mode × 2 MAC, 6 arm | H2-B NOT_TRIGGERED · H2-B-X 완료 |
| S5/A7 | 진단: 격자 기원 · FVP quantum | RNNoise 256 7 arm(4 timeout) + quantum 4×2 | 완료, 판정값 없음 |

## 사전 판정 / 탐색 실험 / 사후 진단의 구분
- 사전 판정(계획서 §1–§7의 식·임계값, 측정 전 고정): H1-A/B/C, H2-A, SRAMCAP, H3의 TOTAL 기준 결과값. `results/judgement_formulas_and_values.csv`, `results/h3_judgements_total_vs_active.csv`의 TOTAL 열.
- 탐색 실험(판정값 없음): H2-B-X (계획서 A4), A3 지연0×MAXR (A3).
- 사후 진단(POST_HOC, 판정을 바꾸지 않음): A5/A7 격자 진단, ACTIVE 기반 재검 (`h3_judgements_total_vs_active.csv`의 ACTIVE 열).

## TOTAL·ACTIVE 판정 불일치 (`results/h3_judgements_total_vs_active.csv`, agree=False 행)
- TOTAL 성립·ACTIVE 불성립: `MEMORY_SHAPE_INTERACTION` conv1x1|36 (spread 0.463→0.132 vs 0.402→0.226), `SHAPE_EFFECT` dw3x3|64 (0.110 vs 0.029).
- TOTAL 불성립·ACTIVE 성립: `AREA_EFFECT` conv1x1 (1.165/0.910/0.922 vs 1.020/0.931/0.913), `AREA_EFFECT` dw3x3 (1.000/1.055/0.800 vs 1.053/1.045/0.777).
- 그 외 항목은 일치. 사전 판정은 TOTAL 기준으로 유지하고 네 항목을 병기한다(H13_RESULTS §6c 정정 단락).

## H3 표 읽는 법 (`results/h3_models_conditions_metrics.csv`)
- 한 행 = 모델 × MAC × 조건. TOTAL/ACTIVE/IDLE은 반복 3회 각각(모두 동일, `reps_identical`). r = C512/C256(같은 모델·조건), 확장 효율 = 1/(2r).
- `cond=base`: 각 MAC의 MLEK 기본 프로파일 — 256은 low(EXT 지연 250/125, BWCAP 2344, MAXR 24), 512는 mid(500/250, 3750, MAXR 64→적용 0=무제한). **MAC 간 TA가 다르다** (`ta_latency_bwcap_same_across_mac=False`).
- `cond=relaxed`: EXT 지연 0/0, EXT_BWCAP 0, SRAM 지연 0/0. 지연·BWCAP은 MAC 간 동일하지만 **EXT_MAXR 적용값은 256=24, 512=무제한으로 여전히 다르다**(`ta_maxr_same_across_mac=False`); pulse는 동일(4000/1000). H1-B에서 RNNoise 256은 MAXR ≥16에서 포화했지만 합성 모델에 대해서는 확인하지 않았다.
- `cond=syscfgMid`: 256 MAC을 Vela `Ethos_U85_SYS_DRAM_Mid_512` 가정으로 컴파일한 대조군(TA는 base와 동일). 512 쪽은 base와 같은 산출물.
- block·ublock·traversal은 Vela `--verbose-schedule`에서, MAC 수·추정 사이클은 per-layer CSV에서 가져왔다(`evidence/vela/<cell>__<arm>/`). "block이 형상에 맞지 않는다"는 해석은 `ofm_block_HWC` 열(예: 36×1의 256 block 20x2x48)에 근거한 **서술**이며 매핑 메커니즘 자체는 가설이다.
- **통제 한계**: 형상마다 양자화 calibration이 따로 됐다(`gen_h3_models.py` seed = 1000+H·1000+W; `weights_sha256`는 float 가중치 해시) → 입력 zp·출력 scale이 형상마다 다르다. relaxed에서도 EXT_MAXR 적용값(24 vs 무제한)과 EXT_MAXW(12 vs 32)가 MAC 간 다르다. "순수 형상 효과"로 확정하지 않는다(H13_RESULTS §6b′).
- 쟁점 사례 바로 찾기: `results/h3_flagged_cases.csv` (A 역전 / A′ 비역전 / B 완화 후 소멸 / C 3×3 형상 차이 감소 / D DW 형상 차이 증가 / E TOTAL·ACTIVE 불일치).

## H2-B-X 읽는 법 (`results/h2bx_placement_schedule_measurements.csv`)
- 추출 모델은 원본 Wav2Letter flatbuffer의 op 15를 텐서·양자화·가중치/bias 버퍼째 복사한 것(`results/h2b_manifest.json`: 원본 실행 IFM→OFM 재생이 바이트 동일, `ofm_identical_to_original=true`, 가중치 sha 동일).
- 배치는 Vela 요약의 `weights_storage_area`/`feature_map_storage_area`와 `--verbose-allocation` 결과(`vela_allocations`)로 확인한다. Sram_Only에서 Vela는 const 영역을 'On-chip Flash'로 표기하지만(로그: "Changing const_mem_area from Sram to OnChipFlash. This will use the same characteristics as Sram") 측정에서 EXT beat는 0이고 가중치 읽기가 SRAM beat로 잡힌다. **Shared_Sram ↔ Sram_Only는 가중치(read-only) 배치만 다르고 feature map은 둘 다 SRAM**; Dedicated_Sram은 가중치와 feature map이 모두 DRAM(512는 SRAM staging 0 B, 256은 SRAM staging 137.5 KiB 사용)이므로 여러 텐서의 배치가 함께 다른 비교다.
- 스케줄 동일의 근거: 세 모드의 `ofm_block/ifm_block/ublock/traversal`이 같음(표의 열, 원본은 `evidence/vela/h2b_*`). 집계 beat 동일의 근거: 표의 beat 열(Dedicated 512 EXT 56,343/4,377 = Sram_Only 512 SRAM 56,343/4,377). Shared_Sram의 SRAM 쓰기 21,586은 Sram_Only의 4,377과 비교한 값이며 차이 ≈17,200 beat는 EXT 읽기 17,260 beat(가중치 276 KB / 16 B)와 대응한다.
- `pct_vs_Shared_same_mac` = (TOTAL / TOTAL_Shared − 1) × 100, 같은 MAC 안에서.
- 256 MAC의 Sram_Only는 encoded weight 657,952 B(다른 두 모드 276,080 B)로 컴파일된 가중치 표현이 다르다. 512는 275,344 / 276,240 B로 거의 같다. Shared↔Sram_Only는 "배치 + 동반된 컴파일 결과"의 효과이고, Dedicated↔Sram_Only(512)는 가중치와 feature map이 함께 옮겨진 비교다.

## H1·H2-A·SRAM 읽는 법
- arm 표: `results/h1_arms_rnnoise.csv`, `h1cb_arms_kws_ad.csv`, `h2a_arms_wav2letter.csv`, `sramcap_arms.csv` — 각 arm의 16개 TA 적용값, `EXT_MAXR_applied`(요청값 & 0x3F; 소스 근거 `evidence/timing_adapter_driver_excerpt.txt`), Vela 산출물 SHA(동결과 동일 여부), 반복 동일 여부, TOTAL/ACTIVE/IDLE/beat.
- 식·검사 지점·허용오차·결과값: `results/judgement_formulas_and_values.csv`. 고정 MAC에서의 민감도(k_r, k_w, s, ρ)와 MAC 간 비교(cross-MAC 1.15, r)는 열로 구분된다.
- H1-A 가산성의 지표 의존(POST_HOC): ACTIVE로 같은 식을 쓰면 256은 −4.5%(통과), 512는 +8.9%(실패). 256 `NON_ADDITIVE`는 지표 의존, 512는 두 지표 모두 비가산.
- "MAXR 16 이상 변화 없음"의 실제 표: 256은 16/63/64/0 모두 동일, 512는 16(34,086/106,086)과 63·64·0(32,086/99,086)이 다르다 — 512는 63 이상에서 동일.

## TOTAL 격자 진단 (`results/diag_arms.csv`, `diag_quantum.csv`, `diag_total_mod1000_by_model.csv`)
- 관측 범위: 모든 stock 실행의 TOTAL % 1000이 모델군별 단일 값(RNNoise 86, KWS/AD/Wav2Letter/합성 68, U55 RNNoise 59, U55 KWS/AD 50). ACTIVE는 그렇지 않다.
- 진단 결과: 읽기 지연 137, EXT pulse 2000/500, SRAM_PULSE_OFF 0, FVP `-Q` 1000/100/10 어디에서도 잔여 불변. 확인된 사실 = "TOTAL이 1,000 단위로 양자화되고 ACTIVE는 아님". 추정(미확인) = 기원이 CPU/드라이버/모델 측 정지 시점. 하드웨어 PMU 해상도와는 다른 문제.
- EXT_PULSE_OFF=0 네 arm: `FAILURE_TIMEOUT`(3,600 s), UART는 `evidence/uart_representative/*eoff0*`.
- "16–33%"는 격자 간격 1,000 ÷ 소형 모델 TOTAL(6,068 → 16.5%, 3,068 → 32.6%)로, 격자 간격의 상대 크기이지 검증된 오차 범위가 아니다. 큰 모델(≥10^5)에서는 ≤1%.
- 진단으로 낮춘 항목: RNNoise C(0,0)의 "정확한 5,000 간격"(ACTIVE로는 20,172/15,087/10,521/10,839로 등간격 아님), 위 TOTAL·ACTIVE 불일치 네 판정.

## Vela–FVP 비교 (기존 자료만, `results/vela_fvp_existing/`)
- 실제 모델(7종 × 3 NPU)의 기존 비교: `vela_fvp_trend_agreement.csv`(포화 판정 일치, 증분 등급 일치, 순위 rho), `vela_matrix.csv`, `canonical_cells.csv`, `U85_256_512_DIFFERENTIAL.csv`.
- 합성 모델: Vela per-layer 추정 사이클(`vela_est_cycles`, `vela_util_pct`)은 `h3_models_conditions_metrics.csv`에 열로만 있고 비교 분석은 **NOT_ANALYSED**.
- H1-C(a)의 M1/M2는 X4 실측에 맞춘 자체 모델이며 Vela 예측과 무관하다.

## 자료가 없거나 확인되지 않은 항목
- stall 카운터(S4 NOT_EVALUABLE) · TOTAL 격자의 기원 · EXT_PULSE_OFF=0 정지 원인 · 합성 모델의 Vela–FVP 비교 · 대표 레이어 외 레이어의 배치 효과 · H3 relaxed 조건에서의 MAXR 동일화.
- 매니저 최종 검토(§8 요인표·병기 방식·v9)는 ChatGPT 탭이 닫혀 미전달(`reports/2026-09-14-h1-h3-verification-plan.md` 종료 기록).
"""
(OUT / "INDEX.md").write_text(index, encoding="utf-8")
with open(OUT / "MANIFEST.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["handoff_path", "source", "kind", "commit", "sha256", "note"]); w.writeheader(); w.writerows(manifest)
print("handoff files:", len(manifest), "->", OUT)
