# FI101 Stage 2A — pipeline activity and stalls, model level (all seven MLEK models)

**TA profile 1 (MLEK sys_dram_mid).** No new board data: fi101_s013 boots 94–100, image `2bb04bfa`, PMU sets A, D, E,
8 measured RUNs per set (`evidence/fi101_s013/`). Every ratio pairs two events of the same RUN (`npu_active` is in every
set); formulas preregistered in `evidence/fi101_s013/contract.md` (stage 1 and "2-pre"). An event that is not
`COUNTED_NONZERO` gives its verdict, not a number. Values equal `results/fi101_stage1/stage1.csv` and
`results/fi101_stage3/unit_stalls.csv` exactly (cross-checked, 0 differences); this page puts them in the Stage 2A
order and adds the checks and Stage 2B candidates below (`POST_HOC_DESCRIPTIVE`). Reproduce:
`python3 results/fi101_stage2a/stage2a_models.py`.

Clock: all cycles are NPU cycles, i.e. the emulated SYS_DRAM_Mid system (S0-3 resolved, `results/fi101_s0_3_clk/`):
FPGA-memory waits beyond the emulated latency are hidden by TA clock stops and appear in no event here.

## Indicators (÷ `npu_active` unless stated)

TRM-documented: `mac_active`, `mac_dpu_active`, `ao_active`, `wd_active`, `wd_stalled`. All others are Reserved IDs,
meaning inferred from driver status bits (`evidence/stage2a/event_semantics_audit.md`) — exploratory.

| model | MAC active | DPU / MAC | AO active | WD active | WD stalled | MAC st. IB | MAC st. W or ACC | MAC st. W | MAC st. ACC | AO st. BS or OB | AO st. OB | AO st. AB or CB | AO st. CB | WD st. WD_BUF | CC st. blockdep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws | 0.621 | 0.877 | 0.195 | 0.124 | 0.707 | 0.098 | 0.137 | 0.121 | 0.013 | 0.438 | zero | 0.413 | zero | 0.543 | 0.260 |
| ad | 0.642 | 1.000 | 0.285 | 0.147 | 0.798 | 0.147 | 0.147 | 0.142 | 0.005 | 0.277 | zero | 0.560 | zero | 0.612 | 0.124 |
| rnnoise | 0.011 | 0.781 | 0.006 | 0.048 | 0.223 | 0.065 | 0.227 | 0.228 | zero | 0.555 | zero | 0.411 | 0.133 | 0.004 | 0.408 |
| vww4 | 0.240 | 0.772 | 0.274 | 0.056 | 0.570 | 0.276 | 0.102 | 0.103 | zero | 0.477 | 0.018 | 0.313 | 0.046 | 0.433 | **0.518** |
| yolo | 0.383 | 0.749 | **0.462** | 0.062 | 0.721 | **0.338** | 0.066 | 0.066 | 0.001 | 0.227 | 0.000 | 0.373 | 0.118 | 0.625 | 0.348 |
| mobilenet | 0.397 | 0.864 | 0.305 | 0.117 | 0.836 | **0.333** | 0.216 | 0.145 | 0.071 | 0.210 | 0.004 | 0.400 | 0.091 | 0.649 | 0.125 |
| wav2letter | 0.852 | 0.968 | 0.014 | 0.274 | 0.721 | 0.010 | 0.134 | 0.134 | zero | 0.032 | 0.001 | 0.116 | 0.001 | 0.552 | 0.002 |

`zero` = `COUNTED_ZERO` (0 in all 8 RUNs). Stalls overlap and are never summed into a total stall time.
From Stage 1 (same boots): active-cycle MAC efficiency kws 0.27, ad 0.65, rnnoise 0.15, vww4 0.33, yolo 0.22,
mobilenet 0.51, wav2letter 0.97; Vela MAC-weighted block fill kws 0.53, ad 0.88, rnnoise 0.24, vww4 0.89, yolo 0.84,
mobilenet 0.85, wav2letter 0.87.

## Consistency of the inferred meanings (`consistency.csv`)

All seven models pass every check: `mac_active + mac_stalled_by_ib ≤ npu_active` in 8/8 RUNs (same RUN, set A);
`mac_dpu_active ≤ mac_active`; `max(by_w, by_acc) ≤ by_w_or_acc ≤ by_w + by_acc`; `ao_stalled_by_ob ≤ by_bs_or_ob`;
`ao_stalled_by_cb ≤ by_ab_or_cb`; `wd_stalled_by_wd_buf ≤ wd_stalled` (cross-set checks on medians, tolerance 0.005 —
rnnoise's `w_or_acc` 0.227 vs `by_w` 0.228 passes only within it). The "or" events behave as unions of their parts.
`dpu_over_mac` is 0.75–1.00, not 1.000 as on the single-operator Stage 2A (2026-10): it carries information on models.

## RUN-to-RUN stability (`run_spread.csv`, step 2A-F1)

Per indicator and model, the range over the 8 measured RUNs. Median relative range (max − min) / median: **1.5 %**
(97 numeric cells). Wide only where the ratio is tiny (`mac_stalled_by_acc` kws 0.010–0.019, ad 0.001–0.005) and on
rnnoise (stalls ±10 %, a 50k-cycle model). The model separations used below hold RUN by RUN: MAC stalled by IB
0.271–0.342 (vww4, mobilenet, yolo) vs ≤ 0.155 (ad, kws, rnnoise, wav2letter); blockdep vww4 0.517–0.520 > rnnoise
0.385–0.428 > yolo 0.346–0.348 > kws 0.247–0.267 > mobilenet, ad ≈ 0.125 > wav2letter 0.002. yolo vs mobilenet on IB
(0.336–0.342 vs 0.333–0.334) do not overlap but differ by ~1 %: not a meaningful ranking.

## Reading — POST_HOC_DESCRIPTIVE

1. **A stall ratio is the unit's held non-active time, not a slowdown of its active work.** *(Corrected 2026-11-03.
   The first version read "stalls counted while the unit is idle" as "not a bottleneck". PMCLUT (2A-F2,
   `results/fi101_stage2_probe/`) shows stall and active cycles of a unit never coincide in any model, so this is
   what a stall event measures: of the cycles a unit is not working, how many it was held for that reason.)*
   rnnoise AO is held by BS/OB or AB/CB in 41–56 % of the inference while active 0.6 %; wav2letter's WD is held 72 %
   (WD_BUF 55 %) while active 27 % — in the model whose MAC runs at 97 % efficiency. A held unit is a bottleneck only
   if the MAC waits on it: `wd_stalled` is 0.57–0.84 in every Conv model regardless of efficiency, so a held WD does
   not by itself separate efficient from inefficient models.
2. **MAC input-buffer stall separates models:** 0.28–0.34 for mobilenet, yolo, vww4 (depthwise conv 25–34 % of Vela
   cycles), 0.10–0.15 for kws, ad, ≤ 0.07 for rnnoise and wav2letter.
3. **Block dependency** (`cc_stalled_on_blockdep`, meaning undocumented) is highest for vww4 (0.52), rnnoise (0.41),
   yolo (0.35), kws (0.26); ≈ 0 for wav2letter.
4. **Weight vs accumulator:** MAC stalls on the W-or-ACC path are almost all weight (`by_acc` ≤ 0.013 except mobilenet
   0.071).

## The plan's per-model focus, checked against the data

| model | plan's Stage 1 observation | data | Stage 2A reading |
| --- | --- | --- | --- |
| RNNoise | very low MAC activity | MAC 0.011, eff 0.15, block fill 0.24, Vela under-predicts 1.62× | blockdep 0.41 and AO stalls with AO almost idle: the NPU waits between small dependent blocks; AO stalls are not AO work |
| KWS | high MAC activity, low efficiency | MAC 0.62, eff 0.27 | stalls are moderate (IB 0.10, W 0.12); the low **block fill 0.53** is the stronger candidate for the efficiency loss |
| VWW4 | low MAC, high internal stalls | MAC 0.24, IB 0.28, blockdep 0.52, AO BS/OB 0.48 | confirmed; highest blockdep of all models |
| YOLO | high block fill, low efficiency | fill 0.84, eff 0.22 | highest IB stall (0.34) and AO active (0.46) |
| MobileNetV2 | high input-buffer stall | IB 0.33 | confirmed; also the only non-negligible ACC stall (0.071) |
| AD MedNet | high MAC and high WD stall | MAC 0.64, WD stalled 0.80 | coexist; wav2letter shows the same WD stall at 97 % efficiency → WD stall is not what limits AD |
| Wav2Letter | high MAC and efficiency | MAC 0.85, eff 0.97 | reference: IB, AO, blockdep stalls ≈ 0; WD stalled still 0.72 |

## Stage 2B candidates (group level; measurement path still to be developed)

| candidate group | models | question |
| --- | --- | --- |
| depthwise conv | mobilenet, yolo, vww4 (ad, kws for contrast) | does the MAC input-buffer stall sit in the depthwise layers? |
| small / dependent blocks (FC, MemoryCopy, small convs) | rnnoise, vww4, yolo | where does `cc_stalled_on_blockdep` accumulate? |
| low-block-fill convs | kws | is the efficiency loss in layers with low block fill rather than stalls? |
| conv reference | wav2letter | baseline per-group efficiency |

Group-level values need a path the runner does not have yet (`docs/plan/fi101_analysis_plan_review.md`, Stage 2:
split command stream, STOP+IRQ at boundaries, or `NPU_OP_PMU_MASK` — the last untested on the board).

## Not claimed

No group-level cost, no cause of any stall (Reserved IDs, inferred meanings), no correctness for vww4, yolo,
wav2letter OFMs (MLEK goldens pending). Not comparable with numbers taken under another TA state.
