"""Milestone 1 corrections: shutdown ordering, RESET contract, total counters."""

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


# --- track whether the PMU was ever armed, so RESET has something to clean --
sub1("static instrumentation_config_t instr_cfg;",
     "static instrumentation_config_t instr_cfg;\n\n"
     "/* Set the first time the counters are armed. RESET_RUNNER uses it to\n"
     " * decide whether there is any PMU state to tear down: in a session that\n"
     " * never left OFF there is nothing to clean, and touching the block would\n"
     " * be an access with no purpose. */\n"
     "static uint32_t pmu_ever_enabled;",
     "pmu_ever_enabled")

sub1('''static void npu_pmu_enable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
}''',
     '''static void npu_pmu_enable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
    pmu_ever_enabled = 1U;
}''',
     "mark enabled")

# --- shutdown ordering ----------------------------------------------------
sub1('''        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_disable();
            r.t_pmu_disable = read_timestamp();
            cycles = npu_pmu_read_cycles(&cycle_stable, &cycle_retries);
            ovf    = npu_pmu_overflow_status();
''',
     '''        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            /* Order matters and is not negotiable:
             *   clear enable -> DSB -> PMCR readback -> cycle -> overflow.
             * The DSB makes the disable write observable before any snapshot
             * read is issued; the readback confirms the block accepted it.
             * Both cost one MMIO access each and are part of the EXPECTED
             * END_ONLY access count, not accidental traffic.
             * Overflow is snapshotted AFTER the counters and is never cleared
             * here -- clearing before the snapshot would destroy the evidence
             * that decides cycle_valid. It is cleared at the START of the next
             * run instead. */
            npu_pmu_disable();
            __DSB();
            r.pmcr_at_disable = pmu_reg_read(NPU_REG_PMCR);
            r.t_pmu_disable = read_timestamp();
            cycles = npu_pmu_read_cycles(&cycle_stable, &cycle_retries);
            ovf    = npu_pmu_overflow_status();
''',
     "shutdown ordering")

# --- new fields: pmcr_at_disable + total counters -------------------------
sub1("    uint32_t pmu_mmio_read_count_delta;\n"
     "    uint32_t pmu_mmio_write_count_delta;\n"
     "} measurement_record_t;",
     "    /* Totals are session-cumulative and may be non-zero purely because\n"
     "     * GET_CAPABILITIES probed, or because an earlier run used END_ONLY.\n"
     "     * THE DELTA IS THE AUTHORITY for the OFF contract; the totals are\n"
     "     * context. */\n"
     "    uint32_t pmu_mmio_read_count_total;\n"
     "    uint32_t pmu_mmio_write_count_total;\n"
     "    uint32_t pmu_mmio_read_count_delta;\n"
     "    uint32_t pmu_mmio_write_count_delta;\n"
     "    uint32_t pmcr_at_disable;   /* readback proving the disable landed */\n"
     "} measurement_record_t;",
     "total counters + pmcr readback field")

sub1("    put32(&c, r->pmu_mmio_read_count_delta);\n"
     "    put32(&c, r->pmu_mmio_write_count_delta);\n",
     "    put32(&c, r->pmu_mmio_read_count_total);\n"
     "    put32(&c, r->pmu_mmio_write_count_total);\n"
     "    put32(&c, r->pmu_mmio_read_count_delta);\n"
     "    put32(&c, r->pmu_mmio_write_count_delta);\n"
     "    put32(&c, r->pmcr_at_disable);\n",
     "serialise totals")

sub1("        r.pmu_mmio_read_count_delta  = pmu_mmio_read_count - pmu_r0;\n"
     "        r.pmu_mmio_write_count_delta = pmu_mmio_write_count - pmu_w0;",
     "        r.pmu_mmio_read_count_delta  = pmu_mmio_read_count - pmu_r0;\n"
     "        r.pmu_mmio_write_count_delta = pmu_mmio_write_count - pmu_w0;\n"
     "        r.pmu_mmio_read_count_total  = pmu_mmio_read_count;\n"
     "        r.pmu_mmio_write_count_total = pmu_mmio_write_count;",
     "assign totals")

sub1("#define MEASUREMENT_FIELD_COUNT 95U",
     "#define MEASUREMENT_FIELD_COUNT 98U",
     "field count 98")
sub1("/* 47 + 48 appended for milestone 1.",
     "/* 47 + 51 appended for milestone 1.",
     "field count comment")

# --- RESET_RUNNER contract ------------------------------------------------
m = re.search(r"static void handle_reset_runner\(uint32_t sequence\)\n\{\n", s)
if not m:
    sys.exit("FAIL: handle_reset_runner not found")
s = s[:m.end()] + '''    /* RESET_RUNNER returns instrumentation to a DEFINED default, so a run can
     * never inherit a configuration the host forgot it set. Chosen for
     * reproducibility: the host must state the mode before every measurement
     * rather than rely on what a previous session left behind.
     *   mode = OFF, event_count = 0, PMU disabled, overflow cleared.
     * The teardown runs only if the counters were ever armed -- in a session
     * that never left OFF there is nothing to tear down and touching the
     * block would be an access with no purpose. */
    instr_cfg.mode        = INSTRUMENTATION_OFF;
    instr_cfg.event_count = 0U;
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        instr_cfg.event_codes[i] = 0U;
    }
    if (pmu_ever_enabled) {
        npu_pmu_disable();
        __DSB();
        pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
        pmu_ever_enabled = 0U;
    }

''' + s[m.end():]

open(F, "w").write(s)
print("patched %s" % F)
