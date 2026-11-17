# Stage 6D 계약 — 7개 MLEK 모델 수준 Hardware–Compiler 재평가 (보드 없음)

지시: ChatGPT "Stage 6D 공식 지시"(2026-11-18, 사본 `docs/plan/stage6d_directive_chatgpt.txt`). Stage 6C 결과 `c4e3965`(PARTIAL_VALID).
이 계약과 판정 코드 `host/analysis/stage6d.py`, 테스트는 결과 계산 전에 커밋한다. 기존 결과 파일은 바꾸지 않는다. 보드, 신규 컴파일, 펌웨어·TA 변경은 없다.
Stage 6-M 판정(`COVERAGE_EXPANDED_NOT_EXPLAINED`)은 그대로 두고, 새 값은 별도 버전(6D)으로 낸다.

## 계약 전 노출

연산 목록(`fi101_stage6m/operator_mapping.csv`, 372행)과 6-M의 H1-UC 연산별 예측(`h1uc_operators.csv`), Stage 4·6C MAC_ACTIVE를 보고 아래 규칙의 범위를 정했다. 규칙이 맞는지 확인한 사례는 다음뿐이다.
- DW: Stage 4 C144 31,752, 6C C8·C16 10,368.
- FC: Stage 4 세 형상 108.
- 1×1 PK: Stage 4 Cin 16/15·Cout 96 2,304, 6C F1 18,432 — 일반 규칙이 맞지 않음.

- 6-M 산출물로 모델별 DF1x1 비중(`share_1x1df`)과 6-M 근거 coverage는 이미 알고 있다. 공백 표의 고정값(통제 가능·구분 가능·비용)은 이 노출 상태에서 정했다.
- 6D 수준별 비중, P, 모델 판정, 권고는 아직 계산하지 않았다.

**입력(모두 기존 동결 산출물)**:
- 연산: `fi101_stage6m/operator_mapping.csv`, `h1uc_operators.csv`(h1uc).
- 모델 측정: `fi101_stage6/whole_model_comparison.csv`(driver runner, TA profile 1; mac·ao·wd·npu_active·vela_npu_cycles).
- DPU·WD_STALLED 비율: `fi101_stage1/stage1.csv`(legacy runner, TA profile 1, mlek_r10).
- AXI: `fi101_stage3/stage3.csv`(legacy runner).
- 6C: `fi101_stage6c/stage6c_summary.json`. 6-M: `coverage_comparison.csv`, `stage6m_summary.json`.

## 1. 연산 분류 (`family`)

`operator_mapping.csv`의 NPU MAC 연산(`exec_on == NPU`, n_mac_tflite > 0):

| family | 규칙 |
|---|---|
| DF1x1 | Conv2D 1x1 DepthFirst |
| PK1x1 | Conv2D 1x1 PartKernel |
| PK3x3 | Conv2D 3x3 PartKernel |
| PK1D | Conv2D 1xK(K ≥ 7) PartKernel |
| FIRST_CONV | Conv2D, Cin < 16, kernel ≠ 1x1·3x3 |
| DW | DepthwiseConv2D |
| FC | FullyConnected |
| OTHER_CONV | 그 밖의 Conv2D |

- MAC 0인 NPU 연산은 `AO_ELEMENTWISE`로 분류하고, 연산 개수 Coverage에만 넣는다.
- `exec_on`이 NPU가 아니면 `CPU_OR_SPLIT`이며 NPU Coverage에서 뺀다.
- N_MAC은 TFLite 값만 쓰고, Vela mac_count와 섞지 않는다.

## 2. 검증된 MAC_ACTIVE 규칙 (범위 밖은 EXTRAPOLATED)

| 규칙 | 식 | 검증 범위(보드 VALID) |
|---|---|---|
| R_DW | Ho·Wo·⌈C/16⌉·16·K²/128 | 3×3, stride 1, C 8–145 (Stage 4, 4C-1, 6C F2) |
| R_FC | ⌈Cin/16⌉·16 · ⌈Cout/16⌉·16 / 256 | Cin 95–96, Cout 287–288 (Stage 4) |
| R_PK3 | Ho·Wo·⌈Cin/16⌉·16·Cout·9/768 | 3×3, stride 1, Cin 16–64, Cout % 16 == 0 (4K) |
| R_H1UC | 6-M 연산별 `h1uc` 값 | 6-M BOARD_MEASURED 연산(동일 실행 구성) |
| R_EXACT | 6C 대표의 측정 MAC_ACTIVE | yolo op9(F1), yolo op3(F2), wav2letter op17(F4), kws op0(F5) — VALID |

- F3(rnnoise op46)는 UNSTABLE이므로 정량 근거에서 제외한다.
- PK1x1의 일반 규칙은 검증되지 않았다(Cout 96은 384, Cout 24는 192).

## 3. Coverage 수준 (연산마다, 위에서부터 처음 성립)

1. `INVALID_OR_UNSTABLE`: 대응 측정이 UNSTABLE 또는 무효(rnnoise op46, 6-M `measured_unstable_match`가 있는 연산).
2. `EXACT_VALIDATED`: 6-M BOARD_MEASURED. A2에서 Conv IFM/OFM이 SRAM이라 모델과 같은 조건이다.
3. `CONFIGURATION_MATCHED`: 6C VALID 대표 연산. 계산 구성은 같고 graph IO 메모리는 다르다.
4. `CLASS_SUPPORTED`: R_DW / R_FC / R_PK3의 검증 범위 안.
5. `EXTRAPOLATED`: 규칙이 있는 연산군인데 범위 밖이거나(R_DW·R_FC·R_PK3·R_H1UC 연장), 6-M EXTRAPOLATED_PREDICTION이거나, PK1x1·PK1D·FIRST_CONV의 대표가 아닌 연산.
6. `UNSUPPORTED`: 그 밖(OTHER_CONV 등).

- 수준은 합산하지 않는다. 모델마다 수준별 N_MAC 비중과 연산 개수 비중을 따로 낸다.
- 1–4 수준의 연산은 예측값 P를 가진다(4는 규칙, 2는 h1uc, 3은 측정값).
- EXTRAPOLATED 중 식이 있는 연산은 P_ext를 가진다(규칙 연장, h1uc). 식이 없는 연산은 예측하지 않는다.

## 4. 모델 판정 (compute = MAC_ACTIVE, 측정 M = driver runner `65cf963`, TA profile 1, `mlek_wd.json`)

- c = 수준 2–4 연산의 N_MAC 비중, P = 그 연산들 예측의 합.
- 판정:
  - `QUANTITATIVELY_EXPLAINED`: c ≥ 0.90이고 0.85·M ≤ P ≤ 1.05·M.
  - `NOT_EXPLAINED`: P > 1.05·M(덮은 부분만으로도 측정을 넘음), 또는 c ≥ 0.90인데 P < 0.85·M.
  - `PARTIALLY_EXPLAINED`: 0.50 ≤ c < 0.90이고 P ≤ 1.05·M.
  - `QUALITATIVE_SUPPORT_ONLY`: c < 0.50이고, 어떤 연산이 수준 2–5에 속함.
  - `INSUFFICIENT_EVIDENCE`: 그 밖(측정 없음, 근거 없음).
- 실행시간(NPU_ACTIVE): 모델 수준에서 검증된 예측기가 없다(독립 연산의 graph IO는 DDR이고, 파이프라인 중첩이 측정되지 않음). 그래서 모든 모델에 `NOT_EXPLAINED`를 주고, 이유를 함께 적는다.
- P_ext 버전(EXTRAPOLATED 포함)은 기술만 하고 판정에 쓰지 않는다.
- Stage 6-M 대비: 6-M의 coverage(1×1 DF만)와 6D c, 그리고 6-M 판정 대 6D 판정을 나란히 놓는다.

## 5. Unit / AXI / Vela (기술, 같은 조건끼리만)

- **Unit**: driver_m7(NPU, MAC, AO, WD, WD_STALLED)과 Stage 1 legacy 비율(DPU)을 쓰고, 조건을 표기한다.
- **AXI**: Stage 3 legacy(SRAM/EXT 바이트, 포트별, 요청 정체 6–18 %, 한계 정체)를 쓴다. 포트 물리 이용률은 계산하지 않는다.
- **Vela**:
  - 모델 board/Vela total(driver).
  - 연산군별 근거 방향: PK1x1 UNDER(F1), DW OVER(F2), PK1D OVER(F4), FIRST_CONV UNDER(F5), FC UNDER(Stage 4), DF1x1 MIXED(E1-R 0.76–1.27), PK3x3 MIXED(4K).
  - 모델마다 OVER 근거 연산군의 N_MAC 비중과 UNDER 비중을 계산한다. 둘 다 ≥ 0.10이면 `CANCELLATION_POSSIBLE`, 아니면 `NO_CANCELLATION_INDICATED`(기술).
  - 연산별 오차를 모델 오차로 귀속하지 않고, 보정 계수를 만들지 않는다.

## 6. 공백과 단일 권고 (`recommend`, 고정 규칙)

후보 공백(고정 목록, 각각 영향받는 연산군):

| 공백 | 영향 연산군 | controllable | discriminating | cost(boot) |
|---|---|---|---|---|
| G_PK1X1 (PK1x1 Cout 의존 처리율) | PK1x1 | 예 | 예 (Cout 24 대 96, 공간 크기 분리) | 6 |
| G_DF_EXT (DF1x1 H1-UC 외삽 영역) | DF1x1 | 예 | 예 | 9 |
| G_FC (FC 불안정) | FC | 예 | 아니오 (불안정 원인 변수가 정해지지 않음) | 4 |
| G_DW_VELA (F2 Vela 방향 반대, stride·커널·큰 C) | DW | 예 | 예 | 6 |
| G_PK1D (1×7·1×48) | PK1D | 예 | 예 | 3 |
| G_FIRST (첫 Conv 다른 형상) | FIRST_CONV, PK3x3 | 예 | 예 | 4 |
| G_AO1 (ABS N/32) | (MAC 없음) | 예 | 예 | 4 |
| G_WD (WD-1/2) | (MAC 없음) | 예 | 예 | 4 |

점수 기준:
- impact = 7개 모델 중 그 연산군이 EXTRAPOLATED/UNSUPPORTED/INVALID 수준으로 남긴 N_MAC 비중의 최댓값. AO-1·WD는 MAC 비중을 정의할 수 없어 0으로 둔다.
- controllable, discriminating, cost(boot)는 표에 고정한다.

선정: controllable이고 discriminating이며 cost ≤ 9인 후보 중 impact가 가장 큰 것 하나를 권고한다. 같으면 표 순서가 앞선 것. 실행은 승인 전까지 하지 않는다.

## 7. 검증

- 테스트 `test_stage6d`, mutation 전부 KILLED, `test.sh` ALL PASS.
- 분석 2회 바이트 동일, 기존 파일 불변. 로컬 커밋만 한다.
