#!/usr/bin/env python3
"""One comparison mode, carried by every layer, agreeing or failing.

The design's fallback -- if Q-to-S5 equivalence fails, V15 retreats to
within-variant claims -- was specified and unenforced. Nothing in the pipeline
behaved differently in fallback mode, so the retreat would have been a sentence
in a document while the analyzer went on comparing. That is the failure this
module exists to make impossible.

The mode is a value. It starts at the firmware evidence, and the manifest, the
parser, the classifier, the collector, the analyzer, the board preflight and the
final report each carry it. Disagreement between any two of them is a refusal,
not a vote: a mode decided by counting layers is a mode nobody set.

And it has to match the evidence it claims to summarise. A chain that says
Q_S5_EQUIVALENT while the equivalence detector refused is the exact forgery the
review asked to be made impossible, so the resolution reads both.
"""

from __future__ import annotations

import contract_pmu_completion_s5_only_control as contract

RULE_MODE_MISSING_LAYER = "RULE_MODE_MISSING_LAYER"
RULE_MODE_UNKNOWN_LAYER = "RULE_MODE_UNKNOWN_LAYER"
RULE_MODE_DISAGREEMENT = "RULE_MODE_DISAGREEMENT"
RULE_MODE_UNKNOWN_VALUE = "RULE_MODE_UNKNOWN_VALUE"
RULE_MODE_CONTRADICTS_EVIDENCE = "RULE_MODE_CONTRADICTS_EVIDENCE"
RULE_MODE_REFERENCE_IDENTITY = "RULE_MODE_REFERENCE_IDENTITY"
RULE_MODE_CROSS_VARIANT_LEAK = "RULE_MODE_CROSS_VARIANT_LEAK"

RULES = (
    "RULE_MODE_MISSING_LAYER",
    "RULE_MODE_UNKNOWN_LAYER",
    "RULE_MODE_DISAGREEMENT",
    "RULE_MODE_UNKNOWN_VALUE",
    "RULE_MODE_CONTRADICTS_EVIDENCE",
    "RULE_MODE_REFERENCE_IDENTITY",
    "RULE_MODE_CROSS_VARIANT_LEAK",
)

# In the order evidence flows. Every one of them carries the mode, because a
# layer that does not carry it is a layer where the fallback stops travelling.
#
# Amendment 2 corrected the first layer and removed the parser. The chain used
# to begin at "firmware_evidence", which read as though the mode arrived in the
# frame; it does not appear in any of the 127 words, and it could not, because
# the mode says whether this image's loop matches the frozen V14 Q reference and
# the target cannot determine that. The mode begins in static image evidence and
# reaches a run through a deployment context verified by hash.
#
# The parser is deliberately absent. parse_frame sees bytes and nothing else, so
# a parser carrying the mode would be a parser asserting something it was not
# told by the device.
LAYERS = (
    "static_image_evidence",
    "build_manifest",
    "verified_deployment_context",
    "collector",
    "normalized_record",
    "classifier",
    "analyzer",
    "report",
)

# Requalified 2026-08-21 against the real candidate: gates re-run on the
# canonical analysis ELFs, real equivalence and static evidence, a real sealed
# manifest, and the mode resolved through that chain rather than through
# synthetic dictionaries.
#
# It stops short of a board. verified_deployment_context requires comparing what
# was deployed against what landed, so the last two layers are not yet carrying
# a mode that reached a run. The status says so rather than rounding up.
END_TO_END_STATUS = "E2E_REQUALIFIED"
# Closed 2026-08-23 by the formal campaign: thirty samples across three fresh
# boots, the mode carried from static image evidence through to the analyzer's
# verdict on real frames rather than synthetic dictionaries.
REQUALIFIED_LAYERS = LAYERS
PENDING_LAYERS = ()
REQUALIFICATION_EVIDENCE = "docs/superpowers/evidence/v15-campaign-20260823"

EQUIVALENCE_PASS = "PASS"
EQUIVALENCE_FALLBACK = "FALLBACK_WITHIN_VARIANT"

Q_REFERENCE_ANCHOR = "153f368"

# Which equivalence outcome licenses which mode. Written as a table so that a
# third outcome cannot be handled by whichever branch happens to catch it.
MODE_FOR_EVIDENCE = {
    EQUIVALENCE_PASS: contract.Q_S5_EQUIVALENT,
    EQUIVALENCE_FALLBACK: contract.S5_WITHIN_VARIANT_ONLY,
}


class ComparisonModeError(RuntimeError):
    """A chain whose mode this module will not resolve."""


def fail_rule(rule: str, message: str) -> ComparisonModeError:
    return ComparisonModeError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def resolve(layers: dict, equivalence: dict, cross_variant_claims_enabled=None) -> dict:
    """The one mode this run is in, or a refusal naming why it has none."""

    missing = [name for name in LAYERS if name not in layers]
    if missing:
        raise fail_rule(
            RULE_MODE_MISSING_LAYER,
            "these layers carry no comparison mode: %s. A layer that does not carry it "
            "is where the fallback stops travelling" % ", ".join(missing),
        )

    # A name that is not a layer is not a layer that agreed. When the chain was
    # renamed, a fixture kept setting the mode on "preflight" and the check
    # simply stopped seeing it: the test passed by testing nothing.
    foreign = [name for name in layers if name not in LAYERS]
    if foreign:
        raise fail_rule(
            RULE_MODE_UNKNOWN_LAYER,
            "these are not layers of this chain: %s. A mode set on a name nobody "
            "reads is a mode nobody carries" % ", ".join(sorted(foreign)),
        )

    unknown = {
        name: value
        for name, value in layers.items()
        if value not in contract.COMPARISON_MODES
    }
    if unknown:
        name, value = sorted(unknown.items())[0]
        raise fail_rule(
            RULE_MODE_UNKNOWN_VALUE,
            "%s carries %r, which is neither %s"
            % (name, value, " nor ".join(contract.COMPARISON_MODES)),
        )

    distinct = sorted({layers[name] for name in LAYERS})
    if len(distinct) != 1:
        disagreeing = sorted(
            "%s=%s" % (name, layers[name]) for name in LAYERS
        )
        raise fail_rule(
            RULE_MODE_DISAGREEMENT,
            "the layers do not agree on the comparison mode (%s): this is a failure "
            "rather than a vote, and no majority resolves it" % ", ".join(disagreeing),
        )
    mode = distinct[0]

    status = equivalence.get("status")
    if status not in MODE_FOR_EVIDENCE:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE,
            "the equivalence evidence says %r, which licenses no mode" % (status,),
        )
    licensed = MODE_FOR_EVIDENCE[status]
    if mode != licensed:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE,
            "the chain claims %s and the equivalence evidence is %s, which licenses %s"
            % (mode, status, licensed),
        )

    if status == EQUIVALENCE_PASS:
        if not equivalence.get("evidence_sha256"):
            raise fail_rule(
                RULE_MODE_CONTRADICTS_EVIDENCE,
                "the equivalence claims PASS and carries no evidence digest: a mode "
                "resting on an unrecorded comparison is a mode resting on nothing",
            )
        if equivalence.get("reference_anchor") != Q_REFERENCE_ANCHOR:
            raise fail_rule(
                RULE_MODE_REFERENCE_IDENTITY,
                "the equivalence passed against reference %r and the qualified one is "
                "%r: a structurally similar Q is not the Q this mode means"
                % (equivalence.get("reference_anchor"), Q_REFERENCE_ANCHOR),
            )

    enabled = (
        mode == contract.Q_S5_EQUIVALENT
        if cross_variant_claims_enabled is None
        else cross_variant_claims_enabled
    )
    if mode == contract.S5_WITHIN_VARIANT_ONLY and enabled:
        raise fail_rule(
            RULE_MODE_CROSS_VARIANT_LEAK,
            "the mode is the fallback and cross-variant claims are still enabled: the "
            "retreat has to reach the thing that would do the comparing",
        )

    return {
        "comparison_mode": mode,
        "layers_agreeing": len(LAYERS),
        "cross_variant_claims_enabled": enabled,
        "outcomes_permitted": contract.OUTCOMES_PERMITTED[mode],
        "reason": contract.FALLBACK_REASON
        if mode == contract.S5_WITHIN_VARIANT_ONLY
        else None,
        "equivalence_status": status,
        "reference_anchor": equivalence.get("reference_anchor"),
    }
