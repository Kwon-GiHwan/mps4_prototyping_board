# Stage 1 fingerprint — boots 65–71 (contract `evidence/stage1/contract.md`, frozen in `a23029a`)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**
- Image APP `2c2fa435…` (deploy evidence `~/evsweep/evidence_m13`); profile `config/mlek_baseline.json`.
- Medians over measured RUNs 6–35. Full statistics: `summary.csv` / `summary.json`; every RUN: `per_run.csv`.

## Gate

| workload | class | boot | gate | status |
| --- | --- | --- | --- | --- |
| kws_micronet_m | model | 65 | BASELINE_PASS | VALID |
| ad_medium_int8 | model | 66 | BASELINE_PASS | VALID |
| mobilenet_v2_1.0_224_INT8 | model | 67 | BASELINE_PASS (MLEK golden, amendment 1) | VALID |
| conv3x3 | isolated_operator | 68 | BASELINE_FAIL — R3 on 35/35 RUNs: 29 OFM bytes ≠ TFLite, max \|diff\| 1, first at 257 | UNRESOLVED |
| dw3x3 | isolated_operator | 69 | BASELINE_PASS | VALID |
| pw1x1 | isolated_operator | 70 | BASELINE_FAIL — R3: 223 bytes, max 1, first at 47 | UNRESOLVED |
| fc1024 | isolated_operator | 71 | BASELINE_FAIL — R3: 1 byte, max 1, at 277 | UNRESOLVED |

For the three failures: knobs were honoured (rc 1 is the vendor output check, not 0x7D), there was no overflow, and
the counters were consistent. The mismatch pattern is the same in every RUN. Under the contract these operators get
no fingerprint.

## Table (models and isolated operators)

| workload | class | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | model | 15,556,352 | 90,930 | 171.1 | 16.7% | 62.1% | 26.9% | 0.0026 | 0.0010 | 0.445 | 0.174 | 0.82% |
| ad_medium_int8 | model | 62,346,720 | 146,412 | 425.8 | 41.6% | 64.0% | 65.0% | 0.0018 | 0.0007 | 0.768 | 0.301 | 0.57% |
| mobilenet_v2_1.0_224_INT8 | model | 300,775,552 | 1,448,582 | 207.6 | 20.3% | 39.7% | 51.1% | 0.0036 | 0.0012 | 0.742 | 0.241 | 0.10% |
| conv3x3 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| dw3x3 | isolated_operator | 3,612,672 | 144,225 | 25.0 | 2.4% | 19.6% | 12.5% | 0.0003 | 0.0147 | 0.009 | 0.368 | 0.25% |
| pw1x1 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| fc1024 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |

## Observations (descriptive only, no cause decided)

- **Deterministic vs. variable:** MAC_ACTIVE and all four beat counters are identical in all 30 measured RUNs of
  every valid workload. NPU_ACTIVE varies: CV 0.10–0.82 %.
- **Decomposition (M6):** peak efficiency = active ratio × active-cycle efficiency per RUN; residual ≤ 6e-17.
- **Models:**
  - ad_medium has the highest peak efficiency (41.6 %); its active ratio and active-cycle efficiency are both
    about 64–65 %.
  - kws has a similar active ratio (62.1 %) but the lowest active-cycle efficiency (26.9 %).
  - mobilenet has the lowest active ratio (39.7 %) with a middle active-cycle efficiency (51.1 %).
- **dw3x3** (the only valid operator):
  - Peak efficiency 2.4 %, active ratio 19.6 %, active-cycle efficiency 12.5 % — all the lowest of any valid
    workload.
  - Its EXT traffic per MAC (0.0147) is 12–21× the models' and its EXT demand per NPU cycle (0.368) is the highest.
    Its SRAM traffic is the lowest (0.009 beats/cycle).
- **Cycles vs. N_MAC:** dw3x3 needs 144k NPU cycles for 3.6M MACs. kws needs 91k cycles for 15.6M MACs: 4.3× the
  MACs in 0.63× the cycles.
- **M11:** SRAM_ENABLED_CYCLES and EXT_ENABLED_CYCLES are equal to each other in every workload and about
  2 × PMCCNTR, so they count memory-clock cycles over the whole window. Kept as raw values, as the contract says.
- **Consistency with Stage 0:** NPU_ACTIVE medians match the stage-0 baselines: kws 90,930 vs 90,767 (boot 59), ad
  146,412 vs 145,764 (boot 60), mobilenet 1,448,582 vs 1,447,422 (boot 64).

## POST_HOC_DESCRIPTIVE — the three UNRESOLVED operators (not fingerprint data, not used for routing)

Medians of the same metrics, reported only to inform the correctness decision. Their outputs did not pass R3.

| operator | NPU cycles | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 213,821 | 52.8 % | 79.2 % | 66.7 % | 0.0004 | 0.0004 | 0.199 | 0.238 |
| pw1x1 | 158,632 | 15.8 % | 19.8 % | 80.0 % | 0.0014 | 0.0020 | 0.221 | 0.321 |
| fc1024 | 127,384 | 0.8 % | 3.2 % | 25.0 % | 0.0000 | 0.0633 | 0.000 | 0.521 |
