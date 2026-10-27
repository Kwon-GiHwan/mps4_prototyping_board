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

## kws_micronet_m (boots 105–108) — `CHANNEL_FILTER_WORKS`

| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unfiltered | 15,815 | — | 22,664 | — | 1,609 | 3,337 |
| rd_weights | 11,857 | 75.0 % | 5,551 | 24.5 % | 789 | 397 |
| rd_ifm | 470 | 3.0 % | 16,213 | 71.5 % | 325 | 2,700 |
| rd_mem2mem (DMA) | 2,087 | 13.2 % | 0 | 0.0 % | 135 | 0 |
| sum of the three | 14,414 | 91.1 % | 21,764 | 96.0 % | | |

wr_ofm: SRAM wr beats 0 (unfiltered 17,760), SRAM wr trans 3,036 (unfiltered 3,170).

Reading: kws reads weights from both ports — 75 % of EXT read beats directly from DRAM and 24.5 % of SRAM read beats
from the on-chip fast scratch, which the DMA channel fills (13 % of EXT reads). IFM reads are SRAM-side (72 %). The
three channels cover 91 % of EXT and 96 % of SRAM reads. Write side: beats 0 again, transactions 3,036 vs 3,170
unfiltered (not equal this time) — still not interpretable.

## vww4_128_128_INT8 (boots 109–112) — `CHANNEL_FILTER_WORKS`

| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unfiltered | 23,761 | — | 69,326 | — | 3,150 | 7,440 |
| rd_weights | 15,586 | 65.6 % | 6,122 | 8.8 % | 1,120 | 798 |
| rd_ifm | 2,174 | 9.1 % | 54,444 | 78.5 % | 874 | 3,978 |
| rd_mem2mem (DMA) | 2,101 | 8.8 % | 0 | 0.0 % | 149 | 0 |
| sum of the three | 19,861 | 83.6 % | 60,566 | 87.4 % | | |

wr_ofm: SRAM wr beats 0 (unfiltered 60,045), SRAM wr trans 8,897 (unfiltered 9,038).

Reading: vww4's SRAM reads are mostly IFM (78.5 %, 54,444 beats; ≈ 13.7 beats per transaction), its EXT reads mostly
weights (65.6 %). IFM also comes over EXT in short bursts (2,174 beats in 874 transactions ≈ 2.5 beats each).
In beats per `npu_active` cycle the IFM stream is small (≈ 0.23 SRAM beats / cycle over 2 ports), so the input-buffer
stall seen in Stage 1 (`mac_stalled_by_ib` 28 %) is not explained by IFM volume alone — latency or access pattern
remain candidates (not measured here). Write side: beats 0, transactions 8,897 vs 9,038.

## yolo-fastest_192_face_v4 (boots 113–116) — `CHANNEL_FILTER_WORKS`

| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unfiltered | 29,347 | — | 236,070 | — | 4,007 | 22,757 |
| rd_weights | 14,300 | 48.7 % | 27,052 | 11.5 % | 1,042 | 3,204 |
| rd_ifm | 3,519 | 12.0 % | 185,400 | 78.5 % | 1,338 | 15,947 |
| rd_mem2mem (DMA) | 7,052 | 24.0 % | 0 | 0.0 % | 482 | 0 |
| sum of the three | 24,871 | 84.7 % | 212,452 | 90.0 % | | |

wr_ofm: SRAM wr beats 0 (unfiltered 188,708), SRAM wr trans 17,641 (unfiltered 18,108).

Reading: yolo's SRAM reads are mostly IFM (78.5 %, 185,400 beats ≈ 11.6 beats per transaction; ≈ 0.41 SRAM beats per
`npu_active` cycle over 2 ports); its EXT reads split between weights (48.7 %) and DMA (24.0 %, the largest DMA share
so far — weights staged into the fast scratch). As for vww4, IFM volume is moderate while Stage 1 showed
`mac_stalled_by_ib` 34 %. Write side: beats 0, transactions 17,641 vs 18,108.

## mobilenet_v2_1.0_224_INT8 (boots 117–120) — `CHANNEL_FILTER_WORKS`

| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unfiltered | 301,217 | — | 672,948 | — | 23,373 | 61,383 |
| rd_weights | 195,310 | 64.8 % | 178,359 | 26.5 % | 12,325 | 13,807 |
| rd_ifm | 59,440 | 19.7 % | 443,635 | 65.9 % | 5,771 | 35,804 |
| rd_mem2mem (DMA) | 28,122 | 9.3 % | 0 | 0.0 % | 1,784 | 0 |
| sum of the three | 282,872 | 93.9 % | 621,994 | 92.4 % | | |

wr_ofm: SRAM wr beats 0 (unfiltered 401,443), SRAM wr trans 33,889 (unfiltered 35,664).

Reading: mobilenet reads weights from both ports (65 % of EXT, 27 % of SRAM reads) and IFM mostly from SRAM (66 %),
plus a visible IFM share over EXT (20 %, the largest so far). Write side: beats 0, transactions 33,889 vs 35,664.
