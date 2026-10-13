# On-chip fast scratch A/B — report

Contract `docs/superpowers/specs/2026-10-12-u85-onchip-fast-contract.md` (frozen `8cd51c3`, before deploy).
Image APP `0cd28e1d…` (deploy `evidence_m8`), boots 43–48, 35 RUNs each, all valid; on-chip runs rc 0 (base
`0x3110_0000` accepted by the runner's range check).

## Outcome (preregistered): **REFUTED** (kws, ad_medium agree; mobilenet the same) — `OUTCOME.md`

Gap closure −0.014 / 0.001 / −0.000; mac_active and EXT beats identical; control / screening 2 = 0.998–1.001.

## Reading — POST_HOC_DESCRIPTIVE

Fast scratch in on-chip SRAM (as MLEK) instead of DDR changes nothing. Together with fast_ext (DDR via EXT), the
runner's NPU-active cycles are the same for three different memories behind fast scratch: the gap is not where
fast scratch lives. Next: timing adapters (contract `566694b`).
