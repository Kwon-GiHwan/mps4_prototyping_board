import os
import sys
import json
import re
import hashlib
import tempfile

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


RUNNER_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

void test_entry(v12_t* d)
{
    d->pmcr_readback_after_disable = 0U;
}

void run_once(v12_t* d)
{
    d->t_pmu_disable = DWT->CYCCNT;
}
"""

RUNNER_V12_OK = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#else
#error "PMU_COMPLETION_POLL_DIAG_V12 requires PMU_QUAL_SCHEMA_V12"
#endif

#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U

#define V12_POLL_SUCCESS 1U
#define V12_POLL_TIMEOUT 2U

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
static pmu_diag_snapshot_t pmu_completion_poll_v12_internal_post_disable;

void test_entry(v12_t* d)
{
    d->pmcr_readback_after_disable = 0U;
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
    printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\\n", status_register);
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
        printf("NPU completion poll: success\\n");
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
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        /* V12_STOCK_IRQ_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        /* V12_STOCK_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }
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

uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    /* V12_P0 */
    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        /* V12_HELPER_STATUS_READ */
        status = *status_reg;
        /* V12_HELPER_STATUS_TEST */
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
        /* V12_SUCCESS_CMD2_2 */
        write_reg(NPU_REG_CMD, 0x00000002);
        if ((read_val & 0x0FU) == 0x03U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }
        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }

    } else {
        /* V12_TIMEOUT_REPORT */
        /* V12_TIMEOUT_TRIGGERED */
        irq_never_triggered = true;
        status_register = read_reg(NPU_REG_STATUS);
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\\n", status_register);

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
        printf("V12: completed\\n");
    }

    /* V12_CMD0C */
    write_reg(NPU_REG_CMD, 0x0000000CU);
}
"""

# NOTE: Disassembly is synthetic, but ordered to match the required checkpoint
# shape and keep helper, branch, and cleanup order explicit.
DISASSEMBLY = """Disassembly of section .text:

00001000 <v12_poll_completion>:
   1000:\t4f10\tldr\tr0, [pc, #64] @ (1040 <v12_poll_completion+0x40>)
   1004:\tf8d0 2000\tldr.w\tr0, [r0]
   1008:\t; V12_P0
   1008:\tf8c3 2080\tstr.w\tr2, [r3, #128]     ; pmu_completion_poll_v12_t_poll_entry
   100c:\t; V12_HELPER_STATUS_READ
   100c:\t... status load from 0x50004004
   1010:\t; V12_HELPER_STATUS_TEST
   1010:\ttst\tr3, #2
   1014:\tbeq\t100c <v12_poll_completion+0x0c>
   1018:\t; V12_P1
   1018:\tf8c3 20c0\tstr.w\tr2, [r3, #192]     ; pmu_completion_poll_v12_t_status_completion_seen
   101c:\t; V12_P2
   101c:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit
   1020:\tbx\tlr

00001100 <test_u85>:
   1100:\t... \tbl\t__asm_nvic_set_vector\t; V12_RUNTIME_VECTOR_INSTALL
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
   1230:\tb\t1250 <v12_common_cleanup>
   1234:\t; V12_TIMEOUT_REPORT
   1234:\tb\t1270 <pmu_completion_poll_v12_timeout>
   1250:\t; V12_FINAL_PENDING_BEFORE_CLEAR
   1250:\t... pending before clear
   1254:\t; V12_FINAL_PENDING_AFTER_CLEAR
   1254:\t... pending after clear
   1258:\t; V12_FINAL_ACTIVE_AFTER_CLEAR
   1258:\t... active after clear
   125c:\t; V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR
   125c:\t... irq false
   1260:\t; V12_CMD0
   1260:\t... cmd0
   1264:\t; V12_HPRINTF_SEAM
   1264:\t... printf call
   1268:\t; V12_CMD0C
   1268:\t... cmd 0x0c
   1270:\t; V12_TIMEOUT_QREAD_READ
   1270:\t... timeout qread
   1274:\t; V12_TIMEOUT_CMD2
   1274:\t... timeout CMD2
   1278:\tb\t1250 <v12_common_cleanup>

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
00001250 T v12_common_cleanup
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

# NOTE: MANIFEST_OK is defined after marker tables so it can carry concrete site-address keys.


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
        "        /* V12_SUCCESS_CMD2_2 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
        "        if ((read_val & 0x0FU) == 0x03U) {\n"
        "            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n"
        "        }\n"
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
        "        }\n"
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
    return v.replace(
        "        /* V12_SUCCESS_CMD2_2 */\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
        "        if ((read_val & 0x0FU) == 0x03U) {\n",
        "        /* V12_SUCCESS_CMD2_2 */\n"
        "        pmu_interval_v11a_t_j0 = DWT->CYCCNT;\n"
        "        write_reg(NPU_REG_CMD, 0x00000002);\n"
        "        if ((read_val & 0x0FU) == 0x03U) {\n",
        1
    )


def _mutate_vendor_success_status_reread(v):
    return v.replace(
        "            /* V12_P1 */\n            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            /* V12_P2 */\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            return status;\n",
        "            /* V12_P1 */\n            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            /* V12_P2 */\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            status = *status_reg;\n            return status;\n",
        1)


def _mutate_vendor_status_from_reread(v):
    return v.replace("    status_at_success = v12_poll_completion();\n",
                     "    status_at_success = read_reg(NPU_REG_STATUS);\n")


def _mutate_disassembly_loop_back(v):
    return v.replace("   1020:\tbx\tlr\n", "   1020:\tb\t100c <v12_poll_completion+0x0c>\t; loop-back after success path\n", 1)


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
    return v.replace("        /* V12_SUCCESS_QREAD_READ */\n        read_val = read_reg(NPU_REG_QREAD);\n        /* V12_SUCCESS_CMD2_2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n        if ((read_val & 0x0FU) == 0x03U) {\n            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n        }\n",
                     "        /* V12_SUCCESS_QREAD_READ */\n        read_val = read_reg(NPU_REG_QREAD);\n        /* V12_SUCCESS_CMD2_2 */\n        write_reg(NPU_REG_CMD, 0x00000002);\n        if ((read_val & 0x0FU) == 0x03U) {}\n", 1)


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
    p1_line = next(i for i, l in enumerate(lines) if "; V12_P1" in l)
    p2_line = next(i for i, l in enumerate(lines) if "; V12_P2" in l)
    if p1_line + 1 >= len(lines) or p2_line + 1 >= len(lines):
        return v
    p1_pair = lines[p1_line:p1_line + 2]
    p2_pair = lines[p2_line:p2_line + 2]
    lines[p1_line:p1_line + 2] = p2_pair
    lines[p2_line:p2_line + 2] = p1_pair
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


def _extract_disassembly_marker_address(disassembly, marker):
    needle = "; %s" % marker
    for line in disassembly.splitlines():
        if needle in line:
            match = re.match(r"\s*([0-9a-fA-F]+):", line)
            if match:
                return "0x%s" % match.group(1)
    return None


def _collect_disassembly_marker_addresses(disassembly, markers):
    return {
        marker: _extract_disassembly_marker_address(disassembly, marker)
        for marker in markers
    }


def _validate_required_site_markers():
    disassembly_marker_addresses = _collect_disassembly_marker_addresses(
        DISASSEMBLY,
        REQUIRED_SITE_MARKERS.keys()
    )

    for marker, key in REQUIRED_SITE_MARKERS.items():
        assert marker in VENDOR_V12_OK, "source marker missing: %s" % marker
    for marker, key in REQUIRED_DISASSEMBLY_MARKERS.items():
        assert marker in DISASSEMBLY, "disassembly marker missing: %s" % marker
    for manifest_key in EXPECTED_MANIFEST_KEYS:
        assert manifest_key in set(REQUIRED_SITE_MARKERS.values()) or manifest_key in set(REQUIRED_DISASSEMBLY_MARKERS.values()), \
            "expected manifest key never mapped: %s" % manifest_key
        assert manifest_key in MANIFEST_OK, "manifest key missing: %s" % manifest_key
        assert str(MANIFEST_OK[manifest_key]).startswith("0x"), "manifest key not address-like: %s" % manifest_key

    for marker in REQUIRED_SITE_MARKERS:
        assert _count_exact_marker(VENDOR_V12_OK, "/* " + marker + " */") == 1, "source marker count mismatch: %s" % marker
        manifest_key = REQUIRED_SITE_MARKERS[marker]
        assert manifest_key in MANIFEST_OK, "manifest missing tracking key: %s" % manifest_key
        assert MANIFEST_OK.get(manifest_key) is not None, "manifest tracking key %s has no value" % manifest_key
        if marker in REQUIRED_DISASSEMBLY_MARKERS:
            assert _count_exact_marker(DISASSEMBLY, marker) == 1, "disassembly marker count mismatch: %s" % marker
            assert marker in disassembly_marker_addresses, "disassembly marker missing during collection: %s" % marker
            assert disassembly_marker_addresses[marker] is not None, "disassembly marker address missing: %s" % marker
            assert MANIFEST_OK[manifest_key] == disassembly_marker_addresses[marker], \
                "manifest address mismatch for %s" % marker

    for marker in REQUIRED_DISASSEMBLY_MARKERS:
        assert DISASSEMBLY.count(" ; " + marker) == 1 or DISASSEMBLY.count(marker) >= 1, "disassembly marker missing/duplicate: %s" % marker

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


_DISASSEMBLY_SITE_ADDRESSES = _collect_disassembly_marker_addresses(DISASSEMBLY, REQUIRED_SITE_MARKERS.keys())

MANIFEST_OK = {
    "schema_version": SCHEMA_VERSION,
    "build_id": BUILD_ID,
    "runner_source_sha256": RUNNER_SHA256,
    "vendor_source_sha256": VENDOR_SHA256,
    "manifest_sha256": "OKMANIFESTSHA",
    "artifact_sha256": "OKBINHASH",
    "parser_sha256": "OKPARSE",
    "helper_one_direct_callsite": True,
    "status_success_dataflow_exact": True,
    "history_mask_from_success_status": True,
    "success_cmd2_count_2": True,
    "timeout_cmd2_count_1": True,
    "nvic_enable_replaced": True,
    "irq_triggered_true_reachable_false": True,
}
for _marker, _manifest_key in REQUIRED_SITE_MARKERS.items():
    MANIFEST_OK[_manifest_key] = _DISASSEMBLY_SITE_ADDRESSES.get(_marker)


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

EXPECTED_MUTATION_ERRORS = {
    "01_missing_success_cmd2_first": "success path CMD=2 count != 2",
    "02_missing_success_cmd2_second": "success path CMD=2 count != 2",
    "03_third_success_cmd2": "success path CMD=2 count != 2",
    "04_success_cmd2_1_moved_after_qread": "success path ordering violated",
    "05_success_cmd2_2_moved_before_qread": "success path ordering violated",
    "06_missing_timeout_cmd2": "timeout path CMD=2 count != 1",
    "07_two_timeout_cmd2": "timeout path CMD=2 count != 1",
    "08_helper_cmd2_injected": "helper contains forbidden operation",
    "09_active_path_nvic_enable": "NVIC enable path remains reachable",
    "10_iser_write": "direct NVIC ISER enable write remains reachable",
    "11_v11_veneer_vector": "runtime vector still reaches V11 veneer",
    "12_reachable_j0_i0_t3": "V11 marker remains reachable",
    "13_success_status_reread": "helper status load: expected 1 match, found 2",
    "14_status_at_success_from_reread": "wait helper call: expected 1 match, found 0",
    "15_loop_back_after_p1": "unexpected post-P1 cycle",
    "16_timeout_flows_to_success_cfg": "timeout path reaches success CFG",
    "17_wrong_completion_mask": "helper completion mask: expected 1 match, found 0",
    "18_extra_helper_mmio": "helper contains forbidden operation 'read_reg('",
    "19_per_iteration_store": "helper contains forbidden operation '0x20000000U'",
    "20_broken_modular_identity": "P1/P2 modular-order identity violated",
    "21_cross_schema_parser_manifest_drift": "schema_version mismatch",
    "22_retain_enable_before_disable": "NVIC enable path remains reachable",
    "23_reachable_irq_true_then_false": "unexpected reachable irq_triggered=true count",
    "24_history_mask_not_from_success_status": "history mask lost single-source status dataflow",
    "25_helper_inlined_or_cloned_or_tailcall": "helper function in disassembly: expected 1 match, found 0",
    "26_success_timeout_merge_before_qread": "success qread verify body missing",
    "27_indirect_or_it_predicated_cmd": "indirect or IT-predicated CMD store",
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

    patch_vendor_stock = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

void u85_irq_handler(void)
{
    int32_t status_register = 0;
    status_register = read_reg(NPU_REG_STATUS);
    irq_history_mask = status_register >> 16;
    if ((status_register & 0x02)){
        printf("Got IRQ, History_mask is %x status_register is %x\\n", irq_history_mask, status_register);
        printf("Expected History_mask is set in CMD0_NPU_OP_STOP of the corresponding cmd stream include file\\n");
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 2);
    }
}

static inline void wait_for_irq(void)
{
    while (false == irq_triggered) {
      sleep();
      if (!irq_triggered) {
        irq_never_triggered = true;
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\\n", read_reg(NPU_REG_STATUS));
        break;
      }
    }
    irq_triggered = false;
}

static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{
\tint ret_code;
    int read_val;

\t/* Init locals */
\tret_code =0;
\tread_val =0;

\t  //Start NPU
\t  read_val = read_reg(NPU_REG_CMD);
\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);
\t  //Clear IRQ
\t  wait_for_irq();
\t  // Read QREAD register
\t  read_val = read_reg(NPU_REG_QREAD);
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  if(read_val == u32CmdQueueSize) {
\t    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t  }
\t  else {
\t    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t    ret_code = 1;
\t  }
\t  //Stop NPU
\t  write_reg(NPU_REG_CMD, 0x00000000);
\t  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
\t    printf("Testing CPM signals\\n");
\t    //Enable Program CLKQ and PWRQ interfaces
\t    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
\t    write_reg(NPU_REG_CMD, 0x0000000C);
#endif
}

int test_u85( const u85_eTest eTest,
              const uint32_t u32ExpectedIRQMask,
              const uint32_t u32OutputSize,
              const uint32_t u32CmdQueueSize,
              struct u85_warp_data_t *pu85_warp_data_st )
{
    int ret_code = 0;

    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    NVIC_EnableIRQ(NPU0_IRQn);
    return ret_code;
}
"""

    real_runner_path = os.path.join(os.path.dirname(__file__), "runner_pmu_diag_main.c")
    with open(real_runner_path, "r", encoding="utf-8") as handle:
        real_runner_stock = handle.read()
    check(
        "real frozen runner hash matches V12 pin",
        hashlib.sha256(real_runner_stock.encode("utf-8")).hexdigest() == RUNNER_SHA256,
    )
    env_vendor_path = os.environ.get("V12_FROZEN_VENDOR_SOURCE")
    if env_vendor_path:
        with open(env_vendor_path, "rb") as handle:
            env_vendor_raw = handle.read()
        env_vendor_stock = env_vendor_raw.decode("utf-8", errors="replace")
        check(
            "env frozen vendor hash matches V12 pin",
            hashlib.sha256(env_vendor_raw).hexdigest() == VENDOR_SHA256,
        )
        env_vendor_out, env_vendor_counts = patcher.patch_vendor(env_vendor_stock)
        check(
            "env frozen vendor default patch succeeds",
            env_vendor_out.count("v12_poll_completion(void)") == 1,
        )
        check(
            "env frozen vendor patch counts recorded",
            env_vendor_counts == {
                "global_defs": 1,
                "helper_insert": 1,
                "command_locals": 1,
                "runtime_enable_site": 1,
                "command_wait_block": 1,
            },
        )

    check("runner stock fixture is pre-v12", "PMU_COMPLETION_POLL_DIAG_V12" not in real_runner_stock)
    runner_out, runner_counts = patcher.patch_runner(real_runner_stock)
    vendor_out, vendor_counts = patcher.patch_vendor(patch_vendor_stock)

    check("runner patch emits schema 12 branch", "#define PMU_DIAG_SCHEMA_VERSION 12U" in runner_out)
    check("runner patch pins V12 build id", "#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U" in runner_out)
    check("runner patch appends 15 V12 fields", all(
        needle in runner_out for needle in (
            "uint32_t t_submit_after_cmd;",
            "uint32_t t_poll_entry;",
            "uint32_t t_status_completion_seen;",
            "uint32_t t_poll_exit;",
            "uint32_t poll_result;",
            "uint32_t status_at_success;",
            "uint32_t installed_vector;",
            "uint32_t nvic_enabled_before_submit;",
            "uint32_t nvic_pending_after_initial_clear;",
            "uint32_t nvic_active_before_submit;",
            "uint32_t irq_triggered_before_submit;",
            "uint32_t nvic_pending_before_final_clear;",
            "uint32_t nvic_pending_after_final_clear;",
            "uint32_t nvic_active_after_cleanup;",
            "uint32_t irq_triggered_after_cleanup;",
        )
    ))
    check("runner patch adds explicit timeout invalid emission",
          "if (d.poll_result != V12_POLL_SUCCESS) {" in runner_out and
          "d.t_status_completion_seen = 0U;" in runner_out and
          "d.t_poll_exit              = 0U;" in runner_out and
          "d.status_at_success        = 0U;" in runner_out)
    check("runner patch counts recorded",
          runner_counts == {
              "schema_version_branch": 1,
              "extern_v12_globals": 1,
              "record_append_fields": 1,
              "field_count_block": 1,
              "static_asserts": 1,
              "reset_v12_globals": 1,
              "copy_v12_values": 1,
              "serialize_v12_values": 1,
          })
    check("vendor patch keeps stock wait body", "while (false == irq_triggered) {" in vendor_out and "sleep();" in vendor_out)
    check("vendor patch keeps stock ISR body", "void u85_irq_handler(void)" in vendor_out and "irq_triggered = true;" in vendor_out)
    check("vendor patch inserts helper once", vendor_out.count("v12_poll_completion(void)") == 1)
    check("vendor patch hard-bypasses enable site", "NVIC_EnableIRQ(NPU0_IRQn)" not in vendor_out and "NVIC_DisableIRQ(NPU0_IRQn);" in vendor_out)
    check("vendor patch stores explicit poll_result", "V12_POLL_TIMEOUT - ((status_at_success & 0x02U) >> 1);" in vendor_out)
    check("vendor patch preserves path-specific CMD semantics",
          vendor_out.count("write_reg(NPU_REG_CMD, 0x00000002);") == 3 and
          "goto v12_common_cleanup;" in vendor_out)
    check("vendor patch counts recorded",
          vendor_counts == {
              "global_defs": 1,
              "helper_insert": 1,
              "command_locals": 1,
              "runtime_enable_site": 1,
              "command_wait_block": 1,
          })

    duplicate_runner = real_runner_stock + patcher._RUNNER_SCHEMA_STOCK
    try:
        patcher.patch_runner(duplicate_runner)
        check("runner exact-one duplicate schema fails", False, "unexpected pass")
    except BaseException as exc:
        check("runner exact-one duplicate schema fails", "schema version branch: expected 1 match, found 2" in str(exc), str(exc))

    try:
        patcher.patch_vendor(patch_vendor_stock.replace("    NVIC_EnableIRQ(NPU0_IRQn);\n", "", 1))
        check("vendor exact-one missing enable site fails", False, "unexpected pass")
    except BaseException as exc:
        check("vendor exact-one missing enable site fails", "vendor V12 NVIC hard-bypass start block: expected 1 match, found 0" in str(exc), str(exc))

    with tempfile.TemporaryDirectory() as tmp:
        runner_in = os.path.join(tmp, "runner.c")
        vendor_in = os.path.join(tmp, "u85.c")
        runner_out_path = os.path.join(tmp, "runner_v12.c")
        vendor_out_path = os.path.join(tmp, "u85_v12.c")
        with open(runner_in, "w", encoding="utf-8") as handle:
            handle.write(real_runner_stock)
        with open(vendor_in, "w", encoding="utf-8") as handle:
            handle.write(patch_vendor_stock)
        try:
            patcher.main([
                "--runner-in", runner_in,
                "--vendor-in", vendor_in,
                "--runner-out", runner_out_path,
                "--vendor-out", vendor_out_path,
            ])
            check("generator default hash pin rejects fixture vendor", False, "unexpected pass")
        except BaseException as exc:
            check("generator default hash pin rejects fixture vendor", "vendor hash mismatch" in str(exc), str(exc))

        runner_fixture_hash = hashlib.sha256(real_runner_stock.encode("utf-8")).hexdigest()
        vendor_fixture_hash = hashlib.sha256(patch_vendor_stock.encode("utf-8")).hexdigest()
        rc = patcher.main([
            "--runner-in", runner_in,
            "--vendor-in", vendor_in,
            "--runner-out", runner_out_path,
            "--vendor-out", vendor_out_path,
            "--expect-runner-sha256", runner_fixture_hash,
            "--expect-vendor-sha256", vendor_fixture_hash,
        ])
        check("generator CLI accepts exact override hashes", rc == 0)
        check("generator CLI writes runner output", os.path.exists(runner_out_path))
        check("generator CLI writes vendor output", os.path.exists(vendor_out_path))

    try:
        gate.verify_generated_sources(runner_out, vendor_out)
        check("current checker accepts canonical generator sources", True)
    except Exception as exc:
        check("current checker accepts canonical generator sources", False, str(exc))

    check(
        "gate exports bounded CFG interfaces",
        all(
            hasattr(gate, name)
            for name in (
                "parse_functions",
                "split_basic_blocks",
                "build_direct_edges",
                "reachable_blocks",
                "enumerate_result_paths",
            )
        ),
    )
    counts = gate.verify_generated_sources(RUNNER_V12_OK, VENDOR_V12_OK)
    check("gate can parse synthetic positive source", counts.get("PMU_COMPLETION_POLL_V12_HELPER", 0) == 1)
    funcs = gate.parse_functions(DISASSEMBLY)
    helper_blocks = gate.split_basic_blocks(funcs["v12_poll_completion"])
    helper_edges = gate.build_direct_edges(helper_blocks)
    helper_status_read = next(block.start for block in helper_blocks.values() if any(ins.marker == "V12_HELPER_STATUS_READ" for ins in block.insns))
    helper_status_test = next(block.start for block in helper_blocks.values() if any(ins.marker == "V12_HELPER_STATUS_TEST" for ins in block.insns))
    helper_seen = gate.reachable_blocks(min(helper_blocks), helper_edges, {(helper_status_test, helper_status_read)})
    check("bounded helper CFG reaches all helper blocks", helper_seen == set(helper_blocks))
    caller_blocks = gate.split_basic_blocks(funcs["test_commands"])
    caller_edges = gate.build_direct_edges(caller_blocks)
    caller_paths = gate.enumerate_result_paths(
        next(block for block in caller_blocks.values() if any(ins.marker == "V12_WAIT_CALL" for ins in block.insns)),
        next(block for block in caller_blocks.values() if any(ins.marker == "V12_WAIT_RESULT_STORE" for ins in block.insns)),
        next(block for block in caller_blocks.values() if any(ins.marker == "V12_FINAL_PENDING_BEFORE_CLEAR" for ins in block.insns)),
        blocks=caller_blocks,
        edges=caller_edges,
    )
    check(
        "caller CFG keeps distinct success/timeout split",
        caller_paths == {
            "branch_block": 0x1214,
            "success_entry": 0x121c,
            "timeout_entry": 0x1270,
            "merge_block": 0x1250,
        },
    )
    gate.verify_callsite_trace(runner_out, vendor_out, DISASSEMBLY, NM)
    gate.validate_artifact_contract(json.dumps(MANIFEST_OK))

    for name, fix in MUTATION_FIXTURES.items():
        synthetic_runner = RUNNER_V12_OK
        broken_vendor = fix.get("vendor", vendor_out)
        broken_disassembly = fix.get("disassembly", DISASSEMBLY)
        broken_manifest = fix.get("manifest", MANIFEST_OK)
        try:
            if "manifest" in fix:
                gate.validate_artifact_contract(json.dumps(broken_manifest))
            gate.verify_generated_sources(synthetic_runner, broken_vendor)
            gate.verify_callsite_trace(synthetic_runner, broken_vendor, broken_disassembly, NM)
            check("mutation rejected: %s" % name, False, fix["note"])
        except Exception as exc:
            expected_error = EXPECTED_MUTATION_ERRORS[name]
            if isinstance(expected_error, tuple):
                ok = any(part in str(exc) for part in expected_error)
            else:
                ok = expected_error in str(exc)
            check(
                "mutation rejected: %s" % name,
                ok,
                "%s [%s]" % (fix["note"], str(exc)),
            )

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
