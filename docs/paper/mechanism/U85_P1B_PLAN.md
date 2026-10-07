# P1-B — targeted cross-memory per-layer profiling (frozen before acquisition)

Manager decision (2026-09-02): P0 ACCEPTED/FROZEN, P1-A ACCEPTED/FROZEN
(with the NOT_SEPARATED amendment), **P1-B GO — TARGETED**. dnn_s P1-B
NOT_AVAILABLE (profiler fail-closed on shape_signature); yolo P1-B HOLD;
P2/P3/P4 and narrative HOLD.

## Scope

```
workloads   rnnoise_INT8  (whole-model reversal representative)
            vww4_128_128_INT8  (local regressions inside whole-model improvement — control)
MAC         256, 512   (P0-convention system-config: Low@256, Mid_512@512)
modes       NEW profiled acquisition: Sram_Only, Shared_Sram
            Dedicated_Sram: REUSED from frozen P0 profiled evidence
            (U85_MECH_P0D2 root) after exact identity verification —
            vela/instr/AXF SHA-256 against the frozen records
new cells   2 × 2 × 2 = 8 profiled cells;  runs = 8 × 3 fresh FVP = 24
analysis    12 profiled cells (8 new + 4 frozen-P0 reuse)
```

Instrumentation identical to P0-D2 (one-hot NPU_OP_IRQ + irq-history
driver v3, qualified at P0-C); artifacts are the hash-gated P1-A Vela
outputs for SO/SH. Repetition contract unchanged: 3 fresh runs,
full-vector exact equality; output CRC must equal the frozen P1-A clean
CRC of the same cell.

## Preregistered questions (no new aggregate metrics)

- Q1 rnnoise: do the logical op/groups producing the 256→512 regression
  reappear identically across Sram_Only / Shared_Sram / Dedicated_Sram?
- Q2 rnnoise: does the DISTRIBUTED regression structure persist across the
  three modes, or does a different op set produce it in some mode?
- Q3 vww4: do the P0-observed local per-op regressions exist in the other
  memory modes even though the whole model always improves?
- Q4 are there logical ops whose direction flips REGRESS↔IMPROVE with
  memory mode?
- Q5 alongside such changes, how do UBLOCK / BLOCK_CONFIG / tile /
  placement / pass-structure booleans differ?

## Preregistered derived output

Per workload, ONE common attribution partition across all six profiled
cells (union-find joining source ops that share a service window in ANY
mode×MAC cell; source-table equality across modes is a gate). The primary
deliverable is the direct table — per logical group: Δ(256→512) under
SO / SH / DS with direction, raw deltas only:

```
logical group    SO Δ      SH Δ      DS Δ
group_k          +....     +....     +....
```

No Jaccard/overlap-percent/contribution-ratio or any new aggregate metric.
Interpretation vocabulary unchanged (ASSOCIATED_WITH / CONSISTENT_WITH /
NOT_SEPARATED / NOT_EVALUABLE).

## Order

disk cleanup (done, CLEANUP_MANIFEST_20260902) → this plan freeze →
identity verification of reused DS cells → 8-cell acquisition →
per-mode analyzer v3.1 + cross-mode group table → freeze → STOP for
manager review.
