# Markdown → LaTeX conversion provenance

**Source of truth:** `d137a7d:docs/paper/MANUSCRIPT.md`, read through `git show`
rather than the working tree, so the conversion cannot pick up an uncommitted
change.
**Converter:** `scripts/md2tex.py` — deterministic, re-run on every build.
**Section trace:** `SECTION_TRACE.md` (37 headings mapped).
**Invariance gate:** `scripts/invariance_check.py` — **51 checks, 0 drift.**

`main.tex` is generated. It is never hand-edited: fixes go into the converter,
and the build regenerates.

## What was transformed

| markdown | latex | note |
| --- | --- | --- |
| `# Title` | `\title{}` | verbatim |
| `## Abstract` | `abstract` environment + `\maketitle` | verbatim |
| `## N. Title` | `\section{}\label{sec:N}` | 10 sections |
| `### N.M Title` | `\subsection{}\label{sec:N.M}` | numbering preserved by order, not hardcoded |
| `## Appendix A/B.` | `\appendix` + `\section{}\label{app:A/B}` | after the bibliography, per ACM ordering |
| `**bold**`, `*italic*`, `` `code` `` | `\textbf`, `\emph`, `\texttt` | |
| pipe tables | `tabular` with `booktabs` rules, alignment read from the separator row | 9 tables |
| fenced code | `verbatim` in a `quote` | 4 blocks |
| `![alt](figures/figN.svg)` + `**Figure N.**` caption | `figure` float with `\includegraphics`, `\Description`, `\caption`, `\label{fig:N}` | 5 figures; alt text preserved as `\Description` for accessibility |
| `[9]`, `[1, 2]` | `\cite{key}`, `\cite{k1,k2}` | 17 keys, all resolving |
| "Section N", "Figure N", "Appendix A" | `\ref` | resolved by LaTeX, so renumbering cannot desynchronize them |

## Deliberate omissions

Both are internal process metadata carrying no scientific claim, and both would
breach the double-anonymous policy by naming the project's git tags and paths:

1. the header provenance block (frozen tag list, revision date, figure-generator
   path);
2. the trailing *Integration status* note (frozen source tags).

The Markdown `## References` list is also dropped — replaced by BibTeX.

## Deliberate presentational transformations

| transformation | reason | scientific effect |
| --- | --- | --- |
| box-drawing and arrow glyphs inside code blocks ASCII-folded (`─`→`-`, `│`→`|`, `→`→`->`, `↓`→`v`, `↔`→`<->`, `┌┐┴`→`+`) | pdfTeX cannot set these in `verbatim` with the default fonts | none — diagram structure preserved, glyphs differ |
| prose unicode mapped to LaTeX (`—`→`---`, `×`→`$\times$`, `≥`→`$\geq$`, `≤`, `±`, `−`, `…`) | correct typesetting | none |
| straight ASCII quotes → TeX quotes | typography | none |
| tables rendered as inline `tabular`, not floats | the source tables carry no captions, and inventing captions would add content | none — position and content preserved |

## Bibliography

17 entries, all cited, all resolving. Correspondence and authority:

| # | title (short) | BibTeX key | authority | verified fields | omitted / unresolved |
| ---: | --- | --- | --- | --- | --- |
| 1 | Ethos-U85 TRM | `arm:ethosu85trm` | Arm doc 102685 | title, org, doc number, URL | publication date |
| 2 | Ethos-U85 Technical Overview | `arm:ethosu85to` | Arm doc 102684 | title, org, doc number, URL | date |
| 3 | ML Developers Guide | `arm:mldevguide` | Arm doc 109267 | title, org, doc number, URL | date |
| 4 | Corstone-320 Reference Package TO | `arm:corstone320` | Arm doc 109761 | title, org, doc number, URL | date |
| 5 | FVPs for Corstone SSE-320 | `arm:fvpsse320` | Arm doc 109760 | title, org, doc number, URL | date |
| 6 | Fast Models FVP Reference Guide | `arm:fastmodels` | Arm doc 100966 | title, org, doc number, URL | date |
| 7 | Ethos-U Vela compiler | `arm:vela` | mlplatform.org repository | title, org, URL, version 5.0.0 | date |
| 8 | ML Embedded Evaluation Kit | `arm:mlek` | mlplatform.org repository | title, org, URL | date |
| 9 | TPU (Jouppi et al.) | `jouppi2017tpu` | ISCA 2017; arXiv:1704.04760 | authors (partial, `and others`), title, venue, year | full author list, pages, DOI |
| 10 | SCALE-Sim | `samajdar2018scalesim` | arXiv:1811.02883 | authors, title, year | venue, DOI |
| 11 | Timeloop | `parashar2019timeloop` | ISPASS 2019 | authors, title, venue, year | pages, DOI |
| 12 | Sources of Error in Full-System Simulation | `gutierrez2014sources` | ISPASS 2014 | authors, title, venue, year | pages, DOI |
| 13 | MLPerf Tiny | `banbury2021mlperftiny` | NeurIPS D&B 2021; arXiv:2106.07597 | authors, title, venue, year | pages, DOI |
| 14 | MicroNets | `banbury2021micronets` | MLSys 2021; arXiv:2010.11267 | authors, title, venue, year | pages, DOI |
| 15 | TensorFlow Lite Micro | `david2021tflm` | MLSys 2021 | authors, title, venue, year | pages, DOI |
| 16 | Ethos-U55 TRM | `arm:ethosu55trm` | Arm doc 102420\_0200\_02\_en, r2p0 | title, org, doc ID, revision, URL — **content verified in Phase 1.5** | date |
| 17 | Ethos-U65 TRM | `arm:ethosu65trm` | Arm doc 102023\_0000\_06\_en, r0p0 | title, org, doc ID, revision, URL — **content verified in Phase 1.5** | date |

**No DOI, page range, issue, publisher or date was invented.** The ten Arm
entries have no verified publication date, so BibTeX renders them "n.d." — the
correct scholarly form for an undated document, and preferred here over a guess.
Resolving those dates and the academic DOIs is a camera-ready task.

**Unresolved metadata count: 10 entries missing a date, 7 missing DOI/pages.**
No citation maps to the wrong source: each key was checked against the frozen
reference list entry it replaces, and the built PDF resolves all 17.
