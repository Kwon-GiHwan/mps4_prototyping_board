# U85 256→512 mechanism — frozen interpretation draft

Status: FROZEN INTERPRETATION DRAFT — authorized by manager review
(P1-B ACCEPTED, 2026-09-02). Scope: **U85 mechanism narrative only.**
Cross-generation per-op narrative, P2–P4, and any new measurement remain
HOLD; integrating this draft into the final manuscript is a separate,
unauthorized step. Sources: frozen P0 (P0-C0/C/D/D2/E), P1-A, P1-B
evidence and derived tables only. No metric, threshold, or aggregate
statistic beyond those frozen records is introduced here.

---

## 1. Whole-model robustness

The central anomaly — a workload becoming *slower* when the U85 doubles
from 256 to 512 MACs — is not an artifact of one configuration. Across
every memory configuration the pinned stack supports (Sram_Only,
Shared_Sram, Dedicated_Sram), rnnoise regressed in all three
(+3,000 / +15,000 / +19,000 cycles) and dnn_s regressed in all three
(+2,000 / +6,000 / +7,000), while vww4 and yolo improved in all three.
No tested configuration removed a reversal, and none created a new one.
The reversal is likewise invariant to the Vela system-config binding at
this boundary: for rnnoise and dnn_s the two 512-side bindings produce
byte-identical compiled programs, which excludes the compiler
system-config as the varying factor for those workloads.

The direction of the 256→512 change is therefore a robust property of the
(workload, MAC transition) pair on this stack — while its magnitude is
strongly configuration-sensitive, a distinction developed in §3 and §5.

## 2. Direct operator-group evidence

Per-layer decomposition of rnnoise (IRQ-history attribution, sum-coherent
with the whole model to within the constant instrumentation residual)
shows the regression is **distributed**: at the baseline configuration the
+19,000-cycle reversal decomposes into ten regressing groups of +1,000 to
+4,030 cycles each, with a single improving group (−1,000). The largest
contributor accounts for roughly a fifth of the whole-model delta. **No
single pathological operation or group explains the reversal.** The
regressing groups are composed of small elementwise clusters
(Add/Mul/Sub/Pack), small FullyConnected operations, and
Concat/Quantize — the workload's abundant low-arithmetic operations —
rather than its few large matrix operations.

## 3. Cross-memory operator robustness

The strongest single result of the campaign: the whole-model regression of
rnnoise persisted across all tested memory configurations, **and the
regression repeatedly arose from the same logical operation groups**,
although its magnitude varied substantially across configurations. In the
common attribution partition spanning all six profiled cells, 27 of 29
groups keep one direction across all three modes and **zero groups flip
direction**; the recurring regression clusters scale monotonically with
the memory configuration:

```
Add/FC/Mul/Pack        +1k → +4k → +7k    (SO → SH → DS)
Add/FC/Mul/Pack        +1k → +5k → +6k
Concat/FC/Quantize     +1k → +3k → +2k
```

This is a materially stronger statement than any whole-model observation:
the *locus* of the regression is stable under an intervention that
changes the compiled program, the memory placement, and the runtime
memory service simultaneously.

## 4. Counterexample and control — vww4

vww4 improves at the whole-model level in every configuration, yet its
decomposition shows that improvement is a *net*, not a uniformity. Local
regressions persist across all three modes (a single Conv2D at +2,000
cycles in each), and 11 of 33 groups are direction-sensitive to the
memory configuration — most prominently a 33-operation cascade group that
moves from −35,000 (Sram_Only) through −2,120 (Shared_Sram) to **+7,015
(Dedicated_Sram)**: the same logical group crosses from improvement into
regression as the memory configuration changes. vww4 thus demonstrates
both that operator-level regressions routinely hide inside net
improvements, and that for some multi-operation groups the memory
configuration changes not just the size but the *sign* of the cost
change.

## 5. Mechanism interpretation

Taken together, the evidence supports one framing and retires another.

**The framing the evidence supports — emergence from heterogeneous local
changes.** The 256→512 transition induces widespread, heterogeneous
operator-level cost changes: some operations gain from the doubled MAC
array, others lose. Whether the whole model improves or regresses is the
**aggregate outcome of that gain/loss balance**, not the direct imprint of
a single structural change:

```
              U85 256→512 transition
                        ↓
      heterogeneous operator-level cost changes
                        ↓
         ┌──────────────┴──────────────┐
   persistent regressions        config-sensitive
   (same groups, every mode)     local changes
         │                             │
      rnnoise                        vww4
   regressions outweigh          gains still outweigh
   gains overall                 regressions overall
         ↓                             ↓
   whole-model REGRESSION       whole-model IMPROVEMENT
```

**The framing the evidence retires — the single-factor ublock account.**
The 256→512 ublock transition is associated with widespread
operator-level changes, **but ublock change alone does not distinguish
improving from regressing operations**: UBLOCK_CHANGED co-occurs with
roughly 95 % of operations in every direction class (41/43 regressing,
63/65 improving, 14/16 unchanged), and BLOCK_CONFIG_CHANGED is *more*
frequent among improving operations (92 %) than regressing ones (63 %).
A claim of the form "ublock enlargement causes the regression" is not
supported by this evidence and is not made. What the small-op composition
of rnnoise's regressing clusters does license is consistency:
the observations are `CONSISTENT_WITH` a small-spatial /
low-arithmetic-utilization account, while remaining `NOT_SEPARATED` from
the compiler-scheduling changes that accompany the same transition.

**Memory configuration — modulation without separation.** Memory
configuration modulates both the magnitude and, for some operation
groups, the direction of the 256→512 cost change; **compiler-generated
program changes and runtime memory-system effects remain inseparable in
this experiment.** Every mode pair compiles to a different artifact, and
the pass/command structure shifts substantially with mode (vww4 launch
counts 83/168/91 across SO/SH/DS at 256). Single-factor memory claims —
"Shared-SRAM contention causes…", "bandwidth causes…" — are therefore
not available; the memory-mode axis is a configuration intervention, not
a bandwidth intervention.

## 6. Limitations

1. **Stall-based causal attribution is `NOT_EVALUABLE`.** The U85
   stall-family PMU events remain `SEMANTICS_UNVERIFIED` and were never
   collected; memory behaviour is observed only through beat counters.
2. **Mixed multi-operation windows bound attribution.** Where small
   operations merge into one IRQ-service window, per-op cause is
   `NOT_EVALUABLE`; only the operation-group effect is evaluable. Claims
   are phrased accordingly — "the multi-operation execution group
   containing …", never "Conv2D X causes …". The vww4 33-op cascade is
   exactly such a group.
3. **Memory-mode is not a pure bandwidth intervention.** It jointly moves
   weight placement, arena headroom, compiler scheduling, and the
   generated command stream (all mode pairs are `DIFFERENT_ARTIFACT`).
4. **Hardware geometry vs compiler scheduling is not causally
   separated** anywhere in this campaign; the wording contract
   (`ASSOCIATED_WITH` / `CONSISTENT_WITH` / `NOT_SEPARATED` /
   `NOT_EVALUABLE`) is maintained throughout.
5. **Scope.** All values are FVP cycle-model observations on the pinned
   stack; nothing here is board data, latency, or `T_npu`. Cross-
   generation per-op comparison (U55/U65 ↔ U85) is **out of scope for
   this narrative**: the two generations' per-layer profilers are
   different implementations (legacy compiler-inserted IRQ vs the U85
   binary post-processor), and joining their per-op numbers first
   requires the separate bridge-equivalence validation — registered as
   future work, not a precondition for this U85 account.

---

*Next gate: manuscript integration — NOT authorized by this freeze.*
