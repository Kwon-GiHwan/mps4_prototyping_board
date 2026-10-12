# Hypothesis status — custom runner vs MLEK NPU-active gap

| Hypothesis | Status | Evidence | Counter-evidence | Next action |
| --- | --- | --- | --- | --- |
| Fast scratch path | REFUTED | fast=ext made kws/ad/mobilenet slower (×1.39/1.32/1.15), routing exact | - | none |
| MAC power ramping (POWER_CTRL=2 vs 0) | UNRESOLVED (top static candidate) | only during-job NPU register that differs; acts on MAC start/stop; extra cycles are non-MAC-active | effect size unknown | A/B: POWER_CTRL 0 vs 2, kws then ad |
| Reset / PROT state | UNRESOLVED | driver soft-resets with secure+privileged before each job; vendor never resets | data correct either way | A/B after POWER_CTRL |
| CFG_*_CAP writes | UNRESOLVED | vendor-only write | likely capability regs | A/B if gap remains |
| CPU polling / D-cache | UNRESOLVED | busy loop vs WFE; D-cache off vs on | NPU traffic identical | A/B (WFI) if gap remains |
| Command stream location/attributes | LOW | cmd in DRAM via EXT in both; MEM_ATTR equal | - | only if all above fail |
| Timing adapter | LOW PRIORITY | MLEK enables it | would slow MLEK | last |
| Clock / cycle domain | UNRESOLVED | CFG_ACLK reads 0 on board in MLEK too | same board, same PMU clock domain expected | wall-clock check (needs CPU timer field) |
