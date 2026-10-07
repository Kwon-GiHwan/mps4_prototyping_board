# Tier C step 3 — verdict (contract: docs/superpowers/specs/2026-10-07-pmu-model-step3-contract.md)

Image MODEL=1 APP 0f215ef5…; one deploy, boots 19 (3a) and 20 (3b), `--validity model --keep-model`.

## 3a — full sweep, mobilenet split ports, AXI limit off: **MODEL_RUNS_CORRECT**

66/66 valid (stream completed; OFM vs reference (5, 4, 491) on every run), 22 sets on ONE blob upload. Both checks PASS.
TRM-110: NONZERO 57 / ZERO 53. Reserved-61: NONZERO 47 / ZERO 14.
vs step 2 boot 18 (48 shared ids): **48 same / 0 different** (reproducible across boots).
vs step 1 boot 13 (kws, different workload and routing): 115 same, 38 ZERO→NONZERO, 18 NONZERO→ZERO — reported, not interpreted.

## 3b — AXI_SRAM = AXI_EXT = 0x00020000 (1 outstanding): 9/9 valid

`*_stall_limit`: 9 of 12 NONZERO (sram/sram0/sram1 rd+wr, ext/ext0/ext1 rd); ext/ext0/ext1 **wr** stay ZERO —
in this routing no write goes to the EXT port (EXT write traffic is also 0 in 3a). The limit knob was honoured (no rc 0x7D).
Controls: `sram_rd_trans_accepted` 69 726 and `ext_rd_trans_accepted` 15 722 equal 3a; npu_active +1.3 % (descriptive).

## Union across all valid campaigns (Tier B boot 9, 0b, 1, 2, 3a, 3b)

TRM-110 ever NONZERO: 78. Never: 32.

| class | ids |
| --- | --- |
| definition (1) | `no_event` |
| ECC error events (6) | `ecc_dma`, `ecc_mac_ib`, `ecc_mac_ab`, `ecc_ao_cb`, `ecc_ao_ob`, `ecc_ao_lut` |
| no EXT writes under split ports (+limit) (3) | `ext_wr_stall_limit`, `ext0_wr_stall_limit`, `ext1_wr_stall_limit` |
| no such port at 1024 MACs (22) | `sram2_rd_trans_accepted`, `sram2_rd_trans_completed`, `sram2_rd_data_beat_received`, `sram2_rd_tran_req_stalled`, `sram2_wr_trans_accepted`, `sram2_wr_data_beat_written`, `sram2_wr_tran_req_stalled`, `sram2_wr_data_beat_stalled`, `sram2_enabled_cycles`, `sram2_rd_stall_limit`, `sram2_wr_stall_limit`, `sram3_rd_trans_accepted`, `sram3_rd_trans_completed`, `sram3_rd_data_beat_received`, `sram3_rd_tran_req_stalled`, `sram3_wr_trans_accepted`, `sram3_wr_data_beat_written`, `sram3_wr_tran_req_stalled`, `sram3_wr_data_beat_stalled`, `sram3_enabled_cycles`, `sram3_rd_stall_limit`, `sram3_wr_stall_limit` |

Driver-only Reserved-61 ever NONZERO: 53. Never: 8 — `wd_stalled_by_ws_fc`, `wd_stalled_by_ws_tc`, `wd_trans_ws_fc`, `wd_trans_ws_tc`, `sram2_wr_trans_completed_m`, `sram2_wr_trans_completed_s`, `sram3_wr_trans_completed_m`, `sram3_wr_trans_completed_s`

First campaign in which each TRM id counted is in `step3_union_first_nonzero.csv`.

Restore + postflight verified (`postflight_restore_3.txt`).
