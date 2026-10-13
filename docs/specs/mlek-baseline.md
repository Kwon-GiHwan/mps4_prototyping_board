# MLEK baseline profile, per-run gate, verification (frozen 2026-10-13, before boot 59)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`) for every RUN under this contract.**

## 1. Profile (stage 0)

`config/mlek_baseline.json` fixes every measurement condition; `config/baseline_ids.txt` the PMU set.

| condition | value |
| --- | --- |
| Vela | 5.0.0, MLEK options (ethos-u85-1024, Performance, Dedicated_Sram, Ethos_U85_SYS_DRAM_Mid_1024, MLEK ini) |
| TA | profile 1 |
| AXI limits | SRAM 0x20F0B, EXT 0x21F3F |
| regions | cmd, const, arena on EXT (DDR); fast scratch on the SRAM port |
| fast scratch | on-chip SRAM at 0x31100000 (MLEK: on-chip SRAM at 0x31000000, which the runner's own code occupies) |
| POWER_CTRL | 0 (MLEK driver value) |
| input | seeded int8, seed 1; reference OFM from tflite_runtime on the original model |
| image | APP `2c2fa435…`, VECTORS `d8c32b14…`, DDR `81d37a21…` (digests in the profile) |
| PMU set | 17 cycle, 32 npu_idle, 35 npu_active, 48 mac_active, 130/135 SRAM rd/wr beats, 386/391 EXT rd/wr beats |
| repetitions | 35 RUNs per boot, first 5 dropped, 30 measured |

The packer takes `--profile` and refuses a Vela version or option list that differs from the profile.
The resulting blob digests are recorded once in `config/mlek_baseline.manifest.json` and then frozen.
Remaining static differences from MLEK: `evidence/runner_gap/mlek_diff_audit.md` (items 9–11, 13–15).

## 2. Per-run gate (`host/baseline_gate.py`)

A workload's data is used only if every check passes. Result: `BASELINE_PASS` / `BASELINE_FAIL` / `UNPROVEN`
(missing file or field).

Per boot:
- B1 image digests in the record == profile `image`
- B2 blob sha256 == manifest; blob knob words == profile knobs + TA profile; blob cms sha256 == manifest
- B3 requested ids == `baseline_ids.txt`; coverage complete; no refusal; RUN count == `repeats`

Per RUN (all RUNs, warm-up included):
- R1 `run_valid`
- R2 `run_rc == 0` (covers `PMWL_KNOB_NOT_HONOURED` 0x7D: read-back of the TA registers, POWER_CTRL, the register knobs)
- R3 `vendor_rc == 0` and `ofm_mismatch_count == 0` (output equals the reference)
- R4 no event overflow
- R5 `npu_active > 0` and `npu_active <= window_cycles`
- R6 `cycle` within 1 % of `window_cycles`

Also amended here: `pmu_events_parse.run_validity` model mode gains the term `knobs_honoured`
(`run_rc != 0x7D`), so a read-back failure no longer passes as a valid RUN.

## 3. Verification (boots 59 kws, 60 ad_medium, 61 mobilenet)

Per workload, from the 30 measured RUNs, against `docs/reference/mlek_board_reference.json`:
- `UNRESOLVED` if the gate is not `BASELINE_PASS`
- `MLEK_EQUIVALENT` if the medians of SRAM rd/wr and EXT rd/wr beats equal MLEK B1 exactly **and**
  |median npu_active − MLEK ACTIVE_median| ≤ 1 % of MLEK ACTIVE_median
- `MLEK_DIFFERENT` otherwise

Overall: `UNRESOLVED` if any workload is, else `MLEK_DIFFERENT` if any workload is, else `MLEK_EQUIVALENT`.

Descriptive only (not an outcome): change in npu_active against boots 57/58 (same image and TA profile 1, fast
scratch in DDR, POWER_CTRL vendor 2) — two variables at once, so not attributable to either.
