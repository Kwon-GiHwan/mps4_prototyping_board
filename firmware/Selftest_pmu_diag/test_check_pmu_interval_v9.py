import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import check_pmu_interval_v9 as gate
import patches.patch_pmu_interval_v9 as patcher

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


RUNNER = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif
static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)
#error "PMU_QUAL: schema v8 must link the reference vendor u85.c"
#endif
#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)
#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)
#error "PMU_DIAG: S1/S2 must link the reference vendor u85.c"
#endif
#endif
    pmu_diag_snapshot_t internal_post_disable;
    pmu_diag_snapshot_t after_return;
#else
#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif
#if defined(PMU_QUAL_SCHEMA_V8)
/* The wire shape, asserted at compile time rather than trusted. The host
 * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch
 * here would otherwise surface as an unparseable board run. */
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_QUAL: a snapshot must be exactly 8 words on the wire");
_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,
               "PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,
               "PMU_QUAL: total is 8 header + 85 body = 93 words");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,
               "PMU_QUAL: payload is 93 * 4 = 372 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,
               "PMU_QUAL: the v8 record must declare schema version 8");
#endif
#if defined(PMU_QUAL_SCHEMA_V8)
    /* Same freshness rule as the two result gates above, and for the same
     * reason: a hook count or an LR left over from the previous run would be
     * indistinguishable from this run's evidence. */
    pmu_qual_reset_hook_state();
#endif
    put_diag_snapshot(&c, &d->internal_post_disable);
    put_diag_snapshot(&c, &d->after_return);
#else
        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;
        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;
        d.internal_pre_release          = pmu_qual_internal_pre_release;
        d.internal_post_disable         = pmu_qual_internal_post_disable;
    d.t_call_enter = read_timestamp();
    rc = run_fixed_inference();
    d.t_call_return = read_timestamp();
    put32(&c, d->t_call_enter);
    put32(&c, d->t_call_return);
"""

VENDOR = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000
static inline void wait_for_irq(void) {}
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x1);
    //Clear IRQ
    wait_for_irq();
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02)){
        irq_triggered = true;
    }
"""

print("=== patcher ===")
runner_out, runner_counts = patcher.patch_runner(RUNNER)
vendor_out, vendor_counts = patcher.patch_vendor(VENDOR)
check("runner patch adds v9 schema branch", "PMU_INTERVAL_DIAG_V9" in runner_out)
check("vendor patch inserts T1/T2/T3 markers",
      all(m in vendor_out for m in gate.VENDOR_MARKERS))
check("runner patch counts recorded", runner_counts["serialize_append"] == 1)
check("v9-only S1/S2 private-driver exception recorded",
      runner_counts["s1_s2_private_driver_boundary"] == 1)
check("vendor patch counts recorded", vendor_counts["irq_status_block"] == 1)

print("=== gate ===")
counts = gate.verify_generated_sources(runner_out, vendor_out)
check("gate accepts patched sources", counts["PMU_INTERVAL_V9_T1"] == 1)

try:
    gate.verify_generated_sources(runner_out, vendor_out.replace("PMU_INTERVAL_V9_T2", ""))
    check("missing marker rejected", False)
except SystemExit:
    check("missing marker rejected", True)

try:
    gate.verify_generated_sources(
        runner_out, vendor_out.replace("pmu_interval_v9_t_submit_after_cmd = DWT->CYCCNT;",
                                       "read_reg(NPU_REG_STATUS);\n    pmu_interval_v9_t_submit_after_cmd = DWT->CYCCNT;")
    )
    check("extra MMIO at checkpoint rejected", False)
except SystemExit:
    check("extra MMIO at checkpoint rejected", True)

try:
    gate.verify_generated_sources(
        runner_out, vendor_out.replace("wait_for_irq();", "PMU_INTERVAL_V9_T2\n    wait_for_irq();")
    )
    check("duplicate marker rejected", False)
except SystemExit:
    check("duplicate marker rejected", True)

for label, broken in (
    ("BUSY_SLEEP removal rejected", vendor_out.replace("#define BUSY_SLEEP\n", "", 1)),
    ("VERIFY_OUTPUT removal rejected", vendor_out.replace("#define VERIFY_OUTPUT 1\n", "", 1)),
):
    try:
        gate.verify_generated_sources(runner_out, broken)
        check(label, False)
    except SystemExit:
        check(label, True)

DISASSEMBLY = """Disassembly of section .text:

00001000 <test_u85>:
    1000:\t4a07      \tldr\tr2, [pc, #28] @ (1020 <test_u85+0x20>)
    1002:\t6851      \tldr\tr1, [r2, #4]
    1004:\t4b07      \tldr\tr3, [pc, #28] @ (1024 <test_u85+0x24>)
    1006:\t6019      \tstr\tr1, [r3, #0]
    1008:\t4d08      \tldr\tr5, [pc, #32] @ (102c <test_u85+0x2c>)
    100a:\t2601      \tmovs\tr6, #1
    100c:\t60ae      \tstr\tr6, [r5, #8]
    100e:\t6851      \tldr\tr1, [r2, #4]
    1010:\t4b05      \tldr\tr3, [pc, #20] @ (1028 <test_u85+0x28>)
    1012:\t6019      \tstr\tr1, [r3, #0]
    1020:\te0001000 \t.word\t0xe0001000
    1024:\t20001000 \t.word\t0x20001000
    1028:\t20001004 \t.word\t0x20001004
    102c:\t50004000 \t.word\t0x50004000

00001100 <u85_irq_handler>:
    1100:\t4a07      \tldr\tr2, [pc, #28] @ (1120 <u85_irq_handler+0x20>)
    1102:\t6851      \tldr\tr1, [r2, #4]
    1104:\t4b07      \tldr\tr3, [pc, #28] @ (1124 <u85_irq_handler+0x24>)
    1106:\t6019      \tstr\tr1, [r3, #0]
    1120:\te0001000 \t.word\t0xe0001000
    1124:\t20001008 \t.word\t0x20001008

00001200 <dispatch>:
    1200:\t4c07      \tldr\tr4, [pc, #28] @ (1220 <dispatch+0x20>)
    1202:\t6863      \tldr\tr3, [r4, #4]
    1204:\t9360      \tstr\tr3, [sp, #96]
    1206:\tf7ff ffff \tbl\t1300 <run_fixed_inference>
    120a:\t6863      \tldr\tr3, [r4, #4]
    120c:\t9364      \tstr\tr3, [sp, #100]
    1220:\te0001000 \t.word\t0xe0001000

00001300 <run_fixed_inference>:
    1300:\t4770      \tbx\tlr
"""
NM = """20001000 B pmu_interval_v9_t_submit_before_cmd
20001004 B pmu_interval_v9_t_submit_after_cmd
20001008 B pmu_interval_v9_t_irq_status_seen
"""

elf_evidence = gate.verify_checkpoint_stores(DISASSEMBLY, NM)
check("ELF gate proves T0/T1/T2/T3/T5 direct DWT pairs",
      elf_evidence["t0_dwt_load_address"] == 0x1202
      and elf_evidence["t5_store_address"] == 0x120C
      and elf_evidence["npu_cmd_submit_store_address"] == 0x100C)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace("[r5, #8]", "[r5, #12]", 1), NM)
    check("missing NPU CMD submit store rejected", False)
except SystemExit:
    check("missing NPU CMD submit store rejected", True)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace("[sp, #96]", "[sp, #0]", 1), NM)
    check("wrong T0 record stack slot rejected", False)
except SystemExit:
    check("wrong T0 record stack slot rejected", True)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace(".word\t0xe0001000", ".word\t0xe0002000", 1), NM)
    check("non-DWT checkpoint load rejected", False)
except SystemExit:
    check("non-DWT checkpoint load rejected", True)

print()
print("passed=%d failed=%d" % (passed, failed))
raise SystemExit(1 if failed else 0)
