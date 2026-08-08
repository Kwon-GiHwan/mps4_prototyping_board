F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()

def sub1(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: %d matches" % (what, n)
    s = s.replace(old, new)

# 1. Arm the cleanup flag BEFORE the write that arms the hardware. If the
#    enable lands and something then fails, the teardown must still know.
sub1('''    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
    pmu_ever_enabled = 1U;''',
     '''    /* Set BEFORE the enable write, never after: if the counter is armed and
     * the very next step faults, the flag must already say there is hardware
     * state to tear down. */
    pmu_ever_enabled = 1U;
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);''',
     "flag before enable")

# 2. RESET_RUNNER must be deterministic regardless of execution history.
sub1('''    instr_cfg.mode        = INSTRUMENTATION_OFF;
    instr_cfg.event_count = 0U;
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        instr_cfg.event_codes[i] = 0U;
    }
    if (pmu_ever_enabled) {
        npu_pmu_disable();
        __DSB();
        pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
        pmu_ever_enabled = 0U;
    }''',
     '''    /* UNCONDITIONAL, and deliberately so. Conditioning the teardown on a
     * software flag cannot recover the cases that matter: an enable that
     * landed before a fault skipped the flag update, a debugger or a previous
     * image leaving the block armed, or a warm handoff. Reset must leave the
     * PMU in a known state no matter what the history was.
     *
     * This costs PMU MMIO accesses, which is fine: the OFF contract is scoped
     * to the RUN PATH, not to RESET_RUNNER. */
    {
        uint32_t pmcr = pmu_reg_read(NPU_REG_PMCR);

        if (pmcr & NPU_PMCR_CNT_EN_MSK) {
            pmu_reg_write(NPU_REG_PMCR, pmcr & ~NPU_PMCR_CNT_EN_MSK);
        }
        __DSB();
        (void)pmu_reg_read(NPU_REG_PMCR);      /* readback: the clear landed */
        pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);  /* overflow evidence */
        pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU); /* counter enables  */
        pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);   /* overflow IRQs    */
        __DSB();
    }

    instr_cfg.mode        = INSTRUMENTATION_OFF;
    instr_cfg.event_count = 0U;
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        instr_cfg.event_codes[i] = 0U;
    }
    pmu_ever_enabled = 0U;''',
     "unconditional reset")

open(F, "w").write(s)
print("RESET_RUNNER is now unconditional; flag armed before enable")
