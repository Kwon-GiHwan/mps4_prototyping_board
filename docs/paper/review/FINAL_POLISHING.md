# FINAL POLISHING PASS — record

**Authorization:** FINAL POLISHING PASS — MANAGER GO. Fix only MOD-1, MOD-2,
MIN-1, MIN-2, using the definitions read from the frozen final review.
**Input:** `paper-manuscript-phase2-frozen` = 8754295
**Finding source:** `paper-final-review-frozen` = 31f2bd4 —
`FINAL_MANUSCRIPT_REVIEW.md` was read at that tag; no finding was reconstructed
from memory.
**Output:** `paper-manuscript-submission-candidate`
**Not done:** no new experiment, no reopened analysis, no scientific claim
touched.

```
MOD-1  CLOSED      figure numbering        PRESENTATION_ONLY
MOD-2  CLOSED      delta semantics         TEXT_ONLY (+ figure regeneration)
MIN-1  CLOSED      methodology length      TEXT_ONLY
MIN-2  CLOSED      appendix title          TEXT_ONLY
```

---

## MOD-1 — figure numbering by first appearance

Figures were numbered in generation order and appeared as **1, 5, 4, 2, 3**.
They are now numbered by first appearance. The underlying data, metric
definitions, transformations and visual encodings are unchanged; only identity
and labels moved.

| appearance | section | old | **new** | old filename | **new filename** |
| --- | --- | --- | --- | --- | --- |
| 1st | 4.1 | Figure 1 | **Figure 1** | `fig1_mac_scaling.svg` | unchanged |
| 2nd | 5 | Figure 5 | **Figure 2** | `fig5_platform_sensitivity.svg` | `fig2_platform_sensitivity.svg` |
| 3rd | 6 | Figure 4 | **Figure 3** | `fig4_board_relative_cost.svg` | `fig3_board_relative_cost.svg` |
| 4th | 7.3 | Figure 2 | **Figure 4** | `fig2_u85_group_delta.svg` | `fig4_u85_group_delta.svg` |
| 5th | 7.4 | Figure 3 | **Figure 5** | `fig3_u85_memory_robustness.svg` | `fig5_u85_memory_robustness.svg` |

The renames form a cycle (2→4, 3→5, 4→3, 5→2), so the files were **regenerated
under the new names** rather than moved in place, and the old files were
deleted. Everything downstream was updated: filenames, captions, alt text, the
one in-prose reference that moved (`Figure 4 shows the two vectors` →
`Figure 3 shows …`), the Appendix A cross-reference, the generator's emission
order, its `prov()` records, and `FIGURE_PROVENANCE.json`.

Checker fixtures needed no figure-ID edit — `phase2_validation.py` iterates over
the files on disk and over caption numbers rather than hardcoding names — but
new check group **A** now pins the ordering, and group **B** asserts each of the
four superseded filenames is absent from both the manuscript and the directory.

## MOD-2 — whole-model delta versus profiled-group sum

The figure previously called +19,060 "the whole-model change". It is the sum of
the instrumented group deltas; the whole-model change is +19,000. Both figures
are now shown, distinguished, and reconciled in the figure itself:

```
whole-model observed delta            +19,000
reconstructed profiled-group delta    +19,060
────────────────────────────────────────────
residual                                   60   deterministic profiling-boundary
                                                (interrupt-service) residual —
                                                the two boundaries are not identical
```

Wording is taken from the frozen evidence, not invented: §9.5 already states
that *"each service boundary carries a small deterministic cycle residual, so
group and whole-model sums agree within that residual."* **No stronger causal
explanation is asserted, and no new residual model was introduced** — the
figure names the residual and stops.

The same distinction now appears at first use in §7.3 prose ("the profiled
groups sum to +19,060 rather than the +19,000 observed without instrumentation;
the 60-cycle difference is the deterministic profiling-boundary residual of
Section 9.5") and in the Figure 4 caption. The figure's alt text was corrected
too — it had inherited the same error.

The provenance record for this figure now carries the distinction in its
`claim` field, so a reader of `FIGURE_PROVENANCE.json` alone cannot reacquire
the confusion.

## MIN-1 — methodology length

`TEXT_ONLY`. §3.6 "Provenance and procedure" moved verbatim to **Appendix B**,
and old §3.7 became §3.6. A one-sentence pointer remains in Methodology naming
what moved and where it went, so nothing is silently dropped.

Methodology falls from 1,685 words to **1,391**, i.e. from 19 % of the body to
**16.2 %**. Every guard the final review named as load-bearing is verified still
present by check group F: the identity chain (`model SHA → Vela artifact SHA
→ …`), `SOURCE_DATE_EPOCH` build reproducibility, the exact-equality repetition
rule, and the mutation-test discipline. They now live in Appendix B rather than
§3.6; none was weakened or removed.

## MIN-2 — appendix title

`TEXT_ONLY`. "Appendix A. Exact values behind Figure 4" →
**"Appendix A. Exact values behind the board validation"**, exactly the
replacement the frozen review proposed. Its opening line now names both what it
supports (Section 6) and the figure it backs (Figure 3, renumbered). A.1 is the
rank-pair table, which supports the §6 ranking claim as much as the figure —
which is what made the old title too narrow.

---

## New issue found during polishing — reported, not fixed

Per the instruction that any new issue be classified and reported before scope
is broadened, this was found and **left unfixed**:

> **NEW-1 — three figures have no in-prose reference.** `MINOR`,
> `PRESENTATION_ONLY`. Figures **2, 4 and 5** are embedded, captioned, and
> placed adjacent to the text they illustrate, but no sentence refers to them by
> number; only Figures 1 and 3 are named in prose. Nothing is unclear or
> unsupported — each figure sits directly beneath the paragraph it belongs to
> and each caption scopes its own evidence — but a reader scanning for
> "Figure 2" finds only the caption.
>
> Fix would be three sentences of the form "Figure 2 shows …". It affects no
> scientific meaning, no number and no claim.

This was not in the authorized set, so it was not applied. It is the sole reason
the readiness verdict carries a copy-edit qualifier rather than being
unqualified.

---

## Preserved without modification

All frozen conclusions listed in the decision were checked and are untouched:
RQ1–RQ4 `CLOSED`; thesis 3/3; abstract ready; X2 `NOT_NEEDED`; raw
cross-platform cycles `NOT_COMPARABLE`; ranking / direction / saturation /
normalized ordering `ROBUST_IN_TESTED_PAIRS`; threshold scaling class
`TA_STATE_SENSITIVE`; CLASS B TA/subsystem/FM `NOT_SEPARATED`; U85 heterogeneous
group gains and losses with ublock alone insufficient and compiler/memory
`NOT_SEPARATED` and stall causality `NOT_EVALUABLE`; board `rho = 1.0` with zero
inversions and no absolute FVP–board timing equivalence; U65 bridge overall
`NOT_EQUIVALENT` with component equivalence only.

The **468×** provenance correction is preserved and verified: check group E
asserts the manuscript states 468× with its basis configuration named, and that
the string `467` does not appear anywhere in it. The historical planning value
remains only in the frozen historical documents, where it belongs.

Platform roles are unchanged, and no polishing edit made the four platforms
readable as one absolute-performance series — Figure 1's panels remain
explicitly non-comparable and Figure 2 still never pools CLASS A with CLASS B.

## Documents updated, and documents deliberately not

Updated: `FINAL_FIGURE_TABLE_AUDIT.md` (figure IDs and filenames), the figure
generator, `FIGURE_PROVENANCE.json`.

**Not modified** — these are the frozen review artifacts at 31f2bd4 and are left
exactly as frozen, so their `Figure 2` / `Figure 4` references should be read
against the mapping table above: `FINAL_MANUSCRIPT_REVIEW.md`,
`FINAL_REVIEW_META.json`, `FINAL_CLAIM_EVIDENCE_AUDIT.csv`,
`FINAL_RQ_CLOSURE_MATRIX.csv`. Likewise every earlier phase record.

**Verification level: static analysis, automated checking against frozen
artifacts, and visual inspection of the regenerated figure.**
Executed: six suites, 209 checks; figure determinism re-verified by digest
comparison across repeated generation; geometry audited for all five figures;
Figure 4 rendered and inspected to confirm the reconciliation block reads
correctly.
Not executed: no build, simulation, FVP run, board run, or measurement; no
frozen analyzer re-run; no external peer review.
