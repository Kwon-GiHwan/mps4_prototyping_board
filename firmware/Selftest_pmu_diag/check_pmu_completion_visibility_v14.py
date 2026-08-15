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
brace matching, loop bodies are flattened into every reachable statement at
every nesting depth, and each statement is classified into a semantic effect (an
MMIO load of a bound register pointer, a timestamp read, a store, a call, a
control branch). Gates are then expressed over the ordered effect sequence and
over the branch topology, so reformatting the generated source cannot change a
verdict while inserting a per-iteration effect anywhere in the loop can. A guard
inside a loop is not assumed to run on the exiting iteration -- no condition
proves that -- so it earns its exemption only by carrying nothing beyond the
canonical result publication and its timestamp and by ending its iteration in a
structurally proven ``break`` or ``return``.

Two things carry that "structural, not textual" claim. Every construct this
module looks for is compiled into a *token* pattern rather than a literal
substring, so whitespace, a line break or a comment between a callee and its
parenthesis is invisible to the rule and a name can never match a longer name
that merely starts with it. And every MMIO access is resolved to the register it
designates rather than to the spelling that reaches it: the vendor accessor
call, a bound ``*const`` pointer, a pointer copied or cast from one, a chain of
such copies, the address of an index into one, a bare base-plus-offset address
and an absolute constant behind a pointer cast all resolve alike. An address
this gate cannot pin to a single register is refused rather than ignored,
because a pointer whose target nothing can name is a pointer no ordering rule
covers. Register offsets come from the translation unit's own ``NPU_REG_*``
table; this module pins none of its own, and says so in every manifest -- so a
source that carries no such table has its absolute addresses refused, never
resolved from an offset map this file invented. Mailbox and observation stores
are resolved the same way: by the storage the lvalue designates, so the
subscript, the reversed subscript C also accepts, a dereference of pointer
arithmetic and a transitive alias all reach the same appendix word.

Three things follow from reading the source the way the compiler does. C line
splicing runs before comment recognition, so it runs first here too: a slash, a
backslash, a newline and a star open a block comment, and the text it encloses
is deleted here exactly as the built image loses it -- a masker that does not
splice keeps crediting code the compiler removed. A
preprocessor directive is not a statement and carries no terminator, so its line
is blanked before statements are split, or the directive folds into the next
statement's lvalue and hides the store from every lvalue rule. And a macro is
never expanded: a function-like macro whose body dereferences a pointer cast is
an MMIO access this gate cannot pin, so it is refused in every contract-critical
function rather than counted as an ordinary call.

Storage that is published is written once. A read-modify-write on an appendix
word or an observation field -- ``+=``, ``|=``, ``++``, through an alias, a
reversed subscript or pointer arithmetic -- rewrites a value after the store
this gate proved, so the image publishes one number and the manifest reports
another. Every such operator is resolved to the storage it names and refused.
The runner's half of the same contract is a mapping, not a count: each of the 34
copies is bound to the appendix word its field is published in, so 34 copies
that all read word 0, read the appendix backwards, or read outside it are
refused rather than counted as 34.

Two things a predicate does are proven separately: which observations it names,
and how it joins them. A conjunction and a disjunction of the same four terms
decide opposite things, and a gate that only greps for the terms proves nothing
about the branch -- so the connective is parsed, and each term is bound to the
exact value its comparison lands on. Every loop guard that publishes is held to
that standard, not just the first one of each name: an extra exit on ``i > 5U``,
one spelled ``else if``, or a reset guard widened with ``|| (i > 5U)`` all
publish a first-observation tuple about a measurement the source never made.
The same holds for a value a gate is credited for: a guarded name has to hold
the result of the very MMIO load this module counted, and its storage must not
be reachable through a second lvalue -- a parenthesised dereference or an
address taken anywhere -- or the gate is a comparison against a constant.

Nothing the manifest publishes about what was *observed* -- the running-QSIZE
count, whether a failure path clears CMD or enters the seam, the reachable NVIC
enable count, the cleanup ordering, the predicate connectives, the
first-observation categories, whether the runner's appendix copy is dominated by
the mailbox magic -- is a constant in this file. Each is the verifier's own
count, set or parse, so a source that would make one of them true is a source
that never reaches the manifest at all.

Two limitations are load-bearing and are published in every manifest rather
than left to be discovered. The frozen raw vendor translation unit is not
tracked in this repository, so the vendor half of this contract runs against a
stock fixture and is **not** proven against the frozen ``u85.c``. And the
cleanup H-PRINTF seam is proven here only as the frozen ``V12_HPRINTF_SEAM``
source anchor; the ``__wrap_printf`` callsite it maps to is an ELF contract that
belongs to the later qualification chunk.
"""

from __future__ import annotations

import argparse
import collections
import functools
import hashlib
import json
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

# The frozen V12/V13 qualified H-PRINTF seam. ``V12_HPRINTF_SEAM`` is the marker
# name ``check_pmu_completion_poll_v12.MANIFEST_MARKER_KEYS`` maps to
# ``hprintf_callsite_address``, which that gate proves is the address of the one
# ``__wrap_printf`` call between CMD=0 and the terminal CMD=0xC. Anchoring the
# generated source on that marker is what makes the seam the qualified callsite
# rather than whichever vendor printf happens to sit in the release window.
HPRINTF_SEAM_MARKER_NAME = "V12_HPRINTF_SEAM"
HPRINTF_SEAM_MARKER = "/* %s */" % HPRINTF_SEAM_MARKER_NAME
HPRINTF_WRAP_SYMBOL = "__wrap_printf"

# Stated in every manifest so no reader has to infer what this chunk did not do.
RESIDUAL_LIMITATIONS = (
    "vendor_raw_source_absent: the frozen u85.c is not tracked here, so the vendor "
    "half runs against a stock fixture and is not proven against the frozen "
    "translation unit",
    "hprintf_callsite_not_elf_bound: the cleanup seam is proven as the frozen "
    "V12_HPRINTF_SEAM source anchor only; binding it to the qualified "
    "__wrap_printf callsite address is an ELF contract",
    "no_elf_disassembly_or_dwarf_evidence: every verdict here is source-structural",
    "test_cpm_branch_not_preprocessed: the H-PRINTF seam and the terminal CMD=0xC are proven "
    "inside the #if(TEST_CPM==1) branch of a source that defines TEST_CPM to 1; this gate does "
    "not preprocess or compile, so whether the built image kept that branch is a "
    "build-configuration fact belonging to the later qualification chunk. The exposure is "
    "general rather than specific to that tail: this gate credits a construct where it is "
    "written, so any contract-critical construct in this file can be proven here and then "
    "removed by conditional compilation -- #if 0, an -D on the command line, or an include "
    "path that resolves differently -- and only a build that compiles can close that",
    "register_offsets_read_from_the_source_only: an NPU address written as a bare "
    "base-plus-offset or as an absolute constant resolves through the translation unit's own "
    "NPU_REG_* table; this gate pins no offset of its own, so a source that omits that table "
    "has every such address refused as unresolved rather than resolved from an assumed "
    "register map",
    "macros_are_not_expanded: this gate reads translation-unit text, so an object-like macro "
    "is resolved only through the source's own #define table and a function-like macro is never "
    "expanded at all; a function-like macro whose body dereferences a pointer cast is refused as "
    "unresolved MMIO in every contract-critical function rather than read through, and C line "
    "splicing is applied before comment recognition so a spliced comment opener deletes the same "
    "text the compiler deletes. Because a macro is read as one value for the whole translation "
    "unit, a source that undefines or redefines a V14_/NPU_REG_ macro is refused rather than "
    "modelled at whichever value happened to be last. None of this makes the gate equivalent to "
    "a C preprocessor: the general question of what the preprocessor produces belongs to a "
    "build that compiles",
    "mmio_and_mailbox_analysis_is_intraprocedural: every ordering, counting and provenance "
    "rule is proven inside the function that carries it, so a register read or a mailbox "
    "store moved into a helper called from a path that permits calls is outside what these "
    "verdicts cover; the measured loops permit no call at all, and each gated value is bound "
    "to a load in its own function, but the general scope is a later contract",
)

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

# C translation phase 2: a backslash immediately before a newline deletes both,
# and it does so *before* a comment or a literal is recognised. Trailing blanks
# between the two are undefined behaviour rather than a splice, but every
# toolchain this contract targets splices them, so they are spliced here too --
# the fail-closed reading.
_LINE_SPLICE_RE = re.compile(r"\\[ \t]*\n")
_NAME_CHARACTER_RE = re.compile(r"[A-Za-z0-9_]")

# The gate reads an operator-supplied source. Every other resource bound in this
# file is explicit, so the input length is one too: a source larger than this is
# refused by name rather than turned into a lexical scan nothing bounds.
_MAX_SOURCE_BYTES = 4 << 20

# Brace nesting deeper than this is refused rather than walked, because the
# structural walks below recurse once per level and a Python ``RecursionError``
# is a traceback, not a verdict a gate is allowed to emit.
_MAX_NESTING_DEPTH = 128


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _blank_span(out: list[str], text: str, start: int, stop: int) -> None:
    for index in range(start, stop):
        out[index] = "\n" if text[index] == "\n" else " "


def _mask_one_pass(text: str) -> str:
    """The single left-to-right comment/literal sweep, over already-spliced text."""

    out = list(text)
    index = 0
    length = len(text)
    # An unterminated ``/*`` proves there is no ``*/`` at or after it, so every
    # later opener is unterminated too. Remembering that is what keeps the sweep
    # linear: without it each of n openers rescans the whole tail, and a source
    # made of nothing but openers turns a verdict into minutes of scanning.
    unterminated_block_from: int | None = None
    while index < length:
        character = text[index]
        if character == "/" and index + 1 < length and text[index + 1] in "/*":
            if text[index + 1] == "/":
                pattern = _LINE_COMMENT_RE
            else:
                if unterminated_block_from is not None and index >= unterminated_block_from:
                    index += 1
                    continue
                pattern = _BLOCK_COMMENT_RE
        elif character == '"':
            pattern = _STRING_LITERAL_RE
        elif character == "'":
            pattern = _CHAR_LITERAL_RE
        else:
            index += 1
            continue
        match = pattern.match(text, index)
        if match is None:
            if pattern is _BLOCK_COMMENT_RE:
                unterminated_block_from = index
            index += 1
            continue
        _blank_span(out, text, index, match.end())
        index = match.end()
    return "".join(out)


def _splice_lines(text: str) -> tuple[str, list[int]]:
    """The phase-2 spliced text, with the origin offset of each surviving byte."""

    parts: list[str] = []
    origins: list[int] = []
    index = 0
    for match in _LINE_SPLICE_RE.finditer(text):
        parts.append(text[index : match.start()])
        origins.extend(range(index, match.start()))
        index = match.end()
    parts.append(text[index:])
    origins.extend(range(index, len(text)))
    return "".join(parts), origins


def require_no_token_splice(text: str) -> None:
    """Refuse a splice that joins two token characters.

    Splicing is undone here by deleting bytes and mapping the mask back onto the
    original offsets, which every offset-comparing rule in this file depends on.
    That mapping is faithful for a splice between tokens and cannot be for one
    *inside* a token: ``write_re\\<newline>g`` is one identifier to the compiler
    and two to any scan that keeps the original offsets. Rather than analyse a
    source under a tokenisation the built image does not share, it is refused.
    """

    for match in _LINE_SPLICE_RE.finditer(text):
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        if _NAME_CHARACTER_RE.match(before) and _NAME_CHARACTER_RE.match(after):
            raise fail(
                "source splices a line inside a token at offset %d: the built image and this "
                "gate would not tokenize it alike" % match.start()
            )


def mask_c_lexical(text: str) -> str:
    """Blank comments and literals while preserving every byte offset.

    Line splicing runs first, because C does: translation phase 2 deletes every
    ``\\<newline>`` before phase 3 recognises a comment, so ``/`` ``\\`` newline
    ``*`` opens a block comment in the built image. A masker that does not
    splice never sees that opener and keeps crediting the enclosed text as
    code -- code the compiler deleted. The sweep therefore runs over the spliced
    text and its result is mapped back onto the original offsets, so every
    offset-comparing rule downstream still holds while the *lexical* answer is
    the one the compiler gives.

    The sweep itself is the single left-to-right pass the frozen V13 gate
    already uses, because the construct that opens first is the construct that
    wins. Masking each kind with its own sweep does not hold that rule: a ``/*``
    written *inside* a string literal opens a block comment for the sweep that
    runs first, and everything up to the next ``*/`` -- real executable code
    included -- is blanked before the string sweep ever gets to see that the
    ``/*`` was only text. One pass cannot be talked into that, because reaching
    the ``/`` means the enclosing string was already recognised and skipped.

    Each construct is recognised by a pattern that must close: an unterminated
    block comment or literal simply does not match, and its opening character
    is then left as ordinary code. That is the fail-closed direction -- the
    scan may look at something that is really comment text, but it can never be
    talked out of looking at real code by an unbalanced quote.
    """

    if len(text) > _MAX_SOURCE_BYTES:
        raise fail(
            "source is larger than the %d-byte bound this gate scans: %d bytes"
            % (_MAX_SOURCE_BYTES, len(text))
        )
    spliced, origins = _splice_lines(text)
    if len(spliced) == len(text):
        return _mask_one_pass(text)
    require_no_token_splice(text)
    masked = _mask_one_pass(spliced)
    out = ["\n" if character == "\n" else " " for character in text]
    for position, origin in enumerate(origins):
        out[origin] = masked[position]
    # The splice itself is put back as the one byte that shows where a logical
    # line continues. Blanking it entirely would leave a continued preprocessor
    # directive looking like a directive line followed by an ordinary one, and
    # ``blank_directives`` would then blank half of a macro -- taking its open
    # parentheses with it and unbalancing every depth-tracking scan below.
    for match in _LINE_SPLICE_RE.finditer(text):
        out[match.start()] = "\\"
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


_DEFINE_RE = re.compile(r"(?m)^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]+(\S+)[ \t]*$")


def parse_define_values(masked: str) -> dict[str, list[int]]:
    """Return every integer value each object-like macro is given, in order.

    A macro this contract owns -- anything in the ``V14_`` namespace -- has to
    parse. Dropping a malformed one and reporting the macro as *undefined*
    names the wrong defect, and a reader chasing "is not defined" against a
    source that plainly defines it learns nothing. Macros outside the namespace
    are the vendor's and are skipped when they are not integers.
    """

    values: dict[str, list[int]] = {}
    for match in _DEFINE_RE.finditer(masked):
        name = match.group(1)
        raw = match.group(2).rstrip("uU")
        try:
            parsed = int(raw, 0)
        except ValueError:
            if name.startswith("V14_"):
                raise fail(
                    "malformed numeric define: %s is %r, which is not an integer literal"
                    % (name, match.group(2))
                )
            continue
        values.setdefault(name, []).append(parsed)
    return values


def parse_defines(masked: str) -> dict[str, int]:
    """Return the integer-valued object-like macros of a translation unit."""

    return {name: seen[-1] for name, seen in parse_define_values(masked).items()}


_UNDEF_RE = re.compile(r"(?m)^[ \t]*#[ \t]*undef[ \t]+([A-Za-z_][A-Za-z0-9_]*)")
# The names whose value this gate reads and then reasons about. A macro outside
# these families belongs to the vendor and may be redefined freely.
_CONTRACT_DEFINE_PREFIXES = ("V14_", "NPU_REG_")


def _is_contract_define(name: str) -> bool:
    return name.startswith(_CONTRACT_DEFINE_PREFIXES) or name in NPU_BASE_SYMBOLS


def require_stable_contract_defines(masked: str, what: str) -> None:
    """Refuse a source whose contract macros do not hold one value throughout.

    Every rule in this file reads a macro's value once and then reasons about
    the store, offset or address that used it. That is only sound while the
    macro has one value for the whole translation unit. ``#undef`` breaks it
    exactly, and warning-free: writing

        #undef V14_MBOX_VARIANT_ID
        #define V14_MBOX_VARIANT_ID 7U
        pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;
        #undef V14_MBOX_VARIANT_ID
        #define V14_MBOX_VARIANT_ID 0U

    is conforming C11 (6.10.3.5), leaves the frozen spelling untouched, and
    builds an image that publishes the variant id into appendix word 7 while
    this gate reports word 0 -- the mis-attributed frame ``verify_variant_identity``
    exists to prevent. This gate does not expand macros, so it cannot model a
    value that changes between use sites; the fail-closed answer is to refuse
    the source rather than to model it wrongly.
    """

    for match in _UNDEF_RE.finditer(masked):
        if _is_contract_define(match.group(1)):
            raise fail(
                "%s undefines a contract macro at offset %d: %s -- its value at a use site is "
                "not the value this gate reads" % (what, match.start(), match.group(1))
            )
    for name, seen in parse_define_values(masked).items():
        if _is_contract_define(name) and len(set(seen)) > 1:
            raise fail(
                "%s defines the contract macro %s with more than one value: %s -- its value at "
                "a use site is not the value this gate reads"
                % (what, name, ", ".join("0x%X" % value for value in sorted(set(seen))))
            )


def require_define(defines: dict[str, int], name: str, expected: int, what: str) -> None:
    if name not in defines:
        raise fail("%s: %s is not defined" % (what, name))
    if defines[name] != expected:
        raise fail("%s: %s is 0x%X, expected 0x%X" % (what, name, defines[name], expected))


# ---------------------------------------------------------------------------
# Token-aware code matching
#
# A C construct is a token sequence, not a byte sequence. Recognising
# ``read_reg(NPU_REG_STATUS)`` by literal substring means a source that writes
# ``read_reg (NPU_REG_STATUS)``, or splits the call over two lines, or puts a
# comment between the callee and its parenthesis, is a source the rule never
# sees -- and reformatting a generated file would then change a verdict. Every
# construct below is therefore compiled into a pattern that matches the same
# tokens separated by any run of whitespace, with identifier boundaries so a
# name can never match a longer name that merely starts with it.
# ---------------------------------------------------------------------------

_C_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|(?:0[xX][0-9A-Fa-f]+|\d+)[uUlL]*|->|\S")


def _token_atom(token: str, open_end: bool) -> str:
    """One token, boundary-anchored on whichever side carries a name character."""

    head = r"(?<![A-Za-z0-9_])" if (token[0].isalnum() or token[0] == "_") else ""
    if open_end or not (token[-1].isalnum() or token[-1] == "_"):
        tail = ""
    else:
        tail = r"(?![A-Za-z0-9_])"
    return head + re.escape(token) + tail


@functools.lru_cache(maxsize=None)
def code_pattern(snippet: str, open_end: bool = False) -> re.Pattern[str]:
    """Compile ``snippet`` into a whitespace-insensitive token matcher.

    ``open_end`` leaves the final token unanchored on its right, which is what
    a register *family* prefix such as ``write_reg(NPU_REG_QBASE`` needs: the
    frozen vendor source spells that register ``NPU_REG_QBASE_LSB``, so the
    prefix has to keep matching the longer name.
    """

    tokens = _C_TOKEN_RE.findall(snippet)
    if not tokens:
        raise fail("empty code pattern %r" % snippet)
    last = len(tokens) - 1
    parts = [_token_atom(tokens[0], open_end and last == 0)]
    for index in range(1, len(tokens)):
        parts.append(r"\s*")
        parts.append(_token_atom(tokens[index], open_end and index == last))
    return re.compile("".join(parts))


def code_positions(text: str, snippet: str, open_end: bool = False) -> tuple[int, ...]:
    """Every offset in ``text`` where ``snippet``'s token sequence starts."""

    return tuple(match.start() for match in code_pattern(snippet, open_end).finditer(text))


def code_find(text: str, snippet: str, open_end: bool = False) -> int:
    """The first offset of ``snippet``'s token sequence, or ``-1``."""

    match = code_pattern(snippet, open_end).search(text)
    return -1 if match is None else match.start()


def code_contains(text: str, snippet: str, open_end: bool = False) -> bool:
    return code_pattern(snippet, open_end).search(text) is not None


def names_identifier(text: str, name: str) -> bool:
    """Whether ``name`` occurs in ``text`` as a whole identifier."""

    return re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name), text) is not None


def function_span(masked: str, name: str, what: str) -> tuple[int, int]:
    return extract_function_body(masked, name, what)


# The queue-programming writes are matched as register *families*: the frozen
# vendor source spells the queue base ``NPU_REG_QBASE_LSB``/``_MSB``, so the
# prefix has to keep matching the longer name. Every other register access goes
# through ``register_access_sites``, which sees the accessor call and every
# pointer spelling alike.
_QBASE_WRITE = "write_reg(NPU_REG_QBASE"
_QSIZE_WRITE = "write_reg(NPU_REG_QSIZE"

# ---------------------------------------------------------------------------
# MMIO address provenance
#
# A register access is an access whatever name it is reached through. The
# frozen source spells one as ``read_reg(NPU_REG_STATUS)`` and another as a
# ``*const`` pointer built from ``U85_BASE_ADDRESS + NPU_REG_STATUS``, but a
# pointer copied out of that pointer, a cast of it, the address of an index
# into it, and a bare base-plus-offset address all reach the same word. Every
# one of those spellings is resolved here to the register it designates, and
# an address that is provably in the NPU region but cannot be pinned to one
# register resolves to ``UNRESOLVED`` -- which the callers refuse, because a
# pointer whose target nothing can name is a pointer no ordering rule covers.
# ---------------------------------------------------------------------------

NPU_BASE_SYMBOLS = ("U85_BASE_ADDRESS",)
UNRESOLVED_ROLE = "UNRESOLVED"

# The lookbehind keeps the ``U`` of a ``0U`` literal from reading as a name.
_IDENTIFIER_RE = re.compile(r"(?<![0-9A-Za-z_])[A-Za-z_]\w*")
_NPU_REG_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])NPU_REG_([A-Z][A-Z0-9_]*)")
_NPU_REG_DEFINE_RE = re.compile(r"^NPU_REG_([A-Z][A-Z0-9_]*)$")
_DECLARATOR_TYPES = frozenset(
    (
        "uint32_t",
        "int32_t",
        "uint64_t",
        "uintptr_t",
        "void",
        "char",
        "short",
        "int",
        "long",
        "unsigned",
        "signed",
        "volatile",
        "const",
        "struct",
    )
)
_CAST_RE = re.compile(
    r"\(\s*(?:(?:volatile|const|unsigned|signed|uint32_t|int32_t|uint64_t|uintptr_t|void|char|short|int|long)"
    r"(?![A-Za-z0-9_])\s*|\*\s*)+\)"
)
# A cast that produces a *pointer* is what separates an address expression from
# an ordinary integer one. ``x = 0U`` is a word; ``(volatile uint32_t *)0x...``
# is an address, and the difference decides whether an unnameable constant is
# ignored or refused.
_POINTER_CAST_RE = re.compile(
    r"\(\s*(?:(?:volatile|const|unsigned|signed|uint32_t|int32_t|uint64_t|uintptr_t|void|char|short|int|long)"
    r"(?![A-Za-z0-9_])\s*)+\*[\s*]*\)"
)
_INDEX_RE = re.compile(r"\[([^\[\]]*)\]")
# Whatever can end an operand makes the ``&`` after it the bitwise operator
# rather than address-of. A second ``&`` is the ``&&`` of a predicate, which is
# neither and is left alone for ``_NOT_AN_ADDRESS_RE`` to refuse.
_OPERAND_END_CHARACTERS = frozenset("&)]")
# ``*`` in value position: not a multiplication, not a declarator star.
_DEREF_RE = re.compile(r"\*\s*(?=[A-Za-z_(])")
_UNARY_DEREF_RE = re.compile(r"(?:^|[-+*/%&|^~!<>=(,?:])\s*\*\s*(?=[A-Za-z_(])")
# An address is arithmetic. A predicate or a selection is not one, and reading
# it as one would make an ordinary comparison an unresolvable NPU pointer.
_NOT_AN_ADDRESS_RE = re.compile(r"==|!=|<=|>=|&&|\|\||\?|(?<![-<>])[<>](?![-<>])")
# The declarator star sits directly against the name in ``uint32_t *p = ...``,
# so the left boundary may only refuse another name character; a compound
# assignment is already excluded because its operator sits between the name and
# the ``=``, where ``\s*`` cannot reach it.
_ASSIGNMENT_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*=(?!=)\s*([^;]+);")

# A word pointer displaces by four bytes per index step.
_POINTER_WORD_BYTES = 4

_EVAL_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|(?:0[xX][0-9A-Fa-f]+|\d+)[uUlL]*|<<|>>|[-+*/()]|\S")

# The evaluator reads an operator-supplied source, and a C integer constant that
# does not fit a machine word is not one this gate needs to fold. Refusing the
# magnitude rather than computing it keeps a written-down ``1 << 40000000`` from
# turning a verdict into a multi-megabyte allocation; ``None`` is already the
# fail-closed answer every caller handles.
_EVAL_MAGNITUDE_LIMIT = 1 << 128
_EVAL_SHIFT_LIMIT = 128


def _c_divide(left: int, right: int) -> int:
    """``left / right`` with C's truncation toward zero."""

    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def _c_modulo(left: int, right: int) -> int:
    """``left % right`` as C defines it from the truncated quotient."""

    return left - _c_divide(left, right) * right


def _evaluate_constant(
    expr: str, defines: dict[str, int], zero_names: tuple[str, ...] = ()
) -> int | None:
    """The integer ``expr`` denotes, or ``None`` when any part of it is unknown.

    ``zero_names`` are the symbols the caller wants treated as the origin, so
    the same evaluator answers "what constant is this" and "how far past that
    pointer is this".
    """

    tokens = _EVAL_TOKEN_RE.findall(expr)
    cursor = [0]

    def peek() -> str | None:
        return tokens[cursor[0]] if cursor[0] < len(tokens) else None

    def primary() -> int | None:
        token = peek()
        if token is None:
            return None
        cursor[0] += 1
        if token == "(":
            value = bit_or()
            if peek() != ")":
                return None
            cursor[0] += 1
            return value
        if token in ("+", "-", "~"):
            value = primary()
            if value is None:
                return None
            if token == "+":
                return value
            return -value if token == "-" else ~value
        if token[0].isdigit():
            try:
                return int(token.rstrip("uUlL"), 0)
            except ValueError:
                return None
        if not (token[0].isalpha() or token[0] == "_"):
            return None
        if token in zero_names:
            return 0
        return defines.get(token)

    def binary(next_level, operators) -> int | None:
        value = next_level()
        while value is not None and peek() in operators:
            operator = tokens[cursor[0]]
            cursor[0] += 1
            right = next_level()
            if right is None:
                return None
            if operator == "+":
                value += right
            elif operator == "-":
                value -= right
            elif operator == "*":
                value *= right
            elif operator in ("/", "%"):
                if right == 0:
                    return None
                # C99 6.5.5p6 truncates the quotient toward zero and defines the
                # remainder from it, so ``(0-3)/2`` is -1 and ``(0-4)%3`` is -1.
                # Python floors instead, which answers -2 and 2 -- a different
                # number, and for ``write_reg(NPU_REG_CMD, ...)`` a different
                # bit 0. An evaluator that folds a submit into a non-submit is
                # a rule the arithmetic walks around, so the C answer is the one
                # computed here.
                value = _c_divide(value, right) if operator == "/" else _c_modulo(value, right)
            elif operator == "<<":
                if not 0 <= right <= _EVAL_SHIFT_LIMIT:
                    return None
                value <<= right
            elif operator == ">>":
                if right < 0:
                    return None
                value >>= right
            elif operator == "&":
                value &= right
            elif operator == "^":
                value ^= right
            else:
                value |= right
            if abs(value) > _EVAL_MAGNITUDE_LIMIT:
                return None
        return value

    def term() -> int | None:
        return binary(primary, ("*", "/", "%"))

    def additive() -> int | None:
        return binary(term, ("+", "-"))

    def shift() -> int | None:
        return binary(additive, ("<<", ">>"))

    # The bitwise levels sit below the shifts in C's precedence, and each is its
    # own level: ``a | b & c`` is ``a | (b & c)``. Folding them is not a
    # convenience -- an address written ``0x48000014U | 0U`` designates exactly
    # one register, and an evaluator that stops at ``|`` reports the whole
    # expression as "not an address" and hands every MMIO rule below a load it
    # never sees.
    def bit_and() -> int | None:
        return binary(shift, ("&",))

    def bit_xor() -> int | None:
        return binary(bit_and, ("^",))

    def bit_or() -> int | None:
        return binary(bit_xor, ("|",))

    value = bit_or()
    return value if cursor[0] == len(tokens) else None


def npu_register_offsets(defines: dict[str, int]) -> dict[int, str]:
    """The source's own ``NPU_REG_*`` offset table, keyed by byte offset.

    An offset two register names share is not a name, so it is dropped rather
    than resolved to whichever one sorts first.
    """

    seen: dict[int, set[str]] = {}
    for name, value in defines.items():
        match = _NPU_REG_DEFINE_RE.match(name)
        if match is not None:
            seen.setdefault(value, set()).add(match.group(1))
    return {offset: sorted(names)[0] for offset, names in seen.items() if len(names) == 1}


def _role_at_offset(offset: int, defines: dict[str, int]) -> str:
    return npu_register_offsets(defines).get(offset, UNRESOLVED_ROLE)


def _has_unary_deref(expr: str) -> bool:
    return _UNARY_DEREF_RE.search(expr) is not None


def _strip_address_of(expr: str) -> str:
    """Drop every *unary* ``&`` and keep every bitwise one.

    ``expr.replace("&", " ")`` drops address-of, and it also destroys ``&`` as
    an operator -- so ``0x50004004U & V14_ADDR_MASK`` reaches the evaluator as
    two adjacent tokens, folds to ``None``, and the address the compiler builds
    from it is reported as "not an address at all". The evaluator has folded
    ``&`` all along; only this rewrite kept it from ever seeing one.

    An ``&`` is unary exactly when nothing that can end an operand precedes it,
    which is what separates ``&mailbox[3]`` from ``base & mask``.
    """

    out = list(expr)
    previous = ""
    for index, character in enumerate(expr):
        if character in _INLINE_SPACE:
            continue
        if character == "&" and not (
            previous
            and (previous in _OPERAND_END_CHARACTERS or _NAME_CHARACTER_RE.match(previous))
        ):
            out[index] = " "
            previous = "&"
            continue
        previous = character
    return "".join(out)


def _flatten_address(expr: str) -> str:
    """Drop casts and address-of, and turn an index into an additive offset."""

    stripped = _CAST_RE.sub(" ", expr)
    flattened = _INDEX_RE.sub(
        lambda match: "+((%s)*%d)" % (match.group(1).strip() or "0", _POINTER_WORD_BYTES),
        stripped,
    )
    return _strip_address_of(flattened)


def resolve_address_role(expr: str, defines: dict[str, int], known: dict[str, str]) -> str | None:
    """The register an address expression designates.

    ``None`` means the expression is not an NPU address at all;
    ``UNRESOLVED_ROLE`` means it provably is one and this gate cannot say which
    register, which is the fail-closed answer rather than a silent pass.
    """

    if _has_unary_deref(expr):
        return None
    if _NOT_AN_ADDRESS_RE.search(expr) is not None:
        # A predicate or a selection is not an address, and reading one as an
        # address would make every ordinary comparison an unresolvable NPU
        # pointer. But a *pointer cast* over one says the operator meant it as
        # an address -- ``(volatile uint32_t *)(c ? A : B)`` reaches a register
        # this gate cannot name, which is refused rather than ignored.
        return UNRESOLVED_ROLE if _POINTER_CAST_RE.search(expr) is not None else None
    flat = _flatten_address(expr)
    # A call *returns* a register value; it does not name the register's
    # address, so ``x = read_reg(NPU_REG_STATUS)`` binds a word, not a pointer.
    if _CALL_RE.search(flat) is not None:
        return None
    registers = sorted(set(_NPU_REG_NAME_RE.findall(flat)))
    if len(registers) > 1:
        return UNRESOLVED_ROLE
    if len(registers) == 1:
        return registers[0]

    pointers = sorted({name for name in _IDENTIFIER_RE.findall(flat) if name in known})
    if pointers:
        if len(pointers) > 1:
            return UNRESOLVED_ROLE
        inherited = known[pointers[0]]
        displacement = _evaluate_constant(flat, defines, (pointers[0],))
        if displacement == 0:
            return inherited
        if displacement is None or inherited == UNRESOLVED_ROLE:
            return UNRESOLVED_ROLE
        anchor = defines.get("NPU_REG_" + inherited)
        if anchor is None:
            return UNRESOLVED_ROLE
        return _role_at_offset(anchor + displacement, defines)

    bases = [name for name in NPU_BASE_SYMBOLS if names_identifier(flat, name)]
    if bases:
        offset = _evaluate_constant(flat, defines, (bases[0],))
        return UNRESOLVED_ROLE if offset is None else _role_at_offset(offset, defines)

    # What is left is an absolute address: a constant reached through a pointer
    # cast. Nothing in it names a register, so whether it can be pinned depends
    # entirely on the translation unit's own map.
    if _POINTER_CAST_RE.search(expr) is None:
        return None
    value = _evaluate_constant(flat, defines)
    if value is None:
        # The pointer cast is the operator saying "this is an address". "This
        # gate cannot fold it" is then not evidence that it is not one -- it is
        # evidence that nothing here can say *which* one, which is
        # ``UNRESOLVED`` and is refused. Reporting it as "not an address" is
        # what lets an operator walk around every MMIO rule below by choosing an
        # operator the evaluator does not implement, or by hiding a foldable
        # address behind an identifier: ``0x50004004U & V14_U32_INVALID`` is the
        # STATUS register to the compiler.
        #
        # A leftover identifier does not earn an exemption here. Every shape
        # this gate *can* name -- an ``NPU_REG_*`` offset, a bound pointer, a
        # base symbol -- was resolved above, so reaching this line with an
        # identifier still in hand means the register genuinely cannot be named.
        return UNRESOLVED_ROLE
    # An address is an unsigned machine word. ``~0xB7FFFFEBU`` is 0x48000014 to
    # the compiler and a negative integer to an evaluator that folds without
    # width, so the fold is normalised before it is compared against the window.
    value &= 0xFFFFFFFF
    table = npu_register_offsets(defines)
    base = defines.get(NPU_BASE_SYMBOLS[0])
    if base is None or not table:
        # The source pins no register map at all, so this gate cannot say which
        # word -- or even which peripheral -- the address reaches. Ignoring it
        # would let every ordering, counting and isolation rule below be walked
        # around by writing the number instead of the name, so it is refused.
        # Resolving it from an assumed map is the one thing this gate must not
        # do: an offset table it invented is not the source's.
        return UNRESOLVED_ROLE
    if not base <= value <= base + max(table):
        return None
    return table.get(value - base, UNRESOLVED_ROLE)


# An alias walk that re-scans every binding once per pass costs one pass per
# link of a copy chain, so ``p1 = p0; p2 = p1; ...`` is quadratic and a source
# well inside ``_MAX_SOURCE_BYTES`` turns a verdict into hours. The walks below
# are worklists instead: a binding is re-examined only when a name it actually
# mentions changes. Each name changes at most twice -- unbound to bound, bound
# to ``UNRESOLVED`` -- so the work is bounded by twice the number of
# name-to-binding edges, which is linear in the source.
#
# The budget is that bound written down. It is derived from the input rather
# than fixed, so it scales with a legitimately large source and still refuses a
# walk that does not converge; ``4x`` leaves room for the lattice without
# leaving room for a quadratic blow-up. Exceeding it is a named verdict, never a
# hang and never a ``RecursionError``.
_ALIAS_BUDGET_FACTOR = 4
_ALIAS_BUDGET_FLOOR = 1024


def _binding_dependents(
    bindings: tuple[tuple[str, str], ...]
) -> tuple[dict[str, list[int]], int]:
    """``name -> binding indices mentioning it``, and the total edge count."""

    dependents: dict[str, list[int]] = {}
    edges = 0
    for index, (_name, expr) in enumerate(bindings):
        for token in set(_IDENTIFIER_RE.findall(expr)):
            dependents.setdefault(token, []).append(index)
            edges += 1
    return dependents, edges


def _alias_fixpoint(bindings, resolve, collapse, what: str) -> dict[str, object]:
    """The least fixpoint of ``resolve`` over ``bindings``, on a bounded worklist.

    ``resolve(expr, known)`` answers what a binding's right-hand side designates
    given what is known so far, or ``None`` when it designates nothing here.
    ``collapse`` reduces the set of answers a name accumulated to the one value
    every rule downstream reads -- a name that resolved two ways is the
    fail-closed ``UNRESOLVED``.
    """

    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    observed: dict[str, set[object]] = {}
    known: dict[str, object] = {}
    pending = collections.deque(range(len(bindings)))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving %s did not settle within %d steps: the source binds more aliases than "
                "this gate walks" % (what, budget)
            )
        name, expr = bindings[index]
        answer = resolve(expr, known)
        if answer is None:
            continue
        seen = observed.setdefault(name, set())
        if answer in seen:
            continue
        seen.add(answer)
        collapsed = collapse(seen)
        if name in known and known[name] == collapsed:
            continue
        known[name] = collapsed
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return known


def pointer_roles(body: str, defines: dict[str, int]) -> dict[str, str]:
    """Every name in ``body`` bound to an NPU register, transitively.

    A pointer copied from a bound pointer is the same pointer, and a chain of
    such copies is still that pointer, so the bindings are re-scanned until
    nothing new resolves. A name bound twice to two different registers is
    ``UNRESOLVED``: nothing here can say which binding a later dereference
    reaches.

    ``p += 4`` and ``++p`` re-point a bound pointer at another register without
    ever writing ``p = expr``, so the binding walk above cannot see them and
    would keep crediting the original register for every later dereference --
    which is worse than not seeing the load, because the load then *satisfies*
    a read-order rule while reading somewhere else. A stepped name is therefore
    ``UNRESOLVED`` here, and refused by ``require_resolved_pointers``.
    """

    bindings = tuple(
        (match.group(1), match.group(2)) for match in _ASSIGNMENT_RE.finditer(body)
    )
    resolved = _alias_fixpoint(
        bindings,
        lambda expr, known: resolve_address_role(expr, defines, known),
        lambda roles: sorted(roles)[0] if len(roles) == 1 else UNRESOLVED_ROLE,
        "an NPU-region pointer",
    )
    for name in compound_assignment_targets(body, tuple(sorted(resolved))):
        resolved[name] = UNRESOLVED_ROLE
    return resolved


def unresolved_pointers(roles: dict[str, str]) -> tuple[str, ...]:
    return tuple(sorted(name for name, role in roles.items() if role == UNRESOLVED_ROLE))


def require_resolved_pointers(roles: dict[str, str], what: str) -> None:
    unresolved = unresolved_pointers(roles)
    if unresolved:
        raise fail(
            "%s binds an NPU-region pointer this gate cannot resolve to one register: %s"
            % (what, ", ".join(unresolved))
        )


_FUNCTION_MACRO_RE = re.compile(
    r"(?m)^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)\([^)\n]*\)[ \t]*(.*)$"
)


def mmio_macro_names(masked: str) -> tuple[str, ...]:
    """Every function-like macro whose body dereferences a pointer cast.

    ``#define REG32(a) (*(volatile uint32_t *)(a))`` turns an MMIO access into
    what reads here as an ordinary call, so the address never reaches
    ``resolve_address_role`` and the access is counted as nothing. This gate
    does not preprocess, so it cannot say which register such a call names --
    which makes it exactly the unresolved access every rule in this file
    refuses rather than ignores.
    """

    found = set()
    for match in _FUNCTION_MACRO_RE.finditer(masked):
        body = match.group(2)
        if _POINTER_CAST_RE.search(body) is not None and _DEREF_RE.search(body) is not None:
            found.add(match.group(1))
    return tuple(sorted(found))


def require_no_macro_mmio(text: str, macros: tuple[str, ...], what: str) -> None:
    """Refuse an MMIO access made through a macro this gate cannot expand."""

    for name in macros:
        if code_contains(text, name + "("):
            raise fail(
                "%s reaches an NPU-region address this gate cannot resolve to one register: "
                "the macro %s expands to an unexpanded MMIO dereference" % (what, name)
            )


def require_resolved_dereferences(
    text: str, defines: dict[str, int], roles: dict[str, str], what: str
) -> None:
    """Refuse an MMIO dereference this gate cannot pin to one register.

    ``require_resolved_pointers`` covers an address that is *bound to a name*.
    This covers the one that is not: an absolute address dereferenced where it
    stands. Its role reaches every rule below as ``UNRESOLVED``, and a rule that
    merely fails to recognise it is a rule the number walks around -- so the
    access is named here rather than counted as nothing.
    """

    for site, role, is_write in dereference_sites(text, defines, roles):
        if role == UNRESOLVED_ROLE:
            raise fail(
                "%s reaches an NPU-region address this gate cannot resolve to one register: "
                "%s at offset %d" % (what, "write" if is_write else "read", site)
            )


# ---------------------------------------------------------------------------
# Assignment structure
#
# A rule written over the *shape* of an lvalue is a rule every other spelling of
# the same store walks around. Assignments are therefore recovered here as whole
# statements -- delimited by the surrounding ``;``/``{``/``}`` rather than by a
# pattern for what an lvalue may look like -- so the lvalue arrives intact and
# can be resolved to the storage it designates.
# ---------------------------------------------------------------------------

_COMPOUND_ASSIGN_OPERATORS = ("<<=", ">>=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=")
# The character before an ``=`` that makes it something other than a plain
# assignment: the second half of a comparison, or the tail of a compound
# operator whose target is read as well as written.
_ASSIGNMENT_BOUNDARY = frozenset("=!<>+-*/%&|^")


def _alternation(names: tuple[str, ...]) -> str:
    return "|".join(re.escape(name) for name in names)


# Every name a statement steps: ``n op= ...``, ``++n``/``--n``, ``n++``/``n--``.
# Built once over the operator set rather than per call over a name set, so the
# scan is one linear pass whatever the source binds.
_STEPPED_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(?:%s)"
    r"|(?:\+\+|--)\s*([A-Za-z_]\w*)(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(?:\+\+|--)"
    % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
)


def _statement_end(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            return index
    return len(text)


# A directive is a *logical* line, so a backslash continuation carries it on.
# Blanking only the first physical line of a continued ``#define`` deletes the
# parentheses it opened and leaves the ones its continuation closes.
_DIRECTIVE_LINE_RE = re.compile(r"(?m)^[ \t]*#(?:\\[ \t]*\n|[^\n])*")


def blank_directives(text: str) -> str:
    """Blank every preprocessor directive line, preserving each byte offset.

    A directive is not a statement and carries no terminator, so a scan that
    breaks statements on ``;``/``{``/``}`` alone folds the directive line into
    the *next* statement's lvalue: ``#line 1`` above ``d.variant_id = ...``
    makes the lvalue ``#line 1 d.variant_id``, which no ``^``-anchored lvalue
    rule matches. The store then exists for the compiler and not for the gate.
    Blanking the line in place removes it from the statement stream while
    leaving every offset -- which the load-provenance and dominance rules
    compare against -- exactly where it was.
    """

    return _DIRECTIVE_LINE_RE.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), text
    )


def assignment_statements(text: str) -> tuple[tuple[int, str, str], ...]:
    """``(start, lvalue, rvalue)`` for every simple assignment in ``text``."""

    scan = blank_directives(text)
    found: list[tuple[int, str, str]] = []
    depth = 0
    start = 0
    for index, character in enumerate(scan):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            start = index + 1
        elif (
            depth == 0
            and character == "="
            and scan[index + 1 : index + 2] != "="
            and scan[index - 1 : index] not in _ASSIGNMENT_BOUNDARY
        ):
            stop = _statement_end(scan, index + 1)
            found.append((start, scan[start:index], scan[index + 1 : stop]))
    return tuple(found)


_COMPOUND_LVALUE_RE = re.compile(
    r"(?:%s)" % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
)
_STEP_RE = re.compile(r"\+\+|--")


def compound_assignment_lvalues(text: str) -> tuple[tuple[int, str], ...]:
    """``(start, lvalue)`` for every read-modify-write statement in ``text``.

    A compound assignment and an increment are stores that no ``name = expr``
    walk sees, and the lvalue they write is an expression rather than a name:
    ``mailbox[V14_MBOX_VARIANT_ID] += 2U`` and ``0[mailbox]++`` both mutate an
    appendix word after its canonical store, and a rule that only knows the
    bare array name never looks at either. The whole lvalue is recovered here
    so the caller can resolve *which storage* it designates.
    """

    scan = blank_directives(text)
    found: list[tuple[int, str]] = []
    depth = 0
    start = 0
    index = 0
    length = len(scan)
    while index < length:
        character = scan[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in ";{}":
            start = index + 1
        elif depth == 0:
            compound = _COMPOUND_LVALUE_RE.match(scan, index)
            if compound is not None and scan[compound.end() : compound.end() + 1] != "=":
                found.append((start, scan[start:index]))
                index = compound.end()
                continue
            step = _STEP_RE.match(scan, index)
            if step is not None:
                before = scan[start:index].strip()
                after = _expression_after(scan, step.end())
                found.append((start, before if before else after))
                index = step.end()
                continue
        index += 1
    return tuple(found)


def compound_assignment_targets(text: str, names: tuple[str, ...]) -> tuple[str, ...]:
    """Every name in ``names`` that ``text`` compound-assigns or increments.

    ``p += 1`` and ``++p`` re-point a pointer without ever writing a plain
    assignment, so a provenance walk built on ``name = expr`` cannot see them.
    Naming them here is what keeps that walk honest.
    """

    if not names:
        return ()
    # Driven by the *operator*, not by an alternation of every candidate name.
    # A pattern rebuilt from n names and matched against the whole text costs
    # O(n x len(text)), so a source that binds thousands of pointers pays a full
    # rescan per name -- the quadratic this walk is bounded against. One pass
    # collects every stepped name; the set membership does the filtering.
    wanted = frozenset(names)
    found = {
        name
        for match in _STEPPED_NAME_RE.finditer(text)
        for name in (match.group(1) or match.group(2) or match.group(3),)
        if name in wanted
    }
    return tuple(sorted(found))


def _is_declaration(lvalue: str) -> bool:
    match = re.match(r"\s*([A-Za-z_]\w*)", lvalue)
    return match is not None and match.group(1) in _DECLARATOR_TYPES


def _strip_leading_derefs(expr: str) -> tuple[int, str]:
    stripped = expr.strip()
    count = 0
    while stripped.startswith("*"):
        count += 1
        stripped = stripped[1:].lstrip()
    return count, stripped


def _flatten_word_address(expr: str) -> str:
    """Drop casts and address-of, and turn an index into a *word* offset.

    ``_flatten_address`` answers the same question in bytes, because an MMIO
    pointer displaces by four per step. The mailbox is addressed by appendix
    word, so the same walk counts in words here.
    """

    stripped = _CAST_RE.sub(" ", expr)
    flattened = _INDEX_RE.sub(
        lambda match: "+(%s)" % (match.group(1).strip() or "0"), stripped
    )
    return _strip_address_of(flattened)


def resolve_mailbox_word(expr: str, defines: dict[str, int], known: dict[str, object]) -> object:
    """The appendix word an expression designates, over every spelling.

    ``None`` means the expression does not reach the mailbox at all;
    ``UNRESOLVED_ROLE`` means it provably does and this gate cannot say which
    word, which is the fail-closed answer rather than a silent pass.
    """

    derefs, addressed = _strip_leading_derefs(expr)
    flat = _flatten_word_address(addressed)
    if _CALL_RE.search(flat) is not None:
        return None
    names = sorted(
        {
            name
            for name in _IDENTIFIER_RE.findall(flat)
            if name == MAILBOX_SYMBOL or name in known
        }
    )
    if not names:
        return None
    if len(names) > 1 or derefs > 1:
        return UNRESOLVED_ROLE
    base = names[0]
    inherited = 0 if base == MAILBOX_SYMBOL else known[base]
    step = _evaluate_constant(flat, defines, (base,))
    if inherited == UNRESOLVED_ROLE or step is None:
        return UNRESOLVED_ROLE
    return inherited + step


def _expression_after(text: str, start: int) -> str:
    """The expression beginning at ``start``, up to its statement terminator."""

    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if character in ";,":
                break
            if character == "=" and text[index + 1 : index + 2] != "=":
                break
        index += 1
    return text[start:index]


_INLINE_SPACE = " \t\n\r\f\v"


def _token_before(text: str, index: int) -> tuple[int, str]:
    """``(start, token)`` for the name token ending just before ``index``.

    Written as a bounded backward scan rather than ``text[:index].rstrip()`` and
    a ``$``-anchored search. Both of those are linear in the *whole* prefix, and
    a source with many declarator stars then costs one full prefix scan each --
    quadratic in exactly the input the size bound was supposed to cover.
    """

    cursor = index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    stop = cursor + 1
    while cursor >= 0 and _NAME_CHARACTER_RE.match(text[cursor]):
        cursor -= 1
    return cursor + 1, text[cursor + 1 : stop]


def _token_after(text: str, index: int) -> str:
    """The name token beginning just after ``index``."""

    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    start = cursor
    while cursor < len(text) and _NAME_CHARACTER_RE.match(text[cursor]):
        cursor += 1
    return text[start:cursor]


def _next_non_space(text: str, index: int) -> str:
    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    return text[cursor : cursor + 2]


def _is_declarator_star(text: str, star_index: int) -> bool:
    if _token_before(text, star_index)[1] in _DECLARATOR_TYPES:
        return True
    return _token_after(text, star_index + 1) in _DECLARATOR_TYPES


_BRACKET_OPENERS = {")": "(", "]": "["}


def _bracket_pairs(text: str) -> tuple[dict[int, int], dict[int, int]]:
    """``(close_of_open, open_of_close)`` for every matched bracket, in one pass.

    Matching each bracket on demand means rescanning from it to the end of the
    text, and an unterminated ``[`` makes that rescan reach the end every time --
    so a source made of nothing but openers costs one full scan per opener. The
    same shape ``_mask_one_pass`` already guards against for ``/*``, answered the
    same way: walk the text once and remember the answers.
    """

    close_of: dict[int, int] = {}
    open_of: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    for index, character in enumerate(text):
        if character in "([":
            stack.append((character, index))
        elif character in ")]":
            if stack and stack[-1][0] == _BRACKET_OPENERS[character]:
                _opener, start = stack.pop()
                close_of[start] = index
                open_of[index] = start
    return close_of, open_of


def _subscript_expression(
    text: str, bracket: int, pairs: tuple[dict[int, int], dict[int, int]]
) -> tuple[int, str, int] | None:
    """``(start, expression, stop)`` for the subscript opening at ``bracket``.

    The base is the postfix expression the ``[`` binds to -- a name, an integer
    literal, or a parenthesised expression -- so ``p[0]``, ``0[p]`` and
    ``(base + 1)[0]`` are each recovered whole and handed to the same resolver a
    ``*`` access is handed.
    """

    close_of, open_of = pairs
    close = close_of.get(bracket)
    if close is None:
        return None
    cursor = bracket - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return None
    if text[cursor] in ")]":
        start = open_of.get(cursor)
        if start is None:
            return None
    else:
        start, token = _token_before(text, cursor + 1)
        if not token:
            return None
    return start, text[start : close + 1], close + 1


def _assigns_at(text: str, stop: int) -> bool:
    """Whether an assignment operator, not a comparison, follows ``stop``."""

    tail = _next_non_space(text, stop)
    return tail.startswith("=") and not tail.startswith("==")


def access_expressions(text: str) -> tuple[tuple[int, str, bool], ...]:
    """``(offset, address expression, is_write)`` for every MMIO-shaped access.

    C spells one load two ways. ``*p`` and ``p[0]`` are the same access --
    6.5.2.1 *defines* ``E1[E2]`` as ``(*((E1)+(E2)))`` -- and the subscript is
    commutative, so ``0[p]`` is that load too. Enumerating only the ``*``
    spelling leaves the others invisible to every ordering, counting and
    provenance rule below, which is worse than not seeing the access: a read
    spelled ``status_reg[0]`` satisfies no read-order rule *and* trips none, so
    the manifest keeps asserting a read order the built image does not have.

    The address expression is handed back rather than a role, because the NVIC
    isolation rule folds these same expressions against a different window than
    the NPU register map.
    """

    found: list[tuple[int, str, bool]] = []
    for match in _DEREF_RE.finditer(text):
        if _is_declarator_star(text, match.start()):
            continue
        expression = _expression_after(text, match.end())
        stop = match.end() + len(expression)
        found.append((match.start(), expression, _assigns_at(text, stop)))
    pairs = _bracket_pairs(text)
    for index, character in enumerate(text):
        if character != "[":
            continue
        recovered = _subscript_expression(text, index, pairs)
        if recovered is None:
            continue
        start, expression, stop = recovered
        # A ``*`` in front of the base already entered this access above, and
        # counting it twice would turn one load into two.
        cursor = start - 1
        while cursor >= 0 and text[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and text[cursor] == "*" and not _is_declarator_star(text, cursor):
            continue
        found.append((start, expression, _assigns_at(text, stop)))
    return tuple(sorted(found))


def dereference_sites(
    text: str, defines: dict[str, int], roles: dict[str, str]
) -> tuple[tuple[int, str, bool], ...]:
    """``(offset, role, is_write)`` for every MMIO access in ``text``."""

    found: list[tuple[int, str, bool]] = []
    for site, expression, is_write in access_expressions(text):
        role = resolve_address_role(expression, defines, roles)
        if role is None:
            continue
        found.append((site, role, is_write))
    return tuple(found)


def register_access_sites(
    text: str,
    register: str,
    defines: dict[str, int],
    roles: dict[str, str] | None = None,
    write: bool = False,
) -> tuple[int, ...]:
    """Every offset in ``text`` that reads or writes ``register``, any spelling."""

    if roles is None:
        roles = pointer_roles(text, defines)
    verb = "write_reg" if write else "read_reg"
    sites = set(
        code_positions(text, "%s(NPU_REG_%s" % (verb, register), open_end=(register == "QBASE"))
    )
    for site, role, is_write in dereference_sites(text, defines, roles):
        if role == register and is_write == write:
            sites.add(site)
    return tuple(sorted(sites))


_CMD_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])write_reg\s*\(\s*NPU_REG_CMD(?![A-Za-z0-9_])\s*,([^;]*?)\)\s*;"
)


def cmd_write_values(
    text: str, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[tuple[int, int | None], ...]:
    """``(offset, value)`` for every CMD write; ``value`` is ``None`` when opaque.

    The value is the OR of every constant term, because that is what decides
    whether a write starts the NPU (bit 0), and a term this gate cannot read is
    reported as opaque rather than assumed harmless.
    """

    if roles is None:
        roles = pointer_roles(text, defines)
    found: list[tuple[int, int | None]] = []
    for match in _CMD_VALUE_RE.finditer(text):
        found.append((match.start(), _or_terms(match.group(1), defines)))
    for site, role, is_write in dereference_sites(text, defines, roles):
        if role != "CMD" or not is_write:
            continue
        tail = text[site:]
        assignment = re.search(r"=(?!=)([^;]*);", tail)
        found.append((site, _or_terms(assignment.group(1), defines) if assignment else None))
    return tuple(sorted(found))


def _or_terms(value: str, defines: dict[str, int]) -> int | None:
    resolved = 0
    for term in _split_top_level(value, "|"):
        part = _evaluate_constant(term, defines)
        if part is None:
            return None
        resolved |= part
    return resolved


def submit_write_sites(
    text: str, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[int, ...]:
    """Every CMD write that starts the NPU, whatever spelling sets bit 0."""

    return tuple(
        site for site, value in cmd_write_values(text, defines, roles) if value is None or value & 1
    )


def cmd_write_sites_with_value(
    text: str, wanted: int, defines: dict[str, int], roles: dict[str, str] | None = None
) -> tuple[int, ...]:
    return tuple(site for site, value in cmd_write_values(text, defines, roles) if value == wanted)


_PRE_SUBMIT_GATES = (
    ("V14_STATUS_STATE", "stopped"),
    ("V14_STATUS_IRQ_RAISED", "stale irq_raised"),
    ("V14_STATUS_RESET", "reset_status"),
    ("V14_STATUS_CMD_END", "stale cmd_end_reached"),
    ("V14_STATUS_FAULT_MASK", "vendor fault"),
)


def _guard_blocks(block: str, subject: str) -> tuple[tuple[str, str], ...]:
    """Return ``(condition, body)`` for every ``if`` whose condition names ``subject``."""

    found = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])if\s*\(", block):
        depth = 0
        index = match.end() - 1
        while index < len(block):
            if block[index] == "(":
                depth += 1
            elif block[index] == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        condition = block[match.end() : index]
        tail = block[index + 1 :]
        stripped = tail.lstrip()
        if not stripped.startswith("{"):
            continue
        open_index = index + 1 + (len(tail) - len(stripped))
        close_index = _matching_brace(block, open_index, "guard body")
        if names_identifier(condition, subject):
            found.append((condition, block[open_index + 1 : close_index]))
    return tuple(found)


def require_load_provenance(
    body: str, name: str, load_sites: tuple[int, ...], register: str, what: str
) -> None:
    """Prove ``name`` holds the value the counted ``register`` load produced.

    Counting the loads and grepping the guards for the mask macros proves the
    two exist; it does not prove they are connected. ``pre_program_status = 0U``
    beside a discarded ``read_reg(NPU_REG_STATUS)`` satisfies both counts and
    turns a mandatory fail-closed gate into a comparison against a constant that
    always passes. So the assignment that produced the guarded value has to
    *be* one of the loads the gate counted, and nothing may overwrite it after.

    "Nothing may overwrite it" is a claim about the *storage*, not about the
    spelling of an lvalue. ``*(&pre_submit_status) = 0U`` writes the same word
    as ``pre_submit_status = 0U`` and matches no name-shaped pattern, so a rule
    written over the pattern lets the clearing store back in and every gate
    below it compares against zero. Two things therefore have to hold: every
    assignment whose lvalue mentions the name is written in the plain form this
    walk can order, and the name's address is never taken at all -- because a
    pointer to it is a second lvalue this intraprocedural walk cannot follow.
    """

    stepped = compound_assignment_targets(body, (name,))
    if stepped:
        raise fail(
            "%s: %s is compound-assigned rather than bound to the %s load it is gated on"
            % (what, name, register)
        )
    plain = re.compile(r"^\s*(?:[A-Za-z_]\w*\s+)*\*?\s*%s\s*$" % re.escape(name))
    for _start, lvalue, _rvalue in assignment_statements(body):
        if names_identifier(lvalue, name) and plain.match(lvalue) is None:
            raise fail(
                "%s: %s is written through an lvalue this gate cannot bind to its storage: %s"
                % (what, name, re.sub(r"\s+", " ", lvalue.strip())[:40])
            )
    if re.search(r"&\s*%s(?![A-Za-z0-9_])" % re.escape(name), body) is not None:
        raise fail(
            "%s: the address of %s is taken, so the %s load its guards are credited for can be "
            "overwritten through an alias this gate cannot follow" % (what, name, register)
        )
    assignments = [
        (start, _statement_end(body, start), rvalue)
        for start, lvalue, rvalue in assignment_statements(body)
        if plain.match(lvalue)
    ]
    if not assignments:
        raise fail("%s: %s is never assigned the %s load" % (what, name, register))
    loading = [
        assignment
        for assignment in assignments
        if any(assignment[0] <= site < assignment[1] for site in load_sites)
    ]
    if len(loading) != 1:
        raise fail(
            "%s: %s is not bound to the %s load this gate counted: %d of its %d assignments "
            "read the register" % (what, name, register, len(loading), len(assignments))
        )
    if any(start > loading[0][0] for start, _stop, _rvalue in assignments):
        raise fail(
            "%s: %s is reassigned after the %s load its guards are credited for"
            % (what, name, register)
        )


def verify_pre_run_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the stopped-state gate, the single QSIZE snapshot and fail-closed submit."""

    if defines.get("V14_QSIZE_EXPECTED") != QSIZE_EXPECTED:
        raise fail(
            "qsize_expected is not manifest 0x110: V14_QSIZE_EXPECTED is %s"
            % ("undefined" if "V14_QSIZE_EXPECTED" not in defines else "0x%X" % defines["V14_QSIZE_EXPECTED"])
        )
    require_define(defines, "V14_STATUS_STATE", STATUS_STATE, "status mask contract")
    require_define(defines, "V14_STATUS_IRQ_RAISED", STATUS_IRQ_RAISED, "status mask contract")
    require_define(defines, "V14_STATUS_RESET", STATUS_RESET, "status mask contract")
    require_define(defines, "V14_STATUS_CMD_END", STATUS_CMD_END, "status mask contract")
    require_define(defines, "V14_STATUS_FAULT_MASK", STATUS_FAULT_MASK, "status mask contract")

    # The gate is anchored on whichever function actually programs the queue,
    # rather than on a function name, so the proof holds wherever the vendor
    # keeps its programming.
    mmio_macros = mmio_macro_names(vendor_masked)
    spans = function_spans(vendor_masked)
    programming_sites = code_positions(vendor_masked, _QBASE_WRITE, open_end=True) + code_positions(
        vendor_masked, _QSIZE_WRITE
    )
    if not programming_sites:
        raise fail("pre-program STATUS gate does not dominate QBASE/QSIZE: no queue programming found")
    owners = {enclosing_function(spans, site) for site in programming_sites}
    if len(owners) != 1:
        raise fail("queue programming is split across %d functions: %s" % (len(owners), sorted(owners)))
    setup_start, setup_stop = function_span(vendor_masked, sorted(owners)[0], "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]
    setup_roles = pointer_roles(setup, defines)
    require_resolved_pointers(setup_roles, "queue setup function")
    require_resolved_dereferences(setup, defines, setup_roles, "the queue setup function")
    require_no_macro_mmio(setup, mmio_macros, "the queue setup function")

    pre_program_reads = register_access_sites(setup, "STATUS", defines, setup_roles)
    queue_accesses = code_positions(setup, _QBASE_WRITE, open_end=True) + code_positions(
        setup, _QSIZE_WRITE
    )
    if len(pre_program_reads) != 1 or pre_program_reads[0] > min(queue_accesses):
        raise fail(
            "pre-program STATUS gate does not dominate QBASE/QSIZE: %d gate loads, first queue access at %d"
            % (len(pre_program_reads), min(queue_accesses))
        )

    for mask, label in (
        ("V14_STATUS_STATE", "stopped"),
        ("V14_STATUS_RESET", "reset_status"),
        ("V14_STATUS_FAULT_MASK", "vendor fault"),
    ):
        guards = [c for c, _ in _guard_blocks(setup, "pre_program_status") if names_identifier(c, mask)]
        if len(guards) != 1:
            raise fail("pre-program gate omits stopped/reset/fault: %s check is missing" % label)

    require_load_provenance(
        setup, "pre_program_status", pre_program_reads, "STATUS", "pre-program gate"
    )

    # The design forbids a running transition *between* the gate and the
    # programming writes, not a CMD write anywhere in the setup function, so
    # the window is exactly that span. A CMD write reached through a raw
    # pointer transitions the state exactly as the vendor accessor does.
    gate_start = pre_program_reads[0]
    programming_start = min(queue_accesses)
    if any(
        gate_start <= site < programming_start
        for site, _value in cmd_write_values(setup, defines, setup_roles)
    ):
        raise fail(
            "state-transitioning CMD write between the pre-program gate and queue programming"
        )

    qsize_writes = code_positions(setup, _QSIZE_WRITE)
    if not qsize_writes:
        raise fail(
            "queue programming does not write QSIZE: the setup function programs QBASE only"
        )
    final_qsize_write = max(qsize_writes)
    for site in register_access_sites(setup, "QSIZE", defines, setup_roles):
        if site < final_qsize_write:
            raise fail("qsize snapshot precedes the final QSIZE programming write")

    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    command_roles = pointer_roles(command, defines)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, mmio_macros, "the command function")

    qsize_loads = register_access_sites(command, "QSIZE", defines, command_roles)
    if len(qsize_loads) == 0:
        raise fail("qsize_expected snapshot is missing between final programming and submit")
    if len(qsize_loads) != 1:
        raise fail("QSIZE is loaded more than once: %d loads in the command path" % len(qsize_loads))

    # A submit is a CMD write that sets bit 0, whichever spelling sets it, so a
    # second start written as ``1`` rather than ``0x00000001`` -- or through a
    # raw CMD pointer -- is counted here rather than walked around.
    submits = submit_write_sites(command, defines, command_roles)
    if len(submits) != 1:
        raise fail(
            "command path does not carry exactly one NPU submit write: %d submit writes"
            % len(submits)
        )
    running_qsize_loads = tuple(site for site in qsize_loads if site > submits[0])
    if running_qsize_loads:
        raise fail("running QSIZE reachable: the QSIZE load follows the submit write")

    # Only the window up to submit belongs to the pre-run gate; STATUS reads
    # after submit are the tail's business and are judged by the cleanup gate.
    status_loads = tuple(
        site
        for site in register_access_sites(command, "STATUS", defines, command_roles)
        if site < submits[0]
    )
    if len(status_loads) != 1:
        raise fail(
            "post-program STATUS load is not distinct from the pre-program load: %d loads"
            % len(status_loads)
        )

    qsize_compare = _guard_blocks(command, "qsize_expected")
    if not any(names_identifier(condition, "V14_QSIZE_EXPECTED") for condition, _ in qsize_compare):
        raise fail("qsize_expected is not manifest 0x110: no compare against V14_QSIZE_EXPECTED")

    pre_submit_guards = _guard_blocks(command, "pre_submit_status")
    for mask, label in _PRE_SUBMIT_GATES:
        if not any(names_identifier(condition, mask) for condition, _ in pre_submit_guards):
            raise fail("post-program stale/reset/fault gate is incomplete: %s check is missing" % label)

    for condition, body in tuple(qsize_compare) + pre_submit_guards:
        if not names_identifier(body, "return"):
            raise fail("pre-run failure reaches submit: guard (%s) does not return" % condition.strip()[:40])

    # Both post-program gates are credited for a load; prove each consumes the
    # one this gate counted rather than a constant beside a discarded read.
    require_load_provenance(
        command, "pre_submit_status", status_loads, "STATUS", "post-program gate"
    )
    require_load_provenance(
        command, "qsize_expected", qsize_loads, "QSIZE", "qsize_expected snapshot"
    )

    return {
        "pre_program_status_loads": len(pre_program_reads),
        "post_program_status_loads": len(status_loads),
        "qsize_loads": len(qsize_loads),
        "qsize_expected": "0x%08X" % QSIZE_EXPECTED,
        "running_qsize_loads": len(running_qsize_loads),
    }


# ---------------------------------------------------------------------------
# Statement-level effect model
# ---------------------------------------------------------------------------

_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*\(")
_NON_CALL_KEYWORDS = frozenset(
    ("if", "for", "while", "switch", "return", "sizeof", "uint32_t", "int32_t", "volatile", "uintptr_t")
)
# A store is recognised by the *storage its lvalue names*, never by the shape
# the lvalue is written in. C's subscript is commutative, so ``33[mailbox]``
# writes the same word as ``mailbox[33]``; ``*(mailbox + 33)`` writes it too,
# and so does a second name bound to the array. Matching ``mailbox[`` alone
# leaves each of those a way past every per-iteration, publication-site and
# tuple-isolation rule below, so the recogniser names the symbol and its
# aliases and lets ``resolve_mailbox_word`` say which word was reached.
_STORE_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_])obs(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_]))"
    % re.escape(MAILBOX_SYMBOL)
)

# A register touched through its raw address expression is the same observable
# as one touched through a bound pointer; only the spelling differs. Naming the
# register is what makes it an access, so ``NPU_REG_STATUS`` written inline
# counts exactly as ``*status_reg`` does.
_RAW_REGISTER_RE = re.compile(r"NPU_REG_([A-Z][A-Z0-9_]*)")

# ---------------------------------------------------------------------------
# Storage provenance
#
# An alias is a second name for the same storage, and a name reached through a
# cast or a chain of copies is still that name. ``obs_alias->result`` writes the
# observation record; ``mb[33]``, ``33[mb]`` and ``*(mb + 33)`` all write mailbox
# word 33. Every rule below is expressed over the storage an lvalue designates,
# so the bindings are resolved transitively here and the *word* is judged
# separately from the *spelling* that reached it.
# ---------------------------------------------------------------------------

_MEMBER_ACCESS_RE = re.compile(r"->|\.")


def _bindings(text: str) -> tuple[tuple[str, str], ...]:
    return tuple((match.group(1), match.group(2)) for match in _ASSIGNMENT_RE.finditer(text))


def _is_pointer_binding(expr: str) -> bool:
    """Whether ``expr`` hands over the storage itself rather than a word of it.

    ``p = mb`` and ``p = &mb[3]`` name the array; ``v = mb[3]`` names the value
    in one of its words, and calling that an alias would make every reader of a
    mailbox word a second name for the mailbox.
    """

    if "&" in expr:
        return True
    return "[" not in expr and not _has_unary_deref(expr)


def obs_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the observation record pointer, transitively."""

    bindings = _bindings(text)
    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    names = {"obs"}
    pending = collections.deque(dependents.get("obs", ()))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving an observation-record alias did not settle within %d steps: the "
                "source binds more aliases than this gate walks" % budget
            )
        name, expr = bindings[index]
        if name in names or _MEMBER_ACCESS_RE.search(expr) is not None:
            continue
        stripped = _strip_address_of(_CAST_RE.sub(" ", expr))
        if not any(token in names for token in _IDENTIFIER_RE.findall(stripped)):
            continue
        names.add(name)
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return tuple(sorted(names - {"obs"}))


def mailbox_alias_words(text: str, defines: dict[str, int]) -> dict[str, object]:
    """Every name bound to the mailbox array, with the word it starts at.

    ``UNRESOLVED_ROLE`` is a displacement nothing here can evaluate -- a name
    bound twice, or bound past the array by arithmetic this gate cannot read.
    That is the fail-closed answer: a second name whose origin is unknown is a
    name no word rule covers.
    """

    def resolve(expr: str, known: dict[str, object]) -> object:
        if not _is_pointer_binding(expr):
            return None
        return resolve_mailbox_word(expr, defines, known)

    resolved = _alias_fixpoint(
        _bindings(text),
        resolve,
        lambda words: sorted(words, key=repr)[0] if len(words) == 1 else UNRESOLVED_ROLE,
        "a mailbox alias",
    )
    return {name: word for name, word in resolved.items() if name != MAILBOX_SYMBOL}


def mailbox_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the failure mailbox array."""

    return tuple(sorted(mailbox_alias_words(text, {})))


def store_pattern(text: str) -> re.Pattern[str]:
    """A store recogniser that also sees ``text``'s obs and mailbox aliases."""

    names = ("obs",) + obs_aliases(text) + (MAILBOX_SYMBOL,) + mailbox_aliases(text)
    return re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % _alternation(names))


def function_spans(masked: str) -> tuple[tuple[str, int, int], ...]:
    """Return ``(name, body_start, body_stop)`` for every top-level brace block."""

    spans: list[tuple[str, int, int]] = []
    index = 0
    declarator_start = 0
    while index < len(masked):
        character = masked[index]
        if character == "{":
            head = masked[declarator_start:index]
            names = _CALL_RE.findall(head)
            close = _matching_brace(masked, index, "top-level block")
            spans.append((names[-1] if names else "", index + 1, close))
            index = close + 1
            declarator_start = index
            continue
        if character == ";":
            declarator_start = index + 1
        index += 1
    return tuple(spans)


def enclosing_block_start(text: str, position: int) -> int:
    """The offset just inside the innermost ``{`` still open at ``position``."""

    stack: list[int] = []
    for index in range(min(position, len(text))):
        character = text[index]
        if character == "{":
            stack.append(index + 1)
        elif character == "}" and stack:
            stack.pop()
    return stack[-1] if stack else 0


def enclosing_function(spans: tuple[tuple[str, int, int], ...], position: int) -> str:
    for name, start, stop in spans:
        if start <= position < stop:
            return name
    return ""


def split_block(block: str) -> tuple[tuple[str, str, str], ...]:
    """Split a compound statement into ``(kind, head, body)`` items."""

    items: list[tuple[str, str, str]] = []
    buffer: list[str] = []
    paren = 0
    index = 0
    while index < len(block):
        character = block[index]
        if character == "(":
            paren += 1
        elif character == ")":
            paren -= 1
        if paren == 0 and character == ";":
            items.append(("stmt", "".join(buffer).strip(), ""))
            buffer = []
            index += 1
            continue
        if paren == 0 and character == "{":
            close = _matching_brace(block, index, "nested block")
            items.append(("block", "".join(buffer).strip(), block[index + 1 : close]))
            buffer = []
            index = close + 1
            continue
        buffer.append(character)
        index += 1
    trailing = "".join(buffer).strip()
    if trailing:
        items.append(("stmt", trailing, ""))
    return tuple(items)


def statement_effects(
    statement: str,
    roles: dict[str, str],
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> tuple[str, ...]:
    effects: list[str] = []
    resolved = defines if defines is not None else {}
    for _site, role, _is_write in dereference_sites(statement, resolved, roles):
        effects.append("qsize" if role == "QSIZE" else "load:%s" % role)
    already_loaded = {effect.split(":", 1)[1] for effect in effects if effect.startswith("load:")}
    for register in _RAW_REGISTER_RE.findall(statement):
        if register == "QSIZE":
            if "qsize" not in effects:
                effects.append("qsize")
        elif register not in already_loaded:
            effects.append("load:%s" % register)
            already_loaded.add(register)
    if code_contains(statement, "DWT->CYCCNT"):
        effects.append("timestamp")
    if store_re.search(statement):
        effects.append("store")
    for callee in _CALL_RE.findall(statement):
        if callee not in _NON_CALL_KEYWORDS and callee not in roles:
            effects.append("call:%s" % callee)
    return tuple(effects)


def extract_loop(body: str, what: str) -> tuple[str, str, int, int]:
    """Return ``(loop_head, loop_body, body_start, body_stop)`` of the single ``for``."""

    heads = [match for match in re.finditer(r"(?<![A-Za-z0-9_])for\s*\(", body)]
    if len(heads) != 1:
        raise fail("%s: expected exactly one loop, found %d" % (what, len(heads)))
    match = heads[0]
    depth = 0
    index = match.end() - 1
    while index < len(body):
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    head = body[match.end() : index]
    tail = body[index + 1 :]
    stripped = tail.lstrip()
    if not stripped.startswith("{"):
        raise fail("%s: loop body is not a compound statement" % what)
    open_index = index + 1 + (len(tail) - len(stripped))
    close_index = _matching_brace(body, open_index, what)
    return head, body[open_index + 1 : close_index], open_index + 1, close_index


_GUARD_HEAD_RE = re.compile(r"^(?:else\s+if\b|if\b|else\b)")

# The loop head runs on every iteration exactly as the body does. An MMIO load
# in the increment, a mailbox store in the initialiser or a call in the
# condition is a per-iteration effect that happens to be written outside the
# braces, so the head is held to the same rule the body is: the only thing it
# may compute is the register-local induction arithmetic.
_INDUCTION_ALLOWED = frozenset(
    ("uint32_t", "int32_t", "uintptr_t", "unsigned", "int", "V14_ITERATION_BOUND")
)
_INDUCTION_DECL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:uint32_t|int32_t|unsigned|int)\s+([A-Za-z_]\w*)"
)

# A second loop is a second polling site, whatever keyword opens it, and a
# ``goto`` or a label is a back-edge the brace structure does not show. The
# bounded ``for`` this contract proves is only a bound if it is the only way
# round.
_EXTRA_LOOP_RE = re.compile(r"(?<![A-Za-z0-9_])(while|do)(?![A-Za-z0-9_])")
_GOTO_RE = re.compile(r"(?<![A-Za-z0-9_])goto(?![A-Za-z0-9_])")
_CONTINUE_RE = re.compile(r"(?<![A-Za-z0-9_])continue(?![A-Za-z0-9_])")
_LABEL_RE = re.compile(r"^([A-Za-z_]\w*)\s*:(?!:)")
_LABEL_KEYWORDS = frozenset(("case", "default"))


def _split_top_level(text: str, separator: str) -> tuple[str, ...]:
    """Split ``text`` on ``separator`` at paren depth zero."""

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for character in text:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and character == separator:
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(character)
    parts.append("".join(buffer))
    return tuple(parts)


def verify_loop_header(
    head: str,
    roles: dict[str, str],
    what: str,
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> None:
    """Reject a ``for`` head that carries anything but induction arithmetic."""

    clauses = _split_top_level(head, ";")
    if len(clauses) != 3:
        raise fail("%s: loop head is not a three-clause bounded for" % what)
    induction = set(_INDUCTION_DECL_RE.findall(clauses[0]))
    for clause in clauses:
        effects = statement_effects(clause, roles, store_re, defines)
        if effects:
            raise fail(
                "%s head carries a per-iteration effect: (%s) carries %s"
                % (what, re.sub(r"\s+", " ", head.strip())[:60], ", ".join(sorted(set(effects))))
            )
        for identifier in _IDENTIFIER_RE.findall(clause):
            if identifier in induction or identifier in _INDUCTION_ALLOWED:
                continue
            raise fail(
                "%s head observes %s outside the induction variable: (%s)"
                % (what, identifier, re.sub(r"\s+", " ", head.strip())[:60])
            )


def _label_statements(block: str, depth: int = 0) -> tuple[str, ...]:
    """Every statement in ``block``, at any depth, that opens with a label."""

    if depth > _MAX_NESTING_DEPTH:
        raise fail(
            "block nesting is deeper than the %d levels this gate walks" % _MAX_NESTING_DEPTH
        )
    found: list[str] = []
    for kind, headline, nested in split_block(block):
        match = _LABEL_RE.match(headline.strip())
        if match is not None and match.group(1) not in _LABEL_KEYWORDS:
            found.append(match.group(1))
        if kind == "block":
            found.extend(_label_statements(nested, depth + 1))
    return tuple(found)


def verify_single_bounded_loop(body: str, what: str) -> None:
    """Reject any polling construct other than the one bounded ``for``.

    ``extract_loop`` already refuses a second ``for``, braceless or not. This
    adds the constructs brace matching does not see as loops at all: a ``while``
    or ``do`` anywhere in the helper -- before the bounded loop, after it, or
    nested inside it -- and a ``goto``/label pair, which can both re-enter the
    loop and jump *into* the middle of a guard whose exemption was granted on
    the assumption that its condition is the only way in.
    """

    extra = _EXTRA_LOOP_RE.search(body)
    if extra is not None:
        raise fail(
            "%s: an unbounded %s polling loop is reachable beside the bounded for"
            % (what, extra.group(1))
        )
    if _GOTO_RE.search(body) is not None:
        raise fail("%s: a goto back-edge is reachable beside the bounded for" % what)
    labels = _label_statements(body)
    if labels:
        raise fail(
            "%s: label %s makes the loop or a guard body multi-entry" % (what, labels[0])
        )


def verify_no_loop_back_edge(loop_body: str, what: str) -> None:
    """Reject a ``continue`` path back to the loop head.

    ``verify_guard_publication`` already refuses one inside an effect-carrying
    guard, where it is the mechanism that turns a published tuple into a
    per-iteration store. This refuses the rest of them: the canonical loop
    leaves by ``break`` or ``return`` and by nothing else, so a ``continue``
    anywhere in it is a control path the ordered-effect model does not describe.
    """

    if _CONTINUE_RE.search(loop_body) is not None:
        raise fail("%s: a continue statement reaches the loop back-edge" % what)


def flatten_loop(block: str, what: str) -> tuple[tuple[int, str, str, str], ...]:
    """Return every reachable item of a loop body as ``(depth, kind, head, body)``.

    ``depth`` 0 is the loop body itself, so a depth-0 item runs on every
    iteration and a deeper one only on the iteration that takes its branch. The
    walk recurses, so no statement can hide behind an earlier guard, and every
    nested block has to be an ``if``/``else`` guard -- a bare block or a nested
    loop would let a per-iteration effect masquerade as a guard body.
    """

    items: list[tuple[int, str, str, str]] = []

    def walk(text: str, depth: int) -> None:
        if depth > _MAX_NESTING_DEPTH:
            raise fail(
                "%s: guard nesting is deeper than the %d levels this gate walks"
                % (what, _MAX_NESTING_DEPTH)
            )
        for kind, headline, nested in split_block(text):
            if kind == "stmt":
                items.append((depth, "stmt", headline, ""))
                continue
            head = headline.strip()
            if _GUARD_HEAD_RE.match(head) is None:
                raise fail("%s: nested block %r is not an if/else guard" % (what, head[:40] or "{}"))
            items.append((depth, "guard", head, nested))
            walk(nested, depth + 1)

    walk(block, 0)
    return tuple(items)


# A guard body may publish the frozen result tuple and its first-observation
# timestamp. Anything else it carries -- a call above all -- is an effect the
# guard cannot own, whatever its condition turns out to be.
_CANONICAL_GUARD_EFFECTS = frozenset(("store", "timestamp"))
_CARRIED_EFFECT_PREFIXES = ("store", "timestamp", "call:")
_TERMINATOR_RE = re.compile(r"^(?:break|return)(?![A-Za-z0-9_])")
_BACK_EDGE_RE = re.compile(r"(?<![A-Za-z0-9_])(continue|goto)(?![A-Za-z0-9_])")


def subtree_effects(
    body: str,
    roles: dict[str, str],
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
    depth: int = 0,
) -> tuple[str, ...]:
    """Return every effect carried anywhere inside ``body``, at any depth.

    ``split_block`` keeps a braceless ``if`` inside its own statement text, so
    scanning both the statement text and every nested block reaches an effect
    however it is written.
    """

    if depth > _MAX_NESTING_DEPTH:
        raise fail(
            "block nesting is deeper than the %d levels this gate walks" % _MAX_NESTING_DEPTH
        )
    effects: list[str] = []
    for kind, headline, nested in split_block(body):
        effects.extend(statement_effects(headline, roles, store_re, defines))
        if kind == "block":
            effects.extend(subtree_effects(nested, roles, store_re, defines, depth + 1))
    return tuple(effects)


def terminates_iteration(body: str) -> bool:
    """True when control cannot fall off the end of ``body`` into the back-edge.

    The proof is structural: the last statement of the body is a ``break`` or a
    ``return``, so every path that runs to the end of the guard leaves the loop
    rather than starting another iteration.
    """

    items = split_block(body)
    if not items:
        return False
    kind, headline, _ = items[-1]
    return kind == "stmt" and _TERMINATOR_RE.match(headline.strip()) is not None


def verify_guard_publication(
    head: str,
    body: str,
    roles: dict[str, str],
    what: str,
    store_re: re.Pattern[str] = _STORE_RE,
    defines: dict[str, int] | None = None,
) -> None:
    """Reject a loop guard body that carries an effect it cannot own.

    A guard body runs only on the iteration that takes its branch -- but that
    says nothing about *how many* iterations there are. An always-true guard,
    or one whose body simply falls through to the back-edge, runs its body on
    every iteration and so carries a per-iteration store, call or timestamp
    exactly as a depth-0 statement would. The exemption therefore has to be
    earned rather than assumed: the effects the body carries must be the
    canonical result publication and its timestamp, and the iteration must end
    in a ``break`` or a ``return`` before any path can reach the back-edge.
    """

    carried = tuple(
        effect
        for effect in subtree_effects(body, roles, store_re, defines)
        if effect.startswith(_CARRIED_EFFECT_PREFIXES)
    )
    if not carried:
        return
    condition = re.sub(r"\s+", " ", head.strip())[:60]
    foreign = sorted({effect for effect in carried if effect not in _CANONICAL_GUARD_EFFECTS})
    if foreign:
        raise fail(
            "%s guard body carries a non-publication effect: (%s) carries %s"
            % (what, condition, ", ".join(foreign))
        )
    back_edge = _BACK_EDGE_RE.search(body)
    if back_edge is not None:
        raise fail(
            "%s guard body carries a per-iteration effect: (%s) reaches the loop back-edge "
            "through %s" % (what, condition, back_edge.group(1))
        )
    if not terminates_iteration(body):
        raise fail(
            "%s guard body carries a per-iteration effect: (%s) does not end the iteration "
            "with a break or a return" % (what, condition)
        )


# ---------------------------------------------------------------------------
# Predicate structure
#
# Which terms a predicate mentions is not what it decides. ``a && b && c && d``
# and ``a || b || c || d`` mention the same four things and agree on nothing:
# the first exits only on the same-iteration tuple the design requires, the
# second exits on any one of them. A gate that greps for the terms therefore
# proves nothing about the branch, so the connective is parsed here and each
# term is bound to the exact value that drives it -- a mask compared against a
# constant, not merely a mask that appears.
# ---------------------------------------------------------------------------

_STATUS_BOOLEAN_NAMES = {
    STATUS_STATE: "state",
    STATUS_IRQ_RAISED: "irq_raised",
    STATUS_RESET: "reset",
    STATUS_CMD_END: "cmd_end_reached",
    STATUS_FAULT_MASK: "fault",
}
# The four same-iteration facts convergence succeeds on, each with the value its
# comparison must land on. ``q_done`` compares two observations rather than a
# constant, so it carries no value.
CONVERGENCE_PREDICATE = (
    ("q_done", "=="),
    ("cmd_end_reached", "!=", 0),
    ("irq_raised", "!=", 0),
    ("state", "==", 0),
)
# The QS/SQ primary loop exits on *either* first observation. An ``&&`` here
# would make ``Q_FIRST`` and ``S5_FIRST`` unreachable and leave the variant
# matrix measuring one thing three times.
PRIMARY_COMPLETION_PREDICATE = (("q_done", "=="), ("cmd_end_reached", "!=", 0))
_FIRST_OBSERVATION_CATEGORY = {"q_done": "Q_FIRST", "cmd_end_reached": "S5_FIRST"}


def _peel_parens(text: str) -> str:
    """Strip parentheses that wrap the whole expression."""

    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        depth = 0
        for index, character in enumerate(stripped):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    break
        if index != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
    return stripped


def _split_logical(text: str, operator: str) -> tuple[str, ...]:
    """Split ``text`` on ``&&`` or ``||`` at paren depth zero."""

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and text[index : index + 2] == operator:
            parts.append("".join(buffer))
            buffer = []
            index += 2
            continue
        buffer.append(character)
        index += 1
    parts.append("".join(buffer))
    return tuple(parts)


def logical_structure(condition: str) -> tuple[str, tuple[str, ...]]:
    """``(connective, terms)`` at the outermost level of ``condition``.

    ``&&`` binds tighter than ``||``, so a top-level ``||`` is the connective
    even when conjunctions sit under it. A leaf comes back as ``("", (leaf,))``.
    """

    peeled = _peel_parens(condition)
    disjuncts = _split_logical(peeled, "||")
    if len(disjuncts) > 1:
        return "||", disjuncts
    conjuncts = _split_logical(peeled, "&&")
    if len(conjuncts) > 1:
        return "&&", conjuncts
    return "", (peeled,)


def guard_condition(head: str, what: str) -> str:
    """The text inside a guard head's parentheses."""

    open_index = head.find("(")
    if open_index < 0:
        raise fail("%s: guard head carries no condition: %s" % (what, head.strip()[:40]))
    depth = 0
    for index in range(open_index, len(head)):
        if head[index] == "(":
            depth += 1
        elif head[index] == ")":
            depth -= 1
            if depth == 0:
                return head[open_index + 1 : index]
    raise fail("%s: guard head has unbalanced parentheses" % what)


def _split_comparison(text: str) -> tuple[str, str, str] | None:
    depth = 0
    for index, character in enumerate(text):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character in "!=" and text[index + 1 : index + 2] == "=":
            if character == "=" and text[index - 1 : index] in ("=", "!", "<", ">"):
                continue
            return text[:index], text[index : index + 2], text[index + 2 :]
    return None


def classify_predicate_leaf(leaf: str, defines: dict[str, int]) -> tuple[object, ...] | None:
    """The named boolean a leaf computes, bound to the value that drives it.

    ``None`` means the leaf is not one of the same-iteration observations this
    contract knows, which every caller refuses rather than ignores: a term
    nothing here can name is a term no exit rule covers.
    """

    parts = _split_comparison(_peel_parens(leaf))
    if parts is None:
        return None
    left, operator, right = parts
    left_tokens = tuple(_C_TOKEN_RE.findall(_peel_parens(left)))
    if left_tokens == ("qread",):
        if tuple(_C_TOKEN_RE.findall(_peel_parens(right))) != ("qsize_expected",):
            return None
        return ("q_done", operator)
    if len(left_tokens) != 3 or left_tokens[0] != "status" or left_tokens[1] != "&":
        return None
    mask = defines.get(left_tokens[2])
    value = _evaluate_constant(right, defines)
    if mask is None or value is None or mask not in _STATUS_BOOLEAN_NAMES:
        return None
    return (_STATUS_BOOLEAN_NAMES[mask], operator, value)


def verify_predicate_shape(
    condition: str,
    connective: str,
    required: tuple[tuple[object, ...], ...],
    defines: dict[str, int],
    what: str,
) -> tuple[tuple[object, ...], ...]:
    """Prove ``condition`` joins exactly ``required`` with exactly ``connective``."""

    observed_connective, terms = logical_structure(condition)
    if observed_connective != connective:
        raise fail(
            "%s does not join its terms with %s: it uses %s"
            % (
                what,
                connective or "a single term",
                observed_connective or "a single term",
            )
        )
    classified: list[tuple[object, ...]] = []
    for term in terms:
        if logical_structure(term)[0]:
            raise fail("%s carries a nested boolean term: %s" % (what, term.strip()[:40]))
        leaf = classify_predicate_leaf(term, defines)
        if leaf is None:
            raise fail(
                "%s carries a term this gate cannot bind to an observed value: %s"
                % (what, term.strip()[:40])
            )
        classified.append(leaf)
    if sorted(classified, key=repr) != sorted(required, key=repr):
        raise fail(
            "%s is not the frozen tuple of observations: it decides on %s"
            % (what, sorted(classified, key=repr))
        )
    return tuple(classified)


def _duplicate_roles(read_order: list[str]) -> list[str]:
    return sorted({role for role in read_order if read_order.count(role) > 1})


def _guard_kind(condition: str) -> str:
    if names_identifier(condition, "V14_STATUS_RESET"):
        return "reset"
    if names_identifier(condition, "V14_STATUS_FAULT_MASK"):
        return "fault"
    if names_identifier(condition, "qsize_expected"):
        return "completion"
    return "other"


# A depth-0 guard that publishes decides *when* the frame is written, so its
# condition is part of the contract exactly as the completion predicate is. Each
# recognised kind therefore carries the connective and the bound tuple its
# condition has to be, and a publishing guard of no recognised kind is refused:
# an exit on ``i > 5U`` fabricates an observation the source never made.
_RESET_PREDICATE = (("reset", "!=", 0),)
_FAULT_PREDICATE = (("fault", "!=", 0),)


def _publishing_guards(
    items: tuple[tuple[int, str, str, str], ...],
    roles: dict[str, str],
    store_re: re.Pattern[str],
    defines: dict[str, int],
) -> tuple[tuple[str, str], ...]:
    """Every depth-0 guard of a loop whose subtree stores anything."""

    return tuple(
        (head, body)
        for depth, kind, head, body in items
        if depth == 0
        and kind == "guard"
        and "store" in subtree_effects(body, roles, store_re, defines)
    )


def verify_publishing_guards(
    guards: tuple[tuple[str, str], ...],
    required: dict[str, tuple[str, str, tuple[tuple[object, ...], ...]]],
    defines: dict[str, int],
    what: str,
    kinds: tuple[str, ...] | None = None,
) -> None:
    """Prove every publishing guard is a known kind joined exactly as its kind is.

    ``guards[kinds.index("completion")]`` checks one guard. It says nothing
    about the guard beside it, and a loop may carry as many as it likes: an
    extra ``if (i > 5U)`` that publishes the frozen success tuple exits on an
    iteration count, and a reset guard rewritten as
    ``((status & RESET) != 0U) || (i > 5U)`` keeps its classification while
    deciding on something else entirely. Both publish evidence about a
    measurement the source does not make, so every publishing guard earns its
    exit here rather than the first one of each name.
    """

    seen: list[str] = []
    for index, (head, _body) in enumerate(guards):
        condition = head.strip()
        if _GUARD_HEAD_RE.match(condition) is None or "(" not in condition:
            raise fail(
                "%s publishes from a guard with no condition this gate can bind: %s"
                % (what, condition[:40] or "else")
            )
        kind = kinds[index] if kinds is not None else _guard_kind(guard_condition(head, what))
        if kind not in required:
            raise fail(
                "%s publishes from a guard whose condition is not a contract predicate: %s"
                % (what, re.sub(r"\s+", " ", condition)[:60])
            )
        label, connective, terms = required[kind]
        verify_predicate_shape(guard_condition(head, what), connective, terms, defines, label)
        seen.append(kind)
    missing = sorted(set(required) - set(seen))
    if missing:
        raise fail("%s has no %s predicate" % (what, missing[0]))
    duplicated = sorted({kind for kind in seen if seen.count(kind) > 1})
    if duplicated:
        raise fail(
            "%s publishes from more than one %s guard: %d"
            % (what, duplicated[0], seen.count(duplicated[0]))
        )


def _q_timeout_classification(
    after_loop: str, roles: dict[str, str], defines: dict[str, int]
) -> list[str]:
    """Prove the one post-timeout STATUS load classifies reset and every fault bit.

    Q's loop never reads STATUS, so the timeout tail's single diagnostic load is
    the only evidence there is about *why* the queue never drained. It has to
    separate reset from a hardware fault, and it has to test the whole pinned
    0x314 mask rather than a subset, or a fault bit silently reports as a plain
    timeout.
    """

    status_pointers = [name for name, role in roles.items() if role == "STATUS"]
    if not status_pointers:
        raise fail("Q timeout diagnostic STATUS read is missing or duplicated: 0 named loads")
    targets = re.findall(
        r"([A-Za-z_]\w*)\s*=\s*\*\s*(?:%s)(?![A-Za-z0-9_])"
        % "|".join(re.escape(name) for name in status_pointers),
        after_loop,
    )
    if len(targets) != 1:
        raise fail(
            "Q timeout diagnostic STATUS read is missing or duplicated: %d named loads" % len(targets)
        )

    guards = _guard_blocks(after_loop, targets[0])
    # One guard that tests both the reset bit and the fault mask cannot report
    # which of the two it found, so it is a contract rejection with a name --
    # not an ordering question, and never a traceback out of ``index``.
    if any(
        names_identifier(condition, "V14_STATUS_RESET")
        and names_identifier(condition, "V14_STATUS_FAULT_MASK")
        for condition, _body in guards
    ):
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "one guard tests both the reset bit and the fault mask"
        )
    reset = [
        c
        for c, b in guards
        if names_identifier(c, "V14_STATUS_RESET") and names_identifier(b, "V14_PRIMARY_RESET")
    ]
    fault = [
        c
        for c, b in guards
        if names_identifier(c, "V14_STATUS_FAULT_MASK") and names_identifier(b, "V14_PRIMARY_FAULT")
    ]
    if len(reset) != 1:
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: %d guards"
            % len(reset)
        )
    if len(fault) != 1:
        raise fail(
            "Q timeout diagnostic does not classify every 0x%03X fault bit from the diagnostic "
            "STATUS load: %d guards test the pinned mask" % (defines["V14_STATUS_FAULT_MASK"], len(fault))
        )
    kinds = [_guard_kind(condition) for condition, _ in guards]
    if "reset" not in kinds or "fault" not in kinds:
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "the reset and fault tests are not two separate guards"
        )
    if kinds.index("reset") > kinds.index("fault"):
        raise fail(
            "Q timeout diagnostic does not classify reset from the diagnostic STATUS load: "
            "the fault test comes first"
        )
    return ["reset:0x%03X" % defines["V14_STATUS_RESET"]] + [
        "fault:0x%03X" % bit
        for bit in (1 << shift for shift in range(32))
        if defines["V14_STATUS_FAULT_MASK"] & bit
    ]


def verify_primary_contract(
    vendor_masked: str, variant: str, defines: dict[str, int]
) -> dict[str, object]:
    """Prove the per-variant primary observation loop."""

    if defines.get("V14_ITERATION_BOUND") != ITERATION_BOUND:
        raise fail("primary loop bound is not 10000: V14_ITERATION_BOUND is %r" % defines.get("V14_ITERATION_BOUND"))

    defined = []
    for name in PRIMARY_SYMBOL.values():
        try:
            extract_function_body(vendor_masked, name, name)
        except GateError:
            continue
        defined.append(name)
    wanted = PRIMARY_SYMBOL[variant]
    if wanted not in defined:
        raise fail("primary helper %s is missing" % wanted)
    for name in defined:
        if name != wanted:
            raise fail("inactive primary helper is reachable: %s" % name)

    body = function_text(vendor_masked, wanted, "primary helper")
    roles = pointer_roles(body, defines)
    require_resolved_pointers(roles, "primary helper")
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in a primary loop: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "primary loop")
    if not names_identifier(head, "V14_ITERATION_BOUND"):
        raise fail("primary loop bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "primary helper")
    verify_loop_header(head, roles, "primary loop", store_re, defines)
    # After the loop-shape rules, so each keeps its own rejection: what is left
    # for this to name is an address written where it stands, which the ordered
    # effect sequence below would otherwise carry as an unnamed load.
    require_resolved_dereferences(body, defines, roles, "the primary helper")
    require_no_macro_mmio(body, mmio_macro_names(vendor_masked), "the primary helper")

    items = flatten_loop(loop_body, "primary loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    expected = ["QREAD"] if variant == "Q" else EXPECTED_PRIMARY_ORDER[variant]
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re, defines)
        if depth:
            # A guard body that has earned its exemption publishes the frozen
            # success tuple, so a store or a timestamp here is that tuple rather
            # than a per-iteration effect. A reload is still forbidden: it would
            # unfreeze the tuple.
            for effect in effects:
                if effect == "qsize":
                    raise fail("QSIZE access reachable in a primary loop")
                if effect.startswith("load:"):
                    raise fail("primary success tuple is re-read rather than frozen")
            continue
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in a primary loop")
        if any(effect in ("timestamp", "store") or effect.startswith("call:") for effect in effects):
            raise fail(
                "primary loop carries a per-iteration store/call/timestamp: %s" % head.strip()[:50]
            )
        for effect in effects:
            if effect.startswith("load:"):
                role = effect.split(":", 1)[1]
                read_order.append(role)
                if branched:
                    loads_after_branch.append(role)
        if kind == "guard":
            guard_bodies.append((head, guard_body))
            branched = True

    # The exemption the depth check above grants is only sound for a guard that
    # provably ends its iteration. Prove it rather than assume it -- after the
    # per-statement rules above, so each keeps its own rejection.
    for head, guard_body in guard_bodies:
        verify_guard_publication(head, guard_body, roles, "primary loop", store_re, defines)
    verify_no_loop_back_edge(loop_body, "primary loop")

    if variant == "Q" and "STATUS" in read_order:
        raise fail("Q primary loop reads STATUS")
    duplicates = _duplicate_roles(read_order)
    if duplicates:
        raise fail(
            "primary loop reloads %s: the exit predicate must come from one load per register"
            % ", ".join(duplicates)
        )
    # A read that exists in the loop but only downstream of a branch is a
    # short-circuit exit, not a missing read: the two cases need different names
    # because they need different fixes.
    if loads_after_branch and read_order == expected:
        raise fail("primary predicate is evaluated before both reads")
    if read_order != expected:
        raise fail(
            "%s primary read order is not %s: observed %s"
            % (variant, " then ".join(expected), read_order or ["nothing"])
        )

    # ``else if`` is a depth-0 guard exactly as ``if`` is, and a filter that
    # only knows the one spelling leaves the other unclassified -- which is to
    # say unchecked, by every ordering and predicate rule below.
    guards = [
        (_guard_kind(head), head)
        for depth, kind, head, _ in items
        if depth == 0 and kind == "guard" and _GUARD_HEAD_RE.match(head) and "(" in head
    ]

    kinds = [kind for kind, _ in guards]
    if "completion" not in kinds:
        raise fail("primary loop has no completion predicate")
    if variant == "Q":
        # The substring ``STATUS`` also names ``V14_STATUS_*`` and
        # ``NPU_REG_STATUS``; it does not name the local ``status`` that holds a
        # STATUS load, which is the one spelling the rule most needs to see.
        if any(
            names_identifier(condition, "status")
            or re.search(r"(?<![A-Za-z0-9_])(?:V14_STATUS_|NPU_REG_STATUS)", condition)
            for _, condition in guards
        ):
            raise fail("Q primary loop reads STATUS")
    else:
        for required in ("reset", "fault"):
            if required not in kinds:
                raise fail(
                    "reset/fault check does not dominate the primary completion predicate: %s guard is missing"
                    % required
                )
            if kinds.index(required) > kinds.index("completion"):
                raise fail(
                    "reset/fault check does not dominate the primary completion predicate: %s guard follows it"
                    % required
                )
        completion = guards[kinds.index("completion")][1]
        if not names_identifier(completion, "V14_STATUS_CMD_END"):
            raise fail("primary completion predicate does not use cmd_end_reached bit5")
        if names_identifier(completion, "V14_STATUS_IRQ_RAISED"):
            raise fail("irq_raised bit1 is used as a primary exit predicate")

    # Which terms the exit tests is not what it decides. ``q_done && s_done``
    # names the same two observations as ``q_done || s_done`` and can only ever
    # report SAME_ITERATION, so the connective is proven rather than assumed --
    # and the categories the manifest publishes are read off that proof.
    completion_condition = guard_condition(guards[kinds.index("completion")][1], "primary loop")
    if variant == "Q":
        completion_terms = verify_predicate_shape(
            completion_condition, "", (("q_done", "=="),), defines,
            "the Q primary completion predicate",
        )
    else:
        completion_terms = verify_predicate_shape(
            completion_condition, "||", PRIMARY_COMPLETION_PREDICATE, defines,
            "the primary completion predicate",
        )
    # Every guard that publishes earns its exit, not just the first one named
    # ``completion``. Without this an extra guard -- before the real one, after
    # it, or spelled ``else if`` -- writes the frozen OBSERVED tuple on an
    # arbitrary condition, and a reset guard rewritten as
    # ``((status & RESET) != 0U) || (i > 5U)`` keeps its classification while
    # deciding on an iteration count. The manifest would then report
    # first-observation evidence about a measurement the source never made.
    if variant == "Q":
        required_guards = {
            "completion": ("the Q primary completion predicate", "", (("q_done", "=="),)),
        }
    else:
        required_guards = {
            "reset": ("the primary reset predicate", "", _RESET_PREDICATE),
            "fault": ("the primary fault predicate", "", _FAULT_PREDICATE),
            "completion": (
                "the primary completion predicate",
                "||",
                PRIMARY_COMPLETION_PREDICATE,
            ),
        }
    publishing = _publishing_guards(items, roles, store_re, defines)
    verify_publishing_guards(publishing, required_guards, defines, "primary loop")
    observed_publishers = [
        head
        for head, guard_body in publishing
        if names_identifier(guard_body, "V14_PRIMARY_OBSERVED")
    ]
    if len(observed_publishers) != 1 or _guard_kind(
        guard_condition(observed_publishers[0], "primary loop")
    ) != "completion":
        raise fail(
            "V14_PRIMARY_OBSERVED is published from a guard that is not the completion "
            "predicate: %d publishing guards write it" % len(observed_publishers)
        )

    categories: list[str] = []
    if len(completion_terms) > 1:
        categories = sorted(_FIRST_OBSERVATION_CATEGORY[name] for name, *_rest in completion_terms)
        categories.append("SAME_ITERATION")

    # Everything before the loop and everything after it is outside authoritative
    # timing; only Q may touch STATUS there, and only once.
    after_loop = body[loop_stop:]
    outside = body[:loop_start] + after_loop
    diagnostic_loads = len(
        re.findall(
            r"\*\s*(?:%s)(?![A-Za-z0-9_])"
            % "|".join(re.escape(name) for name, role in roles.items() if role == "STATUS"),
            outside,
        )
    )
    classification: list[str] = []
    if variant == "Q":
        if diagnostic_loads != 1:
            raise fail(
                "Q timeout diagnostic STATUS read is missing or duplicated: %d loads" % diagnostic_loads
            )
        classification = _q_timeout_classification(after_loop, roles, defines)
    elif diagnostic_loads != 0:
        raise fail("%s primary helper reads STATUS outside its loop: %d loads" % (variant, diagnostic_loads))

    if code_contains(after_loop, "DWT->CYCCNT"):
        raise fail("%s timeout path publishes a first-observation timestamp" % variant)
    if names_identifier(body, CONVERGE_SYMBOL):
        raise fail("%s timeout path reaches the convergence tail" % variant)

    fault_bits = [bit for bit in (1 << shift for shift in range(32)) if defines["V14_STATUS_FAULT_MASK"] & bit]
    return {
        "primary_helper": wanted,
        "primary_read_order": expected,
        "primary_bound": ITERATION_BOUND,
        "valid_iteration_range": [1, ITERATION_BOUND],
        "fault_bits_gated": fault_bits,
        "reset_bit_gated": defines["V14_STATUS_RESET"],
        "q_timeout_classification": classification,
        "q_timeout_diagnostic_status_loads": diagnostic_loads,
        "first_observation_categories": categories,
        "primary_completion_predicate_connective": logical_structure(completion_condition)[0],
        "primary_completion_predicate_terms": [list(term) for term in completion_terms],
    }


EXPECTED_PRIMARY_ORDER = {"Q": ["QREAD"], "QS": ["QREAD", "STATUS"], "SQ": ["STATUS", "QREAD"]}

STOCK_VECTOR_SYMBOL = "u85_irq_handler"

# The Cortex-M NVIC interrupt set-enable array. Eight words, one bit per IRQ:
# any store into it is an enable, whatever name the base is reached through.
NVIC_ISER_BASE = 0xE000E100
NVIC_ISER_BYTES = 8 * 4

# The two spellings that *clear* the flag. Anything else assigned to it is a
# value it can hold on a measured path.
_IRQ_TRIGGERED_CLEARED = frozenset(("false", "0", "0U", "0u"))
HARD_BYPASS_PROBE_ORDER = (
    "NVIC_DisableIRQ",
    "NVIC_ClearPendingIRQ",
    "NVIC_GetVector",
    "NVIC_GetEnableIRQ",
    "NVIC_GetPendingIRQ",
    "NVIC_GetActive",
)


def verify_hard_bypass_contract(vendor_masked: str) -> dict[str, object]:
    """Prove the retained V12/V13 stock vector and NVIC hard bypass."""

    install = "NVIC_SetVector(NPU0_IRQn, (uint32_t)&%s)" % STOCK_VECTOR_SYMBOL
    install_sites = code_positions(vendor_masked, install)
    if len(install_sites) != 1:
        raise fail("runtime vector is not the exact stock u85_irq_handler")

    spans = function_spans(vendor_masked)
    setup_start, setup_stop = function_span(
        vendor_masked, enclosing_function(spans, install_sites[0]), "runtime setup function"
    )
    setup = vendor_masked[setup_start:setup_stop]
    observed = []
    for probe in HARD_BYPASS_PROBE_ORDER:
        site = code_find(setup, probe + "(")
        if site >= 0:
            observed.append((site, probe))
    ordering = [probe for _, probe in sorted(observed)]
    if ordering != list(HARD_BYPASS_PROBE_ORDER):
        raise fail("NVIC hard-bypass probe ordering drifted: observed %s" % ordering)

    enable_sites = code_positions(vendor_masked, "NVIC_EnableIRQ(") + code_positions(
        vendor_masked, "__NVIC_EnableIRQ("
    )
    if enable_sites:
        raise fail("reachable NVIC_EnableIRQ")
    # ``NVIC->ISER[0] = 1UL`` and ``((NVIC_Type *)0xE000E100UL)->ISER[0] = 1UL``
    # enable the same interrupt; only the spelling of the base differs. The NPU
    # registers get full address provenance, so the NVIC gets the same
    # treatment: the register name is refused as a token, and so is the address
    # written as a number.
    if names_identifier(vendor_masked, "ISER"):
        raise fail("direct NVIC ISER enable write is reachable")
    for match in re.finditer(r"(?<![A-Za-z0-9_.])(0[xX][0-9A-Fa-f]+|\d+)[uUlL]*", vendor_masked):
        try:
            literal = int(match.group(1), 0)
        except ValueError:  # pragma: no cover - the pattern only matches literals
            continue
        if NVIC_ISER_BASE <= literal < NVIC_ISER_BASE + NVIC_ISER_BYTES:
            raise fail("direct NVIC ISER enable write is reachable")
    # A literal scan only refuses the address written as *one* number.
    # ``V14_NVIC_LO + 0x100U`` reaches the same register and contains no literal
    # in the window, so every access expression in the file is folded against it
    # here. This runs file-wide on purpose: ``require_resolved_dereferences``
    # covers four functions, and a helper called from ``test_commands`` is
    # neither of them -- which is exactly where the computed address went.
    defines = parse_defines(vendor_masked)
    for site, expression, _is_write in access_expressions(vendor_masked):
        if _POINTER_CAST_RE.search(expression) is None:
            continue
        value = _evaluate_constant(_flatten_address(expression), defines)
        if value is None:
            continue
        if NVIC_ISER_BASE <= (value & 0xFFFFFFFF) < NVIC_ISER_BASE + NVIC_ISER_BYTES:
            raise fail(
                "direct NVIC ISER enable write is reachable: computed address at offset %d" % site
            )

    # ``irq_triggered = 1`` sets the same flag ``irq_triggered = true`` does. The
    # rule is about the value the flag can take on a measured path, so it is the
    # assigned value that decides, not the spelling of the constant -- and a
    # compound assignment sets it without ever writing a plain one.
    stepped = compound_assignment_targets(vendor_masked, ("irq_triggered",))
    if stepped:
        raise fail("irq_triggered can become true on a measured path: sites ['<compound assignment>']")
    # ``*trig_alias = true`` sets the flag without ever spelling its name on the
    # left of an ``=``, so the site walk below never sees it and the manifest
    # keeps publishing the handler as the only writer. The values this file
    # gates already refuse address-taking through ``require_load_provenance``;
    # the flag gets the same treatment. The stock handler assigns it directly
    # and needs no pointer to it, so refusing every ``&irq_triggered`` costs the
    # contract nothing and closes the alias for good.
    for match in re.finditer(r"&\s*(?:\(\s*)*irq_triggered(?![A-Za-z0-9_])", vendor_masked):
        # ``mask & irq_triggered`` reads the flag; only address-of aliases it.
        previous = _token_before(vendor_masked, match.start())[1]
        cursor = match.start() - 1
        while cursor >= 0 and vendor_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if previous or (cursor >= 0 and vendor_masked[cursor] in _OPERAND_END_CHARACTERS):
            continue
        raise fail(
            "irq_triggered can become true on a measured path: sites ['<address taken at offset %d>']"
            % match.start()
        )
    sites = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])irq_triggered\s*=(?!=)([^;]*);", vendor_masked):
        if match.group(1).strip() in _IRQ_TRIGGERED_CLEARED:
            continue
        sites.append(enclosing_function(spans, match.start()))
    if sorted(set(sites)) != [STOCK_VECTOR_SYMBOL]:
        raise fail("irq_triggered can become true on a measured path: sites %s" % sorted(set(sites)))
    if not re.search(
        r"(?<![A-Za-z0-9_])irq_triggered\s*=(?!=)\s*(?:false|0[uU]?)\s*;", setup
    ):
        raise fail("NVIC hard-bypass probe ordering drifted: irq_triggered is not cleared before the probes")

    return {
        "installed_vector_symbol": STOCK_VECTOR_SYMBOL,
        "hard_bypass_probe_order": list(HARD_BYPASS_PROBE_ORDER),
        "irq_triggered_publication_sites": sorted(set(sites)),
        "reachable_nvic_enable_sites": len(enable_sites),
    }


# ---------------------------------------------------------------------------
# Common convergence tail
# ---------------------------------------------------------------------------

_PREDICATE_TERMS = (
    "qread == qsize_expected",
    "status & V14_STATUS_CMD_END",
    "status & V14_STATUS_IRQ_RAISED",
    "status & V14_STATUS_STATE",
)
_PREDICATE_IDENTIFIERS = frozenset(("qread", "status", "qsize_expected"))


def verify_convergence_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the one shared bounded convergence tail."""

    try:
        body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    except GateError:
        raise fail("common convergence helper %s is missing" % CONVERGE_SYMBOL)

    roles = pointer_roles(body, defines)
    require_resolved_pointers(roles, "convergence helper")
    store_re = store_pattern(body)
    if "QSIZE" in roles.values():
        raise fail("QSIZE access reachable in the convergence tail: a QSIZE pointer is bound")

    head, loop_body, loop_start, loop_stop = extract_loop(body, "convergence loop")
    if not names_identifier(head, "V14_ITERATION_BOUND"):
        raise fail("convergence bound is not 10000: loop head does not use V14_ITERATION_BOUND")
    verify_single_bounded_loop(body, "convergence helper")
    verify_loop_header(head, roles, "convergence loop", store_re, defines)
    require_resolved_dereferences(body, defines, roles, "the convergence helper")
    require_no_macro_mmio(body, mmio_macro_names(vendor_masked), "the convergence helper")

    items = flatten_loop(loop_body, "convergence loop")
    read_order: list[str] = []
    loads_after_branch: list[str] = []
    guard_bodies: list[tuple[str, str]] = []
    branched = False
    for depth, kind, head, guard_body in items:
        effects = statement_effects(head, roles, store_re, defines)
        for effect in effects:
            if effect == "qsize":
                raise fail("QSIZE access reachable in the convergence tail")
            if effect == "store":
                raise fail("convergence evidence store occurs inside the loop")
        if depth:
            for effect in effects:
                if effect.startswith("load:"):
                    raise fail("convergence predicate is satisfied by a reread rather than the loop tuple")
            continue
        for effect in effects:
            if effect == "timestamp" or effect.startswith("call:"):
                raise fail(
                    "convergence loop carries a per-iteration store/call/timestamp: %s"
                    % head.strip()[:50]
                )
            if effect.startswith("load:"):
                role = effect.split(":", 1)[1]
                read_order.append(role)
                if branched:
                    loads_after_branch.append(role)
        if kind == "guard":
            guard_bodies.append((head, guard_body))
            branched = True

    # Same proof obligation as the primary loop: a guard only escapes the
    # per-iteration rule if it provably ends the iteration.
    for head, guard_body in guard_bodies:
        verify_guard_publication(head, guard_body, roles, "convergence loop", store_re, defines)
    verify_no_loop_back_edge(loop_body, "convergence loop")

    duplicates = _duplicate_roles(read_order)
    if duplicates:
        raise fail(
            "convergence loop reloads %s: the same-iteration tuple must come from one load per register"
            % ", ".join(duplicates)
        )
    if loads_after_branch and read_order == ["QREAD", "STATUS"]:
        raise fail("convergence predicate is evaluated before both reads")
    if read_order != ["QREAD", "STATUS"]:
        raise fail("convergence read order is not QREAD then STATUS: observed %s" % (read_order or ["nothing"]))

    guards = [
        ("success" if names_identifier(body, "V14_CONVERGENCE_SUCCESS") else _guard_kind(head), head, body)
        for depth, kind, head, body in items
        if depth == 0 and kind == "guard" and _GUARD_HEAD_RE.match(head) and "(" in head
    ]

    kinds = [role for role, _, _ in guards]
    if "success" not in kinds:
        raise fail("convergence loop has no success predicate")
    success_index = kinds.index("success")
    for required in ("reset", "fault"):
        if required not in kinds:
            raise fail("convergence fault/reset check is delayed: %s guard is missing" % required)
        if kinds.index(required) > success_index:
            raise fail("convergence fault/reset check is delayed: %s guard follows the success predicate" % required)

    predicate = guards[success_index][1]
    for identifier in _IDENTIFIER_RE.findall(predicate):
        if identifier in _PREDICATE_IDENTIFIERS or identifier.startswith("V14_") or identifier == "if":
            continue
        raise fail(
            "convergence predicate accumulates across iterations: %s is not part of the same-iteration tuple"
            % identifier
        )
    flattened = re.sub(r"\s+", " ", predicate)
    for term in _PREDICATE_TERMS:
        if term not in flattened:
            raise fail("convergence predicate omits a required term: %s" % term)

    # Naming the four terms is not deciding on them. Written with ``||`` the
    # same four succeed on ``(status & STATE) == 0`` alone -- with the queue
    # undrained, bit5 clear and bit1 clear -- which is the one thing "one
    # same-iteration tuple" was meant to rule out. So the connective is parsed,
    # and each term is bound to the value its comparison lands on.
    predicate_condition = guard_condition(predicate, "convergence loop")
    predicate_terms = verify_predicate_shape(
        predicate_condition,
        "&&",
        CONVERGENCE_PREDICATE,
        defines,
        "the convergence success predicate",
    )

    # Every depth-0 guard of the tail decides an outcome, so each one is held to
    # the predicate its kind is. Without this a second guard that also sets
    # ``V14_CONVERGENCE_SUCCESS`` is classified ``success``, sorts behind the
    # real one, and is never predicate-checked at all -- so it can succeed on
    # anything at all while the manifest publishes the real predicate.
    verify_publishing_guards(
        tuple((head, guard_body) for _kind, head, guard_body in guards),
        {
            "reset": ("the convergence reset predicate", "", _RESET_PREDICATE),
            "fault": ("the convergence fault predicate", "", _FAULT_PREDICATE),
            "success": ("the convergence success predicate", "&&", CONVERGENCE_PREDICATE),
        },
        defines,
        "convergence loop",
        tuple(kind for kind, _head, _guard_body in guards),
    )

    if store_re.search(body[:loop_start]):
        raise fail("convergence evidence store occurs before the loop")

    return {
        "convergence_helper": CONVERGE_SYMBOL,
        "convergence_read_order": ["QREAD", "STATUS"],
        "convergence_bound": ITERATION_BOUND,
        "convergence_predicate_terms": list(_PREDICATE_TERMS),
        "convergence_predicate_connective": logical_structure(predicate_condition)[0],
        "convergence_predicate_bindings": [list(term) for term in predicate_terms],
    }


# ---------------------------------------------------------------------------
# Failure mailbox and success cleanup
# ---------------------------------------------------------------------------

_MAILBOX_DECL_RE = re.compile(r"volatile\s+uint32_t\s+%s\s*\[\s*(\d+)\s*\]" % re.escape(MAILBOX_SYMBOL))
_MAILBOX_STORE_RE = re.compile(r"%s\s*\[\s*([A-Za-z0-9_]+)\s*\]\s*=\s*([^;]+);" % re.escape(MAILBOX_SYMBOL))
_FROZEN_INDEX_RE = re.compile(
    r"^\s*%s\s*\[\s*([A-Za-z0-9_]+)\s*\]\s*$" % re.escape(MAILBOX_SYMBOL)
)

_CONVERGENCE_TUPLE = ("convergence_final_qread", "convergence_final_status")
_FAILURE_TUPLE = ("failure_qread", "failure_status")
_FIRST_TUPLE_FIELDS = (
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
)


def _mbox_macro(field: str) -> str:
    return "V14_MBOX_" + field.upper()


def _word(field: str) -> int:
    return APPENDIX_FIELDS.index(field)


def _mailbox_words_stored(
    block: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[object, str], ...]:
    """``(word, value)`` for every mailbox store in ``block``, in source order."""

    return tuple((word, value) for word, _token, value, _start in mailbox_stores(block, defines, known))


def _publication_words(
    block: str, defines: dict[str, int], known: dict[str, object], what: str
) -> dict[object, str]:
    """The one value each appendix word receives in a publication helper.

    A helper that writes the same word twice is refused rather than reduced to
    whichever store the reader happens to look at: a second store is exactly how
    a tuple the first store invalidated comes back as evidence.
    """

    resolved: dict[object, str] = {}
    for word, _token, value, _start in mailbox_stores(block, defines, known):
        if word == UNRESOLVED_ROLE:
            raise fail("%s stores into the mailbox at an offset this gate cannot resolve" % what)
        if word in resolved:
            raise fail("%s publishes appendix word %s from more than one store" % (what, word))
        resolved[word] = value
    return resolved


def mailbox_stores(
    block: str, defines: dict[str, int], known: dict[str, object] | None = None
) -> tuple[tuple[object, str, str, int], ...]:
    """``(word, index_token, value, start)`` for every store into the mailbox.

    The lvalue is resolved rather than pattern-matched, so the subscript, the
    reversed subscript C also accepts, a dereference of pointer arithmetic and
    an alias of the array all arrive at the same word. ``index_token`` is the
    text between the brackets when -- and only when -- the store is written in
    the frozen ``symbol[macro]`` spelling, so the *spelling* stays judged
    separately from the *word* the callers below need.
    """

    resolved = mailbox_alias_words(block, defines) if known is None else known
    stores: list[tuple[object, str, str, int]] = []
    for start, lvalue, rvalue in assignment_statements(block):
        if _is_declaration(lvalue):
            continue
        word = resolve_mailbox_word(lvalue, defines, resolved)
        if word is None:
            continue
        frozen = _FROZEN_INDEX_RE.match(lvalue)
        index_token = frozen.group(1) if frozen else re.sub(r"\s+", " ", lvalue.strip())
        stores.append((word, index_token, rvalue.strip(), start))
    return tuple(stores)


def require_mailbox_provenance(text: str, defines: dict[str, int], what: str) -> dict[str, object]:
    """Resolve the mailbox aliases of ``text``, refusing the ones nothing can pin.

    A name whose displacement from the array is unknown, and a name the source
    re-points with ``+=`` or ``++``, are both names no word rule covers. They
    are refused here rather than resolved to whichever word they happened to
    start at.

    A read-modify-write on an addressed *word* is refused for a different
    reason. Every publication rule in this file is written over the one value a
    word receives, so ``mailbox[V14_MBOX_VARIANT_ID] += 2U`` after the frozen
    variant-id store leaves the gate reporting the store it proved and the
    image publishing a different number -- exactly the mis-attributed frame
    ``verify_variant_identity`` exists to prevent, and the same for the magic
    that declares the other 33 words real. The mailbox is write-once per word,
    so an operator that also reads it back is refused whatever spelling reaches
    the word.
    """

    aliases = mailbox_alias_words(text, defines)
    unresolved = sorted(name for name, word in aliases.items() if word == UNRESOLVED_ROLE)
    if unresolved:
        raise fail(
            "%s binds a mailbox alias this gate cannot resolve to one appendix word: %s"
            % (what, ", ".join(unresolved))
        )
    stepped = compound_assignment_targets(text, (MAILBOX_SYMBOL,) + tuple(sorted(aliases)))
    if stepped:
        raise fail(
            "%s re-points mailbox storage through a compound assignment or an increment: %s"
            % (what, ", ".join(stepped))
        )
    for start, lvalue in compound_assignment_lvalues(text):
        if resolve_mailbox_word(lvalue, defines, aliases) is None:
            continue
        raise fail(
            "%s mutates a published mailbox word through a read-modify-write at offset %d: %s"
            % (what, start, re.sub(r"\s+", " ", lvalue.strip())[:40])
        )
    return aliases


def require_no_record_read_modify_write(masked: str, what: str) -> None:
    """Refuse a read-modify-write on an observation record, in any function.

    The record is what the primary loop freezes and the publication helpers
    copy into the appendix, so a ``obs->result |= 1U`` between the freeze and
    the copy rewrites a published field without ever appearing as a second
    store. Each function resolves its own aliases, because ``obs`` is a
    parameter and a second name for it is local to the body that binds it.
    """

    for name, start, stop in function_spans(masked):
        body = masked[start:stop]
        names = ("obs",) + obs_aliases(body)
        for offset, lvalue in compound_assignment_lvalues(body):
            if not any(names_identifier(lvalue, alias) for alias in names):
                continue
            raise fail(
                "%s mutates a frozen observation field through a read-modify-write in %s: %s"
                % (what, name or "<file scope>", re.sub(r"\s+", " ", lvalue.strip())[:40])
            )


def is_magic_value(value: str, defines: dict[str, int]) -> bool:
    """Whether a stored value is the 0x5631344D magic, macro or literal."""

    token = value.strip()
    if token in defines:
        return defines[token] == MAILBOX_VALID
    try:
        return int(token.rstrip("uU"), 0) == MAILBOX_VALID
    except ValueError:
        return False


def _resolved_mailbox_stores(
    vendor_masked: str, defines: dict[str, int], known: dict[str, object] | None = None
) -> tuple[tuple[object, str, str, str], ...]:
    """``(word, index_token, value, owner)`` for every mailbox store, aliases included."""

    spans = function_spans(vendor_masked)
    return tuple(
        (word, index_token, value, enclosing_function(spans, start))
        for word, index_token, value, start in mailbox_stores(vendor_masked, defines, known)
    )


def verify_variant_identity(
    vendor_masked: str, defines: dict[str, int], variant: str
) -> dict[str, object]:
    """Bind ``V14_VARIANT_ID`` to the selected variant and to appendix word 0.

    Word 0 is the only thing a decoder has to tell a Q frame from an SQ one, so
    a frame that publishes the wrong id, no id, or an id that never reaches
    word 0 is a frame whose every other field is attributed to the wrong
    experiment. The publication is required in the frozen spelling: an alias
    store is not refused because it would fail, but because nothing here can
    prove it is the same array.
    """

    expected = VARIANTS[variant]
    if defines.get("V14_VARIANT_ID") != expected:
        raise fail(
            "variant id define is not the selected variant: V14_VARIANT_ID is %s, expected %d"
            % (
                "undefined" if "V14_VARIANT_ID" not in defines else str(defines["V14_VARIANT_ID"]),
                expected,
            )
        )

    aliases = require_mailbox_provenance(vendor_masked, defines, "the vendor translation unit")
    stores = _resolved_mailbox_stores(vendor_masked, defines, aliases)
    word_zero = [store for store in stores if store[0] == 0]
    misplaced = [store for store in stores if store[0] != 0 and store[2] == "V14_VARIANT_ID"]
    if len(word_zero) != 1:
        raise fail(
            "variant id is not published to mailbox word 0: %d stores address word 0"
            % len(word_zero)
        )
    word, index_token, value, _owner = word_zero[0]
    if value != "V14_VARIANT_ID":
        raise fail("mailbox word 0 does not publish V14_VARIANT_ID: it stores %s" % value)
    if misplaced:
        raise fail(
            "variant id is published to appendix word %s rather than word 0" % (misplaced[0][0],)
        )

    direct = re.search(
        r"(?<![A-Za-z0-9_])%s\s*\[\s*%s\s*\]\s*=\s*V14_VARIANT_ID\s*;"
        % (re.escape(MAILBOX_SYMBOL), re.escape(_mbox_macro("variant_id"))),
        vendor_masked,
    )
    if direct is None:
        raise fail(
            "variant id is published through a mailbox alias or a raw index rather than "
            "%s[%s]" % (MAILBOX_SYMBOL, _mbox_macro("variant_id"))
        )
    return {
        "variant_id_word": 0,
        "variant_id_publication": "%s[%s] = V14_VARIANT_ID"
        % (MAILBOX_SYMBOL, _mbox_macro("variant_id")),
        "variant_id_define": defines["V14_VARIANT_ID"],
    }


def verify_mailbox_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the exact 34-word mailbox, its reset, and its magic-last publication."""

    declarations = _MAILBOX_DECL_RE.findall(vendor_masked)
    if declarations != [str(APPENDIX_WORDS)]:
        raise fail("mailbox storage is not a 34-word array: found %s" % (declarations or ["no declaration"]))

    for index, field in enumerate(APPENDIX_FIELDS):
        macro = _mbox_macro(field)
        if defines.get(macro) != index:
            raise fail(
                "appendix offset table does not match the schema-14 wire order: %s is %r, expected %d"
                % (macro, defines.get(macro), index)
            )
    if defines.get("V14_APPENDIX_WORDS") != APPENDIX_WORDS:
        raise fail("appendix offset table does not match the schema-14 wire order: V14_APPENDIX_WORDS drifted")
    if defines.get("V14_MAILBOX_VALID") != MAILBOX_VALID:
        raise fail("mailbox magic is not 0x5631344D")
    if defines.get("V14_U32_INVALID") != U32_INVALID:
        raise fail("invalid sentinel is not 0xFFFFFFFF")

    aliases = require_mailbox_provenance(vendor_masked, defines, "the vendor translation unit")
    require_no_record_read_modify_write(vendor_masked, "the vendor translation unit")

    valid_word = APPENDIX_FIELDS.index("mailbox_valid")
    reset = function_text(vendor_masked, MAILBOX_RESET_SYMBOL, "mailbox reset entry")
    if not names_identifier(reset, "V14_U32_INVALID") or not names_identifier(
        reset, "V14_APPENDIX_WORDS"
    ):
        raise fail("mailbox reset does not invalidate every appendix field")
    reset_stores = _mailbox_words_stored(reset, defines, aliases)
    if (valid_word, "0U") not in reset_stores:
        raise fail("mailbox reset does not zero mailbox_valid")
    if reset_stores[-1] != (valid_word, "0U"):
        raise fail("mailbox reset does not zero mailbox_valid last")
    if not code_contains(reset, "__DSB()"):
        raise fail("mailbox reset does not issue a DSB")

    publish = function_text(vendor_masked, MAILBOX_PUBLISH_SYMBOL, "mailbox publication entry")
    publish_stores = mailbox_stores(publish, defines, aliases)
    if len(publish_stores) != 1 or publish_stores[0][0] != valid_word or not is_magic_value(
        publish_stores[0][2], defines
    ):
        raise fail(
            "mailbox magic is not the final appendix store: publication stores %s"
            % ([(store[0], store[2]) for store in publish_stores],)
        )
    if not code_contains(publish[publish_stores[0][3] :], "__DSB()"):
        raise fail("mailbox publication does not issue a DSB")

    # The magic is what tells a reader the other 33 words are real, so it is
    # counted by *value* over every spelling a store can take: the frozen macro
    # or the bare 0x5631344D, the frozen symbol or an alias of it, the offset
    # macro or its numeric 33. Counting the macro text alone leaves three ways
    # to publish a second, earlier, unearned magic.
    resolved_stores = _resolved_mailbox_stores(vendor_masked, defines, aliases)
    magic_stores = [store for store in resolved_stores if is_magic_value(store[2], defines)]
    if len(magic_stores) != 1:
        raise fail(
            "mailbox_valid is published from more than one site: %d stores" % len(magic_stores)
        )
    word, index_token, value, owner = magic_stores[0]
    if word != valid_word:
        raise fail("mailbox magic is not stored at appendix word 33: it lands on word %s" % word)
    if owner != MAILBOX_PUBLISH_SYMBOL:
        raise fail(
            "mailbox magic is published outside %s: stored in %s"
            % (MAILBOX_PUBLISH_SYMBOL, owner or "<file scope>")
        )
    if (index_token, value) != (_mbox_macro("mailbox_valid"), "V14_MAILBOX_VALID"):
        raise fail(
            "mailbox magic is published through an alias or a raw index rather than "
            "%s[%s] = V14_MAILBOX_VALID" % (MAILBOX_SYMBOL, _mbox_macro("mailbox_valid"))
        )

    failure = function_text(vendor_masked, "v14_publish_failure", "failure publication")
    failure_stores = _publication_words(failure, defines, aliases, "the failure publication")
    for field in _CONVERGENCE_TUPLE:
        if failure_stores.get(_word(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a failure" % field)
    for field in _FIRST_TUPLE_FIELDS:
        if _word(field) in failure_stores:
            raise fail("convergence failure discards the retained first-observation tuple: %s" % field)

    success = function_text(vendor_masked, "v14_publish_success", "success publication")
    success_stores = _publication_words(success, defines, aliases, "the success publication")
    for field in _FAILURE_TUPLE:
        if success_stores.get(_word(field)) != "V14_U32_INVALID":
            raise fail("success and failure tuples are both published as valid: %s survives a success" % field)
    if success_stores.get(_word("failure_phase")) != "V14_PHASE_NONE":
        raise fail("success and failure tuples are both published as valid: failure_phase is not NONE")

    cleanup = function_text(vendor_masked, "v14_publish_cleanup_failure", "cleanup publication")
    cleanup_stores = _publication_words(cleanup, defines, aliases, "the cleanup publication")
    if cleanup_stores.get(_word("failure_phase")) != "V14_PHASE_CLEANUP":
        raise fail("cleanup invariant is not recorded as failure_phase=CLEANUP")
    for field in _CONVERGENCE_TUPLE:
        if _word(field) in cleanup_stores:
            raise fail("cleanup invariant discards the convergence tuple: %s" % field)

    first_words = {_word(field) for field in _FIRST_TUPLE_FIELDS}
    for word, index_token, _value, owner in resolved_stores:
        if word not in first_words:
            continue
        if owner != "v14_publish_primary":
            raise fail(
                "first-observation STATUS fields are synthesized from convergence values: %s stored in %s"
                % (index_token, owner or "<file scope>")
            )

    return {
        "mailbox_symbol": MAILBOX_SYMBOL,
        "mailbox_words": APPENDIX_WORDS,
        "mailbox_reset_entry": MAILBOX_RESET_SYMBOL,
        "mailbox_magic_store_index": APPENDIX_FIELDS.index("mailbox_valid"),
        "mailbox_magic": "0x%08X" % MAILBOX_VALID,
        "failure_publication_invalidates": list(_CONVERGENCE_TUPLE),
        "success_publication_invalidates": list(_FAILURE_TUPLE),
        "cleanup_publication_retains": list(_CONVERGENCE_TUPLE),
    }


def require_every_appendix_word_produced(vendor_masked: str, defines: dict[str, int]) -> int:
    """Refuse a frame whose appendix carries a word nothing ever stores.

    A word no store reaches carries the reset sentinel into the published frame,
    and every other rule in this file is written over the stores that *do*
    exist -- so deleting a publication, commenting it out, or splicing a comment
    over it leaves this gate with nothing to object to and a decoder with
    0xFFFFFFFF where the contract promised an observation. Fail-silent is still
    a false manifest: the appendix table is published as the frame's contents,
    so every word in it has to have a producer.

    This runs after every other contract, so a source that breaks a *specific*
    rule is still named by that rule. Reaching here means the store is simply
    absent, which no other rule is written to see. The reset is excluded because
    it writes the sentinel rather than an observation.
    """

    aliases = mailbox_alias_words(vendor_masked, defines)
    produced = {
        word
        for word, _token, _value, owner in _resolved_mailbox_stores(vendor_masked, defines, aliases)
        if owner != MAILBOX_RESET_SYMBOL and isinstance(word, int)
    }
    missing = [index for index in range(APPENDIX_WORDS) if index not in produced]
    if missing:
        raise fail(
            "appendix word %d (%s) has no store outside the mailbox reset: it can only carry the "
            "invalid sentinel" % (missing[0], APPENDIX_FIELDS[missing[0]])
        )
    return len(produced)


SUCCESS_CLEANUP_ORDER = (
    "CMD2",
    "QREAD",
    "CMD2",
    "QREAD_VERIFY",
    "NVIC",
    "CMD0",
    "H-PRINTF",
    "CMD0xC",
)

# Every CMD write in the release window is named by the value it lands, so a
# write this table does not know still appears in the observed ordering rather
# than passing through it unseen.
_CLEANUP_CMD_TOKENS = {0x2: "CMD2", 0x0: "CMD0", 0xC: "CMD0xC"}


def _cmd_value_text(value: int | None) -> str:
    return "opaque" if value is None else "0x%08X" % value


def _hprintf_seam_site(cleanup: str, cleanup_raw: str, cmd0: int, terminal: int) -> int:
    """Return the offset of the one qualified H-PRINTF callsite in the window.

    ``mask_c_lexical`` preserves byte offsets, so the marker can be located in
    the raw text and compared against callsites found in the masked text. The
    marker is what makes this the qualified seam: a bare vendor printf in the
    release window is a debug print, not the ``__wrap_printf`` callsite the
    frozen V12 gate qualified.
    """

    marker_spans = [
        (match.start(), match.end())
        for match in code_pattern(HPRINTF_SEAM_MARKER).finditer(cleanup_raw)
        if cmd0 < match.start() < terminal
    ]
    markers = [start for start, _stop in marker_spans]
    callsites = [site for site in code_positions(cleanup, "printf(") if cmd0 < site < terminal]
    if len(markers) != 1:
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: %d seam markers in the release window"
            % (HPRINTF_SEAM_MARKER_NAME, len(markers))
        )
    if len(callsites) != 1:
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: %d printf callsites in the release window"
            % (HPRINTF_SEAM_MARKER_NAME, len(callsites))
        )
    between = cleanup_raw[marker_spans[0][1] : callsites[0]]
    if markers[0] > callsites[0] or between.strip():
        raise fail(
            "cleanup H-PRINTF seam is not the qualified %s callsite: the seam marker does not anchor it"
            % HPRINTF_SEAM_MARKER_NAME
        )
    return callsites[0]


_TEST_CPM_IF_RE = re.compile(r"#[ \t]*if[ \t]*\(?[ \t]*TEST_CPM[ \t]*==[ \t]*1[ \t]*\)?")
_TEST_CPM_ENDIF_RE = re.compile(r"(?m)^[ \t]*#[ \t]*endif")


def _test_cpm_region(cleanup: str) -> tuple[int, int]:
    """The ``#if(TEST_CPM==1)`` span the terminal cleanup writes live in.

    The seam and the terminal ``CMD=0xC`` are inside a preprocessor branch, and
    this gate reads source rather than a translation unit. What it can prove is
    that the branch is the ``TEST_CPM==1`` one and that ``TEST_CPM`` is defined
    to 1 in the same source; what it cannot prove is that the build actually
    compiled it, which is why the manifest publishes that as a limitation
    rather than implying the writes are unconditionally reachable.
    """

    opens = [match.end() for match in _TEST_CPM_IF_RE.finditer(cleanup)]
    if len(opens) != 1:
        raise fail(
            "cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): %d guards"
            % len(opens)
        )
    close = _TEST_CPM_ENDIF_RE.search(cleanup, opens[0])
    if close is None:
        raise fail("cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): no #endif")
    return opens[0], close.start()


def verify_cleanup_contract(
    vendor_masked: str, vendor_text: str, variant: str, defines: dict[str, int]
) -> dict[str, object]:
    """Prove failure isolation, history provenance and the stock success tail."""

    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    command_raw = vendor_text[command_start:command_stop]

    command_roles = pointer_roles(command, defines)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, mmio_macro_names(vendor_masked), "the command function")

    primary_call = code_find(command, PRIMARY_SYMBOL[variant] + "(")
    if primary_call < 0:
        raise fail("command path does not call the variant primary helper")
    tail = command[primary_call + len(PRIMARY_SYMBOL[variant]) :]
    if re.search(r"(?<![A-Za-z0-9_])v14_primary_", tail) is not None:
        raise fail("variant-specific block between the primary freeze and the common cleanup")

    command_cmd_writes = tuple(site for site, _value in cmd_write_values(command, defines, command_roles))
    command_prints = code_positions(command, "printf(")
    failure_clears: list[int] = []
    failure_prints: list[int] = []
    for site in code_positions(command, "v14_publish_failure("):
        window_end = code_find(command[site:], "return")
        if window_end < 0:
            raise fail("failure path does not return after publication")
        window_stop = site + window_end
        # The failure path is the branch that decided the failure, not the two
        # statements that report it. A CMD clear written immediately *before*
        # the publication clears the NPU exactly as one written after it does,
        # and a window that opens at the publication call never looks there --
        # so the window opens where the branch does.
        window_start = enclosing_block_start(command, site)
        failure_clears.extend(
            offset for offset in command_cmd_writes if window_start <= offset < window_stop
        )
        failure_prints.extend(
            offset for offset in command_prints if window_start <= offset < window_stop
        )
    if failure_clears:
        raise fail("failure path clears NPU state before serialization")
    if failure_prints:
        raise fail("failure path enters the H-PRINTF seam")

    history = re.search(r"irq_history_mask\s*=\s*([^;]+);", command)
    if history is None or not code_contains(history.group(1), "converged.status"):
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")
    converge_call = code_find(command, CONVERGE_SYMBOL + "(")
    if converge_call < 0:
        raise fail("command path does not call the common convergence helper")
    if any(
        site >= converge_call
        for site in register_access_sites(command, "STATUS", defines, command_roles)
    ):
        raise fail("irq_history_mask is derived from a post-convergence STATUS reread")

    cleanup = command[history.start() :]
    cleanup_raw = command_raw[history.start() :]
    cleanup_roles = pointer_roles(cleanup, defines)
    # The cleanup tail is judged by what each CMD write *does*, so a second
    # ISR-equivalent written as ``2`` rather than ``0x00000002`` is the same
    # marker and lands in the same ordering.
    cleanup_cmd_writes = cmd_write_values(cleanup, defines, cleanup_roles)
    markers: list[tuple[int, str]] = []
    for site, value in cleanup_cmd_writes:
        markers.append((site, _CLEANUP_CMD_TOKENS.get(value, "CMD=%s" % _cmd_value_text(value))))
    for site in register_access_sites(cleanup, "QREAD", defines, cleanup_roles):
        markers.append((site, "QREAD"))
    for site in code_positions(cleanup, "read_val == u32CmdQueueSize"):
        markers.append((site, "QREAD_VERIFY"))
    for site in code_positions(cleanup, "NVIC_ClearPendingIRQ("):
        markers.append((site, "NVIC"))
    cmd0 = tuple(site for site, value in cleanup_cmd_writes if value == 0x0)
    terminal = tuple(site for site, value in cleanup_cmd_writes if value == 0xC)
    seam_site = -1
    if cmd0 and terminal:
        seam_site = _hprintf_seam_site(cleanup, cleanup_raw, cmd0[0], terminal[0])
        markers.append((seam_site, "H-PRINTF"))
    observed = tuple(token for _, token in sorted(markers))
    if observed != SUCCESS_CLEANUP_ORDER:
        raise fail("success cleanup ordering drifted: observed %s" % (list(observed),))

    region_start, region_stop = _test_cpm_region(cleanup_raw)
    if not region_start < seam_site < terminal[0] < region_stop:
        raise fail(
            "cleanup terminal sequence is not guarded by one #if(TEST_CPM==1): the seam and the "
            "terminal CMD=0xC are not both inside it"
        )
    if defines.get("TEST_CPM") != 1:
        raise fail(
            "cleanup terminal sequence is compiled out: TEST_CPM is %s, not 1"
            % ("undefined" if "TEST_CPM" not in defines else defines["TEST_CPM"])
        )

    return {
        "success_cleanup_order": list(observed),
        "failure_paths_clear_npu": bool(failure_clears),
        "failure_paths_enter_hprintf": bool(failure_prints),
        "hprintf_seam_marker": HPRINTF_SEAM_MARKER_NAME,
        "hprintf_seam_wrap_symbol": HPRINTF_WRAP_SYMBOL,
        "hprintf_callsite_elf_qualified": False,
        "cleanup_terminal_conditional_on": "TEST_CPM==1",
        "cleanup_terminal_branch_compiled_proof": False,
    }


# ---------------------------------------------------------------------------
# Runner wire contract
# ---------------------------------------------------------------------------

_RECORD_FIELD_RE = re.compile(r"uint32_t\s+([A-Za-z_]\w*)\s*;")
_SERIALIZE_RE = re.compile(r"put32\s*\(\s*&c\s*,\s*d\s*->\s*([A-Za-z_]\w*)\s*\)")
_RECORD_TARGET_RE = re.compile(r"^\s*d\s*\.\s*([A-Za-z_]\w*)\s*$")


def runner_appendix_copies(
    runner_masked: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[int, str, object], ...]:
    """``(start, field, word)`` for every ``d.<field> = <a mailbox word>`` copy.

    The right-hand side is resolved to the storage it reads rather than matched
    as ``symbol[``, so a copy spelled with pointer arithmetic, a reversed
    subscript or an alias is seen exactly where a subscript one is -- which is
    what makes "the 34 are copied only inside the magic branch" a proof rather
    than a claim about one spelling.

    The resolved *word* is carried out with the field, because the transport is
    a mapping and not a count. Thirty-four copies that all read word 0, or read
    the appendix backwards, are thirty-four copies -- and every field but one
    then carries a value the vendor never published there.
    """

    return tuple(
        (start, field, word)
        for start, field, word in runner_record_stores(runner_masked, defines, known)
        if word is not None
    )


def runner_record_stores(
    runner_masked: str, defines: dict[str, int], known: dict[str, object]
) -> tuple[tuple[int, str, object], ...]:
    """``(start, field, word)`` for every ``d.<field> = ...``; ``word`` may be ``None``.

    ``runner_appendix_copies`` keeps only the stores that *read* the mailbox,
    which is what proves the transport. It is not what bounds it: a store whose
    rvalue is a constant, another record field, or anything else this gate does
    not resolve to a word is invisible to a rvalue-keyed walk, so
    ``d.variant_id = 3U`` after the proven copy rewrites a published field and
    the frame still serializes under a manifest that says the 34 words came from
    the mailbox. Every store to the record is recovered here so the caller can
    hold the appendix fields closed between the copy and ``put32``.
    """

    found: list[tuple[int, str, object]] = []
    for start, lvalue, rvalue in assignment_statements(runner_masked):
        if _is_declaration(lvalue):
            continue
        target = _RECORD_TARGET_RE.match(lvalue)
        if target is None:
            continue
        found.append((start, target.group(1), resolve_mailbox_word(rvalue, defines, known)))
    return tuple(found)


MEASURED_CALL = "run_fixed_inference()"


def _contiguous_appendix_run(names: list[str]) -> bool:
    """True when the 34 appendix names form one ordered, non-repeating run.

    The runner keeps its frozen v8 fields around the appendix, so the contract
    is that the appendix words sit together in wire order -- not that they are
    the only fields present.
    """

    if any(names.count(field) != 1 for field in APPENDIX_FIELDS):
        return False
    start = names.index(APPENDIX_FIELDS[0])
    return tuple(names[start : start + APPENDIX_WORDS]) == APPENDIX_FIELDS


def verify_runner_contract(runner_masked: str) -> dict[str, object]:
    """Prove the runner declares schema 14 and copies the mailbox fail-closed."""

    # The runner keeps the frozen v7/v8 branches alongside the V14 one, so a
    # name carries several values here; membership, not the last value, is the
    # question.
    declared = parse_define_values(runner_masked)
    defines = {name: seen[-1] for name, seen in declared.items()}
    if SCHEMA_VERSION not in declared.get("PMU_DIAG_SCHEMA_VERSION", ()):
        raise fail("runner does not declare schema 14")
    if declared.get("PMU_COMPLETION_VISIBILITY_DIAG_V14_BUILD_ID") != [BUILD_ID]:
        raise fail("runner does not declare build id 0x34314950")
    for assertion, reason in (
        ("PMU_DIAG_FIELD_COUNT == %dU" % BODY_WORDS, "runner does not statically assert 119 body words"),
        ("PMU_DIAG_TOTAL_WORDS == %dU" % TOTAL_WORDS, "runner does not statically assert 127 frame words"),
        ("PMU_DIAG_PAYLOAD_SIZE == %dU" % PAYLOAD_BYTES, "runner does not statically assert 508 payload bytes"),
        ("PMU_DIAG_SCHEMA_VERSION == %dU" % SCHEMA_VERSION, "runner does not declare schema 14"),
    ):
        if not code_contains(runner_masked, assertion):
            raise fail(reason)

    record_end = code_find(runner_masked, "} pmu_diag_record_t;")
    record_start = runner_masked.rfind("typedef struct", 0, record_end) if record_end >= 0 else -1
    if record_start < 0:
        raise fail("runner record does not carry the 34 appendix fields in wire order: no record found")
    if not _contiguous_appendix_run(_RECORD_FIELD_RE.findall(runner_masked[record_start:record_end])):
        raise fail("runner record does not carry the 34 appendix fields in wire order")

    if not _contiguous_appendix_run(_SERIALIZE_RE.findall(runner_masked)):
        raise fail("runner serialization order does not match the appendix table")

    reset_site = code_find(runner_masked, MAILBOX_RESET_SYMBOL + "();")
    driver_site = code_find(runner_masked[reset_site:], MEASURED_CALL) if reset_site >= 0 else -1
    if reset_site < 0 or driver_site < 0:
        raise fail("runner does not reset the mailbox before the measured call")

    magic_guard = re.search(
        r"if\s*\(\s*%s\s*\[\s*%d\s*\]\s*!=\s*V14_MAILBOX_VALID\s*\)"
        % (re.escape(MAILBOX_SYMBOL), APPENDIX_FIELDS.index("mailbox_valid")),
        runner_masked,
    )
    if magic_guard is None:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    tail_after_guard = code_find(runner_masked[magic_guard.end() :], "else")
    else_site = -1 if tail_after_guard < 0 else magic_guard.end() + tail_after_guard
    if else_site < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    open_index = runner_masked.find("{", else_site)
    if open_index < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    close_index = _matching_brace(runner_masked, open_index, "runner magic else branch")
    aliases = require_mailbox_provenance(runner_masked, defines, "the runner translation unit")
    record_stores = runner_record_stores(runner_masked, defines, aliases)
    all_copies = tuple(
        (start, field, word) for start, field, word in record_stores if word is not None
    )
    inside = tuple(
        (field, word) for start, field, word in all_copies if open_index <= start < close_index
    )
    copies = tuple(field for field, _word in inside)
    if copies != APPENDIX_FIELDS:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")

    # A count is not a mapping. Thirty-four copies in field order still serialize
    # the wrong frame if every one of them reads word 0, if they read the
    # appendix backwards, or if one reads a word outside the array -- and a word
    # whose index this gate cannot evaluate is a word nothing here can check at
    # all. Each field is therefore bound to the appendix word the wire order
    # gives it, which is the transport half of the same proof the vendor side
    # already carries.
    for index, (field, word) in enumerate(inside):
        if word == UNRESOLVED_ROLE:
            raise fail(
                "runner copies %s from a mailbox offset this gate cannot resolve to one "
                "appendix word" % field
            )
        if not isinstance(word, int) or not 0 <= word < APPENDIX_WORDS:
            raise fail(
                "runner copies %s from outside the 34-word appendix: word %s" % (field, word)
            )
        if word != index:
            raise fail(
                "runner appendix copy does not read the word its field is published in: "
                "%s reads word %s, expected word %d" % (field, word, index)
            )

    # Dominance is not "the valid branch copies all 34"; it is "the 34 are
    # copied *only* there". A copy before the guard runs whatever the magic
    # says, and a copy in the invalid branch publishes reset sentinels -- or
    # stale words from a previous run -- as if they were evidence.
    stray = [
        (start, field)
        for start, field, _word in all_copies
        if not open_index <= start < close_index
    ]
    if stray:
        raise fail(
            "runner copies the appendix outside the mailbox-magic branch: %s copied at %d"
            % (stray[0][1], stray[0][0])
        )

    # Proving where the 34 words come *from* does not prove what is serialized.
    # Between the copy and ``put32`` the record is ordinary memory, and
    # ``d.variant_id = 3U``, ``d.first_qread |= 0x80000000U`` or a two-field swap
    # each rewrite a published field without ever reading the mailbox -- so the
    # rvalue-keyed walk above never sees them and the frame goes out with the
    # manifest still asserting ``runner_appendix_source_words == range(34)``.
    # The appendix half of the record is therefore write-once: exactly the 34
    # proven copies, and nothing after them.
    appendix_fields = frozenset(APPENDIX_FIELDS)
    outside = [
        (start, field)
        for start, field, _word in record_stores
        if field in appendix_fields and not open_index <= start < close_index
    ]
    if outside:
        raise fail(
            "runner rewrites a copied appendix field outside the mailbox-magic branch: "
            "%s assigned at %d" % (outside[0][1], outside[0][0])
        )
    # An increment writes the field without ever spelling ``d.<field> =``, and
    # it can be written prefix or postfix, so the lvalue is read for the names
    # it mentions rather than matched against one shape.
    for offset, lvalue in compound_assignment_lvalues(runner_masked):
        if not names_identifier(lvalue, "d"):
            continue
        touched = [field for field in APPENDIX_FIELDS if names_identifier(lvalue, field)]
        if touched:
            raise fail(
                "runner rewrites a copied appendix field through a read-modify-write: "
                "%s at offset %d" % (touched[0], offset)
            )

    return {
        "runner_serialized_words": TOTAL_WORDS,
        "runner_payload_bytes": PAYLOAD_BYTES,
        # The verifier's own observation: every appendix copy it found sits
        # inside the magic ``else`` branch, and none sits outside it.
        "runner_copy_dominated_by_magic": len(copies) == len(all_copies) and not stray,
        "runner_appendix_copies": len(copies),
        # The mailbox word each copy was resolved to, in the order the copies
        # appear. It is the verifier's own reading of the transport, not a
        # restatement of the wire order it was checked against.
        "runner_appendix_source_words": [word for _field, word in inside],
    }


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

    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError as exc:
        raise fail("fixture manifest is not writable at %r (%s)" % (path, exc))


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


def verify_generated_sources(runner_text: str, vendor_text: str, variant: str) -> dict[str, object]:
    """Verify a generated Q/QS/SQ source pair and return its fixture manifest."""

    if variant not in VARIANTS:
        raise fail("unknown variant %r" % variant)
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    vendor_masked = mask_c_lexical(vendor_text)
    runner_masked = mask_c_lexical(runner_text)
    # Every rule below reads a macro's value once. That is only sound while the
    # macro holds one value for the whole translation unit, so the preprocessing
    # history is settled before anything is derived from it.
    require_stable_contract_defines(vendor_masked, "the vendor translation unit")
    require_stable_contract_defines(runner_masked, "the runner translation unit")
    defines = parse_defines(vendor_masked)

    pre_run = verify_pre_run_contract(vendor_masked, defines)
    primary = verify_primary_contract(vendor_masked, variant, defines)
    hard_bypass = verify_hard_bypass_contract(vendor_masked)
    convergence = verify_convergence_contract(vendor_masked, defines)
    mailbox = verify_mailbox_contract(vendor_masked, defines)
    identity = verify_variant_identity(vendor_masked, defines, variant)
    cleanup = verify_cleanup_contract(vendor_masked, vendor_text, variant, defines)
    runner = verify_runner_contract(runner_masked)
    # Last, so a source that breaks a named rule is reported by that rule rather
    # than by the absence its breakage happens to leave behind.
    produced_words = require_every_appendix_word_produced(vendor_masked, defines)
    converge_body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    tail_start = code_find(command, "v14_publish_primary(")
    if tail_start < 0:
        raise fail("common tail does not start at the shared primary publication")

    doc: dict[str, object] = {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "qualification": "UNIT-QUALIFIED",
        "proof_scope": "generated_source_and_fixture_only",
        "real_elf_qualified": False,
        # The frozen u85.c is not tracked in this repository. The vendor half of
        # this contract therefore runs against a stock fixture, and saying so is
        # part of the verdict rather than a footnote to it.
        "vendor_raw_source_verified": False,
        "residual_limitations": list(RESIDUAL_LIMITATIONS),
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
        "common_convergence_source_sha256": normalized_digest(converge_body),
        "common_tail_source_sha256": normalized_digest(command[tail_start:]),
        # The verifier's own count of appendix words it found a producer for.
        # It equals the appendix width or the verdict was a refusal.
        "appendix_words_with_a_producer": produced_words,
    }
    for section in (pre_run, primary, hard_bypass, convergence, mailbox, identity, cleanup, runner):
        doc.update(section)
    return doc


if __name__ == "__main__":
    sys.exit(main())
