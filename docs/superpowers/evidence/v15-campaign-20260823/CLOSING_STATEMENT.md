# PMU_COMPLETION_S5_ONLY_CONTROL — closing statement

**Status: COMPLETE — 30/30 VALID.** Approved closing state, 2026-08-23.

## What was established

```
Preregistered outcome                              S1
submit_to_s5_observed_cycles floor                 754 cycles
  reproduced across                                3/3 independent boots
Excursions above floor                             PRESENT in 3/3 boots

Q-only and S5-only qualitative structure           BOTH SHOW REPRODUCIBLE
                                                   FLOOR + EXCURSIONS

Floor-plus-excursion structure specific to QREAD   FALSIFIED AS A NECESSARY
                                                   CONDITION
Dual-register polling required for the structure   FALSIFIED AS A NECESSARY
                                                   CONDITION

Common underlying mechanism                        NOT ESTABLISHED
Absolute Q-vs-S5 cycle comparison                  NOT PERMITTED
Intrinsic QREAD-vs-STATUS(bit5) visibility order   UNRESOLVED
Internal NPU completion timestamp                  NOT AVAILABLE

Task 11                                            E2E_REQUALIFIED
Production END_ONLY                                FROZEN
MLEK                                               BLOCKED
```

## On "falsified as a necessary condition"

This phrasing is doing precise work and is not a softened *falsified*.

It does **not** say "QREAD polling does not cause excursions." It says the
explanation *"the structure requires QREAD to be present"* no longer stands,
because the same kind of structure appeared independently in a path that never
reads QREAD. The same holds for dual-register polling.

Whether the two structures share a mechanism is a separate question, and the
answer is `NOT ESTABLISHED` — not "probably yes."

## The comparison that is not permitted

```
V14 Q floor    732 cycles
V15 S5 floor   754 cycles
```

Subtracting these is refused by rule
(`RULE_CROSS_VARIANT_ABSOLUTE_COMPARISON`), and the sentence it would license —
"STATUS becomes visible 22 cycles later than QREAD" — is refused by the
vocabulary guard.

`Q_S5_EQUIVALENT` is evidence that the two **control structures are matched**:
same loop shape, six instructions per iteration, same role sequence, compared
against the pinned V14 Q analysis reference. It is **not** evidence that cycle
counts taken against two different MMIO observables lie on one physical latency
axis. The difference of two such counts is a number with no established meaning.

What the two campaigns support is qualitative structural similarity, and nothing
past it.

## The sentence for the write-up

> Both QREAD-only and STATUS.cmd_end_reached-only matched controls exhibit a
> boot-reproducible lower observation mode with excursions above that floor.
> Therefore, the observed floor-plus-excursion structure is not specific to
> QREAD polling and does not require dual-register observation. However, the
> experiments do not establish a common underlying mechanism, and their absolute
> cycle values do not determine intrinsic QREAD-versus-STATUS visibility
> ordering.

Short form:

> The floor-plus-excursion structure reproduces under both single-register
> completion observables, while the underlying mechanism and intrinsic
> QREAD-versus-STATUS ordering remain unresolved.

## Evidence

| | |
| --- | --- |
| campaign | `v15-campaign-20260823/` — 30/30, frozen before analysis |
| verdict | `verdict.json` — S1 |
| Task 11 | `task11_final.json` — E2E_REQUALIFIED |
| restore + postflight | `postflight.json` |
| anchors | `v15-preboard-anchor`, `v15-board-preflight-passed`, `v15-postdeploy-precampaign-anchor`, `v15-campaign-evidence-frozen`, `v15-campaign-complete` |
