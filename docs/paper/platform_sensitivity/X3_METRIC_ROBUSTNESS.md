# X3 — structural-metric robustness synthesis

Analysis and synthesis only: **no new data was collected**. Inputs are the
frozen X0 comparability evidence and the frozen X1 formal evidence/results,
with every metric definition taken unchanged from the paper's earlier frozen
contracts. All counts below were **recomputed from the frozen evidence**, not
copied from expectations.

```
inputs   paper-platform-sensitivity-x0-frozen          = 78018ac
         paper-platform-sensitivity-x1-evidence-frozen = 0bf3f3c
         paper-platform-sensitivity-x1-results-frozen  = 3ad7bb9
```

CLASS A (same TA state) and CLASS B (TA state differs) are reported
separately and are never pooled into one statistic.

## 1. Tested comparison universe

```
CLASS A   U65   SSE-310 ↔ SSE-315         TA_OFF ↔ TA_OFF
CLASS B   U55   SSE-300 ↔ SSE-310         TA_ON  ↔ TA_OFF
          U65   SSE-300 ↔ SSE-310         TA_ON  ↔ TA_OFF
          U65   SSE-300 ↔ SSE-315         TA_ON  ↔ TA_OFF
```

Every comparison holds model, NPU, MAC and the exact Vela NPU artifact fixed;
only the Corstone/FVP subsystem — and, in CLASS B, the timing-adapter state
and Fast Models implementation — differ.

## 2. Metric-by-metric synthesis

| metric | class | tested universe | agreement | disagreement |
| --- | --- | ---: | ---: | ---: |
| workload ranking | A | 2 MAC points | 2 | 0 |
| workload ranking | B | 8 MAC points | 8 | 0 |
| MAC-step direction | A | 7 steps | 7 | 0 |
| MAC-step direction | B | 32 steps | 32 | 0 |
| scaling class (STRONG/PARTIAL/WEAK) | A | 7 steps | 7 | 0 |
| scaling class | B | 32 steps | **24** | **8** |
| saturation verdict | A | 7 ladders | 7 | 0 |
| saturation verdict | B | 20 ladders | 20 | 0 |
| normalized workload ordering | A | 2 MAC points | 2 | 0 |
| normalized workload ordering | B | 8 MAC points | 8 | 0 |

Ranking agreement means identical order **and** Spearman `rho = 1.0` at that
MAC point. Normalized ordering means the geomean-normalized within-platform
cost ordering is identical; no scalar similarity between the two normalized
vectors is computed.

### The eight disagreements, in full

All eight are scaling-class label changes at a single adjacent-efficiency
step. None is a ranking, direction, or saturation change.

| npu | workload | MAC step | class @ TA_ON | adjacent | class @ TA_OFF | adjacent |
| --- | --- | --- | --- | ---: | --- | ---: |
| U55 | ad_medium_int8 | 256 | PARTIAL | 0.6914 | STRONG | 0.8263 |
| U55 | mobilenet_v2_1.0_224_INT8 | 256 | PARTIAL | 0.6727 | STRONG | 0.8587 |
| U55 | vww4_128_128_INT8 | 256 | PARTIAL | 0.6386 | STRONG | 0.7952 |
| U55 | yolo-fastest_192_face_v4 | 256 | PARTIAL | 0.7470 | STRONG | 0.8448 |
| U65 | rnnoise_INT8 (vs SSE-310) | 512 | PARTIAL | 0.6497 | STRONG | 0.7896 |
| U65 | vww4_128_128_INT8 (vs SSE-310) | 512 | PARTIAL | 0.7367 | STRONG | 0.7705 |
| U65 | rnnoise_INT8 (vs SSE-315) | 512 | PARTIAL | 0.6497 | STRONG | 0.7896 |
| U65 | vww4_128_128_INT8 (vs SSE-315) | 512 | PARTIAL | 0.7367 | STRONG | 0.7705 |

Every one crosses the frozen 0.75 boundary in the same direction: `PARTIAL`
on the TA_ON side, `STRONG` on the TA_OFF side. The scaling *direction* never
changes; what changes is which side of a fixed cut point the value falls on.

## 3. The CLASS A exact-cycle observation

Re-verified from the frozen raw cells: **14/14** U65 cells.

> Under the tested TA-OFF condition, changing from SSE-310 to SSE-315
> produced no observable change in canonical NPU cycles for any of the 14
> evaluated cells.

> This observation does not establish that subsystem/Fast-Models differences
> are generally irrelevant, nor does it transfer to TA-ON conditions.

Classification: `NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR`.
Not claimed: subsystem invariance, Fast-Models-version invariance, or general
TA-OFF equivalence. Transfer to TA-ON is `NOT_EVALUABLE` — no platform pair on
this stack holds TA constant at TA_ON.

*(Wording refinement: the frozen X1 results phrased this as a
"zero-contribution bound". X3 supersedes that phrasing with the narrower
statement above; the frozen X1 document is left unmodified.)*

## 4. Timing-adapter interpretation

Allowed and asserted:

> The scaling-class disagreements were observed only in comparisons where TA
> state also differed.

The disagreements are `ASSOCIATED_WITH` those comparisons. They are **not**
attributed to the timing adapter: in CLASS B the subsystem, the Fast Models
implementation and the TA state change together, so these factors remain
`NOT_SEPARATED`. `CAUSED_BY` is not used.

## 5. Metric qualification (final table)

| metric | qualification |
| --- | --- |
| workload ranking | `ROBUST_IN_TESTED_PAIRS` |
| MAC-step direction | `ROBUST_IN_TESTED_PAIRS` |
| saturation verdict | `ROBUST_IN_TESTED_PAIRS` |
| normalized workload ordering | `ROBUST_IN_TESTED_PAIRS` |
| threshold scaling class (STRONG/PARTIAL/WEAK) | `TA_STATE_SENSITIVE` |
| raw cross-platform cycles | `NOT_COMPARABLE` |
| memory PMU counters | `GENERATION_SPECIFIC_NOT_COMMON` |
| transfer of the CLASS A result to TA_ON | `NOT_EVALUABLE` |

Machine-readable in `X3_METRIC_QUALIFICATION.csv`. No numerical robustness
score, percentage, or index is defined anywhere — the raw agreement counts
above are the result.

## 6. Scope-qualified reading

For the tested U55/U65 platform pairs, with model, NPU, MAC and the exact NPU
artifact held fixed: ordinal and directional conclusions were preserved, while
threshold-based scaling classes were more sensitive to timing-model
configuration. Nothing here extends to untested platforms, to Ethos-U85
(which has no peer platform on this stack), or to absolute cross-platform
cycle comparison, which remains `NOT_COMPARABLE`.
