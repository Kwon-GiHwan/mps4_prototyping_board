# FI101 Stage 0 → Stage 1 + 3 — contract (frozen 2026-10-28, before boot 94)

Plan and review: owner's FI101 analysis plan; feasibility `docs/plan/fi101_analysis_plan_review.md`.
Owner decision 2026-10-28: run Stage 0, then Stage 1 + Stage 3 (model-level); first fix the window problem —
**TOTAL, ACTIVE and inference latency are measured as different quantities.**

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Profile `config/fi101_s013.json`
(= `mlek_r10`: Vela options, knobs, seed 1, 10 RUNs with 2 warm-up; only the image and the PMU sets differ).

## Image (Stage 0 change)

APP `2bb04bfa…`, VECTORS `2ad2f560…`, DDR `81d37a21…` (`make -f Makefile.npu_runner all`, gates PASS). Differs from
`38ce118c` only in `firmware/runner/{io_wrap.c,measure.c,measure.h}`:

- **start seam**: at the vendor's "Updating POWER_CTRL" printf, after the knob writes and right before the vendor writes
  POWER_CTRL and starts the NPU, read NPU `PMCCNTR`, DWT `CYCCNT`, system counter `CNTCV[31:0]` and `CNTCR`;
- at the existing CPM seam (after the NPU stopped) additionally read DWT and `CNTCV`;
- record 109 → 117 fields (8 appended; hosts skip unknown trailing words).

Nothing is written to the NPU, the TA or the system counter. Host: `run_pmu_events.py` decodes the new words, records
host wall time per RUN, and takes explicit PMU sets; validity term `start_seam_once` for these records.

## Window definitions (preregistered)

| name | definition | meaning |
| --- | --- | --- |
| `runner_window` | `PMCCNTR` at the CPM seam (= existing `npu_pmu_window_cycles`) | PMU arm → after the NPU stopped; **includes the CPU staging copies**. Not a model time. |
| `infer_cycles` (TOTAL) | `PMCCNTR`(CPM seam) − `PMCCNTR`(start seam) | right before NPU start → after NPU stop, NPU clock; includes a few CPU register accesses on both ends. The model's inference time. |
| `active` (ACTIVE) | event 35 `npu_active` | NPU in running state. |
| `infer_cpu_cycles` | DWT(CPM seam) − DWT(start seam) | same span on the CPU clock |
| `infer_sys_ticks` | CNTCV(CPM) − CNTCV(start) | same span on the system counter (meaningful only if `CNTCR` bit 0 = 1) |
| `host_run_s` | host wall time RUN sent → RUN_COMPLETE parsed | includes copies and UART frame time; coarse clock cross-check |

Latency is reported from `infer_cycles` and `active`; `runner_window` is reported only as the runner's window.

## Boots

Staging `~/evsweep_s013` (image above + blobs below), one boot per model, `--repeats 10`, ids `config/fi101_passes.txt`
(7 sets A–G, 70 RUNs per boot), RUN wait 120 s.

| boot | model | blob (unchanged from) |
| --- | --- | --- |
| 94 | kws_micronet_m | `f11271cb…` (Stage 1 / x1 control) |
| 95 | ad_medium_int8 | `55fa924c…` (x1 control) |
| 96 | rnnoise_INT8 | `5c3990a9…` (x1 boot 85) |
| 97 | vww4_128_128_INT8 | `b7c15f01…` (x1 boot 84) |
| 98 | yolo-fastest_192_face_v4 | `1f71e475…` (x1 boot 86) |
| 99 | mobilenet_v2_1.0_224_INT8 | `0d51cf9e…` (x1 control) |
| 100 | wav2letter_pruned_int8 | `5b8c9d06…` (x1 boot 93) |

## Stage 0 checks (per model; PASS / FAIL / UNPROVEN)

| id | check | rule |
| --- | --- | --- |
| S0-1 | start seam | every RUN valid with `start_seam_once` (exactly one start seam) |
| S0-2 | window order | every RUN: `active` ≤ `infer_cycles` ≤ `runner_window` |
| S0-3 | NPU vs CPU clock | per RUN `infer_cycles / infer_cpu_cycles` within [0.99, 1.01] |
| S0-4 | image does not change NPU execution | measured RUNs: `mac_active` and the four aggregate beats (130, 135, 386, 391) equal the same blob's values on `38ce118c` (x1 boots 80–82, 84–86, 93); `active` median inside that boot's [min, max] widened by 0.5 % |
| S0-5 | anchor across passes | `active` over all measured RUNs of all 7 sets: (max − min) / median ≤ 2 % |
| S0-6 | event validity | per event per model: `COUNTED_NONZERO` / `COUNTED_ZERO` / `INCONSISTENT` over measured RUNs; any overflow bit → that event `OVERFLOW` |
| S0-7 | window events | descriptive: `cycle`(17) vs `runner_window`; `npu_idle`(32) + `active` vs `runner_window`; `*_enabled_cycles` vs 2 × `runner_window` |
| S0-8 | clock frequency | descriptive: `infer_sys_ticks` ratio if the counter runs (`CNTCR` bit 0), else `NOT_AVAILABLE`; `host_run_s` vs `runner_window` / 50 MHz |

A model with S0-1, S0-2 or S0-4 FAIL is reported `UNRESOLVED (s013)` and kept out of Stage 1/3 tables. An event that is
not `COUNTED_NONZERO` is not used in a ratio.

## Stage 1 / Stage 3 metrics (descriptive, per model, medians over measured RUNs)

Every ratio uses two events **from the same RUN** (same set); `N_MAC` from the original tflite (`workload_meta.py`).
Bytes = beats × 16 (128-bit ports). Aggregate events are summed over the 2 ports of their kind.

| stage | metric | formula |
| --- | --- | --- |
| 1 | inference cycles / latency | `infer_cycles`; µs = `infer_cycles` / f, f from S0-8 (else 50 MHz nominal, labelled) |
| 1 | active ratio in the inference window | `active / infer_cycles` |
| 1 | MAC / DPU / AO / WD active | `48 / 35`, `51 / 35`, `64 / 35`, `80 / 35` (set A) |
| 1 | WD stalled | `81 / 35` (set A) |
| 1 | MAC/cycle, peak eff., MAC active ratio, active-cycle eff. | as in `host/analysis/stage1.py` (denominator `active`) |
| 1 | Vela vs board (whole model) | Vela `cycles_npu` vs `active`; Vela SRAM/DRAM bytes vs measured bytes |
| 3 | traffic | SRAM/EXT RD/WR bytes (set B), per-port bytes (sets F, G) |
| 3 | memory intensity | total bytes / N_MAC |
| 3 | effective bandwidth | bytes / `active`, per port kind and per port |
| 3 | average burst | RD beats / RD trans accepted (set B; SRAM, EXT) |
| 3 | request stall ratio | `131 / (2 × 35)`, `387 / (2 × 35)`, `137 / (2 × 35)`, `393 / (2 × 35)` (set C) |
| 3 | outstanding pressure | `142, 143, 398 / (2 × 35)` (set C), `399` (set E) |
| 3 | port imbalance | (max − min) / sum over SRAM0/1 and over EXT0/1 bytes (sets F, G) |
| 2-pre | unit stalls (model level) | `53, 55, 52, 54 / 35`; AO `67, 69, 70, 72 / 35`; WD `83 / 35`; `33 / 35` (sets A, D, E) |

Reserved-ID events (33, 52–55, 67–72, 83) are reported with "meaning inferred from driver status bits"
(`evidence/stage2a/event_semantics_audit.md`). Latency thresholds and per-channel traffic need a `PMCAXI_CHAN` blob per
channel and are **not** in this campaign.

## Not claimed

No group-level cost (Stage 2), no latency distribution, no statement on the physical DRAM (the memory system is
the TA-emulated SYS_DRAM_Mid). vww4, yolo-fastest, wav2letter OFMs differ from tflite_runtime (`UNRESOLVED (x1)`);
their counters are used, their correctness is not claimed.

## Amendment 1 (2026-10-28, owner decision, during boots 94–100, before any Stage 1 table)

Order changed: **Stage 1 is analysed and reported first; Stage 0 checks are applied afterwards** and decide which
Stage 1 rows stand. Until then every Stage 1 row carries the label `PROVISIONAL (Stage 0 pending)`. Stage 3 data are
collected in the same boots and analysed later. Boots, image, sets and every formula above are unchanged.

## Amendment 2 (2026-10-28, owner decision "do what can run alongside Stage 1", frozen before boot 101)

Two additions for the follow-up table (MAC low / WD stall / AO vs MAC / Vela), Stage 1 conditions unchanged.

1. **Vela detail, no board**: the seven models recompiled with the profile's options plus `--verbose-schedule
   --verbose-performance --verbose-weights`; every `_vela.tflite` hash equals the measured blob's Vela output.
   Stored in `vela/verbose/` (per-operator OFM block, ublock, cascade, estimated cycles and MACs).
2. **Per-channel traffic, boots 101–116** on the same image (`2bb04bfa`), TA profile 1: the measured blobs of
   rnnoise, kws, vww4 and yolo-fastest with **only header word 16** (`PMCAXI_CHAN`) set to `BW_CH_SEL_EN | CH_SEL`
   (`make_chan_blob.py`; 4 bytes differ from the measured blob), one boot per (model, channel):
   `rd_weights` 0x402, `rd_ifm` 0x401, `wr_ofm` 0x408, `rd_mem2mem` 0x404. One PMU set = Pass B
   (`35 128 130 132 135 384 386 391`), 10 RUNs. Wav2letter and mobilenet are left out (upload 33 / 9 min per boot).

   | boot | model | channel | boot | model | channel |
   | --- | --- | --- | --- | --- | --- |
   | 101 | rnnoise | rd_weights | 109 | vww4 | rd_weights |
   | 102 | rnnoise | rd_ifm | 110 | vww4 | rd_ifm |
   | 103 | rnnoise | wr_ofm | 111 | vww4 | wr_ofm |
   | 104 | rnnoise | rd_mem2mem | 112 | vww4 | rd_mem2mem |
   | 105 | kws | rd_weights | 113 | yolo | rd_weights |
   | 106 | kws | rd_ifm | 114 | yolo | rd_ifm |
   | 107 | kws | wr_ofm | 115 | yolo | wr_ofm |
   | 108 | kws | rd_mem2mem | 116 | yolo | rd_mem2mem |

   Rules: a RUN is valid as in the main contract including `knobs_honoured` (the runner reads `PMCAXI_CHAN` back).
   `CHANNEL_FILTER_WORKS` per model needs every channel's beats ≤ the unfiltered Pass B beats of boots 94–98 for the
   same event, at least one channel below it, and `npu_active` and `mac_active` unaffected (S0-4 rule against
   the same model's boot 94–98). Otherwise `CHANNEL_FILTER_UNPROVEN`, and no per-channel number is reported.
   Per-channel shares (channel beats / unfiltered beats) are descriptive.

## Amendment 3 (2026-10-28, owner decision, before boot 101)

Amendment 2 left mobilenet and wav2letter out of the per-channel boots for upload time without the owner's
decision; that exclusion is withdrawn. **All seven models**: boots 117–120 mobilenet and 121–124 wav2letter, same
channels, same blob rule (word 16 only), same set and rules. Owner condition: each model's per-channel result is
added to the results as soon as its boots finish.

## Stage 0 results (recorded 2026-10-28, after boots 94–100) — `results/fi101_stage0/`

- S0-1, S0-2, S0-4 **PASS** for all seven models → every Stage 1 row stands; the PROVISIONAL label is lifted.
- S0-3 **FAIL** for 5 of 7 (PASS rnnoise, wav2letter): CPU DWT span exceeds NPU `PMCCNTR` span over the same seams by a
  model-dependent, RUN-stable amount (0 … +31 %; mobilenet +340,496 cycles). Not an offset, not a clock ratio.
  Hypothesis (untested): NPU-side counting pauses (e.g. clock gating). Latency in seconds is taken from the CPU span.
- S0-5 **FAIL** for kws, ad, rnnoise (anchor spread 2.0–3.4 %, per-set medians within 1.0 %): ±1.5 k cycles RUN jitter.
- S0-6: 310 COUNTED_NONZERO / 36 COUNTED_ZERO / 4 INCONSISTENT, no overflow. S0-7: window events consistent
  (≤ 0.02 %). S0-8: system counter disabled → NOT_AVAILABLE; host time only a coarse check.

## Amendment 4 (2026-10-28, before boot 125) — ad_medium_int8 per-channel boots

Amendment 3 claimed "all seven models" for the per-channel boots but added only mobilenet and wav2letter;
ad_medium_int8 was never in `plan_chan.txt`, so boots 101–124 covered six models. Found after boot 124 while
summarising. Under the owner's "all seven" decision: boots 125–128 = ad_medium_int8 × (rd_weights, rd_ifm, wr_ofm,
rd_mem2mem), same image `2bb04bfa` (re-deployed), same blob rule (word 16 only), same set and rules, TA profile 1.
