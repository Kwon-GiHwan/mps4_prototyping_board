#!/usr/bin/env python3
"""Stage 6C (evidence/stage6c/contract.md): F1-F5 operator families on the FI101 board, passes A (units), B (traffic),
C (requests / ports), TA profile 1, runner image 14077be, placement 0. Validity reuses the Stage 6B-B / E2B checks and
the shared identity; this stage adds the three-pass layout, pass-C metrics and the per-shape verdicts.

  python3 stage6c.py manifest <workloads dir> <image dir> <compile_facts.json>
  python3 stage6c.py boot-check <run root> <workloads dir> <key>          # rc 1 -> the session stops
  python3 stage6c.py repro-gate <run root> <workloads dir> <boot 375 wfe dir>
  python3 stage6c.py judge <run root> <workloads dir> <boot 375 wfe dir> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4k as K  # noqa: E402
import stage6bb as BB  # noqa: E402
import stage6be2b as E2B  # noqa: E402

MANIFEST = "s6c_manifest.json"
PASS_C = [35, 131, 142, 387, 640, 642, 656, 658]
SETS = {1: S4.PASS_A, 2: S4.PASS_B, 3: PASS_C}
N_RUNS = 15
TOL = 0.01
VELA_BAND = 0.10                                   # 6C-0 direction rule: within +-10 % = agreement
F4_RATE = (384, 1024)
ORDER = [("REF", 468), ("s6c_f1_rep", 469), ("s6c_f1_cin16", 470), ("s6c_f2_rep", 471), ("s6c_f2_c16", 472),
         ("s6c_f3_rep", 473), ("s6c_f3_cin16", 474), ("s6c_f4_rep", 475), ("s6c_f5_rep", 476)]
PAIRS = {"F1": ("s6c_f1_rep", "s6c_f1_cin16"), "F2": ("s6c_f2_rep", "s6c_f2_c16"), "F3": ("s6c_f3_rep", "s6c_f3_cin16")}
SINGLE = {"F4": "s6c_f4_rep", "F5": "s6c_f5_rep"}
# TFLite N_MAC (results/fi101_stage6m/operator_mapping.csv for the representatives; controls by the changed dimension)
N_MAC = {"s6c_f1_rep": 884736, "s6c_f1_cin16": 884736 * 4, "s6c_f2_rep": 663552, "s6c_f2_c16": 663552 * 2,
         "s6c_f3_rep": 32832, "s6c_f3_cin16": 288 * 128, "s6c_f4_rep": 2368000000, "s6c_f5_rep": 2744000}
CIN = {"s6c_f1_rep": 4, "s6c_f1_cin16": 16, "s6c_f2_rep": 8, "s6c_f2_c16": 16, "s6c_f3_rep": 114, "s6c_f3_cin16": 128,
       "s6c_f4_rep": 250, "s6c_f5_rep": 1}
STOP = ("CONFIG_MISMATCH", "UNMEASURED")


# ---- pure rules -------------------------------------------------------------------------------------------------------
def tol(base: float, ranges: list) -> float:
    return max(TOL * base, sum(r or 0 for r in ranges))


def measurement(status: str) -> str:
    if status == "VALID":
        return "VALID"
    if status in ("UNSTABLE", "INVALID_PMU"):
        return "PARTIAL_VALID"
    return "MEASUREMENT_INVALID"


def compute_pair(mac_rep, mac_ctl, both_valid: bool) -> str:
    if not both_valid or not mac_rep or mac_ctl is None:
        return "INSUFFICIENT_EVIDENCE"
    return "PREDICTION_SUPPORTED" if abs(mac_ctl - mac_rep) <= TOL * mac_rep else "PREDICTION_REFUTED"


def compute_f4(n_mac: float, mac_active, valid: bool) -> str:
    if not valid or not mac_active:
        return "INSUFFICIENT_EVIDENCE"
    return "PREDICTION_SUPPORTED" if F4_RATE[0] <= n_mac / mac_active <= F4_RATE[1] else "PREDICTION_REFUTED"


def pipeline_pair(npu_rep, r_rep, npu_ctl, r_ctl, both_valid: bool) -> dict:
    if not both_valid or npu_rep is None or npu_ctl is None:
        return dict(verdict="MECHANISM_UNRESOLVED")
    d, t = npu_ctl - npu_rep, tol(npu_rep, [r_rep, r_ctl])
    return dict(verdict="CONTROLLED_EFFECT_OBSERVED" if abs(d) > t else "ASSOCIATION_ONLY", d_npu=d, tol=t)


def pipeline_single(valid: bool) -> str:
    return "ASSOCIATION_ONLY" if valid else "MECHANISM_UNRESOLVED"


def vela_class(npu, vela, valid: bool) -> str:
    if not valid or not npu or not vela:
        return "INSUFFICIENT_EVIDENCE"
    r = npu / vela
    if r < 1 - VELA_BAND:
        return "OVERESTIMATION"
    if r > 1 + VELA_BAND:
        return "UNDERESTIMATION"
    return "ESTIMATE_AGREEMENT"


def h_vela_f12(classes: list[str]) -> str:
    """F1/F2 predicted OVERESTIMATION (NHWC IFM read dominates Vela's DRAM term)."""
    c = [x for x in classes if x != "INSUFFICIENT_EVIDENCE"]
    if not c:
        return "INSUFFICIENT_EVIDENCE"
    if "UNDERESTIMATION" in c:
        return "PREDICTION_REFUTED"
    return "PREDICTION_SUPPORTED" if all(x == "OVERESTIMATION" for x in c) else "INSUFFICIENT_EVIDENCE"


def h_vela_f3(ratios: list[float]) -> str:
    """F3 predicted board/Vela > 1.0 (refuted below 0.9)."""
    if not ratios:
        return "INSUFFICIENT_EVIDENCE"
    if any(r < 1 - VELA_BAND for r in ratios):
        return "PREDICTION_REFUTED"
    return "PREDICTION_SUPPORTED" if all(r > 1.0 for r in ratios) else "INSUFFICIENT_EVIDENCE"


def h_pipeline(ratio: dict) -> str:
    """Observational: NPU/MAC of F1, F2 representatives above F3, F4 representatives."""
    a = [ratio.get(k) for k in ("s6c_f1_rep", "s6c_f2_rep")]
    b = [ratio.get(k) for k in ("s6c_f3_rep", "s6c_f4_rep")]
    if None in a or None in b:
        return "INSUFFICIENT_EVIDENCE"
    if min(a) > max(b):
        return "PREDICTION_SUPPORTED"
    return "PREDICTION_REFUTED" if max(a) < min(b) else "INSUFFICIENT_EVIDENCE"


def validity(gate: dict, res: dict) -> str:
    if gate.get("verdict") != "PASS" or any(r["status"] in STOP for r in res.values()):
        return "MEASUREMENT_INVALID"
    return "VALID" if all(r["status"] == "VALID" for r in res.values()) else "PARTIAL_VALID"


# ---- board results ----------------------------------------------------------------------------------------------------
def pmu3(folder: pathlib.Path, runs: dict) -> list[str]:
    """INVALID_PMU reasons for three passes x (1 warm-up + 4)."""
    bad = []
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    if len(raw) != N_RUNS or sorted({(x["set_id"], x["rep"]) for x in raw}) != [(s, r) for s in SETS for r in range(1, 6)]:
        bad.append("RUN layout (3 passes x (1 warm-up + 4))")
    for s, codes in SETS.items():
        for r in runs.get(s, []):
            if not r["valid"]:
                bad.append(f"set {s} RUN invalid")
            if any(r["ev"].get(c) is None for c in codes) or sorted(r["ev"]) != sorted(codes):
                bad.append(f"set {s} counters missing or wrong pass")
    for r in BB.rows_of(folder):
        if r["event_overflow"] not in ("False", "0", ""):
            bad.append("counter overflow")
        if r["cycle_valid"] not in ("1", "True"):
            bad.append("cycle window invalid")
    return sorted(set(bad))


def pass_c(runs: dict) -> dict:
    out = {}
    for code in PASS_C:
        out[f"C_{code}"], out[f"C_{code}_range"] = S4.stats(runs.get(3, []), code)
    return out


def stability3(s: dict, c: dict) -> list[str]:
    bad = BB.stability(s)
    a, ra = s["metrics"].get("A_35"), s["metrics"].get("A_35_range") or 0
    x, rx = c.get("C_35"), c.get("C_35_range") or 0
    if a is None or x is None or abs(x - a) > max(BB.AB_REL * a, ra + rx):
        bad.append("NPU_ACTIVE pass A vs pass C")
    return bad


def traffic(met: dict, c: dict) -> dict:
    g = lambda k: met.get(k)
    return dict(sram_rd_beats=g("B_130"), sram_rd_trans=g("B_128"), sram_wr_beats=g("B_135"), sram_wr_trans=g("B_132"),
                ext_rd_beats=g("B_386"), ext_rd_trans=g("B_384"), ext_wr_beats=g("B_391"),
                sram_rd_req_stalled=c.get("C_131"), sram_rd_stall_limit=c.get("C_142"), ext_rd_req_stalled=c.get("C_387"),
                ext0_rd_trans=c.get("C_640"), ext0_rd_beats=c.get("C_642"), ext1_rd_trans=c.get("C_656"),
                ext1_rd_beats=c.get("C_658"))


def config_result(root: pathlib.Path, wl: pathlib.Path, k: str) -> dict:
    m = json.loads((wl / MANIFEST).read_text())[k]
    cfg = m["config"]
    folder = root / "conds" / cfg / "wfe"
    base = dict(key=k, config=cfg)
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    ident = BB.identity_of(folder, wl, cfg, m, str(wl / m["caps_ref"]))
    env = E2B.environment(folder, m, ident)
    if env:
        return dict(base, status="CONFIG_MISMATCH", reasons=env)
    s = K.summary_of(folder, m["n_mac"])
    c = pass_c(s["runs"])
    met = BB.rates(m, s["metrics"])
    if not BB.output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][x] for x in BB.IDENT_OUTPUT):
        return dict(base, status="INVALID_OUTPUT", reasons=["board output != reference"])
    p = pmu3(folder, s["runs"])
    if p:
        return dict(base, status="INVALID_PMU", reasons=p)
    st = stability3(s, c)
    res = dict(base, metrics=met, pass_c=c, traffic=traffic(s["metrics"], c), output_sha256=s["output_sha256"])
    return dict(res, status="UNSTABLE", reasons=st) if st else dict(res, status="VALID", reasons=[])


def repro_gate(root: str, wl: str, ref: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    r = config_result(rootp, wlp, "REF")
    if r["status"] != "VALID":
        return dict(verdict="FAIL", why=r["status"], reasons=r["reasons"])
    m = json.loads((wlp / MANIFEST).read_text())["REF"]
    folder = rootp / "conds" / m["config"] / "wfe"
    same = {x["workload_sha256"] for x in BB.rows_of(pathlib.Path(ref))} == {x["workload_sha256"] for x in BB.rows_of(folder)}
    rep = K.reproduce(K.summary_of(folder, m["n_mac"]), K.summary_of(pathlib.Path(ref), m["n_mac"]))
    return dict(verdict="PASS" if rep["ok"] and same else "FAIL", same_binary=same, reproduce=rep)


def boot_check(root: str, wl: str, k: str) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), k)
    return dict(key=k, status=r["status"], reasons=r["reasons"], stop=r["status"] in STOP)


def judge(root: str, wl: str, ref: str, out: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    man = json.loads((wlp / MANIFEST).read_text())
    has_ref = (rootp / "conds" / man["REF"]["config"] / "wfe" / "runs.csv").exists()
    gate = repro_gate(root, wl, ref) if has_ref else dict(verdict="FAIL", why="UNMEASURED")
    res = {k: config_result(rootp, wlp, k) for k in man}
    ok = lambda k: res[k]["status"] == "VALID"
    met = lambda k, x: res[k]["metrics"].get(x) if "metrics" in res[k] else None
    shapes = {}
    for k, m in man.items():
        if k == "REF":
            continue
        v = man[k]["vela"]
        npu = met(k, "npu_active")
        shapes[k] = dict(family=m["family"], measurement=measurement(res[k]["status"]),
                         rates=dict(macs_per_mac_active=met(k, "macs_per_mac_active"), eff_1024=met(k, "eff_1024"),
                                    mac_over_npu=met(k, "mac_activity"), dpu_over_mac=met(k, "dpu_over_mac"),
                                    npu_over_mac=(npu / met(k, "mac_active")) if npu and met(k, "mac_active") else None),
                         vela=v, board_over_vela=(npu / v["op_cycles"]) if npu and v.get("op_cycles") else None,
                         vela_fidelity=vela_class(npu, v.get("op_cycles"), ok(k)))
    for f, (a, b) in PAIRS.items():
        both = ok(a) and ok(b)
        cv = compute_pair(met(a, "mac_active"), met(b, "mac_active"), both)
        pp = pipeline_pair(met(a, "npu_active"), met(a, "npu_active_range"), met(b, "npu_active"), met(b, "npu_active_range"), both)
        va, vb = man[a]["vela"]["op_cycles"], man[b]["vela"]["op_cycles"]
        ctrl = dict(compute=cv, pipeline=pp, vela_ratio=vb / va,
                    board_ratio=(met(b, "npu_active") / met(a, "npu_active")) if both else None)
        for k in (a, b):
            shapes[k].update(compute=cv, pipeline=pp["verdict"], control_pair=ctrl)
    shapes["s6c_f4_rep"].update(compute=compute_f4(N_MAC["s6c_f4_rep"], met("s6c_f4_rep", "mac_active"), ok("s6c_f4_rep")),
                                pipeline=pipeline_single(ok("s6c_f4_rep")))
    shapes["s6c_f5_rep"].update(compute="INSUFFICIENT_EVIDENCE", pipeline=pipeline_single(ok("s6c_f5_rep")))
    npu_mac = {k: shapes[k]["rates"]["npu_over_mac"] for k in shapes if ok(k)}
    hyp = dict(h_vela_f1_f2=h_vela_f12([shapes[k]["vela_fidelity"] for k in ("s6c_f1_rep", "s6c_f1_cin16", "s6c_f2_rep", "s6c_f2_c16")]),
               h_vela_f3=h_vela_f3([shapes[k]["board_over_vela"] for k in ("s6c_f3_rep", "s6c_f3_cin16") if ok(k)]),
               h_pipeline_observational=h_pipeline(npu_mac),
               h_compute_channel16={f: shapes[a]["compute"] for f, (a, _) in PAIRS.items()},
               h_compute_f4=shapes["s6c_f4_rep"]["compute"])
    summary = dict(contract="evidence/stage6c/contract.md",
                   ta="TA profile 1; EXT RLATENCY 500; runner image 14077be (bram ec0e8c3b), placement 0",
                   scope="isolated operators with graph IO in DDR; not attributed to the in-model operators' time",
                   reference_gate=gate, results=res, shapes=shapes, hypotheses=hyp,
                   verdicts=dict(measurement_validity=validity(gate, res), mechanism="MECHANISM_UNRESOLVED"))
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6c_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- manifest -----------------------------------------------------------------------------------------------------------
FAMILY = {"s6c_f1": "F1", "s6c_f2": "F2", "s6c_f3": "F3", "s6c_f4": "F4", "s6c_f5": "F5"}


def manifest(wl: str, img: str, facts_path: str) -> dict:
    wlp = pathlib.Path(wl)
    imgd = dict(reversed(line.split()) for line in (pathlib.Path(img) / "image.sha256").read_text().splitlines())
    image = dict(boot_sha256=imgd["boot.bin"], bram_sha256=imgd["bram.bin"], ddr_sha256=imgd["ddr.bin"], images_txt_sha256=imgd["images.txt"])
    facts = {x["name"]: x for x in json.loads(pathlib.Path(facts_path).read_text())}
    k4 = json.loads((wlp / "s4c2_conv_cin48.compile.json").read_text())
    out = {}
    for name, boot in ORDER:
        common = dict(boot=boot, latency=500, placement=0, image=image, ta_ext_rlatency=500, caps_ref="caps_l500.json")
        if name == "REF":
            out["REF"] = dict(common, kind="reference", config="s4c2_conv_cin48", n_mac=k4["n_mac"], cin=48,
                              drwl_sha256=BB.sha(wlp / "s4c2_conv_cin48.drwl"))
            continue
        r = facts[name]["npu_rows"][0]
        out[name] = dict(common, kind="op", config=name, family=FAMILY[name[:6]], n_mac=N_MAC[name], cin=CIN[name],
                         drwl_sha256=BB.sha(wlp / f"{name}.drwl"),
                         vela=dict(op_cycles=int(r["vela_op_cycles"]), npu_cycles=int(r["vela_npu_cycles"]),
                                   mac_cycles=int(r["vela_mac_cycles"]), sram_ac=int(r["sram_ac"]), dram_ac=int(r["dram_ac"]),
                                   traversal=r["traversal"], ofm_block=r["ofm_block"], ofm_ublock=r["ofm_ublock"]))
    (wlp / MANIFEST).write_text(json.dumps(out, indent=1, sort_keys=True))
    return out


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "manifest":
        manifest(*a[:3]); return 0
    if cmd == "boot-check":
        r = boot_check(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "repro-gate":
        r = repro_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge":
        r = judge(*a[:4])
        print(json.dumps(dict(verdicts=r["verdicts"], hypotheses=r["hypotheses"],
                              shapes={k: {x: v[x] for x in ("measurement", "compute", "pipeline", "vela_fidelity")} for k, v in r["shapes"].items()}),
                         indent=1, default=str)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
