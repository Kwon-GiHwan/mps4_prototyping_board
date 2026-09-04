# Submission-ready gate — review only

**Subject:** `paper-manuscript-submission-ready` = d137a7d
**Input:** `paper-manuscript-submission-candidate` = a990e03
**Finding source:** `paper-submission-readiness-frozen` = d2c5849 (NEW-1)
**Mode:** review only. The manuscript was not edited during this gate.

## Verdict

```
BLOCKER    0
MAJOR      0
MODERATE   0
MINOR      0

SUBMISSION_READY
```

## NEW-1 — CLOSED

Three sentences added, each in the paragraph immediately preceding its figure,
each summarizing only what the surrounding prose and the figure's own caption
already establish.

| figure | § | sentence | constraint honoured |
| --- | --- | --- | --- |
| 2 | 5 | "Figure 2 summarizes these agreement counts metric by metric, with the two classes drawn separately." | no raw cross-platform comparison, no TA-only causality, no new robustness metric |
| 4 | 7.3 | "Figure 4 shows how that change is distributed across the groups, and places the +19,000 whole-model observed delta beside the +19,060 profiled-group sum so that the 60-cycle residual between the two measurement boundaries stays visible." | the three quantities stay distinct; the two boundaries are not implied equal; §9.5's qualified residual semantics preserved |
| 5 | 7.4 | "Figure 5 shows those group deltas side by side across the three configurations, where the magnitudes move and the directions do not." | configuration intervention only; no bandwidth attribution |

None is a bare "See Figure X"; each states the figure's role.

| | |
| --- | --- |
| Figure 1 prose reference | **YES** (§4.1, pre-existing) |
| Figure 2 prose reference | **YES** (§5, added) |
| Figure 3 prose reference | **YES** (§6, pre-existing) |
| Figure 4 prose reference | **YES** (§7.3, added) |
| Figure 5 prose reference | **YES** (§7.4, added) |

## Narrow diff audit — EXPECTED

The diff against a990e03 is exactly the three sentences above. Two of them are
appended to existing lines, which is why those lines appear as a paired
removal/addition; the removed text is re-emitted verbatim. **No unrelated
manuscript edit is present**: no numerical value, metric definition, figure
datum, visual encoding, figure number, caption, RQ, thesis clause, contribution,
Results or Discussion interpretation, limitation, or reference was touched.

## Reconfirmed

```
figure caption order        1,2,3,4,5
figures referenced in prose 1,2,3,4,5
whole-model delta           +19,000
profiled-group delta        +19,060
residual                    60   (deterministic profiling-boundary /
                                  interrupt-service, Section 9.5)
468x provenance             present; the string 467 absent from the manuscript
RQ1-RQ4                     CLOSED
thesis                      3/3 supported (C2 bound to the boundary,
                                           C3 without the intensifier)
abstract                    READY (three primary findings, two validating)
X2                          NOT_NEEDED
```

```
rule failures               0
scientific contradictions   0
numerical discrepancies     0
new experiment required     NO
```

**Suites: 222 / 222** — 16 claim-discipline, 25 structural, 98 numeric-integrity
and reader-flow, 55 polishing (A–G), 28 fixtures.

## Checker changes, disclosed

**New group G** enforces the NEW-1 invariant: every main-text figure must carry
at least one explicit prose reference. Image insertions and caption blocks are
stripped before matching, and the stripping itself is asserted — a check
verifies that `**Figure 1.**` survives caption-only stripping but not the full
strip, so a caption can never satisfy the rule by accident. G also requires each
added reference to explain the figure's role and rejects a bare "See Figure X".

**Check C was tightened**, and this is worth stating plainly because it relaxed
a rule in order to let new text pass. The old pattern flagged any co-occurrence
of "whole-model … delta" and "19,060" within 40 characters. The Figure 4
reconciliation sentence names both numbers deliberately, in order to
*distinguish* them — the opposite of the MOD-2 defect — so the old rule produced
a false positive. C now fires only on an *equating* construction
(`whole-model … delta is/was/=/of +19,060`) with no distinguishing connective
nearby, and it carries **two inline assertions**: that it still fires on the
original MOD-2 sentence, and that it does not fire on the reconciliation
sentence. The rule was not simply loosened; it was made to discriminate, and its
ability to fail is proven in the same run.

## Final state

| | |
| --- | --- |
| words | 9,243 |
| sections | 10 + 2 appendices |
| figures | 5, all captioned and all referenced in prose |
| tables | 9 (+2 in Appendix A) |
| references | 17 |

## Recommendation

**`SUBMISSION_READY`.** No blocker, major, moderate or minor finding remains.
Every RQ closes, every load-bearing number traces to a frozen artifact, every
refused comparison is still refused, and every figure is now reachable from the
prose that depends on it.

No optional stylistic preference has been recorded as a finding.

Nothing here reopens X2, X4 or X5, and nothing requires new measurement.

**Verification level: static analysis and automated checking of the frozen tag.**
Executed: all six suites at d137a7d; line-level diff audit against a990e03;
independent reconfirmation of figure order, prose-reference coverage, the three
delta semantics, the 468× correction, RQ set, thesis clauses and abstract
tiering.
Not executed: no build, simulation, FVP run, board run, or measurement; no
frozen analyzer re-run; no external peer review; no repository push.
