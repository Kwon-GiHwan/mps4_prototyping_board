"""Mutation test of the Stage 4 rules (host/analysis/stage4.py) and the GET_OUTPUT path: each must turn the suite RED;
files restored by sha256."""
import hashlib, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TESTS = ["test_stage4", "test_driver_runner_sim", "test_driver_runner_contract"]
A = "host/analysis/stage4.py"
FW = "firmware/driver_runner/use_case/pmu_runner/src/runner.c"
M = [
    (A, '"PASS_TOLERANCE" if mx <= 1 else "FAIL"', '"PASS_TOLERANCE" if mx <= 2 else "FAIL"'),
    (A, 'verdict="PASS_EXACT" if mx == 0 else', 'verdict="PASS_EXACT" if mx <= 1 else'),
    (A, "    if len(npu) != n or len(ref) != n:\n", "    if False:\n"),
    (A, "    if {r[\"crc\"] for r in all_runs} != {zlib.crc32(npu)}:\n", "    if False:\n"),
    (A, "    if fw != {(mism, mx)}:\n", "    if False:\n"),
    (A, 'gate = "PASS" if valid and oc["verdict"]', 'gate = "PASS" if oc["verdict"]'),
    (A, "    if abs(mv - mb) <= t:\n", "    if abs(mv - mb) < t:\n"),
    (A, "FLOOR = 0.01", "FLOOR = 0.02"),
    (A, "return max(FLOOR * mb, rb or 0, rv or 0)", "return FLOOR * mb"),
    (A, "    elif abs(mv - expected) <= t:\n", "    elif True:\n"),
    (A, 'sched = (c1["ofm_block"], c1["ofm_ublock"], c1["n_kernels"]) != (c2["ofm_block"], c2["ofm_ublock"], c2["n_kernels"])',
     'sched = (c1["ofm_ublock"], c1["n_kernels"]) != (c2["ofm_ublock"], c2["n_kernels"])'),
    (A, "changed=abs(y - x) > tol(b2, v2, code),", "changed=False,"),
    (A, 'if cfgs[b]["gate_c"] == cfgs[v]["gate_c"] == "PASS"', 'if True'),
    (A, "diff_1lsb_count=sum(v == 1 for v in d)", "diff_1lsb_count=sum(v >= 1 for v in d)"),
    (A, "diff_gt_1lsb_count=sum(v > 1 for v in d)", "diff_gt_1lsb_count=sum(v > 2 for v in d)"),
    (FW, "            crc = crc32_update(crc, o, len);\n", ""),
    (FW, "                if (at + k >= first) { out[got++] = o[k]; }", "                out[got++] = o[k];"),
    (FW, "                                  || cmd == CMD_GET_OUTPUT;", "                                  ;"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def suite():
    for c in REPO.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    return subprocess.run([sys.executable, "-B", "-m", "unittest", *TESTS], cwd=REPO / "host" / "tests",
                          capture_output=True, text=True).returncode


assert suite() == 0, "suite not green before mutating"
import os
if os.environ.get('ONLY'):
    M = [M[int(i)] for i in os.environ['ONLY'].split(',')]
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
