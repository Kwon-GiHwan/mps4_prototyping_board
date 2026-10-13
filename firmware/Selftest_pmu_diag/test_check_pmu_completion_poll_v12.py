import os
import sys
import json
import re
import hashlib
import shlex
import subprocess
import tempfile
import copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

MAKEFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Makefile.pmu_completion_poll_v12")

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-72s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def extract_makefile_gate_argv() -> list[str]:
    with open(MAKEFILE_PATH, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    for index, line in enumerate(lines):
        if line.startswith("manifest:"):
            recipe = []
            for body in lines[index + 1:]:
                if not body.startswith("\t"):
                    break
                piece = body.strip()
                if piece.endswith("\\"):
                    piece = piece[:-1].strip()
                recipe.append(piece)
            if not recipe:
                raise AssertionError("manifest recipe missing")
            joined = " ".join(recipe)
            tokens = shlex.split(joined)
            if tokens[:2] != ["python3", "$(GATE)"]:
                raise AssertionError("unexpected manifest recipe prefix: %r" % (tokens[:2],))
            return tokens[2:]
    raise AssertionError("manifest target missing")


def extract_makefile_gate_flags() -> list[str]:
    return [token for token in extract_makefile_gate_argv() if token.startswith("--")]


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
   1000:\t4f10\tldr\tr4, [pc, #64] @ (1044 <v12_poll_completion+0x44>)
   1004:\tf8d4 5000\tldr.w\tr5, [r4]
   1008:\t; V12_P0
   1008:\tf8c3 2080\tstr.w\tr2, [r3, #128]     ; pmu_completion_poll_v12_t_poll_entry
   100c:\t; V12_HELPER_STATUS_READ
   100c:\tf8d5 0004\tldr.w\tr0, [r5, #4]       ; helper STATUS load from 0x50004004
   1010:\t; V12_HELPER_STATUS_TEST
   1010:\tf010 0f02\ttst.w\tr0, #2
   1014:\tbeq\t100c <v12_poll_completion+0x0c>
   1018:\t; V12_P1
   1018:\tf8c3 20c0\tstr.w\tr2, [r3, #192]     ; pmu_completion_poll_v12_t_status_completion_seen
   101c:\t; V12_P2
   101c:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit
   1020:\tbx\tlr

00001100 <test_u85>:
   10fc:\t; V12_RUNTIME_VECTOR_VALUE
   10fc:\tf8df 1000\tldr.w\tr1, [pc]          ; 1300 <u85_irq_handler>
   1100:\t; V12_RUNTIME_VECTOR_INSTALL
   1100:\tf7ff f800\tbl\t1500 <NVIC_SetVector>
   1104:\t; V12_RUNTIME_NVIC_PREPARE
   1104:\tf881 0000\tstrb.w\tr0, [r1]
   1108:\t; V12_RUNTIME_DISABLE
   1108:\tf7ff f802\tbl\t1510 <NVIC_DisableIRQ>
   110c:\t; V12_RUNTIME_CLEAR_PENDING
   110c:\tf7ff f804\tbl\t1520 <NVIC_ClearPendingIRQ>
   1110:\t; V12_RUNTIME_VECTOR_LOAD
   1110:\tf7ff f806\tbl\t1530 <NVIC_GetVector>
   1114:\t; V12_RUNTIME_ENABLE_READ
   1114:\tf7ff f808\tbl\t1540 <NVIC_GetEnableIRQ>
   1118:\t; V12_RUNTIME_PENDING_READ
   1118:\tf7ff f80a\tbl\t1550 <NVIC_GetPendingIRQ>
   111c:\t; V12_RUNTIME_ACTIVE_READ
   111c:\tf7ff f80c\tbl\t1560 <NVIC_GetActive>
   1120:\t; V12_RUNTIME_IRQ_TRIGGERED_READ
   1120:\tf897 0010\tldrb.w\tr0, [r7, #16]

00001200 <test_commands>:
   1200:\t... \t; V12_SUBMIT_READ
   1204:\t... write cmd |= 1
   1208:\t; V12_SUBMIT_WRITE
   1208:\t... cmd write
   120c:\t; V12_SUBMIT_T2
   120c:\t... t2 store
   1210:\t... \t; V12_WAIT_CALL
   1210:\tbl\t1000 <v12_poll_completion>
   1214:\t... \t; V12_WAIT_RESULT_STORE
   1214:\t4624\tmov\tr4, r0
   1218:\tcbz\tr4, 127c <pmu_completion_poll_v12_timeout>
   121c:\t; V12_SUCCESS_HISTORY_STORE
   121c:\tf8cd 4010\tstr.w\tr4, [sp, #16]      ; status_at_success
   1220:\tea5f 4114\tlsrs.w\tr1, r4, #16
   1224:\tf8a7 1004\tstrh.w\tr1, [r7, #4]      ; irq_history_mask
   1228:\t; V12_SUCCESS_CMD2_1
   1228:\t... success CMD2 #1
   122c:\t; V12_SUCCESS_QREAD_READ
   122c:\tf8d7 6030\tldr.w\tr6, [r7, #48]      ; qread load
   1230:\t; V12_SUCCESS_CMD2_2
   1230:\t... success CMD2 #2
   1234:\t; V12_SUCCESS_QREAD_VERIFY
   1234:\tf016 060f\tands.w\tr6, r6, #15
   1238:\t2e03\tcmp\tr6, #3
   123c:\tb\t125c <v12_common_cleanup>
   1240:\t; V12_TIMEOUT_REPORT
   1240:\tb\t127c <pmu_completion_poll_v12_timeout>
   125c:\t; V12_FINAL_PENDING_BEFORE_CLEAR
   125c:\tf7ff f80a\tbl\t1550 <NVIC_GetPendingIRQ>
   1260:\t; V12_FINAL_PENDING_AFTER_CLEAR
   1260:\tf7ff f804\tbl\t1520 <NVIC_ClearPendingIRQ>
   1264:\t; V12_FINAL_ACTIVE_AFTER_CLEAR
   1264:\tf7ff f80a\tbl\t1550 <NVIC_GetPendingIRQ>
   1268:\t; V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR
   1268:\tf7ff f80c\tbl\t1560 <NVIC_GetActive>
   126c:\t; V12_CMD0
   126c:\tf887 0000\tstrb.w\tr0, [r7]
   1270:\t; V12_HPRINTF_SEAM
   1270:\tf7ff f810\tbl\t1900 <printf>
   1274:\t; V12_CMD0C
   1274:\tf887 000c\tstrb.w\tr0, [r7, #12]
   127c:\t; V12_TIMEOUT_QREAD_READ
   127c:\t... timeout qread
   1280:\t; V12_TIMEOUT_CMD2
   1280:\t... timeout CMD2
   1284:\tb\t125c <v12_common_cleanup>

00001300 <u85_irq_handler>:
   1300:\t; V12_ISR_STATUS_READ
   1300:\t... status read
   1304:\t; V12_ISR_TRIGGER_TEST
   1304:\t... status test
   1308:\t; V12_ISR_HISTORY_STORE
   1308:\t... irq_history_mask store
   130c:\t; V12_ISR_CMD2
   130c:\t... cmd2 store

00001700 <dead_debug_path>:
   1700:\tf7ff f846\tbl\t1600 <NVIC_EnableIRQ>
   1704:\tf04f 20e0\tmov.w\tr0, #3758153728  ; 0xE000E100
"""

NM = """00001000 T v12_poll_completion
00001100 T test_u85
00001200 T test_commands
0000125c T v12_common_cleanup
00001300 T u85_irq_handler
00001400 T wrong_helper
00001500 T NVIC_SetVector
00001510 T NVIC_DisableIRQ
00001520 T NVIC_ClearPendingIRQ
00001530 T NVIC_GetVector
00001540 T NVIC_GetEnableIRQ
00001550 T NVIC_GetPendingIRQ
00001560 T NVIC_GetActive
00001600 T NVIC_EnableIRQ
00001900 T printf

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

REAL_ARM_DISASSEMBLY = """Disassembly of section .text:

0000000031002344 <v12_poll_completion>:
31002344:\t4b0c      \tldr\tr3, [pc, #48]   @ (31002378 <v12_poll_completion+0x34>)
31002346:\t685a      \tldr\tr2, [r3, #4]
31002348:\t4b0c      \tldr\tr3, [pc, #48]   @ (3100237c <v12_poll_completion+0x38>)
3100234a:\t601a      \tstr\tr2, [r3, #0]
3100234c:\tf242 7210 \tmovw\tr2, #10000     @ 0x2710
31002350:\t490b      \tldr\tr1, [pc, #44]   @ (31002380 <v12_poll_completion+0x3c>)
31002352:\t4613      \tmov\tr3, r2
31002354:\t6848      \tldr\tr0, [r1, #4]
31002356:\tf010 0f02 \ttst.w\tr0, #2
3100235a:\td104      \tbne.n\t31002366 <v12_poll_completion+0x22>
3100235c:\t3a01      \tsubs\tr2, #1
3100235e:\t3b01      \tsubs\tr3, #1
31002360:\td1f8      \tbne.n\t31002354 <v12_poll_completion+0x10>
31002362:\t4610      \tmov\tr0, r2
31002364:\t4770      \tbx\tlr
31002366:\t4b04      \tldr\tr3, [pc, #16]   @ (31002378 <v12_poll_completion+0x34>)
31002368:\t6859      \tldr\tr1, [r3, #4]
3100236a:\t4a06      \tldr\tr2, [pc, #24]   @ (31002384 <v12_poll_completion+0x40>)
3100236c:\t6011      \tstr\tr1, [r2, #0]
3100236e:\t685a      \tldr\tr2, [r3, #4]
31002370:\t4b05      \tldr\tr3, [pc, #20]   @ (31002388 <v12_poll_completion+0x44>)
31002372:\t601a      \tstr\tr2, [r3, #0]
31002374:\t4770      \tbx\tlr
31002376:\tbf00      \tnop
31002378:\te0001000 \t.word\t0xe0001000
3100237c:\t31005370 \t.word\t0x31005370
31002380:\t50004000 \t.word\t0x50004000
31002384:\t3100536c \t.word\t0x3100536c
31002388:\t31005368 \t.word\t0x31005368

000000003100238c <u85_irq_handler>:
3100238c:\tb508      \tpush\t{r3, lr}
3100238e:\t4b0c      \tldr\tr3, [pc, #48]   @ (310023c0 <u85_irq_handler+0x34>)
31002390:\t685a      \tldr\tr2, [r3, #4]
31002392:\t0c11      \tlsrs\tr1, r2, #16
31002394:\t4b0b      \tldr\tr3, [pc, #44]   @ (310023c4 <u85_irq_handler+0x38>)
31002396:\t8019      \tstrh\tr1, [r3, #0]
31002398:\tf012 0f02 \ttst.w\tr2, #2
3100239c:\td100      \tbne.n\t310023a0 <u85_irq_handler+0x14>
3100239e:\tbd08      \tpop\t{r3, pc}
310023a0:\t8819      \tldrh\tr1, [r3, #0]
310023a2:\tb289      \tuxth\tr1, r1
310023a4:\t4808      \tldr\tr0, [pc, #32]   @ (310023c8 <u85_irq_handler+0x3c>)
310023a6:\tf7ff fe77 \tbl\t31002098 <__wrap_printf>
310023aa:\t4808      \tldr\tr0, [pc, #32]   @ (310023cc <u85_irq_handler+0x40>)
310023ac:\tf7ff fe74 \tbl\t31002098 <__wrap_printf>
310023b0:\t4b07      \tldr\tr3, [pc, #28]   @ (310023d0 <u85_irq_handler+0x44>)
310023b2:\t2201      \tmovs\tr2, #1
310023b4:\t701a      \tstrb\tr2, [r3, #0]
310023b6:\t4b02      \tldr\tr3, [pc, #8]    @ (310023c0 <u85_irq_handler+0x34>)
310023b8:\t2202      \tmovs\tr2, #2
310023ba:\t609a      \tstr\tr2, [r3, #8]
310023bc:\te7ef      \tb.n\t3100239e <u85_irq_handler+0x12>
310023be:\tbf00      \tnop
310023c0:\t50004000 \t.word\t0x50004000
310023c4:\t31005338 \t.word\t0x31005338
310023c8:\t310028f0 \t.word\t0x310028f0
310023cc:\t31002924 \t.word\t0x31002924
310023d0:\t3100533b \t.word\t0x3100533b

00000000310023d4 <test_commands>:
310023d4:\tb570      \tpush\t{r4, r5, r6, lr}
310023d6:\t4604      \tmov\tr4, r0
310023d8:\t460e      \tmov\tr6, r1
310023da:\t4615      \tmov\tr5, r2
310023dc:\t4860      \tldr\tr0, [pc, #384]  @ (31002560 <test_commands+0x18c>)
310023de:\tf7ff fe5b \tbl\t31002098 <__wrap_printf>
310023e2:\t4b60      \tldr\tr3, [pc, #384]  @ (31002564 <test_commands+0x190>)
310023e4:\t2200      \tmovs\tr2, #0
310023e6:\t609a      \tstr\tr2, [r3, #8]
31002438:\t4c4a      \tldr\tr4, [pc, #296]  @ (31002564 <test_commands+0x190>)
3100243a:\t4b4d      \tldr\tr3, [pc, #308]  @ (31002570 <test_commands+0x19c>)
3100243c:\t6523      \tstr\tr3, [r4, #80]   @ 0x50
31002482:\t2102      \tmovs\tr1, #2
31002484:\t483b      \tldr\tr0, [pc, #236]  @ (31002574 <test_commands+0x1a0>)
31002486:\tf7ff fe07 \tbl\t31002098 <__wrap_printf>
3100248a:\t2302      \tmovs\tr3, #2
3100248c:\t63a3      \tstr\tr3, [r4, #56]   @ 0x38
3100248e:\t68a3      \tldr\tr3, [r4, #8]
31002490:\tf043 0301 \torr.w\tr3, r3, #1
31002494:\t60a3      \tstr\tr3, [r4, #8]
31002496:\t4b38      \tldr\tr3, [pc, #224]  @ (31002578 <test_commands+0x1a4>)
31002498:\t685a      \tldr\tr2, [r3, #4]
3100249a:\t4b38      \tldr\tr3, [pc, #224]  @ (3100257c <test_commands+0x1a8>)
3100249c:\t601a      \tstr\tr2, [r3, #0]
3100249e:\tf7ff ff51 \tbl\t31002344 <v12_poll_completion>
310024a2:\tf3c0 0340 \tubfx\tr3, r0, #1, #1
310024a6:\tf1c3 0302 \trsb\tr3, r3, #2
310024aa:\t4a35      \tldr\tr2, [pc, #212]  @ (31002580 <test_commands+0x1ac>)
310024ac:\t6013      \tstr\tr3, [r2, #0]
310024ae:\t6813      \tldr\tr3, [r2, #0]
310024b0:\t2b01      \tcmp\tr3, #1
310024b2:\td037      \tbeq.n\t31002524 <test_commands+0x150>
310024b4:\t4b33      \tldr\tr3, [pc, #204]  @ (31002584 <test_commands+0x1b0>)
310024b6:\t2201      \tmovs\tr2, #1
310024b8:\t701a      \tstrb\tr2, [r3, #0]
310024ba:\t4c2a      \tldr\tr4, [pc, #168]  @ (31002564 <test_commands+0x190>)
310024bc:\t6861      \tldr\tr1, [r4, #4]
310024be:\t4832      \tldr\tr0, [pc, #200]  @ (31002588 <test_commands+0x1b4>)
310024c0:\tf7ff fdea \tbl\t31002098 <__wrap_printf>
310024c4:\t69a2      \tldr\tr2, [r4, #24]
310024c6:\t2302      \tmovs\tr3, #2
310024c8:\t60a3      \tstr\tr3, [r4, #8]
310024d8:\t4b2d      \tldr\tr3, [pc, #180]  @ (31002590 <test_commands+0x1bc>)
310024da:\tf8d3 2100 \tldr.w\tr2, [r3, #256] @ 0x100
310024de:\tf3c2 4200 \tubfx\tr2, r2, #16, #1
310024e2:\t492c      \tldr\tr1, [pc, #176]  @ (31002594 <test_commands+0x1c0>)
310024e4:\t600a      \tstr\tr2, [r1, #0]
310024e6:\tf44f 3280 \tmov.w\tr2, #65536    @ 0x10000
310024ea:\tf8c3 2180 \tstr.w\tr2, [r3, #384] @ 0x180
310024ee:\tf8d3 2100 \tldr.w\tr2, [r3, #256] @ 0x100
310024f2:\tf3c2 4200 \tubfx\tr2, r2, #16, #1
310024f6:\t4928      \tldr\tr1, [pc, #160]  @ (31002598 <test_commands+0x1c4>)
310024f8:\t600a      \tstr\tr2, [r1, #0]
310024fa:\tf8d3 3200 \tldr.w\tr3, [r3, #512] @ 0x200
310024fe:\tf3c3 4300 \tubfx\tr3, r3, #16, #1
31002502:\t4a26      \tldr\tr2, [pc, #152]  @ (3100259c <test_commands+0x1c8>)
31002504:\t6013      \tstr\tr3, [r2, #0]
31002506:\t4b26      \tldr\tr3, [pc, #152]  @ (310025a0 <test_commands+0x1cc>)
31002508:\t781b      \tldrb\tr3, [r3, #0]
3100250a:\tb2db      \tuxtb\tr3, r3
3100250c:\t4a25      \tldr\tr2, [pc, #148]  @ (310025a4 <test_commands+0x1d0>)
3100250e:\t6013      \tstr\tr3, [r2, #0]
31002510:\t4d14      \tldr\tr5, [pc, #80]   @ (31002564 <test_commands+0x190>)
31002512:\t2300      \tmovs\tr3, #0
31002514:\t60ab      \tstr\tr3, [r5, #8]
31002518:\tf7ff fdbe \tbl\t31002098 <__wrap_printf>
3100251c:\t230c      \tmovs\tr3, #12
3100251e:\t60ab      \tstr\tr3, [r5, #8]
31002524:\t4b21      \tldr\tr3, [pc, #132]  @ (310025ac <test_commands+0x1d8>)
31002526:\t6018      \tstr\tr0, [r3, #0]
31002528:\t0c00      \tlsrs\tr0, r0, #16
3100252a:\t4b21      \tldr\tr3, [pc, #132]  @ (310025b0 <test_commands+0x1dc>)
3100252c:\t8018      \tstrh\tr0, [r3, #0]
3100252e:\t2002      \tmovs\tr0, #2
31002530:\t60a0      \tstr\tr0, [r4, #8]
31002532:\t69a2      \tldr\tr2, [r4, #24]
31002534:\t60a0      \tstr\tr0, [r4, #8]
31002560:\t31002984 \t.word\t0x31002984
31002564:\t50004000 \t.word\t0x50004000
31002574:\t310029e8 \t.word\t0x310029e8
31002578:\te0001000 \t.word\t0xe0001000
3100257c:\t31005374 \t.word\t0x31005374
31002580:\t31005364 \t.word\t0x31005364
31002584:\t3100533a \t.word\t0x3100533a
31002588:\t31002ac0 \t.word\t0x31002ac0
3100258c:\t31002a60 \t.word\t0x31002a60
31002590:\te000e100 \t.word\t0xe000e100
31002594:\t31005348 \t.word\t0x31005348
31002598:\t31005344 \t.word\t0x31005344
3100259c:\t31005340 \t.word\t0x31005340
310025a0:\t3100533b \t.word\t0x3100533b
310025a4:\t3100533c \t.word\t0x3100533c
310025a8:\t31002b00 \t.word\t0x31002b00
310025ac:\t31005360 \t.word\t0x31005360
310025b0:\t31005338 \t.word\t0x31005338

00000000310025b8 <test_u85>:
310025b8:\te92d 43f8 \tstmdb\tsp!, {r3, r4, r5, r6, r7, r8, r9, lr}
310025c4:\t494f      \tldr\tr1, [pc, #316]  @ (31002704 <test_u85+0x14c>)
310025c6:\t4a50      \tldr\tr2, [pc, #320]  @ (31002708 <test_u85+0x150>)
310025c8:\t6893      \tldr\tr3, [r2, #8]
310025ca:\tf8c3 1080 \tstr.w\tr1, [r3, #128] @ 0x80
310025dc:\t4b4c      \tldr\tr3, [pc, #304]  @ (31002710 <test_u85+0x158>)
310025de:\tf44f 3080 \tmov.w\tr0, #65536    @ 0x10000
310025d8:\tf88c 3000 \tstrb.w\tr3, [ip]
310025e2:\tf8c3 0080 \tstr.w\tr0, [r3, #128] @ 0x80
310025ee:\tf8c3 0180 \tstr.w\tr0, [r3, #384] @ 0x180
310025f2:\t6892      \tldr\tr2, [r2, #8]
310025f4:\tf8d2 2080 \tldr.w\tr2, [r2, #128] @ 0x80
310025f8:\t4846      \tldr\tr0, [pc, #280]  @ (31002714 <test_u85+0x15c>)
310025fa:\t6002      \tstr\tr2, [r0, #0]
310025fc:\t681a      \tldr\tr2, [r3, #0]
310025fe:\tf3c2 4200 \tubfx\tr2, r2, #16, #1
31002602:\tf8df e114 \tldr.w\tlr, [pc, #276] @ (31002718 <test_u85+0x160>)
31002606:\tf8ce 2000 \tstr.w\tr2, [lr]
3100260a:\tf8d3 2100 \tldr.w\tr2, [r3, #256] @ 0x100
3100260e:\tf3c2 4200 \tubfx\tr2, r2, #16, #1
31002612:\tf8df e108 \tldr.w\tlr, [pc, #264] @ (3100271c <test_u85+0x164>)
31002616:\tf8ce 2000 \tstr.w\tr2, [lr]
3100261a:\tf8d3 2200 \tldr.w\tr2, [r3, #512] @ 0x200
3100261e:\tf3c2 4200 \tubfx\tr2, r2, #16, #1
31002622:\t4b3f      \tldr\tr3, [pc, #252]  @ (31002720 <test_u85+0x168>)
31002624:\t601a      \tstr\tr2, [r3, #0]
31002626:\tf89c 2000 \tldrb.w\tr2, [ip]
3100262a:\tb2d2      \tuxtb\tr2, r2
3100262c:\t4b3d      \tldr\tr3, [pc, #244]  @ (31002724 <test_u85+0x16c>)
3100262e:\t601a      \tstr\tr2, [r3, #0]
31002704:\t3100238d \t.word\t0x3100238d
31002708:\te000ed00 \t.word\t0xe000ed00
3100270c:\t3100533b \t.word\t0x3100533b
31002710:\te000e100 \t.word\t0xe000e100
31002714:\t3100535c \t.word\t0x3100535c
31002718:\t31005358 \t.word\t0x31005358
3100271c:\t31005354 \t.word\t0x31005354
31002720:\t31005350 \t.word\t0x31005350
31002724:\t3100534c \t.word\t0x3100534c
"""

REAL_ARM_NM = """31002344 t v12_poll_completion
3100238c T u85_irq_handler
310023d4 t test_commands
310025b8 T test_u85
31005338 B irq_history_mask
3100533b b irq_triggered
3100533c B pmu_completion_poll_v12_t_irq_triggered_after_cleanup
31005340 B pmu_completion_poll_v12_t_nvic_active_after_cleanup
31005344 B pmu_completion_poll_v12_t_nvic_pending_after_final_clear
31005348 B pmu_completion_poll_v12_t_nvic_pending_before_final_clear
3100534c B pmu_completion_poll_v12_t_irq_triggered_before_submit
31005350 B pmu_completion_poll_v12_t_nvic_active_before_submit
31005354 B pmu_completion_poll_v12_t_nvic_pending_after_initial_clear
31005358 B pmu_completion_poll_v12_t_nvic_enabled_before_submit
3100535c B pmu_completion_poll_v12_t_installed_vector
31005360 B pmu_completion_poll_v12_t_poll_status_at_success
31005364 B pmu_completion_poll_v12_t_poll_result
31005368 B pmu_completion_poll_v12_t_poll_exit
3100536c B pmu_completion_poll_v12_t_status_completion_seen
31005370 B pmu_completion_poll_v12_t_poll_entry
31005374 B pmu_completion_poll_v12_t_submit_after_cmd
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


def _mutate_disassembly_wrong_direct_callee(v):
    return v.replace("   1210:\tbl\t1000 <v12_poll_completion>\n",
                     "   1210:\tbl\t1400 <wrong_helper>\n", 1)


def _mutate_disassembly_status_dataflow_break(v):
    return v.replace("   1214:\t4624\tmov\tr4, r0\n",
                     "   1214:\t4622\tmov\tr2, r0\n", 1).replace(
                     "   121c:\tf8cd 4010\tstr.w\tr4, [sp, #16]      ; status_at_success\n",
                     "   121c:\tf8cd 2010\tstr.w\tr2, [sp, #16]      ; status_at_success\n", 1)


def _mutate_disassembly_alt_status_allocation(v):
    return (
        v.replace(
            "   100c:\tf8d5 0004\tldr.w\tr0, [r5, #4]       ; helper STATUS load from 0x50004004\n",
            "   100c:\tf8d5 3004\tldr.w\tr3, [r5, #4]       ; helper STATUS load from 0x50004004\n",
            1,
        )
        .replace("   1010:\tf010 0f02\ttst.w\tr0, #2\n", "   1010:\tf013 0f02\ttst.w\tr3, #2\n", 1)
        .replace("   101c:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit\n   1020:\tbx\tlr\n",
                 "   101c:\tf8c3 21c0\tstr.w\tr2, [r3, #256]     ; pmu_completion_poll_v12_t_poll_exit\n   1020:\t4618\tmov\tr0, r3\n   1024:\tbx\tlr\n",
                 1)
        .replace("   1214:\t4624\tmov\tr4, r0\n", "   1214:\t4606\tmov\tr6, r0\n", 1)
        .replace("   1218:\tcbz\tr4, 127c <pmu_completion_poll_v12_timeout>\n", "   1218:\tcbz\tr6, 127c <pmu_completion_poll_v12_timeout>\n", 1)
        .replace("   121c:\tf8cd 4010\tstr.w\tr4, [sp, #16]      ; status_at_success\n", "   121c:\tf8cd 6010\tstr.w\tr6, [sp, #16]      ; status_at_success\n", 1)
        .replace("   1220:\tea5f 4114\tlsrs.w\tr1, r4, #16\n", "   1220:\tea5f 6116\tlsrs.w\tr1, r6, #16\n", 1)
    )


def _mutate_disassembly_status_return_overwrite(v):
    return _mutate_disassembly_alt_status_allocation(v).replace(
        "   1020:\t4618\tmov\tr0, r3\n   1024:\tbx\tlr\n",
        "   1020:\t4618\tmov\tr0, r3\n   1024:\t2000\tmovs\tr0, #0\n   1028:\tbx\tlr\n",
        1,
    )


def _mutate_disassembly_wrong_vector_target(v):
    return v.replace("   10fc:\tf8df 1000\tldr.w\tr1, [pc]          ; 1300 <u85_irq_handler>\n",
                     "   10fc:\tf8df 1000\tldr.w\tr1, [pc]          ; 1400 <wrong_helper>\n", 1)


def _mutate_disassembly_enable_iser(v):
    return v.replace("   1114:\tf7ff f808\tbl\t1540 <NVIC_GetEnableIRQ>\n",
                     "   1114:\tf7ff f808\tbl\t1600 <NVIC_EnableIRQ>\n", 1)


def _mutate_disassembly_reachable_iser_write(v):
    return v.replace("   1118:\tf7ff f80a\tbl\t1550 <NVIC_GetPendingIRQ>\n",
                     "   1118:\tf04f 20e0\tmov.w\tr0, #3758153728  ; 0xE000E100\n", 1)


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
        if "\tbl\t1000 <v12_poll_completion>" in line:
            lines[i] = line.replace("\tbl\t1000 <v12_poll_completion>", "\tblx\tr3", 1)
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
    "variant": "PMU_COMPLETION_POLL_DIAG_V12",
    "schema_version": SCHEMA_VERSION,
    "build_id": BUILD_ID,
    "qualification_mode": "Q1",
    "evidence_source": "arm_elf",
    "expected_return_address": 0x1274,
    "characterization_only": True,
    "not_a_performance_baseline": True,
    "not_a_latency_measurement": True,
    "generated_private_driver_diagnostic_only": True,
    "production_end_only_frozen": True,
    "diagnostic_only": True,
    "not_numerically_comparable_to_v11a": True,
    "not_latency": True,
    "not_t_npu": True,
    "not_production": True,
    "not_mlek": True,
    "runner_source_sha256": RUNNER_SHA256,
    "vendor_source_sha256": VENDOR_SHA256,
    "manifest_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
    "artifact_bundle_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "parser_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
    "artifact_sha256": {
        "APP.BIN": "4".ljust(64, "4"),
        "VECTORS.BIN": "5".ljust(64, "5"),
        "DDR.BIN": "6".ljust(64, "6"),
    },
    "build_evidence_sha256": {
        "runner_pmu_completion_poll_v12.elf": "7".ljust(64, "7"),
        "runner_pmu_completion_poll_v12.map": "8".ljust(64, "8"),
        "generated_runner.c": RUNNER_SHA256,
        "generated_vendor_u85.c": VENDOR_SHA256,
        "checker_disassembly.txt": "9".ljust(64, "9"),
        "checker_nm.txt": "a".ljust(64, "a"),
    },
    "helper_symbol": "v12_poll_completion",
    "helper_address": "0x00001000",
    "runtime_vector_target_symbol": "u85_irq_handler",
    "runtime_vector_target_address": "0x00001300",
    "wait_call_target_address": "0x00001000",
    "wait_result_branch_block_address": "0x00001214",
    "success_entry_block_address": "0x0000121C",
    "timeout_entry_block_address": "0x0000127C",
    "merge_block_address": "0x0000125C",
    "helper_status_register_address": "0x50004004",
    "helper_completion_mask_value": "0x00000002",
    "success_cmd2_write_value": "0x00000002",
    "timeout_cmd2_write_value": "0x00000002",
    "qread_verify_mask_value": "0x0000000F",
    "qread_verify_expected_value": "0x00000003",
    "runtime_vector_api_symbol": "NVIC_SetVector",
    "nvic_disable_symbol": "NVIC_DisableIRQ",
    "nvic_clear_pending_symbol": "NVIC_ClearPendingIRQ",
    "nvic_get_vector_symbol": "NVIC_GetVector",
    "nvic_get_enable_symbol": "NVIC_GetEnableIRQ",
    "nvic_get_pending_symbol": "NVIC_GetPendingIRQ",
    "nvic_get_active_symbol": "NVIC_GetActive",
    "helper_one_direct_callsite": True,
    "helper_call_target_exact": True,
    "status_success_dataflow_exact": True,
    "history_mask_from_success_status": True,
    "success_cmd2_count_2": True,
    "timeout_cmd2_count_1": True,
    "nvic_enable_replaced": True,
    "irq_triggered_true_reachable_false": True,
    "runtime_vector_target_exact": True,
    "result_paths_distinct": True,
}
for _marker, _manifest_key in REQUIRED_SITE_MARKERS.items():
    MANIFEST_OK[_manifest_key] = _DISASSEMBLY_SITE_ADDRESSES.get(_marker)


def relocate_disassembly(disassembly_text: str, delta: int) -> str:
    def repl_line(match):
        return ("%04x" % (int(match.group(1), 16) + delta)) + match.group(2)
    def repl_target(match):
        return "%04x <" % (int(match.group(1), 16) + delta)
    text = re.sub(r"(?m)^(\s*[0-9a-fA-F]{4})(:)", lambda m: ("%04x" % (int(m.group(1), 16) + delta)) + m.group(2), disassembly_text)
    text = re.sub(r"\b([0-9a-fA-F]{4}) <", repl_target, text)
    return text


def relocate_nm(nm_text: str, delta: int) -> str:
    lines = []
    for line in nm_text.splitlines():
        parts = line.split()
        if len(parts) == 3 and re.fullmatch(r"[0-9A-Fa-f]+", parts[0]):
            lines.append("%08x %s %s" % (int(parts[0], 16) + delta, parts[1], parts[2]))
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if nm_text.endswith("\n") else "")


def _parameterized_real_fixture(disassembly_text: str, nm_text: str) -> tuple[str, str]:
    mutated_disassembly = (
        disassembly_text
        .replace("v12_poll_completion", "v13_poll_completion")
        .replace("pmu_completion_poll_v12_t_", "pmu_completion_poll_v13_t_")
        .replace(
            "31002356:\tf010 0f02 \ttst.w\tr0, #2",
            "31002356:\tf010 0002 \tands\tr0, r0, #2",
            1,
        )
        .replace(
            "31002398:\tf012 0f02 \ttst.w\tr2, #2",
            "31002398:\tf012 0202 \tands\tr2, r2, #2",
            1,
        )
    )
    mutated_nm = (
        nm_text
        .replace(" v12_poll_completion\n", " v13_poll_completion\n")
        .replace("pmu_completion_poll_v12_t_", "pmu_completion_poll_v13_t_")
    )
    return mutated_disassembly, mutated_nm


def move_cmd0c_after_return(disassembly_text: str) -> str:
    return disassembly_text.replace(
        "   1270:\t; V12_HPRINTF_SEAM\n"
        "   1270:\tf7ff f810\tbl\t1900 <printf>\n"
        "   1274:\t; V12_CMD0C\n"
        "   1274:\tf887 000c\tstrb.w\tr0, [r7, #12]\n",
        "   1270:\t; V12_HPRINTF_SEAM\n"
        "   1270:\tf7ff f810\tbl\t1900 <printf>\n"
        "   1274:\t46c0\tnop\n"
        "   1278:\t; V12_CMD0C\n"
        "   1278:\tf887 000c\tstrb.w\tr0, [r7, #12]\n",
        1,
    )


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
        "disassembly": _mutate_disassembly_wrong_direct_callee(DISASSEMBLY),
        "note": "wrong direct helper callee target",
        "disassembly_include": ["1400 <wrong_helper>"],
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
    "25_helper_inlined_or_cloned_or_tailcall": "helper direct call target mismatch",
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
    check(
        "runner patch exempts V12 from the S1/S2 private-driver compile trap",
        "#if (defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)) && !defined(PMU_QUAL_SCHEMA_V12)"
        in runner_out,
    )
    check(
        "runner patch exempts V12 from the v8 private-driver compile trap",
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_QUAL_SCHEMA_V12)"
        in runner_out,
    )
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
              "private_driver_seam_exemption": 1,
              "private_driver_v8_exemption": 1,
              "reset_v12_globals": 1,
              "copy_v12_values": 1,
              "serialize_v12_values": 1,
          })
    check("vendor patch keeps stock wait body", "while (false == irq_triggered) {" in vendor_out and "sleep();" in vendor_out)
    check("vendor patch keeps stock ISR body", "void u85_irq_handler(void)" in vendor_out and "irq_triggered = true;" in vendor_out)
    check("vendor patch inserts helper once", vendor_out.count("v12_poll_completion(void)") == 1)
    check(
        "vendor patch keeps caller auditable as noinline",
        "__attribute__((noinline))\nstatic int test_commands(" in vendor_out,
    )
    check("vendor patch declares poll result constants", all(
        needle in vendor_out for needle in (
            "#define V12_POLL_SUCCESS 1U",
            "#define V12_POLL_TIMEOUT 2U",
        )
    ))
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
            "timeout_entry": 0x127c,
            "merge_block": 0x125c,
        },
    )
    evidence = gate.verify_callsite_trace(runner_out, vendor_out, DISASSEMBLY, NM)
    gate.validate_artifact_contract(json.dumps(MANIFEST_OK), evidence)
    gate.validate_artifact_against_evidence(json.dumps(MANIFEST_OK), evidence)
    relocated_disassembly = relocate_disassembly(DISASSEMBLY, 0x200)
    relocated_nm = relocate_nm(NM, 0x200)
    relocated_evidence = gate.verify_callsite_trace(runner_out, vendor_out, relocated_disassembly, relocated_nm)
    relocated_manifest = copy.deepcopy(MANIFEST_OK)
    for key in (
        "helper_address",
        "runtime_vector_target_address",
        "wait_call_target_address",
        "wait_result_branch_block_address",
        "success_entry_block_address",
        "timeout_entry_block_address",
        "merge_block_address",
    ):
        relocated_manifest[key] = relocated_evidence[key]
    for key in gate.MANIFEST_MARKER_KEYS.values():
        relocated_manifest[key] = relocated_evidence[key]
    relocated_manifest["expected_return_address"] = int(relocated_evidence["terminal_cmd0c_store_address"], 16)
    relocated_manifest["expected_return_address"] = int(relocated_evidence["hprintf_callsite_address"], 16) + 4
    gate.validate_artifact_contract(json.dumps(relocated_manifest), relocated_evidence)
    gate.validate_artifact_against_evidence(json.dumps(relocated_manifest), relocated_evidence)
    broken_relocated = copy.deepcopy(relocated_manifest)
    broken_relocated["helper_address"] = "0x00001000"
    try:
        gate.validate_artifact_against_evidence(json.dumps(broken_relocated), relocated_evidence)
        check("manifest rejects relocated dynamic address mismatch", False, "unexpected pass")
    except Exception as exc:
        check("manifest rejects relocated dynamic address mismatch", "helper_address mismatch" in str(exc), str(exc))
    try:
        gate.verify_callsite_trace(runner_out, vendor_out, _mutate_disassembly_alt_status_allocation(DISASSEMBLY), NM)
        check("gate accepts allocation-agnostic status dataflow", True)
    except Exception as exc:
        check("gate accepts allocation-agnostic status dataflow", False, str(exc))
    try:
        gate.verify_callsite_trace(runner_out, vendor_out, _mutate_disassembly_status_dataflow_break(DISASSEMBLY), NM)
        check("gate rejects executable status dataflow break", False, "unexpected pass")
    except Exception as exc:
        check("gate rejects executable status dataflow break", "status success dataflow violated" in str(exc), str(exc))
    try:
        gate.verify_callsite_trace(runner_out, vendor_out, _mutate_disassembly_status_return_overwrite(DISASSEMBLY), NM)
        check("gate rejects helper return overwrite after status move", False, "unexpected pass")
    except Exception as exc:
        check("gate rejects helper return overwrite after status move", "status success dataflow violated" in str(exc), str(exc))
    for name, mutated_disassembly, expected in (
        ("gate rejects wrong runtime vector target in disassembly", _mutate_disassembly_wrong_vector_target(DISASSEMBLY), "runtime vector target mismatch"),
        ("gate rejects reachable NVIC enable in disassembly", _mutate_disassembly_enable_iser(DISASSEMBLY), "NVIC enable path remains reachable"),
        ("gate rejects reachable direct ISER write in disassembly", _mutate_disassembly_reachable_iser_write(DISASSEMBLY), "direct NVIC ISER enable write remains reachable"),
    ):
        try:
            gate.verify_callsite_trace(runner_out, vendor_out, mutated_disassembly, NM)
            check(name, False, "unexpected pass")
        except Exception as exc:
            check(name, expected in str(exc), str(exc))
    try:
        gate.verify_callsite_trace(runner_out, vendor_out, DISASSEMBLY, NM)
        check("gate ignores unreachable dead-function NVIC enable", True)
    except Exception as exc:
        check("gate ignores unreachable dead-function NVIC enable", False, str(exc))
    shifted_cmd0c = move_cmd0c_after_return(DISASSEMBLY)
    shifted_evidence = gate.verify_callsite_trace(runner_out, vendor_out, shifted_cmd0c, NM)
    shifted_manifest = copy.deepcopy(MANIFEST_OK)
    shifted_manifest["terminal_cmd0c_store_address"] = shifted_evidence["terminal_cmd0c_store_address"]
    shifted_manifest["expected_return_address"] = int(shifted_evidence["hprintf_callsite_address"], 16) + 4
    gate.validate_artifact_contract(json.dumps(shifted_manifest), shifted_evidence)
    check(
        "expected return address binds H-PRINTF return not CMD0xC",
        shifted_manifest["expected_return_address"] == int(shifted_evidence["hprintf_callsite_address"], 16) + 4
        and shifted_manifest["expected_return_address"] != int(shifted_evidence["terminal_cmd0c_store_address"], 16),
    )
    for name, key, value, expected in (
        ("manifest rejects wrong runner hash", "runner_source_sha256", "0" * 64, "runner_source_sha256 mismatch"),
        ("manifest rejects wrong vector symbol", "runtime_vector_target_symbol", "wrong_helper", "runtime_vector_target_symbol mismatch"),
        ("manifest rejects wrong NVIC symbol", "nvic_disable_symbol", "NVIC_EnableIRQ", "nvic_disable_symbol mismatch"),
        ("manifest rejects false critical boolean", "helper_call_target_exact", False, "manifest boolean missing or false: helper_call_target_exact"),
        ("manifest rejects stale wait callsite address", "wait_call_address", "0x00001234", "wait_call_address mismatch"),
        ("manifest rejects wrong expected return address", "expected_return_address", 0x1270, "expected_return_address mismatch"),
        ("manifest rejects fabricated boolean", "runtime_vector_target_exact", False, "manifest boolean missing or false: runtime_vector_target_exact"),
    ):
        broken = dict(MANIFEST_OK)
        broken[key] = value
        try:
            gate.validate_artifact_contract(json.dumps(broken), evidence)
            check(name, False, "unexpected pass")
        except Exception as exc:
            check(name, expected in str(exc), str(exc))

    with tempfile.TemporaryDirectory() as tmp:
        runner_path = os.path.join(tmp, "runner_generated.c")
        vendor_path = os.path.join(tmp, "vendor_generated.c")
        disassembly_path = os.path.join(tmp, "runner.dis")
        nm_path = os.path.join(tmp, "runner.nm")
        map_path = os.path.join(tmp, "runner.map")
        app_bin = os.path.join(tmp, "APP.BIN")
        vectors_bin = os.path.join(tmp, "VECTORS.BIN")
        ddr_bin = os.path.join(tmp, "DDR.BIN")
        manifest_path = os.path.join(tmp, "pmu_completion_poll_v12_manifest.json")
        for path, content in (
            (runner_path, RUNNER_V12_OK),
            (vendor_path, VENDOR_V12_OK),
            (disassembly_path, DISASSEMBLY),
            (nm_path, NM),
            (map_path, "MEMORY MAP\n"),
        ):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        for path, payload in (
            (app_bin, b"app"),
            (vectors_bin, b"vectors"),
            (ddr_bin, b"ddr"),
            (os.path.join(tmp, "runner.elf"), b"elf"),
        ):
            with open(path, "wb") as handle:
                handle.write(payload)
        recipe_flags = extract_makefile_gate_flags()
        parser = gate.build_arg_parser()
        parser_flags = {
            opt
            for action in parser._actions
            for opt in action.option_strings
            if opt.startswith("--")
        }
        check(
            "makefile recipe flags are accepted by checker argparse",
            all(flag in parser_flags for flag in recipe_flags),
            "unknown=%s" % [flag for flag in recipe_flags if flag not in parser_flags],
        )
        check(
            "makefile recipe flags match V12 real-elf contract",
            recipe_flags == [
                "--build-id",
                "--runner-generated",
                "--vendor-generated",
                "--elf",
                "--map",
                "--app-bin",
                "--vectors-bin",
                "--ddr-bin",
                "--objdump",
                "--nm",
                "--readelf",
                "--manifest-out",
            ],
            str(recipe_flags),
        )

        synthetic_cli_args = [
            "--build-id", BUILD_ID,
            "--runner-generated", runner_path,
            "--vendor-generated", vendor_path,
            "--allow-synthetic-evidence",
            "--disassembly-text", disassembly_path,
            "--nm-text", nm_path,
            "--map", map_path,
            "--app-bin", app_bin,
            "--vectors-bin", vectors_bin,
            "--ddr-bin", ddr_bin,
            "--manifest-out", manifest_path,
        ]
        cli_ok = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "check_pmu_completion_poll_v12.py"),
                *synthetic_cli_args,
            ],
            capture_output=True,
            text=True,
        )
        check("checker CLI accepts synthetic evidence fixture", cli_ok.returncode == 0, cli_ok.stderr or cli_ok.stdout)
        check("checker CLI writes manifest on success", os.path.exists(manifest_path) and os.path.getsize(manifest_path) > 0)
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                cli_manifest = json.load(handle)
            try:
                gate.validate_artifact_contract(json.dumps(cli_manifest), allow_synthetic=True)
                check(
                    "checker CLI synthetic manifest validates only with explicit allow",
                    cli_manifest.get("evidence_source") == "synthetic_fixture"
                    and cli_manifest.get("artifact_sha256", {}).keys() == {"APP.BIN", "VECTORS.BIN", "DDR.BIN"}
                    and "runner_pmu_completion_poll_v12.map" in cli_manifest.get("build_evidence_sha256", {}),
                )
            except Exception as exc:
                check("checker CLI synthetic manifest validates only with explicit allow", False, str(exc))
            try:
                gate.validate_artifact_contract(json.dumps(cli_manifest))
                check("checker CLI synthetic manifest rejected by default validator", False, "unexpected pass")
            except Exception as exc:
                check("checker CLI synthetic manifest rejected by default validator", "allow_synthetic" in str(exc), str(exc))

        missing_manifest = os.path.join(tmp, "missing_manifest.json")
        fail_args = list(synthetic_cli_args)
        dis_idx = fail_args.index("--disassembly-text")
        del fail_args[dis_idx:dis_idx + 2]
        manifest_idx = fail_args.index(manifest_path)
        fail_args[manifest_idx] = missing_manifest
        cli_fail = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "check_pmu_completion_poll_v12.py"),
                *fail_args,
            ],
            capture_output=True,
            text=True,
        )
        check("checker CLI rejects missing evidence inputs", cli_fail.returncode != 0, cli_fail.stderr or cli_fail.stdout)
        check("checker CLI does not write manifest on failure", not os.path.exists(missing_manifest))

        synthetic_without_flag_manifest = os.path.join(tmp, "synthetic_without_flag.json")
        synthetic_without_flag_args = [arg for arg in synthetic_cli_args if arg != "--allow-synthetic-evidence"]
        manifest_idx = synthetic_without_flag_args.index(manifest_path)
        synthetic_without_flag_args[manifest_idx] = synthetic_without_flag_manifest
        cli_no_allow = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "check_pmu_completion_poll_v12.py"),
                *synthetic_without_flag_args,
            ],
            capture_output=True,
            text=True,
        )
        check("synthetic CLI requires explicit allow flag", cli_no_allow.returncode != 0, cli_no_allow.stderr or cli_no_allow.stdout)
        check("synthetic CLI without allow flag writes no manifest", not os.path.exists(synthetic_without_flag_manifest))

    with tempfile.TemporaryDirectory() as tmp:
        runner_path = os.path.join(tmp, "runner_generated.c")
        vendor_path = os.path.join(tmp, "vendor_generated.c")
        elf_path = os.path.join(tmp, "runner.elf")
        map_path = os.path.join(tmp, "runner.map")
        app_bin = os.path.join(tmp, "APP.BIN")
        vectors_bin = os.path.join(tmp, "VECTORS.BIN")
        ddr_bin = os.path.join(tmp, "DDR.BIN")
        manifest_path = os.path.join(tmp, "pmu_completion_poll_v12_manifest.json")
        objdump_path = os.path.join(tmp, "fake_objdump.py")
        nm_tool_path = os.path.join(tmp, "fake_nm.py")
        readelf_path = os.path.join(tmp, "fake_readelf.py")
        bad_readelf_path = os.path.join(tmp, "bad_readelf.py")
        for path, content in (
            (runner_path, RUNNER_V12_OK),
            (vendor_path, VENDOR_V12_OK),
            (map_path, "MEMORY MAP\n"),
        ):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        for path, payload in (
            (elf_path, b"elf"),
            (app_bin, b"app"),
            (vectors_bin, b"vectors"),
            (ddr_bin, b"ddr"),
        ):
            with open(path, "wb") as handle:
                handle.write(payload)
        with open(objdump_path, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "from pathlib import Path\n"
                "mode = sys.argv[1]\n"
                "if mode == '-d':\n"
                "    sys.stdout.write(Path(sys.argv[2]).with_name('objdump_dis.txt').read_text())\n"
                "else:\n"
                "    raise SystemExit(2)\n"
            )
        with open(nm_tool_path, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "from pathlib import Path\n"
                "sys.stdout.write(Path(sys.argv[1]).with_name('nm_out.txt').read_text())\n"
            )
        with open(readelf_path, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "sys.stdout.write('ELF Header\\nType: EXEC (Executable file)\\nMachine: ARM\\n')\n"
            )
        with open(bad_readelf_path, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "sys.stdout.write('ELF Header\\nType: REL (Relocatable file)\\n')\n"
            )
        for script in (objdump_path, nm_tool_path, readelf_path, bad_readelf_path):
            os.chmod(script, 0o755)
        with open(os.path.join(tmp, "objdump_dis.txt"), "w", encoding="utf-8") as handle:
            handle.write(DISASSEMBLY)
        with open(os.path.join(tmp, "nm_out.txt"), "w", encoding="utf-8") as handle:
            handle.write(NM)

        real_cli_args = [
            "--build-id", BUILD_ID,
            "--runner-generated", runner_path,
            "--vendor-generated", vendor_path,
            "--elf", elf_path,
            "--map", map_path,
            "--app-bin", app_bin,
            "--vectors-bin", vectors_bin,
            "--ddr-bin", ddr_bin,
            "--objdump", objdump_path,
            "--nm", nm_tool_path,
            "--readelf", readelf_path,
            "--manifest-out", manifest_path,
        ]
        real_ok = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "check_pmu_completion_poll_v12.py"),
                *real_cli_args,
            ],
            capture_output=True,
            text=True,
        )
        check(
            "real-elf CLI rejects synthetic-looking evidence from fake toolchain",
            real_ok.returncode != 0 and "missing required V12 symbol" in (real_ok.stderr or real_ok.stdout),
            real_ok.stderr or real_ok.stdout,
        )
        check("real-elf CLI fake-tool path writes no manifest", not os.path.exists(manifest_path))
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                real_manifest = json.load(handle)
            try:
                gate.validate_artifact_contract(json.dumps(real_manifest))
                check(
                    "real-elf manifest validates by default",
                    real_manifest.get("evidence_source") == "arm_elf"
                    and real_manifest.get("variant") == "PMU_COMPLETION_POLL_DIAG_V12"
                    and real_manifest.get("qualification_mode") == "Q1"
                    and real_manifest.get("expected_return_address") == int(real_manifest["hprintf_callsite_address"], 16) + 4
                    and set(real_manifest.get("artifact_sha256", {}).keys()) == {"APP.BIN", "VECTORS.BIN", "DDR.BIN"}
                    and "runner_pmu_completion_poll_v12.elf" in real_manifest.get("build_evidence_sha256", {}),
                )
            except Exception as exc:
                check("real-elf manifest validates by default", False, str(exc))

        bad_manifest = os.path.join(tmp, "bad_real_manifest.json")
        bad_real_args = list(real_cli_args)
        bad_real_args[bad_real_args.index(readelf_path)] = bad_readelf_path
        bad_real_args[bad_real_args.index(manifest_path)] = bad_manifest
        real_fail = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "check_pmu_completion_poll_v12.py"),
                *bad_real_args,
            ],
            capture_output=True,
            text=True,
        )
        check("real-elf CLI rejects non-executable readelf result", real_fail.returncode != 0, real_fail.stderr or real_fail.stdout)
        check("real-elf CLI non-executable path writes no manifest", not os.path.exists(bad_manifest))

    for name, fix in MUTATION_FIXTURES.items():
        synthetic_runner = RUNNER_V12_OK
        broken_vendor = fix.get("vendor", vendor_out)
        broken_disassembly = fix.get("disassembly", DISASSEMBLY)
        broken_manifest = fix.get("manifest", MANIFEST_OK)
        try:
            if "manifest" in fix:
                gate.validate_artifact_contract(json.dumps(broken_manifest), evidence)
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

    try:
        real_evidence = gate.verify_callsite_trace(
            runner_out,
            vendor_out,
            REAL_ARM_DISASSEMBLY,
            REAL_ARM_NM,
            evidence_source="arm_elf",
        )
        check(
            "real fixture dispatches into real ELF verifier",
            real_evidence["helper_address"] == "0x31002344"
            and real_evidence["runtime_vector_target_address"] == "0x3100238C"
            and real_evidence["success_cmd2_count_2"] is True
            and real_evidence["timeout_cmd2_count_1"] is True,
        )
    except Exception as exc:
        check("real fixture dispatches into real ELF verifier", False, str(exc))

    try:
        default_contract = gate.DEFAULT_REAL_TRACE_CONTRACT
        check(
            "real verifier exports default V12 trace contract",
            isinstance(default_contract, gate.RealTraceContract)
            and default_contract.helper_symbol == "v12_poll_completion"
            and default_contract.trace_prefix == "pmu_completion_poll_v12_t_",
        )
    except Exception as exc:
        check("real verifier exports default V12 trace contract", False, str(exc))

    try:
        custom_disassembly, custom_nm = _parameterized_real_fixture(REAL_ARM_DISASSEMBLY, REAL_ARM_NM)
        custom_contract = gate.RealTraceContract(
            schema_version=13,
            build_id=0x33314950,
            runner_source_sha256="1" * 64,
            vendor_source_sha256="2" * 64,
            helper_symbol="v13_poll_completion",
            trace_prefix="pmu_completion_poll_v13_t_",
            completion_test_lowering=gate.RealTraceCompletionTestLowering(
                helper_mnemonic="ands",
                helper_status_register="r0",
                helper_dest_register="r0",
                irq_mnemonic="ands",
                irq_status_register="r2",
                irq_dest_register="r2",
                mask=2,
            ),
            caller_addresses=gate.RealTraceCallerAddresses(
                success_cmd2=(0x31002530, 0x31002534),
                other_cmd_stores=(0x310023E6, 0x31002494, 0x310024C8, 0x31002514, 0x3100251E),
                timeout_cmd2=0x310024C8,
                qread_loads=(0x310024C4, 0x31002532),
                cmd0=0x31002514,
                cmd0c=0x3100251E,
            ),
        )
        custom_evidence = gate.verify_callsite_trace(
            runner_out,
            vendor_out,
            custom_disassembly,
            custom_nm,
            evidence_source="arm_elf",
            real_trace_contract=custom_contract,
        )
        check(
            "real verifier accepts parameterized V13-style trace contract",
            custom_evidence["schema_version"] == 13
            and custom_evidence["build_id"] == "0x33314950"
            and custom_evidence["runner_source_sha256"] == "1" * 64
            and custom_evidence["vendor_source_sha256"] == "2" * 64
            and custom_evidence["helper_symbol"] == "v13_poll_completion",
        )
    except Exception as exc:
        check("real verifier accepts parameterized V13-style trace contract", False, str(exc))

    try:
        custom_disassembly, custom_nm = _parameterized_real_fixture(REAL_ARM_DISASSEMBLY, REAL_ARM_NM)
        gate.verify_callsite_trace(
            runner_out,
            vendor_out,
            custom_disassembly,
            custom_nm,
            evidence_source="arm_elf",
            real_trace_contract=gate.RealTraceContract(
                schema_version=13,
                build_id=0x33314950,
                runner_source_sha256="1" * 64,
                vendor_source_sha256="2" * 64,
                helper_symbol="v13_poll_completion",
                trace_prefix="pmu_completion_poll_v13_t_",
                completion_test_lowering=gate.RealTraceCompletionTestLowering(
                    helper_mnemonic="ands",
                    helper_status_register="r0",
                    helper_dest_register="r0",
                    irq_mnemonic="ands",
                    irq_status_register="r2",
                    irq_dest_register="r2",
                    mask=2,
                ),
                caller_addresses=gate.RealTraceCallerAddresses(
                    success_cmd2=(0x31002530, 0x31002538),
                    other_cmd_stores=(0x310023E6, 0x31002494, 0x310024C8, 0x31002514, 0x3100251E),
                    timeout_cmd2=0x310024C8,
                    qread_loads=(0x310024C4, 0x31002532),
                    cmd0=0x31002514,
                    cmd0c=0x3100251E,
                ),
            ),
        )
        check("real verifier binds caller address groups from contract", False, "unexpected pass")
    except Exception as exc:
        check("real verifier binds caller address groups from contract", "success CMD2" in str(exc), str(exc))

    for name, mutated_disassembly, expected in (
        (
            "real verifier rejects wrong runtime vector target literal",
            REAL_ARM_DISASSEMBLY.replace(".word\t0x3100238d", ".word\t0x31002345", 1),
            "runtime vector target is not exact stock handler",
        ),
        (
            "real verifier rejects duplicate STATUS load site",
            REAL_ARM_DISASSEMBLY.replace(
                "31002354:\t6848      \tldr\tr0, [r1, #4]",
                "31002353:\t684a      \tldr\tr2, [r1, #4]\n31002354:\t6848      \tldr\tr0, [r1, #4]",
                1,
            ),
            "helper STATUS static load site count != 1",
        ),
        (
            "real verifier rejects success CMD2 shape drift",
            REAL_ARM_DISASSEMBLY.replace("31002534:\t60a0      \tstr\tr0, [r4, #8]", "31002534:\t60e0      \tstr\tr0, [r4, #12]", 1),
            "real success CMD2 store shape changed",
        ),
        (
            "real verifier rejects success CMD2 value drift",
            REAL_ARM_DISASSEMBLY.replace("3100252e:\t2002      \tmovs\tr0, #2", "3100252e:\t2003      \tmovs\tr0, #3", 1),
            "success CMD2: expected value",
        ),
        (
            "real verifier rejects timeout CMD2 value drift",
            REAL_ARM_DISASSEMBLY.replace("310024c6:\t2302      \tmovs\tr3, #2", "310024c6:\t2303      \tmovs\tr3, #3", 1),
            "timeout CMD2: expected value",
        ),
        (
            "real verifier rejects history shift drift",
            REAL_ARM_DISASSEMBLY.replace("31002528:\t0c00      \tlsrs\tr0, r0, #16", "31002528:\t0c40      \tlsrs\tr0, r0, #17", 1),
            "history mask lost single-source",
        ),
        (
            "real verifier rejects terminal CMD0xC value drift",
            REAL_ARM_DISASSEMBLY.replace("3100251c:\t230c      \tmovs\tr3, #12", "3100251c:\t230d      \tmovs\tr3, #13", 1),
            "terminal CMD0xC: expected value",
        ),
    ):
        try:
            gate.verify_callsite_trace(
                runner_out,
                vendor_out,
                mutated_disassembly,
                REAL_ARM_NM,
                evidence_source="arm_elf",
            )
            check(name, False, "unexpected pass")
        except Exception as exc:
            check(name, expected in str(exc), str(exc))

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
