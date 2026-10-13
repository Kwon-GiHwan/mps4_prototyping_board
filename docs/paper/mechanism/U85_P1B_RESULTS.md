# P1-B results — cross-memory per-layer decomposition (computed, not interpreted)

```
plan      paper-u85-p1b-plan-anchor (7eb51df), applied once
evidence  gihwan:/home/gihwan/mps4/U85_MECH_P1B_20260902T072812Z (153 files;
          manifest excludes itself — the earlier self-referential manifest
          artifact is fixed from this root onward)
identity  DS reuse verified: 4 frozen P0 artifacts hash-equal to the audit
          shas; 8 SO/SH artifacts hash-gated against P1-A records
runs      8 new profiled cells x 3 fresh FVP runs, all vector-exact;
          output CRC == frozen P1-A clean CRC on 8/8; rule failures: 0
analysis  12 profiled cells; ONE common attribution partition per workload
          across all six mode x MAC cells (union-find over shared service
          windows; source-table equality gate passed)
```

## Coherence

Per-mode group sums reproduce the whole-model deltas:

| | SO | SH | DS |
| --- | ---: | ---: | ---: |
| rnnoise Σgroup | +3,015 | +15,075 | +19,060 | (whole-model +3k/+15k/+19k) |
| vww4 Σgroup | −83,015 | −31,120 | −29,000 | (whole-model −83k/−32k/−28k) |

## Q1/Q2 — rnnoise: same groups, every mode

29 groups; **27/29 direction fully consistent across all three modes;
0 direction flips.** The regression sits in the SAME logical groups in
every mode, and the per-group magnitude scales monotonically SO < SH < DS:

| logical group (types) | n_ops | SO Δ | SH Δ | DS Δ | dir |
| --- | ---: | ---: | ---: | ---: | --- |
| Add FullyConnected Mul Pack | 11 | +1,000 | +4,015 | +7,030 | REG 3/3 |
| Add FullyConnected Mul Pack | 15 | +1,015 | +5,030 | +6,015 | REG 3/3 |
| Add FullyConnected Mul Pack | 10 | 0 | +1,015 | +3,015 | SAME→REG |
| Concat FullyConnected Quantize | 4 | +1,000 | +3,000 | +2,000 | REG 3/3 |
| Concat FullyConnected Quantize | 4 | 0 | +2,015 | +1,000 | SAME→REG |

(The two SAME→REG rows are magnitude-below-resolution at SO, not
contradictions; every other group is flat at 0 in all modes.) The
DISTRIBUTED structure persists in every mode. Computed statement licensed
by the frozen plan's own criterion: **whole-model regression magnitude
changes substantially with memory configuration, yet the same logical
operation groups exhibit the regressions across configurations.**

## Q3/Q4 — vww4: local regressions persist AND mode-specific mechanisms exist

33 groups; 19/33 direction-consistent; local per-op regressions exist in
every mode inside the always-improving whole model (e.g. a single Conv2D
at +2,000 in ALL three modes — REG 3/3). **Q4: yes — 11 groups flip
direction with memory mode**, most prominently the 33-op cascade group:

| logical group | n_ops | SO Δ | SH Δ | DS Δ |
| --- | ---: | ---: | ---: | ---: |
| Add Conv2D DepthwiseConv2D Pad (cascade) | 33 | **−35,000** | −2,120 | **+7,015** |

So vww4 exhibits both mode-invariant local regressions and
configuration-specific operator-level mechanisms simultaneously.

## Q5 — accompanying compiler-structure changes (computed bounds)

Every mode pair is `DIFFERENT_ARTIFACT` (P1-A), and the pass/command
structure differs strongly by mode — vww4 launch counts at 256:
SO 83 / SH 168 / DS 91 (at 512: 83/161/90). The flip groups are
predominantly multi-op cascade windows, where per-op ublock/block booleans
are `NOT_EVALUABLE` at op granularity (mixed attribution units); the full
verbose-schedule captures for all 12 cells are archived for op-level
follow-up. Runtime-vs-compiler contribution remains `NOT_SEPARATED`
throughout, per the P1-A amendment.

## Per-plan status

```
dnn_s P1-B   NOT_AVAILABLE (as decided)     yolo P1-B   HOLD
aggregate metrics                            none computed (per contract)
P2/P3/P4, narrative                          HOLD
```

Artifacts: `U85_P1B_CROSSMODE_GROUPS.csv` (62 groups × per-mode
256/512/delta/direction), tools `p1b_all.py`, `p1b_view.py`,
`p1b_crossmode.py` (frozen in evidence and repo).
