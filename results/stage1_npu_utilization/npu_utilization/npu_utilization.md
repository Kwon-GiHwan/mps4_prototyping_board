# Stage 1 NPU utilization — boots 65–74, TA profile 1

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Ethos-U85 1024 MAC on MPS4 FI101.
Values are medians over measured RUNs 6–35 (n = 30), taken from `../summary/summary.csv`. Only the seven valid
fingerprints are listed; the three `s1` BASELINE_FAIL boots (68 conv3x3, 70 pw1x1, 71 fc1024) are left out.

## Definitions (`host/analysis/stage1.py`, M_CONFIGURED = 1024)

```
MAC/cycle             = N_MAC / npu_active
peak MAC eff.         = N_MAC / (1024 × npu_active)
MAC active ratio      = mac_active / npu_active
MAC active-cycle eff. = N_MAC / (1024 × mac_active)
peak MAC eff.         = MAC active ratio × MAC active-cycle eff.
```

`N_MAC` comes from the model, not from the board (`evidence/stage1/summary.json` → `n_mac`).

## Table

| workload | boot | dataset | input | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. (min–max) | MAC active ratio | MAC active-cycle eff. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | 65 | s1 | seed 1 | 15,556,352 | 90,930.0 | 171.1 | 16.7% (16.45%–16.90%) | 62.1% | 26.9% |
| ad_medium_int8 | 66 | s1 | seed 1 | 62,346,720 | 146,411.5 | 425.8 | 41.6% (41.32%–42.17%) | 64.0% | 65.0% |
| mobilenet_v2_1.0_224_INT8 | 67 | s1 | MLEK | 300,775,552 | 1,448,582.5 | 207.6 | 20.3% (20.25%–20.32%) | 39.7% | 51.1% |
| dw3x3 | 69 | s1 | seed 1 | 3,612,672 | 144,225.0 | 25.0 | 2.4% (2.44%–2.46%) | 19.6% | 12.5% |
| conv3x3@a2 | 72 | a2 | MLEK | 115,605,504 | 213,654.0 | 541.1 | 52.8% (52.44%–53.16%) | 79.3% | 66.7% |
| pw1x1@a2 | 73 | a2 | MLEK | 25,690,112 | 158,742.0 | 161.8 | 15.8% (15.74%–15.90%) | 19.8% | 80.0% |
| fc1024@a2 | 74 | a2 | MLEK | 1,048,576 | 127,043.5 | 8.3 | 0.8% (0.80%–0.81%) | 3.2% | 25.0% |

Same values with full precision: `npu_utilization.csv`. Input "seed 1" = runner-generated input judged against
tflite_runtime; "MLEK" = MLEK's input judged against the MLEK FI101 golden (amendment 1 for mobilenet, amendment 2
for the `a2` operators).

Not measured here: MLEK use cases other than kws, ad and mobilenet (rnnoise, vww, yolo-fastest, wav2letter). Their
stock-MLEK board cycle counts exist on branch `refactor/unified-mlek-campaigns` (`docs/paper/evidence/board-stage-b*/`),
without a MAC_ACTIVE counter.
