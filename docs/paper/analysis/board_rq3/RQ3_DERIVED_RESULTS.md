# RQ3 derived results — computed, not interpreted

```
inputs   paper-fvp-formal-evidence-frozen     2dd77839432ac22c…
         paper-board-formal-evidence-frozen   abe945700781d79b…
plan     paper-board-rq3-analysis-plan-anchor 671f35efe30b6e82…
applied  exactly once      rule failures: 0
```

Comparison unit: 7 workloads, `SSE-320 / U85 / 1024` (FVP) against
`Corstone-320 / U85 / 1024` (board). FVP canonical `M1` after `M1==M2==M3`;
board canonical `median(B1,B2,B3)`. Qualification runs excluded from both.

## Primary — workload-ranking preservation

```
Spearman rho        1.0
rank inversions     0
inversion pairs     none
threshold           NONE - no pass/fail rule was preregistered
```

| workload | FVP rank | board rank |
| --- | --- | --- |
| `rnnoise_INT8` | 1 | 1 |
| `kws_micronet_m` | 2 | 2 |
| `ad_medium_int8` | 3 | 3 |
| `vww4_128_128_INT8` | 4 | 4 |
| `yolo-fastest_192_face_v4` | 5 | 5 |
| `mobilenet_v2_1.0_224_INT8` | 6 | 6 |
| `wav2letter_pruned_int8` | 7 | 7 |

Whether `rho = 1.0` constitutes strong validation is a narrative judgement,
deliberately not made here. No threshold was invented to declare it one.

## Secondary — normalized relative workload cost

Each domain normalized **separately** by its own geometric mean.

| workload | FVP normalized | board normalized |
| --- | --- | --- |
| `rnnoise_INT8` | 0.1521 | 0.1619 |
| `kws_micronet_m` | 0.2791 | 0.2858 |
| `ad_medium_int8` | 0.4371 | 0.4459 |
| `vww4_128_128_INT8` | 0.7129 | 0.7027 |
| `yolo-fastest_192_face_v4` | 1.3606 | 1.3309 |
| `mobilenet_v2_1.0_224_INT8` | 4.3570 | 4.2680 |
| `wav2letter_pruned_int8` | 12.7514 | 12.1432 |

The two vectors are presented side by side. **No aggregate deviation metric is
computed** — `L1`, `L2`, `RMSE`, mean absolute %, and `board_norm / fvp_norm` were
never frozen, and selecting one now, with both vectors visible, would be choosing
a statistic to fit the result.

## Board repeatability — raw triplet and median only

| workload | B1 | B2 | B3 | canonical median |
| --- | --- | --- | --- | --- |
| `rnnoise_INT8` | 55,151 | 55,149 | 54,672 | 55,149 |
| `kws_micronet_m` | 97,362 | 96,841 | 97,427 | 97,362 |
| `ad_medium_int8` | 152,977 | 151,876 | 151,918 | 151,918 |
| `vww4_128_128_INT8` | 239,394 | 240,725 | 238,765 | 239,394 |
| `yolo-fastest_192_face_v4` | 455,358 | 453,389 | 452,701 | 453,389 |
| `mobilenet_v2_1.0_224_INT8` | 1,453,996 | 1,452,766 | 1,456,450 | 1,453,996 |
| `wav2letter_pruned_int8` | 4,136,849 | 4,136,385 | 4,141,149 | 4,136,849 |

No spread, CV, standard deviation, percent range, confidence interval, or
pass/fail threshold. No characterisation of the triplets as tight or otherwise —
that would be the same post-hoc statistic in prose form.

## PMU cross-target

```
SRAM_RD/WR, EXT_RD/WR     NOT_EVALUABLE
                          board-collectable; absent from the frozen FVP formal
                          records, which are not re-run

TOTAL / ACTIVE / IDLE     present in both frozen sets, but no canonicalization of
                          board ACTIVE/IDLE across B1/B2/B3 was preregistered

verdict                   MEASUREMENT PATH QUALIFIED
                          COMMON RAW FIELDS AVAILABLE
                          QUANTITATIVE COMPARISON NOT_PREREGISTERED
```

The conditional requirement is closed as far as collectability; it is not
promoted to a quantitative RQ3 result.

## Not computed

```
Board_TOTAL - FVP_TOTAL          rejected in code
Board_TOTAL / FVP_TOTAL          rejected in code
percent error                    rejected in code
aggregate shape distance         not preregistered
repeatability variability stat   not preregistered
quantitative PMU comparison      not preregistered
```

RQ3 validates ranking preservation and relative cost shape. It is not an
absolute timing calibration, and the two absolute figures are not compared even
though both are present in the evidence.

## State

```
RQ3 analysis                APPLIED ONCE
Narrative interpretation    NOT STARTED
```
