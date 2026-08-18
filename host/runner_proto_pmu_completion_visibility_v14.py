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
