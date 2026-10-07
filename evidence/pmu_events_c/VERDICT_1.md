# Tier C step 1 — verdict (contract: docs/superpowers/specs/2026-10-07-pmu-model-step1-contract.md)

Workload `kws_micronet_m` (ethos-u85-1024, SYS_DRAM_Low, Dedicated_Sram), blob 662fa0b2…; image MODEL=1
(APP 0af8d85f…), boot 13, 66 RUNs, one boot.

## Q1: **MODEL_RUNS_CORRECT**

66/66 valid: rc 0 on every run — the vendor's memcmp found the board OFM equal, byte for byte, to the
tflite_runtime reference on the original model. valid_flags 0xF. Both preregistered checks PASS.

## Q2: TRM-110 → NONZERO 38 / ZERO 72; driver-only Reserved-61 → NONZERO 46 / ZERO 15

Against step 0b (same path, 1×1 job): 15 ids ZERO→NONZERO, none NONZERO→ZERO. New TRM ones include
`cc_stalled_on_blockdep`, `ext_wr_tran_req_stalled`, `ext_wr_data_beat_stalled`, `ext0/ext1_*` write stalls,
`ext1_wr_*`; new Reserved: `mac_stalled_by_acc`, `ao_stalled_by_ob`, `wd_parse_stall_in_sc0/sc3`.

TRM ids still ZERO, by factual class (no attribution):
- sram2/3 (no port) (22): `sram2_rd_trans_accepted`, `sram2_rd_trans_completed`, `sram2_rd_data_beat_received`, `sram2_rd_tran_req_stalled`, `sram2_wr_trans_accepted`, `sram2_wr_data_beat_written`, `sram2_wr_tran_req_stalled`, `sram2_wr_data_beat_stalled`, `sram2_enabled_cycles`, `sram2_rd_stall_limit`, `sram2_wr_stall_limit`, `sram3_rd_trans_accepted`, `sram3_rd_trans_completed`, `sram3_rd_data_beat_received`, `sram3_rd_tran_req_stalled`, `sram3_wr_trans_accepted`, `sram3_wr_data_beat_written`, `sram3_wr_tran_req_stalled`, `sram3_wr_data_beat_stalled`, `sram3_enabled_cycles`, `sram3_rd_stall_limit`, `sram3_wr_stall_limit`
- ecc (6): `ecc_dma`, `ecc_mac_ib`, `ecc_mac_ab`, `ecc_ao_cb`, `ecc_ao_ob`, `ecc_ao_lut`
- sram port (all traffic on EXT) (30): `sram_rd_trans_accepted`, `sram_rd_trans_completed`, `sram_rd_data_beat_received`, `sram_rd_tran_req_stalled`, `sram_wr_trans_accepted`, `sram_wr_data_beat_written`, `sram_wr_tran_req_stalled`, `sram_wr_data_beat_stalled`, `sram_rd_stall_limit`, `sram_wr_stall_limit`, `sram0_rd_trans_accepted`, `sram0_rd_trans_completed`, `sram0_rd_data_beat_received`, `sram0_rd_tran_req_stalled`, `sram0_wr_trans_accepted`, `sram0_wr_data_beat_written`, `sram0_wr_tran_req_stalled`, `sram0_wr_data_beat_stalled`, `sram0_rd_stall_limit`, `sram0_wr_stall_limit`, `sram1_rd_trans_accepted`, `sram1_rd_trans_completed`, `sram1_rd_data_beat_received`, `sram1_rd_tran_req_stalled`, `sram1_wr_trans_accepted`, `sram1_wr_data_beat_written`, `sram1_wr_tran_req_stalled`, `sram1_wr_data_beat_stalled`, `sram1_rd_stall_limit`, `sram1_wr_stall_limit`
- axi_latency (PMCAXI_CHAN=SRAM) (7): `axi_latency_any`, `axi_latency_32`, `axi_latency_64`, `axi_latency_128`, `axi_latency_256`, `axi_latency_512`, `axi_latency_1024`
- ext stall_limit (6): `ext_rd_stall_limit`, `ext_wr_stall_limit`, `ext0_rd_stall_limit`, `ext0_wr_stall_limit`, `ext1_rd_stall_limit`, `ext1_wr_stall_limit`
- other (1): `no_event`

## POST_HOC_DESCRIPTIVE

Windows 3.14–3.16 M cycles. Not interpreted. Restore + postflight verified (`postflight_restore_1.txt`).
