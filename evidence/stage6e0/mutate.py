"""Mutation test of the Stage 6E-0 judge (host/analysis/stage6e0.py). Each mutation neuters one rule, runs test_stage6e0,
requires RED, and restores the file by sha256.

    python3 evidence/stage6e0/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6e0.py"
T = ["test_stage6e0"]

MUTATIONS = [
    ("hi", A, "HI, LO, COV_ALL = 1.05, 0.95, 0.95", "HI, LO, COV_ALL = 1.06, 0.95, 0.95"),
    ("lo", A, "HI, LO, COV_ALL = 1.05, 0.95, 0.95", "HI, LO, COV_ALL = 1.05, 0.94, 0.95"),
    ("cov", A, "HI, LO, COV_ALL = 1.05, 0.95, 0.95", "HI, LO, COV_ALL = 1.05, 0.95, 0.94"),
    ("ca quant", A, '    if v6d == "QUANTITATIVELY_EXPLAINED":\n        return "EXPLAINED_WITH_EXISTING_DATA"', '    if False:\n        return "EXPLAINED_WITH_EXISTING_DATA"'),
    ("ca partial6d", A, 'if v6d == "PARTIALLY_EXPLAINED" or (', 'if ('),
    ("ca pv", A, "(p_v <= HI * m and p_all", "(p_all"),
    ("ca pall", A, "and p_all >= LO * m and share_pred", "and share_pred"),
    ("ca share", A, "and share_pred >= COV_ALL)", ")"),
    ("ps pext", A, 'if r["level"] in PRED_LEVELS or fnum(r["p_ext"]) is not None)', 'if r["level"] in PRED_LEVELS)'),
    ("ps cpu", A, 'mac = [r for r in rows if r["level"] not in ("CPU_OR_SPLIT", "AO_ELEMENTWISE")]', 'mac = rows'),
    ("ps denom", A, 'n = sum(int(r["n_mac"]) for r in rows)', 'n = sum(int(r["n_mac"]) for r in mac)'),
    ("pred levels", A, 'PRED_LEVELS = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED")', 'PRED_LEVELS = ("EXACT_VALIDATED", "CONFIGURATION_MATCHED", "CLASS_SUPPORTED", "EXTRAPOLATED")'),
    ("sel eligible", A, "eligible = [c for c in cands if all(c[1])]", "eligible = [c for c in cands if sum(c[1]) >= 9]"),
    ("sel min", A, "pick = min(eligible, key=lambda c: c[3])", "pick = eligible[-1]"),
    ("sel fallback", A, "pick = max(cands, key=lambda c: sum(c[1]))", "pick = cands[-1]"),
    ("x3 c8", A, '("X3_SERIAL_MASK", (Y, Y, Y, Y, Y, Y, Y, Y, Y, Y), Y, 10)', '("X3_SERIAL_MASK", (Y, Y, Y, Y, Y, Y, Y, N, Y, Y), Y, 10)'),
    ("x3 vela", A, '("X3_SERIAL_MASK", (Y, Y, Y, Y, Y, Y, Y, Y, Y, Y), Y, 10)', '("X3_SERIAL_MASK", (Y, Y, Y, Y, Y, Y, Y, Y, Y, Y), N, 10)'),
    ("x1 c1", A, '("X1_G_DF_EXT", (N, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 9)', '("X1_G_DF_EXT", (Y, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 9)'),
    ("x1 c8", A, '("X1_G_DF_EXT", (N, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 9)', '("X1_G_DF_EXT", (N, Y, Y, Y, Y, Y, Y, Y, Y, Y), N, 9)'),
    ("x2 c8", A, '("X2_PREFIX_STOP", (Y, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 10)', '("X2_PREFIX_STOP", (Y, Y, Y, Y, Y, Y, Y, Y, Y, Y), N, 10)'),
    ("x4 c4", A, '("X4_QREAD_FINE", (Y, Y, N, N, Y, N, N, Y, Y, Y), N, 4)', '("X4_QREAD_FINE", (Y, Y, N, Y, Y, N, N, Y, Y, Y), N, 4)'),
    ("x5 c9", A, '("X5_AD_REST_ISOLATED", (N, Y, Y, Y, Y, Y, Y, N, N, Y), N, 4)', '("X5_AD_REST_ISOLATED", (N, Y, Y, Y, Y, Y, Y, N, Y, Y), N, 4)'),
    ("instr ok", A, '("QREAD trace", "qread_pilot, qread_op_pilot", False)', '("QREAD trace", "qread_pilot, qread_op_pilot", True)'),
    ("impl precheck", A, '("PMU_MASK / KERNEL_WAIT(0) on driver runner", "NEEDS_BOARD_PRECHECK")', '("PMU_MASK / KERNEL_WAIT(0) on driver runner", "EXISTS")'),
    ("impl cop1", A, '("COP1 replace + tflite reserialize", "NEW_BOUNDED")', '("COP1 replace + tflite reserialize", "EXISTS")'),
    ("precheck flag", A, 'PRECHECK_IN_FIRST_BOOT = {"X3_SERIAL_MASK": True}', 'PRECHECK_IN_FIRST_BOOT = {"X3_SERIAL_MASK": False}'),
    ("ne c4", A, "    if not any(c[1][3] for c in cands):", "    if not any(c[1][2] for c in cands):"),
    ("ne eligible", A, '    if (sel["eligible"] and "UNKNOWN_FEASIBILITY"', '    if ("UNKNOWN_FEASIBILITY"'),
    ("ne unknown", A, 'and "UNKNOWN_FEASIBILITY" not in states', 'and True'),
    ("ne precheck", A, 'and ("NEEDS_BOARD_PRECHECK" not in states or pre.get(sel["name"], False))', 'and True'),
    ("ec instr", A, "    if any(ok for _, _, ok in instruments):", "    if False:"),
    ("ec c3", A, 'if c["c3"] and c["c4"] and c["c7"]:', 'if c["c4"] and c["c7"]:'),
    ("ec c4", A, 'if c["c3"] and c["c4"] and c["c7"]:', 'if c["c3"] and c["c7"]:'),
    ("ec c7", A, 'if c["c3"] and c["c4"] and c["c7"]:', 'if c["c3"] and c["c4"]:'),
    ("vf c6", A, 'if sel["criteria"]["c6"] and sel["vela_condition_match"]:', 'if sel["vela_condition_match"]:'),
    ("vf match", A, 'if sel["criteria"]["c6"] and sel["vela_condition_match"]:', 'if sel["criteria"]["c6"]:'),
    ("vf classified", A, "    if all_classified:\n        return \"DISCREPANCY_CHARACTERIZED\"", "    if True:\n        return \"DISCREPANCY_CHARACTERIZED\""),
    ("vt npu", A, 'rows = [o for o in ops if o["exec_on"] == "NPU" and', 'rows = [o for o in ops if'),
    ("vt gt", A, 'if float(o["vela_op_cycles"]) > (fnum(o["vela_mac_cycles"]) or 0.0))', 'if float(o["vela_op_cycles"]) >= (fnum(o["vela_mac_cycles"]) or 0.0))'),
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
