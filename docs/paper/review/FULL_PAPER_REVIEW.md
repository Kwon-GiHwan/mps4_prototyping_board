# Full-paper review — `paper-manuscript-x3-integrated` = 08436d2

Review only. No manuscript text was edited, no data collected, no frozen
evidence altered, no claim silently repaired.

# Overall verdict

**`READY_WITH_MAJOR_TEXT_EDITS`**

Every defect found is fixable with text or with figures drawn from already
frozen data. No finding requires reanalysis of raw evidence, and none requires
a new experiment. The scientific content is in good order; the *paper* is not
yet a paper — it has no abstract, no citations, and no figures.

```
BLOCKER 1 · MAJOR 6 · MODERATE 5 · MINOR 4
fixes: TEXT_ONLY 10 · EXISTING_DATA_ONLY 2 · NEW_EXPERIMENT 0
```

# Central thesis

**`CURRENT_THESIS`** — implicit and scope-shaped rather than claim-shaped. The
introduction says the work "characterizes that decision space and then examines
one anomaly inside it in depth". That is an agenda, not a thesis; a reader
finishes §1 without knowing what the paper argues.

**`RECOMMENDED_THESIS`** — supported verbatim by the frozen results:

> Increasing MAC capacity does not yield proportional performance gains;
> scaling behaviour is workload-dependent and can become non-monotonic, is
> shaped by operation-level and memory/compiler interactions rather than by any
> single structural change, and structural conclusions transfer across tested
> platform and timing conditions far better than raw or thresholded
> performance labels.

Each clause is already evidenced: §4.1 (28 STRONG / 23 PARTIAL / 2 WEAK over 53
steps), §6.3–§6.4 (distributed reversal, same groups across memory modes),
§4.6/§7 (ordinal transfers, threshold class does not).

**`STORY_COHERENT = PARTIAL`.** The parts are individually disciplined and
mutually consistent; the spine connecting them is missing from the front
matter. `STORY_DILUTION` is **flagged but mild**: seven candidate stories exist,
and the contribution list is where the dilution shows (see MAJOR-4), not in the
body, which keeps validation work subordinate.

# Strongest contributions

1. **The U85 256→512 mechanism study.** A genuine anomaly, decomposed with a
   purpose-built and separately qualified instrumentation path, answered with a
   non-obvious result (distributed, same groups across memory modes, ublock
   non-discriminative). This is the paper's most defensible novelty.
2. **Executability as a first-class result.** All 133 cells compile, 6 cannot
   run; "compiler acceptance is not deployability" is a reusable finding.
3. **Measurement-validity work.** The TA discovery, the three compilation
   paths, the U65 instrumentation bridge and the X1/X3 platform-sensitivity
   study together give the paper an unusually honest evidential base.

# Blockers

**B1 — No citations and no References section.** *(§2 "Related work" is a
single uncited paragraph; the document contains zero references.)*
Evidence source: the manuscript itself. Why blocking: a systems/performance
paper cannot be assessed for novelty or positioned against prior NPU
characterization, simulator-validation, or operator-level profiling work
without a bibliography; reviewers will stop here. Required correction: write a
real related-work section with citations, covering at minimum NPU/accelerator
characterization studies, simulator-vs-hardware validation, and per-layer
profiling methodology, and cite the Arm toolchain artefacts (Vela, MLEK,
Corstone/FVP, Ethos-U TRM material) used as authorities. Correction type:
**`TEXT_ONLY`**.

# Major issues

**M1 — No abstract.** The document begins with a provenance note and goes
straight to §1. Required: a ~150-word abstract stating the thesis, the scale
(133-cell capability universe, 74-cell/222-sample sweep, 21 board samples,
92-cell platform validation), the headline results and the refusals. **`TEXT_ONLY`**.

**M2 — No figures.** 47 table rows, zero figures. The scaling ladders,
normalized-cost vectors (FVP vs board), per-group cross-memory deltas, and the
CLASS A/B agreement structure are inherently visual and currently force the
reader to reconstruct shape from numbers. Required: 3–5 figures generated from
the frozen CSVs; every caption must scope the evidence and must not encourage
cross-platform raw-cycle reading. **`EXISTING_DATA_ONLY`**.

**M3 — RQ1 promises more than the evidence permits.** *§1: "How do performance
characteristics change across Corstone/Ethos-U generations…"* versus §4.5,
§8.2 and §8.3, which refuse absolute cross-generation comparison, leave only
two `TA_ON` substrates (SSE-300, SSE-320) that additionally differ in Fast
Models version, and scope the one available same-platform NPU pair down to a
system-level configuration comparison. Why too strong: a reader takes RQ1 as a
performance question and receives a structural answer. Required correction:
reword RQ1 to what is answered — e.g. *how do normalized scaling behaviour,
workload ordering and deployability differ across the supported
Corstone/Ethos-U configurations* — and state the refusal at the point of
asking, not only in Limitations. **`TEXT_ONLY`**. (This is also the only place
where a reader could think X2 is owed; see `X2_NECESSITY_DECISION.md`.)

**M4 — The contribution list is disproportionate and incomplete.** The
Vela-prediction characterization is a Results subsection (§4.2) *and* a
Discussion headline, yet appears in no contribution; board validation occupies
a primary slot although its role is validation of one cell; contribution 4
bundles four distinct methodology results plus the entire platform-sensitivity
study. Required correction: restructure to primary vs validation, e.g. primary
= (i) systematic MAC-scaling characterization including executability, (ii) the
U85 operator-level mechanism study, (iii) compiler-estimate characterization;
validation/support = board validation, platform-sensitivity robustness,
instrumentation bridge. **`TEXT_ONLY`**.

**M5 — Platform roles are never stated in one place.** See
`PLATFORM_ROLE_AUDIT.md`. The TA split, the benchmarking-valid subset and the
validation-only role of TA-OFF platforms are distributed across §3.1, §3.7,
§8.1 and §8.2, and no table maps platform → NPU → TA → role. Required: one
compact role table in §3.1 plus a sentence distinguishing primary measurement
substrate from diagnostic/robustness substrate. **`TEXT_ONLY`**.

**M6 — No thesis sentence.** The introduction states scope, not a claim, so
the reader has no spine to hang seven evidence bodies on. Required: add the
recommended thesis (above) to §1 and echo it in the abstract. **`TEXT_ONLY`**.

# Moderate issues

**Mo1 — §4.6 is nested inside the RQ1/RQ2 section it validates.** The
robustness study does not answer RQ1 or RQ2; placing it under "Cross-generation
simulated characterization" invites reading it as an undeclared RQ. Recommend
promoting it to its own short section (e.g. §5 "Validity of the structural
metrics") ahead of board validation, keeping its non-RQ status explicit.
`TEXT_ONLY`.

**Mo2 — Interpretation appears inside Results.** §4.6 carries the
`ASSOCIATED_WITH` reasoning and the qualification list; §5 asserts what the
board comparison "establishes"; §6.6 is explicitly a framing subsection inside
the mechanism results. The wording is disciplined, but the Results/Discussion
boundary is blurred. Recommend moving the interpretive paragraphs to §7 and
leaving pointers. `TEXT_ONLY`.

**Mo3 — Limitations are a flat 14-item list.** Content is necessary and
correctly scoped, but the format reads as self-invalidation. Recommend grouping
under six headings: simulation validity · platform comparability ·
instrumentation paths · PMU semantic coverage · board scope · causal
identifiability. `TEXT_ONLY`.

**Mo4 — §2 Background lacks the platform/TA framing that §3.1 assumes.** The
TA explanation is good, but the reader meets the four subsystems before knowing
their roles. `TEXT_ONLY`.

**Mo5 — No table or caption carries the metric hierarchy.** §4.6 and §7 state
it in prose; a reader scanning tables sees ranking, direction, saturation,
class and raw cycles with equal apparent weight. Recommend one qualification
table (the X3 categories) placed with the results. `TEXT_ONLY`.

# Minor issues

- **mi1** The "467× span" (§3.2) is asserted without the per-workload estimate
  table that supports it. `TEXT_ONLY`.
- **mi2** §3.5 names the V13–V15 campaigns and refers to appendix material that
  does not exist in this document. `TEXT_ONLY`.
- **mi3** §6.1 says "exactly one workload becomes slower" and then adds that
  `dnn_s` also regresses on a separate track; one clause would remove the
  apparent contradiction. `TEXT_ONLY`.
- **mi4** The header says "Assembled 2026-09-02" although the document now
  carries the X1/X3 integration of 09-04. `TEXT_ONLY`.

# RQ closure

See `RQ_CLOSURE_MATRIX.csv`. RQ2, RQ3, RQ4 close cleanly. RQ1 closes only in
structural terms and is marked PARTIAL because of its wording (M3), not because
of missing evidence. The X1/X3 work is correctly *not* an RQ; its placement is
the only thing that risks making it look like one (Mo1).

# Evidence hierarchy

Traceability is strong: the header names the frozen tags, and every quantitative
claim audited in `CLAIM_EVIDENCE_AUDIT.csv` resolves to a frozen artifact. Three
claims were re-derived from raw evidence during this review — the 92/276 counts,
the CLASS A 14/14 cycle equality, and the X3 agreement counts — and all
reproduced exactly. No claim was found that outruns its evidence, with the
single exception of the RQ1 wording (M3).

# Platform-role review

See `PLATFORM_ROLE_AUDIT.md`. No prohibited implication was found: nothing
suggests later-Corstone-is-better, comparable raw cycles, TA_OFF as a
memory-aware substrate, SSE-315 as the uniquely correct U65 substrate, or
SSE-310/315 as silicon references. The defect is presentational (M5), not
semantic.

# U85 mechanism review

All frozen results are reflected: direct profiling exists; the rnnoise
regression is distributed across ten groups; the same logical groups regress in
all three memory modes; vww4 shows local regressions inside a net improvement
and 11 direction-flipping groups; ublock alone is non-discriminative and
block-config alone insufficient; the whole-model effect is framed as the
aggregate of heterogeneous group gains and losses; compiler and memory effects
remain `NOT_SEPARATED`; stall-family attribution remains `NOT_EVALUABLE`.

No sentence claims "we identified the cause", "memory bandwidth caused",
"ublock caused" or names a single operator as cause. Mixed-window attribution
is correctly phrased as "the multi-operation execution group containing …".
**PASS**, with the placement caveat in Mo2.

# Board-validation review

Reports only what was measured: 7 workloads, 21 formal samples,
`median(B1,B2,B3)`, `rho = 1.0` with 0 inversions, and the two normalized
vectors side by side with no aggregate deviation statistic. The protocol
supersession (3×10 → 3×1) is disclosed in the body rather than buried. No
sentence claims FVP accuracy, latency prediction, or cycle matching; absolute
comparison is explicitly refused and the target-specific build difference is
given as the reason. **PASS**.

# Instrumentation review

The three compilation/instrumentation paths are stated in a table in §3.4 and
used consistently thereafter, including the explicit statement that historical
U55/U65 per-layer evidence is *not* an exact decomposition of the frozen regor
executable. The U65 bridge keeps its preregistered overall verdict
`NOT_EQUIVALENT` together with all six component conclusions and is never
collapsed into "the profilers are equivalent"; the permitted scope
(cycle-domain and execution-boundary, under tested U65 conditions) and the
excluded scope (exact memory-traffic comparison, cross-generation PMU
equivalence) are both stated. **PASS**.

# X2 necessity

**`X2_NOT_NEEDED`** — full reasoning in `X2_NECESSITY_DECISION.md`. No
conclusion depends on a controlled same-platform U55/U65 comparison; the only
apparent dependency is the RQ1 wording, and that is closed by text. X2 would
not change what the paper is allowed to conclude.

# Suggested paper structure

```
Abstract                                     (new — M1)
1 Introduction        thesis + RQs (RQ1 reworded — M3, M6)
2 Background          Ethos-U, Corstone, timing adapter, platform roles (Mo4)
3 Methodology         3.1 platforms + ROLE TABLE (M5) · 3.2 workloads
                      3.3 measurement semantics · 3.4 compilation paths
                      3.5 measurement-boundary qualification · 3.6 provenance
                      3.7 platform-sensitivity validation design
4 Simulated characterization (RQ1, RQ2)      scaling, Vela, ranking, executability
5 Validity of the structural metrics         (promoted from §4.6 — Mo1)
6 Hardware validation (RQ3)
7 Operator-level mechanism study (RQ4)       observations only (Mo2)
8 Discussion                                 all interpretation, incl. metric hierarchy
9 Limitations                                grouped into six themes (Mo3)
References                                   (new — B1)
```

# Final action sequence

See `REVIEW_ACTION_PLAN.md` for the ordered list with owners and types. In
brief: B1 → M1/M6 → M3 → M4/M5 → M2 → Mo1/Mo2 → Mo3/Mo4/Mo5 → minors, then
re-freeze the manuscript and re-run the consistency checks used at X3
integration.
