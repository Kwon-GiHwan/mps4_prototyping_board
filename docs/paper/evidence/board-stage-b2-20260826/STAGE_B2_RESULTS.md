# Formal board Stage B2 — 7/7 acquired

```
Stage B2 attempted            7
Stage B2 successful        7 / 7

FORMAL_BOARD_SAMPLES         14
workloads at 2/3              7
workloads at 3/3              0

Stage B3                      HOLD
RQ3 analysis                  NOT STARTED
```

Same frozen seven, same canonical order, one **new independent fresh boot** per
workload. The full cycle ran seven times: deploy → read-back identity → listener
alive before `REBOOT` → boot health → exactly one stock inference → formal `B2` →
restore → postflight.

## Acquisition integrity — B1 gates preserved exactly

| gate | result |
| --- | --- |
| declared configuration (`FPGA_PLATFORM_SSE_320` ON, `Z1024`, CPU fallback 0) | 7/7 |
| staged source == frozen deployment identity | 7/7 |
| deploy `source == declared == destination` | 7/7 |
| capture listener alive before `REBOOT` | 7/7 |
| DDR PASS + CPUWAIT cleared | 7/7 |
| inference count 1, completion marker, no fatal | 7/7 |
| profile block parsed completely | 7/7 |
| `NPU TOTAL` present and > 0 | 7/7 |
| `TOTAL == ACTIVE + IDLE` | 7/7 |
| event family `U85_SRAM_EXT_FAMILY` | 7/7 |
| restore read-back | 7/7 |
| postflight `/dev/sdb` absent, mounts 0, UART holders 0 | 7/7 |
| record labelled `B2`, `boot_index = 2` | 7/7 |

## The seven B2 observations

| workload | `B2` TOTAL | ACTIVE | IDLE |
| --- | --- | --- | --- |
| `rnnoise_INT8` | 55,149 | 49,075 | 6,074 |
| `kws_micronet_m` | 96,841 | 90,915 | 5,926 |
| `ad_medium_int8` | 151,876 | 145,935 | 5,941 |
| `vww4_128_128_INT8` | 240,725 | 234,780 | 5,945 |
| `yolo-fastest_192_face_v4` | 453,389 | 447,401 | 5,988 |
| `mobilenet_v2_1.0_224_INT8` | 1,452,766 | 1,446,821 | 5,945 |
| `wav2letter_pruned_int8` | 4,136,385 | 4,130,438 | 5,947 |

Seven distinct `TOTAL` values — no sample carries another workload's record.

## `B2 != B1` is not a failure condition

These are independent physical observations. Numeric equality was **not**
required, not checked, and no rule was added that would stop the stage because a
`B2` value differs from its `B1` counterpart.

That remains the deliberate difference from the FVP contract, where
`M1 == M2 == M3` was an integrity gate on a deterministic simulator. Here the
gate is *validity of the observation*; the degree of repeatability is descriptive
and is evaluated only after B3, in the preregistered analysis.

## Not performed

No ranking, repeatability quantification, normalized cost, Spearman correlation,
FVP-versus-board relationship, or qualification-versus-formal comparison was
computed. Both `B1` and `B2` are now in hand and the comparison is *available* —
it is deliberately left uncomputed until B3 completes and the analysis is
authorized.

## Board state

Original image restored 4/4 by hash after every workload; postflight clean on all
seven — `/dev/sdb` absent, mounts 0, root-inclusive UART holders 0, DDR PASSED,
CPUWAIT cleared.
