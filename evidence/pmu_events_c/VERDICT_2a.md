# Tier C step 2 (targeted) — boot 14 verdict (contract: docs/superpowers/specs/2026-10-07-pmu-model-step2-targeted-contract.md)

Image MODEL=1 (APP 91a31abc…), blob mobilenet v2 split ports (838b2488…), 48 ids, 6 sets × 3, one boot.

## Campaign: **MODEL_FAILS**

18/18 runs rc 1 (vendor FAIL), valid_flags 0xD (no RC_OK), seam fired once per run, cycle counter valid.
All 48 ids NOT_OBSERVED. Not KNOB_NOT_HONOURED (rc would be 0x7D), not REFUSED (0x7E).

## POST_HOC_DESCRIPTIVE (no verdict depends on this)

- Every run: window ≈ 92.96 M cycles; `npu_active` ≈ 10.72 M, `npu_idle` ≈ 82.25 M (set 1). The NPU stopped
  and then sat idle until the vendor's IRQ wait gave up; the run is not merely slow.
- Traffic is deterministic across runs (e.g. `sram_rd_trans_accepted` 69 726 on every rep).
- The vendor's raw rc and the record's NPU status / QREAD at close were not archived by this driver version,
  so "completed but no IRQ" and "stopped on an error" cannot be told apart from this evidence.
- Vendor `irq_never_triggered` is never cleared (u85.c), so after one timeout every later run on the boot fails.
- Two axes changed from step 1 at once (model size, split ports); this run does not separate them.
