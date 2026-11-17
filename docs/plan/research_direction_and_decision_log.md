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
| Stage 6C-0 | 완료(보드 없음): 통합 95행·21쌍·Vela 57행, F1–F5 선정, 8형상 컴파일 검증, 6C 보드 초안 9 boot(승인 대기) | 74aa09d 동결 |
| Stage 6F-0 | 완료(보드 없음): kws·ad DECOMPOSED_PARTIALLY_PREDICTED(V 0.669/0.646, D 1), 나머지 6D 판정 재현; Runtime 7개 모두 미설명(kws·ad 직렬 분해만, 나머지 하한만); Vela cycles_total 기준 OVER 3·AGREE 1·UNDER 1·경계 2; 권고 X_LAT(12 boot, 승인 대기) | 동결 757da42 |

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
| 2026-11-18 | ChatGPT("Stage 6C 공식 지시", 사본 docs/plan/stage6c_directive_chatgpt.txt) | Stage 6C-0 수용, Stage 6C 보드 측정 승인: 9 boot / 135 RUN(측정 108, warm-up 27), Pass A·B·C, TA profile 1, runner 이미지 14077be, placement 0, PMCLUT 미사용. F1–F5 대표 + F1–F3 통제. F2 Vela 4배 변화의 이유를 컴파일 산출물로 확인하고 MAC 비용으로 해석하지 않음. F1·F2 대 F3·F4 NPU/MAC 비교는 관측 비교. F4·F5는 형상 민감도의 인과 판정 대상 아님. 결과 뒤 자동 확장 금지, 다음은 모델 수준 재평가. 사용자에게 선택지를 요구하지 않고 승인된 작업을 진행 |
| 2026-11-18 | Stage 6C 결과 | boot 468–476(TA profile 1, 14077be): PARTIAL_VALID(F3 쌍 UNSTABLE). 채널 16 올림 F1·F2 SUPPORTED, F4 처리율 992(0.969) SUPPORTED, H-VELA F1·F2 REFUTED(F1 과소 2.0, F2 과대 0.12/0.83, F2 C8→16 보드 ×1.73 대 Vela ×0.25), F4 Vela 0.58, F5 1.32. 다음은 ChatGPT 판단 대기(모델 수준 재평가 예정) |
| 2026-11-18 | ChatGPT: Stage 6C 수용, Stage 6D 확정 | 6C PARTIAL_VALID 수용, F3 불안정 보존, F2 Vela 반대 방향을 Compiler Fidelity 주요 반례로 보존. 다음은 Stage 6D(보드 없는 7개 모델 통합 재평가). 신규 보드·형상 실험 미승인. HW 특성·Vela 연구 지속, 특정 태스크 반복 추적 방지, 단일 권고, 사용자에게 선택지 요구 없음(지시 사본 docs/plan/stage6d_directive_chatgpt.txt) |
| 2026-11-18 | Stage 6D 결과 | 동결 82a398c. 정량 설명 0/7; kws·wav2letter PARTIALLY, ad NOT_EXPLAINED(coverage 0.92인데 P/M 0.646), 4개 QUALITATIVE_SUPPORT_ONLY, Runtime 전부 NOT_EXPLAINED. 6-M 판정 유지(coverage 증가, 실행시간 미설명). 단일 권고 G_DF_EXT(위험: ad 잔여 35 %는 답하지 않음). 실행은 승인 대기 |
| 2026-11-18 | ChatGPT: Stage 6D 수용, Stage 6E-0 확정 | COVERAGE_EXPANDED_NOT_EXPLAINED 유지. G_DF_EXT 즉시 보드 측정 미승인(유효 후보로 보존). 6E-0 정적 분석 승인: 모델 수준 NPU_ACTIVE 설명력과 Vela Fidelity 우선, HW 특성 연구 지속, H1-UC·SRAM 배치 과집중 금지, 식별력 기준 단일 권고, 선택지 요구 없음(지시 사본 docs/plan/stage6e0_directive_chatgpt.txt) |
| 2026-11-18 | Stage 6E-0 결과 | 동결 034ef0e. Compute Attribution kws·ad·wav2letter PARTIALLY_EXPLAINED, 나머지 NOT_IDENTIFIABLE; Execution Cost REQUIRES_CONTROLLED_EXPERIMENT(기존 계측 연산별 시간 귀속 0/5); Vela TESTABLE_MECHANISM_IDENTIFIED; 단일 권고 X3(직렬화 KERNEL_WAIT n=0 + 그룹 PMU_MASK, kws 방법 검증·ad 잔차, 10 boot) READY_FOR_BOARD_REVIEW. 보드 실행은 승인 대기 |
| 2026-11-18 | ChatGPT: Stage 6E-0 수용, X3 조건부 승인 | X3 SERIAL_MASK: kws·ad만, 10 boot / 150 RUN(측정 120, warm-up 30), Pass A·B·C, TA profile 1, EXT RLATENCY 500, 이미지 14077be. 정적·동적 preflight 통과 필수, 실패 시 실행 중단. B2–B4는 같은 직렬 스트림에 PMU 측정 구간만 다르게. 직렬−원본 차이를 순수 중첩 이득으로 단정하지 않음, Vela의 직렬 예측 정확도 가정 안 함, 2B 귀속 오류 재발 방지, 추가 모델·형상·TA·계측 방식 미승인, 결과 후 모델 수준 재평가, 선택지 요구 없음(지시 사본 docs/plan/stage6ex3_directive_chatgpt.txt) |
| 2026-11-18 | Stage 6E-X3 preflight FAIL | 승인 이미지 14077be에서 PMU_MASK 무효(driver runner가 PMCR.mask_en을 설정하지 않음, 6C 135 RUN pmcr_at_arm 0x4001). 지시대로 보드 실행 안 하고 원인만 보고. 6E-0 구현 표 오류는 정오표로 기록(결과 불변) |
| 2026-11-18 | ChatGPT: X3 Amendment A | preflight 실패 수용, 원인 PMCR.mask_en 미설정 확정, 기존 이미지로 그룹 귀속 불가. 최소 펌웨어 수정 승인(DRWL 플래그가 있을 때만 mask_en=1, 기본 0 = 14077be 동작). 신규 이미지 동등성·PMU_MASK 실제 동작 검증 필수(첫 boot kws B0 gate: TA·mask_en=0·NPU ±1 %·Unit·전송·golden·identity; mask gate는 기존 예산 안). X3 예산 10 boot / 150 RUN 유지, 추가 모델·TA·boot 미승인, 특정 계측 문제 과집중 금지, 선택지 요구 없음(사본 docs/plan/stage6ex3_amendment_a_chatgpt.txt) |
| 2026-11-18 | Stage 6E-X3 boot 477: G1 FAIL로 중단 | kws B0(새 이미지 f0baf8c, TA profile 1) VALID, 결정적 카운터 m7과 동일, NPU_ACTIVE −1.57 %(동결 기준 ±1 % 초과; m7 자체 RUN 범위 2.6 %). 계약대로 중단·복원·postflight. 1/10 boot 사용. 사후 기준 변경 없음, ChatGPT 판단 대기 |
| 2026-11-18 | ChatGPT: X3 Amendment B | A의 G1 FAIL 수용, boot 477 결과 불변. G1 NPU 기준을 max(1 % × m7, range_m7 + range_B0)로(측정 변동성 반영), 결정적 PMU/AXI 카운터 정확 일치 gate 추가, 측정 전 동결. 신규 세션 boot 487–496(10 boot / 150 RUN), X3 누적 11 boot / 165 RUN. TA profile 1·펌웨어 f0baf8c 유지. Vela cycles_npu / cycles_total 구분 필수. 그룹 귀속 성공·실패 뒤 전체 연구로 복귀, 선택지 요구 없음(사본 docs/plan/stage6ex3_amendment_b_chatgpt.txt) |
| 2026-11-18 | Stage 6E-X3 Amendment B 세션: boot 489에서 중단 | kws B0 G1 PASS(−0.41 %, 결정적 카운터 정확 일치), kws B1 VALID, kws B2 UNSTABLE(창 NPU range 6.7 % > 5 %) → GS 실패로 중단·복원·postflight. 기술: G_V 창 MAC 11,700 = h1uc, 직렬 NPU +14.9 %. 3/10 boot 사용(누적 4). 사후 재판정 없음, ChatGPT 판단 대기 |
| 2026-11-18 | ChatGPT: X3 Amendment C (마지막) | B의 GS FAIL 수용, boot 489 결과·판정 보존. kws B0(487)·B1(488) 유효 결과 재사용. 그룹 창(B2–B4) pass A NPU range 기준만 max(5 %, cap)로 수정(kws 2,423 / ad 2,596, m7 세트별 range 최댓값). boot 497–504, 8 boot / 120 RUN, X3 누적 12 boot / 180 RUN. PMU_MASK 기능·분할 일관성·독립 기준 일치·시간 귀속 유효성을 따로 판정, 측정 변동이 판별 차이보다 크면 해당 정량 가설 INSUFFICIENT. Amendment C 뒤 X3 종료(추가 Amendment·재측정 금지), cycles_npu/cycles_total 구분, 전체 연구로 복귀, 선택지 요구 없음(사본 docs/plan/stage6ex3_amendment_c_chatgpt.txt) |
| 2026-11-18 | Stage 6E-X3 종료 (Amendment C 결과) | boot 497–504 + 487/488: Measurement VALID, Baseline REPRODUCED(kws −0.41 %, ad +0.13 %), PMU_MASK FUNCTIONAL, 분할 CONSISTENT, 독립 기준 AGREES(kws op0 26,090 = F5, G_V = h1uc 정확), 시간 귀속 VALIDATED_FOR_KERNEL_UNITS, Group Attribution VALIDATED, ad 잔차 33,192 = G_0 16,128 + G_R 17,064(RESIDUAL_REDUCED), 직렬화 +14.9 %/+12.4 %(SCHEDULE_EFFECT_OBSERVED), Vela(cycles_total) INSUFFICIENT_EVIDENCE. X3 누적 12 boot / 180 RUN, 종료 |
| 2026-11-18 | ChatGPT: X3 공식 종료, Stage 6F-0 확정 | X3 Amendment C 결과 수용(VALID, Group Attribution VALIDATED, RESIDUAL_REDUCED, Vela INSUFFICIENT). 추가 X3 없음. 다음은 보드 없는 Stage 6F-0(7개 모델 compute 재구성, 실행시간 설명력, Vela fidelity 재평가). 비율은 분모를 항상 명시(보고서의 12.9 %/11.6 %는 그룹 합 분모의 감소율). 신규 보드·펌웨어·컴파일·TA 변경 미승인(사본 docs/plan/stage6f0_directive_chatgpt.txt) |
| 2026-11-18 | Stage 6F-0 결과(보드 없음) | 동결 757da42. X3 그룹 반영: kws G_0·G_V, ad G_V PREDICTION_AGREES; ad G_0 EXTRAPOLATION_REFUTED(R_PK3 Cin 1→16 연장 36,864 대 16,128); kws G_R EXTRAPOLATION_REFUTED(예측/측정 0.698, 범위 안 DW 포함, 규칙별 귀속 불가); ad G_R NOT_TESTABLE(op10). N_MAC Coverage c는 7개 모두 6D와 같고 근거 수준만 상승. Compute: kws·ad DECOMPOSED_PARTIALLY_PREDICTED, 5개 모델 6D 판정 그대로(재현 7/7). Runtime: 검증된 예측기 없음, kws·ad SERIAL_DECOMPOSITION_ONLY, 나머지 LOWER_BOUND_ONLY(MAC/NPU 0.011–0.852). 원본 대비 직렬 +14.91 %/+12.42 %(분모 원본), 그룹 합 기준 12.90 %/11.59 %(분모 그룹 합). Vela cycles_total 기준: mobilenet·yolo·wav2letter OVER, ad AGREE, rnnoise UNDER, kws·vww4 INSUFFICIENT(경계가 range 안); cycles_npu 분류는 역사값으로 보존. 메모리 항 지배 비중과 과대예측의 관측적 연관(원인 미검증). 후속 단일 권고: X_LAT(직렬 그룹별 EXT 읽기 지연 민감도 + 같은 지연의 Vela 예측, kws·ad, 12 boot, 펌웨어 TA 노브 필요) — 승인 전 보드 미실행 |
