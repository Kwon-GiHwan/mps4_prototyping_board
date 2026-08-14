# PMU_COMPLETION_POLL_COUNT_DIAG_V13 Contract

## Scope

`PMU_COMPLETION_POLL_COUNT_DIAG_V13` is a diagnostic-only V12 derivative.
It is not `T_npu`, not a latency metric, not Production `END_ONLY`, and not
an MLEK dataset source.

## Question

V13 asks one question:

`P0 -> P1` variability comes from different poll iteration counts, or from
different per-iteration observation cost.

## Wire Contract

- Schema version: `13`
- Build id: `0x33314950`
- Field count: `101`
- Total words: `109`
- Payload bytes: `436`
- One new appended word: `poll_remaining_at_success`

`poll_remaining_at_success` is appended after the 15-word V12 appendix.

## Publication Contract

- Success only: `1 <= poll_remaining_at_success <= 10000`
- Timeout: `poll_remaining_at_success` is invalid and must not be published as a
  valid sample value
- Sentinel: `0`
- Derived diagnostic value:
  `poll_iterations = 10001 - poll_remaining_at_success`

`poll_remaining_at_success` is stored exactly once, after `P2`, before helper
return.

## Timing Authority

The authoritative V13 timing remains:

- `submit_to_status_completion_observed_cycles = u32(P1 - T2)`

`poll_remaining_at_success` is causal evidence only. It is not itself a timing
value and must not redefine the authoritative window.

## Source Intent

The helper must preserve V12 hard-bypass semantics and add only:

- one success-only live-out publication
- no timeout publication
- no extra per-iteration store
- no extra per-iteration timestamp
- no extra STATUS/MMIO read

## Qualification Priority

Source-level shape is not sufficient.

Primary qualification gates are:

1. final ELF V12↔V13 poll-loop semantic equivalence, scoped to the
   per-iteration loop region (STATUS load, completion test, success branch,
   failed-path decrements, back edge). Gate 1 is the only cross-image
   comparison; it does not claim prologue, success-tail or epilogue
   equivalence.
2. final ELF proof that the stored remaining value is the actual failed-path
   induction live-out
3. proof that the remaining store occurs after `P2`

Gates 2 and 3 are V13-only CFG/dataflow proofs. V12 has no remaining store, so
there is nothing to compare them against across images.

If the real ARM ELF shows loop perturbation or dataflow drift, V13 fails
qualification even if the source looks correct.

## Retained V12 Whole-Image Proofs

The retained V12 executable proofs that need whole-image artifacts (stock
vector table, NVIC hard-bypass, path-sensitive CMD/QREAD, PMU, H-PRINTF, golden
output, terminal release) are **not yet qualified for the V13 image**. They will
be re-run against it by the V13 build graph, which does not exist yet. Until
then `check_pmu_completion_poll_count_v13` emits no manifest boolean for any of
them; the single retained-V12 proof it does enforce is the absence of an NVIC
enable in the V13 image.
