# Stage 6F-0 계약 — 7개 모델 Compute 재구성, Runtime 설명력, Vela Fidelity 재평가 (보드 없음)

지시: ChatGPT "Stage 6F-0 공식 지시"(사본 `docs/plan/stage6f0_directive_chatgpt.txt`). X3 결과 `65c9b0e`.
이 계약과 판정 코드 `host/analysis/stage6f0.py`, 테스트, mutation 하네스는 결과 파일 생성 전에 커밋한다.
- 보드, 신규 컴파일, 펌웨어·TA 변경은 없다.
- 기존 결과 파일(6D 판정 포함)은 바꾸지 않는다. 새 값은 `results/fi101_stage6f0/`에만 쓴다.

## 계약 전 노출 (정직 기록)

계약을 쓰면서 다음을 보았다. 아래 규칙의 경계값은 모두 6D·X3에서 그대로 가져왔고, 이 값을 보고 새로 정하지 않았다.
- 6D 연산별 수준·P·P_ext(`fi101_stage6d/operator_levels.csv`)와 X3 그룹 MAC_ACTIVE. 따라서 kws G_R의 P 합(약 13,017 대 18,660)과 ad G_0(36,864 대 16,128)은 계산할 수 있는 상태였다.
- 7개 모델의 Σ per-layer Op Cycles. stage4 inventory에서 kws·ad 값이 Vela summary `cycles_total`과 같고, Σ NPU cycles가 7개 모두 `cycles_npu`와 같음을 확인했다. 그 과정에서 board/cycles_total 값도 보였다.
- 수준 경계(0.85·1.05·0.90·0.50)와 Vela 분류 경계(0.9·1.1)는 6D 값이다. 그룹 예측 허용폭(정확 대표 1 %, h1uc 5 %)은 X3 H-K 값이다.

## 입력 (모두 기존 동결 산출물)

| 자료 | 파일 | 조건 |
|---|---|---|
| 연산 분류·예측 | `results/fi101_stage6d/operator_levels.csv`, `stage6d_summary.json` | 6D(`aad5265`) |
| 모델 PMU | `results/fi101_stage6/summary.json` baseline | driver runner `driver_m7`, TA profile 1, pass A·B 측정 RUN 중앙값·range |
| Vela per-layer | `results/fi101_stage4/stage4_operator_inventory.csv` | Vela 5.0.0, MLEK 옵션, `Ethos_U85_SYS_DRAM_Mid_1024` |
| X3 그룹 | `results/fi101_stage6ex3/stage6ex3_summary.json` | driver runner 이미지 `f0baf8c`, TA profile 1(EXT RLATENCY 500), placement 0, pass A·B·C |
| AXI(legacy) | 6D summary `axi`(원천 Stage 3) | legacy runner, TA profile 1. driver 값과 섞지 않는다 |

## 1. X3 반영 — 그룹 판정 (`group_status`)

그룹 구성(TFLite 연산 번호): kws G_0 = {0}, G_V = {2, 4, 6}; ad G_0 = {0}, G_V = {2, 4, 6, 8}. G_R은 그 밖의 모든 NPU 연산이다.
그룹 MAC_ACTIVE는 X3 B2/B3/B4 pass A(set 1) 측정 RUN 중앙값이다.

그룹 MAC 연산(n_mac > 0)의 6D 예측으로 판정한다(위에서부터 처음 성립):
1. `PREDICTION_AGREES` / `PREDICTION_DISAGREES`: 모든 연산이 6D 예측 수준(EXACT_VALIDATED·CONFIGURATION_MATCHED·CLASS_SUPPORTED)에 있을 때 쓴다.
   - ΣP와 측정이 허용폭 안이면 AGREES, 아니면 DISAGREES다.
   - 허용폭: 그룹이 CONFIGURATION_MATCHED 연산만이면 1 %, 그 밖에는 5 %.
2. `EXTRAPOLATION_CONSISTENT` / `EXTRAPOLATION_REFUTED`: 모든 연산이 P 또는 P_ext를 가질 때 쓴다(예측 수준 + EXTRAPOLATED 혼합).
   - 0.85·M ≤ Σ(P 또는 P_ext) ≤ 1.05·M이면 CONSISTENT, 아니면 REFUTED다.
3. `NOT_TESTABLE`: 예측이 없는 연산(INVALID_OR_UNSTABLE, UNSUPPORTED)이 하나라도 있으면 쓴다. 부분 합은 기술만 한다.

**해석 한계**:
- 측정 MAC으로 예측을 바꿔 넣어 잔차가 사라지는 것은 "측정을 통한 잔차 분해"다. 전향적 예측 성공이 아니다.
- 여러 규칙이 섞인 그룹이 REFUTED이면 어느 규칙이 틀렸는지는 정하지 않는다.
- 그룹 NPU_ACTIVE는 직렬 실행의 비용이다. 그룹 SRAM/EXT/AXI는 시간 귀속 근거로 쓰지 않는다(mem2mem DMA).
- MAC 스케줄 불변성(B0 MAC = B1 MAC)은 kws·ad에서만 확인했고, 나머지 5개 모델에 적용하지 않는다.

## 2. 연산 수준 (6F, `level_6f`)

6D 수준을 보존하고(`level_6d`), 새 수준을 따로 둔다(위에서부터 처음 성립):

| level_6f | 조건 | 지시 분류 |
|---|---|---|
| DIRECT_IN_MODEL | 연산이 속한 X3 그룹이 PREDICTION_AGREES | 직접 검증(모델 내부) |
| DIRECT_ISOLATED | 6D EXACT_VALIDATED | 직접 검증(같은 실행 구성 독립 측정) |
| CONFIGURATION | 6D CONFIGURATION_MATCHED | 구성 일치 |
| CLASS | 6D CLASS_SUPPORTED | 연산군 수준 근거 |
| REFUTED | 6D EXTRAPOLATED이고, 연산 하나로 된 X3 그룹이 EXTRAPOLATION_REFUTED | 외삽 반례 |
| EXTRAPOLATED | 6D EXTRAPOLATED(그 밖) | 외삽 |
| UNSUPPORTED_OR_UNSTABLE | 6D INVALID_OR_UNSTABLE, UNSUPPORTED | 미지원·불안정 |

- 여러 연산으로 된 그룹의 판정은 연산 수준을 바꾸지 않는다. 열 `group`, `group_status`로 표시만 한다.

## 3. 모델 지표 (분모 명시)

모든 비중의 분모는 모델 TFLite N_MAC 합 또는 모델 측정 MAC_ACTIVE(M, driver_m7)다.
- **c**(N_MAC Coverage) = DIRECT_IN_MODEL·DIRECT_ISOLATED·CONFIGURATION·CLASS 연산의 N_MAC / 모델 N_MAC. 6D c와 같은 정의다.
- **P** = 그 연산들 예측의 합. **P/M** = MAC_ACTIVE 예측 Coverage.
- **V**(모델 내부 검증 비중) = PREDICTION_AGREES 그룹의 측정 MAC 합 / M.
- **D**(측정 분해 비중) = X3 그룹 MAC 합 / M. X3의 MAC 분할이 정확할 때만 계산하고, 그 밖에는 0이다.
- **외삽 의존도** = EXTRAPOLATED·REFUTED N_MAC / 모델 N_MAC.
  - `P_ext_6d`: 6D 정의 그대로다(REFUTED 연산의 P_ext 포함).
  - `P_ext_6f`: REFUTED 연산을 뺀다. 보정 계수는 만들지 않는다.

## 4. 모델 판정 (네 축, 각각 독립)

**Compute Coverage**: 위 c·외삽 의존도·수준별 비중을 기술한다(판정값 없음).

**Compute Explanation**(`compute_6f`):
- `PROSPECTIVE_6D`: 6D 함수(`stage6d.compute_verdict`)를 그대로 적용한 값이다. 6D 저장값과 같아야 하며, 다르면 `reproduces_6d = false`로 보고한다.
- 판정:
  - D = 1(X3 분할 정확)이고 V ≥ 0.90이며 PROSPECTIVE가 QUANTITATIVELY_EXPLAINED이면 `PROSPECTIVELY_EXPLAINED`.
  - D = 1이고 그렇지 않으면 `DECOMPOSED_PARTIALLY_PREDICTED`.
  - 그 밖에는 PROSPECTIVE 값(QUANTITATIVELY_EXPLAINED / PARTIALLY_EXPLAINED / QUALITATIVE_SUPPORT_ONLY / NOT_EXPLAINED / INSUFFICIENT_EVIDENCE).

**Runtime Explanation**(`runtime_6f`, NPU_ACTIVE):
- `QUANTITATIVELY_EXPLAINED`: 검증된 전향 NPU_ACTIVE 예측기가 있을 때. 입력에 없으므로 이 단계에서는 주지 않는다. 새 예측식은 적합하지 않는다.
- `SERIAL_DECOMPOSITION_ONLY`: X3 H-P에서 NPU_ACTIVE 그룹 합이 직렬 전체와 허용폭 안일 때(kws·ad). 원본 실행 설명은 아니다.
- `LOWER_BOUND_ONLY`: 모델 MAC_ACTIVE와 NPU_ACTIVE가 있을 때.
  - 설명 가능 하한 = MAC_ACTIVE / NPU_ACTIVE.
  - 단위 하한 = max(MAC, AO, WD ACTIVE) / NPU_ACTIVE.
- `NOT_EXPLAINED`: 그 밖.

**Compiler Fidelity**(`fidelity_6f`):
- `CAUSE_IDENTIFIED`: Vela 비용 항 하나를 바꾼 보드 A/B와 그에 맞춘 Vela 예측이 있을 때. 입력에 없으므로 이 단계에서는 주지 않는다.
- `GROUP_DIRECTION_MEASURED`: X3 그룹별 board/Vela가 있을 때(kws·ad).
- `FAMILY_DIRECTION_ONLY`: 6D 연산군 근거 방향의 OVER + UNDER N_MAC 비중이 ≥ 0.10일 때.
- `NO_EVIDENCE`: 그 밖.

## 5. Vela 비교 (모델, 기술 + 분류)

모델마다 값을 모두 낸다.
- **보드 값**: NPU_ACTIVE(driver_m7)와 range.
- **Vela 값**: `cycles_npu`(= Σ per-layer NPU)와 `cycles_total`(= Σ per-layer Op Cycles)은 모두 inventory에서 계산한다.
  - `cycles_npu`는 whole_model_comparison 값과 같아야 한다. 다르면 중단한다.
- **비율과 오차**:
  - board/cycles_total, board/cycles_npu.
  - 절대 오차 = NPU − cycles_total, 상대 오차 = (NPU − cycles_total) / cycles_total.
- **분류**(공식, cycles_total 기준): ratio < 0.9 OVER, > 1.1 UNDER, 그 밖 AGREE.
  - 경계 b ∈ {0.9, 1.1}에 대해 |NPU − b·cycles_total| ≤ range이면 `INSUFFICIENT_EVIDENCE`다.
  - cycles_npu 기준 분류는 역사 비교값으로만 내고, 두 기준을 섞지 않는다.
- **지배 항**: Op Cycles > NPU cycles인 연산을 메모리 항 지배로 본다. 그 연산들의 Op Cycles 합 / cycles_total을 낸다. 연산군별 cycles_total 비중과 메모리 지배 비중도 낸다.
- **상쇄**: 6D cancellation 값을 그대로 옮긴다.
- **X3 그룹 비율**: X3 값을 옮긴다(kws는 직렬화로 cycles_total에 가까워졌고, ad는 멀어졌다).

## 6. 원본·직렬 NPU_ACTIVE (kws·ad, X3 이미지 f0baf8c, TA profile 1)

비율마다 식과 분모를 함께 낸다.
- Δ = 직렬 − 원본, Δ / 원본.
- 그룹 창 합 S = Σ 그룹 NPU 중앙값. (S − 원본) / S와 (S − 원본) / 원본.
- (S − 직렬) / 직렬(분할 잔차, H-P 허용폭과 함께).
- Unit(MAC·DPU·AO·WD·WD_STALLED)·SRAM rd/wr·EXT rd·AXI(387, 640/642/656/658)의 원본 대 직렬 차이를 낸다.

## 7. 후속 실험 단일 권고 (`recommend`, 고정 표)

기준은 지시 §10의 10개다.
- a: 새 HW 특성
- b: 7개 모델 설명력 기여
- c: Vela 오차 원인 구분
- d: 반복 아님
- e: 독립 변수 통제
- f: FI101에서 측정 가능
- g: X3 재사용
- h: 특정 모델·연산군에 한정되지 않음
- i: 보드 비용 대비 정보
- j: 재적용 가능

| 후보 | 내용 | a | b | c | d | e | f | g | h | i | j | boot | 지시상 제외 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| X_LAT | X3 직렬 그룹별 EXT 읽기 지연(TA EXT RLATENCY) 민감도와 같은 지연의 Vela 예측 | Y | Y | Y | Y | Y | Y | Y | N | Y | Y | 12 | 아니오 |
| X_FIRST | 작은 Cin 첫 Conv 형상(Cin·커널·stride) 독립 측정 | Y | Y | Y | Y | Y | Y | N | N | Y | Y | 6 | 아니오 |
| X_DW | DW stride 2·큰 C·정렬과 Vela 방향(F2 반례) | Y | Y | Y | Y | Y | Y | N | N | Y | Y | 6 | 아니오 |
| G_DF_EXT | 6D 권고(DF1x1 h1uc 외삽 영역) | N | Y | N | N | Y | Y | N | N | N | Y | 9 | 아니오 |
| X3_5M | X3 그룹 계측을 나머지 5개 모델에 | N | Y | Y | N | Y | Y | Y | Y | N | Y | 25 | 아니오 |
| X_BARRIER | 직렬화 증가분(장벽·명령) 분해 | Y | N | N | Y | Y | Y | Y | N | N | N | 4 | 예(§12: X3 확장 금지) |

**선정 규칙**:
- 자격: d·e·f가 Y이고, boot ≤ 12이며, 지시상 제외가 아닌 후보.
- 자격 후보 중 Y 개수가 가장 많은 하나를 고른다. 같으면 boot가 적은 쪽, 그래도 같으면 표 순서로 정한다.
- 이 표는 판단값이며 계약 시점에 고정한다. 실행은 승인 전까지 하지 않는다.

## 8. 검증

- 테스트 `test_stage6f0`: 손으로 쓴 기대값을 쓰고, 모듈에서 기대값을 읽지 않는다.
- mutation 전부 KILLED, `test.sh` ALL PASS.
- 판정 2회 바이트 동일, 기존 결과 파일 sha256 불변. 로컬 커밋만 한다.
