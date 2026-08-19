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

That is the opposite of what a naive read-order bias predicts. A sampling
advantage for whichever register is polled first would have produced Q_FIRST in
QS and S5_FIRST in SQ; both are zero.

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
