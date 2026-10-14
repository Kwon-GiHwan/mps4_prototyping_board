# Stage 2A component fingerprint — boots 75–77 (contract `evidence/stage2a/contract.md`)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**
- Image APP `2c2fa435…`, deployed to `~/evsweep/evidence_m15`. Profile `config/mlek_baseline.json`.
- Event set `config/stage2a_ids.txt`: 35, 48, 51, 52, 55, 64, 80, 81. Events 52 and 55 are driver-derived (†).
- Medians over measured RUNs 6–35. Full statistics are in `summary.csv` / `summary.json`, and every RUN is in
  `per_run.csv`.
- Correctness (amendment 2): byte-exact vs the MLEK FI101 golden on MLEK's input.
  - conv3x3 and pw1x1 used the blobs of Stage 1 boots 72/73, unchanged.
  - dw3x3 used a new golden, `mlek_golden/dw3x3` (G1–G5 pass; vs TFLite 0 bytes).

## Gate and reproduction

| operator | boot | gate | Stage 1 reference | MAC_ACTIVE (all 30 RUNs) | NPU_ACTIVE median vs reference range | reproduction |
| --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 75 | BASELINE_PASS | boot 72 (a2, same blob) | 169,344 = 169,344 | 213,506 in [212,357, 215,293] | REPRODUCED |
| dw3x3 | 76 | BASELINE_PASS | boot 69 (s1, seed-1 input) | 28,224 = 28,224 | 144,200.5 in [143,448, 144,567] | REPRODUCED |
| pw1x1 | 77 | BASELINE_PASS | boot 73 (a2, same blob) | 31,360 = 31,360 | 158,522.5 in [157,806, 159,375] | REPRODUCED |

Across the three boots:
- 105/105 RUNs pass B1–B4, R1–R5 and R6s. Knobs were honoured and nothing overflowed.
- Every OFM equals the MLEK golden.
- Diagnostic checks S1–S3: 0 violations in every operator (recorded only, not a validity term).
- Programming the Stage 2A event set instead of the Stage 1 set changed neither MAC_ACTIVE nor the NPU_ACTIVE range.
- dw3x3 also reproduced across its input change (seed 1 → MLEK).

## Component table

| operator | NPU cycles | MAC active ratio | DPU active ratio | DPU / MAC-active | AO active ratio | WD active ratio | WD stalled ratio | IB stall ratio † | W/ACC stall ratio † | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 213,506 | 79.3% | 79.3% | 1.000 | 5.9% | 11.7% | 86.2% | 18.8% | 0.0% | 0.32% |
| dw3x3 | 144,200 | 19.6% | 19.6% | 1.000 | 17.6% | 0.1% | 98.4% | 78.9% | 0.0% | 0.27% |
| pw1x1 | 158,522 | 19.8% | 19.8% | 1.000 | 16.3% | 8.6% | 59.8% | 40.8% | 14.8% | 0.31% |

† Driver-derived event (contract §2): auxiliary evidence, at most `PARTIAL_SUPPORT`.

The ratios are not additive, so no row is a time decomposition.

### Stage 1 values (separate dataset, not re-measured here)

| operator | Stage 1 boot | input | peak MAC eff. | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC |
| --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 72 (a2) | MLEK | 52.8% | 66.7% | 0.0004 | 0.0004 |
| dw3x3 | 69 (s1) | seed 1 | 2.4% | 12.5% | 0.0003 | 0.0147 |
| pw1x1 | 73 (a2) | MLEK | 15.8% | 80.0% | 0.0014 | 0.0020 |

## Relative comparison (median ratio; separation by run-to-run range, contract §7)

| metric | dw3x3 / conv3x3 | pw1x1 / conv3x3 | dw3x3 / pw1x1 |
| --- | --- | --- | --- |
| NPU cycles | 0.675 LOWER | 0.742 LOWER | 0.910 LOWER |
| MAC active ratio | 0.247 LOWER | 0.249 LOWER | 0.989 OVERLAP |
| DPU / MAC-active | 1.000 OVERLAP | 1.000 OVERLAP | 1.000 OVERLAP |
| AO active ratio | 2.96 HIGHER | 2.74 HIGHER | 1.08 HIGHER |
| WD active ratio | 0.011 LOWER | 0.732 LOWER | 0.014 LOWER |
| WD stalled ratio | 1.14 HIGHER | 0.694 LOWER | 1.64 HIGHER |
| IB stall ratio † | 4.20 HIGHER | 2.17 HIGHER | 1.94 HIGHER |
| W/ACC stall ratio † | 0 vs 0, OVERLAP | 0 → 14.8 %, HIGHER | 0.0 LOWER |
| MAC active-cycle eff. (Stage 2A mac_active) | 0.188 LOWER | 1.20 HIGHER | 0.156 LOWER |

**Largest difference from conv3x3 (question 4):**
- dw3x3: WD active ratio (0.011×, consistent with its 1,152-byte weight tensor), then IB stall ratio † (4.2×) and AO
  active ratio (3.0×).
- pw1x1: W/ACC stall ratio †, which is 0 in conv3x3 and 14.8 % in pw1x1, then AO active ratio (2.7×) and IB stall
  ratio † (2.2×).

## Observations (descriptive)

- **`mac_dpu_active` == `mac_active` in every RUN of all three operators** (105/105). With this event set, event 51
  ("at least one DPU active") carries no information beyond event 48. So the DPU / MAC-active ratio is exactly 1 and
  cannot separate the operators (question 2).
- Deterministic in all 30 measured RUNs:
  - every operator: MAC_ACTIVE and MAC_DPU_ACTIVE;
  - conv3x3 and dw3x3: also WD_ACTIVE and MAC_STALLED_BY_W_OR_ACC (0).
- Variable: NPU_ACTIVE (CV 0.27–0.32 %), the IB stall, AO_ACTIVE and WD_STALLED.
- WD_STALLED is high in the reference as well (conv3x3 86.2 %). The TRM text covers two causes: lack of weight-stream
  data, and lack of free WD buffer space, which is back-pressure from the MAC. This event set cannot tell them apart.
- **POST_HOC_DESCRIPTIVE (not preregistered).** pw1x1's driver-derived stall counters and WD_STALLED spread far more
  run to run than its NPU_ACTIVE (CV 0.31 %):
  - IB stall: 59,807–73,534.
  - W/ACC stall: 15,225–29,598, correlation −0.42 with the IB stall.
  - WD_STALLED: 78,653–96,482.

  conv3x3 and dw3x3 show no such spread. This is not used for any status.
