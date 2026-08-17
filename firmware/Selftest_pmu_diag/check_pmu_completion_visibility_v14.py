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
never expanded: a macro whose replacement list reaches a register is an MMIO
access this gate cannot pin, so it is refused in every contract-critical
function rather than counted as an ordinary call, and one whose replacement
list carries a store is refused outright -- ``blank_directives`` removes the
definition and the invocation site names no storage at all, so such a body is a
store no rule in this file can see.

A directive is also a *logical* line, and both halves of that are load-bearing.
The mask keeps every byte at its original offset, which every ordering and
dominance rule below compares against; the directive patterns run over a view
that joins the splices instead, so ``#``-backslash-newline-``undef`` is the
``#undef`` the compiler reads rather than two lines neither pattern matches.
Directive whitespace is all six characters C spells it with, a form feed
included, and not the four a hand-written class remembers.

An address is likewise the storage it designates and not the declarator that
bound it. ``name = expr`` is one way to bind a pointer and
``T *const regs[1] = { expr }`` is another, so both are resolved by the same
walk -- an initializer element the walk cannot see leaves every dereference of
that name resolving to "not an address at all", which is the one answer that
makes an access invisible rather than refused. The walk reads file scope with
the function body for the same reason: a register pointer a function inherits is
a register pointer it uses. The runner's record is closed the same way, by the
field its lvalue designates rather than by the ``d.<field>`` spelling, so
``(&d)->``, an alias, an array of aliases and a macro body all arrive at the
same word; a write to an appendix field this gate cannot bind to that record is
refused rather than passed over.

Storage that is published is written once, and it is written where the design
writes it. A read-modify-write on an appendix word or an observation field --
``+=``, ``|=``, ``++``, through an alias, a reversed subscript or pointer
arithmetic -- rewrites a value after the store this gate proved, so the image
publishes one number and the manifest reports another. Every such operator is
resolved to the storage it names and refused. A second *plain* store is the same
defect reached from the other end, and it defeats more: every provenance,
predicate and publishing-guard proof this file makes about a word is bypassed by
one unconditional assignment to that word downstream of the proof. So each
appendix word's producers are held to the sites and the counts the design gives
it, which is also what makes deleting one of three stores of a word -- the one
that carries the measurement -- a rejection rather than a word that still has
two sentinel producers left. And the magic that declares the other 33 words real
is counted by the value the compiler folds, not by the text that produces it:
``V14_MAILBOX_VALID + 0U`` publishes it exactly as the bare macro does.
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

Each such key is also named for the scope it is taken over, which is a thing an
earlier revision of this file got wrong and is worth stating plainly.
``running_qsize_loads_in_test_commands`` compares load offsets inside
``test_commands``; it was once called ``running_qsize_loads`` and published as
though it were a statement about the running path, which it is not -- a QSIZE
read moved into ``v14_publish_primary`` is on the running path by construction
and that comparison cannot see it. The whole-unit claim is two keys and three
scans, because one register access has more than one spelling and a scan that
knows only one of them is a scan the others walk around.
``vendor_register_designations_confined`` counts the register *names*
``require_register_confinement`` walked; ``vendor_register_accesses_confined``
counts the accesses ``require_whole_unit_mmio_confinement`` resolved over every
function span and file scope, where an address written as a numeric offset or an
absolute constant is named by the same resolver the contract-critical functions
use, and one it cannot name is refused rather than counted as nothing; and
``require_no_macro_mmio`` refuses, whole-unit, a macro whose replacement list
carries either. Together they are what makes ``register_confinement_scope:
vendor_translation_unit`` a statement about the translation unit rather than
about the tokens ``NPU_REG_*`` in it. Neither key says anything about a callee in
another translation unit or about the built image; that is C2-1's, and it is
disclosed below rather than implied away here.

Two proofs are made about every published word, and they are not the same proof.
``require_authorized_appendix_producers`` answers *which function wrote this word
and how many times*; ``require_appendix_value_provenance`` answers *what
expression it wrote*. The second was missing, and its absence let 28 of the 34
words carry an attacker-chosen constant with every site and count rule
satisfied -- ``mailbox[V14_MBOX_PRIMARY_RESULT] = V14_PRIMARY_OBSERVED`` being
the sharpest, since it republishes a timed-out run as an observed one. Words
20..23 are the failure publisher's parameters, so their value proof ends at the
call site and ``require_publication_call_provenance`` is where it continues.

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
# Claims this gate deliberately does not make, because they are control-flow
# properties and this module reads characters. Each is bound on the linked image
# instead. They are named here, published in the manifest, and asserted by the
# unit suite, so that relocating a proof cannot be mistaken for having made it:
# a claim that leaves this list without arriving in the ELF contract is a gap
# somebody has to have decided to accept.
DEFERRED_TO_LINKED_IMAGE = (
    "pre_program_gate_dominates_queue_programming: the stopped-state gate must dominate every "
    "QBASE/QSIZE write. Text order is not dominance -- the frozen vendor's eU85_TEST0 branch "
    "writes QBASE_LSB earlier in the file than the design's programming and never on the "
    "measured path, and the gate itself sits in the caller",
    "no_state_transition_between_gate_and_programming: the part of that window which crosses "
    "the call from the gate frame into the programming frame",
    "mailbox_magic_published_once: the runner reads the appendix only when the magic word is "
    "present, so a second store of it -- on a path that never filled the tuple -- would hand "
    "the host a record nothing wrote",
)

# Stated once, retired, and left here rather than deleted.
#
# ``return_code_not_overwritten_after_the_deciding_branch`` was carried as a
# deferred claim until the image was read. It cannot be proven because it is not
# true and was never meant to be: the frozen vendor rewrites ret_code after the
# command function returns -- ``= 2`` on an output-verify mismatch, ``= 3`` on an
# IRQ-mask mismatch, ``++`` when the IRQ never fired -- and V14 does not edit the
# vendor. It is also not the verdict channel. The runner copies the diagnostic
# record only behind the mailbox magic and uses the vendor return code for one
# telemetry flag, so what needed proving was the magic, and that is the claim
# above. Retiring a claim by replacing it is recorded; retiring one by deleting
# it is how a gap becomes invisible.
RETIRED_CLAIMS = (
    "return_code_not_overwritten_after_the_deciding_branch: retired -- the vendor owns that "
    "variable and rewrites it by design, and the V14 verdict travels in the mailbox instead. "
    "Replaced by mailbox_magic_published_once.",
)

# Of the above, the ones the linked-image contract now actually proves. The two
# registries mean different things and both are needed: the first says the
# source gate does not make the claim, the second says somebody else does. A
# claim in the first and not the second is owed to nobody yet, which is what
# `unbound_claims` in the manifest reports.
BOUND_ON_LINKED_IMAGE = (
    "pre_program_gate_dominates_queue_programming",
    "no_state_transition_between_gate_and_programming",
    "mailbox_magic_published_once",
)


def unbound_claims() -> tuple[str, ...]:
    return tuple(
        claim
        for claim in DEFERRED_TO_LINKED_IMAGE
        if not claim.startswith(tuple(name + ":" for name in BOUND_ON_LINKED_IMAGE))
    )


RESIDUAL_LIMITATIONS = DEFERRED_TO_LINKED_IMAGE + RETIRED_CLAIMS + (
    "vendor_raw_source_pin_not_checked_here: the frozen u85.c is tracked at "
    "firmware/Drivers/u85_driver/u85.c and pinned by the build's frozen-input evidence and by "
    "the unit suite, but this gate is handed generated text and so does not re-check the pin",
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
    "is resolved only through the source's own #define table and a macro with a parameter list "
    "is never expanded at all; a macro whose replacement list dereferences a pointer cast or "
    "names the NPU_REG_ prefix -- by a whole register name or by a token paste -- is refused as "
    "unresolved MMIO across the whole vendor translation unit rather than read through, because "
    "the directive line that carries it is blanked before the confinement scan runs and a rule "
    "bounded to the contract-critical bodies left the publishers and the ISR outside both "
    "scans; and one whose replacement list carries a store is "
    "refused outright, because the directive line is blanked before statements are split and "
    "the invocation site then names no storage at all. C line splicing is applied before comment "
    "recognition so a spliced comment opener deletes the same text the compiler deletes, and the "
    "directive patterns run over a splice-joined logical-line view so a directive written across "
    "two physical lines is the one directive the compiler reads. Because a macro is read as one "
    "value for the whole translation unit, a source that undefines or redefines a "
    "V14_/NPU_REG_ macro is refused rather than modelled at whichever value happened to be last. "
    "None of this makes the gate equivalent to a C preprocessor: the general question of what "
    "the preprocessor produces belongs to a build that compiles",
    "mmio_and_mailbox_analysis_is_intraprocedural: every ordering, counting and provenance "
    "rule is proven inside the function that carries it, so a register read or a mailbox "
    "store moved into a helper called from a path that permits calls is outside what those "
    "particular verdicts cover. Four whole-unit rules now bound what that leaves reachable: "
    "require_register_confinement refuses an NPU register named in any function the design "
    "does not name it in; require_whole_unit_mmio_confinement runs the address resolver over "
    "every function span and file scope, so an NPU-region address written as a numeric offset "
    "or an absolute constant is refused wherever this gate cannot pin it to one register and "
    "held to the same owner table wherever it can; require_no_macro_mmio refuses a macro whose "
    "replacement list carries either spelling; and require_mailbox_storage_closed refuses the "
    "appendix reached as whole storage or by an escaped address -- all four across the entire "
    "vendor translation unit. What remains uncovered is therefore a callee in a *different* "
    "translation unit and the built image itself, not a helper in this one",
    "indirect_calls_are_refused_rather_than_resolved: this gate cannot resolve a function "
    "pointer's target, so it refuses the declarator and the postfix call form outright rather "
    "than modelling them. That refusal covers the whole vendor translation unit and, on the "
    "runner side, the function that owns the serialized record -- the stock runner's file-scope "
    "irq_handler_t is its own construct and is not refused, but a pointer declared inside the "
    "diagnostic is, and the record's copy-out parameter is closed against every call the way "
    "the record itself already is. A source that legitimately needs one is a source this gate "
    "cannot verify, and proving the target set of an indirect call site in the built image is "
    "C2-3",
    "published_values_are_proven_against_the_design_text_not_against_hardware: "
    "require_appendix_value_provenance proves each word carries the expression the approved "
    "design gives it, over the C token sequence. That refuses a forged constant and a wrong "
    "source field; it does not and cannot prove the number the hardware produced at run time. "
    "Only a board run comparing published words against independently observed state does",
)

MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"
MAILBOX_RESET_SYMBOL = "v14_mailbox_reset"
MAILBOX_PUBLISH_SYMBOL = "v14_mailbox_publish"
CONVERGE_SYMBOL = "v14_converge"
PRIMARY_SYMBOL = {"Q": "v14_primary_q", "QS": "v14_primary_qs", "SQ": "v14_primary_sq"}

# The record the primary and convergence helpers freeze and the publication
# helper copies into the appendix. ``verify_observation_contract`` is what holds
# it closed; the names live here with the other contract symbols because the
# macro rules below have to know them too.
OBSERVATION_TYPE = "v14_observation_t"
OBSERVATION_FIELDS = ("result", "iterations", "qread", "status", "t_first")
OBSERVATION_SYMBOL = "obs"
OBSERVATION_PUBLISH_SYMBOL = "v14_publish_primary"


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


# C spells several punctuators more than one way, and both alternate spellings
# are unconditional: no flag turns them on and no compiler diagnoses them.
#
#   - A *trigraph* (C11 5.2.1.1) is replaced in translation phase 1 -- before a
#     comment is recognised and before a line is spliced -- so ``??/`` at the
#     end of a line *is* the backslash that splices it.
#   - A *digraph* (C11 6.4.6) is an alternate spelling of the punctuator itself,
#     and 6.10 recognises a directive by the punctuator rather than by how it is
#     written. So ``%:undef V14_MBOX_VARIANT_ID`` is a directive, ``<%`` is an
#     opening brace and ``<:`` is an opening bracket.
#
# Every rule in this file reads the primary spelling. The directive scans anchor
# on the literal ``#``; ``mask_c_lexical``, ``function_spans``, ``split_block``
# and every depth-tracking walk below count the literal ``{``/``}``/``[``/``]``.
# A source written in the alternate spelling is therefore one this gate reads as
# a translation unit the compiler does not build: ``%:undef`` undefines a
# contract macro that no ``#``-anchored scan sees, and one ``<%`` unbalances
# every structural walk here at once.
#
# This gate does not model the alternate spellings, so it refuses them rather
# than analysing a source it is reading wrong. The frozen sources contain none,
# so the refusal costs the contract nothing. It is deliberately the whole
# family and not the ``%:`` the reviewers demonstrated: closing one spelling of
# a token that has three leaves the other two exactly where the first was.
_TRIGRAPH_RE = re.compile(r"\?\?[=/'()!<>-]")
_DIGRAPH_RE = re.compile(r"<%|%>|<:|:>|%:")
_DIGRAPH_PRIMARY = {"<%": "{", "%>": "}", "<:": "[", ":>": "]", "%:": "#"}


def require_primary_token_spelling(text: str, what: str) -> None:
    """Refuse a source that spells a punctuator as a trigraph or a digraph."""

    # Phase 1, so it is read over the raw text: a trigraph inside what looks
    # like a comment or a literal is still replaced, and ``??/`` is what would
    # decide where the comment or the literal ends.
    match = _TRIGRAPH_RE.search(text)
    if match is not None:
        raise fail(
            "%s writes the trigraph %s at offset %d: it is replaced before this gate's "
            "lexical scan runs, so the tokens here are not the ones the compiler sees"
            % (what, match.group(0), match.start())
        )
    # Phase 3, so it is read over the spliced and masked text: a digraph is a
    # token, which makes it code rather than the text of a comment or a string,
    # and a splice between its two characters still spells it.
    spliced, origins = _splice_lines(text)
    match = _DIGRAPH_RE.search(_mask_one_pass(spliced))
    if match is not None:
        offset = origins[match.start()] if match.start() < len(origins) else match.start()
        raise fail(
            "%s writes the digraph %s at offset %d: it is an alternate spelling of %s that "
            "this gate does not model, so every rule here reads a token the compiler does not"
            % (what, match.group(0), offset, _DIGRAPH_PRIMARY[match.group(0)])
        )


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


# The whitespace a preprocessor directive may be written with. A form feed and a
# vertical tab are whitespace to the compiler exactly as a space is, so a class
# spelled ``[ \t]`` is not "directive whitespace" -- it is four of the six
# characters that spell it, and the other two are a rule this gate never sees.
_DIRECTIVE_SPACE = r"[ \t\f\v]"


@functools.lru_cache(maxsize=4)
def directive_view(masked: str) -> str:
    """``masked`` with every logical line joined, byte offsets preserved.

    A preprocessor directive is a *logical* line. Translation phase 2 deletes
    each ``\\``-newline before phase 4 recognises the ``#``, so
    ``#\\``-newline-``undef X`` *is* ``#undef X`` to the compiler --  and
    ``mask_c_lexical`` deliberately puts the backslash and the newline back at
    their original offsets, because every offset-comparing rule below depends on
    that. The two requirements are answered separately rather than traded off:
    the mask keeps the offsets, and this view keeps the *lines*. Blanking the
    splice to as many spaces as it occupied leaves the logical line reading as
    one physical line at the source's own offsets, which is what the directive
    patterns below are written over.

    Without it a directive split by a splice is invisible to every ``(?m)^``
    anchored scan while ``blank_directives`` still removes it from the statement
    stream -- so a source can undefine and redefine a contract macro at a single
    use site, in conforming warning-free C, and this gate models the macro at a
    value the compiler never uses there.
    """

    return _LINE_SPLICE_RE.sub(lambda match: " " * (match.end() - match.start()), masked)


_DEFINE_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*define%(sp)s+([A-Za-z_][A-Za-z0-9_]*)%(sp)s+(\S+)%(sp)s*$"
    % {"sp": _DIRECTIVE_SPACE}
)


def parse_define_values(masked: str) -> dict[str, list[int]]:
    """Return every integer value each object-like macro is given, in order.

    A macro this contract owns -- anything in the ``V14_`` namespace -- has to
    parse. Dropping a malformed one and reporting the macro as *undefined*
    names the wrong defect, and a reader chasing "is not defined" against a
    source that plainly defines it learns nothing. Macros outside the namespace
    are the vendor's and are skipped when they are not integers.
    """

    values: dict[str, list[int]] = {}
    for match in _DEFINE_RE.finditer(directive_view(masked)):
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


_UNDEF_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*undef%(sp)s+([A-Za-z_][A-Za-z0-9_]*)" % {"sp": _DIRECTIVE_SPACE}
)
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

    for match in _UNDEF_RE.finditer(directive_view(masked)):
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

    # An initializer the declarator walk could not flatten binds the name to
    # *something*, and this gate cannot say what. That is ``UNRESOLVED`` -- the
    # answer the callers refuse -- and never ``None``, which would make every
    # dereference of the name an access to nothing at all.
    if expr == UNRESOLVED_INITIALIZER:
        return UNRESOLVED_ROLE
    # The deref test runs over the cast-stripped text, because a cast's closing
    # parenthesis is not an operator: ``(int)*p`` reads the word ``p`` points at
    # exactly as ``*p`` does, and reading it as an address instead leaves the
    # leading ``*`` in the evaluator's hands, which answers ``UNRESOLVED`` and
    # refuses an ordinary value binding. The load itself is not lost -- the
    # ``*`` is its own access site in ``access_expressions``.
    if _has_unary_deref(expr) or _has_unary_deref(_CAST_RE.sub(" ", expr)):
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


def file_scope_text(masked: str) -> str:
    """``masked`` with every top-level function body blanked, offsets preserved.

    What is left is the declarations a function inherits rather than binds. A
    per-function pointer walk that cannot see them reports a dereference of a
    file-scope register pointer as an access to nothing at all, which is how a
    running-QSIZE read moved out of the function that performs it.
    """

    out = list(masked)
    for _name, start, stop in function_spans(masked):
        # A function body's ``{`` follows its parameter list; a brace
        # initializer's follows an ``=``. Only the first is a body, and blanking
        # the second would delete the very declaration this view exists to keep.
        head = masked[: start - 1].rstrip()
        if head.endswith(")"):
            _blank_span(out, masked, start, stop)
    return "".join(out)


def pointer_roles(body: str, defines: dict[str, int], scope: str = "") -> dict[str, str]:
    """Every name in ``body`` bound to an NPU register, transitively.

    ``scope`` is the enclosing declaration text -- the translation unit's file
    scope -- whose bindings the body inherits. It is resolved in the same
    fixpoint rather than beside it, so a file-scope pointer copied into a local
    one is the same pointer here too.

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

    bindings = _bindings(scope) + _bindings(body)
    resolved = _alias_fixpoint(
        bindings,
        lambda expr, known: resolve_address_role(expr, defines, known),
        lambda roles: sorted(roles)[0] if len(roles) == 1 else UNRESOLVED_ROLE,
        "an NPU-region pointer",
    )
    for name in compound_assignment_targets(scope + body, tuple(sorted(resolved))):
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


# One pattern for every ``#define``, because "object-like" and "function-like"
# are the same construct with and without a parameter list, and a rule that
# knows only one of them is a rule the other spelling walks around.
_MACRO_DEFINITION_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*define%(sp)s+([A-Za-z_]\w*)(\([^)\n]*\))?%(sp)s*(.*)$"
    % {"sp": _DIRECTIVE_SPACE}
)


def macro_definitions(masked: str) -> tuple[tuple[str, str, str], ...]:
    """``(name, parameter list, replacement list)`` for every ``#define``.

    Read over ``directive_view`` so a definition split across physical lines is
    the one logical line the compiler sees.
    """

    return tuple(
        (match.group(1), match.group(2) or "", match.group(3))
        for match in _MACRO_DEFINITION_RE.finditer(directive_view(masked))
    )


def mmio_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list carries an MMIO access.

    ``#define REG32(a) (*(volatile uint32_t *)(a))`` turns an MMIO access into
    what reads here as an ordinary call, so the address never reaches
    ``resolve_address_role`` and the access is counted as nothing. This gate
    does not preprocess, so it cannot say which register such a call names --
    which makes it exactly the unresolved access every rule in this file
    refuses rather than ignores.

    An object-like macro is the same construct without a parameter list, and its
    invocation site carries no parentheses at all: ``#define POKE
    write_reg(NPU_REG_CMD, 1U)`` invoked as ``POKE;`` is a submit write that no
    call, effect or CMD-value rule here can see. A replacement list that names a
    register this gate counts is therefore refused on the same terms, whichever
    of the two forms carries it.
    """

    return tuple(sorted(mmio_macro_kinds(masked)))


# A replacement list that merely *names* the ``NPU_REG_`` prefix is the same
# defect one token earlier: ``#define QSEL NPU_REG_QSIZE`` and
# ``#define SEL(x) NPU_REG_##x`` both put a register designation somewhere
# ``blank_directives`` erases it, so the whole-unit confinement scan below walks
# past a running-path QSIZE load and keeps publishing its count as complete.
_RAW_REGISTER_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9_])NPU_REG_")

# And a replacement list that names the *accessor* is the same defect one token
# to the left of that. Every submit-count, QSIZE-count and designation rule in
# this file recognises an MMIO access by the callee token ``read_reg`` or
# ``write_reg``, so ``#define WR write_reg`` and ``#define WR(o,v)
# write_reg((o),(v))`` both put an accessor call somewhere those rules read as
# an ordinary function call to a name they have never heard of -- a second
# submit that no count covers.
ACCESSOR_SYMBOLS = ("read_reg", "write_reg")
_ACCESSOR_SYMBOL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % "|".join(ACCESSOR_SYMBOLS)
)


def mmio_macro_kinds(masked: str) -> dict[str, str]:
    """Every MMIO-carrying macro, mapped to what its replacement list carries.

    ``"designation"`` is a register *name* the confinement scan would otherwise
    never see; ``"accessor"`` is the vendor accessor under another name;
    ``"dereference"`` is an unexpanded MMIO access. The three are reported
    separately because they are refused for different reasons.
    """

    found: dict[str, str] = {}
    for name, _parameters, body in macro_definitions(masked):
        if _RAW_REGISTER_PREFIX_RE.search(body) is not None:
            found[name] = "designation"
        elif _ACCESSOR_SYMBOL_RE.search(body) is not None:
            found[name] = "accessor"
        elif _POINTER_CAST_RE.search(body) is not None and _DEREF_RE.search(body) is not None:
            found[name] = "dereference"
    return found


# ---------------------------------------------------------------------------
# Identifiers the preprocessor builds
#
# Every reachability rule in this file matches a name as *written*:
# ``names_identifier`` for the ``wait_for_irq`` replacement-list scan,
# ``_PUBLICATION_SYMBOL_RE`` for the publishers, ``_ACCESSOR_CALL_RE`` for the
# accessor, ``_direct_call_sites`` for a callee. A ``##`` paste builds the name
# during translation, so one level of indirection is invisible to all of them at
# once:
#
#     #define JOIN(a, b) a##b
#     #define SETTLE()   JOIN(wait_for,_irq)()      /* reaches wait_for_irq   */
#     #define STAMP()    JOIN(v14_publish,_success)()  /* forges the verdict  */
#     #define POKE(o, v) JOIN(write,_reg)((o), (v))    /* an uncounted submit */
#
# This gate does not preprocess, so it cannot compute the name a paste
# produces. Refusing the operator is the honest statement of that: the design
# writes no token paste, and one that appears is a reachability nothing here can
# bound. It is settled with the rest of the preprocessing history rather than
# left to each identifier rule to miss separately.
# ---------------------------------------------------------------------------

_TOKEN_PASTE_RE = re.compile(r"##")


def require_no_token_paste(masked: str, what: str) -> None:
    """Refuse a macro replacement list that builds an identifier by pasting."""

    for name, _parameters, body in macro_definitions(masked):
        if _TOKEN_PASTE_RE.search(body) is None:
            continue
        if _RAW_REGISTER_PREFIX_RE.search(body) is not None:
            # ``#define SEL(x) NPU_REG_##x`` is a paste too, and it is already a
            # refusal by the rule that owns register designations. Leaving it to
            # that rule keeps a source named by the most specific thing wrong
            # with it rather than by the operator it happens to use.
            continue
        raise fail(
            "%s builds an identifier this gate cannot compute: the macro %s pastes tokens in "
            "its replacement list, and a name produced during translation is one no call, "
            "reachability or designation rule in this file can read"
            % (what, name)
        )


# What a macro this gate refuses is reported as when the caller did not resolve
# its kind. The kinds are carried by ``mmio_macro_kinds`` and threaded through
# ``mmio_macro_table`` below, so this is the answer for a caller that passes a
# bare name tuple -- never a guess at a *specific* construct, which is what
# reported an accessor alias as a dereference.
_UNCLASSIFIED_MACRO_KIND = "construct"


def mmio_macro_table(masked: str) -> tuple[tuple[str, ...], dict[str, str]]:
    """``(names, kinds)`` for every MMIO-carrying macro, resolved together.

    Returned as a pair so a caller cannot pass the names of one walk with the
    kinds of another -- or, as happened before, the names with no kinds at all,
    which reported every refusal under whichever construct the default named.
    """

    kinds = mmio_macro_kinds(masked)
    return tuple(sorted(kinds)), kinds


def require_no_macro_mmio(
    text: str, macros: tuple[str, ...], what: str, kinds: dict[str, str] | None = None
) -> None:
    """Refuse an MMIO access made through a macro this gate cannot expand.

    The invocation is looked for as a *name* rather than as ``name(``, because
    an object-like macro is invoked by naming it and a rule that insists on the
    parenthesis sees only half of the construct.
    """

    for name in macros:
        if names_identifier(text, name):
            raise fail(
                "%s reaches an NPU-region address this gate cannot resolve to one register: "
                "the macro %s expands to an unexpanded MMIO %s"
                % (what, name, (kinds or {}).get(name, _UNCLASSIFIED_MACRO_KIND))
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
_DIRECTIVE_LINE_RE = re.compile(
    r"(?m)^%s*#(?:\\[ \t]*\n|[^\n])*" % _DIRECTIVE_SPACE
)


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


# Recovering an assignment costs one walk of the statement it sits in, so a
# statement carrying n of them costs n walks of itself. That is quadratic in
# exactly the construct a declarator list is -- ``T *a = X, *b = a, *c = b, ...``
# is one statement and as many assignments as the operator cares to write -- and
# a verdict is not allowed to become a stall.
#
# The budget is the bound written down, derived from the input the way the alias
# walks derive theirs. The frozen sources spend under half of one pass over
# their own text; eight passes is room for a legitimately dense translation unit
# and none for a statement written to be walked n times. Exceeding it is a named
# refusal -- never a truncated statement list, which would drop the very stores
# every rule below is written over.
_STATEMENT_SCAN_FACTOR = 8
_STATEMENT_SCAN_FLOOR = 4096


def _statement_scan_budget(text: str) -> int:
    return _STATEMENT_SCAN_FACTOR * len(text) + _STATEMENT_SCAN_FLOOR


def _refuse_statement_scan(walked: int, budget: int) -> None:
    raise fail(
        "recovering the statements of this source did not settle within %d walked characters "
        "(reached %d): it writes more assignments into one statement than this gate walks"
        % (budget, walked)
    )


def assignment_statements(text: str) -> tuple[tuple[int, str, str], ...]:
    """``(start, lvalue, rvalue)`` for every simple assignment in ``text``."""

    scan = blank_directives(text)
    budget = _statement_scan_budget(scan)
    walked = 0
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
            walked += stop - start
            if walked > budget:
                _refuse_statement_scan(walked, budget)
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
    budget = _statement_scan_budget(scan)
    walked = 0
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
            # Each recovered lvalue is one walk of its own statement, so the
            # same budget bounds the same quadratic ``assignment_statements``
            # is bounded against.
            compound = _COMPOUND_LVALUE_RE.match(scan, index)
            if compound is not None and scan[compound.end() : compound.end() + 1] != "=":
                walked += index - start
                if walked > budget:
                    _refuse_statement_scan(walked, budget)
                found.append((start, scan[start:index]))
                index = compound.end()
                continue
            step = _STEP_RE.match(scan, index)
            if step is not None:
                before = scan[start:index].strip()
                after = _expression_after(scan, step.end())
                walked += (index - start) + len(after)
                if walked > budget:
                    _refuse_statement_scan(walked, budget)
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


# An operator that *stores*. The comparisons are excluded by construction: the
# character before an ``=`` that makes it something other than a plain
# assignment is the same set ``assignment_statements`` already reads.
_MACRO_STORE_RE = re.compile(
    r"(?<![=!<>+\-*/%%&|^])=(?!=)|\+\+|--|(?:%s)"
    % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
)


def statement_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list carries a store rather than a value."""

    return tuple(
        sorted(
            {
                name
                for name, _parameters, body in macro_definitions(masked)
                if _MACRO_STORE_RE.search(body) is not None
            }
        )
    )


def require_no_statement_macro(masked: str, what: str) -> None:
    """Refuse a source that hides a store inside a macro replacement list.

    ``blank_directives`` removes the ``#define`` line from the statement stream
    -- it has to, or the directive folds into the next statement's lvalue -- and
    the invocation site is then only ``NAME;``, which names no storage at all.
    So ``#define POKE mailbox[V14_MBOX_VARIANT_ID] = 7U`` is a store that exists
    for the compiler and for no rule in this file: not for
    ``assignment_statements``, not for ``mailbox_stores``, not for the
    ``irq_triggered`` site walk, and not for the runner's record closure.

    This gate does not expand macros, which is stated in every manifest, so it
    cannot model where such a body lands. The fail-closed answer is to refuse the
    definition rather than to analyse a translation unit whose stores it cannot
    see; the frozen sources define no such macro, so the refusal costs the
    contract nothing.
    """

    names = statement_macro_names(masked)
    if names:
        raise fail(
            "%s defines %s with a statement in its replacement list: this gate does not "
            "expand macros, so a store written there is a store no rule here can see"
            % (what, names[0])
        )


# A store is an operator and an lvalue, and ``statement_macro_names`` keys on
# the operator. A macro whose body is the *lvalue* carries no operator at all:
#
#     #define CR_SLOT pmu_completion_visibility_v14_mailbox[V14_MBOX_CONVERGENCE_RESULT]
#     CR_SLOT = V14_CONVERGENCE_SUCCESS;
#
# is a second store to appendix word 15 whose ``=`` sits one token outside the
# replacement list. ``blank_directives`` removes the definition, the invocation
# reads as an assignment to the name ``CR_SLOT``, and ``resolve_mailbox_word``
# answers "not the mailbox" -- so the store is dropped silently. The same holds
# for the array name alone (``#define MB_ARR <mailbox>``, written ``MB_ARR[i] =``)
# and for an observation or record member (``#define OBS_RESULT obs->result``).
#
# This gate does not expand macros either way, so a replacement list that *names*
# the storage the contract tables are written over is refused on exactly the
# terms one carrying a store is. The frozen sources define no such macro.
_MACRO_CRITICAL_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:%s|V14_MBOX_\w+|%s)(?![A-Za-z0-9_])"
    % (re.escape(MAILBOX_SYMBOL), re.escape(OBSERVATION_SYMBOL))
)
_MACRO_CRITICAL_MEMBER_RE = re.compile(
    r"(?:->|\.)\s*(?:%s)(?![A-Za-z0-9_])"
    % "|".join(re.escape(name) for name in sorted(set(APPENDIX_FIELDS + OBSERVATION_FIELDS)))
)


def critical_lvalue_macro_names(masked: str) -> tuple[str, ...]:
    """Every macro whose replacement list names storage the contract tables own."""

    return tuple(
        sorted(
            {
                name
                for name, _parameters, body in macro_definitions(masked)
                if _MACRO_CRITICAL_NAME_RE.search(body) is not None
                or _MACRO_CRITICAL_MEMBER_RE.search(body) is not None
            }
        )
    )


# A compound literal is a brace initializer with no declarator in front of it,
# so there is no name for the declarator walk to bind and no name for any alias
# rule below to follow:
#
#     (void)*((volatile uint32_t *const []){ (volatile uint32_t *)(U85 + QSIZE) })[0];
#
# is a QSIZE load whose address never reaches ``resolve_address_role`` -- the
# same access spelled through a named array is refused by name. Binding it would
# mean inventing a name for storage the source never named, so the fail-closed
# answer is to refuse the construct: this gate cannot attribute the initializer
# to anything, and "cannot attribute" has to refuse rather than ignore. The
# frozen sources contain no compound literal.
# What may precede the ``(`` of a call's argument list: a callee name, or the
# ``)``/``]`` of an expression that yields one.
_CALLABLE_END = frozenset(")]")


def _opens_compound_literal(text: str, brace: int, open_of: dict[int, int]) -> bool:
    """Whether the ``{`` at ``brace`` is a compound literal's, not a block's."""

    cursor = brace - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0 or text[cursor] != ")":
        return False
    open_index = open_of.get(cursor)
    if open_index is None:
        return False
    tokens = _C_TOKEN_RE.findall(text[open_index + 1 : cursor])
    if not any(token in _DECLARATOR_TYPES for token in tokens):
        return False
    # What separates the parentheses of a compound literal's type name from a
    # function definition's parameter list, or an ``if``'s condition, is what
    # sits in front of them: a callee name or a keyword, or the ``)``/``]`` of
    # something already callable. A unary ``&`` is not one of those -- nothing
    # is called through it -- so the operand-end set ``_strip_address_of`` uses
    # is deliberately not the set here: ``*&(volatile uint32_t *const){ addr }``
    # is a compound literal, and reading its ``&`` as an operand end is what let
    # one through.
    cursor = open_index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return False
    return not (_NAME_CHARACTER_RE.match(text[cursor]) or text[cursor] in _CALLABLE_END)


def require_no_compound_literal(masked: str, what: str) -> None:
    """Refuse an initializer this gate cannot attribute to any declared name."""

    _close_of, open_of = _bracket_pairs(masked)
    for index, character in enumerate(masked):
        if character == "{" and _opens_compound_literal(masked, index, open_of):
            raise fail(
                "%s writes a compound literal at offset %d: it initializes storage this gate "
                "cannot bind to any name, so an access through it is an access no rule here sees"
                % (what, index)
            )


def require_no_critical_lvalue_macro(masked: str, what: str) -> None:
    """Refuse a macro that spells the mailbox, an appendix word or a record field."""

    names = critical_lvalue_macro_names(masked)
    if names:
        raise fail(
            "%s defines %s with contract storage in its replacement list: this gate does not "
            "expand macros, so a store written through it is a store no rule here can see"
            % (what, names[0])
        )


# A declarator binds an address without ever writing ``name = expr``:
# ``volatile uint32_t *const regs[1] = { A }`` is a binding of ``regs`` that the
# assignment pattern cannot match, so every dereference of it reached
# ``resolve_address_role`` with nothing to resolve and came back as "not an NPU
# address at all" -- the one answer that makes an access invisible rather than
# refused. Each initializer element is bound to the name, so a name whose
# elements designate two registers collapses to ``UNRESOLVED`` exactly as a name
# assigned twice does.
#
# Only the declarator *head* is matched here. Recovering the initializer with a
# pattern is what reopened the hole this rule was written to close: an
# initializer body spelled ``[^{}]*`` cannot contain a brace, so
# ``*const p[1][1] = {{ A }}`` -- and the equally conforming 1-D
# ``*const p[1] = { { A } }`` -- matched nothing at all and left every
# dereference of ``p`` invisible again. The body is therefore brace-matched and
# flattened below instead of pattern-matched.
_DECLARATOR_INITIALIZER_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(?:\[[^\[\];{}]*\])+\s*=\s*(?=\{)"
)

# The binding a declarator walk hands over when it cannot reduce an initializer
# to its elements. It is deliberately not C: every resolver below answers
# ``UNRESOLVED`` for it, so a name whose initializer this gate cannot read
# refuses every access through it. That asymmetry is the whole point -- "no
# binding" makes an access invisible, and only "unresolved" makes it refused.
UNRESOLVED_INITIALIZER = "@an initializer this gate cannot flatten@"

# A designator names which element an initializer clause fills; the clause
# itself is what binds the address. ``{ [0] = A }`` and ``{ .lo = A }`` reach
# the same storage ``{ A }`` does.
_DESIGNATOR_RE = re.compile(r"^\s*(?:\[[^\[\]]*\]|\.\s*[A-Za-z_]\w*)\s*(?:\[[^\[\]]*\]|\.\s*[A-Za-z_]\w*)*\s*=(?!=)")

# The flattening walk is bounded for the same reason the alias walks are: an
# operator-supplied source may nest braces as deeply as it likes, and a verdict
# is not allowed to become a stall.
#
# The budget counts *characters examined*, not clauses, because the cost here is
# re-reading the same text once per nesting level: an initializer 8000 bytes
# long and 4000 braces deep is 4000 clauses -- nothing at all to a clause
# counter -- and thirty-two million character reads to the walk. Four passes
# over the initializer is room for the nesting a declarator legitimately has
# and none for a source that nests to make the walk quadratic.
#
# The element cap is the same bound from the other side: a declarator that binds
# one name to fifty thousand addresses hands fifty thousand bindings to every
# alias walk in this file, each of which then re-reads them. A declarator wider
# than this is one this gate does not walk.
#
# Exceeding either bound is ``UNRESOLVED_INITIALIZER``, which every resolver
# below refuses by name -- never silence, which is what would make the access
# invisible.
_INITIALIZER_BUDGET_FACTOR = 4
_INITIALIZER_BUDGET_FLOOR = 1024
_MAX_INITIALIZER_ELEMENTS = 1024


def _split_initializer(text: str) -> tuple[str, ...]:
    """Split an initializer body on the commas that separate its clauses.

    ``_split_top_level`` counts parentheses and brackets only, which is right
    for an argument list and wrong here: the comma between two *nested* brace
    groups sits at paren depth zero, so a nested initializer would be cut in
    half rather than descended into.
    """

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        if depth == 0 and character == ",":
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(character)
    parts.append("".join(buffer))
    return tuple(parts)


def _initializer_elements(text: str, open_index: int) -> tuple[str, ...]:
    """The leaf clauses of the brace list at ``open_index``, nesting flattened.

    A brace group is descended into rather than treated as one clause, so
    ``{{ A }}`` and ``{ { A } }`` bind exactly what ``{ A }`` binds. A clause
    this walk cannot reduce to a brace-free expression -- an unterminated group,
    or one still carrying a brace after its designator comes off -- is
    ``UNRESOLVED_INITIALIZER`` rather than nothing, because a name left unbound
    is a name every access through it resolves to "not an address at all".
    """

    depth = 0
    close = -1
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                close = index
                break
    if close < 0:
        return (UNRESOLVED_INITIALIZER,)
    budget = _INITIALIZER_BUDGET_FACTOR * (close - open_index) + _INITIALIZER_BUDGET_FLOOR
    elements: list[str] = []
    pending = [text[open_index + 1 : close]]
    read = 0
    while pending:
        body = pending.pop()
        read += len(body)
        if read > budget or len(elements) > _MAX_INITIALIZER_ELEMENTS:
            return (UNRESOLVED_INITIALIZER,)
        for clause in _split_initializer(body):
            item = _DESIGNATOR_RE.sub("", clause).strip()
            if not item:
                continue
            if item.startswith("{") and item.endswith("}"):
                pending.append(item[1:-1])
                continue
            elements.append(UNRESOLVED_INITIALIZER if "{" in item or "}" in item else item)
    if len(elements) > _MAX_INITIALIZER_ELEMENTS:
        return (UNRESOLVED_INITIALIZER,)
    return tuple(elements)


def _declarator_bindings(text: str) -> tuple[tuple[str, str], ...]:
    """``(name, element)`` for every array declarator initialized with a brace list."""

    found: list[tuple[str, str]] = []
    for match in _DECLARATOR_INITIALIZER_RE.finditer(text):
        for element in _initializer_elements(text, match.end()):
            found.append((match.group(1), element))
    return tuple(found)


# The assignment form of a binding, recovered by scanning for the operator
# rather than by one pattern that runs to the statement terminator.
# ``T *const a = <addr>, *const b = a;`` is *two* bindings in one statement, and
# a pattern anchored on ``;`` matches it once -- binding ``a`` to the whole
# ``<addr>, *const b = a`` tail and consuming ``b``'s binding with it, so every
# dereference of ``b`` resolved to nothing at all. The scan below finds each
# operator independently and reads only as far as the clause it belongs to.
_ASSIGNMENT_OPERATOR_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*=(?!=)")


def _clause_expression(text: str, start: int) -> str:
    """The expression at ``start``, up to the comma or semicolon that ends it."""

    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and character in ",;":
            break
        index += 1
    return text[start:index]


def _assignment_bindings(text: str) -> tuple[tuple[str, str], ...]:
    """``(name, expr)`` for every ``name = expr`` clause, declarator lists split."""

    found: list[tuple[str, str]] = []
    for match in _ASSIGNMENT_OPERATOR_RE.finditer(text):
        operator = match.end() - 1
        if text[operator - 1 : operator] in _ASSIGNMENT_BOUNDARY:
            continue
        expression = _clause_expression(text, match.end()).strip()
        if expression:
            found.append((match.group(1), expression))
    return tuple(found)


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

    # Same asymmetry as ``resolve_address_role``: an initializer this gate could
    # not flatten may well name the mailbox, so it is refused rather than
    # dropped.
    if expr == UNRESOLVED_INITIALIZER:
        return UNRESOLVED_ROLE
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


_TYPE_NAME_TOKEN_RE = re.compile(r"^[A-Za-z_]\w*$")


def _is_cast_parenthesis(text: str, open_index: int, close_index: int) -> bool:
    """Whether ``text[open_index:close_index]`` is a cast rather than an operand.

    A cast's ``)`` and a call's ``)`` are the same character, which is why a rule
    that reads "the previous character is ``)``" as "an operand ended here"
    resolves ``(bool *)&flag`` the same way it resolves ``f() & flag`` -- and
    resolves it in the fail-open direction, because the first one takes an
    address and the second one reads a value.

    The two are separable without a symbol table. A cast encloses a type name and
    nothing else -- identifiers and ``*``, no literal, no operator, no comma --
    and nothing that can end an operand may precede its ``(``, or the parentheses
    are a call's argument list or a subscripted expression instead. A
    parenthesised single identifier is ambiguous in C itself; it is read here as a
    cast, which is the direction that refuses rather than credits.
    """

    tokens = _C_TOKEN_RE.findall(text[open_index + 1 : close_index])
    if not tokens:
        return False
    for token in tokens:
        if token != "*" and _TYPE_NAME_TOKEN_RE.match(token) is None:
            return False
    cursor = open_index - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return True
    return not (
        _NAME_CHARACTER_RE.match(text[cursor]) or text[cursor] in _OPERAND_END_CHARACTERS
    )


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


def _is_declarator_subscript(text: str, base_start: int) -> bool:
    """Whether the name at ``base_start`` is being *declared* as an array.

    ``volatile uint32_t *const regs[1] = { ... }`` gives the array its extent;
    it does not read one of its elements. Counting the declarator's brackets as
    an access invents a load at ``regs + 1`` that the image never performs --
    and once the name is bound to a register, that invented load resolves to
    whatever sits one word past it, which is a rejection with the wrong name.
    """

    cursor = base_start - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if cursor < 0:
        return False
    if text[cursor] == "*":
        return _is_declarator_star(text, cursor)
    return _token_before(text, cursor + 1)[1] in _DECLARATOR_TYPES


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
        if _is_declarator_subscript(text, start):
            continue
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


_QUEUE_PROGRAMMING_ROLES = ("QSIZE", "QBASE")


def queue_programming_sites(
    vendor_masked: str,
    defines: dict[str, int],
    scope: str,
    spans: tuple[tuple[str, int, int], ...],
) -> tuple[int, ...]:
    """Every site that programs the queue, whatever spelling reaches it.

    The frozen sources program the queue through ``write_reg``, and a scan for
    that call is what the single-owner rule was built on. A write through a
    bound pointer reaches the same register and carries no call for that scan to
    find, so a declarator was all it took to reprogram QSIZE in the cleanup tail
    while the gate still proved "queue programming lives in one function" about
    the call sites alone. The resolved write dereferences are therefore collected
    here beside the calls, per function, so a site is a site whichever spelling
    performs it.
    """

    sites = set(code_positions(vendor_masked, _QBASE_WRITE, open_end=True))
    sites.update(code_positions(vendor_masked, _QSIZE_WRITE))
    for _name, start, stop in spans:
        body = vendor_masked[start:stop]
        roles = pointer_roles(body, defines, scope)
        for site, role, is_write in dereference_sites(body, defines, roles):
            if is_write and role.startswith(_QUEUE_PROGRAMMING_ROLES):
                sites.add(start + site)
    return tuple(sorted(sites))


def _pre_program_gate_function(vendor_masked: str, spans) -> str:
    """The one function that carries the pre-program gate.

    The gate is found by the object it binds rather than by a function name, so
    it holds wherever the vendor keeps it -- and requiring exactly one owner is
    what keeps a second gate from being introduced somewhere the guards below
    are never applied to it.
    """

    owners = sorted(
        {
            name
            for name, start, stop in spans
            if code_positions(vendor_masked[start:stop], "pre_program_status")
        }
    )
    if not owners:
        raise fail("pre-program gate is missing: no function binds pre_program_status")
    if len(owners) != 1:
        raise fail("pre-program gate is split across %d functions: %s" % (len(owners), owners))
    return owners[0]


def verify_pre_run_contract(vendor_masked: str, defines: dict[str, int]) -> dict[str, object]:
    """Prove the stopped-state gate, the single QSIZE snapshot and fail-closed submit.

    Everything proved here is a property of the source text: which objects exist,
    how many loads there are, which guards consume them, and that each guard
    returns. Ordering and dominance are deliberately *not* proved here. They are
    control-flow properties, this module reads characters, and a rule that reads
    character order as execution order is wrong in exactly the case that matters
    -- mutually exclusive branches, and gates that sit in a caller. Those claims
    are bound on the linked image instead, and the keys returned below are named
    so that none of them can be read as a dominance proof.
    """

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
    mmio_macros, mmio_kinds = mmio_macro_table(vendor_masked)
    scope = file_scope_text(vendor_masked)
    spans = function_spans(vendor_masked)
    programming_sites = queue_programming_sites(vendor_masked, defines, scope, spans)
    if not programming_sites:
        raise fail("pre-program STATUS gate does not dominate QBASE/QSIZE: no queue programming found")
    owners = {enclosing_function(spans, site) for site in programming_sites}
    if len(owners) != 1:
        raise fail("queue programming is split across %d functions: %s" % (len(owners), sorted(owners)))
    programming_name = sorted(owners)[0]
    setup_start, setup_stop = function_span(vendor_masked, programming_name, "queue setup function")
    setup = vendor_masked[setup_start:setup_stop]
    setup_roles = pointer_roles(setup, defines, scope)
    require_resolved_pointers(setup_roles, "queue setup function")
    require_resolved_dereferences(setup, defines, setup_roles, "the queue setup function")
    require_no_macro_mmio(setup, mmio_macros, "the queue setup function", mmio_kinds)

    # The gate is where ``pre_program_status`` is, which need not be the function
    # that programs the queue -- in the real vendor it is the caller. Anchoring
    # it on the programming function instead was a rule that only its own
    # fixtures could satisfy: it found the *post*-program load, called it the
    # gate, and reported the gate as late.
    gate_name = _pre_program_gate_function(vendor_masked, spans)
    gate_start, gate_stop = function_span(vendor_masked, gate_name, "pre-program gate function")
    gate = vendor_masked[gate_start:gate_stop]
    gate_roles = pointer_roles(gate, defines, scope)
    require_resolved_pointers(gate_roles, "pre-program gate function")
    require_resolved_dereferences(gate, defines, gate_roles, "the pre-program gate function")
    require_no_macro_mmio(gate, mmio_macros, "the pre-program gate function", mmio_kinds)

    pre_program_reads = register_access_sites(gate, "STATUS", defines, gate_roles)
    if len(pre_program_reads) != 1:
        raise fail(
            "pre-program gate does not read STATUS exactly once: %d loads in %s"
            % (len(pre_program_reads), gate_name)
        )

    # Whether the gate *dominates* the programming writes is a control-flow
    # property. Text order cannot decide it -- two sites in mutually exclusive
    # branches have an order here and no order at run time, which is how the
    # vendor's eU85_TEST0 pin-toggle writes to QBASE_LSB came to be read as
    # queue programming. What text can decide is that the gate and the
    # programming are connected at all, so that is what is claimed here; the
    # dominance proof itself is bound on the linked image.
    if gate_name != programming_name and not code_positions(gate, programming_name + "("):
        raise fail(
            "pre-program gate and queue programming are unconnected: %s neither programs the queue nor calls %s"
            % (gate_name, programming_name)
        )

    for mask, label in (
        ("V14_STATUS_STATE", "stopped"),
        ("V14_STATUS_RESET", "reset_status"),
        ("V14_STATUS_FAULT_MASK", "vendor fault"),
    ):
        guards = [c for c, _ in _guard_blocks(gate, "pre_program_status") if names_identifier(c, mask)]
        if len(guards) != 1:
            raise fail("pre-program gate omits stopped/reset/fault: %s check is missing" % label)

    require_load_provenance(
        gate, "pre_program_status", pre_program_reads, "STATUS", "pre-program gate"
    )

    # The design forbids a running transition between the gate and the
    # programming writes. That window is a control-flow span, and once the gate
    # and the programming can live in different functions the span is not a
    # range of characters in one of them. What is decidable here is the part of
    # the window inside the gate function: nothing may transition the state
    # after the gate load and before the function hands control on. The rest of
    # the window is bound on the linked image.
    after_gate = tuple(
        site
        for site, _value in cmd_write_values(gate, defines, gate_roles)
        if site > pre_program_reads[0]
    )
    if after_gate:
        raise fail(
            "state-transitioning CMD write after the pre-program gate in %s" % gate_name
        )

    qsize_writes = [
        site
        for site, role, is_write in dereference_sites(setup, defines, setup_roles)
        if is_write and role == "QSIZE"
    ] + list(code_positions(setup, _QSIZE_WRITE))
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
    command_roles = pointer_roles(command, defines, scope)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, mmio_macros, "the command function", mmio_kinds)

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
    # This comparison is over ``test_commands`` only, which is what the manifest
    # key below is named for. The claim that no QSIZE access is reachable from the
    # running window at all is a different proof and belongs to
    # ``require_register_confinement``, which scans the whole translation unit.

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
        # Named for the scope it is actually taken over. The whole-unit claim is
        # ``vendor_register_designations_confined``.
        "running_qsize_loads_in_test_commands": len(running_qsize_loads),
        # Where the two halves of the pre-run contract were found, so a reader
        # can see whether they were in one function or two without rerunning
        # anything.
        "pre_program_gate_function": gate_name,
        "queue_programming_function": programming_name,
        # What this gate did and did not prove, in the manifest rather than in a
        # comment, because a consumer reads the manifest.
        "pre_run_source_scope": "shape_only_no_control_flow",
        "pre_run_dominance_deferred_to": (
            "linked-image proof: pre-program gate dominates every QBASE/QSIZE write, "
            "and no state transition occurs between them"
        ),
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
    """Every ``name = expr`` and every array declarator element in ``text``.

    Both forms hand a name an address, and a walk that knows only the first one
    resolves a dereference of the second to nothing rather than to a register.
    """

    return _assignment_bindings(text) + _declarator_bindings(text)


def _is_pointer_binding(expr: str) -> bool:
    """Whether ``expr`` hands over the storage itself rather than a word of it.

    ``p = mb`` and ``p = &mb[3]`` name the array; ``v = mb[3]`` names the value
    in one of its words, and calling that an alias would make every reader of a
    mailbox word a second name for the mailbox.
    """

    if "&" in expr:
        return True
    return "[" not in expr and not _has_unary_deref(expr)


def _seeded_bindings(
    bindings: tuple[tuple[str, str], ...], dependents: dict[str, list[int]], root: str
) -> list[int]:
    """The binding indices an alias walk from ``root`` has to start at.

    The bindings that mention ``root``, plus every binding whose initializer the
    declarator walk could not flatten. The second half is what keeps the walk
    honest: such a binding may name ``root`` and this gate cannot see that it
    does, and a name it never examines is a second name for the storage that no
    rule downstream covers.
    """

    seeds = list(dependents.get(root, ()))
    seen = set(seeds)
    for index, (_name, expr) in enumerate(bindings):
        if expr == UNRESOLVED_INITIALIZER and index not in seen:
            seeds.append(index)
            seen.add(index)
    return seeds


def obs_aliases(text: str) -> tuple[str, ...]:
    """Every local name bound to the observation record pointer, transitively."""

    bindings = _bindings(text)
    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    names = {"obs"}
    pending = collections.deque(_seeded_bindings(bindings, dependents, "obs"))
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
        if name in names:
            continue
        # An initializer this gate could not flatten may name the record, so the
        # name it binds is treated as a second name for it rather than as
        # something the walk is free to ignore.
        if expr != UNRESOLVED_INITIALIZER:
            if _MEMBER_ACCESS_RE.search(expr) is not None:
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
    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
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
    require_no_macro_mmio(body, *mmio_macro_table(vendor_masked)[:1], "the primary helper",
                          mmio_macro_table(vendor_masked)[1])

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
    # An address *bound* in a declarator never appears as an access expression:
    # ``*const iser[1] = { (volatile uint32_t *)(0xE000E000UL + 0x100UL) }`` puts
    # the cast in the initializer and leaves the write spelled ``*iser[0]``,
    # which carries no cast for this fold to recognise. The bindings are folded
    # here for the same reason the accesses are -- the register is reached
    # either way, and only the spelling differs.
    candidates = [
        (site, expression) for site, expression, _is_write in access_expressions(vendor_masked)
    ]
    # Both binding forms, through the same walk every other rule reads them
    # with, so a nested-brace or comma-separated declarator is folded here too.
    # A binding carries the name it bound rather than an offset, because the
    # walk resolves a declarator to its elements and an element has no single
    # site the way an access expression does.
    for name, expression in _bindings(vendor_masked):
        candidates.append(("the binding of %s" % name, expression))
    for site, expression in candidates:
        if _POINTER_CAST_RE.search(expression) is None:
            continue
        value = _evaluate_constant(_flatten_address(expression), defines)
        if value is None:
            continue
        if NVIC_ISER_BASE <= (value & 0xFFFFFFFF) < NVIC_ISER_BASE + NVIC_ISER_BYTES:
            raise fail(
                "direct NVIC ISER enable write is reachable: computed address at %s"
                % (site if isinstance(site, str) else "offset %d" % site)
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
    _open_of = _bracket_pairs(vendor_masked)[1]
    for match in re.finditer(r"&\s*(?:\(\s*)*irq_triggered(?![A-Za-z0-9_])", vendor_masked):
        # ``mask & irq_triggered`` reads the flag; only address-of aliases it.
        previous = _token_before(vendor_masked, match.start())[1]
        cursor = match.start() - 1
        while cursor >= 0 and vendor_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if previous:
            continue
        if cursor >= 0 and vendor_masked[cursor] in _OPERAND_END_CHARACTERS:
            # A cast's closing parenthesis is not the end of an operand, so
            # ``(bool *)&irq_triggered`` takes the address the same way a bare
            # ``&irq_triggered`` does. Reading the two alike is what let the
            # alias be bound and the flag set through it, with the manifest still
            # publishing the stock handler as the flag's only writer.
            opening = _open_of.get(cursor) if vendor_masked[cursor] == ")" else None
            if opening is None or not _is_cast_parenthesis(vendor_masked, opening, cursor):
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

    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
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
    require_no_macro_mmio(body, *mmio_macro_table(vendor_masked)[:1], "the convergence helper",
                          mmio_macro_table(vendor_masked)[1])

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


# ---------------------------------------------------------------------------
# Storage closure
#
# Two rules in this file prove what a *named* store does: the appendix producer
# table for the mailbox, and the write-once proof for the runner record. Both
# read an lvalue and resolve the storage it designates, so both are answered by
# a write that names no lvalue at all -- ``memcpy`` through a field pointer, a
# ``memset`` over the record, a second name the walk cannot follow. The helpers
# below close that hop: the address of the storage is what is bounded, so a
# write through any of those spellings is refused before it has to be resolved.
# ---------------------------------------------------------------------------

# A postfix expression: the operand a unary ``&`` takes. Read as one bounded
# pattern rather than a backtracking walk, because the text it is applied to is
# a whole translation unit.
_POSTFIX_OPERAND_RE = re.compile(
    r"\s*\(*\s*[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[^\[\]]*\])*"
)


def address_of_operands(text: str) -> tuple[tuple[int, str], ...]:
    """``(site, operand)`` for every *unary* ``&`` in ``text``.

    Unary is decided the way ``_strip_address_of`` decides it -- nothing that
    can end an operand precedes it -- so ``base & mask`` is left alone and
    ``&d.variant_id`` is not.
    """

    found: list[tuple[int, str]] = []
    previous = ""
    for index, character in enumerate(text):
        if character in _INLINE_SPACE:
            continue
        if character == "&" and not (
            previous
            and (previous in _OPERAND_END_CHARACTERS or _NAME_CHARACTER_RE.match(previous))
        ):
            match = _POSTFIX_OPERAND_RE.match(text, index + 1)
            if match is not None:
                found.append((index, match.group(0).strip()))
            previous = "&"
            continue
        previous = character
    return tuple(found)


def enclosing_calls(text: str, offsets: frozenset) -> dict[int, str]:
    """The innermost callee whose argument list encloses each wanted offset.

    Walked once with an explicit stack rather than by matching each call's
    parenthesis on demand: an unterminated ``(`` makes every on-demand match
    rescan to the end of the text, which is the quadratic ``_bracket_pairs``
    already exists to avoid.
    """

    enclosing: dict[int, str] = {}
    stack: list[str] = []
    for index, character in enumerate(text):
        if character == "(":
            _start, name = _token_before(text, index)
            stack.append("" if name in _NON_CALL_KEYWORDS else name)
        elif character == ")":
            if stack:
                stack.pop()
        elif index in offsets and stack:
            enclosing[index] = stack[-1]
    return enclosing


def _member_base_follows(text: str, index: int) -> bool:
    """Whether the name ending at ``index`` is the base of a member access."""

    cursor = index
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    if text[cursor : cursor + 2] == "->":
        return True
    return text[cursor : cursor + 1] == "." and text[cursor + 1 : cursor + 2] != "."


def _is_whole_rvalue(text: str, start: int, stop: int) -> bool:
    """Whether ``text[start:stop]`` is the entire right-hand side of a copy."""

    cursor = start - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    if text[cursor : cursor + 1] != "=" or text[cursor - 1 : cursor] in _ASSIGNMENT_BOUNDARY:
        return False
    cursor = stop
    while cursor < len(text) and text[cursor] in _INLINE_SPACE:
        cursor += 1
    return text[cursor : cursor + 1] == ";"


def require_record_storage_closed(runner_masked: str, window: tuple[int, int]) -> None:
    """Bound every way the serialized record's storage can be reached.

    ``verify_runner_contract`` proves the 34 appendix fields are written exactly
    once, inside the magic branch, from the word the wire order gives them. It
    proves that over *lvalues it can resolve to the record*, and ``_record_member``
    only resolves an lvalue whose last token follows a ``.`` or a ``->``. A write
    that names no member is therefore neither proven nor refused, and three of
    them reach the same storage:

        { uint32_t *pf = &d.variant_id; *pf = 3U; }
        memset(&d.variant_id, 0, 34U * 4U);
        { uint32_t z = 3U; memcpy(&d.variant_id, &z, sizeof z); }

    Each one rewrites a published field while the manifest still reports the 34
    proven copies. They are answered here the way ``verify_hard_bypass_contract``
    answers ``&irq_triggered`` -- by refusing the *address*, which is the one
    token all three share:

    * the address of an appendix field is refused wherever it is taken, because
      the design never takes one and a pointer to a field is a write to that
      field this gate cannot see; and
    * inside the window the write-once proof covers -- from the end of the
      magic branch to the end of the function that owns the record -- the record
      and its aliases may only be the base of a member access or the whole
      right-hand side of a copy, so ``memset(&d, ...)``, a cast of the record to
      a byte pointer, and handing it to any call are all refused.

    Outside that window the record is not yet the transport: it is zeroed and
    its frozen v7/v8 snapshot fields are filled by address, which is why the
    second rule is bounded to the window and the first one is not.
    """

    aliases = frozenset(record_aliases(runner_masked))
    names = aliases | {RECORD_SYMBOL}
    appendix = frozenset(APPENDIX_FIELDS)
    for site, operand in address_of_operands(runner_masked):
        field = _record_field_target(operand, aliases)
        if field in appendix:
            raise fail(
                "the runner takes the address of the appendix field %s at offset %d: a write "
                "through it is a write the record's write-once proof cannot see" % (field, site)
            )
    start, stop = window
    for match in _IDENTIFIER_RE.finditer(runner_masked, start, stop):
        if match.group(0) not in names:
            continue
        if _member_base_follows(runner_masked, match.end()):
            continue
        if _is_whole_rvalue(runner_masked, match.start(), match.end()):
            continue
        raise fail(
            "the runner reaches the serialized record as whole storage at offset %d, after the "
            "magic-gated appendix copy: %s is neither a member access nor a copy of the record"
            % (match.start(), match.group(0))
        )


# The observation record is the mailbox one hop upstream. ``v14_publish_primary``
# copies ``obs->result``, ``obs->iterations``, ``obs->qread``, ``obs->status``
# and ``obs->t_first`` into the appendix, so every provenance, predicate and
# publishing-guard proof this file makes about those words is a proof about a
# record no rule constrained: one trailing ``obs->result = V14_PRIMARY_OBSERVED``
# republished a timed-out run as an observed one with the mailbox rules fully
# satisfied and the manifest byte-identical.
#
# It therefore gets what ``APPENDIX_PRODUCERS`` gives the mailbox: the sites the
# design writes each field from, and how many times each of them writes it.
_OBSERVATION_DECL_RE = re.compile(
    r"(?<![A-Za-z0-9_])struct\s+%s\s*(?:\*\s*)*(?:const\s+)?([A-Za-z_]\w*)"
    % re.escape(OBSERVATION_TYPE)
)

# The Q primary publishes its five fields once on the observed path and again on
# the timeout path, and settles ``result`` in each of its three timeout
# classifications; the dual-read primaries carry the same shape with a second
# completion guard. The convergence helper publishes each field exactly once.
#
# The table binds each field to the exact *values* its owner stores, not merely
# to how many times it stores it. A count closes the store that is *added* --
# the trailing ``obs->result = V14_PRIMARY_OBSERVED`` that republishes a
# timed-out run -- and says nothing about the store that is *substituted*:
#
#     -    obs->result = V14_PRIMARY_TIMEOUT;
#     +    obs->result = V14_PRIMARY_OBSERVED;
#
# is one token, leaves every count intact, and publishes OBSERVED into appendix
# word 7 on a run that never satisfied the completion predicate. The multiset of
# values carries the count with it, so binding the values closes both.
_PRIMARY_RESULTS = (
    "V14_PRIMARY_OBSERVED",
    "V14_PRIMARY_RESET",
    "V14_PRIMARY_FAULT",
    "V14_PRIMARY_TIMEOUT",
)
_PRIMARY_Q_OBSERVATION = {
    "result": _PRIMARY_RESULTS,
    "iterations": ("i", "0U"),
    "qread": ("qread", "qread"),
    "status": ("V14_U32_INVALID", "status"),
    "t_first": ("DWT->CYCCNT", "V14_U32_INVALID"),
}
# The dual-read primaries reload STATUS on every exit, so their observed path
# publishes the measured status rather than the sentinel and their second
# completion guard adds one more publication of each field.
_PRIMARY_DUAL_OBSERVATION = {
    "result": _PRIMARY_RESULTS,
    "iterations": ("i", "0U", "0U", "0U"),
    "qread": ("qread",) * 4,
    "status": ("status",) * 4,
    "t_first": ("DWT->CYCCNT", "V14_U32_INVALID", "V14_U32_INVALID", "V14_U32_INVALID"),
}
_CONVERGE_OBSERVATION = {
    "result": ("result",),
    "iterations": ("iterations",),
    "qread": ("qread",),
    "status": ("status",),
    "t_first": ("V14_U32_INVALID",),
}

OBSERVATION_PRODUCERS = {
    variant: {
        PRIMARY_SYMBOL[variant]: (
            _PRIMARY_Q_OBSERVATION if variant == "Q" else _PRIMARY_DUAL_OBSERVATION
        ),
        CONVERGE_SYMBOL: _CONVERGE_OBSERVATION,
    }
    for variant in VARIANTS
}


def _observation_value_key(value: str, defines: dict[str, int]) -> str:
    """What a stored value *is*, over every spelling that produces it.

    A value that folds to a constant is compared as that constant, so
    ``V14_PRIMARY_OBSERVED``, ``(V14_PRIMARY_OBSERVED)`` and
    ``V14_PRIMARY_OBSERVED + 0U`` are one value here -- the same reading
    ``is_magic_value`` already gives the mailbox magic. What does not fold is a
    local or a register read, and those are compared as the tokens they are.
    """

    folded = _evaluate_constant(value, defines)
    if folded is not None:
        return "0x%08X" % (folded & 0xFFFFFFFF)
    return re.sub(r"\s+", " ", value.strip())


def _observation_text(published: dict[str, tuple[str, ...]]) -> str:
    return (
        ", ".join(
            "%s=[%s]" % (field, ", ".join(values))
            for field, values in sorted(published.items())
        )
        or "no store"
    )

def _observation_field_target(lvalue: str, names: frozenset) -> str | None:
    """The observation field ``lvalue`` designates, or ``None`` for other storage."""

    member = _record_member(lvalue)
    if member is None:
        return None
    head, field = member
    base = _INDEX_RE.sub(" ", _strip_address_of(_CAST_RE.sub(" ", head)))
    mentioned = set(_IDENTIFIER_RE.findall(base))
    if not mentioned or mentioned - names:
        return None
    return field


def observation_record_names(vendor_masked: str) -> frozenset:
    """Every name declared as an observation record or a pointer to one."""

    return frozenset(_OBSERVATION_DECL_RE.findall(vendor_masked))


def verify_observation_contract(
    vendor_masked: str, variant: str, defines: dict[str, int]
) -> None:
    """Refuse an observation record written anywhere the design does not write it.

    The mailbox half of this proof is ``require_authorized_appendix_producers``.
    This is the same proof one hop upstream, and it is made the same way: the
    sites and counts are a contract table, an lvalue that names an observation
    field through a base this gate cannot bind is refused rather than passed
    over, and the record's address is bounded so a write that names no field at
    all -- an alias, a field pointer, a ``memcpy`` -- cannot reach the storage
    behind the table's back.
    """

    declared = observation_record_names(vendor_masked)
    if not declared:
        raise fail("the vendor translation unit declares no %s record" % OBSERVATION_TYPE)
    fields = frozenset(OBSERVATION_FIELDS)
    authorized = OBSERVATION_PRODUCERS[variant]
    for owner, start, stop in function_spans(vendor_masked):
        body = vendor_masked[start:stop]
        names = declared | frozenset(obs_aliases(body))
        published: dict[str, list[str]] = {}
        for site, lvalue, rvalue in assignment_statements(body):
            if _is_declaration(lvalue):
                continue
            member = _record_member(lvalue)
            if member is None or member[1] not in fields:
                continue
            field = _observation_field_target(lvalue, names)
            if field is None:
                raise fail(
                    "%s writes the observation field %s through an lvalue this gate cannot bind "
                    "to an observation record at offset %d: %s"
                    % (
                        owner or "<file scope>",
                        member[1],
                        start + site,
                        re.sub(r"\s+", " ", lvalue.strip())[:40],
                    )
                )
            published.setdefault(field, []).append(
                _observation_value_key(rvalue, defines)
            )
        observed = {field: tuple(sorted(values)) for field, values in published.items()}
        expected = {
            field: tuple(sorted(_observation_value_key(value, defines) for value in values))
            for field, values in authorized.get(owner, {}).items()
        }
        if observed != expected:
            raise fail(
                "the observation record is not published by its authorized producers in %s: "
                "found %s, expected %s"
                % (owner or "<file scope>", _observation_text(observed), _observation_text(expected))
            )

    consumers = frozenset((PRIMARY_SYMBOL[variant], CONVERGE_SYMBOL, OBSERVATION_PUBLISH_SYMBOL))
    for site, operand in address_of_operands(vendor_masked):
        field = _observation_field_target(operand, declared)
        if field in fields:
            raise fail(
                "the vendor translation unit takes the address of the observation field %s at "
                "offset %d: a write through it is a write the producer table cannot see"
                % (field, site)
            )
    # What is left is the record taken *whole*. It is the argument of the three
    # helpers the design gives it and nothing else: bound to a second name, cast,
    # or handed to any other call, it is storage this gate stops being able to
    # account for.
    exempt = set()
    for match in _OBSERVATION_DECL_RE.finditer(vendor_masked):
        exempt.update(range(match.start(1), match.end(1)))
    wanted = {
        match.start(): match
        for match in _IDENTIFIER_RE.finditer(vendor_masked)
        if match.group(0) in declared
        and match.start() not in exempt
        and not _member_base_follows(vendor_masked, match.end())
    }
    enclosing = enclosing_calls(vendor_masked, frozenset(wanted))
    for offset, match in sorted(wanted.items()):
        if enclosing.get(offset) in consumers:
            continue
        raise fail(
            "the vendor translation unit reaches an observation record as whole storage at "
            "offset %d: %s is neither a member access nor an argument of %s"
            % (offset, match.group(0), ", ".join(sorted(consumers)))
        )


def is_magic_value(value: str, defines: dict[str, int]) -> bool:
    """Whether a stored value *is* the 0x5631344D magic, over every spelling.

    The magic is what tells a reader the other 33 words are real, so what
    matters is the number the compiler stores and not the text that produces it.
    ``V14_MAILBOX_VALID + 0U``, ``(V14_MAILBOX_VALID)`` and ``0x5631344DU | 0U``
    all store it, and a count keyed on the bare macro or the bare literal misses
    each of them -- which leaves the "published from more than one site"
    rejection unreachable and lets a second, earlier, unearned magic hand the
    runner a valid-looking frame full of reset sentinels.

    The evaluator this file already trusts for CMD values and NVIC addresses is
    the one that answers here. The two text cases are kept as the fast path.
    """

    token = value.strip()
    if token in defines:
        return defines[token] == MAILBOX_VALID
    try:
        return int(token.rstrip("uU"), 0) == MAILBOX_VALID
    except ValueError:
        pass
    folded = _evaluate_constant(token, defines)
    return folded is not None and (folded & 0xFFFFFFFF) == MAILBOX_VALID


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


# The sites the design gives each appendix word, and the number of stores each
# of them carries. It is a contract table, not an observation: the manifest
# publishes what this gate *found*, and this is what it is allowed to find.
#
# "Every word has a producer" is a weaker claim than it reads as. The gate
# proves a great deal about how each value is produced -- ``require_load_provenance``
# binds ``pre_submit_status`` to the counted STATUS load, ``verify_predicate_shape``
# binds every convergence term to the value its comparison lands on,
# ``verify_publishing_guards`` makes each publishing guard earn its exit -- and
# one unconditional store to the word *downstream* of all that proof bypasses
# every bit of it. Only three words carried independent protection: word 0 by
# its store count, words 9..14 by their owner, word 33 by the magic count. For
# the other twenty-six, ``mailbox[V14_MBOX_CONVERGENCE_RESULT] = V14_CONVERGENCE_SUCCESS``
# written after the convergence tail serialized SUCCESS on a run that timed out.
#
# The counts matter as much as the owners: they are what makes deleting one of
# ``v14_publish_primary``'s three ``first_state`` stores -- the observed one, the
# only one that carries a measurement -- a rejection rather than a word that
# still has two sentinel producers left.
APPENDIX_PRODUCERS = {
    0: (("test_u85", 1),),
    1: (("test_commands", 1),),
    2: (("test_u85", 1),),
    3: (("test_commands", 1),),
    4: (("test_commands", 1),),
    5: (("test_commands", 1),),
    6: (("v14_publish_primary", 1),),
    7: (("v14_publish_primary", 1),),
    8: (("v14_publish_primary", 1),),
    9: (("v14_publish_primary", 2),),
    10: (("v14_publish_primary", 2),),
    11: (("v14_publish_primary", 2),),
    12: (("v14_publish_primary", 3),),
    13: (("v14_publish_primary", 3),),
    14: (("v14_publish_primary", 3),),
    15: (("test_commands", 1),),
    16: (("test_commands", 1),),
    17: (("test_commands", 1), ("v14_publish_failure", 1)),
    18: (("test_commands", 1), ("v14_publish_failure", 1)),
    19: (("test_commands", 1),),
    20: (
        ("v14_publish_cleanup_failure", 1),
        ("v14_publish_failure", 1),
        ("v14_publish_success", 1),
    ),
    21: (
        ("v14_publish_cleanup_failure", 1),
        ("v14_publish_failure", 1),
        ("v14_publish_success", 1),
    ),
    22: (
        ("v14_publish_cleanup_failure", 1),
        ("v14_publish_failure", 1),
        ("v14_publish_success", 1),
    ),
    23: (
        ("v14_publish_cleanup_failure", 1),
        ("v14_publish_failure", 1),
        ("v14_publish_success", 1),
    ),
    24: (("test_u85", 1),),
    25: (("test_u85", 1),),
    26: (("test_u85", 1),),
    27: (("test_u85", 1),),
    28: (("test_u85", 1),),
    29: (("test_commands", 1),),
    30: (("test_commands", 1),),
    31: (("test_commands", 1),),
    32: (("test_commands", 1),),
    33: (("v14_mailbox_publish", 1),),
}


def _producer_text(producers: dict[str, int]) -> str:
    return ", ".join("%s x%d" % (owner, count) for owner, count in sorted(producers.items()))


def require_authorized_appendix_producers(
    vendor_masked: str, defines: dict[str, int]
) -> int:
    """Refuse an appendix word written anywhere the design does not write it.

    ``require_every_appendix_word_produced`` answers "does this word have a
    producer at all", which is the fail-silent direction. This answers "are its
    producers the ones the design gives it", which is the fail-*open* one: a word
    can carry every proof this file makes about it and still be overwritten by a
    second store one line later.

    The mailbox reset is excluded because it writes the sentinel to every word
    rather than an observation. A store this gate cannot pin to a word is refused
    outright: the reset's loop-indexed sentinel store is the only one the frozen
    sources carry, and it is the reset's.
    """

    aliases = mailbox_alias_words(vendor_masked, defines)
    observed: dict[object, dict[str, int]] = {}
    for word, _token, _value, owner in _resolved_mailbox_stores(
        vendor_masked, defines, aliases
    ):
        if owner == MAILBOX_RESET_SYMBOL:
            continue
        counts = observed.setdefault(word, {})
        counts[owner] = counts.get(owner, 0) + 1
    for word, counts in sorted(observed.items(), key=repr):
        if isinstance(word, int) and 0 <= word < APPENDIX_WORDS:
            continue
        raise fail(
            "the vendor translation unit stores outside the 34-word appendix at word %s: %s"
            % (word, _producer_text(counts))
        )
    for index in range(APPENDIX_WORDS):
        authorized = dict(APPENDIX_PRODUCERS[index])
        found = observed.get(index, {})
        if found != authorized:
            raise fail(
                "appendix word %d (%s) is not published by its authorized producers: found "
                "%s, expected %s"
                % (
                    index,
                    APPENDIX_FIELDS[index],
                    _producer_text(found) or "no store outside the mailbox reset",
                    _producer_text(authorized),
                )
            )
    return sum(sum(counts.values()) for counts in observed.values())


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

    scope = file_scope_text(vendor_masked)
    command_roles = pointer_roles(command, defines, scope)
    require_resolved_pointers(command_roles, "command function")
    require_resolved_dereferences(command, defines, command_roles, "the command function")
    require_no_macro_mmio(command, *mmio_macro_table(vendor_masked)[:1], "the command function",
                          mmio_macro_table(vendor_masked)[1])

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

    # Between the submit write and the point the cleanup ordering starts walking,
    # the only rule that ever applied was "exactly one write sets bit 0". A
    # ``write_reg(NPU_REG_CMD, 0)`` immediately after the submit satisfies it and
    # stops the queue, so every timestamp, iteration count and first-observation
    # word published afterwards describes a run that was not running. The window
    # is closed here rather than by widening the ordering walk, because the walk
    # is a proof about the release tail and this is a proof about the measurement.
    submits = submit_write_sites(command, defines, command_roles)
    if len(submits) != 1:
        raise fail(
            "command path does not carry exactly one NPU submit write: %d submit writes"
            % len(submits)
        )
    intruding = tuple(
        site for site in command_cmd_writes if submits[0] < site < history.start()
    )
    if intruding:
        raise fail(
            "a CMD write falls between the submit write and the convergence tail: %d writes, "
            "first at offset %d -- the queue every measured word reports on is transitioned "
            "while it is being measured" % (len(intruding), intruding[0])
        )

    cleanup = command[history.start() :]
    cleanup_raw = command_raw[history.start() :]
    cleanup_roles = pointer_roles(cleanup, defines, scope)
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
RECORD_SYMBOL = "d"


def _record_member(lvalue: str) -> tuple[str, str] | None:
    """``(base, field)`` for the last member access an lvalue makes, or ``None``.

    ``d.variant_id``, ``(&d)->variant_id``, ``alias->variant_id`` and
    ``array[0]->variant_id`` all designate one field of one record, and a rule
    written over the ``d.<field>`` spelling holds for exactly the first of them.
    Read as a bounded scan back from the end rather than as a backtracking
    pattern, because an lvalue is a whole statement's worth of text here and a
    non-greedy head would try every split point in it.
    """

    tail = lvalue.rstrip()
    stop = len(tail)
    cursor = stop
    while cursor > 0 and _NAME_CHARACTER_RE.match(tail[cursor - 1]):
        cursor -= 1
    field = tail[cursor:stop]
    if not field or field[0].isdigit():
        return None
    head = tail[:cursor].rstrip()
    if head.endswith("->"):
        return head[:-2], field
    if head.endswith(".") and not head.endswith(".."):
        return head[:-1], field
    return None


@functools.lru_cache(maxsize=4)
def record_aliases(runner_masked: str) -> tuple[str, ...]:
    """Every name transitively bound to the address of the serialized record.

    A name is an alias when its binding takes the record's address, or when it
    copies a name that already is one. ``last_pmu_diag = d`` is neither -- it is
    a copy of the *value*, and writing through it reaches other storage -- so it
    is not one here either.
    """

    bindings = _bindings(runner_masked)
    dependents, edges = _binding_dependents(bindings)
    budget = _ALIAS_BUDGET_FACTOR * (len(bindings) + edges) + _ALIAS_BUDGET_FLOOR
    aliases: set[str] = set()
    pending = collections.deque(_seeded_bindings(bindings, dependents, RECORD_SYMBOL))
    queued = set(pending)
    steps = 0
    while pending:
        index = pending.popleft()
        queued.discard(index)
        steps += 1
        if steps > budget:
            raise fail(
                "resolving a record alias did not settle within %d steps: the source binds "
                "more aliases than this gate walks" % budget
            )
        name, expr = bindings[index]
        if name == RECORD_SYMBOL or name in aliases:
            continue
        # An initializer this gate could not flatten may take the record's
        # address, so the name it binds is an alias here rather than a name the
        # write-once proof below is free to ignore.
        if expr != UNRESOLVED_INITIALIZER:
            if _MEMBER_ACCESS_RE.search(expr) is not None:
                continue
            stripped = _CAST_RE.sub(" ", expr)
            mentioned = set(_IDENTIFIER_RE.findall(stripped))
            takes_address = "&" in stripped and RECORD_SYMBOL in mentioned
            if not (takes_address or mentioned & aliases):
                continue
        aliases.add(name)
        for dependent in dependents.get(name, ()):
            if dependent not in queued:
                pending.append(dependent)
                queued.add(dependent)
    return tuple(sorted(aliases))


def _record_field_target(lvalue: str, aliases: frozenset) -> str | None:
    """The record field ``lvalue`` designates, or ``None`` when it names another.

    The base is reduced the way every other lvalue in this file is reduced -- the
    casts, the address-of and the subscripts come off -- so what is left is the
    names it reaches. It designates the record exactly when those names are the
    record and its aliases and nothing else.
    """

    member = _record_member(lvalue)
    if member is None:
        return None
    head, field = member
    base = _INDEX_RE.sub(" ", _strip_address_of(_CAST_RE.sub(" ", head)))
    names = set(_IDENTIFIER_RE.findall(base))
    if not names or names - {RECORD_SYMBOL} - aliases:
        return None
    return field


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

    aliases = frozenset(record_aliases(runner_masked))
    found: list[tuple[int, str, object]] = []
    for start, lvalue, rvalue in assignment_statements(runner_masked):
        if _is_declaration(lvalue):
            continue
        field = _record_field_target(lvalue, aliases)
        if field is None:
            continue
        found.append((start, field, resolve_mailbox_word(rvalue, defines, known)))
    return tuple(found)


def require_bindable_record_writes(runner_masked: str) -> None:
    """Refuse a write to an appendix-named field this gate cannot bind to the record.

    ``runner_record_stores`` resolves the lvalues that *do* designate the record.
    This names the ones that do not: a field the appendix owns, written through a
    base nothing here resolves, is either a second name for the record that this
    walk cannot follow or a different object carrying the same field name. Both
    are outside what the write-once proof below covers, so both are refused
    rather than passed over.
    """

    aliases = frozenset(record_aliases(runner_masked))
    appendix = frozenset(APPENDIX_FIELDS)
    lvalues = [(start, lvalue) for start, lvalue, _rvalue in assignment_statements(runner_masked)]
    lvalues.extend(compound_assignment_lvalues(runner_masked))
    for start, lvalue in lvalues:
        if _is_declaration(lvalue):
            continue
        member = _record_member(lvalue)
        if member is None or member[1] not in appendix:
            continue
        if _record_field_target(lvalue, aliases) is None:
            raise fail(
                "the runner writes the appendix field %s through an lvalue this gate cannot "
                "bind to the serialized record at offset %d: %s"
                % (member[1], start, re.sub(r"\s+", " ", lvalue.strip())[:40])
            )


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
    require_bindable_record_writes(runner_masked)
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
    # Write-once means once, and the walk above only counts where a store sits.
    # A store is credited as a *copy* by its rvalue resolving to a mailbox word,
    # so a second store to an already-copied field whose rvalue is a constant is
    # not a copy at all -- it is invisible to ``all_copies``, it is inside the
    # branch so ``outside`` never looks at it, and ``d.variant_id = 0U`` written
    # one line under the proven copy rewrites a published field with every proof
    # above satisfied. Every store to an appendix field is therefore required to
    # be one of the 34 that read the word the wire order gives it.
    forged = [
        (start, field)
        for start, field, word in record_stores
        if field in appendix_fields and word is None
    ]
    if forged:
        raise fail(
            "runner writes the copied appendix field %s from something that is not its mailbox "
            "word at offset %d" % (forged[0][1], forged[0][0])
        )
    # An increment writes the field without ever spelling ``d.<field> =``, and
    # it can be written prefix or postfix, so the lvalue is resolved to the
    # storage it designates rather than matched against one shape.
    record_names = frozenset(record_aliases(runner_masked))
    for offset, lvalue in compound_assignment_lvalues(runner_masked):
        field = _record_field_target(lvalue, record_names)
        if field in appendix_fields:
            raise fail(
                "runner rewrites a copied appendix field through a read-modify-write: "
                "%s at offset %d" % (field, offset)
            )

    # Everything above reads an *lvalue*, so everything above is answered by a
    # write that names no member: a field pointer, a ``memset``, a ``memcpy``.
    # This bounds the storage those lvalues designate instead, and it runs last
    # so a source that breaks one of the named rules is still named by it. The
    # window ends with the function that owns the record: past that the record
    # has been copied out by value and is no longer this proof's subject.
    owning_stop = next(
        (
            stop
            for _name, start, stop in function_spans(runner_masked)
            if start <= close_index < stop
        ),
        len(runner_masked),
    )
    require_record_storage_closed(runner_masked, (close_index, owning_stop))
    # The vendor-only indirect-call exemption ends at the function that owns the
    # record: the stock runner's file-scope ``irq_handler_t`` is not an attack,
    # and a function pointer declared inside the diagnostic is.
    owning_start = next(
        (
            start
            for _name, start, stop in function_spans(runner_masked)
            if start <= close_index < stop
        ),
        0,
    )
    require_runner_diagnostic_closed(runner_masked, (owning_start, owning_stop))

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


# ---------------------------------------------------------------------------
# The linked image
#
# Everything above reads characters. This reads the instructions the CPU will
# execute, and it exists because the claims it makes cannot be made from text:
# dominance is a property of a control-flow graph, and the source has none.
#
# The parsing front end is the one V13 took to the board rather than a new one.
# V12's parse_functions keeps objdump's encoding column in ``text``, which is
# why V13 strips it in _split_code_and_literals; reusing both is what keeps this
# module's mnemonic classification independent of objdump's flags.
# ---------------------------------------------------------------------------

U85_BASE_ADDRESS = 0x50004000
DWT_BASE_ADDRESS = 0xE0001000
DWT_CYCCNT_ADDRESS = DWT_BASE_ADDRESS + 4
MMIO_REGION_SIZE = 0x1000

NPU_REGISTER_AT_OFFSET = {
    0x00: "ID",
    0x04: "STATUS",
    0x08: "CMD",
    0x0C: "RESET",
    0x10: "QBASE_LSB",
    0x14: "QBASE_MSB",
    0x18: "QREAD",
    0x20: "QSIZE",
}
QUEUE_PROGRAMMING_ROLES = ("QBASE_LSB", "QBASE_MSB", "QSIZE")

_CONDITIONS = (
    "eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le",
)
_ELF_UNCOND_BRANCH = re.compile(r"^b(?:\.[nw])?\s")
_ELF_COND_BRANCH = re.compile(r"^b(?:%s)(?:\.[nw])?\s" % "|".join(_CONDITIONS))
_ELF_CBZ = re.compile(r"^cbn?z\s")
_ELF_CALL = re.compile(r"^bl(?:\.[nw])?\s|^blx\s")
_ELF_IT = re.compile(r"^(it[te]{0,3})\s+(?:%s)\b" % "|".join(_CONDITIONS))
_ELF_RETURN = re.compile(r"^(?:bx\s+lr\b|pop\s*\{[^}]*\bpc\b)")
_ELF_INDIRECT = re.compile(r"^(?:bx|blx)\s+(?!lr\b)\w|^(?:tbb|tbh)\b")
_ELF_LOAD_LITERAL = re.compile(r"^ldr(?:\.[nw])?\s+(\w+),\s*\[pc[^\]]*\]")
_ELF_MOVW = re.compile(r"^movw\s+(\w+),\s*#(\d+)")
_ELF_MOVT = re.compile(r"^movt\s+(\w+),\s*#(\d+)")
_ELF_MOV_REG = re.compile(r"^mov(?:\.[nw])?\s+(\w+),\s*(\w+)\s*$")
_ELF_MOV_IMM = re.compile(r"^movs?(?:\.[nw])?\s+(\w+),\s*#(\d+)")
_ELF_MEMORY = re.compile(
    r"^(ldr|str)(?:b|h)?(?:\.[nw])?\s+(\w+),\s*\[(\w+)(?:,\s*#(-?\d+))?\]"
)
_ELF_WRITEBACK = re.compile(r"\][ \t]*!|\],\s*#")
_ELF_DESTINATION = re.compile(r"^(\w+?)(?:\.[nw])?\s+(\w+)\s*,")
_ELF_TEST_MASK = re.compile(r"^tst(?:\.[nw])?\s+(\w+),\s*#(\d+)")
# ``tst`` is not the only way to test a mask: at -O1 GCC also writes
# ``ands rX, rS, #mask``, which sets the flags the branch reads and happens to
# park the result in a register nobody uses. A rule that knew only ``tst`` would
# have read the reset and cmd_end checks as absent.
_ELF_MASK_TEST = re.compile(r"^(?:tst|ands)(?:\.[nw])?\s+(?:(\w+),\s*)?(\w+),\s*#(\d+)")


def _elf_mask_test(text: str):
    """``(tested register, mask)`` for a flag-setting mask test, or ``None``."""

    hit = _ELF_MASK_TEST.match(text)
    if hit is None:
        return None
    # ``tst rS, #m`` tests rS; ``ands rD, rS, #m`` tests rS and writes rD.
    return (hit.group(2), int(hit.group(3)))
# Instructions whose first operand is read, not written. Reading them as writes
# is what made a ``tst`` look like it clobbered the register it tests.
_ELF_NON_WRITING = frozenset(
    ("cmp", "cmn", "tst", "teq", "str", "strb", "strh", "strd", "push", "stm", "stmia", "stmdb")
)


def _elf_written_register(text: str) -> str | None:
    hit = _ELF_DESTINATION.match(text)
    if hit is None or hit.group(1).lower() in _ELF_NON_WRITING:
        return None
    return hit.group(2)


def _elf_front_end():
    """V12's row parser and V13's encoding-column strip, imported on demand.

    Imported here rather than at module scope so the source-fixture contract
    keeps working in a tree that has only this file.
    """

    try:
        from check_pmu_completion_poll_v12 import parse_functions
        from check_pmu_completion_poll_count_v13 import _split_code_and_literals
    except ImportError as exc:  # pragma: no cover - environment, not contract
        raise fail("linked-image analysis needs the frozen V12/V13 gates: %s" % exc)
    return parse_functions, _split_code_and_literals


def elf_function(disassembly_text: str, name: str):
    """``(instructions, literal pool)`` for one function of the linked image."""

    parse_functions, split_code_and_literals = _elf_front_end()
    headers = re.findall(
        r"(?m)^[0-9a-fA-F]+\s+<%s>:\s*$" % re.escape(name), disassembly_text
    )
    if len(headers) != 1:
        raise fail(
            "linked image carries %d definitions of %s: expected exactly one"
            % (len(headers), name)
        )
    functions = parse_functions(disassembly_text)
    if name not in functions:
        raise fail("linked image has no %s to analyse" % name)
    code, literals = split_code_and_literals(functions[name])
    if not code:
        raise fail("linked image function %s disassembled to nothing" % name)
    return code, literals


def elf_cfg(code) -> tuple[tuple[int, ...], ...]:
    """Successor indices, refusing every control transfer this gate cannot model.

    A predicated instruction is not a branch. It either takes effect or does
    not, and control falls through either way, so an IT block is straight line
    here -- and predication is refused separately, at the instructions a proof
    actually depends on running.
    """

    index_of = {insn.addr: index for index, insn in enumerate(code)}
    successors: list[tuple[int, ...]] = []
    for index, insn in enumerate(code):
        text = insn.text
        fallthrough = (index + 1,) if index + 1 < len(code) else ()
        if _ELF_INDIRECT.match(text):
            raise fail(
                "indirect control transfer at 0x%08x is not modelled: %s" % (insn.addr, text)
            )
        if _ELF_RETURN.match(text):
            successors.append(())
        elif _ELF_CALL.match(text):
            successors.append(fallthrough)
        elif _ELF_COND_BRANCH.match(text) or _ELF_CBZ.match(text):
            if insn.target is None or insn.target not in index_of:
                raise fail(
                    "conditional branch at 0x%08x leaves the function: %s" % (insn.addr, text)
                )
            successors.append((index_of[insn.target],) + fallthrough)
        elif _ELF_UNCOND_BRANCH.match(text):
            if insn.target is None or insn.target not in index_of:
                raise fail(
                    "branch at 0x%08x leaves the function: %s" % (insn.addr, text)
                )
            successors.append((index_of[insn.target],))
        else:
            successors.append(fallthrough)
    return tuple(successors)


def _predecessors(successors) -> list[list[int]]:
    preds: list[list[int]] = [[] for _ in successors]
    for index, outs in enumerate(successors):
        for out in outs:
            preds[out].append(index)
    return preds


def elf_dominators(successors, entry: int = 0) -> tuple[frozenset, ...]:
    """``dom[i]`` is every index that lies on all paths from entry to ``i``.

    An index no path reaches keeps the full set, which makes it dominated by
    everything and therefore evidence for nothing -- the reachability question
    is asked separately by whoever cares about it.
    """

    count = len(successors)
    preds = _predecessors(successors)
    everything = frozenset(range(count))
    dominators = [everything] * count
    dominators[entry] = frozenset((entry,))
    changed = True
    while changed:
        changed = False
        for index in range(count):
            if index == entry or not preds[index]:
                continue
            updated = frozenset.intersection(
                *(dominators[pred] for pred in preds[index])
            ) | {index}
            if updated != dominators[index]:
                dominators[index] = updated
                changed = True
    return tuple(dominators)


def elf_natural_loop(successors, latch: int, head: int) -> frozenset:
    """The body of the loop closed by ``latch -> head``.

    Not ``range(head, latch + 1)``: at -O1 the convergence tail is rotated, so
    its entry jumps into the middle and the increment block sits at a *lower*
    index than the header. Reading the body as an address range made it empty,
    and an empty body satisfies every per-iteration rule there is.
    """

    preds = _predecessors(successors)
    loop = {head, latch}
    pending = [latch]
    while pending:
        node = pending.pop()
        for pred in preds[node]:
            if pred not in loop:
                loop.add(pred)
                pending.append(pred)
    return frozenset(loop)


def elf_predicated(code) -> frozenset:
    """Indices an IT block makes conditional."""

    covered: set[int] = set()
    for index, insn in enumerate(code):
        hit = _ELF_IT.match(insn.text)
        if hit is None:
            continue
        for step in range(1, len(hit.group(1))):
            if index + step < len(code):
                covered.add(index + step)
    return frozenset(covered)


def elf_register_values(code, literals, successors) -> list[dict]:
    """Register values known on entry to each instruction, by fixpoint.

    A value survives a merge only when every predecessor agrees on it, so a
    base materialised on one path and left alone on another is unknown here
    rather than assumed to be the one this gate would like it to be.
    """

    pool = {address: word for address, word in literals}
    count = len(code)
    preds = _predecessors(successors)
    entry_state: list[dict | None] = [None] * count
    exit_state: list[dict | None] = [None] * count
    changed = True
    while changed:
        changed = False
        for index in range(count):
            if not preds[index]:
                state: dict = {}
            else:
                known = [exit_state[pred] for pred in preds[index] if exit_state[pred] is not None]
                if not known:
                    continue
                state = dict(known[0])
                for other in known[1:]:
                    state = {
                        name: value for name, value in state.items() if other.get(name) == value
                    }
            if entry_state[index] != state:
                entry_state[index] = state
                changed = True
            updated = _elf_transfer(dict(state), code[index], pool)
            if exit_state[index] != updated:
                exit_state[index] = updated
                changed = True
    return [state if state is not None else {} for state in entry_state]


def _elf_transfer(state: dict, insn, pool: dict) -> dict:
    text = insn.text
    literal = _ELF_LOAD_LITERAL.match(text)
    if literal is not None:
        word = pool.get(insn.target) if insn.target is not None else None
        if word is None:
            state.pop(literal.group(1), None)
        else:
            state[literal.group(1)] = word
        return state
    for pattern, combine in (
        (_ELF_MOVW, lambda old, imm: imm),
        (_ELF_MOVT, lambda old, imm: ((old or 0) & 0xFFFF) | (imm << 16)),
        (_ELF_MOV_IMM, lambda old, imm: imm),
    ):
        hit = pattern.match(text)
        if hit is not None:
            state[hit.group(1)] = combine(state.get(hit.group(1)), int(hit.group(2)))
            return state
    copy = _ELF_MOV_REG.match(text)
    if copy is not None:
        source = state.get(copy.group(2))
        if source is None:
            state.pop(copy.group(1), None)
        else:
            state[copy.group(1)] = source
        return state
    memory = _ELF_MEMORY.match(text)
    written = _elf_written_register(text)
    if written is not None:
        state.pop(written, None)
    if memory is not None and _ELF_WRITEBACK.search(text):
        state.pop(memory.group(3), None)  # the base moved; it is no longer that value
    return state


def elf_in_modelled_region(address: int) -> bool:
    return (
        U85_BASE_ADDRESS <= address < U85_BASE_ADDRESS + MMIO_REGION_SIZE
        or DWT_BASE_ADDRESS <= address < DWT_BASE_ADDRESS + MMIO_REGION_SIZE
    )


def elf_mmio_accesses(code, states) -> tuple[tuple[int, str, bool], ...]:
    """``(index, role, is_write)`` for every access this gate can name.

    An access whose base is unresolved reaches nothing nameable and is not
    counted. It is not refused here either: whether an unresolved access may
    exist where it does is a confinement question, asked by the rules that own
    the region rather than by the decoder.
    """

    found: list[tuple[int, str, bool]] = []
    for index, insn in enumerate(code):
        hit = _ELF_MEMORY.match(insn.text)
        if hit is None:
            continue
        base = states[index].get(hit.group(3))
        if base is None:
            continue
        address = base + int(hit.group(4) or 0)
        if not elf_in_modelled_region(address):
            continue
        if _ELF_WRITEBACK.search(insn.text):
            raise fail(
                "writeback addressing over the modelled region at 0x%08x is not modelled: %s"
                % (insn.addr, insn.text)
            )
        if U85_BASE_ADDRESS <= address < U85_BASE_ADDRESS + MMIO_REGION_SIZE:
            offset = address - U85_BASE_ADDRESS
            role = NPU_REGISTER_AT_OFFSET.get(offset, "NPU+0x%02X" % offset)
        elif address == DWT_CYCCNT_ADDRESS:
            role = "DWT_CYCCNT"
        else:
            role = "DWT+0x%02X" % (address - DWT_BASE_ADDRESS)
        found.append((index, role, hit.group(1) == "str"))
    return tuple(found)


PRE_PROGRAM_MAILBOX_WORD = 2
_GATE_MASKS = (STATUS_STATE, STATUS_RESET, STATUS_FAULT_MASK)


MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"


def elf_symbol_address(nm_text: str, symbol: str) -> int:
    """The one address ``nm`` gives this symbol, or a refusal."""

    hits = [
        int(parts[0], 16)
        for parts in (line.split() for line in nm_text.splitlines())
        if len(parts) == 3 and parts[2] == symbol
    ]
    if len(hits) != 1:
        raise fail("nm gives %s %d addresses: expected exactly one" % (symbol, len(hits)))
    return hits[0]


def _elf_gate_index(code, states, accesses, mailbox_address: int) -> int:
    """The pre-program gate, found by what it does rather than by where it is.

    A STATUS load is the gate when its value is published to the pre-program
    mailbox word and then tested against the three masks the design gates on.
    Taking the first STATUS load instead would have picked the frozen vendor's
    reset spin, which reads STATUS in a loop of its own a few instructions
    later.

    The publication is checked against the address ``nm`` gives the mailbox, not
    against a displacement. A store at offset 8 of some unresolved pointer is
    not evidence that the pre-program word was written, and reading it as such
    let a mutated image keep its gate by losing the mailbox base.
    """

    candidates = []
    for index, role, is_write in accesses:
        if role != "STATUS" or is_write:
            continue
        register = _elf_written_register(code[index].text)
        if register is None:
            continue
        published = False
        masks = set()
        for step in range(index + 1, min(index + 24, len(code))):
            text = code[step].text
            store = _ELF_MEMORY.match(text)
            if store is not None and store.group(1) == "str" and store.group(2) == register:
                base = states[step].get(store.group(3))
                if (
                    base is not None
                    and base + int(store.group(4) or 0)
                    == mailbox_address + 4 * PRE_PROGRAM_MAILBOX_WORD
                ):
                    published = True
            test = _ELF_TEST_MASK.match(text)
            if test is not None and test.group(1) == register:
                masks.add(int(test.group(2)))
            if _elf_written_register(text) == register:
                break  # the loaded value is gone; anything after tests something else
        if published and set(_GATE_MASKS) <= masks:
            candidates.append(index)
    if len(candidates) != 1:
        raise fail(
            "linked image does not carry exactly one pre-program gate: %d STATUS loads publish "
            "the pre-program mailbox word and test all of state, reset and fault"
            % len(candidates)
        )
    return candidates[0]


def verify_pre_run_dominance(
    disassembly_text: str, nm_text: str, entry_symbol: str | None = None
) -> dict:
    """Bind the two claims the source gate deliberately does not make.

    The source gate proves the gate exists and is shaped right. This proves it
    runs before the queue is programmed on *every* path, which is what the
    design asked for and what character order cannot decide -- the frozen
    vendor's eU85_TEST0 branch writes QBASE_LSB earlier in the file than the
    design's programming and never on the measured path.
    """

    # Resolved here because the symbol constant is declared with the source
    # contract further down; the default is not a second opinion about it.
    entry_symbol = entry_symbol or ENTRY_SYMBOL
    code, literals = elf_function(disassembly_text, entry_symbol)
    successors = elf_cfg(code)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)
    dominators = elf_dominators(successors)
    predicated = elf_predicated(code)

    mailbox_address = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
    gate = _elf_gate_index(code, states, accesses, mailbox_address)
    if gate in predicated:
        raise fail("the pre-program gate is predicated: it may not run at all")

    programming = [
        index for index, role, is_write in accesses if is_write and role in QUEUE_PROGRAMMING_ROLES
    ]
    if not programming:
        raise fail("linked image programs no queue register in %s" % entry_symbol)
    undominated = [index for index in programming if gate not in dominators[index]]
    if undominated:
        raise fail(
            "the pre-program gate does not dominate queue programming: %d of %d writes are "
            "reachable without it, first at 0x%08x"
            % (len(undominated), len(programming), code[undominated[0]].addr)
        )

    # And nothing may start the NPU in between. A CMD write only transitions the
    # state when it sets bit 0, so the value is read rather than the register.
    starts = []
    for index, role, is_write in accesses:
        if role != "CMD" or not is_write:
            continue
        if gate not in dominators[index]:
            continue
        if not any(index in dominators[write] for write in programming):
            continue
        source = _ELF_MEMORY.match(code[index].text).group(2)
        value = states[index].get(source)
        if value is None or value & 1:
            starts.append((index, value))
    if starts:
        index, value = starts[0]
        raise fail(
            "a CMD write between the pre-program gate and queue programming may start the NPU: "
            "0x%08x writes %s"
            % (code[index].addr, "an unresolved value" if value is None else "0x%08X" % value)
        )

    return {
        "entry_symbol": entry_symbol,
        "mailbox_address": "0x%08X" % mailbox_address,
        "gate_address": "0x%08X" % code[gate].addr,
        "queue_programming_writes": len(programming),
        "queue_programming_addresses": ["0x%08X" % code[i].addr for i in programming],
        "pre_program_gate_dominates_queue_programming": True,
        "no_state_transition_between_gate_and_programming": True,
    }


def verify_primary_loop_image(disassembly_text: str, variant: str) -> dict:
    """What the measured loop actually does, per iteration, in the built image."""

    helper = PRIMARY_SYMBOL[variant]
    code, literals = elf_function(disassembly_text, helper)
    successors = elf_cfg(code)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)

    # A back edge is one whose target dominates its source, not merely one that
    # points at a lower address: these helpers end with a shared epilogue, and
    # the branches into it go backwards through the listing without looping.
    dominators = elf_dominators(successors)
    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail(
            "the %s primary helper does not carry exactly one loop: %d back edges"
            % (variant, len(back_edges))
        )
    latch, head = back_edges[0]
    body = elf_natural_loop(successors, latch, head)

    in_loop = [(index, role, is_write) for index, role, is_write in accesses if index in body]
    expected = {"Q": ("QREAD",), "QS": ("QREAD", "STATUS"), "SQ": ("STATUS", "QREAD")}[variant]
    order = tuple(role for _index, role, is_write in in_loop if not is_write)
    if order != expected:
        raise fail(
            "the %s primary loop reads %s per iteration: the variant is defined as %s"
            % (variant, " then ".join(order) or "nothing", " then ".join(expected))
        )
    if any(is_write for _index, _role, is_write in in_loop):
        raise fail("the %s primary loop writes MMIO per iteration" % variant)
    for index in body:
        text = code[index].text
        if _ELF_CALL.match(text):
            raise fail("the %s primary loop calls out per iteration: %s" % (variant, text))
        store = _ELF_MEMORY.match(text)
        if store is not None and store.group(1) == "str":
            raise fail("the %s primary loop stores per iteration: %s" % (variant, text))

    # Which register each of the loop's loads landed in, so the tests below are
    # tied to the load this iteration took rather than to any register that
    # happens to hold the right number.
    load_register = {}
    for index, role, is_write in in_loop:
        if not is_write:
            load_register[role] = _elf_written_register(code[index].text)

    fault_priority = {}
    if variant != "Q":
        status_register = load_register.get("STATUS")
        qread_register = load_register.get("QREAD")
        tests = {}
        for index in body:
            test = _elf_mask_test(code[index].text)
            if test is not None and test[0] == status_register:
                tests.setdefault(test[1], index)
        for mask, label in ((STATUS_RESET, "reset"), (STATUS_FAULT_MASK, "fault")):
            if mask not in tests:
                raise fail(
                    "the %s primary loop does not test %s (0x%03X) on the STATUS it loaded"
                    % (variant, label, mask)
                )
        # Completion is decided by the queue cursor and by cmd_end, and both have
        # to sit downstream of the reset and fault exits -- a run that faulted
        # must not be reported as a completion first.
        completion = [
            index
            for index in body
            if (
                _elf_mask_test(code[index].text) == (status_register, STATUS_CMD_END)
                or re.match(r"^cmp(?:\.[nw])?\s+%s\s*," % re.escape(qread_register or "\0"), code[index].text)
            )
        ]
        if not completion:
            raise fail("the %s primary loop decides completion on neither QREAD nor cmd_end" % variant)
        for mask, label in ((STATUS_RESET, "reset"), (STATUS_FAULT_MASK, "fault")):
            guard = tests[mask]
            late = [index for index in completion if guard not in dominators[index]]
            if late:
                raise fail(
                    "the %s primary loop decides completion without the %s check: 0x%08x is "
                    "reachable without 0x%08x"
                    % (variant, label, code[late[0]].addr, code[guard].addr)
                )
        # irq_raised is recorded, never an exit. Letting it end the loop would
        # measure the interrupt rather than the completion.
        for index in body:
            test = _elf_mask_test(code[index].text)
            if test == (status_register, STATUS_IRQ_RAISED):
                raise fail(
                    "the %s primary loop tests irq_raised at 0x%08x: bit 1 is observed, not an exit"
                    % (variant, code[index].addr)
                )
        fault_priority = {
            "reset_test": "0x%08X" % code[tests[STATUS_RESET]].addr,
            "fault_test": "0x%08X" % code[tests[STATUS_FAULT_MASK]].addr,
            "completion_tests": ["0x%08X" % code[i].addr for i in completion],
        }

    qsize = [index for index, role, _w in accesses if role == "QSIZE"]
    if qsize:
        raise fail(
            "the %s primary helper accesses QSIZE at 0x%08x: the snapshot is taken before submit"
            % (variant, code[qsize[0]].addr)
        )
    timestamps = [index for index, role, _w in accesses if role == "DWT_CYCCNT"]
    if any(index in body for index in timestamps):
        raise fail("the %s primary loop timestamps per iteration" % variant)

    return {
        "helper": helper,
        "loop_reads_in_order": list(order),
        "loop_instruction_count": len(body),
        "loop_mmio_reads_per_iteration": len(order),
        "qsize_accesses": 0,
        "timestamp_reads_outside_the_loop": len(timestamps),
        # Empty for Q, which has no STATUS in its loop to order anything against.
        "fault_priority": fault_priority,
        # Checked where there is a STATUS load in the loop to check it on. Q has
        # none, so the claim is vacuous there and says so rather than reading as
        # a proof somebody made.
        "irq_raised_exit_scope": (
            "no STATUS in the loop" if variant == "Q" else "checked: irq_raised drives no exit"
        ),
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
    parser.add_argument(
        "--real-elf",
        action="store_true",
        help="prove the linked-image claims instead of the source contract",
    )
    parser.add_argument("--objdump-text", help="path to objdump -d of the linked image")
    parser.add_argument("--nm-text", help="path to nm -n of the linked image")
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


_ELF_ANNOTATION = re.compile(r"\s*(?:@.*|<[^>]*>.*)$")


def _elf_normalized(insn) -> str:
    """One instruction with objdump's commentary removed.

    The commentary is where the helper's own name appears, so leaving it in
    would make QS and SQ differ on every branch simply for being called
    different things.
    """

    return re.sub(r"\s+", " ", _ELF_ANNOTATION.sub("", insn.text)).strip()


def _elf_relocatable(code) -> tuple[str, ...]:
    """Each instruction with branch targets read as positions, not addresses.

    The convergence helper is linked at a different address in each variant --
    Q's primary helper is shorter, so everything after it shifts -- and every
    branch inside it then differs by that shift. Comparing raw text would call
    three identical tails three different programs; comparing a raw object
    digest would do the same. What has to match is the instruction and, where it
    branches, which instruction it branches to.
    """

    index_of = {insn.addr: index for index, insn in enumerate(code)}
    rendered = []
    for insn in code:
        text = _elf_normalized(insn)
        if insn.target is not None and insn.target in index_of:
            text = "%s ->#%d" % (text.split()[0], index_of[insn.target])
        rendered.append(text)
    return tuple(rendered)


def _elf_status_bits_tested(code, body, status_register) -> set:
    """Every STATUS bit the loop body decides on, however GCC spelled the test.

    ``-O1`` merges ``cmd_end`` and ``irq_raised`` into one ``and rD, rS, #0x22``
    followed by ``cmp rD, #0x22``, so a rule that only counted single-bit tests
    would report the design's four-condition predicate as two conditions.
    """

    bits = 0
    merged = re.compile(r"^and(?:s)?(?:\.[nw])?\s+(\w+),\s*(\w+),\s*#(\d+)")
    for index in body:
        test = _elf_mask_test(code[index].text)
        if test is not None and test[0] == status_register:
            bits |= test[1]
            continue
        hit = merged.match(code[index].text)
        if hit is not None and hit.group(2) == status_register:
            destination, mask = hit.group(1), int(hit.group(3))
            for step in range(index + 1, min(index + 4, len(code))):
                compare = re.match(
                    r"^cmp(?:\.[nw])?\s+%s\s*,\s*#(\d+)" % re.escape(destination),
                    code[step].text,
                )
                if compare is not None:
                    bits |= mask
                    break
    return bits


def verify_convergence_tail_image(objdump_text: str) -> dict:
    """The common tail, as the image runs it.

    The design joins every variant to one bounded tail whose iteration reads
    QREAD then STATUS and declares convergence only when a single tuple carries
    all four conditions. Accumulating them across iterations would report a
    convergence that never happened at one instant, which is the thing the tail
    exists to avoid.
    """

    code, literals = elf_function(objdump_text, CONVERGE_SYMBOL)
    successors = elf_cfg(code)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)
    dominators = elf_dominators(successors)

    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail(
            "the convergence tail does not carry exactly one loop: %d back edges" % len(back_edges)
        )
    latch, head = back_edges[0]
    body = elf_natural_loop(successors, latch, head)

    in_loop = [(index, role, is_write) for index, role, is_write in accesses if index in body]
    order = tuple(role for _index, role, is_write in in_loop if not is_write)
    if order != ("QREAD", "STATUS"):
        raise fail(
            "the convergence tail reads %s per iteration: the tail order is fixed as QREAD then "
            "STATUS for every variant" % (" then ".join(order) or "nothing")
        )
    if any(is_write for _index, _role, is_write in in_loop):
        raise fail("the convergence tail writes MMIO per iteration")
    for index in body:
        text = code[index].text
        if _ELF_CALL.match(text):
            raise fail("the convergence tail calls out per iteration: %s" % text)
        store = _ELF_MEMORY.match(text)
        if store is not None and store.group(1) == "str":
            raise fail("the convergence tail stores per iteration: %s" % text)
    if any(role in ("QSIZE", "DWT_CYCCNT") for _index, role, _w in in_loop):
        raise fail("the convergence tail reaches QSIZE or the cycle counter per iteration")

    status_register = next(
        _elf_written_register(code[index].text)
        for index, role, is_write in in_loop
        if role == "STATUS" and not is_write
    )
    bits = _elf_status_bits_tested(code, body, status_register)
    required = {
        "cmd_end_reached": STATUS_CMD_END,
        "irq_raised": STATUS_IRQ_RAISED,
        "state": STATUS_STATE,
        "reset_status": STATUS_RESET,
    }
    for label, mask in required.items():
        if not bits & mask:
            raise fail(
                "the convergence tail never decides on %s (0x%03X): the tail requires all four "
                "conditions in one tuple" % (label, mask)
            )
    if not bits & STATUS_FAULT_MASK:
        raise fail("the convergence tail never decides on the vendor fault mask")

    bound = [
        int(hit.group(2))
        for index in range(len(code))
        if index not in body
        for hit in (_ELF_MOVW.match(code[index].text) or _ELF_MOV_IMM.match(code[index].text),)
        if hit is not None
    ]
    if ITERATION_BOUND not in bound:
        raise fail(
            "the convergence tail does not materialise the %d iteration bound outside its loop"
            % ITERATION_BOUND
        )

    return {
        "helper": CONVERGE_SYMBOL,
        "loop_reads_in_order": list(order),
        "loop_instruction_count": len(body),
        "status_bits_decided": "0x%03X" % bits,
        "iteration_bound": ITERATION_BOUND,
        "per_iteration_stores": 0,
    }


def verify_common_tail_is_shared(images: dict) -> dict:
    """One tail, three variants, differing only by where it was linked."""

    rendered = {}
    for variant, text in sorted(images.items()):
        code, _literals = elf_function(text, CONVERGE_SYMBOL)
        rendered[variant] = _elf_relocatable(code)
    shapes = {variant: _sha256_text("\n".join(rows)) for variant, rows in rendered.items()}
    if len(set(shapes.values())) != 1:
        first = sorted(rendered)[0]
        for variant in sorted(rendered):
            if rendered[variant] == rendered[first]:
                continue
            difference = next(
                (
                    "#%d %s against %s" % (index, left, right)
                    for index, (left, right) in enumerate(zip(rendered[first], rendered[variant]))
                    if left != right
                ),
                "a different instruction count",
            )
            raise fail(
                "the convergence tail is not shared: %s and %s differ at %s"
                % (first, variant, difference)
            )
    return {
        "helper": CONVERGE_SYMBOL,
        "variants": sorted(rendered),
        "instructions": len(next(iter(rendered.values()))),
        "relocation_invariant_sha256": next(iter(shapes.values())),
        "shared_by_every_variant": True,
    }


def verify_read_order_equivalence(qs_text: str, sq_text: str) -> dict:
    """QS and SQ differ in read order and in nothing else the image can show.

    This is the claim the campaign rests on. If the two helpers differed
    anywhere else -- a bound, a predicate, an exit, an extra effect -- then a
    difference in what they observe would have a second explanation, and the
    read-order result would not be a read-order result.
    """

    qs, _ = elf_function(qs_text, PRIMARY_SYMBOL["QS"])
    sq, _ = elf_function(sq_text, PRIMARY_SYMBOL["SQ"])
    if len(qs) != len(sq):
        raise fail(
            "the QS and SQ helpers are not the same length: %d against %d instructions"
            % (len(qs), len(sq))
        )
    if elf_cfg(qs) != elf_cfg(sq):
        raise fail("the QS and SQ helpers do not share one control-flow graph")

    differing = [
        index
        for index, (left, right) in enumerate(zip(qs, sq))
        if _elf_normalized(left) != _elf_normalized(right)
    ]
    if len(differing) != 2:
        raise fail(
            "the QS and SQ helpers differ at %d instructions: the variants are defined to "
            "differ at exactly the two loads" % len(differing)
        )
    first, second = differing
    if second != first + 1:
        raise fail("the QS and SQ helpers differ at non-adjacent instructions")
    if not (
        _elf_normalized(qs[first]) == _elf_normalized(sq[second])
        and _elf_normalized(qs[second]) == _elf_normalized(sq[first])
    ):
        raise fail(
            "the two instructions QS and SQ differ at are not each other's swap: %s / %s "
            "against %s / %s"
            % (
                _elf_normalized(qs[first]),
                _elf_normalized(qs[second]),
                _elf_normalized(sq[first]),
                _elf_normalized(sq[second]),
            )
        )
    return {
        "instructions": len(qs),
        "differing_instructions": len(differing),
        "swapped_at": ["0x%08X" % qs[first].addr, "0x%08X" % qs[second].addr],
        "qs_reads_first": _elf_normalized(qs[first]),
        "sq_reads_first": _elf_normalized(sq[first]),
        "differ_only_in_read_order": True,
    }


MAILBOX_PUBLISH_SYMBOL = "v14_mailbox_publish"
MAILBOX_VALID_WORD = APPENDIX_WORDS - 1


def verify_mailbox_publication_image(objdump_text: str, nm_text: str) -> dict:
    """The verdict channel cannot be forged: one store of the magic, in one place.

    This is the claim that matters about integrity, and it replaces one this
    contract used to state about the vendor's return code. The runner reads the
    appendix only when the magic word is present, so a second store of the magic
    anywhere in the image -- on a path that never filled the tuple -- would hand
    the host a record it never wrote. The return code is not that channel: the
    frozen vendor rewrites it after the command function returns, by design, and
    it only raises a telemetry flag on the host.
    """

    parse_functions, split_code_and_literals = _elf_front_end()
    mailbox = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
    target = mailbox + 4 * MAILBOX_VALID_WORD
    stores = []
    unmodelled = []
    for name, rows in parse_functions(objdump_text).items():
        code, literals = split_code_and_literals(rows)
        if not code:
            continue
        try:
            successors = elf_cfg(code)
        except GateError:
            # A function this gate cannot model is one it cannot clear either.
            # Where such a function names the magic, that is recorded as the
            # limit of this proof rather than argued away: the runner's command
            # dispatcher compares against the magic and reaches it through a
            # jump table, and no rule here decodes one.
            #
            # Refusing outright would refuse the real image; claiming the
            # whole-image count anyway would be the overclaim this contract
            # keeps finding in itself. So the count is scoped, and the scope is
            # published beside it.
            if any(word == MAILBOX_VALID for _addr, word in literals):
                unmodelled.append(name)
            continue
        states = elf_register_values(code, literals, successors)
        for index, insn in enumerate(code):
            hit = _ELF_MEMORY.match(insn.text)
            if hit is None or hit.group(1) != "str":
                continue
            if states[index].get(hit.group(2)) != MAILBOX_VALID:
                continue
            base = states[index].get(hit.group(3))
            address = None if base is None else base + int(hit.group(4) or 0)
            stores.append((name, insn, address))

    if len(stores) != 1:
        raise fail(
            "the modelled functions store the mailbox magic %d times: it is published once, by %s"
            % (len(stores), MAILBOX_PUBLISH_SYMBOL)
        )
    name, insn, address = stores[0]
    if name != MAILBOX_PUBLISH_SYMBOL:
        raise fail(
            "the mailbox magic is stored by %s rather than %s" % (name, MAILBOX_PUBLISH_SYMBOL)
        )
    if address != target:
        raise fail(
            "the mailbox magic is stored to %s rather than the mailbox validity word 0x%08X"
            % ("an unresolved address" if address is None else "0x%08X" % address, target)
        )

    # The tuple has to be visible before the word that says it is there.
    code, literals = elf_function(objdump_text, MAILBOX_PUBLISH_SYMBOL)
    publish = next(i for i, row in enumerate(code) if row.addr == insn.addr)
    if not any(row.mnemonic == "dsb" for row in code[:publish]):
        raise fail("the mailbox magic is published without a barrier before it")
    if not any(row.mnemonic == "dsb" for row in code[publish + 1 :]):
        raise fail("the mailbox magic is published without a barrier after it")

    return {
        "publisher": name,
        "magic_store_address": "0x%08X" % insn.addr,
        "mailbox_validity_word_address": "0x%08X" % target,
        "magic_stores_in_the_modelled_functions": len(stores),
        "fenced_both_sides": True,
        # Named for the scope it is taken over, and the scope is the list below.
        "scope": "functions this gate can build a control-flow graph for",
        "names_the_magic_but_is_not_modelled": sorted(unmodelled),
    }


def verify_linked_image(objdump_text: str, nm_text: str, variant: str) -> dict:
    """Every claim this contract makes about the built image, in one document."""

    dominance = verify_pre_run_dominance(objdump_text, nm_text)
    loop = verify_primary_loop_image(objdump_text, variant)
    publication = verify_mailbox_publication_image(objdump_text, nm_text)
    tail = verify_convergence_tail_image(objdump_text)
    return {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "proof_scope": "linked_image",
        "pre_run": dominance,
        "primary_loop": loop,
        "convergence_tail": tail,
        "mailbox_publication": publication,
        "claims_bound_here": list(BOUND_ON_LINKED_IMAGE),
        "retired_claims": list(RETIRED_CLAIMS),
        # Still owed by nobody. The source gate does not make these and this one
        # does not either, so a reader is told rather than left to infer it.
        "unbound_claims": list(unbound_claims()),
    }


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


# ---------------------------------------------------------------------------
# Whole-translation-unit confinement
#
# Every counting and ordering rule above is proven inside the function that
# carries it. That is sound for what it measures and silent about everything
# else, and the silence is the fail-open half: a QSIZE load moved into
# ``v14_publish_primary`` -- called from ``test_commands`` after the submit write
# and before the terminal CMD=0 -- is a load on the running path that the scan of
# ``test_commands`` cannot see, and the manifest went on publishing a
# running-QSIZE count of zero for it.
#
# The answer here is not interprocedural analysis. It is a flat scan over the
# whole vendor translation unit for the *register name itself*, attributed to the
# function that spells it, and refused wherever the design does not touch that
# register. That closes the running-path question at source without resolving a
# single call: a register the running path must not read is one no function
# outside its authorised set may name at all.
#
# The authorised sets are the design's, transcribed from the approved sources:
# the queue-setup function programs QBASE/QSIZE and takes the pre-program STATUS
# gate; ``test_commands`` takes the one pre-submit QSIZE snapshot, the one
# pre-submit STATUS load, the QREAD verify and every CMD write in the release
# tail; the primary and convergence helpers poll QREAD and STATUS; the NPU ISR
# reads STATUS and writes the ISR-clear CMD. Nothing else names an NPU register.
# ---------------------------------------------------------------------------

ISR_SYMBOL = "u85_irq_handler"
COMMAND_SYMBOL = "test_commands"


# The role a register access resolves to is read out of the *source's own*
# ``NPU_REG_*`` define table, and that table is not the design's -- it is
# whatever the unit declares. So a role outside the table above is not "a
# register this contract has no opinion about"; it is a register the operator
# named, at an offset the operator chose, that every counting, ordering and
# confinement rule below would otherwise skip. One added ``#define
# NPU_REG_DOORBELL 0x000U`` turns a second submit into exactly that.
#
# An access this gate can attribute to *no* modelled register is therefore
# refused, on the same terms as one it cannot attribute at all.
# The registers whose *name* may appear outside the functions that may access
# them, because the design binds a pointer to them at file scope and a binding
# reaches nothing. They are still held to the owner table by the two walks that
# read accesses rather than names, and they are still required to be modelled --
# an unmodelled role is refused here exactly as everywhere else.
NAME_UNCONFINED_REGISTERS = frozenset(("QREAD",))

_UNMODELLED_ROLE_REFUSAL = (
    "%s designates NPU_REG_%s at offset %d, which resolves to a register this contract does "
    "not model: the register map this gate reads is the translation unit's own, so a name or "
    "offset outside the modelled set is one no confinement, submit-count or read-order rule "
    "in this file covers"
)


# The registers the frozen stock vendor names that the design has no opinion
# about, each confined to the functions the stock itself names it in.
#
# Refusing these outright refuses the frozen file: the stock unit touches 29 NPU
# registers and the design models five. But allowing them by name alone would
# allow ``read_reg(NPU_REG_PROT)`` inside a measured loop -- per-iteration MMIO
# no read-order rule judges -- so the owner set is carried with each one and a
# stock register named anywhere else is refused exactly as before. A register in
# neither table is still refused: the added ``#define NPU_REG_DOORBELL`` this
# gate was built to catch is not in the frozen source and does not become
# authorised by being spelled like a vendor one.
#
# Derived from the pinned stock source rather than remembered; the unit suite
# recomputes it from the tracked firmware/Drivers/u85_driver/u85.c and refuses a
# mismatch.
# The frozen vendor's two register accessors. Each builds a pointer out of a
# parameter, which no rule here can resolve to one register -- being generic over
# the register is what makes them accessors, and the gate judges their *calls* by
# the argument instead. The hand-written stand-in only ever called them, never
# defined them, so the whole-unit walk had never met one.
#
# The exemption is over these bodies, not these names: an accessor that grew a
# second dereference, reached a register directly, or gained any other effect no
# longer matches and is judged like every other function.
FROZEN_ACCESSOR_BODIES = {
    "read_reg": "3435f9ebb220d8cf413b0d6cb88a44ece1647bb15fa1e1eae03b5a322c404f2c",
    "write_reg": "ccfde47ef69f7cd406d407e6b22a90620dc5de6596b31cc822c214a08e4e7a67",
}


STOCK_REGISTER_OWNERS = {
    "AXI_EXT": frozenset(("test_commands",)),
    "AXI_SRAM": frozenset(("test_commands",)),
    "BASEP0_LSB": frozenset(("test_commands",)),
    "BASEP0_MSB": frozenset(("test_commands",)),
    "BASEP1_LSB": frozenset(("test_commands",)),
    "BASEP1_MSB": frozenset(("test_commands",)),
    "BASEP2_LSB": frozenset(("test_commands",)),
    "BASEP2_MSB": frozenset(("test_commands",)),
    "BASEP3_LSB": frozenset(("test_commands",)),
    "BASEP3_MSB": frozenset(("test_commands",)),
    "CFG_EXT_CAP": frozenset(("test_commands",)),
    "CFG_SRAM_CAP": frozenset(("test_commands",)),
    "CONFIG": frozenset(("test_commands",)),
    "ID": frozenset(("test_commands",)),
    "MEM_ATTR0": frozenset(("test_commands",)),
    "MEM_ATTR1": frozenset(("test_commands",)),
    "MEM_ATTR2": frozenset(("test_commands",)),
    "MEM_ATTR3": frozenset(("test_commands",)),
    "POWER_CTRL": frozenset(("test_commands",)),
    "PROT": frozenset(("test_commands",)),
    "QBASE_LSB": frozenset(("test_commands",)),
    "QBASE_MSB": frozenset(("test_commands",)),
    "QCONFIG": frozenset(("test_commands",)),
    "REGIONCFG": frozenset(("test_commands",)),
    "RESET": frozenset(("test_commands",)),
}


def _require_modelled_role(
    role: str, authorized: dict[str, frozenset], what: str, site: int
) -> frozenset:
    """The owner set for ``role``, or a refusal when the contract models none."""

    allowed = authorized.get(role)
    if allowed is None:
        allowed = STOCK_REGISTER_OWNERS.get(role)
    if allowed is None:
        raise fail(_UNMODELLED_ROLE_REFUSAL % (what, role, site))
    return allowed


# The frozen stock vendor's own STATUS helpers: its IRQ spin and its reset spin.
# Both read STATUS into a diagnostic and neither is on the measured path, but
# both are part of the translation unit this contract is generated into, so
# refusing them refuses the stock file rather than an attack.
#
# This set is *derived* from the pinned stock source rather than remembered, and
# the unit suite recomputes it from the tracked firmware/Drivers/u85_driver/u85.c
# and refuses a mismatch. Listing it by hand is how ``wait_for_reset`` came to be
# missing: the suite's hand-written stand-in vendor did not have one, so nothing
# ever asked whether the list was complete.
STOCK_STATUS_HELPERS = frozenset(("wait_for_irq", "wait_for_reset"))


def _register_authorized_owners(
    vendor_masked: str, setup_name: str, variant: str
) -> dict[str, frozenset]:
    """The functions the design lets name each NPU register.

    ``setup_name`` is resolved rather than named, the way
    ``verify_pre_run_contract`` resolves it, so the confinement holds wherever
    the vendor keeps its queue programming. The pre-program gate is resolved the
    same way and for the same reason: it reads STATUS, and it does not have to
    live in the function that programs the queue -- in the frozen vendor it does
    not.
    """

    primary = PRIMARY_SYMBOL[variant]
    gate_name = _pre_program_gate_function(vendor_masked, function_spans(vendor_masked))
    return {
        "QSIZE": frozenset((setup_name, COMMAND_SYMBOL)),
        "QBASE": frozenset((setup_name,)),
        # Plus the frozen stock vendor's own STATUS helpers -- see
        # STOCK_STATUS_HELPERS. They are authorised for STATUS only: a QSIZE or
        # CMD access relocated into one of them is still refused.
        "STATUS": frozenset(
            (setup_name, gate_name, COMMAND_SYMBOL, ISR_SYMBOL, primary, CONVERGE_SYMBOL)
        )
        | STOCK_STATUS_HELPERS,
        "CMD": frozenset((COMMAND_SYMBOL, ISR_SYMBOL)),
        # QREAD used to be *absent* from this table, on the ground that a bound
        # QREAD pointer is not evidence the way a QSIZE or CMD one is -- it is
        # the register the design polls, its ordering is proven inside the two
        # measured loops, and the frozen contract permits a file-scope binding
        # this table would otherwise refuse.
        #
        # Absence was read by every walk below as permission, and
        # permission-by-absence is indistinguishable from "a role nothing
        # models": one added ``#define NPU_REG_DOORBELL 0x000U`` produced a role
        # with no owner set, and each walk skipped the second submit it named.
        # Writing that permission down as an owner-unconstrained answer fixed
        # the confusion and kept the hole: "its ordering is proven inside the
        # measured loops" is an argument about the loops, not a licence for
        # QREAD MMIO anywhere in the unit, and an extra load in a publisher or
        # in the ISR is running-path MMIO no read-order rule judged.
        #
        # So QREAD is owned like every other register. The design polls it in
        # the active primary helper and the convergence helper, and reads it
        # back once in the command function's cleanup; those three are the whole
        # set the canonical and generated sources *load* it from.
        #
        # This row is read by the two **access** walks only. The name scan skips
        # it, because a QREAD designation is not necessarily a load: the frozen
        # contract binds a QREAD pointer, and a binding names the register
        # without reaching it. Confining the name would refuse that binding;
        # confining the access is what the ground about the measured loops
        # actually supports. Writes are refused by their own rules.
        "QREAD": frozenset((primary, CONVERGE_SYMBOL, COMMAND_SYMBOL)),
    }


_REGISTER_REFUSALS = {
    "QSIZE": (
        "QSIZE is designated outside the queue setup and the one pre-submit snapshot: "
        "%s names NPU_REG_QSIZE at offset %d, and a QSIZE access reached from the running "
        "window is a running-path load no count in this manifest covers"
    ),
    "QBASE": (
        "QBASE is designated outside the queue setup: %s names NPU_REG_QBASE at offset %d, "
        "and reprogramming the queue base off the setup path restarts the run every later "
        "word claims to have measured"
    ),
    "STATUS": (
        "STATUS is designated in a function the contract does not read it from: %s names "
        "NPU_REG_STATUS at offset %d, and a STATUS load this gate does not order is one the "
        "dominance and read-order rules never judged"
    ),
    "CMD": (
        "CMD is written in a function the contract does not write it from: %s names "
        "NPU_REG_CMD at offset %d, and a CMD write off the command path transitions the NPU "
        "between the submit and the measurement that reports it"
    ),
    "QREAD": (
        "QREAD is designated in a function the contract does not poll it from: %s names "
        "NPU_REG_QREAD at offset %d, and a queue-read-pointer access outside the two measured "
        "loops and the read-back is one no ordering rule in this file judged"
    ),
}


def require_register_confinement(
    vendor_masked: str, setup_name: str, variant: str
) -> int:
    """Refuse an NPU register named anywhere the design does not name it.

    Directives are blanked first, so the ``#define NPU_REG_QSIZE`` that gives the
    register its offset is not itself an access. Every remaining spelling counts:
    the vendor accessor's argument, a raw pointer built from
    ``U85_BASE_ADDRESS + NPU_REG_QSIZE``, and a name at file scope with no
    enclosing function at all.

    Returns the number of authorised designations it walked, so the manifest can
    publish the verifier's own count rather than a constant.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    spans = function_spans(vendor_masked)
    scanned = blank_directives(vendor_masked)
    walked = 0
    for match in _RAW_REGISTER_RE.finditer(scanned):
        register = match.group(1)
        owner = enclosing_function(spans, match.start())
        if register in NAME_UNCONFINED_REGISTERS:
            # A designation that may be a *binding* rather than an access. This
            # walk reads names, so confining it here would refuse the frozen
            # contract's own QREAD pointer; the two access walks below own the
            # question of where a load may happen, and they hold it to the same
            # table every other register is held to.
            _require_modelled_role(register, authorized, _span_label(owner), match.start())
            walked += 1
            continue
        allowed = _require_modelled_role(
            register, authorized, _span_label(owner), match.start()
        )
        if owner in allowed:
            walked += 1
            continue
        raise fail(
            _REGISTER_REFUSALS[register]
            % (owner or "file scope", match.start())
        )
    return walked


# ---------------------------------------------------------------------------
# Whole-unit MMIO confinement
#
# The scan above reads a register *name*, so it is a scan every spelling that
# carries no name walks around:
#
#     *(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + 0x000U) = 1U;
#     *(volatile uint32_t *)0x50004000U = 1U;
#
# Both are a second submit. The gate already owns the resolver that names them
# -- ``resolve_address_role``, reached through ``require_resolved_dereferences``
# -- but that resolver ran only inside the functions the design names, and a
# helper the design does not name was scanned by neither rule. The resolver is
# therefore run over *every* function span and over file scope, so an NPU-region
# address this gate cannot pin to one register is refused wherever it is
# written, and a resolved one is held to the same owner table as its name.
#
# That is what makes ``register_confinement_scope: vendor_translation_unit`` a
# statement about the translation unit rather than about the tokens that happen
# to spell a register.
# ---------------------------------------------------------------------------


def _span_label(name: str) -> str:
    return "the vendor function %s" % name if name else "the vendor unit at file scope"


def require_whole_unit_mmio_confinement(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an NPU-region access this gate cannot name, or names out of place.

    Returns the number of resolved, authorised accesses it walked, so the
    manifest publishes the verifier's own whole-unit count.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    scope = file_scope_text(vendor_masked)
    walked = 0
    for name, start, stop in function_spans(vendor_masked):
        body = vendor_masked[start:stop]
        what = _span_label(name)
        if FROZEN_ACCESSOR_BODIES.get(name) == normalized_digest(body):
            continue
        roles = pointer_roles(body, defines, scope)
        require_resolved_pointers(roles, what)
        require_resolved_dereferences(body, defines, roles, what)
        for site, role, is_write in dereference_sites(body, defines, roles):
            if role == "QREAD" and is_write:
                raise fail(_QREAD_WRITE_REFUSAL % (what, start + site))
            allowed = _require_modelled_role(role, authorized, what, start + site)
            if name in allowed:
                walked += 1
                continue
            raise fail(_REGISTER_REFUSALS[role] % (name or "file scope", start + site))
    return walked


# QREAD is the register the design *polls*, so the confinement table above
# authorises no owner for it and a bound QREAD pointer is not evidence of
# anything. A QREAD *write* is a different construct entirely: nothing in this
# contract writes the queue read pointer, and one that does rewinds the queue
# between the primary observation and the convergence tail, so words 17..19 and
# the success predicate all describe a queue that was reset under them.
_QREAD_WRITE_REFUSAL = (
    "QREAD is written in %s at offset %d: the design never writes the queue read pointer, "
    "and a write to it rewinds the queue between the observation and the convergence tail "
    "every later word claims to have measured"
)


# ---------------------------------------------------------------------------
# The QREAD load budget
#
# Owning the register by function says *where* it may be loaded and never *how
# often*. The read-order rules walk the two loop bodies, so a load placed after
# the loop and before publication -- ``(void)*qread_reg;`` in ``v14_converge``
# -- is running-path MMIO inside an authorised owner that no ordering rule
# judged, and it moves the hook read count the runner publishes as a record
# word. Each owner therefore carries the number of QREAD accesses the design
# gives it: one per measured loop, and one read-back in the cleanup.
# ---------------------------------------------------------------------------

QREAD_LOADS_PER_OWNER = 1


def _takes_address_at(text: str, site: int) -> bool:
    """Whether the access at ``site`` is an address-of rather than a load.

    ``&base[NPU_REG_QREAD / 4]`` is a subscript this gate enumerates as an
    access, and it is a *binding*: it reaches no word. Counting it as a load
    would make the design's own pointer bindings look like extra MMIO.
    """

    cursor = site - 1
    while cursor >= 0 and text[cursor] in _INLINE_SPACE:
        cursor -= 1
    return text[cursor : cursor + 1] == "&" and text[cursor - 1 : cursor] != "&"


def qread_access_counts(
    vendor_masked: str, defines: dict[str, int]
) -> dict[str, int]:
    """``owner -> number of QREAD accesses``, over both spellings."""

    scope = file_scope_text(vendor_masked)
    spans = function_spans(vendor_masked)
    counts: dict[str, int] = {}
    for name, start, stop in spans:
        body = vendor_masked[start:stop]
        roles = pointer_roles(body, defines, scope)
        loads = sum(
            1
            for site, role, _write in dereference_sites(body, defines, roles)
            if role == "QREAD" and not _takes_address_at(body, site)
        )
        if loads:
            counts[name] = counts.get(name, 0) + loads
    for site, _verb, role in accessor_designations(vendor_masked, defines):
        if role != "QREAD":
            continue
        owner = enclosing_function(spans, site)
        counts[owner] = counts.get(owner, 0) + 1
    return counts


def require_qread_load_budget(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an authorised owner that loads QREAD more often than the design does."""

    allowed = _register_authorized_owners(vendor_masked, setup_name, variant)["QREAD"]
    counts = qread_access_counts(vendor_masked, defines)
    for owner in sorted(counts):
        if owner not in allowed:
            # Where it may be loaded at all is the confinement walks' question;
            # this rule only bounds the owners they authorise.
            continue
        if counts[owner] != QREAD_LOADS_PER_OWNER:
            raise fail(
                "%s loads QREAD more times than the design loads it: %d accesses where the "
                "design makes %d, and a load outside the loop that measures it is running-path "
                "MMIO no read-order rule in this file judged"
                % (_span_label(owner), counts[owner], QREAD_LOADS_PER_OWNER)
            )
    return sum(counts.get(owner, 0) for owner in allowed)


def require_no_qread_write(vendor_masked: str) -> None:
    """Refuse the accessor spelling of a QREAD write anywhere in the unit."""

    scan = blank_directives(vendor_masked)
    site = code_find(scan, "write_reg(NPU_REG_QREAD")
    if site >= 0:
        raise fail(_QREAD_WRITE_REFUSAL % ("the vendor translation unit", site))


# ---------------------------------------------------------------------------
# The vendor accessor's own argument
#
# The two whole-unit scans above read an address expression and a register
# *name*. The vendor accessor carries neither: it takes the register as an
# ordinary integer argument, so
#
#     write_reg(0x000U, 1U);          /* a second submit                     */
#     (void)read_reg(0x108U);         /* a running-path QSIZE load           */
#     (void)read_reg(SEL2(NPU_REG_,QSIZE));   /* the prefix as a paste argument */
#
# reach CMD and QSIZE without ever spelling ``NPU_REG_`` and without ever
# building a pointer. ``require_register_confinement`` scans for the token,
# ``require_whole_unit_mmio_confinement`` resolves pointer expressions, and an
# accessor call carrying a number is neither -- which is precisely the
# capability both of them exist to bound, spelled a third way.
#
# So the accessor's own argument is resolved here, on the same terms every other
# address in this file is: a designation this gate can pin to one register is
# held to the owner table, and one it cannot pin is refused rather than counted
# as nothing. This is what makes ``register_confinement_scope:
# vendor_translation_unit`` a statement about every access in the unit rather
# than about the two spellings the scans above happen to recognise.
# ---------------------------------------------------------------------------

_ACCESSOR_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(read_reg|write_reg)\s*\(")
# ``NPU_REG_QSIZE`` and nothing else. An offset built *from* a designation --
# ``NPU_REG_QREAD + 4U`` -- is not a designation: it reaches a different word
# than the name it spells, and this gate has no map to say which.
_PLAIN_DESIGNATION_RE = re.compile(r"^\s*NPU_REG_([A-Z][A-Z0-9_]*)\s*$")

_ACCESSOR_REFUSAL = (
    "the vendor accessor %s is called with a register offset this gate cannot resolve to one "
    "register, in %s at offset %d: the argument is neither a register designation nor a value "
    "this unit's own offset table names, so every confinement, submit-count and read-order rule "
    "in this file walks past the access it makes"
)


def _accessor_offset_role(argument: str, defines: dict[str, int]) -> str:
    """The register an accessor's offset argument designates."""

    designation = _PLAIN_DESIGNATION_RE.match(argument)
    if designation is not None:
        return designation.group(1)
    value = _evaluate_constant(argument, defines)
    if value is None:
        return UNRESOLVED_ROLE
    return _role_at_offset(value, defines)


def accessor_designations(
    vendor_masked: str, defines: dict[str, int]
) -> tuple[tuple[int, str, str], ...]:
    """``(site, verb, role)`` for every vendor-accessor *call* in the unit.

    A declaration is separated from a call the way ``_publication_symbol_sites``
    separates them: a declarator is introduced by its return type, and nothing
    but a type name or a ``*`` can sit directly in front of one.
    """

    scan = blank_directives(vendor_masked)
    close_of, _open_of = _bracket_pairs(scan)
    found: list[tuple[int, str, str]] = []
    for match in _ACCESSOR_CALL_RE.finditer(scan):
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(scan[cursor]) or scan[cursor] == "*"
        ):
            continue
        open_index = match.end() - 1
        close_index = close_of.get(open_index)
        if close_index is None:
            found.append((match.start(), match.group(1), UNRESOLVED_ROLE))
            continue
        arguments = _split_top_level(scan[open_index + 1 : close_index], ",")
        found.append(
            (
                match.start(),
                match.group(1),
                _accessor_offset_role(arguments[0] if arguments else "", defines),
            )
        )
    return tuple(found)


def require_accessor_designations_confined(
    vendor_masked: str, defines: dict[str, int], setup_name: str, variant: str
) -> int:
    """Refuse an accessor call this gate cannot pin to one authorised register.

    Returns the number of resolved, authorised accessor calls it walked, so the
    manifest publishes the verifier's own count of the third spelling too.
    """

    authorized = _register_authorized_owners(vendor_masked, setup_name, variant)
    spans = function_spans(vendor_masked)
    walked = 0
    for site, verb, role in accessor_designations(vendor_masked, defines):
        owner = enclosing_function(spans, site)
        if role == UNRESOLVED_ROLE:
            raise fail(_ACCESSOR_REFUSAL % (verb, _span_label(owner), site))
        if role == "QREAD" and verb == "write_reg":
            raise fail(_QREAD_WRITE_REFUSAL % (_span_label(owner), site))
        allowed = _require_modelled_role(role, authorized, _span_label(owner), site)
        if owner not in allowed:
            raise fail(_REGISTER_REFUSALS[role] % (owner or "file scope", site))
        walked += 1
    return walked


# The confinement table authorises ``u85_irq_handler`` to write CMD, because the
# stock ISR clears completion there. It authorised the *owner* and never the
# *value*, so a second submit issued from interrupt context satisfied it -- and
# a terminal CMD=0 written there stops the NPU before the convergence tail
# measures it. The ISR's STATUS load is bounded for the same reason: one load is
# the design's, and a second is one no ordering rule in this file judged.
ISR_CMD_CLEAR_VALUE = 2
ISR_STATUS_LOADS = 1


def require_isr_register_values(vendor_masked: str, defines: dict[str, int]) -> None:
    """Pin what the interrupt handler writes to CMD and how often it reads STATUS."""

    body = function_text(vendor_masked, ISR_SYMBOL, "interrupt handler")
    roles = pointer_roles(body, defines, file_scope_text(vendor_masked))
    for site, value in cmd_write_values(body, defines, roles):
        if value != ISR_CMD_CLEAR_VALUE:
            raise fail(
                "the interrupt handler writes CMD with a value the design does not give it: "
                "%s at offset %d, and the only CMD write this contract makes from interrupt "
                "context is the 0x%X completion clear"
                % (_cmd_value_text(value), site, ISR_CMD_CLEAR_VALUE)
            )
    loads = register_access_sites(body, "STATUS", defines, roles)
    if len(loads) != ISR_STATUS_LOADS:
        raise fail(
            "the interrupt handler loads STATUS %d times: the design loads it %d, and a further "
            "load is one no dominance or read-order rule in this file judged"
            % (len(loads), ISR_STATUS_LOADS)
        )


# ``_register_authorized_owners`` lets ``wait_for_irq`` name STATUS on the
# stated ground that the V14 command path never calls it. That was a comment,
# not a rule, so a ``wait_for_irq`` that spins on STATUS until CMD_END and is
# actually called consumes completion before the measured loop starts -- and
# every ``first_*`` word then describes an already-complete device while the
# gate reports the exemption intact. The ground is checked here.
WAIT_FOR_IRQ_SYMBOL = "wait_for_irq"


def _direct_call_sites(masked: str, name: str) -> tuple[int, ...]:
    """Every offset where ``name`` is used as a callee rather than declared."""

    found: list[int] = []
    pattern = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])\s*\(" % re.escape(name))
    for match in pattern.finditer(blank_directives(masked)):
        cursor = match.start() - 1
        while cursor >= 0 and masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(masked[cursor]) or masked[cursor] == "*"
        ):
            continue
        found.append(match.start())
    return tuple(found)


_WAIT_FOR_IRQ_REFUSAL = (
    "wait_for_irq is named outside its own definition, %s: the STATUS designation this gate "
    "authorises inside it is authorised on the ground that the command path never reaches it, "
    "and a name that is not the declarator is a reachability this gate cannot bound -- a "
    "running-path STATUS load no dominance or read-order rule judged"
)


def require_wait_for_irq_unreachable(vendor_masked: str) -> None:
    """Refuse a ``wait_for_irq`` this gate cannot prove is unreached.

    ``_direct_call_sites`` answers "is it called *here*", which is an answer
    about the token stream after ``blank_directives`` -- so a macro expanding to
    the call is a call after preprocessing and no call site before it, and the
    address of the symbol is a reachability with no call site at all. The
    exemption rests on the helper being unreached, so the proof is written the
    same way: the symbol may appear as its own declarator and nowhere else.
    """

    # The direct call first, so the spelling the design's own fixtures name is
    # reported by the rule that names it rather than by the wider one below.
    sites = _direct_call_sites(vendor_masked, WAIT_FOR_IRQ_SYMBOL)
    if sites:
        raise fail(
            "wait_for_irq is called at offset %d: the STATUS designation this gate authorises "
            "inside it is authorised on the ground that the command path never calls it, and a "
            "call makes that a running-path STATUS load no dominance or read-order rule judged"
            % sites[0]
        )
    scan = blank_directives(vendor_masked)
    for match in _IDENTIFIER_RE.finditer(scan):
        if match.group(0) != WAIT_FOR_IRQ_SYMBOL:
            continue
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        introduced_by_a_type = cursor >= 0 and (
            _NAME_CHARACTER_RE.match(scan[cursor]) or scan[cursor] == "*"
        )
        cursor = match.end()
        while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:
            cursor += 1
        if introduced_by_a_type and scan[cursor : cursor + 1] == "(":
            # A definition or a prototype: a return type in front of it, a
            # parameter list behind it. Neither reaches the helper.
            continue
        raise fail(_WAIT_FOR_IRQ_REFUSAL % ("at offset %d" % match.start()))
    # And the half the scan above cannot see at all. A replacement list naming
    # the helper is a call site this gate never expands, whichever of the two
    # macro forms carries it and whether it spells the parentheses or leaves
    # them to the invocation.
    for name, _parameters, body in macro_definitions(vendor_masked):
        if names_identifier(body, WAIT_FOR_IRQ_SYMBOL):
            raise fail(_WAIT_FOR_IRQ_REFUSAL % ("in the replacement list of %s" % name))


# ---------------------------------------------------------------------------
# The measured locals
#
# ``assignment_statements`` recovers ``name = expr`` and, by construction, skips
# every ``=`` whose preceding character is in ``_ASSIGNMENT_BOUNDARY``. So a
# compound assignment and an increment are stores the same-iteration, count and
# classification proofs never saw:
#
#     status &= ~V14_STATUS_RESET;   /* a reset run published as a timeout   */
#     qread++;                       /* word 17 published one past the read  */
#     iterations += 1U;              /* word 16 off by one                   */
#     status |= V14_STATUS_CMD_END;  /* a timed-out run asserting completion */
#
# The lvalue walk already exists for the mailbox and the record; the measured
# locals are the storage it was not applied to.
# ---------------------------------------------------------------------------

MEASURED_LOCALS = ("qread", "status", "result", "iterations")


def require_measured_locals_not_stepped(body: str, what: str) -> None:
    """Refuse a read-modify-write on a local the publication reads."""

    stepped = compound_assignment_targets(body, MEASURED_LOCALS)
    if stepped:
        raise fail(
            "%s: %s is stepped by a read-modify-write, so the value it publishes is not the one "
            "the measured load produced" % (what, ", ".join(stepped))
        )


# ---------------------------------------------------------------------------
# The convergence helper's declarations
#
# ``require_convergence_classification`` proves each *guard* lands its own
# category. Nothing proved the fall-through, and the fall-through is a
# declaration:
#
#     -    uint32_t result = V14_CONVERGENCE_TIMEOUT;
#     +    uint32_t result = V14_CONVERGENCE_SUCCESS;
#
# The loop then runs to the bound without matching, no ``break`` fires, and
# ``obs->result`` carries SUCCESS out of a run that never converged --
# ``v14_publish_success()`` and ``V14_RET_SUCCESS`` with every convergence
# manifest key still correct. The primary helper has no such hole because it
# ends in an unconditional terminal store the observation table pins; this is
# that pin, written for the helper that carries its terminal category in an
# initialiser instead.
# ---------------------------------------------------------------------------

CONVERGENCE_DECLARATIONS = (
    ("result", "V14_CONVERGENCE_TIMEOUT"),
    ("iterations", "0U"),
    ("qread", "0U"),
    ("status", "0U"),
)
# ``result`` is settled by the three classifier guards, ``iterations`` by the
# completion guard alone, and ``qread``/``status`` by the one read pair the
# same-iteration rule already counts.
CONVERGENCE_ASSIGNMENTS = (("result", 3), ("iterations", 1), ("qread", 1), ("status", 1))

# ``uint32_t result``, ``result`` -- a declarator or a bare name, and nothing
# with a member, a subscript or a dereference in it.
_PLAIN_LOCAL_LVALUE_RE = re.compile(r"^\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*$")


def require_convergence_declarations(converge_body: str, defines: dict[str, int]) -> None:
    """Pin the convergence helper's terminal tuple and count what may rewrite it."""

    wanted_names = frozenset(name for name, _expected in CONVERGENCE_DECLARATIONS)
    declared: dict[str, list[str]] = {}
    assigned: dict[str, int] = {}
    for _start, lvalue, rvalue in assignment_statements(converge_body):
        # The bare local only. ``obs->result`` writes the observation record,
        # which ``verify_observation_contract`` owns, and counting it here would
        # credit the helper with a write to a name it never touched.
        match = _PLAIN_LOCAL_LVALUE_RE.match(lvalue)
        if match is None or match.group(1) not in wanted_names:
            continue
        name = match.group(1)
        if _is_declaration(lvalue):
            declared.setdefault(name, []).append(rvalue)
        else:
            assigned[name] = assigned.get(name, 0) + 1
    for name, expected in CONVERGENCE_DECLARATIONS:
        found = declared.get(name, [])
        wanted = _evaluate_constant(expected, defines)
        if len(found) != 1 or _evaluate_constant(found[0], defines) != wanted:
            raise fail(
                "the convergence helper does not carry its terminal category in its declaration: "
                "%s is declared %s, and the design declares it %s -- a loop that runs to the "
                "bound without matching publishes whatever the declaration left there"
                % (
                    name,
                    ", ".join(_normalized_expression(item) for item in found) or "nowhere",
                    expected,
                )
            )
    for name, count in CONVERGENCE_ASSIGNMENTS:
        found_count = assigned.get(name, 0)
        if found_count != count:
            raise fail(
                "the convergence helper assigns %s %d times outside its declaration: the design "
                "assigns it %d, and a further assignment reaches the publication without passing "
                "the guard that would justify it" % (name, found_count, count)
            )


# ---------------------------------------------------------------------------
# The runner's diagnostic function
#
# ``require_no_function_pointer``/``require_no_indirect_call`` are vendor-only,
# because the stock runner declares an ``irq_handler_t`` of its own at file
# scope. That exemption reached the serialized record: a function pointer
# declared *inside* the diagnostic function rewrote all 34 words after every
# copy and dominance rule was satisfied, and the copy-out parameter escaped the
# ``&d`` closure because the write went through ``out`` rather than through the
# record. The exemption is narrowed to file scope here, and the copy-out pointer
# is closed the way the record already is.
# ---------------------------------------------------------------------------


def _parameter_names(masked: str, body_start: int) -> tuple[tuple[str, bool], ...]:
    """``(name, is_pointer)`` for each parameter of the function opening at ``body_start``."""

    head = masked[: max(body_start - 1, 0)]
    close = head.rfind(")")
    if close < 0:
        return ()
    _close_of, opens = _bracket_pairs(head[: close + 1])
    open_index = opens.get(close)
    if open_index is None:
        return ()
    found: list[tuple[str, bool]] = []
    for declarator in head[open_index + 1 : close].split(","):
        names = _IDENTIFIER_RE.findall(declarator)
        if not names:
            continue
        found.append((names[-1], "*" in declarator))
    return tuple(found)


def require_record_copy_out_closed(
    runner_masked: str, span: tuple[int, int], parameters: frozenset
) -> None:
    """Refuse the record copy-out pointer reaching anything but its own store."""

    start, stop = span
    for match in _IDENTIFIER_RE.finditer(runner_masked, start, stop):
        if match.group(0) not in parameters:
            continue
        cursor = match.start() - 1
        while cursor >= 0 and runner_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if runner_masked[cursor : cursor + 1] == "*" and not _is_declarator_star(
            runner_masked, cursor
        ):
            continue
        raise fail(
            "the runner hands the record copy-out pointer %s to something other than the copy "
            "the design writes, at offset %d: a write through it rewrites every word the "
            "record's copy, dominance and address rules proved"
            % (match.group(0), match.start())
        )


def require_runner_diagnostic_closed(runner_masked: str, span: tuple[int, int]) -> None:
    """Hold the record-owning function to the vendor's indirect-call standard."""

    start, stop = span
    body = runner_masked[start:stop]
    require_no_function_pointer(body, "the runner diagnostic function")
    require_no_indirect_call(body, "the runner diagnostic function")
    # No exemption inside this window: the stock vector slot is chained to from
    # the ISR wrapper, not from the function that owns the serialized record, and
    # a call through any pointer object here rewrites words the copy, dominance
    # and address rules just proved.
    require_no_call_through_pointer_object(
        runner_masked,
        RUNNER_STOCK_FUNCTION_POINTERS,
        "the runner diagnostic function",
        window=span,
    )
    pointers = frozenset(
        name for name, is_pointer in _parameter_names(runner_masked, start) if is_pointer
    )
    if pointers:
        require_record_copy_out_closed(runner_masked, span, pointers)


# ---------------------------------------------------------------------------
# Indirect calls
#
# ``statement_effects`` recognises a call by the identifier in front of the
# ``(``. C's other postfix-call spellings carry the same effect and name no
# identifier there, so ``(*fp)()`` inside a measured loop is a per-iteration call
# the loop's own "no store, no call, no timestamp" rule never saw -- and a second
# submit written ``v14_wr(NPU_REG_CMD, 1)`` through a bound pointer is a submit
# the "exactly one" rule never counted, because the register name it reaches is
# an argument rather than the accessor's.
#
# Resolving a function pointer's target is not something this gate can do, so it
# does not try. The design declares none, and one that appears is refused: the
# declarator is the token every spelling of the attack shares.
# ---------------------------------------------------------------------------

# ``(*name)(``, ``(*name[2])(`` and ``(**name)(`` -- a parenthesised, starred
# declarator followed by a parameter list. A cast such as ``(volatile uint32_t *)``
# does not match: its parenthesis opens on a type name, not on a ``*``.
_FUNCTION_POINTER_DECLARATOR_RE = re.compile(
    r"\(\s*\*+\s*(?:const\s+|volatile\s+)*([A-Za-z_]\w*)\s*(?:\[[^\[\]]*\])*\s*\)\s*\("
)

# The one function-pointer name the *host runner* legitimately declares: the
# stock vector-table type it installs its handler through.
#
# Exempting the name alone exempted the *type*, and an object of a
# function-pointer type is an ordinary identifier -- so ``static irq_handler_t
# g_hook; ... g_hook();`` is a call through a pointer spelled exactly like a
# direct call, which ``require_no_indirect_call`` (which looks for a callee that
# is an *expression*) can never see. Two things are therefore required of the
# exemption rather than one: the declarator must be introduced by ``typedef``,
# so a file-scope pointer *object* that merely reuses the name is still refused;
# and every object declared with the exempt type is collected below, so a call
# through one is refused as the indirect call it is. The stock runner declares
# ``original_u85_handler``, compares it against a cast null and assigns it, and
# never calls through it -- which is what this pair of rules permits and an
# attack is not.
RUNNER_STOCK_FUNCTION_POINTERS = frozenset(("irq_handler_t",))


def _introduced_by_typedef(masked: str, start: int) -> bool:
    """Whether the declarator beginning at ``start`` belongs to a ``typedef``."""

    head = masked.rfind(";", 0, start)
    brace = max(masked.rfind("{", 0, start), masked.rfind("}", 0, start))
    return _TYPEDEF_RE.search(masked, max(head, brace) + 1, start) is not None


_TYPEDEF_RE = re.compile(r"(?<![A-Za-z0-9_])typedef(?![A-Za-z0-9_])")


def require_no_function_pointer(
    masked: str, what: str, exempt: frozenset = frozenset()
) -> None:
    """Refuse a function-pointer declarator anywhere in ``masked``.

    ``exempt`` names the *typedefs* the stock file may introduce. A declarator
    that carries an exempt name without a ``typedef`` in front of it is an
    object, not a type, and is refused like any other.
    """

    match = next(
        (
            found
            for found in _FUNCTION_POINTER_DECLARATOR_RE.finditer(masked)
            if not (
                found.group(1) in exempt
                and _introduced_by_typedef(masked, found.start())
            )
        ),
        None,
    )
    if match is not None:
        raise fail(
            "%s declares a function pointer at offset %d: %s -- a call through it carries "
            "any effect past the per-iteration, submit-counting and register-confinement "
            "rules, and this gate cannot resolve its target"
            % (what, match.start(), " ".join(match.group(0).split()))
        )


# ``T a, b, c;`` is one declaration and three objects. A capture that reads one
# identifier per occurrence of ``T`` collects only ``a``, so ``b`` and ``c`` are
# names the call rule iterates a set that does not contain -- and a call through
# one of them is spelled exactly like a direct call, which
# ``require_no_indirect_call`` is documented as unable to see.
#
# The stock slot is what the exemption exists for, so sharing its declaration is
# the natural place to hide: ``static irq_handler_t original_u85_handler,
# v14_after_copy;``. Declarators are therefore read across the whole
# declaration -- from the type name to the terminator, split on the commas that
# sit at depth zero -- rather than one per type token.
# The declared name is the last identifier in the declarator, and C lets a
# declarator wrap it in redundant parentheses: ``T (x);`` declares ``x`` exactly
# as ``T x;`` does. Anchoring the name at the end of the text therefore missed
# it -- the text ends in ``)`` -- so the tail admits the closing parentheses and
# the subscripts that may follow, in either order.
_DECLARATOR_TAIL_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:\)|\[[^\[\]]*\]|\s)*$")

# ``typedef irq_handler_t irq_alias_t;`` gives the exempt type a second name.
# The object walk scans for type *names*, so an alias is a type it never looks
# for -- and an object of the alias is called with the syntax of a direct call.
# A typedef whose body names a known function-pointer type therefore contributes
# its own name to the set, to a fixpoint, so an alias of an alias is reached too.
_TYPEDEF_DECLARATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])typedef(?![A-Za-z0-9_])([^;{}]*);"
)


def function_pointer_type_names(masked: str, seeds: frozenset) -> frozenset:
    """``seeds`` and every typedef alias that resolves to one of them."""

    declarations = tuple(
        match.group(1) for match in _TYPEDEF_DECLARATION_RE.finditer(masked)
    )
    known = set(seeds)
    budget = len(declarations) + 1
    for _pass in range(budget):
        grown = False
        for body in declarations:
            # One ``typedef`` declares as many names as it has declarators:
            # ``typedef irq_handler_t v14_a_t, v14_b_t;`` gives the exempt type
            # two aliases, and reading only the last identifier lost the first.
            # The declarators are therefore split the same way an object
            # declaration's are, and every one of them enters the closure.
            parts = _split_top_level(body, ",")
            base = _IDENTIFIER_RE.findall(parts[0]) if parts else []
            if len(base) < 2 or not set(base[:-1]) & known:
                continue
            # A typedef that merely *mentions* a known type inside a
            # function-pointer declarator is not an alias of it.
            if _FUNCTION_POINTER_DECLARATOR_RE.search(body) is not None:
                continue
            for part in parts:
                match = _DECLARATOR_TAIL_RE.search(part.strip())
                if match is None or match.group(1) in known:
                    continue
                known.add(match.group(1))
                grown = True
        if not grown:
            break
    return frozenset(known)


def _is_cast_of(masked: str, start: int, stop: int) -> bool:
    """Whether the type name spanning ``start``..``stop`` is a cast operator."""

    before = start - 1
    while before >= 0 and masked[before] in _INLINE_SPACE:
        before -= 1
    after = stop
    while after < len(masked) and masked[after] in _INLINE_SPACE:
        after += 1
    return masked[before : before + 1] == "(" and masked[after : after + 1] == ")"


def _declaration_end(text: str, start: int) -> int:
    """Where the declaration beginning at ``start`` ends.

    ``_statement_end`` stops at ``;``/``{``/``}`` at bracket depth zero, which is
    the wrong end for a *parameter*: the declaration sits inside a parameter
    list, so the first ``)`` closes a bracket this scan never opened and the walk
    ran on past the whole function -- missing the parameter's own name and
    sweeping in identifiers from unrelated statements. A closer with nothing to
    match is therefore an end too.
    """

    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character in "([":
            depth += 1
        elif character in ")]":
            if depth == 0:
                return index
            depth -= 1
        elif depth == 0 and character in ";{}":
            return index
    return len(text)


def declaration_declarators(text: str, start: int) -> tuple[str, ...]:
    """Every declarator name in the declaration whose type name begins at ``start``."""

    body = text[start : _declaration_end(text, start)]
    found: list[str] = []
    for part in _split_top_level(body, ","):
        # An initialiser is not a declarator. ``= 0`` after the name would
        # otherwise make the last identifier of the initialiser the object.
        head = _split_top_level(part, "=")[0]
        match = _DECLARATOR_TAIL_RE.search(head.strip())
        if match is not None:
            found.append(match.group(1))
    return tuple(found)


def function_pointer_objects(masked: str, types: frozenset) -> tuple[str, ...]:
    """Every identifier declared with one of the exempt function-pointer types.

    ``types`` is widened to the alias closure first, so a typedef that renames
    the exempt type does not hide its objects from the call rule.
    """

    scan = blank_directives(masked)
    types = function_pointer_type_names(masked, types)
    found: list[str] = []
    for type_name in sorted(types):
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(type_name)
        )
        for match in pattern.finditer(scan):
            if _introduced_by_typedef(masked, match.start()):
                continue
            if _is_cast_of(scan, match.start(), match.end()):
                # ``(irq_handler_t)0`` names the type as an operator, not as the
                # head of a declaration; reading declarators out of the
                # expression behind it would invent objects the source has none
                # of.
                continue
            found.extend(declaration_declarators(scan, match.end()))
    return tuple(sorted(set(found) - {type_name for type_name in types}))


# The stock host runner declares its vector slot *and chains to it* -- the ISR
# wrapper calls ``original_u85_handler()`` to hand the interrupt on to the
# handler it displaced. That call is part of the frozen file, so the exemption
# has to name the slot as well as the type; refusing every call through the type
# would refuse the stock runner rather than an attack.
#
# It is bounded twice rather than trusted. The slot is exempt by name, so an
# object of the same type under any other name is refused wherever it is called;
# and the exemption does not reach the function that owns the serialized record,
# where a call through any pointer object at all is refused, because that is the
# window in which an unfollowable call rewrites words the copy and dominance
# rules just proved.
RUNNER_STOCK_VECTOR_SLOTS = frozenset(("original_u85_handler",))

_POINTER_OBJECT_CALL_REFUSAL = (
    "%s calls through a function pointer at offset %d: %s is an object of the stock vector "
    "type, so the call is spelled like a direct one and no counting, ordering or "
    "per-iteration rule in this file sees the effect it carries"
)


def require_no_call_through_pointer_object(
    masked: str,
    types: frozenset,
    what: str,
    exempt: frozenset = frozenset(),
    window: tuple[int, int] | None = None,
) -> None:
    """Refuse a call whose callee is an object of a function-pointer type.

    ``exempt`` names the stock slots the frozen host file calls through.
    ``window`` bounds the scan to one span, and an exemption does not apply
    inside one -- the record-owning function is held to the stricter rule.
    """

    objects = function_pointer_objects(masked, types)
    if not objects:
        return
    scan = blank_directives(masked)
    start, stop = window if window is not None else (0, len(scan))
    for name in objects:
        if window is None and name in exempt:
            continue
        for site in _direct_call_sites(scan, name):
            if start <= site < stop:
                raise fail(_POINTER_OBJECT_CALL_REFUSAL % (what, site, name))


# The keywords that can stand directly in front of a parenthesised expression
# without being a value themselves. Everything else spelled as an identifier
# there is an operand, and a ``(`` after an operand is a call.
_EXPRESSION_KEYWORDS = frozenset(("return", "case", "else", "do", "sizeof"))


def _is_type_only_group(masked: str, open_index: int, close_index: int) -> bool:
    """Whether ``(...)`` encloses a type name and nothing else."""

    tokens = _C_TOKEN_RE.findall(masked[open_index + 1 : close_index])
    if not tokens:
        return False
    return all(
        token == "*" or _TYPE_NAME_TOKEN_RE.match(token) is not None for token in tokens
    )


def _closes_cast_chain(masked: str, close_index: int, opens: dict[int, int]) -> bool:
    """Whether the ``)`` at ``close_index`` ends a run of casts rather than an operand.

    ``_is_cast_parenthesis`` answers this for a single group, and answers it
    wrongly for the chain the vendor sources actually write::

        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD)

    because the ``(uintptr_t)`` group is preceded by the ``)`` of another cast,
    which that helper reads as "an operand ended here". Casts chain, so the walk
    chains too: every group stepped over must enclose a type name only, and the
    leftmost one must be preceded by something that cannot end an operand.
    """

    cursor = close_index
    while cursor >= 0 and masked[cursor] == ")":
        open_index = opens.get(cursor)
        if open_index is None or not _is_type_only_group(masked, open_index, cursor):
            return False
        cursor = open_index - 1
        while cursor >= 0 and masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor < 0:
            return True
        if masked[cursor] == ")":
            continue
        if _NAME_CHARACTER_RE.match(masked[cursor]):
            # An identifier before a cast ends an operand only if it *is* one. A
            # keyword that introduces an expression is not a value, so
            # ``return (uint32_t)(uintptr_t)p`` is a chain of casts and not a
            # call through whatever ``return`` produced.
            return _token_before(masked, cursor + 1)[1] in _EXPRESSION_KEYWORDS
        return masked[cursor] not in _OPERAND_END_CHARACTERS
    return False


def require_no_indirect_call(masked: str, what: str) -> None:
    """Refuse a postfix call whose callee is an expression rather than a name.

    A ``(`` whose preceding token is ``)`` or ``]`` is a call through whatever
    that expression produced -- unless what closed is a cast, in which case the
    ``(`` opens the cast's operand rather than an argument list.
    """

    # Directives are blanked first: a function-like macro's replacement list is
    # not a call site, and ``require_no_statement_macro`` is what judges it.
    scan = blank_directives(masked)
    _close_of, opens = _bracket_pairs(scan)
    # A function-pointer *declarator* closes with ``)`` and is followed by its
    # parameter list, so the ``(`` that opens that list is not a call site. The
    # declarator itself is judged by ``require_no_function_pointer``; reading it
    # as a call here would refuse the stock ``typedef void (*irq_handler_t)(void)``
    # for being a declaration.
    declarator_parameters = frozenset(
        match.end() - 1 for match in _FUNCTION_POINTER_DECLARATOR_RE.finditer(scan)
    )
    for index, character in enumerate(scan):
        if character != "(":
            continue
        if index in declarator_parameters:
            continue
        cursor = index - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor < 0 or scan[cursor] not in _CALLABLE_END:
            continue
        if scan[cursor] == ")" and _closes_cast_chain(scan, cursor, opens):
            continue
        raise fail(
            "%s calls through a function pointer at offset %d: the callee is an expression "
            "rather than a name, so no counting, ordering or per-iteration rule in this file "
            "sees the effect it carries" % (what, index)
        )


# ---------------------------------------------------------------------------
# Appendix storage closure
#
# ``require_authorized_appendix_producers`` proves the producer set over lvalue
# stores it can resolve to a word. A write that names no word reaches the same
# storage and is neither proven nor refused by it:
#
#     memcpy((void *)&mailbox[33], &m, 4U);   /* the validity magic, forged */
#     memset((void *)mailbox, 0, 4U * 34U);   /* every measured word, scrubbed */
#     v14_sink(&mailbox[9]);                  /* the address, handed away */
#
# The runner's serialized record and the observation record are already closed
# this way (``require_record_storage_closed``, ``verify_observation_contract``).
# The mailbox is the one transport object that was not, so it gets the same two
# rules: its address is never taken, and it is never reached except as a
# subscript.
# ---------------------------------------------------------------------------


def require_mailbox_storage_closed(masked: str, defines: dict[str, int], what: str) -> None:
    """Refuse the appendix reached as whole storage or by an escaped address."""

    aliases = frozenset(mailbox_alias_words(masked, defines))
    names = aliases | {MAILBOX_SYMBOL}
    scan = blank_directives(masked)
    for match in _IDENTIFIER_RE.finditer(scan):
        if match.group(0) not in names:
            continue
        # The address first, because ``&mailbox[33]`` is also a subscript and the
        # subscript rule below would wave it through. ``address_of_operands``
        # cannot answer this one: the vendor writes ``(void *)&mailbox[33]``, and
        # a ``)`` immediately before the ``&`` reads there as "an operand ended",
        # so the unary address is classified as a bitwise and. Looking left from
        # the *name* has no such ambiguity -- nothing but a unary ``&`` puts an
        # ampersand directly in front of an identifier.
        cursor = match.start() - 1
        while cursor >= 0 and scan[cursor] in _INLINE_SPACE:
            cursor -= 1
        if scan[cursor : cursor + 1] == "&" and scan[cursor - 1 : cursor] != "&":
            raise fail(
                "%s takes the address of appendix word %s at offset %d: a write through it is "
                "a write the producer table cannot see, and the magic it can reach declares "
                "the other 33 words real"
                % (what, scan[match.start() : match.start() + 60].split(";")[0][:40], cursor)
            )
        cursor = match.end()
        while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:
            cursor += 1
        if scan[cursor : cursor + 1] == "[":
            continue
        raise fail(
            "%s reaches the appendix as whole storage at offset %d: %s is not a subscript, so "
            "a library call or a cast can rewrite every word the producer table proved"
            % (what, match.start(), match.group(0))
        )


# ---------------------------------------------------------------------------
# Appendix value provenance
#
# ``APPENDIX_PRODUCERS`` answers "which function wrote this word, and how many
# times". It never reads the value, so a store that satisfies every site and
# count rule can publish a number the diagnostic never measured:
#
#     mailbox[V14_MBOX_PRIMARY_RESULT] = V14_PRIMARY_OBSERVED;   /* was obs->result */
#
# That republishes a timed-out run as an observed one with the producer table
# fully satisfied -- the exact defect the observation-record table was added to
# close, one statement further down. The table below closes it at the mailbox:
# each word carries the producers the design gives it *and the expression each of
# them writes*, compared over the C token sequence so formatting is free and
# spelling is not.
# ---------------------------------------------------------------------------


def _normalized_expression(text: str) -> str:
    """``text`` as its C token sequence, so whitespace and line breaks are free."""

    return " ".join(_C_TOKEN_RE.findall(text))


APPENDIX_VALUES: dict[int, tuple[tuple[str, str], ...]] = {
    0: (("test_u85", "V14_VARIANT_ID"),),
    1: (("test_commands", "qsize_expected"),),
    2: (("test_u85", "pre_program_status"),),
    3: (("test_commands", "pre_submit_status"),),
    4: (("test_commands", "DWT -> CYCCNT"),),
    5: (("test_commands", "DWT -> CYCCNT"),),
    6: (("v14_publish_primary", "obs -> t_first"),),
    7: (("v14_publish_primary", "obs -> result"),),
    8: (("v14_publish_primary", "obs -> iterations"),),
    9: (
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "obs -> qread"),
    ),
    10: (
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "obs -> status"),
    ),
    11: (
        ("v14_publish_primary", "( obs -> qread = = qsize_expected ) ? 1U : 0U"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    12: (
        (
            "v14_publish_primary",
            "( ( obs -> status & V14_STATUS_CMD_END ) ! = 0U ) ? 1U : 0U",
        ),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    13: (
        (
            "v14_publish_primary",
            "( ( obs -> status & V14_STATUS_IRQ_RAISED ) ! = 0U ) ? 1U : 0U",
        ),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    14: (
        ("v14_publish_primary", "( obs -> status & V14_STATUS_STATE )"),
        ("v14_publish_primary", "V14_U32_INVALID"),
        ("v14_publish_primary", "V14_U32_INVALID"),
    ),
    15: (("test_commands", "converged . result"),),
    16: (("test_commands", "converged . iterations"),),
    17: (
        ("test_commands", "converged . qread"),
        ("v14_publish_failure", "V14_U32_INVALID"),
    ),
    18: (
        ("test_commands", "converged . status"),
        ("v14_publish_failure", "V14_U32_INVALID"),
    ),
    19: (
        (
            "test_commands",
            "( converged . result = = V14_CONVERGENCE_TIMEOUT ) ? 1U : 0U",
        ),
    ),
    20: (
        ("v14_publish_cleanup_failure", "V14_PHASE_CLEANUP"),
        ("v14_publish_failure", "phase"),
        ("v14_publish_success", "V14_PHASE_NONE"),
    ),
    21: (
        ("v14_publish_cleanup_failure", "V14_REASON_CLEANUP_INVARIANT"),
        ("v14_publish_failure", "reason"),
        ("v14_publish_success", "V14_REASON_NONE"),
    ),
    22: (
        ("v14_publish_cleanup_failure", "qread"),
        ("v14_publish_failure", "qread"),
        ("v14_publish_success", "V14_U32_INVALID"),
    ),
    23: (
        ("v14_publish_cleanup_failure", "status"),
        ("v14_publish_failure", "status"),
        ("v14_publish_success", "V14_U32_INVALID"),
    ),
    24: (("test_u85", "NVIC_GetVector ( NPU0_IRQn )"),),
    25: (("test_u85", "NVIC_GetEnableIRQ ( NPU0_IRQn )"),),
    26: (("test_u85", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    27: (("test_u85", "NVIC_GetActive ( NPU0_IRQn )"),),
    28: (("test_u85", "irq_triggered ? 1U : 0U"),),
    29: (("test_commands", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    30: (("test_commands", "NVIC_GetPendingIRQ ( NPU0_IRQn )"),),
    31: (("test_commands", "NVIC_GetActive ( NPU0_IRQn )"),),
    32: (("test_commands", "irq_triggered ? 1U : 0U"),),
    33: (("v14_mailbox_publish", "V14_MAILBOX_VALID"),),
}


def _value_text(pairs: tuple[tuple[str, str], ...]) -> str:
    return ", ".join("%s <- %s" % (owner, value) for owner, value in pairs)


def require_appendix_value_provenance(
    vendor_masked: str, defines: dict[str, int]
) -> int:
    """Refuse an appendix word published from a value the design does not give it."""

    aliases = mailbox_alias_words(vendor_masked, defines)
    observed: dict[object, list[tuple[str, str]]] = {}
    for word, _token, value, owner in _resolved_mailbox_stores(
        vendor_masked, defines, aliases
    ):
        if owner == MAILBOX_RESET_SYMBOL:
            continue
        observed.setdefault(word, []).append((owner, _normalized_expression(value)))
    for index in range(APPENDIX_WORDS):
        expected = APPENDIX_VALUES[index]
        found = tuple(sorted(observed.get(index, ())))
        if found != tuple(sorted(expected)):
            raise fail(
                "appendix word %d (%s) is not published from the value the design gives it: "
                "found %s, expected %s"
                % (
                    index,
                    APPENDIX_FIELDS[index],
                    _value_text(found) or "no store outside the mailbox reset",
                    _value_text(tuple(sorted(expected))),
                )
            )
    return sum(len(pairs) for pairs in observed.values())


# ---------------------------------------------------------------------------
# Publication call provenance
#
# Words 20..23 are copies of ``v14_publish_failure``'s parameters, so the value
# table above proves them only as far as the call site. The label a failure is
# published under is decided there:
#
#     v14_publish_failure(V14_PHASE_PRIMARY, V14_REASON_NONE, ...);   /* accepted */
#
# publishes a primary timeout with no reason, and swapping the cleanup branch's
# ``v14_publish_cleanup_failure`` for ``v14_publish_success`` publishes a clean
# run while the vendor return code says the cleanup invariant failed. The design
# gives every publication site one argument tuple; the table is that set.
# ---------------------------------------------------------------------------

# The parenthesis is deliberately not part of the match. A symbol that is not
# followed by one is the same defect with the call removed rather than hidden:
# ``(void)(&v14_publish_failure);`` names a publisher this table never reads,
# and a name it can reach is a call this gate cannot see the arguments of.
_PUBLICATION_SYMBOL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(v14_publish_failure|v14_publish_cleanup_failure|v14_publish_success)"
    r"(?![A-Za-z0-9_])"
)


def _publication_call_sites(vendor_masked: str) -> tuple[tuple[int, str, str], ...]:
    """``(site, callee, arguments)`` for every publication *call* statement.

    The argument list is bounded by the matching parenthesis rather than by a
    ``[^;]*`` run, because such a run walks straight out of a definition's
    parameter list and into the first ``);`` inside its body -- which is how the
    definition of ``v14_publish_failure`` reads as a call to itself. A call is
    then separated from a definition by what follows the ``)``: a ``;`` ends a
    statement, a ``{`` opens a body.

    A forward declaration ends in ``;`` exactly as a call statement does, so the
    two are separated by what *precedes* the name instead: a prototype is
    introduced by its return type, and nothing but a type name or a ``*`` can sit
    directly in front of a declarator. A call statement is preceded by ``;``,
    ``{``, ``}`` or the ``)`` of the branch that reaches it.
    """

    return tuple(
        (site, callee, arguments)
        for site, callee, arguments, is_call in _publication_symbol_sites(vendor_masked)
        if is_call
    )


def _publication_symbol_sites(
    vendor_masked: str,
) -> tuple[tuple[int, str, str, bool], ...]:
    """``(site, callee, arguments, is_call_statement)`` for every publication symbol.

    A symbol that is neither a definition nor a prototype but whose ``)`` is not
    followed by ``;`` is reported here with ``is_call_statement`` false rather
    than dropped, because dropping it is what let a live publication call hide
    behind one pair of parentheses:

        (void)(v14_publish_failure(V14_PHASE_NONE, V14_REASON_NONE, ...));

    That overwrites every verdict the run reached with a clean tuple, republishes
    the magic, and leaves ``publication_calls_with_proven_arguments`` at the
    number the design's own call sites produce.
    """

    close_of, _open_of = _bracket_pairs(vendor_masked)
    found: list[tuple[int, str, str, bool]] = []
    for match in _PUBLICATION_SYMBOL_RE.finditer(vendor_masked):
        cursor = match.start() - 1
        while cursor >= 0 and vendor_masked[cursor] in _INLINE_SPACE:
            cursor -= 1
        if cursor >= 0 and (
            _NAME_CHARACTER_RE.match(vendor_masked[cursor]) or vendor_masked[cursor] == "*"
        ):
            continue
        cursor = match.end()
        while cursor < len(vendor_masked) and vendor_masked[cursor] in _INLINE_SPACE:
            cursor += 1
        if vendor_masked[cursor : cursor + 1] != "(":
            # The symbol reached without a parameter list at all -- its address,
            # or a bare mention. It publishes nothing on its own and it hands
            # the publisher somewhere no argument rule below can follow.
            found.append((match.start(), match.group(1), "", False))
            continue
        open_index = cursor
        close_index = close_of.get(open_index)
        if close_index is None:
            found.append((match.start(), match.group(1), "", False))
            continue
        cursor = close_index + 1
        while cursor < len(vendor_masked) and vendor_masked[cursor] in _INLINE_SPACE:
            cursor += 1
        found.append(
            (
                match.start(),
                match.group(1),
                vendor_masked[open_index + 1 : close_index],
                vendor_masked[cursor : cursor + 1] == ";",
            )
        )
    return tuple(found)

PUBLICATION_CALLS: dict[str, tuple[tuple[str, str], ...]] = {
    "test_u85": (
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_STATE_RUNNING , V14_U32_INVALID , V14_U32_INVALID",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_STATE_RUNNING , V14_U32_INVALID , pre_program_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_RESET_IN_PROGRESS , V14_U32_INVALID , pre_program_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_PROGRAM , V14_REASON_HARDWARE_FAULT , V14_U32_INVALID , pre_program_status",
        ),
    ),
    "test_commands": (
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_QSIZE_MISMATCH , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STATE_RUNNING , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_RESET_IN_PROGRESS , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_HARDWARE_FAULT , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STALE_IRQ , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRE_SUBMIT , V14_REASON_STALE_CMD_END , V14_U32_INVALID , pre_submit_status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_RESET_IN_PROGRESS , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_HARDWARE_FAULT , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_PRIMARY , V14_REASON_PRIMARY_TIMEOUT , primary . qread , primary . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_RESET_IN_PROGRESS , converged . qread , converged . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_HARDWARE_FAULT , converged . qread , converged . status",
        ),
        (
            "v14_publish_failure",
            "V14_PHASE_CONVERGENCE , V14_REASON_CONVERGENCE_TIMEOUT , converged . qread , converged . status",
        ),
        ("v14_publish_cleanup_failure", "( uint32_t ) read_val , converged . status"),
        ("v14_publish_success", ""),
    ),
}


def require_publication_call_provenance(vendor_masked: str) -> int:
    """Refuse a publication call whose argument tuple is not the design's."""

    # A symbol that is not a definition, not a prototype and not a call
    # *statement* is a live publication this table never reads, so it is refused
    # here rather than skipped by the walk that builds the table.
    for site, callee, _arguments, is_call in _publication_symbol_sites(vendor_masked):
        if not is_call:
            raise fail(
                "a publication symbol appears outside a proven call site: %s at offset %d is "
                "neither a definition nor a call statement, so the tuple it publishes is one no "
                "argument rule in this file reads" % (callee, site)
            )
    spans = function_spans(vendor_masked)
    observed: dict[str, list[tuple[str, str]]] = {}
    for site, callee, arguments in _publication_call_sites(vendor_masked):
        owner = enclosing_function(spans, site)
        observed.setdefault(owner, []).append(
            (callee, _normalized_expression(arguments))
        )
    for owner in sorted(set(observed) | set(PUBLICATION_CALLS)):
        expected = tuple(sorted(PUBLICATION_CALLS.get(owner, ())))
        found = tuple(sorted(observed.get(owner, ())))
        if found != expected:
            missing = [pair for pair in expected if pair not in found]
            extra = [pair for pair in found if pair not in expected]
            raise fail(
                "a publication call does not carry the argument tuple the design gives it in "
                "%s: missing %s, unexpected %s"
                % (
                    owner or "file scope",
                    _value_text(tuple(missing)) or "none",
                    _value_text(tuple(extra)) or "none",
                )
            )
    return sum(len(calls) for calls in observed.values())


# The cleanup epilogue decides which tuple the mailbox carries and which code the
# vendor returns, and the two have to agree: publishing success from the branch
# that detected the cleanup invariant hands the host a clean run.
_CLEANUP_EPILOGUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])if\s*\(\s*ret_code\s*!=\s*0\s*\)\s*\{([^{}]*)\}\s*else\s*\{([^{}]*)\}"
)
# The design's own stores to the vendor return code. Counting *every* store in
# the function was calibrated against a hand-written stand-in whose command
# function was a fraction of the real one; the frozen vendor also assigns
# ret_code four times in its eU85_TEST0 pin-toggle diagnostic, on a branch the
# measured path never takes. Raising the number to match would have been fitting
# the rule to whatever the source happened to contain. What the design actually
# owns is one store per epilogue arm, and that is what is counted.
COMMAND_V14_RETURN_CODES = ("V14_RET_CLEANUP_INVARIANT", "V14_RET_SUCCESS")
# Every verdict the design defines, so a store of one the epilogue does not own
# is refused by name rather than by arithmetic on a count.
_V14_RETURN_CONSTANTS = tuple(sorted("V14_RET_%s" % name for name in VENDOR_RETURN))
# And across the entry function that returns it to the host: the initialisation
# and the one store that carries the command function's verdict out.
ENTRY_SYMBOL = "test_u85"
ENTRY_RETURN_CODE_ASSIGNMENTS = 2


def require_cleanup_epilogue(command: str) -> None:
    """Prove the cleanup branch publishes its own tuple and lands its own code."""

    match = _CLEANUP_EPILOGUE_RE.search(command)
    if match is None:
        raise fail(
            "the cleanup epilogue is not the design's ret_code branch: the failure and success "
            "tails are not two arms of one if/else on ret_code"
        )
    for arm, publisher, code, label in (
        (match.group(1), "v14_publish_cleanup_failure", "V14_RET_CLEANUP_INVARIANT", "failure"),
        (match.group(2), "v14_publish_success", "V14_RET_SUCCESS", "success"),
    ):
        if not code_contains(arm, publisher + "("):
            raise fail(
                "a publication call does not carry the argument tuple the design gives it in "
                "the cleanup %s arm: %s is not the publisher it calls" % (label, publisher)
            )
        if not code_contains(arm, "ret_code = " + code):
            raise fail(
                "the cleanup-failure branch does not land its own return code: the %s arm does "
                "not assign %s" % (label, code)
            )
        # Presence is not exclusivity. A second store to the same name walks
        # straight past the check above, and only the last one decides what the
        # host is told -- so the mailbox says CLEANUP_INVARIANT while the vendor
        # returns SUCCESS, which is the disagreement this rule exists to refuse.
        writes = [
            lvalue
            for _start, lvalue, _rvalue in assignment_statements(arm)
            if names_identifier(lvalue, "ret_code")
        ]
        if len(writes) != 1:
            raise fail(
                "the cleanup %s arm assigns ret_code more than once: %d assignments reach the "
                "vendor return code, and only the last one decides what the host is told"
                % (label, len(writes))
            )
        if compound_assignment_targets(arm, ("ret_code",)):
            raise fail(
                "the cleanup %s arm assigns ret_code more than once: a read-modify-write reaches "
                "the vendor return code after the assignment this rule proved" % label
            )
    require_v14_return_codes_settled(command, "command", COMMAND_V14_RETURN_CODES)


# Exclusivity *within* each epilogue arm is only a proof while the arms are the
# last word. The epilogue is not the end of the function and the command
# function is not the end of the call chain, so a store one statement further
# down -- in either frame -- overwrites whichever arm ran with every rule above
# satisfied: ``ret_code &= 0;`` republishes a detected cleanup invariant as
# V14_RET_SUCCESS while the mailbox still carries the failure tuple. The return
# code is therefore settled over each whole function that owns one: the design's
# assignments, and never a read-modify-write.
def _return_code_writes(body: str):
    return [
        (start, rvalue)
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, "ret_code")
    ]


def require_return_code_settled(body: str, what: str, expected: int) -> None:
    """Refuse a return code rewritten after the branch that decided it."""

    if compound_assignment_targets(body, ("ret_code",)):
        raise fail(
            "the %s function reaches ret_code through a read-modify-write: the value the vendor "
            "returns is then not the one the branch that detected the outcome assigned, and the "
            "mailbox tuple and the return code stop agreeing" % what
        )
    writes = _return_code_writes(body)
    if len(writes) != expected:
        raise fail(
            "the %s function assigns ret_code %d times: the design assigns it %d, and a further "
            "assignment reaches the vendor return code after the branch that decided it"
            % (what, len(writes), expected)
        )


# Every way of reaching ret_code that is not a plain assignment.
_RET_CODE_STEP_RE = re.compile(
    r"(?:\+\+|--)\s*ret_code|ret_code\s*(?:\+\+|--|<<=|>>=|[-+*/%&|^]=)"
)
# The only one the frozen vendor uses. It is not counted: an increment cannot
# produce V14_RET_SUCCESS from any verdict -- the codes are 0..7 and stepping
# moves away from zero -- so a second one forges nothing. The operators that can
# forge a verdict are the ones that clear or overwrite, and those are refused.
_FROZEN_ENTRY_STEP = "ret_code++"


def require_entry_return_code_frozen(body: str, what: str) -> None:
    """Hold the entry frame's return code to the frozen vendor's own handling.

    The entry frame is the vendor's, not the design's: it rewrites ret_code after
    the command function has returned, and refusing that refuses the frozen file.
    What must still be refused is a store the frozen vendor does not make, because
    that is how a forged verdict gets one frame further out -- ``ret_code &= 0``
    to mask a failure to success, or a V14 verdict assigned where no V14 branch
    decided one.
    """

    steps = [hit.group(0).replace(" ", "") for hit in _RET_CODE_STEP_RE.finditer(body)]
    foreign = [step for step in steps if step != _FROZEN_ENTRY_STEP]
    if foreign:
        raise fail(
            "the %s function reaches ret_code through a read-modify-write the frozen vendor does "
            "not make (%s): the value returned is then not the one the branch that detected the "
            "outcome assigned" % (what, foreign[0])
        )
    for _start, rvalue in _return_code_writes(body):
        named = [c for c in _V14_RETURN_CONSTANTS if names_identifier(rvalue, c)]
        if named:
            raise fail(
                "the %s function assigns %s: no V14 branch decides a verdict in this frame, so a "
                "store of one forges the command function's" % (what, named[0])
            )


def require_v14_return_codes_settled(body: str, what: str, codes) -> None:
    """Refuse a V14 verdict written more than once, or through a read-modify-write.

    This is the part of "the return code is settled" that reading characters can
    decide. The rest of it -- that no later store overwrites the arm that ran --
    is an ordering claim over a function the frozen vendor also writes to on
    branches of its own, and it is bound on the linked image instead.
    """

    if compound_assignment_targets(body, ("ret_code",)):
        raise fail(
            "the %s function reaches ret_code through a read-modify-write: the value the vendor "
            "returns is then not the one the branch that detected the outcome assigned, and the "
            "mailbox tuple and the return code stop agreeing" % what
        )
    writes = _return_code_writes(body)
    for code in codes:
        carrying = [rvalue for _start, rvalue in writes if names_identifier(rvalue, code)]
        if len(carrying) != 1:
            raise fail(
                "the %s function assigns %s %d times: the design assigns it once, in the epilogue "
                "arm that decided it" % (what, code, len(carrying))
            )
    # A V14 verdict the design does not own has no arm behind it.
    for _start, rvalue in writes:
        named = [c for c in _V14_RETURN_CONSTANTS if names_identifier(rvalue, c)]
        if named and not any(c in codes for c in named):
            raise fail(
                "the %s function assigns %s, which is not one of the design's epilogue verdicts: %s"
                % (what, named[0], ", ".join(codes))
            )


# ---------------------------------------------------------------------------
# The return expressions
#
# Settling the variable is not settling the verdict. Every rule above reads an
# *assignment*, and the host is handed whatever the ``return`` evaluates -- so
# the two need not be the same value at all:
#
#     ret_code = V14_RET_CLEANUP_INVARIANT;   /* the arm rules are satisfied */
#     ...
#     return V14_RET_SUCCESS;                 /* and this is what ships      */
#
# ``return (ret_code != 0) ? V14_RET_SUCCESS : ret_code`` and ``return
# ret_code & 0`` are the same forgery with the constant moved inside an
# operator, and the second is a read-modify-write that
# ``compound_assignment_targets`` cannot see because it is not an assignment.
#
# Each function that carries a vendor return code is therefore pinned to the
# multiset of return expressions the design gives it, compared over the C token
# sequence so formatting is free and spelling is not -- the same shape as
# ``APPENDIX_VALUES`` and ``PUBLICATION_CALLS``. An early exit swapped for a
# different code is refused by the same table.
# ---------------------------------------------------------------------------

_RETURN_STATEMENT_RE = re.compile(r"(?<![A-Za-z0-9_])return\b([^;]*);")
_IF_HEAD_OPEN_RE = re.compile(r"(?<![A-Za-z0-9_])if\s*\(")

# A *bag* of return expressions pins which codes appear and never which guard
# produced which, so any permutation among the arms is accepted: the reset arm
# returns HARDWARE_FAULT and the fault arm returns RESET_IN_PROGRESS with the
# multiset unchanged. The design gives those two separate failure classes and
# fixes their priority -- reset checked before fault -- and the host's
# disposition keys off the class.
#
# So the table is an ordered sequence of ``(guard condition, return
# expression)`` pairs, compared position by position over the C token sequence.
# Order is the priority, the pairing is the binding, and a permutation changes
# both. The fall-through returns carry an empty condition: they are reached when
# no guard in their block matched, which is a position in the sequence rather
# than a predicate.
RETURN_BINDINGS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "test_commands": (
        ((
            "qsize_expected ! = V14_QSIZE_EXPECTED",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_STATE ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_RESET ) ! = 0U",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "( pre_submit_status & V14_STATUS_FAULT_MASK ) ! = 0U",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "( pre_submit_status & V14_STATUS_IRQ_RAISED ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "( pre_submit_status & V14_STATUS_CMD_END ) ! = 0U",
        ), "V14_RET_PRE_SUBMIT_FAILURE"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
            "primary . result = = V14_PRIMARY_RESET",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
            "primary . result = = V14_PRIMARY_FAULT",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "primary . result ! = V14_PRIMARY_OBSERVED",
        ), "V14_RET_PRIMARY_TIMEOUT"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
            "converged . result = = V14_CONVERGENCE_RESET",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
            "converged . result = = V14_CONVERGENCE_FAULT",
        ), "V14_RET_HARDWARE_FAULT"),
        ((
            "converged . result ! = V14_CONVERGENCE_SUCCESS",
        ), "V14_RET_CONVERGENCE_TIMEOUT"),
        ((), "ret_code"),
    ),
    "test_u85": (
        ((
            "( pmu_completion_visibility_v14_mailbox [ V14_MBOX_INSTALLED_VECTOR ] ! = ( uint32_t ) & u85_irq_handler ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_ENABLED_BEFORE_SUBMIT ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT ] ! = 0U ) | | ( pmu_completion_visibility_v14_mailbox [ V14_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT ] ! = 0U )",
        ), "V14_RET_PRE_PROGRAM_FAILURE"),
        ((
            "( pre_program_status & V14_STATUS_STATE ) ! = 0U",
        ), "V14_RET_PRE_PROGRAM_FAILURE"),
        ((
            "( pre_program_status & V14_STATUS_RESET ) ! = 0U",
        ), "V14_RET_RESET_IN_PROGRESS"),
        ((
            "( pre_program_status & V14_STATUS_FAULT_MASK ) ! = 0U",
        ), "V14_RET_HARDWARE_FAULT"),
        ((), "ret_code"),
    ),
}


def _enclosing_guards(
    body: str, position: int, defines: dict[str, int]
) -> tuple[str, ...]:
    """Every ``if`` condition whose block encloses ``position``, outermost first.

    Reading only the *innermost* guard records a pair that an extra enclosing
    guard leaves byte-identical while changing which arm runs first. Wrapping
    the reset arm in ``if ((status & FAULT_MASK) == 0U)`` inverts a priority the
    design fixes -- a status carrying both bits returns HARDWARE_FAULT where the
    design returns RESET_IN_PROGRESS -- so the whole chain is the binding, and
    its depth is part of it.

    A guard this gate can fold to a non-zero constant is not a branch: ``if
    (1)`` selects nothing and reorders nothing, so it is dropped from the chain
    rather than recorded as a level. The walk continues outward past it, so a
    real guard wrapped in a vacuous one is still seen. Only a condition that
    folds -- the same evaluator the value tables use -- earns that; one this
    gate cannot read stays in the chain, which is the fail-closed answer.
    """

    found: list[str] = []
    cursor = position
    budget = len(body)
    for _step in range(budget):
        start = enclosing_block_start(body, cursor)
        if start <= 0:
            break
        head = body[: start - 1]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            break
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None:
            break
        # A block that opens on something other than the guard it follows -- an
        # ``else`` arm, a loop body -- has other text between the ``)`` and the
        # ``{``, and reading its condition as this return's guard would bind the
        # wrong predicate. Only an immediately-following block is the guard's own.
        if head[close + 1 :].strip():
            break
        condition = head[opener.end() : close]
        folded = _evaluate_constant(condition, defines)
        if folded is None or folded == 0:
            found.append(_normalized_expression(condition))
        cursor = opener.start()
    return tuple(reversed(found))


def return_bindings(
    body: str, defines: dict[str, int]
) -> tuple[tuple[tuple[str, ...], str], ...]:
    """``(guard chain, return expression)`` for every return, in source order."""

    return tuple(
        (
            _enclosing_guards(body, match.start(), defines),
            _normalized_expression(match.group(1)),
        )
        for match in _RETURN_STATEMENT_RE.finditer(body)
    )


def _binding_text(pairs: tuple[tuple[tuple[str, ...], str], ...], index: int) -> str:
    if index >= len(pairs):
        return "nothing"
    chain, expression = pairs[index]
    return "%s -> %s" % (" && ".join(chain) or "the fall-through", expression)


def require_return_expression_provenance(
    body: str, name: str, what: str, defines: dict[str, int]
) -> int:
    """Refuse a function whose guards do not return the codes the design binds them to."""

    expected = RETURN_BINDINGS[name]
    found = return_bindings(body, defines)
    if found != expected:
        index = next(
            (
                position
                for position in range(max(len(expected), len(found)))
                if position >= len(found)
                or position >= len(expected)
                or found[position] != expected[position]
            ),
            0,
        )
        raise fail(
            "the %s function does not return the value the design returns: at return %d it "
            "carries %s, and the design binds %s -- the failure class the host is handed is "
            "decided by the guard that detected it, so the codes are not permutable among the "
            "arms"
            % (what, index, _binding_text(found, index), _binding_text(expected, index))
        )
    return len(found)


# ---------------------------------------------------------------------------
# The convergence tail, held to the primary's standard
#
# The primary helper's classifier is proven term by term. The convergence
# helper's was not, so a hardware fault could be published as a benign timeout,
# ``iterations`` could be a constant, and the published tuple did not have to be
# the one the loop's own iteration read:
#
#     uint32_t status_prev = status;
#     qread = *qread_reg; status = *status_reg;
#     status = status_prev;            /* iteration i-1's status, iteration i's qread */
# ---------------------------------------------------------------------------

CONVERGENCE_CLASSIFIER = (
    ("V14_STATUS_RESET", "V14_CONVERGENCE_RESET"),
    ("V14_STATUS_FAULT_MASK", "V14_CONVERGENCE_FAULT"),
)


def require_convergence_classification(converge_body: str) -> None:
    """Prove each convergence category is bound to the condition that decides it."""

    guards = _guard_blocks(converge_body, "status")
    for mask, expected in CONVERGENCE_CLASSIFIER:
        matching = [body for condition, body in guards if names_identifier(condition, mask)]
        if len(matching) != 1:
            raise fail(
                "the convergence classifier does not bind %s to one guard: %d guards name %s"
                % (expected, len(matching), mask)
            )
        if not code_contains(matching[0], "result = " + expected):
            raise fail(
                "the convergence classifier does not bind %s to its own condition: the %s "
                "guard lands a different category" % (expected, mask)
            )
    success = [
        body
        for condition, body in _guard_blocks(converge_body, "qsize_expected")
        if names_identifier(condition, "V14_STATUS_CMD_END")
    ]
    if len(success) != 1:
        raise fail(
            "the convergence classifier does not bind V14_CONVERGENCE_SUCCESS to one guard: "
            "%d completion guards" % len(success)
        )
    if not code_contains(success[0], "result = V14_CONVERGENCE_SUCCESS"):
        raise fail(
            "the convergence classifier does not bind V14_CONVERGENCE_SUCCESS to its own "
            "condition: the completion guard lands a different category"
        )
    if not code_contains(success[0], "iterations = i"):
        raise fail(
            "the convergence classifier does not bind the iteration count to the loop "
            "induction variable: iterations is not set from i"
        )


def require_convergence_same_iteration(loop_body: str) -> None:
    """Prove the published convergence tuple is the one this iteration read."""

    for name in ("qread", "status"):
        writes = [
            lvalue
            for _start, lvalue, _rvalue in assignment_statements(loop_body)
            if names_identifier(lvalue, name) and not _is_declaration(lvalue)
        ]
        if len(writes) != 1:
            raise fail(
                "the convergence tuple is not the one the loop's own iteration read: %s is "
                "assigned %d times in the loop body, so a value from an earlier iteration can "
                "reach the publication" % (name, len(writes))
            )


# ---------------------------------------------------------------------------
# The runner's validity handshake
#
# Word 33 is what tells the host the other 33 words are real. The runner's copy
# is gated on it, and the gate proved the *shape* of that comparison without
# proving the polarity of what each arm sets -- so inverting one assignment
# reported a mailbox that never reached publication as a valid transport.
# ---------------------------------------------------------------------------

TRANSPORT_VALID_SYMBOL = "pmu_diag_v14_transport_valid"
# The design's own stores to the transport flag, across the whole runner: the
# reset clears it, and the mailbox-magic branch settles it one way per arm.
RUNNER_TRANSPORT_ASSIGNMENTS = 3
# The runner function that re-arms the transport before a run, and the value the
# design gives its store. The count above pins how many stores reach the flag
# and the arm rule pins the polarity of one of them; neither reads the reset's
# value, so ``pmu_diag_v14_transport_valid = 1U`` in the reset keeps the count
# at three, keeps the arm's clear intact, and leaves the flag asserted for every
# window between a reset and the branch that settles it.
TRANSPORT_INVALID_VALUE = "0U"
# The *value* the clear has to land, not the text it has to contain. Proving the
# store by substring proves nothing about what it evaluates to: every
# initialiser that merely *begins* with ``0U`` -- ``0U + 1U``, ``0U | 1U``,
# ``0U ? 0U : 1U`` -- contains the literal ``pmu_diag_v14_transport_valid = 0U``
# while storing one, which leaves the flag asserted for the whole window between
# the reset and the branch that settles it. That is the defect this rule was
# written to close, one token to the right of the fix.
TRANSPORT_CLEARED = 0

_MAILBOX_MAGIC_GUARD_RE = re.compile(
    r"(?<![A-Za-z0-9_])if\s*\(\s*%s\s*\[\s*%d\s*\]\s*!=\s*V14_MAILBOX_VALID\s*\)"
    % (re.escape(MAILBOX_SYMBOL), APPENDIX_FIELDS.index("mailbox_valid"))
)


# A statement that leaves the block, and the heads whose bodies ``break`` and
# ``continue`` belong to.
_CONTROL_TRANSFER_RE = re.compile(
    r"(?<![A-Za-z0-9_])(return|goto|break|continue)(?![A-Za-z0-9_])"
)
_LOOP_OR_SWITCH_KEYWORDS = frozenset(("for", "while", "switch"))


def _opens_loop_or_switch(body: str, open_index: int) -> bool:
    """Whether the block opening at ``open_index`` is a loop or ``switch`` body.

    The head is read by matching its parenthesis rather than by a pattern, because
    a ``for`` header carries its own semicolons and any expression the source
    likes -- a regex bounded on ``;`` misses exactly the loop this has to see.
    """

    head = body[:open_index].rstrip()
    if head.endswith("do"):
        return _token_before(head, len(head))[1] == "do"
    if not head.endswith(")"):
        return False
    open_paren = _bracket_pairs(head)[1].get(len(head) - 1)
    if open_paren is None:
        return False
    return _token_before(head, open_paren)[1] in _LOOP_OR_SWITCH_KEYWORDS


def _enclosing_blocks(body: str, position: int) -> tuple[tuple[int, int], ...]:
    """``(open brace, just-inside offset)`` for each block enclosing ``position``."""

    stack: list[tuple[int, int]] = []
    for index in range(min(position, len(body))):
        character = body[index]
        if character == "{":
            stack.append((index, index + 1))
        elif character == "}" and stack:
            stack.pop()
    return tuple(reversed(stack))


def _is_unreachable_here(body: str, position: int, defines: dict[str, int]) -> bool:
    """Whether some block enclosing ``position`` is an ``if`` that folds to zero."""

    for open_index, _inside in _enclosing_blocks(body, position):
        head = body[:open_index]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            continue
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None or head[close + 1 :].strip():
            continue
        if _evaluate_constant(head[opener.end() : close], defines) == 0:
            return True
    return False


def _transfer_stays_inside(body: str, offset: int, position: int) -> bool:
    """Whether a ``break``/``continue`` at ``offset`` is spent before ``position``.

    A loop that runs to completion ahead of the store cannot skip it, so its own
    ``break`` is not a bypass. One whose block still encloses the store is.
    """

    for open_index, _inside in _enclosing_blocks(body, offset):
        if not _opens_loop_or_switch(body, open_index):
            continue
        return _matching_brace(body, open_index, "loop body") < position
    return False


def _reaches_without_transfer(
    body: str, position: int, defines: dict[str, int]
) -> bool:
    """Whether no reachable control transfer precedes ``position`` in ``body``.

    Checking the blocks that *enclose* the store leaves every statement *before*
    it unexamined, and an early exit there skips an otherwise-unguarded clear
    while every enclosing block stays trivially acceptable -- ordinary
    warning-clean C, no dead code. Every transfer in the prefix therefore has to
    be discharged: one this gate can prove unreachable, or a ``break``/
    ``continue`` whose loop is over before the store. Anything else, including a
    ``goto`` whose label this gate does not resolve, is a bypass.
    """

    prefix = blank_directives(body[:position])
    for match in _CONTROL_TRANSFER_RE.finditer(prefix):
        if _is_unreachable_here(body, match.start(), defines):
            continue
        if match.group(1) in ("break", "continue") and _transfer_stays_inside(
            body, match.start(), position
        ):
            continue
        return False
    return True


def _executes_unconditionally(body: str, position: int, defines: dict[str, int]) -> bool:
    """Whether the statement at ``position`` runs on every path through ``body``.

    Proving the clearing store *exists* is not proving it *happens*: wrapping it
    in ``if (0)`` leaves a store that folds to zero and never executes, so the
    flag is never cleared and the run window carries whatever the last one left.
    A store is on the must-execute path when every block enclosing it is an
    ``if`` whose condition folds to a non-zero constant -- a guard that selects
    nothing -- and it is not on that path when a block is an ``else`` arm, a
    loop, or an ``if`` this gate cannot fold.

    The enclosing blocks are only half of it: a transfer that *precedes* the
    store skips it without touching any of them, so the prefix is walked too.
    """

    if not _reaches_without_transfer(body, position, defines):
        return False
    cursor = position
    for _step in range(len(body)):
        start = enclosing_block_start(body, cursor)
        if start <= 0:
            return True
        head = body[: start - 1]
        opener = None
        for match in _IF_HEAD_OPEN_RE.finditer(head):
            opener = match
        if opener is None:
            return False
        close = _bracket_pairs(head)[0].get(opener.end() - 1)
        if close is None or head[close + 1 :].strip():
            # An ``else`` arm or a loop body: text sits between the guard's
            # ``)`` and this block's ``{``, so the block is not the guard's own.
            return False
        folded = _evaluate_constant(head[opener.end() : close], defines)
        if folded is None or folded == 0:
            return False
        cursor = opener.start()
    return False


def _mailbox_magic_branch(runner_masked: str) -> tuple[int, int]:
    """The span of the mailbox-magic ``if``/``else``, arms included.

    Everything inside it is the polarity rule's to judge; everything outside it
    settles the flag before the run and is judged by the lifetime rule.
    """

    match = _MAILBOX_MAGIC_GUARD_RE.search(runner_masked)
    if match is None:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    open_index = runner_masked.find("{", match.end())
    if open_index < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    close_index = _matching_brace(runner_masked, open_index, "runner magic guard")
    tail = code_find(runner_masked[close_index:], "else")
    if tail < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    else_open = runner_masked.find("{", close_index + tail)
    if else_open < 0:
        raise fail("runner appendix copy is not dominated by the mailbox magic check")
    return open_index, _matching_brace(runner_masked, else_open, "runner magic else") + 1


def require_transport_reset_polarity(runner_masked: str) -> None:
    """Prove the runner's reset clears the transport flag rather than asserting it.

    The reset function is *resolved* rather than named -- it is whichever
    function calls ``v14_mailbox_reset()``, the way ``verify_pre_run_contract``
    resolves the queue setup owner. The host runner this contract is generated
    into keeps its own name for that routine, so a rule written against one
    spelling proves nothing about the file it actually runs on.

    The store is then read as a value, folded the way ``APPENDIX_VALUES`` and
    ``RETURN_EXPRESSIONS`` fold theirs, so a spelling this gate cannot fold is
    refused rather than admitted for containing the right prefix.
    """

    site = code_find(runner_masked, MAILBOX_RESET_SYMBOL + "();")
    if site < 0:
        raise fail("runner does not reset the mailbox before the measured call")
    spans = function_spans(runner_masked)
    owner = enclosing_function(spans, site)
    body_start, body_stop = next(
        (
            (start, stop)
            for name, start, stop in spans
            if name == owner and start <= site < stop
        ),
        (0, len(runner_masked)),
    )
    body = runner_masked[body_start:body_stop]
    defines = {
        name: seen[-1] for name, seen in parse_define_values(runner_masked).items()
    }
    branch_start, branch_stop = _mailbox_magic_branch(runner_masked)
    # "The first store after the reset call" is a statement about *where the
    # call is*, and the call can move. Hoisting ``v14_mailbox_reset()`` into the
    # record owner makes the magic branch's own ``= 0U`` the first store after
    # it, so that reading passes while the function that actually re-arms the
    # run asserts the flag. Three things are therefore required of the re-arm,
    # narrowest first, so a source is named by the most specific thing wrong
    # with it: the store that accompanies the call clears the flag; that store
    # is in the same function as the call; and no store anywhere outside the
    # mailbox-magic branch leaves the flag asserted.
    reset_offset = site - body_start
    stores = [
        rvalue
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL) and start >= reset_offset
    ]
    landed = [_evaluate_constant(rvalue, defines) for rvalue in stores]
    if not stores or landed[0] != TRANSPORT_CLEARED:
        raise fail(
            "the runner reset does not clear the transport flag: %s re-arms the run without "
            "storing %s to %s -- it stores %s, so a mailbox that never published is reported "
            "to the host as a valid transport for every window before the magic branch "
            "settles it"
            % (
                owner or "file scope",
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
                ", ".join(_normalized_expression(rvalue) for rvalue in stores)
                or "nothing",
            )
        )
    cleared_here = [
        start
        for start, lvalue, rvalue in assignment_statements(body)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
        and not branch_start <= body_start + start < branch_stop
        and _evaluate_constant(rvalue, defines) == TRANSPORT_CLEARED
    ]
    # A store the contract needs to *happen* is not proven by one that merely
    # *exists*. ``if (0) { pmu_diag_v14_transport_valid = 0U; }`` satisfies the
    # value and the ownership and clears nothing.
    if cleared_here and not any(
        _executes_unconditionally(body, start, defines) for start in cleared_here
    ):
        raise fail(
            "the runner does not clear the transport flag on every path: %s stores %s to %s "
            "only under a guard this gate cannot discharge, so a run whose vendor never "
            "published carries whatever the previous run left in %s"
            % (
                owner or "file scope",
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
                TRANSPORT_VALID_SYMBOL,
            )
        )
    if not cleared_here:
        raise fail(
            "the runner resets the mailbox in a function that does not clear the transport "
            "flag: %s calls %s without storing %s to %s, so the re-arm and the reset are two "
            "different windows and the flag outlives the run they belong to"
            % (
                owner or "file scope",
                MAILBOX_RESET_SYMBOL,
                TRANSPORT_INVALID_VALUE,
                TRANSPORT_VALID_SYMBOL,
            )
        )
    for start, lvalue, rvalue in assignment_statements(runner_masked):
        if not names_identifier(lvalue, TRANSPORT_VALID_SYMBOL):
            continue
        if branch_start <= start < branch_stop:
            continue
        if _evaluate_constant(rvalue, defines) != TRANSPORT_CLEARED:
            raise fail(
                "the runner asserts the transport flag outside the mailbox-magic branch: the "
                "store at offset %d lands %s rather than %s, so a mailbox that never published "
                "is reported to the host as a valid transport for the whole run window before "
                "the branch settles it"
                % (start, _normalized_expression(rvalue), TRANSPORT_INVALID_VALUE)
            )


def require_transport_validity_polarity(runner_masked: str) -> None:
    """Prove the invalid-magic arm clears the transport flag rather than setting it."""

    guards = [
        body
        for condition, body in _guard_blocks(runner_masked, MAILBOX_SYMBOL)
        if names_identifier(condition, "V14_MAILBOX_VALID")
    ]
    if len(guards) != 1:
        raise fail(
            "the runner does not gate its copy on one mailbox-magic comparison: %d guards "
            "name V14_MAILBOX_VALID" % len(guards)
        )
    if not code_contains(guards[0], TRANSPORT_VALID_SYMBOL + " = 0U"):
        raise fail(
            "the runner sets transport_valid on an invalid mailbox magic: the arm taken when "
            "word 33 is not the magic does not clear %s, so a run that never published is "
            "reported to the host as a valid transport" % TRANSPORT_VALID_SYMBOL
        )
    # And clearing it is only a proof while nothing sets it again: the check
    # above asks whether the store appears, never whether it is the last one.
    writes = [
        lvalue
        for _start, lvalue, _rvalue in assignment_statements(guards[0])
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
    ]
    if len(writes) != 1 or compound_assignment_targets(guards[0], (TRANSPORT_VALID_SYMBOL,)):
        raise fail(
            "the invalid-magic arm assigns %s more than once: %d assignments reach the transport "
            "flag, and a run that never published is reported to the host as a valid transport by "
            "whichever one lands last" % (TRANSPORT_VALID_SYMBOL, len(writes))
        )
    # And the arm is only the last word while nothing outside it writes the flag
    # either. A store *after* the branch reports the transport as valid whichever
    # arm ran, with the polarity rule above fully satisfied, so the flag is
    # settled over the whole runner rather than inside one arm of it.
    if compound_assignment_targets(runner_masked, (TRANSPORT_VALID_SYMBOL,)):
        raise fail(
            "the runner reaches %s through a read-modify-write: the flag the host reads is then "
            "not the one the mailbox-magic branch assigned, and a run that never published is "
            "reported as a valid transport" % TRANSPORT_VALID_SYMBOL
        )
    unit_writes = [
        lvalue
        for _start, lvalue, _rvalue in assignment_statements(runner_masked)
        if names_identifier(lvalue, TRANSPORT_VALID_SYMBOL)
    ]
    if len(unit_writes) != RUNNER_TRANSPORT_ASSIGNMENTS:
        raise fail(
            "the runner assigns %s %d times: the design assigns it %d, and a further assignment "
            "reaches the transport flag after the mailbox-magic branch that decided it"
            % (TRANSPORT_VALID_SYMBOL, len(unit_writes), RUNNER_TRANSPORT_ASSIGNMENTS)
        )


def verify_generated_sources(runner_text: str, vendor_text: str, variant: str) -> dict[str, object]:
    """Verify a generated Q/QS/SQ source pair and return its fixture manifest."""

    if variant not in VARIANTS:
        raise fail("unknown variant %r" % variant)
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    vendor_masked = mask_c_lexical(vendor_text)
    runner_masked = mask_c_lexical(runner_text)
    # First, because every scan below -- the lexical mask included -- reads the
    # primary spelling of the punctuators. A source written with a trigraph or a
    # digraph is one this gate is tokenizing differently from the compiler, and
    # nothing derived from that reading is evidence about the built image.
    require_primary_token_spelling(vendor_text, "the vendor translation unit")
    require_primary_token_spelling(runner_text, "the runner translation unit")
    # Every rule below reads a macro's value once. That is only sound while the
    # macro holds one value for the whole translation unit, so the preprocessing
    # history is settled before anything is derived from it.
    require_stable_contract_defines(vendor_masked, "the vendor translation unit")
    require_stable_contract_defines(runner_masked, "the runner translation unit")
    # A macro body is code this gate never expands, so a store written in one is
    # a store no rule below can see. Settled here, with the rest of the
    # preprocessing history, rather than left to each rule to miss separately.
    require_no_statement_macro(vendor_masked, "the vendor translation unit")
    require_no_statement_macro(runner_masked, "the runner translation unit")
    # And a macro body that is only the *lvalue* is the same defect with the
    # store operator moved one token to the right, so it is settled here too.
    require_no_critical_lvalue_macro(vendor_masked, "the vendor translation unit")
    require_no_critical_lvalue_macro(runner_masked, "the runner translation unit")
    # And an initializer with no declarator in front of it is storage the
    # declarator walk has no name to bind, which is the same defect with the
    # name removed instead of the operator.
    require_no_compound_literal(vendor_masked, "the vendor translation unit")
    require_no_compound_literal(runner_masked, "the runner translation unit")
    # A call whose callee is an expression carries any effect past every rule
    # below, so it is settled here with the other things this gate refuses to
    # model rather than left to each counting rule to miss separately.
    # Vendor-side only. The measured path, the submit count and the register
    # confinement all live in the vendor translation unit, and the host runner
    # this contract is generated against legitimately declares an
    # ``irq_handler_t`` function pointer of its own -- refusing that would refuse
    # the stock file rather than an attack. What the runner publishes is closed
    # by its own record, copy and validity rules instead.
    require_no_function_pointer(vendor_masked, "the vendor translation unit")
    require_no_indirect_call(vendor_masked, "the vendor translation unit")
    # The runner gets the same two rules, minus the one name the stock file
    # legitimately declares. Exempting the *translation unit* was what admitted a
    # function pointer at the runner's file scope -- which, composed with a
    # publication or reset symbol taken by address, is a call this gate cannot
    # follow reaching the transport it just proved. Exempting the stock name
    # instead keeps the frozen ``irq_handler_t`` and refuses every other one.
    require_no_function_pointer(
        runner_masked, "the runner translation unit", RUNNER_STOCK_FUNCTION_POINTERS
    )
    require_no_indirect_call(runner_masked, "the runner translation unit")
    # The exemption above admits the stock vector *type*. An object of that type
    # is called with the syntax of a direct call, so the indirect-call rule
    # cannot see it and this is what refuses it.
    require_no_call_through_pointer_object(
        runner_masked,
        RUNNER_STOCK_FUNCTION_POINTERS,
        "the runner translation unit",
        RUNNER_STOCK_VECTOR_SLOTS,
    )
    defines = parse_defines(vendor_masked)

    pre_run = verify_pre_run_contract(vendor_masked, defines)
    primary = verify_primary_contract(vendor_masked, variant, defines)
    hard_bypass = verify_hard_bypass_contract(vendor_masked)
    convergence = verify_convergence_contract(vendor_masked, defines)
    mailbox = verify_mailbox_contract(vendor_masked, defines)
    # The appendix words are copies of observation-record fields, so the
    # producer table that closes the mailbox is only a proof while the record it
    # copies from is closed too.
    verify_observation_contract(vendor_masked, variant, defines)
    identity = verify_variant_identity(vendor_masked, defines, variant)
    cleanup = verify_cleanup_contract(vendor_masked, vendor_text, variant, defines)
    runner = verify_runner_contract(runner_masked)
    # Last, so a source that breaks a named rule is reported by that rule rather
    # than by the absence its breakage happens to leave behind.
    produced_words = require_every_appendix_word_produced(vendor_masked, defines)
    # Having *a* producer is the fail-silent half. Having only the producers the
    # design gives it is the fail-open one, and it runs after the specific rules
    # so a source that breaks one of them is still named by that rule.
    appendix_stores = require_authorized_appendix_producers(vendor_masked, defines)
    # And having the design's producers is still only a proof about *where*. This
    # is the proof about *what*: 28 of the 34 words accepted an attacker-chosen
    # constant while every site and count rule above stayed satisfied.
    appendix_valued = require_appendix_value_provenance(vendor_masked, defines)
    # Words 20..23 are the publisher's parameters, so their value proof ends at
    # the call site; this is where it continues.
    publication_calls = require_publication_call_provenance(vendor_masked)
    require_cleanup_epilogue(
        vendor_masked[function_span(vendor_masked, "test_commands", "command function")[0] :
                      function_span(vendor_masked, "test_commands", "command function")[1]]
    )
    # The epilogue decides the code, and this is the frame that returns it -- but
    # it is not V14's frame. The frozen vendor rewrites the same variable after
    # the command function has returned: ``ret_code = 2`` on an output-verify
    # mismatch, ``ret_code = 3`` on an IRQ-mask mismatch, and ``ret_code++`` when
    # the IRQ never fired. Demanding that this frame leave the value alone was a
    # rule the design never stated, calibrated against a stand-in vendor that had
    # none of those stores, and it cannot be satisfied without editing frozen
    # vendor code.
    #
    # It is also not load-bearing. The V14 verdict travels in the mailbox behind
    # the V14_MAILBOX_VALID magic, which is what the runner copies its phase,
    # reason and tuple from; the vendor return code only raises a telemetry flag.
    # What survives is that the two must never be confused, because the vendor's
    # codes collide numerically with V14_RET_*, so that is stated in the manifest
    # rather than enforced as a shape the vendor cannot have.
    entry_text = function_text(vendor_masked, ENTRY_SYMBOL, "entry function")
    require_entry_return_code_frozen(entry_text, "entry")
    entry_perturbing_stores = _return_code_writes(entry_text)
    # And settling the variable is not settling the verdict: the host is handed
    # whatever the ``return`` evaluates, which no assignment rule above reads.
    returned_expressions = sum(
        require_return_expression_provenance(
            function_text(vendor_masked, name, label), name, label, defines
        )
        for name, label in ((COMMAND_SYMBOL, "command"), (ENTRY_SYMBOL, "entry"))
    )
    # The appendix is a transport object like the other two, and it is the one
    # that was not closed against a write that names no word.
    require_mailbox_storage_closed(vendor_masked, defines, "the vendor translation unit")
    require_mailbox_storage_closed(runner_masked, defines, "the runner translation unit")
    require_transport_validity_polarity(runner_masked)
    # The arm rule proves the branch that settles the flag; this proves the store
    # that re-arms it before the run, which the count above left unread.
    require_transport_reset_polarity(runner_masked)
    # Last of the whole-unit rules: every NPU register named where the design
    # does not name it, which is what makes the running-path counts above
    # statements about the translation unit rather than about one function.
    setup_owner = sorted(
        {
            enclosing_function(function_spans(vendor_masked), site)
            for site in queue_programming_sites(
                vendor_masked, defines, file_scope_text(vendor_masked), function_spans(vendor_masked)
            )
        }
    )[0]
    # Before the confinement walks: a QREAD *write* is refused for what it does
    # to the queue, not for where it sits, and reporting it by owner would name
    # a source by the weaker of the two things wrong with it.
    require_no_qread_write(vendor_masked)
    # Owning the register says where it may be loaded; this says how often, so a
    # load inside an authorised owner but outside the structure that measures it
    # is refused rather than counted as nothing.
    qread_loads = require_qread_load_budget(
        vendor_masked, defines, setup_owner, variant
    )
    register_designations = require_register_confinement(vendor_masked, setup_owner, variant)
    # And the same question asked of every spelling that carries no register
    # name: a numeric offset, an absolute address, a macro alias. Without these
    # three, "confined" is a claim about the tokens ``NPU_REG_*`` rather than
    # about the translation unit the manifest says it is about.
    require_no_macro_mmio(
        vendor_masked,
        mmio_macro_names(vendor_masked),
        "the vendor translation unit",
        mmio_macro_kinds(vendor_masked),
    )
    register_accesses = require_whole_unit_mmio_confinement(
        vendor_masked, defines, setup_owner, variant
    )
    # And the third spelling: the register carried as the accessor's own
    # argument, which neither the name scan nor the address resolver reads.
    accessor_designations_confined = require_accessor_designations_confined(
        vendor_masked, defines, setup_owner, variant
    )
    # After the designation rules, so a paste that *does* name a register or an
    # offset is still reported by the rule that owns designations, and only a
    # name this gate genuinely cannot compute is reported as one.
    require_no_token_paste(vendor_masked, "the vendor translation unit")
    require_no_token_paste(runner_masked, "the runner translation unit")
    require_isr_register_values(vendor_masked, defines)
    require_wait_for_irq_unreachable(vendor_masked)
    converge_body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    require_convergence_classification(converge_body)
    # Before the count rule below, so a local the design assigns once and a
    # mutation steps is named by the stepping rule rather than by the count it
    # happens to leave intact.
    require_measured_locals_not_stepped(converge_body, "the common convergence helper")
    require_measured_locals_not_stepped(
        function_text(vendor_masked, PRIMARY_SYMBOL[variant], "primary helper"),
        "the primary helper",
    )
    require_convergence_same_iteration(
        extract_loop(converge_body, "common convergence helper")[1]
    )
    # Last of the convergence rules, so a source that breaks one of the named
    # ones above is reported by that rule rather than by the count it leaves
    # behind.
    require_convergence_declarations(converge_body, defines)
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
        # This gate is handed generated text, not the frozen inputs, so it is
        # still not the thing that checks the raw vendor pin -- the build graph's
        # frozen-input evidence and the unit suite do that against the tracked
        # firmware/Drivers/u85_driver/u85.c.
        "vendor_raw_source_verified": False,
        # The vendor rewrites its own return code after the command function has
        # returned, and its values collide numerically with V14_RET_*. The V14
        # verdict is the mailbox behind V14_MAILBOX_VALID; this code is not it,
        # and a consumer that classifies run_rc as a V14 phase is reading vendor
        # telemetry as a diagnostic result.
        "vendor_entry_return_code_stores": len(entry_perturbing_stores),
        "vendor_entry_return_code_is_not_the_v14_verdict": True,
        "residual_limitations": list(RESIDUAL_LIMITATIONS),
        "deferred_to_linked_image": list(DEFERRED_TO_LINKED_IMAGE),
        "bound_on_linked_image": list(BOUND_ON_LINKED_IMAGE),
        # Named, not proven by anyone yet. An empty list is the goal; a
        # non-empty one is what a reader of UNIT-QUALIFIED has to weigh.
        "unbound_claims": list(unbound_claims()),
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
        "common_convergence_source_sha256": normalized_digest(converge_body),
        "common_tail_source_sha256": normalized_digest(command[tail_start:]),
        # The verifier's own count of appendix words it found a producer for.
        # It equals the appendix width or the verdict was a refusal.
        "appendix_words_with_a_producer": produced_words,
        # And its own count of the stores that produced them, outside the reset.
        # A word written twice, or written where the design does not write it,
        # is a refusal rather than a larger number here.
        "appendix_stores_outside_the_reset": appendix_stores,
        # The same count taken again over the *values* those stores write. It
        # equals the store count or the verdict was a refusal, and it is what
        # separates "the design's function wrote this word" from "the design's
        # expression reached it".
        "appendix_stores_with_proven_values": appendix_valued,
        # The publication call sites whose argument tuple the verifier matched.
        "publication_calls_with_proven_arguments": publication_calls,
        # Every NPU register designation in the vendor translation unit that fell
        # inside its authorised function set. A designation outside it is a
        # refusal rather than a larger number here, so this is the whole-unit
        # scope the running-path counts above are true of.
        "vendor_register_designations_confined": register_designations,
        # And the verifier's own count of the resolved MMIO accesses it walked
        # over every function span and file scope -- the spellings that carry no
        # register name at all. An access this gate cannot pin to one register,
        # anywhere in the unit, is a refusal rather than a larger number here,
        # which is what makes the scope below a statement about the translation
        # unit rather than about the ``NPU_REG_*`` tokens in it.
        "vendor_register_accesses_confined": register_accesses,
        # And the third spelling, counted the same way: the register carried as
        # the vendor accessor's own argument. An accessor call this gate cannot
        # resolve to one register, anywhere in the unit, is a refusal rather
        # than a larger number here -- without which "confined" would still be a
        # claim about pointer expressions and ``NPU_REG_*`` tokens rather than
        # about every access the unit makes.
        "vendor_accessor_designations_confined": accessor_designations_confined,
        "register_confinement_scope": "vendor_translation_unit",
        # The verifier's own count of the return statements it matched against
        # the design's table, across the two frames that carry a vendor return
        # code. A return expression outside the table is a refusal rather than a
        # larger number here, so the settled return code and the value the host
        # is handed are the same statement.
        "vendor_return_expressions_with_proven_values": returned_expressions,
        # The verifier's own count of the QREAD accesses it walked inside the
        # owners the design authorises. An owner that loads it more often than
        # the design does is a refusal rather than a larger number here, which
        # is what makes the confinement a statement about the loads and not only
        # about the functions.
        "vendor_qread_loads_within_budget": qread_loads,
    }
    for section in (pre_run, primary, hard_bypass, convergence, mailbox, identity, cleanup, runner):
        doc.update(section)
    return doc


if __name__ == "__main__":
    sys.exit(main())
