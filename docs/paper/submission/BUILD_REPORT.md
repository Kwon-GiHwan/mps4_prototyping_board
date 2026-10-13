# SE1 build report

## Build environment (isolated, pinned, project-local)

The host had no `pandoc`, `pdflatex`, `latexmk` or `acmart`. Per the decision,
the host was **not modified globally**: no system package manager was used and
nothing was installed on a system path.

| item | value |
| --- | --- |
| environment | project-local TeX Live under `.toolchain/TinyTeX/` (not on the system `PATH`) |
| installer | `https://yihui.org/tinytex/install-bin-unix.sh`, archived at `.toolchain/install-tinytex.sh` |
| TeX distribution | **TeX Live 2026** |
| TeX engine | pdfTeX 3.141592653-2.6-**1.40.29**, kpathsea 6.4.2 |
| latexmk | **4.88** (9 March 2026) |
| BibTeX | **0.99e** (TeX Live 2026) |
| biber | installed (unused; BibTeX path is used) |
| `tlmgr` | revision 79639 |
| **acmart** | **v2.20**, TeX Live revision 80008, dated 2026/08/16 |
| acmart source | CTAN via TeX Live — the channel ACM's own maintainer publishes to. No `acmart.cls` was copied from a third-party repository |
| acmart SHA-256 | `784c4f2fb07a70d8a797ee9d1c63f441c10fbd2f915c9c615d28cda35c0b742a` |
| SVG→PDF | `svglib` 2.2.0 + `reportlab` 5.0.1, pure Python, vector (no Inkscape/cairo, no rasterization) |
| build command | `./docs/paper/submission/scripts/build_submission.sh` — one command, no manual sequence |

A container was considered first and rejected on evidence: the remote build host
has Docker 29.4.0 but only **3.3 GB free (94 % full)**, which a TeX Live image
does not fit, and filling the project's firmware build host would have been
reckless. The project-local route is the decision's other named option.

**Reproducibility:** `SOURCE_DATE_EPOCH` is pinned to the `d137a7d` commit
timestamp and `FORCE_SOURCE_DATE=1` is set, so the PDF's `CreationDate` is
deterministic (`D:20260904070020Z`) rather than wall-clock.

## Class configuration

```latex
\documentclass[acmsmall, screen, review, anonymous]{acmart}
```

`acmsmall, screen, review` is **verbatim from the CFP**. `anonymous` is added
alongside to satisfy the separate double-anonymous policy — no substitute class
was used to obtain anonymous mode, and margins, font sizes, line spacing and
page geometry are untouched.

## Build result

```
PDF BUILD: PASS
```

Not asserted from exit code alone. Verified:

| check | result |
| --- | --- |
| PDF produced | `build/paper-review.pdf`, 21 pages |
| page size | 486 × 720 pt = 6.75 × 10 in = `acmsmall` |
| undefined citations | **0** |
| undefined references | **0** |
| missing characters | **0** |
| undefined font shapes | **0** |
| Type 3 fonts | **NONE** |
| non-embedded fonts | **NONE** (9 fonts, all embedded) |
| overfull hboxes | **1**, worst 3.4 pt (was 7, worst 474 pt) |
| overfull vboxes | 0 |
| figures present and unclipped | 5/5, verified visually |
| PDF metadata deanonymization | none — no `/Author`; creator/producer are toolchain strings only |
| anonymous mode active | verified in the rendered title block: "ANONYMOUS AUTHOR(S)", running head "Anon." |

**Font embedding required a fix.** The ReportLab figure PDFs initially referenced
the non-embedded base-14 Helvetica, Times-Roman and Symbol. The converter now
registers **Arimo** (Apache-2.0, metric-compatible with Helvetica) for the
figures' text, so layout is unchanged and every font is embedded.

## Visual inspection

Rendered and inspected rather than assumed:

| page | content | result |
| --- | --- | --- |
| 1 | title, anonymous author block, abstract, RQ1 | correct; cross-references resolve |
| 7 | Figure 1 + the efficiency-class table | figure legible and vector, legend intact, table correct |
| 12 | Figure 4 | the MOD-2 reconciliation block renders: +19,000 / +19,060 / 60 with the residual wording |
| 5, 10, 11, 13, 19, 20 | dense tables, remaining figures, references and appendix boundaries | no clipping, no overflow |

## Appendix compliance (CFP: unconstrained length, technical correctness only)

| appendix item | classification | novelty load-bearing? |
| --- | --- | --- |
| A.1 board rank pairs | `TECHNICAL_CORRECTNESS_SUPPORT` | **no** — the result (`rho = 1.0`, 0 inversions) is stated and shown in Section 6 and Figure 3; the table is the exact data behind it |
| A.2 normalized relative cost | `TECHNICAL_CORRECTNESS_SUPPORT` | **no** — Figure 3 carries the shape in the main body |
| B provenance and procedure | `TECHNICAL_CORRECTNESS_SUPPORT` | **no** — identity chain, build reproducibility, repetition rules; a reader can evaluate every claim without it, with a pointer left in Section 3 |

```
NOVELTY_LOAD_BEARING = 0
```

No main conclusion requires reading the appendix, and **no material was moved
into the appendix for page relief** — the appendix contains exactly what the
scientific review placed there before this phase.

## Scientific invariance (SE1 §16)

```
scripts/invariance_check.py   51 checks   DRIFT = 0
```

Verified against the rendered PDF, not just the source: RQ1–RQ4 present and RQ1
not restored to the refused question; all three thesis clauses; all five figure
semantics; the anchors 468×, +19,000 / +19,060 / 60, 133 / 222 / 74 / 21,
24/32, 14/14, 7/7, 27 of 29, 19 of 21, 19/20, 31/55, 0.9429, 1.0000; `467×`
absent; board `rho = 1.0` with 0 inversions; the full scope vocabulary
(`NOT_SEPARATED`, `NOT_EVALUABLE`, `ASSOCIATED_WITH`, `CONSISTENT_WITH`,
`NOT_EQUIVALENT`, `NOT_COMPARABLE`, `ROBUST_IN_TESTED_PAIRS`,
`TA_STATE_SENSITIVE`, `NOT_REPRODUCIBLE`); CLASS A/B never pooled; U65 bridge
`NOT_EQUIVALENT`; and no prohibited claim (raw cross-platform comparability,
architecture-only causality, TA causation, FVP-board timing equivalence).

Three checker artifacts were found and fixed during this gate, and are recorded
rather than silently corrected: PDF line-break hyphenation turned
"non-monotonic" into "nonmonotonic"; the `review` line-number margin made a bare
"467" look like the retired 467× figure; and a greedy section regex matched
whole section bodies. All three were checker defects, not drift.

## Deadline / submission-form checklist (Fall cycle — non-mutating)

Nothing was submitted and no HotCRP entry was created.

| item | state |
| --- | --- |
| abstract registration by **2026-10-02 23:59 AoE** | not done — 27 days from the build date |
| paper submission by **2026-10-09 23:59 AoE** | not done — 34 days |
| substantive title | ready (from the frozen manuscript) |
| substantive abstract | ready, 312 words |
| author list | **not prepared** — author-side data, outside this phase |
| conflicts declaration | **not prepared** — requires the PC list and the author's own records |
| track selection | recommended: Measurement & Applied Modeling, single track (`TRACK_RECOMMENDATION.md`) |
| anonymity | `NEEDS_FIX` — one two-place text edit (`ANONYMITY_AUDIT.md`) |
| reproducibility declaration | drafted, `NEEDS_MANAGER_CONFIRMATION` (hosting target, licence) |
| AI disclosure in Methods | drafted, `NEEDS_MANAGER_CONFIRMATION` (two scope questions); **not yet inserted into the manuscript** |
| PDF upload | build is ready; blocked behind the three items above |

## Known deviations to revisit

1. **Tables have no captions.** The source tables carry none, and inventing
   captions would add content. Acceptable for review; likely wanted for
   camera-ready.
2. **Ten bibliography entries render "n.d."** — the Arm documents have no
   verified publication date. Correct over a guessed date; resolve at
   camera-ready.
3. **Figure 4's reconciliation block is small** (~6 pt at print scale). Legible,
   but a candidate for enlargement in a later pass.
4. **Code-block glyphs are ASCII-folded** (box drawing, arrows) because pdfTeX
   cannot set them in `verbatim`. Structure preserved.
