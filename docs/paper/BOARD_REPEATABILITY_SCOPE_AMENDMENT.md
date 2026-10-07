# Amendment — board repeatability reporting is limited to what was frozen

Recorded **before Stage B3**, in answer to a direct question: was the
board-repeatability descriptive contract frozen before B2 results were seen?

**It was not.** Only the canonical value was.

## What the record actually shows

Frozen before any formal board data — protocol amendment `127632a` (2026-08-25
16:23) and pre-campaign anchor `56ffc1494d7f22a5`:

```
canonical_board_cost = median(B1, B2, B3)
```

Never defined in any artifact:

```
relative_spread = (max - min) / median
min / max as reported metrics
repeatability pass/fail threshold = NONE   (as an explicit statement)
```

The only repeatability text carried in `BOARD_VALIDATION_PLAN.md` was
*"Dispersion within and across boots"* — a placeholder naming a topic, not a
metric definition. It does not preregister a statistic.

Stage B2 evidence was committed at `d8d9f32` (2026-08-26 13:56), so the B1 and B2
values are now known.

## Consequence

Introducing `relative_spread`, a coefficient of variation, or a percentage
deviation **now** would be selecting a variability statistic after seeing the
data it would be computed on. That is precisely the failure mode this project has
guarded against everywhere else, and the fact that it would be easy to justify
retroactively is what makes it inadmissible.

Board repeatability reporting is therefore limited to:

```
pre-existing, frozen before formal data:
    canonical_board_cost = median(B1, B2, B3)

permitted after B3:
    report the raw triplet B1, B2, B3 per workload
    report the canonical median

not permitted:
    any newly introduced repeatability threshold
    any variability metric chosen after B1/B2 were observed
    presenting such a metric as a preregistered RQ3 result
```

Raw values are reportable because they are the observations themselves, not a
statistic selected after the fact.

## Not a loss of information

The triplets are preserved in full. If a variability statistic is wanted later it
can be defined and computed — but it must be labelled as **post-hoc descriptive**,
never as a preregistered RQ3 metric, and it cannot carry a pass/fail threshold
invented after the data existed.

## Stage B3 is unaffected

This bounds *reporting*, not acquisition. B3 uses the same validity gates as
B1/B2, and numeric inequality between boots remains a non-failure.
