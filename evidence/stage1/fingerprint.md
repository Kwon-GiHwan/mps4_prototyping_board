# Stage 1 fingerprint — boots 65–74 (contract `evidence/stage1/contract.md`, frozen in `a23029a`; amendment 2 for boots 72–74)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**
- Image APP `2c2fa435…`. Deploy evidence: `~/evsweep/evidence_m13` (boots 65–71) and `~/evsweep/evidence_m14`
  (boots 72–74). Profile `config/mlek_baseline.json`.
- Medians over measured RUNs 6–35. Full statistics: `summary.csv` / `summary.json`. Every RUN of both datasets:
  `per_run.csv` (column `dataset`: `s1` = boots 65–71, `a2` = boots 72–74).
- Correctness:
  - kws, ad, dw3x3: byte-exact vs tflite_runtime on the seed-1 input.
  - mobilenet: byte-exact vs MLEK FI101 on MLEK's input (amendment 1).
  - conv3x3@a2, pw1x1@a2, fc1024@a2: byte-exact vs MLEK FI101 on MLEK's input (amendment 2,
    `workload_manifest/manifest.a2.json`, goldens in `a2/mlek_golden/`).

## Gate

| workload | class | boot | dataset | gate | status |
| --- | --- | --- | --- | --- | --- |
| kws_micronet_m | model | 65 | s1 | BASELINE_PASS | VALID |
| ad_medium_int8 | model | 66 | s1 | BASELINE_PASS | VALID |
| mobilenet_v2_1.0_224_INT8 | model | 67 | s1 | BASELINE_PASS (MLEK golden, amendment 1) | VALID |
| conv3x3 | isolated_operator | 68 | s1 | BASELINE_FAIL — R3 on 35/35 RUNs: 29 OFM bytes ≠ TFLite, max \|diff\| 1, first at 257 | UNRESOLVED (kept) |
| dw3x3 | isolated_operator | 69 | s1 | BASELINE_PASS | VALID |
| pw1x1 | isolated_operator | 70 | s1 | BASELINE_FAIL — R3: 223 bytes, max 1, first at 47 | UNRESOLVED (kept) |
| fc1024 | isolated_operator | 71 | s1 | BASELINE_FAIL — R3: 1 byte, max 1, at 277 | UNRESOLVED (kept) |
| conv3x3@a2 | isolated_operator | 72 | a2 | BASELINE_PASS (MLEK golden, amendment 2) | VALID |
| pw1x1@a2 | isolated_operator | 73 | a2 | BASELINE_PASS (MLEK golden, amendment 2) | VALID |
| fc1024@a2 | isolated_operator | 74 | a2 | BASELINE_PASS (MLEK golden, amendment 2) | VALID |

The `s1` rows are the recorded results of boots 68/70/71 and are not re-judged.

Boots 72–74:
- 105/105 RUNs passed B1–B4, R1–R5 and R6s.
- Knobs were honoured in every RUN and there was no overflow.
- The OFM equals the MLEK FI101 golden byte for byte in every RUN.

Numerical-difference diagnostic, MLEK FI101 vs tflite_runtime on the same MLEK input (not used for pass/fail):

| operator | mismatch bytes | max \|diff\| |
| --- | --- | --- |
| conv3x3 | 20 | 1 |
| pw1x1 | 217 | 1 |
| fc1024 | 0 | 0 |

## Model table

| workload | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | 15,556,352 | 90,930 | 171.1 | 16.7% | 62.1% | 26.9% | 0.0026 | 0.0010 | 0.445 | 0.174 | 0.82% |
| ad_medium_int8 | 62,346,720 | 146,412 | 425.8 | 41.6% | 64.0% | 65.0% | 0.0018 | 0.0007 | 0.768 | 0.301 | 0.57% |
| mobilenet_v2_1.0_224_INT8 | 300,775,552 | 1,448,582 | 207.6 | 20.3% | 39.7% | 51.1% | 0.0036 | 0.0012 | 0.742 | 0.241 | 0.10% |

## Isolated-operator table (valid fingerprints)

| operator | boot | input | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 72 (a2) | MLEK | 115,605,504 | 213,654 | 541.1 | 52.8% | 79.3% | 66.7% | 0.0004 | 0.0004 | 0.200 | 0.238 | 0.38% |
| dw3x3 | 69 (s1) | seed 1 | 3,612,672 | 144,225 | 25.0 | 2.4% | 19.6% | 12.5% | 0.0003 | 0.0147 | 0.009 | 0.368 | 0.25% |
| pw1x1 | 73 (a2) | MLEK | 25,690,112 | 158,742 | 161.8 | 15.8% | 19.8% | 80.0% | 0.0014 | 0.0020 | 0.220 | 0.321 | 0.28% |
| fc1024 | 74 (a2) | MLEK | 1,048,576 | 127,044 | 8.3 | 0.8% | 3.2% | 25.0% | 0.0000 | 0.0633 | 0.000 | 0.522 | 0.34% |

`fingerprint_table.md` is the tool's own output and holds every entry, including the three `s1` BASELINE_FAIL rows.

## Observations (descriptive only, no cause decided)

- **Deterministic vs. variable:**
  - MAC_ACTIVE and all four beat counters are identical in all 30 measured RUNs of every valid workload.
  - NPU_ACTIVE varies, with CV 0.10–0.82 %.
- **Decomposition (M6):** peak efficiency = active ratio × active-cycle efficiency per RUN. The largest residual is
  1.1e-16.
- **Models:**
  - ad_medium has the highest peak efficiency (41.6 %); its active ratio and active-cycle efficiency are both
    about 64–65 %.
  - kws has a similar active ratio (62.1 %) but the lowest active-cycle efficiency of the models (26.9 %).
  - mobilenet has the lowest active ratio (39.7 %) with a middle active-cycle efficiency (51.1 %).
- **Operators** (relative to one another):
  - conv3x3 has the highest peak efficiency of all valid workloads (52.8 %). Its active ratio is the highest of
    all (79.3 %), and its traffic per MAC is among the lowest (SRAM 0.0004, EXT 0.0004).
  - pw1x1 has the highest active-cycle efficiency of all (80.0 %) but an active ratio of only 19.8 %, so its peak
    efficiency is 15.8 %. Compared with conv3x3 it has 0.22× the MACs in 0.74× the cycles. Its traffic per MAC is
    3.7× (SRAM) and 4.5× (EXT) conv3x3's.
  - dw3x3 is low on all three efficiencies (2.4 / 19.6 / 12.5 %). Its EXT beats/MAC (0.0147) is 33× conv3x3's.
  - fc1024 has the lowest active ratio (3.2 %) and peak efficiency (0.8 %) of all. Its EXT traffic per MAC (0.0633)
    and per NPU cycle (0.522) are the highest of all, and it has no SRAM traffic (0 beats).
  - The NPU cycles span only 1.7× (127k–214k) across the four operators, while N_MAC spans 110× (1.0M–115.6M).
- **M11:** SRAM_ENABLED_CYCLES and EXT_ENABLED_CYCLES are equal to each other in every workload and about
  2 × PMCCNTR, so they count memory-clock cycles over the whole window. They are kept as raw values, as the contract
  says.
- **Consistency with Stage 0:** NPU_ACTIVE medians match the stage-0 baselines: kws 90,930 vs 90,767 (boot 59), ad
  146,412 vs 145,764 (boot 60), mobilenet 1,448,582 vs 1,447,422 (boot 64).

## POST_HOC_DESCRIPTIVE — seed-1 input (boots 68/70/71) vs MLEK input (boots 72–74), same blob cms

Not preregistered. These values are reported only, are not fingerprint data and are not used for routing. The
`s1` RUNs failed R3, so their numbers come from outputs that were not accepted.

| operator | MAC_ACTIVE and 4 beat counters | NPU_ACTIVE median s1 → a2 |
| --- | --- | --- |
| conv3x3 | identical | 213,821 → 213,654 (−0.08 %) |
| pw1x1 | identical | 158,632 → 158,742 (+0.07 %) |
| fc1024 | identical | 127,384 → 127,044 (−0.27 %) |

Changing the input changed neither the activity nor the traffic counts. NPU_ACTIVE moved by less than its own
run-to-run range: conv3x3@a2 ran 212,357–215,293 cycles, pw1x1@a2 157,806–159,375 and fc1024@a2 126,617–127,886.
