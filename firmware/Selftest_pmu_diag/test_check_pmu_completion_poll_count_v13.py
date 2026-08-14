import hashlib
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-72s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def fail(message: str) -> AssertionError:
    return AssertionError(message)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1)


SCHEMA_VERSION = 13
BUILD_ID = "0x33314950"
POLL_LIMIT = 10000
INVALID_REMAINING = 0
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
EXPECTED_SOURCE_NEGATIVE_FIXTURES = {
    "duplicate_helper_definition",
    "duplicate_store",
    "extra_mmio",
    "per_iteration_increment_store",
    "remaining_before_p2",
    "retained_v12_hard_bypass",
    "retained_v12_qread_release_drift",
    "second_status_read",
    "second_writer_after_test_commands",
    "second_writer_before_helper",
    "success_remaining_10001",
    "success_remaining_zero",
    "timeout_reachable_store",
    "wrong_completion_mask",
}

REAL_RUNNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner_pmu_diag_main.c")
ENV_VENDOR_KEY = "V12_FROZEN_VENDOR_SOURCE"
PATCH_VENDOR_STOCK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

void u85_irq_handler(void)
{
    int32_t status_register = 0;
    status_register = read_reg(NPU_REG_STATUS);
    irq_history_mask = status_register >> 16;
    if ((status_register & 0x02)){
        printf("Got IRQ, History_mask is %x status_register is %x\\n", irq_history_mask, status_register);
        printf("Expected History_mask is set in CMD0_NPU_OP_STOP of the corresponding cmd stream include file\\n");
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 2);
    }
}

static inline void wait_for_irq(void)
{
    while (false == irq_triggered) {
      sleep();
      if (!irq_triggered) {
        irq_never_triggered = true;
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\\n", read_reg(NPU_REG_STATUS));
        break;
      }
    }
    irq_triggered = false;
}

static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{
\tint ret_code;
    int read_val;

\t/* Init locals */
\tret_code =0;
\tread_val =0;

\t  //Start NPU
\t  read_val = read_reg(NPU_REG_CMD);
\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);
\t  //Clear IRQ
\t  wait_for_irq();
\t  // Read QREAD register
\t  read_val = read_reg(NPU_REG_QREAD);
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  if(read_val == u32CmdQueueSize) {
\t    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t  }
\t  else {
\t    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t    ret_code = 1;
\t  }
\t  //Stop NPU
\t  write_reg(NPU_REG_CMD, 0x00000000);
\t  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
\t    printf("Testing CPM signals\\n");
\t    //Enable Program CLKQ and PWRQ interfaces
\t    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
\t    write_reg(NPU_REG_CMD, 0x0000000C);
#endif
}

int test_u85( const u85_eTest eTest,
              const uint32_t u32ExpectedIRQMask,
              const uint32_t u32OutputSize,
              const uint32_t u32CmdQueueSize,
              struct u85_warp_data_t *pu85_warp_data_st )
{
    int ret_code = 0;

    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    NVIC_EnableIRQ(NPU0_IRQn);
    return ret_code;
}
"""

RUNNER_RAW_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
}

void run_once(v13_t* d)
{
    d->t_pmu_disable = DWT->CYCCNT;
}
"""

VENDOR_RAW_STOCK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline uint32_t wait_for_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    for (uint32_t i = 0; i < 10000; ++i) {
        status = *status_reg;
        if (status & 0x02) {
            P1 = DWT;
            P2 = DWT;
            return status;
        }
    }

    return 0U;
}
"""

RUNNER_V12_GENERATED = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U
#endif
"""

VENDOR_V12_GENERATED = """uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }

    return 0U;
}
"""

RUNNER_V13_OK = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_SCHEMA_VERSION 13U
#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U
#define V13_POLL_SUCCESS 1U
#define V13_POLL_TIMEOUT 2U
#define PMU_DIAG_FIELD_COUNT 101U
#define PMU_DIAG_TOTAL_WORDS 109U
#define PMU_DIAG_PAYLOAD_SIZE 436U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
typedef struct {
    uint32_t poll_result;
    uint32_t status_at_success;
    uint32_t poll_remaining_at_success;
} v13_t;
extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;

void reset_globals(void)
{
    pmu_completion_poll_v13_t_poll_status_at_success        = 0U;
    pmu_completion_poll_v13_t_poll_remaining_at_success     = 0U;
}

void collect_record(v13_t d)
{
    d.poll_result                     = pmu_completion_poll_v13_t_poll_result;
    d.status_at_success               = pmu_completion_poll_v13_t_poll_status_at_success;
    d.poll_remaining_at_success       = pmu_completion_poll_v13_t_poll_remaining_at_success;
    if (d.poll_result != V13_POLL_SUCCESS) {
        d.status_at_success        = 0U;
        d.poll_remaining_at_success = 0U;
    }
}

void emit_record(v13_t* d, uint32_t *out_words)
{
    out_words[100] = d->poll_remaining_at_success;
}
"""

VENDOR_V13_OK = """uint32_t __attribute__((noinline)) v13_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
            return status;
        }
    }

    return 0U;
}
"""

SECOND_WRITER_BEFORE_HELPER = """void v13_side_effect_before(void)
{
    pmu_completion_poll_v13_t_poll_remaining_at_success = 7U;
}

"""

SECOND_WRITER_AFTER_TEST_COMMANDS = """
static int test_commands(void)
{
    pmu_completion_poll_v13_t_poll_remaining_at_success = 9U;
    return 0;
}
"""

# ---------------------------------------------------------------------------
# Synthetic ELF fixtures.
#
# `build_helper_disassembly` lays the rows out, then derives every PC-relative
# literal offset and every branch target from that layout. No fixture below
# names an instruction address, so inserting or deleting a row re-derives the
# whole image -- including the Thumb ``((addr + 4) & ~3) + imm`` offsets the
# gate independently re-computes when it resolves the literal pool.
#
# The encoding column is filler. The gate strips it by design, so that two
# builds that encode the same instruction differently still verify; these
# fixtures therefore do not model real encodings. Width suffixes (`.w` / `.n`)
# live in the mnemonic text because that is what the gate actually reads.
# ---------------------------------------------------------------------------

V12_HELPER = "v12_poll_completion"
V13_HELPER = "v13_poll_completion"
V12_HELPER_ADDR = 0x31002000
V13_HELPER_ADDR = 0x32002040
EXTERNAL_CALLEE = "helper_bookkeeping"

# The MPS4 address map, pinned here from firmware evidence rather than imported
# from the gate, so that a gate constant drifting away from the board is a test
# failure instead of a silent agreement:
#   * U85 base 0x50004000 -- firmware/Selftest_pmu/runner_pmu_main.c:274
#     (`#define U85_BASE_ADDRESS 0x50004000U`, citing Drivers/u85_driver/u85.c)
#   * helper STATUS 0x50004004 -- check_pmu_completion_poll_v12.py:104's emitted
#     `helper_status_register_address`, reached as base + 4
#   * DWT base 0xE0001000 with CYCCNT at displacement 4 -- the real MPS4 image
#     transcribed in test_check_pmu_completion_poll_v12.py REAL_ARM_DISASSEMBLY
#     (`31002378: .word 0xe0001000`, read back as `ldr r2, [r3, #4]`)
#   * diagnostic globals in .bss around 0x31005xxx -- REAL_ARM_NM
# Every literal below is therefore a *base*, and the address an instruction
# touches is that base plus the displacement it carries.
REAL_U85_BASE_ADDRESS = 0x50004000
REAL_STATUS_ADDRESS = 0x50004004
REAL_DWT_BASE_ADDRESS = 0xE0001000
REAL_DWT_CYCCNT_ADDRESS = 0xE0001004

V12_LITERALS = (
    ("STATUS", REAL_U85_BASE_ADDRESS),
    ("DWT", REAL_DWT_BASE_ADDRESS),
    ("P1", 0x31005368),
    ("P2", 0x3100536C),
)

V13_LITERALS = (
    ("STATUS", REAL_U85_BASE_ADDRESS),
    ("DWT", REAL_DWT_BASE_ADDRESS),
    ("P1", 0x31005380),
    ("P2", 0x31005384),
    ("REMAINING", 0x31005388),
)


def row(label: str, text: str, *, size: int = 2, comment: str = "") -> dict[str, object]:
    return {"label": label, "size": size, "text": text, "comment": comment}


def _align4(value: int) -> int:
    return (value + 3) & ~3


def build_helper_disassembly(
    helper: str,
    base: int,
    rows,
    literals,
    *,
    comments: bool = True,
    pool_gap: int = 0,
    extras: str = "",
) -> str:
    placed = []
    addr = base
    for item in rows:
        placed.append((addr, item))
        addr += item["size"]
    labels = {item["label"]: at for at, item in placed}
    pool = _align4(addr + pool_gap)
    slots = {name: pool + 4 * index for index, (name, _word) in enumerate(literals)}

    def render(at: int, text: str) -> str:
        for name, slot in slots.items():
            text = text.replace("{lit:%s}" % name, "#%d" % (slot - ((at + 4) & ~3)))
        for name, target in labels.items():
            text = text.replace(
                "{to:%s}" % name, "%08x <%s+0x%x>" % (target, helper, target - base)
            )
        return text.replace("{call}", "%08x <%s>" % (base - 0x1000, EXTERNAL_CALLEE))

    lines = ["%08x <%s>:" % (base, helper)]
    for at, item in placed:
        body = render(at, item["text"])
        if comments and item["comment"]:
            body = "%-32s; %s" % (body, item["comment"])
        lines.append(
            "%08x:   %-11s %s" % (at, "0000" if item["size"] == 2 else "0000 0000", body.rstrip())
        )
    for name, word in literals:
        body = ".word   0x%08X" % word
        if comments:
            body = "%-32s; %s" % (body, name)
        lines.append("%08x:   %s" % (slots[name], body.rstrip()))
    return "\n".join(lines) + "\n" + extras


def build_nm(entries) -> str:
    return "".join("%08x T %s\n" % (addr, name) for addr, name in entries)


def _row_index(rows, label: str) -> int:
    for index, item in enumerate(rows):
        if item["label"] == label:
            return index
    raise fail("fixture row not found: %s" % label)


def rows_after(rows, label: str, *inserted):
    at = _row_index(rows, label) + 1
    return list(rows[:at]) + list(inserted) + list(rows[at:])


def rows_before(rows, label: str, *inserted):
    at = _row_index(rows, label)
    return list(rows[:at]) + list(inserted) + list(rows[at:])


def rows_without(rows, *labels):
    return [item for item in rows if item["label"] not in labels]


def rows_retext(rows, label: str, text: str):
    at = _row_index(rows, label)
    return [dict(item, text=text) if index == at else item for index, item in enumerate(rows)]


def rows_relocate(rows, moved, before_label: str):
    moving = [item for item in rows if item["label"] in moved]
    rest = [item for item in rows if item["label"] not in moved]
    at = _row_index(rest, before_label)
    return rest[:at] + moving + rest[at:]


def literals_with(literals, *added):
    return tuple(literals) + tuple(added)


def literals_without(literals, *names):
    return tuple(item for item in literals if item[0] not in names)


def literals_set(literals, name: str, word: int):
    return tuple((key, word if key == name else value) for key, value in literals)


def literals_reversed(literals):
    return tuple(reversed(literals))


def v12_rows():
    return [
        row("init_shadow", "movw    r2, #10000", size=4, comment="V12_FAILED_POLL_REMAINING_INIT"),
        row("init_induction", "movw    r1, #10000", size=4, comment="V12_TIMEOUT_INIT"),
        row("status_ptr", "ldr     r7, [pc, {lit:STATUS}]", comment="V12_HELPER_STATUS_PTR"),
        row("pad", "nop", comment="V12_ALIGNMENT_PAD"),
        row("loop", "ldr.w   r4, [r7, #4]", size=4, comment="V12_HELPER_STATUS_READ"),
        row("test", "tst.w   r4, #2", size=4, comment="V12_HELPER_STATUS_TEST"),
        row("succ_branch", "bne.n   {to:success}", comment="V12_SUCCESS_BRANCH"),
        row("dec_shadow", "subs    r2, #1", comment="V12_FAILED_POLL_DECREMENT"),
        row("dec_induction", "subs    r1, #1", comment="V12_TIMEOUT_DECREMENT"),
        row("back_edge", "bne.n   {to:loop}", comment="V12_BACK_EDGE"),
        row("timeout_result", "movs    r0, #0", comment="V12_TIMEOUT_RESULT"),
        row("timeout_return", "bx      lr", comment="V12_TIMEOUT_RETURN"),
        row("success", "ldr     r6, [pc, {lit:DWT}]", comment="V12_DWT_CYCCNT_PTR"),
        row("p1_read", "ldr     r0, [r6, #4]", comment="V12_P1_DWT_READ"),
        row("p1_ptr", "ldr     r5, [pc, {lit:P1}]", comment="V12_P1_STORE_PTR"),
        row("p1_store", "str     r0, [r5, #0]", comment="V12_P1_STORE"),
        row("p2_read", "ldr     r0, [r6, #4]", comment="V12_P2_DWT_READ"),
        row("p2_ptr", "ldr     r5, [pc, {lit:P2}]", comment="V12_P2_STORE_PTR"),
        row("p2_store", "str     r0, [r5]", comment="V12_P2_STORE"),
        row("succ_result", "mov     r0, r4", comment="V12_SUCCESS_RESULT"),
        row("succ_return", "bx      lr", comment="V12_SUCCESS_RETURN"),
    ]


def v13_rows():
    return rows_after(
        [dict(item, comment=item["comment"].replace("V12_", "V13_")) for item in v12_rows()],
        "p2_store",
        row("rem_ptr", "ldr     r5, [pc, {lit:REMAINING}]", comment="V13_REMAINING_STORE_PTR"),
        row("rem_store", "str     r1, [r5]", comment="V13_REMAINING_STORE"),
    )


def v12_elf(*, rows=None, literals=None, base=V12_HELPER_ADDR, extra_nm=(), **kwargs):
    objdump = build_helper_disassembly(
        V12_HELPER,
        base,
        v12_rows() if rows is None else rows,
        V12_LITERALS if literals is None else literals,
        **kwargs,
    )
    nm = build_nm(((base, V12_HELPER), (0x31003000, "u85_irq_handler")) + tuple(extra_nm))
    return objdump, nm


def v13_elf(*, rows=None, literals=None, base=V13_HELPER_ADDR, extra_nm=(), **kwargs):
    objdump = build_helper_disassembly(
        V13_HELPER,
        base,
        v13_rows() if rows is None else rows,
        V13_LITERALS if literals is None else literals,
        **kwargs,
    )
    nm = build_nm(
        (
            (base, V13_HELPER),
            (0x32003020, "u85_irq_handler"),
            (0x32004200, "NVIC_EnableIRQ"),
        )
        + tuple(extra_nm)
    )
    return objdump, nm


def extras_section(name: str, addr: int, *lines: str) -> str:
    body = "".join("%08x:   %s\n" % (addr + 4 * index, text) for index, text in enumerate(lines))
    return "\n%08x <%s>:\n%s" % (addr, name, body)


def objdump_section(name: str, addr: int, *rows: tuple[str, str, str]) -> str:
    """A section in real ``objdump -d`` layout: tab-separated columns.

    The retained NVIC gate resolves store destinations through the V12 ELF
    parser, whose line grammar is the tab-separated one objdump actually emits.
    Fixtures aimed at that gate must therefore be written in the real layout
    rather than the column-aligned shorthand the other fixtures use, or the
    parser reads them as an empty function and proves nothing.
    """
    body = "".join(
        "%08x:\t%s \t%s\t%s\n" % (addr + 4 * index, encoding, mnemonic, operands)
        for index, (encoding, mnemonic, operands) in enumerate(rows)
    )
    return "\n%08x <%s>:\n%s" % (addr, name, body)


V12_OBJDUMP_OK, V12_NM_OK = v12_elf()
V13_OBJDUMP_OK, V13_NM_OK = v13_elf()

# Retained-V12 runtime shape that the V13 image is *required* to keep: the
# stock vector install and the pending clear. Neither is drift, so the gate
# must accept an image that still calls them.
V13_RETAINED_STOCK_OBJDUMP = V13_OBJDUMP_OK + extras_section(
    "test_u85",
    0x32004000,
    "f7ff f97e   bl      32004300 <NVIC_SetVector> ; V13_RUNTIME_VECTOR_INSTALL",
    "f7ff f9fc   bl      32004400 <NVIC_ClearPendingIRQ> ; V13_RUNTIME_CLEAR_PENDING",
    "4770        bx      lr",
)

V13_RETAINED_STOCK_NM = V13_NM_OK + build_nm(
    (
        (0x32004000, "test_u85"),
        (0x32004300, "NVIC_SetVector"),
        (0x32004400, "NVIC_ClearPendingIRQ"),
    )
)


# Builds the gate must accept: same semantics, different relocation, register
# allocation, literal-pool layout, encoding width or comment stripping.
V13_ACCEPTED_VARIANTS = (
    ("relocated helper with re-derived literal offsets", v13_elf(base=0x32009100, pool_gap=8)),
    ("comment-stripped disassembly", v13_elf(comments=False)),
    (
        "narrow/wide encoding swap on the polled instructions",
        v13_elf(
            rows=rows_retext(
                rows_retext(
                    rows_retext(v13_rows(), "loop", "ldr     r4, [r7, #4]"),
                    "test",
                    "tst     r4, #2",
                ),
                "back_edge",
                "bne.w   {to:loop}",
            )
        ),
    ),
    (
        "different register allocation",
        v13_elf(
            rows=[
                dict(item, text=item["text"].replace("r7", "r3").replace("r4", "r0").replace("r1", "r2")
                     if item["label"] in ("status_ptr", "loop", "test", "succ_result")
                     else item["text"])
                for item in v13_rows()
            ]
        ),
    ),
    ("reversed literal-pool layout", v13_elf(literals=literals_reversed(V13_LITERALS))),
)


# Drifted V12 references: each one still satisfies the V12 half of the
# structural gate on its own, so only the normalized cross-ELF signature can
# tell it apart from the canonical V13 loop.
V12_DRIFTED_REFERENCES = (
    (
        "halfword STATUS read",
        v12_elf(rows=rows_retext(v12_rows(), "loop", "ldrh.w  r4, [r7, #4]")),
    ),
    (
        "success branch on the whole register instead of the masked flags",
        v12_elf(rows=rows_retext(v12_rows(), "succ_branch", "cbnz    r4, {to:success}")),
    ),
)


def _elf_negative_fixtures() -> dict[str, dict[str, str]]:
    """Every V13 image the final-ELF gate must refuse, keyed by drift name."""
    gap_effects = (
        ("gap_extra_mov", "mov     r3, r4", 2, "extra per-iteration instruction"),
        ("gap_dwt_read", "ldr     r0, [r6]", 2, "extra per-iteration load/store"),
        ("gap_sram_store", "str     r4, [r5]", 2, "extra per-iteration store"),
        ("gap_barrier", "dsb     sy", 4, "extra per-iteration barrier"),
        ("gap_call", "bl      {call}", 4, "extra per-iteration call"),
    )
    fixtures = {}

    # The region between the STATUS load and the completion test is executed
    # once per poll just like the failed-path tail, so it must reject the same
    # effects. Every one of these used to slip through unseen.
    for name, text, size, expected in gap_effects:
        fixtures[name] = _elf_case(
            v13_elf(rows=rows_after(v13_rows(), "loop", row(name, text, size=size))), expected
        )

    tail_effects = (
        ("extra_loop_mov", "mov     r1, r5", 2, "extra per-iteration instruction"),
        ("extra_loop_store", "str     r1, [r5]", 2, "extra per-iteration store"),
        ("extra_loop_barrier", "isb     sy", 4, "extra per-iteration barrier"),
        ("extra_loop_call", "bl      {call}", 4, "extra per-iteration call"),
    )
    for name, text, size, expected in tail_effects:
        fixtures[name] = _elf_case(
            v13_elf(
                rows=rows_after(v13_rows(), "succ_branch", row(name, text, size=size)),
                extra_nm=((V13_HELPER_ADDR - 0x1000, EXTERNAL_CALLEE),),
            ),
            expected,
        )

    fixtures["extra_loop_spill_reload"] = _elf_case(
        v13_elf(
            rows=rows_after(
                v13_rows(),
                "succ_branch",
                row("spill", "str     r3, [sp, #0]"),
                row("reload", "ldr     r3, [sp, #0]"),
            )
        ),
        "extra per-iteration load/store",
    )
    fixtures["missing_failed_decrement"] = _elf_case(
        v13_elf(rows=rows_without(v13_rows(), "dec_shadow")), "failed-poll decrement count"
    )
    fixtures["third_failed_decrement"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "dec_induction", row("dec_third", "subs    r5, #1"))),
        "failed-poll decrement count",
    )
    fixtures["wrong_back_edge"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "back_edge", "bne.n   {to:status_ptr}")),
        "conditional loop back-edge",
    )
    fixtures["decrement_clobbers_status_pointer"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "dec_shadow", "subs    r7, #1")),
        "failed-poll decrement clobbers the STATUS read",
    )
    fixtures["second_status_read"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "p2_store", row("reread", "ldr.w   r4, [r7, #4]", size=4))),
        "helper STATUS read count != 1",
    )
    fixtures["extra_non_status_load"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "success", row("stray", "ldr     r3, [r3, #4]"))),
        "extra non-STATUS load",
    )
    fixtures["wrong_status_address"] = _elf_case(
        v13_elf(literals=literals_set(V13_LITERALS, "STATUS", 0x50004018)),
        "helper STATUS MMIO address",
    )
    fixtures["store_before_p2"] = _elf_case(
        v13_elf(rows=rows_relocate(v13_rows(), ("rem_ptr", "rem_store"), "p2_read")),
        "remaining store must follow P2 exactly",
    )
    fixtures["constant_store"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "rem_store", row("const", "movs    r1, #1"))),
        "remaining must dataflow from failed-poll countdown live-out",
    )
    fixtures["recomputed_store"] = _elf_case(
        v13_elf(
            rows=rows_before(v13_rows(), "rem_ptr", row("recompute", "sub.w   r1, r1, #32", size=4))
        ),
        "remaining must dataflow from failed-poll countdown live-out",
    )
    fixtures["timeout_reaches_store"] = _elf_case(
        v13_elf(
            rows=rows_before(
                v13_rows(),
                "timeout_result",
                row("t_ptr", "ldr     r5, [pc, {lit:REMAINING}]"),
                row("t_store", "str     r1, [r5]"),
            )
        ),
        "timeout path must not publish remaining",
    )
    fixtures["push_pop_stack_frame"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "init_shadow", row("push", "push    {r4, lr}"))),
        "helper must remain a leaf without stack access",
    )

    # Literal-pool binding: the pool must be exactly the slots the helper
    # reads, and each pointer must resolve to the address its role requires.
    fixtures["decoy_status_literal"] = _elf_case(
        v13_elf(literals=literals_with(V13_LITERALS, ("DECOY_STATUS", REAL_U85_BASE_ADDRESS))),
        "unreferenced helper literal",
    )
    fixtures["decoy_dwt_literal"] = _elf_case(
        v13_elf(literals=literals_with(V13_LITERALS, ("DECOY_DWT", REAL_DWT_BASE_ADDRESS))),
        "unreferenced helper literal",
    )
    fixtures["bogus_literal_offset"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "status_ptr", "ldr     r7, [pc, #400]")),
        "outside helper literal pool",
    )
    fixtures["status_pointer_into_sram"] = _elf_case(
        v13_elf(
            rows=rows_retext(
                rows_before(
                    v13_rows(), "status_ptr", row("keep_status", "ldr     r3, [pc, {lit:STATUS}]")
                ),
                "status_ptr",
                "ldr     r7, [pc, {lit:SHADOW}]",
            ),
            literals=literals_with(V13_LITERALS, ("SHADOW", 0x31006000)),
        ),
        "helper STATUS load must resolve to 0x%08X" % REAL_STATUS_ADDRESS,
    )
    fixtures["cycle_count_read_from_sram"] = _elf_case(
        v13_elf(
            rows=rows_retext(
                rows_before(v13_rows(), "init_shadow", row("keep_dwt", "ldr     r3, [pc, {lit:DWT}]")),
                "success",
                "ldr     r6, [pc, {lit:FAKE_CYCCNT}]",
            ),
            literals=literals_with(V13_LITERALS, ("FAKE_CYCCNT", 0x31006100)),
        ),
        "cycle-count read must resolve to DWT CYCCNT 0x%08X" % REAL_DWT_CYCCNT_ADDRESS,
    )
    fixtures["remaining_reuses_p2_destination"] = _elf_case(
        v13_elf(
            rows=rows_retext(v13_rows(), "rem_ptr", "ldr     r5, [pc, {lit:P2}]"),
            literals=literals_without(V13_LITERALS, "REMAINING"),
        ),
        "P1/P2/remaining must target three distinct SRAM destinations",
    )
    fixtures["store_destination_in_mmio"] = _elf_case(
        v13_elf(
            rows=rows_retext(v13_rows(), "p1_ptr", "ldr     r5, [pc, {lit:STATUS}]"),
            literals=literals_without(V13_LITERALS, "P1"),
        ),
        "store destination must resolve to an SRAM literal slot",
    )

    # Displacement drifts. Each row below keeps the *base* register that every
    # literal-binding check above already proves, and moves only the immediate
    # displacement -- so a gate that resolves the base and discards the
    # displacement accepts all three while the instruction touches a different
    # address than its role allows.
    fixtures["status_read_displaced_off_register"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "loop", "ldr.w   r4, [r7, #64]")),
        "helper STATUS load must resolve to 0x%08X" % REAL_STATUS_ADDRESS,
    )
    fixtures["cycle_count_read_displaced_off_cyccnt"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "p1_read", "ldr     r0, [r6, #12]")),
        "cycle-count read must resolve to DWT CYCCNT 0x%08X" % REAL_DWT_CYCCNT_ADDRESS,
    )
    fixtures["publication_displaced_off_slot"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "rem_store", "str     r1, [r5, #16]")),
        "store destination must resolve to an SRAM literal slot",
    )

    fixtures["pc_load_in_poll_region"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "loop", row("pc_load", "ldr     r3, [pc, {lit:DWT}]"))),
        "extra per-iteration load/store",
    )
    fixtures["backward_literal_offset"] = _elf_case(
        v13_elf(rows=rows_retext(v13_rows(), "status_ptr", "ldr     r7, [pc, #-16]")),
        "outside helper literal pool",
    )
    fixtures["foreign_peripheral_literal"] = _elf_case(
        v13_elf(
            rows=rows_after(v13_rows(), "init_shadow", row("other", "ldr     r3, [pc, {lit:OTHER}]")),
            literals=literals_with(V13_LITERALS, ("OTHER", 0x40000000)),
        ),
        "helper references unexpected MMIO literal 0x40000000",
    )
    fixtures["fourth_success_store"] = _elf_case(
        v13_elf(
            rows=rows_after(
                v13_rows(),
                "rem_store",
                row("x_ptr", "ldr     r5, [pc, {lit:EXTRA}]"),
                row("x_store", "str     r1, [r5]"),
            ),
            literals=literals_with(V13_LITERALS, ("EXTRA", 0x31005390)),
        ),
        "remaining store after P2 count != 1",
    )
    fixtures["remaining_register_redefined"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "rem_store", row("clobber", "mov     r1, r2"))),
        "remaining must dataflow from failed-poll countdown live-out",
    )
    fixtures["timeout_falls_through_to_success"] = _elf_case(
        v13_elf(rows=rows_without(v13_rows(), "timeout_return")), "timeout exit edge missing"
    )

    # Live-out modelling: every drift below sits between the success entry and
    # the remaining store, and every one of them writes -- or may write -- the
    # published register through an effect the live-out proof does not model.
    # A vocabulary the proof merely ignores would let each of them redefine the
    # countdown invisibly, so the gate must refuse the instruction outright.
    fixtures["ldrd_reloads_remaining_register"] = _elf_case(
        v13_elf(
            rows=rows_before(v13_rows(), "rem_store", row("ldrd", "ldrd    r1, r2, [r5]", size=4))
        ),
        "multi-register transfer on the success path",
    )
    fixtures["it_block_predicates_remaining_register"] = _elf_case(
        v13_elf(
            rows=rows_before(
                v13_rows(),
                "rem_store",
                row("it_eq", "it      eq"),
                row("moveq", "moveq   r1, #5"),
            )
        ),
        "predicated instruction on the success path",
    )
    fixtures["predicated_move_without_it_header"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "rem_store", row("moveq", "moveq   r1, #5"))),
        "predicated instruction on the success path",
    )
    fixtures["rrx_recomputes_remaining_register"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "rem_store", row("rrx", "rrx     r1, r1", size=4))),
        "unmodelled success-path effect",
    )
    fixtures["unrelated_rrx_recompute"] = _elf_case(
        v13_elf(rows=rows_before(v13_rows(), "rem_store", row("rrx", "rrx     r3, r3", size=4))),
        "unmodelled success-path effect",
    )


    # Control-flow reachability: every drift below keeps the instruction *shape*
    # the store-classifying checks look at intact, so only walking the helper's
    # own branch edges can tell that the publication is skipped, repeated,
    # duplicated or reachable from the timeout exit.
    fixtures["timeout_branches_to_remaining_store"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "timeout_result", row("t_jump", "b.n     {to:rem_ptr}"))),
        "remaining store must be unreachable from the timeout path",
    )
    fixtures["success_branch_skips_remaining_store"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "p2_store", row("skip", "bcs.n   {to:succ_result}"))),
        "success path must publish remaining exactly once: return counts [0, 1]",
    )
    fixtures["success_returns_before_remaining_store"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "p2_store", row("early_return", "bx      lr"))),
        "success path must publish remaining exactly once: return counts [0]",
    )
    fixtures["success_branch_revisits_remaining_store"] = _elf_case(
        v13_elf(rows=rows_after(v13_rows(), "rem_store", row("revisit", "bne.n   {to:rem_ptr}"))),
        "success path must publish remaining exactly once: return counts [1, 2]",
    )
    fixtures["alternate_reachable_remaining_store"] = _elf_case(
        v13_elf(
            rows=rows_after(
                rows_after(v13_rows(), "p2_store", row("alt_branch", "bcc.n   {to:alt_ptr}")),
                "succ_return",
                row("alt_ptr", "ldr     r5, [pc, {lit:REMAINING}]"),
                row("alt_store", "str     r1, [r5]"),
                row("alt_result", "mov     r0, r4"),
                row("alt_return", "bx      lr"),
            )
        ),
        "alternate remaining store reachable on the success path",
    )

    fixtures["retained_v12_runtime_drift"] = _elf_case(
        (
            V13_OBJDUMP_OK
            + extras_section(
                "test_u85",
                0x32004000,
                "f7ff f8fe   bl      32004200 <NVIC_EnableIRQ> ; V12_RUNTIME_ENABLE_DRIFT",
            ),
            V13_NM_OK + build_nm(((0x32004000, "test_u85"),)),
        ),
        "retained V12 NVIC enable drift",
    )
    fixtures["retained_v12_iser_direct_enable"] = _elf_case(
        (
            V13_OBJDUMP_OK
            + objdump_section(
                "test_u85",
                0x32004000,
                ("4b02", "ldr", "r3, [pc, #8]  @ (3200400c <test_u85+0xc>)"),
                ("601a", "str", "r2, [r3, #0]"),
                ("4770", "bx", "lr"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            V13_NM_OK + build_nm(((0x32004000, "test_u85"),)),
        ),
        "direct NVIC ISER enable write remains reachable",
    )
    fixtures["duplicate_helper_nm_symbol"] = _elf_case(
        (V13_OBJDUMP_OK, V13_NM_OK + build_nm(((0x32005000, V13_HELPER),))),
        "duplicate poll helper symbol in nm",
    )
    fixtures["ambiguous_v12_and_v13_helper_nm_symbols"] = _elf_case(
        (V13_OBJDUMP_OK, V13_NM_OK + build_nm(((0x32006000, V12_HELPER),))),
        "duplicate poll helper symbol in nm",
    )
    fixtures["duplicate_helper_disassembly_section"] = _elf_case(
        (
            V13_OBJDUMP_OK + extras_section(V13_HELPER, 0x32005000, "4770        bx      lr"),
            V13_NM_OK,
        ),
        "duplicate poll helper section in disassembly",
    )
    return fixtures


def _dataflow_negative_fixtures() -> dict[str, dict[str, str]]:
    """V13 images `prove_remaining_dataflow` must refuse on its own.

    The cross-ELF signature would also reject the drift below -- a `cbnz` back
    edge does not normalize to the V12 `bne` -- but only by comparing it against
    the V12 reference. The live-out proof has to stand on its own instruction
    stream, so it is exercised directly rather than through the paired gate.
    """
    # Control dependency: the loop exits on the flags the back edge reads, so
    # the decrement it reads -- not whichever one happens to sit last in the
    # loop body -- is the countdown the published value must come from. Here the
    # back edge branches on `r1` while the store publishes `r2`, and `r2` is the
    # last decrement in the body, so the layout convention `decrement_regs[-1]`
    # calls it the induction variable even though the loop's exit never reads it.
    return {
        "back_edge_control_dependency_swapped": _elf_case(
            v13_elf(
                rows=rows_retext(
                    rows_retext(
                        rows_retext(
                            rows_retext(v13_rows(), "dec_shadow", "subs    r1, #1"),
                            "dec_induction",
                            "subs    r2, #1",
                        ),
                        "back_edge",
                        "cbnz    r1, {to:loop}",
                    ),
                    "rem_store",
                    "str     r2, [r5]",
                )
            ),
            "back edge must branch on the decrement flags",
        ),
    }


def _elf_case(elf, expected: str) -> dict[str, str]:
    objdump, nm = elf
    return {"objdump": objdump, "nm": nm, "expected": expected}


ELF_NEGATIVE_FIXTURES = _elf_negative_fixtures()
DATAFLOW_NEGATIVE_FIXTURES = _dataflow_negative_fixtures()


def _remaining_after(iteration_index: int) -> int:
    return POLL_LIMIT - iteration_index


SEMANTIC_BOUNDARIES = (
    {"name": "first poll", "remaining": _remaining_after(0), "iterations": 1},
    {"name": "interior poll", "remaining": _remaining_after(4321), "iterations": 4322},
    {"name": "last poll", "remaining": _remaining_after(9999), "iterations": 10000},
)


def _negative_vendor_fixtures() -> dict[str, dict[str, str]]:
    duplicate_store = """            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
"""
    timeout_store = """    pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;
    return 0U;
"""
    second_status_read = """            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            status = *status_reg;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
"""
    extra_mmio = """        (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD);
        status = *status_reg;
"""
    per_iteration_store = """        ++i;
        pmu_completion_poll_v13_t_poll_remaining_at_success = i;
        status = *status_reg;
"""
    return {
        "remaining_before_p2": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n",
                "remaining-before-p2",
            ),
            "expected": "remaining store must follow P2 exactly",
        },
        "duplicate_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                duplicate_store,
                "duplicate-store",
            ),
            "expected": "poll_remaining_at_success store count != 1",
        },
        "timeout_reachable_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    return 0U;\n",
                timeout_store,
                "timeout-store",
            ),
            "expected": "timeout path must not publish remaining",
        },
        "success_remaining_zero": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;\n",
                "remaining-zero",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "success_remaining_10001": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10001U;\n",
                "remaining-10001",
            ),
            "expected": "success remaining must be in 1..10000",
        },
        "per_iteration_increment_store": {
            "vendor": replace_once(
                replace_once(
                    VENDOR_V13_OK,
                    "    uint32_t status;\n",
                    "    uint32_t i = 0U;\n"
                    "    uint32_t status;\n",
                    "per-iteration-counter",
                ),
                "        status = *status_reg;\n",
                per_iteration_store,
                "per-iteration-store",
            ),
            "expected": "remaining store must be success-only",
        },
        "second_status_read": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n",
                second_status_read,
                "second-status-read",
            ),
            "expected": "helper STATUS read count != 1",
        },
        "extra_mmio": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "        status = *status_reg;\n",
                extra_mmio,
                "extra-mmio",
            ),
            "expected": "helper contains forbidden operation",
        },
        "wrong_completion_mask": {
            "vendor": VENDOR_V13_OK.replace("(status & 0x02U)", "(status & 0x04U)", 1),
            "expected": "helper completion mask",
        },
        "retained_v12_hard_bypass": {
            "vendor": VENDOR_V13_OK.replace("return status;", "write_reg(NPU_REG_CMD, 0x00000002);\n            return status;", 1),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
        "retained_v12_qread_release_drift": {
            "vendor": VENDOR_V13_OK.replace(
                "            return status;\n",
                "            read_val = read_reg(NPU_REG_QREAD);\n"
                "            write_reg(NPU_REG_CMD, 0x00000000);\n"
                "            write_reg(NPU_REG_CMD, 0x0000000CU);\n"
                "            return status;\n",
                1,
            ),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
        # Whole-translation-unit uniqueness: a writer that sits outside the
        # slice `_extract_vendor_helper` carves out must still be rejected.
        "second_writer_before_helper": {
            "vendor": SECOND_WRITER_BEFORE_HELPER + VENDOR_V13_OK,
            "expected": "vendor TU remaining write count != 1",
        },
        "second_writer_after_test_commands": {
            "vendor": VENDOR_V13_OK + SECOND_WRITER_AFTER_TEST_COMMANDS,
            "expected": "vendor TU remaining write count != 1",
        },
        "duplicate_helper_definition": {
            "vendor": VENDOR_V13_OK + "\n" + VENDOR_V13_OK,
            "expected": "duplicate V13 poll helper definition",
        },
    }


NEGATIVE_VENDOR_FIXTURES = _negative_vendor_fixtures()


def load_real_runner_stock() -> str:
    with open(REAL_RUNNER_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def maybe_load_env_vendor_stock() -> str | None:
    path = os.environ.get(ENV_VENDOR_KEY)
    if not path:
        return None
    with open(path, "rb") as handle:
        raw = handle.read()
    check(
        "env frozen vendor hash matches V13 pin",
        hashlib.sha256(raw).hexdigest() == VENDOR_SHA256,
    )
    return raw.decode("utf-8", errors="replace")


def run_cli_override_rejection_suite(patcher):
    script_path = patcher.__file__
    real_runner_stock = load_real_runner_stock()
    with tempfile.TemporaryDirectory() as tmp:
        runner_in = os.path.join(tmp, "runner_in.c")
        vendor_in = os.path.join(tmp, "vendor_in.c")
        runner_out = os.path.join(tmp, "runner_out.c")
        vendor_out = os.path.join(tmp, "vendor_out.c")
        with open(runner_in, "w", encoding="utf-8") as handle:
            handle.write(real_runner_stock + "\n/* drift */\n")
        with open(vendor_in, "w", encoding="utf-8") as handle:
            handle.write(PATCH_VENDOR_STOCK)

        drift_runner_sha = hashlib.sha256((real_runner_stock + "\n/* drift */\n").encode("utf-8")).hexdigest()
        cmd = [
            "python3",
            script_path,
            "--runner-in", runner_in,
            "--vendor-in", vendor_in,
            "--runner-out", runner_out,
            "--vendor-out", vendor_out,
            "--expect-runner-sha256", drift_runner_sha,
            "--expect-vendor-sha256", VENDOR_SHA256,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        detail = (result.stdout + result.stderr).strip()
        check(
            "CLI rejects drifted runner even when override SHA matches drift",
            result.returncode != 0 and "runner expected sha override forbidden" in detail,
            detail,
        )

        with open(runner_in, "w", encoding="utf-8") as handle:
            handle.write(real_runner_stock)
        wrong_vendor_sha = "0" * 64
        cmd = [
            "python3",
            script_path,
            "--runner-in", runner_in,
            "--vendor-in", vendor_in,
            "--runner-out", runner_out,
            "--vendor-out", vendor_out,
            "--expect-runner-sha256", RUNNER_SHA256,
            "--expect-vendor-sha256", wrong_vendor_sha,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        detail = (result.stdout + result.stderr).strip()
        check(
            "CLI rejects mismatched expect-vendor override even with pinned inputs",
            result.returncode != 0 and "vendor expected sha override forbidden" in detail,
            detail,
        )


def validate_local_fixtures():
    required_suffix = (
        "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
        "            return status;\n"
    )
    if VENDOR_V13_OK.count("for (uint32_t i = 0U; i < 10000U; ++i) {") != 1:
        raise fail("positive vendor fixture must have exactly one helper loop")
    if required_suffix not in VENDOR_V13_OK:
        raise fail("positive vendor fixture lost V13 success suffix")
    if "uint32_t remaining = 10000U;" in VENDOR_V13_OK or "if (--remaining == 0U) {" in VENDOR_V13_OK:
        raise fail("positive vendor fixture must preserve the V12 for-loop source shape")
    if RUNNER_V13_OK.count("uint32_t poll_remaining_at_success;") != 1:
        raise fail("runner fixture must declare remaining member exactly once")
    if RUNNER_V13_OK.count("if (d.poll_result != V13_POLL_SUCCESS) {") != 1:
        raise fail("runner fixture must expose exactly one timeout gate")
    if RUNNER_V13_OK.count("        d.poll_remaining_at_success = 0U;\n") != 1:
        raise fail("runner fixture must invalidate remaining inside the timeout gate exactly once")
    if RUNNER_V13_OK.count("    pmu_completion_poll_v13_t_poll_remaining_at_success     = 0U;\n") != 1:
        raise fail("runner fixture must keep the column-aligned unrelated global clear reset")
    if RUNNER_V13_OK.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") != 1:
        raise fail("runner fixture must declare remaining field exactly once")
    if RUNNER_V13_OK.count("out_words[100] = d->poll_remaining_at_success;") != 1:
        raise fail("runner fixture must serialize remaining wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_FIELD_COUNT 101U") != 1:
        raise fail("runner fixture must pin field count for appended wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_TOTAL_WORDS 109U") != 1:
        raise fail("runner fixture must pin total words for appended wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_PAYLOAD_SIZE 436U") != 1:
        raise fail("runner fixture must pin payload size for appended wire word exactly once")
    if RUNNER_V12_GENERATED.count("PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID") != 1:
        raise fail("generated V12 raw-input rejection fixture malformed")
    if RUNNER_SHA256 != "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b":
        raise fail("pinned runner raw SHA constant drifted")
    if VENDOR_SHA256 != "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf":
        raise fail("pinned vendor raw SHA constant drifted")
    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        if payload["vendor"] == VENDOR_V13_OK:
            raise fail("negative fixture is a no-op: %s" % name)
    if V12_NM_OK.count("v12_poll_completion") != 1 or V13_NM_OK.count("v13_poll_completion") != 1:
        raise fail("synthetic nm fixtures must define exactly one helper symbol each")
    for label, rows in (("V12", v12_rows()), ("V13", v13_rows())):
        labels = [item["label"] for item in rows]
        if len(set(labels)) != len(labels):
            raise fail("%s synthetic row labels must be unique" % label)
        if labels.count("loop") != 1 or labels.count("test") != 1 or labels.count("back_edge") != 1:
            raise fail("%s synthetic helper must expose exactly one poll iteration" % label)
        if labels[labels.index("succ_branch") + 1:labels.index("back_edge")] != [
            "dec_shadow",
            "dec_induction",
        ]:
            raise fail("%s synthetic failed path must be exactly two decrements" % label)
    v13_labels = [item["label"] for item in v13_rows()]
    if v13_labels.index("rem_store") < v13_labels.index("p2_store"):
        raise fail("V13 synthetic helper must keep the remaining store after P2")
    if [item["label"] for item in v12_rows()] != [
        label for label in v13_labels if label not in ("rem_ptr", "rem_store")
    ]:
        raise fail("V13 synthetic helper must be the V12 helper plus the remaining store")

    # The fixture builder is only trustworthy if its PC-relative offsets really
    # do resolve under the same Thumb rule the gate applies, so re-derive them
    # here from the emitted text rather than trusting the layout pass.
    for label, text in (("V12", V12_OBJDUMP_OK), ("V13", V13_OBJDUMP_OK)):
        slots = {
            int(hit.group(1), 16)
            for hit in re.finditer(r"^([0-9a-f]+):\s+\.word", text, re.M)
        }
        loads = re.findall(r"^([0-9a-f]+):\s+\S+\s+ldr\S*\s+r\d+, \[pc, #(\d+)\]", text, re.M)
        if not loads:
            raise fail("%s synthetic helper must use PC-relative literal loads" % label)
        for at, offset in loads:
            if (((int(at, 16) + 4) & ~3) + int(offset)) not in slots:
                raise fail("%s synthetic PC-relative load misses the literal pool" % label)
        if len(loads) != len(slots):
            raise fail("%s synthetic literal pool must be fully referenced" % label)

    for name, payload in list(ELF_NEGATIVE_FIXTURES.items()) + list(DATAFLOW_NEGATIVE_FIXTURES.items()):
        if payload["objdump"] == V13_OBJDUMP_OK and payload["nm"] == V13_NM_OK:
            raise fail("synthetic ELF negative fixture is a no-op: %s" % name)
    for label, (objdump, nm) in V13_ACCEPTED_VARIANTS:
        if (objdump, nm) == (V13_OBJDUMP_OK, V13_NM_OK):
            raise fail("accepted V13 variant is a no-op: %s" % label)
    for label, (objdump, nm) in V12_DRIFTED_REFERENCES:
        if (objdump, nm) == (V12_OBJDUMP_OK, V12_NM_OK):
            raise fail("drifted V12 reference is a no-op: %s" % label)


def run_retained_runtime_suite(gate):
    """Retained-V12 runtime callee list: only NVIC *enable* is drift."""
    try:
        evidence = gate.verify_cross_elf_contract(
            V12_OBJDUMP_OK, V12_NM_OK, V13_RETAINED_STOCK_OBJDUMP, V13_RETAINED_STOCK_NM
        )
        check(
            "retained runtime gate accepts stock NVIC_SetVector and NVIC_ClearPendingIRQ call sites",
            evidence.get("loop_equivalent") is True,
            str(evidence),
        )
    except Exception as exc:
        check(
            "retained runtime gate accepts stock NVIC_SetVector and NVIC_ClearPendingIRQ call sites",
            False,
            str(exc),
        )

    for label, text, expected in (
        (
            "stock vector install alone is not drift",
            "32004000 <test_u85>:\n"
            "32004000:   f7ff f97e   bl      32004300 <NVIC_SetVector> ; V13_RUNTIME_VECTOR_INSTALL\n",
            None,
        ),
        (
            "stock pending clear alone is not drift",
            "32004000 <test_u85>:\n"
            "32004000:   f7ff f9fc   bl      32004400 <NVIC_ClearPendingIRQ> ; V13_RUNTIME_CLEAR_PENDING\n",
            None,
        ),
        (
            "NVIC enable call site is drift",
            "32004000 <test_u85>:\n"
            "32004000:   f7ff f8fe   bl      32004200 <NVIC_EnableIRQ> ; V13_RUNTIME_ENABLE_DRIFT\n",
            "retained V12 NVIC enable drift",
        ),
        (
            "direct ISER[0] enable store is drift",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("601a", "str", "r2, [r3, #0]"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            "direct NVIC ISER enable write remains reachable",
        ),
        (
            "direct ISER[15] enable store is drift",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("f8c3 203c", "str.w", "r2, [r3, #60] @ 0x3c"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            "direct NVIC ISER enable write remains reachable",
        ),
        (
            "ICER clear through the NVIC base literal is not drift",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("f8c3 2080", "str.w", "r2, [r3, #128] @ 0x80"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            None,
        ),
        (
            "ISER reached by a negative displacement off the ICER base is drift",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("f8c3 2080", "str.w", "r2, [r3, #-128] @ 0x80"),
                ("e000e180", ".word", "0xe000e180"),
            ),
            "direct NVIC ISER enable write remains reachable",
        ),
        (
            "unresolvable store through an NVIC-block base fails closed",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b02", "ldr", "r3, [pc, #8]  @ (3200400c <test_u85+0xc>)"),
                ("4419", "add", "r1, r3"),
                ("600a", "str", "r2, [r1, #0]"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            "NVIC-block store destination unresolvable",
        ),
        (
            "register-offset store through an NVIC-block base fails closed",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("509a", "str", "r2, [r3, r2]"),
                ("e000e100", ".word", "0xe000e100"),
            ),
            "NVIC-block store destination unresolvable",
        ),
        (
            "a store through an unrelated base is not drift",
            objdump_section(
                "test_u85",
                0x32004000,
                ("4b01", "ldr", "r3, [pc, #4]  @ (32004008 <test_u85+0x8>)"),
                ("601a", "str", "r2, [r3, #0]"),
                ("e000ed00", ".word", "0xe000ed00"),
            ),
            None,
        ),
    ):
        try:
            gate._check_retained_v12_runtime(text)
            check("retained runtime callee list: %s" % label, expected is None, "unexpected pass")
        except Exception as exc:
            check(
                "retained runtime callee list: %s" % label,
                expected is not None and expected in str(exc),
                str(exc),
            )


def run_real_image_nvic_suite(gate):
    """The retained NVIC gate, run against the real MPS4 ARM disassembly.

    ``0xE000E100`` is CMSIS ``NVIC_BASE`` as well as ``ISER[0]``, so the stock
    hard bypass loads it as a literal and then writes ICER (``+128``) and ICPR
    (``+384``) through it. A whole-image text search for that word cannot tell
    the required clears from a re-introduced enable; only the resolved store
    destination can. This suite pins that distinction on the one real image the
    repository carries rather than on a hand-built fixture.
    """
    from test_check_pmu_completion_poll_v12 import REAL_ARM_DISASSEMBLY

    icer_store = "310025e2:\tf8c3 0080 \tstr.w\tr0, [r3, #128] @ 0x80"
    icpr_store = "310025ee:\tf8c3 0180 \tstr.w\tr0, [r3, #384] @ 0x180"

    for label, text, expected in (
        (
            "known-good real image with ICER/ICPR through the NVIC base literal",
            REAL_ARM_DISASSEMBLY,
            None,
        ),
        (
            "real ICER store retargeted to ISER[0] is drift",
            replace_once(
                REAL_ARM_DISASSEMBLY,
                icer_store,
                "310025e2:\tf8c3 0000 \tstr.w\tr0, [r3, #0]",
                "real ICER store",
            ),
            "direct NVIC ISER enable write remains reachable",
        ),
        (
            "real ICPR store retargeted to ISER[15] is drift",
            replace_once(
                REAL_ARM_DISASSEMBLY,
                icpr_store,
                "310025ee:\tf8c3 003c \tstr.w\tr0, [r3, #60] @ 0x3c",
                "real ICPR store",
            ),
            "direct NVIC ISER enable write remains reachable",
        ),
        (
            "real ICER store moved into the reserved gap above ISER is not an enable",
            replace_once(
                REAL_ARM_DISASSEMBLY,
                icer_store,
                "310025e2:\tf8c3 0040 \tstr.w\tr0, [r3, #64] @ 0x40",
                "real ICER store",
            ),
            None,
        ),
        (
            "an objdump comment naming the NVIC base is not drift",
            REAL_ARM_DISASSEMBLY.replace(
                icpr_store, icpr_store + "  @ NVIC_BASE 0xe000e100", 1
            ),
            None,
        ),
    ):
        try:
            gate._check_retained_v12_runtime(text)
            check("real-image NVIC gate: %s" % label, expected is None, "unexpected pass")
        except Exception as exc:
            check(
                "real-image NVIC gate: %s" % label,
                expected is not None and expected in str(exc),
                str(exc),
            )


def run_raw_provenance_suite(gate):
    """Raw SHA pins are a pair: both frozen inputs are validated, or neither."""
    runner_stock = load_real_runner_stock()
    vendor_stock_sha = sha256_text(PATCH_VENDOR_STOCK)

    try:
        evidence = gate.verify_generated_sources(
            runner_stock,
            PATCH_VENDOR_STOCK,
            raw_runner_sha256=RUNNER_SHA256,
            raw_vendor_sha256=vendor_stock_sha,
        )
        check(
            "raw provenance accepts both pins over both frozen inputs",
            evidence.get("schema_version") == SCHEMA_VERSION,
            str(evidence),
        )
    except Exception as exc:
        check("raw provenance accepts both pins over both frozen inputs", False, str(exc))

    # The whole-TU scan and the helper scan must agree on which assignment is
    # canonical; a disagreement fails closed rather than silently accepting.
    try:
        gate._verify_vendor_tu_single_writer(VENDOR_V13_OK, 0)
        check("raw provenance rejects non-canonical single TU writer", False, "unexpected pass")
    except Exception as exc:
        check(
            "raw provenance rejects non-canonical single TU writer",
            "vendor TU remaining write must be the canonical helper success assignment" in str(exc),
            str(exc),
        )

    for label, kwargs in (
        ("runner-only raw pin leaves the vendor input unvalidated", {"raw_runner_sha256": RUNNER_SHA256}),
        ("vendor-only raw pin leaves the runner input unvalidated", {"raw_vendor_sha256": vendor_stock_sha}),
    ):
        try:
            gate.verify_generated_sources(runner_stock, PATCH_VENDOR_STOCK, **kwargs)
            check("raw provenance rejects %s" % label, False, "unexpected pass")
        except Exception as exc:
            check(
                "raw provenance rejects %s" % label,
                "raw runner and vendor sha pins must be supplied together" in str(exc),
                str(exc),
            )


def run_runner_gate_suite(gate, runner_out, vendor_out):
    """Timeout/success gate on the generated runner, independent of column alignment."""
    timeout_reset = "            d.poll_remaining_at_success = 0U;\n"
    aligned_clear = "    pmu_completion_poll_v13_t_poll_remaining_at_success     = 0U;\n"
    tight_clear = "    pmu_completion_poll_v13_t_poll_remaining_at_success = 0U;\n"
    copy_line = (
        "        d.poll_remaining_at_success       = "
        "pmu_completion_poll_v13_t_poll_remaining_at_success;\n"
    )
    gate_tail = timeout_reset + "        }\n"

    # Reproduced defect: deleting the timeout invalidation while re-aligning the
    # unrelated global clear keeps a naive substring count at exactly one.
    reproduced = replace_once(runner_out, timeout_reset, "", "timeout-reset-delete")
    reproduced = replace_once(reproduced, aligned_clear, tight_clear, "clear-reset-reformat")
    check(
        "reproduced drift keeps the naive single-match substring count",
        reproduced.count("poll_remaining_at_success = 0U;") == 1,
        "count=%d" % reproduced.count("poll_remaining_at_success = 0U;"),
    )
    try:
        gate.verify_generated_sources(reproduced, vendor_out)
        check("runner gate rejects deleted timeout reset with reformatted clear reset", False, "unexpected pass")
    except Exception as exc:
        check(
            "runner gate rejects deleted timeout reset with reformatted clear reset",
            "runner timeout gate must reset remaining to 0U" in str(exc),
            str(exc),
        )

    for label, mutated, expected in (
        (
            "timeout reset moved outside the gate",
            replace_once(
                runner_out,
                gate_tail,
                "        }\n        d.poll_remaining_at_success = 0U;\n",
                "reset-move",
            ),
            "runner timeout gate must reset remaining to 0U",
        ),
        (
            "extra publishing write after the timeout gate",
            replace_once(
                runner_out,
                gate_tail,
                gate_tail
                + "        d.poll_remaining_at_success = pmu_completion_poll_v13_t_poll_remaining_at_success;\n",
                "extra-publish",
            ),
            "runner remaining write count != 2",
        ),
        (
            "success copy replaced by a constant",
            replace_once(runner_out, copy_line, "        d.poll_remaining_at_success = 1U;\n", "constant-copy"),
            "runner success copy must read the V13 remaining global",
        ),
        (
            "success copy sunk below the timeout gate",
            replace_once(
                replace_once(runner_out, copy_line, "", "copy-sink-delete"),
                gate_tail,
                gate_tail + copy_line,
                "copy-sink-insert",
            ),
            "runner success copy must precede the timeout gate",
        ),
        (
            "timeout gate removed entirely",
            replace_once(
                runner_out,
                "        if (d.poll_result != V13_POLL_SUCCESS) {\n",
                "        if (0) {\n",
                "gate-removed",
            ),
            "runner timeout gate: expected 1 match",
        ),
    ):
        try:
            gate.verify_generated_sources(mutated, vendor_out)
            check("runner gate rejects %s" % label, False, "unexpected pass")
        except Exception as exc:
            check("runner gate rejects %s" % label, expected in str(exc), str(exc))

    for label, reformatted in (
        ("re-aligned unrelated global clear reset", replace_once(runner_out, aligned_clear, tight_clear, "clear-realign")),
        (
            "re-aligned success copy",
            replace_once(
                runner_out,
                copy_line,
                "        d.poll_remaining_at_success = pmu_completion_poll_v13_t_poll_remaining_at_success;\n",
                "copy-realign",
            ),
        ),
        (
            "re-indented timeout reset",
            replace_once(runner_out, timeout_reset, "\t\t\td.poll_remaining_at_success  =  0U;\n", "reset-realign"),
        ),
    ):
        try:
            gate.verify_generated_sources(reformatted, vendor_out)
            check("runner gate accepts %s" % label, True)
        except Exception as exc:
            check("runner gate accepts %s" % label, False, str(exc))


def run_future_elf_suite(gate):
    v12_loop = gate.extract_poll_loop(V12_OBJDUMP_OK, V12_NM_OK)
    v13_loop = gate.extract_poll_loop(V13_OBJDUMP_OK, V13_NM_OK)
    evidence = gate.verify_cross_elf_contract(V12_OBJDUMP_OK, V12_NM_OK, V13_OBJDUMP_OK, V13_NM_OK)

    check(
        "future ELF gate normalizes V12 and V13 loop effects identically",
        gate.normalize_poll_loop(v12_loop) == gate.normalize_poll_loop(v13_loop),
    )
    loop_equivalent = getattr(evidence, "loop_equivalent", None) if not isinstance(evidence, dict) else evidence.get("loop_equivalent")
    check(
        "future ELF gate accepts canonical V12/V13 pair through authoritative contract",
        loop_equivalent is True,
        str(evidence),
    )

    proof = gate.prove_remaining_dataflow(V13_OBJDUMP_OK, V13_NM_OK)
    source = getattr(proof, "source", None) if not isinstance(proof, dict) else proof.get("source")
    check(
        "future ELF gate proves remaining live-out comes from back-edge induction",
        source == "back_edge_induction",
        str(proof),
    )

    # Re-derive the control dependency straight from the fixture text: the
    # register the back edge branches on is the one the `subs` immediately
    # before it writes, and that is the register the proof must name.
    v13_labels = [item["label"] for item in v13_rows()]
    back_edge_decrement = v13_rows()[v13_labels.index("back_edge") - 1]["text"]
    expected_induction = re.match(r"subs\s+(r\d+),", back_edge_decrement).group(1)
    reported = getattr(proof, "induction_register", None) if not isinstance(proof, dict) else proof.get("induction_register")
    check(
        "proved induction register is the one the back edge branches on",
        reported == expected_induction,
        "reported=%s expected=%s" % (reported, expected_induction),
    )

    # The two live-out booleans must record what the graph and the checks found,
    # so a future regression that stops proving them shows up as a False verdict
    # instead of an unconditional True the dataclass carries for free.
    with open(gate.__file__, "r", encoding="utf-8") as handle:
        gate_source = handle.read()
    check(
        "live-out proof booleans are derived, not literal True assignments",
        "remaining_from_back_edge_induction=True" not in gate_source
        and "helper_leaf_no_stack_access=True" not in gate_source,
    )
    check(
        "live-out proof booleans are reported True for the canonical helper",
        getattr(proof, "remaining_from_back_edge_induction", None) is True
        and getattr(proof, "helper_leaf_no_stack_access", None) is True,
        str(proof),
    )

    canonical_signature = gate.normalize_poll_loop(v13_loop)
    check(
        "normalized signature is derived from the parsed stream, not constants",
        dict(canonical_signature).get("status_read_op") == "ldr"
        and dict(canonical_signature).get("failed_path_ops") == "subs|subs"
        and dict(canonical_signature).get("per_iteration_instruction_count") == 6,
        str(canonical_signature),
    )

    for label, (objdump, nm) in V13_ACCEPTED_VARIANTS:
        try:
            variant = gate.extract_poll_loop(objdump, nm)
            evidence = gate.verify_cross_elf_contract(V12_OBJDUMP_OK, V12_NM_OK, objdump, nm)
            check(
                "future ELF gate accepts %s under an unchanged signature" % label,
                gate.normalize_poll_loop(variant) == canonical_signature
                and evidence.get("loop_equivalent") is True,
                str(gate.normalize_poll_loop(variant)),
            )
        except Exception as exc:
            check("future ELF gate accepts %s under an unchanged signature" % label, False, str(exc))

    for label, (objdump, nm) in V12_DRIFTED_REFERENCES:
        try:
            drifted = gate.extract_poll_loop(objdump, nm)
            check(
                "drifted V12 reference (%s) still clears its own structural gate" % label,
                gate.normalize_poll_loop(drifted) != canonical_signature,
                str(gate.normalize_poll_loop(drifted)),
            )
        except Exception as exc:
            check(
                "drifted V12 reference (%s) still clears its own structural gate" % label,
                False,
                str(exc),
            )
        try:
            gate.verify_cross_elf_contract(objdump, nm, V13_OBJDUMP_OK, V13_NM_OK)
            check("cross-ELF mismatch gate fires for %s" % label, False, "unexpected pass")
        except Exception as exc:
            check(
                "cross-ELF mismatch gate fires for %s" % label,
                "V12/V13 normalized poll loop mismatch" in str(exc),
                str(exc),
            )

    for name, payload in ELF_NEGATIVE_FIXTURES.items():
        try:
            gate.verify_cross_elf_contract(V12_OBJDUMP_OK, V12_NM_OK, payload["objdump"], payload["nm"])
            check("future ELF gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future ELF gate rejects %s" % name, payload["expected"] in str(exc), str(exc))

    for name, payload in DATAFLOW_NEGATIVE_FIXTURES.items():
        try:
            gate.prove_remaining_dataflow(payload["objdump"], payload["nm"])
            check("live-out proof rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("live-out proof rejects %s" % name, payload["expected"] in str(exc), str(exc))


def run_generator_suite(patcher):
    real_runner_stock = load_real_runner_stock()
    check(
        "real frozen runner hash matches V13 pin",
        hashlib.sha256(real_runner_stock.encode("utf-8")).hexdigest() == RUNNER_SHA256,
    )
    env_vendor_stock = maybe_load_env_vendor_stock()
    if env_vendor_stock is not None:
        env_vendor_out, env_vendor_meta = patcher.patch_vendor(env_vendor_stock)
        check(
            "env frozen vendor default patch succeeds",
            env_vendor_out.count("v13_poll_completion(void)") == 1,
        )
        check(
            "env frozen vendor patch counts recorded",
            isinstance(env_vendor_meta, dict) and bool(env_vendor_meta),
        )

    runner_out, runner_meta = patcher.patch_runner(real_runner_stock)
    vendor_out, vendor_meta = patcher.patch_vendor(PATCH_VENDOR_STOCK)

    check("runner patch returns replacements", isinstance(runner_meta, dict) and bool(runner_meta))
    check("vendor patch returns replacements", isinstance(vendor_meta, dict) and bool(vendor_meta))
    check("runner patch sets schema 13", "#define PMU_DIAG_SCHEMA_VERSION 13U" in runner_out)
    check("runner patch pins build id 0x33314950", "#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U" in runner_out)
    check(
        "runner patch declares remaining record field exactly once",
        runner_out.count("uint32_t poll_remaining_at_success;") == 1
        and runner_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") >= 1
        and runner_out.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") == 1,
    )
    check("runner patch resets invalid remaining sentinel", "poll_remaining_at_success = 0U;" in runner_out)
    check(
        "runner patch appends exactly one remaining wire word",
        runner_out.count("put32(&c, d->poll_remaining_at_success);") == 1
        and "PMU_DIAG_FIELD_COUNT == 101U" in runner_out
        and "PMU_DIAG_TOTAL_WORDS == 109U" in runner_out
        and "PMU_DIAG_PAYLOAD_SIZE == 436U" in runner_out,
    )
    check("vendor patch emits V13 helper symbol", "v13_poll_completion" in vendor_out)
    check(
        "vendor patch appends one remaining word",
        vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 2
        and vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;") == 1,
    )
    check(
        "vendor patch emits exact success suffix",
        (
            "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;\n"
            "            return status;"
        ) in vendor_out,
    )
    check(
        "vendor patch preserves V12 for-loop source with post-P2 publication",
        "for (uint32_t i = 0U; i < 10000U; ++i) {" in vendor_out
        and "pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;" in vendor_out
        and "if (--remaining == 0U) {" not in vendor_out,
    )
    check(
        "vendor timeout path does not publish remaining",
        "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;\n    return 0U;" not in vendor_out,
    )
    try:
        patcher.patch_runner(load_real_runner_stock() + "\n#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n#endif\n")
        check("runner patch rejects generated V11 input", False, "unexpected pass")
    except BaseException as exc:
        check("runner patch rejects generated V11 input", "V11 marker" in str(exc), str(exc))
    try:
        patcher.patch_vendor(PATCH_VENDOR_STOCK + "\nvolatile uint32_t pmu_interval_v11a_t_vector_probe;\n")
        check("vendor patch rejects generated V11 input", False, "unexpected pass")
    except BaseException as exc:
        check("vendor patch rejects generated V11 input", "V11 marker" in str(exc), str(exc))

    for boundary in SEMANTIC_BOUNDARIES:
        remaining = boundary["remaining"]
        iterations = boundary["iterations"]
        check(
            "semantic boundary %s maps remaining to iterations" % boundary["name"],
            1 <= remaining <= 10000 and iterations == (10001 - remaining),
            "remaining=%d iterations=%d" % (remaining, iterations),
        )
    check("timeout semantic keeps invalid remaining sentinel", INVALID_REMAINING == 0)
    return runner_out, vendor_out


def run_future_suite(gate, patcher):
    runner_out, vendor_out = run_generator_suite(patcher)

    try:
        evidence = gate.verify_generated_sources(runner_out, vendor_out)
        check(
            "future V13 gate accepts canonical generated sources",
            evidence.get("schema_version") == SCHEMA_VERSION
            and evidence.get("build_id") == BUILD_ID
            and evidence.get("poll_remaining_symbol") == "pmu_completion_poll_v13_t_poll_remaining_at_success",
        )
    except Exception as exc:
        check("future V13 gate accepts canonical generated sources", False, str(exc))
        evidence = None

    for wrong_runner, wrong_vendor, label, expected_reason in (
        (load_real_runner_stock() + "\n/* drift */\n", PATCH_VENDOR_STOCK, "runner hash mismatch", "runner hash mismatch"),
        (load_real_runner_stock(), PATCH_VENDOR_STOCK + "\n/* drift */\n", "vendor hash mismatch", "vendor hash mismatch"),
        (RUNNER_V12_GENERATED, PATCH_VENDOR_STOCK, "generated V12 runner as raw input", "generated runner input"),
        (load_real_runner_stock(), VENDOR_V12_GENERATED, "generated V12 vendor as raw input", "generated vendor input"),
        (load_real_runner_stock() + load_real_runner_stock(), PATCH_VENDOR_STOCK, "multiple raw runner targets", "multiple raw runner targets"),
        ("/* missing helper */\n", PATCH_VENDOR_STOCK, "zero raw runner targets", "zero raw runner targets"),
        (load_real_runner_stock(), PATCH_VENDOR_STOCK + PATCH_VENDOR_STOCK, "multiple raw vendor targets", "multiple raw vendor targets"),
        (load_real_runner_stock(), "/* missing helper */\n", "zero raw vendor targets", "zero raw vendor targets"),
    ):
        try:
            gate.verify_generated_sources(
                wrong_runner,
                wrong_vendor,
                raw_runner_sha256=RUNNER_SHA256,
                raw_vendor_sha256=VENDOR_SHA256,
            )
            check("future V13 gate rejects %s" % label, False, "unexpected pass")
        except TypeError:
            check("future V13 gate rejects %s" % label, False, "verify_generated_sources signature still missing V13 raw-input contract")
        except Exception as exc:
            check("future V13 gate rejects %s" % label, expected_reason in str(exc), str(exc))

    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        try:
            gate.verify_generated_sources(RUNNER_V13_OK, payload["vendor"])
            check("future V13 gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future V13 gate rejects %s" % name, payload["expected"] in str(exc), str(exc))

    run_raw_provenance_suite(gate)
    run_runner_gate_suite(gate, runner_out, vendor_out)

    return evidence


if __name__ == "__main__":
    validate_local_fixtures()

    check("fixture schema version is 13", SCHEMA_VERSION == 13)
    check("fixture build id is 0x33314950", BUILD_ID == "0x33314950")
    check("raw runner SHA pin matches frozen contract", RUNNER_SHA256 == "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b")
    check("raw vendor SHA pin matches frozen contract", VENDOR_SHA256 == "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf")
    check("positive vendor stores remaining exactly once", VENDOR_V13_OK.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check("positive vendor timeout publishes no remaining", "return 0U;" in VENDOR_V13_OK and "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;" not in VENDOR_V13_OK)
    check(
        "runner fixture pins concrete V13 ABI values",
        "#define PMU_DIAG_FIELD_COUNT 101U" in RUNNER_V13_OK
        and "#define PMU_DIAG_TOTAL_WORDS 109U" in RUNNER_V13_OK
        and "#define PMU_DIAG_PAYLOAD_SIZE 436U" in RUNNER_V13_OK,
    )
    check(
        "source negative fixture set matches intended drift list",
        set(NEGATIVE_VENDOR_FIXTURES) == EXPECTED_SOURCE_NEGATIVE_FIXTURES,
    )
    check("synthetic ELF negative fixture count covers required drifts", len(ELF_NEGATIVE_FIXTURES) >= 34)
    check(
        "per-iteration gap drifts are covered on both sides of the completion test",
        {"gap_extra_mov", "gap_dwt_read", "gap_sram_store", "gap_barrier", "gap_call"}
        <= set(ELF_NEGATIVE_FIXTURES),
    )
    check(
        "literal-binding drifts are covered",
        {
            "decoy_status_literal",
            "decoy_dwt_literal",
            "bogus_literal_offset",
            "status_pointer_into_sram",
            "cycle_count_read_from_sram",
            "remaining_reuses_p2_destination",
        }
        <= set(ELF_NEGATIVE_FIXTURES),
    )
    check(
        "displacement drifts are covered on every resolved address",
        {
            "status_read_displaced_off_register",
            "cycle_count_read_displaced_off_cyccnt",
            "publication_displaced_off_slot",
        }
        <= set(ELF_NEGATIVE_FIXTURES),
    )
    check(
        "CFG reachability drifts are covered on both helper exits",
        {
            "timeout_branches_to_remaining_store",
            "success_branch_skips_remaining_store",
            "success_returns_before_remaining_store",
            "success_branch_revisits_remaining_store",
            "alternate_reachable_remaining_store",
        }
        <= set(ELF_NEGATIVE_FIXTURES),
    )
    check(
        "unmodelled success-path effects are covered",
        {
            "ldrd_reloads_remaining_register",
            "it_block_predicates_remaining_register",
            "predicated_move_without_it_header",
            "rrx_recomputes_remaining_register",
            "unrelated_rrx_recompute",
        }
        <= set(ELF_NEGATIVE_FIXTURES),
    )
    check(
        "back-edge control dependency drift is covered by the standalone live-out proof",
        "back_edge_control_dependency_swapped" in DATAFLOW_NEGATIVE_FIXTURES,
    )
    check(
        "boundary semantics cover first interior last and timeout invalid",
        [item["remaining"] for item in SEMANTIC_BOUNDARIES] == [10000, 5679, 1] and INVALID_REMAINING == 0,
    )

    import patches.patch_pmu_completion_poll_count_v13 as patcher

    run_generator_suite(patcher)
    run_cli_override_rejection_suite(patcher)

    import check_pmu_completion_poll_count_v13 as gate

    run_future_suite(gate, patcher)
    run_future_elf_suite(gate)
    run_retained_runtime_suite(gate)
    run_real_image_nvic_suite(gate)

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
