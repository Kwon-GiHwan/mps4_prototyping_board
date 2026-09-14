# H13 — H1′·H2′·H3′ 검증 캠페인 계획서 (2026-09-14, 실행 전 고정)

GO 전문: `2026-09-14-h1-h3-verification-GO.md`. 가설 원문: `docs/paper/raw_data_report/amendments/A10_revised_hypotheses.md`.
매니저 대조 체크리스트: `docs/paper/raw_data_report/amendments/manager_review_20260914_v7_directive.md` §0.
실행 기록·원시 증거·분석기: `docs/paper/raw_data_report/amendments/h13/` (서버 `/tmp/h13/`).

이 문서의 판정 기준·예측값은 **해당 측정을 보기 전에** 고정한 것이다. 결과를 본 뒤 고치지 않는다.
바꿔야 한다면 §9에 amendment로 추가한다(원문은 남긴다). 기존 frozen evidence·X4·S4는 건드리지 않는다.

## 0. 공통 조건과 게이트

| 항목 | 값 |
|---|---|
| 환경 | X4와 동일: 컨테이너 `benchmark-runner`, `/tmp/xqbin/stage1.py` 하니스, FVP `fvp_avh/FVP_Corstone_SSE-320`(U85)·`fvp_installed/...SSE-300_Ethos-U55/U65`, MLEK 26.03.0, Vela 5.0.0, GCC 15.2.1, `SOURCE_DATE_EPOCH=1776763519` |
| TA 명시 | 모든 빌드에 SRAM·EXT 16개 파라미터(MAXR/MAXW/MAXRW/RLATENCY/WLATENCY/PULSE_ON/PULSE_OFF/BWCAP)를 `-D`로 **전부** 넘긴다. 기본값은 `ta_parameters.csv`의 프로파일 값. 자동 선택에 맡기지 않는다 |
| 산출물 고정 | 런타임(TA) 실험은 MAC별 Vela 산출물을 동결 SHA와 동일하게 재생성해 사용한다(G1) |
| 입력 | stock `inference_runner`의 `std::rand() & 0xFF`(srand 없음, A7). 입력 바이트는 검증 빌드가 UART에 덤프한다 |
| 반복 | 조건(arm)마다 독립 FVP 프로세스 3회 |
| 출력 검증 | arm마다 stock 소스 + `-DVERIFY_TEST_OUTPUT=1`(MLEK 기본 제공 옵션, 코드 패치 없음) 빌드를 1회 추가 실행해 입력·출력 텐서 hex 덤프를 얻는다. 같은 셀의 모든 arm에서 출력이 동일해야 한다 |
| 계측 영향 | 검증 빌드의 PMU 카운터 6종이 같은 arm의 stock 빌드와 동일한지 기록한다(덤프는 추론 창 밖이므로 동일 예상). 다르면 `INSTRUMENTATION_DEVIATION`으로 기록하고 stock 값만 결과에 쓴다 |
| 원시 증거 | 전체 UART, cmake/vela 명령, generated `timing_adapter_settings.h`, AXF·Vela·cc-body SHA, `results.jsonl` |
| 구조 정보 | 합성 모델은 `vela --verbose-schedule --verbose-performance`로 op·OFM·block·ublock·per-op cycle을 남긴다 |

게이트(모두 통과해야 그 arm의 값이 결과에 들어간다):

| 게이트 | 내용 | 실패 시 |
|---|---|---|
| G1 | Vela 산출물 SHA·cc body SHA = 동결값(기존 셀). 합성 모델은 같은 MAC의 모든 arm에서 동일 | `RULE_H13_ARTIFACT` → 해당 arm NOT_EVALUABLE |
| G2 | 각 셀의 기본 프로파일 arm이 동결 카운터(TOTAL·ACTIVE·beat 4종)를 정확히 재현 | `RULE_H13_BASE_MISMATCH` → 해당 셀 전체 NOT_EVALUABLE |
| G3 | 3회 반복의 카운터 벡터 동일 | `RULE_H13_REPS_DIFFER` → arm NOT_EVALUABLE |
| G4 | generated header의 16개 TA 값 = 요청값 | `RULE_H13_TA_HEADER` → arm NOT_EVALUABLE |
| G5 | 상태 SUCCESS, `Inference completed.`, overflow/에러 문자열 없음 | `RULE_H13_RUN` → arm NOT_EVALUABLE |
| G6 | 검증 빌드 출력 덤프가 같은 셀의 기준 arm과 동일 | `RULE_H13_OUTPUT_MISMATCH` → 해당 실험 중단(GO §7) |

MAXR/MAXW는 헤더 주석대로 6비트 필드다. 요청값과 실제 적용값이 다를 수 있는 경우(예: 64)는 H1-B에서
64와 0(무제한)·63을 함께 측정해 **경험적으로** 구분한다. FVP는 NPU 자체 outstanding 제한을 파라미터로
노출하지 않는다(`--list-params` 확인: `ethosu.num_macs`·`diagnostics`·`extra_args`뿐). 따라서 "NPU 자체
제한"은 측정으로만 추정하고 값을 단정하지 않는다.

## 1. H1-A — 읽기·쓰기 지연 분리 (RNNoise U85 256·512·1024·2048)

프로파일: 256 = low, 512·1024·2048 = mid (X4와 동일). 나머지 TA 파라미터는 해당 프로파일 값.

| arm 군 | EXT_RLATENCY | EXT_WLATENCY |
|---|---|---|
| 읽기 sweep | 0 / 125 / 250 / 500 / 1000 | 250 |
| 쓰기 sweep | 500 | 0 / 125 / 250 / 500 |
| 둘 다 0 | 0 | 0 |
| 기본(G2) | 프로파일 기본 (250/125 또는 500/250) | |

동일 define 조합은 한 번만 측정한다(512·1024·2048의 500/250은 기본 arm과 같다).

**지표 (사전 정의).** k_r = [C(R=1000,W=250) − C(R=0,W=250)] / 1000 · k_w = [C(R=500,W=500) − C(R=500,W=0)] / 500.
둘 다 "설정 1 사이클당 실행 사이클 변화"이며 왕복 횟수가 아니다(체크리스트 C2).

**판정 (MAC별).**

| 조건 | 결과값 |
|---|---|
| k_w ≤ 0.2·k_r | `READ_DOMINANT` |
| k_r ≤ 0.2·k_w | `WRITE_DOMINANT` |
| 그 외 | `MIXED` |
| 가산성: C(0,0) 예측 = C(R=0,W=250) − [C(R=500,W=250) − C(R=500,W=0)] 가 실측 C(0,0)의 ±5% 이내 | `ADDITIVE` / 아니면 `NON_ADDITIVE` |
| MAC 간: 네 MAC의 k_r 최대/최소 비 ≤ 1.15 | `SENSITIVITY_SIMILAR_ACROSS_MAC` / 아니면 `SENSITIVITY_DIFFERS_ACROSS_MAC` |

X4 결합 sweep(읽기 L·쓰기 L/2)의 기울기 k와 k_r + ½·k_w를 비교해 기록한다(설명적, 판정 아님).

## 2. H1-B — 요청 동시성 (RNNoise U85 256·512)

| 변수 | 수준 |
|---|---|
| EXT_MAXR | 1 / 4 / 16 / 63 / 64 / 0(무제한) |
| EXT_RLATENCY | 250 / 1000 (EXT_WLATENCY = 프로파일 기본: 256→125, 512→250) |
| 고정 | MAXW·MAXRW(0)·BWCAP·pulse·SRAM = 프로파일 값 |

기본 프로파일의 MAXR은 256(low) = 24, 512(mid) = 64. 64가 6비트 필드에서 0(무제한)으로 적용되는지는
64 arm과 0 arm의 사이클 동일 여부로 판단한다(동일이면 `MAXR64_IS_UNLIMITED`, 다르면 `MAXR64_DISTINCT`).

**지표.** s(M) = [C(R=1000, MAXR=M) − C(R=250, MAXR=M)] / 750.

**판정 (MAC별).**

| 조건 | 결과값 |
|---|---|
| s가 M에 대해 비증가이고 s(63 또는 0) ≤ 0.8·s(1) | `CONCURRENCY_REDUCES_SENSITIVITY` |
| 모든 M에서 s(M)이 s(1)의 ±5% 이내 | `CONCURRENCY_NO_EFFECT_IN_RANGE` |
| 그 외 | `PARTIAL_OR_NON_MONOTONE` |
| 보조: s(4)와 s(16)이 같고 s(1)만 다르면 | "NPU 측 outstanding 상한이 4 이하일 가능성"으로 기록(추정, 단정 아님) |

## 3. H1-C — 예측 검증과 일반화

### 3a. 미측정 지연 375·750 (RNNoise 4 MAC, 읽기 L·쓰기 L/2 결합, X4와 같은 결합 방식)

예측 모델은 X4의 공통 구간 0/250/500/1000 네 점으로 **지금** 고정한다.
M1 = 선형 회귀 a + kL, M2 = 인접 점 구간 선형 보간.

| MAC | a | k | M1 C(375) | M1 C(750) | M2 C(375) | M2 C(750) |
|---|---|---|---|---|---|---|
| 256 | 16,286 | 97.26 | 52,757 | 89,229 | 49,086 | 89,086 |
| 512 | 12,886 | 86.74 | 45,415 | 77,943 | 43,086 | 78,086 |
| 1024 | 8,686 | 84.91 | 40,529 | 72,372 | 38,586 | 72,086 |
| 2048 | 9,086 | 92.00 | 43,586 | 78,086 | 42,086 | 78,086 |

허용 오차: M1 ±5%, M2 ±2% (예측값 기준). 판정(MAC별, 두 지연값 모두 충족해야 함):

| 조건 | 결과값 |
|---|---|
| M1 통과 | `LINEAR_ADEQUATE` |
| M1 실패, M2 통과 | `PIECEWISE_ADEQUATE` (곡률 확인) |
| 둘 다 실패 | `NEITHER_MODEL_PREDICTS` |

### 3b. KWS·AD U85 256·512 — 읽기 지연 0/250/500/1000, 쓰기 250 고정 (H1-A 읽기 sweep과 같은 설계) + 기본 arm(G2)

**지표.** 민감도 비 ρ = C(R=1000) / C(R=0). **판정(셀별):** ρ ≥ 1.10 → `LATENCY_SENSITIVE`, 그 외 `ROBUST_IN_RANGE`.
**일반화 판정:** KWS·AD 네 셀 모두 `LATENCY_SENSITIVE` → `GENERALISES_TO_KWS_AD`; 모두 `ROBUST` → `RNNOISE_SPECIFIC`; 섞이면 `PARTIAL`.
k_r도 계산해 RNNoise와 비교하되 크기 비교는 서술로만 한다(모델마다 실행 사이클 규모가 다름).

## 4. H2-A — Wav2Letter U85 외부 대역폭 × 지연

| 셀 | EXT_BWCAP 수준 (0.5× / 1× / 2× / 0) | EXT (R, W) 지연 |
|---|---|---|
| 512 (mid, 기본 3750) | 1875 / 3750 / 7500 / 0 | (500, 250) 기본 · (0, 0) |
| 256 (low, 기본 2344) | 1172 / 2344 / 4688 / 0 | (250, 125) 기본 · (0, 0) |

pulse는 프로파일 값 유지(mid 4000/1000, low 4000/1000)하고 기록한다. 명목 상한 = BWCAP × 16 B ÷ (PULSE_ON + PULSE_OFF).
달성 전송률 = (EXT_RD + EXT_WR beat) × 16 B ÷ TOTAL cycles.

**판정(셀별).**

| 조건 | 결과값 |
|---|---|
| 기본 지연에서 C(2× 또는 0) ≤ 0.90·C(1×) | `EXT_CAP_CONSTRAINED` (개입 효과) |
| 기본 지연에서 모든 수준의 사이클이 C(1×)의 ±5% 이내 **이고** 1×에서 달성 전송률 < 0.9·명목 상한 | `EXT_CAP_NOT_BINDING_IN_RANGE` |
| 모든 수준 ±5% 이내인데 달성 전송률 ≥ 0.9·명목 상한 (cap을 올려도 전송률이 안 오름) | `CAP_RAISE_INEFFECTIVE_NOT_EVIDENCE` (대역폭 무관의 근거로 쓰지 않음, GO §4) |
| 0.5×에서 ≥ 10% 증가하지만 2×/0에서 < 10% 감소 | `CAP_LOWERING_SLOWS_ONLY` |
| 지연 0 arm에서 cap 효과(2× 대비 1×의 감소율)가 기본 지연 arm과 5%p 이상 다름 | 추가 표기 `LATENCY_CAP_INTERACTION` |

H2-B 진행 조건: 512 또는 256이 `EXT_CAP_CONSTRAINED`. 아니면 H2-B 대신 "잔여 비용은 시험 범위의 외부 지연·대역폭에 반응하지 않음"으로 기록하고 SRAM·계산 쪽 조사는 다음 계약 후보로 남긴다(GO §4 분기표).

## 5. H2-B — 대표 레이어 가중치 배치 (조건부)

- Wav2Letter의 가중치 바이트가 가장 큰 Conv 연산 1개를 원본 tflite에서 읽어(가중치·양자화 파라미터 그대로) 단일 연산 tflite로 만든다. 입력 형상은 원본 스케줄의 해당 연산 IFM 형상.
- 배치 두 가지: `Dedicated_Sram`(가중치 EXT) vs `Sram_Only`(가중치·arena 모두 SRAM). U85 512(주)·256(확인). TA는 기본 프로파일.
- Vela `--verbose-schedule`로 두 배치의 command stream·block 구성 차이를 기록한다. 스케줄이 달라지면 그 사실을 결과와 함께 적는다.
- 판정: `Dedicated` 대비 `Sram_Only`에서 EXT beat가 ≥ 50% 줄고 TOTAL이 ≥ 10% 줄면 `WEIGHT_PLACEMENT_SENSITIVE`; EXT beat는 줄었는데 TOTAL이 ±5% 이내면 `WEIGHT_TRAFFIC_NOT_COST_DRIVER`; 그 외 `INCONCLUSIVE`(이유 기록).

## 6. §6 — SRAM 대역폭 상한 (KWS·AD × U55-256 Shared_Sram · U65-512 Dedicated_Sram)

SRAM_BWCAP 기본 4000 (pulse 3999/1 → 1 word/cycle). 수준 2000 / 4000 / 8000 / 0. 나머지 고정.
달성 SRAM 전송률 = (SRAM/AXI0 RD + WR beat) × word ÷ TOTAL (U55 8 B, U65 16 B).

**판정(셀별).** C(2000) ≥ 1.10·C(4000) → `SRAM_CAP_LOWERING_SLOWS`; C(8000 또는 0) ≤ 0.90·C(4000) → `SRAM_CAP_CONSTRAINED_AT_DEFAULT`;
둘 다 아니면 `SRAM_CAP_NOT_BINDING_IN_RANGE`. 기본 cap(1 word/cycle)이 인터페이스 실효 상한과 같은 값이므로 물리 SRAM 대역폭은 배제하지 않는다(GO §6).

## 7. H3 — 합성 모델 공간 형상 (U85 256·512)

모델 생성: 로컬 TensorFlow 2.21 venv, Keras → TFLite full-integer INT8(대표 데이터 = 고정 seed 균일 난수), 가중치 고정 seed.
C_in = C_out = 128. 1×1 Conv(H3-A) · 3×3 Conv same-padding · 3×3 DWConv same-padding(H3-B).

| 면적 | 형상 (H×W) |
|---|---|
| 36 | 1×36, 36×1, 2×18, 18×2, 3×12, 12×3, 4×9, 9×4, 6×6 |
| 64 | 1×64, 2×32, 4×16, 8×8 |
| 256 | 1×256, 4×64, 8×32, 16×16 |

실행 매트릭스:
- 주: 51 모델 × MAC {256, 512} × MLEK 기본 sys-config(256 Low / 512 Mid_512) × 기본 TA.
- 메모리 완화: 면적 36의 27 모델 × 2 MAC × TA 완화(EXT R/W 지연 0, EXT_BWCAP 0, SRAM 지연 0, 나머지 동일).
- Vela 공통 가정 대조군: 1×1 면적 36의 9 모델 × 2 MAC × sys-config `Ethos_U85_SYS_DRAM_Mid_512` 공통 × 기본 TA.

수집: TOTAL·ACTIVE·beat, `--verbose-schedule`(OFM block·IFM block·ublock), `--verbose-performance`(연산별 cycle), encoded weight 크기, 각 차원의 block 나머지(OFM 크기 mod block 크기).

**지표.** r = C_512 / C_256 (같은 모델, 같은 조건).

**판정.**

| 조건 | 결과값 |
|---|---|
| 같은 면적·같은 연산 종류 안에서 max r − min r ≥ 0.10 | `SHAPE_EFFECT` (면적만의 설명 반증) |
| 연산 종류별 면적 36 중앙값 r: 36 → 64 → 256 순으로 감소하고 r(256) ≤ r(36) − 0.10 | `AREA_EFFECT` |
| 면적 36에서 1×1 Conv · 3×3 Conv · 3×3 DW의 중앙값 r 중 최대−최소 ≥ 0.10 | `TYPE_DEPENDENT` |
| TA 완화 조건에서 형상 간 spread(max r − min r)가 기본 TA의 50% 미만 | `MEMORY_SHAPE_INTERACTION` |
| ublock/block 경계와 r의 관계: OFM 차원이 block 배수인 형상의 r 중앙값이 배수가 아닌 형상보다 ≥ 0.05 낮으면 | `BLOCK_ALIGNMENT_ASSOCIATED` (서술적, 통제 개입은 형상 자체) |

H×W ÷ MAC 같은 비율을 이용률로 쓰지 않는다. 1024→2048 확장은 이 결과 뒤에 별도 판단.

## 8. 실행 순서·비용 추정·산출물

| 단계 | arm 수 | 예상 시간 |
|---|---|---|
| S1: H1-A + H1-B + H1-C(3a·3b) | ≈ 40 + 24 + 8 + 18 | RNNoise/KWS/AD arm ≈ 2분(stock+검증 빌드) → ≈ 3시간 |
| S2: H2-A + §6 | 16 + 16 | Wav2Letter arm ≈ 12분, KWS/AD U55·U65 ≈ 3분 → ≈ 4시간 |
| S3: H3 (모델 생성 로컬 → scp) | 102 + 54 + 18 | ≈ 3시간 |
| S4: H2-B (조건부) | 4 | ≈ 1시간 |

산출물: `h13/results.jsonl`, `h13/uart/`, `h13/verify/`(검증 빌드 덤프), `h13/manifest.csv`(arm × 16 TA 값 × SHA),
`h13/h13_analyze.py`(+unittest, 돌연변이 검사), `h13/H13_RESULTS.md`(가설별 예측 대 관측 표, 7개 요인 갱신 판정), 그래프, 발표 반영.

## 9. Amendments

### A1 (2026-09-14, S1 실행 전) — 출력 검증 빌드는 MLEK stock 옵션만으로는 컴파일되지 않는다

§0의 "`-DVERIFY_TEST_OUTPUT=1`(코드 패치 없음)"은 성립하지 않았다. MLEK 26.03의 `VERIFY_TEST_OUTPUT` 경로는
구 API(`TfLiteTensor*`, `const Model&`)를 참조해 컴파일 오류 3종이 난다(스모크 1–3, `h13/smoke/`).
대응: `#if VERIFY_TEST_OUTPUT` 가드 **안쪽만** 고친 3-파일 패치(`h13/verify_build/verify_patch.diff`,
`verify_patch.py`, 원본과 다이제스트는 `verify_build/orig/`). 가드 밖 코드는 바뀌지 않으므로 stock 빌드의
바이트는 동일해야 하며, 이를 매 arm의 G1(stock AXF SHA = 동결 AXF SHA)로 검사한다. 스모크 4 결과:
stock AXF = 동결 AXF(True), 검증 빌드 SUCCESS, 출력 덤프 sha `305bc17f…`, 검증 빌드 PMU 6종 = stock(동일).
캠페인 종료 시 세 파일을 `orig/`의 다이제스트로 복원한다. 측정값은 항상 stock 빌드에서만 취한다.

### A2 (2026-09-14, 매니저 답변 반영 — `manager_log.md` 9번째 교환)

- **G1 정정.** 동결 AXF와의 일치는 기본 arm에만 요구한다(TA가 다른 arm은 AXF가 달라지는 것이 정상). 그 외 arm은
  Vela 산출물·cc body SHA 동일성(G1)과 arm 내 3회 반복 동일성(G3)으로 검사한다. 이미 분석기가 그렇게 구현돼 있다.
- **G6 강화.** `VERIFY_TEST_OUTPUT`는 덤프 경로이지 정답 검사가 아니다. 분석기는 검증 UART에서 출력 바이트 목록을
  추출해 같은 셀의 기준 arm과 **바이트 단위로** 비교하고, 덤프 길이가 러너가 선언한 OUTPUT 텐서 바이트 합과 같지
  않으면 `INCOMPLETE_DUMP`로 `RULE_H13_OUTPUT_MISMATCH`를 낸다. PMU 일치는 출력 동일성의 근거로 쓰지 않는다.
- **H2-B 설계 정정.** (i) 대표 레이어(op 15, 7-tap 250→250)는 원본 flatbuffer에서 연산·텐서·양자화 레코드·가중치/bias
  버퍼를 그대로 복사해 잘라낸다(재양자화 없음). 원본 전체 모델을 실행해 얻은 텐서 38(IFM)을 추출 모델에 넣었을 때
  텐서 39(OFM)와 바이트 동일해야 한다(`gen_h2b_model.py`가 검사, `h2b_manifest.json`의 `ofm_identical_to_original`).
  (ii) 주 비교는 **Shared_Sram ↔ Sram_Only**(arena는 둘 다 SRAM, 가중치만 EXT ↔ SRAM). Dedicated_Sram은 전체 배치
  효과의 보조 대조군. (iii) SRAM 적재 가능성은 Vela 요약의 SRAM 사용량(가중치+IFM/OFM+scratch)으로 확인해 기록한다.
  (iv) 모드별 스케줄·tiling 차이는 `--verbose-schedule` 덤프로 기록한다. (v) 결과는 이 레이어에 한정하며 16 MB·4 MB
  레이어로 일반화하지 않는다. §5의 판정 문구는 유지하되 "Dedicated 대비 Sram_Only"를 "Shared_Sram 대비 Sram_Only"로 읽는다.

### A3 (2026-09-14, S1 실행 중 추가 — 결과를 보고 고친 것이 아니라 arm을 더한 것)

요인 6("지연 0의 잔여 비용")이 동시 요청 수에 반응하는지 보기 위해 H1-B에 arm 4개를 더한다: RNNoise U85 256·512 ×
EXT_MAXR {1, 63} × 지연 (0, 0). 판정값은 두지 않고 서술 지표 `C00_by_maxr`로 기록한다(C(0,0)이 MAXR에 따라 5% 이상
움직이면 "지연 0 잔여 비용의 일부가 요청 직렬화에 반응"으로만 적는다). GO §3 H1-B 범위 안이다.

