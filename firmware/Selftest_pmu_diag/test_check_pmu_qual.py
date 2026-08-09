"""Unit fixtures for the schema-v8 Q0/Q1 final-ELF qualification gate.

No toolchain and no board required. Every fixture is synthetic objdump / nm /
readelf text, so each of the gate's ten callsite terms can be invalidated one
at a time and observed to fail CLOSED.

The load-bearing idea under test is how the unique target callsite is counted.
The gate does NOT count occurrences of the target byte sequence: the runner's
own matcher, any diagnostic string table and the rodata copy would all inflate
that number. It follows the caller's literal-pool load, reconstructs the FIRST
ARGUMENT of each printf-family call, and counts the calls whose first argument
IS the complete target string.

That reconstruction is applied at BOTH levels, and they answer different
questions:

  * in the RELOCATABLE vendor object, it identifies the target call and then
    requires THAT CALL's own relocation to be an R_ARM_*_CALL against exactly
    `printf`. This is the term that proves the vendor call was not lowered to
    puts/iprintf or folded to a builtin before the link ever happened.
  * in the FINAL ELF, it requires the same logical call to resolve to
    `__wrap_printf` and to sit in the STOP -> call -> return -> CMD=0xC tail.

Neither total relocation COUNT is a pass/fail term: `printf_relocations` is
informational and is deliberately not pinned, because it tracks unrelated
diagnostic printf edits in the vendor file. What is pinned is the relocation
belonging to the target call itself.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_pmu_qual as gate

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def expect_fail(name, fn, needle=""):
    """A gate term is only useful if it REFUSES. Anything other than a
    GateError -- including silently passing -- is a failure of the gate."""
    global passed, failed
    try:
        fn()
    except gate.GateError as exc:
        ok = needle in str(exc)
        check(name, ok, "" if ok else "wrong reason: %s" % exc)
        return
    check(name, False, "gate did not refuse")


# ---------------------------------------------------------------------------
# Synthetic artifact builders
# ---------------------------------------------------------------------------

NPU_BASE = 0x50004000
CMD_OFF = 0x08
CMD_ADDR = NPU_BASE + CMD_OFF
TARGET = "Testing CPM signals\n"
TEXT_BASE = 0x31000000
STR_TARGET = 0x3100241C
STR_OTHER = 0x31002290

REGS = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "ip", "lr")


class Builder:
    """Emits objdump -d text from high-level ops, allocating a literal pool at
    the end of each function exactly as the real compiler output does."""

    def __init__(self, base=TEXT_BASE):
        self.base = base
        self.funcs = []

    def func(self, name, ops):
        self.funcs.append((name, list(ops)))
        return self

    def render(self):
        out = []
        addr = self.base
        for name, ops in self.funcs:
            body = []
            pool = []
            # Two passes: the pool address is only known once the body length
            # is, and the body references it, exactly like the real tool.
            body_len = 0
            for op in ops:
                body_len += 4 if op[0] in ("bl", "ldr_lit") else 2
            pool_addr = (addr + body_len + 3) & ~3
            cur = addr
            for op in ops:
                kind = op[0]
                if kind == "ldr_lit":
                    _, reg, value = op
                    slot = pool_addr + 4 * len(pool)
                    pool.append(value)
                    body.append((cur, "ldr", "%s, [pc, #%d]" % (reg, slot - cur - 4),
                                 "@ (%08x <%s+0x%x>)" % (slot, name, slot - addr)))
                    cur += 4
                elif kind == "mov":
                    _, reg, imm = op
                    body.append((cur, "movs", "%s, #%d" % (reg, imm), ""))
                    cur += 2
                elif kind == "mov_reg":
                    _, dst, src = op
                    body.append((cur, "mov", "%s, %s" % (dst, src), ""))
                    cur += 2
                elif kind == "str":
                    _, src, base_reg, off = op
                    body.append((cur, "str", "%s, [%s, #%d]" % (src, base_reg, off), ""))
                    cur += 2
                elif kind == "bl":
                    _, sym, sym_addr = op
                    body.append((cur, "bl", "%08x <%s>" % (sym_addr, sym), ""))
                    cur += 4
                elif kind == "raw":
                    _, mnem, operands = op
                    body.append((cur, mnem, operands, ""))
                    cur += 2
                else:
                    raise AssertionError("unknown op %r" % (op,))
            out.append("%08x <%s>:" % (addr, name))
            for a, mnem, operands, comment in body:
                line = "%8x:\t0000      \t%s\t%s" % (a, mnem, operands)
                if comment:
                    line += "\t" + comment
                out.append(line)
            for n, value in enumerate(pool):
                out.append("%8x:\t%08x \t.word\t0x%08x"
                           % (pool_addr + 4 * n, value, value))
            out.append("")
            addr = pool_addr + 4 * len(pool) + 0x40
        return "\n".join(out) + "\n"


def release_tail(callee="__wrap_printf", callee_addr=0x31001DDC,
                 string_addr=STR_TARGET, extra_between=(), release=0x0C,
                 release_first=False, stop_value=0):
    """The vendor release tail: STOP -> target call -> mov #12 -> release."""
    tail = [
        ("ldr_lit", "r5", NPU_BASE),
        ("mov", "r3", stop_value),
        ("str", "r3", "r5", CMD_OFF),
        ("ldr_lit", "r0", string_addr),
        ("bl", callee, callee_addr),
    ]
    tail += list(extra_between)
    tail += [
        ("mov", "r3", release),
        ("str", "r3", "r5", CMD_OFF),
    ]
    if release_first:
        tail = [
            ("ldr_lit", "r5", NPU_BASE),
            ("mov", "r3", release),
            ("str", "r3", "r5", CMD_OFF),
            ("mov", "r3", stop_value),
            ("str", "r3", "r5", CMD_OFF),
            ("ldr_lit", "r0", string_addr),
            ("bl", callee, callee_addr),
        ]
    return tail


def prologue():
    """Ordinary caller body before the release tail, including one non-target
    printf, so the gate is proven to discriminate rather than to match the
    first call it sees."""
    return [
        ("raw", "push", "{r3, lr}"),
        ("ldr_lit", "r0", STR_OTHER),
        ("bl", "__wrap_printf", 0x31001DDC),
    ]


# ---------------------------------------------------------------------------
# Final-ELF hook shape
#
# The internal_pre_release capture is INLINED by the real compiler, so it is
# attested through its own npu_pmu_read_cycles call rather than a wrapper
# symbol; the fixture reproduces that shape rather than an idealised one.
# ---------------------------------------------------------------------------

LATCH_ADDR = 0x31004CFC
PMCR_OFF = 0x1180
HOOK_ADDR = 0x31001034
SYMS = {"npu_pmu_read_cycles": 0x310008D4, "npu_pmu_disable": 0x310008BC,
        "pmu_reg_read": 0x31000854, "pmu_diag_capture_pre_order": 0x31000BC4,
        "pmu_qual_pre_release_hook": HOOK_ADDR}


def snapshot_reads(offsets):
    """The inlined pmu_diag_capture_post_order tail: one pmu_reg_read per
    register, in capture order. A None offset produces a read whose argument
    arrives by register move, i.e. one the gate cannot prove."""
    ops = []
    for off in offsets:
        ops.append(("mov_reg", "r0", "r6") if off is None
                   else ("mov", "r0", off))
        ops.append(("bl", "pmu_reg_read", SYMS["pmu_reg_read"]))
    return ops


def hook_body(drop_cycles=False, dup_cycles=False, drop_disable=False,
              dup_disable=False, drop_dsb=False, drop_readback=False,
              wrong_readback_reg=False, drop_post=False, dup_post=False,
              latch_first=False, drop_latch=False, latch_value=1,
              disable_before_cycles=False, pre_reads=None,
              store_after_latch=False, call_after_latch=False,
              junk_after_latch=False, pad=False, epilogue=None,
              tail_extra=(), extra_call_after_cycles=False,
              extra_readback=False, swap_readback_and_capture=False,
              latch_via_mov=False):
    """The ordered hook operations, in the shape the real Q1 ELF has."""
    cycles = [("bl", "npu_pmu_read_cycles", SYMS["npu_pmu_read_cycles"])]
    if extra_call_after_cycles:
        # An unrelated call between the cycle read and the snapshot reads. It
        # disturbs none of the windows the per-operation terms inspect, so only
        # the exact call-sequence term can see it.
        cycles += [("bl", "memcpy", 0x31002400)]
    cycles += snapshot_reads(PRE_OFFS if pre_reads is None else pre_reads)
    disable = [("bl", "npu_pmu_disable", SYMS["npu_pmu_disable"])]
    # Materialising the latch address with a move instead of a literal-pool
    # load leaves the hook with NO literal pool at all, which is the only way
    # to build a function whose body simply ends -- the shape that exercises
    # "nothing after the latch returns".
    latch = ([("mov", "r3", LATCH_ADDR)] if latch_via_mov
             else [("ldr_lit", "r3", LATCH_ADDR)])
    latch += [("mov", "r2", latch_value), ("str", "r2", "r3", 0)]

    ops = [("raw", "push", "{r3, lr}")]
    if pad:
        ops += [("raw", "nop", "")]
    if latch_first and not drop_latch:
        ops += latch
    if disable_before_cycles:
        ops += disable + (cycles if not drop_cycles else [])
    else:
        if not drop_cycles:
            ops += cycles
        if dup_cycles:
            ops += cycles
        if not drop_disable:
            ops += disable
    if dup_disable:
        ops += disable
    if not drop_dsb:
        ops += [("raw", "dsb", "sy")]
    readback = [("mov", "r0", 0x99 if wrong_readback_reg else PMCR_OFF),
                ("bl", "pmu_reg_read", SYMS["pmu_reg_read"])]
    capture = [("bl", "pmu_diag_capture_pre_order",
                SYMS["pmu_diag_capture_pre_order"])]
    if swap_readback_and_capture:
        # The capture lands before the readback. Ordering terms already cover
        # this; the fixture records that fact rather than assuming it.
        ops += (capture if not drop_post else []) + (
            readback if not drop_readback else [])
    else:
        if not drop_readback:
            ops += readback
        if not drop_post:
            ops += capture
    if extra_readback:
        # A second PMCR read after the capture. The readback search takes the
        # first match and the snapshot window ends at the disable, so nothing
        # but the exact call sequence notices this one.
        ops += readback
    if dup_post:
        ops += capture
    if not latch_first and not drop_latch:
        ops += latch
    # Anything here runs AFTER the validity latch. The real hook has only its
    # epilogue and literal pool, which is what makes the latch provably the
    # last side-effecting operation.
    if store_after_latch:
        ops += [("ldr_lit", "r4", 0x31004E00), ("mov", "r5", 7),
                ("str", "r5", "r4", 0)]
    if call_after_latch:
        ops += [("bl", "read_timestamp", 0x31000AA0)]
    if junk_after_latch:
        ops += [("raw", "svc", "#0")]
    ops += list(tail_extra)
    # The real Q1 epilogue is a single ldmia.w that pops pc straight off sp.
    return ops + (list(epilogue) if epilogue is not None
                  else [("raw", "pop", "{r3, pc}")])


def wrapper_body(hook_calls=1):
    ops = [("raw", "push", "{r3, lr}")]
    for _ in range(hook_calls):
        ops.append(("bl", "pmu_qual_pre_release_hook", HOOK_ADDR))
    return ops + [("raw", "pop", "{r3, pc}")]


def disassembly(caller="test_u85", tail=None, extra_funcs=(), base=TEXT_BASE,
                mode="Q1", wrapper=None, hook=None, drop_hook=False):
    b = Builder(base)
    b.func(caller, prologue() + (release_tail() if tail is None else tail)
           + [("raw", "pop", "{r3, pc}")])
    b.func("__wrap_printf",
           wrapper if wrapper is not None
           else wrapper_body(1 if mode == "Q1" else 0))
    if mode == "Q1" and not drop_hook:
        b.func("pmu_qual_pre_release_hook",
               hook if hook is not None else hook_body())
    for name, ops in extra_funcs:
        b.func(name, ops)
    return b.render()


def strings_dump(target_addr=STR_TARGET, target=TARGET):
    """objdump -s style hex dump. The gate reads the bytes at the reconstructed
    first-argument address out of THIS, so a pointer that happens to land on a
    prefix of the target cannot pass."""
    blobs = {STR_OTHER: b"Read match at address\n\x00",
             target_addr: target.encode() + b"\x00"}
    lines = ["Contents of section .text:"]
    for addr, data in sorted(blobs.items()):
        data = data + b"\x00" * ((-len(data)) % 16)
        for n in range(0, len(data), 16):
            row = data[n:n + 16]
            words = " ".join(row[i:i + 4].hex() for i in range(0, 16, 4))
            lines.append(" %08x %s  %s" % (addr + n, words, "."* len(row)))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Relocatable vendor object fixtures
#
# Offsets here are arbitrary and are NOT the observed ones: the gate must
# derive the target call, its literal slot and the rodata addend from the
# relocations, never from a remembered address. The real object happens to put
# the target call at test_u85+0x190 with a literal at +0x248 carrying rodata
# addend 0x18c; nothing below reuses those numbers.
# ---------------------------------------------------------------------------

OBJ_SECTION = ".text.test_u85"
OBJ_RODATA = ".rodata.test_u85.str1.4"
OBJ_TARGET_ADDEND = 0x2C
OBJ_OTHER_ADDEND = 0x04


def object_disassembly(section=OBJ_SECTION, caller="test_u85",
                       call_reloc=("R_ARM_THM_CALL", "printf"),
                       literal_section=OBJ_RODATA,
                       literal_addend=OBJ_TARGET_ADDEND,
                       drop_call_reloc=False, drop_literal_reloc=False,
                       duplicate=False):
    """objdump -drz --section=.text.<caller> of the relocatable vendor object.

    Always carries an UNRELATED printf call as well, so a gate that simply
    accepted "some printf relocation exists" would still pass every negative
    below -- which is exactly the fail-open shape being tested against.
    """
    rows = [
        (0x00, "push\t{r4, lr}", None),
        (0x02, "ldr\tr0, [pc, #64]\t@ (44 <%s+0x44>)" % caller, None),
        (0x04, "bl\t0 <printf>", ("R_ARM_THM_CALL", "printf")),
        (0x08, "ldr\tr5, [pc, #72]\t@ (50 <%s+0x50>)" % caller, None),
        (0x0a, "movs\tr3, #0", None),
        (0x0c, "str\tr3, [r5, #8]", None),
        (0x0e, "ldr\tr0, [pc, #56]\t@ (48 <%s+0x48>)" % caller, None),
        (0x10, "bl\t0 <printf>", None if drop_call_reloc else call_reloc),
        (0x14, "movs\tr3, #12", None),
        (0x16, "str\tr3, [r5, #8]", None),
    ]
    if duplicate:
        rows += [
            (0x18, "ldr\tr0, [pc, #44]\t@ (48 <%s+0x48>)" % caller, None),
            (0x1a, "bl\t0 <printf>", ("R_ARM_THM_CALL", "printf")),
        ]
    rows += [
        (0x1e, "pop\t{r4, pc}", None),
        (0x44, ".word\t0x%08x" % OBJ_OTHER_ADDEND,
         ("R_ARM_ABS32", literal_section)),
        (0x48, ".word\t0x%08x" % literal_addend,
         None if drop_literal_reloc else ("R_ARM_ABS32", literal_section)),
        (0x50, ".word\t0x50004000", None),
    ]
    out = ["", "Disassembly of section %s:" % section, "",
           "00000000 <%s>:" % caller]
    for off, text, reloc in rows:
        mnem, _, operands = text.partition("\t")
        out.append("%4x:\t0000      \t%s\t%s" % (off, mnem, operands))
        if reloc:
            out.append("\t\t\t%x: %s\t%s" % (off, reloc[0], reloc[1]))
    return "\n".join(out) + "\n"


def object_sections(target=TARGET, target_addend=OBJ_TARGET_ADDEND,
                    section=OBJ_RODATA):
    """objdump -s of the object. Section-relative offsets restart per section,
    so the gate must key strings by (section, offset) and not by a flat
    address -- an object has no VMAs to be unique about."""
    blobs = {OBJ_OTHER_ADDEND: b"Read match at address\n\x00",
             target_addend: target.encode() + b"\x00"}
    lines = ["Contents of section %s:" % section]
    data = bytearray(b"\x00" * 0x80)
    for off, raw in blobs.items():
        data[off:off + len(raw)] = raw
    for n in range(0, len(data), 16):
        row = bytes(data[n:n + 16])
        words = " ".join(row[i:i + 4].hex() for i in range(0, 16, 4))
        lines.append(" %04x %s  %s" % (n, words, "." * len(row)))
    return "\n".join(lines) + "\n"


NM_Q1 = """\
31001ddc T __wrap_printf
31001034 t pmu_qual_pre_release_hook
31004cfc b pmu_qual_hook_snapshot_valid
310005f8 T test_u85
"""
NM_Q0 = """\
31001ddc T __wrap_printf
310005f8 T test_u85
"""

RELOC_OK = """\
RELOCATION RECORDS FOR [.text.test_commands]:
OFFSET   TYPE              VALUE
00000010 R_ARM_THM_CALL    printf
00000024 R_ARM_THM_CALL    printf
00000040 R_ARM_THM_CALL    memcmp
"""
RELOC_PUTS = RELOC_OK + "00000060 R_ARM_THM_CALL    puts\n"

VENDOR_SRC = """\
#define TEST_CPM 1
#define U85_BASE_ADDRESS 0x50004000
    write_reg(NPU_REG_CMD, 0x00000000);
#if(TEST_CPM==1)
    printf("Testing CPM signals\\n");
    write_reg(NPU_REG_CMD, 0x0000000C);
#endif
"""
IFACE_HDR = "#define NPU_REG_CMD                0x00000008\n"

FLAGS_OK = ("-mcpu=cortex-m85+nomve+nofp -mthumb -std=gnu11 -O1 "
            "-fno-builtin-printf -ffunction-sections")

PREPROC_NO_CFG = "pmu_reg_write(0x0004U, 0x00000001U);\n"
PREPROC_CFG = PREPROC_NO_CFG + "pmu_reg_write(0x1188U, 0x00000011U);\n"
# Offsets here are deliberately NOT all the real ones (the real PMCCNTR_CFG is
# 0x11A8): the gate must read every offset out of this generated header, so a
# fixture that agreed with the hardware by accident would prove nothing.
CFG_HDR = ("#define NPU_REG_PMCR                 0x1180U\n"
           "#define NPU_REG_PMCNTENSET           0x1184U\n"
           "#define NPU_REG_PMOVSSET             0x118CU\n"
           "#define NPU_REG_PMCCNTR_CFG 0x1188U\n")
# The compiled signature of the inlined internal_pre_release snapshot, in
# capture order: PMCR, PMCNTENSET, PMCCNTR_CFG, PMOVSSET.
PRE_OFFS = (0x1180, 0x1184, 0x1188, 0x118C)


def run(mode="Q1", dis=None, nm=None, strings=None, reloc=RELOC_OK,
        src=VENDOR_SRC, hdr=IFACE_HDR, flags=FLAGS_OK,
        preproc=PREPROC_NO_CFG, obj_dis=None, obj_sections=None):
    """One full gate evaluation over synthetic inputs."""
    return gate.evaluate(
        mode=mode,
        disassembly_text=dis if dis is not None else disassembly(mode=mode),
        nm_text=nm if nm is not None else (NM_Q1 if mode == "Q1" else NM_Q0),
        strings_text=strings if strings is not None else strings_dump(),
        relocation_text=reloc,
        object_disassembly_text=(obj_dis if obj_dis is not None
                                 else object_disassembly()),
        object_sections_text=(obj_sections if obj_sections is not None
                              else object_sections()),
        vendor_source_text=src,
        interface_header_text=hdr,
        compiler_flags=flags,
        preprocessed_text=preproc,
        cfg_header_text=CFG_HDR,
    )


# ---------------------------------------------------------------------------

print("=== positive: the whole callsite contract holds ===")
res = run("Q1")
check("Q1 accepts the reference release tail", res["ok"], str(res.get("failures")))
check("unique target callsite counted exactly once",
      res["target_callsite_count"] == 1, str(res["target_callsite_count"]))
check("caller is the vendor function", res["caller_symbol"] == "test_u85")
check("expected return address is the instruction after the target bl",
      isinstance(res["expected_return_address"], int)
      and res["expected_return_address"] > 0,
      hex(res["expected_return_address"]))
check("release store address follows the return address",
      res["release_store_address"] > res["expected_return_address"],
      hex(res["release_store_address"]))
check("TEST_CPM is proven, not assumed", res["test_cpm"] == 1)
check("total printf relocations stay informational, not a pinned count",
      res["printf_relocations"] == 2 and res["puts_relocations"] == 0,
      "%d/%d" % (res["printf_relocations"], res["puts_relocations"]))

print("=== positive: the TARGET call's own object relocation ===")
check("object target call is bound to an R_ARM_*_CALL relocation",
      res["object_target_relocation_type"] == "R_ARM_THM_CALL",
      res["object_target_relocation_type"])
check("object target relocation symbol is exactly printf",
      res["object_target_relocation_symbol"] == "printf",
      res["object_target_relocation_symbol"])
check("object caller and section are attested",
      res["object_caller_symbol"] == "test_u85"
      and res["object_section"] == OBJ_SECTION,
      "%s / %s" % (res["object_caller_symbol"], res["object_section"]))
check("object target call offset is derived, not assumed",
      res["object_target_call_offset"] == 0x10,
      hex(res["object_target_call_offset"]))
check("object target literal slot and rodata addend are derived",
      res["object_target_literal_offset"] == 0x48
      and res["object_target_string_offset"] == OBJ_TARGET_ADDEND
      and res["object_target_string_section"] == OBJ_RODATA,
      "lit=%s str=%s@%s" % (hex(res["object_target_literal_offset"]),
                            hex(res["object_target_string_offset"]),
                            res["object_target_string_section"]))
check("exactly one target callsite in the object",
      res["object_target_callsite_count"] == 1)

print("=== positive: release immediate provenance and Q1 hook order ===")
check("release value is an immediate #12, recorded with its address",
      res["release_immediate_value"] == 12
      and res["release_immediate_address"] > res["expected_return_address"] - 1,
      hex(res["release_immediate_address"]))
check("hook order addresses are strictly increasing",
      [res["hook_internal_pre_release_cycle_read_address"],
       res["hook_pmu_disable_address"], res["hook_dsb_address"],
       res["hook_pmcr_readback_address"],
       res["hook_internal_post_disable_capture_address"],
       res["hook_snapshot_valid_latch_address"]]
      == sorted([res["hook_internal_pre_release_cycle_read_address"],
                 res["hook_pmu_disable_address"], res["hook_dsb_address"],
                 res["hook_pmcr_readback_address"],
                 res["hook_internal_post_disable_capture_address"],
                 res["hook_snapshot_valid_latch_address"]]))
check("hook order digest is emitted", len(res["hook_order_sha256"]) == 64)
check("all four internal_pre_release snapshot reads are recorded in order",
      [res["hook_pre_release_%s_address" % n]
       for n in ("pmcr", "pmcntenset", "pmccntr_cfg", "pmovsset")]
      == sorted([res["hook_pre_release_%s_address" % n]
                 for n in ("pmcr", "pmcntenset", "pmccntr_cfg", "pmovsset")]))
check("the snapshot reads sit between the cycle read and the disable",
      res["hook_internal_pre_release_cycle_read_address"]
      < res["hook_pre_release_pmcr_address"]
      and res["hook_pre_release_pmovsset_address"]
      < res["hook_pmu_disable_address"])
# The digest must distinguish instruction streams the gate ACCEPTS, otherwise
# it is only re-stating the term names it already checked. A padded hook is
# still valid -- every ordered term holds -- but is a materially different
# compiled body, so its digest must differ.
_padded = run(dis=disassembly(hook=hook_body(pad=True)))
check("a padded but still-valid hook is accepted", _padded["ok"])
check("the digest tracks the instruction stream, not just the term names",
      _padded["hook_order_sha256"] != res["hook_order_sha256"],
      "%s vs %s" % (_padded["hook_order_sha256"][:16],
                    res["hook_order_sha256"][:16]))
check("an unrelated printf call in the same object is allowed",
      res["printf_relocations"] == 2)
check("callsite disassembly digest is emitted",
      len(res["callsite_disassembly_sha256"]) == 64)
# Q0 is a SEPARATE link, so it is built here at a different text base on
# purpose: the two modes must agree on the logical callsite while their numeric
# addresses differ, which is exactly why no cross-mode LR equality is ever a
# gate. The digest is taken over address-normalized text so it can carry that
# comparison.
res0 = run("Q0", dis=disassembly(base=0x31800000, mode="Q0"))
check("Q0 accepts the same logical callsite", res0["ok"], str(res0.get("failures")))
check("Q0 and Q1 link at different numeric addresses",
      res0["expected_return_address"] != res["expected_return_address"],
      "%s vs %s" % (hex(res0["expected_return_address"]),
                    hex(res["expected_return_address"])))
check("Q0 and Q1 agree on the normalized callsite disassembly",
      res0["callsite_disassembly_sha256"] == res["callsite_disassembly_sha256"])
check("Q0 carries no hook evidence at all",
      not [k for k in res0 if k.startswith("hook_")],
      str([k for k in res0 if k.startswith("hook_")]))

print("=== negative: target identity ===")
expect_fail(
    "missing target callsite",
    lambda: run(dis=disassembly(tail=release_tail(string_addr=STR_OTHER))),
    "target callsite")
expect_fail(
    "duplicate target callsite",
    lambda: run(dis=disassembly(
        extra_funcs=[("test_other", release_tail() + [("raw", "bx", "lr")])])),
    "target callsite")
expect_fail(
    "a prefix of the target is not the target",
    lambda: run(strings=strings_dump(target="Testing CPM signal\n")),
    "target callsite")
expect_fail(
    "wrong caller",
    lambda: run(dis=Builder().func(
        "some_other_function",
        prologue() + release_tail() + [("raw", "pop", "{r3, pc}")]).render()),
    "caller")
expect_fail(
    # The object may still carry a clean printf relocation and the LINK still
    # lower it to puts, so this term is judged on the final ELF, not the object.
    "target lowered to puts",
    lambda: run(dis=disassembly(tail=release_tail(callee="__wrap_puts",
                                                  callee_addr=0x31001E40))),
    "__wrap_printf")
expect_fail(
    "target resolves to the real printf, bypassing --wrap",
    lambda: run(dis=disassembly(tail=release_tail(callee="printf",
                                                  callee_addr=0x31001F00))),
    "__wrap_printf")
expect_fail(
    "vendor object relocates to puts",
    lambda: run(reloc=RELOC_PUTS),
    "puts")

print("=== negative: the TARGET call's object relocation (fail-closed) ===")
expect_fail(
    # THE fail-open case Codex found: with no relocation on the target call at
    # all, a gate that only counted printf relocations elsewhere in the object
    # would still see a healthy total and pass.
    "target call carries NO relocation",
    lambda: run(obj_dis=object_disassembly(drop_call_reloc=True)),
    "relocation")
expect_fail(
    "target call relocates to puts",
    lambda: run(obj_dis=object_disassembly(
        call_reloc=("R_ARM_THM_CALL", "puts"))),
    "printf")
expect_fail(
    "target call relocates to iprintf",
    lambda: run(obj_dis=object_disassembly(
        call_reloc=("R_ARM_THM_CALL", "iprintf"))),
    "printf")
expect_fail(
    "target call relocates to some other symbol entirely",
    lambda: run(obj_dis=object_disassembly(
        call_reloc=("R_ARM_THM_CALL", "__wrap_printf"))),
    "printf")
expect_fail(
    "target call relocation is not an R_ARM_*_CALL",
    lambda: run(obj_dis=object_disassembly(
        call_reloc=("R_ARM_ABS32", "printf"))),
    "R_ARM")
expect_fail(
    "duplicate target callsites in the object",
    lambda: run(obj_dis=object_disassembly(duplicate=True)),
    "object target callsite")
expect_fail(
    "target literal slot carries no rodata relocation",
    lambda: run(obj_dis=object_disassembly(drop_literal_reloc=True)),
    "object target callsite")
expect_fail(
    "target literal addend names bytes that are not the target string",
    lambda: run(obj_dis=object_disassembly(literal_addend=OBJ_OTHER_ADDEND)),
    "object target callsite")
expect_fail(
    "literal relocation names a section absent from the dump",
    lambda: run(obj_dis=object_disassembly(literal_section=".rodata.missing")),
    "object target callsite")
expect_fail(
    "object caller symbol is not the vendor function",
    lambda: run(obj_dis=object_disassembly(caller="test_other",
                                           section=".text.test_other")),
    "caller")
expect_fail(
    "object section is not the caller's function section",
    lambda: run(obj_dis=object_disassembly(section=".text")),
    "section")

print("=== negative: release tail ordering ===")
expect_fail(
    "extra external call between target return and release",
    lambda: run(dis=disassembly(tail=release_tail(
        extra_between=[("bl", "memcmp", 0x310020DC)]))),
    "call")
expect_fail(
    "extra NPU CMD store between target return and release",
    lambda: run(dis=disassembly(tail=release_tail(
        extra_between=[("mov", "r2", 2), ("str", "r2", "r5", CMD_OFF)]))),
    "NPU CMD")
expect_fail(
    "release before the target call",
    lambda: run(dis=disassembly(tail=release_tail(release_first=True))),
    "release")
expect_fail(
    "the preceding NPU CMD write is not the STOP",
    lambda: run(dis=disassembly(tail=release_tail(stop_value=2))),
    "STOP")
expect_fail(
    "release value is not 0xC",
    lambda: run(dis=disassembly(tail=release_tail(release=4))),
    "release")
expect_fail(
    "an unresolvable store in the tail window is not assumed harmless",
    lambda: run(dis=disassembly(tail=release_tail(
        extra_between=[("mov_reg", "r4", "r7"), ("str", "r2", "r4", CMD_OFF)]))),
    "unresolved")

print("=== negative: release value must be an IMMEDIATE #12 after the return ===")


def literal_release_tail():
    """A 12 materialised from the literal pool instead of an immediate."""
    return [
        ("ldr_lit", "r5", NPU_BASE),
        ("mov", "r3", 0),
        ("str", "r3", "r5", CMD_OFF),
        ("ldr_lit", "r0", STR_TARGET),
        ("bl", "__wrap_printf", 0x31001DDC),
        ("ldr_lit", "r3", 0x0C),
        ("str", "r3", "r5", CMD_OFF),
    ]


def moved_release_tail():
    """A 12 that reaches the store through a register-to-register move."""
    return [
        ("ldr_lit", "r5", NPU_BASE),
        ("mov", "r3", 0),
        ("str", "r3", "r5", CMD_OFF),
        ("ldr_lit", "r0", STR_TARGET),
        ("bl", "__wrap_printf", 0x31001DDC),
        ("mov", "r2", 0x0C),
        ("mov_reg", "r3", "r2"),
        ("str", "r3", "r5", CMD_OFF),
    ]


def early_immediate_tail():
    """The immediate is established BEFORE the target call returns."""
    return [
        ("ldr_lit", "r5", NPU_BASE),
        ("mov", "r4", 0x0C),
        ("mov", "r3", 0),
        ("str", "r3", "r5", CMD_OFF),
        ("ldr_lit", "r0", STR_TARGET),
        ("bl", "__wrap_printf", 0x31001DDC),
        ("str", "r4", "r5", CMD_OFF),
    ]


expect_fail("release 12 loaded from the literal pool",
            lambda: run(dis=disassembly(tail=literal_release_tail())),
            "literal pool")
expect_fail("release 12 arrives via a register-to-register move",
            lambda: run(dis=disassembly(tail=moved_release_tail())),
            "cannot be proven")
expect_fail("release immediate established before the target returns",
            lambda: run(dis=disassembly(tail=early_immediate_tail())),
            "BEFORE the target call returns")
expect_fail("release source register never defined",
            lambda: run(dis=disassembly(tail=[
                ("ldr_lit", "r5", NPU_BASE),
                ("mov", "r3", 0),
                ("str", "r3", "r5", CMD_OFF),
                ("ldr_lit", "r0", STR_TARGET),
                ("bl", "__wrap_printf", 0x31001DDC),
                ("str", "r9", "r5", CMD_OFF)])),
            "cannot be proven")

print("=== negative: Q1 hook structure and order in the final ELF ===")
expect_fail("wrapper never calls the hook",
            lambda: run(dis=disassembly(wrapper=wrapper_body(0))),
            "expected exactly 1")
expect_fail("wrapper calls the hook twice",
            lambda: run(dis=disassembly(wrapper=wrapper_body(2))),
            "expected exactly 1")
expect_fail("hook symbol defined but absent from the ELF body",
            lambda: run(dis=disassembly(drop_hook=True)),
            "no body")
expect_fail("hook has no internal_pre_release cycle read",
            lambda: run(dis=disassembly(hook=hook_body(drop_cycles=True))),
            "npu_pmu_read_cycles")
expect_fail("hook reads cycles twice (capture shape unprovable)",
            lambda: run(dis=disassembly(hook=hook_body(dup_cycles=True))),
            "npu_pmu_read_cycles")
expect_fail("hook never disables the PMU",
            lambda: run(dis=disassembly(hook=hook_body(drop_disable=True))),
            "npu_pmu_disable")
expect_fail("hook disables the PMU twice",
            lambda: run(dis=disassembly(hook=hook_body(dup_disable=True))),
            "npu_pmu_disable")
expect_fail("hook disables the PMU before reading the cycle counter",
            lambda: run(dis=disassembly(
                hook=hook_body(disable_before_cycles=True))),
            "does not precede")
expect_fail("hook has no DSB after the disable",
            lambda: run(dis=disassembly(hook=hook_body(drop_dsb=True))),
            "DSB")
expect_fail("hook never reads back PMCR after the DSB",
            lambda: run(dis=disassembly(hook=hook_body(drop_readback=True))),
            "PMCR")
expect_fail("hook reads back a register other than PMCR",
            lambda: run(dis=disassembly(hook=hook_body(wrong_readback_reg=True))),
            "PMCR")
expect_fail("hook has no internal_post_disable capture",
            lambda: run(dis=disassembly(hook=hook_body(drop_post=True))),
            "pmu_diag_capture_pre_order")
expect_fail("hook captures internal_post_disable twice",
            lambda: run(dis=disassembly(hook=hook_body(dup_post=True))),
            "pmu_diag_capture_pre_order")
expect_fail("validity latched before the ordered operations complete",
            lambda: run(dis=disassembly(hook=hook_body(latch_first=True))),
            "BEFORE the ordered hook operations")
expect_fail("hook never latches snapshot_valid",
            lambda: run(dis=disassembly(hook=hook_body(drop_latch=True))),
            "nothing stores to")
expect_fail("latch stores a value other than 1",
            lambda: run(dis=disassembly(hook=hook_body(latch_value=0))),
            "provable 1")
expect_fail("latch symbol has no address in nm",
            lambda: run(nm=NM_Q1.replace(
                "31004cfc b pmu_qual_hook_snapshot_valid\n", "")),
            "pmu_qual_hook_snapshot_valid")
expect_fail("Q0 ELF calls the hook",
            lambda: run("Q0", dis=disassembly(mode="Q0", wrapper=wrapper_body(1))),
            "calls")

print("=== negative: full internal_pre_release snapshot signature ===")
# The cycle read alone proves only cycle_lo/hi. The snapshot the classifier
# judges also carries pmcr/pmcntenset/pmccntr_cfg/pmovsset, so the compiled
# shape of ALL FOUR reads is required between the cycle read and the disable.
expect_fail("snapshot missing the PMOVSSET read",
            lambda: run(dis=disassembly(hook=hook_body(pre_reads=PRE_OFFS[:3]))),
            "expected exactly 4")
expect_fail("snapshot missing the PMCR read",
            lambda: run(dis=disassembly(hook=hook_body(pre_reads=PRE_OFFS[1:]))),
            "expected exactly 4")
expect_fail("snapshot has a duplicated read",
            lambda: run(dis=disassembly(
                hook=hook_body(pre_reads=PRE_OFFS + (PRE_OFFS[0],)))),
            "expected exactly 4")
expect_fail("snapshot has an extra unrelated in-window read",
            lambda: run(dis=disassembly(
                hook=hook_body(pre_reads=PRE_OFFS + (0x1234,)))),
            "expected exactly 4")
expect_fail("snapshot reads are reordered",
            lambda: run(dis=disassembly(hook=hook_body(
                pre_reads=(PRE_OFFS[1], PRE_OFFS[0], PRE_OFFS[2], PRE_OFFS[3])))),
            "capture order")
expect_fail("snapshot reads the wrong register offset",
            lambda: run(dis=disassembly(hook=hook_body(
                pre_reads=(PRE_OFFS[0], PRE_OFFS[1], 0x9999, PRE_OFFS[3])))),
            "capture order")
expect_fail("snapshot read argument cannot be proven",
            lambda: run(dis=disassembly(hook=hook_body(
                pre_reads=(PRE_OFFS[0], PRE_OFFS[1], None, PRE_OFFS[3])))),
            "capture order")

print("=== negative: the latch must be the LAST side-effecting operation ===")
expect_fail("a store follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(store_after_latch=True))),
            "follows the validity latch")
expect_fail("a call follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(call_after_latch=True))),
            "follows the validity latch")
expect_fail("an unrecognised instruction follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(junk_after_latch=True))),
            "follows the validity latch")
# Only true wind-down survives the latch. A bare ldr or a branch is not a
# return, and "probably harmless" is not a proof -- a branch in particular
# could re-enter code that does anything at all.
expect_fail("a generic ldr follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(
                tail_extra=[("raw", "ldr", "r4, [sp, #4]")]))),
            "follows the validity latch")
expect_fail("a generic ldrd follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(
                tail_extra=[("raw", "ldrd", "r4, r5, [sp, #8]")]))),
            "follows the validity latch")
expect_fail("a branch follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(
                tail_extra=[("raw", "b", "31001100 <somewhere>")]))),
            "follows the validity latch")
expect_fail("arithmetic follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(
                tail_extra=[("raw", "adds", "r4, r4, #1")]))),
            "follows the validity latch")
expect_fail("a register move follows the validity latch",
            lambda: run(dis=disassembly(hook=hook_body(
                tail_extra=[("raw", "mov", "r4, r5")]))),
            "follows the validity latch")
expect_fail("a pop that does not restore pc is not a return",
            lambda: run(dis=disassembly(hook=hook_body(
                epilogue=[("raw", "pop", "{r4, r5}"), ("raw", "bx", "lr")]))),
            "follows the validity latch")
expect_fail("an ldmia that is not from sp is not a return",
            lambda: run(dis=disassembly(hook=hook_body(
                epilogue=[("raw", "ldmia", "r4!, {r5, pc}")]))),
            "follows the validity latch")

print("=== negative: post-latch GRAMMAR is nop* return data*, not a filter ===")
# A per-instruction allowlist accepts each of these one at a time. Only a
# grammar over the whole tail rejects them.
expect_fail("nothing after the latch returns at all",
            lambda: run(dis=disassembly(hook=hook_body(latch_via_mov=True,
                                                       epilogue=[]))),
            "never returns")
expect_fail("literal data sits before the return",
            lambda: run(dis=disassembly(hook=hook_body(epilogue=[]))),
            "before <pmu_qual_pre_release_hook> has returned")
expect_fail("a second return follows the first",
            lambda: run(dis=disassembly(hook=hook_body(
                epilogue=[("raw", "bx", "lr"), ("raw", "bx", "lr")]))),
            "returns a second time")
expect_fail("an executable instruction follows the return",
            lambda: run(dis=disassembly(hook=hook_body(
                epilogue=[("raw", "bx", "lr"), ("raw", "nop", "")]))),
            "follows the return")
expect_fail("a nop between the return and the literal pool",
            lambda: run(dis=disassembly(hook=hook_body(
                epilogue=[("raw", "pop", "{r3, pc}"), ("raw", "nop", "")]))),
            "follows the return")

print("=== positive: real-shape epilogues are accepted after the latch ===")
check("the exact Q1 tail: latch -> ldmia.w sp!,{...pc} -> literal pool",
      run(dis=disassembly(hook=hook_body(epilogue=[
          ("raw", "ldmia.w", "sp!, {r3, r4, r5, r6, r7, r8, r9, pc}")])))["ok"])
for _label, _epi in (
        ("ldmia.w sp!, {...pc}  (the real Q1 shape)",
         [("raw", "ldmia.w", "sp!, {r3, r4, r5, r6, r7, r8, r9, pc}")]),
        ("pop {r3, pc}", [("raw", "pop", "{r3, pc}")]),
        ("ldmfd sp!, {r4, pc}", [("raw", "ldmfd", "sp!, {r4, pc}")]),
        ("bx lr", [("raw", "bx", "lr")]),
        ("nop then a return", [("raw", "nop", ""), ("raw", "bx", "lr")])):
    check("accepted after latch: %s" % _label,
          run(dis=disassembly(hook=hook_body(epilogue=_epi)))["ok"])

print("=== negative: the hook's exact direct call sequence ===")
expect_fail("an extra unrelated call before the latch",
            lambda: run(dis=disassembly(
                hook=hook_body(extra_call_after_cycles=True))),
            "direct call sequence")
expect_fail("an extra PMCR readback before the latch",
            lambda: run(dis=disassembly(hook=hook_body(extra_readback=True))),
            "direct call sequence")
expect_fail("readback and post-disable capture reordered",
            lambda: run(dis=disassembly(
                hook=hook_body(swap_readback_and_capture=True))),
            "does not follow the PMCR readback")

print("=== negative: symbols, flags and CFG ===")
expect_fail("Q1 missing the noinline hook symbol",
            lambda: run("Q1", nm=NM_Q0), "pmu_qual_pre_release_hook")
expect_fail("Q0 must not carry the hook symbol",
            lambda: run("Q0", nm=NM_Q1), "pmu_qual_pre_release_hook")
expect_fail("wrapper inlined away / symbol gone",
            lambda: run("Q1", nm="310005f8 T test_u85\n"), "__wrap_printf")
expect_fail("caller symbol gone",
            lambda: run("Q1", nm=NM_Q1.replace("310005f8 T test_u85\n", "")),
            "test_u85")
expect_fail("-fno-builtin-printf missing",
            lambda: run(flags=FLAGS_OK.replace("-fno-builtin-printf", "")),
            "fno-builtin-printf")
expect_fail("LTO enabled", lambda: run(flags=FLAGS_OK + " -flto"), "LTO")
expect_fail("PMCCNTR_CFG written in the translation unit",
            lambda: run(preproc=PREPROC_CFG), "PMCCNTR_CFG")
expect_fail("TEST_CPM is not 1",
            lambda: run(src=VENDOR_SRC.replace("#define TEST_CPM 1",
                                               "#define TEST_CPM 0")),
            "TEST_CPM")
expect_fail("vendor source carries more than one terminal release",
            lambda: run(src=VENDOR_SRC + "    write_reg(NPU_REG_CMD, 0x0000000C);\n"),
            "terminal")
expect_fail("unknown mode", lambda: run(mode="Q2"), "mode")

print("=== manifest ===")
man = gate.manifest_document(
    run("Q1"), build_id=0x31485150,
    vendor_source_sha256="a" * 64, vendor_object_sha256="b" * 64,
    compiler_flags=FLAGS_OK,
    artifacts={"APP.BIN": "c" * 64, "VECTORS.BIN": "d" * 64,
               "DDR.BIN": "e" * 64, "elf": "f" * 64, "map": "0" * 64})
check("schema version is 8", man["schema_version"] == 8)
check("build id is a hex string", man["build_id"] == "0x31485150")
check("expected_return_address is numeric",
      isinstance(man["expected_return_address"], int))
check("release_store_address is numeric",
      isinstance(man["release_store_address"], int))
check("every required manifest key is present",
      not [k for k in ("schema_version", "qualification_mode", "build_id",
                       "vendor_source_sha256", "vendor_object_sha256",
                       "caller_symbol", "expected_return_address",
                       "release_store_address", "callsite_disassembly_sha256",
                       "test_cpm", "printf_relocations", "puts_relocations",
                       "compiler_flags", "artifact_sha256")
           if k not in man])
check("manifest records the object target relocation evidence",
      not [k for k in ("object_caller_symbol", "object_section",
                       "object_target_call_offset",
                       "object_target_relocation_type",
                       "object_target_relocation_symbol",
                       "object_target_literal_offset",
                       "object_target_string_section",
                       "object_target_string_offset")
           if k not in man])
check("object relocation symbol/type are recorded verbatim",
      man["object_target_relocation_symbol"] == "printf"
      and man["object_target_relocation_type"] == "R_ARM_THM_CALL")
check("object call/literal offsets are numeric",
      isinstance(man["object_target_call_offset"], int)
      and isinstance(man["object_target_literal_offset"], int)
      and isinstance(man["object_target_string_offset"], int))
check("all five artifact hashes are carried",
      sorted(man["artifact_sha256"]) == ["APP.BIN", "DDR.BIN", "VECTORS.BIN",
                                         "elf", "map"])
check("the manifest carries no address the firmware could import",
      "expected_return_address" in man and man["expected_return_address"] != 0)

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
