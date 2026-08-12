import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-72s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


RUNNER = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#else
#error "PMU_COMPLETION_POLL_DIAG_V12 requires PMU_QUAL_SCHEMA_V12"
#endif

#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U

#define V12_POLL_SUCCESS 1U
#define V12_POLL_TIMEOUT 2U

static pmu_diag_snapshot_t pmu_completion_poll_v12_internal_post_disable;

void test_entry(v12_t* d)
{
    d->poll_result = V12_POLL_TIMEOUT;
    d->poll_status_at_success = 0U;
    d->t_poll_entry = 0U;
    d->t_status_completion_seen = 0U;
    d->t_poll_exit = 0U;
}

void run_once(v12_t* d)
{
    d->t_submit_after_cmd = DWT->CYCCNT;
}
"""

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
BUILD_ID = "0x32314950"
SCHEMA_VERSION = 12


VENDOR_STOCK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline void wait_for_irq(void)
{
    bool irq_seen = false;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status_register = read_reg(NPU_REG_STATUS);
        if ((status_register & 0x02U) != 0U) {
            irq_seen = true;
            break;
        }
    }

    if (irq_seen) {
        return;
    }

    irq_never_triggered = true;
    status_register = read_reg(NPU_REG_STATUS);
    printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n", status_register);
    irq_triggered = false;
}

void u85_irq_handler(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

void test_u85(void)
{
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    NVIC_EnableIRQ(NPU0_IRQn);
}

void test_commands(void)
{
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x00000001);

    wait_for_irq();

    read_val = read_reg(NPU_REG_QREAD);
    write_reg(NPU_REG_CMD, 0x00000002);
    if ((read_val & 0x0FU) == 0x03U) {
        write_reg(NPU_REG_CMD, 0x00000000);
        printf("NPU completion poll: success\n");
        write_reg(NPU_REG_CMD, 0x0000000CU);
    }
}
"""

VENDOR_V12_OK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline void wait_for_irq(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }

    return 0U;
}

void test_u85(void)
{
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);

    irq_triggered = false;
    NVIC_DisableIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
    pmu_completion_poll_v12_t_irq_triggered_before_submit = irq_triggered ? 1U : 0U;

    if ((pmu_completion_poll_v12_t_nvic_enabled_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_nvic_pending_after_initial_clear != 0U) ||
        (pmu_completion_poll_v12_t_nvic_active_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_irq_triggered_before_submit != 0U)) {
        return;
    }
}

void test_commands(void)
{
    uint32_t status_at_success;

    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x00000001);
    pmu_completion_poll_v12_t_t2 = DWT->CYCCNT;

    status_at_success = v12_poll_completion();
    pmu_completion_poll_v12_t_poll_result = (status_at_success & 0x02U) ? V12_POLL_SUCCESS : V12_POLL_TIMEOUT;

    if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {
        /* V12_SUCCESS_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_at_success >> 16);
        pmu_completion_poll_v12_t_poll_status_at_success = status_at_success;

        /* V12_SUCCESS_CMD2_1 */
        write_reg(NPU_REG_CMD, 0x00000002);

        /* V12_SUCCESS_QREAD_READ */
        read_val = read_reg(NPU_REG_QREAD);
        if ((read_val & 0x0FU) == 0x03U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }

        /* V12_SUCCESS_CMD2_2 */
        write_reg(NPU_REG_CMD, 0x00000002);
        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }

    } else {
        /* V12_TIMEOUT_REPORT */
        irq_never_triggered = true;
        status_register = read_reg(NPU_REG_STATUS);
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n", status_register);

        /* V12_TIMEOUT_QREAD_READ */
        read_val = read_reg(NPU_REG_QREAD);
        if ((read_val & 0x0FU) == 0x03U) {
            pmu_completion_poll_v12_t_timeout_qread_verified = 1U;
        }

        /* V12_TIMEOUT_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }

v12_common_cleanup:
    /* common cleanup after both QREAD verification blocks */
    pmu_completion_poll_v12_t_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
    pmu_completion_poll_v12_t_irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;

    /* V12_CMD0 */
    write_reg(NPU_REG_CMD, 0x00000000);
    if (TEST_CPM) {
        /* V12_HPRINTF_SEAM */
        printf("V12: completed\n");
    }

    /* V12_CMD0C */
    write_reg(NPU_REG_CMD, 0x0000000CU);
}

void u85_irq_handler(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}
"""

# NOTE: Disassembly is synthetic, but ordered to match the required checkpoint
# shape and keep helper, branch, and cleanup order explicit.
DISASSEMBLY = """Disassembly of section .text:

00001000 <v12_poll_completion>:
   1000:\t4f10\tldr\tr0, [pc, #64] @ (1040 <v12_poll_completion+0x40>)
   1004:\tf8d0 2000\tldr.w\tr0, [r0]
   1008:\tf3bf 8f4f\tdsb\tsy
   100c:\tf8c3 2080\tstr.w\tr2, [r3, #128]     ; pmu_completion_poll_v12_t_poll_entry
   1010:\t... status load from 0x50004004
   1014:\ttst\tr3, #2
   1018:\tbeq\t1010 <v12_poll_completion+0x10>
   101c:\tf8c3 20c0\tstr.w\tr2, [r3, #192]     ; pmu_completion_poll_v12_t_status_completion_seen
   1020:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit
   1024:\tbx\tlr

00001100 <test_u85>:
   1100:\t...	bl\t__asm_nvic_set_vector
   1104:\t...	str\tr0, [r1]
   1108:\t...	bl\tNVIC_DisableIRQ
   110c:\t...	bl\tNVIC_ClearPendingIRQ
   1110:\t...	; installed_vector
   1114:\t...	; enable/pending/active reads

00001200 <test_commands>:
   1200:\t... read cmd
   1204:\t... write cmd |= 1
   1208:\t... t2 store
   120c:\tbl\tv12_poll_completion
   1210:\t... poll_result store
   1214:\tcbz\tr0, 1260 <pmu_completion_poll_v12_timeout>
   1218:\t... V12_SUCCESS_HISTORY_STORE
   121c:\t... V12_SUCCESS_CMD2_1
   1220:\t... V12_SUCCESS_QREAD_READ
   1224:\t... V12_SUCCESS_CMD2_2
   1228:\t... V12_CMD2_VERIFY path
   1230:\tb\t1270 <v12_common_cleanup>
   1260:\t... V12_TIMEOUT_REPORT
   1264:\t... V12_TIMEOUT_QREAD_READ
   1268:\t... V12_TIMEOUT_CMD2
   1270:\t... v12_common_cleanup

00001300 <u85_irq_handler>:
   1300:\t... status read
   1304:\t... irq_history_mask store
   1308:\t... irq_triggered = true
   1310:\t... CMD2
"""

NM = """00001000 T v12_poll_completion
00001100 T test_u85
00001200 T test_commands
00001260 T v12_common_cleanup
00001300 T u85_irq_handler

20002000 B pmu_completion_poll_v12_t_installed_vector
20002004 B pmu_completion_poll_v12_t_nvic_enabled_before_submit
20002008 B pmu_completion_poll_v12_t_nvic_pending_after_initial_clear
2000200c B pmu_completion_poll_v12_t_nvic_active_before_submit
20002010 B pmu_completion_poll_v12_t_irq_triggered_before_submit
20002014 B pmu_completion_poll_v12_t_t2
20002018 B pmu_completion_poll_v12_t_poll_entry
2000201c B pmu_completion_poll_v12_t_status_completion_seen
20002020 B pmu_completion_poll_v12_t_poll_exit
20002024 B pmu_completion_poll_v12_t_poll_result
20002028 B pmu_completion_poll_v12_t_poll_status_at_success
2000202c B pmu_completion_poll_v12_t_success_qread_verified
20002030 B pmu_completion_poll_v12_t_timeout_qread_verified
20002034 B pmu_completion_poll_v12_t_nvic_pending_before_final_clear
20002038 B pmu_completion_poll_v12_t_nvic_pending_after_final_clear
2000203c B pmu_completion_poll_v12_t_nvic_active_after_cleanup
20002040 B pmu_completion_poll_v12_t_irq_triggered_after_cleanup
"""

MANIFEST_OK = {
    "schema_version": SCHEMA_VERSION,
    "build_id": BUILD_ID,
    "runner_source_sha256": RUNNER_SHA256,
    "vendor_source_sha256": VENDOR_SHA256,
    "manifest_sha256": "OKMANIFESTSHA",
    "artifact_sha256": "OKBINHASH",
    "parser_sha256": "OKPARSE",
}


# --- deliberate mutations for the 27 required rejection cases ----------------

def _mutate_vendor_missing_first_success_cmd2(v):
    mutated = v.replace("/* V12_SUCCESS_CMD2_1 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n", "")
    return mutated


def _mutate_vendor_missing_second_success_cmd2(v):
    mutated = v.replace("/* V12_SUCCESS_CMD2_2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n", "")
    return mutated


def _mutate_vendor_three_success_cmd2(v):
    return v.replace("/* V12_SUCCESS_CMD2_2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n",
                     "/* V12_SUCCESS_CMD2_2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n        /* V12_SUCCESS_CMD2_3 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n", 1)


def _mutate_vendor_cmd2_after_qread(v):
    return v.replace("        /* V12_SUCCESS_CMD2_1 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n\n        /* V12_SUCCESS_QREAD_READ */",
                     "        /* V12_SUCCESS_QREAD_READ */", 1)


def _mutate_vendor_cmd2_before_qread(v):
    return v.replace("        /* V12_SUCCESS_QREAD_READ */\n        read_val = read_reg(NPU_REG_QREAD);",
                     "        write_reg(NPU_REG_CMD, 0x00000002);\n        /* V12_SUCCESS_QREAD_READ */\n        read_val = read_reg(NPU_REG_QREAD);", 1)


def _mutate_vendor_missing_timeout_cmd2(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n", "")


def _mutate_vendor_two_timeout_cmd2(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n",
                     "        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n        write_reg(NPU_REG_CMD, 0x00000002);\n", 1)


def _mutate_vendor_helper_cmd_write(v):
    return v.replace("        status = *status_reg;\n",
                     "        status = *status_reg;\n        write_reg(NPU_REG_CMD, 0x00000002);\n", 1)


def _mutate_vendor_insert_nvic_enable_active_path(v):
    return v.replace("    NVIC_DisableIRQ(NPU0_IRQn);\n    NVIC_ClearPendingIRQ(NPU0_IRQn);",
                     "    NVIC_EnableIRQ(NPU0_IRQn);\n    NVIC_DisableIRQ(NPU0_IRQn);\n    NVIC_ClearPendingIRQ(NPU0_IRQn);", 1)


def _mutate_vendor_insert_iser_set(v):
    return v.replace("    NVIC_ClearPendingIRQ(NPU0_IRQn);\n",
                     "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n    *(volatile uint32_t *)(0xE000E100U) |= (1U << NPU0_IRQn);\n", 1)


def _mutate_vendor_vector_v11_veneer(v):
    return v.replace("NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
                     "NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);")


def _mutate_vendor_reach_v11(v):
    return v.replace("    write_reg(NPU_REG_CMD, 0x00000002);\n        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {",
                     "    pmu_interval_v11a_t_j0 = DWT->CYCCNT;\n        write_reg(NPU_REG_CMD, 0x00000002);\n        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {")


def _mutate_vendor_success_status_reread(v):
    return v.replace("            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            return status;",
                     "            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            status = *status_reg;\n            return status;", 1)


def _mutate_vendor_status_from_reread(v):
    return v.replace("    status_at_success = v12_poll_completion();\n",
                     "    status_at_success = read_reg(NPU_REG_STATUS);\n")


def _mutate_disassembly_loop_back(v):
    return v + "\n   1028:\tb\t1008 <v12_poll_completion> ; loop-back after success path"


def _mutate_vendor_timeout_falls_into_success(v):
    return v.replace("    } else {\n        /* V12_TIMEOUT_REPORT */",
                     "    } else if ((status_at_success & 0x02U) != 0U) {\n", 1)


def _mutate_vendor_wrong_mask(v):
    return v.replace("if ((status & 0x02U) != 0U) {", "if ((status & 0x04U) != 0U) {")


def _mutate_vendor_extra_mmio_in_helper(v):
    return v.replace("        status = *status_reg;",
                     "        status = read_reg(NPU_REG_STATUS);\n        status = *status_reg;", 1)


def _mutate_vendor_per_iter_store(v):
    return v.replace("    for (uint32_t i = 0U; i < 10000U; ++i) {\n",
                     "    for (uint32_t i = 0U; i < 10000U; ++i) {\n        *(volatile uint32_t *)0x20000000U = i;\n", 1)


def _mutate_manifest_schema_drift(v):
    bad = dict(v)
    bad["schema_version"] = 11
    return bad


def _mutate_vendor_retain_enable_before_disable(v):
    return v.replace("    irq_triggered = false;\n    NVIC_DisableIRQ(NPU0_IRQn);\n",
                     "    irq_triggered = false;\n    NVIC_EnableIRQ(NPU0_IRQn);\n    NVIC_DisableIRQ(NPU0_IRQn);\n", 1)


def _mutate_vendor_reachable_true_store(v):
    return v.replace("irq_triggered = false;\n",
                     "irq_triggered = false;\n    irq_triggered = true;\n", 1)


def _mutate_vendor_history_wrong_source(v):
    return v.replace("irq_history_mask = (uint16_t)(status_at_success >> 16);",
                     "irq_history_mask = 0xABCDU;")


def _mutate_disassembly_inlined_helper(v):
    return v.replace("00001000 <v12_poll_completion>:\n", "")


def _mutate_vendor_merge_qread_verify(v):
    return v.replace("        if ((read_val & 0x0FU) == 0x03U) {\n            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n        }\n\n        /* V12_SUCCESS_CMD2_2 */",
                     "        if ((read_val & 0x0FU) == 0x03U) {}\n\n        /* V12_SUCCESS_CMD2_2 */", 1)


def _mutate_vendor_indirect_cmd_store(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);",
                     "((void(*)(uint32_t, uint32_t))((uint32_t)write_reg))(NPU_REG_CMD, 0x00000002);")


def _mutate_vendor_it_predicated_cmd(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);",
                     "        /* V12_TIMEOUT_CMD2 */\n        __asm volatile(\"itt ne\\n\\tbne.w 1f\\n\" : : : );\n        write_reg(NPU_REG_CMD, 0x00000002);\n1:", 1)


def _mutate_disassembly_wrong_p_order(v):
    return v + "\n#BROKEN_MODULAR_ORDER: poll_exit before status_seen"


def _mutate_manifest_parser_drift(v):
    bad = dict(v)
    bad["parser_sha256"] = "DRIFTED"
    return bad


def _mutate_disassembly_indirect_branch(v):
    return v.replace("   120c:\tbl\tv12_poll_completion", "   120c:\tblx\tr3")


def _validate_mutations():
    for name, fix in MUTATION_FIXTURES.items():
        if "vendor" in fix:
            _validate_text_mutation(
                name,
                fix["vendor"],
                VENDOR_V12_OK,
                fix.get("vendor_include", []),
                fix.get("vendor_exclude", []),
            )
            for needle, minimum in fix.get("vendor_count", {}).items():
                assert fix["vendor"].count(needle) >= minimum, "%s vendor count check failed for %r" % (name, needle)
        if "disassembly" in fix:
            _validate_text_mutation(
                name,
                fix["disassembly"],
                DISASSEMBLY,
                fix.get("disassembly_include", []),
                fix.get("disassembly_exclude", []),
            )
        if "manifest" in fix:
            _validate_manifest_mutation(name, fix["manifest"], MANIFEST_OK, fix.get("manifest_changes", {}))
        if "manifest_parser" in fix:
            _validate_manifest_mutation(name, fix["manifest_parser"], MANIFEST_OK, fix.get("manifest_parser_changes", {}))
        if "vendor_order" in fix:
            first, second = fix["vendor_order"]
            _validate_order(name, fix["vendor"], first, second)
        if "disassembly_order" in fix:
            first, second = fix["disassembly_order"]
            _validate_order(name, fix["disassembly"], first, second)


def _validate_text_mutation(name, mutated, base, include, exclude):
    assert mutated != base, "%s is a no-op" % name
    for needle in include:
        assert needle in mutated, "%s missing marker %r" % (name, needle)
    for needle in exclude:
        assert needle not in mutated, "%s still contains marker %r" % (name, needle)


def _validate_manifest_mutation(name, mutated, base, expected_changes):
    assert mutated != base, "%s manifest mutation is a no-op" % name
    for key, expected in expected_changes.items():
        assert mutated.get(key) == expected, "%s manifest key %s expected %r" % (name, key, expected)


def _validate_order(name, text, before, after):
    assert text.find(before) >= 0 and text.find(after) >= 0, "%s missing order markers" % name
    assert text.find(before) < text.find(after), "%s wrong marker order" % name


POSITIVE_SYMBOLS = {
    "helper_symbol": "v12_poll_completion",
    "runtime_vector_symbol": "u85_irq_handler",
    "status_load_symbol": "0x50004004",
    "completion_mask": "0x02",
    "poll_result_symbol": "pmu_completion_poll_v12_t_poll_result",
    "p0_symbol": "pmu_completion_poll_v12_t_poll_entry",
    "p1_symbol": "pmu_completion_poll_v12_t_status_completion_seen",
    "p2_symbol": "pmu_completion_poll_v12_t_poll_exit",
    "poll_status_symbol": "pmu_completion_poll_v12_t_poll_status_at_success",
    "history_mask_symbol": "irq_history_mask",
    "success_qread_symbol": "pmu_completion_poll_v12_t_success_qread_verified",
    "timeout_qread_symbol": "pmu_completion_poll_v12_t_timeout_qread_verified",
    "cmd2_success_1_symbol": "pmu_completion_poll_v12_t_success_cmd2_1",
    "cmd2_success_2_symbol": "pmu_completion_poll_v12_t_success_cmd2_2",
    "cmd2_timeout_symbol": "pmu_completion_poll_v12_t_timeout_cmd2",
    "cmd0_symbol": "PMU completion poll v12 cmd0 marker",
    "h_printf_symbol": "PMU completion poll v12 hprintf marker",
    "cmd0c_symbol": "PMU completion poll v12 cmd0xC marker",
}


MUTATION_FIXTURES = {
    "01_missing_success_cmd2_first": {
        "vendor": _mutate_vendor_missing_first_success_cmd2(VENDOR_V12_OK),
        "note": "missing success CMD2 #1",
        "vendor_exclude": ["V12_SUCCESS_CMD2_1"],
        "vendor_include": ["V12_SUCCESS_CMD2_2"],
    },
    "02_missing_success_cmd2_second": {
        "vendor": _mutate_vendor_missing_second_success_cmd2(VENDOR_V12_OK),
        "note": "missing success CMD2 #2",
        "vendor_exclude": ["V12_SUCCESS_CMD2_2"],
        "vendor_include": ["V12_SUCCESS_CMD2_1"],
    },
    "03_third_success_cmd2": {
        "vendor": _mutate_vendor_three_success_cmd2(VENDOR_V12_OK),
        "note": "extra third success CMD2",
        "vendor_include": ["V12_SUCCESS_CMD2_3"],
        "vendor_count": {"write_reg(NPU_REG_CMD, 0x00000002);": 3},
    },
    "04_success_cmd2_1_moved_after_qread": {
        "vendor": _mutate_vendor_cmd2_after_qread(VENDOR_V12_OK),
        "note": "success CMD2 #1 moved after QREAD",
        "vendor_include": ["V12_SUCCESS_QREAD_READ", "V12_SUCCESS_CMD2_2"],
        "vendor_exclude": ["V12_SUCCESS_CMD2_1"],
    },
    "05_success_cmd2_2_moved_before_qread": {
        "vendor": _mutate_vendor_cmd2_before_qread(VENDOR_V12_OK),
        "note": "success CMD2 #2 moved before QREAD",
        "vendor_include": ["V12_SUCCESS_CMD2_2", "V12_SUCCESS_QREAD_READ"],
    },
    "06_missing_timeout_cmd2": {
        "vendor": _mutate_vendor_missing_timeout_cmd2(VENDOR_V12_OK),
        "note": "missing timeout CMD2",
        "vendor_exclude": ["V12_TIMEOUT_CMD2"],
        "vendor_include": ["V12_TIMEOUT_REPORT", "V12_TIMEOUT_QREAD_READ"],
    },
    "07_two_timeout_cmd2": {
        "vendor": _mutate_vendor_two_timeout_cmd2(VENDOR_V12_OK),
        "note": "two timeout CMD2",
        "vendor_include": ["V12_TIMEOUT_CMD2"],
        "vendor_count": {"write_reg(NPU_REG_CMD, 0x00000002);": 4},
    },
    "08_helper_cmd2_injected": {
        "vendor": _mutate_vendor_helper_cmd_write(VENDOR_V12_OK),
        "note": "CMD write inside helper loop",
        "vendor_include": ["status = *status_reg;", "write_reg(NPU_REG_CMD, 0x00000002);"],
        "vendor_count": {"write_reg(NPU_REG_CMD, 0x00000002);": 3},
    },
    "09_active_path_nvic_enable": {
        "vendor": _mutate_vendor_insert_nvic_enable_active_path(VENDOR_V12_OK),
        "note": "NVIC_EnableIRQ on measured path",
        "vendor_include": ["NVIC_EnableIRQ(NPU0_IRQn)", "NVIC_DisableIRQ(NPU0_IRQn)", "NVIC_ClearPendingIRQ(NPU0_IRQn)"],
    },
    "10_iser_write": {
        "vendor": _mutate_vendor_insert_iser_set(VENDOR_V12_OK),
        "note": "direct NVIC ISER bit write",
        "vendor_include": ["E000E100U", "<< NPU0_IRQn"],
    },
    "11_v11_veneer_vector": {
        "vendor": _mutate_vendor_vector_v11_veneer(VENDOR_V12_OK),
        "note": "runtime vector changed to V11-A veneer",
        "vendor_include": ["v11a_u85_irq_entry_veneer"],
    },
    "12_reachable_j0_i0_t3": {
        "vendor": _mutate_vendor_reach_v11(VENDOR_V12_OK),
        "note": "V11 J0/I0/T3 path reachable",
        "vendor_include": ["pmu_interval_v11a_t_j0"],
    },
    "13_success_status_reread": {
        "vendor": _mutate_vendor_success_status_reread(VENDOR_V12_OK),
        "note": "successful path has status reread",
        "vendor_include": ["status = *status_reg;", "return status;"],
        "vendor_count": {"status = *status_reg;": 2},
    },
    "14_status_at_success_from_reread": {
        "vendor": _mutate_vendor_status_from_reread(VENDOR_V12_OK),
        "note": "status_at_success from non-branch-driving load",
        "vendor_include": ["status_at_success = read_reg(NPU_REG_STATUS);"],
        "vendor_exclude": ["status_at_success = v12_poll_completion();"],
    },
    "15_loop_back_after_p1": {
        "disassembly": _mutate_disassembly_loop_back(DISASSEMBLY),
        "note": "loop-back edge after P1",
        "disassembly_include": ["loop-back"],
    },
    "16_timeout_flows_to_success_cfg": {
        "vendor": _mutate_vendor_timeout_falls_into_success(VENDOR_V12_OK),
        "note": "timeout path reaches success CFG",
        "vendor_include": ["else if ((status_at_success & 0x02U) != 0U)"],
    },
    "17_wrong_completion_mask": {
        "vendor": _mutate_vendor_wrong_mask(VENDOR_V12_OK),
        "note": "completion mask changed from 0x02",
        "vendor_include": ["0x04U"],
    },
    "18_extra_helper_mmio": {
        "vendor": _mutate_vendor_extra_mmio_in_helper(VENDOR_V12_OK),
        "note": "extra MMIO in helper",
        "vendor_include": ["read_reg(NPU_REG_STATUS);", "status = *status_reg;"],
    },
    "19_per_iteration_store": {
        "vendor": _mutate_vendor_per_iter_store(VENDOR_V12_OK),
        "note": "per-iteration SRAM store inside helper loop",
        "vendor_include": ["0x20000000U"],
    },
    "20_broken_modular_identity": {
        "disassembly": _mutate_disassembly_wrong_p_order(DISASSEMBLY),
        "note": "timestamps violate modular-order identity",
        "disassembly_include": ["#BROKEN_MODULAR_ORDER"],
    },
    "21_cross_schema_parser_manifest_drift": {
        "manifest": _mutate_manifest_schema_drift(MANIFEST_OK),
        "manifest_parser": _mutate_manifest_parser_drift(MANIFEST_OK),
        "note": "cross-schema/parser/manifest mismatch",
        "manifest_changes": {"schema_version": 11},
        "manifest_parser_changes": {"parser_sha256": "DRIFTED"},
    },
    "22_retain_enable_before_disable": {
        "vendor": _mutate_vendor_retain_enable_before_disable(VENDOR_V12_OK),
        "note": "frozen NVIC_EnableIRQ retained before disable",
        "vendor_include": ["NVIC_EnableIRQ(NPU0_IRQn);", "NVIC_DisableIRQ(NPU0_IRQn);"],
        "vendor_order": ("NVIC_EnableIRQ(NPU0_IRQn);", "NVIC_DisableIRQ(NPU0_IRQn);"),
    },
    "23_reachable_irq_true_then_false": {
        "vendor": _mutate_vendor_reachable_true_store(VENDOR_V12_OK),
        "note": "reachable irq_triggered=true on measured path",
        "vendor_include": ["irq_triggered = false;", "irq_triggered = true;"],
    },
    "24_history_mask_not_from_success_status": {
        "vendor": _mutate_vendor_history_wrong_source(VENDOR_V12_OK),
        "note": "irq_history_mask from non-success status source",
        "vendor_include": ["0xABCDU"],
    },
    "25_helper_inlined_or_cloned_or_tailcall": {
        "disassembly": _mutate_disassembly_inlined_helper(DISASSEMBLY),
        "note": "helper inline/clone/tail-call",
        "disassembly_exclude": ["00001000 <v12_poll_completion>:"],
    },
    "26_success_timeout_merge_before_qread": {
        "vendor": _mutate_vendor_merge_qread_verify(VENDOR_V12_OK),
        "note": "success and timeout merged before QREAD verify",
        "vendor_include": ["/* V12_SUCCESS_QREAD_READ */"],
    },
    "27_indirect_or_it_predicated_cmd": {
        "vendor": _mutate_vendor_indirect_cmd_store(_mutate_vendor_it_predicated_cmd(VENDOR_V12_OK)),
        "disassembly": _mutate_disassembly_indirect_branch(DISASSEMBLY),
        "note": "indirect branch/IT-predicated CMD store",
        "vendor_include": ["((void(*)(uint32_t, uint32_t))", "__asm volatile(\"itt ne\\n\\tbne.w 1f\\n\""],
        "disassembly_include": ["blx\tr3"],
    },
}


if __name__ == "__main__":
    # Fail fast if mutation fixtures are accidentally no-op.
    _validate_mutations()

    check("runner fixture includes schema 12", SCHEMA_VERSION == 12)
    check("runner fixture pins build id", BUILD_ID == "0x32314950")
    check("runner fixture has frozen runner hash", RUNNER_SHA256 == "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b")
    check("stock vendor has 10000 spin bound", "10000U" in VENDOR_STOCK)
    check("stock vendor has sleep loop timeout behavior", "irq_never_triggered = true" in VENDOR_STOCK and "printf(\"TEST FAILED" in VENDOR_STOCK)
    check("stock vendor keeps separate ISR", "irq_triggered = true" in VENDOR_STOCK and "void u85_irq_handler" in VENDOR_STOCK)
    check("stock caller includes QREAD verify", "if ((read_val & 0x0FU) == 0x03U)" in VENDOR_STOCK)
    check("stock caller includes CMD0 and CMD0xC", "write_reg(NPU_REG_CMD, 0x00000000);" in VENDOR_STOCK and "write_reg(NPU_REG_CMD, 0x0000000CU);" in VENDOR_STOCK)

    check("v12 ordering preserves vector first", "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);" in VENDOR_V12_OK)
    check("v12 clear pre-read ordering", "/* V12_SUCCESS_CMD2_1 */" in VENDOR_V12_OK)
    check("v12 writes P0/P1/P2 only in helper", VENDOR_V12_OK.count("_poll_entry") == 1 and VENDOR_V12_OK.count("_status_completion_seen") == 1 and VENDOR_V12_OK.count("_poll_exit") == 1)
    check("v12 success and timeout verify remain distinct", "V12_SUCCESS_QREAD_READ" in VENDOR_V12_OK and "V12_TIMEOUT_QREAD_READ" in VENDOR_V12_OK)
    check("mutation fixture count is 27", len(MUTATION_FIXTURES) == 27)

    import check_pmu_completion_poll_v12 as gate
    import patches.patch_pmu_completion_poll_v12 as patcher

    check("runner patch emits v12 schema marker", "PMU_COMPLETION_POLL_DIAG_V12" in RUNNER)
    runner_out, runner_counts = patcher.patch_runner(RUNNER)
    vendor_out, vendor_counts = patcher.patch_vendor(VENDOR_STOCK)

    counts = gate.verify_generated_sources(runner_out, VENDOR_V12_OK)
    check("gate can parse positive generated source", counts.get("PMU_COMPLETION_POLL_V12_HELPER", 0) == 1)
    gate.verify_callsite_trace(runner_out, VENDOR_V12_OK, DISASSEMBLY, NM)

    for name, fix in MUTATION_FIXTURES.items():
        broken_vendor = fix.get("vendor", VENDOR_V12_OK)
        broken_disassembly = fix.get("disassembly", DISASSEMBLY)
        broken_manifest = fix.get("manifest", MANIFEST_OK)
        try:
            if "manifest" in fix:
                gate.validate_artifact_contract(json.dumps(broken_manifest))
            gate.verify_generated_sources(runner_out, broken_vendor)
            gate.verify_callsite_trace(runner_out, broken_vendor, broken_disassembly, NM)
            check("mutation rejected: %s" % name, False, fix["note"])
        except Exception:
            check("mutation rejected: %s" % name, True, fix["note"])

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
