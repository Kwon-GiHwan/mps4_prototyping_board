# Driver runner Phase 3 first validation — kws, ad (boots 298–299, 2026-11-09 UTC board clock)

Contract `evidence/driver_p3/contract.md` (frozen `3c540c3`, before boot 298). MLEK platform TA set-up = **TA profile 1**
(sys_dram_mid), WFE wait, sets BASE (35 17), A, B, 10 RUNs, 2 warm-up. Image boot `8d0123f3` / bram `964ced9c` / ddr
`374708ff` / images.txt `af688281` (deployed with `deploy_mlek.sh`, backup in board root `evidence_driver_p3`; the
campaign wrote to `evidence_driver_p3_run` because the sudo-created root is root-owned). Raw `evidence/driver_p3/raw/`,
both boots `campaign exit=0`, 30 valid RUNs each.
`python3 host/analysis/driver_p3.py evidence/driver_p3/raw <main>/evidence/fi101_s013/raw/ctl results/driver_p3`
(legacy = Stage 0 ctl, image `2bb04bfa`, as the contract names).

| model | D1 platform | D2 exec | D3 window | D4 repeat | D5 legacy | D6 PMU load |
| --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (NPU_ACTIVE +0.52 %) | PMU_INERT |
| ad_medium_int8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (NPU_ACTIVE +0.08 %) | PMU_INERT |

- D1: TA registers = sys_dram_mid, TA_EXT MAXR reads 0 (E2_SAME, as experiment A found on the legacy image), CAP
  0x20F0B / 0x21F3F, AXI/MEM_ATTR/POWER_CTRL as MLEK; idle power requests 1 (the MLEK PMU init keeps power requested,
  `docs/plan/driver_runner_plan.md` §2.7).
- OFM mismatch 0 in every RUN against the DRWL golden (seed-1 input; tflite golden for ad, as for the legacy blobs).

POST_HOC_DESCRIPTIVE (P1, the window; set BASE medians):

| model | NPU_ACTIVE | NPU_EXECUTION (arm → IRQ) | HOST_END_TO_END (Invoke) | legacy PMCCNTR window |
| --- | --- | --- | --- | --- |
| kws_micronet_m | 91,140 | 91,666 (+526) | 111,198 | 2,626,583 |
| ad_medium_int8 | 146,172 | 146,698 (+526) | 175,924 | 8,032,828 |

The driver runner's NPU_EXECUTION median exceeds the NPU_ACTIVE median by 526 cycles on both models (per-RUN spread not examined); the legacy window
includes the CPU staging copies (29× and 55× NPU_ACTIVE). Neither claim says the driver runner equals MLEK (that is C).
