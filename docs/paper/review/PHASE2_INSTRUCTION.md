# REVIEW REMEDIATION PHASE 2 — MANAGER GO (recorded scope + execution table)

Authoritative manuscript : `paper-manuscript-phase1_5-frozen` = 6dce4d8
Authoritative P1.5 review: `paper-manuscript-phase1_5-review-frozen` = 983ef04
Authoritative full review: `paper-full-review-frozen` = 9359c7a

## Decisions
- Phase-1.5 ACCEPTED / FROZEN; REVIEW_ACTION_PLAN 7–14 **GO**
- X2 / X4 / X5 HOLD; new measurements HOLD; new experimental metrics HOLD
- Evidence campaign complete unless a genuine contradiction appears that existing
  frozen evidence cannot resolve → then STOP and return to manager review.
- **F12 Conclusion is now AUTHORIZED**, written *last* among substantive sections.

## Allowed fix classes
`TEXT_ONLY` · `EXISTING_DATA_ONLY` · `REFERENCE_ONLY`.
Any action that turns out to need `NEW_EXPERIMENT`, `NEW_METRIC`, or
`REANALYSIS_WITH_NEW_DEFINITION` ⇒ **STOP**, return to manager.

## Execution table (read from the frozen REVIEW_ACTION_PLAN.md at 9359c7a — not from memory)

| id | description (frozen wording) | finding | dependency | manuscript sections affected | class |
| --- | --- | --- | --- | --- | --- |
| **7** | Generate 3–5 figures from frozen CSVs with scoped captions | M2 | none; but figures land in Results, so before 9 | §4, §5(new), §6, §7 | `EXISTING_DATA_ONLY` |
| **8** | Promote §4.6 to its own section ahead of hardware validation; keep the "not an RQ" statement explicit | Mo1 | **renumbers §5–§8**; must precede 9, 12, 13, 14 | §4.6 → new §5; old §5→§6, §6→§7, §7→§8, §8→§9 | `TEXT_ONLY` |
| **9** | Move interpretive paragraphs out of §4.6, §5 and §6.6 into Discussion; leave one-line pointers | Mo2 | after 8 (numbering) and 7 (figures placed) | new §5, §6, §7.6, §8 Discussion | `TEXT_ONLY` |
| **10** | Group the 14 limitations under six themes | Mo3 | after 9 | Limitations | `TEXT_ONLY` |
| **11** | Add platform/TA role framing to §2 Background (one short paragraph) | Mo4 | none | §2 | `TEXT_ONLY` |
| **12** | Add the X3 qualification table beside the results; reuse `X3_METRIC_QUALIFICATION.csv` categories | Mo5 | after 8 | new §5 | `EXISTING_DATA_ONLY` |
| **13** | Fix minors mi1–mi4 | minors | after 8 (numbering), 10 | §3.2, §3.5, §7.1, header | `TEXT_ONLY` + mi1 `EXISTING_DATA_ONLY` |
| **14** | Re-run consistency checks and re-freeze; new tag, do not move existing tags | — | last | — | `TEXT_ONLY` |
| **+F12** | Conclusion (authorized separately by this decision, §3) | F12 | **after 7–13 stable** | new final section | `TEXT_ONLY` |

Minor detail, from the frozen review:
- **mi1** §3.2's "467× span" is asserted without the per-workload estimate table.
- **mi2** §3.5 refers to V13–V15 appendix material that does not exist here.
- **mi3** §6.1 "exactly one workload becomes slower" vs the `dnn_s` separate track.
- **mi4** header date stale relative to the X1/X3 integration.

## Standing constraints carried into Phase 2
- Platform roles fixed (SSE-300 primary / SSE-310 diagnostic / SSE-315 diagnostic
  reference / SSE-320 primary U85 + board anchor). No prose or figure may reframe
  the four as one absolute-performance series.
- Architecture-only causality stays below the claim ceiling; do not broaden wording
  in any way that would make **X2 necessary again**.
- Abstract / thesis / RQ / contribution hierarchy are structurally accepted — no
  stylistic rewrite without a Phase-2 dependency and re-validation.
- References: maintenance only; preserve the Phase-1.5 U55/U65 primary sources and
  all verified metadata; fabricate nothing.
- Figures: frozen derived data only; no invented transformation; every figure needs a
  provenance record; no raw cross-platform cycle chart; no FVP-vs-board error plot.
- Tables: classify KEEP_MAIN / MERGE_MAIN / MOVE_APPENDIX / REMOVE_REDUNDANT; never
  drop a table because its result is inconvenient; preserve exact numbers for
  reproducibility if a figure supersedes a table.
- Limitations: regroup, never delete a genuine limitation.

## Required outputs
`docs/paper/review/`: `REMEDIATION_PHASE2.md`, `FINAL_CLAIM_EVIDENCE_AUDIT.csv`,
`FINAL_RQ_CLOSURE_MATRIX.csv`, `FINAL_FIGURE_TABLE_AUDIT.md`,
`FINAL_MANUSCRIPT_REVIEW.md`, `FINAL_REVIEW_META.json`. Figure sources/provenance
under a paper figure directory.

## Freeze sequence
1. `paper-manuscript-phase2-frozen` (manuscript remediation state)
2. final review **without editing**
3. `paper-final-review-frozen`
Do not move previous tags. Target: BLOCKER = 0, MAJOR = 0.
