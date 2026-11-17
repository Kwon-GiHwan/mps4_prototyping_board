"""Mutation test of the shared identity expected-placement change (maintenance 2026-11-17) and of the regression
gate compare.py. Each mutation neuters one rule, runs test_identity_placement plus the earlier suites that use the
shared identity, requires RED, and restores the file by sha256.

    python3 evidence/maint/identity_placement/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
K = "host/analysis/stage4k.py"
A = "host/analysis/stage4aoe.py"
B = "host/analysis/stage6bb.py"
C = "evidence/maint/identity_placement/compare.py"
T = ["test_identity_placement", "test_stage6be2d", "test_stage6be2ea"]

MUTATIONS = [
    ("K: placement fixed 0", K, 'placement=all(r.get("placement") == expected_placement for r in recs),',
     'placement=all(r.get("placement") == 0 for r in recs),'),
    ("K: placement ignored", K, 'placement=all(r.get("placement") == expected_placement for r in recs),', 'placement=True,'),
    ("K: placement any RUN", K, 'placement=all(r.get("placement") == expected_placement for r in recs),',
     'placement=any(r.get("placement") == expected_placement for r in recs),'),
    ("K: regioncfg fixed DDR", K, 'r.get("regioncfg_irq") == REGIONCFG_N5.get(expected_placement)', 'r.get("regioncfg_irq") == REGIONCFG_DDR'),
    ("K: regioncfg ignored", K, 'r.get("regioncfg_irq") == REGIONCFG_N5.get(expected_placement) and ', ''),
    ("K: SRAM value", K, "REGIONCFG_N5 = {0: REGIONCFG_DDR, 1: 0x153,", "REGIONCFG_N5 = {0: REGIONCFG_DDR, 1: 0x15F,"),
    ("K: default 1", K, "             expected_placement: int = 0) -> dict:", "             expected_placement: int = 1) -> dict:"),
    ("A1: not passed", A, "k = K.identity(folder, wl, cfg, caps_ref, expected_placement)", "k = K.identity(folder, wl, cfg, caps_ref)"),
    ("A1: header instead of manifest", A, "k = K.identity(folder, wl, cfg, caps_ref, expected_placement)",
     "k = K.identity(folder, wl, cfg, caps_ref, expected_identity(wl, cfg)[\"placement\"])"),
    ("A: placement 2 region 0", A, "(REGION0_SRAM if placement == 2 else REGION0) if i == 0", "REGION0 if i == 0"),
    ("A: placement 2 region 1", A, "(REGION1_SRAM if placement in (1, 2) else REGION1_DDR)", "(REGION1_SRAM if placement == 1 else REGION1_DDR)"),
    ("K: placement 2 value", K, "1: 0x153, 2: 0x150}", "1: 0x153, 2: 0x153}"),
    ("A1: default 1", A, "                expected_placement: int = 0) -> dict:", "                expected_placement: int = 1) -> dict:"),
    ("BB: manifest ignored", B, 'exp = m.get("placement", 0)', "exp = 0"),
    ("BB: absent -> 1", B, 'exp = m.get("placement", 0)', 'exp = m.get("placement", 1)'),
    ("BB: from RUN", B, 'exp = m.get("placement", 0)',
     'exp = json.loads((folder / "raw_runs.json").read_text())[1]["record"]["placement"]'),
    ("BB: reference not passed", B, "return K.identity(folder, wl, cfg, caps_ref, exp) if", "return K.identity(folder, wl, cfg, caps_ref) if"),
    ("cmp: any flip expected", C, 'and flips == {"placement": [False, True]} and rest_same', "and rest_same"),
    ("cmp: direction", C, 'flips == {"placement": [False, True]}', 'flips in ({"placement": [False, True]}, {"placement": [True, False]})'),
    ("cmp: rest ignored", C, 'and flips == {"placement": [False, True]} and rest_same', 'and flips == {"placement": [False, True]}'),
    ("cmp: K may flip", C, 'expected = fn.startswith("identity_of[") and ', "expected = "),
    ("cmp: verdict", C, 'res["verdict"] = "REGRESSION_PASS" if not res["unexpected"] else "REGRESSION_FAIL"', 'res["verdict"] = "REGRESSION_PASS"'),
    ("cmp: exit", C, 'sys.exit(0 if res["verdict"] == "REGRESSION_PASS" else 1)', "sys.exit(0)"),
    ("cmp: folder set", C, '    res["unexpected"].append("folder sets differ")', "    pass"),
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
