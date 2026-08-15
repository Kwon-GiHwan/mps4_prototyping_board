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
EXPECTED_PASS_COUNT = 322

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

def run_fail_open_suite(gate):
    run_vendor_mutations(gate, LEXICAL_VENDOR_MUTATIONS, "Q")


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
    }
    missing = sorted(required - REJECTED_FIXTURES)
    check("every design-mandated negative fixture is present", not missing, repr(missing))


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
        run_coverage_suite()

    try:
        import patches.patch_pmu_completion_visibility_v14 as patcher
    except Exception as exc:  # pragma: no cover - RED path
        check("generator module not found", False, repr(exc))
        patcher = None

    if patcher is not None:
        run_generator_cli_suite()
        if gate is not None:
            run_generator_suite(gate, patcher)
            run_generated_fixture_cli_suite(patcher)

    check(
        "the frozen fixture count is unchanged",
        passed + 1 == EXPECTED_PASS_COUNT,
        "passed=%d expected=%d" % (passed + 1, EXPECTED_PASS_COUNT),
    )

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
