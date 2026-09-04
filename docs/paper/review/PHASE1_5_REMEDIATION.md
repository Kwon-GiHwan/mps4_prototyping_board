# PHASE-1.5 TEXT CORRECTION — traceability record

**Authorization:** MANAGER GO — Phase-1.5 separate text pass (D1 APPROVED,
D2 F12 deferred, D3 F14 approved, D4 X2/X4/X5 HOLD).
**Input:** `paper-manuscript-review-phase1-frozen` = f09bba6
**Review authority:** `paper-manuscript-phase1-review-frozen` = 85aa4d5
**Output:** `paper-manuscript-phase1_5-frozen`
**Applied:** F1–F11, F13, F14, F15. **Not applied:** F12 (Conclusion — explicit
hold; no temporary conclusion inserted).
**Evidence status:** no measurement, build, FVP run, board run, or analysis.
No frozen X0/X1/X3 evidence document was modified. Every figure in the revised
text was already present in the manuscript or in a frozen artifact.

## F4 final causal scope

```
same Vela / NPU artifact                              ESTABLISHED
TA state differs (SSE-300 TA_ON vs SSE-310 TA_OFF)    ESTABLISHED
subsystem differs                                     ESTABLISHED
Fast Models / timing implementation differs           ESTABLISHED

=> TA / subsystem / FM contributions                  NOT_SEPARATED
=> the ~4x magnitude is a methodology warning against raw cross-platform
   cycle comparison, NOT a performance result and NOT an adapter attribution
```

---

## Per-finding record

### F4 — causal-scope contradiction (highest priority)

| field | value |
| --- | --- |
| location | §7, "Measurement methodology results", item (i) |
| old wording | "two platforms running a byte-identical command stream differed ~4× **purely by adapter state**, and nothing in the cycle counts signalled it." |
| new wording | "the same NPU artifact exhibited a large cycle difference — a byte-identical command stream measured ~4× apart — between the SSE-300 and SSE-310 conditions… Because timing-adapter state, subsystem and Fast Models timing implementation differ together across that pair, the magnitude **cannot be attributed to the timing adapter alone**; the three contributions are `NOT_SEPARATED` (Section 8.13). The observation is therefore treated as a **methodology warning against raw cross-platform cycle comparison, not as a performance result**." |
| authority | `TIMING_ADAPTER_AUDIT.md` ("Preserved warning"); `PROJECT_RECORD.md` (cell values, "a methodology warning, not a performance comparison"); §4.6 / §8.13 CLASS B `NOT_SEPARATED` |
| claim strength changed? | **YES — weakened.** A causal isolation became an association plus an explicit non-attribution. |
| checker coverage | check 16 (new). Proven to fire: run against f09bba6 it reports FAIL on exactly this sentence; against the corrected text it passes. |
| verdict | **CLOSED** |

The methodology point that made the observation worth reporting is preserved in
full — the danger is that raw cycle magnitude can move ~4× with nothing in the
counts signalling it. Only the attribution was removed. **No frozen X0/X1/X3
document was edited to harmonize wording**; the manuscript now carries the
integrated hierarchy while the historical artifacts remain as frozen.

### F1 / F2 / F3 — cross-reference repairs

All three were introduced by Phase-1 text. Each was verified semantically, not
by existence alone: the pointer resolves, and the target section is actually
about the subject of the sentence.

| id | location | old → new | target verified as |
| --- | --- | --- | --- |
| F1 | §2.1 simulator-vs-hardware group | `(Section 6)` → `(Section 5)` | §5 "Corstone-320 hardware validation (RQ3)" |
| F2 | §2.1 TinyML group | "the gap Section 7 addresses" → `(Section 6)` | §6 "Operator-level mechanism study: U85 256 → 512 (RQ4)" |
| F3 | §3.1 platform-role prose | `(Section 5)` → `(Section 4.6)` | §4.6 "Robustness of the structural metrics across tested FVP variants" |

Claim strength changed? **NO** for all three — pointer corrections only.
Checker coverage: `phase1_5_validation.py` resolves every `Section N` pointer
in the manuscript against the section index (including §8's bold-inline
subsections), verifies the three repaired pointers land on the expected topic,
and asserts no stale pre-Phase-1 pointer survives.

### F6 / F7 — thesis clause narrowing

| field | value |
| --- | --- |
| location | §1, **Thesis** paragraph |
| old C2 | "**it is** shaped by heterogeneous operation-level and memory/compiler interactions rather than by any single structural change" |
| new C2 | "**where it does become non-monotonic, that transition is** shaped by heterogeneous operation-level and memory/compiler interactions rather than by any single structural change" |
| old C3 | "…transfer across tested platform and timing conditions **far better than raw or thresholded performance labels do**" |
| new C3 | "…transfer across the tested platform and timing conditions, **whereas threshold-based labels proved sensitive to timing-model configuration and raw cross-platform cycles are not comparable at all**" |
| claim strength changed? | **YES — both weakened.** No evidence was added to rescue the broad wording. |

Post-correction trace — all three clauses now `SUPPORTED`:

| clause | result section | frozen evidence | limitation |
| --- | --- | --- | --- |
| C1 — no proportional gain; workload-dependent; can become non-monotonic | §4.1, §6.1 | 53 transitions: 28 `STRONG`, 23 `PARTIAL`, 2 `WEAK_OR_SATURATED`, 3 `NOT_AVAILABLE`; saturation observed once; one non-monotonic transition | §4.1 *Not established* note; §8.14 |
| C2 — where non-monotonic, shaped by heterogeneous operation-level and memory/compiler interactions | §6.3, §6.4, §6.6 | ten regressing groups +1,000…+4,030, largest ≈ 1/5 of delta; 27/29 groups direction-consistent, zero flips; ublock ~95 % in every direction class | §8.8, §8.9, §8.11 |
| C3 — structural conclusions transfer; thresholded labels sensitive; raw not comparable | §4.6, §5 | ranking 2/2 and 8/8; direction 7/7 and 32/32; saturation 7/7 and 20/20; normalized ordering 2/2 and 8/8; scaling class 24/32 CLASS B; board `rho = 1.0`, 0 inversions | §8.13 |

No architecture-only causality was introduced; asserted by validation check
*"thesis asserts no architecture-only causality"*.

### F8 — abstract evidence tiering

| field | value |
| --- | --- |
| location | Abstract |
| old wording | "**Four findings follow.**" … fourth item bolded at parity with the first three |
| new wording | "**Three primary findings follow.**" … then a separate lead-in: "Two results validate these findings rather than extending them." |
| claim strength changed? | **NO** — no factual claim altered, no number added or removed |
| checker coverage | validation checks: abstract tiers primary results / marks validation tier / **adds no new numbers** (asserts the abstract's numeric set is a subset of the manuscript's) |

Primary tier now reads as MAC-scaling characterization, U85 mechanism, Vela
prediction behaviour; validation tier as platform-sensitivity and board
ordering. Board validation and X1/X3 no longer read as co-primary research
questions.

### F9 / F10 — Related Work positioning and attribution

| id | old wording | new wording | why |
| --- | --- | --- | --- |
| F9 | "Systolic-array accelerators are **commonly** characterized with analytical or cycle-level models rather than measurement" | "**SCALE-Sim and Timeloop** characterize systolic-array accelerators with analytical and cycle-level models" | field-wide frequency inferred from three citations; now attributed to the works themselves |
| F10 | "**Such suites** deliberately report system-level outcomes and **do not decompose** an anomaly to the operation level" | "MLPerf Tiny reports system-level outcomes **by design, at whole-inference granularity** [13]; **this work additionally decomposes** one configuration transition to the operation level on a specific NPU (Section 6)." | MicroNets [14] is a NAS/architecture paper, not a suite; and a capability-absence claim was replaced with positive positioning |

Claim strength changed? **YES — both weakened**, from field-level and
capability-absence claims to source-supported statements. Neither `first`,
`few`, `uncommon`, `less common`, nor `no prior work` was reintroduced —
asserted by consistency check 04 and validation check *"no reintroduced novelty
vocabulary"*.

### F11 — RQ1 closure

| field | value |
| --- | --- |
| location | §4.5 RQ1 statement |
| added | one sentence naming the per-axis outcome: **deployability differed** (six non-executable cells, all `wav2letter_pruned_int8` × U55 × `Shared_Sram`, §4.4); **saturation differed** (the only observed instance is one U85 ladder, §4.1); **workload ordering did not differ** (`rho == 1.0` in 31/55 pairs, min 0.9429, median 1.0000, §4.3) |
| authority | existing Results only — every figure is already printed in §4.1, §4.3, §4.4 |
| claim strength changed? | **NO** — assembles printed results; no new metric, no new computation, no X2 |
| chain | RQ1 (§1) → Methods (§3.1 roles, §3.3 admissible comparisons) → Results (§4.1/4.3/4.4/4.5) → Discussion (§7 "Ordering is the portable quantity", "Compilation is not deployment") → answer (§4.5) |
| verdict | **`RQ1_CLOSED`** — answerable without absolute cross-generation performance, without a U65-vs-U85 controlled substrate, and without architecture-only causality |

### F13 — stale integration note

| field | value |
| --- | --- |
| location | closing italic note before References |
| old wording | "RQ1/RQ2/RQ3 and the U85 mechanism study are integrated… **STOP for full-paper review**; no new experiment is initiated by this integration." Frozen-source list omitted the platform-sensitivity tags. |
| new wording | "**RQ1–RQ4** and the U85 mechanism study are integrated…" + added `paper-platform-sensitivity-x1-results-frozen` and `-x3-results-frozen`; the completed "STOP for full-paper review" instruction removed |
| claim strength changed? | **NO** — process metadata only |
| scope | applied exactly as specified in the frozen `PHASE1_ACTIONS.md`; not broadened. The stricter evidence boundary was preserved: the note now lists the X1/X3 sources that §4.6 and thesis clause C3 actually depend on. |

### F14 — U55 / U65 primary Arm sources (REFERENCE_ONLY)

Two references added. **Both were verified by extracting the text of the
document itself**, not by identifier resolution alone.

| claim | source document | exact supporting content | metadata verification |
| --- | --- | --- | --- |
| Ethos-U55 discrete MAC configurations are 32–256 MACs/clock cycle | Arm Ethos-U55 NPU Technical Reference Manual, doc ID `102420_0200_02_en`, revision r2p0 | `macs_per_cc` field: "The log2(macs/clock cycle). Valid encoding range is 5-8 for 32-256 MACs/clock cycle (each MAC is an 8-bit x 8-bit MAC)." | **VERIFIED** — title, document ID and revision read from the document |
| Ethos-U65 discrete MAC configurations are 256 and 512; shared-buffer size differs between them | Arm Ethos-U65 NPU Technical Reference Manual, doc ID `102023_0000_06_en`, revision r0p0 | `macs_per_cc`: "The valid encoding range is 8 for the 256 configuration, and 9 for the 512 configuration." `shram_size`: "48KB for the 256 configuration, and 96KB for the 512 configuration." | **VERIFIED** — title, document ID and revision read from the document |

Cited at two places: §2 Background (per-generation MAC configuration ranges) and
§2.1 Group D (Arm toolchain paragraph). Claim strength changed? **NO** — no
scientific claim was altered to accommodate a citation.

Three boundaries observed deliberately:

1. **`macs_per_cc` is not made the admission authority.** §3.1's rule is
   unchanged: supported MAC configurations are established from the
   Vela/source-defined discrete set and independently confirmed by FVP
   initialization probes, and *"FVP parameter acceptance is not used as the
   authority"*. The TRMs are cited in Background as generational facts, not
   inserted into §3.1's admission procedure — which would have disturbed the X0
   `num_macs` correction (§8.12). Preservation asserted by validation check
   *"X0 num_macs correction preserved"*.
2. **U85 documentation is not cited as authority for U55/U65 facts**, and the
   new citations are not used for U85 — asserted by validation check *"U85 docs
   not used as U55/U65 authority"*.
3. **PMU event names are NOT attributed to these manuals.** The `AXI*` PMU
   *event-name* family could not be located in the extracted text of either TRM
   (only the `AXI_LIMIT0-3` / `AXI_CNT_SEL` registers were found), so the
   Background sentence now states explicitly that which PMU event names a
   generation emits *"is not taken from documentation in this work but
   established empirically (Section 8.4)"*. **Unresolved authority reported
   rather than papered over.**

### F15 — checker gap (causal language)

Phase-1 rule 11 matched only `(TA|timing[- ]adapter|Corstone|Fast Models)\s+caused`,
so "purely by adapter state" passed. Added **check 16, causal isolation**, built
as a three-part predicate rather than a word blacklist:

```
CAUSAL       purely by | purely/solely due to | solely by/because of |
             attributable to | attributed to | results/stems from |
             driven by | caused by | causes | caused | because of | due to
CONFOUNDED   timing-adapter | adapter state | TA | subsystem | Fast Models |
             Corstone | platform | ublock | bandwidth | memory-system |
             shared-SRAM | contention | SSE-3xx
EXCULPATING  not | no | never | cannot | without | refus | unavailable |
             NOT_SEPARATED | NOT_EVALUABLE | ASSOCIATED_WITH | CONSISTENT_WITH |
             retired | retracted | withdraw | unsupported | remain | earlier |
             historical | prior study | methodology warning | rather than
```

A hit is reported only when a causal connective sits within ±260 characters of a
**confounded subject** and **no exculpating marker** appears in that window —
so the checker distinguishes an affirmative causal claim from a negated or
retired claim, a quoted historical framing, and a `NOT_SEPARATED` qualification.

**Mutation-tested, per the project rule that a check which cannot fail is worse
than no check.** Run against the pre-fix manuscript (f09bba6), check 16 reports
FAIL and quotes the F4 sentence verbatim; against the corrected manuscript it
passes.

Regression fixtures: `docs/paper/review/phase1_5_checker_fixtures.py`, 14 tests.

- **6 must-fire:** the exact F4 sentence; `TA caused`; `solely due to the
  subsystem`; `attributable to adapter state`; `driven by memory-system
  bandwidth`; `ublock enlargement causes`.
- **8 must-not-fire:** the F4 replacement text; §4.6's `NOT_SEPARATED`
  qualification; §4.6's `ASSOCIATED_WITH` framing; §6.6's retired ublock
  account; §6.6's unavailable single-factor claims; §6.5's bridge-residual
  refusal; §8.12's withdrawn historical observation; a causal sentence about a
  subject outside the confounded set.

The checker was also made importable — the manuscript load and check execution
moved into `main()` under a `__main__` guard, so the fixtures can import the
detector. This follows the repo convention against modules that execute (or
`sys.exit`) at import.

### F12 — Conclusion

**NOT APPLIED.** Deferred to Phase 2 per D2. No temporary or placeholder
conclusion was inserted.

---

## Validation

Two suites, both fail-closed.

**`phase1_consistency_check.py` — 16/16 PASS** (15 Phase-1 checks + check 16).

**`phase1_5_validation.py` — 25/25 PASS**, covering the manager's battery:
cross-reference existence and semantic target verification; no stale Phase-1
pointer; thesis trace (C1 scoped, C2 bound to the boundary, C3 intensifier
dropped, no architecture-only causality); abstract tiering and no-new-numbers;
related-work attribution (no field-wide frequency claim, no reintroduced novelty
vocabulary, MicroNets not miscast); reference resolution both directions;
U55/U65 primary sources present and U85 not used as their authority;
platform-role conflict scan; and preservation of the X0 `num_macs` correction,
the compiler-path distinction, the U65 bridge `NOT_EQUIVALENT` verdict, and the
X1/X3 CLASS A/B scope.

**`phase1_5_checker_fixtures.py` — 14/14 PASS.**

```
authorized findings closed        F1-F11, F13, F14, F15   (14 of 14)
deferred                          F12
rule failures                     0
scientific contradictions         0
new experiments required          0
```

### Validator corrections recorded

Three checks failed on first run; **all three were validator defects, not
manuscript defects**, and are recorded here rather than silently fixed:

1. *cross-reference targets exist* — §8's subsections are bold-inline
   (`**8.1 …**`), not markdown headings, so every `Section 8.x` pointer looked
   unresolved. The section index now also indexes bold-numbered items.
2. *semantic target — board work* — the pattern was matched against the raw
   text, but the phrase spans a hard line break. All semantic patterns now match
   whitespace-normalized text.
3. *compiler-path distinction preserved* — same cause: "not an exact
   decomposition" is line-wrapped with leading indentation.

This is the same class of defect recorded in Phase 1 (three checker corrections
there, three here), and the same root cause in two of three cases: the
manuscript is hard-wrapped, so any literal multi-word pattern must be
whitespace-normalized before matching.

---

## Scope not touched

REVIEW_ACTION_PLAN items 7–14 remain HOLD; X2, X4, X5 remain HOLD. No frozen
evidence document under `docs/paper/platform_sensitivity/`,
`docs/paper/mechanism/`, or the Phase-1 review set was modified — the only
changed files are `MANUSCRIPT.md` and the checker, plus the new validation and
fixture scripts.

**Verification level: syntactic + automated consistency and validation checking,
with primary-source verification for the two added references.**
Executed: 16 consistency checks; 25 validation checks; 14 checker fixtures;
mutation test of check 16 against f09bba6; text extraction and content
verification of the Ethos-U55 and Ethos-U65 TRMs; semantic re-read of every
edited passage in context.
Not executed: no build, simulation, FVP run, board run, or measurement; no
re-derivation of frozen analyzer outputs; no external peer review.
