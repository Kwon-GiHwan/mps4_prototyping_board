# Stage 6E-0 계약 — 모델 수준 실행 비용 귀속과 Compiler Fidelity의 정적 식별 가능성 (보드 없음)

- 지시: ChatGPT "Stage 6E-0 공식 지시"(2026-11-18, 사본 `docs/plan/stage6e0_directive_chatgpt.txt`). Stage 6D 결과 `aad5265`.
- 이 계약과 판정 코드 `host/analysis/stage6e0.py`, 테스트는 결과 계산 전에 커밋한다.
- 보드, 펌웨어, TA 변경, 신규 컴파일은 없다. 기존 결과·판정은 바꾸지 않는다.

## 계약 전 노출 (무엇을 알고 규칙을 정했나)

- **이미 알고 있는 값**: 6D 결과(모델별 c, P/M, P_ext/M; ad P/M 0.646, P_ext/M 1.204, 수준 2–5 N_MAC 0.98)를 알고 있다. 그래서 ad의 Compute Attribution 판정은 아래 규칙으로 미리 짐작할 수 있다.
- **이 단계에서 읽은 기존 결과**: 2B-0b(mask), 2B-2(그룹 창 귀속 오류, ad CONV 효율 2.845), 2B-3(정적 명령 분석, 3a pilot, 3b 설계와 owner 검토), QREAD pilot 두 건.
  - 이 내용이 아래 계측 목록(§3)과 후보 평가표(§5)의 근거다.
- **판정 성격**: §5 후보 평가는 데이터가 아니라 설계 사실(명령 의미, 기존 도구, 이전 결과)에 대한 판단이다. 이 판단은 이 계약에 고정하며, 판정은 그 고정값을 기계적으로 따른다.

## 1. 모델별 세 차이 (Phase 1, 정의 고정; 같은 조건끼리만)

| 지표 | 정의 | 조건 |
|---|---|---|
| Compute Prediction Residual | R_c = M_MAC − P_v (P_v = 6D 수준 2–4 예측 합). 참고로 R_c,all = M_MAC − P_all (P_all = P_v + 6D P_ext; 외삽 포함, 판정 근거 아님) | driver TA1 |
| Execution Cost Residual | 유효한 모델 수준 NPU_ACTIVE 예측기가 없으므로 **계산하지 않는다**(`NOT_COMPUTED`) | — |
| Vela Prediction Error | E_v = NPU_ACTIVE − Vela npu cycles, 비율 NPU/Vela | driver TA1 |

- 같은 표에 Unit 비율(MAC, AO, WD ÷ NPU: driver; DPU/MAC, WD_STALLED: legacy Stage 1)을 둔다.
- AXI(SRAM/EXT 바이트, 요청 정체, 포트 불균형)는 legacy Stage 3이며, 출처 열로 조건을 표시한다.
- 세 지표는 서로 섞지 않는다.

## 2. Compute Attribution (모델별)

| 판정 | 조건 |
|---|---|
| `EXPLAINED_WITH_EXISTING_DATA` | 6D compute 판정이 QUANTITATIVELY_EXPLAINED |
| `PARTIALLY_EXPLAINED` | 그 밖에, 6D가 PARTIALLY_EXPLAINED이거나 **잔차가 예측 범위 안**(P_v ≤ 1.05·M, P_all ≥ 0.95·M, 예측값이 있는 N_MAC 비중 ≥ 0.95) |
| `NOT_IDENTIFIABLE` | 그 밖 |

- "범위 안"은 잔차가 아직 검증되지 않은 연산의 외삽 예측으로 덮일 수 있다는 뜻일 뿐이며, 귀속이 아니다.
- 기존 연산별 귀속 시도(2B-2 그룹 창)는 귀속 오류로 판정됐으므로 근거로 쓰지 않는다.
- **ad 잔차 진단**: ad의 연산별 표(수준, P, P_ext, Vela op/MAC cycles)와 잔차 R_c를 덮을 수 있는 후보 연산(외삽·불안정)의 P_ext 합을 기술한다. 귀속은 하지 않는다.

## 3. Execution Cost (전체)

기존 계측 목록(고정; 출처의 공식 판정):

| 계측 | 출처 | 연산별 시간 귀속 |
|---|---|---|
| NPU_OP_PMU_MASK (2B-0b) | `fi101_stage2_mask` | 없음(전체 스트림 무교란, 가산성 3/7) |
| 그룹 마스크 창 (2B-2) | `fi101_stage2_groups` | 귀속 오류(창 = 명령 해석 시점, 실행 아님) |
| 3a 창 pilot (2B-3) | `fi101_stage2b3/pilot` | 진단 라벨만(NOT_IDENTIFIABLE/AMBIGUOUS/LOCALIZED) |
| QREAD 추적 | `qread_pilot`, `qread_op_pilot` | TRACE_INVALID, NOT_ASSOCIATED(분해능) |
| PMCLUT 겹침 (2A-F2) | `fi101_stage2_probe` | 모델 전체 비율만 |

판정:
- `MEASURABLE_WITH_EXISTING_INSTRUMENTATION`: 목록 중 하나라도 유효한 연산별 시간 귀속을 냈을 때.
- `REQUIRES_CONTROLLED_EXPERIMENT`: 위가 아니고, 선정 후보(§5)가 c3·c4·c7을 모두 만족할 때.
- `NOT_IDENTIFIABLE`: 그 밖.

## 4. Vela Fidelity (전체)

- **기술**:
  - 모델마다 Vela 연산별 op cycles 합, MAC cycles 합, 그리고 "op > MAC"(Vela가 MAC 아닌 항을 최대로 고른) 연산의 op cycles 비중을 기술한다.
  - Vela npu cycles는 연산별 max(항)의 **합**이므로, 연산 사이 중첩이 없는 실행을 가정한 값이다(Regor 비용 모델; 6C-0 정리).
- 판정:
  - `TESTABLE_MECHANISM_IDENTIFIED`: 선정 후보가 c6를 만족하고, Vela의 합산 가정과 같은 조건(직렬 실행)에서 연산·그룹별 보드 비용을 낼 때(`vela_condition_match`).
  - `DISCREPANCY_CHARACTERIZED`: 위가 아니고, 6D가 7개 모델 모두 board/Vela를 분류했을 때.
  - `CAUSE_UNRESOLVED`: 그 밖.

## 5. 후속 실험 후보와 식별력 (고정 평가)

**기준**(지시 Phase 5):
- c1: 모델 수준 미해결 비용을 겨냥
- c2: 기존 근거로 해결 불가
- c3: 통제 독립 변수
- c4: 경쟁 가설이 다른 관측을 예측
- c5: NPU와 Unit/AXI를 함께 측정
- c6: Vela와 직접 비교
- c7: 2B 귀속 오류 회피
- c8: 모델 실행 조건(텐서 배치·명령 스트림·가중치·출력 검증) 보존
- c9: 다른 모델에 적용 가능
- c10: 종료 조건 정의

| 후보 | 내용 | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 | c10 | vela_condition_match | boot |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| X1 G_DF_EXT | DF1x1 외삽 형상 단독 측정 | 아니오(연산 coverage) | 예 | 예 | 예 | 예 | 예 | 예 | 아니오(graph IO DDR) | 예 | 예 | 아니오 | 9 |
| X2 PREFIX_STOP | 명령 스트림을 연산 k 뒤에서 자르고 STOP | 예 | 예 | 예 | 예 | 예 | 예 | 예 | 아니오(꼬리 스케줄 변경, 출력 검증 불가) | 예 | 예 | 아니오 | 10 |
| X3 SERIAL_MASK | 모든 커널 연산 앞에 KERNEL_WAIT n=0(직렬화), 직렬 스트림에 그룹 PMU_MASK 창 | 예 | 예 | 예 | 예 | 예 | 예 | 예 | 예(텐서·가중치·명령 순서·출력 golden 유지; 바뀌는 것은 겹침뿐이며 그것이 통제 변수) | 예 | 예 | 예 | 10 |
| X4 QREAD_FINE | QREAD 샘플링 강화 | 예 | 예 | 아니오 | 아니오 | 예 | 아니오 | 아니오(분해능 미달 선례) | 예 | 예 | 예 | 아니오 | 4 |
| X5 AD_REST_ISOLATED | ad op0·DW 단독 측정 | 아니오(ad 한 모델) | 예 | 예 | 예 | 예 | 예 | 예 | 아니오 | 아니오 | 예 | 아니오 | 4 |

**X3 설계 근거(TRM 인용은 2B-3)**:
- KERNEL_WAIT n=0은 "waits for all previous kernel operations be complete"이다.
- 따라서 "KERNEL_WAIT(0) → PMU_MASK(1) → 연산 k → KERNEL_WAIT(0) → PMU_MASK(0)" 창은 연산 k 실행만 담는다(mem2mem DMA는 예외이며, MAC·AO 카운터에는 해당 없음).
- owner의 3b 검토대로, 직렬 값은 원래 실행의 연산별 지연이 아니다. 원래 실행과의 차이(NPU_ACTIVE)가 곧 겹침 이득이며, 이를 통제 변수로 측정한다.

**선정 규칙**:
- 적격 = c1–c10 모두 예. 적격 중 boot가 가장 적은 것을 고르고, 같으면 표 순서를 따른다.
- 적격이 없으면 만족한 기준 수가 가장 많은 것을 고르되, 판정은 아래 규칙으로 한다.

**구현 항목**(선정 후보 X3; 상태 고정):

| 항목 | 상태 |
|---|---|
| cms 명령 경계·PMU_MASK 삽입 (`host/lib/cms.py` insert, pmu_mask) | EXISTS |
| KERNEL_WAIT n 인코딩(cmd0 opcode 18, `cms_timeline.py` 정의) | NEW_BOUNDED |
| COP1 COMMAND_STREAM 추출 (`pack_vela_workload.extract_cms`) | EXISTS |
| COP1 교체 후 tflite 재직렬화(컨테이너 flatbuffer 도구 존재) | NEW_BOUNDED |
| DRWL pack, identity | EXISTS |
| runner 펌웨어(명령 스트림 검증 없음, 변경 불필요) | EXISTS |
| driver runner에서 PMU_MASK·KERNEL_WAIT(0) 동작 | NEEDS_BOARD_PRECHECK(legacy runner에서 PMU_MASK는 무교란으로 확인됨; 같은 NPU) |
| 판정 코드·계약 | NEW_BOUNDED |

**Next Experiment 판정**:
- `READY_FOR_BOARD_REVIEW`: 선정 후보가 적격이고, 구현 항목에 `UNKNOWN_FEASIBILITY`가 없으며, `NEEDS_BOARD_PRECHECK` 항목은 예산 안의 첫 boot에서 확인하고 실패하면 멈추게 설계됐을 때.
- `STATIC_DESIGN_INCOMPLETE`: 적격 후보가 없지만 c4를 만족하는 후보가 있거나, 구현에 `UNKNOWN_FEASIBILITY`가 있을 때.
- `INSUFFICIENT_IDENTIFIABILITY`: c4를 만족하는 후보가 없을 때.

## 6. 산출과 검증

- `stage6e0_summary.json`, `model_differences.csv`, `ad_operators.csv`, 그리고 README(X3 정적 설계, 예산, 가설, 종료·복귀 포함).
- 테스트 `test_stage6e0`, mutation 전부 KILLED, `test.sh` ALL PASS, 2회 바이트 동일, 기존 파일 불변. 로컬 커밋만 한다.
