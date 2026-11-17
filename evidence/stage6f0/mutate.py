"""Mutation test of the Stage 6F-0 judge (host/analysis/stage6f0.py). Each mutation neuters one rule, runs test_stage6f0,
requires RED, and restores the file by sha256.

    python3 evidence/stage6f0/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6f0.py"
T = ["test_stage6f0"]

MUTATIONS = [
    ("pred levels", A, 'PRED_6D = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED")', 'PRED_6D = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED", "EXTRAPOLATED")'),
    ("pred class", A, 'PRED_6D = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED")', 'PRED_6D = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED")'),
    ("tol exact", A, "TOL_EXACT, TOL_RULE = 0.01, 0.05", "TOL_EXACT, TOL_RULE = 0.05, 0.05"),
    ("tol rule", A, "TOL_EXACT, TOL_RULE = 0.01, 0.05", "TOL_EXACT, TOL_RULE = 0.01, 0.051"),
    ("tol all", A, 'tol = TOL_EXACT if all(r["level"] == "CONFIGURATION_MATCHED" for r in rows) else TOL_RULE', 'tol = TOL_EXACT if any(r["level"] == "CONFIGURATION_MATCHED" for r in rows) else TOL_RULE'),
    ("agree le", A, '"PREDICTION_AGREES" if abs(measured - p) <= tol * p', '"PREDICTION_AGREES" if abs(measured - p) < tol * p'),
    ("agree sign", A, '"PREDICTION_AGREES" if abs(measured - p) <= tol * p', '"PREDICTION_AGREES" if measured - p <= tol * p'),
    ("untestable", A, "    if any(v is None for v in vals):", "    if False:"),
    ("ext lo", A, '"EXTRAPOLATION_CONSISTENT" if LO * measured <= p <= HI * measured', '"EXTRAPOLATION_CONSISTENT" if LO * measured < p <= HI * measured'),
    ("ext hi", A, '"EXTRAPOLATION_CONSISTENT" if LO * measured <= p <= HI * measured', '"EXTRAPOLATION_CONSISTENT" if LO * measured <= p'),
    ("ext p first", A, 'vals = [fnum(r["p"]) if fnum(r["p"]) is not None else fnum(r["p_ext"]) for r in rows]', 'vals = [fnum(r["p_ext"]) for r in rows]'),
    ("group default", A, 'if op in ops), "G_R")', 'if op in ops), None)'),
    ("group ad gv", A, '"ad_medium_int8": {"G_0": (0,), "G_V": (2, 4, 6, 8)}', '"ad_medium_int8": {"G_0": (0,), "G_V": (2, 4, 6)}'),
    ("lv agrees", A, '    if st == "PREDICTION_AGREES":\n        return "DIRECT_IN_MODEL", g, st', '    if False:\n        return "DIRECT_IN_MODEL", g, st'),
    ("lv isolated", A, 'return "DIRECT_ISOLATED", g, st', 'return "CONFIGURATION", g, st'),
    ("lv class", A, 'return "CLASS", g, st', 'return "EXTRAPOLATED", g, st'),
    ("lv refuted alone", A, 'alone = gi is not None and gi["ops"] == [int(r["op"])]', 'alone = gi is not None'),
    ("lv refuted st", A, 'return ("REFUTED" if alone and st == "EXTRAPOLATION_REFUTED" else "EXTRAPOLATED")', 'return ("REFUTED" if alone else "EXTRAPOLATED")'),
    ("lv unsup", A, '    return "UNSUPPORTED_OR_UNSTABLE", g, st\n\n\ndef levels', '    return "CLASS", g, st\n\n\ndef levels'),
    ("cov covered", A, 'COVERED = ("DIRECT_IN_MODEL", "DIRECT_ISOLATED", "CONFIGURATION", "CLASS")', 'COVERED = ("DIRECT_IN_MODEL", "DIRECT_ISOLATED", "CONFIGURATION")'),
    ("cov ext6f", A, 'P_ext_6d=p + ext + ref, P_ext_6f=p + ext,', 'P_ext_6d=p + ext + ref, P_ext_6f=p + ext + ref,'),
    ("cov ext6d", A, 'P_ext_6d=p + ext + ref, P_ext_6f=p + ext,', 'P_ext_6d=p + ext, P_ext_6f=p + ext,'),
    ("cov v", A, 'if gi["status"] == "PREDICTION_AGREES") / m', 'if gi["status"] != "NOT_TESTABLE") / m'),
    ("cov d exact", A, "if groups and partition_exact else 0.0", "if groups else 0.0"),
    ("cov dep", A, 'extrap_dependence=sh["EXTRAPOLATED"] + sh["REFUTED"]', 'extrap_dependence=sh["EXTRAPOLATED"]'),
    ("c6f d", A, '    if cv["D"] == 1.0:', '    if cv["D"] >= 0.99:'),
    ("c6f v", A, "V_FULL = 0.90", "V_FULL = 0.89"),
    ("c6f prosp", A, 'if cv["V"] >= V_FULL and prospective == "QUANTITATIVELY_EXPLAINED":', 'if cv["V"] >= V_FULL:'),
    ("rt serial", A, "    if serial_partition_holds:\n", "    if serial_partition_holds is not None:\n"),
    ("rt bound", A, "    if mac and npu:\n", "    if npu:\n"),
    ("fid groups", A, "    if has_groups:\n        return \"GROUP_DIRECTION_MEASURED\"", "    if False:\n        return \"GROUP_DIRECTION_MEASURED\""),
    ("fid min", A, "if over + under >= D.CANCEL_MIN:", "if over + under > D.CANCEL_MIN:"),
    ("vela insuff", A, "if any(abs(npu - b * total) <= rng for b in (VELA_LO, VELA_HI)):", "if any(abs(npu - b * total) < rng for b in (VELA_LO, VELA_HI)):"),
    ("vela insuff hi", A, "if any(abs(npu - b * total) <= rng for b in (VELA_LO, VELA_HI)):", "if any(abs(npu - b * total) <= rng for b in (VELA_LO,)):"),
    # r == 0.9 exactly is unreachable (|npu - 0.9 total| = 0 <= range -> INSUFFICIENT first), so "<" vs "<=" is an
    # equivalent mutation; the reachable one moves the threshold.
    ("vela over", A, 'return "OVER" if r < VELA_LO else', 'return "OVER" if r < 0.95 else'),
    ("vela under", A, '"UNDER" if r > VELA_HI else "AGREE"', '"UNDER" if r > 1.2 else "AGREE"'),
    ("terms mem", A, 'mem = [r for r in rows if float(r["vela_op_cycles"]) > float(r["vela_npu_cycles"] or 0)]', 'mem = [r for r in rows if float(r["vela_op_cycles"]) >= float(r["vela_npu_cycles"] or 0)]'),
    ("terms npu", A, 'npu = sum(float(r["vela_npu_cycles"]) for r in rows if r["vela_npu_cycles"])', 'npu = tot'),
    ("ser ratio S", A, '"(S-orig)/S": (gs - o) / gs,', '"(S-orig)/S": (gs - o) / o,'),
    ("ser ratio d", A, '"(serial-orig)/orig": (s - o) / o,', '"(serial-orig)/orig": (s - o) / s,'),
    ("ser inv", A, 'schedule_invariant_mac=ev["mac"]["delta"] == 0', 'schedule_invariant_mac=True'),
    ("rec d", A, 'elig = c["d"] and c["e"] and c["f"] and boots <= MAX_BOOTS and not excluded', 'elig = c["e"] and c["f"] and boots <= MAX_BOOTS and not excluded'),
    ("rec e", A, 'elig = c["d"] and c["e"] and c["f"] and boots <= MAX_BOOTS and not excluded', 'elig = c["d"] and c["f"] and boots <= MAX_BOOTS and not excluded'),
    ("rec f", A, 'elig = c["d"] and c["e"] and c["f"] and boots <= MAX_BOOTS and not excluded', 'elig = c["d"] and c["e"] and boots <= MAX_BOOTS and not excluded'),
    ("rec excl", A, 'and boots <= MAX_BOOTS and not excluded', 'and boots <= MAX_BOOTS'),
    ("rec budget", A, "MAX_BOOTS = 12", "MAX_BOOTS = 11"),
    ("rec tie boots", A, 'key=lambda t: (-t["score"], t["boots"], table.index(t))', 'key=lambda t: (-t["score"], table.index(t))'),
    ("rec order", A, 'key=lambda t: (-t["score"], t["boots"], table.index(t))', 'key=lambda t: (-t["score"], t["boots"], -table.index(t))'),
    ("rec lat g", A, '("X_LAT", "YYYYYYYNYY", 12, False)', '("X_LAT", "YYYYYYNNYY", 12, False)'),
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
