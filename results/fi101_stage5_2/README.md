# Stage 5-2 — Performance vs Size at the same SRAM budget (boots 361–366, 2026-11-11)

Contract `evidence/stage5_2/contract.md` (frozen `caa7325`, before boot 361).

**Conditions.**
- **TA profile 1**, FI101 Ethos-U85 1024 MAC.
- Driver runner image `83398c7` (Dedicated_Sram, fast scratch 384 KiB in SRAM, arena in DDR), WAIT_WFE.
- Vela 5.0.0, requested budget 384 KiB for both strategies.
- Pass A + pass B, 1 warm-up + 4 measured RUNs each: 6 configs, 60 RUNs.

**Session.** All 6 boots `campaign exit=0`. Board restored to m6 (`RESTORE VERIFIED`), postflight PING of the restored image (state 1), card withdrawn (`POSTFLIGHT DONE: card withdrawn`; no `/dev/sdb1` afterwards). Session log `evidence/stage5_2/session.log` (checked: no credential).

**Files.**
- Raw data: `evidence/stage5_2/raw/`.
- Analysis: `python3 host/analysis/stage5.py evidence/stage5_2/raw evidence/stage5_2/workloads evidence/stage5/stage5_0.json results/fi101_stage5_2 5-2` → `summary.json`.

## Validity

- **6/6 configs VALID.** Every output PASS_EXACT:
  - kws and ad are byte-exact against the MLEK FI101 golden.
  - Cin 64 equals the CPU reference.
  - Each Size output equals its Performance output.
- **Base reproduction 3/3:** commonly constant counters equal the earlier measurement of the same DRWL (kws 9, ad 9, Cin 64 10 compared; 0 differ). The references are kws / ad from 5-1 boots 351 / 354 and Cin 64 from 4C-2b boot 350.

## Effective MACs — two corrections (verdicts unchanged)

**1. Before reporting (`93f26a3`).**
- `stage5.py` took each variant's MAC count from that variant's Vela compile (kws Size 15,580,852). The pair derived MAC +9.7 % from it.
- The fix used the base compile's count instead.

**2. After the owner review (2026-11-11).**
- The base compile's count is also a Vela count: kws 14,208,852 and ad 61,466,400.
- The project definition used by Stage 1/3 is the tflite N_MAC (`host/container/workload_meta.py`):
  - kws **15,556,352**
  - ad **62,346,720**
- The contract's "kws 14,208,852 … = the model's" was wrong (amendment A in the contract).
- `stage5.py` now takes effective MACs from the Stage 1 manifests (`EFFECTIVE`). An isolated operator uses its base compile's count, which equals the operator formula (Stage 4 gate B).
- Vela's per-configuration count stays in `vela_macs`.

**Checks.**
- Tests: 2 new tests, each RED before its fix.
- Mutation: 9 mutations in `evidence/stage5/mutate_stage5.py`, **9/9 RED**, restored by digest.
- Verdicts: `evidence/stage5_2/verdicts_unchanged.py` compares against the summaries before the corrections (5-1 at `caa7325`, 5-2 at `93f26a3`). Config, output, base-reproduction and pair verdicts and every counter are equal. The check fails on each of 3 seeded changes (verdict, counter, output).

**Only MAC-derived values changed.** Same definition as Stage 1:

| config | MACs / (1024 × MAC_ACTIVE) | MACs / (1024 × NPU_ACTIVE) | bytes / MAC (pass B, SRAM + EXT) |
| --- | ---: | ---: | ---: |
| kws Performance / Size | 26.91 % / 26.63 % | 16.65 % / 16.59 % | 0.058 / 0.058 |
| ad Performance / Size | 65.00 % / 65.00 % | 41.51 % / 41.84 % | 0.040 / 0.042 |
| conv Cin 64 Performance / Size | 75.00 % / 75.00 % | 14.22 % / 14.16 % | 0.061 / 0.064 |

Stage 1 gave kws 26.9 %, 16.7 %, 0.058 and ad 65.0 %, 41.7 %, 0.040.

## Results

The columns state the actual SRAM requirement and schedule, not the option name. NPU_ACTIVE and MAC/DPU are pass A medians; traffic is pass B. MAC/DPU RUN range is 0 everywhere.

| workload | strategy | SRAM used (Vela) | fast scratch / arena (B) | kernels | NPU_ACTIVE (range) | Δ A / Δ B (tol.) | verdict | MAC_ACTIVE | MAC_DPU_ACTIVE | MAC / NPU_ACTIVE | Vela NPU cycles | Vela MACs (separate; not used) |
| --- | --- | ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| kws | Performance | 89.5 KiB | 91,600 / 496 | 14 | 91,238 (1,889) | — | base | 56,450 | 49,495 | 61.9 % | 86,324 | 14,208,852 |
| kws | Size | 89.5 KiB | 91,600 / 496 | 14 | 91,580 (1,288) | +0.38 % / +0.26 % (1,889) | `UNRESOLVED` | **57,055** | 49,495 | 62.3 % | 89,791 | 15,580,852 |
| ad | Performance | 244.0 KiB | 249,856 / 1,024 | 14 | 146,670 (1,953) | — | base | 93,672 | 93,672 | 63.9 % | 140,277 | 61,466,400 |
| ad | Size | **300.8 KiB** | 308,064 / 1,024 | 14 | 145,511 (3,686) | −0.79 % / −1.12 % (3,686) | `UNRESOLVED` | 93,672 | 93,672 | 64.4 % | 140,277 | 61,466,400 |
| conv Cin 64 | Performance | 8.4 KiB | 8,576 / 92,160 | 2 | 24,310 (898) | — | base | 4,608 | 4,608 | 19.0 % | 16,709 | 3,538,944 |
| conv Cin 64 | Size | 9.3 KiB | 9,536 / 92,160 | 2 | 24,400 (852) | +0.37 % / +0.48 % (898) | `UNRESOLVED` | 4,608 | 4,608 | 18.9 % | 16,822 | 3,538,944 |

Effective MACs (project definition, tflite N_MAC) are kws 15,556,352, ad 62,346,720 and Cin 64 3,538,944. The "Vela MACs" column is Vela's own count per compile.

### Transfers (pass B medians; "changed" = beyond the tolerance rule)

| workload | SRAM rd beats | SRAM wr beats | SRAM rd trans. | EXT rd beats | EXT rd trans. | EXT wr beats |
| --- | --- | --- | --- | --- | --- | --- |
| kws | 22,664 → 22,631 (=) | 17,760 → 17,749 (=) | 3,337 → 3,337 | 15,815 → 15,804 (=) | 1,607 → 1,607 | 1 → 1 |
| ad | **70,538 → 77,814 (+10.3 %)** | **41,888 → 45,526 (+8.7 %)** | 4,971 → 5,495 (+10.5 %) | **44,084 → 40,111 (−9.0 %)** | 3,319 → 2,996 (−9.7 %) | 1 → 1 |
| conv Cin 64 | **4,288 → 4,768 (+11.2 %)** | 536 → 596 (+11.2 %) | 448 → 440 (−1.8 %) | 5,177 → 5,232 (+1.1 %) | **429 → 335 (−21.9 %)** | 3,456 → 3,456 |

## Observations (`OBSERVED`, these three workloads only)

- **No resolved whole-run difference between Size and Performance at 384 KiB.**
  - All three pairs are `UNRESOLVED`: the change lies inside the tolerance, and both passes point the same way.
  - This holds whether Size used the same SRAM (kws) or more (ad +56.8 KiB, Cin 64 +0.9 KiB).
  - `UNRESOLVED` means no difference was resolved in these RUNs. It does not mean the strategies are equivalent.
- **Size used more SRAM, or the same, never less.**
  - ad Size moved kernel 3's weights into the fast-scratch region as one stream. SRAM read and write beats rose by about 9–10 % and EXT read beats fell by 9 %.
  - In Cin 64 the single weight stream went with SRAM reads +11 % and EXT read transactions −22 %.
  - These transfer shifts are recorded. They did not show up as a resolved time change.
- **kws Size: MAC_ACTIVE rose by 605 cycles (+1.07 %), exactly and in every RUN; MAC_DPU_ACTIVE did not change.**
  - The compute configuration per kernel is identical (5-0).
  - The only differences are the weight-stream lengths and weight DMA of 2 kernels (1,712 → 1,664 and 9,600 → 9,472 B).
  - Why the MAC activity count changed is not established. It is recorded, not interpreted.
- **Vela's NPU-cycle estimate:**
  - kws +4.0 %, Cin 64 +0.7 %, ad 0.
  - The board shows no resolved change in any of the three.
  - Vela's larger MAC count for kws Size is its own accounting. It is not used for any efficiency.

## Not generalised

- **mobilenet**, the one `SCHEDULE_CHANGED` Size case (377 → 328 KiB, 208 → 93 kernels), was not measured. Its effect is `UNMEASURED`.
- **vww4, yolo, wav2letter, conv/dw base and fc:** Size gave an identical execution payload, so there was nothing to measure.
- Results hold for the 384 KiB budget only. No other budgets were combined with Size.
