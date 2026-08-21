#!/usr/bin/env python3
"""Collecting runs against a deployment that was already verified.

The collector's job is narrow on purpose. It takes a VerifiedCellContext as an
opaque capability -- something already established elsewhere -- and live frames,
and it turns them into a cell and a campaign. It does not re-adjudicate ELF
equivalence, recompute manifest qualification, infer a comparison mode or decide
what the V14 reference is. Every one of those was settled before a cell could be
opened, and re-deciding any of them here would mean two authorities for one
fact.

The consequence worth stating: when the V14 Q reference pin lands, nothing in
this module changes. What changes is that open_verified_cell starts succeeding
for a real candidate.

The one failure mode this inherits deliberately from V14 is that an
unacceptable run ends the attempt instead of raising. Raising alone was the
defect: a caller could catch the error, offer the run again, and turn nine good
runs and one bad one into a ten-run cell.
"""

from __future__ import annotations

import hashlib
import os
import sys

_HOST = os.path.dirname(os.path.abspath(__file__))
if _HOST not in sys.path:
    sys.path.insert(0, _HOST)

import deployment_pmu_completion_s5_only_control as deployment  # noqa: E402
import normalize_pmu_completion_s5_only_control as normalizer  # noqa: E402
import runner_proto_pmu_completion_s5_only_control as wire  # noqa: E402

RUNS_PER_CELL = 10
BOOTS_PER_CAMPAIGN = 3

RULE_CONTEXT_REQUIRED = "RULE_CONTEXT_REQUIRED"
RULE_CONTEXT_CHANGED_MID_CELL = "RULE_CONTEXT_CHANGED_MID_CELL"
RULE_RUN_OUT_OF_ORDER = "RULE_RUN_OUT_OF_ORDER"
RULE_INVALID_SAMPLE_ENDS_ATTEMPT = "RULE_INVALID_SAMPLE_ENDS_ATTEMPT"
RULE_CELL_ALREADY_COMPLETE = "RULE_CELL_ALREADY_COMPLETE"
RULE_CELL_INCOMPLETE = "RULE_CELL_INCOMPLETE"
RULE_ATTEMPT_IS_OVER = "RULE_ATTEMPT_IS_OVER"
RULE_MODE_CHANGED_MID_CAMPAIGN = "RULE_MODE_CHANGED_MID_CAMPAIGN"

RULES = (
    "RULE_CONTEXT_REQUIRED",
    "RULE_CONTEXT_CHANGED_MID_CELL",
    "RULE_RUN_OUT_OF_ORDER",
    "RULE_INVALID_SAMPLE_ENDS_ATTEMPT",
    "RULE_CELL_ALREADY_COMPLETE",
    "RULE_CELL_INCOMPLETE",
    "RULE_ATTEMPT_IS_OVER",
    "RULE_MODE_CHANGED_MID_CAMPAIGN",
)


class CollectorError(RuntimeError):
    """A refusal with a reason. Never raised for something the board did."""


def fail_rule(rule: str, message: str) -> CollectorError:
    return CollectorError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def frame_digest(payload: bytes) -> str:
    """The digest recorded for a frame, over the bytes as received."""

    return hashlib.sha256(payload).hexdigest()


class Cell:
    """Ten consecutive runs from one boot, under one verified deployment."""

    def __init__(self, context):
        if not isinstance(context, deployment.VerifiedCellContext):
            raise fail_rule(
                RULE_CONTEXT_REQUIRED,
                "a cell is opened against a verified deployment. Collecting without "
                "one would produce samples nothing ties to an image, which is the "
                "provenance the frame itself cannot supply",
            )
        self.context = context
        self.samples: list[dict] = []
        self.frames: list[str] = []
        self.boot_id: str | None = None
        self.dead: str | None = None

    @property
    def complete(self) -> bool:
        return len(self.samples) == RUNS_PER_CELL

    def _end(self, reason: str, rule: str):
        self.dead = reason
        raise fail_rule(rule, "cell attempt ended: %s" % reason)

    def record(self, payload: bytes, context=None) -> dict:
        """Accept one raw frame, or end the attempt.

        The context argument exists so a caller that thinks it is switching
        candidates mid-cell is refused rather than ignored.
        """

        if self.dead:
            raise fail_rule(RULE_ATTEMPT_IS_OVER, "this attempt is over: %s" % self.dead)
        if self.complete:
            raise fail_rule(
                RULE_CELL_ALREADY_COMPLETE,
                "the cell already carries its %d runs" % RUNS_PER_CELL,
            )
        if context is not None and context is not self.context:
            self._end(
                "the cell was opened under candidate %s and run %d was offered under %s"
                % (
                    self.context.candidate_identity[:16],
                    len(self.samples) + 1,
                    getattr(context, "candidate_identity", "?")[:16],
                ),
                RULE_CONTEXT_CHANGED_MID_CELL,
            )

        parsed = wire.parse_frame(payload)
        record = normalizer.normalize(parsed, self.context)
        sample = normalizer.classify(record)

        expected = len(self.samples) + 1
        if sample["run_id"] != expected:
            self._end(
                "expected run %d, was offered run %s" % (expected, sample["run_id"]),
                RULE_RUN_OUT_OF_ORDER,
            )
        # There is no separate boot check here on purpose. boot_id reaches the
        # sample from the cell's own context, so a "boot changed mid-cell" test
        # would compare a value against itself and could never fire. A boot
        # change means a different context, and that is refused above.
        if not sample["sample_valid"]:
            self._end(
                "run %d is not a valid sample (%s)"
                % (sample["run_id"], ", ".join(sample["invalid_reasons"])),
                RULE_INVALID_SAMPLE_ENDS_ATTEMPT,
            )

        if self.boot_id is None:
            self.boot_id = sample["boot_id"]
        self.samples.append(sample)
        self.frames.append(frame_digest(payload))
        return sample

    def bundle(self) -> dict:
        """What this cell contributes as evidence."""

        if not self.complete:
            raise fail_rule(
                RULE_CELL_INCOMPLETE,
                "the cell carries %d of %d runs and a short cell is not a cell"
                % (len(self.samples), RUNS_PER_CELL),
            )
        context = self.context
        return {
            "boot_id": self.boot_id,
            "comparison_mode": context.comparison_mode,
            "candidate_identity": context.candidate_identity,
            "deployment": {
                "app_sha256": context.app_sha256,
                "vectors_sha256": context.vectors_sha256,
                "ddr_sha256": context.ddr_sha256,
                "elf_sha256": context.elf_sha256,
                "manifest_sha256": context.manifest_sha256,
                "static_evidence_sha256": context.static_evidence_sha256,
                "equivalence_evidence_sha256": context.equivalence_evidence_sha256,
                "v14_q_reference_identity": context.v14_q_reference_identity,
            },
            "raw_frame_sha256": tuple(self.frames),
            "run_sequence": tuple(sample["run_id"] for sample in self.samples),
            "samples": tuple(self.samples),
        }


class Campaign:
    """Three boots of ten runs, all under one comparison mode."""

    def __init__(self):
        self.cells: list[Cell] = []
        self.comparison_mode: str | None = None

    def open_cell(self, context) -> Cell:
        cell = Cell(context)
        if self.comparison_mode is None:
            self.comparison_mode = cell.context.comparison_mode
        elif cell.context.comparison_mode != self.comparison_mode:
            raise fail_rule(
                RULE_MODE_CHANGED_MID_CAMPAIGN,
                "the campaign is running in %s and a cell was opened in %s: the mode "
                "is settled before collection and does not move during it"
                % (self.comparison_mode, cell.context.comparison_mode),
            )
        self.cells.append(cell)
        return cell

    def bundle(self) -> dict:
        boots = [cell.bundle() for cell in self.cells]
        return {
            "comparison_mode": self.comparison_mode,
            "boots": tuple(boots),
            "boots_collected": len(boots),
            "boots_required": BOOTS_PER_CAMPAIGN,
            "complete": len(boots) == BOOTS_PER_CAMPAIGN,
        }
