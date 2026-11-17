# Stage 6D 결과 — 7개 MLEK 모델 Hardware–Compiler 재평가 (보드 없음)

- 계약·판정 동결 `82a398c`(`evidence/stage6d/contract.md`, `host/analysis/stage6d.py`). 결과는 이 커밋 이후에 계산했다.
- 입력은 모두 기존 동결 산출물이다(계약 "입력" 절). 기존 파일은 바꾸지 않았다.
- 판정 2회 실행 결과가 바이트 동일하다(`stage6d_summary.json`, `operator_levels.csv`).
- 측정 조건:
  - 모델 MAC/AO/WD/NPU_ACTIVE: driver runner, **TA profile 1**(`fi101_stage6/whole_model_comparison.csv`).
  - DPU/MAC와 WD_STALLED 비율: legacy runner Stage 1, TA profile 1.
  - AXI: legacy runner Stage 3.
  - 단독 연산(6C): driver runner, TA profile 1, graph IO는 DDR.
  - 조건이 다른 값은 같은 표에 나란히 놓되, 직접 비교하지 않는다.

## 1. 모델별 판정

| 모델 | c (근거 수준 2–4 N_MAC 비중) | P / M (MAC_ACTIVE) | P_ext / M (기술) | Compute 판정 | 6-M 근거 coverage | Runtime |
|---|---|---|---|---|---|---|
| kws | 0.687 | 0.754 | 0.900 | **PARTIALLY_EXPLAINED** | 0.472 | NOT_EXPLAINED |
| ad | 0.921 | 0.646 | 1.204 | **NOT_EXPLAINED** | 0.921 | NOT_EXPLAINED |
| mobilenet | 0.165 | 0.181 | 0.805 | QUALITATIVE_SUPPORT_ONLY | 0.139 | NOT_EXPLAINED |
| vww4 | 0.099 | 0.118 | 0.549 | QUALITATIVE_SUPPORT_ONLY | 0.067 | NOT_EXPLAINED |
| rnnoise | 0.318 | 0.197 | 0.418 | QUALITATIVE_SUPPORT_ONLY | 0.000 | NOT_EXPLAINED |
| yolo | 0.179 | 0.447 | 0.753 | QUALITATIVE_SUPPORT_ONLY | 0.000 | NOT_EXPLAINED |
| wav2letter | 0.678 | 0.678 | 0.847 | **PARTIALLY_EXPLAINED** | 0.000 | NOT_EXPLAINED |

- **QUANTITATIVELY_EXPLAINED는 하나도 없다.**
- **Runtime(NPU_ACTIVE)**: 모델 수준에서 검증된 예측기가 없다. 단독 연산의 graph IO는 DDR이고, 연산 사이 중첩은 측정되지 않았다. 그래서 계약대로 7개 모두 NOT_EXPLAINED다.
- **Coverage와 설명력은 다르다**:
  - ad는 coverage 92 %(DF1x1 EXACT_VALIDATED)인데, 덮은 연산의 예측 합이 측정 MAC_ACTIVE의 64.6 %다.
  - 33,192 사이클(35 %)이 남고, 그래서 NOT_EXPLAINED다. 6-M의 V3 실패와 같은 현상이 그대로 남아 있다.
- **6-M 대비**:
  - 근거 coverage가 늘었다: kws 0.47 → 0.69(F5 첫 Conv, DW 규칙), wav2letter 0 → 0.68(F4), yolo 0 → 0.18, rnnoise 0 → 0.32, mobilenet 0.14 → 0.17, vww4 0.07 → 0.10.
  - 정량 설명으로 올라간 모델은 없다. 6-M 판정 `COVERAGE_EXPANDED_NOT_EXPLAINED`는 그대로이며, 6D에서도 "coverage 증가, 실행시간 미설명"이다.

## 2. 근거 수준별 N_MAC 비중 (연산군/수준)

수준 약어: EV = EXACT_VALIDATED, CM = CONFIGURATION_MATCHED, CS = CLASS_SUPPORTED, EX = EXTRAPOLATED, IU = INVALID_OR_UNSTABLE.

| 모델 | EV | CM | CS | EX | IU | 연산군 분포 |
|---|---|---|---|---|---|---|
| kws | 0.472 | 0.176 | 0.038 | 0.313 | — | DF1x1 EV 0.47 / EX 0.30, FIRST_CONV CM 0.18, DW 0.05 |
| ad | 0.921 | — | — | 0.059 | 0.020 | DF1x1 0.94, DW 0.03, PK3x3 0.03 |
| mobilenet | 0.139 | — | 0.026 | 0.835 | — | DF1x1 EX 0.55, PK1x1 EX 0.21, DW 0.07, PK3x3 0.04 |
| vww4 | 0.067 | — | 0.033 | 0.726 | 0.160 | DF1x1 EX 0.42 / IU 0.16, PK1x1 EX 0.23, DW 0.09 |
| rnnoise | — | — | 0.318 | 0.304 | 0.378 | FC만(op0 CS, op46 IU = F3 UNSTABLE) |
| yolo | — | 0.040 | 0.140 | 0.821 | — | DF1x1 EX 0.43, PK1x1 EX 0.32 / CM 0.02, DW CS 0.14 / CM 0.02 / EX 0.06 |
| wav2letter | — | 0.678 | — | 0.322 | — | PK1D CM 0.68(op17) / EX 0.15, DF1x1 EX 0.17 |

- 연산 개수 기준 비중은 `stage6d_summary.json` `count_share`에 있다(예: rnnoise는 연산의 73 %가 AO/elementwise).
- N_MAC은 TFLite 기준이다. vww4의 1.5 %는 CPU/분할 연산이다.

## 3. MAC/DPU/AO/WD (모델 driver runner TA1; DPU/MAC와 WD_STALLED는 legacy Stage 1)

| 모델 | eff (N_MAC/1024/MAC) | MAC/NPU | AO/NPU | WD/NPU | DPU/MAC (legacy) | WD_STALLED 비율 (legacy) |
|---|---|---|---|---|---|---|
| kws | 0.269 | 0.615 | 0.194 | 0.124 | 0.877 | 0.707 |
| ad | 0.650 | 0.642 | 0.284 | 0.146 | 1.000 | 0.798 |
| mobilenet | 0.511 | 0.396 | 0.304 | 0.117 | 0.864 | 0.836 |
| vww4 | 0.325 | 0.241 | 0.275 | 0.057 | 0.772 | 0.570 |
| rnnoise | 0.155 | 0.011 | 0.006 | 0.056 | 0.781 | 0.223 |
| yolo | 0.221 | 0.383 | 0.462 | 0.061 | 0.749 | 0.721 |
| wav2letter | 0.968 | 0.852 | 0.014 | 0.274 | 0.968 | 0.721 |

**6C와의 연결 (POST_HOC_DESCRIPTIVE, 귀속 아님)**:
- **wav2letter**:
  - 모델 eff 0.968이 F4 단독 0.969와 같다.
  - op17의 단독 MAC_ACTIVE가 모델 MAC_ACTIVE의 67.8 %이고, op17의 N_MAC 비중(67.8 %)과 일치한다. 연산 전반에 효율이 균일하다는 해석과 일관된다.
- **kws**:
  - F5 첫 Conv의 단독 MAC_ACTIVE 26,090은 모델 MAC_ACTIVE의 46 %다. N_MAC 비중은 17.6 %에 그친다.
  - 나머지 연산의 평균은 422 MACs/MAC_ACTIVE다.
  - 낮은 모델 효율(0.269)에 첫 Conv(Cin 1)가 크게 기여한다는 후보다. 모델 안 실행이 단독 실행과 같은 MAC_ACTIVE를 낸다는 가정이 필요하다(CM 수준).
- **yolo**:
  - PK1x1 Cin 4(F1) 효율 4.7 %, DW C8(F2) 6.3 %는 16 올림 낭비다.
  - 그러나 이 두 연산은 N_MAC의 4 %다. 모델 AO/NPU 0.46은 MAC 쪽 근거로 설명되지 않는다(AO-1 미해결).
- **rnnoise**: FC 중심이고 MAC/NPU 0.011이다. Stage 4 FC(1.15 %)·6C F3(1.5 %)와 같은 방향이다. F3가 UNSTABLE이어서 정량 판정은 없다.
- **WD_STALLED**는 비율로만 기술하며, 가중치 공급 대기 시간으로 환산하지 않는다.

## 4. SRAM/EXT·AXI (legacy Stage 3; 관측 평균, 물리 이용률 아님)

| 모델 | SRAM B | EXT B | B/MAC | SRAM rd burst | EXT rd burst | EXT rd 요청 정체 | EXT rd 포트 불균형 |
|---|---|---|---|---|---|---|---|
| kws | 646,784 | 253,056 | 0.058 | 6.79 | 9.83 | 0.099 | 0.027 |
| ad | 1,798,816 | 705,360 | 0.040 | 14.19 | 13.27 | 0.131 | 0.001 |
| mobilenet | 17,190,256 | 5,585,664 | 0.076 | 10.96 | 12.89 | 0.097 | 0.000 |
| vww4 | 2,069,936 | 380,192 | 0.130 | 9.32 | 7.54 | 0.099 | 0.004 |
| rnnoise | 4,448 | 125,984 | 1.500 | 1.44 | 9.80 | 0.116 | 0.009 |
| yolo | 6,796,448 | 477,824 | 0.187 | 10.37 | 7.32 | 0.060 | 0.001 |
| wav2letter | 8,064,560 | 29,694,832 | 0.011 | 13.33 | 15.25 | 0.182 | 0.000 |

- EXT0/EXT1 분배는 모델에서도 거의 1:1이다(6C 단독 연산과 같은 방향).
- EXT read 요청 정체 비율은 6–18 %이고 wav2letter가 가장 높다. 핸드셰이크 정체이며 서비스 대기시간이 아니다.
- 전송량만으로 메모리 병목이라고 판정하지 않는다.
- 단독 연산의 DDR graph IO 전송은 모델 안 SRAM 텐서로 옮기지 않는다.

## 5. Vela fidelity (모델 board NPU_ACTIVE ÷ Vela npu cycles, driver TA1)

| 모델 | board/Vela | 분류 | OVER 근거 연산군 비중 | UNDER 비중 | MIXED 비중 | 상쇄 |
|---|---|---|---|---|---|---|
| kws | 1.064 | AGREEMENT | 0.049 | 0.176 | 0.775 | NO_CANCELLATION_INDICATED |
| ad | 1.040 | AGREEMENT | 0.031 | 0.000 | 0.969 | NO_CANCELLATION_INDICATED |
| mobilenet | 0.834 | OVER | 0.069 | 0.206 | 0.726 | NO_CANCELLATION_INDICATED |
| vww4 | 1.055 | AGREEMENT | 0.088 | 0.232 | 0.666 | NO_CANCELLATION_INDICATED |
| rnnoise | 1.612 | UNDER | 0.000 | 1.000 | 0.000 | NO_CANCELLATION_INDICATED |
| yolo | 0.935 | AGREEMENT | 0.214 | 0.343 | 0.443 | **CANCELLATION_POSSIBLE** |
| wav2letter | 0.790 | OVER | 0.828 | 0.000 | 0.172 | NO_CANCELLATION_INDICATED |

연산군별 근거 방향은 계약 §5에 고정했다: PK1x1 UNDER(F1), DW OVER(F2), PK1D OVER(F4), FIRST_CONV UNDER(F5), FC UNDER(Stage 4), DF1x1·PK3x3 MIXED.

- **방향이 일치하는 모델 (기술)**:
  - wav2letter: 모델 OVER와 PK1D OVER(F4 0.58).
  - rnnoise: 모델 UNDER와 FC UNDER.
- **yolo**: 모델 0.935는 일치 범위다. 그러나 OVER(DW) 21 %와 UNDER(PK1x1) 34 %가 함께 있어, 상쇄로 일치처럼 보일 가능성이 있다(후보).
- **mobilenet**: 모델은 OVER인데 연산군 근거는 UNDER가 더 크다. MIXED인 DF1x1(73 %)이 지배하므로 연산군 근거로 설명되지 않는다.
- **해석의 한계**:
  - 연산별 오차를 모델 오차로 귀속하지 않고, 보정 계수를 만들지 않는다.
  - Vela npu cycles는 연산별 max(npu, SRAM, DRAM)의 합이다. 보드 NPU_ACTIVE는 중첩을 포함한 벽시계 활성이다. 같은 개념이 아니며, 그래서 비율은 기술로만 쓴다.
- **F2 반례(C8→16: Vela ×0.25, 보드 ×1.73)**:
  - Compiler Fidelity의 주요 반례로 보존한다.
  - 모델 안 DW 중 F2와 같은 구성(3×3, C ≤ 16, stride 1)은 yolo op3·op6과 vww4 op8(C 14) 세 개다. 7개 모델 N_MAC 비중의 최댓값은 DW 전체가 yolo 0.21이고, EX 수준은 최대 0.057이다.

## 6. 연구 공백과 단일 권고 (계약 §6 고정 규칙)

| 공백 | impact (EX/US/IU 비중 최대) | controllable | discriminating | cost | 적격 |
|---|---|---|---|---|---|
| G_PK1X1 | 0.320 (yolo) | 예 | 예 | 6 | 예 |
| **G_DF_EXT** | **0.583 (vww4)** | 예 | 예 | 9 | **예 → 권고** |
| G_FC | 0.682 (rnnoise) | 예 | 아니오 | 4 | 아니오 |
| G_DW_VELA | 0.057 | 예 | 예 | 6 | 예 |
| G_PK1D | 0.150 | 예 | 예 | 3 | 예 |
| G_FIRST | 0.036 | 예 | 예 | 4 | 예 |
| G_AO1 / G_WD | 0 (MAC 비중 정의 불가) | 예 | 예 | 4 | 예 |

**권고: G_DF_EXT** — 1×1 DepthFirst의 H1-UC 외삽 영역(vww4·mobilenet·yolo 큰 형상)을 실제 모델 구성으로 측정한다.
- **왜**: DF1x1은 vww4 58 %, mobilenet 55 %, yolo 43 %의 N_MAC이 외삽 또는 불안정 상태다. 단일 공백 중 영향이 가장 크다.
- **기존과의 차이**: E1-R·6-M은 kws·ad 형상 영역에서만 h1uc를 검증했다. 외삽 영역에는 검증 영역보다 큰 OFM 공간(최대 3,136 대 256)과 채널(Cin·Cout 최대 2,000 대 Cin 276·Cout 960)이 있다. spatial stripe는 78개 중 1개뿐이다.
- **구분할 가설**: h1uc 식이 외삽 영역에서도 MAC_ACTIVE를 맞히는지(±5 %), 아니면 영역 밖에서 무너지는지.
- **연구 축**: Compute/Unit(주), Vela fidelity(DF1x1 MIXED 방향 해소).
- **종료 조건**: 승인된 boot 안에서 외삽 형상의 판정이 나오면 종료한다. 추가 확장은 없다.
- **복귀**: 결과를 6D 판정 규칙에 넣어 모델별 c와 P/M을 다시 계산한 뒤 전체 공백 평가로 돌아간다.
- **위험(사전 기록)**:
  - ad는 DF1x1이 EXACT_VALIDATED인데도 P/M이 0.646이다. 따라서 G_DF_EXT가 coverage를 올려도 모델 MAC_ACTIVE 설명은 오르지 않을 수 있다.
  - 이 실험은 "연산 단위 h1uc가 맞는가"를 답하고, "모델 MAC_ACTIVE가 연산 합보다 큰 이유"(ad 35 % 잔여)는 답하지 않는다.
- 실행은 승인 전까지 하지 않는다.

## 7. 검증된 결론과 미해결

**검증됨**:
- 7개 모델 중 정량 설명(QUANTITATIVELY_EXPLAINED)은 0이다.
- kws·wav2letter는 PARTIALLY_EXPLAINED, ad는 coverage가 충분한데도 NOT_EXPLAINED, 나머지 4개는 QUALITATIVE_SUPPORT_ONLY다.
- Runtime은 전부 NOT_EXPLAINED다.

**미해결**:
- ad 잔여 35 %(연산 합 대 모델 MAC_ACTIVE)
- AO-1(yolo AO/NPU 0.46)
- WD-1/2
- F1 처리율 192 대 384와 OFM write 1.67배
- F2 Vela 방향 반대
- F3 FC 불안정
- 모델 NPU_ACTIVE 예측기 부재

## 8. 테스트·무결성

- `test_stage6d` 21개, mutation 57/57 KILLED(살아남은 3개에는 fixture를 추가했고 mutation은 그대로 뒀다).
- `test.sh` ALL PASS.
- 판정 2회 바이트 동일.
- 기존 결과 파일 불변.
