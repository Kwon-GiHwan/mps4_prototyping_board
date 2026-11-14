"""Mutation test of the Stage 4K rules (CLAUDE.md: a check that cannot fail is worse than no check). Each mutation
neuters one rule in host/analysis/stage4k.py (or the generator check it relies on), runs test_stage4k, requires RED,
and restores the file by sha256. Writes mutation.txt beside this file; exits 1 if a mutation survives or a file does
not come back byte-identical.

    python3 evidence/stage4k/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage4k.py"
T = ["test_stage4k"]

# (id, file, old, new)
MUTATIONS = [
    ("valid-tap MACs: padded taps excluded", A, "t = (k // 2) * (k // 2 + 1)", "t = 0"),
    ("c16 rounding", A, "c16 = math.ceil(cin / 16) * 16", "c16 = cin"),
    ("hypotheses: both rates", A, "for r in (384, 768)", "for r in (384,)"),
    ("verdict: output / validity", A, "if not (valid and out_ok) or len(macs_per_run) != 4:", "if len(macs_per_run) != 4:"),
    ("verdict: four RUNs", A, "if not (valid and out_ok) or len(macs_per_run) != 4:", "if not (valid and out_ok):"),
    ("verdict: unstable RUNs", A, "if len(set(macs_per_run)) != 1:\n        return \"MEASUREMENT_UNSTABLE\"", "if False:\n        return \"MEASUREMENT_UNSTABLE\""),
    ("repro: MAC_ACTIVE", A, "checks = dict(mac=len(set(now[\"mac_active\"])) == 1 and set(now[\"mac_active\"]) == set(ref[\"mac_active\"]),",
     "checks = dict(mac=True,"),
    ("repro: output sha256", A, "output=now[\"output_sha256\"] is not None and now[\"output_sha256\"] == ref[\"output_sha256\"],", "output=True,"),
    ("repro: constant counters", A, "constant_counters=not diff,", "constant_counters=True,"),
    ("repro: NPU_ACTIVE tolerance", A, "npu_active=abs(na[\"A_35\"] - nb[\"A_35\"]) <= t)", "npu_active=True)"),
    ("repro: 1 % floor", A, "t = max(FLOOR * nb[\"A_35\"], nb[\"A_35_range\"] or 0, na[\"A_35_range\"] or 0)",
     "t = max(0.5 * nb[\"A_35\"], nb[\"A_35_range\"] or 0, na[\"A_35_range\"] or 0)"),
    ("repro gate: requires PASS_EXACT", A, "if rep[\"ok\"] and r[\"output\"][\"verdict\"] == \"PASS_EXACT\" else", "if rep[\"ok\"] else"),
    ("repro gate: stops interpretation", A, "    if gate[\"verdict\"] != \"PASS\":\n        for c in ORDER:", "    if False:\n        for c in ORDER:"),
    ("repro gate: RQ withheld", A, "    ok = gate[\"verdict\"] == \"PASS\"\n", "    ok = True\n"),
    ("CLI exit code (repro-gate, boot-check)", A, "return 0 if r[\"verdict\"] == \"PASS\" else 1", "return 0"),
    ("other 1x1 reproduction", A, "repro[c] = dict(verdict=\"REPRODUCED\" if all(x[\"ok\"] for x in reps.values()) else",
     "repro[c] = dict(verdict=\"REPRODUCED\" if True else"),
    ("exact(): unstable RUNs", A, "return v[0] if len(v) == 4 and len(set(v)) == 1 and", "return v[0] if len(v) == 4 and"),
    ("granularity: ceil16 rule", A, "c16 = all(m[c] * 16 == m[16] * math.ceil(c / 16) * 16 for c in m)", "c16 = False"),
    ("granularity: proportional rule", A, "prop = all(m[c] * 16 == m[16] * c for c in m)", "prop = False"),
    ("RQ1: comparability label", A, "same_trav = sa[\"traversal\"] == sb[\"traversal\"]", "same_trav = True"),
    ("RQ1: rate comparison", A, "verdict=\"SAME_RATE\" if r1 == r3 else", "verdict=\"SAME_RATE\" if True else"),
    ("RQ4: pass B opposite sign", A, "return dict(verdict=\"UNRESOLVED\" if opp else pa[\"verdict\"], pass_a=pa, directions_opposite=opp,",
     "return dict(verdict=pa[\"verdict\"], pass_a=pa, directions_opposite=opp,"),
    ("static: schedule switch detection", A, "zip(cfgs, cfgs[1:], sch, sch[1:]) if x != y]", "zip(cfgs, cfgs[1:], sch, sch[1:]) if False]"),
    ("static: 1x1 SAME control compares bytes", A, "same = lambda a, b: (wl / a).read_bytes() == (wl / b).read_bytes()",
     "same = lambda a, b: True"),
    ("boot-check: Gate C", A, "return dict(config=cfg, verdict=\"PASS\" if r.get(\"gate_c\") == \"PASS\" else \"FAIL\",",
     "return dict(config=cfg, verdict=\"PASS\","),
    ("Gate C: PASS_EXACT only", A, "out_ok = oc[\"verdict\"] == \"PASS_EXACT\"",
     "out_ok = oc[\"verdict\"] in (\"PASS_EXACT\", \"PASS_TOLERANCE\")"),
    ("Gate C: identity", A, "and all(len(rs) == 4 for rs in s[\"runs\"].values()) and ident[\"ok\"]",
     "and all(len(rs) == 4 for rs in s[\"runs\"].values())"),
    ("identity: model length", A, "model_len=bool(recs) and all(r.get(\"model_len\") == model_len for r in recs),", "model_len=True,"),
    ("identity: placement", A, "placement=all(r.get(\"placement\") == 0 for r in recs),", "placement=True,"),
    ("identity: REGIONCFG/QCONFIG", A, "regioncfg=all(r.get(\"regioncfg_irq\") == REGIONCFG_DDR and r.get(\"qconfig_irq\") == QCONFIG for r in recs),", "regioncfg=True,"),
    ("identity: one IRQ", A, "irq=all(r.get(\"irq_count\") == 1 for r in recs),", "irq=True,"),
    ("identity: schema", A, "schema=all(r.get(\"schema\") == 4 for r in recs),", "schema=True,"),
    ("identity: one CRC incl. warm-up", A, "one_crc=len({x.get(\"output_crc32\") for x in raw}) == 1,", "one_crc=True,"),
    ("identity: capabilities", A, "capabilities=caps == ref)", "capabilities=True)"),
    ("predict: MACs = definition", A, "        assert st[\"n_mac\"] == macs(k, cin)[\"nominal\"], c       # the compiled model's MACs = the definition\n", ""),
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
