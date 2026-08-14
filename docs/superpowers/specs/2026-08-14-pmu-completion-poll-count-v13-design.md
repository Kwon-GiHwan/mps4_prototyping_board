# PMU_COMPLETION_POLL_COUNT_DIAG_V13 design

Date: 2026-08-14

## Objective

`PMU_COMPLETION_POLL_COUNT_DIAG_V13` asks one causal-characterization
question:

> Is V12's variable `P0 -> P1` interval explained primarily by a changing
> number of STATUS polls, by a changing average observation cost per poll, or
> by both?

V12 proved that the hard-floor/excursion structure persists when NPU IRQ
delivery, NVIC exception servicing, and ISR execution are hard-bypassed.
Within V12, `T2 -> P0` was 22 for 30/30 samples and `P1 -> P2` was 11 for
30/30 samples, while `P0 -> P1` varied. V13 preserves the V12 completion-poll
mechanism and publishes the existing loop induction state once, after P2, so
the host can derive how many STATUS loads occurred before the first successful
observation.

V13 is diagnostic only. It is not latency, `T_npu`, a STATUS-read latency,
bus latency, a performance baseline, Production END_ONLY, or MLEK evidence.
V12 and all earlier variants remain frozen.

## Frozen provenance

V13 branches from the V12 post-board evidence anchor:

```text
commit  f7da7e85bb50431818fdd59f7784ffe1cbd43842
tag     pmu-completion-poll-v12-board-evidence
branch  pmu-completion-poll-count-v13
```

The V12 implementation, host-fix, and board-evidence anchors remain separate:

```text
firmware/ELF  126ef064a3eff8b41429bb8a82c4756dc20fd000
host fix      de50534b1b92595a04f73ae82e0e5d0d96eb01e3
board result  f7da7e85bb50431818fdd59f7784ffe1cbd43842
```

V13 must consume the same frozen raw runner and vendor inputs used by V12. It
must not patch V12 generated output or modify V8/V9/V10/V11-A/V12, CFG, DIAG,
or Production artifacts. The proposed wire schema is `13`; the proposed build
ID is `0x33314950` (`PI13` in little-endian byte order).

## V12 final-ELF fact established before design

The authoritative V12 ELF has SHA-256
`cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401`.
Its helper is at `0x31002344`. The loop was compiled as:

```text
3100234c  movw r2, #10000
31002352  mov  r3, r2
31002354  ldr  r0, [r1,#4]      ; exact NPU STATUS load
31002356  tst.w r0, #2
3100235a  bne   31002366        ; success edge
3100235c  subs  r2, #1
3100235e  subs  r3, #1
31002360  bne   31002354        ; loop back-edge
31002362  mov   r0, r2          ; timeout returns zero
```

At the success edge, the two register-local counters equal:

```text
remaining = 10000 - failed_polls
```

The successful STATUS load is itself an observed poll, so:

```text
poll_iterations = 10001 - remaining
```

The V12 success block overwrites both counter registers while materializing
the DWT and timestamp-storage addresses. V12 therefore did not publish the
counter and its 30 archived samples cannot be retroactively assigned poll
counts.

## Alternatives considered

### 1. Publish the existing induction state once after P2 — selected

Use the existing source-level loop index/limit state to publish one
`poll_remaining_at_success` value after P2. This adds no per-iteration work and
keeps the new SRAM side effect outside both authoritative V12 timing
intervals. Final-ELF equivalence and dataflow gates decide whether the compiler
actually preserved that intent.

### 2. Replace the loop with a hand-written assembly countdown — rejected

Assembly could make the remaining register explicit, but it would replace the
qualified V12 C loop and create a new completion-observation mechanism. A
numerically cleaner counter would come at the cost of weaker continuity with
the V12 evidence.

### 3. Infer poll count from V12 timing modes — rejected

The V12 cycle values show discrete structure, but no payload contains the
number of STATUS loads. Inferring counts from a presumed cycles-per-poll
ladder would make the proposed explanation self-confirming and cannot
distinguish count variation from per-poll cost variation.

## Selected runtime design

The V12 helper, hard-bypass, stock-vector, success/timeout, CMD/QREAD, PMU,
golden-output, and terminal-release contracts remain unchanged except for one
new success-only publication:

```text
T2  NPU CMD submit complete
P0  poll helper entry

repeat at most 10000 times:
  STATUS load
  test bit 0x02
  success -> P1
  otherwise advance the existing bounded-loop induction state

P1  first successful STATUS observation
P2  existing helper-exit timestamp
R0  store poll_remaining_at_success exactly once
helper return
```

`R0` is a logical publication point, not a new timestamp. It must satisfy:

```text
successful STATUS load < P1 < P2 < R0 store < helper return
```

No extra STATUS read, DWT read, PMU/NPU/NVIC MMIO, barrier, function call, or
stack access is allowed between P2 and the remaining-value store. Address
materialization and the single SRAM store are the only new effects permitted
there.

The source may express the value from the existing zero-based loop index, for
example as `10000U - i`, but source appearance is not qualification evidence.
The final ELF must prove that the stored value is the actual branch-controlling
induction state: the same decrement target that controls the failed-poll
back-edge and survives along the success edge until the post-P2 publication
store. A constant, independently recomputed counter, unrelated variable, value
derived from another loop, or reloaded approximation fails qualification.

## Success and timeout semantics

For a successful sample:

```text
1 <= poll_remaining_at_success <= 10000
poll_iterations = 10001 - poll_remaining_at_success
1 <= poll_iterations <= 10000
```

The boundary cases are:

```text
success on first poll      remaining=10000  iterations=1
success on poll 10000      remaining=1      iterations=10000
```

Timeout must not publish a plausible zero or stale value. Before every run the
storage is reset to an explicit invalid sentinel. On timeout:

- P1 and P2 retain the V12 timeout-invalid semantics;
- `poll_remaining_at_success` remains invalid;
- `poll_iterations` is `None`/not emitted;
- timing/count/ratio fields are excluded from all distributions;
- the sample is invalid and the same boot is blocked exactly as in V12.

The sentinel is ABI evidence only and must never enter statistics.

## Wire and host-derived contract

V13 appends one target word:

```text
poll_remaining_at_success
```

It does not publish both remaining and iterations. The host independently
derives:

```text
poll_observation_cycles = u32(P1 - P0)
poll_iterations = 10001 - poll_remaining_at_success
average_cycles_per_observed_poll =
    poll_observation_cycles / poll_iterations
```

The ratio is a descriptive diagnostic statistic. It includes loop control,
branch/decrement behavior, STATUS MMIO observation, and the final success
path. It is not a pure STATUS-read, NPU, CPU, bus, or interconnect latency.

Existing V12 delta identities remain authoritative and are re-derived from raw
payload bytes. `submit_to_status_completion_observed_cycles = u32(P1 - T2)`
remains the authoritative diagnostic timing for completion observation. The new
remaining/count field is explanatory evidence for decomposing the already
localized `P0 -> P1` variability; it does not replace the V12/V13 retained
timing boundary. The new validity terms include:

- remaining is valid only on poll success;
- remaining and derived iterations are each in `1..10000`;
- timeout exposes neither iterations nor ratio;
- P0/P1/P2 and all retained V12 gates remain valid;
- the raw and re-read payloads are byte-identical;
- manifest, artifact, vector, NVIC, PMU, golden, CMD/QREAD, and release
  identities remain unchanged.

## V12-to-V13 final-ELF equivalence gate

This is the primary V13 pre-board gate. A source-level claim that the loop was
not instrumented is insufficient.

The checker identifies the V12 and V13 loop regions from semantic anchors,
not fixed addresses, then compares normalized CFG and instruction effects.
It permits register renaming, PC-relative literal relocation, code-address
movement, and equivalent branch encodings. It does not permit additional
runtime work on the loop path.

The V12 and V13 loop regions must have equivalent:

- one exact NPU STATUS MMIO load per iteration;
- completion mask `0x02` and the same successful-load dataflow;
- success and failure branch topology;
- two induction-decrement operations on each failed observation;
- one conditional loop back-edge;
- timeout edge after the 10000th failed observation;
- absence of calls, barriers, stack access, and other MMIO.

V13 must have, relative to V12:

```text
extra per-iteration instructions   0
extra per-iteration loads/stores   0
extra per-iteration MMIO           0
extra loop spills/reloads          0
```

The whole V13 helper must remain a leaf with no push/pop or stack spill. If
the new live-out forces a prologue, epilogue, loop bookkeeping, spill/reload,
or any altered loop memory effect, the build fails. The gate is not relaxed;
the publication mechanism must be redesigned.

Separately, the V13-only success suffix must prove:

- P1 and P2 retain their V12 order and DWT/SRAM meaning;
- exactly one remaining-value SRAM store occurs after P2 and before return;
- its value reaches the store from the actual loop-control induction dataflow
  that was decremented on each failed poll;
- no reinitialization or unrelated recomputation intervenes;
- the store is unreachable from timeout;
- no second remaining/count store exists on an active path.

Raw machine-byte equality is supporting evidence only, not the authority,
because relocation and register allocation may legitimately change encoding.

## Fail-closed negative tests

The firmware/ELF checker must deliberately reject at least:

1. completion mask changed from `0x02`;
2. second STATUS read on any iteration or on success;
3. extra loop instruction, load, store, MMIO, or call;
4. one decrement removed or a third decrement added;
5. loop back-edge or success/timeout topology changed;
6. stack spill/reload or push/pop introduced;
7. remaining store moved before P2;
8. remaining store duplicated;
9. remaining store reachable from timeout;
10. constant or unrelated value stored as remaining;
11. value reinitialized between loop success and publication;
12. valid remaining outside `1..10000`;
13. timeout publishing remaining, iterations, or ratio;
14. retained V12 vector/NVIC/CMD/QREAD/PMU/golden/release drift.

Positive fixtures must cover success on poll 1, an interior poll, poll 10000,
and timeout.

## Campaign and analysis

After clean ARM build determinism, actual-ELF qualification, host regression,
and independent review, the first board campaign is:

```text
3 independent full boots x 10 consecutive valid runs = 30 samples
```

Any timeout or invalid sample stops that boot and requires a fresh boot. It is
not included in the 30-sample dataset.

The analyzer preserves boot and within-boot run index and reports:

- `poll_observation_cycles` and `poll_iterations` per sample;
- floor/excursion labels based on the V13 observation distribution;
- per-boot and floor/excursion poll-count distributions;
- a scatter dataset of iterations versus observation cycles;
- Spearman rank correlation with average ranks for ties;
- an ordinary least-squares descriptive fit
  `poll_cycles = alpha + beta * poll_iterations`;
- residuals and per-boot residual summaries;
- `average_cycles_per_observed_poll` distributions.

The implementation uses the Python standard library and records the exact
formulas. Correlation, fit, and residuals are descriptive characterization,
not a performance model or a claim of causality.

Interpretation is limited to:

- more iterations with a small residual spread: completion required more
  STATUS observations under this polling intervention;
- similar iterations with variable cycles/ratio: per-observation execution
  cost is variable under this intervention;
- both variable: multiple or interacting effects remain unresolved.

Even the first outcome does not distinguish later NPU command completion from
later STATUS visibility.

## Qualification phases

1. Freeze this design and implementation plan on the V13 branch.
2. TDD the source and final-ELF equivalence/dataflow checker, including all
   deliberate mutations.
3. Generate V13 only from frozen raw inputs and keep V12 tracked artifacts
   byte-untouched.
4. Perform two isolated clean ARM builds and compare declared artifacts.
5. Run the equivalence gate against the authoritative V12 and actual V13 ELF.
6. Qualify schema/parser/collector/analyzer and all retained regressions.
7. Obtain independent correctness and security review.
8. Create a pre-board anchor only after all prior gates pass.
9. Run the 3 x 10 board campaign under the existing deploy/restore procedure.

Until phase 8 is complete, V13 is not pre-board qualified. Until phase 9 is
complete, it has no board evidence. Production END_ONLY remains frozen and
MLEK remains blocked throughout.
