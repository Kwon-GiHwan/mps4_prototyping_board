#!/usr/bin/env python3
"""Generate the V15 source pair from pinned inputs, or refuse before generating.

The ordering matters more than it looks. A generator that transforms first and
validates afterwards has already written an artifact by the time it notices the
input was wrong, and artifacts get picked up. So every pin is checked while the
output is still nothing.

The pin that carries the most weight is the V14 Q reference. V15's entire claim
is that it is Q with one observable replaced, which is only meaningful if the Q
it came from is the one the campaign qualified -- not a file with the same shape
that happened to be at hand.
"""

from __future__ import annotations

import hashlib

RULE_INPUT_IDENTITY = "RULE_INPUT_IDENTITY"
RULE_Q_REFERENCE_IDENTITY = "RULE_Q_REFERENCE_IDENTITY"
RULE_ANCHOR_IDENTITY = "RULE_ANCHOR_IDENTITY"
RULE_INTERVENTION_SURFACE = "RULE_INTERVENTION_SURFACE"

RULES = (
    "RULE_INPUT_IDENTITY",
    "RULE_Q_REFERENCE_IDENTITY",
    "RULE_ANCHOR_IDENTITY",
    "RULE_INTERVENTION_SURFACE",
)

# The V14 lineage this generator is allowed to derive from. Written here rather
# than discovered at run time: "find the most recent Q-looking thing" is the
# behaviour that would let an unqualified file become the reference.
Q_REFERENCE_PREBOARD_ANCHOR = "619e957"
Q_REFERENCE_BOARD_EVIDENCE_ANCHOR = "153f368"
DESIGN_ANCHOR = "58b0cad"
PLAN_ANCHOR = "3ca7bb1"


class GeneratorError(RuntimeError):
    """An input this generator will not build from."""


def fail_rule(rule: str, message: str) -> GeneratorError:
    return GeneratorError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_inputs(runner: str, vendor: str, identity: dict) -> None:
    """Refuse before a byte is transformed."""

    for name, text in (("runner", runner), ("vendor", vendor)):
        declared = identity.get("%s_sha256" % name)
        actual = _digest(text)
        if declared != actual:
            raise fail_rule(
                RULE_INPUT_IDENTITY,
                "the %s source is %s and the pin says %s: this is not the input this "
                "experiment was designed against" % (name, actual[:16], str(declared)[:16]),
            )

    for key, expected in (
        ("q_reference_preboard_anchor", Q_REFERENCE_PREBOARD_ANCHOR),
        ("q_reference_board_evidence_anchor", Q_REFERENCE_BOARD_EVIDENCE_ANCHOR),
    ):
        if identity.get(key) != expected:
            raise fail_rule(
                RULE_Q_REFERENCE_IDENTITY,
                "the Q reference %s is %r and the qualified one is %r: a file that "
                "looks like Q is not the Q the campaign qualified"
                % (key, identity.get(key), expected),
            )

    for key, expected in (
        ("design_anchor", DESIGN_ANCHOR),
        ("plan_anchor", PLAN_ANCHOR),
    ):
        if identity.get(key) != expected:
            raise fail_rule(
                RULE_ANCHOR_IDENTITY,
                "the %s is %r and this generator belongs to %r"
                % (key, identity.get(key), expected),
            )


# ---------------------------------------------------------------------------
# The intervention surface
#
# V15 replaces the observable and nothing else, so the surface is declared as
# the substitutions themselves. The check is then exact rather than
# approximate: applying the declared substitutions to the input must reproduce
# the output, byte for byte. Anything the generator did beyond them shows up as
# a mismatch, and a line-by-line allowlist -- which has to be maintained and can
# be widened by whoever finds it inconvenient -- is not needed.
# ---------------------------------------------------------------------------

SUBSTITUTIONS = (
    ("qread = *qread_reg;", "status = *status_reg;"),
    (
        "if (qread == qsize_expected) { break; }",
        "if ((status & V15_STATUS_CMD_END) != 0U) { break; }",
    ),
    ("v14_primary_observe", "v15_primary_observe"),
    ("V14_ITERATION_BOUND", "V15_ITERATION_BOUND"),
)


def substitute(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def intervention_surface(before: str, after: str) -> dict:
    """Whether the output is exactly the declared substitutions applied."""

    expected = substitute(before)
    return {
        "substitutions": len(SUBSTITUTIONS),
        "within_expected_surface": after == expected,
        "unexpected_difference": None if after == expected else _first_difference(expected, after),
    }


def _first_difference(expected: str, actual: str) -> str:
    for left, right in zip(expected.splitlines(), actual.splitlines()):
        if left != right:
            return "expected %r, generated %r" % (left.strip()[:60], right.strip()[:60])
    extra = actual.splitlines()[len(expected.splitlines()):]
    if extra:
        return "generated %d line(s) the substitutions do not account for: %r" % (
            len(extra), extra[0].strip()[:60],
        )
    return "the generated file is shorter than the substitutions produce"


def check_intervention_surface(before: str, after: str) -> dict:
    """For text this process did not just produce: a build output, a file on disk."""

    surface = intervention_surface(before, after)
    if not surface["within_expected_surface"]:
        raise fail_rule(
            RULE_INTERVENTION_SURFACE,
            "the generated runner is not the declared substitutions applied: %s"
            % surface["unexpected_difference"],
        )
    return surface


def generate(runner: str, vendor: str, identity: dict) -> dict:
    """The pair, or a refusal. Nothing is produced when an input is wrong."""

    verify_inputs(runner, vendor, identity)

    generated = substitute(runner)

    # No surface check here on purpose. `substitute` is the only thing that
    # produced this text, so asking whether it equals `substitute(runner)` would
    # be asking a function whether it is itself -- a check that cannot fail is
    # worse than no check, because it reads like one. The surface check exists
    # for files that arrive from somewhere else: a generated pair on disk, or
    # one a build produced, where the question is real.
    return {
        "runner": generated,
        # The vendor translation unit is pinned and untouched: V15 changes what
        # the runner observes, not what the driver does.
        "vendor": vendor,
        "identity": dict(identity),
        "generated_runner_sha256": _digest(generated),
    }
