# A9 — S4 (U85 stall 이벤트 원시 수집) 종결: NOT_EVALUABLE

**2026-09-14.** 계획서 §11(정정 1–4), 매니저 4차 GO(탐색적 원시값 수집 범위), 7차 결정 (a).

## 기록 문구 (매니저 확정)

첫 셀 qualification 실패로 캠페인 중단; 추가 이벤트 원시값은 성능·병목 분석에 사용하지 않음.

## 무엇을 했나

- 대상 첫 셀 RNNoise U85 256 MAC. 순서 clean → A → B, 각 3회. 패치는 core-driver
  `ethosu_driver.c`만, 적용·복원을 digest로 증명(stock `56b2fecb…963f`로 복원 확인).
- Qualification 1 (v1: HAL begin 훅 직전에 슬롯 5–7 EVTYPER+enable, end 훅 후 disable+read):
  clean 3회 = 동결값. 패치 빌드 A·B: TOTAL·beat 4종 동일, **ACTIVE −12(35,194), IDLE +12(892)** → G2·G7
  실패. `s4_stall/qual1_inference_time_patch/`.
- Qualification 2 (v2: `ethosu_init()` 끝에서 설정): 같은 −12 편차, 추가 카운터 전부 0.
  `s4_stall/qual2_init_time_patch/`.
- 게이트는 완화하지 않았다. 관측한 편차에 맞춰 허용오차를 사후 설정하지 않는다(매니저).

## 상태

| 항목 | 상태 |
|---|---|
| 첫 셀 (RNNoise 256) | qualification 실패 → `NOT_EVALUABLE` |
| 나머지 5셀 (RNNoise 512, KWS 256/512, Wav2Letter 256/512) | **미실행** (실패가 아님) |
| v1 추가 이벤트 원시값 (MAC_ACTIVE 1,590 / MAC_STALLED_BY_W 18,818 / MAC_STALLED_BY_IB 1,707 / AO_STALLED_BY_OB 0 / NPU_IDLE 이벤트 901 / OVS 0) | 보존만. 성능·병목 분석에 사용하지 않음 |
| 편차 원인 | 미확인. "코드 크기·정렬에 따른 CPU 측 타이밍"은 추정이며 확인하지 않았다 |
| event_semantics | SEMANTICS_UNVERIFIED |
| output_tensor_equivalence | NOT_TESTED |

## 요인 판정에 미치는 영향

없음. 요인 1·2의 stall 근거는 여전히 없다. 요인 2는 A8(X4)의 개입 효과 관측으로만 갱신된다.

## 다시 시도한다면

계약을 새로 쓰고(매니저), 편차 원인을 먼저 분리해야 한다: 패치 코드를 포함하되 실행하지 않는 더미
빌드로 바이너리 효과를 분리하는 qualification, 그리고 HAL 프로파일러 경로와의 상호작용 확인. 이 세션
범위 밖이다.
