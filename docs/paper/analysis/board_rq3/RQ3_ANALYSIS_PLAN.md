# RQ3 analysis plan — frozen before the analyzer reads a board value

Inputs, both immutable:

```
paper-fvp-formal-evidence-frozen     2dd77839432ac22c…   222 samples
paper-board-formal-evidence-frozen   abe945700781d79b…    21 samples
```

## Canonical inputs

```
FVP    canonical value = M1        precondition: M1 == M2 == M3
Board  canonical value = median(B1, B2, B3)
                                   precondition: B1/B2/B3 all valid formal observations
```

Both preconditions were frozen before their respective data existed. Qualification
runs are **not** analysis input on either side.

Comparison unit:

```
7 workloads
FVP    SSE-320 / U85 / 1024   canonical NPU TOTAL × 7
Board  Corstone-320 / U85 / 1024   median(B1,B2,B3) NPU TOTAL × 7
```

## Primary — workload-ranking preservation

Rank the 7 workloads by canonical cost in each domain, then report:

```
Spearman rho
rank inversion count
rank inversion pairs, listed explicitly
```

All seven are executable on both sides, so the full set is used with no subset
reduction. An inversion is a pair whose relative order differs between domains,
and each is named:

```
(A, B)   FVP: A < B   Board: B < A
```

**No pass/fail threshold.** A rule of the form `rho >= X -> validated` is not
created; how strong a validation this constitutes is a narrative judgement made
later, not a number invented here.

## Secondary — normalized relative workload cost

Only the formula frozen before board data:

```
g_FVP   = geomean(FVP_TOTAL_1   … FVP_TOTAL_7)
g_board = geomean(Board_TOTAL_1 … Board_TOTAL_7)

FVP_normalized_i   = FVP_TOTAL_i   / g_FVP
Board_normalized_i = Board_TOTAL_i / g_board
```

The two domains are normalized **separately**. Combining them into a single
geometric mean is rejected.

The permitted output is the two vectors presented side by side. Nothing more.

### No aggregate deviation metric

The frozen plan names *relative-cost-shape deviation* as an objective but never
fixed a scalar formula. `L1`, `L2`, `RMSE`, mean absolute %, and
`board_norm / fvp_norm` were **not** frozen before board data, so choosing one
now — with the values already visible — would be selecting a statistic to fit the
result. Not computed.

If a shape distance is wanted later it must be labelled `POST_HOC_DESCRIPTIVE`
and run as a separate analysis.

## Board repeatability — raw triplet and median only

Per `BOARD_REPEATABILITY_SCOPE_AMENDMENT.md`, recorded before B3:

```
reported:      B1, B2, B3, canonical median
not reported:  relative spread, CV, standard deviation, percent range,
               confidence interval, any repeatability PASS/FAIL threshold
```

Quantitative-sounding narrative such as "board repeatability was high" is also
withheld at this stage. The triplets are preserved as a result artifact; they are
not summarised into a statistic chosen after the fact.

## PMU cross-target — scope narrowed

```
SRAM_RD/WR, EXT_RD/WR     NOT_EVALUABLE
                          board-collectable, but absent from the frozen FVP
                          formal records; those stages are not re-run

TOTAL / ACTIVE / IDLE     present in both frozen record sets
                          BUT no canonicalization of board ACTIVE/IDLE across
                          B1/B2/B3 was ever preregistered
```

So no `median ACTIVE`, `IDLE/TOTAL`, active fraction, or idle fraction is
constructed now. The honest position:

```
PMU bottleneck consistency:
    MEASUREMENT PATH QUALIFIED
    COMMON RAW FIELDS AVAILABLE
    QUANTITATIVE COMPARISON NOT_PREREGISTERED
```

The conditional requirement is closed as far as *collectability*; it is not
promoted to a quantitative RQ3 result.

## Absolute-cycle prohibitions, enforced in code

```
Board_TOTAL - FVP_TOTAL       rejected
Board_TOTAL / FVP_TOTAL       rejected
percent error                 rejected
"hardware is X% slower"       rejected
"FVP overestimates by …"      rejected
```

Enforced even if the two sets of numbers look close. RQ3 validates **ranking
preservation** and **relative cost shape**, not absolute timing calibration.

## Outputs

```
docs/paper/analysis/board_rq3/
  canonical_board_cost.csv        workload, B1, B2, B3, canonical_median
  fvp_board_ranking.csv           workload, fvp_rank, board_rank
  ranking_preservation.json       spearman_rho, inversion_count, inversion_pairs
  normalized_relative_cost.csv    workload, fvp_normalized_cost, board_normalized_cost
  rq3_analysis_meta.json
```

## Order

```
contract complete -> mutation tests -> paper-board-rq3-analysis-plan-anchor
-> frozen FVP + frozen board evidence -> apply exactly once -> derived results
-> paper-board-rq3-analysis-results-frozen -> STOP
```

No narrative interpretation at this stage.
