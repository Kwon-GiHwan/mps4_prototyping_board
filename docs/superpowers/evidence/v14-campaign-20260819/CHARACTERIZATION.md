# V14: what 90 samples showed

Nine cells, nine independent boots, ten runs each. Every sample valid, every
re-read equal to its first read, no contract violation at any point.

## The analyzer's verdict

```
conclusion           UNRESOLVED
dual_order_pattern   MIXED_ACROSS_CELLS
qs_category          None
sq_category          None
```

`UNRESOLVED` because the analyzer requires one stable category per variant and
no cell produced one. That is the analyzer working, not failing: it was written
before the data existed and it was not touched after seeing it.

## What the samples actually contain

| Variant | Reads first | SAME_ITERATION | second-read observed alone | first-read observed alone |
| --- | --- | --- | --- | --- |
| QS | QREAD | 23 | S5_FIRST **7** | Q_FIRST **0** |
| SQ | STATUS | 20 | Q_FIRST **10** | S5_FIRST **0** |

Sixty dual-variant samples across six boots, and the register each variant reads
**first** is never the one observed alone. Not once, in either direction.

That is the opposite of what a *first-read advantage* predicts. If polling a
register first gave it a head start in being observed, QS would show Q_FIRST and
SQ would show S5_FIRST; both are zero.

It is worth being precise about which hypothesis this kills, because the loose
version of the sentence says the opposite of what the data shows. Read order is
not irrelevant here -- it is doing most of the work. What fails is the specific
claim that the first-read register wins:

```
First-read advantage hypothesis            FALSIFIED
Inter-read sampling / order effect         CONFIRMED, and dominant in every
                                           split that is not SAME_ITERATION
Intrinsic QREAD vs STATUS(bit5) ordering   UNRESOLVED
```

Stated once, carefully: **dual-read observations do not establish an intrinsic
QREAD-vs-STATUS visibility ordering. All single-observable splits occurred on the
second MMIO read, consistent with the state transition landing inside the
inter-read sampling window.** Read order is why the intrinsic ordering is hard to
identify, not something the data lets us set aside.

The structure fits a different account, and this is stated as a hypothesis the
data is compatible with rather than as a finding:

```
QS:  QREAD  read -> not yet set
     [ completion becomes visible in this window ]
     STATUS read -> set        => S5_FIRST

SQ:  STATUS read -> not yet set
     [ completion becomes visible in this window ]
     QREAD  read -> set        => Q_FIRST
```

If the two observables become software-visible within a window comparable to the
gap between two MMIO reads, then whichever read happens *after* the transition is
the one that catches it, and that is always the second read. The dominant
SAME_ITERATION count is the same statement: most of the time both are already
set by the time the tuple is taken.

What this does **not** establish is which observable becomes visible first. The
QS loop contains a QREAD access of its own, so the loop cannot separate its own
perturbation from the thing it measures. The design has always said that
separation needs a fresh bit5-only S5 control, and nothing here changes that.

## No position or round effect

| Axis | SAME_ITERATION | S5_FIRST | Q_FIRST |
| --- | --- | --- | --- |
| position 1 | 13 | 3 | 4 |
| position 2 | 15 | 2 | 3 |
| position 3 | 15 | 2 | 3 |
| round 1 | 15 | 2 | 3 |
| round 2 | 14 | 3 | 3 |
| round 3 | 14 | 2 | 4 |

The balanced Latin square did its job: the pattern tracks the variant, not when
or where the cell ran.

## Q: the floor reproduces

| Round | Boot | Observation cycles |
| --- | --- | --- |
| 1 | `Q-1787115071` | 732, 743, 743, 3031, 3941, 4019, 4045, 4955, 5683, 5709 |
| 2 | `Q-1787115558` | 732, 743, 743, 743, 743, 743, 1965, 4669, 5709, 5787 |
| 3 | `Q-1787115723` | 732, 743, 743, 743, 743, 2095, 2303, 2875, 4487, 5839 |

The same floor -- 732 -- is the minimum of every boot separately, and every boot
carries values above it. The analyzer reports floor REPRODUCED and excursion
REPRODUCED, and no qualitative disagreement between Q and either dual variant.

## Board postflight

The original image was restored byte-exact from the pre-campaign backup
(`ffa3e5bd…`, `45e943c5…`, `81d37a21…` on the card after the write), and the
board was closed in the state the procedure ends in:

```
DDR self-test        PASSED
CPUWAIT              cleared
PING                 3/3, every one from IDLE
protocol counters    all seven zero
/dev/sdb             absent
mounts               0
UART holders         0 (root-inclusive)
```

## Final status

```
V14 Q/QS/SQ campaign                     COMPLETE -- 90/90 VALID

QREAD-only floor/excursion               REPRODUCED
STATUS-polling-only cause                FALSIFIED AS NECESSARY CAUSE
First-read advantage                     FALSIFIED
Second-read capture pattern              OBSERVED CONSISTENTLY, 17/17
                                         non-SAME dual samples
Intrinsic QREAD vs STATUS(bit5) ordering UNRESOLVED
Software-visible ordering characterization  COMPLETE

Internal NPU completion timestamp        NOT AVAILABLE
Production END_ONLY                      FROZEN
MLEK                                     BLOCKED
```

The 43 of 60 SAME_ITERATION samples carry their own caveat, and it is the same
one as always: they do not mean the two observables change together in hardware.
They mean this polling loop cannot order them. A gap smaller than the interval
between two MMIO reads is invisible to an instrument whose resolution *is* that
interval.

## Verdict provenance

The frozen analyzer's verdict and the descriptive characterization are kept
apart on purpose:

| | |
| --- | --- |
| Frozen analyzer verdict | `UNRESOLVED`, `MIXED_ACROSS_CELLS` |
| Post-campaign description | 43/60 SAME, 17/60 second-read-only, 0/60 first-read-only |

The analyzer was written before the data existed and was not touched after it
did. Reading its rules in light of the result and adjusting them would have
produced a cleaner-looking verdict and a worthless one.

## Execution provenance

| Item | Commit |
| --- | --- |
| campaign runner, formal 90-sample protocol | `7c3c124` |
| aborted pre-prime runner (0 formal samples) | `3e14a06` |
| R1 / R2 / R3 evidence | `7c3c124`, `b14c730`, `74af272` |
| pre-board qualification anchor | `619e957` |

## What comes next, and what must not

The remaining confound is named rather than papered over: the dual loop performs
two MMIO accesses per iteration, so the second-read capture pattern could come
from register visibility ordering *or* from the QREAD access perturbing the
polling environment plus the sampling phase between the two reads. Those are not
separated by anything in this campaign.

A fresh STATUS-bit5-only control, run under this same discipline, would give a
third single-register reference beside V13's bit1 and V14's Q. That is a separate
short-term goal with its own boundary, not an addition to V14 -- adding it here
would move the boundary of the experiment that just finished.

And it inherits one prohibition unchanged: no absolute cycle comparison between
variants. Each polls a different MMIO register, so bus and interconnect
behaviour may differ, and a subtraction between their floors would be a number
with no meaning.
