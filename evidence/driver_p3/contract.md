# Driver Runner Phase 3 — first validation on kws and ad (frozen 2026-11-09, before boot 298)

Directive: `docs/plan/driver_runner_directive.md` Phase 3 ("작은 모델 두 개로 기본 계측을 검증"). Design:
`docs/plan/driver_runner_plan.md`. **TA: MLEK's own `ta_config_u85_sys_dram_mid`** (the MLEK platform programs both TAs at
boot; = the runner's TA profile 1 values, read back here). FI101 Ethos-U85 1024 MAC. Approval: board image replacement
needs the owner's go (directive 9.5) — this contract is frozen first, the boots run only after that go.

## Image (driver runner, MLEK b2c0bb2 platform + out-of-tree use case `pmu_runner`, branch `feat/driver-runner`)

Built by `host/container/build_driver_runner.sh` (commit `eb4de1d`): gate PASS (driver hooks are the runner's, MLEK's
profiler hooks are MLEK's, `ethosu_dev_run_command_stream` calls the remap hook), no warning from runner sources.
boot.bin `8d0123f322f5…`, bram.bin `964ced9ce7ea…`, images.txt `af688281435a…` (= stock MLEK's). The build emits an empty
ddr.bin (the runner places nothing in DDR); the card gets a **16-byte zero ddr.bin** instead, so the MCC loads a non-empty
file at 0x70000000 that the runner overwrites when it places a model (`docs/plan/driver_runner_plan.md` J11).
Deployed with `deploy_mlek.sh` (MLEK image set), undone with `restore_mlek.sh`.

## Workloads (DRWL, `pack_vela_workload.py --profile config/fi101_s013.json --format drwl`)

| model | Vela output sha256 | = MLEK board reference | IFM | golden |
| --- | --- | --- | --- | --- |
| kws_micronet_m | `f9575c36651e…` | yes (`mlek_board_reference.json`) | seed-1 `6c5409f4d3ea…` | tflite_runtime `416635484ed7…` |
| ad_medium_int8 | `b83f28f2e5ad…` | yes | seed-1 `d61c3b2e3edb…` | tflite_runtime `312b3779d6f1…` |

Same seed-1 input as the legacy runner's Stage 0 blobs (`f11271cb…`, `55fa924c…`; checked on the host before the boots:
DRWL IFM sha256 = the legacy blob's IFM bytes).

## Boots (`plan.txt`): 298 kws, 299 ad — one boot each, sets `ids.txt` (BASE = 35 17, A, B), 10 RUNs, 2 warm-up, WFE

## Rules (`host/analysis/driver_p3.py`, tests `host/tests/test_driver_p3.py`, 15 mutations RED)

| check | PASS | otherwise |
| --- | --- | --- |
| D1 platform | `PLATFORM_AS_MLEK`: both TAs = sys_dram_mid (TA_EXT MAXR recorded apart: `E2_SAME` 0 / `E2_DIFFERS` 64 / `E2_OTHER`), AXI_SRAM 0x20F0B, AXI_EXT 0x21F3F, MEM_ATTR 0/0/4/4, POWER_CTRL 0 | `PLATFORM_DIFFERS` (listed) |
| D2 execution | `EXEC_OK`: every measured RUN valid (record v2: completed, invoke ok, one arm, one IRQ, no overflow, job result OK, codes echo, rc 0) and OFM mismatch 0 | `EXEC_INVALID` |
| D3 window | `WINDOW_OK`: every measured RUN one arm, one IRQ, 0 < NPU_ACTIVE ≤ NPU_EXECUTION | `WINDOW_INVALID` |
| D4 repeat | `STABLE`: mac_active and the four beat counters identical across measured RUNs | `UNSTABLE` |
| D5 legacy | `REPRODUCES_LEGACY`: same input — mac_active and the four beats equal the legacy runner's (Stage 0 ctl, image `2bb04bfa`, passes A/B) exactly; NPU_ACTIVE median within the 2B-0b tolerance of the legacy RUN width | `DIFFERS_FROM_LEGACY` (listed, size) |
| D6 PMU load | `PMU_INERT`: sets A and B vs BASE — NPU_ACTIVE, NPU_EXECUTION, HOST_END_TO_END medians within max(1 %, BASE RUN width); OFM the same | `PMU_EFFECTIVE` (listed) |

Missing data → `UNPROVEN` for that check; no check is inferred from another. Recorded, not judged: CFG_SRAM/EXT_CAP as
the MLEK platform leaves them (E1 reset state, compared with experiment A), the driver's power reference count at idle
and at each arm (`CODE_VERIFIED` expectation: 1 at idle, 2 during a job = no per-job soft reset), NPU_EXECUTION −
NPU_ACTIVE, HOST_END_TO_END, the base addresses TFLM passed and the arena address.

## What the outcomes mean and do not mean

- D1–D4 PASS: the driver runner runs the models correctly on the MLEK platform and measures a defined NPU window. D5
  PASS: on these models and this input it also reproduces the legacy runner's deterministic counters. Neither is MLEK
  equivalence (that is equivalence C, same input as MLEK) — D5 compares two runners, not a runner with MLEK.
- Failure: the boot's raw data, capabilities and text log are kept; nothing is rerun with changed rules.
- Two models only (directive: first validation); the seven-model run follows with the same rules after this result.
