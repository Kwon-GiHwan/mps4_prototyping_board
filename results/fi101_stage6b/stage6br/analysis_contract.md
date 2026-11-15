# Stage 6B-R 분석 계약 — MAC 처리 메커니즘과 Vela 예측 오차 (보드 없음)

작성 2026-11-15. 근거: "Stage 6B-R 공식 지시". 이 단계에서는 보드를 쓰지 않고, 기존 판정과 측정값을 바꾸지 않는다.
모든 가설은 Stage 6B-B 결과(`a2c7406`)를 본 뒤에 세운 것이므로 **`POSTHOC_EXPLANATORY`**다. 이 계약을 지금 커밋해도 기존
데이터에 대한 독립적인 사전 검증이 되지는 않는다.

**탐색 사실을 먼저 밝힌다.** 계약을 쓰기 전에 다음 탐색을 이미 했다(대화 기록에 남아 있다).
- 6B-B 형상 10개와 Stage 4 1×1 6개에 대해, command stream의 커널별 OFM 크기에서 OFM ublock 수를 셌다.
- MAC_ACTIVE와 MAC_DPU_ACTIVE를 ublock 수로 나눴다.
- 그 결과 아래 H1-UC와 D-PW를 찾았다.

따라서 이 둘은 이미 맞춘 식이며, 아래 판정은 그 식이 실제로 얼마나 맞는지를 기록하는 데 그친다. 분석 중에 새 가설을 찾으면
`EXPLORATORY`로 따로 적고, 아래 판정에는 넣지 않는다.

## 1. 원자료 (모두 커밋된 파일)

| 자료 | 경로 |
| --- | --- |
| Stage 4K 1×1 측정 (Cin 16·32·40·48·64; boot 369–378, TA profile 1, 70090f1) | `results/fi101_stage4k/stage4k_table.csv`, 정적 `results/fi101_stage4k/static.json` |
| Stage 4C2 1×1 Cin 128 (같은 형상 계열) | `results/fi101_stage4c2/stage4c2_table.csv`, `static.json` |
| Stage 6B-B 원시 PMU·판정 | `evidence/stage6b/stage6bb/raw/`, `results/fi101_stage6b/stage6bb/` |
| 6B-B 컴파일 산출물·커널 레지스터 | `evidence/stage6b/revision_a/compiled/*.ra.json` (A2 `conv_kernels`, `rows`), manifest `evidence/stage6b/stage6bb/workloads/` |
| Vela 추정 | `evidence/stage6b/revision_a/amendment_b/facts/vela_total.json`; 추가로 같은 tflite의 Vela 요약 CSV 전체 필드(바이트 포함)를 컨테이너에서 다시 수집 |
| Vela 설정 | 컨테이너 `vela --version`, `/opt/arm/ml-embedded-evaluation-kit/scripts/vela/default_vela.ini`, `pack_vela_workload.VELA_OPTIONS` |
| 보드 메모리·TA | 6B-B `capabilities.json`, `host/lib/pmwl.py` TA_PROFILES[1], `evidence/runner_gap/open_equivalence_items.md` E2 |

## 2. 가설과 계산식 (Phase 1)

공통 기호:
- 커널 k의 OFM 크기 (H_k, W_k, D_k)는 command stream의 OFM height·width·depth에서 읽는다.
- ublock (u_h, u_w, u_c)는 Vela가 기록한 `ofm_ublock`이다.
- IFM block 깊이 b_d는 Vela의 `ifm_block` 깊이다.
- U_k = ⌈H_k/u_h⌉·⌈W_k/u_w⌉·⌈D_k/u_c⌉이다.
- 1 ublock-cycle = u_h·u_w·u_c 출력 × 8 입력 채널 = 1024 MAC이다(2×2×32 또는 2×4×16 → 128 × 8).

| ID | 가설 | 예측 MAC_ACTIVE |
| --- | --- | --- |
| H1-G | 지시서의 전역 padding | ⌈H,u_h⌉·⌈W,u_w⌉·⌈Cin,32⌉·⌈Cout,16⌉ / 1024 |
| H1-C16 | 입력 크기만 16 단위로 올림 | H·W·⌈Cin,16⌉·⌈Cout,16⌉ / 1024 |
| H1-U8 | 커널별 ublock × ⌈Cin/8⌉ | Σ_k U_k · ⌈Cin/8⌉ |
| H1-U16 | 커널별 ublock × ⌈Cin,16⌉/8 | Σ_k U_k · ⌈Cin,16⌉/8 |
| **H1-UC** | 커널별 ublock × IFM 깊이 조각 비용 | Σ_k U_k · Σ_조각 max(32, ⌈x,16⌉)/8. 조각은 Cin을 b_d 단위로 나눈 것이다(마지막 조각 x = 나머지) |

- 구성요소 확인(지시 2.1)은 H1-UC에서 한 요소만 뺀 변형으로 한다.
  - 공간 ublock padding 제거(⌈H/u_h⌉ 대신 H/u_h)
  - 커널별 Cout slice 대신 전체 Cout 사용
  - 조각 없이 Cin 전체에 규칙 적용
  - min 32 제거
  - 변형마다 일치 수를 보고한다.
- DPU 가설(지시 2.4, MAC 가설과 같은 메커니즘이라고 가정하지 않음):
  - D-R: 지시서의 DPU/MAC = ⌈Cin,8⌉/⌈Cin,32⌉
  - D-U16: Σ U_k · Σ_조각 ⌈x,16⌉/8
  - D-U8: Σ U_k · Σ_조각 ⌈x,8⌉/8
  - D-PW: 조각 ≤ 8이면 ⌈x,8⌉/8, 그 밖은 ⌈x,16⌉/8 (탐색으로 찾은 식)

**비교 대상**: 1×1 Conv만 본다.
- 공식 표본(VALID)은 다음 12개다.
  - Stage 4K: Cin 16·32(PartKernel), 40·48·64(DepthFirst)
  - Stage 4C2: Cin 128
  - 6B-B: 기준(Cin 48, boot 410), G12·G25·G40·G11·G52·G57·G09
- 6B-B UNSTABLE 3개(G53·G56·G28)는 MAC/DPU가 4회 모두 같았지만 공식 표본에 넣지 않는다. `EXPLORATORY` 열에만 적는다.
- Stage 4K 3×3은 범위 밖이고, 참고로만 적는다.

**판정** (가설마다, 공식 표본 기준):
- `CONSISTENT_WITH_OBSERVATIONS`: 모든 공식 표본에서 예측이 측정값과 정확히 같다. MAC 카운터는 RUN 간 범위가 0인 정수다.
- `CONTRADICTED`: 하나라도 다르다.
- `INSUFFICIENT_EVIDENCE`: 식을 계산할 정적 정보가 없는 표본이 있다. 또는 경쟁 가설과 예측이 갈리는 표본이 1개 이하다.
- 수치가 일치해도 일반 법칙으로 분류하지 않는다(사후 도출). 전향적 검증 필요 여부를 따로 적는다.

**예외 형상(G25, G53)**: 다음 항목을 정적으로 대조한다. 원인은 단정하지 않는다.
- Cin/Cout 정렬, ublock·block, 공간 가장자리, traversal, 커널 수, IFM/OFM 메모리, padding 계산

## 3. Vela 분석 (Phase 2)

- 형상별(VALID 7개)로 다음을 정리한다.
  - Vela `cycles_total`, `cycles_npu`, `cycles_sram_access`, `cycles_dram_access`
  - Vela 바이트(SRAM/DRAM read/write)
  - 보드 NPU_ACTIVE, 보드 beat × 16 B
  - 부호 있는 오차와 절대 오차
- Vela 비용 구성 확인:
  - 연산별 `op_cycles`가 max(npu, sram_ac, dram_ac)인지(합이 아님)를 debug DB 행으로 검사한다.
  - `cycles_total`이 연산별 `op_cycles`의 합인지 검사한다.
  - 둘 다 정적 검사다. Vela 소스 정의는 확인 가능한 범위만 적는다.
- 설정 대조(`vela_configuration_audit.md`):
  - Vela의 resolved 값과 보드(TA profile 1 레지스터, capabilities)를 항목별로 `MATCH`, `MISMATCH`, `UNKNOWN`으로 적는다.
- 결과 범주(근거별로 따로 적용): `CONFIGURATION_MISMATCH_IDENTIFIED`, `COST_MODEL_DISCREPANCY_OBSERVED`, `CAUSE_UNRESOLVED`.
- 기존 오차 수치는 지우지 않는다. 설정 보정으로 만든 가상의 예상값은 이번에 만들지 않는다.
- 상관은 기술 통계로만 쓴다(n=7).
- 모델 수준(Stage 1, 종합 문서 §1-7: NPU_ACTIVE ÷ `cycles_npu` 0.79–1.62)과의 비교는 조건이 다른 비교다. 직접 비교 실험으로 쓰지 않는다.

## 4. UNSTABLE 진단 (Phase 3)

G53·G56·G28의 원시 RUN으로 다음을 표로 만든다. 기준 형상과 VALID 형상을 함께 둔다. 판정은 바꾸지 않고, 5 % 기준도 완화하지 않는다.
- RUN 순서별 NPU_ACTIVE(pass A·B)
- MAC_ACTIVE 반복 일관성
- AO·WD 변동
- pass B의 SRAM/EXT beat·transaction 변동
- NPU_ACTIVE 변동과 다른 카운터 변동의 RUN 단위 동조 여부
- OFM 크기와 출력 바이트

## 5. 후속 계약 초안 (Phase 4)

지시 §5의 형식과 우선순위로 작성한다. 실행은 별도 승인을 받는다.

## 6. 산출물과 검증

- 출력은 `results/fi101_stage6b/stage6br/`에 둔다. 지시 §6의 8개 파일을 만든다.
- 계산 코드는 `host/analysis/stage6br.py`, 테스트는 `host/tests/test_stage6br.py`다. 테스트의 기대값은 직접 손으로 쓴 값이다.
- 불변성: 기존 evidence·results 파일의 수정·삭제가 없음을 git으로 확인한다. 6B-B 판정을 다시 실행해 결과가 바이트 단위로 같은지 확인한다.
