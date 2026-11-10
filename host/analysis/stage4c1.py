#!/usr/bin/env python3
"""Stage 4C-1 (evidence/stage4c1/contract.md): output-write beat predictions from the compiled artifacts (before the
board) and the verdicts after it. TA profile 1, driver runner, Vela 5.0.0, 1 warm-up + 4 measured RUNs per pass.

  python3 host/analysis/stage4c1.py predict <workloads dir> <out dir>
  python3 host/analysis/stage4c1.py judge <campaign root> <workloads dir> <predictions.json> <stage4 root> <out dir>

predict — inputs only from the artifacts: per kernel, the registers of the command stream (`.drwl.cms.bin`, the bytes
the board runs); the OFM absolute address = the runner's arena (0x70000000 + Vela model length, rounded up to 16 bytes:
workload.c drwl_arena_after, checked on all Stage 4 records) + the OFM region offset of the first kernel. Rules A-D:
evidence/stage4/beat_model.py (unchanged rules; count_at). Nothing measured is an input.

judge — per config: INVALID (output not PASS_EXACT/PASS_TOLERANCE, a measured RUN not valid, a pass missing, or the
record's region-1 base differs from the predicted arena) > NOT_COMPARABLE (fixed before the board) >
MEASUREMENT_UNSTABLE (event 391 differs between the 4 measured pass-B RUNs) > PREDICTION_MATCH (all four = rule A's
prediction) / PREDICTION_MISMATCH. A config discriminates the rules only when A's prediction differs from B, C and D.
Base check: the bases' NPU output sha256 and every counter that was constant across measured RUNs both in Stage 4 and
now must equal Stage 4's; otherwise BASELINE_MISMATCH and the pairs are not interpreted. Pairs: stage4.pair on pass A
(primary) and on pass B (reproduction); opposite signs of the NPU_ACTIVE change -> UNRESOLVED.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms  # noqa: E402
import drwl  # noqa: E402
from cms_regs import C0, C1, OP_DMA_START, kernels  # noqa: E402,F401
import stage4 as S4  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("beat_model", REPO / "evidence/stage4/beat_model.py")
BM = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(BM)

CONFIGS = ("s4_conv_base", "s4c_conv_cout94", "s4c_conv_cout97", "s4_dw_base", "s4c_dw_c142", "s4c_dw_c145")
PAIRS = [("s4_conv_base", "s4c_conv_cout94"), ("s4_conv_base", "s4c_conv_cout97"),
         ("s4_dw_base", "s4c_dw_c142"), ("s4_dw_base", "s4c_dw_c145")]
MODEL_BASE, ALIGN = 0x70000000, 16
def arena(model_len: int) -> int:
    return (MODEL_BASE + model_len + ALIGN - 1) & ~(ALIGN - 1)


def predict_one(wl: pathlib.Path, cfg: str) -> dict:
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    meta = json.loads((wl / f"{cfg}.drwl.json").read_text())
    stream = (wl / f"{cfg}.drwl.cms.bin").read_bytes()
    assert hashlib.sha256(stream).hexdigest() == meta["cms_sha256"], cfg
    h = drwl.parse((wl / f"{cfg}.drwl").read_bytes())
    ks = kernels(stream)
    k0 = ks[0]
    _, hh, ww, c = comp["ofm_shape"]
    slices = [k["ofm_depth_m1"] + 1 for k in ks]
    dense = (k0["ofm_stride_x"] == c and k0["ofm_stride_y"] == ww * c and k0["ofm_stride_c"] == 1
             and all(k["ofm_region"] == 1 for k in ks) and sum(slices) == c
             and [k["ofm_base0"] - k0["ofm_base0"] for k in ks] == [sum(slices[:i]) for i in range(len(ks))])
    base = arena(h["model_len"]) + k0["ofm_base0"]
    ar = lambda cc: [(0, cc)]
    rule_c = lambda cc: [(sum(slices[:i]), s) for i, s in enumerate(slices)]
    pred = dict(A=BM.count_at(base, hh, ww, c, c, ww * c, BM.rule_a), B=BM.count_at(base, hh, ww, c, c, ww * c, ar),
                C=BM.count_at(base, hh, ww, c, c, ww * c, rule_c), D=-(-hh * ww * c // 16))
    return dict(config=cfg, ofm_shape=comp["ofm_shape"], ifm_shape=comp["ifm_shape"], model_len=h["model_len"],
                arena=hex(arena(h["model_len"])), ofm_address=hex(base), ofm_address_mod16=base % 16,
                ofm_address_alignment=next(a for a in (64, 32, 16, 8, 4, 2, 1) if base % a == 0), dense_nhwc=dense,
                kernels=[dict(kind=k["kind"], ifm_depth=k["ifm_depth_m1"] + 1, ofm_depth=k["ofm_depth_m1"] + 1,
                              ifm_stride_x=k["ifm_stride_x"], ifm_stride_y=k["ifm_stride_y"],
                              ofm_stride_x=k["ofm_stride_x"], ofm_stride_y=k["ofm_stride_y"], ifm_base0=hex(k["ifm_base0"]),
                              ofm_base0=hex(k["ofm_base0"]), ifm_region=k["ifm_region"], ofm_region=k["ofm_region"],
                              ifm_precision=k["ifm_precision"], ofm_precision=k["ofm_precision"],
                              block=f"{k['blk_height_m1'] + 1}x{k['blk_width_m1'] + 1}x{k['blk_depth_m1'] + 1}",
                              weight_lengths=[k[n] for n in ("weight_length", "weight1_length", "weight2_length",
                                                             "weight3_length")], dma_before=k["dma_before"])
                         for k in ks],
                ofm_block=comp["ofm_block"], ofm_ublock=comp["ofm_ublock"], n_kernels=comp["n_kernels"],
                weight_bytes=comp["weight_bytes"], n_mac=comp["n_mac"], vela_npu_cycles=comp["vela_npu_cycles"],
                vela_op_cycles=comp["vela_op_cycles"], gate_b=comp["gate_b"], vela_ops=comp["vela_ops"],
                model_sha256=comp["model_sha256"], vela_sha256=comp["vela_sha256"], cms_sha256=comp["cms_sha256"],
                drwl_sha256=comp["drwl_sha256"], predicted_write_beats=pred,
                discriminating=pred["A"] not in (pred["B"], pred["C"], pred["D"]),
                not_comparable=not (comp["gate_b"] and dense and comp["ifm_memory"] == comp["ofm_memory"] == "Dram"
                                    and comp["ofm_format"] == "NHWC"))


def predict(wl: str, out: str) -> dict:
    wl, o = pathlib.Path(wl), pathlib.Path(out)
    res = {c: predict_one(wl, c) for c in CONFIGS}
    res["_inputs"] = dict(beat_model_sha256=hashlib.sha256((REPO / "evidence/stage4/beat_model.py").read_bytes()).hexdigest(),
                          rule="beat_model.count_at with the predicted OFM address and dense NHWC strides")
    o.mkdir(parents=True, exist_ok=True)
    (o / "predictions.json").write_text(json.dumps(res, indent=1))
    return res


def judge_one(folder: pathlib.Path, wl: pathlib.Path, cfg: str, pred: dict) -> dict:
    runs = S4.load(folder, 1)
    comp = json.loads((wl / f"{cfg}.compile.json").read_text())
    oc = S4.output_check(folder, comp, (wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), runs)
    valid = all(r["valid"] for rs in runs.values() for r in rs) and sorted(runs) == [1, 2] \
        and all(len(rs) == 4 for rs in runs.values())
    bases = {r["record"]["base1"] for rs in runs.values() for r in rs}
    addr_ok = bases == {int(pred["arena"], 16)}
    beats = [r["ev"].get(391) for r in runs.get(2, [])]
    if not (valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") and addr_ok):
        v = "INVALID"
    elif pred["not_comparable"]:
        v = "NOT_COMPARABLE"
    elif len(set(beats)) != 1:
        v = "MEASUREMENT_UNSTABLE"
    else:
        v = "PREDICTION_MATCH" if beats[0] == pred["predicted_write_beats"]["A"] else "PREDICTION_MISMATCH"
    return dict(verdict=v, measured_write_beats=beats, predicted=pred["predicted_write_beats"],
                discriminating=pred["discriminating"], address_as_predicted=addr_ok, runs_valid=valid, output=oc,
                runs=runs, comp=comp, metrics=S4.metrics(runs, comp["n_mac"]))


def constant_counters(runs: dict) -> dict:
    out = {}
    for s, rs in runs.items():
        for code in rs[0]["ev"]:
            v = {r["ev"].get(code) for r in rs}
            if len(v) == 1:
                out[(s, code)] = v.pop()
    return out


def judge(root: str, wl: str, pred_path: str, s4_root: str, out: str) -> dict:
    root, wl, s4, o = pathlib.Path(root), pathlib.Path(wl), pathlib.Path(s4_root), pathlib.Path(out)
    pred = json.loads(pathlib.Path(pred_path).read_text())
    res = {c: judge_one(root / "conds" / c / "wfe", wl, c, pred[c]) for c in CONFIGS}
    base_check = {}
    for b in ("s4_conv_base", "s4_dw_base"):
        old = S4.load(s4 / "conds" / b / "wfe", 1)
        now, then = constant_counters(res[b]["runs"]), constant_counters(old)
        diff = {f"set{k[0]}_ev{k[1]}": (then[k], now[k]) for k in set(now) & set(then) if now[k] != then[k]}
        same_out = hashlib.sha256((s4 / "conds" / b / "wfe" / "output.bin").read_bytes()).hexdigest() \
            == res[b]["output"].get("npu_sha256")
        base_check[b] = dict(ok=same_out and not diff, output_same=same_out, differing_constant_counters=diff,
                             compared=len(set(now) & set(then)))
    baseline_ok = all(x["ok"] for x in base_check.values())
    pairs = {}
    for b, v in PAIRS:
        if not baseline_ok:
            pairs[f"{b}->{v}"] = dict(verdict="NOT_INTERPRETED", why="BASELINE_MISMATCH")
            continue
        if res[b]["verdict"] == "INVALID" or res[v]["verdict"] == "INVALID":
            pairs[f"{b}->{v}"] = dict(verdict="EXCLUDED", why="INVALID config")
            continue
        cb = dict(runs=res[b]["runs"], macs=res[b]["comp"]["n_mac"], compile=res[b]["comp"], metrics=res[b]["metrics"])
        cv = dict(runs=res[v]["runs"], macs=res[v]["comp"]["n_mac"], compile=res[v]["comp"], metrics=res[v]["metrics"])
        pa = S4.pair(cb, cv)
        pb = S4.pair(dict(cb, runs={1: cb["runs"][2], 2: cb["runs"][2]}), dict(cv, runs={1: cv["runs"][2], 2: cv["runs"][2]}))
        opposite = (pa["npu_active_variant"] - pa["npu_active_base"]) * (pb["npu_active_variant"] - pb["npu_active_base"]) < 0
        pairs[f"{b}->{v}"] = dict(verdict="UNRESOLVED" if opposite else pa["verdict"], pass_a=pa, pass_b_verdict=pb["verdict"],
                                  pass_b_npu_active_change_pct=pb["npu_active_change_pct"], directions_opposite=opposite,
                                  mac_active_base=res[b]["metrics"].get("A_48"), mac_active_variant=res[v]["metrics"].get("A_48"),
                                  ext_read_beats=(res[b]["metrics"].get("B_386"), res[v]["metrics"].get("B_386")),
                                  ext_write_beats=(res[b]["metrics"].get("B_391"), res[v]["metrics"].get("B_391")))
    summary = dict(baseline_ok=baseline_ok, base_check=base_check, pairs=pairs,
                   configs={c: {k: x for k, x in r.items() if k not in ("runs", "comp")} for c, r in res.items()})
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    a = sys.argv[1:]
    r = predict(*a[1:3]) if a[0] == "predict" else judge(*a[1:6])
    print(json.dumps(r, indent=1, default=str)[:4000])
