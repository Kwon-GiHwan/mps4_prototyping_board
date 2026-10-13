# P0-E2 limitations

What the two added workloads do not establish, and where this campaign departed
from the letter of its own contract. Contract:
`docs/superpowers/plans/2026-09-16-p0e2-two-workload-extension-plan.md`.

## Approval

There is no manager GO for this extension. It ran on the repository owner's
direct instruction, recorded in contract section 9. Nothing here may be
described as performed under manager approval.

## Departures from the contract text, and why

Three places where the contract's prose does not describe the path it binds the
work to. In each case the binding rule in section 3 was followed and the prose
was not, because the rules name the September campaign and the prose names a
tool that campaign did not use.

**The method paragraph names the wrong tool.** Contract section 2 describes
`patch-vela.py` inserting `cmd0.NPU_OP_IRQ` after `generate_operation_code`, and
`patch-driver.py` snapshotting the PMU. Those are the exploration tools in
`/workspace/per-layer-profiling/`. The September campaign
(`pd2_orchestrator.log`, and the tool digests in the two frozen evidence
manifests) used `insert_irq.py --all --onehot`, which rewrites the compiled
command stream after Vela rather than patching Vela, together with
`patch_app.py` and `patch_driver_u85_v3.py`. `RULE_P0E2_PATCH_IDENTITY` requires
the September patches by digest, so the September tools were used and the
section 2 paragraph was not followed. The same section's own opening sentence —
"use the existing P0-D2 path as-is" — says the same thing.

**The layer cap constant.** Contract section 2 cites `PROFILING_MAX_LAYERS =
256`. That constant belongs to the exploration tool `patch-driver.py`. The
campaign driver `patch_driver_u85_v3.py` declares `PLPROF_MAX_LAYERS = 512`. The
gate refuses at the tighter of the two, so the question is moot here: every
measured cell is at or below 228 operations and passes under either reading. It
is recorded because a future cell between 257 and 512 operations would make the
two readings disagree, and that disagreement should be resolved before such a
cell is measured, not after.

**The instrumentation residual is not a constant.** Contract section 3 asks
`RULE_P0E2_SUM_COHERENT` to check the per-operation sum against the clean whole
"within the instrumentation residual constant". No such constant exists. Over
the fifteen frozen September cells the residual `sum(unit ccnt) - clean_total`
runs from -2873 to +2272 cycles, that is -2.14% to +1.96%, and it grows with the
number of service windows because the IRQ handler loses the cycles between its
PMU snapshot and its PMU reset once per window. The gate therefore uses an
envelope over those fifteen cells — 3000 cycles absolute and 3.0% relative, both
required — derived and written down before any P0-E2 cell had been measured.
It is an envelope over September's behaviour, not a physical bound, and a cell
inside it is not thereby shown to be correctly attributed.

**That envelope then refused three of the six cells, and was not changed.**
`wav2letter_pruned_int8__512_Low` (+17712 cycles),
`mobilenet_v2_1.0_224_INT8__512_Mid512` (-3313) and
`mobilenet_v2_1.0_224_INT8__512_Low` (-3298) exceed the absolute term. All three
are well inside the ratio term: the worst of the six cells is 0.18%, against a
3.0% bound and against a September spread reaching 2.14%.

The absolute term is what fires, and it is the term that does not scale. It was
derived from cells whose clean totals run 36,086 to 812,074 cycles; these two
workloads run 1,869,068 to 15,147,068, two to four hundred times larger. Per
service window the P0-E2 residuals are -19.9 to +154.0 cycles against
September's -52.5 to +119.6, so the per-window behaviour is in the same family
and only the whole-model total has grown.

None of that is a reason to move the bound now. The contract forbids relaxing a
gate after seeing the data, and an envelope that is widened the first time it
refuses something is not a gate. The three cells are recorded `FAIL` on
`RULE_P0E2_SUM_COHERENT`, every other gate passes on them, and their
measurements are in the tables with that verdict attached. Whether the absolute
term should be replaced by a size-scaled one is a decision for the operator, and
under this repository's convention it would be registered as an amendment before
any re-run, never as an edit to this file.

A question asking which bound to preregister was sent to the coordinator before
any P0-E2 cell was measured, and timed out unanswered; the envelope above is the
default that was recorded in its absence, and it was fixed before the data
existed.

## What the numbers are and are not

**Measured, not estimated.** Every per-operation cycle figure here comes from
PMU counters read by the target at an IRQ. No cell is filled from Vela's
`--verbose-performance` estimate. The Vela estimates that appear in
`U85_256_512_DIFFERENTIAL.csv` (`vela_cycles_256`, `vela_cycles_512`) are the
compiler's own predictions carried alongside for comparison, in the columns the
September campaign already used for them.

**U85 only.** The IRQ per-layer results in
`/tmp/per-layer-profiling/models/{asr,ic}-256-b*` on the build host are
`Ethos_U55_High_End_Embedded` runs from unregistered exploration on 7/1 and 7/4,
cut into fifteen-operation batches with `ETHOSU_PROF_START/END`. They are not
merged into any table here and are not evidence about U85.

**No batch splitting.** Every cell was measured in one pass. The cap is a STOP,
not a reason to split, and the gate refuses a cell that declares a split even
when it is under the cap.

**Attribution is by service window, not by operator.** The unit of measurement
is one IRQ service window. An operator whose launches all fall in windows it
does not share gets an exact cycle count; an operator sharing any window with
another is `NOT_SEPARATED` at operator level and appears with empty cycle
columns. The window rows in `U85_ATTRIBUTION_UNITS.csv` remain lossless in
either case. `U85_GROUP_DIFFERENTIAL.csv` is the floor this forces: the finest
partition that is a common refinement on both sides of a binding pair.

**The 256 to 512 step moves two things at once in B-frozen.** `256_Low` to
`512_Mid512` changes the MAC count and the Vela system config together, because
that is what the frozen paper sweep did. `B-held` (`256_Low` to `512_Low`) holds
the system config and moves only the MAC count. Neither pair isolates a single
mechanism, and `512_Low` has no counterpart in `canonical_cells.csv`, so its
clean cycles cannot be checked against the frozen sweep the way the B-frozen
cells can.

**No causal claims.** Nothing here says a ublock, a block config, or memory
bandwidth caused a direction. The `*_CHANGED` columns record that a compiler
field differed between the two sides; they do not attribute the cycle difference
to it.

**No cross-generation event identity.** U85 emits `SRAM_*` and `EXT_*`; U55 and
U65 emit `AXI*`. The event columns are not claimed equivalent across
generations.

## Tooling defect found in the frozen analysis chain

`pd_groups.py` does not produce a reproducible byte sequence.
Its group ordering derives from iteration over a `set` of strings, so
`PYTHONHASHSEED` changes the order of rows whose sort keys tie. Three runs over
the identical frozen September inputs produced three different file digests; the
row *content* was identical every time, and pinning `PYTHONHASHSEED=0` makes it
stable but does not reproduce the committed file either.

Consequences, in order of importance:

- `U85_GROUP_DIFFERENTIAL.csv`'s digest in `U85_MECHANISM_META.json`
  (`08bf0142…`) cannot be reproduced by re-running the tool. The other four
  recorded digests were reproduced exactly from the frozen evidence tree.
- The P0-E2 regression check on this one file is therefore row-wise (the five
  existing workloads' rows must come back an identical multiset) rather than
  byte-wise. The other three CSVs are checked byte-wise, in order.
- This is a pre-existing property of the September tool, unchanged by P0-E2. It
  was not repaired here: `pd_groups.py` is frozen analysis code and editing it
  to sort deterministically would alter the tool that produced the frozen rows.
  It is reported rather than fixed.

## Scope

Six cells: two workloads by three bindings. The contract forbids adding another
MAC, memory mode, workload, or platform under it. No board was used; every
measurement is `FVP_Corstone_SSE-320` with the timing adapter on and
`Dedicated_Sram`. A build that compiles is not a cell that runs, and every cell
reported here both compiled and ran; no cell was dropped.
