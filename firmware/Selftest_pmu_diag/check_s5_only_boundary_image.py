#!/usr/bin/env python3
"""The S5-only boundary, decided on the linked image.

Two layers, kept apart on purpose.

The V14 checker's ELF primitives -- function extraction, CFG construction, the
register-value fixpoint, MMIO access naming -- are reused as a library. They were
attacked, corrected (the AAPCS clobber and the CFG reachability fixes are recent)
and pinned by digest. What they guarantee is one sentence: *given this
executable, here are the reachable MMIO accesses under this semantic model.*

Everything after that sentence is this module's responsibility and none of
theirs. That an access belongs to the primary phase, that there is exactly one
per iteration, that its mask is bit5, that no QREAD or QSIZE appears before the
freeze -- those are V15 claims, they did not exist in V14, and they carry their
own targeted negatives.

Keeping the two apart means a failure has an address. A wrong answer is either
an extraction bug in a pinned dependency or an interpretation bug here, and the
evidence chain says which:

    ELF -> pinned helper -> normalised evidence -> V15 detector -> verdict
"""

from __future__ import annotations

import hashlib
import os
import re

RULE_V15_HELPER_IDENTITY = "RULE_V15_HELPER_IDENTITY"
RULE_V15_PRIMARY_S5_ONLY = "RULE_V15_PRIMARY_S5_ONLY"
RULE_V15_POST_FREEZE_SCOPE = "RULE_V15_POST_FREEZE_SCOPE"

RULES = (
    "RULE_V15_HELPER_IDENTITY",
    "RULE_V15_PRIMARY_S5_ONLY",
    "RULE_V15_POST_FREEZE_SCOPE",
)

# The load-bearing dependency set, not one top-level file. _elf_transfer and
# _elf_word_writes had their soundness corrected recently, so which version was
# used is part of this evidence rather than an assumption about it.
HELPER_DEPENDENCIES = {
    "check_pmu_completion_visibility_v14.py":
        "60154b1279a48236ad7e20208a25d86733a78081301ae7c12dc01cbeeb310940",
    "check_pmu_completion_poll_v12.py":
        "772144725e2529916a574d3460366b20581c9e1cc90b24d2957aa611c834557b",
    "check_pmu_completion_poll_count_v13.py":
        "fb4014205158d6b4743fcc1a4b7ab9742e6e82035013f21bdc68f6ea470807a8",
}

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


def verify_helper_identity(directory: str | None = None) -> dict:
    """The pinned dependency set, checked before anything is read through it.

    A helper that changed while still labelled UNCHANGED_AND_HASH_PINNED would
    make every claim above it a claim about code nobody looked at.
    """

    directory = directory or os.path.dirname(os.path.abspath(__file__))
    seen = {}
    for name, expected in sorted(HELPER_DEPENDENCIES.items()):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            raise fail_rule(
                RULE_V15_HELPER_IDENTITY,
                "the pinned helper %s is not present: this gate cannot read an "
                "executable through a dependency it does not have" % name,
            )
        with open(path, "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        if actual != expected:
            raise fail_rule(
                RULE_V15_HELPER_IDENTITY,
                "the pinned helper %s is %s and the pin says %s: the analysis "
                "primitives are not the ones this evidence was qualified against"
                % (name, actual[:16], expected[:16]),
            )
        seen[name] = actual
    return {"helper_dependencies": seen}


def _helpers():
    import check_pmu_completion_visibility_v14 as v14

    return v14


def primary_phase_evidence(objdump_text: str) -> dict:
    """Normalised evidence about the measured loop, from the pinned primitives.

    This is the boundary between the two layers: everything here is the
    helpers' answer, and nothing here decides anything.
    """

    v14 = _helpers()
    code, literals, data = v14.elf_function(objdump_text, PRIMARY_SYMBOL)
    successors = v14.elf_cfg(code, data)
    states = v14.elf_register_values(code, literals, successors)
    reachable = v14.elf_reaches(successors, 0) | {0}

    # A back edge is one whose target dominates its source, not one that merely
    # points at a lower address: these helpers end in a shared epilogue and the
    # branches into it run backwards through the listing without looping.
    dominators = v14.elf_dominators(successors)
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
    loop = v14.elf_natural_loop(successors, latch, head)

    # Which register the STATUS load lands in: the mask helper needs to know
    # what to follow, and the answer is a property of this image rather than a
    # constant. Taken from the load itself, not guessed.
    status_register = None
    for index, role, is_write in v14.elf_mmio_accesses(code, states):
        if role == STATUS_ROLE and not is_write and index in loop:
            hit = v14._ELF_MEMORY.match(code[index].text)
            if hit is not None:
                status_register = hit.group(2)
            break

    accesses = []
    for index, role, is_write in v14.elf_mmio_accesses(code, states):
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
        "tested_mask": v14._elf_status_bits_tested(code, loop, status_register)
        if status_register
        else 0,
    }


def verify_s5_only_boundary_image(objdump_text: str) -> dict:
    """The V15 claim: the measured loop observes STATUS bit5 and nothing else."""

    identity = verify_helper_identity()
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

    return {
        "symbol": PRIMARY_SYMBOL,
        "status_reads_per_iteration": len(status_reads),
        "qread_reads_in_loop": 0,
        "qsize_reads_in_loop": 0,
        "other_mmio_in_loop": 0,
        "tested_mask": "0x%02X" % evidence["tested_mask"],
        "helper_dependencies": identity["helper_dependencies"],
    }
