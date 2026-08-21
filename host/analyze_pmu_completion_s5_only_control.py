#!/usr/bin/env python3
"""The S5-only campaign's verdict, from a closed set fixed before the data.

Preregistering six outcomes is worth nothing if the analyzer can look at what
came back and write a sentence about it. So the outcome is a value from a set,
the set narrows with the comparison mode, and the two things that could quietly
widen it -- a free-text conclusion and the poll count -- are refused by name.

The floor and excursion definitions are copied here rather than referred to,
because a definition that lives somewhere else is a definition somebody can
reinterpret at analysis time.
"""

from __future__ import annotations

import contract_pmu_completion_s5_only_control as contract

RULE_OUTCOME_UNKNOWN = "RULE_OUTCOME_UNKNOWN"
RULE_OUTCOME_NOT_PERMITTED = "RULE_OUTCOME_NOT_PERMITTED"
RULE_POLL_COUNT_NOT_ADMITTED = "RULE_POLL_COUNT_NOT_ADMITTED"
RULE_FORBIDDEN_VOCABULARY = "RULE_FORBIDDEN_VOCABULARY"

RULES = (
    "RULE_OUTCOME_UNKNOWN",
    "RULE_OUTCOME_NOT_PERMITTED",
    "RULE_POLL_COUNT_NOT_ADMITTED",
    "RULE_FORBIDDEN_VOCABULARY",
)

FLOOR_DEFINITION = (
    "a reproduced floor is one value that is the minimum of every boot taken "
    "separately; pooling the boots before classifying them is prohibited, and an "
    "excursion is a sample above its own boot's minimum"
)

# Terms that would describe the CPU's observation as the device's internal
# event, or one variant as faster than another. Checked against the analyzer's
# own output rather than against a document.
FORBIDDEN_TERMS = (
    "latency",
    "t_npu",
    "faster",
    "slower",
    "internal completion",
    "npu completion",
    "execution time",
)


class AnalysisError(RuntimeError):
    """A verdict this analyzer will not reach."""


def fail_rule(rule: str, message: str) -> AnalysisError:
    return AnalysisError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def emit(outcome: str, comparison_mode: str, decided_by: str | None = None) -> str:
    """The one way an outcome leaves this module."""

    if outcome not in contract.OUTCOMES:
        raise fail_rule(
            RULE_OUTCOME_UNKNOWN,
            "%r is not one of the preregistered outcomes %s"
            % (outcome, ", ".join(contract.OUTCOMES)),
        )
    permitted = contract.OUTCOMES_PERMITTED[comparison_mode]
    if outcome not in permitted:
        raise fail_rule(
            RULE_OUTCOME_NOT_PERMITTED,
            "%s is not available under %s: %s"
            % (outcome, comparison_mode, contract.FALLBACK_REASON),
        )
    if decided_by == "poll_count":
        raise fail_rule(
            RULE_POLL_COUNT_NOT_ADMITTED,
            "the poll count is present in the record and admitted as a metric in "
            "nothing: it may not decide an outcome",
        )
    return outcome


def narrate(outcome: str, text: str) -> str:
    """Prose about a verdict, checked for the words it may not use."""

    lowered = text.lower()
    for term in FORBIDDEN_TERMS:
        if term in lowered:
            raise fail_rule(
                RULE_FORBIDDEN_VOCABULARY,
                "the narrative uses %r, which describes the observation as if it were "
                "the device's own event or one variant as quicker than another" % term,
            )
    return "%s: %s" % (outcome, text)


def _boot_structure(entry: dict) -> dict:
    values = [
        sample["submit_to_s5_observed_cycles"]
        for sample in entry["samples"]
        if sample.get("sample_valid")
    ]
    if not values:
        return {"boot_id": entry["boot_id"], "minimum": None, "excursions": 0, "valid": 0}
    minimum = min(values)
    return {
        "boot_id": entry["boot_id"],
        "minimum": minimum,
        "excursions": sum(1 for value in values if value > minimum),
        "valid": len(values),
    }


def analyze(campaign: dict) -> dict:
    """Which of the six this campaign is, and nothing beyond it."""

    mode = campaign.get("comparison_mode")
    if mode not in contract.COMPARISON_MODES:
        raise fail_rule(
            RULE_OUTCOME_UNKNOWN, "the campaign carries comparison mode %r" % (mode,)
        )
    permitted = contract.OUTCOMES_PERMITTED[mode]
    boots = [_boot_structure(entry) for entry in campaign["boots"]]

    # The observable was never seen: a diagnostic failure state, not a shape.
    if all(structure["valid"] == 0 for structure in boots):
        outcome = "S5"
    else:
        minima = {structure["minimum"] for structure in boots}
        reproduced = len(minima) == 1 and None not in minima
        with_excursions = sum(1 for structure in boots if structure["excursions"])
        if not reproduced:
            outcome = "S4"
        elif with_excursions == len(boots):
            outcome = "S1"
        elif with_excursions == 0:
            outcome = "S2"
        else:
            # Some boots show excursions and some do not. Registered in advance
            # as boot-dependent precisely so that "two of three" cannot become a
            # reproduction criterion once the data is in.
            outcome = "S6"

    return {
        "outcome": emit(outcome, mode),
        "comparison_mode": mode,
        "outcomes_permitted": permitted,
        "floor_definition": FLOOR_DEFINITION,
        "boots": boots,
        # Present in every record, admitted as a metric in none. Recorded so the
        # distinction is visible in the verdict rather than only in a document.
        "poll_count_transport": contract.POLL_COUNT_PRESENT,
        "poll_count_admission": contract.POLL_COUNT_NOT_ADMITTED,
    }
