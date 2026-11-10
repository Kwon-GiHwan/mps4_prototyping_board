# Stage 4C-1 — output-write beat prediction on new channel counts (frozen 2026-11-10, before boot 338)

Owner directive 2026-11-10 ("Stage 4C-1 — 새로운 채널 조건에서 출력 쓰기 전송량 예측 검증"). **TA: MLEK's own
sys_dram_mid set-up = TA profile 1.** FI101 Ethos-U85 1024 MAC, official driver (driver runner, the Stage 4 image
`83398c7`: boot `1b5c0adb`, bram `4f592f24`, ddr `374708ff`, images.txt `af688281`), WAIT_WFE, caches as before,
Vela 5.0.0 with MLEK's options, INT8, graph I/O in DRAM as in Stage 4, Stage 1 pass A and Stage 3 pass B, 1 warm-up +
4 measured RUNs per config and pass (6 configs × 2 passes × 5 = 60 RUNs, the cap). Stage 4A/4B's contract, data and
verdicts are unchanged; Cout 95 and DW 143 are referenced, not re-measured. Excluded: FC, spatial size, SRAM placement,
QREAD, PMU mask, IRQ, barriers, new instrumentation.

## Question

Does rule A of `evidence/stage4/beat_model.py` (each pixel's channels in ≤ 16-byte chunks, each chunk costing the
16-byte-aligned segments it touches, no merging) predict the output-write beats for channel counts with other
remainders mod 16 (14 and 1), and how do MAC_ACTIVE, transfers and NPU_ACTIVE change at the boundary? Not asked: the
internal DMA/AXI implementation, per-operator times of the source models.

## Configurations (`results/fi101_stage4c1/stage4c1_compile_table.csv`)

| config | shape | C mod 16 | role | MACs |
| --- | --- | ---: | --- | ---: |
| s4_conv_base | Conv 1×1, 24×24, Cin 16 → Cout 96, VALID, RELU6 | 0 | Stage 4 base, re-confirmed | 884,736 |
| s4c_conv_cout94 | Cout 94 | 14 | new | 866,304 |
| s4c_conv_cout97 | Cout 97 | 1 | new | 893,952 |
| s4_dw_base | DWConv 3×3, 56×56, C 144, SAME, multiplier 1, RELU6 | 0 | Stage 4 base, re-confirmed | 4,064,256 |
| s4c_dw_c142 | C 142 | 14 | new | 4,007,808 |
| s4c_dw_c145 | C 145 | 1 | new | 4,092,480 |

Derivation (`host/container/stage4c_models.py`): from the Stage 4 base arrays; smaller = last channels dropped; larger =
channels appended from EXTRA_SEED 20261110 (weights, bias, DW IFM channel) with the generator's ranges; OFM scale = the
base's (no per-shape calibration); per-channel weight scales kept. Checked in the container: every shared channel's
IFM, weights, bias, weight/bias scales, IFM and OFM scales equal the base's (4/4). Bases: the Stage 4 DRWLs, rebuilt and
byte-identical (`2681c566`, `156e1fe3`); the generator refactor keeps all 12 Stage 1/4 models byte-identical.

Gate B (compile): 6/6 PASS — one Ethos-U custom op (no CPU fallback), one scheduled operation of the intended type plus
the 0-cycle RELU6, one kernel kind, MACs as above, debug-db and packer Vela outputs equal. Vela changed the schedule
for Cout 97 (OFM block 6×12×96 → 6×12×112, ublock 2×2×32 → 2×4×16, first weight DMA 1,024 → 736 B): an observation,
not an exclusion. NOT_COMPARABLE before the board: none (all dense NHWC, IFM/OFM in DRAM).

## Pre-registered predictions (`results/fi101_stage4c1/predictions.json`, `stage4c1_predictions.csv`)

Procedure (`host/analysis/stage4c1.py predict`, inputs only from the artifacts): decode the registers of the command
stream the board runs (`.drwl.cms.bin`, sha256 = meta `cms_sha256`); OFM absolute address = the runner's arena
(0x70000000 + Vela model length rounded up to 16 B, `workload.c drwl_arena_after`; checked against all 8 Stage 4
records) + the first kernel's OFM region offset; require dense NHWC (pixel stride = C, row stride = W·C, the kernels'
OFM slices tile C at the matching offsets); rules A–D via `beat_model.count_at` — `evidence/stage4/beat_model.py`
sha256 `ab211e88…` (rules unchanged; `count_at` added and the script body put under `__main__`; `beat_model.json`
reproduced byte for byte). No measured value is an input; no factor; rules are not changed after the data.

| config | OFM address (alignment) | A | B | C | D | discriminates (A ∉ {B, C, D}) |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| s4_conv_base | 0x700015c0 (64 B) | 3,456 | 3,456 | 3,456 | 3,456 | no |
| s4c_conv_cout94 | 0x700015a0 (32 B) | **6,408** | 3,888 | 4,392 | 3,384 | yes |
| s4c_conv_cout97 | 0x700014b0 (16 B) | **7,272** | 4,032 | 4,572 | 3,492 | yes |
| s4_dw_base | 0x700012b0 (16 B) | 28,224 | 28,224 | 28,224 | 28,224 | no |
| s4c_dw_c142 | 0x700012a0 (32 B) | **52,528** | 30,576 | 33,320 | 27,832 | yes |
| s4c_dw_c145 | 0x70001360 (32 B) | **57,820** | 31,360 | 34,300 | 28,420 | yes |

Computed address sensitivity of rule A (not a board measurement): strides 97 and 145 give the same value for any
address mod 16; strides 94 and 142 give 6,408 / 52,528 at even and 6,840 / 56,056 at odd addresses.

## Rules (`host/analysis/stage4c1.py judge`, tests `host/tests/test_stage4c1.py`; mutation below)

Output check and RUN validity: Stage 4's (`stage4.output_check`: PASS_EXACT / PASS_TOLERANCE ≤ 1 LSB vs the CPU
reference / FAIL / INVALID; `record_v2.validity`; output CRC identical in every RUN).

| verdict (per config) | condition |
| --- | --- |
| `INVALID` | output not PASS_EXACT/PASS_TOLERANCE, a measured RUN not valid, a pass missing, or the record's region-1 base ≠ the predicted arena |
| `NOT_COMPARABLE` | fixed before the board (format/placement/operation conditions not met): none |
| `MEASUREMENT_UNSTABLE` | event 391 (EXT write beats) differs among the 4 measured pass-B RUNs |
| `PREDICTION_MATCH` | all 4 equal rule A's prediction |
| `PREDICTION_MISMATCH` | otherwise (a value equal to B, C or D is still a mismatch) |

Only configs that discriminate count as evidence for rule A against B–D. A match is stated only as "rule A's output-write
prediction held on the new channel conditions"; the internal implementation is not claimed.

Base re-confirmation: each base's NPU output sha256 and every counter constant across measured RUNs both in Stage 4 and
now must equal Stage 4's; otherwise `BASELINE_MISMATCH` — the performance pairs are not interpreted and the difference
is reported.

Pairs (base → −2 / +1): Stage 4's pair rule (`stage4.pair`, tol = max(1 % of base, either RUN range)) on pass A, the
same rule on pass B as a reproduction check; opposite signs of the NPU_ACTIVE change → `UNRESOLVED` (no averaging).
Reported beside: MACs, MAC_ACTIVE, NPU_ACTIVE, EXT read and write beats, block/ublock/kernel slices, Vela estimates.
A MAC_ACTIVE step is not generalised to a channel unit; a write-beat match is not evidence about reads or time.

## Boots — `plan.txt`: 338–343, one per config, conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

A boot failing before its RUNs: keep the data, no re-run, report. After the session: board restored to the m6 image,
postflight (PING of the restored image, card withdrawn).

## Mutation test

`evidence/stage4c1/mutate_stage4c1.py`: 12 mutations (arena rounding, MATCH against A only, unstable, address check,
validity, NOT_COMPARABLE precedence, opposite directions, baseline counters, dense check, placement check, rule A,
discrimination). First pass 11/12; the survivor (pixel-stride term of the dense check) got a fixture (a stream copy
whose pixel stride alone differs) → **12/12 RED**, restored by digest.

## Cost

6 boots × ≈ 3–4 min (DW read-back ≈ 0.45 MB each) + one deploy/restore session ≈ 5 min: ≈ 25–30 min.
