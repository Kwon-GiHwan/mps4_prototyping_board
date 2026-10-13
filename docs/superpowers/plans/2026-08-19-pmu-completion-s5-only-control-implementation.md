# PMU_COMPLETION_S5_ONLY_CONTROL — implementation plan

**Status: plan only, revised after a self-attack and an independent attack
review.** No code yet. Written against the design anchor `58b0cad` (tag
`pmu-completion-s5-only-control-design`).

The failure mode of this stage is specific and different from the design's: a
plan that quietly relaxes the design because the design is inconvenient to build.
The normative requirements below exist to make that visible if it happens.

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

An equivalence result computed against anything else is void, and there is a
negative fixture for it (N2).

## Comparison mode: one enum, carried everywhere

The design says that if `verify_single_register_equivalence(Q, S5)` fails, V15
retreats to within-variant characterization. Left as prose, that is a fallback
the program never actually takes — the document says one thing and the code keeps
comparing. So it is an enum, produced once and carried through every layer:

```
comparison_mode ∈ { Q_S5_EQUIVALENT, S5_WITHIN_VARIANT_ONLY }
```

```
firmware/build evidence -> manifest -> host parser -> classifier
    -> collector -> analyzer -> board preflight -> final report
```

Every layer carries it; **any disagreement between layers is a failure**, not a
resolution in favour of one of them.

### What each mode permits

| Outcome | `Q_S5_EQUIVALENT` | `S5_WITHIN_VARIANT_ONLY` |
| --- | --- | --- |
| S1 floor and excursions reproduce | as designed | valid, with the "comparable to Q-only" clause removed |
| S2 floor reproduces, no excursion | as designed | valid, with the "shared variability structure" clause removed |
| S3 excursion structure qualitatively differs from Q | as designed | **`NOT_APPLICABLE`**, reason `Q_S5_EQUIVALENCE_NOT_ESTABLISHED` |
| S4 no reproducible floor | as designed | valid, with the Q-relative reading removed |
| S5 bit5 never observed | as designed | as designed |
| S6 boot-mixed | as designed | as designed |

In fallback mode S1 means exactly *"the S5-only floor and excursion structure
reproduced across independent boots"* and nothing about Q. The analyzer must
refuse to emit S3 in fallback mode, and a fixture that tries must go RED.

## Normative requirements — not relaxable by this plan or by implementation

A task that cannot be built without weakening one of these stops and reports.

1. **Equivalence failure does not relax the gate.** It sets
   `comparison_mode = S5_WITHIN_VARIANT_ONLY` and disables cross-variant claims.
2. **S5 primary path, on the final ELF.** `QREAD` 0, `QSIZE` 0, `STATUS` exactly
   one per iteration, mask `0x20`.
3. **Equivalence negatives fail at the equivalence detector**, by its own rule
   identifier — not at a neighbour that catches them first.
4. **Poll-count publication only at zero loop perturbation** on the final ARM
   image, and the admission status is recorded either way.
5. **S1–S6 are code.** An enum and a verdict contract in the analyzer, fixed by
   tests before any board data exists.
6. **Forbidden claims bind the output.** The analyzer's verdict vocabulary and
   the report wording, not only the prose.
7. **Nothing is inherited by assertion.** Every claim carried over from V14 is
   classified (below) and carries its own V15 proof.

## Chunk 0 — the inheritance matrix, before any code

### Task 0: freeze the requirements and inheritance matrix

This is a design input, not a summary written afterwards. Built before Chunk 1
starts, because it decides what must be newly proved and what may genuinely be
inherited. "V14 already qualified this" is not an accepted answer anywhere.

Every claim gets exactly one classification:

| Class | Meaning | Example |
| --- | --- | --- |
| `UNCHANGED_AND_HASH_PINNED` | same object, pinned by hash, reachable in the V15 ELF | vendor terminal release |
| `REQUALIFIED_FOR_V15` | same claim, re-proved against the V15 image | running QSIZE reads 0 |
| `NOT_APPLICABLE` | the concept does not exist in V15, with the reason recorded | QS/SQ read-order equivalence |
| `NEW_V15_CLAIM` | did not exist in V14 | Q↔S5 equivalence; the S5-only boundary; S1–S6 |

Verify: the matrix resolves like V14's — every rule named exists and is in the
claim matrix, every host function and test named exists, every requirement names
exactly one authority, and no claim is left unclassified.

## Chunk 1 — firmware contract and generator (RED first)

### Task 1: freeze schema-15 constants and source fixtures

Schema 15, PI15 build ID, appendix layout. Primary observation fields named for
what they are: `cmd_end_reached_observed`, `submit_to_s5_observed_cycles`. The
names the design forbids (`internal_completion_cycles`, `npu_completion_timestamp`,
`T_npu`, `execution_latency`) must appear in no struct, parser or manifest.

Verify: a test asserting the forbidden names appear nowhere; frozen constants
differ from V14's.

### Task 2: TDD the S5 primary loop contract on the source

STATUS read once per iteration, bit5 tested, freeze on first observation.
`irq_raised` from the same raw STATUS word.

Verify RED: a second STATUS read; a QREAD read inside the loop; a QSIZE read
inside the loop; `irq_raised` from a separate read.

### Task 3: inherit the rest of the V14 source contract, by classification

Pre-submit stopped gate with QSIZE once, stale STATUS rejection, timestamp
placement, bounded loop, freeze, the QREAD-based convergence tail, fault
priority, cleanup ordering, golden contract — each carrying its Task 0 class and
its own proof.

### Task 4: the frozen-input generator

Pinned inputs, generated output, digests recorded, same shape as V14's patcher.

## Chunk 2 — ARM build and final-ELF qualification

### Task 5: the isolated build graph

One build path, A then B, each copied out before the next.

Verify: `mismatches=[]` from the hardened comparator.

### Task 6: the S5-only boundary gate

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

Against the frozen Q reference. Normalized CFG, semantic instruction roles,
side-effect sequence; relocation- and register-allocation-invariant.

Verify: the design's six negatives, each failing at this detector's own rule, and
the positive passing.

On failure: set `comparison_mode = S5_WITHIN_VARIANT_ONLY`, record the reason,
and continue. Do not edit the gate.

### Task 8: post-freeze equivalence

The minimal-control claim is about more than the primary loop: the convergence
tail and cleanup must also match the frozen V14 Q reference, semantically.

Verify (N3): an extra STATUS read in the tail, or a changed cleanup ordering,
fails the minimal-control claim.

### Task 9: the poll-count admission decision

Build with and without counter publication and compare the measured loop bodies
on the linked images. Case A adopts, Case B deletes the field. The admission
status — `ADMITTED` or `OMITTED_DUE_TO_LOOP_PERTURBATION` — is recorded either
way; a missing field with no recorded decision is a failure.

The counter-less build is **scratch, non-deployable, not a determinism build and
not a board candidate**. The real A/B determinism runs on the adopted candidate
alone.

## Chunk 3 — host chain

### Task 10: parser and classifier for schema 15

New modules, requalified rather than assumed. Flags must agree with the raw words
they came from.

### Task 11: comparison-mode propagation

The enum flows manifest → parser → classifier → collector → analyzer →
preflight → report, and disagreement anywhere is a failure.

Verify (N1, N2): equivalence FAIL with the manifest forged to PASS → FAIL;
manifest in fallback while the analyzer emits S3 → FAIL; fallback with
`cross_variant_comparable = true` → FAIL; equivalence PASS against the wrong Q
reference identity → FAIL.

### Task 12: the analyzer, with S1–S6 as a verdict contract

The outcomes are an enum. The analyzer re-derives from raw fields rather than
reading a field someone else computed.

The floor and excursion definitions are **copied into the V15 contract, not
referred to**:

```
boot minimum          = that boot's floor candidate
reproducible floor    = the same minimum value is the minimum of EVERY
                        independent boot
excursion             = a sample value above that boot's own minimum
pooling before boot classification = prohibited
```

Verify: one synthetic campaign per outcome S1–S6 producing exactly that verdict;
mutations of each decision going RED at their own check; S3 emission in fallback
mode going RED.

### Task 13: forbidden vocabulary, as an output test

Not a documentation lint. The analyzer's actual verdict vocabulary and report
output are tested (N4): mutating them to emit `latency`, `T_npu`, "Q is faster",
"S5 is slower" or `internal completion` must go RED.

### Task 14: collector and campaign runner

V14's fail-closed collector reinstantiated for schema 15; the campaign runner is
V14's at `7c3c124` with the variant set changed, keeping the priming step.

Verify: boot reuse, run-sequence gaps and repeats, foreign variants, and top-ups
after a failure all refused.

## Chunk 4 — pre-board qualification

### Task 15: the V15 static-evidence schema and preflight gate

V14's `STATIC_GATE_EVIDENCE` requires `read_order_equivalent` and
`common_tail_shared`, neither of which exists for a single-variant experiment.
Feeding it `true` would be a gate passing because it was told what it wanted to
hear. V15 gets its own:

```
real_elf_pass                     == true
primary_s5_only_boundary          QREAD 0 / QSIZE 0 pre-freeze,
                                  STATUS exactly 1 per iteration, mask 0x20
running_qsize_reads               == 0
post_freeze_tail_and_cleanup      == frozen V14 Q reference, semantically
equivalence.status                PASS with reference identity and evidence hash,
                                  or FALLBACK_WITHIN_VARIANT with a fixed reason
                                  and cross_variant_claims_enabled = false
poll_count                        ADMITTED or OMITTED_DUE_TO_LOOP_PERTURBATION
comparison_mode                   Q_S5_EQUIVALENT or S5_WITHIN_VARIANT_ONLY
```

`UNKNOWN`, `NOT_RUN`, or a missing evidence hash is a board-gate FAIL.

### Task 16: the full qualification pass at one HEAD

Firmware suite, host suite, comparator regression, A/B determinism, real ELF
gates, manifest replay, frozen V13/V14 integrity, board-preflight synthetic
suite, the Task 0 matrix recomputed here, and silent-gate telemetry.

### Task 17: pre-board anchor

Annotated tag on the qualified HEAD, carrying what was executed, against what,
and what was not run.

## Chunk 5 — board, after explicit GO only

### Task 18: preflight

Eight inherited board gates unchanged; the V15 static-evidence schema above in
place of V14's fourth gate.

### Task 19: the campaign

3 independent boots × 10 consecutive runs, fixed in advance. Boot-first analysis,
pooling last. Boots that disagree resolve to S6 rather than to more boots.

### Task 20: restore and postflight

Original image restored byte-exact, then DDR, CPUWAIT, PING 3/3 from IDLE, seven
counters zero, USB off, card absent, mounts zero, root-inclusive holders zero —
before any verdict is published.

## Negatives this plan owes

| | Scenario | Required |
| --- | --- | --- |
| N1 | equivalence FAIL, report says "comparable to Q" | FAIL |
| N2 | equivalence run against a structurally similar but wrong Q identity | FAIL |
| N3 | primary loop perfect, tail gains a STATUS read or cleanup reorders | FAIL |
| N4 | analyzer emits a forbidden term in its verdict vocabulary | RED |

## What this plan does not do

- it does not modify V13 or V14, which are frozen historical evidence
- it does not merge to local `main` or push to `origin/main`
- it does not touch Production END_ONLY or MLEK
- it does not begin implementation before this plan is anchored
