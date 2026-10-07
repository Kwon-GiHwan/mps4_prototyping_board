# Amendment 2 to the step-2 contract (2026-10-07) — completion vs correctness

**Written after the boot-17 diagnostic** (mobilenet OFM = reference in 996/1001 bytes, |diff| ≤ 4, deterministic),
**before any step-2 event data is valid.** Decided by the owner ("'완주'와 '정답'을 분리").

## Why

PMU event counts describe what the NPU did while executing the stream. They depend on the stream having run to
its end, not on the OFM matching a reference kernel bit for bit. Step 1's exact-match criterion excluded every
mobilenet run although each one executed completely.

## New per-run validity for model workloads (`--validity model`)

Replaces `rc_zero` and `required_flags_ok` (RC_OK cannot hold when the vendor memcmp reports a difference):

| term | condition (TRM 102685 STATUS register) |
| --- | --- |
| `vendor_rc_completed` | vendor_rc ∈ {0, 2} (pass, or output mismatch only — no QREAD/IRQ-mask/IRQ-timeout failure) |
| `flags_completed` | valid_flags has COMPLETED, OUTPUT_CHANGED, COARSE_WINDOW (0xD) |
| `stream_completed` | seam STATUS bit 5 `cmd_end_reached` = 1; bits 2 `bus_status`, 4 `cmd_parse_error`, 8 `ecc_fault`, 9 `branch_fault` = 0; seam QREAD = cms_len |

The other Tier B terms (cycle valid/progress, seam fired, mode, count, mask, codes) are unchanged.

## Correctness is recorded, not required

Every run records `vendor_rc`, OFM mismatch count, max |diff| (int8), first index. A campaign summary reports the
set of (count, max|diff|) observed. No threshold is applied, and no statement about accuracy is derived.

## Step-2 targeted run

Rerun as specified in the step-2 contract (mobilenet, split ports, 48 ids, 6 sets × 3, one boot) with
`--validity model`. Boot 14 stays MODEL_FAILS under the old criterion; it is not re-judged.
