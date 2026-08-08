"""Milestone 1 wiring for the PMU candidate.

Contracts encoded here:
  - The OFF guarantee is scoped to the RUN PATH, not the whole session:
    OFF_RUN_PATH_PMU_MMIO_ACCESS_COUNT == 0. GET_CAPABILITIES may probe the
    PMU because discovery happens outside the measurement window.
  - 8 event slots are ABI CAPACITY, not a hardware claim. Hardware capacity is
    read from PMCR.num_event_cnt; effective = min(abi, hardware).
  - Every PMU register access goes through pmu_reg_read/pmu_reg_write, which
    count accesses. A run reports the delta, so the OFF guarantee is proven at
    runtime rather than argued from disassembly alone.
  - Each RUN stores a COPY of the configuration it actually used. Changing the
    mode afterwards must not rewrite a past result.
  - The cycle value is npu_pmu_window_cycles. It is not T_npu and must never be
    renamed to npu_execution_cycles until a PMCCNTR_CFG hardware start/stop
    boundary has been cross-checked against it.
"""

import re
import sys

F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()


def sub1(old, new, what):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit("FAIL %s: expected 1 match, found %d" % (what, n))
    s = s.replace(old, new)


# ---------------------------------------------------------------- error code
sub1('#define ERR_RESULT_NOT_VALID 0x000BU',
     '#define ERR_RESULT_NOT_VALID 0x000BU\n\n'
     '/* A well-formed request for something this build does not implement --\n'
     ' * distinct from BAD_COMMAND (unknown id) and from RANGE (out of bounds).\n'
     ' * PER_LAYER instrumentation returns this. */\n'
     '#define ERR_UNSUPPORTED      0x000CU',
     "ERR_UNSUPPORTED")

# ------------------------------------------------------- accessors + counters
old_helpers_head = '''static void npu_write(uint32_t offset, uint32_t value)
{
    REG32(U85_BASE_ADDRESS + offset) = value;
}
'''
new_helpers_head = '''/* ------------------------------------------------------------------------ */
/* EVERY PMU register access goes through these two accessors, and nothing     */
/* else in this file dereferences a PMU offset. The counters are what makes    */
/* the OFF contract checkable at RUNTIME: a run in INSTRUMENTATION_OFF must    */
/* report a delta of zero on both. A static gate can show the OFF branch has   */
/* no call edge into the PMU helpers, but only these counters can catch a      */
/* regression that reintroduces a raw dereference somewhere else.              */
/*                                                                             */
/* SCOPE OF THE OFF CONTRACT: the RUN PATH, not the whole session.             */
/* GET_CAPABILITIES probes PMCR deliberately -- discovery happens outside the  */
/* measurement window and is reported via pmu_probe_performed.                 */
static volatile uint32_t pmu_mmio_read_count;
static volatile uint32_t pmu_mmio_write_count;

static uint32_t pmu_reg_read(uint32_t offset)
{
    pmu_mmio_read_count++;
    return REG32(U85_BASE_ADDRESS + offset);
}

static void pmu_reg_write(uint32_t offset, uint32_t value)
{
    pmu_mmio_write_count++;
    REG32(U85_BASE_ADDRESS + offset) = value;
}
'''
sub1(old_helpers_head, new_helpers_head, "PMU accessors")

# rewrite the helpers to use the accessors and the probe model
old_probe = '''/* Runtime instrumentation state. Defaults to OFF so a freshly booted image
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
}'''

new_probe = '''/* --- three DISTINCT capacities, never conflated ------------------------- */
/*   ABI capacity       : RUNNER_MAX_NPU_EVENT_COUNTERS, fixed at 8 slots.    */
/*   hardware capacity  : PMCR.num_event_cnt, the device answering for itself.*/
/*   effective capacity : min(the two). Only this bounds a configuration.     */
/* The vendor header's constant 8 is a BUILD-TIME claim and is recorded only  */
/* as expected_hw_event_counter_count, for a provenance warning if the device */
/* disagrees. A mismatch does not kill the run; it bounds what can be asked   */
/* for and is reported. */
static uint32_t pmu_probe_performed;
static uint32_t pmu_present;
static uint32_t pmu_hw_event_counters;

/* Discovery only. Outside the RUN path by contract -- see the accessor note. */
static void pmu_probe(void)
{
    uint32_t pmcr = pmu_reg_read(NPU_REG_PMCR);

    pmu_hw_event_counters =
        (pmcr & NPU_PMCR_NUM_EVENT_CNT_MSK) >> NPU_PMCR_NUM_EVENT_CNT_POS;
    /* All-ones or all-zeros PMCR means the block did not answer. */
    pmu_present = (pmcr != 0xFFFFFFFFU && pmcr != 0U) ? 1U : 0U;
    pmu_probe_performed = 1U;
}

static uint32_t pmu_effective_event_slots(void)
{
    if (!pmu_probe_performed) {
        pmu_probe();
    }
    return (pmu_hw_event_counters < RUNNER_MAX_NPU_EVENT_COUNTERS)
               ? pmu_hw_event_counters
               : RUNNER_MAX_NPU_EVENT_COUNTERS;
}

static void npu_pmu_disable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) & ~NPU_PMCR_CNT_EN_MSK);
}

static void npu_pmu_enable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
}

/* Clear every overflow flag, disable every counter, then reset the counters.
 * Stale state from a previous run must never be attributable to this one. */
static void npu_pmu_reset_counters(void)
{
    pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CYCLE_CNT_RST_MSK
                                             | NPU_PMCR_EVENT_CNT_RST_MSK);
}

/* PMOVSSET bit for the cycle counter. The event counters occupy bits 0..n-1
 * and the cycle counter sits immediately above the ABI slot range. */
#define NPU_PMU_CYCLE_OVF_BIT (1U << RUNNER_MAX_NPU_EVENT_COUNTERS)

static uint32_t npu_pmu_overflow_status(void)
{
    return pmu_reg_read(NPU_REG_PMOVSSET);
}'''
sub1(old_probe, new_probe, "probe + helpers")

# ------------------------------------------------------- safe 48-bit read
old_read = '''static uint64_t npu_pmu_read_cycles(uint32_t *stable_out)
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
new_read = '''#define NPU_PMU_CYCLE_MASK48 ((1ULL << NPU_PMU_CYCLE_COUNTER_WIDTH) - 1ULL)

static uint64_t npu_pmu_read_cycles(uint32_t *stable_out, uint32_t *retries_out)
{
    uint32_t hi1, lo, hi2;
    uint32_t tries;

    lo  = 0U;
    hi2 = 0U;
    for (tries = 0U; tries < NPU_PMU_CYCLE_READ_TRIES; tries++) {
        hi1 = pmu_reg_read(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        lo  = pmu_reg_read(NPU_REG_PMCCNTR);
        hi2 = pmu_reg_read(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        if (hi1 == hi2) {
            if (stable_out != 0) {
                *stable_out = 1U;
            }
            if (retries_out != 0) {
                *retries_out = tries;
            }
            return (((uint64_t)hi1 << 32) | (uint64_t)lo) & NPU_PMU_CYCLE_MASK48;
        }
    }
    /* Reported, never papered over: the caller sets cycle_valid = 0 and the
     * host must treat the value as absent rather than as a measurement. */
    if (stable_out != 0) {
        *stable_out = 0U;
    }
    if (retries_out != 0) {
        *retries_out = tries;
    }
    return (((uint64_t)hi2 << 32) | (uint64_t)lo) & NPU_PMU_CYCLE_MASK48;
}

/* ------------------------------------------------------------------------ */
/* Instrumentation configuration. handle_run() takes a COPY of this before it  */
/* does anything else, so changing the mode after a run cannot rewrite that    */
/* run's record.                                                              */
typedef struct {
    uint32_t mode;
    uint32_t event_set_id;
    uint32_t event_count;
    uint32_t event_codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    uint32_t configuration_sequence;
} instrumentation_config_t;

static instrumentation_config_t instr_cfg;

/* The frozen u85 driver waits for completion by polling, so the CPU is active
 * throughout NPU execution. Results from a future WFI variant describe a
 * different machine state and must not be pooled with these. */
#define COMPLETION_WAIT_BUSY_POLL 1U'''
sub1(old_read, new_read, "safe 48-bit read")

# ------------------------------------------------------------- record fields
old_fields = re.search(
    r"    /\* --- appended for the PMU candidate, milestone 1\. Order above untouched\. \*/.*?\n\} measurement_record_t;",
    s, re.S)
if not old_fields:
    sys.exit("FAIL: appended field block not found")
new_fields = '''    /* --- appended for the PMU candidate, milestone 1. Order above untouched. */
    uint32_t record_schema_version;
    /* requested vs applied: a request that was clamped or refused must be
     * visible, not silently normalised away. */
    uint32_t instrumentation_mode_requested;
    uint32_t instrumentation_mode_applied;
    uint32_t event_set_id;
    uint32_t configuration_sequence;
    uint32_t npu_pmu_present;
    uint32_t pmu_probe_performed;
    uint32_t hw_event_counter_count;        /* PMCR.num_event_cnt            */
    uint32_t expected_hw_event_counter_count; /* vendor header claim (8)     */
    uint32_t abi_event_slot_count;          /* fixed 8: ABI capacity         */
    uint32_t effective_event_slot_count;    /* min(abi, hardware)            */
    uint32_t requested_event_count;
    uint32_t applied_event_count;
    /* event code 0 may be a real event OR a disabled encoding, so a slot is
     * NEVER judged by its value. The mask is the only authority. */
    uint32_t event_valid_mask;
    uint32_t event_overflow_mask;
    uint32_t event_codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    uint32_t event_values[RUNNER_MAX_NPU_EVENT_COUNTERS];
    /* 48-bit cycle counter, split for the wire. NAMED "window", not
     * "execution": the snapshot is taken after run_fixed_inference() returns,
     * because u85.c reinstalls its own NPU vector and the completion ISR is
     * therefore unreachable. The value can include driver entry, busy-poll,
     * completion handling and the return path. Promote the name only after a
     * PMCCNTR_CFG hardware start/stop boundary has been cross-checked. */
    uint32_t npu_pmu_window_cycles_lo;
    uint32_t npu_pmu_window_cycles_hi;
    uint32_t npu_pmu_cycle_valid;
    uint32_t npu_pmu_cycle_overflow;
    uint32_t npu_pmu_cycle_read_retry_count;
    uint32_t pmu_sample_valid;              /* the PMU path ran at all       */
    uint32_t completion_wait_mode;          /* BUSY_POLL on this build       */
    /* four CPU timestamps, so what the PMU window contains stays analysable */
    uint32_t t_pmu_enable;
    uint32_t t_inference_call_enter;
    uint32_t t_inference_call_return;
    uint32_t t_pmu_disable;
    uint32_t t_pmu_programming;
    uint32_t cpu_call_window_cycles;
    uint32_t cpu_return_to_pmu_disable_cycles;
    uint32_t t_result_processing;
    /* Runtime proof of the OFF contract, scoped to the RUN path. */
    uint32_t pmu_mmio_read_count_delta;
    uint32_t pmu_mmio_write_count_delta;
} measurement_record_t;'''
s = s[:old_fields.start()] + new_fields + s[old_fields.end():]

sub1("#define MEASUREMENT_FIELD_COUNT 77U",
     "#define MEASUREMENT_FIELD_COUNT 94U",
     "field count 94")
sub1("/* 47 + 30 appended for milestone 1.",
     "/* 47 + 47 appended for milestone 1.",
     "field count comment")

# ------------------------------------------------------------- serialisation
old_ser = re.search(
    r"    /\* appended for the PMU candidate, milestone 1 \*/\n(?:.*?\n)*?    put32\(&c, r->t_result_processing\);\n",
    s)
if not old_ser:
    sys.exit("FAIL: appended serialisation block not found")
new_ser = '''    /* appended for the PMU candidate, milestone 1 */
    put32(&c, r->record_schema_version);
    put32(&c, r->instrumentation_mode_requested);
    put32(&c, r->instrumentation_mode_applied);
    put32(&c, r->event_set_id);
    put32(&c, r->configuration_sequence);
    put32(&c, r->npu_pmu_present);
    put32(&c, r->pmu_probe_performed);
    put32(&c, r->hw_event_counter_count);
    put32(&c, r->expected_hw_event_counter_count);
    put32(&c, r->abi_event_slot_count);
    put32(&c, r->effective_event_slot_count);
    put32(&c, r->requested_event_count);
    put32(&c, r->applied_event_count);
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
    put32(&c, r->npu_pmu_cycle_read_retry_count);
    put32(&c, r->pmu_sample_valid);
    put32(&c, r->completion_wait_mode);
    put32(&c, r->t_pmu_enable);
    put32(&c, r->t_inference_call_enter);
    put32(&c, r->t_inference_call_return);
    put32(&c, r->t_pmu_disable);
    put32(&c, r->t_pmu_programming);
    put32(&c, r->cpu_call_window_cycles);
    put32(&c, r->cpu_return_to_pmu_disable_cycles);
    put32(&c, r->t_result_processing);
    put32(&c, r->pmu_mmio_read_count_delta);
    put32(&c, r->pmu_mmio_write_count_delta);
'''
s = s[:old_ser.start()] + new_ser + s[old_ser.end():]

# --------------------------------------------------------- state machine bits
sub1("    CB_RESET_RUNNER,\n#ifdef RUNNER_TEST_ONLY_HOOKS",
     "    CB_RESET_RUNNER,\n    CB_SET_INSTRUMENTATION_MODE,\n#ifdef RUNNER_TEST_ONLY_HOOKS",
     "CB enum")
sub1("    case CMD_RESET_RUNNER:     return CB_RESET_RUNNER;",
     "    case CMD_RESET_RUNNER:     return CB_RESET_RUNNER;\n"
     "    case CMD_SET_INSTRUMENTATION_MODE: return CB_SET_INSTRUMENTATION_MODE;",
     "command_bit mapping")
# IDLE only, per the contract.
sub1("""    /* ST_IDLE          */ M_ALWAYS | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER),""",
     """    /* ST_IDLE          */ M_ALWAYS | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER) |
                           M(CB_SET_INSTRUMENTATION_MODE),""",
     "ST_IDLE accepts SET_INSTRUMENTATION_MODE")

open(F, "w").write(s)
print("patched %s" % F)
