# S0-3 steps 2c/2d — the CPU−NPU gap is the TA stopping the NPU clock

Contract `evidence/s0_3_clk/contract.md` (frozen `3c71ef6`, before boot 137). Image `a7e9feeb`, boots 137–157, all
seven MLEK models, set B, 10 RUNs (8 measured) per boot; **21/21 boots, every RUN valid** (model mode incl.
`knobs_honoured`: the TA counter select read back at the CPM seam). Raw: `evidence/s0_3_clk/raw/`.
TA state: arms c1, c2 = **TA profile 1** (MLEK sys_dram_mid); arm d = **TA profile 3** (profile 1 with TA MODE bit 0 —
dynamic clocking — off; not an MLEK condition, never compared with MLEK).

## Preregistered outcome: **`CAUSE_CONFIRMED`** (`summary.json`, `verdicts.csv`)

| model | drift (c1, c2 vs s013) | 2c clock stop (e) | 2d MODE 0 |
| --- | --- | --- | --- |
| kws_micronet_m | DRIFT_OK | CLOCK_STOP_MATCHES (0.995) | MODE0_REMOVES_GAP |
| ad_medium_int8 | DRIFT_OK | CLOCK_STOP_MATCHES (0.997) | MODE0_REMOVES_GAP |
| vww4_128_128_INT8 | DRIFT_OK | CLOCK_STOP_MATCHES (0.998) | MODE0_REMOVES_GAP |
| yolo-fastest_192_face_v4 | DRIFT_OK | CLOCK_STOP_MATCHES (0.999) | MODE0_REMOVES_GAP |
| mobilenet_v2_1.0_224_INT8 | DRIFT_OK | CLOCK_STOP_MATCHES (1.000) | MODE0_REMOVES_GAP |
| rnnoise_INT8 | DRIFT_OK | descriptive | descriptive |
| wav2letter_pruned_int8 | DRIFT_OK | descriptive | descriptive |

`e` is below 1 only by the scale `k` (1.0003–1.0088): the TA window is wider than the CPU window by the TA reads
themselves (~470 cycles), so `k` slightly overstates the clock ratio (contract, limits).

## Descriptive — `POST_HOC_DESCRIPTIVE` (medians of 8 measured RUNs, cycles)

| model | c1 NPU | c1 CPU | c1 MCLK_OFF (SRAM / EXT) | d NPU = d CPU |
| --- | --- | --- | --- | --- |
| kws | 93,790 | 102,040 | 8,243 / 8,243 | 96,431 |
| ad | 148,542 | 168,930 | 20,279 / 20,279 | 161,195 |
| rnnoise | 53,030 | 53,030 | 0 / 0 | 53,306 |
| vww4 | 237,887 | 268,966 | 31,080 / 31,080 | 262,553 |
| yolo | 450,836 | 591,544 | 140,506 / 140,506 | 572,624 |
| mobilenet | 1,451,284 | 1,789,786 | 338,466 / 338,466 | 1,707,701 |
| wav2letter | 4,134,879 | 4,146,686 | 11,809 / 11,809 | 4,135,358 |

1. **Exact, per RUN.** In arm c1, in all 56 measured RUNs of all seven models, both TAs' `MCLK_OFF` count equals
   `infer_cpu − infer_npu` to the cycle (rnnoise: 0 = 0; wav2letter's small gap too). Both TAs report the same count:
   they see one NPU clock.
2. **Without dynamic clocking the gap is 0** in every RUN of every model (arm d), and no clock-off cycle is counted.
3. **c2:** TA root-clock `CYCLES` = CPU cycles + ~470, `MCLK_ON` = NPU cycles + ~468 (the TA-read overhang), i.e. the TA
   root clock runs at the CPU clock and `MCLK_ON` is the NPU-counted time.
4. **Arm d is shorter in wall time than profile 1** (e.g. mobilenet 1,707,701 vs 1,789,786) but longer in NPU cycles:
   without clock stopping the NPU waits on the real FPGA memory and counts the wait. Arm d therefore does not
   emulate SYS_DRAM_Mid; its numbers describe FI101 memory, not the MLEK condition.
5. **OFM** mismatch counts are identical across c1, c2 and d per model (kws, ad, mobilenet, rnnoise exact; vww4, yolo,
   wav2letter the known differences against TFLite goldens, MLEK goldens pending): profile 3 did not change results.
6. **Profile 2 (step 2a) is explained too:** zero emulated latency can never be met by real memory, so the TA stops the
   NPU clock more — NPU cycles fall while wall time grows. Not measured here (no counter in 2a), consistent with it.

## What this means for the purpose (Stage 2 cost clock)

The S0-3 gap is not a measurement fault: on FI101 with MLEK's TA configuration, the TA stops the NPU clock whenever the
FPGA memory is slower than the emulated SYS_DRAM_Mid, so the NPU sees the emulated timing. NPU `PMCCNTR` (and
`npu_active`) is the emulated system's clock, the one MLEK's board numbers are in; the CPU DWT span is FPGA wall time
including clock stops. **Stage 2 costs are counted in NPU cycles.** S0-3's rule "NPU span = CPU span within ±1 %" was the
wrong expectation for this platform; its FAIL is explained, not a defect of the runner.

## Fix made after the data (not a rule change)

`main()` in `host/analysis/s0_3_clk.py` crashed computing the descriptive `clock_off_over_gap` for rnnoise (gap 0 →
division by zero). It now computes that column only for models with a 2c verdict. The verdict functions and their tests
are unchanged; the outcome was produced by the frozen rules.
