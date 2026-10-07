# Board validation plan (RQ3) — frozen before any board data

Frozen ahead of the seven FPGA builds and the single integration probe, so no
definition here can be shaped by a board observation.

```
target      Corstone-320 / Ethos-U85 / 1024 MAC   (single configuration)
workloads   the frozen main seven — all of them
status      formal board measurements HOLD
```

## Workloads — all seven, no subset

```
rnnoise_INT8
kws_micronet_m
ad_medium_int8
vww4_128_128_INT8
yolo-fastest_192_face_v4
mobilenet_v2_1.0_224_INT8
wav2letter_pruned_int8
```

Ranking preservation is the primary instrument for RQ3, so selecting a subset
would weaken the very result the board is being used to establish.

## The experimental unit is not "the same binary"

FVP and FPGA binaries are **target-specific** — this was established, not
assumed. The unit of comparison is therefore:

```
same model / source identity
same logical U85 @ 1024 configuration
target-specific FVP and FPGA builds
```

Any phrasing of the form "the same binary was run on both" is prohibited.

## Analysis contract

**Primary — workload-ranking preservation.** Spearman `rho` over all seven
workloads, reported together with the actual rank inversions. No arbitrary
pass/fail threshold is invented; the correlation and the inversions are the
result.

**Secondary — within-domain normalized relative workload cost.** FVP and board
are normalized *independently*, because they do not share an absolute cycle
domain. Reference, fixed here:

```
normalized_cost_i = cost_i / geomean(cost_1 … cost_7)
```

computed separately within each domain. No prior paper contract specifies a
different normalization. The comparison is reported as **relative-cost-shape
deviation** and is never called an error.

**Secondary — board repeatability.** Dispersion within and across boots.

**Conditional — U85 PMU / bottleneck consistency.** Admitted *only* if the FPGA
measurement path is independently shown valid. Same generation on both sides
makes the events comparison *candidates*; it does not establish that they are
validly collected on the board.

## Forbidden

```
FVP-vs-board absolute-cycle equality or error
board MAC-scaling claims          (one MAC configuration only)
cross-generation board claims
"the same binary ran on both"
```

## Preregistered formal protocol — NOT YET AUTHORIZED

```
7 workloads × 3 independent fresh boots × 10 consecutive runs = 210 samples

per boot        -> median of its 10 runs
canonical value -> median of the three per-boot medians
```

Boot blocking is preserved: the ten runs within a boot are **not** pooled across
boots into one average. This yields exactly one value per workload for the
ranking and relative-cost analyses.

This protocol is registered, not approved. It runs only after the measurement
path qualifies.

## The blocking prerequisite: does the board measurement path work at all?

The FVP formal data came from the stock MLEK runner's PMU output. Board
qualification earlier in this project showed that the Ethos-U **power-release
lifecycle** can invalidate PMU state after an inference returns.

So the following inference is prohibited:

> "MLEK PMU worked under FVP, therefore the same runner is valid on FPGA."

That is the same defect that has recurred throughout this project — a claim about
one artifact used as authority for a different one.

### Step 1 — seven FPGA builds, no measurement

Build all seven FPGA-specific U85@1024 artifacts and record, per build:

```
model SHA
Vela artifact + configuration
ethos-u85-1024
CPU fallback operator count = 0
FPGA_PLATFORM_SSE_320
runner AXF / APP identities
build closure
```

No board run in this step.

### Step 2 — one integration probe, `rnnoise_INT8` only

**Not a paper sample.** Short, and already known good under FVP, so it is
suitable as an integration probe. It must establish:

```
FPGA image load / deploy valid
model identity correct
inference completes
board measurement field nonzero and not stale
PMU lifecycle does not invalidate the reported metric
the U85 event semantics are actually available on the board
restore / postflight clean
```

### Stop condition

If the stock FPGA runner reports PMU cycles or events as **zero or stale**,
formal board measurement stays on HOLD and the runner is **not** patched to make
the number appear. Patching the runner to obtain a metric would break the
stock-runner contract under which every FVP measurement was taken.

Events that the stock path does not deliver are recorded `NOT_EVALUABLE`. The
formal target is not changed in order to obtain them.

## Outcome of this phase

A statement of which board metrics and events are genuinely admissible for RQ3 —
and, if the measurement path does not qualify, a decision on whether RQ3 must be
redesigned around a different, already-validated board observable.
