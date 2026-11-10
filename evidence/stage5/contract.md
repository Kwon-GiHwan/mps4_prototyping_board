# Stage 5-1 — SRAM workspace budget in Dedicated_Sram (frozen 2026-11-11, before boot 351)

Owner approval 2026-11-11 (5-0 then 5-1, at most 10 configs / 100 RUNs); plan `docs/plan/stage5_plan.md`. **TA: MLEK's own
sys_dram_mid set-up = TA profile 1.** FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (boot `1b5c0adb`, bram
`4f592f24`), WAIT_WFE, caches and initialisation as before, Vela 5.0.0 `--accelerator-config ethos-u85-1024 --optimise
Performance --config default_vela.ini --memory-mode Dedicated_Sram --system-config Ethos_U85_SYS_DRAM_Mid_1024`, pass A
(Stage 1 set A) + pass B (Stage 3 set B), 1 warm-up + 4 measured RUNs per config and pass.

## What is varied — and what is not

5-1 changes **the compiler's SRAM workspace budget** (`--arena-cache-size`, the NPU fast-scratch area Vela may use) in
Dedicated_Sram.
- **memory_mode:** a Vela compile setting that must match the runtime/firmware memory configuration. On image
  `83398c7` only Dedicated_Sram is a verified execution configuration:
  - MLEK build `ETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram`
  - region 0/1 on AXI1 (EXT), regions 2–7 on AXI0 (SRAM), confirmed in the compiled `ethosu_config_select`
  - fast scratch 0x31000000, 384 KiB (capabilities)
  - arena in DDR after the model
- **Not changed:** the physical SRAM capacity, the memory mode, the image, TA, data, quantization, wait and cache policy.
- **Excluded:** Shared_Sram, Sram_Only and region→port remapping.
- **Runtime support of a budget of 0 (checked in source, not assumed):**
  - The core driver refuses a job only when the requested fast-scratch size exceeds the image's (`ethosu_driver.c:672–674`); the TFLM Ethos-U op passes the sizes through.
  - Whether a 0-size fast scratch runs is decided by the board: no completed RUN → `NOT_EXECUTABLE`.

## 5-0 — compile-only classification (`results/fi101_stage5/stage5_0_classification.csv`, `evidence/stage5/stage5_0.json`)

**Scope:** `host/container/stage5_compile.py` on the 7 MLEK models and 4 isolated operators (conv_base, conv Cin 64,
dw_base, fc_base), each with these variants:
- base (the ini's 384 KiB)
- 64 KiB
- 0
- Size
- Size + 0

**Recorded:** requested vs applied `arena_cache_size` (Vela summary), SRAM / DRAM used, fast-scratch and arena bytes from the Vela output, NPU / CPU operators, kernel count and kinds, and per kernel the decoded registers (compute and memory signatures), weight stream and DMA bytes, Vela cycles and MACs.

**"Identical" is judged on the execution payload, not the file hash:** command stream, constant data, fast-scratch size, arena size and IO offsets.

**Classes:**
- `EXEC_IDENTICAL`
- `MEMORY_ONLY`: same compute signature per kernel — kind, shapes, depths, OFM block, microblock, kernel size/stride/weight order.
- `SCHEDULE_CHANGED`: otherwise; a whole-configuration effect.

**Findings** (all 55 compiled; no CPU fallback; every fast-scratch requirement ≤ 384 KiB and every arena ≤ 2 MiB):

| workload | 64 KiB | 0 |
| --- | --- | --- |
| kws_micronet_m | SCHEDULE_CHANGED (SRAM 89.5 → 58.8 KiB, 14 → 19 kernels) | SCHEDULE_CHANGED (0 KiB, 13 kernels) |
| ad_medium_int8 | SCHEDULE_CHANGED (244 → 59.8 KiB, 14 → 66 kernels) | SCHEDULE_CHANGED (0 KiB, 13 kernels) |
| s4_dw_base | EXEC_IDENTICAL | SCHEDULE_CHANGED (2 → 1 kernel) |
| s4_conv_base | EXEC_IDENTICAL | SCHEDULE_CHANGED (2 → 1 kernel) |
| rnnoise | EXEC_IDENTICAL | MEMORY_ONLY |
| vww4, mobilenet | SCHEDULE_CHANGED | SCHEDULE_CHANGED |
| yolo | SCHEDULE_CHANGED | MEMORY_ONLY |
| wav2letter | MEMORY_ONLY | MEMORY_ONLY |
| conv Cin 64 | EXEC_IDENTICAL | SCHEDULE_CHANGED |
| fc_base | EXEC_IDENTICAL | EXEC_IDENTICAL |

- **Not run because the payload equals the base** (`EXEC_IDENTICAL`): dw/conv 64 KiB, rnnoise 64 KiB, conv Cin 64 64 KiB, fc 64 KiB / 0.
- **Changed but not run (scope; effect UNMEASURED, not generalised from kws/ad):** rnnoise 0; vww4, yolo, mobilenet, wav2letter at 64 KiB and 0; conv Cin 64 at 0.
- Size variants are for the 5-2 proposal only.

## 5-1 configs (10, the cap) — boots 351–360, conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

| boot | config | DRWL (Vela output) | 5-0 class | fast scratch / arena (B) |
| --- | --- | --- | --- | --- |
| 351 | kws_micronet_m_base | m7 DRWL (`f9575c36`) | base | 91,600 / 496 |
| 352 | kws_micronet_m_cache64k | `ef4e9440` | SCHEDULE_CHANGED | 60,176 / 18,496 |
| 353 | kws_micronet_m_cache0 | `80e68ec1` | SCHEDULE_CHANGED | 0 / 88,560 |
| 354 | ad_medium_int8_base | m7 DRWL (`b83f28f2`) | base | 249,856 / 1,024 |
| 355 | ad_medium_int8_cache64k | `22069237` | SCHEDULE_CHANGED | 61,280 / 147,456 |
| 356 | ad_medium_int8_cache0 | `638d2dba` | SCHEDULE_CHANGED | 0 / 245,760 |
| 357 | s4_dw_base_base | Stage 4 DRWL (`7b546a4f`) | base | 3,232 / 903,168 |
| 358 | s4_dw_base_cache0 | `0616321b` | SCHEDULE_CHANGED | 0 / 903,168 |
| 359 | s4_conv_base_base | Stage 4 DRWL (`fadf33d7`) | base | 4,032 / 64,512 |
| 360 | s4_conv_base_cache0 | `6761eb94` | SCHEDULE_CHANGED | 0 / 64,512 |

Variants are packed by `pack_vela_workload.py --profile config/fi101_s013.json --format drwl --vela-option=--arena-cache-size=N`.
Inputs and goldens are the base's:
- kws, ad: MLEK input and MLEK FI101 golden taken from the m7 DRWL (sha256 `236ea3d6` / `e8436317`, `89ce99eb` / `3d431e23`)
- conv, dw: the seed-1 input and CPU reference

Every DRWL's Vela output equals the 5-0 artifact (sha256 checked by the analysis).

## Rules (`host/analysis/stage5.py`; tests `host/tests/test_stage5.py`; mutation below)

- **Output** (`output.bin` vs the DRWL golden):
  - MLEK models byte-exact (amendment 2): PASS_EXACT / FAIL.
  - Isolated operators PASS_EXACT / PASS_TOLERANCE (≤ 1 LSB) / FAIL.
  - INVALID on a length difference, differing output CRCs between RUNs, or a firmware-count disagreement.
  - Also recorded: whether the output equals the base config's NPU output.
- **Config verdict:**
  - VALID: output PASS_* and 4 measured RUNs valid in both passes (`record_v2.validity`).
  - INVALID: otherwise.
  - NOT_EXECUTABLE: no completed measured RUN. No workaround, no re-run.
- **Base reproduction:** the same DRWL measured earlier (kws, ad: m7 boots, warm-up 2; dw, conv: Stage 4 boots 333 / 330, warm-up 1).
  - Every counter constant in both, matched by event-set content, must be equal.
  - The earlier RUNs must have matched the same golden.
  - The base's output must be PASS_EXACT now.
  - Otherwise `BASELINE_MISMATCH`, and that workload is not interpreted.
- **Pairs base → variant:**
  - NPU_ACTIVE uses Stage 4's pair rule on pass A (tol = max(1 % of base, either RUN range)), with pass B as a check; opposite signs → `UNRESOLVED`.
  - MAC_ACTIVE / MAC_DPU_ACTIVE are compared exactly where constant.
  - SRAM / EXT beats and transactions use the same tolerance rule.
  - Reported beside: SRAM workspace used, fast-scratch / arena bytes, kernel count, 5-0 class.
- **Interpretation limits:**
  - Every 5-1 variant is `SCHEDULE_CHANGED`, so results are whole-configuration effects of the budget change, not pure placement effects.
  - A smaller SRAM budget is not assumed to cost performance.
  - Transfer and time changes are not assigned to bandwidth or memory waiting.
  - Nothing is generalised to the five models not measured.

## Stops

- A failed base reproduction, output check or memory-capacity check stops that workload's interpretation.
- No image or firmware change and no extra configs.
- 5-2 is decided after the 5-1 report.
- At the end the board is restored to m6, postflight PING of the restored image, card withdrawn.

## Mutation test

`evidence/stage5/mutate_stage5.py`: 7 mutations (model exact-only, base counter check, opposite directions, EXCLUDED,
NOT_EXECUTABLE detection, same-output flag, output CRC check). First pass 5/7. The survivors got fixtures (a config refused after the warm-up RUN; one RUN with a different output CRC). The first also fixed a real defect: a refused first RUN writes no `runs.csv`. Result: **7/7 RED**, restored by digest.
