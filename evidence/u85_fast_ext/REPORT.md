# Fast scratch on EXT — report

Contract: `docs/superpowers/specs/2026-10-12-u85-fast-scratch-ext-contract.md` (frozen in `9a93fee`, before boot 34).
Boots 34–36 (kws, ad_medium, mobilenet), 35 RUNs each, all 35 valid. Same image, Vela output (sha256) and AXI
limits as screening 2; only REGIONCFG region 2 changed (`0x0a` → `0x2a`: fast scratch → EXT port, DRAM).
conv3x3/matmul show NOT_EXECUTABLE in `fingerprint.md` only because they were not part of this run (the unchanged
analysis script lists all five; their metadata was copied so it can run).

## Outcome (preregistered)

| workload | outcome | npu_active R | R / MLEK ACTIVE | R / screening 2 | EXT rd / expected | EXT wr / expected |
| --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | **FAST_PATH_NOT_CAUSE** | 463,586 | 5.07 | 1.39 | 1.000 | 1.000 |
| ad_medium_int8 | **FAST_PATH_NOT_CAUSE** | 1,257,692 | 8.62 | 1.32 | 1.000 | 1.000 |
| mobilenet_v2 | **FAST_PATH_NOT_CAUSE** | 11,618,418 | 8.02 | 1.15 | 1.000 | 1.000 |

Routing check: EXT beats equal MLEK's EXT + SRAM beats exactly (ratio 1.000 to three places) — all fast-scratch
traffic moved to EXT, and MLEK's SRAM-port beats are exactly this runner's fast-scratch traffic.

## Observations — `POST_HOC_DESCRIPTIVE`

1. **The fast-scratch path is not the cause of the gap to MLEK.** Moving it from DDR-behind-the-SRAM-port to EXT DRAM
   made every workload slower (+15 to +39 %), not closer to MLEK. In this runner the SRAM-port path is the faster one.
2. EXT request stalls rose from 1–2 % to 10.7–11.5 % (read) and 4–6 % (write) with the extra EXT traffic.
3. `mac_active` is unchanged (kws 56,450; ad 93,672; mobilenet 574,793–574,799) — the extra time is again
   non-MAC-active time. OFM: kws/ad byte-exact; mobilenet the usual 5 bytes ≤ 4.
4. Withdrawn hypothesis C of the screening-2 cause summary ("fast-scratch path slow") and the screening-2 report's
   observation 3 reading ("consistent with the SRAM-port path being the slower one") — contradicted here.

## What remains (not tested)

Same command stream and EXT/SRAM traffic as MLEK, same board, yet 3.7–7× NPU-active cycles. Untested differences:
NPU power/clock handling by the vendor `test_u85` path vs the core driver, CPU activity during the job (vendor
`BUSY_SLEEP` loop vs driver wait; D-cache off vs on), timing adapter (MLEK ON — would slow MLEK, so an unlikely
explanation), command-stream memory location/attributes, and anything else `test_u85` writes that the driver does not.
