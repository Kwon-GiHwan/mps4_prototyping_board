# Review action plan — ordered, with correction types

No action below requires a new experiment. Ordering is by dependency and by
"least expensive action that fixes the scientific problem".

| # | action | finding | type | notes |
| --- | --- | --- | --- | --- |
| 1 | Write Related Work with citations and add a References section | B1 | `TEXT_ONLY` | blocking for submission; cover NPU/accelerator characterization, simulator-vs-hardware validation, per-layer profiling methodology, and cite the Arm toolchain authorities already used (Vela, MLEK, Corstone/FVP, Ethos-U interface/TRM material) |
| 2 | Add the thesis sentence to §1 | M6 | `TEXT_ONLY` | use the recommended thesis verbatim from the review |
| 3 | Add a ~150-word abstract | M1 | `TEXT_ONLY` | thesis, scale, headline results, explicit refusals |
| 4 | Reword RQ1 to the structural/deployability question and state the refusal at the point of asking | M3 | `TEXT_ONLY` | closes the only apparent X2 dependency |
| 5 | Restructure the contribution list into primary vs validation; add the Vela-prediction contribution; unbundle contribution 4 | M4 | `TEXT_ONLY` | keeps the count small while covering §4.2 |
| 6 | Add the platform role table to §3.1 and one primary-vs-diagnostic sentence | M5 | `TEXT_ONLY` | table already drafted in `PLATFORM_ROLE_AUDIT.md` |
| 7 | Generate 3–5 figures from frozen CSVs with scoped captions | M2 | `EXISTING_DATA_ONLY` | candidates: scaling-efficiency ladders by platform; FVP vs board normalized cost; rnnoise cross-memory group deltas; CLASS A/B agreement summary. No figure may invite cross-platform raw-cycle reading |
| 8 | Promote §4.6 to its own section ahead of hardware validation | Mo1 | `TEXT_ONLY` | keep the "not an RQ" statement explicit |
| 9 | Move interpretive paragraphs out of §4.6, §5 and §6.6 into Discussion | Mo2 | `TEXT_ONLY` | leave one-line pointers in Results |
| 10 | Group the 14 limitations under six themes | Mo3 | `TEXT_ONLY` | simulation validity · platform comparability · instrumentation paths · PMU semantics · board scope · causal identifiability |
| 11 | Add platform/TA role framing to §2 Background | Mo4 | `TEXT_ONLY` | one short paragraph |
| 12 | Add the X3 qualification table beside the results | Mo5 | `EXISTING_DATA_ONLY` | reuse `X3_METRIC_QUALIFICATION.csv` categories |
| 13 | Fix minors mi1–mi4 | minors | `TEXT_ONLY` | workload span table reference; V13–V15 appendix pointer; §6.1 dnn_s clause; header date |
| 14 | Re-run the X3-integration consistency checks and re-freeze the manuscript | — | `TEXT_ONLY` | new tag; do not move existing manuscript tags |

```
TEXT_ONLY            12
EXISTING_DATA_ONLY    2
X2 / X4 / X5          0
OTHER_NEW_EXPERIMENT  0
```

Actions 1–6 are sufficient to move the verdict from
`READY_WITH_MAJOR_TEXT_EDITS` toward `READY_WITH_MINOR_EDITS`; 7–13 are quality
and readability; 14 closes the loop.
