# S0-3 gap — what it goes with across the seven models (`POST_HOC_DESCRIPTIVE`)

Step 1 of `docs/plan/s0_3_resolution_plan.md`. **TA state: profile 1.** No new measurement: inputs are the committed
fi101_s013 tables (boots 94–100; channel boots 101–128), image `2bb04bfa`. Gap = CPU DWT span − NPU `PMCCNTR` span
between the same two seams (S0-3). n = 7 models, 17 features — this ranks candidates, it proves nothing.

`python3 results/fi101_s0_3_correlation/correlate.py` → `features.csv`, `correlation.csv`.

## Result

| model | gap (cycles) | gap / NPU span | SRAM wr beats | gap / SRAM wr beat | SRAM rd beats | Vela ops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rnnoise | −1 | 0.0 % | 135 | ≈ 0 | 143 | 39 |
| kws | 8,408 | 9.0 % | 17,760 | 0.47 | 22,664 | 13 |
| wav2letter | 12,842 | 0.3 % | 40,950 | 0.31 | 463,085 | 27 |
| ad | 20,574 | 13.9 % | 41,888 | 0.49 | 70,538 | 13 |
| vww4 | 31,203 | 13.1 % | 60,045 | 0.52 | 69,326 | 81 |
| yolo | 141,689 | 31.4 % | 188,708 | 0.75 | 236,070 | 95 |
| mobilenet | 340,600 | 23.5 % | 401,443 | 0.85 | 672,948 | 69 |

Rank correlation (Spearman) with the gap in cycles, strongest first:

| feature | Spearman | Pearson | Spearman without mobilenet |
| --- | ---: | ---: | ---: |
| **SRAM write beats** (135) | **+1.00** | +1.00 | +1.00 |
| SRAM write transactions (132) | +0.89 | +0.99 | +0.83 |
| DMA (rd_mem2mem) EXT read beats | +0.89 | +0.98 | +0.83 |
| `mac_stalled_by_ib` ratio | +0.86 | +0.73 | +0.83 |
| SRAM read transactions / beats | +0.79 / +0.75 | +0.85 / +0.78 | +0.66 / +0.60 |
| NPU span, Vela ops | +0.64 | +0.09 / +0.54 | +0.66 / +0.60 |
| EXT read beats | +0.54 | −0.09 | +0.49 |
| `cc_stalled_on_blockdep`, MAC active ratio | ≈ 0 | ≈ 0 | ≈ 0 |

## Reading

- The gap follows **SRAM write volume**: same rank order in all seven models, also without mobilenet. It is not
  proportional (0.31–0.85 gap cycles per SRAM write beat), and rnnoise's 135 write beats leave no gap at all.
- It does **not** follow elapsed time or EXT traffic: wav2letter has the longest span and by far the most EXT reads
  (1.84 M beats) but a gap of 0.3 %. So it is not a periodic stop of the NPU clock (e.g. TA `PULSE_OFF` over time) and
  not tied to the TA-emulated EXT latency.
- Fraction of the span is best ranked by `mac_stalled_by_ib` (+0.93) — models whose MACs wait on the input buffer lose
  more counted cycles. Collinear with SRAM traffic; not separable here.

Candidate explanations to test on the board (step 2), none tested:

1. **SRAM side of the NPU (TA_SRAM, profile 1: `wlatency` 32, `maxw` 8)**: NPU cycles stop advancing while SRAM writes
   are held. Test: TA profile 1 ↔ 2 (pass-through) — the existing knob, no firmware change.
2. **NPU clock gating** (`CLKFORCE` 0x140, bits top/cc/dma/mac/ao/wd "force clocks on for clock gating", driver header
   `ethosu85_interface.h`; neither the vendor driver nor the runner writes it): `PMCCNTR` stops while the top-level
   clock is gated. Test: `CLKFORCE` all-on vs reset value — needs a runner knob (firmware change).
3. **Shared on-chip SRAM with the CPU** (runner busy-polls from on-chip SRAM with caches off — E5 difference from MLEK):
   contention seen only from the CPU side. Test: CPU wait location / WFE — firmware change.

Not claimed: any cause; any statement about MLEK (MLEK has no start seam; its S0-3 is unknown).
