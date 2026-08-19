# Attack review: S5-only implementation plan

Five attacks on the plan at `667f19d`, by its author, before the independent
pass. Two are blocking.

## P1 — The equivalence fallback silently invalidates part of the preregistration

**Severity: blocking.**

The design preregisters S1–S6, and three of those rows are phrased against
Q-only: "structure comparable to Q-only", "differs qualitatively from Q-only".
The plan also says that if `verify_single_register_equivalence` fails, V15
retreats to within-variant characterization.

Both are right on their own and nobody has reconciled them. If the equivalence
gate fails, the comparisons those rows depend on are no longer available — so
either the outcome table quietly loses its meaning, or someone re-interprets it
at analysis time, which is exactly what preregistration exists to prevent.

The plan must state, before implementation, which outcomes survive the fallback
and how the surviving ones are phrased. My proposal:

| | equivalence holds | equivalence fails |
| --- | --- | --- |
| S1 floor + excursion reproduce | as written | keep, drop the "comparable to Q-only" clause |
| S2 floor, no excursion | as written | keep, drop the "shared variability structure" clause |
| S3 floor, different excursion structure | as written | **void** — it is a comparison |
| S4 no reproducible floor | as written | keep, drop "does not mean Q is faster" (nothing to compare) |
| S5 bit5 never observed | as written | as written |
| S6 boot-mixed | as written | as written |

## P2 — The V14 preflight's `STATIC_GATE_EVIDENCE` cannot pass honestly for V15

**Severity: blocking.**

Task 14 reuses the twelve-gate preflight with the four V15 gates "bound to the S5
candidate". But `STATIC_GATE_EVIDENCE` requires three facts: `real_elf_pass`,
`read_order_equivalent` and `common_tail_shared`.

V15 has one variant. There is no read-order equivalence to establish and no tail
shared *across variants*. So that gate would be handed either fabricated values —
answering true to a question never asked — or nulls, refusing the deployment for
the wrong reason.

A gate that passes by being told what it wants to hear is the same defect this
project has found eleven times. The V15 preflight needs its own static-evidence
gate naming the evidence V15 actually produces: REAL_ELF, the S5-only boundary
claim, and the equivalence result *or* its recorded fallback.

## P3 — "Floor" and "excursion" are not defined in the plan

**Severity: gap, closable by inheritance.**

S1–S6 turn on whether a floor "reproduces" and whether excursions are "present",
and the plan leaves both to the reader. V14's analyzer already defines them
operationally — the same value must be the minimum of *every boot separately*,
never pooled, and an excursion is any value above that boot's own minimum — and
Task 10 should say it inherits those definitions rather than inventing them at
analysis time.

## P4 — No task builds the requirements matrix

**Severity: gap.**

Task 12 lists "requirements matrix" among the things that must be green, and no
task produces one. V15 adds claims V14 did not have (equivalence, the S5-only
boundary) and a new host chain, so its matrix is not V14's with a search and
replace. It needs its own task, before Task 12 rather than inside it.

## P5 — Task 8 builds the same variant twice for comparison

**Severity: minor, worth writing down.**

The poll-count decision requires building with and without the counter and
comparing the loop bodies. That is two builds of one variant, which is not what
the determinism procedure is for. The plan should say the counter-less build is
scratch evidence, never a deployment candidate, and never enters the A/B
comparison.

## Disposition

| Attack | Blocking? | Close |
| --- | --- | --- |
| P1 fallback vs preregistration | yes | outcome-survival table above, fixed before implementation |
| P2 static-evidence gate | yes | V15-specific static-evidence gate; no fabricated inputs |
| P3 floor/excursion definitions | no | inherit V14's operational definitions explicitly |
| P4 requirements matrix | no | its own task before the qualification pass |
| P5 scratch build | no | state that it is scratch and excluded |
