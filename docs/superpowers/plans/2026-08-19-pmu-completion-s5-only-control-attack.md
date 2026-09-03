# Attack review: PMU_COMPLETION_S5_ONLY_CONTROL design

Seven attacks on the design as written, by its author, before it goes out for an
independent pass. Each is stated as the sentence someone could write later that
the design does not currently prevent.

Two are severe enough to block anchoring on their own: **A1** and **A2**.

---

## A1 — The design does not pre-register how the result will be interpreted

**Severity: blocking.**

The design says V15 "can strengthen or weaken" the V14 interpretation and stops
there. That leaves the mapping from outcome to meaning to be chosen *after* the
data exists, which is the precise failure mode this project has spent its whole
qualification effort eliminating everywhere else — the analyzer was deliberately
frozen before V14's data existed, and the characterization was kept apart from
its verdict for exactly this reason.

A control whose interpretation is decided after the fact is not a control. The
design must fix, before any firmware is written, what each outcome means:

| S5-only result | What it supports | What it does not |
| --- | --- | --- |
| floor and excursion reproduce, structure comparable to Q-only | single-register polling produces this structure regardless of which register; V14's dual-read pattern is less likely to be an artefact of *having* two reads | still says nothing about which observable is visible first |
| no floor reproduces, or structure differs qualitatively from Q-only | the structure is register-dependent, so cross-variant structural reasoning in V14 is weaker than assumed | does not by itself explain V14's second-read pattern |
| S5 cannot be observed at all in the bounded loop | bit5 is not a usable single-register completion observable under this discipline | does not retroactively invalidate V14's dual-read observations |

Anything not in that table is a post-hoc reading and must be labelled as one.

## A2 — Nothing proves the S5 loop is the Q loop with one thing changed

**Severity: blocking.**

The design's entire value rests on "the same experiment with a single observable
replaced". Nothing in it proves that.

V14 did not leave this to trust: `RULE_READ_ORDER_EQUIVALENCE` proves QS and SQ
differ in read order **and in nothing else**, on the linked images. There is no
counterpart for Q against S5, and the gate audit confirms only one detector,
`verify_primary_loop_image`, is variant-parameterised at all.

Without an equivalence proof, "Q-only and S5-only have comparable structure" is
a claim about two loops that may differ in ways nobody checked — different mask
and test, different register pressure, a different number of instructions per
iteration.

Two ways to close it, and the design must pick one rather than leaving it open:

1. **Add the gate.** A `verify_single_register_equivalence(Q, S5)` proving the
   two primary loops are identical up to the observable's load and test, in the
   same spirit as read-order equivalence. Strongest, and it makes the structural
   comparison mean something.
2. **Drop the claim.** State that no structural equivalence between Q and S5 is
   established, and confine V15's conclusions to *within-variant* reproducibility.

Option 1 is recommended. Option 2 is honest but leaves the control weaker than
the reason for building it.

## A3 — "S5-only" is true of the measured window, not of the run

**Severity: wording, but it is the wording the whole confound turns on.**

The convergence tail still reads QREAD, by design and correctly. So V15 is
S5-only up to the first-observation freeze and not after it. Since the confound
under study *is* QREAD MMIO traffic perturbing the polling environment, the
design must say plainly that the control removes that traffic from the measured
window only, and that the tail's traffic occurs after the measurement it could
have perturbed.

## A4 — The campaign shape is unspecified

**Severity: blocking before implementation, not before anchoring.**

V14 had nine cells, three variants, a balanced Latin square, and nine
independent boots, and the balance is what let it rule out position and round
effects. V15 has one variant, so there is no square to balance and no
position axis at all.

Unanswered: how many independent boots, how many runs per cell, and what
protects against a time-order effect when there is no second variant to
alternate with. At minimum the floor must be required to reproduce as the
minimum of every boot separately, as V14's analyzer already does rather than
pooling.

## A5 — "Minimal change" is minimal in the firmware and not on the host

**Severity: scope accuracy.**

Schema 15 with its own build ID means a new parser, a new classifier, a new
manifest binding and a new collector instantiation. The design lists "manifest
and provenance binding" and "the collector's fail-closed behaviour" among things
inherited unchanged, which is true of their *shapes* and false of their
*modules*: every one of them is new code that must be requalified to the standard
V14's were held to, including the claim matrix, the targeted negatives and the
silent-gate telemetry.

Saying so now prevents the implementation plan from budgeting for a firmware
change and discovering a host chain.

## A6 — The mirror of NO_QSIZE does not exist

**Severity: gap.**

`RULE_PRIMARY_NO_QSIZE` proves V14's measured loop never reaches QSIZE. The S5
loop needs the analogous prohibition — that it never reaches **QREAD** in the
measured window — and no such rule exists. Without it the central property of the
control is asserted rather than gated, which is precisely the shape of the
silent gates this project has found eleven of.

## A7 — "Take the poll count only if it is free" has no arbiter

**Severity: gap.**

The design says the poll count is taken only if an existing counter yields it
without touching the loop body, which is the right rule and has no decision
procedure attached. "Free" must be decided on the linked image — the measured
loop's body identical with and without the counter — and not by whoever is
writing the firmware that day.

---

## Disposition

| Attack | Blocking? | Proposed close |
| --- | --- | --- |
| A1 pre-registration | yes | interpretation table above, fixed in the design before implementation |
| A2 equivalence proof | yes | add `verify_single_register_equivalence`, or drop cross-variant structural claims |
| A3 measured-window wording | no | state the boundary explicitly |
| A4 campaign shape | before implementation | specify boots, runs, and per-boot floor requirement |
| A5 host scope | no | restate what is inherited in shape versus in code |
| A6 no-QREAD rule | yes, before implementation | add the mirror rule to the claim matrix |
| A7 poll-count arbiter | no | decide it on the linked image |

Nothing here requires the design to be abandoned. A1, A2 and A6 require it to be
revised before it is anchored.


---

# Independent attack review

The design went out with the seven attacks above already closed or dispositioned.
The independent pass returned **DESIGN: CONDITIONALLY APPROVED** with three
blocking items and five additional prohibitions. All are now closed in the design.

| # | Finding | Close |
| --- | --- | --- |
| B1 | the equivalence gate was named but not *defined*; requiring raw instruction equality would be wrong and requiring nothing would be useless | defined as relocation- and register-allocation-invariant semantic CFG plus side-effect equivalence, with the permitted difference stated as the observable substitution alone, a per-iteration quantitative table, and six negative fixtures each required to fail at the equivalence detector itself |
| B2 | three outcomes hid the distinctions a post-hoc reading would exploit | six preregistered outcomes S1–S6, separating "no excursions" from "different excursions", and registering `BOOT-DEPENDENT / UNRESOLVED` so that "two of three boots" cannot become a reproduction criterion after the fact |
| B3 | "S5-only" was prose, and it is one of the load-bearing claims | split into an executable pre-freeze / post-freeze claim: pre-freeze QSIZE 0, QREAD 0, STATUS exactly one per iteration masked to bit5; post-freeze QREAD and STATUS allowed, QSIZE still 0 |

Non-blocking, also closed:

- **Latin square is not needed.** With one variant there is no treatment for
  position to confound with. Boot blocking, sequence preservation, boot-first
  analysis and no early pooling replace it; 3x10 fixed in advance, and boots that
  disagree produce S6 rather than more boots.
- **Five further forbidden claims** (F7–F11): S5-only is not an unperturbed
  baseline; unobserved excursions are not absent variability; poll count is not
  visibility latency; the convergence tail is not primary ordering evidence;
  qualitative similarity is not a common mechanism. Eleven in total.
- **Poll count** decided on the linked image as Case A (adopt only if zero extra
  per-iteration instructions, spills, memory or MMIO) or Case B (drop the field).

One correction the independent pass made to my own framing, worth recording
because it is the kind of drift that starts small: the equivalence gate exists to
let V15 stand *beside* V14's Q, and if it fails the answer is to lower V15's
claims, never to loosen the gate. I had written the two options as a choice; they
are a preference and a fallback.
