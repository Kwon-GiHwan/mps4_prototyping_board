# S0-3 steps 2c/2d — is the CPU−NPU gap the TA stopping the NPU clock? (frozen 2026-11-02, before boot 137)

Plan: `docs/plan/s0_3_resolution_plan.md` (2a′ → 2c; 2d added here). Owner 2026-11-02: "원인 알아낼 때 까지 진행해".
Purpose (unchanged since S0-3): decide which clock Stage 2 costs are counted in. S0-3 FAIL: the NPU `PMCCNTR` span
between the start seam and the CPM seam is shorter than the CPU DWT span over the same seams by 0–31 % (5/7 models,
TA profile 1, `results/fi101_stage0/`).

Hypothesis (from `results/fi101_s0_3_ta/ta_semantics.md`, MLEK core-platform `timing_adapter.h`): with TA MODE bit 0
("enable dynamic clocking to avoid underrun") set — as in TA profile 1 and 2 — the TA stops the NPU (DUT) clock when the
FPGA's real memory cannot meet the emulated latency; `PMCCNTR` does not count the stopped cycles, the DWT does.

## Measurement condition

- **TA state:** arms c1, c2 = **TA profile 1** (MLEK `ta_config_u85_sys_dram_mid`, the S0-3 condition); arm d = **TA
  profile 3** = profile 1 with MODE = 0 on both TAs (nothing else differs; `host/lib/pmwl.py`, `firmware/common/ta.c`,
  contract test). Profile 3 is not an MLEK condition; arm d numbers are never compared with MLEK.
- **TA counter select** (new PMWL word 28, written after the profile, read back after writing and at the CPM seam; a
  mismatch → `PMWL_KNOB_NOT_HONOURED` → RUN invalid). Events (`timing_adapter.h`): 19 `MCLK_OFF` "cycles when DUT clock
  is off", 18 `MCLK_ON`, 1 `CYCLES` "all cycles (root clock)".

| arm | TA profile | TA_SRAM counts | TA_EXT counts | word 28 | role |
| --- | --- | --- | --- | --- | --- |
| c1 | 1 | MCLK_OFF | MCLK_OFF | 0x1313 | 2c: clock-off cycles in the window |
| c2 | 1 | CYCLES | MCLK_ON | 0x1201 | root clock per CPU cycle (scale for c1); MCLK_ON vs NPU cycles (descriptive) |
| d | 3 | MCLK_OFF | MCLK_OFF | 0x1313 | 2d: dynamic clocking off |

- **Image** `a7e9feeb` (APP `a7e9feebd7f4…e813`, VECTORS `4c11ff9874f3…2bc8a`, DDR `81d37a219a6b…de98`), built from
  `d76acbd` (runner `2bb04bfa` + TA counter reads + profile 3; deterministic rebuild, gates PASS). TA PERFCNT is read
  just before the start-seam `PMCCNTR` read and just after the CPM-seam DWT/system-counter reads, so the TA window
  contains the NPU and CPU windows plus a few MMIO reads (tens of cycles, against gaps ≥ 8,000 cycles).
- **Blobs** = the fi101_s013 blob of each model (hashes in `evidence/fi101_s013`, re-verified on the board host) with
  word 28 set and, for arm d, word 27 = 3; nothing else (`make_clk_blob.py` asserts the differing bytes lie in words
  27–28: 4 bytes for c1/c2, 5 for d).

| model | s013 blob | c1 | c2 | d |
| --- | --- | --- | --- | --- |
| kws_micronet_m | `f11271cb6a2d` | `f52fb850b3af` | `10f1b5d8dfc7` | `96c8958f3cb4` |
| ad_medium_int8 | `55fa924c7e60` | `446b9cbd4de8` | `e31e9c8009d2` | `2249e72cc018` |
| rnnoise_INT8 | `5c3990a9c991` | `f809cfffbcad` | `d10b311e2ce7` | `1b8a31b07c49` |
| vww4_128_128_INT8 | `b7c15f01c4be` | `a0fca4154b53` | `a0f47c2b864b` | `87afb4c7b056` |
| yolo-fastest_192_face_v4 | `1f71e47582c5` | `d7432a1a4cfa` | `81ad931d0d63` | `481668166068` |
| mobilenet_v2_1.0_224_INT8 | `0d51cf9eaf86` | `deb037c70bfc` | `e8750cf1b966` | `666ce417960a` |
| wav2letter_pruned_int8 | `5b8c9d06dea1` | `293089bcb1f9` | `0d4fe6865f98` | `b1c2641b3d4b` |

- **PMU:** set B only (`ids.txt`: npu_active anchor + traffic), 10 RUNs, 2 warm-up → 8 measured RUNs per boot.
- **Boots** 137–157 (`plan.txt`): per model c1, c2, d; all seven MLEK models. Profile-1 reference = the model's
  fi101_s013 boot (94–100), all 56 measured RUNs.

## Rules (preregistered; `host/analysis/s0_3_clk.py`, tests `host/tests/test_s0_3_clk.py`, committed before boot 137)

Per RUN: `gap = infer_cpu − infer_npu`, `frac = gap / infer_npu`, `ratio = infer_npu / infer_cpu`. Validity as
fi101_s013 (model mode incl. `knobs_honoured`, `start_seam_once`) plus: the CPM-seam counter select equals the arm's
word 28 and both TA counts are present. Any invalid measured RUN in an arm → that arm unusable.

0. **Drift (does selecting a counter change the timing?)** c1 and c2 each against the s013 boot of the model: median
   `npu_active` inside the s013 [min, max] widened by 0.5 %, and median `frac` within ±10 % (relative) of the s013
   median for a model with s013 `frac` ≥ 0.05, within ±0.005 (absolute) otherwise. Either arm `DRIFT` / unusable →
   the model's 2c and 2d verdicts are `UNPROVEN`.
1. **Scale** `k` = median over c2 RUNs of `TA_SRAM CYCLES / infer_cpu` (TA root-clock cycles per CPU cycle).
2. **2c, per model with s013 `frac` ≥ 0.05** (kws, ad, vww4, yolo, mobilenet): `e` = median over c1 RUNs of
   `max(TA_SRAM MCLK_OFF, TA_EXT MCLK_OFF) / k / gap`.
   `CLOCK_STOP_MATCHES` 0.90 ≤ e ≤ 1.10; `CLOCK_STOP_EXCEEDS` e > 1.10; `CLOCK_STOP_PARTIAL` 0.10 ≤ e < 0.90;
   `CLOCK_STOP_ABSENT` e < 0.10.
3. **2d, same models**, arm d against the s013 boot: `MODE0_REMOVES_GAP` if every measured d RUN has `ratio` in
   [0.99, 1.01] (the S0-3 rule); else `MODE0_REDUCES_GAP` if median `frac` ≤ 0.5 × s013 median `frac`; else
   `MODE0_NO_EFFECT`.
4. **Overall:** `CAUSE_CONFIRMED` if all five models are (`CLOCK_STOP_MATCHES`, `MODE0_REMOVES_GAP`);
   `CAUSE_REJECTED` if all five are (`CLOCK_STOP_ABSENT`, `MODE0_NO_EFFECT`); `UNPROVEN` if any verdict is `UNPROVEN`;
   otherwise `MIXED`.
5. rnnoise, wav2letter (s013 `frac` < 0.05): descriptive only.

Descriptive (not verdicts), per model and arm: medians of `npu_active`, `infer_npu`, `infer_cpu`, `gap`, `frac`, beats,
both TA counts; `k`; `e`; c2 `MCLK_ON / k` against `infer_npu`; arm d clock-off counts.

## What each outcome means for the purpose

- `CAUSE_CONFIRMED`: the gap is TA clock stopping (emulation of SYS_DRAM_Mid on FPGA memory), not a measurement fault.
  `PMCCNTR` is the emulated system's clock, the one MLEK reports; S0-3's expectation "NPU span = CPU span" does not
  hold on FI101 with dynamic clocking. Stage 2 costs are counted in NPU cycles.
- `CAUSE_REJECTED`: the hypothesis is wrong; next candidates stay `CLKFORCE` (2b) and CPU/SRAM sharing.
- `MIXED`: reported per model; no conclusion beyond the per-model verdicts.

## Limits

- Arm d changes one TA register field on both TAs; the effect is not attributed to one port. Profile 3 may change NPU
  cycles; that is reported, never compared with MLEK.
- `MCLK_OFF`'s exact definition on FI101 is taken from core-platform `timing_adapter.h`; no FI101 document was found.
- The TA window exceeds the CPU window by the TA reads themselves; not corrected.
