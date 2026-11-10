"""Mutation test of the Stage 4C-1 prediction and verdict rules (host/analysis/stage4c1.py): each must turn the suite
RED; files restored by sha256."""
import hashlib, os, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TESTS = ["test_stage4c1"]
A = "host/analysis/stage4c1.py"
M = [
    (A, "return (MODEL_BASE + model_len + ALIGN - 1) & ~(ALIGN - 1)", "return MODEL_BASE + model_len"),
    (A, 'v = "PREDICTION_MATCH" if beats[0] == pred["predicted_write_beats"]["A"] else',
     'v = "PREDICTION_MATCH" if beats[0] in pred["predicted_write_beats"].values() else'),
    (A, "    elif len(set(beats)) != 1:\n", "    elif False:\n"),
    (A, 'if not (valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") and addr_ok):',
     'if not (valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE")):'),
    (A, 'if not (valid and oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") and addr_ok):',
     'if not (oc["verdict"] in ("PASS_EXACT", "PASS_TOLERANCE") and addr_ok):'),
    (A, '    elif pred["not_comparable"]:\n', "    elif False:\n"),
    (A, 'verdict="UNRESOLVED" if opposite else pa["verdict"]', 'verdict=pa["verdict"]'),
    (A, "base_check[b] = dict(ok=same_out and not diff,", "base_check[b] = dict(ok=same_out,"),
    (A, 'dense = (k0["ofm_stride_x"] == c and', 'dense = (True and'),
    (A, 'not_comparable=not (comp["gate_b"] and dense and comp["ifm_memory"] == comp["ofm_memory"] == "Dram"',
     'not_comparable=not (comp["gate_b"] and dense'),
    (A, "pred = dict(A=BM.count_at(base, hh, ww, c, c, ww * c, BM.rule_a),",
     "pred = dict(A=BM.count_at(base, hh, ww, c, c, ww * c, lambda cc: [(0, cc)]),"),
    (A, 'discriminating=pred["A"] not in (pred["B"], pred["C"], pred["D"]),', 'discriminating=True,'),
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
