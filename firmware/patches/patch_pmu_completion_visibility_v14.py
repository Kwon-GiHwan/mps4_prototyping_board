"""Generate PMU_COMPLETION_VISIBILITY_DIAG_V14 Q/QS/SQ sources from frozen inputs.

The generator owns no anchors of its own: every replacement site is one of the
exact-one anchors already frozen by ``patch_pmu_completion_poll_v12``, and any
site that does not match exactly once is a hard failure. The three variants
differ only in the primary observation helper they emit and call; the common
convergence tail, the failure mailbox and the stock cleanup are byte-identical
across them, which is what lets the checker compare their digests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patches import patch_pmu_completion_poll_v12 as v12

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
SCHEMA_VERSION = 14
BUILD_ID = 0x34314950

VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}

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

MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"
MAILBOX_RESET_SYMBOL = "v14_mailbox_reset"
CONVERGE_SYMBOL = "v14_converge"
PRIMARY_SYMBOL = {"Q": "v14_primary_q", "QS": "v14_primary_qs", "SQ": "v14_primary_sq"}

APPENDIX_WORDS = len(APPENDIX_FIELDS)
BODY_WORDS = 85 + APPENDIX_WORDS
TOTAL_WORDS = 8 + BODY_WORDS
PAYLOAD_BYTES = TOTAL_WORDS * 4


class PatchError(SystemExit):
    pass


def fail(message: str) -> PatchError:
    return PatchError("FAIL %s" % message)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sub_once(text: str, old: str, new: str, what: str) -> tuple[str, int]:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1), count


def _require_variant(variant: str) -> int:
    if variant not in VARIANTS:
        raise fail("unknown variant %r: expected one of Q, QS, SQ" % variant)
    return VARIANTS[variant]


def _mbox(field: str) -> str:
    return "V14_MBOX_" + field.upper()


# ---------------------------------------------------------------------------
# Vendor blocks
# ---------------------------------------------------------------------------


def _vendor_defs(variant: str) -> str:
    offsets = "\n".join("#define %s %dU" % (_mbox(field), index) for index, field in enumerate(APPENDIX_FIELDS))
    returns = "\n".join("#define V14_RET_%s %d" % (name, value) for name, value in sorted(VENDOR_RETURN.items(), key=lambda item: item[1]))
    return """%s

#define V14_VARIANT_ID %dU
#define V14_U32_INVALID 0xFFFFFFFFU
#define V14_MAILBOX_VALID 0x5631344DU
#define V14_QSIZE_EXPECTED 0x00000110U
#define V14_ITERATION_BOUND 10000U
#define V14_APPENDIX_WORDS %dU

#define V14_STATUS_STATE 0x001U
#define V14_STATUS_IRQ_RAISED 0x002U
#define V14_STATUS_RESET 0x008U
#define V14_STATUS_CMD_END 0x020U
#define V14_STATUS_FAULT_MASK 0x314U

%s

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

%s

volatile uint32_t %s[%d];

struct v14_observation_t {
    uint32_t result;
    uint32_t iterations;
    uint32_t qread;
    uint32_t status;
    uint32_t t_first;
};

void %s(void);
static void v14_mailbox_publish(void);
static void v14_publish_failure(uint32_t phase, uint32_t reason, uint32_t qread, uint32_t status);
static void v14_publish_cleanup_failure(uint32_t qread, uint32_t status);
static void v14_publish_success(void);
static void v14_publish_primary(const struct v14_observation_t *obs, uint32_t qsize_expected);
static void %s(uint32_t qsize_expected, struct v14_observation_t *obs);
static void %s(uint32_t qsize_expected, struct v14_observation_t *obs);""" % (
        v12._VENDOR_DEFS_ANCHOR,
        _require_variant(variant),
        APPENDIX_WORDS,
        offsets,
        returns,
        MAILBOX_SYMBOL,
        APPENDIX_WORDS,
        MAILBOX_RESET_SYMBOL,
        PRIMARY_SYMBOL[variant],
        CONVERGE_SYMBOL,
    )


_MAILBOX_HELPERS = """__attribute__((noinline))
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

_PRIMARY_Q = """__attribute__((noinline))
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

_PRIMARY_DUAL = """__attribute__((noinline))
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

_DUAL_READS = {
    "QS": "        qread = *qread_reg;\n        status = *status_reg;",
    "SQ": "        status = *status_reg;\n        qread = *qread_reg;",
}

_CONVERGE = """__attribute__((noinline))
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


def _vendor_helpers(variant: str) -> str:
    if variant == "Q":
        primary = _PRIMARY_Q
    else:
        primary = _PRIMARY_DUAL % {"suffix": variant.lower(), "reads": _DUAL_READS[variant]}
    return "%s\n%s\n%s\n%s" % (_MAILBOX_HELPERS, primary, _CONVERGE, v12._VENDOR_HELPER_ANCHOR)


_VENDOR_LOCALS_V14 = """\tint ret_code;
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
"""

_VENDOR_ENABLE_V14 = """    irq_triggered = false;
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

    {
        uint32_t pre_program_status = read_reg(NPU_REG_STATUS);

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
    }
"""

_VENDOR_COMMAND_V14 = """\t  qsize_expected = read_reg(NPU_REG_QSIZE);
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
\t  }"""


def patch_vendor(text: str, variant: str) -> tuple[str, dict[str, int]]:
    _require_variant(variant)
    text = normalize_newlines(text)
    for marker, what in (
        ("v12_poll_completion(void)", "V12 helper"),
        ("v13_poll_completion(void)", "V13 helper"),
        ("pmu_interval_v11a_", "V11-A marker"),
        (MAILBOX_SYMBOL, "V14 mailbox"),
    ):
        if marker in text:
            raise fail("vendor input already carries the %s" % what)

    counts: dict[str, int] = {}
    text, counts["global_defs"] = sub_once(
        text, v12._VENDOR_DEFS_ANCHOR, _vendor_defs(variant), "vendor V14 globals anchor"
    )
    text, counts["helper_insert"] = sub_once(
        text, v12._VENDOR_HELPER_ANCHOR, _vendor_helpers(variant), "vendor V14 helper insertion"
    )
    text, counts["command_locals"] = sub_once(
        text, v12._VENDOR_LOCALS_STOCK, _VENDOR_LOCALS_V14, "vendor V14 command locals"
    )
    text, counts["runtime_enable_site"] = sub_once(
        text, v12._VENDOR_ENABLE_STOCK, _VENDOR_ENABLE_V14, "vendor V14 NVIC hard-bypass start block"
    )
    text, counts["command_wait_block"] = sub_once(
        text,
        v12._VENDOR_COMMAND_STOCK,
        _VENDOR_COMMAND_V14.replace("%(primary_call)s", PRIMARY_SYMBOL[variant]),
        "vendor V14 observation command block",
    )
    return text, counts


# ---------------------------------------------------------------------------
# Runner blocks
# ---------------------------------------------------------------------------

_RUNNER_SCHEMA_V14 = """#if defined(PMU_QUAL_SCHEMA_V14)
#define PMU_DIAG_SCHEMA_VERSION 14U
#define PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID 0x34314950U
#define V14_MAILBOX_VALID 0x5631344DU
#define V14_APPENDIX_WORDS 34U
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif"""

_RUNNER_EXTERN_V14 = """static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
#if defined(PMU_QUAL_SCHEMA_V14)
extern volatile uint32_t pmu_completion_visibility_v14_mailbox[34];
extern void v14_mailbox_reset(void);
static volatile uint32_t pmu_diag_v14_transport_valid;
#endif
"""

_RUNNER_FIELD_COUNT_V14 = """#if defined(PMU_QUAL_SCHEMA_V14)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 34U)
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif"""

_RUNNER_ASSERTS_V14 = """#if defined(PMU_QUAL_SCHEMA_V14)
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V14: snapshot must remain 8 words");
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
#elif defined(PMU_QUAL_SCHEMA_V8)
""" + v12._RUNNER_ASSERTS_STOCK[len("#if defined(PMU_QUAL_SCHEMA_V8)\n") :]

_RUNNER_PRIVATE_DRIVER_SEAM_V14 = """#if (defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)) && !defined(PMU_QUAL_SCHEMA_V14)
#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)
#error "PMU_DIAG: S1/S2 must link the reference vendor u85.c"
#endif
#endif"""

_RUNNER_PRIVATE_DRIVER_V14 = """#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_QUAL_SCHEMA_V14)
#error "PMU_QUAL: schema v8 must link the reference vendor u85.c"
#endif"""

_RUNNER_CLEAR_V14 = v12._RUNNER_CLEAR_STOCK + """#if defined(PMU_QUAL_SCHEMA_V14)
    v14_mailbox_reset();
    pmu_diag_v14_transport_valid = 0U;
#endif
"""


def _runner_record_v14() -> str:
    fields = "\n".join("    uint32_t %s;" % field for field in APPENDIX_FIELDS)
    return """    pmu_diag_snapshot_t internal_pre_release;
    pmu_diag_snapshot_t internal_post_disable;
    pmu_diag_snapshot_t after_return;
#if defined(PMU_QUAL_SCHEMA_V14)
%s
#endif
#else
    pmu_diag_snapshot_t post;         /* after call, BEFORE disable         */
    pmu_diag_snapshot_t post_disable; /* after disable + DSB + readback     */
#endif""" % fields


def _runner_copy_v14() -> str:
    copies = "\n".join(
        "            d.%s = pmu_completion_visibility_v14_mailbox[%d];" % (field, index)
        for index, field in enumerate(APPENDIX_FIELDS)
    )
    return """        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;
        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;
        d.internal_pre_release          = pmu_qual_internal_pre_release;
        d.internal_post_disable         = pmu_qual_internal_post_disable;
#if defined(PMU_QUAL_SCHEMA_V14)
        if (pmu_completion_visibility_v14_mailbox[33] != V14_MAILBOX_VALID) {
            pmu_diag_v14_transport_valid = 0U;
        }
        else {
            pmu_diag_v14_transport_valid = 1U;
%s
        }
#endif
#else
        /* Post-call snapshot BEFORE the disable, cycle first -- contract. */
        pmu_diag_capture_post_order(&d.post);
""" % copies


def _runner_serialize_v14() -> str:
    puts = "\n".join("    put32(&c, d->%s);" % field for field in APPENDIX_FIELDS)
    return """    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->internal_pre_release);
    put_diag_snapshot(&c, &d->internal_post_disable);
    put_diag_snapshot(&c, &d->after_return);
#if defined(PMU_QUAL_SCHEMA_V14)
%s
#endif
#else
    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->post);
    put_diag_snapshot(&c, &d->post_disable);
#endif""" % puts


def patch_runner(text: str, variant: str) -> tuple[str, dict[str, int]]:
    _require_variant(variant)
    text = normalize_newlines(text)
    for marker, what in (
        ("PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID", "V12 build marker"),
        ("PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID", "V13 build marker"),
        ("PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID", "V14 build marker"),
    ):
        if marker in text:
            raise fail("runner input already carries the %s" % what)

    counts: dict[str, int] = {}
    text, counts["schema_version_branch"] = sub_once(
        text, v12._RUNNER_SCHEMA_STOCK, _RUNNER_SCHEMA_V14, "runner schema version branch"
    )
    text, counts["extern_v14_globals"] = sub_once(
        text, v12._RUNNER_EXTERN_STOCK, _RUNNER_EXTERN_V14, "runner V14 extern globals"
    )
    text, counts["record_append_fields"] = sub_once(
        text, v12._RUNNER_RECORD_STOCK, _runner_record_v14(), "runner appended V14 wire fields"
    )
    text, counts["field_count_block"] = sub_once(
        text, v12._RUNNER_FIELD_COUNT_STOCK, _RUNNER_FIELD_COUNT_V14, "runner V14 field count block"
    )
    text, counts["static_asserts"] = sub_once(
        text, v12._RUNNER_ASSERTS_STOCK, _RUNNER_ASSERTS_V14, "runner V14 static asserts"
    )
    text, counts["private_driver_seam_exemption"] = sub_once(
        text,
        v12._RUNNER_PRIVATE_DRIVER_SEAM_STOCK,
        _RUNNER_PRIVATE_DRIVER_SEAM_V14,
        "runner V14 private-driver seam exemption",
    )
    text, counts["private_driver_v8_exemption"] = sub_once(
        text,
        v12._RUNNER_PRIVATE_DRIVER_V8_STOCK,
        _RUNNER_PRIVATE_DRIVER_V14,
        "runner V14 private-driver v8 exemption",
    )
    text, counts["reset_v14_globals"] = sub_once(
        text, v12._RUNNER_CLEAR_STOCK, _RUNNER_CLEAR_V14, "runner V14 mailbox reset"
    )
    text, counts["copy_v14_values"] = sub_once(
        text, v12._RUNNER_COPY_STOCK, _runner_copy_v14(), "runner V14 magic-gated appendix copy"
    )
    text, counts["serialize_v14_values"] = sub_once(
        text, v12._RUNNER_SERIALIZE_STOCK, _runner_serialize_v14(), "runner V14 serialization append"
    )
    return text, counts


def generate(
    variant: str, runner_src: str, vendor_src: str, out_runner: str, out_vendor: str
) -> dict[str, object]:
    _require_variant(variant)
    if _sha256(runner_src) != RUNNER_SHA256:
        raise fail("runner hash mismatch")
    if _sha256(vendor_src) != VENDOR_SHA256:
        raise fail("vendor hash mismatch")
    with open(runner_src, "r", encoding="utf-8") as handle:
        runner = handle.read()
    with open(vendor_src, "r", encoding="utf-8") as handle:
        vendor = handle.read()

    runner_out, runner_counts = patch_runner(runner, variant)
    vendor_out, vendor_counts = patch_vendor(vendor, variant)

    os.makedirs(os.path.dirname(out_runner), exist_ok=True)
    os.makedirs(os.path.dirname(out_vendor), exist_ok=True)
    with open(out_runner, "w", encoding="utf-8") as handle:
        handle.write(runner_out)
    with open(out_vendor, "w", encoding="utf-8") as handle:
        handle.write(vendor_out)

    return {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "total_words": TOTAL_WORDS,
        "payload_bytes": PAYLOAD_BYTES,
        "primary_helper": PRIMARY_SYMBOL[variant],
        "convergence_helper": CONVERGE_SYMBOL,
        "mailbox_symbol": MAILBOX_SYMBOL,
        "mailbox_reset_entry": MAILBOX_RESET_SYMBOL,
        "runner_source_sha256": RUNNER_SHA256,
        "vendor_source_sha256": VENDOR_SHA256,
        "generated_runner_sha256": hashlib.sha256(runner_out.encode("utf-8")).hexdigest(),
        "generated_vendor_sha256": hashlib.sha256(vendor_out.encode("utf-8")).hexdigest(),
        "runner_patch_counts": runner_counts,
        "vendor_patch_counts": vendor_counts,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patch_pmu_completion_visibility_v14.py",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    parser.add_argument("--runner-in", required=True)
    parser.add_argument("--vendor-in", required=True)
    parser.add_argument("--runner-out", required=True)
    parser.add_argument("--vendor-out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = generate(args.variant, args.runner_in, args.vendor_in, args.runner_out, args.vendor_out)
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
