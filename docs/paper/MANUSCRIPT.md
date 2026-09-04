# Characterizing Arm Ethos-U NPU Configurations: Simulated Scaling, Hardware Validation, and an Operator-Level Mechanism Study

Integrated manuscript draft. Assembled from frozen evidence only
(`paper-fvp-*`, `paper-board-*`, `paper-u85-*`, `paper-u65-bridge-*`,
`paper-platform-sensitivity-*`); last revised 2026-09-04. No new metric,
threshold, correlation, or measurement is introduced by revision. All five
figures are regenerated from the frozen CSVs by
`docs/paper/figures/make_figures.py`, whose per-figure provenance records name
the source artifact, the columns used and the interpretation each figure
refuses. Statements carry the evidence vocabulary used throughout the campaign:
`ASSOCIATED_WITH`, `CONSISTENT_WITH`, `NOT_SEPARATED`, `NOT_EVALUABLE`.

---

## Abstract

Embedded ML deployment on Arm Ethos-U NPUs forces configuration choices —
NPU generation, MAC count, memory mode, host subsystem — long before hardware
exists, and those choices are made from compiler estimates and cycle-model
simulation. We characterize what those tools actually support. Across a
133-cell capability universe we identify 74 executable, timing-adapter-enabled
cells and measure them under a byte-reproducible provenance chain (222
samples), validate one configuration on physical Corstone-320 / Ethos-U85
hardware (21 samples), and decompose the single configuration transition where
more MAC capacity measured *slower*.

Three primary findings follow. **Scaling is workload-dependent and mostly sub-linear**:
of 53 adjacent MAC transitions, 28 retain at least 75 % efficiency and 23 fall
between 50 % and 75 %, and saturation appears in only one of 21 ladders within
the tested range. **One boundary is non-monotonic**: Ethos-U85 at 256 → 512
MACs makes `rnnoise` slower, and direct operation-group profiling shows the
+19,000-cycle reversal is *distributed* over ten operation groups rather than
caused by any single structural change — the same groups regress under every
memory configuration tested, while a compiler-visible ublock change accompanies
roughly 95 % of operations in every direction class and therefore does not
discriminate. **Compiler estimates preserve structure better than magnitude**:
Vela matches the simulated saturation classification and speedup ordering in
19 of 20 ladders while per-step agreement varies widely.

Two results validate these findings rather than extending them.
**Structural conclusions transfer better than labels**: in a same-artifact study across
supported Corstone FVPs, workload ranking, scaling direction, saturation and
normalized ordering are preserved, whereas threshold-based efficiency classes
are more sensitive to timing-model configuration; on hardware, workload
ordering is preserved exactly at the one measurable configuration.

We do not compare absolute cycles across generations, simulators or hardware,
and we do not attribute the non-monotonicity to a single architectural or
compiler factor; both remain outside what this evidence can separate.

---

## 1. Introduction

Embedded ML deployment on Arm Ethos-U NPUs requires choosing among NPU
generations, MAC configurations, memory modes, and host subsystems — usually
before any hardware exists. Practitioners make those choices from compiler
estimates and cycle-model simulation, then discover on hardware what the
estimates did not carry.

**Thesis.** Increasing MAC capacity does not yield proportional performance
gains: scaling behaviour is workload-dependent and can become non-monotonic;
where it does become non-monotonic, that transition is shaped by heterogeneous
operation-level and memory/compiler interactions rather than by any single
structural change; and the structural conclusions drawn from simulation
transfer across the tested platform and timing conditions, whereas
threshold-based labels proved sensitive to timing-model configuration and raw
cross-platform cycles are not comparable at all.

We ask:

- **RQ1** — How do normalized scaling behaviour, workload ordering, and
  deployability differ across the supported Corstone/Ethos-U configurations?
  *(Deliberately not "which generation is faster": Section 3.3 sets out why
  absolute cross-generation cycle comparison is not admissible on this stack,
  and no result in this paper depends on one.)*
- **RQ2** — How does performance scale with MAC configuration, and where does
  scaling saturate?
- **RQ3** — To what extent do qualitative trends observed for Corstone-320 /
  Ethos-U85 in simulation reproduce on physical MPS4/FI101 hardware?
- **RQ4** — For the one configuration transition where more hardware measured
  *slower* — Ethos-U85, 256 → 512 MACs — what operator-level behaviour produces
  that whole-model non-monotonicity, and how robust is it to memory
  configuration?

**Primary contributions.**

1. **A systematic MAC-scaling characterization** over a 133-cell capability
   universe and a 74-cell formal simulated sweep (222 samples) with byte-level
   artifact provenance, in which **executability is reported as a first-class
   result** rather than as missing data: all 133 cells compile and 6 cannot
   run.
2. **An operator-level mechanism study of a non-monotonic boundary.** Using a
   post-compilation instrumentation path built and qualified for this purpose,
   we show the Ethos-U85 256 → 512 reversal is distributed across operation
   groups, recurs in the same groups under every tested memory configuration,
   and is not discriminated by any single compiler-visible transition.
3. **A characterization of compiler cost estimates against simulation**,
   separating what Vela's performance model predicts well (saturation
   classification, speedup ordering) from what it does not (individual
   MAC-step magnitude).

**Validation and supporting results.**

4. **Physical-board ordering validation** on Corstone-320 / Ethos-U85 (21
   formal samples), reporting ranking preservation and relative-cost shape,
   with absolute simulation-versus-hardware comparison refused by construction.
5. **Platform-sensitivity robustness.** A same-artifact study across supported
   Corstone FVPs establishes which structural metrics survive a change of host
   platform and which do not.
6. **Instrumentation qualification**, including a cross-backend bridge that
   bounds what per-layer numbers from two different instrumentation methods may
   be used for.

Alongside these we report measurement-methodology results that generalize
beyond this study: a simulator's timing adapter can silently change what is
being measured, and a compiler backend change can silently change which program
is being instrumented.

## 2. Background

**Ethos-U family.** Ethos-U55, U65, and U85 differ in MAC array size options,
memory interfaces, and PMU event spaces. For the two generations this study
sweeps most widely, the discrete MAC configurations are defined in their
respective technical reference manuals: the `macs_per_cc` field admits 32–256
MACs/clock cycle on Ethos-U55 [16], and 256 or 512 on Ethos-U65 [17], the
latter also differing in shared-buffer size between its two configurations.
Which PMU event names a generation actually emits is not taken from
documentation in this work but established empirically (Section 9.4).
Vela compiles a quantized TFLite
network into an Ethos-U command stream embedded as a custom operator payload;
the core driver submits that payload and the NPU executes it.

**Corstone subsystems.** Corstone-300, -310, -315, and -320 are reference
subsystems pairing a Cortex-M host with an Ethos-U NPU, each available as a
Fast Models FVP and, for Corstone-320, as an MPS4 FPGA implementation.

**The four subsystems do not play the same role here.** They are not four
interchangeable measurement platforms, and this paper never presents them as one
performance series. Two of them carry an enabled timing adapter and serve as
*primary measurement substrates* — Corstone-300 for Ethos-U55 and U65, and
Corstone-320 for Ethos-U85, which is also the configuration validated on
physical hardware. The other two have the adapter disabled and appear only as
*diagnostic substrates*: they are used to ask whether a structural conclusion
survives a change of host platform, never as a source of performance figures.
Section 3.1 states the roles and the reason; Section 9.1 states the consequence
for what the matrix can support.

**Timing adapter.** Verification platforms do not reproduce target-silicon
memory timing: an FVP models ideal memory by default, and an FPGA runs the NPU
at a low clock where memory appears disproportionately fast. The Ethos-U timing
adapter (TA) sits on the NPU's AXI paths and injects latency and bandwidth
constraints so that measurements reflect a modelled memory system. It is a
verification component, not part of production silicon. Its presence or absence
determines whether a cycle count means anything as a performance figure —
Section 3.1 and Section 9.1.

### 2.1 Related work

**Accelerator characterization and scaling models.** SCALE-Sim and Timeloop
characterize systolic-array accelerators with analytical and cycle-level
models: SCALE-Sim models a configurable systolic array and
studies how bandwidth, dataflow and array aspect ratio shape runtime [10], and
Timeloop searches the mapping space to project performance and energy for a
given architecture [11]. The canonical measured account of a production
systolic accelerator is the TPU analysis [9], which reports datapath and
memory-system behaviour for a datacenter part. These establish the vocabulary
we reuse — MAC-array configuration, dataflow, memory-system pressure — but they
model or measure a design, whereas the question here is what a *deployment
toolchain* tells a practitioner about a fixed IP across its supported
configurations.

**TinyML benchmarking.** MLPerf Tiny standardizes end-to-end latency, accuracy
and energy measurement for microcontroller-class systems [13]; the workloads we
use are drawn from that lineage, including MicroNet keyword spotting [14], and
run on TensorFlow Lite Micro [15]. MLPerf Tiny reports system-level outcomes by
design, at whole-inference granularity [13]; this work additionally decomposes
one configuration transition to the operation level on a specific NPU
(Section 7).

**Simulator-versus-hardware validation.** Validating a simulator against
silicon is an established methodology concern: Gutierrez et al. validate a
full-system CPU simulator against an Arm development board and report mean
absolute runtime errors in the 13–17 % range after targeted corrections [12].
Our board work is deliberately weaker in its claim — we validate *ordinal and
relative-cost structure* at the one physically available configuration rather
than absolute cycle agreement (Section 6) — because the simulated and physical
builds are target-specific and the two do not share a timing domain.

**Arm Ethos-U toolchain.** The platform documentation is primary evidence for
this study rather than related work: the Ethos-U85 NPU manuals define its MAC
configurations and PMU event space [1, 2], the Ethos-U55 and Ethos-U65 manuals
define the discrete MAC configurations of those generations [16, 17], the ML
developers guide describes
the NPU/compiler relationship [3], the Corstone-320 reference package and its
Fixed Virtual Platform define the simulated subsystem [4, 5, 6], the Vela
compiler produces both the command stream and the performance estimates we
treat as predictions — its own documentation labels those estimates
experimental [7] — and the ML Embedded Evaluation Kit supplies the runner and
build system used for every measurement [8].

**Position.** Relative to this body of work we contribute measurement rather
than modelling, at the configuration granularity a deployer actually chooses,
with an operator-level decomposition of a specific non-monotonic boundary and
an explicit account of which comparisons the evidence cannot support.

## 3. Methodology

### 3.1 Platforms and configurations

Valid configurations are established by capability audit rather than from
documentation. FVP parameter acceptance is not used as the authority for
discrete MAC support. Supported MAC configurations are established from the
Vela/source-defined discrete configuration set and independently confirmed by
FVP initialization probes; a configuration is admitted only where both agree.
On the pinned stack the two authorities agree on every probed cell.

Each simulated platform therefore plays a distinct role in this study, and the
roles are not interchangeable:

| platform | NPU | timing adapter | role in this paper |
| --- | --- | --- | --- |
| SSE-300 | U55, U65 | `TA_ON` | primary memory-aware simulated substrate |
| SSE-310 | U55, U65 | `TA_OFF` | diagnostic / platform-sensitivity control |
| SSE-315 | U65 | `TA_OFF` | U65-specific diagnostic reference substrate |
| SSE-320 | U85 | `TA_ON` | primary U85 substrate and hardware-validation anchor |

The distinction that matters throughout is **primary measurement substrate**
versus **diagnostic/robustness substrate**. Performance results are reported
only from the former; the latter appear only where a comparison is explicitly
structural (Section 5). The four platforms are never presented as one
absolute-performance series.

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

Seven fully NPU-placed INT8 models from the MLEK resource set span **468×** in
Vela-estimated cycles, which is the dynamic range the scaling and saturation
questions need:

| model | domain | Vela `cycles_total` |
| --- | --- | ---: |
| `rnnoise_INT8` | noise reduction | 37,836 |
| `kws_micronet_m` | keyword spotting | 217,565 |
| `ad_medium_int8` | anomaly detection | 452,112 |
| `vww4_128_128_INT8` | visual wake words | 477,109 |
| `yolo-fastest_192_face_v4` | object detection | 1,300,857 |
| `mobilenet_v2_1.0_224_INT8` | image classification | 4,896,641 |
| `wav2letter_pruned_int8` | speech recognition | 17,718,837 |

Estimates are the frozen Vela matrix at `SSE-320 / ethos-u85-256 /
Dedicated_Sram`, one configuration chosen so the column is internally
comparable; the span is the ratio of the largest to the smallest entry. All
seven place 100 % of their operators on the NPU. `dnn_s_quantized` is excluded from scaling analysis
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
(V13–V15) established the boundary; their closing statements and per-campaign
evidence are frozen under `docs/superpowers/evidence/` rather than reproduced
here, and the tags are listed with the other frozen sources at the end of this
document. V13 showed the observed timing variation
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
enters the comparison). Results and their limits are in Section 7.5; the
preregistered verdict is `NOT_EQUIVALENT` on the full PMU vector, with
component-level equivalence established for execution boundaries, attribution,
and the cycle and active-cycle domains.

**Provenance and procedure** — the identity chain each formal cell carries, the
build-reproducibility condition, the repetition and invalid-run rules, and the
analysis-plan discipline — are set out in Appendix B.

### 3.6 Cross-platform sensitivity validation design

The structural metrics above are used to compare configurations that do not
share an absolute cycle axis, which raises a validity question: do those
metrics survive a change of host platform at all? A separate same-artifact
validation answers it for the pairs this stack supports.

Each validation cell holds **model, NPU, MAC configuration and the exact Vela
NPU artifact fixed**, and changes only the Corstone/FVP platform. Artifact
identity is a hard gate: one artifact is compiled per (workload, NPU, MAC),
its SHA-256 must match across every platform in its comparison set, and the
identical artifact file is built into each platform's firmware. The complete
executable necessarily differs — the host firmware is platform-specific — so
the relation is recorded as
`FIRMWARE_PLATFORM_SPECIFIC_BUT_NPU_ARTIFACT_IDENTICAL` and never as "the same
binary".

Because timing-adapter state is not free to vary independently (Section 3.1),
comparisons are split and never pooled:

```
CLASS A   same TA state      U65: SSE-310 ↔ SSE-315   (TA_OFF ↔ TA_OFF)
CLASS B   TA state differs   U55: SSE-300 ↔ SSE-310
                             U65: SSE-300 ↔ SSE-310, SSE-300 ↔ SSE-315
```

Universe: 92 cells — U55 across MAC {32,64,128,256} on two platforms, U65
across MAC {256,512} on three — with the workload set per MAC point taken from
the frozen executability intersection. Acquisition reuses the qualified clean
whole-model path (three fresh simulator processes per cell, exact vector
equality required); determinism was re-qualified on a representative subset
before the formal contract was applied. Metric definitions are reused
unchanged; no aggregate robustness score is defined.

Note the deliberate boundary: the TA-OFF platforms enter this study as
**validation** subjects for metric behaviour, not as sources of performance
figures. They remain excluded from the performance analysis of Section 4, and
no cross-platform cycle ratio is computed in this validation.

## 4. Cross-generation simulated characterization (RQ1, RQ2)

Formal sweep: 74 executable TA-ON cells, 222 samples, `M1 == M2 == M3` on
74/74 across 19 equality-bearing fields.

### 4.1 MAC scaling and saturation (RQ2)

Figure 1 shows the scaling ladders, one panel per platform/NPU. Across 21
preregistered ladders, 53 adjacent MAC transitions were evaluable:

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

![Cumulative scaling efficiency within each platform and NPU. Each panel is
normalized to its own MAC baseline; the panels share no absolute axis and must
not be read across as a cross-generation performance comparison. Dashed line:
the frozen 0.75 `STRONG` threshold.](figures/fig1_mac_scaling.svg)

**Figure 1.** Cumulative scaling efficiency, timing-adapter-enabled platforms
only. Within-platform comparison only.

The single observed saturation point is the entry point for Section 7.

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
than in directly comparable absolute cycle values. Concretely, across the three
axes the question names: **deployability differed** — six cells were
non-executable, all `wav2letter_pruned_int8` × Ethos-U55 × `Shared_Sram`
(Section 4.4); **saturation differed** — the only observed instance in the
tested range is one Ethos-U85 ladder (Section 4.1); and **workload ordering did
not differ**, remaining invariant across configurations (`rho == 1.0` in 31/55
pairs, minimum 0.9429, median 1.0000; Section 4.3). *Not established:* any "U85
is faster than U55" statement — Fast Models version skew and timing-adapter
differences make absolute cross-generation comparison unsupportable on this
data.

## 5. Validity of the structural metrics across platform and timing conditions

**This section answers no research question.** Sections 4, 6 and 7 use
normalized, ordinal and threshold metrics to compare configurations that share
no absolute cycle axis; this section asks whether those metrics survive a change
of host platform at all. It is a validity check on the instruments of the study,
reported before the results that depend on it, and it is deliberately not
numbered among RQ1–RQ4.

92 cells, 276 samples, all vector-exact; 39/39 artifacts reproduced their
frozen hashes, so every comparison below is a same-NPU-artifact comparison.
Zero artifact-identity failures and zero rule failures.

Ranking agreement means identical order *and* Spearman `rho = 1.0` at that MAC
point. The two classes are reported separately and are not combined into a
single rate; per-metric agreement counts and their qualification are given
together below.

**The only disagreements are eight scaling-class labels**, all in CLASS B, and
every one is `PARTIAL` on the TA_ON side and `STRONG` on the TA_OFF side —
adjacent efficiencies of 0.64–0.75 against 0.77–0.86, i.e. crossings of the
frozen 0.75 cut point in a single direction. No ranking, direction or
saturation verdict changed anywhere.

In CLASS A the agreement is exact in a stronger sense: **14/14 tested cells had
exactly identical canonical NPU cycles** on SSE-310 and SSE-315. Stated
narrowly — under the tested TA-OFF condition, changing from SSE-310 to SSE-315
produced no observable change in canonical NPU cycles for any of the 14
evaluated cells (`NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR`).
This observation does not establish that subsystem or Fast-Models differences
are generally irrelevant, nor does it transfer to TA-ON conditions, which is
`NOT_EVALUABLE` here because no platform pair on this stack holds TA constant
at TA_ON.

All observed scaling-class disagreements occurred in comparisons where TA state
also differed; they are `ASSOCIATED_WITH` those comparisons and are not
attributed to any one factor, because in CLASS B the subsystem, the Fast Models
implementation and the TA state change together and remain `NOT_SEPARATED`.
What this does and does not license is discussed in Section 8.

Resulting qualification of the metrics, as categories rather than scores. This
table is the metric hierarchy the rest of the paper relies on: a reader scanning
results should not give a threshold class the same weight as an ordinal one.

| metric | tested universe | agreement | qualification |
| --- | --- | ---: | --- |
| workload ranking | 2 (A) + 8 (B) MAC points | 2/2, 8/8 | `ROBUST_IN_TESTED_PAIRS` |
| MAC-step direction | 7 (A) + 32 (B) steps | 7/7, 32/32 | `ROBUST_IN_TESTED_PAIRS` |
| saturation verdict | 7 (A) + 20 (B) ladders | 7/7, 20/20 | `ROBUST_IN_TESTED_PAIRS` |
| normalized workload ordering | 2 (A) + 8 (B) MAC points | 2/2, 8/8 | `ROBUST_IN_TESTED_PAIRS` |
| threshold scaling class | 7 (A) + 32 (B) steps | 7/7, **24/32** | `TA_STATE_SENSITIVE` |
| raw cross-platform cycles | — | — | `NOT_COMPARABLE` |
| memory PMU counters | — | — | `GENERATION_SPECIFIC_NOT_COMMON` |
| transfer of the CLASS A result to TA_ON | — | — | `NOT_EVALUABLE` |

CLASS A and CLASS B counts are listed side by side. No aggregate robustness
score is defined.

![Agreement of each structural metric across a change of Corstone platform,
CLASS A and CLASS B shown separately and never pooled. The only disagreements
are eight threshold scaling-class labels, all in CLASS B.](figures/fig2_platform_sensitivity.svg)

**Figure 2.** Metric agreement across the tested platform pairs, same NPU and
byte-identical Vela artifact. Not a platform performance comparison.

## 6. Corstone-320 hardware validation (RQ3)

The board contributes exactly one matrix cell: Corstone-320 / U85 @ 1024 MACs,
seven workloads, three independent fresh boots — **21 formal samples**.

**The protocol was corrected before any formal sample existed.** The registered
3 boots × 10 runs design was not executable: the stock runner performs exactly
one inference per boot, and "ten consecutive runs" was a capability of a custom
runner used in earlier campaigns. Since patching the artifact under test was
not authorized, the protocol became 3 boots × 1 stock inference = 21 samples,
recorded as a supersession. Canonical value per workload is `median(B1,B2,B3)`.

**Ranking preservation (primary).** Spearman `rho = 1.0`, **0 rank inversions**
across all seven workloads: every workload holds the same position in the
simulated and the physical ordering. The rank pairs are tabulated in
Appendix A.

**Relative cost shape (secondary).** Each domain is normalized by its own
geometric mean; Figure 3 shows the two vectors and Appendix A gives the exact
values.

The two vectors are presented side by side. **No aggregate deviation metric is
computed**: `L1`, `L2`, RMSE, mean absolute percentage, and the board/FVP ratio
were never preregistered, and selecting one with both vectors visible would be
choosing a statistic to fit the result. Board repeatability is reported as the
raw triplet plus median, with no spread statistic, for the same reason.

![Simulated and physical relative workload cost, each normalized within its own
domain by its own geometric mean. Ranking is preserved exactly. No deviation,
ratio or error statistic is shown.](figures/fig3_board_relative_cost.svg)

**Figure 3.** Relative cost shape, FVP and board, independently normalized. The
two vectors are shapes to compare, not magnitudes; absolute
simulation-versus-hardware comparison is refused by construction.

Whether `rho = 1.0` constitutes strong validation is a judgement, not a
threshold result: no pass/fail criterion was invented to declare it one. What
this transfer does and does not establish is discussed in Section 8.

PMU cross-target status: `TOTAL`/`ACTIVE`/`IDLE` are present in both frozen
sets but no board canonicalization across boots was preregistered;
`SRAM_*`/`EXT_*` are board-collectable but absent from the frozen simulated
records, hence `NOT_EVALUABLE`. The frozen stages were not re-run to obtain
them.

## 7. Operator-level mechanism study: U85 256 → 512 (RQ4)

### 7.1 The anomaly and its scope

Among the seven scaling workloads, exactly one becomes slower when the U85 doubles
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

### 7.2 Instrumentation

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

### 7.3 The reversal is distributed, not localized

For `rnnoise` at the sweep baseline, the +19,000-cycle reversal decomposes into
**ten regressing groups of +1,000 to +4,030 cycles each**, with a single
improving group (−1,000). The profiled groups sum to +19,060 rather than the
+19,000 observed without instrumentation; the 60-cycle difference is the
deterministic profiling-boundary residual of Section 9.5, and the two figures
are reported separately rather than as one number. The largest contributor accounts for roughly a fifth
of the whole-model delta. **No single pathological operation or group explains
the reversal.** The regressing groups comprise small elementwise clusters
(Add/Mul/Sub/Pack), small fully-connected operations, and Concat/Quantize —
the workload's abundant low-arithmetic operations rather than its few large
matrix operations.

![Per-operation-group cycle change for rnnoise at the Ethos-U85 256 to 512
transition: ten groups regress, one improves, three are unchanged. The
reconstructed profiled-group delta is +19,060 against a whole-model observed
delta of +19,000, a residual of 60 cycles. Bars show where cycles moved, not
why.](figures/fig4_u85_group_delta.svg)

**Figure 4.** Distribution of the reversal across the frozen 14-group common
attribution partition. The **whole-model observed delta is +19,000** cycles
(Section 7.1); the **reconstructed profiled-group delta is +19,060**, and the
**60-cycle residual** is the deterministic profiling-boundary
(interrupt-service) residual described in Section 9.5 — the two measurement
boundaries are not identical and the figure does not treat them as one. No group
is claimed as the cause of the whole-model change; inside a merged
interrupt-service window only the group effect is evaluable.

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

### 7.4 Robustness to memory configuration

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

![rnnoise operation-group deltas under Sram_Only, Shared_Sram and
Dedicated_Sram. The same groups regress in every configuration; magnitude
changes, direction does not.](figures/fig5_u85_memory_robustness.svg)

**Figure 5.** Cross-memory robustness of the regressing groups. Every mode
compiles to a different artifact, so memory-system behaviour and
compiler-generated program change remain `NOT_SEPARATED`; this is a
configuration intervention, not a bandwidth intervention.

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

### 7.5 Cross-backend instrumentation bridge (U65)

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

### 7.6 Summary of the mechanism measurements

Three measurement outcomes close this section.

1. The 256 → 512 transition produces **heterogeneous operator-level cost changes
   in both directions**: some operations gain from the larger MAC array, others
   lose, and the whole-model outcome is the aggregate of that balance rather
   than the behaviour of any single group.
2. `UBLOCK_CHANGED` accompanies roughly 95 % of operations in **every** direction
   class, so it does not discriminate regressing operations from improving ones.
3. Memory configuration modulates the magnitude of the group deltas and, for
   some groups, their direction, while every memory mode compiles to a different
   artifact.

The framing these outcomes support, and the single-factor account they retire,
are in Section 8.

## 8. Discussion

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

**What the mechanism evidence supports, and what it retires.** The evidence
supports one framing and retires another. *Supported — emergence from
heterogeneous local changes.* Whether a whole model improves or regresses across
a MAC transition is the aggregate outcome of a balance between operation groups
that gain and operation groups that lose:

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

*Retired — the single-factor ublock account.* "Ublock enlargement causes the
regression" is not supported: ublock change is a ~95 % background rate in every
direction class. What the small-operation composition of the regressing clusters
licenses is that the observations are `CONSISTENT_WITH` a small-spatial /
low-arithmetic-utilization account, while remaining `NOT_SEPARATED` from the
compiler-scheduling changes that accompany the same transition. Memory
configuration modulates both magnitude and, for some groups, direction, but
single-factor claims ("shared-SRAM contention causes…", "bandwidth causes…") are
unavailable: the memory-mode axis is a configuration intervention, not a
bandwidth intervention, and every mode is a different artifact.

**What the board comparison establishes.** It establishes that **ordinal
structure and relative cost shape transfer from the cycle model to this hardware
configuration**, and nothing about absolute agreement. The two builds are
target-specific — FVP and FPGA binaries are not interchangeable for
Corstone-320 — so any absolute deviation would also include whatever those
builds differ in, which is why no deviation statistic is reported at all.

**Which metrics transfer across platform and timing conditions.** The
same-artifact validation turns a previously implicit assumption into a measured
one. Ordinal and directional conclusions were preserved across the tested
platform pairs, whereas threshold-based scaling classes were more sensitive to
timing-model configuration. That yields a practical hierarchy: workload
ordering, scaling direction, saturation verdicts and normalized ordering
carried across every tested pair; a class label defined by a fixed efficiency
cut point did not, because values sitting near the cut point can cross it;
and raw cross-platform cycles remain outside the comparable set entirely.
Readers reproducing this kind of study on a different simulator stack should
expect the ordinal layer to travel and the thresholded layer to need
re-qualification. The eight disagreements license a scoped statement and no
more: they occurred only where timing-adapter state also differed, and since the
subsystem, the Fast Models implementation and the adapter state change together
in those comparisons, no one of the three can be named as the factor
responsible.

**Measurement methodology results.** Four are reusable beyond this study.
(i) A simulator's timing-adapter configuration can silently change what is
being measured: the same NPU artifact exhibited a large cycle difference — a
byte-identical command stream measured ~4× apart — between the SSE-300 and
SSE-310 conditions, and nothing in the cycle counts signalled it. Because
timing-adapter state, subsystem and Fast Models timing implementation differ
together across that pair, the magnitude cannot be attributed to the timing
adapter alone; the three contributions are `NOT_SEPARATED` (Section 9.2). The
observation is therefore treated as a methodology warning against raw
cross-platform cycle comparison, not as a performance result. (ii) A compiler
backend change can silently change which program is instrumented: the default
`regor` routing means legacy-core instrumentation decomposes a different binary
than the formal sweep executes — which is why this paper separates the three
paths explicitly. (iii) Firmware embedding its own build timestamp is not
byte-reproducible until the build epoch is pinned to source identity. (iv)
Executability classification belongs before the sweep: the formal sample count
could not be fixed until the filter ran (399 assumed; 222 actual).

## 9. Limitations

Fourteen limitations are recorded, grouped here under six themes. The grouping
changes their presentation only; none has been withdrawn or softened. Read as a
whole they say something specific rather than something global: the ordinal and
structural results of this paper are established, the threshold-based labels are
established only under the timing conditions tested, and a small number of
questions — chiefly which of several co-varying factors produces an observed
effect — remain **not separable** with this evidence and are marked as such
wherever they arise.

### 9.1 Simulation and timing-model validity

**The timing adapter splits the matrix.** Only 11 of 19 configurations are
benchmarking-valid; the 56 TA-OFF cells are capability and diagnostic evidence
only. A claim retracted during this work: "same NPU across different Corstone
generations" is not a clean platform isolation, because the two sides differ in
adapter state — a memory-constrained model against an unconstrained one.

**Determinism is exact, and that is the point.** `M1 == M2 == M3` held on
74/74 simulated cells, so the repetitions are not a statistical sample; no mean,
median, or confidence interval is reported for them. Board repetitions are
physical observations where equality is not required, and are reported as raw
triplets with a median.

**Scope.** All simulated values are cycle-model observations on TA-enabled
configurations with a stock single-inference runner; all board values are
software-visible observations on one physical configuration. Workloads are the
MLEK set — representative of embedded ML, not exhaustive.

### 9.2 Cross-platform and cross-generation comparability

**Absolute cross-generation comparison is unsupportable.** Fast Models version
skew and platform configuration differences confound it; comparisons are
restricted to normalized scaling and ordinal ranking.

**`SSE-300 / U55@256` versus `U65@256` is a system-level configuration
comparison**, not a microarchitecture result: the memory mode differs by NPU
(`Shared_Sram` versus `Dedicated_Sram`), moving weights between SRAM and DRAM.

**Platform-sensitivity validation bounds.** The validation covers U55 and U65 on
the platform pairs this stack supports; three bounds follow. There is **no
same-platform U65-versus-U85 controlled pair**, so cross-generation statements
involving U85 rest on structural metrics rather than a controlled substrate.
There is **no TA_ON cross-FVP control pair**, so the CLASS A result exists only
under TA_OFF and its transfer to TA_ON is `NOT_EVALUABLE`. In CLASS B the
timing-adapter state, the subsystem and the Fast Models implementation change
together, so their contributions are `NOT_SEPARATED`; the eight class
disagreements are reported as associated with those comparisons, never as caused
by any one of the three.

### 9.3 Compiler and instrumentation paths

**Instrumentation-bridge bounds.** The overall U65 bridge verdict is
`NOT_EQUIVALENT` under its preregistered full-PMU-vector criterion. Execution
boundaries, attribution, and the cycle and active-cycle domains are established
as equivalent; exact cross-backend memory-traffic comparison is not qualified,
and the bridge does not establish cross-generation PMU-event equivalence. It
was run at U65-256 on two cells with a forced-legacy clean program; other
command structures were not exercised. Historical U55/U65 per-layer data is
therefore usable for cycle-domain mechanism observations on its own program,
and is not an exact decomposition of the frozen regor formal executables.

**A withdrawn auxiliary observation.** An earlier auxiliary record reported that
an FVP accepted an unsupported `num_macs` value, and was used to argue that the
model range-checks bounds without validating the discrete set. The exact probe
invocation was not archived, the observation could not be reproduced under the
same Fast Models build during the X0 capability audit (three invocation styles
all reject, and the model enumerates the legal set in its own error), and it is
classified `NOT_REPRODUCIBLE` / `NOT_LOAD_BEARING`. No argument in this paper
rests on it; Section 3.1 states the authority rule directly instead.

### 9.4 PMU and runner-output semantic coverage

**PMU semantics are generation-conditional.** Only `CYCLE`, `NPU_IDLE`, and
`CC_STALLED_ON_BLOCKDEP` were verified as common-semantics across generations;
of 22 shared event names, 18 differ in ordinal, so event numbers never cross a
generation boundary. `CC_STALLED_ON_BLOCKDEP` cross-generation and the U85
`EXT*`/`SRAM*` family were `NOT_EVALUABLE` — absences in what the stock runner
prints, and obtaining them would break the stock-runner contract under which
every formal measurement was taken. U85 stall-family events remain
`SEMANTICS_UNVERIFIED` and were never collected, so stall-based causal
attribution is `NOT_EVALUABLE` throughout Section 7.

**The inference-count check is a completion check.** The stock runner prints
`Total number of inferences: 1` as a string literal, not a counter; requiring it
verifies that execution reached post-inference code, and must not be described
as counting inferences.

### 9.5 Causal identifiability

**Mechanism-study attribution bounds.** Where small operations merge into one
interrupt-service window, per-operation cause is `NOT_EVALUABLE` and only the
operation-group effect is evaluable — for `rnnoise`, only 3 of 44 operations are
individually separable, and its decomposition floor is the 14-group common
partition. Each service boundary carries a small deterministic cycle residual,
so group and whole-model sums agree within that residual. `dnn_s` profiled arms
are `NOT_AVAILABLE`: its CPU-operator container uses a schema feature outside
the audited rewrite subset, and the instrumentation failed closed rather than
guessing.

**Memory-mode is not a bandwidth intervention.** It jointly moves weight
placement, arena headroom, compiler scheduling, and the generated command
stream; all mode pairs are different artifacts.

**Hardware geometry versus compiler scheduling is not causally separated**
anywhere in this work, and no claim in Section 7 asserts otherwise.

### 9.6 Physical-board scope

**Board scope.** One physical configuration (U85 @ 1024) means no physical
scaling validation is possible; simulation and board binaries are
target-specific, so any absolute deviation would include build differences;
board `SRAM_*`/`EXT_*` counters have no counterpart in the frozen simulated
records. No aggregate deviation or repeatability-variability statistic is
reported, because none was preregistered.

## 10. Conclusion

We set out to characterize what an embedded ML deployment toolchain actually
supports across the configurations a practitioner must choose between, and to
be explicit about which comparisons the resulting evidence cannot carry.

**MAC scaling is workload-dependent and frequently sub-linear (RQ2).** Of 53
adjacent MAC transitions, 28 retained at least 75 % efficiency and 23 fell
between 50 % and 75 %; saturation appeared in one of 21 ladders within the
tested range. More MAC capacity generally helps, and it generally helps less
than proportionally, by an amount that depends on the workload rather than on a
common saturation point.

**Structural conclusions travel better than thresholded labels (RQ1).**
Across a same-artifact study over the supported Corstone FVPs, workload ranking,
MAC-step direction, saturation verdict and normalized ordering were preserved in
every tested pair, while the threshold-based efficiency class disagreed in 8 of
32 CLASS B steps — all of them crossings of the frozen 0.75 cut point in one
direction. The configurations therefore differ in normalized scaling behaviour,
in deployability, and not in any directly comparable absolute cycle value:
deployability differed (six non-executable cells), saturation differed (one U85
ladder), and workload ordering did not differ at all.

**The one non-monotonic boundary is distributed, not localized (RQ4).**
Direct operation-group profiling of the Ethos-U85 256 → 512 transition shows
the +19,060-cycle `rnnoise` reversal spread across ten regressing groups against
one improving group, the largest about a fifth of the whole; the same groups
regress under every memory configuration tested while their magnitudes change.
A compiler-visible ublock change accompanies roughly 95 % of operations in every
direction class, so it does not discriminate regressing operations from
improving ones, and no single group or single compiler-visible transition
accounts for the reversal. Which of the co-varying factors produces it remains
`NOT_SEPARATED`.

**The three kinds of number are not interchangeable (RQ2, RQ3).** A Vela
estimate, an FVP observation and a physical observation play different
evidentiary roles here and are never placed on one axis. Vela preserved coarse
structure — saturation classification and normalized speedup ordering agreed in
19 of 20 ladders — while per-step class agreement ranged from 4/4 to 0/1, so
pruning a design space on predicted trend is supported by this data and ranking
candidates on predicted magnitude is not.

**Physical validation establishes order, not timing accuracy (RQ3).** At the one
configuration the hardware makes available — Corstone-320 / Ethos-U85 @ 1024
MACs, 21 formal samples — workload ranking was preserved exactly, with zero
inversions, and the independently normalized relative-cost vectors have the same
shape. This is evidence that ordinal structure transfers from the cycle model to
this hardware point. It is not evidence about absolute simulator timing
accuracy, which the target-specific builds make unavailable and which no result
here depends on.

Two limits bound all of the above and are stated in full in Section 9: the
comparisons rest on cycle-model observations under an enabled timing adapter
with a stock single-inference runner, and wherever several factors change
together — timing-adapter state with subsystem and Fast Models implementation,
memory mode with the compiled artifact, hardware geometry with compiler
scheduling — the contributions are reported as associated and never as separated.

The practical form of the result is short. A MAC upgrade must be validated per
workload, because a model dominated by many small, low-arithmetic operations can
lose more on those operations than it gains elsewhere, and the compiler estimate
will not necessarily reveal it: Vela predicted improvement for the one workload
that regressed.

## Appendix A. Exact values behind the board validation

Reproduced from `docs/paper/analysis/board_rq3/` so that the numbers behind
Section 6 and Figure 3 remain available without re-running the frozen analysis. Corstone-320 /
Ethos-U85 @ 1024 MACs, 21 formal samples, canonical value per workload
`median(B1,B2,B3)`.

**A.1 Rank preservation.**

| workload | FVP rank | board rank |
| --- | --- | --- |
| `rnnoise_INT8` | 1 | 1 |
| `kws_micronet_m` | 2 | 2 |
| `ad_medium_int8` | 3 | 3 |
| `vww4_128_128_INT8` | 4 | 4 |
| `yolo-fastest_192_face_v4` | 5 | 5 |
| `mobilenet_v2_1.0_224_INT8` | 6 | 6 |
| `wav2letter_pruned_int8` | 7 | 7 |

**A.2 Independently normalized relative cost.** Each domain is divided by its
own geometric mean. The two columns are shapes to compare, not magnitudes: no
ratio, difference, or error between them is computed anywhere in this paper.

| workload | FVP normalized | board normalized |
| --- | --- | --- |
| `rnnoise_INT8` | 0.1521 | 0.1619 |
| `kws_micronet_m` | 0.2791 | 0.2858 |
| `ad_medium_int8` | 0.4371 | 0.4459 |
| `vww4_128_128_INT8` | 0.7129 | 0.7027 |
| `yolo-fastest_192_face_v4` | 1.3606 | 1.3309 |
| `mobilenet_v2_1.0_224_INT8` | 4.3570 | 4.2680 |
| `wav2letter_pruned_int8` | 12.7514 | 12.1432 |

## Appendix B. Provenance and procedure

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

---

*Integration status: RQ1–RQ4 and the U85 mechanism study are integrated with
their limitations. Frozen sources: `paper-fvp-analysis-results-frozen`,
`paper-board-rq3-analysis-results-frozen`, `paper-fvp-narrative-frozen`,
`paper-u85-mechanism-derived-frozen`, `paper-u85-p1a-frozen`,
`paper-u85-p1b-frozen`, `paper-u85-mechanism-narrative-frozen`,
`paper-u65-bridge-verdict-frozen`,
`paper-platform-sensitivity-x1-results-frozen`,
`paper-platform-sensitivity-x3-results-frozen`. No new experiment is initiated
by this integration.*

---

## References

Arm platform documentation is cited as primary evidence for the measured
system; every entry below was verified against its source during review.

[1] Arm Ltd. *Arm Ethos-U85 NPU Technical Reference Manual*.
    developer.arm.com/documentation/102685

[2] Arm Ltd. *Arm Ethos-U85 NPU Technical Overview*.
    developer.arm.com/documentation/102684

[3] Arm Ltd. *ML Developers Guide for Cortex-M Processors and Ethos-U NPU*.
    developer.arm.com/documentation/109267

[4] Arm Ltd. *Arm Corstone-320 Reference Package Technical Overview*.
    developer.arm.com/documentation/109761

[5] Arm Ltd. *Fixed Virtual Platforms for Arm Corstone SSE-320*.
    developer.arm.com/documentation/109760

[6] Arm Ltd. *Fast Models Fixed Virtual Platforms (FVP) Reference Guide*.
    developer.arm.com/documentation/100966

[7] Arm Ltd. *Ethos-U Vela compiler*.
    review.mlplatform.org/plugins/gitiles/ml/ethos-u/ethos-u-vela

[8] Arm Ltd. *ML Embedded Evaluation Kit*.
    review.mlplatform.org/plugins/gitiles/ml/ethos-u/ml-embedded-evaluation-kit

[9] N. P. Jouppi et al. In-Datacenter Performance Analysis of a Tensor
    Processing Unit. *ISCA*, 2017. arXiv:1704.04760

[10] A. Samajdar, Y. Zhu, P. Whatmough, M. Mattina, T. Krishna. SCALE-Sim:
     Systolic CNN Accelerator Simulator. arXiv:1811.02883, 2018.

[11] A. Parashar, P. Raina, Y. S. Shao, Y.-H. Chen, V. A. Ying, A. Mukkara,
     R. Venkatesan, B. Khailany, S. W. Keckler, J. S. Emer. Timeloop: A
     Systematic Approach to DNN Accelerator Evaluation. *ISPASS*, 2019.

[12] A. Gutierrez, J. Pusdesris, R. G. Dreslinski, T. Mudge, C. Sudanthi,
     C. D. Emmons, M. Hayenga, N. Paver. Sources of Error in Full-System
     Simulation. *ISPASS*, 2014.

[13] C. Banbury, V. J. Reddi, P. Torelli, J. Holleman, N. Jeffries, C. Kiraly,
     P. Montino, D. Kanter, S. Ahmed, D. Pau, U. Thakker, A. Torrini,
     P. Warden, J. Cordaro, G. Di Guglielmo, J. Duarte, S. Gibellini,
     V. Parekh, H. Tran, N. Tran, N. Wenxu, X. Xuesong. MLPerf Tiny Benchmark.
     *NeurIPS Datasets and Benchmarks Track*, 2021. arXiv:2106.07597

[14] C. Banbury, C. Zhou, I. Fedorov, R. Matas, U. Thakker, D. Gope,
     V. J. Reddi, M. Mattina, P. Whatmough. MicroNets: Neural Network
     Architectures for Deploying TinyML Applications on Commodity
     Microcontrollers. *MLSys*, 2021. arXiv:2010.11267

[15] R. David, J. Duke, A. Jain, V. J. Reddi, N. Jeffries, J. Li, N. Kreeger,
     I. Nappier, M. Natraj, T. Wang, P. Warden, R. Rhodes. TensorFlow Lite
     Micro: Embedded Machine Learning for TinyML Systems. *MLSys*, 2021.

[16] Arm Ltd. *Arm Ethos-U55 NPU Technical Reference Manual*, revision r2p0,
     document ID 102420_0200_02_en. developer.arm.com/documentation/102420

[17] Arm Ltd. *Arm Ethos-U65 NPU Technical Reference Manual*, revision r0p0,
     document ID 102023_0000_06_en. developer.arm.com/documentation/102023
