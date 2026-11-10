"""Mutation test of the operator-aware pilot checks: each mutation must turn the suite RED; files restored by digest."""
import hashlib, pathlib, shutil, subprocess, sys

REPO = pathlib.Path("/Users/gihwan/Documents/Projects/mps4_prototyping_board-driver")
TESTS = ["test_qread_checked", "test_qread_op_pilot", "test_driver_runner_sim", "test_driver_runner_contract"]
FW = "firmware/driver_runner/use_case/pmu_runner/src/"
M = [
    (FW + "trace.c", "ok = (id == st.id && v != id &&", "ok = (v != id &&"),
    (FW + "trace.c", "ok = (id == st.id && v != id &&", "ok = (id == st.id &&"),
    (FW + "trace.c", "&& v >= lo && v <= hi &&", "&& v <= hi &&"),
    (FW + "trace.c", "&& v >= lo && v <= hi &&", "&& v >= lo &&"),
    (FW + "trace.c", "(v & align) == 0U) ? 1U : 0U;", "1) ? 1U : 0U;"),
    (FW + "trace.c", "while (a < TRACE_MAX_ATTEMPTS && ok == 0U)", "while (a < 1U && ok == 0U)"),
    (FW + "trace.c", "s->rejected += a - ok;", "s->rejected += 0U;"),
    (FW + "trace.c", "for (uint32_t i = 0; i < s->n; i++) { x ^= s->w[i]; }", ""),
    (FW + "trace.c", "if (held_valid != 0U && q != last_qread) { store_checked(&smp[cur ^ 1U]); }", ""),
    (FW + "trace.c", "    job_qread = 0U;\n", ""),
    (FW + "trace.c", "if (checked() && job != 0U) {", "if (checked()) {"),
    (FW + "trace.c", "if ((s->w[2] >> 20) & 1U) { job_qread = q; }", ""),
    (FW + "hooks.c", "sem == ethosu_drv.semaphore ? 1U : 0U", "1U"),
    ("host/lib/qread_checked.py", "if any(not x.checksum_ok for x in s):", "if False:"),
    ("host/lib/qread_checked.py", 'if h["trace_unaccepted"] != 0 or any(not sl.accepted for x in s for sl in x.slots):',
     'if h["trace_unaccepted"] != 0:'),
    ("host/lib/qread_checked.py", 'if h["trace_id"] != npu_id:', "if False:"),
    ("host/lib/qread_checked.py", "if t.qsize() != cms_len:", "if False:"),
    ("host/lib/qread_checked.py", "if any(b < a for a, b in zip(q, q[1:])):", "if False:"),
    ("host/lib/qread_checked.py", "if any(v > cms_len or v % 4 for v in q):", "if any(v > cms_len for v in q):"),
    ("host/lib/qread_checked.py", "if any(y.value < x.value for x, y in zip(a.events, b.events)):", "if False:"),
    ("host/lib/qread_checked.py", "return (RECOVERED if any(x.rejected for x in t.samples) else VALID), []",
     "return VALID, []"),
    ("host/lib/qread_checked.py", "if s.job and not s.start)", "if s.job)"),
    ("host/lib/qread_checked.py", "return self.accepted and len(self.attempts) == 1", "return self.accepted"),
    ("host/lib/qread_checked.py", 'if h["trace_rejected"] != sum(x.rejected for x in s):', "if False:"),
    ("host/lib/qread_checked.py", "if not job[-1].final or job[-1].qread_after.value != cms_len:", "if False:"),
    ("host/analysis/qread_op_pilot.py", "if abs(ma - mb) > FLOOR * mb:", "if abs(ma - mb) >= FLOOR * mb:"),
    ("host/analysis/qread_op_pilot.py", "FLOOR = 0.01", "FLOOR = 0.02"),
    ("host/analysis/qread_op_pilot.py", "    if C.INVALID in classes:\n        return C.INVALID\n", ""),
    ("host/analysis/qread_op_pilot.py", "ok = a.qread_before.first_ok and b.qread_after.first_ok", "ok = True"),
    ("host/analysis/qread_op_pilot.py", "for sl in (s.qread_before, s.qread_after) if sl.first_ok)",
     "for sl in (s.qread_before, s.qread_after))"),
    ("host/analysis/qread_op_pilot.py", 'for op in OPS) and v["separated"] for v in per.values())',
     "for op in OPS) for v in per.values())"),
    ("host/analysis/qread_op_pilot.py", '([] if run["output"] else ["output_mismatch"])', "[]"),
    ("host/analysis/qread_op_pilot.py", "width[op] <= RESOLUTION_FACTOR * width_q06[op]", "True"),
    ("host/analysis/qread_op_pilot.py", 'if prev.get("P2") != OBSERVED:', "if False:"),
    ("host/analysis/qread_op_pilot.py", 'if j["verdict"] in (C.VALID, C.RECOVERED):\n        ok, per', "if True:\n        ok, per"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def suite():
    for c in REPO.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    r = subprocess.run([sys.executable, "-B", "-m", "unittest", *TESTS], cwd=REPO / "host" / "tests",
                       capture_output=True, text=True)
    return r.returncode


assert suite() == 0, "suite not green before mutating"
import os
ONLY = os.environ.get('ONLY')
if ONLY: M = [M[int(i)] for i in ONLY.split(',')]
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
