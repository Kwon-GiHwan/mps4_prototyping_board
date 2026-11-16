#!/usr/bin/env python3
"""Stage 6B-E2A (evidence/stage6b/stage6be2a/contract.md): board-free POSTHOC_DIAGNOSTIC audit of the Vela 5.0.0 cost
model against existing FI101 data (TA profile 1). Pure rules first, then loading and the run.

  python3 stage6be2a.py targets <targets.json>            # inputs for host/container/stage6be2a_vela.py
  python3 stage6be2a.py run <facts dir> <out dir>
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
BEAT = 16
FORM_TOL = 0.15          # M2: every B shape and the A median within 15 %
B_MIN = 5                # M2: at least 5 comparable B shapes
M1C_MIN = 0.90           # M1c: share of 1x1 DepthFirst Conv ops reproduced within +-1 cycle
BURST_TOL = 0.10         # C5
H1_DIFF = 0.10           # H-E2-1 (a): F4 vs F0 median |error| difference
H3_HI, H3_LO, H3_CV = 0.8, 0.2, 0.25
H4_DIFF = 0.25
VELA = dict(Sram=dict(clock_scale=1.0, ports_used=2, burst_length=64, read_latency=32, write_latency=32, max_reads=8, max_writes=8),
            Dram=dict(clock_scale=0.75, ports_used=2, burst_length=128, read_latency=500, write_latency=250, max_reads=64, max_writes=32))
ARENA_CACHE = 393216
RB_U85_1024 = dict(Mem2Mem=256, IFMStream=256, Weight=416, FastWeight=208, IFM=256, Scale=16)   # ethos_u85.cpp channelRBs
A_GROUPS = ("G09", "G11", "G12", "G25", "G40", "G52", "G57")
A_UNSTABLE = ("G28", "G53", "G56")
B_SHAPES = ("e1r_c200_h37w37_o96", "e1r_c200_h33w33_o96", "e1r_c200_h37w37_o176", "e1r_c200_h29w29_o96",
            "e1r_c100_h37w37_o96", "e1r_c136_h37w37_o96")
C1 = "s4c2_conv_cin48"
BB_WL = REPO / "evidence/stage6b/stage6bb/workloads"
BB_RAW = REPO / "evidence/stage6b/stage6bb/raw/evsweep_s6bb_run/conds"
RA = REPO / "evidence/stage6b/revision_a/compiled"
E1R_WL = REPO / "evidence/stage6b/stage6be1r/workloads"
E1R_RAW = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r_run/conds"
E1R_SUM = REPO / "results/fi101_stage6b/stage6be1r/stage6be1r_summary.json"
BB_SHAPES = REPO / "results/fi101_stage6b/stage6bb/shapes.csv"
BR_VELA = REPO / "results/fi101_stage6b/stage6br/vela_fidelity_analysis.csv"
S6_WHOLE = REPO / "results/fi101_stage6/whole_model_comparison.csv"
M_FACTS = REPO / "evidence/stage6m/facts/kernels.json"


# ---- pure: Vela 5.0.0 source formulas ------------------------------------------------------------------------------------
def channel_bw(mem: dict, channel: str) -> float:
    """EthosU85Performance::ChannelBW; Bandwidth = clock_scale * 16 * ports_used (regor.cpp, U85 AXI 16 B)."""
    bandwidth = mem["clock_scale"] * 16 * mem["ports_used"]
    burst_words = max(mem["burst_length"] // 16, 1)
    if channel == "Write":
        out, lat, rb = mem["max_writes"], mem["write_latency"], math.inf
    else:
        out, lat, rb = mem["max_reads"], mem["read_latency"], RB_U85_1024[channel] / burst_words
    util = min(rb, out * mem["ports_used"] * 0.8)
    return min(bandwidth, mem["burst_length"] * util / lat * 0.8)


def mac_cycles_src(ifm: list, ofm: list, ifm_blk: list, ofm_blk: list, ub: list, const_latency: int = 500,
                   ao_per_elem: float = 0.0625) -> int:
    """EstimateMacOpCycles.totalMacCycles for a 1x1 DepthFirst int8 Conv (contract §3 M1c)."""
    ob = [min(a, b) for a, b in zip(ofm, ofm_blk)]
    ib_c = min(ifm[2], ifm_blk[2])
    nu = [math.ceil(o / u) for o, u in zip(ob, ub)]
    cyc = max(32 * ub[2] // 8, ib_c // 8 * nu[0] * nu[1]) * nu[2]
    delay = 2 if nu[0] * nu[1] == 1 and nu[2] == 1 else 0
    per_blk = (cyc + delay) * math.ceil(ifm[2] / ib_c)
    n = math.prod(math.ceil(o / u) for o, u in zip(ofm, ub)) / math.prod(nu)
    ao = max(math.ceil(ao_per_elem * math.prod(ob)), 10 * ob[2] * const_latency / 256)
    return int(per_blk * n + ao)


# ---- pure: mechanism forms (contract §5) -----------------------------------------------------------------------------
def forms(ops: list[dict], r_s: float | None, r_d: float | None) -> dict:
    f = dict(F0=sum(max(o["npu"], o["sram"], o["dram"]) for o in ops),
             F1=sum(o["npu"] + max(o["sram"], o["dram"]) for o in ops),
             F2=sum(max(o["npu"], o["sram"] + o["dram"]) for o in ops),
             F3=sum(o["npu"] + o["sram"] + o["dram"] for o in ops))
    f["F4"] = None if r_s is None or r_d is None else sum(max(o["npu"], o["sram"] * r_s, o["dram"] * r_d) for o in ops)
    return f


def rel_err(board: float, est: float | None) -> float | None:
    return None if est in (None, 0) else (board - est) / est


def m2(form_err: dict, key: str) -> dict:
    """form_err: {"A": [err...], "B": [err...]} for one form; contract §5."""
    a, b = form_err["A"], form_err["B"]
    ok_b = len(b) >= B_MIN and all(abs(e) <= FORM_TOL for e in b)
    ok_a = bool(a) and statistics.median(abs(e) for e in a) <= FORM_TOL
    return dict(form=key, n_b=len(b), b_all_within=ok_b, a_median_abs=statistics.median(abs(e) for e in a) if a else None,
                a_within=ok_a, holds=ok_b and ok_a)


# ---- pure: configuration audit (contract §6) ------------------------------------------------------------------------
def axi_fields(word: int) -> dict:
    return dict(max_reads=(word & 0x3F) + 1, max_writes=((word >> 8) & 0x1F) + 1, max_beats=(word >> 16) & 0x3)


def effective_outstanding(ta: int, axi: int) -> int:
    return axi if ta == 0 else min(ta, axi)


def c4_bandwidth(bwcap: int, pulse_on: int, pulse_off: int, vela_bw: float) -> str:
    caps = [bwcap * w / (pulse_on + pulse_off) * k for w in (8, 16) for k in (1, 2)]
    if all(c < vela_bw for c in caps):
        return "MISMATCH_VERIFIED"
    if all(c >= vela_bw for c in caps):
        return "MATCH"
    return "UNKNOWN"


def c5_burst(bursts: list[float], vela_burst: int) -> str:
    if bursts and all(b > vela_burst * (1 + BURST_TOL) for b in bursts):
        return "MISMATCH_VERIFIED"
    if bursts and all(b <= vela_burst * (1 + BURST_TOL) for b in bursts):
        return "MATCH"
    return "UNKNOWN"


def audit(caps: dict, bursts: dict) -> list[dict]:
    """caps: board capabilities.json; bursts: {"sram_read": [...], "sram_write": [...], "ext_read": [...]} (bytes)."""
    rows = []
    add = lambda item, vela, board, status, note="": rows.append(dict(item=item, vela=vela, board=board, status=status, note=note))
    for mem, ta in (("Sram", "sram"), ("Dram", "ext")):
        v = VELA[mem]
        same = caps[f"ta_{ta}_rlatency"] == v["read_latency"] and caps[f"ta_{ta}_wlatency"] == v["write_latency"]
        add(f"C1 latency {mem}", f"{v['read_latency']}/{v['write_latency']}", f"{caps[f'ta_{ta}_rlatency']}/{caps[f'ta_{ta}_wlatency']}",
            "MATCH" if same else "MISMATCH_VERIFIED", "unit: TA root clock = CPU clock, MCLK_ON = NPU cycles (S0-3 c2)")
        ax = axi_fields(caps[f"axi_{ta}"])
        er = effective_outstanding(caps[f"ta_{ta}_maxr"], ax["max_reads"])
        ew = effective_outstanding(caps[f"ta_{ta}_maxw"], ax["max_writes"])
        add(f"C2 outstanding {mem}", f"{v['max_reads']}/{v['max_writes']}", f"TA {caps[f'ta_{ta}_maxr']}/{caps[f'ta_{ta}_maxw']} (0=inf), AXI {ax['max_reads']}/{ax['max_writes']} -> {er}/{ew}",
            "MATCH" if (er, ew) == (v["max_reads"], v["max_writes"]) else "MISMATCH_VERIFIED")
        vbw = v["clock_scale"] * 16 * v["ports_used"]
        add(f"C4 bandwidth {mem}", f"{vbw:g} B/cycle", f"bwcap {caps[f'ta_{ta}_bwcap']} per {caps[f'ta_{ta}_pulse_on']}+{caps[f'ta_{ta}_pulse_off']} cycles",
            c4_bandwidth(caps[f"ta_{ta}_bwcap"], caps[f"ta_{ta}_pulse_on"], caps[f"ta_{ta}_pulse_off"], vbw),
            "word 8 or 16 B (docs differ), one TA per bus or per port")
    cfg = caps["npu_config"]
    ns, ne = 2 ** ((cfg >> 8) & 0x3), 2 ** ((cfg >> 10) & 0x1)
    add("C3 ports", f"{VELA['Sram']['ports_used']}/{VELA['Dram']['ports_used']}", f"CONFIG num_axi_sram/ext (log2) -> {ns}/{ne}",
        "MATCH" if (ns, ne) == (VELA["Sram"]["ports_used"], VELA["Dram"]["ports_used"]) else "MISMATCH_VERIFIED")
    for key, mem in (("sram_read", "Sram"), ("sram_write", "Sram"), ("ext_read", "Dram")):
        b = bursts.get(key, [])
        add(f"C5 burst {key}", f"{VELA[mem]['burst_length']} B", f"measured mean {min(b):.1f}-{max(b):.1f} B" if b else "none",
            c5_burst(b, VELA[mem]["burst_length"]), "a mean burst only bounds the largest burst from below")
    add("C5 AXI max_beats", "-", f"SRAM {axi_fields(caps['axi_sram'])['max_beats']}, EXT {axi_fields(caps['axi_ext'])['max_beats']} (enum B64/B128/B256)",
        "NOT_APPLICABLE", "upper limit of the NPU, not a Vela parameter")
    add("C6 placement", "const/arena Dram (Axi1), cache Sram (Axi0)", "fast_base via SRAM port, DDR via EXT port", "MATCH", "static, 6B-R")
    add("C7 SRAM size", str(ARENA_CACHE), str(caps["fast_size"]), "MATCH" if caps["fast_size"] == ARENA_CACHE else "MISMATCH_VERIFIED")
    add("C8 clock", "1 GHz", "cycles compared in NPU cycles", "NOT_APPLICABLE")
    add("C9 TA MODE bit 0", "no counterpart", f"SRAM {caps['ta_sram_mode'] & 1}, EXT {caps['ta_ext_mode'] & 1}", "NOT_APPLICABLE",
        "dynamic clocking: the NPU clock stops while the FPGA memory misses the emulated deadline (S0-3)")
    return rows


# ---- pure: hypotheses and verdict (contract §7, §9) ----------------------------------------------------------------------
def ranks(v: list) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x: list, y: list) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def h1(f4_abs: list, f0_abs: list, board_le_vela_bytes: list[bool]) -> str:
    if f4_abs and statistics.median(f4_abs) <= FORM_TOL:
        return "SUPPORTED_PATTERN"
    if board_le_vela_bytes and all(board_le_vela_bytes) and abs(statistics.median(f4_abs) - statistics.median(f0_abs)) <= H1_DIFF:
        return "CONTRADICTED"
    return "NOT_DISTINGUISHABLE"


def h2(m2_rows: dict, over: dict) -> str:
    """m2_rows: {form: m2()}; over: {form: {"A": [bool...], "B": [bool...]}} True = form over-predicts by > 15 %."""
    if any(m2_rows[f]["holds"] for f in ("F1", "F2", "F3")):
        return "SUPPORTED_PATTERN"
    if all(sum(over[f][g]) * 2 >= len(over[f][g]) > 0 for f in ("F1", "F2", "F3") for g in ("A", "B")):
        return "CONTRADICTED"
    return "NOT_DISTINGUISHABLE"


def h3_group(excess: list, vela_total: list) -> str:
    rho = spearman(excess, vela_total)
    if rho is None:
        return "NOT_DISTINGUISHABLE"
    if rho >= H3_HI:
        return "CONTRADICTED"
    m = statistics.mean(excess)
    cv = statistics.pstdev(excess) / abs(m) if m else math.inf
    return "SUPPORTED_PATTERN" if rho <= H3_LO and cv <= H3_CV else "NOT_DISTINGUISHABLE"


def h3(a: str, b: str) -> str:
    return a if a == b else "NOT_DISTINGUISHABLE"


def h4(med_a: float, med_b: float) -> dict:
    return dict(status="NOT_DISTINGUISHABLE", pattern_difference=abs(med_a - med_b) > H4_DIFF)


def verdict(m1: dict, m2_rows: dict, audit_rows: list[dict], integrity_ok: bool) -> str:
    if not integrity_ok:
        return "NOT_JUDGED (integrity)"
    if m1["M1a"] and m1["M1b"] and m1["M1c"] and any(r["holds"] for r in m2_rows.values()):
        return "COST_MODEL_MECHANISM_IDENTIFIED"
    if any(r["status"] == "MISMATCH_VERIFIED" for r in audit_rows):
        return "CONFIGURATION_DISCREPANCY_IDENTIFIED"
    return "CAUSE_UNRESOLVED"


def sensitivity_class(base: dict, var: dict) -> str:
    if not var.get("ok") or not base.get("ok") or "cms_sha256" not in var or "cms_sha256" not in base:
        return "NOT_COMPARABLE"
    keys = ("cms_sha256", "const_sha256", "arena_size", "fast_size", "inputs", "outputs")
    return "ESTIMATOR_ONLY_COMPARABLE" if all(base[k] == var[k] for k in keys) else "COMPILE_CHANGED"


# ---- loading -------------------------------------------------------------------------------------------------------------
def read_csv(p: pathlib.Path) -> list[dict]:
    with open(p) as f:
        return list(csv.DictReader(f))


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def vela_ops(c: dict) -> list[dict]:
    """Per scheduled op from the debug-DB `perf` table (op_cycles = total, npu_cycles, <mem>_ac)."""
    return [dict(id=r.get("id"), operator=r["operator"], total=num(r["op_cycles"]), npu=num(r["npu_cycles"]),
                 sram=num(r.get("Sram_ac")), dram=num(r.get("Dram_ac")), lut=num(r.get("lutram_ac")))
            for r in c["db"]["perf"]]


def m1_checks(compiles: dict) -> dict:
    a, b, c, rows = [], [], [], []
    for sid, cmp in compiles.items():
        ops = vela_ops(cmp)
        a += [o["total"] == max(o["npu"], o["sram"], o["dram"], o["lut"]) for o in ops]
        b.append(num(cmp["summary"]["cycles_total"]) == sum(o["total"] for o in ops))
        dbg = {r.get("id"): r for r in cmp["db"]["perf_debug"]}
        kind = {r.get("id"): r.get("operator") for r in cmp["db"]["perf"]}
        for m in cmp["db"]["perf_debug_main"]:
            d = dbg.get(m.get("id"))
            if not d or kind.get(m.get("id")) != "Conv2D" or m.get("traversal") != "DepthFirst" or num(d.get("kernel_size_x")) != 1 or num(d.get("kernel_size_y")) != 1:
                continue
            hwc = lambda p, src: [int(num(src[f"{p}_{k}"])) for k in ("h", "w", "c")]
            pred = mac_cycles_src(hwc("ifm_shape", d), hwc("ofm_shape", d), hwc("ifm_block", m), hwc("ofm_block", m), hwc("ofm_ublock", m))
            rep = int(num(m["mac_cycles"]))
            c.append(abs(pred - rep) <= 1)
            rows.append(dict(shape=sid, op_id=m.get("id"), reported=rep, source_formula=pred, within_1=abs(pred - rep) <= 1))
    return dict(M1a=bool(a) and all(a), M1a_n=len(a), M1b=bool(b) and all(b), M1b_n=len(b),
                M1c=bool(c) and sum(c) / len(c) >= M1C_MIN, M1c_n=len(c), M1c_share=sum(c) / len(c) if c else None, rows=rows)


def board_of(folder: pathlib.Path, n_mac: int) -> dict:
    import stage4k as K
    m = K.summary_of(folder, n_mac)["metrics"]
    g = lambda k: m.get(k)
    burst = lambda beat, tr: g(beat) / g(tr) * BEAT if g(beat) and g(tr) else None
    return dict(npu=g("A_35"), mac=g("A_48"), ao=g("A_64"), wd=g("A_80"), wd_stalled=g("A_81"),
                sram_rd=g("B_130") * BEAT, sram_wr=g("B_135") * BEAT, ext_rd=g("B_386") * BEAT, ext_wr=g("B_391") * BEAT,
                burst_sram_read=burst("B_130", "B_128"), burst_sram_write=burst("B_135", "B_132"), burst_ext_read=burst("B_386", "B_384"))


def targets() -> list[dict]:
    out = []
    man = json.loads((BB_WL / "stage6bb_manifest.json").read_text())
    for cfg, m in man.items():
        if m["kind"] != "A2":
            continue
        rec = json.loads((RA / f"s6b_{m['group'].lower()}.ra.json").read_text())["forms"]["A2"]
        out.append(dict(id=m["group"], group="A" if m["group"] in A_GROUPS else "A_UNSTABLE", config=cfg,
                        tflite=f"/work/s6b_ra_compile/s6b_{m['group'].lower()}_f_ctx_self.tflite",
                        model_sha256=rec["model_sha256"], vela_sha256=m["vela_sha256"], cms_sha256=m["cms_sha256"]))
    for n in B_SHAPES:
        r = json.loads((E1R_WL / f"{n}.drwl.json").read_text())
        out.append(dict(id=n, group="B", config=n, tflite=f"/work/s6be2a/wl/{n}.tflite", model_sha256=r["model_sha256"],
                        vela_sha256=r["vela_sha256"], cms_sha256=r["cms_sha256"]))
    r = json.loads((E1R_WL / f"{C1}.compile.json").read_text())
    out.append(dict(id=C1, group="C1", config=C1, tflite=f"/work/s4k_compile/{C1}.tflite", model_sha256=r["model_sha256"],
                    vela_sha256=r["vela_sha256"], cms_sha256=r["cms_sha256"]))
    return out


# ---- run -----------------------------------------------------------------------------------------------------------------
def h1uc_a() -> dict:
    import stage6br as BR
    return {c["case"].split(":")[1]: BR.h1_uc(c) for c in BR.stage6bb_cases() if c["case"].startswith("6bb:G")}


def shape_rows(facts: dict) -> tuple[list[dict], dict]:
    """Phase 3 table (base compile) and the integrity checks I1-I6."""
    man = json.loads((BB_WL / "stage6bb_manifest.json").read_text())
    bb = {r["config"]: r for r in read_csv(BB_SHAPES)}
    e1r = {s["config"]: s for s in json.loads(E1R_SUM.read_text())["shapes"]}
    preds = json.loads((E1R_WL / "predictions.json").read_text())
    h_a = h1uc_a()
    rows, integ = [], dict(I1=[], I2=[], I3=[], I5=[], I6=[])
    for sid, t in facts["targets"].items():
        rec, base = t["record"], t["by_variant"]["base"]
        if rec["group"] == "A" or rec["group"] == "A_UNSTABLE":
            m = man[rec["config"]]
            valid = bb[rec["config"]]["status"] == "VALID"
            folder, n_mac, h1uc = BB_RAW / rec["config"] / "wfe", m["n_mac"], h_a.get(sid)
        elif rec["group"] == "B":
            s = e1r.get(sid, {})
            valid = s.get("cls") == "PRIMARY_VALID"
            folder, n_mac, h1uc = E1R_RAW / sid / "wfe", preds[sid]["n_mac"], preds[sid]["mac"]["H1-UC"]
        else:
            valid, folder, n_mac, h1uc = True, E1R_RAW / sid / "wfe", json.loads((E1R_WL / f"{C1}.compile.json").read_text())["n_mac"], None
        comparable = bool(t["model_equals_record"] and t["vela_equals_record"] and t["cms_equals_record"] and valid)
        integ["I1"].append(t["vela_equals_record"]); integ["I2"].append(t["cms_equals_record"]); integ["I3"].append(t["model_equals_record"])
        bd = board_of(folder, n_mac)
        if rec["group"] in ("A", "A_UNSTABLE"):
            integ["I5"].append(abs(bd["npu"] - float(bb[rec["config"]]["npu_active"])) < 1e-6 and abs(bd["mac"] - float(bb[rec["config"]]["mac_active"])) < 1e-6
                               if valid else True)
        elif rec["group"] == "B":
            integ["I5"].append(abs(bd["npu"] - e1r[sid]["npu"]["a_median"]) < 1e-6)
        s = base["summary"]
        ops = vela_ops(base)
        conv = [m for m in base["db"]["perf_debug_main"] if m.get("traversal") == "DepthFirst" and m.get("mac_cycles")]
        vs = lambda k: int(num(s[k]))
        v_sr, v_sw = vs("sram_feature_map_read_bytes") + vs("sram_weight_read_bytes"), vs("sram_feature_map_write_bytes") + vs("sram_weight_write_bytes")
        v_dr, v_dw = vs("dram_feature_map_read_bytes") + vs("dram_weight_read_bytes"), vs("dram_feature_map_write_bytes") + vs("dram_weight_write_bytes")
        r_s = (bd["sram_rd"] + bd["sram_wr"]) / (v_sr + v_sw) if v_sr + v_sw else None
        r_d = (bd["ext_rd"] + bd["ext_wr"]) / (v_dr + v_dw) if v_dr + v_dw else None
        f = forms(ops, r_s, r_d)
        total = vs("cycles_total")
        conv_mac = sum(num(m["mac_cycles"]) for m in conv)
        row = dict(shape=sid, group=rec["group"], status="COMPARABLE" if comparable else "NOT_COMPARABLE",
                   vela_compute=vs("cycles_npu"), vela_sram_ac=vs("cycles_sram_access"), vela_dram_ac=vs("cycles_dram_access"), vela_total=total,
                   board_npu_active=bd["npu"], board_mac_active=bd["mac"], board_ao_active=bd["ao"], board_wd_active=bd["wd"],
                   board_wd_stalled=bd["wd_stalled"], vela_sram_read_bytes=v_sr, vela_sram_write_bytes=v_sw,
                   vela_dram_read_bytes=v_dr, vela_dram_write_bytes=v_dw, board_sram_read_bytes=bd["sram_rd"],
                   board_sram_write_bytes=bd["sram_wr"], board_ext_read_bytes=bd["ext_rd"], board_ext_write_bytes=bd["ext_wr"],
                   error_total=rel_err(bd["npu"], total), excess=bd["npu"] - total,
                   diag_vela_compute_over_mac_active=vs("cycles_npu") / bd["mac"] if bd["mac"] else None,
                   vela_conv_mac_cycles=conv_mac, h1uc_mac_active=h1uc,
                   diag_vela_conv_mac_over_h1uc=conv_mac / h1uc if h1uc else None,
                   burst_sram_read=bd["burst_sram_read"], burst_sram_write=bd["burst_sram_write"], burst_ext_read=bd["burst_ext_read"],
                   r_sram_bytes=r_s, r_dram_bytes=r_d, ta_profile=1, image="70090f1")
        for k, v in f.items():
            row[k] = v
            row[f"err_{k}"] = rel_err(bd["npu"], v)
        rows.append(row)
    br = {r["group"]: r for r in read_csv(BR_VELA)}
    for r in rows:
        if r["group"] == "A":
            integ["I6"].append(abs(r["error_total"] * 100 - float(br[r["shape"]]["error_pct"])) < 1e-9)
    return rows, {k: dict(n=len(v), all_true=all(v)) for k, v in integ.items()}


def sensitivity_rows(facts: dict, shapes: dict) -> list[dict]:
    out = []
    for sid, t in facts["targets"].items():
        base = t["by_variant"]["base"]
        b_total = num(base["summary"]["cycles_total"]) if base.get("ok") else None
        for name, change in facts["variants"].items():
            if name == "base":
                continue
            v = t["by_variant"][name]
            cls = sensitivity_class(base, v)
            row = dict(shape=sid, group=t["record"]["group"], variant=name, parameter=change["parameter"], base_value=change["base"],
                       value=change["value"], cls=cls, label="POSTHOC_SENSITIVITY")
            if cls == "ESTIMATOR_ONLY_COMPARABLE":
                vt = num(v["summary"]["cycles_total"])
                p0, p1 = float(change["base"]), float(change["value"])
                row.update(vela_total_base=b_total, vela_total=vt, total_ratio=vt / b_total,
                           elasticity=math.log(vt / b_total) / math.log(p1 / p0) if p1 != p0 else None)
                s = shapes.get(sid)
                if s and s["status"] == "COMPARABLE":
                    row["error_vs_board"] = rel_err(s["board_npu_active"], vt)
            out.append(row)
    return out


def caps_all() -> dict:
    seen = {}
    for p in sorted(list(E1R_RAW.glob("*/capabilities.json")) + list(BB_RAW.glob("*/capabilities.json"))):
        d = json.loads(p.read_text())
        key = json.dumps({k: v for k, v in d.items() if k.startswith(("ta_", "axi_", "npu_config", "fast_size"))}, sort_keys=True)
        seen.setdefault(key, []).append(str(p.relative_to(REPO)))
    if len(seen) != 1:
        raise SystemExit(f"capabilities differ across boots: {len(seen)} variants")
    return json.loads(pathlib.Path(REPO / next(iter(seen.values()))[0]).read_text()) | dict(n_files=len(next(iter(seen.values()))))


def reference_models(models: dict) -> list[dict]:
    whole = {r["model"]: r for r in read_csv(S6_WHOLE) if r["axis"] == "mac"}
    mf = json.loads(M_FACTS.read_text())
    out = []
    for m, c in models.items():
        npu = float(whole[m]["npu_active"])
        tot = num(c["summary"]["cycles_total"]) if c.get("summary") else None
        out.append(dict(model=m, vela_equals_stage6m=c.get("vela_sha256") == mf[m]["vela_sha256"], vela_total=tot,
                        vela_npu=num(c["summary"]["cycles_npu"]) if c.get("summary") else None,
                        board_npu_active=npu, error_total=rel_err(npu, tot), image="65cf963", ta_profile=1,
                        label="REFERENCE_NOT_EQUIVALENT"))
    return out


def run(facts_dir: str, out: str) -> dict:
    fd, o = pathlib.Path(facts_dir), pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    facts = json.loads((fd / "vela_targets.json").read_text())
    rows, integ = shape_rows(facts)
    S.write_csv(o / "vela_board_table.csv", rows)
    comp = {r["shape"]: r for r in rows}
    ok_ids = [r["shape"] for r in rows if r["status"] == "COMPARABLE" and r["group"] in ("A", "B")]
    m1 = m1_checks({i: facts["targets"][i]["by_variant"]["base"] for i in ok_ids})
    S.write_csv(o / "m1_mac_cycles.csv", m1.pop("rows"))
    errs = {f: {g: [comp[i][f"err_{f}"] for i in ok_ids if comp[i]["group"] == g and comp[i][f"err_{f}"] is not None]
                for g in ("A", "B")} for f in ("F0", "F1", "F2", "F3", "F4")}
    m2_rows = {f: m2(errs[f], f) for f in ("F1", "F2", "F3", "F4")}
    over = {f: {g: [e < -FORM_TOL for e in errs[f][g]] for g in ("A", "B")} for f in ("F1", "F2", "F3")}
    caps = caps_all()
    comp_rows = [comp[i] for i in ok_ids]
    bursts = {k: [r[f"burst_{k}"] for r in comp_rows if r[f"burst_{k}"]] for k in ("sram_read", "sram_write", "ext_read")}
    aud = audit(caps, bursts)
    S.write_csv(o / "config_audit.csv", aud)
    ab = lambda f: [abs(e) for g in ("A", "B") for e in errs[f][g]]
    tot_le = [r["board_sram_read_bytes"] + r["board_sram_write_bytes"] + r["board_ext_read_bytes"] + r["board_ext_write_bytes"]
              <= r["vela_sram_read_bytes"] + r["vela_sram_write_bytes"] + r["vela_dram_read_bytes"] + r["vela_dram_write_bytes"] for r in comp_rows]
    grp = lambda g, k: [comp[i][k] for i in ok_ids if comp[i]["group"] == g]
    h3a, h3b = h3_group(grp("A", "excess"), grp("A", "vela_total")), h3_group(grp("B", "excess"), grp("B", "vela_total"))
    med = lambda g: statistics.median(grp(g, "error_total"))
    hyp = [dict(hypothesis="H-E2-1a bytes", status=h1(ab("F4"), ab("F0"), tot_le),
                f4_median_abs=statistics.median(ab("F4")), f0_median_abs=statistics.median(ab("F0")), board_bytes_le_vela=sum(tot_le), n=len(tot_le)),
           dict(hypothesis="H-E2-1b service cost per byte", status="NOT_DISTINGUISHABLE", note="contract: needs a TA-condition A/B"),
           dict(hypothesis="H-E2-2 overlap", status=h2(m2_rows, over)),
           dict(hypothesis="H-E2-3 fixed cost", status=h3(h3a, h3b), A=h3a, B=h3b,
                rho_A=spearman(grp("A", "excess"), grp("A", "vela_total")), rho_B=spearman(grp("B", "excess"), grp("B", "vela_total"))),
           dict(hypothesis="H-E2-4 compile/placement", **h4(med("A"), med("B")), median_error_A=med("A"), median_error_B=med("B"))]
    S.write_csv(o / "hypotheses.csv", hyp)
    S.write_csv(o / "sensitivity.csv", sensitivity_rows(facts, comp))
    S.write_csv(o / "channel_bw.csv", [dict(memory=mem, channel=ch, bytes_per_cycle=channel_bw(VELA[mem], ch),
                                            bandwidth=VELA[mem]["clock_scale"] * 16 * VELA[mem]["ports_used"])
                                       for mem in ("Sram", "Dram") for ch in ("IFM", "IFMStream", "Weight", "Scale", "Mem2Mem", "Write")])
    refs = reference_models(json.loads((fd / "vela_models.json").read_text())) if (fd / "vela_models.json").exists() else []
    S.write_csv(o / "reference_models.csv", refs)
    integrity_ok = integ["I5"]["all_true"] and integ["I6"]["all_true"]
    summary = dict(contract="evidence/stage6b/stage6be2a/contract.md", label="POSTHOC_DIAGNOSTIC", ta_profile=1,
                   images=dict(A_B_C1="70090f1", C2="65cf963"), integrity=integ, comparable=ok_ids,
                   not_comparable=[r["shape"] for r in rows if r["status"] != "COMPARABLE"], m1=m1, m2=m2_rows,
                   form_errors=errs, audit={r["item"]: r["status"] for r in aud}, hypotheses={h["hypothesis"]: h["status"] for h in hyp},
                   capabilities_files=caps["n_files"], verdict=verdict(m1, m2_rows, aud, integrity_ok))
    (o / "stage6be2a_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    if sys.argv[1] == "targets":
        pathlib.Path(sys.argv[2]).write_text(json.dumps(targets(), indent=1))
    elif sys.argv[1] == "run":
        print(json.dumps(run(sys.argv[2], sys.argv[3]), indent=1, default=str)[:6000])
