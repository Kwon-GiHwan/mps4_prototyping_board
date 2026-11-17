# Stage 6 최종 재평가 계획 (Stage 6C 결과 이후)

Stage 6-M 판정 `COVERAGE_EXPANDED_NOT_EXPLAINED`는 유지한다. Stage 6C 결과가 나오면 아래 자료로 다시 평가한다.

## 준비 자료

| 자료 | 원천 |
|---|---|
| 연산군별 characterization coverage | `results/fi101_stage6m/mac_family_breakdown.csv` + Stage 6C 연산군(F1–F5) |
| 모델별 N_MAC 비중(TFLite) | `mac_family_breakdown.csv` |
| MAC 활성 중 처리 효율 | 모델: driver_m7(`fi101_stage4wd/mlek_wd.json`), 연산군: Stage 4/4C/4K/6B/6C |
| Unit 활동 패턴 | `results/fi101_stage6c0/integrated.csv` + Stage 6C |
| 메모리 트래픽·접근 조건 | Stage 3(모델), Stage 6C Pass B·C(연산군) |
| NPU_ACTIVE, Vela 예상과 오차 | `vela_fidelity.csv` + Stage 6C |

## 다시 볼 현상

| 현상 | Stage 6C 근거 후보 |
|---|---|
| KWS 대 AD 효율 차이 | F5(kws 첫 Conv 17.6 %), 1×1 DF 외삽 비중 |
| rnnoise 낮은 MAC 활성(1.1 %), Vela 과소 1.53 | F3 FC 처리율·WD-1 |
| yolo·vww4 AO 우세 | F1(1×1 PK)·F2(DW)의 AO/MAC 비 |
| wav2letter 높은 MAC 효율 | F4(1×32 PK) 처리율 |

## 규칙

- 독립 연산 결과를 모델 안 연산의 실행시간으로 직접 귀속하지 않는다. graph IO 위치, 캐스케이드, 의존성이 다르기 때문이다.
- 설명 범위는 "같은 연산군·처리율 규칙이 모델 MAC_ACTIVE와 일치하는가"(H1-UC 방식)까지로 한정한다. NPU_ACTIVE 귀속은 별도 근거가 있을 때만 한다.
- 판정 규칙은 Stage 6C 결과 전에 동결한다.
