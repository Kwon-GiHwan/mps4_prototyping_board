# Project status — scientific closeout

**Recorded:** 2026-09-04

```
SCIENTIFIC_CAMPAIGN_COMPLETE
MANUSCRIPT_CONTENT_SUBMISSION_READY
```

## Authoritative state

| role | tag | commit |
| --- | --- | --- |
| paper content | `paper-manuscript-submission-ready` | **d137a7d** |
| final internal review | `paper-submission-ready-final-review` | **49c8b3b** |

Final verdict `SUBMISSION_READY` — BLOCKER 0, MAJOR 0, MODERATE 0, MINOR 0.
X2 `NOT_NEEDED`. X4 / X5 **HOLD**.

The scientific and manuscript-content campaign is **closed**. No further
experiment, analysis, metric, scientific rewriting, RQ or contribution
restructuring, or opportunistic paper edit is to be performed.

## Remote backup

| | |
| --- | --- |
| branch | `paper/submission-ready` |
| remote head | `49c8b3bc77143e293137cf6d4f3e732635709a83` |
| contains | d137a7d (manuscript) and 49c8b3b (final review), verified by ancestry |
| `origin/main` | untouched — `cd59986`, unchanged |
| tags pushed | none of this campaign's 11 tags are on the remote |

**Branch point.** The branch was cut at 49c8b3b rather than d137a7d. The review
commit adds only `SUBMISSION_READY_REVIEW.md` and `SUBMISSION_READY_META.json`
and changes no paper content, so the manuscript, figures, tables, references and
frozen evidence on the branch are byte-identical to the submission-ready state,
while the authoritative final review is preserved on the remote as well. Cutting
at d137a7d would have left the final review local-only, against the purpose of
the backup. If strictly d137a7d is wanted as the branch head, the branch can be
reset — the manuscript content is identical either way.

## Evidence and review trail (11 tags, all local)

```
paper-full-review-frozen                  9359c7a   full-paper review
paper-manuscript-review-phase1-frozen     f09bba6   remediation items 1-6
paper-manuscript-phase1-review-frozen     85aa4d5   phase-1 gate
paper-manuscript-phase1_5-frozen          6dce4d8   F1-F11, F13-F15
paper-manuscript-phase1_5-review-frozen   983ef04   phase-1.5 gate
paper-manuscript-phase2-frozen            8754295   action plan 7-14 + conclusion
paper-final-review-frozen                 31f2bd4   final review
paper-manuscript-submission-candidate     a990e03   polishing MOD/MIN
paper-submission-readiness-frozen         d2c5849   readiness gate
paper-manuscript-submission-ready         d137a7d   NEW-1 closed
paper-submission-ready-final-review       49c8b3b   submission-ready gate
```

## Manuscript at closeout

| | |
| --- | --- |
| words | 9,243 |
| sections | 10 + 2 appendices |
| figures | 5, all captioned and prose-referenced, regenerable from frozen CSVs |
| tables | 9 (+2 in Appendix A) |
| references | 17, all resolving both directions |
| validation | 222 checks across 6 suites, all passing |

## Next phase — SUBMISSION ENGINEERING (not started)

Inspected read-only for scoping; **nothing was modified**. Current state:

| asset | present |
| --- | --- |
| `.tex` / `.cls` / `.sty` / `.bib` | none |
| ACM `acmart` template | none |
| `pandoc` | not installed |
| `pdflatex` / `latexmk` | not installed |
| manuscript format | Markdown, 9,243 words |
| figures | SVG × 5 (generator emits SVG; no PDF/EPS path yet) |
| bibliography | 17-entry manual numeric list, no `.bib` |

So that phase begins from a Markdown source with no LaTeX toolchain on this
machine, and will need at minimum: an ACM document class, a `.bib` conversion, a
figure format acceptable to the template, and a PDF build path.

**No conference or ACM requirement is recorded here, deliberately.** Page limits,
anonymization rules, template version, and artifact/supplementary policy must be
retrieved from authoritative sources when that phase is authorized, with the
exact source, version and retrieval date recorded — not reproduced from memory.

## Unrelated working-tree item

`docs/presentation/ethos_u_measurement_deck.md` is untracked and unrelated to
the paper. It was **not** included in the backup, not committed, and not
cleaned. Reported here for a separate decision.
