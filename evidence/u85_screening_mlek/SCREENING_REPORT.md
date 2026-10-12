# Ethos-U85 screening 2 (MLEK-Vela-aligned) — report

Contract: `docs/superpowers/specs/2026-10-12-u85-screening-mlek-contract.md` (frozen in `4ed151b`, before boot 29).
Board FI101 r1p0, MODEL image APP `0f215ef5…` (unchanged since screening 1). Boots 29–33, 35 RUNs each.
Vela: MLEK's `ethos-u85-1024` option list (`Ethos_U85_SYS_DRAM_Mid_1024`, MLEK `default_vela.ini`,
`--optimise Performance`, arena cache 384 KiB); AXI_SRAM `0x20F0B`, AXI_EXT `0x21F3F` (MLEK driver values).
**Not an MLEK measurement**: fast scratch is still DDR behind the SRAM port, no timing adapter, no TFLM.

## Outcome (preregistered)

All five **SCREENED** (35/35 valid, 30 measured, no consistency failure). Fallback not needed.
Fingerprint: `fingerprint.md`; comparison with screening 1: `compare.md`.

| metric (median of 30) | kws | mobilenet_v2 | ad_medium | conv3x3 | matmul |
| --- | --- | --- | --- | --- | --- |
| M1 npu_active (cycles) | 334,714 | 10,121,486 | 951,418 | 612,396 | 14,880 |
| M3 peak MAC efficiency | 4.5% | 2.9% | 6.4% | 18.4% | 6.9% |
| M4 MAC active ratio | 16.9% | 5.7% | 9.8% | 27.7% | 6.9% |
| M5 EXT beats / MAC | 0.0010 | 0.0012 | 0.0007 | 0.0004 | 0.0022 |
| M6 EXT read-req stall | 2.1% | 2.2% | 1.1% | 3.3% | 2.9% |
| M7 Vela signed error (cycles_total) | −69.5% | −76.7% | −84.4% | +14.3% | −66.4% |
| Vela cycles_npu vs npu_active | −74.2% | −82.8% | −85.3% | −73.9% | −88.6% |
| CV of npu_active | 1.2% | 0.0% | 0.3% | 0.5% | 18.9% |

Ratio of medians, screening 2 / screening 1 (preregistered comparison):

| workload | cms changed | npu_active | M3 | M4 | M5 EXT beats/MAC | M6 read stall |
| --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | yes | **0.642** | 1.559 | 1.559 | 1.614 | 6.318 |
| mobilenet_v2 | yes | 0.960 | 1.042 | 1.008 | 1.415 | 1.268 |
| ad_medium_int8 | yes | **0.700** | 1.429 | 1.362 | 1.517 | 1.431 |
| conv3x3 | yes | 1.008 | 0.992 | 0.992 | 0.980 | 0.963 |
| matmul | **no** | 0.986 | 1.015 | 1.015 | 1.000 | 1.000 |

Write-stall ratios are N/A where screening 1 had 0 (ratio undefined); see `compare.md`.

## Observations — `POST_HOC_DESCRIPTIVE`

1. **The Vela options change NPU time by up to a third.** kws −36 %, ad_medium −30 %, mobilenet −4 %;
   conv3x3 and matmul unchanged. So screening 1's absolute numbers were specific to the packer's Vela options;
   the cross-workload picture (low M3/M4, low EXT stall) is the same in both runs.
2. **The time saved is not MAC time.** `mac_active` is unchanged for kws (56,447/56,450 in both runs), conv3x3
   and matmul; −3.2 % for mobilenet, −4.7 % for ad_medium. kws's 187 k fewer cycles are all cycles where the MAC
   block was not active.
3. **More EXT traffic, yet faster.** EXT beats/MAC rose 42–61 % for kws, mobilenet and ad_medium (the 384 KiB cache
   limit moves data from the fast-scratch region to the EXT arena; mobilenet now writes to EXT). That this ran
   faster is consistent with the SRAM-port path (here backed by DDR staging, not on-chip SRAM) being the slower
   one — **not established**: no SRAM-port event was measured, and Vela options and AXI_SRAM changed together.
4. **matmul is the control.** Same command stream, no fast scratch (so the AXI_SRAM change has nothing to act on):
   `mac_active` (1,024) and EXT read/write beats (2,070 / 256) identical across boots 28 and 33, npu_active 0.986 (within its 19 % CV).
5. **conv3x3 output is no longer byte-exact.** 27 of 200,704 OFM bytes differ by 1 from tflite_runtime,
   identically in all 35 RUNs (screening 1: 0 bytes). vendor_rc 2, valid under the completion rule (contract).
   The Mid_1024 Vela output computes this layer slightly differently; cause not investigated.
6. The Vela gap remains: `cycles_npu` under-predicts by 74–89 % with Mid_1024 (1 GHz) as with DRAM_Low (500 MHz).

## Correction to screening 1's report

`evidence/u85_screening/SCREENING_REPORT.md` observation 2 says `mac_active` "is identical in all 30 runs of every
workload". That is wrong for kws_micronet_m: it takes two values, 56,447 and 56,450, in both screenings. It is
identical for the other four. Screening 1's report is left as written; this note is the correction.

## Not done

Fast scratch in on-chip SRAM, timing adapter, SRAM-port events, separating the Vela-option effect from the
AXI_SRAM effect, the conv3x3 numerical difference, an MLEK run for reference.
