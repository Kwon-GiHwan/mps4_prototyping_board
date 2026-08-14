import hashlib
import os
import sys

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


def fail(message: str) -> AssertionError:
    return AssertionError(message)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1)


SCHEMA_VERSION = 13
BUILD_ID = "0x33314950"
POLL_LIMIT = 10000
INVALID_REMAINING = 0
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
EXPECTED_SOURCE_NEGATIVE_FIXTURES = {
    "duplicate_store",
    "extra_mmio",
    "per_iteration_increment_store",
    "remaining_before_p2",
    "retained_v12_hard_bypass",
    "retained_v12_qread_release_drift",
    "second_status_read",
    "success_remaining_10001",
    "success_remaining_zero",
    "timeout_reachable_store",
    "wrong_completion_mask",
}

REAL_RUNNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner_pmu_diag_main.c")
ENV_VENDOR_KEY = "V12_FROZEN_VENDOR_SOURCE"
PATCH_VENDOR_STOCK = """#define BUSY_SLEEP
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

RUNNER_RAW_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
}

void run_once(v13_t* d)
{
    d->t_pmu_disable = DWT->CYCCNT;
}
"""

VENDOR_RAW_STOCK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline uint32_t wait_for_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    for (uint32_t i = 0; i < 10000; ++i) {
        status = *status_reg;
        if (status & 0x02) {
            P1 = DWT;
            P2 = DWT;
            return status;
        }
    }

    return 0U;
}
"""

RUNNER_V12_GENERATED = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U
#endif
"""

VENDOR_V12_GENERATED = """uint32_t __attribute__((noinline)) v12_poll_completion(void)
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
"""

RUNNER_V13_OK = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_SCHEMA_VERSION 13U
#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U
#define V13_POLL_SUCCESS 1U
#define V13_POLL_TIMEOUT 2U
#define PMU_DIAG_FIELD_COUNT 101U
#define PMU_DIAG_TOTAL_WORDS 109U
#define PMU_DIAG_PAYLOAD_SIZE 436U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
typedef struct {
    uint32_t poll_result;
    uint32_t poll_status_at_success;
    uint32_t poll_remaining_at_success;
} v13_wire_tail_t;
extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
    d->poll_result = V13_POLL_TIMEOUT;
    d->poll_status_at_success = 0U;
    d->poll_remaining_at_success = 0U;
}

void emit_record(v13_t* d, uint32_t *out_words)
{
    out_words[100] = d->poll_remaining_at_success;
}
"""

VENDOR_V13_OK = """uint32_t __attribute__((noinline)) v13_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
            return status;
        }
    }

    return 0U;
}
"""

V12_NM_OK = """31002000 T v12_poll_completion
31003000 T u85_irq_handler
"""

V13_NM_OK = """32002040 T v13_poll_completion
32003020 T u85_irq_handler
32004200 T NVIC_EnableIRQ
"""

V12_OBJDUMP_OK = """31002000 <v12_poll_completion>:
31002000:   f242 7210   movw    r2, #10000      ; V12_FAILED_POLL_REMAINING_INIT
31002004:   f242 7110   movw    r1, #10000      ; V12_TIMEOUT_INIT
31002008:   4f0b        ldr     r7, [pc, #44]   ; V12_HELPER_STATUS_PTR
3100200a:   bf00        nop
3100200c:   f8d7 4000   ldr.w   r4, [r7]        ; V12_HELPER_STATUS_READ
31002010:   f014 0f02   tst.w   r4, #2          ; V12_HELPER_STATUS_TEST
31002014:   d105        bne.n   31002022 <v12_poll_completion+0x22>
31002016:   3a01        subs    r2, #1          ; V12_FAILED_POLL_DECREMENT
31002018:   3901        subs    r1, #1          ; V12_TIMEOUT_DECREMENT
3100201a:   d1f7        bne.n   3100200c <v12_poll_completion+0x0c>
3100201c:   2000        movs    r0, #0
3100201e:   4770        bx      lr
31002022:   4e08        ldr     r6, [pc, #32]   ; V12_DWT_CYCCNT_PTR
31002024:   6830        ldr     r0, [r6]        ; V12_P1_DWT_READ
31002026:   4d08        ldr     r5, [pc, #32]   ; V12_P1_STORE_PTR
31002028:   6028        str     r0, [r5]        ; V12_P1_STORE
3100202a:   6830        ldr     r0, [r6]        ; V12_P2_DWT_READ
3100202c:   4d08        ldr     r5, [pc, #32]   ; V12_P2_STORE_PTR
3100202e:   6028        str     r0, [r5]        ; V12_P2_STORE
31002030:   4620        mov     r0, r4
31002032:   4770        bx      lr
31002034:   .word   0x51000014   ; V12_HELPER_STATUS_ADDR
31002038:   .word   0xE0001004   ; V12_DWT_CYCCNT_ADDR
3100203c:   .word   0x20001000   ; V12_P1_STORE_ADDR
31002040:   .word   0x20001004   ; V12_P2_STORE_ADDR

31003000 <u85_irq_handler>:
31003000:   4770        bx      lr
"""

V13_OBJDUMP_OK = """32002040 <v13_poll_completion>:
32002040:   f242 7210   movw    r2, #10000      ; V13_FAILED_POLL_REMAINING_INIT
32002044:   f242 7110   movw    r1, #10000      ; V13_BACK_EDGE_INDUCTION_INIT
32002048:   4f0c        ldr     r7, [pc, #48]   ; V13_HELPER_STATUS_PTR
3200204a:   bf00        nop
3200204c:   f8d7 4000   ldr.w   r4, [r7]        ; V13_HELPER_STATUS_READ
32002050:   f014 0f02   tst.w   r4, #2          ; V13_HELPER_STATUS_TEST
32002054:   d105        bne.n   32002062 <v13_poll_completion+0x22>
32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT
32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT
3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>
3200205c:   2000        movs    r0, #0
3200205e:   4770        bx      lr
32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR
32002064:   6830        ldr     r0, [r6]        ; V13_P1_DWT_READ
32002066:   4d09        ldr     r5, [pc, #36]   ; V13_P1_STORE_PTR
32002068:   6028        str     r0, [r5]        ; V13_P1_STORE
3200206a:   6830        ldr     r0, [r6]        ; V13_P2_DWT_READ
3200206c:   4d09        ldr     r5, [pc, #36]   ; V13_P2_STORE_PTR
3200206e:   6028        str     r0, [r5]        ; V13_P2_STORE
32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR
32002072:   6029        str     r1, [r5]        ; V13_REMAINING_STORE
32002074:   4620        mov     r0, r4
32002076:   4770        bx      lr
32002078:   .word   0x51000014   ; V13_HELPER_STATUS_ADDR
3200207c:   .word   0xE0001004   ; V13_DWT_CYCCNT_ADDR
32002080:   .word   0x20002000   ; V13_P1_STORE_ADDR
32002084:   .word   0x20002004   ; V13_P2_STORE_ADDR
32002088:   .word   0x20002008   ; V13_REMAINING_STORE_ADDR

32003020 <u85_irq_handler>:
32003020:   4770        bx      lr
"""


def _replace_once_exact(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise fail("%s old text missing" % label)
    return replace_once(text, old, new, label)


def _replace_block(text: str, old: str, new: str, label: str) -> str:
    return _replace_once_exact(text, old, new, label)


def _elf_negative_fixtures() -> dict[str, dict[str, str]]:
    return {
        "extra_loop_mov": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002054:   d105        bne.n   32002062 <v13_poll_completion+0x22>\n"
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205c:   2000        movs    r0, #0\n"
                "3200205e:   4770        bx      lr\n"
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "32002054:   d106        bne.n   32002064 <v13_poll_completion+0x24>\n"
                "32002056:   4629        mov     r1, r5          ; V13_EXTRA_LOOP_MOV\n"
                "32002058:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "3200205a:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205c:   d1f6        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205e:   2000        movs    r0, #0\n"
                "32002060:   4770        bx      lr\n"
                "32002064:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "extra-loop-mov",
            ),
            "nm": V13_NM_OK,
            "expected": "extra per-iteration instruction",
        },
        "extra_loop_store": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002054:   d105        bne.n   32002062 <v13_poll_completion+0x22>\n"
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205c:   2000        movs    r0, #0\n"
                "3200205e:   4770        bx      lr\n"
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "32002054:   d106        bne.n   32002064 <v13_poll_completion+0x24>\n"
                "32002056:   6019        str     r1, [r3]        ; V13_EXTRA_LOOP_STORE\n"
                "32002058:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "3200205a:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205c:   d1f6        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205e:   2000        movs    r0, #0\n"
                "32002060:   4770        bx      lr\n"
                "32002064:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "extra-loop-store",
            ),
            "nm": V13_NM_OK,
            "expected": "extra per-iteration store",
        },
        "extra_loop_spill_reload": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002054:   d105        bne.n   32002062 <v13_poll_completion+0x22>\n"
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205c:   2000        movs    r0, #0\n"
                "3200205e:   4770        bx      lr\n"
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "32002054:   d107        bne.n   32002068 <v13_poll_completion+0x28>\n"
                "32002056:   9300        str     r3, [sp, #0]    ; V13_EXTRA_LOOP_SPILL\n"
                "32002058:   9b00        ldr     r3, [sp, #0]    ; V13_EXTRA_LOOP_RELOAD\n"
                "3200205a:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "3200205c:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205e:   d1f5        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "32002060:   2000        movs    r0, #0\n"
                "32002062:   4770        bx      lr\n"
                "32002068:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "extra-loop-spill-reload",
            ),
            "nm": V13_NM_OK,
            "expected": "extra per-iteration load/store",
        },
        "extra_loop_call": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002054:   d105        bne.n   32002062 <v13_poll_completion+0x22>\n"
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "3200205c:   2000        movs    r0, #0\n"
                "3200205e:   4770        bx      lr\n"
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "32002054:   d106        bne.n   32002066 <v13_poll_completion+0x26>\n"
                "32002056:   f7ff ffd3   bl      32002000 <helper_bookkeeping> ; V13_EXTRA_LOOP_CALL\n"
                "3200205a:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "3200205c:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205e:   d1f5        bne.n   3200204c <v13_poll_completion+0x0c>\n"
                "32002060:   2000        movs    r0, #0\n"
                "32002062:   4770        bx      lr\n"
                "32002066:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n",
                "extra-loop-call",
            ),
            "nm": V13_NM_OK + "32002000 T helper_bookkeeping\n",
            "expected": "extra per-iteration call",
        },
        "missing_failed_decrement": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n",
                "",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "failed-poll decrement count",
        },
        "third_failed_decrement": {
            "objdump": _replace_once_exact(
                V13_OBJDUMP_OK,
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n",
                "32002056:   3a01        subs    r2, #1          ; V13_FAILED_POLL_SHADOW_DECREMENT\n"
                "32002058:   3901        subs    r1, #1          ; V13_BACK_EDGE_INDUCTION_DECREMENT\n"
                "3200205a:   3d01        subs    r5, #1          ; V13_THIRD_DECREMENT\n",
                "third-decrement",
            ),
            "nm": V13_NM_OK,
            "expected": "failed-poll decrement count",
        },
        "wrong_back_edge": {
            "objdump": V13_OBJDUMP_OK.replace(
                "3200205a:   d1f7        bne.n   3200204c <v13_poll_completion+0x0c>\n",
                "3200205a:   d1f7        bne.n   32002048 <v13_poll_completion+0x08> ; V13_WRONG_BACK_EDGE\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "conditional loop back-edge",
        },
        "second_status_read": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n"
                "32002064:   6830        ldr     r0, [r6]        ; V13_P1_DWT_READ\n"
                "32002066:   4d09        ldr     r5, [pc, #36]   ; V13_P1_STORE_PTR\n"
                "32002068:   6028        str     r0, [r5]        ; V13_P1_STORE\n"
                "3200206a:   6830        ldr     r0, [r6]        ; V13_P2_DWT_READ\n"
                "3200206c:   4d09        ldr     r5, [pc, #36]   ; V13_P2_STORE_PTR\n"
                "3200206e:   6028        str     r0, [r5]        ; V13_P2_STORE\n"
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002072:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n"
                "32002074:   4620        mov     r0, r4\n"
                "32002076:   4770        bx      lr\n",
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n"
                "32002064:   6830        ldr     r0, [r6]        ; V13_P1_DWT_READ\n"
                "32002066:   4d09        ldr     r5, [pc, #36]   ; V13_P1_STORE_PTR\n"
                "32002068:   6028        str     r0, [r5]        ; V13_P1_STORE\n"
                "3200206a:   6830        ldr     r0, [r6]        ; V13_P2_DWT_READ\n"
                "3200206c:   4d09        ldr     r5, [pc, #36]   ; V13_P2_STORE_PTR\n"
                "3200206e:   6028        str     r0, [r5]        ; V13_P2_STORE\n"
                "32002070:   f8d7 4000   ldr.w   r4, [r7]        ; V13_SECOND_STATUS_READ\n"
                "32002074:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002076:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n"
                "32002078:   4620        mov     r0, r4\n"
                "3200207a:   4770        bx      lr\n",
                "second-status-read",
            ),
            "nm": V13_NM_OK,
            "expected": "helper STATUS read count != 1",
        },
        "extra_non_status_load": {
            "objdump": _replace_block(
                V13_OBJDUMP_OK,
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n"
                "32002064:   6830        ldr     r0, [r6]        ; V13_P1_DWT_READ\n"
                "32002066:   4d09        ldr     r5, [pc, #36]   ; V13_P1_STORE_PTR\n"
                "32002068:   6028        str     r0, [r5]        ; V13_P1_STORE\n",
                "32002062:   4e09        ldr     r6, [pc, #36]   ; V13_DWT_CYCCNT_PTR\n"
                "32002064:   685b        ldr     r3, [r3, #4]    ; V13_EXTRA_NON_STATUS_LOAD\n"
                "32002066:   6830        ldr     r0, [r6]        ; V13_P1_DWT_READ\n"
                "32002068:   4d09        ldr     r5, [pc, #36]   ; V13_P1_STORE_PTR\n"
                "3200206a:   6028        str     r0, [r5]        ; V13_P1_STORE\n",
                "extra-non-status-load",
            ),
            "nm": V13_NM_OK,
            "expected": "extra non-STATUS load",
        },
        "wrong_status_address": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002078:   .word   0x51000014   ; V13_HELPER_STATUS_ADDR\n",
                "32002078:   .word   0x51000018   ; V13_HELPER_STATUS_ADDR_WRONG\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "helper STATUS MMIO address",
        },
        "store_before_p2": {
            "objdump": V13_OBJDUMP_OK.replace(
                "3200206a:   6830        ldr     r0, [r6]        ; V13_P2_DWT_READ\n"
                "3200206c:   4d09        ldr     r5, [pc, #36]   ; V13_P2_STORE_PTR\n"
                "3200206e:   6028        str     r0, [r5]        ; V13_P2_STORE\n"
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002072:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n",
                "3200206a:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "3200206c:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n"
                "3200206e:   6830        ldr     r0, [r6]        ; V13_P2_DWT_READ\n"
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_P2_STORE_PTR\n"
                "32002072:   6028        str     r0, [r5]        ; V13_P2_STORE\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "remaining store must follow P2 exactly",
        },
        "constant_store": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002072:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n",
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002072:   2101        movs    r1, #1\n"
                "32002074:   6029        str     r1, [r5]        ; V13_REMAINING_STORE_CONSTANT\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "remaining must dataflow from failed-poll countdown live-out",
        },
        "recomputed_store": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002070:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002072:   6029        str     r1, [r5]        ; V13_REMAINING_STORE\n",
                "32002070:   f1c1 0120   sub.w   r1, r1, #32      ; V13_RECOMPUTE_REMAINING\n"
                "32002074:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "32002076:   6029        str     r1, [r5]        ; V13_REMAINING_STORE_RECOMPUTED\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "remaining must dataflow from failed-poll countdown live-out",
        },
        "timeout_reaches_store": {
            "objdump": V13_OBJDUMP_OK.replace(
                "3200205c:   2000        movs    r0, #0\n"
                "3200205e:   4770        bx      lr\n",
                "3200205c:   4d09        ldr     r5, [pc, #36]   ; V13_REMAINING_STORE_PTR\n"
                "3200205e:   6029        str     r1, [r5]        ; V13_TIMEOUT_STORE\n"
                "32002060:   2000        movs    r0, #0\n"
                "32002062:   4770        bx      lr\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "timeout path must not publish remaining",
        },
        "push_pop_stack_frame": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002040:   f242 7210   movw    r2, #10000      ; V13_FAILED_POLL_REMAINING_INIT\n",
                "32002040:   b510        push    {r4, lr}        ; V13_PUSH\n"
                "32002042:   f242 7210   movw    r2, #10000      ; V13_FAILED_POLL_REMAINING_INIT\n",
                1,
            ),
            "nm": V13_NM_OK,
            "expected": "helper must remain a leaf without stack access",
        },
        "retained_v12_runtime_drift": {
            "objdump": V13_OBJDUMP_OK
            + "\n32004000 <test_u85>:\n"
            + "32004000:   f7ff f8fe   bl      32004200 <NVIC_EnableIRQ> ; V12_RUNTIME_ENABLE_DRIFT\n",
            "nm": V13_NM_OK + "32004000 T test_u85\n",
            "expected": "retained V12 vector/NVIC/CMD/QREAD/PMU/release drift",
        },
    }


ELF_NEGATIVE_FIXTURES = _elf_negative_fixtures()


def _remaining_after(iteration_index: int) -> int:
    return POLL_LIMIT - iteration_index


SEMANTIC_BOUNDARIES = (
    {"name": "first poll", "remaining": _remaining_after(0), "iterations": 1},
    {"name": "interior poll", "remaining": _remaining_after(4321), "iterations": 4322},
    {"name": "last poll", "remaining": _remaining_after(9999), "iterations": 10000},
)


def _negative_vendor_fixtures() -> dict[str, dict[str, str]]:
    duplicate_store = """            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
"""
    timeout_store = """    pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;
    return 0U;
"""
    second_status_read = """            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            status = *status_reg;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
"""
    extra_mmio = """        (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD);
        status = *status_reg;
"""
    per_iteration_store = """        ++i;
        pmu_completion_poll_v13_t_poll_remaining_at_success = i;
        status = *status_reg;
"""
    return {
        "remaining_before_p2": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n",
                "remaining-before-p2",
            ),
            "expected": "remaining store must follow P2 exactly",
        },
        "duplicate_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                duplicate_store,
                "duplicate-store",
            ),
            "expected": "poll_remaining_at_success store count != 1",
        },
        "timeout_reachable_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    return 0U;\n",
                timeout_store,
                "timeout-store",
            ),
            "expected": "timeout path must not publish remaining",
        },
        "success_remaining_zero": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;\n",
                "remaining-zero",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "success_remaining_10001": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10001U;\n",
                "remaining-10001",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "per_iteration_increment_store": {
            "vendor": replace_once(
                replace_once(
                    VENDOR_V13_OK,
                    "    uint32_t status;\n",
                    "    uint32_t i = 0U;\n"
                    "    uint32_t status;\n",
                    "per-iteration-counter",
                ),
                "        status = *status_reg;\n",
                per_iteration_store,
                "per-iteration-store",
            ),
            "expected": "remaining store must be success-only",
        },
        "second_status_read": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                second_status_read,
                "second-status-read",
            ),
            "expected": "helper STATUS read count != 1",
        },
        "extra_mmio": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "        status = *status_reg;\n",
                extra_mmio,
                "extra-mmio",
            ),
            "expected": "helper contains forbidden operation",
        },
        "wrong_completion_mask": {
            "vendor": VENDOR_V13_OK.replace("(status & 0x02U)", "(status & 0x04U)", 1),
            "expected": "helper completion mask",
        },
        "retained_v12_hard_bypass": {
            "vendor": VENDOR_V13_OK.replace("return status;", "write_reg(NPU_REG_CMD, 0x00000002);\n            return status;", 1),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
        "retained_v12_qread_release_drift": {
            "vendor": VENDOR_V13_OK.replace(
                "            return status;\n",
                "            read_val = read_reg(NPU_REG_QREAD);\n"
                "            write_reg(NPU_REG_CMD, 0x00000000);\n"
                "            write_reg(NPU_REG_CMD, 0x0000000CU);\n"
                "            return status;\n",
                1,
            ),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
    }


NEGATIVE_VENDOR_FIXTURES = _negative_vendor_fixtures()


def load_real_runner_stock() -> str:
    with open(REAL_RUNNER_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def maybe_load_env_vendor_stock() -> str | None:
    path = os.environ.get(ENV_VENDOR_KEY)
    if not path:
        return None
    with open(path, "rb") as handle:
        raw = handle.read()
    check(
        "env frozen vendor hash matches V13 pin",
        hashlib.sha256(raw).hexdigest() == VENDOR_SHA256,
    )
    return raw.decode("utf-8", errors="replace")


def validate_local_fixtures():
    required_suffix = (
        "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
        "            return status;\n"
    )
    if VENDOR_V13_OK.count("for (uint32_t i = 0U; i < 10000U; ++i) {") != 1:
        raise fail("positive vendor fixture must have exactly one helper loop")
    if required_suffix not in VENDOR_V13_OK:
        raise fail("positive vendor fixture lost V13 success suffix")
    if "uint32_t remaining = 10000U;" in VENDOR_V13_OK or "if (--remaining == 0U) {" in VENDOR_V13_OK:
        raise fail("positive vendor fixture must preserve the V12 for-loop source shape")
    if RUNNER_V13_OK.count("uint32_t poll_remaining_at_success;") != 1:
        raise fail("runner fixture must declare remaining member exactly once")
    if RUNNER_V13_OK.count("poll_remaining_at_success = 0U;") != 1:
        raise fail("runner fixture must reset invalid remaining sentinel exactly once")
    if RUNNER_V13_OK.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") != 1:
        raise fail("runner fixture must declare remaining field exactly once")
    if RUNNER_V13_OK.count("out_words[100] = d->poll_remaining_at_success;") != 1:
        raise fail("runner fixture must serialize remaining wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_FIELD_COUNT 101U") != 1:
        raise fail("runner fixture must pin field count for appended wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_TOTAL_WORDS 109U") != 1:
        raise fail("runner fixture must pin total words for appended wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_PAYLOAD_SIZE 436U") != 1:
        raise fail("runner fixture must pin payload size for appended wire word exactly once")
    if RUNNER_V12_GENERATED.count("PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID") != 1:
        raise fail("generated V12 raw-input rejection fixture malformed")
    if RUNNER_SHA256 != "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b":
        raise fail("pinned runner raw SHA constant drifted")
    if VENDOR_SHA256 != "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf":
        raise fail("pinned vendor raw SHA constant drifted")
    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        if payload["vendor"] == VENDOR_V13_OK:
            raise fail("negative fixture is a no-op: %s" % name)
    if V12_NM_OK.count("v12_poll_completion") != 1 or V13_NM_OK.count("v13_poll_completion") != 1:
        raise fail("synthetic nm fixtures must define exactly one helper symbol each")
    for marker in (
        "V12_HELPER_STATUS_READ",
        "V12_HELPER_STATUS_TEST",
        "V12_HELPER_STATUS_ADDR",
        "V12_P1",
        "V12_P2",
        "V13_HELPER_STATUS_READ",
        "V13_HELPER_STATUS_TEST",
        "V13_HELPER_STATUS_ADDR",
        "V13_P1",
        "V13_P2",
        "V13_REMAINING_STORE",
    ):
        if marker not in V12_OBJDUMP_OK and marker not in V13_OBJDUMP_OK:
            raise fail("synthetic objdump fixture missing marker: %s" % marker)
    if V12_OBJDUMP_OK.count("ldr.w   r4, [r7]        ; V12_HELPER_STATUS_READ") != 1:
        raise fail("V12 synthetic objdump must expose exactly one STATUS read site")
    if V13_OBJDUMP_OK.count("ldr.w   r4, [r7]        ; V13_HELPER_STATUS_READ") != 1:
        raise fail("V13 synthetic objdump must expose exactly one STATUS read site")
    if V13_OBJDUMP_OK.count("str     r1, [r5]        ; V13_REMAINING_STORE") != 1:
        raise fail("V13 synthetic objdump must expose exactly one post-P2 remaining store")
    if V13_OBJDUMP_OK.find("V13_P2") > V13_OBJDUMP_OK.find("V13_REMAINING_STORE"):
        raise fail("V13 synthetic objdump must keep remaining store after P2")
    for name, payload in ELF_NEGATIVE_FIXTURES.items():
        if payload["objdump"] == V13_OBJDUMP_OK:
            raise fail("synthetic ELF negative fixture is a no-op: %s" % name)


def run_future_elf_suite(gate):
    v12_loop = gate.extract_poll_loop(V12_OBJDUMP_OK, V12_NM_OK)
    v13_loop = gate.extract_poll_loop(V13_OBJDUMP_OK, V13_NM_OK)
    evidence = gate.verify_cross_elf_contract(V12_OBJDUMP_OK, V12_NM_OK, V13_OBJDUMP_OK, V13_NM_OK)

    check(
        "future ELF gate normalizes V12 and V13 loop effects identically",
        gate.normalize_poll_loop(v12_loop) == gate.normalize_poll_loop(v13_loop),
    )
    loop_equivalent = getattr(evidence, "loop_equivalent", None) if not isinstance(evidence, dict) else evidence.get("loop_equivalent")
    check(
        "future ELF gate accepts canonical V12/V13 pair through authoritative contract",
        loop_equivalent is True,
        str(evidence),
    )

    proof = gate.prove_remaining_dataflow(V13_OBJDUMP_OK, V13_NM_OK)
    source = getattr(proof, "source", None) if not isinstance(proof, dict) else proof.get("source")
    check(
        "future ELF gate proves remaining live-out comes from back-edge induction",
        source == "back_edge_induction",
        str(proof),
    )

    for name, payload in ELF_NEGATIVE_FIXTURES.items():
        try:
            gate.verify_cross_elf_contract(V12_OBJDUMP_OK, V12_NM_OK, payload["objdump"], payload["nm"])
            check("future ELF gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future ELF gate rejects %s" % name, payload["expected"] in str(exc), str(exc))


def run_generator_suite(patcher):
    real_runner_stock = load_real_runner_stock()
    check(
        "real frozen runner hash matches V13 pin",
        hashlib.sha256(real_runner_stock.encode("utf-8")).hexdigest() == RUNNER_SHA256,
    )
    env_vendor_stock = maybe_load_env_vendor_stock()
    if env_vendor_stock is not None:
        env_vendor_out, env_vendor_meta = patcher.patch_vendor(env_vendor_stock)
        check(
            "env frozen vendor default patch succeeds",
            env_vendor_out.count("v13_poll_completion(void)") == 1,
        )
        check(
            "env frozen vendor patch counts recorded",
            isinstance(env_vendor_meta, dict) and bool(env_vendor_meta),
        )

    runner_out, runner_meta = patcher.patch_runner(real_runner_stock)
    vendor_out, vendor_meta = patcher.patch_vendor(PATCH_VENDOR_STOCK)

    check("runner patch returns replacements", isinstance(runner_meta, dict) and bool(runner_meta))
    check("vendor patch returns replacements", isinstance(vendor_meta, dict) and bool(vendor_meta))
    check("runner patch sets schema 13", "#define PMU_DIAG_SCHEMA_VERSION 13U" in runner_out)
    check("runner patch pins build id 0x33314950", "#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U" in runner_out)
    check(
        "runner patch declares remaining record field exactly once",
        runner_out.count("uint32_t poll_remaining_at_success;") == 1
        and runner_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") >= 1
        and runner_out.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") == 1,
    )
    check("runner patch resets invalid remaining sentinel", "poll_remaining_at_success = 0U;" in runner_out)
    check(
        "runner patch appends exactly one remaining wire word",
        runner_out.count("put32(&c, d->poll_remaining_at_success);") == 1
        and "PMU_DIAG_FIELD_COUNT == 101U" in runner_out
        and "PMU_DIAG_TOTAL_WORDS == 109U" in runner_out
        and "PMU_DIAG_PAYLOAD_SIZE == 436U" in runner_out,
    )
    check("vendor patch emits V13 helper symbol", "v13_poll_completion" in vendor_out)
    check(
        "vendor patch appends one remaining word",
        vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 2
        and vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;") == 1,
    )
    check(
        "vendor patch emits exact success suffix",
        (
            "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
            "            return status;"
        ) in vendor_out,
    )
    check(
        "vendor patch preserves V12 for-loop source with post-P2 publication",
        "for (uint32_t i = 0U; i < 10000U; ++i) {" in vendor_out
        and "pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;" in vendor_out
        and "if (--remaining == 0U) {" not in vendor_out,
    )
    check(
        "vendor timeout path does not publish remaining",
        "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;\n    return 0U;" not in vendor_out,
    )
    try:
        patcher.patch_runner(load_real_runner_stock() + "\n#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n#endif\n")
        check("runner patch rejects generated V11 input", False, "unexpected pass")
    except BaseException as exc:
        check("runner patch rejects generated V11 input", "V11 marker" in str(exc), str(exc))
    try:
        patcher.patch_vendor(PATCH_VENDOR_STOCK + "\nvolatile uint32_t pmu_interval_v11a_t_vector_probe;\n")
        check("vendor patch rejects generated V11 input", False, "unexpected pass")
    except BaseException as exc:
        check("vendor patch rejects generated V11 input", "V11 marker" in str(exc), str(exc))

    for boundary in SEMANTIC_BOUNDARIES:
        remaining = boundary["remaining"]
        iterations = boundary["iterations"]
        check(
            "semantic boundary %s maps remaining to iterations" % boundary["name"],
            1 <= remaining <= 10000 and iterations == (10001 - remaining),
            "remaining=%d iterations=%d" % (remaining, iterations),
        )
    check("timeout semantic keeps invalid remaining sentinel", INVALID_REMAINING == 0)
    return runner_out, vendor_out


def run_future_suite(gate, patcher):
    runner_out, vendor_out = run_generator_suite(patcher)

    try:
        evidence = gate.verify_generated_sources(runner_out, vendor_out)
        check(
            "future V13 gate accepts canonical generated sources",
            evidence.get("schema_version") == SCHEMA_VERSION
            and evidence.get("build_id") == BUILD_ID
            and evidence.get("poll_remaining_symbol") == "pmu_completion_poll_v13_t_poll_remaining_at_success",
        )
    except Exception as exc:
        check("future V13 gate accepts canonical generated sources", False, str(exc))
        evidence = None

    for wrong_runner, wrong_vendor, label, expected_reason in (
        (load_real_runner_stock() + "\n/* drift */\n", PATCH_VENDOR_STOCK, "runner hash mismatch", "runner hash mismatch"),
        (load_real_runner_stock(), PATCH_VENDOR_STOCK + "\n/* drift */\n", "vendor hash mismatch", "vendor hash mismatch"),
        (RUNNER_V12_GENERATED, PATCH_VENDOR_STOCK, "generated V12 runner as raw input", "generated runner input"),
        (load_real_runner_stock(), VENDOR_V12_GENERATED, "generated V12 vendor as raw input", "generated vendor input"),
        (load_real_runner_stock() + load_real_runner_stock(), PATCH_VENDOR_STOCK, "multiple raw runner targets", "multiple raw runner targets"),
        ("/* missing helper */\n", PATCH_VENDOR_STOCK, "zero raw runner targets", "zero raw runner targets"),
        (load_real_runner_stock(), PATCH_VENDOR_STOCK + PATCH_VENDOR_STOCK, "multiple raw vendor targets", "multiple raw vendor targets"),
        (load_real_runner_stock(), "/* missing helper */\n", "zero raw vendor targets", "zero raw vendor targets"),
    ):
        try:
            gate.verify_generated_sources(
                wrong_runner,
                wrong_vendor,
                raw_runner_sha256=RUNNER_SHA256,
                raw_vendor_sha256=VENDOR_SHA256,
            )
            check("future V13 gate rejects %s" % label, False, "unexpected pass")
        except TypeError:
            check("future V13 gate rejects %s" % label, False, "verify_generated_sources signature still missing V13 raw-input contract")
        except Exception as exc:
            check("future V13 gate rejects %s" % label, expected_reason in str(exc), str(exc))

    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        try:
            gate.verify_generated_sources(RUNNER_V13_OK, payload["vendor"])
            check("future V13 gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future V13 gate rejects %s" % name, payload["expected"] in str(exc), str(exc))

    return evidence


if __name__ == "__main__":
    validate_local_fixtures()

    check("fixture schema version is 13", SCHEMA_VERSION == 13)
    check("fixture build id is 0x33314950", BUILD_ID == "0x33314950")
    check("raw runner SHA pin matches frozen contract", RUNNER_SHA256 == "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b")
    check("raw vendor SHA pin matches frozen contract", VENDOR_SHA256 == "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf")
    check("positive vendor stores remaining exactly once", VENDOR_V13_OK.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check("positive vendor timeout publishes no remaining", "return 0U;" in VENDOR_V13_OK and "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;" not in VENDOR_V13_OK)
    check(
        "runner fixture pins concrete V13 ABI values",
        "#define PMU_DIAG_FIELD_COUNT 101U" in RUNNER_V13_OK
        and "#define PMU_DIAG_TOTAL_WORDS 109U" in RUNNER_V13_OK
        and "#define PMU_DIAG_PAYLOAD_SIZE 436U" in RUNNER_V13_OK,
    )
    check(
        "source negative fixture set matches intended drift list",
        set(NEGATIVE_VENDOR_FIXTURES) == EXPECTED_SOURCE_NEGATIVE_FIXTURES,
    )
    check("synthetic ELF negative fixture count covers required drifts", len(ELF_NEGATIVE_FIXTURES) >= 13)
    check(
        "boundary semantics cover first interior last and timeout invalid",
        [item["remaining"] for item in SEMANTIC_BOUNDARIES] == [10000, 5679, 1] and INVALID_REMAINING == 0,
    )

    import patches.patch_pmu_completion_poll_count_v13 as patcher

    run_generator_suite(patcher)

    import check_pmu_completion_poll_count_v13 as gate

    run_future_suite(gate, patcher)
    run_future_elf_suite(gate)

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
