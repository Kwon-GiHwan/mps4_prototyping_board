# 후속 검증 계약 초안 (Phase 4) — **실행 미승인**

- Stage 6B-R의 식은 모두 같은 데이터로 만든 사후 식이다. 검증하려면 **새로운 독립 측정**이 필요하다.
- 아래 초안의 예측값은 측정 전에 컴파일 산출물만으로 계산해 커밋한다. 측정 뒤에는 바꾸지 않는다.
- 보드 조건은 기존과 같다: Driver Runner `70090f1`, TA profile 1, DDR/EXT, pass A·B(Stage 4와 같음), pass마다 warm-up 1 + 측정 4.

## E1 (우선순위 1) — MAC 패딩 메커니즘 H1-UC의 전향적 검증

- **단일 주요 가설:** 1×1 Conv의 MAC_ACTIVE = Σ_커널 U_k · Σ_Cin조각 max(32, ⌈x,16⌉)/8.
  - U_k는 command stream 커널별 OFM의 ublock 수, 조각은 IFM block 깊이 단위다.
- **통제 변수:**
  - 연산: 1×1, stride 1, RELU6, INT8. 단일 Conv(F_PLAIN 계열)이며 A2 래퍼를 쓰지 않는다. 래퍼 효과를 섞지 않기 위해서다.
  - Vela 5.0.0과 MLEK 옵션, 이미지, TA, placement.
- **변경 변수:** H1-UC와 가장 가까운 경쟁 식(H1-U16, D-U16, "min 32 제거", "공간 padding 제거", "전체 Cout")의 예측이 서로 갈리는 값.
  - Cin 나머지 조각 ∈ {8, 16, 24, 36}: min 32와 16 단위를 가른다. 예: Cin 72, 80, 88, 100.
  - OFM 공간: ublock 경계에 맞음 / 맞지 않음. 예: 8×8 대 7×7, 같은 Cout.
  - Vela가 고른 ublock 깊이 16인 형상 1개 이상(현재 공식 표본에 없음).
  - Vela가 Cout을 여러 커널로 나눈 형상 1개(Stage 4 24×24×96 외).
- **대상 선정 규칙:** 후보를 합성 생성기로 만들어 컴파일한다. 컴파일 산출물(ublock, IFM block, 커널 분할)을 읽어, 위 경쟁 식 사이의 예측 차이가 큰 순서로 6개를 고른다.
  - 동률은 N_MAC이 작은 순서로 정한다.
  - 선정 스크립트와 결과를 측정 전에 커밋한다.
- **예측값:** 6개 형상 각각의 MAC_ACTIVE와 MAC_DPU_ACTIVE 정수값.
  - H1-UC, D-PW 외에 경쟁 식의 값도 함께 적는다.
- **PMU:** pass A 35 48 51 53 55 64 80 81, pass B 35 128 130 132 135 384 386 391.
- **출력 정확성:** 보드 출력이 CPU BUILTIN_REF golden과 PASS_EXACT여야 한다. 아니면 그 형상은 INVALID_OUTPUT이다.
- **예산:** 기준 1(Stage 4K Cin48 재현) + 6 = 최대 7 boot / 70 RUN.
- **판정:**
  - `SUPPORTED_PROSPECTIVELY`: VALID 형상 모두에서 MAC_ACTIVE = 예측(정확).
  - `CONTRADICTED`: 하나라도 다르다.
  - `INCONCLUSIVE`: VALID가 4개 미만이거나, 기준 재현이 실패했다.
  - DPU(D-PW)는 같은 표에서 따로 판정한다.
- **종료 기준:** 판정이 나면 끝난다. 추가 형상은 별도 계약으로 한다. CONTRADICTED이면 새 식을 맞추지 않고 기록만 한다.

## E2 (우선순위 2) — Vela 예측 오차의 비교 조건과 비용 모델

- **단일 주요 가설:** A2 그래프에서 Vela `cycles_total`의 과소예측(+54~+102 %)은 그래프가 DRAM 접근에 좌우되는 경우에 나타난다. 보드의 EXT 경로 비용이 Vela의 DRAM 비용 모델보다 크다는 뜻이다(현재는 `CAUSE_UNRESOLVED`).
- **1단계 (보드 없음, 먼저):** 같은 tflite를 Vela 시스템 설정만 바꿔 컴파일한다.
  - 예: Dram_clock_scale, Dram_max_reads, burst.
  - `cycles_total`의 민감도를 기록한다(가상의 예상값으로 분리 표시).
  - 대응을 모르는 TA 대역폭 레지스터(pulse·bwcap)의 의미를 TRM 또는 MLEK 소스로 확인한다. E2(TA EXT MAXR) 확인도 같이 계획한다.
- **2단계 (보드, 별도 승인):**
  - 통제 변수: 같은 Conv(G09처럼 패딩이 없는 형상).
  - 변경 변수: 메모리 배치 하나(A0 단독 Conv, Dram→Dram 대 A2 Sram→Sram).
  - 각 바이너리의 Vela `cycles_total`과 NPU_ACTIVE를 같은 바이너리끼리만 비교한다.
- **예측:**
  - 1단계 결과로 형상별 `cycles_total`을 측정 전에 고정한다.
  - "DRAM 비중이 큰 쪽의 오차가 크다"는 방향 예측을 사전 등록한다.
- **예산:** 기준 1 + 최대 4 = 5 boot / 50 RUN.
- **판정:**
  - `DIRECTION_CONFIRMED`, `DIRECTION_NOT_CONFIRMED`, `NOT_COMPARABLE`.
  - 같은 바이너리, 같은 범위(그래프 전체 대 NPU_ACTIVE)가 아니면 NOT_COMPARABLE이다.

## E3 (우선순위 3) — UNSTABLE 형상의 NPU_ACTIVE 변동

- **단일 주요 가설:** G56의 NPU_ACTIVE 변동(11.4 %)은 같은 바이너리를 다른 boot에서 재도 다시 나타난다(바이너리 고유). 반대 가설은 boot 고유다.
- **통제:** G56 fixture DRWL(같은 sha256), 이미지, TA.
- **변경:** boot만(2 boot).
- **판정:**
  - 두 boot 모두 pass A range > 5 %: `REPRODUCED`.
  - 둘 다 ≤ 5 %: `NOT_REPRODUCED`.
  - 엇갈림: `INCONCLUSIVE`.
  - MAC_ACTIVE는 6B-B 값(1,056)과 같아야 한다. 다르면 측정 무효다.
- **예산:** 2 boot / 20 RUN. 5 % 기준은 바꾸지 않는다. 결과가 나와도 6B-B의 UNSTABLE 판정은 바꾸지 않는다.

## 공통

- 추가 실험은 모두 ChatGPT/owner의 별도 실행 승인을 받는다. Stage 6C는 포함하지 않는다.
- 가장 적은 실험으로 메커니즘을 가르려면 E1 하나(최대 7 boot)가 먼저다.
  - E1이 CONTRADICTED이면 E2와 E3의 해석 틀(MAC 쪽)은 다시 검토한다.
