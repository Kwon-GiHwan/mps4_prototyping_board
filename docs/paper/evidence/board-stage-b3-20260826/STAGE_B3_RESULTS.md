# Formal board Stage B3 — 7/7 acquired, campaign complete

```
Stage B3 attempted              7
Stage B3 successful           7/7

FORMAL_BOARD_SAMPLES           21
workloads at 3/3                7

board formal evidence      FROZEN
RQ3 analysis             NOT STARTED
```

## Acquisition gates

```
artifact identity            7/7
fresh boot                   7/7
valid inference              7/7
valid profile                7/7
restore / postflight         7/7
label B3 / boot_index 3      7/7

invalid records                0
fatal                          0
timeout                        0
restore failures               0
```

## The seven B3 observations

| workload | `B3` TOTAL | ACTIVE | IDLE |
| --- | --- | --- | --- |
| `rnnoise_INT8` | 54,672 | 48,596 | 6,076 |
| `kws_micronet_m` | 97,427 | 91,501 | 5,926 |
| `ad_medium_int8` | 151,918 | 145,976 | 5,942 |
| `vww4_128_128_INT8` | 238,765 | 232,818 | 5,947 |
| `yolo-fastest_192_face_v4` | 452,701 | 446,706 | 5,995 |
| `mobilenet_v2_1.0_224_INT8` | 1,456,450 | 1,450,501 | 5,949 |
| `wav2letter_pruned_int8` | 4,141,149 | 4,135,179 | 5,970 |

Seven distinct `TOTAL` values.

`B3 != B1` and `B3 != B2` were not failure conditions and were not checked. No
observation was re-run: the first validly acquired `B1`/`B2`/`B3` are the formal
set.

## Reporting scope — bounded before this stage

Per `BOARD_REPEATABILITY_SCOPE_AMENDMENT.md`, recorded **before** B3 ran:

```
frozen before formal data:   canonical_board_cost = median(B1, B2, B3)
permitted after B3:          the raw triplet, and the canonical median
not permitted:               relative_spread, CV, % deviation, or any
                             variability statistic chosen after B1/B2 were seen
```

The raw triplets are reportable because they are the observations themselves. A
variability statistic would be a *choice* made with the data already visible, so
it is inadmissible as a preregistered RQ3 metric.

## Not performed

No ranking, Spearman correlation, normalized cost, relative-cost shape,
repeatability quantification, FVP-versus-board relationship, or
qualification-versus-formal comparison. The full 21-sample set is now in hand and
every one of those is computable — each is deliberately left uncomputed pending a
separate RQ3 analysis authorization.

## Board state

Original image restored 4/4 by hash after every workload across all three stages;
postflight clean on all 21 runs — `/dev/sdb` absent, mounts 0, root-inclusive
UART holders 0, DDR PASSED, CPUWAIT cleared.
