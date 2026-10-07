# R1 gate report

Gates were frozen in `REMEASURE_CONTRACT.md` before this data existed.
A gate is PASS only at 35/35.

| gate | passed | verdict |
| --- | ---: | --- |
| `G1_artifact_reproduction` | 35/35 | **PASS** |
| `G2_total_cycles_match_frozen` | 35/35 | **PASS** |
| `G3_active_cycles_match_frozen` | 35/35 | **PASS** |
| `G4_repetition_identical` | 35/35 | **PASS** |
| `G5_memory_counters_present` | 35/35 | **PASS** |

```
R1_GATES: PASS
```

All five gates hold. The rebuild is byte-identical to the frozen
anchor (G1); the cycle counters this run observes are the frozen
values themselves (G2, G3), which is what licenses attaching the
recovered memory counters to those same cells; the two repetitions
agree exactly (G4); and all four U85 memory counters are present on
every cell (G5).

The loss was in the reader, not the measurement: `stage1.py` matched
`AXI0_*`/`AXI1_*`, which the U85 runner never emits. The same UART
block re-read with a parser that discovers the emitted set yields
`SRAM_*`/`EXT_*` on all 35 cells.
