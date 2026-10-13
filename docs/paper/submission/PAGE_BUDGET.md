# Page budget — SE1 baseline

**Constraint (CFP):** technical content ≤ **20 pages** in `acmsmall`, with
tables and figures counted. References unlimited. Appendix unconstrained.

**Built:** `build/paper-review.pdf`, 21 pages total, page size 486 × 720 pt
(6.75 × 10 in), which is `acmsmall`.

```
technical content (pp. 1-18)      18 / 20     UNDER by 2 pages
references        (p.  19)         1          unlimited
appendices A + B  (pp. 20-21)      2          unconstrained
                                  ----
total                             21
```

**Verdict: within the limit, with two pages of headroom.** No shortening is
required, and none was performed — SE1 is an accurate-format baseline.

## Section-by-section occupancy

| section | pages | span |
| --- | ---: | --- |
| 1 Introduction | 1 | p. 1 |
| 2 Background (incl. 2.1 Related work) | 2 | pp. 2–3 |
| 3 Methodology (3.1–3.6) | 3 | pp. 4–6 |
| 4 Cross-generation characterization (RQ1, RQ2) | 1 | p. 7 |
| 5 Validity of the structural metrics | 1 | p. 8 |
| 6 Corstone-320 hardware validation (RQ3) | 1 | p. 9 |
| **7 Operator-level mechanism study (RQ4)** | **5** | pp. 10–14 |
| 8 Discussion | 1 | p. 15 |
| 9 Limitations | 2 | pp. 16–17 |
| 10 Conclusion | 1 | p. 18 |
| — References | 1 | p. 19 |
| — Appendix A + B | 2 | pp. 20–21 |

Section 7 is the largest at five pages, which matches its role: it carries the
mechanism study, two of the five figures, and the cross-memory table. Sections 4,
5 and 6 are one page each, so the results/validation balance established in the
scientific review survives typesetting.

Figures occupy roughly two pages in aggregate across pp. 7, 10, 11, 12 and 13.

## Notes

- The margin is genuine but not large. Any later content addition — for example
  the AI-disclosure paragraph required in Methods, ~180 words — consumes part of
  the two-page headroom. Estimated cost of that paragraph: well under half a
  page.
- **No page-count optimization was performed**, as the phase requires: nothing
  was deleted, no font or margin was altered, no spacing squeezed, and no
  load-bearing evidence was moved to the appendix. The appendix contains only
  what the scientific review already placed there.
- The unlimited references and appendix allowance was **not** used as a reason
  to move main-body material out. Appendix classification is in `BUILD_REPORT.md`.

## Effect of the typesetting fixes

Two typesetting-only changes were applied during SE1 and both were re-verified
against the invariance gate (0 drift):

| change | reason | effect |
| --- | --- | --- |
| wide table columns switched to wrapping `tabularx` `X` columns | one table overflowed the text block by **474 pt** | overfull boxes 7 → 6; no content change |
| `hyphenat[htt]` + `\emergencystretch=2em` | long machine identifiers such as `software_visible_completion_observation_cycles` cannot break and overflowed | overfull boxes 6 → **1** (worst 3.4 pt); total pages 20 → 21 |

The extra page landed in the **appendix**, which the CFP leaves unconstrained.
**Technical content stayed at 18 pages throughout**, so the limit position is
unchanged.
