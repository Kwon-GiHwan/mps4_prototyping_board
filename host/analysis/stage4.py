#!/usr/bin/env python3
"""Stage 4A/4B (evidence/stage4/contract.md): output check, Gate C, execution metrics and channel-alignment
sensitivity of the eight isolated operators. TA profile 1, driver runner, 1 warm-up + 4 measured RUNs per pass.

  python3 host/analysis/stage4.py <campaign root (conds/<cfg>/wfe/)> <compile dir> <out dir> [warm-up]

Rules (fixed before the data):
  output   NPU OFM (output.bin, the last RUN) vs the CPU reference (tflite_runtime, .drwl.tflite_ofm.bin), int8:
           INVALID if the length differs from the output shape or the reference, or the RUNs' output CRCs differ from
           each other or from output.bin; else PASS_EXACT if every element is equal; PASS_TOLERANCE if max |diff| <= 1;
           FAIL otherwise. The firmware's own count against the same reference (ofm_mismatch, ofm_max_diff) must agree
           in every RUN, else INVALID.
  gate C   output PASS_EXACT / PASS_TOLERANCE, every measured RUN valid (record_v2.validity), both passes present.
  pairs    base vs variant, NPU_ACTIVE (35) medians of pass A: tol = max(1 % of the base median, either RUN range).
           |variant - base| <= tol -> UNRESOLVED; else expected = base x MACs(variant) / MACs(base):
           |variant - expected| <= tol -> CONSISTENT_WITH_MAC_CHANGE, else NOT_PROPORTIONAL_TO_MAC. Reported beside it:
           schedule_changed (Vela OFM block, ublock or kernel count differ) and traffic_changed (any pass-B event median
           differs by more than the same tolerance rule). Pairs with a config failing gate C: EXCLUDED.
MACs / (1024 x MAC_ACTIVE) is a MAC-count-to-active-cycle efficiency, not a measured lane occupancy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import statistics
import sys
import zlib

PASS_A = [35, 48, 51, 53, 55, 64, 80, 81]
PASS_B = [35, 128, 130, 132, 135, 384, 386, 391]
RESERVED = {53, 55}                      # not in the TRM 110 list: reported, never a basis for a conclusion
PAIRS = [("conv_base", "conv_cin15"), ("conv_base", "conv_cout95"), ("dw_base", "dw_c143"),
         ("fc_base", "fc_in95"), ("fc_base", "fc_out287")]
FLOOR = 0.01


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def load(folder: pathlib.Path, warmup: int) -> dict:
    """{set: [{"ev": {code: value}, "record": ..., "crc": ..., "valid": bool}]} for measured RUNs."""
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    rows = {}
    with open(folder / "runs.csv") as f:
        for r in csv.DictReader(f):
            k = (int(r["set_id"]), int(r["rep"]))
            rows.setdefault(k, {"ev": {}, "valid": r["run_valid"] == "True"})["ev"][int(r["ev_type"])] = \
                int(r["event_value"]) if r["event_value"] not in ("", "None") else None
    out = {}
    for x in raw:
        if x["rep"] <= warmup:
            continue
        k = (x["set_id"], x["rep"])
        out.setdefault(x["set_id"], []).append(dict(rows.get(k, {"ev": {}, "valid": False}), record=x["record"],
                                                    crc=x.get("output_crc32"), length=x.get("output_len")))
    return out


def output_check(folder: pathlib.Path, comp: dict, ref: bytes, runs: dict) -> dict:
    """The output verdict and its statistics."""
    npu_path = folder / "output.bin"
    n = 1
    for v in comp["ofm_shape"]:
        n *= v
    all_runs = [r for rs in runs.values() for r in rs]
    res = dict(cpu_sha256=hashlib.sha256(ref).hexdigest(), elements=n, ofm_scale=comp["quant"]["ofm_scale"],
               ofm_zero_point=comp["quant"]["zero_points"], ifm_scale=comp["quant"]["ifm_scale"],
               weight_scale=comp["quant"]["weight_scale"])
    if not npu_path.exists():
        return dict(res, verdict="INVALID", why="no output.bin")
    npu = npu_path.read_bytes()
    res["npu_sha256"] = hashlib.sha256(npu).hexdigest()
    why = []
    if len(npu) != n or len(ref) != n:
        why.append(f"length npu {len(npu)} cpu {len(ref)} shape {n}")
    if {r["crc"] for r in all_runs} != {zlib.crc32(npu)}:
        why.append("output CRC differs between RUNs or from output.bin")
    if why:
        return dict(res, verdict="INVALID", why="; ".join(why))
    a = [x - 256 if x > 127 else x for x in npu]
    b = [x - 256 if x > 127 else x for x in ref]
    d = [abs(x - y) for x, y in zip(a, b)]
    mism, mx = sum(v != 0 for v in d), max(d)
    fw = {(r["record"]["ofm_mismatch"], r["record"]["ofm_max_diff"]) for r in all_runs}
    if fw != {(mism, mx)}:
        return dict(res, verdict="INVALID", why=f"firmware count {sorted(fw)} != host ({mism}, {mx})")
    cout = comp["ofm_shape"][-1]
    per_ch = [0] * cout
    for i, v in enumerate(d):
        if v:
            per_ch[i % cout] += 1
    s = comp["quant"]["ofm_scale"]
    cap = round(6 / s) if comp["activation"] == "RELU6" else None
    sat = lambda xs, v: sum(x == v for x in xs)
    top = sorted(per_ch, reverse=True)
    res.update(
        verdict="PASS_EXACT" if mx == 0 else "PASS_TOLERANCE" if mx <= 1 else "FAIL", why="",
        max_abs_diff=mx, mean_abs_diff=sum(d) / n, mismatch_count=mism, mismatch_ratio=mism / n,
        diff_1lsb_count=sum(v == 1 for v in d), diff_gt_1lsb_count=sum(v > 1 for v in d),
        npu_min=min(a), npu_max=max(a), cpu_min=min(b), cpu_max=max(b),
        npu_at_127=sat(a, 127), npu_at_minus128=sat(a, -128), relu6_cap=cap,
        npu_at_relu6_cap=sat(a, cap) if cap is not None and cap <= 127 else None,
        mismatch_at_saturation=sum(1 for x, v in zip(a, d) if v and (x in (127, -128) or x == cap)),
        channels_with_mismatch=sum(c > 0 for c in per_ch), channels=cout,
        top_channel_share=(top[0] / mism) if mism else None,
        signed_diff_sum=sum(x - y for x, y in zip(a, b)))
    return res


def stats(runs: list, code: int) -> tuple:
    v = [r["ev"].get(code) for r in runs]
    v = [x for x in v if x is not None]
    return (med(v), (max(v) - min(v)) if v else None)


def metrics(runs: dict, macs: int) -> dict:
    a, b = runs.get(1, []), runs.get(2, [])
    out = {}
    for code in PASS_A:
        out[f"A_{code}"], out[f"A_{code}_range"] = stats(a, code)
    for code in PASS_B:
        out[f"B_{code}"], out[f"B_{code}_range"] = stats(b, code)
    na = out["A_35"]
    if na:
        for code, name in ((48, "mac_active"), (51, "mac_dpu_active"), (64, "ao_active"), (80, "wd_active"),
                           (81, "wd_stalled")):
            out[f"{name}_per_npu_active"] = out[f"A_{code}"] / na if out[f"A_{code}"] is not None else None
        out["macs_per_npu_active"] = macs / na
        out["cycles_per_mac"] = na / macs
    if out.get("A_48"):
        out["macs_per_1024_mac_active"] = macs / (1024 * out["A_48"])
    return out


def tol(base: list, var: list, code: int) -> float:
    mb, rb = stats(base, code)
    _, rv = stats(var, code)
    return max(FLOOR * mb, rb or 0, rv or 0)


def pair(bc: dict, vc: dict) -> dict:
    ba, va = bc["runs"].get(1, []), vc["runs"].get(1, [])
    mb, mv = stats(ba, 35)[0], stats(va, 35)[0]
    t = tol(ba, va, 35)
    expected = mb * vc["macs"] / bc["macs"]
    if abs(mv - mb) <= t:
        verdict = "UNRESOLVED"
    elif abs(mv - expected) <= t:
        verdict = "CONSISTENT_WITH_MAC_CHANGE"
    else:
        verdict = "NOT_PROPORTIONAL_TO_MAC"
    traffic = {}
    for code in PASS_B[1:]:
        b2, v2 = bc["runs"].get(2, []), vc["runs"].get(2, [])
        x, y = stats(b2, code)[0], stats(v2, code)[0]
        if x is not None and y is not None:
            traffic[code] = dict(base=x, variant=y, changed=abs(y - x) > tol(b2, v2, code),
                                 pct=(y / x - 1) * 100 if x else None)
    c1, c2 = bc["compile"], vc["compile"]
    sched = (c1["ofm_block"], c1["ofm_ublock"], c1["n_kernels"]) != (c2["ofm_block"], c2["ofm_ublock"], c2["n_kernels"])
    pct = lambda x, y: (y / x - 1) * 100 if x else None
    return dict(verdict=verdict, npu_active_base=mb, npu_active_variant=mv, tolerance=t, expected_by_macs=expected,
                mac_change_pct=pct(bc["macs"], vc["macs"]), npu_active_change_pct=pct(mb, mv),
                cycles_per_mac_change_pct=pct(mb / bc["macs"], mv / vc["macs"]),
                mac_active_ratio_base=bc["metrics"].get("mac_active_per_npu_active"),
                mac_active_ratio_variant=vc["metrics"].get("mac_active_per_npu_active"),
                vela_cycles_change_pct=pct(int(c1["vela_npu_cycles"]), int(c2["vela_npu_cycles"])),
                block_base=c1["ofm_block"], block_variant=c2["ofm_block"], ublock_base=c1["ofm_ublock"],
                ublock_variant=c2["ofm_ublock"], kernels_base=c1["n_kernels"], kernels_variant=c2["n_kernels"],
                schedule_changed=sched, traffic_changed=any(v["changed"] for v in traffic.values()), traffic=traffic)


def main(root: str, comp_dir: str, out: str, warmup: int = 1) -> dict:
    root, comp_dir, out = pathlib.Path(root), pathlib.Path(comp_dir), pathlib.Path(out)
    cfgs = {}
    for c in ("conv_base", "conv_cin15", "conv_cout95", "dw_base", "dw_c143", "fc_base", "fc_in95", "fc_out287"):
        name = "s4_" + c
        folder = root / "conds" / name / "wfe"
        comp = json.loads((comp_dir / f"{name}.compile.json").read_text())
        if not (folder / "raw_runs.json").exists():
            cfgs[c] = dict(gate_c="NOT_MEASURED", compile=comp, macs=comp["n_mac"], runs={}, metrics={})
            continue
        runs = load(folder, warmup)
        oc = output_check(folder, comp, (comp_dir / f"{name}.drwl.tflite_ofm.bin").read_bytes(), runs)
        valid = all(r["valid"] for rs in runs.values() for r in rs) and sorted(runs) == [1, 2] \
            and all(len(rs) == 4 for rs in runs.values())
        gate = "PASS" if valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") else "FAIL"
        recs = [r["record"] for rs in runs.values() for r in rs]
        counters = dict(  # descriptive: the PMU was reset at the arm and stopped with the NPU (D6-style)
            stopped_after_irq=all(x.get(f"ev_post{i}") == x.get(f"ev_irq{i}") for x in recs for i in range(8)),
            pmcr_at_arm=sorted({hex(x.get("pmcr_at_arm", 0)) for x in recs}),
            arm_irq_counts=sorted({(x.get("arm_count"), x.get("irq_count")) for x in recs}))
        cfgs[c] = dict(gate_c=gate, runs_valid=valid, output=oc, compile=comp, macs=comp["n_mac"], runs=runs,
                       counters=counters, metrics=metrics(runs, comp["n_mac"]))
    pairs = {f"{b}->{v}": (pair(cfgs[b], cfgs[v]) if cfgs[b]["gate_c"] == cfgs[v]["gate_c"] == "PASS"
                           else dict(verdict="EXCLUDED", why=f"gate C {cfgs[b]['gate_c']} / {cfgs[v]['gate_c']}"))
             for b, v in PAIRS}
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for c, x in cfgs.items():
        comp = x["compile"]
        rows.append(dict(config=c, gate_b="PASS" if comp["gate_b"] else "FAIL", gate_c=x["gate_c"],
                         output=x.get("output", {}).get("verdict"), macs=x["macs"],
                         vela_npu_cycles=comp["vela_npu_cycles"], ofm_block=comp["ofm_block"],
                         ofm_ublock=comp["ofm_ublock"], kernels=comp["n_kernels"], **x["metrics"]))
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(out / "stage4_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    oc_rows = [dict(config=c, **{k: v for k, v in x.get("output", {}).items()}) for c, x in cfgs.items()]
    cols = list(dict.fromkeys(k for r in oc_rows for k in r))
    with open(out / "stage4_output_checks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(oc_rows)
    res = dict(configs={c: {k: v for k, v in x.items() if k not in ("runs", "compile")} for c, x in cfgs.items()},
               pairs=pairs)
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4], *(int(x) for x in sys.argv[4:5])), indent=1, default=str))
