"""Mutation test of the Stage 4C-2b rules (host/analysis/stage4c2b.py): each must turn the suite
RED; files restored by sha256."""
import hashlib, os, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TESTS = ["test_stage4c2b"]
A = "host/analysis/stage4c2b.py"
M = [
    (A, "H4=24 * 24 * 96 * math.ceil(cin / 16) * 16 / 768", "H4=24 * 24 * 96 * cin / 768"),
    (A, "H3=macs / 384", "H3=macs / 768"),
    (A, "    if len(set(macs_per_run)) != 1:\n", "    if False:\n"),
    (A, "    if not (valid and out_ok):\n", "    if not valid:\n"),
    (A, 'and set(r64["mac_dpu_active_per_run"]) == {REF_MAC} and same_out and not diff)', 'and set(r64["mac_dpu_active_per_run"]) == {REF_MAC} and not diff)'),
    (A, 'ref_ok = (r64["verdict"] != "INVALID" and set(r64["mac_active_per_run"]) == {REF_MAC}', 'ref_ok = (r64["verdict"] != "INVALID"'),
    (A, 'distinct={k: vals.count(v) == 1 for k, v in h.items()},', 'distinct={k: True for k, v in h.items()},'),
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
