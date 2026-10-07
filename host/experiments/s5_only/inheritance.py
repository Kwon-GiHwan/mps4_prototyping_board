#!/usr/bin/env python3
"""What V15 inherits from V14, and on what terms.

Written before any V15 code exists, because this table is a design input rather
than a description. A matrix built after the implementation explains what was
built; a matrix built before it decides what must be proved.

Every claim carries exactly one class, and a claim with no class does not enter
implementation:

``UNCHANGED_AND_HASH_PINNED``
    the same object, pinned by hash and reachable in the V15 image. Nothing is
    re-proved because nothing changed, and the pin is what makes that checkable.
``REQUALIFIED_FOR_V15``
    the same claim, proved again against the V15 image. Inheriting the *rule* is
    not inheriting the *proof*: V14's evidence is about V14's executable.
``NOT_APPLICABLE``
    the concept does not exist in V15, with the reason recorded. A rule kept
    alive by feeding it a fabricated input is the silent-gate pattern this
    project has found eleven times.
``NEW_V15_CLAIM``
    did not exist in V14 at all.

"V14 already qualified this" is not an accepted answer anywhere in this file.
"""

from __future__ import annotations

UNCHANGED_AND_HASH_PINNED = "UNCHANGED_AND_HASH_PINNED"
REQUALIFIED_FOR_V15 = "REQUALIFIED_FOR_V15"
NOT_APPLICABLE = "NOT_APPLICABLE"
NEW_V15_CLAIM = "NEW_V15_CLAIM"

CLASSES = (UNCHANGED_AND_HASH_PINNED, REQUALIFIED_FOR_V15, NOT_APPLICABLE, NEW_V15_CLAIM)

# The V14 anchors this table is written against. An equivalence or inheritance
# result computed against anything else is void.
V14_REFERENCE = {
    "preboard_anchor": "619e957",
    "board_evidence_anchor": "153f368",
    "campaign_protocol": "7c3c124",
    "q_reference_artifacts": "FINAL8_A/Q/{APP,VECTORS,DDR}.BIN and their manifest",
    "q_reference_image": "FINAL8_A/Q/runner_pmu_completion_visibility_v14.{elf,objdump,nm}",
}


def _row(claim, klass, *, reason=None, proof=None, detector=None):
    return {"claim": claim, "class": klass, "reason": reason, "proof": proof,
            "detector": detector}


# ---------------------------------------------------------------------------
# V14's thirty-six load-bearing rules
# ---------------------------------------------------------------------------

INHERITED_RULES = (
    _row("RULE_PRE_PROGRAM_DOMINANCE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_NO_TRANSITION_BEFORE_PROGRAMMING", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRE_PROGRAM_GATE_SHAPE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRIMARY_READ_ORDER", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRIMARY_NO_PER_ITERATION_EFFECT", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRIMARY_NO_QSIZE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRIMARY_FAULT_PRIORITY", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_PRIMARY_IRQ_NOT_AN_EXIT", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_TAIL_SHARED", NOT_APPLICABLE,
         reason="one variant: there is no set of variants to share a tail across"),
    _row("RULE_TAIL_READ_ORDER", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_TAIL_FOUR_CONDITIONS", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_TAIL_BOUND", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_TAIL_NO_PER_ITERATION_EFFECT", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_READ_ORDER_EQUIVALENCE", NOT_APPLICABLE,
         reason="one variant: there is no second read order to be equivalent to"),
    _row("RULE_MAILBOX_PUBLISHED_ONCE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_MAILBOX_PUBLISHER_IDENTITY", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_MAILBOX_PUBLISH_ADDRESS", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_MAILBOX_PUBLISH_FENCED", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RUNNER_MAILBOX_GATED", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RUNNER_MAILBOX_READONLY", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RUNNER_MAILBOX_ONE_CHECK", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RUNNER_TUPLE_COMPLETE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_SERIALIZATION_LENGTH", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_SERIALIZATION_COUNTABLE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_SERIALIZATION_NAMED_CALLEES", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RECORD_SIZE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RECORD_APPENDIX_ORDER", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RECORD_APPENDIX_CONTIGUOUS", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_RECORD_APPENDIX_ENDS_RECORD", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_DWARF_RECORD_PRESENT", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_DWARF_MEMBER_READABLE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_DWARF_SIZE_PRESENT", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_DWARF_NM_AGREE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_NPU_IRQ_NEVER_ENABLED", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_NPU_IRQ_UNRESOLVED_WRITE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
    _row("RULE_STORE_FORM_UNREADABLE", REQUALIFIED_FOR_V15,
         proof="proved again on the V15 linked image"),
)


# ---------------------------------------------------------------------------
# Objects that do not change, and are pinned rather than re-proved
# ---------------------------------------------------------------------------

PINNED_OBJECTS = (
    _row("the frozen Arm u85.c vendor translation unit", UNCHANGED_AND_HASH_PINNED,
         proof="sha256 of the raw bytes, plus reachability of its terminal release in the V15 ELF"),
    _row("the vendor entry return code is not the verdict", UNCHANGED_AND_HASH_PINNED,
         proof="same frozen object; the V15 gate re-reads the pin rather than trusting V14's read"),
    _row("the V14 Q reference executable used for equivalence", UNCHANGED_AND_HASH_PINNED,
         proof="APP/VECTORS/DDR and ELF digests from the board-evidence anchor"),
)

# ---------------------------------------------------------------------------
# Claims V14 never made
# ---------------------------------------------------------------------------

NEW_CLAIMS = (
    _row("the S5 primary loop reads STATUS exactly once per iteration and tests bit5",
         NEW_V15_CLAIM, detector="verify_s5_only_boundary_image"),
    _row("the word the loop decided on is the word the record carries",
         NEW_V15_CLAIM, detector="verify_s5_only_boundary_image"),
    _row("the pre-freeze primary path reads QREAD zero times and QSIZE zero times",
         NEW_V15_CLAIM, detector="verify_s5_only_boundary_image"),
    _row("the post-freeze tail and cleanup match the frozen V14 Q reference semantically",
         NEW_V15_CLAIM, detector="verify_post_freeze_equivalence"),
    _row("the S5 primary loop is the Q primary loop up to the observable substitution",
         NEW_V15_CLAIM, detector="verify_single_register_equivalence"),
    _row("the comparison mode is one value, carried by every layer, and disagreement fails",
         NEW_V15_CLAIM, detector="verify_comparison_mode_propagation"),
    _row("the campaign verdict is one of S1..S6, permitted by the comparison mode",
         NEW_V15_CLAIM, detector="analyze_s5_only:verdict"),
    _row("no forbidden term appears in the analyzer's verdict vocabulary or report",
         NEW_V15_CLAIM, detector="analyze_s5_only:vocabulary"),
    _row("poll-count publication is admitted only at zero loop perturbation",
         NEW_V15_CLAIM, detector="verify_poll_count_admission"),
)

ALL_ROWS = INHERITED_RULES + PINNED_OBJECTS + NEW_CLAIMS


def summary():
    counts = {klass: 0 for klass in CLASSES}
    for row in ALL_ROWS:
        counts[row["class"]] += 1
    return {"total": len(ALL_ROWS), "by_class": counts}


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Where each requalified rule is actually re-proved
#
# "Inherited" is not a place. Every rule carried over names the layer whose
# answer will count for V15 and the task that produces it, so that a rule which
# is never applied shows up as a missing entry rather than as an assumption
# nobody wrote down.
#
# The distribution is worth noticing: of the thirty-four, exactly one is decided
# on the source. The rest are claims about what the compiler emitted, and the
# plan's phrase "inherit the rest of the V14 source contract" was larger than
# what exists at that layer.
# ---------------------------------------------------------------------------

# Enforcement status. Deliberately not the word "qualified": a rule can be
# re-proved on the V15 source and still be waiting for the layer whose answer
# finally counts. Saying QUALIFIED at the source layer would retire a claim that
# the compiler has not yet been asked about.
NOT_YET_APPLIED = "NOT_YET_APPLIED"
SOURCE_REQUALIFIED = "SOURCE_CONTRACT_REQUALIFIED"
ELF_REQUALIFIED = "ELF_REQUALIFIED"
STATUSES = (NOT_YET_APPLIED, SOURCE_REQUALIFIED, ELF_REQUALIFIED)

APPLICATION = {
    "RULE_PRE_PROGRAM_DOMINANCE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_NO_TRANSITION_BEFORE_PROGRAMMING": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_PRE_PROGRAM_GATE_SHAPE": ("source/generator", "Task 3", NOT_YET_APPLIED),
    "RULE_PRIMARY_READ_ORDER": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_PRIMARY_NO_PER_ITERATION_EFFECT": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_PRIMARY_NO_QSIZE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_PRIMARY_FAULT_PRIORITY": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_PRIMARY_IRQ_NOT_AN_EXIT": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_TAIL_READ_ORDER": ("linked ELF", "Task 8", NOT_YET_APPLIED),
    "RULE_TAIL_FOUR_CONDITIONS": ("linked ELF", "Task 8", NOT_YET_APPLIED),
    "RULE_TAIL_BOUND": ("linked ELF", "Task 8", NOT_YET_APPLIED),
    "RULE_TAIL_NO_PER_ITERATION_EFFECT": ("linked ELF", "Task 8", NOT_YET_APPLIED),
    "RULE_MAILBOX_PUBLISHED_ONCE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_MAILBOX_PUBLISHER_IDENTITY": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_MAILBOX_PUBLISH_ADDRESS": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_MAILBOX_PUBLISH_FENCED": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RUNNER_MAILBOX_GATED": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RUNNER_MAILBOX_READONLY": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RUNNER_MAILBOX_ONE_CHECK": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RUNNER_TUPLE_COMPLETE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_SERIALIZATION_LENGTH": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_SERIALIZATION_COUNTABLE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_SERIALIZATION_NAMED_CALLEES": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RECORD_SIZE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RECORD_APPENDIX_ORDER": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RECORD_APPENDIX_CONTIGUOUS": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_RECORD_APPENDIX_ENDS_RECORD": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_DWARF_RECORD_PRESENT": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_DWARF_MEMBER_READABLE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_DWARF_SIZE_PRESENT": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_DWARF_NM_AGREE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_NPU_IRQ_NEVER_ENABLED": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_NPU_IRQ_UNRESOLVED_WRITE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
    "RULE_STORE_FORM_UNREADABLE": ("linked ELF", "Task 6", NOT_YET_APPLIED),
}


# ---------------------------------------------------------------------------
# Claims proved on the real V15 image
#
# Promoted only after the detector refused a fixture aimed at each of its rules
# *and* passed the real image. A claim reaching ELF_REQUALIFIED because a
# neighbouring one did would be the promotion this project keeps refusing.
# ---------------------------------------------------------------------------

ELF_PROVED = {
    "S5 primary-only boundary": {
        "detector": "verify_s5_only_boundary_image",
        "rule": "RULE_V15_PRIMARY_S5_ONLY",
        "negatives": (
            "QREAD read planted in the loop",
            "QSIZE read planted in the loop",
            "unrelated MMIO (CMD) read planted in the loop",
            "mask moved from bit5 to bit1",
            "a second STATUS read",
        ),
        "status": ELF_REQUALIFIED,
    },
    "the deciding word is the recorded word": {
        "detector": "verify_s5_only_boundary_image",
        "rule": "RULE_V15_IRQ_FROM_DECIDING_WORD",
        "negatives": ("STATUS reloaded into the deciding register after the loop",),
        "status": ELF_REQUALIFIED,
    },
    "pinned helper identity": {
        "detector": "verify_helper_identity",
        "rule": "RULE_V15_HELPER_IDENTITY",
        "negatives": ("a pinned helper whose digest no longer matches",),
        "status": ELF_REQUALIFIED,
    },
    "Q-to-S5 single-register equivalence": {
        "detector": "verify_single_register_equivalence",
        "rule": "RULE_EQUIVALENCE_LOOP_SHAPE",
        "negatives": (
            "an extra per-iteration instruction",
            "an extra SRAM store",
            "a QREAD read planted in S5",
            "a changed timeout topology",
            "a moved first-observation freeze",
            "the observable load reaching a stack slot rather than MMIO",
            "a wrong Q reference identity",
        ),
        "status": ELF_REQUALIFIED,
    },
}
