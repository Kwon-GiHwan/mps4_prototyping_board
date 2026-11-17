"""Mutation test of the Stage 6C judge (host/analysis/stage6c.py). Each mutation neuters one rule, runs test_stage6c,
requires RED, and restores the file by sha256.

    python3 evidence/stage6c/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6c.py"
T = ["test_stage6c"]

MUTATIONS = [
    ("passC list", A, "PASS_C = [35, 131, 142, 387, 640, 642, 656, 658]", "PASS_C = [35, 131, 142, 387, 640, 642, 656, 659]"),
    ("n runs", A, "N_RUNS = 15", "N_RUNS = 10"),
    ("tol", A, "TOL = 0.01", "TOL = 0.02"),
    ("vela band", A, "VELA_BAND = 0.10", "VELA_BAND = 0.20"),
    ("f4 rate", A, "F4_RATE = (384, 1024)", "F4_RATE = (300, 1024)"),
    ("meas partial", A, "    if status in (\"UNSTABLE\", \"INVALID_PMU\"):\n        return \"PARTIAL_VALID\"", "    if False:\n        return \"PARTIAL_VALID\""),
    ("meas valid", A, "    if status == \"VALID\":\n        return \"VALID\"\n    if status in", "    if status in"),
    ("cp valid", A, "    if not both_valid or not mac_rep or mac_ctl is None:", "    if not mac_rep or mac_ctl is None:"),
    ("cp tol", A, "return \"PREDICTION_SUPPORTED\" if abs(mac_ctl - mac_rep) <= TOL * mac_rep else", "return \"PREDICTION_SUPPORTED\" if mac_ctl - mac_rep <= TOL * mac_rep else"),
    ("f4 valid", A, "    if not valid or not mac_active:\n        return \"INSUFFICIENT_EVIDENCE\"\n    return \"PREDICTION_SUPPORTED\" if F4_RATE", "    if not mac_active:\n        return \"INSUFFICIENT_EVIDENCE\"\n    return \"PREDICTION_SUPPORTED\" if F4_RATE"),
    ("f4 upper", A, "F4_RATE[0] <= n_mac / mac_active <= F4_RATE[1]", "F4_RATE[0] <= n_mac / mac_active"),
    ("pp valid", A, "    if not both_valid or npu_rep is None or npu_ctl is None:", "    if npu_rep is None or npu_ctl is None:"),
    ("pp tol", A, "d, t = npu_ctl - npu_rep, tol(npu_rep, [r_rep, r_ctl])", "d, t = npu_ctl - npu_rep, tol(npu_rep, [r_rep])"),
    ("pp abs", A, "verdict=\"CONTROLLED_EFFECT_OBSERVED\" if abs(d) > t else", "verdict=\"CONTROLLED_EFFECT_OBSERVED\" if d > t else"),
    ("pp strict", A, "verdict=\"CONTROLLED_EFFECT_OBSERVED\" if abs(d) > t else", "verdict=\"CONTROLLED_EFFECT_OBSERVED\" if abs(d) >= t else"),
    ("ps", A, "return \"ASSOCIATION_ONLY\" if valid else \"MECHANISM_UNRESOLVED\"", "return \"ASSOCIATION_ONLY\""),
    ("vc valid", A, "    if not valid or not npu or not vela:", "    if not npu or not vela:"),
    ("vc over", A, "    if r < 1 - VELA_BAND:\n        return \"OVERESTIMATION\"", "    if r <= 1 - VELA_BAND:\n        return \"OVERESTIMATION\""),
    ("vc under", A, "    if r > 1 + VELA_BAND:\n        return \"UNDERESTIMATION\"", "    if r >= 1 + VELA_BAND:\n        return \"UNDERESTIMATION\""),
    ("h12 refute", A, "    if \"UNDERESTIMATION\" in c:\n        return \"PREDICTION_REFUTED\"", "    if False:\n        return \"PREDICTION_REFUTED\""),
    ("h12 all", A, "return \"PREDICTION_SUPPORTED\" if all(x == \"OVERESTIMATION\" for x in c) else", "return \"PREDICTION_SUPPORTED\" if any(x == \"OVERESTIMATION\" for x in c) else"),
    ("h12 drop insufficient", A, "c = [x for x in classes if x != \"INSUFFICIENT_EVIDENCE\"]", "c = list(classes)"),
    ("h3 refute", A, "    if any(r < 1 - VELA_BAND for r in ratios):", "    if all(r < 1 - VELA_BAND for r in ratios):"),
    ("h3 support", A, "return \"PREDICTION_SUPPORTED\" if all(r > 1.0 for r in ratios) else", "return \"PREDICTION_SUPPORTED\" if all(r >= 1.0 for r in ratios) else"),
    ("hp support", A, "    if min(a) > max(b):", "    if max(a) > max(b):"),
    ("hp refute", A, "return \"PREDICTION_REFUTED\" if max(a) < min(b) else", "return \"PREDICTION_REFUTED\" if min(a) < min(b) else"),
    ("valid gate", A, "if gate.get(\"verdict\") != \"PASS\" or any(", "if any("),
    ("valid stop", A, "or any(r[\"status\"] in STOP for r in res.values()):", ":"),
    ("pmu layout", A, "if len(raw) != N_RUNS or sorted(", "if False and sorted("),
    ("pmu counters", A, "if any(r[\"ev\"].get(c) is None for c in codes) or sorted(r[\"ev\"]) != sorted(codes):", "if False:"),
    ("pmu sets", A, "SETS = {1: S4.PASS_A, 2: S4.PASS_B, 3: PASS_C}", "SETS = {1: S4.PASS_A, 2: S4.PASS_B}"),
    ("stab c", A, "if a is None or x is None or abs(x - a) > max(BB.AB_REL * a, ra + rx):", "if a is None or x is None:"),
    ("cr env", A, "    if env:\n        return dict(base, status=\"CONFIG_MISMATCH\", reasons=env)", "    if False:\n        return dict(base, status=\"CONFIG_MISMATCH\", reasons=env)"),
    ("cr pmu", A, "    if p:\n        return dict(base, status=\"INVALID_PMU\", reasons=p)", "    if False:\n        return dict(base, status=\"INVALID_PMU\", reasons=p)"),
    ("cr stable", A, "return dict(res, status=\"UNSTABLE\", reasons=st) if st else", "return"),
    ("gate rep", A, "return dict(verdict=\"PASS\" if rep[\"ok\"] and same else \"FAIL\"", "return dict(verdict=\"PASS\""),
    ("traffic map", A, "ext1_rd_beats=c.get(\"C_658\"))", "ext1_rd_beats=c.get(\"C_656\"))"),
    ("vela ratio", A, "ctrl = dict(compute=cv, pipeline=pp, vela_ratio=vb / va,", "ctrl = dict(compute=cv, pipeline=pp, vela_ratio=va / vb,"),
    ("order", A, "(\"s6c_f4_rep\", 475), (\"s6c_f5_rep\", 476)]", "(\"s6c_f5_rep\", 475), (\"s6c_f4_rep\", 476)]"),
    ("nmac f5", A, "\"s6c_f5_rep\": 2744000}", "\"s6c_f5_rep\": 1372000}"),
    ("f5 compute", A, "shapes[\"s6c_f5_rep\"].update(compute=\"INSUFFICIENT_EVIDENCE\",", "shapes[\"s6c_f5_rep\"].update(compute=\"PREDICTION_SUPPORTED\","),
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
