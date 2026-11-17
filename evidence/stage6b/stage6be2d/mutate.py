"""Mutation test of the Stage 6B-E2D effect, fidelity and validity rules
(host/analysis/stage6be2d.py). Each mutation neuters one rule, runs test_stage6be2d, requires RED, and restores the file by
sha256.

    python3 evidence/stage6b/stage6be2d/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2d.py"
T = ["test_stage6be2d"]

MUTATIONS = [
    ('H1UC', A, 'H1UC = 20736', 'H1UC = 20737'),
    ('MODEL_TOL', A, 'MODEL_TOL = 0.15', 'MODEL_TOL = 0.2'),
    ('NOISE_FLOOR', A, 'NOISE_FLOOR = 0.01', 'NOISE_FLOOR = 0.02'),
    ('PE_VELA', A, 'PE_VELA = {500: 47258, 1000: 117480}', 'PE_VELA = {500: 47258, 1000: 117481}'),
    ('INTERACTION_VELA', A, 'INTERACTION_VELA = 70222', 'INTERACTION_VELA = 70223'),
    ('order', A, '("W1-P1", 1000, 445), ("W1-P0", 1000, 446)', '("W1-P0", 1000, 445), ("W1-P1", 1000, 446)'),
    ('tol floor', A, 'return max(NOISE_FLOOR * base, sum(ranges))', 'return sum(ranges)'),
    ('tol ranges', A, 'return max(NOISE_FLOOR * base, sum(ranges))', 'return NOISE_FLOOR * base'),
    ('pe usable', A, '    if not usable:\n        return "NOT_IDENTIFIABLE"\n    big', '    big'),
    ('pe strict', A, 'big = [abs(pe[L]) > tols[L] for L in (500, 1000)]', 'big = [abs(pe[L]) >= tols[L] for L in (500, 1000)]'),
    ('pe sign', A, 'if all(big) and same_sign else', 'if all(big) else'),
    ('pe all', A, 'if all(big) and same_sign else', 'if any(big) and same_sign else'),
    ('within model', A, 'return abs(board - vela) <= MODEL_TOL * abs(vela) + t', 'return abs(board - vela) <= t'),
    ('within tol', A, 'return abs(board - vela) <= MODEL_TOL * abs(vela) + t', 'return abs(board - vela) <= MODEL_TOL * abs(vela)'),
    ('fid empty', A, '    if not ok:\n        return "NOT_COMPARABLE"', '    if False:\n        return "NOT_COMPARABLE"'),
    ('fid discrepancy', A, '    if not all(ok.values()):\n        return "PLACEMENT_RESPONSE_DISCREPANCY"', '    if False:\n        return "PLACEMENT_RESPONSE_DISCREPANCY"'),
    ('fid partial', A, 'return "PLACEMENT_RESPONSE_CONSISTENT" if len(ok) == 2 else "FIDELITY_PARTIAL"', 'return "PLACEMENT_RESPONSE_CONSISTENT"'),
    ('fid evaluable', A, 'for L in (500, 1000) if evaluable.get(L)}', 'for L in (500, 1000)}'),
    ('validity gate', A, 'if gate.get("verdict") != "PASS" or any(r["status"] in STOP', 'if any(r["status"] in STOP'),
    ('validity stop', A, 'STOP = ("CONFIG_MISMATCH", "UNMEASURED")', 'STOP = ("CONFIG_MISMATCH",)'),
    ('validity mac', A, 'if all(r["status"] == "VALID" for r in res.values()) and all(mac_ok.values()):', 'if all(r["status"] == "VALID" for r in res.values()):'),
    ('validity all', A, 'if all(r["status"] == "VALID" for r in res.values()) and all(', 'if any(r["status"] == "VALID" for r in res.values()) and all('),
    ('eff pe sign', A, 'pe = {L: b(p0, L) - b(p1, L) for L in (500, 1000)}\n    t_pe', 'pe = {L: b(p1, L) - b(p0, L) for L in (500, 1000)}\n    t_pe'),
    ('eff tol base', A, 't_pe = {L: tol(b(p1, L), [r(p0, L), r(p1, L)]) for L in (500, 1000)}\n    le', 't_pe = {L: tol(b(p0, L), [r(p0, L), r(p1, L)]) for L in (500, 1000)}\n    le'),
    ('eff le', A, 'le = {c: b(c, 1000) - b(c, 500) for c in (p0, p1)}', 'le = {c: b(c, 1000) - b(c, 500) + 1 for c in (p0, p1)}'),
    ('eff tol le', A, 't_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in (p0, p1)}', 't_le = {c: tol(b(c, 1000), [r(c, 500), r(c, 1000)]) for c in (p0, p1)}'),
    ('eff interaction', A, 'inter = le[p0] - le[p1]', 'inter = le[p1] - le[p0]'),
    ('eff tol interaction', A, 't_i = tol(b(p1, 500), [r(c, L) for c in (p0, p1) for L in (500, 1000)])', 't_i = tol(b(p1, 500), [r(c, 500) for c in (p0, p1)])'),
    ('eff usable', A, '    if not usable:\n        return dict(usable=False)', '    if False:\n        return dict(usable=False)'),
    ('key', A, 'return "REF" if cell == "REF" else f"{cell}-L{lat}"', 'return f"{cell}-L{lat}"'),
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
