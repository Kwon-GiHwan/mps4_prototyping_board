"""Mutation test of the Stage 4AO-E rules (CLAUDE.md: a check that cannot fail is worse than no check). Each mutation
neuters one rule in host/analysis/stage4aoe.py or host/board/run_driver_events.py, runs test_stage4aoe and test_driver_runner_sim, requires RED, and restores the file by sha256.
Writes mutation.txt beside this file; exits 1 if a mutation survives or a file does not come back byte-identical.

    python3 evidence/stage4aoe/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage4aoe.py"
T = ["test_stage4aoe", "test_driver_runner_sim"]
B = "host/board/run_driver_events.py"

# (id, file, old, new)
MUTATIONS = [
    ("TRM rate 16", A, "TRM_RATE = 16 ", "TRM_RATE = 15 "),
    ("conv rate 15.605", A, "CONV_RATE = 15.605 ", "CONV_RATE = 15.8 "),
    ("precision field", A, "return None if word is None else 8 << ((word >> 1) & 3)", "return None if word is None else 8"),
    ("pass source: CB", A, '("CB" if k["ifm_storage"] == CHAINED else "IFM")', '"IFM"'),
    ("pass destination: CB", A, 'dst = "CB" if k["ofm_storage"] == CHAINED else "OB"', 'dst = "OB"'),
    ("pass LUT bit", A, 'lut=bool((k["activation"] or 0) & 0x1F)', "lut=False"),
    ("pass elements", A, 'elements=g["h"] * g["w"] * g["c"]', 'elements=g["h"] * g["w"]'),
    ("TRM rate only 8-bit", A, 'return TRM_RATE if p["ofm_bits"] == 8 else None', "return TRM_RATE"),
    ("exactness", A, 'return "EXACT_EITHER" if aoe["reference"]["opt_vs_ref"] == 0 else "REF_ONLY"', 'return "EXACT_EITHER"'),
    ("select: cpu fallback", A, '(("cpu_fallback", bool(aoe["cpu_fallback"])),', '(("cpu_fallback", False),'),
    ("select: pack", A, '("pack_failed", aoe["pack_rc"] != 0),', '("pack_failed", False),'),
    ("select: path covered", A, '("path_not_covered", any(trm_rate(p) is None for p in ps))', '("path_not_covered", False)'),
    ("select: golden rule", A, 'if exactness(aoe) != "EXACT_EITHER":', "if False:"),
    ("logical elements: all passes", A, 'logical = sum(p["elements"] for p in ps)', 'logical = ps[-1]["elements"]'),
    ("rate class: nominal band", A, 'if abs(rate / TRM_RATE - 1) <= RATE_TOL:\n        return "NOMINAL_16"',
     'if False:\n        return "NOMINAL_16"'),
    ("rate class: conv band", A, 'if abs(rate / CONV_RATE - 1) <= RATE_TOL:\n        return "CONV_LIKE"',
     'if False:\n        return "CONV_LIKE"'),
    ("rate class: above", A, 'if rate > TRM_RATE:\n        return "ABOVE_NOMINAL"', 'if False:\n        return "ABOVE_NOMINAL"'),
    ("rate class: below vs between", A, 'return "BELOW_CONV" if rate < CONV_RATE else "BETWEEN"', 'return "BETWEEN"'),
    ("stability: AO range", A, "return r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao) and \\", "return True and \\"),
    ("stability: AO 50 floor", A, "return r <= max(AO_RANGE_ABS, AO_RANGE_REL * ao) and \\", "return r <= AO_RANGE_REL * ao and \\"),
    ("stability: pass A/B", A, 'abs(b - a) <= max(AB_REL * a, (m.get("A_35_range") or 0) + (m.get("B_35_range") or 0))', "True"),
    ("stability: missing values", A, "if None in (ao, r, a, b):\n        return False", "if False:\n        return False"),
    ("output: bytes vs golden", A, 'if not p.exists() or p.read_bytes() != golden:', 'if not p.exists():'),
    ("output: every row matched", A, 'all(r["output_match"] == "1" and r["ofm_mismatch_count"] == "0" for r in rows)', "True"),
    ("config: output exact", A, 'ok = runs_ok and ident["ok"] and wl_ok and out_ok', 'ok = runs_ok and ident["ok"] and wl_ok'),
    ("config: identity", A, 'ok = runs_ok and ident["ok"] and wl_ok and out_ok', 'ok = runs_ok and wl_ok and out_ok'),
    ("config: workload sha", A, 'ok = runs_ok and ident["ok"] and wl_ok and out_ok', 'ok = runs_ok and ident["ok"] and out_ok'),
    ("config: four RUNs", A, 'all(len(rs) == 4 and all(r["valid"] for r in rs) for rs in s["runs"].values())',
     'all(all(r["valid"] for r in rs) for rs in s["runs"].values())'),
    ("rate verdict: validity", A, 'if r.get("verdict") != "VALID":\n        return dict(verdict="INVALID" if',
     'if r.get("verdict") not in ("VALID", "INVALID"):\n        return dict(verdict="INVALID" if'),
    ("rate verdict: stability", A, 'if not r["stable"]:\n        return dict(verdict="MEASUREMENT_UNSTABLE")',
     'if False:\n        return dict(verdict="MEASUREMENT_UNSTABLE")'),
    ("rate verdict: logical elements", A, "rate = logical / r[\"metrics\"][\"A_64\"]", "rate = 55296 / r[\"metrics\"][\"A_64\"]"),
    ("prop: tolerance", A, 'verdict="PROPORTIONAL" if abs(ratio / 3 - 1) <= PROP_TOL else "NOT_PROPORTIONAL"',
     'verdict="PROPORTIONAL" if ratio / 3 - 1 <= PROP_TOL else "NOT_PROPORTIONAL"'),
    ("prop: validity", A, 'if a.get("verdict") != "VALID" or b.get("verdict") != "VALID":\n        return dict(verdict="INVALID")',
     'if False:\n        return dict(verdict="INVALID")'),
    ("prop: stability", A, 'if not (a["stable"] and b["stable"]):', "if False:"),
    ("runner: keep mismatch output", B, "                    keep_mismatch_output(link, raw[-1], d)\n", "                    pass\n"),
    ("runner: only with --outputs", B, 'if ctx["outputs"] and r.f["ofm_mismatch"] != 0:', 'if r.f["ofm_mismatch"] != 0:'),
    ("runner: mismatch file content", B, '(d / "output_mismatch.bin").write_bytes(data)', '(d / "output_mismatch.bin").write_bytes(data[1:])'),
    ("runner: CRC check", B, 'note["crc_ok"] = zlib.crc32(data) == run["output_crc32"]', 'note["crc_ok"] = True'),
    ("repro: reproduce()", A, 'verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep', 'verdict="PASS" if ao_ok else "FAIL", reproduce=rep'),
    ("repro: AO tolerance", A, 'verdict="PASS" if rep["ok"] and ao_ok else "FAIL", reproduce=rep', 'verdict="PASS" if rep["ok"] else "FAIL", reproduce=rep'),
    ("repro: validity first", A, 'if r["verdict"] != "VALID":\n        return dict(verdict="FAIL", why=r["verdict"])\n    now',
     'if False:\n        return dict(verdict="FAIL", why=r["verdict"])\n    now'),
    ("boot-check: gate", A, 'return dict(config=cfg, verdict="PASS" if r.get("gate_c") == "PASS" else "FAIL",',
     'return dict(config=cfg, verdict="PASS",'),
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
