#!/usr/bin/env python3
"""Schema-15 contract constants for the STATUS bit5-only control.

One experiment, one observable, and a vocabulary chosen so that the record
cannot be read as saying more than it does. That last part is not fussiness:
what a field is called travels into every report built on it, and a field named
for a hardware event the CPU never saw would license a sentence nobody is
entitled to write, permanently.

So the primary observation is named for the act of observing it --
``cmd_end_reached_observed``, ``submit_to_s5_observed_cycles`` -- and the names
this contract refuses are listed rather than merely avoided, so that a test can
check the refusal instead of trusting it.
"""

from __future__ import annotations

EXPERIMENT_NAME = "PMU_COMPLETION_S5_ONLY_CONTROL"
SCHEMA_VERSION = 15

# 'PI15' little-endian, in the family the earlier experiments used. Distinct from
# V14's build id so a V14 frame can never be read as a V15 one.
PI15_FAMILY = 0x3531  # '15'
BUILD_ID = 0x49503531  # 'PI15'

# ---------------------------------------------------------------------------
# The observable
# ---------------------------------------------------------------------------

STATUS_CMD_END = 0x020
"""bit5. The one the primary loop tests, and the only exit condition it has."""

STATUS_IRQ_RAISED = 0x002
"""bit1. Kept as supporting evidence, never as a reason to leave the loop."""

IRQ_SCOPE = (
    "read out of the same raw STATUS word the deciding bit5 test used; a second "
    "read would rebuild the perturbation this control exists to remove"
)

# ---------------------------------------------------------------------------
# Comparison mode
#
# The design's fallback is only real if it is carried rather than described, so
# it is a value here and every layer passes it on. Disagreement between layers
# is a failure, not something to be resolved in favour of whichever layer is
# more convenient.
# ---------------------------------------------------------------------------

Q_S5_EQUIVALENT = "Q_S5_EQUIVALENT"
S5_WITHIN_VARIANT_ONLY = "S5_WITHIN_VARIANT_ONLY"
COMPARISON_MODES = (Q_S5_EQUIVALENT, S5_WITHIN_VARIANT_ONLY)

FALLBACK_REASON = "Q_S5_EQUIVALENCE_NOT_ESTABLISHED"

OUTCOMES = ("S1", "S2", "S3", "S4", "S5", "S6")

OUTCOMES_PERMITTED = {
    Q_S5_EQUIVALENT: OUTCOMES,
    # S3 is "the excursion structure differs qualitatively from Q". Without an
    # established equivalence there is no Q to differ from, so the verdict is
    # not available -- not merely unlikely, unavailable.
    S5_WITHIN_VARIANT_ONLY: ("S1", "S2", "S4", "S5", "S6"),
}

# ---------------------------------------------------------------------------
# The normalized host record
#
# This list is NOT the wire appendix and never was. The firmware emits 34 words;
# eleven of the names below are frame header words or values this host derives.
# It carried a "in wire order" comment until Amendment 2, and the Task 10 parser
# would have been its first consumer -- zipping 24 names onto 34 words truncates
# silently and yields plausible numbers from misaligned slots.
#
# The wire appendix lives in runner_proto_pmu_completion_s5_only_control and is
# the firmware tuple exactly. This is what the normalizer produces afterwards.
# Where each of these comes from is RECORD_FIELD_ORIGINS below, which is a
# contract rather than a comment: without it the three provenances drift back
# into one list under a better name.
# ---------------------------------------------------------------------------

RECORD_FIELDS = (
    "schema_version",
    "build_id",
    "variant_id",
    "run_sequence",
    "comparison_mode",
    "pre_submit_status",
    "qsize_expected",
    "submit_to_s5_observed_cycles",
    "cmd_end_reached_observed",
    "status_at_success",
    "irq_raised_at_success",
    "primary_iterations",
    "primary_result",
    "convergence_iterations",
    "convergence_result",
    "convergence_final_status",
    "convergence_final_qread",
    "cleanup_result",
    "failure_phase",
    "failure_reason",
    "t_primary_entry",
    "t_first_observation",
    "poll_count_admission",
    "mailbox_magic",
)

# ---------------------------------------------------------------------------
# Where each record field comes from
#
# Amendment 2 made this a contract rather than a comment. One list held three
# provenances at once and said "wire order" about all of them; the correction is
# not a better name but an authoritative mapping, because a renamed list drifts
# back to mixed exactly as fast as the original did.
#
# Declaring a field WIRE_APPENDIX makes a checkable claim: that name must appear
# in the firmware's 34-word tuple. runner_proto verifies it, so a wrong
# declaration fails rather than reads well.
# ---------------------------------------------------------------------------

WIRE_HEADER = "WIRE_HEADER"
WIRE_APPENDIX = "WIRE_APPENDIX"
DERIVED_FROM_WIRE = "DERIVED_FROM_WIRE"
STATIC_IMAGE_EVIDENCE = "STATIC_IMAGE_EVIDENCE"
QUALIFICATION_METADATA = "QUALIFICATION_METADATA"

FIELD_ORIGINS = (
    WIRE_HEADER,
    WIRE_APPENDIX,
    DERIVED_FROM_WIRE,
    STATIC_IMAGE_EVIDENCE,
    QUALIFICATION_METADATA,
)

RECORD_FIELD_ORIGINS = {
    "schema_version": WIRE_HEADER,
    "run_sequence": WIRE_HEADER,
    # Not in the frame. V14 established that image identity is a manifest field
    # checked by verify_manifest(), and V15 keeps it there.
    "build_id": STATIC_IMAGE_EVIDENCE,
    # Whether the V15 loop matches the frozen V14 Q reference is decided by
    # host-side ELF analysis. The target cannot determine it, so no wire word
    # could honestly carry it.
    "comparison_mode": STATIC_IMAGE_EVIDENCE,
    "variant_id": WIRE_APPENDIX,
    "qsize_expected": WIRE_APPENDIX,
    "pre_submit_status": WIRE_APPENDIX,
    "primary_iterations": WIRE_APPENDIX,
    "primary_result": WIRE_APPENDIX,
    "convergence_iterations": WIRE_APPENDIX,
    "convergence_result": WIRE_APPENDIX,
    "convergence_final_status": WIRE_APPENDIX,
    "convergence_final_qread": WIRE_APPENDIX,
    "failure_phase": WIRE_APPENDIX,
    "failure_reason": WIRE_APPENDIX,
    "t_primary_entry": WIRE_APPENDIX,
    "t_first_observation": WIRE_APPENDIX,
    # The firmware word is mailbox_valid; this record names the same word.
    "mailbox_magic": WIRE_APPENDIX,
    # Computed by the normalizer from wire words. Named separately from the
    # words they come from so that a derived value is never mistaken for one
    # the device reported.
    "submit_to_s5_observed_cycles": DERIVED_FROM_WIRE,
    "cmd_end_reached_observed": DERIVED_FROM_WIRE,
    "status_at_success": DERIVED_FROM_WIRE,
    "irq_raised_at_success": DERIVED_FROM_WIRE,
    "cleanup_result": DERIVED_FROM_WIRE,
    # Present in the record, admitted as a metric in nothing. Amendment 1.
    "poll_count_admission": QUALIFICATION_METADATA,
}

# ---------------------------------------------------------------------------
# Names this contract refuses
#
# Each of these would describe the CPU's observation as if it were the device's
# internal event. What the record holds is the end of a chain -- internal
# transition, register visibility, MMIO sampling, CPU observation -- and only the
# last link is measured. This module has to name them in order to refuse them;
# every other module in the chain must not contain them at all, which is what the
# test actually scans for.
# ---------------------------------------------------------------------------

FORBIDDEN_FIELD_NAMES = (
    "internal_completion_cycles",
    "npu_completion_timestamp",
    "T_npu",
    "execution_latency",
)

# ---------------------------------------------------------------------------
# Poll count: two axes, because one enum told a lie
#
# The measured comparison came out against admission -- publishing the count
# costs one instruction per iteration against a no-publication S5 -- and the
# criterion that says so is the frozen one and stays. But removing the counter
# changes the primary loop's shape against the frozen V14 Q reference, which
# breaks the matched control V15 exists to be. So the instruction stays and the
# metric does not.
#
# A single enum could not say that. "OMITTED" reads as a lie about a field that
# is present in the record, so presence and admission are separate values.
# ---------------------------------------------------------------------------

POLL_COUNT_PRESENT = "PRESENT_REFERENCE_MATCHED"
POLL_COUNT_ABSENT = "ABSENT"
POLL_COUNT_TRANSPORT = (POLL_COUNT_PRESENT, POLL_COUNT_ABSENT)

POLL_COUNT_ADMITTED = "ADMITTED"
POLL_COUNT_NOT_ADMITTED = "NOT_ADMITTED_DUE_TO_LOOP_PERTURBATION"
POLL_COUNT_ADMISSION = (POLL_COUNT_ADMITTED, POLL_COUNT_NOT_ADMITTED)

# What the analyzer may do with a value that is present and not admitted:
# record that it is there. Nothing else.
POLL_COUNT_FORBIDDEN_USES = (
    "choosing among S1..S6",
    "regression against cycles",
    "a histogram offered as evidence",
    "comparison between Q and S5",
    "poll count multiplied by loop cost as a visibility latency",
)
