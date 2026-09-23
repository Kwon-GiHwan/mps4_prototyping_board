# Amendment 8 to the Tier B contract (2026-09-23, after boot 8)

## What boot 8 showed, and what the project already knew

The CPM read seam fired exactly once on 66/66 runs and snapshotted PMCCNTR
= 0 inside the live window. The readout position was therefore never the
cause: the PMU does not engage on this image. The 2026-08-08/09 diagnostic
campaign (PMU_DIAG_PROCEDURE.md, final table) had already located this:
*"root cause는 PMU programming/readback window가 NPU clock/power request
lifetime 밖에 있었던 power-lifecycle integration 결함"*. The qualification
run's `pre` snapshot (before the vendor call) shows pmcr=0x4001,
pmcntenset=0x80000000 and cycle_lo=10592 -- counting already, because that
runner writes `NPU_REG_CMD = 0` (hold clock-Q / power-Q) and waits a guard
BEFORE touching the PMU. The milestone-1 base, and every Tier B image so
far, programmed the PMU while the NPU was still released by the previous
test's `CMD = 0xC`. PMCCNTR_CFG is not involved (case A counted).

## What changes (EVENTS mode only; END_ONLY untouched)

The EVENTS programming block becomes the diag lineage's proven sequence,
copied with its guard constants:
```
CMD = 0 (hold)            DSB ISB  wait POWER_GUARD
disable; clear OVS/CNTEN/INT
PMCR = CNT_EN | EVENT_RST | CYCLE_RST     (one write, power held)
DSB ISB  wait RESET_GUARD
PMCNTENSET = CYCLE | ((1<<count)-1)
PMEVTYPER[i] = codes[i]                   (cnt_en = 1)
cnten readback  ->  base enable block (RMW, idempotent)  ->  call
CPM seam read (amendment 7) -> vendor CMD = 0xC releases as before
```
The amendment-6 post-enable arming write is removed (arming happens once,
in the proven position). Validity terms unchanged (9). Re-run on boot 9.
