# Tier C step 4 — weight-decoder FWD / tensor-core paths and EXT write limit (contract)

Frozen 2026-10-07, **before any data exists**. Authorization: owner, 2026-10-07 ("진행하자").
Plan: `docs/superpowers/plans/2026-10-07-u85-pmu-real-model-plan.md` (단계 4 조사).

No firmware change: MODEL image as step 3 (APP `0f215ef5…`, VECTORS `13c906de…`, DDR `81d37a21…`).
Host unchanged. One boot per blob, `--keep-model`, `--validity model`. Blob records: `evidence/pmu_events_c/step4_workload/`.

## Question and its limit

`wd_stalled_by_ws_fc` (84), `wd_stalled_by_ws_tc` (85), `wd_trans_ws_fc` (90), `wd_trans_ws_tc` (91) are
driver-only names (TRM: Reserved). They were ZERO on every workload so far, and those cms contain neither an FWD
`NPU_SET_WEIGHT_FORMAT` (opcode 302, bit16) nor an `NPU_OP_CONV` with `weights_ifm2` (bit16).
Mapping hypothesis, **not documented anywhere**: `fc` = Fast Weight Decoder, `tc` = tensor core (MatMul, IFM2 as weights).
A NONZERO result is reported as "counts on a workload with that path", never as a proven mapping.

## 4a — FWD (boot 21)

`ad_medium_int8`, all EXT, knobs off. Static: FWD 1, SWD 3. Blob `a710c63f…`.
Ids: `step4_wd_ids.txt` — controls 17, 32, 35 + all 36 `wd_*` (39 ids).

## 4b — tensor core (boot 22)

Hand-built int8 `BATCH_MATMUL` x[1,64,256]·xᵀ (`host/make_matmul_tflite.py`, tflite `ebfde77b…`), all EXT,
knobs off. Static: one `NPU_OP_CONV weights_ifm2=1`, FWD 0, const 0. Blob `70ce560b…`. Ids as 4a.

## 4c — EXT write limit (boot 23)

`kws_micronet_m`, all EXT (ports split off), `AXI_SRAM = AXI_EXT = 0x00020000`. Blob `b53b66e0…`.
Ids: `step4c_ids.txt` = step 3b's 19 ids + `ext_wr_trans_accepted` 388 (20 ids). Question: do `ext_wr_stall_limit` (399), `ext0_wr_stall_limit` (655),
`ext1_wr_stall_limit` (671) count when EXT writes exist under a limit?

## Verdicts (closed sets)

Per id: Tier B set (`COUNTED_NONZERO`, `COUNTED_ZERO`, `INCONSISTENT`, `NOT_OBSERVED`). Per boot: campaign as step 2.
Preregistered reading:

| result | reading |
| --- | --- |
| 4a: 84 or 90 NONZERO, 4b: 85 and 91 ZERO | consistent with fc = FWD |
| 4b: 85 or 91 NONZERO | consistent with tc = MatMul/IFM2-weights path |
| still ZERO on its workload | `UNPROVEN` — path present in cms, counter silent; no further claim |
| 4c: 399/655/671 NONZERO | EXT write limit counter counts |
| 4c: ZERO while 388 is NONZERO in the same run | `UNPROVEN` — limit possibly not reached |

A blob that does not complete (validity fails) yields `NOT_OBSERVED` for its ids; it is not rerun with edits
under this contract — a change is a new amendment.
