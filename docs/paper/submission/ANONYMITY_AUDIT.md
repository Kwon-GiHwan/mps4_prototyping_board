# Anonymity audit — SIGMETRICS 2027 double-anonymous submission

**Policy (CFP, verified 2026-09-04):** double-anonymous review; authors must
make a good-faith effort to anonymize using non-destructive anonymization.

**Scope of this audit:** `main.tex`, `references.bib`, `figures/*.pdf`, and the
built `build/paper-review.pdf`.

**Class note.** The CFP mandates `\documentclass[acmsmall, screen, review]{acmart}`.
`acmart`'s own anonymization is enabled with the additional `anonymous` option,
which is what `main.tex` uses:
`\documentclass[acmsmall, screen, review, anonymous]{acmart}`.
The required class and mode are unchanged — **no substitute document class was
used to obtain anonymity**, which the decision explicitly forbids.

---

## Category results

| # | category | result | evidence |
| --- | --- | --- | --- |
| 1 | author names | **PASS** | no `\author`, `\authornote`, or name anywhere in `main.tex`; the only `author` fields in `references.bib` are the authors of cited works, which anonymization must not remove |
| 2 | affiliations | **PASS** | no `\affiliation`, `\institution`, `\department`, `\city`, `\country` |
| 3 | email addresses | **PASS** | no `\email`; no address pattern in either file |
| 4 | acknowledgments | **PASS** | no `acks` environment; none present in the source manuscript either |
| 5 | funding identifiers | **PASS** | no `\thanks`, no grant number, no `\acmBooktitle` funding text |
| 6 | institutional self-identification | **PASS** | no institution, lab, group or facility name in the prose; the hardware is identified only by product name (MPS4, Corstone-320), which is vendor identification, not author identification |
| 7 | repository / project URLs | **NEEDS_FIX** | see below |
| 8 | PDF metadata | **PASS (figures)**, pending for the built paper | figure PDFs carry `/Author (anonymous)`, `/Creator (anonymous)`, `/Producer (ReportLab PDF Library)`; no user or machine name. The built `paper-review.pdf` is re-audited after the build (`BUILD_REPORT.md`) |
| 9 | filenames | **PASS** | `main.tex`, `references.bib`, `fig1..fig5_*.pdf` — no name, initials, institution or project-owner string |
| 10 | comments embedded in the PDF | **PASS** | LaTeX `%` comments do not reach the PDF. The generator header comment naming `docs/paper/submission/scripts/md2tex.py` exists in `main.tex` only, and only the PDF is submitted |
| 11 | self-citations in first-person identifying form | **NOT_APPLICABLE** | the bibliography contains no self-citation: all 17 entries are Arm vendor documentation or third-party published work. Nothing needs conversion to third person |
| 12 | anonymous mode actually active | **PASS** | `anonymous` option present; verified in the built PDF's title block during the build audit |

---

## The one finding — category 7

Three repository-relative paths survive from the source manuscript into
`main.tex`:

| location | string | why it matters |
| --- | --- | --- |
| Section 3.5 | `docs/superpowers/evidence/` | a distinctive, unusual directory name; searching it together with "Ethos-U85" is a plausible route to the author's public repository |
| Appendix A | `docs/paper/analysis/board_rq3/` | generic enough alone, but corroborating |
| Section 3.5 / prose | reference to the frozen tag naming scheme | corroborating |

The project's repositories are public, so these are a realistic deanonymization
vector rather than a theoretical one. This is **not** a scientific claim and
removing it costs no evidence: each path is an internal pointer, not a result.

**Proposed minimal, non-destructive replacement** (not applied — it edits
manuscript text, which is outside this phase's authorized scope):

| current | proposed |
| --- | --- |
| "frozen under `docs/superpowers/evidence/` rather than reproduced here" | "frozen in the project's evidence archive rather than reproduced here" |
| "Reproduced from `docs/paper/analysis/board_rq3/`" | "Reproduced from the frozen board-analysis outputs" |

Both preserve the reproducibility intent — the artifact is still identified as
frozen and archived — while removing the searchable path. The concrete paths
belong in the artifact/reproducibility declaration at camera-ready, when
anonymity no longer applies.

**Status:** `NEEDS_FIX`, one text edit in two places, awaiting manager
authorization because this phase forbids manuscript edits.

---

## What was deliberately not done

- No cited work was removed or obscured for anonymity. The CFP requires
  non-destructive anonymization, and the bibliography contains no self-citation
  to soften in any case.
- No document class substitution. `acmsmall, screen, review` is retained exactly
  as the CFP mandates, with `anonymous` added alongside rather than instead.
- Vendor and product names (Arm, Ethos-U55/U65/U85, Corstone-300/310/315/320,
  Vela, MPS4) were retained. They identify the measured system, not the authors,
  and removing them would destroy the paper.

## Verdict

```
ANONYMITY: NEEDS_FIX  (1 category of 12; 10 PASS, 1 NOT_APPLICABLE)
```

The single finding is a two-place text substitution with no scientific content.
Everything the class and metadata control already passes.
