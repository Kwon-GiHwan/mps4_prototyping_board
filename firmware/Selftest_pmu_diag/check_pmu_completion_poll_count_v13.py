"""Static source and cross-ELF gate for PMU_COMPLETION_POLL_COUNT_DIAG_V13.

The gate proves two independent properties:

1. the generated V13 sources publish ``poll_remaining_at_success`` exactly once
   across the whole vendor translation unit -- on the helper success path only,
   immediately after P2, from the loop induction variable -- and the generated
   runner can only forward that value on the success path, because its single
   other write to the record field is the ``0U`` invalidation inside the
   ``poll_result != V13_POLL_SUCCESS`` gate that follows the copy; and
2. the final V13 poll loop is structurally the V12 poll loop plus that single
   post-P2 store, with the stored value flowing out of the register that the
   failed-poll conditional back edge decrements.

Property 2 is derived from the instruction stream itself (basic-block edges,
register definitions and uses), not from disassembly comments or fixed
addresses, so a relabelled or relocated build is accepted while an extra
per-iteration effect is not. The whole per-iteration region -- STATUS load,
completion test, success branch, failed-path tail and back edge -- is closed:
it may contain those six instructions and nothing else, on either side of the
completion test. Every pointer the helper uses is resolved through the Thumb
literal-pool rule ``((addr + 4) & ~3) + imm`` and bound to the exact address
its role requires, so a build that polls a RAM shadow, reads a fake cycle
counter or publishes the countdown over the P2 slot is refused even though its
instruction shape is unchanged. Where the publication actually *runs* is proven
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
set, including the pre-loop prologue and the tail past the publication. On the
same footing, each of the three published slots must be written by its canonical
site and by nothing else the helper can reach, which is what refuses a pre-loop
store that pre-seeds the record ahead of both the success and timeout entries.
The runner half of property 1 is likewise derived
from brace nesting and assignment right-hand sides, never from column alignment,
so reformatting the generated runner cannot change the verdict.

Scope: this module gates generated sources and the helper poll loop of the two
final ELFs. The retained V12 executable proofs that need whole-image artifacts
(stock vector table, NVIC hard-bypass, path-sensitive CMD/QREAD, PMU, H-PRINTF,
golden output, terminal release) stay in ``check_pmu_completion_poll_v12`` and
are re-run against the V13 image by the V13 build graph. The only retained-V12
proof enforced here is that the V13 image reintroduces no NVIC *enable*: neither
an ``NVIC_EnableIRQ`` call site nor a direct NVIC->ISER write. The stock
``NVIC_SetVector`` and ``NVIC_ClearPendingIRQ`` call sites are required by that
retained contract, so their presence is not drift here; their operands and
ordering are proven by the whole-image gate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import check_pmu_qual as qual_elf
from check_pmu_completion_poll_v12 import (
    _function_section,
    fail,
    parse_functions,
)

SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
VARIANT = "PMU_COMPLETION_POLL_COUNT_DIAG_V13"
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
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
_LOOP_HEADER = "for (uint32_t i = 0U; i < %dU; ++i) {" % POLL_LIMIT
_SUCCESS_GUARD = "if ((status & 0x%02XU) != 0U) {" % COMPLETION_MASK
_STATUS_READ_STATEMENT = "status = *status_reg;"
_REMAINING_RHS = "%dU - i" % POLL_LIMIT

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
_REG_TOKEN_RE = re.compile(r"\b(?:r\d+|sl|sb|fp|ip|sp|lr|pc)\b")

_HEX_WORD_RE = re.compile(r"\.word\s+0x([0-9A-Fa-f]+)")
_ENCODING_RE = re.compile(r"^(?:[0-9a-f]{8}|[0-9a-f]{4}(?:\s+[0-9a-f]{4})*)\s+(?=[a-z.])")
_BRANCH_TARGET_RE = re.compile(r"\b([0-9a-fA-F]+)\s+<")
# Group 3 of a load/store is whatever else lives inside the brackets: empty for
# `[r7]`, `, #4` for a displaced access, `, r2` or `, r2, lsl #1` for a
# register-offset one. `_displacement` reads it, and reports None for every
# form whose displacement is not a plain immediate so the address stays
# unproven rather than being silently taken as zero.
_LOAD_RE = re.compile(r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+(r\d+),\s*\[([a-z0-9]+)([^\]]*)\]")
_PC_LOAD_RE = re.compile(r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+(r\d+),\s*\[pc\b")
_PC_OFFSET_RE = re.compile(
    r"^ldr(?:b|h|sb|sh)?(?:\.w)?\s+r\d+,\s*\[pc,\s*#(-?\d+)\]"
)
_STORE_RE = re.compile(r"^str(?:b|h)?(?:\.w)?\s+(r\d+),\s*\[([a-z0-9]+)([^\]]*)\]")
_DISPLACEMENT_RE = re.compile(r"^,\s*#(-?(?:0x[0-9a-fA-F]+|\d+))$")
_DECREMENT_RE = re.compile(r"^subs(?:\.w)?\s+(r\d+),\s*#1$")
_TEST_RE = re.compile(r"^tst(?:\.w)?\s+(r\d+),\s*#(\d+)$")
_DEST_RE = re.compile(r"^[a-z][a-z0-9.]*\s+(r\d+)\b")
_CALL_TO_RE = r"\bbl(?:x)?(?:\.w)?\s+[0-9a-fA-F]+\s+<%s>"

_WRITING_MNEMONICS = frozenset(
    (
        "mov", "movs", "movw", "movt", "mvn", "mvns", "neg", "negs",
        "add", "adds", "adc", "adcs", "sub", "subs", "sbc", "sbcs", "rsb", "rsbs",
        "and", "ands", "orr", "orrs", "orn", "eor", "eors", "bic", "bics",
        "lsl", "lsls", "lsr", "lsrs", "asr", "asrs", "ror", "rors",
        "mul", "muls", "mla", "mls", "udiv", "sdiv", "umull", "smull",
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
    induction_register: str
    remaining_store_after_p2_exactly_once: bool
    remaining_store_timeout_unreachable: bool
    remaining_from_back_edge_induction: bool
    helper_leaf_no_stack_access: bool


@dataclass(frozen=True)
class _HelperAnalysis:
    variant: str
    helper_name: str
    helper_addr: int
    code: tuple[_Insn, ...]
    literals: tuple[tuple[int, int], ...]
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


def _verify_runner_remaining_gate(runner_text: str) -> None:
    """Prove the runner can publish remaining only on the success path.

    Structural, not textual: the two record writes are located by brace nesting
    relative to the ``poll_result != V13_POLL_SUCCESS`` gate and classified by
    their normalized right-hand side, so re-indenting or re-aligning the
    generated runner cannot change the verdict.
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
        raise fail("remaining must be derived from the loop induction variable")

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
        helper, helper_start = _extract_vendor_helper(vendor_text)
        remaining_offset = _verify_vendor_helper_source(helper)
        _verify_vendor_tu_single_writer(vendor_text, helper_start + remaining_offset)

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
        if not body or body.startswith("."):
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
    """
    slots = dict(literals)
    states: list[dict[str, int]] = []
    state: dict[str, int] = {}
    for index, insn in enumerate(code):
        states.append(dict(state))
        target = pc_targets.get(index)
        if target is not None:
            state[_PC_LOAD_RE.match(insn.text).group(1)] = slots[target]
            continue
        dest = _defined_register(insn)
        if dest is not None:
            state.pop(dest, None)
    return tuple(states)


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

    # The published register must be the one the back edge counts on, and it
    # must still hold that decrement's value when the store runs. "Still holds"
    # is a statement about every path, not about layout order, so the redefining
    # instructions are looked for on the instructions that actually lie between
    # the success entry and the publication: reachable from the entry and able
    # to reach the store. A reload parked on a branch the entry can take reaches
    # the store just as surely as one written in a straight line.
    induction_reg = _back_edge_induction_register(analysis)
    on_path_to_store = (
        _reachable(successors, success_entry)
        & _co_reachable(successors, remaining_index)
    ) - {remaining_index}
    redefined_on_path = any(
        _defined_register(analysis.code[index]) == remaining_reg for index in on_path_to_store
    )
    remaining_from_back_edge_induction = remaining_reg == induction_reg and not redefined_on_path
    if not remaining_from_back_edge_induction:
        raise fail("remaining must dataflow from failed-poll countdown live-out")

    helper_leaf_no_stack_access = not analysis.has_stack_access
    if not helper_leaf_no_stack_access:
        raise fail("helper must remain a leaf without stack access")
    if analysis.has_extra_non_status_load:
        raise fail("extra non-STATUS load")

    return RemainingDataflowProof(
        source="back_edge_induction",
        induction_register=induction_reg,
        remaining_store_after_p2_exactly_once=remaining_store_after_p2_exactly_once,
        remaining_store_timeout_unreachable=remaining_store_timeout_unreachable,
        remaining_from_back_edge_induction=remaining_from_back_edge_induction,
        helper_leaf_no_stack_access=helper_leaf_no_stack_access,
    )


def _nvic_block_bases(fn, pool: dict[int, int]) -> tuple[frozenset[str], ...]:
    """Per-instruction set of registers that may hold an NVIC-block pointer.

    A register enters the set by loading a literal inside ``NVIC_Type`` and
    leaves it when it is redefined by anything that does not read a member of
    the set. Arithmetic on such a pointer keeps it in the set even though its
    value stops being provable, which is what makes the caller's fail-closed
    branch reachable instead of vacuous.
    """
    states: list[frozenset[str]] = []
    tainted: set[str] = set()
    for ins in fn.insns:
        states.append(frozenset(tainted))
        if ins.kind == "call":
            tainted -= set(qual_elf.CALL_CLOBBERED)
            continue
        if ins.kind == "ldr_lit":
            word = pool.get(ins.literal_addr)
            if word is not None and _NVIC_BLOCK_FIRST <= word <= _NVIC_BLOCK_LAST:
                tainted.add(ins.dest)
            else:
                tainted.discard(ins.dest)
            continue
        if ins.dest is None:
            continue
        # Every other writer is opaque, so it is read pessimistically: it
        # carries the taint of whatever registers it reads, which are the
        # operands after the destination it writes in the first one.
        _, _, read_operands = ins.operands.partition(",")
        if set(_REG_TOKEN_RE.findall(read_operands)) & tainted:
            tainted.add(ins.dest)
        else:
            tainted.discard(ins.dest)
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
    -- which the retained V12 hard bypass is required to do. Store destinations
    are therefore resolved the way V12 resolves them, through
    ``qual_elf.store_address``, and only a store that lands inside ISER is
    drift. A store that cannot be resolved is drift too whenever its base could
    be an NVIC-block pointer, so an enable cannot hide behind a base the
    resolver gives up on.
    """
    for callee in _V12_RUNTIME_DRIFT_CALLEES:
        if re.search(_CALL_TO_RE % re.escape(callee), disassembly_text):
            raise fail("retained V12 NVIC enable drift: %s call site" % callee)
    dis = qual_elf.parse_disassembly(disassembly_text)
    pool = qual_elf.literal_pool(dis.functions)
    for name, fn in dis.functions.items():
        bases = _nvic_block_bases(fn, pool)
        for index, ins in enumerate(fn.insns):
            if ins.kind == "store":
                address = qual_elf.store_address(fn, index, pool)
                if address is None:
                    if ins.base in bases[index]:
                        raise fail(
                            "NVIC-block store destination unresolvable at %s+0x%X"
                            % (name, ins.addr - fn.addr)
                        )
                    continue
                if _NVIC_ISER_FIRST <= address <= _NVIC_ISER_LAST:
                    raise fail(
                        "direct NVIC ISER enable write remains reachable: %s+0x%X -> 0x%08X"
                        % (name, ins.addr - fn.addr, address)
                    )
                continue
            # A store the classifier could not decode -- a register-offset or
            # writeback form -- is not a store it can prove innocent either.
            if ins.mnemonic.split(".")[0].startswith("str") and (
                set(_REG_TOKEN_RE.findall(ins.operands)) & bases[index]
            ):
                raise fail(
                    "NVIC-block store destination unresolvable at %s+0x%X"
                    % (name, ins.addr - fn.addr)
                )


def verify_cross_elf_contract(
    v12_disassembly_text: str,
    v12_nm_text: str,
    v13_disassembly_text: str,
    v13_nm_text: str,
) -> dict[str, object]:
    v12_loop = extract_poll_loop(v12_disassembly_text, v12_nm_text)
    v13_loop = extract_poll_loop(v13_disassembly_text, v13_nm_text)
    if v12_loop.variant != "v12" or v13_loop.variant != "v13":
        raise fail("cross-ELF gate requires one V12 and one V13 helper")
    if normalize_poll_loop(v12_loop) != normalize_poll_loop(v13_loop):
        raise fail("V12/V13 normalized poll loop mismatch")
    if v13_loop.extra_per_iteration_instruction_count != 0 or v13_loop.has_forbidden_loop_effect:
        raise fail("extra per-iteration instruction")
    proof = prove_remaining_dataflow(v13_disassembly_text, v13_nm_text)
    _check_retained_v12_runtime(v13_disassembly_text)
    return {
        "variant": VARIANT,
        "v12_v13_poll_loop_semantically_equivalent": True,
        "v13_extra_per_iteration_instruction_count_zero": True,
        "remaining_store_after_p2_exactly_once": proof.remaining_store_after_p2_exactly_once,
        "remaining_from_back_edge_induction": proof.remaining_from_back_edge_induction,
        "remaining_store_timeout_unreachable": proof.remaining_store_timeout_unreachable,
        "helper_leaf_no_stack_access": proof.helper_leaf_no_stack_access,
        "remaining_induction_register": proof.induction_register,
        "loop_equivalent": True,
    }
