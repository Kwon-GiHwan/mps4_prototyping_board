# P0-E2 results

Per-layer IRQ measurement of Wav2Letter and MobileNetV2 on Ethos-U85, six
cells. Calculation only: no interpretation, no causal statement, no
comparison across NPU generations. Contract:
`docs/superpowers/plans/2026-09-16-p0e2-two-workload-extension-plan.md`.
Limits and departures: `P0E2_LIMITATIONS.md`.

Approval: repository owner's direct instruction. There is no manager GO
for this extension (contract section 9).

## 1. Cells

| cell | MACs | system config | ops | clean cycles | active | idle | windows |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| wav2letter_pruned_int8__256_Low | 256 | Ethos_U85_SYS_DRAM_Low | 226 | 15147068 | 15146719 | 349 | 114 |
| wav2letter_pruned_int8__512_Mid512 | 512 | Ethos_U85_SYS_DRAM_Mid_512 | 39 | 7654068 | 7653598 | 470 | 21 |
| wav2letter_pruned_int8__512_Low | 512 | Ethos_U85_SYS_DRAM_Low | 228 | 10137068 | 10136159 | 909 | 114 |
| mobilenet_v2_1.0_224_INT8__256_Low | 256 | Ethos_U85_SYS_DRAM_Low | 221 | 2874068 | 2873773 | 295 | 176 |
| mobilenet_v2_1.0_224_INT8__512_Mid512 | 512 | Ethos_U85_SYS_DRAM_Mid_512 | 216 | 1914068 | 1913404 | 664 | 179 |
| mobilenet_v2_1.0_224_INT8__512_Low | 512 | Ethos_U85_SYS_DRAM_Low | 220 | 1869068 | 1868401 | 667 | 180 |

`ops` is the number of non-DMA operation launches instrumented with
`NPU_OP_IRQ`; `windows` is the number of IRQ service windows the target
actually recorded. One window can cover several launches, so the two
differ; the window is the unit of attribution.

## 2. Clean cycles against the frozen sweep

`256_Low` and `512_Mid512` are the bindings the frozen U85 sweep used, so
their clean cycle counts have a counterpart in `canonical_cells.csv`.
`512_Low` does not and is left blank.

| cell | clean cycles | canonical_cells.csv | equal |
| --- | ---: | ---: | --- |
| wav2letter_pruned_int8__256_Low | 15147068 | 15147068 | yes |
| wav2letter_pruned_int8__512_Mid512 | 7654068 | 7654068 | yes |
| wav2letter_pruned_int8__512_Low | 10137068 | (no frozen counterpart) | |
| mobilenet_v2_1.0_224_INT8__256_Low | 2874068 | 2874068 | yes |
| mobilenet_v2_1.0_224_INT8__512_Mid512 | 1914068 | 1914068 | yes |
| mobilenet_v2_1.0_224_INT8__512_Low | 1869068 | (no frozen counterpart) | |

## 3. Direction, whole model

Preregistered rule, no threshold: `delta(b) = clean_512(b) - clean_256`;
REGRESS iff delta > 0, IMPROVE iff delta < 0, SAME iff delta = 0.

| workload | pair | clean 256 | clean 512 | delta | direction |
| --- | --- | ---: | ---: | ---: | --- |
| wav2letter_pruned_int8 | B-frozen | 15147068 | 7654068 | -7493000 | IMPROVE |
| wav2letter_pruned_int8 | B-held | 15147068 | 10137068 | -5010000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 2874068 | 1914068 | -960000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 2874068 | 1869068 | -1005000 | IMPROVE |

## 4. Operator-level separability

| workload | pair | source ops | separable | NOT_SEPARATED | IMPROVE | REGRESS | SAME |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wav2letter_pruned_int8 | B-frozen | 12 | 2 | 10 | 1 | 1 | 0 |
| wav2letter_pruned_int8 | B-held | 12 | 2 | 10 | 1 | 1 | 0 |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 65 | 37 | 28 | 28 | 7 | 2 |
| mobilenet_v2_1.0_224_INT8 | B-held | 65 | 36 | 29 | 28 | 6 | 2 |

## 5. Group differential

Groups are the finest partition common to both sides of a pair, from
`pd_groups.py` unchanged. Group cycles are exact sums on both sides.

| workload | pair | groups | IMPROVE | REGRESS | SAME | sum delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| wav2letter_pruned_int8 | B-frozen | 3 | 2 | 1 | 0 | -7490395 |
| wav2letter_pruned_int8 | B-held | 3 | 2 | 1 | 0 | -4990000 |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 43 | 34 | 7 | 2 | -960955 |
| mobilenet_v2_1.0_224_INT8 | B-held | 41 | 33 | 6 | 2 | -1005940 |

The five largest groups by |delta| per workload and pair:

| workload | pair | ops | types | cycles 256 | cycles 512 | delta | direction |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| wav2letter_pruned_int8 | B-frozen | 11 | Conv2D KERNEL_WAIT | 15075585 | 7544190 | -7531395 | IMPROVE |
| wav2letter_pruned_int8 | B-frozen | 1 | Conv2D | 52015 | 94015 | +42000 | REGRESS |
| wav2letter_pruned_int8 | B-frozen | 1 | Softmax | 17180 | 16180 | -1000 | IMPROVE |
| wav2letter_pruned_int8 | B-held | 11 | Conv2D KERNEL_WAIT | 15075585 | 10044600 | -5030985 | IMPROVE |
| wav2letter_pruned_int8 | B-held | 1 | Conv2D | 52015 | 94015 | +42000 | REGRESS |
| wav2letter_pruned_int8 | B-held | 1 | Softmax | 17180 | 16165 | -1015 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 1 | Conv2D | 319285 | 156285 | -163000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 19 | Add Conv2D DepthwiseConv2D KERNEL_WAIT | 455195 | 359195 | -96000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 1 | Conv2D | 139045 | 66045 | -73000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 1 | Conv2D | 137045 | 66045 | -71000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-frozen | 1 | DepthwiseConv2D | 128045 | 63045 | -65000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 1 | Conv2D | 319285 | 156285 | -163000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 22 | Add Conv2D DepthwiseConv2D KERNEL_WAIT | 521225 | 389225 | -132000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 1 | Conv2D | 139045 | 66045 | -73000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 1 | Conv2D | 137045 | 66045 | -71000 | IMPROVE |
| mobilenet_v2_1.0_224_INT8 | B-held | 1 | DepthwiseConv2D | 128045 | 63045 | -65000 | IMPROVE |

## 6. Convolution share, measured against the Vela estimate

Contract section 4 recorded, before the data existed, the Vela-estimated
convolution share: Wav2Letter 99.9%, MobileNetV2 80.5%. The measurement is
adopted whatever it shows; this table exists to extend the
estimate-versus-measurement record, not to decide anything.

Measured share is over *separable* operators only, since a NOT_SEPARATED
operator has no cycle count of its own. The unassigned column is the share
of unit cycles in windows that no single source operator owns.

| workload | binding | conv cycles | separable total | conv share | unassigned share |
| --- | --- | ---: | ---: | ---: | ---: |
| wav2letter_pruned_int8 | 256_Low | 1784190 | 1801370 | 99.0% | 88.1% |
| wav2letter_pruned_int8 | 512_Mid512 | 7638205 | 7654385 | 99.8% | 0.0% |
| wav2letter_pruned_int8 | 512_Low | 1318190 | 1334355 | 98.8% | 86.9% |
| mobilenet_v2_1.0_224_INT8 | 256_Low | 2233320 | 2246440 | 99.4% | 21.8% |
| mobilenet_v2_1.0_224_INT8 | 512_Mid512 | 1504380 | 1521545 | 98.9% | 20.4% |
| mobilenet_v2_1.0_224_INT8 | 512_Low | 1404350 | 1421515 | 98.8% | 23.8% |

Estimate against measurement, in percentage points:

| workload | Vela estimate | measured (256_Low) | difference |
| --- | ---: | ---: | ---: |
| wav2letter_pruned_int8 | 99.9% | 99.0% | -0.9 pp |
| mobilenet_v2_1.0_224_INT8 | 80.5% | 99.4% | +18.9 pp |

The September campaign's five workloads spanned 0.0 to 41.2 percentage
points on this comparison. These two fall inside that span. The
measurement is what is recorded; the estimate is not used to fill any
cell.

## 7. Sum coherence

`sum(window cycles) - clean cycles`, against the envelope derived from the
fifteen frozen September cells (3000 cycles absolute and 3.0% relative,
both required; see `P0E2_LIMITATIONS.md`).

| cell | window sum | clean cycles | residual | ratio |
| --- | ---: | ---: | ---: | ---: |
| wav2letter_pruned_int8__256_Low | 15144780 | 15147068 | -2288 | -0.0151% |
| wav2letter_pruned_int8__512_Mid512 | 7654385 | 7654068 | +317 | +0.0041% |
| wav2letter_pruned_int8__512_Low | 10154780 | 10137068 | +17712 | +0.1747% |
| mobilenet_v2_1.0_224_INT8__256_Low | 2871710 | 2874068 | -2358 | -0.0820% |
| mobilenet_v2_1.0_224_INT8__512_Mid512 | 1910755 | 1914068 | -3313 | -0.1731% |
| mobilenet_v2_1.0_224_INT8__512_Low | 1865770 | 1869068 | -3298 | -0.1765% |

## 8. Per-cell verdict

Tri-state, from the gate run. A cell is PASS only if every gate that
applies to it passed; FAIL names the gates that refused. There is no
"probably fine".

| cell | verdict | refusing gates |
| --- | --- | --- |
| wav2letter_pruned_int8__256_Low | PASS |  |
| wav2letter_pruned_int8__512_Mid512 | PASS |  |
| wav2letter_pruned_int8__512_Low | FAIL | RULE_P0E2_SUM_COHERENT |
| mobilenet_v2_1.0_224_INT8__256_Low | PASS |  |
| mobilenet_v2_1.0_224_INT8__512_Mid512 | FAIL | RULE_P0E2_SUM_COHERENT |
| mobilenet_v2_1.0_224_INT8__512_Low | FAIL | RULE_P0E2_SUM_COHERENT |

The refusals are all `RULE_P0E2_SUM_COHERENT`, and all of them are the
absolute term of the envelope, not the ratio term. Every one of the six
cells is within 0.18% relatively, against a 3.0% bound and against a
September spread reaching 2.14%. The absolute term, 3000 cycles, was
derived from cells whose clean totals are 36,086 to 812,074 cycles;
these cells run 1,869,068 to 15,147,068. The envelope was registered
before these cells were measured and has not been changed now that it
has fired. Changing it is a decision for the operator and would be
recorded as an amendment, not an edit.

## 9. Gates

```
RULE                         SUBJECT                                        VERDICT
------------------------------------------------------------------------------------------------
RULE_P0E2_MODEL_SHA          both workloads                                 PASS
RULE_P0E2_TOOLCHAIN          vela/mlek/core-driver/fvp                      PASS
RULE_P0E2_PATCH_IDENTITY     september patch digests                        PASS
RULE_P0E2_IRQ_VALID          mobilenet_v2_1.0_224_INT8__256_Low             PASS
RULE_P0E2_LAYER_CAP          mobilenet_v2_1.0_224_INT8__256_Low             PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__256_Low/clean       PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__256_Low/prof        PASS
RULE_P0E2_OUTPUT_CRC         mobilenet_v2_1.0_224_INT8__256_Low             PASS
RULE_P0E2_IRQ_VALID          mobilenet_v2_1.0_224_INT8__512_Low             PASS
RULE_P0E2_LAYER_CAP          mobilenet_v2_1.0_224_INT8__512_Low             PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__512_Low/clean       PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__512_Low/prof        PASS
RULE_P0E2_OUTPUT_CRC         mobilenet_v2_1.0_224_INT8__512_Low             PASS
RULE_P0E2_IRQ_VALID          mobilenet_v2_1.0_224_INT8__512_Mid512          PASS
RULE_P0E2_LAYER_CAP          mobilenet_v2_1.0_224_INT8__512_Mid512          PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__512_Mid512/clean    PASS
RULE_P0E2_REPS_EXACT         mobilenet_v2_1.0_224_INT8__512_Mid512/prof     PASS
RULE_P0E2_OUTPUT_CRC         mobilenet_v2_1.0_224_INT8__512_Mid512          PASS
RULE_P0E2_IRQ_VALID          wav2letter_pruned_int8__256_Low                PASS
RULE_P0E2_LAYER_CAP          wav2letter_pruned_int8__256_Low                PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__256_Low/clean          PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__256_Low/prof           PASS
RULE_P0E2_OUTPUT_CRC         wav2letter_pruned_int8__256_Low                PASS
RULE_P0E2_IRQ_VALID          wav2letter_pruned_int8__512_Low                PASS
RULE_P0E2_LAYER_CAP          wav2letter_pruned_int8__512_Low                PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__512_Low/clean          PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__512_Low/prof           PASS
RULE_P0E2_OUTPUT_CRC         wav2letter_pruned_int8__512_Low                PASS
RULE_P0E2_IRQ_VALID          wav2letter_pruned_int8__512_Mid512             PASS
RULE_P0E2_LAYER_CAP          wav2letter_pruned_int8__512_Mid512             PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__512_Mid512/clean       PASS
RULE_P0E2_REPS_EXACT         wav2letter_pruned_int8__512_Mid512/prof        PASS
RULE_P0E2_OUTPUT_CRC         wav2letter_pruned_int8__512_Mid512             PASS
RULE_P0E2_SUM_COHERENT       mobilenet_v2_1.0_224_INT8__256_Low             PASS
RULE_P0E2_SUM_COHERENT       mobilenet_v2_1.0_224_INT8__512_Low             FAIL
    [RULE_P0E2_SUM_COHERENT] mobilenet_v2_1.0_224_INT8__512_Low: residual -3298 cycles exceeds 3000
RULE_P0E2_SUM_COHERENT       mobilenet_v2_1.0_224_INT8__512_Mid512          FAIL
    [RULE_P0E2_SUM_COHERENT] mobilenet_v2_1.0_224_INT8__512_Mid512: residual -3313 cycles exceeds 3000
RULE_P0E2_SUM_COHERENT       wav2letter_pruned_int8__256_Low                PASS
RULE_P0E2_SUM_COHERENT       wav2letter_pruned_int8__512_Low                FAIL
    [RULE_P0E2_SUM_COHERENT] wav2letter_pruned_int8__512_Low: residual 17712 cycles exceeds 3000
RULE_P0E2_SUM_COHERENT       wav2letter_pruned_int8__512_Mid512             PASS
RULE_P0E2_IDENTITY_JOIN      wav2letter_pruned_int8 B-frozen                PASS
RULE_P0E2_IDENTITY_JOIN      wav2letter_pruned_int8 B-held                  PASS
RULE_P0E2_IDENTITY_JOIN      mobilenet_v2_1.0_224_INT8 B-frozen             PASS
RULE_P0E2_IDENTITY_JOIN      mobilenet_v2_1.0_224_INT8 B-held               PASS
RULE_P0E2_RESTORE            patch targets                                  PASS
------------------------------------------------------------------------------------------------
checks: 44  FAIL=3  PASS=41
rules evaluated: 10/10
```

## 10. Regression over the existing five workloads

```
view cells: 24
analyzer workloads: ['rnnoise_INT8', 'vww4_128_128_INT8', 'yolo-fastest_192_face_v4', 'kws_micronet_m', 'ad_medium_int8', 'dnn_s_quantized', 'wav2letter_pruned_int8', 'mobilenet_v2_1.0_224_INT8']
diff rows: 656 match rows: 656 unit rows: 1446
wrote U85_256_512_DIFFERENTIAL.csv, U85_OPERATOR_MATCH.csv
group rows: 405
pd_analyzer.py unchanged: 9f552255801fa99c

== regression: existing five workloads ==
  U85_256_512_DIFFERENTIAL.csv     byte-order    UNCHANGED  (502 rows)
                                                 +154 new rows
  U85_OPERATOR_MATCH.csv           byte-order    UNCHANGED  (502 rows)
                                                 +154 new rows
  U85_ATTRIBUTION_UNITS.csv        byte-order    UNCHANGED  (656 rows)
                                                 +790 new rows
  U85_GROUP_DIFFERENTIAL.csv       row-multiset  UNCHANGED  (315 rows)
                                                 +90 new rows
regression: PASS

formal matrix: existing 7963 bytes preserved as prefix: True
formal matrix rows now: 24
published 4 CSVs to /Users/gihwan/Documents/Projects/mps4_prototyping_board/docs/paper/mechanism
```

