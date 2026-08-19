#!/usr/bin/env python3
"""The S5 primary loop contract, decided on the generated source.

This gate is small on purpose. It answers one question -- does the measured loop
observe STATUS bit5 and nothing else -- and it answers it on the text, which is
where the shape of the loop is decided. Whether the compiler kept that shape is a
separate question with a separate authority: the linked image, gated later.

Every refusal carries its own identifier, so a fixture aimed at one rule that
trips another is a failed fixture rather than a passing test. That convention
cost V14 three attempts on a single fixture and found a rule that could not fire
at all, so it is here from the first line rather than added afterwards.
"""

from __future__ import annotations

import re

RULE_S5_ONE_STATUS_READ = "RULE_S5_ONE_STATUS_READ"
RULE_S5_NO_QREAD_IN_LOOP = "RULE_S5_NO_QREAD_IN_LOOP"
RULE_S5_NO_QSIZE_IN_LOOP = "RULE_S5_NO_QSIZE_IN_LOOP"
RULE_S5_IRQ_FROM_DECIDING_WORD = "RULE_S5_IRQ_FROM_DECIDING_WORD"
RULE_S5_EXIT_IS_CMD_END = "RULE_S5_EXIT_IS_CMD_END"
RULE_S5_ITERATION_BOUND = "RULE_S5_ITERATION_BOUND"

RULES = (
    "RULE_S5_ONE_STATUS_READ",
    "RULE_S5_NO_QREAD_IN_LOOP",
    "RULE_S5_NO_QSIZE_IN_LOOP",
    "RULE_S5_IRQ_FROM_DECIDING_WORD",
    "RULE_S5_EXIT_IS_CMD_END",
    "RULE_S5_ITERATION_BOUND",
)

ITERATION_BOUND_MACRO = "V15_ITERATION_BOUND"
CMD_END_MACRO = "V15_STATUS_CMD_END"
IRQ_MACRO = "V15_STATUS_IRQ_RAISED"


class GateError(RuntimeError):
    """A source this gate will not accept."""


def fail_rule(rule: str, message: str) -> GateError:
    return GateError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    """The identifier a refusal carries, or None if it carries none."""

    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_LOOP_HEAD = re.compile(r"for\s*\([^;]*;([^;]*);[^)]*\)\s*\{")
_STATUS_DEREF = re.compile(r"\*\s*status_reg\b")
_QREAD_DEREF = re.compile(r"\*\s*qread_reg\b")
_QSIZE_DEREF = re.compile(r"\*\s*qsize_reg\b")


def _strip_comments(source: str) -> str:
    return _COMMENT.sub(" ", source)


def _loop_body(source: str) -> tuple[str, str]:
    """``(header condition, body)`` of the one measured loop.

    Brace-matched rather than regex-terminated: a nested block inside the loop
    is ordinary, and a scan that stopped at the first closing brace would read
    half a loop and call it the whole one.
    """

    head = _LOOP_HEAD.search(source)
    if head is None:
        raise fail_rule(
            RULE_S5_ITERATION_BOUND, "the source carries no bounded measured loop"
        )
    depth = 0
    start = head.end() - 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return head.group(1), source[start + 1 : index]
    raise fail_rule(RULE_S5_ITERATION_BOUND, "the measured loop is not closed")


def verify_s5_primary_contract(source: str) -> dict:
    """What the measured loop reads, and what it is allowed to leave on."""

    text = _strip_comments(source)
    condition, body = _loop_body(text)

    if ITERATION_BOUND_MACRO not in condition:
        raise fail_rule(
            RULE_S5_ITERATION_BOUND,
            "the loop bound is %r rather than %s: the bound is the contract's, not the "
            "author's" % (condition.strip(), ITERATION_BOUND_MACRO),
        )

    status_reads = len(_STATUS_DEREF.findall(body))
    if status_reads != 1:
        raise fail_rule(
            RULE_S5_ONE_STATUS_READ,
            "the measured loop reads STATUS %d times: one read per iteration is the "
            "whole point of a single-register control" % status_reads,
        )

    qread_reads = len(_QREAD_DEREF.findall(body))
    if qread_reads:
        raise fail_rule(
            RULE_S5_NO_QREAD_IN_LOOP,
            "the measured loop reads QREAD %d time(s): the traffic this control exists "
            "to remove is back in the window it was removed from" % qread_reads,
        )

    qsize_reads = len(_QSIZE_DEREF.findall(body))
    if qsize_reads:
        raise fail_rule(
            RULE_S5_NO_QSIZE_IN_LOOP,
            "the measured loop reaches QSIZE %d time(s): QSIZE is read once, while "
            "stopped" % qsize_reads,
        )

    # The loop may leave on reset, on fault, and on completion. Completion means
    # bit5 -- leaving on irq_raised would make the interrupt an exit condition,
    # which is the thing V14 proved it is not and V15 inherits.
    exits = re.findall(r"if\s*\(\(\s*status\s*&\s*(\w+)\s*\)[^)]*\)\s*\{?", body)
    if CMD_END_MACRO not in exits:
        raise fail_rule(
            RULE_S5_EXIT_IS_CMD_END,
            "the measured loop has no %s exit: its completion condition is some other "
            "bit" % CMD_END_MACRO,
        )
    if IRQ_MACRO in exits:
        raise fail_rule(
            RULE_S5_EXIT_IS_CMD_END,
            "the measured loop can leave on %s: the interrupt is observed, never an "
            "exit" % IRQ_MACRO,
        )

    # irq_raised is supporting evidence from the word the deciding test used.
    # The firmware is not required to compute it -- publishing the raw deciding
    # word and letting the host derive bit1 costs the measured loop nothing and
    # is provably the same word. What is required is that the deciding word
    # reaches the record, and that any derivation the firmware does do is not
    # taken from a fresh read.
    published = re.search(r"obs->status\s*=\s*(\w+)\s*;", body)
    if published is None or published.group(1) != "status":
        raise fail_rule(
            RULE_S5_IRQ_FROM_DECIDING_WORD,
            "the deciding STATUS word is not published from inside the loop: the host "
            "cannot derive irq_raised from the word the bit5 test used",
        )
    irq_site = re.search(r"irq_raised[a-z_]*\s*=\s*\(([^)]*)\)", text)
    if irq_site is not None and _STATUS_DEREF.search(irq_site.group(1)):
        raise fail_rule(
            RULE_S5_IRQ_FROM_DECIDING_WORD,
            "irq_raised is taken from a fresh STATUS read: it must come from the word "
            "the bit5 test already sampled",
        )

    return {
        "status_reads_per_iteration": status_reads,
        "qread_reads_in_loop": qread_reads,
        "qsize_reads_in_loop": qsize_reads,
        "exit_conditions": sorted(set(exits)),
        "deciding_word_published": True,
        "irq_from_the_deciding_word": True,
        "iteration_bound": ITERATION_BOUND_MACRO,
    }
