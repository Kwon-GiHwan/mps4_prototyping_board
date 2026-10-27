# FI101 Stage 0 — measurement environment and PMU checks (boots 94–100, all seven models)

**TA state: profile 1.** Image APP `2bb04bfa`; contract `evidence/fi101_s013/contract.md` (checks preregistered
before boot 94; applied after Stage 1 per amendment 1). Raw: `evidence/fi101_s013/raw/`. 490/490 RUNs valid.

## Verdicts (preregistered rules)

| model | S0-1 start seam | S0-2 window order | S0-3 NPU vs CPU clock | S0-4 image unchanged | S0-5 anchor spread ≤ 2 % |
| --- | --- | --- | --- | --- | --- |
| kws_micronet_m | PASS | PASS | FAIL | PASS | FAIL (2.89 %) |
| ad_medium_int8 | PASS | PASS | FAIL | PASS | FAIL (2.04 %) |
| mobilenet_v2_1.0_224_INT8 | PASS | PASS | FAIL | PASS | PASS |
| vww4_128_128_INT8 | PASS | PASS | FAIL | PASS | PASS |
| rnnoise_INT8 | PASS | PASS | PASS | PASS | FAIL (3.35 %) |
| yolo-fastest_192_face_v4 | PASS | PASS | FAIL | PASS | PASS |
| wav2letter_pruned_int8 | PASS | PASS | PASS | PASS | PASS |

S0-1, S0-2 and S0-4 PASS for every model: **all Stage 1 rows stand** (`results/fi101_stage1/`). The image with the
inference-window seams reproduces `mac_active` and the four beat counters of `38ce118c` exactly.

## S0-3 — the NPU cycle count is shorter than elapsed CPU time, by a model-dependent amount

| model | inference window, NPU `PMCCNTR` | same span, CPU DWT | CPU − NPU | CPU / NPU |
| --- | ---: | ---: | ---: | ---: |
| rnnoise | 53,040 | 53,039 | −1 | 1.000 |
| wav2letter | 4,133,625 | 4,146,467 | 12,863 | 1.003 |
| kws | 93,348 | 101,756 | 8,322 | 1.090 |
| vww4 | 238,112 | 269,315 | 31,125 | 1.131 |
| ad | 148,432 | 169,007 | 20,461 | 1.139 |
| mobilenet | 1,450,765 | 1,791,365 | 340,496 | 1.235 |
| yolo | 450,642 | 592,332 | 141,892 | 1.314 |

Not a fixed offset (rnnoise −1, mobilenet +340,496) and not a constant clock ratio (1.000 … 1.314); per model the
difference is stable across RUNs (e.g. mobilenet 340,023–340,763). rnnoise's exact agreement says both counters run at
the same nominal rate. Reading (hypothesis, **not tested**): during part of some inferences the NPU's `PMCCNTR` does
not advance while the CPU clock does — e.g. NPU clock gating — so **NPU cycles undercount elapsed time by 0–31 %**.
`npu_idle + npu_active = PMCCNTR` (below) holds either way, so the PMU cannot show such gaps itself.

Consequence for reporting: latency in seconds must come from the CPU-side span (`infer_cpu_cycles`, 50 MHz
nominal, not verified), not from NPU cycles; NPU-cycle ratios (MAC active / npu_active etc.) are unaffected as
ratios but describe only the counted cycles. Next check: a contract that reads `npu_idle` and `PMCCNTR` together with
DWT around the NPU run on mobilenet and yolo, and a CPU-clock check against an independent reference.

## S0-5 — anchor spread

Fails only for the short models: `npu_active` jitters by about ±1.5 k cycles per RUN, i.e. 2–3.4 % of kws, ad and
rnnoise. Per-set medians agree within 1.0 % for every model (`s0_3_s0_5_detail.csv`). The 2 % rule was preregistered
and is reported as FAIL; cross-pass ratios for these models carry this spread.

## S0-6 — event validity (50 events × 7 models)

310 `COUNTED_NONZERO`, 36 `COUNTED_ZERO`, 4 `INCONSISTENT`, no overflow (`event_validity.csv`).
- Always zero: `sram_wr_stall_limit` (143) in all 7; `sram_rd_stall_limit` (142) in 5, `ext_rd_stall_limit` (398) in 4,
  `ext_wr_stall_limit` (399) in 5 → outstanding limits are rarely or never reached under TA profile 1.
- Model-dependent zeros: `mac_stalled_by_acc` (54), `ao_stalled_by_ob` (69), `ao_stalled_by_cb` (72), write-beat
  stalls (137, 393), single-port write beats (647 ext0, 663 ext1) — zero means "did not occur here", not "unsupported".
- `INCONSISTENT`: 137 (ad), 393 (kws, rnnoise), 398 (kws) — counts of 0/1 size.

## S0-7, S0-8 — window events and clock

| model | `cycle`(17) / runner window | (`npu_idle` + ACTIVE) / runner window | `sram_enabled_cycles` / (2 × window) | host time × 50 MHz / window |
| --- | ---: | ---: | ---: | ---: |
| all seven | 1.00000–1.00019 | 1.00000–1.00020 | 1.00000–1.00022 | 1.04 (wav2letter) – 4.75 (rnnoise) |

The runner window is counted completely by `cycle`, by `npu_idle + npu_active`, and by each SRAM port's enabled
cycles. The system counter is disabled on this image (`CNTCR` = 0) → S0-8 `NOT_AVAILABLE`. Host time includes UART
frames and copies; only for wav2letter (long RUN) does it approach the 50 MHz nominal (1.04) — a coarse
consistency, not a frequency measurement.

## Files

`stage0.csv` (verdicts), `s0_3_s0_5_detail.csv`, `event_validity.csv`, `stage0_descriptive.csv`.
