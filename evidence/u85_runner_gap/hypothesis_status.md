# Hypothesis status — custom runner vs MLEK NPU-active gap

| Hypothesis | Status | Evidence | Counter-evidence | Next action |
| --- | --- | --- | --- | --- |
| Fast scratch port path (DDR via SRAM port vs DDR via EXT) | REFUTED | fast=ext made kws/ad/mobilenet slower (×1.39/1.32/1.15), routing exact | - | none |
| Fast scratch memory type (DDR vs on-chip SRAM, as MLEK) | REFUTED | on-chip A/B boots 43–48: gap closure −0.014 / 0.001 / 0.000 | - | none |
| MAC power ramping (POWER_CTRL=2 vs 0) | REFUTED | A/B boots 37–42: gap closure 0.005 / 0.001 / 0.000 | - | none |
| Reset / PROT state | UNRESOLVED | driver soft-resets with secure+privileged before each job; vendor never resets | data correct either way | A/B after POWER_CTRL |
| CFG_*_CAP writes | UNRESOLVED | vendor-only write | likely capability regs | A/B if gap remains |
| CPU polling / D-cache | UNRESOLVED | busy loop vs WFE; D-cache off vs on | NPU traffic identical | A/B (WFI) if gap remains |
| Command stream location/attributes | LOW | cmd in DRAM via EXT in both; MEM_ATTR equal | - | only if all above fail |
| Timing adapter (runner leaves TAs at reset; MLEK programs both) | **SUPPORTED** | TA A/B boots 49–56: MLEK TA config closes the gap 1.002 / 0.999 / 0.999 (kws/ad/mobilenet), mac_active & EXT beats unchanged | which reset register is responsible not read out | optional: read TA reset values |
| Clock / cycle domain | UNRESOLVED | CFG_ACLK reads 0 on board in MLEK too | same board, same PMU clock domain expected | wall-clock check (needs CPU timer field) |

Residual after the TA fix: kws 91,058 vs MLEK 91,431 (−0.4 %), ad 146,547 vs 145,976 (+0.4 %), mobilenet 1,452,640 vs 1,448,049 (+0.3 %) — within MLEK's own boot-to-boot spread. Remaining static differences (soft reset, CAP, WFE, D-cache) are not needed to explain the gap and were not tested.
