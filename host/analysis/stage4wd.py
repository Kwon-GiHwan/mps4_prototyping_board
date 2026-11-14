#!/usr/bin/env python3
"""Stage 4WD (docs/plan/stage4wd_characterization_plan.md, contract draft evidence/stage4wd/contract_draft.md): weight
decoder (WD) activity. TA profile 1, driver runner image 70090f1, DDR/EXT placement, Vela 5.0.0 (MLEK options).

  python3 host/analysis/stage4wd.py inventory <out dir>                every archived Stage 4 RUN folder with a weight
                                                                       stream: WD / MAC / AO / NPU / beats + static facts
  python3 host/analysis/stage4wd.py static <workloads dir> <out dir>   Experiment A / B candidates
  python3 host/analysis/stage4wd.py predict <out dir>                  pre-registered hypotheses (from inventory.json)
  python3 host/analysis/stage4wd.py judge <campaign root> <workloads dir> <predictions.json> <out dir> [<caps>]
  python3 host/analysis/stage4wd.py repro-gate <campaign root> <workloads dir> <boot-394 wfe copy> [<caps>]
  python3 host/analysis/stage4wd.py boot-check <campaign root> <workloads dir> <config> [<caps>]   (= stage4aoe A1)

Official (Arm Ethos-U85 TRM 102685 issue 05): wd_active (80) "WD is decoding weight stream. Valid blk_cmd and not
stalled"; wd_stalled (81) "WD stalled on lack of weight stream data or lack of free WD buffer space" — supply and
backpressure in one counter; 82-127 Reserved. §2.2: "The traversal unit triggers these [weight] channels for blocks
that require the transfer of weights." §2.4: SWD lossless (zero runs + Golomb-Rice), up to 64 bits/cycle each; U85-1024
num_wd = 4 (Table 3-90). Encoded bytes = the command stream's WEIGHT/WEIGHT1-3 lengths, never Vela's estimate alone.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4aoe as AOE  # noqa: E402
import stage4k as K  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
WL_DIRS = ["evidence/stage4/workloads", "evidence/stage4c1/workloads", "evidence/stage4c2/workloads",
           "evidence/stage4c2b/workloads", "evidence/stage4k/workloads", "evidence/stage4ao/workloads"]
RAW_GLOBS = ["evidence/stage4/raw", "evidence/stage4c1/raw", "evidence/stage4c2/raw", "evidence/stage4c2b/raw",
             "evidence/stage4k/raw", "evidence/stage4ao/raw", "evidence/stage4_placement/raw",
             "evidence/stage4aoe/raw_a1"]
ALIAS = {"s4p_conv_base_ddr": "s4_conv_base", "s4p_conv_base_sram": "s4_conv_base"}   # same DRWL content, placement only
WEIGHT_FORMAT = 302              # cmd0 NPU_SET_WEIGHT_FORMAT: bit 0 SWD/FWD, bit 4 sparse 2:4 (ethosu85_interface.h)
BEAT = 16                        # bytes per AXI beat (128-bit)
# Experiment B (fixed): spatial blocks of the 6x12x96 block at W = 24: ceil(H/6) * 2
EXP_A = ["s4ao_conv1x1_h24", "s4wd_w_small", "s4wd_w_sparse75", "s4wd_w_sparse90"]
EXP_B = ["s4wd_h23", "s4ao_conv1x1_h24", "s4wd_h32", "s4wd_h34", "s4ao_conv1x1_h36"]
TOL_ABS, TOL_REL = 25, 0.02      # equality of WD_ACTIVE: |a - b| <= max(25, 2 % of the mean, range_a + range_b)
AO_RANGE_ABS, AO_RANGE_REL, AB_REL = 50, 0.02, 0.05


def static_of(wl: pathlib.Path, cfg: str) -> dict:
    """Weight facts from the compiled stream: per-kernel encoded stream bytes (4 SWD streams), weight DMA, blocks."""
    import cms
    import cms_regs
    stream = (wl / f"{cfg}.drwl.cms.bin").read_bytes()
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    ks = cms_regs.kernels(stream)
    fmt = sorted({w >> 16 for _, w, c, op in cms.instructions(stream) if c == 0 and op == WEIGHT_FORMAT})
    enc = [sum(k[f] or 0 for f in ("weight_length", "weight1_length", "weight2_length", "weight3_length")) for k in ks]
    ofm = comp["ofm_shape"][1:] if len(comp["ofm_shape"]) == 4 else [1, 1, comp["ofm_shape"][-1]]
    bh, bw, bc = (int(v) for v in comp["ofm_block"].split("x")) if comp.get("ofm_block") else (1, 1, 1)
    blocks = [math.ceil(ofm[0] / bh) * math.ceil(ofm[1] / bw) * math.ceil((k["ofm_depth_m1"] + 1) / bc) for k in ks]
    spatial = math.ceil(ofm[0] / bh) * math.ceil(ofm[1] / bw)
    staged = sum(sum(d for d in k["dma_before"] if d) for k in ks)
    raw_w = math.prod(comp["weight_shape"]) if comp.get("weight_shape") else 0
    return dict(config=cfg, kind=comp.get("kernel_kinds", ["?"])[0], traversal=comp.get("traversal"),
                ofm_block=comp.get("ofm_block"), n_kernels=len(ks), raw_weight_bytes=raw_w,
                encoded_bytes=sum(enc), encoded_per_kernel=enc, vela_weight_bytes=int(comp["weight_bytes"] or 0),
                weight_dma=[k["dma_before"] for k in ks], weight_format=fmt, blocks=sum(blocks), spatial_blocks=spatial,
                staged_bytes=staged,
                blocks_per_kernel=blocks, block_weight_reads=sum(b * e for b, e in zip(blocks, enc)),
                n_ofm=math.prod(ofm), n_mac=comp["n_mac"])


def sram_rule(r: dict) -> bool:
    """DDR/EXT placement: the weight staging is written to SRAM once (SRAM write beats = staged bytes / 16) and read
    once per spatial OFM block (SRAM read beats = spatial blocks x staged bytes / 16)."""
    return r["placement"] == "ddr" and r["staged_bytes"] > 0 and \
        r["sram_rd"] == r["spatial_blocks"] * r["staged_bytes"] / BEAT and r["sram_wr"] == r["staged_bytes"] / BEAT


def wl_of(cfg: str) -> pathlib.Path | None:
    c = ALIAS.get(cfg, cfg)
    for d in WL_DIRS + ["evidence/stage4wd/workloads"]:
        if (REPO / d / f"{c}.drwl.cms.bin").exists() and (REPO / d / f"{c}.compile.json").exists():
            return REPO / d
    return None


def all_valid(folder: pathlib.Path) -> bool:
    with open(folder / "runs.csv") as f:
        rows = list(csv.DictReader(f))
    return bool(rows) and all(r["run_valid"] == "True" for r in rows)


def inventory(out: str) -> list:
    rows = []
    for g in RAW_GLOBS:
        for f in sorted(glob.glob(str(REPO / g / "**" / "conds" / "*" / "wfe"), recursive=True)):
            folder = pathlib.Path(f); cfg = folder.parent.name
            wl = wl_of(cfg)
            if wl is None:
                continue
            st = static_of(wl, ALIAS.get(cfg, cfg))
            if st["encoded_bytes"] == 0:
                continue
            m = K.summary_of(folder, 1)["metrics"]
            if m.get("A_80") is None:                    # a refused boot (Stage 4AO act_none: one RUN)
                continue
            boot = next(csv.DictReader(open(folder / "runs.csv")))["host_boot_index"]
            rows.append(dict(stage=g.split("/")[1], boot=int(boot), config=cfg, placement="sram" if cfg.endswith("_sram") else "ddr",
                             all_valid=all_valid(folder), **{k: v for k, v in st.items() if k != "config"},
                             wd_active=m["A_80"], wd_active_range=m["A_80_range"], wd_stalled=m["A_81"],
                             wd_stalled_range=m["A_81_range"], mac_active=m["A_48"], ao_active=m["A_64"],
                             npu_active=m["A_35"], sram_rd=m["B_130"], sram_wr=m["B_135"], ext_rd=m["B_386"],
                             ext_wr=m["B_391"]))
    for r in rows:
        r["sram_rd_is_spatial_x_staged"] = sram_rule(r)
        r["sram_rd_bytes_per_wd_cycle"] = r["sram_rd"] * BEAT / r["wd_active"] if r["wd_active"] else None
        r["enc_bytes_per_wd_cycle"] = r["encoded_bytes"] / r["wd_active"] if r["wd_active"] else None
        r["wd_per_block"] = r["wd_active"] / r["blocks"] if r["wd_active"] else None
        r["block_reads_bytes_per_wd_cycle"] = r["block_weight_reads"] / r["wd_active"] if r["wd_active"] else None
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "inventory.json").write_text(json.dumps(rows, indent=1, default=str))
    cols = [k for k in rows[0] if k not in ("encoded_per_kernel", "weight_dma", "blocks_per_kernel", "weight_format")]
    with open(o / "wd_inventory.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return rows


MLEK_RAW = "evidence/driver_m7/raw/wfe"


def mlek_wd(out: str) -> list:
    """The seven MLEK models on the driver runner (driver_m7, TA profile 1): pass-A medians of WD_ACTIVE, WD_STALLED,
    MAC_ACTIVE, AO_ACTIVE, NPU_ACTIVE over the measured RUNs (whole inference, no per-layer split)."""
    rows = []
    for f in sorted(glob.glob(str(REPO / MLEK_RAW / "*" / "runs.csv"))):
        with open(f) as fh:
            rs = [r for r in csv.DictReader(fh) if r["run_valid"] == "True"]
        sets = {r["set_id"] for r in rs if r["ev_type"] == "80"}
        if not sets:
            continue
        sid = min(sets); reps = sorted({int(r["rep"]) for r in rs if r["set_id"] == sid})
        val = lambda e: statistics.median(int(r["event_value"]) for r in rs if r["set_id"] == sid and r["ev_type"] == e
                                          and int(r["rep"]) > reps[0])
        rows.append(dict(model=pathlib.Path(f).parent.name, set_id=sid, wd_active=val("80"), wd_stalled=val("81"),
                         mac_active=val("48"), ao_active=val("64"), npu_active=val("35")))
    (pathlib.Path(out) / "mlek_wd.json").write_text(json.dumps(rows, indent=1))
    return rows


def linfit(xs: list, ys: list) -> dict:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)); st = sum((y - my) ** 2 for y in ys)
    return dict(slope=b, intercept=a, r2=1 - ss / st if st else 1.0, n=len(xs))


RNG = {}                         # config -> pass-A WD_ACTIVE RUN range, set by judge (0 in unit tests unless given)


def same(a: float, b: float, ra: float = 0, rb: float = 0) -> bool:
    """Equal WD_ACTIVE: |a - b| <= max(25, 2 % of the mean, range_a + range_b) (the Stage 4 pair-rule form)."""
    return abs(a - b) <= max(TOL_ABS, TOL_REL * (a + b) / 2, ra + rb)


def eq(wd: dict, x: str, y: str) -> bool:
    return same(wd[x], wd[y], RNG.get(x, 0), RNG.get(y, 0))


# ---- Experiment verdicts (closed sets, fixed before the board) ----------------------------------------------------
def verdict_b(wd: dict, st: dict) -> dict:
    """Experiment B: WD_ACTIVE at equal block counts and different N. BLOCK_LIKE: equal within each block-count group
    (H23 = H24; H32 = H34 = H36) and the groups differ; N_LIKE: within each group WD rises with N by more than the
    tolerance and in N's order; NEITHER otherwise. Missing -> INCOMPLETE."""
    if any(wd.get(c) is None for c in EXP_B):
        return dict(verdict="INCOMPLETE")
    groups = {}
    for c in EXP_B:
        groups.setdefault(st[c]["blocks"], []).append(c)
    flat = all(eq(wd, g[0], x) for g in groups.values() for x in g[1:])
    levels = sorted(groups)
    apart = all(not eq(wd, groups[a][0], groups[b][0]) for a, b in zip(levels, levels[1:]))
    rising = all(wd[y] > wd[x] and not eq(wd, x, y)
                 for g in groups.values() for x, y in zip(sorted(g, key=lambda c: st[c]["n_ofm"]),
                                                           sorted(g, key=lambda c: st[c]["n_ofm"])[1:]))
    v = "BLOCK_LIKE" if flat and apart else ("N_LIKE" if rising else "NEITHER")
    return dict(verdict=v, groups={str(k): v_ for k, v_ in groups.items()}, flat_within=flat, apart=apart,
                rising_with_n=rising)


def verdict_a(wd: dict, st: dict) -> dict:
    """Experiment A: WD_ACTIVE against the stream size at the same schedule. ENCODED_PROPORTIONAL: every config within
    tolerance of WD_dense x encoded/encoded_dense; STAGED_PROPORTIONAL: the same with the staged bytes (weights + bias
    and scale, the DMA lengths); CONSTANT: every config equal to dense; MONOTONE: WD falls with encoded bytes
    (strictly, beyond tolerance) but none of the above; OTHER otherwise. Checked in this order."""
    if any(wd.get(c) is None for c in EXP_A):
        return dict(verdict="INCOMPLETE")
    ref = EXP_A[0]
    pred = {c: wd[ref] * st[c]["encoded_bytes"] / st[ref]["encoded_bytes"] for c in EXP_A}
    pred_s = {c: wd[ref] * st[c]["staged_bytes"] / st[ref]["staged_bytes"] for c in EXP_A}
    fits = dict(ENCODED_PROPORTIONAL=all(same(wd[c], pred[c], RNG.get(c, 0)) for c in EXP_A),
                STAGED_PROPORTIONAL=all(same(wd[c], pred_s[c], RNG.get(c, 0)) for c in EXP_A),
                CONSTANT=all(eq(wd, c, ref) for c in EXP_A))
    satisfied = [k for k, ok in fits.items() if ok]          # priority = this order; the rest are reported, not hidden
    if satisfied:
        v = satisfied[0]
    else:
        order = sorted(EXP_A, key=lambda c: st[c]["encoded_bytes"])
        mono = all(wd[y] > wd[x] and not eq(wd, x, y) for x, y in zip(order, order[1:]))
        v = "MONOTONE" if mono else "OTHER"      # MONOTONE: direction only, not a byte model
    return dict(verdict=v, also_satisfied=satisfied[1:], predicted_encoded=pred, predicted_staged=pred_s)


def verdict_mac(mac: dict, dpu: dict) -> dict:
    """Experiment A, compute side (separate from the WD verdict): MAC_SAME if MAC_ACTIVE is identical (every measured
    RUN, every config) to dense, else MAC_CHANGED; the same for MAC_DPU_ACTIVE (DPU_SAME / DPU_CHANGED)."""
    if any(mac.get(c) is None or dpu.get(c) is None for c in EXP_A):
        return dict(verdict="INCOMPLETE")
    one = lambda d: all(len(set(d[c])) == 1 and d[c][0] == d[EXP_A[0]][0] for c in EXP_A)
    return dict(verdict=("MAC_SAME" if one(mac) else "MAC_CHANGED") + "+" + ("DPU_SAME" if one(dpu) else "DPU_CHANGED"),
                mac={c: sorted(set(mac[c])) for c in EXP_A}, dpu={c: sorted(set(dpu[c])) for c in EXP_A})


def verdict_sram(sram_rd: dict, st: dict) -> dict:
    """Secondary, exact (both experiments): SRAM read beats = spatial blocks x staged bytes / 16 for every config
    (weights re-read from the fast scratch once per spatial OFM block). HOLDS / FAILS / INCOMPLETE."""
    cfgs = sorted(set(EXP_A + EXP_B))
    if any(sram_rd.get(c) is None for c in cfgs):
        return dict(verdict="INCOMPLETE")
    bad = {c: (sram_rd[c], st[c]["spatial_blocks"] * st[c]["staged_bytes"] / BEAT) for c in cfgs
           if sram_rd[c] != st[c]["spatial_blocks"] * st[c]["staged_bytes"] / BEAT}
    return dict(verdict="HOLDS" if not bad else "FAILS", mismatches=bad)


def static(wl: str, out: str) -> dict:
    res = {}
    for c in sorted(set(EXP_A + EXP_B)):
        d = pathlib.Path(wl) if (pathlib.Path(wl) / f"{c}.compile.json").exists() else REPO / "evidence/stage4ao/workloads"
        res[c] = static_of(d, c)
        wdj = pathlib.Path(wl) / f"{c}.wd.json"
        res[c]["reference"] = json.loads(wdj.read_text())["reference"] if wdj.exists() else None
    res["_checks"] = checks(res)
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "static.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def checks(res: dict) -> dict:
    """Candidate preconditions: A keeps the reference schedule and differs in stream size only; B keeps the block and
    the stream; the golden is unambiguous (default = BUILTIN_REF kernels)."""
    ref = res["s4ao_conv1x1_h24"]
    return dict(
        a_same_schedule=all(res[c]["ofm_block"] == ref["ofm_block"] and res[c]["traversal"] == ref["traversal"]
                            and res[c]["n_kernels"] == ref["n_kernels"] and res[c]["blocks"] == ref["blocks"] for c in EXP_A),
        a_encoded_distinct=len({res[c]["encoded_bytes"] for c in EXP_A}) == len(EXP_A),
        a_staged_distinct=len({res[c]["staged_bytes"] for c in EXP_A}) == len(EXP_A),
        b_same_block=all(res[c]["ofm_block"] == ref["ofm_block"] and res[c]["traversal"] == ref["traversal"]
                         and res[c]["encoded_bytes"] == ref["encoded_bytes"] for c in EXP_B),
        b_block_groups=sorted({res[c]["blocks"] for c in EXP_B}),
        golden_unambiguous=all((res[c]["reference"] or dict(opt_vs_ref=0))["opt_vs_ref"] == 0 for c in res if not c.startswith("_")))


def predict(out: str) -> dict:
    """Pre-registered predictions from the archived Stage 4AO sweep (H24/36/54/72): WD_ACTIVE per block and per
    element, then the Experiment B / A configs under each hypothesis (values reported next to the verdicts)."""
    inv = json.loads((pathlib.Path(out) / "inventory.json").read_text())
    st = json.loads((pathlib.Path(out) / "static.json").read_text())
    sweep = [r for r in inv if r["stage"] == "stage4ao" and r["config"].startswith("s4ao_conv1x1_h") and r["all_valid"]]
    fb = linfit([r["blocks"] for r in sweep], [r["wd_active"] for r in sweep])
    fn = linfit([r["n_ofm"] for r in sweep], [r["wd_active"] for r in sweep])
    res = dict(fit_blocks=fb, fit_n=fn, tolerance=dict(abs=TOL_ABS, rel=TOL_REL),
               exp_b={c: dict(blocks=st[c]["blocks"], n_ofm=st[c]["n_ofm"],
                              by_blocks=fb["intercept"] + fb["slope"] * st[c]["blocks"],
                              by_n=fn["intercept"] + fn["slope"] * st[c]["n_ofm"]) for c in EXP_B},
               exp_a={c: dict(encoded_bytes=st[c]["encoded_bytes"]) for c in EXP_A})
    (pathlib.Path(out) / "predictions.json").write_text(json.dumps(res, indent=1))
    return res


def repro_gate(root: str, wl: str, ref: str, caps_ref: str | None = None) -> dict:
    """Boot 1 (s4ao_conv1x1_h24) against the Stage 4AO-E A1 boot 394 copy: stage4aoe.repro_gate (validity,
    K.reproduce, AO within 35.34) and WD_ACTIVE equal by same() with both RUN ranges."""
    r = AOE.repro_gate(root, wl, ref, caps_ref)
    if r["verdict"] != "PASS":
        return dict(r, wd_ok=None)
    now = K.summary_of(pathlib.Path(root) / "conds" / AOE.REPRO_CFG / "wfe", 1)["metrics"]
    was = K.summary_of(pathlib.Path(ref), 1)["metrics"]
    wd_ok = same(now["A_80"], was["A_80"], now["A_80_range"], was["A_80_range"])
    return dict(r, verdict="PASS" if wd_ok else "FAIL", wd=now["A_80"], wd_ref=was["A_80"], wd_ok=wd_ok)


def judge(root: str, wl: str, pred_path: str, out: str, caps_ref: str | None = None) -> dict:
    """Validity per config = stage4aoe.config_result (A1 identity, workload sha256, PASS_EXACT vs <cfg>.ref_ofm.bin,
    RUN validity, stability); verdicts only from VALID and stable configs."""
    st = json.loads((pathlib.Path(out) / "static.json").read_text())
    res = {c: AOE.config_result(pathlib.Path(root), pathlib.Path(wl), c, caps_ref) for c in sorted(set(EXP_A + EXP_B))}
    ok = {c: r.get("verdict") == "VALID" and r.get("stable") for c, r in res.items()}
    wd = {c: (r["metrics"]["A_80"] if ok[c] else None) for c, r in res.items()}
    sr = {c: (r["metrics"]["B_130"] if ok[c] else None) for c, r in res.items()}
    RNG.clear(); RNG.update({c: r["metrics"]["A_80_range"] for c, r in res.items() if ok[c]})
    runs = {c: K.summary_of(pathlib.Path(root) / "conds" / c / "wfe", 1) if ok[c] else None for c in res}
    mac = {c: (runs[c]["mac_active"] if runs[c] else None) for c in res}
    dpu = {c: (runs[c]["mac_dpu_active"] if runs[c] else None) for c in res}
    summary = dict(exp_a=verdict_a(wd, st), exp_a_compute=verdict_mac(mac, dpu), exp_b=verdict_b(wd, st),
                   sram_rule=verdict_sram(sr, st), wd_active=wd,
                   configs={c: {k: v for k, v in r.items() if k != "identity"} for c, r in res.items()})
    (pathlib.Path(out) / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd in ("repro-gate", "boot-check"):
        r = repro_gate(*a[:4]) if cmd == "repro-gate" else AOE.boot_check(*a[:4])
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    r = dict(inventory=lambda: (inventory(a[0]), mlek_wd(a[0]))[0], static=lambda: static(*a[:2]), predict=lambda: predict(a[0]),
             judge=lambda: judge(*a[:5]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
