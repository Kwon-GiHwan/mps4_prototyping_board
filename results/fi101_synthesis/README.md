# FI101 Ethos-U85 1024 — Stage 1·2A·3·4·5 종합 (2026-11-11, 새 보드 측정 없음)

이 문서는 기존 결과 문서만 모아 정리한다. 새 측정·새 판정은 없고, 원래 문서의 판정과 표시(`OBSERVED`,
`POST_HOC_DESCRIPTIVE`, `HYPOTHESIS`, `UNRESOLVED` 등)를 그대로 옮긴다. 숫자의 근거는 각 행의 출처 문서다.

**공통 조건.**
- **TA profile 1 (MLEK `ta_config_u85_sys_dram_mid`)**: 모든 보드 숫자. 메모리는 TA가 흉내 낸 SYS_DRAM_Mid이며
  FPGA DRAM 자체가 아니다. TA clock stop이 감춘 대기는 어떤 이벤트에도 나타나지 않는다(`results/fi101_s0_3_clk/`).
- FI101 Ethos-U85 1024 MAC, Vela 5.0.0, MLEK의 Vela 옵션(Dedicated_Sram, `Ethos_U85_SYS_DRAM_Mid_1024`).
- 모든 사이클은 NPU 사이클이다. NPU 카운트는 경과 CPU 시간보다 모델에 따라 0–31 % 적다(S0-3). "시간"은 NPU_ACTIVE를 뜻한다.

| 묶음 | 실행 환경 | 사용 규칙 |
| --- | --- | --- |
| Stage 1·2A·3 (boots 94–100) | 기존 runner, 이미지 `2bb04bfa`, MLEK 입력 | Driver Runner m7(boots 308–316)로 재검증. `REVALIDATED`만 그대로 쓰고, `RETAINED`는 조건과 함께, `CONDITION_SPECIFIC`는 따로 표시, `runner_window`는 쓰지 않음(`results/driver_m7/reval/reval.csv`) |
| Stage 2B (2B-2, 2B-3, QREAD) | 기존 runner `d0cd4775` / Driver Runner | 그룹·연산 귀속 시도. H1/H2 **무효**. 연산별 시간 없음 |
| Stage 4·4C (boots 330–350) | Driver Runner `83398c7` | 독립 연산, 그래프 입출력이 DRAM. 원본 모델의 연산별 비용이 아님 |
| Stage 5 (boots 351–366) | Driver Runner `83398c7` | 컴파일 설정 변경 = 실행 구성 전체의 효과 |

Driver Runner와 MLEK: 일곱 모델 모두 출력·beat 4종·NPU_ACTIVE `EQUIVALENT`(M1–M3), NPU_ACTIVE 차이 −0.33 … +0.47 %.
MAC_ACTIVE·MAC_DPU_ACTIVE·AO_ACTIVE(M4)는 여섯 모델 `EQUIVALENT`, wav2letter `UNPROVEN`(`results/driver_m7/`).

---

## 1. 모델 전체에서 확인한 현상 (Stage 1·2A·3)

### 1.1 표 (일곱 모델, TA profile 1)

NPU_ACTIVE는 Driver Runner m7 중앙값(64 RUN). 나머지는 Stage 1·3 값이며 재검증 결과를 열 이름 옆에 적는다.
비율은 같은 RUN의 `npu_active`로 나눈 값이다.

| model | NPU_ACTIVE (m7) | MAC active ÷ ACTIVE `REVAL` | MAC active-cycle eff. `REVAL` | peak MAC eff. `REVAL` | DPU/MAC `REVAL` | AO active `REVAL` | WD stalled `REVAL` | bytes/MAC `REVAL` | SRAM / EXT B/cycle `REVAL` | MAC stalled by IB `REVAL`* | ACTIVE ÷ Vela `REVAL` | Vela block fill (컴파일 값) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| kws | 91,262 | 62.1 % | 26.9 % | 16.7 % | 0.877 | 19.5 % | 70.7 % | 0.058 | 7.1 / 2.8 | 9.8 % | 1.05 | 0.53 |
| ad | 146,040 | 64.2 % | 65.0 % | 41.7 % | 1.000 | 28.5 % | 79.8 % | 0.040 | 12.3 / 4.8 | 14.7 % | 1.04 | 0.88 |
| mobilenet | 1,449,070 | 39.7 % | 51.1 % | 20.3 % | 0.864 | 30.5 % | 83.6 % | 0.076 | 11.9 / 3.9 | 33.3 % | 0.83 | 0.85 |
| vww4 | 234,489 | 24.0 % | 32.5 % | 7.8 % | 0.772 | 27.4 % | 57.0 % | 0.130 | 8.8 / 1.6 | 27.6 % | 1.06 | 0.89 |
| rnnoise | 50,436 | 1.1 % | 15.5 % | 0.2 % | 0.781 | 0.6 % | 22.3 % | 1.500 | 0.1 / 2.5 | 6.5 % | 1.62 | 0.24 |
| yolo | 447,982 | 38.3 % | 22.1 % | 8.5 % | 0.749 | 46.2 % | 72.1 % | 0.187 | 15.2 / 1.1 | 33.8 % | 0.94 | 0.84 |
| wav2letter | 4,132,806 | 85.2 % | 96.8 % | 82.5 % | 0.968 | 1.4 % | 72.1 % | 0.011 | 2.0 / 7.2 | 1.0 % | 0.79 | 0.87 |

\* Reserved-ID 이벤트. 의미는 드라이버 상태 비트에서 추론했다(`evidence/stage2a/event_semantics_audit.md`). 탐색용이다.
vww4의 WD active는 `CONDITION_SPECIFIC`이다. MAC active-cycle eff. = N_MAC / (1024 × mac_active),
peak MAC eff. = N_MAC / (1024 × NPU_ACTIVE).

### 1.2 현상 (모델 수준의 연관성, 원인 미확정)

1. **MAC 활동 비중의 폭이 넓다.** NPU_ACTIVE 중 MAC 활동 비중은 rnnoise 1.1 %부터 wav2letter 85 %까지다.
   1024-MAC 기준 효율도 wav2letter 82.5 %에서 rnnoise 0.2 %까지 퍼진다.
2. **MAC이 활동한 사이클 안에서도 효율이 낮은 모델이 있다.**
   - kws 27 %, yolo 22 %, vww4 33 %, rnnoise 16 %.
   - vww4·yolo는 Vela block fill이 0.84–0.89로 높은데도 효율이 낮다. block fill로는 설명되지 않는다.
   - kws는 block fill(0.53)과 효율이 함께 낮다(같은 방향일 뿐, 인과는 미확인).
3. **AO가 MAC보다 오래 활동하는 모델이 있다:** yolo(46 % vs 38 %), vww4(27 % vs 24 %).
4. **DPU/MAC 비율이 모델마다 다르다(0.75–1.00).** 단일 연산 Stage 2A의 1.000과 달리 모델에서는 정보를 담는다.
   이 비율은 활동 카운터 사이의 관계이며 점유율이 아니다(4C-2 보충 참고).
5. **메모리 접근.**
   - EXT 읽기 요청 stall은 포트-사이클의 6–18 %(wav2letter 18 %)다. SRAM 읽기 요청 stall은 ≤ 0.6 %다
     (`RETAINED`: 여섯 모델은 기존 경로 값이 유지되고 한 모델만 재측정으로 `REVALIDATED`).
   - outstanding-limit stall은 0이거나 거의 0이다. 따라서 TA가 흉내 낸 EXT 지연이 후보지만, 시험하지 않았다.
   - SRAM 대역폭은 최대 15.2 B/cycle(yolo)로, 두 포트 합계 32 B/cycle의 약 절반이다.
   - bytes/MAC은 wav2letter 0.011(가중치 위주)에서 rnnoise 1.5(작은 모델)까지다.
   - 측정 바이트는 모든 모델에서 Vela 추정보다 적다.
   - EXT 포트 0/1 분배·EXT read burst는 경로에 따라 달라서 `CONDITION_SPECIFIC` 또는 `REMEASURE_REQUIRED`이며, 여기서 쓰지 않는다.
6. **단위 stall** (Reserved ID, 탐색용):
   - MAC stalled by IB가 depthwise 비중이 큰 모델(mobilenet 33 %, yolo 34 %, vww4 28 %)에서 높고, wav2letter에서 낮다(1 %).
   - WD stalled by WD buffer는 Conv 모델 43–65 %(`RETAINED`)이고 rnnoise는 0.4 %다.
   - CC blockdep stall은 vww4 52 %, rnnoise 41 %, yolo 35 %로 높다(대부분 `RETAINED`, 일부 모델 `REMEASURE_REQUIRED`).
   - stall들은 겹칠 수 있으므로 더해서 "총 stall 시간"으로 쓰지 않는다.
7. **Vela와 보드.** ACTIVE ÷ Vela `cycles_npu`는 rnnoise 1.62(보드가 더 느림), mobilenet 0.83, wav2letter 0.79(보드가
   더 빠름)이고 나머지는 0.94–1.06이다. 이 비율은 범위가 다른 두 양의 비이며 Vela의 오차로 읽지 않는다.
8. **고정 비용.** Driver Runner 창은 NPU_ACTIVE보다 모델과 무관하게 534–666 사이클 길다(m7).

이 현상들은 모델 수준의 연관성이다. 어느 연산이 만들었는지는 Stage 2B에서 정하려 했으나 실패했다(§3.2).

---

## 2. 통제 실험에서 확인한 영향 (Stage 4·4C·5)

조건: Driver Runner `83398c7`, Pass A(Stage 1 세트 A) + Pass B(Stage 3 세트 B), RUN당 warm-up 1 + 측정 4. 쌍 판정은
tol = max(base의 1 %, 두 RUN 범위 중 큰 값)이며, Pass A가 주 판정이고 Pass B는 확인용이다(방향이 반대면 `UNRESOLVED`).
출력은 모든 구성에서 PASS_EXACT였다(독립 연산은 CPU 기준, kws·ad는 MLEK FI101 golden과 바이트 일치).

### 2.1 연산 종류 (Stage 4, 독립 연산, 입출력 DRAM)

| | Conv 1×1 16→96 @24×24 | DWConv 3×3 144 @56×56 | FC 96→288 |
| --- | ---: | ---: | ---: |
| MACs per MAC-active cycle | 384 | 128 | 256 |
| ÷ 문서상 클래스 최대치(TRM Table 7) | 0.375 (CONV 1024) | **1.00** (DW 128) | 표에 없음 |
| MAC_ACTIVE ÷ NPU_ACTIVE | 10.9 % | 19.9 % | 1.15 % |
| WD_STALLED ÷ NPU_ACTIVE | 33 % | 98 % | 36 % |

- DWConv는 MAC 활동 중 클래스 최대치로 돌았다. 1024 기준의 낮은 값(0.125)은 클래스 최대치 때문이며, 매핑 실패가 아니다.
- 세 독립 연산 모두 NPU_ACTIVE의 대부분이 MAC 활동 밖에 있었다.
- FC는 가중치 읽기, DW는 DRAM 입출력 전송이 실행을 지배할 수 있다는 것은 `HYPOTHESIS`다. 시간 분해는 측정하지 않았다.

### 2.2 채널 정렬 (Stage 4, 4C-1)

- **채널 하나를 줄여도 MAC_ACTIVE는 같았다**(Conv Cin 15, Cout 95, DW 143, FC in 95, FC out 287; 다섯 쌍 모두 사이클 단위로 동일).
- **NPU_ACTIVE는 일부만 변했다.**
  - Conv Cout 95: +7.0 % / +10.4 %. DW 143: +6.1 % / +6.1 %. 두 경우 모두 EXT write beat가 +93 % 늘었다(`OBSERVED`, 인과 미확인).
  - FC out 287: 두 Pass에서 재현되지 않았다(−9.5 % / +0.9 %).
- **출력 쓰기 beat 규칙 A**(16-byte 정렬 기반, Stage 4 §6.1 사후 가설)가 새 채널 4개(Conv 94·97, DW 142·145)에서 측정 전
  예측과 모든 RUN이 맞았다. 구현 메커니즘과 시간 증가와의 인과는 `UNVERIFIED`다.
- **DWConv MAC_ACTIVE**는 C를 16의 배수로 올림한 양과 맞았다(142–144 → 31,752, 145 → 35,280 = ×10/9). `POST_HOC_DESCRIPTIVE`이며,
  이 shape에 한한다.

### 2.3 처리 구성 (4C-1, 4C-2, 4C-2b)

- **ublock 변경 (Conv Cout 96 → 97):**
  - Vela가 OFM ublock을 2×2×32에서 2×4×16으로 바꿨다.
  - MAC_ACTIVE는 2,304 → 2,016으로 줄었고, MACs per active cycle은 +15.5 % 올랐다.
  - 그런데 NPU_ACTIVE는 +23 % / +25 % 늘었다(EXT write ×2.1, AO_ACTIVE +17 %).
  - MAC_ACTIVE ÷ OFM ublock = Conv 4.0, DW 9.0 (Cin 16에서 읽은 사후 기술).
- **입력 채널 (Conv 1×1, Cin 16/32/64/128):**
  - 같은 처리 구성 안에서는 MAC_ACTIVE가 MAC 수에 정확히 비례했다(16→32, 64→128 모두 ×2).
  - 32 → 64에서 traversal(PartKernel → DepthFirst), IFM block 깊이(16 → 64), weight order가 함께 바뀌었다.
    MAC_ACTIVE는 같았고(4,608), MACs per active cycle은 384에서 768로 두 배가 되었다. NPU_ACTIVE는 −5.6 % / −4.9 %.
  - 같은 구성 안에서 MAC이 두 배가 되어도 NPU_ACTIVE는 +19 %·+27 %만 늘었다. MAC 비중은 올라갔다.
  - 세 설정 가운데 무엇이 원인인지는 분리하지 않았다.
- **DepthFirst의 Cin 40 (4C-2b):**
  - MAC_ACTIVE = 3,456으로 Cin 48과 같았다. 네 가설 중 "16의 배수로 올림"(H4)만 맞았다.
  - DPU/MAC = 1.0인데도 MACs per DPU-active cycle은 640(Cin 48·64는 768)이었다. DPU/MAC 비율이 1이라고 실효 처리량이 같은 것은 아니다.

### 2.4 SRAM 작업공간 예산 (Stage 5-1)

**5-0 분류에서 모든 5-1 비교는 `SCHEDULE_CHANGED`였다.** 따라서 결과는 SRAM 배치만의 효과가 아니라, 예산에 따라
Vela가 만든 실행 구성 전체의 효과다.

| workload | 384 KiB (기준) | 64 KiB | 0 |
| --- | --- | --- | --- |
| kws | 91,770 | +5.4 % / +6.6 % (kernel 14 → 19) | **+24.2 % / +25.4 %** |
| ad | 145,991 | **+158 % / +158 %** (kernel 14 → 66) | +61 % / +60 % |
| dw_base | 159,780 | (payload 동일, 측정 안 함) | +0.5 %, `UNRESOLVED` |
| conv_base | 21,587 | (payload 동일, 측정 안 함) | `UNRESOLVED`; MAC_ACTIVE 2,304 → 1,728 (kernel 2 → 1) |

- kws·ad의 MAC_ACTIVE는 거의 그대로였다(kws −3 사이클, ad −2.5 % … +1.2 %). 그런데 NPU_ACTIVE는 늘었다.
- **ad는 64 KiB에서 0보다 더 느렸다(×2.58).** 예산과 실행 비용은 단순 비례 관계가 아니었다.
- 예산이 줄면 전송이 EXT로 옮겨 갔다(예산 0에서 SRAM beat 0, EXT 읽기 kws ×2.3, ad ×2.6, 모델은 EXT 쓰기 발생).
  kernel 수 증가, EXT 전송 증가, 시간 증가는 함께 일어났지만 각각의 인과적 기여는 확정하지 않았다.
- Conv·DW의 `UNRESOLVED`는 이 조건에서 차이를 판정하지 못했다는 뜻이며, SRAM이 필요 없다는 뜻이 아니다.

### 2.5 최적화 전략 Performance vs Size (Stage 5-2)

요청 예산은 두 전략 모두 384 KiB였다. 5-0에서 세 workload 모두 `MEMORY_ONLY`였다(kernel별 계산 구성은 같고, 가중치 stream·배치만 다름).

| workload | SRAM 사용 Performance → Size | NPU_ACTIVE Δ A / Δ B | 판정 | MAC_ACTIVE | 전송 변화 (Pass B) |
| --- | --- | --- | --- | --- | --- |
| kws | 89.5 → 89.5 KiB | +0.38 % / +0.26 % | `UNRESOLVED` | 56,450 → **57,055** (DPU 같음) | 없음 |
| ad | 244.0 → **300.8 KiB** | −0.79 % / −1.12 % | `UNRESOLVED` | 같음 | SRAM 읽기 +10 %, SRAM 쓰기 +9 %, EXT 읽기 −9 % |
| conv Cin 64 | 8.4 → 9.3 KiB | +0.37 % / +0.48 % | `UNRESOLVED` | 같음 | SRAM 읽기 +11 %, EXT 읽기 transaction −22 % |

- 세 쌍 모두 전체 실행 비용의 차이가 판정되지 않았다(허용폭 안, 두 Pass 같은 방향). 두 전략이 같다는 뜻은 아니다.
- Size는 SRAM을 같거나 더 많이 썼다. 이름으로 "SRAM을 덜 쓴다"고 읽지 않는다.
- ad·Cin 64에서는 전송이 EXT에서 SRAM으로 일부 옮겨 갔다. 하지만 시간 변화로는 나타나지 않았다.
- kws Size의 MAC_ACTIVE는 모든 RUN에서 정확히 +605(+1.07 %)였다. 계산 레지스터는 같고 두 kernel의 가중치 stream 길이만
  달랐다. 이유는 확인하지 않았다(`OBSERVED`).
- Vela의 구성별 MAC 집계(kws Size 15.58 M)는 효율 계산에 쓰지 않는다. 유효 MAC은 원본 정의(14.21 M)다.
- mobilenet(`SCHEDULE_CHANGED`인 Size 사례)은 측정하지 않았다(`UNMEASURED`).

### 2.6 여러 실험에 걸친 공통점

1. **MAC 활동과 전체 실행 비용은 따로 움직였다.**
   - MAC 효율이 좋아졌는데 전체 비용이 늘었다: Conv 97(+15.5 % vs +23 %).
   - MAC 활동이 줄었는데 전체 비용은 판정되지 않았다: conv 예산 0(MAC_ACTIVE −25 %, NPU_ACTIVE `UNRESOLVED`).
   - MAC 활동은 그대로인데 전체 비용이 늘었다: Cout 95, DW 143, kws·ad의 예산 축소.
   - 둘이 함께 좋아진 경우: Cin 32 → 64.
   - 계산 레지스터가 같은데 MAC_ACTIVE만 바뀌었고, 전체 비용은 판정되지 않았다: kws Size(+605).
   - 전송 경로는 바뀌었는데 MAC과 전체 비용은 그대로였다: ad·Cin 64 Size.
   - 그러므로 MAC_ACTIVE만으로 실행 시간을 설명하지 않으며, 두 값은 항상 따로 보고한다.
2. **MAC_ACTIVE는 결정적이었다.** 측정한 모든 독립 연산 구성에서 RUN 범위가 0이었다. NPU_ACTIVE는 RUN마다 수백–수천 사이클 흔들렸다.
3. **처리 구성이 바뀌면 같은 계산도 다른 비용을 낸다.** ublock, traversal, kernel 분할, SRAM 예산이 모두 Vela의 선택을 통해 결과를 바꿨다.
   하나의 설정만 바꾼 비교는 거의 없었다. 대부분은 `SCHEDULE_CHANGED` 또는 여러 설정이 함께 바뀐 비교다.
4. **Vela 추정이 보드 변화를 따라가지 않은 경우가 있다.**
   - Cout 95·DW 143: Vela 변화 ≤ 1 %, 보드 +6–10 %.
   - Cin 15: Vela는 메모리 비용 2.5×를 예상했으나 보드에서는 나타나지 않았다.
   - 5-1: 방향은 같았으나 폭이 달랐다(ad 64 KiB: Vela ×3.0, 보드 ×2.58).
   - 5-2: kws Size에서 Vela는 +4.0 %를 예상했으나 보드 차이는 판정되지 않았다.

---

## 3. 아직 설명하지 못한 부분

### 3.1 원본 모델과의 연결 수준

- **Stage 4·4C는 원본 모델 안의 연산이 아니다.**
  - 독립 연산이고, 그래프 입출력이 DRAM에 있다. 원본 모델에서는 같은 층의 feature map이 SRAM에 있었고, cascade 안에 있던 연산도 있다.
  - 그러므로 "모델 안에서 DW가 비싸다"나 "Conv가 몇 사이클" 같은 연산별 비용으로 옮기지 않는다.
- **Stage 5는 kws·ad(와 독립 연산)에서만 측정했다.** 다섯 모델의 예산·전략 효과는 `UNMEASURED`이며 일반화하지 않는다.
- **Stage 1 현상 중 통제 실험으로 설명되지 않은 것:**
  - vww4·yolo가 block fill이 높은데도 MAC active-cycle 효율이 낮은 이유.
  - depthwise 비중이 큰 모델의 높은 MAC stalled by IB.
  - rnnoise의 보드 ÷ Vela 1.62.
  - AO가 MAC보다 오래 활동하는 이유(yolo, vww4).
- **채널 올림과 ublock padding이 모델 효율을 얼마나 깎는지는 측정하지 않았다.**
  - 4C에서 본 "16의 배수 올림"과 ublock 선택이 kws의 낮은 효율과 관련이 있을 수 있다(`HYPOTHESIS`).
  - 모델의 연산 shape에 대해 확인하지 않았다.

### 3.2 그룹·연산별 귀속의 한계

- **Stage 2B-2 (PMU Mask 그룹 창):**
  - 창은 command stream 해석 위치를 따라가며, 실행을 따라가지 않는다.
  - ad CONV 그룹의 MAC 효율이 2.845로 계산되었다. 불가능한 값이다.
  - 그러므로 그룹별 비율과 H1/H2는 연산 종류에 대한 진술이 아니다. **H1/H2는 계속 무효다.**
- **Stage 2B-3:** yolo Op 99/100 창은 `WINDOW_AMBIGUOUS`였다. MAC 활동이 앞뒤 창으로 갈렸다.
- **QREAD 파일럿 (원본 stream 유지):**
  - 결과는 P1 `TRACE_RECOVERED`, P2 `BOUNDARY_OBSERVED`, P3 `NOT_ASSOCIATED`다.
  - 경계 통과 시점의 범위는 보였다. 하지만 PMU 판독 비용(297 → 642 cycles) 때문에 경계 해상도가 사전 기준을 넘었다.
  - 관측된 간격(약 1.82–1.84k CPU cycles)은 연산 실행시간이 아니다.
- **현재 방법으로는 원본 모델의 연산별 시작·종료 시각, 연산별 실행시간, PMU 이벤트의 연산 귀속을 얻지 못했다.**
  독립 연산 결과나 구성 비교로 이를 복원하지 않는다.

### 3.3 NPU_ACTIVE의 비-MAC 부분

- MAC 활동 밖의 NPU_ACTIVE 비중: Stage 4 독립 연산 80–99 %(4C의 Conv Cin 128은 70 %), 모델 15–99 %.
- 그 부분이 무엇으로 이루어지는지(전송 대기, 가중치 디코드, AO, 명령 처리, 동기화)는 측정으로 나누지 못했다.
- 전송 증가와 시간 증가가 함께 일어난 경우는 많지만(Stage 4, 4C-1, 5-1), 대역폭이나 메모리 대기로 배정하지 않았다.
- TA 에뮬레이션 아래의 값이므로 실제 DRAM에서의 크기는 다를 수 있다.

### 3.4 남은 조건·검증 공백

- wav2letter M4(MAC/DPU/AO 동등성)는 `UNPROVEN`이다. 교차 재확인(`NO_SHIFT`)은 따로 기록되어 있고, 판정에 합치지 않는다.
- 입력은 MLEK 입력 하나뿐이다. 다른 입력으로 일반화하지 않는다.
- 4C 결과는 각 구성당 한 부팅이다. 부팅 간·입력 간 재현성은 주장하지 않는다.
- Stage 1 문서는 vww4·yolo·wav2letter OFM을 tflite 대비로 주장하지 않았다(`UNRESOLVED (x1)`). Driver Runner m7에서는
  일곱 모델 모두 출력이 MLEK와 같았다(M1).

### 3.5 중요한 추가 검증 후보 (제안만; 계약·승인 전 보드 실험 없음)

| 우선 | 질문 | 근거 | 가장 작은 다음 단계 |
| --- | --- | --- | --- |
| 1 | ad 64 KiB가 왜 0보다 느린가 (×2.58) | 5-1, `SCHEDULE_CHANGED`, kernel 14 → 66 | 컴파일 산출물에서 kernel별 구성·전송 비교(보드 없음) → 필요하면 구성 하나씩 바꾼 비교 |
| 2 | MAC 활동이 그대로거나 좋아졌는데 전체 비용이 늘어나는 부분은 무엇인가 | Conv 97, Cout 95, DW 143, kws·ad 예산 | 같은 구성에서 MAC 외 단위의 활동·stall을 시간 분해 없이 비교하는 계약 |
| 3 | 모델의 MAC active-cycle 효율이 낮은 것을 채널 올림·ublock padding이 얼마나 설명하는가 | Stage 1 kws·yolo·vww4, 4C의 올림 관계 | Vela 산출물로 모델 연산별 정적 계산(보드 없음), 관계가 유지되는지만 확인 |
| 4 | depthwise 비중 모델의 MAC stalled by IB | Stage 3 | Reserved-ID 의미 확인이 먼저 필요 |
| 5 | rnnoise 보드 ÷ Vela 1.62 | Stage 1 | 구성 확인(보드 없음) |
| 6 | 계산 레지스터가 같은데 MAC_ACTIVE가 바뀐 이유 (kws Size +605) | 5-2 | 두 kernel의 가중치 stream 차이를 산출물로 비교(보드 없음) |

연산별 시간 귀속(2B H1/H2의 재구성)은 현재 방법으로는 후보에서 뺀다. 새 방법 없이는 다시 시도하지 않는다.

---

## 출처

| 내용 | 문서 |
| --- | --- |
| Stage 1 | `results/fi101_stage1/README.md` (main 브랜치 쪽 원본 데이터 `evidence/fi101_s013/`) |
| Stage 2A | `results/fi101_stage2a/README.md` |
| Stage 3 | `results/fi101_stage3/README.md`, `results/fi101_stage3_channels/` |
| 재검증 | `results/driver_m7/README.md`, `results/driver_m7/reval/reval.csv`, `docs/plan/reference_environment.md` |
| Stage 2B | `results/fi101_stage2_groups/README.md`, `results/fi101_stage2b3/README.md`, `results/qread_op_pilot/FINAL.md` |
| Stage 4 | `results/fi101_stage4/stage4_analysis.md`, `results/fi101_stage4c1/README.md`, `results/fi101_stage4c2/README.md`, `results/fi101_stage4c2b/README.md` |
| Stage 5 | `results/fi101_stage5/README.md`, `results/fi101_stage5_2/README.md` |
