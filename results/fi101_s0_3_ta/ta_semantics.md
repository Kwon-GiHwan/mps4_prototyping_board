# S0-3 step 2a′ — what the TA register values mean (2026-11-02, no board)

Question: is TA profile 2 ("pass-through") really "no limits, no added latency, full speed", and does the TA documentation
say anything that bears on the S0-3 gap (NPU `PMCCNTR` span shorter than CPU DWT span over the same seams)?

Sources (container `benchmark-runner`, read only):
- `S` = MLEK `dependencies/core-platform/drivers/timing_adapter/include/timing_adapter.h` + `src/timing_adapter.c`
  (core-platform `02d02901842f`, 2025-11-24).
- `D` = MLEK `docs/sections/timing_adapters.md`.
- `C` = MLEK `scripts/cmake/timing_adapter/ta_config_u85_sys_dram_mid.cmake` (profile 1's origin).
No FI101 / MPS4 application note was found (local, board host, container). Nothing here was measured.

## Register meanings (as documented)

| register | profile 1 SRAM / EXT | profile 2 | documented meaning | profile 2 = "no limit"? |
| --- | --- | --- | --- | --- |
| MAXR, MAXW, MAXRW | 8,8,0 / 0,32,0 | 0,0,0 | max pending reads / writes / both, **0 = infinite** (S, D) | yes |
| RLATENCY, WLATENCY | 32,32 / 500,250 | 0,0 | **minimum** latency in clock cycles, AVALID→RVALID / WVALID&WLAST→BVALID (S, D) | yes: no added minimum |
| PULSE_ON, PULSE_OFF | 3999,1 / 4000,1000 | 0xFFFF, 0 | cycles addresses let through / **blocked** (S, D) | yes: never blocked |
| BWCAP | 4000 / 3750 | 0 | max words per pulse cycle, **0 = infinite** (S says 64-bit words, C and D say 128-bit for U85) | yes |
| MODE | 1 / 1 | **1** | bit 0: S and C "**1 = enable dynamic clocking to avoid underrun**"; D "1 = latency-deadline QoS throttling of read versus write". Bits 1–3 random reordering (0 = off). Bits 11–4 frequency scale, **0 = full speed** | limits off, full speed — **but bit 0 (dynamic clocking) stays on in both profiles** |
| PERFCTRL / PERFCNT | 0 | 0 | event select for the TA's own 32-bit counter; 0 = off | — |

So the limit fields of profile 2 do mean "no limits, no added latency, full speed". The name "pass-through" is still
misleading: with MODE bit 0 set the TA is not a bypass, it emulates a zero-latency memory.

## What bears on the S0-3 gap

1. **The TA can stop the NPU clock.** PERFCTRL events (S): `TA_PERFCTRL_MCLK_ON` = 18 "Count cycles when DUT clock is on",
   `TA_PERFCTRL_MCLK_OFF` = 19 "Count cycles when DUT clock is off", `UNDERRUN_R` = 2 / `UNDERRUN_B` = 3 "Unable to meet
   RLATENCY / WLATENCY deadline", `CYCLES` = 1 "Count all cycles (root clock)". The DUT behind an NPU TA is the NPU.
2. **MODE bit 0 is set in both profiles.** Step 2a varied the limit/latency fields only; the dynamic-clocking bit was never
   a variable. `TA_NOT_EXPLAINS` therefore means "the limit and latency values do not remove the gap", not "the TA is
   not the cause". The contract's wording "one variable: the TA state" overstated what was varied; this is a limit of
   that contract, recorded here, the contract itself is not edited.
3. **Two Arm sources describe bit 0 differently** (S/C: dynamic clocking; D: QoS throttling). Which is right on FI101 is
   not established.

## Hypothesis (not tested) — `POST_HOC_DESCRIPTIVE`

With dynamic clocking on, when the FPGA's real memory cannot meet the emulated latency deadline, the TA stops the NPU
clock until it can, so the NPU sees the emulated timing. `PMCCNTR` runs on the NPU clock and does not count the stopped
cycles; the CPU DWT does. This fits every observation so far:
- the gap exists only when there is traffic the real memory cannot serve on time, and ranks exactly with SRAM write beats
  (`results/fi101_s0_3_correlation/`);
- profile 2 asks for zero latency, which real memory can never meet: NPU-counted cycles fall (the NPU sees ideal memory)
  while the gap grows in all seven models;
- MLEK's board numbers ("FI101 + emulated SYS_DRAM_Mid") are NPU-clock numbers and our profile-1 NPU cycles reproduce them.

Not explained by it: why CPU elapsed time *grows* under profile 2 in 6/7 models (clock stop/restart overhead? the
deadline logic itself?).

## Consequence for the purpose of S0-3 (choosing the Stage 2 cost clock)

If the hypothesis holds: NPU `PMCCNTR` is the clock of the emulated system, which is what MLEK reports and what Stage 2
should use for MLEK-comparable costs; the CPU span is FPGA wall time including TA clock stops. S0-3's expectation
"NPU span = CPU span" would be the wrong expectation on FI101 with dynamic clocking, not a measurement fault.

## Direct test (proposed, needs a firmware knob and a contract)

Program TA PERFCTRL = 19 (`MCLK_OFF`) on both TAs, zero PERFCNT at the start seam, read it at the CPM seam, profile 1,
all seven models. Prediction: `MCLK_OFF` ≈ `infer_cpu − infer_npu` per RUN. `PERFCTRL = 1` (root-clock cycles) also gives
an elapsed-time count independent of the CPU (bears on step 3). Selecting a counter is not documented to change TA timing
— this is an assumption the contract must state and the drift arm must check. Cheaper and more direct than 2b
`CLKFORCE` (an NPU register write, which changes the condition) — reorder 2b after it.
