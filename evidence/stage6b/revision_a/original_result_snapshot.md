# Stage 6B Revision A — Original Contract Result (snapshot, 2026-11-15)

This is the result of the Revision A contract as frozen in `37b6268`, recorded before Amendment B was written. Nothing
in this file, in `compiled/` or in `results/fi101_stage6b/revision_a/` is edited by Amendment B; the amendment writes to
its own files (`amendment_b/`, `results/fi101_stage6b/revision_a/amendment_b/`).

## Identifiers

| item | sha256 |
| --- | --- |
| contract `revision_a_contract.md` (`37b6268`) | `993a807b57257749a79f802305e109f864df8c51cfccbc2ebb117fc92a235a41` |
| judge `host/analysis/stage6b_revision_a.py` (`37b6268`) | `8cd145a7e1970cd8f1690516a828fdacda57a5d3547ddc0edeb475d51c233a5f` |
| compile script `host/container/stage6b_revision_a_models.py` (`37b6268`) | `f2b0902f96009f8d98a2e79c21c4318723092cb488aa0e1c7e5e4eea82c2cfb9` |
| source manifest `revision_a_manifest.json` | `0b2befcd51a501d80bb164b78c8e377c818abbe087e3f0e27952e53826231185` |
| `results/.../revision_a_results.csv` | `f95b47486764409b369d68ee9e93daaf34346ec56305602a08748e02c96a3512` |
| `results/.../revision_a_coverage.csv` | `22339c81f28522f1be8b889047ff3fd48486b89a63e5ea4638af822923475d3e` |
| `results/.../revision_a_summary.json` | `4e93838e09b928d104ec9696ebfeebdfad703ec8b40c7d5d340c4136000a5f60` |

The 26 container records (`compiled/<cfg>.ra.json`) and the compile log: digests in `compiled.sha256`. They were
produced in the container `benchmark-runner` (gihwan), `/work/s6b_ra_compile` (every form compiled twice; the
container also holds the tflite, DRWL and `.cms.bin` files whose digests the records carry).

Reproduce: `python3 host/analysis/stage6b_revision_a.py run evidence/stage6b/revision_a/compiled <out>` at `37b6268`
gives byte-identical `revision_a_results.csv`, `revision_a_coverage.csv`, `revision_a_summary.json` (checked
2026-11-15 by re-running into a scratch directory and `cmp`).

## Result (Original Contract Result)

- 26 candidates; A0/A1/A2 each compiled twice; no provenance error (A0/A1 DRWL bytes equal Stage 6B `0c4bf4c`).
- Class (best form per candidate): EXACT_A 13, PARTIAL_A 13, NOT_REPRODUCIBLE_A 0. All 13 EXACT_A are A2
  (G09 G11 G12 G14 G23 G25 G28 G40 G41 G52 G53 G56 G57); G14 is EXACT_A in A1 as well.
- BOARD_ELIGIBLE: 0. Selection: none. Verdict **NEEDS_REVISION**, reasons "no BOARD_ELIGIBLE shape besides G14",
  "nothing selected", "board contract not written" (the judge was run before the board contract existed, as planned).

## Why the 13 EXACT_A candidates are not BOARD_ELIGIBLE (A2 form)

| check | candidates failing | recorded diff |
| --- | --- | --- |
| fusion | G09 G11 G12 G23 G25 G28 G40 G41 G52 G53 G56 G57 | scheduled ops `['Add','Conv2D','Relu6','Add']` ≠ fixed `['Add','Conv2D','Add']` |
| reference (saturation) | G14 G23 G41 | `conv_out saturated`, `final output saturated` (share strictly inside the clamp range < 0.10) |
| params, repeat, registers, package | none | — |

G14 (no fused activation in the source op) fails only the saturation rule; in A1 its `conv_out` share is 0.050 as well.
