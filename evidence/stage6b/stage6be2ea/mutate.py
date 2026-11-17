"""Mutation test of the Stage 6B-E2E-A audit and design rules
(host/analysis/stage6be2ea.py). Each mutation neuters one rule, runs test_stage6be2ea, requires RED, and restores the file by
sha256.

    python3 evidence/stage6b/stage6be2ea/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2ea.py"
T = ["test_stage6be2ea"]

MUTATIONS = [
    ('cls: not identity', A, '    if not uses_identity:\n        return "UNAFFECTED"', '    if False:\n        return "UNAFFECTED"'),
    ('cls: field', A, '    if not has_field:\n        return "UNRESOLVED"', '    if False:\n        return "UNRESOLVED"'),
    ('cls: zero only', A, '    if placements <= {0}:', '    if 0 in placements:'),
    ('cls: remeasured', A, '    if not s.get("remeasured"):', '    if False:'),
    ('cls: rejudged', A, '    if not s.get("rejudged"):', '    if False:'),
    ('overall: order', A, '    if "REMEASUREMENT_REQUIRED" in classes:\n        return "HISTORICAL_REMEASUREMENT_REQUIRED"\n', ''),
    ('overall: rejudge', A, '    if "REJUDGE_REQUIRED" in classes:\n        return "HISTORICAL_REJUDGE_REQUIRED"\n', ''),
    ('overall: unresolved', A, '    if "UNRESOLVED" in classes:\n        return "HISTORICAL_IMPACT_UNRESOLVED"\n', ''),
    ('exp: trailing slash', A, 'if rel.startswith(k + "/") or rel == k:', 'if rel.startswith(k):'),
    ('scan: has field', A, 'has = bool(recs) and all("placement" in r for r in recs)', 'has = True'),
    ('c1 all', A, '    if all(above):\n        return "SUPPORTED"', '    if any(above):\n        return "SUPPORTED"'),
    ('c1 none', A, '    if not any(above):\n        return "CONTRADICTED"', '    if not all(above):\n        return "CONTRADICTED"'),
    ('c1 strict', A, 'board_bytes[L] / npu[L] > vela_bw[L]', 'board_bytes[L] / npu[L] >= vela_bw[L] * 2'),
    ('c2 factor', A, 'if f >= 1.3 and board_burst > vela_burst:', 'if f > 1.3 and board_burst > vela_burst:'),
    ('c2 burst', A, 'if f >= 1.3 and board_burst > vela_burst:', 'if f >= 1.3:'),
    ('c2 contradicted', A, '    if f < 1.1:\n        return "CONTRADICTED"', '    if f < 1.2:\n        return "CONTRADICTED"'),
    ('c3 low', A, 'return "SUPPORTED" if 0.8 <= board / vela_actual <= 1.25 else', 'return "SUPPORTED" if 0.8 < board / vela_actual <= 1.25 else'),
    ('c3 high', A, 'return "SUPPORTED" if 0.8 <= board / vela_actual <= 1.25 else', 'return "SUPPORTED" if 0.8 <= board / vela_actual <= 1.4 else'),
    ('cause both', A, 'if c1_ == "SUPPORTED" and c2_ == "SUPPORTED":', 'if c1_ == "SUPPORTED":'),
    ('cause contra', A, '    if c1_ == "CONTRADICTED":\n        return "CONTRADICTED"', '    if False:\n        return "CONTRADICTED"'),
    ('verdict i1', A, '    if not i1:\n        return "INVALID"', '    if False:\n        return "INVALID"'),
    ('verdict fits', A, 'if io_only and sram_fits and reference:', 'if io_only and reference:'),
    ('verdict ref', A, 'if io_only and sram_fits and reference:', 'if io_only and sram_fits:'),
    ('verdict partial', A, '    if io_only:\n        return "PARTIAL_IDENTIFIABILITY"', '    if True:\n        return "PARTIAL_IDENTIFIABILITY"'),
    ('arena align', A, 'start = (sram_free + mask) & ~mask', 'start = sram_free'),
    ('arena model align', A, 'if model_base & mask or ddr_arena < model_base:', 'if ddr_arena < model_base:'),
    ('arena below', A, 'if model_base & mask or ddr_arena < model_base:', 'if model_base & mask:'),
    ('arena fit', A, 'return a if a <= limit and arena_len <= limit - a else 0', 'return a'),
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
