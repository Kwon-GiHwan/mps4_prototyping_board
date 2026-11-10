"""Mutation test of the Stage 4C-2 rules (host/analysis/stage4c2.py): each must turn the suite
RED; files restored by sha256."""
import hashlib, os, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TESTS = ["test_stage4c2"]
A = "host/analysis/stage4c2.py"
M = [
    (A, "ub = math.ceil(h / uh) * math.ceil(w / uw) * math.ceil(sl / uc)", "ub = math.ceil(h / uh) * math.ceil(w / uw) * sl // uc"),
    (A, "steps = math.ceil(idep / ib)", "steps = 1"),
    (A, 'verdict="VALID" if valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") else "INVALID"',
     'verdict="VALID" if oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE", "FAIL") else "INVALID"'),
    (A, "base = dict(ok=same_out and not diff,", "base = dict(ok=not diff,"),
    (A, 'verdict="UNRESOLVED" if opposite else pa["verdict"]', 'verdict=pa["verdict"]'),
    (A, 'schedule="SAME_SCHEDULE" if st[b]["schedule"] == st[v]["schedule"] else "SCHEDULE_CHANGED"', 'schedule="SAME_SCHEDULE"'),
    (A, 'if "INVALID" in (res[b]["verdict"], res[v]["verdict"]):', 'if False:'),
    (A, 'mac_active_per_ublock=mac / st[c]["ofm_ublocks"]', 'mac_active_per_ublock=mac / st[c]["ublock_x_steps"]'),
    (A, '                          tuple(r["ofm_slice"] for r in rows)))', '                          ))'),
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
