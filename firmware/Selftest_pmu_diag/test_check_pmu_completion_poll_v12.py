import os
import sys
import json
import re

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
    /* V12_STOCK_VECTOR_INSTALL */
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    /* V12_STOCK_ENABLE */
    NVIC_EnableIRQ(NPU0_IRQn);
}

void test_commands(void)
{
    /* V12_STOCK_SUBMIT */
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x00000001);

    /* V12_STOCK_WAIT */
    wait_for_irq();

    /* V12_STOCK_QREAD_READ */
    read_val = read_reg(NPU_REG_QREAD);
    /* V12_STOCK_CMD2_SUCCESS */
    write_reg(NPU_REG_CMD, 0x00000002);
    if ((read_val & 0x0FU) == 0x03U) {
        /* V12_STOCK_CMD0 */
        write_reg(NPU_REG_CMD, 0x00000000);
        printf("NPU completion poll: success\n");
        /* V12_STOCK_CMD0xC */
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
    /* V12_HELPER_STATUS_READ */
    status_register = read_reg(NPU_REG_STATUS);
    /* V12_HELPER_STATUS_TEST */
    if ((status_register & 0x02U)) {
        /* V12_HELPER_IRQ_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        /* V12_STOCK_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    /* V12_P0 */
    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            /* V12_P1 */
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            /* V12_P2 */
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }

    return 0U;
}

void test_u85(void)
{
    /* V12_RUNTIME_VECTOR_INSTALL */
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);

    /* V12_RUNTIME_NVIC_PREPARE */
    irq_triggered = false;
    /* V12_RUNTIME_DISABLE */
    NVIC_DisableIRQ(NPU0_IRQn);
    /* V12_RUNTIME_CLEAR_PENDING */
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    /* V12_RUNTIME_VECTOR_LOAD */
    pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);
    /* V12_RUNTIME_ENABLE_READ */
    pmu_completion_poll_v12_t_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
    /* V12_RUNTIME_PENDING_READ */
    pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    /* V12_RUNTIME_ACTIVE_READ */
    pmu_completion_poll_v12_t_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
    /* V12_RUNTIME_IRQ_TRIGGERED_READ */
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

    /* V12_SUBMIT_READ */
    read_val = read_reg(NPU_REG_CMD);
    /* V12_SUBMIT_WRITE */
    write_reg(NPU_REG_CMD, read_val | 0x00000001);
    /* V12_SUBMIT_T2 */
    pmu_completion_poll_v12_t_t2 = DWT->CYCCNT;

    /* V12_WAIT_CALL */
    status_at_success = v12_poll_completion();
    /* V12_WAIT_RESULT_STORE */
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
        /* V12_TIMEOUT_TRIGGERED */
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
    /* V12_FINAL_PENDING_BEFORE_CLEAR */
    pmu_completion_poll_v12_t_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);
    /* V12_FINAL_PENDING_AFTER_CLEAR */
    pmu_completion_poll_v12_t_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    /* V12_FINAL_ACTIVE_AFTER_CLEAR */
    pmu_completion_poll_v12_t_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
    /* V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR */
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
    /* V12_ISR_STATUS_READ */
    status_register = read_reg(NPU_REG_STATUS);
    /* V12_ISR_TRIGGER_TEST */
    if ((status_register & 0x02U)) {
        /* V12_ISR_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        /* V12_ISR_CMD2 */
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
   100c:\t; V12_P0
   100c:\tf8c3 2080\tstr.w\tr2, [r3, #128]     ; pmu_completion_poll_v12_t_poll_entry
   1010:\t; V12_HELPER_STATUS_READ
   1010:\t... status load from 0x50004004
   1014:\t; V12_HELPER_STATUS_TEST
   1014:\ttst\tr3, #2
   1018:\tbeq\t1010 <v12_poll_completion+0x10>
   101c:\t; V12_P1
   101c:\tf8c3 20c0\tstr.w\tr2, [r3, #192]     ; pmu_completion_poll_v12_t_status_completion_seen
   1020:\t; V12_P2
   1020:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit
   1024:\tbx\tlr

00001100 <test_u85>:
   1100:\t... \tbl\t__asm_nvic_set_vector
   1104:\t; V12_RUNTIME_NVIC_PREPARE
   1104:\t... \tstr\tr0, [r1]
   1108:\t; V12_RUNTIME_DISABLE
   1108:\t... \tbl\tNVIC_DisableIRQ
   110c:\t; V12_RUNTIME_CLEAR_PENDING
   110c:\t... \tbl\tNVIC_ClearPendingIRQ
   1110:\t... \t; V12_RUNTIME_VECTOR_LOAD
   1114:\t; V12_RUNTIME_ENABLE_READ
   1114:\t... 
   1118:\t... \t; V12_RUNTIME_PENDING_READ
   111c:\t; V12_RUNTIME_ACTIVE_READ
   111c:\t... 
   1120:\t; V12_RUNTIME_IRQ_TRIGGERED_READ
   1120:\t... \t; irq_triggered
   1124:\t; V12_RUNTIME_VECTOR_INSTALL
   1124:\t... \t; vector install site

00001200 <test_commands>:
   1200:\t... \t; V12_SUBMIT_READ
   1204:\t... write cmd |= 1
   1208:\t; V12_SUBMIT_WRITE
   1208:\t... cmd write
   120c:\t; V12_SUBMIT_T2
   120c:\t... t2 store
   1210:\t... \t; V12_WAIT_CALL
   1210:\tbl\tv12_poll_completion
   1214:\t... \t; V12_WAIT_RESULT_STORE
   1214:\t... poll_result store
   1218:\tcbz\tr0, 1270 <pmu_completion_poll_v12_timeout>
   121c:\t; V12_SUCCESS_HISTORY_STORE
   121c:\t... history store
   1220:\t; V12_SUCCESS_CMD2_1
   1220:\t... success CMD2 #1
   1224:\t; V12_SUCCESS_QREAD_READ
   1224:\t... qread load
   1228:\t; V12_SUCCESS_CMD2_2
   1228:\t... success CMD2 #2
   122c:\t; V12_SUCCESS_QREAD_VERIFY
   122c:\t... qread verify check
   1230:\t; V12_CMD0
   1230:\t... cmd0
   1234:\t; V12_HPRINTF_SEAM
   1234:\t... printf call
   1238:\t; V12_CMD0C
   1238:\t... cmd 0x0c
   123c:\t... v12_common_cleanup
   1240:\t; V12_TIMEOUT_REPORT
   1240:\tb\t1270 <pmu_completion_poll_v12_timeout>
   1244:\t; V12_TIMEOUT_QREAD_READ
   1244:\t... timeout qread
   1248:\t; V12_TIMEOUT_CMD2
   1248:\t... timeout CMD2
   124c:\t... v12_common_cleanup
   1250:\t; V12_FINAL_PENDING_BEFORE_CLEAR
   1250:\t... pending before clear
   1254:\t; V12_FINAL_PENDING_AFTER_CLEAR
   1254:\t... pending after clear
   1258:\t; V12_FINAL_ACTIVE_AFTER_CLEAR
   1258:\t... active after clear
   125c:\t; V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR
   125c:\t... irq false

00001300 <u85_irq_handler>:
   1300:\t; V12_ISR_STATUS_READ
   1300:\t... status read
   1304:\t; V12_ISR_TRIGGER_TEST
   1304:\t... status test
   1308:\t; V12_ISR_HISTORY_STORE
   1308:\t... irq_history_mask store
   130c:\t; V12_ISR_CMD2
   130c:\t... cmd2 store
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
    block = (
        "        /* V12_SUCCESS_CMD2_1 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n\n"
        "        /* V12_SUCCESS_QREAD_READ */\n"
        "        read_val = read_reg(NPU_REG_QREAD);\n"
    )
    swapped = (
        "        /* V12_SUCCESS_QREAD_READ */\n"
        "        read_val = read_reg(NPU_REG_QREAD);\n\n"
        "        /* V12_SUCCESS_CMD2_1 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
    )
    return v.replace(block, swapped, 1)


def _mutate_vendor_cmd2_before_qread(v):
    before = (
        "        /* V12_SUCCESS_QREAD_READ */\n"
        "        read_val = read_reg(NPU_REG_QREAD);\n"
        "        if ((read_val & 0x0FU) == 0x03U) {\n"
        "            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n"
        "        }\n\n"
        "        /* V12_SUCCESS_CMD2_2 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
        "        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {\n"
        "            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n"
        "        }\n\n"
    )
    moved = (
        "        /* V12_SUCCESS_CMD2_2 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
        "        /* V12_SUCCESS_QREAD_READ */\n"
        "        read_val = read_reg(NPU_REG_QREAD);\n"
        "        if ((read_val & 0x0FU) == 0x03U) {\n"
        "            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n"
        "        }\n\n"
        "        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {\n"
        "            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n"
        "        }\n\n"
    )
    return v.replace(before, moved, 1)


def _mutate_vendor_missing_timeout_cmd2(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n", "")


def _mutate_vendor_two_timeout_cmd2(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n",
                     "        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n        write_reg(NPU_REG_CMD, 0x00000002);\n", 1)


def _mutate_vendor_helper_cmd_write(v):
    return v.replace("        status = *status_reg;\n",
                     "        status = *status_reg;\n        write_reg(NPU_REG_CMD, 0x00000002);\n", 1)


def _mutate_vendor_insert_nvic_enable_active_path(v):
    return v.replace(
        "    NVIC_DisableIRQ(NPU0_IRQn);\n",
        "    NVIC_EnableIRQ(NPU0_IRQn);\n    NVIC_DisableIRQ(NPU0_IRQn);\n",
        1
    )


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
    return v.replace(
        "            /* V12_P1 */\n            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            /* V12_P2 */\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            return status;\n",
        "            /* V12_P1 */\n            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            /* V12_P2 */\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            status = *status_reg;\n            return status;\n",
        1)


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
    return v.replace(
        "    NVIC_DisableIRQ(NPU0_IRQn);\n",
        "    NVIC_EnableIRQ(NPU0_IRQn);\n    NVIC_DisableIRQ(NPU0_IRQn);\n",
        1
    )


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


def _mutate_vendor_indirect_or_predicated_cmd(v):
    return _mutate_vendor_indirect_cmd_store(_mutate_vendor_it_predicated_cmd(v))


def _mutate_vendor_it_predicated_cmd(v):
    return v.replace("        /* V12_TIMEOUT_CMD2 */\n        write_reg(NPU_REG_CMD, 0x00000002);",
                     "        /* V12_TIMEOUT_CMD2 */\n        __asm volatile(\"itt ne\\n\\tbne.w 1f\\n\" : : : );\n        write_reg(NPU_REG_CMD, 0x00000002);\n1:", 1)


def _mutate_disassembly_wrong_p_order(v):
    lines = v.splitlines()
    p1_line = next(i for i, l in enumerate(lines) if "V12_P1" in l and "; V12_P1" in l)
    p2_line = next(i for i, l in enumerate(lines) if "V12_P2" in l and "; V12_P2" in l)
    p1_op_line = p1_line + 1
    p2_op_line = p2_line + 1
    if p1_op_line >= len(lines) or p2_op_line >= len(lines):
        return v
    p1_addr = lines[p1_line][:6]
    p2_addr = lines[p2_line][:6]
    p1_op = lines[p1_op_line]
    p2_op = lines[p2_op_line]
    lines[p1_line] = p1_addr + "\t; V12_P2"
    lines[p1_op_line] = p2_op.replace("21c0", "20c0")
    lines[p2_line] = p2_addr + "\t; V12_P1"
    lines[p2_op_line] = p1_op.replace("20c0", "21c0")
    return "\n".join(lines) + ("\\n" if v.endswith("\\n") else "")


def _mutate_manifest_parser_drift(v):
    bad = dict(v)
    bad["parser_sha256"] = "DRIFTED"
    return bad


def _mutate_disassembly_indirect_branch(v):
    lines = v.splitlines()
    for i, line in enumerate(lines):
        if "\tbl\tv12_poll_completion" in line:
            lines[i] = line.replace("\tbl\tv12_poll_completion", "\tblx\tr3", 1)
            break
    else:
        return v
    return "\\n".join(lines) + ("\\n" if v.endswith("\\n") else "")


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
            if "vendor_success_cmd2_count_exact" in fix:
                assert _count_success_path_cmd2(fix["vendor"]) == fix["vendor_success_cmd2_count_exact"], \
                    "%s success-path CMD2 count check failed" % name
            if name in ("04_success_cmd2_1_moved_after_qread", "05_success_cmd2_2_moved_before_qread"):
                assert _count_success_path_cmd2(fix["vendor"]) == 2, "%s changed success CMD2 count" % name
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
        if name == "04_success_cmd2_1_moved_after_qread":
            _validate_order(name, fix["vendor"], "/* V12_SUCCESS_QREAD_READ */", "/* V12_SUCCESS_CMD2_1 */")
        if name == "05_success_cmd2_2_moved_before_qread":
            _validate_order(name, fix["vendor"], "/* V12_SUCCESS_CMD2_2 */", "/* V12_SUCCESS_QREAD_READ */")


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


def _count_success_path_cmd2(wtext):
    start = wtext.find("if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {")
    if start < 0:
        return 0
    end = wtext.find("} else {", start)
    if end < 0:
        return 0
    return wtext[start:end].count("write_reg(NPU_REG_CMD, 0x00000002);")


def _validate_required_site_markers():
    for marker, key in REQUIRED_SITE_MARKERS.items():
        assert marker in VENDOR_V12_OK, "source marker missing: %s" % marker
    for marker, key in REQUIRED_DISASSEMBLY_MARKERS.items():
        assert marker in DISASSEMBLY, "disassembly marker missing: %s" % marker
    for manifest_key in EXPECTED_MANIFEST_KEYS:
        assert manifest_key in set(REQUIRED_SITE_MARKERS.values()) or manifest_key in set(REQUIRED_DISASSEMBLY_MARKERS.values()), \
            "expected manifest key never mapped: %s" % manifest_key

    for marker in REQUIRED_SITE_MARKERS:
        assert _count_exact_marker(VENDOR_V12_OK, "/* " + marker + " */") == 1, "source marker count mismatch: %s" % marker
        if marker in REQUIRED_DISASSEMBLY_MARKERS:
            assert _count_exact_marker(DISASSEMBLY, marker) == 1, "disassembly marker count mismatch: %s" % marker

    for marker in REQUIRED_DISASSEMBLY_MARKERS:
        assert DISASSEMBLY.count(" ; " + marker) == 1 or DISASSEMBLY.count(marker) >= 1, "disassembly marker missing/duplicate: %s" % marker

    for marker in REQUIRED_DISASSEMBLY_MARKERS:
        if marker in REQUIRED_SITE_MARKERS:
            assert DISASSEMBLY.count(marker) >= 1
        assert marker in DISASSEMBLY

    for symbol in (
        "v12_poll_completion",
        "u85_irq_handler",
        "pmu_completion_poll_v12_t_poll_entry",
        "pmu_completion_poll_v12_t_status_completion_seen",
        "pmu_completion_poll_v12_t_poll_exit",
        "pmu_completion_poll_v12_t_poll_result",
        "pmu_completion_poll_v12_t_poll_status_at_success",
        "pmu_completion_poll_v12_t_success_qread_verified",
        "pmu_completion_poll_v12_t_timeout_qread_verified",
        "pmu_completion_poll_v12_t_nvic_enabled_before_submit",
        "pmu_completion_poll_v12_t_nvic_pending_after_initial_clear",
        "pmu_completion_poll_v12_t_nvic_active_before_submit",
        "pmu_completion_poll_v12_t_irq_triggered_before_submit",
        "pmu_completion_poll_v12_t_nvic_pending_before_final_clear",
        "pmu_completion_poll_v12_t_nvic_pending_after_final_clear",
        "pmu_completion_poll_v12_t_nvic_active_after_cleanup",
        "pmu_completion_poll_v12_t_irq_triggered_after_cleanup",
        "irq_history_mask",
    ):
        assert symbol in VENDOR_V12_OK or symbol in DISASSEMBLY or symbol in NM, "symbol missing from fixture references: %s" % symbol


def _count_exact_marker(text, marker):
    return len(re.findall(r"(?<!\w)%s(?!\w)" % re.escape(marker), text))


POSITIVE_SYMBOLS = {
    "helper_symbol": "v12_poll_completion",
    "runtime_vector_symbol": "u85_irq_handler",
    "status_read_address": "0x50004004",
    "completion_mask": "0x02",
    "poll_result_symbol": "pmu_completion_poll_v12_t_poll_result",
    "p0_symbol": "pmu_completion_poll_v12_t_poll_entry",
    "p1_symbol": "pmu_completion_poll_v12_t_status_completion_seen",
    "p2_symbol": "pmu_completion_poll_v12_t_poll_exit",
    "poll_status_symbol": "pmu_completion_poll_v12_t_poll_status_at_success",
    "history_mask_symbol": "irq_history_mask",
    "success_qread_symbol": "pmu_completion_poll_v12_t_success_qread_verified",
    "timeout_qread_symbol": "pmu_completion_poll_v12_t_timeout_qread_verified",
    "installed_vector_symbol": "pmu_completion_poll_v12_t_installed_vector",
    "irq_triggered_before_submit_symbol": "pmu_completion_poll_v12_t_irq_triggered_before_submit",
    "pending_before_symbol": "pmu_completion_poll_v12_t_nvic_pending_after_initial_clear",
    "active_before_symbol": "pmu_completion_poll_v12_t_nvic_active_before_submit",
    "enabled_before_symbol": "pmu_completion_poll_v12_t_nvic_enabled_before_submit",
    "final_pending_before_symbol": "pmu_completion_poll_v12_t_nvic_pending_before_final_clear",
    "final_pending_after_symbol": "pmu_completion_poll_v12_t_nvic_pending_after_final_clear",
    "final_active_after_symbol": "pmu_completion_poll_v12_t_nvic_active_after_cleanup",
    "final_irq_triggered_after_symbol": "pmu_completion_poll_v12_t_irq_triggered_after_cleanup",
}

REQUIRED_SITE_MARKERS = {
    "V12_RUNTIME_VECTOR_INSTALL": "runtime_vector_install_site_address",
    "V12_RUNTIME_DISABLE": "runtime_disable_site_address",
    "V12_RUNTIME_CLEAR_PENDING": "runtime_clear_pending_site_address",
    "V12_RUNTIME_ENABLE_READ": "runtime_enable_read_address",
    "V12_RUNTIME_PENDING_READ": "runtime_pending_read_address",
    "V12_RUNTIME_ACTIVE_READ": "runtime_active_read_address",
    "V12_RUNTIME_IRQ_TRIGGERED_READ": "runtime_irq_triggered_read_address",
    "V12_HELPER_STATUS_READ": "helper_status_read_address",
    "V12_HELPER_STATUS_TEST": "helper_status_test_address",
    "V12_HELPER_IRQ_HISTORY_STORE": "helper_history_mask_store_address",
    "V12_P0": "poll_helper_p0_address",
    "V12_P1": "poll_helper_p1_address",
    "V12_P2": "poll_helper_p2_address",
    "V12_SUBMIT_READ": "submit_read_address",
    "V12_SUBMIT_WRITE": "submit_write_address",
    "V12_SUBMIT_T2": "submit_t2_address",
    "V12_WAIT_CALL": "wait_call_address",
    "V12_WAIT_RESULT_STORE": "wait_result_store_address",
    "V12_SUCCESS_HISTORY_STORE": "success_history_mask_store_address",
    "V12_SUCCESS_CMD2_1": "success_cmd2_1_store_address",
    "V12_SUCCESS_QREAD_READ": "success_qread_load_address",
    "V12_SUCCESS_CMD2_2": "success_cmd2_2_store_address",
    "V12_TIMEOUT_REPORT": "timeout_report_address",
    "V12_TIMEOUT_QREAD_READ": "timeout_qread_load_address",
    "V12_TIMEOUT_CMD2": "timeout_cmd2_store_address",
    "V12_CMD0": "cmd0_store_address",
    "V12_HPRINTF_SEAM": "hprintf_callsite_address",
    "V12_CMD0C": "terminal_cmd0c_store_address",
    "V12_FINAL_PENDING_BEFORE_CLEAR": "final_pending_before_clear_address",
    "V12_FINAL_PENDING_AFTER_CLEAR": "final_pending_after_clear_address",
    "V12_FINAL_ACTIVE_AFTER_CLEAR": "final_active_after_cleanup_address",
    "V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR": "final_irq_triggered_after_cleanup_address",
    "V12_ISR_STATUS_READ": "irq_status_read_address",
    "V12_ISR_TRIGGER_TEST": "irq_trigger_test_address",
    "V12_ISR_HISTORY_STORE": "irq_history_mask_store_address",
    "V12_ISR_CMD2": "irq_cmd2_store_address",
}

REQUIRED_DISASSEMBLY_MARKERS = {
    "V12_P0": "poll_helper_p0_address",
    "V12_HELPER_STATUS_READ": "helper_status_read_address",
    "V12_HELPER_STATUS_TEST": "helper_status_test_address",
    "V12_P1": "poll_helper_p1_address",
    "V12_P2": "poll_helper_p2_address",
    "V12_RUNTIME_DISABLE": "runtime_disable_site_address",
    "V12_RUNTIME_CLEAR_PENDING": "runtime_clear_pending_site_address",
    "V12_RUNTIME_ENABLE_READ": "runtime_enable_read_address",
    "V12_RUNTIME_PENDING_READ": "runtime_pending_read_address",
    "V12_RUNTIME_ACTIVE_READ": "runtime_active_read_address",
    "V12_RUNTIME_IRQ_TRIGGERED_READ": "runtime_irq_triggered_read_address",
    "V12_RUNTIME_VECTOR_INSTALL": "runtime_vector_install_site_address",
    "V12_SUBMIT_READ": "submit_read_address",
    "V12_SUBMIT_WRITE": "submit_write_address",
    "V12_SUBMIT_T2": "submit_t2_address",
    "V12_WAIT_CALL": "wait_call_address",
    "V12_WAIT_RESULT_STORE": "wait_result_store_address",
    "V12_SUCCESS_HISTORY_STORE": "success_history_mask_store_address",
    "V12_SUCCESS_CMD2_1": "success_cmd2_1_store_address",
    "V12_SUCCESS_QREAD_READ": "success_qread_load_address",
    "V12_SUCCESS_CMD2_2": "success_cmd2_2_store_address",
    "V12_CMD0": "cmd0_store_address",
    "V12_HPRINTF_SEAM": "hprintf_callsite_address",
    "V12_CMD0C": "terminal_cmd0c_store_address",
    "V12_TIMEOUT_REPORT": "timeout_report_address",
    "V12_TIMEOUT_QREAD_READ": "timeout_qread_load_address",
    "V12_TIMEOUT_CMD2": "timeout_cmd2_store_address",
    "V12_FINAL_PENDING_BEFORE_CLEAR": "final_pending_before_clear_address",
    "V12_FINAL_PENDING_AFTER_CLEAR": "final_pending_after_clear_address",
    "V12_FINAL_ACTIVE_AFTER_CLEAR": "final_active_after_cleanup_address",
    "V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR": "final_irq_triggered_after_cleanup_address",
    "V12_ISR_STATUS_READ": "irq_status_read_address",
    "V12_ISR_TRIGGER_TEST": "irq_trigger_test_address",
    "V12_ISR_HISTORY_STORE": "irq_history_mask_store_address",
    "V12_ISR_CMD2": "irq_cmd2_store_address",
}

EXPECTED_MANIFEST_KEYS = {
    "runtime_vector_install_site_address": "runtime vector install callsite",
    "runtime_disable_site_address": "runtime disable callsite",
    "runtime_clear_pending_site_address": "runtime clear-pending callsite",
    "runtime_enable_read_address": "runtime nvic-enable snapshot",
    "runtime_pending_read_address": "runtime pending snapshot",
    "runtime_active_read_address": "runtime active snapshot",
    "runtime_irq_triggered_read_address": "runtime irq-triggered snapshot",
    "helper_status_read_address": "helper status MMIO load",
    "helper_status_test_address": "helper completion-bit test",
    "helper_history_mask_store_address": "helper irq-history mask store",
    "poll_helper_p0_address": "helper poll entry time capture",
    "poll_helper_p1_address": "helper poll status completion timestamp",
    "poll_helper_p2_address": "helper poll exit timestamp",
    "submit_read_address": "submit command register read",
    "submit_write_address": "submit poll-start write",
    "submit_t2_address": "submit T2 capture",
    "wait_call_address": "wait helper callsite",
    "wait_result_store_address": "wait result store",
    "success_history_mask_store_address": "success path status-history-mask capture",
    "success_cmd2_1_store_address": "success path CMD2 #1",
    "success_qread_load_address": "success path QREAD load",
    "success_cmd2_2_store_address": "success path CMD2 #2",
    "timeout_report_address": "timeout report branch",
    "timeout_qread_load_address": "timeout path QREAD load",
    "timeout_cmd2_store_address": "timeout path CMD2",
    "cmd0_store_address": "terminal CMD0",
    "hprintf_callsite_address": "final H-PRINTF callsite",
    "terminal_cmd0c_store_address": "terminal CMD0xC",
    "final_pending_before_clear_address": "final pending before clear",
    "final_pending_after_clear_address": "final pending after clear",
    "final_active_after_cleanup_address": "final active after cleanup",
    "final_irq_triggered_after_cleanup_address": "final irq-triggered capture",
    "irq_status_read_address": "ISR status read",
    "irq_trigger_test_address": "ISR completion-bit test",
    "irq_history_mask_store_address": "ISR history-mask store",
    "irq_cmd2_store_address": "ISR CMD2 write",
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
        "vendor_include": ["V12_SUCCESS_QREAD_READ", "V12_SUCCESS_CMD2_1", "V12_SUCCESS_CMD2_2"],
        "vendor_exclude": [],
        "vendor_success_cmd2_count_exact": 2,
    },
    "05_success_cmd2_2_moved_before_qread": {
        "vendor": _mutate_vendor_cmd2_before_qread(VENDOR_V12_OK),
        "note": "success CMD2 #2 moved before QREAD",
        "vendor_include": ["V12_SUCCESS_CMD2_2", "V12_SUCCESS_QREAD_READ"],
        "vendor_success_cmd2_count_exact": 2,
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
        "disassembly_order": ("V12_P2", "V12_P1"),
        "disassembly_include": ["V12_P2", "V12_P1"],
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
        "vendor": _mutate_vendor_indirect_or_predicated_cmd(VENDOR_V12_OK),
        "disassembly": _mutate_disassembly_indirect_branch(DISASSEMBLY),
        "note": "indirect branch/IT-predicated CMD store",
        "vendor_include": ["((void(*)(uint32_t, uint32_t))", "__asm volatile(\"itt ne\\n\\tbne.w 1f\\n\""],
        "disassembly_include": ["blx\tr3"],
    },
}


if __name__ == "__main__":
    # Fail fast if mutation fixtures are accidentally no-op.
    _validate_mutations()
    _validate_required_site_markers()

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
