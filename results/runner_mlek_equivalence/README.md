# Runner ↔ MLEK — what existing data shows (2026-11-09, POST_HOC_DESCRIPTIVE, TA profile 1)

Plan and criteria: `docs/plan/equivalence_plan.md`. Table: `existing_equivalence.csv`, made by
`python3 host/analysis/equiv_existing.py results/runner_mlek_equivalence s1=evidence/stage1/raw/s1:5
s013=evidence/fi101_s013/raw/ctl:2 s2b0b=evidence/s2_mask/raw/ctl:2 s2b3=evidence/s2b3_pilot/raw/ctl:2`.

- MLEK side: stock MLEK on FI101, B1–B3 (`docs/reference/mlek_board_reference.json`), kws, ad, mobilenet only;
  profiler counters ACTIVE and four beat counters.
- Beats (SRAM rd/wr, EXT rd/wr): equal to MLEK exactly in 3 models × 2 runner images (`2c2fa435`, `2bb04bfa`).
- NPU_ACTIVE: runner median − MLEK median −0.79 … +0.30 %; 9 of 11 comparisons inside MLEK's B1–B3 range; kws lower
  on every image (−0.5 … −0.8 %).
- Not comparable or not available: IDLE/TOTAL (different PMU windows, E4), MAC_ACTIVE and every other event (MLEK
  profiler does not count them), vww4/rnnoise/yolo/wav2letter (no MLEK counters), output equality with MLEK except
  mobilenet.
