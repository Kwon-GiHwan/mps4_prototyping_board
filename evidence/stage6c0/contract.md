# Stage 6C-0 계약 — Unit/AXI/Vela 통합 분석과 Stage 6C 실험 설계 (보드 없음)

지시: Stage 6C-0 공식 지시(2026-11-18). ChatGPT 결정(2026-11-18, `docs/plan/research_direction_and_decision_log.md`): E2E-D를 종료하고 6C-0을 이 계약대로 완료하며, 신규 보드 측정은 하지 않는다.
이 계약, 통합·분류·선정 코드(`host/analysis/stage6c0.py`), 컴파일 검증 스크립트(`host/container/stage6c0_models.py`), 테스트는 **결과 생성 전에** 커밋한다.
기존 실험의 계약·판정·결과 파일은 바꾸지 않는다. 보드 자료는 모두 기존 원시·요약 파일에서 읽는다. 값이 없으면 채우지 않고 빈칸으로 둔다.

## 계약 전 노출

- 결과 폴더 인벤토리(읽기 전용)와 7개 모델 연산 목록의 연산군별 요약을 보았다. 요약의 근거는 `results/fi101_stage4/stage4_operator_inventory.csv`(Vela mac_count 기준)다.
- 연산군별로 모델 안 비중이 가장 큰 연산:
  - 1×1 PartKernel: yolo op9(96×96, Cin 4 → 24)
  - DW 3×3: yolo op3(96×96, C 8)
  - FC: rnnoise op46(114 → 288)
  - 1×32 PartKernel: wav2letter op17
  - 10×4 첫 Conv: kws op0(Cin 1)
- 아래 선정 규칙은 이 노출 뒤에 정했다. 규칙은 데이터에서 대표 연산을 기계적으로 고르며, 특정 모델의 사후 측정 결과로 바꾸지 않는다.

## 1. Phase 0 — 통합표 (`integrate`)

- **행**: 측정 하나(모델, 또는 독립 연산 구성, 또는 E2 구성 × 지연).
- **열**: source, stage, item, level(model/operator/graph), family, runner, image, ta, placement, latency, n_mac, npu_active, mac_active, mac_dpu_active, ao_active, wd_active, wd_stalled, SRAM/EXT read·write beat, EXT read 트랜잭션, Vela compute/SRAM/DRAM/total, Vela npu cycles, status.
- **원천**(경로는 코드의 `SOURCES`):
  - E2A `vela_board_table.csv`(driver runner, 7개 모델과 독립 구성)
  - Stage 1 `stage1.csv`(legacy, 7개 모델)
  - Stage 3 `stage3.csv`(legacy, AXI)
  - Stage 4 `stage4_summary.csv`, 4C-2, 4K(+static), 4AO, 4AO-E, 4WD
  - 6B-B `shapes.csv`, `fidelity.csv`
  - E2D/E2E-B `ext_transactions.csv`, `e2d_table.csv`
  - E2E-D summary
- **조건 그룹** = (runner, image, TA, latency, placement). 다른 그룹의 값은 같은 표에 두되, 직접 비교 쌍으로 묶지 않는다.

## 2. Phase 1 — Unit별 확보·미확보 지표 (`unit_inventory`)

- MAC/DPU, AO, WD, DMA/AXI 각각에 대해 확보된 관측(근거 파일), 미확보 지표, Open Issue(AO-1, WD-1, WD-2)를 표로 정리한다.
- **AXI 이용률**: 포트 대역폭, 클럭, 측정 조건이 검증된 경우에만 계산한다. 이번에는 검증된 포트 물리 한도가 없으므로 계산하지 않는다(`AXI_UTILIZATION_NOT_COMPUTED`). 바이트 ÷ NPU_ACTIVE는 "관측 평균 처리율(B/cycle)"이라고만 부른다.

## 3. Phase 2 — 통제 비교 쌍과 분류 (`compare`, `tags`)

- **쌍**: 같은 조건 그룹 안에서 변수 하나를 바꾼 기존 실험(코드의 `PAIRS`).
  - Stage 4: Cin−1, Cout−1, C−1, in−1, out−1
  - 4C-2 Cin sweep
  - 4K 1×1 대 3×3
  - 4AO OFM sweep
  - Stage 4 placement A/B
  - E2D 배치·지연, E2E-B, E2E-D
- **태그**(동시에 붙을 수 있고, 시간 기여로 합산하지 않음). tol = 1 %이며, NPU는 max(1 %, 두 range 합)이다.
  - `COMPUTE_COST_CHANGE`: |ΔMAC_ACTIVE| 또는 |ΔDPU| > 1 %.
  - `DATA_TRANSFER_CHANGE`: SRAM+EXT read 또는 write beat 합, 또는 EXT read 트랜잭션이 > 1 % 변함.
  - `MEMORY_SERVICE_CONDITION_CHANGE`: 쌍의 변수가 배치·지연·SRAM 예산.
  - `COMPILER_MAPPING_CHANGE`: traversal, ofm_block, ofm_ublock, kernel 수가 다름(값이 있을 때).
  - `PIPELINE_DEPENDENCY_CANDIDATE`: ΔNPU > tol_NPU인데 MAC_ACTIVE 변화 ≤ 1 %.
  - `CAUSE_UNRESOLVED`: ΔNPU > tol_NPU인데 위 태그가 하나도 없음.
- 카운터 상관만으로 병목을 판정하지 않는다.

## 4. Phase 3 — Vela Fidelity 통합 (`vela_table`)

- board/Vela와 (board − Vela)/Vela를 계산한다. 각 행에 기준을 표기한다(Vela total 또는 npu cycles).
- 사례:
  - 모델(driver runner, legacy)
  - 독립 1×1 DepthFirst(E1-R)
  - A2 래퍼(6B-B, E2D)
  - Conv 단독 DRAM(E2D W0)
  - SRAM 예산(Stage 5)
  - 배치(E2D, E2E-B)
- **방향**: over(board < Vela) / under / within ±10 %.
- 모델식: `op = max(compute, SRAM, DRAM)`, `graph = Σ op`. H1-UC MAC_ACTIVE와 Vela compute는 다른 지표로 둔다. 사후 보정은 하지 않는다.

## 5. Phase 4 — Stage 6C 연산군 선정 (`select`, 동결)

후보 연산군(고정):

| 코드 | 연산군 | 연산 분류 규칙(`operator_mapping.csv`) |
|---|---|---|
| F1 | 1×1 PartKernel Conv | Conv2D, kernel 1x1, traversal PartKernel |
| F2 | Depthwise Conv | DepthwiseConv2D |
| F3 | Fully Connected | FullyConnected |
| F4 | 1D 대형 커널 PartKernel | Conv2D, kernel 1xK, K ≥ 7 |
| F5 | 특수 채널 첫 Conv | Conv2D, Cin < 16, kernel ≠ 1x1 |

제외(이미 규명): 1×1 DepthFirst(H1-UC PROSPECTIVE_SUPPORT, 반복 측정 금지), 3×3 PartKernel Cin 16–64(4K).

기준(순서 고정, 모두 참이어야 선정):
1. **C1 근거 부족**: driver runner에서 측정한 형상(구성) 수 ≤ 2. 고정값: F1 2(4K Cin 16/32), F2 1(144×56²), F3 1(96→288), F4 0, F5 0.
2. **C2 중요도**: 7개 모델 중 어느 하나에서 그 연산군의 TFLite N_MAC 비중 ≥ 0.10.
3. **C3 새 현상 구분**: 대표 형상의 (traversal, kernel, Cin mod 16 = 0 여부)가 이미 측정한 형상과 다르다.
4. **C4 통제 가능**: 대표 형상의 단독 컴파일이 모델 안 연산과 같은 traversal, ofm_block, ofm_ublock을 낸다(`MAPPING_SAME`). 컴파일 검증 결과로 판정한다.
5. **C5 분석 가능**: 단독 컴파일이 NPU 연산 하나이고, Vela per-op compute/SRAM/DRAM/total을 얻으며, DRWL로 포장되고 runner 한도(fast ≤ 0x60000, arena ≤ 2 MiB, model+arena ≤ 32 MiB) 안이다.

대표 형상:
- 그 연산군의 TFLite N_MAC 비중이 가장 큰 모델에서, N_MAC이 가장 큰 연산을 고른다.
- 연산은 원본 MLEK tflite의 텐서(가중치, bias, 양자화, activation, stride, padding)로 다시 만든다.

통제 형상(변수 하나, 고정):

| 연산군 | 변수 |
|---|---|
| F1 | Cin이 16의 배수가 아니면 Cin → ⌈Cin/16⌉·16, 아니면 Cout ×2 |
| F2 | C가 16의 배수가 아니면 C → ⌈C/16⌉·16, 아니면 kernel 3×3 → 5×5 |
| F3 | Cin이 16의 배수가 아니면 Cin → ⌈Cin/16⌉·16, 아니면 Cout ×2 |
| F4, F5 | 통제 없음(예산) |

- 늘어난 채널의 가중치는 고정 시드의 int8 난수로 채운다. 나머지는 원본 그대로다.
- 통제 형상의 traversal이 대표와 다르면 `COMPILER_MAPPING_CHANGE`로 표시한다. 하드웨어 변수로 해석하지 않는다.

**예산 계획**: REF 1 + 선정 연산군의 대표·통제 형상 수. 상한은 9 boot이며, 넘치면 F5, F4 순으로 뺀다.

## 6. Phase 5–6 — 계측 계약과 가설 (설계만)

- PMU:
  - Pass A·B(기존)를 그대로 쓴다.
  - Pass C 후보는 FI101에서 VERIFIED인 공개 이벤트만 쓴다(E2E-C 분류: 387, 640, 642, 656, 658). SRAM 쪽(131, 142, 512/514/528/530)은 Stage 3 감사 상태로 분류한다.
  - 398은 INCONSISTENT이므로 쓰지 않는다. Reserved 이벤트(53, 55)는 탐색용이다.
- 가설 H-COMPUTE / H-PIPELINE / H-VELA를 연산군마다 정의한다(사전 예측, 검증 조건, 반례).
  - 수치 예측은 기존 근거가 있는 것만 쓴다. 예: Cin·C를 16으로 올림하는 가설(4C-1, 4C-2b 근거) → 통제 형상에서 MAC_ACTIVE 불변.
  - 나머지는 방향성 예측과 판정 불가 조건만 쓴다.
- 보드 계약 초안은 실행 승인이 아니다.

## 7. 산출물

`results/fi101_stage6c0/`:
- `integrated.csv`, `unit_inventory.md`, `comparisons.csv`, `vela_fidelity.csv`
- `selection.json`, `compile_check.json`
- `README.md`(보고 1–15 순서), `stage6c_board_contract_draft.md`, `stage6_reassessment_plan.md`

## 8. 검증

- 테스트 `host/tests/test_stage6c0.py`, mutation 전부 KILLED, `test.sh` ALL PASS.
- 분석 2회 바이트 동일, 컴파일 검증 2회 동일, 기존 파일 불변.
- 로컬 커밋만 한다.
