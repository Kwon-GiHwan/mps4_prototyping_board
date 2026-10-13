# Submission-readiness review — review only

**Subject:** `paper-manuscript-submission-candidate` = a990e03
**Polishing record:** `FINAL_POLISHING.md`, `FINAL_POLISHING_CHECKS.md`
**Predecessors:** 8754295 (Phase-2 manuscript), 31f2bd4 (final review)
**Mode:** review only. The manuscript was not edited during this gate and is
byte-identical to the tag.

## Verdict

```
BLOCKER    0
MAJOR      0
MODERATE   0
MINOR      1   (optional copy-editing; no scientific meaning affected)

SUBMISSION_READY_WITH_COPYEDIT
```

## Authorized issue set — all closed

| id | issue | status | evidence |
| --- | --- | --- | --- |
| **MOD-1** | figures appeared 1, 5, 4, 2, 3 | **CLOSED** | captions and embedded filenames both run 1→5; each caption number asserted equal to the number in the file it follows; all four superseded filenames absent from text and directory |
| **MOD-2** | figure called the profiled-group sum the whole-model change | **CLOSED** | figure, prose and provenance now carry +19,000 / +19,060 / 60 distinctly; checked in all three places independently |
| **MIN-1** | methodology the largest section | **CLOSED** | §3.6 moved verbatim to Appendix B with a pointer; 1,685 → 1,580 words, 19.5 % → 18.0 %; four named guards verified present |
| **MIN-2** | appendix title too narrow | **CLOSED** | retitled "Exact values behind the board validation"; old title absent; still reachable from §6 |

## MINOR remaining

**NEW-1 — Figures 2, 4 and 5 have no in-prose reference.** Only Figures 1 and 3
are named in a sentence. Every figure is embedded, captioned, placed directly
beneath the paragraph it illustrates, and scoped by its own caption, so nothing
is unclear or unsupported — but a reader scanning for "Figure 2" finds only the
caption. Three sentences of the form "Figure 2 shows …" would close it.

This was discovered during polishing, is outside the authorized fix set, and was
reported rather than applied. It affects **no number, no claim and no scientific
meaning**, which is precisely the category the decision permits to remain.

## What was verified

**All six mandated checks pass.** A: figures first appear in order 1–5, with
caption-to-filename numbers cross-asserted. B: every figure reference resolves,
five files on disk, all referenced, no stale filename anywhere. C: no
"whole-model +19,060" claim survives in the manuscript, the figure, or the
provenance JSON. D: the three delta semantics are distinguished, the residual
carries the frozen scoped wording rather than a stronger causal model, the
arithmetic is asserted, and §9.5's original explanation is intact. E: 468× is
used with its basis configuration named and the string `467` does not occur in
the manuscript. F: MIN-1 and MIN-2 closed with guards preserved.

**Suites: 209 / 209** across six files — 16 claim-discipline, 25 structural,
98 numeric-integrity and reader-flow, 42 polishing, and 28 fixtures.

```
rule failures              0
scientific contradictions  0
numerical discrepancies    0
new experiment required    NO
X2                         NOT_NEEDED
```

**Frozen conclusions intact.** RQ1–RQ4 `CLOSED`; thesis 3/3; abstract ready;
raw cross-platform cycles `NOT_COMPARABLE`; ranking / direction / saturation /
normalized ordering `ROBUST_IN_TESTED_PAIRS`; threshold scaling class
`TA_STATE_SENSITIVE`; CLASS B TA / subsystem / FM `NOT_SEPARATED`; U85
heterogeneous group gains and losses with ublock alone insufficient,
compiler/memory `NOT_SEPARATED`, stall causality `NOT_EVALUABLE`; board
`rho = 1.0` with zero inversions and no absolute FVP–board timing equivalence;
U65 bridge `NOT_EQUIVALENT` overall with component equivalence only. Platform
roles unchanged; no edit made the four platforms readable as one
absolute-performance series.

**Frozen review artifacts at 31f2bd4 were not modified** — confirmed by diff.
Their `Figure 2` / `Figure 4` references predate the renumbering and should be
read against the mapping table in `FINAL_POLISHING.md`.

## One defect in this pass, disclosed

The first draft of the polishing record stated the post-move methodology size as
"1,391 words / 16.2 %". **Neither number was ever produced by a check** — the
relevant check prints its detail only on failure, and it passed, so the value was
written without being observed. The measured figures are 1,580 words / 18.0 %,
down from 1,685 / 19.5 %.

Both documents were corrected before this gate, and check F was tightened from
an open `< 19 %` bound to an assertion on the measured word count and a narrow
share band, so a reported figure nobody observed cannot pass again. **The
manuscript contains no such figure and was unaffected**; the defect was confined
to my own record of the work. It is disclosed here rather than quietly fixed
because the failure mode — stating a number that was not observed — is the one
this project treats as most serious.

## Final state

| | |
| --- | --- |
| words | 9,171 |
| sections | 10 + 2 appendices |
| figures | 5 |
| tables | 9 (+2 in Appendix A) |
| references | 17 |
| whole-model delta | +19,000 |
| profiled-group delta | +19,060 |
| residual | 60 (deterministic profiling-boundary / interrupt-service) |
| workload span | 468× |

## Recommendation

**`SUBMISSION_READY_WITH_COPYEDIT`.** The paper is scientifically complete and
internally consistent: no blocker, no major, no moderate finding, every RQ
closed, every load-bearing number traced to a frozen artifact, and every refused
comparison still refused. The single remaining item is three optional sentences
of figure cross-reference.

Nothing found here reopens X2, X4 or X5, and nothing requires new measurement.

**Verification level: static analysis and automated checking of the frozen tag.**
Executed: all six suites at a990e03; independent re-verification of the
methodology word count and share; confirmation that the frozen review artifacts
are untouched; structural read of the final section layout and appendix
placement.
Not executed: no build, simulation, FVP run, board run, or measurement; no
frozen analyzer re-run; no external peer review; figures inspected visually for
two of five, geometry-audited for all five.
