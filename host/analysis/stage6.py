#!/usr/bin/env python3
"""Stage 6 (docs/plan/stage6_model_level_characterization.md; rules fixed first in evidence/stage6/rules.md, commit
cbf8e23): the Stage 4-4WD single-operator characteristics applied to the seven MLEK models, compared with the
driver_m7 whole-model PMU (boots 308-316, TA profile 1). Board-free. Every rule and threshold below is the rules
document's; nothing is fitted to the whole-model numbers.

  python3 host/analysis/stage6.py run <out dir>
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import statistics
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = REPO / "results/fi101_stage4/stage4_operator_inventory.csv"
DTYPES = REPO / "results/fi101_stage6/tflite_dtypes.json"
M7_RAW = REPO / "evidence/driver_m7/raw/wfe"
M7_WL = REPO / "evidence/driver_m7/workloads"
MODELS = ["kws_micronet_m", "ad_medium_int8", "mobilenet_v2_1.0_224_INT8", "vww4_128_128_INT8", "rnnoise_INT8",
          "yolo-fastest_192_face_v4", "wav2letter_pruned_int8"]
SET_A, SET_B = "2", "3"
COVER_COMPARE, COVER_PARTIAL, TOL = 0.80, 0.50, 0.10        # rules §4, §5
AO_CONV_RATE, AO_EW_RATE = 15.60, 16.0                       # rules §2
WD_T0 = dict(slope=60.6, intercept=96.7)                     # rules §2 (Stage 4AO fit, BLOCK_LIKE in 4WD)

# MAC catalog (rules §2): family -> measured points (cin, cout, ofm_block, rate)
FAMILIES = {
    ("Conv2D", "1x1", "1x1", "PartKernel"): [(16, 96, "6x12x96", 384), (32, 96, "6x12x96", 384), (16, 95, "6x12x96", 384),
                                              (16, 94, "6x12x96", 384)],
    ("Conv2D", "1x1", "1x1", "DepthFirst"): [(40, 96, "6x12x96", 640), (48, 96, "6x12x96", 768), (64, 96, "6x12x96", 768),
                                              (128, 96, "6x12x96", 768)],
    ("Conv2D", "3x3", "1x1", "PartKernel"): [(c, 96, "24x10x32", 768) for c in (16, 32, 40, 48, 64)],
    ("DepthwiseConv2D", "3x3", "1x1", "Depthwise"): [(c, c, "26x28x16", 128) for c in (142, 143, 144, 145)],
    ("FullyConnected", "1x1", "1x1", ""): [(96, 288, "2x2x288", 256), (95, 288, "2x2x288", 256), (96, 287, "2x2x288", 256)],
}
MAC_OPS = {"Conv2D", "DepthwiseConv2D", "FullyConnected"}
EW_OPS = {"Add", "Mul"}
WD_T0_KEY = (("Conv2D", "1x1", "1x1", "PartKernel"), 16, 96, "6x12x96")


def i(x) -> int:
    return int(x) if x not in (None, "") else 0


def hwc(s: str) -> list[int]:
    return [int(v) for v in s.split("x")] if s and "x" in s and "xx" not in s else []


def fused(r: dict) -> bool:
    """A scheduled row with no cycles and no MACs (Vela's fused activation / pass-through)."""
    return i(r["vela_npu_cycles"]) == 0 and i(r["mac_count"]) == 0


def family(r: dict) -> tuple:
    return (r["npu_op"], r["kernel"], r["stride"], r["traversal"])


def mac_tier(r: dict) -> tuple[str, float | None]:
    """(tier, observed MAC rate or None) for one scheduled NPU operation (rules §3)."""
    if r["npu_op"] not in MAC_OPS or i(r["mac_count"]) == 0:
        return "U", None
    pts = FAMILIES.get(family(r))
    if pts is None:
        return "T2", None
    cin, cout = i(r["cin"]), i(r["cout"])
    for c, co, blk, rate in pts:
        if (cin, cout, r["ofm_block"]) == (c, co, blk):
            return "T0", rate
    rates = {p[3] for p in pts}
    lo, hi = min(p[0] for p in pts), max(p[0] for p in pts)
    if lo <= cin <= hi and len(rates) == 1:
        return "T1_INTERP", rates.pop()
    return "T1_EXTRAP", None


def int8_out(r: dict, dt: dict) -> bool:
    ops = dt.get(r["model"], {}).get("ops", {})
    o = ops.get(str(r["tflite_op_index"]))
    return bool(o) and all(t == "INT8" for t in o["outputs"])


def ao_tier(r: dict, dt: dict) -> tuple[str, float | None]:
    """(tier, AO rate) — rules §3 AO axis. Fused 0-cycle rows carry no AO pass of their own."""
    if not r["npu_op"] or fused(r) or r["cpu"] == "1":
        return "U", None
    if r["npu_op"] == "Conv2D" and int8_out(r, dt):
        return "T1_INTERP", AO_CONV_RATE
    if r["npu_op"] in ("DepthwiseConv2D", "FullyConnected"):
        return "T2", None
    if r["npu_op"] in EW_OPS and int8_out(r, dt) and r["ofm_format"] == "NHWC":
        return "T1_INTERP", AO_EW_RATE
    return "U", None


def ao_elements(r: dict) -> int:
    o = hwc(r["npu_ofm_hwc"])
    return o[0] * o[1] * math.ceil(o[2] / 16) * 16 if len(o) == 3 else 0


def spatial_blocks(r: dict) -> int:
    o, b = hwc(r["npu_ofm_hwc"]), hwc(r["ofm_block"])
    return math.ceil(o[0] / b[0]) * math.ceil(o[1] / b[1]) if len(o) == 3 and len(b) == 3 else 0


def wd_tier(r: dict) -> str:
    if i(r["weight_bytes"]) == 0:
        return "U"
    t, _ = mac_tier(r)
    return "T0" if t == "T0" and (family(r), i(r["cin"]), i(r["cout"]), r["ofm_block"]) == WD_T0_KEY else "PROXY"


def baseline(model: str) -> dict:
    """driver_m7 whole-model PMU medians (pass A set 2, pass B set 3, measured RUNs rep > 2) and the checks."""
    rows = list(csv.DictReader(open(M7_RAW / model / "runs.csv")))
    reps = sorted({int(r["rep"]) for r in rows})
    v = lambda s, e: [int(r["event_value"]) for r in rows if r["set_id"] == s and r["ev_type"] == e and int(r["rep"]) > 2]
    med = lambda s, e: statistics.median(v(s, e)) if v(s, e) else None
    rng = lambda s, e: (max(v(s, e)) - min(v(s, e))) if v(s, e) else None
    out = dict(npu_active=med(SET_A, "35"), npu_active_range=rng(SET_A, "35"), mac_active=med(SET_A, "48"),
               mac_dpu_active=med(SET_A, "51"), ao_active=med(SET_A, "64"), wd_active=med(SET_A, "80"),
               wd_stalled=med(SET_A, "81"), sram_rd=med(SET_B, "130"), sram_wr=med(SET_B, "135"),
               ext_rd=med(SET_B, "386"), ext_wr=med(SET_B, "391"), reps=len(reps))
    vela = json.loads((M7_WL / f"{model}.drwl.json").read_text())["vela_sha256"]
    out["checks"] = dict(all_valid=all(r["run_valid"] == "True" for r in rows), ten_runs=len(reps) == 10,
                         vela_sha_matches_inventory=None, vela_sha256=vela)
    return out


def classify(rows: list, dt: dict) -> list:
    res = []
    for r in rows:
        mt, mrate = mac_tier(r)
        at, arate = ao_tier(r, dt)
        n_ao = ao_elements(r) if at != "U" or (r["npu_op"] and not fused(r) and r["cpu"] != "1") else 0
        sb = spatial_blocks(r)
        res.append(dict(model=r["model"], scheduled_id=r["scheduled_id"], tflite_op_index=r["tflite_op_index"],
                        tflite_op=r["tflite_op"], npu_op=r["npu_op"], kernel=r["kernel"], stride=r["stride"],
                        cin=r["cin"], cout=r["cout"], traversal=r["traversal"], ofm_block=r["ofm_block"],
                        npu_ofm_hwc=r["npu_ofm_hwc"], fused=fused(r), cpu=r["cpu"] == "1",
                        int8_out=int8_out(r, dt), mac=i(r["mac_count"]), mac_tier=mt, mac_rate=mrate,
                        ao_elements=n_ao, ao_tier=at, ao_rate=arate, weight_bytes=i(r["weight_bytes"]),
                        spatial_blocks=sb, wd_tier=wd_tier(r), wd_proxy=sb * i(r["weight_bytes"]),
                        vela_npu_cycles=i(r["vela_npu_cycles"]), vela_mac_cycles=i(r["vela_mac_cycles"]),
                        vela_ao_cycles=i(r["vela_ao_cycles"]), ifm_memory=r["ifm_memory"], ofm_memory=r["ofm_memory"]))
    return res


def shares(ops: list, key: str, tier: str) -> dict:
    tot = sum(o[key] for o in ops)
    tiers = ("T0", "T1_INTERP", "T1_EXTRAP", "T2", "U") if tier != "wd_tier" else ("T0", "PROXY", "U")
    return dict(total=tot, **{t: (sum(o[key] for o in ops if o[tier] == t) / tot if tot else None) for t in tiers})


def estimate(ops: list) -> dict:
    mac_cal = [o for o in ops if o["mac_tier"] in ("T0", "T1_INTERP")]
    ao_cal = [o for o in ops if o["ao_tier"] in ("T0", "T1_INTERP")]
    wd_cal = [o for o in ops if o["wd_tier"] == "T0"]
    mac_s, ao_s, wd_s = shares(ops, "mac", "mac_tier"), shares(ops, "ao_elements", "ao_tier"), shares(ops, "wd_proxy", "wd_tier")
    return dict(
        mac=dict(shares=mac_s, calibrated_coverage=(mac_s["T0"] or 0) + (mac_s["T1_INTERP"] or 0),
                 calibrated_estimate=sum(o["mac"] / o["mac_rate"] for o in mac_cal)),
        ao=dict(shares=ao_s, calibrated_coverage=(ao_s["T0"] or 0) + (ao_s["T1_INTERP"] or 0),
                calibrated_estimate=sum(o["ao_elements"] / o["ao_rate"] for o in ao_cal)),
        wd=dict(shares=wd_s, calibrated_coverage=wd_s["T0"] or 0,
                calibrated_estimate=sum(WD_T0["slope"] * 2 * o["spatial_blocks"] + WD_T0["intercept"] for o in wd_cal),
                proxy_total=wd_s["total"]),
        vela=dict(npu_cycles=sum(o["vela_npu_cycles"] for o in ops), mac_cycles=sum(o["vela_mac_cycles"] for o in ops),
                  ao_cycles=sum(o["vela_ao_cycles"] for o in ops)))


def compare(est: dict, measured: float | None) -> dict:
    """rules §4: quantitative only at calibrated coverage >= 0.80; then CONSISTENT within 10 %."""
    cov = est["calibrated_coverage"]
    if measured is None:
        return dict(status="BASELINE_NOT_COMPARABLE", coverage=cov)
    if cov < COVER_COMPARE:
        return dict(status="INSUFFICIENT_EVIDENCE", coverage=cov, measured=measured)
    err = (est["calibrated_estimate"] - measured) / measured
    return dict(status="CONSISTENT" if abs(err) <= TOL else "NOT_CONSISTENT", coverage=cov, measured=measured,
                estimate=est["calibrated_estimate"], rel_error=err)


PHENOMENA = [("P1", "MAC active share high, effective rate low", ["kws_micronet_m"], ["mac"], False),
             ("P2", "high MAC efficiency with high WD_STALLED", ["ad_medium_int8", "wav2letter_pruned_int8"], ["mac", "wd"], False),
             ("P3", "AO_ACTIVE > MAC_ACTIVE", ["yolo-fastest_192_face_v4", "vww4_128_128_INT8"], ["ao", "mac"], False),
             ("P4", "very low MAC activity", ["rnnoise_INT8"], ["mac"], False),
             ("P5", "NPU cost vs Vela estimate", ["rnnoise_INT8"], ["mac", "ao", "wd"], False),
             ("P6", "SRAM budget changes performance (Stage 5)", ["ad_medium_int8"], ["wd"], False),
             ("P7", "similar MACs, different cycles", MODELS, ["mac", "ao", "wd"], False)]


def verdict(baseline_ok: bool, covs: list, comps: list, needs_attribution: bool) -> str:
    """rules §5, in order."""
    if not baseline_ok:
        return "BASELINE_NOT_COMPARABLE"
    c = min(covs)
    if c < COVER_PARTIAL or needs_attribution:
        return "INSUFFICIENT_EVIDENCE"
    if c >= COVER_COMPARE:
        return "SUPPORTED_WITHIN_SCOPE" if all(x == "CONSISTENT" for x in comps) else "NOT_SUPPORTED"
    return "PARTIALLY_SUPPORTED"


def run(out: str) -> dict:
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    inv = list(csv.DictReader(open(INVENTORY)))
    dt = json.loads(DTYPES.read_text())
    ops = classify(inv, dt)
    models = {}
    for m in MODELS:
        mo = [x for x in ops if x["model"] == m]
        b = baseline(m)
        inv_sha = {r["vela_sha256"] for r in inv if r["model"] == m}
        b["checks"]["vela_sha_matches_inventory"] = inv_sha == {b["checks"]["vela_sha256"][:16]}
        b["ok"] = all(v for k, v in b["checks"].items() if k != "vela_sha256")
        e = estimate(mo)
        cmp_ = {ax: compare(e[ax], b.get(f"{ax}_active") if b["ok"] else None) for ax in ("mac", "ao", "wd")}
        models[m] = dict(baseline=b, estimate=e, comparison=cmp_, n_ops=len(mo),
                         n_npu_ops=sum(1 for x in mo if x["npu_op"] and not x["fused"] and not x["cpu"]),
                         n_fused=sum(1 for x in mo if x["fused"]), n_cpu_or_removed=sum(1 for x in mo if not x["npu_op"] or x["cpu"]))
    matrix = []
    for pid, desc, ms, axes, attrib in PHENOMENA:
        for m in ms:
            md = models[m]
            covs = [md["estimate"][a]["calibrated_coverage"] for a in axes]
            comps = [md["comparison"][a]["status"] for a in axes]
            matrix.append(dict(phenomenon=pid, description=desc, model=m, axes="+".join(axes),
                               coverages=";".join(f"{a}={c:.3f}" for a, c in zip(axes, covs)),
                               comparisons=";".join(comps), verdict=verdict(md["baseline"]["ok"], covs, comps, attrib)))
    write_csv(o / "model_operator_inventory.csv", [dict((k, x[k]) for k in ("model", "scheduled_id", "tflite_op_index",
              "tflite_op", "npu_op", "kernel", "stride", "cin", "cout", "traversal", "ofm_block", "npu_ofm_hwc", "int8_out",
              "mac", "weight_bytes", "ifm_memory", "ofm_memory")) for x in ops])
    write_csv(o / "vela_kernel_mapping.csv", [dict(model=x["model"], tflite_op_index=x["tflite_op_index"],
              tflite_op=x["tflite_op"], scheduled_id=x["scheduled_id"], npu_op=x["npu_op"] or "(none)", fused=x["fused"],
              cpu_or_removed=x["cpu"] or not x["npu_op"]) for x in ops])
    write_csv(o / "unit_model_applicability.csv", [dict((k, x[k]) for k in ("model", "scheduled_id", "npu_op", "kernel",
              "cin", "cout", "traversal", "ofm_block", "mac", "mac_tier", "mac_rate", "ao_elements", "ao_tier", "ao_rate",
              "weight_bytes", "spatial_blocks", "wd_tier", "wd_proxy")) for x in ops])
    write_csv(o / "model_activity_estimates.csv", [dict(model=m, axis=ax, total=d["estimate"][ax]["shares"]["total"],
              **{f"share_{k}": v for k, v in d["estimate"][ax]["shares"].items() if k != "total"},
              calibrated_coverage=d["estimate"][ax]["calibrated_coverage"],
              calibrated_estimate=d["estimate"][ax]["calibrated_estimate"]) for m, d in models.items() for ax in ("mac", "ao", "wd")])
    write_csv(o / "whole_model_comparison.csv", [dict(model=m, axis=ax, **d["comparison"][ax],
              vela_npu_cycles=d["estimate"]["vela"]["npu_cycles"], npu_active=d["baseline"]["npu_active"])
              for m, d in models.items() for ax in ("mac", "ao", "wd")])
    write_csv(o / "anomaly_attribution_matrix.csv", matrix)
    summary = dict(models=models, matrix=matrix)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def write_csv(path: pathlib.Path, rows: list) -> None:
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    r = run(sys.argv[2]) if sys.argv[1:2] == ["run"] else sys.exit("usage: stage6.py run <out dir>")
    print(json.dumps({m: {ax: d["comparison"][ax] for ax in ("mac", "ao", "wd")} for m, d in r["models"].items()},
                     indent=1, default=str)[:5000])
