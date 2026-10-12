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
| Timing adapter (runner leaves TAs at reset; MLEK programs both) | UNRESOLVED — top candidate | slowdown independent of memory placement (3 memories tried); TAs sit in front of both NPU ports; MLEK board log 'Configured TA_SRAM/EXT' | MLEK's own TA config adds latency | TA A/B (contract 566694b) |
| Clock / cycle domain | UNRESOLVED | CFG_ACLK reads 0 on board in MLEK too | same board, same PMU clock domain expected | wall-clock check (needs CPU timer field) |
