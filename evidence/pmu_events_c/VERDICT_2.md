# Tier C step 2 (targeted) — boot 18 verdict
(contract: docs/superpowers/specs/2026-10-07-pmu-model-step2-targeted-contract.md + amendments 1, 2)

Image MODEL=1 (APP 919c2477…), blob mobilenet v2 split ports (838b2488…): cmd+constants on EXT (S DRAM),
arena+fast scratch on the SRAM port (staging), PMCAXI_CHAN = EXT / rd_weights. 48 ids, 6 sets × 3, one boot,
`--validity model`.

## Campaign: **MODEL_RUNS_CORRECT** under amendment 2 (stream completed on every run)

18/18 valid: vendor_rc 2 (output mismatch only), STATUS 0xFFFF0020 (cmd_end_reached, no faults), QREAD = 17468 =
cms_len, flags 0xD. Every run's OFM vs reference: (5 bytes, max |diff| 4, first index 491) — the same on all 18.
Preregistered checks: `CYCLE_EVENT_VS_PMCCNTR` **PASS**, `NPU_ACTIVE_LE_CYCLE` **PASS**. No knob refusal (0x7D).

## Events (48 requested): NONZERO 36 / ZERO 12

- `sram_*`, `sram0_*`, `sram1_*` traffic and stalls (24) — **all NONZERO** (were ZERO in step 1 with everything on EXT).
- `axi_latency_any/_32/_64/_128/_256/_512/_1024` (7) — **all NONZERO** (835 / 835 / 832 / 637 / 21 / 20 / 20 on rep 1).
- controls 17, 32, 35, 140, 396 — NONZERO.
- ZERO: every `*_stall_limit` (12): `sram_`, `sram0_`, `sram1_`, `ext_`, `ext0_`, `ext1_` × rd/wr.

## Where the TRM-110 zeros now stand (union of steps 0b, 1, 2; descriptive)

`sram2_*`/`sram3_*` 22 (no such port at 1024 MACs), `ecc_*` 6, `*_stall_limit` 12, `no_event` 1 → 41 ids never
observed nonzero. All 69 others have been observed NONZERO in at least one valid campaign. The stall_limit
counters need outstanding transactions to reach the AXI limit (vendor AXI_SRAM/AXI_EXT = 0x00021F3F); that is a
further knob, not exercised here.

## POST_HOC_DESCRIPTIVE

Windows ≈ 73.9 M cycles of which `npu_active` ≈ 10.7 M; the rest includes the in-window constant copy.
Restore + postflight verified (`postflight_restore_2.txt`).
