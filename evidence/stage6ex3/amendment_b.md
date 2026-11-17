# Stage 6E-X3 계약 Amendment B — G1 재현 기준 수정과 결정적 카운터 gate (보드 boot 487–496 전에 동결)

지시: `docs/plan/stage6ex3_amendment_b_chatgpt.txt`(2026-11-18). 전향적 수정이다.

**바꾸지 않는 것**:
- boot 477의 원시 자료와 판정(G1 FAIL, MEASUREMENT_INVALID; `result_g1.md`), 이전 preflight `dc7709c`.
- 계약 `contract.md`의 나머지(구성, 유효성, GS, GM, 가설 H-S·H-P·H-K·H-A·H-O·H-V, 해석 제한).
- 펌웨어 f0baf8c, 이미지, 워크로드 digest, TA profile 1, EXT RLATENCY 500, placement 0.

## 1. G1 변경

| | 변경 전 (contract §4) | 변경 후 (Amendment B) |
|---|---|---|
| NPU_ACTIVE | \|B0 − m7\| ≤ 1 % × m7 (pass A 중앙값) | \|B0 − m7\| ≤ max(1 % × m7, range_m7 + range_B0), 그리고 range_B0 ≤ R_cap(m7 세트별 NPU_ACTIVE range의 최댓값) |
| 결정적 카운터 | max(1 %, range 합) | **정확 일치**: 48, 51, 128, 130, 132, 135, 384, 386, 391, 640, 642, 656, 658이 B0 측정 RUN 모두 m7 중앙값과 같고, B0·m7 range가 모두 0 |
| 그 밖의 카운터 (53 55 64 80 81 131 142 387) | max(1 %, range 합) | 같음 |
| B0 VALID, pmu_flags 0, mask_en 0, 출력 golden | 필수 | 같음 |

- **range의 정의**: 같은 조건의 측정 RUN에서 max − min이다. m7은 warm-up 2를 뺀 8 RUN, B0는 warm-up 1을 뺀 4 RUN이다. NPU_ACTIVE의 m7 기준은 pass A(m7 set 2)다.
- **R_cap**: m7 원시 자료의 세트별(BASE와 A–G, 측정 RUN) NPU_ACTIVE range 중 최댓값이다. B0 하나가 잡음으로 허용폭을 키워 통과하는 것을 막는다.
- **변경 사유**: 동결한 ±1 % 중앙값 기준이 기준값 자체의 RUN 간 변동보다 좁았다. m7 pass A RUN range는 kws 2,423(2.64 %), ad 1,774(1.22 %)이고, 세트별 중앙값도 kws 90,822–91,824(1.1 % 폭)로 움직인다.
- **임계값을 정한 근거**: 계산식과 m7 원시 분포로만 정했다. boot 477의 값은 임계값을 정하는 데 쓰지 않았다(사용한 것은 "±1 %가 m7 변동보다 좁다"는 사실뿐이다).

**사전 계산한 허용폭** (m7 원시 자료):

| 모델 | m7 pass A 중앙값 | range_m7 (A) | R_cap (세트별 최대) | 최소 허용폭 | 최대 허용폭(range_B0 = R_cap) |
|---|---|---|---|---|---|
| kws | 91,824.5 | 2,423 | 2,423 | 918.2 (1 %) | 4,846 (5.28 %) |
| ad | 145,949.5 | 1,774 | 2,596 | 1,459.5 (1 %) | 4,370 (2.99 %) |

## 2. 한계 (사전 기록)

- 이 기준은 두 세션 중앙값 차이에 대한 경험적 허용 기준이다. 신뢰구간이 아니며 실행 동등성의 증명도 아니다.
- 최대 허용폭(kws 5.3 %)은 넓다. 이 범위 안의 실제 성능 차이는 놓칠 수 있다. 그래서 결정적 카운터의 정확 일치와 출력 일치를 함께 요구한다. 단, 카운터가 같다는 것도 실행 동등성의 증명은 아니다.
- B0가 UNSTABLE(pass A range > 5 %)이면 G1은 실패한다. 허용폭을 넓혀 통과시키지 않는다.

## 3. 판정 항목 (지시 §9; 기존 판정 기준 유지, 둘 추가)

- **Baseline Reproducibility**: 모델별로 G1 PASS이면 REPRODUCED, FAIL이면 NOT_REPRODUCED, B0이 없으면 INSUFFICIENT_EVIDENCE다.
- **PMU_MASK Functionality**: kws GM의 M2와 M3이 모두 성립하면 FUNCTIONAL이다. 하나라도 성립하지 않으면 NOT_FUNCTIONAL, kws 직렬 boot가 측정되지 않았으면 INSUFFICIENT_EVIDENCE다. 레코드의 mask_en=1은 GS(identity)에서 확인한다.
- Measurement, Group Attribution, Compute Explanation, Serialization, Vela Fidelity는 contract §6 그대로다.
- **Vela 공식 지표**:
  - 그룹·전체 비교의 분모는 **cycles_total**(per-layer Op Cycles 합)이다.
  - cycles_npu 기준 비율(원본·직렬)은 병렬로만 기술하며, 6-M·6D·6E-0의 cycles_npu 기준 값과 같은 계열로 비교하지 않는다.

## 4. 실행

- boot 487–496: kws B0–B4, ad B0–B4, 3 pass × 5 RUN, 10 boot / 150 RUN이다. X3 누적은 11 boot / 165 RUN이다.
- staging `~/evsweep_x3b_img`, run root `~/evsweep_x3b_run`, evidence root `~/evsweep/evidence_x3b`이다(boot 477의 경로와 분리).
- 세션 gate는 contract §4와 같다: G1(새 기준)은 각 B0 뒤, GS는 각 직렬 boot 뒤, GM은 kws B4 뒤(실패 시 ad 진행 안 함). 실패하면 중단·복원한다. 추가 boot나 재측정은 없다.
- 판정 코드 `host/analysis/stage6ex3.py`(BOOT 487–496, G1 Amendment B), 테스트 `test_stage6ex3` 28개, mutation 81/81.
