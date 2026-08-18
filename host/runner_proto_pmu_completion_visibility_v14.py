"""Schema-14 PMU completion-visibility frame.

The frame is the 85-word body every PMU diagnostic has carried since v8, with a
34-word appendix after it. This module parses that appendix explicitly, word by
word, and refuses anything that is not a complete V14 frame.

It does not coerce. Earlier parsers reject schema 14, and the temptation is to
hand them a frame wearing an older schema number so they will read the prefix
they understand -- which publishes a V14 run as a v8 measurement. An older view
is available here, but only from a frame that has already passed every check
below, and only over the prefix this module has verified is unchanged.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

try:
    from host import runner_proto as v8
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8

ProtocolError = v8.ProtocolError

NAME = "PMU_COMPLETION_VISIBILITY_DIAG_V14"
SCHEMA_VERSION = 14
BUILD_ID = 0x34314950
MAGIC = v8.PMU_DIAG_MAGIC
MAILBOX_VALID = 0x5631344D

HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS                 # 8
BASE_WORDS = v8.PMU_QUAL_KNOWN_FIELDS                   # 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS                # 119
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS                 # 127
PAYLOAD_BYTES = TOTAL_WORDS * 4                         # 508

QSIZE_EXPECTED = 0x110

# The appendix, in wire order. Position is the contract; this table is this
# module's own and is never read back from a test.
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

VARIANT_BY_ID = {1: "Q", 2: "QS", 3: "SQ"}

# STATUS bits, named where they are read rather than where they are decoded.
STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_RESET = 0x008
STATUS_CMD_END = 0x020
STATUS_FAULT_MASK = 0x314

U32_INVALID = 0xFFFFFFFF


@dataclass(frozen=True)
class PmuCompletionVisibilityV14Result:
    """One decoded frame. Every appendix word is a field, none is derived."""

    schema_version: int
    total_words: int
    run_sequence: int
    run_rc: int
    base_words: tuple = field(repr=False)

    variant_id: int = 0
    qsize_expected: int = 0
    pre_program_status: int = 0
    pre_submit_status: int = 0
    t_submit_after_cmd: int = 0
    t_primary_entry: int = 0
    t_first_observation: int = 0
    primary_result: int = 0
    primary_iterations: int = 0
    first_qread: int = 0
    first_status: int = 0
    first_q_done: int = 0
    first_cmd_end_reached: int = 0
    first_irq_raised: int = 0
    first_state: int = 0
    convergence_result: int = 0
    convergence_iterations: int = 0
    convergence_final_qread: int = 0
    convergence_final_status: int = 0
    convergence_timeout: int = 0
    failure_phase: int = 0
    failure_reason: int = 0
    failure_qread: int = 0
    failure_status: int = 0
    installed_vector: int = 0
    nvic_enabled_before_submit: int = 0
    nvic_pending_after_initial_clear: int = 0
    nvic_active_before_submit: int = 0
    irq_triggered_before_submit: int = 0
    nvic_pending_before_final_clear: int = 0
    nvic_pending_after_final_clear: int = 0
    nvic_active_after_cleanup: int = 0
    irq_triggered_after_cleanup: int = 0
    mailbox_valid: int = 0

    @property
    def variant(self) -> str:
        return VARIANT_BY_ID[self.variant_id]


def parse_payload(payload: bytes) -> PmuCompletionVisibilityV14Result:
    """Decode a schema-14 frame, or refuse it by name."""

    if len(payload) < HEADER_WORDS * 4:
        raise ProtocolError("V14 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, _flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != MAGIC:
        raise ProtocolError("bad PMU diagnostic magic 0x%08X" % magic)
    if version != SCHEMA_VERSION:
        # Deliberately not a fallback. A frame that is not schema 14 is not a
        # completion-visibility record, and reading its prefix anyway is how a
        # diagnostic becomes a measurement.
        raise ProtocolError(
            "unsupported schema %d: %s reads schema %d only" % (version, NAME, SCHEMA_VERSION)
        )
    if header_words != HEADER_WORDS:
        raise ProtocolError("unexpected V14 header_words %d" % header_words)
    if total_words != TOTAL_WORDS:
        raise ProtocolError(
            "declared %d payload words: the V14 frame is %d" % (total_words, TOTAL_WORDS)
        )
    if len(payload) != PAYLOAD_BYTES:
        raise ProtocolError(
            "V14 frame carried %d bytes, the contract is %d" % (len(payload), PAYLOAD_BYTES)
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("V14 payload CRC mismatch")

    body = struct.unpack_from("<%dI" % BODY_WORDS, payload, HEADER_WORDS * 4)
    base = body[:BASE_WORDS]
    appendix = dict(zip(APPENDIX_FIELDS, body[BASE_WORDS:]))

    # The magic is the firmware's statement that the appendix was filled in.
    # It is checked before any appendix word is believed, not after.
    if appendix["mailbox_valid"] != MAILBOX_VALID:
        raise ProtocolError(
            "V14 appendix carries no mailbox magic: 0x%08X" % appendix["mailbox_valid"]
        )
    if appendix["variant_id"] not in VARIANT_BY_ID:
        raise ProtocolError("V14 variant_id %d is not Q, QS or SQ" % appendix["variant_id"])
    if appendix["qsize_expected"] != QSIZE_EXPECTED:
        raise ProtocolError(
            "V14 qsize_expected 0x%X is not the frozen workload 0x%X"
            % (appendix["qsize_expected"], QSIZE_EXPECTED)
        )

    return PmuCompletionVisibilityV14Result(
        schema_version=version,
        total_words=total_words,
        run_sequence=seq,
        run_rc=rc,
        base_words=base,
        **appendix,
    )


def v8_prefix_view(result: PmuCompletionVisibilityV14Result) -> tuple:
    """The frozen 85-word prefix, for readers that predate the appendix.

    Available only from an already-validated V14 result, and only as the words
    themselves: handing back a re-headered frame would let an older parser
    publish this run under a schema it never carried.
    """

    if result.schema_version != SCHEMA_VERSION:
        raise ProtocolError("prefix view requires a validated V14 result")
    if len(result.base_words) != BASE_WORDS:
        raise ProtocolError(
            "prefix view requires the %d-word frozen body, found %d"
            % (BASE_WORDS, len(result.base_words))
        )
    return result.base_words


# ---------------------------------------------------------------------------
# Phase validity
#
# A frame carries words for every stage whether or not that stage ran, so the
# question a reader actually has is which of them mean anything. That is decided
# here, once, from the results the firmware published -- not by each consumer
# noticing that a timestamp looks like 0xFFFFFFFF.
#
# The rule throughout: a word is valid when the stage that writes it reached the
# point of writing it. Everything downstream of a failure is invalid even when
# the frame happens to carry a plausible number there.
# ---------------------------------------------------------------------------

PRIMARY_NOT_RUN = 0
PRIMARY_OBSERVED = 1
PRIMARY_TIMEOUT = 2
PRIMARY_RESET = 3
PRIMARY_FAULT = 4

CONVERGENCE_NOT_RUN = 0
CONVERGENCE_SUCCESS = 1
CONVERGENCE_TIMEOUT = 2
CONVERGENCE_RESET = 3
CONVERGENCE_FAULT = 4

PHASE_NONE = 0
PHASE_PRE_PROGRAM = 1
PHASE_PRE_SUBMIT = 2
PHASE_PRIMARY = 3
PHASE_CONVERGENCE = 4
PHASE_CLEANUP = 5

REASON_NONE = 0

ITERATION_BOUND = 10000

CATEGORY_Q_FIRST = "Q_FIRST"
CATEGORY_S5_FIRST = "S5_FIRST"
CATEGORY_SAME_ITERATION = "SAME_ITERATION"

PRIMARY_FAILURES = (PRIMARY_TIMEOUT, PRIMARY_RESET, PRIMARY_FAULT)
CONVERGENCE_FAILURES = (CONVERGENCE_TIMEOUT, CONVERGENCE_RESET, CONVERGENCE_FAULT)


def _iteration_is_well_formed(count: int, succeeded: bool) -> bool:
    """A stage that ran counts from one; a stage that did not counts zero."""

    return 1 <= count <= ITERATION_BOUND if succeeded else count == 0


def classify_payload(result: PmuCompletionVisibilityV14Result) -> dict:
    """Which phases of one frame mean anything, and what may be published.

    Returns a document rather than a verdict: a consumer that wants the first
    tuple has to read whether the first tuple is valid, and a consumer that
    wants a category gets one only where the contract allows a category at all.
    """

    primary_ok = result.primary_result == PRIMARY_OBSERVED
    convergence_ok = result.convergence_result == CONVERGENCE_SUCCESS
    pre_run_failed = result.failure_phase in (PHASE_PRE_PROGRAM, PHASE_PRE_SUBMIT)
    cleanup_failed = result.failure_phase == PHASE_CLEANUP
    submitted = not pre_run_failed

    problems = []

    # The stage results and the failure phase are two accounts of the same run,
    # and they have to agree. Disagreement is not a phase to be classified; it
    # is a frame nobody should read.
    if result.primary_result in PRIMARY_FAILURES and result.failure_phase != PHASE_PRIMARY:
        problems.append("primary failed but the failure phase is %d" % result.failure_phase)
    if (
        result.convergence_result in CONVERGENCE_FAILURES
        and result.failure_phase != PHASE_CONVERGENCE
    ):
        problems.append("convergence failed but the failure phase is %d" % result.failure_phase)
    if result.failure_phase == PHASE_NONE and result.failure_reason != REASON_NONE:
        problems.append("a failure reason without a failure phase")
    if pre_run_failed and result.primary_result != PRIMARY_NOT_RUN:
        problems.append("the primary loop ran after a pre-run failure")

    if not _iteration_is_well_formed(result.primary_iterations, primary_ok):
        problems.append(
            "primary_iterations %d does not match primary_result %d"
            % (result.primary_iterations, result.primary_result)
        )
    if not _iteration_is_well_formed(result.convergence_iterations, convergence_ok):
        problems.append(
            "convergence_iterations %d does not match convergence_result %d"
            % (result.convergence_iterations, result.convergence_result)
        )
    expected_timeout = 1 if result.convergence_result == CONVERGENCE_TIMEOUT else 0
    if result.convergence_timeout != expected_timeout:
        problems.append(
            "convergence_timeout %d does not match convergence_result %d"
            % (result.convergence_timeout, result.convergence_result)
        )

    succeeded = (
        not problems
        and result.failure_phase == PHASE_NONE
        and result.failure_reason == REASON_NONE
        and primary_ok
        and convergence_ok
    )

    phases = {
        # Submit-side timing exists once the run was allowed to start.
        "t_submit_after_cmd": submitted,
        "t_primary_entry": submitted,
        # The first-observation timestamp is written by the primary loop when it
        # observed something, so a timeout has no P1.
        "t_first_observation": primary_ok,
        "first_tuple": primary_ok,
        "convergence": convergence_ok,
        # The failure tuple is the one thing a failure does publish.
        "failure_tuple": result.failure_phase != PHASE_NONE,
        "cleanup_readbacks": submitted,
    }

    # Q observes one register, so its first tuple has no STATUS-derived words to
    # believe even when the tuple itself is valid.
    q_only = result.variant == "Q"
    tuple_fields = {
        "first_qread": phases["first_tuple"],
        "first_q_done": phases["first_tuple"],
        "first_status": phases["first_tuple"] and not q_only,
        "first_cmd_end_reached": phases["first_tuple"] and not q_only,
        "first_irq_raised": phases["first_tuple"] and not q_only,
        "first_state": phases["first_tuple"] and not q_only,
    }

    category = None
    if succeeded and not q_only:
        q_done = result.first_q_done == 1
        cmd_end = result.first_cmd_end_reached == 1
        if q_done and cmd_end:
            category = CATEGORY_SAME_ITERATION
        elif q_done:
            category = CATEGORY_Q_FIRST
        elif cmd_end:
            category = CATEGORY_S5_FIRST
        else:
            problems.append("a successful primary observation that observed neither register")
            succeeded = False

    return {
        "variant": result.variant,
        "sample_valid": succeeded,
        "phases": phases,
        "first_tuple_fields": tuple_fields,
        "primary_result": result.primary_result,
        "convergence_result": result.convergence_result,
        "failure_phase": result.failure_phase,
        "failure_reason": result.failure_reason,
        # Q is a single-register variant: it has no read order to categorise, so
        # it never carries a category rather than carrying an empty one.
        "category": category,
        "category_scope": (
            "Q observes one register and has no read order to categorise"
            if q_only
            else "read order category, published only for a fully successful sample"
        ),
        # Nothing derived from an invalid phase may be published, and that
        # includes anything that would read like a performance number.
        "may_publish_distribution": succeeded,
        "may_publish_pmu_metric": False,
        "perturbed_by_convergence_tail": True,
        "not_comparable_to_v13": True,
        "not_performance_metric": True,
        "problems": problems,
    }
