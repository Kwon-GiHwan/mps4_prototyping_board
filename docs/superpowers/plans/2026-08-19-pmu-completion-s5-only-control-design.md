# PMU_COMPLETION_S5_ONLY_CONTROL — short-term goal and design

**Status: design only.** No code exists for this yet, and none should until this
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
