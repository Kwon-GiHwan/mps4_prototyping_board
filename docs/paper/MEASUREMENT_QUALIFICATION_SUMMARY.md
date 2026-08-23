# Measurement qualification summary — V13 to V15

Paper-facing. This states what the qualification campaigns established about the
measurement boundary. Implementation and debugging history is appendix material
and is not reproduced here.

## Why this section exists

The main characterization reports timing. Before any of it can be interpreted,
one question has to be settled: **what exactly does a reported cycle count
measure?** Three board campaigns were run to answer that, and the answer bounds
every claim in the paper.

## What each campaign established

### V13 — STATUS-bit1 polling variability

Software observation variability was characterized, and for that experiment the
observed timing variation was accounted for by poll-count dependence: variation
tracked how many times the CPU looked, not something the device did between
looks.

### V14 — QREAD vs STATUS(bit5), dual-read

Both registers read in one run, order swapped between variants, 90/90 valid
samples across nine independent boots.

| | |
| --- | --- |
| first-read advantage | **FALSIFIED** |
| inter-read sampling / order effect | **CONFIRMED** |
| intrinsic QREAD-vs-STATUS ordering | **UNRESOLVED** |

The apparent advantage of whichever register was read first is a property of
when the software sampled, not of when the registers became visible.

### V15 — STATUS(bit5)-only matched single-register control

A matched control qualified as `Q_S5_EQUIVALENT` against the frozen V14 Q
reference: same loop shape, six instructions per iteration, same role sequence.
30/30 valid samples across three independent boots.

| | |
| --- | --- |
| preregistered outcome | **S1** |
| reproducible floor + excursions | **CONFIRMED** |
| QREAD necessary for the structure | **FALSIFIED AS A NECESSARY CONDITION** |
| dual-register observation necessary | **FALSIFIED AS A NECESSARY CONDITION** |
| common underlying mechanism | **NOT ESTABLISHED** |

"Falsified as a necessary condition" is precise, not hedged. It does not say
QREAD polling fails to produce excursions; it says the explanation *requiring*
QREAD no longer stands, because the same structure appeared in a path that never
reads QREAD.

## The measurement boundary

```
internal NPU transition
      ↓
register visibility
      ↓
MMIO sampling
      ↓
CPU observation          ← only this is measured
```

| measured | not measured |
| --- | --- |
| software-visible completion observation | internal NPU completion timestamp |
| | pure NPU execution latency |
| | T_npu |

This device exposes no internal completion timestamp, so no campaign of this
design can produce one. That is a property of the target, not a limitation of
the method.

## The comparison that is not permitted

```
V14 Q floor    732 cycles
V15 S5 floor   754 cycles
```

These may not be subtracted or divided. "STATUS becomes visible 22 cycles later
than QREAD" is **not** a result of this work, and the analyzer refuses both the
arithmetic (`RULE_CROSS_VARIANT_ABSOLUTE_COMPARISON`) and the sentence.

`Q_S5_EQUIVALENT` establishes that the two control structures are matched. It
does not establish that cycle counts taken against two different MMIO
observables lie on one physical latency axis.

What the campaigns support is qualitative structural similarity across matched
controls, and nothing past it.

## Statement for the main text

> Both QREAD-only and STATUS.cmd_end_reached-only matched controls exhibit a
> boot-reproducible lower observation mode with excursions above that floor.
> Therefore, the observed floor-plus-excursion structure is not specific to
> QREAD polling and does not require dual-register observation. However, the
> experiments do not establish a common underlying mechanism, and their absolute
> cycle values do not determine intrinsic QREAD-versus-STATUS visibility
> ordering.

Short form:

> The floor-plus-excursion structure reproduces under both single-register
> completion observables, while the underlying mechanism and intrinsic
> QREAD-versus-STATUS ordering remain unresolved.

## Appendix evidence

`v15-frozen` and the tags beneath it; `V13_V15_CHARACTERIZATION.md`;
`v15-campaign-20260823/CLOSING_STATEMENT.md`.
