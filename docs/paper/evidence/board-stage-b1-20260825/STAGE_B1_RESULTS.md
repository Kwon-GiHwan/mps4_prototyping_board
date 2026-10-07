# Formal board Stage B1 — 7/7 acquired

```
Stage B1 attempted            7
Stage B1 successful        7 / 7

FORMAL_BOARD_SAMPLES          7
workloads at 1/3              7
workloads at 3/3              0

Stage B2 / B3                 HOLD
RQ3 analysis                  NOT STARTED
```

Each workload received its **own independent fresh boot**. Boot #1 is not a
shared boot across the seven — the FPGA artifacts are target- and
workload-specific, so the unit ran seven times end to end: deploy → read-back →
listener before reset → boot health → one stock inference → formal `B1` →
evidence → restore → postflight.

No qualification boot or run was reused as a formal sample.

## Acquisition integrity

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

## The seven formal observations

| workload | `B1` TOTAL | ACTIVE | IDLE |
| --- | --- | --- | --- |
| `rnnoise_INT8` | 55,151 | 49,072 | 6,079 |
| `kws_micronet_m` | 97,362 | 91,431 | 5,931 |
| `ad_medium_int8` | 152,977 | 147,041 | 5,936 |
| `vww4_128_128_INT8` | 239,394 | 233,445 | 5,949 |
| `yolo-fastest_192_face_v4` | 455,358 | 449,373 | 5,985 |
| `mobilenet_v2_1.0_224_INT8` | 1,453,996 | 1,448,049 | 5,947 |
| `wav2letter_pruned_int8` | 4,136,849 | 4,130,911 | 5,938 |

Seven distinct `TOTAL` values — no sample carries another workload's record.

## Physical repeatability is not an acquisition gate

`B1`, `B2`, `B3` are independent physical observations, so numeric equality is
**not** required and is not checked. That is why the frozen protocol takes
`median(B1, B2, B3)` rather than asserting equality, and it is the deliberate
difference from the FVP contract, where `M1 == M2 == M3` was an integrity gate on
a deterministic simulator.

No rule was invented that would hard-stop Stage B2 because `B2 != B1`. Validity
of the observation is the gate; the degree of repeatability is described after
B3, in the preregistered analysis.

The `B1` values differ slightly from the earlier qualification runs, as expected
for independent physical executions. Qualification values are **not** part of
formal repeatability and are not carried into the formal set.

## Not performed

No Spearman `rho`, rank inversions, geometric-mean normalization, relative-cost
shape, FVP-versus-board comparison, qualification-versus-formal comparison, or
repeatability interpretation. Stage B1 examined acquisition integrity only.
