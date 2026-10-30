# S0-3 step 2a — does the TA state remove the CPU−NPU gap? (frozen 2026-10-31, before boot 129)

Plan: `docs/plan/s0_3_resolution_plan.md` step 2 (a). Owner decision 2026-10-31: all seven MLEK models ("전부 하자").
Background: S0-3 FAIL for 5/7 models — the NPU `PMCCNTR` span between the start seam and the CPM seam is shorter than
the CPU DWT span over the same seams by 0–31 % of the span (`results/fi101_stage0/`); across models the gap ranks
exactly with SRAM write beats (`results/fi101_s0_3_correlation/`, POST_HOC_DESCRIPTIVE).

**One variable: the TA state.** Control = TA profile 1 (MLEK `ta_config_u85_sys_dram_mid`), treatment = TA profile 2
(pass-through: no limits, no added latency, full speed; both TA_SRAM and TA_EXT). The runner reads both TAs back
every RUN (`knobs_honoured`).

## Image, blobs, PMU

- Image `2bb04bfa` (APP `2bb04bfa…6927`, VECTORS `2ad2f560…c343`, DDR `81d37a21…`), unchanged from fi101_s013.
- Treatment blob = the fi101_s013 blob of the same model with header word 27 changed 1 → 2 and nothing else
  (`make_ta_blob.py`: exactly 1 byte differs, asserted). Control blobs are the fi101_s013 blobs unchanged.

| model | profile 1 blob (fi101_s013) | profile 2 blob |
| --- | --- | --- |
| kws_micronet_m | `f11271cb6a2d…` | `a1bb6ce553ab…` |
| ad_medium_int8 | `55fa924c7e60…` | `04ce587f0234…` |
| mobilenet_v2_1.0_224_INT8 | `0d51cf9eaf86…` | `fa75889a1a32…` |
| vww4_128_128_INT8 | `b7c15f01c4be…` | `e081a373d077…` |
| rnnoise_INT8 | `5c3990a9c991…` | `cfda19734682…` |
| yolo-fastest_192_face_v4 | `1f71e47582c5…` | `f01ea30d7e4b…` |
| wav2letter_pruned_int8 | `5b8c9d06dea1…` | `e2989a34f953…` |

- PMU: sets A and B of `config/fi101_passes.txt` (`ids.txt` here), 10 RUNs per set, 2 warm-up → 16 measured RUNs per
  boot. The window quantities (`infer_npu_cycles`, `infer_cpu_cycles`) are in every RUN regardless of the set.

## Boots

| boot | model | TA profile | purpose |
| --- | --- | --- | --- |
| 129 | mobilenet_v2_1.0_224_INT8 | 1 | drift check against boot 99 |
| 130 | kws_micronet_m | 2 | treatment |
| 131 | ad_medium_int8 | 2 | treatment |
| 132 | rnnoise_INT8 | 2 | treatment |
| 133 | vww4_128_128_INT8 | 2 | treatment |
| 134 | yolo-fastest_192_face_v4 | 2 | treatment |
| 135 | mobilenet_v2_1.0_224_INT8 | 2 | treatment |
| 136 | wav2letter_pruned_int8 | 2 | treatment |

Profile 1 reference for every model = its fi101_s013 boot (94–100), all 56 measured RUNs.

## Rules (preregistered)

Per RUN: `gap = infer_cpu_cycles − infer_npu_cycles`, `frac = gap / infer_npu_cycles`, `ratio = infer_npu / infer_cpu`.
Validity: as fi101_s013 (model mode incl. `knobs_honoured`, `start_seam_once`). A boot with any invalid measured RUN
→ that model `UNPROVEN`.

1. **Drift (boot 129)**: `DRIFT_OK` if the median `frac` is within ±10 % (relative) of boot 99's median `frac` and the
   median `npu_active` lies inside boot 99's [min, max] widened by 0.5 %. Otherwise `DRIFT`, and every verdict below
   is `UNPROVEN`.
2. **Per model with profile-1 median `frac` ≥ 0.05** (kws, ad, vww4, yolo, mobilenet):
   - `TA_REMOVES_GAP`: every measured profile-2 RUN has `ratio` in [0.99, 1.01] (the S0-3 rule);
   - else `TA_REDUCES_GAP`: profile-2 median `frac` ≤ 0.5 × profile-1 median `frac`;
   - else `TA_NO_EFFECT`.
3. **Overall**: `TA_EXPLAINS` if all five are `TA_REMOVES_GAP`; `TA_NOT_EXPLAINS` if all five are `TA_NO_EFFECT`;
   otherwise `MIXED`. Any `UNPROVEN` model → overall `UNPROVEN`.
4. rnnoise, wav2letter (profile-1 `frac` < 0.05): descriptive only (S0-3 rule applied to profile 2 and reported).

Descriptive (not verdicts): per model and profile, median `npu_active`, `infer_npu`, `infer_cpu`, `gap`, SRAM/EXT
write and read beats (set B), gap per SRAM write beat.

## Limits

- Profile 2 changes TA_SRAM and TA_EXT together: a TA effect is not attributed to one port by this experiment.
- Profile 2 is not an MLEK condition; numbers from boots 130–136 are never compared with MLEK. All other s013
  conditions (Vela options, knobs, seed, image) are unchanged.
- Nothing here claims a cause beyond the TA state; the clock-gating (`CLKFORCE`) and CPU/SRAM-sharing candidates stay
  open whatever the outcome.
