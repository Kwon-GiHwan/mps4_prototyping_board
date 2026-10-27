# FI101 Stage 1 — model execution characteristics (all seven MLEK models)

**Stage 0 applied (`results/fi101_stage0/`): S0-1, S0-2, S0-4 PASS for all seven models — every row stands.**
Caveats from Stage 0: NPU cycles undercount elapsed CPU time by 0–31 % depending on the model (S0-3), so TOTAL and
ACTIVE here are NPU-counted cycles, not wall time; `npu_active` jitters ±1.5 k cycles per RUN (S0-5).

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** FI101 Ethos-U85 1024 MAC, runner
image APP `2bb04bfa` (inference-window seams), profile `config/fi101_s013.json` (= `mlek_r10` conditions), Vela
output byte-identical to MLEK's. Boots 94–100, one per model, 7 PMU sets × 10 RUNs, medians over the 8 measured RUNs
of each set (all 70/70 RUNs valid). Raw data `evidence/fi101_s013/raw/`.

## Table

| model | inference window (TOTAL) | npu_active (ACTIVE) | ACTIVE/TOTAL | MAC | DPU/MAC | AO | WD | WD stalled | peak MAC eff. | MAC active-cycle eff. | ACTIVE / Vela | block fill † | ublock fill † |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kws_micronet_m | 93,348 | 90,961 | 97.4 % | 62.1 % | 0.877 | 19.5 % | 12.4 % | 70.7 % | 16.7 % | 26.9 % | 1.05 | 0.53 | 0.72 |
| ad_medium_int8 | 148,432 | 146,033 | 98.4 % | 64.2 % | 1.000 | 28.5 % | 14.7 % | 79.8 % | 41.7 % | 65.0 % | 1.04 | 0.88 | 0.96 |
| mobilenet_v2_1.0_224_INT8 | 1,450,765 | 1,448,379 | 99.8 % | 39.7 % | 0.864 | 30.5 % | 11.7 % | 83.6 % | 20.3 % | 51.1 % | 0.83 | 0.85 | 0.95 |
| vww4_128_128_INT8 | 238,112 | 235,703 | 99.0 % | 24.0 % | 0.772 | 27.4 % | 5.6 % | 57.0 % | 7.8 % | 32.5 % | 1.06 | 0.89 | 0.92 |
| rnnoise_INT8 | 53,040 | 50,688 | 95.6 % | 1.1 % | 0.781 | 0.6 % | 4.8 % | 22.3 % | 0.2 % | 15.5 % | 1.62 | 0.24 | 0.24 |
| yolo-fastest_192_face_v4 | 450,642 | 448,204 | 99.5 % | 38.3 % | 0.749 | 46.2 % | 6.2 % | 72.1 % | 8.5 % | 22.1 % | 0.94 | 0.84 | 0.87 |
| wav2letter_pruned_int8 | 4,133,625 | 4,131,215 | 99.9 % | 85.2 % | 0.968 | 1.4 % | 27.4 % | 72.1 % | 82.5 % | 96.8 % | 0.79 | 0.87 | 0.99 |

† POST_HOC_DESCRIPTIVE, from Vela `--verbose-schedule`, MAC-weighted (`host/analysis/vela_block_fill.py`); a
compile-time quantity, not a hardware occupancy. Per operator: `vela_block_fill_per_op.csv`.

## Definitions

| column | definition |
| --- | --- |
| inference window (TOTAL) | `PMCCNTR`(CPM seam, after the NPU stopped) − `PMCCNTR`(start seam, right before the NPU starts) |
| npu_active (ACTIVE) | event 35, median over all 7 sets (anchor) |
| MAC, AO, WD, WD stalled | events 48, 64, 80, 81 ÷ event 35 of the same RUN (set A) |
| DPU/MAC | event 51 ÷ event 48 (set A). 51 = "at least one DPU active", not a utilisation |
| peak MAC eff. | N_MAC / (1024 × ACTIVE); N_MAC from the original tflite |
| MAC active-cycle eff. | N_MAC / (1024 × `mac_active`) |
| ACTIVE / Vela | ACTIVE ÷ Vela `cycles_npu` (`evidence/fi101_s013/vela/*_summary.csv`) |

The runner's own window (`PMCCNTR` from PMU arm to the CPM seam, CPU staging copies included; `runner_window` in
`stage1.csv`) is **not** a model time and is not shown in the table.

## Observations (descriptive)

- TOTAL − ACTIVE is 2,352–2,438 cycles for every model: a fixed start/stop cost of the window, independent of the
  model. ACTIVE/TOTAL therefore only drops for short models (rnnoise 95.6 %, kws 97.4 %).
- MAC active is low for rnnoise (1.1 %), vww4 (24 %), yolo (38 %), mobilenet (40 %).
- kws: MAC active 62 % but MAC active-cycle eff. 27 %, with the lowest Conv block fill (0.53) — same direction.
- vww4, yolo: block fill 0.84–0.89 yet active-cycle eff. 22–33 % — block fill does not explain them.
- DPU/MAC is 1.000 only for ad; 0.75–0.97 elsewhere — event 51 carries information beyond event 48 in real models.
- AO active exceeds MAC active for yolo (46 % vs 38 %) and vww4 (27 % vs 24 %).
- WD stalled is 57–84 % except rnnoise (22 %); WD stall alone does not separate the models (see unit stalls, Stage 3).
- ACTIVE / Vela: rnnoise 1.62 (board slower than Vela's estimate); mobilenet 0.83, wav2letter 0.79 (faster);
  others 0.94–1.06.

These are associations at model level; which operators cause them needs Stage 2 (group measurement) and Stage 4
(shape-controlled operators). Hypothesis → metric map: `docs/plan/fi101_analysis_plan_review.md`.

## Not claimed

vww4, yolo, wav2letter OFMs differ from tflite_runtime (`UNRESOLVED (x1)`, MLEK golden pending) —
their counters are used, their correctness is not claimed. Reserved-ID events are not used in this table.

## Files

| file | content |
| --- | --- |
| `stage1.csv` | all Stage 1 columns per model (`host/analysis/fi101_s013.py --stage1-only`) |
| `vela_block_fill.csv`, `vela_block_fill_per_op.csv` | block / ublock fill per model and per operator |
| `figures/` | unit activity, efficiency vs block fill, inference cycles and Vela ratio (`plot_stage1.py`) |
