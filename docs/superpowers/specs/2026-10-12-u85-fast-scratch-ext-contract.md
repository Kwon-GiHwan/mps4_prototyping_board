# Fast scratch on EXT — is the runner's fast-scratch path the cause of the gap to MLEK? (contract)

Frozen 2026-10-12, **before any data of this run exists**. Authorization: owner, 2026-10-12 ("확인 해봐").

## Question

Screening 2 (`2026-10-12-u85-screening-mlek-contract.md`) ran the **same Vela output** (sha256 equal) as the stock
MLEK board run of the paper campaign (`docs/paper/evidence/board-stage-b1..b3`), with **identical EXT beats**, yet
`npu_active` was 3.7× (kws), 6.5× (ad_medium), 7.0× (mobilenet) the MLEK `NPU ACTIVE`. The largest structural
difference left: MLEK's fast scratch (SRAM-port traffic) is on-chip SRAM `0x3100_0000`; the runner's is DDR staging
`0x9012_xxxx` behind the SRAM port. This run moves fast scratch to the EXT port (DRAM `0x7010_0000` region, the path
const/arena already use) and changes nothing else.

## Protocol

Screening-2 blobs re-packed with one change: `--ports cmd=ext,const=ext,arena=ext,fast=ext` (was `fast=sram`).
Same Vela profile `mlek`, same `--axi-limit sram=0x20F0B,ext=0x21F3F`, same MODEL image `0f215ef5…`, same 8 ids,
35 RUNs (1–5 warm-up). Boots **34, 35, 36** = kws_micronet_m, ad_medium_int8, mobilenet_v2_1.0_224_INT8.
Analysis: `host/screening_metrics.py` (unchanged) on `evidence/u85_fast_ext`, plus the outcome below.

## Reference values (fixed now)

| workload | MLEK ACTIVE, median of B1–B3 | screening 2 npu_active median | MLEK SRAM rd / wr beats (B1) | MLEK EXT rd / wr (B1) |
| --- | --- | --- | --- | --- |
| kws_micronet_m | 91,431 | 334,714 | 22,664 / 17,760 | 15,815 / 1 |
| ad_medium_int8 | 145,976 | 951,418 | 70,538 / 41,888 | 44,084 / 1 |
| mobilenet_v2 | 1,448,049 | 10,121,486 | 672,948 / 401,443 | 301,217 / 47,887 |

## Outcome per workload (closed set)

Let `R = median npu_active (this run)`, `M` = MLEK ACTIVE, `S` = screening-2 median.

- `FAST_PATH_EXPLAINS`: `R ≤ 1.25 × M`
- `FAST_PATH_PARTIAL`: `1.25 × M < R < 0.8 × S`
- `FAST_PATH_NOT_CAUSE`: `R ≥ 0.8 × S`
- `UNPROVEN`: fewer than 30 valid measured RUNs or a consistency failure (as screening 1)

## Routing check (descriptive, stated before data)

If all fast-scratch traffic moved to EXT, EXT read beats ≈ MLEK EXT rd + SRAM rd and EXT write beats ≈ MLEK EXT wr +
SRAM wr. Reported as the ratio measured / expected; no outcome depends on it.

## What a result would and would not show

- `FAST_PATH_EXPLAINS` shows that the SRAM-port → DDR-staging path accounts for the gap **in this runner**; it does
  not show that on-chip SRAM would match MLEK exactly (that would need firmware change), nor that EXT DRAM equals
  on-chip SRAM in speed.
- `FAST_PATH_NOT_CAUSE` sends the search to the remaining differences: timing adapter, NPU power/clock hold,
  IRQ wait loop, CPU-side activity during the job.
