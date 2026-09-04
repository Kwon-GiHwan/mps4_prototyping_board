# X1 limitations

1. **The TA axis cannot be isolated.** No platform pair on this stack holds TA
   constant at `TA_ON`, so every CLASS B comparison changes subsystem, Fast
   Models version and TA state together. Attribution to any single factor is
   `NOT_SEPARATED`; the CLASS A result bounds only the `TA_OFF` case.
2. **Class-label disagreements sit at a threshold.** All 8 CLASS B
   disagreements are one-label crossings of the frozen 0.75 boundary
   (0.64–0.75 vs 0.77–0.86). The threshold was frozen long before this
   campaign and is not retuned here, but a metric defined by a cut point is
   more fragile near that cut point than the underlying efficiency values are.
3. **CLASS A is a two-platform, single-NPU comparison** (U65, 14 cells). Its
   exact value-identity is a strong datum for those cells and is not
   generalized to other NPUs, MACs, or to `TA_ON`.
4. **`wav2letter` has no U55 ladder.** It is executable only at MAC 256 on
   both U55 platforms, so it contributes to ranking there and is
   `NOT_AVAILABLE` for U55 scaling and saturation — as in the frozen sweep.
5. **Scope.** Clean whole-model observations only; no per-layer profiling, no
   memory-mode sweep, no U85/SSE-320 runs. All values are FVP cycle-model
   observations on the pinned stack.
6. **Raw cycles are per-platform evidence only.** They are stored in
   `X1_FORMAL_CELLS.json` for provenance and are not a cross-platform
   performance metric; the analyzer emits no cross-platform ratio and the
   mutation tests fail closed on requests for one.
