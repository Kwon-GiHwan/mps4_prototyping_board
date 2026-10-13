# Mobilenet OFM — MLEK board vs custom board vs TFLite (2026-10-13/14)

Purpose: find out why mobilenet fails R3 (exact output) of `docs/specs/mlek-baseline.md`. **The preregistered
mobilenet result stays UNRESOLVED; the correctness criterion is unchanged.** This is output verification only; no
performance number from the patched MLEK build is used.

## Inputs and builds

- **One input for all three:** MLEK inference_runner's own input (`std::rand()`, 150,528 B), dumped on the board.
  `ifm.bin` sha256 `be4e0171…`. Numpy seed-1 was not used: feeding it to MLEK needs DYNAMIC_MEM_LOAD, which moves the
  model to 0x90000000 (memory placement must not change).
- **MLEK:** b2c0bb2, the stage-B options plus `-DVERIFY_TEST_OUTPUT=1`. That flag does not compile at b2c0bb2. The
  owner authorised a verification-only fix of 6 lines in 3 files, all inside `#if VERIFY_TEST_OUTPUT`
  (`verify_test_output_fix6.diff`). Sources were restored by digest after the build.
  - Vela output is `031fade0…` (= stage B); images.txt is `af688281…` (= stage B).
  - Placement: `nn_model` at 0x70000000, `cache_arena` at 0x31000000. TA `ta_config_u85_sys_dram_mid` ("Configured
    TA_SRAM/TA_EXT" in the UART log).
- **MLEK capture:**
  - Deployed with `board/deploy_mlek.sh` (backs up images.txt plus APP/VECTORS/DDR.BIN).
  - The app UART listener was open before REBOOT.
  - 303,058 hex values captured = 150,528 + 1,001 + 150,528 + 1,001: nothing lost.
  - Undone with `board/restore_mlek.sh` (RESTORE VERIFIED, SOFTWARE/ listing same as before).
- **Custom:**
  - Runner image APP `2c2fa435…`, profile `config/mlek_baseline.json` (TA profile 1), same `ifm.bin`.
  - Two blobs that differ only in the golden: TFLite (boot 62) and the MLEK board OFM (boot 63). Both have the same
    cms (`884470be…`) and knobs.
  - Boot 63's first attempt never loaded an image: the MCC reported `File not found …\images.txt` although a
    read-only mount showed the card intact. It was rerun as `evidence_ofmcmp_retry`.

## Result

| comparison | mismatch count | positions | signed diff (a − b) | max abs diff |
| --- | --- | --- | --- | --- |
| MLEK board vs TFLite | 7 | 540, 620, 825, 880, 886, 912, 972 | +2, +1, +1, −1, −16, +8, +2 | 16 |
| custom board vs MLEK board | **0** (35/35 RUNs, runner byte compare) | — | — | 0 |
| custom board vs TFLite | 7 (35/35 RUNs; runner reports 7 / max 16 / first 540) | same as MLEK vs TFLite | same | 16 |

Byte values at those positions (int8):

| | 540 | 620 | 825 | 880 | 886 | 912 | 972 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MLEK board = custom board | −116 | −120 | −123 | −128 | 23 | −87 | −119 |
| TFLite | −118 | −121 | −124 | −127 | 39 | −95 | −121 |

How the three-way table follows from the measurements:
- Custom vs MLEK is measured directly: the runner compared every byte against the MLEK OFM and found 0 mismatches.
- Custom vs TFLite therefore equals MLEK vs TFLite. The runner's own summary for boot 62 (count 7, max 16, first 540)
  agrees with that (`COMPARISON.json` → `consistency_check`).

## Reading (per the owner's decision rule)

- **MLEK board == custom board** → board execution equivalence of the custom runner is confirmed for mobilenet on
  this input.
- The difference from TFLite is a numerical difference of the NPU path against tflite_runtime. MLEK on the board shows
  it too, and it is recorded separately here. With the earlier numpy seed-1 input the custom runner showed 5 bytes /
  max 4; the pattern depends on the input.

## Proposed amendment (not applied)

Replace R3 "OFM equals the tflite_runtime reference" with "OFM equals the MLEK board OFM for the same input". In
practice: a blob whose golden is the MLEK board output for the MLEK input, `ofm_mismatch_count == 0`. Mobilenet's
recorded result stays UNRESOLVED; an amended contract would apply to new boots only.
