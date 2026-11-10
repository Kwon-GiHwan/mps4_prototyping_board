"""Mutation test of the Stage 5-1/5-2 rules (host/analysis/stage5.py): each must turn the suite
RED; files restored by sha256."""
import hashlib, os, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TESTS = ["test_stage5"]
A = "host/analysis/stage5.py"
M = [
    (A, 'v = "PASS_EXACT" if mx == 0 else ("PASS_TOLERANCE" if mx <= 1 and not exact_only else "FAIL")',
     'v = "PASS_EXACT" if mx == 0 else ("PASS_TOLERANCE" if mx <= 1 else "FAIL")'),
    (A, 'base_check[w] = dict(ok=not diff and early_out and b["output"]["verdict"] == "PASS_EXACT",',
     'base_check[w] = dict(ok=early_out and b["output"]["verdict"] == "PASS_EXACT",'),
    (A, 'verdict="UNRESOLVED" if opposite else pa["verdict"]', 'verdict=pa["verdict"]'),
    (A, '            if x.get("verdict") != "VALID":\n                pairs[key] = dict(verdict="EXCLUDED"', '            if False:\n                pairs[key] = dict(verdict="EXCLUDED"'),
    (A, 'if not (folder / "runs.csv").exists() or not S4.load(folder, 1):', 'if not (folder / "runs.csv").exists():'),
    (A, 'x["same_output_as_base"] = x["output"]["npu_sha256"] == b["output"]["npu_sha256"]', 'x["same_output_as_base"] = True'),
    (A, '    if {r["crc"] for r in allr} != {zlib.crc32(npu)}:\n', '    if False:\n'),
    (A, 'comp = comp_of(c50[w][v], wl, name, c50[w]["base"]["nn_macs"])', 'comp = comp_of(c50[w][v], wl, name, c50[w][v]["nn_macs"])'),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def suite():
    for c in REPO.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    return subprocess.run([sys.executable, "-B", "-m", "unittest", *TESTS], cwd=REPO / "host" / "tests",
                          capture_output=True, text=True).returncode


assert suite() == 0, "suite not green before mutating"
if os.environ.get("ONLY"):
    M = [M[int(i)] for i in os.environ["ONLY"].split(",")]
red = 0
for f, a, b in M:
    p = REPO / f
    orig, d0 = p.read_bytes(), digest(p)
    s = orig.decode()
    assert s.count(a) == 1, (f, a, s.count(a))
    p.write_text(s.replace(a, b))
    rc = suite()
    p.write_bytes(orig)
    assert digest(p) == d0, f"restore failed {f}"
    red += rc != 0
    print(("RED     " if rc else "SURVIVED"), f, repr(a[:70]), flush=True)
print(f"{red}/{len(M)} RED; all files restored by digest")
assert suite() == 0
print("suite green after restore")
