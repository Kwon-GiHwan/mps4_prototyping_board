# POWER_CTRL A/B — report

Contract `docs/superpowers/specs/2026-10-12-u85-power-ctrl-ab-contract.md` (frozen `c1bb88f`, before the build).
Image APP `159fb188…` (deploy `evidence_m7`), boots 37–42, 35 RUNs each, all valid; treatment runs rc 0, i.e. the
seam read-back confirmed POWER_CTRL = 0 (a mismatch would have made the run invalid).

## Outcome (preregistered): **REFUTED** (kws and ad_medium agree; mobilenet the same)

See `OUTCOME.md`. Gap closure 0.005 / 0.001 / −0.000. mac_active and EXT beats identical between arms.
Image neutrality: control / screening 2 = 0.997 / 1.001 / 1.000 — the image change itself is neutral.

## Reading — POST_HOC_DESCRIPTIVE

MAC power ramping (vendor 2 vs driver 0) changes NPU-active cycles by ≤ 0.4 %. It is not the cause of the 3.7–7×
gap. The static diff's other during-job differences remain (`evidence/u85_runner_gap/hypothesis_status.md`), and
the on-chip-SRAM fast-scratch question reopened by `2026-10-12-u85-onchip-fast-contract.md`.
