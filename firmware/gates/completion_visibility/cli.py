"""Successor completion-visibility checker: cli."""

from __future__ import annotations

import argparse
import json

from .constants import (
    VARIANTS,
    VARIANT_FAMILY,
)

from .errors import (
    GateError,
    fail,
)

from .c_lexical import (
    _normalize_newlines,
)

from .source_contracts import (
    verify_generated_sources,
)

from .image_contracts import (
    verify_common_tail_is_shared,
    verify_linked_image,
    verify_read_order_equivalence,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_pmu_completion_visibility_v14.py",
        description="Source and fixture contract gate for %s." % VARIANT_FAMILY,
    )
    parser.add_argument(
        "--allow-fixture",
        action="store_true",
        help="acknowledge that the inputs are generated/fixture sources, not board evidence",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANTS),
        help="variant under test: Q, QS or SQ",
    )
    parser.add_argument("--runner-generated", help="path to the generated runner translation unit")
    parser.add_argument("--vendor-generated", help="path to the generated vendor translation unit")
    parser.add_argument("--fixture-manifest-out", help="path the fixture manifest is written to")
    parser.add_argument(
        "--real-elf",
        action="store_true",
        help="prove the linked-image claims instead of the source contract",
    )
    parser.add_argument("--objdump-text", help="path to objdump -d of the linked image")
    parser.add_argument("--nm-text", help="path to nm -n of the linked image")
    parser.add_argument(
        "--dwarf-text", help="path to readelf --debug-dump of the linked image"
    )
    parser.add_argument("--elf-evidence-out", help="path the linked-image evidence is written to")
    parser.add_argument(
        "--read-order-equivalence",
        action="store_true",
        help="prove QS and SQ differ only in read order; needs both disassemblies",
    )
    parser.add_argument("--qs-objdump-text", help="path to objdump -d of the QS image")
    parser.add_argument("--sq-objdump-text", help="path to objdump -d of the SQ image")
    parser.add_argument(
        "--q-objdump-text",
        help="path to objdump -d of the Q image; adds the shared-tail proof",
    )
    return parser


def _read_text(path: str, what: str) -> str:
    """Read a source file, reporting a bad byte as a verdict rather than a crash.

    A translation unit that is not UTF-8 is not a translation unit this gate can
    read, and "cannot read it" is a rejection with a name. Letting the decoder's
    ``UnicodeDecodeError`` escape would print a traceback instead, which is not
    a verdict a gate is allowed to emit.
    """

    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _normalize_newlines(handle.read())
    except UnicodeDecodeError as exc:
        raise fail(
            "%s: is not UTF-8 text (byte 0x%02X at offset %d)" % (what, exc.object[exc.start], exc.start)
        )
    except OSError as exc:
        raise fail("%s: unreadable (%s)" % (what, exc))


def _write_manifest(path: str, doc: dict[str, object]) -> None:
    """Write the manifest, reporting a bad path as a named rejection.

    A bare relative filename is a legitimate output path and needs no directory
    handling at all; a path whose directory does not exist is an operator
    mistake. Either way the caller gets a ``FAIL`` line, because a traceback on
    stderr is not a verdict a gate is allowed to emit.
    """

    from ..identity import IdentityError, capture_identity

    try:
        doc = dict(doc, checker_identity=capture_identity())
    except IdentityError as exc:
        raise fail("successor identity cannot be recorded: %s" % exc) from exc
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError as exc:
        raise fail("fixture manifest is not writable at %r (%s)" % (path, exc))


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.read_order_equivalence:
        # A campaign-level claim: it needs two images, and no single-variant
        # build has both. The build graph proves what one image can show; this
        # is the step that compares the pair the campaign will run.
        missing = [
            name
            for name, value in (
                ("--qs-objdump-text", args.qs_objdump_text),
                ("--sq-objdump-text", args.sq_objdump_text),
                ("--elf-evidence-out", args.elf_evidence_out),
            )
            if value in (None, "")
        ]
        if missing:
            print("FAIL read-order equivalence requires %s" % ", ".join(missing))
            return 2
        try:
            qs_text = _read_text(args.qs_objdump_text, "QS disassembly")
            sq_text = _read_text(args.sq_objdump_text, "SQ disassembly")
            document = {"read_order": verify_read_order_equivalence(qs_text, sq_text)}
            if args.q_objdump_text:
                # The tail is a claim about all three, so it is made only when
                # all three are on the table rather than inferred from two.
                document["common_tail"] = verify_common_tail_is_shared(
                    {
                        "Q": _read_text(args.q_objdump_text, "Q disassembly"),
                        "QS": qs_text,
                        "SQ": sq_text,
                    }
                )
            else:
                document["common_tail"] = {
                    "shared_by_every_variant": False,
                    "scope": "not checked: --q-objdump-text was not given",
                }
            _write_manifest(args.elf_evidence_out, document)
        except GateError as exc:
            print("FAIL %s" % exc)
            return 1
        print("READ_ORDER EQUIVALENT %s" % VARIANT_FAMILY)
        return 0
    if args.real_elf:
        # The linked image needs no --allow-fixture: it *is* the evidence the
        # flag exists to distinguish fixtures from.
        missing = [
            name
            for name, value in (
                ("--variant", args.variant),
                ("--objdump-text", args.objdump_text),
                ("--nm-text", args.nm_text),
                ("--dwarf-text", args.dwarf_text),
                ("--elf-evidence-out", args.elf_evidence_out),
            )
            if value in (None, "")
        ]
        if missing:
            print("FAIL linked-image mode requires %s" % ", ".join(missing))
            return 2
        try:
            document = verify_linked_image(
                _read_text(args.objdump_text, "disassembly"),
                _read_text(args.nm_text, "symbol table"),
                args.variant,
                _read_text(args.dwarf_text, "debug info") if args.dwarf_text else None,
            )
            _write_manifest(args.elf_evidence_out, document)
        except GateError as exc:
            print("FAIL %s" % exc)
            return 1
        print("REAL_ELF PASS %s variant=%s" % (VARIANT_FAMILY, args.variant))
        return 0
    if not args.allow_fixture:
        print("FAIL fixture mode requires --allow-fixture; synthetic evidence is refused by default")
        return 2
    missing = [
        name
        for name, value in (
            ("--variant", args.variant),
            ("--runner-generated", args.runner_generated),
            ("--vendor-generated", args.vendor_generated),
            ("--fixture-manifest-out", args.fixture_manifest_out),
        )
        if value in (None, "")
    ]
    if missing:
        print("FAIL fixture mode requires %s" % ", ".join(missing))
        return 2

    try:
        runner_text = _read_text(args.runner_generated, "generated runner")
        vendor_text = _read_text(args.vendor_generated, "generated vendor")
        doc = verify_generated_sources(runner_text, vendor_text, args.variant)
        _write_manifest(args.fixture_manifest_out, doc)
    except GateError as exc:
        print("FAIL %s" % exc)
        return 1
    except RecursionError:
        # The structural walks bound their own depth, so this is the backstop
        # for a construct none of them owns. A traceback on stderr is not a
        # verdict a gate is allowed to emit, so it is one here instead.
        print("FAIL source nests deeper than this gate can analyse")
        return 1

    print("FIXTURE PASS %s variant=%s" % (VARIANT_FAMILY, args.variant))
    return 0
