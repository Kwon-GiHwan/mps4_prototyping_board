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
    "elf_sha256",
    "app_sha256",
    "vectors_sha256",
    "ddr_sha256",
    "generated_source_sha256",
    "static_evidence_sha256",
    "equivalence_evidence_sha256",
    "equivalence_status",
    # The ELF the equivalence gate actually read. Kept separate from elf_sha256
    # on purpose: equal is the thing being checked, not the thing being assumed.
    "equivalence_elf_sha256",
    "v14_q_reference_identity",
    MANIFEST_SELF_HASH_KEY,
)


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

    elf_sha256: str = ""
    manifest_sha256: str = ""
    static_evidence_sha256: str = ""
    equivalence_evidence_sha256: str = ""

    comparison_mode: str = ""
    v14_q_reference_identity: str = ""
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


def _check_equivalence_binding(document: dict) -> str:
    """The mode against the evidence, and the evidence against the ELF."""

    mode = document["comparison_mode"]
    if mode not in contract.COMPARISON_MODES:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE,
            "the manifest declares comparison mode %r" % (mode,),
        )
    status = document["equivalence_status"]
    if status not in chain.MODE_FOR_EVIDENCE:
        raise fail_rule(
            RULE_EQUIVALENCE_EVIDENCE_UNUSABLE,
            "the equivalence evidence says %r, which licenses no mode" % (status,),
        )
    licensed = chain.MODE_FOR_EVIDENCE[status]
    if mode != licensed:
        raise fail_rule(
            RULE_MODE_CONTRADICTS_EVIDENCE,
            "the manifest claims %s and its equivalence evidence is %s, which licenses %s"
            % (mode, status, licensed),
        )

    digest = document["equivalence_evidence_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise fail_rule(
            RULE_EQUIVALENCE_EVIDENCE_UNUSABLE,
            "the manifest carries no usable equivalence evidence digest: a mode resting "
            "on an unrecorded comparison rests on nothing",
        )

    # The comparison has to have been made over the image being deployed. Two
    # digests sitting side by side say both exist, not that they belong together.
    if document["equivalence_elf_sha256"] != document["elf_sha256"]:
        raise fail_rule(
            RULE_EVIDENCE_ELF_UNBOUND,
            "the equivalence gate analysed ELF %s and the manifest deploys ELF %s: the "
            "evidence describes an image that is not the one being run"
            % (document["equivalence_elf_sha256"], document["elf_sha256"]),
        )

    if status == chain.EQUIVALENCE_PASS:
        if document["v14_q_reference_identity"] != chain.Q_REFERENCE_ANCHOR:
            raise fail_rule(
                RULE_REFERENCE_IDENTITY,
                "equivalence passed against reference %r and the qualified one is %r: a "
                "structurally similar Q is not the Q this mode means"
                % (document["v14_q_reference_identity"], chain.Q_REFERENCE_ANCHOR),
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
                "landed is not what was verified"
                % (name, readback[name], declared),
            )


def open_verified_cell(manifest: dict, source: dict, readback: dict, *, boot_id: str) -> VerifiedCellContext:
    """The only way a cell context comes into being.

    Order matters and is the order of the procedure: the manifest is checked
    against itself, then the mode against its evidence and the evidence against
    the ELF, then what is about to be written against what was qualified, and
    only then what actually landed.
    """

    document = verify_manifest(manifest)
    mode = _check_equivalence_binding(manifest)
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
        elf_sha256=manifest["elf_sha256"],
        manifest_sha256=document["manifest_sha256"],
        static_evidence_sha256=manifest["static_evidence_sha256"],
        equivalence_evidence_sha256=manifest["equivalence_evidence_sha256"],
        comparison_mode=mode,
        v14_q_reference_identity=manifest["v14_q_reference_identity"],
        boot_id=boot_id,
    )
