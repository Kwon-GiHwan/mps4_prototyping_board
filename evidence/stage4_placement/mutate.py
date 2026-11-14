"""Mutation test of the Stage 4 placement checks (CLAUDE.md: a check that cannot fail is worse than no check). Each
mutation neuters one check, runs the test modules that should catch it, requires RED, and restores the file by sha256.
Writes mutation.txt beside this file; exits 1 if a mutation survives or a file does not come back byte-identical.

    python3 evidence/stage4_placement/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FW = "firmware/driver_runner/use_case/pmu_runner/src/"
SIM, PLC, DRWL, REC, CON, S4P = ("test_driver_runner_sim", "test_placement", "test_drwl", "test_record_v2",
                                 "test_driver_runner_contract", "test_stage4p")

# (id, file, old, new, test modules)
MUTATIONS = [
    ("F1 firmware refuses placement > 1", FW + "workload.c",
     "if (w->placement >= PLACEMENT_MODES) { return 7U; }", "", [SIM]),
    ("F2 SRAM arena fits below the limit", FW + "placement.c",
     "if (arena < start || arena > sram_limit || arena_len > sram_limit - arena) { return 0U; }", "", [PLC, SIM]),
    ("F2 SRAM arena 64 KiB aligned", FW + "placement.c",
     "uintptr_t start = (sram_free + mask) & ~mask, arena;", "uintptr_t start = sram_free, arena;", [PLC, SIM]),
    ("F2 model base alignment refused", FW + "placement.c",
     "if ((model_base & mask) != 0U || ddr_arena < model_base", "if (ddr_arena < model_base", [PLC]),
    ("F2 runner uses the SRAM arena", FW + "runner.c",
     "if (ddr == 0U || wl.placement == PLACEMENT_DDR) { return ddr; }", "return ddr;", [SIM]),
    ("F3 region 1 -> SRAM port for placement 1", FW + "placement.c",
     "placement == PLACEMENT_SRAM ? PLACEMENT_REGION1_SRAM : PLACEMENT_REGION1_DDR", "PLACEMENT_REGION1_DDR",
     [PLC, SIM]),
    ("F3 runner hands the placement to the hook", FW + "runner.c",
     "    placement_set(wl.placement);\n", "", [SIM]),
    ("F3 hook returns the placement table", FW + "hooks.c",
     "return placement_config_select(index, placement_get());", "return placement_config_select(index, 0U);", [CON]),
    ("F4 REGIONCFG_MATCH flag", FW + "runner.c",
     "if (r->irq_count != 0U && r->regioncfg_irq == placement_regioncfg(r->n_base, r->placement)",
     "if (r->irq_count != 0U", [SIM]),
    ("F4 IRQ reads REGIONCFG", FW + "hooks.c",
     "    probe.regioncfg_irq = npu_word(NPU_OFF_REGIONCFG);\n", "", [CON]),
    ("F5 arena memory check", FW + "runner.c",
     "if ((r = placement_mem_check(arena_base, P->arena_len, P->dcache_sync, &bad)) != 0U) { return LOAD_MEM_CHECK + r; }",
     "(void)bad;", [SIM]),
    ("F5 complement pass", FW + "placement.c", "pass <= 2U", "pass <= 1U", [PLC]),
    ("F5 OFM poison", FW + "runner.c", "        memset(o, OFM_POISON, len);\n", "", [SIM]),
    ("F5 IFM read-back", FW + "runner.c",
     "if (memcmp(p, wl.in[i].ptr, len) != 0) { return LOAD_IFM_CHECK + i; }", "", [SIM]),
    ("F1 host refuses placement > 1", "host/lib/drwl.py",
     """    if h["placement"] not in PLACEMENTS.values():
        raise ValueError(f"placement {h['placement']}")
""", "", [DRWL]),
    ("F1 with_placement writes word 7 only", "host/lib/drwl.py",
     "struct.pack_into(\"<I\", out, 4 * PLACEMENT_WORD, placement)",
     "struct.pack_into(\"<I\", out, 4 * PLACEMENT_WORD - 4, placement)", [DRWL]),
    ("F4 validity requires REGIONCFG_MATCH", "host/lib/record_v2.py",
     "if r.f[\"schema\"] >= 4 and not r.valid_flags & REGIONCFG_MATCH:", "if False:", [REC]),
    ("F4 schema word matches record length", "host/lib/record_v2.py",
     "if f[\"schema\"] != known[total]:", "if False:", [REC]),
    ("F7 board stops on REGIONCFG mismatch", "host/board/run_driver_events.py",
     "if not r.valid_flags & record_v2.REGIONCFG_MATCH:", "if False:", [SIM]),
    ("F7 board refuses an old image with SRAM", "host/board/run_driver_events.py",
     "        if placement != drwl.PLACEMENT_DDR:\n", "        if False:\n", [SIM]),
    ("F7 board stops on a placement mismatch", "host/board/run_driver_events.py",
     "if r.f[\"placement\"] != placement:", "if False:", [SIM]),
    ("gate B only word 7", "host/analysis/stage4p.py",
     "only_word_7_differs=len(a) == len(b) and", "only_word_7_differs=True or", [S4P]),
    ("gate B sections", "host/analysis/stage4p.py", "sections_equal=sec(a, ha) == sec(b, hb),", "sections_equal=True,", [S4P]),
    ("placement verification", "host/analysis/stage4p.py",
     "    e, out = EXPECTED[placement], []\n", "    return []\n    e, out = EXPECTED[placement], []\n", [S4P]),
    ("A/B invariants", "host/analysis/stage4p.py", "    out = []\n    ra, rb = ", "    return []\n    ra, rb = ", [S4P]),
    ("gate C PASS_EXACT", "host/analysis/stage4p.py", "oc[\"verdict\"] == \"PASS_EXACT\"",
     "oc[\"verdict\"] in (\"PASS_EXACT\", \"PASS_TOLERANCE\")", [S4P]),
    ("output CRC A = B", "host/analysis/stage4p.py",
     "if a[\"output_crc32\"] is None or a[\"output_crc32\"] != b[\"output_crc32\"]:", "if False:", [S4P]),
    ("P1 exact counters", "host/analysis/stage4p.py", "if stat(a, p, c)[0] != v]", "if False]", [S4P]),
    ("P1 NPU_ACTIVE tolerance", "host/analysis/stage4p.py",
     "t = max(FLOOR * STAGE4[\"npu_active\"],", "t = max(2 * FLOOR * STAGE4[\"npu_active\"],", [S4P]),
    ("traffic direction", "host/analysis/stage4p.py",
     "ok = all(per[c][\"outside\"] and (per[c][\"delta\"] > 0) == (s > 0)", "ok = all(per[c][\"outside\"]", [S4P]),
    ("cost same sign", "host/analysis/stage4p.py", "and len(signs) == 1:", ":", [S4P]),
    ("cost 1 % floor", "host/analysis/stage4p.py", "return max(FLOOR * ma, ra or 0, rb or 0)",
     "return max(ra or 0, rb or 0)", [S4P]),
    ("compute rule", "host/analysis/stage4p.py",
     "same=abs(mb - ma) <= max(ra or 0, rb or 0))", "same=True)", [S4P]),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_tests(mods):
    shutil.rmtree(REPO / "host" / "__pycache__", ignore_errors=True)
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    rcs = [subprocess.run([sys.executable, "-B", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                          capture_output=True).returncode for m in mods]
    return all(rc == 0 for rc in rcs)


def main():
    lines, bad = [], 0
    if not run_tests(sorted({m for *_, ms in MUTATIONS for m in ms})):
        print("baseline not GREEN"); return 1
    for mid, rel, old, new, mods in MUTATIONS:
        p = REPO / rel
        before, text = sha(p), p.read_text()
        if text.count(old) != 1:
            lines.append(f"NOT_APPLIED  {mid}  ({rel}: pattern found {text.count(old)}x)"); bad += 1; continue
        p.write_text(text.replace(old, new))
        try:
            green = run_tests(mods)
        finally:
            p.write_text(text)
        restored = sha(p) == before
        verdict = "SURVIVED" if green else "KILLED"
        bad += green or not restored
        lines.append(f"{verdict:12s} {mid}  ({rel}; {', '.join(mods)}; restored by sha256: {restored})")
        print(lines[-1], flush=True)
    green = run_tests(sorted({m for *_, ms in MUTATIONS for m in ms}))
    lines.append(f"after restore: {'GREEN' if green else 'RED'}")
    (pathlib.Path(__file__).parent / "mutation.txt").write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if bad or not green else 0


if __name__ == "__main__":
    sys.exit(main())
