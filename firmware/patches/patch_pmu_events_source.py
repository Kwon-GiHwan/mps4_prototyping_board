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
 # 5. programming block: widen + program event slots after the cycle counter is armed
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            uint32_t cnten;\n",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            uint32_t cnten;\n"),
 ("            cnten = pmu_reg_read(NPU_REG_PMCNTENSET);\n",
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B. TRM: PMU writes other than PMCR.cnt_en are not\n"
  "                 * guaranteed to take effect unless cnt_en=1. Boot 5 showed exactly\n"
  "                 * that: slots and enables written under cnt_en=0 counted nothing\n"
  "                 * (66/66 runs, 0 cycles, 0 events). So: enable FIRST, then select\n"
  "                 * and arm in ONE PMCNTENSET write that carries the cycle bit, then\n"
  "                 * pulse both reset bits so every counter starts from 0 together.\n"
  "                 * The window therefore includes this programming; the cycle event\n"
  "                 * and PMCCNTR share the reset, which is what the +/-1 % check needs. */\n"
  "                npu_pmu_enable();\n"
  "                for (i = 0; i < cfg.event_count; i++) {\n"
  "                    pmu_reg_write(NPU_REG_PMEVTYPER_BASE + 4U * i, cfg.event_codes[i] & 0x3FFU);\n"
  "                }\n"
  "                pmu_reg_write(NPU_REG_PMCNTENSET,\n"
  "                              NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U));\n"
  "                pmu_reg_write(NPU_REG_PMCR, pmu_reg_read(NPU_REG_PMCR)\n"
  "                              | NPU_PMCR_CYCLE_CNT_RST_MSK | NPU_PMCR_EVENT_CNT_RST_MSK);\n"
  "                __DSB();\n"
  "            }\n"
  "            cnten = pmu_reg_read(NPU_REG_PMCNTENSET);\n"),
 # 6. enable block: widen
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            uint32_t pmcr;\n",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            uint32_t pmcr;\n"),
 # 7. readout block: widen
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            /* Order matters and is not negotiable:",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            /* Order matters and is not negotiable:"),
 # 8. readout: replace milestone-1 "no slots" with the event readback
 ("            /* Milestone 1 arms no event counters: every slot stays invalid. */\n"
  "            r.event_valid_mask    = 0U;\n"
  "            r.event_overflow_mask = 0U;\n"
  "            r.applied_event_count = 0U;\n",
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B: read every armed slot AFTER the disable; overflow\n"
  "                 * bits [7:0] of PMOVSSET veto validity, and the mask -- never\n"
  "                 * a code of 0 -- is what the host judges a slot by. */\n"
  "                uint32_t armed = (1U << cfg.event_count) - 1U;\n"
  "                for (i = 0; i < cfg.event_count; i++) {\n"
  "                    r.event_values[i] = pmu_reg_read(NPU_REG_PMEVCNTR_BASE + 4U * i);\n"
  "                }\n"
  "                r.event_overflow_mask = ovf & 0xFFU;\n"
  "                r.applied_event_count = cfg.event_count;\n"
  "                r.event_valid_mask    = armed & ~r.event_overflow_mask;\n"
  "            } else {\n"
  "                /* END_ONLY, unchanged: no event slot is ever armed. */\n"
  "                r.event_valid_mask    = 0U;\n"
  "                r.event_overflow_mask = 0U;\n"
  "                r.applied_event_count = 0U;\n"
  "            }\n"),
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
