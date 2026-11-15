"""Mutation test of the Stage 6B-R formulas and verdict rule (host/analysis/stage6br.py). Each mutation neuters one
rule, runs test_stage6br, requires RED, and restores the file by sha256.

    python3 results/fi101_stage6b/stage6br/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6br.py"
T = ["test_stage6br"]

MUTATIONS = [
    ('ublock spatial ceil', A, 'f = (lambda a, b: math.ceil(a / b)) if pad_spatial else', 'f = (lambda a, b: a / b) if pad_spatial else'),
    ('ublock depth ceil', A, '* math.ceil(d / ub[2]) for h, w, d in kernels)', '* d / ub[2] for h, w, d in kernels)'),
    ('chunk remainder', A, '+ ([cin % depth] if cin % depth else [])', ''),
    ('chunk min 32', A, 'return max(32 if min32 else 0, up(x, 16)) / 8', 'return max(16 if min32 else 0, up(x, 16)) / 8'),
    ('chunk ceil 16', A, 'return max(32 if min32 else 0, up(x, 16)) / 8', 'return max(32 if min32 else 0, up(x, 8)) / 8'),
    ('per-kernel slices', A, 'ks = c["kernels"] if per_kernel else', 'ks = [[c["ofm"][0], c["ofm"][1], c["cout"]]] if per_kernel else'),
    ('dpu piecewise', A, 'return up(x, 8) / 8 if x <= 8 else up(x, 16) / 8', 'return up(x, 16) / 8'),
    ('D-R ratio', A, 'return up(c["cin"], 8) / up(c["cin"], 32)', 'return up(c["cin"], 16) / up(c["cin"], 32)'),
    ('H1-G cout 16', A, 'up(c["cin"], 32) * up(c["cout"], 16) / 1024', 'up(c["cin"], 32) * up(c["cout"], 32) / 1024'),
    ('verdict exact', A, 'miss = [c["case"] for c in official if pred(c) != c[key]]', 'miss = [c["case"] for c in official if abs(pred(c) - c[key]) > 2]'),
    ('verdict official only', A, 'official = [c for c in cases if c["status"] == "VALID"]', 'official = list(cases)'),
    ('verdict closest competitor', A, 'elif competitors is not None and split <= 1:', 'elif competitors is not None and split < 1:'),
    ('ranks ties', A, 'return [sum(i + 1 for i, a in enumerate(order) if a == x) / order.count(x) for x in v]', 'return [order.index(x) + 1 for x in v]'),
    ('spearman constant', A, 'if not sa or not sb:\n        return None', 'if False:\n        return None'),
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
