# Main experiment matrix — proposed, frozen for review

**Not executed.** This fixes what would be run, before any sweep.

Every support claim below is marked with how it was established. Nothing here is
asserted from memory: the failure mode this project has repeatedly hit is a host
declaration treated as authority, so support is taken from the installed tools.

## Verified environment

| | | source |
| --- | --- | --- |
| Vela | 5.0.0 | `vela --version` |
| accelerator configs | u55: 32/64/128/256 · u65: 256/512 · u85: 128/256/512/1024/2048 | `vela --help` |
| board | MPS4 / FI101, Corstone-320, **Ethos-U85 @ 1024 MACs**, 1 NPU | `CFG__NPU0_NUM_MACS 0x400`, `CFG__NUM_NPUS 1`, vendor package |

### Installed FVPs and their stated MAC support

| FVP | NPU | `num_macs` as the model states it | Fast Models |
| --- | --- | --- | --- |
| `SSE-300_Ethos-U55` | U55 | *not stated*, default 128 | 11.22.35 |
| `SSE-300_Ethos-U65` | U65 | *not stated*, default 256 | 11.22.35 |
| `SSE-310` | U55 | "32, 64, 128, or 256" | 11.24.13 |
| `SSE-310_Ethos-U65` | U65 | "256 or 512" | 11.24.13 |
| `SSE-315` (AVH) | U65 | "256 or 512", `[0x100:0x200]` | 11.31.28 |
| `SSE-320` | U85 | `[0x80:0x800]` = 128–2048 | 11.27.25 |

## Valid configurations

Intersection of Vela support and FVP-stated support. **Not** a Cartesian product.

| # | platform | NPU | MAC configs | status |
| --- | --- | --- | --- | --- |
| C1 | SSE-300 | U55 | 32, 64, 128, 256 | **UNVERIFIED** — FVP does not state a range; boot-probe required |
| C2 | SSE-300 | U65 | 256, 512 | **UNVERIFIED** — same |
| C3 | SSE-310 | U55 | 32, 64, 128, 256 | verified, both sides agree |
| C4 | SSE-310 | U65 | 256, 512 | verified |
| C5 | SSE-315 | U65 | 256, 512 | verified |
| C6 | SSE-320 | U85 | 128, 256, 512, 1024, 2048 | verified |
| **B1** | **MPS4 board** | **U85** | **1024 only** | verified from vendor config |

**19 simulated platform × MAC configurations**, of which 13 are fully verified and
6 (C1, C2) need a boot probe.

### Two comparisons this inventory happens to enable

Worth stating because they are stronger than a generation sweep alone:

- **U55 @ same MAC across SSE-300 and SSE-310** — same NPU, different Corstone
  subsystem. Isolates the platform effect from the NPU effect.
- **U65 @ 256 across SSE-300, SSE-310 and SSE-315** — three Corstone generations,
  one NPU configuration.

Both are confounded by the Fast Models version skew (see MEASUREMENT_SEMANTICS)
and are qualitative until that is resolved.

## Workload set

From MLEK `resources_downloaded`, all INT8. NPU/CPU placement measured at
`ethos-u85-256`.

| model | domain | Vela `cycles_total` | CPU operators |
| --- | --- | --- | --- |
| `rnnoise_INT8` | noise reduction | 37,922 | 0 (0.0%) |
| `kws_micronet_m` | keyword spotting | 217,272 | 0 (0.0%) |
| `ad_medium_int8` | anomaly detection | 452,090 | 0 (0.0%) |
| `vww4_128_128_INT8` | visual wake words | 477,143 | 0 (0.0%) |
| `yolo-fastest_192_face_v4` | object detection | 1,297,666 | 0 (0.0%) |
| `mobilenet_v2_1.0_224_INT8` | image classification | 4,891,133 | 0 (0.0%) |
| `wav2letter_pruned_int8` | speech recognition | 17,720,421 | 0 (0.0%) |
| `dnn_s_quantized` | generic DNN | 24,452 | **2 (9.5%)** |

**Proposed: the seven fully-NPU models.** `dnn_s_quantized` is excluded from
scaling analysis because ~9.5% of its operators run on CPU, so its total does not
scale with MAC count and would flatten the scaling curve for reasons unrelated to
the NPU. It may be retained as a deliberate partial-fallback case if that is
wanted, but then it is reported separately and never pooled.

The seven span **467×** in estimated cycles, which is the dynamic range the
scaling and saturation questions need.

## Metrics

| class | metric | source |
| --- | --- | --- |
| estimate | `vela_estimated_cycles_total`, `_cycles_npu`, `_cycles_sram_access`, `_cycles_dram_access` | Vela CSV |
| estimate | `vela_estimated_inference_time` (= cycles ÷ assumed clock) | Vela CSV |
| memory | `sram_memory_used`, `dram_memory_used`, `*_total_bytes`, `total_npu_encoded_weights` | Vela CSV |
| structure | `passes_before_fusing`, `passes_after_fusing` | Vela CSV |
| simulated | NPU PMU cycle counters | FVP run |
| physical | `software_visible_completion_observation_cycles` | board |

Scaling metrics derived per model, per platform: raw speedup vs the smallest MAC
config, scaling efficiency (speedup ÷ MAC ratio), saturation point (first config
where efficiency falls below a threshold fixed **before** the sweep), and the
memory-bandwidth share of `cycles_total`.

## Procedure, per configuration

Warm-up policy, repetitions and validity are inherited from the board campaigns
rather than reinvented:

- **Warm-up:** discard the first inference; it carries cold-cache and first-touch
  effects. Fixed before the sweep, applied uniformly.
- **Repetitions:** FVP is deterministic per configuration, so repetition tests the
  harness, not the device — **3 repetitions**, required to be identical, with any
  disagreement a hard stop rather than an average.
- **Board:** the campaign design already qualified — 3 fresh boots × 10
  consecutive runs, per-boot minima, no pooling before classification.
- **Invalid runs:** discarded with a named reason, never down-weighted. No top-up.

## Provenance required per run

Model digest, Vela version and full command line, `accelerator_config`,
`system_config`, `memory_mode`, FVP binary path and Fast Models version, every
`ethosu.*` parameter used (including the empty `extra_args`), harness commit, and
the output CSV digest.

## Board's role

```
Corstone-320 + Ethos-U85 @ 1024 MACs
```

**One** configuration, and only one — the FPGA is fixed. The board is the
physical-validation layer for the Corstone-320 simulation characterization. It is
**not** a source of cross-generation comparison, and it cannot validate any MAC
configuration other than 1024.

Concretely, board validation touches exactly one cell of the matrix: C6 @ 1024.

## Research questions

**RQ1** — How do performance characteristics change across Corstone/Ethos-U
generations for representative workloads?

**RQ2** — How does performance scale with MAC configuration, and where does
scaling saturate because of workload, operator or memory characteristics?
Reported as: raw speedup, scaling efficiency, saturation point, workload/operator
sensitivity, memory-related bottlenecks.

**RQ3** — To what extent do the qualitative trends observed for
Corstone-320/U85 in FVP reproduce on the physical MPS4/FI101 platform?

### RQ3 validation criteria, preregistered

Numeric equality is **not** the criterion and is not expected.

| criterion | preregistered standard |
| --- | --- |
| ranking preservation | model ordering by cost identical between FVP and board |
| scaling-trend preservation | not testable on the board — only 1024 MACs exists |
| bottleneck consistency | models Vela marks memory-bound behave alike on both |
| repeatability | board floor reproduces across 3/3 boots |
| deviation | direction and magnitude reported as characterization, not agreement |

**Recorded now, before data:** the board offers one MAC configuration, so RQ3
cannot validate scaling behaviour — only per-model relative cost at 1024 MACs.
Any scaling claim remains simulation-only. Stating this after seeing results
would be choosing a standard to fit them.

## Estimated scale

| | |
| --- | --- |
| Vela compilations | 7 models × 19 configs = **133** |
| FVP runs | 133 × 3 repetitions = **399** |
| board runs | 7 models × 30 runs = **210** (needs separate authorization) |

Vela compile time is seconds per model. **FVP runtime is UNMEASURED** — a timing
probe on one small and one large model is proposed before committing, since
`wav2letter` at 17.7M cycles may dominate wall-clock.
