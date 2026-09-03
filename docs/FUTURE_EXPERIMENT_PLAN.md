# FUTURE_EXPERIMENT_PLAN.md

> **Project:** Arm Ethos-U / Corstone FVP MAC-scaling characterization  
> **Purpose:** Preserve the next-step experimental plan for future code-agent sessions.  
> **Status:** Planning only. **No new experiment is authorized by this document itself.**  
> **Date:** 2026-09-03  
>
> This file is intended to be copied into the project vault/context and used as a persistent
> reference. Any execution stage still requires explicit manager approval.

---

## 0. Current project state

The following evidence chains are already complete/frozen and must not be overwritten,
silently regenerated, or reinterpreted with new metrics.

### Completed / frozen

- Main Vela/FVP capability and executability characterization.
- Primary TA-enabled FVP formal campaign.
- RQ1/RQ2 FVP scaling analysis and narrative.
- Corstone-320 / Ethos-U85 @ 1024 physical-board validation.
- Board RQ3 analysis:
  - seven workloads;
  - Spearman rho = 1.0;
  - zero rank inversions;
  - only within-domain normalized relative workload cost was used;
  - no absolute FVP-vs-board cycle comparison.
- U85 direct mechanism study at the 256 -> 512 boundary.
- U85 memory-configuration robustness:
  - Sram_Only;
  - Shared_Sram;
  - Dedicated_Sram.
- U85 selective cross-memory operation-group profiling.
- U65 instrumentation bridge:
  - preregistered overall verdict remains `NOT_EQUIVALENT`;
  - structural/boundary/attribution/CYCLE/ACTIVE equivalence established;
  - AXI beat exact equivalence not established.
- Integrated manuscript draft exists and is frozen for review.

### Important compiler-path correction

Keep the following distinction explicit in every future analysis:

| Evidence class | Compiler path | Instrumentation |
|---|---|---|
| Formal U55/U65/U85 performance runs | default **regor** path | stock runner |
| Historical U55/U65 mechanism profiling | legacy Python core via `--debug-force-legacy-core` | compiler-internal IRQ |
| New U85 mechanism profiling | default **regor** path | post-compilation command-stream IRQ insertion |

Historical U55/U65 per-layer evidence is therefore **not** an exact decomposition of the
frozen regor formal executable. It remains supporting mechanism evidence.

---

# 1. Why additional work may still be valuable

The remaining high-value validity question is not whether the current U85 mechanism study
works. That path is already qualified.

The unresolved question is:

> **How sensitive are the paper's structural MAC-scaling conclusions to the Corstone/FVP
> platform on which the same NPU and program are executed?**

The available FVP grid is incomplete:

| Corstone / FVP | U55 | U65 | U85 | Timing Adapter |
|---|---|---|---|---|
| SSE-300 | 32 / 64 / 128 / 256 | 256 / 512 | - | ON |
| SSE-310 | 32 / 64 / 128 / 256 | 256 / 512 | - | OFF |
| SSE-315 | - | 256 / 512 | - | OFF |
| SSE-320 | - | - | 128 / 256 / 512 / 1024 / 2048 | ON |

Therefore the project must **not** present SSE-300/310/315/320 as one directly comparable
absolute-cycle benchmark series.

Instead, use the FVPs as controlled comparison pairs.

---

# 2. Core experimental philosophy

## 2.1 Do not pursue one global absolute-cycle table

Cross-platform raw cycle comparison remains invalid unless additional qualification is
performed.

Known confounds include:

- different Corstone subsystems;
- different memory/interconnect structures;
- Timing Adapter ON/OFF mismatch;
- Fast Models version skew;
- different NPU support by platform;
- compiler memory/system configuration changing the generated artifact.

The default cross-platform comparison layer should therefore use **structural /
dimensionless metrics**, not raw cross-platform cycle ratios.

## 2.2 Separate the three different "memory" axes

Never collapse all memory-related controls into one variable.

### A. Vela `memory-mode`

Examples:

- `Sram_Only`
- `Shared_Sram`
- `Dedicated_Sram`

Changing this may change:

- weight placement;
- activation-buffer headroom;
- tiling;
- DMA behavior;
- scheduling;
- generated program bytes.

Interpret as:

`compiler + placement + memory-configuration effect`

not as a pure bandwidth intervention.

### B. Vela `system-config`

Examples are generation-specific.

This is a compiler-side memory-system model and can also change the generated artifact.

### C. FVP Timing Adapter / simulated memory-service parameters

Examples:

- latency;
- bandwidth / scale;
- burst/service parameters.

If these can be changed while keeping the exact same compiled artifact, this is the
cleanest available way to study simulated memory-service sensitivity.

---

# 3. Planned future campaign hierarchy

The following stages are **plans, not execution authorization**.

---

## Stage X0 — Comparability / capability matrix

### Goal

Freeze the exact comparison universe before collecting new performance data.

### Audit for every FVP

Record:

- exact executable name;
- Fast Models version;
- runtime version;
- supported NPU generation(s);
- supported MAC settings;
- Timing Adapter state;
- all load-bearing FVP parameters;
- supported Vela memory modes;
- supported Vela system configs;
- whether the same compiled artifact can be reused across candidate FVPs;
- PMU event family;
- known semantic limitations.

### Required output

Suggested files:

```text
docs/paper/platform_sensitivity/
  FVP_COMPARABILITY_MATRIX.md
  FVP_CAPABILITY_MATRIX.csv
  FVP_PARAMETER_AUTHORITY.md
  ARTIFACT_REUSE_MATRIX.csv
```

### Gate

No performance collection until the matrix is frozen.

Suggested tag:

```text
paper-platform-sensitivity-x0-frozen
```

---

## Stage X1 — Same NPU, different Corstone: platform/timing sensitivity

### Priority

**Highest-value remaining experiment.**

### Research question

> Does the same NPU, running the same workload and the same compiled program, preserve its
> MAC-scaling structure when moved between supported Corstone FVPs?

### X1-A: U55

Candidate comparison:

```text
U55
MAC {32,64,128,256}
SSE-300 vs SSE-310
```

Requirements:

- same workload identity;
- same Vela version;
- same compiler configuration;
- exact same Vela artifact wherever technically possible;
- no per-platform recompilation unless unavoidable and explicitly classified.

### X1-B: U65

Candidate comparison:

```text
U65
MAC {256,512}
SSE-300 vs SSE-310 vs SSE-315
```

Again prefer exact artifact reuse.

### Important interpretation boundary

Because Timing Adapter state differs:

```text
SSE-300  = TA ON
SSE-310  = TA OFF
SSE-315  = TA OFF
```

do **not** call the result a pure "Corstone hardware effect."

Use:

```text
subsystem + timing-model sensitivity
```

or equivalent wording.

### Primary metrics

Reuse previously frozen structural metrics whenever possible:

- workload ranking;
- adjacent MAC scaling efficiency;
- cumulative scaling efficiency;
- saturation verdict;
- normalized relative workload cost.

Do not invent new robustness thresholds after observing X1 data.

### Main validity question

Test whether the L2 structural metrics themselves are robust to platform/timing changes.

Do **not** assume robustness in advance.

### Example interpretation outcomes

If a workload's scaling class/rank is preserved across FVPs:

```text
CONSISTENT_ACROSS_TESTED_PLATFORM_TIMING_CONDITIONS
```

If direction/class changes:

```text
PLATFORM_TIMING_SENSITIVE
```

Do not jump to a hardware-causal explanation.

### Stop condition

After X1 evidence and derived structural comparison are frozen:

```text
STOP FOR MANAGER REVIEW
```

Do not automatically start X2.

---

## Stage X2 — Same Corstone, different NPU: controlled NPU contrast

### Goal

Use the small subset where the Corstone substrate is shared.

### X2-A — SSE-300

Candidate clean contrast:

```text
SSE-300
U55 @ 256
vs
U65 @ 256
```

Both are on the same SSE-300 substrate and TA is ON.

This is the strongest currently available same-platform U55/U65 contrast.

### X2-B — SSE-310 diagnostic control

Candidate:

```text
SSE-310
U55 @ 256
vs
U65 @ 256
```

TA is OFF.

Treat this as diagnostic evidence, not primary performance truth.

### Key use

Check whether U55-vs-U65 structural differences have the same direction under:

- memory-aware / TA-ON SSE-300;
- TA-OFF SSE-310.

### Critical limitation

There is no equivalent same-SSE U65-vs-U85 pair.

Therefore:

```text
U65 vs U85 absolute cross-generation comparison remains unqualified.
```

U85 must still be connected through structural/normalized evidence unless a future platform
provides a true controlled pair.

---

## Stage X3 — Structural-metric robustness synthesis

### Goal

After X1/X2, explicitly assess which paper metrics survive platform variation.

Candidate metrics:

- Spearman workload ranking;
- adjacent scaling efficiency;
- cumulative scaling efficiency;
- saturation classification;
- geomean-normalized relative workload cost.

### Rule

This stage should reuse definitions already frozen for the main paper whenever possible.

If a new robustness statistic is desired, it must be preregistered **before** applying it
to X1/X2 results.

### Intended output

A comparability table such as:

```text
Metric                           U55 300↔310   U65 300↔310↔315   Cross-NPU use
--------------------------------------------------------------------------------
workload rank                    ...
adjacent efficiency              ...
saturation                       ...
normalized relative cost         ...
raw cycles                       NOT_ALLOWED
```

---

## Stage X4 — Timing Adapter memory-service sensitivity

### Status

Optional / follow-up unless full-paper review identifies it as necessary.

### Goal

Study simulated memory-service sensitivity while keeping the compiled artifact fixed.

Candidate platforms:

```text
SSE-300
SSE-320
```

because TA is available there.

### Experimental isolation target

Keep fixed:

- NPU;
- MAC;
- workload;
- exact Vela artifact.

Vary only an audited FVP memory-service parameter, e.g.:

- latency;
- bandwidth/scale.

### Preferred U85 focus

If revisiting the known U85 256 -> 512 boundary:

```text
U85 / SSE-320
MAC {256,512}
```

This can test whether observed regressions persist as simulated memory service is relaxed or
tightened.

### Interpretation

If a reversal changes with TA conditions:

```text
MEMORY_SERVICE_SENSITIVE
```

If it persists:

```text
ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE
```

Neither result alone proves hardware geometry or compiler scheduling causality.

---

## Stage X5 — Fast Models version-matched subset

### Status

Only required if the paper decides to open a true absolute cross-platform comparison layer.

### Preconditions for absolute comparison

All must be satisfied:

```text
Fast Models version matched
+
Timing Adapter semantics matched or explicitly calibrated
+
same artifact
+
same measurement definition
```

Until then:

```text
cross-platform raw-cycle ratio/error claims remain forbidden.
```

Do not reinstall/rebuild the FVP stack merely for aesthetic uniformity.

---

# 4. Relationship to existing P0/P1/U65-bridge evidence

Do not confuse the new X-series with the completed U85 mechanism campaign.

## Existing P0/P1 evidence answers

- Which U85 operation groups regress/improve at 256 -> 512?
- Does U85 whole-model direction persist across tested Vela memory modes?
- Do the same logical groups regress across those modes?
- Is ublock change alone discriminative?
- Can U85 post-compilation profiling be trusted in the cycle domain?

## X-series answers

- How much can Corstone/FVP substrate and timing semantics alter the same NPU's scaling
  structure?
- Which normalized metrics remain usable across those platform variations?
- Which architecture comparisons are genuinely controlled and which remain confounded?

The two evidence chains are complementary.

---

# 5. Current interpretation boundaries to preserve

## Allowed

Examples:

```text
within-platform MAC scaling
same-NPU cross-platform sensitivity
same-SSE U55/U65 structural contrast
normalized / dimensionless cross-platform comparison after qualification
U85 direct operation-group mechanism evidence
```

## Not allowed without new qualification

```text
"SSE-320 is X% faster than SSE-315"
"U85 is X% faster than U65" using raw FVP cycles
"core replication is superior to block enlargement"
"memory bandwidth alone caused the change"
"TA-OFF and TA-ON cycles are directly comparable"
"Fast Models version skew is negligible"
```

---

# 6. Artifact identity rules

Every future platform comparison must explicitly classify artifact identity.

Use at least:

```text
SAME_ARTIFACT
DIFFERENT_ARTIFACT
NOT_COMPARABLE
```

The strongest X1 cell is:

```text
same model
same NPU
same MAC
same Vela artifact hash
different FVP
```

If the artifact must be recompiled for a platform, the comparison is no longer a clean
same-program platform effect and must be downgraded.

---

# 7. Formal acquisition rules

Unless explicitly superseded by a new frozen plan:

- preserve fresh-process FVP measurement semantics;
- qualify determinism before imposing exact-equality repetition contracts;
- do not average deterministic FVP runs;
- do not introduce tolerances after observing formal data;
- preserve all raw UART / PMU / build provenance;
- freeze the analysis contract before applying it;
- apply the frozen analyzer once;
- freeze derived evidence before narrative.

Existing frozen evidence must never be rewritten.

---

# 8. Storage / evidence hygiene

Before any new campaign:

1. check disk free space;
2. preserve every frozen evidence root and manifest;
3. delete only artifacts classified:

```text
REBUILDABLE_AND_NOT_EVIDENCE
```

4. never delete `UNCERTAIN` files;
5. verify frozen evidence hashes after cleanup;
6. create one manifest per new campaign;
7. avoid self-referential manifest hashing bugs.

---

# 9. Recommended actual execution order

If future manager review authorizes more experiments, use this order:

```text
1. X0 capability/comparability audit
2. manager review
3. X1 same-NPU platform-sensitivity campaign
4. freeze + review
5. decide whether X2 is still scientifically useful
6. if useful, X2 same-SSE NPU contrast
7. X3 structural-metric robustness synthesis
8. manuscript update/review
9. X4 TA sweep only if a remaining mechanism question justifies it
10. X5 FM-version matching only if absolute cross-platform performance becomes a paper goal
```

Do **not** automatically execute X0 -> X5 as one pipeline.

Each major stage requires a manager GO.

---

# 10. Current recommended project stance

As of this plan:

```text
Current manuscript              REVIEWABLE
U85 mechanism evidence          SUFFICIENT
board validation                SUFFICIENT
profiling-method validation     SUFFICIENT

remaining high-value robustness question:
  same-NPU / different-Corstone platform sensitivity

recommended next experiment:
  X0 -> X1

not currently recommended:
  full 19 × 3-memory-mode × workload Cartesian sweep
  cross-generation raw-cycle bar chart
  immediate FM reinstall/version-unification
  unrestricted TA parameter sweep
```

The next agent should first read this document, the frozen measurement semantics, the main
experiment matrix, and all existing P0/P1/U65-bridge verdicts before proposing any
new execution.

---

# 11. First instruction for a future code-agent session

Use the following as the default startup instruction:

```text
Read FUTURE_EXPERIMENT_PLAN.md and the existing frozen paper evidence.

Do not start a new experiment.

First report:
1. current frozen project state;
2. which X-stage is currently authorized, if any;
3. exact capability/artifact information needed before that stage;
4. conflicts between this future plan and existing frozen contracts.

If no explicit manager GO exists, remain in PLANNING/HOLD.
```
