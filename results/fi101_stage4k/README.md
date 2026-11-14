# Stage 4K — Conv 1×1·3×3 MAC 활동 (boot 369–378, 2026-11-14 UTC 보드 시계)

이 결과는 계약 `evidence/stage4k/contract.md`(동결 `fe2f7aa`, boot 369 전)에 따른 것이다.
- **측정 조건:**
  - FI101 Ethos-U85 1024 MAC, **TA profile 1**(MLEK sys_dram_mid, boot마다 capabilities로 확인).
  - Driver Runner 이미지 `70090f1`(boot `718c4562`, bram `c80e77df`), DDR/EXT 배치(REGIONCFG 0x15F).
  - Vela 5.0.0과 MLEK 옵션, WAIT_WFE.
  - 24×24, Cout 96, stride 1, SAME, RELU6, INT8.
- **측정 규모:** pass A·B × (warm-up 1 + 측정 4) × 10 구성 = **100 RUN**.
- **원시 데이터:** `evidence/stage4k/raw/`(sha256 목록 `evidence/stage4k/raw.sha256`, 보드 원본과 일치).
- **분석 산출물:** `python3 host/analysis/stage4k.py judge evidence/stage4k/raw/evsweep_s4k_run evidence/stage4k/workloads results/fi101_stage4k/predictions.json results/fi101_stage4k`로 `summary.json`과 `stage4k_table.csv`를 만들었다.
- **정적 분석:** `docs/plan/stage4k_conv_kernel_plan.md`, `static.json`, `stage4k_static.csv`, `prior.json`, `predictions.json`.

## 1. 실행과 Gate

| 단계 | 결과 (세션 로그 `raw/evsweep_s4k/session.txt.log`과 원시 파일로 확인) |
| --- | --- |
| G0 | 이미지·워크로드 48개 파일 sha256 일치, 15개 DRWL word 7 = 0, PMU 세트·조건 Stage 4와 같음, 보드 쪽 gate 명령 dry run PASS (`evidence/stage4k/board/g0.txt`) |
| G1 (boot 369) | `repro-gate` PASS: MAC 2,304·DPU 1,152(4/4 RUN), 출력 sha256 같음, 공통 상수 카운터 같음, NPU_ACTIVE 21,629 vs 21,086.5(차이 542.5 ≤ tol 968) |
| G2 (boot 369–378) | 10/10 `boot-check` PASS: **PASS_EXACT**, RUN 10/10 유효, refusal 없음, 정체성(model_len, schema 4, placement 0, REGIONCFG 0x15F/QCONFIG 3, IRQ 1, warm-up 포함 CRC 하나, capabilities = boot 367) |
| 보조 재현 | 1×1 다섯 개 모두 `REPRODUCED`: 기존 `83398c7` 측정(boot 330, 344–346, 348–350)과 MAC·DPU·출력·상수 카운터 같음, NPU_ACTIVE 허용폭 안 |
| 종료 | `RESTORE VERIFIED`(m6 digest가 이전 복원과 같음), postflight PING state 1, `card withdrawn`, 카드 미마운트 확인 |

## 2. 결과 (측정 4회 중앙값, pass A; MAC_ACTIVE·MAC_DPU_ACTIVE는 모든 구성에서 RUN range 0)

| K | Cin | 전략 | MAC_ACTIVE | MAC_DPU | DPU/MAC | nominal MAC / MAC_ACTIVE | valid MAC / MAC_ACTIVE | NPU_ACTIVE (range) | nominal / NPU_ACTIVE | valid / NPU_ACTIVE | MAC_ACTIVE / NPU_ACTIVE | 1024 대비 (MAC_ACTIVE / NPU_ACTIVE) | 가설 판정 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| 1×1 | 16 | PartKernel | 2,304 | 1,152 | 0.5 | 384 | 384 | 21,629 (968) | 40.9 | 40.9 | 0.107 | 37.5 % / 4.0 % | R384 (4개 일치, 구분 불가) |
| 1×1 | 32 | PartKernel | 4,608 | 2,304 | 0.5 | 384 | 384 | 25,470 (695) | 69.5 | 69.5 | 0.181 | 37.5 % / 6.8 % | R384 (4개) |
| 1×1 | 40 | DepthFirst | 3,456 | 3,456 | 1.0 | 640 | 640 | 21,927.5 (866) | 100.9 | 100.9 | 0.158 | 62.5 % / 9.9 % | **R768_c16** (+valid_c16) |
| 1×1 | 48 | DepthFirst | 3,456 | 3,456 | 1.0 | 768 | 768 | 22,251 (154) | 119.3 | 119.3 | 0.155 | 75 % / 11.6 % | R768 (4개) |
| 1×1 | 64 | DepthFirst | 4,608 | 4,608 | 1.0 | 768 | 768 | 24,257 (931) | 145.9 | 145.9 | 0.190 | 75 % / 14.2 % | R768 (4개) |
| 3×3 | 16 | PartKernel | 10,368 | 10,368 | 1.0 | **768** | 725.9 | 22,777 (1,103) | 349.6 | 330.4 | 0.455 | 75 % / 34.1 % | R768_nominal+c16 |
| 3×3 | 32 | PartKernel | 20,736 | 20,736 | 1.0 | 768 | 725.9 | 30,494.5 (309) | 522.2 | 493.6 | 0.680 | 75 % / 51.0 % | R768_nominal+c16 |
| 3×3 | 40 | PartKernel | **25,920** | 25,920 | 1.0 | 768 | 725.9 | 37,635 (1,673) | 528.9 | 500.0 | 0.689 | 75 % / 51.7 % | **`MATCH:R768_nominal`** (단독) |
| 3×3 | 48 | PartKernel | 31,104 | 31,104 | 1.0 | 768 | 725.9 | 40,156 (267) | 594.9 | 562.3 | 0.775 | 75 % / 58.1 % | R768_nominal+c16 |
| 3×3 | 64 | PartKernel | 41,472 | 41,472 | 1.0 | 768 | 725.9 | 55,015 (2,012) | 578.9 | 547.2 | 0.754 | 75 % / 56.5 % | R768_nominal+c16 |

**MAC 정의와 지표의 성격.**
- nominal = H·W·Cout·k²·Cin(padding 탭 포함, = Vela MAC 수)이다.
- valid = 범위 안의 탭만 센 값으로, 3×3에서는 nominal × 0.9452이다.
- "1024 대비"는 구성 MAC/CC(1024)에 대한 비율이다. Conv 전용 공식 peak가 아니며, 이 값은 확보하지 못했다.
- MAC_ACTIVE / NPU_ACTIVE는 활성 비율이다. 유효 MAC / MAC_ACTIVE는 활성 사이클당 처리량이다. 둘은 다른 지표다.

**RELU6 포화(기록만).**
- OFM scale은 10개 모두 base와 같고, cap은 120이다.
- NPU 출력의 cap 값 개수(55,296 중):
  - 1×1: 1 / 39 / 116 / 244 / 637.
  - 3×3: 3,271 / 7,422 / 8,924 / 10,066 / 12,046 (5.9–21.8 %).
- CPU reference와 같은 값이다. 포화를 MAC 계산 생략의 근거로 쓰지 않는다.

## 3. 판정 (`summary.json`, 동결 규칙)

**RQ1 — 커널 크기 (같은 Cin, nominal MAC / MAC_ACTIVE).**

| Cin | 1×1 | 3×3 | 판정 | 비교 가능성 |
| ---: | ---: | ---: | --- | --- |
| 16 | 384 | 768 | `RATE_3X3_HIGHER` (×2.0) | `SAME_TRAVERSAL_BLOCKS_DIFFER` |
| 32 | 384 | 768 | `RATE_3X3_HIGHER` (×2.0) | `SAME_TRAVERSAL_BLOCKS_DIFFER` |
| 40 | 640 | 768 | `RATE_3X3_HIGHER` (×1.2) | `TRAVERSAL_DIFFERS` |
| 48 | 768 | 768 | `SAME_RATE` | `TRAVERSAL_DIFFERS` |
| 64 | 768 | 768 | `SAME_RATE` | `TRAVERSAL_DIFFERS` |

- Cin 16·32에서 두 구성은 같은 PartKernel이고 IFM block 깊이도 16으로 같다.
- 그런데 3×3은 MAC 활성 사이클당 768, 1×1은 384였다.
- 다만 OFM block(6×12×96 vs 24×10×32), weight 크기, 커널 탭 수가 함께 다르다. 그래서 이 차이를 커널 크기 하나의 효과로 확정하지 않는다.

**RQ2 — 채널 단위.**
- 3×3: `PROPORTIONAL_TO_CIN`.
  - MAC_ACTIVE 10,368 / 20,736 / 25,920 / 31,104 / 41,472 = nominal/768로, Cin에 정확히 비례한다.
  - **Cin 40 ≠ Cin 48**이다. Cin 40은 사전 가설 8개 중 `R768_nominal`에만 일치했다. 16채널 올림 가설(31,104)과 padding 탭 제외 가설(24,500)은 기각됐다.
- 1×1: `NEITHER`.
  - 두 전략에 걸친 집합이라 하나의 규칙으로 판정되지 않는다.
  - 전략별로 보면 다음과 같다. PartKernel(16, 32)은 Cin에 비례한다. DepthFirst(40, 48, 64)는 Cin 40 = 48로, 16채널 올림과 부합한다(4C-2b 재현).
- **해석 범위.**
  - "1×1에서 본 16채널 계단은 이번 3×3(PartKernel, IFM block 16)에서는 나타나지 않았다"까지만 말할 수 있다.
  - 계단의 원인이 DepthFirst / IFM block 64 / weight order / 1×1 중 무엇인지는 분리되지 않는다. 이 세 요소와 커널 크기가 함께 다르기 때문이다.

**RQ3 — 컴파일러 전략.**
- 3×3 다섯 점은 traversal(PartKernel)과 block 구성이 고정된 비교다. 여기서 처리율은 768로 일정했다.
- 1×1에서는 처리율이 PartKernel 384에서 DepthFirst 640/768로 바뀌었다.
- 따라서 **"PartKernel = 384"는 1×1에 한한 관측이다.** 같은 PartKernel이라도 3×3에서는 768이었다.
- 처리율을 바꾼 요인은 이번 데이터로 하나로 확정하지 않는다. 후보는 다음과 같다.
  - OFM block 깊이(96 vs 32).
  - k²·Cin에 따른 PartKernel의 depth 묶음.
  - weight order.
- 1×1의 PartKernel→DepthFirst 전환과 처리율 변화는 4C-2·4C-2b와 같게 재현됐다.

**RQ4 — 계산 활동과 실행 비용 (Stage 4 pair 규칙; 10쌍 모두 pass B 방향 같음).**

| 쌍 | MAC 수 | MAC_ACTIVE | NPU_ACTIVE pass A (pass B) | 판정 |
| --- | --- | --- | --- | --- |
| 1×1 16→32 | ×2 | ×2 | +17.8 % (+20.8 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1 32→40 | ×1.25 | ×0.75 | −13.9 % (−15.1 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1 40→48 | ×1.2 | ×1.0 | +1.5 % (+4.5 %) | `UNRESOLVED` (tol 866 안) |
| 1×1 48→64 | ×1.33 | ×1.33 | +9.0 % (+7.8 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 3×3 16→32 | ×2 | ×2 | +33.9 % (+36.1 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 3×3 32→40 | ×1.25 | ×1.25 | +23.4 % (+22.4 %) | `CONSISTENT_WITH_MAC_CHANGE` |
| 3×3 40→48 | ×1.2 | ×1.2 | +6.7 % (+7.4 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 3×3 48→64 | ×1.33 | ×1.33 | +37.0 % (+40.7 %) | `CONSISTENT_WITH_MAC_CHANGE` |
| 1×1→3×3, Cin 16 | ×9 | ×4.5 | +5.3 % (+6.2 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1→3×3, Cin 32 | ×9 | ×4.5 | +19.7 % (+19.5 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1→3×3, Cin 40 | ×9 | ×7.5 | +71.6 % (+72.3 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1→3×3, Cin 48 | ×9 | ×9 | +80.5 % (+77.1 %) | `NOT_PROPORTIONAL_TO_MAC` |
| 1×1→3×3, Cin 64 | ×9 | ×9 | +126.8 % (+131.0 %) | `NOT_PROPORTIONAL_TO_MAC` |

- MAC 처리율이 같거나 높아도 NPU_ACTIVE가 줄지 않는 조건이 있다.
  - 3×3 16→32: 처리율은 768로 같고, MAC_ACTIVE가 ×2일 때 NPU_ACTIVE는 +34 %였다.
  - 1×1 40→48: 처리율이 640→768로 올랐지만 NPU_ACTIVE는 판정되지 않았다(`UNRESOLVED`).
- 반대로, 처리율이 오르면서 비용이 준 경우도 있다(1×1 32→40, 4C-2의 32→64와 같은 방향).
- MAC_ACTIVE / NPU_ACTIVE는 1×1이 0.11–0.19, 3×3이 0.46–0.78이다.
- NPU_ACTIVE − MAC_ACTIVE를 무엇으로 채웠는지는 측정하지 않았다. 메모리 대기로 배정하지 않는다.

**RQ5 — 이론 처리율과의 차이.**
- MAC 활성 사이클 기준 상한: 이번 10개에서 nominal MAC / MAC_ACTIVE는 384, 640, 768 세 값뿐이다(1024 대비 37.5 / 62.5 / 75 %). 1024에 도달한 구성은 없다.
- 전체 실행 기준: 3×3 Cin 48이 가장 높았다(nominal 594.9 / NPU_ACTIVE cycle = 58.1 %, valid 기준 54.9 %). 1×1은 모두 15 % 아래였다.
- 경계 padding: MAC_ACTIVE는 padding 탭을 **포함한** nominal 양과 정확히 맞았다(`R768_valid*` 기각).
  - 그래서 valid MAC 기준 처리율은 725.9(70.9 %)로, nominal보다 5.5 % 낮다.
  - 이것은 MAC 활성 사이클이 padding 위치를 포함한 양과 부합한다는 뜻이다. 0 탭을 실제로 곱했다는 증거는 아니다.

## 4. 주변 처리부와 전송량 (보조, 원인 배정 없음)

| K | Cin | weight B | AO_ACTIVE | WD_ACTIVE | WD_STALLED (range) | EXT rd beat (386) | EXT wr (391) | SRAM rd (130) | SRAM wr (135) | EXT rd trans (384) | 53 / 55 (TRM 목록 밖) |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1×1 | 16 | 2,752 | 3,540.5 | 1,052 | 6,402 (1,252) | 1,437 | 3,456 | 2,016 | 252 | 171 | 0 / 4,849 |
| 1×1 | 32 | 4,928 | 3,533 | 1,762 | 17,838 (900) | 2,725 | 3,456 | 3,104 | 388 | 2,339 | 0 / 12,881.5 |
| 1×1 | 40 | 4,992 | 3,530 | 1,670 | 8,962.5 (502) | 3,305 | 3,456 | 3,136 | 392 | 300 | 0 / 7,373 |
| 1×1 | 48 | 5,760 | 3,533 | 1,781 | 9,748 (504) | 3,929 | 3,456 | 3,520 | 440 | 327 | 0 / 8,603 |
| 1×1 | 64 | 7,296 | 3,538 | 1,954 | 13,062.5 (716) | 5,177 | 3,456 | 4,288 | 536 | 429 | 0 / 11,020.5 |
| 3×3 | 16 | 16,432 | 3,562.5 | 1,886 | 13,205.5 (68) | 2,484 | 3,456 | 3,321 | 1,107 | 296 | 0 / 943.5 |
| 3×3 | 32 | 32,800 | 3,529.5 | 3,802 | 22,271 (96) | 4,851 | 3,456 | 6,390 | 2,130 | 2,832 | 0 / 5,527 |
| 3×3 | 40 | 42,240 | 3,484.5 | 5,224 | 28,519 (1,158) | 8,129 | 3,456 | 8,160 | 2,720 | 4,309 | 1 / 7,911 |
| 3×3 | 48 | 49,104 | 3,507.5 | 5,768 | 30,697.5 (211) | 7,214 | 3,456 | 9,447 | 3,149 | 4,240 | 0 / 5,551.5 |
| 3×3 | 64 | 65,424 | 3,524.5 | 7,637 | 43,080.5 (1,132) | 10,682 | 3,456 | 12,507 | 4,169 | 6,752 | 0 / 9,435.5 |

- **AO_ACTIVE**는 10개 구성 모두 약 3,485–3,563이다. 커널·Cin·MAC 수와 무관하게 거의 일정하다. 10개 모두 OFM(24×24×96)이 같다.
- **WD_ACTIVE**는 weight 크기와 함께 늘었다.
  - POST_HOC_DESCRIPTIVE: weight B / WD_ACTIVE는 3×3에서 8.1–8.7, 1×1에서 2.6–3.7이다.
- **WD_STALLED**는 3×3에서 13,206–43,081이다. NPU_ACTIVE와 같은 방향으로 늘었다.
  - 이 값을 병목 시간으로 환산하지 않는다. 지연 원인으로 특정하지도 않는다.
- **EXT wr beat**는 3,456으로 10개 모두 같다(OFM 같음).
- **EXT rd·SRAM rd/wr beat**는 weight와 IFM 양에 따라 늘었다.
  - 3×3의 SRAM wr(1,107–4,169)는 1×1(252–536)보다 크다.
  - 무엇을 쓴 것인지(가중치 staging 등)는 이 이벤트만으로 확정하지 않는다.
- **이벤트 53·55**는 TRM 110 목록 밖이다. 보고만 하고 결론에 쓰지 않는다.

## 5. 해석 한계

- 형상은 한 가지 family(24×24, Cout 96, stride 1)이고, Cin은 5개, 구성마다 boot 1회다. 순서는 1×1→3×3 고정이며 순서 효과는 통제하지 않았다.
- 1×1과 3×3은 OFM block, weight 크기, 탭 수가 언제나 다르다. Cin ≥ 40에서는 traversal도 다르다. 커널 크기 효과는 분리되지 않는다.
- 3×3의 768과 Cin 비례가 다른 Cin(예: 16의 배수가 아닌 작은 Cin, Cin > 64), 다른 OFM block, stride 2로 일반화되는지는 측정하지 않았다.
- Vela 성능 모델과의 차이: Vela의 MAC 사이클 추정은 3×3 Cin 40과 48을 같게(31,729) 보았다. 실측 MAC_ACTIVE는 Cin에 비례했다. Vela 추정이 이 지표를 예측하지 못했다는 관측일 뿐, Vela 모델의 결함이라고 단정하지 않는다.
