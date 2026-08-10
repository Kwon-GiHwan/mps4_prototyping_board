import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import check_pmu_interval_v10 as gate
import patches.patch_pmu_interval_v10 as patcher

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
void u85_irq_handler(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02)){
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 2);
    }
}
void test_commands(void) {
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x1);
    //Clear IRQ
    wait_for_irq();
}
"""

print("=== patcher ===")
runner_out, runner_counts = patcher.patch_runner(RUNNER)
vendor_out, vendor_counts = patcher.patch_vendor(VENDOR)
check("runner patch adds v10 schema branch", "PMU_INTERVAL_FINE_DIAG_V10" in runner_out)
check("vendor patch inserts T1/T2/I0/T3 markers",
      all(m in vendor_out for m in gate.VENDOR_MARKERS))
check("runner patch counts recorded", runner_counts["serialize_append"] == 1)
check("v10-only S1/S2 private-driver exception recorded",
      runner_counts["s1_s2_private_driver_boundary"] == 1)
check("vendor patch counts recorded",
      vendor_counts["irq_status_block"] == 1
      and vendor_counts["irq_entry_block"] == 1
      and vendor_counts["irq_post_t3_counts"] == 1)

print("=== gate ===")
counts = gate.verify_generated_sources(runner_out, vendor_out)
check("gate accepts patched sources", counts["PMU_INTERVAL_V10_T1"] == 1)

try:
    gate.verify_generated_sources(runner_out, vendor_out.replace("PMU_INTERVAL_V10_T2", ""))
    check("missing marker rejected", False)
except SystemExit:
    check("missing marker rejected", True)

try:
    gate.verify_generated_sources(
        runner_out, vendor_out.replace("pmu_interval_v10_t_submit_after_cmd = DWT->CYCCNT;",
                                       "read_reg(NPU_REG_STATUS);\n    pmu_interval_v10_t_submit_after_cmd = DWT->CYCCNT;")
    )
    check("extra MMIO at checkpoint rejected", False)
except SystemExit:
    check("extra MMIO at checkpoint rejected", True)

try:
    gate.verify_generated_sources(
        runner_out, vendor_out.replace("wait_for_irq();", "PMU_INTERVAL_V10_T2\n    wait_for_irq();")
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
    1000:\t4a09      \tldr\tr2, [pc, #36] @ (1028 <test_u85+0x28>)
    1002:\t6851      \tldr\tr1, [r2, #4]
    1004:\t4b09      \tldr\tr3, [pc, #36] @ (102c <test_u85+0x2c>)
    1006:\t6019      \tstr\tr1, [r3, #0]
    1008:\t4d09      \tldr\tr5, [pc, #36] @ (1030 <test_u85+0x30>)
    100a:\t68ae      \tldr\tr6, [r5, #8]
    100c:\tf046 0601 \torr.w\tr6, r6, #1
    1010:\t60ae      \tstr\tr6, [r5, #8]
    1012:\t6851      \tldr\tr1, [r2, #4]
    1014:\t4b07      \tldr\tr3, [pc, #28] @ (1034 <test_u85+0x34>)
    1016:\t6019      \tstr\tr1, [r3, #0]
    1028:\te0001000 \t.word\t0xe0001000
    102c:\t20001000 \t.word\t0x20001000
    1030:\t50004000 \t.word\t0x50004000
    1034:\t20001004 \t.word\t0x20001004

00001100 <u85_irq_handler>:
    1100:\t4a0f      \tldr\tr2, [pc, #60] @ (1140 <u85_irq_handler+0x40>)
    1102:\t6851      \tldr\tr1, [r2, #4]
    1104:\t4b0f      \tldr\tr3, [pc, #60] @ (1144 <u85_irq_handler+0x44>)
    1106:\t6019      \tstr\tr1, [r3, #0]
    1108:\t4e0f      \tldr\tr6, [pc, #60] @ (1148 <u85_irq_handler+0x48>)
    110a:\t6871      \tldr\tr1, [r6, #4]
    110c:\tf011 0f02 \ttst.w\tr1, #2
    1110:\t6851      \tldr\tr1, [r2, #4]
    1112:\t4b0e      \tldr\tr3, [pc, #56] @ (114c <u85_irq_handler+0x4c>)
    1114:\t6019      \tstr\tr1, [r3, #0]
    1116:\t4c0e      \tldr\tr4, [pc, #56] @ (1150 <u85_irq_handler+0x50>)
    1118:\t6821      \tldr\tr1, [r4, #0]
    111a:\t3101      \tadds\tr1, #1
    111c:\t6021      \tstr\tr1, [r4, #0]
    111e:\t2701      \tmovs\tr7, #1
    1120:\t4d0c      \tldr\tr5, [pc, #48] @ (1154 <u85_irq_handler+0x54>)
    1122:\t702f      \tstrb\tr7, [r5, #0]
    1124:\t2702      \tmovs\tr7, #2
    1126:\t60b7      \tstr\tr7, [r6, #8]
    1128:\te002      \tb.n\t1130 <u85_irq_handler+0x30>
    1130:\t4c09      \tldr\tr4, [pc, #36] @ (1158 <u85_irq_handler+0x58>)
    1132:\t6821      \tldr\tr1, [r4, #0]
    1134:\t3101      \tadds\tr1, #1
    1136:\t6021      \tstr\tr1, [r4, #0]
    1140:\te0001000 \t.word\t0xe0001000
    1144:\t20001008 \t.word\t0x20001008
    1148:\t50004000 \t.word\t0x50004000
    114c:\t2000100c \t.word\t0x2000100c
    1150:\t20001014 \t.word\t0x20001014
    1154:\t20001018 \t.word\t0x20001018
    1158:\t20001010 \t.word\t0x20001010

00001200 <dispatch>:
    1200:\t4c07      \tldr\tr4, [pc, #28] @ (1220 <dispatch+0x20>)
    1202:\t6863      \tldr\tr3, [r4, #4]
    1204:\t9368      \tstr\tr3, [sp, #104]
    1206:\tf7ff ffff \tbl\t1300 <run_fixed_inference>
    120a:\t6863      \tldr\tr3, [r4, #4]
    120c:\t936c      \tstr\tr3, [sp, #108]
    1220:\te0001000 \t.word\t0xe0001000

00001300 <run_fixed_inference>:
    1300:\t4770      \tbx\tlr
"""
NM = """20001000 B pmu_interval_v10_t_submit_before_cmd
20001004 B pmu_interval_v10_t_submit_after_cmd
20001008 B pmu_interval_v10_t_irq_handler_entry
2000100c B pmu_interval_v10_t_irq_status_seen
20001010 B pmu_interval_v10_i0_hit_count
20001014 B pmu_interval_v10_t3_hit_count
20001018 B irq_triggered
"""

elf_evidence = gate.verify_checkpoint_stores(DISASSEMBLY, NM)
check("ELF gate proves T0/T1/T2/I0/T3/T5 and ISR order",
      elf_evidence["t0_dwt_load_address"] == 0x1202
      and elf_evidence["t5_store_address"] == 0x120C
      and elf_evidence["npu_cmd_submit_store_address"] == 0x1010
      and elf_evidence["npu_status_read_address"] == 0x110A
      and elf_evidence["npu_cmd_irq_clear_store_address"] == 0x1126)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace("1010:\t60ae      \tstr\tr6, [r5, #8]",
                            "1010:\t60ae      \tstr\tr6, [r5, #12]", 1), NM)
    check("missing NPU CMD submit store rejected", False)
except SystemExit:
    check("missing NPU CMD submit store rejected", True)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace("[sp, #104]", "[sp, #0]", 1), NM)
    check("wrong T0 record stack slot rejected", False)
except SystemExit:
    check("wrong T0 record stack slot rejected", True)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace(".word\t0xe0001000", ".word\t0xe0002000", 1), NM)
    check("non-DWT checkpoint load rejected", False)
except SystemExit:
    check("non-DWT checkpoint load rejected", True)

try:
    gate.verify_checkpoint_stores(
        DISASSEMBLY.replace(
            "1100:\t4a0f      \tldr\tr2, [pc, #60] @ (1140 <u85_irq_handler+0x40>)",
            "10fe:\t4f10      \tldr\tr7, [pc, #64] @ (1140 <u85_irq_handler+0x40>)\n"
            "    1100:\t4a0f      \tldr\tr2, [pc, #60] @ (1140 <u85_irq_handler+0x40>)",
            1,
        ), NM)
    check("extra literal load before I0 rejected", False)
except SystemExit:
    check("extra literal load before I0 rejected", True)

print()
print("passed=%d failed=%d" % (passed, failed))
raise SystemExit(1 if failed else 0)
