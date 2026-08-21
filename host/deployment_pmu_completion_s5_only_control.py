#!/usr/bin/env python3
"""Binding a board run to the image whose evidence licenses it.

comparison_mode is not in the frame and cannot be: it records whether the V15
primary loop is semantically equivalent to the frozen V14 Q reference, and the
target has no way to determine that. Amendment 2 settled where it lives instead
-- static image evidence -- and this module is the part that keeps a run and
that evidence attached to each other.

What it establishes is deployment provenance, not frame attestation. A frame
carries no image identity, so a raw frame replayed against another cell context
cannot be caught by looking at the frame. What can be caught, and is caught
here, is a run whose deployed artifacts are not the artifacts the qualification
evidence was computed over.

The attack that motivates it is real rather than illustrative. Amendment 1's
no-count scratch build is schema 15, variant S5, and fails equivalence at
RULE_EQUIVALENCE_LOOP_SHAPE. Its frames are indistinguishable from the shipped
build's, so before this module the only thing keeping its data out of an
equivalence-mode analysis was that nobody flashed it.

Three digests are not enough on their own. Recording the deployed APP beside an
equivalence evidence digest says both exist, not that the evidence was computed
over the image that ran. So the manifest binds the analysed ELF to the deployed
artifacts, and the gate refuses when they come apart.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field

# The other V15 modules import each other by bare name and expect host/ on the
# path. Bootstrapping it here rather than relying on the caller keeps one copy
# of each module loaded: reaching the same file by two import paths gives two
# module objects, and then a rule patched in one is not the rule the other runs.
_HOST = os.path.dirname(os.path.abspath(__file__))
if _HOST not in sys.path:
    sys.path.insert(0, _HOST)

import canonical_elf_pmu_completion_s5_only_control as canonical  # noqa: E402
import comparison_mode_pmu_completion_s5_only_control as chain  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402

RULE_MANIFEST_INCOMPLETE = "RULE_MANIFEST_INCOMPLETE"
RULE_MANIFEST_SELF_HASH = "RULE_MANIFEST_SELF_HASH"
RULE_MANIFEST_IDENTITY = "RULE_MANIFEST_IDENTITY"
RULE_EQUIVALENCE_EVIDENCE_UNUSABLE = "RULE_EQUIVALENCE_EVIDENCE_UNUSABLE"
RULE_MODE_CONTRADICTS_EVIDENCE = "RULE_MODE_CONTRADICTS_EVIDENCE"
RULE_REFERENCE_IDENTITY = "RULE_REFERENCE_IDENTITY"
RULE_EVIDENCE_ELF_UNBOUND = "RULE_EVIDENCE_ELF_UNBOUND"
RULE_ARTIFACT_NOT_DECLARED = "RULE_ARTIFACT_NOT_DECLARED"
RULE_READBACK_MISMATCH = "RULE_READBACK_MISMATCH"
RULE_CELL_CONTEXT_FORGED = "RULE_CELL_CONTEXT_FORGED"
RULE_EVIDENCE_INCOMPLETE = "RULE_EVIDENCE_INCOMPLETE"
RULE_EVIDENCE_DIGEST_MISMATCH = "RULE_EVIDENCE_DIGEST_MISMATCH"
RULE_MODE_DISAGREES_ACROSS_EVIDENCE = "RULE_MODE_DISAGREES_ACROSS_EVIDENCE"
RULE_V14_REFERENCE_MISMATCH = "RULE_V14_REFERENCE_MISMATCH"
RULE_RAW_ELF_USED_AS_IDENTITY = "RULE_RAW_ELF_USED_AS_IDENTITY"

RULES = (
    "RULE_MANIFEST_INCOMPLETE",
    "RULE_MANIFEST_SELF_HASH",
    "RULE_MANIFEST_IDENTITY",
    "RULE_EQUIVALENCE_EVIDENCE_UNUSABLE",
    "RULE_MODE_CONTRADICTS_EVIDENCE",
    "RULE_REFERENCE_IDENTITY",
    "RULE_EVIDENCE_ELF_UNBOUND",
    "RULE_ARTIFACT_NOT_DECLARED",
    "RULE_READBACK_MISMATCH",
    "RULE_CELL_CONTEXT_FORGED",
    "RULE_EVIDENCE_INCOMPLETE",
    "RULE_EVIDENCE_DIGEST_MISMATCH",
    "RULE_MODE_DISAGREES_ACROSS_EVIDENCE",
    "RULE_V14_REFERENCE_MISMATCH",
    "RULE_RAW_ELF_USED_AS_IDENTITY",
)

CANONICAL_JSON = "v15-canonical-json-v1"
MANIFEST_SELF_HASH_KEY = "manifest_self_hash"

# What the board actually consumes. Binding the APP alone would leave the other
# two free to differ from the qualified set.
DEPLOYED_ARTIFACTS = ("app", "vectors", "ddr")

MANIFEST_REQUIRED = (
    "canonical_json",
    "schema_version",
    "build_id",
    "variant",
    "comparison_mode",
    # raw_elf_sha256 is informational; analysis_elf_sha256 is load-bearing.
    "raw_elf_sha256",
    "analysis_elf_sha256",
    "app_sha256",
    "vectors_sha256",
    "ddr_sha256",
    "generated_source_sha256",
    "static_evidence_sha256",
    "equivalence_evidence_sha256",
    "equivalence_status",
    "v14_q_reference_identity",
    MANIFEST_SELF_HASH_KEY,
)


EQUIVALENCE_EVIDENCE_REQUIRED = (
    # The artifacts the checker actually read. Amendment 3: raw ELF digests are
    # path-sensitive and are provenance, not identity.
    "v15_analysis_elf_sha256",
    "v14_q_analysis_elf_sha256",
    "v14_q_app_sha256",
    "v14_q_reference_identity",
    "comparison_mode",
    "status",
    "detector_identity",
)

STATIC_EVIDENCE_REQUIRED = (
    "v15_analysis_elf_sha256",
    "equivalence_evidence_sha256",
    "comparison_mode",
    "boundary_image_verdict",
    "equivalence_verdict",
    "post_freeze_verdict",
    "poll_count_transport",
    "poll_count_admission",
)

# The frozen V14 Q reference, in two parts, because they are two different kinds
# of fact and conflating them is what the earlier UNPINNED state was protecting
# against.
#
# The deployed reference is what the board ran: recorded by the V14 campaign in
# v14-campaign-20260819/R1/cell_Q.json, source and destination read-back equal
# across nine boots.
V14_Q_DEPLOYED_REFERENCE = {
    "app_sha256": "f745eebd1f1ddcb7a2015f7dab21d2bf4ceb270cf43c7f932aa8419770e7b25d",
    "vectors_sha256": "6864a22bf98b0172ee7ace58aead9c6d85ebd3afec64ddae0771bbe2474d0d91",
    "ddr_sha256": "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
}
V14_Q_DEPLOYED_APP_SHA256 = V14_Q_DEPLOYED_REFERENCE["app_sha256"]

# The analysis reference is what the equivalence gate reads. Reconstructed
# 2026-08-21 from the frozen lineage in the original benchmark-runner container.
#
# Amendment 3 superseded the first version of this. It pinned the *raw* ELF
# digest, which is path-sensitive: three distinct raw digests have since been
# observed for this same image, so a legitimate rebuild from another directory
# would have been rejected despite identical code. The pin is now the analysis
# ELF, and that digest was measured identical across two build paths.
#
# Still not claimed: that the historical raw ELF was recovered. None was ever
# recorded, so there is nothing a reconstruction could have matched.
V14_Q_ANALYSIS_REFERENCE = {
    "analysis_elf_sha256": canonical.V14_Q_ANALYSIS_ELF_SHA256,
    # The build relation, proved rather than assumed: replaying objcopy against
    # the reconstructed ELF alone reproduces the deployed artifact set.
    "produced_app_sha256": V14_Q_DEPLOYED_APP_SHA256,
    # Informational provenance. Never an identity.
    "raw_elf_same_path_observation": canonical.V14_Q_RAW_ELF_SAME_PATH_OBSERVATION,
    "evidence": "docs/superpowers/evidence/v14-q-reconstruction-20260821",
}

RECONSTRUCTION_NOT_RUN = "NOT_RUN"
RECONSTRUCTION_ENVIRONMENT_UNAVAILABLE = "QUALIFIED_BUILD_ENVIRONMENT_UNAVAILABLE"
RECONSTRUCTION_APP_SET_MATCHED = "APP_ARTIFACT_SET_MATCHED"

V14_Q_RECONSTRUCTION_ATTEMPT_RESULT = RECONSTRUCTION_APP_SET_MATCHED

# Three claims, kept apart so none of them borrows another's strength.
V14_Q_RAW_ELF_SAME_PATH_AB = canonical.V14_Q_RAW_ELF_SAME_PATH_AB
V14_Q_ANALYSIS_ELF_STABILITY = canonical.V14_Q_ANALYSIS_ELF_STABILITY
V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET = canonical.V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET
HISTORICAL_RAW_ELF_IDENTITY = canonical.HISTORICAL_RAW_ELF_IDENTITY

Q_S5_EXECUTABLE_COMPARISON = "PASS"
# Two bridges, not one: the runtime identity bridge (reconstructed objcopy
# output == deployed artifacts) and the analysis identity bridge (canonical
# analysis ELF == the checkers' input).
Q_S5_RUNTIME_IDENTITY_BRIDGE = "RESOLVED_BY_RECONSTRUCTION"
Q_S5_ANALYSIS_IDENTITY_BRIDGE = "RESOLVED_BY_CANONICAL_ANALYSIS_ELF"


class DeploymentError(RuntimeError):
    """A run this module will not license."""


def fail_rule(rule: str, message: str) -> DeploymentError:
    return DeploymentError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def canonical_json_bytes(document: dict) -> bytes:
    """The one serialisation both sides hash."""

    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def manifest_self_hash(document: dict) -> str:
    preimage = {k: v for k, v in document.items() if k != MANIFEST_SELF_HASH_KEY}
    return hashlib.sha256(canonical_json_bytes(preimage)).hexdigest()


def seal_manifest(document: dict) -> dict:
    """A manifest with its own digest written in. Immutable from here on."""

    sealed = {k: v for k, v in document.items() if k != MANIFEST_SELF_HASH_KEY}
    sealed[MANIFEST_SELF_HASH_KEY] = manifest_self_hash(sealed)
    return sealed


_ISSUER = object()


@dataclass(frozen=True)
class VerifiedCellContext:
    """Issued by open_verified_cell and by nothing else.

    Constructing one by hand would make the whole chain a naming convention, so
    the constructor refuses a caller that did not come through the gate.
    """

    issued_by: object = field(repr=False, compare=False)

    app_sha256: str = ""
    vectors_sha256: str = ""
    ddr_sha256: str = ""

    raw_elf_sha256: str = ""
    analysis_elf_sha256: str = ""
    manifest_sha256: str = ""
    static_evidence_sha256: str = ""
    equivalence_evidence_sha256: str = ""

    comparison_mode: str = ""
    v14_q_reference_identity: str = ""
    candidate_identity: str = ""
    boot_id: str = ""

    def __post_init__(self):
        if self.issued_by is not _ISSUER:
            raise fail_rule(
                RULE_CELL_CONTEXT_FORGED,
                "a cell context was constructed directly. It is issued only after the "
                "manifest, the static evidence and the destination read-back have "
                "agreed, and a hand-built one asserts that agreement without it",
            )


def verify_manifest(document: dict) -> dict:
    """Recompute what the manifest asserts about itself."""

    missing = [key for key in MANIFEST_REQUIRED if key not in document]
    if missing:
        raise fail_rule(
            RULE_MANIFEST_INCOMPLETE,
            "the build manifest carries no %s" % ", ".join(sorted(missing)),
        )
    if document["canonical_json"] != CANONICAL_JSON:
        raise fail_rule(
            RULE_MANIFEST_SELF_HASH,
            "the manifest declares canonical form %r, this reader implements %r"
            % (document["canonical_json"], CANONICAL_JSON),
        )
    stored = document[MANIFEST_SELF_HASH_KEY]
    if not isinstance(stored, str) or len(stored) != 64:
        raise fail_rule(RULE_MANIFEST_SELF_HASH, "the manifest carries no usable self-hash")
    recomputed = manifest_self_hash(document)
    if recomputed != stored:
        raise fail_rule(
            RULE_MANIFEST_SELF_HASH,
            "manifest self-hash mismatch: stored %s, recomputed %s" % (stored, recomputed),
        )
    if document["schema_version"] != contract.SCHEMA_VERSION:
        raise fail_rule(
            RULE_MANIFEST_IDENTITY,
            "the manifest declares schema %r, not %d"
            % (document["schema_version"], contract.SCHEMA_VERSION),
        )
    if int(str(document["build_id"]), 16) != contract.BUILD_ID:
        raise fail_rule(
            RULE_MANIFEST_IDENTITY, "the manifest declares build %r" % (document["build_id"],)
        )
    if document["variant"] != "S5":
        raise fail_rule(
            RULE_MANIFEST_IDENTITY,
            "the manifest declares variant %r: schema 15 has one" % (document["variant"],),
        )
    return {"manifest_sha256": stored}


def document_digest(document: dict) -> str:
    """The digest of a completed document, taken from outside it."""

    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def candidate_identity(manifest: dict) -> str:
    """One name for this candidate, computed rather than chosen.

    A hand-written identity string is a label somebody picked; this is the
    artifact and evidence set itself, so two candidates differ here exactly when
    they differ in something that matters.
    """

    tuple_ = {
        "app_sha256": manifest["app_sha256"],
        "vectors_sha256": manifest["vectors_sha256"],
        "ddr_sha256": manifest["ddr_sha256"],
        "analysis_elf_sha256": manifest["analysis_elf_sha256"],
        "static_evidence_sha256": manifest["static_evidence_sha256"],
        "equivalence_evidence_sha256": manifest["equivalence_evidence_sha256"],
        "comparison_mode": manifest["comparison_mode"],
    }
    return hashlib.sha256(canonical_json_bytes(tuple_)).hexdigest()


def _require_keys(document, required, name):
    missing = [key for key in required if key not in document]
    if missing:
        raise fail_rule(
            RULE_EVIDENCE_INCOMPLETE,
            "the %s carries no %s" % (name, ", ".join(sorted(missing))),
        )


def _check_evidence_binding(manifest: dict, equivalence: dict, static: dict) -> str:
    """The binding graph, walked in the direction the evidence was produced.

    equivalence -> static evidence -> manifest, with the V15 ELF the same object
    at every step. Digests recorded side by side would say each document exists;
    what has to hold is that each one describes the next.
    """

    _require_keys(equivalence, EQUIVALENCE_EVIDENCE_REQUIRED, "equivalence evidence")
    _require_keys(static, STATIC_EVIDENCE_REQUIRED, "static evidence")

    # Each document is named by its digest in the one that cites it.
    if document_digest(equivalence) != static["equivalence_evidence_sha256"]:
        raise fail_rule(
            RULE_EVIDENCE_DIGEST_MISMATCH,
            "the static evidence cites equivalence evidence %s and the document "
            "offered digests to %s"
            % (static["equivalence_evidence_sha256"], document_digest(equivalence)),
        )
    if document_digest(equivalence) != manifest["equivalence_evidence_sha256"]:
        raise fail_rule(
            RULE_EVIDENCE_DIGEST_MISMATCH,
            "the manifest cites equivalence evidence %s and the document offered "
            "digests to %s"
            % (manifest["equivalence_evidence_sha256"], document_digest(equivalence)),
        )
    if document_digest(static) != manifest["static_evidence_sha256"]:
        raise fail_rule(
            RULE_EVIDENCE_DIGEST_MISMATCH,
            "the manifest cites static evidence %s and the document offered digests "
            "to %s" % (manifest["static_evidence_sha256"], document_digest(static)),
        )

    # The load-bearing equality: one analysis ELF, named identically at all three
    # steps. Raw digests are deliberately absent from this comparison -- they
    # move with the build directory, so requiring them equal would reject an
    # identical image rebuilt elsewhere.
    for name, offered in (
        ("equivalence evidence", equivalence["v15_analysis_elf_sha256"]),
        ("static evidence", static["v15_analysis_elf_sha256"]),
        ("manifest", manifest["analysis_elf_sha256"]),
    ):
        if canonical.is_raw_identity(offered):
            raise fail_rule(
                canonical.RULE_RAW_ELF_USED_AS_IDENTITY,
                canonical.RAW_AS_IDENTITY_MESSAGE % name,
            )
    elves = {
        "equivalence evidence": equivalence["v15_analysis_elf_sha256"],
        "static evidence": static["v15_analysis_elf_sha256"],
        "manifest": manifest["analysis_elf_sha256"],
    }
    if len(set(elves.values())) != 1:
        raise fail_rule(
            RULE_EVIDENCE_ELF_UNBOUND,
            "the V15 analysis ELF is not one object across the chain (%s): good evidence "
            "attached to a different image is the attack this closes"
            % ", ".join("%s=%s" % (k, v) for k, v in sorted(elves.items())),
        )

    # N7: the mode is a value carried by each document, and disagreement is a
    # refusal. No majority, no most-recent-wins -- a mode settled by
    # reconciliation is a mode nobody established.
    modes = {
        "equivalence evidence": equivalence["comparison_mode"],
        "static evidence": static["comparison_mode"],
        "manifest": manifest["comparison_mode"],
    }
    if len(set(modes.values())) != 1:
        raise fail_rule(
            RULE_MODE_DISAGREES_ACROSS_EVIDENCE,
            "the comparison mode differs across the evidence chain (%s) and is not "
            "reconciled by vote or recency"
            % ", ".join("%s=%s" % (k, v) for k, v in sorted(modes.items())),
        )

    mode = manifest["comparison_mode"]
    if mode not in contract.COMPARISON_MODES:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE, "the manifest declares comparison mode %r" % (mode,)
        )
    status = equivalence["status"]
    if status not in chain.MODE_FOR_EVIDENCE:
        raise fail_rule(
            RULE_EQUIVALENCE_EVIDENCE_UNUSABLE,
            "the equivalence evidence says %r, which licenses no mode" % (status,),
        )
    licensed = chain.MODE_FOR_EVIDENCE[status]
    if mode != licensed:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE,
            "the chain claims %s and the equivalence result is %s, which licenses %s"
            % (mode, status, licensed),
        )

    if status == chain.EQUIVALENCE_PASS:
        if equivalence["v14_q_reference_identity"] != chain.Q_REFERENCE_ANCHOR:
            raise fail_rule(
                RULE_REFERENCE_IDENTITY,
                "equivalence passed against reference %r and the qualified one is %r: "
                "a structurally similar Q is not the Q this mode means"
                % (equivalence["v14_q_reference_identity"], chain.Q_REFERENCE_ANCHOR),
            )
        if equivalence["v14_q_app_sha256"] != V14_Q_DEPLOYED_APP_SHA256:
            raise fail_rule(
                RULE_REFERENCE_IDENTITY,
                "equivalence compared against V14 Q APP %s and the image the V14 "
                "campaign actually ran is %s"
                % (equivalence["v14_q_app_sha256"], V14_Q_DEPLOYED_APP_SHA256),
            )
        # The V14 Q comparison reference, as an analysis ELF. Exact equality is
        # still required; Amendment 3 changed which object it is required of.
        if canonical.is_raw_identity(equivalence["v14_q_analysis_elf_sha256"]):
            raise fail_rule(
                canonical.RULE_RAW_ELF_USED_AS_IDENTITY,
                canonical.RAW_AS_IDENTITY_MESSAGE % "the equivalence evidence",
            )
        if equivalence["v14_q_analysis_elf_sha256"] != canonical.V14_Q_ANALYSIS_ELF_SHA256:
            raise fail_rule(
                RULE_V14_REFERENCE_MISMATCH,
                "equivalence read V14 Q analysis ELF %s and the pinned reference is %s"
                % (
                    equivalence["v14_q_analysis_elf_sha256"],
                    canonical.V14_Q_ANALYSIS_ELF_SHA256,
                ),
            )
    return mode


def _check_artifacts(document: dict, source: dict, readback: dict) -> None:
    """source == manifest == destination, for every artifact the board loads."""

    for name in DEPLOYED_ARTIFACTS:
        declared = document["%s_sha256" % name]
        if name not in source:
            raise fail_rule(
                RULE_ARTIFACT_NOT_DECLARED, "no source digest was offered for %s" % name
            )
        if source[name] != declared:
            raise fail_rule(
                RULE_ARTIFACT_NOT_DECLARED,
                "the %s about to be deployed is %s and the manifest qualifies %s: this "
                "image is not the one the evidence was computed over"
                % (name, source[name], declared),
            )
    for name in DEPLOYED_ARTIFACTS:
        declared = document["%s_sha256" % name]
        if name not in readback:
            raise fail_rule(
                RULE_READBACK_MISMATCH, "the destination was not read back for %s" % name
            )
        if readback[name] != declared:
            raise fail_rule(
                RULE_READBACK_MISMATCH,
                "%s reads back from the destination as %s, not the qualified %s: what "
                "landed is not what was verified" % (name, readback[name], declared),
            )


def verify_evidence_chain(manifest: dict, equivalence_evidence: dict,
                          static_evidence: dict) -> dict:
    """Everything that can be established before a board is involved.

    Pre-board qualification stops here on purpose. The remaining gate compares
    what was deployed against what landed, and there is no honest way to run it
    without deploying -- so it is absent rather than satisfied with placeholder
    digests.
    """

    document = verify_manifest(manifest)
    mode = _check_evidence_binding(manifest, equivalence_evidence, static_evidence)
    return {
        "manifest_sha256": document["manifest_sha256"],
        "comparison_mode": mode,
        "analysis_elf_sha256": manifest["analysis_elf_sha256"],
        "candidate_identity": candidate_identity(manifest),
        "deployment_verified": False,
        "remaining_before_a_cell": ("source artifact equality", "destination read-back"),
    }


def open_verified_cell(manifest: dict, equivalence_evidence: dict, static_evidence: dict,
                       source: dict, readback: dict, *, boot_id: str) -> VerifiedCellContext:
    """The only way a cell context comes into being.

    The order is the order of the procedure: the manifest against itself, the
    evidence chain against the ELF it describes, what is about to be written
    against what was qualified, and only then what actually landed.
    """

    verify_manifest(manifest)
    mode = _check_evidence_binding(manifest, equivalence_evidence, static_evidence)
    _check_artifacts(manifest, source, readback)
    if not boot_id:
        raise fail_rule(
            RULE_CELL_CONTEXT_FORGED,
            "a cell context needs the boot it belongs to: samples are compared within "
            "a boot before they are compared across boots",
        )
    return VerifiedCellContext(
        issued_by=_ISSUER,
        app_sha256=manifest["app_sha256"],
        vectors_sha256=manifest["vectors_sha256"],
        ddr_sha256=manifest["ddr_sha256"],
        raw_elf_sha256=manifest["raw_elf_sha256"],
        analysis_elf_sha256=manifest["analysis_elf_sha256"],
        # Taken over the finished manifest from outside it, rather than read out
        # of a field the manifest carries about itself.
        manifest_sha256=document_digest(manifest),
        static_evidence_sha256=manifest["static_evidence_sha256"],
        equivalence_evidence_sha256=manifest["equivalence_evidence_sha256"],
        comparison_mode=mode,
        v14_q_reference_identity=equivalence_evidence["v14_q_reference_identity"],
        candidate_identity=candidate_identity(manifest),
        boot_id=boot_id,
    )
