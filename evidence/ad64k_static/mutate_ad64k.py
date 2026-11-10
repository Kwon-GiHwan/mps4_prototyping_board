"""Mutation test of host/analysis/ad64k_static.py's refusals and decoding: each mutation must turn
test_ad64k_static RED; the file is restored by sha256."""
import hashlib, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = REPO / "host/analysis/ad64k_static.py"
M = [
    ("        if a != b:\n", "        if False:\n"),
    ('    if [int(r["offset"]) for r in rows] != [k["offset"] for k in regs] or len(hl) != len(regs):',
     '    if len(hl) != len(regs):'),
    ('        if c["op"] != r["optimised_op"]:', '        if False:'),
    ('        if op_name != r["optimised_op"]:', '        if False:'),
    ('        if ub != f"U{ub_dims[0]}X{ub_dims[1]}":', '        if False:'),
    ('wl = 0 if k["kind"] == "POOL" else sum(', 'wl = sum('),
    ('    mb = (param >> 8) & 7', '    mb = (param >> 7) & 7'),
    ('    return -(-h // ub[0]) * -(-w // ub[1]) * -(-c // ub[2])', '    return h // ub[0] * -(-w // ub[1]) * -(-c // ub[2])'),
]


def suite():
    for c in REPO.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    return subprocess.run([sys.executable, "-B", "-m", "unittest", "test_ad64k_static"], cwd=REPO / "host" / "tests",
                          capture_output=True, text=True).returncode


assert suite() == 0, "suite not green before mutating"
orig = A.read_bytes(); d0 = hashlib.sha256(orig).hexdigest(); red = 0
for a, b in M:
    s = orig.decode(); assert s.count(a) == 1, (a, s.count(a))
    A.write_text(s.replace(a, b)); rc = suite(); A.write_bytes(orig)
    assert hashlib.sha256(A.read_bytes()).hexdigest() == d0, "restore failed"
    red += rc != 0
    print("RED     " if rc else "SURVIVED", repr(a.strip()[:70]), flush=True)
print(f"{red}/{len(M)} RED; restored by digest")
assert suite() == 0
print("suite green after restore")
