# Stage 1 anomaly candidates (from VALID workloads only; TA profile 1)

Routing by relative comparison across kws, ad_medium, mobilenet and dw3x3. No thresholds and no causes are
decided. Event ids come from the U85 driver table; "(TRM)" marks an id the TRM also describes, and "(driver only)"
one the TRM table does not, whose semantics must be checked before use.

| # | candidate | pattern | supporting Stage 1 metrics | competing explanations | proposed next event set (8 slots) | priority |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | dw3x3 | A + B + C + E | Lowest peak efficiency (2.4 %), active ratio (19.6 %) and active-cycle efficiency (12.5 %) of all valid workloads. EXT beats/MAC 12–21× the models'. 144k cycles for 3.6M MAC, vs kws 91k cycles for 15.6M. | Depthwise has no reduction over input channels, so little of the MAC array has work. IFM/OFM traffic to the DDR arena via EXT. Weight/IFM supply. AO-side work per output. | Stage 2: npu_active 35, mac_active 48, mac_dpu_active 51 (TRM), ao_active 64 (TRM), wd_active 80 (TRM), wd_stalled 81 (TRM), mac_stalled_by_ib 55 (driver only), cc_stalled_on_blockdep 33 (driver only). Stage 3 if supply is implicated: ext_rd_tran_req_stalled 387, ext_rd_stall_limit 398, axi_latency_any 160, axi_latency_128 163 (TRM). | high |
| 2 | mobilenet_v2 | A | Lowest MAC active ratio among the models (39.7 %, vs 62–64 %) at a middle active-cycle efficiency (51.1 %). | 17 depthwise layers (see #1). 10 ADD and other non-MAC ops on the NPU. Per-layer start/drain. Memory supply. | Stage 2: npu_active 35, mac_active 48, ao_active 64, wd_active 80, wd_stalled 81, mac_dpu_active 51, cc_stalled_on_blockdep 33 (driver only), mac_stalled_by_w_or_acc 52 (driver only). | medium |
| 3 | kws_micronet_m | B | Active ratio as high as ad's (62.1 % vs 64.0 %), but active-cycle efficiency much lower (26.9 % vs 65.0 %). | Small channel/spatial sizes mapping poorly onto 1024 MACs (5 depthwise of 13 MAC ops). Block-size choices. | Stage 2: mac_active 48, mac_dpu_active 51, mac_stalled_by_w 53 / by_acc 54 / by_ib 55 (driver only), ao_active 64, npu_active 35. Stage 4 (operator mapping) after that. | medium |
| 4 | conv3x3, pw1x1, fc1024 | — (not routable) | No valid fingerprint: R3 failed by 1 LSB (29 / 223 / 1 bytes). | NPU vs tflite_runtime requantization rounding, as seen for mobilenet (where MLEK FI101 showed the same difference). | Needs an owner decision on their golden first (see below). Pattern D (operator vs operator) cannot be judged with one valid operator. | blocking for Stage 1 success criterion 2 |

Stage-1 success criteria:
- 1 — all baseline models pass: **met**.
- 2 — all representative operators valid: **not met** (1 of 4).
- 3 and 4 — comparison across models and operators: **partial** (models + dw3x3 only).
- 5 — anomaly candidates named: **met** for the valid set.
- 6 — next event sets chosen with a reason: **met** for the valid set.
