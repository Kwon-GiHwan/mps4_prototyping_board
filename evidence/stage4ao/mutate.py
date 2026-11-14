"""Mutation test of the Stage 4AO rules (CLAUDE.md: a check that cannot fail is worse than no check). Each mutation
neuters one rule in host/analysis/stage4ao.py, runs test_stage4ao, requires RED, and restores the file by sha256.
Writes mutation.txt beside this file; exits 1 if a mutation survives or a file does not come back byte-identical.

    python3 evidence/stage4ao/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage4ao.py"
T = ["test_stage4ao"]

# (id, file, old, new)
MUTATIONS = [
    ("SU rate 16 (TRM Table 4-11)", A, "SU_RATE = 16 ", "SU_RATE = 15 "),
    ("c16: channel rounding", A, "return h * w * math.ceil(c / 16) * 16", "return h * w * c"),
    ("tol: absolute floor", A, "return max(T_ABS, T_REL * pred)", "return T_REL * pred"),
    ("tol: relative part", A, "return max(T_ABS, T_REL * pred)", "return T_ABS"),
    ("calibration: median of five boots", A, "c0 = statistics.median(v - 55296 / SU_RATE for v in per.values())",
     "c0 = max(v - 55296 / SU_RATE for v in per.values())"),
    ("M3: per-block scaling", A, "M3=n_ofm / SU_RATE + c0 * blocks / ref_blocks", "M3=n_ofm / SU_RATE + c0"),
    ("comparable: >= 3", A, 'verdict="COMPARABLE" if len(same) >= 3 else "NEEDS_REVISION"',
     'verdict="COMPARABLE" if len(same) >= 2 else "NEEDS_REVISION"'),
    ("comparable: signature", A, 'same = [c for c in cfgs if st[c]["signature"] == ref and st[c]["gate_b"]]',
     'same = [c for c in cfgs if st[c]["gate_b"]]'),
    ("comparable: gate B", A, 'same = [c for c in cfgs if st[c]["signature"] == ref and st[c]["gate_b"]]',
     'same = [c for c in cfgs if st[c]["signature"] == ref]'),
    ("phase C: only ACTIVATION_MIN/MAX", A, "and set(d[\"ops\"]) <= ALLOWED_C_DIFF", "and True"),
    ("phase C: weight stream", A, 'and st[c]["weight_lengths"] == st[REF_H]["weight_lengths"]', "and True"),
    ("phase C: signature", A, 'ok = st[c]["gate_b"] and st[c]["signature"] == st[REF_H]["signature"] and d["aligned"]',
     'ok = st[c]["gate_b"] and d["aligned"]'),
    ("phase C: gate B", A, 'ok = st[c]["gate_b"] and st[c]["signature"] == st[REF_H]["signature"] and d["aligned"]',
     'ok = st[c]["signature"] == st[REF_H]["signature"] and d["aligned"]'),
    ("stream diff: alignment", A, "if len(x) != len(y) or any(p[:2] != q[:2] for p, q in zip(x, y)):", "if False:"),
    ("stream diff: payload compared", A, "d = [(i, p[1], p[2:], q[2:]) for i, (p, q) in enumerate(zip(x, y)) if p != q]",
     "d = [(i, p[1], p[2:], q[2:]) for i, (p, q) in enumerate(zip(x, y)) if p[:3] != q[:3]]"),
    ("static: base == ref bytes", A, "same = lambda a, b: (wl / a).read_bytes() == (wl / b).read_bytes()",
     "same = lambda a, b: True"),
    ("stability: AO range", A, "r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao)", "True"),
    ("stability: AO range 50 floor", A, "r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao)", "r <= AO_RANGE_REL * ao"),
    ("stability: pass A/B", A, "abs(b - a) <= max(AB_REL * a, (m.get(\"A_35_range\") or 0) + (m.get(\"B_35_range\") or 0))",
     "True"),
    ("rate: INVALID below 3 valid", A, 'if len(valid) < 3:\n        return dict(verdict="INVALID", valid=valid)',
     'if not valid:\n        return dict(verdict="INVALID", valid=valid)'),
    ("rate: MEASUREMENT_UNSTABLE", A, 'if not all(res[c]["stability"]["ok"] for c in valid):', "if False:"),
    ("rate: SCHEDULE_CONFOUNDED", A, 'if len(use) < 3:\n        return dict(verdict="SCHEDULE_CONFOUNDED"',
     'if not use:\n        return dict(verdict="SCHEDULE_CONFOUNDED"'),
    ("rate: slope tolerance", A, 'verdict="RATE_CONSISTENT" if abs(b - 1) <= SLOPE_TOL else "RATE_NOT_CONSISTENT", configs=use',
     'verdict="RATE_CONSISTENT" if b - 1 <= SLOPE_TOL else "RATE_NOT_CONSISTENT", configs=use'),
    ("act: validity", A, 'if r.get("verdict") != "VALID" or ref.get("verdict") != "VALID":', "if False:"),
    ("act: stability", A, 'if not (r["stability"]["ok"] and ref["stability"]["ok"]):', "if False:"),
    ("act: tolerance", A, 'verdict="RATE_CONSISTENT" if abs(d) <= tol(ref["metrics"]["A_64"]) else "RATE_NOT_CONSISTENT"',
     'verdict="RATE_CONSISTENT"'),
    ("model check: tolerance", A, "within=abs(ao - v) <= tol(v)", "within=True"),
    ("config: PASS_EXACT", A, 'ok = runs_ok and ident["ok"] and oc["verdict"] == "PASS_EXACT"',
     'ok = runs_ok and ident["ok"] and oc["verdict"] != "INVALID"'),
    ("config: identity", A, 'ok = runs_ok and ident["ok"] and oc["verdict"] == "PASS_EXACT"',
     'ok = runs_ok and oc["verdict"] == "PASS_EXACT"'),
    ("config: four valid RUNs per pass", A, "all(len(rs) == 4 and all(r[\"valid\"] for r in rs)",
     "all(all(r[\"valid\"] for r in rs)"),
    ("repro: reproduce()", A, 'verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep',
     'verdict="PASS" if ao_ok else "FAIL", reproduce=rep'),
    ("repro: AO tolerance", A, 'verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep',
     'verdict="PASS" if rep["ok"] else "FAIL", reproduce=rep'),
    ("repro: validity first", A, 'if r["verdict"] != "VALID":\n        return dict(verdict="FAIL", why=r["verdict"])',
     'if False:\n        return dict(verdict="FAIL", why=r["verdict"])'),
    ("boot-check: Gate C", A, 'return dict(config=cfg, verdict="PASS" if r.get("gate_c") == "PASS" else "FAIL",',
     'return dict(config=cfg, verdict="PASS",'),
    ("judge: repro gate first", A, 'rq1 = rate_verdict(res, sw, cmp_set) if gate["verdict"] == "PASS" else',
     'rq1 = rate_verdict(res, sw, cmp_set) if True else'),
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
