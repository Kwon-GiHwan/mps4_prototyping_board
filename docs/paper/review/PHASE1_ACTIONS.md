# PHASE-1 REVIEW — remediation actions

Derived from `PHASE1_REVIEW.md` against `paper-manuscript-review-phase1-frozen`
(f09bba6). **Not applied.** No action below requires new data.

```
TEXT_ONLY            13
REFERENCE_ONLY        1
EXISTING_DATA_ONLY    0
NEW_EXPERIMENT        0
tooling (checker)     1
```

Ordering note: F4/F5 are a single coupled repair and should be applied together.
F1–F3 are mechanical. F12 is structural and pairs naturally with action items
7–14 rather than with a text pass.

---

## TEXT_ONLY

### F1 — §2.1 Group C cross-reference (mechanical)

`…rather than absolute cycle agreement **(Section 6)**` → **(Section 5)**.
Board validation is §5; §6 is the U85 mechanism study.

### F2 — §2.1 Group B cross-reference (mechanical)

`…which is the gap **Section 7** addresses` → **Section 6**.
The operation-level decomposition is §6; §7 discusses it.

### F3 — §3.1 cross-reference (mechanical)

`…the latter appear only where a comparison is explicitly structural
**(Section 5)**` → **(Section 4.6)**.
The TA-OFF platforms appear in the structural robustness subsection, not in the
board section.

### F4 — §7(i) causal attribution (coupled with F5)

Current: *"two platforms running a byte-identical command stream differed ~4×
**purely by adapter state**, and nothing in the cycle counts signalled it."*

Conflicts with §4.6 (`ASSOCIATED_WITH`, "not attributed to the timing adapter")
and §8.13 (`NOT_SEPARATED`) for the **same CLASS B pair**, SSE-300 ↔ SSE-310.

Restate in the frozen X0 vocabulary, preserving the methodology point that makes
the observation worth reporting:

> A simulator's timing adapter can silently change what is being measured: a
> byte-identical NPU command stream measured ~4× apart between a TA-ON and a
> TA-OFF platform (`SSE-300/U55@32`, 112,059 cycles; `SSE-310/U55@32`, 27,059),
> and nothing in the cycle counts signalled it. The frozen record classifies
> this as a methodology warning rather than a performance comparison; as a
> CLASS B pair the subsystem, the Fast Models implementation and the adapter
> state change together, so the magnitude is `ASSOCIATED_WITH` the adapter
> difference and not attributed to it alone.

Sources: `TIMING_ADAPTER_AUDIT.md` ("Preserved warning"), `PROJECT_RECORD.md`
(the two cell values, `CAUSE_RESOLVED`, "a methodology warning, not a
performance comparison").

### F5 — §3.7 over-scoped refusal (coupled with F4)

Current: `…and no cross-platform cycle ratio is computed **anywhere**.`
True of the X1/X3 validation; false of the paper, since §7(i) reports a ~4× one
inherited from the X0 audit. Scope the sentence:

> …and no cross-platform cycle ratio is computed in this validation.

### F6 — thesis clause C2 scope

Current: *"…it is shaped by heterogeneous operation-level and memory/compiler
interactions rather than by any single structural change…"*

Bind to the boundary actually studied:

> …and where scaling does become non-monotonic, that transition is shaped by
> heterogeneous operation-level and memory/compiler interactions rather than by
> any single structural change…

### F7 — thesis clause C3 precision

Current: *"…transfer across tested platform and timing conditions far better
than raw or thresholded performance labels do."*

Two problems: "far better" is an unpreregistered intensifier over a categorical
qualification, and raw cycles were refused *a priori* rather than evaluated for
transfer. Replace with:

> …and the structural conclusions drawn from simulation transfer across the
> tested platform and timing conditions, whereas threshold-based labels proved
> sensitive to timing-model configuration and raw cross-platform cycles are not
> comparable at all.

### F8 — abstract tier framing

`Four findings follow.` gives the platform-sensitivity result headline parity
with the three primary findings, contradicting §1's supporting tier, and merges
X1/X3 with the board result into one "finding".

Minimal repair — either:
- `Three findings follow, with a fourth result validating them.`, or
- prefix the fourth sentence with **Validation —**.

No figure changes. (Splitting X1/X3 from the board result would lengthen the
abstract and is not required.)

### F9 — §2.1 Group A overbroad field claim

Current: *"Systolic-array accelerators are **commonly** characterized with
analytical or cycle-level models rather than measurement…"* — a frequency claim
about the field on three citations, the same species as the "less common"
sentence Phase 1 removed. Attribute to the works:

> SCALE-Sim [10] and Timeloop [11] characterize systolic arrays with analytical
> and cycle-level models rather than measurement: SCALE-Sim studies how
> bandwidth, dataflow and array aspect ratio shape runtime, and Timeloop
> searches the mapping space to project performance and energy.

### F10 — §2.1 Group B attribution

`Such suites deliberately report system-level outcomes…` sweeps MicroNets [14]
— a NAS/architecture paper — into "suites". Scope the negative claim to the
benchmark suite and runtime, leaving [14] as workload provenance only.

### F11 — §4.5 RQ1 per-axis answer

§4.5 states the framing but not the three-part answer its own Results already
contain. Add one sentence assembled from §4.1, §4.3 and §4.4 — **no new
computation**:

> Concretely: deployability differed (six non-executable cells, all
> `wav2letter_pruned_int8` × U55 × `Shared_Sram`); saturation differed, the only
> observed instance being one U85 ladder; and workload ordering did not differ
> at all, remaining invariant across configurations (`rho == 1.0` in 31/55
> pairs, minimum 0.9429, median 1.0000).

Closes `RQ1_PARTIALLY_CLOSED` → `RQ1_CLOSED`. **X2 is not required.**

### F12 — no Conclusion section (Phase-2 structural)

The manuscript ends at §8 Limitations. A Conclusion is the missing final stage
of the RQ1→…→Conclusion trace and of the RQ2/RQ3/RQ4 traces. Recommend
deferring to action items 7–14, where Results/Discussion separation is already
scheduled, rather than adding a section in a text pass. If added, it must state
only the four RQ answers already in §4.5, §4.1, §5 and §6.6 and must not
reintroduce anything removed from RQ1 or Related Work.

### F13 — stale *Integration status* note (lines 884–890)

Two corrections:
1. `STOP for full-paper review; no new experiment is initiated by this
   integration.` describes a state the document has left — the review is
   complete (9359c7a) and Phase-1 remediation is frozen (f09bba6).
2. The frozen-source list omits `paper-platform-sensitivity-x1-*` and `-x3-*`
   although §4.6 and thesis clause C3 depend on them; the header block at lines
   3–8 does list `paper-platform-sensitivity-*`, so the document contradicts
   itself about its own evidence base.

---

## REFERENCE_ONLY

### F14 — missing primary Arm citation for U55 / U65

The paper measures U55 and U65 across 92 validation cells and much of the formal
sweep, but cites primary manuals only for U85 ([1], [2]). Statements about
U55/U65 MAC configurations and the `AXI*` PMU family (§8.4) rest on no primary
Arm source. Add the Ethos-U55 and Ethos-U65 Technical Reference Manuals,
verified to primary-source metadata as in Phase 1 — **no metadata inferred or
reconstructed**; omit any detail that cannot be verified.

Secondary, optional: [6] (Fast Models FVP Reference Guide) is cited only in a
lump while the Fast Models version skew it would naturally support (§3.3:
11.22.35 / 11.24.13 / 11.27.25 / 11.31.28) is asserted uncited. Citing [6]
there would convert a weak reference into a load-bearing one. [3] overlaps
[1]/[2] and may simply remain as-is.

---

## Tooling

### F15 — Phase-1 consistency checker rule 11 gap

Rule 11 matches `(TA|timing[- ]adapter|Corstone|Fast Models)\s+caused` and
therefore did not catch "differed ~4× **purely by adapter state**", which
asserts causation without the word *caused*. Extend the rule with
attribution-without-*caused* forms — `purely by`, `solely`, `attributable to`,
`due to the (TA|adapter|subsystem)`, `because of the adapter` — keeping the
existing negation-context guard. The pattern set is already drafted and was used
manually in this review.

---

## Not recommended

- **No new experiment.** No scientific contradiction was found; F4 is a
  presentation conflict between two frozen artifacts answering different
  questions, not a data conflict.
- **X2 remains HOLD.** Revised RQ1 does not ask for a controlled U65-vs-U85
  substrate and no clause of its answer depends on one. X2 should not be opened
  to preserve a breadth the RQ no longer claims.
- **X4, X5 remain HOLD.** Nothing in this review bears on them.
