# Amendment — the board protocol was not executable with the stock runner

**Formal board samples observed before this correction: 0.**

Not a reduction in scope. The registered protocol was incompatible with the
artifact under test, and the qualification probe is what exposed it.

## Finding

The stock MLEK `inference_runner` executes **exactly one inference per
application boot**. `UseCaseHandler.cc` runs a single `RunInference` and prints
`Total number of inferences: 1` as a literal; there is no run loop. The board
probe confirmed this on hardware.

The registered protocol was:

```
7 workloads × 3 independent boots × 10 consecutive runs per boot = 210 samples
```

"Ten consecutive runs inside one boot" is a capability of the **V15 custom
runner**, which implemented its own command protocol. It was carried over to the
MLEK runner, which has no such facility. Executing it would require patching
`inference_runner` — explicitly not authorized, and the same patch that the FVP
protocol was amended to avoid.

## Correction

```
7 workloads × 3 independent fresh boots × 1 stock inference = 21 formal samples

per workload:   Boot 1 -> one inference -> B1
                Boot 2 -> one inference -> B2
                Boot 3 -> one inference -> B3

canonical_board_cost = median(B1, B2, B3)      (middle of three)
```

The previous `3 × 10` protocol is marked **SUPERSEDED BEFORE FORMAL BOARD DATA**.

This is better aligned than the original, not merely smaller: it leaves the stock
artifact unmodified, never re-runs a workload against carried-over state, reports
boot-level repeatability directly, and matches the FVP unit of three independent
fresh processes.

## What the qualification did and did not establish

**Established:** the stock FPGA runner delivers a non-stale, software-visible
U85 PMU observation corresponding to a fresh inference on real hardware.

**Not established:** that board PMU values share a timing domain with FVP values.
Nothing here licenses an absolute comparison.

## Board cost metric for RQ3

`NPU TOTAL`, the counter qualified on hardware. Normalized independently within
each domain:

```
normalized_cost_i = total_i / geomean(total_1 … total_7)
```

Permitted: Spearman ranking, rank inversions, relative-cost-shape deviation.
Prohibited: `board TOTAL − FVP TOTAL`, `board/FVP` ratio, and any "hardware is
X % slower" statement.

## A limit inherited from the frozen FVP records

The board emits `SRAM_RD/WR` and `EXT_RD/WR`, and those are collectable. But the
frozen FVP formal records **did not preserve** them — the stage records kept
parsed fields only, and the harness of the day matched AXI names.

```
TOTAL / ACTIVE / IDLE     comparable — preserved in the frozen FVP records
SRAM_* / EXT_*            board-collectable, FVP formal counterpart absent
                          -> cross-target consistency NOT_EVALUABLE
```

The frozen FVP stages are **not** re-run to obtain them.

## Prerequisite before any formal board sample

`rnnoise_INT8` is qualified. Compile and link success is not runtime
executability on a concrete target — the FVP pass established that with six
`NOT_EXECUTABLE_MEMORY` cells — so each remaining workload gets exactly one
qualification-only execution:

```
BOARD_EXECUTABILITY_QUALIFICATION
  rnnoise_INT8    already QUALIFIED
  remaining       6 workloads × 1 run
  FORMAL_BOARD_SAMPLES = 0
```

Each must establish deployment/read-back identity, fresh boot health, inference
completion, no fatal/NPU error, `NPU TOTAL > 0`, `TOTAL == ACTIVE + IDLE`, the
expected U85 event family, and a clean restore/postflight.

**If any workload fails, the seven-workload RQ3 universe is `NOT ESTABLISHED`.**
It is not quietly reduced to six — ranking preservation over the frozen seven is
what RQ3 was designed around.

## Harness contracts added

**Capture ordering** (from attempt #1): listener alive and confirmed before
`REBOOT`.

**Postflight ordering** (new): the postflight reboot **re-presents** the debug
USB card, observed in both attempts. Therefore

```
REBOOT -> wait for postflight state -> USB_OFF -> assert /dev/sdb* absent
```

and *not* `USB_OFF -> REBOOT -> assert absent`, which leaves the card exposed.
Both orderings are enforced by guards that raise before any serial I/O, and both
are covered by offline mutation tests (13 in total).

## Staged rollout

Even once the six qualify, the 21 samples do not open at once:

```
Stage B1   7 workloads × fresh Boot #1 = 7 samples   -> STOP and report
Stage B2   fresh Boot #2 × 7                          -> B1 vs B2 repeatability
Stage B3   fresh Boot #3 × 7                          -> FORMAL_BOARD_SAMPLES = 21
```

then evidence freeze, then the preregistered RQ3 analysis.
