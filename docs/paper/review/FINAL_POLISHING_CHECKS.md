# Final polishing pass — check results

Manuscript under test: `paper-manuscript-submission-candidate`.
All suites fail-closed; any FAIL blocks the freeze.

## Suite totals

| suite | checks | result |
| --- | ---: | --- |
| `phase1_consistency_check.py` — claim discipline incl. causal isolation | 16 | **PASS** |
| `phase1_5_validation.py` — structure, thesis, references, platform roles | 25 | **PASS** |
| `phase2_validation.py` — numeric integrity, prohibited claims, reader flow | 98 | **PASS** |
| `polish_validation.py` — checks A–F, new in this pass | 42 | **PASS** |
| `manuscript_text_fixtures.py` — shared normalization | 14 | **PASS** |
| `phase1_5_checker_fixtures.py` — F4 causal-language regression | 14 | **PASS** |
| **total** | **209** | **209 / 209** |

```
rule failures              0
scientific contradictions  0
numerical discrepancies    0
```

## The six mandated final checks

**A — figures first appear in order 1,2,3,4,5.** Caption sequence is
`['1','2','3','4','5']`; embedded filenames are `fig1…fig5` in that order; each
figure is embedded exactly once; and each caption number is asserted to match
the number in the filename it follows, so a future edit cannot desynchronise a
caption from its image.

**B — every Figure reference resolves.** Referenced set ⊆ {1..5}; no `Figure 6-9`
anywhere; exactly five SVG files on disk and each is referenced by the
manuscript; and each of the four superseded filenames
(`fig5_platform_sensitivity`, `fig4_board_relative_cost`, `fig2_u85_group_delta`,
`fig3_u85_memory_robustness`) is asserted absent from both the text and the
directory, so the renumbering left no stale artifact.

**C — no "whole-model +19,060" claim remains.** Checked in three places
independently: the manuscript prose, the rendered text of
`fig4_u85_group_delta.svg`, and `FIGURE_PROVENANCE.json`. All clear.

**D — the three delta semantics are distinguished.** The manuscript states the
whole-model observed delta as +19,000, the reconstructed profiled-group delta as
+19,060, and the residual as 60; the residual carries the frozen scoped wording
(*deterministic profiling-boundary / interrupt-service*) and not a stronger
causal model; the arithmetic 19,060 − 19,000 = 60 is asserted; the figure shows
all three quantities and states that the two boundaries are not identical; and
§9.5's original residual explanation is verified still present.

**E — 468× used everywhere in current manuscript authority.** The manuscript
states 468× with its basis configuration named
(`SSE-320 / ethos-u85-256 / Dedicated_Sram`) and the supporting per-workload
table present. The string `467` does not occur anywhere in the manuscript. The
historical planning value survives only in frozen historical documents.

**F — MIN-1 and MIN-2 closed.** Methodology is §3.1–3.6 with no §3.7; provenance
lives in Appendix B with a pointer left in Methodology; all four named guards
(identity chain, `SOURCE_DATE_EPOCH`, exact-equality repetitions, mutation
tests) verified still present; methodology share is **18.0 %** of the body (1,580 words), down from
19.5 % (1,685 words). Appendix A carries the new title, the narrow title is gone, and
Appendix A remains reachable from §6.

## Figure regeneration verification

Only the four renumbered figures and the MOD-2 figure were regenerated — in
practice all five, since the generator emits them together from one frozen read.

| property | result |
| --- | --- |
| same source frozen tags | yes — unchanged in every `prov()` record |
| same source rows | yes — no filter, sort key or row selection was touched |
| same numerical values | yes — only labels and annotations changed |
| deterministic digest | yes — verified byte-identical across repeated generation, twice |
| geometry | no element or text run exceeds its canvas, all five figures |
| visual | Figure 4 rendered and inspected; reconciliation block reads correctly |

No new normalization, aggregation, smoothing, threshold, or row selection was
introduced.

## Defects found in this pass, and recorded

**A fabricated figure in my own record.** The first draft of `FINAL_POLISHING.md`
and of this file stated the post-move methodology size as "1,391 words / 16.2 %".
Neither number was ever produced by a check: `polish_validation.py` prints that
detail only on failure, and the check passed, so the value was written without
being observed. The verified figures are **1,580 words / 18.0 %**, down from
1,685 / 19.5 %. Both documents were corrected before the readiness gate, and
check F now asserts the measured share against a pinned bound so the number
cannot drift unobserved again. The manuscript itself contains no such figure and
was unaffected.

**A validator defect, not a manuscript defect.** One check failed on first run: the caption-to-filename matcher used `[a-z_]+` for the filename stem,
which excludes digits, so the two `u85` filenames could not match. Widened to
`[a-z0-9_]+`. Recorded here rather than silently corrected, consistent with how
the three Phase-1, three Phase-1.5 and two Phase-2 checker defects were handled.

## New issue found, reported not fixed

**NEW-1** — Figures 2, 4 and 5 have no in-prose reference (only Figures 1 and 3
are named in a sentence). `MINOR` / `PRESENTATION_ONLY`; affects no number and
no claim. Outside the authorized fix set, so reported rather than applied.
