# Stage 4C-1 — output-write beat prediction on new channel counts (boots 338–343, 2026-11-10 UTC board clock)

Contract `evidence/stage4c1/contract.md` (frozen `a80e28f`, before boot 338). **TA profile 1** (MLEK sys_dram_mid),
FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (the Stage 4 image; boot `1b5c0adb`, bram `4f592f24`), WAIT_WFE,
Vela 5.0.0 with MLEK's options, INT8, graph I/O in DRAM, pass A + pass B, 1 warm-up + 4 measured RUNs each = 60 RUNs.
All boots `campaign exit=0`; board restored to m6 (`RESTORE VERIFIED`), postflight: PING of the restored image
(state 1), card withdrawn. Raw: `evidence/stage4c1/raw/`, session log `evidence/stage4c1/session.log`.

```
python3 host/analysis/stage4c1.py judge evidence/stage4c1/raw evidence/stage4c1/workloads \
  results/fi101_stage4c1/predictions.json evidence/stage4/raw results/fi101_stage4c1     -> summary.json
```

## Validity

- Output: 6/6 **PASS_EXACT** against the CPU reference, output CRC identical in every RUN; 60/60 RUNs valid.
- Region-1 base (OFM arena) of every RUN = the address predicted from the artifacts (6/6).
- Bases re-confirmed: NPU output sha256 equal to Stage 4's and all constant counters equal (conv 10, DW 11 compared, 0
  differ) → `baseline_ok`.

## 1. Prediction (primary; pre-registered)

| config | C mod 16 | rule A (pre-registered) | measured EXT write beats, 4 pass-B RUNs | verdict | discriminates A from B–D |
| --- | ---: | ---: | --- | --- | --- |
| s4_conv_base | 0 | 3,456 | 3,456 ×4 | `PREDICTION_MATCH` | no (A = B = C = D) |
| s4c_conv_cout94 | 14 | 6,408 | 6,408 ×4 | `PREDICTION_MATCH` | **yes** (B 3,888, C 4,392, D 3,384) |
| s4c_conv_cout97 | 1 | 7,272 | 7,272 ×4 | `PREDICTION_MATCH` | **yes** (B 4,032, C 4,572, D 3,492) |
| s4_dw_base | 0 | 28,224 | 28,224 ×4 | `PREDICTION_MATCH` | no |
| s4c_dw_c142 | 14 | 52,528 | 52,528 ×4 | `PREDICTION_MATCH` | **yes** (B 30,576, C 33,320, D 27,832) |
| s4c_dw_c145 | 1 | 57,820 | 57,820 ×4 | `PREDICTION_MATCH` | **yes** (B 31,360, C 34,300, D 28,420) |

**Rule A's output-write prediction held on the new channel conditions** (remainders 14 and 1, Conv and DWConv, one with
a changed Vela schedule), in addition to the remainder-15 cases it was derived from. Four configs discriminate A from
B–D; the bases do not count. The internal DMA/AXI implementation is not claimed to be rule A.

## 2. Execution and transfers (secondary; Stage 4 pair rule, pass A primary, pass B check)

| pair | MACs | MAC_ACTIVE cycles | NPU_ACTIVE pass A / pass B | verdict | EXT read beats | EXT write beats | Vela schedule |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| Conv 96 → 94 | −2.1 % | 2,304 → 2,304 | +5.1 % / +7.4 % | `NOT_PROPORTIONAL_TO_MAC` | 1,437 → 1,435 | 3,456 → 6,408 | same |
| Conv 96 → 97 | +1.0 % | 2,304 → **2,016** | **+23.0 % / +24.9 %** | `NOT_PROPORTIONAL_TO_MAC` | 1,437 → 1,420 | 3,456 → 7,272 | **changed** (block 6×12×112, ublock 2×4×16, slices 16 + 81) |
| DW 144 → 142 | −1.4 % | 31,752 → 31,752 | +5.4 % / +5.7 % | `NOT_PROPORTIONAL_TO_MAC` | 31,556 → 58,675 | 28,224 → 52,528 | same |
| DW 144 → 145 | +0.7 % | 31,752 → **35,280** | **+17.3 % / +17.5 %** | `NOT_PROPORTIONAL_TO_MAC` | 31,556 → 64,477 | 28,224 → 57,820 | same |

Vela `npu_cycles` (compute estimate) changed −2.0 % (Conv 94), +0.9 % (Conv 97), 0 % (DW 142), +10.8 % (DW 145); in this
setting it did not reproduce the measured increases (`stage4c1_changes.csv`).

Both passes moved in the same direction in every pair (no `UNRESOLVED`). Four measured RUNs per pass; the tolerances
(1,047 conv, 1,598 DW) are the RUN ranges/1 % floor, so only the sign and approximate size are claimed.

Observations (`OBSERVED`, these shapes only):
- **MAC_ACTIVE** (deterministic): unchanged for −2 (Conv, DW), as for −1 in Stage 4; **rose for DW +1** (31,752 →
  35,280 = ×10/9, i.e. as if 160 instead of 144 channels) and **fell for Conv +1** (2,304 → 2,016) where Vela also chose
  a different block/ublock. A step pattern consistent with 16-channel groups for DW is seen here; it is not generalised
  to a channel unit.
- **EXT write beats** rose to rule A's values in every non-multiple-of-16 config; **EXT read beats** rose only where the
  IFM has the changed channel count (DW: 31,556 → 58,675 / 64,477); for Conv (IFM Cin 16 unchanged) reads did not rise.
  Rule A was not evaluated for reads; the read increase is reported, not explained.
- NPU_ACTIVE rose in all four pairs beyond the MAC change; the largest rises (Conv +1 +23 %, DW +1 +17 %) are where
  MAC_ACTIVE or the schedule also changed. Which part of the time comes from transfers is not measured; the write-beat
  match is not evidence of a cause of the time increase.

## 4. Closing analysis (owner, 2026-11-11: Stage 4C-1 adopted as complete; no board run, existing artifacts only)

### 4.1 Output-write prediction — conclusion

On the four new channel conditions (Conv 94, Conv 97, DW 142, DW 145; remainders 14 and 1) **rule A predicted the
output-write beats before the measurement and was right in every measured RUN**. These four are the discriminating
cases (A differs from B, C, D). The two aligned bases (Conv 96, DW 144) are a **reproducibility check** of Stage 4
(same output, same constant counters, A = B = C = D there), not evidence for A. The real DMA/AXI implementation and any
causal link from the write beats to the execution-time increase remain **unverified**.

### 4.2 DWConv MAC_ACTIVE — a separate result (by source)

| C | source | MAC_ACTIVE cycles (RUN range) | C rounded up to a multiple of 16 |
| ---: | --- | ---: | ---: |
| 142 | Stage 4C-1, boot 342 | 31,752 (0) | 144 |
| 143 | Stage 4, boot 334 | 31,752 (0) | 144 |
| 144 | Stage 4, boot 333 and Stage 4C-1, boot 341 | 31,752 (0) both | 144 |
| 145 | Stage 4C-1, boot 343 | **35,280** (0) | 160 |

35,280 / 31,752 = 10/9 = 160/144. Post-hoc description (`POST_HOC_DESCRIPTIVE`): for the DWConv shape tested (3×3,
56×56, multiplier 1) MAC_ACTIVE matches the channel count rounded up to a multiple of 16. It is not shown that this is a
universal processing unit of all operators, nor that invalid channels are actually computed. This channel boundary of
the MAC work is kept apart from the 16-byte memory-access rule A of §1 (a different quantity and mechanism).

### 4.3 Conv 96 → 97: schedule differences (artifacts: `evidence/stage4c1/conv_cout97.regs.txt` vs
`evidence/stage4/registers/conv_base.regs.txt`; Vela outputs equal the measured ones)

| item | Conv 96 (base) | Conv 97 |
| --- | --- | --- |
| OFM block / IFM block | 6×12×96 / 6×12×16 | **6×12×112** / 6×12×16 |
| OFM ublock (ACC_FORMAT microblock) | **2×2×32** (U2X2) | **2×4×16** (U2X4) |
| kernels, OFM channel slices | 2 CONV, 16 + 80 | 2 CONV, 16 + 81 |
| traversal / weight order | PartKernel / part-kernel-first | same |
| first kernel: weight streams, scales, weight DMA | 4 × 176 B, 320 B, 1,024 B | 4 × 144 B, 160 B, 736 B |
| MACs | 884,736 | 893,952 (+1.0 %) |
| MAC_ACTIVE / MAC_DPU_ACTIVE (RUN range 0) | 2,304 / 1,152 | **2,016 / 1,008** (DPU = ½ MAC in both) |
| MACs per MAC_ACTIVE cycle | 384.0 | **443.4 (+15.5 %)** |

A concrete change accounts for the decrease (`results/fi101_stage4c1/mac_active_ublocks.py` → `.csv`, all Conv and DW
configs of Stage 4 and 4C-1): counting the OFM ublocks the kernels cover (Σ ⌈H/ub_h⌉·⌈W/ub_w⌉·⌈slice/ub_c⌉),
MAC_ACTIVE / ublocks is **4.0 in every Conv config** (Cin 16, 1×1: 576 ublocks → 2,304; Conv 97: 504 → 2,016) and **9.0 in
every DW config** (3×3: 3,528 → 31,752; DW 145: 3,920 → 35,280). In the base the first kernel's 16-channel slice
occupies 32-deep ublocks (144 ublocks for 16 channels); with Conv 97's 16-deep ublock that slice takes 72 and the
81-channel slice 432, so fewer ublocks in total despite more MACs. The constants 4 and 9 are read from the data, so
this is a post-hoc description, not a prediction; why Vela chose a different ublock for 97 channels and what the NPU
does per ublock are not established.

### 4.4 Computation vs whole execution

Conv 97 raised the effective MACs per MAC-active cycle by ≈ 15.5 % (384 → 443.4) while its whole execution cost rose
by 23.0 % (pass A) / 24.9 % (pass B) in NPU_ACTIVE, with EXT write beats ×2.1 and AO_ACTIVE +17 %. An improvement in the
MAC unit's processing efficiency did not translate into a shorter run: the two must be reported separately. Which
parts of the remaining time grew is not measured.

### 4.5 Next questions (proposals only; no board run, no write-rule extension, no read model, no Stage 4D)

Centred on MAC throughput by operator and shape (the original Stage 4 aim):
1. Does MAC_ACTIVE = (cycles per ublock) × (ublocks) hold beyond the two shapes, and how does cycles-per-ublock depend
   on Cin (Conv 1×1: 4 at Cin 16 — Cin 32, 64, 128?) and on kernel size (DW 3×3: 9 — 5×5, stride 2)?
2. When does Vela choose a 2×4×16 instead of a 2×2×32 ublock (channel counts, OFM depth, operator), and how much of the
   model-level MAC-active efficiency (Stage 1) is ublock/slice padding?
3. For FC (Stage 4: 108 MAC-active cycles, 256 MACs per cycle) the same ublock description is untested.
4. MAC-active share of NPU_ACTIVE for larger Conv shapes (the AD / Wav2Letter link) — computation and whole execution
   kept as separate outcomes.

## 3. Status

- Prediction verification: **extended** — rule A predicted the output-write beats for remainders 14 and 1 (4/4
  discriminating configs), `POST_HOC` hypothesis now with a pre-registered confirmation; mechanism `UNVERIFIED`.
- Execution-time effects: observed with consistent direction in both passes; causes `UNRESOLVED`.
- Not done (proposals only): other remainders, address changes, SRAM placement, FC, Stage 4D, a read-beat rule.
