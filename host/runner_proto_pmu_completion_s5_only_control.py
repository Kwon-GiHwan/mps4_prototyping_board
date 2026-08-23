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

import re
import struct
from dataclasses import dataclass, field

try:
    from host import runner_proto as v8
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8

ProtocolError = v8.ProtocolError

NAME = "PMU_COMPLETION_S5_ONLY_CONTROL_V15"

# Amendment 4: the wire ABI version, as the firmware actually emits it. The
# generated C defines PMU_DIAG_SCHEMA_VERSION as 14U and static-asserts it, and
# this parser previously read 15 -- so it rejected every real frame the board
# produced. 15 is the qualification generation and is not a wire number.
SCHEMA_VERSION = 14
QUALIFICATION_GENERATION = 15
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

# The result encodings the firmware actually writes into the mailbox. These are
# NOT the runner's VENDOR_RETURN codes, and assuming they were is what made the
# classifier read a successful run as a failed one: VENDOR_RETURN has SUCCESS=0,
# while here 0 means the phase never ran. Verified against the emitted C by
# verify_result_enums rather than transcribed and trusted.
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

RESULT_ENUMS = {
    "V15_PRIMARY_NOT_RUN": PRIMARY_NOT_RUN,
    "V15_PRIMARY_OBSERVED": PRIMARY_OBSERVED,
    "V15_PRIMARY_TIMEOUT": PRIMARY_TIMEOUT,
    "V15_PRIMARY_RESET": PRIMARY_RESET,
    "V15_PRIMARY_FAULT": PRIMARY_FAULT,
    "V15_CONVERGENCE_NOT_RUN": CONVERGENCE_NOT_RUN,
    "V15_CONVERGENCE_SUCCESS": CONVERGENCE_SUCCESS,
    "V15_CONVERGENCE_TIMEOUT": CONVERGENCE_TIMEOUT,
    "V15_CONVERGENCE_RESET": CONVERGENCE_RESET,
    "V15_CONVERGENCE_FAULT": CONVERGENCE_FAULT,
}

STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_RESET = 0x008
STATUS_CMD_END = 0x020
STATUS_FAULT_MASK = 0x314


GENERATED_RUNNER_EVIDENCE = (
    "docs/superpowers/evidence/v15-wire-contract-20260823/"
    "generated_runner_pmu_diag_main.c"
)


def emitted_wire_contract(generated_c: str) -> dict:
    """What the compiled firmware says about the wire, read out of its own C.

    This exists because the previous check did not do it. It compared the
    generator's Python constant SCHEMA_VERSION against this module's, found 15
    on both sides, and passed -- while the C those same files emit defines the
    schema as 14. Two host-side declarations descended from one assumption are
    not two independent declarations, and a live frame proved it.

    So the authority here is the generated source that was actually compiled,
    parsed for the values the firmware will put on the wire.
    """

    block = re.search(
        r"#if defined\(PMU_QUAL_SCHEMA_V15\)(.*?)#elif", generated_c, re.S
    )
    if not block:
        raise ProtocolError(
            "the generated source carries no PMU_QUAL_SCHEMA_V15 block, so nothing "
            "here describes what the firmware emits"
        )
    head = block.group(1)

    schema = re.search(r"#define\s+PMU_DIAG_SCHEMA_VERSION\s+(\d+)U", head)
    if not schema:
        raise ProtocolError("the V15 block defines no PMU_DIAG_SCHEMA_VERSION")

    words = re.search(r"#define\s+V15_APPENDIX_WORDS\s+(\d+)U", head)
    magic = re.search(r"#define\s+V15_MAILBOX_VALID\s+0x([0-9A-Fa-f]+)U", head)

    asserted = re.search(
        r"_Static_assert\(PMU_DIAG_SCHEMA_VERSION == (\d+)U", generated_c
    )

    # The appendix as the firmware fills it: mailbox index -> record field.
    assigns = re.findall(
        r"d\.(\w+)\s*=\s*pmu_completion_visibility_v15_mailbox\[(\d+)\]", generated_c
    )
    by_index = {}
    for field, index in assigns:
        by_index[int(index)] = field

    return {
        "schema_version": int(schema.group(1)),
        "schema_version_asserted": int(asserted.group(1)) if asserted else None,
        "appendix_words": int(words.group(1)) if words else None,
        "mailbox_valid": int(magic.group(1), 16) if magic else None,
        "appendix_by_index": by_index,
    }


def verify_wire_contract(generated_c: str) -> dict:
    """This module's wire declarations against the firmware's own emitted C.

    Not against the generator's Python constants. That is the check that let a
    schema mismatch reach the board.
    """

    emitted = emitted_wire_contract(generated_c)

    if emitted["schema_version"] != SCHEMA_VERSION:
        raise ProtocolError(
            "the firmware emits wire schema %d and this parser reads %d"
            % (emitted["schema_version"], SCHEMA_VERSION)
        )
    if emitted["schema_version_asserted"] not in (None, SCHEMA_VERSION):
        raise ProtocolError(
            "the firmware static-asserts wire schema %d and this parser reads %d"
            % (emitted["schema_version_asserted"], SCHEMA_VERSION)
        )
    if emitted["appendix_words"] not in (None, APPENDIX_WORDS):
        raise ProtocolError(
            "the firmware emits %d appendix words, this parser reads %d"
            % (emitted["appendix_words"], APPENDIX_WORDS)
        )
    if emitted["mailbox_valid"] not in (None, MAILBOX_VALID):
        raise ProtocolError(
            "the firmware writes mailbox magic 0x%08X, this parser expects 0x%08X"
            % (emitted["mailbox_valid"], MAILBOX_VALID)
        )

    by_index = emitted["appendix_by_index"]
    if by_index:
        if len(by_index) != APPENDIX_WORDS:
            raise ProtocolError(
                "the firmware fills %d appendix slots and this parser names %d"
                % (len(by_index), APPENDIX_WORDS)
            )
        for index in range(APPENDIX_WORDS):
            if index not in by_index:
                raise ProtocolError("the firmware fills no appendix slot %d" % index)
            if by_index[index] != APPENDIX_FIELDS[index]:
                raise ProtocolError(
                    "appendix word %d: the firmware writes %r, this parser names %r"
                    % (index, by_index[index], APPENDIX_FIELDS[index])
                )

    return {
        "source": "emitted firmware C",
        "wire_schema_version": SCHEMA_VERSION,
        "appendix_words": APPENDIX_WORDS,
        "appendix_order_verified": bool(by_index),
        "mailbox_valid": "0x%08X" % MAILBOX_VALID,
    }


def verify_result_enums(generated_u85_c: str) -> dict:
    """The host's result encodings against the firmware's own #defines.

    Nothing here is transcribed on trust. The classifier read a successful run
    as a failed one because it borrowed VENDOR_RETURN, where SUCCESS is 0, while
    the firmware writes 0 for a phase that never ran.
    """

    found = {}
    for name in RESULT_ENUMS:
        match = re.search(r"#define\s+%s\s+(\d+)U" % re.escape(name), generated_u85_c)
        if not match:
            raise ProtocolError(
                "the emitted firmware defines no %s, so this host constant describes "
                "nothing" % name
            )
        found[name] = int(match.group(1))
    wrong = {n: (found[n], RESULT_ENUMS[n]) for n in RESULT_ENUMS if found[n] != RESULT_ENUMS[n]}
    if wrong:
        name, (theirs, ours) = sorted(wrong.items())[0]
        raise ProtocolError(
            "%s is %d in the firmware and %d here" % (name, theirs, ours)
        )
    return {"result_enums_checked": len(found), "source": "emitted firmware C"}


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
