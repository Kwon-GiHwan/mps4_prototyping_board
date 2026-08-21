#!/usr/bin/env python3
"""Schema-15 S5-only frame: the wire, and only the wire.

The frame is the 85-word body every PMU diagnostic has carried since v8, with
the same 34-word appendix V14 shipped, behind the fixed 8-word ABI header.

This module is deliberately narrow. It knows the bytes the target emitted and
nothing else. It does not know the comparison mode, the build id, or which image
was flashed, because the target does not emit any of them -- see Amendment 2.
``parse_frame`` returns a ``ParsedFrame`` and stops there; attaching externally
bound facts is ``normalize``'s job, in a later stage, against a cell context
that was verified by hash. A parser that reads a manifest is a parser that has
re-mixed the two provenances the amendment exists to separate.

The appendix tuple below is this module's own declaration, not an import. The
firmware generator declares the same 34 names independently, and
``verify_wire_contract`` compares the two: a copy would agree with itself, two
declarations have to be kept equal. Nothing here zips names onto words --
``dict(zip(...))`` truncates to the shorter side without raising, which is how a
24-name list nearly became a parser for a 34-word record.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

try:
    from host import runner_proto as v8
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8

ProtocolError = v8.ProtocolError

NAME = "PMU_COMPLETION_S5_ONLY_CONTROL_V15"
SCHEMA_VERSION = 15
BUILD_ID = 0x49503531                                   # 'IP51', manifest-side
MAGIC = v8.PMU_DIAG_MAGIC

# ASCII "V14M". The appendix is byte-identical to V14's and so is the word that
# says it was filled in; schema_version is what separates a V15 frame from a
# V14 one, and it is checked before any appendix word is believed.
MAILBOX_VALID = 0x5631344D

HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS                 # 8
BASE_WORDS = v8.PMU_QUAL_KNOWN_FIELDS                   # 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS                # 119
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS                 # 127
PAYLOAD_BYTES = TOTAL_WORDS * 4                         # 508

QSIZE_EXPECTED = 0x110
VARIANT_BY_ID = {1: "S5"}

# The appendix, in wire order. Position is the contract.
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

STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_RESET = 0x008
STATUS_CMD_END = 0x020
STATUS_FAULT_MASK = 0x314


def verify_wire_contract() -> dict:
    """This module's appendix against the firmware generator's, name for name."""

    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    firmware = os.path.join(root, "firmware")
    if firmware not in sys.path:
        sys.path.insert(0, firmware)
    from patches import patch_pmu_completion_s5_only_control_source as generator

    theirs = tuple(generator.APPENDIX_FIELDS)
    if len(theirs) != APPENDIX_WORDS:
        raise ProtocolError(
            "the firmware generator emits %d appendix words, this parser reads %d"
            % (len(theirs), APPENDIX_WORDS)
        )
    if theirs != APPENDIX_FIELDS:
        differing = [
            "word %d: firmware %r, parser %r" % (index, a, b)
            for index, (a, b) in enumerate(zip(theirs, APPENDIX_FIELDS))
            if a != b
        ]
        raise ProtocolError(
            "the appendix order does not match the firmware's: %s"
            % ("; ".join(differing) or "same names, different order")
        )
    if generator.SCHEMA_VERSION != SCHEMA_VERSION:
        raise ProtocolError(
            "the firmware generator emits schema %d, this parser reads %d"
            % (generator.SCHEMA_VERSION, SCHEMA_VERSION)
        )
    if generator.BUILD_ID != BUILD_ID:
        raise ProtocolError(
            "the firmware generator declares build 0x%08X, this parser expects 0x%08X"
            % (generator.BUILD_ID, BUILD_ID)
        )
    return {
        "appendix_words": APPENDIX_WORDS,
        "firmware_appendix_words": len(theirs),
        "tuples_equal": True,
        "schema_version": SCHEMA_VERSION,
    }


def verify_record_field_origins() -> dict:
    """Every record field declared WIRE_APPENDIX must be a word the wire carries.

    The provenance mapping is only worth having if a wrong entry fails. A field
    called out as coming from the appendix that is not in the appendix is the
    exact confusion Amendment 2 was written about.
    """

    try:
        from host import contract_pmu_completion_s5_only_control as contract
    except ModuleNotFoundError:  # pragma: no cover - direct script fallback
        import contract_pmu_completion_s5_only_control as contract

    origins = contract.RECORD_FIELD_ORIGINS
    unmapped = [name for name in contract.RECORD_FIELDS if name not in origins]
    if unmapped:
        raise ProtocolError(
            "these record fields declare no origin: %s" % ", ".join(sorted(unmapped))
        )
    stray = [name for name in origins if name not in contract.RECORD_FIELDS]
    if stray:
        raise ProtocolError(
            "these origins name no record field: %s" % ", ".join(sorted(stray))
        )
    unknown = {
        name: value for name, value in origins.items() if value not in contract.FIELD_ORIGINS
    }
    if unknown:
        name, value = sorted(unknown.items())[0]
        raise ProtocolError("%s declares origin %r, which is not an origin" % (name, value))

    # mailbox_magic is this record's name for the wire's mailbox_valid word.
    aliases = {"mailbox_magic": "mailbox_valid"}
    wrong = [
        name
        for name, origin in origins.items()
        if origin == contract.WIRE_APPENDIX
        and aliases.get(name, name) not in APPENDIX_FIELDS
    ]
    if wrong:
        raise ProtocolError(
            "these fields claim to come from the wire appendix and are not in it: %s"
            % ", ".join(sorted(wrong))
        )
    return {"record_fields": len(contract.RECORD_FIELDS), "origins_checked": len(origins)}


@dataclass(frozen=True)
class ParsedFrame:
    """One decoded frame. Every field is a word the target emitted.

    No comparison_mode and no build_id: the target emits neither, and a parser
    that supplies them from elsewhere is not reporting what the board said.
    """

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


def _appendix_from_words(words: tuple) -> dict:
    """Name the appendix words, refusing any count but the contracted one."""

    if len(words) != len(APPENDIX_FIELDS):
        raise ProtocolError(
            "the V15 appendix is %d words and this frame carries %d: zipping the "
            "shorter against the longer would silently misalign every word after "
            "the first difference" % (len(APPENDIX_FIELDS), len(words))
        )
    return dict(zip(APPENDIX_FIELDS, words))


def parse_frame(payload: bytes) -> ParsedFrame:
    """Decode a schema-15 frame, or refuse it by name."""

    if len(payload) < HEADER_WORDS * 4:
        raise ProtocolError("V15 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, _flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != MAGIC:
        raise ProtocolError("bad PMU diagnostic magic 0x%08X" % magic)
    if version != SCHEMA_VERSION:
        # Not a fallback. A frame that is not schema 15 is not an S5-only
        # record, and reading its prefix anyway is how a diagnostic becomes a
        # measurement.
        raise ProtocolError(
            "unsupported schema %d: %s reads schema %d only" % (version, NAME, SCHEMA_VERSION)
        )
    if header_words != HEADER_WORDS:
        raise ProtocolError("unexpected V15 header_words %d" % header_words)
    if total_words != TOTAL_WORDS:
        raise ProtocolError(
            "declared %d payload words: the V15 frame is %d" % (total_words, TOTAL_WORDS)
        )
    if len(payload) != PAYLOAD_BYTES:
        raise ProtocolError(
            "V15 frame carried %d bytes, the contract is %d" % (len(payload), PAYLOAD_BYTES)
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("V15 payload CRC mismatch")

    body = struct.unpack_from("<%dI" % BODY_WORDS, payload, HEADER_WORDS * 4)
    base = body[:BASE_WORDS]
    appendix = _appendix_from_words(body[BASE_WORDS:])

    # The magic is the firmware's statement that the appendix was filled in. It
    # is checked before any appendix word is believed, not after.
    if appendix["mailbox_valid"] != MAILBOX_VALID:
        raise ProtocolError(
            "V15 appendix carries no mailbox magic: 0x%08X" % appendix["mailbox_valid"]
        )
    if appendix["variant_id"] not in VARIANT_BY_ID:
        raise ProtocolError(
            "V15 variant_id %d is not S5: this schema has one variant"
            % appendix["variant_id"]
        )
    if appendix["qsize_expected"] != QSIZE_EXPECTED:
        raise ProtocolError(
            "V15 qsize_expected 0x%X is not the frozen workload 0x%X"
            % (appendix["qsize_expected"], QSIZE_EXPECTED)
        )

    return ParsedFrame(
        schema_version=version,
        total_words=total_words,
        run_sequence=seq,
        run_rc=rc,
        base_words=base,
        **appendix,
    )
