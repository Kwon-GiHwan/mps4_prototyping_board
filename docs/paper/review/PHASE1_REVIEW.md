# PHASE-1 REVIEW GATE — structural coherence audit

**Task:** REVIEW ONLY. No manuscript modification, no new data, no items 7–14.
**Manuscript audited:** `paper-manuscript-review-phase1-frozen` = f09bba6
**Review baseline:** `paper-full-review-frozen` = 9359c7a
**Change surface audited:** thesis, abstract, RQ1, contribution hierarchy,
Related Work / citations, platform-role table — plus the Results/Discussion
passages those six point to.

## Verdict

```
PHASE1_NEEDS_SMALL_TEXT_FIX
```

Fifteen findings, all correctable in text or references. **No scientific
contradiction was found**, and no finding requires new measurement. Every
Phase-1 change is structurally sound in its own right; the defects are
integration seams — cross-references pointing at the wrong sections, two thesis
clauses stated more broadly than the evidence they index, and one pre-existing
Discussion sentence that now visibly contradicts the platform-role discipline
Phase 1 made explicit.

| axis | verdict |
| --- | --- |
| thesis clauses supported as written | 1 of 3 (2 `TOO_BROAD`) |
| abstract | `ABSTRACT_NEEDS_TEXT_FIX` (framing only; 0 unsupported claims) |
| RQ1 | `RQ1_PARTIALLY_CLOSED` |
| contribution hierarchy | balanced — `PASS` |
| related-work positioning | 2 positioning issues, 2 cross-reference errors |
| references | 15 total, 9 load-bearing, 2 weak, 0 needing replacement, 1 missing near-neighbour |
| platform roles | `PLATFORM_ROLES_COHERENT` |
| story hierarchy | `STORY_HIERARCHY_PASS` |

---

## 2. Central thesis ↔ paper body

Thesis as frozen (§1, lines 56–61), decomposed into three clauses. Full trace in
`PHASE1_THESIS_TRACE.csv`.

### C1 — "Increasing MAC capacity does not yield proportional performance gains: scaling behaviour is workload-dependent and can become non-monotonic"

- **Evidence:** §4.1 — 53 adjacent transitions, 28 `STRONG` (≥ 0.75), 23
  `PARTIAL`, 2 `WEAK_OR_SATURATED`, 3 `NOT_AVAILABLE`; saturation observed once
  (SSE-320/U85/`rnnoise` at 512). §6.1 — the one non-monotonic transition.
- **Conclusion:** §7 "More hardware is not monotonically faster."
- **Limitation:** §8.14 (scope), §4.1 *Not established* note — `NONE_OBSERVED`
  is not "does not saturate", and `STRONG` is a 0.75 threshold, not ideal
  scaling.
- **Verdict: `SUPPORTED`.** The clause is an existence claim plus a
  distributional claim, and both are discharged. No causality asserted, no
  cross-generation absolute comparison required.

### C2 — "it is shaped by heterogeneous operation-level and memory/compiler interactions rather than by any single structural change"

- **Evidence:** §6.3 (ten regressing groups, +1,000…+4,030, largest ≈ 1/5 of the
  delta), §6.4 (27/29 groups direction-consistent, zero flips), §6.6 (retired
  single-factor ublock account; ~95 % background rate in every direction class).
- **Conclusion:** §6.6, §7.
- **Limitation:** §8.8 (per-operation cause `NOT_EVALUABLE` inside merged
  windows), §8.9 (memory mode is not a bandwidth intervention), §8.11 (geometry
  vs scheduling not causally separated).
- **Verdict: `TOO_BROAD`.** The pronoun "it" grammatically refers to *scaling
  behaviour in general*, but the evidence covers **one workload, at one MAC
  transition, on one NPU generation**. §6 is scrupulous about this scope; the
  thesis sentence is not. The clause is true of the studied boundary and
  unestablished as a general property of MAC scaling.
- **Smallest fix (TEXT_ONLY):** bind the clause to the boundary — "…and where it
  does become non-monotonic, that transition is shaped by heterogeneous
  operation-level and memory/compiler interactions rather than by any single
  structural change".

### C3 — "the structural conclusions drawn from simulation transfer across tested platform and timing conditions far better than raw or thresholded performance labels do"

- **Evidence:** §4.6 (ranking 2/2 and 8/8 MAC points; direction 7/7 and 32/32;
  saturation 7/7 and 20/20; normalized ordering 2/2 and 8/8; scaling class
  **24/32** in CLASS B), §5 (board `rho = 1.0`, 0 inversions).
- **Conclusion:** §7 "Which metrics transfer across platform and timing
  conditions."
- **Limitation:** §8.13 (no TA_ON cross-FVP control pair; no same-platform
  U65-vs-U85 pair; CLASS B contributions `NOT_SEPARATED`).
- **Verdict: `TOO_BROAD`,** on two counts. First, "far better" is a comparative
  intensifier with no preregistered basis; the frozen X3 qualification is a set
  of **categories**, deliberately not a score (`X3_METRIC_QUALIFICATION.csv`,
  and §3.7 "no aggregate robustness score is defined"). Second, and more
  substantively, **raw cycles were never evaluated for transfer** — they are
  refused *a priori* as `NOT_COMPARABLE`, not measured and found to transfer
  poorly. Ranking structural metrics as transferring "better than raw labels do"
  implies a comparison that was not performed on the raw layer.
- **Smallest fix (TEXT_ONLY):** "…transfer across the tested platform and timing
  conditions, whereas threshold-based labels proved sensitive to timing-model
  configuration and raw cross-platform cycles are not comparable at all."

**No clause introduces a contribution absent from Results, and none depends on
an unsupported cross-generation absolute comparison.**

---

## 3. Abstract audit

Every quantitative claim maps to frozen evidence and to an exact section; all
scope qualifiers survived compression. Mapping in `PHASE1_THESIS_TRACE.csv`
(rows `ABS-*`).

Negative checks — the abstract implies **none** of the prohibited readings:

| must not imply | status | why |
| --- | --- | --- |
| U55/U65/U85 raw performance ranking | clear | no cross-generation cycle appears; closing paragraph refuses it explicitly |
| U65-vs-U85 causal architectural superiority | clear | no generation is compared to another anywhere in the abstract |
| FVP cycle accuracy against hardware | clear | hardware appears only as "workload ordering is preserved exactly", and the closing paragraph refuses absolute comparison |
| memory bandwidth as a separated cause | clear | "the same groups regress under every memory configuration tested" is an invariance statement, not an attribution |
| ublock as sole cause | clear | stated as accompanying ~95 % of operations "in every direction class and therefore does not discriminate" |
| X1/X3 as a new primary RQ | **at risk** | see below |

**The one issue.** The abstract opens its results with "**Four findings
follow**" and gives the platform-sensitivity result equal bolded weight to the
three primary findings — while §1 places it at **supporting contribution 5**.
The abstract also merges two different validation results (X1/X3 platform
sensitivity and the board ordering result) into that single fourth finding.
A reader of the abstract alone would infer four co-equal contributions and a
tiering that §1 contradicts one page later.

The abstract is otherwise understandable without the limitations section: the
closing paragraph carries the refusal scope, which is the property the review
asked for.

- **Classification: `ABSTRACT_NEEDS_TEXT_FIX`** — framing only, zero unsupported
  claims.
- **Smallest fix (TEXT_ONLY):** change "Four findings follow" to "Three findings
  follow, with a fourth result validating them", or mark the fourth sentence
  **Validation —**. No figure changes.

*Precision note, not a defect:* the abstract's "the same groups regress under
every memory configuration tested" mirrors §6.4's own bold heading, whose
underlying figure is 27 of 29 groups direction-consistent with zero flips. The
abstract is faithful to the body; if §6.4's heading is ever tightened, the
abstract must follow.

---

## 4. RQ1 closure audit

Revised RQ1, read literally: *"How do normalized scaling behaviour, workload
ordering, and deployability differ across the supported Corstone/Ethos-U
configurations?"*

| stage | location | status |
| --- | --- | --- |
| Methods | §3.1 platform roles, §3.3 admissible comparisons | present |
| Results | §4.1 scaling, §4.3 ordering, §4.4 executability, §4.5 RQ1 statement | present |
| Discussion | §7 "Ordering is the portable quantity", "Compilation is not deployment" | present |
| Conclusion | **absent — the manuscript has no Conclusion section** | missing |

**Answerable without the three prohibited supports?** Yes on all three. No raw
cross-generation cycle is needed (§4.5 says so explicitly and §8.2 backs it); no
same-platform U65/U85 comparison is invoked (§8.13 concedes none exists); no
architecture-only causal inference is used — §4.4 classifies the six failures as
a **system-level memory/deployability limitation, not a U55 microarchitecture
limit**, with MAC count, NPU, memory mode and memory map confounded.

**Why it is not fully closed.** RQ1 asks how three axes *differ*, and §4.5
answers at the level of *which axis carries the difference* rather than stating
the per-axis outcome the Results already contain. Assembled from existing
frozen data, the answer is: **deployability differs** (six non-executable cells,
all U55 / `Shared_Sram`); **saturation differs** (the only observed saturation
is one U85 ladder); **workload ordering does not differ** — it is invariant
(`rho = 1.0` in 31/55 pairs, minimum 0.9429, median 1.0000). §4.5 currently
states the framing but not this three-part answer, so a reader must assemble it.

- **Verdict: `RQ1_PARTIALLY_CLOSED`.**
- **Smallest fix (TEXT_ONLY):** one added sentence in §4.5 stating the three
  per-axis outcomes above. All three figures are already printed in §4.1, §4.3
  and §4.4 — nothing is computed.
- **X2 is not required to close RQ1.** RQ1 as revised does not ask for a
  controlled U65-vs-U85 substrate, and no clause of the answer depends on one.

---

## 5. Contribution hierarchy audit

| # | contribution (verbatim head) | classification | verdict |
| --- | --- | --- | --- |
| 1 | systematic MAC-scaling characterization; executability first-class | `PRIMARY_RESULT` | appropriate |
| 2 | operator-level mechanism study of a non-monotonic boundary | `MECHANISM_RESULT` | appropriate |
| 3 | characterization of compiler cost estimates against simulation | `TOOLING/PREDICTION_RESULT` | appropriate |
| 4 | physical-board ordering validation | `VALIDATION` | appropriate |
| 5 | platform-sensitivity robustness | `VALIDATION` | appropriate in §1 |
| 6 | instrumentation qualification incl. cross-backend bridge | `METHODOLOGY_SUPPORT` | appropriate |

- **Balanced:** yes — 3 primary / 3 supporting, and the tier labels are explicit
  headings rather than implied by order.
- **Board validation supporting, not dominating:** yes in §1 (item 4, explicitly
  under "Validation and supporting results", with absolute comparison "refused
  by construction").
- **Platform sensitivity as robustness, not a new main topic:** yes in §1 — but
  contradicted by the abstract's framing (§3 above). The §1 tiering is correct;
  the abstract must be brought into line with it, not the reverse.
- **Instrumentation bridge not oversold:** correct. Item 6 claims only that it
  "bounds what per-layer numbers … may be used for", matching §6.5's
  preregistered `NOT_EQUIVALENT` verdict and §8.10.
- **Vela prominence:** correct at primary tier — it carries §4.2 and the lead
  Discussion paragraph, and is the finding with the most direct practitioner
  consequence.
- **Wording matches Results structure:** yes; items 1–3 map to §4, §6, §4.2 and
  items 4–6 to §5, §4.6, §6.5.

**No contribution combines unrelated claims.** Item 1's pairing of the scaling
sweep with executability is one sweep's two outcomes, not two topics; item 6's
pairing of U85 qualification (§3.5) with the U65 bridge (§6.5) is one
instrumentation-trust argument. **No split is recommended and the count stays at
six.**

One observation for Phase 2 (not a Phase-1 defect): the methodology results
demoted to the closing sentence of §1 are developed at length in §7 as four
numbered items. That asymmetry is a §7 structural matter and belongs to action
items 7–14.

---

## 6. Related Work positioning audit

### Group A — accelerator characterization / models [9] [10] [11]

- **What they do:** SCALE-Sim models a configurable systolic array against
  bandwidth, dataflow and aspect ratio [10]; Timeloop searches a mapping space
  to project performance and energy [11]; the TPU paper measures a production
  datacenter accelerator [9].
- **What this paper does differently:** measures a fixed IP across its supported
  deployment configurations rather than modelling or measuring a design.
- **Contrast factual?** Yes — the characterizations of [9], [10] and [11] are
  accurate and the contrast is real.
- **Flag: `OVERBROAD_FIELD_CLAIM`** on the group's opening clause: *"Systolic-array
  accelerators are **commonly** characterized with analytical or cycle-level
  models rather than measurement."* This is a frequency claim about the field
  supported by three citations — the same species as the "less common" sentence
  Phase 1 deliberately removed. It should be attributed to the cited works, not
  to the field. **Fix (TEXT_ONLY):** "SCALE-Sim [10] and Timeloop [11]
  characterize systolic arrays with analytical and cycle-level models rather
  than measurement."

### Group B — TinyML benchmarking [13] [14] [15]

- **What they do:** MLPerf Tiny standardizes end-to-end latency/accuracy/energy
  for MCU-class systems [13]; MicroNets is a NAS/architecture paper supplying
  `kws_micronet_m` [14]; TFLite Micro is the runtime [15].
- **Contrast factual?** Partly.
- **Flag: attribution imprecision.** The sentence "**Such suites** deliberately
  report system-level outcomes and do not decompose an anomaly to the operation
  level" sweeps [14] into "suites" — MicroNets is not a benchmark suite, and the
  manuscript's own preceding clause correctly uses it as workload provenance.
  **Fix (TEXT_ONLY):** scope the negative claim to [13] (and [15] as a runtime),
  leaving [14] as workload provenance only.
- **Flag: `MISSING_NEAR_NEIGHBOR` — none.** No closer neighbour was identified
  in review; the paper's specific object (operation-level decomposition of a
  configuration-scaling anomaly on a commercial embedded NPU) has no located
  direct predecessor, and **that absence is deliberately not converted into a
  novelty claim.**

### Group C — simulator-vs-hardware validation [12]

- **What it does:** validates gem5 against an ARM Versatile Express TC2 board.
- **Numeric claim verified.** The manuscript's "mean absolute runtime errors in
  the 13–17 % range after targeted corrections" is **accurate**: the paper
  reports MAPE 13 % (SPEC CPU2006) and 16 %/17 % (PARSEC single/dual-core) after
  simulator modifications. The manuscript correctly says *mean absolute*; the
  signed means (5 %, −11 %, −12 %) are not claimed. **`PASS` — no fix.**
- **Contrast factual?** Yes, and it is the strongest positioning move in the
  section: it names what simulator validation normally claims, which is what
  makes §5's narrower ordinal claim read as discipline rather than evasion.

### Group D — Arm / Ethos-U / Vela toolchain [1]–[8]

- Correctly framed as *primary evidence for the measured system rather than
  related work* — an accurate distinction.
- **Capability attribution is correct**, including the load-bearing one: Vela's
  own documentation labels its performance estimates experimental [7], which is
  the external warrant for treating them as predictions under test in §4.2.
- **`PASS`.**

### Cross-reference errors introduced in this section (both TEXT_ONLY)

1. §2.1 Group C: "…rather than absolute cycle agreement **(Section 6)**" — the
   board work is **Section 5**. Section 6 is the U85 mechanism study.
2. §2.1 Group B: "…which is the gap **Section 7** addresses" — the
   operation-level decomposition is **Section 6**; §7 only discusses it.

**No "first", "few", "less common" or equivalent frequency claim was
reintroduced** — confirmed by check 04 of the Phase-1 script and by manual read.
The one surviving frequency word is "commonly" in Group A, flagged above.

---

## 7. Reference quality audit

Full table in `PHASE1_REFERENCE_ROLE_AUDIT.csv`.

```
references total            15
load-bearing                 9   [1][2][4][5][7][8][12][13][14]
supporting / contextual      4   [9][10][11][15]
weak or redundant            2   [3][6]
needing replacement          0
missing near-neighbour       1   Ethos-U55 / U65 TRM (see below)
```

- **Primary Arm sources are used for architectural and tool facts** — [1]/[2]
  for MAC configurations and PMU event space, [4]/[5]/[6] for the subsystem and
  its FVP, [7]/[8] for compiler and runner. This satisfies the requirement that
  architectural facts prefer primary Arm sources.
- **No citation supports a claim beyond its scope.** [12] was the one at risk
  and was verified against the source (§6 above). [7] is cited only for what its
  documentation states about itself. [14] is cited only for workload provenance.
- **Weak/redundant:** [3] (ML Developers Guide) overlaps [1]/[2] and is cited
  once in a lump; [6] (Fast Models FVP Reference Guide) is cited only in the
  same lump, although the Fast Models **version skew** it would naturally
  support is asserted uncited in §3.3 (11.22.35 / 11.24.13 / 11.27.25 /
  11.31.28). Neither is wrong; both are under-used.
- **`MISSING_NEAR_NEIGHBOR` (REFERENCE_ONLY):** the paper measures U55 and U65
  across 92 validation cells and much of the formal sweep, but cites primary
  manuals only for **U85** ([1], [2]). Architectural statements about U55/U65
  MAC configurations and their `AXI*` PMU family currently rest on no primary
  Arm citation. Adding the U55/U65 TRMs is a reference-only correction.

---

## 8. Platform role table audit

The §3.1 table matches the frozen X0/X1/X3 evidence exactly, on all four rows:

| platform | NPU | TA | role | matches expected |
| --- | --- | --- | --- | --- |
| SSE-300 | U55, U65 | `TA_ON` | primary memory-aware simulated substrate | yes |
| SSE-310 | U55, U65 | `TA_OFF` | diagnostic / platform-sensitivity control | yes |
| SSE-315 | U65 | `TA_OFF` | U65-specific diagnostic reference substrate | yes |
| SSE-320 | U85 | `TA_ON` | primary U85 substrate and hardware-validation anchor | yes |

TA states cross-check against `x1_analyzer.py`'s frozen `TA` map and against the
compiled-source evidence in §3.1 (sse-310: 399 sources / 0 timing-adapter;
sse-315: 400 / 0). NPU coverage matches `EXPECTED_MACS` and the CLASS A/B
definitions in §3.7.

**Searched specifically for the failure mode named in the gate:** every
occurrence of SSE-310 and SSE-315 in the manuscript (lines 196, 197, 207, 208,
357, 358, 359, 471, 472) is in the role table, the configuration enumeration,
the CLASS A/B definition, or the §4.6 CLASS A result — which states its finding
in the narrow frozen form (`NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR`)
and explicitly declines to generalize. **No passage treats SSE-315 as an
authoritative U65 performance platform.**

- **Verdict: `PLATFORM_ROLES_COHERENT`.**

**But one nearby prose statement does undermine the table's discipline** — see
finding F4 below. It is a §7 sentence, not a §3.1 one, which is why the table
verdict stands.

---

## 9. Primary vs validation story

| layer | components | narrative weight |
| --- | --- | --- |
| primary scientific story | MAC scaling / workload dependence (§4); U85 direct mechanism (§6, 139 lines); Vela prediction behaviour (§4.2, lead Discussion paragraph) | dominant |
| validation / robustness | board validation (§5, 58 lines); X1/X3 platform sensitivity (§4.6 — a *subsection*, not a section); U65 bridge (§6.5 — a subsection) | subordinate |

The subordination is carried structurally, not merely asserted: platform
sensitivity and the instrumentation bridge live as subsections inside the
sections whose claims they support, and §1 tiers all six contributions
explicitly.

- **Verdict: `STORY_HIERARCHY_PASS`.**

Two qualifications. The board validation holds a top-level section (§5) of the
same rank as the mechanism study, giving it structural parity the narrative does
not — mitigated by length (58 vs 139 lines) and by RQ3 legitimately needing a
home; any rebalancing belongs to action items 7–14, not here. And the abstract's
"four findings" framing (§3 above) is the one place where the hierarchy is
actually blurred for a reader.

---

## 10. Conclusion audit

**The manuscript has no Conclusion section.** It ends at §8 Limitations, followed
by an italic *Integration status* note and the References. This is a structural
gap, and it is why the RQ1 trace in §4 above terminates before its final stage.

Consequently there is no stale Conclusion language to flag — but the closing
note that occupies the position **is** stale on two counts:

1. It reads *"STOP for full-paper review; no new experiment is initiated by this
   integration."* The full-paper review is complete (9359c7a) and Phase-1
   remediation has since been applied and frozen. The sentence describes a state
   the document has left.
2. Its frozen-source list omits the platform-sensitivity tags
   (`paper-platform-sensitivity-x1-*`, `-x3-*`) even though §4.6 — the entire
   robustness result and thesis clause C3 — depends on them. The header block at
   lines 3–8 does list `paper-platform-sensitivity-*`, so the manuscript
   contradicts itself about its own evidence base.

Neither is a claim defect; both are process scaffolding that outlived its state.
Whether to add a real Conclusion is a Phase-2 structural decision (it pairs
naturally with action items 7–14); correcting the stale note is TEXT_ONLY and
can be done in either phase.

---

## 11. Phase-1 verdict and findings

```
PHASE1_NEEDS_SMALL_TEXT_FIX

TEXT_ONLY            13   (F1–F13)
REFERENCE_ONLY        1   (F14)
EXISTING_DATA_ONLY    0
NEW_EXPERIMENT        0
tooling (checker)     1   (F15)
```

Full remediation detail in `PHASE1_ACTIONS.md`. Summary:

| id | finding | class |
| --- | --- | --- |
| F1 | §2.1 cross-ref: board work cited as "(Section 6)", is §5 | TEXT_ONLY |
| F2 | §2.1 cross-ref: "the gap Section 7 addresses", is §6 | TEXT_ONLY |
| F3 | §3.1 cross-ref: structural comparison cited as "(Section 5)", is §4.6 | TEXT_ONLY |
| F4 | §7(i) "differed ~4× **purely by adapter state**" — causal attribution contradicting §4.6 / §8.13 `NOT_SEPARATED` for the same CLASS B pair | TEXT_ONLY |
| F5 | §3.7 "no cross-platform cycle ratio is computed **anywhere**" over-scoped, given F4 reports one | TEXT_ONLY |
| F6 | thesis C2 stated generally; evidence is one workload / one transition / one generation | TEXT_ONLY |
| F7 | thesis C3 "far better than raw … labels do" implies the raw layer was evaluated for transfer; it is refused a priori | TEXT_ONLY |
| F8 | abstract "Four findings" gives X1/X3 co-equal headline status vs supporting tier in §1 | TEXT_ONLY |
| F9 | §2.1 "commonly characterized … rather than measurement" — `OVERBROAD_FIELD_CLAIM` | TEXT_ONLY |
| F10 | §2.1 "such suites" sweeps MicroNets [14] into benchmark suites | TEXT_ONLY |
| F11 | §4.5 does not assemble the per-axis RQ1 answer its own Results contain | TEXT_ONLY |
| F12 | no Conclusion section | TEXT_ONLY (Phase-2 structural) |
| F13 | stale *Integration status* note; omits platform-sensitivity frozen tags | TEXT_ONLY |
| F14 | no primary Arm citation for U55/U65 (only U85 manuals cited) | REFERENCE_ONLY |
| F15 | Phase-1 checker rule 11 missed "purely by adapter state" (matched only `X caused`) | tooling |

### The one finding worth reading twice — F4

§7 states: *"two platforms running a byte-identical command stream differed ~4×
purely by adapter state, and nothing in the cycle counts signalled it."*

The observation is real and frozen — `TIMING_ADAPTER_AUDIT.md` records a
byte-identical NPU program measured ~4× apart between TA-ON and TA-OFF, and
`PROJECT_RECORD.md` gives the cells (`SSE-300/U55@32` 112,059 cycles vs
`SSE-310/U55@32` 27,059) and classifies it `CAUSE_RESOLVED`, framed as *"a
methodology warning, not a performance comparison."*

The problem is that the manuscript now carries **two different verdicts on the
same platform pair**. SSE-300 ↔ SSE-310 is a CLASS B pair, and §4.6 and §8.13
state that in CLASS B the timing-adapter state, the subsystem and the Fast
Models implementation change together and their contributions are
`NOT_SEPARATED`. A reader who takes §8.13 seriously cannot also accept "purely
by adapter state" for the same comparison. Relatedly, §3.7's "no cross-platform
cycle ratio is computed anywhere" is contradicted by §7 reporting a ~4× one.

This is a **presentation conflict, not a data conflict** — the two frozen
artifacts are answering different questions (X0 asked what the adapter does to
raw magnitude; X1/X3 asked what survives a platform change) and neither is
wrong. The minimal repair is to state the ~4× in the frozen X0 vocabulary and
scope §3.7's sentence to the validation. **No new experiment is warranted.**

Phase-1 checker rule 11 did not catch this because it matches
`(TA|timing[- ]adapter|Corstone|Fast Models)\s+caused`; "purely by adapter
state" asserts causation without the word. F15 records the rule gap.

---

## What remains out of scope

Action items 7–14 were not started. X2, X4, X5 remain HOLD; nothing in this
review argues for opening them, and **X2 in particular is not needed to close
RQ1** as revised. No data was collected, and `MANUSCRIPT.md` was not modified —
verified clean at f09bba6.

**Verification level: review / static analysis.**
Executed: full read of the six Phase-1 change surfaces and every Results,
Discussion and Limitations passage they reference; cross-reference resolution of
all section pointers in the changed text; trace of every abstract figure to its
results line; comparison of the §3.1 table against frozen X0/X1/X3 artifacts and
`x1_analyzer.py`; grep sweep for platform-role conflicts and for causal phrasing
outside the checker's rule set; primary-source verification of the [12] numeric
claim.
Not executed: no build, simulation, board run, or measurement; no re-derivation
of frozen analyzer outputs; no external peer review; no verification of Arm
document contents beyond identifier resolution.
