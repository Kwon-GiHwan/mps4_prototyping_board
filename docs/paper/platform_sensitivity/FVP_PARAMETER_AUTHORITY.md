# FVP parameter authority — X0

Established by executing every installed FVP on the pinned stack
(`--version`, `--list-params`, and direct `-C` injection at init), not from
documentation or prior notes.

## Namespaces differ by platform generation

| FVP executable | platform | MAC parameter | board namespace |
| --- | --- | --- | --- |
| `FVP_Corstone_SSE-300_Ethos-U55` | SSE-300 | `ethosu.num_macs` | `mps3_board` |
| `FVP_Corstone_SSE-300_Ethos-U65` | SSE-300 | `ethosu.num_macs` | `mps3_board` |
| `FVP_Corstone_SSE-310` | SSE-310 | `ethosu.num_macs` | `mps3_board` |
| `FVP_Corstone_SSE-310_Ethos-U65` | SSE-310 | `ethosu.num_macs` | `mps3_board` |
| `FVP_Corstone_SSE-315` | SSE-315 | `mps4_board.subsystem.ethosu.num_macs` | `mps4_board` |
| `FVP_Corstone_SSE-320` | SSE-320 | `mps4_board.subsystem.ethosu.num_macs` | `mps4_board` |

**Consequence for X1**: a single invocation string cannot drive SSE-300/310 and
SSE-315/320. Any harness must select the namespace per platform; this is a
harness contract, not a semantic difference in the measured quantity.

## Two distinct validation layers (new X0 finding)

Injecting MAC values reveals that the FVPs validate in two stages:

```
ethosu.num_macs=512  on SSE-300/U55 →  "parameter error: value is out of range"   (range check)
ethosu.num_macs=100  on SSE-300/U55 →  "FATAL ERROR: The number of MACs parameter
                                        value '100' for Ethos-U55 is not valid!
                                        Expected 32, 64, 128, or 256."            (discrete-set check at model init)
```

The second layer means **the FVP model does validate the discrete legal set**,
and its error message enumerates it. This supersedes the auxiliary observation
recorded in the frozen `MAIN_EXPERIMENT_MATRIX.md` — see `X0_LIMITATIONS.md`
§1. The frozen document itself is left unmodified.

Authority rule retained regardless: **discrete MAC support is established from
source/Vela configuration authority**, with FVP init behaviour as corroboration.
Parameter acceptance alone is never used as architectural authority.

## Versions (probed, not assumed)

| FVP | Fast Models | binary date |
| --- | --- | --- |
| SSE-300 (U55, U65) | 11.22.35 | Aug 2023 |
| SSE-310, SSE-310_U65 | 11.24.13 | — |
| SSE-315 | 11.31.28 | — |
| SSE-320 | 11.27.25 | — |

SSE-300/U55 binary re-verified this session: `Fast Models [11.22.35 (Aug 18
2023)]`, identical to the version recorded in the frozen campaign — no stack
drift on that executable.
