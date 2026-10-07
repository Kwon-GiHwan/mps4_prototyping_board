# REMEDIATION PHASE 1 — traceability record

**Authorization:** MANAGER DECISION — FULL REVIEW ACCEPTED / REMEDIATION PHASE 1 GO
**Input baseline:** `paper-manuscript-x3-integrated` (08436d2)
**Review baseline:** `docs/paper/review/` frozen at 9359c7a
**Output freeze:** `paper-manuscript-review-phase1-frozen`
**Scope:** REVIEW_ACTION_PLAN items **1–6 only**. Items 7–14 NOT applied.
**Evidence status:** no new experiment, measurement, metric, threshold, or
correlation was introduced. Every number in the revised text was already present
in a frozen artifact; the revision is presentational and scoping only.

---

## 1. Actions applied, in dependency order

### Item 1 — Related Work and References (BLOCKER B1)

The single-paragraph placeholder in §2 was replaced by **§2.1 Related work**,
organized into four positioned groups, plus a new **References** section with
15 entries.

| group | citations | position taken |
| --- | --- | --- |
| accelerator characterization / scaling models | [9] TPU, [10] SCALE-Sim, [11] Timeloop | they model or measure a *design*; we characterize a deployment toolchain across a fixed IP's supported configurations |
| TinyML benchmarking | [13] MLPerf Tiny, [14] MicroNets, [15] TFLite Micro | system-level outcomes, no operation-level anomaly decomposition |
| simulator-vs-hardware validation | [12] Gutierrez et al., ISPASS 2014 | their claim is absolute-error validation; ours is deliberately weaker (ordinal/relative structure at one configuration) |
| Arm Ethos-U toolchain | [1]–[8] | primary evidence for the measured system, not related work |

**Citation-metadata discipline.** All 15 entries were verified against their
primary source during review (Arm documentation IDs resolved on
developer.arm.com; ML platform repositories resolved on review.mlplatform.org;
academic entries resolved to venue and arXiv identifier). **No author list,
venue, year, or identifier was inferred or reconstructed from memory.** Where a
detail could not be verified it was omitted rather than guessed — this is why
Arm entries carry a document ID rather than a fabricated publication date.

Two citations do real argumentative work rather than decoration:

- **[7]** — the Vela documentation's own labelling of its performance estimates
  as *experimental* is the external warrant for treating Vela output as a
  prediction to be tested (§7 / RQ-adjacent framing), not as ground truth.
- **[12]** — provides the field's reference point for what simulator validation
  normally claims, which is exactly what makes the narrower board claim in §6
  defensible rather than evasive.

**Novelty claim.** The pre-existing soft novelty sentence at old line 78
("validation against physical hardware, and operator-level decomposition of
anomalies, are less common") was **removed, not re-supported**. It is replaced by
a positioning paragraph that states what this work contributes *relative to the
cited literature* without any comparative-frequency claim about the field. The
consistency checker now rejects `to our knowledge`, `no prior work`, `the first
study/work/paper/to`, `we are the first`, `few studies/works`, `unprecedented`,
and `novel contribution` outright.

### Item 2 — Thesis sentence (M6)

A single labelled **Thesis** paragraph was inserted in §1 immediately after the
motivating paragraph. It asserts three things and nothing more: scaling is not
proportional to MAC capacity and can be non-monotonic; the mechanism is
heterogeneous and operation-level rather than a single structural cause;
structural conclusions transfer across tested conditions better than raw or
thresholded labels. Each clause is discharged by a numbered contribution and an
existing frozen result — no clause was written that the evidence does not
already carry.

### Item 3 — Abstract (M1)

A 299-word abstract was added ahead of §1. It is assembled exclusively from
frozen figures; every quantity was verified to appear in the corresponding
results section (consistency check 08):

| abstract figure | source section |
| --- | --- |
| 133-cell universe, 74 executable cells, 222 samples | §3, §4 |
| 53 adjacent transitions; 28 `STRONG`, 23 `PARTIAL` | §4 class table |
| saturation in one of 21 ladders | §4 saturation paragraph |
| +19,000 cycles, ten regressing groups | §6.3 |
| ~95 % ublock co-occurrence in every direction class | §6.3 |
| 19 of 20 ladders (Vela classification and ordering) | §7 |
| 21 board samples, ordering preserved | §5 |

The abstract closes with an explicit refusal paragraph (no absolute
cross-generation / cross-simulator / simulation-vs-hardware cycle comparison; no
single-factor attribution of the non-monotonicity), so the scope limits travel
with the abstract rather than being discoverable only in §8.

### Item 4 — RQ1 rescoping (M3)

RQ1 previously invited an absolute cross-generation performance comparison that
§3.3 forbids. It now asks about **normalized scaling behaviour, workload
ordering, and deployability** across supported configurations, and carries an
inline parenthetical stating that "which generation is faster" is deliberately
not asked and that no result depends on it. Consistency check 06 fails the
build if that phrase ever appears outside a negated context.

### Item 5 — Contribution hierarchy (M4)

The flat six-item list was split into **three primary contributions** and
**three validation/supporting results**, matching the review's finding that the
list did not distinguish load-bearing claims from scaffolding.

| tier | contribution | rationale |
| --- | --- | --- |
| primary 1 | systematic MAC-scaling characterization, executability as a first-class result | the study's breadth claim |
| primary 2 | operator-level mechanism study of the non-monotonic boundary | the study's depth claim, and the only one requiring purpose-built instrumentation |
| primary 3 | compiler-estimate characterization against simulation | the practitioner-facing claim |
| supporting 4 | physical-board ordering validation | validates, does not establish |
| supporting 5 | platform-sensitivity robustness (X1/X3) | robustness evidence for the primary claims — **explicitly framed as validation, not as a separate contribution** |
| supporting 6 | instrumentation qualification (U65 bridge) | bounds interpretation of 2 |

Methodology observations (a timing adapter silently changing what is measured; a
compiler backend change silently changing which program is instrumented) were
demoted out of the contribution list to a closing sentence, since they are
findings *about* measurement rather than results of the study.

### Item 6 — Platform role table (M5)

A four-row table was inserted in §3.1 assigning each simulated platform an
explicit role, with the operative distinction stated in prose: **primary
measurement substrate** (SSE-300, SSE-320) versus **diagnostic / robustness
substrate** (SSE-310, SSE-315), and the statement that the four platforms are
never presented as a single absolute-performance series.

| platform | NPU | TA | role |
| --- | --- | --- | --- |
| SSE-300 | U55, U65 | `TA_ON` | primary memory-aware simulated substrate |
| SSE-310 | U55, U65 | `TA_OFF` | diagnostic / platform-sensitivity control |
| SSE-315 | U65 | `TA_OFF` | U65-specific diagnostic reference substrate |
| SSE-320 | U85 | `TA_ON` | primary U85 substrate and hardware-validation anchor |

---

## 2. Invariants verified as preserved

The review required that six properties survive the rewrite. Each is enforced by
a consistency check rather than asserted:

| invariant | check |
| --- | --- |
| cross-generation comparison discipline | 06, 09 |
| X1/X3 presented as robustness validation, not as a headline result | item 5 restructure; 10 |
| U85 mechanism nuance (distributed, non-causal, ublock non-discriminating) | 12 |
| board validation scope (ordinal, one configuration) | 13 |
| frozen evidence vocabulary and CLASS A/B separation | 14 |
| frozen numeric results unchanged | 15 |

---

## 3. Consistency checks

Script: `docs/paper/review/phase1_consistency_check.py` (fail-closed, exit 1 on
any FAIL). Whitespace-normalized matching, because the manuscript is hard
wrapped and several prohibited phrases span line breaks; negation-context aware,
because the paper legitimately *refuses* many of the phrases a naive checker
would flag.

```
01 citations resolve                            PASS
02 no orphan references                         PASS
03 no fabricated/placeholder citations          PASS
04 no unsupported novelty claim                 PASS
05 RQ set intact (1–4)                          PASS
06 RQ1 rescoped away from absolute comparison   PASS
07 abstract present (299 words)                 PASS
08 abstract figures traceable to body           PASS
09 no prohibited cross-platform magnitude claim PASS
10 no robustness score invented                 PASS
11 TA association not causation                 PASS
12 U85 mechanism stays non-causal               PASS
13 board validation scope preserved             PASS
14 frozen invariants retained                   PASS
15 frozen figures unchanged                     PASS
```

Three checks initially fired and all three were **checker defects, not
manuscript defects**; each was corrected in the checker and the corrections are
recorded here rather than silently applied:

1. *orphan references* — the reference-extraction regex did not match grouped
   citations of the form `[1, 2]`, so eight genuinely-cited Arm entries appeared
   uncited. Regex extended to comma-separated groups.
2. *novelty phrasing* — `\bthe first\b` matched "the first allocation failure"
   in §4. Narrowed to `the first (study|work|paper|to)`.
3. *robustness score* — matched line 368, which is the sentence *declining* to
   define one. Negation-context guard added, consistent with checks 09/11/12/13.

---

## 4. Explicitly NOT done

Items 7–14 of REVIEW_ACTION_PLAN remain unapplied and unmodified: figures,
table-density rebalancing, §4.6 promotion, Results/Discussion separation,
limitations grouping (§8.1–8.14 left as-is), and the minor editorial set. No
experiment was run. X2, X4, X5 remain HOLD. No frozen artifact under
`docs/paper/mechanism/`, `docs/paper/platform_sensitivity/`, or
`docs/paper/review/` (other than the new checker and this record) was touched.

**Verification level: syntactic + automated consistency checking.**
Executed: the 15 checks above; manual cross-reference of every abstract figure
to its results section; reference-metadata verification against primary sources.
Not executed: no measurement, no build, no simulation, no board run, and no
external peer review of the added Related Work positioning.
