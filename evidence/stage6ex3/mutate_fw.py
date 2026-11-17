"""Mutation test of the Stage 6E-X3 amendment A firmware/host change (DRWL pmu_flags -> PMCR.mask_en). Each mutation neuters
one part, runs the driver-runner tests,
requires RED, and restores the file by sha256.

    python3 evidence/stage6ex3/mutate_fw.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
P = "firmware/driver_runner/use_case/pmu_runner/"
T = ["test_driver_runner_sim", "test_driver_runner_contract", "test_drwl", "test_record_v2"]

MUTATIONS = [
    ("arm no clear", P + "src/pmu_session.c", "NPU_PMCR_CYCLE_CNT_RST_MSK | NPU_PMCR_MASK_EN_MSK))", "NPU_PMCR_CYCLE_CNT_RST_MSK))"),
    ("arm no set", P + "src/pmu_session.c", "NPU_PMCR_CYCLE_CNT_RST_MSK | mask_en;", "NPU_PMCR_CYCLE_CNT_RST_MSK;"),
    ("arm always set", P + "src/pmu_session.c", "    mask_en = on ? NPU_PMCR_MASK_EN_MSK : 0U;", "    mask_en = NPU_PMCR_MASK_EN_MSK; (void)on;"),
    ("arm readback", P + "src/pmu_session.c", "    *pmcr_after = *reg(NPU_REG_PMCR);", "    *pmcr_after = pmcr;"),
    ("load no reset", P + "src/runner.c", "    pmu_session_set_mask_en(0U);\n", ""),
    ("load no set", P + "src/runner.c", "    pmu_session_set_mask_en(wl.pmu_flags & DRWL_PMU_MASK_EN);\n", ""),
    ("parse no refuse", P + "src/workload.c", "    if ((w->pmu_flags & ~DRWL_PMU_FLAGS_KNOWN) != 0U) { return 8U; }\n", ""),
    ("parse word", P + "src/workload.c", "    w->pmu_flags = rd32(blob + 4U * DRWL_PMU_FLAGS_WORD);", "    w->pmu_flags = rd32(blob + 4U * 9U);"),
    ("record flags", P + "src/runner.c", "    r->pmu_flags = wl.pmu_flags;\n", ""),
    ("record after", P + "src/runner.c", "    r->pmcr_after_arm = p->pmcr_after_arm;\n", ""),
    ("schema", P + "include/record.h", "#define RECORD_SCHEMA       5U", "#define RECORD_SCHEMA       4U"),
    ("host pack refuse", "host/lib/drwl.py", "    if pmu_flags & ~PMU_FLAGS_KNOWN:\n        raise ValueError(f\"pmu_flags {pmu_flags:#x}\")\n", ""),
    ("host parse refuse", "host/lib/drwl.py", "    if h[\"pmu_flags\"] & ~PMU_FLAGS_KNOWN:\n", "    if False:\n"),
    ("host schema", "host/lib/record_v2.py", "SCHEMA_FIELDS = {3: FIELDS_V3, 4: FIELDS_V4, 5: FIELDS}", "SCHEMA_FIELDS = {3: FIELDS_V3, 4: FIELDS, 5: FIELDS}"),
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
