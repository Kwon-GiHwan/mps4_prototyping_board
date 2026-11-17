#!/usr/bin/env python3
"""Stage 6B-E2B (evidence/stage6b/stage6be2b/contract.md): TA EXT read latency 500 vs 1000 on the same binaries; board
NPU_ACTIVE response against Vela's estimate response. Validity reuses the Stage 6B-B checks with the image digest and the
expected TA read-back taken per condition from the manifest.

  python3 stage6be2b.py manifest <workloads dir> <l1000 image.sha256>      # writes e2b_manifest.json
  python3 stage6be2b.py boot-check <run root> <workloads dir> <key>         # rc 1 -> the session stops
  python3 stage6be2b.py repro-gate <run root> <workloads dir> <boot 375 wfe dir>
  python3 stage6be2b.py judge <l500 run root> <l1000 run root> <workloads dir> <boot 375 wfe dir> <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage4 as S4  # noqa: E402
import stage4k as K  # noqa: E402
import stage6bb as BB  # noqa: E402

REPO = BB.REPO
MANIFEST = "e2b_manifest.json"
MODEL_TOL = 0.15          # |dB - dV| <= 0.15 |dV| + tol
NOISE_FLOOR = 0.01        # tol = max(1 % of B500, r500 + r1000)
RESOLVE = 0.5             # tol > 0.5 |dV| -> INSUFFICIENT
BEAT_TOL = 0.01           # auxiliary: beats equal within 1 %
BEATS = (130, 135, 386, 391)
KEYS = ("REF", "G12-L500", "CONV-L500", "G12-L1000", "CONV-L1000")
WORKLOADS = {"G12": ("G12-L500", "G12-L1000"), "CONV": ("CONV-L500", "CONV-L1000")}
STOP = ("CONFIG_MISMATCH", "UNMEASURED")
FAIL_STATES = ("CONFIG_MISMATCH", "UNMEASURED", "INVALID_OUTPUT", "INVALID_PMU")
IMAGE_L500 = BB.IMAGE


# ---- pure rules -------------------------------------------------------------------------------------------------------
def tolerance(b500: float, r500: float, r1000: float) -> float:
    return max(NOISE_FLOOR * b500, r500 + r1000)


def primary(d_board: float, d_vela: float, tol: float) -> str:
    if tol > RESOLVE * abs(d_vela):
        return "INSUFFICIENT"
    return "CONSISTENT" if abs(d_board - d_vela) <= MODEL_TOL * abs(d_vela) + tol else "DISCREPANT"


def secondary(r_board: float, r_vela: float, tol: float, b500: float) -> str:
    return "CONSISTENT" if abs(r_board - r_vela) <= MODEL_TOL * abs(r_vela - 1) + tol / b500 else "DISCREPANT"


def history(new: float, new_range: float, old: float, old_range: float) -> str:
    return "REPRODUCED" if abs(new - old) <= max(NOISE_FLOOR * old, new_range + old_range) else "DIFFERENT"


def auxiliary(m500: dict, m1000: dict, d_board: float, tol: float) -> dict:
    """m: {"mac": .., "dpu": .., "beats": {code: value}} (medians)."""
    same_mac = m500["mac"] == m1000["mac"]
    same_dpu = m500["dpu"] == m1000["dpu"]
    beats = {c: (m1000["beats"][c] - m500["beats"][c]) / m500["beats"][c] if m500["beats"][c] else None for c in BEATS}
    same_beats = all(v is not None and abs(v) <= BEAT_TOL for v in beats.values())
    cls = "MEMORY_SERVICE_RESPONSE" if same_mac and same_dpu and same_beats and d_board > tol else "CHANGED: " + ", ".join(
        n for n, ok in (("MAC_ACTIVE", same_mac), ("MAC_DPU_ACTIVE", same_dpu), ("beats", same_beats), ("NPU_ACTIVE not above tol", d_board > tol)) if not ok)
    return dict(cls=cls, same_mac=same_mac, same_dpu=same_dpu, beat_rel_change=beats)


def workload(r500: dict, r1000: dict, v: dict) -> dict:
    """r: config_result(); v: {"v500": .., "v1000": ..}."""
    st = (r500["status"], r1000["status"])
    if st != ("VALID", "VALID"):
        cls = "INSUFFICIENT" if all(s in ("VALID", "UNSTABLE") for s in st) else "NOT_EVALUABLE"
        return dict(primary=cls, statuses=st)
    b500, b1000 = r500["metrics"]["npu_active"], r1000["metrics"]["npu_active"]
    tol = tolerance(b500, r500["metrics"]["npu_active_range"], r1000["metrics"]["npu_active_range"])
    d_b, d_v = b1000 - b500, v["v1000"] - v["v500"]
    r_b, r_v = b1000 / b500, v["v1000"] / v["v500"]
    return dict(statuses=st, b500=b500, b1000=b1000, v500=v["v500"], v1000=v["v1000"], d_board=d_b, d_vela=d_v,
                r_board=r_b, r_vela=r_v, slope_board=d_b / 500, slope_vela=d_v / 500, tol=tol,
                primary=primary(d_b, d_v, tol), secondary=secondary(r_b, r_v, tol, b500),
                abs_err_500=(b500 - v["v500"]) / v["v500"], abs_err_1000=(b1000 - v["v1000"]) / v["v1000"])


def verdict(gate: dict, results: dict, wl: dict) -> str:
    if gate.get("verdict") != "PASS" or any(r["status"] in FAIL_STATES for r in results.values()):
        return "MEASUREMENT_INVALID"
    if any(w["primary"] == "DISCREPANT" for w in wl.values()):
        return "SENSITIVITY_DISCREPANCY_OBSERVED"
    if any(w["primary"] != "CONSISTENT" for w in wl.values()):
        return "INSUFFICIENT_EVIDENCE"
    return "SENSITIVITY_CONSISTENT"


# ---- board results (Stage 6B-B checks; image and TA read-back per condition) ---------------------------------------------
def environment(folder: pathlib.Path, m: dict, ident: dict) -> list[str]:
    bad = []
    rows = BB.rows_of(folder)
    if not rows:
        return ["no RUN rows"]
    if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:
        bad.append("workload sha256")
    for k, v in m["image"].items():
        if {r[k] for r in rows} != {v}:
            bad.append(f"image {k}")
    if not all(r["fpga_image"].startswith(BB.FPGA) for r in rows):
        bad.append("fpga image")
    if {r["host_boot_index"] for r in rows} != {str(m["boot"])}:
        bad.append("boot index")
    if {r["condition"] for r in rows} != {"wfe"}:
        bad.append("condition")
    caps_p = folder.parent / "capabilities.json"
    caps = json.loads(caps_p.read_text()) if caps_p.exists() else {}
    if (caps.get("npu_config", 0) & 0xF) != BB.LOG2_MACS:
        bad.append("NPU MAC count")
    if caps.get("ta_ext_rlatency") != m["ta_ext_rlatency"]:
        bad.append("TA EXT RLATENCY read-back")
    bad += [f"identity {k}" for k, v in ident["checks"].items() if not v and k not in BB.IDENT_PMU + BB.IDENT_OUTPUT]
    return bad


def config_result(root: pathlib.Path, wl: pathlib.Path, key: str) -> dict:
    m = json.loads((wl / MANIFEST).read_text())[key]
    cfg = m["config"]
    folder = root / "conds" / cfg / "wfe"
    base = dict(key=key, config=cfg)
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    ident = BB.identity_of(folder, wl, cfg, m, str(wl / m["caps_ref"]))
    env = environment(folder, m, ident)
    if env:
        return dict(base, status="CONFIG_MISMATCH", reasons=env)
    s = K.summary_of(folder, m["n_mac"])
    met = BB.rates(m, s["metrics"])
    if not BB.output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][k] for k in BB.IDENT_OUTPUT):
        return dict(base, status="INVALID_OUTPUT", reasons=["board output != reference"])
    p = BB.pmu(folder, s["runs"], m["n_mac"])
    if p:
        return dict(base, status="INVALID_PMU", reasons=p)
    st = BB.stability(s)
    res = dict(base, metrics=met, beats={c: s["metrics"].get(f"B_{c}") for c in S4.PASS_B[1:]},
               mac_active_runs=s["mac_active"], mac_dpu_active_runs=s["mac_dpu_active"], output_sha256=s["output_sha256"])
    return dict(res, status="UNSTABLE", reasons=st) if st else dict(res, status="VALID", reasons=[])


def repro_gate(root: str, wl: str, ref: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    r = config_result(rootp, wlp, "REF")
    if r["status"] != "VALID":
        return dict(verdict="FAIL", why=r["status"], reasons=r["reasons"])
    m = json.loads((wlp / MANIFEST).read_text())["REF"]
    folder = rootp / "conds" / m["config"] / "wfe"
    same_bin = {x["workload_sha256"] for x in BB.rows_of(pathlib.Path(ref))} == {x["workload_sha256"] for x in BB.rows_of(folder)}
    rep = K.reproduce(K.summary_of(folder, m["n_mac"]), K.summary_of(pathlib.Path(ref), m["n_mac"]))
    return dict(verdict="PASS" if rep["ok"] and same_bin else "FAIL", same_binary=same_bin, reproduce=rep)


def boot_check(root: str, wl: str, key: str) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), key)
    return dict(key=key, status=r["status"], reasons=r["reasons"], stop=r["status"] in STOP)


def judge(root500: str, root1000: str, wl: str, ref: str, out: str) -> dict:
    wlp = pathlib.Path(wl)
    man = json.loads((wlp / MANIFEST).read_text())
    roots = {k: pathlib.Path(root1000 if man[k]["latency"] == 1000 else root500) for k in KEYS}
    has_ref = (roots["REF"] / "conds" / man["REF"]["config"] / "wfe" / "runs.csv").exists()
    gate = repro_gate(str(roots["REF"]), wl, ref) if has_ref else dict(verdict="FAIL", why="UNMEASURED")
    res = {k: config_result(roots[k], wlp, k) for k in KEYS}
    pred = json.loads((wlp / "predictions.json").read_text())
    wls, aux, hist = {}, {}, {}
    for w, (k5, k10) in WORKLOADS.items():
        wls[w] = workload(res[k5], res[k10], pred[w])
        if wls[w].get("tol") is not None:
            mm = lambda r: dict(mac=r["metrics"]["mac_active"], dpu=r["metrics"]["mac_dpu_active"], beats=r["beats"])
            aux[w] = auxiliary(mm(res[k5]), mm(res[k10]), wls[w]["d_board"], wls[w]["tol"])
        if res[k5]["status"] == "VALID":
            old = K.summary_of(REPO / man[k5]["history"], man[k5]["n_mac"])["metrics"]
            hist[w] = dict(old_boot=man[k5]["history_boot"], old=old["A_35"], old_range=old["A_35_range"],
                           new=res[k5]["metrics"]["npu_active"], new_range=res[k5]["metrics"]["npu_active_range"],
                           cls=history(res[k5]["metrics"]["npu_active"], res[k5]["metrics"]["npu_active_range"], old["A_35"], old["A_35_range"]))
    summary = dict(contract="evidence/stage6b/stage6be2b/contract.md", ta="TA profile 1; EXT RLATENCY 500 (image 70090f1) vs 1000 (image L1000)",
                   reference_gate=gate, results=res, workloads=wls, auxiliary=aux, history=hist,
                   verdict=verdict(gate, res, wls),
                   limits=["one boot per condition: no independent boot repetition, no statistical causal claim",
                           "L1000 boots follow the L500 boots in time; drift checked once by REF",
                           "one latency variable: no separation of individual memory/pipeline contributions"])
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2b_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


# ---- manifest (before the board) ---------------------------------------------------------------------------------------
def manifest(wl: str, l1000_sha: str) -> dict:
    wlp = pathlib.Path(wl)
    sha = lambda p: BB.sha(wlp / p)
    img = {}
    for line in pathlib.Path(l1000_sha).read_text().splitlines():
        h, n = line.split()
        img[n] = h
    image_l1000 = dict(boot_sha256=img["boot.bin"], bram_sha256=img["bram.bin"], ddr_sha256=img["ddr.bin"],
                       images_txt_sha256=img["images.txt"])
    bb = json.loads((REPO / "evidence/stage6b/stage6bb/workloads/stage6bb_manifest.json").read_text())["s6bb_g12"]
    e1 = json.loads((REPO / "evidence/stage6b/stage6be1r/workloads/stage6bb_manifest.json").read_text())["e1r_c200_h37w37_o96"]
    k4 = json.loads((wlp / "s4c2_conv_cin48.compile.json").read_text())
    common = lambda m, cfg, boot, lat, caps: dict(m, config=cfg, boot=boot, latency=lat, drwl_sha256=sha(f"{cfg}.drwl"),
                                                  image=IMAGE_L500 if lat == 500 else image_l1000,
                                                  ta_ext_rlatency=lat, caps_ref=caps)
    ref = dict(kind="reference", n_mac=k4["n_mac"], cin=48, internal_conv="CONV_OUTPUT_OBSERVED")
    out = {"REF": common(ref, "s4c2_conv_cin48", 435, 500, "caps_l500.json"),
           "G12-L500": common(bb, "s6bb_g12", 436, 500, "caps_l500.json"),
           "CONV-L500": common(e1, "e1r_c200_h37w37_o96", 437, 500, "caps_l500.json"),
           "G12-L1000": common(bb, "s6bb_g12", 438, 1000, "caps_l1000.json"),
           "CONV-L1000": common(e1, "e1r_c200_h37w37_o96", 439, 1000, "caps_l1000.json")}
    out["G12-L500"].update(history="evidence/stage6b/stage6bb/raw/evsweep_s6bb_run/conds/s6bb_g12/wfe", history_boot=411)
    out["CONV-L500"].update(history="evidence/stage6b/stage6be1r/raw/evsweep_s6be1r_run/conds/e1r_c200_h37w37_o96/wfe", history_boot=429)
    (wlp / MANIFEST).write_text(json.dumps(out, indent=1, sort_keys=True))
    return out


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "manifest":
        print(json.dumps(manifest(*a[:2]), indent=1)[:2000]); return 0
    if cmd == "boot-check":
        r = boot_check(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "repro-gate":
        r = repro_gate(*a[:3]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "judge":
        r = judge(*a[:5]); print(json.dumps({k: r[k] for k in ("verdict", "workloads", "auxiliary", "history")}, indent=1, default=str)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
