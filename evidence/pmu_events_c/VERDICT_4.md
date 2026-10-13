# Tier C step 4 — verdict

Contract: `docs/superpowers/specs/2026-10-07-pmu-model-step4-contract.md` (frozen in `0fd8793` before boot 21).
Image: MODEL APP `0f215ef5…` (deploy `deploy_step4/`, source == destination). Board: FI101 r1p0 via `ssh gihwan`.
Launcher output: `step4.nohup.out`. All three campaigns exit 0, refusal none, both consistency checks PASS.

| boot | workload | runs valid | vendor_rc | OFM vs reference | verdicts |
| --- | --- | --- | --- | --- | --- |
| 21 (4a) | ad_medium_int8, all EXT | 15/15 | 0 | 0 bytes differ | NONZERO 37 / ZERO 2 (39) |
| 22 (4b) | int8 BATCH_MATMUL x·xᵀ, all EXT | 15/15 | 0 | 0 bytes differ | NONZERO 13 / ZERO 26 (39) |
| 23 (4c) | kws_micronet_m, all EXT, AXI limit 0x00020000 | 9/9 | 0 | 0 bytes differ | NONZERO 13 / ZERO 7 (20) |

## Target ids (values = 3 repeats)

| id | name | boot 21 (FWD) | boot 22 (MatMul) |
| --- | --- | --- | --- |
| 84 | wd_stalled_by_ws_fc | **NONZERO** [114622, 114831, 104912] | ZERO |
| 90 | wd_trans_ws_fc | **NONZERO** [3458 ×3] | ZERO |
| 85 | wd_stalled_by_ws_tc | ZERO | **NONZERO** [8937, 6061, 8366] |
| 91 | wd_trans_ws_tc | ZERO | **NONZERO** [1024 ×3] |
| 116–119 | wd_trans_ws_sc0..3 | NONZERO | ZERO |

| id | name | boot 23 |
| --- | --- | --- |
| 399 | ext_wr_stall_limit | **NONZERO** [283782, 283782, 282088] |
| 655 | ext0_wr_stall_limit | **NONZERO** [177507 ×3] |
| 671 | ext1_wr_stall_limit | **NONZERO** [106275, 106276, 106275] |
| 388 | ext_wr_trans_accepted (control) | NONZERO [3563 ×3] |

## Preregistered readings

- Row 1 ("4a: 84 or 90 NONZERO, 4b: 85 and 91 ZERO → consistent with fc = FWD"): **NOT MET as written** —
  4a holds, but 4b's 85/91 are NONZERO. The row was drafted wrongly (the intended condition was 4a's 85/91 ZERO);
  the frozen text stands, and the correction is amendment 1. Under the contract as frozen, the fc mapping is
  therefore not supported by a preregistered reading. `POST_HOC_DESCRIPTIVE`: 84/90 count only on the
  FWD workload (4a) and stay at zero on the MatMul workload (4b), and 85/91 do the reverse.
- 4b: 85 and 91 NONZERO → **consistent with tc = MatMul / IFM2-as-weights path**.
- 4c: 399/655/671 NONZERO → **EXT write limit counters count**.

Limit, as the contract states: the fc/tc names are driver-only (TRM: Reserved). This shows that the counters
count on a workload whose cms has that path and stay at zero on the other workload. It does not prove the
documented meaning, because no document defines one.

## Union after step 4 (`step4_union_first_nonzero.csv`)

TRM-110 ever NONZERO: **81** (step 3: 78). Never: 29 = `no_event`, 6 `ecc_*`, 22 `sram2_*`/`sram3_*` (no such
port at 1024 MACs). Driver-only Reserved-61 ever NONZERO: **57** (step 3: 53). Never: 4 =
`sram2/3_wr_trans_completed_m/s`.
