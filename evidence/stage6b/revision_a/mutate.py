"""Mutation test of the Stage 6B Revision A judge (evidence/stage6b/revision_a/revision_a_contract.md). Each mutation
neuters one rule in host/analysis/stage6b_revision_a.py, runs test_stage6b_revision_a, requires RED, and restores the
file by sha256.

    python3 evidence/stage6b/revision_a/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6b_revision_a.py"
T = ["test_stage6b_revision_a"]

MUTATIONS = [
    ('EXACT_A = Stage 6B definition', A, 'CLS = {"EXACT_STATIC_MATCH": "EXACT_A", "PARTIAL_STATIC_MATCH": "PARTIAL_A"', 'CLS = {"EXACT_STATIC_MATCH": "EXACT_A", "PARTIAL_STATIC_MATCH": "EXACT_A"'),
    ('params: weight/bias bytes', A, '(("sha256",) if k in ("w", "b") else ())', '()'),
    ('params: conv OFM quantisation', A, 'for k in ("ifm", "w", "b", "ofm")}', 'for k in ("ifm", "w", "b")}'),
    ('ref: numpy tolerance', A, 'NUMPY_MAX_ABS = 1 ', 'NUMPY_MAX_ABS = 2 '),
    ('ref: informative threshold', A, 'INFORMATIVE_MIN = 0.10', 'INFORMATIVE_MIN = 0.0'),
    ('ref: conv_out saturation', A, 'if r.get("conv_out_informative", 0) < INFORMATIVE_MIN:', 'if False:'),
    ('ref: final saturation', A, 'if r.get("final_informative", 0) < INFORMATIVE_MIN:', 'if False:'),
    ('ref: self-ADD tolerance', A, 'SELF_ADD_MAX_ABS = 1 ', 'SELF_ADD_MAX_ABS = 200 '),
    ('ref: self-ADD identity A2 only', A, 'if label == "A2" and', 'if label != "A0" and'),
    ('ref: golden = BUILTIN_REF', A, 'if form.get("golden_sha256") != (form.get("reference") or {}).get("ref_sha256"):', 'if False:'),
    ('ref: reference output', A, 'if not form.get("feasible", {}).get("reference") or not r.get("final_sha256_equals_ref"):', 'if False:'),
    ('repeat: kernels compared', A, '"cms_sha256", "conv_row", "conv_kernels")\n    diffs', '"cms_sha256", "conv_row")\n    diffs'),
    ('repeat: manifest compared', A, 'keys = ("model_sha256", "vela_sha256", "drwl_sha256", "manifest_sha256",', 'keys = ("model_sha256", "vela_sha256", "drwl_sha256",'),
    ('fusion: scheduled ops', A, 'if form.get("npu_ops") != EXPECTED_OPS[label]:', 'if False:'),
    ('fusion: cpu ops', A, 'if form.get("cpu_rows"):', 'if False:'),
    ('fusion: fused names', A, 'if str(row.get("fused_names")) != "1":', 'if False:'),
    ('fusion: conv output tensor', A, 'if row.get("name") != CONV_OUT_NAME[label]:', 'if False:'),
    ('registers: regions compared', A, 'REG_CONFIG + REG_REGION)', 'REG_CONFIG)'),
    ('registers: kernel count', A, 'if len(orig) != len(mine):', 'if False:'),
    ('registers: original compile identity', A, 'if not original or not original.get("vela_sha256", "").startswith(inv_vela) or original.get("n_ethosu_ops") != 1:', 'if not original:'),
    ('eligible: NOT_VERIFIED blocks', A, 'all(c["status"] == PASS for c in checks.values())', 'all(c["status"] != FAIL for c in checks.values())'),
    ('package: feasibility', A, 'diffs = [k for k, ok in form.get("feasible", {}).items() if not ok]', 'diffs = []'),
    ('package: TA profile 1', A, 'if form.get("ta_profile") != TA_PROFILE:', 'if False:'),
    ('package: DDR placement', A, 'if form.get("placement") != PLACEMENT_DDR:', 'if False:'),
    ('package: n_base max', A, 'N_BASE_MAX = 8', 'N_BASE_MAX = 9'),
    ('eligible: EXACT_A required', A, 'ok = ex["cls"] == "EXACT_A" and all(', 'ok = ex["cls"] != "NOT_REPRODUCIBLE_A" and all('),
    ('form: A0 > A1 > A2', A, 'key=lambda f: (RANK[forms[f]["cls"]], FORMS.index(f)))', 'key=lambda f: (RANK[forms[f]["cls"]], -FORMS.index(f)))'),
    ('form: first eligible board form', A, 'board = next((f for f in FORMS if', 'board = next((f for f in reversed(FORMS) if'),
    ('select: BOARD_ELIGIBLE', A, '"EXACT_STATIC_MATCH" if j["board_eligible"] else', '"EXACT_STATIC_MATCH" if True else'),
    ('prov: A0/A1 bytes = Stage 6B', A, 'if prev is None or prev != now:', 'if prev is None:'),
    ('prov: source model sha', A, 'if rec.get("source", {}).get("model_sha256") != c["model_sha256"]:', 'if False:'),
    ('prov: source tensors', A, 'if any(tensor_eq(c["tensors"][k], rec.get("source", {}).get("tensors", {}).get(k)) for k in ("ifm", "w", "b", "ofm")):', 'if False:'),
    ('prov: candidate set', A, 'if man.get("n") != len(cands) or', 'if False and'),
    ('prov: missing form', A, 'if f not in (rec.get("forms") or {}):', 'if False:'),
    ('verdict: provenance -> INVALID', A, 'if prov_err:', 'if False:'),
    ('verdict: new shape besides G14', A, 'if j["board_eligible"] and g != "G14")', 'if j["board_eligible"])'),
    ('verdict: selection reproducible', A, 'if [s["group"] for s in sel] != [s["group"] for s in sel2]:', 'if False:'),
    ('verdict: board contract', A, 'if not board_contract:', 'if False:'),
    ('second compile: class', A, ' and j["forms"][f]["second_cls"] == "EXACT_A"), None)', '), None)'),
    ('coverage: validated unchanged', A, 'validated_hw_coverage=s6cov.get(m),', 'validated_hw_coverage=(s6cov.get(m) or 0) + share(mac(sel_rows)),'),
    ('coverage: calibrated not recounted', A, 'new = [r for r in sel_rows if (m, r["scheduled_id"]) not in calibrated]', 'new = sel_rows'),
    ('coverage: NO_ELIGIBLE', A, '"NO_ELIGIBLE" if not own(elig) else', '"NO_ELIGIBLE" if False else'),
    ('coverage: static = EXACT_A', A, 'static_reproduction_coverage=share(mac(own(exact))),', 'static_reproduction_coverage=share(mac(own(elig))),'),
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
