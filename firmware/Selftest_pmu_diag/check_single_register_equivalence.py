#!/usr/bin/env python3
"""Whether the S5 measured loop is the Q measured loop with one thing changed.

V15's value rests on a sentence: *the same experiment, with the observable
replaced.* V14 did not leave the analogous sentence to trust -- it proved QS and
SQ differ in read order and in nothing else -- and this is V15's counterpart.

The comparison is deliberately not byte equality. Register allocation and branch
encoding are the compiler's business and carry no meaning: what carries meaning
is the shape of the loop and what it does to the world each time round. So every
instruction in the measured loop is reduced to a semantic role, and the two role
sequences must match exactly.

One difference is permitted, and only one: the observable's load and the test
that decides on it. Everything else -- an extra instruction, an extra memory
touch, a moved freeze, a changed exit topology -- is a difference this gate
refuses, because a control that differs from its reference in two ways is not a
control.

If it refuses, the gate is not relaxed. The comparison mode drops to
S5_WITHIN_VARIANT_ONLY and V15's claims retreat with it.
"""

from __future__ import annotations

import re

RULE_EQUIVALENCE_LOOP_SHAPE = "RULE_EQUIVALENCE_LOOP_SHAPE"
RULE_EQUIVALENCE_SIDE_EFFECTS = "RULE_EQUIVALENCE_SIDE_EFFECTS"
RULE_EQUIVALENCE_OBSERVABLE_ONLY = "RULE_EQUIVALENCE_OBSERVABLE_ONLY"
RULE_EQUIVALENCE_REFERENCE_IDENTITY = "RULE_EQUIVALENCE_REFERENCE_IDENTITY"

RULES = (
    "RULE_EQUIVALENCE_LOOP_SHAPE",
    "RULE_EQUIVALENCE_SIDE_EFFECTS",
    "RULE_EQUIVALENCE_OBSERVABLE_ONLY",
    "RULE_EQUIVALENCE_REFERENCE_IDENTITY",
)

Q_SYMBOL = "v14_primary_q"
S5_SYMBOL = "v15_primary_s5"

# The frozen V14 Q this gate is allowed to compare against. Not "a Q-looking
# function in whatever image is at hand": the whole point of the comparison is
# that the reference is the one the campaign qualified.
Q_REFERENCE_BOARD_EVIDENCE_ANCHOR = "153f368"

# Semantic roles. The names are the vocabulary of the comparison: two loops are
# the same shape when their role sequences are equal, whatever registers the
# compiler chose.
OBSERVABLE_LOAD = "OBSERVABLE_LOAD"
OBSERVABLE_TEST = "OBSERVABLE_TEST"
EXIT_BRANCH = "EXIT_BRANCH"
INDUCTION = "INDUCTION"
BACK_EDGE = "BACK_EDGE"
OTHER = "OTHER"

_LOAD = re.compile(r"^ldr(?:\.[nw])?\s+\w+,\s*\[")
_STORE = re.compile(r"^str(?:b|h)?(?:\.[nw])?\s")
_TEST = re.compile(r"^(cmp|tst|teq|cmn)(?:\.[nw])?\s")
_BRANCH = re.compile(r"^b(?:%s)(?:\.[nw])?\s" % "|".join(
    ("eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le")
))
_INDUCTION = re.compile(r"^(adds?|subs?)(?:\.[nw])?\s")
_CALL = re.compile(r"^bl(?:\.[nw])?\s|^blx\s")


class EquivalenceError(RuntimeError):
    """A pair this gate will not call equivalent."""


def fail_rule(rule: str, message: str) -> EquivalenceError:
    return EquivalenceError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def _helpers():
    import check_pmu_completion_visibility_v14 as v14

    return v14


def _measured_loop(objdump_text: str, symbol: str):
    """The loop body, found by back edge rather than by address order."""

    v14 = _helpers()
    # A helper refusal is this gate's refusal, not an exception from somewhere
    # else. An image whose loop the primitives cannot parse is an image this
    # comparison cannot make, and the caller should hear that in the gate's own
    # vocabulary rather than in the library's.
    try:
        code, literals, data = v14.elf_function(objdump_text, symbol)
        successors = v14.elf_cfg(code, data)
        dominators = v14.elf_dominators(successors)
    except v14.GateError as exc:
        raise fail_rule(
            RULE_EQUIVALENCE_LOOP_SHAPE,
            "%s cannot be read as a comparable function: %s" % (symbol, exc),
        ) from exc
    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail_rule(
            RULE_EQUIVALENCE_LOOP_SHAPE,
            "%s carries %d loops: a helper whose measured loop cannot be identified "
            "cannot be compared" % (symbol, len(back_edges)),
        )
    latch, head = back_edges[0]
    body = sorted(v14.elf_natural_loop(successors, latch, head))
    states = v14.elf_register_values(code, literals, successors)
    return code, states, body, latch


def _roles(code, body, latch):
    """One semantic role per instruction, register names discarded."""

    roles = []
    for index in body:
        text = code[index].text
        if index == latch:
            roles.append(BACK_EDGE)
        elif _LOAD.match(text):
            roles.append(OBSERVABLE_LOAD)
        elif _TEST.match(text):
            roles.append(OBSERVABLE_TEST)
        elif _BRANCH.match(text):
            roles.append(EXIT_BRANCH)
        elif _INDUCTION.match(text):
            roles.append(INDUCTION)
        else:
            roles.append(OTHER)
    return roles


def _side_effects(code, states, body):
    """What each iteration does to the *world*, which roles cannot see.

    The role sequence already says an instruction is a load. It cannot say
    whether that load reaches MMIO or a stack slot, and two loops that agree
    instruction for instruction can still differ in whether they touch the
    device at all. So this asks the pinned helper, which resolves addresses,
    rather than re-reading mnemonics that the roles have already read.
    """

    v14 = _helpers()
    mmio = [
        (role, is_write)
        for index, role, is_write in v14.elf_mmio_accesses(code, states)
        if index in body
    ]
    return {
        "mmio_reads": sum(1 for _role, is_write in mmio if not is_write),
        "mmio_writes": sum(1 for _role, is_write in mmio if is_write),
        "non_mmio_loads": sum(
            1 for index in body if _LOAD.match(code[index].text)
        ) - sum(1 for _role, is_write in mmio if not is_write),
    }


def verify_single_register_equivalence(
    q_objdump_text: str, s5_objdump_text: str, reference_anchor: str
) -> dict:
    """The S5 loop is the Q loop up to the observable, or it is not."""

    if reference_anchor != Q_REFERENCE_BOARD_EVIDENCE_ANCHOR:
        raise fail_rule(
            RULE_EQUIVALENCE_REFERENCE_IDENTITY,
            "the Q reference is %r and the qualified one is %r: a structurally similar "
            "Q is not the Q this comparison means"
            % (reference_anchor, Q_REFERENCE_BOARD_EVIDENCE_ANCHOR),
        )

    q_code, q_states, q_body, q_latch = _measured_loop(q_objdump_text, Q_SYMBOL)
    s5_code, s5_states, s5_body, s5_latch = _measured_loop(s5_objdump_text, S5_SYMBOL)

    q_roles = _roles(q_code, q_body, q_latch)
    s5_roles = _roles(s5_code, s5_body, s5_latch)

    if len(q_roles) != len(s5_roles):
        raise fail_rule(
            RULE_EQUIVALENCE_LOOP_SHAPE,
            "the measured loops are %d and %d instructions: the difference is not the "
            "observable" % (len(q_roles), len(s5_roles)),
        )
    if q_roles != s5_roles:
        first = next(i for i, (a, b) in enumerate(zip(q_roles, s5_roles)) if a != b)
        raise fail_rule(
            RULE_EQUIVALENCE_LOOP_SHAPE,
            "the loops diverge at position %d: Q does %s where S5 does %s"
            % (first, q_roles[first], s5_roles[first]),
        )

    q_effects = _side_effects(q_code, q_states, q_body)
    s5_effects = _side_effects(s5_code, s5_states, s5_body)
    if q_effects != s5_effects:
        raise fail_rule(
            RULE_EQUIVALENCE_SIDE_EFFECTS,
            "the loops touch the world differently per iteration: Q %r against S5 %r"
            % (q_effects, s5_effects),
        )

    # The permitted difference, checked rather than assumed: the load must name
    # different registers or offsets (it is a different register being read) and
    # nothing outside the load and its test may differ in kind.
    q_load = next(code.text for code in (q_code[i] for i in q_body) if _LOAD.match(code.text))
    s5_load = next(code.text for code in (s5_code[i] for i in s5_body) if _LOAD.match(code.text))
    if q_load == s5_load:
        raise fail_rule(
            RULE_EQUIVALENCE_OBSERVABLE_ONLY,
            "the two loops load the same thing: %r. A control that observes what its "
            "reference observes is not a control" % q_load,
        )

    return {
        "q_symbol": Q_SYMBOL,
        "s5_symbol": S5_SYMBOL,
        "reference_anchor": reference_anchor,
        "instructions_per_iteration": len(q_roles),
        "role_sequence": q_roles,
        "side_effects_per_iteration": q_effects,
        "q_observable_load": q_load,
        "s5_observable_load": s5_load,
        "comparison_mode": "Q_S5_EQUIVALENT",
    }
