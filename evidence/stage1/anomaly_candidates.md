# Stage 1 anomaly candidates (from VALID workloads only; TA profile 1)

Routing by relative comparison across the three models and the four operators: dw3x3 from boot 69, and conv3x3,
pw1x1 and fc1024 from boots 72–74 under amendment 2. No thresholds and no causes are decided. Event ids come from the U85 driver table; "(TRM)" marks an id the TRM also describes, and "(driver only)"
one the TRM table does not, whose semantics must be checked before use.

| # | candidate | pattern | supporting Stage 1 metrics | competing explanations | proposed next event set (8 slots) | priority |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | dw3x3 | A + B + C + E | Lowest peak efficiency (2.4 %), active ratio (19.6 %) and active-cycle efficiency (12.5 %) of all valid workloads. EXT beats/MAC 12–21× the models'. 144k cycles for 3.6M MAC, vs kws 91k cycles for 15.6M. | Depthwise has no reduction over input channels, so little of the MAC array has work. IFM/OFM traffic to the DDR arena via EXT. Weight/IFM supply. AO-side work per output. | Stage 2: npu_active 35, mac_active 48, mac_dpu_active 51 (TRM), ao_active 64 (TRM), wd_active 80 (TRM), wd_stalled 81 (TRM), mac_stalled_by_ib 55 (driver only), cc_stalled_on_blockdep 33 (driver only). Stage 3 if supply is implicated: ext_rd_tran_req_stalled 387, ext_rd_stall_limit 398, axi_latency_any 160, axi_latency_128 163 (TRM). | high |
| 2 | mobilenet_v2 | A | Lowest MAC active ratio among the models (39.7 %, vs 62–64 %) at a middle active-cycle efficiency (51.1 %). | 17 depthwise layers (see #1). 10 ADD and other non-MAC ops on the NPU. Per-layer start/drain. Memory supply. | Stage 2: npu_active 35, mac_active 48, ao_active 64, wd_active 80, wd_stalled 81, mac_dpu_active 51, cc_stalled_on_blockdep 33 (driver only), mac_stalled_by_w_or_acc 52 (driver only). | medium |
| 3 | kws_micronet_m | B | Active ratio as high as ad's (62.1 % vs 64.0 %), but active-cycle efficiency much lower (26.9 % vs 65.0 %). | Small channel/spatial sizes mapping poorly onto 1024 MACs (5 depthwise of 13 MAC ops). Block-size choices. | Stage 2: mac_active 48, mac_dpu_active 51, mac_stalled_by_w 53 / by_acc 54 / by_ib 55 (driver only), ao_active 64, npu_active 35. Stage 4 (operator mapping) after that. | medium |
| 4 | pw1x1 | A + C + D | Active ratio 19.8 % (as low as dw3x3) with the highest active-cycle efficiency of all (80.0 %), so peak 15.8 %. vs conv3x3: 0.22× the MACs in 0.74× the cycles; SRAM/EXT beats per MAC 3.7× / 4.5× conv3x3's. 1×1 CONV_2D carries 77–94 % of the MACs of all three models (`workload_manifest/meta`). | A 1×1 kernel reuses each IFM element 9× less than 3×3, so per-MAC IFM/OFM traffic is higher. The OFM (2× the IFM here) goes to the DDR arena. A fixed per-op cost (start, weight decode, drain) is larger relative to fewer MACs. Memory supply. | Stage 2: npu_active 35, mac_active 48, mac_dpu_active 51 (TRM), ao_active 64 (TRM), wd_active 80 (TRM), wd_stalled 81 (TRM), mac_stalled_by_ib 55 (driver only), cc_stalled_on_blockdep 33 (driver only). Pattern D: shape sweep over Cin/Cout and H×W. Stage 3 (as #1) if supply is implicated. | high |
| 5 | fc1024 | A + C + D | Lowest active ratio (3.2 %) and peak efficiency (0.8 %) of all. Highest EXT beats/MAC (0.0633, 4.3× dw3x3) and EXT beats/NPU cycle (0.522). Zero SRAM beats. | Batch-1 FC uses each weight once, so the 1M-weight constant stream through EXT is the whole job. A 1×1024 IFM has little work per weight for the MAC array. Vela placed no fast-storage tensor (fast_size 0). EXT supply/latency. | Stage 3 first: npu_active 35, mac_active 48, wd_active 80, wd_stalled 81 (TRM), ext_rd_tran_req_stalled 387, ext_rd_stall_limit 398, axi_latency_any 160, axi_latency_128 163 (TRM). Pattern D: shape sweep over Cin/Cout. | medium-low (no FULLY_CONNECTED in the three models) |
| 6 | conv3x3 | — (reference) | Highest peak efficiency (52.8 %) and active ratio (79.3 %) of all valid workloads; traffic per MAC among the lowest. | — | Kept in the Stage 2 runs as the high-efficiency reference operator for #1, #4 and #5. | reference |

Stage-1 success criteria (after boots 72–74):
- 1 — all baseline models pass: **met**.
- 2 — all representative operators valid: **met**. 4 of 4 have a valid fingerprint: dw3x3 under the TFLite-exact
  R3, and conv3x3, pw1x1 and fc1024 under amendment 2. Their boot-68/70/71 records stay `UNRESOLVED`.
- 3 and 4 — comparison across models and operators: **met**. The operators' inputs differ (seed 1 for dw3x3, MLEK's
  for the other three). A POST_HOC check on the same blobs found MAC_ACTIVE and all beat counters unchanged by the
  input (`fingerprint.md`).
- 5 — anomaly candidates named: **met** (#1–#5; #6 is the reference).
- 6 — next event sets chosen with a reason: **met**.

Earlier version (boots 65–71 only): criterion 2 was not met (1 of 4); row 4 then read "conv3x3, pw1x1, fc1024 —
not routable, needs an owner decision on their golden". That decision was amendment 2.
