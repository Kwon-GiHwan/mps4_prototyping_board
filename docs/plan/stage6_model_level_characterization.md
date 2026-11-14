# Stage 6 — Model-level Hardware Characterization: 계획과 수행 기록

상태: **2026-11-15 보드 없는 분석 완료, READY_FOR_RESEARCH_REVIEW.** 결과 `results/fi101_stage6/README.md`, 근거 `evidence/stage6/`.

## 목적과 범위 (owner 지시, ChatGPT 경유)

Stage 4–4WD의 단일 연산 특성 (MAC·AO·WD·메모리)이 7개 MLEK 모델의 whole-model 측정 (driver_m7, TA profile 1)을 어디까지 설명하는지 평가한다.
- 신규 보드 RUN, TA·이미지 변경, 층별 실행 시간 귀속, Stage 2B 그룹 귀속 재사용, Transformer, push는 하지 않는다.

## 수행 순서

1. 적용 규칙·허용폭·판정 순서를 계산 전에 고정 (`evidence/stage6/rules.md`, `cbf8e23`).
2. 기준 데이터 확인:
   - driver_m7 원시 RUN 유효성과 RUN 수
   - Vela sha256 일치 (인벤토리 = 측정 DRWL)
   - 보고 중앙값과 원시 재계산 대조
   - 출력 dtype (원본 tflite)
3. 스케줄된 NPU 연산 591개를 축별로 T0 / T1_INTERP / T1_EXTRAP / T2 / U로 분류.
   - fused 0-cycle 행과 CPU·제거 연산을 표시해 중복 집계를 막았다.
4. 축별 coverage (MAC: Vela mac_count, AO: OFM 원소 (⌈C/16⌉·16), WD: spatial block × weight bytes)와 calibrated estimate 계산.
5. coverage가 0.80 이상인 축만 whole-model과 정량 비교 (허용폭 10 %). 현상 P1–P7은 rules §5 순서로 판정.
6. 테스트 (10개), mutation (18/18), test.sh ALL PASS. 기존 Stage 4–4WD 산출물은 바뀌지 않았다 (git status 확인).

## 결론

- 단일 연산 카탈로그가 모델 MAC의 0–22 %만 보정 범위로 덮는다. 정량 판정은 wav2letter AO (CONSISTENT, −3.5 %) 하나다.
- 현상 P1–P7은 모두 INSUFFICIENT_EVIDENCE다.
- 다음 단계 판단은 C (구조적 한계)다. 1×1 DepthFirst Conv 처리율 지도가 1순위 측정 후보다 (결과 README의 우선순위 참고).
