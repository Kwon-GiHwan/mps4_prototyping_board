#!/usr/bin/env python3
"""Stage 6B-B tables from the judge summary (descriptive; every pass/fail rule is in stage6bb.py).

  stage6bb_analysis.py <stage6bb_summary.json> <workloads dir> <out dir>
writes shapes.csv (per config: status, metrics, analysis variables), fidelity.csv (Vela vs NPU_ACTIVE), coverage.csv
(per model: static / selected / validly measured MAC shares; Stage 6 validated value unchanged)."""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6b as S  # noqa: E402
import stage6bb as B  # noqa: E402

AMB_COV = S.REPO / "results" / "fi101_stage6b" / "revision_a" / "amendment_b" / "amendment_b_coverage.csv"
DIRECT = ("ad_medium_int8", "kws_micronet_m", "mobilenet_v2_1.0_224_INT8", "vww4_128_128_INT8")
VARS = ("group", "kind", "cin", "cout", "ifm_hwc", "ofm_hwc", "ofm_block", "ifm_block", "ofm_ublock", "traversal",
        "cin_mod16", "cout_mod16", "spatial_blocks", "ifm_memory", "ofm_memory", "weight_bytes", "n_mac")
METRICS = ("mac_active", "mac_dpu_active", "npu_active", "npu_active_range", "npu_active_pass_b", "mac_activity",
           "macs_per_mac_active", "eff_1024", "dpu_over_mac", "macs_per_1024_npu_active", "stage4k_nearest",
           "rate_over_640", "rate_over_768", "c16_rate_768", "rate_over_c16_768", "ao_active", "wd_active", "wd_stalled",
           "reserved_53", "reserved_55")


def shapes(summary: dict, man: dict) -> list[dict]:
    out = []
    for c in B.ORDER:
        r, m = summary["results"][c], man[c]
        row = dict(config=c, boot=m["boot"], status=r["status"], reasons=" | ".join(r.get("reasons", [])),
                   internal_conv=r.get("internal_conv"), output_board_verified=r.get("output_board_verified"))
        row.update({k: m.get(k) for k in VARS})
        met = r.get("metrics") or {}
        row.update({k: met.get(k) for k in METRICS})
        row.update({f"passB_{k}": v for k, v in (met.get("pass_b") or {}).items()})
        out.append(row)
    return out


def fidelity(summary: dict, man: dict) -> list[dict]:
    rows = []
    for c in B.ORDER[1:]:
        f, m, r = summary["fidelity"][c], man[c], summary["results"][c]
        met = r.get("metrics") or {}
        rows.append(dict(config=c, group=m["group"], status=f["status"], why=f.get("why", ""), vela_cycles=m["vela"]["cycles_total"],
                         npu_active=f.get("npu_active"), error_pct=f.get("error_pct"), abs_error_pct=f.get("abs_error_pct"),
                         macs_per_mac_active=met.get("macs_per_mac_active"), mac_activity=met.get("mac_activity"),
                         non_mac_share=(1 - met["mac_activity"]) if met.get("mac_activity") is not None else None,
                         vela_conv_op_cycles=m["vela"]["conv_op_cycles"], vela_conv_mac_cycles=m["vela"]["conv_mac_cycles"],
                         cin=m["cin"], cout=m["cout"], ofm_block=m["ofm_block"], spatial_blocks=m["spatial_blocks"]))
    return rows


def coverage(summary: dict, man: dict) -> list[dict]:
    """Validly Measured Shape Coverage: MAC of the groups whose representative was VALID on the board, per model."""
    rows, dt = S.load(), json.loads(S.DTYPES.read_text())
    tot, tg = S.model_macs(rows), S.targets(rows, dt)
    gmap = {g["group"]: g for g in S.groups(tg)}
    valid = {man[c]["group"] for c in B.ORDER[1:] if summary["results"][c]["status"] == "VALID"}
    with open(AMB_COV) as f:
        amb = {r["model"]: r for r in csv.DictReader(f)}
    out = []
    for mdl in S.MODELS:
        mac = sum(int(r["mac_count"]) for g in valid for r in gmap[g]["members"] if r["model"] == mdl)
        a = amb[mdl]
        t = tot.get(mdl, 0)
        out.append(dict(model=mdl, direct_scope=mdl in DIRECT, n_mac_model=t,
                        static_reproduction_coverage=float(a["static_reproduction_coverage"]),
                        selected_measurement_coverage=float(a["selected_measurement_coverage"]),
                        n_mac_validly_measured=mac, validly_measured_shape_coverage=mac / t if t else 0.0,
                        stage6_validated_hw_coverage=a["validated_hw_coverage"],
                        model_level_explanation_coverage="NOT_QUANTIFIED (Stage 6 INSUFFICIENT_EVIDENCE unchanged)"))
    return out


def main(argv: list) -> None:
    summary = json.loads(pathlib.Path(argv[0]).read_text())
    man = json.loads((pathlib.Path(argv[1]) / B.MANIFEST).read_text())
    o = pathlib.Path(argv[2]); o.mkdir(parents=True, exist_ok=True)
    S.write_csv(o / "shapes.csv", shapes(summary, man))
    S.write_csv(o / "fidelity.csv", fidelity(summary, man))
    S.write_csv(o / "coverage.csv", coverage(summary, man))


if __name__ == "__main__":
    main(sys.argv[1:])
