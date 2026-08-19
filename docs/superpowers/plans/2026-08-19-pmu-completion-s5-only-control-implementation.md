# PMU_COMPLETION_S5_ONLY_CONTROL — implementation plan

**Status: plan only.** No code yet. The plan is written against the design anchor
`58b0cad` (tag `pmu-completion-s5-only-control-design`) and goes out for its own
independent attack review before anything is implemented.

The design was attacked twice and revised twice. The failure mode of this stage
is different and specific: a plan that quietly relaxes the design because the
design is inconvenient to build. The six normative requirements below exist to
make that visible if it happens.

## Reference identity, frozen as plan input

Equivalence needs an unambiguous other side. It is not "the Q-ish code on some
branch" — it is the qualified V14 Q executable and its evidence:

| | |
| --- | --- |
| V14 pre-board qualification anchor | `619e957` (`pmu-completion-visibility-v14-preboard`) |
| V14 board evidence anchor | `153f368` (`pmu-completion-visibility-v14-board-evidence`) |
| V14 campaign execution protocol | `7c3c124` |
| Q reference artifacts | `FINAL8_A/Q/{APP,VECTORS,DDR}.BIN` and their manifest |
| Q reference image | `FINAL8_A/Q/runner_pmu_completion_visibility_v14.{elf,objdump,nm}` |

Any equivalence result computed against anything else is void.

## Normative requirements — may not be relaxed by this plan or by implementation

These come down from the design unchanged. A task that cannot be built without
weakening one of them is a task that stops and reports, not one that adjusts the
requirement.

1. **Equivalence failure does not relax the gate.** If
   `verify_single_register_equivalence(Q, S5)` fails, the cross-variant
   structural claim is dropped and V15 retreats to within-variant S5
   characterization. The gate is not loosened to admit the image.
2. **S5 primary path, on the final ELF.** `QREAD` reads 0, `QSIZE` reads 0,
   `STATUS` reads exactly one per iteration, mask `0x20`.
3. **Equivalence negative fixtures fail at the equivalence detector**, by its own
   rule identifier. A negative caught first by a neighbouring rule is a failed
   fixture, exactly as in V14's claim matrix.
4. **Poll-count publication only at zero loop perturbation**, decided on the final
   ARM image: zero extra per-iteration instructions, spills, reloads, moves,
   memory or MMIO. Otherwise the field does not exist.
5. **S1–S6 are code, not prose.** They become an enum and a verdict contract in
   the host analyzer, fixed by tests before any board data exists.
6. **Forbidden claims bind the output, not just the document.** The analyzer's
   verdict vocabulary and the report wording may not express any of the eleven.

## Chunk 1 — firmware contract and generator (RED first)

### Task 1: freeze schema-15 constants and the source fixtures

Schema 15, build ID in the PI15 family, and the appendix layout. The wire ABI is
V14's with the primary observation fields renamed to what they actually are:
`cmd_end_reached_observed`, `submit_to_s5_observed_cycles`. Names forbidden by
the design (`internal_completion_cycles`, `npu_completion_timestamp`, `T_npu`,
`execution_latency`) must not appear in the struct, the parser, or the manifest.

Verify: a test asserting the forbidden field names appear nowhere in the schema,
and that the frozen constants differ from V14's.

### Task 2: TDD the S5 primary loop contract on the source

The loop reads STATUS once per iteration, tests bit5, and freezes on first
observation. `irq_raised` comes from the same raw STATUS word — a second read is
a contract violation, not an optimisation.

Verify: RED fixtures for a second STATUS read, for a QREAD read inside the loop,
for a QSIZE read inside the loop, and for `irq_raised` taken from a separate
read.

### Task 3: inherit the rest of the V14 source contract unchanged

Pre-submit stopped gate with QSIZE read exactly once, stale STATUS rejection,
timestamp placement, bounded loop, first-observation freeze, the QREAD-based
convergence tail, fault priority, cleanup ordering, golden contract.

Verify: the V14 source-side rules apply to the S5 generated pair with the
variant-specific ones re-pointed, and each still has a targeted negative.

### Task 4: the frozen-input generator

Same shape as V14's patcher: pinned inputs, generated output, digests recorded.

Verify: the generator emits S5 from the pinned sources, and the source gate
accepts the generated pair.

## Chunk 2 — ARM build and final-ELF qualification

### Task 5: the isolated build graph

One build path, A then B, each copied out before the next — the corrected V14
procedure, not the one that compared different paths.

Verify: `mismatches=[]` from the hardened comparator, which now also refuses the
same root, path aliases, nesting and hardlinked artifacts.

### Task 6: the S5-only boundary gate

The executable claim from the design, split by phase:

```
PRE-FREEZE PRIMARY PATH        POST-FREEZE CONVERGENCE TAIL
  QSIZE  reads   0               QREAD   allowed
  QREAD  reads   0               STATUS  allowed
  STATUS reads   exactly 1/iter  QSIZE   still 0
  STATUS mask    bit5 / 0x20
```

Verify: rule identifiers in the claim matrix, targeted negatives failing at those
rules, applied to the real S5 image.

### Task 7: `verify_single_register_equivalence(Q, S5)`

Against the frozen Q reference image above. Normalized CFG, semantic instruction
roles, side-effect sequence; relocation and register allocation invariant.

Verify: the six negative fixtures from the design, each failing at this
detector's own rule; and the positive — only the observable load and test
exchanged — passing.

If it fails on the real pair: stop, report, and apply the fallback. Do not edit
the gate.

### Task 8: the poll-count admission decision

Build both ways and compare the measured loop bodies on the linked images.
Case A adopts the field; Case B deletes it. Record the decision and its evidence
either way.

## Chunk 3 — host chain

### Task 9: parser and classifier for schema 15

New modules. Requalified to V14's standard, not assumed to inherit it.

Verify: frame geometry, digest binding, phase validity, and the same
contract-consistency checks V14's classifier grew — flags agreeing with the raw
words they came from, above all.

### Task 10: the analyzer, with S1–S6 as a verdict contract

The outcomes become an enum. The analyzer re-derives its classification from raw
fields rather than reading a field someone else computed — the defect V14's
analyzer had and had corrected.

Verify: one synthetic campaign per outcome S1–S6 producing exactly that verdict;
mutations of each decision going RED at their own check; and a test asserting no
forbidden claim appears in the verdict vocabulary.

### Task 11: collector and campaign runner

The V14 collector's fail-closed behaviour, reinstantiated for schema 15. The
campaign runner is V14's with the variant set changed, and it keeps the priming
step that V14's first cell aborted without.

Verify: boot reuse, run-sequence gaps and repeats, foreign variants, and
top-ups after a failure all refused.

## Chunk 4 — pre-board qualification

### Task 12: the full pass at one HEAD

Firmware suite, host suite, comparator regression, A/B determinism, real ELF
gates, manifest replay, frozen V13/V14 integrity, board-preflight synthetic
suite, requirements matrix, silent-gate telemetry.

Exit: every item green at one commit, with the matrix recomputed there rather
than assumed from an earlier run.

### Task 13: pre-board anchor

Annotated tag on the qualified HEAD, carrying the same kind of message V14's
did — what was executed, against what, and what was not run.

## Chunk 5 — board, after explicit GO

### Task 14: preflight

The V15 candidate through the existing twelve-gate contract: eight inherited
board gates unchanged, four V15-specific ones bound to the S5 candidate's own
hashes and manifest.

### Task 15: the campaign

3 independent boots x 10 consecutive runs, fixed in advance. Boot-first analysis,
pooling last. Boots that disagree resolve to S6 rather than to more boots.

### Task 16: restore and postflight

Original image restored byte-exact, then DDR, CPUWAIT, PING 3/3 from IDLE, seven
counters zero, USB off, card absent, mounts zero, root-inclusive holders zero —
before any verdict is published.

## What this plan does not do

- it does not modify V13 or V14, which are frozen historical evidence
- it does not merge to local `main` or push to `origin/main`
- it does not touch Production END_ONLY or MLEK
- it does not begin implementation before this plan has been attacked
  independently and anchored
