# REMEDIATION PHASE 2 — traceability record

**Authorization:** REVIEW REMEDIATION PHASE 2 — MANAGER GO (7–14 GO; F12
Conclusion authorized; X2/X4/X5 HOLD; no new measurement).
**Input:** `paper-manuscript-phase1_5-frozen` = 6dce4d8
**Action plan:** read from `paper-full-review-frozen` = 9359c7a, not from memory.
**Output:** `paper-manuscript-phase2-frozen`
**Fix classes used:** `TEXT_ONLY`, `EXISTING_DATA_ONLY`. No `NEW_EXPERIMENT`,
no `NEW_METRIC`, no `REANALYSIS_WITH_NEW_DEFINITION`. No build, FVP run, board
run, or measurement.

---

## 0. Checker infrastructure (prerequisite, not an action)

Phase 1 and Phase 1.5 each lost checks to one failure family: the manuscript is
hard-wrapped, so literal multi-word patterns failed on text that was
semantically present, and each checker relaxed its own regex ad hoc. **Six of
six checker defects across those two phases were variants of this.**

`docs/paper/review/manuscript_text.py` now provides one read-only normalization
behaviour for every checker:

- intra-paragraph whitespace collapsed for semantic phrase matching, with
  paragraph and block boundaries preserved as sentinels so a pattern cannot
  match across two unrelated blocks;
- fenced code blocks masked for prose matching (whitespace is load-bearing
  inside them) while preserving offsets, so line mapping still works;
- bold-inline subsections indexed alongside markdown headings;
- every normalized match mapped back to its original 1-based line number.

**The source manuscript is never rewritten to satisfy a regex.** Both existing
checkers were migrated onto it, and `phase1_5_validation.py` now resolves
section pointers against section **titles** rather than hardcoded numbers —
which is what allowed action 8 to renumber five sections without silently
invalidating a check.

Fixtures: `manuscript_text_fixtures.py`, 14 tests, covering the seven cases the
decision named (phrase split across one newline; across multiple spaces; section
pointer wrapped across lines; bold/inline formatting around a section reference;
negated causal sentence; `NOT_SEPARATED` qualification; quoted historical
framing) plus paragraph/code-block boundaries and line mapping.

---

## 1. Execution table, as applied

| id | old location | old role | change performed | frozen evidence used | numeric content changed? | claim strength changed? |
| --- | --- | --- | --- | --- | --- | --- |
| **7** | none | no figures existed | five SVG figures generated from frozen CSVs and placed in §4.1, §5, §6, §7.3, §7.4 with scoped captions | `scaling.csv`, `U85_GROUP_DIFFERENTIAL.csv`, `U85_P1B_CROSSMODE_GROUPS.csv`, `normalized_relative_cost.csv`, `X3_METRIC_QUALIFICATION.csv` | no — every value is plotted as frozen | no |
| **8** | §4.6, nested in the RQ1/RQ2 section | robustness study read as an undeclared RQ | promoted to **§5 "Validity of the structural metrics across platform and timing conditions"**, ahead of hardware validation, opening with an explicit *"This section answers no research question"*; §5→6, §6→7, §7→8, §8→9 | — | no | no |
| **9** | §4.6, §5, §6.6 | interpretation inside Results | CLASS B licensing, board "what this establishes", and the mechanism framing moved to §8 Discussion; Results keep the observation plus a one-line pointer; §7.6 became "Summary of the mechanism measurements" | — | no | no |
| **10** | §8, flat 14-item list | read as self-invalidation | regrouped under six themes (§9.1–9.6) with an orienting paragraph; **all 14 preserved verbatim in substance, none withdrawn or softened** | — | no | no |
| **11** | §2 Background | reader met four subsystems before knowing their roles | one paragraph distinguishing primary measurement substrates from diagnostic substrates, pointing to §3.1 and §9.1 | frozen platform roles | no | no |
| **12** | §5 (code block) | metric hierarchy stated only in prose | X3 categories rendered as a table beside the results, including tested universe and agreement counts | `X3_METRIC_QUALIFICATION.csv` | no — counts copied from the frozen CSV | no |
| **13** | §3.2, §3.5, §7.1, header | four minors | mi1 workload estimate table added; mi2 V13–V15 now points at the frozen evidence directory; mi3 scope clause added; mi4 header updated with figure provenance | `vela_matrix.csv` | **yes — see §2 below** | no |
| **14** | — | — | all suites re-run; manuscript re-frozen under a new tag; no existing tag moved | — | no | no |
| **F12** | absent | no Conclusion | §10 Conclusion written **last**, after 7–13 were stable | existing results only | no | no |

---

## 2. The one numerical discrepancy found

**§3.2's "467× span" did not reproduce from any frozen artifact.**

Tracing it: the figure appears in `docs/paper/MAIN_EXPERIMENT_MATRIX.md`, a
**pre-sweep planning document**, whose per-model Vela estimates are close to but
not identical with the frozen acquisition matrix
(`evidence/vela-matrix-20260824/vela_matrix.csv`). No row in the frozen matrix
reproduces the planning document's values — for example `rnnoise_INT8` is 37,922
there and 37,836 in the frozen matrix — and no configuration in the frozen
matrix yields a span of 467×.

Resolution, `EXISTING_DATA_ONLY`: §3.2 now carries the per-workload table the
claim rests on, computed from the frozen matrix at one named configuration
(`SSE-320 / ethos-u85-256 / Dedicated_Sram`, the configuration where all seven
workloads are present and which matches the planning document's stated
`ethos-u85-256` basis), and states the span as **468×**.

- This is the same metric — the ratio of the largest to the smallest frozen
  `vela_cycles_total` — read from the frozen artifact instead of the planning
  document. No new metric, and no frozen metric was regenerated with modified
  code.
- The figure is descriptive, not load-bearing: no result, threshold or
  conclusion depends on the workload span. It states that the workload set has
  wide dynamic range.
- **This is a provenance correction, not a scientific contradiction.** It did
  not require returning to manager review under the Phase-2 stop rule.

---

## 3. Figures

Five figures, all `EXISTING_DATA_ONLY`. Generated by
`docs/paper/figures/make_figures.py`, which emits SVG directly — no plotting
dependency, deterministic byte-for-byte output (verified by re-running and
comparing digests), and every plotted number greppable in the file. **There is
no spreadsheet or manual copy step anywhere in the chain**; the script re-derives
each figure from the frozen CSV on every run, and per-figure provenance is
recorded in `docs/paper/figures/FIGURE_PROVENANCE.json`.

| figure | section | source (frozen) | claim supported | interpretation refused |
| --- | --- | --- | --- | --- |
| 1 MAC scaling | §4.1 | `analysis/scaling.csv` | scaling is workload-dependent and mostly sub-proportional | reading across panels as a cross-generation performance comparison — panels share no absolute axis |
| 2 U85 group delta | §7.3 | `mechanism/U85_GROUP_DIFFERENTIAL.csv` | the reversal is distributed across operation groups | any single bar as *the cause*; per-operation attribution inside a merged window |
| 3 cross-memory robustness | §7.4 | `mechanism/U85_P1B_CROSSMODE_GROUPS.csv` | direction invariant across memory modes, magnitude not | attributing modulation to bandwidth — the modes are different artifacts |
| 4 board relative cost | §6 | `analysis/board_rq3/normalized_relative_cost.csv` | ordinal structure and cost shape transfer to the one hardware point | any error, ratio, accuracy or deviation reading between the two bars |
| 5 platform sensitivity | §5 | `platform_sensitivity/X3_METRIC_QUALIFICATION.csv` | ordinal metrics robust, thresholded class TA-state sensitive | pooling CLASS A with CLASS B; any platform performance ranking |

The refusals in column five are enforced in the generator itself, not left to the
caption: the script contains no code path that places two platforms' raw cycles
on one axis or computes an FVP-versus-board difference.

Geometry was audited programmatically (no element or text run exceeds its
canvas) and two figures were additionally rendered and inspected visually.

---

## 4. Tables

Ten tables before, nine after. Full classification in
`FINAL_FIGURE_TABLE_AUDIT.md`.

- **KEEP_MAIN (7)** — platform roles (§3.1), workload estimates (§3.2),
  three-kinds-of-number (§3.3), compilation paths (§3.4), efficiency class
  counts (§4.1), X3 qualification (§5), memory-mode totals (§7.4).
- **MERGE_MAIN (1)** — the §5 CLASS A/B agreement table was subsumed by the X3
  qualification table, which carries the same counts plus the qualification.
  Genuine redundancy, not an inconvenient result.
- **MOVE_APPENDIX (2)** — the board rank-pair table and the normalized-cost
  table moved to **Appendix A**, where their exact values are preserved for
  reproducibility, with a pointer left in §6. Figure 4 now carries the shape.
- **REMOVE_REDUNDANT (0)** — nothing was deleted.

**One regression was caught by the checks during this step.** The MERGE_MAIN
edit removed the sentence *"The two classes are reported separately and are not
combined into a single rate"*, a load-bearing invariant. Consistency check 14
and the X1/X3 scope validation both failed; the sentence was restored into the
merged text rather than the check being weakened.

---

## 5. Results / Discussion separation

Audited after figure integration. Results (§4, §5, §6, §7) now state what was
observed — counts, rankings, directions, frozen classifications — and defer
interpretation with an explicit pointer. Discussion (§8) received:

- the mechanism framing formerly in §6.6, including the emergence diagram and
  the retired single-factor ublock account;
- what the board comparison establishes, and what it does not;
- the licensing statement for the eight CLASS B disagreements.

The priority audit areas named in the decision were each checked: U85 mechanism
(§7 now measurement-only, framing in §8), TA/platform sensitivity (§5
observation, §8 interpretation), U55/U65/U85 structural contrast (§4.5 states
per-axis outcomes without causal language), memory-mode interpretation (§7.4
observation, `NOT_SEPARATED` retained in both places), board validation (§6
observation, §8 interpretation).

---

## 6. Conclusion (F12)

Written last, after 7–13 were stable, as instructed. §10 answers the RQs in the
priority order the decision specified: workload-dependent sub-linear scaling;
structural stability versus thresholded labels; the distributed U85 mechanism
with ublock insufficient as an explanation; the distinct evidentiary roles of
compiler estimate, FVP observation and physical observation; and board
validation as order preservation rather than timing accuracy.

Verified by check: it introduces **no new number** (its numeric set is a subset
of the preceding text), **no novelty claim**, and **no future-work promise
phrased as a current result**. Limitations are compressed to two sentences
pointing at §9 rather than restated.

---

## 7. Validation

| suite | checks | result |
| --- | --- | --- |
| `phase1_consistency_check.py` | 16 | **16/16 PASS** |
| `phase1_5_validation.py` | 25 | **25/25 PASS** |
| `phase2_validation.py` | 98 | **98/98 PASS** |
| `manuscript_text_fixtures.py` | 14 | **14/14 PASS** |
| `phase1_5_checker_fixtures.py` | 14 | **14/14 PASS** |

`phase2_validation.py` re-derives every load-bearing number from the frozen
output artifacts and compares it against the text: formal counts (74 cells / 222
samples / 74-of-74 determinism, and the derivation 74 = 77 TA-ON − 3
non-executable), 21 ladders and 53 adjacent transitions recomputed from
`scaling.csv`, the scaling-class rows, saturation (19/21 `NONE_OBSERVED`,
observed exactly once, at SSE-320/U85/`rnnoise`@512), Vela agreement 19/20 on
both criteria, board 7 workloads / 21 samples / `rho = 1.0` / 0 inversions and
all fourteen appendix values to four decimals, the U85 14-group partition
summing to +19,060 with 10/1/3 directions, cross-memory totals
3,015 / 15,075 / 19,060 with 27-of-29 direction-consistent and zero flips, the
X1/X3 agreement counts including 24/32 and the eight disagreements, CLASS A
14/14, all six bridge component verdicts, and 133 compiled / 6 non-executable
with the six confirmed as `wav2letter` × U55 × `Shared_Sram`.

It also runs the nine-item prohibited-claim scan with negation awareness, and a
reader-flow audit (contiguous numbering 1–10, every pointer resolves, every
figure embedded and captioned and referenced, every RQ declared before it is
answered, terminology consistency, appendix pointer present).

**Two validator defects were found and are recorded rather than silently fixed:**
`executability.csv` uses a `classification` column, not an `executable` boolean;
and the conclusion-versus-body number comparison normalized only one side, so
`"53\n"` did not match `"53 "`. Both were validator bugs, not manuscript
defects — the same hard-wrap family the shared normalization layer exists to
end, which is why the second one is noted here as a lesson rather than a
one-off.

---

## 8. Scope not touched

X2, X4, X5 remain HOLD; no new measurement, metric, or reanalysis. Abstract,
thesis, RQ wording and the contribution hierarchy were not stylistically
rewritten — the only change touching them is action 8's renumbering, which
affects pointers and not claims. No frozen evidence artifact under
`analysis/`, `mechanism/`, `platform_sensitivity/`, or `evidence/` was modified;
figures read them and never write them.

**Verification level: syntactic and automated consistency, validation and
numerical-integrity checking against frozen artifacts, with visual inspection of
two rendered figures.**
Executed: the five suites above (167 checks total); figure determinism verified
by digest comparison across runs; figure geometry audited; two figures rendered
and inspected; every load-bearing number re-derived from frozen CSV/JSON.
Not executed: no build, simulation, FVP run, board run, or measurement; no
frozen analyzer was re-run; no external peer review.
