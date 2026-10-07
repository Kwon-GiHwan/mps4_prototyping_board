# U65 bridge — limitations

1. **Legacy-core scope (Amendment 1).** Vela 5.0.0 default-routes U55/U65
   through regor; C0 is the deprecated forced-legacy-core output. The
   bridge validates insertion-backend equivalence on that program; the
   frozen formal U65 artifacts of the paper are regor outputs and differ
   from C0 (kws clean 220,068 vs 217,068). Any manuscript use must state
   this compiler distinction.
2. **AXI beat fields are container-layout-sensitive** at the ±8-beat /
   ±1-cycle order, demonstrated with zero instrumentation (C0′ control).
   Per-segment beat values should not be treated as layout-invariant at
   this granularity on U65; CYCLE/ACTIVE are.
3. **U65 IRQ service merging** occurs (46 IRQs → 22 records) with no
   irq-history mechanism on this generation; both methods merge
   identically and deterministically, so A/B comparison is unaffected, but
   per-op attribution granularity on U65 is bounded the same way P0-D2
   documented for U85 — without the history-decode remedy.
4. Two cells at U65-256 only, per the escalation rule; coverage of other
   command structures (U65-512, U55) was not exercised.
5. This bridge proves instrumentation-boundary equivalence only — not
   U55/U65↔U85 PMU semantic equivalence, and no absolute cross-generation
   comparison is licensed by it.
