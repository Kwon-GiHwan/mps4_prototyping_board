# Stage 6-M — Model-level MAC Explainability Reassessment (보드 없음)

- 계약 `evidence/stage6m/contract.md`, 판정 코드, 테스트 21개, mutation 69/69 KILLED를 `387ab60`에서 동결했다. 원본 kernel 추출과 모든 결과 계산은 그 뒤에 했다.
- 보드 측정, 새 형상 생성, Vela 옵션 변경, E2·E3·Stage 6C는 하지 않았다. H1-UC 식은 바꾸지 않았다.
- 원본 7개 모델은 MLEK Vela 옵션 그대로 컨테이너에서 재컴파일해 kernel 레지스터를 읽었다(`evidence/stage6m/facts/kernels.json`, sha256 `6fb0f307…`, 두 번 추출해 같음).
  - 7개 모두 Vela 출력·command stream·원본 tflite sha256이 driver_m7 측정 DRWL 기록과 같다(V1).
- 모델 수준 관측은 driver_m7이다: boot 308–316, **TA profile 1**, 이미지 `65cf963`.
  - 형상 근거는 6B-B(boot 410–420)와 E1-R(boot 428–434)이며, 둘 다 **TA profile 1**, 이미지 `70090f1`이다.
  - 이미지가 다르다는 점은 조건 차이로 기록한다.
- MAC 비중은 모두 **원본 TFLite N_MAC** 기준이다. 기존 Stage 6·6B-B 수치(Vela `mac_count` 기준)는 비교 열로만 둔다.

## 판정

| 항목 | 결과 |
|---|---|
| H1-UC 단일 연산 판정 | **PROSPECTIVE_SUPPORT** (E1-R, 변경 없음) |
| 모델 수준 설명력 | **COVERAGE_EXPANDED_NOT_EXPLAINED** |
| V1 무결성 | 성립 (7/7) |
| V2 경계 R(S_AB) ≥ 0 | 성립 (위반 모델 0) |
| V3 KWS·AD Evidence-supported ≥ 0.50 | **실패**: KWS 0.472, AD 0.921 |
| V4 방향 (eff_set, eff_meas 모두 AD > KWS) | 성립 |
| V5 E(S_AB) ≥ 0.10 (KWS·AD 중 하나 이상) | 성립 (KWS 0.110, AD 0.134) |

- 실패는 V3 하나다. KWS에서 보드로 측정한 구성(G25)이 덮는 MAC이 TFLite 기준 47.2 %다.
  - 같은 연산을 6B-B처럼 Vela `mac_count` 기준으로 세면 51.7 %지만, 계약대로 TFLite 기준만 판정에 썼다.
  - 기준선 근처라는 점을 함께 적는다. 규칙은 바꾸지 않았다.
- 그래서 판정은 "적용 가능한 MAC 비중은 늘었지만, 모델 수준 효율 차이를 H1-UC로 설명했다고 말할 근거는 기준에 못 미친다"이다.

## 1. 범주 (대상 = Stage 6B와 같은 1×1 DepthFirst Conv 93개)

| 범주 | 연산 수 | 내용 |
|---|---:|---|
| A BOARD_MEASURED | 15 | kws 3 (G25), ad 4 (G11, G12×2, G52), mobilenet 7 (G09×4, G40×3), vww4 1 (G57) |
| B VALIDATED_DOMAIN_PREDICTION | **0** | E1-R 범위에 드는 원본 연산이 없다 |
| C EXTRAPOLATED_PREDICTION | 78 | 추정값으로만 쓴다 |
| D NOT_APPLICABLE (대상 중) | 0 | 93개 모두 kernel 매핑과 H1-UC 계산이 가능했다 |

- **A는 실행 구성 전체가 같아야 한다.** kernel OFM 크기, ublock, block, Cin 조각 비용, 메모리, stride, 활성화가 모두 같아야 하고 LUT fused가 아니어야 한다.
  - 예: kws op 8(25×5, Cin 140→112)은 G25와 Cin이 같고 효율도 같지만, 실행 구성이 달라 C다.
- **B가 0인 이유**: E1-R 범위는 Dram→Dram, OFM 29–37, Cin 100–200, Cout 96–176이다.
  - 원본 대상은 대부분 Sram 배치이고, 공간 크기가 작다.
  - C 78개 중 77개는 메모리 차원이 범위 밖이다. 나머지 1개(mobilenet op 8, 56×56, Dram/Dram)는 공간과 Cout이 범위 밖이다.
  - E1-R 범위는 원본 모델의 MAC을 직접 덮지 못한다. MAC_ACTIVE가 메모리 경로와 무관하다는 가정은 검증된 사실이 아니라서 범주를 올리는 근거로 쓰지 않았다.
- 실행 조건의 차이(기록만 함):
  - G14(wav2letter op 19)는 LEAKY_RELU LUT가 fused돼 있어 C다.
  - mobilenet op 5는 cascade 5이고 kernel 19개(공간 stripe)로 실행된다.
  - 6B-B UNSTABLE 형상에 맞는 연산 5개(ad op 10 = G28, vww4 op 28·33 = G53, op 46·50 = G56)는 C로 두고 따로 표시했다.
  - 대상 93개 모두 kernel의 OFM 합이 원본 OFM과 같고, TFLite N_MAC = OFM×Cin이다. 다중 kernel 연산의 N_MAC은 한 번만 셌다.

## 2. 모델별 지표 (`model_metrics.csv`, `coverage_comparison.csv`)

| 모델 | N_MAC (TFLite) | 1×1 DF = Static | Evidence (A∪B) = Direct (A) | eff_set A∪B | eff_set A∪B∪C | 관측 eff_meas | MAC_ACTIVE | R(S_AB) | E(A∪B) | E(A∪B∪C) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ad | 62,346,720 | 0.941 | 0.921 | 0.928 | 0.927 | 0.650 | 93,672 | 28,404 | 0.134 | 0.138 |
| kws | 15,556,352 | 0.775 | **0.472** | 0.613 | 0.631 | 0.269 | 56,450 | 36,736 | 0.110 | 0.167 |
| mobilenet_v2 | 300,775,552 | 0.690 | 0.139 | 0.928 | 0.898 | 0.511 | 574,795 | 277,919 | 0.011 | 0.082 |
| vww4 | 18,828,800 | 0.650 | 0.067 | 0.708 | 0.807 | 0.325 | 56,512 | 37,620 | 0.013 | 0.075 |
| yolo-fastest | 38,916,000 | 0.426 | 0 | — | 0.834 | 0.221 | 171,576 | 133,572 | — | 0.024 |
| wav2letter | 3,491,098,000 | 0.172 | 0 | — | 0.983 | 0.968 | 3,521,802 | 112,527 | — | 0.091 |
| rnnoise | 86,952 | 0 | 0 | — | — | 0.155 | 548 | 463 | — | — |

- MAC_ACTIVE와 관측 효율은 driver_m7 값이다(TA profile 1). eff_meas = N_MAC/(1024 × MAC_ACTIVE)로, Stage 1 구 runner 값(kws 26.9 %, ad 65.0 %)과 같다.
- **eff_set은 정적 계산 비용 모델**이다. 모델 PMU 효율과 같은 것이 아니며, 독립 연산의 합으로 모델 MAC_ACTIVE를 복원했다고 주장하지 않는다.
- R(S_AB) > 0은 필요조건을 만족한다는 뜻일 뿐이다. S_AB가 빈 모델에서는 모든 MAC 연산에 하한 N/1024만 쓴 값이다.
- E(S) = Σ_S(H1-UC − N/1024) ÷ (MAC_ACTIVE − N/1024): 관측 MAC_ACTIVE의 초과분 가운데 S의 H1-UC 패딩 손실이 차지할 수 있는 몫이다. H1-UC가 모델 안에서도 성립한다는 조건부 값이다.

### Coverage 비교 (연산은 한 번만 셈)

| 모델 | Static Structural (TFLite) | Evidence-supported (TFLite) | Direct Model-shape (TFLite) | 6B-B Validly Measured (Vela) | Stage 6 MAC calibrated (Vela) | Model-level Explanation |
|---|---:|---:|---:|---:|---:|---|
| ad | 0.941 | 0.921 | 0.921 | 0.935 | 0 | E = 0.134 (조건부) |
| kws | 0.775 | 0.472 | 0.472 | 0.517 | 0 | E = 0.110 (조건부) |
| mobilenet_v2 | 0.690 | 0.139 | 0.139 | 0.139 | 0.219 | E = 0.011 |
| vww4 | 0.650 | 0.067 | 0.067 | 0.067 | 0.196 | E = 0.013 |
| yolo-fastest | 0.426 | 0 | 0 | 0 | 0.220 | — |
| wav2letter | 0.172 | 0 | 0 | 0 | 0 | — |
| rnnoise | 0 | 0 | 0 | 0 | 0 | — |

- 6B-B의 93.5 %·51.7 %는 Vela `mac_count` 기준이었다. TFLite 기준으로 다시 세면 92.1 %·47.2 %다.
  - kws 차이의 원인은 분모다. TFLite N_MAC 합이 15.56 M로, Vela의 14.21 M보다 크다.
- Stage 6 MAC calibrated coverage는 주로 **1×1 PartKernel**(Stage 4 측정 계열)이었다. H1-UC의 1×1 DepthFirst와 겹치지 않으며, 두 수치를 더하지 않는다(서로 다른 비용 모델).
- E1-R 합성 형상 6개는 Direct 지표에 넣지 않았다. B로도 원본 연산을 덮지 못했다.
- 위 세 coverage가 높아도 Model-level Explanation이 높아지지는 않는다. ad는 Direct 0.921이지만 E는 0.134다.

## 3. Stage 1 현상과의 비교

### KWS와 AD

- 관측: MAC 활성 비율은 비슷하다(MAC_ACTIVE/NPU_ACTIVE kws 0.61, ad 0.64). 그런데 활성 사이클당 효율은 kws 0.269, ad 0.650으로 크게 다르다.
- H1-UC로 본 1×1 DF 구성의 차이:
  - kws G25(25×5×140, Cin 140): eff 0.613. 공간 25×5 → 26×6(F_sp 1.248), Cout 140 → 160(F_cout 1.143), Cin 조각 64+64+12에서 12 → 32(F_cin 1.143)이다.
  - ad G11/G12/G52(16×16·8×8, Cin 192·276, Cout 276): eff 0.918–0.958. 공간 패딩이 없고(F_sp 1.000), Cout 276 → 288(1.043), Cin 276의 끝 조각 20 → 32(1.043)이다.
  - 같은 방향의 차이다. 1×1 DF 집합의 eff_set이 ad 0.928, kws 0.613이다(V4 성립).
- 그러나 H1-UC 패딩이 설명하는 몫은 작다:
  - E는 kws 0.110(A∪B∪C 0.167), ad 0.134다. 관측 초과분(kws 41,258, ad 32,787 사이클)의 대부분이 H1-UC 집합 밖에 남는다.
  - 남는 부분의 후보는 1×1 DF 밖의 연산이다. 근거는 POST_HOC_DESCRIPTIVE인 `mac_family_breakdown.csv`이다.
    - kws: 첫 Conv 10×4 PartKernel(Cin 1)이 N_MAC의 17.6 %, DW 3×3이 4.9 %다. Vela가 이 둘에 매긴 MAC 사이클은 13,125와 17,164이고, 이상치(N/1024)는 2,680과 738이다.
    - ad: DW 3×3이 3.1 %, 3×3 PartKernel이 2.8 %다. Vela MAC 사이클은 28,781과 9,841이다.
    - 연산별 PMU 귀속이 없으므로 이 배분은 판정하지 않는다(Stage 2B 한계 유지).
  - 또 하나의 가능성은 같은 구성이라도 모델 안의 MAC_ACTIVE가 A2 래퍼에서 잰 값과 다른 경우다. 지금 자료로는 구분할 수 없다.
- 결론: H1-UC는 kws와 ad 사이 1×1 DF 구성 차이의 **방향**과 일관된다. 하지만 두 모델 효율 차이의 대부분을 H1-UC로 설명했다고 할 수 없다. kws는 판정 기준(V3)에서도 근거 범위가 모자란다.

### MobileNetV2와 VWW4

- 1×1 DF는 69 %·65 %이지만, 보드 측정 구성(A)이 덮는 몫은 13.9 %·6.7 %이고 나머지는 C(외삽)다.
- H1-UC 밖의 MAC: 1×1 PartKernel 20.6 %·23.2 %, DW 3×3 6.9 %·8.8 %, 3×3 PartKernel 3.6 %·1.6 %다.
  - Vela는 DW에 MAC 사이클을 크게 매긴다: mobilenet 323,490(이상치 20,231), vww4 56,057(이상치 1,613).
- E(A∪B)는 0.011·0.013이다. 낮은 MAC 활성·효율의 원인으로 H1-UC를 쓸 수 없다.
- **VWW4의 AO>MAC(P3)은 AO 축의 문제다.** MAC 패딩 모델인 H1-UC와 별개이며, 이번 결과로 다루지 않는다.

### YOLO-Fastest, Wav2Letter, RNNoise

- YOLO:
  - H1-UC 계산 가능 42.6 %는 모두 C다.
  - 1×1 PartKernel 34.3 %, DW 3×3/5×5 21.4 %는 범위 밖이다.
  - E(A∪B∪C) 0.024다.
- Wav2Letter:
  - 1×32·1×7·1×48 **PartKernel**이 83 %이고 D다.
  - 1×1 DF 17.2 %(G14·G15)는 C다. G14는 LUT fused다.
  - 관측 효율이 이미 0.968이라 설명할 초과분이 상대적으로 작다(초과분 112,527 사이클 = MAC_ACTIVE의 3.2 %, E(A∪B∪C) 0.091).
  - M4(MAC 포함)의 MLEK 동등성은 UNPROVEN 상태 그대로다.
- RNNoise:
  - MAC의 100 %가 **FC**이고 D다. 1×1 Conv 모델로 설명하지 않는다.
  - MAC_ACTIVE 548 사이클, 효율 0.155다.

## 4. P1–P7 (`p1_p7.csv`; 기존 판정은 그대로 둔다)

| 현상 | 모델 | 기존 판정 | 새 증거 | 설명할 수 있는 부분 | 남은 요인 | H1-UC MAC 수준 |
|---|---|---|---|---|---|---|
| P1 MAC 활성 높고 유효율 낮음 | kws | INSUFFICIENT | A 47.2 %, eff_set 0.613, E 0.110 | 1×1 DF 패딩 방향 | 첫 Conv(Cin 1)·DW, C 30 % | INSUFFICIENT_EVIDENCE |
| P2 MAC 효율 높고 WD_STALLED 높음 | ad | INSUFFICIENT | A 92.1 %, R ≥ 0, E 0.134 | MAC 축의 1×1 DF 패딩 일부 | WD_STALLED 전부, MAC 초과분 87 % | PARTIAL_MAC_COST |
| P2 | wav2letter | INSUFFICIENT | A∪B 0 | — | PartKernel 83 %, WD | INSUFFICIENT_EVIDENCE |
| P3 AO > MAC | yolo, vww4 | INSUFFICIENT | A∪B 0 / 6.7 % | — | AO 축(H1-UC 밖) | INSUFFICIENT_EVIDENCE |
| P4 MAC 활동 매우 낮음 | rnnoise | INSUFFICIENT | 대상 0 | — | FC | NOT_APPLICABLE_TO_H1UC |
| P5 NPU 대 Vela | rnnoise | INSUFFICIENT | 대상 0 | — | 전체 | NOT_APPLICABLE_TO_H1UC |
| P6 SRAM 예산 | ad | INSUFFICIENT | WD 축 | — | WD 재스트리밍 | NOT_APPLICABLE_TO_H1UC |
| P7 MAC 비슷해도 사이클 다름 | 7개 | INSUFFICIENT | 위 표 | ad의 MAC 축 일부만 | AO·WD·메모리, 대부분의 MAC 초과분 | ad PARTIAL_MAC_COST, 나머지 INSUFFICIENT 또는 N/A |

- `PARTIAL_MAC_COST`는 MAC 축의 일부라는 뜻이다. WD_STALLED, AO 병목, 메모리 대기, NPU_ACTIVE 전체의 원인으로 넓히지 않는다.
- Stage 6의 판정(모두 INSUFFICIENT_EVIDENCE)은 소급 변경하지 않았다.

## 5. E2 연결 (`e2_link.csv`, 기술만)

| 근거 | H1-UC = 실측 MAC_ACTIVE | Vela Conv mac_cycles | Vela Conv op_cycles | Vela 그래프 cycles | 실측 NPU_ACTIVE |
|---|---|---|---|---|---|
| 6B-B VALID 7 (A2 그래프) | 1,728–20,736, 7/7 같음 | H1-UC의 1.09–2.42배 | 7,031–24,290 | cycles_total 10,955–53,052 | 19,131–99,555 |
| E1-R 6 (Conv 단독) | 20,216–58,520, 6/6 같음 | H1-UC의 0.90–1.17배 | 58,593–171,630 | Σop = Conv op | 65,692–131,056 |

- 단위는 모두 NPU 사이클이다. 6B-B의 NPU_ACTIVE에는 ADD 2개와 DMA가 포함된다.
- Vela의 MAC 사이클 추정은 측정 MAC_ACTIVE와 일관되게 같지도, 일관되게 크지도 않다(6B-B는 모두 크고, E1-R은 5개가 작음).
- Vela의 메모리 비용 모델이 보드의 TA profile 1 에뮬레이션과 같은지는 확인되지 않았다.
- 후속 계약 초안: `e2_contract_draft.md` (실행하지 않음).

## 6. 설명 한계

- H1-UC는 MAC_ACTIVE 모델이다. NPU_ACTIVE 중 MAC이 쉬는 부분, WD_STALLED, AO, 메모리 대기는 다루지 않는다.
- 원본 모델의 연산별 PMU 귀속이 없다(Stage 2B 한계). 그래서 E는 "H1-UC가 모델 안에서도 성립한다면"이라는 조건부 몫이고, R ≥ 0은 필요조건일 뿐이다.
  - R의 가정(MAC 엔진은 한 번에 kernel 하나, 연산당 MAC_ACTIVE ≥ N/1024)도 검증하지 않았다.
- A는 A2 래퍼(ADD→Conv→ADD) 안에서 잰 구성이다. 원본 모델 안의 파이프라인과 의존성(cascade, 앞뒤 연산, weight 버퍼링)은 다를 수 있다.
- B 범위는 차원별 상자이고, 차원 사이의 상호작용은 검증하지 않았다. 이번에는 해당 연산이 없었다.
- driver_m7(이미지 `65cf963`)과 형상 측정(이미지 `70090f1`)은 이미지가 다르다. TA profile은 둘 다 1이다.

## 7. 권고

- 모델 수준 설명력을 더 올리려면 H1-UC를 더 확인하는 것보다 다음 둘이 먼저다.
  - H1-UC 밖 연산(1×1 PartKernel, DW, 첫 Conv)의 MAC_ACTIVE 비용
  - 원본 모델 안의 연산별 귀속
- 둘 다 보드 측정이 필요하므로 별도 승인이 필요하다.
- KWS V3를 다시 보려면 G24·G23(kws op 8·10, Sram/Sram)을 보드로 재야 한다. 그 경우에도 기준과 규칙은 바꾸지 않는다.
- E2(Vela 오차 분해)는 위 초안대로 별도 승인 전까지 실행하지 않는다.

## 파일과 재현

| 파일 | 내용 |
|---|---|
| `operator_mapping.csv` | 7개 모델의 모든 TFLite 연산(372행): N_MAC, Vela 실행, 범주, 사유 |
| `h1uc_operators.csv` | 대상 93개: kernel, ublock, block, Cin 조각, H1-UC, eff, F_sp·F_cout·F_cin, 범주, B 실패 차원, 메모리, cascade, LUT, Vela 대조 |
| `model_metrics.csv`, `coverage_comparison.csv`, `p1_p7.csv`, `e2_link.csv`, `stage6m_summary.json` | 판정 코드 산출물 |
| `mac_family_breakdown.csv` | POST_HOC_DESCRIPTIVE (`evidence/stage6m/family_breakdown.py`), 판정 입력 아님 |

```
# 컨테이너 (/work/s6b_host, 저장소와 sha256 같음): 원본 kernel 추출
python3 host/container/stage6m_models.py kernels /work/s6m/kernels_1.json
# Mac
python3 host/analysis/stage6m.py run evidence/stage6m/facts/kernels.json results/fi101_stage6m
python3 evidence/stage6m/family_breakdown.py results/fi101_stage6m
```

- 분석을 두 번 돌렸을 때 산출물 7개의 sha256이 같았다. kernel 추출도 두 번 해서 같았다.
- 기준 커밋 `b57af6f` 이후 바뀐 기존 파일은 `test.sh`의 모듈 목록 한 줄뿐이다.
- 컨테이너 사본 불일치 22개는 `evidence/stage6m/container_copies.md`에 있다. 누락 12개와 예전 git 버전의 사본 10개이며, 이번 분석에 쓰지 않았고 고치지 않았다.
