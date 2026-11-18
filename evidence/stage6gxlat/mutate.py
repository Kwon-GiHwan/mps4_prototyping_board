"""Mutation test of the Stage 6G-X_LAT judge (host/analysis/stage6gxlat.py). Each mutation neuters one rule, runs test_stage6gxlat,
requires RED, and restores the file by sha256.

    python3 evidence/stage6gxlat/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6gxlat.py"
T = ["test_stage6gxlat"]

MUTATIONS = [
    ("boot 505", A, '("x3_kws_B2", 250): 505', '("x3_kws_B2", 250): 506'),
    ("boot 516", A, '("x3_ad_B4", 250): 516', '("x3_ad_B4", 250): 515'),
    ("img 250", A, 'bram_sha256="4f5f54aa2e5d49054769bd25897d6c3dcb55149510e0de4a3faea43fc2991d15"', 'bram_sha256=X.IMAGE["bram_sha256"]'),
    ("img 1000", A, 'bram_sha256="7004c53022901a0cc9d9b46e53cf2066bdb0b666ec1856b203d6b3e8fc775e47"', 'bram_sha256="4f5f54aa2e5d49054769bd25897d6c3dcb55149510e0de4a3faea43fc2991d15"'),
    ("id lat", A, "        X.EXT_RLATENCY = lat\n", "        X.EXT_RLATENCY = 500\n"),
    ("id boot", A, "        X.BOOT = {key: BOOTS[(key, lat)]}\n", "        X.BOOT = dict(X.BOOT)\n"),
    ("id restore", A, "        X.IMAGE, X.BOOT, X.EXT_RLATENCY, X.KEY_ROOT = saved", "        pass"),
    ("id b0 root", A, 'X.KEY_ROOT = {"x3_kws_B0": "x3b", "x3_ad_B0": "x3c", key: f"l{lat}"}', 'X.KEY_ROOT = {"x3_kws_B0": "x3b", "x3_ad_B0": "x3b", key: f"l{lat}"}'),
    ("caps lat", A, "return dict(caps500, ta_ext_rlatency=lat)", "return dict(caps500)"),
    ("comp l500", A, 'and e["L500"]["cms_sha256"] == e["base"]["cms_sha256"]', ''),
    ("comp lat", A, 'return e[f"L{lat}"]["cms_sha256"] == e["base"]["cms_sha256"] and', 'return True and'),
    ("vg share", A, 'if term(r) == "DRAM AC") / oc) if oc else 0.0)', 'if term(r) != "NPU") / oc) if oc else 0.0)'),
    ("tol cap", A, "return max(cap, ra + rb, REL_FLOOR * max(ba, bb))", "return max(ra + rb, REL_FLOOR * max(ba, bb))"),
    ("tol range", A, "return max(cap, ra + rb, REL_FLOOR * max(ba, bb))", "return max(cap, REL_FLOOR * max(ba, bb))"),
    ("tol floor", A, "return max(cap, ra + rb, REL_FLOOR * max(ba, bb))", "return max(cap, ra + rb)"),
    ("resp abs", A, 'return "SENSITIVE" if abs(db) > tol else', 'return "SENSITIVE" if db > tol else'),
    ("resp ge", A, 'return "SENSITIVE" if abs(db) > tol else', 'return "SENSITIVE" if abs(db) >= tol else'),
    ("fid ident", A, "if tol > IDENT * max(abs(dv), abs(db)):", "if tol > IDENT * abs(dv):"),
    ("fid ident k", A, "IDENT = 0.5 ", "IDENT = 0.6 "),
    ("fid mag", A, "MAG_TOL = 0.15 ", "MAG_TOL = 0.16 "),
    ("fid mag tol", A, "if abs(db - dv) <= MAG_TOL * abs(dv) + tol:", "if abs(db - dv) <= MAG_TOL * abs(dv):"),
    ("fid dir sign", A, "and (db > 0) == (dv > 0):", ":"),
    ("fid dir db", A, "if abs(db) > tol and abs(dv) > tol and", "if abs(dv) > tol and"),
    ("fid dir dv", A, "if abs(db) > tol and abs(dv) > tol and", "if abs(db) > tol and"),
    ("ov incons", A, '    if "INCONSISTENT" in t:\n        return "INCONSISTENT"\n', ''),
    ("ov empty", A, '    if not t:\n        return "INSUFFICIENT_EVIDENCE"\n', '    if not per_group:\n        return "INSUFFICIENT_EVIDENCE"\n'),
    ("ov all", A, 'if all(v == "DIRECTION_AND_MAGNITUDE_CONSISTENT" for v in t):', 'if "DIRECTION_AND_MAGNITUDE_CONSISTENT" in t:'),
    ("inv tol", A, "INV_TOL = 0.01 ", "INV_TOL = 0.02 "),
    ("inv none", A, "return all(v is not None and abs(v - ref) <= INV_TOL * ref for v in vals.values())", "return all(abs((v or ref) - ref) <= INV_TOL * ref for v in vals.values())"),
    ("mech share", A, "MECH_SHARE = 0.5 ", "MECH_SHARE = 0.6 "),
    ("mech sign", A, "and (e[c] > 0) == (g[\"db\"] > 0) and", "and"),
    ("mech events", A, "MECH_EVENTS = (81, 55, 387)", "MECH_EVENTS = (81, 387)"),
    ("mech all", A, "    ok = all(any(", "    ok = any(any("),
    ("l2 share", A, "DRAM_SHARE = 0.5 ", "DRAM_SHARE = 0.51 "),
    ("l2 strict", A, 'return "SUPPORTED" if min(d) > max(n) else "REFUTED"', 'return "SUPPORTED" if max(d) > max(n) else "REFUTED"'),
    ("l2 empty", A, "    if not d or not n:\n", "    if not d and not n:\n"),
    ("meas stop", A, "if any(s in X.STOP for s in statuses) or not any(s == \"VALID\" for s in statuses):", "if not any(s == \"VALID\" for s in statuses):"),
    ("meas none", A, "if any(s in X.STOP for s in statuses) or not any(s == \"VALID\" for s in statuses):", "if any(s in X.STOP for s in statuses):"),
    ("j seg", A, "seg = (250, 1000) if comp[250] and comp[1000] else (250, 500) if comp[250] else None", "seg = (250, 1000) if comp[250] else None"),
    ("j db", A, "db = b[1000][0] - b[250][0]", "db = b[1000][0] - b[500][0]"),
    ("j tol", A, "tol = tol_of(cap, b[250][1], b[1000][1], b[250][0], b[1000][0])", "tol = tol_of(cap, b[250][1], b[250][1], b[250][0], b[1000][0])"),
    ("j inv conf", A, 'response=response(db, tol) if inv else "CONFOUNDED"', 'response=response(db, tol)'),
    ("j inv skip", A, "                if inv:\n                    lo, hi", "                if True:\n                    lo, hi"),
    ("j dpu", A, "inv = invariant(macs, macs[500]) and invariant(dpus, dpus[500])", "inv = invariant(macs, macs[500])"),
    ("j valid all", A, "            if all(ok.values()):", "            if ok[250] and ok[1000]:"),
    ("j slope", A, "slope_250_500=(b[500][0] - b[250][0]) / 250,", "slope_250_500=(b[500][0] - b[250][0]) / 500,"),
    ("j err", A, "prediction_error_delta=(dbs - dvs) if seg else None", "prediction_error_delta=(dvs - dbs) if seg else None"),
    ("j sens", A, '                    if e["response"] == "SENSITIVE":', '                    if True:'),
    ("j traffic", A, "for t in TRAFFIC if med(by[500], 2, t)[0])", "for t in TRAFFIC[:3] if med(by[500], 2, t)[0])"),
    ("j overall resp", A, 'latency_response_overall="SENSITIVE" if "SENSITIVE" in resp else (', 'latency_response_overall="SENSITIVE" if resp.count("SENSITIVE") > 6 else ('),
    ("j inv empty", A, 'compute_invariance="INSUFFICIENT_EVIDENCE" if not inv_all else ("SUPPORTED" if all(inv_all) else "REFUTED")', 'compute_invariance="INSUFFICIENT_EVIDENCE" if not inv_all else ("SUPPORTED" if any(inv_all) else "REFUTED")'),
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
