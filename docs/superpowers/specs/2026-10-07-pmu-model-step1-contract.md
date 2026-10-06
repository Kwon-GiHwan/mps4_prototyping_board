# Tier C step 1 — a Vela-compiled model through the EXT/DRAM path (contract)

Frozen 2026-10-07, **before any data exists**, after step 0b = EXT_DRAM_REACHABLE. Authorization: owner, 2026-10-07.

## Question

(Q1) Does a real Vela-compiled network (`kws_micronet_m`, ethos-u85-1024, Ethos_U85_SYS_DRAM_Low,
Dedicated_Sram) run correctly on FI101 through the vendor submit path? (Q2) Which events count for it?

## Workload blob (host, `host/pack_vela_workload.py`, seed 1)

vela → the single `ethos-u` op: raw command stream out of the COP1 payload (core-driver semantics),
read_only constants, arena / fast-scratch sizes, IFM/OFM arena offsets from `OfflineMemoryAllocation`.
IFM = seeded int8. **Reference OFM = `tflite_runtime` on the ORIGINAL model.** Header `PMWL` v1 (16 u32).
Model / vela output / blob sha256 recorded in `<blob>.json`.

## Firmware (`Makefile.pmu_events MODEL=1`, build id "PMWL" 0x504D574C)

- Vendor `u85.c` (sha256 bcd877bb…, unedited) → generated copy with ONE change:
  `BUSY_SLEEP_TIMEOUT 10000 → 200000000` (the original gives up after a few ms and would write
  `CMD=0xC` under a still-running NPU). Compiled with `USE_AXI_EXT=1` as in steps 0/0b.
- `__wrap_test_u85` (step 0b) gains a `PMU_EVENTS_MODEL` branch: reads the PMWL header from the staging
  window, refuses (rc 0x7E) unless magic, version and `total_len == model_total_length`; lays out
  cms / const / arena / fast at S DRAM 0x7010_0000 (256-B aligned); poisons the OFM, copies the IFM;
  calls the vendor with `irq_mask=0xFFFF`, `out_size=ofm_len`, `qsize=cms_len`, BASEP0=const,
  BASEP1=arena, BASEP2=fast, `out_ver` = reference OFM. **The vendor's own memcmp decides correctness →
  rc 0 means the board output equals the tflite_runtime reference byte for byte.**
- Everything else (EVENTS mode, power hold, CPM seam, record) unchanged.
- Gate `RULE_MODEL`: PMWL literal present iff MODEL=1; generated vendor carries the raised timeout and
  differs from the pinned original in that line only.

## Procedure

Tier B's 22 sets × 3 on one boot; `prime` uploads the blob (LOAD_MODEL, CRC-checked) instead of 64 zero
bytes. No GET_RESULT golden check (the 256-B test3 window does not apply); correctness = rc 0.

## Verdicts

Per-run validity: Tier B's nine terms (golden_ok not checked). Event verdicts: Tier B's closed set.
Q1 campaign verdict: `MODEL_RUNS_CORRECT` (≥ 1 valid run) / `MODEL_WRONG_OUTPUT` (every run rc 2 =
memcmp mismatch) / `MODEL_FAILS` (any other all-invalid outcome) / `MODEL_REFUSED` (rc 0x7E: blob not seen).
