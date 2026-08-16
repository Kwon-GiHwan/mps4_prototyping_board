"""Firmware contract tests for PMU_COMPLETION_VISIBILITY_DIAG_V14.

The suite is self-contained: every schema constant, appendix offset and enum
value below is transcribed from the approved design rather than imported from
the gate, so a gate constant drifting away from the design is a test failure
instead of a silent agreement.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-78s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


SCHEMA = 14
BUILD_ID = 0x34314950
BASE_WORDS = 85
APPENDIX_WORDS = 34
BODY_WORDS = 119
TOTAL_WORDS = 127
PAYLOAD_BYTES = 508
HEADER_WORDS = 8
QSIZE_EXPECTED = 0x110
MAILBOX_VALID = 0x5631344D
U32_INVALID = 0xFFFFFFFF
ITERATION_BOUND = 10000
VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"

# Transcribed from the design's appendix table, words 0..33 in wire order.
APPENDIX_FIELDS = (
    "variant_id",
    "qsize_expected",
    "pre_program_status",
    "pre_submit_status",
    "t_submit_after_cmd",
    "t_primary_entry",
    "t_first_observation",
    "primary_result",
    "primary_iterations",
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
    "convergence_result",
    "convergence_iterations",
    "convergence_final_qread",
    "convergence_final_status",
    "convergence_timeout",
    "failure_phase",
    "failure_reason",
    "failure_qread",
    "failure_status",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
    "mailbox_valid",
)

PRIMARY_RESULT = {"NOT_RUN": 0, "OBSERVED": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
CONVERGENCE_RESULT = {"NOT_RUN": 0, "SUCCESS": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
FAILURE_PHASE = {
    "NONE": 0,
    "PRE_PROGRAM": 1,
    "PRE_SUBMIT": 2,
    "PRIMARY": 3,
    "CONVERGENCE": 4,
    "CLEANUP": 5,
}
FAILURE_REASON = {
    "NONE": 0,
    "STATE_RUNNING": 1,
    "RESET_IN_PROGRESS": 2,
    "HARDWARE_FAULT": 3,
    "STALE_IRQ": 4,
    "STALE_CMD_END": 5,
    "QSIZE_MISMATCH": 6,
    "PRIMARY_TIMEOUT": 7,
    "CONVERGENCE_TIMEOUT": 8,
    "CLEANUP_INVARIANT": 9,
}
VENDOR_RETURN = {
    "SUCCESS": 0,
    "PRE_PROGRAM_FAILURE": 1,
    "PRE_SUBMIT_FAILURE": 2,
    "PRIMARY_TIMEOUT": 3,
    "RESET_IN_PROGRESS": 4,
    "HARDWARE_FAULT": 5,
    "CONVERGENCE_TIMEOUT": 6,
    "CLEANUP_INVARIANT": 7,
}

STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_RESET = 0x008
STATUS_CMD_END = 0x020
STATUS_FAULT_MASK = 0x314

# The suite is frozen at this many assertions. Adding a named fixture is a
# deliberate act, so the count moves with it and never drifts silently.
EXPECTED_PASS_COUNT = 865

CHECKER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "check_pmu_completion_visibility_v14.py",
)


def run_checker(args):
    return subprocess.run(
        [sys.executable, CHECKER_PATH] + list(args),
        capture_output=True,
        text=True,
    )


def replace_once(text, old, new, what):
    count = text.count(old)
    if count != 1:
        raise AssertionError("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1)


def mbox(field):
    return "V14_MBOX_" + field.upper()


# ---------------------------------------------------------------------------
# Canonical generated-source fixtures.
#
# These are transcribed from the approved design, not imported from the gate or
# the generator, so a drift on either side is a test failure. Every negative
# fixture below is one named mutation of this text.
# ---------------------------------------------------------------------------

VENDOR_DEFS = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

#define V14_VARIANT_ID %(variant_id)uU
#define V14_U32_INVALID 0xFFFFFFFFU
#define V14_MAILBOX_VALID 0x5631344DU
#define V14_QSIZE_EXPECTED 0x00000110U
#define V14_ITERATION_BOUND 10000U
#define V14_APPENDIX_WORDS 34U

#define V14_STATUS_STATE 0x001U
#define V14_STATUS_IRQ_RAISED 0x002U
#define V14_STATUS_RESET 0x008U
#define V14_STATUS_CMD_END 0x020U
#define V14_STATUS_FAULT_MASK 0x314U

%(offsets)s

#define V14_PRIMARY_NOT_RUN 0U
#define V14_PRIMARY_OBSERVED 1U
#define V14_PRIMARY_TIMEOUT 2U
#define V14_PRIMARY_RESET 3U
#define V14_PRIMARY_FAULT 4U

#define V14_CONVERGENCE_NOT_RUN 0U
#define V14_CONVERGENCE_SUCCESS 1U
#define V14_CONVERGENCE_TIMEOUT 2U
#define V14_CONVERGENCE_RESET 3U
#define V14_CONVERGENCE_FAULT 4U

#define V14_PHASE_NONE 0U
#define V14_PHASE_PRE_PROGRAM 1U
#define V14_PHASE_PRE_SUBMIT 2U
#define V14_PHASE_PRIMARY 3U
#define V14_PHASE_CONVERGENCE 4U
#define V14_PHASE_CLEANUP 5U

#define V14_REASON_NONE 0U
#define V14_REASON_STATE_RUNNING 1U
#define V14_REASON_RESET_IN_PROGRESS 2U
#define V14_REASON_HARDWARE_FAULT 3U
#define V14_REASON_STALE_IRQ 4U
#define V14_REASON_STALE_CMD_END 5U
#define V14_REASON_QSIZE_MISMATCH 6U
#define V14_REASON_PRIMARY_TIMEOUT 7U
#define V14_REASON_CONVERGENCE_TIMEOUT 8U
#define V14_REASON_CLEANUP_INVARIANT 9U

#define V14_RET_SUCCESS 0
#define V14_RET_PRE_PROGRAM_FAILURE 1
#define V14_RET_PRE_SUBMIT_FAILURE 2
#define V14_RET_PRIMARY_TIMEOUT 3
#define V14_RET_RESET_IN_PROGRESS 4
#define V14_RET_HARDWARE_FAULT 5
#define V14_RET_CONVERGENCE_TIMEOUT 6
#define V14_RET_CLEANUP_INVARIANT 7

volatile uint32_t pmu_completion_visibility_v14_mailbox[34];

struct v14_observation_t {
    uint32_t result;
    uint32_t iterations;
    uint32_t qread;
    uint32_t status;
    uint32_t t_first;
};
"""

VENDOR_STOCK_ISR = """
void u85_irq_handler(void)
{
    int32_t status_register = 0;
    status_register = read_reg(NPU_REG_STATUS);
    irq_history_mask = status_register >> 16;
    if ((status_register & 0x02)){
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 2);
    }
}
"""

VENDOR_MAILBOX_HELPERS = """
__attribute__((noinline))
void v14_mailbox_reset(void)
{
    for (uint32_t i = 0U; i < V14_APPENDIX_WORDS; ++i) {
        pmu_completion_visibility_v14_mailbox[i] = V14_U32_INVALID;
    }
    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = 0U;
    __DSB();
}

__attribute__((noinline))
static void v14_mailbox_publish(void)
{
    __DSB();
    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;
    __DSB();
}

__attribute__((noinline))
static void v14_publish_failure(uint32_t phase, uint32_t reason, uint32_t qread, uint32_t status)
{
    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] = V14_U32_INVALID;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_STATUS] = V14_U32_INVALID;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = phase;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_REASON] = reason;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_QREAD] = qread;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = status;
    v14_mailbox_publish();
}

__attribute__((noinline))
static void v14_publish_cleanup_failure(uint32_t qread, uint32_t status)
{
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_CLEANUP;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_REASON] = V14_REASON_CLEANUP_INVARIANT;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_QREAD] = qread;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = status;
    v14_mailbox_publish();
}

__attribute__((noinline))
static void v14_publish_success(void)
{
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_NONE;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_REASON] = V14_REASON_NONE;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_QREAD] = V14_U32_INVALID;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = V14_U32_INVALID;
    v14_mailbox_publish();
}

__attribute__((noinline))
static void v14_publish_primary(const struct v14_observation_t *obs, uint32_t qsize_expected)
{
    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_RESULT] = obs->result;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_ITERATIONS] = obs->iterations;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_T_FIRST_OBSERVATION] = obs->t_first;
    if (obs->result != V14_PRIMARY_OBSERVED) {
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_QREAD] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_Q_DONE] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_CMD_END_REACHED] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_IRQ_RAISED] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATE] = V14_U32_INVALID;
        return;
    }
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_QREAD] = obs->qread;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = obs->status;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_Q_DONE] = (obs->qread == qsize_expected) ? 1U : 0U;
    if (obs->status == V14_U32_INVALID) {
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_CMD_END_REACHED] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_IRQ_RAISED] = V14_U32_INVALID;
        pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATE] = V14_U32_INVALID;
        return;
    }
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_CMD_END_REACHED] = ((obs->status & V14_STATUS_CMD_END) != 0U) ? 1U : 0U;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_IRQ_RAISED] = ((obs->status & V14_STATUS_IRQ_RAISED) != 0U) ? 1U : 0U;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATE] = (obs->status & V14_STATUS_STATE);
}
"""

VENDOR_PRIMARY_Q = """
__attribute__((noinline))
static void v14_primary_q(uint32_t qsize_expected, struct v14_observation_t *obs)
{
    volatile uint32_t *const qread_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD);
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t qread = 0U;
    uint32_t status = 0U;

    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {
        qread = *qread_reg;
        if (qread == qsize_expected) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V14_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = qread;
            obs->status = V14_U32_INVALID;
            return;
        }
    }

    status = *status_reg;
    obs->t_first = V14_U32_INVALID;
    obs->iterations = 0U;
    obs->qread = qread;
    obs->status = status;
    if ((status & V14_STATUS_RESET) != 0U) {
        obs->result = V14_PRIMARY_RESET;
        return;
    }
    if ((status & V14_STATUS_FAULT_MASK) != 0U) {
        obs->result = V14_PRIMARY_FAULT;
        return;
    }
    obs->result = V14_PRIMARY_TIMEOUT;
}
"""

VENDOR_PRIMARY_DUAL = """
__attribute__((noinline))
static void v14_primary_%(suffix)s(uint32_t qsize_expected, struct v14_observation_t *obs)
{
    volatile uint32_t *const qread_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD);
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t qread = 0U;
    uint32_t status = 0U;

    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {
%(reads)s
        if ((status & V14_STATUS_RESET) != 0U) {
            obs->t_first = V14_U32_INVALID;
            obs->result = V14_PRIMARY_RESET;
            obs->iterations = 0U;
            obs->qread = qread;
            obs->status = status;
            return;
        }
        if ((status & V14_STATUS_FAULT_MASK) != 0U) {
            obs->t_first = V14_U32_INVALID;
            obs->result = V14_PRIMARY_FAULT;
            obs->iterations = 0U;
            obs->qread = qread;
            obs->status = status;
            return;
        }
        if ((qread == qsize_expected) || ((status & V14_STATUS_CMD_END) != 0U)) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V14_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = qread;
            obs->status = status;
            return;
        }
    }

    obs->t_first = V14_U32_INVALID;
    obs->result = V14_PRIMARY_TIMEOUT;
    obs->iterations = 0U;
    obs->qread = qread;
    obs->status = status;
}
"""

VENDOR_CONVERGE = """
__attribute__((noinline))
static void v14_converge(uint32_t qsize_expected, struct v14_observation_t *obs)
{
    volatile uint32_t *const qread_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD);
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t qread = 0U;
    uint32_t status = 0U;
    uint32_t result = V14_CONVERGENCE_TIMEOUT;
    uint32_t iterations = 0U;

    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {
        qread = *qread_reg;
        status = *status_reg;
        if ((status & V14_STATUS_RESET) != 0U) {
            result = V14_CONVERGENCE_RESET;
            break;
        }
        if ((status & V14_STATUS_FAULT_MASK) != 0U) {
            result = V14_CONVERGENCE_FAULT;
            break;
        }
        if ((qread == qsize_expected) &&
            ((status & V14_STATUS_CMD_END) != 0U) &&
            ((status & V14_STATUS_IRQ_RAISED) != 0U) &&
            ((status & V14_STATUS_STATE) == 0U)) {
            result = V14_CONVERGENCE_SUCCESS;
            iterations = i;
            break;
        }
    }

    obs->t_first = V14_U32_INVALID;
    obs->result = result;
    obs->iterations = iterations;
    obs->qread = qread;
    obs->status = status;
}
"""

VENDOR_TEST_U85 = """
int test_u85( const u85_eTest eTest,
              const uint32_t u32ExpectedIRQMask,
              const uint32_t u32OutputSize,
              const uint32_t u32CmdQueueSize,
              struct u85_warp_data_t *pu85_warp_data_st )
{
    int ret_code = 0;
    uint32_t pre_program_status = 0U;

    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    irq_triggered = false;
    NVIC_DisableIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;
    pmu_completion_visibility_v14_mailbox[V14_MBOX_INSTALLED_VECTOR] = NVIC_GetVector(NPU0_IRQn);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ENABLED_BEFORE_SUBMIT] = NVIC_GetEnableIRQ(NPU0_IRQn);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT] = NVIC_GetActive(NPU0_IRQn);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT] = irq_triggered ? 1U : 0U;

    if ((pmu_completion_visibility_v14_mailbox[V14_MBOX_INSTALLED_VECTOR] != (uint32_t)&u85_irq_handler) ||
        (pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ENABLED_BEFORE_SUBMIT] != 0U) ||
        (pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR] != 0U) ||
        (pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT] != 0U) ||
        (pmu_completion_visibility_v14_mailbox[V14_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT] != 0U)) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_STATE_RUNNING, V14_U32_INVALID, V14_U32_INVALID);
        return V14_RET_PRE_PROGRAM_FAILURE;
    }

    pre_program_status = read_reg(NPU_REG_STATUS);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRE_PROGRAM_STATUS] = pre_program_status;
    if ((pre_program_status & V14_STATUS_STATE) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_STATE_RUNNING, V14_U32_INVALID, pre_program_status);
        return V14_RET_PRE_PROGRAM_FAILURE;
    }
    if ((pre_program_status & V14_STATUS_RESET) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_RESET_IN_PROGRESS, V14_U32_INVALID, pre_program_status);
        return V14_RET_RESET_IN_PROGRESS;
    }
    if ((pre_program_status & V14_STATUS_FAULT_MASK) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_HARDWARE_FAULT, V14_U32_INVALID, pre_program_status);
        return V14_RET_HARDWARE_FAULT;
    }

    write_reg(NPU_REG_QBASE, (uint32_t)pu85_warp_data_st->pu32CmdStream);
    write_reg(NPU_REG_QSIZE, u32CmdQueueSize);

    ret_code = test_commands(eTest, u32CmdQueueSize, pu85_warp_data_st);
    return ret_code;
}
"""

VENDOR_TEST_COMMANDS = """
__attribute__((noinline))
static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{
\tint ret_code;
    int read_val;
    uint32_t qsize_expected;
    uint32_t pre_submit_status;
    struct v14_observation_t primary;
    struct v14_observation_t converged;

\t/* Init locals */
\tret_code =0;
\tread_val =0;
    qsize_expected = 0U;
    pre_submit_status = 0U;

\t  qsize_expected = read_reg(NPU_REG_QSIZE);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_QSIZE_EXPECTED] = qsize_expected;
\t  pre_submit_status = read_reg(NPU_REG_STATUS);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_PRE_SUBMIT_STATUS] = pre_submit_status;
\t  if (qsize_expected != V14_QSIZE_EXPECTED) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_QSIZE_MISMATCH, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_PRE_SUBMIT_FAILURE;
\t  }
\t  if ((pre_submit_status & V14_STATUS_STATE) != 0U) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_STATE_RUNNING, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_PRE_SUBMIT_FAILURE;
\t  }
\t  if ((pre_submit_status & V14_STATUS_RESET) != 0U) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_RESET_IN_PROGRESS, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_RESET_IN_PROGRESS;
\t  }
\t  if ((pre_submit_status & V14_STATUS_FAULT_MASK) != 0U) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_HARDWARE_FAULT, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_HARDWARE_FAULT;
\t  }
\t  if ((pre_submit_status & V14_STATUS_IRQ_RAISED) != 0U) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_STALE_IRQ, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_PRE_SUBMIT_FAILURE;
\t  }
\t  if ((pre_submit_status & V14_STATUS_CMD_END) != 0U) {
\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_STALE_CMD_END, V14_U32_INVALID, pre_submit_status);
\t    return V14_RET_PRE_SUBMIT_FAILURE;
\t  }
\t  //Start NPU
\t  read_val = read_reg(NPU_REG_CMD);
\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_PRIMARY_ENTRY] = DWT->CYCCNT;
\t  %(primary_call)s(qsize_expected, &primary);
\t  v14_publish_primary(&primary, qsize_expected);
\t  if (primary.result != V14_PRIMARY_OBSERVED) {
\t    if (primary.result == V14_PRIMARY_RESET) {
\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);
\t      return V14_RET_RESET_IN_PROGRESS;
\t    }
\t    if (primary.result == V14_PRIMARY_FAULT) {
\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_HARDWARE_FAULT, primary.qread, primary.status);
\t      return V14_RET_HARDWARE_FAULT;
\t    }
\t    v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_PRIMARY_TIMEOUT, primary.qread, primary.status);
\t    return V14_RET_PRIMARY_TIMEOUT;
\t  }
\t  v14_converge(qsize_expected, &converged);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_RESULT] = converged.result;
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_ITERATIONS] = converged.iterations;
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_TIMEOUT] =
\t      (converged.result == V14_CONVERGENCE_TIMEOUT) ? 1U : 0U;
\t  if (converged.result != V14_CONVERGENCE_SUCCESS) {
\t    if (converged.result == V14_CONVERGENCE_RESET) {
\t      v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_RESET_IN_PROGRESS, converged.qread, converged.status);
\t      return V14_RET_RESET_IN_PROGRESS;
\t    }
\t    if (converged.result == V14_CONVERGENCE_FAULT) {
\t      v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_HARDWARE_FAULT, converged.qread, converged.status);
\t      return V14_RET_HARDWARE_FAULT;
\t    }
\t    v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_CONVERGENCE_TIMEOUT, converged.qread, converged.status);
\t    return V14_RET_CONVERGENCE_TIMEOUT;
\t  }
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] = converged.qread;
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_STATUS] = converged.status;
\t  irq_history_mask = converged.status >> 16;
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  read_val = read_reg(NPU_REG_QREAD);
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  if(read_val == u32CmdQueueSize) {
\t    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t  }
\t  else {
\t    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t    ret_code = 1;
\t  }
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_BEFORE_FINAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
\t  NVIC_ClearPendingIRQ(NPU0_IRQn);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_AFTER_FINAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ACTIVE_AFTER_CLEANUP] = NVIC_GetActive(NPU0_IRQn);
\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_IRQ_TRIGGERED_AFTER_CLEANUP] = irq_triggered ? 1U : 0U;
\t  //Stop NPU
\t  write_reg(NPU_REG_CMD, 0x00000000);
\t  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
\t    /* V12_HPRINTF_SEAM */
\t    printf("Testing CPM signals\\n");
\t    //Enable Program CLKQ and PWRQ interfaces
\t    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
\t    write_reg(NPU_REG_CMD, 0x0000000C);
#endif
\t  if (ret_code != 0) {
\t    v14_publish_cleanup_failure((uint32_t)read_val, converged.status);
\t    ret_code = V14_RET_CLEANUP_INVARIANT;
\t  }
\t  else {
\t    v14_publish_success();
\t    ret_code = V14_RET_SUCCESS;
\t  }
\treturn ret_code;
}
"""

_DUAL_READS = {
    "QS": "        qread = *qread_reg;\n        status = *status_reg;",
    "SQ": "        status = *status_reg;\n        qread = *qread_reg;",
}


def vendor_offsets_block():
    return "\n".join(
        "#define %s %dU" % (mbox(field), index) for index, field in enumerate(APPENDIX_FIELDS)
    )


def canonical_vendor(variant):
    if variant == "Q":
        primary = VENDOR_PRIMARY_Q
    else:
        primary = VENDOR_PRIMARY_DUAL % {
            "suffix": variant.lower(),
            "reads": _DUAL_READS[variant],
        }
    return "".join(
        (
            VENDOR_DEFS % {"variant_id": VARIANTS[variant], "offsets": vendor_offsets_block()},
            VENDOR_STOCK_ISR,
            VENDOR_MAILBOX_HELPERS,
            primary,
            VENDOR_CONVERGE,
            VENDOR_TEST_COMMANDS.replace("%(primary_call)s", "v14_primary_" + variant.lower()),
            VENDOR_TEST_U85,
        )
    )


RUNNER_HEAD = """#if defined(PMU_QUAL_SCHEMA_V14)
#define PMU_DIAG_SCHEMA_VERSION 14U
#define PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID 0x34314950U
#define V14_MAILBOX_VALID 0x5631344DU
#define V14_APPENDIX_WORDS 34U
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

#if defined(PMU_QUAL_SCHEMA_V14)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 34U)
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#endif

#if defined(PMU_QUAL_SCHEMA_V14)
_Static_assert(PMU_DIAG_FIELD_COUNT == 119U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: v8 body plus the 34-word appendix");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 127U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: 8 header plus 119 body");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 508U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: payload is 127 * 4 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 14U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: schema must be 14");
_Static_assert(RUNNER_FIRMWARE_BUILD_ID == PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: build id must be 0x34314950");
#endif

extern volatile uint32_t pmu_completion_visibility_v14_mailbox[34];
extern void v14_mailbox_reset(void);
"""


# The frozen v8 fields the appendix is appended to. They are retained verbatim
# so the contiguity rule is exercised rather than trivially satisfied.
RUNNER_STOCK_FIELDS = ("hook_pmu_mmio_read_count", "hook_pmu_mmio_write_count")


def runner_record_block():
    stock = "\n".join("    uint32_t %s;" % field for field in RUNNER_STOCK_FIELDS)
    body = "\n".join("    uint32_t %s;" % field for field in APPENDIX_FIELDS)
    return "typedef struct {\n%s\n%s\n} pmu_diag_record_t;\n" % (stock, body)


def runner_reset_block():
    return """
void pmu_diag_reset_v14_state(void)
{
    v14_mailbox_reset();
    pmu_diag_v14_transport_valid = 0U;
}
"""


def runner_copy_block():
    lines = "\n".join(
        "            d.%s = pmu_completion_visibility_v14_mailbox[%d];" % (field, index)
        for index, field in enumerate(APPENDIX_FIELDS)
    )
    return """
void pmu_diag_collect_v14(pmu_diag_record_t *out)
{
    pmu_diag_record_t d;

    memset(&d, 0, sizeof(d));
    pmu_diag_reset_v14_state();
    rc = run_fixed_inference();
    d.hook_pmu_mmio_read_count = pmu_qual_hook_pmu_reads;
    d.hook_pmu_mmio_write_count = pmu_qual_hook_pmu_writes;
    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {
        pmu_diag_v14_transport_valid = 0U;
    }
    else {
        pmu_diag_v14_transport_valid = 1U;
%s
    }
    *out = d;
}
""" % lines


def runner_serialize_block():
    stock = "\n".join("    put32(&c, d->%s);" % field for field in RUNNER_STOCK_FIELDS)
    lines = "\n".join("    put32(&c, d->%s);" % field for field in APPENDIX_FIELDS)
    return """
void pmu_diag_serialize_v14(const pmu_diag_record_t *d, uint8_t *c)
{
%s
%s
}
""" % (stock, lines)


def canonical_runner(variant):
    return "".join(
        (
            RUNNER_HEAD,
            runner_record_block(),
            runner_reset_block(),
            runner_copy_block(),
            runner_serialize_block(),
        )
    )


DIAG_DIR = os.path.dirname(os.path.abspath(__file__))


def tracked_sources_matching(digest):
    """Tracked C sources in this directory whose contents hash to ``digest``."""

    found = []
    for name in sorted(os.listdir(DIAG_DIR)):
        if not name.endswith(".c"):
            continue
        with open(os.path.join(DIAG_DIR, name), "rb") as handle:
            if hashlib.sha256(handle.read()).hexdigest() == digest:
                found.append(name)
    return found


def frozen_v12_hprintf_marker():
    """The V12 marker name that maps to the qualified __wrap_printf callsite.

    Read from the frozen V12 gate rather than transcribed, because the whole
    point of the V14 seam contract is that it is *that* anchor and not a name
    this suite invented.
    """

    import check_pmu_completion_poll_v12 as v12

    names = [
        name
        for name, key in v12.MANIFEST_MARKER_KEYS.items()
        if key == "hprintf_callsite_address"
    ]
    return names[0] if len(names) == 1 else None


def run_identity_suite(gate):
    check("schema version is 14", gate.SCHEMA_VERSION == SCHEMA)
    check("build id is 0x34314950", gate.BUILD_ID == BUILD_ID)
    check("frozen v8 base body is 85 words", gate.BASE_WORDS == BASE_WORDS)
    check("appendix is exactly 34 words", gate.APPENDIX_WORDS == APPENDIX_WORDS)
    check("body is 85 + 34 = 119 words", gate.BODY_WORDS == BODY_WORDS)
    check("header stays 8 words", gate.HEADER_WORDS == HEADER_WORDS)
    check("frame is 127 words", gate.TOTAL_WORDS == TOTAL_WORDS)
    check("payload is 508 bytes", gate.PAYLOAD_BYTES == PAYLOAD_BYTES)
    check("body derives from base plus appendix", gate.BASE_WORDS + gate.APPENDIX_WORDS == gate.BODY_WORDS)
    check("frame derives from header plus body", gate.HEADER_WORDS + gate.BODY_WORDS == gate.TOTAL_WORDS)
    check("payload derives from the frame", gate.TOTAL_WORDS * 4 == gate.PAYLOAD_BYTES)
    check("qsize expected is 0x110", gate.QSIZE_EXPECTED == QSIZE_EXPECTED)
    check("mailbox magic is 0x5631344D", gate.MAILBOX_VALID == MAILBOX_VALID)
    check("u32 invalid sentinel is 0xFFFFFFFF", gate.U32_INVALID == U32_INVALID)
    check("iteration bound is 10000", gate.ITERATION_BOUND == ITERATION_BOUND)
    check("variant ids are Q=1 QS=2 SQ=3", gate.VARIANTS == VARIANTS)
    check("appendix field order matches the design table", tuple(gate.APPENDIX_FIELDS) == APPENDIX_FIELDS)
    check("mailbox_valid is the final appendix word", gate.APPENDIX_FIELDS[-1] == "mailbox_valid")
    check(
        "mailbox_valid lands on absolute frame word 126",
        gate.HEADER_WORDS + gate.BASE_WORDS + gate.APPENDIX_FIELDS.index("mailbox_valid") == 126,
    )
    check("appendix names are unique", len(set(gate.APPENDIX_FIELDS)) == APPENDIX_WORDS)
    check("primary_result enum matches the design", gate.PRIMARY_RESULT == PRIMARY_RESULT)
    check("convergence_result enum matches the design", gate.CONVERGENCE_RESULT == CONVERGENCE_RESULT)
    check("failure_phase enum matches the design", gate.FAILURE_PHASE == FAILURE_PHASE)
    check("failure_reason enum matches the design", gate.FAILURE_REASON == FAILURE_REASON)
    check("vendor return mapping matches the plan", gate.VENDOR_RETURN == VENDOR_RETURN)
    check("status state mask is bit0", gate.STATUS_STATE == STATUS_STATE)
    check("status irq_raised mask is bit1", gate.STATUS_IRQ_RAISED == STATUS_IRQ_RAISED)
    check("status reset mask is bit3", gate.STATUS_RESET == STATUS_RESET)
    check("status cmd_end mask is bit5", gate.STATUS_CMD_END == STATUS_CMD_END)
    check("vendor fault mask is 0x314", gate.STATUS_FAULT_MASK == STATUS_FAULT_MASK)
    check(
        "the fault mask is exactly bus|parse|ecc|branch",
        gate.STATUS_FAULT_MASK == 0x004 | 0x010 | 0x100 | 0x200,
    )
    check("reset is not folded into the fault mask", gate.STATUS_RESET & gate.STATUS_FAULT_MASK == 0)
    check("raw runner sha pin is frozen", gate.RUNNER_SHA256 == RUNNER_SHA256)
    check("raw vendor sha pin is frozen", gate.VENDOR_SHA256 == VENDOR_SHA256)
    check(
        "the H-PRINTF seam marker is the frozen V12 qualified callsite anchor",
        gate.HPRINTF_SEAM_MARKER_NAME == frozen_v12_hprintf_marker(),
        repr(frozen_v12_hprintf_marker()),
    )
    check(
        "the frozen raw vendor translation unit is not tracked here",
        not tracked_sources_matching(VENDOR_SHA256),
        repr(tracked_sources_matching(VENDOR_SHA256)),
    )
    check(
        "the tracked raw runner is, so the runner half is not fixture-only",
        tracked_sources_matching(RUNNER_SHA256) == ["runner_pmu_diag_main.c"],
    )

    for name, wrong in (
        ("schema", 13),
        ("build id", 0x33314950),
        ("appendix words", 33),
        ("qsize", 0x108),
        ("mailbox magic", 0x5631334D),
    ):
        check(
            "a different %s is rejected" % name,
            gate.identity_matches(
                schema_version=SCHEMA if name != "schema" else wrong,
                build_id=BUILD_ID if name != "build id" else wrong,
                appendix_words=APPENDIX_WORDS if name != "appendix words" else wrong,
                qsize_expected=QSIZE_EXPECTED if name != "qsize" else wrong,
                mailbox_valid=MAILBOX_VALID if name != "mailbox magic" else wrong,
            )
            is False,
        )
    check(
        "the exact identity tuple is accepted",
        gate.identity_matches(
            schema_version=SCHEMA,
            build_id=BUILD_ID,
            appendix_words=APPENDIX_WORDS,
            qsize_expected=QSIZE_EXPECTED,
            mailbox_valid=MAILBOX_VALID,
        )
        is True,
    )


def run_cli_suite():
    result = run_checker(["--help"])
    check("--help exits zero", result.returncode == 0, result.stderr.strip()[:60])
    for option in (
        "--allow-fixture",
        "--variant",
        "--runner-generated",
        "--vendor-generated",
        "--fixture-manifest-out",
    ):
        check("--help documents %s" % option, option in result.stdout)

    result = run_checker([])
    check("no arguments is refused", result.returncode != 0)

    result = run_checker(
        [
            "--variant",
            "Q",
            "--runner-generated",
            "/dev/null",
            "--vendor-generated",
            "/dev/null",
            "--fixture-manifest-out",
            "/dev/null",
        ]
    )
    check(
        "synthetic evidence without --allow-fixture is refused",
        result.returncode != 0 and "fixture mode requires --allow-fixture" in (result.stdout + result.stderr),
        (result.stdout + result.stderr).strip()[:70],
    )

    result = run_checker(
        [
            "--allow-fixture",
            "--variant",
            "QQ",
            "--runner-generated",
            "/dev/null",
            "--vendor-generated",
            "/dev/null",
            "--fixture-manifest-out",
            "/dev/null",
        ]
    )
    check("an invalid variant is refused", result.returncode != 0)

    result = run_checker(["--allow-fixture", "--variant", "Q"])
    check("fixture mode without inputs is refused", result.returncode != 0)


# ---------------------------------------------------------------------------
# Frozen raw inputs for the generator.
#
# The raw runner is tracked in this repository at its frozen digest, so the
# generator's runner half runs against the real thing. The raw vendor
# translation unit is not tracked here, so its half runs against a stock
# fixture that carries the five frozen V12 anchors verbatim. That is a real
# limitation of this chunk and is reported as one.
# ---------------------------------------------------------------------------

REAL_RUNNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner_pmu_diag_main.c")

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
\treturn ret_code;
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
    write_reg(NPU_REG_QBASE, (uint32_t)pu85_warp_data_st->pu32CmdStream);
    write_reg(NPU_REG_QSIZE, u32CmdQueueSize);
    ret_code = test_commands(eTest, u32CmdQueueSize, pu85_warp_data_st);
    return ret_code;
}
"""


def load_real_runner_stock():
    with open(REAL_RUNNER_PATH, "r", encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n").replace("\r", "\n")


def expect_accept(gate, variant, runner, vendor, name):
    try:
        doc = gate.verify_generated_sources(runner, vendor, variant)
    except Exception as exc:
        check(name, False, ("%s" % exc)[:80])
        return None
    check(name, True)
    return doc


def expect_reject(gate, variant, runner, vendor, name, reason):
    try:
        gate.verify_generated_sources(runner, vendor, variant)
    except gate.GateError as exc:
        check("rejects %s" % name, reason in str(exc), ("%s" % exc)[:80])
        return
    except Exception as exc:  # pragma: no cover - a crash is not a rejection
        check("rejects %s" % name, False, "raised %r" % exc)
        return
    check("rejects %s" % name, False, "accepted")


REJECTED_FIXTURES = set()


def run_vendor_mutations(gate, mutations, variant="Q"):
    runner = canonical_runner(variant)
    vendor = canonical_vendor(variant)
    for name, mutate, reason in mutations:
        REJECTED_FIXTURES.add(name)
        expect_reject(gate, variant, runner, mutate(vendor), name, reason)


def run_runner_mutations(gate, mutations, variant="Q"):
    runner = canonical_runner(variant)
    vendor = canonical_vendor(variant)
    for name, mutate, reason in mutations:
        REJECTED_FIXTURES.add(name)
        expect_reject(gate, variant, mutate(runner), vendor, name, reason)


PRE_PROGRAM_GATE = """    pre_program_status = read_reg(NPU_REG_STATUS);
    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRE_PROGRAM_STATUS] = pre_program_status;
    if ((pre_program_status & V14_STATUS_STATE) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_STATE_RUNNING, V14_U32_INVALID, pre_program_status);
        return V14_RET_PRE_PROGRAM_FAILURE;
    }
    if ((pre_program_status & V14_STATUS_RESET) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_RESET_IN_PROGRESS, V14_U32_INVALID, pre_program_status);
        return V14_RET_RESET_IN_PROGRESS;
    }
    if ((pre_program_status & V14_STATUS_FAULT_MASK) != 0U) {
        v14_publish_failure(V14_PHASE_PRE_PROGRAM, V14_REASON_HARDWARE_FAULT, V14_U32_INVALID, pre_program_status);
        return V14_RET_HARDWARE_FAULT;
    }

"""

QUEUE_PROGRAMMING = """    write_reg(NPU_REG_QBASE, (uint32_t)pu85_warp_data_st->pu32CmdStream);
    write_reg(NPU_REG_QSIZE, u32CmdQueueSize);
"""


def drop_pre_program_gate(vendor):
    return replace_once(vendor, PRE_PROGRAM_GATE, "", "pre-program gate")


def move_pre_program_gate_after_programming(vendor):
    text = replace_once(vendor, PRE_PROGRAM_GATE, "", "pre-program gate")
    return replace_once(text, QUEUE_PROGRAMMING, QUEUE_PROGRAMMING + "\n" + PRE_PROGRAM_GATE, "queue programming")


def insert_running_transition(vendor):
    return replace_once(
        vendor,
        QUEUE_PROGRAMMING,
        "    write_reg(NPU_REG_CMD, 0x00000001);\n" + QUEUE_PROGRAMMING,
        "queue programming",
    )


def snapshot_qsize_before_final_programming(vendor):
    return replace_once(
        vendor,
        QUEUE_PROGRAMMING,
        "    write_reg(NPU_REG_QBASE, (uint32_t)pu85_warp_data_st->pu32CmdStream);\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_QSIZE_EXPECTED] = read_reg(NPU_REG_QSIZE);\n"
        "    write_reg(NPU_REG_QSIZE, u32CmdQueueSize);\n",
        "queue programming",
    )


def qsize_compare_off_manifest(vendor):
    return replace_once(vendor, "#define V14_QSIZE_EXPECTED 0x00000110U", "#define V14_QSIZE_EXPECTED 0x00000108U", "qsize define")


def add_second_qsize_read(vendor):
    return replace_once(
        vendor,
        "\t  pre_submit_status = read_reg(NPU_REG_STATUS);",
        "\t  qsize_expected = read_reg(NPU_REG_QSIZE);\n\t  pre_submit_status = read_reg(NPU_REG_STATUS);",
        "pre-submit status read",
    )


def move_qsize_read_after_submit(vendor):
    text = replace_once(vendor, "\t  qsize_expected = read_reg(NPU_REG_QSIZE);\n", "", "qsize read")
    return replace_once(
        text,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  qsize_expected = read_reg(NPU_REG_QSIZE);\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "submit timestamp",
    )


def _drop_pre_submit_gate(mask_macro, reason_macro, ret_macro):
    block = (
        "\t  if ((pre_submit_status & %s) != 0U) {\n"
        "\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, %s, V14_U32_INVALID, pre_submit_status);\n"
        "\t    return %s;\n"
        "\t  }\n" % (mask_macro, reason_macro, ret_macro)
    )

    def mutate(vendor):
        return replace_once(vendor, block, "", "pre-submit %s gate" % mask_macro)

    return mutate


def pre_run_failure_falls_through(vendor):
    return replace_once(
        vendor,
        "\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_QSIZE_MISMATCH, V14_U32_INVALID, pre_submit_status);\n"
        "\t    return V14_RET_PRE_SUBMIT_FAILURE;\n",
        "\t    v14_publish_failure(V14_PHASE_PRE_SUBMIT, V14_REASON_QSIZE_MISMATCH, V14_U32_INVALID, pre_submit_status);\n",
        "qsize mismatch return",
    )


def reuse_pre_program_status_after_programming(vendor):
    return replace_once(
        vendor,
        "\t  pre_submit_status = read_reg(NPU_REG_STATUS);\n",
        "\t  pre_submit_status = pmu_completion_visibility_v14_mailbox[V14_MBOX_PRE_PROGRAM_STATUS];\n",
        "pre-submit status read",
    )


PRE_RUN_MUTATIONS = (
    ("pre_program_gate_missing", drop_pre_program_gate, "pre-program STATUS gate does not dominate QBASE/QSIZE"),
    (
        "pre_program_gate_after_programming",
        move_pre_program_gate_after_programming,
        "pre-program STATUS gate does not dominate QBASE/QSIZE",
    ),
    (
        "running_transition_between_gate_and_programming",
        insert_running_transition,
        "state-transitioning CMD write between the pre-program gate and queue programming",
    ),
    (
        "qsize_snapshot_before_final_programming",
        snapshot_qsize_before_final_programming,
        "qsize snapshot precedes the final QSIZE programming write",
    ),
    ("qsize_compare_not_manifest", qsize_compare_off_manifest, "qsize_expected is not manifest 0x110"),
    ("second_qsize_read", add_second_qsize_read, "QSIZE is loaded more than once"),
    ("qsize_read_after_submit", move_qsize_read_after_submit, "running QSIZE reachable"),
    (
        "post_program_stale_irq_gate_missing",
        _drop_pre_submit_gate("V14_STATUS_IRQ_RAISED", "V14_REASON_STALE_IRQ", "V14_RET_PRE_SUBMIT_FAILURE"),
        "post-program stale/reset/fault gate is incomplete",
    ),
    (
        "post_program_stale_cmd_end_gate_missing",
        _drop_pre_submit_gate("V14_STATUS_CMD_END", "V14_REASON_STALE_CMD_END", "V14_RET_PRE_SUBMIT_FAILURE"),
        "post-program stale/reset/fault gate is incomplete",
    ),
    (
        "post_program_reset_gate_missing",
        _drop_pre_submit_gate("V14_STATUS_RESET", "V14_REASON_RESET_IN_PROGRESS", "V14_RET_RESET_IN_PROGRESS"),
        "post-program stale/reset/fault gate is incomplete",
    ),
    (
        "post_program_fault_gate_missing",
        _drop_pre_submit_gate("V14_STATUS_FAULT_MASK", "V14_REASON_HARDWARE_FAULT", "V14_RET_HARDWARE_FAULT"),
        "post-program stale/reset/fault gate is incomplete",
    ),
    (
        "post_program_stopped_gate_missing",
        _drop_pre_submit_gate("V14_STATUS_STATE", "V14_REASON_STATE_RUNNING", "V14_RET_PRE_SUBMIT_FAILURE"),
        "post-program stale/reset/fault gate is incomplete",
    ),
    ("pre_run_failure_reaches_submit", pre_run_failure_falls_through, "pre-run failure reaches submit"),
    (
        "post_program_status_reused_from_pre_program",
        reuse_pre_program_status_after_programming,
        "post-program STATUS load is not distinct from the pre-program load",
    ),
)


Q_LOOP_READ = "        qread = *qread_reg;\n        if (qread == qsize_expected) {"
Q_TIMEOUT_DIAGNOSTIC = "    status = *status_reg;\n    obs->t_first = V14_U32_INVALID;\n"
DUAL_COMPLETION_GUARD = "        if ((qread == qsize_expected) || ((status & V14_STATUS_CMD_END) != 0U)) {"

DUAL_RESET_GUARD = """        if ((status & V14_STATUS_RESET) != 0U) {
            obs->t_first = V14_U32_INVALID;
            obs->result = V14_PRIMARY_RESET;
            obs->iterations = 0U;
            obs->qread = qread;
            obs->status = status;
            return;
        }
"""

DUAL_FAULT_GUARD = """        if ((status & V14_STATUS_FAULT_MASK) != 0U) {
            obs->t_first = V14_U32_INVALID;
            obs->result = V14_PRIMARY_FAULT;
            obs->iterations = 0U;
            obs->qread = qread;
            obs->status = status;
            return;
        }
"""


CONVERGE_MARKER = "\n__attribute__((noinline))\nstatic void v14_converge("


def mutate_primary(vendor, old, new, what):
    """Apply a replacement inside the primary helper only.

    The convergence helper shares the QREAD/STATUS read pair verbatim, which is
    the point of the contract, so a primary-loop mutation has to be scoped or it
    would land on the common tail instead.
    """

    split = vendor.index(CONVERGE_MARKER)
    return replace_once(vendor[:split], old, new, what) + vendor[split:]


def q_primary_reads_status(vendor):
    return replace_once(
        vendor,
        Q_LOOP_READ,
        "        qread = *qread_reg;\n        status = *status_reg;\n        if (qread == qsize_expected) {",
        "Q loop read",
    )


def q_timeout_diagnostic_missing(vendor):
    return replace_once(vendor, Q_TIMEOUT_DIAGNOSTIC, "    obs->t_first = V14_U32_INVALID;\n", "Q timeout tail")


def q_timeout_diagnostic_duplicated(vendor):
    return replace_once(
        vendor,
        Q_TIMEOUT_DIAGNOSTIC,
        "    status = *status_reg;\n    status = *status_reg;\n    obs->t_first = V14_U32_INVALID;\n",
        "Q timeout tail",
    )


def q_timeout_publishes_p1(vendor):
    return replace_once(
        vendor,
        Q_TIMEOUT_DIAGNOSTIC,
        "    status = *status_reg;\n    obs->t_first = DWT->CYCCNT;\n",
        "Q timeout tail",
    )


def q_timeout_enters_convergence(vendor):
    return replace_once(
        vendor,
        Q_TIMEOUT_DIAGNOSTIC,
        "    status = *status_reg;\n    v14_converge(qsize_expected, obs);\n    obs->t_first = V14_U32_INVALID;\n",
        "Q timeout tail",
    )


Q_TIMEOUT_RESET_BLOCK = """    if ((status & V14_STATUS_RESET) != 0U) {
        obs->result = V14_PRIMARY_RESET;
        return;
    }
"""

Q_TIMEOUT_FAULT_BLOCK = """    if ((status & V14_STATUS_FAULT_MASK) != 0U) {
        obs->result = V14_PRIMARY_FAULT;
        return;
    }
"""


def q_timeout_reset_classification_missing(vendor):
    return replace_once(vendor, Q_TIMEOUT_RESET_BLOCK, "", "Q timeout reset classification")


def q_timeout_fault_classification_missing(vendor):
    return replace_once(vendor, Q_TIMEOUT_FAULT_BLOCK, "", "Q timeout fault classification")


def _q_timeout_fault_bit_dropped(bit):
    """Classify the timeout with every fault bit but ``bit``."""

    partial = "0x%03XU" % (STATUS_FAULT_MASK & ~bit)

    def mutate(vendor):
        return replace_once(
            vendor,
            Q_TIMEOUT_FAULT_BLOCK,
            Q_TIMEOUT_FAULT_BLOCK.replace("V14_STATUS_FAULT_MASK", partial),
            "Q timeout fault classification",
        )

    return mutate


def _drop_second_read(variant):
    def mutate(vendor):
        return mutate_primary(vendor, _DUAL_READS[variant] + "\n", "        qread = *qread_reg;\n", "dual reads")

    return mutate


def _short_circuit_between_reads(variant):
    first, second = _DUAL_READS[variant].split("\n")

    def mutate(vendor):
        return mutate_primary(
            vendor,
            _DUAL_READS[variant],
            first
            + "\n        if (qread == qsize_expected) {\n"
            "            obs->result = V14_PRIMARY_OBSERVED;\n"
            "            return;\n        }\n" + second,
            "dual reads",
        )

    return mutate


def sq_order_matches_qs(vendor):
    return mutate_primary(vendor, _DUAL_READS["SQ"], _DUAL_READS["QS"], "SQ dual reads")


def completion_uses_bit1(vendor):
    return replace_once(
        vendor,
        DUAL_COMPLETION_GUARD,
        "        if ((qread == qsize_expected) || ((status & V14_STATUS_IRQ_RAISED) != 0U)) {",
        "completion guard",
    )


def success_tuple_reread(vendor):
    return replace_once(
        vendor,
        "            obs->qread = qread;\n            obs->status = status;\n            return;\n        }\n    }\n\n    obs->t_first = V14_U32_INVALID;\n    obs->result = V14_PRIMARY_TIMEOUT;",
        "            obs->qread = *qread_reg;\n            obs->status = *status_reg;\n            return;\n        }\n    }\n\n    obs->t_first = V14_U32_INVALID;\n    obs->result = V14_PRIMARY_TIMEOUT;",
        "dual success tuple",
    )


def _inject_into_dual_loop(variant, statement):
    def mutate(vendor):
        return mutate_primary(
            vendor, _DUAL_READS[variant], _DUAL_READS[variant] + "\n        " + statement, "dual reads"
        )

    return mutate


# The first structural scanner stopped at the first nested block, so an effect
# placed *after* a guard was invisible. Every forbidden effect therefore has a
# fixture that hides behind the first guard rather than sitting between the
# reads, and a normal guard body still has to read as a guard body.
Q_LOOP_GUARD_TAIL = (
    "            obs->status = V14_U32_INVALID;\n            return;\n        }\n"
)


def _inject_after_q_guard(statement):
    def mutate(vendor):
        return replace_once(
            vendor,
            Q_LOOP_GUARD_TAIL,
            Q_LOOP_GUARD_TAIL + "        " + statement + "\n",
            "Q loop guard tail",
        )

    return mutate


def _inject_after_dual_guard(statement):
    def mutate(vendor):
        return mutate_primary(
            vendor,
            DUAL_RESET_GUARD,
            DUAL_RESET_GUARD + "        " + statement + "\n",
            "dual reset guard",
        )

    return mutate


# Depth alone proves nothing. A guard body runs only on the iteration that takes
# its branch, but no condition tells the scanner how many iterations there are:
# ``if (i != 0U)`` is true on every one of them, and a body that simply falls out
# of its braces runs again on the next. Both shapes put a store, a call or a
# timestamp on every iteration exactly as a depth-0 statement would, so every
# forbidden effect gets a fixture *inside* a guard as well as after one, in the
# braced and the braceless spelling.
ALWAYS_TRUE_CONDITION = "if (i != 0U)"
BRACELESS_NESTED_CALL = "            if (i != 0U) helper_bookkeeping();\n"
DUAL_RESET_GUARD_HEAD = "        if ((status & V14_STATUS_RESET) != 0U) {\n"


def _always_true_guard(statement):
    return "        %s {\n            %s\n        }" % (ALWAYS_TRUE_CONDITION, statement)


def _inject_guard_into_q_loop(statement):
    def mutate(vendor):
        return mutate_primary(
            vendor,
            Q_LOOP_READ,
            "        qread = *qread_reg;\n"
            + _always_true_guard(statement)
            + "\n        if (qread == qsize_expected) {",
            "Q loop read",
        )

    return mutate


def _inject_guard_into_dual_loop(statement):
    def mutate(vendor):
        return mutate_primary(
            vendor,
            _DUAL_READS["QS"],
            _DUAL_READS["QS"] + "\n" + _always_true_guard(statement),
            "dual reads",
        )

    return mutate


def q_primary_braceless_call_in_guard(vendor):
    return mutate_primary(
        vendor, Q_LOOP_READ, Q_LOOP_READ + "\n" + BRACELESS_NESTED_CALL.rstrip("\n"), "Q loop read"
    )


def primary_braceless_call_in_reset_guard(vendor):
    return mutate_primary(
        vendor,
        DUAL_RESET_GUARD_HEAD,
        DUAL_RESET_GUARD_HEAD + BRACELESS_NESTED_CALL,
        "dual reset guard head",
    )


def q_primary_guard_reaches_back_edge(vendor):
    return mutate_primary(
        vendor,
        Q_LOOP_READ + "\n            obs->t_first = DWT->CYCCNT;\n",
        Q_LOOP_READ + "\n"
        "            obs->qread = qread;\n"
        "            if (i == 0U) {\n"
        "                continue;\n"
        "            }\n"
        "            obs->t_first = DWT->CYCCNT;\n",
        "Q completion guard",
    )


def primary_guard_reaches_back_edge(vendor):
    return mutate_primary(
        vendor,
        DUAL_RESET_GUARD_HEAD + "            obs->t_first = V14_U32_INVALID;\n",
        DUAL_RESET_GUARD_HEAD + "            obs->qread = qread;\n"
        "            if (i == 0U) {\n"
        "                continue;\n"
        "            }\n"
        "            obs->t_first = V14_U32_INVALID;\n",
        "dual reset guard",
    )


DUAL_COMPLETION_BLOCK = """        if ((qread == qsize_expected) || ((status & V14_STATUS_CMD_END) != 0U)) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V14_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = qread;
            obs->status = status;
            return;
        }
"""


def reset_priority_lost(vendor):
    text = replace_once(vendor, DUAL_RESET_GUARD, "", "dual reset guard")
    return replace_once(
        text, DUAL_COMPLETION_BLOCK, DUAL_COMPLETION_BLOCK + DUAL_RESET_GUARD, "completion block"
    )


def fault_priority_lost(vendor):
    text = replace_once(vendor, DUAL_FAULT_GUARD, "", "dual fault guard")
    return replace_once(
        text, DUAL_COMPLETION_BLOCK, DUAL_COMPLETION_BLOCK + DUAL_FAULT_GUARD, "completion block"
    )


def primary_bound_drift(vendor):
    return replace_once(vendor, "#define V14_ITERATION_BOUND 10000U", "#define V14_ITERATION_BOUND 9999U", "bound")


def inactive_primary_present(vendor):
    extra = VENDOR_PRIMARY_DUAL % {"suffix": "qs", "reads": _DUAL_READS["QS"]}
    return replace_once(vendor, VENDOR_CONVERGE, extra + VENDOR_CONVERGE, "converge helper")


def primary_helper_renamed(vendor):
    return replace_once(vendor, "static void v14_primary_q(", "static void v14_primary_x(", "Q helper name")


def vector_not_stock(vendor):
    return replace_once(
        vendor,
        "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
        "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&v14_shim_handler);",
        "vector install",
    )


def nvic_probe_order_drift(vendor):
    pending = "    pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);\n"
    active = "    pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT] = NVIC_GetActive(NPU0_IRQn);\n"
    return replace_once(vendor, pending + active, active + pending, "nvic probes")


def nvic_disable_missing(vendor):
    return replace_once(vendor, "    NVIC_DisableIRQ(NPU0_IRQn);\n", "", "nvic disable")


def nvic_enable_reachable(vendor):
    return replace_once(
        vendor,
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n\n    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID]",
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n    NVIC_EnableIRQ(NPU0_IRQn);\n\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID]",
        "nvic clear",
    )


def direct_iser_write(vendor):
    return replace_once(
        vendor,
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n\n    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID]",
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n    NVIC->ISER[0] = 1UL;\n\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID]",
        "nvic clear",
    )


def irq_triggered_published(vendor):
    return replace_once(
        vendor,
        "\t  //Start NPU\n",
        "\t  irq_triggered = true;\n\t  //Start NPU\n",
        "submit comment",
    )


PRIMARY_Q_MUTATIONS = (
    ("q_primary_status_read", q_primary_reads_status, "Q primary loop reads STATUS"),
    (
        "q_timeout_diagnostic_missing",
        q_timeout_diagnostic_missing,
        "Q timeout diagnostic STATUS read is missing or duplicated",
    ),
    (
        "q_timeout_diagnostic_duplicated",
        q_timeout_diagnostic_duplicated,
        "Q timeout diagnostic STATUS read is missing or duplicated",
    ),
    ("q_timeout_publishes_p1", q_timeout_publishes_p1, "Q timeout path publishes a first-observation timestamp"),
    ("q_timeout_enters_convergence", q_timeout_enters_convergence, "Q timeout path reaches the convergence tail"),
    ("primary_helper_missing", primary_helper_renamed, "primary helper v14_primary_q is missing"),
    ("inactive_primary_helper_present", inactive_primary_present, "inactive primary helper is reachable"),
    ("primary_bound_not_10000", primary_bound_drift, "primary loop bound is not 10000"),
    (
        "q_timeout_reset_classification_missing",
        q_timeout_reset_classification_missing,
        "Q timeout diagnostic does not classify reset from the diagnostic STATUS load",
    ),
    (
        "q_timeout_fault_classification_missing",
        q_timeout_fault_classification_missing,
        "Q timeout diagnostic does not classify every 0x314 fault bit from the diagnostic STATUS load",
    ),
    (
        "q_timeout_fault_bit_bus_dropped",
        _q_timeout_fault_bit_dropped(0x004),
        "Q timeout diagnostic does not classify every 0x314 fault bit from the diagnostic STATUS load",
    ),
    (
        "q_timeout_fault_bit_cmd_parse_dropped",
        _q_timeout_fault_bit_dropped(0x010),
        "Q timeout diagnostic does not classify every 0x314 fault bit from the diagnostic STATUS load",
    ),
    (
        "q_timeout_fault_bit_ecc_dropped",
        _q_timeout_fault_bit_dropped(0x100),
        "Q timeout diagnostic does not classify every 0x314 fault bit from the diagnostic STATUS load",
    ),
    (
        "q_timeout_fault_bit_branch_dropped",
        _q_timeout_fault_bit_dropped(0x200),
        "Q timeout diagnostic does not classify every 0x314 fault bit from the diagnostic STATUS load",
    ),
    (
        "q_primary_status_read_after_guard",
        _inject_after_q_guard("status = *status_reg;"),
        "Q primary loop reads STATUS",
    ),
    (
        "q_primary_qsize_read_after_guard",
        _inject_after_q_guard("qsize_expected = read_reg(NPU_REG_QSIZE);"),
        "QSIZE access reachable in a primary loop",
    ),
    (
        "q_primary_timestamp_after_guard",
        _inject_after_q_guard("obs->t_first = DWT->CYCCNT;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "q_primary_call_after_guard",
        _inject_after_q_guard("helper_bookkeeping();"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "q_primary_evidence_store_after_guard",
        _inject_after_q_guard("pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_ITERATIONS] = i;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "q_primary_always_true_guard_call",
        _inject_guard_into_q_loop("helper_bookkeeping();"),
        "primary loop guard body carries a non-publication effect: (%s) carries call:helper_bookkeeping"
        % ALWAYS_TRUE_CONDITION,
    ),
    (
        "q_primary_always_true_guard_timestamp",
        _inject_guard_into_q_loop("obs->t_first = DWT->CYCCNT;"),
        "primary loop guard body carries a per-iteration effect: (%s) does not end the iteration "
        "with a break or a return" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "q_primary_always_true_guard_evidence_store",
        _inject_guard_into_q_loop("pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_ITERATIONS] = i;"),
        "primary loop guard body carries a per-iteration effect: (%s) does not end the iteration "
        "with a break or a return" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "q_primary_braceless_nested_call_in_guard",
        q_primary_braceless_call_in_guard,
        "primary loop guard body carries a non-publication effect: (if (qread == qsize_expected)) "
        "carries call:helper_bookkeeping",
    ),
    (
        "q_primary_guard_reaches_back_edge",
        q_primary_guard_reaches_back_edge,
        "primary loop guard body carries a per-iteration effect: (if (qread == qsize_expected)) "
        "reaches the loop back-edge through continue",
    ),
)

PRIMARY_QS_MUTATIONS = (
    ("qs_second_read_dropped", _drop_second_read("QS"), "QS primary read order is not QREAD then STATUS"),
    (
        "qs_short_circuit_exit",
        _short_circuit_between_reads("QS"),
        "primary predicate is evaluated before both reads",
    ),
    ("primary_completion_uses_bit1", completion_uses_bit1, "primary completion predicate does not use cmd_end_reached bit5"),
    ("primary_success_tuple_reread", success_tuple_reread, "primary success tuple is re-read rather than frozen"),
    (
        "primary_per_iteration_store",
        _inject_into_dual_loop("QS", "obs->iterations = i;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_per_iteration_timestamp",
        _inject_into_dual_loop("QS", "obs->t_first = DWT->CYCCNT;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_per_iteration_call",
        _inject_into_dual_loop("QS", "helper_bookkeeping();"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_qsize_read",
        _inject_into_dual_loop("QS", "qsize_expected = read_reg(NPU_REG_QSIZE);"),
        "QSIZE access reachable in a primary loop",
    ),
    ("primary_reset_priority_lost", reset_priority_lost, "reset/fault check does not dominate the primary completion predicate"),
    ("primary_fault_priority_lost", fault_priority_lost, "reset/fault check does not dominate the primary completion predicate"),
    (
        "primary_status_reload_after_guard",
        _inject_after_dual_guard("status = *status_reg;"),
        "primary loop reloads STATUS",
    ),
    (
        "primary_qsize_read_after_guard",
        _inject_after_dual_guard("qsize_expected = read_reg(NPU_REG_QSIZE);"),
        "QSIZE access reachable in a primary loop",
    ),
    (
        "primary_timestamp_after_guard",
        _inject_after_dual_guard("obs->t_first = DWT->CYCCNT;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_call_after_guard",
        _inject_after_dual_guard("helper_bookkeeping();"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_evidence_store_after_guard",
        _inject_after_dual_guard("pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_ITERATIONS] = i;"),
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_always_true_guard_call",
        _inject_guard_into_dual_loop("helper_bookkeeping();"),
        "primary loop guard body carries a non-publication effect: (%s) carries call:helper_bookkeeping"
        % ALWAYS_TRUE_CONDITION,
    ),
    (
        "primary_always_true_guard_timestamp",
        _inject_guard_into_dual_loop("obs->t_first = DWT->CYCCNT;"),
        "primary loop guard body carries a per-iteration effect: (%s) does not end the iteration "
        "with a break or a return" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "primary_always_true_guard_evidence_store",
        _inject_guard_into_dual_loop("pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_ITERATIONS] = i;"),
        "primary loop guard body carries a per-iteration effect: (%s) does not end the iteration "
        "with a break or a return" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "primary_braceless_nested_call_in_guard",
        primary_braceless_call_in_reset_guard,
        "primary loop guard body carries a non-publication effect: "
        "(if ((status & V14_STATUS_RESET) != 0U)) carries call:helper_bookkeeping",
    ),
    (
        "primary_guard_reaches_back_edge",
        primary_guard_reaches_back_edge,
        "primary loop guard body carries a per-iteration effect: "
        "(if ((status & V14_STATUS_RESET) != 0U)) reaches the loop back-edge through continue",
    ),
)

PRIMARY_SQ_MUTATIONS = (
    ("sq_second_read_dropped", _drop_second_read("SQ"), "SQ primary read order is not STATUS then QREAD"),
    (
        "sq_short_circuit_exit",
        _short_circuit_between_reads("SQ"),
        "primary predicate is evaluated before both reads",
    ),
    ("sq_read_order_matches_qs", sq_order_matches_qs, "SQ primary read order is not STATUS then QREAD"),
)

HARD_BYPASS_MUTATIONS = (
    ("vector_not_stock_handler", vector_not_stock, "runtime vector is not the exact stock u85_irq_handler"),
    ("nvic_probe_order_drift", nvic_probe_order_drift, "NVIC hard-bypass probe ordering drifted"),
    ("nvic_disable_missing", nvic_disable_missing, "NVIC hard-bypass probe ordering drifted"),
    ("nvic_enable_reachable", nvic_enable_reachable, "reachable NVIC_EnableIRQ"),
    ("direct_iser_enable_write", direct_iser_write, "direct NVIC ISER enable write is reachable"),
    ("irq_triggered_publication", irq_triggered_published, "irq_triggered can become true on a measured path"),
)


def run_primary_suite(gate):
    run_vendor_mutations(gate, PRIMARY_Q_MUTATIONS, "Q")
    run_vendor_mutations(gate, PRIMARY_QS_MUTATIONS, "QS")
    run_vendor_mutations(gate, PRIMARY_SQ_MUTATIONS, "SQ")
    run_vendor_mutations(gate, HARD_BYPASS_MUTATIONS, "Q")


EXPECTED_READ_ORDER = {"Q": ["QREAD"], "QS": ["QREAD", "STATUS"], "SQ": ["STATUS", "QREAD"]}
# Q never reads STATUS inside its loop, so the one post-timeout diagnostic load
# is the only evidence of why the queue never drained: it has to separate reset
# from a fault and cover the whole 0x314 mask, bit by bit.
Q_TIMEOUT_CLASSIFICATION = [
    "reset:0x%03X" % STATUS_RESET,
    "fault:0x004",
    "fault:0x010",
    "fault:0x100",
    "fault:0x200",
]
EXPECTED_PROBE_ORDER = [
    "NVIC_DisableIRQ",
    "NVIC_ClearPendingIRQ",
    "NVIC_GetVector",
    "NVIC_GetEnableIRQ",
    "NVIC_GetPendingIRQ",
    "NVIC_GetActive",
]


def run_primary_positive_suite(gate):
    for variant in ("Q", "QS", "SQ"):
        doc = expect_accept(
            gate,
            variant,
            canonical_runner(variant),
            canonical_vendor(variant),
            "%s primary contract is proven" % variant,
        )
        if doc is None:
            continue
        check(
            "%s primary read order is %s" % (variant, "/".join(EXPECTED_READ_ORDER[variant])),
            doc.get("primary_read_order") == EXPECTED_READ_ORDER[variant],
            repr(doc.get("primary_read_order")),
        )
        check("%s primary bound is 10000" % variant, doc.get("primary_bound") == ITERATION_BOUND)
        check("%s valid iteration range is 1..10000" % variant, doc.get("valid_iteration_range") == [1, ITERATION_BOUND])
        check(
            "%s gates every independent fault bit and reset" % variant,
            doc.get("fault_bits_gated") == [0x004, 0x010, 0x100, 0x200]
            and doc.get("reset_bit_gated") == 0x008,
        )
        check(
            "%s Q-timeout diagnostic STATUS reads" % variant,
            doc.get("q_timeout_diagnostic_status_loads") == (1 if variant == "Q" else 0),
        )
        check(
            "%s Q-timeout diagnostic classifies reset and every 0x314 fault bit" % variant,
            doc.get("q_timeout_classification")
            == (Q_TIMEOUT_CLASSIFICATION if variant == "Q" else []),
            repr(doc.get("q_timeout_classification")),
        )
        check(
            "%s first-observation categories" % variant,
            doc.get("first_observation_categories")
            == ([] if variant == "Q" else ["Q_FIRST", "S5_FIRST", "SAME_ITERATION"]),
        )
        check(
            "%s retains the stock vector and hard-bypass probe order" % variant,
            doc.get("installed_vector_symbol") == "u85_irq_handler"
            and doc.get("hard_bypass_probe_order") == EXPECTED_PROBE_ORDER,
        )
        check(
            "%s keeps irq_triggered false on every measured path" % variant,
            doc.get("irq_triggered_publication_sites") == ["u85_irq_handler"],
        )


TEST_COMMANDS_MARKER = "\n__attribute__((noinline))\nstatic int test_commands("

CONVERGE_PREDICATE = """        if ((qread == qsize_expected) &&
            ((status & V14_STATUS_CMD_END) != 0U) &&
            ((status & V14_STATUS_IRQ_RAISED) != 0U) &&
            ((status & V14_STATUS_STATE) == 0U)) {
            result = V14_CONVERGENCE_SUCCESS;
            iterations = i;
            break;
        }
"""

CONVERGE_RESET_GUARD = """        if ((status & V14_STATUS_RESET) != 0U) {
            result = V14_CONVERGENCE_RESET;
            break;
        }
"""

CONVERGE_FAULT_GUARD = """        if ((status & V14_STATUS_FAULT_MASK) != 0U) {
            result = V14_CONVERGENCE_FAULT;
            break;
        }
"""


def mutate_converge(vendor, old, new, what):
    start = vendor.index(CONVERGE_MARKER)
    stop = vendor.index(TEST_COMMANDS_MARKER)
    return vendor[:start] + replace_once(vendor[start:stop], old, new, what) + vendor[stop:]


def _drop_predicate_term(term, replacement=""):
    def mutate(vendor):
        return mutate_converge(vendor, term, replacement, "convergence predicate term")

    return mutate


def converge_accumulates(vendor):
    text = mutate_converge(
        vendor,
        "    uint32_t iterations = 0U;\n",
        "    uint32_t iterations = 0U;\n    uint32_t seen_q = 0U;\n",
        "convergence locals",
    )
    text = mutate_converge(
        text,
        "        if ((qread == qsize_expected) &&\n",
        "        if (qread == qsize_expected) {\n            seen_q = 1U;\n        }\n"
        "        if ((seen_q != 0U) &&\n",
        "convergence predicate head",
    )
    return text


def converge_reset_delayed(vendor):
    text = mutate_converge(vendor, CONVERGE_RESET_GUARD, "", "convergence reset guard")
    return mutate_converge(text, CONVERGE_PREDICATE, CONVERGE_PREDICATE + CONVERGE_RESET_GUARD, "convergence predicate")


def converge_fault_delayed(vendor):
    text = mutate_converge(vendor, CONVERGE_FAULT_GUARD, "", "convergence fault guard")
    return mutate_converge(text, CONVERGE_PREDICATE, CONVERGE_PREDICATE + CONVERGE_FAULT_GUARD, "convergence predicate")


def converge_order_swapped(vendor):
    return mutate_converge(vendor, _DUAL_READS["QS"], _DUAL_READS["SQ"], "convergence reads")


def converge_bound_drift(vendor):
    return mutate_converge(
        vendor,
        "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {",
        "    for (uint32_t i = 1U; i <= 9999U; ++i) {",
        "convergence loop head",
    )


def _inject_into_converge_loop(statement):
    def mutate(vendor):
        return mutate_converge(
            vendor, _DUAL_READS["QS"], _DUAL_READS["QS"] + "\n        " + statement, "convergence reads"
        )

    return mutate


def _inject_after_converge_guard(statement):
    def mutate(vendor):
        return mutate_converge(
            vendor,
            CONVERGE_RESET_GUARD,
            CONVERGE_RESET_GUARD + "        " + statement + "\n",
            "convergence reset guard",
        )

    return mutate


CONVERGE_RESET_GUARD_HEAD = "        if ((status & V14_STATUS_RESET) != 0U) {\n"


def _inject_guard_into_converge_loop(statement):
    def mutate(vendor):
        return mutate_converge(
            vendor,
            _DUAL_READS["QS"],
            _DUAL_READS["QS"] + "\n" + _always_true_guard(statement),
            "convergence reads",
        )

    return mutate


def converge_braceless_call_in_guard(vendor):
    return mutate_converge(
        vendor,
        CONVERGE_RESET_GUARD_HEAD,
        CONVERGE_RESET_GUARD_HEAD + BRACELESS_NESTED_CALL,
        "convergence reset guard head",
    )


def converge_guard_reaches_back_edge(vendor):
    return mutate_converge(
        vendor,
        CONVERGE_RESET_GUARD,
        CONVERGE_RESET_GUARD_HEAD + "            iterations = DWT->CYCCNT;\n"
        "            if (i == 0U) {\n"
        "                continue;\n"
        "            }\n"
        "            result = V14_CONVERGENCE_RESET;\n"
        "            break;\n"
        "        }\n",
        "convergence reset guard",
    )


def converge_terminating_guard_evidence_store(vendor):
    """A guard that *does* end its iteration still may not store evidence.

    The new exemption is about how many iterations an effect can run on; it is
    not a licence for the convergence tail to publish from inside its loop, so
    the all-depth store ban has to survive it.
    """

    return mutate_converge(
        vendor,
        CONVERGE_RESET_GUARD_HEAD,
        CONVERGE_RESET_GUARD_HEAD
        + "            pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_ITERATIONS] = i;\n",
        "convergence reset guard head",
    )


def converge_short_circuit_between_reads(vendor):
    first, second = _DUAL_READS["QS"].split("\n")
    return mutate_converge(
        vendor,
        _DUAL_READS["QS"],
        first
        + "\n        if (qread == qsize_expected) {\n"
        "            result = V14_CONVERGENCE_SUCCESS;\n"
        "            break;\n        }\n" + second,
        "convergence reads",
    )


def converge_helper_variant_specific(vendor):
    text = replace_once(vendor, "static void v14_converge(", "static void v14_converge_q(", "converge definition")
    return replace_once(text, "\t  v14_converge(qsize_expected, &converged);", "\t  v14_converge_q(qsize_expected, &converged);", "converge call")


def variant_block_in_common_tail(vendor):
    return replace_once(
        vendor,
        "\t  v14_publish_primary(&primary, qsize_expected);\n",
        "\t  v14_publish_primary(&primary, qsize_expected);\n\t  v14_primary_q(qsize_expected, &primary);\n",
        "common tail head",
    )


CONVERGE_MUTATIONS = (
    ("converge_cross_iteration_accumulation", converge_accumulates, "convergence predicate accumulates across iterations"),
    (
        "converge_predicate_missing_qread",
        _drop_predicate_term("        if ((qread == qsize_expected) &&\n", "        if (\n"),
        "convergence predicate omits a required term",
    ),
    (
        "converge_predicate_missing_bit5",
        _drop_predicate_term("            ((status & V14_STATUS_CMD_END) != 0U) &&\n"),
        "convergence predicate omits a required term",
    ),
    (
        "converge_predicate_missing_bit1",
        _drop_predicate_term("            ((status & V14_STATUS_IRQ_RAISED) != 0U) &&\n"),
        "convergence predicate omits a required term",
    ),
    (
        "converge_predicate_missing_stopped",
        _drop_predicate_term("            ((status & V14_STATUS_STATE) == 0U)"),
        "convergence predicate omits a required term",
    ),
    ("converge_reset_delayed", converge_reset_delayed, "convergence fault/reset check is delayed"),
    ("converge_fault_delayed", converge_fault_delayed, "convergence fault/reset check is delayed"),
    ("converge_read_order_swapped", converge_order_swapped, "convergence read order is not QREAD then STATUS"),
    ("converge_bound_not_10000", converge_bound_drift, "convergence bound is not 10000"),
    (
        "converge_per_loop_evidence_store",
        _inject_into_converge_loop("pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_ITERATIONS] = i;"),
        "convergence evidence store occurs inside the loop",
    ),
    (
        "converge_loop_qsize_read",
        _inject_into_converge_loop("qsize_expected = read_reg(NPU_REG_QSIZE);"),
        "QSIZE access reachable in the convergence tail",
    ),
    (
        "converge_loop_call",
        _inject_into_converge_loop("helper_bookkeeping();"),
        "convergence loop carries a per-iteration store/call/timestamp",
    ),
    (
        "converge_short_circuit_between_reads",
        converge_short_circuit_between_reads,
        "convergence predicate is evaluated before both reads",
    ),
    (
        "converge_status_reload_after_guard",
        _inject_after_converge_guard("status = *status_reg;"),
        "convergence loop reloads STATUS",
    ),
    (
        "converge_qsize_read_after_guard",
        _inject_after_converge_guard("qsize_expected = read_reg(NPU_REG_QSIZE);"),
        "QSIZE access reachable in the convergence tail",
    ),
    (
        "converge_timestamp_after_guard",
        _inject_after_converge_guard("iterations = DWT->CYCCNT;"),
        "convergence loop carries a per-iteration store/call/timestamp",
    ),
    (
        "converge_call_after_guard",
        _inject_after_converge_guard("helper_bookkeeping();"),
        "convergence loop carries a per-iteration store/call/timestamp",
    ),
    (
        "converge_evidence_store_after_guard",
        _inject_after_converge_guard(
            "pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_ITERATIONS] = i;"
        ),
        "convergence evidence store occurs inside the loop",
    ),
    (
        "converge_always_true_guard_call",
        _inject_guard_into_converge_loop("helper_bookkeeping();"),
        "convergence loop guard body carries a non-publication effect: (%s) carries "
        "call:helper_bookkeeping" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "converge_always_true_guard_timestamp",
        _inject_guard_into_converge_loop("iterations = DWT->CYCCNT;"),
        "convergence loop guard body carries a per-iteration effect: (%s) does not end the "
        "iteration with a break or a return" % ALWAYS_TRUE_CONDITION,
    ),
    (
        "converge_always_true_guard_evidence_store",
        _inject_guard_into_converge_loop(
            "pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_ITERATIONS] = i;"
        ),
        # The convergence tail bans an evidence store at every depth, so this
        # one is owned by that older rule rather than by the guard rule.
        "convergence evidence store occurs inside the loop",
    ),
    (
        "converge_braceless_nested_call_in_guard",
        converge_braceless_call_in_guard,
        "convergence loop guard body carries a non-publication effect: "
        "(if ((status & V14_STATUS_RESET) != 0U)) carries call:helper_bookkeeping",
    ),
    (
        "converge_terminating_guard_evidence_store",
        converge_terminating_guard_evidence_store,
        "convergence evidence store occurs inside the loop",
    ),
    (
        "converge_guard_reaches_back_edge",
        converge_guard_reaches_back_edge,
        "convergence loop guard body carries a per-iteration effect: "
        "(if ((status & V14_STATUS_RESET) != 0U)) reaches the loop back-edge through continue",
    ),
    (
        "variant_specific_convergence_helper",
        converge_helper_variant_specific,
        "common convergence helper v14_converge is missing",
    ),
    (
        "variant_block_between_primary_and_cleanup",
        variant_block_in_common_tail,
        "variant-specific block between the primary freeze and the common cleanup",
    ),
)


def mailbox_offsets_swapped(vendor):
    first = "#define %s %d" % (mbox(APPENDIX_FIELDS[9]), 9)
    second = "#define %s %d" % (mbox(APPENDIX_FIELDS[10]), 10)
    text = replace_once(vendor, first + "U", "#define %s 10U" % mbox(APPENDIX_FIELDS[9]), "offset 9")
    return replace_once(text, second + "U", "#define %s 9U" % mbox(APPENDIX_FIELDS[10]), "offset 10")


def mailbox_wrong_size(vendor):
    return replace_once(
        vendor,
        "volatile uint32_t pmu_completion_visibility_v14_mailbox[34];",
        "volatile uint32_t pmu_completion_visibility_v14_mailbox[33];",
        "mailbox storage",
    )


def mailbox_reset_no_invalid_fill(vendor):
    return replace_once(
        vendor,
        "    for (uint32_t i = 0U; i < V14_APPENDIX_WORDS; ++i) {\n"
        "        pmu_completion_visibility_v14_mailbox[i] = V14_U32_INVALID;\n"
        "    }\n",
        "",
        "mailbox reset fill",
    )


def mailbox_reset_valid_not_zeroed(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = 0U;\n    __DSB();\n}",
        "    __DSB();\n}",
        "mailbox reset zero",
    )


def mailbox_reset_no_dsb(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = 0U;\n    __DSB();\n}",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = 0U;\n}",
        "mailbox reset dsb",
    )


def mailbox_magic_not_last(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n    __DSB();\n}",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = 0U;\n    __DSB();\n}",
        "mailbox publish",
    )


def mailbox_publish_no_dsb(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n    __DSB();\n}",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n}",
        "mailbox publish",
    )


def mailbox_second_magic_site(vendor):
    return replace_once(
        vendor,
        "static void v14_publish_success(void)\n{\n",
        "static void v14_publish_success(void)\n{\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n",
        "success publication",
    )


def _inject_before_convergence_failure_return(statement):
    def mutate(vendor):
        return replace_once(
            vendor,
            "\t    v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_CONVERGENCE_TIMEOUT, converged.qread, converged.status);\n"
            "\t    return V14_RET_CONVERGENCE_TIMEOUT;\n",
            "\t    v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_CONVERGENCE_TIMEOUT, converged.qread, converged.status);\n"
            "\t    " + statement + "\n"
            "\t    return V14_RET_CONVERGENCE_TIMEOUT;\n",
            "convergence timeout return",
        )

    return mutate


def history_from_status_reread(vendor):
    return replace_once(
        vendor,
        "\t  irq_history_mask = converged.status >> 16;",
        "\t  irq_history_mask = read_reg(NPU_REG_STATUS) >> 16;",
        "history assignment",
    )


def success_cleanup_order_drift(vendor):
    return replace_once(
        vendor,
        "\t  write_reg(NPU_REG_CMD, 0x00000002);\n\t  read_val = read_reg(NPU_REG_QREAD);\n\t  write_reg(NPU_REG_CMD, 0x00000002);\n",
        "\t  read_val = read_reg(NPU_REG_QREAD);\n\t  write_reg(NPU_REG_CMD, 0x00000002);\n\t  write_reg(NPU_REG_CMD, 0x00000002);\n",
        "success cleanup",
    )


def success_publishes_failure_tuple(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_QREAD] = V14_U32_INVALID;\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = V14_U32_INVALID;\n"
        "    v14_mailbox_publish();\n}",
        "    v14_mailbox_publish();\n}",
        "success publication",
    )


def convergence_failure_discards_first_tuple(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] = V14_U32_INVALID;\n",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_QREAD] = V14_U32_INVALID;\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = V14_U32_INVALID;\n"
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] = V14_U32_INVALID;\n",
        "failure publication",
    )


def q_first_status_from_convergence(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_STATUS] = converged.status;\n",
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_STATUS] = converged.status;\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = converged.status;\n",
        "convergence tuple publication",
    )


# The qualified seam is the frozen V12_HPRINTF_SEAM anchor, which V12 maps to
# the single __wrap_printf callsite between CMD=0 and the terminal CMD=0xC. The
# TEST_CPM debug print that sits there is not, by itself, that seam.
HPRINTF_SEAM_BLOCK = '\t    /* V12_HPRINTF_SEAM */\n\t    printf("Testing CPM signals\\n");\n'
HPRINTF_DEBUG_ONLY = '\t    printf("Testing CPM signals\\n");\n'


def hprintf_seam_marker_missing(vendor):
    return replace_once(vendor, HPRINTF_SEAM_BLOCK, HPRINTF_DEBUG_ONLY, "cleanup seam")


def hprintf_seam_marker_detached(vendor):
    return replace_once(
        vendor,
        HPRINTF_SEAM_BLOCK,
        "\t    /* V12_HPRINTF_SEAM */\n\t    ret_code = ret_code;\n" + HPRINTF_DEBUG_ONLY,
        "cleanup seam",
    )


def hprintf_second_unmarked_callsite(vendor):
    return replace_once(
        vendor,
        HPRINTF_SEAM_BLOCK,
        HPRINTF_SEAM_BLOCK + '\t    printf("CPM signals done\\n");\n',
        "cleanup seam",
    )


def cleanup_invariant_mislabelled(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_CLEANUP;",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_CONVERGENCE;",
        "cleanup publication",
    )


MAILBOX_MUTATIONS = (
    ("mailbox_offset_table_swapped", mailbox_offsets_swapped, "appendix offset table does not match the schema-14 wire order"),
    ("mailbox_not_34_words", mailbox_wrong_size, "mailbox storage is not a 34-word array"),
    (
        "mailbox_reset_missing_invalid_fill",
        mailbox_reset_no_invalid_fill,
        "mailbox reset does not invalidate every appendix field",
    ),
    ("mailbox_reset_valid_not_zeroed", mailbox_reset_valid_not_zeroed, "mailbox reset does not zero mailbox_valid"),
    ("mailbox_reset_missing_dsb", mailbox_reset_no_dsb, "mailbox reset does not issue a DSB"),
    ("mailbox_magic_not_last", mailbox_magic_not_last, "mailbox magic is not the final appendix store"),
    ("mailbox_publish_missing_dsb", mailbox_publish_no_dsb, "mailbox publication does not issue a DSB"),
    (
        "mailbox_magic_published_from_second_site",
        mailbox_second_magic_site,
        "mailbox_valid is published from more than one site",
    ),
    (
        "failure_path_clears_npu",
        _inject_before_convergence_failure_return("write_reg(NPU_REG_CMD, 0x00000000);"),
        "failure path clears NPU state before serialization",
    ),
    (
        "failure_path_terminal_cmd0xc",
        _inject_before_convergence_failure_return("write_reg(NPU_REG_CMD, 0x0000000C);"),
        "failure path clears NPU state before serialization",
    ),
    (
        "failure_path_enters_hprintf",
        _inject_before_convergence_failure_return('printf("Testing CPM signals\\n");'),
        "failure path enters the H-PRINTF seam",
    ),
    ("history_from_status_reread", history_from_status_reread, "irq_history_mask is derived from a post-convergence STATUS reread"),
    ("success_cleanup_order_drift", success_cleanup_order_drift, "success cleanup ordering drifted"),
    (
        "success_publishes_failure_tuple",
        success_publishes_failure_tuple,
        "success and failure tuples are both published as valid",
    ),
    (
        "convergence_failure_discards_first_tuple",
        convergence_failure_discards_first_tuple,
        "convergence failure discards the retained first-observation tuple",
    ),
    (
        "q_first_status_synthesized_from_convergence",
        q_first_status_from_convergence,
        "first-observation STATUS fields are synthesized from convergence values",
    ),
    (
        "cleanup_invariant_reported_as_convergence",
        cleanup_invariant_mislabelled,
        "cleanup invariant is not recorded as failure_phase=CLEANUP",
    ),
    (
        "cleanup_hprintf_debug_printf_only",
        hprintf_seam_marker_missing,
        "0 seam markers in the release window",
    ),
    (
        "cleanup_hprintf_seam_marker_detached",
        hprintf_seam_marker_detached,
        "the seam marker does not anchor it",
    ),
    (
        "cleanup_hprintf_second_unmarked_callsite",
        hprintf_second_unmarked_callsite,
        "2 printf callsites in the release window",
    ),
)


def runner_copy_before_magic_check(runner):
    text = replace_once(
        runner,
        "    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {\n"
        "        pmu_diag_v14_transport_valid = 0U;\n"
        "    }\n    else {\n        pmu_diag_v14_transport_valid = 1U;\n",
        "    pmu_diag_v14_transport_valid = 1U;\n    {\n",
        "runner magic guard",
    )
    return text


def runner_serialize_swapped(runner):
    first = "    put32(&c, d->%s);\n" % APPENDIX_FIELDS[4]
    second = "    put32(&c, d->%s);\n" % APPENDIX_FIELDS[5]
    return replace_once(runner, first + second, second + first, "serialization order")


def runner_record_field_dropped(runner):
    return replace_once(runner, "    uint32_t first_irq_raised;\n", "", "record field")


def runner_no_mailbox_reset(runner):
    return replace_once(runner, "    v14_mailbox_reset();\n", "", "mailbox reset call")


def runner_payload_assert_drift(runner):
    return replace_once(runner, "PMU_DIAG_PAYLOAD_SIZE == 508U", "PMU_DIAG_PAYLOAD_SIZE == 436U", "payload assert")


def runner_schema_drift(runner):
    return replace_once(runner, "#define PMU_DIAG_SCHEMA_VERSION 14U", "#define PMU_DIAG_SCHEMA_VERSION 13U", "schema define")


def runner_build_id_drift(runner):
    return replace_once(
        runner,
        "#define PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID 0x34314950U",
        "#define PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID 0x33314950U",
        "build id define",
    )


def runner_appendix_not_contiguous(runner):
    return replace_once(
        runner,
        "    put32(&c, d->first_qread);\n",
        "    put32(&c, d->hook_armed);\n    put32(&c, d->first_qread);\n",
        "serialization run",
    )


RUNNER_MUTATIONS = (
    (
        "runner_appendix_words_not_contiguous",
        runner_appendix_not_contiguous,
        "runner serialization order does not match the appendix table",
    ),
    (
        "runner_copy_before_magic_check",
        runner_copy_before_magic_check,
        "runner appendix copy is not dominated by the mailbox magic check",
    ),
    ("runner_serialize_order_swapped", runner_serialize_swapped, "runner serialization order does not match the appendix table"),
    (
        "runner_record_field_missing",
        runner_record_field_dropped,
        "runner record does not carry the 34 appendix fields in wire order",
    ),
    ("runner_missing_mailbox_reset", runner_no_mailbox_reset, "runner does not reset the mailbox before the measured call"),
    ("runner_payload_assert_drift", runner_payload_assert_drift, "runner does not statically assert 508 payload bytes"),
    ("runner_schema_not_14", runner_schema_drift, "runner does not declare schema 14"),
    ("runner_build_id_drift", runner_build_id_drift, "runner does not declare build id 0x34314950"),
)


def run_convergence_suite(gate):
    run_vendor_mutations(gate, CONVERGE_MUTATIONS, "Q")
    run_vendor_mutations(gate, MAILBOX_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_MUTATIONS, "Q")


def run_cross_variant_suite(gate):
    docs = {}
    for variant in ("Q", "QS", "SQ"):
        try:
            docs[variant] = gate.verify_generated_sources(
                canonical_runner(variant), canonical_vendor(variant), variant
            )
        except Exception as exc:
            check("cross-variant %s manifest" % variant, False, ("%s" % exc)[:70])
            return
    convergence = {doc.get("common_convergence_source_sha256") for doc in docs.values()}
    tails = {doc.get("common_tail_source_sha256") for doc in docs.values()}
    check("all variants share one convergence-helper source digest", len(convergence) == 1, repr(convergence))
    check("all variants share one common-tail source digest", len(tails) == 1, repr(tails))
    check(
        "each variant still binds its own primary helper",
        sorted(doc["primary_helper"] for doc in docs.values())
        == ["v14_primary_q", "v14_primary_qs", "v14_primary_sq"],
    )
    for variant, doc in docs.items():
        check("%s mailbox is the 34-word appendix" % variant, doc.get("mailbox_words") == APPENDIX_WORDS)
        check("%s mailbox magic is the last stored word" % variant, doc.get("mailbox_magic_store_index") == 33)
        check("%s runner serializes 127 words" % variant, doc.get("runner_serialized_words") == TOTAL_WORDS)
        check(
            "%s failure publication invalidates the convergence tuple" % variant,
            doc.get("failure_publication_invalidates")
            == ["convergence_final_qread", "convergence_final_status"],
        )
        check(
            "%s success publication invalidates the failure tuple" % variant,
            doc.get("success_publication_invalidates") == ["failure_qread", "failure_status"],
        )
        check(
            "%s cleanup invariant retains the convergence tuple" % variant,
            doc.get("cleanup_publication_retains")
            == ["convergence_final_qread", "convergence_final_status"],
        )
        check(
            "%s success cleanup keeps the frozen stock ordering" % variant,
            doc.get("success_cleanup_order")
            == ["CMD2", "QREAD", "CMD2", "QREAD_VERIFY", "NVIC", "CMD0", "H-PRINTF", "CMD0xC"],
        )


def run_canonical_suite(gate):
    for variant in ("Q", "QS", "SQ"):
        doc = expect_accept(
            gate,
            variant,
            canonical_runner(variant),
            canonical_vendor(variant),
            "canonical %s sources pass" % variant,
        )
        if doc is None:
            continue
        check("%s manifest reports its variant id" % variant, doc.get("variant_id") == VARIANTS[variant])
        check("%s manifest claims only UNIT-QUALIFIED" % variant, doc.get("qualification") == "UNIT-QUALIFIED")
        check("%s manifest binds qsize 0x110" % variant, doc.get("qsize_expected") == "0x00000110")
        check(
            "%s manifest publishes the common convergence digest" % variant,
            isinstance(doc.get("common_convergence_source_sha256"), str)
            and len(doc.get("common_convergence_source_sha256", "")) == 64,
        )
        check(
            "%s manifest publishes the common tail digest" % variant,
            isinstance(doc.get("common_tail_source_sha256"), str)
            and len(doc.get("common_tail_source_sha256", "")) == 64,
        )
        check(
            "%s manifest reports the vendor raw-source limitation" % variant,
            doc.get("vendor_raw_source_verified") is False
            and any(
                item.startswith("vendor_raw_source_absent")
                for item in doc.get("residual_limitations", [])
            ),
            repr(doc.get("residual_limitations")),
        )
        check(
            "%s manifest names the seam without claiming the ELF callsite" % variant,
            doc.get("hprintf_seam_marker") == "V12_HPRINTF_SEAM"
            and doc.get("hprintf_seam_wrap_symbol") == "__wrap_printf"
            and doc.get("hprintf_callsite_elf_qualified") is False,
        )
        check(
            "%s manifest binds the variant id to appendix word 0" % variant,
            doc.get("variant_id_word") == 0
            and doc.get("variant_id_define") == VARIANTS[variant]
            and doc.get("variant_id_publication")
            == "pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID",
            repr(doc.get("variant_id_publication")),
        )
        check(
            "%s manifest reports the terminal cleanup as TEST_CPM-conditional" % variant,
            doc.get("cleanup_terminal_conditional_on") == "TEST_CPM==1"
            and doc.get("cleanup_terminal_branch_compiled_proof") is False
            and any(
                item.startswith("test_cpm_branch_not_preprocessed")
                for item in doc.get("residual_limitations", [])
            ),
            repr(doc.get("cleanup_terminal_conditional_on")),
        )
        check(
            "%s manifest counts all 34 appendix copies in the magic branch" % variant,
            doc.get("runner_appendix_copies") == APPENDIX_WORDS
            and doc.get("runner_copy_dominated_by_magic") is True,
        )


def run_pre_run_suite(gate):
    run_vendor_mutations(gate, PRE_RUN_MUTATIONS)


GENERATOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "patches",
    "patch_pmu_completion_visibility_v14.py",
)

EXPECTED_RUNNER_COUNT_KEYS = (
    "schema_version_branch",
    "extern_v14_globals",
    "record_append_fields",
    "field_count_block",
    "static_asserts",
    "private_driver_seam_exemption",
    "private_driver_v8_exemption",
    "reset_v14_globals",
    "copy_v14_values",
    "serialize_v14_values",
)

EXPECTED_VENDOR_COUNT_KEYS = (
    "global_defs",
    "helper_insert",
    "command_locals",
    "runtime_enable_site",
    "command_wait_block",
)


def run_generator(args):
    return subprocess.run(
        [sys.executable, GENERATOR_PATH] + list(args),
        capture_output=True,
        text=True,
    )


def run_generator_suite(gate, patcher):
    check("generator pins the frozen raw runner sha", patcher.RUNNER_SHA256 == RUNNER_SHA256)
    check("generator pins the frozen raw vendor sha", patcher.VENDOR_SHA256 == VENDOR_SHA256)
    check("generator declares schema 14", patcher.SCHEMA_VERSION == SCHEMA)
    check("generator declares build id 0x34314950", patcher.BUILD_ID == BUILD_ID)
    check("generator accepts exactly Q, QS and SQ", patcher.VARIANTS == VARIANTS)
    check("generator freezes the vendor return mapping", patcher.VENDOR_RETURN == VENDOR_RETURN)

    runner_stock = load_real_runner_stock()
    check(
        "the tracked raw runner still hashes to the frozen pin",
        hashlib.sha256(runner_stock.encode("utf-8")).hexdigest() == RUNNER_SHA256,
    )

    for variant in ("Q", "QS", "SQ"):
        try:
            runner_out, runner_counts = patcher.patch_runner(runner_stock, variant)
            vendor_out, vendor_counts = patcher.patch_vendor(PATCH_VENDOR_STOCK, variant)
        except (Exception, SystemExit) as exc:
            check("generator emits %s sources" % variant, False, ("%s" % exc)[:80])
            continue
        check("generator emits %s sources" % variant, True)
        check(
            "%s runner replacement counts are all exactly one" % variant,
            tuple(sorted(runner_counts)) == tuple(sorted(EXPECTED_RUNNER_COUNT_KEYS))
            and set(runner_counts.values()) == {1},
            repr(runner_counts),
        )
        check(
            "%s vendor replacement counts are all exactly one" % variant,
            tuple(sorted(vendor_counts)) == tuple(sorted(EXPECTED_VENDOR_COUNT_KEYS))
            and set(vendor_counts.values()) == {1},
            repr(vendor_counts),
        )
        check(
            "%s emits the frozen mailbox and tail symbols" % variant,
            all(
                symbol in vendor_out
                for symbol in (
                    "pmu_completion_visibility_v14_mailbox",
                    "v14_mailbox_reset",
                    "v14_converge",
                    "v14_primary_" + variant.lower(),
                )
            ),
        )
        inactive = [
            "v14_primary_" + other.lower() for other in ("Q", "QS", "SQ") if other != variant
        ]
        check(
            "%s leaves every inactive primary helper out of the image" % variant,
            not any(re.search(r"(?<![A-Za-z0-9_])%s\s*\(" % symbol, vendor_out) for symbol in inactive),
        )
        check(
            "%s carries the frozen return mapping" % variant,
            all(
                "#define V14_RET_%s %d" % (name, value) in vendor_out
                for name, value in VENDOR_RETURN.items()
            ),
        )
        expect_accept(gate, variant, runner_out, vendor_out, "generated %s sources pass the gate" % variant)

        repeat_runner, _ = patcher.patch_runner(runner_stock, variant)
        repeat_vendor, _ = patcher.patch_vendor(PATCH_VENDOR_STOCK, variant)
        check(
            "%s generation is deterministic for the same inputs" % variant,
            repeat_runner == runner_out and repeat_vendor == vendor_out,
        )

    for bad in ("q", "QSQ", "", "S5"):
        try:
            patcher.patch_vendor(PATCH_VENDOR_STOCK, bad)
        except (Exception, SystemExit):
            check("generator refuses variant %r" % bad, True)
        else:
            check("generator refuses variant %r" % bad, False, "accepted")

    already = patcher.patch_vendor(PATCH_VENDOR_STOCK, "Q")[0]
    for name, candidate in (
        ("generated vendor output", already),
        ("a V12-generated vendor input", PATCH_VENDOR_STOCK + "\nstatic uint32_t v12_poll_completion(void) { return 0U; }\n"),
        ("a V13-generated vendor input", PATCH_VENDOR_STOCK + "\nstatic uint32_t v13_poll_completion(void) { return 0U; }\n"),
    ):
        try:
            patcher.patch_vendor(candidate, "Q")
        except (Exception, SystemExit) as exc:
            check("%s is refused as raw input" % name, "already carries" in str(exc), str(exc)[:60])
        else:
            check("%s is refused as raw input" % name, False, "accepted")


def run_generator_cli_suite():
    result = run_generator(["--help"])
    check("generator --help exits zero", result.returncode == 0)
    for option in ("--variant", "--runner-in", "--vendor-in", "--runner-out", "--vendor-out"):
        check("generator --help documents %s" % option, option in result.stdout)
    for forbidden in ("--expect-runner-sha256", "--expect-vendor-sha256"):
        check("generator has no %s escape hatch" % forbidden, forbidden not in result.stdout)

    result = run_generator([])
    check("generator refuses an empty command line", result.returncode != 0)

    with tempfile.TemporaryDirectory() as scratch:
        runner_in = os.path.join(scratch, "runner.c")
        vendor_in = os.path.join(scratch, "u85.c")
        with open(runner_in, "w", encoding="utf-8") as handle:
            handle.write(load_real_runner_stock())
        with open(vendor_in, "w", encoding="utf-8") as handle:
            handle.write(PATCH_VENDOR_STOCK)
        result = run_generator(
            [
                "--variant",
                "Q",
                "--runner-in",
                runner_in,
                "--vendor-in",
                vendor_in,
                "--runner-out",
                os.path.join(scratch, "out_runner.c"),
                "--vendor-out",
                os.path.join(scratch, "out_vendor.c"),
            ]
        )
        check(
            "generator refuses a vendor input that is not the frozen digest",
            result.returncode != 0 and "vendor hash mismatch" in (result.stdout + result.stderr),
            (result.stdout + result.stderr).strip()[:70],
        )

        result = run_generator(
            [
                "--variant",
                "QQ",
                "--runner-in",
                runner_in,
                "--vendor-in",
                vendor_in,
                "--runner-out",
                os.path.join(scratch, "out_runner.c"),
                "--vendor-out",
                os.path.join(scratch, "out_vendor.c"),
            ]
        )
        check("generator CLI refuses an unknown variant", result.returncode != 0)


def run_generated_fixture_cli_suite(patcher):
    """Drive the real checker CLI over real generator output."""

    runner_stock = load_real_runner_stock()
    with tempfile.TemporaryDirectory() as scratch:
        digests = []
        for variant in ("Q", "QS", "SQ"):
            runner_out, _ = patcher.patch_runner(runner_stock, variant)
            vendor_out, _ = patcher.patch_vendor(PATCH_VENDOR_STOCK, variant)
            runner_path = os.path.join(scratch, "%s_runner.c" % variant)
            vendor_path = os.path.join(scratch, "%s_vendor.c" % variant)
            manifest_path = os.path.join(scratch, "%s_manifest.json" % variant)
            with open(runner_path, "w", encoding="utf-8") as handle:
                handle.write(runner_out)
            with open(vendor_path, "w", encoding="utf-8") as handle:
                handle.write(vendor_out)
            result = run_checker(
                [
                    "--allow-fixture",
                    "--variant",
                    variant,
                    "--runner-generated",
                    runner_path,
                    "--vendor-generated",
                    vendor_path,
                    "--fixture-manifest-out",
                    manifest_path,
                ]
            )
            check(
                "checker CLI passes generated %s sources" % variant,
                result.returncode == 0,
                (result.stdout + result.stderr).strip()[:70],
            )
            if result.returncode != 0:
                continue
            with open(manifest_path, "r", encoding="utf-8") as handle:
                raw = handle.read()
            doc = json.loads(raw)
            check(
                "%s fixture manifest is canonical JSON" % variant,
                raw == json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
            )
            check(
                "%s fixture manifest binds the generated vendor digest" % variant,
                doc["generated_vendor_sha256"] == hashlib.sha256(vendor_out.encode("utf-8")).hexdigest(),
            )
            check(
                "%s fixture manifest claims no real-ELF qualification" % variant,
                doc["real_elf_qualified"] is False and doc["qualification"] == "UNIT-QUALIFIED",
            )
            check(
                "%s fixture manifest hands Chunk 2 the unproven vendor half" % variant,
                doc["vendor_raw_source_verified"] is False
                and any(
                    item.startswith("hprintf_callsite_not_elf_bound")
                    for item in doc["residual_limitations"]
                ),
                repr(doc["residual_limitations"])[:70],
            )
            digests.append(doc["common_convergence_source_sha256"])
        check("generated variants share one convergence-helper digest", len(set(digests)) == 1, repr(set(digests)))


# ---------------------------------------------------------------------------
# Fail-open fixtures.
#
# Each mutation below was accepted by the gate before the rule that rejects it
# existed. They are grouped by the assumption they break rather than by the
# function they land in, because that is what a reader has to check when the
# analyzer changes: not "does this still parse" but "is this still the thing
# the rule believed".
# ---------------------------------------------------------------------------

# -- Lexical masking: a comment opener written inside a literal is text. ----

Q_LOOP_TAIL = """            obs->status = V14_U32_INVALID;
            return;
        }
    }
"""

Q_LOOP_HEAD = """    uint32_t status = 0U;

    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {
        qread = *qread_reg;
"""

Q_LOOP_HEAD_DECLS = """    uint32_t status = 0U;

"""


def lexical_hides_nvic_enable(vendor):
    return replace_once(
        vendor,
        "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);\n",
        "    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);\n"
        '    const char *v14_lex_open = "/*";\n'
        "    NVIC_EnableIRQ(NPU0_IRQn);\n"
        '    const char *v14_lex_close = "*/";\n',
        "vector install",
    )


def lexical_hides_qsize_read(vendor):
    return replace_once(
        vendor,
        Q_LOOP_TAIL,
        """            obs->status = V14_U32_INVALID;
            return;
        }
        const char *v14_lex = "//"; (void)read_reg(NPU_REG_QSIZE);
    }
""",
        "q loop tail",
    )


def lexical_hides_second_magic_store(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = V14_U32_INVALID;\n"
        "    v14_mailbox_publish();\n",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_STATUS] = V14_U32_INVALID;\n"
        '    const char *v14_lex_open = "/*";\n'
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n"
        '    const char *v14_lex_close = "*/";\n'
        "    v14_mailbox_publish();\n",
        "success publication",
    )


LEXICAL_VENDOR_MUTATIONS = (
    (
        "lexical_string_hides_nvic_enable",
        lexical_hides_nvic_enable,
        "reachable NVIC_EnableIRQ",
    ),
    (
        "lexical_string_hides_qsize_read",
        lexical_hides_qsize_read,
        "QSIZE access reachable in a primary loop",
    ),
    (
        "lexical_string_hides_second_magic_store",
        lexical_hides_second_magic_store,
        "mailbox_valid is published from more than one site",
    ),
)

# -- Loop structure: the head runs per iteration, and the for must be alone. --


def primary_head_carries_load(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; i += ((*qread_reg != 0U) ? 1U : 1U)) {\n"
        "        qread = *qread_reg;\n",
        "q loop head",
    )


def primary_head_carries_store(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; obs->iterations = ++i) {\n"
        "        qread = *qread_reg;\n",
        "q loop head",
    )


def primary_head_carries_qsize(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    for (uint32_t i = (read_reg(NPU_REG_QSIZE) != 0U) ? 1U : 1U; i <= V14_ITERATION_BOUND; ++i) {\n"
        "        qread = *qread_reg;\n",
        "q loop head",
    )


def primary_head_observes_extra_state(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    for (uint32_t i = 1U; (i <= V14_ITERATION_BOUND) && (qsize_expected != 0U); ++i) {\n"
        "        qread = *qread_reg;\n",
        "q loop head",
    )


def primary_extra_while_after_loop(vendor):
    return replace_once(
        vendor,
        Q_LOOP_TAIL,
        Q_LOOP_TAIL + "    while (*qread_reg != qsize_expected) { break; }\n",
        "q loop tail",
    )


def primary_braceless_while_before_loop(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    while (*qread_reg == 0U);\n"
        + Q_LOOP_HEAD[len(Q_LOOP_HEAD_DECLS) :],
        "q loop head",
    )


CONVERGE_PUBLICATION = """    obs->t_first = V14_U32_INVALID;
    obs->result = result;
"""


def converge_goto_back_edge(vendor):
    return replace_once(
        vendor,
        CONVERGE_PUBLICATION,
        "v14_retry:\n    ;\n    if (result == V14_CONVERGENCE_NOT_RUN) { goto v14_retry; }\n"
        + CONVERGE_PUBLICATION,
        "converge publication",
    )


def converge_head_carries_load(vendor):
    return replace_once(
        vendor,
        "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {\n"
        "        qread = *qread_reg;\n        status = *status_reg;\n",
        "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; i += ((*qread_reg != 0U) ? 1U : 1U)) {\n"
        "        qread = *qread_reg;\n        status = *status_reg;\n",
        "converge loop head",
    )


LOOP_STRUCTURE_MUTATIONS = (
    (
        "primary_loop_head_carries_a_load",
        primary_head_carries_load,
        "primary loop head carries a per-iteration effect",
    ),
    (
        "primary_loop_head_carries_a_store",
        primary_head_carries_store,
        "primary loop head carries a per-iteration effect",
    ),
    (
        "primary_loop_head_carries_qsize",
        primary_head_carries_qsize,
        "primary loop head carries a per-iteration effect",
    ),
    (
        "primary_loop_head_observes_extra_state",
        primary_head_observes_extra_state,
        "primary loop head observes qsize_expected outside the induction variable",
    ),
    (
        "primary_extra_while_loop_after_the_bounded_for",
        primary_extra_while_after_loop,
        "primary helper: an unbounded while polling loop is reachable beside the bounded for",
    ),
    (
        "primary_braceless_while_loop_before_the_bounded_for",
        primary_braceless_while_before_loop,
        "primary helper: an unbounded while polling loop is reachable beside the bounded for",
    ),
    (
        "converge_loop_head_carries_a_load",
        converge_head_carries_load,
        "convergence loop head carries a per-iteration effect",
    ),
    (
        "converge_goto_back_edge_after_the_bounded_for",
        converge_goto_back_edge,
        "convergence helper: a goto back-edge is reachable beside the bounded for",
    ),
)


# -- Jump topology: an exempt guard has to be single-entry and terminating. --


def primary_depth0_continue(vendor):
    return replace_once(
        vendor,
        Q_LOOP_TAIL,
        """            obs->status = V14_U32_INVALID;
            return;
        }
        if (qread == 0U) { continue; }
    }
""",
        "q loop tail",
    )


def primary_goto_into_terminating_guard(vendor):
    text = replace_once(
        vendor,
        "        if (qread == qsize_expected) {\n            obs->t_first = DWT->CYCCNT;\n",
        "        if (qread == qsize_expected) {\nv14_publish_entry:\n            obs->t_first = DWT->CYCCNT;\n",
        "q completion guard",
    )
    return replace_once(
        text,
        "            return;\n        }\n    }\n",
        "            return;\n        }\n        if (qread == 0U) { goto v14_publish_entry; }\n    }\n",
        "q loop back edge",
    )


def converge_goto_out_of_terminating_guard(vendor):
    return replace_once(
        vendor,
        """            result = V14_CONVERGENCE_SUCCESS;
            iterations = i;
            break;
        }
    }
""",
        """            result = V14_CONVERGENCE_SUCCESS;
            iterations = i;
            goto v14_done;
        }
    }
v14_done:
    ;
""",
        "converge success guard",
    )


JUMP_TOPOLOGY_MUTATIONS = (
    (
        "primary_depth0_continue_reaches_the_back_edge",
        primary_depth0_continue,
        "primary loop: a continue statement reaches the loop back-edge",
    ),
    (
        "primary_goto_enters_the_terminating_guard",
        primary_goto_into_terminating_guard,
        "primary helper: a goto back-edge is reachable beside the bounded for",
    ),
    (
        "converge_goto_leaves_the_terminating_guard",
        converge_goto_out_of_terminating_guard,
        "convergence helper: a goto back-edge is reachable beside the bounded for",
    ),
)


# -- Aliases: a second name for the same storage is the same storage. -------


def primary_obs_alias_store(vendor):
    return replace_once(
        vendor,
        Q_LOOP_HEAD,
        Q_LOOP_HEAD_DECLS
        + "    struct v14_observation_t *obs_alias = obs;\n"
        + Q_LOOP_HEAD[len(Q_LOOP_HEAD_DECLS) :]
        + "        obs_alias->iterations = i;\n",
        "q loop head",
    )


def primary_raw_register_status_read(vendor):
    return replace_once(
        vendor,
        Q_LOOP_TAIL,
        """            obs->status = V14_U32_INVALID;
            return;
        }
        status = *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    }
""",
        "q loop tail",
    )


def first_tuple_through_mailbox_alias(vendor):
    return replace_once(
        vendor,
        "\t  irq_history_mask = converged.status >> 16;\n",
        "\t  volatile uint32_t *mb_alias = pmu_completion_visibility_v14_mailbox;\n"
        "\t  mb_alias[V14_MBOX_FIRST_QREAD] = converged.qread;\n"
        "\t  irq_history_mask = converged.status >> 16;\n",
        "cleanup seam",
    )


ALIAS_MUTATIONS = (
    (
        "primary_per_loop_store_through_an_obs_alias",
        primary_obs_alias_store,
        "primary loop carries a per-iteration store/call/timestamp",
    ),
    (
        "primary_status_read_through_a_raw_register_address",
        primary_raw_register_status_read,
        "Q primary loop reads STATUS",
    ),
    (
        "first_tuple_stored_through_a_mailbox_alias",
        first_tuple_through_mailbox_alias,
        "first-observation STATUS fields are synthesized from convergence values",
    ),
)


# -- Variant identity: word 0 is what tells Q evidence from SQ evidence. ----

VARIANT_ID_PUBLICATION = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;\n"
)


def variant_id_define_wrong(vendor):
    return replace_once(vendor, "#define V14_VARIANT_ID 1U", "#define V14_VARIANT_ID 2U", "variant id define")


def variant_id_not_published(vendor):
    return replace_once(vendor, VARIANT_ID_PUBLICATION, "", "variant id publication")


def variant_id_hardcoded(vendor):
    return replace_once(
        vendor,
        VARIANT_ID_PUBLICATION,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = 3U;\n",
        "variant id publication",
    )


def variant_id_swapped_to_another_word(vendor):
    return replace_once(
        vendor,
        VARIANT_ID_PUBLICATION,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRE_PROGRAM_STATUS] = V14_VARIANT_ID;\n",
        "variant id publication",
    )


def variant_id_through_mailbox_alias(vendor):
    return replace_once(
        vendor,
        VARIANT_ID_PUBLICATION,
        "    volatile uint32_t *mb_alias = pmu_completion_visibility_v14_mailbox;\n"
        "    mb_alias[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;\n",
        "variant id publication",
    )


VARIANT_ID_MUTATIONS = (
    (
        "variant_id_define_is_another_variant",
        variant_id_define_wrong,
        "variant id define is not the selected variant",
    ),
    (
        "variant_id_never_reaches_mailbox_word_0",
        variant_id_not_published,
        "variant id is not published to mailbox word 0",
    ),
    (
        "variant_id_word_0_is_hardcoded",
        variant_id_hardcoded,
        "mailbox word 0 does not publish V14_VARIANT_ID",
    ),
    (
        "variant_id_published_to_the_wrong_word",
        variant_id_swapped_to_another_word,
        "variant id is not published to mailbox word 0",
    ),
    (
        "variant_id_published_through_a_mailbox_alias",
        variant_id_through_mailbox_alias,
        "variant id is published through a mailbox alias or a raw index",
    ),
)


# -- Magic safety: one publication, at word 33, in the frozen spelling. -----


def magic_stored_by_numeric_index_and_literal(vendor):
    return replace_once(
        vendor,
        "\t  irq_history_mask = converged.status >> 16;\n",
        "\t  pmu_completion_visibility_v14_mailbox[33] = 0x5631344DU;\n"
        "\t  irq_history_mask = converged.status >> 16;\n",
        "cleanup seam",
    )


def magic_stored_through_mailbox_alias(vendor):
    return replace_once(
        vendor,
        "\t  irq_history_mask = converged.status >> 16;\n",
        "\t  volatile uint32_t *mb_alias = pmu_completion_visibility_v14_mailbox;\n"
        "\t  mb_alias[33] = 0x5631344DU;\n"
        "\t  irq_history_mask = converged.status >> 16;\n",
        "cleanup seam",
    )


MAGIC_SAFETY_MUTATIONS = (
    (
        "magic_published_by_numeric_index_and_literal",
        magic_stored_by_numeric_index_and_literal,
        "mailbox_valid is published from more than one site",
    ),
    (
        "magic_published_through_a_mailbox_alias",
        magic_stored_through_mailbox_alias,
        "mailbox_valid is published from more than one site",
    ),
)


RUNNER_MAGIC_GUARD = "    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {\n"


def runner_copy_in_invalid_branch(runner):
    return replace_once(
        runner,
        "        pmu_diag_v14_transport_valid = 0U;\n    }\n",
        "        pmu_diag_v14_transport_valid = 0U;\n"
        "        d.first_qread = pmu_completion_visibility_v14_mailbox[9];\n    }\n",
        "runner invalid branch",
    )


def runner_copy_ahead_of_the_guard(runner):
    return replace_once(
        runner,
        RUNNER_MAGIC_GUARD,
        "    d.first_status = pmu_completion_visibility_v14_mailbox[10];\n" + RUNNER_MAGIC_GUARD,
        "runner magic guard",
    )


RUNNER_DOMINANCE_MUTATIONS = (
    (
        "runner_copy_in_the_magic_invalid_branch",
        runner_copy_in_invalid_branch,
        "runner copies the appendix outside the mailbox-magic branch",
    ),
    (
        "runner_copy_ahead_of_the_magic_guard",
        runner_copy_ahead_of_the_guard,
        "runner copies the appendix outside the mailbox-magic branch",
    ),
)


def lexical_hides_runner_copy(runner):
    return replace_once(
        runner,
        "        pmu_diag_v14_transport_valid = 0U;\n    }\n",
        "        pmu_diag_v14_transport_valid = 0U;\n"
        '        const char *v14_lex_open = "/*";\n'
        "        d.first_qread = pmu_completion_visibility_v14_mailbox[9];\n"
        '        const char *v14_lex_close = "*/";\n    }\n',
        "runner invalid branch",
    )


LEXICAL_RUNNER_MUTATIONS = (
    (
        "lexical_string_hides_runner_copy",
        lexical_hides_runner_copy,
        "runner copies the appendix outside the mailbox-magic branch",
    ),
)


# -- Fail-closed: a named rejection, never a traceback. ---------------------


def queue_programming_without_qsize_write(vendor):
    return replace_once(
        vendor, "    write_reg(NPU_REG_QSIZE, u32CmdQueueSize);\n", "", "queue programming"
    )


def malformed_qsize_define(vendor):
    return replace_once(
        vendor,
        "#define V14_QSIZE_EXPECTED 0x00000110U",
        "#define V14_QSIZE_EXPECTED 0x0000011ZU",
        "qsize define",
    )


def malformed_bound_define(vendor):
    return replace_once(
        vendor, "#define V14_ITERATION_BOUND 10000U", "#define V14_ITERATION_BOUND 10O00U", "bound define"
    )


def malformed_offset_define(vendor):
    return replace_once(
        vendor, "#define V14_MBOX_MAILBOX_VALID 33U", "#define V14_MBOX_MAILBOX_VALID 33QU", "offset define"
    )


def malformed_unread_return_define(vendor):
    return replace_once(
        vendor,
        "#define V14_RET_CLEANUP_INVARIANT 7",
        "#define V14_RET_CLEANUP_INVARIANT 7Z",
        "vendor return define",
    )


FAIL_CLOSED_MUTATIONS = (
    (
        "queue_programming_without_a_qsize_write",
        queue_programming_without_qsize_write,
        "queue programming does not write QSIZE",
    ),
    (
        # This one no rule reads, so a malformed value used to be dropped in
        # silence -- which is the shape of the defect the other three only
        # mis-name: the parse result is discarded and the source is judged as
        # though the macro were never written.
        "malformed_unread_v14_define",
        malformed_unread_return_define,
        "malformed numeric define: V14_RET_CLEANUP_INVARIANT",
    ),
    (
        "malformed_qsize_expected_define",
        malformed_qsize_define,
        "malformed numeric define: V14_QSIZE_EXPECTED",
    ),
    (
        "malformed_iteration_bound_define",
        malformed_bound_define,
        "malformed numeric define: V14_ITERATION_BOUND",
    ),
    (
        "malformed_appendix_offset_define",
        malformed_offset_define,
        "malformed numeric define: V14_MBOX_MAILBOX_VALID",
    ),
)


def magic_store_with_a_spaced_semicolon(vendor):
    return replace_once(
        vendor,
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n",
        "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID ;\n",
        "magic publication",
    )


# -- TEST_CPM: the terminal cleanup writes live in a preprocessor branch. ---
#
# These are mutation builders, not tests. The ``test_`` prefix made pytest
# collect them as test functions needing a ``vendor`` fixture, so running the
# directory under pytest errored on this file even though the suite's own entry
# point exercises them. The name says what they are instead.


def mutate_cpm_compiled_out(vendor):
    return replace_once(vendor, "#define TEST_CPM 1", "#define TEST_CPM 0", "TEST_CPM define")


def mutate_cpm_guard_removed(vendor):
    text = replace_once(vendor, "#if(TEST_CPM==1)\n", "", "TEST_CPM guard")
    return replace_once(text, "#endif\n", "", "TEST_CPM endif")


TEST_CPM_MUTATIONS = (
    (
        "test_cpm_branch_compiled_out",
        mutate_cpm_compiled_out,
        "cleanup terminal sequence is compiled out: TEST_CPM is 0, not 1",
    ),
    (
        "test_cpm_guard_removed_from_the_terminal_sequence",
        mutate_cpm_guard_removed,
        "cleanup terminal sequence is not guarded by one #if(TEST_CPM==1)",
    ),
)


def run_fail_open_suite(gate):
    run_vendor_mutations(gate, LEXICAL_VENDOR_MUTATIONS, "Q")
    run_vendor_mutations(gate, LOOP_STRUCTURE_MUTATIONS, "Q")
    run_vendor_mutations(gate, JUMP_TOPOLOGY_MUTATIONS, "Q")
    run_vendor_mutations(gate, ALIAS_MUTATIONS, "Q")
    run_vendor_mutations(gate, VARIANT_ID_MUTATIONS, "Q")
    run_vendor_mutations(gate, MAGIC_SAFETY_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_DOMINANCE_MUTATIONS, "Q")
    run_runner_mutations(gate, LEXICAL_RUNNER_MUTATIONS, "Q")
    run_vendor_mutations(gate, FAIL_CLOSED_MUTATIONS, "Q")
    run_vendor_mutations(gate, TEST_CPM_MUTATIONS, "Q")

    # Every variant carries its own id, so the binding is proven per variant
    # rather than once on Q's behalf.
    for variant in ("QS", "SQ"):
        for other in sorted(set(VARIANTS) - {variant}):
            REJECTED_FIXTURES.add("variant_id_define_is_%s_under_%s" % (other, variant))
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                replace_once(
                    canonical_vendor(variant),
                    "#define V14_VARIANT_ID %dU" % VARIANTS[variant],
                    "#define V14_VARIANT_ID %dU" % VARIANTS[other],
                    "variant id define",
                ),
                "variant_id_define_is_%s_under_%s" % (other, variant),
                "variant id define is not the selected variant",
            )

    # A whitespace-only respelling of the frozen magic store is the same store.
    # It used to reach a bare ``str.index`` and raise, which is a crash rather
    # than a verdict; the gate has to survive it and still say PASS.
    expect_accept(
        gate,
        "Q",
        canonical_runner("Q"),
        magic_store_with_a_spaced_semicolon(canonical_vendor("Q")),
        "a whitespace respelling of the magic store is a verdict, not a crash",
    )

def run_fail_closed_cli_suite(patcher):
    """Bad paths and bare relative filenames are FAIL lines, not tracebacks."""

    check(
        "generator tolerates a bare relative output filename",
        patcher._ensure_parent_dir("v14_bare_output.c") is None,
    )

    with tempfile.TemporaryDirectory() as scratch:
        runner_path = os.path.join(scratch, "runner.c")
        vendor_path = os.path.join(scratch, "vendor.c")
        with open(runner_path, "w", encoding="utf-8") as handle:
            handle.write(canonical_runner("Q"))
        with open(vendor_path, "w", encoding="utf-8") as handle:
            handle.write(canonical_vendor("Q"))

        result = run_checker(
            [
                "--allow-fixture",
                "--variant",
                "Q",
                "--runner-generated",
                runner_path,
                "--vendor-generated",
                vendor_path,
                "--fixture-manifest-out",
                os.path.join(scratch, "absent", "manifest.json"),
            ]
        )
        combined = result.stdout + result.stderr
        check(
            "an unwritable manifest path is a named FAIL, not a traceback",
            result.returncode == 1
            and "FAIL fixture manifest is not writable" in combined
            and "Traceback" not in combined,
            combined.strip()[:70],
        )

        manifest_name = "bare_manifest.json"
        result = subprocess.run(
            [
                sys.executable,
                CHECKER_PATH,
                "--allow-fixture",
                "--variant",
                "Q",
                "--runner-generated",
                runner_path,
                "--vendor-generated",
                vendor_path,
                "--fixture-manifest-out",
                manifest_name,
            ],
            capture_output=True,
            text=True,
            cwd=scratch,
        )
        check(
            "the checker writes a bare relative manifest filename",
            result.returncode == 0 and os.path.isfile(os.path.join(scratch, manifest_name)),
            (result.stdout + result.stderr).strip()[:70],
        )

        result = run_generator(
            [
                "--variant",
                "Q",
                "--runner-in",
                os.path.join(scratch, "absent_runner.c"),
                "--vendor-in",
                vendor_path,
                "--runner-out",
                os.path.join(scratch, "out_runner.c"),
                "--vendor-out",
                os.path.join(scratch, "out_vendor.c"),
            ]
        )
        combined = result.stdout + result.stderr
        check(
            "a missing generator input is a named FAIL, not a traceback",
            result.returncode != 0
            and "FAIL input is unreadable" in combined
            and "Traceback" not in combined,
            combined.strip()[:70],
        )


# ---------------------------------------------------------------------------
# Structural matching: reformatting the source must not move a verdict.
#
# Every rule below used to be a literal substring, so a space between a callee
# and its parenthesis, a newline inside an argument list, or a comment in the
# middle of a call was a rule the source walked around. The accept fixtures
# respell the canonical source and must still pass; the reject fixtures are the
# same evasions carrying a forbidden construct and must still fail.
# ---------------------------------------------------------------------------


def respell(old, new):
    return lambda vendor: replace_once(vendor, old, new, "respelling")


WHITESPACE_RESPELLINGS = (
    (
        "a spaced pre-submit QSIZE read",
        respell(
            "qsize_expected = read_reg(NPU_REG_QSIZE);",
            "qsize_expected = read_reg ( NPU_REG_QSIZE );",
        ),
    ),
    (
        "a pre-submit STATUS read split over three lines",
        respell(
            "pre_submit_status = read_reg(NPU_REG_STATUS);",
            "pre_submit_status = read_reg(\n\t      NPU_REG_STATUS\n\t  );",
        ),
    ),
    (
        "a comment between the pre-program callee and its parenthesis",
        respell(
            "pre_program_status = read_reg(NPU_REG_STATUS);",
            "pre_program_status = read_reg /* gate */ (NPU_REG_STATUS);",
        ),
    ),
    (
        "a spaced QSIZE programming write",
        respell(
            "write_reg(NPU_REG_QSIZE, u32CmdQueueSize);",
            "write_reg ( NPU_REG_QSIZE , u32CmdQueueSize );",
        ),
    ),
    (
        "a submit write broken across two lines",
        respell(
            "write_reg(NPU_REG_CMD, read_val | 0x00000001);",
            "write_reg( NPU_REG_CMD ,\n\t      read_val | 0x00000001 );",
        ),
    ),
    (
        "a comment inside the first cleanup CMD2",
        respell(
            "\t  write_reg(NPU_REG_CMD, 0x00000002);\n\t  read_val = read_reg(NPU_REG_QREAD);",
            "\t  write_reg /* isr */ (NPU_REG_CMD, 0x00000002);\n\t  read_val = read_reg (NPU_REG_QREAD);",
        ),
    ),
    (
        "a spaced NVIC clear in the cleanup tail",
        respell("\t  NVIC_ClearPendingIRQ(NPU0_IRQn);", "\t  NVIC_ClearPendingIRQ ( NPU0_IRQn );"),
    ),
    (
        "a terminal CMD=0xC broken across two lines",
        respell(
            "write_reg(NPU_REG_CMD, 0x0000000C);",
            "write_reg (\n\t        NPU_REG_CMD , 0x0000000C );",
        ),
    ),
    (
        "a spaced stop CMD=0",
        respell(
            "\t  write_reg(NPU_REG_CMD, 0x00000000);", "\t  write_reg( NPU_REG_CMD, 0x00000000 );"
        ),
    ),
    (
        "a spaced NVIC_SetVector install",
        respell(
            "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
            "NVIC_SetVector ( NPU0_IRQn , ( uint32_t ) & u85_irq_handler );",
        ),
    ),
    (
        "a respaced H-PRINTF seam marker",
        respell("/* V12_HPRINTF_SEAM */", "/*   V12_HPRINTF_SEAM   */"),
    ),
)


def nvic_enable_with_a_space(vendor):
    return replace_once(
        vendor,
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n\n    pmu_completion",
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n    NVIC_EnableIRQ (NPU0_IRQn);\n\n    pmu_completion",
        "runtime setup",
    )


def nvic_enable_through_core_alias(vendor):
    return replace_once(
        vendor,
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n\n    pmu_completion",
        "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n    __NVIC_EnableIRQ(NPU0_IRQn);\n\n    pmu_completion",
        "runtime setup",
    )


def spaced_second_qsize_read(vendor):
    return replace_once(
        vendor,
        "\t  pre_submit_status = read_reg(NPU_REG_STATUS);",
        "\t  qsize_expected = read_reg ( NPU_REG_QSIZE );\n\t  pre_submit_status = read_reg(NPU_REG_STATUS);",
        "pre-submit status read",
    )


def spaced_cmd_write_before_programming(vendor):
    return replace_once(
        vendor,
        "    write_reg(NPU_REG_QBASE,",
        "    write_reg ( NPU_REG_CMD , 0x00000001 );\n    write_reg(NPU_REG_QBASE,",
        "queue programming",
    )


WHITESPACE_EVASION_MUTATIONS = (
    (
        "nvic_enable_written_with_a_space",
        nvic_enable_with_a_space,
        "reachable NVIC_EnableIRQ",
    ),
    (
        "nvic_enable_written_as_the_core_alias",
        nvic_enable_through_core_alias,
        "reachable NVIC_EnableIRQ",
    ),
    (
        "second_qsize_read_written_with_spaces",
        spaced_second_qsize_read,
        "QSIZE is loaded more than once",
    ),
    (
        "cmd_write_before_programming_written_with_spaces",
        spaced_cmd_write_before_programming,
        "state-transitioning CMD write between the pre-program gate and queue programming",
    ),
)


# ---------------------------------------------------------------------------
# MMIO provenance: a register is the register whatever name reaches it.
# ---------------------------------------------------------------------------

MMIO_BINDINGS = """    volatile uint32_t *const qread_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD);
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
"""

# The same binding block opens the primary helper and the convergence helper,
# so each fixture anchors on the locals that follow the one it means.
PRIMARY_LOCALS = "    uint32_t qread = 0U;\n    uint32_t status = 0U;\n\n"
CONVERGE_LOCALS = "    uint32_t qread = 0U;\n    uint32_t status = 0U;\n    uint32_t result"
RESET_GUARD = "        if ((status & V14_STATUS_RESET) != 0U) {\n"
PRIMARY_RESET_TAIL = "            obs->t_first = V14_U32_INVALID;"
CONVERGE_RESET_TAIL = "            result = V14_CONVERGENCE_RESET;"
Q_LOOP_READ = "        qread = *qread_reg;\n        if (qread == qsize_expected) {"
DUAL_LOOP_READS = {
    "QS": "        qread = *qread_reg;\n        status = *status_reg;\n",
    "SQ": "        status = *status_reg;\n        qread = *qread_reg;\n",
}


def bind_in_primary(vendor, declarations):
    return replace_once(
        vendor,
        MMIO_BINDINGS + PRIMARY_LOCALS,
        MMIO_BINDINGS + declarations + PRIMARY_LOCALS,
        "primary bindings",
    )


def bind_in_converge(vendor, declarations):
    return replace_once(
        vendor,
        MMIO_BINDINGS + CONVERGE_LOCALS,
        MMIO_BINDINGS + declarations + CONVERGE_LOCALS,
        "convergence bindings",
    )


def q_loop_reads(vendor, replacement):
    return replace_once(vendor, Q_LOOP_READ, replacement, "Q primary loop read")


def read_through(declarations, name):
    def mutate(vendor):
        return q_loop_reads(
            bind_in_primary(vendor, declarations),
            "        qread = *%s;\n        if (qread == qsize_expected) {" % name,
        )

    return mutate


def bare_base_and_offsets(vendor):
    """The frozen bindings respelled as the base plus the source's own offsets."""

    text = replace_once(
        vendor,
        "#define V14_APPENDIX_WORDS 34U",
        "#define V14_APPENDIX_WORDS 34U\n#define NPU_REG_QREAD 0x0018\n#define NPU_REG_STATUS 0x0004",
        "appendix words define",
    )
    return replace_once(
        text,
        MMIO_BINDINGS + PRIMARY_LOCALS,
        "    volatile uint32_t *const qread_reg =\n"
        "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x0018);\n"
        "    volatile uint32_t *const status_reg =\n"
        "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x0004);\n" + PRIMARY_LOCALS,
        "primary bindings",
    )


MMIO_RESPELLINGS = (
    (
        "a primary read through a copied pointer",
        read_through("    volatile uint32_t *const qread_copy = qread_reg;\n", "qread_copy"),
    ),
    (
        "a primary read through a chained alias",
        read_through(
            "    volatile uint32_t *const qread_one = qread_reg;\n"
            "    volatile uint32_t *const qread_two = qread_one;\n",
            "qread_two",
        ),
    ),
    (
        "a primary read through a cast of a bound pointer",
        read_through(
            "    volatile uint32_t *const qread_cast = (volatile uint32_t *)(uintptr_t)qread_reg;\n",
            "qread_cast",
        ),
    ),
    (
        "a primary read through an address-of index",
        read_through(
            "    volatile uint32_t *const qread_index =\n"
            "        &((volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS))[NPU_REG_QREAD / 4];\n",
            "qread_index",
        ),
    ),
    (
        "a primary read through the bare base plus the source's own offset",
        bare_base_and_offsets,
    ),
)


def unknown_region_pointer(vendor):
    return q_loop_reads(
        bind_in_primary(
            vendor,
            "    volatile uint32_t *const spare_reg =\n"
            "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x40);\n",
        ),
        "        qread = *qread_reg;\n        status = *spare_reg;\n        if (qread == qsize_expected) {",
    )


def pointer_rebound_to_two_registers(vendor):
    return q_loop_reads(
        bind_in_primary(vendor, "    volatile uint32_t *both_reg = qread_reg;\n"),
        "        both_reg = status_reg;\n        qread = *qread_reg;\n"
        "        if (qread == qsize_expected) {",
    )


ALIAS_DECLARATIONS = (
    "    volatile uint32_t *const qread_alias = qread_reg;\n"
    "    volatile uint32_t *const status_alias = status_reg;\n"
)


def _dual_order_inverted(variant):
    def mutate(vendor):
        inverted = DUAL_LOOP_READS["SQ" if variant == "QS" else "QS"].replace(
            "qread_reg", "qread_alias"
        ).replace("status_reg", "status_alias")
        return replace_once(
            bind_in_primary(vendor, ALIAS_DECLARATIONS),
            DUAL_LOOP_READS[variant] + RESET_GUARD + PRIMARY_RESET_TAIL,
            inverted + RESET_GUARD + PRIMARY_RESET_TAIL,
            "%s primary loop reads" % variant,
        )

    return mutate


def converge_order_inverted_through_aliases(vendor):
    return replace_once(
        bind_in_converge(vendor, ALIAS_DECLARATIONS),
        DUAL_LOOP_READS["QS"] + RESET_GUARD + CONVERGE_RESET_TAIL,
        "        status = *status_alias;\n        qread = *qread_alias;\n"
        + RESET_GUARD
        + CONVERGE_RESET_TAIL,
        "convergence loop reads",
    )


def converge_qsize_pointer(vendor):
    return bind_in_converge(
        vendor,
        "    volatile uint32_t *const qsize_reg =\n"
        "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE);\n",
    )


def primary_qsize_read_through_raw_address(vendor):
    return q_loop_reads(
        vendor,
        "        qread = *qread_reg;\n"
        "        status = *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE);\n"
        "        if (qread == qsize_expected) {",
    )


def running_qsize_through_raw_pointer(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  qsize_expected = *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE);\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "submit timestamp",
    )


def raw_pointer_cmd_start_before_programming(vendor):
    return replace_once(
        vendor,
        "    write_reg(NPU_REG_QBASE,",
        "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD) = 0x00000001U;\n"
        "    write_reg(NPU_REG_QBASE,",
        "queue programming",
    )


def second_submit_as_a_bare_one(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  write_reg(NPU_REG_CMD, 1);\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "submit timestamp",
    )


def failure_path_clears_cmd_through_raw_pointer(vendor):
    return replace_once(
        vendor,
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);",
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);\n"
        "\t      *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD) = 0x00000000U;",
        "primary reset failure path",
    )


def failure_path_prints_through_the_seam(vendor):
    return replace_once(
        vendor,
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_HARDWARE_FAULT, primary.qread, primary.status);",
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_HARDWARE_FAULT, primary.qread, primary.status);\n"
        '\t      printf ("primary fault\\n");',
        "primary fault failure path",
    )


def extra_cleanup_cmd2_as_a_bare_two(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_BEFORE_FINAL_CLEAR]",
        "\t  write_reg(NPU_REG_CMD, 2);\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_NVIC_PENDING_BEFORE_FINAL_CLEAR]",
        "final pending probe",
    )


# A second name for a bound register pointer is that register. Reading STATUS
# through one used to be invisible: the read simply did not appear in the
# ordered effect sequence, so a Q loop could read STATUS, and a dual loop or the
# convergence tail could reload it, without any rule seeing it happen.
STATUS_ALIAS_DECLARATION = "    volatile uint32_t *const status_alias = status_reg;\n"

# The same holds for an address written as the base plus a bare offset: nothing
# in it names a register, so a QSIZE pointer spelled this way used to bind to
# nothing at all.
BARE_QSIZE_OFFSET_DEFINE = (
    "#define V14_APPENDIX_WORDS 34U",
    "#define V14_APPENDIX_WORDS 34U\n#define NPU_REG_QSIZE 0x001C",
)
BARE_QSIZE_POINTER = (
    "    volatile uint32_t *const spare_reg =\n"
    "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x001C);\n"
)


def q_primary_status_read_through_alias(vendor):
    return q_loop_reads(
        bind_in_primary(vendor, STATUS_ALIAS_DECLARATION),
        "        qread = *qread_reg;\n        status = *status_alias;\n"
        "        if (qread == qsize_expected) {",
    )


def qs_primary_status_reload_through_alias(vendor):
    return replace_once(
        bind_in_primary(vendor, STATUS_ALIAS_DECLARATION),
        DUAL_LOOP_READS["QS"] + RESET_GUARD + PRIMARY_RESET_TAIL,
        DUAL_LOOP_READS["QS"]
        + "        status = *status_alias;\n"
        + RESET_GUARD
        + PRIMARY_RESET_TAIL,
        "QS primary loop reads",
    )


def converge_status_reload_through_alias(vendor):
    return replace_once(
        bind_in_converge(vendor, STATUS_ALIAS_DECLARATION),
        DUAL_LOOP_READS["QS"] + RESET_GUARD + CONVERGE_RESET_TAIL,
        DUAL_LOOP_READS["QS"]
        + "        status = *status_alias;\n"
        + RESET_GUARD
        + CONVERGE_RESET_TAIL,
        "convergence loop reads",
    )


def primary_qsize_read_through_bare_offset(vendor):
    text = replace_once(vendor, *BARE_QSIZE_OFFSET_DEFINE, "appendix words define")
    return q_loop_reads(
        bind_in_primary(text, BARE_QSIZE_POINTER),
        "        qread = *qread_reg;\n        status = *spare_reg;\n"
        "        if (qread == qsize_expected) {",
    )


def converge_qsize_pointer_through_bare_offset(vendor):
    text = replace_once(vendor, *BARE_QSIZE_OFFSET_DEFINE, "appendix words define")
    return bind_in_converge(text, BARE_QSIZE_POINTER)


MMIO_PROVENANCE_MUTATIONS = (
    (
        "q_primary_status_read_through_an_alias",
        q_primary_status_read_through_alias,
        "Q primary loop reads STATUS",
    ),
    (
        "convergence_status_reload_through_an_alias",
        converge_status_reload_through_alias,
        "convergence loop reloads STATUS",
    ),
    (
        "primary_qsize_read_through_a_bare_offset",
        primary_qsize_read_through_bare_offset,
        "QSIZE access reachable in a primary loop",
    ),
    (
        "convergence_qsize_pointer_through_a_bare_offset",
        converge_qsize_pointer_through_bare_offset,
        "QSIZE access reachable in the convergence tail",
    ),
    (
        "unknown_npu_region_pointer_in_the_primary_loop",
        unknown_region_pointer,
        "binds an NPU-region pointer this gate cannot resolve to one register",
    ),
    (
        "primary_pointer_rebound_to_two_registers",
        pointer_rebound_to_two_registers,
        "binds an NPU-region pointer this gate cannot resolve to one register",
    ),
    (
        "convergence_read_order_inverted_through_aliases",
        converge_order_inverted_through_aliases,
        "convergence read order is not QREAD then STATUS",
    ),
    (
        "convergence_qsize_pointer_through_a_raw_address",
        converge_qsize_pointer,
        "QSIZE access reachable in the convergence tail",
    ),
    (
        "primary_qsize_read_through_a_raw_address",
        primary_qsize_read_through_raw_address,
        "QSIZE access reachable in a primary loop",
    ),
    (
        "running_qsize_read_through_a_raw_pointer",
        running_qsize_through_raw_pointer,
        "QSIZE is loaded more than once",
    ),
    (
        "raw_pointer_cmd_start_between_gate_and_programming",
        raw_pointer_cmd_start_before_programming,
        "state-transitioning CMD write between the pre-program gate and queue programming",
    ),
    (
        "second_submit_written_as_a_bare_one",
        second_submit_as_a_bare_one,
        "command path does not carry exactly one NPU submit write",
    ),
    (
        "failure_path_clears_cmd_through_a_raw_pointer",
        failure_path_clears_cmd_through_raw_pointer,
        "failure path clears NPU state before serialization",
    ),
    (
        "failure_path_prints_through_the_seam",
        failure_path_prints_through_the_seam,
        "failure path enters the H-PRINTF seam",
    ),
    (
        "extra_cleanup_cmd2_written_as_a_bare_two",
        extra_cleanup_cmd2_as_a_bare_two,
        "success cleanup ordering drifted",
    ),
)


# ---------------------------------------------------------------------------
# Predicate connectives: naming the terms is not deciding on them.
# ---------------------------------------------------------------------------

CONVERGENCE_CONJUNCTION = """        if ((qread == qsize_expected) &&
            ((status & V14_STATUS_CMD_END) != 0U) &&
            ((status & V14_STATUS_IRQ_RAISED) != 0U) &&
            ((status & V14_STATUS_STATE) == 0U)) {"""
PRIMARY_DISJUNCTION = (
    "        if ((qread == qsize_expected) || ((status & V14_STATUS_CMD_END) != 0U)) {"
)


def convergence_predicate_disjoined(vendor):
    """The four same-iteration terms joined with ``||`` instead of ``&&``.

    Every required term is still spelled out, so a gate that greps for them
    still finds all four -- while the branch now succeeds on a stopped bit
    alone, with the queue undrained and bits 5 and 1 clear.
    """

    return replace_once(
        vendor,
        CONVERGENCE_CONJUNCTION,
        CONVERGENCE_CONJUNCTION.replace("&&", "||"),
        "convergence success predicate",
    )


def primary_completion_conjoined(vendor):
    """The QS/SQ first-observation exit joined with ``&&`` instead of ``||``.

    An AND-only exit can only ever report SAME_ITERATION: Q_FIRST and S5_FIRST
    become unreachable, and the variant matrix measures one thing three times.
    """

    return replace_once(
        vendor,
        PRIMARY_DISJUNCTION,
        PRIMARY_DISJUNCTION.replace("||", "&&"),
        "primary completion predicate",
    )


def convergence_predicate_bit_value_inverted(vendor):
    """``stopped`` tested for set rather than clear, with the term untouched."""

    return replace_once(
        vendor,
        "((status & V14_STATUS_STATE) == 0U)) {",
        "((status & V14_STATUS_STATE) != 0U)) {",
        "convergence stopped term",
    )


# ---------------------------------------------------------------------------
# Load-to-gate dataflow: a gate is credited for the load it actually consumes.
# ---------------------------------------------------------------------------


def pre_program_status_from_a_constant(vendor):
    return replace_once(
        vendor,
        "    pre_program_status = read_reg(NPU_REG_STATUS);\n",
        "    pre_program_status = 0U;\n    (void)read_reg(NPU_REG_STATUS);\n",
        "pre-program STATUS load",
    )


def pre_submit_status_from_a_constant(vendor):
    return replace_once(
        vendor,
        "\t  pre_submit_status = read_reg(NPU_REG_STATUS);\n",
        "\t  pre_submit_status = 0U;\n\t  (void)read_reg(NPU_REG_STATUS);\n",
        "post-program STATUS load",
    )


def qsize_expected_from_the_manifest_constant(vendor):
    return replace_once(
        vendor,
        "\t  qsize_expected = read_reg(NPU_REG_QSIZE);\n",
        "\t  qsize_expected = V14_QSIZE_EXPECTED;\n\t  (void)read_reg(NPU_REG_QSIZE);\n",
        "QSIZE load",
    )


def qsize_expected_overwritten_after_its_gate(vendor):
    return replace_once(
        vendor,
        "\t  //Start NPU\n",
        "\t  qsize_expected = 0U;\n\t  //Start NPU\n",
        "submit comment",
    )


QSIZE_REREAD_HELPER = """__attribute__((noinline))
static uint32_t v14_reread_qsize(void)
{
    return read_reg(NPU_REG_QSIZE);
}

__attribute__((noinline))
static void v14_converge("""


def qsize_expected_reread_through_a_helper(vendor):
    """The running re-read hidden in a helper the command path may call."""

    text = replace_once(
        vendor,
        "__attribute__((noinline))\nstatic void v14_converge(",
        QSIZE_REREAD_HELPER,
        "convergence helper",
    )
    return replace_once(
        text,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  qsize_expected = v14_reread_qsize();\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "submit timestamp",
    )


# ---------------------------------------------------------------------------
# Absolute MMIO addresses in a translation unit that pins no register map.
#
# The tracked fixtures define no NPU_REG_* table and no U85_BASE_ADDRESS, which
# is exactly the configuration in which a numeric address can be pinned to
# nothing. Ignoring it there is what let every rule below be walked around by
# writing the number instead of the name.
# ---------------------------------------------------------------------------


def _numeric_mmio(word):
    return "*(volatile uint32_t *)(uintptr_t)0x4810%02X04U" % word


def primary_status_read_through_a_numeric_address(vendor):
    return q_loop_reads(
        vendor,
        "        qread = *qread_reg;\n        status = %s;\n"
        "        if (qread == qsize_expected) {" % _numeric_mmio(0x20),
    )


def running_qsize_read_through_a_numeric_address(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  qsize_expected = %s;\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;"
        % _numeric_mmio(0x21),
        "submit timestamp",
    )


def second_submit_through_a_numeric_address(vendor):
    return replace_once(
        vendor,
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;",
        "\t  %s = 1U;\n"
        "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;"
        % _numeric_mmio(0x22),
        "submit timestamp",
    )


def failure_path_clears_cmd_through_a_numeric_address(vendor):
    return replace_once(
        vendor,
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);",
        "\t      v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);\n"
        "\t      %s = 0U;" % _numeric_mmio(0x22),
        "primary reset failure path",
    )


def convergence_status_load_through_a_numeric_address(vendor):
    return replace_once(
        vendor,
        "        qread = *qread_reg;\n        status = *status_reg;\n" + RESET_GUARD,
        "        qread = *qread_reg;\n        status = *status_reg;\n"
        "        status = %s;\n" % _numeric_mmio(0x20) + RESET_GUARD,
        "convergence loop reads",
    )


# ---------------------------------------------------------------------------
# Mailbox lvalue provenance: the storage an lvalue names, not its spelling.
# ---------------------------------------------------------------------------

SUCCESS_PUBLICATION_HEAD = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_NONE;"
)
FAILURE_PUBLICATION_HEAD = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = phase;"
)


def _before_success_publication(statements):
    def mutate(vendor):
        return replace_once(
            vendor,
            SUCCESS_PUBLICATION_HEAD,
            statements + SUCCESS_PUBLICATION_HEAD,
            "success publication",
        )

    return mutate


magic_through_pointer_arithmetic = _before_success_publication(
    "    *(pmu_completion_visibility_v14_mailbox + 33) = V14_MAILBOX_VALID;\n"
)
magic_through_a_reversed_subscript = _before_success_publication(
    "    33[pmu_completion_visibility_v14_mailbox] = V14_MAILBOX_VALID;\n"
)
magic_through_a_reversed_addition = _before_success_publication(
    "    *(33 + pmu_completion_visibility_v14_mailbox) = V14_MAILBOX_VALID;\n"
)
magic_through_a_transitive_alias = _before_success_publication(
    "    volatile uint32_t *mb_one = pmu_completion_visibility_v14_mailbox;\n"
    "    volatile uint32_t *mb_two = (volatile uint32_t *)mb_one;\n"
    "    *(mb_two + 33) = V14_MAILBOX_VALID;\n"
)
mailbox_alias_repointed_by_compound_assignment = _before_success_publication(
    "    volatile uint32_t *mb_step = pmu_completion_visibility_v14_mailbox;\n"
    "    mb_step += 33;\n"
    "    *mb_step = V14_MAILBOX_VALID;\n"
)
mailbox_alias_repointed_by_an_increment = _before_success_publication(
    "    volatile uint32_t *mb_inc = pmu_completion_visibility_v14_mailbox;\n"
    "    ++mb_inc;\n"
    "    *mb_inc = V14_MAILBOX_VALID;\n"
)
variant_id_relabelled_through_pointer_arithmetic = _before_success_publication(
    "    *(pmu_completion_visibility_v14_mailbox + 0) = 3U;\n"
)


def failure_publication_forges_the_convergence_tuple(vendor):
    """A second store to word 17, after the one that invalidated it."""

    return replace_once(
        vendor,
        FAILURE_PUBLICATION_HEAD,
        "    *(pmu_completion_visibility_v14_mailbox + 17) = qread;\n" + FAILURE_PUBLICATION_HEAD,
        "failure publication",
    )


def primary_per_loop_store_through_pointer_arithmetic(vendor):
    return q_loop_reads(
        vendor,
        "        qread = *qread_reg;\n"
        "        *(pmu_completion_visibility_v14_mailbox + 7) = i;\n"
        "        if (qread == qsize_expected) {",
    )


def runner_copy_ahead_of_the_guard_through_pointer_arithmetic(runner):
    return replace_once(
        runner,
        "    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {",
        "    d.variant_id = *(pmu_completion_visibility_v14_mailbox + 0);\n"
        "    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {",
        "runner magic guard",
    )


PREDICATE_STRUCTURE_MUTATIONS = (
    (
        "convergence_predicate_joined_with_or",
        convergence_predicate_disjoined,
        "the convergence success predicate does not join its terms with &&",
    ),
    (
        "convergence_predicate_stopped_bit_inverted",
        convergence_predicate_bit_value_inverted,
        "the convergence success predicate is not the frozen tuple of observations",
    ),
)

LOAD_PROVENANCE_MUTATIONS = (
    (
        "pre_program_status_gated_on_a_constant",
        pre_program_status_from_a_constant,
        "pre-program gate: pre_program_status is not bound to the STATUS load this gate counted",
    ),
    (
        "post_program_status_gated_on_a_constant",
        pre_submit_status_from_a_constant,
        "post-program gate: pre_submit_status is not bound to the STATUS load this gate counted",
    ),
    (
        "qsize_expected_taken_from_the_manifest_constant",
        qsize_expected_from_the_manifest_constant,
        "qsize_expected snapshot: qsize_expected is not bound to the QSIZE load this gate counted",
    ),
    (
        "qsize_expected_overwritten_after_its_gate",
        qsize_expected_overwritten_after_its_gate,
        "qsize_expected snapshot: qsize_expected is reassigned after the QSIZE load",
    ),
    (
        "qsize_expected_reread_through_a_helper",
        qsize_expected_reread_through_a_helper,
        "qsize_expected snapshot: qsize_expected is reassigned after the QSIZE load",
    ),
)

NUMERIC_MMIO_MUTATIONS = (
    (
        "primary_status_read_through_a_numeric_address",
        primary_status_read_through_a_numeric_address,
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "running_qsize_read_through_a_numeric_address",
        running_qsize_read_through_a_numeric_address,
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "second_submit_through_a_numeric_address",
        second_submit_through_a_numeric_address,
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "failure_path_clears_cmd_through_a_numeric_address",
        failure_path_clears_cmd_through_a_numeric_address,
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "convergence_status_load_through_a_numeric_address",
        convergence_status_load_through_a_numeric_address,
        "the convergence helper reaches an NPU-region address this gate cannot resolve",
    ),
)

MAILBOX_LVALUE_MUTATIONS = (
    (
        "magic_published_through_pointer_arithmetic",
        magic_through_pointer_arithmetic,
        "mailbox_valid is published from more than one site",
    ),
    (
        "magic_published_through_a_reversed_subscript",
        magic_through_a_reversed_subscript,
        "mailbox_valid is published from more than one site",
    ),
    (
        "magic_published_through_a_reversed_addition",
        magic_through_a_reversed_addition,
        "mailbox_valid is published from more than one site",
    ),
    (
        "magic_published_through_a_transitive_mailbox_alias",
        magic_through_a_transitive_alias,
        "mailbox_valid is published from more than one site",
    ),
    (
        "mailbox_alias_repointed_by_a_compound_assignment",
        mailbox_alias_repointed_by_compound_assignment,
        "re-points mailbox storage through a compound assignment or an increment",
    ),
    (
        "mailbox_alias_repointed_by_an_increment",
        mailbox_alias_repointed_by_an_increment,
        "re-points mailbox storage through a compound assignment or an increment",
    ),
    (
        "variant_id_relabelled_through_pointer_arithmetic",
        variant_id_relabelled_through_pointer_arithmetic,
        "variant id is not published to mailbox word 0",
    ),
    (
        "failure_publication_forges_the_convergence_tuple",
        failure_publication_forges_the_convergence_tuple,
        "the failure publication publishes appendix word 17 from more than one store",
    ),
    (
        "primary_per_loop_store_through_pointer_arithmetic",
        primary_per_loop_store_through_pointer_arithmetic,
        "primary loop carries a per-iteration store/call/timestamp",
    ),
)

RUNNER_LVALUE_MUTATIONS = (
    (
        "runner_copy_ahead_of_the_guard_through_pointer_arithmetic",
        runner_copy_ahead_of_the_guard_through_pointer_arithmetic,
        "runner copies the appendix outside the mailbox-magic branch",
    ),
)


def run_predicate_and_provenance_suite(gate):
    """The connective, the load a gate consumes, and the storage an lvalue names."""

    run_vendor_mutations(gate, PREDICATE_STRUCTURE_MUTATIONS, "Q")
    run_vendor_mutations(gate, LOAD_PROVENANCE_MUTATIONS, "Q")
    run_vendor_mutations(gate, NUMERIC_MMIO_MUTATIONS, "Q")
    run_vendor_mutations(gate, MAILBOX_LVALUE_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_LVALUE_MUTATIONS, "Q")

    # The convergence tail is one shared helper, so the disjunction has to be
    # refused in every variant that reaches it -- not only in the one the rest
    # of this file mutates.
    for variant in ("QS", "SQ"):
        name = "%s_convergence_predicate_joined_with_or" % variant.lower()
        REJECTED_FIXTURES.add(name)
        expect_reject(
            gate,
            variant,
            canonical_runner(variant),
            convergence_predicate_disjoined(canonical_vendor(variant)),
            name,
            "the convergence success predicate does not join its terms with &&",
        )

    for variant in ("QS", "SQ"):
        name = "%s_primary_completion_joined_with_and" % variant.lower()
        REJECTED_FIXTURES.add(name)
        expect_reject(
            gate,
            variant,
            canonical_runner(variant),
            primary_completion_conjoined(canonical_vendor(variant)),
            name,
            "the primary completion predicate does not join its terms with ||",
        )


def q_timeout_reset_and_fault_in_one_guard(vendor):
    return replace_once(
        vendor,
        "    if ((status & V14_STATUS_RESET) != 0U) {\n"
        "        obs->result = V14_PRIMARY_RESET;\n        return;\n    }\n"
        "    if ((status & V14_STATUS_FAULT_MASK) != 0U) {\n"
        "        obs->result = V14_PRIMARY_FAULT;\n        return;\n    }",
        "    if (((status & V14_STATUS_RESET) != 0U) || ((status & V14_STATUS_FAULT_MASK) != 0U)) {\n"
        "        obs->result = V14_PRIMARY_RESET;\n"
        "        obs->iterations = V14_PRIMARY_FAULT;\n"
        "        return;\n    }",
        "Q timeout classification",
    )


ERROR_CONTRACT_MUTATIONS = (
    (
        "q_timeout_reset_and_fault_share_one_guard",
        q_timeout_reset_and_fault_in_one_guard,
        "Q timeout diagnostic does not classify reset from the diagnostic STATUS load",
    ),
)


def run_structural_matching_suite(gate):
    """Respelling the source keeps its verdict; respelling an evasion does not."""

    runner = canonical_runner("Q")
    vendor = canonical_vendor("Q")
    for name, mutate in WHITESPACE_RESPELLINGS:
        expect_accept(gate, "Q", runner, mutate(vendor), "%s is still accepted" % name)
    run_vendor_mutations(gate, WHITESPACE_EVASION_MUTATIONS, "Q")


def run_mmio_provenance_suite(gate):
    """Every spelling of an NPU address resolves to the register it names."""

    runner = canonical_runner("Q")
    vendor = canonical_vendor("Q")
    for name, mutate in MMIO_RESPELLINGS:
        expect_accept(gate, "Q", runner, mutate(vendor), "%s is still accepted" % name)
    run_vendor_mutations(gate, MMIO_PROVENANCE_MUTATIONS, "Q")
    run_vendor_mutations(gate, ERROR_CONTRACT_MUTATIONS, "Q")

    run_vendor_mutations(
        gate,
        (
            (
                "qs_primary_status_reload_through_an_alias",
                qs_primary_status_reload_through_alias,
                "primary loop reloads STATUS",
            ),
        ),
        "QS",
    )

    for variant in ("QS", "SQ"):
        name = "%s_read_order_inverted_through_aliases" % variant.lower()
        REJECTED_FIXTURES.add(name)
        expect_reject(
            gate,
            variant,
            canonical_runner(variant),
            _dual_order_inverted(variant)(canonical_vendor(variant)),
            name,
            "%s primary read order is not" % variant,
        )


# ---------------------------------------------------------------------------
# Manifest evidence: a published boolean or count is what the verifier saw.
# ---------------------------------------------------------------------------

DERIVED_MANIFEST_FIELDS = (
    "running_qsize_loads_in_test_commands",
    "failure_paths_clear_npu",
    "failure_paths_enter_hprintf",
    "reachable_nvic_enable_sites",
    "success_cleanup_order",
    # Each of these was a literal in the gate. A connective the gate spells out
    # is a connective it did not read, and a category list it hardcodes is a
    # claim rather than an observation.
    "first_observation_categories",
    "convergence_predicate_connective",
    "primary_completion_predicate_connective",
    "runner_copy_dominated_by_magic",
    # The mailbox word each runner copy was resolved to. A count of 34 is not a
    # mapping, so the mapping itself is what the manifest publishes.
    "runner_appendix_source_words",
)

# Each field paired with the fixture whose true value contradicts the canonical
# claim. A rejection is the proof: the manifest is never written, so the false
# claim cannot be published.
DERIVED_FIELD_WITNESSES = (
    ("running_qsize_loads_in_test_commands", running_qsize_through_raw_pointer),
    ("failure_paths_clear_npu", failure_path_clears_cmd_through_raw_pointer),
    ("failure_paths_enter_hprintf", failure_path_prints_through_the_seam),
    ("reachable_nvic_enable_sites", nvic_enable_with_a_space),
    ("success_cleanup_order", extra_cleanup_cmd2_as_a_bare_two),
)


def run_manifest_evidence_suite(gate):
    doc = expect_accept(
        gate,
        "Q",
        canonical_runner("Q"),
        canonical_vendor("Q"),
        "the canonical Q manifest carries every derived field",
    )
    if doc is not None:
        check(
            "derived manifest fields report what the verifier observed",
            doc["running_qsize_loads_in_test_commands"] == 0
            and doc["failure_paths_clear_npu"] is False
            and doc["failure_paths_enter_hprintf"] is False
            and doc["reachable_nvic_enable_sites"] == 0
            and doc["success_cleanup_order"] == list(gate.SUCCESS_CLEANUP_ORDER)
            and doc["runner_appendix_source_words"] == list(range(APPENDIX_WORDS)),
            repr({field: doc.get(field) for field in DERIVED_MANIFEST_FIELDS})[:70],
        )
        check(
            "the manifest reports the connectives the verifier parsed",
            doc["convergence_predicate_connective"] == "&&"
            and doc["primary_completion_predicate_connective"] == ""
            and doc["convergence_predicate_bindings"]
            == [
                ["q_done", "=="],
                ["cmd_end_reached", "!=", 0],
                ["irq_raised", "!=", 0],
                ["state", "==", 0],
            ]
            and doc["primary_completion_predicate_terms"] == [["q_done", "=="]],
            repr(doc.get("convergence_predicate_bindings"))[:70],
        )

    with open(CHECKER_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    hardcoded = sorted(
        field
        for field in DERIVED_MANIFEST_FIELDS
        if re.search(r'"%s":\s*(?:False|True|\d|\[\s*\])' % re.escape(field), source)
    )
    check(
        "no derived manifest field is a literal in the gate",
        not hardcoded,
        repr(hardcoded),
    )

    for field, mutate in DERIVED_FIELD_WITNESSES:
        name = "false_%s_claim" % field
        REJECTED_FIXTURES.add(name)
        try:
            gate.verify_generated_sources(
                canonical_runner("Q"), mutate(canonical_vendor("Q")), "Q"
            )
        except gate.GateError:
            check("a false %s claim is refused, not published" % field, True)
        except Exception as exc:  # pragma: no cover - a crash is not a rejection
            check("a false %s claim is refused, not published" % field, False, "raised %r" % exc)
        else:
            check("a false %s claim is refused, not published" % field, False, "accepted")


# ---------------------------------------------------------------------------
# Post-store mutation, transport binding, failure-path window, address folding,
# pointer re-pointing, line splicing, publishing guards, directive lines and
# storage aliasing.
#
# Each fixture below was accepted by the gate before the rule that names it
# existed, so each one is a proof that the rule is load-bearing rather than a
# restatement of what the canonical source happens to do.
# ---------------------------------------------------------------------------

VARIANT_ID_STORE = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;\n"
)
MAGIC_PUBLICATION = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;\n"
    "    __DSB();\n"
)
CONVERGENCE_QREAD_STORE = (
    "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] = converged.qread;\n"
)
PRIMARY_RESULT_PUBLICATION = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_RESULT] = obs->result;\n"
)
PRIMARY_TIMEOUT_PUBLICATION = (
    "\t    v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_PRIMARY_TIMEOUT,"
    " primary.qread, primary.status);\n"
)
SUBMIT_WRITE = "\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);\n"
STOP_NPU_WRITE = "\t  write_reg(NPU_REG_CMD, 0x00000000);\n"
CLEANUP_NVIC_CLEAR = "\t  NVIC_ClearPendingIRQ(NPU0_IRQn);\n"
PRE_SUBMIT_STATUS_READ = "\t  pre_submit_status = read_reg(NPU_REG_STATUS);\n"
PRE_PROGRAM_STATUS_READ = "    pre_program_status = read_reg(NPU_REG_STATUS);\n"
Q_LOOP_READ_AND_GUARD = (
    "        qread = *qread_reg;\n        if (qread == qsize_expected) {\n"
)
Q_LOOP_PROLOGUE = (
    "    uint32_t qread = 0U;\n    uint32_t status = 0U;\n\n"
    "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {\n"
    "        qread = *qread_reg;\n"
)
RUNNER_MAGIC_GUARD_LINE = (
    "    if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {\n"
)


def _append_after(anchor, statement, what):
    def mutate(text):
        return replace_once(text, anchor, anchor + statement, what)

    return mutate


def _prepend_before(anchor, statement, what):
    def mutate(text):
        return replace_once(text, anchor, statement + anchor, what)

    return mutate


def _inject_into_q_loop(statement):
    def mutate(vendor):
        return replace_once(
            vendor,
            Q_LOOP_READ_AND_GUARD,
            "        qread = *qread_reg;\n"
            + statement
            + "        if (qread == qsize_expected) {\n",
            "Q primary loop read",
        )

    return mutate


def _q_pointer_stepped(step):
    def mutate(vendor):
        return replace_once(
            vendor,
            Q_LOOP_PROLOGUE,
            "    uint32_t qread = 0U;\n    uint32_t status = 0U;\n"
            "    volatile uint32_t *stepped_reg = qread_reg;\n"
            "%s\n"
            "    for (uint32_t i = 1U; i <= V14_ITERATION_BOUND; ++i) {\n"
            "        qread = *stepped_reg;\n" % step,
            "Q primary loop prologue",
        )

    return mutate


def _spliced_comment_around(anchor, what):
    """Delete ``anchor`` from the built image with a ``/\\<newline>*`` opener."""

    def mutate(vendor):
        return replace_once(
            vendor, anchor, "\t  /\\\n*\n" + anchor + "\t  */\n", what
        )

    return mutate


def deeply_nested_primary_guards(vendor):
    depth = 1500
    return replace_once(
        vendor,
        Q_LOOP_READ_AND_GUARD,
        "        qread = *qread_reg;\n"
        + "        if (i != 0U) {\n" * depth
        + "        }\n" * depth
        + "        if (qread == qsize_expected) {\n",
        "Q primary loop read",
    )


PUBLISHING_COMPLETION_GUARD = """        if ((qread == qsize_expected) || ((status & V14_STATUS_CMD_END) != 0U)) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V14_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = qread;
            obs->status = status;
            return;
        }
"""
FABRICATED_OBSERVED_GUARD = """        if (i > 5U) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V14_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = qread;
            obs->status = status;
            return;
        }
"""
DUAL_RESET_GUARD_OPENING = (
    "        if ((status & V14_STATUS_RESET) != 0U) {\n"
    "            obs->t_first = V14_U32_INVALID;\n"
    "            obs->result = V14_PRIMARY_RESET;\n"
)


def dual_reset_guard_publishes_observed(vendor):
    return replace_once(
        vendor,
        DUAL_RESET_GUARD_OPENING,
        "        if (((status & V14_STATUS_RESET) != 0U) || (i > 5U)) {\n"
        "            obs->t_first = DWT->CYCCNT;\n"
        "            obs->result = V14_PRIMARY_OBSERVED;\n",
        "dual reset guard",
    )


MMIO_FOLDING_MUTATIONS = (
    (
        "primary_status_read_through_an_or_folded_address",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000014U | 0U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_status_read_through_an_and_masked_address",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000014U & 0xFFFFFFFFU);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_status_read_through_a_modulo_address",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000014U % 0x100000000U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_qsize_read_through_an_xor_address",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000010U ^ 0U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "second_submit_through_an_or_folded_address",
        _append_after(
            SUBMIT_WRITE,
            "\t  *(volatile uint32_t *)(uintptr_t)(0x48000000U | 0U) = 1U;\n",
            "submit write",
        ),
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "numeric_npu_address_this_gate_cannot_fold",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000014U / 0U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "npu_address_written_as_a_complement",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(~0xB7FFFFEBU);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "npu_address_selected_by_a_ternary",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)((1U > 0U) ? 0x48000014U : 0U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "npu_address_written_as_a_comparison",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x48000014U == 0U);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "macro_wrapped_mmio_in_the_command_path",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                "\t  irq_history_mask = converged.status >> 16;\n",
                "\t  irq_history_mask = converged.status >> 16;\n"
                "\t  read_val = (int)V14_REG32(0x48000014U);\n",
                "irq history assignment",
            ),
            "#define V14_APPENDIX_WORDS 34U",
            "#define V14_APPENDIX_WORDS 34U\n#define V14_REG32(a) (*(volatile uint32_t *)(a))",
            "appendix words define",
        ),
        "the macro V14_REG32 expands to an unexpanded MMIO dereference",
    ),
)

MMIO_POINTER_STEP_MUTATIONS = (
    (
        "mmio_pointer_repointed_by_a_compound_assignment",
        _q_pointer_stepped("    stepped_reg += 4;"),
        "primary helper binds an NPU-region pointer this gate cannot resolve to one register",
    ),
    (
        "mmio_pointer_repointed_by_an_increment",
        _q_pointer_stepped("    ++stepped_reg;"),
        "primary helper binds an NPU-region pointer this gate cannot resolve to one register",
    ),
)

POST_STORE_MUTATION_MUTATIONS = (
    (
        "mailbox_word_incremented_after_its_store",
        _append_after(
            VARIANT_ID_STORE,
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] += 2U;\n",
            "variant id store",
        ),
        "mutates a published mailbox word through a read-modify-write",
    ),
    (
        "mailbox_magic_cleared_after_publication",
        _append_after(
            MAGIC_PUBLICATION,
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] &= 0U;\n",
            "magic publication",
        ),
        "mutates a published mailbox word through a read-modify-write",
    ),
    (
        "mailbox_data_word_or_masked_after_its_store",
        _append_after(
            CONVERGENCE_QREAD_STORE,
            "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD] |="
            " 0xFFFF0000U;\n",
            "convergence final qread store",
        ),
        "mutates a published mailbox word through a read-modify-write",
    ),
    (
        "mailbox_word_incremented_through_an_alias",
        lambda vendor: replace_once(
            vendor,
            VARIANT_ID_STORE,
            "    volatile uint32_t *mailbox_alias = pmu_completion_visibility_v14_mailbox;\n"
            + VARIANT_ID_STORE
            + "    mailbox_alias[0]++;\n",
            "variant id store",
        ),
        "mutates a published mailbox word through a read-modify-write",
    ),
    (
        "mailbox_word_mutated_through_a_reversed_subscript",
        _append_after(
            VARIANT_ID_STORE,
            "    0[pmu_completion_visibility_v14_mailbox] += 2U;\n",
            "variant id store",
        ),
        "mutates a published mailbox word through a read-modify-write",
    ),
    (
        "observation_field_or_masked_before_publication",
        _prepend_before(
            PRIMARY_RESULT_PUBLICATION, "    obs->result |= 1U;\n", "primary result publication"
        ),
        "mutates a frozen observation field through a read-modify-write",
    ),
)

FAILURE_WINDOW_MUTATIONS = (
    (
        "failure_path_clears_cmd_immediately_before_publication",
        _prepend_before(
            PRIMARY_TIMEOUT_PUBLICATION,
            "\t    write_reg(NPU_REG_CMD, 0x00000000);\n",
            "primary timeout publication",
        ),
        "failure path clears NPU state before serialization",
    ),
    (
        "failure_path_prints_immediately_before_publication",
        _prepend_before(
            PRIMARY_TIMEOUT_PUBLICATION,
            '\t    printf("primary timeout\\n");\n',
            "primary timeout publication",
        ),
        "failure path enters the H-PRINTF seam",
    ),
)

LINE_SPLICING_MUTATIONS = (
    (
        "terminal_cmd_write_deleted_by_a_spliced_comment",
        _spliced_comment_around(STOP_NPU_WRITE, "stop NPU write"),
        "success cleanup ordering drifted",
    ),
    (
        "cleanup_nvic_clear_deleted_by_a_spliced_comment",
        _spliced_comment_around(CLEANUP_NVIC_CLEAR, "cleanup NVIC clear"),
        "success cleanup ordering drifted",
    ),
)

STORAGE_ALIAS_MUTATIONS = (
    (
        "pre_submit_status_overwritten_through_a_dereferenced_lvalue",
        _append_after(
            PRE_SUBMIT_STATUS_READ,
            "\t  *(&pre_submit_status) = 0U;\n",
            "pre-submit status read",
        ),
        "post-program gate: pre_submit_status is written through an lvalue this gate cannot bind",
    ),
    (
        "pre_program_status_overwritten_through_a_dereferenced_lvalue",
        _append_after(
            PRE_PROGRAM_STATUS_READ,
            "    *(&pre_program_status) = 0U;\n",
            "pre-program status read",
        ),
        "pre-program gate: pre_program_status is written through an lvalue this gate cannot bind",
    ),
)

NVIC_ISOLATION_MUTATIONS = (
    (
        "raw_nvic_iser_enable_write",
        _append_after(
            "    NVIC_ClearPendingIRQ(NPU0_IRQn);\n\n",
            "    ((NVIC_Type *)0xE000E100UL)->ISER[0] = 1UL;\n",
            "runtime setup NVIC clear",
        ),
        "direct NVIC ISER enable write is reachable",
    ),
    (
        "irq_triggered_set_to_one_on_a_measured_path",
        _append_after(SUBMIT_WRITE, "\t  irq_triggered = 1;\n", "submit write"),
        "irq_triggered can become true on a measured path",
    ),
)

BOUNDED_ANALYSIS_MUTATIONS = (
    (
        "guard_nesting_deeper_than_the_gate_walks",
        deeply_nested_primary_guards,
        "nesting is deeper than the 128 levels this gate walks",
    ),
)

PUBLISHING_GUARD_MUTATIONS = (
    (
        "extra_publishing_guard_after_the_completion_guard",
        _append_after(
            PUBLISHING_COMPLETION_GUARD, FABRICATED_OBSERVED_GUARD, "dual completion guard"
        ),
        "publishes from a guard whose condition is not a contract predicate",
    ),
    (
        "extra_publishing_guard_before_the_completion_guard",
        _prepend_before(
            PUBLISHING_COMPLETION_GUARD, FABRICATED_OBSERVED_GUARD, "dual completion guard"
        ),
        "publishes from a guard whose condition is not a contract predicate",
    ),
    (
        "extra_publishing_guard_spelled_else_if",
        _append_after(
            PUBLISHING_COMPLETION_GUARD,
            "        else " + FABRICATED_OBSERVED_GUARD.lstrip(" "),
            "dual completion guard",
        ),
        "publishes from a guard whose condition is not a contract predicate",
    ),
    (
        "reset_guard_repurposed_to_publish_observed",
        dual_reset_guard_publishes_observed,
        "the primary reset predicate does not join its terms with a single term",
    ),
)


def _runner_copies_from_one_word(runner):
    out = runner
    for index, field in enumerate(APPENDIX_FIELDS):
        out = replace_once(
            out,
            "            d.%s = pmu_completion_visibility_v14_mailbox[%d];" % (field, index),
            "            d.%s = pmu_completion_visibility_v14_mailbox[0];" % field,
            "runner copy of %s" % field,
        )
    return out


def _runner_copies_in_reverse_word_order(runner):
    out = runner
    for index, field in enumerate(APPENDIX_FIELDS):
        out = replace_once(
            out,
            "            d.%s = pmu_completion_visibility_v14_mailbox[%d];" % (field, index),
            "            d.%s = pmu_completion_visibility_v14_mailbox[@%d@];" % (field, index),
            "runner copy of %s" % field,
        )
    for index in range(len(APPENDIX_FIELDS)):
        out = out.replace("@%d@" % index, str(len(APPENDIX_FIELDS) - 1 - index))
    return out


def _runner_copy_index(new_index):
    def mutate(runner):
        return replace_once(
            runner,
            "            d.qsize_expected = pmu_completion_visibility_v14_mailbox[1];",
            "            d.qsize_expected = pmu_completion_visibility_v14_mailbox[%s];" % new_index,
            "runner qsize_expected copy",
        )

    return mutate


RUNNER_TRANSPORT_MUTATIONS = (
    (
        "runner_copies_every_appendix_field_from_word_zero",
        _runner_copies_from_one_word,
        "runner appendix copy does not read the word its field is published in",
    ),
    (
        "runner_copies_the_appendix_in_reverse_word_order",
        _runner_copies_in_reverse_word_order,
        "runner appendix copy does not read the word its field is published in",
    ),
    (
        "runner_copies_a_field_from_an_out_of_range_word",
        _runner_copy_index("99"),
        "runner copies qsize_expected from outside the 34-word appendix",
    ),
    (
        "runner_copies_a_field_from_an_unresolvable_word",
        _runner_copy_index("rt_index"),
        "runner copies qsize_expected from a mailbox offset this gate cannot resolve",
    ),
    (
        "runner_copy_hidden_behind_a_preprocessor_directive",
        _prepend_before(
            RUNNER_MAGIC_GUARD_LINE,
            "#line 1\n    d.variant_id = pmu_completion_visibility_v14_mailbox[0];\n",
            "runner magic guard",
        ),
        "runner copies the appendix outside the mailbox-magic branch",
    ),
)


# ---------------------------------------------------------------------------
# Final-gate blockers: every one of these was ACCEPT at d07f0d6, reproduced
# against that exact tree before the fix, and is kept here so it stays closed.
# ---------------------------------------------------------------------------

# C 6.5.2.1 defines ``E1[E2]`` as ``(*((E1)+(E2)))``, so a subscript is a
# dereference and the subscript is commutative. Enumerating only the ``*``
# spelling left each of these invisible to every MMIO rule at once.
SUBSCRIPT_MMIO_MUTATIONS = (
    (
        "q_primary_status_read_through_a_subscript",
        _inject_into_q_loop("        status = status_reg[0];\n"),
        "Q primary loop reads STATUS",
    ),
    (
        "q_primary_status_read_through_a_reversed_subscript",
        _inject_into_q_loop("        status = 0[status_reg];\n"),
        "Q primary loop reads STATUS",
    ),
    (
        "q_primary_status_read_through_a_parenthesised_subscript_base",
        _inject_into_q_loop("        status = (status_reg)[0];\n"),
        "Q primary loop reads STATUS",
    ),
    (
        # A discarded load binds no name, so nothing but the access enumerator
        # can see it -- which is what makes it the sharpest test of the fix.
        "q_primary_status_read_through_a_discarded_subscript",
        _inject_into_q_loop("        (void)status_reg[0];\n"),
        "Q primary loop reads STATUS",
    ),
    (
        "primary_status_read_through_a_discarded_numeric_subscript_base",
        _inject_into_q_loop(
            "        (void)((volatile uint32_t *)(uintptr_t)0x48000014U)[0];\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "second_submit_through_a_subscript",
        _append_after(
            SUBMIT_WRITE,
            "\t  ((volatile uint32_t *)(uintptr_t)0x48000000U)[0] = 1U;\n",
            "submit write",
        ),
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "running_qsize_read_through_a_discarded_reversed_subscript",
        _append_after(
            SUBMIT_WRITE,
            "\t  (void)0[(volatile uint32_t *)(uintptr_t)0x48000010U];\n",
            "submit write",
        ),
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
)

# A pointer cast says "this is an address". An identifier the evaluator cannot
# fold is then evidence that nothing here can say *which* address -- not
# evidence that it is not one. ``0x50004004U & V14_U32_INVALID`` needs no new
# macro: the sentinel is already 0xFFFFFFFF in every generated vendor.
UNFOLDABLE_ADDRESS_MUTATIONS = (
    (
        "primary_status_read_through_an_and_masked_sentinel_address",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)"
            "(0x50004004U & V14_U32_INVALID);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "second_submit_through_an_and_masked_sentinel_address",
        _append_after(
            SUBMIT_WRITE,
            "\t  *(volatile uint32_t *)(uintptr_t)(0x50004008U & V14_U32_INVALID) = 1U;\n",
            "submit write",
        ),
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "running_qsize_read_through_an_and_masked_sentinel_address",
        _append_after(
            SUBMIT_WRITE,
            "\t  (void)*(volatile uint32_t *)(uintptr_t)(0x50004014U & V14_U32_INVALID);\n",
            "submit write",
        ),
        "the command function reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_status_read_through_an_undefined_mask_identifier",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x50004004U & addr_mask_g);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_status_read_through_an_unfoldable_additive_identifier",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x50004004U + zero_off_g);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        "primary_status_read_through_an_unfoldable_struct_member_mask",
        _inject_into_q_loop(
            "        status = *(volatile uint32_t *)(uintptr_t)(0x50004004U & cfg_g.mask);\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
    (
        # Both halves of B1 in one spelling: the subscript hides the access from
        # the enumerator and the AND-masked identifier hides the address from
        # the resolver.
        "and_masked_address_reached_through_a_subscript",
        _inject_into_q_loop(
            "        (void)((volatile uint32_t *)(uintptr_t)"
            "(0x50004004U & V14_U32_INVALID))[0];\n"
        ),
        "the primary helper reaches an NPU-region address this gate cannot resolve",
    ),
)

# C truncates a quotient toward zero (6.5.5p6); Python floors. ``(0-3)/2`` is -1
# to a compiler and -2 to a floor-dividing evaluator, and 0xFFFFFFFF has bit 0
# set where -2 does not -- so the gate reads "not a submit" where the built image
# starts the NPU a second time.
C_ARITHMETIC_FOLDING_MUTATIONS = (
    (
        "hidden_cmd_start_through_a_truncating_division",
        _append_after(SUBMIT_WRITE, "\t  write_reg(NPU_REG_CMD, (0-3)/2);\n", "submit write"),
        "command path does not carry exactly one NPU submit write",
    ),
    (
        "hidden_cmd_start_through_a_truncating_modulo",
        _append_after(SUBMIT_WRITE, "\t  write_reg(NPU_REG_CMD, (0-4)%3);\n", "submit write"),
        "command path does not carry exactly one NPU submit write",
    ),
)

# ``#undef`` plus a redefinition is warning-free, conforming C11 (6.10.3.5) and
# leaves the frozen spelling of the store untouched, so the image publishes into
# a different appendix word than the one the gate reads.
PREPROCESSING_HISTORY_MUTATIONS = (
    (
        "appendix_word_repointed_by_undef_and_redefine",
        lambda vendor: replace_once(
            vendor,
            VARIANT_ID_STORE,
            "#undef V14_MBOX_VARIANT_ID\n#define V14_MBOX_VARIANT_ID 7U\n"
            + VARIANT_ID_STORE
            + "#undef V14_MBOX_VARIANT_ID\n#define V14_MBOX_VARIANT_ID 0U\n",
            "variant id store",
        ),
        "undefines a contract macro",
    ),
    (
        "register_offset_macro_undefined_mid_source",
        _prepend_before(
            SUBMIT_WRITE, "#undef NPU_REG_CMD\n#define NPU_REG_CMD 0x10\n", "submit write"
        ),
        "undefines a contract macro",
    ),
    (
        # Not a fresh bypass -- d07f0d6 already refused this one, because
        # ``parse_defines`` keeps the last value and the appendix offset table
        # then fails to match. It is kept as the negative control for the pair
        # above: only ``#undef`` plus a *restoring* redefinition evaded that,
        # and this pins the plain-redefinition half to a named rule of its own.
        "contract_macro_redefined_with_a_second_value",
        _prepend_before(
            VARIANT_ID_STORE, "#define V14_MBOX_VARIANT_ID 7U\n", "variant id store"
        ),
        "defines the contract macro V14_MBOX_VARIANT_ID with more than one value",
    ),
)

RUNNER_PREPROCESSING_MUTATIONS = (
    (
        "runner_contract_macro_undefined_before_the_guard",
        _prepend_before(
            RUNNER_MAGIC_GUARD_LINE,
            "#undef V14_MAILBOX_VALID\n#define V14_MAILBOX_VALID 0x5631344D\n",
            "runner magic guard",
        ),
        "undefines a contract macro",
    ),
)

# The record is ordinary memory between the proven copy and ``put32``. Proving
# where the 34 words came *from* does not bound what is serialized.
RUNNER_RECORD_CLOSURE_ANCHOR = "    }\n    *out = d;\n"


def _after_the_appendix_copy(statement):
    return _prepend_before(
        RUNNER_RECORD_CLOSURE_ANCHOR,
        "    }\n" + statement,
        "runner appendix copy tail",
    )


RUNNER_RECORD_CLOSURE_MUTATIONS = (
    (
        "runner_record_field_overwritten_after_the_copy",
        _after_the_appendix_copy("    d.variant_id = 3U;\n"),
        "runner rewrites a copied appendix field outside the mailbox-magic branch",
    ),
    (
        "runner_record_field_read_modify_written_after_the_copy",
        _after_the_appendix_copy("    d.first_qread |= 0x80000000U;\n"),
        "runner rewrites a copied appendix field through a read-modify-write",
    ),
    (
        "runner_record_field_incremented_after_the_copy",
        _after_the_appendix_copy("    ++d.primary_iterations;\n"),
        "runner rewrites a copied appendix field through a read-modify-write",
    ),
    (
        "runner_record_fields_swapped_after_the_copy",
        _after_the_appendix_copy(
            "    { uint32_t swap_tmp = d.first_qread;\n"
            "      d.first_qread = d.first_status;\n"
            "      d.first_status = swap_tmp; }\n"
        ),
        "runner rewrites a copied appendix field outside the mailbox-magic branch",
    ),
    (
        "runner_record_field_zeroed_before_serialization",
        _after_the_appendix_copy("    d.mailbox_valid = 0U;\n"),
        "runner rewrites a copied appendix field outside the mailbox-magic branch",
    ),
)

# The literal scan only ever refused the ISER address written as one number.
# A helper called from ``test_commands`` is outside all four functions that get
# dereference resolution, which is where the computed address went.
NVIC_COMPUTED_ADDRESS_MUTATIONS = (
    (
        "computed_nvic_iser_enable_in_an_uninspected_helper",
        lambda vendor: replace_once(
            replace_once(
                replace_once(
                    vendor,
                    "#define V14_U32_INVALID",
                    "#define V14_NVIC_LO 0xE000E000U\n#define V14_U32_INVALID",
                    "invalid sentinel define",
                ),
                "int test_commands(",
                "static void v14_extra_setup(void)\n{\n"
                "    *(volatile uint32_t *)(uintptr_t)(V14_NVIC_LO + 0x100U) = (1UL << 20);\n"
                "}\n\nint test_commands(",
                "command function head",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  v14_extra_setup();\n",
            "submit write",
        ),
        "direct NVIC ISER enable write is reachable",
    ),
    (
        "computed_nvic_iser_enable_through_a_subscript",
        lambda vendor: replace_once(
            replace_once(
                replace_once(
                    vendor,
                    "#define V14_U32_INVALID",
                    "#define V14_NVIC_LO 0xE000E000U\n#define V14_U32_INVALID",
                    "invalid sentinel define",
                ),
                "int test_commands(",
                "static void v14_extra_enable(void)\n{\n"
                "    ((volatile uint32_t *)(uintptr_t)(V14_NVIC_LO + 0x100U))[0] = 1UL;\n"
                "}\n\nint test_commands(",
                "command function head",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  v14_extra_enable();\n",
            "submit write",
        ),
        "direct NVIC ISER enable write is reachable",
    ),
)

# ``*trig_alias = true`` never spells the flag on the left of an ``=``, so the
# publication-site walk kept reporting the handler as its only writer.
IRQ_TRIGGERED_ALIAS_MUTATIONS = (
    (
        "irq_triggered_set_true_through_an_alias",
        _append_after(
            SUBMIT_WRITE,
            "\t  { volatile bool *trig_alias = &irq_triggered; *trig_alias = true; }\n",
            "submit write",
        ),
        "irq_triggered can become true on a measured path",
    ),
    (
        "irq_triggered_address_taken_through_a_parenthesised_alias",
        _append_after(
            SUBMIT_WRITE,
            "\t  { volatile bool *trig_alias = &(irq_triggered); trig_alias[0] = true; }\n",
            "submit write",
        ),
        "irq_triggered can become true on a measured path",
    ),
    (
        "irq_triggered_address_passed_to_a_call",
        _append_after(
            SUBMIT_WRITE, "\t  v14_touch_flag(&irq_triggered);\n", "submit write"
        ),
        "irq_triggered can become true on a measured path",
    ),
)


def _appendix_store_line(vendor, macro_word):
    head = "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_%s] = " % macro_word
    for candidate in vendor.split("\n"):
        if candidate.startswith(head):
            return candidate
    raise AssertionError("no success-path store found for %s" % macro_word)


def _appendix_store_deleted(macro_word):
    """Delete the one success-path store of an appendix word outright."""

    def mutate(vendor):
        line = _appendix_store_line(vendor, macro_word)
        return vendor.replace(line + "\n", "", 1)

    return mutate


def _comment_out_appendix_store(vendor, macro_word):
    line = _appendix_store_line(vendor, macro_word)
    return vendor.replace(line + "\n", "\t  /* %s */\n" % line.strip(), 1)


def _splice_out_appendix_store(vendor, macro_word):
    """Delete the store with a ``/\\<newline>*`` opener the compiler honours."""

    line = _appendix_store_line(vendor, macro_word)
    return vendor.replace(line + "\n", "\t  /\\\n*\n" + line + "\n\t  */\n", 1)


# A word no store ever reaches carries the reset sentinel into the frame. Every
# other rule is written over the stores that *do* exist, so an outright deletion
# left the gate with nothing to object to -- fail-silent, but still a manifest
# that asserts an observation the image never made.
APPENDIX_PRODUCER_MUTATIONS = (
    (
        "appendix_word_with_no_success_path_store",
        _appendix_store_deleted("NVIC_PENDING_AFTER_FINAL_CLEAR"),
        "appendix word 30 (nvic_pending_after_final_clear) has no store outside the mailbox reset",
    ),
    (
        "appendix_word_producer_commented_out",
        lambda vendor: _comment_out_appendix_store(vendor, "NVIC_ACTIVE_AFTER_CLEANUP"),
        "appendix word 31 (nvic_active_after_cleanup) has no store outside the mailbox reset",
    ),
    (
        "appendix_word_producer_deleted_by_a_spliced_comment",
        lambda vendor: _splice_out_appendix_store(vendor, "IRQ_TRIGGERED_AFTER_CLEANUP"),
        "appendix word 32 (irq_triggered_after_cleanup) has no store outside the mailbox reset",
    ),
)


def run_final_blocker_suite(gate):
    """The d07f0d6 acceptance blockers, each reproduced before it was closed."""

    run_vendor_mutations(gate, SUBSCRIPT_MMIO_MUTATIONS, "Q")
    run_vendor_mutations(gate, UNFOLDABLE_ADDRESS_MUTATIONS, "Q")
    run_vendor_mutations(gate, C_ARITHMETIC_FOLDING_MUTATIONS, "Q")
    run_vendor_mutations(gate, PREPROCESSING_HISTORY_MUTATIONS, "Q")
    run_vendor_mutations(gate, NVIC_COMPUTED_ADDRESS_MUTATIONS, "Q")
    run_vendor_mutations(gate, IRQ_TRIGGERED_ALIAS_MUTATIONS, "Q")
    run_vendor_mutations(gate, APPENDIX_PRODUCER_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_RECORD_CLOSURE_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_PREPROCESSING_MUTATIONS, "Q")

    # The subscript rule has to see the *variant matrix* too, not only the Q
    # loop it was reported against.
    for variant in ("QS", "SQ"):
        name = "%s_running_qsize_read_through_a_subscript" % variant.lower()
        REJECTED_FIXTURES.add(name)
        expect_reject(
            gate,
            variant,
            canonical_runner(variant),
            _append_after(
                SUBMIT_WRITE,
                "\t  (void)((volatile uint32_t *)(uintptr_t)0x48000010U)[0];\n",
                "submit write",
            )(canonical_vendor(variant)),
            name,
            "the command function reaches an NPU-region address this gate cannot resolve",
        )

    _check_c_integer_folding(gate)
    _check_address_of_is_not_bitwise_and(gate)
    _check_alias_resolution_is_bounded(gate)


def _check_c_integer_folding(gate):
    """The evaluator answers what a C compiler answers, sign included."""

    cases = (
        ("(0-3)/2", -1),
        ("(0-3)%2", -1),
        ("(0-4)%3", -1),
        ("(0-4)/3", -1),
        ("3/(0-2)", -1),
        ("3%(0-2)", 1),
        ("(0-7)/2", -3),
        ("(0-7)%2", -1),
        ("7/2", 3),
        ("7%2", 1),
    )
    wrong = [
        (expr, gate._evaluate_constant(expr, {}), expected)
        for expr, expected in cases
        if gate._evaluate_constant(expr, {}) != expected
    ]
    check(
        "integer division and modulo truncate toward zero as C does",
        not wrong,
        repr(wrong)[:80],
    )
    # The identity C guarantees: ``(a/b)*b + a%b == a`` for every folded pair.
    broken = []
    for left in (-7, -4, -3, 3, 4, 7):
        for right in (-3, -2, 2, 3):
            expr = "(0%+d)/(0%+d)" % (left, right)
            rest = "(0%+d)%%(0%+d)" % (left, right)
            quotient = gate._evaluate_constant(expr, {})
            remainder = gate._evaluate_constant(rest, {})
            if quotient * right + remainder != left:
                broken.append((left, right, quotient, remainder))
    check("the folded quotient and remainder satisfy C's identity", not broken, repr(broken)[:80])


def _check_address_of_is_not_bitwise_and(gate):
    """``&`` as an operator survives flattening; ``&`` as address-of does not.

    The negative controls matter as much as the rejections above: a rule that
    refused *every* AND-masked address would be indistinguishable from one that
    still could not read them.
    """

    defines = {
        "U85_BASE_ADDRESS": 0x48000000,
        "NPU_REG_STATUS": 0x14,
        "NPU_REG_CMD": 0x00,
        "V14_ADDR_MASK": 0xFFFFFFFF,
    }
    folded = gate.resolve_address_role(
        "(volatile uint32_t *)(uintptr_t)(0x48000014U & V14_ADDR_MASK)", defines, {}
    )
    check(
        "an AND-masked address folds to the register it names",
        folded == "STATUS",
        repr(folded),
    )
    check(
        "address-of is still stripped from a flattened address",
        gate._flatten_address("&mailbox[3]").strip().startswith("mailbox"),
        repr(gate._flatten_address("&mailbox[3]")),
    )
    check(
        "a bitwise AND survives flattening",
        "&" in gate._flatten_address("(0x48000014U & V14_ADDR_MASK)"),
        repr(gate._flatten_address("(0x48000014U & V14_ADDR_MASK)")),
    )
    unfoldable = gate.resolve_address_role(
        "(volatile uint32_t *)(uintptr_t)(0x48000014U & runtime_mask)", defines, {}
    )
    check(
        "an address this gate cannot fold is UNRESOLVED, never ignored",
        unfoldable == gate.UNRESOLVED_ROLE,
        repr(unfoldable),
    )


def _check_alias_resolution_is_bounded(gate):
    """A several-thousand-link copy chain settles in work linear in its length.

    The assertion is a *call count*, not a wall clock: the defect was the shape
    of the walk, and a deterministic budget says so without depending on how
    fast the machine running the suite happens to be. A quadratic walk over
    4000 links costs about eight million resolutions; the bound below is 40
    thousand. A wall-clock check follows only as a coarse backstop.
    """

    defines = {"U85_BASE_ADDRESS": 0x48000000, "NPU_REG_QREAD": 0x10}

    def chain_body(links):
        head = "    volatile uint32_t *p0 = (volatile uint32_t *)(U85_BASE_ADDRESS + NPU_REG_QREAD);\n"
        return head + "".join(
            "    volatile uint32_t *p%d = p%d;\n" % (index, index - 1)
            for index in range(1, links)
        )

    def resolutions_for(links):
        original = gate.resolve_address_role
        calls = [0]

        def counted(expr, defs, known):
            calls[0] += 1
            return original(expr, defs, known)

        gate.resolve_address_role = counted
        try:
            started = time.time()
            roles = gate.pointer_roles(chain_body(links), defines)
            return calls[0], roles, time.time() - started
        finally:
            gate.resolve_address_role = original

    links = 4000
    calls, roles, elapsed = resolutions_for(links)
    half_calls, _half_roles, _half_elapsed = resolutions_for(links // 2)

    check(
        "a %d-link alias chain resolves in work linear in its length" % links,
        calls <= 10 * links,
        "%d resolutions for %d links" % (calls, links),
    )
    # Doubling the chain may not more than roughly double the work. This is the
    # deterministic form of the claim -- a quadratic walk quadruples here, and no
    # wall clock is involved, so the assertion cannot flake on a busy machine.
    check(
        "doubling the alias chain does not more than double the work",
        calls <= 3 * half_calls,
        "%d resolutions at %d links vs %d at %d" % (calls, links, half_calls, links // 2),
    )
    # Non-vacuity: a bounded walk that resolved nothing would also be cheap.
    check(
        "every link of the chain still resolves to the register it copies",
        len(roles) == links and set(roles.values()) == {"QREAD"},
        "%d names, roles=%s" % (len(roles), sorted(set(roles.values()))),
    )
    check(
        "the bounded alias walk finishes well inside a coarse wall-clock bound",
        elapsed < 30.0,
        "%.2fs for %d links" % (elapsed, links),
    )
    # The stepped-name walk is driven by the operator set, not by an alternation
    # rebuilt from the candidate names, so a large name set costs no rescan.
    stepped_text = chain_body(2000) + "    p1999 += 4;\n"
    many = tuple("p%d" % index for index in range(2000))
    check(
        "the stepped-name walk answers the same over a large name set",
        gate.compound_assignment_targets(stepped_text, many) == ("p1999",)
        and gate.compound_assignment_targets(stepped_text, ("p1999",)) == ("p1999",)
        and gate.compound_assignment_targets(stepped_text, ("p0",)) == (),
        repr(gate.compound_assignment_targets(stepped_text, many))[:60],
    )

    # The same chain through the whole gate is a verdict, never a hang and never
    # a traceback.
    chain = "".join(
        "    volatile uint32_t *c%d = %s;\n" % (index, "qread_reg" if index == 0 else "c%d" % (index - 1))
        for index in range(2000)
    )
    started = time.time()
    try:
        gate.verify_generated_sources(
            canonical_runner("Q"),
            replace_once(
                canonical_vendor("Q"),
                Q_LOOP_PROLOGUE,
                chain + Q_LOOP_PROLOGUE,
                "Q primary loop prologue",
            ),
            "Q",
        )
        outcome = "accepted"
    except gate.GateError as exc:
        outcome = "FAIL %s" % exc
    except RecursionError as exc:  # pragma: no cover - the defect this guards
        outcome = "RecursionError %r" % exc
    check(
        "a 2000-link chain through the whole gate is a verdict, not a hang",
        not outcome.startswith("RecursionError") and time.time() - started < 60.0,
        "%s in %.2fs" % (outcome[:40], time.time() - started),
    )

    # The access enumerator and the address-of stripper both walk raw operator
    # runs. A source made of nothing but openers, stars or ampersands is a named
    # verdict rather than a traceback -- the same guarantee ``_MAX_SOURCE_BYTES``
    # and ``_MAX_NESTING_DEPTH`` already carry for the constructs they bound.
    # Appended to a *valid* vendor so the run actually reaches the enumerator
    # rather than stopping at the first define check. Either verdict is fine
    # here -- the assertion is that one is reached, bounded and traceback-free.
    hostile = {
        "20k open subscripts": "\nint hostile_q = " + "a[" * 20000 + "0;\n",
        "20k unary stars": "\nint hostile_s = " + "*" * 20000 + "p;\n",
        "20k address-of": "\nint hostile_w = " + "&" * 20000 + "p;\n",
        "6000 deep parens": "\nint hostile_z = " + "(" * 6000 + "1" + ")" * 6000 + ";\n",
        "20k balanced subscripts": "\nint hostile_b = " + "a[0]" * 20000 + ";\n",
    }
    for label, tail in hostile.items():
        started = time.time()
        try:
            gate.verify_generated_sources(
                canonical_runner("Q"), canonical_vendor("Q") + tail, "Q"
            )
            verdict = "accepted"
        except gate.GateError as exc:
            verdict = "FAIL %s" % exc
        except RecursionError as exc:  # pragma: no cover - the defect this guards
            verdict = "RecursionError %r" % exc
        elapsed = time.time() - started
        check(
            "a vendor carrying %s is a bounded verdict, not a traceback" % label,
            (verdict == "accepted" or verdict.startswith("FAIL ")) and elapsed < 30.0,
            "%s in %.2fs" % (verdict[:40], elapsed),
        )


def run_reviewer_blocker_suite(gate):
    """Every acceptance and red-team blocker, as a fixture that once passed."""

    run_vendor_mutations(gate, POST_STORE_MUTATION_MUTATIONS, "Q")
    run_vendor_mutations(gate, FAILURE_WINDOW_MUTATIONS, "Q")
    run_vendor_mutations(gate, MMIO_FOLDING_MUTATIONS, "Q")
    run_vendor_mutations(gate, MMIO_POINTER_STEP_MUTATIONS, "Q")
    run_vendor_mutations(gate, LINE_SPLICING_MUTATIONS, "Q")
    run_vendor_mutations(gate, STORAGE_ALIAS_MUTATIONS, "Q")
    run_vendor_mutations(gate, NVIC_ISOLATION_MUTATIONS, "Q")
    run_vendor_mutations(gate, BOUNDED_ANALYSIS_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_TRANSPORT_MUTATIONS, "Q")

    # The publishing-guard rules are about the two-observation loops, so they are
    # proven in both of the variants that have one.
    for variant in ("QS", "SQ"):
        for name, mutate, reason in PUBLISHING_GUARD_MUTATIONS:
            scoped = "%s_%s" % (variant.lower(), name)
            REJECTED_FIXTURES.add(scoped)
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                mutate(canonical_vendor(variant)),
                scoped,
                reason,
            )

    # A splice inside a token is refused rather than analysed under a
    # tokenisation the built image does not share.
    try:
        gate.mask_c_lexical("int f(void){ int abc = 1; return a\\\nbc; }")
    except gate.GateError as exc:
        check("a line splice inside a token is a named rejection", "inside a token" in str(exc))
    else:
        check("a line splice inside a token is a named rejection", False, "accepted")

    # A spliced comment opener really does delete the enclosed text.
    original = "int x = 1;\n/\\\n*\nx = 999;\n*/\nint y = 2;\n"
    spliced = gate.mask_c_lexical(original)
    check(
        "a spliced comment opener blanks the code it encloses",
        "999" not in spliced
        and "int x = 1;" in spliced
        and "int y = 2;" in spliced
        and len(spliced) == len(original),
        repr(spliced)[:70],
    )

    # A continued preprocessor directive is one logical line, so blanking it
    # cannot unbalance the statement scan below it.
    continued = gate.blank_directives("#define M(a) ((a) \\\n  | (a))\nd.x = m[0];\n")
    check(
        "a continued preprocessor directive is blanked whole",
        continued.strip() == "d.x = m[0];" and continued.count("(") == 0,
        repr(continued)[:70],
    )

    verdict = _mask_rejection(gate, "/*" * ((4 << 20) // 2 + 8))
    check(
        "a source past the scan bound is a named rejection",
        verdict.startswith("source is larger than"),
        verdict[:70],
    )

    started = time.time()
    gate.mask_c_lexical("/*x" * 40000)
    elapsed = time.time() - started
    check(
        "unterminated block-comment openers stay linear",
        elapsed < 1.0,
        "%.2fs for 120 KB" % elapsed,
    )

    # The bound is structural, so the CLI reports it as a verdict. A traceback
    # on stderr is what commit 194d2db exists to keep out of this gate.
    with tempfile.TemporaryDirectory() as scratch:
        runner_path = os.path.join(scratch, "runner.c")
        vendor_path = os.path.join(scratch, "vendor.c")
        with open(runner_path, "w", encoding="utf-8") as handle:
            handle.write(canonical_runner("Q"))
        with open(vendor_path, "w", encoding="utf-8") as handle:
            handle.write(deeply_nested_primary_guards(canonical_vendor("Q")))
        result = run_checker(
            [
                "--allow-fixture",
                "--variant",
                "Q",
                "--runner-generated",
                runner_path,
                "--vendor-generated",
                vendor_path,
                "--fixture-manifest-out",
                os.path.join(scratch, "manifest.json"),
            ]
        )
        combined = result.stdout + result.stderr
        check(
            "pathological guard nesting is a named FAIL, not a traceback",
            result.returncode == 1
            and combined.startswith("FAIL ")
            and "Traceback" not in combined,
            combined.strip()[:70],
        )


def _mask_rejection(gate, text):
    try:
        gate.mask_c_lexical(text)
    except gate.GateError as exc:
        return str(exc)
    return "accepted"


def run_encoding_cli_suite(patcher):
    """A source that is not UTF-8 is a named FAIL line, never a traceback."""

    with tempfile.TemporaryDirectory() as scratch:
        runner_path = os.path.join(scratch, "runner.c")
        vendor_path = os.path.join(scratch, "vendor.c")
        with open(runner_path, "w", encoding="utf-8") as handle:
            handle.write(canonical_runner("Q"))
        with open(vendor_path, "wb") as handle:
            handle.write(canonical_vendor("Q").encode("utf-8").replace(b"//Start NPU", b"//Start \xff\xfeNPU"))

        result = run_checker(
            [
                "--allow-fixture",
                "--variant",
                "Q",
                "--runner-generated",
                runner_path,
                "--vendor-generated",
                vendor_path,
                "--fixture-manifest-out",
                os.path.join(scratch, "manifest.json"),
            ]
        )
        combined = result.stdout + result.stderr
        check(
            "a non-UTF-8 vendor source is a named FAIL, not a traceback",
            result.returncode == 1
            and "FAIL generated vendor: is not UTF-8 text" in combined
            and "Traceback" not in combined,
            combined.strip()[:70],
        )

        # The generator hashes both inputs before it decodes either, so its CLI
        # can never reach the decoder with the frozen sources. The contract is
        # still the reader's, so it is proven where it lives.
        try:
            patcher._read_text(vendor_path)
            verdict = "returned text"
        except patcher.PatchError as error:
            verdict = str(error)
        except Exception as error:  # pragma: no cover - a crash is not a verdict
            verdict = repr(error)
        check(
            "a non-UTF-8 generator input is a named FAIL, not a traceback",
            "FAIL input is not UTF-8 text" in verdict,
            verdict[:70],
        )


# ---------------------------------------------------------------------------
# The acceptance grammar: what an accepted source is allowed to be written as
#
# Every fixture below was accepted by 96d5113 and publishes a manifest field
# that is false for the image the compiler builds. They are grouped by the
# *shape* that reached past a rule rather than by the rule, because each one is
# another spelling of a construct the gate already models -- which is what a
# grammar, and not one more spelling exception, has to answer.
# ---------------------------------------------------------------------------

TERMINAL_CMD_WRITE = "\t    write_reg(NPU_REG_CMD, 0x0000000C);\n"
ISR_TRIGGER_SET = "        irq_triggered = true;\n"
PRIMARY_PUBLICATION_CALL = "\t  v14_publish_primary(&primary, qsize_expected);\n"
FIRST_STATE_OBSERVED_STORE = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATE]"
    " = (obs->status & V14_STATUS_STATE);\n"
)
COMMAND_FUNCTION_HEAD = "static int test_commands("


def _spliced_directive(directive):
    """``#\\<newline> <directive>`` -- one logical directive line to the compiler.

    Translation phase 2 deletes the backslash and the newline before phase 4
    recognises the directive, so this is exactly ``#<directive>``.
    """

    return "#\\\n " + directive + "\n"


def _form_feed_directive(directive):
    """``#\\f<directive>`` -- a form feed is directive whitespace in C."""

    return "#\014" + directive + "\n"


def _repointed_around(anchor, spell, macro, hidden, restored, what):
    """Repoint ``macro`` at ``anchor`` only, and restore it straight after."""

    def mutate(vendor):
        return replace_once(
            vendor,
            anchor,
            spell("undef " + macro)
            + spell("define %s %s" % (macro, hidden))
            + anchor
            + spell("undef " + macro)
            + spell("define %s %s" % (macro, restored)),
            what,
        )

    return mutate


LOGICAL_DIRECTIVE_LINE_MUTATIONS = (
    (
        "contract_macro_repointed_by_a_spliced_directive",
        _repointed_around(
            VARIANT_ID_STORE, _spliced_directive, "V14_MBOX_VARIANT_ID", "7U", "0U",
            "variant id store",
        ),
        "undefines a contract macro",
    ),
    (
        "contract_macro_repointed_by_a_form_feed_directive",
        _repointed_around(
            VARIANT_ID_STORE, _form_feed_directive, "V14_MBOX_VARIANT_ID", "7U", "0U",
            "variant id store",
        ),
        "undefines a contract macro",
    ),
    (
        "register_offset_macro_repointed_by_a_spliced_directive",
        _repointed_around(
            PRE_PROGRAM_STATUS_READ, _spliced_directive, "NPU_REG_STATUS", "0x0CU",
            "0x14U", "pre-program status read",
        ),
        "undefines a contract macro",
    ),
    (
        "variant_id_macro_repointed_by_a_spliced_directive",
        _repointed_around(
            VARIANT_ID_STORE, _spliced_directive, "V14_VARIANT_ID", "3U", "1U",
            "variant id store",
        ),
        "undefines a contract macro",
    ),
)

# An array declarator binds an address without ever writing ``name = expr``, so
# every alias walk built on the assignment form reported the dereference as
# "not an NPU address at all" and dropped the access entirely.
POINTER_ARRAY_ALIAS_MUTATIONS = (
    (
        "running_qsize_read_through_a_pointer_array_alias",
        _append_after(
            SUBMIT_WRITE,
            "\t  { volatile uint32_t *const rt_regs[1] = {\n"
            "\t        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE) };\n"
            "\t    read_val = (int)*rt_regs[0]; }\n",
            "submit write",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_file_scope_pointer_array",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                COMMAND_FUNCTION_HEAD,
                "static volatile uint32_t *const rt_gregs[1] = {\n"
                "    (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE) };\n\n"
                + COMMAND_FUNCTION_HEAD,
                "command function head",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  read_val = (int)*rt_gregs[0];\n",
            "submit write",
        ),
        "QSIZE",
    ),
    (
        "second_submit_through_a_pointer_array_alias",
        _append_after(
            SUBMIT_WRITE,
            "\t  { volatile uint32_t *const rt_cmd[1] = {\n"
            "\t        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD) };\n"
            "\t    *rt_cmd[0] = 1U; }\n",
            "submit write",
        ),
        "exactly one NPU submit write",
    ),
    (
        # In a helper none of the four inspected functions is, so the file-wide
        # ISER fold is what has to name it rather than the local pointer rule.
        "nvic_iser_enable_through_a_pointer_array_alias",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                COMMAND_FUNCTION_HEAD,
                "static void v14_rt_iser_poke(void)\n{\n"
                "    volatile uint32_t *const rt_iser[1] = {\n"
                "        (volatile uint32_t *)(0xE000E000UL + 0x100UL) };\n"
                "    *rt_iser[0] = 1UL;\n}\n\n" + COMMAND_FUNCTION_HEAD,
                "command function head",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  v14_rt_iser_poke();\n",
            "submit write",
        ),
        "direct NVIC ISER enable write is reachable",
    ),
    (
        "terminal_cmd_write_repeated_through_a_pointer_array_alias",
        _append_after(
            TERMINAL_CMD_WRITE,
            "\t    { volatile uint32_t *const rt_cmd[1] = {\n"
            "\t          (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD) };\n"
            "\t      *rt_cmd[0] = 0x0000000CU; }\n",
            "terminal cmd write",
        ),
        "success cleanup ordering drifted",
    ),
    (
        "mailbox_word_rewritten_through_a_pointer_array_alias",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "\t  { volatile uint32_t *const rt_mb[1] = { pmu_completion_visibility_v14_mailbox };\n"
            "\t    rt_mb[0][V14_MBOX_VARIANT_ID] = 7U; }\n",
            "primary publication call",
        ),
        "variant id",
    ),
)

# ``blank_directives`` removes the ``#define`` line from the statement stream and
# the invocation site is only ``NAME;``, so an object-like macro whose body is a
# whole statement was a store no lvalue rule ever saw.
STATEMENT_MACRO_MUTATIONS = (
    (
        "irq_triggered_set_through_a_statement_macro",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                ISR_TRIGGER_SET,
                ISR_TRIGGER_SET + "#define V14_RT_SET_TRIG irq_triggered = true\n",
                "stock handler trigger set",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  V14_RT_SET_TRIG;\n",
            "submit write",
        ),
        "statement",
    ),
    (
        "mailbox_word_rewritten_through_a_statement_macro",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                ISR_TRIGGER_SET,
                ISR_TRIGGER_SET
                + "#define V14_RT_POKE"
                " pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = 7U\n",
                "stock handler trigger set",
            ),
            PRIMARY_PUBLICATION_CALL,
            PRIMARY_PUBLICATION_CALL + "\t  V14_RT_POKE;\n",
            "primary publication call",
        ),
        "statement",
    ),
    (
        "mmio_written_through_a_statement_macro",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                ISR_TRIGGER_SET,
                ISR_TRIGGER_SET
                + "#define V14_RT_CMD write_reg(NPU_REG_CMD, 1U)\n",
                "stock handler trigger set",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  V14_RT_CMD;\n",
            "submit write",
        ),
        "the macro V14_RT_CMD",
    ),
)

# A cast's closing parenthesis and a call's are the same character, and the
# address-of scan resolved that ambiguity in the fail-open direction.
def _irq_alias_in_an_uncovered_helper(declaration, store):
    """Bind the alias in a helper none of the four inspected functions is.

    Inside ``test_commands`` a pointer cast the register resolver cannot pin is
    refused incidentally, which proves nothing about the address-of scan. The
    helper is where the acceptance review measured all three cast types being
    accepted, so it is where the rule has to name them.
    """

    def mutate(vendor):
        return replace_once(
            replace_once(
                vendor,
                COMMAND_FUNCTION_HEAD,
                "static void v14_rt_arm_flag(void)\n{\n    %s\n    %s\n}\n\n"
                % (declaration, store)
                + COMMAND_FUNCTION_HEAD,
                "command function head",
            ),
            SUBMIT_WRITE,
            SUBMIT_WRITE + "\t  v14_rt_arm_flag();\n",
            "submit write",
        )

    return mutate


IRQ_TRIGGERED_CAST_ALIAS_MUTATIONS = (
    (
        "irq_triggered_aliased_through_a_cast_parenthesis",
        _append_after(
            SUBMIT_WRITE,
            "\t  { bool *trig_alias = (bool *)&irq_triggered; *trig_alias = true; }\n",
            "submit write",
        ),
        "irq_triggered can become true on a measured path",
    ),
    (
        "irq_triggered_aliased_through_a_void_cast_parenthesis",
        _irq_alias_in_an_uncovered_helper(
            "void *trig_alias = (void *)&irq_triggered;", "*(bool *)trig_alias = true;"
        ),
        "irq_triggered can become true on a measured path",
    ),
    (
        "irq_triggered_aliased_through_a_cast_in_an_uncovered_helper",
        _irq_alias_in_an_uncovered_helper(
            "bool *trig_alias = (bool *)&irq_triggered;", "*trig_alias = true;"
        ),
        "irq_triggered can become true on a measured path",
    ),
)

# The magic is what declares the other 33 words real, and it was counted by the
# text of the stored value rather than by the value the compiler folds.
SECOND_MAGIC_MUTATIONS = tuple(
    (
        "second_magic_published_as_%s" % label,
        _prepend_before(
            VARIANT_ID_STORE,
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = %s;\n"
            % spelling,
            "variant id store",
        ),
        "mailbox_valid is published from more than one site",
    )
    for label, spelling in (
        ("a_folded_sum", "V14_MAILBOX_VALID + 0U"),
        ("a_parenthesised_macro", "(V14_MAILBOX_VALID)"),
        ("a_folded_disjunction", "0x5631344DU | 0U"),
        ("a_folded_product", "V14_MAILBOX_VALID * 1U"),
    )
)

# Every appendix word is published by the sites the design gives it. Proving a
# word has *a* producer left every other rule in this file -- provenance,
# predicate shape, publishing guards -- bypassable by one unconditional store
# downstream of the proof.
APPENDIX_AUTHORIZED_PRODUCER_MUTATIONS = tuple(
    (
        "%s_forged_from_a_second_store" % field,
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_%s] = %s;\n"
            % (field.upper(), value),
            "primary publication call",
        ),
        "appendix word %d (%s)" % (APPENDIX_FIELDS.index(field), field),
    )
    for field, value in (
        ("convergence_result", "V14_CONVERGENCE_SUCCESS"),
        ("pre_submit_status", "0U"),
        ("primary_result", "V14_PRIMARY_OBSERVED"),
        ("failure_phase", "V14_PHASE_NONE"),
        ("installed_vector", "0xDEADBEEFU"),
        ("convergence_timeout", "0U"),
    )
) + (
    (
        "first_state_producer_deleted_by_a_spliced_comment",
        lambda vendor: replace_once(
            vendor,
            FIRST_STATE_OBSERVED_STORE,
            "    /\\\n*\n" + FIRST_STATE_OBSERVED_STORE + "    */\n",
            "first_state observed store",
        ),
        "appendix word 14 (first_state)",
    ),
    (
        "appendix_word_published_from_an_unauthorized_function",
        lambda vendor: replace_once(
            vendor,
            PRIMARY_RESULT_PUBLICATION,
            PRIMARY_RESULT_PUBLICATION
            + "    pmu_completion_visibility_v14_mailbox[V14_MBOX_QSIZE_EXPECTED]"
            " = qsize_expected;\n",
            "primary result publication",
        ),
        "appendix word 1 (qsize_expected)",
    ),
)

# The runner record is the transport. It was closed against the literal
# ``d.<field>`` spelling only, so every other lvalue that designates the same
# storage rewrote a published field after the copy this gate proved.
RUNNER_RECORD_ALIAS_MUTATIONS = (
    (
        "runner_record_rewritten_through_a_parenthesised_address_of",
        _after_the_appendix_copy("    (&d)->variant_id = 3U;\n"),
        "runner rewrites a copied appendix field",
    ),
    (
        "runner_record_rewritten_through_a_record_pointer_alias",
        _after_the_appendix_copy(
            "    { pmu_diag_record_t *rt_rd = &d; rt_rd->variant_id = 3U; }\n"
        ),
        "runner rewrites a copied appendix field",
    ),
    (
        "runner_record_read_modify_written_through_a_record_pointer_alias",
        _after_the_appendix_copy(
            "    { pmu_diag_record_t *rt_rd = &d; rt_rd->first_qread |= 0x80000000U; }\n"
        ),
        "runner rewrites a copied appendix field",
    ),
    (
        "runner_record_rewritten_through_an_array_of_record_pointers",
        _after_the_appendix_copy(
            "    { pmu_diag_record_t *const rt_a[1] = {&d}; rt_a[0]->variant_id = 3U; }\n"
        ),
        "runner rewrites a copied appendix field",
    ),
    (
        "runner_record_rewritten_through_a_statement_macro",
        _after_the_appendix_copy(
            "#define V14_RT_RD d.variant_id = 3U\n    V14_RT_RD;\n"
        ),
        "statement",
    ),
)


# ---------------------------------------------------------------------------
# Source-gate remediation fixtures.
#
# Each family below was ACCEPTED at 7456670 -- the real checker CLI answered
# rc=0 over a mutated pair whose compiled semantics contradict the manifest it
# wrote. They are grouped by the assumption the gate was making, because that
# is what a reader has to re-check when the analyzer changes: not "is this still
# rejected" but "is the reason it is rejected still the structural one".
# ---------------------------------------------------------------------------

QSIZE_ADDRESS = "(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE)"
STATUS_ADDRESS = "(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS)"
CMD_ADDRESS = "(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD)"
PRIMARY_TIMEOUT_RESULT_STORE = "    obs->result = V14_PRIMARY_TIMEOUT;\n"
# The dual-read primaries end with the same two stores, so the convergence tail
# is anchored on the one store only it makes -- the local ``result`` it settled
# in its loop.
CONVERGE_OBSERVATION_TAIL = (
    "    obs->result = result;\n"
    "    obs->iterations = iterations;\n"
    "    obs->qread = qread;\n"
    "    obs->status = status;\n}"
)
CONVERGE_CALL = "\t  v14_converge(qsize_expected, &converged);\n"
RUNNER_RECORD_RESET = "    memset(&d, 0, sizeof(d));\n"
RUNNER_FIRST_APPENDIX_COPY = (
    "            d.variant_id = pmu_completion_visibility_v14_mailbox[0];\n"
)


def _after_the_first_appendix_copy(statement):
    """Put ``statement`` inside the magic branch, right under the first copy."""

    return _append_after(
        RUNNER_FIRST_APPENDIX_COPY, statement, "runner first appendix copy"
    )


def _at_file_scope(declaration):
    """Put ``declaration`` at file scope, just above the command function."""

    return lambda vendor: replace_once(
        vendor,
        COMMAND_FUNCTION_HEAD,
        declaration + "\n" + COMMAND_FUNCTION_HEAD,
        "command function head",
    )


def _read_in_the_q_loop(declaration, expression):
    """Bind at file scope and read it once per primary iteration."""

    def mutate(vendor):
        return replace_once(
            _at_file_scope(declaration)(vendor),
            Q_LOOP_READ_AND_GUARD,
            "        qread = *qread_reg;\n        (void)%s;\n"
            "        if (qread == qsize_expected) {\n" % expression,
            "q loop read and guard",
        )

    return mutate


def _digraph_directive(directive):
    """``%:<directive>`` -- C11 6.4.6 spells the ``#`` punctuator this way too."""

    return "%:" + directive + "\n"


def _trigraph_directive(directive):
    """``??=<directive>`` -- C11 5.2.1.1, replaced in translation phase 1."""

    return "??=" + directive + "\n"


def _spliced_digraph_directive(directive):
    """``%\\<newline>:<directive>`` -- the two digraph characters, spliced apart."""

    return "%\\\n:" + directive + "\n"


VENDOR_DEFINE_BLOCK_ANCHOR = "#define V14_PRIMARY_NOT_RUN 0U\n"


def _repointed_for_the_translation_unit(spell, macro, value):
    """Undefine and redefine ``macro`` at file scope, for the whole unit.

    The directives sit inside the define block with no code near them, so
    nothing but a directive scan can notice them at all. That is what makes this
    the faithful reproduction: ``_repointed_around`` brackets a *use site*, and
    the frozen-spelling rules then object to the lines it inserted rather than
    to the redefinition. Here the compiler builds every use site at ``value``
    while the gate keeps reading the frozen definition, and nothing else about
    the source has changed.
    """

    return lambda vendor: replace_once(
        vendor,
        VENDOR_DEFINE_BLOCK_ANCHOR,
        VENDOR_DEFINE_BLOCK_ANCHOR
        + spell("undef " + macro)
        + spell("define %s %s" % (macro, value)),
        "vendor define block",
    )


# F1. Every directive scan in the gate anchored on the literal ``#``, and every
# structural walk counted the literal braces and brackets. C spells all four
# punctuators a second way, unconditionally and without a diagnostic, so the
# whole ``#undef``/redefine class the contract-macro rule exists to prevent was
# reachable again -- in both translation units, for every contract macro.
ALTERNATE_TOKEN_SPELLING_MUTATIONS = (
    (
        "contract_macro_repointed_by_a_digraph_directive",
        _repointed_for_the_translation_unit(_digraph_directive, "V14_MBOX_VARIANT_ID", "7U"),
        "writes the digraph %:",
    ),
    (
        "register_offset_macro_repointed_by_a_digraph_directive",
        _repointed_for_the_translation_unit(_digraph_directive, "NPU_REG_STATUS", "0x0CU"),
        "writes the digraph %:",
    ),
    (
        "magic_macro_repointed_by_a_digraph_directive",
        _repointed_for_the_translation_unit(_digraph_directive, "V14_MAILBOX_VALID", "0xDEADBEEFU"),
        "writes the digraph %:",
    ),
    (
        "contract_macro_repointed_by_a_trigraph_directive",
        _repointed_for_the_translation_unit(_trigraph_directive, "V14_MBOX_VARIANT_ID", "7U"),
        "writes the trigraph ??=",
    ),
    (
        # The two digraph characters are one token to the compiler whether or
        # not a phase-2 splice sits between them.
        "digraph_directive_split_by_a_line_splice",
        _repointed_for_the_translation_unit(
            _spliced_digraph_directive, "V14_MBOX_VARIANT_ID", "7U"
        ),
        "writes the digraph %:",
    ),
    (
        # ``<:``/``:>`` are the subscript brackets, so this is a second store to
        # appendix word 0 that no bracket-counting walk in the gate can see.
        "mailbox_word_rewritten_through_digraph_brackets",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "\t  pmu_completion_visibility_v14_mailbox<:V14_MBOX_VARIANT_ID:> = 7U;\n",
            "primary publication call",
        ),
        "writes the digraph <:",
    ),
    (
        # ``<%``/``%>`` are the braces, so this unbalances every structural walk
        # in the gate at once while the compiler reads a well-formed block.
        "block_braces_written_as_digraphs",
        _append_after(
            SUBMIT_WRITE,
            "\t  if (read_val == 0) <% read_val = 0; %>\n",
            "submit write",
        ),
        "writes the digraph <%",
    ),
)

RUNNER_ALTERNATE_TOKEN_SPELLING_MUTATIONS = (
    (
        "runner_contract_macro_repointed_by_a_digraph_directive",
        _prepend_before(
            RUNNER_MAGIC_GUARD_LINE,
            "%:undef V14_MAILBOX_VALID\n%:define V14_MAILBOX_VALID 0U\n",
            "runner magic guard",
        ),
        "writes the digraph %:",
    ),
    (
        "runner_contract_macro_repointed_by_a_trigraph_directive",
        _prepend_before(
            RUNNER_MAGIC_GUARD_LINE,
            "??=undef V14_MAILBOX_VALID\n??=define V14_MAILBOX_VALID 0U\n",
            "runner magic guard",
        ),
        "writes the trigraph ??=",
    ),
)

# F2. The declarator rule recovered its initializer with a pattern whose body
# could not contain a brace, and the assignment rule ran greedily to the
# statement's ``;``. Both misses answer "not an NPU address at all" rather than
# "unresolved", which is the one answer that makes an access invisible instead
# of refused -- so every ordering, counting and isolation rule below was
# reachable through one extra brace pair or one extra declarator.
DECLARATOR_INITIALIZER_MUTATIONS = (
    (
        "running_qsize_read_through_a_nested_brace_pointer_array",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_n1[1] = { { %s } };" % QSIZE_ADDRESS,
            "*rt_n1[0]",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_two_dimensional_pointer_array",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_n2[1][1] = {{ %s }};" % QSIZE_ADDRESS,
            "*rt_n2[0][0]",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_three_dimensional_pointer_array",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_n3[1][1][1] = {{{ %s }}};" % QSIZE_ADDRESS,
            "*rt_n3[0][0][0]",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_designated_nested_initializer",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_n4[1] = { [0] = { %s } };" % QSIZE_ADDRESS,
            "*rt_n4[0]",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_comma_declarator_list",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_c1 = %s, *const rt_c2 = rt_c1;" % QSIZE_ADDRESS,
            "*rt_c2",
        ),
        "QSIZE",
    ),
    (
        "running_qsize_read_through_a_three_declarator_comma_list",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_c3 = %s, *const rt_c4 = rt_c3,"
            " *const rt_c5 = rt_c4;" % QSIZE_ADDRESS,
            "*rt_c5",
        ),
        "QSIZE",
    ),
    (
        "primary_status_read_through_a_comma_declarator_list",
        _read_in_the_q_loop(
            "static volatile uint32_t *const rt_s1 = %s, *const rt_s2 = rt_s1;" % STATUS_ADDRESS,
            "*rt_s2",
        ),
        "Q primary loop reads STATUS",
    ),
    (
        "second_submit_through_a_two_dimensional_pointer_array",
        _append_after(
            SUBMIT_WRITE,
            "\t  { volatile uint32_t *const rt_g2[1][1] = {{ %s }};\n"
            "\t    *rt_g2[0][0] = 1U; }\n" % CMD_ADDRESS,
            "submit write",
        ),
        "exactly one NPU submit write",
    ),
    (
        "terminal_cmd_write_repeated_through_a_nested_brace_pointer_array",
        _append_after(
            TERMINAL_CMD_WRITE,
            "\t    { volatile uint32_t *const rt_g3[1] = { { %s } };\n"
            "\t      *rt_g3[0] = 0x0000000CU; }\n" % CMD_ADDRESS,
            "terminal cmd write",
        ),
        "success cleanup ordering drifted",
    ),
    (
        "mailbox_word_rewritten_through_a_two_dimensional_pointer_array",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "\t  { volatile uint32_t *const rt_g4[1][1] = {{ pmu_completion_visibility_v14_mailbox }};\n"
            "\t    rt_g4[0][0][V14_MBOX_VARIANT_ID] = 7U; }\n",
            "primary publication call",
        ),
        "variant id",
    ),
    (
        # The queue-programming single-owner proof was built on the
        # ``write_reg(NPU_REG_QSIZE`` call, and a write through a bound pointer
        # carries no call for that scan to find.
        "tail_qsize_write_through_a_two_dimensional_pointer_array",
        _prepend_before(
            STOP_NPU_WRITE,
            "\t  { volatile uint32_t *const rt_q2[1][1] = {{ %s }};\n"
            "\t    *rt_q2[0][0] = 1U; }\n" % QSIZE_ADDRESS,
            "stop npu write",
        ),
        "queue programming is split across",
    ),
    (
        "tail_qsize_write_through_a_comma_declarator_list",
        _prepend_before(
            STOP_NPU_WRITE,
            "\t  { volatile uint32_t *const rt_q3 = %s, *const rt_q4 = rt_q3;\n"
            "\t    *rt_q4 = 1U; }\n" % QSIZE_ADDRESS,
            "stop npu write",
        ),
        "queue programming is split across",
    ),
    (
        # A compound literal is a brace initializer with no declarator in front
        # of it, so there is no name to bind and no name to follow -- the same
        # defect with the name removed instead of the braces added.
        # Bound in the primary helper's declarations, which is where the named
        # array sibling is refused by the QSIZE-in-a-primary-loop rule.
        "qsize_load_through_a_compound_literal_array",
        lambda vendor: bind_in_primary(
            vendor,
            "    uint32_t rt_sneak = *((volatile uint32_t *const []){ %s })[0];\n"
            "    (void)rt_sneak;\n" % QSIZE_ADDRESS,
        ),
        "writes a compound literal",
    ),
    (
        "qsize_load_through_a_compound_literal_scalar",
        lambda vendor: bind_in_primary(
            vendor,
            "    uint32_t rt_sneak = *(volatile uint32_t *const){ %s };\n"
            "    (void)rt_sneak;\n" % QSIZE_ADDRESS,
        ),
        "writes a compound literal",
    ),
    (
        # A unary ``&`` cannot introduce a call, so it cannot be read as the end
        # of an operand here the way the address-of walk reads it.
        "qsize_load_through_a_compound_literal_behind_an_address_of",
        _append_after(
            SUBMIT_WRITE,
            "\t  read_val = (int)**&(volatile uint32_t *const){ %s };\n" % QSIZE_ADDRESS,
            "submit write",
        ),
        "writes a compound literal",
    ),
    (
        "compound_literal_nested_in_a_declarator_initializer",
        _at_file_scope(
            "static volatile uint32_t *const rt_u1[1] ="
            " { (volatile uint32_t *)&(uint32_t){0} };"
        ),
        "writes a compound literal",
    ),
)

# F3. The write-once proof over the serialized record reads lvalues, and an
# lvalue is only resolved when its last token follows a ``.`` or a ``->``. A
# write that names no member was therefore neither proven nor refused.
RUNNER_RECORD_STORAGE_MUTATIONS = (
    (
        "runner_record_field_written_through_a_field_pointer",
        _after_the_appendix_copy("    { uint32_t *rt_pf = &d.variant_id; *rt_pf = 3U; }\n"),
        "takes the address of the appendix field variant_id",
    ),
    (
        "runner_record_appendix_wiped_by_memset",
        _after_the_appendix_copy("    memset(&d.variant_id, 0, 34U * 4U);\n"),
        "takes the address of the appendix field variant_id",
    ),
    (
        "runner_record_field_written_by_memcpy",
        _after_the_appendix_copy(
            "    { uint32_t rt_z = 3U; memcpy(&d.variant_id, &rt_z, sizeof rt_z); }\n"
        ),
        "takes the address of the appendix field variant_id",
    ),
    (
        # Bound before the proven copy and written after it, so no rule that
        # only looks inside the window can see the binding.
        "runner_record_field_pointer_bound_before_the_copy",
        lambda runner: _after_the_appendix_copy("    *rt_pg = 3U;\n")(
            replace_once(
                runner,
                RUNNER_RECORD_RESET,
                RUNNER_RECORD_RESET + "    uint32_t *rt_pg = &d.variant_id;\n",
                "runner record reset",
            )
        ),
        "takes the address of the appendix field variant_id",
    ),
    (
        "runner_record_written_through_a_byte_pointer_alias",
        lambda runner: _after_the_appendix_copy("    *(uint32_t *)rt_cp = 3U;\n")(
            replace_once(
                runner,
                RUNNER_RECORD_RESET,
                RUNNER_RECORD_RESET + "    uint8_t *rt_cp = (uint8_t *)&d;\n",
                "runner record reset",
            )
        ),
        "reaches the serialized record as whole storage",
    ),
    (
        "runner_record_written_through_a_subscripted_address",
        _after_the_appendix_copy("    ((uint32_t *)&d)[0] = 3U;\n"),
        "reaches the serialized record as whole storage",
    ),
    (
        "runner_record_handed_to_a_call_after_the_copy",
        _after_the_appendix_copy("    memset(&d, 0, sizeof d);\n"),
        "reaches the serialized record as whole storage",
    ),
    # A store is credited as a *copy* by its rvalue resolving to a mailbox word,
    # and the "outside the branch" walk only looks at where a store sits. A
    # second store to an already-copied field, inside the branch, from a
    # constant, is therefore neither -- it rewrites a published field one line
    # under the copy this gate proved.
    (
        "runner_record_field_forged_inside_the_magic_branch",
        _after_the_first_appendix_copy("            d.variant_id = 0U;\n"),
        "from something that is not its mailbox word",
    ),
    (
        "runner_record_field_forged_in_the_branch_through_a_pointer_alias",
        _after_the_first_appendix_copy(
            "            { pmu_diag_record_t *rt_dp = &d; rt_dp->variant_id = 0U; }\n"
        ),
        "from something that is not its mailbox word",
    ),
    (
        "runner_record_field_forged_in_the_branch_through_an_array_of_aliases",
        _after_the_first_appendix_copy(
            "            { pmu_diag_record_t *const rt_da[1][1] = {{ &d }};"
            " rt_da[0][0]->variant_id = 0U; }\n"
        ),
        "from something that is not its mailbox word",
    ),
)

# F4. The appendix words are copies of observation-record fields, so every
# provenance, predicate and publishing-guard proof the gate makes about those
# words was a proof about a record no rule constrained. One trailing store
# republished a timed-out run as an observed one with the mailbox rules fully
# satisfied and the manifest byte-identical.
OBSERVATION_PRODUCER_MUTATIONS = (
    (
        "primary_result_overwritten_after_the_timeout_publication",
        _append_after(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    obs->result = V14_PRIMARY_OBSERVED;\n",
            "primary timeout result store",
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        "primary_qread_forged_before_the_result_overwrite",
        _append_after(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    obs->qread = qsize_expected;\n    obs->result = V14_PRIMARY_OBSERVED;\n",
            "primary timeout result store",
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        "observation_field_rewritten_through_an_obs_pointer_alias",
        _append_after(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    { struct v14_observation_t *rt_o = obs;"
            " rt_o->result = V14_PRIMARY_OBSERVED; }\n",
            "primary timeout result store",
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        "observation_field_written_through_a_field_pointer",
        _append_after(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    { uint32_t *rt_pr = &obs->result; *rt_pr = V14_PRIMARY_OBSERVED; }\n",
            "primary timeout result store",
        ),
        "takes the address of the observation field result",
    ),
    (
        "observation_field_written_by_memcpy",
        _append_after(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    { uint32_t rt_z = V14_PRIMARY_OBSERVED;"
            " memcpy(&obs->result, &rt_z, 4U); }\n",
            "primary timeout result store",
        ),
        "takes the address of the observation field result",
    ),
    # A count closes the store that is *added*. This is the store that is
    # *substituted*: one token, every count intact, and a timed-out run
    # publishes OBSERVED into appendix word 7.
    (
        "primary_timeout_result_substituted_for_observed",
        lambda vendor: replace_once(
            vendor,
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    obs->result = V14_PRIMARY_OBSERVED;\n",
            "primary timeout result store",
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        # And the value is compared as the number it folds to, so respelling it
        # is not a way around the table either.
        "primary_timeout_result_substituted_by_a_folded_spelling",
        lambda vendor: replace_once(
            vendor,
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    obs->result = V14_PRIMARY_OBSERVED + 0U;\n",
            "primary timeout result store",
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        "observation_producer_deleted_from_the_primary",
        lambda vendor: replace_once(
            vendor, "    obs->iterations = 0U;\n", "", "primary timeout iterations store"
        ),
        "not published by its authorized producers in v14_primary_q",
    ),
    (
        "observation_record_forged_by_an_added_helper",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                CONVERGE_MARKER,
                "\n__attribute__((noinline))\nstatic void v14_rt_forge(struct v14_observation_t *o)\n"
                "{\n    o->result = V14_PRIMARY_OBSERVED;\n}\n" + CONVERGE_MARKER,
                "converge marker",
            ),
            CONVERGE_CALL,
            CONVERGE_CALL + "\t  v14_rt_forge(&converged);\n",
            "converge call",
        ),
        "not published by its authorized producers in v14_rt_forge",
    ),
    (
        "observation_record_copied_whole_by_memcpy",
        _append_after(
            CONVERGE_CALL,
            "\t  { struct v14_observation_t rt_z = converged;"
            " memcpy(&converged, &rt_z, sizeof rt_z); }\n",
            "converge call",
        ),
        "reaches an observation record as whole storage",
    ),
    (
        "observation_field_forged_in_the_command_function",
        _append_after(
            CONVERGE_CALL,
            "\t  converged.result = V14_CONVERGENCE_SUCCESS;\n",
            "converge call",
        ),
        "not published by its authorized producers in test_commands",
    ),
)

# The convergence helper is shared by all three variants, so its half of the
# producer table is proven on the whole matrix rather than on the Q image alone.
CONVERGENCE_OBSERVATION_MUTATIONS = (
    (
        "convergence_result_overwritten_in_the_publication_tail",
        lambda vendor: replace_once(
            vendor,
            CONVERGE_OBSERVATION_TAIL,
            CONVERGE_OBSERVATION_TAIL[:-1]
            + "    obs->result = V14_CONVERGENCE_SUCCESS;\n}",
            "convergence observation tail",
        ),
        "not published by its authorized producers in v14_converge",
    ),
    (
        "convergence_qread_forged_in_the_publication_tail",
        lambda vendor: replace_once(
            vendor,
            CONVERGE_OBSERVATION_TAIL,
            CONVERGE_OBSERVATION_TAIL[:-1]
            + "    obs->qread = qsize_expected;\n}",
            "convergence observation tail",
        ),
        "not published by its authorized producers in v14_converge",
    ),
    (
        "convergence_result_substituted_for_success",
        lambda vendor: replace_once(
            vendor,
            CONVERGE_OBSERVATION_TAIL,
            CONVERGE_OBSERVATION_TAIL.replace(
                "obs->result = result;", "obs->result = V14_CONVERGENCE_SUCCESS;"
            ),
            "convergence observation tail",
        ),
        "not published by its authorized producers in v14_converge",
    ),
)

# A store is an operator and an lvalue, and the macro rule keyed on the
# operator. A macro whose body is the *lvalue* carries no operator at all: the
# ``=`` sits one token outside the replacement list, the invocation reads as an
# assignment to the macro's own name, and the store is dropped in silence.
CRITICAL_LVALUE_MACRO_MUTATIONS = (
    (
        "mailbox_word_rewritten_through_an_lvalue_macro",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "#define RT_CR_SLOT"
            " pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_RESULT]\n"
            "\t  RT_CR_SLOT = V14_CONVERGENCE_SUCCESS;\n",
            "primary publication call",
        ),
        "with contract storage in its replacement list",
    ),
    (
        "mailbox_array_named_by_an_lvalue_macro",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "#define RT_MB_ARR pmu_completion_visibility_v14_mailbox\n"
            "\t  RT_MB_ARR[V14_MBOX_CONVERGENCE_RESULT] = V14_CONVERGENCE_SUCCESS;\n",
            "primary publication call",
        ),
        "with contract storage in its replacement list",
    ),
    (
        "observation_field_named_by_an_lvalue_macro",
        _prepend_before(
            PRIMARY_TIMEOUT_RESULT_STORE,
            "#define RT_OBS_RESULT obs->result\n",
            "primary timeout result store",
        ),
        "with contract storage in its replacement list",
    ),
    (
        "mailbox_word_named_by_a_function_like_macro",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "#define RT_MB_AT(i) pmu_completion_visibility_v14_mailbox[i]\n"
            "\t  RT_MB_AT(V14_MBOX_CONVERGENCE_RESULT) = V14_CONVERGENCE_SUCCESS;\n",
            "primary publication call",
        ),
        "with contract storage in its replacement list",
    ),
    (
        "appendix_index_named_by_an_lvalue_macro",
        _append_after(
            PRIMARY_PUBLICATION_CALL,
            "#define RT_CR_IDX [V14_MBOX_CONVERGENCE_RESULT]\n"
            "\t  pmu_completion_visibility_v14_mailbox RT_CR_IDX = V14_CONVERGENCE_SUCCESS;\n",
            "primary publication call",
        ),
        "with contract storage in its replacement list",
    ),
)

RUNNER_CRITICAL_LVALUE_MACRO_MUTATIONS = (
    (
        "runner_record_field_named_by_an_lvalue_macro",
        _after_the_appendix_copy("#define RT_VID d.variant_id\n    RT_VID = 3U;\n"),
        "with contract storage in its replacement list",
    ),
)

# Recovering the statements of a source costs one walk of a statement per
# assignment in it, and flattening an initializer costs one read of it per
# nesting level. Both are quadratic in a construct an operator controls, so both
# carry a budget derived from the input -- and exceeding it is a named refusal,
# never a truncated statement list or an unbound name.
_BUDGET_DECLARATOR_CLAUSES = 200
_BUDGET_INITIALIZER_ELEMENTS = 1200
_BUDGET_INITIALIZER_DEPTH = 600

ANALYSIS_BUDGET_MUTATIONS = (
    (
        "declarator_list_wider_than_the_statement_walk",
        _at_file_scope(
            "static volatile uint32_t *const rt_w0 = 0, "
            + ", ".join(
                "*const rt_w%d = rt_w%d" % (index, index - 1)
                for index in range(1, _BUDGET_DECLARATOR_CLAUSES)
            )
            + ";"
        ),
        "did not settle within",
    ),
    (
        "initializer_wider_than_the_declarator_walk",
        _at_file_scope(
            "static volatile uint32_t *const rt_wide[1] = { "
            + ", ".join(["0"] * _BUDGET_INITIALIZER_ELEMENTS)
            + " };"
        ),
        "cannot resolve to one register",
    ),
    (
        "initializer_nested_deeper_than_the_declarator_walk",
        _at_file_scope(
            "static volatile uint32_t *const rt_deep[1] = "
            + "{" * _BUDGET_INITIALIZER_DEPTH
            + "0"
            + "}" * _BUDGET_INITIALIZER_DEPTH
            + ";"
        ),
        "cannot resolve to one register",
    ),
)

# The controls. Every rule above refuses a *specific* structure, and a rule that
# refuses the neighbouring legal one instead is a rule that has stopped saying
# anything. Each of these is conforming C the frozen contract permits.
REMEDIATION_CONTROLS = (
    (
        "a plain nested-brace pointer array bound to QREAD",
        _at_file_scope(
            "static volatile uint32_t *const rt_ok1[1][1] = {{"
            " (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD) }};"
        ),
    ),
    (
        "a short comma declarator list that binds no register",
        _at_file_scope("static uint32_t rt_ok2 = 0U, rt_ok3 = 1U, rt_ok4 = 2U;"),
    ),
    (
        "an initializer nested inside the declarator walk's budget",
        _at_file_scope("static const uint32_t rt_ok5[2][2] = {{0U, 1U}, {2U, 3U}};"),
    ),
    (
        # The producer table compares a value by the number it folds to, so a
        # respelling of the value the design already stores is still that value.
        "an authorized observation value written in a folded spelling",
        lambda vendor: replace_once(
            vendor,
            PRIMARY_TIMEOUT_RESULT_STORE,
            "    obs->result = (V14_PRIMARY_TIMEOUT) + 0U;\n",
            "primary timeout result store",
        ),
    ),
)

RUNNER_REMEDIATION_CONTROLS = (
    (
        "the address of a non-appendix record field after the copy",
        _after_the_appendix_copy("    memset(&d.hook_pmu_mmio_read_count, 0, 4U);\n"),
    ),
)


# ---------------------------------------------------------------------------
# a1208a3 red-team and acceptance-review blockers.
#
# Every mutation below was an ACCEPT against the a1208a3 gate and compiles as a
# C11 translation unit. They are grouped by the property each one falsifies:
#
#   * a running-path QSIZE or STATUS access reached through a helper or the ISR,
#     which the intraprocedural scan of ``test_commands`` never saw;
#   * an indirect call, which carries any effect -- a second submit, a second
#     register load -- past the statement-effect model and the measured loops;
#   * the appendix reached as whole storage, by ``memcpy``/``memset``/an escaped
#     address, which the resolved-lvalue producer table never saw;
#   * a CMD write between the submit and the convergence tail, which stops the
#     queue every later word claims to have measured;
#   * an appendix word published from a value the design does not give it, which
#     the site-and-count producer table never looked at;
#   * a publication call, a convergence classification or the runner's validity
#     handshake carrying a label the condition that produced it does not imply.
# ---------------------------------------------------------------------------

RT_PUBLISH_PRIMARY_FIRST_STORE = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_RESULT] = obs->result;"
)
RT_MAILBOX_PUBLISH_MAGIC = (
    "    __DSB();\n"
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID] = V14_MAILBOX_VALID;"
)
RT_ISR_STATUS_READ = "    status_register = read_reg(NPU_REG_STATUS);"
RT_PUBLISH_FAILURE_HEAD = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_QREAD]"
    " = V14_U32_INVALID;\n"
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_FINAL_STATUS]"
    " = V14_U32_INVALID;"
)
RT_PUBLISH_SUCCESS_HEAD = (
    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FAILURE_PHASE] = V14_PHASE_NONE;"
)
RT_PUBLISH_PRIMARY_CALL = "\t  v14_publish_primary(&primary, qsize_expected);"
RT_T_SUBMIT_AFTER = (
    "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;"
)
RT_T_PRIMARY_ENTRY = (
    "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_T_PRIMARY_ENTRY] = DWT->CYCCNT;"
)
RT_PUBLISH_PRIMARY_DEF = "__attribute__((noinline))\nstatic void v14_publish_primary("
RT_PUBLISH_SUCCESS_DEF = "__attribute__((noinline))\nstatic void v14_publish_success(void)"
RT_MAILBOX_DECL = "volatile uint32_t pmu_completion_visibility_v14_mailbox[34];"
RT_CONVERGE_READ_PAIR = "        qread = *qread_reg;\n        status = *status_reg;\n"
RT_CONVERGE_FAULT_BLOCK = (
    "        if ((status & V14_STATUS_FAULT_MASK) != 0U) {\n"
    "            result = V14_CONVERGENCE_FAULT;\n"
    "            break;\n"
    "        }"
)
RT_CONVERGE_RESET_BLOCK = (
    "        if ((status & V14_STATUS_RESET) != 0U) {\n"
    "            result = V14_CONVERGENCE_RESET;\n"
    "            break;\n"
    "        }"
)
RT_CONVERGE_ITERATIONS = (
    "            result = V14_CONVERGENCE_SUCCESS;\n            iterations = i;"
)
RT_CLEANUP_FAILURE_BRANCH = (
    "\t  if (ret_code != 0) {\n"
    "\t    v14_publish_cleanup_failure((uint32_t)read_val, converged.status);\n"
    "\t    ret_code = V14_RET_CLEANUP_INVARIANT;\n"
    "\t  }"
)
RT_PRIMARY_TIMEOUT_PUBLICATION = (
    "\t    v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_PRIMARY_TIMEOUT,"
    " primary.qread, primary.status);"
)
RT_CONVERGENCE_TIMEOUT_PUBLICATION = (
    "\t    v14_publish_failure(V14_PHASE_CONVERGENCE, V14_REASON_CONVERGENCE_TIMEOUT,"
    " converged.qread, converged.status);"
)


def _rt_after(anchor, statement, what):
    return _append_after(anchor, statement, what)


def _rt_before(anchor, statement, what):
    return _prepend_before(anchor, statement, what)


def _rt_swap(anchor, replacement, what):
    def mutate(text):
        return replace_once(text, anchor, replacement, what)

    return mutate


# --- running-path QSIZE reached through a callee or the ISR -----------------

RUNNING_PATH_QSIZE_MUTATIONS = (
    (
        "qsize_read_in_the_primary_publisher",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    (void)read_reg(NPU_REG_QSIZE);\n",
            "primary publisher head",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_read_in_the_mailbox_publisher",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    (void)read_reg(NPU_REG_QSIZE);\n",
            "mailbox publish barrier",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_read_in_the_npu_isr",
        _rt_after(
            RT_ISR_STATUS_READ,
            "\n    (void)read_reg(NPU_REG_QSIZE);",
            "isr status read",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_read_in_a_new_running_path_helper",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_PRIMARY_DEF,
                "__attribute__((noinline))\nstatic uint32_t v14_running_probe(void)\n"
                "{\n    return read_reg(NPU_REG_QSIZE);\n}\n\n" + RT_PUBLISH_PRIMARY_DEF,
                "primary publisher definition",
            ),
            RT_PUBLISH_PRIMARY_CALL,
            "\t  (void)v14_running_probe();\n" + RT_PUBLISH_PRIMARY_CALL,
            "primary publication call",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_read_in_the_failure_publisher",
        _rt_before(
            RT_PUBLISH_FAILURE_HEAD,
            "    (void)read_reg(NPU_REG_QSIZE);\n",
            "failure publisher head",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_read_in_the_success_publisher",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    (void)read_reg(NPU_REG_QSIZE);\n",
            "success publisher head",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "qsize_pointer_bound_in_the_primary_publisher",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    volatile uint32_t *const qsize_reg =\n"
            "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE);\n"
            "    (void)*qsize_reg;\n",
            "primary publisher head",
        ),
        "QSIZE is designated outside the queue setup",
    ),
    (
        "first_q_done_compared_against_a_running_qsize_read",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    volatile uint32_t *const qsize_reg =\n"
            "        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QSIZE);\n"
            "    (void)qsize_reg;\n",
            "primary publisher head",
        ),
        "QSIZE is designated outside the queue setup",
    ),
)

# --- other running-path MMIO reached through a callee -----------------------

RUNNING_PATH_STATUS_MUTATIONS = (
    (
        "extra_status_load_in_the_primary_publisher",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    (void)read_reg(NPU_REG_STATUS);\n",
            "primary publisher head",
        ),
        "STATUS is designated in a function the contract does not read it from",
    ),
    (
        "extra_status_load_in_the_success_publisher",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    (void)read_reg(NPU_REG_STATUS);\n",
            "success publisher head",
        ),
        "STATUS is designated in a function the contract does not read it from",
    ),
    (
        "extra_status_load_in_the_mailbox_publisher",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    (void)read_reg(NPU_REG_STATUS);\n",
            "mailbox publish barrier",
        ),
        "STATUS is designated in a function the contract does not read it from",
    ),
)

# --- indirect calls ---------------------------------------------------------

RT_HOOK_DECLARATION = (
    RT_MAILBOX_DECL
    + "\n\ntypedef void (*v14_hook_t)(void);\nextern v14_hook_t v14_hook;"
)

INDIRECT_CALL_MUTATIONS = (
    (
        "indirect_call_through_a_parenthesised_pointer_in_the_primary_loop",
        lambda vendor: replace_once(
            replace_once(
                vendor, RT_MAILBOX_DECL, RT_HOOK_DECLARATION, "mailbox declaration"
            ),
            Q_LOOP_READ_AND_GUARD,
            "        (*v14_hook)();\n" + Q_LOOP_READ_AND_GUARD,
            "Q primary loop read",
        ),
        "declares a function pointer",
    ),
    (
        "indirect_qsize_read_through_a_pointer_in_the_primary_loop",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_MAILBOX_DECL,
                RT_MAILBOX_DECL
                + "\n\n__attribute__((noinline))\nstatic void v14_tick(void)\n{\n"
                "    (void)read_reg(NPU_REG_QSIZE);\n}\n"
                "static void (*const v14_hook)(void) = v14_tick;",
                "mailbox declaration",
            ),
            Q_LOOP_READ_AND_GUARD,
            "        (*v14_hook)();\n" + Q_LOOP_READ_AND_GUARD,
            "Q primary loop read",
        ),
        "declares a function pointer",
    ),
    (
        "indirect_call_through_a_struct_member_in_the_primary_loop",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_MAILBOX_DECL,
                RT_MAILBOX_DECL
                + "\n\nstruct v14_ops_t { void (*tick)(void); };\nextern struct v14_ops_t v14_ops;",
                "mailbox declaration",
            ),
            Q_LOOP_READ_AND_GUARD,
            "        v14_ops.tick();\n" + Q_LOOP_READ_AND_GUARD,
            "Q primary loop read",
        ),
        "declares a function pointer",
    ),
    (
        "second_submit_written_through_a_function_pointer",
        _rt_after(
            SUBMIT_WRITE,
            "\t  void (*v14_wr)(uint32_t, uint32_t) = write_reg;\n"
            "\t  v14_wr(NPU_REG_CMD, 0x00000001);\n",
            "submit write",
        ),
        "declares a function pointer",
    ),
    (
        "second_submit_written_through_a_function_pointer_array",
        _rt_after(
            SUBMIT_WRITE,
            "\t  void (*v14_tab[1])(uint32_t, uint32_t) = { write_reg };\n"
            "\t  v14_tab[0](NPU_REG_CMD, 0x00000001);\n",
            "submit write",
        ),
        "declares a function pointer",
    ),
    (
        "second_pre_submit_status_load_through_a_function_pointer",
        _rt_before(
            SUBMIT_WRITE,
            "\t  uint32_t (*v14_rd)(uint32_t) = read_reg;\n"
            "\t  pre_submit_status = v14_rd(NPU_REG_STATUS);\n",
            "submit write",
        ),
        "declares a function pointer",
    ),
    (
        "second_qsize_load_through_a_function_pointer",
        _rt_before(
            SUBMIT_WRITE,
            "\t  uint32_t (*v14_rd)(uint32_t) = read_reg;\n"
            "\t  qsize_expected = v14_rd(NPU_REG_QSIZE);\n",
            "submit write",
        ),
        "declares a function pointer",
    ),
)

# --- the appendix reached as whole storage ---------------------------------

APPENDIX_STORAGE_CLOSURE_MUTATIONS = (
    (
        "appendix_word_forged_by_memcpy_inline",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    static const uint32_t f = V14_QSIZE_EXPECTED;\n"
            "    memcpy((void *)&pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_QREAD],"
            " &f, 4U);\n",
            "success publisher head",
        ),
        "takes the address of appendix word",
    ),
    (
        "appendix_address_handed_to_an_extern_sink",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    extern void v14_sink(volatile uint32_t *p);\n"
            "    v14_sink(&pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_QREAD]);\n",
            "success publisher head",
        ),
        "takes the address of appendix word",
    ),
    (
        "appendix_scrubbed_by_memset_inline",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    memset((void *)pmu_completion_visibility_v14_mailbox, 0xFF, 4U * 34U);\n",
            "success publisher head",
        ),
        "reaches the appendix as whole storage",
    ),
    (
        "appendix_forged_by_memcpy_from_a_helper",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_SUCCESS_DEF,
                "__attribute__((noinline))\nstatic void v14_fixup2(const uint32_t *src)\n{\n"
                "    memcpy((void *)&pmu_completion_visibility_v14_mailbox"
                "[V14_MBOX_FIRST_QREAD], src, 4U);\n}\n\n" + RT_PUBLISH_SUCCESS_DEF,
                "success publisher definition",
            ),
            RT_PUBLISH_SUCCESS_HEAD,
            "    static const uint32_t forged = V14_QSIZE_EXPECTED;\n"
            "    v14_fixup2(&forged);\n" + RT_PUBLISH_SUCCESS_HEAD,
            "success publisher head",
        ),
        "takes the address of appendix word",
    ),
    (
        "appendix_scrubbed_by_memset_from_a_helper",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_SUCCESS_DEF,
                "__attribute__((noinline))\nstatic void v14_scrub(void)\n{\n"
                "    memset((void *)pmu_completion_visibility_v14_mailbox, 0, 4U * 33U);\n}\n\n"
                + RT_PUBLISH_SUCCESS_DEF,
                "success publisher definition",
            ),
            RT_PUBLISH_SUCCESS_HEAD,
            "    v14_scrub();\n" + RT_PUBLISH_SUCCESS_HEAD,
            "success publisher head",
        ),
        "reaches the appendix as whole storage",
    ),
    (
        "mailbox_magic_forged_by_memcpy_from_a_helper",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_PRIMARY_DEF,
                "__attribute__((noinline))\nstatic void v14_forge(void)\n{\n"
                "    static const uint32_t m = V14_MAILBOX_VALID;\n"
                "    memcpy((void *)&pmu_completion_visibility_v14_mailbox[33], &m, 4U);\n}\n\n"
                + RT_PUBLISH_PRIMARY_DEF,
                "primary publisher definition",
            ),
            RT_T_SUBMIT_AFTER,
            "\t  v14_forge();\n" + RT_T_SUBMIT_AFTER,
            "submit timestamp",
        ),
        "takes the address of appendix word",
    ),
    (
        "mailbox_magic_forged_by_memcpy_inline_in_the_command_path",
        _rt_before(
            RT_T_SUBMIT_AFTER,
            "\t  static const uint32_t m = V14_MAILBOX_VALID;\n"
            "\t  memcpy((void *)&pmu_completion_visibility_v14_mailbox[33], &m, 4U);\n",
            "submit timestamp",
        ),
        "takes the address of appendix word",
    ),
    (
        "mailbox_magic_forged_by_memcpy_from_the_appendix_itself",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_PRIMARY_DEF,
                "__attribute__((noinline))\nstatic void v14_early(void)\n{\n"
                "    memcpy((void *)&pmu_completion_visibility_v14_mailbox[33],\n"
                "           (const void *)&pmu_completion_visibility_v14_mailbox[0], 4U);\n}\n\n"
                + RT_PUBLISH_PRIMARY_DEF,
                "primary publisher definition",
            ),
            RT_PUBLISH_PRIMARY_CALL,
            "\t  v14_early();\n" + RT_PUBLISH_PRIMARY_CALL,
            "primary publication call",
        ),
        "takes the address of appendix word",
    ),
    (
        "first_q_done_forged_by_memcpy_inline",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    static const uint32_t f = 1U;\n"
            "    memcpy((void *)&pmu_completion_visibility_v14_mailbox"
            "[V14_MBOX_FIRST_Q_DONE], &f, 4U);\n",
            "success publisher head",
        ),
        "takes the address of appendix word",
    ),
)

# --- CMD writes between the submit and the convergence tail -----------------

SUBMIT_WINDOW_CMD_MUTATIONS = (
    (
        "cmd_stop_written_immediately_after_the_submit",
        _rt_before(
            RT_T_SUBMIT_AFTER,
            "\t  write_reg(NPU_REG_CMD, 0x00000000);\n",
            "submit timestamp",
        ),
        "CMD write falls between the submit write and the convergence tail",
    ),
    (
        "extra_cmd_isr_clear_between_submit_and_convergence",
        _rt_before(
            RT_PUBLISH_PRIMARY_CALL,
            "\t  write_reg(NPU_REG_CMD, 0x00000002);\n",
            "primary publication call",
        ),
        "CMD write falls between the submit write and the convergence tail",
    ),
    (
        "cmd_stop_written_inline_before_the_primary_loop",
        _rt_after(
            RT_T_PRIMARY_ENTRY,
            "\n\t  write_reg(NPU_REG_CMD, 0x00000000);",
            "primary entry timestamp",
        ),
        "CMD write falls between the submit write and the convergence tail",
    ),
    (
        "cmd_stop_written_from_a_helper_before_the_primary_loop",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_PRIMARY_DEF,
                "__attribute__((noinline))\nstatic void v14_pre(void)\n{\n"
                "    write_reg(NPU_REG_CMD, 0x00000000);\n}\n\n" + RT_PUBLISH_PRIMARY_DEF,
                "primary publisher definition",
            ),
            RT_T_PRIMARY_ENTRY,
            RT_T_PRIMARY_ENTRY + "\n\t  v14_pre();",
            "primary entry timestamp",
        ),
        "CMD is written in a function the contract does not write it from",
    ),
    (
        "cmd_stop_written_from_the_primary_publisher",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    write_reg(NPU_REG_CMD, 0x00000000);\n",
            "primary publisher head",
        ),
        "CMD is written in a function the contract does not write it from",
    ),
)

# --- appendix value provenance ---------------------------------------------
#
# Transcribed from the design's appendix table: the expression each producer
# writes into each word. A store whose right-hand side is not the one named here
# publishes a number the diagnostic never measured.

APPENDIX_VALUE_SOURCES = (
    ("variant_id", "V14_VARIANT_ID"),
    ("qsize_expected", "qsize_expected"),
    ("pre_program_status", "pre_program_status"),
    ("pre_submit_status", "pre_submit_status"),
    ("t_submit_after_cmd", "DWT->CYCCNT"),
    ("t_primary_entry", "DWT->CYCCNT"),
    ("t_first_observation", "obs->t_first"),
    ("primary_result", "obs->result"),
    ("primary_iterations", "obs->iterations"),
    ("first_qread", "obs->qread"),
    ("first_status", "obs->status"),
    ("first_q_done", "(obs->qread == qsize_expected) ? 1U : 0U"),
    ("first_cmd_end_reached", "((obs->status & V14_STATUS_CMD_END) != 0U) ? 1U : 0U"),
    ("first_irq_raised", "((obs->status & V14_STATUS_IRQ_RAISED) != 0U) ? 1U : 0U"),
    ("first_state", "(obs->status & V14_STATUS_STATE)"),
    ("convergence_result", "converged.result"),
    ("convergence_iterations", "converged.iterations"),
    ("convergence_final_qread", "converged.qread"),
    ("convergence_final_status", "converged.status"),
    ("convergence_timeout", "(converged.result == V14_CONVERGENCE_TIMEOUT) ? 1U : 0U"),
    ("failure_phase", "phase"),
    ("failure_reason", "reason"),
    ("failure_qread", "qread"),
    ("failure_status", "status"),
    ("installed_vector", "NVIC_GetVector(NPU0_IRQn)"),
    ("nvic_enabled_before_submit", "NVIC_GetEnableIRQ(NPU0_IRQn)"),
    ("nvic_pending_after_initial_clear", "NVIC_GetPendingIRQ(NPU0_IRQn)"),
    ("nvic_active_before_submit", "NVIC_GetActive(NPU0_IRQn)"),
    ("irq_triggered_before_submit", "irq_triggered ? 1U : 0U"),
    ("nvic_pending_before_final_clear", "NVIC_GetPendingIRQ(NPU0_IRQn)"),
    ("nvic_pending_after_final_clear", "NVIC_GetPendingIRQ(NPU0_IRQn)"),
    ("nvic_active_after_cleanup", "NVIC_GetActive(NPU0_IRQn)"),
    ("irq_triggered_after_cleanup", "irq_triggered ? 1U : 0U"),
    ("mailbox_valid", "V14_MAILBOX_VALID"),
)

FORGED_CONSTANT = "0x41414141U"

_APPENDIX_STORE_RE = re.compile(
    r"pmu_completion_visibility_v14_mailbox\[(V14_MBOX_[A-Z0-9_]+)\]\s*=\s*[^;]*;"
)


def _forge_appendix_word(field):
    """Replace the *last* store to ``field`` with an attacker-chosen constant.

    The last one is the measured store wherever a word has both a sentinel and a
    measured producer, so the mutation lands on the value the host is meant to
    trust rather than on the ``V14_U32_INVALID`` beside it.
    """

    macro = mbox(field)

    def mutate(vendor):
        sites = [
            match
            for match in _APPENDIX_STORE_RE.finditer(vendor)
            if match.group(1) == macro
        ]
        if not sites:
            raise AssertionError("no store to %s in the canonical vendor" % macro)
        match = sites[-1]
        forged = "pmu_completion_visibility_v14_mailbox[%s] = %s;" % (macro, FORGED_CONSTANT)
        return vendor[: match.start()] + forged + vendor[match.end() :]

    return mutate


# Nine of the thirty-four forgeries are refused by an older, more specific rule
# before the value table is reached -- the variant-id binding, the success/failure
# exclusivity rule, the NVIC probe ordering and the magic-is-last rule. The
# property is closed either way; the fixture records which rule closes it rather
# than asserting a message the gate has no reason to prefer.
APPENDIX_VALUE_EARLIER_REFUSALS = {
    "variant_id": "mailbox word 0 does not publish V14_VARIANT_ID",
    "failure_phase": "success and failure tuples are both published as valid",
    "failure_qread": "success and failure tuples are both published as valid",
    "failure_status": "success and failure tuples are both published as valid",
    "installed_vector": "NVIC hard-bypass probe ordering drifted",
    "nvic_enabled_before_submit": "NVIC hard-bypass probe ordering drifted",
    "nvic_pending_after_initial_clear": "NVIC hard-bypass probe ordering drifted",
    "nvic_active_before_submit": "NVIC hard-bypass probe ordering drifted",
    "mailbox_valid": "mailbox magic is not the final appendix store",
}

APPENDIX_VALUE_MUTATIONS = tuple(
    (
        "appendix_word_%s_published_from_a_forged_constant" % field,
        _forge_appendix_word(field),
        APPENDIX_VALUE_EARLIER_REFUSALS.get(
            field, "is not published from the value the design gives it"
        ),
    )
    for field, _source in APPENDIX_VALUE_SOURCES
)

APPENDIX_VALUE_SHARP_MUTATIONS = (
    (
        "primary_result_republished_as_observed_by_a_constant",
        _rt_swap(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_PRIMARY_RESULT]"
            " = V14_PRIMARY_OBSERVED;",
            "primary result store",
        ),
        "is not published from the value the design gives it",
    ),
    (
        "first_status_published_from_the_wrong_observation_field",
        _rt_swap(
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = obs->status;",
            "    pmu_completion_visibility_v14_mailbox[V14_MBOX_FIRST_STATUS] = obs->qread;",
            "first status store",
        ),
        "is not published from the value the design gives it",
    ),
    (
        "convergence_timeout_flag_pinned_to_zero",
        _rt_swap(
            "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_TIMEOUT] =\n"
            "\t      (converged.result == V14_CONVERGENCE_TIMEOUT) ? 1U : 0U;",
            "\t  pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_TIMEOUT] = 0U;",
            "convergence timeout flag",
        ),
        "is not published from the value the design gives it",
    ),
)

# --- publication call sites -------------------------------------------------

PUBLICATION_CALL_MUTATIONS = (
    (
        "primary_timeout_published_with_reason_none",
        _rt_swap(
            RT_PRIMARY_TIMEOUT_PUBLICATION,
            "\t    v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_NONE,"
            " primary.qread, primary.status);",
            "primary timeout publication",
        ),
        "publication call does not carry the argument tuple the design gives it",
    ),
    (
        "primary_timeout_published_with_the_cleanup_phase",
        _rt_swap(
            RT_PRIMARY_TIMEOUT_PUBLICATION,
            "\t    v14_publish_failure(V14_PHASE_CLEANUP, V14_REASON_PRIMARY_TIMEOUT,"
            " primary.qread, primary.status);",
            "primary timeout publication",
        ),
        "publication call does not carry the argument tuple the design gives it",
    ),
    (
        "convergence_timeout_published_with_phase_none",
        _rt_swap(
            RT_CONVERGENCE_TIMEOUT_PUBLICATION,
            "\t    v14_publish_failure(V14_PHASE_NONE, V14_REASON_CONVERGENCE_TIMEOUT,"
            " converged.qread, converged.status);",
            "convergence timeout publication",
        ),
        "publication call does not carry the argument tuple the design gives it",
    ),
    (
        "cleanup_failure_branch_calls_the_success_publisher",
        _rt_swap(
            RT_CLEANUP_FAILURE_BRANCH,
            "\t  if (ret_code != 0) {\n"
            "\t    v14_publish_success();\n"
            "\t    ret_code = V14_RET_CLEANUP_INVARIANT;\n"
            "\t  }",
            "cleanup failure branch",
        ),
        "publication call does not carry the argument tuple the design gives it",
    ),
    (
        "cleanup_failure_branch_drops_the_failure_publication",
        _rt_swap(
            RT_CLEANUP_FAILURE_BRANCH,
            "\t  if (ret_code != 0) {\n"
            "\t    ret_code = V14_RET_CLEANUP_INVARIANT;\n"
            "\t  }",
            "cleanup failure branch",
        ),
        "publication call does not carry the argument tuple the design gives it",
    ),
    (
        "cleanup_failure_branch_returns_success",
        _rt_swap(
            RT_CLEANUP_FAILURE_BRANCH,
            "\t  if (ret_code != 0) {\n"
            "\t    v14_publish_cleanup_failure((uint32_t)read_val, converged.status);\n"
            "\t    ret_code = V14_RET_SUCCESS;\n"
            "\t  }",
            "cleanup failure branch",
        ),
        "the cleanup-failure branch does not land its own return code",
    ),
)

# --- the convergence tail held to the primary's standard --------------------

CONVERGENCE_CLASSIFICATION_MUTATIONS = (
    (
        "convergence_fault_relabelled_as_timeout",
        _rt_swap(
            RT_CONVERGE_FAULT_BLOCK,
            "        if ((status & V14_STATUS_FAULT_MASK) != 0U) {\n"
            "            result = V14_CONVERGENCE_TIMEOUT;\n"
            "            break;\n"
            "        }",
            "convergence fault guard",
        ),
        "convergence classifier does not bind",
    ),
    (
        "convergence_reset_relabelled_as_timeout",
        _rt_swap(
            RT_CONVERGE_RESET_BLOCK,
            "        if ((status & V14_STATUS_RESET) != 0U) {\n"
            "            result = V14_CONVERGENCE_TIMEOUT;\n"
            "            break;\n"
            "        }",
            "convergence reset guard",
        ),
        "convergence classifier does not bind",
    ),
    (
        "convergence_iterations_set_to_a_constant",
        _rt_swap(
            RT_CONVERGE_ITERATIONS,
            "            result = V14_CONVERGENCE_SUCCESS;\n            iterations = 1U;",
            "convergence success block",
        ),
        "convergence classifier does not bind",
    ),
)

CONVERGENCE_SAME_ITERATION_MUTATIONS = (
    (
        "convergence_status_published_from_the_previous_iteration",
        _rt_swap(
            RT_CONVERGE_READ_PAIR,
            "        uint32_t status_prev = status;\n"
            "        qread = *qread_reg;\n"
            "        status = *status_reg;\n"
            "        status = status_prev;\n",
            "convergence read pair",
        ),
        "convergence tuple is not the one the loop's own iteration read",
    ),
    (
        "convergence_qread_reassigned_after_its_load",
        _rt_swap(
            RT_CONVERGE_READ_PAIR,
            "        qread = *qread_reg;\n"
            "        status = *status_reg;\n"
            "        qread = qsize_expected;\n",
            "convergence read pair",
        ),
        "convergence tuple is not the one the loop's own iteration read",
    ),
)

# --- the runner's validity handshake ---------------------------------------

RUNNER_TRANSPORT_POLARITY_MUTATIONS = (
    (
        "runner_sets_transport_valid_on_an_invalid_magic",
        _rt_swap(
            RUNNER_MAGIC_GUARD_LINE + "        pmu_diag_v14_transport_valid = 0U;\n",
            RUNNER_MAGIC_GUARD_LINE + "        pmu_diag_v14_transport_valid = 1U;\n",
            "runner magic guard",
        ),
        "runner sets transport_valid on an invalid mailbox magic",
    ),
)

# --- controls: neighbouring legal sources still pass ------------------------

RT_REMEDIATION_CONTROLS = (
    (
        "the canonical pre-submit QSIZE snapshot and setup programming",
        lambda vendor: vendor,
    ),
    (
        "a non-MMIO helper called from the running path",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                RT_PUBLISH_PRIMARY_DEF,
                "__attribute__((noinline))\nstatic uint32_t v14_double(uint32_t v)\n"
                "{\n    return v + v;\n}\n\n" + RT_PUBLISH_PRIMARY_DEF,
                "primary publisher definition",
            ),
            RT_PUBLISH_PRIMARY_CALL,
            "\t  (void)v14_double(qsize_expected);\n" + RT_PUBLISH_PRIMARY_CALL,
            "primary publication call",
        ),
    ),
    (
        "a cast of a parenthesised expression, which is not an indirect call",
        _rt_before(
            RT_PUBLISH_SUCCESS_HEAD,
            "    volatile uint32_t sink = (uint32_t)(1U + 2U);\n    (void)sink;\n",
            "success publisher head",
        ),
    ),
)


# ---------------------------------------------------------------------------
# e6d0393 acceptance-review and red-team blockers.
#
# Every mutation below was an ACCEPT against the e6d0393 gate. They are grouped
# by the property each one falsifies:
#
#   * an NPU register designated through an object-like macro alias, which the
#     ``NPU_REG_*`` name scan cannot see because the ``#define`` that carries it
#     is blanked before the scan runs;
#   * an NPU register reached by numeric offset or absolute address from a
#     function the design does not name, which the address resolver never ran
#     over because it ran only inside contract-critical bodies;
#   * a QREAD write, or a CMD value written from the ISR that is not the
#     ISR-clear, which the confinement table authorised by owner without ever
#     reading the value;
#   * ``wait_for_irq`` actually called, which the STATUS exemption for it
#     assumed in a comment and never checked;
#   * a measured local stepped or read-modify-written, which the plain-assignment
#     walk skips by construction;
#   * a convergence category or iteration count carried in a declaration, which
#     the classifier proved only for the in-guard writes;
#   * a publication call whose ``)`` is not followed by ``;``, which the call
#     site walk skipped rather than refused;
#   * a second assignment to ``ret_code`` or ``transport_valid`` in an arm whose
#     first assignment the presence check already accepted;
#   * the runner's serialized record rewritten through a function pointer or
#     through the copy-out parameter, which the vendor-only indirect-call rule
#     and the ``&d`` address closure both leave open.
# ---------------------------------------------------------------------------

V14_CONVERGE_CALL = "\t  v14_converge(qsize_expected, &converged);"
V14_CONVERGE_LOCAL_DECLS = (
    "    uint32_t qread = 0U;\n"
    "    uint32_t status = 0U;\n"
    "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n"
    "    uint32_t iterations = 0U;\n"
)
V14_CONVERGE_TAIL = (
    "    obs->t_first = V14_U32_INVALID;\n    obs->result = result;\n"
)
V14_PRIMARY_STATUS_LOAD = (
    "    status = *status_reg;\n    obs->t_first = V14_U32_INVALID;\n"
)
V14_CLEANUP_SUCCESS_ARM = (
    "\t  else {\n"
    "\t    v14_publish_success();\n"
    "\t    ret_code = V14_RET_SUCCESS;\n"
    "\t  }"
)
V14_TEST_U85_TAIL = (
    "    ret_code = test_commands(eTest, u32CmdQueueSize, pu85_warp_data_st);\n"
)
RUNNER_COLLECT_HEAD = "void pmu_diag_collect_v14(pmu_diag_record_t *out)\n{\n"
RUNNER_RESET_HEAD = "void pmu_diag_reset_v14_state(void)\n"


def _with_macro_alias(name, register, statement, anchor, what):
    """Alias an ``NPU_REG_*`` name behind an object-like macro and use it."""

    def mutate(vendor):
        aliased = replace_once(
            vendor,
            RT_MAILBOX_DECL,
            "#define %s %s\n%s" % (name, register, RT_MAILBOX_DECL),
            "mailbox declaration",
        )
        return replace_once(aliased, anchor, statement + anchor, what)

    return mutate


def _with_helper(definition, call_anchor, call, what):
    """Define a helper above the primary publisher and call it from ``anchor``."""

    def mutate(vendor):
        defined = replace_once(
            vendor,
            RT_PUBLISH_PRIMARY_DEF,
            definition + RT_PUBLISH_PRIMARY_DEF,
            "primary publisher definition",
        )
        if call_anchor is None:
            return defined
        return replace_once(defined, call_anchor, call + call_anchor, what)

    return mutate


def _numeric_helper(name, body):
    return (
        "__attribute__((noinline))\nstatic void %s(void)\n{\n%s}\n\n" % (name, body)
    )


MACRO_ALIASED_CONFINEMENT_MUTATIONS = (
    (
        "running_qsize_load_through_an_object_like_macro_alias",
        _with_macro_alias(
            "QSEL_RUNNING",
            "NPU_REG_QSIZE",
            "    (void)read_reg(QSEL_RUNNING);\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "expands to an unexpanded MMIO designation",
    ),
    (
        "second_submit_through_an_object_like_macro_alias",
        _with_macro_alias(
            "CMDSEL_X",
            "NPU_REG_CMD",
            "    write_reg(CMDSEL_X, 0x00000001);\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "expands to an unexpanded MMIO designation",
    ),
    (
        "terminal_cmd_write_through_an_object_like_macro_alias",
        _with_macro_alias(
            "CMDSEL_Z",
            "NPU_REG_CMD",
            "    write_reg(CMDSEL_Z, 0x00000000);\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "expands to an unexpanded MMIO designation",
    ),
    (
        "qbase_reprogrammed_through_an_object_like_macro_alias",
        _with_macro_alias(
            "QBSEL",
            "NPU_REG_QBASE",
            "    write_reg(QBSEL, 0U);\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "expands to an unexpanded MMIO designation",
    ),
    (
        "isr_qsize_load_through_an_object_like_macro_alias",
        _with_macro_alias(
            "QSEL_ISR",
            "NPU_REG_QSIZE",
            "    (void)read_reg(QSEL_ISR);\n",
            RT_ISR_STATUS_READ,
            "isr status read",
        ),
        "expands to an unexpanded MMIO designation",
    ),
    (
        "running_qsize_load_through_a_function_like_macro_alias",
        _with_macro_alias(
            "SEL(x)",
            "NPU_REG_##x",
            "    (void)read_reg(SEL(QSIZE));\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "expands to an unexpanded MMIO designation",
    ),
)

NUMERIC_OFFSET_CONFINEMENT_MUTATIONS = (
    (
        "second_submit_through_a_numeric_offset_helper",
        _with_helper(
            _numeric_helper(
                "v14_resubmit",
                "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 1U;\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_resubmit();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "cmd_transition_through_a_numeric_offset_helper",
        _with_helper(
            _numeric_helper(
                "v14_transition",
                "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 2U;\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_transition();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "qbase_reprogrammed_through_a_numeric_offset_helper",
        _with_helper(
            _numeric_helper(
                "v14_rebase",
                "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x100U) = 0U;\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_rebase();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "running_qsize_load_through_a_numeric_offset_helper",
        _with_helper(
            _numeric_helper(
                "v14_probe_qsize",
                "    (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x104U);\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_probe_qsize();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "second_submit_through_an_absolute_address_helper",
        _with_helper(
            _numeric_helper(
                "v14_absolute_submit",
                "    *(volatile uint32_t *)0x50004000U = 1U;\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_absolute_submit();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "numeric_offset_write_through_folded_arithmetic",
        _with_helper(
            _numeric_helper(
                "v14_folded_write",
                "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x100U + 4U) = 3U;\n",
            ),
            V14_CONVERGE_CALL,
            "\t  v14_folded_write();\n",
            "convergence call",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "numeric_offset_helper_that_is_never_called",
        _with_helper(
            _numeric_helper(
                "v14_dead_submit",
                "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 1U;\n",
            ),
            None,
            "",
            "",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "numeric_offset_helper_called_from_the_primary_publisher",
        _with_helper(
            _numeric_helper(
                "v14_publisher_probe",
                "    (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x104U);\n",
            ),
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    v14_publisher_probe();\n",
            "primary publisher head",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "isr_qsize_load_through_a_numeric_offset",
        _rt_after(
            RT_ISR_STATUS_READ,
            "\n    (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x104U);",
            "isr status read",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
    (
        "numeric_offset_write_in_the_mailbox_publisher",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 1U;\n",
            "mailbox publish barrier",
        ),
        "reaches an NPU-region address this gate cannot resolve to one register",
    ),
)

QREAD_AND_ISR_VALUE_MUTATIONS = (
    (
        "qread_reset_written_from_the_primary_publisher",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    write_reg(NPU_REG_QREAD, 0U);\n",
            "primary publisher head",
        ),
        "QREAD is written",
    ),
    (
        "qread_reset_written_from_the_mailbox_publisher",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    write_reg(NPU_REG_QREAD, 0U);\n",
            "mailbox publish barrier",
        ),
        "QREAD is written",
    ),
    (
        "qread_reset_written_from_the_command_tail",
        _rt_before(
            V14_CONVERGE_CALL,
            "\t  write_reg(NPU_REG_QREAD, 0U);\n",
            "convergence call",
        ),
        "QREAD is written",
    ),
    (
        "second_submit_written_from_the_npu_isr",
        _rt_after(
            RT_ISR_STATUS_READ,
            "\n    write_reg(NPU_REG_CMD, 1);",
            "isr status read",
        ),
        "the interrupt handler writes CMD with a value the design does not give it",
    ),
    (
        "isr_cmd_clear_replaced_by_a_terminal_stop",
        _rt_swap(
            "        write_reg(NPU_REG_CMD, 2);\n",
            "        write_reg(NPU_REG_CMD, 0);\n",
            "isr cmd clear",
        ),
        "the interrupt handler writes CMD with a value the design does not give it",
    ),
    (
        "second_status_load_in_the_npu_isr",
        _rt_after(
            RT_ISR_STATUS_READ,
            "\n    status_register = read_reg(NPU_REG_STATUS);",
            "isr status read",
        ),
        "the interrupt handler loads STATUS",
    ),
)

RT_WAIT_FOR_IRQ_DEFINITION = (
    "__attribute__((noinline))\nstatic void wait_for_irq(void)\n"
    "{\n    (void)read_reg(NPU_REG_STATUS);\n}\n\n"
)
RT_WAIT_FOR_IRQ_SPIN_DEFINITION = (
    "__attribute__((noinline))\nstatic void wait_for_irq(void)\n"
    "{\n    for (uint32_t w = 0U; w < 10000U; ++w) {\n"
    "        if ((read_reg(NPU_REG_STATUS) & V14_STATUS_CMD_END) != 0U) {\n"
    "            break;\n        }\n    }\n}\n\n"
)

WAIT_FOR_IRQ_REACHABILITY_MUTATIONS = (
    (
        "wait_for_irq_called_from_the_command_path",
        _with_helper(
            RT_WAIT_FOR_IRQ_DEFINITION,
            RT_PUBLISH_PRIMARY_CALL,
            "\t  wait_for_irq();\n",
            "primary publication call",
        ),
        "wait_for_irq is called",
    ),
    (
        "wait_for_irq_spins_on_status_before_the_measured_publication",
        _with_helper(
            RT_WAIT_FOR_IRQ_SPIN_DEFINITION,
            RT_PUBLISH_PRIMARY_CALL,
            "\t  wait_for_irq();\n",
            "primary publication call",
        ),
        "wait_for_irq is called",
    ),
    (
        "wait_for_irq_called_from_the_mailbox_publisher",
        _with_helper(
            RT_WAIT_FOR_IRQ_DEFINITION,
            RT_MAILBOX_PUBLISH_MAGIC,
            "    wait_for_irq();\n",
            "mailbox publish barrier",
        ),
        "wait_for_irq is called",
    ),
)

MEASURED_LOCAL_STEP_MUTATIONS = (
    (
        "convergence_status_masked_by_a_compound_assignment",
        _rt_swap(
            RT_CONVERGE_READ_PAIR,
            RT_CONVERGE_READ_PAIR + "        status &= ~V14_STATUS_RESET;\n",
            "convergence read pair",
        ),
        "is stepped by a read-modify-write",
    ),
    (
        "convergence_qread_stepped_by_an_increment",
        _rt_swap(
            RT_CONVERGE_READ_PAIR,
            RT_CONVERGE_READ_PAIR + "        qread++;\n",
            "convergence read pair",
        ),
        "is stepped by a read-modify-write",
    ),
    (
        "convergence_status_restored_through_a_compound_xor",
        _rt_swap(
            RT_CONVERGE_READ_PAIR,
            "        uint32_t status_prev = status;\n"
            + RT_CONVERGE_READ_PAIR
            + "        status ^= (status ^ status_prev);\n",
            "convergence read pair",
        ),
        "is stepped by a read-modify-write",
    ),
    (
        "convergence_iterations_stepped_after_the_loop",
        _rt_before(
            V14_CONVERGE_TAIL,
            "    iterations += 1U;\n",
            "convergence publication tail",
        ),
        "is stepped by a read-modify-write",
    ),
    (
        "primary_status_forced_by_a_compound_or_before_publication",
        _rt_swap(
            V14_PRIMARY_STATUS_LOAD,
            "    status = *status_reg;\n"
            "    status |= V14_STATUS_CMD_END;\n"
            "    obs->t_first = V14_U32_INVALID;\n",
            "primary status load",
        ),
        "is stepped by a read-modify-write",
    ),
    (
        "primary_qread_stepped_after_the_measured_loop",
        _rt_swap(
            V14_PRIMARY_STATUS_LOAD,
            "    status = *status_reg;\n"
            "    qread--;\n"
            "    obs->t_first = V14_U32_INVALID;\n",
            "primary status load",
        ),
        "is stepped by a read-modify-write",
    ),
)

CONVERGENCE_DECLARATION_MUTATIONS = (
    (
        "convergence_result_initialised_to_success",
        _rt_swap(
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "    uint32_t result = V14_CONVERGENCE_SUCCESS;\n",
            "convergence result declaration",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_result_initialised_to_reset",
        _rt_swap(
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "    uint32_t result = V14_CONVERGENCE_RESET;\n",
            "convergence result declaration",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_result_initialised_to_a_folded_success",
        _rt_swap(
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT - 1U;\n",
            "convergence result declaration",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_iterations_initialised_to_one",
        _rt_swap(
            "    uint32_t iterations = 0U;\n",
            "    uint32_t iterations = 1U;\n",
            "convergence iterations declaration",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_result_and_iterations_forged_as_a_coherent_tuple",
        lambda vendor: replace_once(
            replace_once(
                vendor,
                "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
                "    uint32_t result = V14_CONVERGENCE_SUCCESS;\n",
                "convergence result declaration",
            ),
            "    uint32_t iterations = 0U;\n",
            "    uint32_t iterations = 1U;\n",
            "convergence iterations declaration",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_qread_and_status_seeded_to_converged_constants",
        _rt_swap(
            "    uint32_t qread = 0U;\n"
            "    uint32_t status = 0U;\n"
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "    uint32_t qread = V14_QSIZE_EXPECTED;\n"
            "    uint32_t status = V14_STATUS_CMD_END;\n"
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "convergence local declarations",
        ),
        "the convergence helper does not carry its terminal category in its declaration",
    ),
    (
        "convergence_result_assigned_success_before_the_publication",
        _rt_before(
            V14_CONVERGE_TAIL,
            "    result = V14_CONVERGENCE_SUCCESS;\n",
            "convergence publication tail",
        ),
        "the convergence helper assigns",
    ),
    (
        "convergence_iterations_assigned_after_the_loop",
        _rt_before(
            V14_CONVERGE_TAIL,
            "    iterations = 1U;\n",
            "convergence publication tail",
        ),
        "the convergence helper assigns",
    ),
)

PARENTHESISED_PUBLICATION_MUTATIONS = (
    (
        "publication_call_hidden_behind_a_cast_parenthesis",
        _rt_after(
            V14_TEST_U85_TAIL,
            "    (void)(v14_publish_failure(V14_PHASE_NONE, V14_REASON_NONE,"
            " V14_U32_INVALID, V14_U32_INVALID));\n",
            "test_u85 command call",
        ),
        "publication symbol appears outside a proven call site",
    ),
    (
        "publication_call_hidden_behind_redundant_parentheses",
        _rt_after(
            V14_TEST_U85_TAIL,
            "    (v14_publish_success());\n",
            "test_u85 command call",
        ),
        "publication symbol appears outside a proven call site",
    ),
    (
        "publication_call_hidden_inside_a_comma_expression",
        _rt_after(
            V14_TEST_U85_TAIL,
            "    (void)(0U, v14_publish_success());\n",
            "test_u85 command call",
        ),
        "publication symbol appears outside a proven call site",
    ),
)

CLEANUP_AND_TRANSPORT_EXCLUSIVITY_MUTATIONS = (
    (
        "cleanup_failure_arm_reassigns_the_success_return_code",
        _rt_swap(
            RT_CLEANUP_FAILURE_BRANCH,
            "\t  if (ret_code != 0) {\n"
            "\t    v14_publish_cleanup_failure((uint32_t)read_val, converged.status);\n"
            "\t    ret_code = V14_RET_CLEANUP_INVARIANT;\n"
            "\t    ret_code = V14_RET_SUCCESS;\n"
            "\t  }",
            "cleanup failure branch",
        ),
        "assigns ret_code more than once",
    ),
    (
        "cleanup_success_arm_reassigns_the_cleanup_return_code",
        _rt_swap(
            V14_CLEANUP_SUCCESS_ARM,
            "\t  else {\n"
            "\t    v14_publish_success();\n"
            "\t    ret_code = V14_RET_SUCCESS;\n"
            "\t    ret_code = V14_RET_CLEANUP_INVARIANT;\n"
            "\t  }",
            "cleanup success branch",
        ),
        "assigns ret_code more than once",
    ),
)

RUNNER_TRANSPORT_EXCLUSIVITY_MUTATIONS = (
    (
        "runner_reasserts_transport_valid_after_clearing_it",
        _rt_swap(
            RUNNER_MAGIC_GUARD_LINE + "        pmu_diag_v14_transport_valid = 0U;\n",
            RUNNER_MAGIC_GUARD_LINE
            + "        pmu_diag_v14_transport_valid = 0U;\n"
            + "        pmu_diag_v14_transport_valid = 1U;\n",
            "runner magic guard",
        ),
        "assigns pmu_diag_v14_transport_valid more than once",
    ),
)

RUNNER_DIAGNOSTIC_ESCAPE_MUTATIONS = (
    (
        "runner_record_rewritten_through_a_function_pointer_in_the_diagnostic",
        lambda runner: replace_once(
            replace_once(
                runner,
                RUNNER_COLLECT_HEAD,
                "static void v14_fill(pmu_diag_record_t *r)\n{\n"
                "    uint32_t *w = (uint32_t *)r;\n    w[2] = 3U;\n}\n\n"
                + RUNNER_COLLECT_HEAD
                + "    void (*fp)(pmu_diag_record_t *) = v14_fill;\n",
                "runner collect head",
            ),
            RUNNER_RECORD_CLOSURE_ANCHOR,
            RUNNER_RECORD_CLOSURE_ANCHOR + "    fp(out);\n",
            "runner record copy out",
        ),
        "declares a function pointer",
    ),
    (
        "runner_copy_out_pointer_handed_to_a_call",
        lambda runner: replace_once(
            replace_once(
                runner,
                RUNNER_COLLECT_HEAD,
                "static void v14_fill(pmu_diag_record_t *r)\n{\n"
                "    uint32_t *w = (uint32_t *)r;\n    w[2] = 3U;\n}\n\n" + RUNNER_COLLECT_HEAD,
                "runner collect head",
            ),
            RUNNER_RECORD_CLOSURE_ANCHOR,
            RUNNER_RECORD_CLOSURE_ANCHOR + "    v14_fill(out);\n",
            "runner record copy out",
        ),
        "hands the record copy-out pointer",
    ),
    (
        "runner_copy_out_pointer_address_escapes_the_diagnostic",
        lambda runner: replace_once(
            replace_once(
                runner,
                RUNNER_COLLECT_HEAD,
                "static void v14_sink(pmu_diag_record_t **r)\n{\n"
                "    uint32_t *w = (uint32_t *)(*r);\n    w[2] = 3U;\n}\n\n" + RUNNER_COLLECT_HEAD,
                "runner collect head",
            ),
            RUNNER_RECORD_CLOSURE_ANCHOR,
            RUNNER_RECORD_CLOSURE_ANCHOR + "    v14_sink(&out);\n",
            "runner record copy out",
        ),
        "hands the record copy-out pointer",
    ),
)

# --- a0fe0ab red-team blockers ---------------------------------------------
#
# The a0fe0ab review reproduced every fixture above and then walked around four
# of the rules they pin, by changing the *spelling* rather than the capability:
# the vendor accessor carries the register as an argument, so a numeric offset
# reaches CMD or QSIZE without ever spelling ``NPU_REG_``; ``wait_for_irq`` is
# reached from a macro instead of from a call site; and the cleanup return code
# and the transport flag are rewritten one statement past the arm each
# exclusivity rule reads.

RT_TOKEN_PASTE_ACCESSOR = "    (void)read_reg(SEL2(NPU_REG_,QSIZE));\n"


def _with_define_and_statement(define, statement, anchor, what):
    """Add a ``#define`` at the head of the unit and use it at ``anchor``."""

    def mutate(vendor):
        defined = replace_once(
            vendor, RT_MAILBOX_DECL, define + RT_MAILBOX_DECL, "mailbox declaration"
        )
        return replace_once(defined, anchor, statement + anchor, what)

    return mutate


ACCESSOR_OFFSET_CONFINEMENT_MUTATIONS = (
    (
        "running_qsize_load_through_a_bare_numeric_accessor_offset",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    (void)read_reg(0x108U);\n",
            "primary publisher head",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "second_submit_through_a_numeric_accessor_offset",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    write_reg(0x000U, 1U);\n",
            "primary publisher head",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "terminal_stop_through_a_numeric_accessor_offset",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    write_reg(0x000U, 0U);\n",
            "mailbox publish barrier",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "qread_rewound_through_a_numeric_accessor_offset",
        _rt_before(
            V14_CONVERGE_CALL,
            "\t  write_reg(0x104U, 0U);\n",
            "convergence call",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "isr_qsize_load_through_a_numeric_accessor_offset",
        _rt_after(
            RT_ISR_STATUS_READ,
            "\n    (void)read_reg(0x108U);",
            "isr status read",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "running_qsize_load_through_an_object_like_offset_macro",
        _with_define_and_statement(
            "#define QOFF_N 0x108U\n",
            "    (void)read_reg(QOFF_N);\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "running_qsize_load_through_a_token_paste_argument",
        _with_define_and_statement(
            "#define SEL2(a,b) a##b\n",
            RT_TOKEN_PASTE_ACCESSOR,
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
    (
        "accessor_offset_computed_from_the_designated_name",
        _rt_before(
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "    (void)read_reg(NPU_REG_QREAD + 4U);\n",
            "primary publisher head",
        ),
        "is called with a register offset this gate cannot resolve to one register",
    ),
)

RT_WAIT_FOR_IRQ_MACRO_CALL = "#define SETTLE() wait_for_irq()\n"
RT_WAIT_FOR_IRQ_MACRO_OBJECT = "#define SETTLE wait_for_irq()\n"
RT_WAIT_FOR_IRQ_MACRO_ALIAS = "#define SPIN wait_for_irq\n"


def _with_wait_for_irq_macro(define, statement, definition=None):
    """Define ``wait_for_irq``, alias it behind a macro, and reach it."""

    def mutate(vendor):
        defined = replace_once(
            vendor,
            RT_PUBLISH_PRIMARY_DEF,
            (definition or RT_WAIT_FOR_IRQ_SPIN_DEFINITION) + RT_PUBLISH_PRIMARY_DEF,
            "primary publisher definition",
        )
        aliased = replace_once(
            defined, RT_MAILBOX_DECL, define + RT_MAILBOX_DECL, "mailbox declaration"
        )
        return replace_once(
            aliased,
            RT_PUBLISH_PRIMARY_CALL,
            RT_PUBLISH_PRIMARY_CALL + statement,
            "primary publication call",
        )

    return mutate


WAIT_FOR_IRQ_MACRO_REACHABILITY_MUTATIONS = (
    (
        "wait_for_irq_reached_through_a_function_like_macro",
        _with_wait_for_irq_macro(RT_WAIT_FOR_IRQ_MACRO_CALL, "\n\t  SETTLE();"),
        "wait_for_irq is named outside its own definition",
    ),
    (
        "wait_for_irq_reached_through_an_object_like_macro",
        _with_wait_for_irq_macro(RT_WAIT_FOR_IRQ_MACRO_OBJECT, "\n\t  SETTLE;"),
        "wait_for_irq is named outside its own definition",
    ),
    (
        "wait_for_irq_reached_through_a_macro_that_aliases_its_name",
        _with_wait_for_irq_macro(RT_WAIT_FOR_IRQ_MACRO_ALIAS, "\n\t  SPIN();"),
        "wait_for_irq is named outside its own definition",
    ),
    (
        "wait_for_irq_address_taken_on_the_measured_path",
        _with_wait_for_irq_macro(
            "#define V14_SPARE_WORD 7U\n", "\n\t  (void)(&wait_for_irq);"
        ),
        "wait_for_irq is named outside its own definition",
    ),
)

CLEANUP_TAIL_EXCLUSIVITY_MUTATIONS = (
    (
        "cleanup_return_code_masked_to_success_after_the_epilogue",
        _rt_before(
            "\treturn ret_code;\n}",
            "\t  ret_code &= 0;\n",
            "command function return",
        ),
        "reaches ret_code through a read-modify-write",
    ),
    (
        "cleanup_return_code_zeroed_by_a_multiply_after_the_epilogue",
        _rt_before(
            "\treturn ret_code;\n}",
            "\t  ret_code *= 0;\n",
            "command function return",
        ),
        "reaches ret_code through a read-modify-write",
    ),
    (
        "cleanup_return_code_reassigned_to_success_after_the_epilogue",
        _rt_before(
            "\treturn ret_code;\n}",
            "\t  ret_code = V14_RET_SUCCESS;\n",
            "command function return",
        ),
        "the command function assigns ret_code",
    ),
    (
        "cleanup_return_code_stepped_before_the_epilogue",
        _rt_before(
            RT_CLEANUP_FAILURE_BRANCH,
            "\t  ret_code |= 1;\n",
            "cleanup failure branch",
        ),
        "reaches ret_code through a read-modify-write",
    ),
    # The command function's epilogue decides the code, and ``test_u85`` is what
    # returns it to the host. A store in *its* tail forges the same verdict one
    # frame further out, with every rule inside the command function satisfied.
    (
        "entry_return_code_masked_to_success_after_the_command_call",
        _rt_before(
            "    return ret_code;\n}",
            "    ret_code &= 0;\n",
            "entry function return",
        ),
        "reaches ret_code through a read-modify-write",
    ),
    (
        "entry_return_code_reassigned_after_the_command_call",
        _rt_before(
            "    return ret_code;\n}",
            "    ret_code = V14_RET_SUCCESS;\n",
            "entry function return",
        ),
        "the entry function assigns ret_code",
    ),
)

RUNNER_TRANSPORT_TAIL_EXCLUSIVITY_MUTATIONS = (
    (
        "runner_reasserts_transport_valid_after_the_magic_branch",
        _rt_before(
            RUNNER_RECORD_CLOSURE_ANCHOR,
            "    pmu_diag_v14_transport_valid = 1U;\n",
            "runner record copy out",
        ),
        "the runner assigns pmu_diag_v14_transport_valid",
    ),
    (
        "runner_sets_transport_valid_through_a_compound_or",
        _rt_before(
            RUNNER_RECORD_CLOSURE_ANCHOR,
            "    pmu_diag_v14_transport_valid |= 1U;\n",
            "runner record copy out",
        ),
        "reaches pmu_diag_v14_transport_valid through a read-modify-write",
    ),
    (
        "runner_steps_transport_valid_after_the_magic_branch",
        _rt_before(
            RUNNER_RECORD_CLOSURE_ANCHOR,
            "    pmu_diag_v14_transport_valid++;\n",
            "runner record copy out",
        ),
        "reaches pmu_diag_v14_transport_valid through a read-modify-write",
    ),
)

PUBLICATION_SYMBOL_ESCAPE_MUTATIONS = (
    (
        "publication_symbol_address_taken_on_the_measured_path",
        _rt_after(
            V14_TEST_U85_TAIL,
            "    (void)(&v14_publish_failure);\n",
            "test_u85 command call",
        ),
        "publication symbol appears outside a proven call site",
    ),
    (
        "publication_symbol_address_taken_in_the_mailbox_publisher",
        _rt_before(
            RT_MAILBOX_PUBLISH_MAGIC,
            "    (void)(&v14_publish_success);\n",
            "mailbox publish barrier",
        ),
        "publication symbol appears outside a proven call site",
    ),
    (
        "publication_symbol_bound_to_a_file_scope_name",
        _rt_before(
            RT_MAILBOX_DECL,
            "static void (*const v14_pub_alias)(void) = v14_publish_success;\n",
            "mailbox declaration",
        ),
        "declares a function pointer",
    ),
)

RUNNER_FILE_SCOPE_INDIRECTION_MUTATIONS = (
    (
        "runner_declares_a_function_pointer_at_file_scope",
        _rt_before(
            RUNNER_RESET_HEAD,
            "static void (*v14_hook)(void);\n\n",
            "runner reset definition",
        ),
        "declares a function pointer",
    ),
    (
        "runner_calls_a_file_scope_pointer_beside_the_mailbox_reset",
        lambda runner: replace_once(
            replace_once(
                runner,
                RUNNER_RESET_HEAD,
                "static void (*v14_hook)(void) = v14_mailbox_reset;\n\n" + RUNNER_RESET_HEAD,
                "runner reset definition",
            ),
            "    v14_mailbox_reset();\n",
            "    v14_mailbox_reset();\n    v14_hook();\n",
            "runner reset body",
        ),
        "declares a function pointer",
    ),
    (
        "runner_calls_through_a_file_scope_handler_table",
        lambda runner: replace_once(
            replace_once(
                runner,
                RUNNER_RESET_HEAD,
                "typedef void (*irq_handler_t)(void);\n"
                "static irq_handler_t v14_table[1];\n\n" + RUNNER_RESET_HEAD,
                "runner reset definition",
            ),
            "    v14_mailbox_reset();\n",
            "    v14_mailbox_reset();\n    v14_table[0]();\n",
            "runner reset body",
        ),
        "calls through a function pointer",
    ),
)


# --- controls: the neighbouring legal sources still pass --------------------

A0FE0AB_REMEDIATION_CONTROLS = (
    (
        "the design's own accessor calls, each naming the register it designates",
        lambda vendor: vendor,
    ),
    (
        "an object-like macro whose replacement list is an ordinary constant",
        _with_define_and_statement(
            "#define V14_SPARE_LIMIT 7U\n",
            "    irq_history_mask = irq_history_mask;\n",
            RT_PUBLISH_PRIMARY_FIRST_STORE,
            "primary publisher head",
        ),
    ),
    (
        "the stock wait_for_irq helper, defined and named nowhere else",
        _with_helper(RT_WAIT_FOR_IRQ_SPIN_DEFINITION, None, "", ""),
    ),
    (
        "a publication call statement written exactly as the design writes it",
        lambda vendor: vendor,
    ),
)

RUNNER_A0FE0AB_REMEDIATION_CONTROLS = (
    (
        "the stock host runner's file-scope irq_handler_t typedef and vector slot",
        _rt_before(
            RUNNER_RESET_HEAD,
            "typedef void (*irq_handler_t)(void);\nstatic irq_handler_t v14_vector_slot;\n\n",
            "runner reset definition",
        ),
    ),
    (
        "the runner's transport flag cleared and set exactly as the design does",
        lambda runner: runner,
    ),
)


E6_REMEDIATION_CONTROLS = (
    (
        "an object-like macro whose replacement list names no NPU register",
        lambda vendor: replace_once(
            vendor,
            RT_MAILBOX_DECL,
            "#define SPARE_WORD 7U\n" + RT_MAILBOX_DECL,
            "mailbox declaration",
        ),
    ),
    (
        "the stock wait_for_irq helper, defined and never called",
        _with_helper(RT_WAIT_FOR_IRQ_DEFINITION, None, "", ""),
    ),
    (
        "a helper that reaches no NPU address at all, called from the command path",
        _with_helper(
            "__attribute__((noinline))\nstatic void v14_note(void)\n"
            "{\n    irq_history_mask = irq_history_mask;\n}\n\n",
            V14_CONVERGE_CALL,
            "\t  v14_note();\n",
            "convergence call",
        ),
    ),
    (
        "the convergence terminal category spelled with redundant parentheses",
        _rt_swap(
            "    uint32_t result = V14_CONVERGENCE_TIMEOUT;\n",
            "    uint32_t result = (V14_CONVERGENCE_TIMEOUT);\n",
            "convergence result declaration",
        ),
    ),
    (
        "a non-publication call statement wrapped in a cast parenthesis",
        _rt_after(
            V14_TEST_U85_TAIL,
            "    (void)(NVIC_GetActive(NPU0_IRQn));\n",
            "test_u85 command call",
        ),
    ),
)

RUNNER_E6_REMEDIATION_CONTROLS = (
    (
        "the record copy-out pointer dereferenced exactly as the design writes it",
        lambda runner: runner,
    ),
)


def run_e6_remediation_suite(gate):
    """The e6d0393 acceptance and red-team blockers, each reproduced first."""

    run_vendor_mutations(gate, MACRO_ALIASED_CONFINEMENT_MUTATIONS, "Q")
    run_vendor_mutations(gate, NUMERIC_OFFSET_CONFINEMENT_MUTATIONS, "Q")
    run_vendor_mutations(gate, QREAD_AND_ISR_VALUE_MUTATIONS, "Q")
    run_vendor_mutations(gate, WAIT_FOR_IRQ_REACHABILITY_MUTATIONS, "Q")
    run_vendor_mutations(gate, MEASURED_LOCAL_STEP_MUTATIONS, "Q")
    run_vendor_mutations(gate, CONVERGENCE_DECLARATION_MUTATIONS, "Q")
    run_vendor_mutations(gate, PARENTHESISED_PUBLICATION_MUTATIONS, "Q")
    run_vendor_mutations(gate, CLEANUP_AND_TRANSPORT_EXCLUSIVITY_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_TRANSPORT_EXCLUSIVITY_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_DIAGNOSTIC_ESCAPE_MUTATIONS, "Q")

    # The properties a downstream reader would qualify an ELF against are proven
    # on the whole variant matrix, not only on the Q image the reports were
    # written against.
    for variant in ("QS", "SQ"):
        for label, mutate, reason in (
            MACRO_ALIASED_CONFINEMENT_MUTATIONS[0],
            NUMERIC_OFFSET_CONFINEMENT_MUTATIONS[0],
            QREAD_AND_ISR_VALUE_MUTATIONS[0],
            QREAD_AND_ISR_VALUE_MUTATIONS[3],
            WAIT_FOR_IRQ_REACHABILITY_MUTATIONS[0],
            CONVERGENCE_DECLARATION_MUTATIONS[0],
            PARENTHESISED_PUBLICATION_MUTATIONS[0],
            CLEANUP_AND_TRANSPORT_EXCLUSIVITY_MUTATIONS[0],
        ):
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                mutate(canonical_vendor(variant)),
                name,
                reason,
            )

    for label, mutate in E6_REMEDIATION_CONTROLS:
        expect_accept(
            gate,
            "Q",
            canonical_runner("Q"),
            mutate(canonical_vendor("Q")),
            "accepts %s" % label,
        )
    for label, mutate in RUNNER_E6_REMEDIATION_CONTROLS:
        expect_accept(
            gate,
            "Q",
            mutate(canonical_runner("Q")),
            canonical_vendor("Q"),
            "accepts %s" % label,
        )


def run_a0fe0ab_remediation_suite(gate):
    """The a0fe0ab red-team blockers, each reproduced before it was closed.

    Every one of these is a *sibling* of a fixture above: the same capability
    spelled so that the rule which refuses it never reads the tokens it matches
    on. They are kept as their own family because the property each one pins --
    "the accessor's argument is a designation this gate resolved", "the exempt
    IRQ helper is named nowhere but its own definition", "the return code and
    the transport flag are settled once" -- is a statement about the whole unit
    rather than about the statement the mutation happens to sit in.
    """

    run_vendor_mutations(gate, ACCESSOR_OFFSET_CONFINEMENT_MUTATIONS, "Q")
    run_vendor_mutations(gate, WAIT_FOR_IRQ_MACRO_REACHABILITY_MUTATIONS, "Q")
    run_vendor_mutations(gate, CLEANUP_TAIL_EXCLUSIVITY_MUTATIONS, "Q")
    run_vendor_mutations(gate, PUBLICATION_SYMBOL_ESCAPE_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_TRANSPORT_TAIL_EXCLUSIVITY_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_FILE_SCOPE_INDIRECTION_MUTATIONS, "Q")

    # Replayed on the other two variants, because the confinement scope the
    # manifest publishes is a claim about each generated unit and not about Q.
    for variant in ("QS", "SQ"):
        for label, mutate, reason in (
            ACCESSOR_OFFSET_CONFINEMENT_MUTATIONS[0],
            ACCESSOR_OFFSET_CONFINEMENT_MUTATIONS[1],
            WAIT_FOR_IRQ_MACRO_REACHABILITY_MUTATIONS[0],
            CLEANUP_TAIL_EXCLUSIVITY_MUTATIONS[0],
            PUBLICATION_SYMBOL_ESCAPE_MUTATIONS[0],
        ):
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                mutate(canonical_vendor(variant)),
                name,
                reason,
            )
        for label, mutate, reason in (
            RUNNER_TRANSPORT_TAIL_EXCLUSIVITY_MUTATIONS[0],
            RUNNER_FILE_SCOPE_INDIRECTION_MUTATIONS[0],
        ):
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate,
                variant,
                mutate(canonical_runner(variant)),
                canonical_vendor(variant),
                name,
                reason,
            )

    for label, mutate in A0FE0AB_REMEDIATION_CONTROLS:
        expect_accept(
            gate,
            "Q",
            canonical_runner("Q"),
            mutate(canonical_vendor("Q")),
            "accepts %s" % label,
        )
    for label, mutate in RUNNER_A0FE0AB_REMEDIATION_CONTROLS:
        expect_accept(
            gate,
            "Q",
            mutate(canonical_runner("Q")),
            canonical_vendor("Q"),
            "accepts %s" % label,
        )


def run_value_and_confinement_remediation_suite(gate):
    """The a1208a3 red-team and acceptance-review blockers, each reproduced first.

    Grouped by the property each mutation falsifies rather than by the report it
    came from, because several of them were found twice from different angles and
    a fixture named after a report is a fixture nobody can place later.
    """

    run_vendor_mutations(gate, RUNNING_PATH_QSIZE_MUTATIONS, "Q")
    run_vendor_mutations(gate, RUNNING_PATH_STATUS_MUTATIONS, "Q")
    run_vendor_mutations(gate, INDIRECT_CALL_MUTATIONS, "Q")
    run_vendor_mutations(gate, APPENDIX_STORAGE_CLOSURE_MUTATIONS, "Q")
    run_vendor_mutations(gate, SUBMIT_WINDOW_CMD_MUTATIONS, "Q")
    run_vendor_mutations(gate, APPENDIX_VALUE_MUTATIONS, "Q")
    run_vendor_mutations(gate, APPENDIX_VALUE_SHARP_MUTATIONS, "Q")
    run_vendor_mutations(gate, PUBLICATION_CALL_MUTATIONS, "Q")
    run_vendor_mutations(gate, CONVERGENCE_CLASSIFICATION_MUTATIONS, "Q")
    run_vendor_mutations(gate, CONVERGENCE_SAME_ITERATION_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_TRANSPORT_POLARITY_MUTATIONS, "Q")

    # The four properties a downstream reader would qualify an ELF against are
    # proven on the whole variant matrix, not only on the Q image the reports
    # were written against.
    for variant in ("QS", "SQ"):
        for label, mutate, reason in (
            RUNNING_PATH_QSIZE_MUTATIONS[0],
            APPENDIX_STORAGE_CLOSURE_MUTATIONS[6],
            SUBMIT_WINDOW_CMD_MUTATIONS[0],
            APPENDIX_VALUE_SHARP_MUTATIONS[0],
            CONVERGENCE_CLASSIFICATION_MUTATIONS[0],
        ):
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                mutate(canonical_vendor(variant)),
                name,
                reason,
            )

    for label, mutate in RT_REMEDIATION_CONTROLS:
        expect_accept(
            gate,
            "Q",
            canonical_runner("Q"),
            mutate(canonical_vendor("Q")),
            "accepts %s" % label,
        )


def run_source_gate_remediation_suite(gate):
    """The 7456670 acceptance and red-team blockers, each reproduced first."""

    run_vendor_mutations(gate, ALTERNATE_TOKEN_SPELLING_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_ALTERNATE_TOKEN_SPELLING_MUTATIONS, "Q")
    run_vendor_mutations(gate, DECLARATOR_INITIALIZER_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_RECORD_STORAGE_MUTATIONS, "Q")
    run_vendor_mutations(gate, OBSERVATION_PRODUCER_MUTATIONS, "Q")
    run_vendor_mutations(gate, CRITICAL_LVALUE_MACRO_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_CRITICAL_LVALUE_MACRO_MUTATIONS, "Q")
    run_vendor_mutations(gate, ANALYSIS_BUDGET_MUTATIONS, "Q")

    # The convergence helper and the digraph directive are variant-independent,
    # so they are proven on the whole matrix rather than on the Q image alone.
    for variant in ("Q", "QS", "SQ"):
        for label, mutate, reason in CONVERGENCE_OBSERVATION_MUTATIONS:
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate, variant, canonical_runner(variant),
                mutate(canonical_vendor(variant)), name, reason,
            )
    for variant in ("QS", "SQ"):
        name = "%s_contract_macro_repointed_by_a_digraph_directive" % variant.lower()
        REJECTED_FIXTURES.add(name)
        expect_reject(
            gate,
            variant,
            canonical_runner(variant),
            _repointed_for_the_translation_unit(
                _digraph_directive, "V14_MBOX_VARIANT_ID", "7U"
            )(canonical_vendor(variant)),
            name,
            "writes the digraph %:",
        )

    # And the controls: the neighbouring legal spellings still pass.
    for label, mutate in REMEDIATION_CONTROLS:
        expect_accept(
            gate, "Q", canonical_runner("Q"), mutate(canonical_vendor("Q")),
            "accepts %s" % label,
        )
    for label, mutate in RUNNER_REMEDIATION_CONTROLS:
        expect_accept(
            gate, "Q", mutate(canonical_runner("Q")), canonical_vendor("Q"),
            "accepts %s" % label,
        )


def run_acceptance_grammar_suite(gate):
    """The 96d5113 acceptance and red-team blockers, each reproduced first."""

    run_vendor_mutations(gate, LOGICAL_DIRECTIVE_LINE_MUTATIONS, "Q")
    run_vendor_mutations(gate, POINTER_ARRAY_ALIAS_MUTATIONS, "Q")
    run_vendor_mutations(gate, STATEMENT_MACRO_MUTATIONS, "Q")
    run_vendor_mutations(gate, IRQ_TRIGGERED_CAST_ALIAS_MUTATIONS, "Q")
    run_vendor_mutations(gate, SECOND_MAGIC_MUTATIONS, "Q")
    run_vendor_mutations(gate, APPENDIX_AUTHORIZED_PRODUCER_MUTATIONS, "Q")
    run_runner_mutations(gate, RUNNER_RECORD_ALIAS_MUTATIONS, "Q")

    # The two blockers that falsify a manifest key outright are proven on the
    # whole variant matrix, not only on the Q image they were reported against.
    for variant in ("QS", "SQ"):
        for label, mutate, reason in (
            (
                "second_magic_published_as_a_folded_sum",
                _prepend_before(
                    VARIANT_ID_STORE,
                    "    pmu_completion_visibility_v14_mailbox[V14_MBOX_MAILBOX_VALID]"
                    " = V14_MAILBOX_VALID + 0U;\n",
                    "variant id store",
                ),
                "mailbox_valid is published from more than one site",
            ),
            (
                "irq_triggered_aliased_through_a_cast_parenthesis",
                _append_after(
                    SUBMIT_WRITE,
                    "\t  { bool *trig_alias = (bool *)&irq_triggered;"
                    " *trig_alias = true; }\n",
                    "submit write",
                ),
                "irq_triggered can become true on a measured path",
            ),
        ):
            name = "%s_%s" % (variant.lower(), label)
            REJECTED_FIXTURES.add(name)
            expect_reject(
                gate,
                variant,
                canonical_runner(variant),
                mutate(canonical_vendor(variant)),
                name,
                reason,
            )


def run_coverage_suite():
    """The named negative fixtures the design demands are all present."""

    required = {
        "qsize_read_after_submit",
        "qsize_snapshot_before_final_programming",
        "pre_program_gate_missing",
        "pre_run_failure_reaches_submit",
        "q_primary_status_read",
        "qs_second_read_dropped",
        "sq_read_order_matches_qs",
        "primary_completion_uses_bit1",
        "primary_success_tuple_reread",
        "converge_cross_iteration_accumulation",
        "converge_predicate_missing_bit1",
        "converge_reset_delayed",
        "variant_specific_convergence_helper",
        "converge_per_loop_evidence_store",
        "failure_path_clears_npu",
        "history_from_status_reread",
        "success_cleanup_order_drift",
        "q_first_status_synthesized_from_convergence",
        "mailbox_magic_not_last",
        "mailbox_reset_valid_not_zeroed",
        "mailbox_magic_published_from_second_site",
        "runner_copy_before_magic_check",
        "cleanup_invariant_reported_as_convergence",
        "post_program_stale_cmd_end_gate_missing",
        "q_timeout_diagnostic_missing",
        "q_timeout_diagnostic_duplicated",
        "convergence_failure_discards_first_tuple",
        "success_publishes_failure_tuple",
        # Every forbidden effect, hidden behind the first guard of each loop.
        "q_primary_status_read_after_guard",
        "q_primary_qsize_read_after_guard",
        "q_primary_timestamp_after_guard",
        "q_primary_call_after_guard",
        "q_primary_evidence_store_after_guard",
        "primary_status_reload_after_guard",
        "primary_qsize_read_after_guard",
        "primary_timestamp_after_guard",
        "primary_call_after_guard",
        "primary_evidence_store_after_guard",
        "converge_status_reload_after_guard",
        "converge_qsize_read_after_guard",
        "converge_timestamp_after_guard",
        "converge_call_after_guard",
        "converge_evidence_store_after_guard",
        "converge_short_circuit_between_reads",
        # ...and every forbidden effect hidden *inside* a guard, where depth
        # alone used to buy an exemption no condition had earned.
        "q_primary_always_true_guard_call",
        "q_primary_always_true_guard_timestamp",
        "q_primary_always_true_guard_evidence_store",
        "q_primary_braceless_nested_call_in_guard",
        "q_primary_guard_reaches_back_edge",
        "primary_always_true_guard_call",
        "primary_always_true_guard_timestamp",
        "primary_always_true_guard_evidence_store",
        "primary_braceless_nested_call_in_guard",
        "primary_guard_reaches_back_edge",
        "converge_always_true_guard_call",
        "converge_always_true_guard_timestamp",
        "converge_always_true_guard_evidence_store",
        "converge_terminating_guard_evidence_store",
        "converge_braceless_nested_call_in_guard",
        "converge_guard_reaches_back_edge",
        # The Q post-timeout diagnostic classification, bit by bit.
        "q_timeout_reset_classification_missing",
        "q_timeout_fault_classification_missing",
        "q_timeout_fault_bit_bus_dropped",
        "q_timeout_fault_bit_cmd_parse_dropped",
        "q_timeout_fault_bit_ecc_dropped",
        "q_timeout_fault_bit_branch_dropped",
        # The qualified H-PRINTF seam, not any vendor printf.
        "cleanup_hprintf_debug_printf_only",
        "cleanup_hprintf_seam_marker_detached",
        "cleanup_hprintf_second_unmarked_callsite",
        # A comment opener written inside a literal is text, and must not blank
        # the executable code that follows it.
        "lexical_string_hides_nvic_enable",
        "lexical_string_hides_qsize_read",
        "lexical_string_hides_second_magic_store",
        # The loop head runs per iteration, and the bounded for must be alone.
        "primary_loop_head_carries_a_load",
        "primary_loop_head_carries_a_store",
        "primary_loop_head_carries_qsize",
        "primary_loop_head_observes_extra_state",
        "primary_extra_while_loop_after_the_bounded_for",
        "primary_braceless_while_loop_before_the_bounded_for",
        "converge_loop_head_carries_a_load",
        "converge_goto_back_edge_after_the_bounded_for",
        # An exempt guard has to be single-entry and structurally terminating.
        "primary_depth0_continue_reaches_the_back_edge",
        "primary_goto_enters_the_terminating_guard",
        "converge_goto_leaves_the_terminating_guard",
        # A second name for the same storage is the same storage.
        "primary_per_loop_store_through_an_obs_alias",
        "primary_status_read_through_a_raw_register_address",
        "first_tuple_stored_through_a_mailbox_alias",
        # Word 0 is what attributes the frame to a variant.
        "variant_id_define_is_another_variant",
        "variant_id_never_reaches_mailbox_word_0",
        "variant_id_word_0_is_hardcoded",
        "variant_id_published_to_the_wrong_word",
        "variant_id_published_through_a_mailbox_alias",
        # One magic publication, at word 33, in the frozen spelling.
        "magic_published_by_numeric_index_and_literal",
        "magic_published_through_a_mailbox_alias",
        "runner_copy_in_the_magic_invalid_branch",
        "runner_copy_ahead_of_the_magic_guard",
        "lexical_string_hides_runner_copy",
        # A named rejection, never a traceback.
        "queue_programming_without_a_qsize_write",
        "malformed_unread_v14_define",
        "malformed_qsize_expected_define",
        "malformed_iteration_bound_define",
        "malformed_appendix_offset_define",
        # The terminal cleanup writes live in a preprocessor branch.
        "test_cpm_branch_compiled_out",
        "test_cpm_guard_removed_from_the_terminal_sequence",
        # Reformatting is not a way past a rule.
        "nvic_enable_written_with_a_space",
        "nvic_enable_written_as_the_core_alias",
        "second_qsize_read_written_with_spaces",
        "cmd_write_before_programming_written_with_spaces",
        # A register is the register whatever name reaches it.
        "q_primary_status_read_through_an_alias",
        "qs_primary_status_reload_through_an_alias",
        "convergence_status_reload_through_an_alias",
        "primary_qsize_read_through_a_bare_offset",
        "convergence_qsize_pointer_through_a_bare_offset",
        "unknown_npu_region_pointer_in_the_primary_loop",
        "primary_pointer_rebound_to_two_registers",
        "qs_read_order_inverted_through_aliases",
        "sq_read_order_inverted_through_aliases",
        "convergence_read_order_inverted_through_aliases",
        "convergence_qsize_pointer_through_a_raw_address",
        "primary_qsize_read_through_a_raw_address",
        "running_qsize_read_through_a_raw_pointer",
        "raw_pointer_cmd_start_between_gate_and_programming",
        "second_submit_written_as_a_bare_one",
        "failure_path_clears_cmd_through_a_raw_pointer",
        "failure_path_prints_through_the_seam",
        "extra_cleanup_cmd2_written_as_a_bare_two",
        # A guard that cannot say what it found is a named rejection.
        "q_timeout_reset_and_fault_share_one_guard",
        # Naming the terms of a predicate is not deciding on them.
        "convergence_predicate_joined_with_or",
        "qs_convergence_predicate_joined_with_or",
        "sq_convergence_predicate_joined_with_or",
        "qs_primary_completion_joined_with_and",
        "sq_primary_completion_joined_with_and",
        "convergence_predicate_stopped_bit_inverted",
        # A gate is credited for the load it actually consumes.
        "pre_program_status_gated_on_a_constant",
        "post_program_status_gated_on_a_constant",
        "qsize_expected_taken_from_the_manifest_constant",
        "qsize_expected_overwritten_after_its_gate",
        "qsize_expected_reread_through_a_helper",
        # A source that pins no register map cannot write the number instead.
        "primary_status_read_through_a_numeric_address",
        "running_qsize_read_through_a_numeric_address",
        "second_submit_through_a_numeric_address",
        "failure_path_clears_cmd_through_a_numeric_address",
        "convergence_status_load_through_a_numeric_address",
        # A store is the storage its lvalue names, not the shape it is written in.
        "magic_published_through_pointer_arithmetic",
        "magic_published_through_a_reversed_subscript",
        "magic_published_through_a_reversed_addition",
        "magic_published_through_a_transitive_mailbox_alias",
        "mailbox_alias_repointed_by_a_compound_assignment",
        "mailbox_alias_repointed_by_an_increment",
        "variant_id_relabelled_through_pointer_arithmetic",
        "failure_publication_forges_the_convergence_tuple",
        "primary_per_loop_store_through_pointer_arithmetic",
        "runner_copy_ahead_of_the_guard_through_pointer_arithmetic",
        # A manifest field is what the verifier saw, so a false one is refused.
        "false_running_qsize_loads_in_test_commands_claim",
        "false_failure_paths_clear_npu_claim",
        "false_failure_paths_enter_hprintf_claim",
        "false_reachable_nvic_enable_sites_claim",
        "false_success_cleanup_order_claim",
        # The acceptance and red-team blockers. Each one was accepted before the
        # rule that names it existed.
        "mailbox_word_incremented_after_its_store",
        "mailbox_magic_cleared_after_publication",
        "mailbox_data_word_or_masked_after_its_store",
        "mailbox_word_incremented_through_an_alias",
        "mailbox_word_mutated_through_a_reversed_subscript",
        "observation_field_or_masked_before_publication",
        "runner_copies_every_appendix_field_from_word_zero",
        "runner_copies_the_appendix_in_reverse_word_order",
        "runner_copies_a_field_from_an_out_of_range_word",
        "runner_copies_a_field_from_an_unresolvable_word",
        "runner_copy_hidden_behind_a_preprocessor_directive",
        "failure_path_clears_cmd_immediately_before_publication",
        "failure_path_prints_immediately_before_publication",
        "primary_status_read_through_an_or_folded_address",
        "primary_status_read_through_an_and_masked_address",
        "primary_status_read_through_a_modulo_address",
        "primary_qsize_read_through_an_xor_address",
        "second_submit_through_an_or_folded_address",
        "numeric_npu_address_this_gate_cannot_fold",
        "npu_address_written_as_a_complement",
        "npu_address_selected_by_a_ternary",
        "npu_address_written_as_a_comparison",
        "macro_wrapped_mmio_in_the_command_path",
        "mmio_pointer_repointed_by_a_compound_assignment",
        "mmio_pointer_repointed_by_an_increment",
        "terminal_cmd_write_deleted_by_a_spliced_comment",
        "cleanup_nvic_clear_deleted_by_a_spliced_comment",
        "qs_extra_publishing_guard_after_the_completion_guard",
        "qs_extra_publishing_guard_before_the_completion_guard",
        "qs_extra_publishing_guard_spelled_else_if",
        "qs_reset_guard_repurposed_to_publish_observed",
        "sq_extra_publishing_guard_after_the_completion_guard",
        "sq_extra_publishing_guard_before_the_completion_guard",
        "sq_extra_publishing_guard_spelled_else_if",
        "sq_reset_guard_repurposed_to_publish_observed",
        "pre_submit_status_overwritten_through_a_dereferenced_lvalue",
        "pre_program_status_overwritten_through_a_dereferenced_lvalue",
        "raw_nvic_iser_enable_write",
        "irq_triggered_set_to_one_on_a_measured_path",
        "guard_nesting_deeper_than_the_gate_walks",
        # The acceptance grammar. A directive is a logical line, an address is
        # the storage it designates whatever declarator bound it, a macro body
        # is code, and every appendix word has the producers the design gives it.
        "contract_macro_repointed_by_a_spliced_directive",
        "contract_macro_repointed_by_a_form_feed_directive",
        "register_offset_macro_repointed_by_a_spliced_directive",
        "variant_id_macro_repointed_by_a_spliced_directive",
        "running_qsize_read_through_a_pointer_array_alias",
        "running_qsize_read_through_a_file_scope_pointer_array",
        "second_submit_through_a_pointer_array_alias",
        "nvic_iser_enable_through_a_pointer_array_alias",
        "terminal_cmd_write_repeated_through_a_pointer_array_alias",
        "mailbox_word_rewritten_through_a_pointer_array_alias",
        "irq_triggered_set_through_a_statement_macro",
        "mailbox_word_rewritten_through_a_statement_macro",
        "mmio_written_through_a_statement_macro",
        "irq_triggered_aliased_through_a_cast_parenthesis",
        "irq_triggered_aliased_through_a_void_cast_parenthesis",
        "irq_triggered_aliased_through_a_cast_in_an_uncovered_helper",
        "second_magic_published_as_a_folded_sum",
        "second_magic_published_as_a_parenthesised_macro",
        "second_magic_published_as_a_folded_disjunction",
        "second_magic_published_as_a_folded_product",
        "convergence_result_forged_from_a_second_store",
        "pre_submit_status_forged_from_a_second_store",
        "primary_result_forged_from_a_second_store",
        "failure_phase_forged_from_a_second_store",
        "installed_vector_forged_from_a_second_store",
        "convergence_timeout_forged_from_a_second_store",
        "first_state_producer_deleted_by_a_spliced_comment",
        "appendix_word_published_from_an_unauthorized_function",
        "runner_record_rewritten_through_a_parenthesised_address_of",
        "runner_record_rewritten_through_a_record_pointer_alias",
        "runner_record_read_modify_written_through_a_record_pointer_alias",
        "runner_record_rewritten_through_an_array_of_record_pointers",
        "runner_record_rewritten_through_a_statement_macro",
        "qs_second_magic_published_as_a_folded_sum",
        "sq_second_magic_published_as_a_folded_sum",
        "qs_irq_triggered_aliased_through_a_cast_parenthesis",
        "sq_irq_triggered_aliased_through_a_cast_parenthesis",
        # The 7456670 source-gate remediation. A punctuator has more than one
        # spelling, a declarator initializer is brace-matched rather than
        # pattern-matched, the observation record has the producer table the
        # mailbox has, the serialized record's storage is bounded rather than
        # only its lvalues, and a macro naming contract storage is refused on
        # the same terms as one carrying a store.
        "contract_macro_repointed_by_a_digraph_directive",
        "register_offset_macro_repointed_by_a_digraph_directive",
        "magic_macro_repointed_by_a_digraph_directive",
        "contract_macro_repointed_by_a_trigraph_directive",
        "digraph_directive_split_by_a_line_splice",
        "mailbox_word_rewritten_through_digraph_brackets",
        "block_braces_written_as_digraphs",
        "runner_contract_macro_repointed_by_a_digraph_directive",
        "runner_contract_macro_repointed_by_a_trigraph_directive",
        "qs_contract_macro_repointed_by_a_digraph_directive",
        "sq_contract_macro_repointed_by_a_digraph_directive",
        "running_qsize_read_through_a_nested_brace_pointer_array",
        "running_qsize_read_through_a_two_dimensional_pointer_array",
        "running_qsize_read_through_a_three_dimensional_pointer_array",
        "running_qsize_read_through_a_designated_nested_initializer",
        "running_qsize_read_through_a_comma_declarator_list",
        "running_qsize_read_through_a_three_declarator_comma_list",
        "primary_status_read_through_a_comma_declarator_list",
        "second_submit_through_a_two_dimensional_pointer_array",
        "terminal_cmd_write_repeated_through_a_nested_brace_pointer_array",
        "mailbox_word_rewritten_through_a_two_dimensional_pointer_array",
        "tail_qsize_write_through_a_two_dimensional_pointer_array",
        "tail_qsize_write_through_a_comma_declarator_list",
        "qsize_load_through_a_compound_literal_array",
        "qsize_load_through_a_compound_literal_scalar",
        "qsize_load_through_a_compound_literal_behind_an_address_of",
        "compound_literal_nested_in_a_declarator_initializer",
        "runner_record_field_written_through_a_field_pointer",
        "runner_record_appendix_wiped_by_memset",
        "runner_record_field_written_by_memcpy",
        "runner_record_field_pointer_bound_before_the_copy",
        "runner_record_written_through_a_byte_pointer_alias",
        "runner_record_written_through_a_subscripted_address",
        "runner_record_handed_to_a_call_after_the_copy",
        "runner_record_field_forged_inside_the_magic_branch",
        "runner_record_field_forged_in_the_branch_through_a_pointer_alias",
        "runner_record_field_forged_in_the_branch_through_an_array_of_aliases",
        "primary_result_overwritten_after_the_timeout_publication",
        "primary_qread_forged_before_the_result_overwrite",
        "primary_timeout_result_substituted_for_observed",
        "primary_timeout_result_substituted_by_a_folded_spelling",
        "q_convergence_result_substituted_for_success",
        "qs_convergence_result_substituted_for_success",
        "sq_convergence_result_substituted_for_success",
        "observation_field_rewritten_through_an_obs_pointer_alias",
        "observation_field_written_through_a_field_pointer",
        "observation_field_written_by_memcpy",
        "observation_producer_deleted_from_the_primary",
        "observation_record_forged_by_an_added_helper",
        "observation_record_copied_whole_by_memcpy",
        "observation_field_forged_in_the_command_function",
        "q_convergence_result_overwritten_in_the_publication_tail",
        "qs_convergence_result_overwritten_in_the_publication_tail",
        "sq_convergence_result_overwritten_in_the_publication_tail",
        "q_convergence_qread_forged_in_the_publication_tail",
        "qs_convergence_qread_forged_in_the_publication_tail",
        "sq_convergence_qread_forged_in_the_publication_tail",
        "mailbox_word_rewritten_through_an_lvalue_macro",
        "mailbox_array_named_by_an_lvalue_macro",
        "observation_field_named_by_an_lvalue_macro",
        "mailbox_word_named_by_a_function_like_macro",
        "appendix_index_named_by_an_lvalue_macro",
        "runner_record_field_named_by_an_lvalue_macro",
        "declarator_list_wider_than_the_statement_walk",
        "initializer_wider_than_the_declarator_walk",
        "initializer_nested_deeper_than_the_declarator_walk",
    }
    missing = sorted(required - REJECTED_FIXTURES)
    check("every design-mandated negative fixture is present", not missing, repr(missing))


# ---------------------------------------------------------------------------
# The zero-test trap
#
# This suite is a hand-rolled script: every fixture runs from the ``__main__``
# block below, and nothing in it is a ``unittest.TestCase`` or a module-level
# ``test_*`` function. ``python3 -m pytest`` and ``python3 -m unittest`` both
# therefore collect *nothing* from it and exit reporting success -- a green
# shell with zero assertions executed, which is indistinguishable in CI from a
# suite that ran and passed.
#
# The class below is the one collectable thing in the file. Under either
# collector it runs the script the only way that executes the fixtures, and
# fails unless the run reports the frozen count with no failures. So the two
# invocations that used to report a silent pass now report the real verdict,
# and a run that executes no fixture at all cannot be mistaken for a run that
# executed all of them.
# ---------------------------------------------------------------------------


class DirectSuiteExecution(unittest.TestCase):
    """Run the suite the way it has to be run, and pin its fixture count."""

    def test_the_v14_contract_suite_runs_every_frozen_fixture(self):
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True,
            text=True,
        )
        tail = (result.stdout[-4000:] + result.stderr[-2000:]).strip()
        self.assertEqual(result.returncode, 0, tail)
        self.assertIn("passed=%d failed=0" % EXPECTED_PASS_COUNT, result.stdout, tail)


if __name__ == "__main__":
    try:
        import check_pmu_completion_visibility_v14 as gate
    except Exception as exc:  # pragma: no cover - RED path
        check("checker module imports", False, repr(exc))
        gate = None

    if gate is not None:
        run_identity_suite(gate)
        run_cli_suite()
        run_canonical_suite(gate)
        run_pre_run_suite(gate)
        run_primary_positive_suite(gate)
        run_primary_suite(gate)
        run_cross_variant_suite(gate)
        run_convergence_suite(gate)
        run_fail_open_suite(gate)
        run_structural_matching_suite(gate)
        run_mmio_provenance_suite(gate)
        run_predicate_and_provenance_suite(gate)
        run_manifest_evidence_suite(gate)
        run_reviewer_blocker_suite(gate)
        run_final_blocker_suite(gate)
        run_acceptance_grammar_suite(gate)
        run_source_gate_remediation_suite(gate)
        run_value_and_confinement_remediation_suite(gate)
        run_e6_remediation_suite(gate)
        run_a0fe0ab_remediation_suite(gate)
        run_coverage_suite()

    try:
        import patches.patch_pmu_completion_visibility_v14 as patcher
    except Exception as exc:  # pragma: no cover - RED path
        check("generator module not found", False, repr(exc))
        patcher = None

    if patcher is not None:
        run_generator_cli_suite()
        run_fail_closed_cli_suite(patcher)
        run_encoding_cli_suite(patcher)
        if gate is not None:
            run_generator_suite(gate, patcher)
            run_generated_fixture_cli_suite(patcher)

    check(
        "the suite executed fixtures rather than collecting none",
        passed + failed > 0,
        "passed=%d failed=%d" % (passed, failed),
    )
    check(
        "the frozen fixture count is unchanged",
        passed + 1 == EXPECTED_PASS_COUNT,
        "passed=%d expected=%d" % (passed + 1, EXPECTED_PASS_COUNT),
    )

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
