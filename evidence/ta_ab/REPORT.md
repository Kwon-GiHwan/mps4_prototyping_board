# Timing adapter A/B — report

Contract `docs/superpowers/specs/2026-10-12-u85-timing-adapter-ab-contract.md` (frozen `566694b`, before deploy).
Image APP `2c2fa435…`, VECTORS `d8c32b14…` (VECTORS differs from earlier images; rebuilt with the TA tables),
DDR `81d37a21…`; deploy `evidence_m9`. Boots 49–56, 35 RUNs each, all valid. TA arms rc 0: both TAs reported
TA_VERSION 0x1117 and read back every written value on every RUN.

## Outcome (preregistered): **SUPPORTED** — kws, ad_medium agree; mobilenet the same (`OUTCOME.md`)

| workload | ctrl (TA untouched) | ta1 (MLEK TA) | MLEK board ACTIVE | gap closure |
| --- | --- | --- | --- | --- |
| kws_micronet_m | 334,695 | 91,058 | 91,431 | 1.002 |
| ad_medium_int8 | 952,191 | 146,547 | 145,976 | 0.999 |
| mobilenet_v2 | 10,121,840 | 1,452,640 | 1,448,049 | 0.999 |

mac_active and EXT beats identical between arms; OFM validity unchanged (kws/ad exact, mobilenet the usual 5 B ≤ 4).
Control / screening 2 = 1.000–1.001.

## Reading — POST_HOC_DESCRIPTIVE

1. **Cause found.** The runner never programs the NPU timing adapters; at their reset state every NPU memory
   access is slowed. Programming them as MLEK does reproduces MLEK's board NPU ACTIVE to within 0.4 % on all three
   workloads with the identical command stream. The removed cycles are all non-MAC-active cycles
   (kws 278,245 → 34,608).
2. **Pass-through (ta2, descriptive)**: kws 61,071, ad 111,878 — faster than MLEK. MLEK's own TA configuration adds
   latency (EXT RLATENCY 500 etc.) to emulate a mid-range DRAM system; MLEK's numbers are therefore "FI101 +
   emulated SYS_DRAM_Mid", not raw FI101.
3. **Every earlier screening number on this runner was taken under the TA reset state** (screening 1, 2, fast_ext,
   POWER_CTRL, on-chip). Their absolute values and the readings built on them — "MAC mostly idle", "Vela
   under-predicts 4–9×" — describe that state, not the NPU. Under MLEK's TA: MAC active ratio 62 / 64 / 40 %
   (kws / ad / mobilenet), peak MAC efficiency 16.7 / 41.5 / 20.2 %, Vela cycles_total error +12 / +1 / +62 %.
4. The TA reset register values were not read out (no wire field); which TA register(s) carry the slowdown is
   not established.
