"""Mutation test of the Stage 6 rules (evidence/stage6/rules.md). Each mutation neuters one rule in
host/analysis/stage6.py, runs test_stage6, requires RED, and restores the file by sha256.

    python3 evidence/stage6/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6.py"
T = ["test_stage6"]

MUTATIONS = [
    ("T0 exact match", A, 'if (cin, cout, r["ofm_block"]) == (c, co, blk):', 'if (cin, cout) == (c, co):'),
    ("T1 range", A, 'if lo <= cin <= hi and len(rates) == 1:', 'if len(rates) == 1:'),
    ("T1 constant rate", A, 'if lo <= cin <= hi and len(rates) == 1:', 'if lo <= cin <= hi:'),
    ("MAC: zero-MAC rows U", A, 'if r["npu_op"] not in MAC_OPS or i(r["mac_count"]) == 0:', 'if r["npu_op"] not in MAC_OPS:'),
    ("AO: INT8 check", A, 'if r["npu_op"] == "Conv2D" and int8_out(r, dt):', 'if r["npu_op"] == "Conv2D":'),
    ("AO: fused rows", A, 'if not r["npu_op"] or fused(r) or r["cpu"] == "1":', 'if not r["npu_op"] or r["cpu"] == "1":'),
    ("AO: chaining undecided", A, 'and int8_out(r, dt) and r["ofm_format"] == "NHWC":', 'and int8_out(r, dt):'),
    ("AO: c16 rounding", A, "return o[0] * o[1] * math.ceil(o[2] / 16) * 16 if len(o) == 3 else 0", "return o[0] * o[1] * o[2] if len(o) == 3 else 0"),
    ("WD T0 key", A, 'return "T0" if t == "T0" and (family(r), i(r["cin"]), i(r["cout"]), r["ofm_block"]) == WD_T0_KEY else "PROXY"',
     'return "T0" if t == "T0" else "PROXY"'),
    ("compare: coverage gate", A, "if cov < COVER_COMPARE:", "if False:"),
    ("compare: tolerance", A, 'status="CONSISTENT" if abs(err) <= TOL else "NOT_CONSISTENT"', 'status="CONSISTENT"'),
    ("compare: baseline", A, 'if measured is None:\n        return dict(status="BASELINE_NOT_COMPARABLE", coverage=cov)', 'if False:\n        return dict(status="BASELINE_NOT_COMPARABLE", coverage=cov)'),
    ("verdict: baseline first", A, 'if not baseline_ok:\n        return "BASELINE_NOT_COMPARABLE"', 'if False:\n        return "BASELINE_NOT_COMPARABLE"'),
    ("verdict: min coverage", A, "c = min(covs)", "c = max(covs)"),
    ("verdict: attribution", A, "if c < COVER_PARTIAL or needs_attribution:", "if c < COVER_PARTIAL:"),
    ("verdict: supported needs all consistent", A, 'return "SUPPORTED_WITHIN_SCOPE" if all(x == "CONSISTENT" for x in comps) else "NOT_SUPPORTED"',
     'return "SUPPORTED_WITHIN_SCOPE"'),
    ("calibrated = T0 + T1_INTERP", A, 'mac_cal = [o for o in ops if o["mac_tier"] in ("T0", "T1_INTERP")]', 'mac_cal = [o for o in ops if o["mac_tier"] in ("T0",)]'),
    ("baseline: all valid", A, 'out["checks"] = dict(all_valid=all(r["run_valid"] == "True" for r in rows),', 'out["checks"] = dict(all_valid=True,'),
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
