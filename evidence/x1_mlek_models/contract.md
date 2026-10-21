# x1 — exploratory NPU utilization of the remaining MLEK models (frozen 2026-10-21, before boot 78)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**

Owner request (2026-10-21): measure the MLEK models missing from `results/npu_utilization_mps4/` quickly, NPU
utilization items only, and add them in the same format. This is **exploratory**, outside the Stage 1 contract and
outside amendment 2: no MLEK FI101 golden is produced for these models. Every result is labelled `x1` and never
mixed into a Stage 1 table without that label.

## Scope

| boot | workload | blob | N_MAC |
| --- | --- | --- | --- |
| 78 | vww4_128_128_INT8 | `b7c15f01…` | 18,828,800 |
| 79 | wav2letter_pruned_int8 | `5b8c9d06…` | 3,491,098,000 |

`NOT_EXECUTABLE` with the current packer (1 input / 1 output only; `pack_vela_workload.py:87` path, custom op
5 in / 1 out): rnnoise_INT8 (custom op 8 in / 5 out), yolo-fastest_192_face_v4 (5 in / 2 out). Not measured.

## Protocol (unchanged from Stage 1)

- Blobs packed with `--profile config/mlek_baseline.json` (Vela 5.0.0 MLEK options, `Ethos_U85_SYS_DRAM_Mid_1024`,
  TA profile 1, knobs as in Stage 1). Both Vela outputs equal MLEK's own (sha256 equal to the FVP campaign's
  `vela_sha256`: vww4 `637711c9…`, wav2letter `4c5b6402…`).
- Image APP `2c2fa435…` (same as Stage 1 / 2A), event set `config/stage1_ids.txt`, 35 RUNs per boot, RUNs 6–35
  measured, one boot per workload.
- N_MAC: `host/container/workload_meta.py` on the original MLEK tflite (`*.meta.json` here).
- Analysis: `host/analysis/stage1.py … --add x1 <root> evidence/x1_mlek_models/manifest.x1.json`; metrics and
  definitions as in Stage 1.

## Correctness and status

Golden = tflite_runtime OFM of the original model on the seed-1 IFM (the stage-0 R3 rule). Gate as in Stage 1
(B1–B4, R1–R5, R6s).
- Gate `BASELINE_PASS` → status `VALID (x1)`.
- Gate `BASELINE_FAIL` only on R3 (OFM differs from tflite_runtime) → the counters are kept and reported as
  `UNRESOLVED (x1)`, with the mismatch count, as the `s1` operators were. No MLEK golden is made to rescue them in
  this pass.
- Any other failure → `UNRESOLVED (x1)`, not reported as a utilization value.
