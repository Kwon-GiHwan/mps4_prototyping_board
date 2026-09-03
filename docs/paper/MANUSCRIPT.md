# Characterizing Arm Ethos-U NPU Configurations: Simulated Scaling, Hardware Validation, and an Operator-Level Mechanism Study

Integrated manuscript draft. Assembled 2026-09-02 from frozen evidence only
(`paper-fvp-*`, `paper-board-*`, `paper-u85-*`, `paper-u65-bridge-*`). No new
metric, threshold, correlation, or measurement is introduced by this
integration. Statements carry the evidence vocabulary used throughout the
campaign: `ASSOCIATED_WITH`, `CONSISTENT_WITH`, `NOT_SEPARATED`,
`NOT_EVALUABLE`.

---

## 1. Introduction

Embedded ML deployment on Arm Ethos-U NPUs requires choosing among NPU
generations, MAC configurations, memory modes, and host subsystems — usually
before any hardware exists. Practitioners make those choices from compiler
estimates and cycle-model simulation, then discover on hardware what the
estimates did not carry.

This work characterizes that decision space and then examines one anomaly
inside it in depth. We ask:

- **RQ1** — How do performance characteristics change across Corstone/Ethos-U
  generations for representative workloads?
- **RQ2** — How does performance scale with MAC configuration, and where does
  scaling saturate?
- **RQ3** — To what extent do qualitative trends observed for Corstone-320 /
  Ethos-U85 in simulation reproduce on physical MPS4/FI101 hardware?
- **RQ4 (mechanism)** — For the one configuration transition where more
  hardware measured *slower* — Ethos-U85, 256 → 512 MACs — what operator-level
  behaviour produces that whole-model non-monotonicity, and how robust is it to
  memory configuration?

Contributions:

1. A 133-cell capability/executability characterization and a 74-cell formal
   simulated sweep (222 samples) with byte-level artifact provenance, in which
   **executability is reported as a first-class result** rather than as missing
   data.
2. Physical validation on Corstone-320 / Ethos-U85 hardware (21 formal
   samples), reporting **ranking preservation and relative-cost shape**, with
   absolute simulation-versus-hardware comparison refused by construction.
3. A direct operator-level mechanism study of the U85 256 → 512 reversal,
   built on a new post-compilation instrumentation path, showing the reversal
   is **distributed across operation groups** and **persists across every
   tested memory configuration** with the **same logical groups** regressing.
4. Measurement-methodology results that generalize beyond this study: a
   simulator timing adapter can silently change what is being measured; a
   compiler backend change can silently change which program is being
   instrumented; and instrumentation backends must be cross-validated before
   their per-layer numbers are joined.

## 2. Background

**Ethos-U family.** Ethos-U55, U65, and U85 differ in MAC array size options,
memory interfaces, and PMU event spaces. Vela compiles a quantized TFLite
network into an Ethos-U command stream embedded as a custom operator payload;
the core driver submits that payload and the NPU executes it.

**Corstone subsystems.** Corstone-300, -310, -315, and -320 are reference
subsystems pairing a Cortex-M host with an Ethos-U NPU, each available as a
Fast Models FVP and, for Corstone-320, as an MPS4 FPGA implementation.

**Timing adapter.** Verification platforms do not reproduce target-silicon
memory timing: an FVP models ideal memory by default, and an FPGA runs the NPU
at a low clock where memory appears disproportionately fast. The Ethos-U timing
adapter (TA) sits on the NPU's AXI paths and injects latency and bandwidth
constraints so that measurements reflect a modelled memory system. It is a
verification component, not part of production silicon. Its presence or absence
determines whether a cycle count means anything as a performance figure —
Section 3.1 and Section 8.1.

**Related work.** Prior NPU characterization studies typically report simulated
cycles across configurations; validation against physical hardware, and
operator-level decomposition of anomalies, are less common. This work
contributes both, and is explicit about which comparisons its evidence cannot
support.

## 3. Methodology

### 3.1 Platforms and configurations

Valid configurations are the intersection of Vela support and FVP-accepted
parameters, established by capability probe rather than from documentation.
The probe exposed a trap: `FVP_Corstone_SSE-300_Ethos-U55` accepts
`num_macs=100`, because the model range-checks bounds without validating the
discrete legal set. Acceptance by an FVP is therefore not evidence that a
configuration is real; Vela's `--accelerator-config` enumeration is the
authority, and a configuration is admitted only where both hold.

That yields **19 simulated configurations** (SSE-300/U55 at 32–256,
SSE-300/U65 at 256/512, SSE-310/U55 at 32–256, SSE-310/U65 at 256/512,
SSE-315/U65 at 256/512, SSE-320/U85 at 128–2048) and **one board
configuration** (MPS4 / Corstone-320 / U85 @ 1024 MACs, fixed in the FPGA).

**The capability universe is not the benchmark universe.** MLEK disables the
timing adapter for Corstone-310 and Corstone-315, visible in which files
compile (sse-300: 401 sources, 2 timing-adapter sources; sse-320: 402/2;
sse-310: 399/0; sse-315: 400/0), following Arm's own guidance that those
subsystems' adapter implementations are unsuitable for bandwidth/latency
sweeps. Consequently **11 of 19 configurations are benchmarking-valid**, and
the 56 TA-OFF cells are retained as capability and diagnostic evidence only.

### 3.2 Workloads

Seven fully NPU-placed INT8 models from the MLEK resource set span 467× in
estimated cycles: `rnnoise_INT8`, `kws_micronet_m`, `ad_medium_int8`,
`vww4_128_128_INT8`, `yolo-fastest_192_face_v4`, `mobilenet_v2_1.0_224_INT8`,
`wav2letter_pruned_int8`. `dnn_s_quantized` is excluded from scaling analysis
because ~9.5 % of its operators run on the CPU, so its total does not scale
with MAC count; where it appears in the mechanism study it is reported on a
separate track and never pooled.

### 3.3 Metrics and measurement semantics

Three kinds of number are reported, never mixed on one axis:

| kind | source | what it is |
| --- | --- | --- |
| compiler estimate | Vela summary CSV | a performance-model prediction (`vela_estimated_*`) |
| simulated observation | FVP run | a cycle-model result |
| physical observation | MPS4 board | a software-visible observation on hardware |

Vela's `inference_time` divides estimated cycles by an assumed system clock,
not a measured one. Timing intervals obtained by software polling are named
`software_visible_completion_observation_cycles`: both endpoints are CPU-side
events, and the interval includes register-visibility delay and MMIO sampling
granularity. The vocabulary `latency`, `T_npu`, and `execution time` is refused
for such intervals, in prose and in analyzer code.

Admissible comparisons: within-configuration repeatability, within-platform
MAC scaling, estimate-versus-estimate, and same-generation simulated
comparisons, numerically; simulation-versus-board as ranking and trend,
qualitatively. Refused: absolute simulation-versus-board cycles, absolute
cross-generation cycles (Fast Models versions differ across the four FVPs:
11.22.35 / 11.24.13 / 11.27.25 / 11.31.28), and estimate-versus-observation
absolutes.

### 3.4 Compilation and instrumentation paths (three distinct paths)

Vela 5.0.0 routes compilation through the `regor` backend by default for all
targets; the legacy Python compilation core is deprecated and reachable only
via `--debug-force-legacy-core`, which supports Ethos-U55/U65 with TFLite
inputs. This distinction is load-bearing and is stated explicitly because the
three bodies of evidence in this paper do **not** all come from the same
compilation path:

| evidence | compilation path | instrumentation |
| --- | --- | --- |
| **Formal performance evidence** (RQ1/RQ2/RQ3; all 74 formal cells, all board cells) | **default regor path** | none — stock unmodified runner |
| **Historical U55/U65 mechanism profiling** | **legacy Python core**, entered only via `--debug-force-legacy-core` | compiler-internal IRQ insertion inside the legacy code generator |
| **U85 mechanism profiling** (Sections 6, RQ4) | **default regor path** | **post-compilation** instrumentation of the regor-generated command stream |

Two consequences are stated up front:

1. The frozen U55/U65 formal performance artifacts of this paper are **regor**
   outputs. Any description of that data as legacy-core output would be wrong.
2. The historical U55/U65 per-layer profiling data is **not an exact
   decomposition of the frozen regor formal executable**: it decomposes a
   legacy-core program compiled under the same source contract, which is a
   different binary. It is reported as historical mechanism evidence on its own
   program, never as a per-operator breakdown of the formal RQ1/RQ2 cells.

The U85 post-compilation instrumentation inserts `NPU_OP_IRQ` commands into the
compiled command stream using opcode tables and framing extracted mechanically
from the vendor interface header, so the measured program is the regor program
that the formal path also compiles, plus declared interrupts.

### 3.5 Measurement-boundary qualification

**What a polled completion interval measures.** Three board campaigns
(V13–V15) established the boundary. V13 showed the observed timing variation
was accounted for by poll count — how often the CPU looked, not what the device
did between looks. V14 (90/90 valid samples, nine boots) falsified a
first-read advantage and confirmed an inter-read sampling effect, leaving
intrinsic register-visibility ordering unresolved. V15 (30/30 valid samples,
three boots) reproduced a floor-plus-excursion structure using a single-register
control, falsifying both "the structure requires QREAD" and "the structure
requires dual-register observation" as necessary conditions. The chain is
`internal transition → register visibility → MMIO sampling → CPU observation`,
and only the last link is measured; the device exposes no internal completion
timestamp, so no campaign of this design can produce one.

**Whether the U85 per-layer instrumentation is sound.** The post-compilation
path was qualified before use: identity-preserving parse/serialize round trips
on all candidate streams, single- then multi-interrupt proofs, bit-identical
outputs against uninstrumented runs, operator-to-interrupt mapping predicted
from the compiler schedule and matched exactly, per-segment sums coherent with
whole-model totals, and full-vector exact repeatability across fresh simulator
processes. Whole-model instrumentation perturbation is reported descriptively
(+0.309 % at 15 interrupt boundaries on the qualification cell); no pass/fail
threshold is attached, and the prior study's U55 figure is not imported.

**Whether the two instrumentation backends measure the same boundary.** A
cross-backend bridge experiment on Ethos-U65 compared the compiler-internal
method against the post-compilation method **on the same underlying program**
(a forced-legacy-core clean stream, so that no compiler-backend difference
enters the comparison). Results and their limits are in Section 6.5; the
preregistered verdict is `NOT_EQUIVALENT` on the full PMU vector, with
component-level equivalence established for execution boundaries, attribution,
and the cycle and active-cycle domains.

### 3.6 Provenance and procedure

Every formal cell carries an identity chain: model SHA → Vela artifact SHA →
generated model-source body SHA → linked executable SHA → execution. Builds are
byte-reproducible after pinning `SOURCE_DATE_EPOCH` to the source-tree commit
timestamp — necessary because the firmware embeds `__DATE__`/`__TIME__`, which
made every binary unique until pinned.

Simulated cells use one discarded warm-up inference and three deterministic
runs required to be **exactly equal**; disagreement is a hard stop, never an
average, because a deterministic model disagreeing with itself indicates a
harness fault. Board cells use three independent fresh boots. Invalid runs are
discarded with a named reason and never down-weighted.

Analysis plans were frozen before the data they read, applied exactly once, and
amended only by recorded supersession. Analyzers carry mutation tests proving
each rejection rule can fire.

## 4. Cross-generation simulated characterization (RQ1, RQ2)

Formal sweep: 74 executable TA-ON cells, 222 samples, `M1 == M2 == M3` on
74/74 across 19 equality-bearing fields.

### 4.1 MAC scaling and saturation (RQ2)

Across 21 preregistered ladders, 53 adjacent MAC transitions were evaluable:

| incremental efficiency class | count |
| --- | --- |
| `STRONG` (≥ 0.75) | 28 |
| `PARTIAL` (0.50–0.75) | 23 |
| `WEAK_OR_SATURATED` (< 0.50) | 2 |
| `NOT_AVAILABLE` (adjacent point non-executable) | 3 |

Under the preregistered saturation criterion, saturation was `NONE_OBSERVED` in
19 of 21 ladders, observed once (SSE-320 / U85 / `rnnoise_INT8` at MAC 512), and
`NOT_AVAILABLE` once (`wav2letter` / SSE-300 / U55, whose baseline is
non-executable).

*Supported:* most tested ladders retained at least partial scaling over the
explored MAC range, and scaling response was workload-dependent rather than
converging on a universal saturation point. *Not established:* that these
workloads do not saturate — `NONE_OBSERVED` means not seen within the tested
range — or that scaling is "mostly linear", since `STRONG` is a threshold at
0.75 efficiency, not ideal scaling.

The single observed saturation point is the entry point for Section 6.

### 4.2 Compiler estimates versus simulated observation

Over 20 comparable ladders, each series normalized independently: saturation
classification agreed in 19/20, normalized speedup ordering agreed in 19/20
(Spearman `rho == 1.0`), while per-step incremental class agreement ranged from
4/4 down to 0/1.

*Supported:* Vela preserves coarse scaling structure — whether a configuration
keeps scaling, and the ordering of normalized speedups — but is less reliable
for the class of an individual MAC step. *Not established:* any accuracy,
error percentage, or systematic bias of Vela against FVP cycles; no absolute
error or calibration was computed, and the analysis contract rejects one.

### 4.3 Workload ranking stability

Over 55 configuration pairs: `rho == 1.0` in 31/55, minimum 0.9429, median
1.0000. Ordering is the portable quantity of this dataset; absolute cycles are
not comparable across generations at all.

### 4.4 Executability as a result (RQ1 boundary condition)

All 133 capability cells compiled under Vela; **6 could not run**. The failures
are homogeneous — `wav2letter_pruned_int8` × Ethos-U55 × `Shared_Sram` at MAC
32/64/128 — and each reached a linker SRAM overflow after the deterministic
minimum-increment arena retry, meaning the smallest arena that could clear the
first allocation failure already did not fit. `EXECUTABILITY_UNRESOLVED` was 0.

Classification: **system-level memory / deployability limitation**, not a U55
microarchitecture limit; MAC count, NPU, memory mode, and platform memory map
are confounded in those six cells. Compiler acceptance does not establish
deployability, and a missing cell is a result rather than a gap in collection.

### 4.5 RQ1 statement

*Supported:* the generations and configurations differ primarily in normalized
scaling behaviour, workload ordering, and deployability characteristics, rather
than in directly comparable absolute cycle values. *Not established:* any "U85
is faster than U55" statement — Fast Models version skew and timing-adapter
differences make absolute cross-generation comparison unsupportable on this
data.

## 5. Corstone-320 hardware validation (RQ3)

The board contributes exactly one matrix cell: Corstone-320 / U85 @ 1024 MACs,
seven workloads, three independent fresh boots — **21 formal samples**.

**The protocol was corrected before any formal sample existed.** The registered
3 boots × 10 runs design was not executable: the stock runner performs exactly
one inference per boot, and "ten consecutive runs" was a capability of a custom
runner used in earlier campaigns. Since patching the artifact under test was
not authorized, the protocol became 3 boots × 1 stock inference = 21 samples,
recorded as a supersession. Canonical value per workload is `median(B1,B2,B3)`.

**Ranking preservation (primary).** Spearman `rho = 1.0`, **0 rank inversions**
across all seven workloads:

| workload | FVP rank | board rank |
| --- | --- | --- |
| `rnnoise_INT8` | 1 | 1 |
| `kws_micronet_m` | 2 | 2 |
| `ad_medium_int8` | 3 | 3 |
| `vww4_128_128_INT8` | 4 | 4 |
| `yolo-fastest_192_face_v4` | 5 | 5 |
| `mobilenet_v2_1.0_224_INT8` | 6 | 6 |
| `wav2letter_pruned_int8` | 7 | 7 |

**Relative cost shape (secondary).** Each domain normalized by its own
geometric mean:

| workload | FVP normalized | board normalized |
| --- | --- | --- |
| `rnnoise_INT8` | 0.1521 | 0.1619 |
| `kws_micronet_m` | 0.2791 | 0.2858 |
| `ad_medium_int8` | 0.4371 | 0.4459 |
| `vww4_128_128_INT8` | 0.7129 | 0.7027 |
| `yolo-fastest_192_face_v4` | 1.3606 | 1.3309 |
| `mobilenet_v2_1.0_224_INT8` | 4.3570 | 4.2680 |
| `wav2letter_pruned_int8` | 12.7514 | 12.1432 |

The two vectors are presented side by side. **No aggregate deviation metric is
computed**: `L1`, `L2`, RMSE, mean absolute percentage, and the board/FVP ratio
were never preregistered, and selecting one with both vectors visible would be
choosing a statistic to fit the result. Board repeatability is reported as the
raw triplet plus median, with no spread statistic, for the same reason.

Whether `rho = 1.0` constitutes strong validation is a judgement, not a
threshold result: no pass/fail criterion was invented to declare it one. What
the comparison establishes is that **ordinal structure and relative cost shape
transfer from the cycle model to this hardware configuration**, while absolute
comparison remains refused — the two builds are target-specific (FVP and FPGA
binaries are not interchangeable for Corstone-320), so any absolute deviation
would also include whatever those builds differ in.

PMU cross-target status: `TOTAL`/`ACTIVE`/`IDLE` are present in both frozen
sets but no board canonicalization across boots was preregistered;
`SRAM_*`/`EXT_*` are board-collectable but absent from the frozen simulated
records, hence `NOT_EVALUABLE`. The frozen stages were not re-run to obtain
them.

## 6. Operator-level mechanism study: U85 256 → 512 (RQ4)

### 6.1 The anomaly and its scope

In the formal sweep, exactly one workload becomes slower when the U85 doubles
from 256 to 512 MACs: `rnnoise_INT8`, 36,086 → 55,086 cycles (+19,000). Vela
predicts improvement for every workload including this one, so the reversal is
also a compiler-estimate/simulation disagreement point. `dnn_s_quantized`, on
its separate track, also regresses (22,068 → 29,068).

A registered boundary condition: on this stack the 256 → 512 step also crosses
a Vela system-config discontinuity (`SYS_DRAM_Low` at 128/256,
`SYS_DRAM_Mid_512` at 512). The mechanism study therefore compiled **both**
bindings — reproducing the sweep convention, and holding the system config
fixed — as a registered dual binding. For `rnnoise` and `dnn_s` the two 512
bindings produce **byte-identical artifacts**, which excludes the system-config
choice as the varying factor for exactly those workloads.

### 6.2 Instrumentation

Per-layer decomposition uses the post-compilation instrumentation path of
Section 3.4, qualified as described in Section 3.5. Attribution uses the U85
interrupt-history mechanism: interrupts carry one-hot identifiers and the
driver records the history mask consumed by each service, so when consecutive
small operations merge into one service window the window's exact membership is
recovered. Operations confined to unmixed windows receive exact cycles;
operations sharing a window are `NOT_SEPARATED` at operation granularity and
are reported at operation-group granularity, which remains lossless.

Formal acquisition: 18 cells (6 workloads × 3 artifacts), clean and profiled
arms, three fresh simulator processes per arm with full-vector exact equality,
and profiled outputs bit-identical to the clean outputs on every profiled cell.

### 6.3 The reversal is distributed, not localized

For `rnnoise` at the sweep baseline, the +19,000-cycle reversal decomposes into
**ten regressing groups of +1,000 to +4,030 cycles each**, with a single
improving group (−1,000). The largest contributor accounts for roughly a fifth
of the whole-model delta. **No single pathological operation or group explains
the reversal.** The regressing groups comprise small elementwise clusters
(Add/Mul/Sub/Pack), small fully-connected operations, and Concat/Quantize —
the workload's abundant low-arithmetic operations rather than its few large
matrix operations.

Two further observations bound interpretation. First, `UBLOCK_CHANGED`
co-occurs with roughly 95 % of operations in **every** direction class (41/43
regressing, 63/65 improving, 14/16 unchanged), and `BLOCK_CONFIG_CHANGED` is
*more* frequent among improving operations (92 %) than regressing ones (63 %).
The 256 → 512 ublock transition is therefore associated with widespread
operator-level change, but **ublock change alone does not distinguish improving
from regressing operations**. Second, per-operator regressions also exist
inside workloads whose whole-model result improves — 19 regressing operations
summing +31,015 in `vww4` against −56,000 of improvements, 21 summing +40,985
in `yolo` against −140,000.

### 6.4 Robustness to memory configuration

A capability audit of the memory configurations admitted three tuples on this
stack (`Sram_Only`, `Shared_Sram`, `Dedicated_Sram`); no Ethos-U85 Flash system
configuration exists, so that prior-study tuple is `NOT_SUPPORTED`.

**Whole-model direction is invariant across all three; magnitude is not:**

| workload | Sram_Only | Shared_Sram | Dedicated_Sram |
| --- | ---: | ---: | ---: |
| rnnoise | **+3,000** | **+15,000** | **+19,000** |
| dnn_s | **+2,000** | **+6,000** | **+7,000** |
| vww4 | −83,000 | −32,000 | −28,000 |
| yolo | −288,000 | −244,000 | −225,000 |

No configuration removes a reversal and none creates one. Because every memory
mode compiles to a **different artifact**, the contribution of memory-system
behaviour versus compiler-generated program change remains `NOT_SEPARATED`.

**The same logical groups regress in every configuration.** Cross-memory
decomposition of `rnnoise` (12 profiled cells, one common attribution partition)
shows 27 of 29 groups direction-consistent across all three modes and **zero
direction flips**, with the recurring clusters scaling monotonically:

```
Add/FC/Mul/Pack        +1k → +4k → +7k     (Sram_Only → Shared_Sram → Dedicated_Sram)
Add/FC/Mul/Pack        +1k → +5k → +6k
Concat/FC/Quantize     +1k → +3k → +2k
```

The control workload `vww4` behaves differently and instructively: its
whole-model result improves in every mode, yet local regressions persist in
every mode (a single Conv2D at +2,000 in all three), and **11 of 33 groups are
direction-sensitive** to the memory configuration — most prominently a
33-operation cascade group moving from −35,000 (Sram_Only) through −2,120
(Shared_Sram) to **+7,015 (Dedicated_Sram)**. The same logical group crosses
from improvement into regression as the configuration changes. Per-operation
cause inside such multi-operation windows is `NOT_EVALUABLE`; only the group
effect is evaluable, and claims are phrased as "the multi-operation execution
group containing …" accordingly.

### 6.5 Cross-backend instrumentation bridge (U65)

Because the historical U55/U65 per-layer method and the U85 method are
different instrumentation backends (Section 3.4), we tested whether they
implement the same measurement boundary — on Ethos-U65, with **both methods
applied to the same clean program**, so that no compiler-backend difference
enters the comparison.

Structural result: zero-modification round trips byte-identical; stripping the
interrupt contribution from either method reconstructs the clean stream
exactly; boundary positions and identifiers match exactly (14/14 and 46/46);
and the two independently produced instrumented streams are **byte-identical**.

Runtime result across two cells, three fresh processes per arm: outputs
identical to each other and to the clean run; segmentation and ordering
identical; per-segment and summed `CYCLE` and `ACTIVE` **exact**; AXI beat
fields **not exact** (≤ 8 beats per segment, ≤ 7 in whole-profile sums).

Because exact equality of the complete PMU vector was a frozen preregistered
criterion, the overall verdict is **`NOT_EQUIVALENT`**; that criterion is not
redefined post hoc. Component-level conclusions:

```
STRUCTURAL_EQUIVALENCE          ESTABLISHED
SEMANTIC_BOUNDARY_EQUIVALENCE   ESTABLISHED
ATTRIBUTION_EQUIVALENCE         ESTABLISHED
CYCLE_DOMAIN_EQUIVALENCE        ESTABLISHED
ACTIVE_DOMAIN_EQUIVALENCE       ESTABLISHED
AXI_BEAT_EXACT_EQUIVALENCE      NOT_ESTABLISHED
```

The beat residual **cannot be attributed specifically to the instrumentation
backend**: an uninstrumented re-containerization control, with zero interrupts
inserted, reproduced comparable beat-level and ±1-cycle variation. The residual
is `ASSOCIATED_WITH` container re-serialization; no mechanism is claimed as
uniquely proven.

Consequently the bridge permits cross-backend comparison of **execution
boundaries, attribution, and cycle-domain mechanism observations** under the
tested U65 conditions. It does **not** qualify exact cross-backend
memory-traffic comparison, and it does not establish cross-generation
PMU-event equivalence, which the event audit treats separately.

### 6.6 Mechanism framing

The evidence supports one framing and retires another.

**Supported — emergence from heterogeneous local changes.** The 256 → 512
transition induces widespread, heterogeneous operator-level cost changes: some
operations gain from the larger MAC array, others lose. Whether a whole model
improves or regresses is the **aggregate outcome of that balance**:

```
              U85 256 → 512 transition
                        ↓
      heterogeneous operator-level cost changes
                        ↓
        ┌───────────────┴───────────────┐
  persistent regressions          config-sensitive
  (same groups, every mode)       local changes
        │                               │
     rnnoise                          vww4
  regressions outweigh gains    gains still outweigh regressions
        ↓                               ↓
  whole-model REGRESSION          whole-model IMPROVEMENT
```

**Retired — the single-factor ublock account.** "Ublock enlargement causes the
regression" is not supported: ublock change is a ~95 % background rate in every
direction class. What the small-operation composition of the regressing
clusters does license is that the observations are `CONSISTENT_WITH` a
small-spatial / low-arithmetic-utilization account, while remaining
`NOT_SEPARATED` from the compiler-scheduling changes that accompany the same
transition.

**Memory configuration — modulation without separation.** Memory configuration
modulates both the magnitude and, for some operation groups, the direction of
the cost change; compiler-generated program changes and runtime memory-system
effects remain inseparable here. Single-factor claims ("shared-SRAM contention
causes…", "bandwidth causes…") are unavailable: the memory-mode axis is a
configuration intervention, not a bandwidth intervention.

## 7. Discussion

**The compiler predicts shape better than steps.** Vela matched saturation
classification in 19/20 ladders and preserved speedup ordering in 19/20, while
per-step class agreement ranged 4/4 to 0/1. Pruning a design space on predicted
*trend* is supported by this data; ranking candidates on predicted *magnitude*
is not.

**Ordering is the portable quantity.** Workload ranking was stable across
simulated configurations (`rho` median 1.0000) and transferred to hardware with
zero inversions, while absolute cycles are not comparable across generations at
all. This also explains why a single-cell board campaign can be decisive:
ranking preservation remains comparable even when MAC scaling and absolute
cycles are not.

**Compilation is not deployment.** All 133 cells compiled; 6 could not run. For
the largest workload, executability — not throughput — was the binding
constraint, and a scaling table must be read with missing cells as results.

**More hardware is not monotonically faster, and the reason is distributed.**
The one reversal in the sweep survives every memory configuration tested and
arises repeatedly from the same operation groups, yet no single group or single
compiler-visible transition accounts for it. For practitioners, the actionable
form is that a MAC upgrade must be validated per workload: models dominated by
many small, low-arithmetic operations can lose more on those operations than
they gain elsewhere, and a compiler estimate will not necessarily reveal it —
Vela predicted improvement for the one workload that regressed.

**Measurement methodology results.** Four are reusable beyond this study.
(i) A simulator's timing adapter can silently change what is being measured:
two platforms running a byte-identical command stream differed ~4× purely by
adapter state, and nothing in the cycle counts signalled it. (ii) A compiler
backend change can silently change which program is instrumented: the default
`regor` routing means legacy-core instrumentation decomposes a different binary
than the formal sweep executes — which is why this paper separates the three
paths explicitly. (iii) Firmware embedding its own build timestamp is not
byte-reproducible until the build epoch is pinned to source identity. (iv)
Executability classification belongs before the sweep: the formal sample count
could not be fixed until the filter ran (399 assumed; 222 actual).

## 8. Limitations

**8.1 The timing adapter splits the matrix.** Only 11 of 19 configurations are
benchmarking-valid; the 56 TA-OFF cells are capability and diagnostic evidence
only. A claim retracted during this work: "same NPU across different Corstone
generations" is not a clean platform isolation, because the two sides differ in
adapter state — a memory-constrained model against an unconstrained one.

**8.2 Absolute cross-generation comparison is unsupportable.** Fast Models
version skew and platform configuration differences confound it; comparisons are
restricted to normalized scaling and ordinal ranking.

**8.3 `SSE-300 / U55@256` versus `U65@256` is a system-level configuration
comparison**, not a microarchitecture result: the memory mode differs by NPU
(`Shared_Sram` versus `Dedicated_Sram`), moving weights between SRAM and DRAM.

**8.4 PMU semantics are generation-conditional.** Only `CYCLE`, `NPU_IDLE`, and
`CC_STALLED_ON_BLOCKDEP` were verified as common-semantics across generations;
of 22 shared event names, 18 differ in ordinal, so event numbers never cross a
generation boundary. `CC_STALLED_ON_BLOCKDEP` cross-generation and the U85
`EXT*`/`SRAM*` family were `NOT_EVALUABLE` — absences in what the stock runner
prints, and obtaining them would break the stock-runner contract under which
every formal measurement was taken. U85 stall-family events remain
`SEMANTICS_UNVERIFIED` and were never collected, so stall-based causal
attribution is `NOT_EVALUABLE` throughout Section 6.

**8.5 The inference-count check is a completion check.** The stock runner prints
`Total number of inferences: 1` as a string literal, not a counter; requiring it
verifies that execution reached post-inference code, and must not be described
as counting inferences.

**8.6 Determinism is exact, and that is the point.** `M1 == M2 == M3` held on
74/74 simulated cells, so the repetitions are not a statistical sample; no mean,
median, or confidence interval is reported for them. Board repetitions are
physical observations where equality is not required, and are reported as raw
triplets with a median.

**8.7 Board scope.** One physical configuration (U85 @ 1024) means no physical
scaling validation is possible; simulation and board binaries are
target-specific, so any absolute deviation would include build differences;
board `SRAM_*`/`EXT_*` counters have no counterpart in the frozen simulated
records. No aggregate deviation or repeatability-variability statistic is
reported, because none was preregistered.

**8.8 Mechanism-study attribution bounds.** Where small operations merge into
one interrupt-service window, per-operation cause is `NOT_EVALUABLE` and only
the operation-group effect is evaluable — for `rnnoise`, only 3 of 44
operations are individually separable, and its decomposition floor is the
14-group common partition. Each service boundary carries a small deterministic
cycle residual, so group and whole-model sums agree within that residual.
`dnn_s` profiled arms are `NOT_AVAILABLE`: its CPU-operator container uses a
schema feature outside the audited rewrite subset, and the instrumentation
failed closed rather than guessing.

**8.9 Memory-mode is not a bandwidth intervention.** It jointly moves weight
placement, arena headroom, compiler scheduling, and the generated command
stream; all mode pairs are different artifacts.

**8.10 Instrumentation-bridge bounds.** The overall U65 bridge verdict is
`NOT_EQUIVALENT` under its preregistered full-PMU-vector criterion. Execution
boundaries, attribution, and the cycle and active-cycle domains are established
as equivalent; exact cross-backend memory-traffic comparison is not qualified,
and the bridge does not establish cross-generation PMU-event equivalence. It
was run at U65-256 on two cells with a forced-legacy clean program; other
command structures were not exercised. Historical U55/U65 per-layer data is
therefore usable for cycle-domain mechanism observations on its own program,
and is not an exact decomposition of the frozen regor formal executables.

**8.11 Hardware geometry versus compiler scheduling is not causally
separated** anywhere in this work, and no claim in Section 6 asserts otherwise.

**8.12 Scope.** All simulated values are cycle-model observations on TA-enabled
configurations with a stock single-inference runner; all board values are
software-visible observations on one physical configuration. Workloads are the
MLEK set — representative of embedded ML, not exhaustive.

---

*Integration status: RQ1/RQ2/RQ3 and the U85 mechanism study are integrated
with their limitations. Frozen sources: `paper-fvp-analysis-results-frozen`,
`paper-board-rq3-analysis-results-frozen`, `paper-fvp-narrative-frozen`,
`paper-u85-mechanism-derived-frozen`, `paper-u85-p1a-frozen`,
`paper-u85-p1b-frozen`, `paper-u85-mechanism-narrative-frozen`,
`paper-u65-bridge-verdict-frozen`. STOP for full-paper review; no new
experiment is initiated by this integration.*
