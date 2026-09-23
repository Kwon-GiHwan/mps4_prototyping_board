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
  "            } else {\n"
  "                /* END_ONLY, unchanged: no event slot is ever armed. */\n"
  "                r.event_valid_mask    = 0U;\n"
  "                r.event_overflow_mask = 0U;\n"
  "                r.applied_event_count = 0U;\n"
  "                r.read_seam_fired     = 0U;\n"
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
  "static volatile uint32_t seam_fired, seam_cycle_lo, seam_cycle_hi, seam_cycle_stable,\n"
  "                         seam_cycle_retries, seam_ovf, seam_ev[RUNNER_MAX_NPU_EVENT_COUNTERS];\n"),
 # 10. clear the seam storage when the window opens
 ("    measurement_active = 1U;\n",
  "    seam_fired = 0U; seam_cycle_lo = 0U; seam_cycle_hi = 0U; seam_cycle_stable = 0U;\n"
  "    seam_cycle_retries = 0U; seam_ovf = 0U;\n"
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
  "        seam_fired++;\n"
  "    }\n"
  "    (void)fmt;\n    suppressed_printf_calls++;\n    return 0;\n}\n"),
 # 12. one appended record word: read_seam_fired (field 103)
 ("    uint32_t cycle_progress_observed;      /* the counter actually moved*/\n} measurement_record_t;\n",
  "    uint32_t cycle_progress_observed;      /* the counter actually moved*/\n"
  "    uint32_t read_seam_fired;              /* Tier B: CPM seam arrivals  */\n} measurement_record_t;\n"),
 ("    put32(&c, r->cycle_progress_observed);\n",
  "    put32(&c, r->cycle_progress_observed);\n    put32(&c, r->read_seam_fired);\n"),
 ("#define MEASUREMENT_FIELD_COUNT 102U\n", "#define MEASUREMENT_FIELD_COUNT 103U\n"),
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
