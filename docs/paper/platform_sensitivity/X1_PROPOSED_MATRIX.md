# X1 proposed matrix — PLAN ONLY (not authorized, not run)

Proposed at the end of X0 per the instruction. **No X1 cell was executed.**

## Matrix

```
U55 : common workloads × MAC {32,64,128,256} × SSE {300,310}
      (6,6,6,7 workloads per MAC)                       = 50 cells
U65 : 7 workloads × MAC {256,512} × SSE {300,310,315}   = 42 cells
                                              TOTAL     = 92 cells
```

Clean whole-model arms only. Under the existing fresh-process/exact-equality
convention (3 runs per cell) this is 276 simulator runs; the repetition
contract must be re-qualified for these platforms before being imposed, per
the standing acquisition rules.

## Canonical compiler memory tuple (one per NPU, chosen before any measurement)

| NPU | memory mode | system config | why |
| --- | --- | --- | --- |
| U55 | `Shared_Sram` | `Ethos_U55_High_End_Embedded` | `Dedicated_Sram` fails to compile for U55 on this stack; `Shared_Sram` is the tuple already used by every frozen U55 cell, so X1 inherits an artifact-identical baseline across both platforms |
| U65 | `Dedicated_Sram` | `Ethos_U65_High_End` | supported on all three U65 platforms, and the tuple used by every frozen U65 cell, giving byte-identical artifacts across SSE-300/310/315 |

Selection rule satisfied: supported on all compared platforms, maximises exact
NPU-artifact reuse, and chosen from capability + frozen-provenance grounds
only — **no performance observation entered this choice**. X1 varies platform
only; it is not a memory-mode sweep.

## Comparison classes carried into X1

```
CLASS A  U65 {256,512}  SSE-310 ↔ SSE-315     same TA state (both TA_OFF)
CLASS B  U55 {32..256}  SSE-300 ↔ SSE-310     TA state differs
         U65 {256,512}  SSE-300 ↔ SSE-310/315 TA state differs
```

Class B results must be reported as **subsystem + timing-model sensitivity**,
never as a Corstone hardware effect. Class A is the only pair on this stack
where the TA axis is held constant.

## Metrics — registered for reuse, none computed in X0

Reuse the already-frozen definitions verbatim: workload ranking (Spearman),
adjacent scaling efficiency, cumulative scaling efficiency, saturation verdict
(incremental efficiency < 0.50), geomean-normalized relative workload cost.

Raw cycles may be recorded within a platform. Prohibited: cross-platform
raw-cycle ratios, "% faster/slower", cross-platform error metrics. Outcome
vocabulary: `CONSISTENT_ACROSS_TESTED_PLATFORM_TIMING_CONDITIONS` /
`PLATFORM_TIMING_SENSITIVE`.

No new robustness score is proposed. If one is later desired it must be
preregistered before touching X1 data; nothing here is registered beyond the
list above (`PROPOSED_NOT_REGISTERED`: none).

## Prerequisite noted, not performed

For the 3 `NOT_YET_QUALIFIED` portability cells (wav2letter/U55 @32/64/128,
non-executable on both platforms) nothing is required — they are excluded from
X1 by the executability intersection. For all other candidate cells,
same-artifact portability is `ESTABLISHED` from frozen evidence, so the
lightweight `X1-Q` portability qualification proposed by the manager is **not
required** on current evidence. It remains available if X1 later adds a cell
outside the frozen universe.

## Scaling-ladder caveat

`wav2letter_pruned_int8` has no complete U55 ladder (non-executable below MAC
256 on both platforms), exactly as in the frozen sweep. Its U55 scaling
metrics remain `NOT_AVAILABLE`; it contributes to ranking at MAC 256 only.
