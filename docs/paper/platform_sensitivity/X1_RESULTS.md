# X1 results — platform/timing sensitivity of MAC-scaling structure

```
contract   paper-platform-sensitivity-x1-plan-anchor = 31267d1  (applied once)
evidence   paper-platform-sensitivity-x1-evidence-frozen = 0bf3f3c
cells      92 attempted / 92 successful     samples 276     rule failures 0
artifact identity failures 0  (39/39 Vela artifacts matched the frozen X0 hashes)
```

Computed, not interpreted. CLASS A and CLASS B are reported separately and are
never combined into a single rate. No cross-platform ratio, percentage, error
metric or aggregate robustness score is computed anywhere.

## CLASS A — same TA state (U65: SSE-310 ↔ SSE-315, both `TA_OFF`)

| structural item | agreement |
| --- | --- |
| workload ranking | identical order; Spearman `rho = 1.0` at MAC 256 and 512 |
| MAC-step direction | 7/7 |
| scaling class (STRONG/PARTIAL/WEAK) | 7/7 |
| saturation verdict | 7/7 |
| normalized-cost ordering | identical at both MACs |
| **disagreements** | **0** |

**Equality observation** (not a performance comparison, no ratio computed):
on all **14/14** U65 cells the two platforms produced **identical canonical
cycle values**, despite different Fast Models versions (11.24.13 vs 11.31.28)
and different board namespaces (`mps3_board` vs `mps4_board`). The structural
agreement above is therefore exact rather than approximate.

Verdict: `CONSISTENT_ACROSS_TESTED_PLATFORM_TIMING_CONDITIONS`. Scope:
subsystem/FVP sensitivity **under the tested TA_OFF condition**; this is not a
silicon or hardware-platform causal statement.

## CLASS B — TA state differs

### U55: SSE-300 (`TA_ON`) ↔ SSE-310 (`TA_OFF`), MAC {32,64,128,256}

| structural item | agreement |
| --- | --- |
| workload ranking | identical order; `rho = 1.0` at all four MAC points |
| MAC-step direction | **18/18** |
| scaling class | **14/18** |
| saturation verdict | **6/6** (`NONE_OBSERVED` on both sides for every ladder) |
| normalized-cost ordering | identical at all four MAC points |
| disagreements | 4 |

### U65: SSE-300 (`TA_ON`) ↔ SSE-310 (`TA_OFF`) and ↔ SSE-315 (`TA_OFF`)

| structural item | agreement (each pair) |
| --- | --- |
| workload ranking | identical order; `rho = 1.0` at MAC 256 and 512 |
| MAC-step direction | 7/7 |
| scaling class | 5/7 |
| saturation verdict | 7/7 |
| normalized-cost ordering | identical at both MACs |
| disagreements | 2 + 2 |

The two U65 CLASS B comparisons carry the same disagreement list because the
two `TA_OFF` platforms are value-identical (CLASS A above).

### Every CLASS B disagreement, exactly

All 8 are scaling-class label changes at a single adjacent-efficiency step;
none is a ranking, direction, or saturation change.

| npu | workload | MAC step | class @TA_ON | adjacent | class @TA_OFF | adjacent |
| --- | --- | --- | --- | ---: | --- | ---: |
| U55 | ad_medium_int8 | 256 | PARTIAL | 0.6914 | STRONG | 0.8263 |
| U55 | mobilenet_v2_1.0_224_INT8 | 256 | PARTIAL | 0.6727 | STRONG | 0.8587 |
| U55 | vww4_128_128_INT8 | 256 | PARTIAL | 0.6386 | STRONG | 0.7952 |
| U55 | yolo-fastest_192_face_v4 | 256 | PARTIAL | 0.7470 | STRONG | 0.8448 |
| U65 | rnnoise_INT8 | 512 | PARTIAL | 0.6497 | STRONG | 0.7896 |
| U65 | vww4_128_128_INT8 | 512 | PARTIAL | 0.7367 | STRONG | 0.7705 |
| U65 | rnnoise_INT8 (vs SSE-315) | 512 | PARTIAL | 0.6497 | STRONG | 0.7896 |
| U65 | vww4_128_128_INT8 (vs SSE-315) | 512 | PARTIAL | 0.7367 | STRONG | 0.7705 |

Every disagreement is `PARTIAL` on the `TA_ON` side and `STRONG` on the
`TA_OFF` side — a one-label change across the frozen 0.75 boundary, in the
same direction in all eight cases. Verdict for this item:
`PLATFORM_TIMING_SENSITIVE`.

## Answers to the registered questions

```
Q1 ranking preserved?              YES — identical order and rho = 1.0 in every
                                   comparison, both classes, every MAC point
Q2 MAC-step direction preserved?   YES — 32/32 steps across all comparisons
Q3 scaling class preserved?        NO in CLASS B (24/32 steps agree; 8 differ);
                                   YES in CLASS A (7/7)
Q4 saturation verdict preserved?   YES — 20/20 ladder verdicts across all comparisons
Q5 normalized-cost ordering/shape  YES — identical ordering at every MAC point in
                                   every comparison
Q6 where are disagreements?        CLASS A: 0.  CLASS B: 8, all of one kind
                                   (scaling-class label at a 0.75 threshold crossing).
                                   Reported non-causally.
```

## What Q6 does and does not license

The disagreements are `ASSOCIATED_WITH` the comparisons in which TA state
differs, and are absent where TA state is held constant. They remain
`NOT_SEPARATED` from the subsystem and Fast Models differences that co-vary in
those same comparisons.

One bound is available and is stated as a bound only: under the tested
`TA_OFF` condition, varying subsystem **and** Fast Models version together
(SSE-310 → SSE-315) changed nothing at all on 14/14 cells. Whether that
zero-contribution bound transfers to the `TA_ON` condition is
`NOT_EVALUABLE` on this evidence — no platform pair on this stack holds TA
constant at `TA_ON`.

No cross-platform cycle ratio, percentage, error or platform ranking was
computed, and none may be derived from the stored raw cycles.
