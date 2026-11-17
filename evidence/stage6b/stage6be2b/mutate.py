"""Mutation test of the Stage 6B-E2B sensitivity, validity and verdict rules
(host/analysis/stage6be2b.py). Each mutation neuters one rule, runs test_stage6be2b, requires RED, and restores the file by
sha256.

    python3 evidence/stage6b/stage6be2b/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2b.py"
T = ["test_stage6be2b"]

MUTATIONS = [
    ('MODEL_TOL', A, 'MODEL_TOL = 0.15 ', 'MODEL_TOL = 0.2 '),
    ('NOISE_FLOOR', A, 'NOISE_FLOOR = 0.01 ', 'NOISE_FLOOR = 0.02 '),
    ('RESOLVE', A, 'RESOLVE = 0.5 ', 'RESOLVE = 0.6 '),
    ('BEAT_TOL', A, 'BEAT_TOL = 0.01 ', 'BEAT_TOL = 0.02 '),
    ('tol: floor', A, 'return max(NOISE_FLOOR * b500, r500 + r1000)', 'return r500 + r1000'),
    ('tol: ranges', A, 'return max(NOISE_FLOOR * b500, r500 + r1000)', 'return NOISE_FLOOR * b500'),
    ('primary: resolve', A, '    if tol > RESOLVE * abs(d_vela):\n        return "INSUFFICIENT"', '    if False:\n        return "INSUFFICIENT"'),
    ('primary: tol in band', A, 'MODEL_TOL * abs(d_vela) + tol else "DISCREPANT"', 'MODEL_TOL * abs(d_vela) else "DISCREPANT"'),
    ('primary: model term', A, '<= MODEL_TOL * abs(d_vela) + tol else', '<= tol else'),
    ('secondary: tol', A, 'MODEL_TOL * abs(r_vela - 1) + tol / b500 else', 'MODEL_TOL * abs(r_vela - 1) else'),
    ('secondary: minus one', A, 'MODEL_TOL * abs(r_vela - 1) + tol', 'MODEL_TOL * abs(r_vela) + tol'),
    ('history: ranges', A, 'max(NOISE_FLOOR * old, new_range + old_range)', 'NOISE_FLOOR * old'),
    ('aux: mac', A, 'cls = "MEMORY_SERVICE_RESPONSE" if same_mac and same_dpu', 'cls = "MEMORY_SERVICE_RESPONSE" if same_dpu'),
    ('aux: dpu', A, 'if same_mac and same_dpu and same_beats', 'if same_mac and same_beats'),
    ('aux: beats', A, 'same_dpu and same_beats and d_board > tol', 'same_dpu and d_board > tol'),
    ('aux: npu', A, 'same_beats and d_board > tol else', 'same_beats else'),
    ('workload: unstable', A, 'cls = "INSUFFICIENT" if all(s in ("VALID", "UNSTABLE") for s in st) else "NOT_EVALUABLE"', 'cls = "NOT_EVALUABLE"'),
    ('workload: slope', A, 'slope_board=d_b / 500,', 'slope_board=d_b / 1000,'),
    ('verdict: gate', A, 'if gate.get("verdict") != "PASS" or any(', 'if any('),
    ('verdict: fail states', A, 'FAIL_STATES = ("CONFIG_MISMATCH", "UNMEASURED", "INVALID_OUTPUT", "INVALID_PMU")', 'FAIL_STATES = ("CONFIG_MISMATCH", "UNMEASURED")'),
    ('verdict: discrepancy first', A, '    if any(w["primary"] == "DISCREPANT" for w in wl.values()):\n        return "SENSITIVITY_DISCREPANCY_OBSERVED"\n', ''),
    ('verdict: all consistent', A, 'if any(w["primary"] != "CONSISTENT" for w in wl.values()):', 'if all(w["primary"] != "CONSISTENT" for w in wl.values()):'),
    ('env: workload', A, '    if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:\n        bad.append("workload sha256")', '    pass'),
    ('env: image', A, '        if {r[k] for r in rows} != {v}:\n            bad.append(f"image {k}")', '        pass'),
    ('env: fpga', A, '        bad.append("fpga image")', '        pass'),
    ('env: boot', A, '        bad.append("boot index")', '        pass'),
    ('env: condition', A, '        bad.append("condition")', '        pass'),
    ('env: macs', A, '        bad.append("NPU MAC count")', '        pass'),
    ('env: rlatency', A, '        bad.append("TA EXT RLATENCY read-back")', '        pass'),
    ('env: identity', A, 'bad += [f"identity {k}" for k, v in ident["checks"].items() if not v and', 'bad += [f"identity {k}" for k, v in ident["checks"].items() if False and'),
    ('stop states', A, 'STOP = ("CONFIG_MISMATCH", "UNMEASURED")', 'STOP = ("UNMEASURED",)'),
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
