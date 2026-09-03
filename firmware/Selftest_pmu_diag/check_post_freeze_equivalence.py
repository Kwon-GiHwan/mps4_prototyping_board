#!/usr/bin/env python3
"""Whether V15 left everything after the freeze exactly as V14 Q had it.

This is a negative-space proof. It discovers nothing about the device; it proves
that the patcher's reach stopped where the design says it stops. The tail is
shared code and is *expected* to be identical -- which is not a reason to skip
the check but the reason to make it, because an expectation nobody tested is how
a second change travels unnoticed alongside the first.

The boundary is the common-tail entry, after the first-observation freeze. What
is compared is the tail's *program semantics*, not its inputs: V14 Q and V15 S5
reach that entry with different observation state by construction, and requiring
their values to match would be requiring the two experiments to be one.

    PRIMARY -> freeze
    ================= boundary =================
    convergence tail -> fault/timeout -> cleanup -> terminal release
"""

from __future__ import annotations

import re

RULE_TAIL_MMIO_SEQUENCE = "RULE_TAIL_MMIO_SEQUENCE"
RULE_TAIL_PREDICATE = "RULE_TAIL_PREDICATE"
RULE_TAIL_TOPOLOGY = "RULE_TAIL_TOPOLOGY"
RULE_TAIL_SIDE_EFFECTS = "RULE_TAIL_SIDE_EFFECTS"
RULE_TAIL_CALL_TOPOLOGY = "RULE_TAIL_CALL_TOPOLOGY"

RULES = (
    "RULE_TAIL_MMIO_SEQUENCE",
    "RULE_TAIL_PREDICATE",
    "RULE_TAIL_TOPOLOGY",
    "RULE_TAIL_SIDE_EFFECTS",
    "RULE_TAIL_CALL_TOPOLOGY",
)

Q_TAIL_SYMBOL = "v14_converge"
S5_TAIL_SYMBOL = "v15_converge"

QSIZE_ROLE = "QSIZE"

_STORE = re.compile(r"^str(?:b|h)?(?:\.[nw])?\s")
_CALL = re.compile(r"^bl(?:\.[nw])?\s+[0-9a-f]+\s*<([^>+]+)")


class TailError(RuntimeError):
    """A tail this gate will not call unchanged."""


def fail_rule(rule: str, message: str) -> TailError:
    return TailError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def _helpers():
    import check_pmu_completion_visibility_v14 as v14

    return v14


def tail_shape(objdump_text: str, symbol: str) -> dict:
    """Everything about the tail that does not depend on what reached it.

    Addresses, register numbers and branch encodings are left out on purpose:
    they differ between two links of the same code and mean nothing here.
    """

    v14 = _helpers()
    try:
        code, literals, data = v14.elf_function(objdump_text, symbol)
        successors = v14.elf_cfg(code, data)
        states = v14.elf_register_values(code, literals, successors)
    except v14.GateError as exc:
        raise fail_rule(
            RULE_TAIL_TOPOLOGY, "%s cannot be read as a tail: %s" % (symbol, exc)
        ) from exc

    dominators = v14.elf_dominators(successors)
    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    loop = (
        v14.elf_natural_loop(successors, *back_edges[0])
        if len(back_edges) == 1
        else frozenset()
    )
    status_register = None
    for index, role, is_write in v14.elf_mmio_accesses(code, states):
        if role == "STATUS" and not is_write and index in loop:
            status_register = v14._ELF_MEMORY.match(code[index].text).group(2)
            break

    accesses = v14.elf_mmio_accesses(code, states)
    return {
        "symbol": symbol,
        "instructions": len(code),
        # The order the tail touches the device in, which is the thing the
        # design fixes and the thing a reordering patch would move.
        "mmio_sequence": [
            (role, "w" if is_write else "r") for _index, role, is_write in accesses
        ],
        "mmio_in_loop": [
            (role, "w" if is_write else "r")
            for index, role, is_write in accesses
            if index in loop
        ],
        "qsize_reads": sum(1 for _i, role, w in accesses if role == QSIZE_ROLE and not w),
        # The four-condition predicate, as a mask rather than a count: at -O1
        # GCC folds two bit tests into one and/cmp pair.
        "predicate_mask": v14._elf_status_bits_tested(code, loop, status_register)
        if status_register
        else 0,
        "edges": sum(len(outs) for outs in successors),
        "exits": sum(1 for outs in successors if not outs),
        "back_edges": len(back_edges),
        "stores": sum(1 for insn in code if _STORE.match(insn.text)),
        "callees": sorted(
            {
                hit.group(1).replace("v14_", "").replace("v15_", "")
                for insn in code
                for hit in [_CALL.match(insn.text)]
                if hit
            }
        ),
    }


def verify_post_freeze_equivalence(q_objdump_text: str, s5_objdump_text: str) -> dict:
    """The tail V15 ships is the tail V14 Q shipped."""

    q = tail_shape(q_objdump_text, Q_TAIL_SYMBOL)
    s5 = tail_shape(s5_objdump_text, S5_TAIL_SYMBOL)

    if q["mmio_sequence"] != s5["mmio_sequence"]:
        raise fail_rule(
            RULE_TAIL_MMIO_SEQUENCE,
            "the tail touches the device differently: Q %r against S5 %r"
            % (q["mmio_sequence"], s5["mmio_sequence"]),
        )
    if s5["qsize_reads"]:
        raise fail_rule(
            RULE_TAIL_MMIO_SEQUENCE,
            "the S5 tail reads QSIZE %d time(s): QSIZE is read once, while stopped"
            % s5["qsize_reads"],
        )
    if q["predicate_mask"] != s5["predicate_mask"]:
        raise fail_rule(
            RULE_TAIL_PREDICATE,
            "the convergence predicate decides on STATUS mask 0x%02X in Q and 0x%02X "
            "in S5" % (q["predicate_mask"], s5["predicate_mask"]),
        )
    for key, rule in (
        ("edges", RULE_TAIL_TOPOLOGY),
        ("exits", RULE_TAIL_TOPOLOGY),
        ("back_edges", RULE_TAIL_TOPOLOGY),
        ("instructions", RULE_TAIL_TOPOLOGY),
        ("stores", RULE_TAIL_SIDE_EFFECTS),
    ):
        if q[key] != s5[key]:
            raise fail_rule(
                rule,
                "the tail's %s differ: Q %r against S5 %r" % (key, q[key], s5[key]),
            )
    if q["callees"] != s5["callees"]:
        raise fail_rule(
            RULE_TAIL_CALL_TOPOLOGY,
            "the tail calls different things: Q %r against S5 %r"
            % (q["callees"], s5["callees"]),
        )

    return {
        "q_symbol": Q_TAIL_SYMBOL,
        "s5_symbol": S5_TAIL_SYMBOL,
        "instructions": q["instructions"],
        "mmio_sequence": q["mmio_sequence"],
        "predicate_mask": "0x%02X" % q["predicate_mask"],
        "qsize_reads": 0,
        "stores": q["stores"],
        "callees": q["callees"],
        "unchanged_after_the_freeze": True,
    }
