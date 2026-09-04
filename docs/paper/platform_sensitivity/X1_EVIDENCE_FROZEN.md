# X1 formal evidence — frozen

```
contract     paper-platform-sensitivity-x1-plan-anchor = 31267d1
evidence     gihwan:/home/gihwan/mps4/X1_PLATFORM_SENSITIVITY_20260904T002134Z
             (634 files, EVIDENCE.sha256; per-cell UART logs, build identities,
              result vectors, acquisition script and plan)
cells        92 attempted / 92 successful
samples      276 (92 cells x 3 fresh FVP processes, stock inference once each)
```

## Gates passed

| gate | result |
| --- | --- |
| artifact identity binding | **39/39** unique Vela artifacts reproduced the frozen X0 hashes exactly; the identical artifact file was then built into each platform's firmware |
| determinism qualification | 3 representative cells (U55/SSE-300, U55/SSE-310, U65/SSE-315), 3/3 exact each, before the formal contract was applied |
| formal repetition | **92/92** cells vector-exact across 3 fresh processes |
| TA state | verified per build from `CMakeCache.txt`: SSE-300 ON (39/39), SSE-310 OFF (39/39), SSE-315 OFF (14/14) — independent confirmation of the X0 classification |
| rule failures | 0 |

Cell distribution: SSE-300 39, SSE-310 39, SSE-315 14; U55 50, U65 42.

Raw cycles are stored per platform in `X1_FORMAL_CELLS.json` as formal
evidence. They are **not** a cross-platform performance metric and no
cross-platform ratio is computed anywhere in this campaign.
