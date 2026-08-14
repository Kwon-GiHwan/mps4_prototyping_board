"""Static source and cross-ELF gate for PMU_COMPLETION_POLL_COUNT_DIAG_V13.

The gate proves two independent properties:

1. the generated V13 sources publish ``poll_remaining_at_success`` exactly once
   across the whole vendor translation unit -- on the helper success path only,
   immediately after P2, from the loop induction variable -- and the generated
   runner can only forward that value on the success path, because its single
   other write to the record field is the ``0U`` invalidation inside the
   ``poll_result != V13_POLL_SUCCESS`` gate that follows the copy. Both halves
   are held to *every mention* of the name rather than to a write count: a
   write is classified by the operator next to the symbol, and taking the
   symbol's address never puts one there, so ``&SYM`` handed to a helper, to
   ``memcpy`` or to a second record pointer would publish through an alias
   while the count stayed at one. Each translation unit may therefore mention
   the global and the record field only in the uses this gate models, which is
   what stops an alias from being *named*. Two things sit outside a rule about
   mentions and are handled separately. Token pasting forms the symbol out of
   fragments that are not mentions of it, and is refused in the vendor TU by
   rejecting ``##`` anywhere on a ``#define``'s *logical* line -- across the
   backslash continuation any wrapped macro is written over, because a rule
   that stopped at the first newline would refuse the paste only in the
   formatting nobody writes. A mutation of the record that encloses the field
   -- ``memset(&d, ...)``, a whole-record assignment, the record's address
   handed out -- is refused over the record's scope rather than downstream of
   the success copy: a scan bounded at the copy sees mutations but not the
   capability behind them, and an alias captured above the copy survives it.
   So the innermost block the ``pmu_diag_record_t d`` declaration lives in may
   name the record as a whole exactly twice -- the canonical pre-run
   ``memset(&d, 0, sizeof(d));`` reset, which must precede the copy, and the
   declaration's own initializer -- while member addresses stay untouched and a
   ``&d`` outside that scope is a different object the rule does not examine.
   Both scans read comment- and literal-masked text, so ``&d`` or ``##``
   written inside a comment or a string is text rather than a use.

   What no scan over source text can reach is a publication that never names
   the slot at all: an absolute-address store, a cast of the record pointer,
   inline assembly, or a store to the wire word by index. Nothing in this
   module covers those. The three-slot store lock is helper-scoped -- its
   domain is the code reachable from the V13 poll helper's own entry, the one
   function ``_analyze_helper`` resolves -- so it cannot see the runner's
   record or the wire buffer at all, and naming it as their authority would
   report an uncovered class as covered. Those forms are therefore
   **unqualified**. Closing them needs a distinct runner-record and wire
   dataflow gate over the linked image. This module now carries that linked image
   gate, but only in an exact fixed-build, DWARF-dependent, fail-closed form:
   it accepts the concrete singleton locations and writer paths the linked image
   proves, and refuses anything broader rather than claiming a general helper
   proof; and
2. the V13 *per-iteration loop region* -- STATUS load, completion test, success
   branch, failed-path decrements and back edge -- signs exactly as the V12 one
   does, and the value the V13 helper publishes after P2 flows out of the
   register that the failed-poll conditional back edge decrements.

The two halves of property 2 are scoped differently, and the manifest says so:
``v12_v13_poll_loop_semantically_equivalent`` is the cross-image half and covers
that per-iteration loop region and nothing else, which is what the manifest's
``v12_v13_poll_loop_equivalence_scope`` names. The post-P2 publication is the
V13-only half -- V12 has no such store, so it is not a cross-image comparison
at all but a CFG and dataflow proof over the V13 image alone. Cross-image
equivalence of the helper prologue, of the success tail past the completion
branch and of the epilogue is not claimed here: a V13 build whose prologue or
success tail differs from V12's signs the same region and is accepted.

Property 2 is derived from the instruction stream itself (basic-block edges,
register definitions and uses), not from disassembly comments or fixed
addresses, so a relabelled or relocated build is accepted while an extra
per-iteration effect is not. That per-iteration region is closed:
it may contain those six instructions and nothing else, on either side of the
completion test. Every pointer the helper uses is resolved through the Thumb
literal-pool rule ``((addr + 4) & ~3) + imm`` and bound to the exact address
its role requires, so a build that polls a RAM shadow, reads a fake cycle
counter or publishes the countdown over the P2 slot is refused even though its
instruction shape is unchanged. Because that resolution stands on a register
still holding the literal it was loaded with, writeback addressing --
``[rN, #imm]!`` and ``[rN], #imm``, which advance the base without ever naming
it as a destination -- is refused anywhere in the helper rather than modelled:
it is one of the two forms under which a certified address and a touched
address can drift apart. The other is the walk itself: those bindings are
computed in layout order, so a control-flow edge that reaches an access without
executing the literal load feeding its base would leave the access certified
against a word the register never held on that edge. Every effective address
the gate certifies is therefore re-derived over the helper's own branch edges,
meeting predecessors by agreement, and an access the two walks disagree about
is refused. The three published slots are also the
only stores the helper may execute at all, so a fourth referenced SRAM literal
cannot be written from the prologue, where it would run ahead of both the
success and the timeout entry. Where the publication actually *runs* is proven
over an explicit control-flow graph of the helper rather than over layout order:
the remaining store must be unreachable from the timeout exit, and every path
from the completion branch to a return must execute it exactly once, so a build
that jumps over it, jumps back to it, publishes from a second site or falls into
it from the timeout tail is refused even though its store shape is unchanged.
Which register carries the countdown is read off the loop's own control
dependency -- the decrement whose flags the back edge branches on -- rather than
off the position of a decrement in the loop body, and that register is proven
undisturbed on every path from the success entry to the store, not merely in
layout order. Because that proof can only see the register effects it models,
the modelled instruction vocabulary is enforced over every instruction the
helper can *execute* -- the set reachable from its entry, not a slice between
two indices -- so a multi-register ``ldrd`` reload, a predicated ``moveq`` or an
``rrx`` recomputation is refused outright instead of being read as writing
nothing, and so is a ``cpsid``, ``wfi`` or coprocessor effect anywhere on that
set, including the pre-loop prologue and the tail past the publication. A long
multiply belongs to the same family for the same reason: ``umull``/``smull``
write RdLo *and* RdHi, and only the first destination operand is readable, so
the pair is refused rather than read as writing the register it names first. On the
same footing, each of the three published slots must be written by its canonical
site and by nothing else the helper can reach, which is what refuses a pre-loop
store that pre-seeds the record ahead of both the success and timeout entries.
The runner half of property 1 is likewise derived
from brace nesting and assignment right-hand sides, never from column alignment,
so reformatting the generated runner cannot change the verdict.

Scope: this module gates generated sources and the helper poll loop of the two
final ELFs. It also re-runs an exact retained-V12 executable subset against the
V13 linked image through ``check_pmu_completion_poll_v12``'s parameterized
real-trace verifier. A distinct, hash-bound evidence artifact proves the stock
vector target, NVIC hard-bypass, STATUS/history provenance, path-sensitive
CMD/QREAD ordering, P0/P1/P2 publication, the H-PRINTF seam and terminal
release at the frozen V13 addresses. That subset does not qualify runtime
golden output or the full base-PMU contract, and its evidence states both
limitations explicitly. Separately, the generated-source screen enforces a
bounded refusal of the NVIC *enable* forms it enumerates -- an
``NVIC_EnableIRQ`` call site and a direct NVIC->ISER write -- not a complete
proof that no enable exists. The stock
``NVIC_SetVector`` and ``NVIC_ClearPendingIRQ`` call sites are required by that
retained contract, so their presence is not drift here; their operands and
ordering are proven by the whole-image gate. That ISER half examines the store
mnemonics it names -- ``str*``, ``stm*``, ``stl*``, ``stc*``, ``vst*``,
``push``/``pop`` and ``vpush``/``vpop`` -- resolving a base materialised by
``movw``/``movt`` as well as by a literal pool, keeping a pointer's taint
across the two-operand ``adds Rd, #imm`` that a ``NVIC->ISER[i]`` walk lowers
to, refusing a register-list store whose proven base lies within the list's own
span of the ISER bank, and tainting a base a writeback form can advance into
``NVIC_Type``.

What it still cannot see, stated so no reader takes the gate for more than it
is: a store mnemonic outside that list is not examined at all, so the list is an
allow-list of names rather than a statement about every instruction that can
write memory; a base whose value arrives from memory, from a function argument
or from a transfer list is unproven *and* untainted, so a store through it is
accepted; a writeback advance whose amount is unreadable taints only a base
proven within one register-file span of the block; taint does not flow through
memory; and every one of these judgements is made in layout order over each
function, not over its control-flow graph. The CFG-derived binding rule above
covers the V13 poll helper alone, not the whole image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

import check_pmu_qual as qual_elf
from check_pmu_completion_poll_v12 import (
    RealTraceCallerAddresses,
    RealTraceCompletionTestLowering,
    RealTraceContract,
    _function_section,
    fail,
    parse_functions,
    verify_callsite_trace_real,
)

SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
VARIANT = "PMU_COMPLETION_POLL_COUNT_DIAG_V13"
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
RUNNER_GENERATED_SHA256 = "b66f49eee75f7bfbe6a8cd972f86449751cff25eb5ac98be392a46cbbfc50b8f"
VENDOR_GENERATED_SHA256 = "2d86f78f3e8b0ee1f52bf1a74bbf07a4a8c2e43d2e262a50a36a9f8a5a02b4c9"
AUTHORITATIVE_V12_SHA256 = "cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401"
RETAINED_V12_EXECUTABLE_PROOF_SCOPE = "v12_real_trace_subset_replayed_on_v13"
RETAINED_V12_EXECUTABLE_LIMITATIONS = (
    "Proves the retained V12 real-trace subset over the fixed V13 linked image: "
    "stock vector target, NVIC hard bypass, STATUS/history provenance, path-sensitive "
    "CMD/QREAD ordering, P0/P1/P2, H-PRINTF seam, and terminal CMD=0xC. It does not "
    "qualify runtime golden output or the full base PMU contract."
)
RETAINED_V12_EXECUTABLE_BOOLEAN_KEYS = (
    "retained_v12_stock_vector_exact",
    "retained_v12_nvic_hard_bypass_exact",
    "retained_v12_status_history_provenance_exact",
    "retained_v12_cmd_qread_ordering_exact",
    "retained_v12_p0_p1_p2_exact",
    "retained_v12_hprintf_seam_exact",
    "retained_v12_terminal_release_exact",
)
V13_REAL_TRACE_CONTRACT = RealTraceContract(
    schema_version=SCHEMA_VERSION,
    build_id=BUILD_ID,
    runner_source_sha256=RUNNER_GENERATED_SHA256,
    vendor_source_sha256=VENDOR_GENERATED_SHA256,
    helper_symbol="v13_poll_completion",
    trace_prefix="pmu_completion_poll_v13_t_",
    completion_test_lowering=RealTraceCompletionTestLowering(
        helper_mnemonic="tst",
        helper_status_register="r0",
        helper_dest_register=None,
        irq_mnemonic="tst",
        irq_status_register="r2",
        irq_dest_register=None,
        mask=2,
    ),
    caller_addresses=RealTraceCallerAddresses(
        success_cmd2=(0x31002560, 0x31002564),
        other_cmd_stores=(0x31002416, 0x310024C4, 0x310024F8, 0x31002544, 0x3100254E),
        timeout_cmd2=0x310024F8,
        qread_loads=(0x310024F4, 0x31002562),
        cmd0=0x31002544,
        cmd0c=0x3100254E,
    ),
)
V13_RETAINED_V12_EXPECTED_ADDRESSES = {
    "helper_address": "0x31002368",
    "runtime_vector_target_address": "0x310023BC",
    "wait_call_target_address": "0x31002368",
    "wait_result_branch_block_address": "0x310024DC",
    "success_entry_block_address": "0x31002556",
    "timeout_entry_block_address": "0x310024F4",
    "merge_block_address": "0x31002514",
    "helper_status_register_address": "0x50004004",
    "runtime_vector_install_site_address": "0x310025FA",
    "runtime_disable_site_address": "0x31002612",
    "runtime_clear_pending_site_address": "0x3100261E",
    "runtime_enable_read_address": "0x31002636",
    "runtime_pending_read_address": "0x31002646",
    "runtime_active_read_address": "0x31002654",
    "runtime_irq_triggered_read_address": "0x3100265E",
    "helper_status_read_address": "0x31002378",
    "helper_status_test_address": "0x3100237A",
    "poll_helper_p0_address": "0x3100236E",
    "poll_helper_p1_address": "0x31002392",
    "poll_helper_p2_address": "0x3100239A",
    "submit_read_address": "0x310024BE",
    "submit_write_address": "0x310024C4",
    "submit_t2_address": "0x310024CC",
    "wait_call_address": "0x310024CE",
    "wait_result_store_address": "0x310024DC",
    "success_history_mask_store_address": "0x3100255C",
    "success_cmd2_1_store_address": "0x31002560",
    "success_qread_load_address": "0x31002562",
    "success_cmd2_2_store_address": "0x31002564",
    "timeout_report_address": "0x310024F0",
    "timeout_qread_load_address": "0x310024F4",
    "timeout_cmd2_store_address": "0x310024F8",
    "cmd0_store_address": "0x31002544",
    "hprintf_callsite_address": "0x31002548",
    "terminal_cmd0c_store_address": "0x3100254E",
    "final_pending_before_clear_address": "0x31002514",
    "final_pending_after_clear_address": "0x31002528",
    "final_active_after_cleanup_address": "0x31002534",
    "final_irq_triggered_after_cleanup_address": "0x3100253E",
    "irq_status_read_address": "0x310023C0",
    "irq_trigger_test_address": "0x310023C8",
    "irq_history_mask_store_address": "0x310023C6",
    "irq_cmd2_store_address": "0x310023EA",
}
# The MPS4 address map. Every peripheral literal a helper carries is a *base*;
# the address an instruction touches is that base plus the displacement it
# encodes, which is why the checks below resolve `literal + displacement` and
# never the literal alone.
#   * U85 base -- firmware/Selftest_pmu/runner_pmu_main.c:274
#     (`#define U85_BASE_ADDRESS 0x50004000U`, citing Drivers/u85_driver/u85.c)
#   * helper STATUS -- U85 base + 4, the `helper_status_register_address` V12's
#     own manifest emits (check_pmu_completion_poll_v12.py:104)
#   * DWT base + CYCCNT displacement -- the real MPS4 image reaches CYCCNT as
#     `.word 0xe0001000` loaded and read back through `[rN, #4]`
#   * diagnostic globals live in the 0x3100_0000 SRAM image alongside .bss
U85_BASE_ADDRESS = 0x50004000
STATUS_ADDRESS = 0x50004004
DWT_BASE_ADDRESS = 0xE0001000
DWT_CYCCNT_DISPLACEMENT = 4
DWT_CYCCNT_ADDRESS = DWT_BASE_ADDRESS + DWT_CYCCNT_DISPLACEMENT
COMPLETION_MASK = 0x02
POLL_LIMIT = 10000
NPU_MMIO_BASE = 0x50004000
NPU_MMIO_LIMIT = 0x50005000
SRAM_BASE = 0x31000000
SRAM_LIMIT = 0x32000000

_RAW_RUNNER_ANCHOR = "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;"
_RAW_VENDOR_ANCHOR = "static int test_commands( const u85_eTest eTest,"
_RAW_RUNNER_GENERATED_MARKER = "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID"
_RAW_VENDOR_GENERATED_MARKER = "v12_poll_completion(void)"

_REMAINING_SYMBOL = "pmu_completion_poll_v13_t_poll_remaining_at_success"
_REMAINING_FIELD = "poll_remaining_at_success"
_VENDOR_HELPER_DEF_MARKER = "v13_poll_completion(void)"
_P1_STATEMENT = "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;"
_P2_STATEMENT = "pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;"
_LOOP_HEADER = "for (uint32_t i = 0U; remaining != 0U; ++i, --remaining) {"
_SUCCESS_GUARD = "if ((status & 0x%02XU) != 0U) {" % COMPLETION_MASK
_STATUS_READ_STATEMENT = "status = *status_reg;"
_REMAINING_RHS = "remaining"

_RECORD_REMAINING_WRITE_RE = re.compile(
    r"\bd\s*(?:\.|->)\s*%s\s*=\s*([^;]*);" % _REMAINING_FIELD
)
_RUNNER_TIMEOUT_GATE_RE = re.compile(
    r"\bif\s*\(\s*d\s*(?:\.|->)\s*poll_result\s*!=\s*V13_POLL_SUCCESS\s*\)\s*\{"
)
_RUNNER_REMAINING_EXTERN_RE = re.compile(
    r"\bextern\s+volatile\s+uint32_t\s+%s\s*;" % re.escape(_REMAINING_SYMBOL)
)
_RUNNER_REMAINING_MEMBER_RE = re.compile(r"\buint32_t\s+%s\s*;" % _REMAINING_FIELD)
_RUNNER_REMAINING_GLOBAL_RESET_RE = re.compile(
    r"\b%s\s*=\s*0U\s*;" % re.escape(_REMAINING_SYMBOL)
)
_RUNNER_REMAINING_SERIALIZE_RE = re.compile(
    r"put32\s*\(\s*&\s*c\s*,\s*d\s*(?:\.|->)\s*%s\s*\)\s*;"
    r"|out_words\s*\[\s*100\s*\]\s*=\s*d\s*(?:\.|->)\s*%s\s*;" % (_REMAINING_FIELD, _REMAINING_FIELD)
)
_REMAINING_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(_REMAINING_SYMBOL)
)
_WRITE_OP_RE = re.compile(r"\s*(?:\+\+|--|<<=|>>=|[-+*/%&|^]=|=(?!=))")
_PREFIX_WRITE_OP_RE = re.compile(r"(?:\+\+|--)\s*$")
_REMAINING_FIELD_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(_REMAINING_FIELD)
)
# Lexical constructs whose bodies are text rather than code. Each must close
# to match, so an unterminated one leaves its opening character as code --
# masking may never be used to hide a real reference behind a stray quote.
_LINE_COMMENT_RE = re.compile(r"//(?:\\[ \t]*\n|[^\n])*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL_RE = re.compile(r'"(?:\\[\s\S]|[^"\\\n])*"')
_CHAR_LITERAL_RE = re.compile(r"'(?:\\[\s\S]|[^'\\\n])+'")
# A `#define` is one *logical* line: `##` on a continuation is the same paste
# operator as `##` on the first line, so the directive is located here and its
# extent is walked through the splices by `_logical_line_end`.
_DEFINE_DIRECTIVE_RE = re.compile(r"(?m)^[ \t]*#[ \t]*define\b")
# The record the runner publishes through, mentioned as a whole rather than
# through a member: `&d` (but not `&d.field` or `&d->field`) and `d = ...` (but
# not `d.field = ...`). Both are how a publication can be undone without ever
# spelling the field -- `__builtin_memset(&d, 0, sizeof d)`, a compound-literal
# reassignment, or handing the record's address to a function that scrubs it.
_RUNNER_RECORD_ADDRESS_RE = re.compile(r"&\s*d(?![A-Za-z0-9_])(?!\s*(?:\.|->))")
_RUNNER_RECORD_ASSIGN_RE = re.compile(r"(?<![A-Za-z0-9_])d\s*=(?!=)")
# The record object whose scope the whole-record rule is stated over, and the
# one whole-record address use that scope may contain. The reset is pinned to
# the canonical spelling -- plain `memset`, parenthesised `sizeof (d)` -- so
# that a scrub wearing its shape (`__builtin_memset(&d, 0, sizeof d)`) is an
# unpermitted address use rather than a second reset.
_RUNNER_RECORD_DECL_RE = re.compile(r"(?<![A-Za-z0-9_])pmu_diag_record_t\s+d\s*(?:=|;)")
_RUNNER_RECORD_RESET_RE = re.compile(
    r"(?<![A-Za-z0-9_])memset\s*\(\s*&\s*d\s*,\s*0\s*,\s*sizeof\s*\(\s*d\s*\)\s*\)\s*;"
)
_VENDOR_REMAINING_DECLARATION_RE = re.compile(
    r"(?:extern\s+)?volatile\s+uint32_t\s+(%s)\s*(?:=\s*0U\s*)?;" % re.escape(_REMAINING_SYMBOL)
)
# CMSIS `NVIC_Type` covers 0xE000E100..0xE000E4EF -- ISER at +0x000, ICER at
# +0x080, ISPR +0x100, ICPR +0x180, IABR +0x200, IPR +0x300 -- and its base
# address is also ISER[0]. A compiler therefore parks the single word
# 0xE000E100 in the literal pool and reaches every one of those registers as
# base + displacement, which is exactly how the retained V12 hard bypass writes
# ICER and ICPR. Only ISER writes enable an interrupt, so the drift term is the
# resolved destination, never the literal.
_NVIC_BLOCK_FIRST = 0xE000E100
_NVIC_BLOCK_LAST = 0xE000E4EF
# ISER is the *whole* NVIC_ISER0..NVIC_ISER15 bank, 0xE000E100..0xE000E13C in
# the Armv7-M/Armv8-M register map -- CMSIS `NVIC_Type.ISER[16U]`, whose 0x40
# bytes are followed by 0x40 reserved bytes before ICER lands at +0x080. No
# CMSIS header is vendored in this repository, so the bound is taken from that
# architectural map; taking only ISER[0] would let an enable of any IRQ above
# 31 through, and the diag's own NPU0 IRQ is not pinned to ISER[0] by anything
# this gate can see.
_NVIC_ISER_FIRST = 0xE000E100
_NVIC_ISER_LAST = 0xE000E13F
_NVIC_BLOCK_HIGH_HALFWORD = _NVIC_BLOCK_FIRST >> 16
# How far outside `NVIC_Type` a base may be proven and still be treated as a
# pointer into it once a writeback form advances it by an amount this gate
# cannot read. The block's own span is the bound: a base further away than the
# whole register file cannot be walking it.
_NVIC_WRITEBACK_REACH = _NVIC_BLOCK_LAST - _NVIC_BLOCK_FIRST + 1
_REG_TOKEN_RE = re.compile(r"\b(?:r\d+|sl|sb|fp|ip|sp|lr|pc)\b")
_QUAL_IMMEDIATE_RE = re.compile(r"#(-?(?:0x[0-9A-Fa-f]+|\d+))")
_MEMORY_BASE_RE = re.compile(r"\[\s*([a-z0-9]+)")
_REGISTER_LIST_RE = re.compile(r"\{([^}]*)\}")
# Store-family prefixes the whole-image gate must look at. ``check_pmu_qual``
# decodes a destination only for ``str*`` with a literal- or immediate-proven
# base, so every other one of these reaches an address the resolver cannot see
# -- and a store-multiple through an NVIC-block base writes ISER just as surely
# as a single store does. ``vst`` is deliberately the bare prefix rather than
# ``vstr``/``vstm``: Armv8.1-M Helium, which the MPS4 Cortex-M55 implements,
# writes memory through ``VST20``..``VST43`` interleaving stores and A-profile
# builds through ``VST1``..``VST4``, none of which match a longer prefix. This
# list is still an allow-list of *names*, so a store mnemonic outside it is not
# examined at all -- the limit the contract states rather than one it hides.
_STORE_FAMILY_PREFIXES = ("str", "stm", "stl", "stc", "vst")
_MULTIPLE_TRANSFER_PREFIXES = ("stm", "ldm")
_LOAD_MULTIPLE_PREFIXES = ("ldm", "pop", "vpop")
# ``vpush``/``vpop`` name no base in their operands; like ``push``/``pop`` they
# transfer through ``sp``, which is what ``_memory_base`` reports for them so
# the store filter judges them on the stack pointer rather than on nothing.
_STACK_TRANSFER_MNEMONICS = frozenset(("push", "pop", "vpush", "vpop"))
# Mnemonics that overwrite their destination without reading it. Every other
# two-operand data-processing form reads the register it writes.
_FULL_WRITE_MNEMONICS = frozenset(
    ("mov", "movs", "movw", "mvn", "mvns", "adr", "ldr", "ldrb", "ldrh", "ldrsb", "ldrsh")
)

_HEX_WORD_RE = re.compile(r"\.word\s+0x([0-9A-Fa-f]+)")
_ENCODING_RE = re.compile(r"^(?:[0-9a-f]{8}|[0-9a-f]{4}(?:\s+[0-9a-f]{4})*)\s+(?=[a-z.])")
_BRANCH_TARGET_RE = re.compile(r"\b([0-9a-fA-F]+)\s+<")
# Group 3 of a load/store is whatever else lives inside the brackets: empty for
# `[r7]`, `, #4` for a displaced access, `, r2` or `, r2, lsl #1` for a
# register-offset one. `_displacement` reads it, and reports None for every
# form whose displacement is not a plain immediate so the address stays
# unproven rather than being silently taken as zero.
_REG_NAME_RE = r"(?:r\d+|sl|sb|fp|ip|sp|lr|pc)"
_LOAD_RE = re.compile(r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+(%s),\s*\[([a-z0-9]+)([^\]]*)\]" % _REG_NAME_RE)
_PC_LOAD_RE = re.compile(r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+(%s),\s*\[pc\b" % _REG_NAME_RE)
_PC_OFFSET_RE = re.compile(
    r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+%s,\s*\[pc,\s*#(-?\d+)\]" % _REG_NAME_RE
)
_STORE_RE = re.compile(r"^str(?:b|h)?(?:\.w)?\s+(%s),\s*\[([a-z0-9]+)([^\]]*)\]" % _REG_NAME_RE)
_DISPLACEMENT_RE = re.compile(r"^,\s*#(-?(?:0x[0-9a-fA-F]+|\d+))$")
# Writeback: `[rN, #imm]!` advances the base before the access, `[rN], #imm`
# after it. Both live *outside* the brackets, so `_LOAD_RE`/`_STORE_RE` report
# the displacement the access uses and nothing about the advance, and
# `_defined_register` reads the first register operand, which is never the
# base. The base would therefore keep its literal binding while the next access
# through it touches the next word of the window -- the polled STATUS pointer
# walking the U85 register file, a P2 that reads DWT CPICNT while the gate
# certifies CYCCNT. The form is refused outright, the way register-offset
# addressing already is, rather than modelled.
_WRITEBACK_RE = re.compile(r"\]\s*(?:!|,)")
_DECREMENT_RE = re.compile(r"^subs(?:\.w)?\s+(%s),\s*#1$" % _REG_NAME_RE)
_TEST_RE = re.compile(r"^tst(?:\.w)?\s+(r\d+),\s*#(\d+)$")
_DEST_RE = re.compile(r"^[a-z][a-z0-9.]*\s+(%s)\b" % _REG_NAME_RE)
_CALL_TO_RE = r"\bbl(?:x)?(?:\.w)?\s+[0-9a-fA-F]+\s+<%s>"

_WRITING_MNEMONICS = frozenset(
    (
        "mov", "movs", "movw", "movt", "mvn", "mvns", "neg", "negs",
        "add", "adds", "adc", "adcs", "sub", "subs", "sbc", "sbcs", "rsb", "rsbs",
        "and", "ands", "orr", "orrs", "orn", "eor", "eors", "bic", "bics",
        "lsl", "lsls", "lsr", "lsrs", "asr", "asrs", "ror", "rors",
        "mul", "muls", "mla", "mls", "udiv", "sdiv",
        "ldr", "ldrb", "ldrh", "ldrsb", "ldrsh",
        "uxtb", "uxth", "sxtb", "sxth", "rev", "rev16", "clz", "ubfx", "sbfx",
    )
)
_STACK_MNEMONICS = frozenset(("push", "pop", "stm", "stmdb", "ldm", "ldmia"))
_CALL_MNEMONICS = frozenset(("bl", "blx"))
_BARRIER_MNEMONICS = frozenset(("dsb", "isb", "dmb"))
_COND_BRANCH_MNEMONICS = frozenset(
    (
        "bne", "beq", "bcs", "bhs", "bcc", "blo", "bmi", "bpl", "bvs", "bvc",
        "bhi", "bls", "bge", "blt", "bgt", "ble", "cbz", "cbnz",
    )
)
_UNCONDITIONAL_BRANCH_MNEMONIC = "b"
# The helper is entered at its first instruction; every "can the helper execute
# this?" question is a reachability question anchored there.
_HELPER_ENTRY_INDEX = 0
_INDIRECT_BRANCH_MNEMONICS = frozenset(("bx", "blx", "tbb", "tbh"))
_IT_RE = re.compile(r"^it[te]{0,3}$")
_PC_DEST_RE = re.compile(r"^[a-z][a-z0-9.]*\s+pc\b")
_STORE_MNEMONICS = frozenset(("str", "strb", "strh"))
_COMPARE_MNEMONICS = frozenset(("cmp", "cmn", "tst", "teq"))
_MULTI_REGISTER_TRANSFER_MNEMONICS = frozenset(("ldrd", "strd"))
# A long multiply writes RdLo *and* RdHi, and `_defined_register` reports only
# the first register operand -- so the second destination would redefine the
# published countdown register with the multiply-high result while the live-out
# proof reads the instruction as writing something else entirely. Modelling two
# destinations for one mnemonic family buys nothing the helper needs, so the
# family is refused on any path the helper can execute.
_MULTI_DESTINATION_MNEMONICS = frozenset(
    ("umull", "smull", "umlal", "smlal", "umaal", "smlald", "smlsld")
)
# The whole vocabulary the live-out proof knows how to reason about. Anything
# outside it is refused rather than ignored, because `_defined_register` reports
# "defines nothing" for every mnemonic it does not list -- which is exactly what
# an unmodelled reload of the published register would look like.
_MODELLED_MNEMONICS = (
    _WRITING_MNEMONICS
    | _STORE_MNEMONICS
    | _COMPARE_MNEMONICS
    | _STACK_MNEMONICS
    | _CALL_MNEMONICS
    | _BARRIER_MNEMONICS
    | _COND_BRANCH_MNEMONICS
    | _INDIRECT_BRANCH_MNEMONICS
    | frozenset((_UNCONDITIONAL_BRANCH_MNEMONIC, "nop"))
)
_CONDITION_SUFFIXES = (
    "eq", "ne", "cs", "hs", "cc", "lo", "mi", "pl", "vs", "vc",
    "hi", "ls", "ge", "lt", "gt", "le",
)
# The back edge shape the V13 contract freezes: a flag-test branch, so the
# decrement whose flags it reads is recoverable from the instruction before it.
_BACK_EDGE_MNEMONIC = "bne"
# Publication counts saturate here, so a cycle through the store terminates the
# walk with a witness of the second visit instead of counting forever.
_MAX_PUBLICATIONS = 2
_V12_RUNTIME_DRIFT_CALLEES = ("NVIC_EnableIRQ",)
# STATUS load, completion test, success branch, two failed-path decrements and
# the back edge -- the whole of what one poll iteration is allowed to execute.
_CANONICAL_PER_ITERATION_INSTRUCTIONS = 6

# The region the cross-ELF equivalence boolean covers, named in the manifest so
# no consumer can read that boolean as whole-helper or whole-image equivalence.
EQUIVALENCE_SCOPE = "per_iteration_loop_region"


@dataclass(frozen=True)
class _Insn:
    """One helper instruction with the objdump encoding column removed."""

    addr: int
    mnemonic: str
    text: str
    target: int | None
    is_cond_branch: bool
    is_return: bool


@dataclass(frozen=True)
class PollLoop:
    variant: str
    helper_name: str
    helper_addr: int
    status_addr: int
    mask: int
    status_base_reg: str
    status_value_reg: str
    status_read_count: int
    failed_path_decrement_regs: tuple[str, ...]
    failed_path_decrement_count: int
    back_edge_target: int
    conditional_back_edge_count: int
    success_edge_count: int
    timeout_edge_count: int
    extra_per_iteration_instruction_count: int
    has_stack_access: bool
    has_extra_non_status_load: bool
    has_forbidden_loop_effect: bool
    signature: tuple[tuple[str, str | int], ...]


@dataclass(frozen=True)
class RemainingDataflowProof:
    source: str
    publication_register: str
    back_edge_induction_register: str
    remaining_store_after_p2_exactly_once: bool
    remaining_store_timeout_unreachable: bool
    remaining_from_back_edge_induction: bool
    synchronized_induction_pair: bool
    helper_leaf_no_stack_access: bool


@dataclass(frozen=True)
class _HelperAnalysis:
    variant: str
    helper_name: str
    helper_addr: int
    code: tuple[_Insn, ...]
    literals: tuple[tuple[int, int], ...]
    pc_targets: dict[int, int]
    pointer_words: tuple[dict[str, int], ...]
    status_index: int
    test_index: int
    success_branch_index: int
    success_index: int
    back_edge_index: int
    loop_head_addr: int
    status_base_reg: str
    status_value_reg: str
    mask: int
    decrement_regs: tuple[str, ...]
    loop_body: tuple[_Insn, ...]
    timeout_block: tuple[_Insn, ...]
    status_read_count: int
    conditional_back_edge_count: int
    success_edge_count: int
    timeout_edge_count: int
    has_stack_access: bool
    has_extra_non_status_load: bool


# --------------------------------------------------------------------------
# generated-source gate
# --------------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _count_raw_inputs(text: str, anchor: str, generated_marker: str, kind: str) -> None:
    if generated_marker in text:
        raise fail("generated %s input" % kind)
    count = text.count(anchor)
    if count == 0:
        raise fail("zero raw %s targets" % kind)
    if count != 1:
        raise fail("multiple raw %s targets" % kind)


def _blank_span(out: list[str], text: str, start: int, stop: int) -> None:
    """Overwrite a span with spaces, keeping its newlines so offsets hold."""
    for index in range(start, stop):
        if text[index] != "\n":
            out[index] = " "


def _mask_c_lexical(text: str) -> str:
    """Blank comment and literal *bodies*, returning a same-length string.

    Every rule below that reads C source reads this instead of the raw text, so
    that ``&d`` written inside a comment or a string is what it actually is --
    text, not a use of the record -- while every offset the caller reports still
    points into the original.

    Each construct is recognised by a pattern that must close: an unterminated
    block comment or literal simply does not match, and the opening character is
    then left as ordinary code. That is the fail-closed direction: the scan may
    look at something that is really comment text, but it can never be talked
    out of looking at real code by an unbalanced quote. Line splices inside a
    ``//`` comment and inside a string are honoured, because the C translation
    phases join them before either construct is recognised. Trigraphs are not:
    they are off by default in every mode this firmware builds under, and a
    ``??/`` splice is therefore out of scope rather than silently handled.
    """
    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "/" and index + 1 < length and text[index + 1] in "/*":
            pattern = _LINE_COMMENT_RE if text[index + 1] == "/" else _BLOCK_COMMENT_RE
        elif char == '"':
            pattern = _STRING_LITERAL_RE
        elif char == "'":
            pattern = _CHAR_LITERAL_RE
        else:
            index += 1
            continue
        hit = pattern.match(text, index)
        if hit is None:
            index += 1
            continue
        _blank_span(out, text, index, hit.end())
        index = hit.end()
    return "".join(out)


def _logical_line_end(text: str, start: int) -> int:
    """Offset of the newline that ends the logical line ``start`` is on.

    A backslash immediately before the newline -- trailing blanks tolerated,
    because every compiler this firmware builds under does -- splices the next
    physical line onto this one. A preprocessing directive is one *logical*
    line, so a rule scoped to a directive has to follow the splices or it stops
    at the first wrap, which is the ordinary formatting for any macro long
    enough to need one.
    """
    position = start
    while True:
        newline = text.find("\n", position)
        if newline < 0:
            return len(text)
        tail = newline
        while tail > position and text[tail - 1] in " \t":
            tail -= 1
        if tail > position and text[tail - 1] == "\\":
            position = newline + 1
            continue
        return newline


def _matching_brace(text: str, open_index: int, what: str) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise fail(what)


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def _extract_vendor_helper(vendor_text: str) -> tuple[str, int]:
    """Return the V13 poll helper body and its offset in the vendor TU."""
    definitions = vendor_text.count(_VENDOR_HELPER_DEF_MARKER)
    if definitions == 0:
        raise fail("poll helper signature not found")
    if definitions != 1:
        raise fail("duplicate V13 poll helper definition: found %d" % definitions)
    starts = (
        "__attribute__((noinline))\nstatic uint32_t v13_poll_completion(void)",
        "uint32_t __attribute__((noinline)) v13_poll_completion(void)",
        "static uint32_t v13_poll_completion(void)",
    )
    start = -1
    for candidate in starts:
        start = vendor_text.find(candidate)
        if start >= 0:
            break
    if start < 0:
        raise fail("poll helper signature not found")
    end = vendor_text.find("static int test_commands(", start)
    if end < 0:
        end = len(vendor_text)
    return vendor_text[start:end], start


def _remaining_write_positions(text: str) -> tuple[int, ...]:
    """Offsets of every write to the V13 remaining global, reads excluded."""
    positions = []
    for hit in _REMAINING_WORD_RE.finditer(text):
        if _PREFIX_WRITE_OP_RE.search(text[max(0, hit.start() - 4):hit.start()]):
            positions.append(hit.start())
        elif _WRITE_OP_RE.match(text, hit.end()):
            positions.append(hit.start())
    return tuple(positions)


def _verify_vendor_tu_single_writer(vendor_text: str, canonical_position: int) -> None:
    """The whole vendor TU may write the remaining global exactly once."""
    positions = _remaining_write_positions(vendor_text)
    if len(positions) != 1:
        raise fail("vendor TU remaining write count != 1: found %d" % len(positions))
    if positions[0] != canonical_position:
        raise fail("vendor TU remaining write must be the canonical helper success assignment")


def _reference_spans(text: str, patterns) -> tuple[tuple[int, int], ...]:
    return tuple((hit.start(), hit.end()) for pattern in patterns for hit in pattern.finditer(text))


def _reject_unclassified_references(text: str, token_re, spans, what: str) -> None:
    """Every mention of a name must lie inside one of the uses the gate models."""
    for hit in token_re.finditer(text):
        if not any(start <= hit.start() and hit.end() <= stop for start, stop in spans):
            raise fail("%s at offset %d" % (what, hit.start()))


def _reject_vendor_token_pasting(vendor_text: str) -> None:
    """Refuse the one alias the reference lock is structurally blind to.

    ``_reject_unclassified_references`` holds every *mention* of the symbol to a
    modelled use, and token pasting forms the symbol out of two fragments that
    are not mentions of it: ``GLUE(pmu_completion_poll_v13_t_poll_remaining_,
    at_success)`` publishes the slot while the token regex sees two unrelated
    identifiers. The generated vendor TU carries no ``##`` in any ``#define``,
    so refusing the operator there costs nothing the contract allows.

    The rule is stated over the directive's *logical* line, not its first
    physical one. Any macro long enough to wrap is written across a backslash
    continuation, and the motivating example is exactly that shape, so a rule
    that stopped at the first newline would refuse the paste only in the
    formatting nobody uses. Comment and string bodies are masked first, because
    the compiler removes comments before it looks for the operator and a ``##``
    inside a string literal is characters, not a paste.

    This is the only such construction the gate closes. A publication that
    reaches the slot without naming it at all -- an absolute-address store, a
    cast of a record pointer, inline assembly, or a store to the wire word by
    index -- is out of reach of any scan over source text. Nothing in this
    module covers those; see the module docstring for why the ELF half cannot.
    """
    masked = _mask_c_lexical(vendor_text)
    for directive in _DEFINE_DIRECTIVE_RE.finditer(masked):
        paste = masked.find("##", directive.end(), _logical_line_end(vendor_text, directive.end()))
        if paste >= 0:
            raise fail("vendor TU token pasting at offset %d" % paste)


def _verify_vendor_tu_reference_sites(vendor_text: str, canonical_position: int) -> None:
    """Hold the whole vendor TU to the two references the contract names.

    ``_remaining_write_positions`` classifies a mention by the operator directly
    next to the symbol token, and taking the symbol's *address* never puts one
    there: ``&SYM`` passed to a helper, handed to ``memcpy`` or returned from a
    getter publishes the slot while the write count stays at one. Rather than
    enumerate the ways an alias can be built, every mention must be either the
    definition or the canonical success assignment -- so a pointer to the slot
    cannot be formed inside this translation unit at all.
    """
    spans = tuple(
        (hit.start(1), hit.end(1)) for hit in _VENDOR_REMAINING_DECLARATION_RE.finditer(vendor_text)
    ) + ((canonical_position, canonical_position + len(_REMAINING_SYMBOL)),)
    _reject_unclassified_references(
        vendor_text,
        _REMAINING_WORD_RE,
        spans,
        "vendor TU remaining reference outside its definition and canonical write",
    )


def _verify_runner_reference_sites(runner_text: str) -> None:
    """Hold the runner to the uses its gate actually models.

    The record write gate reads ``d.<field> = ...`` and the global gate reads
    the extern, the reset and that copy. An alias defeats both the same way it
    defeats the vendor scan -- ``&d.<field>``, or a second pointer to the same
    record -- so the field and the global are each held to their declared uses
    instead of to a write count.
    """
    for token_re, patterns, what in (
        (
            _REMAINING_FIELD_WORD_RE,
            (
                _RUNNER_REMAINING_MEMBER_RE,
                _RECORD_REMAINING_WRITE_RE,
                _RUNNER_REMAINING_SERIALIZE_RE,
            ),
            "runner remaining record field reference outside its declared uses",
        ),
        (
            _REMAINING_WORD_RE,
            (
                _RUNNER_REMAINING_EXTERN_RE,
                _RUNNER_REMAINING_GLOBAL_RESET_RE,
                _RECORD_REMAINING_WRITE_RE,
            ),
            "runner remaining global reference outside its declared uses",
        ),
    ):
        _reject_unclassified_references(
            runner_text, token_re, _reference_spans(runner_text, patterns), what
        )


def _enclosing_block(masked: str, position: int) -> int:
    """Offset of the innermost ``{`` still open at ``position``."""
    depth = 0
    for index in range(position - 1, -1, -1):
        char = masked[index]
        if char == "}":
            depth += 1
        elif char == "{":
            if depth == 0:
                return index
            depth -= 1
    raise fail("runner record declaration is not inside a block")


def _verify_runner_record_scope(runner_text: str, copy_position: int) -> None:
    """Hold the record's whole scope to one whole-record address use.

    The reference locks are rules about *mentions* of the two names, so they
    cannot see a publication being undone through the record that encloses the
    field: ``__builtin_memset(&d, 0, sizeof d)``, ``d = (record_t){0}`` and
    ``scrub(&d)`` are all valid C that leave every count the gate keeps exactly
    as the canonical runner produces them while zeroing or caller-controlling
    the published word.

    Scanning only downstream of the success copy would see mutations and miss
    the capability behind them. An alias captured *upstream* --
    ``pmu_diag_record_t *alias = &d;`` above the copy, ``memset(alias, 0,
    ...)`` below it -- is a durable pointer the copy does not overwrite, and it
    spells neither the field nor the global anywhere the downstream scan looks.
    The rule is therefore stated over the record's scope as a whole: the
    innermost block the canonical ``pmu_diag_record_t d`` declaration lives in
    may contain exactly one whole-record address use, the canonical pre-run
    ``memset(&d, 0, sizeof(d));`` reset, which must itself precede the copy;
    and exactly one whole-record assignment, the declaration's own initializer.
    Nothing else in that scope may name the record as a whole. A ``&d``
    *outside* the scope belongs to a different object and is not examined, and
    taking the address of a *member* is untouched -- it is how the runner
    captures every other snapshot -- so this stays a rule about one record, not
    about the ``&d`` spelling.

    The scan is lexical, over comment- and literal-masked text, so a comment
    that discusses ``&d`` or a string that contains it is not a use. What no
    rule over source text reaches is a publication that never names the record
    at all: an absolute-address store, a cast, inline assembly, or a store to
    the wire word by index. Those are unqualified -- see the module docstring.
    """
    masked = _mask_c_lexical(runner_text)
    declarations = list(_RUNNER_RECORD_DECL_RE.finditer(masked))
    if len(declarations) != 1:
        raise fail("runner record declaration: expected 1 match, found %d" % len(declarations))
    declaration = declarations[0]
    terminator = masked.find(";", declaration.start())
    if terminator < 0:
        raise fail("runner record declaration is unterminated")

    scope_open = _enclosing_block(masked, declaration.start())
    scope_end = _matching_brace(masked, scope_open, "runner record scope is unbalanced")
    if not scope_open < copy_position < scope_end:
        raise fail("runner success copy must lie in the record's scope")

    resets = list(_RUNNER_RECORD_RESET_RE.finditer(masked, scope_open, scope_end))
    if len(resets) != 1:
        raise fail("runner record pre-run reset: expected 1 match, found %d" % len(resets))
    if resets[0].start() > copy_position:
        raise fail("runner record pre-run reset must precede the success copy")

    for pattern, permitted, what in (
        (
            _RUNNER_RECORD_ADDRESS_RE,
            resets[0].span(),
            "its address is taken outside the canonical pre-run reset",
        ),
        (
            _RUNNER_RECORD_ASSIGN_RE,
            (declaration.start(), terminator + 1),
            "it is assigned as a whole outside its declaration",
        ),
    ):
        for hit in pattern.finditer(masked, scope_open, scope_end):
            if not (permitted[0] <= hit.start() and hit.end() <= permitted[1]):
                raise fail("runner record mutated: %s at offset %d" % (what, hit.start()))


def _verify_runner_remaining_gate(runner_text: str) -> None:
    """Prove the runner can publish remaining only on the success path.

    The two record writes are located by brace nesting relative to the
    ``poll_result != V13_POLL_SUCCESS`` gate and classified by their normalized
    right-hand side, so re-indenting or re-aligning the generated runner cannot
    change which write is which. The whole-record rule this function then runs
    is lexical rather than structural -- it reads masked source text, not a
    parse -- so its own immunity to reformatting is the narrower one the mask
    provides: comments, string literals and whitespace do not move the verdict,
    but it is a scan over text and does not claim to be anything else.
    """
    gates = list(_RUNNER_TIMEOUT_GATE_RE.finditer(runner_text))
    if len(gates) != 1:
        raise fail("runner timeout gate: expected 1 match, found %d" % len(gates))
    gate_open = runner_text.index("{", gates[0].start())
    gate_end = _matching_brace(runner_text, gate_open, "runner timeout gate is unbalanced")

    writes = [
        (hit.start(), _normalize_spaces(hit.group(1)))
        for hit in _RECORD_REMAINING_WRITE_RE.finditer(runner_text)
    ]
    inside = [item for item in writes if gate_open < item[0] < gate_end]
    outside = [item for item in writes if not gate_open < item[0] < gate_end]
    if len(inside) != 1 or inside[0][1] != "0U":
        raise fail("runner timeout gate must reset remaining to 0U")
    if len(writes) != 2:
        raise fail("runner remaining write count != 2: found %d" % len(writes))
    if len(outside) != 1 or outside[0][1] != _REMAINING_SYMBOL:
        raise fail("runner success copy must read the V13 remaining global")
    if outside[0][0] > gate_open:
        raise fail("runner success copy must precede the timeout gate")
    _verify_runner_record_scope(runner_text, outside[0][0])


def _verify_runner_source(runner_text: str) -> None:
    if "PMU_COMPLETION_POLL_DIAG_V13" not in runner_text:
        raise fail("runner schema marker missing")
    if "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x%08XU" % BUILD_ID not in runner_text:
        raise fail("runner build id missing")
    for pattern, what in (
        (_RUNNER_REMAINING_EXTERN_RE, "runner remaining extern"),
        (_RUNNER_REMAINING_MEMBER_RE, "runner remaining field"),
        (_RUNNER_REMAINING_GLOBAL_RESET_RE, "runner remaining global reset"),
    ):
        found = len(pattern.findall(runner_text))
        if found != 1:
            raise fail("%s: expected 1 match, found %d" % (what, found))
    for needle, what in (
        ("PMU_DIAG_FIELD_COUNT 101U", "runner field count"),
        ("PMU_DIAG_TOTAL_WORDS 109U", "runner total words"),
        ("PMU_DIAG_PAYLOAD_SIZE 436U", "runner payload size"),
    ):
        if needle not in runner_text and needle.replace(" ", " == ") not in runner_text:
            raise fail("%s missing" % what)
    if _RUNNER_REMAINING_SERIALIZE_RE.search(runner_text) is None:
        raise fail("runner remaining serialization missing")
    _verify_runner_remaining_gate(runner_text)
    _verify_runner_reference_sites(runner_text)


def _verify_vendor_helper_source(helper: str) -> int:
    """Gate the helper body and return the offset of its remaining assignment."""
    if helper.count("*status_reg") != 1 or helper.count(_STATUS_READ_STATEMENT) != 1:
        raise fail("helper STATUS read count != 1")
    if helper.count(_SUCCESS_GUARD) != 1:
        raise fail("helper completion mask")
    if (
        "write_reg(NPU_REG_CMD" in helper
        or "read_reg(NPU_REG_QREAD)" in helper
        or "0x0000000C" in helper
    ):
        raise fail("retained V12 hard-bypass/CMD/QREAD/release drift")
    if re.findall(r"NPU_REG_[A-Z0-9_]+", helper) != ["NPU_REG_STATUS"]:
        raise fail("helper contains forbidden operation")
    if helper.count("U85_BASE_ADDRESS") != 1:
        raise fail("helper contains forbidden operation")

    if helper.count(_LOOP_HEADER) != 1:
        raise fail("canonical V13 helper shape missing")
    loop_open = helper.index("{", helper.index(_LOOP_HEADER))
    loop_end = _matching_brace(helper, loop_open, "canonical V13 helper shape missing")
    guard_start = helper.find(_SUCCESS_GUARD, loop_open)
    if not loop_open < guard_start < loop_end:
        raise fail("canonical V13 helper shape missing")
    guard_open = helper.index("{", guard_start)
    guard_end = _matching_brace(helper, guard_open, "canonical V13 helper shape missing")

    assignments = [
        (hit.start(), hit.group(1).strip())
        for hit in re.finditer(r"%s\s*=\s*([^;]+);" % re.escape(_REMAINING_SYMBOL), helper)
    ]
    references = len(re.findall(re.escape(_REMAINING_SYMBOL), helper))
    if references != len(assignments):
        raise fail("remaining store must be success-only")
    if any(position > loop_end for position, _ in assignments):
        raise fail("timeout path must not publish remaining")
    if any(not guard_open < position < guard_end for position, _ in assignments):
        raise fail("remaining store must be success-only")
    if len(assignments) != 1:
        raise fail("poll_remaining_at_success store count != 1")

    remaining_position, remaining_rhs = assignments[0]
    if remaining_rhs != _REMAINING_RHS:
        literal = re.fullmatch(r"(\d+)U?", remaining_rhs)
        if literal is not None and not 1 <= int(literal.group(1)) <= POLL_LIMIT:
            raise fail("success remaining must be in 1..%d" % POLL_LIMIT)
        raise fail("remaining must publish the failed-poll back-edge induction state")

    p1_position = helper.find(_P1_STATEMENT, guard_open)
    p2_position = helper.find(_P2_STATEMENT, guard_open)
    if not guard_open < p1_position < p2_position < remaining_position < guard_end:
        raise fail("remaining store must follow P2 exactly")
    if helper.find("return status;", remaining_position) > guard_end:
        raise fail("canonical V13 helper shape missing")

    if helper[loop_open + 1:guard_start].strip() != _STATUS_READ_STATEMENT:
        raise fail("extra per-iteration source statement")
    if helper[guard_end + 1:loop_end].strip():
        raise fail("extra per-iteration source statement")
    if "return 0U;" not in helper[loop_end:]:
        raise fail("canonical V13 helper shape missing")
    return remaining_position


def verify_generated_sources(
    runner_text: str,
    vendor_text: str,
    *,
    raw_runner_sha256: str | None = None,
    raw_vendor_sha256: str | None = None,
) -> dict[str, object]:
    """Gate the generated V13 runner/vendor sources.

    The two raw SHA-256 pins are a pair, never a single side: supplying both
    means the arguments are the frozen *raw* generator inputs and both are held
    to the frozen-input contract; supplying neither means they are the generated
    outputs and both are held to the generated-source contract. A one-sided pin
    would silently leave the other translation unit unvalidated, so it is
    rejected outright.
    """
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    if (raw_runner_sha256 is None) != (raw_vendor_sha256 is None):
        raise fail("raw runner and vendor sha pins must be supplied together")
    if raw_runner_sha256 is not None and raw_vendor_sha256 is not None:
        _count_raw_inputs(runner_text, _RAW_RUNNER_ANCHOR, _RAW_RUNNER_GENERATED_MARKER, "runner")
        if _sha256_text(runner_text) != raw_runner_sha256:
            raise fail("runner hash mismatch")
        _count_raw_inputs(vendor_text, _RAW_VENDOR_ANCHOR, _RAW_VENDOR_GENERATED_MARKER, "vendor")
        if _sha256_text(vendor_text) != raw_vendor_sha256:
            raise fail("vendor hash mismatch")
    else:
        _verify_runner_source(runner_text)
        _reject_vendor_token_pasting(vendor_text)
        helper, helper_start = _extract_vendor_helper(vendor_text)
        remaining_offset = _verify_vendor_helper_source(helper)
        _verify_vendor_tu_single_writer(vendor_text, helper_start + remaining_offset)
        _verify_vendor_tu_reference_sites(vendor_text, helper_start + remaining_offset)

    return {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "poll_remaining_symbol": _REMAINING_SYMBOL,
    }


# --------------------------------------------------------------------------
# final-ELF gate
# --------------------------------------------------------------------------


def _helper_name_from_nm(nm_text: str) -> str:
    names = re.findall(r"^[0-9A-Fa-f]+\s+[Tt]\s+([A-Za-z0-9_]+)$", nm_text, re.M)
    present = [
        candidate
        for candidate in ("v12_poll_completion", "v13_poll_completion")
        if names.count(candidate) >= 1
    ]
    if not present:
        raise fail("poll helper symbol in nm: expected 1 text symbol, found 0")
    if len(present) > 1:
        raise fail("duplicate poll helper symbol in nm: %s" % ", ".join(present))
    candidate = present[0]
    defined = names.count(candidate)
    if defined != 1:
        raise fail("duplicate poll helper symbol in nm: %s defined %d times" % (candidate, defined))
    return candidate


def _symbol_addr_from_nm(nm_text: str, symbol: str) -> int:
    match = re.search(r"^([0-9A-Fa-f]+)\s+[Tt]\s+%s$" % re.escape(symbol), nm_text, re.M)
    if match is None:
        raise fail("missing symbol in nm: %s" % symbol)
    return int(match.group(1), 16)


def _split_code_and_literals(raw_insns) -> tuple[tuple[_Insn, ...], tuple[tuple[int, int], ...]]:
    """Normalize objdump rows into instructions plus the helper literal pool.

    The V12 parser keeps the raw encoding column in ``text``; strip it here so
    mnemonic classification does not depend on the objdump invocation flags.
    Literal-pool entries keep their address next to their word so a PC-relative
    load can be resolved back to the exact slot it reads.
    """
    code: list[_Insn] = []
    words: list[tuple[int, int]] = []
    for raw in raw_insns:
        body = _ENCODING_RE.sub("", raw.text).strip()
        if body.startswith(".word"):
            hit = _HEX_WORD_RE.search(body)
            if hit is None:
                raise fail("helper literal pool word unreadable")
            words.append((raw.addr, int(hit.group(1), 16)))
            continue
        if not body or body.startswith(".") or body == "nop":
            continue
        mnemonic = body.split()[0].lower().split(".")[0]
        target_hit = _BRANCH_TARGET_RE.search(body)
        code.append(
            _Insn(
                addr=raw.addr,
                mnemonic=mnemonic,
                text=body,
                target=int(target_hit.group(1), 16) if target_hit else None,
                is_cond_branch=mnemonic in _COND_BRANCH_MNEMONICS,
                is_return=(mnemonic == "bx" and body.rstrip().endswith("lr"))
                or (mnemonic == "pop" and "pc" in body),
            )
        )
    return tuple(code), tuple(words)


def _defined_register(insn: _Insn) -> str | None:
    if insn.mnemonic not in _WRITING_MNEMONICS:
        return None
    if _STORE_RE.match(insn.text):
        return None
    hit = _DEST_RE.match(insn.text)
    return hit.group(1) if hit else None


def _is_stack_access(insn: _Insn) -> bool:
    return "[sp" in insn.text or insn.mnemonic in _STACK_MNEMONICS


def _is_call(insn: _Insn) -> bool:
    return insn.mnemonic in _CALL_MNEMONICS


def _is_barrier(insn: _Insn) -> bool:
    return insn.mnemonic in _BARRIER_MNEMONICS


def _pc_literal_target(insn: _Insn) -> int:
    """Resolve a PC-relative load to its literal slot under Thumb PC semantics.

    Thumb reads the literal pool through ``Align(PC, 4)`` where ``PC`` is the
    instruction address plus four, so the slot is ``((addr + 4) & ~3) + imm``.
    Both the 16-bit and 32-bit encodings share that rule, which is why the
    encoding width never has to be modelled.
    """
    hit = _PC_OFFSET_RE.match(insn.text)
    if hit is None:
        raise fail("PC-relative literal offset unreadable: %s" % insn.text)
    return ((insn.addr + 4) & ~3) + int(hit.group(1))


def _resolve_pc_literals(
    code: tuple[_Insn, ...], literals: tuple[tuple[int, int], ...]
) -> dict[int, int]:
    """Map each PC-relative load index to the literal-pool address it reads."""
    slots = dict(literals)
    targets: dict[int, int] = {}
    for index, insn in enumerate(code):
        if _PC_LOAD_RE.match(insn.text) is None:
            continue
        target = _pc_literal_target(insn)
        if target not in slots:
            raise fail(
                "PC-relative literal target 0x%08X outside helper literal pool" % target
            )
        targets[index] = target
    return targets


def _pointer_bindings(
    code: tuple[_Insn, ...],
    pc_targets: dict[int, int],
    literals: tuple[tuple[int, int], ...],
) -> tuple[dict[str, int], ...]:
    """Per-instruction map of registers to the literal word they still hold.

    A register is bound only by a PC-relative load and is dropped the moment any
    other instruction redefines it, so a pointer that was recomputed at runtime
    never counts as literal-pool resolved.

    This walk is in layout order, which is what the *shape* checks want: they
    ask what the stream says about each site. It is not on its own a statement
    about what the helper executes, so ``_reject_layout_only_addresses`` holds
    every address it certifies against the same walk over the helper's edges.
    """
    slots = dict(literals)
    states: list[dict[str, int]] = []
    state: dict[str, int] = {}
    for index, insn in enumerate(code):
        states.append(dict(state))
        state = _binding_transfer(state, index, insn, pc_targets, slots)
    return tuple(states)


def _binding_transfer(
    state: dict[str, int],
    index: int,
    insn: _Insn,
    pc_targets: dict[int, int],
    slots: dict[int, int],
) -> dict[str, int]:
    """``state`` after ``insn``: the one binding rule, shared by both walks."""
    after = dict(state)
    target = pc_targets.get(index)
    if target is not None:
        after[_PC_LOAD_RE.match(insn.text).group(1)] = slots[target]
        return after
    dest = _defined_register(insn)
    if dest is not None:
        after.pop(dest, None)
    return after


def _cfg_pointer_bindings(
    code: tuple[_Insn, ...],
    successors: tuple[tuple[int, ...], ...],
    pc_targets: dict[int, int],
    literals: tuple[tuple[int, int], ...],
) -> tuple[dict[str, int] | None, ...]:
    """Bindings that hold on *every* path from the helper entry to each index.

    ``_pointer_bindings`` walks the instruction stream in layout order, so a
    register keeps the literal its last preceding load put there whether or not
    the paths that actually reach the instruction ran that load. This is the
    same walk over the helper's own edges instead, meeting predecessors by
    agreement: a register keeps a literal only if every predecessor agrees on
    it. ``None`` marks an index no path reaches, which the caller leaves alone.

    The meet starts optimistic -- an index inherits its first predecessor's
    state outright and intersects on every later visit -- because a loop header
    is otherwise met against a back edge that has not been walked yet, which
    would drop the loop-invariant STATUS pointer the contract requires.
    """
    slots = dict(literals)
    states: list[dict[str, int] | None] = [None] * len(code)
    states[_HELPER_ENTRY_INDEX] = {}
    changed = True
    while changed:
        changed = False
        for index, insn in enumerate(code):
            state = states[index]
            if state is None:
                continue
            after = _binding_transfer(state, index, insn, pc_targets, slots)
            for successor in successors[index]:
                current = states[successor]
                if current is None:
                    merged = after
                else:
                    merged = {
                        reg: word for reg, word in current.items() if after.get(reg) == word
                    }
                if current is None or merged != current:
                    states[successor] = merged
                    changed = True
    return tuple(states)


def _reject_layout_only_addresses(
    analysis: _HelperAnalysis,
    cfg_words: tuple[dict[str, int] | None, ...],
    active: frozenset[int],
) -> None:
    """Refuse an effective address the helper's own edges cannot certify.

    Every address term in this module reads ``pointer_words``, which is built in
    layout order. A control-flow edge that reaches an access without executing
    the literal load feeding its base therefore leaves the access certified
    against a word the register never held on that edge -- the STATUS load
    proven at 0x50004004, the publication proven at its own slot -- while what
    it touches is whatever the taken path left in the base. Writeback is one way
    a certified address and a touched address drift apart; this is the other,
    and it is closed by requiring the two walks to agree wherever the layout
    walk resolved anything at all.
    """
    for index in sorted(active):
        insn = analysis.code[index]
        hit = _STORE_RE.match(insn.text) or _LOAD_RE.match(insn.text)
        if hit is None or hit.group(2) == "pc":
            continue
        layout = _resolved_address(analysis.pointer_words[index], hit)
        if layout is None:
            continue
        state = cfg_words[index]
        if state is None or _resolved_address(state, hit) != layout:
            raise fail(
                "effective address unproven on some path reaching it: %s" % insn.text
            )


def _displacement(hit: re.Match[str]) -> int | None:
    """Immediate displacement of a matched load/store, or None when unproven.

    A bare `[rN]` displaces by zero and an explicit `#imm` by that immediate.
    Every other addressing mode -- register offset, shifted register, anything
    the assembler renders inside the brackets that is not a plain immediate --
    leaves the touched address dependent on a runtime value, so it is reported
    as unproven and the caller refuses it.
    """
    rest = hit.group(3).strip()
    if not rest:
        return 0
    imm = _DISPLACEMENT_RE.match(rest)
    return int(imm.group(1), 0) if imm else None


def _resolved_address(bindings: dict[str, int], hit: re.Match[str]) -> int | None:
    """Address a matched load/store touches: bound literal + displacement.

    None whenever either half is unproven, because a check that reasons about
    the base register alone constrains which object is addressed but never
    which word inside it -- the displacement is the other half of the address.
    """
    word = bindings.get(hit.group(2))
    displacement = _displacement(hit)
    if word is None or displacement is None:
        return None
    return word + displacement


def _reject_writeback_addressing(code: tuple[_Insn, ...]) -> None:
    """Refuse every access whose base register the gate cannot keep track of.

    Pointer bindings are what every effective-address check in this module
    stands on, and they are dropped only when an instruction *defines* the
    register. Writeback redefines the base without naming it as a destination,
    so an access certified against the literal it was loaded with silently walks
    forward on the next iteration. The helper's pointers are loop-invariant by
    contract, so refusing the form costs nothing the contract allows and closes
    the whole family at once.
    """
    for insn in code:
        if not _WRITEBACK_RE.search(insn.text):
            continue
        if _LOAD_RE.match(insn.text) or _STORE_RE.match(insn.text) or _PC_LOAD_RE.match(insn.text):
            raise fail("writeback addressing mode in helper: %s" % insn.text)


def _check_literal_pool(
    literals: tuple[tuple[int, int], ...], referenced: frozenset[int]
) -> None:
    for addr, word in literals:
        if addr not in referenced:
            raise fail("unreferenced helper literal 0x%08X at 0x%08X" % (word, addr))
    words = [word for _, word in literals]
    npu_words = [word for word in words if NPU_MMIO_BASE <= word < NPU_MMIO_LIMIT]
    if npu_words != [U85_BASE_ADDRESS]:
        raise fail("helper STATUS MMIO address")
    for word in words:
        if word in (U85_BASE_ADDRESS, DWT_BASE_ADDRESS):
            continue
        if SRAM_BASE <= word < SRAM_LIMIT:
            continue
        raise fail("helper references unexpected MMIO literal 0x%08X" % word)


def _forbidden_region_effect(insn: _Insn) -> str:
    """Name the effect that disqualifies ``insn`` from the per-iteration region."""
    if _is_call(insn):
        return "extra per-iteration call"
    if _is_stack_access(insn):
        return "extra per-iteration load/store"
    if _STORE_RE.match(insn.text):
        return "extra per-iteration store"
    if _LOAD_RE.match(insn.text) or _PC_LOAD_RE.match(insn.text):
        return "extra per-iteration load/store"
    if _is_barrier(insn):
        return "extra per-iteration barrier"
    return "extra per-iteration instruction"


def _reject_region_residue(residue: tuple[_Insn, ...]) -> None:
    """Fail closed on anything the per-iteration contract does not name."""
    if residue:
        raise fail(_forbidden_region_effect(residue[0]))


def _check_loop_body(loop_body: tuple[_Insn, ...]) -> tuple[str, ...]:
    decrements = tuple(
        hit.group(1) for hit in (_DECREMENT_RE.match(insn.text) for insn in loop_body) if hit
    )
    _reject_region_residue(
        tuple(insn for insn in loop_body if _DECREMENT_RE.match(insn.text) is None)
    )
    if len(decrements) != 2:
        raise fail("failed-poll decrement count")
    return decrements


def _analyze_helper(disassembly_text: str, nm_text: str) -> _HelperAnalysis:
    helper_name = _helper_name_from_nm(nm_text)
    helper_addr = _symbol_addr_from_nm(nm_text, helper_name)
    sections = re.findall(
        r"(?m)^[0-9a-fA-F]+\s+<%s>:\s*$" % re.escape(helper_name), disassembly_text
    )
    if len(sections) > 1:
        raise fail("duplicate poll helper section in disassembly: found %d" % len(sections))
    functions = parse_functions(disassembly_text)
    insns = functions.get(helper_name)
    if insns is None or not sections:
        raise fail("helper function in disassembly: expected 1 match, found 0")
    if insns[0].addr != helper_addr:
        raise fail("helper symbol/address mismatch")
    _function_section(disassembly_text, helper_name)

    code, literals = _split_code_and_literals(insns)
    if not code:
        raise fail("helper disassembly empty")
    _reject_writeback_addressing(code)

    tests = [(index, _TEST_RE.match(insn.text)) for index, insn in enumerate(code)]
    tests = [(index, hit) for index, hit in tests if hit is not None]
    if len(tests) != 1:
        raise fail("helper completion mask: expected 1 completion test, found %d" % len(tests))
    test_index, test_hit = tests[0]
    status_value_reg = test_hit.group(1)
    mask = int(test_hit.group(2))
    if mask != COMPLETION_MASK:
        raise fail("helper completion mask")

    status_index = -1
    for index in range(test_index - 1, -1, -1):
        hit = _LOAD_RE.match(code[index].text)
        if hit and hit.group(1) == status_value_reg and hit.group(2) != "pc":
            status_index = index
            break
    if status_index < 0:
        raise fail("helper STATUS read shape missing")
    status_base_reg = _LOAD_RE.match(code[status_index].text).group(2)
    status_reads = [
        insn
        for insn in code
        if (hit := _LOAD_RE.match(insn.text)) is not None and hit.group(2) == status_base_reg
    ]
    if len(status_reads) != 1:
        raise fail("helper STATUS read count != 1")
    loop_head_addr = code[status_index].addr

    success_branch_index = test_index + 1
    if success_branch_index >= len(code):
        raise fail("success branch missing")
    success_branch = code[success_branch_index]
    if not success_branch.is_cond_branch or success_branch.target is None:
        raise fail("success branch missing")
    success_addr = success_branch.target
    success_index = next((index for index, insn in enumerate(code) if insn.addr == success_addr), -1)
    if success_index <= success_branch_index:
        raise fail("success branch target missing")

    back_edges = [
        index
        for index, insn in enumerate(code)
        if insn.is_cond_branch and insn.target == loop_head_addr
    ]
    if len(back_edges) != 1:
        raise fail("conditional loop back-edge")
    back_edge_index = back_edges[0]
    if not success_branch_index < back_edge_index < success_index:
        raise fail("conditional loop back-edge")

    # The per-iteration region is everything the CPU re-executes: the STATUS
    # load, the completion test, the success branch, the failed-path tail and
    # the back edge. Nothing else may live inside it, so both the gap between
    # the load and the test and the failed-path tail are checked for residue.
    _reject_region_residue(code[status_index + 1:test_index])
    loop_body = code[success_branch_index + 1:back_edge_index]
    decrement_regs = _check_loop_body(loop_body)
    if status_base_reg in decrement_regs or status_value_reg in decrement_regs:
        raise fail("failed-poll decrement clobbers the STATUS read")

    timeout_block = code[back_edge_index + 1:success_index]
    for insn in timeout_block:
        if _STORE_RE.match(insn.text):
            raise fail("timeout path must not publish remaining")
    if not any(insn.is_return for insn in timeout_block):
        raise fail("timeout exit edge missing")

    pc_targets = _resolve_pc_literals(code, literals)
    _check_literal_pool(literals, frozenset(pc_targets.values()))
    pointer_words = _pointer_bindings(code, pc_targets, literals)

    # Each address below is the literal the base register still holds plus the
    # displacement the instruction encodes. Proving the base alone would leave
    # every one of these free to touch a neighbouring word of the same object:
    # a different NPU register, a different DWT register, a different global.
    status_hit = _LOAD_RE.match(code[status_index].text)
    if _resolved_address(pointer_words[status_index], status_hit) != STATUS_ADDRESS:
        raise fail("helper STATUS load must resolve to 0x%08X" % STATUS_ADDRESS)

    has_extra_non_status_load = False
    for index, insn in enumerate(code):
        hit = _LOAD_RE.match(insn.text)
        if hit is None or hit.group(2) == "pc" or index == status_index:
            continue
        if pointer_words[index].get(hit.group(2)) is None:
            has_extra_non_status_load = True
            break
        if _resolved_address(pointer_words[index], hit) != DWT_CYCCNT_ADDRESS:
            raise fail("cycle-count read must resolve to DWT CYCCNT 0x%08X" % DWT_CYCCNT_ADDRESS)
    # A publication must land on a slot the literal pool actually names. The
    # SRAM window alone would admit a store displaced off the intended slot into
    # whatever global happens to sit beside it, which is the failure the message
    # has always described.
    sram_slots = frozenset(
        word for _, word in literals if SRAM_BASE <= word < SRAM_LIMIT
    )
    for index, insn in enumerate(code):
        hit = _STORE_RE.match(insn.text)
        if hit is None:
            continue
        if _resolved_address(pointer_words[index], hit) not in sram_slots:
            raise fail("store destination must resolve to an SRAM literal slot")

    return _HelperAnalysis(
        variant="v12" if helper_name.startswith("v12_") else "v13",
        helper_name=helper_name,
        helper_addr=helper_addr,
        code=code,
        literals=literals,
        pc_targets=pc_targets,
        pointer_words=pointer_words,
        status_index=status_index,
        test_index=test_index,
        success_branch_index=success_branch_index,
        success_index=success_index,
        back_edge_index=back_edge_index,
        loop_head_addr=loop_head_addr,
        status_base_reg=status_base_reg,
        status_value_reg=status_value_reg,
        mask=mask,
        decrement_regs=decrement_regs,
        loop_body=loop_body,
        timeout_block=timeout_block,
        status_read_count=len(status_reads),
        conditional_back_edge_count=len(back_edges),
        success_edge_count=sum(
            1
            for insn in code[status_index:back_edge_index + 1]
            if insn.is_cond_branch and insn.target == success_addr
        ),
        timeout_edge_count=sum(1 for insn in timeout_block if insn.is_return),
        has_stack_access=any(_is_stack_access(insn) for insn in code),
        has_extra_non_status_load=has_extra_non_status_load,
    )


def _region_signature(analysis: _HelperAnalysis) -> tuple[tuple[str, str | int], ...]:
    """Effect signature of the per-iteration region, computed from the stream.

    Every entry is read off the parsed instructions: the opcode that performs
    each named step, the tested mask, the branch conditions and the counted
    edges. Register names, literal addresses, encoding widths and disassembly
    comments are all absent, so a relabelled or relocated build signs the same
    while a build that reads STATUS at a different width, tests a different
    mask or grows an iteration step does not.
    """
    code = analysis.code
    return (
        ("status_read_op", code[analysis.status_index].mnemonic),
        ("status_reads_per_iteration", analysis.status_read_count),
        ("completion_test_op", code[analysis.test_index].mnemonic),
        ("completion_mask", analysis.mask),
        ("success_branch_op", code[analysis.success_branch_index].mnemonic),
        ("success_edges", analysis.success_edge_count),
        ("failed_path_ops", "|".join(insn.mnemonic for insn in analysis.loop_body)),
        ("failed_path_decrements", len(analysis.decrement_regs)),
        ("back_edge_op", code[analysis.back_edge_index].mnemonic),
        ("conditional_back_edges", analysis.conditional_back_edge_count),
        ("timeout_edges", analysis.timeout_edge_count),
        (
            "per_iteration_instruction_count",
            analysis.back_edge_index - analysis.status_index + 1,
        ),
    )


def extract_poll_loop(disassembly_text: str, nm_text: str) -> PollLoop:
    analysis = _analyze_helper(disassembly_text, nm_text)
    return PollLoop(
        variant=analysis.variant,
        helper_name=analysis.helper_name,
        helper_addr=analysis.helper_addr,
        status_addr=STATUS_ADDRESS,
        mask=analysis.mask,
        status_base_reg=analysis.status_base_reg,
        status_value_reg=analysis.status_value_reg,
        status_read_count=analysis.status_read_count,
        failed_path_decrement_regs=analysis.decrement_regs,
        failed_path_decrement_count=len(analysis.decrement_regs),
        back_edge_target=analysis.loop_head_addr,
        conditional_back_edge_count=analysis.conditional_back_edge_count,
        success_edge_count=analysis.success_edge_count,
        timeout_edge_count=analysis.timeout_edge_count,
        extra_per_iteration_instruction_count=(
            analysis.back_edge_index
            - analysis.status_index
            + 1
            - _CANONICAL_PER_ITERATION_INSTRUCTIONS
        ),
        has_stack_access=analysis.has_stack_access,
        has_extra_non_status_load=analysis.has_extra_non_status_load,
        has_forbidden_loop_effect=any(
            _is_call(insn) or _is_stack_access(insn) or _is_barrier(insn) or _STORE_RE.match(insn.text)
            for insn in analysis.code[analysis.status_index:analysis.back_edge_index + 1]
        ),
        signature=_region_signature(analysis),
    )


def normalize_poll_loop(loop: PollLoop) -> tuple[tuple[str, str | int], ...]:
    """Register names, addresses and literal-pool layout are normalized away."""
    return loop.signature


def _build_helper_cfg(code: tuple[_Insn, ...]) -> tuple[tuple[int, ...], ...]:
    """Successor indices for every helper instruction.

    Exactly four edge kinds are modelled: a direct conditional branch (taken
    target plus fall-through), a direct unconditional ``b`` (taken target only),
    a plain fall-through, and a return (no successor). Anything whose successors
    would have to be guessed is refused rather than approximated -- a call, an
    indirect branch, a branch out of the helper, or an IT block, which is the
    only way Thumb-2 reaches predication and would otherwise turn a modelled
    unconditional edge into a conditional one.
    """
    index_of = {insn.addr: index for index, insn in enumerate(code)}
    successors: list[tuple[int, ...]] = []
    for index, insn in enumerate(code):
        if insn.is_return:
            successors.append(())
            continue
        if _is_call(insn):
            raise fail("helper CFG cannot model a call")
        if insn.mnemonic in _INDIRECT_BRANCH_MNEMONICS or _PC_DEST_RE.match(insn.text):
            raise fail("helper CFG cannot model an indirect branch")
        if _IT_RE.match(insn.mnemonic):
            raise fail("helper CFG cannot model a predicated instruction")

        taken: tuple[int, ...] = ()
        if insn.is_cond_branch or insn.mnemonic == _UNCONDITIONAL_BRANCH_MNEMONIC:
            if insn.target is None or insn.target not in index_of:
                raise fail("helper CFG branch target outside the helper")
            taken = (index_of[insn.target],)
            if not insn.is_cond_branch:
                successors.append(taken)
                continue
        if index + 1 >= len(code):
            raise fail("helper CFG falls off the end of the helper")
        successors.append(taken + (index + 1,))
    return tuple(successors)


def _reachable(successors: tuple[tuple[int, ...], ...], entry: int) -> frozenset[int]:
    seen: set[int] = set()
    stack = [entry]
    while stack:
        index = stack.pop()
        if index in seen:
            continue
        seen.add(index)
        stack.extend(successors[index])
    return frozenset(seen)


def _return_publication_counts(
    successors: tuple[tuple[int, ...], ...], entry: int, publisher: int
) -> frozenset[int]:
    """Publication counts observed at every return reachable from ``entry``.

    The walk is over ``(instruction, publications so far)`` pairs, so a path
    that skips the store and a path that takes it stay distinct states and a
    cycle back through the store is seen as a second publication. The empty set
    means no return is reachable at all, which the caller reads as a failure the
    same way an unbalanced count is.
    """
    counts: set[int] = set()
    seen: set[tuple[int, int]] = set()
    stack = [(entry, 0)]
    while stack:
        state = stack.pop()
        if state in seen:
            continue
        seen.add(state)
        index, count = state
        if index == publisher:
            count = min(count + 1, _MAX_PUBLICATIONS)
        if not successors[index]:
            counts.add(count)
            continue
        stack.extend((successor, count) for successor in successors[index])
    return frozenset(counts)


def _stores_to(analysis: _HelperAnalysis, address: int) -> frozenset[int]:
    """Indices of every helper store whose destination resolves to ``address``."""
    return frozenset(
        index
        for index, insn in enumerate(analysis.code)
        if (hit := _STORE_RE.match(insn.text)) is not None
        and _resolved_address(analysis.pointer_words[index], hit) == address
    )


def _success_block(analysis: _HelperAnalysis) -> tuple[_Insn, ...]:
    """Every instruction from the success entry to the end of the helper.

    The block deliberately runs past the first return rather than stopping at
    it: an early return planted ahead of the publication must still leave the
    store visible to the classifier, so that the control-flow proof is what
    rejects it instead of a store count that quietly lost sight of it.
    """
    if not any(insn.is_return for insn in analysis.code[analysis.success_index:]):
        raise fail("success path return missing")
    return analysis.code[analysis.success_index:]


def _classify_success_stores(block: tuple[_Insn, ...]) -> tuple[list[int], list[tuple[int, str]]]:
    """Split success-path stores into memory-derived (P1/P2) and live-in stores."""
    memory_derived: set[str] = set()
    cyccnt_store_offsets: list[int] = []
    live_in_stores: list[tuple[int, str]] = []
    for offset, insn in enumerate(block):
        store = _STORE_RE.match(insn.text)
        if store is not None:
            if store.group(1) in memory_derived:
                cyccnt_store_offsets.append(offset)
            else:
                live_in_stores.append((offset, store.group(1)))
            continue
        dest = _defined_register(insn)
        if dest is None:
            continue
        load = _LOAD_RE.match(insn.text)
        if load is not None and load.group(2) != "pc":
            memory_derived.add(dest)
        else:
            memory_derived.discard(dest)
    return cyccnt_store_offsets, live_in_stores


def _is_predicated(mnemonic: str) -> bool:
    """True for an IT block header or an instruction carrying a condition code.

    Predication is the one way a Thumb-2 instruction writes a register without
    the write being visible in its mnemonic's usual meaning, so a ``moveq`` that
    reloads the published register must never be read as an ordinary ``mov``.
    Mnemonics the gate already models are exempt, which keeps the flag-setting
    ``s`` forms (``adcs``, ``sbcs``, ``bics``) and the conditional branches from
    being mistaken for predicated writes.
    """
    if _IT_RE.match(mnemonic):
        return True
    if mnemonic in _MODELLED_MNEMONICS:
        return False
    return any(
        mnemonic.endswith(suffix) and mnemonic[: -len(suffix)] in _WRITING_MNEMONICS
        for suffix in _CONDITION_SUFFIXES
    )


def _reject_unmodelled_active_effects(
    code: tuple[_Insn, ...], active: frozenset[int]
) -> None:
    """Fail closed on every effect the helper can execute but the proof cannot read.

    ``_defined_register`` answers "defines nothing" both for an instruction that
    really writes no register and for one whose mnemonic it has never heard of,
    and the live-out proof cannot tell those two answers apart. So an ``ldrd``
    pair reload, a predicated ``moveq`` and an ``rrx`` recomputation each
    redefine a register invisibly, and each is refused here instead of being
    silently treated as a no-op.

    The lock is applied to the instructions the helper can actually *execute*,
    not to a slice between two indices. A slice from the success entry to the
    publication misses a redefinition parked on a branch detour that runs
    between them but is laid out after the success return, and it never looks at
    the pre-loop prologue at all -- where a ``cpsid i`` would change the very
    interrupt regime this diagnostic exists to characterize. Instructions the
    helper cannot reach are left alone: they carry no effect to constrain.
    """
    for insn in (code[index] for index in sorted(active)):
        if _is_predicated(insn.mnemonic):
            raise fail("predicated instruction on an active helper path: %s" % insn.text)
        if insn.mnemonic in _MULTI_REGISTER_TRANSFER_MNEMONICS:
            raise fail("multi-register transfer on an active helper path: %s" % insn.text)
        if insn.mnemonic in _MULTI_DESTINATION_MNEMONICS:
            raise fail("multi-destination multiply on an active helper path: %s" % insn.text)
        if insn.mnemonic not in _MODELLED_MNEMONICS:
            raise fail("unmodelled active-helper effect: %s" % insn.text)


def _back_edge_induction_register(analysis: _HelperAnalysis) -> str:
    """Register whose decrement the failed-poll back edge actually branches on.

    The back edge is the loop's only exit test, so the countdown that decides
    how many polls are left is the one whose flags that branch reads -- not
    whichever decrement happens to sit last in the loop body. Only the frozen
    shape is accepted: a ``bne`` immediately preceded by the flag-setting
    ``subs Rd, #1`` it tests. A back edge that branches on a register directly
    (``cbnz``) or on flags set somewhere else is refused rather than guessed,
    because for those the register the loop counts on is no longer recoverable
    from the decrement's position.
    """
    back_edge = analysis.code[analysis.back_edge_index]
    if back_edge.mnemonic != _BACK_EDGE_MNEMONIC:
        raise fail("back edge must branch on the decrement flags: %s" % back_edge.text)
    decrement = analysis.code[analysis.back_edge_index - 1]
    hit = _DECREMENT_RE.match(decrement.text)
    if hit is None:
        raise fail(
            "back edge must be preceded by its flag-setting decrement: %s" % decrement.text
        )
    return hit.group(1)


def _synchronized_induction_pair(
    analysis: _HelperAnalysis,
    publication_reg: str,
    back_edge_reg: str,
) -> bool:
    """Exact fixed-form proof for the fresh ARM helper's two-register countdown.

    The accepted relation is deliberately narrow: the helper must seed the two
    registers equal immediately before the loop, decrement each exactly once on
    the failed path, branch on the second register's flags, publish the first
    register, and leave neither clobbered on any path from the success entry to
    the publication. Anything broader fails closed.
    """
    if publication_reg == back_edge_reg:
        return True
    if analysis.decrement_regs != (publication_reg, back_edge_reg):
        return False
    seed = analysis.code[analysis.status_index - 1] if analysis.status_index > 0 else None
    if seed is None or seed.text != "mov\t%s, %s" % (back_edge_reg, publication_reg):
        return False
    return True


def _co_reachable(successors: tuple[tuple[int, ...], ...], target: int) -> frozenset[int]:
    """Indices from which ``target`` is reachable, walked over reversed edges."""
    predecessors: list[list[int]] = [[] for _ in successors]
    for index, edges in enumerate(successors):
        for edge in edges:
            predecessors[edge].append(index)
    return _reachable(tuple(tuple(edges) for edges in predecessors), target)


def prove_remaining_dataflow(disassembly_text: str, nm_text: str) -> RemainingDataflowProof:
    analysis = _analyze_helper(disassembly_text, nm_text)
    if analysis.variant != "v13":
        raise fail("remaining dataflow proof requires V13 helper")

    block = _success_block(analysis)
    cyccnt_store_offsets, live_in_stores = _classify_success_stores(block)
    if len(cyccnt_store_offsets) != 2:
        raise fail("success path P1/P2 cycle-count store count != 2")
    if not live_in_stores:
        raise fail("remaining store after P2 count != 1")
    remaining_offset, remaining_reg = live_in_stores[0]
    if remaining_offset < max(cyccnt_store_offsets):
        raise fail("remaining store must follow P2 exactly")

    # Reachability, walked over the helper's own branch edges. The store-shape
    # checks above only see instructions in layout order, so they cannot tell
    # that the publication is jumped over, jumped back to, duplicated at a
    # second site or reached from the timeout exit; the graph can. The active
    # set is everything the helper can execute from its entry, which is the
    # domain every check below is really about.
    successors = _build_helper_cfg(analysis.code)
    active = _reachable(successors, _HELPER_ENTRY_INDEX)

    # Everything the live-out proof is about to read must be an effect it can
    # actually model, publication included.
    _reject_unmodelled_active_effects(analysis.code, active)

    # Every effective address this module certifies was resolved in layout
    # order. Re-derive the same bindings over the helper's own edges and refuse
    # any access the two walks disagree about, so a path that reaches a store
    # without the literal load feeding its base cannot be certified against a
    # word the base never held on that path.
    _reject_layout_only_addresses(
        analysis,
        _cfg_pointer_bindings(analysis.code, successors, analysis.pc_targets, analysis.literals),
        active,
    )

    # P1, P2 and remaining must land in three different SRAM slots. Reusing the
    # P2 destination would publish a cycle count where the record expects the
    # poll countdown, which no store-shape check alone can see.
    canonical_sites = [
        analysis.success_index + offset
        for offset in sorted(cyccnt_store_offsets + [remaining_offset])
    ]
    destinations = [
        _resolved_address(
            analysis.pointer_words[index], _STORE_RE.match(analysis.code[index].text)
        )
        for index in canonical_sites
    ]
    if len(set(destinations)) != len(destinations):
        raise fail("P1/P2/remaining must target three distinct SRAM destinations")

    remaining_index = analysis.success_index + remaining_offset
    publishers = _stores_to(analysis, destinations[-1])
    # The timeout exit is the failed-poll back edge's not-taken successor.
    timeout_entry = analysis.back_edge_index + 1
    # The success entry is the completion branch's taken target.
    success_entry = analysis.success_index

    remaining_store_timeout_unreachable = not (
        publishers & _reachable(successors, timeout_entry)
    )
    if not remaining_store_timeout_unreachable:
        raise fail("remaining store must be unreachable from the timeout path")
    if (publishers - {remaining_index}) & _reachable(successors, success_entry):
        raise fail("alternate remaining store reachable on the success path")

    # Each of the three published slots may be written by its canonical site and
    # by nothing else the helper can execute. The two reachability checks above
    # are anchored at the success and timeout entries, so neither sees a store
    # in the pre-loop prologue -- which runs ahead of both and would pre-seed
    # the record, or on a timeout supply the only value the host ever reads.
    for canonical_index, address in zip(canonical_sites, destinations):
        duplicates = (_stores_to(analysis, address) & active) - {canonical_index}
        if duplicates:
            raise fail(
                "published slot 0x%08X written away from its canonical site: helper index %d"
                % (address, min(duplicates))
            )


    return_counts = _return_publication_counts(successors, success_entry, remaining_index)
    remaining_store_after_p2_exactly_once = return_counts == frozenset((1,))
    if not remaining_store_after_p2_exactly_once:
        raise fail(
            "success path must publish remaining exactly once: return counts %s"
            % sorted(return_counts)
        )

    if len(live_in_stores) != 1:
        raise fail("remaining store after P2 count != 1")

    # Those three sites are also the *only* stores the helper may execute. The
    # lock above is per published slot, so a store through a fourth referenced
    # SRAM literal -- a slot the record never names -- passes every check above:
    # it resolves to a literal the pool really carries, it is not a duplicate of
    # any published slot, and in the prologue it runs ahead of both the success
    # and the timeout entry. Whatever global sits at that address is then
    # clobbered by a helper this gate had called closed.
    stray_stores = sorted(
        index
        for index in active
        if _STORE_RE.match(analysis.code[index].text) is not None
        and index not in set(canonical_sites)
    )
    pre_loop_stray_stores = [index for index in stray_stores if index < analysis.status_index]
    other_stray_stores = [index for index in stray_stores if index >= analysis.status_index]
    if len(pre_loop_stray_stores) > 1:
        raise fail(
            "helper store outside its three published slots: helper index %d" % pre_loop_stray_stores[1]
        )
    if pre_loop_stray_stores:
        pre_loop_index = pre_loop_stray_stores[0]
        pre_loop_hit = _STORE_RE.match(analysis.code[pre_loop_index].text)
        memory_derived: set[str] = set()
        for insn in analysis.code[:pre_loop_index]:
            dest = _defined_register(insn)
            if dest is None:
                continue
            load = _LOAD_RE.match(insn.text)
            if load is not None and load.group(2) != "pc":
                memory_derived.add(dest)
            else:
                memory_derived.discard(dest)
        if pre_loop_hit.group(1) not in memory_derived:
            raise fail(
                "helper store outside its three published slots: helper index %d" % pre_loop_index
            )
        pre_loop_destination = _resolved_address(analysis.pointer_words[pre_loop_index], pre_loop_hit)
        if pre_loop_destination in set(destinations):
            raise fail(
                "helper store outside its three published slots: helper index %d" % pre_loop_index
            )
    if other_stray_stores:
        raise fail(
            "helper store outside its three published slots: helper index %d" % other_stray_stores[0]
        )

    # The published register must still hold the synchronized countdown value
    # when the store runs. "Still holds" is a statement about every path, not
    # about layout order, so the redefining instructions are looked for on the
    # instructions that actually lie between the success entry and the
    # publication: reachable from the entry and able to reach the store. A
    # reload parked on a branch the entry can take reaches the store just as
    # surely as one written in a straight line.
    #
    # For the accepted two-register form, only the publication register has to
    # stay live after the success branch. The back-edge register has already
    # done its job by proving the failed-poll countdown stays synchronized up to
    # loop exit, so repurposing it as a pointer on the success path is allowed.
    induction_reg = _back_edge_induction_register(analysis)
    on_path_to_store = (
        _reachable(successors, success_entry)
        & _co_reachable(successors, remaining_index)
    ) - {remaining_index}
    redefined_on_path = any(
        _defined_register(analysis.code[index]) == remaining_reg
        for index in on_path_to_store
    )
    synchronized_induction_pair = _synchronized_induction_pair(
        analysis,
        remaining_reg,
        induction_reg,
    )
    remaining_from_back_edge_induction = synchronized_induction_pair and not redefined_on_path
    if not remaining_from_back_edge_induction:
        raise fail("remaining must dataflow from the synchronized failed-poll countdown pair")

    helper_leaf_no_stack_access = not analysis.has_stack_access
    if not helper_leaf_no_stack_access:
        raise fail("helper must remain a leaf without stack access")
    if analysis.has_extra_non_status_load:
        raise fail("extra non-STATUS load")

    return RemainingDataflowProof(
        source="back_edge_induction",
        publication_register=remaining_reg,
        back_edge_induction_register=induction_reg,
        remaining_store_after_p2_exactly_once=remaining_store_after_p2_exactly_once,
        remaining_store_timeout_unreachable=remaining_store_timeout_unreachable,
        remaining_from_back_edge_induction=remaining_from_back_edge_induction,
        synchronized_induction_pair=synchronized_induction_pair,
        helper_leaf_no_stack_access=helper_leaf_no_stack_access,
    )


def _qual_mnemonic(ins) -> str:
    """Bare mnemonic of a ``check_pmu_qual`` instruction, suffixes removed."""
    return ins.mnemonic if ins.mnemonic.startswith(".") else ins.mnemonic.split(".")[0]


def _immediate(ins) -> int | None:
    hit = _QUAL_IMMEDIATE_RE.search(ins.operands)
    if hit is None:
        return None
    text = hit.group(1)
    return int(text, 16) if text.lower().startswith(("0x", "-0x")) else int(text, 10)


def _read_operands(ins) -> str:
    """The operand text an instruction reads its inputs from.

    A three-operand data-processing form names its destination first and its
    sources after it, so the sources are everything past the first comma. A
    *two*-operand form does not: ``adds r3, #4`` and ``movt r3, #57344`` both
    read the register they write. Dropping the destination there is how an NVIC
    pointer being walked forward -- exactly what ``for (i) NVIC->ISER[i] = ...``
    lowers to -- used to shed the taint that keeps its stores fail-closed.
    """
    operands = ins.operands.split(",")
    if len(operands) < 2:
        return ins.operands
    if len(operands) == 2 and _qual_mnemonic(ins) not in _FULL_WRITE_MNEMONICS:
        return ins.operands
    return ins.operands.partition(",")[2]


def _register_list(ins) -> tuple[str, ...]:
    """Registers a ``{...}`` transfer list names."""
    hit = _REGISTER_LIST_RE.search(ins.operands)
    return tuple(_REG_TOKEN_RE.findall(hit.group(1))) if hit else ()


def _memory_base(ins) -> str | None:
    """Base register a memory access addresses through, when it is readable."""
    hit = _MEMORY_BASE_RE.search(ins.operands)
    if hit is not None:
        return hit.group(1)
    mnemonic = _qual_mnemonic(ins)
    if mnemonic in _STACK_TRANSFER_MNEMONICS:
        return "sp"
    if mnemonic.startswith(_MULTIPLE_TRANSFER_PREFIXES):
        head = ins.operands.partition(",")[0].strip().rstrip("!")
        return head if _REG_TOKEN_RE.fullmatch(head) else None
    return None


def _writeback_base(ins) -> str | None:
    """Base register an access advances as a side effect, or None."""
    if _WRITEBACK_RE.search(ins.operands) or "!" in ins.operands:
        return _memory_base(ins)
    return None


def _writeback_advance(ins) -> int | None:
    """Bytes a writeback form adds to its base, or None when it is unreadable.

    An indexed form carries the advance as the only immediate in its operands,
    which is the same immediate for the pre- and the post-index spelling. A
    register-list form advances by four bytes per transferred register instead,
    and the sign of that advance depends on the direction the list runs -- which
    ``_advance_reaches_nvic_block`` treats symmetrically rather than decoding.
    """
    mnemonic = _qual_mnemonic(ins)
    if mnemonic in _STACK_TRANSFER_MNEMONICS or mnemonic.startswith(_MULTIPLE_TRANSFER_PREFIXES):
        count = len(_register_list(ins))
        return 4 * count if count else None
    return _immediate(ins)


def _advance_reaches_nvic_block(word: int, step: int | None) -> bool:
    """True when advancing a base proven at ``word`` can leave it in the block.

    Taint is otherwise seeded only by a value proven *inside* ``NVIC_Type``, so
    a base proven just below the block and then advanced into it was invisible
    to both halves of the analysis: the advance drops the proven value, and
    there was never any taint to keep. A readable advance is checked exactly; an
    unreadable one falls back to the block's own span, so a base further away
    than the whole register file is not treated as walking it.
    """
    if step is None:
        return (
            _NVIC_BLOCK_FIRST - _NVIC_WRITEBACK_REACH
            <= word
            <= _NVIC_BLOCK_LAST + _NVIC_WRITEBACK_REACH
        )
    return any(
        _NVIC_BLOCK_FIRST <= word + direction * step <= _NVIC_BLOCK_LAST
        for direction in (1, -1)
    )


def _bind_pointer(values: dict[str, int], tainted: set[str], reg: str | None, word: int | None) -> None:
    if reg is None:
        return
    if word is None:
        values.pop(reg, None)
        tainted.discard(reg)
        return
    values[reg] = word
    if _NVIC_BLOCK_FIRST <= word <= _NVIC_BLOCK_LAST:
        tainted.add(reg)
    else:
        tainted.discard(reg)


def _bind_movt(values: dict[str, int], tainted: set[str], reg: str, imm: int | None) -> None:
    """``movt`` replaces the top halfword and keeps the bottom one.

    Materialising a pointer as ``movw``/``movt`` carries no literal-pool entry
    at all, so a gate that only reads literal loads sees neither the value nor
    anything to taint -- and a toolchain that materialises addresses this way
    (``-mslow-flash-data``, for one) would make the ISER proof vacuous across
    the whole image, silently. A ``movt`` of the NVIC block's own high halfword
    over an unproven low half is treated as a pointer into the block, because
    it may be one.
    """
    low = values.get(reg)
    if imm is not None and low is not None:
        _bind_pointer(values, tainted, reg, (low & 0xFFFF) | ((imm & 0xFFFF) << 16))
        return
    values.pop(reg, None)
    if imm is not None and (imm & 0xFFFF) == _NVIC_BLOCK_HIGH_HALFWORD:
        tainted.add(reg)
    else:
        tainted.discard(reg)


def _nvic_pointer_state(
    fn, pool: dict[int, int]
) -> tuple[tuple[dict[str, int], frozenset[str]], ...]:
    """Per-instruction proven register values and NVIC-tainted registers.

    The value half resolves the three ways a Thumb-2 build materialises a
    peripheral pointer -- a literal-pool load, a move-immediate and a
    ``movw``/``movt`` pair -- and drops a register the moment anything else
    writes it, a transfer list pops it, a call clobbers it or a writeback form
    advances it by an amount this gate does not model.

    The taint half is the fail-closed companion: a register enters it by
    holding a word inside ``NVIC_Type``, or by being advanced into it by a
    writeback form, and stays in it while its value is derived from one, even
    once that value stops being provable. The writeback case is the one that
    would otherwise fall between the two halves -- the advance drops the proven
    value, and a base proven just *outside* the block was never tainted to
    begin with -- so the store that follows it would be judged with nothing to
    go on. That is what makes the caller's fail-closed branch reachable instead
    of vacuous.
    """
    states: list[tuple[dict[str, int], frozenset[str]]] = []
    values: dict[str, int] = {}
    tainted: set[str] = set()
    for ins in fn.insns:
        states.append((dict(values), frozenset(tainted)))
        mnemonic = _qual_mnemonic(ins)
        if ins.kind == "call":
            for reg in qual_elf.CALL_CLOBBERED:
                values.pop(reg, None)
            tainted -= set(qual_elf.CALL_CLOBBERED)
            continue
        if mnemonic in _STACK_TRANSFER_MNEMONICS or mnemonic.startswith(_MULTIPLE_TRANSFER_PREFIXES):
            # A transfer list defines registers the classifier never reports as
            # a destination, so a stale proven value would survive the load.
            for reg in _register_list(ins):
                if mnemonic.startswith(_LOAD_MULTIPLE_PREFIXES):
                    values.pop(reg, None)
                    tainted.discard(reg)
        if ins.kind == "ldr_lit":
            _bind_pointer(values, tainted, ins.dest, pool.get(ins.literal_addr))
        elif mnemonic == "movt" and ins.dest is not None:
            _bind_movt(values, tainted, ins.dest, _immediate(ins))
        elif ins.kind == "mov_imm":
            _bind_pointer(values, tainted, ins.dest, ins.value)
        elif ins.dest is not None:
            # Every other writer is opaque, so it is read pessimistically: it
            # carries the taint of whatever registers it reads.
            values.pop(ins.dest, None)
            if set(_REG_TOKEN_RE.findall(_read_operands(ins))) & tainted:
                tainted.add(ins.dest)
            else:
                tainted.discard(ins.dest)
        advanced = _writeback_base(ins)
        if advanced is not None:
            word = values.pop(advanced, None)
            if word is not None and _advance_reaches_nvic_block(word, _writeback_advance(ins)):
                tainted.add(advanced)
    return tuple(states)


def _check_retained_v12_runtime(disassembly_text: str) -> None:
    """Refuse a re-introduced NVIC enable in the V13 image.

    ``NVIC_SetVector`` and ``NVIC_ClearPendingIRQ`` call sites are required by
    the retained V12 runtime contract, so their mere existence is not drift and
    is not checked here; the whole-image gate proves their operands and order.
    What must never come back is an interrupt *enable*, in either form: a call
    to ``NVIC_EnableIRQ`` or a direct write to NVIC->ISER.

    The ISER half is a statement about *destinations*, not about text. The word
    ``0xE000E100`` is ISER[0] and CMSIS ``NVIC_BASE`` at once, so it appears in
    the literal pool of every build that clears ICER or ICPR through that base
    -- which the retained V12 hard bypass is required to do. Only a store that
    lands inside ISER is drift.

    Every instruction whose mnemonic matches ``_STORE_FAMILY_PREFIXES`` or the
    stack transfers is examined, not only the ones ``check_pmu_qual`` decodes as
    single stores: a ``stmia``/``stmdb`` through an NVIC-block base reaches ISER
    from either side of the base and is refused outright, because no single
    destination can be resolved for a register list at all, and one whose base
    is proven *outside* the block is refused when the list's own span reaches
    into ISER from it. That prefix list is an allow-list of names, so a store
    mnemonic outside it is skipped rather than judged -- the limit the module
    docstring states. What *grants* acceptance is
    ``_nvic_pointer_state``'s own resolution, never ``qual_elf.store_address``:
    the latter reads a base's defining literal load straight through a writeback
    form that has since advanced it, so its answer can only ever raise the
    verdict to drift, not settle it. A destination that stays unproven is drift
    whenever its base could be an NVIC-block pointer, so an enable cannot hide
    behind a base the resolver gives up on.
    """
    for callee in _V12_RUNTIME_DRIFT_CALLEES:
        if re.search(_CALL_TO_RE % re.escape(callee), disassembly_text):
            raise fail("retained V12 NVIC enable drift: %s call site" % callee)
    dis = qual_elf.parse_disassembly(disassembly_text)
    pool = qual_elf.literal_pool(dis.functions)
    for name, fn in dis.functions.items():
        states = _nvic_pointer_state(fn, pool)
        for index, ins in enumerate(fn.insns):
            mnemonic = _qual_mnemonic(ins)
            if not (
                mnemonic.startswith(_STORE_FAMILY_PREFIXES)
                or mnemonic in _STACK_TRANSFER_MNEMONICS
            ):
                continue
            values, tainted = states[index]
            base = _memory_base(ins)
            where = "%s+0x%X" % (name, ins.addr - fn.addr)
            if mnemonic.startswith("stm") or mnemonic in _STACK_TRANSFER_MNEMONICS:
                if mnemonic in _LOAD_MULTIPLE_PREFIXES:
                    continue
                if base is None or base in tainted:
                    raise fail(
                        "NVIC-block multiple store destination unresolvable at %s" % where
                    )
                # A base proven *outside* the block carries no taint, but a
                # register list reaches four bytes per register away from it --
                # so a base one word below ISER[0] writes ISER[0] with its
                # second register. That is the same reasoning `strd` already
                # carries, applied to a list whose length the operands name.
                # The direction the list runs is not decoded: both are refused,
                # which costs a build nothing the contract allows.
                reach = 4 * max(1, len(_register_list(ins)))
                proven_base = values.get(base)
                if proven_base is None:
                    continue
                for address in range(proven_base - reach, proven_base + reach, 4):
                    if _NVIC_ISER_FIRST <= address <= _NVIC_ISER_LAST:
                        raise fail(
                            "NVIC ISER bank within store-multiple reach at %s -> 0x%08X"
                            % (where, address)
                        )
                continue
            proven = (
                values.get(ins.base) if ins.kind == "store" and ins.base is not None else None
            )
            reported = qual_elf.store_address(fn, index, pool) if ins.kind == "store" else None
            # A `strd` writes two consecutive words, so a destination four bytes
            # below ISER[0] still lands one word inside the bank.
            span = 2 if mnemonic == "strd" else 1
            for first in (None if proven is None else proven + ins.offset, reported):
                if first is None:
                    continue
                for address in range(first, first + 4 * span, 4):
                    if _NVIC_ISER_FIRST <= address <= _NVIC_ISER_LAST:
                        raise fail(
                            "direct NVIC ISER enable write remains reachable: %s -> 0x%08X"
                            % (where, address)
                        )
            if proven is not None:
                continue
            # An unproven destination. A form the classifier could not decode at
            # all -- register-offset, shifted-register, a vector store -- hides
            # which of its operands is the base, so it is judged on every
            # register it names rather than on a base that may not be one.
            candidates = (
                {ins.base}
                if ins.kind == "store" and ins.base is not None
                else set(_REG_TOKEN_RE.findall(ins.operands))
            )
            if candidates & tainted:
                raise fail("NVIC-block store destination unresolvable at %s" % where)


def verify_cross_elf_contract(
    v12_disassembly_text: str,
    v12_nm_text: str,
    v13_disassembly_text: str,
    v13_nm_text: str,
) -> dict[str, object]:
    """Cross-ELF gate over the per-iteration poll loop region only.

    ``v12_v13_poll_loop_semantically_equivalent`` means exactly one thing: the
    V12 and V13 helpers sign the same ``_region_signature`` over the region
    that runs once per poll iteration -- STATUS load, completion test, success
    branch, failed-path decrements and back edge -- with register names,
    addresses and literal-pool layout normalized away. ``EQUIVALENCE_SCOPE``
    carries that region name into the manifest so a reader cannot take the
    boolean for whole-helper or whole-image equivalence: a V13 build whose
    prologue, success tail or epilogue differs from V12's still signs the same
    region and is accepted here, by design.

    The post-P2 publication is *not* part of that comparison -- V12 has no such
    store, so there is nothing to compare it against. It is proven separately by
    ``prove_remaining_dataflow``, over the V13 image alone.
    """
    v12_loop = extract_poll_loop(v12_disassembly_text, v12_nm_text)
    v13_loop = extract_poll_loop(v13_disassembly_text, v13_nm_text)
    if v12_loop.variant != "v12" or v13_loop.variant != "v13":
        raise fail("cross-ELF gate requires one V12 and one V13 helper")
    poll_loop_region_equivalent = normalize_poll_loop(v12_loop) == normalize_poll_loop(v13_loop)
    if not poll_loop_region_equivalent:
        raise fail("V12/V13 normalized poll loop mismatch")
    extra_per_iteration_instruction_count_zero = (
        v13_loop.extra_per_iteration_instruction_count == 0
        and not v13_loop.has_forbidden_loop_effect
    )
    if not extra_per_iteration_instruction_count_zero:
        raise fail("extra per-iteration instruction")
    proof = prove_remaining_dataflow(v13_disassembly_text, v13_nm_text)
    return {
        "variant": VARIANT,
        "v12_v13_poll_loop_semantically_equivalent": poll_loop_region_equivalent,
        "v12_v13_poll_loop_equivalence_scope": EQUIVALENCE_SCOPE,
        "v13_extra_per_iteration_instruction_count_zero": extra_per_iteration_instruction_count_zero,
        "remaining_store_after_p2_exactly_once": proof.remaining_store_after_p2_exactly_once,
        "remaining_from_back_edge_induction": proof.remaining_from_back_edge_induction,
        "synchronized_induction_pair": proof.synchronized_induction_pair,
        "remaining_store_timeout_unreachable": proof.remaining_store_timeout_unreachable,
        "helper_leaf_no_stack_access": proof.helper_leaf_no_stack_access,
        "remaining_publication_register": proof.publication_register,
        "remaining_back_edge_induction_register": proof.back_edge_induction_register,
    }


def verify_retained_v12_executable_contract(
    runner_text: str,
    vendor_text: str,
    disassembly_text: str,
    nm_text: str,
) -> dict[str, object]:
    """Replay the fixed V12 real-trace subset against the linked V13 image.

    The shared verifier supplies the instruction-, symbol-, address-, and
    dataflow-derived evidence. This wrapper binds that evidence to the exact
    V13 generated inputs and adds only booleans whose underlying checks have
    already succeeded. Runtime golden output and the complete base PMU gate are
    deliberately outside this subset and remain explicitly unqualified.
    """
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    if _sha256_text(runner_text) != RUNNER_GENERATED_SHA256:
        raise fail("retained V12 executable runner hash mismatch")
    if _sha256_text(vendor_text) != VENDOR_GENERATED_SHA256:
        raise fail("retained V12 executable vendor hash mismatch")
    evidence = verify_callsite_trace_real(
        runner_text,
        vendor_text,
        _normalize_newlines(disassembly_text),
        _normalize_newlines(nm_text),
        contract=V13_REAL_TRACE_CONTRACT,
    )
    for key, expected in V13_RETAINED_V12_EXPECTED_ADDRESSES.items():
        if evidence.get(key) != expected:
            raise fail(
                "retained V12 executable address drift: %s expected %s, got %s"
                % (key, expected, evidence.get(key))
            )

    def address(key: str) -> int:
        value = evidence.get(key)
        if not isinstance(value, str) or re.fullmatch(r"0x[0-9A-Fa-f]{8}", value) is None:
            raise fail("retained V12 executable address missing: %s" % key)
        return int(value, 16)

    stock_vector_exact = evidence.get("runtime_vector_target_exact") is True
    nvic_hard_bypass_exact = (
        evidence.get("nvic_enable_replaced") is True
        and evidence.get("irq_triggered_true_reachable_false") is True
        and address("runtime_disable_site_address") < address("runtime_clear_pending_site_address")
    )
    status_history_exact = (
        evidence.get("status_success_dataflow_exact") is True
        and evidence.get("history_mask_from_success_status") is True
    )
    cmd_qread_exact = (
        evidence.get("success_cmd2_count_2") is True
        and evidence.get("timeout_cmd2_count_1") is True
        and address("timeout_qread_load_address") < address("timeout_cmd2_store_address")
        and address("success_cmd2_1_store_address")
        < address("success_qread_load_address")
        < address("success_cmd2_2_store_address")
    )
    p0_p1_p2_exact = (
        address("poll_helper_p0_address")
        < address("helper_status_read_address")
        < address("helper_status_test_address")
        < address("poll_helper_p1_address")
        < address("poll_helper_p2_address")
    )
    hprintf_exact = (
        address("cmd0_store_address")
        < address("hprintf_callsite_address")
        < address("terminal_cmd0c_store_address")
    )
    terminal_release_exact = (
        evidence.get("success_cmd2_write_value") == "0x00000002"
        and address("terminal_cmd0c_store_address") > address("hprintf_callsite_address")
    )
    evidence.update(
        {
            "retained_v12_executable_proof_scope": RETAINED_V12_EXECUTABLE_PROOF_SCOPE,
            "retained_v12_executable_limitations": RETAINED_V12_EXECUTABLE_LIMITATIONS,
            "retained_v12_stock_vector_exact": stock_vector_exact,
            "retained_v12_nvic_hard_bypass_exact": nvic_hard_bypass_exact,
            "retained_v12_status_history_provenance_exact": status_history_exact,
            "retained_v12_cmd_qread_ordering_exact": cmd_qread_exact,
            "retained_v12_p0_p1_p2_exact": p0_p1_p2_exact,
            "retained_v12_hprintf_seam_exact": hprintf_exact,
            "retained_v12_terminal_release_exact": terminal_release_exact,
            "runtime_golden_output_qualified": False,
            "full_base_pmu_qualified": False,
        }
    )
    for key in RETAINED_V12_EXECUTABLE_BOOLEAN_KEYS:
        if evidence.get(key) is not True:
            raise fail("retained V12 executable proof missing or false: %s" % key)
    return evidence


RUNNER_RECORD_WIRE_PROOF_SCOPE = "linked_image_dwarf_exact_locations"
RUNNER_RECORD_WIRE_SCOPE_NOTE = (
    "Fails closed unless DWARF yields exact singleton locations for the inlined "
    "handle_run_pmu_diag local record and response buffer plus the concrete "
    "build_pmu_diag_payload last_pmu_diag alias. This scope does not claim a "
    "general helper proof outside the observed linked-image forms."
)
RUNNER_RECORD_WIRE_DWARF_REQUIRED_NOTE = (
    "DWARF readelf --debug-dump=info,loc evidence is mandatory; missing, "
    "multi-range, non-singleton, register-only, or unresolved locations fail."
)
_HEX_LOC_RE = re.compile(r"0x([0-9A-Fa-f]+)")
_DIS_LINE_RE = re.compile(r"^\s*([0-9A-Fa-f]+):\s+(.*)$")


def _json_bytes(doc: dict[str, object]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def _extract_named_block(dwarf_text: str, name: str) -> str:
    match = re.search(
        r"(?ms)^\s*<\d+><(?:0x)?([0-9a-f]+)>:.*?DW_AT_name\s*:\s*(?:\([^)]*\):\s*)?%s\s*$"
        % re.escape(name),
        dwarf_text,
    )
    if match is None:
        raise fail("DWARF block missing: %s" % name)
    start = match.start()
    next_match = re.search(r"(?m)^\s*<\d+><(?:0x)?[0-9a-f]+>:", dwarf_text[match.end():])
    end = len(dwarf_text) if next_match is None else match.end() + next_match.start()
    return dwarf_text[start:end]


def _extract_level1_named_block(dwarf_text: str, name: str) -> tuple[str, str]:
    lines = dwarf_text.splitlines()
    level1_re = re.compile(r"^\s*<1><(?:0x)?([0-9a-f]+)>:")
    for index, line in enumerate(lines):
        if "DW_AT_name" not in line or not line.rstrip().endswith(name):
            continue
        start = None
        block_id = None
        for back in range(index, -1, -1):
            hit = level1_re.match(lines[back])
            if hit is not None:
                start = back
                block_id = hit.group(1)
                break
        if start is None:
            continue
        end = len(lines)
        for forward in range(start + 1, len(lines)):
            if level1_re.match(lines[forward]) is not None:
                end = forward
                break
        return block_id, "\n".join(lines[start:end])
    raise fail("DWARF level-1 block missing: %s" % name)


def _extract_member_offset(dwarf_text: str, struct_name: str, member_name: str) -> int:
    struct_hits = [
        hit.start()
        for hit in re.finditer(
            r"DW_AT_name\s*:\s*(?:\([^)]*\):\s*)?%s\s*$" % re.escape(struct_name),
            dwarf_text,
            re.M,
        )
    ]
    member_hits = list(
        re.finditer(
            r"DW_AT_name\s*:\s*(?:\([^)]*\):\s*)?%s\s*$" % re.escape(member_name),
            dwarf_text,
            re.M,
        )
    )
    for member_hit in member_hits:
        window_start = max(0, member_hit.start() - 256)
        window_end = min(len(dwarf_text), member_hit.end() + 2048)
        window = dwarf_text[window_start:window_end]
        if "DW_TAG_member" not in window:
            continue
        offset_match = re.search(
            r"DW_AT_data_member_location:\s*(\d+)",
            dwarf_text[member_hit.end():window_end],
        )
        if offset_match is None:
            continue
        absolute_member = member_hit.start()
        if any(abs(struct_pos - absolute_member) <= 4096 for struct_pos in struct_hits):
            return int(offset_match.group(1))
    raise fail("DWARF member offset missing for %s.%s" % (struct_name, member_name))


def _extract_producer(dwarf_text: str) -> str:
    match = re.search(r"DW_AT_producer\s*:\s*(?:\([^)]*\):\s*)?(.+)$", dwarf_text, re.M)
    if match is None:
        raise fail("DWARF producer missing")
    return match.group(1).strip()


def _parse_disassembly_lines(section_text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in section_text.splitlines():
        match = _DIS_LINE_RE.match(raw)
        if match is None:
            continue
        lines.append((int(match.group(1), 16), match.group(2).strip()))
    return lines


def _parse_nm_symbols(nm_text: str) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for raw in nm_text.splitlines():
        parts = raw.split()
        if len(parts) == 3 and re.fullmatch(r"[0-9A-Fa-f]+", parts[0]):
            symbols[parts[2]] = int(parts[0], 16)
    return symbols


def _find_line_index(lines: list[tuple[int, str]], addr: int, pattern: str, what: str) -> int:
    for index, (line_addr, body) in enumerate(lines):
        if line_addr == addr and pattern in body:
            return index
    raise fail("%s missing at 0x%08X" % (what, addr))


def _ensure_next(lines: list[tuple[int, str]], index: int, pattern: str, what: str) -> None:
    if index + 1 >= len(lines) or pattern not in lines[index + 1][1]:
        raise fail("%s ordering violated" % what)


def _parse_synthetic_location(dwarf_text: str, function_name: str, variable_name: str) -> tuple[int, int, int]:
    match = re.search(
        r"(?ms)DW_AT_name\s*:\s*(?:\([^)]*\):\s*)?%s\s*$.*?"
        r"DW_AT_name\s*:\s*(?:\([^)]*\):\s*)?%s\s*$.*?"
        r"DW_AT_location\s*:\s*\[0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+)\):\s*DW_OP_fbreg\s+(-?\d+)"
        % (re.escape(function_name), re.escape(variable_name)),
        dwarf_text,
    )
    if match is None:
        raise fail("DWARF singleton location missing for %s.%s" % (function_name, variable_name))
    return (int(match.group(1), 16), int(match.group(2), 16), int(match.group(3)))


def _parse_real_inlined_location(
    dwarf_text: str,
    abstract_name: str,
    variable_name: str,
) -> int:
    abstract_id, abstract_block = _extract_level1_named_block(dwarf_text, abstract_name)
    block_lines = abstract_block.splitlines()
    die_re = re.compile(r"^\s*<(\d+)><(?:0x)?([0-9a-f]+)>:")
    variable_id = None
    for index, line in enumerate(block_lines):
        if "DW_AT_name" not in line or not line.rstrip().endswith(variable_name):
            continue
        for back in range(index, -1, -1):
            hit = die_re.match(block_lines[back])
            if hit is not None:
                variable_id = hit.group(2)
                break
        if variable_id is not None:
            break
    if variable_id is None:
        raise fail("DWARF abstract variable missing: %s.%s" % (abstract_name, variable_name))
    lines = dwarf_text.splitlines()
    level2_re = re.compile(r"^\s*<2><(?:0x)?([0-9a-f]+)>:")
    level3_re = re.compile(r"^\s*<3><(?:0x)?([0-9a-f]+)>:")
    for index, line in enumerate(lines):
        if "DW_TAG_inlined_subroutine" not in line:
            continue
        if index + 1 >= len(lines) or ("DW_AT_abstract_origin: <0x%s>" % abstract_id) not in lines[index + 1] and ("DW_AT_abstract_origin: <%s>" % abstract_id) not in lines[index + 1]:
            continue
        end = len(lines)
        for forward in range(index + 1, len(lines)):
            if forward > index and level2_re.match(lines[forward]) is not None:
                end = forward
                break
        current_level3 = None
        current_origin = None
        for subline in lines[index:end]:
            hit3 = level3_re.match(subline)
            if hit3 is not None:
                current_level3 = hit3.group(1)
                current_origin = None
                continue
            if "DW_AT_abstract_origin" in subline and current_level3 is not None:
                origin_match = re.search(r"<0x?([0-9a-f]+)>", subline)
                if origin_match is not None:
                    current_origin = origin_match.group(1)
                continue
            if current_origin == variable_id and "DW_AT_location" in subline:
                fbreg_match = re.search(r"DW_OP_fbreg:\s*(-?\d+)\)", subline)
                if fbreg_match is not None:
                    return int(fbreg_match.group(1))
        break
    if variable_id is None:
        raise fail("DWARF inlined subroutine missing for %s" % abstract_name)
    raise fail("DWARF inlined singleton fbreg missing for %s.%s" % (abstract_name, variable_name))


def _extract_real_build_payload_alias(dwarf_text: str) -> int:
    _, block = _extract_level1_named_block(dwarf_text, "build_pmu_diag_payload")
    lines = block.splitlines()
    seen_d = False
    for line in lines:
        if "DW_AT_name" in line and line.rstrip().endswith("d"):
            seen_d = True
            continue
        if seen_d and "DW_AT_location" in line and "DW_OP_addr:" in line and "DW_OP_stack_value" in line:
            addr_match = re.search(r"DW_OP_addr:\s*([0-9A-Fa-f]+)", line)
            if addr_match is not None:
                return int(addr_match.group(1), 16)
    raise fail("DWARF build_pmu_diag_payload last_pmu_diag alias missing")


def _assert_single_named_occurrence(text: str, needle: str, what: str) -> None:
    if text.count(needle) != 1:
        raise fail("%s count != 1" % what)


def _verify_runner_record_wire_synthetic(
    runner_text: str,
    objdump_text: str,
    nm_text: str,
    dwarf_text: str,
) -> dict[str, object]:
    field_offset = _extract_member_offset(dwarf_text, "pmu_diag_record_t", "poll_remaining_at_success")
    if field_offset != 20:
        raise fail("synthetic fixture field offset drift")
    collect_d = _parse_synthetic_location(dwarf_text, "collect_record", "d")
    emit_resp = _parse_synthetic_location(dwarf_text, "emit_wire", "resp")
    if collect_d[2] != 0:
        raise fail("synthetic local d location must be singleton fbreg 0")
    if emit_resp[2] != 0:
        raise fail("synthetic resp location must be singleton fbreg 0")
    symbols = _parse_nm_symbols(nm_text)
    last_addr = symbols.get("last_pmu_diag")
    if last_addr is None:
        raise fail("missing symbol in nm: last_pmu_diag")
    collect_text = _function_section(objdump_text, "collect_record")
    emit_text = _function_section(objdump_text, "emit_wire")
    if "strd" in collect_text and "[sp, #20]" in collect_text:
        raise fail("unsupported write form reaches local d")
    d_store_count = collect_text.count("[sp, #20]")
    if d_store_count != 1:
        raise fail("overlapping write to local d.poll_remaining_at_success")
    if "stm" in collect_text and "r4" in collect_text:
        raise fail("store-multiple overlaps last_pmu_diag.poll_remaining_at_success")
    if collect_text.count("[r4, #20]") != 1:
        raise fail("overlapping write to last_pmu_diag.poll_remaining_at_success")
    if "<clobber_record>" in collect_text:
        raise fail("pointer escape or unresolved callee write reaches local d")
    if emit_text.count("[sp, #400]") != 1:
        raise fail("overlapping write to wire poll_remaining_at_success slot")
    if "last_pmu_diag = d;" in runner_text:
        _assert_single_named_occurrence(runner_text, "last_pmu_diag = d;", "runner last_pmu_diag assignment")
    if "resp[100] = d->poll_remaining_at_success;" in runner_text:
        _assert_single_named_occurrence(
            runner_text,
            "resp[100] = d->poll_remaining_at_success;",
            "runner wire publish",
        )
    return {
        "variant": VARIANT,
        "runner_record_wire_proof_scope": RUNNER_RECORD_WIRE_PROOF_SCOPE,
        "runner_record_wire_scope_statement": RUNNER_RECORD_WIRE_SCOPE_NOTE,
        "runner_record_wire_limitations": RUNNER_RECORD_WIRE_DWARF_REQUIRED_NOTE,
        "dwarf_required": True,
        "evidence_source": "synthetic_fixture",
        "poll_remaining_field_offset_bytes": field_offset,
        "wire_word_index": 100,
        "local_d_location": "fbreg+0",
        "resp_location": "fbreg+0",
        "last_pmu_diag_address": "0x%08X" % last_addr,
    }


def _verify_runner_record_wire_real(
    runner_text: str,
    objdump_text: str,
    nm_text: str,
    dwarf_text: str,
) -> dict[str, object]:
    producer = _extract_producer(dwarf_text)
    field_offset = _extract_member_offset(dwarf_text, "pmu_diag_record_t", "poll_remaining_at_success")
    if field_offset != 400:
        raise fail("DWARF member offset drift for poll_remaining_at_success")
    local_d_fbreg = _parse_real_inlined_location(dwarf_text, "handle_run_pmu_diag", "d")
    resp_fbreg = _parse_real_inlined_location(dwarf_text, "handle_run_pmu_diag", "resp")
    if local_d_fbreg != -1056:
        raise fail("DWARF exact local d location unavailable")
    if resp_fbreg != -652:
        raise fail("DWARF exact resp location unavailable")
    symbols = _parse_nm_symbols(nm_text)
    last_addr = symbols.get("last_pmu_diag")
    if last_addr is None:
        raise fail("missing symbol in nm: last_pmu_diag")
    if _extract_real_build_payload_alias(dwarf_text) != last_addr:
        raise fail("DWARF build_pmu_diag_payload alias mismatch")
    build_lines = _parse_disassembly_lines(_function_section(objdump_text, "build_pmu_diag_payload"))
    dispatch_lines = _parse_disassembly_lines(_function_section(objdump_text, "dispatch"))
    load_index = _find_line_index(
        build_lines,
        0x31000DEA,
        "[r5, #400]",
        "build_pmu_diag_payload poll_remaining load",
    )
    _ensure_next(build_lines, load_index, "mov\tr0, sp", "build_pmu_diag_payload put32 source")
    _ensure_next(build_lines, load_index + 1, "<put32>", "build_pmu_diag_payload put32 call")
    memcpy_index = _find_line_index(dispatch_lines, 0x31001F82, "<memcpy>", "dispatch memcpy call")
    window = "\n".join(body for _, body in dispatch_lines[max(0, memcpy_index - 10):memcpy_index + 1])
    if "mov.w\tr2, #404" not in window:
        raise fail("dispatch memcpy span is not exact record size")
    if "sp, #48" not in window:
        raise fail("dispatch local d source does not match DWARF fbreg")
    dispatch_text = _function_section(objdump_text, "dispatch")
    if ("31002048" not in dispatch_text) or (("%08x" % last_addr).lower() not in dispatch_text.lower()):
        raise fail("dispatch memcpy destination is not last_pmu_diag")
    payload_index = _find_line_index(dispatch_lines, 0x31001FA0, "<build_pmu_diag_payload>", "dispatch payload builder call")
    payload_window = "\n".join(body for _, body in dispatch_lines[max(0, payload_index - 2):payload_index + 1])
    if "add\tr4, sp, #452" not in payload_window and "add.w\tr4, sp, #452" not in payload_window:
        raise fail("dispatch resp pointer does not match DWARF fbreg")
    frame_index = _find_line_index(dispatch_lines, 0x31001FB2, "<send_frame>", "dispatch send_frame call")
    frame_window = "\n".join(body for _, body in dispatch_lines[max(0, frame_index - 4):frame_index + 1])
    if "mov\tr3, r4" not in frame_window:
        raise fail("dispatch send_frame payload is not exact resp buffer")
    _assert_single_named_occurrence(
        runner_text,
        "d.poll_remaining_at_success       = pmu_completion_poll_v13_t_poll_remaining_at_success;",
        "runner local d poll_remaining assignment",
    )
    _assert_single_named_occurrence(
        runner_text,
        "d.poll_remaining_at_success = 0U;",
        "runner timeout invalidation",
    )
    _assert_single_named_occurrence(
        runner_text,
        "put32(&c, d->poll_remaining_at_success);",
        "runner wire poll_remaining serialization",
    )
    return {
        "variant": VARIANT,
        "runner_record_wire_proof_scope": RUNNER_RECORD_WIRE_PROOF_SCOPE,
        "runner_record_wire_scope_statement": RUNNER_RECORD_WIRE_SCOPE_NOTE,
        "runner_record_wire_limitations": RUNNER_RECORD_WIRE_DWARF_REQUIRED_NOTE,
        "dwarf_required": True,
        "evidence_source": "arm_elf",
        "dwarf_producer": producer,
        "poll_remaining_field_offset_bytes": field_offset,
        "wire_word_index": 100,
        "handle_run_pmu_diag_local_d_fbreg": local_d_fbreg,
        "handle_run_pmu_diag_resp_fbreg": resp_fbreg,
        "dispatch_local_d_copy_source_offset_bytes": 48,
        "dispatch_resp_offset_bytes": 452,
        "last_pmu_diag_address": "0x%08X" % last_addr,
        "build_pmu_diag_payload_address": "0x31000B0C",
        "dispatch_address": "0x31001010",
        "memcpy_size_bytes": 404,
    }


def verify_runner_record_wire_contract(
    runner_text: str,
    objdump_text: str,
    nm_text: str,
    dwarf_text: str,
) -> dict[str, object]:
    runner_text = _normalize_newlines(runner_text)
    objdump_text = _normalize_newlines(objdump_text)
    nm_text = _normalize_newlines(nm_text)
    dwarf_text = _normalize_newlines(dwarf_text)
    if (
        "build_pmu_diag_payload" in objdump_text
        and "<dispatch>" in objdump_text
        and "handle_run_pmu_diag" in dwarf_text
        and "build_pmu_diag_payload" in dwarf_text
    ):
        return _verify_runner_record_wire_real(runner_text, objdump_text, nm_text, dwarf_text)
    if _sha256_text(runner_text) == RUNNER_GENERATED_SHA256:
        raise fail("canonical generated runner requires arm_elf runner-record/wire evidence")
    return _verify_runner_record_wire_synthetic(runner_text, objdump_text, nm_text, dwarf_text)


def _load_json(path: str) -> dict[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_path(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _artifact_bundle_sha256(artifact_hashes: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(artifact_hashes, sort_keys=True).encode("utf-8")).hexdigest()


def _parser_sha256() -> str:
    return _sha256_path(__file__)


ARTIFACT_HASH_KEYS = (
    "authoritative_v12_elf",
    "elf",
    "map",
    "app_bin",
    "vectors_bin",
    "ddr_bin",
    "runner_generated",
    "vendor_generated",
    "authoritative_v12_objdump",
    "authoritative_v12_nm",
    "v13_objdump",
    "v13_nm",
    "v13_dwarf",
    "cross_elf_evidence",
    "runner_record_wire_evidence",
    "retained_v12_executable_evidence",
)
BUILD_EVIDENCE_HASH_KEYS = (
    "authoritative_v12_elf",
    "authoritative_v12_objdump",
    "authoritative_v12_nm",
    "v13_objdump",
    "v13_nm",
    "v13_dwarf",
    "cross_elf_evidence",
    "runner_record_wire_evidence",
    "retained_v12_executable_evidence",
)


def _write_manifest_atomic(path: str, doc: dict[str, object]) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    payload = _json_bytes(doc)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, delete=False) as handle:
        handle.write(payload)
        tmp_path = handle.name
    os.replace(tmp_path, path)


def validate_artifact_contract(
    manifest_json: str,
    cross_elf_evidence: dict[str, object] | None = None,
    runner_record_wire_evidence: dict[str, object] | None = None,
    artifact_hashes: dict[str, str] | None = None,
    build_evidence_hashes: dict[str, str] | None = None,
    retained_v12_executable_evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    doc = json.loads(manifest_json)
    exact = {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "runner_source_sha256": RUNNER_GENERATED_SHA256,
        "vendor_source_sha256": VENDOR_GENERATED_SHA256,
        "authoritative_v12_elf_sha256": AUTHORITATIVE_V12_SHA256,
    }
    for key, expected in exact.items():
        if doc.get(key) != expected:
            raise fail("manifest %s mismatch" % key)
    if doc.get("cross_elf_evidence_proof_scope") != EQUIVALENCE_SCOPE:
        raise fail("manifest cross-ELF scope mismatch")
    if doc.get("runner_record_wire_proof_scope") != RUNNER_RECORD_WIRE_PROOF_SCOPE:
        raise fail("manifest runner-record/wire scope mismatch")
    if doc.get("retained_v12_executable_proof_scope") != RETAINED_V12_EXECUTABLE_PROOF_SCOPE:
        raise fail("manifest retained V12 executable scope mismatch")
    retained_doc = doc.get("retained_v12_executable_evidence")
    if not isinstance(retained_doc, dict):
        raise fail("manifest retained V12 executable evidence malformed")
    if retained_doc.get("retained_v12_executable_proof_scope") != RETAINED_V12_EXECUTABLE_PROOF_SCOPE:
        raise fail("manifest retained V12 executable evidence scope mismatch")
    for key in RETAINED_V12_EXECUTABLE_BOOLEAN_KEYS:
        if retained_doc.get(key) is not True:
            raise fail("manifest retained V12 executable boolean missing or false: %s" % key)
    if retained_doc.get("runtime_golden_output_qualified") is not False:
        raise fail("manifest must not qualify runtime golden output")
    if retained_doc.get("full_base_pmu_qualified") is not False:
        raise fail("manifest must not qualify full base PMU")
    retained_hash = doc.get("retained_v12_executable_evidence_sha256")
    if retained_hash != _sha256_text(_json_bytes(retained_doc)):
        raise fail("manifest retained V12 executable evidence hash mismatch")
    if doc.get("parser_sha256") != _parser_sha256():
        raise fail("manifest parser_sha256 mismatch")
    artifacts = doc.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise fail("artifact_sha256 malformed")
    if sorted(artifacts) != sorted(ARTIFACT_HASH_KEYS):
        raise fail("artifact_sha256 key set mismatch")
    for key in ARTIFACT_HASH_KEYS:
        value = artifacts.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise fail("artifact_sha256 mismatch: %s" % key)
    evidence_hashes = doc.get("build_evidence_sha256")
    if not isinstance(evidence_hashes, dict):
        raise fail("build_evidence_sha256 malformed")
    if sorted(evidence_hashes) != sorted(BUILD_EVIDENCE_HASH_KEYS):
        raise fail("build_evidence_sha256 key set mismatch")
    for key in BUILD_EVIDENCE_HASH_KEYS:
        value = evidence_hashes.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise fail("build_evidence_sha256 mismatch: %s" % key)
    if doc.get("artifact_bundle_sha256") != _artifact_bundle_sha256(artifacts):
        raise fail("manifest artifact_bundle_sha256 mismatch")
    claimed_manifest_sha = doc.get("manifest_sha256")
    if not isinstance(claimed_manifest_sha, str) or re.fullmatch(r"[0-9a-f]{64}", claimed_manifest_sha) is None:
        raise fail("manifest manifest_sha256 malformed")
    manifest_seed = dict(doc)
    manifest_seed["manifest_sha256"] = "0" * 64
    if claimed_manifest_sha != _sha256_text(_json_bytes(manifest_seed)):
        raise fail("manifest manifest_sha256 mismatch")
    if cross_elf_evidence is not None:
        if doc.get("cross_elf_evidence") != cross_elf_evidence:
            raise fail("manifest cross-ELF evidence mismatch")
        if doc.get("cross_elf_evidence_sha256") != _sha256_text(_json_bytes(cross_elf_evidence)):
            raise fail("manifest cross-ELF evidence hash mismatch")
    if runner_record_wire_evidence is not None:
        if doc.get("runner_record_wire_evidence") != runner_record_wire_evidence:
            raise fail("manifest runner-record/wire evidence mismatch")
        if doc.get("runner_record_wire_evidence_sha256") != _sha256_text(_json_bytes(runner_record_wire_evidence)):
            raise fail("manifest runner-record/wire evidence hash mismatch")
    if retained_v12_executable_evidence is not None:
        if doc.get("retained_v12_executable_evidence") != retained_v12_executable_evidence:
            raise fail("manifest retained V12 executable evidence mismatch")
        if doc.get("retained_v12_executable_evidence_sha256") != _sha256_text(
            _json_bytes(retained_v12_executable_evidence)
        ):
            raise fail("manifest retained V12 executable evidence hash mismatch")
    if artifact_hashes is not None:
        for key in ARTIFACT_HASH_KEYS:
            if artifacts.get(key) != artifact_hashes.get(key):
                raise fail("artifact_sha256 mismatch: %s" % key)
    if build_evidence_hashes is not None:
        for key in BUILD_EVIDENCE_HASH_KEYS:
            if evidence_hashes.get(key) != build_evidence_hashes.get(key):
                raise fail("build_evidence_sha256 mismatch: %s" % key)
    return doc


def _run_tool(args: list[str]) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def _run_tool_normalized(args: list[str]) -> str:
    return _normalize_newlines(_run_tool(args))


def _build_manifest(
    *,
    build_id: str,
    runner_generated: str,
    vendor_generated: str,
    elf_path: str,
    authoritative_v12_elf_path: str,
    objdump_tool: str,
    nm_tool: str,
    map_path: str,
    app_bin_path: str,
    vectors_bin_path: str,
    ddr_bin_path: str,
    v12_objdump_path: str,
    v12_nm_path: str,
    v13_objdump_path: str,
    v13_nm_path: str,
    v13_dwarf_path: str,
    readelf_tool: str,
    cross_elf_evidence_path: str,
    runner_record_wire_evidence_path: str,
    retained_v12_executable_evidence_path: str,
) -> dict[str, object]:
    if build_id != "0x%08X" % BUILD_ID:
        raise fail("build id mismatch")
    with open(runner_generated, "r", encoding="utf-8") as handle:
        runner_text = _normalize_newlines(handle.read())
    with open(vendor_generated, "r", encoding="utf-8") as handle:
        vendor_text = _normalize_newlines(handle.read())
    runner_generated_sha = _sha256_text(runner_text)
    vendor_generated_sha = _sha256_text(vendor_text)
    if runner_generated_sha != RUNNER_GENERATED_SHA256:
        raise fail("runner generated hash mismatch")
    if vendor_generated_sha != VENDOR_GENERATED_SHA256:
        raise fail("vendor generated hash mismatch")
    verify_generated_sources(runner_text, vendor_text)
    header = _run_tool_normalized([readelf_tool, "-h", elf_path])
    if "Type: EXEC" not in header or "Machine: ARM" not in header:
        raise fail("ELF header is not ARM EXEC")
    authoritative_v12_header = _run_tool_normalized([readelf_tool, "-h", authoritative_v12_elf_path])
    if "Type: EXEC" not in authoritative_v12_header or "Machine: ARM" not in authoritative_v12_header:
        raise fail("authoritative V12 ELF header is not ARM EXEC")
    authoritative_v12_sha = _sha256_path(authoritative_v12_elf_path)
    if authoritative_v12_sha != AUTHORITATIVE_V12_SHA256:
        raise fail("authoritative V12 ELF hash mismatch")
    with open(v12_objdump_path, "r", encoding="utf-8") as handle:
        v12_objdump_text = _normalize_newlines(handle.read())
    with open(v12_nm_path, "r", encoding="utf-8") as handle:
        v12_nm_text = _normalize_newlines(handle.read())
    with open(v13_objdump_path, "r", encoding="utf-8") as handle:
        v13_objdump_text = _normalize_newlines(handle.read())
    with open(v13_nm_path, "r", encoding="utf-8") as handle:
        v13_nm_text = _normalize_newlines(handle.read())
    with open(v13_dwarf_path, "r", encoding="utf-8") as handle:
        v13_dwarf_text = _normalize_newlines(handle.read())
    if _run_tool_normalized([objdump_tool, "-d", authoritative_v12_elf_path]) != v12_objdump_text:
        raise fail("authoritative V12 objdump sidecar mismatch")
    if _run_tool_normalized([nm_tool, "-n", authoritative_v12_elf_path]) != v12_nm_text:
        raise fail("authoritative V12 nm sidecar mismatch")
    if _run_tool_normalized([objdump_tool, "-d", elf_path]) != v13_objdump_text:
        raise fail("V13 objdump sidecar mismatch")
    if _run_tool_normalized([nm_tool, "-n", elf_path]) != v13_nm_text:
        raise fail("V13 nm sidecar mismatch")
    if _run_tool_normalized([readelf_tool, "--debug-dump=info,loc", elf_path]) != v13_dwarf_text:
        raise fail("V13 DWARF sidecar mismatch")
    cross_loaded = _load_json(cross_elf_evidence_path)
    cross_expected = verify_cross_elf_contract(
        v12_objdump_text,
        v12_nm_text,
        v13_objdump_text,
        v13_nm_text,
    )
    if cross_loaded != cross_expected:
        raise fail("cross-ELF evidence mismatch")
    runner_record_wire_loaded = _load_json(runner_record_wire_evidence_path)
    runner_record_wire_expected = verify_runner_record_wire_contract(
        runner_text,
        v13_objdump_text,
        v13_nm_text,
        v13_dwarf_text,
    )
    if runner_record_wire_loaded != runner_record_wire_expected:
        raise fail("runner-record/wire evidence mismatch")
    retained_v12_executable_loaded = _load_json(retained_v12_executable_evidence_path)
    retained_v12_executable_expected = verify_retained_v12_executable_contract(
        runner_text,
        vendor_text,
        v13_objdump_text,
        v13_nm_text,
    )
    if retained_v12_executable_loaded != retained_v12_executable_expected:
        raise fail("retained V12 executable evidence mismatch")
    artifact_hashes = {
        "authoritative_v12_elf": authoritative_v12_sha,
        "elf": _sha256_path(elf_path),
        "map": _sha256_path(map_path),
        "app_bin": _sha256_path(app_bin_path),
        "vectors_bin": _sha256_path(vectors_bin_path),
        "ddr_bin": _sha256_path(ddr_bin_path),
        "runner_generated": _sha256_path(runner_generated),
        "vendor_generated": _sha256_path(vendor_generated),
        "authoritative_v12_objdump": _sha256_path(v12_objdump_path),
        "authoritative_v12_nm": _sha256_path(v12_nm_path),
        "v13_objdump": _sha256_path(v13_objdump_path),
        "v13_nm": _sha256_path(v13_nm_path),
        "v13_dwarf": _sha256_path(v13_dwarf_path),
        "cross_elf_evidence": _sha256_path(cross_elf_evidence_path),
        "runner_record_wire_evidence": _sha256_path(runner_record_wire_evidence_path),
        "retained_v12_executable_evidence": _sha256_path(retained_v12_executable_evidence_path),
    }
    build_evidence_hashes = {
        key: artifact_hashes[key]
        for key in BUILD_EVIDENCE_HASH_KEYS
    }
    doc = {
        "variant": VARIANT,
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "runner_source_sha256": runner_generated_sha,
        "vendor_source_sha256": vendor_generated_sha,
        "authoritative_v12_elf_sha256": authoritative_v12_sha,
        "artifact_sha256": artifact_hashes,
        "build_evidence_sha256": build_evidence_hashes,
        "artifact_bundle_sha256": _artifact_bundle_sha256(artifact_hashes),
        "parser_sha256": _parser_sha256(),
        "cross_elf_evidence": cross_loaded,
        "cross_elf_evidence_sha256": _sha256_text(_json_bytes(cross_loaded)),
        "cross_elf_evidence_proof_scope": EQUIVALENCE_SCOPE,
        "runner_record_wire_evidence": runner_record_wire_loaded,
        "runner_record_wire_evidence_sha256": _sha256_text(_json_bytes(runner_record_wire_loaded)),
        "runner_record_wire_proof_scope": RUNNER_RECORD_WIRE_PROOF_SCOPE,
        "runner_record_wire_scope_statement": RUNNER_RECORD_WIRE_SCOPE_NOTE,
        "runner_record_wire_limitations": RUNNER_RECORD_WIRE_DWARF_REQUIRED_NOTE,
        "retained_v12_executable_evidence": retained_v12_executable_loaded,
        "retained_v12_executable_evidence_sha256": _sha256_text(
            _json_bytes(retained_v12_executable_loaded)
        ),
        "retained_v12_executable_proof_scope": RETAINED_V12_EXECUTABLE_PROOF_SCOPE,
        "retained_v12_executable_limitations": RETAINED_V12_EXECUTABLE_LIMITATIONS,
    }
    manifest_seed = dict(doc)
    manifest_seed["manifest_sha256"] = "0" * 64
    doc["manifest_sha256"] = _sha256_text(_json_bytes(manifest_seed))
    validate_artifact_contract(
        _json_bytes(doc),
        cross_loaded,
        runner_record_wire_loaded,
        artifact_hashes,
        build_evidence_hashes,
        retained_v12_executable_loaded,
    )
    return doc


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--runner-generated", required=True)
    parser.add_argument("--vendor-generated", required=True)
    parser.add_argument("--elf", required=True)
    parser.add_argument("--authoritative-v12-elf", required=True)
    parser.add_argument("--objdump-tool", required=True)
    parser.add_argument("--nm-tool", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--app-bin", required=True)
    parser.add_argument("--vectors-bin", required=True)
    parser.add_argument("--ddr-bin", required=True)
    parser.add_argument("--v12-objdump", required=True)
    parser.add_argument("--v12-nm", required=True)
    parser.add_argument("--v13-objdump", required=True)
    parser.add_argument("--v13-nm", required=True)
    parser.add_argument("--v13-dwarf", required=True)
    parser.add_argument("--readelf", required=True)
    parser.add_argument("--cross-elf-evidence", required=True)
    parser.add_argument("--runner-record-wire-evidence", required=True)
    parser.add_argument("--retained-v12-executable-evidence", required=True)
    parser.add_argument("--manifest-out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        cross_loaded = _load_json(args.cross_elf_evidence)
        if cross_loaded.get("v12_v13_poll_loop_equivalence_scope") != EQUIVALENCE_SCOPE:
            raise fail("cross-ELF evidence scope mismatch")
        runner_doc = _build_manifest(
            build_id=args.build_id,
            runner_generated=args.runner_generated,
            vendor_generated=args.vendor_generated,
            elf_path=args.elf,
            authoritative_v12_elf_path=args.authoritative_v12_elf,
            objdump_tool=args.objdump_tool,
            nm_tool=args.nm_tool,
            map_path=args.map,
            app_bin_path=args.app_bin,
            vectors_bin_path=args.vectors_bin,
            ddr_bin_path=args.ddr_bin,
            v12_objdump_path=args.v12_objdump,
            v12_nm_path=args.v12_nm,
            v13_objdump_path=args.v13_objdump,
            v13_nm_path=args.v13_nm,
            v13_dwarf_path=args.v13_dwarf,
            readelf_tool=args.readelf,
            cross_elf_evidence_path=args.cross_elf_evidence,
            runner_record_wire_evidence_path=args.runner_record_wire_evidence,
            retained_v12_executable_evidence_path=args.retained_v12_executable_evidence,
        )
    except Exception as exc:
        raise SystemExit(str(exc))
    _write_manifest_atomic(args.manifest_out, runner_doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
