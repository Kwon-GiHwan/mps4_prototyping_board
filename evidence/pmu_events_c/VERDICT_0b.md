# Tier C step 0b — verdict (contract: docs/superpowers/specs/2026-10-07-pmu-ext-port-step0b-contract.md)

Image DRAM=1 (APP 07f77347…, VECTORS 9437774a…, DDR 81d37a21…), boot 12, 66 RUNs, one boot.

## Q1: **EXT_DRAM_REACHABLE**

66/66 runs valid on all ten terms: rc 0, valid_flags 0xF, golden window CRC 0x27084C4C on every run, seam once
per run, cycle progress. Preregistered checks: `CYCLE_EVENT_VS_PMCCNTR` **PASS**, `NPU_ACTIVE_LE_CYCLE` **PASS**.

## Q2: event verdicts

TRM `ext_*` (excluding `*_enabled_cycles`): COUNTED_NONZERO 19 — `ext_rd_trans_accepted`, `ext_rd_trans_completed`, `ext_rd_data_beat_received`, `ext_rd_tran_req_stalled`, `ext_wr_trans_accepted`, `ext_wr_data_beat_written`, `ext_enabled_cycles`, `ext0_rd_trans_accepted`, `ext0_rd_trans_completed`, `ext0_rd_data_beat_received`, `ext0_rd_tran_req_stalled`, `ext0_wr_trans_accepted`, `ext0_wr_data_beat_written`, `ext0_enabled_cycles`, `ext1_rd_trans_accepted`, `ext1_rd_trans_completed`, `ext1_rd_data_beat_received`, `ext1_rd_tran_req_stalled`, `ext1_enabled_cycles`.
COUNTED_ZERO 14 — `ext_wr_tran_req_stalled`, `ext_wr_data_beat_stalled`, `ext_rd_stall_limit`, `ext_wr_stall_limit`, `ext0_wr_tran_req_stalled`, `ext0_wr_data_beat_stalled`, `ext0_rd_stall_limit`, `ext0_wr_stall_limit`, `ext1_wr_trans_accepted`, `ext1_wr_data_beat_written`, `ext1_wr_tran_req_stalled`, `ext1_wr_data_beat_stalled`, `ext1_rd_stall_limit`, `ext1_wr_stall_limit`.
Preregistered comparison with Tier B boot 9 (per id, same/different verdict): 119 same, 52 different
(ZERO→NONZERO 21, NONZERO→ZERO 28, INCONSISTENT→ZERO 3); full list in `boot12/per_event.csv` vs
`evidence/pmu_events/boot9/per_event.csv`.

## POST_HOC_DESCRIPTIVE (no verdict depends on this)

- The traffic moved port, with the same byte totals: read beats SRAM 177 (Tier B) → EXT 177; write beats
  16 → 16; write transactions 4 → 4. Read transactions 28 → 25. Writes all on ext0 in this run.
- Every `sram_*` traffic counter is now 0 and `axi_latency_*` are 0: PMCAXI_CHAN.AXI_SEL resets to the SRAM
  port, which carries no traffic here.
- Windows are ~85k cycles (Tier B ~4–9k). Not interpreted.

Restore + postflight verified (`postflight_restore_0b.txt`).
