# MLEK baseline verification — boots 59–61 (contract `docs/specs/mlek-baseline.md`, frozen in `f39eca8`)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Image APP `2c2fa435…`
(deploy evidence `~/evsweep/evidence_m10`). Profile `config/mlek_baseline.json` (sha256 `b2a40af9…`): fast scratch on-chip
0x31100000, POWER_CTRL 0. Gate + outcome: `host/baseline_gate.py` → `OUTCOME.json`.

| workload | boot | gate | npu_active median (30) | MLEK ACTIVE median | Δ | SRAM/EXT rd/wr beats = MLEK | outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | 59 | BASELINE_PASS | 90,766.5 | 91,431 | −0.73 % | yes | **MLEK_EQUIVALENT** |
| ad_medium_int8 | 60 | BASELINE_PASS | 145,763.5 | 145,976 | −0.15 % | yes | **MLEK_EQUIVALENT** |
| mobilenet_v2_1.0_224_INT8 | 61 | BASELINE_FAIL (R2, R3 on all 35 RUNs) | — | 1,448,049 | — | — | **UNRESOLVED** |

**Overall: UNRESOLVED** (closed set; mobilenet unresolved).

Why mobilenet fails the gate: every RUN has `run_rc=1`, `vendor_rc=2`, OFM mismatch count 5 of 1,001 bytes, max |diff| 4,
first at byte 491 — identical in every RUN and identical to the earlier TA A/B arm (`evidence/ta_ab/ta1`, fast scratch in
DDR, POWER_CTRL 2). It is the vendor output check against the tflite_runtime reference, not a knob read-back failure
(that would be rc 0x7D). The contract requires an exact output (R3), so the data is not used. Whether this is an
NPU-vs-reference rounding difference is not established here.

## POST_HOC_DESCRIPTIVE (not outcomes)

- mobilenet, boot 61, 30 measured RUNs: npu_active median 1,448,852.5 (MLEK +0.06 %); SRAM/EXT rd/wr beats equal MLEK B1.
- Against boots 57/58 and TA A/B ta1 (same image, TA 1, fast scratch in DDR, POWER_CTRL 2): kws −0.74 %, ad −0.33 %,
  mobilenet −0.26 %. Two variables changed together, so not attributable to either.
