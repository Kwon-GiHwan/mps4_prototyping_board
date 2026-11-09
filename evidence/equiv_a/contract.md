# Equivalence experiment A — CAP and TA_EXT MAXR read-back (frozen 2026-11-09, before boot 296)

Plan: `docs/plan/equivalence_plan.md` §5 A and §8 (owner 2026-11-09: approved). **TA profile 1** (MLEK
sys_dram_mid) in every RUN. FI101 Ethos-U85 1024 MAC. Questions:

- **E1:** does the vendor path's write of 0x00021F3F to CFG_SRAM_CAP / CFG_EXT_CAP (`u85.c` 215–216) change those
  registers? MLEK never writes them, so MLEK runs with their reset value.
- **E2:** what does TA_EXT MAXR hold after MLEK's value 64 is written? The runner's profile 1 writes 0.

## Image (diagnostic; the measurement image is unchanged)

- **Sources:** `firmware/runner/diag_equiv.[ch]`. The calls in `pmwl.c` and `io_wrap.c` expand to nothing unless `-DRUNNER_DIAG_EQUIV` is set.
- **Build:** `make -f Makefile.npu_runner BUILD=build_npu_runner_equiv OWN_CFLAGS="-Werror=implicit-function-declaration -DRUNNER_DIAG_EQUIV" all` in the container tree `/work/selftest_equiv`. rc 0, all gates PASS, no warning from `runner/` or `common/`.
- **Digests:** APP `a65cf112fd07…f7`, VECTORS `4b7cc040a352…40`, DDR `81d37a219a6b…98`.
- **Check that the measurement image is unchanged:** the same tree without the flag gives APP `d0cd47756c0b…` and VECTORS `4c11ff9874f3…`, byte-identical to the measurement image `d0cd4775`. HEAD sources before the change give the same bytes.
- **Diagnostic record words:** appended after the 122 fields, so `Measurement.trailing[20:29]`.
  - RUN index since boot.
  - CAP SRAM/EXT at `__wrap_test_u85` entry. On RUN 1 this is the reset value, before any write in this boot.
  - CAP SRAM/EXT at the POWER_CTRL printf, after the vendor's writes.
  - CAP SRAM/EXT at the CPM seam.
  - TA_EXT MAXR read after writing 64, then after restoring profile 1's value.
- **The TA probe:** runs after profile 1 is applied and verified, before the NPU starts. If the restore does not read back, the RUN fails `knobs_honoured`.

## Boots (`plan.txt`): 296 kws_micronet_m, 297 ad_medium_int8

- **Blobs:** the 2B-0b `ctl` blobs, unchanged: kws `f11271cb6a2d…`, ad `55fa924c7e60…`.
- **Sets and RUNs:** sets A, C, D (`ids.txt` = 2B-2/2B-3 sets), 10 RUNs, 2 warm-up.
- **Validity:** model mode, including `knobs_honoured`.
- **Reference for the image check:** the same blobs and ids on `d0cd4775`. kws: 2B-3 amendment-1 `ctl` (boot 274). ad: 2B-3 pilot `ctl` (boot 244).
- **Re-run rule:** a boot that fails before any RUN is re-run once (amendment).

## Rules (`host/analysis/equiv_a.py`, tests `host/tests/test_equiv_a.py`, 14 mutations RED)

- **E1:**
  - `UNPROVEN` if a word is missing or no RUN 1 exists.
  - `E1_UNSTABLE` if the post-write or seam values vary between RUNs.
  - `E1_INERT` if every post-write value equals RUN 1's entry value. The write leaves the reset state MLEK runs with.
  - `E1_DIFFERS` otherwise. The runner runs with a CAP state MLEK does not have; this makes it a candidate for experiment B4.
- **E2:**
  - `UNPROVEN` if a word is missing or any restore read is not 0.
  - `E2_UNSTABLE` if the read after writing 64 varies.
  - `E2_SAME` if that read is 0. MLEK's 64 leaves the runner's register state.
  - `E2_DIFFERS` if it reads 64.
  - `E2_OTHER` for any other value.
- **Image check:**
  - Every RUN in both roots must be valid.
  - Every key the reference judges must lie within the 2B-0b tolerance. Deterministic keys: 0.1 %. Jittery keys: max(1 %, reference RUN width). Noisy keys are not judged.
  - Outcomes: `DIAG_IMAGE_REPRODUCES` / `DIAG_IMAGE_DIFFERS` / `UNPROVEN`.
  - This only says whether the diagnostic reads disturbed the RUN. It is not part of E1/E2.
- **Per model:** both models are reported. E1/E2 are properties of the board and the vendor path, so the two models must agree. If they disagree, that is reported as is.

## What the outcomes mean

- **E1_INERT and E2_SAME:** the runner and MLEK have the same CAP and TA_EXT MAXR register state during the job. E1 and E2 close as static items (R2 `APPLIED`).
- **Any DIFFERS:** the state differs. The difference becomes a one-variable experiment-B item; results are not discarded (plan §8.2).
- **Limits:**
  - "Reset value" is the value at RUN 1 entry after a board reboot. Nothing in the runner writes CAP before that point; checked in the sources.
  - That MLEK keeps this value rests on MLEK not writing these registers (static, MLEK `b2c0bb2`).
  - That MLEK's TA_EXT MAXR ends at the same value rests on the same TA instance responding to the same write.
