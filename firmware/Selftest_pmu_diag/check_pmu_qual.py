"""Schema-v8 Q0/Q1 qualification gate: source, object, final ELF and map.

The H-PRINTF candidate hooks a callsite that exists only in the VENDOR
driver's compiled output. Nothing in the C source names it, so the only honest
proof that the hook lands where the design says it does is the final link
itself. This gate reads that link and refuses to emit a deployable manifest
unless every one of the design's callsite terms is proven.

Two rules are worth stating outright, because getting either wrong turns the
gate into decoration:

  * The unique-target term counts CALLSITES, not strings. Counting occurrences
    of the target byte sequence would be trivially satisfiable -- the runner's
    own matcher, the rodata copy and any diagnostic table all contain it. This
    gate follows the caller's literal-pool load, reconstructs the FIRST
    ARGUMENT of every call, reads the bytes that pointer actually names out of
    the section dump, and requires exactly one call whose first argument is the
    complete target string.

  * The target call's OWN relocation is a hard term; the total relocation
    COUNTS are not. Those are two different claims and only one of them is
    worth gating. Pinning `printf_relocations` at a remembered number would
    fail whenever an unrelated diagnostic printf was edited in the vendor
    file, and -- worse -- a healthy-looking total says nothing about the one
    call that matters. So the gate reconstructs the target call inside the
    RELOCATABLE object and requires THAT call to carry an R_ARM_*_CALL
    relocation against exactly `printf`. An object whose target call was
    lowered to puts/iprintf, folded to a builtin, or left unrelocated fails
    even while its printf total looks entirely normal.

    This was originally written the other way round -- totals recorded, target
    relocation merely implied -- which was fail-open: a target call with no
    relocation at all still passed. Independent review caught it.

Anything the gate cannot PROVE is a failure. An unresolved register in the
release tail is treated as an access that might be there, never as one that is
not; a build whose optimization shape defeats the reconstruction fails rather
than being accepted on the strength of the shape it used to have.

Addresses flow one way only. They are extracted here, after the link, and
written into the manifest for the host to compare against the runtime LR. The
firmware never imports them.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys

# The exact vendor format string, spelled once. The FIRMWARE matcher may not
# hold a second copy of this literal (it compares byte by byte instead), but
# the gate is a separate program on the host side and is where the expected
# bytes are allowed to be written down.
TARGET_FORMAT = "Testing CPM signals\n"
CALLER_SYMBOL = "test_u85"
WRAP_PRINTF_SYMBOL = "__wrap_printf"
HOOK_SYMBOL = "pmu_qual_pre_release_hook"
# The hook's ordered operations, named by the symbols that survive the link.
# pmu_diag_capture_post_order (the internal_pre_release capture) is inlined by
# the compiler and has no symbol, so it is attested through its own cycle read.
CYCLE_READ_SYMBOL = "npu_pmu_read_cycles"
PMU_DISABLE_SYMBOL = "npu_pmu_disable"
POST_DISABLE_CAPTURE_SYMBOL = "pmu_diag_capture_pre_order"
PMU_REG_READ_SYMBOL = "pmu_reg_read"
LATCH_SYMBOL = "pmu_qual_hook_snapshot_valid"
# The compiled signature of pmu_diag_capture_post_order, which the compiler
# inlines into the hook: the cycle counter first (its own call), then these
# four registers in this order. The cycle read alone would prove only
# cycle_lo/hi; the snapshot the host classifier judges also carries
# pmcr/pmcntenset/pmccntr_cfg/pmovsset, and every one of those terms is
# meaningless if the read that produced it is not in the image.
PRE_RELEASE_SNAPSHOT_REGS = ("NPU_REG_PMCR", "NPU_REG_PMCNTENSET",
                             "NPU_REG_PMCCNTR_CFG", "NPU_REG_PMOVSSET")
REGS_HEADER_OFFSETS = PRE_RELEASE_SNAPSHOT_REGS
# After the validity latch the hook may only wind down. Judged on OPERANDS,
# not on the mnemonic alone: `pop {r4, r5}` and `pop {r4, pc}` are the same
# instruction with materially different meanings, and only the second one ends
# the function. Anything that is not literal data, a nop, or a real return is
# refused -- including a bare ldr or a branch, which are side-effect-free in
# isolation but prove nothing about what runs next.
DATA_DIRECTIVES = frozenset((".word", ".short", ".hword", ".byte", ".long",
                             ".quad", ".ascii", ".asciz", ".space", ".zero"))
_REGLIST = re.compile(r"\{([^}]*)\}")
_RETURN_STACK_POPS = ("pop", "ldmia", "ldmfd", "ldm")
# What the target call must relocate against in the RELOCATABLE object, before
# --wrap has had any say. Exact match: __wrap_printf here would mean the vendor
# object was built against the wrapper directly, which is a different image.
TARGET_RELOC_SYMBOL = "printf"
VENDOR_RELEASE_VALUE = 0x0C
VENDOR_STOP_VALUE = 0x00
MODES = ("Q0", "Q1")

# -ffunction-sections puts the vendor caller in its own section; that is the
# only section the object gate will read, so a relocation from anywhere else
# cannot be mistaken for the target's.
OBJECT_TEXT_SECTION = ".text." + CALLER_SYMBOL
# Debug/comment sections are not addressable code or data. In a linked ELF they
# all sit at address 0, so flattening them into the VMA map could collide with
# real low addresses; they are skipped rather than trusted not to.
NON_ADDRESSABLE_SECTION_PREFIXES = (".debug", ".comment", ".ARM.attributes")

_REG = re.compile(r"^(r\d+|sl|sb|fp|ip|sp|lr|pc)$")
_FUNC_HDR = re.compile(r"^([0-9a-fA-F]+)\s+<([^>]+)>:\s*$")
_INSN = re.compile(r"^\s*([0-9a-fA-F]+):\t[^\t]*\t(\S+)(?:\t(.*))?$")
_CALL_TARGET = re.compile(r"<([^>+]+)(?:\+0x[0-9a-fA-F]+)?>")
_PCREL = re.compile(r"\[pc[^\]]*\]")
_PCREL_ADDR = re.compile(r"[@;]\s*\(?\s*(?:0x)?([0-9a-fA-F]+)\s*<")
_IMM = re.compile(r"#(-?\d+|0x[0-9a-fA-F]+)")
_MEMOP = re.compile(r"\[(\w+)(?:\s*,\s*#(-?\d+|0x[0-9a-fA-F]+))?\s*\]")
_DUMP_ROW = re.compile(r"^ ([0-9a-fA-F]{4,16}) ")
_SECTION_HDR = re.compile(r"^Disassembly of section (\S+):\s*$")
_SECTION_CONTENTS = re.compile(r"^Contents of section (\S+):\s*$")
# objdump -dr prints relocations under the instruction they apply to, as
# "OFFSET: TYPE\tSYMBOL" (optionally "SYMBOL+0xADDEND"). Note the space after
# the colon, which is what keeps these lines from matching _INSN.
_RELOC = re.compile(
    r"^\s+([0-9a-fA-F]+):\s+(R_\S+)\s+(\S+?)(?:\+0x([0-9a-fA-F]+))?\s*$")
_CALL_RELOC = re.compile(r"^R_ARM_\w*CALL$")


class GateError(Exception):
    """A design term that could not be proven. Always fatal."""


def _int(text):
    return int(text, 16) if text.lower().startswith("0x") else int(text, 10)


# ---------------------------------------------------------------------------
# Disassembly model
# ---------------------------------------------------------------------------

class Insn:
    __slots__ = ("addr", "mnemonic", "operands", "kind", "dest", "value",
                 "base", "offset", "src", "callee", "literal_addr", "text")

    def __init__(self, addr, mnemonic, operands):
        self.addr = addr
        self.mnemonic = mnemonic
        self.operands = operands
        self.text = "%s %s" % (mnemonic, operands)
        self.kind = "other"
        self.dest = self.value = self.base = self.offset = None
        self.src = self.callee = self.literal_addr = None
        self._classify()

    def _classify(self):
        # Directives keep their leading dot; only real mnemonics carry the
        # ".w"/".n"/condition suffixes that need stripping.
        mnem = (self.mnemonic if self.mnemonic.startswith(".")
                else self.mnemonic.split(".")[0])
        ops = [o.strip() for o in self.operands.split(",")] if self.operands else []
        first = ops[0] if ops and _REG.match(ops[0]) else None

        if mnem in ("bl", "blx"):
            self.kind = "call"
            hit = _CALL_TARGET.search(self.operands)
            self.callee = hit.group(1) if hit else self.operands.strip()
            return
        if mnem == ".word":
            self.kind = "word"
            self.value = _int(self.operands.split()[0].strip())
            return
        if mnem.startswith("ldr") and _PCREL.search(self.operands):
            hit = _PCREL_ADDR.search(self.operands)
            if hit and first:
                self.kind = "ldr_lit"
                self.dest = first
                self.literal_addr = int(hit.group(1), 16)
                return
        if mnem.startswith("str"):
            hit = _MEMOP.search(self.operands)
            if hit and ops and _REG.match(ops[0]):
                self.kind = "store"
                self.src = ops[0]
                self.base = hit.group(1)
                self.offset = _int(hit.group(2)) if hit.group(2) else 0
                return
        if mnem in ("mov", "movs", "movw") and first:
            imm = _IMM.search(self.operands)
            self.dest = first
            if imm:
                self.kind = "mov_imm"
                self.value = _int(imm.group(1))
            return
        # Everything else is an opaque definition of its first operand. That is
        # deliberately pessimistic: an unrecognised writer makes the register
        # UNKNOWN, which fails closed wherever its value is load-bearing.
        self.dest = first


class Function:
    def __init__(self, name, addr):
        self.name = name
        self.addr = addr
        self.insns = []


class Disassembly:
    """One objdump -d / -dr dump: its functions, the sections it covered, and
    any relocation records keyed by the offset they apply to."""

    def __init__(self):
        self.functions = {}
        self.sections = []
        self.relocations = {}   # offset -> (type, symbol, explicit_addend|None)


def parse_disassembly(text):
    """objdump -d / -dr text -> Disassembly. Literal-pool `.word` entries stay
    in the instruction list so the pool can be read back from the same source
    the callsite came from."""
    dis = Disassembly()
    cur = None
    for line in text.splitlines():
        sec = _SECTION_HDR.match(line)
        if sec:
            dis.sections.append(sec.group(1))
            continue
        hdr = _FUNC_HDR.match(line)
        if hdr:
            cur = Function(hdr.group(2), int(hdr.group(1), 16))
            dis.functions[cur.name] = cur
            continue
        # Relocations are matched BEFORE instructions: both start with an
        # offset and a colon, and only the separator that follows tells them
        # apart. Getting that order wrong would silently drop every record.
        rel = _RELOC.match(line)
        if rel:
            dis.relocations[int(rel.group(1), 16)] = (
                rel.group(2), rel.group(3),
                int(rel.group(4), 16) if rel.group(4) else None)
            continue
        hit = _INSN.match(line)
        if not hit or cur is None:
            continue
        cur.insns.append(Insn(int(hit.group(1), 16), hit.group(2),
                              hit.group(3) or ""))
    if not dis.functions:
        raise GateError("no disassembly could be parsed from the dump")
    return dis


def literal_pool(funcs):
    pool = {}
    for fn in funcs.values():
        for ins in fn.insns:
            if ins.kind == "word":
                pool[ins.addr] = ins.value
    return pool


def parse_section_dumps(text):
    """objdump -s text -> {section: {offset: byte}}.

    Section-keyed rather than flat, because in a RELOCATABLE object the
    offsets restart at zero in every section: a flat map would let one
    section's bytes answer for another's. Fixed-width fields, which is what
    objdump emits: 4 groups of 8 hex digits after the offset.
    """
    dumps = {}
    cur = None
    for line in text.splitlines():
        sec = _SECTION_CONTENTS.match(line)
        if sec:
            cur = dumps.setdefault(sec.group(1), {})
            continue
        hit = _DUMP_ROW.match(line)
        if not hit or cur is None:
            continue
        addr = int(hit.group(1), 16)
        blob = line[hit.end():hit.end() + 35].replace(" ", "")
        if len(blob) % 2:
            blob = blob[:-1]
        try:
            raw = bytes.fromhex(blob)
        except ValueError:
            continue
        for n, byte in enumerate(raw):
            cur[addr + n] = byte
    return dumps


def flatten_section_dumps(dumps):
    """Collapse to {address: byte} for a LINKED image, where every section has
    a distinct VMA. Non-addressable sections are dropped rather than trusted:
    they all report address 0 and would otherwise overlay real low memory."""
    flat = {}
    for name, blob in dumps.items():
        if name.startswith(NON_ADDRESSABLE_SECTION_PREFIXES):
            continue
        flat.update(blob)
    return flat


def parse_section_dump(text):
    return flatten_section_dumps(parse_section_dumps(text))


def read_cstring(data, addr, limit=256):
    """The bytes the reconstructed pointer actually names, NUL-terminated. A
    pointer into the middle of another string, or one whose bytes are simply
    absent from the dump, yields None rather than a lucky prefix."""
    out = bytearray()
    for n in range(limit):
        byte = data.get(addr + n)
        if byte is None:
            return None
        if byte == 0:
            return out.decode("utf-8", "replace")
        out.append(byte)
    return None


# AAPCS: a definition older than a call proves nothing about these.
CALL_CLOBBERED = ("r0", "r1", "r2", "r3", "ip", "lr")


def defining_insn(fn, index, reg):
    """(position, Insn) of the definition of `reg` that REACHES fn.insns[index],
    or None.

    The first definition found walking backwards is by construction the one
    that reaches the use, so callers get "no intervening redefinition" for
    free rather than having to re-scan for it.
    """
    for n in range(index - 1, -1, -1):
        ins = fn.insns[n]
        if ins.kind == "call":
            if reg in CALL_CLOBBERED:
                return None
            continue
        if ins.dest != reg:
            continue
        return n, ins
    return None


def resolve_register(fn, index, reg, pool):
    """Value of `reg` immediately before fn.insns[index], or None if it cannot
    be proven. Only a literal-pool load or a move-immediate counts; every other
    definition -- including a register-to-register move -- is unknown."""
    found = defining_insn(fn, index, reg)
    if found is None:
        return None
    _, ins = found
    if ins.kind == "ldr_lit":
        return pool.get(ins.literal_addr)
    if ins.kind == "mov_imm":
        return ins.value
    return None


def store_address(fn, index, pool):
    """Absolute address a store writes to, or None when the base register
    cannot be proven."""
    ins = fn.insns[index]
    base = resolve_register(fn, index, ins.base, pool)
    return None if base is None else base + ins.offset


# ---------------------------------------------------------------------------
# Callsite terms
# ---------------------------------------------------------------------------

def resolve_r0_literal(fn, index):
    """Offset of the literal-pool SLOT that supplies r0 at fn.insns[index], or
    None if it cannot be proven.

    The object needs the slot's offset, not its value: the value is only half
    the pointer -- the other half is the slot's own relocation, which names the
    section the addend is relative to.
    """
    found = defining_insn(fn, index, "r0")
    if found is None:
        return None
    _, ins = found
    return ins.literal_addr if ins.kind == "ldr_lit" else None


def check_object_target_relocation(dis, section_dumps):
    """Prove the TARGET vendor call relocates against printf, in the object.

    This is the term that cannot be recovered after the link. Once ld has run,
    a call that the compiler lowered to puts and a call it left as printf both
    look like ordinary resolved calls; only the relocatable object still says
    which one the compiler emitted. So the target call is re-identified here
    from scratch -- literal slot, slot relocation, rodata addend, string bytes
    -- and then its own relocation record is required to be an R_ARM_*_CALL
    against exactly `printf`.

    Unrelated printf calls in the same object are untouched by any of this.
    """
    fn = dis.functions.get(CALLER_SYMBOL)
    if fn is None:
        raise GateError(
            "object caller <%s> is absent from the disassembled section "
            "(found %s)"
            % (CALLER_SYMBOL,
               ", ".join("<%s>" % n for n in sorted(dis.functions)) or "none"))
    if OBJECT_TEXT_SECTION not in dis.sections:
        raise GateError(
            "object disassembly covers section %s, expected %s"
            % (", ".join(dis.sections) or "none", OBJECT_TEXT_SECTION))

    pool = {ins.addr: ins.value for ins in fn.insns if ins.kind == "word"}
    hits = []
    for n, ins in enumerate(fn.insns):
        if ins.kind != "call":
            continue
        slot = resolve_r0_literal(fn, n)
        if slot is None:
            continue
        slot_reloc = dis.relocations.get(slot)
        if slot_reloc is None:
            # An unrelocated literal is an absolute address, which a
            # relocatable object has no business knowing. Not the target.
            continue
        _, string_section, explicit = slot_reloc
        # REL, as ARM uses: the addend lives in the word itself unless objdump
        # printed an explicit one.
        addend = explicit if explicit is not None else pool.get(slot)
        if addend is None:
            continue
        blob = section_dumps.get(string_section)
        if blob is None:
            continue
        if read_cstring(blob, addend) != TARGET_FORMAT:
            continue
        hits.append((ins, slot, string_section, addend))

    if len(hits) != 1:
        raise GateError(
            "expected exactly 1 object target callsite whose first argument "
            "resolves to the complete target string, found %d" % len(hits))

    call, slot, string_section, addend = hits[0]
    reloc = dis.relocations.get(call.addr)
    if reloc is None:
        raise GateError(
            "the object target call at <%s>+0x%x carries NO relocation; the "
            "vendor call must relocate against %r"
            % (CALLER_SYMBOL, call.addr, TARGET_RELOC_SYMBOL))
    rtype, symbol, _ = reloc
    if not _CALL_RELOC.match(rtype):
        raise GateError(
            "the object target call at <%s>+0x%x has relocation type %s, "
            "expected an R_ARM_*_CALL"
            % (CALLER_SYMBOL, call.addr, rtype))
    if symbol != TARGET_RELOC_SYMBOL:
        raise GateError(
            "the object target call at <%s>+0x%x relocates against %r, "
            "expected exactly %r -- a puts/iprintf/builtin lowering erases the "
            "callsite the hook depends on"
            % (CALLER_SYMBOL, call.addr, symbol, TARGET_RELOC_SYMBOL))

    return {
        "object_caller_symbol": CALLER_SYMBOL,
        "object_section": OBJECT_TEXT_SECTION,
        "object_target_call_offset": call.addr,
        "object_target_relocation_type": rtype,
        "object_target_relocation_symbol": symbol,
        "object_target_literal_offset": slot,
        "object_target_string_section": string_section,
        "object_target_string_offset": addend,
        "object_target_callsite_count": len(hits),
    }


def find_target_callsites(funcs, pool, data):
    """Every call in the image whose reconstructed first argument is the
    COMPLETE target string, wherever it lives."""
    hits = []
    for fn in funcs.values():
        for n, ins in enumerate(fn.insns):
            if ins.kind != "call":
                continue
            arg0 = resolve_register(fn, n, "r0", pool)
            if arg0 is None:
                continue
            if read_cstring(data, arg0) != TARGET_FORMAT:
                continue
            hits.append((fn, n))
    return hits


def check_stop_precedes(fn, index, pool, cmd_addr):
    """The vendor STOP (CMD=0) is the last NPU CMD write before the target
    call, and nothing is called in between."""
    for n in range(index - 1, -1, -1):
        ins = fn.insns[n]
        if ins.kind == "call":
            raise GateError(
                "an external call sits between the vendor STOP and the target "
                "call in <%s> at 0x%08x" % (fn.name, ins.addr))
        if ins.kind != "store":
            continue
        addr = store_address(fn, n, pool)
        if addr != cmd_addr:
            continue
        value = resolve_register(fn, n, ins.src, pool)
        if value != VENDOR_STOP_VALUE:
            raise GateError(
                "the NPU CMD write preceding the target call at 0x%08x stores "
                "%s, expected the vendor STOP value 0x%02X"
                % (ins.addr, "an unresolved value" if value is None
                   else "0x%X" % value, VENDOR_STOP_VALUE))
        return ins.addr
    raise GateError("no vendor STOP (NPU CMD=0) write precedes the target call "
                    "in <%s>" % fn.name)


def check_release_tail(fn, index, pool, cmd_addr):
    """From the target call's RETURN address to the vendor terminal release,
    the caller's instruction stream contains no other NPU CMD access and no
    external call."""
    if index + 1 >= len(fn.insns):
        raise GateError("the target call is the last instruction in <%s>; no "
                        "vendor release follows" % fn.name)
    return_addr = fn.insns[index + 1].addr

    release = None
    for n in range(index + 1, len(fn.insns)):
        ins = fn.insns[n]
        if ins.kind != "store":
            continue
        if store_address(fn, n, pool) != cmd_addr:
            continue
        value = resolve_register(fn, n, ins.src, pool)
        if value is None:
            # An NPU CMD write whose value cannot be proven is not something to
            # scan past looking for a nicer one: it may itself be the release,
            # or may disturb the register the release depends on.
            raise GateError(
                "an NPU CMD store at 0x%08x after the target return writes a "
                "value that cannot be proven (source register %s); the vendor "
                "release must be a provable immediate" % (ins.addr, ins.src))
        if value == VENDOR_RELEASE_VALUE:
            release = n
            break
    if release is None:
        raise GateError(
            "no vendor terminal release (NPU CMD=0x%02X) store follows the "
            "target call's return in <%s>" % (VENDOR_RELEASE_VALUE, fn.name))

    for n in range(index + 1, release):
        ins = fn.insns[n]
        if ins.kind == "call":
            raise GateError(
                "an external call to %s at 0x%08x sits between the target "
                "return and the vendor release" % (ins.callee, ins.addr))
        if ins.kind != "store":
            continue
        addr = store_address(fn, n, pool)
        if addr is None:
            raise GateError(
                "a store at 0x%08x between the target return and the vendor "
                "release has an unresolved base register (%s); it cannot be "
                "proven not to touch NPU CMD" % (ins.addr, ins.base))
        if addr == cmd_addr:
            raise GateError(
                "an extra NPU CMD access at 0x%08x sits between the target "
                "return and the vendor release" % ins.addr)

    immediate = check_release_immediate(fn, release, index)
    return return_addr, fn.insns[release].addr, release, immediate


def check_release_immediate(fn, release_index, call_index):
    """Design item 8: the release value must be an IMMEDIATE 12 established
    after the target call returns.

    The value being 12 is already pinned by the search above; what is proven
    here is where that 12 came from. A literal-pool load would mean the
    constant was materialised somewhere the caller's instruction stream does
    not show, and the whole point of this tail contract is that the vendor's
    release is visible, in order, between the return and the store. A
    register-to-register move has the same problem one step removed.

    "No intervening redefinition" comes for free: defining_insn() returns the
    definition that REACHES the store, so a later redefinition would be the
    one returned.
    """
    store = fn.insns[release_index]
    found = defining_insn(fn, release_index, store.src)
    if found is None:
        raise GateError(
            "nothing defines the release source register %s before the store "
            "at 0x%08x" % (store.src, store.addr))
    pos, ins = found
    if ins.kind == "ldr_lit":
        raise GateError(
            "the release value at 0x%08x is loaded from the literal pool by "
            "0x%08x (%s); design item 8 requires an immediate move of #%d "
            "after the target call returns"
            % (store.addr, ins.addr, ins.text, VENDOR_RELEASE_VALUE))
    if ins.kind != "mov_imm":
        raise GateError(
            "the release value at 0x%08x is defined by 0x%08x (%s), which is "
            "not a move-immediate; the release constant must be provable"
            % (store.addr, ins.addr, ins.text))
    if ins.value != VENDOR_RELEASE_VALUE:
        raise GateError(
            "the release immediate at 0x%08x is #%d, expected #%d"
            % (ins.addr, ins.value, VENDOR_RELEASE_VALUE))
    if pos <= call_index:
        raise GateError(
            "the release immediate at 0x%08x is established BEFORE the target "
            "call returns; the STOP -> call -> immediate -> store order is "
            "what the tail contract asserts" % ins.addr)
    return ins.addr, ins.value


def normalized_digest(fn, stop_index, release_index):
    """Digest over the callsite tail with ADDRESSES REMOVED, so Q0 and Q1 --
    which are separate links at different numeric addresses -- can be compared
    on logical shape. The absolute addresses are reported separately."""
    body = []
    for ins in fn.insns[stop_index:release_index + 1]:
        text = re.sub(r"\b[0-9a-fA-F]{6,16}\b", "<addr>", ins.text)
        text = re.sub(r"\[pc[^\]]*\]", "[pc]", text)
        text = re.sub(r"[@;].*$", "", text)
        body.append(" ".join(text.split()))
    return hashlib.sha256("\n".join(body).encode()).hexdigest(), body


# ---------------------------------------------------------------------------
# Source, object and configuration terms
# ---------------------------------------------------------------------------

def check_test_cpm(source_text):
    hits = re.findall(r"^\s*#define\s+TEST_CPM\s+(\d+)\s*$", source_text, re.M)
    if len(hits) != 1:
        raise GateError("vendor source declares TEST_CPM %d times, expected 1"
                        % len(hits))
    if hits[0] != "1":
        raise GateError("vendor source has TEST_CPM=%s; the qualification "
                        "images require TEST_CPM=1" % hits[0])
    return 1


def check_single_terminal_release(source_text):
    hits = re.findall(
        r"write_reg\s*\(\s*NPU_REG_CMD\s*,\s*0x0*C\s*\)"
        r"|write_reg\s*\(\s*NPU_REG_CMD\s*,\s*0x0*0C\s*\)"
        r"|write_reg\s*\(\s*NPU_REG_CMD\s*,\s*0x0{0,7}C\s*\)",
        source_text)
    if len(hits) != 1:
        raise GateError("vendor source contains %d terminal CMD=0xC writes, "
                        "expected exactly 1" % len(hits))


def npu_cmd_address(vendor_source_text, interface_header_text):
    """Read the two constants out of the vendor sources rather than restating
    them: a moved register would otherwise read as 'no CMD access anywhere'."""
    base = re.findall(r"^\s*#define\s+U85_BASE_ADDRESS\s+(0x[0-9A-Fa-f]+)\s*$",
                      vendor_source_text, re.M)
    off = re.findall(r"^\s*#define\s+NPU_REG_CMD\s+(0x[0-9A-Fa-f]+)\s*$",
                     interface_header_text, re.M)
    if len(base) != 1:
        raise GateError("U85_BASE_ADDRESS: expected 1 definition, found %d"
                        % len(base))
    if len(off) != 1:
        raise GateError("NPU_REG_CMD: expected 1 definition, found %d" % len(off))
    return int(base[0], 16) + int(off[0], 16)


def parse_relocations(text):
    printf = puts = 0
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 3 or not cols[1].startswith("R_"):
            continue
        symbol = cols[2]
        if symbol == "printf":
            printf += 1
        elif symbol in ("puts", "_puts", "iprintf"):
            puts += 1
    return printf, puts


def parse_nm(nm_text):
    """nm text -> {name: address}. Undefined/absolute entries carry no address
    and are recorded as None so a name can still be tested for presence."""
    symbols = {}
    for line in nm_text.splitlines():
        cols = line.split()
        if not cols:
            continue
        if len(cols) >= 3:
            try:
                symbols[cols[-1]] = int(cols[0], 16)
                continue
            except ValueError:
                pass
        symbols[cols[-1]] = None
    return symbols


def check_symbols(nm_text, mode):
    names = set(parse_nm(nm_text))
    if WRAP_PRINTF_SYMBOL not in names:
        raise GateError(
            "%s is absent from the final ELF: the wrapper was inlined or "
            "garbage-collected, so no call/symbol boundary can be proven"
            % WRAP_PRINTF_SYMBOL)
    if CALLER_SYMBOL not in names:
        raise GateError("caller symbol %s is absent from the final ELF"
                        % CALLER_SYMBOL)
    if mode == "Q1" and HOOK_SYMBOL not in names:
        raise GateError("%s is absent from the Q1 ELF: the noinline hook must "
                        "survive as its own symbol" % HOOK_SYMBOL)
    if mode == "Q0" and HOOK_SYMBOL in names:
        raise GateError("%s is present in the Q0 ELF; the baseline image must "
                        "carry no hook side effect at all" % HOOK_SYMBOL)


def _regs_header_offset(cfg_header_text, name):
    hits = re.findall(r"^\s*#define\s+%s\s+(0x[0-9A-Fa-f]+)U?\s*$" % name,
                      cfg_header_text, re.M)
    if len(hits) != 1:
        raise GateError("%s: expected 1 definition in the generated register "
                        "header, found %d" % (name, len(hits)))
    return int(hits[0], 16)


def _normalize_text(ins):
    """Instruction text with link-dependent detail removed, so two builds of
    the same source at different addresses compare equal."""
    text = re.sub(r"\b[0-9a-fA-F]{6,16}\b", "<addr>", ins.text)
    text = re.sub(r"\[pc[^\]]*\]", "[pc]", text)
    text = re.sub(r"[@;].*$", "", text)
    return " ".join(text.split())


def check_pre_release_snapshot(hook, pool, cycles, disable, reg_offsets):
    """The inlined internal_pre_release snapshot, proven in full.

    Attesting only the cycle read would license an image whose snapshot
    captured cycle_lo/hi and nothing else, while the host classifier went on
    to judge pre/internal armed, global-enable, CFG-zero and overflow terms
    from fields no instruction ever produced. So all four register reads are
    required, in capture order, with every argument derived from the
    generated header.

    Extra pmu_reg_read calls in the same window are rejected too: a fifth read
    means the compiled snapshot is not the one this contract describes.
    """
    expected = [reg_offsets[name] for name in PRE_RELEASE_SNAPSHOT_REGS]
    reads = [(n, ins) for n, ins in enumerate(hook.insns)
             if cycles < n < disable and ins.kind == "call"
             and ins.callee == PMU_REG_READ_SYMBOL]
    if len(reads) != len(expected):
        raise GateError(
            "in <%s> there are %d direct <%s> call(s) between the cycle read "
            "and the PMU disable, expected exactly %d -- the inlined "
            "internal_pre_release snapshot reads %s"
            % (HOOK_SYMBOL, len(reads), PMU_REG_READ_SYMBOL, len(expected),
               ", ".join(PRE_RELEASE_SNAPSHOT_REGS)))
    observed = [resolve_register(hook, n, "r0", pool) for n, _ in reads]
    if observed != expected:
        raise GateError(
            "in <%s> the internal_pre_release snapshot reads %s, expected %s "
            "in capture order (%s)"
            % (HOOK_SYMBOL,
               ", ".join("unprovable" if v is None else "0x%04X" % v
                         for v in observed),
               ", ".join("0x%04X" % v for v in expected),
               ", ".join(PRE_RELEASE_SNAPSHOT_REGS)))
    return [ins.addr for _, ins in reads]


def expected_hook_calls():
    """The hook's complete direct-call sequence, flattened.

    The per-operation terms each police one call in isolation, which leaves
    room for calls nobody is looking at: an unrelated call between the cycle
    read and the snapshot reads sits outside every window they inspect, and a
    second PMCR read after the capture is invisible to a readback search that
    stops at its first match. Pinning the WHOLE sequence closes that: these
    calls, in this order, and no others.
    """
    calls = [CYCLE_READ_SYMBOL]
    calls += [PMU_REG_READ_SYMBOL] * len(PRE_RELEASE_SNAPSHOT_REGS)
    calls += [PMU_DISABLE_SYMBOL, PMU_REG_READ_SYMBOL,
              POST_DISABLE_CAPTURE_SYMBOL]
    return calls


def check_hook_call_sequence(hook):
    observed = [ins.callee for ins in hook.insns if ins.kind == "call"]
    expected = expected_hook_calls()
    if observed != expected:
        raise GateError(
            "in <%s> the direct call sequence is [%s], expected exactly [%s] "
            "-- the hook makes these calls, in this order, and no others"
            % (HOOK_SYMBOL, ", ".join(observed) or "none", ", ".join(expected)))


def _register_list(operands):
    hit = _REGLIST.search(operands)
    if not hit:
        return set()
    return {tok.strip() for tok in hit.group(1).split(",") if tok.strip()}


def _is_return_form(ins):
    """True only for instructions that actually END the function: `bx lr`, or
    a stack pop that writes pc. `pop {r4, r5}` restores a register and falls
    through, which is not the same thing and is not accepted."""
    mnem = ins.mnemonic.split(".")[0]
    if mnem == "bx":
        return ins.operands.strip() == "lr"
    if mnem == "pop":
        return "pc" in _register_list(ins.operands)
    if mnem in _RETURN_STACK_POPS:
        base = ins.operands.split(",", 1)[0].strip().rstrip("!").strip()
        return base == "sp" and "pc" in _register_list(ins.operands)
    return False


def _mnemonic(ins):
    return (ins.mnemonic if ins.mnemonic.startswith(".")
            else ins.mnemonic.split(".")[0])


def check_latch_is_last(hook, latch):
    """Nothing with an effect may outlive the validity latch.

    The record's exit timestamp and MMIO deltas are written before it in the
    source; requiring the latch to be the last side-effecting instruction is
    what proves the compiler did not sink either of them past it. A record
    that latched valid while a later store was still pending would describe a
    hook state that never existed.

    The tail is checked as a GRAMMAR, not as a per-instruction filter:

        nop*  <exactly one return>  <data directive>*

    Filtering instruction by instruction accepts each of these individually
    while the sequence as a whole is wrong: a tail with no return at all (the
    hook falls through into whatever follows), literal data reached before the
    return, a second return, or an executable instruction sitting past the
    return. Each is rejected by name below.

    Returns the address of the single return instruction.
    """
    returned = None
    for n in range(latch + 1, len(hook.insns)):
        ins = hook.insns[n]
        if ins.kind == "call":
            raise GateError(
                "in <%s> a call to <%s> at 0x%08x follows the validity latch; "
                "the latch must be the LAST side-effecting operation"
                % (HOOK_SYMBOL, ins.callee, ins.addr))
        if ins.kind == "store":
            raise GateError(
                "in <%s> a store at 0x%08x follows the validity latch; the "
                "latch must be the LAST side-effecting operation"
                % (HOOK_SYMBOL, ins.addr))

        mnem = _mnemonic(ins)
        is_data = mnem in DATA_DIRECTIVES

        if returned is None:
            if _is_return_form(ins):
                returned = n
            elif mnem == "nop":
                continue
            elif is_data:
                # Literal data reached before any return means control never
                # left the function here -- it would fall through INTO the
                # pool. Whatever the intent, the latch is not the last thing
                # that happens.
                raise GateError(
                    "in <%s> literal data at 0x%08x appears before <%s> has "
                    "returned; after the validity latch the tail must be "
                    "optional nops, exactly one return, then data only"
                    % (HOOK_SYMBOL, ins.addr, HOOK_SYMBOL))
            else:
                raise GateError(
                    "in <%s> the instruction %r at 0x%08x follows the validity "
                    "latch; only literal data, nop and a true return (bx lr, "
                    "or a pop/ldmia from sp that writes pc) may outlive it"
                    % (HOOK_SYMBOL, ins.text, ins.addr))
        elif not is_data:
            # Past the return only the literal pool may follow. A second
            # return means there is a reachable path this gate has not
            # examined; anything else executable is simply unreachable-or-not
            # and cannot be proven either way.
            if _is_return_form(ins):
                raise GateError(
                    "in <%s> the tail returns a second time at 0x%08x; exactly "
                    "one return may follow the validity latch"
                    % (HOOK_SYMBOL, ins.addr))
            raise GateError(
                "in <%s> the executable instruction %r at 0x%08x follows the "
                "return at 0x%08x; only literal-pool data may sit past it"
                % (HOOK_SYMBOL, ins.text, ins.addr, hook.insns[returned].addr))

    if returned is None:
        raise GateError(
            "in <%s> nothing after the validity latch returns; the hook never "
            "returns, so the latch cannot be its last operation" % HOOK_SYMBOL)
    return hook.insns[returned].addr


def check_hook_structure(funcs, pool, symbols, mode, reg_offsets):
    """Prove the Q1 hook's ORDER in the final ELF, not just its existence.

    A surviving symbol says the hook was not inlined away. It says nothing
    about whether the wrapper reaches it, nor whether the operations inside
    happen in the order the whole measurement depends on. Both are checked
    here against the linked instruction stream.

    Two shapes are deliberately NOT required to be calls:

      - the internal_pre_release capture is inlined by the compiler, so it is
        attested by its own `npu_pmu_read_cycles` call instead. That is the
        stronger evidence anyway: it proves the CYCLE READ -- the actual end of
        the measured window -- happens before the disable, which a wrapper call
        would only imply.
      - the PMCR readback is a pmu_reg_read call whose argument is checked
        against the generated header, not a dedicated helper.

    If a future compiler also inlines pmu_diag_capture_pre_order, the counts
    below stop being provable and the gate fails closed rather than guessing.
    Absolute addresses are read from nm; none are written down here.
    """
    hook_present = HOOK_SYMBOL in funcs
    if mode == "Q0":
        # Q0 must carry no side effect at all: not the hook, and not a call to
        # it from anywhere (a call to an absent symbol would not link, but a
        # stray alias would).
        if hook_present:
            raise GateError("the Q0 ELF defines <%s>" % HOOK_SYMBOL)
        callers = [fn.name for fn in funcs.values()
                   for ins in fn.insns
                   if ins.kind == "call" and ins.callee == HOOK_SYMBOL]
        if callers:
            raise GateError("the Q0 ELF calls <%s> from %s"
                            % (HOOK_SYMBOL, ", ".join(sorted(set(callers)))))
        return {}

    wrapper = funcs.get(WRAP_PRINTF_SYMBOL)
    if wrapper is None:
        raise GateError("<%s> has no body in the final ELF" % WRAP_PRINTF_SYMBOL)
    hook_calls = [ins for ins in wrapper.insns
                  if ins.kind == "call" and ins.callee == HOOK_SYMBOL]
    if len(hook_calls) != 1:
        raise GateError(
            "<%s> makes %d direct call(s) to <%s>, expected exactly 1"
            % (WRAP_PRINTF_SYMBOL, len(hook_calls), HOOK_SYMBOL))

    hook = funcs.get(HOOK_SYMBOL)
    if hook is None:
        raise GateError("<%s> has no body in the final ELF" % HOOK_SYMBOL)

    def sole_call(callee):
        hits = [n for n, ins in enumerate(hook.insns)
                if ins.kind == "call" and ins.callee == callee]
        if len(hits) != 1:
            raise GateError(
                "<%s> makes %d direct call(s) to <%s>, expected exactly 1"
                % (HOOK_SYMBOL, len(hits), callee))
        return hits[0]

    cycles = sole_call(CYCLE_READ_SYMBOL)
    disable = sole_call(PMU_DISABLE_SYMBOL)
    post_capture = sole_call(POST_DISABLE_CAPTURE_SYMBOL)

    if not cycles < disable:
        raise GateError(
            "in <%s> the internal_pre_release cycle read (0x%08x) does not "
            "precede the PMU disable (0x%08x); the measured window would end "
            "after the counter was stopped"
            % (HOOK_SYMBOL, hook.insns[cycles].addr, hook.insns[disable].addr))

    snapshot = check_pre_release_snapshot(hook, pool, cycles, disable,
                                          reg_offsets)

    dsb = next((n for n in range(disable + 1, len(hook.insns))
                if hook.insns[n].mnemonic.split(".")[0] == "dsb"), None)
    if dsb is None:
        raise GateError(
            "in <%s> no DSB follows the PMU disable at 0x%08x; the disable "
            "must be ordered before its acknowledgement is read"
            % (HOOK_SYMBOL, hook.insns[disable].addr))

    readback = None
    for n in range(dsb + 1, len(hook.insns)):
        ins = hook.insns[n]
        if ins.kind != "call" or ins.callee != PMU_REG_READ_SYMBOL:
            continue
        if resolve_register(hook, n, "r0", pool) == reg_offsets["NPU_REG_PMCR"]:
            readback = n
            break
    if readback is None:
        raise GateError(
            "in <%s> no <%s> of PMCR (offset 0x%04X) follows the DSB at "
            "0x%08x; the disable acknowledgement is unproven"
            % (HOOK_SYMBOL, PMU_REG_READ_SYMBOL, reg_offsets["NPU_REG_PMCR"],
               hook.insns[dsb].addr))

    if not readback < post_capture:
        raise GateError(
            "in <%s> the internal_post_disable capture (0x%08x) does not "
            "follow the PMCR readback (0x%08x)"
            % (HOOK_SYMBOL, hook.insns[post_capture].addr,
               hook.insns[readback].addr))

    latch_addr = symbols.get(LATCH_SYMBOL)
    if latch_addr is None:
        raise GateError(
            "<%s> has no address in nm, so the validity latch cannot be "
            "located in the instruction stream" % LATCH_SYMBOL)
    latch = None
    for n, ins in enumerate(hook.insns):
        if ins.kind != "store" or store_address(hook, n, pool) != latch_addr:
            continue
        if resolve_register(hook, n, ins.src, pool) != 1:
            raise GateError(
                "in <%s> the store to <%s> at 0x%08x does not write a provable 1"
                % (HOOK_SYMBOL, LATCH_SYMBOL, ins.addr))
        if latch is not None:
            raise GateError("in <%s> <%s> is latched more than once"
                            % (HOOK_SYMBOL, LATCH_SYMBOL))
        latch = n
    if latch is None:
        raise GateError(
            "in <%s> nothing stores to <%s>; the validity latch is what makes "
            "a partial hook distinguishable from a complete one"
            % (HOOK_SYMBOL, LATCH_SYMBOL))
    if latch < post_capture:
        raise GateError(
            "in <%s> <%s> is latched at 0x%08x, BEFORE the ordered hook "
            "operations complete (internal_post_disable capture at 0x%08x); a "
            "hook cut short would present as a complete one"
            % (HOOK_SYMBOL, LATCH_SYMBOL, hook.insns[latch].addr,
               hook.insns[post_capture].addr))

    # Order matters only for which message a reader gets first. The specific
    # terms run before this catch-all so a post-latch call is reported as a
    # latch violation rather than as a sequence mismatch; this one then catches
    # whatever none of them was looking at.
    return_addr = check_latch_is_last(hook, latch)
    check_hook_call_sequence(hook)

    ordered = [("wrapper_call", hook_calls[0].addr),
               ("internal_pre_release_cycle_read", hook.insns[cycles].addr)]
    ordered += [("pre_release_%s_address"
                 % name[len("NPU_REG_"):].lower(), addr)
                for name, addr in zip(PRE_RELEASE_SNAPSHOT_REGS, snapshot)]
    ordered += [("pmu_disable", hook.insns[disable].addr),
                ("dsb", hook.insns[dsb].addr),
                ("pmcr_readback", hook.insns[readback].addr),
                ("internal_post_disable_capture", hook.insns[post_capture].addr),
                ("snapshot_valid_latch", hook.insns[latch].addr),
                ("latch_is_final", hook.insns[latch].addr),
                ("return", return_addr)]

    # The digest covers the attested term NAMES *and* the address-normalized
    # instruction slice up to and including the latch. Names alone would
    # digest identically across materially different instruction streams that
    # happened to satisfy the same terms, which is exactly the property a
    # provenance digest must not have. Normalizing addresses keeps it stable
    # across links of the same source.
    body = [_normalize_text(ins) for ins in hook.insns[:latch + 1]]
    digest = hashlib.sha256(
        "\n".join([name for name, _ in ordered] + ["--"] + body).encode()
    ).hexdigest()

    evidence = {"hook_order_sha256": digest, "hook_address": hook.addr}
    for name, addr in ordered:
        if name == "latch_is_final":
            continue
        key = ("hook_%s" % name if name.endswith("_address")
               else "hook_%s_address" % name)
        evidence[key] = addr
    return evidence


def check_no_cfg_write(preprocessed_text, cfg_header_text):
    offset = _regs_header_offset(cfg_header_text, "NPU_REG_PMCCNTR_CFG")
    pattern = r"pmu_reg_write\s*\(\s*0x0*%X[Uu]?\s*," % offset
    found = len(re.findall(pattern, preprocessed_text))
    if found:
        raise GateError("the preprocessed translation unit contains %d "
                        "PMCCNTR_CFG write(s); schema v8 writes none" % found)


def check_compiler_flags(flags):
    if "-fno-builtin-printf" not in flags:
        raise GateError("compiler flags omit -fno-builtin-printf, so printf "
                        "may be lowered to puts: %s" % flags)
    if re.search(r"(^|\s)-f(no-)?lto\b", flags) and "-fno-lto" not in flags:
        raise GateError("LTO is enabled; the callsite may be moved or erased "
                        "across translation units: %s" % flags)


# ---------------------------------------------------------------------------
# Whole-gate evaluation
# ---------------------------------------------------------------------------

def evaluate(mode, disassembly_text, nm_text, strings_text, relocation_text,
             object_disassembly_text, object_sections_text,
             vendor_source_text, interface_header_text, compiler_flags,
             preprocessed_text, cfg_header_text):
    """Prove every design term or raise. Returns the extracted callsite facts."""
    if mode not in MODES:
        raise GateError("unknown qualification mode %r, expected one of %s"
                        % (mode, ", ".join(MODES)))

    test_cpm = check_test_cpm(vendor_source_text)
    check_single_terminal_release(vendor_source_text)
    check_compiler_flags(compiler_flags)
    check_no_cfg_write(preprocessed_text, cfg_header_text)
    check_symbols(nm_text, mode)
    reg_offsets = {name: _regs_header_offset(cfg_header_text, name)
                   for name in REGS_HEADER_OFFSETS}

    # Totals first, but ONLY the puts term is a gate here: a puts relocation
    # anywhere in this object means some printf was folded, which -fno-builtin
    # -printf is supposed to prevent. The printf total stays informational.
    printf_relocs, puts_relocs = parse_relocations(relocation_text)
    if puts_relocs:
        raise GateError("the vendor object carries %d puts-family relocation(s); "
                        "no printf in it may be folded" % puts_relocs)

    # The load-bearing object term: the TARGET call's own relocation.
    object_evidence = check_object_target_relocation(
        parse_disassembly(object_disassembly_text),
        parse_section_dumps(object_sections_text))

    cmd_addr = npu_cmd_address(vendor_source_text, interface_header_text)
    funcs = parse_disassembly(disassembly_text).functions
    pool = literal_pool(funcs)
    data = parse_section_dump(strings_text)

    hits = find_target_callsites(funcs, pool, data)
    if len(hits) != 1:
        raise GateError(
            "expected exactly 1 target callsite whose first argument is the "
            "complete target string, found %d%s"
            % (len(hits),
               " (in %s)" % ", ".join("<%s>" % f.name for f, _ in hits)
               if hits else ""))
    fn, index = hits[0]
    if fn.name != CALLER_SYMBOL:
        raise GateError("the target callsite is in caller <%s>, expected <%s>"
                        % (fn.name, CALLER_SYMBOL))

    callee = fn.insns[index].callee
    if callee != WRAP_PRINTF_SYMBOL:
        raise GateError("the target call resolves to <%s>, expected <%s>"
                        % (callee, WRAP_PRINTF_SYMBOL))

    stop_addr = check_stop_precedes(fn, index, pool, cmd_addr)
    return_addr, release_addr, release_index, release_imm = check_release_tail(
        fn, index, pool, cmd_addr)
    hook_evidence = check_hook_structure(funcs, pool, parse_nm(nm_text), mode,
                                         reg_offsets)
    stop_index = next(n for n, i in enumerate(fn.insns) if i.addr == stop_addr)
    digest, body = normalized_digest(fn, stop_index, release_index)

    result = {
        "ok": True,
        "qualification_mode": mode,
        "caller_symbol": fn.name,
        "target_callsite_count": len(hits),
        "target_call_address": fn.insns[index].addr,
        "expected_return_address": return_addr,
        "release_store_address": release_addr,
        "release_immediate_address": release_imm[0],
        "release_immediate_value": release_imm[1],
        "stop_store_address": stop_addr,
        "npu_cmd_address": cmd_addr,
        "callsite_disassembly_sha256": digest,
        "callsite_disassembly": body,
        "test_cpm": test_cpm,
        "printf_relocations": printf_relocs,
        "puts_relocations": puts_relocs,
    }
    result.update(object_evidence)
    result.update(hook_evidence)
    return result


def manifest_document(result, build_id, vendor_source_sha256,
                      vendor_object_sha256, compiler_flags, artifacts):
    """The machine-readable build manifest. build_id is a HEX STRING because
    JSON has no unsigned 32-bit type and the host parses it with base 16; every
    address is numeric because the host compares it to a raw record field."""
    doc = {
        "schema_version": 8,
        "qualification_mode": result["qualification_mode"],
        "build_id": "0x%08X" % build_id,
        "vendor_source_sha256": vendor_source_sha256,
        "vendor_object_sha256": vendor_object_sha256,
        "caller_symbol": result["caller_symbol"],
        "expected_return_address": result["expected_return_address"],
        "release_store_address": result["release_store_address"],
        # Provenance of the release constant, not just its value: an immediate
        # established after the return, at this address.
        "release_immediate_address": result["release_immediate_address"],
        "release_immediate_value": result["release_immediate_value"],
        "stop_store_address": result["stop_store_address"],
        "target_call_address": result["target_call_address"],
        "callsite_disassembly_sha256": result["callsite_disassembly_sha256"],
        "test_cpm": result["test_cpm"],
        # The object-level target evidence: which call, in which section of
        # which caller, bound to which relocation. This is what a reviewer
        # re-derives by hand to confirm the gate was not merely agreeing with
        # itself.
        "object_caller_symbol": result["object_caller_symbol"],
        "object_section": result["object_section"],
        "object_target_call_offset": result["object_target_call_offset"],
        "object_target_relocation_type": result["object_target_relocation_type"],
        "object_target_relocation_symbol":
            result["object_target_relocation_symbol"],
        "object_target_literal_offset": result["object_target_literal_offset"],
        "object_target_string_section": result["object_target_string_section"],
        "object_target_string_offset": result["object_target_string_offset"],
        # Totals, informational only. Not pinned: they move with unrelated
        # diagnostic printf edits in the vendor file.
        "printf_relocations": result["printf_relocations"],
        "puts_relocations": result["puts_relocations"],
        "compiler_flags": compiler_flags,
        "artifact_sha256": dict(artifacts),
    }
    # Q1 only: the hook's ordered operation addresses and an
    # address-normalized digest of that order. Q0 has no hook by contract, so
    # the keys are simply absent rather than present-and-null.
    doc.update((k, v) for k, v in result.items()
               if k.startswith("hook_") and k != "hook_symbol")
    return doc


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--vendor-source", required=True)
    ap.add_argument("--interface-header", required=True)
    ap.add_argument("--vendor-object", required=True)
    ap.add_argument("--regs-header", required=True)
    ap.add_argument("--preprocessed", required=True)
    ap.add_argument("--elf", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--app-bin", required=True)
    ap.add_argument("--vectors-bin", required=True)
    ap.add_argument("--ddr-bin", required=True)
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--nm", required=True)
    ap.add_argument("--readelf", required=True)
    ap.add_argument("--cflags", required=True)
    ap.add_argument("--manifest-out", required=True)
    a = ap.parse_args()

    vendor_source = open(a.vendor_source, newline=None).read()
    interface_header = open(a.interface_header, newline=None).read()
    regs_header = open(a.regs_header, newline=None).read()
    preprocessed = open(a.preprocessed, newline=None).read()

    # readelf proves the ELF is the object file kind claimed before anything
    # else reads it; a truncated or wrong-format file otherwise shows up as an
    # empty disassembly, which must never read as "no violations found".
    header = _run([a.readelf, "-h", a.elf])
    if "Executable" not in header and "EXEC" not in header:
        raise GateError("%s is not an executable ELF" % a.elf)

    try:
        result = evaluate(
            mode=a.mode,
            disassembly_text=_run([a.objdump, "-d", a.elf]),
            nm_text=_run([a.nm, a.elf]),
            strings_text=_run([a.objdump, "-s", a.elf]),
            relocation_text=_run([a.objdump, "-r", a.vendor_object]),
            # -z disables objdump's "..." run-compression of zero words. Without
            # it a literal slot whose addend happens to be 0 -- a string at the
            # very start of its rodata section -- would have no .word line at
            # all, and the target would silently fail to resolve.
            object_disassembly_text=_run([
                a.objdump, "-drz", "--section=" + OBJECT_TEXT_SECTION,
                a.vendor_object]),
            object_sections_text=_run([a.objdump, "-s", a.vendor_object]),
            vendor_source_text=vendor_source,
            interface_header_text=interface_header,
            compiler_flags=a.cflags,
            preprocessed_text=preprocessed,
            cfg_header_text=regs_header,
        )
    except GateError as exc:
        print("FAIL %s" % exc)
        sys.exit(1)

    manifest = manifest_document(
        result,
        build_id=int(a.build_id, 16),
        vendor_source_sha256=_sha256(a.vendor_source),
        vendor_object_sha256=_sha256(a.vendor_object),
        compiler_flags=a.cflags,
        artifacts={
            "APP.BIN": _sha256(a.app_bin),
            "VECTORS.BIN": _sha256(a.vectors_bin),
            "DDR.BIN": _sha256(a.ddr_bin),
            "elf": _sha256(a.elf),
            "map": _sha256(a.map),
        },
    )
    with open(a.manifest_out, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print("  PASS TEST_CPM=%d, exactly one vendor terminal release"
          % result["test_cpm"])
    print("  PASS object target call <%s>+0x%x -> %s against %r "
          "(literal +0x%x -> %s+0x%x)"
          % (result["object_caller_symbol"], result["object_target_call_offset"],
             result["object_target_relocation_type"],
             result["object_target_relocation_symbol"],
             result["object_target_literal_offset"],
             result["object_target_string_section"],
             result["object_target_string_offset"]))
    print("  PASS unique target callsite in <%s>, resolves to <%s>"
          % (result["caller_symbol"], WRAP_PRINTF_SYMBOL))
    print("  PASS STOP 0x%08x -> target call 0x%08x -> return 0x%08x -> "
          "immediate #%d 0x%08x -> release 0x%08x, nothing in between"
          % (result["stop_store_address"], result["target_call_address"],
             result["expected_return_address"], result["release_immediate_value"],
             result["release_immediate_address"], result["release_store_address"]))
    if a.mode == "Q1":
        print("  PASS hook order: wrapper 0x%08x -> cycle read 0x%08x -> "
              "disable 0x%08x -> dsb 0x%08x -> PMCR readback 0x%08x -> "
              "post-disable capture 0x%08x -> latch 0x%08x (last)"
              % (result["hook_wrapper_call_address"],
                 result["hook_internal_pre_release_cycle_read_address"],
                 result["hook_pmu_disable_address"],
                 result["hook_dsb_address"],
                 result["hook_pmcr_readback_address"],
                 result["hook_internal_post_disable_capture_address"],
                 result["hook_snapshot_valid_latch_address"]))
        print("  PASS internal_pre_release snapshot: %s"
              % ", ".join(
                  "%s 0x%08x" % (name[len("NPU_REG_"):],
                                 result["hook_pre_release_%s_address"
                                        % name[len("NPU_REG_"):].lower()])
                  for name in PRE_RELEASE_SNAPSHOT_REGS))
    else:
        print("  PASS Q0 carries no <%s> definition and no call to it"
              % HOOK_SYMBOL)
    print("  PASS no PMCCNTR_CFG write, -fno-builtin-printf set, no LTO")
    print("  PASS callsite digest %s" % result["callsite_disassembly_sha256"])
    # Deliberately labelled: the TARGET relocation printed above is gated, the
    # whole-object totals below are not. Reading these as the printf gate is
    # the mistake this wording exists to prevent.
    print("  INFO whole-object relocation totals, NOT pinned: printf=%d, "
          "puts=%d (the gated printf term is the target call above)"
          % (result["printf_relocations"], result["puts_relocations"]))
    print("PASS %s qualification callsite manifest -> %s" % (a.mode, a.manifest_out))


if __name__ == "__main__":
    main()
