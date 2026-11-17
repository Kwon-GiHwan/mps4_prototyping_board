"""Mutation test of the Stage 6C-0 rules (host/analysis/stage6c0.py). Each mutation neuters one rule, runs test_stage6c0,
requires RED, and restores the file by sha256.

    python3 evidence/stage6c0/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6c0.py"
T = ["test_stage6c0"]

MUTATIONS = [
    ("tol", A, "TOL = 0.01", "TOL = 0.02"),
    ("compute mac", A, "if (d_mac is not None and abs(d_mac) > TOL) or (d_dpu is not None and abs(d_dpu) > TOL):", "if (d_dpu is not None and abs(d_dpu) > TOL):"),
    ("compute dpu", A, "if (d_mac is not None and abs(d_mac) > TOL) or (d_dpu is not None and abs(d_dpu) > TOL):", "if (d_mac is not None and abs(d_mac) > TOL):"),
    ("transfer", A, "if any(x is not None and abs(x) > TOL for x in (rd, wr, tr)):", "if any(x is not None and abs(x) > TOL for x in (rd,)):"),
    ("transfer missing", A, "tot = lambda r, ks: None if any(r[k] is None for k in ks) else sum(r[k] for k in ks)", "tot = lambda r, ks: sum(r[k] or 0 for k in ks)"),
    ("memory vars", A, "if variable in (\"placement\", \"latency\", \"sram_budget\"):", "if variable in (\"placement\",):"),
    ("mapping", A, "for k in (\"traversal\", \"ofm_block\", \"ofm_ublock\", \"kernels\")):", "for k in (\"traversal\",)):"),
    ("mapping none", A, "if any(a[k] is not None and b[k] is not None and str(a[k]) != str(b[k])", "if any(str(a[k]) != str(b[k])"),
    ("npu tol", A, "tol_npu = None if d_npu is None else max(TOL * a[\"npu_active\"], (a[\"npu_range\"] or 0) + (b[\"npu_range\"] or 0))", "tol_npu = None if d_npu is None else TOL * a[\"npu_active\"]"),
    ("npu strict", A, "sig = d_npu is not None and abs(d_npu) > tol_npu", "sig = d_npu is not None and abs(d_npu) >= tol_npu"),
    ("pipeline", A, "if sig and d_mac is not None and abs(d_mac) <= TOL:", "if sig:"),
    ("unresolved", A, "if sig and not t:", "if not t:"),
    ("dir within", A, "return \"WITHIN_10PCT\" if abs(err) <= 0.10 else", "return \"WITHIN_10PCT\" if abs(err) < 0.10 else"),
    ("dir sign", A, "(\"UNDER_PREDICTS\" if err > 0 else \"OVER_PREDICTS\")", "(\"OVER_PREDICTS\" if err > 0 else \"UNDER_PREDICTS\")"),
    ("vela basis", A, "for basis in (\"vela_total\", \"vela_npu\"):", "for basis in (\"vela_npu\", \"vela_total\"):"),
    ("fam f1", A, "if op == \"Conv2D\" and k == \"1x1\" and trav == \"PartKernel\":", "if op == \"Conv2D\" and k == \"1x1\":"),
    ("fam f4 k", A, "int(k.split(\"x\")[1]) >= 7:", "int(k.split(\"x\")[1]) >= 5:"),
    ("fam f5 cin", A, "if op == \"Conv2D\" and cin is not None and cin < 16 and k != \"1x1\":", "if op == \"Conv2D\" and k != \"1x1\":"),
    ("share", A, "fam[f][r[\"model\"]] += n", "fam[f][r[\"model\"]] = n"),
    ("rep model", A, "model = max(sorted(shares[f]), key=lambda m: shares[f][m])", "model = min(sorted(shares[f]), key=lambda m: shares[f][m])"),
    ("rep op", A, "return max(cand, key=lambda r: (_f(r.get(\"n_mac_tflite\")) or 0, -int(r[\"tflite_op_index\"])))", "return cand[-1]"),
    ("control", A, "return c[0] if cin % 16 else c[1]", "return c[1] if cin % 16 else c[0]"),
    ("c1", A, "c1 = MEASURED_SHAPES[f] <= LOW_EVIDENCE_MAX", "c1 = True"),
    ("c2", A, "c2 = mx >= IMPORTANCE_MIN", "c2 = mx > 0"),
    ("c3", A, "not in MEASURED_KEYS[f]", "is not None"),
    ("importance", A, "IMPORTANCE_MIN = 0.10", "IMPORTANCE_MIN = 0.04"),
    ("specs gate", A, "        if not (s[\"c1_low_evidence\"] and s[\"c2_importance\"] and s[\"c3_new\"]) or s[\"rep\"] is None:\n            continue\n        base", "        if s[\"rep\"] is None:\n            continue\n        base"),
    ("specs control", A, "        if s[\"control\"]:\n            out.append(", "        if False:\n            out.append("),
    ("c5 single", A, "c5 = dict(single_npu_op=r is not None,", "c5 = dict(single_npu_op=True,"),
    ("c5 cpu", A, "no_cpu=not fact.get(\"cpu_rows\"),", "no_cpu=True,"),
    ("c5 pack", A, "packed=fact.get(\"pack_rc\") == 0,", "packed=True,"),
    ("c5 vela", A, "for k in (\"vela_op_cycles\", \"vela_npu_cycles\", \"sram_ac\", \"dram_ac\")),", "for k in (\"vela_op_cycles\",)),"),
    ("c5 fast", A, "fast_size=fact.get(\"pack_rc\") == 0 and fact.get(\"fast_size\", 1 << 30) <= LIMITS[\"fast_size\"],", "fast_size=True,"),
    ("c5 arena", A, "arena_size=fact.get(\"pack_rc\") == 0 and fact.get(\"arena_size\", 1 << 30) <= LIMITS[\"arena_size\"],", "arena_size=True,"),
    ("c5 region", A, "model_region=fact.get(\"pack_rc\") == 0 and fact.get(\"model_len\", 1 << 30) + fact.get(\"arena_size\", 0) <= LIMITS[\"model_region\"])", "model_region=True)"),
    ("c4 mapping", A, "for k in (\"traversal\", \"ofm_block\", \"ofm_ublock\")) \\\n            else \"COMPILER_MAPPING_CHANGE\"", "for k in (\"traversal\",)) \\\n            else \"COMPILER_MAPPING_CHANGE\""),
    ("final c4", A, "        if s[\"c4_controllable\"] and s[\"c5_analyzable\"]:", "        if s[\"c5_analyzable\"]:"),
    ("final c5", A, "        if s[\"c4_controllable\"] and s[\"c5_analyzable\"]:", "        if s[\"c4_controllable\"]:"),
    ("final control ok", A, "            if s[\"control\"] and s[\"control_check\"][\"c5_ok\"]:", "            if s[\"control\"]:"),
    ("budget", A, "    while 1 + len(shapes) > MAX_BOOTS and chosen:", "    while len(shapes) > MAX_BOOTS and chosen:"),
    ("budget order", A, "        f = chosen.pop()", "        f = chosen.pop(0)"),
    ("ctl traversal", A, "cc[\"traversal_same\"] = r0 is not None and r1 is not None and r0.get(\"traversal\") == r1.get(\"traversal\")", "cc[\"traversal_same\"] = True"),
    ("pair placement", A, "    (\"4p placement DDR->SRAM\", \"stage4p:conv_base_ddr\", \"stage4p:conv_base_sram\", \"placement\"),\n", ""),
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
