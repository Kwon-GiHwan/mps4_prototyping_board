"""Mutation test of the Stage 6B-E2A source formulas, forms, audit, hypothesis and verdict rules
(host/analysis/stage6be2a.py). Each mutation neuters one rule, runs test_stage6be2a, requires RED, and restores the file by
sha256.

    python3 evidence/stage6b/stage6be2a/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2a.py"
T = ["test_stage6be2a"]

MUTATIONS = [
    # thresholds
    ('FORM_TOL', A, 'FORM_TOL = 0.15 ', 'FORM_TOL = 0.17 '),
    ('B_MIN', A, 'B_MIN = 5 ', 'B_MIN = 4 '),
    ('M1C_MIN', A, 'M1C_MIN = 0.90 ', 'M1C_MIN = 0.0 '),
    ('BURST_TOL', A, 'BURST_TOL = 0.10 ', 'BURST_TOL = 0.0 '),
    ('H1_DIFF', A, 'H1_DIFF = 0.10 ', 'H1_DIFF = 0.5 '),
    ('H3 thresholds hi', A, 'H3_HI, H3_LO, H3_CV = 0.8, 0.2, 0.25', 'H3_HI, H3_LO, H3_CV = 1.1, 0.2, 0.25'),
    ('H3 thresholds lo', A, 'H3_HI, H3_LO, H3_CV = 0.8, 0.2, 0.25', 'H3_HI, H3_LO, H3_CV = 0.8, 0.5, 0.25'),
    ('H3 thresholds cv', A, 'H3_HI, H3_LO, H3_CV = 0.8, 0.2, 0.25', 'H3_HI, H3_LO, H3_CV = 0.8, 0.2, 1e9'),
    ('H4_DIFF', A, 'H4_DIFF = 0.25', 'H4_DIFF = 0.35'),
    ('RB weight', A, 'Weight=416,', 'Weight=256,'),
    ('RB scale', A, 'Scale=16)', 'Scale=256)'),
    # ChannelBW
    ('bw: ports in bandwidth', A, 'bandwidth = mem["clock_scale"] * 16 * mem["ports_used"]', 'bandwidth = mem["clock_scale"] * 16'),
    ('bw: write no RB limit', A, 'out, lat, rb = mem["max_writes"], mem["write_latency"], math.inf', 'out, lat, rb = mem["max_writes"], mem["write_latency"], RB_U85_1024["IFM"] / burst_words'),
    ('bw: read latency', A, 'out, lat, rb = mem["max_reads"], mem["read_latency"]', 'out, lat, rb = mem["max_reads"], mem["write_latency"]'),
    ('bw: 0.8 outstanding', A, 'util = min(rb, out * mem["ports_used"] * 0.8)', 'util = min(rb, out * mem["ports_used"])'),
    ('bw: 0.8 channel', A, 'mem["burst_length"] * util / lat * 0.8)', 'mem["burst_length"] * util / lat)'),
    ('bw: min with bandwidth', A, 'return min(bandwidth, mem["burst_length"]', 'return max(bandwidth, mem["burst_length"]'),
    # MAC cycles
    ('mac: int depth division', A, 'ib_c // 8 * nu[0] * nu[1]', 'ib_c / 8 * nu[0] * nu[1]'),
    ('mac: writeback floor', A, 'max(32 * ub[2] // 8,', 'max(0,'),
    ('mac: delay', A, 'delay = 2 if nu[0] * nu[1] == 1 and nu[2] == 1 else 0', 'delay = 0'),
    ('mac: chunks', A, 'per_blk = (cyc + delay) * math.ceil(ifm[2] / ib_c)', 'per_blk = (cyc + delay)'),
    ('mac: fractional blocks', A, 'n = math.prod(math.ceil(o / u) for o, u in zip(ofm, ub)) / math.prod(nu)', 'n = math.ceil(math.prod(math.ceil(o / u) for o, u in zip(ofm, ub)) / math.prod(nu)) + 1'),
    ('mac: AO max', A, 'ao = max(math.ceil(ao_per_elem * math.prod(ob)), 10 * ob[2] * const_latency / 256)', 'ao = min(math.ceil(ao_per_elem * math.prod(ob)), 10 * ob[2] * const_latency / 256)'),
    ('mac: bias term', A, '10 * ob[2] * const_latency / 256)', '0)'),
    ('mac: clip block', A, 'ob = [min(a, b) for a, b in zip(ofm, ofm_blk)]', 'ob = list(ofm_blk)'),
    # forms
    ('F0', A, 'f = dict(F0=sum(max(o["npu"], o["sram"], o["dram"]) for o in ops),', 'f = dict(F0=sum(max(o["npu"], o["dram"]) for o in ops),'),
    ('F1', A, 'F1=sum(o["npu"] + max(o["sram"], o["dram"]) for o in ops),', 'F1=sum(max(o["npu"], o["sram"], o["dram"]) for o in ops),'),
    ('F2', A, 'F2=sum(max(o["npu"], o["sram"] + o["dram"]) for o in ops),', 'F2=sum(max(o["npu"], o["sram"], o["dram"]) for o in ops),'),
    ('F3', A, 'F3=sum(o["npu"] + o["sram"] + o["dram"] for o in ops))', 'F3=sum(o["npu"] + o["dram"] for o in ops))'),
    ('F4 ratios', A, 'max(o["npu"], o["sram"] * r_s, o["dram"] * r_d) for o in ops)', 'max(o["npu"], o["sram"], o["dram"]) for o in ops)'),
    ('rel_err zero', A, 'return None if est in (None, 0) else', 'return None if est is None else'),
    # M2
    ('m2: B count', A, 'ok_b = len(b) >= B_MIN and all(', 'ok_b = all('),
    ('m2: B all', A, 'and all(abs(e) <= FORM_TOL for e in b)', 'and any(abs(e) <= FORM_TOL for e in b)'),
    ('m2: A median', A, 'ok_a = bool(a) and statistics.median(abs(e) for e in a) <= FORM_TOL', 'ok_a = bool(a)'),
    ('m2: both', A, 'holds=ok_b and ok_a)', 'holds=ok_b)'),
    # audit
    ('axi: reads m1', A, 'max_reads=(word & 0x3F) + 1,', 'max_reads=(word & 0x3F),'),
    ('axi: writes field', A, 'max_writes=((word >> 8) & 0x1F) + 1,', 'max_writes=((word >> 8) & 0x3F) + 1,'),
    ('outstanding: 0 = infinite', A, 'return axi if ta == 0 else min(ta, axi)', 'return min(ta, axi)'),
    ('c4: word sizes', A, 'for w in (8, 16) for k in (1, 2)]', 'for w in (16,) for k in (1, 2)]'),
    ('c4: port coverage', A, 'for w in (8, 16) for k in (1, 2)]', 'for w in (8, 16) for k in (1,)]'),
    ('c4: MATCH rule', A, '    if all(c >= vela_bw for c in caps):\n        return "MATCH"', '    if any(c >= vela_bw for c in caps):\n        return "MATCH"'),
    ('c5: all above', A, 'if bursts and all(b > vela_burst * (1 + BURST_TOL) for b in bursts):', 'if bursts and any(b > vela_burst * (1 + BURST_TOL) for b in bursts):'),
    ('c5: empty', A, '    if bursts and all(b <= vela_burst', '    if all(b <= vela_burst'),
    ('audit: latency', A, 'same = caps[f"ta_{ta}_rlatency"] == v["read_latency"] and caps[f"ta_{ta}_wlatency"] == v["write_latency"]', 'same = True'),
    ('audit: outstanding', A, '"MATCH" if (er, ew) == (v["max_reads"], v["max_writes"]) else "MISMATCH_VERIFIED")', '"MATCH")'),
    ('audit: ports log2', A, 'ns, ne = 2 ** ((cfg >> 8) & 0x3), 2 ** ((cfg >> 10) & 0x1)', 'ns, ne = 2, 2'),
    ('audit: sram size', A, '"MATCH" if caps["fast_size"] == ARENA_CACHE else "MISMATCH_VERIFIED")', '"MATCH")'),
    ('audit: burst port map', A, 'for key, mem in (("sram_read", "Sram"), ("sram_write", "Sram"), ("ext_read", "Dram")):', 'for key, mem in (("sram_read", "Sram"), ("sram_write", "Dram"), ("ext_read", "Dram")):'),
    # hypotheses
    ('spearman ties', A, '            r[order[k]] = (i + j) / 2 + 1', '            r[order[k]] = k + 1'),
    ('spearman n', A, '    if len(x) < 3:\n        return None', '    if len(x) < 2:\n        return None'),
    ('h1 support', A, 'if f4_abs and statistics.median(f4_abs) <= FORM_TOL:', 'if False:'),
    ('h1 bytes all', A, 'if board_le_vela_bytes and all(board_le_vela_bytes) and', 'if board_le_vela_bytes and'),
    ('h1 diff', A, 'abs(statistics.median(f4_abs) - statistics.median(f0_abs)) <= H1_DIFF:', 'True:'),
    ('h2 support', A, 'if any(m2_rows[f]["holds"] for f in ("F1", "F2", "F3")):', 'if any(m2_rows[f]["holds"] for f in ("F1", "F2", "F3", "F4")):'),
    ('h2 contradict', A, 'if all(sum(over[f][g]) * 2 >= len(over[f][g]) > 0', 'if any(sum(over[f][g]) * 2 >= len(over[f][g]) > 0'),
    ('h3 cv', A, 'return "SUPPORTED_PATTERN" if rho <= H3_LO and cv <= H3_CV else', 'return "SUPPORTED_PATTERN" if rho <= H3_LO else'),
    ('h3 combine', A, 'return a if a == b else "NOT_DISTINGUISHABLE"', 'return a'),
    ('h4 pattern', A, 'pattern_difference=abs(med_a - med_b) > H4_DIFF)', 'pattern_difference=True)'),
    # verdict
    ('verdict: integrity', A, '    if not integrity_ok:\n        return "NOT_JUDGED (integrity)"', '    if False:\n        return "NOT_JUDGED (integrity)"'),
    ('verdict: M1a', A, 'if m1["M1a"] and m1["M1b"] and m1["M1c"] and', 'if m1["M1b"] and m1["M1c"] and'),
    ('verdict: M1b', A, 'if m1["M1a"] and m1["M1b"] and m1["M1c"] and', 'if m1["M1a"] and m1["M1c"] and'),
    ('verdict: M1c', A, 'if m1["M1a"] and m1["M1b"] and m1["M1c"] and', 'if m1["M1a"] and m1["M1b"] and'),
    ('verdict: M2', A, 'and any(r["holds"] for r in m2_rows.values()):', ':'),
    ('verdict: config', A, 'if any(r["status"] == "MISMATCH_VERIFIED" for r in audit_rows):', 'if False:'),
    # sensitivity
    ('sens: const', A, 'keys = ("cms_sha256", "const_sha256", "arena_size"', 'keys = ("cms_sha256", "arena_size"'),
    ('sens: io', A, '"fast_size", "inputs", "outputs")', '"fast_size")'),
    ('sens: not ok', A, 'if not var.get("ok") or not base.get("ok") or', 'if'),
    # M1 checks
    ('m1a: lut in max', A, 'a += [o["total"] == max(o["npu"], o["sram"], o["dram"], o["lut"]) for o in ops]', 'a += [True for o in ops]'),
    ('m1b: sum', A, 'b.append(num(cmp["summary"]["cycles_total"]) == sum(o["total"] for o in ops))', 'b.append(True)'),
    ('m1c: tolerance', A, '            c.append(abs(pred - rep) <= 1)', '            c.append(abs(pred - rep) <= 2)'),
    ('m1c: scope DF', A, 'm.get("traversal") != "DepthFirst" or num(d.get("kernel_size_x"))', 'num(d.get("kernel_size_x"))'),
    ('m1c: scope Conv2D', A, 'if not d or kind.get(m.get("id")) != "Conv2D" or m.get("traversal")', 'if not d or m.get("traversal")'),
    ('m1c: scope 1x1', A, ' or num(d.get("kernel_size_x")) != 1 or num(d.get("kernel_size_y")) != 1:', ':'),
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
