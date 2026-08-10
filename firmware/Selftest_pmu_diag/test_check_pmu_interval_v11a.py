import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import check_pmu_interval_v11a as gate
import patches.patch_pmu_interval_v11a as patcher

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
void test_u85(void)
{
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
}
void test_commands(void) {
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x1);
    //Clear IRQ
    wait_for_irq();
}
"""

DISASSEMBLY = """Disassembly of section .text:

00001000 <test_u85>:
    1000:\t4b0b      \tldr\tr3, [pc, #44] @ (1030 <test_u85+0x30>)
    1002:\t689b      \tldr\tr3, [r3, #8]
    1004:\t4a0b      \tldr\tr2, [pc, #44] @ (1034 <test_u85+0x34>)
    1006:\tf8c3 2080 \tstr.w\tr2, [r3, #128]
    100a:\tf3bf 8f4f \tdsb\tsy
    100e:\t4c0a      \tldr\tr4, [pc, #40] @ (1038 <test_u85+0x38>)
    1010:\t6863      \tldr\tr3, [r4, #4]
    1012:\t9368      \tstr\tr3, [sp, #104]
    1014:\t4d09      \tldr\tr5, [pc, #36] @ (103c <test_u85+0x3c>)
    1016:\t68ae      \tldr\tr6, [r5, #8]
    1018:\tf046 0601 \torr.w\tr6, r6, #1
    101c:\t60ae      \tstr\tr6, [r5, #8]
    101e:\t6863      \tldr\tr3, [r4, #4]
    1020:\t936c      \tstr\tr3, [sp, #108]
    1030:\te000ed00 \t.word\t0xe000ed00
    1034:\t00001101 \t.word\t0x00001101
    1038:\te0001000 \t.word\t0xe0001000
    103c:\t50004000 \t.word\t0x50004000

00001100 <v11a_u85_irq_entry_veneer>:
    1100:\t4804      \tldr\tr0, [pc, #16] @ (1114 <v11a_u85_irq_entry_veneer+0x14>)
    1102:\t6801      \tldr\tr1, [r0, #0]
    1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)
    1106:\t6001      \tstr\tr1, [r0, #0]
    1108:\tf000 b80a \tb.w\t1120 <u85_irq_handler>
    1114:\te0001004 \t.word\t0xe0001004
    1118:\t20001000 \t.word\t0x20001000

00001120 <u85_irq_handler>:
    1120:\tb510      \tpush\t{r4, lr}
    1122:\t4a0e      \tldr\tr2, [pc, #56] @ (115c <u85_irq_handler+0x3c>)
    1124:\t6851      \tldr\tr1, [r2, #4]
    1126:\t4b0e      \tldr\tr3, [pc, #56] @ (1160 <u85_irq_handler+0x40>)
    1128:\t6019      \tstr\tr1, [r3, #0]
    112a:\t4e0e      \tldr\tr6, [pc, #56] @ (1164 <u85_irq_handler+0x44>)
    112c:\t6871      \tldr\tr1, [r6, #4]
    112e:\tf011 0f02 \ttst.w\tr1, #2
    1132:\t6851      \tldr\tr1, [r2, #4]
    1134:\t4b0c      \tldr\tr3, [pc, #48] @ (1168 <u85_irq_handler+0x48>)
    1136:\t6019      \tstr\tr1, [r3, #0]
    1138:\t4d0c      \tldr\tr5, [pc, #48] @ (116c <u85_irq_handler+0x4c>)
    113a:\t702d      \tstrb\tr5, [r5, #0]
    113c:\t2202      \tmovs\tr2, #2
    113e:\t60b2      \tstr\tr2, [r6, #8]
    1140:\t4c0b      \tldr\tr4, [pc, #44] @ (1170 <u85_irq_handler+0x50>)
    1142:\t6821      \tldr\tr1, [r4, #0]
    1144:\t3101      \tadds\tr1, #1
    1146:\t6021      \tstr\tr1, [r4, #0]
    1148:\t4c0a      \tldr\tr4, [pc, #40] @ (1174 <u85_irq_handler+0x54>)
    114a:\t6821      \tldr\tr1, [r4, #0]
    114c:\t3101      \tadds\tr1, #1
    114e:\t6021      \tstr\tr1, [r4, #0]
    1150:\tbd10      \tpop\t{r4, pc}
    115c:\te0001000 \t.word\t0xe0001000
    1160:\t20001004 \t.word\t0x20001004
    1164:\t50004000 \t.word\t0x50004000
    1168:\t20001008 \t.word\t0x20001008
    116c:\t20001014 \t.word\t0x20001014
    1170:\t20001018 \t.word\t0x20001018
    1174:\t2000101c \t.word\t0x2000101c
"""

NM = """00001100 T v11a_u85_irq_entry_veneer
00001120 T u85_irq_handler
20001000 B pmu_interval_v11a_t_vector_probe
20001004 B pmu_interval_v10_t_irq_handler_entry
20001008 B pmu_interval_v10_t_irq_status_seen
20001014 B irq_triggered
20001018 B pmu_interval_v10_i0_hit_count
2000101c B pmu_interval_v10_t3_hit_count
"""

MOVW_MOVT_DISASSEMBLY = """Disassembly of section .text:

00001000 <test_u85>:
    1000:\t4b0c      \tldr\tr3, [pc, #48] @ (1034 <test_u85+0x34>)
    1002:\t689b      \tldr\tr3, [r3, #8]
    1004:\tf241 1201 \tmovw\tr2, #4353
    1008:\tf2c0 0200 \tmovt\tr2, #0
    100c:\tf8c3 2080 \tstr.w\tr2, [r3, #128]
    1010:\tf3bf 8f4f \tdsb\tsy
    1014:\t4c0a      \tldr\tr4, [pc, #40] @ (103c <test_u85+0x3c>)
    1016:\t6863      \tldr\tr3, [r4, #4]
    1018:\t9368      \tstr\tr3, [sp, #104]
    101a:\t4d09      \tldr\tr5, [pc, #36] @ (1040 <test_u85+0x40>)
    101c:\t68ae      \tldr\tr6, [r5, #8]
    101e:\tf046 0601 \torr.w\tr6, r6, #1
    1022:\t60ae      \tstr\tr6, [r5, #8]
    1024:\t6863      \tldr\tr3, [r4, #4]
    1026:\t936c      \tstr\tr3, [sp, #108]
    1034:\te000ed00 \t.word\t0xe000ed00
    1038:\t00001101 \t.word\t0x00001101
    103c:\te0001000 \t.word\t0xe0001000
    1040:\t50004000 \t.word\t0x50004000

00001100 <v11a_u85_irq_entry_veneer>:
    1100:\t4804      \tldr\tr0, [pc, #16] @ (1114 <v11a_u85_irq_entry_veneer+0x14>)
    1102:\t6801      \tldr\tr1, [r0, #0]
    1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)
    1106:\t6001      \tstr\tr1, [r0, #0]
    1108:\tf000 b80a \tb.w\t1120 <u85_irq_handler>
    1114:\te0001004 \t.word\t0xe0001004
    1118:\t20001000 \t.word\t0x20001000

00001120 <u85_irq_handler>:
    1120:\tb510      \tpush\t{r4, lr}
    1122:\t4a0e      \tldr\tr2, [pc, #56] @ (115c <u85_irq_handler+0x3c>)
    1124:\t6851      \tldr\tr1, [r2, #4]
    1126:\t4b0e      \tldr\tr3, [pc, #56] @ (1160 <u85_irq_handler+0x40>)
    1128:\t6019      \tstr\tr1, [r3, #0]
    112a:\t4e0e      \tldr\tr6, [pc, #56] @ (1164 <u85_irq_handler+0x44>)
    112c:\t6871      \tldr\tr1, [r6, #4]
    112e:\tf011 0f02 \ttst.w\tr1, #2
    1132:\t6851      \tldr\tr1, [r2, #4]
    1134:\t4b0c      \tldr\tr3, [pc, #48] @ (1168 <u85_irq_handler+0x48>)
    1136:\t6019      \tstr\tr1, [r3, #0]
    1138:\t4d0c      \tldr\tr5, [pc, #48] @ (116c <u85_irq_handler+0x4c>)
    113a:\t702d      \tstrb\tr5, [r5, #0]
    113c:\t2202      \tmovs\tr2, #2
    113e:\t60b2      \tstr\tr2, [r6, #8]
    1140:\t4c0b      \tldr\tr4, [pc, #44] @ (1170 <u85_irq_handler+0x50>)
    1142:\t6821      \tldr\tr1, [r4, #0]
    1144:\t3101      \tadds\tr1, #1
    1146:\t6021      \tstr\tr1, [r4, #0]
    1148:\t4c0a      \tldr\tr4, [pc, #40] @ (1174 <u85_irq_handler+0x54>)
    114a:\t6821      \tldr\tr1, [r4, #0]
    114c:\t3101      \tadds\tr1, #1
    114e:\t6021      \tstr\tr1, [r4, #0]
    1150:\tbd10      \tpop\t{r4, pc}
    115c:\te0001000 \t.word\t0xe0001000
    1160:\t20001004 \t.word\t0x20001004
    1164:\t50004000 \t.word\t0x50004000
    1168:\t20001008 \t.word\t0x20001008
    116c:\t20001014 \t.word\t0x20001014
    1170:\t20001018 \t.word\t0x20001018
    1174:\t2000101c \t.word\t0x2000101c
"""

POST_SUBMIT_VECTOR_RESTORE = DISASSEMBLY.replace(
    "1020:\t936c      \tstr\tr3, [sp, #108]",
    "1020:\t936c      \tstr\tr3, [sp, #108]\n"
    "    1022:\tf64e 5d88 \tmovw\tr3, #60808\n"
    "    1026:\tf2ce 0300 \tmovt\tr3, #57344\n"
    "    102a:\t601a      \tstr\tr2, [r3, #0]",
    1,
)

PRE_SUBMIT_VECTOR_OVERWRITE = DISASSEMBLY.replace(
    "100a:\tf3bf 8f4f \tdsb\tsy",
    "100a:\tf8c3 2080 \tstr.w\tr2, [r3, #128]\n"
    "    100e:\tf3bf 8f4f \tdsb\tsy",
    1,
)

print("=== patcher ===")
runner_out, runner_counts = patcher.patch_runner(RUNNER)
vendor_out, vendor_counts = patcher.patch_vendor(VENDOR)
check("runner patch adds v11a schema branch", "PMU_INTERVAL_ENTRY_DIAG_V11A" in runner_out)
check("runner patch declares schema-11 J0 field",
      "uint32_t t_vector_probe;" in runner_out and "d.t_vector_probe" in runner_out)
check("runner patch serializes J0 field",
      "put32(&c, d->t_vector_probe);" in runner_out)
check("vendor patch declares J0 storage symbol",
      "volatile uint32_t pmu_interval_v11a_t_vector_probe;" in vendor_out)
check("vendor patch installs veneer vector", "&v11a_u85_irq_entry_veneer" in vendor_out)
check("vendor patch preserves stock handler body",
      "void u85_irq_handler(void)" in vendor_out and "write_reg(NPU_REG_CMD, 2);" in vendor_out)
check("patch counts recorded",
      runner_counts["serialize_append"] == 1
      and runner_counts["record_append_fields"] == 1
      and vendor_counts["runtime_vector_install"] == 1
      and vendor_counts["veneer_extern_decl"] == 1
      and vendor_counts["j0_global_defs"] == 1)

print("=== source gate ===")
counts = gate.verify_generated_sources(runner_out, vendor_out)
check("gate accepts patched sources", counts["runtime_vector_install"] == 1)

for name, broken in (
    ("stock vector target rejected",
     vendor_out.replace("&v11a_u85_irq_entry_veneer", "&u85_irq_handler", 1)),
    ("later-overwritten vector target rejected",
     vendor_out.replace(
         "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);\n",
         "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);\n"
         "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);\n",
         1,
     )),
):
    try:
        gate.verify_generated_sources(runner_out, broken)
        check(name, False)
    except SystemExit:
        check(name, True)

print("=== elf gate ===")
elf = gate.verify_final_elf(DISASSEMBLY, NM)
check("ELF gate proves vector -> veneer -> stock path",
      elf["vector_slot_store"] == 0x1006
      and elf["vector_value"] == 0x1101
      and elf["veneer_address"] == 0x1100
      and elf["stock_handler_address"] == 0x1120)
check("ELF gate composes movw/movt vector materialization",
      gate.verify_final_elf(MOVW_MOVT_DISASSEMBLY, NM)["vector_value"] == 0x1101)
check("post-submit vector restore does not violate overwrite gate",
      gate.verify_final_elf(POST_SUBMIT_VECTOR_RESTORE, NM)["vector_value"] == 0x1101)

try:
    gate.verify_final_elf(PRE_SUBMIT_VECTOR_OVERWRITE, NM)
    check("pre-submit vector overwrite rejected", False)
except SystemExit:
    check("pre-submit vector overwrite rejected", True)

NEGATIVE_DISASSEMBLIES = (
    ("even vector target rejected",
     DISASSEMBLY.replace("0x00001101", "0x00001100", 1)),
    ("wrong DWT address rejected",
     DISASSEMBLY.replace("0xe0001004", "0xe0001008", 1)),
    ("wrong J0 storage rejected",
     DISASSEMBLY.replace("0x20001000", "0x20001020", 1)),
    ("extra stack access rejected",
     DISASSEMBLY.replace(
         "1100:\t4804      \tldr\tr0, [pc, #16] @ (1114 <v11a_u85_irq_entry_veneer+0x14>)",
         "1100:\tb401      \tpush\t{r0}\n    1102:\t4804      \tldr\tr0, [pc, #16] @ (1114 <v11a_u85_irq_entry_veneer+0x14>)",
         1)),
    ("extra call rejected",
     DISASSEMBLY.replace("1108:\tf000 b80a \tb.w\t1120 <u85_irq_handler>",
                         "1108:\tf000 f80a \tbl\t1120 <u85_irq_handler>", 1)),
    ("conditional branch rejected",
     DISASSEMBLY.replace("1108:\tf000 b80a \tb.w\t1120 <u85_irq_handler>",
                         "1108:\td001      \tbeq.n\t1120 <u85_irq_handler>", 1)),
    ("wrong tail target rejected",
     DISASSEMBLY.replace("<u85_irq_handler>", "<other_irq_handler>", 1)),
    ("thunk rejected",
     DISASSEMBLY.replace("1108:\tf000 b80a \tb.w\t1120 <u85_irq_handler>",
                         "1108:\tf000 b80a \tb.w\t1130 <__veneer_helper>", 1)),
    ("barrier rejected",
     DISASSEMBLY.replace(
         "1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         "1104:\tf3bf 8f4f \tdsb\tsy\n    1108:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         1)),
    ("interrupt mask change rejected",
     DISASSEMBLY.replace(
         "1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         "1104:\tb672      \tcpsid\ti\n    1106:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         1)),
    ("LR write rejected",
     DISASSEMBLY.replace(
         "1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         "1104:\t4676      \tmov\tlr, r6\n    1106:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         1)),
    ("extra data load rejected",
     DISASSEMBLY.replace(
         "1104:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         "1104:\t4a05      \tldr\tr2, [pc, #20] @ (111c <v11a_u85_irq_entry_veneer+0x1c>)\n    1106:\t4804      \tldr\tr0, [pc, #16] @ (1118 <v11a_u85_irq_entry_veneer+0x18>)",
         1)),
    ("extra data store rejected",
     DISASSEMBLY.replace(
         "1106:\t6001      \tstr\tr1, [r0, #0]",
         "1106:\t6001      \tstr\tr1, [r0, #0]\n    1108:\t6041      \tstr\tr1, [r0, #4]",
         1)),
)

for name, broken in NEGATIVE_DISASSEMBLIES:
    try:
        gate.verify_final_elf(broken, NM)
        check(name, False)
    except SystemExit:
        check(name, True)

print("=== verify wrapper ===")
with tempfile.TemporaryDirectory() as tmpdir:
    runner_path = os.path.join(tmpdir, "runner.c")
    vendor_path = os.path.join(tmpdir, "vendor.c")
    dis_path = os.path.join(tmpdir, "final.S")
    nm_path = os.path.join(tmpdir, "final.nm")
    vendor_src_path = os.path.join(tmpdir, "vendor_src.c")
    for path, text in (
        (runner_path, runner_out),
        (vendor_path, vendor_out),
        (dis_path, DISASSEMBLY),
        (nm_path, NM),
        (vendor_src_path, ""),
    ):
        with open(path, "w") as handle:
            handle.write(text)
    args = type("Args", (), {
        "vendor_src": vendor_src_path,
        "runner_generated": runner_path,
        "vendor_generated": vendor_path,
        "final_disassembly": dis_path,
        "final_nm": nm_path,
    })()
    orig_sha256 = gate._sha256
    orig_evaluate = gate.q.evaluate
    calls = []

    def fake_sha256(path):
        if path == vendor_src_path:
            return gate.FROZEN_VENDOR_SHA256
        return orig_sha256(path)

    def fake_evaluate(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    gate._sha256 = fake_sha256
    gate.q.evaluate = fake_evaluate
    try:
        gate.verify(args)
        check("verify() invokes base H-PRINTF gate",
              len(calls) == 1 and calls[0]["mode"] == "Q1"
              and calls[0]["vendor_source_text"] == vendor_out)
    finally:
        gate._sha256 = orig_sha256
        gate.q.evaluate = orig_evaluate

    def raising_evaluate(**kwargs):
        raise gate.q.GateError("synthetic base failure")

    gate._sha256 = fake_sha256
    gate.q.evaluate = raising_evaluate
    try:
        gate.verify(args)
        check("verify() propagates base gate failure", False)
    except SystemExit as exc:
        check("verify() propagates base gate failure",
              "base H-PRINTF gate: synthetic base failure" in str(exc))
    finally:
        gate._sha256 = orig_sha256
        gate.q.evaluate = orig_evaluate

print()
print("passed=%d failed=%d" % (passed, failed))
raise SystemExit(1 if failed else 0)
