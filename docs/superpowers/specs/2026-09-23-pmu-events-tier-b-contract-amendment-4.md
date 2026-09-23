# Amendment 4 to the Tier B contract (2026-09-23, after boot 5, before any valid run)

## What boot 5 showed

66/66 runs completed with rc=0, mode 2 applied, count echoed, valid mask
full, no overflow — and 0 window cycles and 0 in every event slot, with
`cycle_counter_armed` reading 0 on 64 runs and 1 on 2 (set 22 reps 2-3), the
latter still counting nothing. The only difference from END_ONLY, whose
cycle window has been non-zero in every prior campaign, is that EVENTS mode
wrote PMEVTYPER x8 and PMCNTENSET while `PMCR.cnt_en = 0`.

That is the case the TRM names on the PMU register summary page: *"Register
writes to the PMU, other than those that modify PMCR.cnt_en, are not
guaranteed to take effect unless PMCR.cnt_en=1."* Tier A's readbacks under
cnt_en=0 matched (P0 == P1); readback is not "took effect for counting".
END_ONLY's single arming write under cnt_en=0 has always taken effect, so the
clause is real and END_ONLY sits inside whatever the RTL tolerates.

## What changes (firmware edit 5 only; END_ONLY untouched)

In EVENTS mode the run path now, after the base's disable + reset:
```
npu_pmu_enable()                                  cnt_en = 1 FIRST
PMEVTYPER[i] = codes[i]      for i < count
PMCNTENSET  = CYCLE | ((1<<count)-1)              one write, cycle bit carried
PMCR       |= cycle_cnt_rst | event_cnt_rst       all counters restart from 0 together
cnten = PMCNTENSET                                readback under cnt_en=1
```
Consequence, preregistered: the window now includes the programming MMIO
(a few hundred cycles). `window_cycles` is not a performance metric in this
contract; the cycle event (id 17) and PMCCNTR share the reset pulse, which
is what `CYCLE_EVENT_VS_PMCCNTR` (+/-1 %) requires. If the reset pulse
clears enables on this RTL, `cycle_counter_armed` reads 0 and the run is
INVALID by the existing terms — no new term is needed.

Boot 5 is archived with all 171 verdicts NOT_OBSERVED. The campaign re-runs
on boot 6 with the rebuilt image (new digests recorded at deploy).
