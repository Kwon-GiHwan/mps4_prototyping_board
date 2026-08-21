#!/usr/bin/env python3
"""From a parsed frame to a record, with each field's origin honoured.

parse_frame knows the wire and nothing else. This is the step after it, where
wire words, values derived from them, and facts that were never on the wire come
together into the twenty-four RECORD_FIELDS -- and the point of separating the
two steps is that this is the only place the three provenances meet, in the open,
under a mapping that says which is which.

comparison_mode and build_id come from the verified cell context, because the
target emits neither. Taking them from anywhere else, or letting them default,
would put back exactly the confusion Amendment 2 removed: a record field that
looks like it was measured and was not.

Derived fields are cross-checked rather than simply computed. The firmware
reports both a status word and its own reading of that word, and where the two
disagree the record is refused instead of one of them being preferred.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_HOST = os.path.dirname(os.path.abspath(__file__))
if _HOST not in sys.path:
    sys.path.insert(0, _HOST)

import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deployment  # noqa: E402
import runner_proto_pmu_completion_s5_only_control as wire  # noqa: E402

RULE_CONTEXT_REQUIRED = "RULE_CONTEXT_REQUIRED"
RULE_CONTEXT_VARIANT_MISMATCH = "RULE_CONTEXT_VARIANT_MISMATCH"
RULE_STATUS_SELF_CONTRADICTION = "RULE_STATUS_SELF_CONTRADICTION"
RULE_TIMESTAMPS_UNORDERED = "RULE_TIMESTAMPS_UNORDERED"
RULE_RECORD_FIELD_MISSING = "RULE_RECORD_FIELD_MISSING"

RULES = (
    "RULE_CONTEXT_REQUIRED",
    "RULE_CONTEXT_VARIANT_MISMATCH",
    "RULE_STATUS_SELF_CONTRADICTION",
    "RULE_TIMESTAMPS_UNORDERED",
    "RULE_RECORD_FIELD_MISSING",
)

VENDOR_SUCCESS = 0
CLEANUP_PASS = 0
CLEANUP_FAIL = 1


class NormalizeError(RuntimeError):
    """A record this module will not build."""


def fail_rule(rule: str, message: str) -> NormalizeError:
    return NormalizeError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


@dataclass(frozen=True)
class NormalizedRecord:
    """The twenty-four record fields, and the cell they belong to.

    fields is keyed by RECORD_FIELDS exactly. The context is kept beside the
    record rather than folded into it so that a record can always be traced to
    the deployment that licensed it.
    """

    fields: dict
    context: deployment.VerifiedCellContext

    @property
    def comparison_mode(self) -> str:
        return self.fields["comparison_mode"]

    def origin_of(self, name: str) -> str:
        return contract.RECORD_FIELD_ORIGINS[name]


def _derive(parsed) -> dict:
    """Values this host computes, each cross-checked against the wire."""

    status = parsed.first_status

    cmd_end_from_status = 1 if status & wire.STATUS_CMD_END else 0
    if cmd_end_from_status != (1 if parsed.first_cmd_end_reached else 0):
        raise fail_rule(
            RULE_STATUS_SELF_CONTRADICTION,
            "the status word 0x%08X %s the CMD_END bit and the firmware recorded "
            "first_cmd_end_reached=%d: preferring either one would be choosing which "
            "of the device's two statements to believe"
            % (status, "sets" if cmd_end_from_status else "clears",
               parsed.first_cmd_end_reached),
        )

    irq_from_status = 1 if status & wire.STATUS_IRQ_RAISED else 0
    if irq_from_status != (1 if parsed.first_irq_raised else 0):
        raise fail_rule(
            RULE_STATUS_SELF_CONTRADICTION,
            "the status word 0x%08X %s the IRQ_RAISED bit and the firmware recorded "
            "first_irq_raised=%d"
            % (status, "sets" if irq_from_status else "clears", parsed.first_irq_raised),
        )

    if parsed.t_first_observation < parsed.t_submit_after_cmd:
        raise fail_rule(
            RULE_TIMESTAMPS_UNORDERED,
            "the first observation is stamped %d and the submit %d: a negative interval "
            "is a wrapped or unsynchronised counter, not a fast run"
            % (parsed.t_first_observation, parsed.t_submit_after_cmd),
        )

    cleanup_clean = (
        parsed.nvic_pending_after_final_clear == 0
        and parsed.nvic_active_after_cleanup == 0
        and parsed.irq_triggered_after_cleanup == 0
    )
    return {
        "submit_to_s5_observed_cycles": parsed.t_first_observation - parsed.t_submit_after_cmd,
        "cmd_end_reached_observed": cmd_end_from_status,
        "status_at_success": status,
        "irq_raised_at_success": irq_from_status,
        "cleanup_result": CLEANUP_PASS if cleanup_clean else CLEANUP_FAIL,
    }


def normalize(parsed, context: deployment.VerifiedCellContext) -> NormalizedRecord:
    """One parsed frame plus the deployment that licensed it."""

    if not isinstance(context, deployment.VerifiedCellContext):
        raise fail_rule(
            RULE_CONTEXT_REQUIRED,
            "normalising needs a verified cell context. comparison_mode and build_id "
            "are not on the wire, and taking them from anywhere else is how a field "
            "that was never measured starts looking like one that was",
        )
    if parsed.variant != "S5":
        raise fail_rule(
            RULE_CONTEXT_VARIANT_MISMATCH,
            "the frame reports variant %s and this schema has one" % parsed.variant,
        )

    fields = {
        # WIRE_HEADER
        "schema_version": parsed.schema_version,
        "run_sequence": parsed.run_sequence,
        # WIRE_APPENDIX
        "variant_id": parsed.variant_id,
        "qsize_expected": parsed.qsize_expected,
        "pre_submit_status": parsed.pre_submit_status,
        "primary_iterations": parsed.primary_iterations,
        "primary_result": parsed.primary_result,
        "convergence_iterations": parsed.convergence_iterations,
        "convergence_result": parsed.convergence_result,
        "convergence_final_status": parsed.convergence_final_status,
        "convergence_final_qread": parsed.convergence_final_qread,
        "failure_phase": parsed.failure_phase,
        "failure_reason": parsed.failure_reason,
        "t_primary_entry": parsed.t_primary_entry,
        "t_first_observation": parsed.t_first_observation,
        "mailbox_magic": parsed.mailbox_valid,
        # STATIC_IMAGE_EVIDENCE -- from the context, never from the frame
        "build_id": contract.BUILD_ID,
        "comparison_mode": context.comparison_mode,
        # QUALIFICATION_METADATA
        "poll_count_admission": contract.POLL_COUNT_NOT_ADMITTED,
    }
    fields.update(_derive(parsed))

    missing = [name for name in contract.RECORD_FIELDS if name not in fields]
    if missing:
        raise fail_rule(
            RULE_RECORD_FIELD_MISSING,
            "the normalized record is missing %s" % ", ".join(sorted(missing)),
        )
    extra = [name for name in fields if name not in contract.RECORD_FIELDS]
    if extra:
        raise fail_rule(
            RULE_RECORD_FIELD_MISSING,
            "the normalized record carries %s, which is not a record field"
            % ", ".join(sorted(extra)),
        )
    return NormalizedRecord(fields=fields, context=context)


# ---------------------------------------------------------------------------
# Classification
#
# A sample is valid when the run did what it was asked and the device said so
# consistently. Invalid is a diagnostic outcome, not a measurement to be kept
# with a caveat, so the reasons are named and the sample is dropped from the
# distribution rather than down-weighted in it.
# ---------------------------------------------------------------------------

INVALID_PRIMARY_FAILED = "PRIMARY_DID_NOT_SUCCEED"
INVALID_CMD_END_NOT_OBSERVED = "CMD_END_NEVER_OBSERVED"
INVALID_FAULT_BITS = "STATUS_CARRIES_FAULT_BITS"
INVALID_CONVERGENCE_FAILED = "CONVERGENCE_DID_NOT_SUCCEED"
INVALID_CLEANUP_FAILED = "CLEANUP_INVARIANT_BROKEN"
INVALID_FAILURE_RECORDED = "FIRMWARE_RECORDED_A_FAILURE_PHASE"


def classify(record: NormalizedRecord) -> dict:
    """Whether this sample counts, and if not, exactly why."""

    fields = record.fields
    reasons = []
    if fields["primary_result"] != VENDOR_SUCCESS:
        reasons.append(INVALID_PRIMARY_FAILED)
    if not fields["cmd_end_reached_observed"]:
        reasons.append(INVALID_CMD_END_NOT_OBSERVED)
    if fields["status_at_success"] & wire.STATUS_FAULT_MASK:
        reasons.append(INVALID_FAULT_BITS)
    if fields["convergence_result"] != VENDOR_SUCCESS:
        reasons.append(INVALID_CONVERGENCE_FAILED)
    if fields["cleanup_result"] != CLEANUP_PASS:
        reasons.append(INVALID_CLEANUP_FAILED)
    if fields["failure_phase"] != 0:
        reasons.append(INVALID_FAILURE_RECORDED)

    return {
        "run_id": fields["run_sequence"],
        "boot_id": record.context.boot_id,
        "sample_valid": not reasons,
        "invalid_reasons": tuple(reasons),
        "submit_to_s5_observed_cycles": fields["submit_to_s5_observed_cycles"],
        "cmd_end_reached_observed": fields["cmd_end_reached_observed"],
        "status_at_success": fields["status_at_success"],
        "comparison_mode": fields["comparison_mode"],
        # Present, and admitted as a metric in nothing. Amendment 1.
        "poll_count": fields["primary_iterations"],
        "poll_count_admission": fields["poll_count_admission"],
        "candidate_identity": record.context.candidate_identity,
    }
