#!/usr/bin/env python3
"""Stage 4K (docs/plan/stage4k_conv_kernel_plan.md, contract draft evidence/stage4k/contract_draft.md): MAC activity of
the 1x1 and 3x3 Conv (24x24, Cout 96, stride 1, SAME (1x1: VALID = the same op), RELU6, INT8) at Cin 16/32/40/48/64.
TA profile 1, driver runner image 70090f1 (DDR/EXT placement, DRWL word 7 = 0), Vela 5.0.0 with MLEK's options.

  python3 host/analysis/stage4k.py static <workloads dir> <out dir>       compile facts, block fill, 1x1 SAME control
  python3 host/analysis/stage4k.py prior <out dir>                        the existing 1x1 numbers recomputed from raw
  python3 host/analysis/stage4k.py predict <workloads dir> <out dir>      pre-registered MAC_ACTIVE hypotheses
  python3 host/analysis/stage4k.py repro-gate <campaign root> <workloads dir> [<reference wfe folder>]
                                                                          boot 1 (1x1 Cin 16): exit 0 = PASS
  python3 host/analysis/stage4k.py boot-check <campaign root> <workloads dir> <config> [<reference capabilities.json>]
                                                                          after every boot: exit 0 = Gate C
  python3 host/analysis/stage4k.py judge <campaign root> <workloads dir> <predictions.json> <out dir>

MAC definitions (per config, from the compiled model; never from a counter):
  nominal  H*W*Cout*k*k*Cin = the tflite N_MAC = Vela's MAC count (SAME: padded taps counted)
  valid    in-bound taps only: (k*H - t)(k*W - t)*Cin*Cout, t = (k//2)(k//2 + 1); = nominal for 1x1
  c16      nominal with Cin rounded up to a multiple of 16 (a normaliser taken from 4C-2b, not a hardware unit)
Peak: 1024 MACs per clock cycle = the FI101 configuration (Arm 102684 Issue 03 "NPU Configuration (MACs/CC)" and
CONFIG.macs_per_cc = 10 read on the board). An operation-specific TRM peak was not available; "peak-relative" is
MACs / (1024 x cycles), a MAC-count-to-cycle ratio, not a measured lane occupancy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4c1 as C1  # noqa: E402
import stage4c2 as C2  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
H = W = 24
COUT = 96
CINS = (16, 32, 40, 48, 64)
K1 = {16: "s4_conv_base", 32: "s4c2_conv_cin32", 40: "s4c2_conv_cin40", 48: "s4c2_conv_cin48", 64: "s4c2_conv_cin64"}
K3 = {c: f"s4k_conv3x3_cin{c}" for c in CINS}
K1_SAME = {c: f"s4k_conv1x1same_cin{c}" for c in CINS}
CONFIGS = {**{v: (1, c) for c, v in K1.items()}, **{v: (3, c) for c, v in K3.items()}}
ORDER = [x for c in CINS for x in (K1[c], K3[c])]     # = plan.txt boot order: 1x1 then 3x3 at each Cin; first = gate
BASE = K1[16]
PEAK = 1024
FLOOR = 0.01
# Existing 1x1 data (Phase 1). image 83398c7: Stage 4 boot 330, 4C-2 boots 344-346, 4C-2b 348-349; image 70090f1:
# the placement A run (boot 367), the same image this stage uses.
PRIOR = {
    K1[16]: [("stage4_b330_83398c7", "evidence/stage4/raw"), ("stage4c2_b344_83398c7", "evidence/stage4c2/raw"),
             ("placement_a_b367_70090f1", "evidence/stage4_placement/raw/evsweep_s4p_run_a", "s4p_conv_base_ddr")],
    K1[32]: [("stage4c2_b345_83398c7", "evidence/stage4c2/raw")],
    K1[40]: [("stage4c2b_b348_83398c7", "evidence/stage4c2b/raw")],
    K1[48]: [("stage4c2b_b349_83398c7", "evidence/stage4c2b/raw")],
    K1[64]: [("stage4c2_b346_83398c7", "evidence/stage4c2/raw"), ("stage4c2b_b350_83398c7", "evidence/stage4c2b/raw")],
}
GATE_REF = "placement_a_b367_70090f1"    # boot-1 gate: same image, same blob, same counters


def macs(k: int, cin: int) -> dict:
    t = (k // 2) * (k // 2 + 1)
    c16 = math.ceil(cin / 16) * 16
    return dict(nominal=H * W * COUT * k * k * cin, valid=(k * H - t) * (k * W - t) * cin * COUT,
                c16=H * W * COUT * k * k * c16)


def hypotheses(k: int, cin: int) -> dict:
    """MAC_ACTIVE predicted by rate (384 / 768 effective MACs per MAC-active cycle, the two rates seen on the 1x1) x
    amount (nominal / valid taps / Cin rounded up to 16). Closed set, values only; no hypothesis is a mechanism."""
    m = macs(k, cin)
    valid_c16 = m["valid"] * math.ceil(cin / 16) * 16 // cin
    amounts = dict(nominal=m["nominal"], valid=m["valid"], c16=m["c16"], valid_c16=valid_c16)
    return {f"R{r}_{a}": v / r for r in (384, 768) for a, v in amounts.items()}


def fill(ofm: list, blk: list) -> float:
    used = 1
    for o, b in zip(ofm, blk):
        used *= math.ceil(o / b) * b
    return math.prod(ofm) / used


def static_one(wl: pathlib.Path, cfg: str) -> dict:
    st = C2.static_one(wl, cfg)
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    ks = C1.kernels((wl / f"{cfg}.drwl.cms.bin").read_bytes())
    ofm = comp["ofm_shape"][1:]
    blk = [int(x) for x in comp["ofm_block"].split("x")]
    ub = [int(x) for x in comp["ofm_ublock"].split("x")]
    k, cin = CONFIGS.get(cfg, (None, comp["ifm_shape"][-1]))
    kernel_hw = [list(t) for t in sorted({(x["kernel_height_m1"] + 1, x["kernel_width_m1"] + 1) for x in ks})]
    per_kernel_ub = [fill([ofm[0], ofm[1], r["ofm_slice"]], ub) for r in st["kernels"]]
    m = macs(kernel_hw[0][0], cin) if len(kernel_hw) == 1 else {}
    return dict({x: st[x] for x in ("config", "cin", "n_mac", "ofm_block", "ifm_block", "ofm_ublock", "traversal",
                                     "n_kernels", "kernels", "ofm_ublocks", "ublock_x_steps", "weight_bytes",
                                     "vela_npu_cycles", "vela_mac_cycles", "vela_op_cycles", "gate_b", "model_sha256",
                                     "cms_sha256", "drwl_sha256")},
                kernel=k, kernel_hw=kernel_hw, macs=m, valid_tap_fraction=m["valid"] / m["nominal"] if m else None,
                block_fill=fill(ofm, blk),
                ublock_fill=sum(r["ofm_slice"] * ofm[0] * ofm[1] for r in st["kernels"])
                / sum(math.ceil(ofm[0] / ub[0]) * ub[0] * math.ceil(ofm[1] / ub[1]) * ub[1]
                      * math.ceil(r["ofm_slice"] / ub[2]) * ub[2] for r in st["kernels"]),
                ublock_fill_per_kernel=per_kernel_ub,
                ifm_block_depth_fill=[r["ifm_depth"] / (r["ifm_depth_steps"] * int(comp["ifm_block"].split("x")[2]))
                                      for r in st["kernels"]],
                vela_ao_cycles=comp["vela_ao_cycles"], cms_len=comp["cms_len"],
                weight_stream_lengths=[r["weight_lengths"] for r in st["kernels"]],
                dma_lengths=[r["dma_before"] for r in st["kernels"]], acc_format=sorted({r["acc_format"] for r in st["kernels"]}),
                vela_macs_per_mac_cycle=st["n_mac"] / int(comp["vela_mac_cycles"]) if comp["vela_mac_cycles"] else None,
                ifm_sha256=json.loads((wl / f"{cfg}.drwl.json").read_text())["ifm_sha256"],
                schedule=st["schedule"])


def static(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {c: static_one(wl, c) for c in ORDER}
    for k in (1, 3):
        cfgs = [c for c in ORDER if CONFIGS[c][0] == k]
        sch = [res[c]["schedule"] for c in cfgs]
        res[f"switches_k{k}"] = [f"{CONFIGS[a][1]}->{CONFIGS[b][1]}" for a, b, x, y in
                                 zip(cfgs, cfgs[1:], sch, sch[1:]) if x != y]
    same = lambda a, b: (wl / a).read_bytes() == (wl / b).read_bytes()
    res["k1_same_control"] = {c: dict(cms=same(f"{K1[c]}.drwl.cms.bin", f"{K1_SAME[c]}.drwl.cms.bin"),
                                      cpu_ofm=same(f"{K1[c]}.drwl.tflite_ofm.bin", f"{K1_SAME[c]}.drwl.tflite_ofm.bin"))
                              for c in CINS}
    res["same_ifm_per_cin"] = {c: res[K1[c]]["ifm_sha256"] == res[K3[c]]["ifm_sha256"] for c in CINS}
    o.mkdir(parents=True, exist_ok=True)
    (o / "static.json").write_text(json.dumps(res, indent=1))
    cols = ["config", "kernel", "cin", "traversal", "ofm_block", "ifm_block", "ofm_ublock", "n_kernels", "ofm_ublocks",
            "ublock_x_steps", "block_fill", "ublock_fill", "weight_bytes", "vela_npu_cycles", "vela_mac_cycles",
            "vela_ao_cycles", "vela_op_cycles", "vela_macs_per_mac_cycle", "valid_tap_fraction", "cms_len", "drwl_sha256"]
    with open(o / "stage4k_static.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + ["macs_nominal", "macs_valid", "macs_c16"], lineterminator="\n")
        w.writeheader()
        for c in ORDER:
            r = res[c]
            w.writerow(dict({x: r[x] for x in cols}, macs_nominal=r["macs"]["nominal"], macs_valid=r["macs"]["valid"],
                            macs_c16=r["macs"]["c16"]))
    return res


def folder_of(entry: tuple, cfg: str) -> pathlib.Path:
    return REPO / entry[1] / "conds" / (entry[2] if len(entry) > 2 else cfg) / "wfe"


def summary_of(folder: pathlib.Path, n_mac: int) -> dict:
    runs = S4.load(folder, 1)
    m = S4.metrics(runs, n_mac)
    out = hashlib.sha256((folder / "output.bin").read_bytes()).hexdigest() if (folder / "output.bin").exists() else None
    return dict(runs=runs, metrics=m, output_sha256=out,
                mac_active=[r["ev"].get(48) for r in runs.get(1, [])],
                mac_dpu_active=[r["ev"].get(51) for r in runs.get(1, [])])


def prior(out: str) -> dict:
    """Phase 1: the existing 1x1 numbers recomputed from the archived raw RUNs (pass-A medians, measured RUNs only)."""
    res = {}
    for cfg, entries in PRIOR.items():
        k, cin = CONFIGS[cfg]
        n = macs(k, cin)["nominal"]
        for e in entries:
            s = summary_of(folder_of(e, cfg), n)
            m = s["metrics"]
            res[f"{cfg}@{e[0]}"] = dict(
                cin=cin, macs=n, mac_active=s["mac_active"], mac_dpu_active=s["mac_dpu_active"],
                npu_active=m["A_35"], npu_active_range=m["A_35_range"],
                macs_per_mac_active=n / m["A_48"] if m["A_48"] else None,
                macs_per_mac_dpu_active=n / m["A_51"] if m["A_51"] else None,
                dpu_over_mac=m["A_51"] / m["A_48"] if m["A_48"] else None,
                mac_active_over_npu_active=m["A_48"] / m["A_35"] if m["A_35"] else None,
                pass_b={c: m[f"B_{c}"] for c in S4.PASS_B[1:]}, output_sha256=s["output_sha256"])
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "prior.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def predict(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {}
    for c in ORDER:
        k, cin = CONFIGS[c]
        st = static_one(wl, c)
        assert st["n_mac"] == macs(k, cin)["nominal"], c       # the compiled model's MACs = the definition
        h = hypotheses(k, cin)
        vals = list(h.values())
        res[c] = dict(kernel=k, cin=cin, macs=macs(k, cin), hypotheses=h,
                      distinct={x: vals.count(v) == 1 for x, v in h.items()},
                      static={x: st[x] for x in ("traversal", "ofm_block", "ifm_block", "ofm_ublock", "ofm_ublocks",
                                                  "ublock_x_steps", "n_kernels", "weight_bytes", "drwl_sha256")})
    o.mkdir(parents=True, exist_ok=True)
    (o / "predictions.json").write_text(json.dumps(res, indent=1))
    return res


def verdict(macs_per_run: list, valid: bool, out_ok: bool, hyp: dict) -> str:
    """4C-2b rule: INVALID > MEASUREMENT_UNSTABLE > MATCH:<every hypothesis equal to all RUNs> > NONE_MATCHED."""
    if not (valid and out_ok) or len(macs_per_run) != 4:
        return "INVALID"
    if len(set(macs_per_run)) != 1:
        return "MEASUREMENT_UNSTABLE"
    hit = [x for x, v in hyp.items() if macs_per_run[0] == v]
    return "MATCH:" + "+".join(hit) if hit else "NONE_MATCHED"


def reproduce(now: dict, ref: dict) -> dict:
    """Same blob on another boot: MAC_ACTIVE / MAC_DPU_ACTIVE equal in every measured RUN, output sha256 equal, every
    counter constant in both equal, NPU_ACTIVE pass A |median difference| <= max(1 % of the reference, either range)."""
    a, b = C1.constant_counters(now["runs"]), C1.constant_counters(ref["runs"])
    diff = {f"set{k[0]}_ev{k[1]}": (b[k], a[k]) for k in set(a) & set(b) if a[k] != b[k]}
    na, nb = now["metrics"], ref["metrics"]
    t = max(FLOOR * nb["A_35"], nb["A_35_range"] or 0, na["A_35_range"] or 0)
    checks = dict(mac=len(set(now["mac_active"])) == 1 and set(now["mac_active"]) == set(ref["mac_active"]),
                  dpu=len(set(now["mac_dpu_active"])) == 1 and set(now["mac_dpu_active"]) == set(ref["mac_dpu_active"]),
                  output=now["output_sha256"] is not None and now["output_sha256"] == ref["output_sha256"],
                  constant_counters=not diff, npu_active=abs(na["A_35"] - nb["A_35"]) <= t)
    return dict(ok=all(checks.values()), checks=checks, differing_constant_counters=diff,
                npu_active=(nb["A_35"], na["A_35"]), tolerance=t, compared=len(set(a) & set(b)))


REGIONCFG_DDR, QCONFIG = 0x15F, 3          # region 1 on the EXT port (DDR placement), as the placement A run
CAPS_REF = "evidence/stage4_placement/raw/evsweep_s4p_run_a/conds/s4p_conv_base_ddr/capabilities.json"


def identity(folder: pathlib.Path, wl: pathlib.Path, cfg: str, caps_ref: str | None = None) -> dict:
    """The boot ran this config on the fixed set-up: every RUN (warm-up included) carries this DRWL's model length,
    schema 4, placement 0 (DDR/EXT), REGIONCFG 0x15F / QCONFIG 3 at the IRQ, one IRQ, one output CRC (so the
    warm-up RUN's output equals the measured ones, which output_check compares byte by byte with the CPU reference)
    and the output length of the CPU reference; capabilities.json (TA registers, AXI, MEM_ATTR, fast memory, NPU
    config) equals the placement A boot of the same image."""
    import drwl
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    model_len = drwl.parse((wl / f"{cfg}.drwl").read_bytes())["model_len"]
    n_out = len((wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes())
    recs = [x["record"] for x in raw]
    caps_path = folder.parent / "capabilities.json"
    ref = json.loads(pathlib.Path(caps_ref or REPO / CAPS_REF).read_text())
    caps = json.loads(caps_path.read_text()) if caps_path.exists() else {}
    checks = dict(runs=len(raw) == 10,
                  model_len=bool(recs) and all(r.get("model_len") == model_len for r in recs),
                  schema=all(r.get("schema") == 4 for r in recs),
                  placement=all(r.get("placement") == 0 for r in recs),
                  regioncfg=all(r.get("regioncfg_irq") == REGIONCFG_DDR and r.get("qconfig_irq") == QCONFIG for r in recs),
                  irq=all(r.get("irq_count") == 1 for r in recs),
                  one_crc=len({x.get("output_crc32") for x in raw}) == 1,
                  output_len=all(x.get("output_len") == n_out for x in raw),
                  capabilities=caps == ref)
    return dict(ok=all(checks.values()), checks=checks,
                caps_diff={k: (ref.get(k), caps.get(k)) for k in set(ref) | set(caps) if ref.get(k) != caps.get(k)})


def config_result(root: pathlib.Path, wl: pathlib.Path, cfg: str, hyp: dict, caps_ref: str | None = None) -> dict:
    """Gate C of this stage (owner 2026-11-14: output must be PASS_EXACT): both passes with 4 measured RUNs, every
    RUN valid, output byte-identical to the CPU reference, and identity() above."""
    folder = root / "conds" / cfg / "wfe"
    if not (folder / "raw_runs.json").exists():
        return dict(verdict="NOT_MEASURED")
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    s = summary_of(folder, comp["n_mac"])
    oc = S4.output_check(folder, comp, (wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), s["runs"])
    ident = identity(folder, wl, cfg, caps_ref)
    valid = all(r["valid"] for rs in s["runs"].values() for r in rs) and sorted(s["runs"]) == [1, 2] \
        and all(len(rs) == 4 for rs in s["runs"].values()) and ident["ok"]
    out_ok = oc["verdict"] == "PASS_EXACT"
    return dict(s, comp=comp, output=oc, identity=ident, runs_valid=valid,
                gate_c="PASS" if valid and out_ok else "FAIL", verdict=verdict(s["mac_active"], valid, out_ok, hyp))


def gate_ref(ref: str | None = None) -> dict:
    """The boot-1 reference: the placement A run (boot 367) folder, or a copy of it given on the board."""
    folder = pathlib.Path(ref) if ref else folder_of(next(x for x in PRIOR[BASE] if x[0] == GATE_REF), BASE)
    return summary_of(folder, macs(1, 16)["nominal"])


def repro_gate(root: str, wl: str, ref: str | None = None) -> dict:
    """Boot 1 (1x1 Cin 16) on image 70090f1 against the placement A run of the same image and blob (boot 367).
    Fail -> the campaign stops before any 3x3 boot."""
    caps = str(pathlib.Path(ref).parent / "capabilities.json") if ref else None
    r = config_result(pathlib.Path(root), pathlib.Path(wl), BASE, hypotheses(1, 16), caps)
    if r["verdict"] in ("NOT_MEASURED", "INVALID"):
        return dict(verdict="FAIL", why=r["verdict"])
    rep = reproduce(r, gate_ref(ref))
    return dict(verdict="PASS" if rep["ok"] and r["output"]["verdict"] == "PASS_EXACT" else "FAIL", **rep,
                output=r["output"]["verdict"])


def boot_check(root: str, wl: str, cfg: str, caps_ref: str | None = None) -> dict:
    """Stop rule after each boot: config_result's Gate C (PASS_EXACT, valid RUNs, identity). FAIL -> the session
    stops; later configs stay NOT_MEASURED."""
    r = config_result(pathlib.Path(root), pathlib.Path(wl), cfg, {}, caps_ref)
    return dict(config=cfg, verdict="PASS" if r.get("gate_c") == "PASS" else "FAIL",
                runs_valid=r.get("runs_valid"), output=r.get("output", {}).get("verdict"), why=r.get("verdict"),
                identity=r.get("identity"))


def exact(r: dict) -> int | None:
    """The MAC_ACTIVE of a config if all four measured RUNs agree, else None."""
    v = r.get("mac_active") or []
    return v[0] if len(v) == 4 and len(set(v)) == 1 and r.get("gate_c") == "PASS" else None


def granularity(res: dict, cfgs: dict) -> dict:
    """RQ2 over one kernel's configs (MAC_ACTIVE exact): PROPORTIONAL_TO_CIN (MAC_ACTIVE x 16 = MAC_ACTIVE(16) x Cin),
    CONSISTENT_WITH_CEIL16 (= MAC_ACTIVE(16) x roundup(Cin, 16)), both / NEITHER; reported per schedule group too."""
    m = {c: exact(res[n]) for c, n in cfgs.items()}
    if None in m.values():
        return dict(verdict="NOT_JUDGED", mac_active=m)
    prop = all(m[c] * 16 == m[16] * c for c in m)
    c16 = all(m[c] * 16 == m[16] * math.ceil(c / 16) * 16 for c in m)
    v = "PROPORTIONAL_TO_CIN" if prop and not c16 else "CONSISTENT_WITH_CEIL16" if c16 and not prop else \
        "BOTH" if prop else "NEITHER"
    return dict(verdict=v, mac_active=m, step_40_48_equal=m[40] == m[48])


def kernel_compare(res: dict, st: dict, cin: int) -> dict:
    """RQ1 at one Cin: effective MACs per MAC-active cycle, 1x1 vs 3x3 (nominal and valid-tap MACs). Labelled with what
    else differs (traversal, OFM/IFM block): no kernel-size effect is claimed from a pair where they differ."""
    a, b = res[K1[cin]], res[K3[cin]]
    ma, mb = exact(a), exact(b)
    sa, sb = st[K1[cin]], st[K3[cin]]
    same_trav = sa["traversal"] == sb["traversal"]
    label = ("SAME_TRAVERSAL_SAME_BLOCKS" if same_trav and (sa["ofm_block"], sa["ifm_block"]) == (sb["ofm_block"], sb["ifm_block"])
             else "SAME_TRAVERSAL_BLOCKS_DIFFER" if same_trav else "TRAVERSAL_DIFFERS")
    if ma is None or mb is None:
        return dict(verdict="NOT_JUDGED", comparability=label)
    r1, r3 = macs(1, cin)["nominal"] / ma, macs(3, cin)["nominal"] / mb
    return dict(verdict="SAME_RATE" if r1 == r3 else "RATE_3X3_HIGHER" if r3 > r1 else "RATE_3X3_LOWER",
                comparability=label, rate_1x1=r1, rate_3x3=r3, rate_3x3_valid_taps=macs(3, cin)["valid"] / mb,
                ratio=r3 / r1, traversal=(sa["traversal"], sb["traversal"]), ofm_block=(sa["ofm_block"], sb["ofm_block"]),
                ifm_block=(sa["ifm_block"], sb["ifm_block"]))


def npu_pair(res: dict, b: str, v: str) -> dict:
    """Stage 4 pair rule on NPU_ACTIVE (pass A), pass B as a check (opposite signs -> UNRESOLVED)."""
    if "PASS" != res[b].get("gate_c") or "PASS" != res[v].get("gate_c"):
        return dict(verdict="EXCLUDED")
    cb = dict(runs=res[b]["runs"], macs=res[b]["comp"]["n_mac"], compile=res[b]["comp"], metrics=res[b]["metrics"])
    cv = dict(runs=res[v]["runs"], macs=res[v]["comp"]["n_mac"], compile=res[v]["comp"], metrics=res[v]["metrics"])
    pa = S4.pair(cb, cv)
    pb = S4.pair(dict(cb, runs={1: cb["runs"][2], 2: cb["runs"][2]}), dict(cv, runs={1: cv["runs"][2], 2: cv["runs"][2]}))
    opp = (pa["npu_active_variant"] - pa["npu_active_base"]) * (pb["npu_active_variant"] - pb["npu_active_base"]) < 0
    mb, mv = res[b]["metrics"]["A_48"], res[v]["metrics"]["A_48"]
    return dict(verdict="UNRESOLVED" if opp else pa["verdict"], pass_a=pa, directions_opposite=opp,
                pass_b_npu_active_change_pct=pb["npu_active_change_pct"],
                mac_ratio=cv["macs"] / cb["macs"], mac_active_ratio=mv / mb if mb else None,
                npu_active_ratio=pa["npu_active_variant"] / pa["npu_active_base"])


def judge(root: str, wl: str, pred_path: str, out: str) -> dict:
    root, wl, o = pathlib.Path(root), pathlib.Path(wl), pathlib.Path(out)
    pred = json.loads(pathlib.Path(pred_path).read_text())
    st = {c: static_one(wl, c) for c in ORDER}
    res = {c: config_result(root, wl, c, pred[c]["hypotheses"]) for c in ORDER}
    gate = repro_gate(str(root), str(wl))
    repro = {}
    for c in K1.values():
        if res[c].get("gate_c") != "PASS":
            repro[c] = dict(verdict="NOT_JUDGED")
            continue
        k, cin = CONFIGS[c]
        reps = {e[0]: reproduce(res[c], summary_of(folder_of(e, c), macs(k, cin)["nominal"])) for e in PRIOR[c]}
        repro[c] = dict(verdict="REPRODUCED" if all(x["ok"] for x in reps.values()) else "REPRO_MISMATCH", refs=reps)
    if gate["verdict"] != "PASS":
        for c in ORDER:
            res[c]["verdict"] = "NOT_INTERPRETED (REPRO_GATE)"
    ok = gate["verdict"] == "PASS"
    rq = dict(
        rq1={cin: kernel_compare(res, st, cin) if ok else dict(verdict="NOT_INTERPRETED") for cin in CINS},
        rq2=dict(k1=granularity(res, K1) if ok else dict(verdict="NOT_INTERPRETED"),
                 k3=granularity(res, K3) if ok else dict(verdict="NOT_INTERPRETED")),
        rq4=dict(cin_pairs={f"{a}->{b}": npu_pair(res, a, b) if ok else dict(verdict="NOT_INTERPRETED")
                            for t in (K1, K3) for a, b in zip(list(t.values()), list(t.values())[1:])},
                 kernel_pairs={f"{K1[c]}->{K3[c]}": npu_pair(res, K1[c], K3[c]) if ok else dict(verdict="NOT_INTERPRETED")
                               for c in CINS}))
    rows = []
    for c in ORDER:
        r, m, s = res[c], res[c].get("metrics", {}), st[c]
        n, mac = s["macs"], m.get("A_48")
        na = m.get("A_35")
        rows.append(dict(
            config=c, kernel=CONFIGS[c][0], cin=CONFIGS[c][1], verdict=r["verdict"], gate_c=r.get("gate_c"),
            output=r.get("output", {}).get("verdict"), traversal=s["traversal"], ofm_block=s["ofm_block"],
            ifm_block=s["ifm_block"], ofm_ublock=s["ofm_ublock"], macs_nominal=n["nominal"], macs_valid=n["valid"],
            npu_active=na, npu_active_range=m.get("A_35_range"), mac_active=mac, mac_dpu_active=m.get("A_51"),
            dpu_over_mac=m.get("A_51") / mac if mac else None,
            macs_per_mac_active=n["nominal"] / mac if mac else None,
            valid_macs_per_mac_active=n["valid"] / mac if mac else None,
            macs_per_npu_active=n["nominal"] / na if na else None,
            valid_macs_per_npu_active=n["valid"] / na if na else None,
            mac_active_over_npu_active=mac / na if mac and na else None,
            peak_rel_mac_active=n["nominal"] / (PEAK * mac) if mac else None,
            peak_rel_npu_active=n["nominal"] / (PEAK * na) if na else None,
            relu6_cap_count=r.get("output", {}).get("npu_at_relu6_cap"),
            relu6_cap_share=(r.get("output", {}).get("npu_at_relu6_cap") or 0) / 55296 if r.get("output") else None,
            ao_active=m.get("A_64"), wd_active=m.get("A_80"), wd_stalled=m.get("A_81"),
            **{f"b{x}": m.get(f"B_{x}") for x in S4.PASS_B[1:]}, ev53=m.get("A_53"), ev55=m.get("A_55")))
    o.mkdir(parents=True, exist_ok=True)
    with open(o / "stage4k_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    summary = dict(repro_gate=gate, reproduction=repro, rq=rq, table=rows,
                   configs={c: {k: x for k, x in r.items() if k not in ("runs", "comp")} for c, r in res.items()})
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd in ("repro-gate", "boot-check"):
        r = repro_gate(*a[:3]) if cmd == "repro-gate" else boot_check(*a[:4])
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    r = dict(static=lambda: static(*a[:2]), prior=lambda: prior(a[0]), predict=lambda: predict(*a[:2]),
             judge=lambda: judge(*a[:4]))[cmd]()
    print(json.dumps(r, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
