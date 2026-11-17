"""Mutation test of the Stage 6B-E2E-B judge (host/analysis/stage6be2eb.py) and of the shared identity it relies on.
Each mutation neuters one rule, runs test_stage6be2eb, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6be2eb/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2eb.py"
K = "host/analysis/stage4k.py"
B = "host/analysis/stage6bb.py"
T = ["test_stage6be2eb"]

MUTATIONS = [
    ("io: both", A, "return \"IO_PLACEMENT_EFFECT_OBSERVED\" if all(big) and same_sign", "return \"IO_PLACEMENT_EFFECT_OBSERVED\" if any(big) and same_sign"),
    ("io: sign", A, "return \"IO_PLACEMENT_EFFECT_OBSERVED\" if all(big) and same_sign", "return \"IO_PLACEMENT_EFFECT_OBSERVED\" if all(big)"),
    ("io: strict", A, "big = [abs(pe[L]) > tols[L] for L in (500, 1000)]", "big = [abs(pe[L]) >= tols[L] for L in (500, 1000)]"),
    ("io: usable", A, "    if not usable:\n        return \"NOT_IDENTIFIABLE\"", "    if False:\n        return \"NOT_IDENTIFIABLE\""),
    ("sens: strict", A, "return \"IO_SENSITIVITY_REDUCED\" if inter > t else", "return \"IO_SENSITIVITY_REDUCED\" if inter >= t else"),
    ("sens: abs", A, "return \"IO_SENSITIVITY_REDUCED\" if inter > t else", "return \"IO_SENSITIVITY_REDUCED\" if abs(inter) > t else"),
    ("sens: usable", A, "    if not usable:\n        return \"INSUFFICIENT_EVIDENCE\"", "    if False:\n        return \"INSUFFICIENT_EVIDENCE\""),
    ("resp: abs", A, "return \"RESIDUAL_RESPONSE_OBSERVED\" if abs(le) > t else", "return \"RESIDUAL_RESPONSE_OBSERVED\" if le > t else"),
    ("resp: strict", A, "return \"RESIDUAL_RESPONSE_OBSERVED\" if abs(le) > t else", "return \"RESIDUAL_RESPONSE_OBSERVED\" if abs(le) >= t else"),
    ("resp: usable", A, "    if not usable:\n        return \"NOT_EVALUABLE\"", "    if False:\n        return \"NOT_EVALUABLE\""),
    ("ext: tol", A, "return abs(beats - expected) <= EXT_TOL * expected", "return abs(beats - expected) <= 2 * EXT_TOL * expected"),
    ("ext: tol const", A, "EXT_TOL = 0.01", "EXT_TOL = 0.05"),
    ("ext: expected", A, "B3_EXT_READ_BYTES = 174752 + 5760 + 628", "B3_EXT_READ_BYTES = 174752 + 5760 + 348"),
    ("path: write", A, "v[\"ext_wr_beats\"] != 0 or v[\"ext_rd_beats\"] >= b0_ext_read", "v[\"ext_rd_beats\"] >= b0_ext_read"),
    ("path: below b0", A, "v[\"ext_wr_beats\"] != 0 or v[\"ext_rd_beats\"] >= b0_ext_read", "v[\"ext_wr_beats\"] != 0"),
    ("path: empty", A, "    if not b3 or any(", "    if any("),
    ("path: both L", A, "if len(b3) == 2 and all(", "if all("),
    ("path: within", A, "and all(ext_within(v[\"ext_rd_beats\"], EXT_READ_EXPECTED[\"B3\"]) for v in b3.values()):", ":"),
    ("valid: gate", A, "if gate.get(\"verdict\") != \"PASS\" or any(", "if any("),
    ("valid: stop", A, "or any(r[\"status\"] in STOP for r in res.values()):", ":"),
    ("valid: mac", A, "if all(r[\"status\"] == \"VALID\" for r in res.values()) and all(mac_ok.values()):", "if all(r[\"status\"] == \"VALID\" for r in res.values()):"),
    ("eff: tol pe", A, "t_pe = {L: tol(b(\"B3\", L), [r(\"B0\", L), r(\"B3\", L)]) for L in (500, 1000)}", "t_pe = {L: tol(b(\"B3\", L), [r(\"B0\", L)]) for L in (500, 1000)}"),
    ("eff: inter", A, "inter = le[\"B0\"] - le[\"B3\"]", "inter = le[\"B3\"] - le[\"B0\"]"),
    ("eff: tol i", A, "t_i = tol(b(\"B3\", 500), [r(c, L) for c in CELLS for L in (500, 1000)])", "t_i = tol(b(\"B3\", 500), [r(c, 500) for c in CELLS])"),
    ("eff: tol le", A, "t_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in CELLS}", "t_le = {c: tol(b(c, 500), [r(c, 500)]) for c in CELLS}"),
    ("tol: floor", A, "NOISE_FLOOR = 0.01", "NOISE_FLOOR = 0.0"),
    ("usable: mac", A, "good = lambda k: res[k][\"status\"] == \"VALID\" and mac_ok.get(k, False)", "good = lambda k: res[k][\"status\"] == \"VALID\""),
    ("layout: where", A, "return dict(arena_where=r.get(\"arena_base\") == a and b(1) == a,", "return dict(arena_where=True,"),
    ("layout: inside", A, "arena_inside=mem[0] <= b(1) and b(1) + alen <= mem[1] and s(1) <= alen,", "arena_inside=True,"),
    ("layout: inside size", A, "arena_inside=mem[0] <= b(1) and b(1) + alen <= mem[1] and s(1) <= alen,", "arena_inside=mem[0] <= b(1) and b(1) + alen <= mem[1],"),
    ("layout: fast inside", A, "fast_inside=fb <= b(2) and b(2) + s(2) <= fb + fs,", "fast_inside=True,"),
    ("layout: disjoint fast mem", A, " and (fb + fs <= b(1) or b(1) + alen <= fb),", ","),
    ("layout: disjoint region2", A, "fast_disjoint=(b(2) + s(2) <= b(1) or b(1) + alen <= b(2)) and ", "fast_disjoint="),
    ("layout: weights", A, "weights_ddr=mb <= b(0) and b(0) + s(0) <= mb + r.get(\"model_len\", 0),", "weights_ddr=True,"),
    ("layout: io", A, "io_in_arena=all(b(1) <= b(i) and b(i) + s(i) <= b(1) + s(1) for i in io))", "io_in_arena=True)"),
    ("layout: empty", A, "    if not records or None in (fb, fs, mb, lim, alen):", "    if None in (fb, fs, mb, lim, alen):"),
    ("layout: used", A, "    env += [f\"layout {c}\" for c, v in lay[\"checks\"].items() if not v]\n", ""),
    ("layout: sram window", A, "mem = (SRAM_BASE, SRAM_LIMIT) if placement == 1 else (mb, lim)", "mem = (SRAM_BASE, 0x40000000) if placement == 1 else (mb, lim)"),
    ("arena: align", A, "start = (fast_base + fast_size + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)", "start = fast_base + fast_size"),
    ("arena: ddr round", A, "ddr = model_base + ((model_len + 15) & ~15)", "ddr = model_base + model_len"),
    ("cr: env", A, "    if env:\n        return dict(base, status=\"CONFIG_MISMATCH\", reasons=env, layout=lay)", "    if False:\n        return dict(base, status=\"CONFIG_MISMATCH\", reasons=env, layout=lay)"),
    ("cr: output", A, "if not BB.output_ok(folder, wl, cfg, m, s[\"runs\"]) or not", "if not"),
    ("cr: pmu", A, "    if p:\n        return dict(base, status=\"INVALID_PMU\", reasons=p)", "    if False:\n        return dict(base, status=\"INVALID_PMU\", reasons=p)"),
    ("cr: stable", A, "return dict(res, status=\"UNSTABLE\", reasons=st) if st else", "return"),
    ("gate: reproduce", A, "return dict(verdict=\"PASS\" if rep[\"ok\"] and same else \"FAIL\"", "return dict(verdict=\"PASS\""),
    ("gate: ref valid", A, "    if r[\"status\"] != \"VALID\":\n        return dict(verdict=\"FAIL\", why=r[\"status\"], reasons=r[\"reasons\"])", "    if False:\n        pass"),
    ("stop: set", A, "STOP = (\"CONFIG_MISMATCH\", \"UNMEASURED\")", "STOP = (\"CONFIG_MISMATCH\",)"),
    ("order", A, "(\"B3\", 1000, 461), (\"B0\", 1000, 462)]", "(\"B0\", 1000, 461), (\"B3\", 1000, 462)]"),
    ("placement const", A, "PLACEMENT = {\"REF\": 0, \"B0\": 0, \"B3\": 1}", "PLACEMENT = {\"REF\": 0, \"B0\": 0, \"B3\": 0}"),
    ("shared: K placement", K, "placement=all(r.get(\"placement\") == expected_placement for r in recs),", "placement=True,"),
    ("shared: BB manifest", B, "exp = m.get(\"placement\", 0)", "exp = 0"),
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
