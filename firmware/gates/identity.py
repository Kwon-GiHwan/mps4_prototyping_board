"""Byte identity for the unqualified modular gate successor.

A captured identity is a reproducibility record, never qualification evidence.
Verification requires a previously retained record supplied by the caller.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import RLock

VERSION = "completion-visibility-successor-v1"
QUALIFICATION_STATUS = "UNQUALIFIED_SUCCESSOR"
FIRMWARE = Path(__file__).resolve().parents[1]
FROZEN_DEPENDENCIES = {
    "check_pmu_qual.py": "46829a93cad770a1ebffb30fdb234cd28874514bd6932c278df5379b7d4552bd",
    "check_pmu_completion_poll_v12.py": "772144725e2529916a574d3460366b20581c9e1cc90b24d2957aa611c834557b",
    "check_pmu_completion_poll_count_v13.py": "fb4014205158d6b4743fcc1a4b7ab9742e6e82035013f21bdc68f6ea470807a8",
}
_LOAD_LOCK = RLock()


class IdentityError(RuntimeError):
    """Missing or changed code in a successor's dependency set."""


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise IdentityError("cannot read identity input %s: %s" % (path, exc)) from exc


def _frozen_identity(directory: Path) -> dict:
    seen = {}
    for name, expected in FROZEN_DEPENDENCIES.items():
        actual = _digest(directory / name)
        if actual != expected:
            raise IdentityError("frozen dependency changed: %s" % name)
        seen[name] = actual
    return seen


def implementation_paths() -> tuple[str, ...]:
    from . import completion_visibility

    paths = {
        "gates/__init__.py", "gates/identity.py", "gates/s5_boundary.py",
        "gates/completion_visibility/__init__.py",
        "gates/completion_visibility/__main__.py",
    }
    for module in completion_visibility.IMPLEMENTATION_MODULES:
        paths.add(Path(module.__file__).resolve().relative_to(FIRMWARE).as_posix())
    return tuple(sorted(paths))


def capture_identity(*, firmware_root: Path | None = None) -> dict:
    """Capture code bytes; this does not confer a qualified status."""
    root = firmware_root or FIRMWARE
    _frozen_identity(root / "Selftest_pmu_diag")
    paths = set(implementation_paths())
    paths.update("Selftest_pmu_diag/" + name for name in FROZEN_DEPENDENCIES)
    files = {name: _digest(root / name) for name in sorted(paths)}
    identity = {
        "schema_version": 1,
        "version": VERSION,
        "qualification_status": QUALIFICATION_STATUS,
        "files": files,
    }
    identity["sha256"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return identity


def verify_identity(expected: dict, *, firmware_root: Path | None = None) -> dict:
    """Reject any missing, extra, or altered identity field or code input."""
    actual = capture_identity(firmware_root=firmware_root)
    if expected != actual:
        raise IdentityError("successor identity differs from the supplied code snapshot")
    return actual


def load_frozen_helpers():
    """Load the verified frozen parsers without changing the import search path."""
    directory = FIRMWARE / "Selftest_pmu_diag"
    with _LOAD_LOCK:
        _frozen_identity(directory)
        loaded = []
        aliases = {}
        try:
            for filename in FROZEN_DEPENDENCIES:
                public = Path(filename).stem
                private = "_mps4_successor_frozen_" + public
                aliases[public] = sys.modules.get(public)
                module = sys.modules.get(private)
                if module is None:
                    spec = importlib.util.spec_from_file_location(private, directory / filename)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[private] = module
                    try:
                        spec.loader.exec_module(module)
                    except BaseException:
                        sys.modules.pop(private, None)
                        raise
                sys.modules[public] = module
                loaded.append(module)
        finally:
            for name, previous in aliases.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
        return loaded[1], loaded[2]
