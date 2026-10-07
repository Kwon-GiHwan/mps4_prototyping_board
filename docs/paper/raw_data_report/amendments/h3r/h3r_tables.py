"""H3-R tables (plan A8, GO section 10): descriptive CSVs built from h3r_results.json, results.jsonl, the Vela dumps and
the read-only H13 evidence. No judgement is made here (judgements: h3r_analyze.py). /usr/bin/python3 h3r_tables.py

  runs_all.csv                         every stock run record (rep level) + verify status
  h3r_models_conditions_metrics.csv    model x MAC x arm (gate-passed): counters, r (TOTAL/ACTIVE), 16 requested + 16 applied TA values, SHAs, Vela block/encoded weights
  h3r_judgements_total_vs_active.csv   preregistered judgements on TOTAL vs ACTIVE, label HOLDS_BOTH/FAILS_BOTH/METRIC_DEPENDENT
  h3_vs_h3r_base.csv                   Q1: H3 base (per-shape quantisation) vs H3-R base (common quantisation), same shape
  base_vs_equalized.csv                Q2: H3-R base vs equalized per model and MAC
  dw_bridge_vs_equalized.csv           Q3: DW H3 relaxed (legacy) vs H3-R bridge_legacy_relaxed vs equalized
  h3r_blocks.csv                       Q5: Vela OFM/IFM block, ublock, traversal, kernel padding, encoded weights, counters per model x MAC x arm
  legacy_judgements_area36.csv         the same preregistered rules applied to the H3 area-36 data (base/relaxed), for Q4
  gate_summary.csv                     gate counts
"""
import csv, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
H13 = HERE.parent / "h13"
sys.path.insert(0, str(HERE))
from h3r_analyze import TA_KEYS, REQUIRED, applied, load, model_of, mac_of, judge, compare_metrics, METRICS  # noqa: E402

OP_RE = re.compile(r"^\s*(\d+): Operation (\S+)\s+- OFM ([\d, ]+)$")
CFG_RE = re.compile(r"OFM Block=\[([\d, ]+)\], IFM Block=\[([\d, ]+)\](?:, OFM UBlock=\[([\d, ]+)\])?(?: Traversal=(\w+))?")
KER_RE = re.compile(r"Kernel: size=(\S+) stride=(\S+), dilation=(\S+) padding=\[([^\]]+)\]")
ENC_RE = re.compile(r"Encoded Weights = (\d+) bytes")
EST_RE = re.compile(r"Estimated Perf: Macs=(\d+) Cycles=(\d+)")
DRAM_RE = re.compile(r"Total DRAM used\s+([\d.]+) KiB")


def write_csv(name, rows, note=None):
    if not rows:
        print("no rows for", name); return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(HERE / name, "w", newline="") as f:
        if note:
            f.write("# " + note + "\n")
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print("%-40s %d rows" % (name, len(rows)))


def parse_vela(path):
    d = {}
    if not path.exists():
        return d
    txt = open(path, errors="replace").read()
    first = True
    for line in txt.splitlines():
        m = OP_RE.match(line)
        if m and first:
            d["vela_op"] = m.group(2); d["ofm"] = "x".join(m.group(3).replace(" ", "").split(",")); first = False
        c = CFG_RE.search(line)
        if c and "ofm_block" not in d:
            ob = [int(x) for x in c.group(1).split(",")]; ib = [int(x) for x in c.group(2).split(",")]
            d["ofm_block_HWC"] = "x".join(map(str, ob[-3:])); d["ifm_block_HWC"] = "x".join(map(str, ib[-3:]))
            d["ublock_HWC"] = "x".join(c.group(3).replace(" ", "").split(",")) if c.group(3) else None; d["traversal"] = c.group(4)
        k = KER_RE.search(line)
        if k and "kernel" not in d:
            d["kernel"] = k.group(1); d["stride"] = k.group(2); d["dilation"] = k.group(3); d["padding_tlbr"] = k.group(4)
        e = ENC_RE.search(line)
        if e and "encoded_weight_bytes" not in d:
            d["encoded_weight_bytes"] = int(e.group(1))
        s = EST_RE.search(line)
        if s and "vela_est_cycles" not in d:
            d["vela_est_macs"] = int(s.group(1)); d["vela_est_cycles"] = int(s.group(2))
        t = DRAM_RE.search(line)
        if t:
            d["vela_total_dram_KiB"] = float(t.group(1))
    return d


def h13_records():
    """Read-only: H3 base/relaxed counters and per-shape quantisation of the legacy area-36 models."""
    out = {}
    for r in load(H13 / "results.jsonl"):
        if "measurement" not in r or not r["cell_id"].startswith("h3_") or r.get("rep") != 1 or "syscfgMid" in r["cell_id"]:
            continue
        model = r["cell_id"].split("__")[0]; mac = int(r["cell_id"].split("ethos-u85-")[1])
        out[(model, r["arm"], mac)] = r
    blocks = {}
    for row in csv.DictReader(open(H13 / "h3_blocks.csv")):
        blocks[(row["model"], row["cond"], int(row["mac"]))] = row
    quant = {m["model"]: m for m in json.load(open(H13 / "h3_manifest.json"))}
    return out, blocks, quant


def main():
    res = json.load(open(HERE / "h3r_results.json"))
    recs = load(HERE / "results.jsonl")
    man = {m["model"]: m for m in json.load(open(HERE / "h3r_manifest.json"))}
    cyc = {}
    for k, v in res["cycles"].items():
        model, cond, mac = k.split("|"); cyc[(model, cond, int(mac))] = v
    rt = {tuple(k.split("|")): v for k, v in res["judged"]["TOTAL"]["ratios"].items()}
    ra = {tuple(k.split("|")): v for k, v in res["judged"]["ACTIVE"]["ratios"].items()}
    passed = {tuple(k.split("|")) for k, v in res["gates"]["arms"].items() if v == "PASS"}
    passed_models = {m for m, v in res["gates"]["models"].items() if not v.get("refused")}

    # ---- runs_all
    rows = []
    for r in recs:
        m = r.get("measurement") or {}
        v = r.get("verify") or {}
        model = model_of(r["cell_id"]); mm = man.get(model, {})
        rows.append({"cell_id": r["cell_id"], "model": model, "op": mm.get("op"), "H": mm.get("H"), "W": mm.get("W"), "mac": mac_of(r["cell_id"]),
                     "arm": r["arm"], "rep": r.get("rep"), "status": r["status"], "TOTAL": m.get("npu_total_cycles"), "ACTIVE": m.get("npu_active_cycles"),
                     "IDLE": m.get("npu_idle_cycles"), "SRAM_RD": m.get("sram_rd_beats"), "SRAM_WR": m.get("sram_wr_beats"), "EXT_RD": m.get("ext_rd_beats"),
                     "EXT_WR": m.get("ext_wr_beats"), "vela_sha256": (r.get("artifact") or {}).get("vela_sha256"), "axf_sha256": (r.get("artifact") or {}).get("axf_sha256"),
                     "header_matches_request": r.get("header_matches_request"), "wall_clock_s": r.get("wall_clock_s"), "elapsed_s": r.get("elapsed_s"),
                     "uart_file": Path(r["uart_file"]).name if r.get("uart_file") else None,
                     "verify_status": v.get("status"), "verify_dump_sha256": v.get("dump_sha256"), "verify_axf_sha256": v.get("axf_sha256"),
                     "gate": "PASS" if (r["cell_id"], r["arm"]) in passed and model in passed_models else "REFUSED_OR_INCOMPLETE",
                     "log": (r.get("log") or "")[-200:].replace("\n", " ") if r["status"].startswith("BUILD_FAILED") else None})
    write_csv("runs_all.csv", rows)

    # ---- per model x MAC x arm
    first = {}
    for r in recs:
        if "measurement" in r and r.get("rep") == 1:
            first[(r["cell_id"], r["arm"])] = r
    metrics = []
    for (cell, arm), r in sorted(first.items(), key=lambda kv: (man.get(model_of(kv[0][0]), {}).get("op", ""), man.get(model_of(kv[0][0]), {}).get("H", 0), kv[0][1], mac_of(kv[0][0]))):
        model = model_of(cell); mac = mac_of(cell); mm = man.get(model, {}); m = r["measurement"]
        ok = (cell, arm) in passed and model in passed_models
        vd = parse_vela(HERE / "vela" / ("%s__%s" % (cell, arm)) / "vela_verbose.txt")
        row = {"model": model, "op": mm.get("op"), "H": mm.get("H"), "W": mm.get("W"), "C": 128, "area": 36, "arm": arm, "mac": mac, "gate": "PASS" if ok else "REFUSED",
               "kernel": vd.get("kernel"), "stride": vd.get("stride"), "padding_tlbr": vd.get("padding_tlbr"), "dilation": vd.get("dilation"),
               "model_sha256": mm.get("sha256"), "weights_sha256": mm.get("weights_sha256"), "bias_sha256": mm.get("bias_sha256"),
               "ifm_q": json.dumps(mm.get("ifm_q")), "ofm_q": json.dumps(mm.get("ofm_q")),
               "vela_version": "5.0.0", "accelerator_config": "ethos-u85-%d" % mac, "system_config": "Ethos_U85_SYS_DRAM_Low" if mac == 256 else "Ethos_U85_SYS_DRAM_Mid_512",
               "memory_mode": "Dedicated_Sram", "vela_sha256": r["artifact"]["vela_sha256"], "cc_body_sha256": r["artifact"]["cc_body_sha256"], "axf_sha256": r["artifact"]["axf_sha256"],
               "ofm_block_HWC": vd.get("ofm_block_HWC"), "ifm_block_HWC": vd.get("ifm_block_HWC"), "ublock_HWC": vd.get("ublock_HWC"), "traversal": vd.get("traversal"),
               "encoded_weight_bytes": vd.get("encoded_weight_bytes"), "vela_total_dram_KiB": vd.get("vela_total_dram_KiB"), "vela_est_cycles": vd.get("vela_est_cycles"),
               "TOTAL": m["npu_total_cycles"], "ACTIVE": m["npu_active_cycles"], "IDLE": m["npu_idle_cycles"],
               "SRAM_RD": m["sram_rd_beats"], "SRAM_WR": m["sram_wr_beats"], "EXT_RD": m["ext_rd_beats"], "EXT_WR": m["ext_wr_beats"],
               "r_TOTAL_512_over_256": rt.get((model, arm)) if mac == 256 else None, "r_ACTIVE_512_over_256": ra.get((model, arm)) if mac == 256 else None,
               "scaling_eff_TOTAL": round(1 / (2 * rt[(model, arm)]), 4) if mac == 256 and (model, arm) in rt else None,
               "scaling_eff_ACTIVE": round(1 / (2 * ra[(model, arm)]), 4) if mac == 256 and (model, arm) in ra else None,
               "verify_dump_sha256": (r.get("verify") or {}).get("dump_sha256"), "verify_status": (r.get("verify") or {}).get("status"),
               "uart_file": Path(r["uart_file"]).name if r.get("uart_file") else None}
        hdr = r.get("ta_header") or {}; ap = applied(hdr) if hdr else {}
        for k in TA_KEYS:
            row["%s_requested" % k] = r["defines"].get(k)
        for k in TA_KEYS:
            row["%s_header" % k] = hdr.get(k)
        for k in TA_KEYS:
            row["%s_applied" % k] = ap.get(k)
        metrics.append(row)
    write_csv("h3r_models_conditions_metrics.csv", metrics)

    # ---- judgements
    write_csv("h3r_judgements_total_vs_active.csv", [dict(r, TOTAL_value=json.dumps(r["TOTAL_value"]), ACTIVE_value=json.dumps(r["ACTIVE_value"])) for r in res["judgements"]],
              note="preregistered judgements (plan A8) applied to NPU TOTAL (primary) and NPU ACTIVE (parallel); METRIC_DEPENDENT when they disagree")
    write_csv("h3r_spread_medians.csv", [dict({"metric": met, "op_cond": k}, **v) for met in ("TOTAL", "ACTIVE") for k, v in res["judged"][met]["spread"].items()])

    # ---- Q1: H3 base vs H3-R base
    legacy, lblocks, lquant = h13_records()

    # ---- the same rules applied to the H3 area-36 data (Q4: did the metric dependence of H3 reproduce?)
    lcyc, lmeta = {}, {}
    for (model, arm, mac), r in legacy.items():
        op = model.split("_")[1]
        hw = model.split("_")[2].split("x")
        h, w = int(hw[0]), int(hw[1])
        if h * w != 36:
            continue
        # H3's 'relaxed' arm is the same TA definition H3-R calls bridge_legacy_relaxed, so it is read into that
        # slot; the judgement code itself (the preregistered contract) is not touched.
        slot = "bridge_legacy_relaxed" if arm == "relaxed" else arm
        lcyc[(model, slot, mac)] = r["measurement"]
        lmeta[model] = {"model": model, "op": op, "H": h, "W": w}
    ljudged = {name: judge(lcyc, lmeta, key) for name, key in METRICS.items()}
    write_csv("legacy_judgements_area36.csv", [dict(r, TOTAL_value=json.dumps(r["TOTAL_value"]), ACTIVE_value=json.dumps(r["ACTIVE_value"]))
                                               for r in compare_metrics(ljudged)],
              note="Q4 reference: the preregistered H3-R rules (plan A8) applied unchanged to the H3 area-36 measurements from h13/results.jsonl (arms base and relaxed); H3 'relaxed' occupies the slot H3-R calls bridge_legacy_relaxed")
    json.dump({k: {"ratios": v["ratios"], "spread": v["spread"], "values": v["values"], "outcomes": v["outcomes"]} for k, v in ljudged.items()},
              open(HERE / "legacy_judgements_area36.json", "w"), indent=1)
    q1 = []
    for model, mm in sorted(man.items(), key=lambda kv: (kv[1]["op"], kv[1]["H"])):
        lm = "h3_%s_%dx%d_c128" % (mm["op"], mm["H"], mm["W"])
        l256, l512 = legacy.get((lm, "base", 256)), legacy.get((lm, "base", 512))
        n256, n512 = cyc.get((model, "base", 256)), cyc.get((model, "base", 512))
        v256 = parse_vela(HERE / "vela" / ("%s__SSE-320__ethos-u85-256__base" % model) / "vela_verbose.txt")
        v512 = parse_vela(HERE / "vela" / ("%s__SSE-320__ethos-u85-512__base" % model) / "vela_verbose.txt")
        row = {"op": mm["op"], "H": mm["H"], "W": mm["W"], "legacy_model": lm, "h3r_model": model,
               "legacy_ifm_zp": lquant.get(lm, {}).get("input_zp"), "legacy_out_scale": lquant.get(lm, {}).get("output_scale"), "legacy_out_zp": lquant.get(lm, {}).get("output_zp"),
               "h3r_ifm_zp": (mm.get("ifm_q") or {}).get("zero_point", [None])[0], "h3r_out_scale": (mm.get("ofm_q") or {}).get("scale", [None])[0], "h3r_out_zp": (mm.get("ofm_q") or {}).get("zero_point", [None])[0],
               "legacy_TOTAL_256": l256 and l256["measurement"]["npu_total_cycles"], "legacy_TOTAL_512": l512 and l512["measurement"]["npu_total_cycles"],
               "legacy_r_TOTAL": round(l512["measurement"]["npu_total_cycles"] / l256["measurement"]["npu_total_cycles"], 4) if l256 and l512 else None,
               "h3r_TOTAL_256": n256 and n256["npu_total_cycles"], "h3r_TOTAL_512": n512 and n512["npu_total_cycles"], "h3r_r_TOTAL": rt.get((model, "base")),
               "legacy_ACTIVE_256": l256 and l256["measurement"]["npu_active_cycles"], "legacy_ACTIVE_512": l512 and l512["measurement"]["npu_active_cycles"],
               "legacy_r_ACTIVE": round(l512["measurement"]["npu_active_cycles"] / l256["measurement"]["npu_active_cycles"], 4) if l256 and l512 else None,
               "h3r_ACTIVE_256": n256 and n256["npu_active_cycles"], "h3r_ACTIVE_512": n512 and n512["npu_active_cycles"], "h3r_r_ACTIVE": ra.get((model, "base")),
               "legacy_reversal_TOTAL": (l512["measurement"]["npu_total_cycles"] > l256["measurement"]["npu_total_cycles"]) if l256 and l512 else None,
               "h3r_reversal_TOTAL": (n512["npu_total_cycles"] > n256["npu_total_cycles"]) if n256 and n512 else None,
               "same_TOTAL_256": (l256 and n256 and l256["measurement"]["npu_total_cycles"] == n256["npu_total_cycles"]) or False,
               "same_TOTAL_512": (l512 and n512 and l512["measurement"]["npu_total_cycles"] == n512["npu_total_cycles"]) or False,
               "same_ACTIVE_256": (l256 and n256 and l256["measurement"]["npu_active_cycles"] == n256["npu_active_cycles"]) or False,
               "same_ACTIVE_512": (l512 and n512 and l512["measurement"]["npu_active_cycles"] == n512["npu_active_cycles"]) or False,
               "legacy_block_256": (lblocks.get((lm, "base", 256)) or {}).get("ofm_block_HWC"), "h3r_block_256": v256.get("ofm_block_HWC"),
               "legacy_block_512": (lblocks.get((lm, "base", 512)) or {}).get("ofm_block_HWC"), "h3r_block_512": v512.get("ofm_block_HWC"),
               "legacy_ublock_256": (lblocks.get((lm, "base", 256)) or {}).get("ublock_HWC"), "h3r_ublock_256": v256.get("ublock_HWC"),
               "legacy_ublock_512": (lblocks.get((lm, "base", 512)) or {}).get("ublock_HWC"), "h3r_ublock_512": v512.get("ublock_HWC"),
               "h3r_encoded_w_256": v256.get("encoded_weight_bytes"), "h3r_encoded_w_512": v512.get("encoded_weight_bytes"),
               "legacy_EXT_RD_256": l256 and l256["measurement"]["ext_rd_beats"], "h3r_EXT_RD_256": n256 and n256["ext_rd_beats"],
               "legacy_EXT_RD_512": l512 and l512["measurement"]["ext_rd_beats"], "h3r_EXT_RD_512": n512 and n512["ext_rd_beats"],
               "legacy_SRAM_RD_256": l256 and l256["measurement"]["sram_rd_beats"], "h3r_SRAM_RD_256": n256 and n256["sram_rd_beats"],
               "legacy_SRAM_RD_512": l512 and l512["measurement"]["sram_rd_beats"], "h3r_SRAM_RD_512": n512 and n512["sram_rd_beats"],
               "legacy_vela_sha_256": l256 and l256["artifact"]["vela_sha256"], "h3r_vela_sha_256": (first.get(("%s__SSE-320__ethos-u85-256" % model, "base")) or {}).get("artifact", {}).get("vela_sha256"),
               "legacy_vela_sha_512": l512 and l512["artifact"]["vela_sha256"], "h3r_vela_sha_512": (first.get(("%s__SSE-320__ethos-u85-512" % model, "base")) or {}).get("artifact", {}).get("vela_sha256")}
        q1.append(row)
    write_csv("h3_vs_h3r_base.csv", q1, note="Q1: H3 (per-shape calibration, h13/results.jsonl read-only) vs H3-R base (common quantisation); reproduction of legacy reversals is not a gate")

    # ---- Q2: base vs equalized
    q2 = []
    for model, mm in sorted(man.items(), key=lambda kv: (kv[1]["op"], kv[1]["H"])):
        row = {"op": mm["op"], "H": mm["H"], "W": mm["W"], "model": model}
        for cond in ("base", "equalized"):
            for mac in (256, 512):
                m = cyc.get((model, cond, mac))
                for k, lab in (("npu_total_cycles", "TOTAL"), ("npu_active_cycles", "ACTIVE"), ("npu_idle_cycles", "IDLE"), ("ext_rd_beats", "EXT_RD"), ("ext_wr_beats", "EXT_WR"), ("sram_rd_beats", "SRAM_RD"), ("sram_wr_beats", "SRAM_WR")):
                    row["%s_%s_%d" % (lab, cond, mac)] = m and m[k]
            row["r_TOTAL_%s" % cond] = rt.get((model, cond)); row["r_ACTIVE_%s" % cond] = ra.get((model, cond))
        for mac in (256, 512):
            b, e = cyc.get((model, "base", mac)), cyc.get((model, "equalized", mac))
            row["dTOTAL_eq_minus_base_%d" % mac] = (e["npu_total_cycles"] - b["npu_total_cycles"]) if b and e else None
            row["dACTIVE_eq_minus_base_%d" % mac] = (e["npu_active_cycles"] - b["npu_active_cycles"]) if b and e else None
        row["dr_TOTAL_eq_minus_base"] = round(rt[(model, "equalized")] - rt[(model, "base")], 4) if (model, "base") in rt and (model, "equalized") in rt else None
        row["dr_ACTIVE_eq_minus_base"] = round(ra[(model, "equalized")] - ra[(model, "base")], 4) if (model, "base") in ra and (model, "equalized") in ra else None
        q2.append(row)
    write_csv("base_vs_equalized.csv", q2, note="Q2: same model, TA bundle changed (base profile -> equalized); the difference is the effect of the whole bundle")

    # ---- Q3: DW legacy relaxed vs bridge vs equalized
    q3 = []
    for model, mm in sorted(man.items(), key=lambda kv: (kv[1]["op"], kv[1]["H"])):
        if mm["op"] != "dw3x3":
            continue
        lm = "h3_dw3x3_%dx%d_c128" % (mm["H"], mm["W"])
        row = {"H": mm["H"], "W": mm["W"], "model": model, "legacy_model": lm}
        for mac in (256, 512):
            l = legacy.get((lm, "relaxed", mac)); lb = legacy.get((lm, "base", mac))
            row["legacy_relaxed_TOTAL_%d" % mac] = l and l["measurement"]["npu_total_cycles"]; row["legacy_relaxed_ACTIVE_%d" % mac] = l and l["measurement"]["npu_active_cycles"]
            row["legacy_base_TOTAL_%d" % mac] = lb and lb["measurement"]["npu_total_cycles"]
            for cond in ("base", "bridge_legacy_relaxed", "equalized"):
                m = cyc.get((model, cond, mac))
                row["h3r_%s_TOTAL_%d" % (cond, mac)] = m and m["npu_total_cycles"]; row["h3r_%s_ACTIVE_%d" % (cond, mac)] = m and m["npu_active_cycles"]
                row["h3r_%s_EXT_RD_%d" % (cond, mac)] = m and m["ext_rd_beats"]; row["h3r_%s_SRAM_RD_%d" % (cond, mac)] = m and m["sram_rd_beats"]
                row["h3r_%s_SRAM_WR_%d" % (cond, mac)] = m and m["sram_wr_beats"]
        l256, l512 = legacy.get((lm, "relaxed", 256)), legacy.get((lm, "relaxed", 512))
        row["legacy_r_TOTAL_relaxed"] = round(l512["measurement"]["npu_total_cycles"] / l256["measurement"]["npu_total_cycles"], 4) if l256 and l512 else None
        row["legacy_r_ACTIVE_relaxed"] = round(l512["measurement"]["npu_active_cycles"] / l256["measurement"]["npu_active_cycles"], 4) if l256 and l512 else None
        for cond in ("base", "bridge_legacy_relaxed", "equalized"):
            row["h3r_r_TOTAL_%s" % cond] = rt.get((model, cond)); row["h3r_r_ACTIVE_%s" % cond] = ra.get((model, cond))
        b = res["bridge"].get(model, {})
        row["delta_r_TOTAL_eq_minus_bridge"] = b.get("delta_r_TOTAL"); row["delta_r_ACTIVE_eq_minus_bridge"] = b.get("delta_r_ACTIVE")
        q3.append(row)
    write_csv("dw_bridge_vs_equalized.csv", q3, note="Q3: DW area 36 -- legacy H3 relaxed (per-shape quantisation + MAC-specific MAXR/MAXW), bridge (common quantisation + same legacy relaxed), equalized (common quantisation + identical applied TA); descriptive, no threshold")

    # ---- Q5: blocks
    q5 = []
    for row in metrics:
        q5.append({k: row.get(k) for k in ("op", "H", "W", "mac", "arm", "gate", "kernel", "padding_tlbr", "ofm_block_HWC", "ifm_block_HWC", "ublock_HWC", "traversal",
                                           "encoded_weight_bytes", "vela_est_cycles", "TOTAL", "ACTIVE", "IDLE", "SRAM_RD", "SRAM_WR", "EXT_RD", "EXT_WR", "r_TOTAL_512_over_256", "r_ACTIVE_512_over_256")})
        ob = (row.get("ofm_block_HWC") or "").split("x"); ub = (row.get("ublock_HWC") or "").split("x")
        if len(ob) == 3 and row["H"]:
            bh, bw, bc = map(int, ob); q5[-1].update({"H_mod_bH": row["H"] % bh, "W_mod_bW": row["W"] % bw, "n_blocks": -(-row["H"] // bh) * -(-row["W"] // bw) * -(-128 // bc)})
        if len(ub) == 3 and row["H"]:
            uh, uw, _ = map(int, ub); q5[-1].update({"H_mod_uH": row["H"] % uh, "W_mod_uW": row["W"] % uw})
    write_csv("h3r_blocks.csv", q5, note="Q5: Vela schedule facts per model x MAC x arm; H x W / MAC is not a utilisation; 3x3 border/padding effects are not attributed to a ublock automatically")

    # ---- gate summary
    arms = res["gates"]["arms"]; cells = res["gates"]["cells"]; models = res["gates"]["models"]
    write_csv("gate_summary.csv", [
        {"gate": "arms (RUN/REPS/TA header+cache)", "pass": sum(1 for v in arms.values() if v == "PASS"), "refused": sum(1 for v in arms.values() if v != "PASS"), "total": len(arms)},
        {"gate": "cells G1 (artifact identity across arms)", "pass": sum(1 for v in cells.values() if v == "PASS"), "refused": sum(1 for v in cells.values() if v != "PASS"), "total": len(cells)},
        {"gate": "models (G1', output identity, equalized applied)", "pass": sum(1 for v in models.values() if not v.get("refused")), "refused": sum(1 for v in models.values() if v.get("refused")), "total": len(models)},
        {"gate": "preservation", "pass": 1 if res["gates"]["preservation"] == "PASS" else 0, "refused": 0 if res["gates"]["preservation"] == "PASS" else 1, "total": 1}])
    refused = [(k, v["refused"]) for k, v in arms.items() if v != "PASS"] + [(k, v["refused"]) for k, v in cells.items() if v != "PASS"] + [(k, v["refused"]) for k, v in models.items() if v.get("refused")]
    print("refusals:", refused or "none")


if __name__ == "__main__":
    main()
