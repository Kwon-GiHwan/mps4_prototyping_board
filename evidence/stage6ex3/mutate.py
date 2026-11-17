"""Mutation test of the Stage 6E-X3 judge and stream edits (host/analysis/stage6ex3.py, stage6ex3_workloads.py,
host/lib/cms.py serial part, host/lib/tflite_cop1.py). Each mutation neuters one rule, runs the tests,
requires RED, and restores the file by sha256.

    python3 evidence/stage6ex3/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6ex3.py"
W = "host/analysis/stage6ex3_workloads.py"
C = "host/lib/cms.py"
F = "host/lib/tflite_cop1.py"
T = ["test_stage6ex3", "test_cms_serial"]

MUTATIONS = [
    ("npu tol", A, "NPU_TOL = 0.01", "NPU_TOL = 0.02"),
    ("ev tol", A, "EV_TOL = 0.01 ", "EV_TOL = 0.02 "),
    ("unstable rel", A, "UNSTABLE_REL = 0.05", "UNSTABLE_REL = 0.10"),
    ("m2 max", A, "M2_MAX = 0.95", "M2_MAX = 1.0"),
    ("f5", A, "F5_MAC, F5_TOL = 26090.0, 0.01", "F5_MAC, F5_TOL = 26090.0, 0.02"),
    ("h1uc tol", A, "H1UC_KWS, H1UC_AD, H1UC_TOL = 11700.0, 60480.0, 0.05", "H1UC_KWS, H1UC_AD, H1UC_TOL = 11700.0, 60480.0, 0.10"),
    ("vela band", A, "VELA_LO, VELA_HI = 0.9, 1.1", "VELA_LO, VELA_HI = 0.8, 1.1"),
    ("schema", A, "SCHEMA, RECORD_FIELDS, LOG2_MACS, EXT_RLATENCY = 5, 92, 10, 500", "SCHEMA, RECORD_FIELDS, LOG2_MACS, EXT_RLATENCY = 5, 92, 10, 1000"),
    ("id workload", A, '    if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:\n        bad.append("workload sha256")\n', ""),
    ("id image", A, '        if {r[f] for r in rows} != {v}:\n            bad.append(f"image {f}")\n', '        pass\n'),
    ("id boot", A, '    if {r["host_boot_index"] for r in rows} != {str(BOOT[k])}:\n        bad.append("boot index")\n', ""),
    ("id condition", A, '    if {r["condition"] for r in rows} != {"wfe"}:\n        bad.append("condition")\n', ""),
    ("id ta", A, '    if not ta or ta != {x: v for x, v in caps_ref.items() if x.startswith("ta_")}:', '    if not ta:'),
    ("id mac", A, '    if (caps.get("npu_config", 0) & 0xF) != LOG2_MACS:\n        bad.append("NPU MAC count")\n', ""),
    ("id caps schema", A, '    if caps.get("schema") != SCHEMA or caps.get("record_fields") != RECORD_FIELDS:', '    if False:'),
    ("id rec schema", A, 'checks = dict(schema=all(r.get("schema") == SCHEMA for r in recs),', 'checks = dict(schema=True,'),
    ("id placement", A, '                  placement=all(r.get("placement") == 0 for r in recs),\n', ""),
    ("id model len", A, '                  model_len=bool(recs) and all(r.get("model_len") == model_len for r in recs),\n', ""),
    ("id flags", A, '                  pmu_flags=all(r.get("pmu_flags") == m["pmu_flags"] for r in recs),\n', ""),
    ("id mask_en", A, '                  mask_en=all(bool(r.get("pmcr_after_arm", 0) & MASK_EN) == bool(m["pmu_flags"]) for r in recs),\n', ""),
    ("id irq", A, '                  irq=all(r.get("irq_count") == 1 for r in recs))', '                  irq=True)'),
    ("out golden", A, '    if not all(x["record"].get("ofm_mismatch") == 0 and x["valid_flags"] & record_v2.OUTPUT_MATCH for x in d["raw"]):', '    if not all(x["record"].get("ofm_mismatch") == 0 for x in d["raw"]):'),
    ("out mismatch", A, '    if not all(x["record"].get("ofm_mismatch") == 0 and x["valid_flags"] & record_v2.OUTPUT_MATCH for x in d["raw"]):', '    if not all(x["valid_flags"] & record_v2.OUTPUT_MATCH for x in d["raw"]):'),
    ("out crc single", A, '    if len(crcs) != 1 or None in crcs:', '    if None in crcs:'),
    ("out crc b0", A, '    elif crc_ref is not None and crcs != {crc_ref}:', '    elif False:'),
    ("out b0 ref", A, '    ob = output_bad(d, None if m["cond"] == "B0" else b0_crc(root, m["model"]))', '    ob = output_bad(d, None)'),
    ("pmu layout", A, '        bad.append("RUN layout (3 passes x (1 warm-up + 4))")', '        pass'),
    ("pmu validity", A, '        if not ok:\n            bad.append(f"set {x[\'set_id\']} RUN invalid: {\' \'.join(why)}")', '        if False:\n            bad.append("")'),
    ("unstable mac", A, '        if len(vals) != 1:\n            bad.append(f"event {c} differs between RUNs")', '        if False:\n            bad.append("")'),
    ("unstable ab", A, '        if a is None or x is None or abs(x - a) > max(UNSTABLE_REL * a, ra + rx):', '        if a is None or x is None:'),
    ("unstable range", A, '    if a and ra > UNSTABLE_REL * a:', '    if False:'),
    ("measured reps", A, 'def stats(raw: list, measured_from: int = 2) -> dict:', 'def stats(raw: list, measured_from: int = 1) -> dict:'),
    ("m7 warmup", A, '        if x["rep"] <= 2:\n            continue\n', ''),
    ("m7 pass a", A, '    ref[35] = pa[35]  ', '    ref[35] = ref[35]  '),
    ("g1 valid", A, '    if b0["status"] != "VALID":\n        return dict(verdict="FAIL", why=f"B0 {b0[\'status\']}", reasons=b0["reasons"])', '    if b0["status"] not in ("VALID", "UNSTABLE", "INVALID_OUTPUT"):\n        return dict(verdict="FAIL", why="", reasons=[])'),
    ("g1 npu", A, '    if npu is None or rn is None or abs(npu - rn) > tol:', '    if npu is None or rn is None:'),
    ("g1 npu tol range", A, '    tol = max(NPU_TOL * rn, rm + rb) if rn is not None and rb is not None else None', '    tol = NPU_TOL * rn if rn is not None and rb is not None else None'),
    ("g1 npu tol b0 range", A, '    tol = max(NPU_TOL * rn, rm + rb) if rn is not None and rb is not None else None', '    tol = max(NPU_TOL * rn, rm) if rn is not None and rb is not None else None'),
    ("g1 cap", A, '    if rb is None or rb > ref["npu_range_cap"]:', '    if rb is None:'),
    ("g1 cap value", A, '    cap = max(max(v) - min(v) for (s, c), v in ev.items() if c == 35)       # largest m7 per-set NPU_ACTIVE range', '    cap = 10 ** 9'),
    ("g1 det value", A, '                if v is None or v != mv or rv != 0 or rmv != 0:', '                if v is None or rv != 0 or rmv != 0:'),
    ("g1 det b0 range", A, '                if v is None or v != mv or rv != 0 or rmv != 0:', '                if v is None or v != mv or rmv != 0:'),
    ("g1 det m7 range", A, '                if v is None or v != mv or rv != 0 or rmv != 0:', '                if v is None or v != mv or rv != 0:'),
    ("g1 det list", A, 'DETERMINISTIC = (48, 51, 128, 130, 132, 135, 384, 386, 391, 640, 642, 656, 658)', 'DETERMINISTIC = (48, 51, 128, 130, 132, 135, 384, 386, 391, 640, 656, 658)'),
    ("g1 events", A, '            elif v is None or abs(v - mv) > max(EV_TOL * mv, rmv + rv):', '            elif v is None:'),
    ("repro", A, '             ("REPRODUCED" if gates[m]["g1"]["verdict"] == "PASS" else "NOT_REPRODUCED") for m in models}', '             "REPRODUCED" for m in models}'),
    ("mask m3", A, '        mask = "FUNCTIONAL" if kg["m2"]["holds"] and all(x["holds"] for x in kg["m3"].values()) else "NOT_FUNCTIONAL"', '        mask = "FUNCTIONAL" if kg["m2"]["holds"] else "NOT_FUNCTIONAL"'),
    ("mask m2", A, '        mask = "FUNCTIONAL" if kg["m2"]["holds"] and all(x["holds"] for x in kg["m3"].values()) else "NOT_FUNCTIONAL"', '        mask = "FUNCTIONAL" if all(x["holds"] for x in kg["m3"].values()) else "NOT_FUNCTIONAL"'),
    ("part tol", A, '    tol = max(EV_TOL * w, rw + sum(r for _, r in vs))', '    tol = 2 * w'),
    ("m2 zero", A, '        out[c] = w is not None and v is not None and 0 < v < M2_MAX * w', '        out[c] = w is not None and v is not None and v < M2_MAX * w'),
    ("gm m2", A, '    ok = r2["holds"] and all(x["holds"] for x in r3.values()) and r4', '    ok = all(x["holds"] for x in r3.values()) and r4'),
    ("gm m3", A, '    ok = r2["holds"] and all(x["holds"] for x in r3.values()) and r4', '    ok = r2["holds"] and r4'),
    ("gm m4", A, '    ok = r2["holds"] and all(x["holds"] for x in r3.values()) and r4', '    ok = r2["holds"] and all(x["holds"] for x in r3.values())'),
    ("gm mac code", A, '    r3 = {c: partition(res, model, c) for c in (35, 48)}', '    r3 = {c: partition(res, model, c) for c in (35,)}'),
    ("hs", A, '    return "SUPPORTED" if abs(b - a) <= EV_TOL * a else "REFUTED"', '    return "SUPPORTED"'),
    ("ha2", A, '    if gv > (1 + H1UC_TOL) * H1UC_AD:', '    if gv > H1UC_AD:'),
    ("ha neither", A, '    elif gv < (1 - H1UC_TOL) * H1UC_AD:', '    elif gv < H1UC_AD:'),
    ("ho tol", A, '    tol = max(EV_TOL * a, ra + rb)', '    tol = EV_TOL * a'),
    ("ho valid", A, '    if b0["status"] != "VALID" or b1["status"] != "VALID":', '    if False:'),
    ("att gv", A, '    if kws_gm and hk["G_V"] == "SUPPORTED" and ad_ok:', '    if kws_gm and ad_ok:'),
    ("att ad", A, '    if kws_gm and hk["G_V"] == "SUPPORTED" and ad_ok:', '    if kws_gm and hk["G_V"] == "SUPPORTED":'),
    ("compute", A, '        "RESIDUAL_REDUCED" if ha["verdict"] == "H_A1_SUPPORTED" else "RESIDUAL_UNCHANGED")', '        "RESIDUAL_REDUCED")'),
    ("serial all", A, '        "NO_SIGNIFICANT_EFFECT" if all(v == "NO_SIGNIFICANT_EFFECT" for v in vs) else "INSUFFICIENT_EVIDENCE")', '        "NO_SIGNIFICANT_EFFECT")'),
    ("vf closer", A, '        vf = "GROUP_FIDELITY_IMPROVED" if closer and agree else "GROUP_DISCREPANCY_REMAINS"', '        vf = "GROUP_FIDELITY_IMPROVED" if agree else "GROUP_DISCREPANCY_REMAINS"'),
    ("vf agree", A, '        vf = "GROUP_FIDELITY_IMPROVED" if closer and agree else "GROUP_DISCREPANCY_REMAINS"', '        vf = "GROUP_FIDELITY_IMPROVED" if closer else "GROUP_DISCREPANCY_REMAINS"'),
    ("meas gates", A, '    if not gates_ok or any(s in STOP for s in sts):', '    if any(s in STOP for s in sts):'),
    ("gates gs", A, '    gates_ok = all(g["g1"]["verdict"] == "PASS" for g in gates.values()) and all(gs.values()) and kws_gm', '    gates_ok = all(g["g1"]["verdict"] == "PASS" for g in gates.values()) and kws_gm'),
    ("gates g1", A, '    gates_ok = all(g["g1"]["verdict"] == "PASS" for g in gates.values()) and all(gs.values()) and kws_gm', '    gates_ok = all(gs.values()) and kws_gm'),
    ("cli serial", A, '        return 1 if r["status"] in STOP or (not argv[6].endswith("B0") and r["status"] != "VALID") else 0', '        return 1 if r["status"] in STOP else 0'),
    ("vela rows", A, '        rows = [r for r in csv.DictReader(f) if float(r["Op Cycles"]) > 0]', '        rows = list(csv.DictReader(f))'),
    ("tfl groups", A, '    src = {int(r["index"]): int(r["source_id"]) - 1 for r in rows}', '    src = {int(r["index"]): int(r["source_id"]) for r in rows}'),
    ("kw word", C, '    return OP_KERNEL_WAIT | n << 16', '    return OP_KERNEL_WAIT | 1 << 16'),
    ("serial last", C, '    at[b[n]] = [kernel_wait(0), pmu_mask(0)]', '    at[b[n]] = [kernel_wait(0), pmu_mask(1)]'),
    ("serial order", C, '    at = {b[i]: [kernel_wait(0), pmu_mask(bits[i])] for i in range(n)}', '    at = {b[i]: [pmu_mask(bits[i]), kernel_wait(0)] for i in range(n)}'),
    ("serial no wait", C, '    at = {b[i]: [kernel_wait(0), pmu_mask(bits[i])] for i in range(n)}', '    at = {b[i]: [pmu_mask(bits[i])] for i in range(n)}'),
    ("serial check", C, '    if len(bits) != n or any(x not in (0, 1) for x in bits):', '    if len(bits) != n:'),
    ("cop1 len", F, '            out.append(DA_COMMAND_STREAM | ((m >> 16) & 0xFF) << 8 | (m & 0xFFFF) << 16)', '            out.append(w)'),
    ("cop1 align", F, 'DATA_ALIGN = 16', 'DATA_ALIGN = 4'),
    ("cop1 redirect", F, '    struct.pack_into("<I", out, field, vec - field)', '    pass'),
    ("wl flags", W, '                flags = drwl.PMU_MASK_EN', '                flags = 0'),
    ("wl groups", W, '    gv = [int(r["index"]) for r in rows if lv.get(int(r["source_id"]) - 1) == "EXACT_VALIDATED"]', '    gv = [int(r["index"]) for r in rows if lv.get(int(r["source_id"])) == "EXACT_VALIDATED"]'),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def green():
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return all(subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                              capture_output=True).returncode == 0 for m in T)


def main():
    if not green():
        print("baseline not GREEN"); return 1
    lines, bad = [], 0
    for mid, rel, old, new in MUTATIONS:
        p = REPO / rel
        before, text = sha(p), p.read_text()
        if text.count(old) != 1:
            lines.append(f"NOT_APPLIED  {mid}  ({rel}: pattern found {text.count(old)}x)"); bad += 1; print(lines[-1]); continue
        p.write_text(text.replace(old, new))
        try:
            g = green()
        finally:
            p.write_text(text)
        restored = sha(p) == before
        bad += g or not restored
        lines.append(f"{'SURVIVED' if g else 'KILLED':12s} {mid}  ({rel}; restored by sha256: {restored})")
        print(lines[-1], flush=True)
    g = green()
    lines.append(f"after restore: {'GREEN' if g else 'RED'}")
    (pathlib.Path(__file__).parent / "mutation.txt").write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if bad or not g else 0


if __name__ == "__main__":
    sys.exit(main())
