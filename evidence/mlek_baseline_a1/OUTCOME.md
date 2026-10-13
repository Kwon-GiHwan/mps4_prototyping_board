# MLEK baseline — mobilenet under amendment 1 (boot 64)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**
- Image APP `2c2fa435…` (deploy evidence `~/evsweep/evidence_m12`).
- Profile `config/mlek_baseline.json`; manifest `config/mlek_baseline.manifest.a1.json`; contract
  `docs/specs/mlek-baseline.md` amendment 1, frozen in `c10b32a`.
- Blob `0d51cf9e…`: cms `884470be…` (= boot 61), IFM `be4e0171…`, golden = MLEK FI101 OFM `6f5b50a8…`.

| workload | boot | gate | npu_active median (30) | MLEK ACTIVE median | Δ | SRAM/EXT rd/wr beats = MLEK | outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet_v2_1.0_224_INT8 | 64 | BASELINE_PASS (35/35 RUNs byte-exact vs MLEK golden, B4 hashes match) | 1,447,421.5 | 1,448,049 | −0.04 % | yes | **MLEK_EQUIVALENT** |

Numerical-difference diagnostic (not used for pass/fail): MLEK = custom vs tflite_runtime → 7 bytes at 540, 620, 825,
880, 886, 912, 972, signed diff +2/+1/+1/−1/−16/+8/+2, max 16.

## Stage-0 baseline status (all TA profile 1)

| workload | boot | criterion | outcome |
| --- | --- | --- | --- |
| kws_micronet_m | 59 | original | MLEK_EQUIVALENT |
| ad_medium_int8 | 60 | original | MLEK_EQUIVALENT |
| mobilenet_v2_1.0_224_INT8 | 61 | original (TFLite-exact) | UNRESOLVED (kept) |
| mobilenet_v2_1.0_224_INT8 | 64 | amendment 1 (MLEK-golden exact) | MLEK_EQUIVALENT |

Under the section-3 overall rule, applied to the current criterion for each workload (59, 60, 64): **MLEK_EQUIVALENT**.
