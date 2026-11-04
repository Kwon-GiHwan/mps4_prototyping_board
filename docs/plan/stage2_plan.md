# Stage 2 진행 순서 (2026-11-03)

Owner 결정 2026-11-03: Stage 2A 문서(사용자 제공, "Pipeline 활동 및 정체 분석")를 기준으로 진행. "2A에서 못한 것도
채우고 진행하자". 단계마다 끝나면 결과를 아래와 결과 폴더에 기록하고 보고한다. 비용 시계 = NPU 사이클
(S0-3 해소, `results/fi101_s0_3_clk/`). 보드 측정은 TA profile 1, 7개 MLEK 모델(부분집합은 계약에 이유 명시).

| # | 단계 | 내용 | 보드 | 상태 |
| --- | --- | --- | --- | --- |
| 2A | 모델 단위 활동·정체 | 기존 Pass A·D·E(boots 94–100) 재정리, 의미 일관성 점검, 모델별 확인, 2B 후보 (`results/fi101_stage2a/`, `2d5a7ef`) | 없음 | **완료** |
| 2A-F1 | RUN 간 안정성 | 지표별 RUN 간 범위(min–max, 상대 폭) — 2A 표의 숫자가 모델 차이를 말할 만큼 안정적인가 | 없음 | **완료** |
| 2A-F2 | stall이 처리부 활동 중인가 쉬는 중인가 | `PMCLUT` 복합 이벤트로 `unit_active AND stall` 직접 계수 → 2A 읽기 1("stall ≠ 병목")을 측정으로 확인. 먼저 같은 RUN 항등 검사(LUT가 단일 이벤트를 고르면 원 계수와 같아야 함)로 기능 검증 | 있음 | **완료**: LUT_IDENTITY_EXACT, stall∧active = 0 (7개 모델) |
| 2B-0 | 그룹 계측 가능성 | `PMCR.mask_en` + 명령 스트림에 `NPU_OP_PMU_MASK` 삽입(TRM "debug feature", 보드 미검증). 검사: 전체 enable = 마스크 없는 값, (앞 구간) + (뒤 구간) = 전체 | 있음 | **완료**: MASK_DISTURBS (kws, 1 % 기준 < kws 흔들림) / mobilenet MASK_WORKS → 재확인 필요 |
| 2B-0b | 마스크 재확인 | 7개 모델, 대조 2회(A/A), 대조 자신의 RUN 폭 기준 (`evidence/s2_mask/`) | 있음 | **완료**: MASK_NOT_ADDITIVE (교란 없음 7/7, 합산 3/7) |
| 2B-1 | 그룹 정의·도구 | Vela 연산 ↔ 명령 스트림 경계 매핑, 그룹(depthwise / 작은 의존 블록 / 낮은 채움 conv / 기준 conv)별 마스크 blob 생성 | 없음 | 대기 |
| 2B-2 | 그룹 측정 | 7개 모델, 그룹별 사이클·활동·stall, Σgroup vs 전체 | 있음 | 대기 |

2A-F2와 2B-0은 같은 펌웨어 변경(PMCLUT·mask_en knob)을 쓰므로 한 이미지·한 캠페인으로 묶는다(계약은 각각 판정).

## 단계별 기록

### 2A-F1. RUN 간 안정성 — 완료 2026-11-03 (`results/fi101_stage2a/run_spread.csv`)

- 97개 숫자 칸의 상대 폭(max−min)/median 중앙값 1.5 %. 큰 폭은 값이 아주 작은 칸(`mac_stalled_by_acc` kws·ad)과
  rnnoise(stall ±10 %)뿐. 2A 읽기에서 쓴 모델 구분(IB 높은 군 0.271–0.342 vs 낮은 군 ≤ 0.155, blockdep 순위)은 RUN
  범위가 겹치지 않는다. yolo vs mobilenet IB 차이(~1 %)는 순위로 쓰지 않는다. `POST_HOC_DESCRIPTIVE`.

### 2A-F2 / 2B-0. PMCLUT·PMU_MASK 보드 시험 — 완료 2026-11-03 (`results/fi101_stage2_probe/`)

- 계약 `evidence/s2_probe/contract.md`(`62cf7f4`, amendment 1 `043e492`: boot 170 첫 PING 무응답 → boot 176 재실행).
  이미지 `d0cd4775`, TA profile 1, boots 158–176, 완료된 부팅의 RUN 전부 유효.
- **2A-F2:** `LUT_IDENTITY_EXACT`. 7개 모델 × 4쌍에서 처리부의 stall과 active가 같은 사이클에 겹치지 않음(정확히 0)
  → stall 비율 = 처리부가 일하지 않은 시간 중 그 이유로 묶인 몫. 2A 읽기 1을 정정함. blockdep은 NPU 활동 중에만.
  MAC·AO 동시 활동 비율이 모델 효율 순서와 같음(wav2letter 0.90 … rnnoise 0.01).
- **2B-0:** 사전 판정 **`MASK_DISTURBS`**: kws가 1 % 기준을 넘음(npu_active −1.5 %). 명령 스트림이 정하는 이벤트
  (mac_active 등)는 같고, 대조·처리 RUN 범위가 모든 이벤트에서 겹침 → kws 자체 흔들림(2.9 %)보다 좁은 기준이라는
  계약 설계 오류. mobilenet은 `MASK_WORKS`(mac_active 합 정확히 일치, PMCCNTR도 마스크됨, 기본 꺼짐).
- 다음: 2B-0 재확인(흔들림을 고려한 기준, 짧은 모델 RUN 수 증가, 데이터 전 고정) 후 2B-1.

### 2B-0b. 마스크 재확인 — 완료 2026-11-04 (`results/fi101_stage2_mask/`)

- 계약 `evidence/s2_mask/contract.md`(`fbdeb69`), 이미지 `d0cd4775`, TA profile 1, boots 177–211, 700/700 RUN 유효.
- 사전 판정 **`MASK_NOT_ADDITIVE`**. 마스크는 실행을 교란하지 않음(7/7 passthrough, A/A 7/7) → 2B-0의 kws 실패는
  흔들림이었음. 합산은 ad·yolo·mobilenet만 통과, kws·rnnoise·vww4·wav2letter는 분할 경계에서 계수가 빠짐(항상 부족,
  한 경계당 12–1,980 사이클, 최대 이벤트의 4 %).
- 결정: 대안(스트림 분할, STOP+IRQ)은 연산 간 겹침을 없애 실행을 바꾼다. 마스크로 2B-2를 하되 **경계 손실을 미귀속
  몫(deficit)으로 직접 재고**, |deficit| ≤ 5 %인 모델에서만 그룹 비교(H1/H2)를 판정한다. 그룹 = 명령 스트림의 연산 유형
  (Vela 연산 ↔ 스트림 kernel op은 1:1이 아님: mobilenet 69 → 208).
