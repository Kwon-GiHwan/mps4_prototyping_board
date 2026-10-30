# FI101 Stage 3 — model-level memory access and unit stalls (all seven MLEK models)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`) — the memory system is the TA-emulated SYS_DRAM_Mid, not
the physical FPGA DRAM.** Image APP `2bb04bfa`, boots 94–100, PMU sets B, C, E, F, G (traffic, stalls, ports) and
A, D, E (unit stalls), 8 measured RUNs per set, ratios within one RUN. Stage 0 applied (`results/fi101_stage0/`):
S0-1/2/4 PASS for all seven; denominators are NPU-counted cycles (`npu_active`), which undercount elapsed time by
0–31 % (S0-3). Per-channel traffic: `results/fi101_stage3_channels/`.

## Traffic, bandwidth, stalls

Bytes = beats × 16 (128-bit ports); aggregate events sum the 2 ports of each kind, so stall ratios use
2 × `npu_active` and B/cycle is summed over the 2 ports (peak 32 B/cycle per kind).

| model | SRAM bytes | EXT bytes | bytes / MAC | SRAM B/cycle | EXT B/cycle | RD burst SRAM / EXT | RD req stall SRAM / EXT | WR beat stall SRAM / EXT | SRAM0/1 rd imbalance | EXT0/1 rd imbalance | Vela SRAM / DRAM bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kws_micronet_m | 0.65 MB | 0.25 MB | 0.058 | 7.1 | 2.8 | 6.8 / 9.8 | 0.4 % / 9.9 % | 0.0 % / inc. | 0.00 | 0.03 | 1.01 / 0.32 MB |
| ad_medium_int8 | 1.80 MB | 0.71 MB | 0.040 | 12.3 | 4.8 | 14.2 / 13.3 | 0.0 % / 13.1 % | inc. / zero | 0.00 | 0.00 | 2.23 / 0.76 MB |
| mobilenet_v2_1.0_224_INT8 | 17.19 MB | 5.59 MB | 0.076 | 11.9 | 3.9 | 11.0 / 12.9 | 0.0 % / 9.7 % | 0.0 % / 0.9 % | 0.00 | 0.00 | 19.44 / 6.87 MB |
| vww4_128_128_INT8 | 2.07 MB | 0.38 MB | 0.130 | 8.8 | 1.6 | 9.3 / 7.5 | 0.6 % / 9.9 % | 1.6 % / zero | 0.00 | 0.00 | 2.50 / 0.62 MB |
| rnnoise_INT8 | 0.00 MB | 0.13 MB | 1.500 | 0.1 | 2.5 | 1.4 / 9.8 | 0.0 % / 11.6 % | zero / inc. | 0.03 | 0.01 | 0.00 / 0.12 MB |
| yolo-fastest_192_face_v4 | 6.80 MB | 0.48 MB | 0.187 | 15.2 | 1.1 | 10.4 / 7.3 | 0.1 % / 6.0 % | 0.0 % / 0.1 % | 0.00 | 0.00 | 7.53 / 0.79 MB |
| wav2letter_pruned_int8 | 8.06 MB | 29.69 MB | 0.011 | 2.0 | 7.2 | 13.3 / 15.3 | 0.0 % / 18.2 % | 0.0 % / 0.1 % | 0.00 | 0.00 | 12.14 / 33.40 MB |

- EXT read requests are stalled for 6–18 % of port-cycles (wav2letter 18 %); SRAM read requests almost never
  (≤ 0.6 %). Write-beat stalls are ≤ 1.6 % everywhere. Outstanding-limit stalls (`*_stall_limit`) are zero or 0/1
  (`results/fi101_stage0/event_validity.csv`): the limits are not what holds the reads back; the TA-emulated EXT
  latency is the candidate.
- SRAM0/SRAM1 read traffic is perfectly balanced (imbalance 0.00) and so is EXT0/EXT1 read traffic except kws
  (0.03), rnnoise (0.01); address striping spreads the load. (EXT write imbalance is not computed where one EXT write
  port counted zero: ad, kws, rnnoise, vww4.)
- Measured bytes stay below Vela's estimate for every model (e.g. mobilenet SRAM 17.2 vs 19.4 MB, wav2letter EXT
  29.7 vs 33.4 MB).
- Bytes per MAC: wav2letter 0.011 (weight-dominant, high reuse of activations) … rnnoise 1.5 (tiny model, every
  byte used once). Achieved SRAM bandwidth peaks at 15.2 B/cycle (yolo), about half of the two ports' 32 B/cycle.

**Cells `zero` / `inc.`** (corrected 2026-10-31): the contract excludes events that are not `COUNTED_NONZERO` from
ratios; the CSVs carry the verdict (`COUNTED_ZERO`, `INCONSISTENT` = 0 in some RUNs, nonzero in others) instead of a
number. Before the correction these 40 cells (stage3 32, unit_stalls 8) held 0.0, 1.0 or a small ratio; no other value
changed. Outstanding-limit ratios (142, 143, 398, 399): only 6 of 28 cells are numbers, all ≤ 0.13 % (kws, vww4 SRAM
rd; vww4, wav2letter EXT rd; wav2letter, yolo EXT wr); the rest are `COUNTED_ZERO` (kws EXT rd `INCONSISTENT`).

## Unit stalls (÷ `npu_active`, same RUN) — Reserved-ID events, meaning inferred from driver status bits

| model | MAC by W | MAC by IB | MAC by W or ACC | MAC by ACC | AO by BS or OB | AO by OB | AO by AB or CB | AO by CB | WD by WD buf | CC blockdep |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kws_micronet_m | 12.1 % | 9.8 % | 13.7 % | 1.3 % | 43.8 % | zero | 41.3 % | zero | 54.3 % | 26.0 % |
| ad_medium_int8 | 14.2 % | 14.7 % | 14.7 % | 0.5 % | 27.7 % | zero | 56.0 % | zero | 61.2 % | 12.4 % |
| mobilenet_v2_1.0_224_INT8 | 14.5 % | 33.3 % | 21.6 % | 7.1 % | 21.0 % | 0.4 % | 40.0 % | 9.1 % | 64.9 % | 12.5 % |
| vww4_128_128_INT8 | 10.3 % | 27.6 % | 10.2 % | zero | 47.7 % | 1.8 % | 31.3 % | 4.6 % | 43.3 % | 51.8 % |
| rnnoise_INT8 | 22.8 % | 6.5 % | 22.7 % | zero | 55.5 % | zero | 41.1 % | 13.3 % | 0.4 % | 40.8 % |
| yolo-fastest_192_face_v4 | 6.6 % | 33.8 % | 6.6 % | 0.1 % | 22.7 % | 0.0 % | 37.3 % | 11.8 % | 62.5 % | 34.8 % |
| wav2letter_pruned_int8 | 13.4 % | 1.0 % | 13.4 % | zero | 3.2 % | 0.1 % | 11.6 % | 0.1 % | 55.2 % | 0.2 % |

- MAC stalled by the input buffer is high for mobilenet (33 %), yolo (34 %) and vww4 (28 %) — the depthwise-heavy
  models — and low for wav2letter (1 %). Together with the per-channel data (IFM is 78 % of SRAM reads for vww4 and
  yolo, at moderate volume) this points at IFM latency / access pattern rather than IFM volume; untested.
- `wd_stalled_by_wd_buf` is 43–65 % for all Conv models and 0.4 % for rnnoise: the weight decoder mostly waits for
  buffer space (consumer side), except in rnnoise.
- Command-controller block-dependency stalls are high for vww4 (52 %), rnnoise (41 %), yolo (35 %), kws (26 %).
- AO is stalled 21–56 % of active cycles (by BS or OB, by AB or CB) in every model except wav2letter (3–12 %).

## Not claimed

Model-level associations only — which operators carry these stalls needs Stage 2. Latency distributions are not
measured. "Not the physical DRAM": every memory number here is under the TA emulation.

## Files

`stage3.csv` (traffic, bandwidth, burst, stalls, port imbalance, per-port bytes, Vela bytes), `unit_stalls.csv`;
`events_pass_B_to_G.csv` / `_wide.csv`: every event of sets B–G per model (name, TRM or Reserved, n, median, min, max,
verdict; `npu_active` appears once per set).
Generated by `host/analysis/fi101_s013.py` (Stage 0/1/3 tables).
