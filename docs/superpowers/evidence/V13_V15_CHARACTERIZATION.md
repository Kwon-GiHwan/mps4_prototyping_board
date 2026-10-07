# Completion observability, V13 → V15

Three board campaigns on the same MPS4 / Ethos-U85 target, each closing a
question the previous one opened.

## V13 — poll count explains the variation

STATUS bit1 polling. The observed timing variation was accounted for exactly by
the poll count: the number of times the CPU looked, not something the device did
between looks.

## V14 — dual-read ordering is a sampling effect

QREAD against STATUS bit5, both read in one run, order swapped between variants.

```
first-read advantage                 FALSIFIED
inter-read sampling / order effect   CONFIRMED
intrinsic ordering                   UNRESOLVED
```

The apparent advantage of whichever register was read first is a property of
*when the software sampled*, not of when the two registers became visible. What
V14 could not settle is whether either register genuinely becomes visible before
the other.

90/90 valid samples across nine independent boots.

## V15 — the structure does not need QREAD

A matched single-register control reading STATUS bit5 only, qualified as
`Q_S5_EQUIVALENT` against the frozen V14 Q reference: same loop shape, six
instructions per iteration, same role sequence.

```
reproducible floor + excursions            CONFIRMED (754 cycles, 3/3 boots)
structure requires QREAD                   FALSIFIED AS A NECESSARY CONDITION
structure requires dual-read polling       FALSIFIED AS A NECESSARY CONDITION
common mechanism with Q                    NOT ESTABLISHED
```

30/30 valid samples across three independent boots.

## Taken together

> Software-visible completion timing exhibits a reproducible floor with
> excursions across multiple observation paths, while dual-read ordering is
> dominated by software sampling effects; these experiments characterize the
> observable software boundary but do not expose an internal NPU completion
> timestamp or a definitive intrinsic ordering between QREAD and STATUS
> visibility.

## What remains out of reach, and why

Every measurement in all three campaigns is a **CPU observation**. The chain is:
internal transition → register visibility → MMIO sampling → CPU observation, and
only the last link is measured. No internal NPU completion timestamp is exposed
by this device, so no campaign of this design can produce one.

That is a property of the target, not a shortfall of the method — which is why
the vocabulary guards refuse `latency`, `T_npu`, `internal completion` and
`execution time` throughout: they would describe the CPU's observation as the
device's own event.

## Further board work

Not recommended. The completion-observability question is characterized as far
as this observation boundary allows; more runs of this design would add samples
without adding reach.
