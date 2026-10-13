# V15 implementation protocol — Amendment 1

**Poll count: retained for reference equivalence, not admitted as a metric.**

Discovered before any board execution and before any experimental data existed.
The frozen design (`58b0cad`) and plan (`3ca7bb1`) are **not** modified: the
admission criterion they fixed is the criterion that was applied, and it is the
criterion that produced this outcome.

## What was measured

Two builds from the same frozen inputs, differing only in whether the primary
helper publishes its iteration counter:

| Build | Measured loop | Q equivalence |
| --- | --- | --- |
| S5, counter published | 6 instructions | `Q_S5_EQUIVALENT` |
| S5, counter not published (scratch) | 5 instructions | refused, `RULE_EQUIVALENCE_LOOP_SHAPE` |
| frozen V14 Q reference | 6 instructions | — |

The counter costs exactly one instruction per iteration: `adds r0, #1`.

## The conflict

Two frozen requirements pointed opposite ways.

The poll-count admission rule asks whether publication perturbs the loop
*against a no-publication S5*. It does, by one instruction, so the count is not
admitted.

The equivalence requirement asks whether the S5 loop matches the frozen V14 Q
loop. Removing the counter makes it five instructions against Q's six, which
fails — and that failure would demote the whole experiment to
`S5_WITHIN_VARIANT_ONLY`, discarding the matched control V15 exists to be.

## Decision

Preserve the reference-matched six-instruction loop. Preserve Q↔S5 equivalence.
Do not admit the poll count as an analytical metric.

```
poll_count_transport   PRESENT_REFERENCE_MATCHED
poll_count_admission   NOT_ADMITTED_DUE_TO_LOOP_PERTURBATION
```

The original absolute no-perturbation admission criterion is **unchanged**. What
this amendment records is that the criterion was applied, the count failed it,
and the instruction is retained for a different contract's sake -- not that the
criterion was rewritten to let the count pass.

### Why not simply admit it

The technically defensible argument is that V14 Q pays the same instruction, so
the perturbation relative to the reference is zero. That argument is sound and
it is still refused, because taking it *after seeing the measurement* would mean
changing a preregistered adjudication standard to fit the result. That is the
move this project has spent its entire history refusing, and the fact that no
board data exists yet does not make it a different move.

### Why not simply remove the counter

Because it sacrifices the primary experimental control for the absolute purity
of an auxiliary diagnostic. The priorities are the other way round: V15's
objective is a matched single-register control for V14 Q, and the poll count is
a convenience.

## What the analyzer may do with the value

Record that it is present, and that it is not admitted. Nothing else. These five
are forbidden and enumerated in the contract rather than left to judgement:

- choosing among S1–S6
- regression against cycles
- a histogram offered as evidence
- comparison between Q and S5
- poll count multiplied by loop cost as a visibility latency

A targeted negative is owed here and is listed in the plan's negatives: an
analyzer that reaches a verdict using the poll count, or a report carrying a
poll-count-based interpretation, must go RED.

## The sentence that goes in the write-up

> Poll-count publication is not perturbation-free relative to a minimal S5-only
> loop. However, removing it changes the primary-loop shape relative to the
> frozen V14 Q reference. The counter is therefore retained solely to preserve
> the matched-control structure; poll count is not admitted as an analytical
> metric.

## Provenance

Both builds are preserved as evidence. The no-count build is scratch: not a
deployment candidate, not a determinism build, and not a board candidate. Its
value is as direct evidence for why the shipped firmware keeps the counter.

| | |
| --- | --- |
| design anchor | `58b0cad`, unchanged |
| plan anchor | `3ca7bb1`, unchanged |
| amendment | this document |
