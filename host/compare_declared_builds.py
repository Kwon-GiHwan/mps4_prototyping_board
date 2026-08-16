#!/usr/bin/env python3
"""Compare the declared artifacts of two independent builds.

Two clean builds of the same variant are the only evidence that the graph is
deterministic, and "the trees look the same" is not that evidence: a tree can
match while a manifest declares something it did not produce, and a tree can
differ for reasons -- an absolute root, a build timestamp -- that say nothing
about the compiler.

So the comparison is driven by what each side *declares*. For every variant the
manifest names a set of logical artifacts with their digests, and four
independent questions are asked of it:

* does each side declare the same set of artifacts (missing / extra),
* does each declared artifact exist on disk (missing),
* do the bytes on disk hash to what the manifest declared (declared),
* do the two sides agree on the digest (digest).

A manifest that carries an absolute path or a timestamp is rejected before any
of that (leakage), because such a manifest cannot be compared across roots at
all -- it encodes where it was built rather than what was built.

Exit status is zero only when the report's ``mismatches`` list is empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys


# Keys whose *name* says the value is a wall-clock reading, and values shaped
# like one. Either is a manifest that cannot be reproduced by a second build.
_TIME_KEY_RE = re.compile(r"time|timestamp|date|epoch|built_at|generated_at", re.I)
_TIME_VALUE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"          # ISO 8601
    r"|\b\d{10}\b"                                 # seconds since the epoch
    r"|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2} +\d"  # ctime
)
_ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\"' =:])(/[A-Za-z0-9._/-]{6,})")


# The manifest declares logical artifact *keys*, and those keys are resolved
# against the variant root to find bytes. A key is therefore only usable when it
# names something inside that root: nesting is ordinary -- the V14 manifest
# declares ``generated/Drivers/u85_driver/u85.c`` -- but an absolute path, a
# ``..`` component, an empty or ``.`` component, or a symlink pointing out of the
# tree all make "the same artifact" mean two different files on two machines.
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
SCHEMA_VERSION = 14
# The contract builds exactly these three. A variant outside the set is refused
# whether or not a tree happens to exist for it: a populated ``ZZ`` would
# otherwise compare clean and be reported as evidence about a variant this
# contract never defines.
CONTRACT_VARIANTS = ("Q", "QS", "SQ")


def manifest_name_fault(name: str):
    """Why ``--manifest-name`` is not a safe basename, or ``None``.

    It is joined onto every variant root, so it has to be a plain filename.
    Anything that can leave the directory -- a separator, a parent component, an
    absolute path -- would make the comparison read a file the build never
    declared.
    """

    if not isinstance(name, str) or not name or name != name.strip():
        return "--manifest-name must be a non-empty basename"
    if "/" in name or "\\" in name:
        return "--manifest-name must not contain a path separator"
    if name in (".", ".."):
        return "--manifest-name must not be %r" % name
    if pathlib.PurePosixPath(name).name != name:
        return "--manifest-name must be a bare filename"
    return None


def artifact_path_fault(root: pathlib.Path, variant: str, name: str):
    """Why ``name`` cannot be resolved inside the variant root, or ``None``."""

    if not isinstance(name, str) or not name:
        return "artifact key is not a non-empty string"
    if name != name.strip():
        return "artifact key carries surrounding whitespace"
    if name.startswith("/") or "\\" in name:
        return "artifact key is an absolute path"
    # The raw segments, not ``PurePosixPath.parts`` -- pathlib normalises ``.``
    # and collapses ``//`` away, so asking it would silently accept the very
    # spellings this is here to refuse.
    segments = name.split("/")
    for part in segments:
        if part in ("", ".", ".."):
            return "artifact key carries a %r component" % part
    pure = pathlib.PurePosixPath(name)

    base = (root / variant).resolve()
    candidate = (root / variant / name)
    # ``strict=False`` so an absent file is reported as missing by the caller
    # rather than as a path fault here; what matters is where it *would* land.
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return "artifact resolves outside the variant root"
    # A symlink anywhere on the way is a second name for bytes this comparison
    # cannot attribute, so it is refused even when it currently lands inside.
    probe = root / variant
    for part in pure.parts:
        probe = probe / part
        if probe.is_symlink():
            return "artifact path traverses the symlink %r" % part
    return None


def declaration_fault(entry):
    """Why a declared artifact entry is unusable, or ``None``."""

    if not isinstance(entry, dict):
        return "declaration is %s, not an object" % type(entry).__name__
    digest = entry.get("sha256")
    if digest is None:
        return "declaration carries no sha256"
    if not isinstance(digest, str) or _HEX64_RE.match(digest) is None:
        return "declaration carries a sha256 that is not 64 hex characters"
    if "bytes" not in entry:
        return "declaration carries no bytes"
    size = entry["bytes"]
    # ``bool`` is an ``int`` in Python, and ``True`` is not a byte count.
    if isinstance(size, bool) or not isinstance(size, int):
        return "declaration carries a bytes value that is not an integer"
    if size < 0:
        return "declaration carries a negative bytes value"
    return None


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _mismatch(kind: str, variant: str, artifact: str, detail: str) -> dict:
    return {"kind": kind, "variant": variant, "artifact": artifact, "detail": detail}


def _walk(node, path=()):
    """Every ``(key path, scalar)`` in a decoded JSON document."""

    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, path + (str(index),))
    else:
        yield path, node


def find_leakage(manifest: dict, variant: str, side: str) -> list:
    """Absolute paths and timestamps a second build could not reproduce."""

    found = []
    for path, value in _walk(manifest):
        where = "%s:%s" % (side, ".".join(path))
        if _TIME_KEY_RE.search(path[-1] if path else ""):
            found.append(_mismatch("leakage", variant, where, "timestamp-named key"))
            continue
        if not isinstance(value, str):
            continue
        if _TIME_VALUE_RE.search(value):
            found.append(_mismatch("leakage", variant, where, "timestamp value %r" % value[:40]))
        # A digest is hex and carries no separator; an absolute path is the
        # thing that differs between two roots by construction.
        match = _ABSOLUTE_PATH_RE.search(value)
        if match is not None:
            found.append(
                _mismatch("leakage", variant, where, "absolute path %r" % match.group(1)[:60])
            )
    return found


def load_manifest(root: pathlib.Path, variant: str, name: str, side: str) -> tuple:
    """``(manifest, mismatches)`` -- a bad manifest is a verdict, not a traceback."""

    path = root / variant / name
    if path.is_symlink():
        return None, [
            _mismatch(
                "manifest",
                variant,
                "%s:%s" % (side, name),
                "manifest is a symlink, so its bytes are not this build's",
            )
        ]
    if not path.is_file():
        return None, [_mismatch("manifest", variant, "%s:%s" % (side, name), "manifest is absent")]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return None, [
            _mismatch("manifest", variant, "%s:%s" % (side, name), "unreadable: %s" % exc)
        ]
    if not isinstance(document, dict) or not isinstance(
        document.get("declared_artifacts"), dict
    ):
        return None, [
            _mismatch(
                "manifest",
                variant,
                "%s:%s" % (side, name),
                "manifest declares no artifact table",
            )
        ]
    # An empty table agrees with any other empty table and proves nothing: two
    # builds that declared nothing would compare clean and be reported as
    # evidence of determinism.
    if not document["declared_artifacts"]:
        return None, [
            _mismatch(
                "manifest",
                variant,
                "%s:%s" % (side, name),
                "manifest declares an empty artifact table",
            )
        ]
    return document, []


def variant_directory_fault(root: pathlib.Path, variant: str):
    """Why a variant directory cannot be attributed to this build, or ``None``.

    The comparison asks whether two builds produced the same bytes, and that
    question only means something when each side's tree *is* that side's output.
    A symlinked variant directory -- or a symlinked build root -- can point both
    sides at one tree, which then compares clean while proving nothing, or point
    a side at a tree the build never wrote.
    """

    if root.is_symlink():
        return "build root is a symlink"
    directory = root / variant
    if directory.is_symlink():
        return "variant directory is a symlink"
    if not directory.is_dir():
        return "variant directory is absent"
    # Belt and braces: even without a symlink on the last component, the
    # resolved directory has to sit under the resolved root.
    try:
        directory.resolve().relative_to(root.resolve())
    except ValueError:
        return "variant directory resolves outside the build root"
    return None


def compare_variant(
    left: pathlib.Path, right: pathlib.Path, variant: str, manifest_name: str
) -> list:
    mismatches = []
    for side, root in (("left", left), ("right", right)):
        fault = variant_directory_fault(root, variant)
        if fault is not None:
            mismatches.append(_mismatch("variant", variant, side, fault))
    if mismatches:
        # Nothing below can be attributed to a build, so nothing below is read.
        return mismatches
    left_manifest, problems = load_manifest(left, variant, manifest_name, "left")
    mismatches.extend(problems)
    right_manifest, problems = load_manifest(right, variant, manifest_name, "right")
    mismatches.extend(problems)
    if left_manifest is None or right_manifest is None:
        return mismatches

    mismatches.extend(find_leakage(left_manifest, variant, "left"))
    mismatches.extend(find_leakage(right_manifest, variant, "right"))

    # A manifest has to say which variant and which schema it is, and say the
    # same thing the caller asked for -- otherwise a substituted manifest passes
    # by declaring artifacts that happen to match.
    for side, manifest in (("left", left_manifest), ("right", right_manifest)):
        if manifest.get("variant") != variant:
            mismatches.append(
                _mismatch(
                    "identity",
                    variant,
                    "%s:variant" % side,
                    "manifest declares variant %r, requested %r"
                    % (manifest.get("variant"), variant),
                )
            )
        if manifest.get("schema_version") != SCHEMA_VERSION:
            mismatches.append(
                _mismatch(
                    "identity",
                    variant,
                    "%s:schema_version" % side,
                    "manifest declares schema_version %r, expected %d"
                    % (manifest.get("schema_version"), SCHEMA_VERSION),
                )
            )

    # Reproducible metadata is part of what the two builds must agree on. Binding
    # only the artifact digests would let a substituted build identity through.
    for key in sorted(set(left_manifest) | set(right_manifest)):
        if key == "declared_artifacts":
            continue
        if left_manifest.get(key) != right_manifest.get(key):
            mismatches.append(
                _mismatch(
                    "metadata",
                    variant,
                    key,
                    "left %r != right %r"
                    % (str(left_manifest.get(key))[:40], str(right_manifest.get(key))[:40]),
                )
            )

    left_declared = left_manifest["declared_artifacts"]
    right_declared = right_manifest["declared_artifacts"]

    for side, root, declared in (
        ("left", left, left_declared),
        ("right", right, right_declared),
    ):
        for artifact in sorted(declared):
            fault = artifact_path_fault(root, variant, artifact)
            if fault is not None:
                mismatches.append(
                    _mismatch("artifact-path", variant, "%s:%s" % (side, artifact), fault)
                )
                continue
            fault = declaration_fault(declared[artifact])
            if fault is not None:
                mismatches.append(
                    _mismatch("declaration", variant, "%s:%s" % (side, artifact), fault)
                )
    if mismatches:
        # A manifest this comparison cannot trust is not compared further: the
        # digests below would be reading paths that were just refused.
        return mismatches

    for artifact in sorted(set(left_declared) - set(right_declared)):
        mismatches.append(_mismatch("missing", variant, artifact, "declared left, absent right"))
    for artifact in sorted(set(right_declared) - set(left_declared)):
        mismatches.append(_mismatch("extra", variant, artifact, "declared right, absent left"))

    for artifact in sorted(set(left_declared) & set(right_declared)):
        for side, root, declared in (
            ("left", left, left_declared),
            ("right", right, right_declared),
        ):
            path = root / variant / artifact
            if not path.is_file():
                mismatches.append(
                    _mismatch("missing", variant, artifact, "%s: declared but not on disk" % side)
                )
                continue
            actual = _sha256(path)
            claimed = declared[artifact].get("sha256")
            if actual != claimed:
                mismatches.append(
                    _mismatch(
                        "declared",
                        variant,
                        artifact,
                        "%s: bytes hash %s, manifest declares %s" % (side, actual[:16], str(claimed)[:16]),
                    )
                )
            # The size is declared alongside the digest, so it is bound too: a
            # drifted byte count is a manifest that does not describe the file
            # it points at, whether or not the hash happens to agree.
            on_disk = path.stat().st_size
            if declared[artifact]["bytes"] != on_disk:
                mismatches.append(
                    _mismatch(
                        "declared",
                        variant,
                        artifact,
                        "%s: file is %d bytes, manifest declares %s"
                        % (side, on_disk, declared[artifact]["bytes"]),
                    )
                )
        left_digest = left_declared[artifact].get("sha256")
        right_digest = right_declared[artifact].get("sha256")
        if left_digest != right_digest:
            mismatches.append(
                _mismatch(
                    "digest",
                    variant,
                    artifact,
                    "left %s != right %s" % (str(left_digest)[:16], str(right_digest)[:16]),
                )
            )
        if left_declared[artifact]["bytes"] != right_declared[artifact]["bytes"]:
            mismatches.append(
                _mismatch(
                    "size",
                    variant,
                    artifact,
                    "left declares %s bytes, right declares %s"
                    % (left_declared[artifact]["bytes"], right_declared[artifact]["bytes"]),
                )
            )
    return mismatches


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compare_declared_builds.py",
        description="Compare the declared artifacts of two independent builds.",
    )
    parser.add_argument("--left", required=True, help="root of the first build")
    parser.add_argument("--right", required=True, help="root of the second build")
    parser.add_argument(
        "--variants", required=True, help="comma-separated variants to compare, e.g. Q,QS,SQ"
    )
    parser.add_argument(
        "--manifest-name", required=True, help="manifest filename inside each variant directory"
    )
    parser.add_argument("--report", required=True, help="path the JSON report is written to")
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    left = pathlib.Path(args.left)
    right = pathlib.Path(args.right)

    # An empty or duplicated variant list is a caller error, not a clean run:
    # comparing nothing would otherwise report ``mismatches=[]`` and exit zero.
    requested = [item.strip() for item in args.variants.split(",")]
    if any(not item for item in requested):
        print("--variants carries an empty entry: %r" % args.variants, file=sys.stderr)
        return 2
    duplicated = sorted({item for item in requested if requested.count(item) > 1})
    if duplicated:
        print("--variants repeats %s" % ", ".join(duplicated), file=sys.stderr)
        return 2
    unknown = [item for item in requested if item not in CONTRACT_VARIANTS]
    if unknown:
        print(
            "--variants names %s, which is not one of %s"
            % (", ".join(unknown), ", ".join(CONTRACT_VARIANTS)),
            file=sys.stderr,
        )
        return 2
    variants = requested

    fault = manifest_name_fault(args.manifest_name)
    if fault is not None:
        print("%s: %r" % (fault, args.manifest_name), file=sys.stderr)
        return 2

    mismatches = []
    for variant in variants:
        # A variant directory that is absent on either side is a verdict rather
        # than a traceback, and it is not silently skipped.
        absent = [
            side
            for side, root in (("left", left), ("right", right))
            if not (root / variant).is_dir()
        ]
        if absent:
            mismatches.append(
                _mismatch(
                    "variant",
                    variant,
                    ",".join(absent),
                    "variant directory is absent on: %s" % ", ".join(absent),
                )
            )
            continue
        mismatches.extend(compare_variant(left, right, variant, args.manifest_name))

    report = {
        "variants": variants,
        "manifest_name": args.manifest_name,
        "mismatches": mismatches,
        "comparison": "declared-artifact byte identity",
    }
    report_path = pathlib.Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if mismatches:
        print("mismatches=%d" % len(mismatches), file=sys.stderr)
        for item in mismatches[:20]:
            print("  %(kind)s %(variant)s %(artifact)s: %(detail)s" % item, file=sys.stderr)
        return 1
    print("mismatches=[]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
