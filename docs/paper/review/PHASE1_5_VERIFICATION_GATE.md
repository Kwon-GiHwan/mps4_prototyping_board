# PHASE-1.5 VERIFICATION GATE — verification only

**Subject:** `paper-manuscript-phase1_5-frozen` = 6dce4d8
**Predecessors:** f09bba6 (Phase-1 manuscript), 85aa4d5 (Phase-1 review)
**Mode:** verification only. Nothing was modified during this gate; the
manuscript and all scripts are byte-identical to the frozen tag.

This gate answers only the nine questions the manager specified.

| # | question | answer |
| --- | --- | --- |
| 1 | thesis clauses supported? | **YES — 3/3 SUPPORTED** |
| 2 | abstract ready? | **YES — `ABSTRACT_READY`** |
| 3 | RQ1 closed? | **YES — `RQ1_CLOSED`** |
| 4 | F4 contradiction removed? | **YES** |
| 5 | Related Work positioning valid? | **YES** |
| 6 | references resolved? | **YES — 17/17, both directions** |
| 7 | checker catches F4-style causality? | **YES — mutation-proven** |
| 8 | platform roles still coherent? | **YES — `PLATFORM_ROLES_COHERENT`** |
| 9 | new experiment needed? | **NO — 0** |

---

**1. Thesis clauses — 3/3 SUPPORTED.** C1 unchanged and already supported. C2 is
now bound to the studied boundary ("where it does become non-monotonic, that
transition is shaped by…"), matching evidence drawn from one workload at one
transition. C3 no longer carries the unpreregistered intensifier and no longer
ranks structural transfer against a raw layer that was never evaluated for
transfer; it states the threshold sensitivity and the `NOT_COMPARABLE` status
separately. Each clause traces to a result section, frozen evidence and a
limitation (table in `PHASE1_5_REMEDIATION.md`). No architecture-only causality
present.

**2. Abstract — `ABSTRACT_READY`.** Zero unsupported factual claims (all 15
figures traced in `PHASE1_THESIS_TRACE.csv` and re-checked by consistency check
08). Tiering is now legible: "Three primary findings follow" introduces MAC
scaling, U85 mechanism and Vela prediction; a separate lead-in — "Two results
validate these findings rather than extending them" — introduces platform
sensitivity and board ordering. Board validation and X1/X3 no longer read as
co-primary research questions. No number was added: the abstract's numeric set
is asserted to be a subset of the manuscript's.

**3. RQ1 — `RQ1_CLOSED`.** §4.5 now states the per-axis answer: deployability
differed (six non-executable cells, all `wav2letter_pruned_int8` × U55 ×
`Shared_Sram`), saturation differed (one U85 ladder), workload ordering did not
differ (`rho == 1.0` in 31/55, min 0.9429, median 1.0000). Chain complete:
RQ1 → §3.1/§3.3 → §4.1/4.3/4.4/4.5 → §7 → answer. Requires no absolute
cross-generation performance, no U65-vs-U85 controlled substrate, and no
architecture-only causality. Assembled from printed Results; no new metric, no
new computation, no X2.

**4. F4 — removed.** No occurrence of "purely by" or any equivalent survives.
§7(i) now records that TA state, subsystem and Fast Models implementation differ
together across the SSE-300/SSE-310 pair, that the magnitude *cannot be
attributed to the timing adapter alone*, that the three contributions are
`NOT_SEPARATED`, and that the observation is a methodology warning against raw
cross-platform cycle comparison rather than a performance result. This agrees
with §4.6 and §8.13; the contradiction between §7 and §8.13 is gone. The
methodology warning itself is preserved in full. §3.7's over-scoped "computed
anywhere" was narrowed to "computed in this validation". **No frozen X0/X1/X3
evidence document was edited** to achieve this.

**5. Related Work — valid.** The field-wide frequency claim is now attributed to
SCALE-Sim and Timeloop themselves. The capability-absence claim about TinyML
suites is replaced with positive positioning ("MLPerf Tiny reports system-level
outcomes by design, at whole-inference granularity; this work additionally
decomposes…"), and MicroNets is no longer swept into "such suites". No `first`,
`few`, `uncommon`, `less common`, or `no prior work` was reintroduced. The two
cross-reference errors in this section are repaired and semantically verified.

**6. References — 17/17 resolved**, every citation listed and every entry cited.
Added: [16] Ethos-U55 TRM (`102420_0200_02_en`, r2p0) and [17] Ethos-U65 TRM
(`102023_0000_06_en`, r0p0), both **content-verified from the documents
themselves** (`macs_per_cc` ranges quoted in the remediation record), not by
identifier resolution alone. Three boundaries hold: the TRMs are not made the
MAC admission authority (X0 `num_macs` correction preserved), U85 documentation
is not used as U55/U65 authority, and PMU event names are explicitly *not*
attributed to these manuals — the manuscript states they are established
empirically instead, so the unresolved authority is reported rather than
papered over.

**7. Checker — mutation-proven.** Check 16 flags causal isolation using a
confounded-subject plus exculpating-context predicate rather than a word
blacklist, so it distinguishes an affirmative claim from a negated, retired,
qualified or historically-quoted use of the same words. Run against f09bba6 it
FAILS and quotes the F4 sentence verbatim; run against 6dce4d8 it passes.
14 regression fixtures (6 must-fire, 8 must-not-fire) all pass.

**8. Platform roles — `PLATFORM_ROLES_COHERENT`.** The four-row §3.1 table is
intact and unchanged. No passage treats SSE-315 as an authoritative U65
performance platform. The one nearby prose statement that undermined the table's
discipline was §7(i), now corrected (question 4).

**9. New experiment — 0.** No scientific contradiction was found at this gate.
X2, X4, X5 remain HOLD; REVIEW_ACTION_PLAN items 7–14 remain HOLD.

---

## Outstanding, by prior decision

**F12 — no Conclusion section.** Deferred to Phase 2 per D2; no placeholder was
inserted. This remains the one structural gap in the manuscript and is the
reason the RQ traces terminate at their Discussion stage.

## Suite status at 6dce4d8

```
phase1_consistency_check.py     16/16 PASS   (15 Phase-1 + check 16)
phase1_5_validation.py          25/25 PASS
phase1_5_checker_fixtures.py    14/14 PASS
rule failures                   0
scientific contradictions       0
new experiments required        0
```

**Verification level: static analysis of the frozen tag.**
Executed: all three suites at 6dce4d8; mutation of check 16 against f09bba6;
independent greps for F4 residue, reference count, platform-table integrity;
semantic re-read of the thesis, abstract, §4.5 and §7(i).
Not executed: no build, simulation, FVP run, board run, or measurement; no
re-derivation of frozen analyzer outputs; no external peer review.
