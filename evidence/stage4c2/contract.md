# Stage 4C-2 — MAC activity of the 1×1 Conv vs input channels (frozen 2026-11-11, before boot 344)

Owner directive 2026-11-11 ("Stage 4C-2 — 입력 채널 수에 따른 Conv의 MAC 처리율 분석"); plan `docs/plan/stage4c2_plan.md`.
**TA: MLEK's own sys_dram_mid set-up = TA profile 1.** FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (boot
`1b5c0adb`, bram `4f592f24`, ddr `374708ff`, images.txt `af688281`), WAIT_WFE, caches and initialisation as before,
Vela 5.0.0 with MLEK's options, INT8, graph I/O in DRAM, pass A (Stage 1 set A) + pass B (Stage 3 set B), 1 warm-up + 4
measured RUNs per config and pass: 4 × 2 × 5 = 40 RUNs (cap). Stage 4 / 4C-1 contracts, data and verdicts unchanged.
Excluded: DW kernel/stride changes, FC, spatial size, placement or TA changes, QREAD / PMU mask / IRQ, new
instrumentation, any write-rule or read model.

## Question

For the same 1×1 Conv (24×24, Cout 96, VALID, RELU6), as Cin goes 16 → 32 → 64 → 128: does MAC_ACTIVE grow in
proportion to the MACs, or does the effective MAC count per active cycle improve, and how does that relate to the
block / ublock / traversal the compiler chose? Not asked: a per-ublock time, a hardware constant, causes in the seven
models. MAC_ACTIVE and MAC_DPU_ACTIVE are activity counts, not operation counts or a MAC-circuit occupancy.

## Configurations and data (`results/fi101_stage4c2/stage4c2_compile_table.csv`)

| config | Cin | MACs = 24·24·Cin·96 (= Vela) | traversal | OFM block / IFM block / ublock | kernels (OFM slices) | OFM ublocks | IFM depth steps per kernel |
| --- | ---: | ---: | --- | --- | --- | ---: | --- |
| s4_conv_base | 16 | 884,736 | PartKernel | 6×12×96 / 6×12×16 / 2×2×32 | 2 (16 + 80) | 576 | 1 / 1 |
| s4c2_conv_cin32 | 32 | 1,769,472 | PartKernel | 6×12×96 / 6×12×16 / 2×2×32 | 2 (16 + 80) | 576 | 2 / 2 |
| s4c2_conv_cin64 | 64 | 3,538,944 | **DepthFirst** | 6×12×96 / **6×12×64** / 2×2×32 | 2 (16 + 80) | 576 | 1 / 1 |
| s4c2_conv_cin128 | 128 | 7,077,888 | **DepthFirst** | 6×12×96 / **6×12×64** / 2×2×32 | 2 (16 + 80) | 576 | 2 / 2 |

- Every kernel reads the full IFM depth (IFM_DEPTH = Cin) with ACC_INPUT_RESET: no accumulation across kernels.
- Weight order follows the traversal (part-kernel-first / depth-first).
- Weight bytes are 2,752 / 4,928 / 7,296 / 14,416 B, with weight DMA 1,024 + 3,008 / 1,280 + 4,928 / 1,664 + 6,912 / 2,944 + 12,752 B.
- Vela NPU (MAC) cycles are 16,660 (8,019) / 17,231 (14,163) / 16,709 (5,331) / 17,061 (8,787).
- One Ethos-U custom op, no CPU fallback; Gate B 4/4.
- IFM/OFM are in DRAM, NHWC, OFM stride 96; the OFM arena differs only through the model length.
- Data (`host/container/stage4c_models.py derive_cin`):
  - The base IFM and weights are extended once to 128 input channels from CIN_SEED 20261111; each config takes the first Cin.
  - Checked in the container: the first 16 channels equal the base (IFM, weights); shared channels are equal between configs; the extra weights are not all zero.
  - Bias, weight/bias scales, IFM and OFM scales are the base's. There is no recalibration, so larger Cin saturates more (|acc| max 131 k / 184 k / 283 k vs the base's): this is recorded, and the inputs are not replaced.
- Cin 16 runs the Stage 4 base DRWL (`2681c566`). The rebuilt Cin 16 model differs only in its name string and has the same command stream (`596fe964`).
- These configs change the input, weight sizes and MACs together. They are not "identical memory conditions".

**Comparison classes** (fixed now):
- 16→32 and 64→128: `SAME_SCHEDULE`, the Cin effect within one schedule.
- 32→64: `SCHEDULE_CHANGED`, a combined effect of Cin and traversal / IFM block.

## Static quantities (`host/analysis/stage4c2.py static`; no measurement is an input)

- **Per kernel:**
  - OFM ublocks = ⌈H/ub_h⌉·⌈W/ub_w⌉·⌈OFM slice/ub_c⌉ (the output area)
  - IFM depth steps = ⌈kernel IFM depth / IFM block depth⌉ (the input direction)
  - Their product, kept apart from the OFM ublocks.
- MAC_ACTIVE / ublocks normalises the whole-run count. It is not a per-ublock time.
- The 576 OFM ublocks of Cin 16 reproduce the Stage 4C-1 count; this is not counted as a new check.
- **No prediction formula is frozen.** The existing data (Cin 15/16 only) give no basis to derive a Cin dependence. A coefficient fitted from the new data would reproduce the data by construction and is not a validation.

## Rules (`host/analysis/stage4c2.py judge`; tests `host/tests/test_stage4c2.py`; mutation below)

- **Output and RUN validity:** Stage 4's (PASS_EXACT / PASS_TOLERANCE ≤ 1 LSB vs the CPU reference / FAIL / INVALID; `record_v2.validity`; output CRC identical in every RUN).
- **Config verdict:** `VALID` when the output is PASS_* and all 4 measured RUNs of both passes are valid; else `INVALID`.
- **Base reproduction:** the Cin 16 output sha256 and every counter constant across measured RUNs in both Stage 4 (boot 330) and now must equal.
  - Otherwise `BASELINE_MISMATCH`: pairs are not interpreted and the difference is reported first.
- **Pairs** 16→32, 32→64, 64→128 use Stage 4's pair rule on NPU_ACTIVE: tol = max(1 % of base, either RUN range); outcomes `UNRESOLVED` / `CONSISTENT_WITH_MAC_CHANGE` / `NOT_PROPORTIONAL_TO_MAC`.
  - Pass A is primary; pass B uses the same rule as a check. Opposite signs give `UNRESOLVED` (no averaging). An INVALID config gives `EXCLUDED`.
- **Reported per pair (descriptive):** MAC ratio, MAC_ACTIVE ratio, MAC_DPU_ACTIVE ratio, schedule class.
- **Reported per config:** MACs / MAC_ACTIVE, MAC_ACTIVE / NPU_ACTIVE, MAC_ACTIVE and MAC_DPU_ACTIVE per OFM ublock, SRAM/EXT beats, AO, WD.
- **Not done:**
  - no claim beyond the boot's 4 RUNs (no cross-boot or cross-input reproducibility)
  - DPU/MAC not read as an occupancy
  - NPU_ACTIVE − MAC_ACTIVE not assigned to memory waiting
  - kernel averages not read as a hardware constant

## Boots — `plan.txt`: 344–347, one per config, conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

- A boot failing before its RUNs: keep the data, no re-run, report.
- Board restored to m6 at the end; postflight PING of the restored image; card withdrawn.
- A needed firmware or image change is not made: it is reported.

## Mutation test

`evidence/stage4c2/mutate_stage4c2.py`: 9 mutations (ublock ceil, IFM steps, VALID rule, base output check, opposite
directions, schedule class, EXCLUDED, normalisation denominator, slices in the schedule key). First pass 6/9; the
survivors got fixtures (an output FAIL the firmware agrees with, a 2-step config's normalisation, the slice tuple) →
**9/9 RED**, restored by digest.
