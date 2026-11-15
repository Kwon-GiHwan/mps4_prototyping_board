"""Mutation test of the Stage 6B-E1 selection and verdict rules (host/analysis/stage6be1.py). Each mutation neuters one
rule, runs test_stage6be1, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6be1/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be1.py"
T = ["test_stage6be1"]

MUTATIONS = [
    ('elig: one ethos-u op', A, 'if f.get("error") or f.get("n_ethosu_ops") != 1:', 'if f.get("error"):'),
    ('elig: cpu', A, 'if any(r["cpu"] == "1" for r in rows):', 'if False:'),
    ('elig: npu rows', A, 'if npu != ["Conv2D", "Relu6"] or', 'if False or'),
    ('elig: DepthFirst', A, 'if c["traversal"] != "DepthFirst":', 'if False:'),
    ('elig: 1x1', A, '["kernel"] != "1x1":', '["kernel"] == "never":'),
    ('elig: duplicates', A, 'if (h, w, cin, cout) in existing:', 'if False:'),
    ('elig: split required', A, 'if n_split(c) == 0:', 'if False:'),
    ('existing: Stage 4 family', A, 's = {(24, 24, c, 96) for c in (15, 16, 32, 40, 48, 56, 64, 128)}', 's = set()'),
    ('cat A: min32 split', A, 'if COMPETITORS[NO_MIN32](c) != R.h1_uc(c):', 'if True:'),
    ('cat B: spatial split', A, 'if COMPETITORS[NO_SPATIAL](c) != R.h1_uc(c):', 'if True:'),
    ('cat C: ublock 16', A, 'if c["ublock"][2] == 16:', 'if c["ublock"][2] != 32:'),
    ('cat D: split kernels', A, 'and COMPETITORS[WHOLE_COUT](c) != R.h1_uc(c):', ':'),
    ('rank: n_split first', A, 'return (-n_split(c), 0 if', 'return (n_split(c), 0 if'),
    ('select: category missing', A, 'status = "OK" if not missing and len(taken) == N_SELECT else "NEEDS_REVISION"', 'status = "OK"'),
    ('select: distinct Cin/Cout', A, 'if any((c["cin"], c["cout"]) == (x["cin"], x["cout"]) for x in cases if x["case"] in taken):', 'if False:'),
    ('select: packs', A, 'pick = next((c for c in order if cat in categories(c) and c["case"] not in taken and packs(c["case"])), None)', 'pick = next((c for c in order if cat in categories(c) and c["case"] not in taken), None)'),
    ('classify: VALID only primary', A, 'if r["status"] == "VALID":\n        return "PRIMARY_VALID"', 'if r["status"] in ("VALID", "UNSTABLE"):\n        return "PRIMARY_VALID"'),
    ('classify: MAC stable', A, 'if r["status"] == "UNSTABLE" and len(set(r.get("mac_active_runs") or [None, 0])) == 1 and', 'if r["status"] == "UNSTABLE" and'),
    ('classify: DPU stable', A, 'len(set(r.get("mac_dpu_active_runs") or [None, 0])) == 1:', 'True:'),
    ('shape: exact match', A, 'h1_uc_match=mac == p,', 'h1_uc_match=abs(mac - p) <= 50,'),
    ('verdict: contradiction', A, 'if gate.get("verdict") == "PASS" and any(not s["h1_uc_match"] for s in primary):', 'if False:'),
    ('verdict: six primary', A, 'and len(primary) == N_SELECT and', 'and len(primary) >= 1 and'),
    ('verdict: gate', A, 'if gate.get("verdict") == "PASS" and len(primary) == N_SELECT', 'if len(primary) == N_SELECT'),
    ('dpu: split only', A, 'split = [s for s in shapes if s["cls"] == "PRIMARY_VALID" and s["dpu_pw_vs_u16_split"]]', 'split = [s for s in shapes if s["cls"] == "PRIMARY_VALID"]'),
    ('dpu: primary only', A, 'split = [s for s in shapes if s["cls"] == "PRIMARY_VALID" and s["dpu_pw_vs_u16_split"]]', 'split = [s for s in shapes if s["cls"] != "INVALID_OR_UNRESOLVED" and s["dpu_pw_vs_u16_split"]]'),
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
