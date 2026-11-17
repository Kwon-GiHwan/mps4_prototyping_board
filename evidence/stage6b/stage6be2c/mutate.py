"""Mutation test of the Stage 6B-E2C comparison classes, register categories and verdict
(host/analysis/stage6be2c.py, host/lib/cms_full.py). Each mutation neuters one rule, runs test_stage6be2c, requires RED, and restores the file by
sha256.

    python3 evidence/stage6b/stage6be2c/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2c.py"
L = "host/lib/cms_full.py"
T = ["test_stage6be2c"]

MUTATIONS = [
    ('cat: address base', L, 'ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\\d*|.*_REGION|DMA0_SRC|DMA0_DST)$")', 'ADDRESS = re.compile(r"^NPU_SET_(.*_REGION|DMA0_SRC|DMA0_DST)$")'),
    ('cat: address region', L, 'ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\\d*|.*_REGION|DMA0_SRC|DMA0_DST)$")', 'ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\\d*|DMA0_SRC|DMA0_DST)$")'),
    ('cat: address dma', L, 'ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\\d*|.*_REGION|DMA0_SRC|DMA0_DST)$")', 'ADDRESS = re.compile(r"^NPU_SET_(.*_BASE\\d*|.*_REGION)$")'),
    ('cat: layout precision', L, '|IFM2?_PRECISION|OFM_PRECISION)$")', ')$")'),
    ('cat: layout stride', L, 'LAYOUT = re.compile(r"^NPU_SET_(IFM2?_STRIDE_[XYC]|OFM_STRIDE_[XYC]|', 'LAYOUT = re.compile(r"^NPU_SET_('),
    ('cat: dependency', L, 'DEPENDENCY = {"NPU_SET_BLOCKDEP"}', 'DEPENDENCY = set()'),
    ('dec: cmd1 payload', L, 'reg[CMD1.get(op, f"CMD1_{op}")] = (word >> 16) << 32 | int.from_bytes(', 'reg[CMD1.get(op, f"CMD1_{op}")] = int.from_bytes('),
    ('dec: dma reset', L, '            dmas = []\n        elif CMD0', '        elif CMD0'),
    ('dec: state copy', L, 'regs=dict(reg), dma=dmas', 'regs=reg, dma=dmas'),
    ('diff: missing', L, '        if a.get(n) != b.get(n):', '        if n in a and n in b and a[n] != b[n]:'),
    ('cmp: weights digest required', A, 'and all(v["const_sha256"] for v in x.values())', ''),
    ('cmp: weights key', A, 'key = lambda s: {w: (v["length"], v["const_sha256"]) for w, v in s.items()}', 'key = lambda s: {w: v["length"] for w, v in s.items()}'),
    ('placement: address only', A, 'or set(c["diff"]) - {"ADDRESS"}:', 'or set(c["diff"]) - {"ADDRESS", "DEPENDENCY"}:'),
    ('placement: ops', A, 'if not (c["same_n_conv"] and c["weights_equal"] and c["same_ops"]) or', 'if not (c["same_n_conv"] and c["weights_equal"]) or'),
    ('placement: weights', A, 'if not (c["same_n_conv"] and c["weights_equal"] and c["same_ops"]) or', 'if not (c["same_n_conv"] and c["same_ops"]) or'),
    ('placement: memory', A, 'return "PLACEMENT_ONLY" if (mem_a, mem_b) == want else "NOT_CONTROLLED"', 'return "PLACEMENT_ONLY"'),
    ('placement: unavailable', A, '    if mem_a is None or mem_b is None:\n        return "UNAVAILABLE"\n    if not (c["same_n_conv"] and c["weights_equal"] and c["same_ops"])', '    if not (c["same_n_conv"] and c["weights_equal"] and c["same_ops"])'),
    ('wrapper: compute', A, 'or "COMPUTE" in c["diff"] or mem_a != mem_b:', 'or mem_a != mem_b:'),
    ('wrapper: memory', A, 'or "COMPUTE" in c["diff"] or mem_a != mem_b:', 'or "COMPUTE" in c["diff"]:'),
    ('wrapper: weights', A, '    if not (c["same_n_conv"] and c["weights_equal"]) or "COMPUTE"', '    if not c["same_n_conv"] or "COMPUTE"'),
    ('wrapper: layout', A, 'return "WRAPPER_PLUS_LAYOUT" if "LAYOUT" in c["diff"] else "WRAPPER_ONLY"', 'return "WRAPPER_ONLY"'),
    ('wrapper: unavailable', A, '    if mem_a is None or mem_b is None:\n        return "UNAVAILABLE"\n    if not (c["same_n_conv"] and c["weights_equal"]) or', '    if not (c["same_n_conv"] and c["weights_equal"]) or'),
    ('eoc: keys', A, 'keys = ("cms_sha256", "const_sha256", "arena_size", "fast_size", "inputs", "outputs")', 'keys = ("cms_sha256",)'),
    ('eoc: ok', A, 'return bool(l500.get("ok") and l1000.get("ok")) and all(', 'return all('),
    ('first_dram: memory', A, 'if f.get("ok") and conv_memory(f) == ("Dram", "Dram"):', 'if f.get("ok"):'),
    ('first_dram: ok', A, 'if f.get("ok") and conv_memory(f) == ("Dram", "Dram"):', 'if conv_memory(f) == ("Dram", "Dram"):'),
    ('conv_memory: single', A, 'return (rows[0]["ifm_memory"], rows[0]["ofm_memory"]) if len(rows) == 1 else None', 'return (rows[0]["ofm_memory"], rows[0]["ifm_memory"]) if rows else None'),
    ('h1uc: ublock', A, 'ub = [int(m[0][f"ofm_ublock_{x}"]) for x in "hwc"]', 'ub = [2, 2, 16]'),
    ('verdict: invalid', A, '    if invalid:\n        return "INVALID"', '    if False:\n        return "INVALID"'),
    ('verdict: numeric', A, 'if any(c["cls"] in CONTROLLED and c["numeric_verified"] for', 'if any(c["cls"] in CONTROLLED for'),
    ('verdict: controlled', A, 'if any(c["cls"] in CONTROLLED and c["numeric_verified"] for', 'if any(c["numeric_verified"] for'),
    ('verdict: partial', A, 'if any(c["cls"] not in ("UNAVAILABLE", "NOT_CONTROLLED") for c in comps.values()):', 'if any(c["cls"] != "UNAVAILABLE" for c in comps.values()):'),
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
