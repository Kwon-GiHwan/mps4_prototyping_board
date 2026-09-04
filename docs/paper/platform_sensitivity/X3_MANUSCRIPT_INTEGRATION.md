# X3 → manuscript integration record

Authorized by the manager decision of 2026-09-04 (X1 and X3 ACCEPTED/FROZEN;
manuscript X3 update GO; X2/X4/X5 and new measurements HOLD). Only frozen
X0/X1/X3 evidence was used; no data was collected, no metric was added, and no
frozen analysis definition was changed.

## What was inserted, and where

| manuscript location | inserted content | source |
| --- | --- | --- |
| §3.7 *Cross-platform sensitivity validation design* (new) | same-artifact design (model/NPU/MAC/artifact fixed, platform varied), artifact-identity hard gate, `FIRMWARE_PLATFORM_SPECIFIC_BUT_NPU_ARTIFACT_IDENTICAL` wording, CLASS A/B split, 92-cell universe, acquisition semantics, and the explicit note that TA-OFF platforms enter as validation subjects rather than performance sources | X0 + X1 contract |
| §4.6 *Robustness of the structural metrics across tested FVP variants* (new) | the five-metric agreement table by class, the eight scaling-class disagreements, the CLASS A exact-cycle observation with its narrow classification, the TA association statement, and the category-only qualification list | X1 results + X3 synthesis |
| §7 Discussion (new paragraph) | metric hierarchy: ordinal/directional preserved, threshold class sensitive, raw cross-platform cycles outside the comparable set | X3 |
| §8.13 *Platform-sensitivity validation bounds* (new; previous 8.13 Scope renumbered 8.14) | no same-platform U65↔U85 pair; no TA_ON cross-FVP control; CLASS B TA/subsystem/FM `NOT_SEPARATED` | X3 limitations |
| Contribution 4 (extended, no new list item) | one compact statement of the same-artifact platform-sensitivity result | manager-approved phrasing |

No new research question was created: X1/X3 appear as a robustness/validity
study supporting the existing cross-platform interpretation.

## Interpretation constraints honoured

- Approved framing used verbatim in substance: *ordinal and directional
  conclusions were preserved across the tested platform pairs, whereas
  threshold-based scaling classes were more sensitive to timing-model
  configuration.*
- Approved TA statement used: *all observed scaling-class disagreements
  occurred in comparisons where TA state also differed*, with
  `ASSOCIATED_WITH`. No "TA caused", "Corstone caused", or "Fast Models
  caused" claim appears.
- CLASS A observation stated narrowly as
  `NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR`, with explicit
  non-generalization and `NOT_EVALUABLE` transfer to TA_ON.
- CLASS A and CLASS B are reported separately; no pooled statistic, no
  robustness score, percentage or index.
- No cross-platform raw-cycle ratio, "% faster/slower", platform ranking, or
  U65-versus-U85 absolute comparison was introduced; raw cycles remain
  evidence inputs, qualified `NOT_COMPARABLE`.
- The X0 factual correction is preserved: the manuscript does not claim the
  FVP checks only bounds and does not use the historical `num_macs=100`
  acceptance record.

## Cross-generation claim audit

The manuscript was scanned for architecture-causal wording. No instance of
"core replication is better than block enlargement", "U65 scales better because
it replicates cores", or "the U85 reversal is caused by block enlargement"
exists. The single occurrence of "ublock enlargement causes the regression"
appears only as the framing the mechanism study **retires**, and remains
labelled as such. X1/X3 strengthen the validity of structural comparison; they
do not establish architecture-only causality, and no claim was upgraded.

## TAG_CONSTRUCTION_CORRECTION

```
initial local tag/commit:  e4f45be
                           incomplete artifact set (X3_METRIC_ROBUSTNESS.md and
                           X3_META.json missing)
                           never published, never used as analysis authority
final authoritative tag:   paper-platform-sensitivity-x3-results-frozen = fabf3b5
```

The omission was detected immediately, the missing artifacts were written, and
the commit was amended before any publication or downstream use. `e4f45be` is
**not** a prior frozen result and must not be cited as one; `fabf3b5` is the
sole X3 authority. This record is kept here rather than inside the frozen X3
artifact set so that the frozen files themselves remain untouched after their
freeze.

## Freeze

Manuscript frozen as `paper-manuscript-x3-integrated`. Earlier manuscript tags
(`paper-manuscript-integrated`, `paper-manuscript-x0-correction-frozen`) are
left exactly where they are.
