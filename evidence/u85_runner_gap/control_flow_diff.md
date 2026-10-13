# Control flow: vendor `test_u85` (custom runner) vs core-driver (MLEK) — static, POST_HOC_DESCRIPTIVE

Sources: vendor copy `build_pmu_events_model/generated/Drivers/u85_driver/u85.c` (the MODEL image APP `0f215ef5…`),
core-driver `ethosu_device_u85.c` / `ethosu_driver.c` in MLEK `b2c0bb2`. Line numbers in `register_diff.csv`.

| step | test_u85 (custom) | core-driver (MLEK) |
| --- | --- | --- |
| 1 | NVIC vector + enable; poll reset_status (no reset issued) | `ethosu_request_power`: **soft reset** (RESET with CPL/CSL = privileged/secure), verify PROT |
| 2 | CMD = 0 (clock/power Q disabled = on) | after reset: AXI/MEM_ATTR init, **POWER_CTRL = 0**, CMD q bits off (power requested) |
| 3 | AXI_SRAM/EXT = 0x21F3F, **CFG_*_CAP = 0x21F3F**, MEM_ATTR = 0 (+ runner knobs at step 5) | AXI_SRAM 0x20F0B, AXI_EXT 0x21F3F, MEM_ATTR 0/0/4/4 |
| 4 | BASEP0..3, QBASE, QSIZE, QCONFIG = 0, REGIONCFG = 0 | QBASE, QSIZE, QCONFIG, BASEP[i], REGIONCFG from defines |
| 5 | printf("Updating POWER_CTRL…") → **runner knob seam** (REGIONCFG/QCONFIG/MEM_ATTR/AXI overrides) | — |
| 6 | **POWER_CTRL = 2** (MAC ramping on) | — (0 since step 2) |
| 7 | CMD = CMD \| 1 (start) | CMD = (CMD & PWR_CLK) \| running |
| 8 | busy loop polling `irq_triggered` (CPU active, D-cache off) | `__WFE()` (CPU sleeps), D-cache on |
| 9 | IRQ: read STATUS, printf, CMD = 2 | IRQ: CMD clear_irq (keep PWR/CLK) |
| 10 | QREAD check, CMD = 0, printf "Testing CPM signals" (**runner PMU seam**), CMD = 0xC | release power (q enable) |

Differences that act **during** the job (between steps 7 and 9): POWER_CTRL (6), reset state / PROT (1),
CFG_*_CAP (3), CPU wait (8), D-cache, timing adapter (MLEK only). Everything else is either aligned already
(AXI, MEM_ATTR, regions — screening 2) or happens after the job ends.

Testable by one A/B each: POWER_CTRL (needs a vendor-copy change: it is written after the knob seam);
CFG_*_CAP (same); soft reset (runner change); CPU wait WFI vs busy loop (vendor-copy `BUSY_SLEEP` undef).
