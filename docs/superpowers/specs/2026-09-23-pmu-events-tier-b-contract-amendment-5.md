# Amendment 5 to the Tier B contract (2026-09-23, after boot 6, before any valid run)

## What boot 6 showed

66/66 runs again counted nothing, and this time `cycle_global_enable_verified`
read 0 (boot 5: 1). The single new write of the amendment-4 sequence was
`PMCR = PMCR | cycle_cnt_rst | event_cnt_rst` with `cnt_en = 1`. After it,
`PMCR.cnt_en` read 0 and the base's read-modify-write enable did not re-set
it within the run. On this RTL the reset pulse is safe only the way the
base has always issued it: with `cnt_en = 0`, before arming.

## What changes (edits 5/6 only; END_ONLY untouched)

The sequence now departs from END_ONLY's proven order in exactly two places:

```
disable -> reset_counters (base, cnt_en=0)
PMCNTENSET = CYCLE | ((1<<count)-1)        [was CYCLE]  -- same single write, extra bits
cnten readback (base)
enable (base) -> PMCR readback -> cycle_global_enable_verified (base)
PMEVTYPER[i] = codes[i]  for i < count     [new]        -- under cnt_en=1, per the TRM clause
run_fixed_inference
```
No PMCR write of ours remains. Until a select lands, its already-armed slot
counts `no_event`, i.e. nothing; the skew is a few MMIO cycles and no value
is interpreted under this contract.

Boot 6 is archived with all 171 verdicts NOT_OBSERVED. Re-run on boot 7.
