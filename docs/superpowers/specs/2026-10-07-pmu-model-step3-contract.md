# Tier C step 3 — full 171-id sweep on mobilenet (3a) and AXI-limit targeted run (3b) (contract)

Frozen 2026-10-07, **before any data exists**. Authorization: owner, 2026-10-07 ("둘 다 진행하자").
Plan: `docs/superpowers/plans/2026-10-07-u85-pmu-real-model-plan.md` (단계 3 결정).

## Changes (MODEL build only; EXT=0/1 images unchanged)

1. **Upload once per boot.** The state table also accepts `SET_INSTRUMENTATION_MODE` in `INPUT_READY` and
   `RESULT_READY`. Host `--keep-model`: `RESET → SET_MODE → LOAD_MODEL(CRC) → LOAD_INPUT` once, then per set
   only `SET_MODE` and three RUNs. RESET semantics unchanged. Between sets, each RUN's power-hold sequence clears
   OVS/CNTEN/INT and resets the counters before arming; slots ≥ count are never armed.
2. **PMWL header v3** (32 words): v2 knobs + `[23] AXI_SRAM [24] AXI_EXT` (0xFFFFFFFF = off), applied at the
   POWER_CTRL seam after the vendor's own write (0x00021F3F), read back; mismatch → rc 0x7D.
   TRM: `max_outstanding_read_m1[5:0]`, `max_outstanding_write_m1[12:8]`, `max_beats[17:16]`.

## 3a — full sweep

mobilenet, blob as step 2 (split ports, PMCAXI_CHAN = EXT/rd_weights), AXI limits **off**, all 171 ids,
22 sets × 3, one boot, `--validity model`, `--keep-model`. Verdicts: Tier B closed set; campaign as step 2.
Preregistered comparisons (same/different verdict per id): vs step 2 boot 18 (48 shared ids), vs step 1
boot 13 (171 ids, different workload — reported, not interpreted).

## 3b — AXI limit

Same blob with `AXI_SRAM = AXI_EXT = 0x00020000` (one outstanding read and write per port, 256-B bursts).
Ids: the 12 `*_stall_limit` + controls 17, 32, 35, 140, 396 + `sram_rd_trans_accepted` 128,
`ext_rd_trans_accepted` 384 (19 ids, 3 sets × 3). Question: do the stall_limit counters count when the limit is
reachable? Verdicts: Tier B closed set per id. Validity as 3a.
