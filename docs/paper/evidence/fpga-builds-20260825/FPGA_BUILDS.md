# Seven FPGA artifacts for board validation — built, not measured

```
target      FPGA / Corstone-320 / Ethos-U85 / 1024 MAC
builds      7 / 7 OK
board runs  NONE in this step
```

## The FVP binaries cannot be reused — confirmed, not assumed

MLEK states it directly:

```
scripts/cmake/platforms/mps4/build_configuration.cmake:27
  For sse-320 specifically, binaries built for FVP will not work on FPGA and vice
  versa. As a result, the flag `FPGA_PLATFORM_SSE_320` must be provided when
  building for FPGA, and omitted when building for FVP.
```

```
scripts/cmake/configuration_options/npu_opts.cmake:60
  if (FPGA_PLATFORM_SSE_320)
      # FPGA is fixed at 1024 MACs
```

The claim was then checked against the artifacts rather than taken from the
comment:

| workload | FVP AXF | FPGA AXF | differ | Vela artifact |
| --- | --- | --- | --- | --- |
| `rnnoise_INT8` | `845288d515447807…` | `83a69be4620ad1a6…` | ✅ | **identical** |
| `kws_micronet_m` | `f4d4e0604b097394…` | `d3a2739e8929c90b…` | ✅ | **identical** |
| `ad_medium_int8` | `841bade0ca897e87…` | `f390530637412683…` | ✅ | **identical** |
| `vww4_128_128_INT8` | `50abba5cf2fa6ffc…` | `c420aae236b6ca75…` | ✅ | **identical** |
| `yolo-fastest_192_face_v4` | `a5db2577558cbe8b…` | `a24bd80f7cb2d7ef…` | ✅ | **identical** |
| `mobilenet_v2_1.0_224_INT8` | `101aba59af42d7b6…` | `7deaa14c5e8ba003…` | ✅ | **identical** |
| `wav2letter_pruned_int8` | `e28c25ae8cbd9ebf…` | `1081d815ac3770a3…` | ✅ | **identical** |

This is the right shape for RQ3. The **Vela artifact is byte-identical in all
seven cases**, so the NPU program is the same; only the platform code around it
differs. The experimental unit is therefore

```
same model / source identity + same logical U85@1024 configuration
+ target-specific FVP and FPGA builds
```

and never "the same binary ran on both".

## Per-build provenance

Recorded for each of the seven in `fpga_builds.json`:

```
model source path + model_sha256
vela argument vector, artifact name, vela_sha256
vela CPU operator count
generated .cc raw + BODY sha256
AXF sha256 + size
full build argument vector, arena
FPGA_PLATFORM_SSE_320 resolved from CMakeCache
ETHOS_U_NPU_CONFIG_ID resolved   (Z1024)
timing adapter cache value
embedded build stamp + SOURCE_DATE_EPOCH
MLEK commit
kept artifact list + FPGA sectors manifest
```

Checks:

```
vela CPU operators == 0        7 / 7      full NPU placement
distinct FPGA AXFs             7 / 7      no two workloads share a binary
FPGA_PLATFORM_SSE_320 = ON     7 / 7
NPU_CONFIG_ID resolved         Z1024
```

Deployable set retained per workload:

```
mlek_inference_runner.axf
mlek_inference_runner.map
sectors/  -> images.txt, inference_runner, hal-test
```

## What this step deliberately does not do

No board deployment and no measurement. Whether the **stock FPGA measurement
path** returns valid, non-stale PMU observations across the Ethos-U power-release
lifecycle is unproven, and that is the blocking prerequisite for any formal board
run.

"MLEK PMU worked under FVP, therefore the same runner is valid on FPGA" is
precisely the inference this project has repeatedly been caught making — a claim
about one artifact used as authority for a different one. It is settled by the
`rnnoise_INT8` integration probe, not by inheritance.
