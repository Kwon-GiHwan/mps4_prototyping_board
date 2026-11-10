#!/usr/bin/env python3
"""Stage 4C-2b (evidence/stage4c2b/contract.md): MAC_ACTIVE of the DepthFirst 1x1 Conv at Cin 40 and 48 against four
pre-registered hypotheses, with Cin 64 as the in-session reference. TA profile 1, driver runner 83398c7, pass A + B,
1 warm-up + 4 measured RUNs each.

  python3 host/analysis/stage4c2b.py predict <workloads dir> <out dir>
  python3 host/analysis/stage4c2b.py judge <campaign root> <workloads dir> <stage4c2 root> <predictions.json> <out dir>

Hypotheses (owner 2026-11-11; MACs = 24*24*96*Cin from the compiled model):
  H1 MACs / 768            H2 4,608 (as Cin 64)       H3 MACs / 384            H4 24*24*96*roundup(Cin, 16) / 768
Per config: INVALID (output not PASS_EXACT/PASS_TOLERANCE or a measured RUN not valid or a pass incomplete) >
MEASUREMENT_UNSTABLE (the 4 measured pass-A MAC_ACTIVE values differ) > MATCH:<hypotheses whose value equals every
RUN> > NONE_MATCHED. Reference: Cin 64 must give MAC_ACTIVE = MAC_DPU_ACTIVE = 4,608 in every measured RUN, the 4C-2
(boot 346) output sha256 and every commonly constant counter; else REFERENCE_MISMATCH and no hypothesis verdict.
"""
from __future__ import annotations

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

CONFIGS = {"s4c2_conv_cin40": 40, "s4c2_conv_cin48": 48, "s4c2_conv_cin64": 64}
REF = "s4c2_conv_cin64"
REF_MAC = 4608


def hypotheses(macs: int, cin: int) -> dict:
    return dict(H1=macs / 768, H2=4608, H3=macs / 384, H4=24 * 24 * 96 * math.ceil(cin / 16) * 16 / 768)


def predict(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {}
    for c, cin in CONFIGS.items():
        st = C2.static_one(wl, c)
        assert st["n_mac"] == 24 * 24 * 96 * cin, c
        h = hypotheses(st["n_mac"], cin)
        vals = list(h.values())
        res[c] = dict(cin=cin, n_mac=st["n_mac"], hypotheses=h,
                      distinct={k: vals.count(v) == 1 for k, v in h.items()},
                      static={k: st[k] for k in ("traversal", "ofm_block", "ifm_block", "ofm_ublock", "ofm_ublocks",
                                                 "ublock_x_steps", "n_kernels", "weight_bytes", "drwl_sha256")},
                      kernels=[{k: x[k] for k in ("ofm_slice", "ifm_depth", "ofm_ublocks", "ifm_depth_steps")}
                               for x in st["kernels"]])
    o.mkdir(parents=True, exist_ok=True)
    (o / "predictions.json").write_text(json.dumps(res, indent=1))
    return res


def verdict(macs_per_run: list, valid: bool, out_ok: bool, hyp: dict) -> str:
    if not (valid and out_ok):
        return "INVALID"
    if len(set(macs_per_run)) != 1:
        return "MEASUREMENT_UNSTABLE"
    hit = [k for k, v in hyp.items() if macs_per_run[0] == v]   # all RUNs are equal here
    return "MATCH:" + "+".join(hit) if hit else "NONE_MATCHED"


def judge(root: str, wl: str, c2_root: str, pred_path: str, out: str) -> dict:
    root, wl, c2, o = map(pathlib.Path, (root, wl, c2_root, out))
    pred = json.loads(pathlib.Path(pred_path).read_text())
    res = {}
    for c in CONFIGS:
        folder = root / "conds" / c / "wfe"
        runs = S4.load(folder, 1)
        comp = json.loads((wl / f"{c}.compile.json").read_text())
        oc = S4.output_check(folder, comp, (wl / f"{c}.drwl.tflite_ofm.bin").read_bytes(), runs)
        valid = all(r["valid"] for rs in runs.values() for r in rs) and sorted(runs) == [1, 2] \
            and all(len(rs) == 4 for rs in runs.values())
        mac = [r["ev"].get(48) for r in runs.get(1, [])]
        dpu = [r["ev"].get(51) for r in runs.get(1, [])]
        m = S4.metrics(runs, comp["n_mac"])
        st = pred[c]["static"]
        res[c] = dict(mac_active_per_run=mac, mac_dpu_active_per_run=dpu, output=oc, runs_valid=valid,
                      verdict=verdict(mac, valid, oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE"), pred[c]["hypotheses"]),
                      macs_per_mac_active=[comp["n_mac"] / x for x in mac if x],
                      macs_per_mac_dpu_active=[comp["n_mac"] / x for x in dpu if x],
                      dpu_over_mac=[d / x for d, x in zip(dpu, mac) if x],
                      mac_active_per_ofm_ublock=[x / st["ofm_ublocks"] for x in mac if x is not None],
                      ofm_ublocks=st["ofm_ublocks"], ublock_x_steps=st["ublock_x_steps"], metrics=m, runs=runs)
    r64 = res[REF]
    old = S4.load(c2 / "conds" / REF / "wfe", 1)
    now, then = C1.constant_counters(r64["runs"]), C1.constant_counters(old)
    diff = {f"set{k[0]}_ev{k[1]}": (then[k], now[k]) for k in set(now) & set(then) if now[k] != then[k]}
    same_out = hashlib.sha256((c2 / "conds" / REF / "wfe" / "output.bin").read_bytes()).hexdigest() \
        == r64["output"].get("npu_sha256")
    ref_ok = (r64["verdict"] != "INVALID" and set(r64["mac_active_per_run"]) == {REF_MAC}
              and set(r64["mac_dpu_active_per_run"]) == {REF_MAC} and same_out and not diff)
    reference = dict(ok=ref_ok, output_same=same_out, differing_constant_counters=diff,
                     mac=r64["mac_active_per_run"], dpu=r64["mac_dpu_active_per_run"])
    if not ref_ok:
        for c in ("s4c2_conv_cin40", "s4c2_conv_cin48"):
            res[c]["verdict"] = "NOT_JUDGED (REFERENCE_MISMATCH)"
    pairs = {}
    for b, v in (("s4c2_conv_cin40", "s4c2_conv_cin48"), ("s4c2_conv_cin48", "s4c2_conv_cin64")):
        if not ref_ok or "INVALID" in (res[b]["verdict"], res[v]["verdict"]):
            pairs[f"{b}->{v}"] = dict(verdict="NOT_INTERPRETED")
            continue
        cb = dict(runs=res[b]["runs"], macs=pred[b]["n_mac"], compile=json.loads((wl / f"{b}.compile.json").read_text()),
                  metrics=res[b]["metrics"])
        cv = dict(runs=res[v]["runs"], macs=pred[v]["n_mac"], compile=json.loads((wl / f"{v}.compile.json").read_text()),
                  metrics=res[v]["metrics"])
        pa = S4.pair(cb, cv)
        pb = S4.pair(dict(cb, runs={1: cb["runs"][2], 2: cb["runs"][2]}), dict(cv, runs={1: cv["runs"][2], 2: cv["runs"][2]}))
        opposite = (pa["npu_active_variant"] - pa["npu_active_base"]) * (pb["npu_active_variant"] - pb["npu_active_base"]) < 0
        pairs[f"{b}->{v}"] = dict(verdict="UNRESOLVED" if opposite else pa["verdict"], pass_a=pa,
                                  pass_b_npu_active_change_pct=pb["npu_active_change_pct"], directions_opposite=opposite)
    summary = dict(reference=reference, pairs=pairs,
                   configs={c: {k: x for k, x in r.items() if k != "runs"} for c, r in res.items()})
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    a = sys.argv[1:]
    r = predict(*a[1:3]) if a[0] == "predict" else judge(*a[1:6])
    print(json.dumps(r, indent=1, default=str)[:3000])
