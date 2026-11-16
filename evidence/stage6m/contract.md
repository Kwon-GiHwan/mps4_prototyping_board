# Stage 6-M 분석 계약 — Model-level MAC Explainability Reassessment (보드 없음)

- 지시: "Stage 6-M 공식 지시"(2026-11-16). 이 계약과 판정 코드(`host/analysis/stage6m.py`), 테스트(`host/tests/test_stage6m.py`),
  mutation(`evidence/stage6m/mutate.py`)은 원본 모델의 kernel 사실을 추출하고 주요 결과를 계산하기 **전에** 커밋한다.
- 보드 측정, 새 형상 생성, Vela 옵션 변경, E2·E3·Stage 6C는 하지 않는다.
- H1-UC 식(`host/analysis/stage6br.py` `h1_uc`, 커밋 `5c801f7`)은 바꾸지 않는다. 보정계수나 예외 규칙을 더하지 않는다.
- E1-R 산출물과 판정(PROSPECTIVE_SUPPORT)은 바꾸지 않는다. Stage 6·6B-B·E1의 기존 판정도 소급 변경하지 않는다.
- 모든 MAC 비중의 분자·분모는 **원본 TFLite N_MAC**이다(`host/container/workload_meta.py` `op_macs`: CONV_2D, DEPTHWISE_CONV_2D,
  FULLY_CONNECTED, BATCH_MATMUL만 MAC을 가진다). Vela `mac_count`(nn_macs)는 대조용 열로만 둔다.

## 1. 자료 (모두 커밋된 것)

| 자료 | 경로 | 쓰는 곳 |
|---|---|---|
| TFLite 연산별 N_MAC | `evidence/stage1/workload_manifest/meta/{kws,ad,mobilenet}.meta.json`, `evidence/x1_mlek_models/{vww4,rnnoise,yolo,wav2letter}.meta.json` | 분자·분모 |
| Vela scheduled op 인벤토리 (591행) | `results/fi101_stage4/stage4_operator_inventory.csv` | 매핑, 실행 구성 |
| 출력 dtype | `results/fi101_stage6/tflite_dtypes.json` | 대상 정의(Stage 6B와 같음) |
| 원본 모델 kernel 레지스터 | `evidence/stage6m/facts/kernels.json` (이 계약 뒤 컨테이너에서 추출) | H1-UC 입력 |
| 모델 수준 PMU (driver_m7, boot 308–316, TA profile 1, 이미지 65cf963) | `results/fi101_stage6/whole_model_comparison.csv`, `evidence/driver_m7/workloads/*.drwl.json` | 관측, 무결성 |
| Stage 6 MAC coverage, P1–P7 | `results/fi101_stage6/whole_model_comparison.csv`, `anomaly_attribution_matrix.csv` | 비교 |
| 6B-B 형상 (boot 410–420, TA profile 1, 이미지 70090f1) | `results/fi101_stage6b/stage6bb/shapes.csv`, `coverage.csv`, `evidence/stage6b/stage6bb/workloads/stage6bb_manifest.json`, `evidence/stage6b/revision_a/compiled/*.ra.json` | A 범주, E2 표 |
| E1-R (boot 428–434, TA profile 1, 이미지 70090f1) | `evidence/stage6b/stage6be1r/workloads/{predictions,build}.json`, `results/fi101_stage6b/stage6be1r/stage6be1r_summary.json` | B 범주, E2 표 |
| 6B-R Vela 대조 | `results/fi101_stage6b/stage6br/vela_fidelity_analysis.csv` | E2 표 |

## 2. Phase 1 — 매핑 규칙

1. **무결성(V1)**: 모델마다 재컴파일한 Vela 출력 sha256과 command stream sha256이 driver_m7 DRWL 기록(`vela_sha256`, `cms_sha256`)과 같아야 한다.
   원본 tflite sha256도 같아야 하고, 인벤토리의 `vela_sha256`(앞 16자)과도 같아야 한다. 하나라도 다르면 그 모델의 매핑은 성립하지 않는다.
2. **연산 단위**: TFLite 연산 하나(`tflite_op_index`, meta `ops` 순서)가 한 행이다. N_MAC은 이 행에 한 번만 센다.
3. **TFLite ↔ Vela**: 인벤토리에서 같은 `tflite_op_index`를 가진 행 중 fused(사이클 0·MAC 0)가 아니고 CPU가 아닌 scheduled op를 그 연산의 실행으로 본다.
   - 0개면 CPU 또는 제거로, 2개 이상이면 `AMBIGUOUS_SPLIT`으로 기록한다.
4. **kernel**: scheduled op의 `cms_offsets` 각각에서 decode한 kernel 레지스터(OFM H/W/D, IFM depth, kernel 크기, 종류)를 붙인다.
   - 원본 연산 하나가 여러 kernel(Cout 분할, stripe)로 실행되면 H1-UC는 kernel마다 계산해 더한다. N_MAC은 TFLite 연산 기준으로 한 번만 센다.
5. **fusion·LUT**: 같은 모델에서 사이클 0인 행 중 `name`이 Conv 행과 같은 행을 fused 연산으로 본다. 그중 `npu_op == LUT`가 있으면 `lut_fused`다(예: wav2letter LEAKY_RELU).
   - 이 정보는 AO 쪽이다. H1-UC 값에 반영하지 않지만 A 범주의 구성 일치 조건에 넣는다.
6. 실행 구성 식별자 = `exec_sig`(stage6be1r): kernel OFM 크기 목록, ublock, OFM block, IFM block, Cin 조각별 H1-UC 비용. 여기에 메모리(IFM/OFM), stride, 활성화, `lut_fused`를 함께 비교한다.
   **Cin/Cout이 같다는 것만으로 같은 구성이라고 하지 않는다.**

## 3. Phase 2 — H1-UC 적용 범주

**대상(1×1 DepthFirst Conv)**은 Stage 6B와 같다: CPU 0, `npu_op == Conv2D`, kernel `1x1`, DepthFirst, `mac_count > 0`, 출력 INT8 (`stage6b.targets`).

**계산 가능(computable)**: 대상이면서 다음을 모두 만족한다. 하나라도 어기면 **D. NOT_APPLICABLE**(사유 기록).
- TFLite ↔ Vela 매핑이 하나(§2.3), 모델 무결성 성립(§2.1)
- 모든 `cms_offsets`에서 kernel을 찾았고, 종류가 CONV, kernel 1×1, IFM depth = Cin
- Σ_kernel H·W·D = OFM H·W·Cout (kernel이 OFM을 정확히 덮음)
- TFLite N_MAC = OFM H·W·Cout·Cin
- ublock 부피 = 128 (H1-UC를 검증한 ublock 2x2x32, 2x4x16, 1x4x32가 모두 128)

계산 가능한 연산을 다음 순서로 분류한다(앞 범주가 우선).

| 범주 | 조건 |
|---|---|
| **A. BOARD_MEASURED** | 6B-B **VALID** A2 형상(G12 G25 G40 G11 G52 G57 G09) 중 하나와 `exec_sig`, IFM/OFM 메모리, stride, 활성화가 모두 같고, `lut_fused`가 아님. A2 Conv의 kernel은 `revision_a/compiled/*.ra.json` A2 `conv_kernels`에서 읽는다. |
| **B. VALIDATED_DOMAIN_PREDICTION** | A가 아니고, E1-R 6개 형상에서 유도한 검증 범위에 모든 차원이 들어감: DepthFirst, 1×1, stride 1x1, ublock ∈ E1-R 집합({2x2x32, 2x4x16}), IFM block 깊이 ∈ E1-R 집합({64}), Cin ∈ [100, 200], OFM H·W ∈ [29, 37], Cout ∈ [96, 176], 모든 kernel이 OFM 전체 H·W를 가짐(공간 stripe 없음), IFM/OFM 메모리 ∈ E1-R 집합({Dram/Dram}), `lut_fused` 아님. 범위 값은 코드가 E1-R 파일에서 유도하고, 테스트가 위 값을 직접 적어 대조한다. |
| **C. EXTRAPOLATED_PREDICTION** | 계산 가능하지만 A·B가 아님. 추정값으로만 쓴다. 어긋난 차원을 열로 남긴다. 6B-B UNSTABLE 형상(G53 G56 G28)에 맞는 연산은 C이며, `measured_unstable_match`로 따로 표시한다. |
| **D. NOT_APPLICABLE** | 대상이 아니거나(Conv 외, DW, FC, PartKernel, 1×1 아님) 계산 가능 조건을 어김. |

- 범위는 차원별 상자로 본다. 차원 사이의 상호작용은 검증하지 않았다는 점을 보고서에 적는다.
- 메모리 배치가 측정 근거와 다르면 그 차이를 표에 남긴다. MAC_ACTIVE가 메모리 경로와 무관하다는 가정은 일부 과거 실험의 관측일 뿐이므로 범주를 올리는 근거로 쓰지 않는다.
- 파이프라인 관련 사실(`cascade`, kernel 수, 공간 stripe 여부, IFM/OFM 메모리)은 연산마다 기록만 한다.

## 4. Phase 3 — 연산별 비용 (H1-UC 정의 안에서만)

연산 o의 kernel k = (h, w, d), ublock (uh, uw, ud), Cin 조각 x ∈ chunks(Cin, IFM block 깊이)에 대해:

- `H1UC(o)` = Σ_k ⌈h/uh⌉⌈w/uw⌉⌈d/ud⌉ × Σ_x max(32, ⌈x⌉₁₆)/8 (stage6br `h1_uc` 그대로)
- `ideal(o)` = N_MAC(o)/1024. 예상 유효 MAC/활성 사이클 = N_MAC/H1UC, 정규화 효율 `eff(o)` = ideal/H1UC
- 비용 인자는 **곱으로** 쓴다. U = Σ_k⌈h/uh⌉⌈w/uw⌉⌈d/ud⌉, U₀ = Σ_k h·w·d/128, C = Σ_x max(32,⌈x⌉₁₆)/8, C₀ = Cin/8일 때:
  - `F_U` = U/U₀ (공간 패딩과 kernel별 Cout 패딩을 함께), `F_cin` = C/C₀ (Cin 조각, 16 정렬, 최소 32)
  - 계산 가능 조건이 성립하면 1/eff = F_U × F_cin이다(검사 항목).
  - F_U 안의 단일 인자: `F_sp` = Σ_k⌈h/uh⌉⌈w/uw⌉(d/ud)/U₀, `F_cout` = Σ_k(h/uh)(w/uw)⌈d/ud⌉/U₀. 상호작용 = F_U/(F_sp·F_cout).
  - 인자들은 겹치므로 각자의 손실 사이클을 더해 원인 기여도로 쓰지 않는다. 모델 수준에서는 "그 인자만 없앴을 때의 Σ H1UC"를 따로 보고하고 합산하지 않는다.

## 5. 모델 지표

S는 연산 집합이다: S_ABC = A∪B∪C, S_AB = A∪B, S_A = A. N(model) = 모델의 모든 MAC 연산의 TFLite N_MAC 합이다.

- 1×1 DepthFirst MAC 비중 = Σ N(대상) / N(model)
- H1-UC 적용 가능 MAC 비중(= Static Structural Coverage) = Σ N(S_ABC) / N(model)
- Evidence-supported Coverage = Σ N(S_AB) / N(model)
- Direct Model-shape Measurement Coverage = Σ N(S_A) / N(model) (합집합, 연산은 한 번만)
- 집합 효율 `eff_set(S)` = Σ_S N / (1024 × Σ_S H1UC). **정적 계산 비용 모델**이며 모델 PMU 효율이 아니다.
- 관측(driver_m7): MAC_ACTIVE_meas, NPU_ACTIVE_meas, 관측 MAC 활성 효율 `eff_meas` = N_npu/(1024 × MAC_ACTIVE_meas).
  N_npu는 NPU에서 실행되는 MAC 연산(§2.3에서 scheduled op가 있는 연산)의 N_MAC 합이다.
- **경계 검사(bound)**: R(S) = MAC_ACTIVE_meas − Σ_S H1UC − Σ_{NPU MAC 연산 ∉ S} N/1024.
  - 가정 둘: MAC 엔진이 한 번에 kernel 하나를 처리한다, 연산당 MAC_ACTIVE ≥ N/1024이다. 둘 다 미검증이다.
  - R(S) < 0이면 "H1-UC를 모델 안에 그대로 적용하는 것"이 관측과 양립하지 않는다(`BOUND_VIOLATION`). 이것은 H1-UC의 단일 연산 판정을 바꾸지 않는다.
  - R(S) ≥ 0은 필요조건일 뿐이며, 복원의 근거가 아니다.
- **초과분 설명 비율** E(S) = Σ_S (H1UC − N/1024) / (MAC_ACTIVE_meas − N_npu/1024).
  - 관측 MAC_ACTIVE 중 이상치(N/1024)를 넘는 부분 가운데 S의 H1-UC 패딩 손실이 차지할 수 있는 몫이다. **H1-UC가 모델 안에서도 성립한다는 조건부**이다.
  - Σ_S H1UC / MAC_ACTIVE_meas는 기술 열로만 둔다. 독립 연산의 합으로 모델 MAC_ACTIVE나 NPU_ACTIVE를 복원했다고 주장하지 않는다.

## 6. Phase 4–5 — 비교와 coverage

- 모델별: 위 지표, 관측 MAC/NPU, Stage 1(구 runner, boot 94–100) 값은 참고 열로만 둔다. driver_m7(REVALIDATED)이 기준이다.
- KWS·AD: 대상 연산의 실행 구성, 인자(F_sp, F_cout, F_cin), eff_set, E, R를 나란히 둔다.
- MobileNetV2·VWW4: 적용 가능 비중, DW 비중(TFLite N_MAC), AO>MAC(P3)는 MAC 패딩 모델과 다른 문제라는 점을 명시한다.
- YOLO·Wav2Letter·RNNoise: 설명 가능한 부분(S의 비중)과 불가능한 부분(DW, PartKernel, FC 등)을 TFLite N_MAC으로 나눈다.
  RNNoise의 FC와 Wav2Letter의 PartKernel은 D다.
- Coverage 표: 새 세 지표(TFLite 기준) 옆에 Stage 6 MAC calibrated coverage와 6B-B Validly Measured Shape(둘 다 Vela `mac_count` 기준)를 그대로 둔다.
  E1-R 합성 형상은 Direct 지표에 넣지 않는다.

## 7. 판정 (closed set, 위에서 아래 순서로 처음 성립하는 것)

H1-UC의 PROSPECTIVE_SUPPORT는 이 분석으로 바뀌지 않는다. 모델 수준 설명력만 판정한다.

- V1 무결성: 7개 모델 모두 §2.1 성립.
- V2 경계: S_AB가 비지 않은 모든 모델에서 R(S_AB) ≥ 0.
- V3 근거 범위: KWS와 AD 모두 Evidence-supported Coverage ≥ 0.50.
- V4 방향: eff_set(S_AB)가 AD > KWS이고, eff_meas도 AD > KWS.
- V5 정량: E(S_AB) ≥ 0.10인 모델이 KWS·AD 중 하나 이상(사전 고정한 "무시할 수 없는 몫"의 하한).

| 판정 | 조건 |
|---|---|
| `INSUFFICIENT_EVIDENCE` | V1 실패 |
| `EXPLANATORY_SUPPORT_PARTIAL` | V1–V5 모두 성립 |
| `COVERAGE_EXPANDED_NOT_EXPLAINED` | 위가 아니고, Static Structural Coverage가 Stage 6 MAC calibrated coverage보다 큰 모델이 하나 이상 |
| `INSUFFICIENT_EVIDENCE` | 그 밖 |

- 실패한 V 항목과 `BOUND_VIOLATION` 모델은 summary에 그대로 남긴다.

## 8. Phase 6 — P1–P7

각 현상 행(Stage 6 `anomaly_attribution_matrix.csv`)에 기존 관측·기존 판정(그대로)을 두고, 새 열 `h1uc_mac_level`을 아래 closed set으로 정한다.

| 값 | 조건 |
|---|---|
| `NOT_APPLICABLE_TO_H1UC` | 현상의 축에 mac이 없거나, 그 모델의 대상 연산 N_MAC이 0 |
| `PARTIAL_MAC_COST` | 그 모델에서 R(S_AB) ≥ 0, Evidence-supported Coverage ≥ 0.50, E(S_AB) ≥ 0.10 |
| `INSUFFICIENT_EVIDENCE` | 그 밖 |

- `PARTIAL_MAC_COST`는 MAC 축의 일부만 뜻한다. WD_STALLED, AO 병목, 메모리 대기, NPU_ACTIVE 전체의 원인으로 넓히지 않는다. 연산별 PMU 귀속이 없다는 Stage 2B의 한계는 그대로다.

## 9. Phase 7 — E2 연결 (기술만)

- 측정 형상(6B-B VALID 7 + 기준 + E1-R 6): H1-UC 예측, 실측 MAC_ACTIVE, Vela Conv `mac_cycles`, Conv `op_cycles`, 그래프 `cycles_total`(있는 것만), 실측 NPU_ACTIVE와 단위를 한 표에 둔다.
- 원본 대상 연산: H1UC 대 Vela `vela_mac_cycles`의 비(정적, `POST_HOC_DESCRIPTIVE`).
- E2 계약 초안(`results/fi101_stage6m/e2_contract_draft.md`)을 쓴다. 실행하지 않는다.

## 10. 산출물과 검증

- `results/fi101_stage6m/`: `operator_mapping.csv`(7개 모델 모든 TFLite 연산), `h1uc_operators.csv`(대상 연산의 kernel·인자·범주), `model_metrics.csv`, `coverage_comparison.csv`, `p1_p7.csv`, `e2_link.csv`, `stage6m_summary.json`, `README.md`, `e2_contract_draft.md`.
- 테스트는 합성 fixture와 직접 적은 기대값을 쓴다. 판정·범주·지표 규칙마다 mutation을 걸어 모두 KILLED여야 한다.
- 재현성: 분석을 두 번 돌려 산출물 sha256이 같아야 한다. kernel 추출도 두 번 해서 같아야 한다.
- 불변성: 기준 커밋 `b57af6f` 대비 기존 파일은 `test.sh`의 모듈 목록 한 줄 외에 바뀌지 않는다.
- 컨테이너: 작업 경로는 `/work/s6b_host`(쓰는 파일은 저장소와 sha256 대조)와 `/work/s6m`이다. `/work/mps4_host`, `/work/selftest`의 기존 불일치 22개는 기록만 하고 고치지 않는다.
- 로컬 커밋만 한다. push하지 않는다.
