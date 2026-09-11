"""Successor completion-visibility checker: constants."""

from __future__ import annotations

import re


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
# The functions the design lets write the mailbox at all. Everything else that
# touches the magic is reading it, and "the runner never writes the mailbox" is
# a claim of its own rather than a special case of this one.
MAILBOX_WRITER_SYMBOLS = frozenset(
    (
        "v14_mailbox_publish",
        "v14_mailbox_reset",
        "v14_publish_failure",
        "v14_publish_cleanup_failure",
        "v14_publish_success",
        "v14_publish_primary",
    )
)
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


# The whitespace a preprocessor directive may be written with. A form feed and a
# vertical tab are whitespace to the compiler exactly as a space is, so a class
# spelled ``[ \t]`` is not "directive whitespace" -- it is four of the six
# characters that spell it, and the other two are a rule this gate never sees.
_DIRECTIVE_SPACE = r"[ \t\f\v]"


_DEFINE_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*define%(sp)s+([A-Za-z_][A-Za-z0-9_]*)%(sp)s+(\S+)%(sp)s*$"
    % {"sp": _DIRECTIVE_SPACE}
)


_UNDEF_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*undef%(sp)s+([A-Za-z_][A-Za-z0-9_]*)" % {"sp": _DIRECTIVE_SPACE}
)
# The names whose value this gate reads and then reasons about. A macro outside
# these families belongs to the vendor and may be redefined freely.
_CONTRACT_DEFINE_PREFIXES = ("V14_", "NPU_REG_")


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


# One pattern for every ``#define``, because "object-like" and "function-like"
# are the same construct with and without a parameter list, and a rule that
# knows only one of them is a rule the other spelling walks around.
_MACRO_DEFINITION_RE = re.compile(
    r"(?m)^%(sp)s*#%(sp)s*define%(sp)s+([A-Za-z_]\w*)(\([^)\n]*\))?%(sp)s*(.*)$"
    % {"sp": _DIRECTIVE_SPACE}
)


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


# What a macro this gate refuses is reported as when the caller did not resolve
# its kind. The kinds are carried by ``mmio_macro_kinds`` and threaded through
# ``mmio_macro_table`` below, so this is the answer for a caller that passes a
# bare name tuple -- never a guess at a *specific* construct, which is what
# reported an accessor alias as a dereference.
_UNCLASSIFIED_MACRO_KIND = "construct"


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


# Every name a statement steps: ``n op= ...``, ``++n``/``--n``, ``n++``/``n--``.
# Built once over the operator set rather than per call over a name set, so the
# scan is one linear pass whatever the source binds.
_STEPPED_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(?:%s)"
    r"|(?:\+\+|--)\s*([A-Za-z_]\w*)(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(?:\+\+|--)"
    % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
)


# A directive is a *logical* line, so a backslash continuation carries it on.
# Blanking only the first physical line of a continued ``#define`` deletes the
# parentheses it opened and leaves the ones its continuation closes.
_DIRECTIVE_LINE_RE = re.compile(
    r"(?m)^%s*#(?:\\[ \t]*\n|[^\n])*" % _DIRECTIVE_SPACE
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


_COMPOUND_LVALUE_RE = re.compile(
    r"(?:%s)" % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
)
_STEP_RE = re.compile(r"\+\+|--")


# An operator that *stores*. The comparisons are excluded by construction: the
# character before an ``=`` that makes it something other than a plain
# assignment is the same set ``assignment_statements`` already reads.
_MACRO_STORE_RE = re.compile(
    r"(?<![=!<>+\-*/%%&|^])=(?!=)|\+\+|--|(?:%s)"
    % "|".join(re.escape(operator) for operator in _COMPOUND_ASSIGN_OPERATORS)
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


# The assignment form of a binding, recovered by scanning for the operator
# rather than by one pattern that runs to the statement terminator.
# ``T *const a = <addr>, *const b = a;`` is *two* bindings in one statement, and
# a pattern anchored on ``;`` matches it once -- binding ``a`` to the whole
# ``<addr>, *const b = a`` tail and consuming ``b``'s binding with it, so every
# dereference of ``b`` resolved to nothing at all. The scan below finds each
# operator independently and reads only as far as the clause it belongs to.
_ASSIGNMENT_OPERATOR_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*=(?!=)")


_INLINE_SPACE = " \t\n\r\f\v"


_TYPE_NAME_TOKEN_RE = re.compile(r"^[A-Za-z_]\w*$")


_BRACKET_OPENERS = {")": "(", "]": "["}


_CMD_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])write_reg\s*\(\s*NPU_REG_CMD(?![A-Za-z0-9_])\s*,([^;]*?)\)\s*;"
)


_PRE_SUBMIT_GATES = (
    ("V14_STATUS_STATE", "stopped"),
    ("V14_STATUS_IRQ_RAISED", "stale irq_raised"),
    ("V14_STATUS_RESET", "reset_status"),
    ("V14_STATUS_CMD_END", "stale cmd_end_reached"),
    ("V14_STATUS_FAULT_MASK", "vendor fault"),
)


_QUEUE_PROGRAMMING_ROLES = ("QSIZE", "QBASE")


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


# A guard body may publish the frozen result tuple and its first-observation
# timestamp. Anything else it carries -- a call above all -- is an effect the
# guard cannot own, whatever its condition turns out to be.
_CANONICAL_GUARD_EFFECTS = frozenset(("store", "timestamp"))
_CARRIED_EFFECT_PREFIXES = ("store", "timestamp", "call:")
_TERMINATOR_RE = re.compile(r"^(?:break|return)(?![A-Za-z0-9_])")
_BACK_EDGE_RE = re.compile(r"(?<![A-Za-z0-9_])(continue|goto)(?![A-Za-z0-9_])")


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


# A depth-0 guard that publishes decides *when* the frame is written, so its
# condition is part of the contract exactly as the completion predicate is. Each
# recognised kind therefore carries the connective and the bound tuple its
# condition has to be, and a publishing guard of no recognised kind is refused:
# an exit on ``i > 5U`` fabricates an observation the source never made.
_RESET_PREDICATE = (("reset", "!=", 0),)
_FAULT_PREDICATE = (("fault", "!=", 0),)


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


_TEST_CPM_IF_RE = re.compile(r"#[ \t]*if[ \t]*\(?[ \t]*TEST_CPM[ \t]*==[ \t]*1[ \t]*\)?")
_TEST_CPM_ENDIF_RE = re.compile(r"(?m)^[ \t]*#[ \t]*endif")


# ---------------------------------------------------------------------------
# Runner wire contract
# ---------------------------------------------------------------------------

_RECORD_FIELD_RE = re.compile(r"uint32_t\s+([A-Za-z_]\w*)\s*;")
_SERIALIZE_RE = re.compile(r"put32\s*\(\s*&c\s*,\s*d\s*->\s*([A-Za-z_]\w*)\s*\)")
RECORD_SYMBOL = "d"


MEASURED_CALL = "run_fixed_inference()"


# The claims this contract is qualified on. Anything here needs a positive
# fixture, a negative that fails at its own rule, and application to the real
# linked image; anything not here is a check, not a claim.
RULE_PRE_PROGRAM_DOMINANCE = "RULE_PRE_PROGRAM_DOMINANCE"
RULE_NO_TRANSITION_BEFORE_PROGRAMMING = "RULE_NO_TRANSITION_BEFORE_PROGRAMMING"
RULE_PRE_PROGRAM_GATE_SHAPE = "RULE_PRE_PROGRAM_GATE_SHAPE"
RULE_PRIMARY_READ_ORDER = "RULE_PRIMARY_READ_ORDER"
RULE_PRIMARY_NO_PER_ITERATION_EFFECT = "RULE_PRIMARY_NO_PER_ITERATION_EFFECT"
RULE_PRIMARY_FAULT_PRIORITY = "RULE_PRIMARY_FAULT_PRIORITY"
RULE_PRIMARY_IRQ_NOT_AN_EXIT = "RULE_PRIMARY_IRQ_NOT_AN_EXIT"
RULE_PRIMARY_NO_QSIZE = "RULE_PRIMARY_NO_QSIZE"
RULE_TAIL_SHARED = "RULE_TAIL_SHARED"
RULE_TAIL_READ_ORDER = "RULE_TAIL_READ_ORDER"
RULE_TAIL_FOUR_CONDITIONS = "RULE_TAIL_FOUR_CONDITIONS"
RULE_TAIL_BOUND = "RULE_TAIL_BOUND"
RULE_TAIL_NO_PER_ITERATION_EFFECT = "RULE_TAIL_NO_PER_ITERATION_EFFECT"
RULE_READ_ORDER_EQUIVALENCE = "RULE_READ_ORDER_EQUIVALENCE"
RULE_MAILBOX_PUBLISHED_ONCE = "RULE_MAILBOX_PUBLISHED_ONCE"
RULE_MAILBOX_PUBLISHER_IDENTITY = "RULE_MAILBOX_PUBLISHER_IDENTITY"
RULE_MAILBOX_PUBLISH_ADDRESS = "RULE_MAILBOX_PUBLISH_ADDRESS"
RULE_MAILBOX_PUBLISH_FENCED = "RULE_MAILBOX_PUBLISH_FENCED"
RULE_RUNNER_MAILBOX_GATED = "RULE_RUNNER_MAILBOX_GATED"
RULE_RUNNER_MAILBOX_READONLY = "RULE_RUNNER_MAILBOX_READONLY"
RULE_RUNNER_MAILBOX_ONE_CHECK = "RULE_RUNNER_MAILBOX_ONE_CHECK"
RULE_RUNNER_TUPLE_COMPLETE = "RULE_RUNNER_TUPLE_COMPLETE"
RULE_SERIALIZATION_LENGTH = "RULE_SERIALIZATION_LENGTH"
RULE_SERIALIZATION_COUNTABLE = "RULE_SERIALIZATION_COUNTABLE"
RULE_SERIALIZATION_NAMED_CALLEES = "RULE_SERIALIZATION_NAMED_CALLEES"
RULE_RECORD_SIZE = "RULE_RECORD_SIZE"
RULE_RECORD_APPENDIX_ORDER = "RULE_RECORD_APPENDIX_ORDER"
RULE_RECORD_APPENDIX_CONTIGUOUS = "RULE_RECORD_APPENDIX_CONTIGUOUS"
RULE_RECORD_APPENDIX_ENDS_RECORD = "RULE_RECORD_APPENDIX_ENDS_RECORD"
RULE_DWARF_RECORD_PRESENT = "RULE_DWARF_RECORD_PRESENT"
RULE_DWARF_MEMBER_READABLE = "RULE_DWARF_MEMBER_READABLE"
RULE_DWARF_SIZE_PRESENT = "RULE_DWARF_SIZE_PRESENT"
RULE_DWARF_NM_AGREE = "RULE_DWARF_NM_AGREE"
RULE_NPU_IRQ_NEVER_ENABLED = "RULE_NPU_IRQ_NEVER_ENABLED"
RULE_NPU_IRQ_UNRESOLVED_WRITE = "RULE_NPU_IRQ_UNRESOLVED_WRITE"
RULE_STORE_FORM_UNREADABLE = "RULE_STORE_FORM_UNREADABLE"


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
# AAPCS-defined call clobber. A value this gate is tracking in one of these does
# not survive a call, and reading it afterwards as if it did is how a register
# that names an MMIO address can appear to hold something it no longer holds.
_ELF_CALL_CLOBBERED = ("r0", "r1", "r2", "r3", "r12", "ip", "lr")
# The multi-register loads. Their destinations come from the stack, which this
# gate does not model, so every register in the list stops being known -- which
# is what a push/pop pair around a call would otherwise be able to hide.
_ELF_MULTI_LOAD = re.compile(
    r"^(pop|ldm(?:ia|db|ea|fd)?)(?:\.[nw])?\s+(?:(\w+)(!?),\s*)?\{([^}]*)\}"
)
_ELF_PUSH = re.compile(r"^(push|stm(?:ia|db|ea|fd)?)(?:\.[nw])?\s")
_ELF_DESTINATION = re.compile(r"^(\w+?)(?:\.[nw])?\s+(\w+)\s*,")
_ELF_TEST_MASK = re.compile(r"^tst(?:\.[nw])?\s+(\w+),\s*#(\d+)")
# Any store, whatever its addressing form. _ELF_MEMORY reads only the
# ``[rB, #imm]`` shape, and a rule built on it does not *refuse* the others --
# it does not see them. The real image stores through ``[rB, rI, lsl #2]`` in
# three places, so this is a form the gate has to account for rather than one it
# can pretend does not occur.
_ELF_STORE_STEMS = ("str", "strb", "strh", "strd", "stm", "stmia", "stmdb", "stmea", "push")
# The mnemonic carries its condition: ``it ne`` + ``strne.w`` disassembles with
# mnemonic ``strne``, which a membership test against the bare stems misses
# entirely -- so a predicated store was invisible to a rule that thought it was
# looking at every store.
_ELF_CONDITION_SUFFIX = re.compile(r"^(%s)(?:%s)?$" % ("|".join(_ELF_STORE_STEMS), "|".join(_CONDITIONS)))
_ELF_REGISTER_LIST = re.compile(r"\{([^}]*)\}")
_ELF_STORE_BASE = re.compile(r"\[\s*(\w+)")
_ELF_STORE_OPERANDS = re.compile(r"^\w+(?:\.[nw])?\s+(.*)$")
# ``tst`` is not the only way to test a mask: at -O1 GCC also writes
# ``ands rX, rS, #mask``, which sets the flags the branch reads and happens to
# park the result in a register nobody uses. A rule that knew only ``tst`` would
# have read the reset and cmd_end checks as absent.
_ELF_MASK_TEST = re.compile(r"^(?:tst|ands)(?:\.[nw])?\s+(?:(\w+),\s*)?(\w+),\s*#(\d+)")
# Instructions whose first operand is read, not written. Reading them as writes
# is what made a ``tst`` look like it clobbered the register it tests.
_ELF_NON_WRITING = frozenset(
    ("cmp", "cmn", "tst", "teq", "str", "strb", "strh", "strd", "push", "stm", "stmia", "stmdb")
)



# ---------------------------------------------------------------------------
# Load-bearing claim matrix
#
# Six columns per claim, and a claim is QUALIFIED only when all of them hold:
#
#   CLAIM             what is being asserted
#   DETECTOR          which function looks
#   REJECTION POINT   the rule identifier it refuses with
#   POSITIVE          the real image passes it
#   TARGETED NEGATIVE a mutation of the real image fails *at that rule*
#   REAL ELF          the claim is applied to Q, QS and SQ
#
# The fifth column is the one this project had to learn. A negative fixture
# that makes the suite red proves nothing on its own: two fixtures written
# here tripped a different rule than the one they were named for and were
# green for it. So the expectation is the rule identifier, not the exit code.
# ---------------------------------------------------------------------------

CLAIM_MATRIX = (
    ("the stopped-state gate runs before the queue is programmed, on every path",
     "verify_pre_run_dominance", RULE_PRE_PROGRAM_DOMINANCE),
    ("nothing starts the NPU between that gate and the programming",
     "verify_pre_run_dominance", RULE_NO_TRANSITION_BEFORE_PROGRAMMING),
    # Source-side: the shape of the gate is decided on the generated text, and
    # the matrix said "verify_pre_run_dominance" until a negative aimed at this
    # rule kept landing somewhere else and the harness said so.
    ("the gate reads STATUS exactly once, in one function",
     "verify_pre_run_contract", RULE_PRE_PROGRAM_GATE_SHAPE),
    ("the measured loop reads what the variant is named for, in that order",
     "verify_primary_loop_image", RULE_PRIMARY_READ_ORDER),
    ("the measured loop has no per-iteration effect",
     "verify_primary_loop_image", RULE_PRIMARY_NO_PER_ITERATION_EFFECT),
    ("the measured loop never reaches QSIZE",
     "verify_primary_loop_image", RULE_PRIMARY_NO_QSIZE),
    ("reset and fault are decided before completion is",
     "verify_primary_loop_image", RULE_PRIMARY_FAULT_PRIORITY),
    ("irq_raised is observed, never an exit",
     "verify_primary_loop_image", RULE_PRIMARY_IRQ_NOT_AN_EXIT),
    ("every variant joins one convergence tail",
     "verify_common_tail_is_shared", RULE_TAIL_SHARED),
    ("the tail reads QREAD then STATUS per iteration",
     "verify_convergence_tail_image", RULE_TAIL_READ_ORDER),
    ("the tail decides all four conditions in one tuple",
     "verify_convergence_tail_image", RULE_TAIL_FOUR_CONDITIONS),
    ("the tail carries the contract's iteration bound",
     "verify_convergence_tail_image", RULE_TAIL_BOUND),
    ("the tail has no per-iteration effect",
     "verify_convergence_tail_image", RULE_TAIL_NO_PER_ITERATION_EFFECT),
    ("QS and SQ differ in read order and nothing else",
     "verify_read_order_equivalence", RULE_READ_ORDER_EQUIVALENCE),
    ("the mailbox validity word is written once",
     "verify_mailbox_publication_image", RULE_MAILBOX_PUBLISHED_ONCE),
    ("it is written by the publisher",
     "verify_mailbox_publication_image", RULE_MAILBOX_PUBLISHER_IDENTITY),
    ("it is written to the validity word and nowhere else",
     "verify_mailbox_publication_image", RULE_MAILBOX_PUBLISH_ADDRESS),
    ("it is fenced on both sides",
     "verify_mailbox_publication_image", RULE_MAILBOX_PUBLISH_FENCED),
    ("the runner reads the tuple only where the magic check dominates",
     "verify_runner_mailbox_gate_image", RULE_RUNNER_MAILBOX_GATED),
    ("the runner writes no mailbox word",
     "verify_runner_mailbox_gate_image", RULE_RUNNER_MAILBOX_READONLY),
    ("the runner checks the magic once",
     "verify_runner_mailbox_gate_image", RULE_RUNNER_MAILBOX_ONE_CHECK),
    ("the runner reads the whole tuple",
     "verify_runner_mailbox_gate_image", RULE_RUNNER_TUPLE_COMPLETE),
    ("the serializer writes the contract's frame length",
     "verify_serialization_image", RULE_SERIALIZATION_LENGTH),
    ("the word count is countable: no loop, no recursion on the path",
     "verify_serialization_image", RULE_SERIALIZATION_COUNTABLE),
    ("every callee on the counting path can be named",
     "verify_serialization_image", RULE_SERIALIZATION_NAMED_CALLEES),
    ("the laid-out record is the contract's body",
     "verify_record_layout_image", RULE_RECORD_SIZE),
    ("the laid-out appendix is the contract's table in wire order",
     "verify_record_layout_image", RULE_RECORD_APPENDIX_ORDER),
    ("the appendix is contiguous",
     "verify_record_layout_image", RULE_RECORD_APPENDIX_CONTIGUOUS),
    ("the appendix ends the record",
     "verify_record_layout_image", RULE_RECORD_APPENDIX_ENDS_RECORD),
    ("DWARF describes the record this contract names",
     "dwarf_record_layout", RULE_DWARF_RECORD_PRESENT),
    ("every member DWARF describes is readable",
     "dwarf_record_layout", RULE_DWARF_MEMBER_READABLE),
    ("DWARF gives the record a size",
     "dwarf_record_layout", RULE_DWARF_SIZE_PRESENT),
    ("DWARF and nm describe the same build",
     "verify_record_layout_image", RULE_DWARF_NM_AGREE),
    ("the NPU interrupt is never enabled",
     "verify_npu_irq_never_enabled_image", RULE_NPU_IRQ_NEVER_ENABLED),
    ("a write into its enable word that cannot be read is refused",
     "verify_npu_irq_never_enabled_image", RULE_NPU_IRQ_UNRESOLVED_WRITE),
    ("a store whose form this gate cannot read is refused where it matters",
     "several", RULE_STORE_FORM_UNREADABLE),
)


# Loops inside this gate whose body runs zero times while the real artifacts are
# verified. The list exists because the worst defect this contract has produced
# twice is a rule that examines nothing and reports success: a rotated loop whose
# body set came out empty made every per-iteration rule vacuously true, and it
# looked exactly like a pass.
#
# So the condition is measured rather than trusted. The suite traces the real
# verification, collects every loop that never entered its body, and refuses any
# entry not named here -- and any entry named here that starts running, and any
# change in the count. An allowlist that only grew would be a way to legalise the
# next silent gate; this one fails in both directions.
#
# Each entry says what its owner is proving, why the loop is idle on these
# artifacts, and -- the part that matters -- what evidence proves that claim
# instead. Every one of these is a source-side helper, and none of them is the
# detector of a load-bearing claim: no claim in CLAIM_MATRIX rests on a path
# that examined nothing. The suite checks that too.
#
# Keyed by (function, header source, occurrences) so it survives line movement.
VACUOUS_ON_REAL_ARTIFACTS = {
    ("_is_whole_rvalue",
     "while cursor < len(text) and text[cursor] in _INLINE_SPACE:", 1): {
        "proves": "an assignment's right-hand side is the whole expression and not a fragment of one",
        "scope": "the three generated source pairs",
        "why_vacuous": "the rvalue is written with no inline space before its terminator",
        "evidence_instead": "the sites this decides are read by their own rules, which do run",
    },
    ("_member_base_follows",
     "while cursor < len(text) and text[cursor] in _INLINE_SPACE:", 1): {
        "proves": "a member access names the object this rule is about",
        "scope": "the three generated source pairs",
        "why_vacuous": "the member base is written without inline space",
        "evidence_instead": "the record and appendix rules resolve every member they need",
    },
    ("_publication_symbol_sites",
     "while cursor < len(vendor_masked) and vendor_masked[cursor] in _INLINE_SPACE:", 2): {
        "proves": "the publication helpers are called where the design says and nowhere else",
        "scope": "the three generated source pairs",
        "why_vacuous": "the call sites are written without inline space around the parenthesis",
        "evidence_instead": "the sites are found and counted; only the space-skipping arm is idle",
    },
    ("_reaches_without_transfer",
     "for match in _CONTROL_TRANSFER_RE.finditer(prefix):", 1): {
        "proves": "one statement reaches another with nothing in between that could divert",
        "scope": "the three generated source pairs",
        "why_vacuous": "no control transfer stands between the two sites the real sources present",
        "evidence_instead": "the reachability answer is still computed and used",
    },
    ("_subscript_expression",
     "while cursor >= 0 and text[cursor] in _INLINE_SPACE:", 1): {
        "proves": "a subscripted access names the array this rule is about",
        "scope": "the three generated source pairs",
        "why_vacuous": "the subscripts are written without inline space before the bracket",
        "evidence_instead": "the appendix producer rules resolve every subscript they need",
    },
    ("_token_after",
     "while cursor < len(text) and text[cursor] in _INLINE_SPACE:", 1): {
        "proves": "the token following a construct is the one the rule expects",
        "scope": "the three generated source pairs",
        "why_vacuous": "the tokens this looks past are written without inline space",
        "evidence_instead": "every caller gets its token and decides on it",
    },
    ("cmd_write_values",
     "for site, role, is_write in dereference_sites(text, defines, roles):", 1): {
        "proves": "no CMD write starts the NPU where the contract forbids it",
        "scope": "the three generated source pairs",
        "why_vacuous": "CMD is written through write_reg in the real sources, never through a pointer dereference",
        "evidence_instead": "the write_reg scan above it finds every CMD write there is",
    },
    ("obs_aliases",
     "while pending:", 1): {
        "proves": "every alias of the observation record is known to the storage rules",
        "scope": "the three generated source pairs",
        "why_vacuous": "the record is aliased directly, so the transitive closure has nothing to add",
        "evidence_instead": "the direct aliases are collected and used",
    },
    ("pointer_roles",
     "for name in compound_assignment_targets(scope + body, tuple(sorted(resolved))):", 1): {
        "proves": "every register pointer's role is known wherever it is used",
        "scope": "the three generated source pairs",
        "why_vacuous": "no register pointer is reassigned through a compound assignment",
        "evidence_instead": "the direct assignments resolve every pointer the rules ask about",
    },
    ("register_access_sites",
     "for site, role, is_write in dereference_sites(text, defines, roles):", 1): {
        "proves": "every read or write of a register is seen, whatever spelling it uses",
        "scope": "the three generated source pairs",
        "why_vacuous": "the same dereference spelling the real sources do not use",
        "evidence_instead": "the read_reg/write_reg scan finds every access there is",
    },
    ("require_mailbox_storage_closed",
     "while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:", 1): {
        "proves": "nothing writes the mailbox except the publishers the design names",
        "scope": "the three generated source pairs",
        "why_vacuous": "the mailbox stores are written without inline space before the assignment",
        "evidence_instead": "every store is found and attributed",
    },
    ("require_no_macro_mmio",
     "for name in macros:", 1): {
        "proves": "no MMIO reaches the registers through a macro this gate cannot expand",
        "scope": "the three generated source pairs",
        "why_vacuous": "the real translation units define no MMIO macro at all, which is the condition",
        "evidence_instead": "the emptiness is the evidence: there is nothing to check because nothing exists",
    },
    ("require_stable_contract_defines",
     "for match in _UNDEF_RE.finditer(directive_view(masked)):", 1): {
        "proves": "a contract constant means the same thing everywhere in the file",
        "scope": "the three generated source pairs",
        "why_vacuous": "the real sources carry no #undef",
        "evidence_instead": "the emptiness is the evidence: no constant is ever undefined",
    },
    ("require_wait_for_irq_unreachable",
     "while cursor < len(scan) and scan[cursor] in _INLINE_SPACE:", 1): {
        "proves": "no path waits for an interrupt the contract says never arrives",
        "scope": "the three generated source pairs",
        "why_vacuous": "the scanned sites are written without inline space",
        "evidence_instead": "the sites are found and their reachability decided",
    },
    ("statement_effects",
     "for register in _RAW_REGISTER_RE.findall(statement):", 1): {
        "proves": "what each statement in a measured loop does to the registers",
        "scope": "the three generated source pairs",
        "why_vacuous": "the loop bodies reach the registers through pointers loaded before them, so the bare NPU_REG_ spelling appears in no statement this is given",
        "evidence_instead": "the dereference arm above it does produce load:QREAD and load:STATUS on the real sources",
    },
    ("verify_convergence_contract",
     "for effect in effects:", 1): {
        "proves": "no convergence predicate is satisfied by a reread rather than by the loop's tuple",
        "scope": "the three generated source pairs",
        "why_vacuous": "no statement inside a guard body carries a load, which is the condition it exists to refuse",
        "evidence_instead": "the depth-zero arm reads every statement and orders the loads",
    },
    ("verify_hard_bypass_contract",
     "for match in re.finditer(r\"&\\s*(?:\\(\\s*)*irq_triggered(?![A-Za-z0-9_])\", vendor_masked):", 1): {
        "proves": "the interrupt flag is never taken by address and written from somewhere unseen",
        "scope": "the three generated source pairs",
        "why_vacuous": "irq_triggered is never address-taken in the real sources",
        "evidence_instead": "the emptiness is the evidence: there is no address-taken use to follow",
    },
}


_ELF_DATA_ROW = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F ]+\t\.(word|short|byte)\s+0x([0-9a-fA-F]+)"
)
_ELF_DATA_WIDTH = {"word": 4, "short": 2, "byte": 1}


_ELF_TABLE_BRANCH = re.compile(r"^(tbb|tbh)\s+\[pc,\s*(\w+)(?:,\s*lsl\s*#1)?\]")
_ELF_TABLE_GUARD = re.compile(r"^cmp(?:\.[nw])?\s+(\w+),\s*#(\d+)")
_ELF_TABLE_DEFAULT = re.compile(r"^bhi(?:\.[nw])?\s")


PRE_PROGRAM_MAILBOX_WORD = 2
_GATE_MASKS = (STATUS_STATE, STATUS_RESET, STATUS_FAULT_MASK)


MAILBOX_SYMBOL = "pmu_completion_visibility_v14_mailbox"


_ELF_ANNOTATION = re.compile(r"\s*(?:@.*|<[^>]*>.*)$")


# ---------------------------------------------------------------------------
# The record the compiler actually laid out
#
# Every rule about the appendix above reads the *source* -- field order in the
# struct, call order in the serializer -- and infers the wire from them. What
# the host parses is neither: it is the bytes the compiler laid out. Padding, a
# reordered member, a type that is not four bytes wide, and the source still
# reads exactly as the contract requires while the record on the wire does not
# match the table the host indexes with.
#
# DWARF is where that stops being an inference. -g3 is in CFLAGS, so the build
# already emits it; this reads the member offsets the compiler recorded.
# ---------------------------------------------------------------------------

_DWARF_DIE = re.compile(
    r"^\s*<(\d+)><([0-9a-f]+)>:\s+Abbrev Number:\s+\d+\s+\((DW_TAG_\w+)\)"
)
# Two spellings: ``DW_AT_name : (indirect string, offset: 0x...): field`` and the
# direct ``DW_AT_name : field``. A pattern that required the second colon read
# the directly-spelled members as nameless.
_DWARF_NAME = re.compile(r"DW_AT_name\s*:\s*(?:.*:\s*)?(\S+)\s*$")
_DWARF_MEMBER_OFFSET = re.compile(r"DW_AT_data_member_location:\s*(\d+)")
_DWARF_TYPE_REF = re.compile(r"DW_AT_type\s*:\s*<0x([0-9a-f]+)>")
_DWARF_BYTE_SIZE = re.compile(r"DW_AT_byte_size\s*:\s*(\d+)")
_DWARF_ADDR = re.compile(r"DW_AT_location\s*:.*\(DW_OP_addr:\s*([0-9a-f]+)\)")

RECORD_TYPEDEF = "pmu_diag_record_t"


RUNNER_DISPATCH_SYMBOL = "dispatch"
_ELF_COMPARE_REGISTERS = re.compile(r"^cmp(?:\.[nw])?\s+(\w+),\s*(\w+)\s*$")


SERIALIZER_SYMBOL = "build_pmu_diag_payload"
WORD_WRITER_SYMBOL = "put32"
_ELF_CALLEE = re.compile(r"^bl(?:\.[nw])?\s+[0-9a-f]+\s*<([^>+]+)")


NVIC_ISER_BASE = 0xE000E100
NVIC_ISER_WORDS = 16
NPU_IRQ_NUMBER = 16


MAILBOX_PUBLISH_SYMBOL = "v14_mailbox_publish"
MAILBOX_VALID_WORD = APPENDIX_WORDS - 1


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


# The confinement table authorises ``u85_irq_handler`` to write CMD, because the
# stock ISR clears completion there. It authorised the *owner* and never the
# *value*, so a second submit issued from interrupt context satisfied it -- and
# a terminal CMD=0 written there stops the NPU before the convergence tail
# measures it. The ISR's STATUS load is bounded for the same reason: one load is
# the design's, and a second is one no ordering rule in this file judged.
ISR_CMD_CLEAR_VALUE = 2
ISR_STATUS_LOADS = 1


# ``_register_authorized_owners`` lets ``wait_for_irq`` name STATUS on the
# stated ground that the V14 command path never calls it. That was a comment,
# not a rule, so a ``wait_for_irq`` that spins on STATUS until CMD_END and is
# actually called consumes completion before the measured loop starts -- and
# every ``first_*`` word then describes an already-complete device while the
# gate reports the exemption intact. The ground is checked here.
WAIT_FOR_IRQ_SYMBOL = "wait_for_irq"


_WAIT_FOR_IRQ_REFUSAL = (
    "wait_for_irq is named outside its own definition, %s: the STATUS designation this gate "
    "authorises inside it is authorised on the ground that the command path never reaches it, "
    "and a name that is not the declarator is a reachability this gate cannot bound -- a "
    "running-path STATUS load no dominance or read-order rule judged"
)


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


_TYPEDEF_RE = re.compile(r"(?<![A-Za-z0-9_])typedef(?![A-Za-z0-9_])")


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


# The keywords that can stand directly in front of a parenthesised expression
# without being a value themselves. Everything else spelled as an identifier
# there is an operand, and a ``(`` after an operand is a call.
_EXPRESSION_KEYWORDS = frozenset(("return", "case", "else", "do", "sizeof"))


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


# Every way of reaching ret_code that is not a plain assignment.
_RET_CODE_STEP_RE = re.compile(
    r"(?:\+\+|--)\s*ret_code|ret_code\s*(?:\+\+|--|<<=|>>=|[-+*/%&|^]=)"
)
# The only one the frozen vendor uses. It is not counted: an increment cannot
# produce V14_RET_SUCCESS from any verdict -- the codes are 0..7 and stepping
# moves away from zero -- so a second one forges nothing. The operators that can
# forge a verdict are the ones that clear or overwrite, and those are refused.
_FROZEN_ENTRY_STEP = "ret_code++"


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
