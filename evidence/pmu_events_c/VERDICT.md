# Tier C step 0 — verdict (contract: docs/superpowers/specs/2026-10-07-pmu-ext-port-step0-contract.md)

Image: EXT=1 (APP 2d1a24ad…, VECTORS 9437774a…, DDR 81d37a21…), deployed 2026-10-07 (backup = original ffa3e5bd…).
Boot 10: aborted (ssh tunnel dropped during the REBOOT capture, 0 RUNs; `boot10/ABORTED.txt`). Boot 11: 66 RUNs.

## Q1 reachability: **EXT_UNREACHABLE**

rc ≠ 0 on every run (66/66 rc=1 = vendor test FAIL), valid_flags 0x9 (no RC_OK, no OUTPUT_CHANGED),
GET_RESULT refused (NACK 11, result not valid), so golden_ok never true. The board did not hang:
every RUN returned and the seam fired once per run.

## Q2 events: all 171 NOT_OBSERVED (no valid run). Comparison with Tier B: not computable.

## POST_HOC_DESCRIPTIVE (no verdict depends on this)

Counters read at the seam in the INVALID runs show the EXT port issuing and then stalling:
`ext_rd_trans_accepted` 4, `ext_rd_trans_completed` 4, `ext_rd_data_beat_received` 13 (all on ext1),
then `ext1_rd_tran_req_stalled` up to 4992 (arvalid & ~arready); `mac_active` 0, no SRAM traffic.
FI101 memory map: 0x9000_0000 is IDAU 9 "DDR4 Dev Access" (main expansion), the path the SRAM-side
managers (M0/M1 → XMSTEXPDEV) use; the EXT managers M2/M3 reach XMSTEPDRAM0/1, which the map lists as
"DDR4 DRAM0/1 Access" at IDAU 6 (NS) / 7 (S), i.e. 0x6000_0000 / 0x7000_0000. Consistent reading, not
established: the EXT port cannot serve the 0x9000_0000 alias; an EXT test needs the tensors at a DRAM alias.

Restore + postflight: RESTORE_DESTINATION == original backup; reboot DDR test PASSED; PING idle, error
counters 0; USB_OFF, card withdrawn (`postflight_restore.txt`).
