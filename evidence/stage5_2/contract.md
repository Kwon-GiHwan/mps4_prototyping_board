# Stage 5-2 — Size vs Performance at the same SRAM budget (frozen 2026-11-11, before boot 361)

Owner decision 2026-11-11 (after the 5-1 report): minimal 5-2, at most 6 configs / 60 RUNs, no mobilenet.

**Fixed conditions.**
- **TA: MLEK's own sys_dram_mid set-up = TA profile 1.**
- FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (memory configuration Dedicated_Sram; the only verified one), WAIT_WFE.
- Vela 5.0.0, `ethos-u85-1024`, Dedicated_Sram, `Ethos_U85_SYS_DRAM_Mid_1024`.
- **Requested budget 384 KiB for both strategies.** The base DRWLs use the ini's 393,216; an explicit `--arena-cache-size=393216` gives the same Vela output for all three workloads (checked).
- Inputs and goldens as in 5-1 / 4C-2.
- Pass A + B, 1 warm-up + 4 measured RUNs.

## Execution-payload check before the board (`evidence/stage5/size_payload_diff.json`, 5-0 rules)

| workload | command stream | constants | fast scratch | arena | IO | compute config per kernel | what differs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | differs (2,572 vs 2,568 B) | differ (145,728 vs 145,552 B) | 91,600 = | 496 = | = | = | 2 kernels: weight-stream lengths and weight DMA (1,712 → 1,664; 9,600 → 9,472 B) |
| ad_medium_int8 | differs | differ | 249,856 → **308,064** | 1,024 = | = | = | 11 kernels: kernel 3's weights in the fast-scratch region (region 2) as one stream instead of four; weight DMA 4,096 → 58,208 B |
| conv Cin 64 | differs (520 vs 448 B) | differ | 8,576 → 9,536 | 92,160 = | = | = | both kernels: one weight stream instead of four, DMA 1,664 → 2,400 and 6,912 → 7,136 B |

- KWS's execution payload differs, so it is **included**: not only Vela's MAC count differs.
- Effective MACs stay the original operator definition (kws 14,208,852 from the 384 KiB / Performance compile, = the model's; ad 61,466,400; Cin 64 3,538,944).
- Vela's per-configuration MAC count (kws Size 15,580,852) is kept in a separate column and is not used for any efficiency.

## Configs — boots 361–366, conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

| boot | config | Vela output | strategy / applied budget | SRAM used (Vela) |
| --- | --- | --- | --- | --- |
| 361 | kws_micronet_m_base | `f9575c36` (m7 DRWL) | Performance / 384 KiB | 89.5 KiB |
| 362 | kws_micronet_m_size | `febca586` | Size / 384 KiB | 89.5 KiB |
| 363 | ad_medium_int8_base | `b83f28f2` (m7 DRWL) | Performance / 384 KiB | 244.0 KiB |
| 364 | ad_medium_int8_size | `c6508a44` | Size / 384 KiB | 300.8 KiB |
| 365 | s4c2_conv_cin64_base | `f3229048` (4C-2 DRWL) | Performance / 384 KiB | 8.4 KiB |
| 366 | s4c2_conv_cin64_size | `bfad9666` | Size / 384 KiB | 9.3 KiB |

## Rules — `host/analysis/stage5.py … 5-2` (the 5-1 rules; tests `test_stage5`, 7/7 mutations RED)

- Output: MLEK models byte-exact; Cin 64 PASS_EXACT / PASS_TOLERANCE (≤ 1 LSB) vs the CPU reference.
- Config verdict: VALID / INVALID / NOT_EXECUTABLE.
- **Base reproduction** against the latest measurement of the same DRWL on the same image:
  - kws and ad: 5-1 boots 351 and 354.
  - Cin 64: 4C-2b boot 350.
  - Every commonly constant counter must be equal, else `BASELINE_MISMATCH`.
- **Pairs base → Size:** NPU_ACTIVE uses Stage 4's pair rule on pass A, with pass B as a check; opposite signs → `UNRESOLVED`. MAC / DPU are compared exactly where constant. Transfers use the same tolerance rule.
- **Not assumed:** that Size uses less SRAM (here it uses the same or more) or that Performance is faster. Results are stated by actual SRAM requirement, execution configuration and PMU values, not by the option name.

## Stops

- No image or firmware change. A failed base reproduction, or an output or memory check failing, stops that workload; it is reported, with no workaround.
- No mobilenet and no other configs.
- After 5-2 the board is restored to m6, postflight PING of the restored image, card withdrawn.
- The Stage 1–5 synthesis follows without board runs.

## Amendment A (2026-11-11, after boots 361–366; recorded, the text above is not edited)

- **What was wrong:** line "Effective MACs stay the original operator definition (kws 14,208,852 from the 384 KiB / Performance compile, = the model's; ad 61,466,400 …)". Both numbers are Vela's `nn_macs` of the Performance compile, not the model's.
- **The project definition** is the tflite N_MAC used by Stage 1/3 (`host/container/workload_meta.py`; `evidence/stage1/workload_manifest/manifest.json`):
  - kws 15,556,352
  - ad 62,346,720
  - Cin 64 3,538,944 (operator formula = Vela's count)
- **Effective MACs for every Stage 5 derived value** are these. Vela's per-configuration counts are kept apart (`vela_macs`).
- **Rules and verdicts are unchanged:**
  - The pair rule tests the NPU_ACTIVE change against the tolerance first.
  - It uses only the MAC ratio of base and variant, which is 1 for every Stage 5 pair.
  - Checked by `evidence/stage5_2/verdicts_unchanged.py`.
