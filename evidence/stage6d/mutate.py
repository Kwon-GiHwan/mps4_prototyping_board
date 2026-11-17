"""Mutation test of the Stage 6D judge (host/analysis/stage6d.py). Each mutation neuters one rule, runs test_stage6d,
requires RED, and restores the file by sha256.

    python3 evidence/stage6d/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6d.py"
T = ["test_stage6d"]

MUTATIONS = [
    ("fam split", A, '    if r["exec_on"] != "NPU":\n        return "CPU_OR_SPLIT"', '    if r["exec_on"] == "CPU_OR_REMOVED":\n        return "CPU_OR_SPLIT"'),
    ("fam ao", A, 'if not r["n_mac_tflite"] or int(r["n_mac_tflite"]) == 0:', 'if not r["n_mac_tflite"]:'),
    ("fam df", A, 'return "DF1x1" if tr == "DepthFirst" else "PK1x1"', 'return "DF1x1"'),
    ("fam pk3 tr", A, 'if k == "3x3" and tr == "PartKernel":', 'if k == "3x3":'),
    ("fam pk1d k", A, "if kh == 1 and kw >= 7 and", "if kh == 1 and kw >= 5 and"),
    ("fam first cin", A, 'if int(r["cin"]) < 16:', 'if int(r["cin"]) <= 16:'),
    ("dw 128", A, "p = ho * wo * up16(cout) * k[0] * k[1] / 128", "p = ho * wo * cout * k[0] * k[1] / 128"),
    ("dw k", A, 'return p, k == [3, 3] and s == "1x1" and 8 <= cout <= 145', 'return p, s == "1x1" and 8 <= cout <= 145'),
    ("dw s", A, 'return p, k == [3, 3] and s == "1x1" and 8 <= cout <= 145', 'return p, k == [3, 3] and 8 <= cout <= 145'),
    ("dw lo", A, "and 8 <= cout <= 145", "and 7 <= cout <= 145"),
    ("dw hi", A, "and 8 <= cout <= 145", "and 8 <= cout <= 146"),
    ("fc pad", A, "p = ho * wo * up16(cin) * up16(cout) / 256", "p = ho * wo * cin * up16(cout) / 256"),
    ("fc rows", A, "return p, ho * wo == 1 and 95 <= cin", "return p, 95 <= cin"),
    ("fc cin hi", A, "95 <= cin <= 96 and", "95 <= cin <= 97 and"),
    ("fc cin lo", A, "95 <= cin <= 96 and", "94 <= cin <= 96 and"),
    ("fc cout", A, "287 <= cout <= 288", "286 <= cout <= 289"),
    ("pk3 768", A, "p = ho * wo * up16(cin) * cout * 9 / 768", "p = ho * wo * cin * cout * 9 / 768"),
    ("pk3 stride", A, 'return p, s == "1x1" and 16 <= cin <= 64 and cout % 16 == 0', 'return p, 16 <= cin <= 64 and cout % 16 == 0'),
    ("pk3 cin", A, "16 <= cin <= 64 and cout % 16", "1 <= cin <= 64 and cout % 16"),
    ("pk3 cin hi", A, "16 <= cin <= 64 and cout % 16", "16 <= cin <= 65 and cout % 16"),
    ("pk3 cout", A, "16 <= cin <= 64 and cout % 16 == 0", "16 <= cin <= 64"),
    ("lv unstable ops", A, 'if key in UNSTABLE_OPS or (hr and hr["measured_unstable_match"]):', 'if hr and hr["measured_unstable_match"]:'),
    ("lv unstable match", A, 'if key in UNSTABLE_OPS or (hr and hr["measured_unstable_match"]):', 'if key in UNSTABLE_OPS:'),
    ("lv exact first", A, '    if key in exact:\n        return LEVELS[2], exact[key], None\n    p, ok = rule(r, fam)\n    if ok:', '    p, ok = rule(r, fam)\n    if ok:\n        return LEVELS[3], p, None\n    if key in exact:'),
    ("lv class", A, "    if ok:\n        return LEVELS[3], p, None", "    if False:\n        return LEVELS[3], p, None"),
    ("lv df ext", A, 'return LEVELS[4], None, float(hr["h1uc"])', 'return LEVELS[4], None, None'),
    ("lv ext fams", A, 'if fam in ("DW", "FC", "PK3x3", "PK1x1", "PK1D", "FIRST_CONV", "DF1x1"):', 'if fam in ("DW", "FC", "PK3x3", "PK1D", "FIRST_CONV", "DF1x1"):'),
    ("lv unsupported", A, 'if fam in ("DW", "FC", "PK3x3", "PK1x1", "PK1D", "FIRST_CONV", "DF1x1"):', 'if True:'),
    ("f3 key", A, 'UNSTABLE_OPS = {("rnnoise_INT8", 46)}', 'UNSTABLE_OPS = {("rnnoise_INT8", 45)}'),
    ("exact f1", A, '("yolo-fastest_192_face_v4", 9): "s6c_f1_rep"', '("yolo-fastest_192_face_v4", 8): "s6c_f1_rep"'),
    ("exact f5", A, '("kws_micronet_m", 0): "s6c_f5_rep"', '("kws_micronet_m", 1): "s6c_f5_rep"'),
    ("cov predicted", A, "PREDICTED = LEVELS[1:4]", "PREDICTED = LEVELS[1:5]"),
    ("cov ext sum", A, 'if r["level"] == "EXTRAPOLATED" and r["p_ext"] is not None)', 'if r["level"] == "EXTRAPOLATED" and r["p_ext"] is not None and False)'),
    ("cov count ao", A, 'npu_ops = [r for r in rows if r["level"] != "CPU_OR_SPLIT"]', 'npu_ops = mac_ops'),
    ("cov evidence", A, 'any_evidence=any(r["level"] in LEVELS[1:5] for r in mac_ops)', 'any_evidence=any(r["level"] in LEVELS[1:4] for r in mac_ops)'),
    ("v full", A, "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.50", "COV_FULL, LO, HI, COV_PART = 0.89, 0.85, 1.05, 0.50"),
    ("v lo", A, "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.50", "COV_FULL, LO, HI, COV_PART = 0.90, 0.84, 1.05, 0.50"),
    ("v hi", A, "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.50", "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.06, 0.50"),
    ("v part", A, "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.50", "COV_FULL, LO, HI, COV_PART = 0.90, 0.85, 1.05, 0.49"),
    ("v over", A, "if p > HI * m or (c >= COV_FULL and p < LO * m):", "if c >= COV_FULL and p < LO * m:"),
    ("v under", A, "if p > HI * m or (c >= COV_FULL and p < LO * m):", "if p > HI * m:"),
    ("v qual ev", A, "if c < COV_PART and any_evidence:", "if c < COV_PART:"),
    ("v nom", A, "    if not m:\n        return \"INSUFFICIENT_EVIDENCE\"\n    if c >= COV_FULL", "    if c >= COV_FULL"),
    ("cancel min", A, "CANCEL_MIN = 0.10", "CANCEL_MIN = 0.11"),
    ("cancel and", A, "if over >= CANCEL_MIN and under >= CANCEL_MIN", "if over >= CANCEL_MIN or under >= CANCEL_MIN"),
    ("dir pk1d", A, '"PK1D": "OVER", "FIRST_CONV": "UNDER"', '"PK1D": "UNDER", "FIRST_CONV": "UNDER"'),
    ("dir fc", A, '"FC": "UNDER",', '"FC": "OVER",'),
    ("vela over", A, 'return "OVERESTIMATION" if ratio < 0.9 else', 'return "OVERESTIMATION" if ratio <= 0.9 else'),
    ("vela under", A, '"UNDERESTIMATION" if ratio > 1.1 else', '"UNDERESTIMATION" if ratio >= 1.1 else'),
    ("gap levels", A, 'GAP_LEVELS = ("INVALID_OR_UNSTABLE", "EXTRAPOLATED", "UNSUPPORTED")', 'GAP_LEVELS = ("EXTRAPOLATED", "UNSUPPORTED")'),
    ("gap fc disc", A, '("G_FC", ("FC",), True, False, 4)', '("G_FC", ("FC",), True, True, 4)'),
    ("gap df cost", A, '("G_DF_EXT", ("DF1x1",), True, True, 9)', '("G_DF_EXT", ("DF1x1",), True, True, 10)'),
    ("gap first fams", A, '("G_FIRST", ("FIRST_CONV", "PK3x3"), True, True, 4)', '("G_FIRST", ("FIRST_CONV",), True, True, 4)'),
    ("max cost", A, "MAX_COST = 9", "MAX_COST = 10"),
    ("elig cost", A, 'and t["cost"] <= MAX_COST]', ']'),
    ("elig ctrl", A, 'if t["controllable"] and t["discriminating"]', 'if t["discriminating"]'),
    ("impact max", A, "best = max(best, s / n if n else 0.0)", "best = best + (s / n if n else 0.0)"),
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
