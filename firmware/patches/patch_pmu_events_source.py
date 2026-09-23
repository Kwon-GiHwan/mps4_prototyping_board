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
 # 5b. arming: the base's ONE PMCNTENSET write, with the event bits carried in the same
 #     write for EVENTS. Reset pulse stays the base's (under cnt_en=0). No PMCR write of ours:
 #     boot 6 showed a PMCR write of the reset bits under cnt_en=1 leaves cnt_en=0 and the
 #     base's RMW enable cannot re-set it within the run.
 ("            pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);\n",
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B: arm cycle + event slots in the SAME single write the base\n"
  "                 * makes (boot 5: a second write of the event bits alone read back\n"
  "                 * without the cycle bit). Selects are written after enable, below. */\n"
  "                pmu_reg_write(NPU_REG_PMCNTENSET,\n"
  "                              NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U));\n"
  "            } else {\n"
  "                pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);\n"
  "            }\n"),
 # 6. enable block: widen, and select the events AFTER cnt_en=1 is verified (TRM: PMU writes
 #    other than PMCR.cnt_en are not guaranteed to take effect unless cnt_en=1).
 ("        if (cfg.mode == INSTRUMENTATION_END_ONLY) {\n            uint32_t pmcr;\n",
  "        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {\n            uint32_t pmcr;\n"),
 ("                (pmcr & NPU_PMCR_CNT_EN_MSK) ? 1U : 0U;\n",
  "                (pmcr & NPU_PMCR_CNT_EN_MSK) ? 1U : 0U;\n"
  "            if (cfg.mode == INSTRUMENTATION_EVENTS) {\n"
  "                /* Tier B: event selects under cnt_en=1. Slots are already armed;\n"
  "                 * until each select lands the slot counts no_event, i.e. nothing. */\n"
  "                for (i = 0; i < cfg.event_count; i++) {\n"
  "                    pmu_reg_write(NPU_REG_PMEVTYPER_BASE + 4U * i, cfg.event_codes[i] & 0x3FFU);\n"
  "                }\n"
  "                __DSB();\n"
  "            }\n"),
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
