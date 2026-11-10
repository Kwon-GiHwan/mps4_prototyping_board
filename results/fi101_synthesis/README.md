# FI101 Ethos-U85 1024 — Stage 1·2A·3·4·5 종합 (2026-11-11, 새 보드 측정 없음)

이 문서는 기존 결과 문서만 모아 정리한다. 새 측정·새 판정은 없고, 원래 문서의 판정과 표시(`OBSERVED`,
`POST_HOC_DESCRIPTIVE`, `HYPOTHESIS`, `UNRESOLVED` 등)를 그대로 옮긴다. 숫자의 근거는 각 절의 출처 문서다.
기본 실험은 Stage 5-2로 끝났다(owner, 2026-11-11). 아래 §5의 후보는 제안일 뿐이며, 자동으로 시작하지 않는다.

**공통 조건.**
- **TA profile 1 (MLEK `ta_config_u85_sys_dram_mid`)**: 모든 보드 숫자. 메모리는 TA가 흉내 낸 SYS_DRAM_Mid이며
  FPGA DRAM 자체가 아니다.
- FI101 Ethos-U85 1024 MAC, Vela 5.0.0, MLEK의 Vela 옵션(Dedicated_Sram, `Ethos_U85_SYS_DRAM_Mid_1024`).
- 모든 사이클은 NPU 사이클이다. "실행 시간·실행 비용"은 NPU_ACTIVE(event 35)를 뜻한다.

| 묶음 | 실행 환경 | 사용 규칙 |
| --- | --- | --- |
| Stage 1·2A·3 (boots 94–100) | 기존 runner, 이미지 `2bb04bfa`, MLEK 입력 | Driver Runner m7(boots 308–316)로 재검증했다. `REVALIDATED`는 그대로, `RETAINED`는 조건과 함께, `CONDITION_SPECIFIC`는 따로 표시하며, `runner_window`는 쓰지 않는다(`results/driver_m7/reval/reval.csv`) |
| Stage 2B (2B-2, 2B-3, QREAD) | 기존 runner `d0cd4775` / Driver Runner | 그룹·연산 귀속 시도. H1/H2는 **무효**이고, 연산별 시간은 없다 |
| Stage 4·4C (boots 330–350) | Driver Runner `83398c7` | 독립 연산, 그래프 입출력이 DRAM에 있다. 원본 모델의 연산별 비용이 아니다 |
| Stage 5 (boots 351–366) | Driver Runner `83398c7` | 컴파일 설정 변경 = 실행 구성 전체의 효과 |

---

## 0. MAC 수의 정의와 출처 (owner 요청 2026-11-11, 정정 이력 포함)

**유효 MAC(N_MAC) = 프로젝트 정의.**
- 원본 tflite의 연산 shape에서 계산한다(`host/container/workload_meta.py`). CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, BATCH_MATMUL만 MAC을 가진다.
- Stage 1·3의 효율·처리량·bytes/MAC이 모두 이 값을 쓴다.
- 출처는 `evidence/stage1/workload_manifest/manifest.json`(kws, ad, mobilenet)과 `evidence/x1_mlek_models/manifest.x1.json`(나머지 넷)이다.

Vela의 `nn_macs`는 컴파일 결과마다 다른 Vela 자체의 집계다. 별도 열로만 두고, 효율에는 쓰지 않는다.

| model | MAC을 가진 연산 (tflite) | 유효 MAC (프로젝트 정의) | Vela `nn_macs` Performance @384 KiB | Vela `nn_macs` Size @384 KiB | 유효 ÷ Vela Perf. |
| --- | --- | ---: | ---: | ---: | ---: |
| kws_micronet_m | CONV 7, DW 5 | **15,556,352** | 14,208,852 | 15,580,852 | 1.095 |
| ad_medium_int8 | CONV 7, DW 5 | **62,346,720** | 61,466,400 | 61,466,400 | 1.014 |
| mobilenet_v2_1.0_224_INT8 | CONV 36, DW 17 | 300,775,552 | 300,840,274 | 300,840,274 | 1.000 |
| vww4_128_128_INT8 | CONV 37, DW 17 | 18,828,800 | 18,763,264 | 18,763,264 | 1.003 |
| rnnoise_INT8 | FC 9 | 86,952 | 87,510 | 87,510 | 0.994 |
| yolo-fastest_192_face_v4 | CONV 56, DW 28 | 38,916,000 | 38,807,136 | 38,807,136 | 1.003 |
| wav2letter_pruned_int8 | CONV 11 | 3,491,098,000 | 3,491,110,876 | 3,491,110,876 | 1.000 |

- **독립 연산(Stage 4·4C·5):** 연산이 하나이므로 Vela의 집계가 공식과 같다. Stage 4의 gate B가 같음을 검사했다(예: Conv 24·24·Cin·96).
- **Vela 집계를 쓰는 곳:**
  - Stage 1의 block fill (컴파일 값)
  - Stage 2B-2의 그룹별 "Vela MAC share"
  - 보조 열 `vela_macs`
  - ad의 차이(1.4 %)로는 2B-2의 불가능한 그룹 효율 2.845가 설명되지 않는다.
- **kws의 차이 9.5 %**의 이유는 확인하지 않았다(Vela 내부 집계, 해석하지 않음).

**정정 이력 (Stage 5).**
1. `93f26a3`
   - 변형 구성마다 그 구성의 Vela 집계를 쓰던 것(kws Size 15,580,852)을 base 컴파일의 집계로 바꿨다.
   - 하지만 그 값(kws 14,208,852, ad 61,466,400)도 Vela 집계였다. 5-2 계약의 "원본 정의(14,208,852, = the model's)" 표기가 틀렸다.
2. 이번 정정
   - Stage 5의 유효 MAC을 위 프로젝트 정의로 바꿨다(`host/analysis/stage5.py` `EFFECTIVE`, Stage 1과 같은 manifest).
   - 독립 연산은 base 컴파일의 값(= 공식)을 쓴다.
   - 테스트 1개를 추가했고, 변이 시험은 9/9 RED다.
   - 판정은 바뀌지 않았다. `evidence/stage5_2/verdicts_unchanged.py`가 정정 전 커밋과 비교한다:
     5-1은 `caa7325`, 5-2는 `93f26a3` 대비 config·출력·기준 재현·쌍 판정·카운터가 모두 같았다.
   - 이 검사 자체도 판정·카운터·출력을 바꾼 3개 변이에서 모두 실패했다.
   - 바뀐 것은 MAC 기반 파생값뿐이다. Stage 5 README에는 효율이 보고되지 않았고, summary의 파생값만 갱신되었다.
3. 결과: kws의 MAC 활성 사이클 효율 **26.9 %**(Stage 1 = 5-1 base = 5-2 base)는 같은 정의로 일치한다.
   ChatGPT 검토의 24.58 %는 Vela Performance 집계(14,208,852)로 계산한 값이다.

| config (TA profile 1) | 유효 MAC | MACs / (1024 × MAC_ACTIVE) | MACs / (1024 × NPU_ACTIVE) | bytes / MAC (Pass B, SRAM + EXT) |
| --- | ---: | ---: | ---: | ---: |
| Stage 1 kws (기존 runner, 재검증) | 15,556,352 | 26.9 % | 16.7 % | 0.058 |
| 5-1/5-2 kws Performance @384 KiB | 15,556,352 | 26.91 % | 16.55 % / 16.65 % | 0.058 |
| 5-2 kws Size @384 KiB | 15,556,352 | 26.63 % | 16.59 % | 0.058 |
| 5-1 kws 64 KiB / 0 | 15,556,352 | 26.91 % / 26.91 % | 15.71 % / 13.32 % | 0.058 / 0.054 |
| Stage 1 ad | 62,346,720 | 65.0 % | 41.7 % | 0.040 |
| 5-1/5-2 ad Performance @384 KiB | 62,346,720 | 65.00 % | 41.70 % / 41.51 % | 0.040 |
| 5-2 ad Size @384 KiB | 62,346,720 | 65.00 % | 41.84 % | 0.042 |
| 5-1 ad 64 KiB / 0 | 62,346,720 | 64.21 % / 66.64 % | 16.15 % / 25.92 % | 0.065 / 0.040 |

---

## 1. 실측으로 확인한 사실 (모델 전체, Stage 1·2A·3)

NPU_ACTIVE는 Driver Runner m7의 중앙값(64 RUN)이고, 나머지는 Stage 1·3 값이다. 비율은 같은 RUN의 `npu_active`로 나눴다.
효율은 §0의 유효 MAC을 쓴다.

| model | NPU_ACTIVE (m7) | MAC active ÷ ACTIVE | MAC 활성 사이클 효율 | 1024 기준 효율 | DPU/MAC | AO active | WD stalled | bytes/MAC | SRAM / EXT B/cycle | MAC stalled by IB* | ACTIVE ÷ Vela `cycles_npu` | Vela block fill (컴파일 값) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| kws | 91,262 | 62.1 % | 26.9 % | 16.7 % | 0.877 | 19.5 % | 70.7 % | 0.058 | 7.1 / 2.8 | 9.8 % | 1.05 | 0.53 |
| ad | 146,040 | 64.2 % | 65.0 % | 41.7 % | 1.000 | 28.5 % | 79.8 % | 0.040 | 12.3 / 4.8 | 14.7 % | 1.04 | 0.88 |
| mobilenet | 1,449,070 | 39.7 % | 51.1 % | 20.3 % | 0.864 | 30.5 % | 83.6 % | 0.076 | 11.9 / 3.9 | 33.3 % | 0.83 | 0.85 |
| vww4 | 234,489 | 24.0 % | 32.5 % | 7.8 % | 0.772 | 27.4 % | 57.0 % | 0.130 | 8.8 / 1.6 | 27.6 % | 1.06 | 0.89 |
| rnnoise | 50,436 | 1.1 % | 15.5 % | 0.2 % | 0.781 | 0.6 % | 22.3 % | 1.500 | 0.1 / 2.5 | 6.5 % | 1.62 | 0.24 |
| yolo | 447,982 | 38.3 % | 22.1 % | 8.5 % | 0.749 | 46.2 % | 72.1 % | 0.187 | 15.2 / 1.1 | 33.8 % | 0.94 | 0.84 |
| wav2letter | 4,132,806 | 85.2 % | 96.8 % | 82.5 % | 0.968 | 1.4 % | 72.1 % | 0.011 | 2.0 / 7.2 | 1.0 % | 0.79 | 0.87 |

- 표의 열은 모두 `REVALIDATED`다. 예외: vww4 WD active는 `CONDITION_SPECIFIC`(표에 없음).
- \* Reserved-ID 이벤트다. 의미는 드라이버 상태 비트에서 추론했으므로 탐색용이다.
- Driver Runner와 MLEK: 일곱 모델 모두 출력·beat 4종·NPU_ACTIVE가 `EQUIVALENT`(−0.33 … +0.47 %)다.
  MAC/DPU/AO는 여섯 모델 `EQUIVALENT`, wav2letter는 `UNPROVEN`이다.

모델 수준의 연관성이며, 원인은 확정하지 않았다.

1. **MAC 활동 비중의 폭이 넓다.**
   - MAC 활동 비중은 rnnoise 1.1 %부터 wav2letter 85 %까지다.
   - 1024 기준 효율은 0.2 %부터 82.5 %까지다.
2. **MAC이 활동한 사이클 안에서도 효율이 낮은 모델이 있다.**
   - kws 27 %, yolo 22 %, vww4 33 %, rnnoise 16 %.
   - vww4·yolo는 block fill이 0.84–0.89로 높은데도 효율이 낮다. block fill로는 설명되지 않는다.
3. **AO가 MAC보다 오래 활동하는 모델:** yolo(46 % vs 38 %), vww4(27 % vs 24 %).
4. **DPU/MAC은 0.75–1.00이다.** 활동 카운터 사이의 관계이며, 점유율이 아니다.
5. **메모리 접근.**
   - EXT 읽기 요청 stall은 포트-사이클의 6–18 %이고, SRAM은 ≤ 0.6 %다(`RETAINED`: 여섯 모델은 기존 값 유지, 한 모델만 재측정).
   - outstanding-limit stall은 0이거나 거의 0이다.
   - SRAM 대역폭은 최대 15.2 B/cycle로, 두 포트 합의 약 절반이다.
   - 측정 바이트는 모든 모델에서 Vela 추정보다 적다.
   - EXT 포트 0/1 분배·EXT read burst는 `CONDITION_SPECIFIC` 또는 `REMEASURE_REQUIRED`이므로 쓰지 않는다.
6. **단위 stall** (탐색용):
   - MAC stalled by IB는 depthwise 비중이 큰 모델(mobilenet 33 %, yolo 34 %, vww4 28 %)에서 높고, wav2letter에서 1 %다.
   - WD stalled by WD buffer는 Conv 모델에서 43–65 %다.
   - CC blockdep stall은 vww4 52 %, rnnoise 41 %, yolo 35 %다.
   - stall은 겹치므로 더하지 않는다.
7. **ACTIVE ÷ Vela `cycles_npu`**(Vela summary, 네트워크 전체의 compute 추정): rnnoise 1.62, mobilenet 0.83,
   wav2letter 0.79, 나머지 0.94–1.06. 범위가 다른 두 양의 비이며, Vela의 오차로 읽지 않는다.
8. Driver Runner 창은 NPU_ACTIVE보다 모델과 무관하게 534–666 사이클 길다.

---

## 2. 통제 실험으로 확인한 조건별 영향 (Stage 4·4C·5)

**조건.**
- Driver Runner `83398c7`, Pass A(Stage 1 세트 A) + Pass B(Stage 3 세트 B), warm-up 1 + 측정 4.
- 쌍 판정: tol = max(base의 1 %, 두 RUN 범위 중 큰 값). Pass A가 주 판정이고 Pass B는 확인용이며, 방향이 반대면 `UNRESOLVED`다.
- 출력은 모든 구성에서 PASS_EXACT였다.

### 2.1 연산 종류 (Stage 4, 독립 연산, 입출력 DRAM)

| | Conv 1×1 16→96 @24×24 | DWConv 3×3 144 @56×56 | FC 96→288 |
| --- | ---: | ---: | ---: |
| MACs per MAC-active cycle | 384 | 128 | 256 |
| ÷ 문서상 클래스 최대치 (TRM Table 7) | 0.375 (CONV 1024) | **1.00** (DW 128) | 표에 없음 |
| MAC_ACTIVE ÷ NPU_ACTIVE | 10.9 % | 19.9 % | 1.15 % |

- DWConv는 MAC 활동 중에 클래스 최대치로 돌았다. 매핑 실패가 아니다.
- 세 독립 연산 모두 NPU_ACTIVE의 대부분이 MAC 활동 밖이었다.
- 무엇이 실행을 지배하는지는 `HYPOTHESIS`다(FC는 가중치 읽기, DW는 DRAM 입출력).

### 2.2 채널 정렬 (Stage 4, 4C-1)

- **채널 하나를 줄여도 MAC_ACTIVE는 사이클 단위로 같았다.** 다섯 쌍: Conv Cin 15, Cout 95, DW 143, FC in 95, FC out 287.
- **NPU_ACTIVE**
  - Conv Cout 95는 +7.0 % / +10.4 %, DW 143은 +6.1 % / +6.1 %였다. 둘 다 EXT write beat +93 %와 함께였다(인과 미확인).
  - FC out 287은 두 Pass에서 재현되지 않았다.
- **출력 쓰기 beat 규칙 A**는 새 4개 조건(remainder 14·1)에서 사전 예측과 모든 RUN이 일치했다. 메커니즘은 `UNVERIFIED`다.
- **DWConv MAC_ACTIVE**는 C를 16의 배수로 올림한 양과 맞았다(145 → ×10/9; `POST_HOC_DESCRIPTIVE`, 이 shape 한정).

### 2.3 처리 구성과 채널 조건 (4C-1, 4C-2, 4C-2b) — 적용 범위 정정

**비례 관계는 시험한 정렬된 쌍에 한정한다.**
- Cin 16 → 32(PartKernel)와 64 → 128(DepthFirst)에서는 MAC_ACTIVE가 계산량에 정확히 비례했다(×2).
- DepthFirst의 **Cin 40과 48은 계산량이 달라도(×1.2) MAC_ACTIVE가 같았다**(3,456). 채널을 16의 배수로 올린 계산량과 부합한다.
- 그러므로 "같은 처리 구성에서는 계산량에 비례한다"는 일반 결론이 아니다.

| 관측 조건 (Conv 1×1, 24×24, Cout 96) | MACs / MAC_ACTIVE | MACs / MAC_DPU_ACTIVE |
| --- | ---: | ---: |
| PartKernel, Cin 16·32 | 384 | 768 |
| DepthFirst, Cin 48·64·128 | 768 | 768 |
| DepthFirst, Cin 40 | **640** | **640** |

- 처리 방식만으로 유효 처리율이 정해지지 않는다. 채널 조건도 바꾼다.
- DPU/MAC = 1.0이어도 실효 처리량은 다를 수 있다(Cin 40).
- Cin 32 → 64에서는 traversal, IFM block 깊이(16 → 64), weight order가 함께 바뀌었고, 처리량이 384에서 768이 되었다. 원인은 분리하지 않았다.
- **ublock 변경 (Conv Cout 96 → 97):**
  - OFM ublock이 2×2×32에서 2×4×16으로 바뀌었다.
  - MAC_ACTIVE −12.5 %, MACs per active cycle +15.5 %인데, NPU_ACTIVE는 +23 % / +25 %였다.
- **사후 정규화:** MAC_ACTIVE ÷ OFM ublock = 4.0(Conv, Cin 16)과 9.0(DW). 이 관계는 Cin 32 이상에서 유지되지 않았다.

### 2.4 SRAM 작업공간 예산 (Stage 5-1)

5-0 분류에서 모든 비교가 `SCHEDULE_CHANGED`였다. 따라서 결과는 실행 구성 전체의 효과다.

| workload | 384 KiB (기준) | 64 KiB | 0 |
| --- | --- | --- | --- |
| kws | 91,770 | +5.4 % / +6.6 % (kernel 14 → 19) | **+24.2 % / +25.4 %** |
| ad | 145,991 | **+158 % / +158 %** (kernel 14 → 66) | +61 % / +60 % |
| dw_base | 159,780 | payload 동일, 측정 안 함 | +0.5 %, `UNRESOLVED` |
| conv_base | 21,587 | payload 동일, 측정 안 함 | `UNRESOLVED`; MAC_ACTIVE 2,304 → 1,728 (kernel 2 → 1) |

- kws·ad의 MAC_ACTIVE는 거의 그대로였다(kws −3 사이클, ad −2.5 % … +1.2 %). 그래도 NPU_ACTIVE는 늘었다.
- **ad는 64 KiB에서 0보다 느렸다(×2.58).** 예산과 실행 비용은 단순 비례 관계가 아니었다.
- 예산이 줄면 전송이 EXT로 옮겨 갔다. kernel 수, EXT 전송, 시간의 증가는 함께 일어났지만 각각의 인과적 기여는 확정하지 않았다.
- Conv·DW의 `UNRESOLVED`는 SRAM이 필요 없다는 뜻이 아니다.

### 2.4a AD 64 KiB 사례 — 정적 분석 (보드 없음, `results/ad64k_static/README.md`)

**상태: 실행 구성 변화와 성능 차이는 확인했으나, 개별 요인의 인과적 기여는 분리하지 못했다** (owner 채택 2026-11-11, AD 분석 종료).

- **실측 사실 (5-1, TA profile 1).**
  - NPU_ACTIVE: 384 KiB 145,991, 64 KiB 376,999(×2.58), 0 234,881(×1.61).
  - MAC_ACTIVE: 93,672 / 94,824 / 91,368(+1.2 %, −2.5 %). AO_ACTIVE 변화는 1 % 미만이다.
  - WD_ACTIVE: 64 KiB에서만 ×2.15(0은 기준과 같음).
  - EXT 읽기: 0.71 / 2.55 / 1.82 MB. EXT 쓰기: 0 / 0.22 / 0.66 MB.
  - EXT 총량은 64 KiB가 0보다 11.6 % 많지만, NPU_ACTIVE는 60.5 % 많다(보조 관측; 메모리 병목의 증명·배제 근거로 쓰지 않음).
- **정적 근거** (측정한 Vela 출력·command stream과 해시로 연결):
  - 64 KiB의 kernel 66개 = 원본 연산 1–7이 60개 + 8–13이 6개다. 늘어난 52개는 모두 연산 1–7의 cascade stripe 분할에서 나왔다(연산 1–3은 16 stripe, 4–5·6–7은 3 stripe).
  - 원본 연산 3(Conv 1×1 192→276)의 가중치 58,016 B가 stripe마다 DRAM에서 다시 stream된다(16회). 연산 5·7은 3회다.
  - DRAM 가중치 stream은 423 KB → 1,637 KB로 늘었다. 연산 3·5·7의 출력과 4·6·8의 입력은 DRAM을 거친다.
  - 0은 가중치를 한 번씩만 읽고, feature map을 모두 DRAM에 둔다.
  - MAC_ACTIVE 변화는 연산 1·2의 ublock 수 변화와 산술적으로 맞는다(사후).
- **탐색 결과 (컴파일만):**
  - 80·96·112·128 KiB에서는 작업 분할·block·중간 데이터 배치가 함께 바뀌었다. 다른 주요 조건을 유지한 채 가중치 반복 이동만 다른 비교 구성은 찾지 못했다.
  - 연산 3의 가중치를 SRAM에 버퍼하는 구성도 없었다.
- **결론의 한계.**
  - 반복 가중치 이동은 64 KiB가 0보다 느린 것의 유력한 원인 후보다.
  - 반복 읽기·작업 분할·데이터 배치 각각의 시간 기여는 분리하지 못했다.
- **추가 관측 (실행 성능 미측정).** kernel 수(66·77·40·43·86)와 정적 DRAM 가중치 stream(1.64·2.09·1.26·1.18·3.31 MB)은 예산(64 → 128 KiB)에 따라 단조롭게 줄지 않았다. 새 예산의 실행 비용은 측정하지 않았다.
- **의미.** Stage 4는 독립 연산이라 원본 모델의 연산 비용으로 옮기지 않았다. 이 사례는 실제 모델에서 관측한 큰 성능 차이를 그 모델의 컴파일 구성과 연결했다.

### 2.5 최적화 전략 Performance vs Size @384 KiB (Stage 5-2)

5-0에서 세 workload 모두 `MEMORY_ONLY`였다(kernel별 계산 구성은 같고, 가중치 stream·배치가 다름).

| workload | SRAM 사용 Perf. → Size | NPU_ACTIVE Δ A / Δ B | 판정 | MAC_ACTIVE | 전송 변화 (Pass B) |
| --- | --- | --- | --- | --- | --- |
| kws | 89.5 → 89.5 KiB | +0.38 % / +0.26 % | `UNRESOLVED` | 56,450 → **57,055** (DPU 같음) | 없음 |
| ad | 244.0 → **300.8 KiB** | −0.79 % / −1.12 % | `UNRESOLVED` | 같음 | SRAM 읽기 +10 %, SRAM 쓰기 +9 %, EXT 읽기 −9 % |
| conv Cin 64 | 8.4 → 9.3 KiB | +0.37 % / +0.48 % | `UNRESOLVED` | 같음 | SRAM 읽기 +11 %, EXT 읽기 transaction −22 % |

- 내부 실행 구성과 일부 카운터는 달라졌지만, 전체 실행 시간의 차이는 이번 기준으로 판정하지 못했다. 같다는 뜻이 아니다.
- SRAM 사용량이 같거나 늘었다는 것은 이 세 workload의 fast-scratch 요구량에 한정된 결과다.
- kws Size의 MAC_ACTIVE +605(+1.07 %)는 모든 RUN에서 같았다. 계산 레지스터는 같고 두 kernel의 가중치 stream만 달랐다. 원인과 전체 실행에 대한 영향은 확인하지 않았다.
- mobilenet(`SCHEDULE_CHANGED`인 Size 사례)은 `UNMEASURED`다.

### 2.6 MAC 활동과 전체 실행 비용

여러 실험에서 MAC_ACTIVE와 NPU_ACTIVE는 따로 움직였다.

| 유형 | 사례 |
| --- | --- |
| MAC 효율↑, 전체 비용↑ | Conv 97 (+15.5 % vs +23 %) |
| MAC_ACTIVE↓, 전체 비용 미판정 | conv 예산 0 (−25 %, `UNRESOLVED`) |
| MAC_ACTIVE 같음, 전체 비용↑ | Cout 95, DW 143, kws·ad 예산 축소 |
| 둘 다 개선 | Cin 32 → 64 |
| MAC_ACTIVE만 변화, 전체 비용 미판정 | kws Size (+605) |
| 전송 경로 변화, MAC·전체 비용 미판정 | ad·Cin 64 Size |

- MAC_ACTIVE는 측정한 모든 독립 연산 구성에서 RUN 범위가 0이었다(결정적).
- NPU_ACTIVE는 RUN마다 수백–수천 사이클 흔들렸다.

### 2.7 Vela 추정과 보드 — 실측 불일치와 판정 불가를 구분 (정정)

필드와 범위는 다음과 같다. 모두 NPU 클럭 사이클이고 Vela의 모델 값이며, 보드 지표는 NPU_ACTIVE다.
- Stage 4: Vela debug database의 연산별 `perf.npu_cycles`(compute)와 `perf.op_cycles`(compute·memory 중 큰 값), 연산 하나짜리 네트워크.
- Stage 5: Vela summary의 `cycles_npu`(네트워크 compute 추정)와 `cycles_total`(네트워크 전체 추정).
- 보드 NPU_ACTIVE: PMU arm(NPU 시작 직전)부터 완료 IRQ까지의 command stream 전체. 범위가 같지 않으므로 비율을 오차로 읽지 않는다.

**A. 보드 변화가 확인되었고, Vela가 그 증가폭을 재현하지 못한 경우**

| 사례 | 보드 NPU_ACTIVE (A / B) | Vela |
| --- | --- | --- |
| Conv Cout 95 | +7.0 % / +10.4 % (`NOT_PROPORTIONAL_TO_MAC`) | `npu_cycles` −1.0 %, `op_cycles` 0 |
| DW 143 | +6.1 % / +6.1 % | `npu_cycles` 0, `op_cycles` −0.7 % |

**B. 보드 변화가 확인되었고, Vela도 같은 방향이지만 폭이 다른 경우 (5-1)**

| 사례 | 보드 | Vela `cycles_total` / `cycles_npu` |
| --- | --- | --- |
| ad 64 KiB | ×2.58 | ×2.99 / ×2.46 |
| ad 0 | +61 % | +81.5 % / −0.5 % |
| kws 0 | +24–25 % | +27.1 % / −8.8 % |
| kws 64 KiB | +5–7 % | +2.9 % / +6.7 % |

**C. 보드 변화가 `UNRESOLVED`인 경우: Vela의 예측 변화는 예측 오류가 아니다.** 보드에서 변화가 없다는 것도 보이지 않았다.

| 사례 | 보드 | Vela |
| --- | --- | --- |
| Conv Cin 15 | −1.4 % / +0.03 % | `op_cycles` ×2.46, `npu_cycles` −40 % |
| conv 예산 0 | +0.4 % / +2.8 % | `cycles_total` −25 %, `cycles_npu` −3.9 % |
| dw 예산 0 | +0.5 % / +0.5 % | `cycles_npu` −0.5 %, `cycles_total` 0 |
| kws Size | +0.38 % / +0.26 % | `cycles_npu` +4.0 %, `cycles_total` +3.4 % |
| Cin 64 Size | +0.37 % / +0.48 % | `cycles_npu` +0.7 % |
| ad Size | −0.79 % / −1.12 % | 0 |

**D. FC out 287:** 사전 판정 라벨은 `NOT_PROPORTIONAL_TO_MAC`이지만 두 Pass에서 재현되지 않았다(−9.5 % / +0.9 %). Vela는 −0.25 %였다. A·B·C 어디에도 넣지 않는다.

---

## 3. 원본 모델과의 연결이 아직 가설인 부분

**이번 연구가 보인 것.** 연산 종류, 채널 조건, 처리 구성, SRAM 예산이 실행 비용과 MAC 활동을 바꿀 수 있다는 것을
통제 실험으로 보였다.
**보이지 못한 것.** 그 요인들이 원본 일곱 모델의 실행 시간에서 각각 얼마를 차지하는지는 나누지 못했다.

- **Stage 4·4C의 범위.** 독립 연산이고 그래프 입출력이 DRAM에 있다. 원본 모델에서는 feature map이 SRAM에 있었고
  cascade 안의 연산도 있었다. 그러므로 모델 안의 연산별 비용으로 옮기지 않는다.
- **Stage 5의 범위.** kws·ad와 독립 연산만 측정했다. 다섯 모델의 예산·전략 효과는 `UNMEASURED`다.
- **Stage 1 현상 중 통제 실험으로 설명되지 않은 것** (`HYPOTHESIS` 또는 미설명):
  - vww4·yolo의 낮은 MAC 활성 사이클 효율 (block fill은 높음)
  - depthwise 비중이 큰 모델의 높은 MAC stalled by IB
  - rnnoise의 보드 ÷ Vela 1.62
  - yolo·vww4에서 AO가 MAC보다 오래 활동하는 것
- **채널 올림·ublock padding과 모델 효율의 관계는 가설이다.** 4C의 "16의 배수 올림"과 ublock 선택이 kws 등의
  낮은 효율에 기여할 수 있다는 것은 모델의 연산 shape에서 확인하지 않았다.
- **그룹·연산 귀속은 얻지 못했다.**
  - 2B-2의 PMU Mask 창은 실행이 아니라 명령 해석 위치를 따라갔다(ad CONV 그룹 MAC 효율 2.845, 불가능). **H1/H2는 계속 무효다.**
  - 2B-3는 `WINDOW_AMBIGUOUS`였다.
  - QREAD는 `BOUNDARY_OBSERVED`였지만 PMU 귀속은 `NOT_ASSOCIATED`(판독 비용 297 → 642 cycles)였다.
  - 연산별 시작·종료, 실행 시간, PMU 귀속은 독립 연산 결과나 구성 비교로 복원하지 않는다.

---

## 4. 계측·표본·실행 환경의 한계

- **메모리 환경.** TA 에뮬레이션(SYS_DRAM_Mid) 아래의 값이다. TA clock stop이 감춘 FPGA 메모리 대기는 어떤 이벤트에도 나타나지 않는다.
  NPU 카운트는 경과 CPU 시간보다 0–31 % 적다(S0-3).
- **NPU_ACTIVE의 비-MAC 부분.** Stage 4 독립 연산에서 80–99 %(4C Conv Cin 128은 70 %), 모델에서 15–99 %다.
  측정으로 나누지 못했고, 전송 증가는 함께 관측되었을 뿐 대역폭이나 메모리 대기로 배정하지 않았다.
- **이벤트.** Reserved-ID 이벤트(단위 stall 등)는 의미를 추론한 것이다. 이벤트 53·55는 TRM 110에 없다.
- **표본.**
  - 입력은 MLEK 입력 하나뿐이다.
  - Stage 4·4C·5는 구성당 한 부팅에 측정 4 RUN이다(Pass별). 부팅 간·입력 간 재현성은 주장하지 않는다.
  - FC는 RUN 범위가 중앙값의 약 7–9 %다.
- **동등성.**
  - wav2letter M4는 `UNPROVEN`이다(교차 재확인 `NO_SHIFT`는 따로 기록하고 합치지 않음).
  - Stage 1 문서는 vww4·yolo·wav2letter OFM을 tflite 대비로 주장하지 않았다. Driver Runner m7에서는 일곱 모델 모두 MLEK와 출력이 같았다.
- **컴파일러.** Vela 5.0.0 regor 경로만 사용했다. Dedicated_Sram만 검증된 실행 구성이다. Vela의 스케줄 정책은 컴파일 결과로만 기술했다.
- **변수 분리.** 대부분의 구성 비교에서 여러 설정이 함께 바뀌었다(`SCHEDULE_CHANGED`, traversal·IFM block·weight order 동시 변경).

---

## 5. 중요한 심층 분석 후보와 우선순위 (제안만; 자동으로 시작하지 않음)

| 우선 | 질문 | 근거 | 가장 작은 다음 단계 |
| --- | --- | --- | --- |
| ~~1~~ **종료** | 같은 계산인데 ad 64 KiB가 왜 0보다 느린가 (×2.58) | 5-1 | 정적 분석·컴파일 탐색 완료(§2.4a). 실행 구성 변화와 성능 차이는 확인, 개별 요인의 인과적 기여는 미분리. 추가 탐색·보드 측정 없음 |
| 2 | MAC 활동이 같거나 좋아졌는데 전체 비용이 늘어나는 부분 | Conv 97, Cout 95, DW 143, kws·ad 예산 | 계약 필요 |
| 3 | 모델의 낮은 MAC 활성 사이클 효율을 채널 올림·ublock padding이 얼마나 설명하는가 | Stage 1 kws·yolo·vww4, 4C | Vela 산출물로 정적 계산(보드 없음) |
| 4 | depthwise 비중 모델의 MAC stalled by IB | Stage 3 | Reserved-ID 의미 확인이 먼저 |
| 5 | rnnoise 보드 ÷ Vela 1.62 | Stage 1 | 구성 확인(보드 없음) |
| 6 | 계산 레지스터가 같은데 MAC_ACTIVE가 바뀐 이유 (kws Size +605) | 5-2 | 가중치 stream 차이를 산출물로 비교(보드 없음) |

- 남은 후보 2–6은 목록으로만 유지하며, 자동으로 착수하지 않는다.
- 연산별 시간 귀속(2B H1/H2의 재구성)은 새 방법 없이는 후보에서 뺀다.

---

## 출처

| 내용 | 문서 |
| --- | --- |
| Stage 1 | `results/fi101_stage1/README.md`, `stage1.csv` |
| Stage 2A | `results/fi101_stage2a/README.md` |
| Stage 3 | `results/fi101_stage3/README.md`, `results/fi101_stage3_channels/` |
| 재검증 | `results/driver_m7/README.md`, `results/driver_m7/reval/reval.csv`, `docs/plan/reference_environment.md` |
| Stage 2B | `results/fi101_stage2_groups/README.md`, `results/fi101_stage2b3/README.md`, `results/qread_op_pilot/FINAL.md` |
| Stage 4 | `results/fi101_stage4/stage4_analysis.md`, `results/fi101_stage4c1/README.md`, `results/fi101_stage4c2/README.md`, `results/fi101_stage4c2b/README.md` |
| Stage 5 | `results/fi101_stage5/README.md`, `results/fi101_stage5_2/README.md`, `evidence/stage5/stage5_0.json` |
| AD 64 KiB 정적 분석 | `results/ad64k_static/README.md`, `evidence/ad64k_static/` (컴파일 산출물, 예산 탐색) |
| 요약본 | `results/fi101_synthesis/SUMMARY.md` |
| MAC 정의 | `host/container/workload_meta.py`, `evidence/stage1/workload_manifest/manifest.json`, `evidence/x1_mlek_models/manifest.x1.json` |
