#!/usr/bin/env python3
"""Stage 5-1 (evidence/stage5/contract.md): SRAM workspace budget (Vela --arena-cache-size) in Dedicated_Sram on the
driver runner image 83398c7, TA profile 1, pass A + pass B, 1 warm-up + 4 measured RUNs.

  python3 host/analysis/stage5.py <campaign root> <workloads dir> <stage5_0.json> <out dir> [5-1 | 5-2]

Per config (conds/<workload>_<variant>/wfe):
  output   NPU output (output.bin) vs the DRWL golden: MLEK models byte-exact (amendment 2) -> PASS_EXACT / FAIL;
           isolated operators PASS_EXACT / PASS_TOLERANCE (<= 1 LSB, owner rule) / FAIL; INVALID if the length differs,
           the RUNs' output CRCs differ, or the firmware count disagrees. Also recorded: equal to the base's NPU output.
  config   VALID (output PASS_*, 4 measured RUNs valid in both passes) / INVALID / NOT_EXECUTABLE (no completed RUN)
  base     reproduction of the earlier measurement of the same DRWL (m7 for kws/ad, warm-up 2; Stage 4 for conv/dw,
           warm-up 1): every counter constant in both, matched by event-set content, must be equal, and the earlier
           output must have matched the same golden; else BASELINE_MISMATCH -> that workload's pairs not interpreted
  pairs    base -> variant: stage4.pair on pass A (NPU_ACTIVE; tol = max(1 %, either RUN range)), the same rule on pass
           B as a check (opposite signs -> UNRESOLVED); MAC_ACTIVE / MAC_DPU_ACTIVE compared exactly where both are
           constant; traffic per stage4.pair; the 5-0 class (all 5-1 variants: SCHEDULE_CHANGED -> whole-config effect)
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import drwl  # noqa: E402
import stage4 as S4  # noqa: E402
from fi101_s013 import MANIFESTS  # noqa: E402  (the project's N_MAC source, Stage 1/3)

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKLOADS = {"kws_micronet_m": ("model", ("base", "cache64k", "cache0")),
             "ad_medium_int8": ("model", ("base", "cache64k", "cache0")),
             "s4_dw_base": ("op", ("base", "cache0")), "s4_conv_base": ("op", ("base", "cache0"))}
# Effective MACs = the project definition: N_MAC of the original tflite (host/container/workload_meta.py; CONV_2D,
# DEPTHWISE_CONV_2D, FULLY_CONNECTED, BATCH_MATMUL), as used by Stage 1/3. An isolated operator has no manifest entry:
# its base compile's count is used (one operator: Vela's count equals the formula, Stage 4 gate B).
EFFECTIVE = {k: v["n_mac"] for f in MANIFESTS for k, v in json.loads((REPO / f).read_text())["workloads"].items()
             if isinstance(v, dict) and v.get("n_mac")}
EARLIER = {"kws_micronet_m": (REPO / "evidence/driver_m7/raw/wfe/kws_micronet_m", 2),
           "ad_medium_int8": (REPO / "evidence/driver_m7/raw/wfe/ad_medium_int8", 2),
           "s4_dw_base": (REPO / "evidence/stage4/raw/conds/s4_dw_base/wfe", 1),
           "s4_conv_base": (REPO / "evidence/stage4/raw/conds/s4_conv_base/wfe", 1)}
# Stage 5-2 (evidence/stage5_2/contract.md): Size vs Performance at the same budget (384 KiB); bases re-measured in the
# session and checked against their latest measurement on the same image (5-1 boots 351/354, 4C-2b boot 350)
WORKLOADS_52 = {"kws_micronet_m": ("model", ("base", "size")), "ad_medium_int8": ("model", ("base", "size")),
                "s4c2_conv_cin64": ("op", ("base", "size"))}
EARLIER_52 = {"kws_micronet_m": (REPO / "evidence/stage5/raw/conds/kws_micronet_m_base/wfe", 1),
              "ad_medium_int8": (REPO / "evidence/stage5/raw/conds/ad_medium_int8_base/wfe", 1),
              "s4c2_conv_cin64": (REPO / "evidence/stage4c2b/raw/conds/s4c2_conv_cin64/wfe", 1)}
PLANS = {"5-1": (WORKLOADS, EARLIER), "5-2": (WORKLOADS_52, EARLIER_52)}


def golden(wl: pathlib.Path, name: str) -> bytes:
    b = (wl / f"{name}.drwl").read_bytes()
    return b"".join(b[o:o + n] for o, n in drwl.parse(b)["outputs"])


def output_check(folder: pathlib.Path, gold: bytes, runs: dict, exact_only: bool) -> dict:
    out = folder / "output.bin"
    allr = [r for rs in runs.values() for r in rs]
    if not out.exists() or not allr:
        return dict(verdict="INVALID", why="no output")
    npu = out.read_bytes()
    if len(npu) != len(gold):
        return dict(verdict="INVALID", why=f"length {len(npu)} vs {len(gold)}")
    if {r["crc"] for r in allr} != {zlib.crc32(npu)}:
        return dict(verdict="INVALID", why="output CRC differs between RUNs")
    s = lambda x: x - 256 if x > 127 else x
    d = [abs(s(a) - s(b)) for a, b in zip(npu, gold)]
    mism, mx = sum(x != 0 for x in d), max(d, default=0)
    if {(r["record"]["ofm_mismatch"], r["record"]["ofm_max_diff"]) for r in allr} != {(mism, mx)}:
        return dict(verdict="INVALID", why="firmware count disagrees")
    v = "PASS_EXACT" if mx == 0 else ("PASS_TOLERANCE" if mx <= 1 and not exact_only else "FAIL")
    return dict(verdict=v, mismatch_count=mism, max_abs_diff=mx, npu_sha256=hashlib.sha256(npu).hexdigest())


def constant_by_set(runs: dict) -> dict:
    """{(event set content, code): value} for counters constant across the measured RUNs."""
    out = {}
    for rs in runs.values():
        key = tuple(sorted(rs[0]["ev"]))
        for code in key:
            v = {r["ev"].get(code) for r in rs}
            if len(v) == 1:
                out[(key, code)] = v.pop()
    return out


def comp_of(c50: dict, wl: pathlib.Path, name: str, n_mac: int) -> dict:
    """n_mac = effective MACs (EFFECTIVE); Vela's own count of this compile stays in vela_macs."""
    meta = json.loads((wl / f"{name}.drwl.json").read_text())
    return dict(n_mac=n_mac, vela_macs=c50["nn_macs"], ofm_block=c50["compute_sig"], ofm_ublock="", n_kernels=c50["kernels"],
                vela_npu_cycles=c50["cycles_npu"], vela_sha256=meta["vela_sha256"])


def main(root: str, wl: str, s50: str, out: str, plan: str = "5-1") -> dict:
    root, wl, o = pathlib.Path(root), pathlib.Path(wl), pathlib.Path(out)
    workloads, earlier_dirs = PLANS[plan]
    c50 = json.loads(pathlib.Path(s50).read_text())
    res, base_check, pairs = {}, {}, {}
    for w, (kind, variants) in workloads.items():
        gold = golden(wl, f"{w}_base")
        for v in variants:
            name = f"{w}_{v}"
            folder = root / "conds" / name / "wfe"
            comp = comp_of(c50[w][v], wl, name, EFFECTIVE.get(w, c50[w]["base"]["nn_macs"]))
            assert comp["vela_sha256"] == c50[w][v]["vela_sha256"], name   # the measured DRWL is the 5-0 artifact
            if not (folder / "runs.csv").exists() or not S4.load(folder, 1):   # a refused first RUN writes no runs.csv
                res[name] = dict(verdict="NOT_EXECUTABLE", why="no completed RUN")
                continue
            runs = S4.load(folder, 1)
            assert golden(wl, name) == gold, name
            oc = output_check(folder, gold, runs, kind == "model")
            valid = all(r["valid"] for rs in runs.values() for r in rs) and sorted(runs) == [1, 2] \
                and all(len(rs) == 4 for rs in runs.values())
            res[name] = dict(verdict="VALID" if valid and oc["verdict"].startswith("PASS") else "INVALID",
                             output=oc, runs=runs, comp=comp, c50=c50[w][v], metrics=S4.metrics(runs, comp["n_mac"]),
                             constant=constant_by_set(runs))
        b = res.get(f"{w}_base", {})
        if b.get("verdict") == "VALID":
            for v in variants[1:]:
                x = res[f"{w}_{v}"]
                if x.get("verdict") == "VALID":
                    x["same_output_as_base"] = x["output"]["npu_sha256"] == b["output"]["npu_sha256"]
        e_dir, e_warm = earlier_dirs[w]
        earlier = S4.load(e_dir, e_warm) if (e_dir / "runs.csv").exists() else {}
        if b.get("verdict") != "VALID" or not earlier:
            base_check[w] = dict(ok=False, why="base not VALID or earlier data missing")
        else:
            then, now = constant_by_set(earlier), b["constant"]
            common = set(then) & set(now)
            diff = {f"{k[1]}@{len(k[0])}ev": (then[k], now[k]) for k in common if then[k] != now[k]}
            early_out = all(r["record"]["ofm_mismatch"] == 0 for rs in earlier.values() for r in rs)
            base_check[w] = dict(ok=not diff and early_out and b["output"]["verdict"] == "PASS_EXACT",
                                 compared=len(common), differing=diff, earlier_output_matched_golden=early_out)
        for v in variants[1:]:
            key, x = f"{w}_base->{w}_{v}", res.get(f"{w}_{v}", {})
            if not base_check[w]["ok"]:
                pairs[key] = dict(verdict="NOT_INTERPRETED", why="BASELINE_MISMATCH")
                continue
            if x.get("verdict") != "VALID":
                pairs[key] = dict(verdict="EXCLUDED", why=x.get("verdict"))
                continue
            cb = dict(runs=b["runs"], macs=b["comp"]["n_mac"], compile=b["comp"], metrics=b["metrics"])
            cv = dict(runs=x["runs"], macs=x["comp"]["n_mac"], compile=x["comp"], metrics=x["metrics"])
            pa = S4.pair(cb, cv)
            pb = S4.pair(dict(cb, runs={1: cb["runs"][2], 2: cb["runs"][2]}), dict(cv, runs={1: cv["runs"][2], 2: cv["runs"][2]}))
            opposite = (pa["npu_active_variant"] - pa["npu_active_base"]) * (pb["npu_active_variant"] - pb["npu_active_base"]) < 0
            mb, mv = b["metrics"], x["metrics"]
            exact = {n: (mb[f"A_{c}"], mv[f"A_{c}"]) for n, c in (("mac_active", 48), ("mac_dpu_active", 51))
                     if mb[f"A_{c}_range"] == 0 and mv[f"A_{c}_range"] == 0}
            pairs[key] = dict(verdict="UNRESOLVED" if opposite else pa["verdict"], pass_a=pa, directions_opposite=opposite,
                              pass_b_npu_active_change_pct=pb["npu_active_change_pct"], class_5_0=x["c50"]["class"],
                              mac_dpu_exact=exact, same_output_as_base=x.get("same_output_as_base"),
                              sram_used_kib=(b["c50"]["sram_used_kib"], x["c50"]["sram_used_kib"]),
                              fast_size=(b["c50"]["fast_size"], x["c50"]["fast_size"]),
                              arena_size=(b["c50"]["arena_size"], x["c50"]["arena_size"]),
                              kernels=(b["c50"]["kernels"], x["c50"]["kernels"]),
                              vela_macs=(b["comp"]["vela_macs"], x["comp"]["vela_macs"]))
    summary = dict(base_check=base_check, pairs=pairs,
                   configs={c: {k: v for k, v in r.items() if k not in ("runs", "constant")} for c, r in res.items()})
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:6]), indent=1, default=str)[:3000])
