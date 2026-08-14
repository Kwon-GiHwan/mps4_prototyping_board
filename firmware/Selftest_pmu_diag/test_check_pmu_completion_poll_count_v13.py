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

RUNNER_SHA256 = "57b3028bc820825ce7e560e0979e36a4c10acd9cfff55408d2985132ca384b4c"
VENDOR_SHA256 = "053d15bd81ce35f32b18d6d876ac501db41d97db141ab1fbe8fb7b70a564dceb"

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
    uint32_t remaining = 10000U;
    uint32_t status;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (;;) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
            return status;
        }
        if (--remaining == 0U) {
            break;
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
        "wrong_status_address": {
            "objdump": V13_OBJDUMP_OK.replace(
                "32002048:   4f0c        ldr     r7, [pc, #48]   ; V13_HELPER_STATUS_PTR\n",
                "32002048:   4f0c        ldr     r7, [pc, #48]   ; V13_HELPER_STATUS_PTR_WRONG_MMIO\n",
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
            "objdump": V13_OBJDUMP_OK + "\n32004000 <test_u85>:\n32004000:   4800        ldr     r0, [pc, #0]   ; V12_RUNTIME_ENABLE_DRIFT\n",
            "nm": V13_NM_OK,
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
    duplicate_store = """            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
"""
    timeout_store = """    pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;
    return 0U;
"""
    second_status_read = """            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            status = *status_reg;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
"""
    extra_mmio = """        (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD);
        status = *status_reg;
"""
    unrelated_counter = """    uint32_t remaining = 10000U;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (;;) {
        remaining = 10000U;
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
            return status;
        }
        if (--remaining == 0U) {
            break;
        }
    }
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
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n",
                "remaining-before-p2",
            ),
            "expected": "remaining store must follow P2 exactly",
        },
        "duplicate_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
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
        "recomputed_remaining": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    uint32_t remaining = 10000U;\n"
                "    uint32_t status;\n",
                "    uint32_t remaining = 10000U;\n"
                "    uint32_t i = 0U;\n"
                "    uint32_t status;\n",
                "recomputed-remaining-counter",
            ),
            "expected": "remaining must dataflow from failed-poll countdown live-out",
        },
        "recomputed_remaining_store": {
            "vendor": replace_once(
                replace_once(
                    VENDOR_V13_OK,
                    "    uint32_t remaining = 10000U;\n"
                    "    uint32_t status;\n",
                    "    uint32_t remaining = 10000U;\n"
                    "    uint32_t i = 0U;\n"
                    "    uint32_t status;\n",
                    "recomputed-remaining-counter",
                ),
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n",
                "recomputed-remaining",
            ),
            "expected": "remaining must dataflow from failed-poll countdown live-out",
        },
        "success_remaining_zero": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;\n",
                "remaining-zero",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "success_remaining_10001": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10001U;\n",
                "remaining-10001",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "unrelated_reinitialized_counter": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;\n\n"
                "    for (;;) {\n"
                "        status = *status_reg;\n"
                "        if ((status & 0x02U) != 0U) {\n"
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n"
                "            return status;\n"
                "        }\n"
                "        if (--remaining == 0U) {\n"
                "            break;\n"
                "        }\n"
                "    }\n",
                unrelated_counter,
                "reinitialized-counter",
            ),
            "expected": "remaining must dataflow from failed-poll countdown live-out",
        },
        "per_iteration_increment_store": {
            "vendor": replace_once(
                replace_once(
                    VENDOR_V13_OK,
                    "    uint32_t remaining = 10000U;\n"
                    "    uint32_t status;\n",
                    "    uint32_t remaining = 10000U;\n"
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
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n",
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


def validate_local_fixtures():
    required_suffix = (
        "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n"
        "            return status;\n"
    )
    if VENDOR_V13_OK.count("for (;;) {") != 1:
        raise fail("positive vendor fixture must have exactly one helper loop")
    if required_suffix not in VENDOR_V13_OK:
        raise fail("positive vendor fixture lost V13 success suffix")
    if VENDOR_V13_OK.count("uint32_t remaining = 10000U;") != 1:
        raise fail("positive vendor fixture must seed countdown once")
    if VENDOR_V13_OK.count("if (--remaining == 0U) {") != 1:
        raise fail("positive vendor fixture must use failed-path countdown exactly once")
    if sha256_text(RUNNER_RAW_STOCK) != RUNNER_SHA256:
        raise fail("pinned runner raw SHA fixture drifted")
    if sha256_text(VENDOR_RAW_STOCK) != VENDOR_SHA256:
        raise fail("pinned vendor raw SHA fixture drifted")
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
    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        if payload["vendor"] == VENDOR_V13_OK:
            raise fail("negative fixture is a no-op: %s" % name)
    if V12_NM_OK.count("v12_poll_completion") != 1 or V13_NM_OK.count("v13_poll_completion") != 1:
        raise fail("synthetic nm fixtures must define exactly one helper symbol each")
    for marker in (
        "V12_HELPER_STATUS_READ",
        "V12_HELPER_STATUS_TEST",
        "V12_P1",
        "V12_P2",
        "V13_HELPER_STATUS_READ",
        "V13_HELPER_STATUS_TEST",
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

    check(
        "future ELF gate normalizes V12 and V13 loop effects identically",
        gate.normalize_poll_loop(v12_loop) == gate.normalize_poll_loop(v13_loop),
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
            mutated = gate.extract_poll_loop(payload["objdump"], payload["nm"])
            if gate.normalize_poll_loop(mutated) == gate.normalize_poll_loop(v12_loop):
                gate.prove_remaining_dataflow(payload["objdump"], payload["nm"])
            check("future ELF gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future ELF gate rejects %s" % name, payload["expected"] in str(exc), str(exc))


def run_future_suite(gate, patcher):
    runner_out, runner_meta = patcher.patch_runner(RUNNER_RAW_STOCK)
    vendor_out, vendor_meta = patcher.patch_vendor(VENDOR_RAW_STOCK)

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
        runner_out.count("out_words[100] = d->poll_remaining_at_success;") == 1
        and runner_out.count("#define PMU_DIAG_FIELD_COUNT 101U") == 1
        and runner_out.count("#define PMU_DIAG_TOTAL_WORDS 109U") == 1
        and runner_out.count("#define PMU_DIAG_PAYLOAD_SIZE 436U") == 1,
    )
    check("vendor patch emits V13 helper symbol", "v13_poll_completion" in vendor_out)
    check("vendor patch appends one remaining word", vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check(
        "vendor patch emits exact success suffix",
        (
            "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;\n"
            "            return status;"
        ) in vendor_out,
    )
    check(
        "vendor patch uses failed-path countdown live-out",
        "uint32_t remaining = 10000U;" in vendor_out
        and "if (--remaining == 0U) {" in vendor_out
        and "pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);" not in vendor_out,
    )
    check(
        "vendor timeout path does not publish remaining",
        "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;\n    return 0U;" not in vendor_out,
    )

    for boundary in SEMANTIC_BOUNDARIES:
        remaining = boundary["remaining"]
        iterations = boundary["iterations"]
        check(
            "semantic boundary %s maps remaining to iterations" % boundary["name"],
            1 <= remaining <= 10000 and iterations == (10001 - remaining),
            "remaining=%d iterations=%d" % (remaining, iterations),
        )
    check("timeout semantic keeps invalid remaining sentinel", INVALID_REMAINING == 0)

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

    for wrong_runner, wrong_vendor, label in (
        (RUNNER_RAW_STOCK + "\n/* drift */\n", VENDOR_RAW_STOCK, "runner hash mismatch"),
        (RUNNER_RAW_STOCK, VENDOR_RAW_STOCK + "\n/* drift */\n", "vendor hash mismatch"),
        (RUNNER_V12_GENERATED, VENDOR_RAW_STOCK, "generated V12 runner as raw input"),
        (RUNNER_RAW_STOCK, VENDOR_V12_GENERATED, "generated V12 vendor as raw input"),
        (RUNNER_RAW_STOCK + RUNNER_RAW_STOCK, VENDOR_RAW_STOCK, "multiple raw runner targets"),
        ("/* missing helper */\n", VENDOR_RAW_STOCK, "zero raw runner targets"),
        (RUNNER_RAW_STOCK, VENDOR_RAW_STOCK + VENDOR_RAW_STOCK, "multiple raw vendor targets"),
        (RUNNER_RAW_STOCK, "/* missing helper */\n", "zero raw vendor targets"),
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
            check("future V13 gate rejects %s" % label, True, str(exc))

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
    check("raw runner SHA fixture is frozen", RUNNER_SHA256 == sha256_text(RUNNER_RAW_STOCK))
    check("raw vendor SHA fixture is frozen", VENDOR_SHA256 == sha256_text(VENDOR_RAW_STOCK))
    check("positive vendor stores remaining exactly once", VENDOR_V13_OK.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check("positive vendor timeout publishes no remaining", "return 0U;" in VENDOR_V13_OK and "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;" not in VENDOR_V13_OK)
    check(
        "runner fixture pins concrete V13 ABI values",
        "#define PMU_DIAG_FIELD_COUNT 101U" in RUNNER_V13_OK
        and "#define PMU_DIAG_TOTAL_WORDS 109U" in RUNNER_V13_OK
        and "#define PMU_DIAG_PAYLOAD_SIZE 436U" in RUNNER_V13_OK,
    )
    check("negative fixture count covers required drifts", len(NEGATIVE_VENDOR_FIXTURES) >= 13)
    check("synthetic ELF negative fixture count covers required drifts", len(ELF_NEGATIVE_FIXTURES) >= 13)
    check(
        "boundary semantics cover first interior last and timeout invalid",
        [item["remaining"] for item in SEMANTIC_BOUNDARIES] == [10000, 5679, 1] and INVALID_REMAINING == 0,
    )

    import check_pmu_completion_poll_count_v13 as gate
    import patches.patch_pmu_completion_poll_count_v13 as patcher

    run_future_suite(gate, patcher)
    run_future_elf_suite(gate)

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
