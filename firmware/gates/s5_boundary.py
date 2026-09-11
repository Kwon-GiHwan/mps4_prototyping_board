"""S5 boundary detector using the unqualified modular gate successor.

Predicate semantics are retained from the frozen V15 detector. Callers must
supply a retained successor byte identity; results are not frozen qualification.
"""

from __future__ import annotations

from .identity import IdentityError, verify_identity
from .completion_visibility import constants, elf_analysis, image_contracts

RULE_V15_HELPER_IDENTITY = "RULE_V15_HELPER_IDENTITY"
RULE_V15_PRIMARY_S5_ONLY = "RULE_V15_PRIMARY_S5_ONLY"
RULE_V15_POST_FREEZE_SCOPE = "RULE_V15_POST_FREEZE_SCOPE"
RULE_V15_IRQ_FROM_DECIDING_WORD = "RULE_V15_IRQ_FROM_DECIDING_WORD"

RULES = (
    "RULE_V15_HELPER_IDENTITY",
    "RULE_V15_PRIMARY_S5_ONLY",
    "RULE_V15_POST_FREEZE_SCOPE",
    "RULE_V15_IRQ_FROM_DECIDING_WORD",
)

PRIMARY_SYMBOL = "v15_primary_s5"
STATUS_OFFSET = 0x04
QREAD_ROLE = "QREAD"
QSIZE_ROLE = "QSIZE"
STATUS_ROLE = "STATUS"
CMD_END_MASK = 0x20


class GateError(RuntimeError):
    """An image this gate will not accept."""


def fail_rule(rule: str, message: str) -> GateError:
    return GateError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def verify_helper_identity(expected_identity: dict) -> dict:
    try:
        return verify_identity(expected_identity)
    except IdentityError as exc:
        raise fail_rule(RULE_V15_HELPER_IDENTITY, str(exc)) from exc


def primary_phase_evidence(objdump_text: str) -> dict:
    """Normalised evidence about the measured loop, from the pinned primitives.

    This is the boundary between the two layers: everything here is the
    helpers' answer, and nothing here decides anything.
    """

    code, literals, data = elf_analysis.elf_function(objdump_text, PRIMARY_SYMBOL)
    successors = elf_analysis.elf_cfg(code, data)
    states = elf_analysis.elf_register_values(code, literals, successors)
    reachable = elf_analysis.elf_reaches(successors, 0) | {0}

    # A back edge is one whose target dominates its source, not one that merely
    # points at a lower address: these helpers end in a shared epilogue and the
    # branches into it run backwards through the listing without looping.
    dominators = elf_analysis.elf_dominators(successors)
    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail_rule(
            RULE_V15_PRIMARY_S5_ONLY,
            "the primary helper carries %d loops: a measured loop this gate cannot "
            "identify is not one it can bound" % len(back_edges),
        )
    latch, head = back_edges[0]
    loop = elf_analysis.elf_natural_loop(successors, latch, head)

    # Which register the STATUS load lands in: the mask helper needs to know
    # what to follow, and the answer is a property of this image rather than a
    # constant. Taken from the load itself, not guessed.
    status_register = None
    for index, role, is_write in elf_analysis.elf_mmio_accesses(code, states):
        if role == STATUS_ROLE and not is_write and index in loop:
            hit = constants._ELF_MEMORY.match(code[index].text)
            if hit is not None:
                status_register = hit.group(2)
            break

    accesses = []
    for index, role, is_write in elf_analysis.elf_mmio_accesses(code, states):
        accesses.append(
            {
                "index": index,
                "address": "0x%08X" % code[index].addr,
                "role": role,
                "is_write": is_write,
                "in_loop": index in loop,
                "reachable": index in reachable,
                "text": code[index].text,
            }
        )
    return {
        "symbol": PRIMARY_SYMBOL,
        "instructions": len(code),
        "loop_body": sorted(loop),
        "accesses": accesses,
        "status_register": status_register,
        # The helper answers with a bitmask of every STATUS bit the loop decides
        # on, merged tests included -- at -O1 GCC folds two bit tests into one
        # `and`/`cmp` pair, and a counter of single-bit tests would report the
        # wrong number of conditions.
        "tested_mask": image_contracts._elf_status_bits_tested(code, loop, status_register)
        if status_register
        else 0,
    }


def verify_s5_only_boundary_image(objdump_text: str, *, expected_identity: dict) -> dict:
    """The V15 claim: the measured loop observes STATUS bit5 and nothing else."""

    identity = verify_helper_identity(expected_identity)
    evidence = primary_phase_evidence(objdump_text)
    in_loop = [access for access in evidence["accesses"] if access["in_loop"] and access["reachable"]]

    forbidden = [access for access in in_loop if access["role"] in (QREAD_ROLE, QSIZE_ROLE)]
    if forbidden:
        raise fail_rule(
            RULE_V15_PRIMARY_S5_ONLY,
            "the measured loop reaches %s at %s: the traffic this control removes is "
            "back inside the window it was removed from"
            % (forbidden[0]["role"], forbidden[0]["address"]),
        )

    status_reads = [
        access for access in in_loop if access["role"] == STATUS_ROLE and not access["is_write"]
    ]
    if len(status_reads) != 1:
        raise fail_rule(
            RULE_V15_PRIMARY_S5_ONLY,
            "the measured loop reads STATUS %d times per iteration: one read is what "
            "makes this a single-register control" % len(status_reads),
        )

    other = [
        access
        for access in in_loop
        if access["role"] not in (STATUS_ROLE, QREAD_ROLE, QSIZE_ROLE)
    ]
    if other:
        raise fail_rule(
            RULE_V15_PRIMARY_S5_ONLY,
            "the measured loop reaches %s at %s, which is neither the observable nor "
            "anything this contract permits" % (other[0]["role"], other[0]["address"]),
        )

    # Exactly bit5. Not "bit5 among others": a loop that also decided on another
    # STATUS bit would have a second exit condition, and the control's claim is
    # that completion is the only one.
    tested = evidence["tested_mask"]
    if tested != CMD_END_MASK:
        raise fail_rule(
            RULE_V15_PRIMARY_S5_ONLY,
            "the measured loop decides on STATUS mask 0x%02X and the contract's "
            "observable is 0x%02X alone" % (tested, CMD_END_MASK),
        )

    # The word the loop decided on has to be the word the record carries. A
    # second STATUS load would give the record a value the bit5 test never saw,
    # and the host would then derive irq_raised from a different sample than the
    # one it is reported beside. This is its own claim and its own rule: passing
    # the one-read rule does not carry it, and one is not promoted because the
    # other passed.
    code, literals, data = elf_analysis.elf_function(objdump_text, PRIMARY_SYMBOL)
    successors = elf_analysis.elf_cfg(code, data)
    states = elf_analysis.elf_register_values(code, literals, successors)
    deciding = status_reads[0]
    deciding_register = constants._ELF_MEMORY.match(code[deciding["index"]].text).group(2)
    reloads = [
        index
        for index, role, is_write in elf_analysis.elf_mmio_accesses(code, states)
        if role == STATUS_ROLE
        and not is_write
        and index != deciding["index"]
        and constants._ELF_MEMORY.match(code[index].text).group(2) == deciding_register
    ]
    if reloads:
        raise fail_rule(
            RULE_V15_IRQ_FROM_DECIDING_WORD,
            "STATUS is reloaded into %s at 0x%08X after the deciding read: the record "
            "would carry a word the bit5 test never saw"
            % (deciding_register, code[reloads[0]].addr),
        )

    return {
        "symbol": PRIMARY_SYMBOL,
        "deciding_register": deciding_register,
        "status_reloads_into_deciding_register": 0,
        "status_reads_per_iteration": len(status_reads),
        "qread_reads_in_loop": 0,
        "qsize_reads_in_loop": 0,
        "other_mmio_in_loop": 0,
        "tested_mask": "0x%02X" % evidence["tested_mask"],
        "successor_identity": identity,
    }
