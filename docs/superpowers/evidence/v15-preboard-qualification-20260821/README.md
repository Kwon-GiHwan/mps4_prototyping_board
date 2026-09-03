# V15 pre-board qualification — the real candidate, on canonical artifacts

Run 2026-08-21 in the qualified container. **No board was touched.**

Everything before this point had been exercised over synthetic fixtures. This is
the first pass with a real V15 candidate, real gate output, a real sealed
manifest, and a comparison mode resolved through that chain rather than through
dictionaries built to resolve.

## The candidate

| | |
| --- | --- |
| raw ELF | `c2373581…` — informational, path-sensitive |
| **analysis ELF** | `49d22540…` — the identity, and what the gates read |
| `APP.BIN` | `4967fa39…` |
| `VECTORS.BIN` | `6864a22b…` |
| `DDR.BIN` | `81d37a21…` |
| generated runner | `7e62c2f3…` |
| generated vendor | `0d4dca52…` |

## Gates, run against the canonical analysis ELF

| gate | verdict | measured |
| --- | --- | --- |
| Task 6 S5-only boundary | PASS | 1 STATUS read per iteration, deciding register `r2` |
| Task 7 Q↔S5 equivalence | PASS | 6 instructions/iteration; `OBSERVABLE_LOAD, OBSERVABLE_TEST, EXIT_BRANCH, INDUCTION, INDUCTION, BACK_EDGE` |
| Task 8 post-freeze tail | PASS | 40 instructions, MMIO `QREAD,STATUS`, predicate mask `0x33F` |

The V14 Q side of the comparison is the reconstructed analysis reference
`24c31bf4…`, whose objcopy output is the artifact set the board ran.

## The chain

```
equivalence_evidence.json  ─┐
                            ├─ digest-cited by ─→ build_manifest.json
static_evidence.json      ─┘                       │
                                                   ↓
                                        comparison_mode = Q_S5_EQUIVALENT
```

`manifest_sha256 = 42bb2310…` (taken over the finished manifest from outside it)
`candidate_identity = 0c3ac91a…` (computed from the artifact and evidence set)

## Where it stops, and why

```
deployment_verified       False
remaining_before_a_cell   source artifact equality, destination read-back
```

Pre-board qualification ends here deliberately. The remaining gate compares what
was deployed against what landed on the device, and there is no honest way to
run it without deploying. It is absent rather than satisfied with placeholder
digests.

Consequently Task 11 is `REQUALIFIED_TO_MANIFEST_PENDING_DEPLOYMENT`:
`static_image_evidence` and `build_manifest` now carry the mode on real
evidence; `verified_deployment_context` and `collector` do not yet. A mode that
has not reached a run is not an end-to-end mode.

## Status

| | |
| --- | --- |
| V15 board work | **NOT AUTHORIZED** |
| Board | NOT TOUCHED |
| Production `END_ONLY` | FROZEN |
| MLEK | BLOCKED |

## Pre-board gate

`preflight_result.json`, produced by `host/preflight_pmu_completion_s5_only_control.py`
against the documents above and the measured artifact digests.

| check | |
| --- | --- |
| artifacts match the built candidate | PASS |
| gates passed | PASS |
| gates ran on the analysis ELF | PASS |
| reference is the pinned V14 Q analysis ELF | PASS |
| evidence binding | PASS |
| comparison mode established | PASS |
| candidate identity recomputes | PASS |
| poll count contract | PASS |
| source artifact equality | PENDING_DEPLOYMENT |
| destination read-back equality | PENDING_DEPLOYMENT |
| verified cell context issued | PENDING_DEPLOYMENT |
| fresh boot | PENDING_DEPLOYMENT |
| campaign, three boots × ten runs | PENDING_DEPLOYMENT |
| original image restored | PENDING_DEPLOYMENT |

**overall: `PENDING_DEPLOYMENT`** — not PASS, and unreachable as PASS while any
board-dependent check is outstanding. Each of the six is named rather than
omitted, because a reader who counts eight PASSes and sees nothing else would
conclude the candidate is cleared.

`board_authorization: NOT_REQUESTED`. No SD write, no deploy, no UART campaign
has been performed or attempted.

## The anchor

This directory, with the state below, is the pre-board anchor. It is fixed
*before* any board authorization is sought, so that it records what was known in
advance rather than being written up afterwards.

| | |
| --- | --- |
| Task 6/7/8 on canonical artifacts | PASS |
| Task 11 | `REQUALIFIED_TO_MANIFEST_PENDING_DEPLOYMENT` |
| Task 14A collector mechanics | PASS |
| Task 14B final positive path | `BLOCKED_PENDING_DEPLOYMENT` |
| `deployment_verified` | `False` — not a PASS |
| V15 board work | NOT AUTHORIZED |
| Production `END_ONLY` | FROZEN |
| MLEK | BLOCKED |
