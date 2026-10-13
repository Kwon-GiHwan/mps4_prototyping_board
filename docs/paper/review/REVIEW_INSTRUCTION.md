# Full-paper review instruction (manager, 2026-09-04) — REVIEW ONLY

Authoritative manuscript: `paper-manuscript-x3-integrated` = 08436d2
State: X0/X1/X3 ACCEPTED-FROZEN; X2/X4/X5 and new measurements HOLD.

**Prohibited in this task**: starting X2, collecting data, editing
MANUSCRIPT.md, changing frozen evidence, adding metrics or RQs, silently
repairing claims while reviewing.

**Purpose**: (1) logical coherence; (2) claim-to-frozen-evidence support;
(3) correctly scoped SSE-300/310/315/320 roles; (4) whether X2 is
scientifically necessary before submission; (5) required edits, if any.

## Review order and finding classes

Order: A central thesis · B RQ structure · C evidence hierarchy ·
D experimental validity · E causal-claim discipline · F platform/comparability
semantics · G result-to-discussion consistency · H contribution
proportionality · I limitations · J presentation cohesion.

Classes: BLOCKER / MAJOR / MODERATE / MINOR / PASS. Every BLOCKER/MAJOR must
carry: section, exact claim or paraphrase, evidence source, why it is too
strong/unsupported/confusing, required correction, and correction type
(`TEXT_ONLY` / `REANALYSIS_EXISTING_DATA` / `NEW_EXPERIMENT`).

## Mandated audits

2. **Central story** — report `CURRENT_THESIS`, `RECOMMENDED_THESIS`,
   `STORY_COHERENT = YES/PARTIAL/NO`; flag `STORY_DILUTION` if too many
   co-primary stories (MAC scaling, Vela prediction, U85 mechanism, memory
   robustness, board validation, platform sensitivity, instrumentation).
3. **RQ audit** — RQ → METHOD → EVIDENCE → RESULT → CONCLUSION; check
   numbering drift, result/question mismatch, X1/X3 becoming an undeclared RQ,
   board-vs-Vela confusion, U85 scope inflation. Keep X1/X3 as robustness
   validation by default.
4. **Platform roles** — SSE-300 (U55/U65, TA_ON, primary memory-aware),
   SSE-310 (TA_OFF, diagnostic/sensitivity control), SSE-315 (U65, TA_OFF,
   diagnostic reference), SSE-320 (U85, TA_ON, primary + board anchor). Flag
   any wording implying a single absolute-performance ranking series, "later
   Corstone = better", comparable raw cycles, TA_OFF ≡ memory-aware platform,
   SSE-315 as the uniquely correct U65 substrate, or 310/315 as silicon
   references.
5. **TA semantics** — preserve the four TA states; X1/X3 qualifications;
   forbid "TA caused"; allow only the association wording; CLASS B remains
   TA/subsystem/FM `NOT_SEPARATED`; CLASS A stated only as
   `NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR`.
6. **Cross-generation causality** — audit every U65-core-replication vs
   U85-block-enlargement instance; established-fact claims prohibited;
   classify X2 necessity as `X2_NOT_NEEDED` / `X2_OPTIONAL_STRENGTHENING` /
   `X2_RECOMMENDED` / `X2_REQUIRED` using the manager's rules. Do not
   authorize X2 here.
7. **U85 mechanism** — verify the frozen P0/P1 result is reflected and flag any
   "we identified the cause" / "memory bandwidth caused" / "ublock caused" /
   "Conv2D X caused" where the unit is a mixed operation group.
8. **Compiler-path / instrumentation** — three-path distinction consistent;
   historical U55/U65 per-layer evidence must not be described as the exact
   decomposition of the frozen regor executable; U65 bridge must keep overall
   `NOT_EQUIVALENT` with its component conclusions and must not collapse into
   "the profilers are fully equivalent".
9. **Board validation** — only what was measured (7 workloads, 21 samples,
   median(B1,B2,B3), rho = 1.0, 0 inversions, normalized structure). Flag any
   FVP-accuracy/latency-prediction phrasing unless explicitly negated.
10. **Vela/FVP** — keep estimate / simulated / physical distinct; no raw
    cross-generation performance comparison; X0 correction preserved.
11. **Metric hierarchy** — stronger structural metrics vs condition-sensitive
    threshold class vs unqualified raw cycles vs generation-specific PMU;
    check tables and captions too.
12. **Results/Discussion separation** — Results reports observations;
    Discussion interprets; Limitations states what remains inseparable.
13. **Contributions** — classify PRIMARY / SUPPORTING / VALIDATION; report
    whether the list should be reduced or reworded.
14. **Limitations** — necessary and scoped, not an invalidating list;
    recommend grouping only.
15. **Figures/tables** — per item: question answered, evidence source, whether
    axes/labels imply an invalid comparison, caption scoping, redundancy. Flag
    anything encouraging cross-platform raw-cycle ranking.

## Outputs (create under `docs/paper/review/`)

`FULL_PAPER_REVIEW.md` (fixed structure: overall verdict; central thesis;
strongest contributions; blockers; major; moderate; minor; RQ closure;
evidence hierarchy; platform-role review; U85 mechanism review;
board-validation review; instrumentation review; X2 necessity; suggested
paper structure; final action sequence), `CLAIM_EVIDENCE_AUDIT.csv`,
`RQ_CLOSURE_MATRIX.csv`, `PLATFORM_ROLE_AUDIT.md`,
`X2_NECESSITY_DECISION.md`, `REVIEW_ACTION_PLAN.md`, `REVIEW_META.json`.

Overall verdict ∈ `READY_WITH_MINOR_EDITS` / `READY_WITH_MAJOR_TEXT_EDITS` /
`NEEDS_REANALYSIS` / `NEEDS_X2` / `NEEDS_NEW_EXPERIMENT`.

Action classes: `TEXT_ONLY` / `EXISTING_DATA_ONLY` / `X2` / `X4` / `X5` /
`OTHER_NEW_EXPERIMENT`; prefer the least expensive action that fixes the
scientific problem. X2 is recommended only if it would change what the paper
is allowed to conclude.

## Freeze / stop

Tag the review (`paper-full-review-frozen`), then STOP. Report to the manager:
overall verdict, BLOCKER count, MAJOR count, X2 necessity verdict, counts of
TEXT_ONLY / EXISTING_DATA_ONLY / NEW_EXPERIMENT fixes, top 5 issues, review
tag/hash.
