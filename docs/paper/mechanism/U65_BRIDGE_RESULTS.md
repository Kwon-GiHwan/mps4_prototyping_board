# U65 bridge results — computed, with the classification decision surfaced

```
plan      paper-u65-bridge-plan-anchor (4100f46) + Amendment 1 (3150f9f)
E1        paper-u65-bridge-structural-frozen (be44b13): A==B byte-identical
runs      clean/A/B x 2 cells x 3 fresh FVP runs — every arm vector-exact
rule failures  0  (two pre-runtime fail-closed catches, both fixed before data)
```

## Final report fields (per plan)

- clean cells 2 / Method-A cells 2 / Method-B cells 2 (all OK)
- no-op roundtrip: byte-identical (both cells)
- exact semantic boundary matches: 14/14 and 46/46 (positions AND params);
  **instrumented streams byte-identical A==B** — the stronger implementation
  evidence, reported separately as the plan requested
- exact attribution matches: record counts and order identical (13/13,
  22/22; U65 service merging occurs — 46 IRQs → 22 records — identically
  and deterministically in both methods)
- exact PMU-vector matches: **CYCLE and ACTIVE exact in every segment and
  in every sum**; tail totals exact; output CRC identical to each other and
  to clean. **AXI beat fields are NOT exact**: 9/13 and 13/22 segments
  differ by ≤8 beats, whole-profile beat sums differ by ≤7.
- perturbation (descriptive): clean totals 220,068 / 64,086; instrumented
  runs segment identically under both methods (no threshold attached).
  Legacy-core clean totals differ from the frozen regor-artifact totals
  (kws 220,068 vs 217,068; rnnoise 64,086 vs 65,086) — an Amendment-1
  consequence, out of bridge scope, recorded.
- **container-isolation control**: an UNinstrumented deep-copy
  re-containerization (C0′) vs C0 shows TOTAL identical, all four beat
  totals identical, output identical, and a ±1 ACTIVE/IDLE split shift —
  the container re-serialization alone moves counters at this order of
  magnitude with zero IRQs present.

## Verdict

Strict plan criterion ("PMU vector exact" over ALL fields):
**NOT met** — the AXI beat fields differ.

Evidence-weighted reading, surfaced for the manager's classification:
every quantity that defines the measurement boundary — segmentation,
ordering, per-segment CYCLE/ACTIVE, sums, tails, outputs — is **exactly
equivalent**, and the residual beat differences are `ASSOCIATED_WITH`
container re-serialization (address/layout) rather than the insertion
method: the two methods' streams are byte-identical, and the no-IRQ
container control reproduces same-order counter sensitivity. Per the
plan's stop rule this report STOPs **without** self-declaring
`MEASUREMENT_EQUIVALENT`; the binary classification (strict
`NOT_EQUIVALENT` vs cycle-domain `MEASUREMENT_EQUIVALENT` with a declared
beat-attribution caveat) is the manager's call.
