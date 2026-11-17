"""Mutation test of the Stage 6B-E2E-D judge (host/analysis/stage6be2ed.py) and of the runner's placement-2 firmware
(placement.c, hooks.c, runner.c; 14077be). Each mutation neuters one rule, runs the named tests (default
test_stage6be2ed), requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6be2ed/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2ed.py"
FW = "firmware/driver_runner/use_case/pmu_runner/src/"
T = ["test_stage6be2ed"]
PLC, CON, SIM = "test_placement", "test_driver_runner_contract", "test_driver_runner_sim"

MUTATIONS = [
    ("dst align", A, "start = (end + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)", "start = end"),
    ("dst fits", A, "return dst if dst + length <= sram_limit else 0", "return dst"),
    ("dst src", A, "    if src == 0 or length == 0:\n        return 0", "    if False:\n        return 0"),
    ("lay where", A, "c.update(weights_where=b(0) == weights_at and weights_at is not None,", "c.update(weights_where=True,"),
    ("lay inside", A, "weights_inside=SRAM_BASE <= b(0) and b(0) + s(0) <= SRAM_LIMIT,", "weights_inside=True,"),
    ("lay disjoint arena", A, "weights_disjoint=(b(0) + s(0) <= b(1) or b(1) + alen <= b(0)) and ", "weights_disjoint="),
    ("lay disjoint fast", A, " and (b(0) + s(0) <= fb or fb + fs <= b(0)))", ")"),
    ("lay ddr", A, "c.update(weights_ddr=mb <= b(0) and b(0) + s(0) <= mb + r.get(\"model_len\", 0))", "c.update(weights_ddr=True)"),
    ("lay arena where", A, "c = dict(arena_where=r.get(\"arena_base\") == a and b(1) == a,", "c = dict(arena_where=True,"),
    ("lay fast disjoint", A, "fast_disjoint=(b(2) + s(2) <= b(1) or b(1) + alen <= b(2)) and (fb + fs <= b(1) or b(1) + alen <= fb),", "fast_disjoint=True,"),
    ("lay empty", A, "    if not records or None in (fb, fs, mb, lim, alen):", "    if None in (fb, fs, mb, lim, alen):"),
    ("lay used", A, "    env += [f\"layout {c}\" for c, v in lay[\"checks\"].items() if not v]\n", ""),
    ("remap ext low", A, "ext_rd=EXT_RD_B3W[0] <= b3w[\"ext_rd_beats\"] <= EXT_RD_B3W[1],", "ext_rd=b3w[\"ext_rd_beats\"] <= EXT_RD_B3W[1],"),
    ("remap ext high", A, "ext_rd=EXT_RD_B3W[0] <= b3w[\"ext_rd_beats\"] <= EXT_RD_B3W[1],", "ext_rd=EXT_RD_B3W[0] <= b3w[\"ext_rd_beats\"],"),
    ("remap ext range", A, "EXT_RD_B3W = (39, 64)", "EXT_RD_B3W = (39, 128)"),
    ("remap wr", A, "ext_wr=b3w[\"ext_wr_beats\"] == 0,", "ext_wr=True,"),
    ("remap shift", A, "sram_shift=abs((b3w[\"sram_rd_beats\"] - b3_sram_rd) - WEIGHT_SCALE_BEATS) <= SHIFT_TOL * WEIGHT_SCALE_BEATS,", "sram_shift=True,"),
    ("remap shift tol", A, "SHIFT_TOL = 0.01", "SHIFT_TOL = 0.03"),
    ("remap total", A, "read_total=abs(b3w[\"sram_rd_beats\"] + b3w[\"ext_rd_beats\"] - b3_read_total) <= SHIFT_TOL * b3_read_total)", "read_total=True)"),
    ("remap both", A, "    if len(ok) == 2:\n        return \"WEIGHT_SCALE_REMAP_CONFIRMED\"", "    if ok:\n        return \"WEIGHT_SCALE_REMAP_CONFIRMED\""),
    ("remap partial", A, "return \"REMAP_PARTIAL\" if ok else \"REMAP_INVALID\"", "return \"REMAP_PARTIAL\""),
    ("eq npu", A, "c = dict(npu=abs(npu - eb) <= tol(eb, [r_eb, rng]),", "c = dict(npu=True,"),
    ("eq npu ranges", A, "tol(eb, [r_eb, rng])", "tol(eb, [r_eb, rng, rng])"),
    ("eq traffic", A, "traffic={k: traffic.get(k) for k in B3_EB_TRAFFIC} == B3_EB_TRAFFIC)", "traffic=True)"),
    ("eq both", A, "return \"B3_REPRODUCED\" if len(ok) == 2 else", "return \"B3_REPRODUCED\" if ok else"),
    ("res usable", A, "    if not usable or le3 <= t3:", "    if le3 <= t3:"),
    ("res b3 response", A, "    if not usable or le3 <= t3:", "    if not usable:"),
    ("res low", A, "    if ratio <= LOW and removed:", "    if ratio <= LOW:"),
    ("res low strict", A, "    if ratio <= LOW and removed:", "    if ratio < LOW and removed:"),
    ("res high", A, "    elif ratio >= HIGH and remains:", "    elif ratio >= HIGH:"),
    ("res high strict", A, "    elif ratio >= HIGH and remains:", "    elif ratio > HIGH and remains:"),
    ("res mixed", A, "    elif LOW < ratio < HIGH and removed and remains:", "    elif LOW < ratio < HIGH:"),
    ("res removed tol", A, "removed, remains = le3 - le3w > t3 + t3w, le3w > t3w", "removed, remains = le3 - le3w > t3, le3w > t3w"),
    ("res remains tol", A, "removed, remains = le3 - le3w > t3 + t3w, le3w > t3w", "removed, remains = le3 - le3w > t3 + t3w, le3w > 0"),
    ("judge res gate", A, "res_ok = usable and equiv == \"B3_REPRODUCED\" and remap == \"WEIGHT_SCALE_REMAP_CONFIRMED\"", "res_ok = usable and remap == \"WEIGHT_SCALE_REMAP_CONFIRMED\""),
    ("judge res remap", A, "res_ok = usable and equiv == \"B3_REPRODUCED\" and remap == \"WEIGHT_SCALE_REMAP_CONFIRMED\"", "res_ok = usable and equiv == \"B3_REPRODUCED\""),
    ("judge usable mac", A, "good = lambda k: res[k][\"status\"] == \"VALID\" and mac_ok.get(k, False)", "good = lambda k: res[k][\"status\"] == \"VALID\""),
    ("judge le tol", A, "t_le = {c: tol(b(c, 500), [r(c, 500), r(c, 1000)]) for c in CELLS}", "t_le = {c: tol(b(c, 500), [r(c, 500)]) for c in CELLS}"),
    ("valid gate", A, "if gate.get(\"verdict\") != \"PASS\" or any(", "if any("),
    ("valid mac", A, "if all(r[\"status\"] == \"VALID\" for r in res.values()) and all(mac_ok.values()):", "if all(r[\"status\"] == \"VALID\" for r in res.values()):"),
    ("b3gate mac", A, "if r[\"status\"] != \"VALID\" or r[\"metrics\"][\"mac_active\"] != H1UC:", "if r[\"status\"] != \"VALID\":"),
    ("b3gate rep", A, "return dict(verdict=\"PASS\" if rep[\"ok\"] else \"FAIL\", reproduce=rep)", "return dict(verdict=\"PASS\", reproduce=rep)"),
    ("gate rep", A, "return dict(verdict=\"PASS\" if rep[\"ok\"] and same else \"FAIL\"", "return dict(verdict=\"PASS\""),
    ("order", A, "(\"B3w\", 1000, 466), (\"B3\", 1000, 467)]", "(\"B3\", 1000, 466), (\"B3w\", 1000, 467)]"),
    ("placement const", A, "PLACEMENT = {\"REF\": 0, \"B3\": 1, \"B3w\": 2}", "PLACEMENT = {\"REF\": 0, \"B3\": 1, \"B3w\": 1}"),
    # firmware (placement 2)
    ("fw select region 0", FW + "placement.c", "case 0:  return placement == PLACEMENT_SRAM_W ? PLACEMENT_REGION0_SRAM : PLACEMENT_REGION0;",
     "case 0:  return PLACEMENT_REGION0;", [PLC]),
    ("fw select region 1", FW + "placement.c", "(placement == PLACEMENT_SRAM || placement == PLACEMENT_SRAM_W) ? PLACEMENT_REGION1_SRAM",
     "(placement == PLACEMENT_SRAM) ? PLACEMENT_REGION1_SRAM", [PLC]),
    ("fw dst align", FW + "placement.c", "    start = (end + mask) & ~mask;\n", "    start = end;\n", [PLC]),
    ("fw dst fits", FW + "placement.c", " || len > sram_limit - dst) { return 0U; }\n    return dst;", ") { return 0U; }\n    return dst;", [PLC]),
    ("fw prepare compare", FW + "placement.c", "    if (memcmp((const void *)dst, (const void *)src, len) != 0) { return 0U; }\n", "", [PLC]),
    ("fw prepare sync", FW + "placement.c", "    memcpy((void *)dst, (const void *)src, len);\n    sync();\n", "    memcpy((void *)dst, (const void *)src, len);\n", [PLC]),
    ("fw prepare repeat", FW + "placement.c", "    if (w_dst != 0U && src == w_src && len == w_len) { return w_dst; }\n", "", [PLC]),
    ("fw reset", FW + "placement.c", "    w_src = 0U; w_len = 0U; w_dst = 0U;\n}", "}", [PLC]),
    ("fw effective", FW + "placement.c", "return (active == PLACEMENT_SRAM_W && w_dst == 0U) ? PLACEMENT_SRAM : active;", "return active;", [PLC, SIM]),
    ("fw hook index 0", FW + "hooks.c", "    if (index == 0 && placement_weights() != 0U) {", "    if (index >= -1 && placement_weights() != 0U) {", [CON]),
    ("fw hook effective", FW + "hooks.c", "return placement_config_select(index, placement_effective());", "return placement_config_select(index, placement_get());", [CON]),
    ("fw hook prepare", FW + "hooks.c", "        if (placement_get() == PLACEMENT_SRAM_W && j->num_base_addr > 0) {\n            (void)placement_weights_prepare(", "        if (0) {\n            (void)placement_weights_prepare(", [CON]),
    ("fw runner reset", FW + "runner.c", "        placement_weights_reset(arena_base, P->arena_len, limit);", "        (void)limit;", [CON]),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def green():
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return all(subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                              capture_output=True).returncode == 0 for m in T)


def green_for(tests):
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return all(subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                              capture_output=True).returncode == 0 for m in tests)


def main():
    if not green():
        print("baseline not GREEN"); return 1
    lines, bad = [], 0
    for mid, rel, old, new, *tests in MUTATIONS:
        p = REPO / rel
        before, text = sha(p), p.read_text()
        if text.count(old) != 1:
            lines.append(f"NOT_APPLIED  {mid}  ({rel}: pattern found {text.count(old)}x)"); bad += 1; print(lines[-1]); continue
        p.write_text(text.replace(old, new))
        try:
            g = green_for(tests[0]) if tests else green()
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
