# Stage 5-1 — SRAM workspace budget in Dedicated_Sram (boots 351–360, 2026-11-10/11 UTC board clock)

Contract `evidence/stage5/contract.md` (frozen `f89c672`, before boot 351); plan `docs/plan/stage5_plan.md`.

**Conditions.**
- **TA profile 1**, FI101 Ethos-U85 1024 MAC.
- Driver runner image `83398c7` (memory configuration Dedicated_Sram: fast scratch 384 KiB in SRAM, arena in DDR).
- Vela 5.0.0, Performance; the budget `--arena-cache-size` was 384 KiB (ini), 64 KiB or 0.
- Pass A + pass B, 1 warm-up + 4 measured RUNs each = 100 RUNs.

**Session.** All boots `campaign exit=0`. Board restored to m6 (`RESTORE VERIFIED`), postflight PING of the restored image (state 1), card withdrawn.

**Files.**
- Raw data: `evidence/stage5/raw/`.
- Compile classification: `stage5_0_classification.csv`.
- Analysis: `python3 host/analysis/stage5.py evidence/stage5/raw evidence/stage5/workloads evidence/stage5/stage5_0.json results/fi101_stage5` → `summary.json`.

## Validity

- **10/10 configs VALID.**
- **Outputs:** every output is PASS_EXACT. kws and ad are byte-exact against the MLEK FI101 golden; the isolated operators match the CPU reference. Every variant's NPU output equals its base's NPU output.
- **Base reproduction:** passed for all 4 workloads. Commonly constant counters equal the earlier measurements (kws 9, ad 9, dw 11, conv 10 compared; 0 differ), and the earlier RUNs had matched the same golden.
- **Compile scope:** every 5-1 variant is `SCHEDULE_CHANGED` in the 5-0 classification. The results below are whole-configuration effects of the budget change, not pure placement effects.

## Results (pass A medians; NPU_ACTIVE change pass A / pass B; MAC/DPU RUN range 0 unless noted)

| workload | budget | SRAM used (Vela) | kernels | NPU_ACTIVE (range) | Δ A / Δ B | verdict | MAC_ACTIVE | MAC_DPU_ACTIVE | MAC / NPU_ACTIVE | SRAM rd / wr beats | EXT rd / wr beats | Vela NPU / total cycles |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| kws | 384 KiB | 89.5 KiB | 14 | 91,770 (860) | — | base | 56,450 | 49,495 | 61.5 % | 22,664 / 17,760 | 15,815 / 1 | 86,324 / 102,248 |
| kws | 64 KiB | 58.8 KiB | 19 | 96,719 (2,442) | +5.4 % / +6.6 % | `NOT_PROPORTIONAL_TO_MAC` | 56,450 | 49,495 | 58.4 % | 21,192 / 16,439 | 17,633 / 1,126 | 92,095 / 105,195 |
| kws | 0 | 0 | 13 | 114,021 (1,099) | **+24.2 % / +25.4 %** | `NOT_PROPORTIONAL_TO_MAC` | 56,447 | 49,495 | 49.5 % | 0 / 0 | 36,358 / 15,674 | 78,730 / 130,003 |
| ad | 384 KiB | 244 KiB | 14 | 145,991 (1,584) | — | base | 93,672 | 93,672 | 64.2 % | 70,538 / 41,888 | 44,084 / 1 | 140,277 / 148,328 |
| ad | 64 KiB | 59.8 KiB | **66** | **376,999** (1,703) | **+158.2 % / +158.3 %** | `NOT_PROPORTIONAL_TO_MAC` | 94,824 | 94,680 | 25.2 % | 51,482 / 28,779 | 159,245 / 13,825 | 345,342 / 443,065 |
| ad | 0 | 0 | 13 | 234,881 (2,456) | **+60.9 % / +60.4 %** | `NOT_PROPORTIONAL_TO_MAC` | 91,368 | 91,368 | 38.9 % | 0 / 0 | 113,811 / 41,299 | 139,553 / 269,222 |
| dw_base | 384 KiB | 3.2 KiB | 2 | 159,780 (42) | — | base | 31,752 | 31,752 | 19.9 % | 1,212 / 202 | 31,556 / 28,224 | 112,225 / 944,999 |
| dw_base | 0 | 0 | 1 | 160,576 (891) | +0.5 % / +0.5 % | `UNRESOLVED` (inside tolerance) | 31,752 | 31,752 | 19.8 % | 0 / 0 | 32,500 / 28,224 | 111,652 / 944,999 |
| conv_base | 384 KiB | 3.9 KiB | 2 | 21,587 (564) | — | base | 2,304 | 1,152 | 10.7 % | 2,016 / 252 | 1,437 / 3,456 | 16,660 / 24,999 |
| conv_base | 0 | 0 | 1 | 21,679 (682) | +0.4 % / +2.8 % | `UNRESOLVED` (inside tolerance) | **1,728** | **864** | 8.0 % | 0 / 0 | 2,254 / 3,456 | 16,004 / 18,750 |

## Observations (`OBSERVED`, these configs only; whole-configuration effects)

- **A smaller budget was not uniformly costly.**
  - **kws:** monotone in the budget — 64 KiB +5–7 %, 0 +24–25 %.
  - **ad:** 64 KiB cost much more than 0 (+158 % vs +61 %). Vela split ad into 66 kernels at 64 KiB against 14 at 384 KiB and 13 at 0.
  - **dw and conv:** no resolved time change at 0.
- **The compute activity barely moved for the models.**
  - kws MAC/DPU are unchanged, except MAC_ACTIVE −3 at 0.
  - ad MAC_ACTIVE moved by −2.5 % (at 0) and +1.2 % (at 64 KiB), with DPU likewise.
  - The MAC share of NPU_ACTIVE fell as NPU_ACTIVE rose.
- **conv_base at budget 0 compiled to one kernel instead of two.** MAC_ACTIVE dropped 2,304 → 1,728 and DPU 1,152 → 864, while NPU_ACTIVE did not change beyond the tolerance. This is another case where the compute activity and the whole-run cost moved differently.
- **Transfers moved to the EXT port when the SRAM budget shrank.**
  - At 0, all SRAM beats became 0 and EXT read beats rose (kws ×2.3, ad ×2.6, conv ×1.6, dw +3 %).
  - EXT writes appeared for the models (kws 15,674, ad 41,299, from 1).
  - These are co-occurring changes. The time changes are **not** attributed to bandwidth or memory waiting.
- **Vela's estimates:** Vela's total-cycle estimate (field `cycles_total`, NPU cycles, Vela's model of the network) rose in the same configs where NPU_ACTIVE rose (kws 0, ad 64 KiB, ad 0).
  - The size of the rise did not match: e.g. ad 64 KiB Vela total ×3.0 vs board ×2.58; kws 0 Vela ×1.27 vs board ×1.24.
  - The dw/conv estimates moved without a resolved board change.
  - Ratios are described, not read as estimation errors.

## Not generalised

- **Changed in 5-0 but not measured (scope):** effect `UNMEASURED`, not generalised from kws/ad.
  - rnnoise at 0
  - vww4, yolo, mobilenet, wav2letter at 64 KiB and 0
  - conv Cin 64 at 0
- **Not run because the execution payload equals the base:** dw/conv/Cin 64/rnnoise at 64 KiB; fc at both budgets.

## 5-2 — minimal comparison proposal (not started; needs a decision)

**How Vela 5.0.0 treats Size.** For U85 Vela uses its regor backend and passes both `optimize` and `arena_size_limit` (= the SRAM budget) to it (`vela.py` `get_compiler_config`). The `--help` text "Size … does not use arena-cache-size" describes the legacy scheduler, not this path; the budget still limits Size. Evidence from 5-0: Size + budget 0 used 0 SRAM. The regor scheduler is a compiled binary, so its policy is described from the compile results only.

**5-0 facts** at the same budget (384 KiB, Size vs Performance):

| workload | class | SRAM used | kernels | Vela NPU cycles | note |
| --- | --- | --- | --- | --- | --- |
| kws | MEMORY_ONLY | 89.5 → 89.5 KiB | 14 → 14 | 86,324 → 89,791 | Vela's MAC count 14.21 M → 15.58 M with identical compute registers (Vela accounting, not interpreted) |
| ad | MEMORY_ONLY | 244 → **301** KiB | 14 → 14 | 140,277 → 140,277 | Size used **more** SRAM |
| conv Cin 64 | MEMORY_ONLY | 8.4 → 9.3 KiB | 2 → 2 | 16,709 → 16,822 | |
| mobilenet | SCHEDULE_CHANGED | 377 → 328 KiB | 208 → 93 | 1,737,984 → 1,644,334 | |
| vww4, yolo, wav2letter, conv/dw base, fc | EXEC_IDENTICAL | | | | nothing to measure |

At budget 0, Size and Performance gave the same payload for mobilenet but different payloads for kws, ad and conv Cin 64.

**Proposal:**
- Size vs Performance at the default budget (384 KiB), one axis.
- Measure only where the payload differs: kws, ad, conv Cin 64. Each Size config with its Performance base re-measured in the same session: 6 configs × 2 passes × 5 = 60 RUNs.
- Optional: mobilenet base + Size (+2 configs, 20 RUNs; longer upload) as the one `SCHEDULE_CHANGED` case.
- Rules as 5-1.

**How to report it:** "Size" must not be read as "less SRAM". In ad it used more SRAM, so each pair would be reported by its actual SRAM requirement and schedule, not by the option name.
