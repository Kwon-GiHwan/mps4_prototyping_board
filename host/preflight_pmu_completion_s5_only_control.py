#!/usr/bin/env python3
"""What can be established before a board exists, and nothing beyond it.

This gate exists to be run before deployment, and its main job is to be honest
about its own edge. Every check that needs a device is enumerated and reported
as PENDING_DEPLOYMENT -- never as PASS, never omitted so that a reader counts
the remaining PASSes and concludes the candidate is cleared.

Tri-state throughout: PASS, FAIL, PENDING_DEPLOYMENT. A PENDING is not a soft
pass and an overall verdict of PASS is impossible while any board-dependent
check is outstanding, which is enforced rather than described.

The evidence it reads was produced by running the real gates against the real
candidate. So the checks here are not re-derivations of those verdicts -- they
are the questions a reader of the evidence should ask of it: was this measured
on the artifact that is actually being shipped, against the reference that is
actually pinned, and is any of it stale.
"""

from __future__ import annotations

import os
import sys

_HOST = os.path.dirname(os.path.abspath(__file__))
if _HOST not in sys.path:
    sys.path.insert(0, _HOST)

import canonical_elf_pmu_completion_s5_only_control as canonical  # noqa: E402
import comparison_mode_pmu_completion_s5_only_control as chain  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deployment  # noqa: E402

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_PENDING = "PENDING_DEPLOYMENT"

RULE_GATE_VERDICT_NOT_PASS = "RULE_GATE_VERDICT_NOT_PASS"
RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF = "RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF"
RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF = "RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF"
RULE_EVIDENCE_BINDING_BROKEN = "RULE_EVIDENCE_BINDING_BROKEN"
RULE_MODE_NOT_ESTABLISHED = "RULE_MODE_NOT_ESTABLISHED"
RULE_CANDIDATE_IDENTITY_MISMATCH = "RULE_CANDIDATE_IDENTITY_MISMATCH"
RULE_POLL_COUNT_CONTRACT_BROKEN = "RULE_POLL_COUNT_CONTRACT_BROKEN"
RULE_STALE_EVIDENCE = "RULE_STALE_EVIDENCE"
RULE_RAW_ELF_IN_IDENTITY_POSITION = "RULE_RAW_ELF_IN_IDENTITY_POSITION"
RULE_DEPLOYMENT_TREATED_AS_VERIFIED = "RULE_DEPLOYMENT_TREATED_AS_VERIFIED"

RULES = (
    "RULE_GATE_VERDICT_NOT_PASS",
    "RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF",
    "RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF",
    "RULE_EVIDENCE_BINDING_BROKEN",
    "RULE_MODE_NOT_ESTABLISHED",
    "RULE_CANDIDATE_IDENTITY_MISMATCH",
    "RULE_POLL_COUNT_CONTRACT_BROKEN",
    "RULE_STALE_EVIDENCE",
    "RULE_RAW_ELF_IN_IDENTITY_POSITION",
    "RULE_DEPLOYMENT_TREATED_AS_VERIFIED",
)

# Named individually so a reader sees what is outstanding rather than inferring
# it from an absence. Each stays PENDING_DEPLOYMENT until a board is authorized.
BOARD_DEPENDENT_CHECKS = (
    "source_artifact_equality",
    "destination_readback_equality",
    "verified_cell_context_issued",
    "fresh_boot",
    "campaign_three_boots_ten_runs",
    "original_image_restored",
)

GATE_VERDICTS_REQUIRED = (
    "boundary_image_verdict",
    "equivalence_verdict",
    "post_freeze_verdict",
)


class PreflightError(RuntimeError):
    """A candidate this gate will not clear for deployment."""


def fail_rule(rule: str, message: str) -> PreflightError:
    return PreflightError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def _check_gates_passed(static: dict) -> None:
    for name in GATE_VERDICTS_REQUIRED:
        verdict = static.get(name)
        if verdict != "PASS":
            raise fail_rule(
                RULE_GATE_VERDICT_NOT_PASS,
                "the static evidence records %s = %r. Anything that is not PASS is not "
                "a pass, including a missing verdict" % (name, verdict),
            )


def _check_gates_ran_on_the_analysis_elf(equivalence: dict, manifest: dict) -> None:
    """The verdicts have to be about the artifact being shipped."""

    transform = equivalence.get("analysis_elf_transform")
    if transform != canonical.ANALYSIS_ELF_TRANSFORM:
        raise fail_rule(
            RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF,
            "the equivalence evidence does not record the pinned analysis transform, so "
            "nothing here says the gates read the canonical artifact rather than the raw "
            "one",
        )
    if equivalence["v15_analysis_elf_sha256"] != manifest["analysis_elf_sha256"]:
        raise fail_rule(
            RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF,
            "the gates were run on analysis ELF %s and the manifest ships %s"
            % (equivalence["v15_analysis_elf_sha256"], manifest["analysis_elf_sha256"]),
        )


def _check_reference(equivalence: dict) -> None:
    offered = equivalence["v14_q_analysis_elf_sha256"]
    if canonical.is_raw_identity(offered):
        raise fail_rule(
            RULE_RAW_ELF_IN_IDENTITY_POSITION,
            canonical.RAW_AS_IDENTITY_MESSAGE % "the equivalence evidence",
        )
    if offered != canonical.V14_Q_ANALYSIS_ELF_SHA256:
        raise fail_rule(
            RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF,
            "the comparison used V14 Q analysis ELF %s and the pinned reference is %s"
            % (offered, canonical.V14_Q_ANALYSIS_ELF_SHA256),
        )
    if equivalence["v14_q_app_sha256"] != deployment.V14_Q_DEPLOYED_APP_SHA256:
        raise fail_rule(
            RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF,
            "the reference APP is %s and the image the V14 campaign ran is %s"
            % (equivalence["v14_q_app_sha256"], deployment.V14_Q_DEPLOYED_APP_SHA256),
        )


def _check_not_stale(manifest: dict, artifacts: dict) -> None:
    """The evidence has to describe the artifacts that were actually built."""

    for name in ("app_sha256", "vectors_sha256", "ddr_sha256",
                 "raw_elf_sha256", "analysis_elf_sha256"):
        if name not in artifacts:
            raise fail_rule(
                RULE_STALE_EVIDENCE,
                "no measured %s was offered, so the manifest's value is unchecked" % name,
            )
        if manifest[name] != artifacts[name]:
            raise fail_rule(
                RULE_STALE_EVIDENCE,
                "the manifest declares %s = %s and the built artifact measures %s: this "
                "evidence describes a different build"
                % (name, manifest[name], artifacts[name]),
            )
    if manifest["analysis_elf_sha256"] == manifest["raw_elf_sha256"]:
        raise fail_rule(
            RULE_STALE_EVIDENCE,
            "the manifest gives the same digest for the raw and analysis ELF, which "
            "means one of them was not produced by the pinned transform",
        )
    if canonical.is_raw_identity(manifest["analysis_elf_sha256"]):
        raise fail_rule(
            RULE_RAW_ELF_IN_IDENTITY_POSITION,
            canonical.RAW_AS_IDENTITY_MESSAGE % "the manifest",
        )


def _check_poll_count(static: dict) -> None:
    transport = static.get("poll_count_transport")
    admission = static.get("poll_count_admission")
    if transport != contract.POLL_COUNT_PRESENT:
        raise fail_rule(
            RULE_POLL_COUNT_CONTRACT_BROKEN,
            "the poll count transport is %r and the reference-matched loop requires %r"
            % (transport, contract.POLL_COUNT_PRESENT),
        )
    if admission != contract.POLL_COUNT_NOT_ADMITTED:
        raise fail_rule(
            RULE_POLL_COUNT_CONTRACT_BROKEN,
            "the poll count admission is %r. Amendment 1 applied the frozen criterion "
            "and the count failed it; admitting it here would rewrite that after the "
            "fact" % (admission,),
        )


def preflight(manifest: dict, equivalence: dict, static: dict, artifacts: dict) -> dict:
    """The pre-board verdict, with the board-dependent checks left visible."""

    _check_not_stale(manifest, artifacts)
    _check_gates_passed(static)
    _check_gates_ran_on_the_analysis_elf(equivalence, manifest)
    _check_reference(equivalence)
    _check_poll_count(static)

    try:
        resolved = deployment.verify_evidence_chain(manifest, equivalence, static)
    except deployment.DeploymentError as exc:
        raise fail_rule(
            RULE_EVIDENCE_BINDING_BROKEN,
            "the evidence chain does not bind: %s" % exc,
        ) from exc

    if resolved["comparison_mode"] not in contract.COMPARISON_MODES:
        raise fail_rule(
            RULE_MODE_NOT_ESTABLISHED,
            "no comparison mode was established: %r" % (resolved["comparison_mode"],),
        )
    recomputed = deployment.candidate_identity(manifest)
    if resolved["candidate_identity"] != recomputed:
        raise fail_rule(
            RULE_CANDIDATE_IDENTITY_MISMATCH,
            "the candidate identity does not recompute from the manifest",
        )
    if resolved["deployment_verified"]:
        raise fail_rule(
            RULE_DEPLOYMENT_TREATED_AS_VERIFIED,
            "the evidence claims the deployment was verified. No board was involved, so "
            "that claim can only have come from placeholder digests",
        )

    checks = {
        "artifacts_match_the_built_candidate": STATUS_PASS,
        "gates_passed": STATUS_PASS,
        "gates_ran_on_the_analysis_elf": STATUS_PASS,
        "reference_is_the_pinned_v14_q_analysis_elf": STATUS_PASS,
        "evidence_binding": STATUS_PASS,
        "comparison_mode_established": STATUS_PASS,
        "candidate_identity_recomputes": STATUS_PASS,
        "poll_count_contract": STATUS_PASS,
    }
    for name in BOARD_DEPENDENT_CHECKS:
        checks[name] = STATUS_PENDING

    pending = sorted(k for k, v in checks.items() if v == STATUS_PENDING)
    # An overall PASS is unreachable while anything is outstanding. Enforced
    # here rather than left to whoever reads the table.
    overall = STATUS_PENDING if pending else STATUS_PASS

    return {
        "overall": overall,
        "checks": checks,
        "pending": tuple(pending),
        "comparison_mode": resolved["comparison_mode"],
        "candidate_identity": resolved["candidate_identity"],
        "manifest_sha256": resolved["manifest_sha256"],
        "analysis_elf_sha256": manifest["analysis_elf_sha256"],
        "v14_q_analysis_elf_sha256": canonical.V14_Q_ANALYSIS_ELF_SHA256,
        "board_authorization": "NOT_REQUESTED",
        "task_11": chain.END_TO_END_STATUS,
        "task_14b_final_positive_path": "BLOCKED_PENDING_DEPLOYMENT",
    }
