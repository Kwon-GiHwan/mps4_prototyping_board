# Tier C step 4 — amendment 1 (drafting error in the fc reading)

Recorded 2026-10-07, **after** boots 21–23. The frozen contract is not edited.

Row 1 of the preregistered readings says "4a: 84 or 90 NONZERO, **4b**: 85 and 91 ZERO → consistent with fc = FWD".
The intended condition was **4a**: 85 and 91 ZERO, so that the fc counters move while the tc counters stay at zero on
the same workload. Under the row as written, the result (4b's 85/91 are NONZERO) does not meet the condition, and
`VERDICT_4.md` reports it as NOT MET.

Because this amendment was written after the data existed, the corrected condition holds on the data
(4a: 84/90 NONZERO, 85/91 ZERO) but has **no preregistered standing**. It is reported only as
`POST_HOC_DESCRIPTIVE`. Rows 2 (tc) and 4c are unaffected and were met as written.
