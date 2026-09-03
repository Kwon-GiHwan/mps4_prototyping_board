# X1 analysis contract — frozen BEFORE any formal acquisition

Authorized by the manager decision of 2026-09-03 (X0 ACCEPTED/FROZEN =
`78018ac`; X1 GO). Goal: measure platform/timing sensitivity of MAC-scaling
**structure** using the SAME NPU artifact across supported Corstone FVPs.
No per-layer profiling. No memory-mode sweep. No cross-platform absolute
performance claim.

## 1. Formal universe (X0-frozen tuples; not changed after seeing results)

```
U55   memory-mode Shared_Sram      system-config Ethos_U55_High_End_Embedded
      platforms SSE-300, SSE-310   MAC {32,64,128,256}
      workloads = X0 common executable set per MAC (6,6,6,7)      → 50 cells
U65   memory-mode Dedicated_Sram   system-config Ethos_U65_High_End
      platforms SSE-300, SSE-310, SSE-315   MAC {256,512}
      workloads = X0 common 7-workload set                        → 42 cells
                                                        TOTAL     → 92 cells
```

Workloads may not be added or removed after observation.

## 2. Artifact identity (hard gate)

Each (workload, npu, mac) compiles **one** Vela artifact, whose SHA-256 must
equal the X0/frozen-matrix hash for **every** platform in its comparison set.
The identical artifact file is then built into each platform's firmware.

```
VELA_ARTIFACT_IDENTICAL              required TRUE per comparison pair
host firmware                        FIRMWARE_PLATFORM_SPECIFIC_BUT_NPU_ARTIFACT_IDENTICAL
hash mismatch                        STOP that comparison; classify identity failure;
                                     never silently rebuild or recompile
```

The phrase "the same binary" is not used.

## 3. Acquisition semantics

Pre-campaign binding: X0 artifact hashes, FVP executable + Fast Models
version, platform parameter namespace (`ethosu.num_macs` for SSE-300/310;
`mps4_board.subsystem.ethosu.num_macs` for SSE-315), TA state.

Determinism is **qualified on a small representative subset first**. Only if
the full metric vector repeats exactly does the formal contract apply:

```
3 independent fresh FVP processes per cell, stock inference exactly once each
exact equality of the canonical measurement vector required
no averaging, no median, no tolerance introduced after data
```

If exact equality fails → STOP before inventing any tolerance.

## 4. Metrics (reused frozen definitions only)

```
A  within-platform workload ranking (Spearman rho, and the ranking order)
B  within-platform MAC scaling: adjacent efficiency, cumulative efficiency
     adjacent(Mi)    = (cycles(Mi-1)/cycles(Mi)) / (Mi/Mi-1)
     cumulative(Mi)  = (cycles(M0)/cycles(Mi))   / (Mi/M0)
C  scaling classes STRONG >= 0.75 | PARTIAL 0.50-0.75 | WEAK_OR_SATURATED < 0.50
D  saturation: first Mi with adjacent < 0.50, else NONE_OBSERVED
E  within-platform geomean-normalized workload cost
```

No aggregate "platform robustness score". No new pass/fail threshold.

## 5. Comparison classes — analysed separately, never pooled

```
CLASS A  same TA state    U65: SSE-310 ↔ SSE-315            (TA_OFF ↔ TA_OFF)
         scope: subsystem/FVP sensitivity under the tested TA-OFF condition.
         Not silicon or hardware-platform causality.

CLASS B  TA state differs  U55: SSE-300 ↔ SSE-310
                           U65: SSE-300 ↔ SSE-310, SSE-300 ↔ SSE-315
         scope: subsystem + timing-model sensitivity. A difference is never
         attributed solely to Corstone or solely to the timing adapter.

CLASS C  same-SSE U55 vs U65 — NOT executed in this campaign (HOLD).
CLASS D  SSE-320/U85 — no new runs; connected only via prior structural evidence.
```

## 6. Forbidden calculations (analyzer rejects, prose prohibits)

```
SSE300/SSE310 cycle ratio · SSE310/SSE315 cycle ratio · "% faster" · "% slower"
absolute cross-platform cycle error · absolute cross-platform latency comparison
raw-cycle platform ranking · cross-platform geomean mixing
CLASS A and CLASS B pooled into one statistic
```

Raw cycles are stored per platform as formal evidence; they are not a
cross-platform performance metric.

## 7. Structural questions (answered descriptively)

Q1 ranking preserved? Q2 MAC-step direction preserved? Q3 scaling class
preserved? Q4 saturation verdict preserved? Q5 normalized-cost ordering/shape
qualitatively consistent? Q6 are disagreements concentrated in CLASS B or also
present in CLASS A — **answered non-causally**.

Outcome vocabulary: `CONSISTENT_ACROSS_TESTED_PLATFORM_TIMING_CONDITIONS` /
`PLATFORM_TIMING_SENSITIVE`, plus the standing
`ASSOCIATED_WITH` / `CONSISTENT_WITH` / `NOT_SEPARATED` / `NOT_EVALUABLE`.

## 8. Freeze sequence

contract (this file) → mutation tests → pre-campaign anchor → formal
acquisition → raw evidence freeze → derived structural analysis → results
freeze → STOP. Tags: `paper-platform-sensitivity-x1-plan-anchor`,
`…-x1-evidence-frozen`, `…-x1-results-frozen`. No manuscript narrative.
