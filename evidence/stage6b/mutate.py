"""Mutation test of the Stage 6B rules (evidence/stage6b/rules.md). Each mutation neuters one rule in
host/analysis/stage6b.py, runs test_stage6b, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
A = "host/analysis/stage6b.py"
T = ["test_stage6b"]

MUTATIONS = [
    ("target: DepthFirst only", A, 'and r["traversal"] == "DepthFirst" and int(r["mac_count"] or 0) > 0', 'and int(r["mac_count"] or 0) > 0'),
    ("target: INT8 output", A, 'and int(r["mac_count"] or 0) > 0 and int8_out(r, dt)]', 'and int(r["mac_count"] or 0) > 0]'),
    ("target: NPU only", A, 'return [r for r in rows if r["cpu"] == "0" and r["npu_op"]', 'return [r for r in rows if r["npu_op"]'),
    ("group: block in key", A, '"npu_ofm_hwc", "ifm_block", "ofm_block", "ofm_ublock",', '"npu_ofm_hwc", "ifm_block", "ofm_ublock",'),
    ("rep: largest MAC", A, 'key=lambda r: (-int(r["mac_count"]), r["model"]', 'key=lambda r: (int(r["mac_count"]), r["model"]'),
    ("top-N", A, "TOP_N = 5", "TOP_N = 6"),
    ("class: shape -> NOT", A, "if feas or shape or not row:", "if feas or not row:"),
    ("class: feasibility -> NOT", A, "if feas or shape or not row:", "if shape or not row:"),
    ("class: placement compared", A, "diffs = [k for k in EXEC + PLACE + WEIGHT", "diffs = [k for k in EXEC + WEIGHT"),
    ("class: weight compared", A, "diffs = [k for k in EXEC + PLACE + WEIGHT", "diffs = [k for k in EXEC + PLACE"),
    ("best form: plain on tie", A, 'key=lambda f: (RANK[forms[f]["cls"]], f != "F_PLAIN"))', 'key=lambda f: (RANK[forms[f]["cls"]], f == "F_PLAIN"))'),
    ("select: EXACT only", A, 'elig = [g for g in cands if cls[g["group"]]["cls"] == "EXACT_STATIC_MATCH"]', 'elig = [g for g in cands if cls[g["group"]]["cls"] != "NOT_REPRODUCIBLE"]'),
    ("select: model floor", A, 'out.append(dict(group=mine[0]["group"], reason=f"model_floor:{m}")); picked.add(mine[0]["group"])', 'pass'),
    ("select: cap", A, "MAX_SELECT = 10", "MAX_SELECT = 11"),
    ("score: normalised", A, 'return sum(v / tot[m] for m, v in g["macs"].items())', 'return sum(g["macs"].values())'),
    ("tie: measured Cin", A, "0 if MEASURED_CIN[0] <= cin_of(g) <= MEASURED_CIN[1] else 1,", "0,"),
    ("coverage: calibrated not recounted", A, 'new = [r for r in sel_rows if (m, r["scheduled_id"]) not in calibrated]', 'new = sel_rows'),
    ("coverage: partial not counted", A, 'selected_share=share(sel_rows),', 'selected_share=sum(by_cls.values()),'),
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
