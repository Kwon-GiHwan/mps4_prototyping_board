"""Mutation test of the Stage 4WD rules (CLAUDE.md: a check that cannot fail is worse than no check). Each mutation
neuters one rule in host/analysis/stage4wd.py, runs test_stage4wd, requires RED, and restores the file by sha256.

    python3 evidence/stage4wd/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage4wd.py"
T = ["test_stage4wd"]

# (id, file, old, new)
MUTATIONS = [
    ("encoded: all four streams", A, 'for f in ("weight_length", "weight1_length", "weight2_length", "weight3_length")', 'for f in ("weight_length",)'),
    ("staged: DMA lengths", A, 'staged = sum(sum(d for d in k["dma_before"] if d) for k in ks)', 'staged = 0'),
    ("spatial blocks", A, "spatial = math.ceil(ofm[0] / bh) * math.ceil(ofm[1] / bw)", "spatial = math.ceil(ofm[0] / bh)"),
    ("blocks: depth slices", A, "* math.ceil((k[\"ofm_depth_m1\"] + 1) / bc) for k in ks]", "* 1 for k in ks]"),
    ("inventory: refused boot skipped", A, 'if m.get("A_80") is None:                    # a refused boot (Stage 4AO act_none: one RUN)\n                continue',
     'if False:\n                continue'),
    ("rule: rd = spatial x staged", A, 'r["sram_rd"] == r["spatial_blocks"] * r["staged_bytes"] / BEAT and', 'True and'),
    ("rule: wr = staged", A, 'and r["sram_wr"] == r["staged_bytes"] / BEAT', 'and True'),
    ("same: absolute floor", A, "return abs(a - b) <= max(TOL_ABS, TOL_REL * (a + b) / 2, ra + rb)", "return abs(a - b) <= max(TOL_REL * (a + b) / 2, ra + rb)"),
    ("same: relative part", A, "return abs(a - b) <= max(TOL_ABS, TOL_REL * (a + b) / 2, ra + rb)", "return abs(a - b) <= max(TOL_ABS, ra + rb)"),
    ("same: ranges", A, "return abs(a - b) <= max(TOL_ABS, TOL_REL * (a + b) / 2, ra + rb)", "return abs(a - b) <= max(TOL_ABS, TOL_REL * (a + b) / 2)"),
    ("B: flat within groups", A, 'v = "BLOCK_LIKE" if flat and apart else', 'v = "BLOCK_LIKE" if apart else'),
    ("B: groups apart", A, 'v = "BLOCK_LIKE" if flat and apart else', 'v = "BLOCK_LIKE" if flat else'),
    ("B: rising with N", A, '("N_LIKE" if rising else "NEITHER")', '("N_LIKE" if True else "NEITHER")'),
    ("B: rising beyond tolerance", A, "rising = all(wd[y] > wd[x] and not eq(wd, x, y)", "rising = all(wd[y] > wd[x]"),
    ("B: incomplete", A, 'if any(wd.get(c) is None for c in EXP_B):\n        return dict(verdict="INCOMPLETE")',
     'if False:\n        return dict(verdict="INCOMPLETE")'),
    ("A: encoded proportional", A, 'if all(same(wd[c], pred[c], RNG.get(c, 0)) for c in EXP_A):', "if False:"),
    ("A: staged proportional", A, 'elif all(same(wd[c], pred_s[c], RNG.get(c, 0)) for c in EXP_A):', "elif False:"),
    ("A: constant", A, "elif all(eq(wd, c, ref) for c in EXP_A):", "elif False:"),
    ("A: monotone", A, 'v = "MONOTONE" if mono else "OTHER"', 'v = "MONOTONE"'),
    ("A: incomplete", A, 'if any(wd.get(c) is None for c in EXP_A):\n        return dict(verdict="INCOMPLETE")',
     'if False:\n        return dict(verdict="INCOMPLETE")'),
    ("SRAM verdict exact", A, "if sram_rd[c] != st[c][\"spatial_blocks\"] * st[c][\"staged_bytes\"] / BEAT}", "if False}"),
    ("SRAM verdict incomplete", A, 'if any(sram_rd.get(c) is None for c in cfgs):\n        return dict(verdict="INCOMPLETE")',
     'if False:\n        return dict(verdict="INCOMPLETE")'),
    ("judge: valid and stable only", A, 'ok = {c: r.get("verdict") == "VALID" and r.get("stable") for c, r in res.items()}',
     'ok = {c: True for c, r in res.items()}'),
    ("static: A same schedule", A, 'a_same_schedule=all(res[c]["ofm_block"] == ref["ofm_block"]', 'a_same_schedule=True or all(res[c]["ofm_block"] == ref["ofm_block"]'),
    ("static: B same block and stream", A, 'b_same_block=all(res[c]["ofm_block"] == ref["ofm_block"]', 'b_same_block=True or all(res[c]["ofm_block"] == ref["ofm_block"]'),
    ("static: golden unambiguous", A, '["opt_vs_ref"] == 0 for c in res if not c.startswith("_")))', '["opt_vs_ref"] >= 0 for c in res if not c.startswith("_")))'),
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
