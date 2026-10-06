# Amendment 1 to the step-2 contract (2026-10-07, after boot 14 = MODEL_FAILS, before the diagnostic data)

## Instrumentation added (no change to the measured sequence)

- Vendor copy, change 2: `irq_never_triggered = false` at `test_u85` entry (per run, not per boot).
- Record field 104 `vendor_rc` = `test_u85`'s own return (0 pass, 1 QREAD mismatch, 2 output mismatch,
  3 IRQ mask mismatch, +1 IRQ timeout), DRAM-family builds only (earlier images stay byte-identical).
- The driver archives the 47 base record fields (incl. NPU status / QREAD at close) per run.

## Diagnostic boots (one deploy, two REBOOTs)

Ids: `cycle` 17, `npu_idle` 32, `npu_active` 35, `sram_enabled_cycles` 140, `ext_enabled_cycles` 396; 1 set × 3.
- Boot 15: mobilenet blob with knobs **OFF** (every region on EXT/DRAM, as kws in step 1).
- Boot 16: mobilenet blob with the step-2 split ports (as boot 14).

Preregistered reading, closed set per boot: `RUNS_CORRECT` (vendor_rc 0 on ≥ 1 run) / `OUTPUT_MISMATCH`
(vendor_rc 2 or 3) / `IRQ_TIMEOUT` (vendor_rc odd, NPU idle) / `OTHER`. The pair decides whether the boot-14
failure belongs to the model size (both fail) or to the split-port placement (15 correct, 16 fails).
