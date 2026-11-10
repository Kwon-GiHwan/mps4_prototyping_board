# Stage 4A/4B — operator type and channel alignment (boots 330–337, 2026-11-10 UTC board clock)

Contract `evidence/stage4/contract.md` (frozen `448c4c3`, before boot 330). **TA profile 1** (MLEK sys_dram_mid),
FI101 Ethos-U85 1024 MAC, official driver (driver runner `83398c7`, boot `1b5c0adb`, bram `4f592f24`), WAIT_WFE,
Vela 5.0.0 with MLEK's options, INT8 isolated operators, IFM seed 1. One boot per config; pass A (Stage 1 set A) and
pass B (Stage 3 set B), 1 warm-up + 4 measured RUNs each = 80 RUNs. All boots `campaign exit=0`; board restored to m6
(`RESTORE VERIFIED`), postflight done. Analysis: `python3 host/analysis/stage4.py evidence/stage4/raw
evidence/stage4/workloads <out>` → `stage4_summary.csv`, `stage4_output_checks.csv`, `stage4_summary.json`.

**Scope.** Standalone operators with graph I/O in DRAM (Vela placement; in the source models these layers' feature maps
were in SRAM, and mobilenet op 7 was inside a cascade). Results describe the operator under this condition; they are
not per-layer times of the source models.

## 1. Output check (first, as the owner asked)

| config | verdict | mismatches | max \|diff\| | NPU = CPU sha256 | RUNs' output CRC |
| --- | --- | ---: | ---: | --- | --- |
| all 8 | **PASS_EXACT** | 0 | 0 | yes | identical in all 10 RUNs of each config |

The tolerance was never needed: every NPU output equals the tflite_runtime reference byte for byte, and the firmware's
own comparison (`ofm_mismatch` 0 in all 80 RUNs) agrees with the host's. Saturation counts, scales and zero points:
`stage4_output_checks.csv`. (Stage 1's isolated conv3x3 / pw1x1 / fc1024 differed by ≤ 1 LSB from tflite_runtime on the
legacy runner; those stay `UNRESOLVED` as recorded — this result does not re-judge them.)

**Gate C: 8/8 PASS** (output PASS_EXACT, 80/80 RUNs valid, both passes with 4 measured RUNs). Counters: PMCR 0x4001
at the arm in every RUN, one arm and one IRQ, the post-inference read equals the IRQ read in every slot (counters
stopped with the NPU).

## 2. RQ4-1 — operator type (medians of 4 measured RUNs, pass A; ratios ÷ NPU_ACTIVE of the same RUN)

| | Conv2D 1×1 16→96 @24×24 | DWConv 3×3 144 @56×56 | FC 96→288 |
| --- | ---: | ---: | ---: |
| MACs | 884,736 | 4,064,256 | 27,648 |
| NPU_ACTIVE (RUN range) | 21,207 (367) | 159,325 (513) | 9,416 (674) |
| MAC_ACTIVE cycles (range) | 2,304 (0) | 31,752 (0) | 108 (0) |
| MACs / MAC_ACTIVE cycle | 384 | 128 | 256 |
| MAC_ACTIVE / NPU_ACTIVE | 10.9 % | 19.9 % | 1.15 % |
| MAC_DPU_ACTIVE / NPU_ACTIVE | 5.4 % | 19.9 % | 1.15 % |
| AO_ACTIVE / NPU_ACTIVE | 16.7 % | 17.9 % | 0.20 % |
| WD_ACTIVE / NPU_ACTIVE | 5.0 % | 0.12 % | 8.9 % |
| WD_STALLED / NPU_ACTIVE | 33.0 % | 98.4 % | 35.5 % |
| MACs / NPU_ACTIVE | 41.7 | 25.5 | 2.9 |
| MACs / (1024 × MAC_ACTIVE) | 0.375 | 0.125 | 0.25 |
| EXT read / write beats (pass B) | 1,437 / 3,456 | 31,556 / 28,224 | 2,221 / 18 |
| SRAM read / write beats (pass B) | 2,016 / 252 | 1,212 / 202 | 0 / 0 |

`OBSERVED` (this condition):
- MAC_ACTIVE is fully deterministic (range 0) and the MAC rate per active cycle is a fixed fraction of 1024: DWConv
  128 (= the TRM's depthwise peak for U85-1024, 8-bit), FC 256, this 1×1 Conv with Cin 16 384. The last metric is a
  MAC-count efficiency, not a measured lane occupancy.
- The MAC array is active for a small share of NPU_ACTIVE in every operator (1–20 %). DWConv's DRAM traffic
  (≈ 505 KB read, 452 KB written ≈ its IFM and OFM) dominates its run; its weight decoder is stalled 98 % of the time.
- FC moves almost only weights (EXT read ≈ 35.5 KB ≈ its 32 KB of encoded weights), no SRAM traffic, MAC active 1.15 %.
- Baselines differ in MACs by 150×: this is a technical comparison of three operators, not a controlled one.

## 3. RQ4-2 — channel alignment (pair rule; tolerance = max(1 % of base, either RUN range))

| pair | MACs | NPU_ACTIVE A (B) | verdict (pass A) | same rule on pass B (descriptive) | MAC_ACTIVE cycles | Vela schedule | traffic beyond tolerance |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| Conv Cin 16→15 | −6.25 % | −1.4 % (+0.03 %) | `UNRESOLVED` | UNRESOLVED | 2,304 = 2,304 | **changed** (block 6×12×96 → 14×18×32) | SRAM read beats −52 %, SRAM rd trans −50 %, EXT rd trans +10 % |
| Conv Cout 96→95 | −1.04 % | **+7.0 % (+10.4 %)** | `NOT_PROPORTIONAL_TO_MAC` | NOT_PROPORTIONAL | 2,304 = 2,304 | same | **EXT write beats +93 %** (3,456 → 6,660), EXT rd trans +14 % |
| DW C 144→143 | −0.69 % | **+6.1 % (+6.1 %)** | `NOT_PROPORTIONAL_TO_MAC` | NOT_PROPORTIONAL | 31,752 = 31,752 | same | **EXT read beats +93 %, EXT write beats +93 %**, EXT rd trans +6 % |
| FC in 96→95 | −1.04 % | −0.2 % (+0.1 %) | `UNRESOLVED` | UNRESOLVED | 108 = 108 | same | EXT rd trans 185 → 183 (deterministic) |
| FC out 288→287 | −0.35 % | −9.5 % (+0.9 %) | `NOT_PROPORTIONAL_TO_MAC` | **UNRESOLVED** | 108 = 108 | same | none |

- **Removing one channel never reduced MAC work** (`OBSERVED`): MAC_ACTIVE cycles are identical, to the cycle, in every
  pair. The MAC array processes these channel counts at a granularity of at least 16, so a −1 config costs the same
  MAC time for fewer MACs (cycles per MAC +0.7 to +6.7 % from MACs alone).
- **Where NPU_ACTIVE rose (Conv Cout 95, DW 143), DRAM beats nearly doubled while transactions rose 6–14 %**
  (`OBSERVED`); MAC and AO activity were unchanged. The rows of a 95- or 143-channel NHWC tensor in DRAM are not
  16-byte aligned, and the measured beat count is about twice the aligned one — `CONSISTENT_WITH` unaligned NHWC rows
  being transferred in more, partly filled beats. The mechanism inside the NPU/DMA is `UNVERIFIED`.
- **Cin 15:** no NPU_ACTIVE change within the spread, although MACs fell 6.25 % (so per-MAC cost rose) and Vela chose a
  different block with half the SRAM reads.
- **FC out 287:** the pass-A verdict stands by rule, but it is not reproduced in pass B and FC's RUN range is ≈ 7–9 %
  of its median; it is reported as **not robust**. FC alignment effects are not established.

Simple MAC-count changes explain none of the resolved differences; the resolved ones co-occur with memory-traffic
changes, not with Vela schedule changes (the one schedule change, Cin 15, shows no resolved time change).

## 4. RQ4-3 — Vela vs board

| config | Vela NPU (compute) | Vela op (max of compute, memory) | NPU_ACTIVE | NPU_ACTIVE / Vela op |
| --- | ---: | ---: | ---: | ---: |
| conv_base | 16,660 | 24,999 | 21,207 | 0.85 |
| conv_cin15 | 10,068 | 61,523 | 20,905 | 0.34 |
| conv_cout95 | 16,497 | 24,999 | 22,684 | 0.91 |
| dw_base | 112,225 | 944,999 | 159,325 | 0.17 |
| dw_c143 | 112,225 | 938,437 | 169,069 | 0.18 |
| fc_base | 7,929 | 7,929 | 9,416 | 1.19 |
| fc_in95 | 7,929 | 7,929 | 9,400 | 1.19 |
| fc_out287 | 7,909 | 7,909 | 8,519 | 1.08 |

Scope first: NPU_ACTIVE covers the whole job of the command stream (setup commands, weight / IFM / OFM DMA, the kernel
and the driver's run), Vela's numbers are its per-operator model; with one operator per network the scopes are close but
not identical, so the ratios are not estimation errors.
- Vela's **memory** estimate for DRAM-resident feature maps is far above the board (DW: 945 k vs 159 k), so its op
  estimate does not track these runs; NPU_ACTIVE is 1.08–1.51× its **compute** estimate, except Cin 15 (2.08×, the
  config whose compute estimate Vela lowered with the new block).
- Vela changed the schedule only for Cin 15 and predicted a 2.5× memory cost there; the board showed neither a time
  change nor more EXT reads. For Cout 95 and DW 143 Vela's estimates moved ≤ 1 % while the board moved +6–10 % with
  doubled DRAM beats: **Vela's estimate did not reflect the alignment cost that the board showed** (`OBSERVED` for these
  shapes, Vela 5.0.0).

## 5. Link to the seven models (Stage 1/3 values are `REVALIDATED` ratios; legacy windows not used)

| model / phenomenon (Stage 1/3) | Stage 4 evidence | level |
| --- | --- | --- |
| RNNoise: MAC active 1.1 %, ACTIVE/Vela 1.62, EXT-read-dominated | rnnoise op 0 alone: MAC active 1.15 %, EXT read ≈ weights, NPU_ACTIVE/Vela 1.19 | `CONSISTENT_WITH` (FC on the NPU is weight-fetch-bound); alignment as a cause: `NOT_SUPPORTED` (FC pairs unresolved / not robust) |
| KWS: MAC active 62 % but MAC active-cycle eff. 27 %; 1/12 aligned convs | MAC time is quantized by channel granularity (−1 channel = same MAC cycles) | `UNRESOLVED` (KWS shapes and SRAM-resident maps not tested) |
| YOLO: MAC 38 % < AO 46 %, active-cycle eff. 22 %, DW 21.5 % of MACs | DWConv runs at 128 MACs per active cycle (1/8 of the array) with AO ≈ MAC activity | `CONSISTENT_WITH` (DW share lowers the model's MAC-cycle efficiency); memory stalls: `UNRESOLVED` (stall pass not measured) |
| VWW4: MAC 24 %, AO 27 %, 19/56 aligned | same DW evidence; misaligned NHWC rows doubled DRAM beats here | `CONSISTENT_WITH` (partly: DW 9.7 % of MACs); alignment/memory in-model: `UNRESOLVED` (its maps are in SRAM) |
| MobileNetV2: Conv/DW mix, MAC 40 %, eff. 51 % | DW at 1/8 rate vs Conv at higher rates | `CONSISTENT_WITH` (DW's 6.9 % of MACs take disproportionate MAC time) |
| AD: MAC 64 %, eff. 65 % | the isolated 1×1 Conv (small Cin) showed only 10.9 % MAC activity | `UNRESOLVED` (large convs not tested; Stage 4C) |
| Wav2Letter: MAC 85 %, eff. 97 %, all Conv | — | `UNRESOLVED` (shape scaling not tested) |

None of these establishes the cause of a model's efficiency; isolated operators with DRAM-resident I/O differ from the
models' execution.

## 6. Gates

| gate | result |
| --- | --- |
| A — inventory | PASS: 7/7 models mapped (591 rows), TFLite op ↔ NPU kernel kept apart, no CPU fallback |
| B — compilation | PASS 8/8 (`stage4_compiler_report.md`) |
| C — measurement | PASS 8/8 (output PASS_EXACT, 80/80 RUNs valid) |
| D — interpretation | MAC change, Vela schedule change and board time change reported separately per pair (§3, §4) |

## 7. Limits

- One shape per operator, one −1 step, one input, one boot per config; feature maps in DRAM only.
- The pair rule uses pass A; pass B is reported as a check. FC runs (~9 k cycles) have RUN ranges of 7–9 %.
- The beat-doubling mechanism and why Cin 15 does not show it are not explained; event 53/55 not used.
- No QREAD, PMU mask or IRQ tracing; no TA change; Stage 1/2A/2B/3 data unchanged.
