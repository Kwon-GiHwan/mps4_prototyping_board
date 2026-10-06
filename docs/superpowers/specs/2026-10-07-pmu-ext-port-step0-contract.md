# Tier C step 0 — EXT AXI port reachability and `ext_*` counters (contract)

Frozen 2026-10-07, **before any data exists**. Amend by a new file. Plan:
`docs/superpowers/plans/2026-10-07-u85-pmu-real-model-plan.md`. Authorization: owner, 2026-10-07 ("진행하자").

## Question

The fixed U85 Convolution test's tensors live in DDR (`0x9000_0000`) and the vendor routes every
region through the SRAM AXI port (`MEM_ATTR0..3 = 0`). With the vendor's own switch `USE_AXI_EXT=1`
(sets MEM_ATTR bit 2 = EXT port on all four attributes), (Q1) does the same job still complete correctly
through the EXT port, and (Q2) which `ext_*` counters count?

## The only change

`Makefile.pmu_events EXT=1`: `Drivers/u85_driver/u85.c` (sha256 `bcd877bb…6bcf`, unedited) is compiled
with `-DUSE_AXI_EXT=1`; build dir `build_pmu_events_ext`, build id ASCII "PMEX" `0x504D4558`. Runner,
EVENTS mode, power hold, CPM seam: identical to Tier B boot 9 image.
Gate `RULE_EXT_ATTR`: the literal `"Enabling AXI EXT port testing"` is in the ELF iff EXT=1.

## Procedure

Same as Tier B (22 sets × 3 repeats, one boot), plus after **every** RUN:
`GET_RESULT(0x90020CC0, 0x100, run_sequence)` → `golden_ok = (crc == 0x27084C4C)`.

## Per-run validity

Tier B's nine terms **plus** `golden_ok`. An INVALID run is archived, never dropped or re-run.

## Reachability verdict (Q1) — closed set, campaign level

| verdict | condition |
| --- | --- |
| `EXT_REACHABLE` | ≥ 1 valid run (all ten terms) |
| `EXT_RUNS_WRONG_OUTPUT` | runs complete (rc 0) but no run has `golden_ok` |
| `EXT_UNREACHABLE` | campaign refused by `RULE_RUN_TRANSPORT` on set 1 rep 1 (hang / NACK) or rc ≠ 0 on every run |

## Event verdicts (Q2)

Tier B's closed set, unchanged. Preregistered comparison only: for each id, Tier B boot 9 verdict vs
step-0 verdict (same/different). No value is interpreted.

## Recovery

A hang is the expected failure mode of `EXT_UNREACHABLE`; MCC `REBOOT` recovers. Card restore +
postflight at the end as in Tier B.
