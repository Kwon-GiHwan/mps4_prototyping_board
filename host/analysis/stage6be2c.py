#!/usr/bin/env python3
"""Stage 6B-E2C (evidence/stage6b/stage6be2c/contract.md): which wrapper-only / placement-only comparisons of the same
G12 Conv can be controlled, from the compile facts (host/container/stage6be2c_configs.py). Board-free.

  python3 stage6be2c.py run <facts.json> <out dir>
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage6br as BR  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
RECORD_VELA = dict(A0="64c350eb9813a9cf4b8366b5e454fe3c395801e574b92890185966d2b9bddb04",
                   A2="95cf070b8da226167e984817f0a093a63b3a246f8d7da26d267ac52eba1b620b")   # Revision A s6b_g12.ra.json
W1P0_ORDER = ("W1-P0-c0", "W1-P0-c16384", "W1-P0-c65536")
CONTROLLED = ("PLACEMENT_ONLY", "WRAPPER_ONLY")
E2B_SUMMARY = REPO / "results/fi101_stage6b/stage6be2b/stage6be2b_summary.json"


# ---- pure rules ------------------------------------------------------------------------------------------------------
def conv_kernels(f: dict) -> list[dict]:
    return [k for k in f["kernels"] if k["kind"] == "CONV"]


def conv_memory(f: dict) -> tuple | None:
    ids = [r["id"] for r in f["perf"] if r["operator"] == "Conv2D"]
    rows = [r for r in f["perf_debug"] if r["id"] in ids]
    return (rows[0]["ifm_memory"], rows[0]["ofm_memory"]) if len(rows) == 1 else None


def diff_regs(a: dict, b: dict) -> dict:
    import cms_full
    return cms_full.diff(a, b)


def compare(fa: dict, fb: dict) -> dict:
    ka, kb = conv_kernels(fa), conv_kernels(fb)
    out = dict(n_conv=(len(ka), len(kb)), same_n_conv=len(ka) == len(kb), diff={}, weights_equal=False,
               ops=([r["operator"] for r in fa["perf"]], [r["operator"] for r in fb["perf"]]))
    if out["same_n_conv"] and ka:
        d = {}
        for x, y in zip(ka, kb):
            for cat, names in diff_regs(x["regs"], y["regs"]).items():
                d.setdefault(cat, sorted(set(d.get(cat, [])) | set(names)))
        out["diff"] = d
        sa = [s for s, k in zip(fa["streams"], fa["kernels"]) if k["kind"] == "CONV"]
        sb = [s for s, k in zip(fb["streams"], fb["kernels"]) if k["kind"] == "CONV"]
        key = lambda s: {w: (v["length"], v["const_sha256"]) for w, v in s.items()}
        out["weights_equal"] = all(key(x) == key(y) and all(v["const_sha256"] for v in x.values()) for x, y in zip(sa, sb))
    out["same_ops"] = out["ops"][0] == out["ops"][1]
    return out


def placement_class(c: dict, mem_a, mem_b, want=(("Dram", "Dram"), ("Sram", "Sram"))) -> str:
    if mem_a is None or mem_b is None:
        return "UNAVAILABLE"
    if not (c["same_n_conv"] and c["weights_equal"] and c["same_ops"]) or set(c["diff"]) - {"ADDRESS"}:
        return "NOT_CONTROLLED"
    return "PLACEMENT_ONLY" if (mem_a, mem_b) == want else "NOT_CONTROLLED"


def wrapper_class(c: dict, mem_a, mem_b) -> str:
    if mem_a is None or mem_b is None:
        return "UNAVAILABLE"
    if not (c["same_n_conv"] and c["weights_equal"]) or "COMPUTE" in c["diff"] or mem_a != mem_b:
        return "NOT_CONTROLLED"
    return "WRAPPER_PLUS_LAYOUT" if "LAYOUT" in c["diff"] else "WRAPPER_ONLY"


def estimator_only(l500: dict, l1000: dict) -> bool:
    keys = ("cms_sha256", "const_sha256", "arena_size", "fast_size", "inputs", "outputs")
    return bool(l500.get("ok") and l1000.get("ok")) and all(l500[k] == l1000[k] for k in keys)


def first_dram(cands: dict) -> str | None:
    for c in W1P0_ORDER:
        f = cands.get(c, {}).get("L500", {})
        if f.get("ok") and conv_memory(f) == ("Dram", "Dram"):
            return c
    return None


def h1uc(f: dict) -> float | None:
    """H1-UC for the single Conv: kernels from the OFM registers, ublock and IFM block depth from perf_debug_main."""
    conv_ids = [r["id"] for r in f["perf"] if r["operator"] == "Conv2D"]
    m = [r for r in f["main"] if r["id"] in conv_ids]
    if len(m) != 1:
        return None
    ub = [int(m[0][f"ofm_ublock_{x}"]) for x in "hwc"]
    ks = [[k["regs"]["NPU_SET_OFM_HEIGHT_M1"] + 1, k["regs"]["NPU_SET_OFM_WIDTH_M1"] + 1, k["regs"]["NPU_SET_OFM_DEPTH_M1"] + 1]
          for k in conv_kernels(f)]
    cin = conv_kernels(f)[0]["regs"]["NPU_SET_IFM_DEPTH_M1"] + 1
    return BR.h1_uc(dict(kernels=ks, ublock=ub, cin=cin, ifm_block_depth=int(m[0]["ifm_block_c"])))


def verdict(invalid: bool, comps: dict) -> str:
    if invalid:
        return "INVALID"
    if any(c["cls"] in CONTROLLED and c["numeric_verified"] for c in comps.values()):
        return "READY_FOR_BOARD_REVIEW"
    if any(c["cls"] not in ("UNAVAILABLE", "NOT_CONTROLLED") for c in comps.values()):
        return "PARTIAL_IDENTIFIABILITY"
    return "NOT_IDENTIFIABLE"


# ---- run --------------------------------------------------------------------------------------------------------------
def e2b_recheck() -> dict:
    s = json.loads(E2B_SUMMARY.read_text())
    out = {}
    for w, (k5, k10) in (("G12", ("G12-L500", "G12-L1000")), ("CONV", ("CONV-L500", "CONV-L1000"))):
        b5, b10 = s["results"][k5]["metrics"]["npu_active"], s["results"][k10]["metrics"]["npu_active"]
        x = s["workloads"][w]
        out[w] = dict(d_board=b10 - b5, r_board=b10 / b5, d_vela=x["v1000"] - x["v500"], r_vela=x["v1000"] / x["v500"],
                      equals_summary=(b10 - b5 == x["d_board"] and math.isclose(b10 / b5, x["r_board"])))
    return out


def vela_row(f5: dict, f10: dict) -> dict:
    s = lambda f, k: int(f["summary"][k])
    r = dict(estimator_only=estimator_only(f5, f10))
    for lat, f in (("500", f5), ("1000", f10)):
        for k in ("cycles_npu", "cycles_sram_access", "cycles_dram_access", "cycles_total"):
            r[f"{k}_{lat}"] = s(f, k)
        for k in ("sram_feature_map_read_bytes", "sram_feature_map_write_bytes", "dram_feature_map_read_bytes", "dram_feature_map_write_bytes",
                  "dram_weight_read_bytes", "sram_weight_read_bytes"):
            r[f"{k}_{lat}"] = s(f, k)
    r["d_vela"] = r["cycles_total_1000"] - r["cycles_total_500"]
    r["r_vela"] = r["cycles_total_1000"] / r["cycles_total_500"]
    r["per_op_500"] = [(o["operator"], o["op_cycles"], o["npu_cycles"], o["Sram_ac"], o["Dram_ac"]) for o in f5["perf"]]
    return r


def run(facts_p: str, out: str) -> dict:
    F = json.loads(pathlib.Path(facts_p).read_text())
    C = F["candidates"]
    base = {c: C[c]["L500"] for c in C}
    invalid = base["W0-P0"].get("vela_sha256") != RECORD_VELA["A0"] or base["W1-P1"].get("vela_sha256") != RECORD_VELA["A2"]
    e2b = e2b_recheck()
    invalid = invalid or not all(v["equals_summary"] for v in e2b.values())
    w1p0 = first_dram(C)
    cells = {"W0-P0": "W0-P0", "W0-P1": "W0-P0", "W1-P1": "W1-P1", "W1-P0": w1p0}    # W0-P1 runs the W0-P0 blob
    mem = {"W0-P0": conv_memory(base["W0-P0"]), "W0-P1": ("Sram", "Sram") if base["W0-P0"].get("ok") else None,
           "W1-P1": conv_memory(base["W1-P1"]), "W1-P0": conv_memory(base[w1p0]) if w1p0 else None}
    est = compare(base["W0-P0"], base["W0-P1-est"]) if base["W0-P1-est"].get("ok") else None
    est_ok = bool(est and est["same_n_conv"] and est["weights_equal"] and not set(est["diff"]) - {"ADDRESS"}
                  and conv_memory(base["W0-P1-est"]) == ("Sram", "Sram"))
    vela_src = {"W0-P0": "W0-P0", "W1-P1": "W1-P1", "W1-P0": w1p0, "W0-P1": "W0-P1-est" if est_ok else None}
    vela = {cell: vela_row(C[src]["L500"], C[src]["L1000"]) if src else None for cell, src in vela_src.items()}
    h = {cell: h1uc(base[src]) if src and base[src].get("ok") else None for cell, src in cells.items()}
    blob = lambda cell: base[cells[cell]] if cells[cell] else None
    comps = {}
    for name, a, b, kind in (("B_W0 placement (W0-P0 vs W0-P1)", "W0-P0", "W0-P1", "P"),
                             ("B_W1 placement (W1-P0 vs W1-P1)", "W1-P0", "W1-P1", "P"),
                             ("A_P0 wrapper (W0-P0 vs W1-P0)", "W0-P0", "W1-P0", "W"),
                             ("A_P1 wrapper (W0-P1 vs W1-P1)", "W0-P1", "W1-P1", "W")):
        if not cells[a] or not cells[b]:
            comps[name] = dict(cls="UNAVAILABLE", numeric_verified=False); continue
        c = compare(blob(a), blob(b))
        cls = placement_class(c, mem[a], mem[b]) if kind == "P" else wrapper_class(c, mem[a], mem[b])
        nv = bool(vela[a] and vela[b] and vela[a]["estimator_only"] and vela[b]["estimator_only"]
                  and h[a] is not None and h[a] == h[b] and F["cpu"]["a0_out_equals_a2_conv_out"] and F["cpu"]["a2_out_equals_ref"])
        comps[name] = dict(cls=cls, numeric_verified=nv, diff=c["diff"], same_ops=c["same_ops"], weights_equal=c["weights_equal"],
                           memory=(mem[a], mem[b]), same_blob=cells[a] == cells[b],
                           vela=None if not (vela[a] and vela[b]) else dict(d_vela=(vela[a]["d_vela"], vela[b]["d_vela"]),
                                                                            r_vela=(vela[a]["r_vela"], vela[b]["r_vela"])))
    interaction = all(comps[n]["cls"] in CONTROLLED for n in comps)
    summary = dict(contract="evidence/stage6b/stage6be2c/contract.md", label="STATIC_DESIGN (no board)", invalid=invalid,
                   e2b_recheck=e2b, w1p0_selected=w1p0, compile_ok={c: (C[c]["L500"].get("ok"), C[c]["L1000"].get("ok")) for c in C},
                   conv_memory={c: conv_memory(base[c]) if base[c].get("ok") else None for c in C},
                   w0p1_estimator=dict(source="W0-P1-est (Shared_Sram)", usable=est_ok, diff=est["diff"] if est else None),
                   vela=vela, h1uc=h, cpu=F["cpu"], comparisons=comps, interaction_identifiable=interaction,
                   verdict=verdict(invalid, comps))
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2c_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[2], sys.argv[3]), indent=1, default=str)[:8000])
