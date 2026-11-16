"""Mutation test of the Stage 6-M mapping, category, metric and verdict rules (host/analysis/stage6m.py). Each mutation
neuters one rule, runs test_stage6m, requires RED, and restores the file by sha256.

    python3 evidence/stage6m/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6m.py"
T = ["test_stage6m"]

MUTATIONS = [
    # §2 mapping and integrity
    ('integrity: vela sha', A, 'checks = dict(vela_sha256=f.get("vela_sha256") == m7.get("vela_sha256"),', 'checks = dict(vela_sha256=True,'),
    ('integrity: cms sha', A, 'cms_sha256=f.get("cms_sha256") == [m7.get("cms_sha256")],', 'cms_sha256=True,'),
    ('integrity: model sha vs meta', A, '== m7.get("model_sha256") == meta.get("model_sha256"),', '== m7.get("model_sha256"),'),
    ('integrity: inventory sha', A, 'inventory=inv_sha16 == {(m7.get("vela_sha256") or "")[:16]})', 'inventory=True)'),
    ('exec: fused excluded', A, 'r["cpu"] == "0" and not S6.fused(r)]', 'r["cpu"] == "0"]'),
    ('exec: cpu excluded', A, 'r["npu_op"] and r["cpu"] == "0" and', 'r["npu_op"] and'),
    ('exec: ambiguous split', A, 'exec_on="NPU" if len(ex) == 1 else', 'exec_on="NPU" if len(ex) >= 1 else'),
    ('exec: single for target', A, '        if len(ex) == 1:\n            r = ex[0]', '        if ex:\n            r = ex[0]'),
    ('fused: same name', A, 'r["name"] == conv["name"] and S6.fused(r)', 'S6.fused(r)'),
    ('fused: LUT flag', A, 'lut_fused=any(x["npu_op"] == "LUT" for x in fz)', 'lut_fused=False'),
    ('streams: single stream', A, 'kf["kernels"][0] if kf and kf.get("n_ethosu_ops") == 1 else None', 'kf["kernels"][0] if kf else None'),
    # §3 computability
    ('comp: model integrity', A, '    if not ok_model:', '    if False:'),
    ('comp: missing kernel', A, 'if not ks or any(k is None for k in ks):', 'if not ks:'),
    ('comp: CONV kind', A, 'if any(k["kind"] != "CONV" or k["kernel_width_m1"]', 'if any(k["kernel_width_m1"]'),
    ('comp: 1x1 kernel', A, ' or k["kernel_width_m1"] != 0 or k["kernel_height_m1"] != 0 for k in ks):', ' for k in ks):'),
    ('comp: IFM depth', A, 'if any(k["ifm_depth_m1"] + 1 != int(r["cin"]) for k in ks):', 'if False:'),
    ('comp: kernel cover', A, 'if sum(h * w * d for h, w, d in c["kernels"]) != oh * ow * cout:', 'if False:'),
    ('comp: TFLite N_MAC', A, 'if n_tfl != oh * ow * cout * c["cin"]:', 'if False:'),
    ('comp: ublock volume', A, 'if math.prod(c["ublock"]) != UBLOCK_VOLUME:', 'if False:'),
    # §3 categories
    ('A: exec_sig', A, 'same = lambda m: m["sig"] == mine["sig"] and', 'same = lambda m: m["sig"][4] == mine["sig"][4] and'),
    ('A: memory', A, 'and m["memory"] == mine["memory"] and', 'and'),
    ('A: stride', A, 'm["stride"] == mine["stride"] \\', 'True \\'),
    ('A: activation', A, 'and m["activation"] == mine["activation"]', 'and True'),
    ('A: no LUT', A, 'if hit and not lut:', 'if hit:'),
    ('A: VALID only', A, 'meas.get("VALID", []) if same(m)), "")', 'meas.get("VALID", []) + meas.get("UNSTABLE", []) if same(m)), "")'),
    ('B: every dim', A, 'return (B if not fails else C)', 'return (B if len(fails) <= 1 else C)'),
    ('B dim: traversal', A, 'traversal=r["traversal"] in dom["traversal"],', 'traversal=True,'),
    ('B dim: kernel', A, 'kernel=r["kernel"] in dom["kernel"],', 'kernel=True,'),
    ('B dim: stride', A, 'stride=r["stride"] in dom["stride"],', 'stride=True,'),
    ('B dim: ublock', A, 'ublock=tuple(c["ublock"]) in dom["ublock"],', 'ublock=True,'),
    ('B dim: ifm depth', A, 'ifm_depth=c["ifm_block_depth"] in dom["ifm_depth"],', 'ifm_depth=True,'),
    ('B dim: cin', A, 'cin=inside(c["cin"], dom["cin"]),', 'cin=True,'),
    ('B dim: ofm h', A, 'ofm_h=inside(oh, dom["hw"]),', 'ofm_h=True,'),
    ('B dim: ofm w', A, 'ofm_w=inside(ow, dom["hw"]),', 'ofm_w=True,'),
    ('B dim: cout', A, 'cout=inside(cout, dom["cout"]),', 'cout=True,'),
    ('B dim: full spatial', A, 'full_spatial=all((h, w) == (oh, ow) for h, w, _ in c["kernels"]),', 'full_spatial=True,'),
    ('B dim: memory', A, 'memory=(r["ifm_memory"], r["ofm_memory"]) in dom["memory"], no_lut=not lut)', 'memory=True, no_lut=not lut)'),
    ('B dim: no LUT', A, 'in dom["memory"], no_lut=not lut)', 'in dom["memory"], no_lut=True)'),
    ('domain: valid shapes only', A, 'if s["cls"] == "PRIMARY_VALID" and s["h1_uc_match"]}', 'if s["cls"] != "INVALID_OR_UNRESOLVED"}'),
    ('domain: exact match only', A, 'if s["cls"] == "PRIMARY_VALID" and s["h1_uc_match"]}', 'if s["cls"] == "PRIMARY_VALID"}'),
    # §4 factors
    ('factor: ideal 1024', A, 'dict(h1uc=h1, ideal=n / 1024,', 'dict(h1uc=h1, ideal=n / 768,'),
    ('factor: U0 128', A, 'u0 = sum(h * w * d for h, w, d in c["kernels"]) / UBLOCK_VOLUME', 'u0 = sum(h * w * d for h, w, d in c["kernels"]) / 64'),
    ('factor: F_cin', A, 'F_cin=cc / (c["cin"] / 8))', 'F_cin=cc / (c["cin"] / 16))'),
    ('factor: no-cin-pad', A, 'f["h1uc_no_cin_pad"] = u * c["cin"] / 8', 'f["h1uc_no_cin_pad"] = u * cc'),
    ('factor: no-cout-pad', A, 'f["h1uc_no_cout_pad"] = u_sp * cc', 'f["h1uc_no_cout_pad"] = u_co * cc'),
    # §5 metrics
    ('metric: NPU MAC ops', A, 'npu_mac = [o for o in mac_ops if o["n_sched"] >= 1]', 'npu_mac = mac_ops'),
    ('metric: eff_meas N_npu', A, 'eff_meas=n_npu / (1024 * mac_meas)', 'eff_meas=n_model / (1024 * mac_meas)'),
    ('metric: share target only', A, 'share_1x1df=sum(o["n_mac_tflite"] for o in tg) / n_model', 'share_1x1df=sum(o["n_mac_tflite"] for o in mac_ops) / n_model'),
    ('metric: set = category', A, 's = [o for o in npu_mac if o["category"] in cats and o["is_target"]]', 's = [o for o in npu_mac if o["is_target"]]'),
    ('metric: coverage over model', A, 'm[f"coverage_{key}"] = n_s / n_model if n_model else 0.0', 'm[f"coverage_{key}"] = n_s / n_npu if n_npu else 0.0'),
    ('metric: eff_set 1024', A, 'm[f"eff_set_{key}"] = n_s / (1024 * h1) if h1 else None', 'm[f"eff_set_{key}"] = n_s / (768 * h1) if h1 else None'),
    ('bound: rest lower bound', A, 'm[f"bound_{key}"] = mac_meas - h1 - sum(o["n_mac_tflite"] for o in rest) / 1024', 'm[f"bound_{key}"] = mac_meas - h1'),
    ('excess: ideal removed', A, 'excess = mac_meas - n_npu / 1024', 'excess = mac_meas'),
    ('excess: loss not h1uc', A, 'm[f"excess_share_{key}"] = sum(o["loss"] for o in s) / excess', 'm[f"excess_share_{key}"] = sum(o["h1uc"] for o in s) / excess'),
    # §7 verdict
    ('V1', A, '    v = dict(V1=all(x["ok"] for x in integ.values()))', '    v = dict(V1=True)'),
    ('V2: bound', A, 'viol = [m for m, x in mm.items() if x["n_ops"][A] + x["n_ops"][B] > 0 and x["bound_AB"] < 0]', 'viol = []'),
    ('V2: only with AB ops', A, 'if x["n_ops"][A] + x["n_ops"][B] > 0 and x["bound_AB"] < 0]', 'if x["bound_AB"] < 0]'),
    ('V3: threshold', A, 'v["V3"] = all(x["coverage_AB"] >= MIN_EVIDENCE_COVERAGE for x in (k, a))', 'v["V3"] = all(x["coverage_AB"] >= 0 for x in (k, a))'),
    ('V3: both models', A, 'v["V3"] = all(x["coverage_AB"]', 'v["V3"] = any(x["coverage_AB"]'),
    ('V4: set direction', A, 'and a["eff_set_AB"] > k["eff_set_AB"]', 'and True'),
    ('V4: measured direction', A, '                   and a["eff_meas"] > k["eff_meas"])', '                   and True)'),
    ('V5: threshold', A, 'v["V5"] = any((x["excess_share_AB"] or 0) >= MIN_EXCESS_SHARE for x in (k, a))', 'v["V5"] = True'),
    ('verdict: all V', A, '    elif all(v.values()):', '    elif v["V1"]:'),
    ('verdict: expanded rule', A, 'if x["coverage_ABC"] > s6_cov.get(m, 0.0)]', 'if True]'),
    # §8 P level
    ('P: mac axis', A, 'if "mac" not in axes.split("+") or x["share_1x1df"] == 0:', 'if x["share_1x1df"] == 0:'),
    ('P: no target ops', A, 'if "mac" not in axes.split("+") or x["share_1x1df"] == 0:', 'if "mac" not in axes.split("+"):'),
    ('P: bound', A, 'if x["bound_AB"] >= 0 and x["coverage_AB"]', 'if x["coverage_AB"]'),
    ('P: coverage', A, 'and x["coverage_AB"] >= MIN_EVIDENCE_COVERAGE and (x["excess_share_AB"]', 'and (x["excess_share_AB"]'),
    ('P: excess', A, 'and (x["excess_share_AB"] or 0) >= MIN_EXCESS_SHARE:\n        return "PARTIAL_MAC_COST"', ':\n        return "PARTIAL_MAC_COST"'),
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
