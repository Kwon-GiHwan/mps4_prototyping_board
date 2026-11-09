# Stage 2B-3 Phase 3a pilot — results (boots 244–273, 2026-11-08 UTC board clock)

Contract: `evidence/s2b3_pilot/contract.md` (frozen `dc9b795`, before boot 244). **TA profile 1** (MLEK
sys_dram_mid) in every boot, Ethos-U85 1024 MAC, image `d0cd4775`. Raw: `evidence/s2b3_pilot/raw/` (30 boots, all
`campaign exit=0`, none re-run). Analysis: `python3 host/analysis/s2b3_windows.py evidence/s2b3_pilot/raw
results/fi101_stage2b3/timeline results/fi101_stage2b3/pilot` → `summary.json`, `windows.csv`, `patterns.csv`.

**No outcome here attributes counts to an op.** A diagnosis says where the MAC activity sits among the four windows,
compared with A's fewest MAC cycles S; it does not say that the counts in a window are A's.

## Verdicts (preregistered rules, TA profile 1)

M_k = median `mac_active` (event 48, set A, RUNs 3–10) of window W(A+k).

| model | A / B | S | M(−1) | M(0) | M(+1) | M(+2) | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ad_medium_int8 | 5 / 6 | 19,044 | 13,912 | 6,095 | 19,835 | 6,143 | **NOT_IDENTIFIABLE** (static, before data) |
| mobilenet_v2_1.0_224_INT8 | 164 / 165 | 10,584 | 1,423 | 10,584 | 10,584 | 3,333 | **WINDOW_AMBIGUOUS** |
| rnnoise_INT8 | 37 / 38 | 32 | 0 | 8 | 0 | 144 | **WINDOW_LOCALIZED(+2)** |
| yolo-fastest_192_face_v4 | 99 / 100 | 648 | 1,512 | 72 | 648 | 0 | **WINDOW_AMBIGUOUS** |

- No offset is shared. The three judged models give three different results; they are reported as they are.
- Stability: the per-RUN diagnosis equals the median diagnosis in every measured RUN of every judged model (no
  `UNSTABLE`). `mac_active` of every window arm of mobilenet, rnnoise and yolo has RUN width 0.
- ad: preconditions also hold (checked after the static verdict, same function), and its per-RUN windows are stable
  (W(A+1) 19,820–19,886). Only W(A+1) holds ≥ S, but op 7 (= A+2) is the same conv as A, so by rule the window set
  cannot separate them.

## Preconditions (all hold for all four models)

| model | ctl NPU cycles | ctl2 | ctl `npu_active` | ctl CPU inference cycles | masked arms' CPU | OFM (mismatch, max diff), every arm and RUN |
| --- | --- | --- | --- | --- | --- | --- |
| ad | 148,357 | 148,082 | 145,838 | 169,462 | 168,521–169,789 | (0, 0) = tflite_runtime golden (seed-1 IFM) |
| mobilenet | 1,450,566 | 1,451,432 | 1,448,103 | 1,796,255 | 1,796,058–1,796,994 | (0, 0) = MLEK FI101 golden (MLEK input) |
| rnnoise | 53,175 | 53,329 | 50,670 | 53,175 | 52,487–53,248 | (0, 0) = tflite_runtime golden (seed-1 IFM) |
| yolo | 449,939 | 450,828 | 447,457 | 593,667 | 593,253–594,161 | (955, 7) = ctl (MLEK golden pending) |

- Every RUN of every arm valid (model mode incl. `knobs_honoured`); A/A ctl2 = ctl on every key of every set within
  the 2B-0b tolerance; CPU inference cycles (not gated by the mask) of every masked arm = ctl's: no disturbance seen.
- rnnoise NPU cycles = CPU cycles in every unmasked RUN: already so in Stage 0 (`results/fi101_stage0/s0_3_s0_5_detail.csv`,
  ratio 0.99998) and in 2B-0b `ctl2`; not new.

## Union window and tiling (descriptive)

Σ of the four windows / u (one window over A−1 … A+2), `mac_active`: ad 0.9997, mobilenet 1.0000, rnnoise 1.0000,
yolo 1.0000. Over all non-zero events of sets A, C, D: ad 0.957–1.006 except event 54 (Reserved, 463 counts in ctl;
2.13), mobilenet 0.978–1.046, rnnoise 0.910–1.105, yolo 0.999–1.000. The four single windows partition the union
window's counts; as stated in the plan, a conserved sum is not evidence of attribution.

## Event patterns (`patterns.csv`, descriptive; Reserved events 33, 52–55, 83 listed, not interpreted)

Window holding the largest count, per non-zero event (sets A, C, D):

| model | window with most `mac_active` | other events' largest window |
| --- | --- | --- |
| ad | W(A+1) | W(A+1) 13, W(A) 2, W(A−1) 1 of 16 |
| mobilenet | W(A) = W(A+1) (tie) | W(A) 11, W(A+1) 4, W(A−1) 2, W(A+2) 1 of 18 |
| rnnoise | W(A+2) | W(A+2) 14, W(A+1) 1 of 15 |
| yolo | W(A−1) | W(A+1) 10, W(A−1) 3, W(A) 3, W(A+2) 2 of 18 |

- rnnoise: almost every event concentrates in W(A+2) with `mac_active`; `npu_active` 7,045 of 8,716 there.
- yolo: `mac_active` splits W(A−1) 1,512 / W(A+1) 648, while the write/AO-side events (`wd_active` 80, `wd_stalled` 81,
  `ao_stalled_by_bs_or_ob` 67) sit only in W(A+1). The events do not concentrate in one window together.
- mobilenet: `mac_active` and `mac_dpu_active` (51) both 10,584 in W(A) and W(A+1); `ao_active` (64) mostly W(A+1),
  `ao_stalled_by_cb` (72) only W(A), `ao_stalled_by_bs_or_ob` (67) mostly W(A+2).

## B window and zero-MAC ops (descriptive; not evidence of misattribution, per the owner)

- yolo B = Resize (0 MACs): W(B) `mac_active` 648 = exactly A's fewest cycles.
- rnnoise B = Add (0 MACs): W(B) `mac_active` 0; W(A+2) (Add, 0 MACs) 144.
- mobilenet B = DWConv, fewest 1,984.5: W(B) 10,584 = exactly A's fewest cycles.

## Wait variant (window opening moved past the last DMA_WAIT/KERNEL_WAIT in the op's setup)

- mobilenet `w_A_wait` vs `w_A`: `mac_active` 3,249 vs 10,584 → 7,335 cycles of W(A)'s MAC activity occur between the
  window opening and the end of op 164's setup waits (KERNEL_WAIT n=1, DMA_START, DMA_WAIT k=0), i.e. before op 164's
  kernel instruction is issued. `npu_active` 6,922 vs 18,516.
- rnnoise `w_B_wait` vs `w_B`: `mac_active` 0 vs 0; `npu_active` 5 vs 618.

## Static context the frozen rule did not cover (POST_HOC_DESCRIPTIVE)

The identifiability rule compares A only with A−1, A+1, A+2. Ops outside the four windows were not considered:

- mobilenet op 162 (= A−2) is a 1×1 Conv with exactly A's MACs (10,838,016; fewest 10,584), and op 164's setup holds a
  KERNEL_WAIT n=1.
- yolo op 97 (= A−2) is a 9×9 pool (139,968 MACs, fewest cycles not bounded by the peak table).
- rnnoise ops 38–40 after A are all zero-MAC Elementwise.

Whether W(A)'s or W(A−1)'s activity comes from A−2 is not tested here; the verdicts above stand as computed and the
selection is unchanged.

## What this pilot shows and does not show

- Shows: on the original command stream (TA profile 1), the mask windows are stable RUN to RUN, do not disturb the CPU
  timeline or the output, and partition the union window. Where the MAC activity of the A region sits relative to the
  windows differs by model: one window late by two (rnnoise), split between two windows of which one equals A's minimum
  exactly (mobilenet, yolo), not separable (ad).
- Does not show: which op the counts in any window belong to; a common window–op offset; any per-op exact attribution.
  The wait variant shows that in mobilenet MAC activity runs inside W(A) before op 164 is issued.

Correction 2026-11-09: the golden column first said "MLEK golden" for ad and rnnoise; their goldens are tflite_runtime OFMs on the seed-1 IFM (only mobilenet's is MLEK FI101). See the correction at the end of `evidence/s2b3_pilot/contract.md`.
