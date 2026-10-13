# Ethos-U85 first-pass screening — report

Contract: `docs/superpowers/specs/2026-10-12-u85-screening-contract.md` (frozen in `736caa5` with the analysis
code, before boot 24). Board FI101 r1p0 via `ssh gihwan`, MODEL image APP `0f215ef5…` (already on the card).
Boots 24–28, one per workload, 35 RUNs each (1–5 warm-up, 6–35 measured), the 8 events in one set.
Per-run data: `screening_per_run.csv`; summaries: `screening_summary.json`; raw: `<workload>/`.

## Outcome (preregistered)

All five **SCREENED**: 35/35 RUNs valid, 30 measured, no consistency failure (`npu_active ≤ window`,
`mac_active ≤ npu_active`, stalls ≤ `ext_enabled`, no overflow). The fallback routing was not needed. OFM: four
workloads byte-exact against tflite_runtime; mobilenet differs in 5/1001 bytes by ≤ 4 (vendor_rc 2), as in every
earlier mobilenet campaign (validity = completion, step-2 amendment 2).

## Fingerprint (median of 30)

| metric | kws_micronet_m | mobilenet_v2 | ad_medium | conv3x3 (isolated) | matmul (isolated) |
| --- | --- | --- | --- | --- | --- |
| M1 npu_active (cycles) | 521,665 | 10,543,758 | 1,359,638 | 607,386 | 15,096 |
| window (PMCCNTR, incl. staging) | 3,070,016 | 73,788,649 | 9,224,137 | 9,537,304 | 396,450 |
| M2 npu_active / window | 17.0% | 14.3% | 14.7% | 6.4% | 3.8% |
| M3 peak MAC efficiency | 2.9% | 2.8% | 4.5% | 18.6% | 6.8% |
| MAC active-cycle efficiency | 26.9% | 49.5% | 62.0% | 66.7% | 100.0% |
| M4 MAC active ratio | 10.8% | 5.6% | 7.2% | 27.9% | 6.8% |
| M5 EXT beats / MAC | 0.00063 | 0.00082 | 0.00047 | 0.00045 | 0.00222 |
| read / write beats per MAC | 0.00063 / ~0 | 0.00082 / ~0 | 0.00047 / ~0 | 0.00034 / 0.00011 | 0.00197 / 0.00024 |
| M6 EXT read-req stall | 0.3% | 1.8% | 0.8% | 3.4% | 2.9% |
| EXT write-req / write-data stall | 0 / 0 | 0 / 0 | 0 / 0 | 1.2% / 1.2% | 0.2% / 0.2% |
| M7 Vela signed error (cycles_total vs npu_active) | −80.1% | −74.1% | −86.5% | +92.1% | −44.8% |
| Vela cycles_npu vs npu_active | −82.9% | −84.3% | −88.6% | −72.7% | −86.0% |
| CV of npu_active (30 runs) | 0.6% | 0.1% | 0.2% | 0.5% | **19.1%** |

Units and scope, as preregistered: cycles only (no ms: clock unverified); beats only (no bytes); M1 is NPU-running
cycles, not latency of the inference call; M2 is the share of a window dominated by CPU staging copies, so it is
**not** NPU utilisation; M3 assumes 1024 int8 MACs/cycle (Vela convention, not TRM-verified); M7 mixes Vela model
error with the FPGA's unknown core/DRAM clock ratio (Vela assumes 500 MHz, DRAM at 0.47×).

Rank per metric (1 = highest):

| metric | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| M3 peak MAC eff. | conv3x3 | matmul | ad_medium | kws | mobilenet |
| M4 MAC active ratio | conv3x3 | kws | ad_medium | matmul | mobilenet |
| M5 EXT beats/MAC | matmul | mobilenet | kws | ad_medium | conv3x3 |
| M6 read-req stall | conv3x3 | matmul | mobilenet | ad_medium | kws |
| \|M7\| | conv3x3 | ad_medium | kws | mobilenet | matmul |

## Observations — `POST_HOC_DESCRIPTIVE` (not preregistered)

1. **Low compute utilisation, low EXT stall, everywhere.** M3 2.8–18.6 % and M4 5.6–27.9 %, while EXT read-request
   stall stays ≤ 3.4 %. In the guideline's terms this resembles pattern A (compute-side candidate) for all five,
   but see 3: the SRAM side, which carries the intermediate tensors here, was not measured.
2. **`mac_active` is deterministic and quantised.** It is identical in all 30 runs of every workload. For matmul
   it equals N_MAC/1024 exactly (1024 cycles → 100 % active-cycle efficiency); conv3x3 is exactly 1.5× N_MAC/1024
   (169,344 vs 112,896). So when the MAC block is active, its per-cycle fill depends on the operator shape
   (26.9 % kws … 100 % matmul); most of the loss in M3 is cycles where it is not active (M4).
3. **EXT traffic is essentially weights + IFM + OFM.** With `fast=sram` the intermediates go through the SRAM
   port: EXT writes are the OFM only. Write beats × 16 equal the OFM size exactly in all five (conv 12,544 ×16 =
   200,704; matmul 256 ×16 = 4,096; mobilenet 63 ≈ 1,001/16; kws and ad 1). That is consistent with 16-byte
   beats, but it is an inference from data; bytes stay unreported until the beat width is verified.
   Consequence: M5/M6 describe the EXT port only, and "memory bottleneck" cannot be judged without the SRAM events.
4. **Vela underestimates NPU time 3.7–8.8×** (`npu_active` / Vela `cycles_npu`) on all five. conv3x3 is the only
   positive `cycles_total` error because Vela predicts it DRAM-bound (1.17 M cycles of DRAM access) while the board
   ran it in 0.61 M. The direction is consistent with the FPGA memory being faster per NPU cycle than Vela's
   500 MHz system, but that clock ratio is unverified; this is the largest open question for M7.
5. **matmul is too short for stable timing.** 15 k NPU cycles, CV 19 %, against ≤ 0.6 % for the rest; its
   counts (`mac_active`, beats) are deterministic, only the time varies.
6. No warm-up effect: RUNs 1–5 fall inside the measured range for every workload.

## Second-pass routing — suggestions only (`POST_HOC_DESCRIPTIVE`)

| finding | next events |
| --- | --- |
| low M4 everywhere (1, 2) | `mac_stalled_by_*`, `ao_*`, `wd_active`/`wd_stalled`, `cc_stalled_on_blockdep` — where the inactive MAC cycles go |
| EXT-only view (3) | `sram_rd/wr_data_beat_*`, `sram_*_stalled`, `sram_enabled_cycles` — the intermediates' port |
| Vela gap (4) | NPU clock and DRAM latency on FI101 (verify, then re-derive a Vela system config), per-layer Vela vs board |
| matmul variance (5) | a larger isolated matmul shape before using its timing |

## Not done

ms latency, bytes, the clock, the beat width, SRAM-side metrics, per-layer breakdown, more than five workloads.
