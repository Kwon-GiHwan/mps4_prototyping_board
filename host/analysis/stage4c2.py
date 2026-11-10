#!/usr/bin/env python3
"""Stage 4C-2 (evidence/stage4c2/contract.md): MAC activity of the 1x1 Conv (24x24, Cout 96) for Cin 16/32/64/128.
TA profile 1, driver runner image 83398c7, Vela 5.0.0, pass A + pass B, 1 warm-up + 4 measured RUNs each.

  python3 host/analysis/stage4c2.py static <workloads dir> <out dir>
  python3 host/analysis/stage4c2.py judge <campaign root> <workloads dir> <stage4 root> <out dir>

static — per kernel, from the command stream the board runs and Vela's debug record (no measurement):
  OFM ublocks = ceil(H / ub_h) * ceil(W / ub_w) * ceil(kernel OFM channel slice / ub_c)   (the output area)
  IFM depth steps = ceil(kernel IFM depth / IFM block depth)                                (the input direction)
  OFM-ublock x IFM-step = their product (a count of output area x input-direction blocks; a definition, not a cost)
judge — per config VALID / INVALID (output PASS_EXACT or PASS_TOLERANCE, every measured RUN valid, both passes with 4
  measured RUNs); base check against Stage 4 (output sha256 and every counter constant in both) else BASELINE_MISMATCH
  and no pair is interpreted; adjacent pairs 16->32, 32->64, 64->128 with Stage 4's pair rule on pass A, pass B as a
  check (opposite signs -> UNRESOLVED); each pair is `SAME_SCHEDULE` (traversal, OFM/IFM block, ublock, kernel slices
  equal) or `SCHEDULE_CHANGED`. MAC_ACTIVE / ublocks is a normalisation of the whole-run count, not a per-ublock time.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4c1 as P  # noqa: E402

CONFIGS = {"s4_conv_base": 16, "s4c2_conv_cin32": 32, "s4c2_conv_cin64": 64, "s4c2_conv_cin128": 128}
PAIRS = [("s4_conv_base", "s4c2_conv_cin32"), ("s4c2_conv_cin32", "s4c2_conv_cin64"),
         ("s4c2_conv_cin64", "s4c2_conv_cin128")]


def static_one(wl: pathlib.Path, cfg: str) -> dict:
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    ks = P.kernels((wl / f"{cfg}.drwl.cms.bin").read_bytes())
    _, h, w, _ = comp["ofm_shape"]
    uh, uw, uc = map(int, comp["ofm_ublock"].split("x"))
    ib = int(comp["ifm_block"].split("x")[2])
    rows = []
    for k in ks:
        sl, idep = k["ofm_depth_m1"] + 1, k["ifm_depth_m1"] + 1
        ub = math.ceil(h / uh) * math.ceil(w / uw) * math.ceil(sl / uc)
        steps = math.ceil(idep / ib)
        rows.append(dict(kind=k["kind"], ofm_slice=sl, ifm_depth=idep, ofm_ublocks=ub, ifm_depth_steps=steps,
                         ublock_x_steps=ub * steps, acc_format=k["acc_format"],
                         block=f"{k['blk_height_m1'] + 1}x{k['blk_width_m1'] + 1}x{k['blk_depth_m1'] + 1}",
                         weight_lengths=[k[n] for n in ("weight_length", "weight1_length", "weight2_length",
                                                        "weight3_length")], dma_before=k["dma_before"]))
    return dict(config=cfg, cin=comp["ifm_shape"][-1], n_mac=comp["n_mac"], ofm_block=comp["ofm_block"],
                ifm_block=comp["ifm_block"], ofm_ublock=comp["ofm_ublock"], traversal=comp["traversal"],
                n_kernels=comp["n_kernels"], kernels=rows, ofm_ublocks=sum(r["ofm_ublocks"] for r in rows),
                ublock_x_steps=sum(r["ublock_x_steps"] for r in rows), weight_bytes=comp["weight_bytes"],
                vela_npu_cycles=comp["vela_npu_cycles"], vela_mac_cycles=comp["vela_mac_cycles"],
                vela_op_cycles=comp["vela_op_cycles"], gate_b=comp["gate_b"], vela_ops=comp["vela_ops"],
                model_sha256=comp["model_sha256"], cms_sha256=comp["cms_sha256"], drwl_sha256=comp["drwl_sha256"],
                schedule=(comp["traversal"], comp["ofm_block"], comp["ifm_block"], comp["ofm_ublock"],
                          tuple(r["ofm_slice"] for r in rows)))


def static(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {c: static_one(wl, c) for c in CONFIGS}
    o.mkdir(parents=True, exist_ok=True)
    (o / "static.json").write_text(json.dumps(res, indent=1))
    return res


def judge(root: str, wl: str, s4_root: str, out: str) -> dict:
    root, wl, s4, o = map(pathlib.Path, (root, wl, s4_root, out))
    st = {c: static_one(wl, c) for c in CONFIGS}
    res = {}
    for c in CONFIGS:
        folder = root / "conds" / c / "wfe"
        runs = S4.load(folder, 1)
        comp = json.loads((wl / f"{c}.compile.json").read_text())
        oc = S4.output_check(folder, comp, (wl / f"{c}.drwl.tflite_ofm.bin").read_bytes(), runs)
        valid = all(r["valid"] for rs in runs.values() for r in rs) and sorted(runs) == [1, 2] \
            and all(len(rs) == 4 for rs in runs.values())
        m = S4.metrics(runs, comp["n_mac"])
        mac, dpu = m["A_48"], m["A_51"]
        res[c] = dict(verdict="VALID" if valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") else "INVALID",
                      output=oc, runs=runs, comp=comp, metrics=m,
                      mac_active_per_ublock=mac / st[c]["ofm_ublocks"] if mac is not None else None,
                      dpu_active_per_ublock=dpu / st[c]["ofm_ublocks"] if dpu is not None else None,
                      mac_active_per_ublock_x_step=mac / st[c]["ublock_x_steps"] if mac is not None else None,
                      macs_per_mac_active=comp["n_mac"] / mac if mac else None)
    old = S4.load(s4 / "conds" / "s4_conv_base" / "wfe", 1)
    now, then = P.constant_counters(res["s4_conv_base"]["runs"]), P.constant_counters(old)
    diff = {f"set{k[0]}_ev{k[1]}": (then[k], now[k]) for k in set(now) & set(then) if now[k] != then[k]}
    same_out = hashlib.sha256((s4 / "conds" / "s4_conv_base" / "wfe" / "output.bin").read_bytes()).hexdigest() \
        == res["s4_conv_base"]["output"].get("npu_sha256")
    base = dict(ok=same_out and not diff, output_same=same_out, differing_constant_counters=diff,
                compared=len(set(now) & set(then)))
    pairs = {}
    for b, v in PAIRS:
        key = f"{b}->{v}"
        if not base["ok"]:
            pairs[key] = dict(verdict="NOT_INTERPRETED", why="BASELINE_MISMATCH")
            continue
        if "INVALID" in (res[b]["verdict"], res[v]["verdict"]):
            pairs[key] = dict(verdict="EXCLUDED", why="INVALID config")
            continue
        cb = dict(runs=res[b]["runs"], macs=res[b]["comp"]["n_mac"], compile=res[b]["comp"], metrics=res[b]["metrics"])
        cv = dict(runs=res[v]["runs"], macs=res[v]["comp"]["n_mac"], compile=res[v]["comp"], metrics=res[v]["metrics"])
        pa = S4.pair(cb, cv)
        pb = S4.pair(dict(cb, runs={1: cb["runs"][2], 2: cb["runs"][2]}),
                     dict(cv, runs={1: cv["runs"][2], 2: cv["runs"][2]}))
        opposite = (pa["npu_active_variant"] - pa["npu_active_base"]) * \
                   (pb["npu_active_variant"] - pb["npu_active_base"]) < 0
        mb, mv = res[b]["metrics"]["A_48"], res[v]["metrics"]["A_48"]
        pairs[key] = dict(verdict="UNRESOLVED" if opposite else pa["verdict"], pass_a=pa, pass_b_verdict=pb["verdict"],
                          pass_b_npu_active_change_pct=pb["npu_active_change_pct"], directions_opposite=opposite,
                          schedule="SAME_SCHEDULE" if st[b]["schedule"] == st[v]["schedule"] else "SCHEDULE_CHANGED",
                          mac_ratio=res[v]["comp"]["n_mac"] / res[b]["comp"]["n_mac"], mac_active_ratio=mv / mb,
                          mac_dpu_ratio=res[v]["metrics"]["A_51"] / res[b]["metrics"]["A_51"])
    summary = dict(baseline=base, pairs=pairs, static=st,
                   configs={c: {k: x for k, x in r.items() if k not in ("runs", "comp")} for c, r in res.items()})
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    a = sys.argv[1:]
    r = static(*a[1:3]) if a[0] == "static" else judge(*a[1:5])
    print(json.dumps(r, indent=1, default=str)[:3000])
