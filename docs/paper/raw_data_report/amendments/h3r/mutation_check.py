"""Mutation check for h3r_analyze.py (CLAUDE.md: a check that cannot fail is worse than no check).
Each mutation neuters one comparison in a temporary copy of the analyzer; the unit suite must go RED for every one.
Writes mutation_log.md. The repository file is never modified (the copy lives in a temp dir; digest is asserted after)."""
import hashlib, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "h3r_analyze.py"
MUTATIONS = [
    ("RUN status", 'any(r["status"] != "SUCCESS" for r in a["runs"])', 'False'),
    ("RUN missing counter", 'if missing:', 'if False:'),
    ("REPS differ", 'if len({vec(r["measurement"]) for r in a["runs"]}) != 1:', 'if False:'),
    ("TA header", 'if not a["header_ok"] or any(a["header"].get(k) != req.get(k) for k in TA_KEYS):', 'if False:'),
    ("TA cache", 'if a["cache"] is not None and any(a["cache"].get(k) != req.get(k) for k in TA_KEYS):', 'if False:'),
    ("ARTIFACT identity", 'if len(shas) > 1:', 'if False:'),
    ("G1PRIME flag", 'if m is None or m.get("g1prime_pass") is not True:', 'if m is None:'),
    ("OUTPUT no verify", 'if v.get("status") == "SUCCESS" and v.get("dump_sha256"):', 'if True:'),
    ("OUTPUT incomplete", 'if bad:', 'if False:'),
    ("OUTPUT differ", 'if len({str(d) for d in dumps.values()}) > 1:', 'if False:'),
    ("OUTPUT bytes vs digest", 'return data\n', 'return v["dump_sha256"]\n'),
    ("EQUALIZED applied across MACs", 'if len(eq) == 2 and eq[256] != eq[512]:', 'if False:'),
    ("applied mask", '(v & TA_MASK[k.split("_", 1)[1]])', 'v'),
    ("PRESERVATION", 'if changed:', 'if False:'),
    ("ratio direction", 'r[(model, cond)] = cyc[(model, cond, 512)][key] / float(m[key])', 'r[(model, cond)] = float(m[key]) / cyc[(model, cond, 512)][key]'),
    ("SHAPE_EFFECT threshold", '"holds": spread[(op, cond)]["spread"] >= SHAPE_T', '"holds": spread[(op, cond)]["spread"] > SHAPE_T'),
    ("MSI factor", 'e["spread"] < MSI_FACTOR * b["spread"]', 'e["spread"] <= MSI_FACTOR * b["spread"]'),
    ("TYPE_DEPENDENT threshold", 'round(max(ms) - min(ms), 4) >= TYPE_T', 'round(max(ms) - min(ms), 4) > TYPE_T'),
    ("METRIC_DEPENDENT label", 'elif t["holds"] == a["holds"]:', 'elif True:'),
    ("refused arm excluded", 'ok.pop((cell, a), None)', 'pass'),
]


def main():
    before = hashlib.sha256(SRC.read_bytes()).hexdigest()
    src = SRC.read_text()
    rows = []
    for name, old, new in MUTATIONS:
        assert src.count(old) == 1, (name, src.count(old))
        d = Path(tempfile.mkdtemp())
        (d / "h3r_analyze.py").write_text(src.replace(old, new))
        shutil.copy(HERE / "test_h3r_analyze.py", d / "test_h3r_analyze.py")
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", "test_h3r_analyze"], cwd=d, capture_output=True, text=True)
        red = r.returncode != 0
        rows.append((name, old, new, "RED" if red else "SURVIVED"))
        shutil.rmtree(d, ignore_errors=True)
    after = hashlib.sha256(SRC.read_bytes()).hexdigest()
    assert before == after, "analyzer changed on disk"
    lines = ["# h3r_analyze.py mutation log", "", "analyzer sha256 (unchanged before/after): `%s`" % after, "",
             "| # | mutation | original | mutated | suite |", "|---|---|---|---|---|"]
    for i, (n, o, nw, res) in enumerate(rows, 1):
        lines.append("| %d | %s | `%s` | `%s` | %s |" % (i, n, o.replace("|", "\\|").replace("\n", "\\n"), nw.replace("|", "\\|").replace("\n", "\\n"), res))
    survived = [n for n, _, _, res in rows if res != "RED"]
    lines += ["", "survived: %s" % (survived or "none"), "",
              "note: an earlier `b[\"spread\"] > 0 and` guard in MEMORY_SHAPE_INTERACTION survived as an equivalent mutant "
              "(a spread is never negative, so it could not change any outcome); the redundant guard was removed instead of "
              "keeping an untestable branch."]
    (HERE / "mutation_log.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
