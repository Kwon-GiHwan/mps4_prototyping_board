"""Milestone 1 for the PMU candidate: runtime instrumentation_mode, NPU PMU
cycle counter only. Applied to Selftest_pmu/runner_pmu_main.c.

Design constraints this patch encodes:
  - B and C are the SAME BIN. OFF vs END_ONLY is a runtime branch, never a
    compile-time one, and OFF performs ZERO PMU MMIO accesses.
  - Register geometry comes from the generated npu_pmu_regs.h, never retyped.
  - The cycle counter is 48-bit, held in a uint64_t and sent as two words.
  - Event slots are fixed at 8 (the U85 hardware maximum) from the start, so
    widening later cannot force another ABI change. Milestone 1 activates none
    of them: active_event_counter_count is 0 and event_valid_mask is 0.
"""

import re
import sys

F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()
orig = s


def sub1(old, new, what):
    global s
    if s.count(old) != 1:
        sys.exit("FAIL %s: expected exactly 1 match, found %d" % (what, s.count(old)))
    s = s.replace(old, new)


# --- 1. include the generated register map -------------------------------
sub1('#define U85_BASE_ADDRESS 0x50004000U',
     '#include "npu_pmu_regs.h"\n\n#define U85_BASE_ADDRESS 0x50004000U',
     "include npu_pmu_regs.h")

# --- 2. instrumentation mode state ---------------------------------------
sub1('#define CMD_RESET_RUNNER      0x50U',
     '#define CMD_RESET_RUNNER      0x50U\n'
     '#define CMD_SET_INSTRUMENTATION_MODE 0x05U',
     "new command id")

sub1('/* unsolicited */\n#define CMD_RUN_COMPLETE 0x31U',
     '/* unsolicited */\n#define CMD_RUN_COMPLETE 0x31U\n'
     '\n'
     '/* ------------------------------------------------------------------------ */\n'
     '/* Instrumentation mode. THE POINT OF THIS BUILD: configurations B and C are */\n'
     '/* the same three BINs and differ only by this runtime value, so a B/C delta */\n'
     '/* cannot be explained by code layout, vector addresses or linker placement. */\n'
     '/* In OFF the PMU registers are never read and never written.               */\n'
     '#define INSTRUMENTATION_OFF       0U\n'
     '#define INSTRUMENTATION_END_ONLY  1U\n'
     '#define RUNNER_MAX_NPU_EVENT_COUNTERS NPU_PMU_EVENT_COUNTERS_MAX\n',
     "instrumentation mode defines")

# --- 3. PMU helpers, placed just after npu_read ---------------------------
anchor = "    return REG32(U85_BASE_ADDRESS + offset);\n}"
helpers = anchor + r'''

static void npu_write(uint32_t offset, uint32_t value)
{
    REG32(U85_BASE_ADDRESS + offset) = value;
}

/* Runtime instrumentation state. Defaults to OFF so a freshly booted image
 * behaves exactly like the MEASURE baseline until a host asks otherwise. */
static uint32_t instrumentation_mode          = INSTRUMENTATION_OFF;
static uint32_t active_event_counter_count    = 0U;
static uint32_t instrumentation_event_set_id  = 0U;

/* How many event counters the HARDWARE has. Read from PMCR.num_event_cnt
 * rather than assumed: the constant 8 in the vendor header is a build-time
 * claim, this is the device answering for itself. Sampled lazily so that OFF
 * mode never touches the PMU. */
static uint32_t npu_pmu_hw_event_counters(void)
{
    uint32_t pmcr = npu_read(NPU_REG_PMCR);
    return (pmcr & NPU_PMCR_NUM_EVENT_CNT_MSK) >> NPU_PMCR_NUM_EVENT_CNT_POS;
}

static void npu_pmu_disable(void)
{
    npu_write(NPU_REG_PMCR, npu_read(NPU_REG_PMCR) & ~NPU_PMCR_CNT_EN_MSK);
}

static void npu_pmu_enable(void)
{
    npu_write(NPU_REG_PMCR, npu_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
}

/* Clear every overflow flag, then every counter. Stale state from a previous
 * run must not be attributable to this one. */
static void npu_pmu_reset_counters(void)
{
    npu_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
    npu_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
    npu_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);
    npu_write(NPU_REG_PMCR,
              npu_read(NPU_REG_PMCR) | NPU_PMCR_CYCLE_CNT_RST_MSK
                                     | NPU_PMCR_EVENT_CNT_RST_MSK);
}

/* The cycle counter is 48 bits across two registers and the vendor header
 * documents NO latch or atomic-read semantics -- the reference driver just
 * reads LO then HI, which can tear if LO wraps between the two reads. Read
 * HI, LO, HI and retry while HI moved. The bound is small because HI can
 * advance at most once per 2^32 NPU cycles. */
#define NPU_PMU_CYCLE_READ_TRIES 4U

static uint64_t npu_pmu_read_cycles(uint32_t *stable_out)
{
    uint32_t hi1, lo, hi2;
    uint32_t tries;

    for (tries = 0U; tries < NPU_PMU_CYCLE_READ_TRIES; tries++) {
        hi1 = npu_read(NPU_REG_PMCCNTR_HI);
        lo  = npu_read(NPU_REG_PMCCNTR);
        hi2 = npu_read(NPU_REG_PMCCNTR_HI);
        if (hi1 == hi2) {
            if (stable_out != 0) {
                *stable_out = 1U;
            }
            return ((uint64_t)(hi1 & 0xFFFFU) << 32) | (uint64_t)lo;
        }
    }
    /* Never observed in practice; reported rather than papered over. */
    if (stable_out != 0) {
        *stable_out = 0U;
    }
    return ((uint64_t)(hi2 & 0xFFFFU) << 32) | (uint64_t)lo;
}'''
sub1(anchor, helpers, "PMU helper functions")

# --- 4. record fields -----------------------------------------------------
sub1('''    uint32_t result_region_crc; /* CRC of the WHOLE .sec_noinit after the run */
} measurement_record_t;''',
     '''    uint32_t result_region_crc; /* CRC of the WHOLE .sec_noinit after the run */
    /* --- appended for the PMU candidate, milestone 1. Order above untouched. */
    uint32_t instrumentation_mode;       /* OFF / END_ONLY, as actually run    */
    uint32_t event_set_id;               /* which event set was requested      */
    uint32_t npu_pmu_present;            /* PMCR readable and sane             */
    uint32_t hw_event_counter_count;     /* from PMCR.num_event_cnt, U85: 8    */
    uint32_t active_event_counter_count; /* 0 in milestone 1 (cycle-only)      */
    uint32_t event_valid_mask;           /* bit n set => event_values[n] real  */
    uint32_t event_overflow_mask;        /* bit n set => counter n overflowed  */
    uint32_t event_codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    uint32_t event_values[RUNNER_MAX_NPU_EVENT_COUNTERS];
    /* 48-bit cycle counter, split for the wire. NAMED "window", not
     * "execution": the snapshot is taken as soon as run_fixed_inference()
     * returns, not inside the completion ISR, because u85.c reinstalls its own
     * NPU vector (see the hijack note). The value therefore includes the
     * driver's post-completion path and any idle between PMU enable and the
     * first NPU command. Promote the name only after the PMCCNTR_CFG
     * hardware start/stop boundary has been cross-checked against it. */
    uint32_t npu_pmu_window_cycles_lo;
    uint32_t npu_pmu_window_cycles_hi;
    uint32_t npu_pmu_cycle_valid;        /* a stable HI/LO/HI read succeeded   */
    uint32_t npu_pmu_cycle_overflow;     /* PMOVSSET cycle bit after the run   */
    uint32_t t_pmu_programming;          /* reset/clear cost, before submit    */
    uint32_t t_submit_to_completion;     /* the only field for pure comparison */
    uint32_t t_result_processing;        /* CRC + serialisation, after close   */
} measurement_record_t;''',
     "record fields")

sub1('#define MEASUREMENT_FIELD_COUNT 47U',
     '/* 47 + 30 appended for milestone 1. The ABI header\'s total_payload_words\n'
     ' * remains the authority; hosts skip trailing words they do not know. */\n'
     '#define MEASUREMENT_FIELD_COUNT 77U',
     "field count")

# --- 5. serialisation ----------------------------------------------------
sub1('''    put32(&c, r->output_crc);''',
     '''    put32(&c, r->output_crc);''',
     "locate output_crc (no-op check)")

m = re.search(r"(    put32\(&c, r->result_region_crc\);\n)", s)
if not m:
    sys.exit("FAIL: result_region_crc serialisation not found")
s = s.replace(m.group(1), m.group(1) + '''    /* appended for the PMU candidate, milestone 1 */
    put32(&c, r->instrumentation_mode);
    put32(&c, r->event_set_id);
    put32(&c, r->npu_pmu_present);
    put32(&c, r->hw_event_counter_count);
    put32(&c, r->active_event_counter_count);
    put32(&c, r->event_valid_mask);
    put32(&c, r->event_overflow_mask);
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        put32(&c, r->event_codes[i]);
    }
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        put32(&c, r->event_values[i]);
    }
    put32(&c, r->npu_pmu_window_cycles_lo);
    put32(&c, r->npu_pmu_window_cycles_hi);
    put32(&c, r->npu_pmu_cycle_valid);
    put32(&c, r->npu_pmu_cycle_overflow);
    put32(&c, r->t_pmu_programming);
    put32(&c, r->t_submit_to_completion);
    put32(&c, r->t_result_processing);
''', 1)

open(F, "w").write(s)
print("patched %s (%d -> %d bytes)" % (F, len(orig), len(s)))
