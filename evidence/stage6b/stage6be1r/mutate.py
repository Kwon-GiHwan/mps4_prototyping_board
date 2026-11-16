"""Mutation test of the Stage 6B-E1-R rules (host/analysis/stage6be1r.py). Each mutation neuters one rule, runs
test_stage6be1r, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6be1r/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be1r.py"
T = ["test_stage6be1r"]

MUTATIONS = [
    ('elig: E1 terms', A, 'ok, why = E.eligible(name, f, existing)', 'ok, why = True, []'),
    ('elig: cycle floor', A, 'if vela_cycles(f) < MIN_VELA_CYCLES:', 'if False:'),
    ('elig: floor inclusive', A, 'if vela_cycles(f) < MIN_VELA_CYCLES:', 'if vela_cycles(f) <= MIN_VELA_CYCLES:'),
    ('elig: Dram/Dram', A, '!= ("Dram", "Dram"):', '== ("never", "never"):'),
    ('existing: E1 six', A, 'return E.existing_shapes() | e1', 'return E.existing_shapes()'),
    ('cycles: all rows', A, 'for r in f.get("rows", []))', 'for r in f.get("rows", [])[:1])'),
    ('min_gap: differing only', A, 'for f in COMPETITORS.values() if f(c) != h), default=0)', 'for f in COMPETITORS.values()), default=0)'),
    ('rank: min_gap desc', A, 'return (-E.n_split(c), -min_gap(c),', 'return (-E.n_split(c), min_gap(c),'),
    ('rank: cycles desc', A, '-c["vela_cycles"], c["case"])', 'c["vela_cycles"], c["case"])'),
    ('rank: n_split before gap', A, 'return (-E.n_split(c), -min_gap(c),', 'return (-min_gap(c), -E.n_split(c),'),
    ('sig: chunk costs', A, 'c["ofm_block"], c["ifm_block"], costs)', 'c["ofm_block"], c["ifm_block"])'),
    ('sig: ublock', A, 'return (json.dumps(c["kernels"]), tuple(c["ublock"]),', 'return (json.dumps(c["kernels"]),'),
    ('select: exec de-dup', A, 'c["case"] != t["case"] and exec_sig(c) != exec_sig(t)', 'c["case"] != t["case"]'),
    ('select: extra Cin/Cout', A, 'not (extra and any(', 'not (False and any('),
    ('select: failed build', A, 'usable = lambda c: built.get(c["case"], True)', 'usable = lambda c: True'),
    ('select: DPU slot', A, 'if dpu_pw_vs(c, "D-U8") and free(c, True)), None)', 'if free(c, True)), None)'),
    ('select: status', A, 'status = "OK" if not missing and len(names) == N_SELECT else "NEEDS_REVISION"', 'status = "OK"'),
    ('select: need_build', A, 'need_build=[n for n in names if n not in built]', 'need_build=[]'),
    ('build: pack', A, 'if b.get("pack_rc") != 0 or not b.get("fits"):', 'if not b.get("fits"):'),
    ('build: fits', A, 'if b.get("pack_rc") != 0 or not b.get("fits"):', 'if b.get("pack_rc") != 0:'),
    ('build: deterministic', A, 'if not b.get("deterministic"):', 'if False:'),
    ('build: golden = ref', A, 'or b.get("golden_sha256") != b.get("ref_sha256"):', ':'),
    ('build: golden present', A, 'if not b.get("golden_sha256") or', 'if'),
    ('build: length', A, 'if (b.get("reference") or {}).get("n") != h * w * cout:', 'if False:'),
    ('dpu: contradiction', A, 'if any(not s["dpu"]["D-PW"]["match"] for v in split.values() for s in v):', 'if False:'),
    ('dpu: primary only', A, 'pv = [s for s in shapes if s["cls"] == "PRIMARY_VALID"]', 'pv = shapes'),
    ('dpu: both competitors', A, 'if all(split.values()) else', 'if any(split.values()) else'),
    ('dpu: split shapes only', A, 'for s in pv if s["dpu"]["D-PW"]["pred"] != s["dpu"][k]["pred"]]', 'for s in pv]'),
    ('npu: percent', A, 'else 100 * ra / a,', 'else ra / a,'),
    ('pred: D-U8 split', A, 'dpu_pw_vs_u8_split=p["dpu"]["D-PW"] != p["dpu"]["D-U8"]', 'dpu_pw_vs_u8_split=p["dpu"]["D-PW"] != p["dpu"]["D-U16"]'),
    ('pred: cycles', A, 'return dict(p, vela_cycles=c["vela_cycles"],', 'return dict(p, vela_cycles=0,'),
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
