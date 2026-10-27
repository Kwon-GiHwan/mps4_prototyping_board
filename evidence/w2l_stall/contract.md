# wav2letter RUN stall — cause, one hypothesis at a time (frozen 2026-10-28, before boot 90)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Diagnostic, not a measurement:
no number from these boots enters `results/`.

## Symptom (x1 boots 87, 89)

`wav2letter_pruned_int8` (blob `5b8c9d06…`, image `38ce118c`) loads (14.5 MB, LOAD_MODEL_END answered) and the RUN
is ACKed, but no RUN_COMPLETE arrives within 120 s (boot 87) or 900 s (boot 89). Stock MLEK ran the same model on
the same board on 2026-08-25 (NPU ACTIVE 4,141,085, `eaa1fa7` on the old branch): the stall is on the runner side.

## Candidates (static analysis 2026-10-28)

| # | candidate | what is unique to wav2letter |
| --- | --- | --- |
| C1 | S DRAM footprint | the runner places cmd, const, arena from `0x7010_0000`; wav2letter reaches `0x70F1_B040`, every model that ran stayed below `0x7050_C100` (mobilenet) |
| C2 | operators | `Transpose` and `Conv2D` with a LUT sub-op (LeakyReLU) occur in no other measured model; the softmax lowering (CLZ, SHL, ReduceSum, …) also occurs in mobilenet, which runs |
| C3 | IRQ handling / wait | the vendor handler clears the IRQ only when STATUS bit 1 is set; an error IRQ without it re-enters forever. The wait loop is 200,000,000 iterations whose duration was never measured |

Ruled out: aliasing of the S DRAM placement with the staging window (DDR4 block 0 S `0x7xxx_xxxx` vs block 1 S
`0x9xxx_xxxx`, MLEK `mem_regions.h`), fast scratch outside SRAM (`0x3110_0000 + 333,888` < `0x3140_0000`), command
stream addresses outside their regions (Vela `--verbose-register-command-stream`: region 0 up to `0xDD13D0` <
const_len).

## Step 1 — C1 (boot 90)

Blob `kws_micronet_m.c1pad.pmwl` (`e484e72d…`) = the x1 control blob `f11271cb…` (Stage 1 boot 65) with zero
padding appended and two header words changed (`const_len` 145,728 → 14,491,648, `total_len` 148,944 →
14,494,352; `make_padded_blob.py`). The runner's const copy then spans 14.5 MB and the arena lands at
`0x70ED_2B00`, wav2letter's arena base. Command stream, constants, IFM and golden are unchanged.

Image `38ce118c` (staging `~/evsweep_x1c`), profile `mlek_r10` (10 RUNs), event ids = x1's, RUN wait 120 s.

| outcome | condition | reading |
| --- | --- | --- |
| `C1_REFUTED` | 10 RUNs complete, vendor_rc 0, OFM exact | the footprint (CPU copy range, NPU arena at the top) is not the cause → step 2 (C2/C3) |
| `C1_SUPPORTED` | the RUN stalls like wav2letter (no RUN_COMPLETE in 120 s) | the footprint is enough to stall; locate it next (CPU copy vs NPU access) |
| `C1_OTHER` | anything else (refusal, OFM mismatch, load failure) | recorded as is, no conclusion on C1 |

### Step 1 result (boot 90, recorded 2026-10-28) — `C1_REFUTED`

Deploy `~/evsweep/evidence_w2l_c1` (APP `38ce118c`, VECTORS `589f8b88`, DDR `81d37a21`, read back after deploy).
Raw data `raw_c1/` (board root `~/evsweep/evidence_w2l_c1r`). **TA state: profile 1.**

- 10/10 RUNs complete: `run_rc` 0, `vendor_rc` 0, `ofm_mismatch_count` 0, `run_valid` True in every RUN.
- `mac_active` 56,450 in every RUN (= Stage 1 and the x1 control); `npu_active` 90,482–92,317, inside Stage 1's
  range [89,884, 92,356].
- PMCCNTR window 246.01 M cycles per RUN (the kws control: a few M): the 14.5 MB CPU copy into S DRAM
  is inside the window and finishes every RUN.

Reading: the CPU copy over wav2letter's whole S DRAM range and NPU arena traffic at `0x70ED_2B00` work. The
footprint alone does not stall a RUN. NPU reads of constants above `0x7050_C100` are not covered by this step
(kws reads its constants at their original low offsets). Next: step 2 (where the NPU stops, C2/C3).
