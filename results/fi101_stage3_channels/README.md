# FI101 Stage 3 — per-channel AXI traffic (added model by model)

**TA state: profile 1.** Image APP `2bb04bfa`; contract `evidence/fi101_s013/contract.md` amendments 2–3. Each boot
runs the model's measured blob with only `PMCAXI_CHAN` (header word 16) = `BW_CH_SEL_EN | CH_SEL`, one PMU set
(`35 128 130 132 135 384 386 391`), 10 RUNs (8 measured). "Unfiltered" = the same events in pass B of the model's
boot 94–100. Share = channel median ÷ unfiltered median. Raw: `evidence/fi101_s013/raw_chan/`. Rule
(`CHANNEL_FILTER_WORKS`): every channel ≤ unfiltered, at least one below, `npu_active` unchanged.

**Write side is not interpretable.** With `wr_ofm` selected, `sram_wr_trans_accepted` stays at the unfiltered
count while every write **beat** event reads 0 (rnnoise: 113 / 113 transactions, 0 / 135 beats). The read side
behaves as a filter; the write side does not. Write shares are therefore not reported. (A plausible reading is that
AXI W beats carry no channel ID; not verified.)

## rnnoise_INT8 (boots 101–104) — `CHANNEL_FILTER_WORKS`

| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unfiltered | 7,838 | — | 143 | — | 800 | 99 |
| rd_weights | 6,397 | 81.6 % | 0 | 0 % | 434 | 0 |
| rd_ifm | 25 | 0.3 % | 53 | 37.1 % | 9 | 21 |
| rd_mem2mem (DMA) | 176 | 2.2 % | 0 | 0 % | 22 | 0 |
| sum of the three | 6,598 | 84.2 % | 53 | 37.1 % | | |

Reading: rnnoise's DRAM reads are mostly weights (82 %); weights come over EXT only. The rest of EXT reads (≈16 %)
and of SRAM reads (≈63 %) belong to channels not measured here (command stream, scale/bias, IFM stream, mem2mem
index). Average weight burst on EXT: 6,397 / 434 ≈ 14.7 beats per transaction.
