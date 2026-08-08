F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()

def sub1(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: %d matches" % (what, n)
    s = s.replace(old, new)

# 1. the derived-bit defect
sub1('''/* PMOVSSET bit for the cycle counter. The event counters occupy bits 0..n-1
 * and the cycle counter sits immediately above the ABI slot range. */
#define NPU_PMU_CYCLE_OVF_BIT (1U << RUNNER_MAX_NPU_EVENT_COUNTERS)

static uint32_t npu_pmu_overflow_status(void)''',
     '''/* The cycle overflow bit is NPU_PMU_PMOVS_CYCLE_OVF_MASK, extracted from
 * pmovsset_r. It is bit 31, NOT bit 8: eight event bits are followed by 23
 * reserved bits. The earlier 1<<RUNNER_MAX_NPU_EVENT_COUNTERS read a reserved
 * bit that is always zero, so a wrapped counter reported "no overflow" -- a
 * false negative that would have promoted a torn sample to a measurement. */
static uint32_t npu_pmu_overflow_status(void)''',
     "overflow bit")

sub1("r.npu_pmu_cycle_overflow   = (ovf & NPU_PMU_CYCLE_OVF_BIT) ? 1U : 0U;",
     "r.npu_pmu_cycle_overflow   = (ovf & NPU_PMU_PMOVS_CYCLE_OVF_MASK) ? 1U : 0U;",
     "overflow use")

# 2. arm the cycle counter, and verify both the arm and the global enable
sub1('''        ts_prog_start = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_disable();
            npu_pmu_reset_counters();
            r.npu_pmu_present          = pmu_present;
            r.pmu_probe_performed      = pmu_probe_performed;
            r.hw_event_counter_count   = pmu_hw_event_counters;
            r.effective_event_slot_count = pmu_effective_event_slots();
        }
        ts_prog_end = read_timestamp();
        r.t_pmu_programming = ts_prog_end - ts_prog_start;

        __DSB();
        __ISB();

        r.t_pmu_enable = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_enable();
        }''',
     '''        ts_prog_start = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            uint32_t cnten;

            /* PMCR.cnt_en is a GLOBAL gate; it does not arm any counter.
             * npu_pmu_reset_counters() clears PMCNTEN for everything, so the
             * cycle counter must be armed explicitly afterwards. Skipping this
             * is what produced window_cycles == 0 with every other flag green. */
            npu_pmu_disable();
            npu_pmu_reset_counters();
            pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);
            cnten = pmu_reg_read(NPU_REG_PMCNTENSET);
            r.cycle_counter_armed =
                (cnten & NPU_PMU_PMCNTEN_CYCLE_MASK) ? 1U : 0U;

            r.npu_pmu_present          = pmu_present;
            r.pmu_probe_performed      = pmu_probe_performed;
            r.hw_event_counter_count   = pmu_hw_event_counters;
            r.effective_event_slot_count = pmu_effective_event_slots();
        }
        ts_prog_end = read_timestamp();
        r.t_pmu_programming = ts_prog_end - ts_prog_start;

        __DSB();
        __ISB();

        r.t_pmu_enable = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            uint32_t pmcr;

            npu_pmu_enable();
            pmcr = pmu_reg_read(NPU_REG_PMCR);
            /* "Armed" and "globally enabled" are separate facts, and neither is
             * implied by a successful register read. Both are recorded. */
            r.cycle_global_enable_verified =
                (pmcr & NPU_PMCR_CNT_EN_MSK) ? 1U : 0U;
            __DSB();
        }''',
     "arm + verify")

# 3. validity decomposition
sub1('''            r.npu_pmu_cycle_read_retry_count = cycle_retries;
            /* A torn read or a wrapped counter is NOT a measurement. 48 bits
             * cannot be un-wrapped from endpoints alone, so the overflow flag
             * is the authority and invalidates the sample. */
            r.npu_pmu_cycle_valid =
                (cycle_stable && !r.npu_pmu_cycle_overflow) ? 1U : 0U;
            r.pmu_sample_valid    = 1U;''',
     '''            r.npu_pmu_cycle_read_retry_count = cycle_retries;
            r.cycle_read_stable   = cycle_stable ? 1U : 0U;
            r.pmu_sample_valid    = 1U;
            /* These are DIFFERENT facts and the milestone-1 defect proved it:
             * the counter read cleanly, was never armed, and still reported
             * valid. Validity now requires every one of them. Progress is
             * tracked separately -- a zero-cycle window is not universally
             * illegal, so the test-19 gate demands progress explicitly rather
             * than folding it into validity here. */
            r.cycle_progress_observed =
                (r.npu_pmu_window_cycles_lo || r.npu_pmu_window_cycles_hi) ? 1U : 0U;
            r.npu_pmu_cycle_valid =
                (r.pmu_sample_valid && r.cycle_counter_armed
                 && r.cycle_global_enable_verified && r.cycle_read_stable
                 && !r.npu_pmu_cycle_overflow) ? 1U : 0U;''',
     "validity decomposition")

# 4. new record fields + serialisation
sub1("    uint32_t pmcr_at_disable;   /* readback proving the disable landed */\n"
     "} measurement_record_t;",
     "    uint32_t pmcr_at_disable;   /* readback proving the disable landed */\n"
     "    /* Independent evidence, each answering a different question. */\n"
     "    uint32_t cycle_counter_armed;          /* PMCNTENSET readback       */\n"
     "    uint32_t cycle_global_enable_verified; /* PMCR readback after enable*/\n"
     "    uint32_t cycle_read_stable;            /* HI/LO/HI agreed           */\n"
     "    uint32_t cycle_progress_observed;      /* the counter actually moved*/\n"
     "} measurement_record_t;",
     "validity fields")

sub1("    put32(&c, r->pmcr_at_disable);\n",
     "    put32(&c, r->pmcr_at_disable);\n"
     "    put32(&c, r->cycle_counter_armed);\n"
     "    put32(&c, r->cycle_global_enable_verified);\n"
     "    put32(&c, r->cycle_read_stable);\n"
     "    put32(&c, r->cycle_progress_observed);\n",
     "serialise validity")

sub1("#define MEASUREMENT_FIELD_COUNT 98U", "#define MEASUREMENT_FIELD_COUNT 102U", "count")
sub1("/* 47 + 51 appended for milestone 1.", "/* 47 + 55 appended for milestone 1.", "count comment")

open(F, "w").write(s)
print("patched")
