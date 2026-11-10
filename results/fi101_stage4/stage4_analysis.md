# Stage 4A/4B — operator type and channel alignment (boots 330–337, 2026-11-10 UTC board clock) — closed

Contract `evidence/stage4/contract.md` (frozen `448c4c3`, before boot 330). **TA profile 1** (MLEK sys_dram_mid),
FI101 Ethos-U85 1024 MAC, official driver (driver runner), WAIT_WFE, Vela 5.0.0 with MLEK's options, INT8 isolated
operators, IFM seed 1. One boot per config; pass A (Stage 1 set A) and pass B (Stage 3 set B), 1 warm-up + 4 measured
RUNs each = 80 RUNs. All boots `campaign exit=0`; board restored to m6 (`RESTORE VERIFIED`), postflight done.
Analysis: `python3 host/analysis/stage4.py evidence/stage4/raw evidence/stage4/workloads <out>` →
`stage4_summary.csv`, `stage4_output_checks.csv`, `stage4_summary.json`. Owner (2026-11-10): 8/8 PASS_EXACT and Gate C
adopted; the experiment is closed; later revisions add the interpretation limits, the artifact cross-check (§6) and the
output-write beat hypothesis (§6.1, adopted as post-hoc) — no new board run. Stage 4C/4D: proposals only.

**Image.** All 80 RUNs (boots 330–337, both passes, every config) ran on the same image: driver runner `83398c7`
(adds `GET_OUTPUT`; RUN path unchanged), boot `1b5c0adb`, bram `4f592f24`, ddr `374708ff`, images.txt `af688281`
(recorded per RUN in `runs.csv`). No pair mixes images.

**Scope.** Standalone operators with graph I/O in DRAM (Vela placement; in the source models these layers' feature maps
were in SRAM, and mobilenet op 7 was inside a cascade). Results describe the operator under this condition. They are not
per-operator costs of the source models and are not used to reconstruct Stage 2B H1/H2 (which stay invalid).

## 1. Output check

| config | verdict | mismatches | max \|diff\| | NPU = CPU sha256 | RUNs' output CRC |
| --- | --- | ---: | ---: | --- | --- |
| all 8 | **PASS_EXACT** | 0 | 0 | yes | identical in all 10 RUNs of each config |

Every NPU output equals the tflite_runtime reference byte for byte; the firmware's own comparison (`ofm_mismatch` 0 in all
80 RUNs) agrees. Saturation counts, scales, zero points: `stage4_output_checks.csv`. Stage 1's isolated-operator
`UNRESOLVED` results are not re-judged by this. **Gate C: 8/8 PASS** (80/80 RUNs valid; PMCR 0x4001 at the arm, one arm
and one IRQ, post-inference counters = IRQ counters in every slot).

## 2. Main result — MAC_ACTIVE did not change when one channel was removed (`OBSERVED`)

| pair | MACs | MAC_ACTIVE cycles base → variant (RUN range) |
| --- | ---: | --- |
| Conv Cin 16→15 | −6.25 % | 2,304 → 2,304 (0) |
| Conv Cout 96→95 | −1.04 % | 2,304 → 2,304 (0) |
| DW C 144→143 | −0.69 % | 31,752 → 31,752 (0) |
| FC in 96→95 | −1.04 % | 108 → 108 (0) |
| FC out 288→287 | −0.35 % | 108 → 108 (0) |

In all five pairs MAC_ACTIVE was deterministic and identical to the cycle, so per-MAC MAC-active time rose by the MAC
reduction (+0.4 to +6.7 %). This shows that one channel below 16/96/144/288 is processed in the same MAC time **for these
five shapes**; it does not establish a minimum processing unit (16 channels or otherwise) for all operators or shapes.

## 3. Execution time and transfers (pair rule; tolerance = max(1 % of base, either RUN range))

| pair | NPU_ACTIVE pass A | pass B (same rule, descriptive) | pre-registered verdict (pass A) | EXT transfers | Vela schedule |
| --- | --- | --- | --- | --- | --- |
| Conv Cin 16→15 | −1.4 % | +0.03 % | `UNRESOLVED` | EXT read beats −0.6 %, SRAM read beats −52 % | changed (block 6×12×96 → 14×18×32) |
| Conv Cout 96→95 | **+7.0 %** | **+10.4 %** | `NOT_PROPORTIONAL_TO_MAC` | **EXT write beats +93 %** (3,456 → 6,660), EXT read trans +14 % | same |
| DW C 144→143 | **+6.1 %** | **+6.1 %** | `NOT_PROPORTIONAL_TO_MAC` | **EXT read beats +93 %, EXT write beats +93 %**, EXT read trans +6 % | same |
| FC in 96→95 | −0.2 % | +0.1 % | `UNRESOLVED` | EXT read trans 185 → 183 | same |
| FC out 288→287 | −9.5 % | +0.9 % (UNRESOLVED) | `NOT_PROPORTIONAL_TO_MAC` (label kept) | none beyond tolerance | same |

- **Conv Cout 95 and DW 143:** the increase of external transfer beats and the increase of NPU_ACTIVE occurred together,
  in both passes, while MAC_ACTIVE and AO_ACTIVE were unchanged (`OBSERVED`). That the beats cause the time increase is
  not shown (no time breakdown); the internal alignment/transfer mechanism is `UNVERIFIED` (§6).
- **FC out 287:** the pre-registered label stands, but the change was **not reproduced** between passes (pass A −9.5 %,
  pass B +0.9 %, inside its spread); FC RUN ranges are ≈ 7–9 % of the median. No FC alignment effect is established.
  The two passes are not averaged into one figure.
- Cin 15: no NPU_ACTIVE change within the spread although MACs fell 6.25 % and Vela changed the block.

## 4. Operator types — throughput per operator class vs the 1024-MAC basis (pass A medians)

| | Conv2D 1×1 16→96 @24×24 | DWConv 3×3 144 @56×56 | FC 96→288 |
| --- | ---: | ---: | ---: |
| MACs | 884,736 | 4,064,256 | 27,648 |
| NPU_ACTIVE (RUN range) | 21,207 (367) | 159,325 (513) | 9,416 (674) |
| MAC_ACTIVE cycles | 2,304 | 31,752 | 108 |
| MACs per MAC_ACTIVE cycle | 384 | 128 | 256 |
| documented peak for the class (TRM Table 7, U85-1024, 8-bit, as quoted in `evidence/s2b3_pilot/contract.md`) | CONV 1024 | DEPTHWISE 128 | not listed (runs as a CONV kernel) |
| MACs per MAC_ACTIVE cycle ÷ class peak | 0.375 | **1.00** | — (0.25 of the CONV figure) |
| MACs / (1024 × MAC_ACTIVE) (1024 basis) | 0.375 | 0.125 | 0.25 |
| MAC_ACTIVE / NPU_ACTIVE | 10.9 % | 19.9 % | 1.15 % |
| MAC_DPU_ACTIVE / NPU_ACTIVE | 5.4 % | 19.9 % | 1.15 % |
| AO_ACTIVE / NPU_ACTIVE | 16.7 % | 17.9 % | 0.20 % |
| WD_ACTIVE / NPU_ACTIVE | 5.0 % | 0.12 % | 8.9 % |
| WD_STALLED / NPU_ACTIVE | 33.0 % | 98.4 % | 35.5 % |
| EXT read / write beats (pass B) | 1,437 / 3,456 | 31,556 / 28,224 | 2,221 / 18 |
| SRAM read / write beats (pass B) | 2,016 / 252 | 1,212 / 202 | 0 / 0 |

- **DWConv:** during its MAC-active cycles it ran at 128 MACs per cycle — its documented class peak (ratio 1.00). Its low
  value on the 1024 basis (0.125) reflects the class peak, **not a mapping failure**; the two bases answer different
  questions and are kept apart.
- **Conv 1×1 with Cin 16:** 384 per MAC-active cycle = 0.375 of the CONV peak; why (Cin 16 vs the array's input depth,
  the 1×1 kernel) is not tested here.
- **FC:** 256 per MAC-active cycle; no documented FC figure is used, so no class-peak ratio is given.
- **Hypotheses only (no time breakdown measured):** FC's EXT reads (≈ 35.5 KB) are about its encoded weights (32 KB) —
  weight fetch may dominate its run; DWConv's EXT traffic (≈ 505 KB read, 452 KB written) is about its IFM and OFM —
  DRAM transfer may dominate its run. Low MAC activity or high WD_STALLED alone does not assign the remaining time to
  memory waiting; these stay `HYPOTHESIS`.
- Baselines differ in MACs by 150×: a technical comparison, not a controlled one.

## 5. Vela vs board — same fields, units and scope stated

| config | Vela `npu_cycles` (compute) | Vela `op_cycles` (max of compute, memory) | NPU_ACTIVE (event 35) |
| --- | ---: | ---: | ---: |
| conv_base / cin15 / cout95 | 16,660 / 10,068 / 16,497 | 24,999 / 61,523 / 24,999 | 21,207 / 20,905 / 22,684 |
| dw_base / c143 | 112,225 / 112,225 | 944,999 / 938,437 | 159,325 / 169,069 |
| fc_base / in95 / out287 | 7,929 / 7,929 / 7,909 | 7,929 / 7,929 / 7,909 | 9,416 / 9,400 / 8,519 |

Fields: Vela 5.0.0 debug database `perf.npu_cycles` and `perf.op_cycles` for the single scheduled operation, in NPU clock
cycles, Vela's model of that operation. Board: NPU_ACTIVE, NPU clock cycles counted from the PMU arm (right before the
NPU starts) to the completion IRQ, i.e. the whole job of the command stream (DMA of weights, IFM/OFM access, the kernels,
setup commands). The scopes are close (one operator per network) but not identical; ratios are not estimation errors.

Within this setting: Vela's estimates moved ≤ 1 % for Cout 95 and DW 143, so **Vela 5.0.0 did not reproduce the measured
increase (+6–10 %)** for these shapes; for Cin 15 it changed the schedule and predicted a 2.5× memory cost that the board
did not show. Vela's memory estimate for DRAM-resident maps is far above NPU_ACTIVE (DW 945 k vs 159 k).

## 6. Transfer pairs — artifact cross-check (no board run; `evidence/stage4/registers/*.regs.txt` = Vela
`--verbose-register-command-stream` of the measured Vela outputs, hashes equal)

| item | conv_base | conv_cout95 | conv_cin15 (no beat increase) | dw_base | dw_c143 |
| --- | --- | --- | --- | --- | --- |
| IFM / OFM format | NHWC, TILE2X2, int8 | same | same | same | same |
| memory | IFM, OFM: DRAM (region 1, feature-map arena); weights: DMA DRAM → SRAM staging | same | same | same | same |
| IFM stride X / Y (bytes) | 16 / 384 | 16 / 384 | **15** / 360 | 144 / 8,064 | **143** / 8,008 |
| OFM stride X / Y (bytes) | 96 / 2,304 | **95** / 2,280 | 96 / 2,304 | 144 / 8,064 | **143** / 8,008 |
| channel slices per kernel (IFM / OFM depth) | IFM 16 full; OFM 16 + 80 | IFM 16 full; **OFM 16 + 79** | **IFM 15 full**; OFM 16 + 80 | **IFM, OFM 16 + 128** | **IFM, OFM 16 + 127** |
| IFM absolute address (alignment) | 0x7000edc0 (64 B) | 0x7000eb70 (16 B) | 0x7000ed40 (64 B) | 0x7006f6b0 (16 B) | 0x7006ea60 (32 B) |
| OFM absolute address (alignment) | 0x700015c0 (64 B) | 0x700015b0 (16 B) | 0x70001540 (64 B) | 0x700012b0 (16 B) | 0x700012a0 (32 B) |
| OFM block / IFM block / ublock | 6×12×96 / 6×12×16 / 2×2×32 | same | 14×18×32 / 14×20×16 / 2×2×32 | 26×28×16 / 28×32×16 / 2×4×16 | same |
| kernels | 2 CONV | 2 CONV | 2 CONV | 2 DEPTHWISE | 2 DEPTHWISE |
| weight encoding | SWD, no sparsity; streams 176 / 512 B | SWD; last stream 496 B | SWD | SWD; 80 / 368 B | SWD; last stream 352 B |
| weight DMA (bytes) | 1,024 + 3,008 | 1,024 + 2,992 | 1,024 + 2,880 | 480 + 2,752 | 480 + 2,736 |
| EXT read / write beats | 1,437 / 3,456 | 1,436 / **6,660** | 1,429 / 3,456 | 31,556 / 28,224 | **60,775 / 54,488** |

What the cross-check shows (`OBSERVED` in the artifacts; the link to the beats is a candidate):
- Format, memory area, block/ublock, kernel kind and count, and weight encoding are the same within each pair; weight DMA
  shrinks by 16 bytes. Absolute addresses differ (16–64 B alignment) but do not line up with the beat increases:
  dw_base (16 B) has none, dw_c143 (32 B) has one.
- The beats doubled exactly where a tensor whose pixel stride is not a multiple of 16 bytes is read or written in channel
  slices narrower than its depth: Cout 95's OFM (95-byte stride, slices 16 + 79) and DW 143's IFM and OFM (143-byte
  stride, slices 16 + 127). Cin 15's IFM also has a non-16-multiple stride (15 B) but is read at full depth in each kernel,
  and its EXT reads did not rise.
- Candidate (not verified): "unaligned NHWC pixel stride combined with channel-sliced access" — the narrower original
  candidate "NHWC rows not 16-byte aligned" alone does not fit Cin 15. The beat counts have not been derived from this
  candidate quantitatively, and the DMA/AXI behaviour behind them is `UNVERIFIED`.

### 6.1 Output-write beats — quantitative candidate (POST_HOC_DESCRIPTIVE, owner request; no board run)

`evidence/stage4/beat_model.py` → `beat_model.json`. Inputs: OFM absolute address (record `base1` + the OFM offset in the
register stream), H, W, C, OFM stride X / Y from the register stream (dense NHWC: stride X = C, Y = W·C, asserted). No
factor is fitted to the measurement.

| rule (one access = …) | conv_base | conv_cout95 | dw_base | dw_c143 |
| --- | ---: | ---: | ---: | ---: |
| **A: ≤ 16-byte channel chunks per pixel** (from channel 0), each costing the 16-B segments it touches, no merging | **3,456** | **6,660** | **28,224** | **54,488** |
| B: the whole channel vector of a pixel | 3,456 | 3,960 | 28,224 | 30,968 |
| C: the kernel's channel slices per pixel (16 + 80 / 16 + 79 / 16 + 128 / 16 + 127) | 3,456 | 4,500 | 28,224 | 33,908 |
| D: the tensor as one contiguous stream (bytes / 16) | 3,456 | 3,420 | 28,224 | 28,028 |
| measured EXT write beats (event 391; identical in all 5 pass-B RUNs) | 3,456 | 6,660 | 28,224 | 54,488 |

- Rule A reproduces all four measured output-write beat counts exactly; B, C and D do not reproduce the two −1 configs.
- Rule A's access unit (≤ 16 bytes of one pixel) is smaller than the kernel's channel slices (16 + 79, 16 + 127), which
  rule C tests separately; here A's chunk boundaries fall on the slice boundary at channel 16, so the 16-channel first
  slice is one A-chunk and the second slice is split further.
- Sensitivity: for 95- and 143-byte strides rule A gives the same count for any base address mod 16 (6,660; 54,488);
  for 96- and 144-byte strides it gives the measured count only with a 16-byte-aligned base (actual bases are 16-byte
  aligned; a misaligned base would double it under the rule).
- Discriminating cases: in the aligned base configs (96, 144 channels) rules A–D all give the measured count, so only
  Cout 95 and DW 143 tell the rules apart. Both have C mod 16 = 15 (95 = 5·16 + 15, 143 = 8·16 + 15); other remainders
  were not measured, so rule A is tested on one remainder only.
- The address sensitivity above is a property of the rule computed for shifted addresses, not a board measurement with
  moved buffers.
- Status (owner, 2026-11-10: adopted as the post-hoc quantitative hypothesis for Stage 4's output-write traffic): a
  quantitative candidate that matches the **output writes** of these four configs, `POST_HOC_DESCRIPTIVE`. The internal
  access pattern, the input-read increase and any causal link to the NPU_ACTIVE increase stay `UNVERIFIED`.
  It is not evidence about the input reads (not computed here) or about the NPU_ACTIVE increase; the actual DMA/AXI
  mechanism stays `UNVERIFIED`. Cin 15 is used only as a reason why a plain "unaligned rows" explanation is insufficient
  (its schedule also changed, so it is not a clean test of rule A).

## 7. Link to the seven models (Stage 1/3 values are `REVALIDATED` ratios; legacy windows not used)

| model / phenomenon (Stage 1/3) | Stage 4 evidence | level |
| --- | --- | --- |
| RNNoise: MAC active 1.1 %, ACTIVE/Vela 1.62, EXT-read-dominated | rnnoise op 0 alone: MAC active 1.15 %, EXT reads ≈ its weights | `CONSISTENT_WITH` (low MAC activity of a small FC); weight fetch as the cause: `HYPOTHESIS`; alignment as a cause: `NOT_SUPPORTED` |
| KWS: MAC active 62 %, MAC active-cycle eff. 27 %; 1/12 aligned convs | MAC time unchanged by −1 channel in five pairs | `UNRESOLVED` (KWS shapes, SRAM-resident maps not tested) |
| YOLO: MAC 38 % < AO 46 %, eff. 22 %, DW 21.5 % of MACs | DWConv at its class peak 128 per MAC-active cycle = 1/8 of the 1024 basis | `CONSISTENT_WITH` (DW share lowers the 1024-basis efficiency); memory stalls: `UNRESOLVED` |
| VWW4: MAC 24 %, AO 27 %, 19/56 aligned | same DW evidence; beat increase seen only with channel-sliced access in DRAM | `CONSISTENT_WITH` (partly: DW 9.7 % of MACs); alignment/memory in-model: `UNRESOLVED` |
| MobileNetV2: Conv/DW mix, MAC 40 %, eff. 51 % | DW at 1/8 of the 1024 basis | `CONSISTENT_WITH` |
| AD: MAC 64 %, eff. 65 % | the small 1×1 Conv showed 10.9 % MAC activity | `UNRESOLVED` (large convs not tested) |
| Wav2Letter: MAC 85 %, eff. 97 %, all Conv | — | `UNRESOLVED` |

No cause of a model's efficiency is concluded from isolated operators.

## 8. Gates and limits

Gates: A PASS (7/7 mapped, 591 rows), B PASS 8/8, C PASS 8/8, D: MAC change, Vela schedule change, board time and
transfers reported separately per pair.

Limits: one shape per operator, one −1 step, one input, one boot per config, feature maps in DRAM only; pass B as a check
of pass A; FC RUN ranges 7–9 %; events 53/55 not used; no stall pass (C); no QREAD / PMU mask / IRQ tracing; no TA
change; Stage 1/2A/2B/3 data unchanged; Stage 4C/4D not started.
