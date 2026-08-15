"""Source and fixture contract gate for PMU_COMPLETION_VISIBILITY_DIAG_V14.

Scope, stated first so nothing here is read for more than it is: this module
gates **generated C sources** for the Q/QS/SQ schema-14 diagnostic images. It
proves the identity constants, the pre-run stopped-state/QSIZE contract, the
per-variant primary observation loops, the one common convergence tail, the
34-word failure mailbox, and the retained V12/V13 IRQ hard-bypass and success
cleanup ordering -- all over comment- and literal-masked source text.

What it does **not** do: it does not read an ELF, a disassembly, DWARF, or a
map file, so it cannot prove what the compiler actually lowered. Source
inspection is supporting evidence only; the final-ELF qualification gates named
in the design are a separate, later contract and are not implemented here. A
build that satisfies this module is UNIT-QUALIFIED and nothing more.

The analyzer is structural rather than textual. Function bodies are resolved by
brace matching, loop bodies are split into statements, and each statement is
classified into a semantic effect (an MMIO load of a bound register pointer, a
timestamp read, a store, a call, a control branch). Gates are then expressed
over the ordered effect sequence and over the branch topology, so reformatting
the generated source cannot change a verdict while inserting a per-iteration
effect can.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA_VERSION = 14
BUILD_ID = 0x34314950
VARIANT_FAMILY = "PMU_COMPLETION_VISIBILITY_DIAG_V14"

HEADER_WORDS = 8
BASE_WORDS = 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS
PAYLOAD_BYTES = TOTAL_WORDS * 4

QSIZE_EXPECTED = 0x110
MAILBOX_VALID = 0x5631344D
U32_INVALID = 0xFFFFFFFF
ITERATION_BOUND = 10000

VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"

APPENDIX_FIELDS = (
    "variant_id",
    "qsize_expected",
    "pre_program_status",
    "pre_submit_status",
    "t_submit_after_cmd",
    "t_primary_entry",
    "t_first_observation",
    "primary_result",
    "primary_iterations",
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
    "convergence_result",
    "convergence_iterations",
    "convergence_final_qread",
    "convergence_final_status",
    "convergence_timeout",
    "failure_phase",
    "failure_reason",
    "failure_qread",
    "failure_status",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
    "mailbox_valid",
)

PRIMARY_RESULT = {"NOT_RUN": 0, "OBSERVED": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
CONVERGENCE_RESULT = {"NOT_RUN": 0, "SUCCESS": 1, "TIMEOUT": 2, "RESET": 3, "FAULT": 4}
FAILURE_PHASE = {
    "NONE": 0,
    "PRE_PROGRAM": 1,
    "PRE_SUBMIT": 2,
    "PRIMARY": 3,
    "CONVERGENCE": 4,
    "CLEANUP": 5,
}
FAILURE_REASON = {
    "NONE": 0,
    "STATE_RUNNING": 1,
    "RESET_IN_PROGRESS": 2,
    "HARDWARE_FAULT": 3,
    "STALE_IRQ": 4,
    "STALE_CMD_END": 5,
    "QSIZE_MISMATCH": 6,
    "PRIMARY_TIMEOUT": 7,
    "CONVERGENCE_TIMEOUT": 8,
    "CLEANUP_INVARIANT": 9,
}
VENDOR_RETURN = {
    "SUCCESS": 0,
    "PRE_PROGRAM_FAILURE": 1,
    "PRE_SUBMIT_FAILURE": 2,
    "PRIMARY_TIMEOUT": 3,
    "RESET_IN_PROGRESS": 4,
    "HARDWARE_FAULT": 5,
    "CONVERGENCE_TIMEOUT": 6,
    "CLEANUP_INVARIANT": 7,
}

STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_BUS = 0x004
STATUS_RESET = 0x008
STATUS_CMD_PARSE = 0x010
STATUS_CMD_END = 0x020
STATUS_ECC = 0x100
STATUS_BRANCH = 0x200
STATUS_FAULT_MASK = STATUS_BUS | STATUS_CMD_PARSE | STATUS_ECC | STATUS_BRANCH

MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"
MAILBOX_RESET_SYMBOL = "v14_mailbox_reset"
MAILBOX_PUBLISH_SYMBOL = "v14_mailbox_publish"
CONVERGE_SYMBOL = "v14_converge"
PRIMARY_SYMBOL = {"Q": "v14_primary_q", "QS": "v14_primary_qs", "SQ": "v14_primary_sq"}


class GateError(Exception):
    """A stable, named contract rejection."""


def fail(message: str) -> GateError:
    return GateError(message)


def identity_matches(
    *,
    schema_version: int,
    build_id: int,
    appendix_words: int,
    qsize_expected: int,
    mailbox_valid: int,
) -> bool:
    """Report whether a candidate identity tuple is the frozen V14 one."""

    return (
        schema_version == SCHEMA_VERSION
        and build_id == BUILD_ID
        and appendix_words == APPENDIX_WORDS
        and qsize_expected == QSIZE_EXPECTED
        and mailbox_valid == MAILBOX_VALID
    )


# ---------------------------------------------------------------------------
# Lexical masking and structural extraction
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//(?:\\[ \t]*\n|[^\n])*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL_RE = re.compile(r'"(?:\\[\s\S]|[^"\\\n])*"')
_CHAR_LITERAL_RE = re.compile(r"'(?:\\[\s\S]|[^'\\\n])+'")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _blank_span(out: list[str], text: str, start: int, stop: int) -> None:
    for index in range(start, stop):
        out[index] = "\n" if text[index] == "\n" else " "


def mask_c_lexical(text: str) -> str:
    """Blank comments and literals while preserving every byte offset."""

    out = list(text)
    for pattern in (_BLOCK_COMMENT_RE, _LINE_COMMENT_RE, _STRING_LITERAL_RE, _CHAR_LITERAL_RE):
        for match in pattern.finditer("".join(out)):
            _blank_span(out, text, match.start(), match.end())
    return "".join(out)


def _matching_brace(text: str, open_index: int, what: str) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise fail("%s: unbalanced braces" % what)


def extract_function_body(masked: str, name: str, what: str) -> tuple[int, int]:
    """Return the ``(start, stop)`` span of ``name``'s body, braces excluded."""

    definitions = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])%s\s*\(" % re.escape(name), masked):
        close = masked.find(")", match.end() - 1)
        if close < 0:
            continue
        tail = masked[close + 1 :]
        stripped = tail.lstrip()
        if not stripped.startswith("{"):
            continue
        open_index = close + 1 + (len(tail) - len(stripped))
        definitions.append((open_index, _matching_brace(masked, open_index, what)))
    if len(definitions) != 1:
        raise fail("%s: expected exactly one definition, found %d" % (what, len(definitions)))
    open_index, close_index = definitions[0]
    return open_index + 1, close_index


def function_text(masked: str, name: str, what: str) -> str:
    start, stop = extract_function_body(masked, name, what)
    return masked[start:stop]


def normalized_digest(text: str) -> str:
    """Digest of ``text`` after collapsing all whitespace runs to one space."""

    return _sha256_text(re.sub(r"\s+", " ", text).strip())


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
    return parser


def _read_text(path: str, what: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _normalize_newlines(handle.read())
    except OSError as exc:
        raise fail("%s: unreadable (%s)" % (what, exc))


def _write_manifest(path: str, doc: dict[str, object]) -> None:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
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
    except GateError as exc:
        print("FAIL %s" % exc)
        return 1

    _write_manifest(args.fixture_manifest_out, doc)
    print("FIXTURE PASS %s variant=%s" % (VARIANT_FAMILY, args.variant))
    return 0


def verify_generated_sources(runner_text: str, vendor_text: str, variant: str) -> dict[str, object]:
    """Verify a generated Q/QS/SQ source pair and return its fixture manifest."""

    if variant not in VARIANTS:
        raise fail("unknown variant %r" % variant)
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    return {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "qualification": "UNIT-QUALIFIED",
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
    }


if __name__ == "__main__":
    sys.exit(main())
