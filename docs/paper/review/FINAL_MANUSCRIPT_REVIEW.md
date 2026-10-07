# Final manuscript review — frozen paper

**Subject:** `paper-manuscript-phase2-frozen` = 8754295
**Predecessors:** 6dce4d8 (Phase-1.5), 983ef04 (Phase-1.5 review), 9359c7a (full review)
**Mode:** review only. Nothing was modified during this gate; the manuscript is
byte-identical to the frozen tag.

## Verdict

```
BLOCKER    0
MAJOR      0
MODERATE   2
MINOR      2
```

Target met. The two moderate findings are presentation defects introduced by
Phase-2 itself, both mechanical to repair in a polishing pass. **No scientific
contradiction was found, and no finding requires new measurement.**

| | |
| --- | --- |
| all RQs closed | **YES** — RQ1–RQ4 `CLOSED`, none depending on a refused comparison |
| thesis clauses supported | **3 / 3** |
| references | 17, all resolving both directions |
| figures | 5 |
| tables | 9 (+ 2 in Appendix A) |
| numerical discrepancies | 1, found and resolved in Phase 2 (the 467× span) |
| rule failures | 0 |
| scientific contradictions | 0 |
| new experiment required | **NO** |
| X2 | `NOT_NEEDED` |

---

## MODERATE

### MOD-1 — Figures appear out of numerical order

Order of appearance is **1, 5, 4, 2, 3**: Figure 1 in §4.1, Figure 5 in §5,
Figure 4 in §6, Figure 2 in §7.3, Figure 3 in §7.4.

The numbering follows the order the figures were *generated* (the frozen action
plan's candidate list) rather than the order the reader meets them. Every figure
is embedded, captioned and referenced in prose, and each caption scopes its own
evidence, so nothing is unclear — but a reader who encounters Figure 5 second
will assume they have missed something.

**Fix:** renumber to appearance order (1 → 1, 5 → 2, 4 → 3, 2 → 4, 3 → 5),
updating the five filenames, the five captions, the alt text, the generator's
`prov()` records and `FIGURE_PROVENANCE.json`. `TEXT_ONLY` plus a figure
regeneration; no data changes. Deferred to the polishing pass because this gate
forbids editing.

### MOD-2 — Figure 2 labels the instrumented group sum as the whole-model change

Figure 2's subtitle and alt text both read *"the whole-model change is +19,060
cycles"*. That number is the **sum of the instrumented group deltas**, not the
whole-model change, which §7.1 gives as `36,086 → 55,086` = **+19,000**.

The 60-cycle difference is not an error in the data and is already explained in
§9.5 — each interrupt-service boundary carries a small deterministic cycle
residual, so group and whole-model sums agree within that residual — but the
caption states the group sum under the whole-model's name, and the two figures
(+19,000 in prose and the abstract, +19,060 in the figure) sit two pages apart
with no adjacent reconciliation.

**Fix:** caption should read "the instrumented group deltas sum to +19,060,
against a whole-model change of +19,000; the 60-cycle difference is the
interrupt-service residual of Section 9.5". `TEXT_ONLY` plus regeneration.
Defect introduced by Phase-2 action 7, not present before.

---

## MINOR

- **MIN-1 — Methodology is the largest section.** §3 is 1,685 words of ~9,040
  (19 %). The content is load-bearing — three-kinds-of-number, the three
  compilation paths, and the measurement-boundary qualification all guard
  against specific misreadings — but §3.6 (provenance and procedure) could move
  to the appendix in a polishing pass without weakening any guard.
- **MIN-2 — Appendix A's title is narrower than its content.** It is titled
  "Exact values behind Figure 4", but A.1 (the rank pairs) supports the §6
  ranking claim as much as it supports the figure. "Exact values behind the
  board validation" would be more accurate.

---

## What was checked, and what held

**Numerical integrity (22 audited claims,** `FINAL_CLAIM_EVIDENCE_AUDIT.csv`**).**
Thirteen claims were re-derived from frozen artifacts rather than read back:
the 74/222/74-of-74 formal counts and their derivation from the 77-cell TA-ON
universe minus 3 non-executable cells; 21 ladders and 53 adjacent transitions
recomputed from `scaling.csv`; saturation counted from `saturation.csv`
(19 `NONE_OBSERVED`, exactly one observed, at SSE-320/U85/`rnnoise`@512); Vela
agreement 19/20 on both criteria; board counts and all fourteen appendix values
to four decimals; the U85 14-group partition (10/1/3 directions, summing to
19,060); cross-memory totals 3,015 / 15,075 / 19,060 with 27-of-29
direction-consistent and zero flips; the X1/X3 agreement counts including 24/32
and the eight disagreements; and 133 compiled / 6 non-executable with the six
confirmed as `wav2letter` × U55 × `Shared_Sram`. Eight further claims were
verified as present and correctly scoped. **Every load-bearing number resolves.**

**The one discrepancy, already resolved.** §3.2's "467×" workload span traced
only to a pre-sweep planning document whose per-model Vela values do not appear
in the frozen matrix. Phase 2 replaced it with 468×, computed from the frozen
matrix at `SSE-320 / ethos-u85-256 / Dedicated_Sram`. This review additionally
confirmed that the configuration choice was **forced, not arbitrary**: it is the
only U85-256 configuration in the frozen matrix containing all seven workloads.
The claim is descriptive and load-bearing for nothing.

**Prohibited-claim scan — 9/9 clear.** No affirmative claim that raw
cross-platform cycles are comparable; no "U85 is X % faster"; no TA causation
for the X1 disagreements; no block-enlargement or bandwidth causation; no
FVP-predicts-board accuracy; no full PMU backend equivalence; no claim that the
legacy profile exactly decomposes regor execution; no `num_macs=100` /
bounds-only claim. Negated, retired and historical uses of the same vocabulary
are correctly preserved and were not flagged.

**Platform roles — stable.** The four-row §3.1 table is unchanged, the new §2
paragraph states the primary-versus-diagnostic distinction before the reader
meets the subsystems, and no figure or prose presents the four as one
absolute-performance series. Figure 1's panels are explicitly non-comparable and
Figure 5 never pools CLASS A with CLASS B.

**Cross-generation ceiling — held.** No statement attributes performance to core
replication, block enlargement, or Corstone generation. §4.5 answers RQ1 in
per-axis terms without causal language, and the wording was not broadened in any
way that would make X2 necessary again. **X2 remains `NOT_NEEDED`.**

**Results / Discussion separation.** §7.6 is now a measurement summary; the
emergence framing, the retired ublock account, the board interpretation and the
CLASS B licensing all live in §8 with one-line pointers left in Results. Zero
duplicated sentences between §7.6 and §8.

**Limitations.** All 14 preserved under six themes, none withdrawn or softened,
with an orienting paragraph that states what is established, what is structural
only, and what is not separable — the section no longer reads as
self-invalidation.

**Conclusion.** Introduces no new number (its numeric set is a subset of the
preceding text), no novelty claim, and no future-work promise stated as a
current result. Limitations compressed to two sentences pointing at §9.

**Structural balance.** §7 mechanism 1,210 words against §6 board 356 words: the
narrative hierarchy now matches the contribution hierarchy, with board
validation clearly supporting rather than co-primary.

---

## Suite status at 8754295

```
phase1_consistency_check.py     16/16   claim discipline, incl. causal isolation
phase1_5_validation.py          25/25   structure, thesis, references, roles
phase2_validation.py            98/98   numeric integrity, prohibited claims, flow
manuscript_text_fixtures.py     14/14   shared normalization
phase1_5_checker_fixtures.py    14/14   F4 causal-language regression
                               -------
                               167/167
```

## Recommendation

The paper is **not yet submission-ready**, by the intended margin: MOD-1 and
MOD-2 are a renumbering and a caption correction, both mechanical, both
`TEXT_ONLY` plus a deterministic figure regeneration, and both introduced by
Phase 2 rather than surviving from the original review. A single polishing pass
closes them along with the two minors.

Nothing found here reopens X2, X4 or X5, and nothing requires new measurement.

**Verification level: static analysis and automated checking of the frozen tag.**
Executed: all five suites at 8754295; re-derivation of every load-bearing number
from frozen CSV/JSON; the nine-item prohibited-claim scan; reader-flow audit
(numbering, pointers, figure embedding/captioning/reference, RQ declaration
order, terminology); section-balance and duplication measurement; independent
confirmation that the mi1 configuration choice was forced.
Not executed: no build, simulation, FVP run, board run, or measurement; no
frozen analyzer re-run; no external peer review; figures inspected visually for
two of five, geometry-audited for all five.
