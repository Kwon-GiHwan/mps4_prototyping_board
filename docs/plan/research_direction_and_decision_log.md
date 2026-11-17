# Research Direction & Guardrails / User Request & Decision Log

매 단계 시작과 보고 전에 읽는다. 새 결정은 아래에 덧붙이고, 기존 결정을 덮어쓰지 않는다(변경 전·후와 이유를 함께 적는다).

## 최종 연구 목표

**Workload-Dependent Compute and Memory Characterization of Arm Ethos-U85**(Hardware–Compiler Performance Analysis)

| 연구 축 | 핵심 목표 |
|---|---|
| Compute / Unit | MAC·DPU·AO·WD의 처리율과 형상별 특성 |
| Memory / Pipeline / AXI | 데이터 공급, 버퍼, 요청, 트래픽, 병렬 실행과 지연 |
| Vela Compiler Fidelity | 예측 오차의 원인, 실행 구성에 따른 성능 차이 |
| Model-level | 7개 MLEK 모델의 효율과 NPU_ACTIVE 설명력 |

## 진행 원칙

- 특정 형상, PMU 이벤트, 메모리 배치 문제에 지나치게 집중하지 않는다.
- 새 실험마다 기존 실험과 비교해 어떤 새 지식을 주는지 명시한다. 이미 예상 가능하거나 검증된 결과는 반복 측정하지 않는다.
- 새 형상을 측정할 때는 연산 처리율, Unit 활동, AXI 트래픽, NPU_ACTIVE, Vela 예측 오차를 한 실험에서 함께 확보한다(2026-11-18 ChatGPT 결정).
- 실험이 끝나면 전체 연구 질문으로 돌아와 다음 우선순위를 평가한다.
- 관측, 가설, 원인 규명, 미해결을 구분한다.
- 계약과 판정은 결과 전에 동결하고 보존한다. 보드 측정은 승인된 범위에서만 한다.

## 사용자 요청 (누적)

| 날짜 | 요청 |
|---|---|
| 상시 | 보고는 한국어. 끝에 검증 수준 / 실제 실행한 것 / 실행하지 않은 것. 보드 수치에는 TA 상태를 함께 적는다. push HOLD, 로컬 커밋만. sudo 암호는 `.env`에서 파이프로만 쓴다 |
| 2026-11-15 | 작업 결과는 Chrome의 ChatGPT 창과 osascript JS로 주고받는다. "접근 불가"라고 하지 않는다. 답이 렌더링될 때까지 주기적으로 확인한다(JS 렌더링·가상화 확인) |
| 2026-11-18 | ChatGPT 창 이름은 "실험 계속 진행". 보고 끝에 "선택지를 띄우지 말고 하나의 결정으로 답해 달라"를 명시한다(선택지가 오면 진행이 막힘). ChatGPT의 판단이 나올 때까지, 그리고 그 판단대로 실험을 끝까지 진행한다. 요청 자체를 기록하고 매번 참고한다 |
| 2026-11-18 | (ChatGPT 경유) 연구 방향과 사용자 요청 이력을 매 지시에 포함하고 저장소에 누적한다 — 이 파일 |

## 현재 상태 (2026-11-18)

| 단계 | 판정 / 상태 | 커밋 |
|---|---|---|
| E2D Amendment A | VALID, PLACEMENT_EFFECT_OBSERVED, MECHANISM_UNRESOLVED | `ef0290f` |
| E2E-A | Track A NO_HISTORICAL_IMPACT, Track B READY_FOR_BOARD_REVIEW | `e53b618` |
| E2E-B | VALID, IO_PLACEMENT_EFFECT_OBSERVED, IO_SENSITIVITY_REDUCED, WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED | `650e79e` |
| E2E-C | READY_FOR_TARGETED_BOARD_REVIEW(방법 B) | `d94840d` |
| E2E-D | VALID, WEIGHT_SCALE_REMAP_CONFIRMED, B3_REPRODUCED, WEIGHT_PATH_DOMINANT_RESPONSE(R 0.064), MECHANISM_UNRESOLVED; L500에서 B3w +3,840 느림 | 결과 커밋 참조 |
| Stage 6C-0 | 지시 수신(2026-11-18). E2E-D 결과 뒤 진행. 보드 측정 미승인 | — |

## 다음 순서 (ChatGPT 2026-11-18)

1. E2E-D 결과로 Memory/Pipeline 축 종료 여부 결정
2. 기존 Unit/AXI/Vela 결과 통합(Stage 6C-0)
3. Stage 6C — PartKernel·DW·FC 등 미해결 연산의 Unit 특성과 Vela 예측
4. 7개 MLEK 모델 수준 재평가

## 결정 기록 (누적)

| 날짜 | 출처 | 결정 |
|---|---|---|
| 2026-11-18 | ChatGPT("E2E-D 결과 수용 및 Stage 6C-0 진행 지시") | E2E-D 종료, 판정 유지. Graph I/O와 Weight/Scale 경로의 EXT 지연 민감도 변화를 Hardware Memory Characterization의 검증된 결과로 정리. TA 지연 민감도를 Unit 대기시간이나 AXI 물리 활용률로 해석하지 않음. B3w가 L500에서 느린 현상은 미해결로 보존하고 신규 보드 실험은 미승인. Stage 6C-0을 동결 계약대로 완료하되, E2E-D가 선정 규칙에 영향을 주면 Amendment로 기록. 완료 후 통합 결과·신규 실험 필요성·최소 보드 예산·모델 설명력 기여를 보고하고 승인을 기다림. 신규 보드 측정·E3·메모리 배치 실험은 시작하지 않음 |
| 2026-11-18 | ChatGPT | 이후 모든 공식 지시에 Research Direction & Guardrails와 User Request & Decision Log 유지 지시를 포함 |
