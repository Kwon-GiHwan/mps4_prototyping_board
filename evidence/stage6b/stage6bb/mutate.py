"""Mutation test of the Stage 6B-B board judge (evidence/stage6b/stage6bb/contract.md). Each mutation neuters one rule
in host/analysis/stage6bb.py, runs test_stage6bb, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6bb/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6bb.py"
T = ["test_stage6bb"]

MUTATIONS = [
    ('env: workload sha', A, 'if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:', 'if False:'),
    ('env: image digests', A, 'if {r[k] for r in rows} != {v}:', 'if False:'),
    ('env: FI101', A, 'if not all(r["fpga_image"].startswith(FPGA) for r in rows):', 'if False:'),
    ('env: boot index', A, 'if {r["host_boot_index"] for r in rows} != {str(m["boot"])}:', 'if False:'),
    ('env: wfe condition', A, 'if {r["condition"] for r in rows} != {"wfe"}:', 'if False:'),
    ('env: 1024 MAC', A, 'if (caps.get("npu_config", 0) & 0xF) != LOG2_MACS:', 'if False:'),
    ('env: identity terms', A, 'bad += [f"identity {k}" for k, v in ident["checks"].items() if not v and k not in IDENT_PMU + IDENT_OUTPUT]', 'pass'),
    ('identity: A2 uses identity_a1', A, 'if m["kind"] == "reference" \\\n        else AOE.identity_a1(folder, wl, cfg, caps_ref, exp)', 'if True \\\n        else AOE.identity_a1(folder, wl, cfg, caps_ref, exp)'),
    ('output: board output', A, 'if not output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][k] for k in IDENT_OUTPUT):', 'if not all(ident["checks"][k] for k in IDENT_OUTPUT):'),
    ('output: one CRC', A, 'IDENT_OUTPUT = ("one_crc", "output_len")', 'IDENT_OUTPUT = ("output_len",)'),
    ('output: reference PASS_EXACT', A, '(wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), runs)["verdict"] == "PASS_EXACT"', '(wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), runs)["verdict"] != "FAIL_X"'),
    ('pmu: RUN layout', A, 'if len(raw) != N_RUNS or sorted({(x["set_id"], x["rep"]) for x in raw}) != [(s, r) for s in SETS for r in range(1, 6)]:', 'if False:'),
    ('pmu: RUN valid', A, 'if not r["valid"]:', 'if False:'),
    ('pmu: counters and pass', A, 'if any(r["ev"].get(c) is None for c in codes) or sorted(r["ev"]) != sorted(codes):', 'if False:'),
    ('pmu: pass membership', A, 'if any(r["ev"].get(c) is None for c in codes) or sorted(r["ev"]) != sorted(codes):', 'if any(r["ev"].get(c) is None for c in codes):'),
    ('pmu: overflow', A, 'if r["event_overflow"] not in ("False", "0", ""):', 'if False:'),
    ('pmu: window', A, 'if r["cycle_valid"] not in ("1", "True"):', 'if False:'),
    ('pmu: implausible MAC', A, 'min(mac) * 1024 < n_mac:', 'min(mac) * 1024 < 0:'),
    ('stable: MAC', A, 'if len(set(s["mac_active"])) != 1:', 'if False:'),
    ('stable: DPU', A, 'if len(set(s["mac_dpu_active"])) != 1:', 'if False:'),
    ('stable: pass A vs B', A, 'if a is None or b is None or abs(b - a) > max(AB_REL * a, ra + rb):', 'if a is None or b is None:'),
    ('stable: range', A, 'RANGE_REL = 0.05 ', 'RANGE_REL = 0.50 '),
    ('stop: CONFIG_MISMATCH', A, 'STOP = ("CONFIG_MISMATCH", "UNMEASURED")', 'STOP = ("UNMEASURED",)'),
    ('stop: UNMEASURED', A, 'STOP = ("CONFIG_MISMATCH", "UNMEASURED")', 'STOP = ("CONFIG_MISMATCH",)'),
    ('stop: output continues', A, 'stop=r["status"] in STOP)', 'stop=r["status"] != "VALID")'),
    ('repro: same binary', A, 'return dict(verdict="PASS" if rep["ok"] and same_bin else "FAIL"', 'return dict(verdict="PASS" if rep["ok"] else "FAIL"'),
    ('repro: reproduce', A, 'return dict(verdict="PASS" if rep["ok"] and same_bin else "FAIL"', 'return dict(verdict="PASS" if same_bin else "FAIL"'),
    ('repro: config VALID', A, 'if r["status"] != "VALID":\n        return dict(verdict="FAIL", why=r["status"]', 'if False:\n        return dict(verdict="FAIL", why=r["status"]'),
    ('fid: vela missing', A, 'if not isinstance(v.get("cycles_total"), int) or v["cycles_total"] <= 0:', 'if False:'),
    ('fid: same compile', A, 'if v.get("vela_sha256") != m.get("vela_sha256"):', 'if False:'),
    ('fid: scope', A, 'if not str(v.get("scope", "")).startswith("A2 graph"):', 'if False:'),
    ('fid: VALID only', A, 'if r["status"] != "VALID":\n        return dict(status="NOT_COMPARABLE"', 'if False:\n        return dict(status="NOT_COMPARABLE"'),
    ('fid: reference excluded', A, 'if m["kind"] != "A2":\n        return dict(status="NOT_COMPARABLE", why="reference config")', 'if False:\n        return dict(status="NOT_COMPARABLE", why="reference config")'),
    ('fid: sign', A, 'e = (b - v) / v * 100', 'e = (v - b) / v * 100'),
    ('verdict: gate', A, 'if gate.get("verdict") != "PASS" or any(', 'if False or any('),
    ('verdict: config mismatch', A, 'or any(res[c]["status"] == "CONFIG_MISMATCH" for c in ORDER) or not valid:', 'or not valid:'),
    ('verdict: all valid', A, 'return "CHARACTERIZATION_VALID" if len(valid) == len(reps) else', 'return "CHARACTERIZATION_VALID" if valid else'),
    ('fid verdict: all', A, 'return "FIDELITY_COMPARABLE" if n == len(reps) else', 'return "FIDELITY_COMPARABLE" if n else'),
    ('fid verdict: none', A, 'else "FIDELITY_PARTIAL" if n else "FIDELITY_NOT_COMPARABLE"', 'else "FIDELITY_PARTIAL"'),
    ('static: drwl digest', A, 'if sha(wl / f"{cfg}.drwl") != m["drwl_sha256"]:', 'if False:'),
    ('static: N_MAC', A, 'or oh * ow * m["cin"] * m["cout"] != m["n_mac"]:', ':'),
    ('static: vela', A, 'if vela_source(m) is not None:', 'if False:'),
    ('rates: 1024', A, 'eff_1024=rate / 1024,', 'eff_1024=rate / 768,'),
    ('c16 comparison value', A, 'return 768 * cin / (math.ceil(cin / 16) * 16)', 'return 768 * cin / cin'),
    ('order fixed', A, 'for g in ("g12", "g25", "g40", "g53", "g11", "g56", "g52", "g57", "g09", "g28")]', 'for g in ("g12", "g25", "g40", "g53", "g11", "g56", "g52", "g57", "g28", "g09")]'),
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
