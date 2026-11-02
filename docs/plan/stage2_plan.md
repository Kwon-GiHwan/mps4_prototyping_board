# Stage 2 진행 순서 (2026-11-03)

Owner 결정 2026-11-03: Stage 2A 문서(사용자 제공, "Pipeline 활동 및 정체 분석")를 기준으로 진행. "2A에서 못한 것도
채우고 진행하자". 단계마다 끝나면 결과를 아래와 결과 폴더에 기록하고 보고한다. 비용 시계 = NPU 사이클
(S0-3 해소, `results/fi101_s0_3_clk/`). 보드 측정은 TA profile 1, 7개 MLEK 모델(부분집합은 계약에 이유 명시).

| # | 단계 | 내용 | 보드 | 상태 |
| --- | --- | --- | --- | --- |
| 2A | 모델 단위 활동·정체 | 기존 Pass A·D·E(boots 94–100) 재정리, 의미 일관성 점검, 모델별 확인, 2B 후보 (`results/fi101_stage2a/`, `2d5a7ef`) | 없음 | **완료** |
| 2A-F1 | RUN 간 안정성 | 지표별 RUN 간 범위(min–max, 상대 폭) — 2A 표의 숫자가 모델 차이를 말할 만큼 안정적인가 | 없음 | **완료** |
| 2A-F2 | stall이 처리부 활동 중인가 쉬는 중인가 | `PMCLUT` 복합 이벤트로 `unit_active AND stall` 직접 계수 → 2A 읽기 1("stall ≠ 병목")을 측정으로 확인. 먼저 같은 RUN 항등 검사(LUT가 단일 이벤트를 고르면 원 계수와 같아야 함)로 기능 검증 | 있음 | 대기 |
| 2B-0 | 그룹 계측 가능성 | `PMCR.mask_en` + 명령 스트림에 `NPU_OP_PMU_MASK` 삽입(TRM "debug feature", 보드 미검증). 검사: 전체 enable = 마스크 없는 값, (앞 구간) + (뒤 구간) = 전체 | 있음 | 대기 |
| 2B-1 | 그룹 정의·도구 | Vela 연산 ↔ 명령 스트림 경계 매핑, 그룹(depthwise / 작은 의존 블록 / 낮은 채움 conv / 기준 conv)별 마스크 blob 생성 | 없음 | 대기 |
| 2B-2 | 그룹 측정 | 7개 모델, 그룹별 사이클·활동·stall, Σgroup vs 전체 | 있음 | 대기 |

2A-F2와 2B-0은 같은 펌웨어 변경(PMCLUT·mask_en knob)을 쓰므로 한 이미지·한 캠페인으로 묶는다(계약은 각각 판정).

## 단계별 기록

### 2A-F1. RUN 간 안정성 — 완료 2026-11-03 (`results/fi101_stage2a/run_spread.csv`)

- 97개 숫자 칸의 상대 폭(max−min)/median 중앙값 1.5 %. 큰 폭은 값이 아주 작은 칸(`mac_stalled_by_acc` kws·ad)과
  rnnoise(stall ±10 %)뿐. 2A 읽기에서 쓴 모델 구분(IB 높은 군 0.271–0.342 vs 낮은 군 ≤ 0.155, blockdep 순위)은 RUN
  범위가 겹치지 않는다. yolo vs mobilenet IB 차이(~1 %)는 순위로 쓰지 않는다. `POST_HOC_DESCRIPTIVE`.
