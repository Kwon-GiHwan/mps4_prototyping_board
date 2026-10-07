# Timing adapter audit — X0 (re-established from current source)

Classification vocabulary is restricted to `TA_ON`, `TA_OFF`,
`SEMANTICS_UNRESOLVED`. No claim is made that TA-OFF equals zero-latency
hardware or that TA-ON is cycle-accurate.

## Verdict per platform

| platform | TA | source authority |
| --- | --- | --- |
| SSE-300 | `TA_ON` | default `ETHOS_U_NPU_TIMING_ADAPTER_ENABLED=ON` (`npu_opts.cmake:87-89`); no forced override |
| SSE-310 | `TA_OFF` | **forced**: `scripts/cmake/platforms/mps3/build_configuration.cmake:53-55` sets it `OFF … FORCE` when `TARGET_SUBSYSTEM STREQUAL "sse-310"` |
| SSE-315 | `TA_OFF` | **forced**: `scripts/cmake/platforms/mps4/build_configuration.cmake:67-69`, same construct for `sse-315` |
| SSE-320 | `TA_ON` | default ON; TA config selected by MAC (`Z128/Z256→_low`, `Z512/Z1024→_mid`, `Z2048→_high`) |

The forced-disable is unconditional in the platform build configuration: a
user-supplied `ON` is overridden. This reproduces the frozen audit's
conclusion from the current tree.

## Where TA parameters live (X4 feasibility)

TA parameters are **firmware build-time cmake values**, not FVP command-line
parameters. Per interface (SRAM/EXT) the controllable fields are:

```
MAXR, MAXW, MAXRW          outstanding transaction limits
RLATENCY, WLATENCY         minimum read/write latency in clock cycles
PULSE_ON, PULSE_OFF, BWCAP bandwidth shaping
PERFCTRL, PERFCNT, MODE, HISTBIN, HISTCNT
```

Example values: U55 high-end `SRAM_RLATENCY=32`; U85 `SYS_DRAM_Low`
`SRAM_RLATENCY=16` — i.e. the profiles differ per generation and per MAC band.

**Consequence for a future X4**: varying TA parameters requires rebuilding the
host firmware but **does not require recompiling the Vela NPU artifact**. The
artifact can be held byte-identical while the memory service is varied, which
is exactly the isolation X4 wants. This is recorded as a capability fact; X4
remains HOLD.

For SSE-320 the FVP additionally exposes seven `mps4_board.stub_timing_adapter.*`
parameters, but these configure a stub peripheral model, not the TA profile
programmed by firmware. They are not a substitute for the firmware TA config
and are classified `SEMANTICS_UNRESOLVED` for sweep purposes.

## Preserved warning

The frozen observation stands: TA state differences may dominate raw cycle
values (a byte-identical NPU program measured ~4× apart between TA-ON and
TA-OFF platforms). No platform performance ratio is computed in X0.
