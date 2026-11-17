# Stage 6F-0 결과 — 7개 모델 Compute 재구성, Runtime 설명력, Vela Fidelity 재평가 (보드 없음)

- 계약·판정 동결: `757da42`(`evidence/stage6f0/contract.md`, `host/analysis/stage6f0.py`).
- 판정 2회 바이트 동일. 기존 결과 파일 sha256 불변.
- 산출물: `stage6f0_summary.json`, `operator_levels_6f.csv`.
- 보드·컴파일·펌웨어·TA 변경 없음.

**측정 조건 (값마다 출처)**
- 모델 PMU: driver runner `driver_m7`, **TA profile 1**, pass A·B 측정 RUN 중앙값.
- X3 그룹·원본/직렬: 이미지 `f0baf8c`, **TA profile 1**(EXT RLATENCY 500), placement 0.
- AXI: legacy runner Stage 3, **TA profile 1**. driver 값과 섞지 않는다.
- Vela 5.0.0, `Ethos_U85_SYS_DRAM_Mid_1024`, per-layer는 stage4 inventory.
  - Σ NPU cycles가 7개 모델 모두 whole_model_comparison의 `cycles_npu`와 같다(판정 코드가 확인).
  - kws·ad의 Σ Op Cycles는 Vela summary `cycles_total`과 같다.

## 1. X3 그룹 반영 (`groups`)

| 모델·그룹 | TFLite 연산 | 측정 MAC_ACTIVE | 6D 예측 합 | 예측/측정 | 판정 |
|---|---|---|---|---|---|
| kws G_0 | 0 | 26,090 | 26,090 (F5 대표) | 1.000 | PREDICTION_AGREES (1 %) |
| kws G_V | 2, 4, 6 | 11,700 | 11,700 (h1uc) | 1.000 | PREDICTION_AGREES (5 %) |
| kws G_R | 1, 3, 5, 7, 8, 9, 10, 12 | 18,660 | 13,016.9 (DW 규칙 + DF1x1·DW 외삽) | 0.698 | **EXTRAPOLATION_REFUTED** |
| ad G_0 | 0 | 16,128 | 36,864 (R_PK3 연장, Cin 1→16) | 2.286 | **EXTRAPOLATION_REFUTED** |
| ad G_V | 2, 4, 6, 8 | 60,480 | 60,480 (h1uc) | 1.000 | PREDICTION_AGREES (5 %) |
| ad G_R | 1, 3, 5, 7, 9, 10, 12 | 17,064 | 15,480 (부분 합) | 0.907 | NOT_TESTABLE (op10 = INVALID_OR_UNSTABLE) |

- kws G_R가 새 반례다. 이 그룹에는 6D가 **검증 범위 안**(CLASS_SUPPORTED)으로 분류한 DW 3×3 stride 1 C140·C112 4개가 들어 있다.
  - 그룹 예측은 측정의 70 %다. 다만 DF1x1 외삽(op 8, 10, 12)과 DW stride 2(op 1)가 섞여 있어, 어느 규칙이 틀렸는지는 정하지 않는다(계약 §1).
- ad G_R 부분 합이 0.907로 가까운 것은 판정에 쓰지 않는다. op10 예측이 없어서다.
- 이 값들은 측정을 통한 잔차 분해다. 전향적 예측 성공이 아니다.
- MAC 스케줄 불변성(원본 B0 MAC = 직렬 B1 MAC)은 kws·ad에서만 확인했다.

## 2. 모델별 Compute Coverage와 설명력 (분모: 모델 TFLite N_MAC, 측정 M = driver_m7 MAC_ACTIVE)

| 모델 | c (N_MAC) | 외삽 의존도 | P/M | V (모델 내부 검증) | D (측정 분해) | 6D 판정(재현) | 6F Compute |
|---|---|---|---|---|---|---|---|
| kws | 0.687 | 0.313 | 0.754 | 0.669 | 1.000 | PARTIALLY_EXPLAINED (재현) | DECOMPOSED_PARTIALLY_PREDICTED |
| ad | 0.921 | 0.059 | 0.646 | 0.646 | 1.000 | NOT_EXPLAINED (재현) | DECOMPOSED_PARTIALLY_PREDICTED |
| mobilenet | 0.165 | 0.835 | 0.181 | 0 | 0 | QUALITATIVE_SUPPORT_ONLY (재현) | 같음 |
| vww4 | 0.099 | 0.726 | 0.118 | 0 | 0 | QUALITATIVE_SUPPORT_ONLY (재현) | 같음 |
| rnnoise | 0.318 | 0.304 | 0.197 | 0 | 0 | QUALITATIVE_SUPPORT_ONLY (재현) | 같음 |
| yolo | 0.179 | 0.821 | 0.447 | 0 | 0 | QUALITATIVE_SUPPORT_ONLY (재현) | 같음 |
| wav2letter | 0.678 | 0.322 | 0.678 | 0 | 0 | PARTIALLY_EXPLAINED (재현) | 같음 |

**수준별 N_MAC 비중**:
- kws: DIRECT_IN_MODEL 0.649, CLASS 0.038, EXTRAPOLATED 0.313.
- ad: DIRECT_IN_MODEL 0.921, EXTRAPOLATED 0.031, **REFUTED 0.028**(op0), UNSUPPORTED 0.020.
- mobilenet: DIRECT_ISOLATED 0.139, CLASS 0.026, EXTRAPOLATED 0.835.
- vww4: DIRECT_ISOLATED 0.067, CLASS 0.033, EXTRAPOLATED 0.726, UNSUPPORTED 0.160.
- rnnoise: CLASS 0.318, EXTRAPOLATED 0.304, UNSUPPORTED 0.378(F3 UNSTABLE 포함).
- yolo: CONFIGURATION 0.040, CLASS 0.140, EXTRAPOLATED 0.821.
- wav2letter: CONFIGURATION 0.678, EXTRAPOLATED 0.322.

**P_ext(기술, 판정 미사용)**:
- ad: 6D 정의 112,824 → 6F 75,960(반박된 op0 외삽 제외, 보정 없음).
- 나머지 모델은 6D와 같다.

**6D 대비 변화**:
- N_MAC Coverage c는 7개 모델 모두 6D와 같다. X3는 Coverage를 넓히지 않았다. 대신 근거의 종류를 바꿨다.
  - kws: DIRECT_IN_MODEL 0.649(CONFIGURATION·EXACT → 모델 내부).
  - ad: DIRECT_IN_MODEL 0.921, 반박 0.028.
- kws·ad의 MAC_ACTIVE는 측정으로 완전히 분해된다(D = 1). 전향 예측으로 확인된 비중은 V = 0.669 / 0.646이다.
- 나머지 5개 모델은 모델 내부 검증이 없다. 6D 판정이 그대로다.

## 3. 외삽 규칙의 유효 범위와 반례

| 규칙 | 기존 근거 | 6F-0에서 추가된 것 | 상태 |
|---|---|---|---|
| R_H1UC (DF1x1) | 6B·6-M 독립 측정 | kws G_V, ad G_V 모델 내부 정확 일치 | 모델 내부 적용 지지(kws·ad). DF1x1 외삽 영역(kws op 8, 10, 12 등)은 미검증 |
| R_EXACT F5 (kws op0, Cin 1 10×4) | 6C 단독 | 모델 내부 26,090 정확 일치 | 이 형상에 한해 직접 검증 |
| R_PK3 연장(Cin < 16 → 16 패딩) | 없음(6D 외삽) | ad op0: 예측 36,864 대 측정 16,128 | **반례**: Cin 1 3×3 PartKernel은 16 패딩 처리율이 아니다 |
| R_DW (3×3 s1, C 8–145) | Stage 4, 4C-1, 6C F2 | kws G_R(규칙 범위 안 DW 4개 + 외삽 4개) 예측 0.698 | 그룹 반례. 규칙별 귀속은 불가 |
| R_DW 연장(stride 2, C > 145) | 없음 | ad G_R NOT_TESTABLE | 미검증 |
| R_FC | Stage 4 세 형상 | 없음. F3(rnnoise op46)는 UNSTABLE | 정량 승격하지 않음 |
| PK1x1 / PK1D | 6C F1(18,432)·F4 대표만 | 없음 | 대표 형상만 구성 일치. 1×1·1×32 단일 처리율 일반화 불가 |

- Cin이 작은 첫 Conv는 두 사례가 반대쪽이다.
  - kws F5(10×4, Cin 1)는 대표 측정이 정확히 맞는다.
  - ad op0(3×3, Cin 1)는 패딩 외삽이 2.3배 과대다.
  - 따라서 "Cin 1 → 16 패딩" 규칙을 다른 커널·traversal에 적용할 수 없다.
- Vela 방향 반례 F2(DW C8→C16, Vela ×0.25 대 보드 ×1.73)는 그대로 보존한다. 한 사례로 Vela 비용 모델의 원인을 정하지 않는다.

## 4. Unit 활동 (driver_m7, TA profile 1, 분모 = 모델 NPU_ACTIVE)

| 모델 | NPU_ACTIVE (range) | MAC | DPU | AO | WD | WD_STALLED | SRAM rd/wr beat | EXT rd beat |
|---|---|---|---|---|---|---|---|---|
| kws | 91,824.5 (2,423) | 0.615 | 0.539 | 0.194 | 0.124 | 0.698 | 22,664 / 17,760 | 15,815 |
| ad | 145,949.5 (1,774) | 0.642 | 0.642 | 0.284 | 0.146 | 0.803 | 70,538 / 41,888 | 44,084 |
| mobilenet | 1,450,096 (3,643) | 0.396 | 0.342 | 0.304 | 0.117 | 0.836 | 672,948 / 401,443 | 301,217 |
| vww4 | 234,669 (2,924) | 0.241 | 0.186 | 0.275 | 0.057 | 0.572 | 69,326 / 60,045 | 23,761 |
| rnnoise | 50,508 (2,079) | 0.011 | 0.008 | 0.006 | 0.056 | 0.249 | 143 / 135 | 7,838 |
| yolo | 447,601.5 (2,866) | 0.383 | 0.287 | 0.462 | 0.061 | 0.722 | 236,070 / 188,708 | 29,347 |
| wav2letter | 4,133,297.5 (2,571) | 0.852 | 0.825 | 0.014 | 0.274 | 0.721 | 463,085 / 40,950 | 1,836,882 |

**AXI**(legacy Stage 3, TA profile 1): EXT rd 요청 정체 비율은 6–18 %다. 가장 높은 모델은 wav2letter 0.182와 ad 0.131이다. SRAM rd 요청 정체는 ≤ 0.6 %다.

## 5. Runtime (NPU_ACTIVE) 설명력

| 모델 | 판정 | 설명 가능 하한 MAC/NPU | 단위 하한 max(MAC, AO, WD)/NPU |
|---|---|---|---|
| kws | SERIAL_DECOMPOSITION_ONLY | 0.615 | 0.615 |
| ad | SERIAL_DECOMPOSITION_ONLY | 0.642 | 0.642 |
| mobilenet | LOWER_BOUND_ONLY | 0.396 | 0.396 |
| vww4 | LOWER_BOUND_ONLY | 0.241 | 0.275 |
| rnnoise | LOWER_BOUND_ONLY | 0.011 | 0.056 |
| yolo | LOWER_BOUND_ONLY | 0.383 | 0.462 |
| wav2letter | LOWER_BOUND_ONLY | 0.852 | 0.852 |

- 검증된 전향 NPU_ACTIVE 예측기는 없다. 새 예측식도 적합하지 않았다. 따라서 어느 모델도 QUANTITATIVELY_EXPLAINED가 아니다.
- 단위 하한은 가장 바쁜 단위 하나의 시간이다. 나머지(1 − 하한)는 단위 중첩이 없다고 가정해도 설명되지 않는 시간이다. 범위는 wav2letter 0.15부터 rnnoise 0.94까지다.

**원본 대 직렬** (X3 이미지 f0baf8c, TA profile 1; 식과 분모 명시):

| 항목 | kws | ad |
|---|---|---|
| 원본 O / 직렬 S1 NPU_ACTIVE | 91,444.5 / 105,074.5 | 146,136.5 / 164,292.5 |
| (S1 − O) / O | **+14.91 %** | **+12.42 %** |
| 그룹 창 합 S = G_0 + G_V + G_R | 104,992 | 165,299.5 |
| (S − O) / S | 12.90 % | 11.59 % |
| (S − O) / O | 14.81 % | 13.11 % |
| (S − S1) / S1 (분할 잔차; H-P 허용폭) | −0.08 % (4,069) | +0.61 % (5,075) |
| MAC·DPU 차이 | 0 / 0 | 0 / 0 |
| AO·WD 차이 | −44.5 / −258 | −2 / −923.5 |
| WD_STALLED 차이 | −1,362.5 | +1,903 |
| SRAM rd/wr·EXT rd beat 차이 | 0 / 0 / −1 | 0 / 0 / −1 |
| EXT rd 요청 정체(387) | 19,304.5 → 19,977.5 (+673) | 40,902 → 44,343.5 (+3,441.5) |
| EXT0/EXT1 rd 트랜잭션(640/656) | 754/853 → 822/788 | 1,656/1,663 → 1,646/1,671 |

- X3 보고서의 12.9 %·11.6 %는 그룹 합 S를 분모로 쓴 값이다. 원본 기준으로는 14.8 %·13.1 %다.
- 직렬화는 계산량과 전송량을 바꾸지 않았다. 바뀐 것은 실행시간과 EXT 요청 정체(ad +8.4 %, 분모 원본 정체)다.
  - 이 증가분에는 장벽·명령 처리 비용과 중첩 손실이 섞여 있다. 순수 커널 간 중첩 이득으로 해석하지 않는다.
- **기존 PMU만으로 검증할 수 있는 범위**:
  - 단위별 ACTIVE 시간과 전송 beat·요청·정체 수.
  - 직렬 조건의 그룹 분해.
- **원본 실행의 그룹별 시간과 단위 간 중첩은 PMU 합계로 분리되지 않는다.** 정확한 원본 실행시간 예측기는 현재 자료로 만들 수 없다.

## 6. Vela 비교 (공식 분모 cycles_total; cycles_npu는 역사 비교값)

| 모델 | Board NPU_ACTIVE | cycles_npu | cycles_total | Board/cycles_npu (6D 분류) | Board/cycles_total | 절대 오차 | 상대 오차 | 분류(cycles_total) | 메모리 지배 비중 |
|---|---|---|---|---|---|---|---|---|---|
| kws | 91,824.5 | 86,324 | 102,248 | 1.064 (AGREEMENT) | 0.898 | −10,423.5 | −10.2 % | INSUFFICIENT_EVIDENCE | 0.676 |
| ad | 145,949.5 | 140,277 | 148,328 | 1.040 (AGREEMENT) | 0.984 | −2,378.5 | −1.6 % | AGREE | 0.378 |
| mobilenet | 1,450,096 | 1,737,984 | 2,358,886 | 0.834 (OVER) | 0.615 | −908,790 | −38.5 % | OVER | 0.921 |
| vww4 | 234,669 | 222,478 | 263,411 | 1.055 (AGREEMENT) | 0.891 | −28,742 | −10.9 % | INSUFFICIENT_EVIDENCE | 0.659 |
| rnnoise | 50,508 | 31,334 | 33,040 | 1.612 (UNDER) | 1.529 | +17,468 | +52.9 % | UNDER | 0.313 |
| yolo | 447,601.5 | 478,546 | 584,760 | 0.935 (AGREEMENT) | 0.765 | −137,158.5 | −23.5 % | OVER | 0.582 |
| wav2letter | 4,133,297.5 | 5,233,545 | 5,761,355 | 0.790 (OVER) | 0.717 | −1,628,057.5 | −28.3 % | OVER | 0.110 |

- 절대·상대 오차는 Board − cycles_total이고, 상대 오차의 분모는 cycles_total이다.
- 메모리 지배 비중 = Op Cycles > NPU cycles인 연산의 Op Cycles 합 / cycles_total이다.

**정정의 의미**:
- cycles_total 기준으로 보면 yolo가 AGREEMENT → OVER로 바뀌고, kws·vww4는 경계 안(INSUFFICIENT)이 된다.
- 7개 중 4개가 과대예측(보드가 더 빠름), 1개가 과소예측(rnnoise)이다.
- 6D의 cycles_npu 분류는 바꾸지 않고 역사값으로 둔다.

**어떤 항이 Vela 값을 정하는가**:
- 메모리 항 지배 비중이 큰 모델일수록 과대예측이 크다.
  - mobilenet: 0.921, ratio 0.615.
  - yolo: 0.582, ratio 0.765.
  - wav2letter는 예외다: 0.110, ratio 0.717. PK1D 0.89(메모리 지배 0.11)의 NPU 항 자체가 과대다(6C F4 방향과 같음).
- 이는 관측적 연관이다. Vela DRAM/SRAM 항이 실제 비용을 넘는다는 원인 검증은 아니다.

**연산군**:
- kws: DF1x1 cycles_total 0.44(모두 메모리 지배), DW 0.27(0.90), FIRST_CONV 0.23(NPU 지배).
- ad: DF1x1 0.57(0.10), DW 0.28(0.63), PK3x3(op0) 0.15(1.00).

**X3 그룹(직렬, kws·ad)**: 그룹 오차 방향이 섞여 있다(README X3 §Vela).
- kws G_0는 NPU 항 지배이고 1.336으로 UNDER다.
- kws G_R는 DRAM 항 지배이고 0.861로 OVER다.
- ad G_V·G_R은 UNDER다.
- kws·ad 모델 비율의 일치는 그룹 오차의 상쇄로도 생길 수 있다.
- 직렬화가 Vela 일치도를 일관되게 높인다는 가설은 성립하지 않는다(kws 개선, ad 악화).

**상쇄 가능성**(6D 연산군 방향 근거, N_MAC 비중):
- yolo만 CANCELLATION_POSSIBLE(OVER 0.214, UNDER 0.343)이다.
- 나머지는 NO_CANCELLATION_INDICATED다.

## 7. 모델별 판정 (네 축, 근거 수준과 조건)

| 모델 | Compute Coverage | Compute Explanation | Runtime Explanation | Compiler Fidelity |
|---|---|---|---|---|
| kws | c 0.687, 외삽 0.313 | DECOMPOSED_PARTIALLY_PREDICTED (V 0.669, D 1; X3 직렬) | SERIAL_DECOMPOSITION_ONLY | GROUP_DIRECTION_MEASURED |
| ad | c 0.921, 반박 0.028 | DECOMPOSED_PARTIALLY_PREDICTED (V 0.646, D 1) | SERIAL_DECOMPOSITION_ONLY | GROUP_DIRECTION_MEASURED |
| mobilenet | c 0.165, 외삽 0.835 | QUALITATIVE_SUPPORT_ONLY | LOWER_BOUND_ONLY (0.396) | FAMILY_DIRECTION_ONLY |
| vww4 | c 0.099, 외삽 0.726 | QUALITATIVE_SUPPORT_ONLY | LOWER_BOUND_ONLY (0.275) | FAMILY_DIRECTION_ONLY |
| rnnoise | c 0.318, 미지원 0.378 | QUALITATIVE_SUPPORT_ONLY | LOWER_BOUND_ONLY (0.056) | FAMILY_DIRECTION_ONLY |
| yolo | c 0.179, 외삽 0.821 | QUALITATIVE_SUPPORT_ONLY | LOWER_BOUND_ONLY (0.462) | FAMILY_DIRECTION_ONLY |
| wav2letter | c 0.678, 외삽 0.322 | PARTIALLY_EXPLAINED | LOWER_BOUND_ONLY (0.852) | FAMILY_DIRECTION_ONLY |

**식별한 사례**:
- **Coverage는 그대로인데 근거 수준만 오른 경우**: kws, ad.
- **Compute는 설명했지만 Runtime은 설명하지 못한 경우**: kws, ad.
  - MAC_ACTIVE는 전부 분해되지만 원본 NPU_ACTIVE는 설명되지 않는다.
  - 하한은 0.62 / 0.64다.
- **Vela 오차 방향만 정성적으로 아는 경우**: 나머지 5개 모델.
- **모델 내부 실행 특성이 직접 검증된 경우**: kws G_0·G_V, ad G_V.
- **추가 하드웨어 계측이 필요한 경우**:
  - 7개 모두 Runtime 축에서 필요하다.
  - Compute 축에서는 mobilenet·vww4·yolo(외삽 > 0.7)와 rnnoise(FC 불안정)다.
- `CAUSE_IDENTIFIED`(Vela 항 하나를 바꾼 보드 A/B)는 어느 모델에도 없다.

## 8. 미해결 Hardware/Compiler 공백

1. **원본 실행의 그룹별 시간과 단위 중첩.** PMU 합계로는 분리되지 않는다(kws·ad).
2. **메모리 지연이 NPU_ACTIVE에 주는 몫.** Vela 메모리 항 지배 비중과 과대예측이 함께 커지지만, 원인으로 검증되지 않았다.
3. **처리 규칙**:
   - Cin이 작은 첫 Conv(ad op0 반례).
   - DW stride 2와 C > 145.
   - 모델 내부 DW(kws G_R 0.698).
4. **기타 미분리·미일반화 항목**:
   - FC 불안정(rnnoise).
   - PK1x1·PK1D의 일반 처리율.
   - DF1x1 외삽 영역.
5. **Vela 반대 방향 사례**: F2 DW, rnnoise 과소예측 +52.9 %.

## 9. 후속 단일 실험 권고 — **X_LAT** (고정 표 §7: 자격 후보 X_LAT 9점, X_FIRST 8점, X_DW 8점)

**연구 질문**: 같은 명령 스트림에서 EXT 읽기 지연만 바꾸면, 그룹별 NPU_ACTIVE는 얼마나 변하는가? 그 민감도는 Vela가 그 그룹에서 DRAM 항을 지배 항으로 본 것과 일치하는가?

**필요한 이유**:
- Runtime 공백(§8-1·2)과 Vela 과대예측의 주된 관측 연관(메모리 항 지배)을 직접 겨냥한다.
- 지금 자료로는 계산 시간과 메모리 대기를 나눌 수 없다.

**기존 실험과의 차별점**:
- TA A/B(`evidence/ta_ab/`)는 모델 전체에서 TA 미설정과 profile을 비교했다.
- X3는 지연을 고정했다.
- 여기서는 지연 한 변수를 그룹 단위로 바꾸므로, 그룹마다 지연 민감도를 얻는다.

**통제 변수**:
- 이미지 f0baf8c 계열(TA EXT RLATENCY를 DRWL 헤더로 받는 펌웨어 노브 추가가 필요하다. 승인 대상).
- X3 직렬 스트림 B2–B4(바이트 동일), placement 0, TA SRAM 설정 고정.
- 지연 3단계: 500은 X3 값을 재사용하고, 250과 1000을 새로 잰다. 모든 수치에 지연값을 표기한다.

**주요 지표**:
- NPU_ACTIVE, MAC·DPU·AO·WD·WD_STALLED.
- EXT rd beat·요청 정체(387), EXT0/1 트랜잭션.
- MAC_STALLED_BY_IB(55)와 그룹 창 range.

**Vela 비교**:
- 그룹별 Vela 지배 항(NPU 대 DRAM)을 사전 고정한다.
- 같은 지연을 넣은 시스템 설정 사본으로 per-layer 비용을 다시 계산한다(컴파일만). Vela가 지연 항을 비용에 반영하는지는 preflight에서 먼저 확인한다.
- **사전 가설**:
  - DRAM 지배 그룹(kws G_V·G_R, ad G_0)은 지연에 민감하다.
  - NPU 지배 그룹(kws G_0, ad G_V)은 둔감하다.

**예상 보드 예산**: 2 모델 × 3 그룹 × 2 지연 = **12 boot / 180 RUN**(boot당 3 pass × 5 RUN).

**판정 기준(초안, 계약에서 동결)**:
- 그룹마다 |NPU(1000) − NPU(250)|가 max(5 %, 그룹 창 cap)를 넘으면 `LATENCY_SENSITIVE`, 아니면 `INSENSITIVE`다.
- 가설과 맞은 그룹 비율로 `VELA_TERM_CONSISTENT / INCONSISTENT / INSUFFICIENT_EVIDENCE`를 정한다.
- MAC_ACTIVE가 지연에 따라 변하면 `MEASUREMENT_CONFOUNDED`로 중단한다.

**종료 조건**:
- 12 boot 상한이며, amendment는 최대 1회다.
- 게이트가 실패하면 중단하고 보고한다.
- 결과와 무관하게 7개 모델 재평가로 돌아간다.

**모델 수준 적용 범위**:
- kws·ad 그룹에 한정된다.
- 다른 모델로 넓히려면 모델 전체 지연 민감도(모델당 2 boot)를 별도로 승인받아야 한다.

**보드는 승인 전까지 실행하지 않는다.**

## 10. 검증

- 테스트 `test_stage6f0` 14개, mutation 49/49 KILLED, `test.sh` ALL PASS.
  - 동결 커밋 `757da42` 메시지의 "tests 15"는 잘못 적은 값이다. 실제 테스트는 14개다.
  - `vela over`는 동등 mutation이라 도달 가능한 경계 변경으로 바꿨다(사유는 하네스 주석).
- 판정 2회 바이트 동일, 기존 결과 sha256 불변, 6D 판정 7/7 재현. 로컬 커밋만 했다.
