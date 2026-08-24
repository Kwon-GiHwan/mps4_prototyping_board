# FVP execution-pipeline qualification — 2026-08-24

One build, one run, under `MLEK_EXCEPTION`.

```
QUALIFICATION_RUNS = 1
FORMAL_FVP_SAMPLES = 0
```

**Neither the wall-clock nor the simulated cycles below are paper results.**
They exist to show the pipeline executes and to size the sweep.

## Preconditions, proven before the run

| | |
| --- | --- |
| target platform | SSE-320 (`TARGET_PLATFORM=mps4`, `TARGET_SUBSYSTEM=sse-320`, FPGA off) |
| accelerator config | Ethos-U85-1024 (`ETHOS_U_NPU_CONFIG_ID=Z1024`) |
| workload | `wav2letter_pruned_int8`, source `e0814a0e…b257` |
| CPU fallback | **0** — `CPU operators = 0 (0.0%)`, `NPU operators = 27 (100.0%)` |
| memory map | valid — image loaded with no write failures |
| NPU config confirmed | FVP `num_macs=1024`, TA `ta_config_u85_sys_dram_mid` |
| system config | `Ethos_U85_SYS_DRAM_Mid_1024`, `Dedicated_Sram` |
| network size | 3,491,110,876 MACs/batch |

## Results

| | |
| --- | --- |
| build | **SUCCESS**, 48 s |
| runner binary | `bf336fb42568efeb…acbe` |
| vela output | `4c5b640211f0aaa6…def7b` |
| image load | **PASS** |
| inference | **COMPLETED** — `Total number of inferences: 1`, `Inference completed.` |
| **wall-clock to completion** | **≈112 s** (FVP start 02:42:15 → last UART write 02:44:07.68) |
| FVP exit | did not self-exit; idled after the application terminated, and was killed |

### PMU counters reported by the run

```
NPU ACTIVE                             4,114,227 cycles
NPU IDLE                                     841 cycles
NPU TOTAL                              4,115,068 cycles
ETHOSU_PMU_SRAM_RD_DATA_BEAT_RECEIVED    463,085 beats
ETHOSU_PMU_SRAM_WR_DATA_BEAT_WRITTEN      40,950 beats
ETHOSU_PMU_EXT_RD_DATA_BEAT_RECEIVED   1,836,882 beats
ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN       19,045 beats
```

This **confirms the PMU audit empirically**: the `SRAM_*` and `EXT_*` events the
audit classified as U85-only are exactly the ones this U85 run emits. On U55/U65
these names do not exist, so this metric set is not portable across generations —
as predicted from the header, now observed in practice.

## Two operational facts

**The FVP does not exit when the application finishes.** The UART reached
`program terminating…` and `Inference completed.`, and the simulator kept
running. A sweep harness must detect completion from the **UART marker**, not
from process exit, or every run will hang until its timeout.

**A run dies with its SSH session.** The first attempt was launched over an SSH
command that closed; the UART showed initialization and stopped, which reads
exactly like a completed-but-quiet run. Relaunching detached (`setsid nohup`)
produced the full inference. The sweep harness must detach, and must distinguish
"finished" from "killed" by the completion marker rather than by output ending.

## Sweep projection

One measured point: **112 s** for the heaviest of the seven models, at one of the
19 configurations.

| | |
| --- | --- |
| naive upper bound | 399 × 112 s ≈ **12.4 hours** |

That bound is loose. `wav2letter` accounts for **70.6 %** of the seven models'
combined Vela cycle estimate (17.72 M of 25.09 M at u85-256), so most runs will be
far shorter.

A defensible projection needs two things, neither of which is the sweep:

1. **Vela cycle estimates for all 133 model × config pairs** — compilation only,
   seconds each, no FVP involved.
2. **One light-model FVP probe** (`rnnoise_INT8`, ~0.2 % of wav2letter's cycles)
   to separate fixed per-run overhead from per-cycle simulation cost. With two
   points, `T = fixed + k·cycles` is solvable; with one, it is not.

Until then the projection is stated as a **bound, not an estimate**: the sweep is
**at most ~12.4 hours** of FVP wall-clock, likely substantially less, and the
error bars cannot be narrowed from a single observation.
