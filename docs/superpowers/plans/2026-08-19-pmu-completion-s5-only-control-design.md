# PMU_COMPLETION_S5_ONLY_CONTROL — short-term goal and design

**Status: design only, revised after a self-attack and an independent attack
review** (see
`2026-08-19-pmu-completion-s5-only-control-attack.md`; A1, A2, A4, A6 and A7 are
closed in the text below, A3 and A5 as wording). No code exists for this yet, and none should until this
document has been attacked independently and anchored. In particular nothing in
V14 is to be modified: V13 and V14 are frozen historical evidence, and this is a
new independent control beside them, not an extension of either.

| | |
| --- | --- |
| Experiment name | `PMU_COMPLETION_S5_ONLY_CONTROL` |
| Schema | 15 |
| Internal version | V15 |
| Branch | `pmu-completion-s5-only-control` |
| Build ID family | PI15 |
| Branched from | `153f368` — V14 board evidence anchor |

The name carries the purpose and the version carries the provenance. Beside its
neighbours it reads as a table rather than as a sequence:

| | Single observable | What it settled |
| --- | --- | --- |
| V13 | `STATUS` bit1 `irq_raised` only | polling variability explained by poll count |
| V14 | `QREAD == qsize_expected`, plus Q/QS/SQ dual-read | inter-read sampling effect characterised |
| V15 | `STATUS` bit5 `cmd_end_reached` only | the control the dual-read interpretation is missing |

## The question

One question, fixed, and deliberately not a family of them:

> When `STATUS.cmd_end_reached` (bit 5) is polled **on its own**, what is the
> run-to-run structure of the completion observation, and what constraint does
> that place on interpreting the inter-read sampling effect V14 observed in its
> dual-read variants?

## Why this is the next thing worth doing

V14 finished with a named confound rather than a hidden one. Its dual-read loop
performs two MMIO accesses per iteration, so the pattern it found — every one of
the 17 single-observable splits landing on the *second* read, and none on the
first — is compatible with two different accounts that the experiment cannot
separate:

- the two observables become software-visible close enough together that the
  read following the transition is the one that catches it, or
- the QREAD access in the loop perturbs the polling environment, and the
  sampling phase between the two reads does the rest

A fresh single-register control on bit5 gives the third leg of the table above.
It does not resolve the ordering by itself — nothing in this design does — but it
tells us whether the completion observation has the same shape when only one
register is being polled.

## Scope: the smallest change that answers it

V14's Q variant, with the primary observable replaced. Nothing else moves.

The primary loop becomes:

```
    read STATUS
    test bit5 (0x20)
      false -> loop
      true  -> first-observation freeze
```

`irq_raised` (bit1) is kept from **the same raw STATUS word** as supporting
evidence. No additional STATUS read is permitted — a second read would rebuild
the very perturbation this control exists to avoid.

Everything below is inherited from V14 unchanged, because the point of a control
is that only the thing under study differs:

- the pre-submit stopped-state gate, and QSIZE read exactly once while stopped
- stale STATUS rejection
- PMU setup and ordering
- timestamp placement
- the bounded primary loop
- first-observation freeze
- the common convergence tail
- fault handling and priority
- cleanup ordering
- the golden contract
- manifest and provenance binding
- the collector's fail-closed behaviour
- board pre- and post-flight

**Inherited in shape, not in code.** Schema 15 with its own build ID means a new
parser, a new classifier, a new manifest binding and a new collector
instantiation. Their *designs* come across unchanged; their *modules* are new
code and must be requalified to the standard V14's were held to -- claim matrix,
targeted negatives that fail at their own rule, real-artifact application, and
silent-gate telemetry. The implementation plan must budget for a host chain, not
only a firmware change.

### QSIZE and the convergence tail stay

Being S5-only in the *primary* loop does not mean dropping the QREAD-based tail.
Post-observation safety is not what is under study, and changing it would move a
second thing at the same time. So:

```
pre-submit (stopped):   QSIZE read exactly once -> qsize_expected
primary:                STATUS only, bit5
                        first observation freeze
convergence tail:       QREAD -> STATUS, then
                        QREAD == QSIZE && cmd_end && irq && stopped
```

The observable changes; the cleanup contract does not.

**What "S5-only" means, precisely.** The tail reads QREAD, so this control is
S5-only *up to the first-observation freeze* and not after it. Since the confound
under study is QREAD MMIO traffic perturbing the polling environment, that
boundary is the whole point: the traffic is removed from the measured window, and
what remains happens after the measurement it could have perturbed.

## Primary outputs

Kept deliberately short:

- first-observed cycle distribution
- floor and excursion reproducibility across independent boots
- poll-iteration structure
- `status_at_success`
- `irq_raised` from the same raw STATUS word as the deciding bit5 test

### Poll count, if and only if it is free

V13 established `cycles = constant + per_poll × iterations`. The same
characterisation here would sharpen the interpretation considerably, so the
design audit should ask whether the poll count can be taken from an existing
induction counter with no perturbation.

If it cannot be taken without changing the loop body, it is not taken. A control
whose loop differs from the thing it is controlling for is not a control.

## Pre-registered interpretation

Fixed here, before any firmware exists, because a control whose interpretation is
chosen after the data arrives is not a control. This project froze V14's analyzer
before its data existed for the same reason.

Six outcomes, because the three-row version hid the distinctions that a post-hoc
reading would have exploited -- most of all the difference between "no excursions"
and "different excursions".

**S1 — floor and excursions both reproduce**, per boot, with excursions above the
floor present in each.
Supports: a discrete floor-plus-excursion structure exists in S5-only observation
too. Does **not** support: that Q and S5 are perturbed by the same cause, that
their floors mean the same hardware timing, or that intrinsic ordering is settled.

**S2 — floor reproduces, no excursion observed.**
Supports: a reproducible lower observation mode exists in S5-only. Weakens: the
reading that Q and S5 share one variability structure. Forbidden: "S5 is stable"
or "STATUS visibility has no excursions" — thirty samples not showing something is
not an absence proof.

**S3 — floor reproduces, excursion structure qualitatively different** (different
per-boot excursion frequency, different modality, boot-dependent floor-like
states).
Supports: the within-variant observation dynamics of Q and S5 differ. Still not
evidence about intrinsic ordering.

**S4 — no reproducible floor** (boot minima disagree, distribution continuously
spread).
Supports: the hard-floor structure V14 saw in Q does not reproduce under
S5-only. Does **not** mean "therefore Q is faster".

**S5 — bit5 never observed within the bounded loop.**
This is a diagnostic failure state, not a characterization result: sample
invalid, boot aborted, fresh boot required, excluded from the distribution
dataset.

**S6 — boot-dependent, mixed behaviour** (one boot floor-plus-excursion, another
floor only, another no reproducible floor).
Verdict: `BOOT-DEPENDENT / UNRESOLVED`. Registered as its own outcome precisely so
that "two of three boots showed it, so it reproduces" cannot be invented
afterwards. No pooling across boots to manufacture a single answer.

Any reading not in this list is post-hoc and is to be labelled as such.

## Three gates this control needs that V14 did not

### 1. Q-to-S5 structural equivalence

The value of the control rests on "the same experiment with one observable
replaced", and V14 did not leave the analogous claim to trust:
`RULE_READ_ORDER_EQUIVALENCE` proves QS and SQ differ in read order and nothing
else. V15 needs `verify_single_register_equivalence(Q, S5)`.

**Not raw instruction equality.** Register allocation and branch encoding are
free to differ. The gate's authority is a normalized CFG plus semantic
instruction roles plus the side-effect sequence:

- entry and exit CFG, loop header, success edge, timeout and back edge
- timestamp placement
- induction-counter semantics
- first-observation freeze position
- helper and call topology
- per-iteration instruction class and count
- per-iteration memory side effects
- tail entry point

The only permitted difference is the observable substitution and the dataflow
that depends on it:

```
Q :  load QREAD    ; compare qread == qsize_expected
S5:  load STATUS   ; test status & 0x20
```

Per iteration, quantitatively:

| | Q primary | S5 primary |
| --- | --- | --- |
| QREAD reads | exactly 1 | **0** |
| STATUS reads | 0 | exactly 1 |
| QSIZE reads | 0 | 0 |
| extra load/store, MMIO, timestamp, call | 0 | 0 |
| spill/reload delta, barrier delta | — | 0 |

**If this gate fails, it is not relaxed.** V15's claims drop to S5-only
within-variant characterization and the Q-to-S5 structural comparison is
abandoned. Weakening a gate to make an image pass is the one move this project
has spent its entire history refusing.

**Negative fixtures, each failing at the equivalence detector itself** — not at a
neighbouring rule that happens to catch it first:

| Mutation | Required |
| --- | --- |
| an extra per-iteration instruction in S5 | FAIL |
| an extra SRAM store in S5 | FAIL |
| a QREAD read added to the S5 primary loop | FAIL |
| S5 timeout branch topology changed | FAIL |
| S5 first-freeze position moved | FAIL |
| only the observable load/test exchanged | PASS |

### 2. The S5-only boundary, as an executable claim

Writing "S5-only means up to the freeze" in prose is not enough; it is one of the
load-bearing claims of the whole control, so it is gated on the final ELF and
split by phase:

```
PRE-FREEZE PRIMARY PATH        POST-FREEZE CONVERGENCE TAIL
  QSIZE  reads   0               QREAD   allowed
  QREAD  reads   0               STATUS  allowed
  STATUS reads   exactly 1/iter  QSIZE   still 0
  STATUS mask    bit5 / 0x20
```

The pre-freeze half is the mirror of V14's `RULE_PRIMARY_NO_QSIZE` and does not
exist yet. Asserted rather than gated is the shape of all eleven silent gates
this project has found.

### 3. Both belong to the matrix

On the same terms as V14's thirty-six: a rule identifier, a targeted negative
that fails at that rule, application to the real images, and inclusion in the
silent-gate telemetry.

## Campaign shape

V14's balance came from three variants in a Latin square. V15 has one variant, so
there is no treatment for position to confound with, and no square is needed. The
protection comes from boot blocking and sequence preservation instead:

- **3 independent boots x 10 consecutive runs**, fixed before the campaign starts
- `run_sequence` preserved; no cell completed by topping up a failed attempt
- **boot-first analysis, pooling last**: per-boot minimum, per-boot median,
  per-boot excursion count, within-boot dispersion, between-boot dispersion, and
  the trend across run index 1..N
- the floor must reproduce as the minimum of **every boot separately**, the rule
  V14's analyzer already applies

The sample size is fixed at 3x10 rather than extended adaptively. If the boots
disagree, the result is outcome **S6** — `BOOT-DEPENDENT / UNRESOLVED` — and a
follow-up is designed separately. Deciding to run more boots after seeing the
data is how a preregistered outcome table gets quietly unregistered.

## Deciding whether the poll count is free

Decided on the linked image after the S5 loop exists, not by judgement at
authoring time:

- **Case A** — publishing the existing induction counter as a live-out leaves the
  primary loop semantically and structurally equivalent: zero extra per-iteration
  instructions, zero spills, zero loads or stores, zero MMIO. Adopt it.
- **Case B** — publication changes the loop shape at all, by a spill, a reload, an
  extra move or any bookkeeping. Drop the field.

V15's purpose is a fresh S5 control, not a reproduction of V13's poll-count
study. A control whose loop differs from the thing it controls for is not a
control, and no amount of extra characterization is worth that.

## Forbidden claims

These are contract-level prohibitions, not style notes. Each one is a sentence
somebody could write from this data that the data does not support.

1. **No absolute cycle subtraction between variants.** "Q floor 732, S5 floor
   790, therefore STATUS is 58 cycles later" is forbidden. The two variants poll
   different MMIO registers, so the loop's own bus and interconnect interaction
   may differ. What is comparable is *within-variant* structure: that a floor and
   excursions exist in each.
2. **The S5 first observation is not an internal NPU completion timestamp.** What
   the CPU read is the end of a chain — internal transition, register visibility,
   MMIO sampling, CPU observation. Field names stay descriptive:
   `submit_to_s5_observed_cycles`, `cmd_end_reached_observed`. Forbidden:
   `internal_completion_cycles`, `npu_completion_timestamp`, `T_npu`,
   `execution_latency`.
3. **Q-only and S5-only together do not establish intrinsic ordering.** They are
   different firmware variants. The only direct evidence about ordering remains
   V14's QS/SQ, which read both observables in one run; V15 evaluates whether
   that evidence was distorted by MMIO perturbation, and decides nothing on its
   own.
4. **V15 does not "prove" or "disprove" V14's second-read pattern.** It can
   strengthen or weaken the interpretation. "V15 is stable, therefore QREAD is
   first" is not a valid inference and is not to be written.
5. **SAME_ITERATION is not hardware simultaneity.** Closed in V14 and
   cross-referenced here: it means this loop cannot order the two, not that they
   change together.
6. **No promotion to production or benchmark.** Production END_ONLY stays FROZEN
   and MLEK stays BLOCKED however clean the result is. This is a completion
   observability control, not a measurement candidate.
7. **S5-only is not an "unperturbed baseline".** STATUS polling is itself repeated
   MMIO traffic. The accurate name is *single-register STATUS(bit5) polling
   control*; "natural" or "unperturbed" baseline is forbidden.
8. **Unobserved excursions are not absent variability.** "No excursion in thirty
   samples, therefore STATUS visibility is deterministic" is forbidden. What may
   be written is that no excursion was observed in this campaign.
9. **Poll count is not visibility latency.** If the count survives the Case A/B
   decision, it remains a software polling observation count. "200 polls
   therefore 200xX of hardware latency" is forbidden.
10. **The convergence tail is not primary ordering evidence.** The tail reads
    QREAD after the freeze; what it sees is cleanup safety evidence and may not
    be used to argue about Q-versus-S5 ordering.
11. **Qualitative similarity is not a common mechanism.** "Q shows floor and
    excursions, S5 shows floor and excursions, therefore both come from the same
    NPU execution variability" is forbidden. What may be written is that both
    single-register observations showed a similar qualitative structure.

## Sequence

The manager's order, and nothing runs ahead of it:

```
V14 FROZEN / BOARD EVIDENCE COMPLETE   (done: 153f368)
        |
V15 design                             (this document)
        |
independent attack review
        |
design anchor
        |
implementation plan
        |
plan review
        |
implementation / qualification
```

## Inherited state at the time of writing

| | |
| --- | --- |
| V14 board evidence | `153f368`, tag `pmu-completion-visibility-v14-board-evidence` |
| V14 pre-board anchor | `619e957`, tag `pmu-completion-visibility-v14-preboard` |
| V14 campaign protocol | `7c3c124` |
| Production END_ONLY | FROZEN |
| MLEK | BLOCKED |
| `origin/main` | HOLD |
| Known inherited limitation | V13 standalone suite 306 PASS / 4 FAIL, missing historical `/tmp` probe artifacts, not introduced by V14 |
