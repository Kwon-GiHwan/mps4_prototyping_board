# Stage 2B-0b — NPU_OP_PMU_MASK confirmation (all seven models) — board results

Contract `evidence/s2_mask/contract.md` (frozen `fbdeb69`, before boot 177). Image `d0cd4775`, **TA profile 1** in every
boot. Boots 177–211, 20 RUNs per boot (2 warm-up), 700/700 RUNs valid, no boot failed. Raw: `evidence/s2_mask/raw/`.
Verdict: `python3 host/analysis/s2_mask_confirm.py evidence/s2_mask/raw results/fi101_stage2_mask`.

## Preregistered outcome: **`MASK_NOT_ADDITIVE`**

| model | A/A (ctl2 vs ctl) | passthrough | additive | verdict | keys not judged (NOISY, width > 5 %) |
| --- | --- | --- | --- | --- | --- |
| kws | holds | holds | **no** | `MASK_NOT_ADDITIVE` | mac_stalled_by_w, mac_stalled_by_ib |
| ad | holds | holds | holds | `MASK_WORKS` | mac_stalled_by_w, mac_stalled_by_ib |
| rnnoise | holds | holds | **no** | `MASK_NOT_ADDITIVE` | mac_stalled_by_w, mac_stalled_by_ib, wd_active, wd_stalled |
| vww4 | holds | holds | **no** | `MASK_NOT_ADDITIVE` | — |
| yolo | holds | holds | holds | `MASK_WORKS` | mac_stalled_by_w |
| mobilenet | holds | holds | holds | `MASK_WORKS` | — |
| wav2letter | holds | holds | **no** | `MASK_NOT_ADDITIVE` | — |

Events that failed additivity (m_a + m_b − m_all; tolerance max(1 %, control width)) — `mask_confirm.csv`:

| model | event | control width | m_a + m_b − m_all |
| --- | --- | --- | --- |
| kws | wd_active | 3.02 % | −462 (−4.02 %) |
| rnnoise | npu_active | 2.92 % | −1,980 (−3.95 %) |
| rnnoise | mac_active / mac_dpu_active | 0 (fixed) | −12 / −12 (−2.2 % / −2.8 % of 548 / 428) |
| vww4 | mac_stalled_by_w | 2.92 % | −1,022 (−4.25 %) |
| wav2letter | ao_active | 0.06 % | −1,183 (−1.98 %) |

## Reading — `POST_HOC_DESCRIPTIVE`

1. **The mask does not disturb execution.** With the mask on for the whole stream every judged key, NPU cycles
   included, stays within the control's own variation in all seven models; the A/A control holds in all seven. kws's
   2B-0 failure (`results/fi101_stage2_probe/`) was its own jitter: here kws m_all vs ctl is −0.32 % on npu_active.
2. **A split loses counts, never adds them.** Every additivity failure, and every deficit in the table, is negative: some
   cycles near the split are counted by neither half. One split costs 12–1,980 cycles here (up to 4 % of an event).
   mobilenet and yolo (long streams) and ad are within tolerance; the failures sit in short streams (kws, rnnoise) or in
   a small event of a long one (wav2letter ao_active, 59,784 cycles).
3. Consequence for Stage 2B: a group gated at many boundaries will under-count by an amount that grows with the
   number of boundaries. Per the contract this outcome means "Stage 2B needs another path"; the alternatives (split
   streams, STOP+IRQ) remove the overlap between operators and so change execution. See `docs/plan/stage2_plan.md`.
