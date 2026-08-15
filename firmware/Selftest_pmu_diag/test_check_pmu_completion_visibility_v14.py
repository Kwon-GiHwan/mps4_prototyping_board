"""Firmware contract tests for PMU_COMPLETION_VISIBILITY_DIAG_V14.

The suite is self-contained: every schema constant, appendix offset and enum
value below is transcribed from the approved design rather than imported from
the gate, so a gate constant drifting away from the design is a test failure
instead of a silent agreement.
"""

import os
import subprocess
import sys

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


def runner_record_block():
    body = "\n".join("    uint32_t %s;" % field for field in APPENDIX_FIELDS)
    return "typedef struct {\n%s\n} pmu_diag_record_t;\n" % body


def runner_reset_block():
    return """
void pmu_diag_reset_v14_state(void)
{
    v14_mailbox_reset();
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
    pmu_diag_private_driver_call();
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
    lines = "\n".join("    put32(&c, d->%s);" % field for field in APPENDIX_FIELDS)
    return """
void pmu_diag_serialize_v14(const pmu_diag_record_t *d, uint8_t *c)
{
%s
}
""" % lines


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


def run_pre_run_suite(gate):
    run_vendor_mutations(gate, PRE_RUN_MUTATIONS)


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

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
