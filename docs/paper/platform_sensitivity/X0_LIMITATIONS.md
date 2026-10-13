# X0 limitations and discrepancies

## 1. `num_macs=100` — auxiliary probe discrepancy (no load-bearing impact)

The frozen `MAIN_EXPERIMENT_MATRIX.md` records that
`FVP_Corstone_SSE-300_Ethos-U55` **accepts** `num_macs=100`, and uses it to
argue the FVP range-checks bounds without validating the discrete set. On the
current stack that invocation is **rejected**:

```
FATAL ERROR: The number of MACs parameter value '100' for Ethos-U55 is not
valid! Expected 32, 64, 128, or 256.
```

Classification per the manager decision tree:

- **CASE B (stack drift) is excluded.** The executable reports
  `Fast Models [11.22.35 (Aug 18 2023)]`, identical to the frozen record, and
  the binary is the same install path/date.
- **CASE A cannot be tested.** The historical probe's script, command line,
  and acceptance criterion were **not archived** — only the prose claim exists.
  Three invocation styles were tried now (bare `-C`, with `--cyclelimit 1`,
  with `--list-params`); all reject.
- Recorded verdict: **`HISTORICAL_AUXILIARY_RECORD_DISCREPANCY`** with
  **`NO_LOAD_BEARING_IMPACT`**.

Why no impact: the authoritative discrete support set is unchanged
(U55 {32,64,128,256}, U65 {256,512}, U85 {128…2048}), it agrees with the Vela
enumeration, and no X1 load-bearing cell changes. The most likely mechanical
explanation — two validation layers, a parameter-framework range check that
`100` passes and a model-init discrete check that it fails — is consistent
with a historical probe that observed only the first layer, but this is
`NOT_SEPARATED` from other explanations without the archived method.

Actions taken: the frozen document is **not modified**. Actions **required of
the manuscript** (flagged, not applied): `MANUSCRIPT.md` §3.1 currently repeats
the `num_macs=100` example and the claim that the model "range-checks bounds
without validating the discrete set". That sentence is now known to be false
for this binary and should be replaced with the general rule — *FVP parameter
acceptance is not used as architectural configuration authority; discrete
support is established from source/Vela configuration authority* — which the
evidence still fully supports.

**Methodology lesson recorded**: an auxiliary probe whose conclusion enters a
paper must archive its invocation, not only its verdict.

## 2. Artifact portability is evidence-derived, not re-executed

`CROSS_PLATFORM_SAME_ARTIFACT_PORTABILITY = ESTABLISHED` (67 pairs) combines
two frozen sources: byte-identical Vela artifact hashes across platforms, and
per-cell build/execution evidence showing both platform cells executed with
`vela_sha_matches_frozen: True`. No cell was re-executed in X0. Should a future
X1 cell fall outside the frozen universe, its portability reverts to
`NOT_YET_QUALIFIED` and requires the lightweight `X1-Q` stage.

## 3. TA semantics are classified, not modelled

Only `TA_ON` / `TA_OFF` are asserted, from build-configuration authority. No
claim is made that TA-OFF equals zero-latency hardware or that TA-ON is
cycle-accurate. The SSE-320 `stub_timing_adapter.*` FVP parameters are
`SEMANTICS_UNRESOLVED` and are not treated as a TA profile control.

## 4. Namespace divergence is a harness fact

SSE-315/320 use `mps4_board.subsystem.ethosu.num_macs` while SSE-300/310 use
`ethosu.num_macs`. This is a command-line contract difference only; it does
not alter the measured quantity, but any X1 harness must handle both.

## 5. Repository state

`docs/presentation/ethos_u_measurement_deck.md` is
`PREEXISTING_UNRELATED_UNTRACKED`. It was not modified, committed, deleted, or
added to ignore rules.

## 6. Scope

X0 collected **no performance data** and computed no platform ratio. Compile
probes and FVP init probes only. Server free space at completion remains the
X1 blocker to revisit (≈4 GB); X1 acquisition should not start without a
cleanup pass under the standing hygiene rules.
