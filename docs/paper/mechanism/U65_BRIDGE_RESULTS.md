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

## Verdict (manager decision, 2026-09-02)

**Overall bridge verdict: `NOT_EQUIVALENT`.** Exact equality of the
complete PMU vector was a frozen, preregistered criterion and the AXI-beat
fields did not satisfy it. That criterion is **not** redefined post hoc,
and no cycle-domain-only restatement replaces it.

Component-level conclusions, recorded alongside the overall verdict:

```
STRUCTURAL_EQUIVALENCE          ESTABLISHED
SEMANTIC_BOUNDARY_EQUIVALENCE   ESTABLISHED
ATTRIBUTION_EQUIVALENCE         ESTABLISHED
CYCLE_DOMAIN_EQUIVALENCE        ESTABLISHED
ACTIVE_DOMAIN_EQUIVALENCE       ESTABLISHED
AXI_BEAT_EXACT_EQUIVALENCE      NOT_ESTABLISHED
```

**The AXI-beat residual cannot be attributed specifically to the
instrumentation backend**, because an uninstrumented re-containerization
control (C0′, zero IRQs inserted) reproduced comparable beat-level and
±1-cycle variation. The residual is therefore `ASSOCIATED_WITH`
container re-serialization; container layout is **not** claimed as a
uniquely proven causal mechanism, and no other single mechanism is
claimed either.

### What the bridge permits, and what it does not

Permitted, under the tested U65 conditions (U65-256, the two frozen
cells, the forced-legacy C0 program): cross-backend comparison of
**execution boundaries**, **attribution**, and **cycle-domain mechanism
observations**.

Not qualified by this bridge: **exact cross-backend memory-traffic
comparison** (the AXI-beat domain) and **cross-generation PMU-event
equivalence** (which the event audit already classified independently).
