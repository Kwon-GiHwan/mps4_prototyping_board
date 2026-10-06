#!/usr/bin/env python3
"""Generate the Tier B EVENTS-mode runner from the frozen base runner.

Every replacement site must match EXACTLY once in the base, or this refuses.
The base file is never edited. Contract:
  docs/superpowers/specs/2026-09-23-pmu-events-tier-b-contract.md
"""
import argparse, hashlib, pathlib, sys

BASE_SHA256 = "b95b11b0cbddceefa8940515b8965be0d1132ea209ba32e12dbf4fefa95e41a2"
BUILD_ID = 0x504D4556  # "PMEV"

# (anchor, replacement) -- anchor must occur exactly once.
EDITS = [
 # 1. the mode constant
 ("#define INSTRUMENTATION_END_ONLY  1U\n",
  "#define INSTRUMENTATION_END_ONLY  1U\n#define INSTRUMENTATION_EVENTS    2U /* Tier B: END_ONLY + event slots */\n"),
 # 2. accept mode 2 in the command handler
 ("if (mode != INSTRUMENTATION_OFF && mode != INSTRUMENTATION_END_ONLY) {",
  "if (mode != INSTRUMENTATION_OFF && mode != INSTRUMENTATION_END_ONLY\n        && mode != INSTRUMENTATION_EVENTS) {"),
 # 3. milestone-1 refusal of count != 0 now applies to OFF/END_ONLY only
 ("    if (count != 0U) {\n",
  "    if (count != 0U && mode != INSTRUMENTATION_EVENTS) {\n"),
 # 4. advertise the mode
 ("(1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY)",
  "(1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY) | (1U << INSTRUMENTATION_EVENTS)"),
 # 5. programming block: widen the header only
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            uint32_t cnten;\n",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            uint32_t cnten;\n"),
 # 5b. EVENTS programming = the diag lineage's proven power-lifecycle sequence (amendment 8):
 #     hold NPU clock/power (CMD=0) and wait, disable+clear, PMCR=EN|RST in one write and wait,
 #     then arm cycle+events in one PMCNTENSET write and select the events under cnt_en=1.
 ("            npu_pmu_disable();\n            npu_pmu_reset_counters();\n            pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);\n",
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B (amendment 8). The previous test released clock/power with\n"
  "                 * CMD=0xC; PMU writes made in that state land in the register file\n"
  "                 * and never engage the counters (boots 5-8). Hold both Q interfaces\n"
  "                 * first, let it settle, then reset+enable under held power, wait,\n"
  "                 * then do the final programming -- the sequence PMU_DIAG/QUAL proved. */\n"
  "                npu_write(NPU_OFF_CMD, 0U);\n"
  "                __DSB(); __ISB();\n"
  "                pmu_events_wait_cycles(PMU_EVENTS_POWER_GUARD_CYCLES);\n"
  "                npu_pmu_disable();\n"
  "                pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);\n"
  "                pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);\n"
  "                pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);\n"
  "                pmu_reg_write(NPU_REG_PMCR, NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK\n"
  "                                            | NPU_PMCR_CYCLE_CNT_RST_MSK);\n"
  "                __DSB(); __ISB();\n"
  "                pmu_events_wait_cycles(PMU_EVENTS_RESET_GUARD_CYCLES);\n"
  "                pmu_reg_write(NPU_REG_PMCNTENSET,\n"
  "                              NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U));\n"
  "                for (i = 0; i < cfg.event_count; i++) {\n"
  "                    pmu_reg_write(NPU_REG_PMEVTYPER_BASE + 4U * i, cfg.event_codes[i] & 0x3FFU);\n"
  "                }\n"
  "                __DSB();\n"
  "            } else {\n"
  "                npu_pmu_disable();\n"
  "                npu_pmu_reset_counters();\n"
  "                pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);\n"
  "            }\n"),
 # 5c. helpers: NPU CMD offset (BASE.CMD, 0x08 -- as Selftest_pmu_diag defines it), a write
 #     accessor beside the base's npu_read, and the guard wait copied from pmu_diag_wait_cycles.
 ("static uint32_t npu_read(uint32_t offset)\n{\n    return REG32(U85_BASE_ADDRESS + offset);\n}\n",
  "static uint32_t npu_read(uint32_t offset)\n{\n    return REG32(U85_BASE_ADDRESS + offset);\n}\n"
  "#define NPU_OFF_CMD 0x08U /* BASE.CMD; bits [3:2] = clock-Q / power-Q enables, 0 = hold */\n"
  "static void npu_write(uint32_t offset, uint32_t value)\n{\n    REG32(U85_BASE_ADDRESS + offset) = value;\n}\n"
  "#define PMU_EVENTS_POWER_GUARD_CYCLES 65536U /* = PMU_DIAG_POWER_GUARD_CYCLES */\n"
  "#define PMU_EVENTS_RESET_GUARD_CYCLES 65536U /* = PMU_DIAG_RESET_GUARD_CYCLES */\n"),
 # 6. enable block: widen, and select the events AFTER cnt_en=1 is verified (TRM: PMU writes
 #    other than PMCR.cnt_en are not guaranteed to take effect unless cnt_en=1).
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            uint32_t pmcr;\n",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            uint32_t pmcr;\n"),
 # 7. readout block: widen
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            /* Order matters and is not negotiable:",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            /* Order matters and is not negotiable:"),
 # 8. readout: EVENTS copies the CPM-seam snapshot over the post-return (dead-PMU) reads
 ("            /* Milestone 1 arms no event counters: every slot stays invalid. */\n"
  "            r.event_valid_mask    = 0U;\n"
  "            r.event_overflow_mask = 0U;\n"
  "            r.applied_event_count = 0U;\n",
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B (amendment 7): the vendor test releases clock/power (CMD=0xC)\n"
  "                 * before returning, so the reads above saw a dead PMU. The read seam in\n"
  "                 * __wrap_printf snapshotted the live counters just before that release;\n"
  "                 * the record carries the snapshot and recomputes validity from it. */\n"
  "                uint32_t armed = (1U << cfg.event_count) - 1U;\n"
  "                r.npu_pmu_window_cycles_lo = seam_cycle_lo;\n"
  "                r.npu_pmu_window_cycles_hi = seam_cycle_hi;\n"
  "                r.cycle_read_stable        = seam_cycle_stable ? 1U : 0U;\n"
  "                r.npu_pmu_cycle_read_retry_count = seam_cycle_retries;\n"
  "                r.npu_pmu_cycle_overflow   = (seam_ovf & NPU_PMU_PMOVS_CYCLE_OVF_MASK) ? 1U : 0U;\n"
  "                r.cycle_progress_observed  = (seam_cycle_lo || seam_cycle_hi) ? 1U : 0U;\n"
  "                r.npu_pmu_cycle_valid =\n"
  "                    (r.pmu_sample_valid && r.cycle_counter_armed\n"
  "                     && r.cycle_global_enable_verified && r.cycle_read_stable\n"
  "                     && !r.npu_pmu_cycle_overflow) ? 1U : 0U;\n"
  "                for (i = 0; i < cfg.event_count; i++) {\n"
  "                    r.event_values[i] = seam_ev[i];\n"
  "                }\n"
  "                r.event_overflow_mask = seam_ovf & 0xFFU;\n"
  "                r.applied_event_count = cfg.event_count;\n"
  "                r.event_valid_mask    = armed & ~r.event_overflow_mask;\n"
  "                r.read_seam_fired     = seam_fired;\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\n                r.vendor_rc           = (uint32_t)last_vendor_rc;\n                r.seam_npu_status     = seam_status;\n                r.seam_npu_qread      = seam_qread;\n                r.ofm_mismatch_count  = ofm_mm_count;\n                r.ofm_max_abs_diff    = ofm_mm_max;\n                r.ofm_first_mismatch  = ofm_mm_first;\n#endif\n"
  "            } else {\n"
  "                /* END_ONLY, unchanged: no event slot is ever armed. */\n"
  "                r.event_valid_mask    = 0U;\n"
  "                r.event_overflow_mask = 0U;\n"
  "                r.applied_event_count = 0U;\n"
  "                r.read_seam_fired     = 0U;\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\n                r.vendor_rc           = 0U;\n                r.seam_npu_status     = 0U;\n                r.seam_npu_qread      = 0U;\n                r.ofm_mismatch_count  = 0U;\n                r.ofm_max_abs_diff    = 0U;\n                r.ofm_first_mismatch  = 0xFFFFFFFFU;\n#endif\n"
  "            }\n"),
 # 8b. guard wait, after read_timestamp() so both timestamp helpers are visible
 ("static uint32_t read_timestamp(void)\n",
  "static uint32_t timestamp_source_ready(void);\n"
  "static uint32_t read_timestamp(void);\n"
  "/* Tier B: bounded busy-wait, copied from pmu_diag_wait_cycles(). */\n"
  "static void pmu_events_wait_cycles(uint32_t cycles)\n{\n"
  "    if (timestamp_source_ready()) {\n"
  "        const uint32_t start = read_timestamp();\n"
  "        while ((read_timestamp() - start) < cycles) {\n        }\n"
  "    } else {\n"
  "        for (volatile uint32_t n = 0U; n < cycles; n++) {\n        }\n"
  "    }\n}\n"
  "static uint32_t read_timestamp(void)\n"),
 # 9. seam storage, next to the window flag
 ("volatile uint32_t measurement_active;\n",
  "volatile uint32_t measurement_active;\n"
  "/* Tier B read seam (amendment 7): filled inside __wrap_printf at the vendor's\n"
  " * \"Testing CPM signals\" printf, i.e. after CMD=0 and before CMD=0xC. */\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\nstatic volatile int32_t last_vendor_rc; /* Tier C: test_u85's own rc, set by __wrap_test_u85 */\nstatic volatile uint32_t seam_status, seam_qread; /* NPU STATUS / QREAD at the CPM seam */\nstatic volatile uint32_t ofm_mm_count, ofm_mm_max, ofm_mm_first; /* model OFM vs reference */\n#endif\n"
  "static volatile uint32_t seam_fired, seam_cycle_lo, seam_cycle_hi, seam_cycle_stable,\n"
  "                         seam_cycle_retries, seam_ovf, seam_ev[RUNNER_MAX_NPU_EVENT_COUNTERS];\n"),
 # 10. clear the seam storage when the window opens
 ("    measurement_active = 1U;\n",
  "    seam_fired = 0U; seam_cycle_lo = 0U; seam_cycle_hi = 0U; seam_cycle_stable = 0U;\n"
  "    seam_cycle_retries = 0U; seam_ovf = 0U;\n#if defined(PMU_EVENTS_EXT_DRAM)\n    last_vendor_rc = -1; seam_status = 0U; seam_qread = 0U;\n    ofm_mm_count = 0U; ofm_mm_max = 0U; ofm_mm_first = 0xFFFFFFFFU;\n#endif\n"
  "    for (unsigned k = 0; k < RUNNER_MAX_NPU_EVENT_COUNTERS; k++) { seam_ev[k] = 0U; }\n"
  "    measurement_active = 1U;\n"),
 # 11. the read seam itself, in the clean-profile printf wrapper
 ("int __wrap_printf(const char *fmt, ...)\n{\n    (void)fmt;\n    suppressed_printf_calls++;\n    return 0;\n}\n",
  "int __wrap_printf(const char *fmt, ...)\n{\n"
  "    /* Tier B read seam (amendment 7). Exactly one printf in the vendor test\n"
  "     * carries this format, between its STOP (CMD=0) and its clock/power\n"
  "     * release (CMD=0xC). Counted on every arrival so a double fire is visible. */\n"
  "    if (measurement_active && instr_cfg.mode == INSTRUMENTATION_EVENTS\n"
  "        && strcmp(fmt, \"Testing CPM signals\\n\") == 0) {\n"
  "        uint32_t st = 0U, rt = 0U;\n"
  "        uint64_t cyc = npu_pmu_read_cycles(&st, &rt);\n"
  "        seam_cycle_lo = (uint32_t)(cyc & 0xFFFFFFFFU);\n"
  "        seam_cycle_hi = (uint32_t)(cyc >> 32);\n"
  "        seam_cycle_stable = st; seam_cycle_retries = rt;\n"
  "        seam_ovf = npu_pmu_overflow_status();\n"
  "        for (unsigned k = 0; k < instr_cfg.event_count; k++) {\n"
  "            seam_ev[k] = pmu_reg_read(NPU_REG_PMEVCNTR_BASE + 4U * k);\n"
  "        }\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\n        seam_status = npu_read(NPU_OFF_STATUS);\n        seam_qread  = npu_read(NPU_OFF_QREAD);\n#endif\n        seam_fired++;\n"
  "    }\n"
  "#if defined(PMU_EVENTS_MODEL)\n"
  "    /* Tier C step 2 apply seam: right after the vendor wrote REGIONCFG/QCONFIG/MEM_ATTR,\n"
  "     * right before it starts the NPU. Every override is read back. */\n"
  "    if (measurement_active && pmwl_knob_pending\n"
  "        && strcmp(fmt, \"Updating POWER_CTRL register with MAC_RAMP_VAR=%d \\n\") == 0) {\n"
  "        static const uint32_t off[6] = {NPU_OFF_REGIONCFG, NPU_OFF_QCONFIG, NPU_OFF_MEM_ATTR0,\n"
  "                                        NPU_OFF_MEM_ATTR0 + 4U, NPU_OFF_MEM_ATTR0 + 8U, NPU_OFF_MEM_ATTR0 + 12U};\n"
  "        for (unsigned k = 0; k < 6U; k++) {\n"
  "            if (pmwl_knob[k] != PMWL_OFF) {\n"
  "                npu_write(off[k], pmwl_knob[k]);\n"
  "                if (npu_read(off[k]) != pmwl_knob[k]) { pmwl_knob_bad = 1U; }\n"
  "            }\n"
  "        }\n"
  "        pmwl_knob_pending = 0U;\n"
  "    }\n"
  "#endif\n"
  "    (void)fmt;\n    suppressed_printf_calls++;\n    return 0;\n}\n"),
 # 12. one appended record word: read_seam_fired (field 103)
 ("    uint32_t cycle_progress_observed;      /* the counter actually moved*/\n} measurement_record_t;\n",
  "    uint32_t cycle_progress_observed;      /* the counter actually moved*/\n"
  "    uint32_t read_seam_fired;              /* Tier B: CPM seam arrivals  */\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\n    uint32_t vendor_rc;                    /* Tier C: test_u85's own rc  */\n    uint32_t seam_npu_status;              /* STATUS at the CPM seam     */\n    uint32_t seam_npu_qread;               /* QREAD at the CPM seam      */\n    uint32_t ofm_mismatch_count;           /* OFM bytes != reference     */\n    uint32_t ofm_max_abs_diff;             /* as int8                    */\n    uint32_t ofm_first_mismatch;           /* index, 0xFFFFFFFF = none   */\n#endif\n} measurement_record_t;\n"),
 ("    put32(&c, r->cycle_progress_observed);\n",
  "    put32(&c, r->cycle_progress_observed);\n    put32(&c, r->read_seam_fired);\n#if defined(PMU_EVENTS_EXT_DRAM)\n    put32(&c, r->vendor_rc);\n    put32(&c, r->seam_npu_status);\n    put32(&c, r->seam_npu_qread);\n    put32(&c, r->ofm_mismatch_count);\n    put32(&c, r->ofm_max_abs_diff);\n    put32(&c, r->ofm_first_mismatch);\n#endif\n"),
 ("#define MEASUREMENT_FIELD_COUNT 102U\n", "#if defined(PMU_EVENTS_EXT_DRAM)\n#define MEASUREMENT_FIELD_COUNT 109U\n#else\n#define MEASUREMENT_FIELD_COUNT 103U\n#endif\n"),
 # 13. Tier C step 0b: __wrap_test_u85 (only under PMU_EVENTS_EXT_DRAM; --wrap=test_u85 in that build)
 ("static int32_t run_fixed_inference(void)\n",
  "#if defined(PMU_EVENTS_EXT_DRAM)\n"
  "/* Tier C step 0b. Step 0 showed the EXT AXI port cannot serve the 0x9000_0000\n"
  " * 'Dev Access' alias. Copy the vendor's own tensors to S DRAM (IDAU 7), let the\n"
  " * vendor run and judge them there, copy the output back to its own buffer.\n"
  " * Sizes are the linked symbol sizes; the gate checks them against nm -S. */\n"
  "#define EXT_DRAM_BASE      0x70100000U\n"
  "#define EXT_DRAM_CMD_OFF   0x0000U\n"
  "#define EXT_DRAM_W_OFF     0x1000U\n"
  "#define EXT_DRAM_IN_OFF    0x2000U\n"
  "#define EXT_DRAM_SCR_OFF   0x3000U\n"
  "#define EXT_DRAM_OUT_OFF   0x4000U\n"
  "#define TEST3_WEIGHTS_SIZE 0x600U\n"
  "#define TEST3_IN_SIZE      0x400U\n"
  "#define TEST3_SCRATCH_SIZE 0x300U\n"
  "int __real_test_u85(const u85_eTest eTest, const uint32_t irq_mask, const uint32_t out_size,\n"
  "                    const uint32_t qsize, struct u85_warp_data_t *w);\n"
  "#if defined(PMU_EVENTS_MODEL)\n"
  "/* Tier C step 1: a PMWL workload blob staged by LOAD_MODEL replaces test3. Header = 16 u32:\n"
  " * magic ver cms_off cms_len const_off const_len arena fast ifm_aoff ifm_len ifm_doff\n"
  " * ofm_aoff ofm_len golden_off irq_mask total. The vendor's memcmp against the reference\n"
  " * OFM (tflite_runtime on the original model) decides correctness. */\n"
  "#define PMWL_MAGIC 0x4C574D50U\n"
  "#define PMWL_REFUSED 0x7E\n"
  "#define PMWL_KNOB_NOT_HONOURED 0x7D\n"
  "#define PMWL_OFF 0xFFFFFFFFU\n"
  "#define NPU_REG_PMCAXI_CHAN_ABS 0x11ACU /* PMU block 0x1180 + 0x2C */\n"
  "#define NPU_OFF_REGIONCFG 0x3CU\n"
  "#define NPU_OFF_QCONFIG   0x1CU /* interface.h NPU_REG_QCONFIG */\n"
  "#define NPU_OFF_MEM_ATTR0 0x40U\n"
  "/* v2 knobs, applied at the vendor's POWER_CTRL printf (see __wrap_printf). */\n"
  "static volatile uint32_t pmwl_knob_pending, pmwl_knob_bad;\n"
  "static uint32_t pmwl_knob[7]; /* regioncfg qconfig mem_attr0..3 (+pad) */\n"
  "static uint32_t pmwl_al256(uint32_t n) { return (n + 255U) & ~255U; }\n"
  "/* 1 = the region's traffic goes to the EXT port (default: USE_AXI_EXT makes every MEM_ATTR EXT). */\n"
  "static uint32_t pmwl_is_ext(uint32_t attr_index)\n{\n"
  "    uint32_t a = pmwl_knob[2U + attr_index];\n"
  "    return (a == PMWL_OFF) ? 1U : ((a >> 2) & 1U);\n}\n"
  "static uint32_t pmwl_region_ext(uint32_t region)\n{\n"
  "    return (pmwl_knob[0] == PMWL_OFF) ? 1U : pmwl_is_ext((pmwl_knob[0] >> (2U * region)) & 3U);\n}\n"
  "int __wrap_test_u85(const u85_eTest eTest, const uint32_t irq_mask, const uint32_t out_size,\n"
  "                    const uint32_t qsize, struct u85_warp_data_t *w)\n{\n"
  "    const uint8_t *s = __runner_staging_start__;\n"
  "    uint8_t *dram = (uint8_t *)(uintptr_t)EXT_DRAM_BASE;\n"
  "    uint8_t *near; /* SRAM-port side: staging window after the blob */\n"
  "    struct u85_warp_data_t x = *w;\n"
  "    uint32_t h[24], i, cmd_ext;\n"
  "    uint8_t *cmd, *cst, *arena, *fast;\n"
  "    int rc;\n"
  "    (void)irq_mask; (void)qsize;\n"
  "    memcpy(h, s, 16U * 4U);\n"
  "    if (h[0] != PMWL_MAGIC || (h[1] != 1U && h[1] != 2U) || h[15] != model_total_length) {\n"
  "        return PMWL_REFUSED;  /* no blob: never fall back to test3 silently */\n"
  "    }\n"
  "    for (i = 16U; i < 24U; i++) { h[i] = PMWL_OFF; }\n"
  "    if (h[1] == 2U) { memcpy(&h[16], s + 64U, 8U * 4U); }\n"
  "    for (i = 0U; i < 6U; i++) { pmwl_knob[i] = h[17U + i]; }\n"
  "    near = (uint8_t *)s + pmwl_al256(h[15]);\n"
  "    cmd_ext = (pmwl_knob[1] == PMWL_OFF) ? 1U : pmwl_is_ext(pmwl_knob[1] & 3U);\n"
  "    /* placement follows the port: EXT regions in S DRAM, SRAM-port regions in staging */\n"
  "    cmd = cmd_ext ? dram : (uint8_t *)s + h[2];\n"
  "    if (cmd_ext) { memcpy(cmd, s + h[2], h[3]); dram += pmwl_al256(h[3]); }\n"
  "    if (pmwl_region_ext(0U)) { cst = dram; memcpy(cst, s + h[4], h[5]); dram += pmwl_al256(h[5]); }\n"
  "    else { cst = (uint8_t *)s + h[4]; }\n"
  "    if (pmwl_region_ext(1U)) { arena = dram; dram += pmwl_al256(h[6]); } else { arena = near; near += pmwl_al256(h[6]); }\n"
  "    if (pmwl_region_ext(2U)) { fast = dram; } else { fast = near; }\n"
  "    memset(arena + h[11], 0xA5, h[12]);  /* poison OFM, then IFM (they may overlap) */\n"
  "    memcpy(arena + h[8], s + h[10], h[9]);\n"
  "    __DSB();\n"
  "    pmwl_knob_bad = 0U;\n"
  "    if (h[16] != PMWL_OFF) {\n"
  "        pmu_reg_write(NPU_REG_PMCAXI_CHAN_ABS, h[16]);\n"
  "        if (pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS) != h[16]) { pmwl_knob_bad = 1U; }\n"
  "    }\n"
  "    pmwl_knob_pending = 0U;\n"
  "    for (i = 0U; i < 6U; i++) { if (pmwl_knob[i] != PMWL_OFF) { pmwl_knob_pending = 1U; } }\n"
  "    x.cmd_st         = cmd;\n"
  "    x.weights        = cst;\n"
  "    x.scratch_buffer = arena;\n"
  "    x.in_data_0      = fast;\n"
  "    x.out_data_0     = arena + h[11];\n"
  "    x.out_ver_data_0 = s + h[13];\n"
  "    rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);\n"
  "    {   /* how far the OFM is from the reference, as int8: decides +/-1 vs garbage */\n"
  "        const int8_t *o = (const int8_t *)(arena + h[11]);\n"
  "        const int8_t *g = (const int8_t *)(s + h[13]);\n"
  "        for (i = 0U; i < h[12]; i++) {\n"
  "            int32_t dd = (int32_t)o[i] - (int32_t)g[i];\n"
  "            if (dd != 0) {\n"
  "                if (ofm_mm_count == 0U) { ofm_mm_first = i; }\n"
  "                ofm_mm_count++;\n"
  "                if (dd < 0) { dd = -dd; }\n"
  "                if ((uint32_t)dd > ofm_mm_max) { ofm_mm_max = (uint32_t)dd; }\n"
  "            }\n"
  "        }\n"
  "    }\n"
  "    if (pmwl_knob_pending) { pmwl_knob_bad = 1U; }  /* the apply seam never fired */\n"
  "    pmwl_knob_pending = 0U;\n"
  "    last_vendor_rc = rc;\n"
  "    memcpy(w->out_data_0, arena + h[11], (h[12] < out_size) ? h[12] : out_size);\n"
  "    return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;\n}\n"
  "#else\n"
  "int __wrap_test_u85(const u85_eTest eTest, const uint32_t irq_mask, const uint32_t out_size,\n"
  "                    const uint32_t qsize, struct u85_warp_data_t *w)\n{\n"
  "    uint8_t *d = (uint8_t *)(uintptr_t)EXT_DRAM_BASE;\n"
  "    struct u85_warp_data_t x = *w;\n"
  "    int rc;\n"
  "    memcpy(d + EXT_DRAM_CMD_OFF, w->cmd_st, qsize);\n"
  "    memcpy(d + EXT_DRAM_W_OFF, w->weights, TEST3_WEIGHTS_SIZE);\n"
  "    memcpy(d + EXT_DRAM_IN_OFF, w->in_data_0, TEST3_IN_SIZE);\n"
  "    memcpy(d + EXT_DRAM_SCR_OFF, w->scratch_buffer, TEST3_SCRATCH_SIZE);\n"
  "    memset(d + EXT_DRAM_OUT_OFF, 0xA5, out_size); /* stale DRAM must never pass as output */\n"
  "    __DSB();\n"
  "    x.cmd_st         = d + EXT_DRAM_CMD_OFF;\n"
  "    x.weights        = d + EXT_DRAM_W_OFF;\n"
  "    x.in_data_0      = d + EXT_DRAM_IN_OFF;\n"
  "    x.scratch_buffer = d + EXT_DRAM_SCR_OFF;\n"
  "    x.out_data_0     = d + EXT_DRAM_OUT_OFF;\n"
  "    rc = __real_test_u85(eTest, irq_mask, out_size, qsize, &x);\n"
  "    last_vendor_rc = rc;\n"
  "    memcpy(w->out_data_0, d + EXT_DRAM_OUT_OFF, out_size);\n"
  "    return rc;\n}\n"
  "#endif /* PMU_EVENTS_MODEL */\n"
  "#endif\n"
  "#if defined(PMU_EVENTS_EXT_DRAM)\n"
  "/* Keep the measured-path root out of line in this build: with __wrap_test_u85 above it\n"
  " * GCC inlines it, and check_measure_symbols.py then cannot locate the root. */\n"
  "__attribute__((noinline))\n"
  "#endif\n"
  "static int32_t run_fixed_inference(void)\n"),
]


def generate(base_text):
    out = base_text
    for anchor, repl in EDITS:
        n = out.count(anchor)
        if n != 1:
            raise SystemExit(f"anchor matched {n} times, need exactly 1:\n{anchor!r}")
        out = out.replace(anchor, repl, 1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    data = pathlib.Path(a.base).read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != BASE_SHA256:
        raise SystemExit(f"base runner sha256 {got} != pinned {BASE_SHA256}")
    gen = generate(data.decode())
    p = pathlib.Path(a.out); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(gen)
    print(f"generated {p} ({len(gen)} bytes) from base {got[:12]}; build id 0x{BUILD_ID:08X}")


if __name__ == "__main__":
    main()
