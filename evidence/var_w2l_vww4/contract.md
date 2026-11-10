# wav2letter instrumented-build shift (W) and vww4 boot-to-boot spread (V) (frozen 2026-11-10, before boot 308)

Owner request 2026-11-10 (item 2): separate the cause of wav2letter's NPU_ACTIVE difference between stock MLEK and the
instrumented MLEK build; check vww4's boot-to-boot NPU_ACTIVE spread and its difference from MLEK; do not change existing
rules to fit results; keep what is not shown UNPROVEN. **TA profile 1 everywhere** (MLEK's own set-up on MLEK and the
driver runner; profile 1 on the legacy runner). FI101 Ethos-U85 1024 MAC. Analysis `host/analysis/var_w2l_vww4.py`
(dataset list fixed in the code), tests `host/tests/test_var_w2l_vww4.py` (7 mutations RED).

## What is known before any new boot (equivalence C, `results/runner_mlek_equivalence/equiv_c/`)

wav2letter, MLEK input, one inference per boot: stock B1–B3 ACTIVE 4,132,211 / 4,133,890 / 4,133,959; instrumented
B1–B3 4,130,708 / 4,131,099 / 4,131,728 (all three below all three stock boots; by chance alone that order has
probability 1/20); legacy runner RUN range 4,129,476–4,133,411 (16 RUNs, one boot). Beats identical in all six boots.
The two builds differ in boot.bin/bram.bin (instrumented: three more profiler counters, `mlek_profiler_events.py`); the
model (ddr.bin) is the same file. Captures were taken stock first, then instrumented, in separate sessions.

## W — wav2letter, MLEK stock vs instrumented, interleaved

Hypotheses: (Wa) the instrumented build changes the NPU's run (build effect); (Wb) the C difference is session/boot
variation (the three stock and three instrumented boots were taken in separate blocks).

Boots 317–324 (`plan_mlek.txt`): S E E S E S S E (each variant's mean position 4.5), images
`evidence/equiv_c/mlek/wav2letter_pruned_int8/{stock,events}` (stock boot `9dc61053`/bram `4e112520`; instrumented
`5dc56b13`/`5c5728c0`; ddr `e57a6546`, images.txt `af688281`), re-checked on the board host before deploy. One
deploy_mlek → app-UART capture (240 s) → restore_mlek per boot, all inside one owner sudo session.

| outcome | rule (the 4 new stock vs the 4 new instrumented boots; every capture valid: one profile, both TA lines, program end) |
| --- | --- |
| W1 `SHIFT_REPRODUCED` | every instrumented ACTIVE below every stock ACTIVE (chance 1/70 without an effect) |
| W1 `SHIFT_REVERSED` | every instrumented ACTIVE above every stock ACTIVE |
| W1 `NO_SHIFT` | neither, and the medians within the larger of the two ranges (the M3 rule) |
| W1 `UNPROVEN` | anything else, or a capture missing / invalid |
| W2 `BEATS_FIXED` / `BEATS_DIFFER` | the four beats of all eight new boots equal stock B1's exactly |

Reading fixed now: `SHIFT_REPRODUCED` → (Wa): the instrumented build lowers wav2letter's ACTIVE; which part of the build
(counter selection or code/layout) is **not** separated by W (UNPROVEN). The driver runner's D6 on wav2letter (sets with
and without MAC/AO events, one image) is reported next to it as the event-selection evidence on another execution
path, with its resolution (D6 tolerance ≥ 1 %, far above 2,791 cycles = 0.07 %) stated. `NO_SHIFT` → (Wb) for the C
difference. Either way the frozen equivalence-C verdict (wav2letter M4 `UNPROVEN`) is not changed; W3 below is reported
as supplementary only.

W3 (supplementary, labelled as such): `equiv_c.model()` with stock = old 3 + new 4 and instrumented = old 3 + new 4,
runner = legacy C-d and = driver m7 (boot 314).

## V — vww4 boot-to-boot

Datasets (NPU_ACTIVE, all measured RUNs of all sets per boot):
- MLEK: equivalence C stock B1–B3 and instrumented B1–B3 (the instrumented build passed the inertness check for vww4) = 6
  boots, one inference each; stock-only reported too.
- Driver runner, MLEK input: boots 310, 315, 316 (`evidence/driver_m7/`).
- Legacy runner, seed-1 blob `b7c15f01` (same blob in every boot): boots 97, 192, 196, 281, 287; MLEK input: boot 306.

| outcome | rule |
| --- | --- |
| V2 `DRIVER_WITHIN_MLEK_RANGE` / `DRIVER_OUTSIDE_MLEK_RANGE` | every driver boot median inside [min, max] of the 6 MLEK boots / not; `UNPROVEN` if a driver boot or an MLEK boot is missing |

Descriptive (not judged): per environment the boot medians, their range, the within-boot RUN range; the driver's first
RUN after boot (set 1, rep 1, a warm-up RUN — MLEK's number is a first inference after boot); driver − MLEK and
legacy (MLEK input) − MLEK medians in %. **V3** "legacy C-d median inside the MLEK 6-boot range" is computable from data
that already exist (it is: 235,892 ≤ 236,774) — reported as POST_HOC_DESCRIPTIVE, not as an outcome.

## Limits

- No new MLEK vww4 boots; no new legacy-runner boots; no build variant that separates the counter selection from the
  code layout (would need a new MLEK build and a separate approval).
- One input per model (MLEK's for MLEK and driver, seed-1 for most legacy vww4 boots: cross-input, descriptive only).
