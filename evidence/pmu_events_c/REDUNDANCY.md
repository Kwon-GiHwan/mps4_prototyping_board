# PMU counter redundancy (POST_HOC_DESCRIPTIVE)

Boots: boot9 = 1x1 conv, SRAM port; boot12 = 1x1 conv, EXT/DRAM; boot13 = kws, all EXT; boot18 = mobilenet, split ports (48 ids); boot19 = mobilenet, split ports; boot20 = mobilenet, split ports, AXI limit (19 ids); boot21 = ad_medium (FWD), all EXT (39 ids); boot22 = MatMul, all EXT (39 ids); boot23 = kws, all EXT, AXI limit (20 ids).
`drv` = driver-only (TRM Reserved). Approximate relations: repeat min–max ranges meet after widening by 2%.

Events nonzero in at least one boot: **138** of 171.

## A. Exact equality (deterministic counts)

- `wd_trans_wb0`(120, drv) = `wd_trans_wb1`(121, drv) = `wd_trans_wb2`(122, drv) = `wd_trans_wb3`(123, drv) — support: boot9, boot12, boot13, boot19, boot21, boot22
- `sram_rd_trans_accepted`(128) = `sram_rd_trans_completed`(129) — support: boot9, boot18, boot19
- `sram_wr_trans_accepted`(132) = `sram_wr_trans_completed_m`(133, drv) = `sram_wr_trans_completed_s`(134, drv) — support: boot9, boot19
- `ext_rd_trans_accepted`(384) = `ext_rd_trans_completed`(385) — support: boot12, boot13, boot19
- `ext_wr_trans_accepted`(388) = `ext_wr_trans_completed_m`(389, drv) = `ext_wr_trans_completed_s`(390, drv) — support: boot12, boot13
- `sram0_rd_trans_accepted`(512) = `sram0_rd_trans_completed`(513) — support: boot9, boot18, boot19
- `sram0_wr_trans_accepted`(516) = `sram0_wr_trans_completed_m`(517, drv) = `sram0_wr_trans_completed_s`(518, drv) — support: boot9, boot19
- `sram1_rd_trans_accepted`(528) = `sram1_rd_trans_completed`(529) — support: boot9, boot18, boot19
- `sram1_wr_trans_accepted`(532) = `sram1_wr_trans_completed_m`(533, drv) = `sram1_wr_trans_completed_s`(534, drv) — support: boot9, boot19
- `ext0_rd_trans_accepted`(640) = `ext0_rd_trans_completed`(641) — support: boot12, boot13, boot19
- `ext0_wr_trans_accepted`(644) = `ext0_wr_trans_completed_m`(645, drv) = `ext0_wr_trans_completed_s`(646, drv) — support: boot12, boot13
- `ext1_rd_trans_accepted`(656) = `ext1_rd_trans_completed`(657) — support: boot12, boot13, boot19
- `ext1_wr_trans_accepted`(660) = `ext1_wr_trans_completed_m`(661, drv) = `ext1_wr_trans_completed_s`(662, drv) — support: boot13

## B. Exact sums a = b + c (one member per class A)

- `sram_rd_trans_accepted`(128) = `sram0_rd_trans_accepted`(512) + `sram1_rd_trans_accepted`(528) — support: boot9, boot18, boot19
- `sram_rd_data_beat_received`(130) = `sram0_rd_data_beat_received`(514) + `sram1_rd_data_beat_received`(530) — support: boot9, boot18, boot19
- `sram_wr_trans_accepted`(132) = `sram0_wr_trans_accepted`(516) + `sram1_wr_trans_accepted`(532) — support: boot9, boot18, boot19
- `sram_wr_data_beat_written`(135) = `sram0_wr_data_beat_written`(519) + `sram1_wr_data_beat_written`(535) — support: boot9, boot18, boot19
- `ext_rd_trans_accepted`(384) = `ext0_rd_trans_accepted`(640) + `ext1_rd_trans_accepted`(656) — support: boot12, boot13, boot19
- `ext_rd_data_beat_received`(386) = `ext0_rd_data_beat_received`(642) + `ext1_rd_data_beat_received`(658) — support: boot12, boot13, boot19
- `ext_wr_trans_accepted`(388) = `ext0_wr_trans_accepted`(644) + `ext1_wr_trans_accepted`(660) — support: boot13
- `ext_wr_data_beat_written`(391) = `ext0_wr_data_beat_written`(647) + `ext1_wr_data_beat_written`(663) — support: boot13

## C. Aggregate ≈ port0 + port1 (repeat ranges meet, widened by 2%)

- `sram_rd_trans_completed`(129) ≈ `sram0_rd_trans_completed`(513) + `sram1_rd_trans_completed`(529) — holds — support: boot9, boot18, boot19
- `sram_rd_tran_req_stalled`(131) ≈ `sram0_rd_tran_req_stalled`(515) + `sram1_rd_tran_req_stalled`(531) — holds — support: boot9, boot18, boot19
- `sram_wr_trans_completed_m`(133, drv) ≈ `sram0_wr_trans_completed_m`(517, drv) + `sram1_wr_trans_completed_m`(533, drv) — holds — support: boot9, boot19
- `sram_wr_trans_completed_s`(134, drv) ≈ `sram0_wr_trans_completed_s`(518, drv) + `sram1_wr_trans_completed_s`(534, drv) — holds — support: boot9, boot19
- `sram_wr_tran_req_stalled`(136) ≈ `sram0_wr_tran_req_stalled`(520) + `sram1_wr_tran_req_stalled`(536) — holds — support: boot18, boot19
- `sram_wr_data_beat_stalled`(137) ≈ `sram0_wr_data_beat_stalled`(521) + `sram1_wr_data_beat_stalled`(537) — holds — support: boot18, boot19
- `sram_enabled_cycles`(140) ≈ `sram0_enabled_cycles`(524) + `sram1_enabled_cycles`(540) — **does not hold** in some boot
- `sram_rd_stall_limit`(142) ≈ `sram0_rd_stall_limit`(526) + `sram1_rd_stall_limit`(542) — holds — support: boot20
- `sram_wr_stall_limit`(143) ≈ `sram0_wr_stall_limit`(527) + `sram1_wr_stall_limit`(543) — holds — support: boot20
- `ext_rd_trans_completed`(385) ≈ `ext0_rd_trans_completed`(641) + `ext1_rd_trans_completed`(657) — holds — support: boot12, boot13, boot19
- `ext_rd_tran_req_stalled`(387) ≈ `ext0_rd_tran_req_stalled`(643) + `ext1_rd_tran_req_stalled`(659) — holds — support: boot12, boot13, boot19
- `ext_wr_trans_completed_m`(389, drv) ≈ `ext0_wr_trans_completed_m`(645, drv) + `ext1_wr_trans_completed_m`(661, drv) — holds — support: boot13
- `ext_wr_trans_completed_s`(390, drv) ≈ `ext0_wr_trans_completed_s`(646, drv) + `ext1_wr_trans_completed_s`(662, drv) — holds — support: boot13
- `ext_wr_tran_req_stalled`(392) ≈ `ext0_wr_tran_req_stalled`(648) + `ext1_wr_tran_req_stalled`(664) — holds — support: boot13
- `ext_wr_data_beat_stalled`(393) ≈ `ext0_wr_data_beat_stalled`(649) + `ext1_wr_data_beat_stalled`(665) — holds — support: boot13
- `ext_enabled_cycles`(396) ≈ `ext0_enabled_cycles`(652) + `ext1_enabled_cycles`(668) — holds — support: boot9, boot12, boot13, boot19
- `ext_rd_stall_limit`(398) ≈ `ext0_rd_stall_limit`(654) + `ext1_rd_stall_limit`(670) — holds — support: boot20, boot23
- `ext_wr_stall_limit`(399) ≈ `ext0_wr_stall_limit`(655) + `ext1_wr_stall_limit`(671) — holds — support: boot23

## D. Cycle-like counters equal within repeat ranges ± 2%

- `cycle`(17) ≈ `sram0_enabled_cycles`(524) ≈ `sram1_enabled_cycles`(540) ≈ `ext0_enabled_cycles`(652) ≈ `ext1_enabled_cycles`(668)
- `sram_enabled_cycles`(140) ≈ `ext_enabled_cycles`(396)

## Count

- nonzero in at least one boot: 138
- expressible by the relations above (A–D): 44
- **left: 94**

"Left" is an upper bound on independent information, not a count of independent counters: only
pairwise equality and two-term sums are searched, and an equality seen on these workloads may
be a property of the workloads (e.g. even load across ports) rather than of the counters.

## Notes

- The one contradicted relation, `sram_enabled_cycles` ≈ port0 + port1, fails only in boot 9 (1x1 conv, ~5.9k
  cycles): aggregate 8.9k against a port sum of at least 10.8k. On the larger workloads it holds. Not resolved.
- Class A `*_trans_accepted = *_completed(_m/_s)` holds because every transaction finished within the window;
  a run that stops with transactions outstanding would separate them.
- Workload-dependent rather than by definition: `wd_trans_wb0..3` equal (even buffer loading), port
  `enabled_cycles` ≈ `cycle` (ports clocked for the whole window). Different hardware states could split them.
