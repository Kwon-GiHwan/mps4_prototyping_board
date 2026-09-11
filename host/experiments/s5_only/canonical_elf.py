#!/usr/bin/env python3
"""The ELF the analysis actually reads, and the transform that produces it.

A raw ELF's SHA-256 is a fine digest of that file and a bad identity for the
code inside it. DWARF records absolute build paths, so the same sources, the
same toolchain and the same runtime image produce different raw ELF digests when
built from different directories. That was measured, not assumed: three raw
digests for one image, while APP/VECTORS/DDR stayed byte-identical throughout.

An identity that moves when a nuisance variable moves is not an identity. So the
comparison identity is the *analysis ELF* -- the raw ELF put through one pinned,
deterministic transform that drops exactly the debug sections carrying the path
and nothing else.

This is not a tolerance. Nothing here says "close enough". Exact equality is
still required; the change is which object exact equality is required of, and
that object is chosen so it depends on the code rather than on where the code
was compiled.

The condition that makes it honest: the analysis ELF is what the checkers
consume, not merely what gets hashed. Hashing one artifact and analysing another
would mean the thing given an identity and the thing examined are different
objects.
"""

from __future__ import annotations

import hashlib
import subprocess

RULE_TRANSFORM_UNPINNED = "RULE_TRANSFORM_UNPINNED"
RULE_ANALYSIS_ELF_MISMATCH = "RULE_ANALYSIS_ELF_MISMATCH"
RULE_RAW_ELF_USED_AS_IDENTITY = "RULE_RAW_ELF_USED_AS_IDENTITY"

RULES = (
    "RULE_TRANSFORM_UNPINNED",
    "RULE_ANALYSIS_ELF_MISMATCH",
    "RULE_RAW_ELF_USED_AS_IDENTITY",
)

# Frozen. "We strip debug info" is a description; this is a contract, because a
# description drifts and a contract fails.
ANALYSIS_ELF_TRANSFORM = {
    "kind": "GNU_OBJCOPY_STRIP_DEBUG",
    "tool": "arm-none-eabi-objcopy",
    "toolchain": "Arm GNU Toolchain 15.2.Rel1 (Build arm-15.86)",
    "compiler_version": "15.2.1 20251203",
    "operation": "--strip-debug",
    "input": "RAW_ELF",
    "output": "ANALYSIS_ELF",
}

# What the transform is required to preserve, and required to drop. Measured on
# both V14 Q and V15 S5: disassembly identical, all 363 symbols identical,
# allocatable sections identical, ten debug sections removed.
ANALYSIS_ELF_PRESERVES = (
    "disassembly of every section the checkers read",
    "the complete symbol table, so function resolution is unchanged",
    "every allocatable section",
)
ANALYSIS_ELF_DROPS = ("debug sections, which are what carry the build path",)

# The frozen V14 Q comparison reference, as an analysis ELF. Reconstructed
# 2026-08-21; see docs/superpowers/evidence/v14-q-reconstruction-20260821 and
# the amendment-3 evidence for the path-independence measurement.
V14_Q_ANALYSIS_ELF_SHA256 = (
    "24c31bf4e7e338b888097953873d6511af3c6fd82eac2777ca1d12bbb2d10b2e"
)

# Informational only. Path-sensitive: three distinct values have been observed
# for this same image. Never compare against it to establish identity.
V14_Q_RAW_ELF_SAME_PATH_OBSERVATION = (
    "20baff11490045289be46deebc43558812c7d5d498118e21376748585612391a"
)

# The claims, separated so that neither borrows the other's strength.
V14_Q_RAW_ELF_SAME_PATH_AB = "IDENTICAL"
V14_Q_ANALYSIS_ELF_STABILITY = "PATH_INDEPENDENT_ACROSS_TESTED_BUILD_PATHS"
V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET = "REPRODUCED_BYTE_EXACT"
# Never claimed, and named here so the absence is deliberate rather than an
# oversight: no historical raw ELF digest was ever recorded, so there is nothing
# a reconstruction could have matched.
HISTORICAL_RAW_ELF_IDENTITY = "NOT_CLAIMED"


class CanonicalElfError(RuntimeError):
    """An artifact this module will not treat as an analysis reference."""


def fail_rule(rule: str, message: str) -> CanonicalElfError:
    return CanonicalElfError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def transform_identity() -> str:
    """The transform's own identity, so a changed transform is a changed pin."""

    payload = "|".join(
        "%s=%s" % (key, ANALYSIS_ELF_TRANSFORM[key])
        for key in sorted(ANALYSIS_ELF_TRANSFORM)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def canonicalize(raw_elf: str, analysis_elf: str, objcopy: str | None = None) -> str:
    """RAW_ELF -> ANALYSIS_ELF by the pinned transform, returning its digest.

    The same call is what produces the artifact the checkers are given, so the
    digest and the analysed bytes cannot come apart.
    """

    tool = objcopy or ANALYSIS_ELF_TRANSFORM["tool"]
    if ANALYSIS_ELF_TRANSFORM["operation"] != "--strip-debug":
        raise fail_rule(
            RULE_TRANSFORM_UNPINNED,
            "the analysis transform is %r and this module implements --strip-debug"
            % (ANALYSIS_ELF_TRANSFORM["operation"],),
        )
    subprocess.run(
        [tool, ANALYSIS_ELF_TRANSFORM["operation"], raw_elf, analysis_elf], check=True
    )
    return digest(analysis_elf)


def require_analysis_identity(observed: str, expected: str, what: str) -> None:
    """Exact equality, of the analysis ELF rather than of the raw one."""

    if observed != expected:
        raise fail_rule(
            RULE_ANALYSIS_ELF_MISMATCH,
            "%s analysis ELF is %s and the pinned reference is %s: exact equality is "
            "still required, of the artifact the checkers actually read"
            % (what, observed, expected),
        )


def is_raw_identity(candidate: str) -> bool:
    """Whether a digest offered as an analysis identity is a known raw digest.

    A predicate rather than a raiser, so the module that owns the surrounding
    contract raises its own error type and the caller of a gate has one
    exception to catch. The rule id stays here, where the reason lives.
    """

    return candidate == V14_Q_RAW_ELF_SAME_PATH_OBSERVATION


RAW_AS_IDENTITY_MESSAGE = (
    "%s offers a raw ELF digest as an analysis identity. Raw digests are "
    "path-sensitive -- three distinct values have been observed for one image -- "
    "and are informational provenance only"
)
