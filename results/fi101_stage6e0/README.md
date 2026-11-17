# Stage 6E-0 결과 — 모델 수준 실행 비용 귀속과 Compiler Fidelity의 정적 식별 가능성 (보드 없음)

## 1. 커밋

- 계약·판정 동결 `034ef0e`(`evidence/stage6e0/contract.md`, `host/analysis/stage6e0.py`). 결과는 그 뒤에 계산했다.
- 판정 2회 실행 결과가 바이트 동일하다(`stage6e0_summary.json`, `model_differences.csv`, `ad_operators.csv`).

## 2. 데이터 범위

- 6D 산출물(연산 수준·예측), 6-M 연산표(Vela 연산별 op/MAC cycles).
- driver runner 모델 측정(**TA profile 1**). legacy Stage 1(DPU/MAC, WD_STALLED)과 Stage 3(AXI)도 TA1이지만 runner가 달라, 출처 열로 표시했다.
- 계측 근거: 2B-0b, 2B-2, 2B-3(정적 분석, 3a pilot, 3b 설계·owner 검토), QREAD pilot 두 건.
- 신규 측정·컴파일·펌웨어 변경은 없다.

## 3. 모델별 세 차이 (모델 수치 driver TA1)

| 모델 | Compute residual R_c = M − P_v (÷M) | R_c,all (외삽 포함, 기술) | 예측 있는 N_MAC | Execution residual | Vela error E_v = NPU − Vela (board/Vela) | Compute Attribution |
|---|---|---|---|---|---|---|
| kws | 13,879 (0.246) | 5,643 | 1.00 | NOT_COMPUTED | +5,500 (1.064) | PARTIALLY_EXPLAINED |
| ad | 33,192 (0.354) | −19,152 | 0.98 | NOT_COMPUTED | +5,672 (1.040) | PARTIALLY_EXPLAINED |
| mobilenet | 470,803 (0.819) | 112,064 | 0.79 | NOT_COMPUTED | −287,888 (0.834) | NOT_IDENTIFIABLE |
| vww4 | 49,852 (0.882) | 25,488 | 0.59 | NOT_COMPUTED | +12,191 (1.055) | NOT_IDENTIFIABLE |
| rnnoise | 440 (0.803) | 319 | 0.62 | NOT_COMPUTED | +19,174 (1.612) | NOT_IDENTIFIABLE |
| yolo | 94,824 (0.553) | 42,376 | 0.68 | NOT_COMPUTED | −30,944 (0.935) | NOT_IDENTIFIABLE |
| wav2letter | 1,134,858 (0.322) | 538,122 | 0.85 | NOT_COMPUTED | −1,100,248 (0.790) | PARTIALLY_EXPLAINED |

- 세 지표는 서로 다른 개념이다.
  - R_c는 MAC_ACTIVE 축이고, E_v는 NPU_ACTIVE 축이다.
  - Execution residual은 유효한 모델 수준 실행시간 예측기가 없어 계산하지 않았다.
- Unit·AXI 비율은 `model_differences.csv`에 있다(6D §3·§4와 같은 값).

## 4. ad 잔여 MAC_ACTIVE (기술, 귀속 아님)

| op | 연산군 | 수준 | N_MAC | 예측 | Vela op / MAC cycles |
|---|---|---|---|---|---|
| 0 | PK3x3 Cin 1, 32²×192 | EXTRAPOLATED | 1,769,472 | P_ext 36,864(R_PK3 연장, Cin 1→16 패딩) | 21,874 / 9,841 |
| 1, 7, 9 | DW stride 2 | EXTRAPOLATED | 641,088 | P_ext 5,076 | — |
| 3, 5 | DW C 276 | EXTRAPOLATED | 1,271,808 | P_ext 10,368 | — |
| 2, 4, 6, 8 | DF1x1 | EXACT_VALIDATED | 57,443,328 | P 60,480(h1uc) | 71,857 / 71,289 |
| 10 | DF1x1 4×4 | INVALID_OR_UNSTABLE | 1,218,816 | 없음 | 11,150 / 11,150 |
| 12 | DF1x1 Cout 8 | EXTRAPOLATED | 2,208 | 36 | — |

- **잔차 범위**: 검증된 연산 밖 후보(0, 1, 3, 5, 7, 9, 10, 12)는 N_MAC의 8 %다. 이 후보의 외삽 예측 합 52,344가 잔차 33,192보다 크므로 잔차는 "범위 안"이다(PARTIALLY_EXPLAINED).
- **op0만으로도 잔차에 가깝다**: op0(Cin 1 첫 Conv)의 P_ext 36,864는 Cin을 16으로 채운다는 가정이다. 그런데 kws F5(Cin 1, 10×4)는 그 가정의 0.61배(26,090 대 42,875)로 측정됐다. 따라서 Cin 1 연산의 PartKernel 처리는 단순 16 패딩이 아니다. op0의 실제 값은 미정이다.
- **연산 단위로는 식별할 수 없다**: 2B-2 그룹 창은 ad에서 CONV 효율 2.845(불가능)를 냈다. 기존 계측으로는 잔차가 어느 연산 것인지 정할 수 없다.

## 5. Stage 2B 귀속 실패와 현재 계측 한계

- **원인**(2B-3 정적 분석, TRM 인용):
  - 커널 명령은 비차단이고(발행 후 완료를 기다리지 않음, 남은 커널 최대 2개), 연속 커널 사이에 장벽이 없다(BLOCKDEP > 0 경계: kws·ad 12/13, mobilenet 160/207).
  - PMU_MASK는 명령 처리기가 그 위치에 도착한 시점에 적용된다.
  - 그래서 창은 "연산 i의 실행"이 아니라 "앞 연산들의 완료 사이"를 잰다.
- **기존 계측 목록**: 연산별 시간 귀속을 낸 것은 0/5다.

| 계측 | 결과 |
|---|---|
| PMU_MASK | 무교란, 가산성 3/7 |
| 2B-2 창 | 귀속 오류 |
| 3a pilot | 진단 라벨만 |
| QREAD | TRACE_INVALID / NOT_ASSOCIATED(분해능) |
| PMCLUT | 모델 전체 비율만 |

- **재발 방지 조건**:
  - 창 경계를 명령 위치가 아니라 완료 보장 지점에 둔다(KERNEL_WAIT n=0).
  - 합계 보존(Σ창 = 전체)을 귀속 정확성의 증거로 쓰지 않는다.
  - 독립 기준값(단독 측정)으로 창 값을 검증한다.

## 6. 실제 모델의 실행 구조

| 항목 | 정적 사실 |
|---|---|
| **명령 실행** | Vela 명령 스트림(stream 연산 kws·ad 14, rnnoise 48, wav2letter 39, vww4 85, yolo 112, mobilenet 208). 순서는 BLOCKDEP로 정해진다. KERNEL_WAIT는 DMA 앞에서만 나온다(vww4 4, yolo 11, mobilenet 11, 나머지 0). 완료 경계는 STOP(스트림 끝)뿐이다 |
| **동기화 지점** | DMA_WAIT·KERNEL_WAIT·BLOCKDEP 0 경계. 대부분의 경계는 겹칠 수 있다 |
| **Compute** | MAC·DPU·AO·WD 카운터는 NPU 전체 단위다. 연산 구분은 PMU_MASK 창뿐이다. PMCLUT 결과 MAC∧AO 동시 활동은 kws 0.66, ad 0.85, wav2letter 0.90, rnnoise 0.01이다 |
| **Memory·AXI** | 가중치는 DMA로 선반입된다(다음 연산과 겹침). 포트별 카운터(EXT0/1, SRAM0/1)는 전체 창 단위다 |
| **Instrumentation** | PMU 카운터를 더 모아도 창이 실행과 맞지 않으면 연산별 귀속은 안 된다. 추가 계측 없이 가능한 것은 모델 전체 비율과 정적 분석까지다 |

## 7. Unit/AXI 활동의 시간적 귀속 가능성

- **현재**: 모델 전체 비율만 유효하다.
- **연산·그룹 단위로 가능해지는 조건**: 연산 경계에 완료 장벽을 넣는다(직렬화). 이것은 실행을 바꾼다. 그래서 직렬 값은 원래 실행의 연산별 지연이 아니라 "직렬 조건의 연산 비용"이다(owner 3b 검토와 같음).
- **원래 실행과의 차이**: NPU_ACTIVE(직렬) − NPU_ACTIVE(원래)가 모델의 겹침 이득이다. 이것이 측정 대상이다.
- **MAC_ACTIVE의 성격**: MAC_ACTIVE가 스케줄 불변이라면 직렬 창 값을 원래 실행에도 쓸 수 있다. 다만 이것은 가설이며, 보드에서 판정해야 한다.

## 8. Vela 비용 모델의 미해결 원인

| 모델 | Σ Vela op cycles | Σ MAC cycles | "MAC 아닌 항이 최대"인 op cycles 비중 | board/Vela |
|---|---|---|---|---|
| kws | 102,248 | 69,011 | 1.00 | 1.064 |
| ad | 148,328 | 123,031 | 0.39 | 1.040 |
| mobilenet | 2,342,411 | 1,269,030 | 0.96 | 0.834 |
| vww4 | 222,002 | 151,038 | 0.73 | 1.055 |
| rnnoise | 32,641 | 28,843 | 0.39 | 1.612 |
| yolo | 579,877 | 362,346 | 0.84 | 0.935 |
| wav2letter | 5,750,003 | 5,158,420 | 1.00 | 0.790 |

- **연산별 합 대 모델 값**:
  - Vela 모델 npu cycles는 연산별 max(항)의 합이며, 중첩 없는 실행을 가정한다.
  - 연산별 Σ op cycles(6-M 매핑의 NPU MAC 연산 기준)는 Vela 모델 값과 다르다(예: kws 102,248 대 86,324). 매핑 범위 차이이며, 해석하지 않았다.
- **검증 가능한 원인**:
  - 보드의 실제 실행은 중첩을 포함한다. 중첩이 없는 직렬 실행을 측정하면 Vela의 합산 가정과 같은 조건이 된다.
  - 그때 남는 차이는 연산별 비용 항의 오차다. 원래 실행과의 차이는 중첩 효과다.
  - 이 둘을 분리하는 것이 검증 가능한 메커니즘이다(TESTABLE_MECHANISM_IDENTIFIED).
- **F2 반례**(C8→16 Vela ×0.25, 보드 ×1.73)는 보존한다. 이번 설계는 F2 전용이 아니다.

## 9. 기존 Characterization의 적용 범위

- 근거 수준 2–4(6D)는 kws 0.69, ad 0.92, wav2letter 0.68이다. 나머지 4개는 0.10–0.32다.
- 넓히는 것(X1 G_DF_EXT)은 coverage를 올리지만 c1(모델 수준 비용)과 c8(모델 조건)을 만족하지 못한다.
- ad는 coverage 0.92에서도 잔차 35 %가 남는다. 따라서 **현재 장애물은 coverage보다 "연산 비용 → 모델 비용" 연결의 부재**다. 적용 범위 확장은 연결이 검증된 뒤에 의미가 커진다.

## 10. 후속 실험의 식별력 (계약 §5 고정 평가)

| 후보 | 충족 기준 | 불충족 | Vela 조건 일치 | boot |
|---|---|---|---|---|
| X1 G_DF_EXT | 8/10 | c1 모델 수준 아님, c8 graph IO DDR | 아니오 | 9 |
| X2 PREFIX_STOP | 9/10 | c8 꼬리 스케줄 변경, 출력 검증 불가 | 아니오 | 10 |
| **X3 SERIAL_MASK** | **10/10** | — | **예** | **10** |
| X4 QREAD_FINE | 6/10 | c3, c4, c6, c7 | 아니오 | 4 |
| X5 AD_REST_ISOLATED | 8/10 | c1 ad 한정, c8, c9 | 아니오 | 4 |

## 11. 단일 권고 — Stage 6E: 직렬화 + 그룹 PMU_MASK (X3), 보드 예산 10 boot

**설계 (승인 전 실행 안 함)**

- **모델과 역할**:
  - kws는 방법 검증용이다. 독립 기준값이 둘 있다: op0 단독 6C F5 MAC_ACTIVE 26,090, 그리고 DF1x1 EXACT 연산 2·4·6의 h1uc 합 11,700.
  - ad는 잔차 진단용이다.
- **조건(모델마다 5 boot)**:

| boot | 조건 |
|---|---|
| B0 | 원래 스트림(driver_m7과 같은 DRWL, 재현 대조) |
| B1 | 모든 커널 연산 앞에 KERNEL_WAIT n=0(직렬화), 마스크 없음 |
| B2 | 직렬 + 마스크 G_V(DF1x1 EXACT: kws 2·4·6, ad 2·4·6·8) |
| B3 | 직렬 + 마스크 G_0(op0, kws는 stream 연산 2개) |
| B4 | 직렬 + 마스크 G_R(나머지) |

  - 창은 "KERNEL_WAIT(0) → PMU_MASK(1) → 그룹 연산 → KERNEL_WAIT(0) → PMU_MASK(0)"이다.
- **측정 조건**: **TA profile 1**, driver runner 이미지 `14077be`, placement 0, Pass A·B·C, boot당 3 set × 5 RUN(1 warm-up + 4) → 150 RUN(측정 120).
- **사전 확인**: 첫 boot(kws B1)에서 출력 = golden, 스트림 완료, 마스크 동작을 확인한다. 실패하면 멈추고 복원한다.
- **경쟁 가설과 예측 (판정 기준은 계약 시 동결)**:

| 가설 | 예측 관측 | 반대 결과의 의미 |
|---|---|---|
| H-S MAC_ACTIVE 스케줄 불변 | MAC(B1) = MAC(B0) ±1 % | 스케줄 의존 → 직렬 창 값을 원래 실행에 쓰지 않음 |
| H-P 창 분할 정확 | MAC(G_V)+MAC(G_0)+MAC(G_R) = MAC(B1) ±1 % | 창 누설 |
| H-K 방법 검증(kws) | MAC(G_0) = 26,090 ±1 %, MAC(G_V) = 11,700 ±5 % | 모델 안 ≠ 단독(문맥 비용) |
| H-A1 ad 잔차는 미검증 연산 | MAC(G_V) = 60,480 ±5 %, MAC(G_0)+MAC(G_R) ≈ 33,192 | — |
| H-A2 ad 잔차는 검증 연산의 문맥 비용 | MAC(G_V) > 1.05 × 60,480 | — |
| H-O 겹침 이득 | NPU(B1) − NPU(B0) > max(1 %, range 합) | 겹침 이득 없음 |
| H-V Vela 합산 가정 | 그룹별 직렬 NPU_ACTIVE 대 Σ Vela op cycles. 직렬 전체 대 Vela 모델 값의 차이와 원래 실행의 차이를 분리 | — |

- **구현** (계약 §5 상태):
  - 있음: cms 삽입·PMU_MASK, COP1 추출, DRWL, 펌웨어 무변경.
  - 새로 만들되 범위가 정해짐: KERNEL_WAIT 인코딩, COP1 교체 후 tflite 재직렬화, 판정 코드.
  - 보드 사전 확인: driver runner에서 PMU_MASK·KERNEL_WAIT(0).
- **이 설계가 답하는 다섯 가지**:
  - 왜 필요한가: 연산 비용과 모델 비용의 연결이 7개 모델 모두 없다. ad 잔차와 Vela 오차의 출처(연산 비용 대 겹침)를 기존 자료로 가를 수 없다.
  - 무엇이 다른가: 2B 창(명령 위치)과 달리 완료 장벽으로 창을 닫는다. 단독 연산(graph IO DDR)과 달리 모델의 텐서 배치·가중치·명령 순서를 유지한다.
  - 새로 규명하는 HW 특성: MAC_ACTIVE의 스케줄 불변성, 모델의 겹침 이득, Cin 1 첫 Conv의 모델 안 비용.
  - Vela에 더하는 근거: 합산 가정(중첩 없음)과 같은 조건의 보드 값이다. 연산 비용 항의 오차와 중첩 효과를 분리한다.
  - 모델 설명력 연결: 6D 규칙에 그룹 측정값을 넣어 kws·ad의 c와 P/M을 다시 계산한다.
- **종료와 복귀**:
  - 10 boot 뒤 판정하고 자동 확장은 하지 않는다.
  - H-K가 실패하면 방법이 무효이므로 다른 모델로 넓히지 않는다.
  - 성공하면 다른 모델 적용은 모델별로 따로 승인받는다.
  - 결과는 6D 표와 공백 평가로 돌아가며, G_DF_EXT는 그때 재평가한다.

## 12. 결정 로그

`docs/plan/research_direction_and_decision_log.md`에 6D 수용, G_DF_EXT 보류(보존), 6E-0 승인, 6E-0 결과를 누적했다.

## 13. 테스트·Mutation·불변성

- `test_stage6e0` 11개, mutation 39/39 KILLED, `test.sh` ALL PASS.
- 판정 2회 바이트 동일, 기존 결과 파일 불변.

## 14. 최종 판정

| 항목 | 판정 |
|---|---|
| Compute Attribution | kws·ad·wav2letter **PARTIALLY_EXPLAINED**, mobilenet·vww4·rnnoise·yolo **NOT_IDENTIFIABLE** (EXPLAINED_WITH_EXISTING_DATA 0) |
| Execution Cost | **REQUIRES_CONTROLLED_EXPERIMENT** |
| Vela Fidelity | **TESTABLE_MECHANISM_IDENTIFIED** |
| Next Experiment | **READY_FOR_BOARD_REVIEW** (X3, 10 boot) |

- Execution Cost·Vela·Next Experiment 판정은 계약에 고정한 설계 평가(§5)를 기계적으로 따른 것이다. 데이터에서 나온 판정이 아니다.
