# Stage X6 — Memory-service envelope identification on physical hardware

**Status: PLANNING / HOLD.** No manager GO. No board authorization. Nothing here
is a frozen contract — the contract freeze is a separate named step (below).

Successor to Stage X4 (`FUTURE_EXPERIMENT_PLAN.md` §3), which studied simulated
memory-service sensitivity on the FVP with the artifact fixed. X4 was executed
(`docs/paper/raw_data_report/amendments/A8_x4_timing_adapter_sweep.md`). This
stage moves the same axis onto the MPS4 board and widens it from one knob to a
full envelope.

## 0. Why this exists

The prior campaign produced **observations about workloads** ("RNNoise reverses
at 512 MAC"). The reference literature produces **characters of the machine** —
quantities defined before any workload is substituted in, onto which workloads
are then placed:

| reference | character | axis |
| --- | --- | --- |
| TPU (Jouppi ISCA'17) | ridge point | ops/byte |
| SCALE-Sim | feeding requirement as the array grows | bytes/cycle |
| Timeloop | achievable frontier of the mapping space | — |

This program derives machine characters for one fixed configuration
(Corstone-320 / Ethos-U85 / 1024 MAC) on physical hardware.

**Why the board and not the FVP.** Whether the measured latency-hiding
concurrency is a property of the RTL or an artefact of the FVP's timing model is
not answerable by the FVP. Arm's own FVP documentation disclaims accuracy of
cycle counts and low-level component interactions; latency-hiding concurrency is
exactly such an interaction. The MPS4 board runs Corstone-320 synthesised into
an FPGA, so its timing adapter and PMU are real RTL.

## 1. What is already established

All of the following is `POST_HOC_DESCRIPTIVE` — computed on frozen data after
the values were seen. None of it may serve as a confirmatory result.

### 1.1 Latency response is not affine over the full range

Fitting the asymptotic (high-latency) line per MAC configuration, FVP, RNNoise:

| MAC | C(L=0) | asymptotic line | residual at L = 0 / 250 / 500 / 1000 |
| ---: | ---: | --- | --- |
| 256 | 21,086 | 8,086 + 108·L | −13000 / −1000 / **0** / **0** |
| 512 | 16,086 | 5,086 + 96·L | −11000 / −2000 / **0** / **0** |
| 1024 | 11,086 | 3,086 + 92·L | −8000 / −2000 / **0** / **0** |
| 2048 | 11,086 | 6,086 + 96·L | −5000 / **0** / **0** / **0** |

Three regimes: latency-hiding → transition → exposed asymptote. `C(L=0)` is
**not** the intercept of the asymptotic line.

**Retracted claim.** An earlier working note asserted the additive form
`C = C₀ + k·L` predicted the shipped 256→512 transition exactly (+19,000). It
does not. With a common k = 96 the two predictions are each wrong by +9,000 and
the error cancels only in the difference. That agreement was arithmetic
coincidence, not model validation.

### 1.2 A concurrency saturation law is visible in the H1B data

From `docs/paper/raw_data_report/amendments/h13/h13_results.json`, k computed
between L = 250 and L = 1000:

| MAXR | k (256) | Q_eff (256) | k (512) | Q_eff (512) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 944.0 | 1.00 | 962.7 | 1.00 |
| 4 | 242.7 | 3.89 | 245.3 | 3.92 |
| 16 | 102.7 | 9.19 | 96.0 | 10.03 |
| 63 | 102.7 | 9.19 | 89.3 | 10.78 |
| unlimited | 102.7 | 9.19 | 89.3 | 10.78 |

Candidate law:

```
k_{p,N}(m) ≈ R_p / min(m, Q_N)
```

- `R` = 944 / 963 across two MAC configurations — a 2 % spread, consistent with
  R being a program property rather than a machine one.
- At MAXR 1→4, `Q_eff` = 3.89 / 3.92 against a nominal 4 — within 2 %.
- `Q_eff` saturates at 9.19 / 10.78; raising MAXR to 63 or unlimited changes
  nothing, so the externally imposed limit stops binding and some internal
  ceiling takes over.

### 1.3 A previously `NOT_SEPARATED` item is explained by this

The shipped profiles set `EXT_MAXR` to 24 (low) and 64 (mid, masked to
unlimited). Both are above `Q_eff ≈ 9–11`, so MAXR never binds in the shipped
configuration. This accounts for the X4 campaign-C observation that swapping
MAXR between 24 and unlimited changed the cycle count by zero.

### 1.4 FVP and board agree exactly on memory traffic at U85-1024

Same `model_sha256`, same `vela_sha256` (`5bc1ee08…`), same memory mode and
system config; the only build difference is `FPGA_PLATFORM_SSE_320`.

All four SRAM/EXT read-write beat counters matched the FVP reference exactly
across seven workloads and three independent board boots (84/84 counter
observations; 7/7 workloads passed the complete four-counter identity test).
Cycles differ by +0.5 % to +12.4 %, workload-dependent in magnitude.

This licenses a two-axis contract: **identity first, then timing**.

## 2. The model this program identifies

Per path `p ∈ {SRAM, EXT}` and direction `d ∈ {R, W}`:

```
X_{p,d}  ≲  min( J_{p,d} ,  min(m, Q_{p,d}) / L_{p,d} ,  B_{p,d} / g_{p,d} )
```

| symbol | meaning | kind |
| --- | --- | --- |
| `Q` | effective latency-hiding concurrency | machine |
| `B` | sustainable beat throughput | machine |
| `J` | request-issue ceiling (front-end) | machine |
| `P_C` | sustained useful MAC/cycle envelope | machine |
| `g` | beats per transaction | workload |
| `I_B`, `I_R` | ops per beat, ops per transaction | workload |
| `L` | effective memory-service latency | environment |
| `m` | externally imposed outstanding limit (TA MAXR) | environment |

With a workload substituted in:

```
P_w  ≤  min( P_C ,  I_B·B ,  I_R·Q/L ,  I_R·J )
```

`J` is a third roof, independent of latency and bandwidth: if at L ≈ 0 with
bandwidth unconstrained the transactions-per-cycle rate still saturates, that
ceiling is front-end request generation.

Memory-service ridge, before any workload is introduced:

```
L† = Q·g / B
```

## 3. Character inventory

| family | characters |
| --- | --- |
| Compute | `P_C` (via `MAC_ACTIVE`, `MAC_DPU_ACTIVE`) |
| Concurrency | `Q_{EXT,R}`, `Q_{EXT,W}`, `Q_{SRAM,R}`, `Q_{SRAM,W}` |
| Bandwidth | `B_{EXT,R/W}`, `B_{SRAM,R/W}` |
| Request issue | `J_{EXT,R/W}`, `J_{SRAM,R/W}` |
| Port behaviour | `Π_EXT`, `Π_SRAM` — striping across the two physical ports |
| Frontier | `F_RW` (achievable read/write region), `F_{EXT,SRAM}` (path interference) |
| Latency exposure | `H_{p,d}(L)`, decomposed per AXI channel |
| Derived balance | `Q_R/Q_W`, `Q_SRAM/Q_EXT`, `B_R/B_W` |

A frontier is a stronger character than a scalar ratio: a rectangular achievable
region implies independent resources, a triangular or curved one implies a
shared resource, an asymmetric one implies priority.

## 4. Verified platform facts

Checked directly in this repository / the build container. Anything not listed
here is unverified.

| fact | evidence |
| --- | --- |
| TA is active on the board build | `source/hal/source/platform/mps4/CMakeLists.txt`: `FPGA_PLATFORM_SSE_320` → `TA_SRAM_BASE 0x51102000`, `TA_EXT_BASE 0x51102400`. Board B1/B2/B3 UART logs print exactly these addresses. |
| TA values need no source patch | `host/campaigns/build.py` forwards arbitrary `-D` through `target["cmake_options"]` / `options["cmake_options"]`, and `verify_cache` confirms they landed. |
| Board baseline TA profile | `scripts/cmake/configuration_options/npu_opts.cmake`: `Z1024 ∈ U85_TA_MID` → `ta_config_u85_sys_dram_mid` = `EXT_RLATENCY 500`, `EXT_MAXR 64` (masked to unlimited by `TA_MAXR_MASK 0x3F`). |
| PMU slots | `ETHOSU_PMU_NCOUNTERS = 8` for U85; `ETHOSU_USED_PMU_NCOUNTERS = 5` in `ethosu_profiler.h`. Three free. |
| `NPU IDLE` is derived | `ethosu_profiler.c` computes `npu_total_ccnt − npu_evt_counters[0]`. Not an independent counter. |
| PMU instrumentation was non-perturbing in one test | FVP probe, RNNoise/u85-256: three extra counters enabled, `TOTAL` = 36,086, identical to the frozen value. One cell, one run. |
| Event numbers are not the enum index | `ethosu85_interface.h`: `EXT_RD_TRANS_ACCEPTED = 384`, `EXT_RD_STALL_LIMIT = 398`, `EXT0_RD_TRANS_ACCEPTED = 640`. `ethosu_pmu.c` maps enum → encoding via `eventbyid[]`. **Contract must name events symbolically.** |
| Latency histograms are channel-filterable | `NPU_REG_PMCAXI_CHAN = 0x11AC` (absolute `0x500051AC`), fields `CH_SEL[3:0]`, `AXI_SEL[8]`, `BW_CH_SEL_EN[10]`. Channels: `RD_CMD(0) RD_IFM(1) RD_WEIGHTS(2) RD_SCALE_BIAS(3) RD_MEM2MEM(4) RD_IFM_STREAM(5) RD_MEM2MEM_IDX(6) WR_OFM(8) WR_MEM2MEM(9)`. |
| Board is single-configuration | FPGA image is Z1024. MAC cannot be varied. FVP MAXR sweeps exist only at 256 and 512. |

**Not verified.** Architectural outstanding ceilings quoted in discussion
(SRAM R/W 12/16 per port, EXT R/W 64/32 per port; ×2 ports at U85-1024) come
from secondary citation of Arm documentation and have **not** been read in the
U85 TRM. `ethosu_config_u85.h` carries fixed driver defaults
(`AXI_LIMIT_EXT_MAX_OUTSTANDING_READ_M1 = 64`) with the comment
`Hardware max might be less`, which is consistent with but does not establish
the table. TA performance counters (`ARTRANS`, `ARQTIME`, …) are unverified on
the board; they appear unimplemented in the FVP.

## 5. Phases

Each phase is a separate contract freeze and a separate board authorization.

```
P1  EXT read axis          Q_EXT,R · J_EXT,R · B_EXT,R
                           L × MAXR × BWCAP cube
                           RNNoise (calibration) + FC saturator family
P2  Path symmetry          same protocol on the SRAM side → Q_SRAM,R
P3  Direction symmetry     write axis → Q_{EXT,W}, Q_{SRAM,W}
P4  Frontiers              F_RW and F_EXT,SRAM via mixed-traffic ratio sweeps
P5  Channel decomposition  PMCAXI_CHAN — attribute the latency tail to
                           weights / IFM / OFM traffic
```

P1 alone yields the headline result if the FVP finding reproduces: *the
effective latency-hiding concurrency saturates far below the architectural
outstanding capacity, so the front end limits before the port does.*

## 6. Design rules already settled

These came out of design review and are intended to go into the P1 contract
verbatim.

**Endpoints and statistics**

- Primary confirmatory endpoint: the slope `k` of cycles versus external-read
  latency in the preregistered asymptotic region.
- Do not fix a tolerance number. Fix the formula that computes it:
  `SE(k̂) = σ_C / √Σ(Lᵢ − L̄)²`; with L = {250, 500, 1000}, `√Σ ≈ 540`.
  `Z_p = (k̂_p − k_pred_p) / √(SE(k̂)² + SE(k_pred)²)`; with five held-out
  workloads, family-wise 5 % gives `|Z| ≤ 2.576`.
- `PREDICTION_PASS` iff all held-out workloads fall inside the preregistered
  simultaneous prediction interval derived solely from calibration-run variance.
- Fit `k` by regression over three latency points, not a two-point difference.
  Preregister `ASYMPTOTIC_LINEARITY_FAIL`: if `k(250→500)` and `k(500→1000)`
  disagree beyond the repeatability-derived tolerance, no single `k` is defined.

**Hold-out discipline**

- **RNNoise is calibration only.** It was used to discover the model and cannot
  count as a hold-out. The claim that `Q_1024` is workload-independent is
  evaluated exclusively on the remaining workloads.
- Hold-out procedure: measure `R_p` from the transaction counter, predict
  `k̂_p = R_p / Q_1024` **before** running the latency sweep, then compare.

**Replication and ordering**

- Three boots per cell for a core claim; two is the minimum defensible, with
  four sentinel cells at four boots. `identity exact` guarantees the same
  program ran, not that timing noise is small, and `k` is built from differences
  across latency cells so their variances propagate.
- Blocked randomization of run order, so drift and thermal state do not align
  with MAXR/L conditions.

**Knee localization (Stage B)**

- `PLATEAU(m)` requires both `k(m) ≈ k(63)` and `dSTALL_LIMIT/dL ≈ 0`, under the
  same noise-derived tolerance.
- Finite preregistered bracket-and-refine: measure {8, 12} first, then a fixed
  branch rule, at most one further refinement — at most three added MAXR values.
- Stop conditions: `NO_PLATEAU_WITHIN_RANGE`, `MODEL_SHAPE_FAIL`,
  `KNEE_INTERVAL_ONLY` (interval reported, point estimate forbidden).

**Counters and their interpretation**

- Name events symbolically; add a gate that reads back `PMEVTYPER` and confirms
  384 / 398 / 640.
- Slot allocation for the main pass: `EXT_RD_TRANS_ACCEPTED`,
  `EXT_RD_STALL_LIMIT`, `EXT0_RD_TRANS_ACCEPTED` (EXT1 = total − EXT0).
- `A(m) = k_S / k_C` is a **stall-limit elasticity ratio**, not a causal
  fraction. `EXT_RD_STALL_LIMIT` sums over both EXT ports, so `A > 1` is
  possible when both stall in the same cycle.
- Core mechanism prediction: in the binding region `k` and the stall-limit slope
  fall together; in the non-binding region the stall-limit approaches **zero**,
  not a plateau.
- `B` must be calibrated from delivered throughput
  (`DATA_BEATS / NPU_ACTIVE`, and separately `/ *_ENABLED_CYCLES`), never from
  the configured `BWCAP`.
- Transaction counts across two ports show **traffic distribution**, not
  concurrent operation. Port-level concurrency needs `EXT0_RD_STALL_LIMIT` /
  `EXT1_RD_STALL_LIMIT`.

**Multi-pass joining**

- FVP: deterministic join, gated on `TOTAL`, `ACTIVE`, invariant traffic
  counters and output all identical across passes.
- Board: identity-matched **statistical** join. Beats / CRC / artifact identity
  make two runs samples of the same cell; they do **not** license treating
  pass A's stall counter and pass B's port counter as one joint observation.
  Counters that enter the same equation must be collected in the same pass.

**Built-in falsification gates**

- If `R` is a program property, then beats, `EXT_RD_TRANS_ACCEPTED` and the
  output CRC must be invariant under changes to `L` and `MAXR`. Required on
  every cell. Any violation invalidates the `k = R/Q` factorization.
- Instrumentation neutrality is `TOTAL == TOTAL`, `ACTIVE == ACTIVE`,
  beats == beats, output == output between clean and instrumented builds — not
  `TOTAL` alone.

## 7. Synthetic saturator suite

Needed because `Q_machine = sup_w Q_eff(w)` is an upper envelope: a natural
workload may simply fail to generate enough memory-level parallelism to reach
the machine ceiling.

| purpose | candidate |
| --- | --- |
| compute roof | 3×3 conv, 32×32×64 → 64, Sram_Only (high reuse, small footprint) |
| EXT read / `Q` | batch-1 large FullyConnected, e.g. Cin 4096 × Cout 2048 INT8 → ~8 MiB weights, ~4 KiB input, ~2 KiB output |
| compiler-artefact control | several shapes: 4096×1024, 4096×2048, 8192×1024, 2048×4096; take the envelope |
| SRAM read / `Q` | same family scaled to fit SRAM, e.g. 768×256 ≈ 192 KiB |
| write saturation | large `ResizeNearestNeighbor` (small input, large output) |
| mixed R/W | large `Add` (two read streams, one write stream) |
| EXT/SRAM coexistence | Dedicated_Sram conv/FC — EXT weight stream with SRAM staging |

Exact sizes must be chosen against a real SRAM-fit gate on the built artifact,
not from arithmetic alone.

## 8. What this program cannot do

- **MAC scaling.** The board image is Z1024. Nothing here speaks to how `Q`,
  `B` or `J` vary with MAC configuration. That axis stays on the FVP and must be
  labelled as model observation, not hardware-validated measurement.
- **Energy.** The board is an FPGA implementation; its power is dominated by
  fabric switching and bears no fixed relation to ASIC power, and the NPU's
  contribution cannot be separated from the rest of the synthesised design.
  Any energy figure obtained here characterises the FPGA image, not Ethos-U85.
- **Absolute FVP-versus-board cycle agreement.** Refused by the frozen
  measurement contract. The identity axis (beats, CRC, artifact) is the
  comparable one.

## 9. Scope of the resulting claim

Permitted, if the program succeeds:

> effective latency-hiding capacity of the Corstone-320 / Ethos-U85 1024-MAC
> configuration under the tested memory configuration

Not permitted on this evidence:

- "Ethos-U85's Q is X"
- "Q grows with MAC count as …"
- "the intrinsic concurrency of the U85 architecture is X"

## 10. Named steps

```
STEP-X6-0   read the U85 TRM; establish the architectural outstanding table   (no board)
STEP-X6-1   freeze the P1 contract                                            (no board)
STEP-X6-2   build the synthetic saturator family and pass the SRAM-fit gate   (no board)
STEP-X6-3   P1 instrumentation-neutrality runs                                (board)
STEP-X6-4   P1 L × MAXR × BWCAP acquisition                                   (board)
STEP-X6-5   P1 hold-out prediction runs                                       (board)
```

`STEP-X6-0` through `STEP-X6-2` touch no hardware and can begin without board
authorization. Every board step needs its own named authorization; board access
is never standing.

## 11. Provenance

Design review was conducted as a dialogue with an external model over five
rounds on 2026-09-17/18. Corrections adopted from it that changed the design:
the additive-model retraction in §1.1, the hold-out exclusion of RNNoise, the
elasticity-ratio reinterpretation of `A(m)`, the symbolic-event requirement,
the three-boot replication argument, and the bracket-and-refine knee design.
Platform facts in §4 were verified locally against the repository and build
container rather than taken from that dialogue.
